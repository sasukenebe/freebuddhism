"""Explicit rights checks for project-authored HTML pages copied into the site."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
SITE_MANIFEST = Path("metadata/site-content.json")
SITE_SCOPE = "CC0-1.0 project-authored website content"
NAVIGATION_SCOPE = "CC0-1.0 project navigation and availability metadata"
SITE_RIGHTS_BASIS = "Original project-authored site content released under CC0-1.0 by the repository owner."
NAVIGATION_RIGHTS_BASIS = (
    "Owner-authored navigation and availability metadata; each page is checked against the strict route-content policy."
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _site_content_paths(root: Path) -> set[str]:
    site_root = root / "theravada/tipitaka/site"
    paths = set()
    for directory, subdirectories, filenames in os.walk(site_root):
        subdirectories.sort()
        for filename in filenames:
            path = Path(directory) / filename
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Website content must be a regular file: {path.relative_to(root)}")
            paths.add(path.relative_to(root).as_posix())
    entry = root / "site-entry/index.html"
    if entry.is_symlink() or not entry.is_file():
        raise ValueError("Required project site entry is missing or unsafe: site-entry/index.html")
    paths.add(entry.relative_to(root).as_posix())
    return paths


def validate_site_content_manifest(root: Path = ROOT) -> dict[str, dict]:
    data = json.loads((root / SITE_MANIFEST).read_text(encoding="utf-8"))
    if set(data) != {"schema_version", "scope", "files"} or data.get("schema_version") != 1:
        raise ValueError("Site-content manifest has an unknown schema")
    if data.get("scope") != "Only owner-approved project-authored pages with CC0-1.0 rights are included.":
        raise ValueError("Site-content manifest must state its owner-approved scope")
    listed = {}
    for entry in data.get("files", []):
        if set(entry) != {"path", "sha256", "license_scope", "rights_basis"}:
            raise ValueError("Site-content entries must be explicit path/hash/license/rights records")
        path_text = entry.get("path", "")
        relative = PurePosixPath(path_text)
        if relative.is_absolute() or ".." in relative.parts or not path_text:
            raise ValueError(f"Unsafe path in site-content manifest: {path_text}")
        if path_text not in {"site-entry/index.html"} and not path_text.startswith("theravada/tipitaka/site/"):
            raise ValueError(f"Unapproved site-content path: {path_text}")
        if (entry.get("license_scope") != SITE_SCOPE
                or entry.get("rights_basis") != SITE_RIGHTS_BASIS):
            raise ValueError(f"Site page lacks explicit CC0 rights basis: {path_text}")
        if path_text in listed:
            raise ValueError(f"Duplicate site-content path: {path_text}")
        path = root / path_text
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Site-content file is missing or unsafe: {path_text}")
        if sha256_file(path) != entry.get("sha256"):
            raise ValueError(f"Site-content checksum mismatch: {path_text}")
        listed[path_text] = entry
    actual = _site_content_paths(root)
    if set(listed) != actual:
        raise ValueError(
            "Site-content manifest mismatch: "
            f"unlisted={sorted(actual - set(listed))[:10]}, "
            f"missing={sorted(set(listed) - actual)[:10]}"
        )
    return listed


def require_allowlisted_page(root: Path, path_text: str, expected_scope: str) -> None:
    manifest_path = root / "metadata/public-file-allowlist.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = {row["path"]: row for row in manifest.get("files", [])}
    entry = entries.get(path_text)
    expected_basis = SITE_RIGHTS_BASIS if expected_scope == SITE_SCOPE else NAVIGATION_RIGHTS_BASIS
    if (not entry or entry.get("license_scope") != expected_scope
            or entry.get("rights_basis") != expected_basis):
        raise ValueError(f"Source HTML has no matching explicit rights entry: {path_text}")
    path = root / path_text
    if path.is_symlink() or not path.is_file() or sha256_file(path) != entry.get("sha256"):
        raise ValueError(f"Source HTML does not match its allowlisted checksum: {path_text}")
