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
GROUP_SOURCE_MAP = {
    "156": (list(range(157, 163)), (286, 288), "cf363139e54784393ea41f49fcb6f35dbb8a86a5fe44513798c65321441f46a9"),
    "157": ([163, 164], (289, 289), "d742bb1d4946ef2903d340590b9a7512eb8dd8dd3e655bb75597a1d51a246037"),
    "158": ([165, 166], (289, 290), "6a592f8a0129507bf0de1caf68eaa6d7ae212439f28410b3572038f7861e632b"),
    "159": ([167, 168], (290, 290), "2bcdfc7c62cba94b73c10ea06956ff8308299168e309f92d82f286127a23b551"),
    "160": ([169, 170], (291, 291), "98f1e9753ce4083e55672945e43622a33db227cf8db2e718c4cdb1fe3446187d"),
    "161": ([171, 172], (291, 291), "25e95e7814abff9f06c4aa95467336e0fd3501725777656a64298fde5a939d09"),
    "162": ([173, 174], (291, 292), "b3ffdeb60276895df8755ae9e35e990859d5569d9608c920300347a56b3313e6"),
    "163": ([175, 176], (292, 292), "7ca45849b368ab8e9badd91551f35caae96ebba1c8338ec74993d2ca6f7c045b"),
    "164": ([177, 178], (292, 293), "a782d957f191539831738c6b1fc24e71e068ef63dbb024a2ee436627c22e5eaa"),
    "165": ([179, 180], (293, 293), "2df65a789a3f9d70bb614111d71563c9a1a8e8d5fa9c77d3e1afbba715c91866"),
    "166": ([181, 182], (293, 294), "600eb173bcf710c6cfa0fa89d1ec2c26f587b885e6c6ff495a0c01c344122ffd"),
}
GROUP_REFERENCE_SOURCE_MAP = {
    # The intact final chapter is associated with the site's one existing
    # grouped reference. Its internal source labels and topic wording do not
    # support a one-to-one split, so preserve it once and keep that discrepancy
    # visible for human review.
    "167-352": (["AN 3.183-352"], (295, 299),
                "cf449ffc66761c1c7d9c3351ee1f59dbbddaf5157a52708519bc06e74639eb02",
                "Rāga Peyyāla Vagga — The Section on Abbreviated Repetitions, Starting with Passion"),
}


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


def replace_numbered_rows(existing: list[dict], replacements: list[dict]) -> list[dict]:
    """Replace this book family without moving unrelated books or editions."""
    def selected(row):
        return row.get('book', row.get('id')) in BOOK_IDS
    positions = [i for i, row in enumerate(existing) if selected(row)]
    insertion = positions[0] if positions else len(existing)
    return ([row for row in existing[:insertion] if not selected(row)]
            + replacements + [row for row in existing[insertion:] if not selected(row)])


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
    # Reviewed against both complete bodies and PDF 284–286: source 155 is
    # the three-practice teaching whose middle practice is the four foundations
    # of mindfulness. Source 156 instead groups six further practices and must
    # not be attached to just AN 3.157 or split by an assumed numeric offset.
    result["AN 3.156"] = ["155"]
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


def plan(root: Path, source_paths: dict[str, Path]) -> tuple[list[dict], list[dict], list[dict], dict]:
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
    books, texts, group_texts, reports = [], [], [], {}
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
        grouped_ids = set()
        grouped_labels = set()
        for label, (numbers, page_range, expected_section_sha256) in (GROUP_SOURCE_MAP.items() if key == "an-book3" else ()):
            if label not in by_label or label in used or label in grouped_labels:
                raise ValueError("Missing, repeated or already assigned grouped source section")
            canonical_ids = [f"AN 3.{number}" for number in numbers]
            if any(canonical_id not in {row["canonical_id"] for row in refs} for canonical_id in canonical_ids):
                raise ValueError("Grouped Candana source refers to an absent site text ID")
            if grouped_ids.intersection(canonical_ids):
                raise ValueError("Grouped Candana source memberships overlap")
            grouped_ids.update(canonical_ids)
            grouped_labels.add(label)
            part = by_label[label]
            if (part["source_page"] != page_range[0]
                    or sha(part["body"].encode()) != expected_section_sha256):
                raise ValueError("Grouped Candana source differs from the reviewed section or PDF start page")
            reference_label = f"AN 3.{numbers[0]}–{numbers[-1]}"
            group_id = f"an3-{numbers[0]}-{numbers[-1]}"
            title = re.sub(r"^\d+[a-z]?\.[ \t]*", "", part["title"]).strip()
            source_url = book["source_url"] + f"#page={page_range[0]}"
            relative = f"theravada/tipitaka/translations/en/candana/groups/{group_id}.txt"
            header = "\n".join((f"{reference_label} - {title}", "Translated by Bhikkhu Candana",
                                f"Source: {source_url}", f"License: {LICENSE}", NOTICE,
                                f"Candana source section: {label}. Shared across: {', '.join(canonical_ids)}."))
            raw = header + "\n\n" + part["body"]
            group_texts.append({
                "kind": "sutta_group", "group_id": group_id, "canonical_id": canonical_ids[0],
                "canonical_ids": canonical_ids, "group_reference": reference_label,
                "collection": "anguttara-nikaya", "title": title, "translator": "Bhikkhu Candana",
                "version": f"candana-group-{label}", "source_url": source_url,
                "source_revision": book["sha256"], "license": LICENSE,
                "license_url": book["source_url"], "local_path": relative,
                "sha256": sha(raw.encode()), "body_sha256": sha(part["body"].encode()),
                "book": key, "source_labels": [label], "source_pdf_pages": list(page_range),
                "rights_status": "EXPLICIT_PERMISSION_VERIFIED",
                "completeness_status": "GROUPED_SOURCE_SCOPE",
                "completeness_scope": "One intact Candana source passage covers the listed existing text references; it is not a separate complete translation for each reference.",
                "_source_text": raw,
            })
        for label, (canonical_ids, page_range, expected_section_sha256, title) in (
                GROUP_REFERENCE_SOURCE_MAP.items() if key == "an-book3" else ()):
            if label not in by_label or label in used or label in grouped_labels:
                raise ValueError("Missing, repeated or already assigned grouped source section")
            if len(canonical_ids) != 1 or canonical_ids[0] not in {row["canonical_id"] for row in refs}:
                raise ValueError("Whole-group Candana source must point to one existing grouped text ID")
            if grouped_ids.intersection(canonical_ids):
                raise ValueError("Grouped Candana source memberships overlap")
            grouped_ids.update(canonical_ids)
            grouped_labels.add(label)
            part = by_label[label]
            if (part["source_page"] != page_range[0]
                    or part["last"] != 352
                    or page_range[-1] != recipe["last_page"]
                    or list(by_label)[-1] != label
                    or sha(part["body"].encode()) != expected_section_sha256):
                raise ValueError("Final Candana group differs from the reviewed section or PDF boundaries")
            canonical_id = canonical_ids[0]
            reference_label = "AN 3.183–352"
            group_id = "an3-183-352"
            source_url = book["source_url"] + f"#page={page_range[0]}"
            relative = f"theravada/tipitaka/translations/en/candana/groups/{group_id}.txt"
            scope_note = ("Whole-group placement only: the source's 167–352 label and 16 lettered "
                          "headings are not aligned one-to-one with the site's 183–352 label and "
                          "17 topic names. No internal topic mapping is claimed; retain this "
                          "difference for human review.")
            header = "\n".join((f"{reference_label} - {title}", "Translated by Bhikkhu Candana",
                                f"Source: {source_url}", f"License: {LICENSE}", NOTICE,
                                f"Candana source section: {label}. Whole-group reference: {canonical_id}.",
                                scope_note))
            raw = header + "\n\n" + part["body"]
            group_texts.append({
                "kind": "sutta_group", "group_id": group_id, "canonical_id": canonical_id,
                "canonical_ids": canonical_ids, "group_reference": reference_label,
                "collection": "anguttara-nikaya", "title": title, "translator": "Bhikkhu Candana",
                "version": f"candana-group-{label}", "source_url": source_url,
                "source_revision": book["sha256"], "license": LICENSE,
                "license_url": book["source_url"], "local_path": relative,
                "sha256": sha(raw.encode()), "body_sha256": sha(part["body"].encode()),
                "book": key, "source_labels": [label], "source_pdf_pages": list(page_range),
                "rights_status": "EXPLICIT_PERMISSION_VERIFIED",
                "completeness_status": "GROUPED_SOURCE_SCOPE",
                "completeness_scope": scope_note,
                "_source_text": raw,
            })
        expected_group_labels = set(GROUP_SOURCE_MAP) | set(GROUP_REFERENCE_SOURCE_MAP)
        if key == "an-book3" and grouped_labels != expected_group_labels:
            raise ValueError("Reviewed grouped-source coverage is incomplete or changed")
        if key == "an-book3" and (len(group_texts) != len(GROUP_SOURCE_MAP) + len(GROUP_REFERENCE_SOURCE_MAP)
                                  or len(grouped_ids) != 27):
            raise ValueError("Reviewed grouped-source coverage is incomplete or changed")
        grouped_source_labels = [label for label in by_label if label in grouped_labels]
        held = [label for label in by_label if label not in used and label not in grouped_labels]
        reports[key] = {"source_sha256": book["sha256"], "comparison": comparison,
                        "translation_pages": [recipe["first_page"], recipe["last_page"]],
                        "source_sections": len(by_label),
                        "imported_source_sections": len(set(used) | grouped_labels),
                        "imported_readers": len(groups), "held_source_labels": held,
                        "held_source_labels_scope": "Source labels not represented either by a single-ID reader or an intact grouped edition.",
                        "grouped_source_labels": grouped_source_labels,
                        "grouped_source_bodies": [{"group_id": row["group_id"], "source_labels": row["source_labels"],
                                                   "canonical_ids": row["canonical_ids"],
                                                   "source_pdf_pages": row["source_pdf_pages"],
                                                   "body_sha256": row["body_sha256"]}
                                                  for row in group_texts if row["book"] == key],
                        "grouped_source_body_count": sum(row["book"] == key for row in group_texts),
                        "grouped_canonical_reference_count": sum(len(row["canonical_ids"]) for row in group_texts if row["book"] == key),
                        "unresolved_group_source_labels": [],
                        "mapping": "Book Two uses explicit source numbers; Book Three uses a reviewed piecewise map through site AN 3.156. The coarse/fine cloth source sections 97 and 98 are retained together at AN 3.99. Source 155 is the complete three-practice teaching at AN 3.156, including its closing sentence on PDF 286; sources 156–166 are retained as eleven intact grouped bodies covering AN 3.157–182. Source 167–352 is retained once as an intact passage under the existing grouped site reference AN 3.183–352; no one-to-one mapping of its internal topics is claimed.",
                        "scope_limit": "Sources 156–166 are represented as eleven shared group editions across 26 existing references. Source 167–352 is one whole-group edition under existing site reference AN 3.183–352; its source/site numbering and internal topic wording remain flagged for human review."}
    report = {"schema_version": 1, "observed": "2026-11-10", "status": "SOURCE_VERIFIED_WITH_EXPLICIT_MAPPING_LIMITS",
              "recipe_sha256": sha(recipes_path.read_bytes()), "books": reports,
              "reader_body_hashes": {row["canonical_id"]: row["body_sha256"] for row in texts}}
    return books, texts, group_texts, report


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
    books, texts, group_texts, report = plan(root, paths)  # Complete all checks before writing any corpus files.
    # Check every pre-existing target before writing the first new file.
    for book in books:
        target = root / book["local_path"]
        if target.is_symlink() or (target.exists() and target.read_bytes() != paths[book["id"]].read_bytes()):
            raise ValueError("Refusing to replace a different numbered book")
    for row in texts + group_texts:
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
    for row in texts + group_texts:
        target = root / row["local_path"]
        raw = row.pop("_source_text")
        if target.exists() and target.read_text() != raw:
            raise ValueError("Refusing to overwrite a different imported numbered text")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(raw, encoding="utf-8")
        new_paths[row["local_path"]] = LICENSE
    manifest["books"] = replace_numbered_rows(manifest['books'], books)
    manifest["texts"] = replace_numbered_rows(manifest['texts'], texts)
    manifest["group_texts"] = replace_numbered_rows(manifest.get("group_texts", []), group_texts)
    manifest["numbered_extension"] = {"schema_version": 1, "report": REPORT_PATH,
                                      "books": sorted(BOOK_IDS), "reader_count": len(texts)}
    manifest["numbered_group_extension"] = {"schema_version": 1, "report": REPORT_PATH,
                                            "books": ["an-book3"], "group_count": len(group_texts),
                                            "reference_count": sum(len(row["canonical_ids"]) for row in group_texts)}
    manifest["source_units_scope"] = "The legacy source_units field counts Book One only; the numbered-extension report records additional source coverage separately."
    write_json(manifest_path, manifest)
    write_json(root / REPORT_PATH, report)
    new_paths[REPORT_PATH] = "CC0-1.0 project metadata"
    for filename, field, rows in (("eligible-texts.json", "texts", texts),
                                  ("eligible-texts.json", "group_texts", group_texts),
                                  ("eligible-assets.json", "assets", [dict(book, license_url=book["source_url"], rights_status="EXPLICIT_PERMISSION_VERIFIED") for book in books])):
        path = root / "metadata" / filename
        document = json.loads(path.read_text())
        document.setdefault(field, [])
        document[field] = replace_numbered_rows(document[field], rows)
        if "count" in document and field == "texts":
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
    return {"numbered_readers": len(texts), "grouped_bodies": len(group_texts),
            "grouped_text_references": sum(len(row["canonical_ids"]) for row in group_texts),
            "by_book": {key: report["books"][key]["imported_readers"] for key in sorted(BOOK_IDS)},
            "held_source_labels": report["books"]["an-book3"]["held_source_labels"]}


def verify(root: Path, manifest: dict, require_review: bool) -> None:
    extension = manifest.get("numbered_extension")
    actual = [row for row in manifest["books"] if row["id"] in BOOK_IDS]
    if not extension:
        if actual or any(row["book"] != "an-book1" for row in manifest["texts"]):
            raise ValueError("Numbered Candana texts have no reviewed extension")
        return
    if extension != {"schema_version": 1, "report": REPORT_PATH, "books": sorted(BOOK_IDS), "reader_count": 350}:
        raise ValueError("Numbered Candana extension scope changed")
    books, texts, group_texts, report = plan(root, {book["id"]: root / book["local_path"] for book in actual})
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
    group_extension = manifest.get("numbered_group_extension")
    actual_groups = [row for row in manifest.get("group_texts", []) if row.get("book") in BOOK_IDS]
    if group_extension is None:
        if actual_groups:
            raise ValueError("Candana grouped texts have no reviewed group extension")
    else:
        expected_group_extension = {"schema_version": 1, "report": REPORT_PATH,
                                    "books": ["an-book3"], "group_count": 12,
                                    "reference_count": 27}
        expected_groups = []
        for row in group_texts:
            clean = dict(row)
            clean.pop("_source_text")
            expected_groups.append(clean)
        if group_extension != expected_group_extension or actual_groups != expected_groups:
            raise ValueError("Candana grouped-text scope or metadata changed")
        for row in group_texts:
            raw = row.pop("_source_text")
            path = root / row["local_path"]
            if path.is_symlink() or not path.is_file() or path.read_text(encoding="utf-8") != raw:
                raise ValueError("Candana grouped reader differs from its exact source passage")
    if require_review and json.loads((root / REPORT_PATH).read_text()) != report:
        raise ValueError("Numbered Candana extraction/mapping report is missing or stale")
