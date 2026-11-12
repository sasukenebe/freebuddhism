"""Edition-specific redistribution rules approved on 2026-11-11 (code: 0BSD)."""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "metadata/source-manifests/licensed-collections.json"
IDENTITY_REVIEWS = Path("metadata/source-manifests/licensed-identity-review-2026-11-11.json")
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


def identity_visible_text(path: Path) -> str:
    """Exact decoded text nodes for HTML, raw characters for the canonical TXT."""
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".source":
        class Text(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.parts = []
                self.hidden = 0
            def handle_starttag(self, tag, attrs):
                if tag in {"script", "style"}: self.hidden += 1
            def handle_endtag(self, tag):
                if tag in {"script", "style"}: self.hidden -= 1
            def handle_data(self, value):
                if not self.hidden: self.parts.append(value)
        parser = Text()
        parser.feed(raw)
        parser.close()
        raw = "".join(parser.parts)
    return " ".join(raw.split())


def identity_for_source(source_url: str, source_hash: str, root: Path = ROOT) -> dict | None:
    """Only a pinned, explicit content review may override source numbering/title."""
    path = root / IDENTITY_REVIEWS
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    matches = [row for row in data["records"]
               if row["source_url"] == source_url and row["source_sha256"] == source_hash]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("Duplicate source identity review")
    review = matches[0]
    verify_identity_review(review, root)
    return review


def verify_identity_review(review: dict, root: Path = ROOT) -> None:
    """Pin comparison inputs and nonquoted content intervals for a reviewed decision."""
    if review.get("status") != "VERIFIED":
        raise ValueError("The source identity review is unresolved")
    for field, hash_field, anchors_field in (
            ("source_snapshot", "source_sha256", "source_anchors"),
            ("canonical_text_path", "canonical_text_sha256", "canonical_anchors")):
        target = checked_path(root, review[field])
        if not target.is_file() or sha256(target) != review[hash_field]:
            raise ValueError("Identity review input changed: " + review[field])
        visible = identity_visible_text(target)
        if field == "canonical_text_path":
            first_line = target.read_text(encoding="utf-8").splitlines()[0]
            if not first_line.startswith(review["canonical_id"] + " - "):
                raise ValueError("Identity review canonical ID differs from comparison text")
        anchors = review.get(anchors_field, [])
        if len(anchors) < 2:
            raise ValueError("Identity review content evidence is missing or changed")
        intervals = set()
        for anchor in anchors:
            start, end = anchor["start"], anchor["end"]
            if (not isinstance(start, int) or not isinstance(end, int)
                    or not 0 <= start < end <= len(visible) or end - start < 16
                    or hashlib.sha256(visible[start:end].encode("utf-8")).hexdigest() != anchor["sha256"]):
                raise ValueError("Identity review content interval changed")
            intervals.add((start, end))
        if len(intervals) < 2:
            raise ValueError("Identity review needs distinct content intervals")
    if not review.get("review_basis", "").strip() or not review.get("review_id", "").strip():
        raise ValueError("Identity review needs its comparison basis and identifier")


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
        references = record.get("publisher_references", "")
        if references:
            if (hashlib.sha256(references.encode("utf-8")).hexdigest()
                    != record.get("publisher_references_sha256")
                    or "Publisher references (not part of the sutta): " + " ".join(references.split()) not in header):
                raise ValueError(f"Publisher references are missing or changed: {key}")
            if references.strip() in body:
                raise ValueError(f"Publisher references must not be part of the sutta body: {key}")
        mapping = record.get("mapping_evidence", {})
        if mapping.get("method") == "unique pinned Pali title within publisher chapter; numbering corrected":
            raise ValueError(f"Title-only discourse remapping is not publishable: {key}")
        if mapping.get("method") == "Content-verified edition concordance":
            review = identity_for_source(record["source_url"], record["source_sha256"], root)
            if (not review or review["canonical_id"] != record["canonical_id"]
                    or review["publisher_id"] != mapping.get("publisher_id")
                    or review["review_id"] != mapping.get("review_id")):
                raise ValueError(f"Published edition does not match its content review: {key}")
    if manifest.get("count", len(identifiers)) != len(identifiers):
        raise ValueError("Licensed-collection manifest count differs from its records")
    for held in manifest.get("held_source_records", []):
        source = checked_path(root, held["source_snapshot"])
        name = held["license"]
        if (not source.is_file() or sha256(source) != held["source_sha256"]
                or urlsplit(held["source_url"]).scheme != "https"
                or held.get("status") != "SOURCE_RIGHTS_VERIFIED_READER_SCOPE_HELD"
                or not held.get("copyright") or not held.get("license_notice")):
            raise ValueError("Held publisher-source rights evidence is missing or changed")
        if name == FREE_GRANT:
            if not held.get("explicit_grant") or not held.get("conditions"):
                raise ValueError("Held publisher source lacks its distribution grant")
        elif (canonical_license(name) != name or held["license_url"] != license_url(name)
              or held["conditions"] != license_conditions(name)):
            raise ValueError("Held publisher-source license changed")
    return manifest
