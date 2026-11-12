#!/usr/bin/env python3
"""Import reviewed native-text batches under their own redistribution terms."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import unicodedata

from publication_rights import (
    ROOT, MANIFEST, FREE_GRANT, SCOPE_BASIS, COMPLETENESS,
    canonical_license, license_conditions, license_url, sha256, verified_manifest,
)

REPORT = ROOT / "metadata/reports/licensed-reassessment-2026-11-11.json"
CHANGES = "Presentation only: original HTML markup reflowed into plain text; wording, numbering and source repetitions retained. No repetitions expanded."


def attributed_text(row: dict, body: str) -> str:
    header = [f"{row['canonical_id']} - {row['title']}", f"Translated by {row['translator']}",
              f"Source: {row['source_url']}", f"License: {row['license']}",
              f"License URL: {row['license_url']}", f"Copyright: {row['copyright']}",
              f"License notice: {row['license_notice']}"]
    if row.get("attribution_notice"):
        header.append("Attribution: " + row["attribution_notice"])
    if row.get("publisher_references"):
        header.append("Publisher references (not part of the sutta): " + " ".join(row["publisher_references"].split()))
    header.extend(["Changes: " + CHANGES,
                   f"Completeness: {row['completeness_status']}. {row['completeness_scope']}"])
    return "\n".join(header) + "\n\n" + body


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def reassess() -> dict:
    historical = json.loads((ROOT / "metadata/reports/strict-license-classification-2026-10.json").read_text())["records"]
    released = {row.get("prior_record_id") for row in verified_manifest()["records"]}
    rows = []
    for original in historical:
        if original.get("rights_status") != "RIGHTS_RESTRICTED":
            continue
        label = original.get("declared_license", "")
        canonical = canonical_license(label)
        key = original["record_key"]
        decision = "IMPORTED" if key in released else "LICENSE_ACCEPTED_PENDING_SOURCE_CHECK" if canonical else "EXPLICIT_GRANT_REVIEW"
        if re.search(r"(?:^|[- ])ND(?:[- ]|$)", label.upper()):
            decision = "SEPARATE_NO_DERIVATIVES_REVIEW"
        rows.append({"record_id": key, "canonical_id": original["canonical_id"],
                     "source_group": original.get("source_group"), "source_url": original.get("source_url"),
                     "source_license": label, "license": canonical or label,
                     "conditions": license_conditions(canonical) if canonical else [],
                     "decision": decision})
    if len(rows) != 937:
        raise ValueError(f"Historical conditional-license batch changed: {len(rows)} entries")
    result = {"schema_version": 1, "policy_version": 4, "date": "2026-11-11",
              "scope": "All 937 historically excluded entries with stated conditional licenses or free-distribution terms; counts are editions/sections, not promises of complete books.",
              "count": len(rows), "decisions": dict(Counter(row["decision"] for row in rows)),
              "records": rows}
    write_json(REPORT, result)
    return result


def input_path(value: str, proposal_path: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    candidate = ROOT / path
    return candidate if candidate.is_file() else proposal_path.parent / path


def import_proposal(proposal_path: Path) -> int:
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    if not isinstance(proposal.get("records"), list):
        raise ValueError("A batch proposal needs records and retained source comparisons")
    for row in proposal["records"]:
        if row.get("mapping_evidence", {}).get("method") == "unique pinned Pali title within publisher chapter; numbering corrected":
            raise ValueError("Title-only discourse remapping cannot be imported; review actual contents")
        if (row.get("mapping_evidence") and "prepare_ati_licensed.py" in row.get("source_comparison_method", "")
                and row.get("source_partition_version") != 2):
            raise ValueError("Publisher reference boundaries require the corrected source-partition recipe")
    manifest = verified_manifest()
    by_key = {(row["collection"], row["canonical_id"], row["version"]): row for row in manifest["records"]}
    prior = json.loads((ROOT / "metadata/excluded-sources.json").read_text())["text_versions"]
    prior_keys = {(row["collection"], row["canonical_id"], canonical_license(row["license"]) or row["license"]): row["record_id"] for row in prior}
    added = 0
    for row in proposal["records"]:
        name = canonical_license(row["license"])
        explicit = row.get("explicit_grant", "")
        if name is None:
            if not explicit or row["license"] != FREE_GRANT:
                raise ValueError(f"Uncleared edition license: {row['license']}")
            name = FREE_GRANT
        if row.get("source_comparison") != "PASS":
            raise ValueError(f"No complete source comparison: {row['canonical_id']}")
        body_source = input_path(row["body_path"], proposal_path)
        body = body_source.read_text(encoding="utf-8")
        body_hash = hashlib.sha256(body.encode()).hexdigest()
        if body_hash != row["body_sha256"] or not body.strip():
            raise ValueError(f"Prepared body changed: {row['canonical_id']}")
        if any(unicodedata.category(character) == "Co" for character in body):
            # Preserve the draft, but do not publish an unidentified font code
            # as though it were a portable Unicode character.
            continue
        original = input_path(row["source_snapshot"], proposal_path)
        source_hash = sha256(original)
        if source_hash != row["source_sha256"]:
            raise ValueError(f"Original source changed: {row['canonical_id']}")
        collection = row["collection"]
        version = row.get("version_slug", row.get("version", ""))
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", version):
            raise ValueError(f"Invalid version identifier: {version}")
        if not re.fullmatch(r"[a-z0-9-]+(?:/[a-z0-9-]+)*", collection):
            raise ValueError(f"Invalid collection path: {collection}")
        key = (collection, row["canonical_id"], version)
        if key in by_key:
            if by_key[key]["body_sha256"] != body_hash or by_key[key]["source_sha256"] != source_hash:
                raise ValueError(f"Refusing to overwrite a different edition at {key}")
            if row.get("mapping_evidence"):
                by_key[key]["mapping_evidence"] = row["mapping_evidence"]
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", row["canonical_id"].lower()).strip("-")
        relative = f"theravada/tipitaka/translations/en/licensed/{version}/{slug}.txt"
        snapshot_relative = f"metadata/source-snapshots/licensed/{source_hash}.source"
        source_url = row["source_url"]
        notice = re.sub(r"\s+", " ", row["license_notice"]).strip()
        copyright_text = re.sub(r"\s+", " ", row["copyright"]).strip()
        status = row.get("completeness_status", "UNKNOWN")
        if status not in COMPLETENESS or not notice or not copyright_text:
            raise ValueError(f"Edition notices/completeness missing: {key}")
        scope = row["completeness_scope"]
        attribution = re.sub(r"\s+", " ", row.get("attribution_notice", "")).strip()
        text = attributed_text({**row, "license": name, "copyright": copyright_text,
                                "license_notice": notice, "attribution_notice": attribution,
                                "license_url": license_url(name) if name != FREE_GRANT else row["license_url"]}, body)
        target = ROOT / relative
        if target.exists():
            raise ValueError(f"Refusing an unmanifested existing text: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        snapshot = ROOT / snapshot_relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        if snapshot.exists() and sha256(snapshot) != source_hash:
            raise ValueError("An existing pinned snapshot has changed")
        if not snapshot.exists():
            shutil.copyfile(original, snapshot)
        record = {field: row[field] for field in ("canonical_id", "collection", "title", "translator", "source_url", "completeness_scope")}
        record.update(version=version, license=name, license_url=license_url(name) if name != FREE_GRANT else row["license_url"],
                      copyright=copyright_text, license_notice=notice,
                      conditions=license_conditions(name) if name != FREE_GRANT else row["conditions"],
                      local_path=relative, sha256=hashlib.sha256(text.encode()).hexdigest(), body_sha256=body_hash,
                      source_snapshot=snapshot_relative, source_sha256=source_hash,
                      source_revision=row.get("source_revision", ""), upstream_file=row.get("upstream_file", ""),
                      source_repository=row.get("source_repository", ""), source_comparison="PASS",
                      source_comparison_method=row.get("source_comparison_method", proposal.get("source_comparison_method", "")),
                      completeness_status=status,
                      attribution_notice=attribution, changes=CHANGES,
                      prior_record_id=row.get("prior_record_id") or prior_keys.get((collection, row["canonical_id"], name)),
                      review_flags=row.get("exceptions", []))
        if explicit:
            record["explicit_grant"] = explicit
        if row.get("mapping_evidence"):
            record["mapping_evidence"] = row["mapping_evidence"]
        if row.get("publisher_references"):
            record["publisher_references"] = row["publisher_references"]
            record["publisher_references_sha256"] = row["publisher_references_sha256"]
        if row.get("source_partition_version"):
            record["source_partition_version"] = row["source_partition_version"]
        by_key[key] = record
        added += 1
    manifest.update(schema_version=1, policy_version=4, count=len(by_key),
                    records=sorted(by_key.values(), key=lambda row: (row["collection"], row["canonical_id"], row["version"])))
    write_json(MANIFEST, manifest)
    verified_manifest()
    update_metadata(manifest)
    return added


def update_metadata(manifest: dict) -> None:
    # Rebuild only our metadata wrapper, never the source translation body.
    # This also upgrades earlier batches to retain the license URL and changes notice.
    for row in manifest["records"]:
        path = ROOT / row["local_path"]
        _header, body = path.read_text(encoding="utf-8").split("\n\n", 1)
        if hashlib.sha256(body.encode()).hexdigest() != row["body_sha256"]:
            raise ValueError("Refusing to rewrap a changed translation")
        text = attributed_text(row, body)
        if text.encode() != path.read_bytes():
            path.write_text(text, encoding="utf-8", newline="\n")
        row.update(sha256=hashlib.sha256(text.encode()).hexdigest(), changes=CHANGES)
    write_json(MANIFEST, manifest)
    verified_manifest()
    eligible_path = ROOT / "metadata/eligible-texts.json"
    eligible = json.loads(eligible_path.read_text())
    existing = [row for row in eligible["texts"] if not row.get("licensed_collection")]
    for row in manifest["records"]:
        existing.append({**row, "kind": "sutta", "licensed_collection": True, "rights_status": "EXPLICIT_PERMISSION_VERIFIED"})
    eligible.update(policy="Documented public-domain status, accepted Creative Commons licenses or explicit free-redistribution permission",
                    count=len(existing), texts=existing)
    write_json(eligible_path, eligible)
    # Register only these individually reviewed source and text payloads. Code/docs
    # added during development require their separate rights review before publication.
    path = ROOT / "metadata/public-file-allowlist.json"
    allowlist = json.loads(path.read_text())
    entries = {row["path"]: row for row in allowlist["files"]}
    for row in manifest["records"]:
        for source_path in (row["local_path"], row["source_snapshot"]):
            entries[source_path] = {"path": source_path, "sha256": sha256(ROOT / source_path),
                                    "license_scope": row["license"], "rights_basis": SCOPE_BASIS}
    allowlist["files"] = sorted(entries.values(), key=lambda row: row["path"])
    write_json(path, allowlist)


def write_coverage() -> None:
    """Generate edition coverage without claiming all built files are already live."""
    eligible = json.loads((ROOT / "metadata/eligible-texts.json").read_text())["texts"]
    excluded = json.loads((ROOT / "metadata/excluded-sources.json").read_text())["text_versions"]
    records = []
    for row in eligible:
        records.append({"canonical_id": row["canonical_id"], "collection": row.get("collection", ""),
                        "translator": row.get("translator", ""), "license": row["license"],
                        "state": "BUILD_ELIGIBLE", "completeness": row.get("completeness_status", "UNKNOWN"),
                        "source_url": row["source_url"]})
    for row in excluded:
        records.append({"canonical_id": row["canonical_id"], "collection": row.get("collection", ""),
                        "translator": row.get("translator", ""), "license": row["license"],
                        "state": row["rights_status"], "completeness": row.get("completeness_status", "UNKNOWN"),
                        "source_url": row["source_url"]})
    result = {"date": "2026-11-11", "scope": "Known English edition records. BUILD_ELIGIBLE means validated source/build inclusion; actual public deployment is recorded separately.",
              "build_eligible_editions": len(eligible),
              "build_eligible_text_ids": len({(row.get("collection"), row["canonical_id"]) for row in eligible}),
              "known_edition_records": len(records),
              "by_state": dict(Counter(row["state"] for row in records)), "records": records}
    write_json(ROOT / "metadata/reports/translation-coverage-2026-11-11.json", result)
    path = ROOT / "metadata/reports/translation-coverage-2026-11-11.csv"
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def write_held_sources() -> None:
    """Retain the whole source-review queue without copying held translations."""
    ati = ROOT / "build/ati-bulk-20261111/proposal.json"
    sc = ROOT / "build/sc-bulk-20261111/proposal.json"
    if not ati.is_file() or not sc.is_file():
        return
    rows = []
    for row in json.loads(ati.read_text())["held"]:
        name = row["upstream_file"]
        url = ("https://www.accesstoinsight.org/" + name.removeprefix("ati/")
               if row["publisher"] == "ati" else "https://www.dhammatalks.org/suttas/" + name)
        rows.append({"source": row["publisher"], "title": name, "original": url,
                     "source_sha256": row["source_sha256"], "questions": row["held_reasons"]})
    for row in json.loads(sc.read_text())["held"]:
        rows.append({"source": "SuttaCentral / PTS", "title": "The Path of Discrimination",
                     "original": "https://palitextsociety.org/copyright-information/",
                     "source_sha256": row["source_sha256"],
                     "questions": [row["decision"], "154 of 664 PDF pages differ in text extraction order."]})
    abt = ROOT / "build/abt-bulk-20261111/proposal.json"
    if abt.is_file():
        for row in json.loads(abt.read_text())["records"]:
            body = input_path(row["body_path"], abt).read_text(encoding="utf-8")
            codes = sorted({f"U+{ord(c):04X}" for c in body if unicodedata.category(c) == "Co"})
            if codes:
                rows.append({"source": "Ancient Buddhist Texts", "title": row["canonical_id"],
                             "original": row["source_url"], "source_sha256": row["source_sha256"],
                             "questions": ["Unmapped private-use source font characters: " + ", ".join(codes) + ". Preserve original; verify publisher font mapping before release."]})
    identity_report = ROOT / "metadata/reports/licensed-identity-corrections-2026-11-11.json"
    if identity_report.exists():
        rows.extend(json.loads(identity_report.read_text(encoding="utf-8"))["held"])
    write_json(ROOT / "metadata/reports/licensed-held-sources-2026-11-11.json",
               {"date": "2026-11-11", "scope": "All held ATI/dhammatalks source pages and the SC PDF in this bounded batch; source pages are not necessarily unique suttas. PTS EPUB and Candana work have separate review lists.",
                "count": len(rows), "sources": rows})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", action="append", type=Path, default=[])
    args = parser.parse_args()
    imported = sum(import_proposal(path) for path in args.proposal)
    result = reassess()
    write_coverage()
    write_held_sources()
    print(json.dumps({"imported": imported, "reassessed": result["count"], "decisions": result["decisions"]}))


if __name__ == "__main__":
    main()
