#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Plan/apply a recoverable identity correction and publisher-reference separation.

No source is downloaded. Original publisher snapshots never change. Title-only
remappings require a pinned content review or are held outside publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

from import_licensed_batches import (
    attributed_text, reassess, update_metadata, write_coverage, write_held_sources, write_json,
)
from prepare_ati_licensed import COMPARISON, region, render, split_publisher_references, check_characters
from publication_rights import (
    ROOT, MANIFEST, IDENTITY_REVIEWS, checked_path, sha256, verify_identity_review, verified_manifest,
    identity_visible_text,
)

TITLE_ONLY = "unique pinned Pali title within publisher chapter; numbering corrected"
AUDIT = ROOT / "metadata/reports/licensed-identity-corrections-2026-11-11.json"
PUBLIC_REVIEW_FIELDS = {"review_id", "status", "source_url", "source_sha256", "source_snapshot",
                        "publisher_id", "canonical_id", "canonical_text_path", "canonical_text_sha256",
                        "source_anchors", "canonical_anchors", "review_basis"}


def visible_text(path: Path) -> str:
    return identity_visible_text(path)


def content_intervals(path: Path, anchors: list[str]) -> list[dict]:
    text = visible_text(path)
    intervals = []
    for raw in anchors:
        anchor = " ".join(raw.split())
        start = text.find(anchor)
        if len(anchor) < 16 or start < 0:
            raise ValueError("Review content anchor is absent: " + str(path) + ": " + anchor)
        intervals.append({"start": start, "end": start + len(anchor),
                          "sha256": hashlib.sha256(anchor.encode("utf-8")).hexdigest()})
    return intervals


def prepare_reviews(paths: list[Path]) -> dict:
    records = {}
    existing = ROOT / IDENTITY_REVIEWS
    if existing.exists():
        for original in json.loads(existing.read_text())["records"]:
            row = {key: value for key, value in original.items() if key in PUBLIC_REVIEW_FIELDS}
            records[(row["source_url"], row["source_sha256"])] = row
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else data["records"]
        for original in rows:
            if original.get("status") != "VERIFIED":
                continue
            row = {key: value for key, value in original.items() if key in PUBLIC_REVIEW_FIELDS}
            for input_field, anchor_field in (("source_snapshot", "source_anchors"),
                                               ("canonical_text_path", "canonical_anchors")):
                if row[anchor_field] and isinstance(row[anchor_field][0], str):
                    row[anchor_field] = content_intervals(checked_path(ROOT, row[input_field]), row[anchor_field])
            verify_identity_review(row)
            key = (row["source_url"], row["source_sha256"])
            if key in records and records[key] != row:
                raise ValueError("Conflicting reviewed identity decisions: " + row["source_url"])
            records[key] = row
    return {"schema_version": 1, "date": "2026-11-11",
            "scope": "Explicit discourse-content comparisons for the previously title-remapped editions. Intervals pin comparison evidence without quoting licensed passages in project metadata.",
            "records": sorted(records.values(), key=lambda row: row["source_url"])}


def plan(review_data: dict) -> tuple[dict, dict, dict[str, bytes], list[dict]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    reviews = {(row["source_url"], row["source_sha256"]): row for row in review_data["records"]}
    previous_audit = json.loads(AUDIT.read_text(encoding="utf-8")) if AUDIT.exists() else {}
    records, texts = [], {}
    changes = list(previous_audit.get("corrections", []))
    held = list(previous_audit.get("held", []))
    held_sources = {(r["source_url"], r["source_sha256"]): r
                    for r in manifest.get("held_source_records", [])}
    def retain_source_rights(row: dict) -> None:
        fields = ("source_url", "source_snapshot", "source_sha256", "source_repository", "source_revision",
                  "license", "license_url", "copyright", "license_notice", "conditions", "explicit_grant")
        entry = {field: row[field] for field in fields if field in row}
        entry["status"] = "SOURCE_RIGHTS_VERIFIED_READER_SCOPE_HELD"
        held_sources[(row["source_url"], row["source_sha256"])] = entry
    for original in manifest["records"]:
        row = dict(original)
        source_path, old_path = checked_path(ROOT, row["source_snapshot"]), checked_path(ROOT, row["local_path"])
        if sha256(source_path) != row["source_sha256"] or sha256(old_path) != row["sha256"]:
            raise ValueError("Correction input changed: " + row["source_url"])
        old_text = old_path.read_text(encoding="utf-8")
        old_body = old_text.split("\n\n", 1)[1]
        if hashlib.sha256(old_body.encode()).hexdigest() != row["body_sha256"]:
            raise ValueError("Correction body changed: " + row["local_path"])
        mapping = row.get("mapping_evidence", {})
        if mapping.get("method") == TITLE_ONLY:
            review = reviews.get((row["source_url"], row["source_sha256"]))
            if not review:
                retain_source_rights(original)
                held.append({"source": "Discourse identity review", "title": row["title"],
                             "original": row["source_url"], "source_sha256": row["source_sha256"],
                             "publisher_id": mapping["publisher_id"], "previous_canonical_id": row["canonical_id"],
                             "questions": ["Previous title-only association withdrawn. Distinctive discourse contents must establish the correct text reference before republication."]})
                changes.append({"source_url": row["source_url"], "version": row["version"],
                                "previous_canonical_id": row["canonical_id"], "publisher_id": mapping["publisher_id"],
                                "action": "HELD_FOR_IDENTITY_REVIEW"})
                continue
            if review["publisher_id"] != mapping["publisher_id"]:
                raise ValueError("Review differs from original publisher ID")
            row["canonical_id"] = review["canonical_id"]
            slug = re.sub(r"[^a-z0-9]+", "-", row["canonical_id"].lower()).strip("-")
            row["local_path"] = str(Path(row["local_path"]).with_name(slug + ".txt"))
            row["mapping_evidence"] = {"method": "Content-verified edition concordance",
                                       "review_id": review["review_id"], "publisher_id": review["publisher_id"],
                                       "publisher_alternate_id": mapping.get("publisher_alternate_id", "")}
            changes.append({"source_url": row["source_url"], "version": row["version"],
                            "previous_canonical_id": original["canonical_id"], "publisher_id": review["publisher_id"],
                            "canonical_id": row["canonical_id"], "review_id": review["review_id"],
                            "action": "CORRECTED" if row["canonical_id"] != original["canonical_id"] else "CONTENT_CONFIRMED"})
            row["review_flags"] = [flag for flag in row.get("review_flags", [])
                                   if flag != "Publisher numbering differs; see mapping_evidence."]
            if review["publisher_id"] != row["canonical_id"]:
                row["review_flags"].append("Publisher numbering differs; a pinned discourse-content comparison establishes this association.")
        if mapping:
            source = source_path.read_bytes().decode("utf-8")
            fragment_id = "COPYRIGHTED_TEXT_CHUNK" if "accesstoinsight.org/" in row["source_url"] else "sutta"
            fragment = region(source, fragment_id)
            try:
                body, references = split_publisher_references(fragment)
            except ValueError as error:
                retain_source_rights(original)
                held.append({"source": "Publisher source-scope review", "title": row["title"],
                             "original": row["source_url"], "source_sha256": row["source_sha256"],
                             "publisher_id": mapping.get("publisher_id", row["canonical_id"]),
                             "previous_canonical_id": original["canonical_id"],
                             "questions": [str(error), "Keep the complete original outside reader publication until its discourse and editorial boundaries are reviewed."]})
                if changes and changes[-1]["source_url"] == row["source_url"]:
                    changes[-1]["action"] = "IDENTITY_VERIFIED_BUT_SOURCE_HELD"
                continue
            if old_body not in (render(fragment), body):
                raise ValueError("Stored body differs from its complete publisher source: " + row["source_url"])
            check_characters(fragment, body + references)
            if references:
                row.update(publisher_references=references,
                           publisher_references_sha256=hashlib.sha256(references.encode()).hexdigest())
            row.update(body_sha256=hashlib.sha256(body.encode()).hexdigest(), source_partition_version=2,
                       source_comparison_method=COMPARISON)
        else:
            body = old_body
        text = attributed_text(row, body).encode("utf-8")
        row["sha256"] = hashlib.sha256(text).hexdigest()
        key = (row["collection"], row["canonical_id"], row["version"])
        if any((r["collection"], r["canonical_id"], r["version"]) == key for r in records):
            raise ValueError("Corrected editions collide; disposition required: " + str(key))
        if row["local_path"] in texts:
            raise ValueError("Corrected output paths collide")
        texts[row["local_path"]] = text
        records.append(row)
    manifest.update(count=len(records), records=records,
                    held_source_records=sorted(held_sources.values(), key=lambda row: row["source_url"]))
    report = {"date": "2026-11-11", "prior_editions": len(records) + len(held), "editions": len(records),
              "title_only_associations_reviewed": len(changes), "corrections": changes,
              "held": held, "publisher_reference_editions": sum(bool(r.get("publisher_references")) for r in records),
              "limits": "Full-source character preservation and discourse identity are separate checks. No translation wording or repeated passage is invented."}
    return manifest, report, texts, json.loads(MANIFEST.read_text())["records"]


def apply(review_data: dict, manifest: dict, report: dict, texts: dict[str, bytes], originals: list[dict]) -> Path:
    original_paths = {row["local_path"]: row["sha256"] for row in originals}
    for relative in texts:
        path = checked_path(ROOT, relative)
        if path.exists() and relative not in original_paths:
            raise ValueError("Correction would overwrite an unrelated file: " + relative)
    backup = Path(tempfile.mkdtemp(prefix="licensed-identity-before-", dir=ROOT / "build"))
    metadata = [MANIFEST, ROOT / "metadata/eligible-texts.json", ROOT / "metadata/public-file-allowlist.json"]
    for path in metadata + [ROOT / relative for relative in original_paths]:
        target = backup / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for relative, data in texts.items():
        target = checked_path(ROOT, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    stale = set(original_paths) - set(texts)
    for relative in stale:
        # Exact per-edition targets, each retained in the backup above; never a directory.
        checked_path(ROOT, relative).unlink()
    write_json(ROOT / IDENTITY_REVIEWS, review_data)
    write_json(MANIFEST, manifest)
    allowlist_path = ROOT / "metadata/public-file-allowlist.json"
    allowlist = json.loads(allowlist_path.read_text())
    allowlist["files"] = [entry for entry in allowlist["files"] if entry["path"] not in stale]
    write_json(allowlist_path, allowlist)
    update_metadata(manifest)
    verified_manifest()
    write_json(AUDIT, report)
    reassess()
    write_coverage()
    write_held_sources()
    return backup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", action="append", type=Path, default=[])
    parser.add_argument("--apply", action="store_true", help="Write the reviewed plan after retaining original files")
    args = parser.parse_args()
    reviews = prepare_reviews(args.review)
    manifest, report, texts, originals = plan(reviews)
    if args.apply:
        backup = apply(reviews, manifest, report, texts, originals)
        print("Original editions retained at " + str(backup))
    print(json.dumps({key: value for key, value in report.items() if key not in {"corrections", "held"}}, sort_keys=True))
    print("Held associations: " + str(len(report["held"])))
    for row in report["held"]:
        if row["source"] == "Publisher source-scope review":
            print("Source-scope hold: " + row["original"] + ": " + row["questions"][0])


if __name__ == "__main__":
    main()
