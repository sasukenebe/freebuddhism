#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Check every conditionally licensed reader and download without model calls."""
from __future__ import annotations

import argparse
from collections import Counter
from html import escape, unescape
import json
from pathlib import Path
import re

from check_candana_readers import SourceText
from publication_rights import ROOT, verified_manifest, verify_published_source
from public_site_catalog import canonical_slug


def check_reader(row: dict, source_root: Path, site_root: Path) -> dict:
    slug = canonical_slug(row["canonical_id"])
    relative = Path("theravada/tipitaka/sutta") / row["collection"] / slug / f"{slug}-{row['version']}.html"
    original = (source_root / row["local_path"]).read_bytes()
    body = original.decode("utf-8").split("\n\n", 1)[1]
    downloaded = site_root / row["local_path"]
    if downloaded.read_bytes() != original:
        raise ValueError("Public TXT differs from verified source: " + str(relative))
    page = (site_root / relative).read_text(encoding="utf-8")
    parser = SourceText()
    parser.feed(page)
    parser.close()
    if parser.body() != body:
        raise ValueError("Reader body differs from verified source: " + str(relative))
    visible = unescape(re.sub(r"<[^>]*>", " ", page))
    for value in (row["license"], row["license_notice"], row["copyright"]):
        if value not in visible:
            raise ValueError("Reader is missing edition rights: " + str(relative))
    if row["license_url"] not in unescape(page) or row["source_url"] not in unescape(page):
        raise ValueError("Reader is missing original/license link: " + str(relative))
    if row.get("publisher_references"):
        if (row["publisher_references"] not in visible
                or 'class="publisher-references"' not in page
                or "Publisher references (not part of the sutta)" not in visible):
            raise ValueError("Publisher references are not separately retained: " + str(relative))
    pdf = (site_root / relative).with_name(f"{slug}-{row['version']}-reader.pdf")
    if not pdf.read_bytes().startswith(b"%PDF-"):
        raise ValueError("Reader PDF is absent or invalid: " + str(relative))
    return {"text": row["canonical_id"], "translator": row["translator"],
            "original": row["source_url"], "new": "https://freebuddhism.org/" + relative.as_posix(),
            "completeness": row["completeness_status"], "review_notes": row.get("review_flags", []),
            "human_review": "NOT_RECORDED"}


def check_release(site_root: Path) -> dict:
    rows = verified_manifest()["records"]
    for row in rows:
        verify_published_source(row)
    reviews = [check_reader(row, ROOT, site_root) for row in rows]
    return {"status": "ALL_LICENSED_READERS_MATCH", "edition_count": len(rows),
            "unique_text_ids": len({(r["collection"], r["canonical_id"]) for r in rows}),
            "completeness": dict(Counter(r["completeness_status"] for r in rows)),
            "publisher_html_sources_recompared": sum(bool(r.get("mapping_evidence")) for r in rows),
            "comparison": "Every displayed character, whitespace and punctuation matches the pinned translation body; TXT downloads are byte-identical; rights notices/links and PDF presence checked.",
            "limits": "Not a translation-quality verdict or full visual proofreading. Source extraction comparisons are recorded separately. PDF text is spot-checked separately.",
            "model_calls": 0, "review": reviews}


def write_public_review(site_root: Path, source_revision: str = "") -> set[Path]:
    """Simple original-versus-new links, with the entire rolling exception list."""
    rows = verified_manifest()["records"]
    if not rows:
        return set()
    groups = {}
    for row in rows:
        groups.setdefault(row["collection"], []).append(row)
    sections = []
    for collection, editions in sorted(groups.items()):
        links = []
        for row in editions:
            slug = canonical_slug(row["canonical_id"])
            node = "/theravada/tipitaka/sutta/" + collection + "/" + slug + "/"
            notes = row.get("review_flags", [])
            detail = ("<details><summary>Review notes</summary><ul>" + "".join("<li>" + escape(n) + "</li>" for n in notes) + "</ul></details>") if notes else ""
            links.append("<li><strong>" + escape(row["canonical_id"] + " — " + row["title"]) + "</strong> — " + escape(row["translator"]) +
                         ' · <a href="' + escape(row["source_url"], quote=True) + '">Original source</a>' +
                         ' · <a href="' + node + slug + "-" + row["version"] + '.html">Converted text</a>' +
                         ' · <a href="' + node + 'index.html">Text home</a> · ' + escape(row["completeness_status"]) + detail + "</li>")
        sections.append("<details><summary>" + escape(collection.replace("/", " / ")) + f" — {len(editions)} editions</summary><ul>" + "".join(links) + "</ul></details>")
    held_path = ROOT / "metadata/reports/licensed-held-sources-2026-11-11.json"
    held = json.loads(held_path.read_text())["sources"] if held_path.exists() else []
    held_html = '<details><summary>All held source pages</summary><ul>' + ''.join(
        '<li><a href="' + escape(r["original"], quote=True) + '">' + escape(r["title"]) + '</a> — '
        + escape(' '.join(r["questions"])) + '</li>' for r in held) + '</ul></details>'
    corrections_path = ROOT / "metadata/reports/licensed-identity-corrections-2026-11-11.json"
    corrections_html = ""
    if corrections_path.exists():
        audit = json.loads(corrections_path.read_text(encoding="utf-8"))
        corrections = [r for r in audit["corrections"] if r["action"] == "CORRECTED"]
        confirmed = sum(r["action"] == "CONTENT_CONFIRMED" for r in audit["corrections"])
        items = []
        for row in corrections:
            edition = next(r for r in rows if r["source_url"] == row["source_url"] and r["version"] == row["version"])
            slug = canonical_slug(row["canonical_id"])
            url = "/theravada/tipitaka/sutta/" + edition["collection"] + "/" + slug + "/" + slug + "-" + row["version"] + ".html"
            items.append('<li>' + escape(row["previous_canonical_id"]) + ' was incorrect for this edition; '
                         '<a href="' + escape(url, quote=True) + '">' + escape(row["canonical_id"]) + '</a> is correct. '
                         '<a href="' + escape(row["source_url"], quote=True) + '">Publisher source</a>.</li>')
        corrections_html = (f'<p>Correction: {len(corrections)} discourse associations were wrong and have been reassigned; '
                            f'{confirmed} other title-remapped associations were confirmed by content. '
                            f'{audit.get("additional_numbering_associations_reviewed", 0)} additional edition-number differences were reviewed, '
                            f'of which {audit.get("additional_numbering_associations_confirmed", 0)} existing targets were confirmed. '
                            f'{len(audit["held"])} source pages are held for discourse-boundary review. '
                            'Publisher cross-references are now separate from the sutta body.</p>'
                            '<details><summary>Corrected references</summary><ul>' + ''.join(items) + '</ul></details>')
    page = site_root / "review/licensed-2026-11-11/index.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    release = ('<p>Release: <a href="https://github.com/sasukenebe/freebuddhism/commit/' + source_revision
               + '">' + source_revision[:12] + '</a> · <a href="/release.json">Release details</a>.</p>') if source_revision else ''
    page.write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Compare translations</title></head><body><p><a href="/">Home</a> · <a href="/theravada/tipitaka/site/tipitaka.html">Buddhist Texts</a></p><h1>Compare translations</h1>' +
                    release + f"<p>{len(rows)} imported editions. Open a collection, then compare Original source with Converted text.</p>" +
                    "<p>Automated source comparison checks text preservation, not whether two reference numbers identify the same discourse. Identity reviews are separate. This is not full human proofreading. COMPLETE refers to the scope recorded for that edition; ABBREVIATED and PARTIAL preserve the source's omissions. UNKNOWN means completeness is not established.</p>" +
                    corrections_html + "".join(sections) + "<h2>Still held</h2><ul><li>The Path of Discrimination: 154 of 664 pages differ in extraction order; no book published.</li><li>Access to Insight/dhammatalks source pages listed below need numbering, grouping or source-scope review. These are source pages, not necessarily distinct suttas.</li><li>PTS Nikāya EPUBs: original translation permissions identified; editorial additions and mappings still need checking before import.</li><li>Candana's separate PDFs: awaiting confirmation of the permission scope; not imported by this batch.</li></ul>" + held_html + "</body></html>\n", encoding="utf-8")
    return {page}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-root", type=Path, default=ROOT / "build/site-root")
    parser.add_argument("--output", type=Path, default=ROOT / "build/licensed-reader-check.json")
    args = parser.parse_args()
    report = check_release(args.site_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "review"}))


if __name__ == "__main__":
    main()
