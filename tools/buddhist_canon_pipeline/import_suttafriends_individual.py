# SPDX-License-Identifier: 0BSD
"""Import pinned individual articles, never whole site wrappers or bulk grants."""
from __future__ import annotations

import argparse
from html import escape, unescape
import json
from pathlib import Path
import re
import subprocess
import sys

from prepare_suttafriends import (MANIFEST as CACHED_MANIFEST, MANIFEST_SHA256, SNAPSHOTS,
                                 REGION, checked, source_metadata, article, digest, publisher_citation_matches)
from publication_rights import ROOT, MANIFEST, verified_manifest, checked_path
from distribution_policy import (INDIVIDUAL_LICENSE, INDIVIDUAL_TERMS, INDIVIDUAL_CONDITIONS,
                                 INDIVIDUAL_DISTRIBUTION)
from suttafriends_rights import ARTICLE_DIRECTORY, TEXT_DIRECTORY, RIGHTS_URL, verify_record
from import_licensed_batches import attributed_text, write_json, update_metadata, write_coverage, CHANGES


def import_individual(source_root: Path) -> int:
    original = json.loads(checked(source_root, CACHED_MANIFEST.as_posix(), MANIFEST_SHA256))
    cache = source_root / SNAPSHOTS
    rights = checked(cache, "rights/copyright.html.source", original["shared_sources"]["rights/copyright.html.source"])
    visible = " ".join(unescape(re.sub(r"<[^>]*>", " ", rights.decode())).split())
    if INDIVIDUAL_TERMS not in visible:
        raise ValueError("Pinned original does not contain the complete individual-sharing statement")
    manifest = verified_manifest()
    prior_rows = json.loads((ROOT / "metadata/excluded-sources.json").read_text())["text_versions"]
    prior = {(r["canonical_id"], r["source_url"]): r["record_id"] for r in prior_rows}
    existing = {(r["collection"], r["canonical_id"], r["version"]): r for r in manifest["records"]}
    prepared = []
    # Validate the entire pinned batch before any public source file is written.
    for row in source_metadata(original)["rows"]:
        stem = row["source_url"].rstrip("/").split("/")[-1]
        page = checked(cache, row["prefix"] + "/" + stem + "-page.html.source", row["page_sha256"])
        source = page.decode("utf-8")
        headings = re.findall(r'<h1\b[^>]*>(.*?)</h1>', source, re.S)
        if len(headings) != 1:
            raise ValueError("Expected one original article heading")
        heading = " ".join(unescape(re.sub(r"<[^>]*>", "", headings[0])).split())
        if not publisher_citation_matches(row["source_id"], heading):
            raise ValueError("Original publisher heading disagrees")
        pali = json.loads(checked(cache, f'pali/{row["prefix"]}{row["number"]}_root-pli-ms.json.source', row["pali_sha256"]))
        title_key = f'{row["prefix"]}{row["number"]}:0.' + ("4" if row["prefix"] == "vv" else "3")
        if pali.get(title_key, "").strip() != row["pali_title"]:
            raise ValueError("Pinned Pali correspondence changed")
        body, _comparison = article(page)
        # The grant covers the individual article, not navigation, adverts or
        # unrelated web-page wrappers. Preserve its full original region only.
        regions = REGION.findall(source)
        fragment = ('<h1>' + escape(heading) + '</h1>\n<div class="entry-content">'
                    + regions[0] + '</div><!-- .entry-content -->\n').encode()
        if article(fragment)[0] != body:
            raise ValueError("Article-only snapshot loses source text")
        collection = "khuddaka-nikaya/" + ("vimanavatthu" if row["prefix"] == "vv" else "petavatthu")
        record = {
            "canonical_id": row["canonical_id"], "collection": collection,
            "version": "suttafriends", "title": row["title"],
            "translator": "Mahamevnawa Buddhist Monastery (Sutta Friends)",
            "source_url": row["source_url"], "license": INDIVIDUAL_LICENSE, "license_url": RIGHTS_URL,
            "copyright": "© Mahamevnawa Buddhist Monastery", "license_notice": INDIVIDUAL_TERMS,
            "explicit_grant": INDIVIDUAL_TERMS, "conditions": INDIVIDUAL_CONDITIONS,
            "distribution": INDIVIDUAL_DISTRIBUTION,
            "source_snapshot": ARTICLE_DIRECTORY + stem + ".source", "source_sha256": digest(fragment),
            "source_page_sha256": row["page_sha256"], "pali_source_sha256": row["pali_sha256"],
            "pali_title": row["pali_title"], "source_revision": row["page_sha256"],
            "permission_source_sha256": digest(rights), "preparation_manifest_sha256": MANIFEST_SHA256,
            "local_path": TEXT_DIRECTORY + row["prefix"] + str(row["number"]) + ".txt",
            "body_sha256": digest(body.encode()), "source_comparison": "PASS",
            "source_comparison_method": "Whole protected article: HTMLParser and independent ordered-character lexer; complete original page pinned separately; public snapshot omits unrelated site wrapper.",
            "completeness_status": "UNKNOWN",
            "completeness_scope": "Complete publisher article including supplied Pali, notes and lists. Unabridged canonical coverage and translation accuracy not independently established.",
            "mapping_evidence": {"method": "Publisher chapter/flat numbering concordance", "publisher_id": row["source_id"],
                                 "flat_id": row["canonical_id"], "pali_title": row["pali_title"],
                                 "basis": "Publisher chapter order/counts and actual article heading, checked against pinned numbered Pali title; not a same-title reassignment."},
            "attribution_notice": "English from the Sinhala translations published by Mahamevnawa Buddhist Monastery; see the original article and publisher permission statement.",
            "changes": CHANGES, "review_flags": ["Individual-reader permission only in this build; no combined/source archives.",
                                                     "Full human proofreading and unabridged canonical coverage remain unverified."],
        }
        previous = existing.get((collection, record["canonical_id"], record["version"]), {})
        record["prior_record_id"] = prior.get((record["canonical_id"], record["source_url"])) or previous.get("prior_record_id")
        text = attributed_text(record, body).encode()
        record["sha256"] = digest(text)
        key = (collection, record["canonical_id"], record["version"])
        if key in existing:
            if existing[key] != record:
                raise ValueError("Refusing to replace a different individual edition")
            continue
        for name in (record["source_snapshot"], record["local_path"]):
            if checked_path(ROOT, name).exists():
                raise ValueError("Unmanifested individual source file already exists: " + name)
        prepared.append((record, fragment, text))
    for record, fragment, text in prepared:
        for name, payload in ((record["source_snapshot"], fragment), (record["local_path"], text)):
            path = checked_path(ROOT, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        verify_record(record, ROOT)
        manifest["records"].append(record)
    manifest["records"].sort(key=lambda r: (r["collection"], r["canonical_id"], r["version"]))
    manifest["count"] = len(manifest["records"])
    write_json(MANIFEST, manifest)
    verified_manifest()
    update_metadata(manifest)
    subprocess.run([sys.executable, str(ROOT / "tools/build_excluded_inventory.py")], check=True)
    write_coverage()
    return len(prepared)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({"imported_individual_articles": import_individual(args.source_root.resolve()),
                      "bulk_distribution": False, "deployed": False}))


if __name__ == "__main__": main()
