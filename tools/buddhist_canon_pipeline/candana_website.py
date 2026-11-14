#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Build opt-in website-only Candana editions from explicitly staged, pinned PDFs.

No network access and no translated body or private correspondence in Git.
Missing/changed private inputs fail an enabled build; they never cause fallback.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import zipfile

try:
    from .candana_processing_register import CONDITIONS
    from .candana_queue import checked_url
    from .distribution_policy import WEBSITE_LICENSE, WEBSITE_DISTRIBUTION
    from .import_candana import ROOT
    from .prepare_candana_batch import safe_relative, write_file, pages_of
    from .publication_rights import verify_identity_review
except ImportError:
    from candana_processing_register import CONDITIONS
    from candana_queue import checked_url
    from distribution_policy import WEBSITE_LICENSE, WEBSITE_DISTRIBUTION
    from import_candana import ROOT
    from prepare_candana_batch import safe_relative, write_file, pages_of
    from publication_rights import verify_identity_review

MANIFEST_PATH = "metadata/source-manifests/candana-website.json"
CACHE_PATH = "build/candana-website-inputs"
RIGHTS_PATH = "theravada/tipitaka/site/candana-permission.html"
RIGHTS_URL = "https://freebuddhism.org/" + RIGHTS_PATH
NOTICE = "; ".join(CONDITIONS) + ". Permission is for republication on freebuddhism.org; no general public-repository or third-party archive grant is claimed."
CHANGES = ("Presentation only: original heading retained in edition details; physical line wraps reflowed; "
           "reviewed page breaks retained as paragraph breaks. No words, punctuation, notes or closings removed or repaired.")
LAYOUT_CHANGES = ("Presentation only: original heading retained in edition details; reviewed paragraph boundaries retained "
                  "and continued prose reflowed without word changes. No words, punctuation, notes or closings removed or repaired.")
SCOPE = "Whole reviewed source translation, including section headings and closings; completeness and translation accuracy remain unverified."


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_partition(recipe: dict, pdf_pages: int) -> None:
    required = {"header_characters", "header_sha256", "raw_body_sha256", "page_break_paragraphs"}
    if not isinstance(recipe, dict) or not required <= set(recipe) <= required | {"page_break_joins"}:
        raise ValueError("Source partition contains unexpected or missing fields")
    if type(pdf_pages) is not int or pdf_pages < 1:
        raise ValueError("Invalid reviewed PDF page count")
    fields = ["page_break_paragraphs"]
    if "page_break_joins" in recipe:
        fields.append("page_break_joins")
    classified = set()
    for field in fields:
        boundaries = recipe[field]
        if (not isinstance(boundaries, list) or any(type(index) is not int for index in boundaries)
                or boundaries != sorted(set(boundaries))
                or any(not 1 <= index < pdf_pages for index in boundaries)
                or classified.intersection(boundaries)):
            raise ValueError("Page breaks need sorted unique integer classifications without overlap or out-of-range indexes")
        classified.update(boundaries)
    if classified != set(range(1, pdf_pages)):
        raise ValueError("Every page break must be explicitly classified exactly once")


def changes_for(row: dict) -> str:
    return LAYOUT_CHANGES if "page_break_joins" in row["partition"] else CHANGES


def manifest(root: Path = ROOT) -> dict:
    value = json.loads((root / MANIFEST_PATH).read_bytes())
    if (value.get("schema_version") != 1 or value.get("license") != WEBSITE_LICENSE
            or value.get("conditions") != CONDITIONS
            or value.get("distribution") != WEBSITE_DISTRIBUTION
            or value.get("permission", {}).get("evidence") != "OWNER_SUPPLIED_PERMISSION_AND_REPORTED_CONFIRMATION"
            or value["permission"].get("website") != "https://freebuddhism.org"
            or value["permission"].get("confirmation_reported") is not True):
        raise ValueError("Website edition needs the recorded permission and every condition")
    seen = set()
    for row in value["records"]:
        permitted = {"canonical_id", "collection", "title", "translator", "version", "source_url",
                     "source_sha256", "copyright", "pdf_pages", "raw_text_sha256", "body_sha256",
                     "text_sha256", "partition", "identity_review", "processing_review_entry_id", "completeness_status"}
        if set(row) != permitted:
            raise ValueError("Website source metadata contains unexpected or missing fields")
        key = (row["canonical_id"], row["version"])
        if key in seen or row.get("translator") != "Bhikkhu Candana":
            raise ValueError("Duplicate or unreviewed website edition")
        seen.add(key)
        if (not re.fullmatch(r"(?:AN|SN) \d+\.\d+|(?:DN|MN) \d+|(?:Ud|Snp|Thag) \d+\.\d+", row["canonical_id"])
                or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", row["version"])
                or not re.fullmatch(r"[a-z0-9-]+(?:/[a-z0-9-]+)*", row["collection"])
                or row.get("completeness_status") != "UNKNOWN"
                or row["identity_review"].get("review_kind") != "CONTENT_IDENTITY_REVIEW"):
            raise ValueError("Unreviewed website edition identity/scope")
        if checked_url(row["source_url"]) != row["source_url"]:
            raise ValueError("Use the exact approved original PDF URL")
        _validate_partition(row["partition"], row["pdf_pages"])
        for digest in (row["source_sha256"], row["raw_text_sha256"], row["body_sha256"],
                       row["text_sha256"], row["partition"]["header_sha256"], row["partition"]["raw_body_sha256"]):
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("Website inputs/outputs need exact hashes")
        for field in ("body", "text", "original_notice", "private_correspondence", "local_path"):
            if field in row:
                raise ValueError("Website manifest must not contain private inputs or translation bodies")
        review = row["identity_review"]
        canonical = safe_relative(root, review["canonical_text_path"])
        raw = canonical.read_bytes()
        if (sha(raw) != review["canonical_text_sha256"]
                or not raw.decode().splitlines()[0].startswith(row["canonical_id"] + " - ")):
            raise ValueError("Website identity comparison changed or names a different discourse")
    return value


def public_text_path(row: dict) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", row["canonical_id"].lower()).strip("-")
    return f"theravada/tipitaka/translations/en/candana-website/{slug}-{row['version']}.txt"


def reflow_body(source: str, recipe: dict, pdf_pages: int) -> str:
    """Reflow reviewed prose only; boundary 1 is the break after source page 1.

    The recipe is the complete partition metadata. Presence of page_break_joins,
    even an empty list, selects explicit layout review. Callers must still verify
    the pinned source/header/output hashes and independent extractor agreement.
    """
    _validate_partition(recipe, pdf_pages)
    pages = pages_of(source)
    if len(pages) != pdf_pages or re.search(r"\w-\n[ \t]*\w", source):
        raise ValueError("Unreviewed page-break or hyphen-wrap layout")
    if "page_break_joins" in recipe:
        joins = set(recipe["page_break_joins"])
        parts = []
        for index, page in enumerate(pages):
            if index:
                parts.append("\n" if index in joins else "\n\n")
            parts.append(page.strip())
        layout = "".join(parts)
        if re.search(r"\w-\n[ \t]*\w", layout):
            raise ValueError("Unreviewed hyphen-wrap layout across a page break")
    else:
        # Preserve the original recipe's page-margin handling and output bytes.
        layout = "\n\n".join(pages).strip()
    paragraphs = re.split(r"\n[ \t]*\n+", layout)
    body = "\n\n".join(" ".join(p.split()) for p in paragraphs if p.strip()) + "\n"
    if source.split() != body.split():
        raise ValueError("Reader reflow changed words/order")
    return body


def partition(raw: str, row: dict) -> tuple[str, str]:
    recipe = row["partition"]
    _validate_partition(recipe, row["pdf_pages"])
    offset = recipe["header_characters"]
    if type(offset) is not int or not 0 < offset < len(raw):
        raise ValueError("Invalid source header/body boundary")
    header, source = raw[:offset], raw[offset:]
    if "page_break_joins" in recipe:
        reference_matches = sum(line.strip() == row["canonical_id"] for line in header.splitlines()) == 1
    else:
        reference_matches = raw.splitlines()[0].strip() == row["canonical_id"]
    if (sha(header.encode()) != recipe["header_sha256"]
            or sha(source.encode()) != recipe["raw_body_sha256"]
            or not reference_matches
            or row["copyright"] not in header
            or "Translated by Bhikkhu Candana" not in " ".join(header.split())):
        raise ValueError("Source identity, notice or exact reader boundary changed")
    body = reflow_body(source, recipe, row["pdf_pages"])
    if raw.split() != (header + "\n" + body).split() or sha(body.encode()) != row["body_sha256"]:
        raise ValueError("Reader reflow changed words/order or differs from reviewed output")
    return header, body


def attributed_text(row: dict, header: str, body: str) -> str:
    return "\n".join([
        f"{row['canonical_id']} - {row['title']}", "Translated by Bhikkhu Candana",
        "Source: " + row["source_url"], "License: " + WEBSITE_LICENSE,
        "License URL: " + RIGHTS_URL, "Copyright: " + row["copyright"],
        "License notice: " + NOTICE,
        "Original document heading: " + " ".join(header.split()),
        "Distribution: Website-only edition; excluded from combined readers and site/source archives in this build.",
        "Changes: " + changes_for(row), "Completeness: UNKNOWN. " + SCOPE,
    ]) + "\n\n" + body


def checked_input(row: dict, root: Path = ROOT) -> tuple[str, str, str]:
    pdf = safe_relative(root, CACHE_PATH + "/" + row["source_sha256"] + ".pdf")
    if not pdf.is_file():
        raise ValueError("Website-only PDF input is missing; explicitly stage the pinned source before enabling these editions")
    original = pdf.read_bytes()
    if not original.startswith(b"%PDF-") or sha(original) != row["source_sha256"]:
        raise ValueError("Website-only source PDF changed")
    raw = subprocess.check_output(["pdftotext", "-layout", str(pdf), "-"], timeout=60).decode("utf-8")
    alternate = subprocess.check_output(["mutool", "draw", "-F", "txt", "-o", "-", str(pdf)],
                                         stderr=subprocess.PIPE, timeout=60).decode("utf-8")
    if (sha(raw.encode()) != row["raw_text_sha256"] or len(pages_of(raw)) != row["pdf_pages"]
            or len(pages_of(alternate)) != row["pdf_pages"]
            or any(a.split() != b.split() for a, b in zip(pages_of(raw), pages_of(alternate)))):
        raise ValueError("PDF text layers/word boundaries differ from the reviewed source")
    header, body = partition(raw, row)
    text = attributed_text(row, header, body)
    if sha(text.encode()) != row["text_sha256"]:
        raise ValueError("Website download metadata or body differs from reviewed output")
    return raw, header, text


def stage(pdf: Path, root: Path = ROOT) -> list[str]:
    if pdf.is_symlink() or not pdf.is_file() or pdf.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Use a regular source PDF within the collector's 64 MiB bound")
    data = pdf.read_bytes()
    matched = [row for row in manifest(root)["records"] if row["source_sha256"] == sha(data)]
    if not matched:
        raise ValueError("PDF is not in the reviewed website manifest")
    target = safe_relative(root, CACHE_PATH + "/" + sha(data) + ".pdf")
    if target.exists() and target.read_bytes() != data:
        raise ValueError("Refusing to replace changed website input")
    if not target.exists():
        write_file(target, data)
    for row in matched:
        checked_input(row, root)
    return [row["canonical_id"] for row in matched]


def collect_records(output_root: Path, root: Path = ROOT) -> list[dict]:
    if __package__:
        from .build_eligible_readers import parse_source_text, sutta_output_paths, route_for, COLLECTION_TITLES
    else:
        from build_eligible_readers import parse_source_text, sutta_output_paths, route_for, COLLECTION_TITLES
    output_root = Path(output_root).absolute()
    if not output_root.resolve().is_relative_to((root / "build").resolve()):
        raise ValueError("Website-only readers must be generated below build/, never into the public source tree")
    safe_relative(root, output_root.relative_to(root).as_posix())
    value = manifest(root)
    records = []
    for item in value["records"]:
        safe_relative(output_root, public_text_path(item))
        raw, header, text = checked_input(item, root)
        raw_path = CACHE_PATH + "/" + item["raw_text_sha256"] + ".txt"
        write_file(safe_relative(root, raw_path), raw.encode())
        review = dict(item["identity_review"], source_snapshot=raw_path,
                      source_sha256=item["raw_text_sha256"], canonical_id=item["canonical_id"])
        verify_identity_review(review, root)
        text_path = safe_relative(root, CACHE_PATH + "/" + item["text_sha256"] + ".txt")
        if text_path.exists() and text_path.read_bytes() != text.encode():
            raise ValueError("Staged website download changed")
        if not text_path.exists():
            write_file(text_path, text.encode())
        row = {**item, "collection_path": item["collection"], "version_slug": item["version"],
               "version_label": "Bhikkhu Candana translation", "txt_path": public_text_path(item)}
        folder, base, output_html = sutta_output_paths(row, output_root)
        site_path = root / output_html.relative_to(output_root)
        entry = root / "theravada/tipitaka/sutta" / item["collection"] / folder.name / "index.html"
        _source, body, notes, translator, body_hash = parse_source_text(text_path, row, WEBSITE_LICENSE)
        records.append({
            "kind": "sutta", "manifest": value, "website_record": item, "row": row,
            "canonical_id": item["canonical_id"], "collection": item["collection"],
            "collection_label": COLLECTION_TITLES[item["collection"]], "collection_page": entry.parent.parent / "index.html",
            "folder": folder, "base_name": base, "html_path": output_html, "site_path": site_path,
            "output_root": output_root, "pdf_path": folder / (base + "-reader.pdf"),
            "entry_page": entry, "entry_href": route_for(entry, site_path), "version": item["version"],
            "preference_id": "candana", "version_label": row["version_label"], "translator": translator,
            "title": item["title"], "source_url": item["source_url"], "source_repository": "",
            "source_revision": item["source_sha256"], "upstream_file": "", "license": WEBSITE_LICENSE,
            "license_url": RIGHTS_URL, "copyright": item["copyright"], "license_notice": NOTICE,
            "changes": changes_for(item), "conditions": CONDITIONS, "distribution": WEBSITE_DISTRIBUTION,
            "completeness_status": "UNKNOWN", "completeness_scope": SCOPE,
            "source_label": "Mind Released · original Candana PDF", "text_path": text_path,
            "site_text_path": root / public_text_path(item), "source_sha256": sha(text.encode()),
            "body": body, "body_sha256": body_hash, "metadata_notes": notes,
        })
    return records


def verify_record(record: dict, root: Path = ROOT) -> bool:
    item = record.get("website_record")
    if item is None or item not in manifest(root)["records"]:
        return False
    safe_relative(Path(record.get("output_root", root)), public_text_path(item))
    text_path = safe_relative(root, CACHE_PATH + "/" + item["text_sha256"] + ".txt")
    return (Path(record.get("output_root", root)).resolve().is_relative_to((root / "build").resolve())
            and record.get("license") == WEBSITE_LICENSE and record.get("canonical_id") == item["canonical_id"]
            and record.get("version") == item["version"] and record.get("source_url") == item["source_url"]
            and record.get("body_sha256") == item["body_sha256"] and record.get("source_sha256") == item["text_sha256"]
            and record.get("distribution") == WEBSITE_DISTRIBUTION and record.get("conditions") == CONDITIONS
            and record.get("changes") == changes_for(item)
            and record.get("license_notice") == NOTICE and record.get("license_url") == RIGHTS_URL
            and record.get("title") == item["title"] and record.get("copyright") == item["copyright"]
            and isinstance(record.get("body"), str) and sha(record["body"].encode()) == item["body_sha256"]
            and record.get("site_text_path") == root / public_text_path(item)
            and Path(record["text_path"]) == text_path and text_path.is_file()
            and sha(text_path.read_bytes()) == item["text_sha256"])


def verify_public_boundary(root: Path = ROOT) -> None:
    """The public source carries metadata only, never website-only text payloads."""
    value = manifest(root)
    directory = root / "theravada/tipitaka/translations/en/candana-website"
    if directory.exists():
        raise ValueError("Website-only payloads must not enter the public source tree")
    for row in value["records"]:
        if (root / public_text_path(row)).exists():
            raise ValueError("Website-only text is not a public repository source")


def write_permission_page(destination: Path, records: list[dict]) -> set[Path]:
    selected = [row for row in records if row.get("website_record")]
    if not selected:
        return set()
    path = destination / RIGHTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Candana website permission</title></head><body><h1>Candana website permission</h1>'
            '<p>The website owner supplied permission to republish Bhikkhu Candana’s sutta translations on freebuddhism.org '
            'and reported sending the required confirmation. Private correspondence is not reproduced here.</p><ul>'
            + ''.join('<li>' + html.escape(condition) + '</li>' for condition in CONDITIONS)
            + '</ul><p>This is not CC0 or a general third-party republication grant. These editions are excluded from '
            'combined readers and collection/source archives in this build. Earlier exact-book grants remain separate.</p>'
            '<p>Original PDFs and source hashes are linked from the individual readers. '
            'Processing and discourse-identity checks do not certify translation accuracy or a complete human proofread.</p>'
            '<p><a href="tipitaka.html">Buddhist Texts</a></p></body></html>\n')
    path.write_text(body, encoding="utf-8")
    return {path}


def check_site(site: Path, root: Path = ROOT) -> dict:
    """Check actual reader/download bytes and every built collection archive."""
    if __package__:
        from .render_cc0_reader import ReaderParser, verify_pdf_body
    else:
        from render_cc0_reader import ReaderParser, verify_pdf_body
    records = collect_records(root / "build/candana-website-check", root)
    excluded = set()
    for record in records:
        item = record["website_record"]
        relative = record["html_path"].relative_to(record["output_root"])
        page = site / relative
        parser = ReaderParser()
        document = page.read_text(encoding="utf-8")
        parser.feed(document)
        if "".join(parser.source_parts) != record["body"]:
            raise ValueError("Published website reader differs from its reviewed source")
        download = site / public_text_path(item)
        if sha(download.read_bytes()) != item["text_sha256"]:
            raise ValueError("Website TXT download differs from its reviewed notice/body")
        pdf = page.with_name(record["pdf_path"].name)
        verify_pdf_body(pdf, record["body"])
        pdf_text = subprocess.check_output(["pdftotext", "-layout", str(pdf), "-"]).decode()
        if (item["copyright"] not in html.unescape(document)
                or " ".join(item["copyright"].split()) not in " ".join(pdf_text.split())
                or item["source_url"] not in parser.links or RIGHTS_URL not in parser.links):
            raise ValueError("Website reader lost its copyright, original source or permission link")
        for condition in CONDITIONS:
            if condition not in html.unescape(document) or " ".join(condition.split()) not in " ".join(pdf_text.split()):
                raise ValueError("Website HTML/PDF download lost a permission condition")
        for target in (relative, Path(public_text_path(item)), pdf.relative_to(site)):
            excluded.add(target.relative_to("theravada/tipitaka").as_posix())
        index = json.loads((site / "theravada/tipitaka/site/reading-index.json").read_bytes())
        if any(row["canonical_id"] == item["canonical_id"] and any(e["id"] == item["version"] for e in row["editions"])
               for row in index["texts"]):
            raise ValueError("Website-only edition entered the combined reader")
    archives = list((site / "theravada/tipitaka/downloads").glob("*.zip"))
    if not archives:
        raise ValueError("Cannot check website archive exclusions without built archives")
    for archive_path in archives:
        with zipfile.ZipFile(archive_path) as archive:
            if any(name == blocked or name.endswith("/" + blocked) for name in archive.namelist() for blocked in excluded):
                raise ValueError("Website-only payload entered a collection archive")
    notice = (site / RIGHTS_PATH).read_text(encoding="utf-8")
    if any(condition not in notice for condition in CONDITIONS):
        raise ValueError("Website permission page is incomplete")
    release = json.loads((site / "release.json").read_bytes())
    expected = [{key: row["website_record"][key] for key in
                 ("canonical_id", "source_sha256", "body_sha256", "text_sha256", "processing_review_entry_id")}
                for row in records]
    if release.get("website_only_editions") != expected:
        raise ValueError("Website release does not identify its exact optional inputs")
    return {"website_editions": len(records), "archives_checked": len(archives),
            "body_download_notice_checks": "PASS", "combined_reader_exclusion": "PASS",
            "scope": "Built website-only editions; not human proofreading or deployment evidence"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--stage-pdf", type=Path)
    action.add_argument("--check-site", type=Path)
    args = parser.parse_args()
    if args.stage_pdf:
        print(json.dumps({"staged": stage(args.stage_pdf), "network_requests": 0}))
    else:
        print(json.dumps(check_site(args.check_site)))


if __name__ == "__main__":
    main()
