#!/usr/bin/env python3
"""Audit Candana's official PDFs; never infer permission from free access."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "build/candana-audit"
PAGES = ("https://www.mindreleased.com/pali-suttas",
         "https://www.mindreleased.com/new-page-1",
         "https://www.mindreleased.com/sutta-nipata")
LICENSE = "Candana — free distribution, unaltered contents"
RIGHTS_BASIS = ("The exact source PDF grants redistribution in any medium, "
                "free of charge and without altering its contents; its notice "
                "and the source SHA-256 are recorded in the Candana manifest.")
MANIFEST = ROOT / "metadata/source-manifests/candana.json"
BOOKS = (
    ("an-book1", "Aṅguttara Nikāya — Book of the Ones", "anguttara-nikaya",
     "https://www.mindreleased.com/s/Book-1_Anguttara-Nikya-A-New-Translation.pdf"),
    ("sutta-nipata", "Sutta Nipāta — A New Translation", "khuddaka-nikaya/sutta-nipata",
     "https://www.mindreleased.com/s/Sutta-Nipta_Bhikkhu_Candana_2026-sm.pdf"),
)
NOTICE = ("Copyright © Bhikkhu Candana, 2020, 2026. Free distribution only; do not alter the contents. "
          "The original book, including its complete permission notice, accompanies this text.")
REVIEWED_COMPOUND_BREAKS = {
    ("Self-", "Awakened"), ("Wheel-", "Turning"), ("heart-", "wrenching"),
    ("merit-", "making"), ("one-of-", "a-kind"), ("well-", "developed"), ("well-", "proclaimed"),
}


def granted_notice(text: str) -> bool:
    """Recognize the reviewed grant, not just a copyright/free-download label."""
    compact = re.sub(r"\s+", " ", text).casefold()
    return all((
        "you may copy, reprint, republish" in compact,
        "redistribute this work" in compact,
        "in any medium" in compact,
        "free of charge" in compact,
        "not alter its content" in compact,
        "copyright" in compact and "candana" in compact,
    ))


def extract(path: Path, first_pages: int | None = None) -> str:
    args = ["pdftotext", "-layout"]
    if first_pages:
        args += ["-f", "1", "-l", str(first_pages)]
    return subprocess.run([*args, str(path), "-"], check=True, capture_output=True, text=True).stdout


def audit_one(url: str) -> dict:
    key = hashlib.sha256(url.encode()).hexdigest()
    path = CACHE / (key + ".pdf")
    try:
        if not path.exists():
            return {"url": url, "rights": "PENDING_TIMER"}
        data = path.read_bytes()
        notice = extract(path, 10)
        return {"url": url, "sha256": hashlib.sha256(data).hexdigest(),
                "cache": path.relative_to(ROOT).as_posix(),
                "rights": "EXPLICIT_FREE_UNALTERED" if granted_notice(notice) else "NEEDS_PERMISSION_REVIEW"}
    except Exception as error:
        return {"url": url, "rights": "LOOKUP_FAILED", "error": str(error)}


def audit() -> dict:
    """Read queue evidence without bypassing its persistent pacing/cooldown."""
    from candana_queue import seed
    state = seed()
    return {"observed": "2026-11-05", "pages": list(PAGES),
            "sources": [{"url": job["url"], "rights": job.get("rights", job["state"])} for job in state["jobs"]]}


def split_an_one(text: str) -> tuple[dict[int, str], dict[int, int]]:
    """Split the numbered source, preserving every non-pagination body line.

    The source has precisely 627 standalone numbered headings. Chapter headings
    at the top of a page belong to the first discourse on that page, not the
    preceding discourse. Only a matching printed page number is removed.
    """
    pieces = []
    page_starts = []
    offset = 0
    for page_number, page in enumerate(text.split("\f"), 1):
        lines = page.splitlines(keepends=True)
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and lines[-1].strip() == str(page_number):
            lines.pop()
        content = "".join(lines).rstrip() + "\n\n"
        page_starts.append((offset, content, page_number))
        pieces.append(content)
        offset += len(content)
    cleaned = "".join(pieces)
    closing = re.search(r"(?m)^\s*\(Here ends Book of the Ones\)", cleaned)
    if closing is None:
        raise ValueError("AN Book 1 lacks its expected end-of-translation boundary")
    cleaned = cleaned[:closing.start()]
    headings = list(re.finditer(r"(?m)^[ \t]*(\d+)\.[ \t]*$", cleaned))
    numbers = [int(match.group(1)) for match in headings]
    if numbers != list(range(1, 628)):
        raise ValueError("AN Book 1 must contain exactly the ordered headings 1–627")
    starts = [match.start() for match in headings]
    pages = {}
    for position, heading in enumerate(headings):
        preceding = next((row for row in reversed(page_starts) if row[0] <= heading.start()), None)
        if preceding is None:
            raise ValueError("No PDF page for source heading")
        page_start, content, page_number = preceding
        prefix = cleaned[page_start:heading.start()]
        if re.match(r"\s*AN I\s*\n", prefix) and not re.search(r"(?m)^\s*\d+\.\s*$", prefix):
            starts[position] = page_start
        elif position:
            between_start = headings[position - 1].end()
            between = cleaned[between_start:heading.start()]
            chapter = re.search(r"(?m)^[ \t]{8,}[^\n]*Vagga[ \t]*$", between)
            if chapter:
                # Some subgroup headings occur mid-page (for example the fifth
                # subgroup before 235), not under a repeated AN I page header.
                starts[position] = between_start + chapter.start()
        pages[position + 1] = page_number
    sections = {number: cleaned[start:starts[number] if number < 627 else len(cleaned)].strip() + "\n"
                for number, start in enumerate(starts, 1)}
    if any(not re.search(r"[A-Za-z]{3}", value) for value in sections.values()):
        raise ValueError("An empty/number-only Candana source unit cannot be published")
    return sections, pages


def _json_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def reflow_text(body: str) -> str:
    """Discard physical line wrapping/indentation, not words or paragraphs."""
    original = body
    def join_compound(match):
        if match.groups() not in REVIEWED_COMPOUND_BREAKS:
            raise ValueError(f"Unreviewed hyphenated line break: {match.groups()}")
        return "".join(match.groups())
    body = re.sub(r"([A-Za-z]+(?:-[A-Za-z]+)*-)\n[ \t\n]*([A-Za-z]+(?:-[A-Za-z]+)*)", join_compound, body)
    paragraphs = re.split(r"\n[ \t]*\n", body.strip())
    reflowed = "\n\n".join(" ".join(part.split()) for part in paragraphs if part.strip()) + "\n"
    if re.sub(r"\s+", "", original) != re.sub(r"\s+", "", reflowed):
        raise ValueError("Text reflow changed non-whitespace characters")
    return reflowed


def install(local_directory: Path) -> dict:
    """Import only the two individually reviewed book editions from local bytes."""
    if MANIFEST.exists() and json.loads(MANIFEST.read_text()).get("numbered_extension"):
        raise ValueError("Legacy two-book installation would discard numbered imports; use --install-numbered")
    assets, books = [], []
    new_paths: dict[str, str] = {}
    for key, title, collection, url in BOOKS:
        source = local_directory / (key + ".pdf")
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"Reviewed local PDF is missing or unsafe: {source}")
        notice = extract(source, 10)
        if not granted_notice(notice):
            raise ValueError(f"No reviewed free-unaltered grant inside {key}")
        data = source.read_bytes()
        relative = f"theravada/tipitaka/translations/en/candana/books/{key}.pdf"
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != data:
            raise ValueError(f"Refusing to replace a different pinned book: {relative}")
        target.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        book = {"id": key, "title": title, "collection": collection,
                "translator": "Bhikkhu Candana", "source_url": url,
                "local_path": relative, "sha256": digest, "license": LICENSE,
                "permission_pages": [3] if key == "an-book1" else [7],
                "conditions": ["Copies must be available free of charge", "Do not alter the contents"],
                "formats": ["Original PDF", "Unaltered text in another medium"],
                "plain_text_status": "VERIFIED_NUMBERED_EXTRACTION" if key == "an-book1" else "HOLD_EXTRACTION_QUALITY"}
        books.append(book)
        assets.append({**book, "label": title + " — Bhikkhu Candana (original PDF)",
                       "license_url": url, "rights_status": "EXPLICIT_PERMISSION_VERIFIED"})
        new_paths[relative] = LICENSE
    sections, pages = split_an_one(extract(local_directory / "an-book1.pdf"))
    with (ROOT / "theravada/tipitaka/sutta/suttacentral-sujato-text-ledger.tsv").open(newline="", encoding="utf-8") as handle:
        reference_rows = [row for row in csv.DictReader(handle, dialect="excel-tab")
                          if row["canonical_id"].startswith("AN 1.")]
    # These three source units are present in Candana's book but not in the
    # existing Sujato ledger. They keep their author's explicit numbers.
    reference_rows.extend({"canonical_id": f"AN 1.{number}"} for number in (330, 331, 332))
    imported, covered = [], set()
    for row in reference_rows:
        match = re.fullmatch(r"AN 1\.(\d+)(?:[-–](\d+))?", row["canonical_id"])
        if not match:
            raise ValueError(f"Unrecognized reference boundary: {row['canonical_id']}")
        first, last = int(match[1]), int(match[2] or match[1])
        numbers = range(first, last + 1)
        if any(number in covered or number not in sections for number in numbers):
            raise ValueError("The reference units must partition the book without gaps or overlap")
        covered.update(numbers)
        body = reflow_text("\n".join(sections[number] for number in numbers))
        canonical_id = row["canonical_id"]
        relative = "theravada/tipitaka/translations/en/candana/an/" + canonical_id.lower().replace(" ", "") + ".txt"
        source_url = books[0]["source_url"] + f"#page={pages[first]}"
        header = "\n".join((f"{canonical_id} - {canonical_id}", "Translated by Bhikkhu Candana",
                            f"Source: {source_url}", f"License: {LICENSE}", NOTICE))
        source = header + "\n\n" + body
        path = ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        imported.append({"kind": "sutta", "canonical_id": canonical_id, "collection": "anguttara-nikaya",
                         "title": canonical_id, "translator": "Bhikkhu Candana", "version": "candana",
                         "source_url": source_url, "source_revision": books[0]["sha256"],
                         "license": LICENSE, "license_url": books[0]["source_url"], "local_path": relative,
                         "sha256": hashlib.sha256(source.encode()).hexdigest(),
                         "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                         "book": "an-book1", "source_numbers": [first, last], "source_page": pages[first],
                         "rights_status": "EXPLICIT_PERMISSION_VERIFIED", "completeness_status": "UNKNOWN",
                         "completeness_scope": "All numbered units in this range are preserved from the pinned book; canonical equivalence has not been independently reviewed."})
        new_paths[relative] = LICENSE
    if covered != set(range(1, 628)):
        raise ValueError("The mapped reader units do not cover all 627 numbered source units")
    manifest = {"schema_version": 1, "observed": "2026-11-05", "license": LICENSE,
                "rights_basis": RIGHTS_BASIS, "books": books, "texts": imported,
                "default_translator": "candana", "source_units": 627,
                "scope": "Only the exact book PDFs and unaltered extracted units listed here; not a blanket grant for other PDFs or recordings."}
    _json_write(MANIFEST, manifest)
    new_paths[MANIFEST.relative_to(ROOT).as_posix()] = "CC0-1.0 project metadata"
    for filename, field, rows, predicate in (
        ("eligible-assets.json", "assets", assets, lambda item: item.get("translator") == "Bhikkhu Candana"),
        ("eligible-texts.json", "texts", imported, lambda item: item.get("version") == "candana"),
    ):
        path = ROOT / "metadata" / filename
        document = json.loads(path.read_text(encoding="utf-8"))
        document[field] = [item for item in document[field] if not predicate(item)] + rows
        if "count" in document:
            document["count"] = len(document[field])
        if "policy" in document:
            document["policy"] = "Documented CC0, verified public domain, or source-specific explicit permission"
        _json_write(path, document)
    # Exact new outputs receive their reviewed scope; existing hashes are never
    # refreshed here. The normal reviewed-files validator handles those later.
    sys.path.insert(0, str(ROOT / "tools"))
    from validate_public_tree import RIGHTS_BASIS_BY_SCOPE
    new_paths["tools/buddhist_canon_pipeline/import_candana.py"] = "0BSD"
    new_paths["docs/tasks/candana-ingestion.md"] = "CC0-1.0 project documentation"
    allowlist = ROOT / "metadata/public-file-allowlist.json"
    document = json.loads(allowlist.read_text(encoding="utf-8"))
    existing = {item["path"] for item in document["files"]}
    for path, scope in new_paths.items():
        if path not in existing:
            document["files"].append({"path": path, "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
                                      "license_scope": scope, "rights_basis": RIGHTS_BASIS_BY_SCOPE[scope]})
    document["files"].sort(key=lambda item: item["path"])
    _json_write(allowlist, document)
    return {"books": len(books), "reader_units": len(imported), "source_units": len(covered),
            "new_paths": len(new_paths)}


def verified_manifest(root: Path = ROOT, *, require_review: bool = False) -> dict:
    """Recheck original grants, pinned bytes and every extracted text unit."""
    manifest = json.loads((root / MANIFEST.relative_to(ROOT)).read_text(encoding="utf-8"))
    if (manifest.get("schema_version") != 1 or manifest.get("license") != LICENSE
            or manifest.get("rights_basis") != RIGHTS_BASIS):
        raise ValueError("Unreviewed Candana rights manifest")
    books = {}
    for book in manifest["books"]:
        relative = Path(book["local_path"])
        if relative.is_absolute() or ".." in relative.parts or book["license"] != LICENSE:
            raise ValueError("Unsafe/unreviewed Candana book entry")
        path = root / relative
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != book["sha256"]:
            raise ValueError(f"Candana book differs from its reviewed source: {relative}")
        if not granted_notice(extract(path, 10)):
            raise ValueError(f"Candana book lacks its recorded permission: {relative}")
        books[book["id"]] = book
    if __package__:
        from .candana_numbered_books import BOOK_IDS, verify as verify_numbered
    else:
        from candana_numbered_books import BOOK_IDS, verify as verify_numbered
    additional = BOOK_IDS if manifest.get("numbered_extension") else set()
    if set(books) != {item[0] for item in BOOKS} | additional:
        raise ValueError("Candana book scope changed without review")
    supported_text_books = {"an-book1"} | additional
    if any(row.get("book") not in supported_text_books for row in manifest["texts"]):
        raise ValueError("Candana text refers to an unsupported source book")
    if len({row["canonical_id"] for row in manifest["texts"]}) != len(manifest["texts"]):
        raise ValueError("Duplicate Candana text ID across source books")
    sections, pages = split_an_one(extract(root / books["an-book1"]["local_path"]))
    seen, covered = set(), set()
    for row in manifest["texts"]:
        if row["book"] != "an-book1":
            continue
        if row["license"] != LICENSE or row["canonical_id"] in seen or row["book"] != "an-book1":
            raise ValueError("Unreviewed or duplicate Candana text entry")
        seen.add(row["canonical_id"])
        first, last = row["source_numbers"]
        numbers = range(first, last + 1)
        if first < 1 or last > 627 or first > last or covered.intersection(numbers):
            raise ValueError("Invalid/overlapping Candana source boundaries")
        covered.update(numbers)
        body = reflow_text("\n".join(sections[number] for number in numbers))
        relative = Path(row["local_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe Candana source text path")
        path = root / relative
        raw = path.read_bytes()
        expected_url = books["an-book1"]["source_url"] + f"#page={pages[first]}"
        if (path.is_symlink() or hashlib.sha256(raw).hexdigest() != row["sha256"]
                or raw.decode().split("\n\n", 1)[1] != body
                or hashlib.sha256(body.encode()).hexdigest() != row["body_sha256"]
                or row["source_url"] != expected_url or row["source_revision"] != books["an-book1"]["sha256"]):
            raise ValueError(f"Candana text differs from its numbered source: {row['canonical_id']}")
    if covered != set(range(1, 628)):
        raise ValueError("Candana manifest omits numbered source units")
    if require_review:
        report = json.loads((root / "metadata/reports/candana-extraction-2026-11-05.json").read_text(encoding="utf-8"))
        if (report.get("source_sha256") != books["an-book1"]["sha256"]
                or report.get("pages_compared") != 175 or report.get("mismatched_pages") != []
                or report.get("status") != "TWO_ENGINE_AGREEMENT_WITH_VISUAL_SAMPLES"
                or not {36, 39, 100, 210}.issubset(report.get("visual_sample_pages", []))
                or report.get("reader_body_hashes") != {row["canonical_id"]: row["body_sha256"] for row in manifest["texts"] if row["book"] == "an-book1"}):
            raise ValueError("Candana extraction review is missing or stale; do not publish unchecked text")
    verify_numbered(root, manifest, require_review)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--audit", action="store_true")
    group.add_argument("--install-local", type=Path)
    group.add_argument("--install-numbered", action="store_true", help="Import checked cached AN Books Two/Three mappings")
    args = parser.parse_args()
    if args.install_numbered:
        from candana_numbered_books import install as install_numbered
        print(json.dumps(install_numbered(), indent=2))
    elif args.install_local:
        print(json.dumps(install(args.install_local), indent=2))
    else:
        result = audit()
        print(json.dumps({"sources": len(result["sources"]), "permitted": [row["url"] for row in result["sources"]
                          if row["rights"] == "EXPLICIT_FREE_UNALTERED"],
                          "status_counts": {status: sum(row["rights"] == status for row in result["sources"])
                                            for status in sorted({row["rights"] for row in result["sources"]})}}, indent=2))
