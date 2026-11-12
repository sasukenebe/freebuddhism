"""Edition-specific redistribution rules approved on 2026-11-11 (code: 0BSD)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "metadata/source-manifests/licensed-collections.json"
COMPLETENESS = {"COMPLETE", "ABBREVIATED", "PARTIAL", "UNKNOWN"}
FREE_GRANT = "Free redistribution with attribution and complete notice"
STANDARD_SCOPES = {f"CC-{family}-{version}" for family in ("BY", "BY-SA", "BY-NC", "BY-NC-SA")
                   for version in ("1.0", "2.0", "2.5", "3.0", "4.0")}
STANDARD_SCOPES.update(f"CC-{family}-3.0-US" for family in ("BY", "BY-SA", "BY-NC", "BY-NC-SA"))
SCOPE_BASIS = "The exact edition's source license, full notice and source/text SHA-256 values are verified in the licensed-collections manifest; its conditions remain attached to every copy."


def canonical_license(label: str) -> str | None:
    value = re.sub(r"[ _]+", "-", label.strip().upper())
    if value == "CC0-1.0":
        return value
    return value if value in STANDARD_SCOPES else None


def license_conditions(label: str) -> list[str]:
    license_name = canonical_license(label)
    if license_name is None:
        raise ValueError(f"License needs separate review: {label}")
    if license_name == "CC0-1.0":
        return []
    conditions = ["attribution", "copyright-and-license-notice", "source", "identify-changes"]
    if "-NC-" in license_name:
        conditions.append("noncommercial")
    if "-SA-" in license_name:
        conditions.append("share-alike")
    return conditions


def license_url(label: str) -> str:
    name = canonical_license(label)
    if name is None:
        raise ValueError(f"Unknown standard license: {label}")
    if name == "CC0-1.0":
        return "https://creativecommons.org/publicdomain/zero/1.0/"
    match = re.fullmatch(r"CC-(BY(?:-NC)?(?:-SA)?)-(\d\.\d)(?:-(US))?", name)
    if not match:
        raise ValueError(f"Unrecognized license components: {label}")
    suffix = "us/" if match[3] else ""
    return f"https://creativecommons.org/licenses/{match[1].lower()}/{match[2]}/{suffix}"


def checked_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError(f"Unsafe edition path: {value}")
    target = root / path
    if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Edition path escapes its source tree: {value}")
    return target


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_manifest(root: Path = ROOT, manifest_path: Path | None = None) -> dict:
    path = manifest_path or root / MANIFEST.relative_to(ROOT)
    if not path.exists():
        return {"schema_version": 1, "records": []}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("records"), list):
        raise ValueError("Unrecognized licensed-collection manifest")
    identifiers = set()
    for record in manifest["records"]:
        key = (record["collection"], record["canonical_id"], record["version"])
        if key in identifiers:
            raise ValueError(f"Duplicate licensed edition: {key}")
        identifiers.add(key)
        name = record["license"]
        if name == FREE_GRANT:
            if not record.get("explicit_grant") or not record.get("conditions"):
                raise ValueError("Explicit distribution grant and conditions are required")
        elif canonical_license(name) != name or record.get("license_url") != license_url(name):
            raise ValueError(f"Edition has an unsupported or mismatched license: {key}")
        if name != FREE_GRANT and record.get("conditions") != license_conditions(name):
            raise ValueError(f"Edition license conditions are incomplete: {key}")
        if record.get("completeness_status") not in COMPLETENESS:
            raise ValueError(f"Edition completeness is not classified: {key}")
        for field in ("translator", "source_url", "license_notice", "copyright", "completeness_scope"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f"Missing {field} for licensed edition: {key}")
        if urlsplit(record["source_url"]).scheme != "https":
            raise ValueError(f"Edition source must use HTTPS: {key}")
        for field, hash_field in (("local_path", "sha256"), ("source_snapshot", "source_sha256")):
            source = checked_path(root, record[field])
            if not source.is_file() or sha256(source) != record[hash_field]:
                raise ValueError(f"Licensed edition source changed: {record[field]}")
        text = checked_path(root, record["local_path"]).read_text(encoding="utf-8")
        header, body = text.split("\n\n", 1)
        if f"License: {name}" not in header.splitlines() or record["source_url"] not in header:
            raise ValueError(f"Edition source header is inconsistent: {key}")
        if record["license_notice"] not in text or record["copyright"] not in text:
            raise ValueError(f"Edition notices are absent from text download: {key}")
        if hashlib.sha256(body.encode()).hexdigest() != record["body_sha256"]:
            raise ValueError(f"Licensed translation body changed: {key}")
        if not body.strip() or record.get("source_comparison") != "PASS":
            raise ValueError(f"Complete source comparison is required: {key}")
        if any(unicodedata.category(c) == "Co" for c in body):
            raise ValueError(f"Unmapped private-use source font character: {key}")
    if manifest.get("count", len(identifiers)) != len(identifiers):
        raise ValueError("Licensed-collection manifest count differs from its records")
    return manifest
