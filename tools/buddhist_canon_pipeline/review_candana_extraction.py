#!/usr/bin/env python3
"""Record full-page engine comparison and explicitly performed visual samples."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unicodedata

from import_candana import ROOT, MANIFEST, verified_manifest


REPORT = ROOT / "metadata/reports/candana-extraction-2026-11-05.json"


def page_characters(text: str, page_number: int) -> str:
    # Both engines preserve source order, but one emits the page number first
    # and the other emits it last. Ignore that one pagination token and spaces.
    matches = list(re.finditer(rf"(?m)^[ \t]*{page_number}[ \t]*$", text))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one pagination label on page {page_number}")
    text = text[:matches[0].start()] + text[matches[0].end():]
    return re.sub(r"\s+", "", text)


def compare(book: Path, visual_pages: list[int]) -> dict:
    poppler = subprocess.run(["pdftotext", "-layout", str(book), "-"], check=True,
                             capture_output=True, text=True).stdout.split("\f")
    mupdf = subprocess.run(["mutool", "draw", "-F", "txt", "-o", "-", str(book)], check=True,
                           capture_output=True, text=True).stdout.split("\f")
    pages = list(range(36, 211))
    if len(poppler) != 213 or len(mupdf) != 213:
        raise ValueError("The reviewed AN Book 1 edition must have 212 PDF pages")
    mismatches = [number for number in pages
                  if page_characters(poppler[number - 1], number) != page_characters(mupdf[number - 1], number)]
    if mismatches:
        raise ValueError(f"Extraction engines disagree on source pages: {mismatches}")
    if set(visual_pages) - set(pages):
        raise ValueError("A visual review page is outside the translated text")
    return {"source_sha256": hashlib.sha256(book.read_bytes()).hexdigest(),
            "engines": ["Poppler pdftotext -layout", "MuPDF mutool draw -F txt"],
            "comparison": "Ordered non-whitespace characters, excluding one printed page number per page",
            "translation_pages": [36, 210], "pages_compared": len(pages), "mismatched_pages": mismatches,
            "visual_sample_pages": sorted(set(visual_pages)),
            "visual_reviewer": "Codex: visible PDF pages compared with extracted text",
            "review_limit": "Visual samples are not a page-by-page human certification; other PDFs require their own checks."}


def stage_sutta_nipata_candidate() -> dict:
    """Keep the improved extraction private until its order/boundaries are checked."""
    manifest = verified_manifest()
    book = next(row for row in manifest["books"] if row["id"] == "sutta-nipata")
    source = ROOT / book["local_path"]
    poppler = subprocess.run(["pdftotext", "-layout", str(source), "-"], check=True,
                             capture_output=True, text=True).stdout.split("\f")
    raw = subprocess.run(["mutool", "draw", "-F", "txt", "-o", "-", str(source)], check=True,
                         capture_output=True, text=True).stdout
    mupdf = raw.split("\f")
    def inventory(text):
        return Counter(re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)))
    if len(poppler) != len(mupdf):
        raise ValueError("Sutta Nipāta extraction page counts differ")
    mismatches = [number for number in range(1, len(mupdf))
                  if inventory(poppler[number - 1]) != inventory(mupdf[number - 1])]
    output = ROOT / "build/candana-audit/sutta-nipata-mupdf-candidate.txt"
    output.write_text(raw, encoding="utf-8")
    identifiers = re.findall(r"(?m)^Snp\.\s*(\d+\.\d+)", raw)
    report = {"status": "DRAFT_NOT_PUBLISHABLE", "source_sha256": book["sha256"],
              "candidate_sha256": hashlib.sha256(raw.encode()).hexdigest(),
              "pages": len(mupdf) - 1, "character_inventory_mismatch_pages": mismatches,
              "comparison_limit": "Matching character inventories do not verify reading order",
              "detected_header_count": len(identifiers), "detected_ids": identifiers,
              "visual_sample_pages": [20],
              "remaining": "Reconcile all source text boundaries, verify reading/verse order and Pāli characters; no automatic corrections",
              "candidate": output.relative_to(ROOT).as_posix()}
    (output.parent / "sutta-nipata-candidate-review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {key: report[key] for key in ("status", "pages", "character_inventory_mismatch_pages", "detected_header_count", "candidate")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--visual-pages",
                        help="Comma-separated pages already inspected visually; never infer these from machine agreement")
    group.add_argument("--stage-sutta-nipata-candidate", action="store_true")
    args = parser.parse_args()
    if args.stage_sutta_nipata_candidate:
        print(json.dumps(stage_sutta_nipata_candidate()))
        return
    manifest = verified_manifest()
    book = next(row for row in manifest["books"] if row["id"] == "an-book1")
    result = compare(ROOT / book["local_path"], [int(value) for value in args.visual_pages.split(",")])
    result.update(schema_version=1, observed="2026-11-05", reader_units=len(manifest["texts"]), numbered_source_units=627,
                  status="TWO_ENGINE_AGREEMENT_WITH_VISUAL_SAMPLES",
                  paragraph_reflow="Whitespace-only physical line-wrap removal; seven reviewed compound-break spellings are rejoined with their original hyphens; no corrections or expansion",
                  source_manifest="metadata/source-manifests/candana.json",
                  reader_body_hashes={row["canonical_id"]: row["body_sha256"] for row in manifest["texts"]},
                  held_sources={"sutta-nipata": "Ligature/diacritic extraction problems; no plain-text import or default selection"})
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "pages_compared", "mismatched_pages", "visual_sample_pages", "reader_units")}))


if __name__ == "__main__":
    main()
