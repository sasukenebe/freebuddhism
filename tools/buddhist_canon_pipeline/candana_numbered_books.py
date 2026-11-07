"""Import pinned AN books using checked source boundaries and explicit text-ID maps."""

from __future__ import annotations

import csv
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = "metadata/reports/candana-numbered-books-2026-11-07.json"
BOOK_IDS = {"an-book2", "an-book3"}


@lru_cache(maxsize=8)
def pinned_text(path: str, engine: str, verified_sha256: str) -> str:
    """Reuse extraction within a run; the caller checks current PDF bytes before every call."""
    if __package__:
        from .prepare_candana_batch import pdf_text
    else:
        from prepare_candana_batch import pdf_text
    return pdf_text(Path(path), engine)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def book_three_map() -> dict[str, list[str]]:
    """Source labels are retained; no suffix stripping or blanket numeric offset."""
    result = {f"AN 3.{number}": [str(number)] for number in range(1, 81)}
    result.update({"AN 3.81": ["81a"], "AN 3.82": ["81b"]})
    result.update({f"AN 3.{number + 1}": [str(number)] for number in range(82, 92)})
    result.update({"AN 3.93": ["92a"], "AN 3.94": ["92b"]})
    result.update({f"AN 3.{number + 2}": [str(number)] for number in range(93, 97)})
    # The source separates coarse jute and fine Kāsi cloth; the site's AN 3.99
    # includes both halves. Preserve both source sections, in order, in one reader.
    result["AN 3.99"] = ["97", "98"]
    result.update({f"AN 3.{number + 1}": [str(number)] for number in range(99, 155)})
    return result


def mappings(book: str, sections: list[dict], reference: list[dict]) -> dict[str, list[str]]:
    if book == "an-book3":
        result = book_three_map()
        known = {row["canonical_id"] for row in reference}
        if set(result) - known:
            raise ValueError("Book Three map refers to an absent site text ID")
        return result
    if book != "an-book2":
        raise ValueError("Unsupported numbered Candana book")
    result, covered = {}, set()
    for row in reference:
        match = re.fullmatch(r"AN 2\.(\d+)(?:[-–](\d+))?", row["canonical_id"])
        if not match:
            continue
        first, last = int(match[1]), int(match[2] or match[1])
        selected = [part for part in sections if first <= part["first"] <= part["last"] <= last]
        actual = [number for part in selected for number in range(part["first"], part["last"] + 1)]
        if actual != list(range(first, last + 1)) or covered.intersection(actual):
            raise ValueError("Book Two reference boundaries split, omit or repeat source numbers")
        covered.update(actual)
        result[row["canonical_id"]] = [part["source_label"] for part in selected]
    if covered != set(range(1, 480)):
        raise ValueError("Book Two site mappings do not cover all 479 source numbers")
    return result


def plan(root: Path, source_paths: dict[str, Path]) -> tuple[list[dict], list[dict], dict]:
    if __package__:
        from .import_candana import LICENSE, NOTICE, granted_notice
        from .prepare_candana_batch import engine_comparison, numbered_book, pages_of
    else:
        from import_candana import LICENSE, NOTICE, granted_notice
        from prepare_candana_batch import engine_comparison, numbered_book, pages_of
    recipes_path = root / "metadata/candana-batch-recipes.json"
    recipes = json.loads(recipes_path.read_text())["recipes"]
    recipes = [row for row in recipes if row["id"] in BOOK_IDS]
    if {row["id"] for row in recipes} != BOOK_IDS:
        raise ValueError("Numbered-book recipes are missing or duplicated")
    with (root / "theravada/tipitaka/sutta/suttacentral-sujato-text-ledger.tsv").open(newline="") as handle:
        reference = list(csv.DictReader(handle, dialect="excel-tab"))
    books, texts, reports = [], [], {}
    for recipe in recipes:
        key = recipe["id"]
        path = source_paths[key]
        if path.is_symlink() or sha(path.read_bytes()) != recipe["source_sha256"]:
            raise ValueError(f"Numbered Candana source changed: {key}")
        left, right = (pinned_text(str(path), engine, recipe["source_sha256"]) for engine in ("poppler", "mupdf"))
        if not all(granted_notice("\f".join(pages_of(value)[:10])) for value in (left, right)):
            raise ValueError(f"Numbered Candana permission is missing: {key}")
        comparison = engine_comparison(left, right, pagination=True)
        if comparison["mismatched_pages"]:
            raise ValueError(f"Numbered Candana extraction disagreement: {key}")
        partition = numbered_book(left, recipe)
        if partition["status"] != "PARTITION_CHECK_PASSED":
            raise ValueError(f"Numbered Candana source boundaries failed: {key}")
        number = 2 if key == "an-book2" else 3
        refs = [row for row in reference if row["canonical_id"].startswith(f"AN {number}.")]
        groups = mappings(key, partition["sections"], refs)
        by_label = {row["source_label"]: row for row in partition["sections"]}
        used = []
        book = {"id": key, "title": recipe["title"].removeprefix("Candana — "),
                "collection": "anguttara-nikaya", "translator": "Bhikkhu Candana",
                "source_url": recipe["source_url"], "source_sha256": recipe["source_sha256"],
                "sha256": recipe["source_sha256"], "license": LICENSE,
                "local_path": f"theravada/tipitaka/translations/en/candana/books/{key}.pdf",
                "permission_pages": [3],
                "conditions": ["Copies must be available free of charge", "Do not alter the contents"],
                "formats": ["Original PDF", "Unaltered text in another medium"],
                "plain_text_status": "VERIFIED_NUMBERED_EXTRACTION" if number == 2 else "PARTIAL_CANONICAL_MAPPING"}
        books.append(book)
        for canonical_id, labels in groups.items():
            if any(label not in by_label or label in used for label in labels):
                raise ValueError("Missing or repeated source section in numbered Candana mapping")
            parts = [by_label[label] for label in labels]
            used.extend(labels)
            body = "\n".join(part["body"] for part in parts)
            titles = [re.sub(r"^[\d a-z–.-]+\.[ \t]*", "", part["title"]).strip() for part in parts]
            title = " / ".join(value for value in titles if value) or canonical_id
            first_page = parts[0]["source_page"]
            source_url = book["source_url"] + f"#page={first_page}"
            relative = "theravada/tipitaka/translations/en/candana/an/" + canonical_id.lower().replace(" ", "") + ".txt"
            numbering_note = "Candana source labels: " + ", ".join(labels) + ". Site text ID: " + canonical_id + "."
            header = "\n".join((f"{canonical_id} - {title}", "Translated by Bhikkhu Candana",
                                f"Source: {source_url}", f"License: {LICENSE}", NOTICE, numbering_note))
            raw = header + "\n\n" + body
            texts.append({"kind": "sutta", "canonical_id": canonical_id, "collection": "anguttara-nikaya",
                          "title": title, "translator": "Bhikkhu Candana", "version": "candana",
                          "source_url": source_url, "source_revision": book["sha256"],
                          "license": LICENSE, "license_url": book["source_url"], "local_path": relative,
                          "sha256": sha(raw.encode()), "body_sha256": sha(body.encode()),
                          "book": key, "source_labels": labels, "source_page": first_page,
                          "rights_status": "EXPLICIT_PERMISSION_VERIFIED", "completeness_status": "UNKNOWN",
                          "completeness_scope": "The listed source sections are preserved without word changes; this does not certify translation accuracy or the completeness of the canonical collection.",
                          "_source_text": raw})
        held = [label for label in by_label if label not in used]
        reports[key] = {"source_sha256": book["sha256"], "comparison": comparison,
                        "translation_pages": [recipe["first_page"], recipe["last_page"]],
                        "source_sections": len(by_label), "imported_source_sections": len(used),
                        "imported_readers": len(groups), "held_source_labels": held,
                        "mapping": "Book Two uses explicit source numbers; Book Three uses a reviewed piecewise map through site AN 3.155. The coarse/fine cloth source sections 97 and 98 are retained together at AN 3.99.",
                        "scope_limit": "Later Book Three practices, paired good/evil conduct, and passion repetitions require grouped correspondence; they are not attached to incorrect single-sutta IDs."}
    report = {"schema_version": 1, "observed": "2026-11-07", "status": "SOURCE_VERIFIED_WITH_EXPLICIT_MAPPING_LIMITS",
              "recipe_sha256": sha(recipes_path.read_bytes()), "books": reports,
              "reader_body_hashes": {row["canonical_id"]: row["body_sha256"] for row in texts}}
    return books, texts, report


def install(root: Path = ROOT) -> dict:
    if __package__:
        from .import_candana import LICENSE, MANIFEST
    else:
        from import_candana import LICENSE, MANIFEST
    sys.path.insert(0, str(root / "tools"))
    from validate_public_tree import RIGHTS_BASIS_BY_SCOPE
    manifest_path = root / MANIFEST.relative_to(ROOT)
    manifest = json.loads(manifest_path.read_text())
    recipes = json.loads((root / "metadata/candana-batch-recipes.json").read_text())["recipes"]
    jobs = json.loads((root / "build/candana-audit/queue.json").read_text())["jobs"]
    paths = {}
    for recipe in recipes:
        matches = [job for job in jobs if job["url"] == recipe["source_url"] and job["state"] == "COLLECTED"]
        if len(matches) != 1:
            raise ValueError("Required numbered book was not collected")
        paths[recipe["id"]] = root / matches[0]["cache"]
    books, texts, report = plan(root, paths)  # Complete all checks before writing any corpus files.
    # Check every pre-existing target before writing the first new file.
    for book in books:
        target = root / book["local_path"]
        if target.is_symlink() or (target.exists() and target.read_bytes() != paths[book["id"]].read_bytes()):
            raise ValueError("Refusing to replace a different numbered book")
    for row in texts:
        target = root / row["local_path"]
        if target.is_symlink() or (target.exists() and target.read_text() != row["_source_text"]):
            raise ValueError("Refusing to overwrite a different imported numbered text")
    new_paths = {}
    for book in books:
        target = root / book["local_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != paths[book["id"]].read_bytes():
            raise ValueError("Refusing to replace a different numbered book")
        shutil.copyfile(paths[book["id"]], target)
        new_paths[book["local_path"]] = LICENSE
    for row in texts:
        target = root / row["local_path"]
        raw = row.pop("_source_text")
        if target.exists() and target.read_text() != raw:
            raise ValueError("Refusing to overwrite a different imported numbered text")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(raw, encoding="utf-8")
        new_paths[row["local_path"]] = LICENSE
    manifest["books"] = [row for row in manifest["books"] if row["id"] not in BOOK_IDS] + books
    manifest["texts"] = [row for row in manifest["texts"] if row["book"] not in BOOK_IDS] + texts
    manifest["numbered_extension"] = {"schema_version": 1, "report": REPORT_PATH,
                                      "books": sorted(BOOK_IDS), "reader_count": len(texts)}
    manifest["source_units_scope"] = "The legacy source_units field counts Book One only; the numbered-extension report records additional source coverage separately."
    write_json(manifest_path, manifest)
    write_json(root / REPORT_PATH, report)
    new_paths[REPORT_PATH] = "CC0-1.0 project metadata"
    for filename, field, rows in (("eligible-texts.json", "texts", texts),
                                  ("eligible-assets.json", "assets", [dict(book, license_url=book["source_url"], rights_status="EXPLICIT_PERMISSION_VERIFIED") for book in books])):
        path = root / "metadata" / filename
        document = json.loads(path.read_text())
        document[field] = [row for row in document[field] if row.get("book", row.get("id")) not in BOOK_IDS] + rows
        if "count" in document:
            document["count"] = len(document[field])
        write_json(path, document)
    allowlist = root / "metadata/public-file-allowlist.json"
    document = json.loads(allowlist.read_text())
    known = {entry["path"] for entry in document["files"]}
    for relative, scope in new_paths.items():
        if relative not in known:
            document["files"].append({"path": relative, "sha256": sha((root / relative).read_bytes()),
                                      "license_scope": scope, "rights_basis": RIGHTS_BASIS_BY_SCOPE[scope]})
    document["files"].sort(key=lambda row: row["path"])
    write_json(allowlist, document)
    return {"new_readers": len(texts), "by_book": {key: report["books"][key]["imported_readers"] for key in sorted(BOOK_IDS)},
            "held_source_labels": report["books"]["an-book3"]["held_source_labels"]}


def verify(root: Path, manifest: dict, require_review: bool) -> None:
    extension = manifest.get("numbered_extension")
    actual = [row for row in manifest["books"] if row["id"] in BOOK_IDS]
    if not extension:
        if actual or any(row["book"] != "an-book1" for row in manifest["texts"]):
            raise ValueError("Numbered Candana texts have no reviewed extension")
        return
    if extension != {"schema_version": 1, "report": REPORT_PATH, "books": sorted(BOOK_IDS), "reader_count": 349}:
        raise ValueError("Numbered Candana extension scope changed")
    books, texts, report = plan(root, {book["id"]: root / book["local_path"] for book in actual})
    if actual != books:
        raise ValueError("Numbered Candana book metadata changed")
    expected = []
    for row in texts:
        raw = row.pop("_source_text")
        path = root / row["local_path"]
        if path.is_symlink() or path.read_text() != raw:
            raise ValueError("Numbered Candana reader differs from the source")
        expected.append(row)
    if [row for row in manifest["texts"] if row["book"] in BOOK_IDS] != expected:
        raise ValueError("Numbered Candana text mapping changed")
    if require_review and json.loads((root / REPORT_PATH).read_text()) != report:
        raise ValueError("Numbered Candana extraction/mapping report is missing or stale")
