#!/usr/bin/env python3
"""Build a text-free public exclusion inventory from reviewed metadata."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from buddhist_canon_pipeline.publication_rights import canonical_license


ROOT = Path(__file__).resolve().parents[1]
LICENSED = ROOT / "metadata/source-manifests/licensed-collections.json"
CLASSIFICATION = ROOT / "metadata/reports/strict-license-classification-2026-10.json"
IMPACT = ROOT / "metadata/reports/remediation-impact-map-2026-10.json"
OUTPUT = ROOT / "metadata/excluded-sources.json"
URL_RE = re.compile(r"https?://[^\s;,<>\"']+")
STANDALONE_TRANSLATORS = {
    "The Minor Readings and The Illustrator of Ultimate Meaning": "Bhikkhu Ñāṇamoli",
    "The Piṭaka-Disclosure (Peṭakopadesa)": "Bhikkhu Ñāṇamoli",
    "The Questions of King Milinda, Parts I–II": "T. W. Rhys Davids",
    "dhammasangani.txt": "Caroline A.F. Rhys Davids",
    "dhatukatha.txt": "U Nārada, assisted by Thein Nyun",
    "puggalapannatti.txt": "Bimala Charan Law",
    "kathavatthu.txt": "Shwe Zan Aung and Caroline A.F. Rhys Davids",
    "yamaka.txt": "U Nārada, U Nandamedha, and U Kumārābhivaṃsa, assisted by others",
    "vibhanga.txt": "Paṭhamkyaw Ashin Thiṭṭila (Seiṭṭhila)",
    "The Birth Stories: revised and reconstructed Jātaka commentary":
        "T. W. Rhys Davids, Robert Chalmers, H. T. Francis, W. H. D. Rouse, and E. B. Cowell",
    "The Path of Discrimination": "Bhikkhu Ñāṇamoli",
    "The Book of the Discipline": "I.B. Horner; supplementary translated passages by Bhikkhu Brahmali",
}


def clean_evidence(value: str) -> dict:
    urls = URL_RE.findall(value or "")
    note = re.sub(URL_RE, "", value or "")
    note = note.replace("metadata/source-manifests/", "source manifest ")
    note = re.sub(r"\s+", " ", note).strip(" ;,")
    return {"note": note or None, "urls": sorted(set(urls))}


def translator(record: dict) -> str:
    label = record.get("version_label", "").strip()
    if label:
        name = label.split(" — ", 1)[0].strip()
        if " (" in name:
            name = name.split(" (", 1)[0].strip()
        return name
    group = record.get("source_group", "")
    match = re.search(r"—\s*(Bhikkhu\s+[^,]+)", group)
    return match.group(1).strip() if match else "Not identified in source metadata"


def build() -> dict:
    classified = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))["records"]
    impact = json.loads(IMPACT.read_text(encoding="utf-8"))
    impact_records = {row["record_key"]: row for row in impact["records"]}
    versions = []
    released = {row.get("prior_record_id") for row in json.loads(LICENSED.read_text(encoding="utf-8"))["records"]} if LICENSED.exists() else set()
    for record in classified:
        key = record["record_key"]
        if key in released:
            continue
        mapped = impact_records.get(key)
        if mapped is None:
            raise ValueError(f"No impact-map record for {key}")
        license_name = record.get("declared_license") or "Not verified"
        reason = record.get("rights_basis") or (
            f"Rights status is {record.get('rights_status', 'unknown')}; "
            "the edition did not pass the CC0/verified-public-domain allowlist."
        )
        status = record.get("rights_status")
        if status == "RIGHTS_RESTRICTED" and canonical_license(license_name):
            status = "LICENSE_ACCEPTED_PENDING_SOURCE_CHECK"
            reason = "The current publication policy accepts this license; complete source validation and import are still pending."
        versions.append({
            "record_id": key,
            "canonical_id": record.get("canonical_id"),
            "collection": record.get("collection_path"),
            "source_group": record.get("source_group"),
            "title": record.get("label") or record.get("canonical_id"),
            "translator": translator(record),
            "translator_label": record.get("version_label") or None,
            "source_url": record.get("source_url") or "Not recorded in current metadata",
            "historical_local_paths": [value for value in (
                record.get("local_text_path"), record.get("local_pdf_path")
            ) if value],
            "license": license_name,
            "rights_status": status,
            "exclusion_reason": reason,
            "rights_evidence": clean_evidence(record.get("rights_evidence", "")),
            "completeness_status": record.get("completeness_status", "UNKNOWN"),
            "completeness_scope": record.get("completeness_scope") or None,
            "completeness_evidence": clean_evidence(record.get("completeness_evidence", "")),
            "existing_site_routes": mapped.get("published_urls", {}),
        })

    standalone = []
    for record in impact.get("standalone_assets", []):
        if record.get("rights_status") in {"ELIGIBLE_CC0", "ELIGIBLE_PD"}:
            continue
        license_name = record.get("license") or "Not verified"
        status = record.get("rights_status", "RIGHTS_UNVERIFIED")
        accepted_license = bool(canonical_license(license_name))
        if accepted_license and status == "RIGHTS_RESTRICTED":
            status = "LICENSE_ACCEPTED_PENDING_SOURCE_CHECK"
        translator_name = STANDALONE_TRANSLATORS.get(record.get("title", ""))
        standalone.append({
            "record_id": record.get("record_key") or None,
            "asset_type": record.get("entity_type"),
            "canonical_id": record.get("canonical_id") or None,
            "collection": record.get("collection") or None,
            "title": record.get("title"),
            "translator": record.get("translator") or translator_name or "Not identified in source metadata",
            "source_url": record.get("source_page") or "Not recorded in current metadata",
            "license": license_name,
            "rights_status": status,
            "exclusion_reason": (
                (f"The current policy accepts the declared {license_name}; exact source, extraction and publication checks remain pending."
                 if accepted_license else
                 f"{status}; this exact edition's redistribution terms and source have not yet been verified.")
            ),
            "completeness_status": record.get("completeness_status", "UNKNOWN"),
            "completeness_scope": record.get("completeness_scope") or None,
            "existing_site_routes": record.get("published_urls", {}),
        })

    if {row["record_key"] for row in classified} != set(impact_records):
        raise ValueError("Historical classification and impact identifiers differ")
    return {
        "schema_version": 1,
        "license": "CC0-1.0",
        "content_policy": "Metadata only; excluded source text is never copied here.",
        "rights_and_completeness_are_independent": True,
        "text_versions": versions,
        "standalone_assets": standalone,
        "counts": {
            "excluded_text_versions": len(versions),
            "excluded_standalone_assets": len(standalone),
            "rights_status": dict(sorted(
                (status, sum(item["rights_status"] == status for item in versions))
                for status in {item["rights_status"] for item in versions}
            )),
            "completeness_status": dict(sorted(
                (status, sum(item["completeness_status"] == status for item in versions))
                for status in {item["completeness_status"] for item in versions}
            )),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare generated metadata without writing")
    args = parser.parse_args()
    result = build()
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != encoded:
            raise SystemExit("excluded inventory is stale; run build_excluded_inventory.py")
        print(f"excluded inventory current: {len(result['text_versions'])} text versions")
    else:
        OUTPUT.write_text(encoded, encoding="utf-8")
        print(f"wrote {OUTPUT.relative_to(ROOT)}: {len(result['text_versions'])} text versions, "
              f"{len(result['standalone_assets'])} standalone assets")


if __name__ == "__main__":
    main()
