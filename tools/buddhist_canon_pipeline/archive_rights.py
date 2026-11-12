# SPDX-License-Identifier: 0BSD
"""File-specific reuse metadata; never impose one archive-wide text license."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
import re
import subprocess
import zipfile

from distribution_policy import require_archive_permission

TERMS_NAME = "REUSE-TERMS.txt"
MANIFEST_NAME = "LICENSE-MANIFEST.json"
RESERVED_NAMES = {TERMS_NAME, MANIFEST_NAME}
TERMS = (
    "FILE-SPECIFIC REUSE TERMS\n\n"
    "This ZIP has no blanket text license. LICENSE-MANIFEST.json identifies each\n"
    "payload file, its SHA-256, source and applicable edition terms.\n"
    "Some editions require attribution, noncommercial use, share-alike, or free\n"
    "unaltered distribution. Apply only the conditions belonging to that file.\n"
    "Do not assume every file permits commercial reuse or modification.\n"
    "CC0/public-domain files do not acquire restrictions from neighboring works.\n"
    "Keep the original attribution, copyright, license and permission notices.\n"
)
CANDANA_LICENSE = "Candana — free distribution, unaltered contents"
CANDANA_CONDITIONS = ["Copies must be available free of charge", "Do not alter the contents"]
UNRESTRICTED_LICENSES = {"CC0-1.0", "Public Domain (original English edition, published 1895–1907)",
                         "Public domain in the United States"}


@lru_cache(maxsize=8)
def candana_permission_notice(path: Path, digest: str, pages: tuple[int, ...]) -> str:
    """Carry the complete notice from the pinned book, not a paraphrased grant."""
    from import_candana import granted_notice
    if (path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest
            or not pages or any(type(page) is not int or page < 1 for page in pages)):
        raise ValueError("Candana archive notice needs its pinned original permission pages")
    notices = [subprocess.check_output(["pdftotext", "-layout", "-f", str(page), "-l", str(page),
                                        str(path), "-"], text=True) for page in pages]
    notice = "\n".join(notices)
    if not granted_notice(notice):
        raise ValueError("Candana original permission page lacks its complete grant")
    return notice


def edition_rights(record: dict) -> dict:
    require_archive_permission(record)
    fields = ("canonical_id", "version", "translator", "source_url", "source_revision",
              "license", "license_url", "copyright", "license_notice", "attribution_notice",
              "conditions", "changes", "completeness_status", "completeness_scope",
              "metadata_notes", "group_reference", "canonical_ids", "permission_pages")
    fields += ("title", "edition", "rights_note", "rights_evidence", "scope", "print_notice_note")
    result = {key: record[key] for key in fields if key in record}
    if not result.get("license") or not result.get("source_url"):
        raise ValueError("Archive payload needs its file-specific license and source")
    if result["license"] == CANDANA_LICENSE:
        if record.get("original_book_path"):
            path = Path(record["original_book_path"])
            book = next(book for book in record["manifest"]["books"]
                        if record["source_revision"] == book["sha256"])
            result["license_notice"] = candana_permission_notice(path, book["sha256"], tuple(book["permission_pages"]))
            result["conditions"] = book["conditions"]
            result["permission_pages"] = book["permission_pages"]
        from import_candana import granted_notice
        if not granted_notice(result.get("license_notice", "")) or result.get("conditions") != CANDANA_CONDITIONS:
            raise ValueError("Candana archive rights need the original notice and all conditions")
    if result["license"] not in UNRESTRICTED_LICENSES:
        if (not result.get("license_notice") or not result.get("license_url")
                or not isinstance(result.get("conditions"), list) or not result["conditions"]):
            raise ValueError("Restricted archive rights need a full notice, license URL and conditions")
    return result


def metadata_bytes(files: list[dict]) -> bytes:
    return (json.dumps({"schema_version": 1, "scope": "File-specific terms; no blanket text license",
                       "files": files}, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def verify_archive_rights(archive: zipfile.ZipFile, expected: list[dict]) -> None:
    """Verify metadata, every file hash and ZIP CRC independently after writing."""
    for row in expected:
        if not row.get("editions"):
            raise ValueError("Archive payload lacks explicit edition terms")
        for rights in row["editions"]:
            edition_rights(rights)
    manifest = json.loads(archive.read(MANIFEST_NAME))
    if manifest != json.loads(metadata_bytes(expected)) or archive.read(TERMS_NAME) != TERMS.encode():
        raise ValueError("Archive reuse metadata differs from verified edition terms")
    names = archive.namelist()
    if len(names) != len(set(names)) or set(names) != {r["path"] for r in expected} | RESERVED_NAMES:
        raise ValueError("Archive license manifest does not cover exactly its payload files")
    for row in expected:
        digest = hashlib.sha256()
        with archive.open(row["path"]) as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != row["sha256"]:
            raise ValueError("Archive payload hash differs from its license manifest: " + row["path"])


def archive_label(label: str, populated: bool) -> str:
    label = re.sub(r"(?: — no eligible files; notice only)+$", "", label)
    if not populated:
        for suffix in (" — complete English book", " — complete English text and scan (TXT + PDF)"):
            label = label.replace(suffix, "")
        label += " — no eligible files; notice only"
    return label


def write_release_metadata(destination: Path, source_root: Path, records: list[dict]) -> tuple[set[Path], str]:
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source_root, text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Release must identify a full source commit")
    modified = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"],
                                          cwd=source_root, text=True))
    payload = {"schema_version": 1, "source_commit": revision, "source_tree_modified": modified,
               "source_url": "https://github.com/sasukenebe/freebuddhism/commit/" + revision,
               "reader_versions": len(records), "rights_policy": "documented-redistribution-permission",
               "scope": "Release identity, not human proofreading approval"}
    website = [row["website_record"] for row in records if row.get("website_record")]
    if website:
        payload["website_only_editions"] = [{key: row[key] for key in
            ("canonical_id", "source_sha256", "body_sha256", "text_sha256", "processing_review_entry_id")}
            for row in website]
    path = destination / "release.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {path}, revision
