#!/usr/bin/env python3
"""Publish only the pinned, permission-checked complete Sutta Nipāta review snapshot."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path

if __package__:
    from .candana_resources import SNP_SHA, SNP_FOLIOS, document, reading_html, section_link, snp_partition, snp_reading_body
else:
    from candana_resources import SNP_SHA, SNP_FOLIOS, document, reading_html, section_link, snp_partition, snp_reading_body

LICENSE = "Candana — free distribution, unaltered contents"
RIGHTS_BASIS = ("The exact source PDF grants redistribution in any medium, "
                "free of charge and without altering its contents; its notice "
                "and the source SHA-256 are recorded in the Candana manifest.")

ROOT = Path(__file__).resolve().parents[2]
SOURCE_URL = "https://www.mindreleased.com/s/Sutta-Nipta_Bhikkhu_Candana_2026-2ggf.pdf"
TEXT_SHA = "fb1e36fb23c076949b15aaa3c5e738342ead95a924e376837e2921da58481087"
INPUT = Path("review-sources/candana-sutta-nipata")
MANIFEST = Path("metadata/source-manifests/candana-snp-review.json")
ROUTE = Path("reviews/candana-sutta-nipata")
ORIGIN = "https://freebuddhism.org/" + ROUTE.as_posix() + "/"
CONDITIONS = ["Copies must be available free of charge", "Do not alter the contents"]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def expected_manifest() -> dict:
    return {"schema_version": 1, "status": "CONVERSION_REVIEW_DRAFT", "title": "Sutta Nipāta",
            "translator": "Bhikkhu Candana", "source_url": SOURCE_URL,
            "pdf_path": (INPUT / "original.pdf").as_posix(), "pdf_sha256": SNP_SHA,
            "text_path": (INPUT / "converted.txt").as_posix(), "text_sha256": TEXT_SHA,
            "permission_pages": [7], "license": LICENSE, "conditions": CONDITIONS,
            "pdf_pages": 391, "sutta_sections": 73, "all_source_intervals": 80,
            "extractor": "MuPDF mutool draw -F txt", "encoding": "UTF-8",
            "canonical_mapping_approval": False, "full_human_proofread_approval": False}


def checked_data(pdf: bytes, raw: bytes) -> tuple[str, list[dict]]:
    if not pdf.startswith(b"%PDF-") or digest(pdf) != SNP_SHA or digest(raw) != TEXT_SHA:
        raise ValueError("Public review must match the exact approved PDF and conversion snapshot")
    text = raw.decode("utf-8", errors="strict")
    notice = " ".join("\f".join(text.split("\f")[:10]).casefold().split())
    if not all(fragment in notice for fragment in (
        "you may copy, reprint, republish", "redistribute this work", "in any medium",
        "free of charge", "not alter its content", "copyright", "candana")):
        raise ValueError("The exact review snapshot lacks its free-unaltered redistribution notice")
    units = snp_partition(text)
    return text, units


def freeze(source: Path, root: Path = ROOT) -> None:
    """Explicit owner-requested release preparation, never called by a timer."""
    if source.is_symlink() or (source / "source.pdf").is_symlink() or (source / "mupdf.txt").is_symlink():
        raise ValueError("Review input must be regular source files")
    pdf, raw = (source / "source.pdf").read_bytes(), (source / "mupdf.txt").read_bytes()
    checked_data(pdf, raw)
    for relative, data in ((INPUT / "original.pdf", pdf), (INPUT / "converted.txt", raw),
                           (MANIFEST, json_bytes(expected_manifest()))):
        target = root / relative
        if any(part.is_symlink() for part in (target, *target.parents)):
            raise ValueError("Review snapshot paths must not contain symlinks")
        if target.exists() and target.read_bytes() != data:
            raise ValueError("Refusing to replace a different public review snapshot")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def payload(root: Path = ROOT) -> dict[str, bytes]:
    manifest_path = root / MANIFEST
    if manifest_path.is_symlink() or json.loads(manifest_path.read_text(encoding="utf-8")) != expected_manifest():
        raise ValueError("Public review manifest changed or is unapproved")
    source, raw_path = root / INPUT / "original.pdf", root / INPUT / "converted.txt"
    if source.is_symlink() or raw_path.is_symlink():
        raise ValueError("Public review sources must be regular files")
    pdf, raw = source.read_bytes(), raw_path.read_bytes()
    text, units = checked_data(pdf, raw)
    attribution = ('<p>Translation © Bhikkhu Candana. Free distribution only; do not alter the contents. '
                   'The original PDF retains the complete permission notice on PDF page 7.</p>')
    body = ('<p>Conversion draft for comparison, not an approved new edition.</p>'
            '<p><a href="original.pdf">Original PDF — complete book</a></p>'
            '<p><a href="converted.html">Converted text — complete book, text-only</a></p>'
            '<p><a href="converted.txt" download>Download complete raw text (UTF-8)</a> · '
            '<a href="review-request.txt">External review request</a></p>' + attribution
            + '<h2>Individual suttas</h2><ol>')
    text_only = '<p>Text-only rendering. Photographs and artwork remain in the original PDF.</p>'
    all_text = ('<p>Conversion draft for comparison; no source-content approval is implied.</p>'
                '<p><a href="index.html">Review home</a> · <a href="original.pdf">Original PDF</a></p>'
                + text_only + attribution)
    outputs = {"original.pdf": pdf, "converted.txt": raw}
    for unit in units:
        label = f'PDF pages {unit["first_pdf_page"]}–{unit["last_pdf_page"]}'
        all_text += ('<section id="' + unit["id"] + '"><h2>' + html.escape(unit["title"])
                     + '</h2><p>' + label + '</p>' + snp_reading_body(unit) + '</section>')
        if unit["kind"] != "SUTTA_SOURCE_INTERVAL":
            continue
        relative = "suttas/" + unit["id"]
        body += section_link(unit["title"], relative + ".html", label)
        outputs[relative + ".txt"] = unit["body"].encode("utf-8")
        outputs[relative + ".html"] = reading_html(unit["title"], unit["body"],
                                                   "../original.pdf", "../index.html", label,
                                                   rendered=snp_reading_body(unit))
        outputs[relative + ".html"] = outputs[relative + ".html"].replace(
            b'</html>', (text_only + attribution).encode("utf-8") + b'</html>')
    body += ('</ol><details><summary>Conversion details</summary><p>'
             'The complete text includes front matter, book dividers and end matter. '
             'This is text-only; artwork remains in the PDF. Index titles stay beside their printed page references. '
             'Proven footer numbers are labeled as pagination. The Snake’s repeated verse breaks are retained; '
             'other verse layout still needs visual proofreading. The raw download is unchanged. '
             'No source words, punctuation, page numbers or footnotes were deleted or corrected.</p>'
             '<p><a href="conversion.json">Source hashes and section/page map</a> · '
             '<a href="' + SOURCE_URL + '">Publisher’s source</a></p></details>')
    outputs["index.html"] = document("Sutta Nipāta — original and converted text", body)
    outputs["converted.html"] = document("Sutta Nipāta — complete conversion draft", all_text)
    request = (
        "Review Bhikkhu Candana's complete Sutta Nipata PDF-to-text conversion.\n\n"
        "Original PDF: " + ORIGIN + "original.pdf\n"
        "Complete converted text: " + ORIGIN + "converted.html\n"
        "Unchanged raw extraction (UTF-8): " + ORIGIN + "converted.txt\n"
        "Section and PDF-page map: " + ORIGIN + "conversion.json\n\n"
        "Compare all 391 PDF pages, including front matter and end matter, not only Snp 1.1. "
        "Check missing/repeated/reordered words or verses, accents, punctuation, word boundaries, "
        "footnotes, numbered markers and section starts/ends. Distinguish physical line wrapping "
        "from genuine paragraph or verse structure. Do not rewrite the translation, modernize "
        "wording, invent omitted repetitions or silently repair the source.\n\n"
        "For each finding give the PDF page, source sutta reference if present, original wording, "
        "converted wording, concrete difference and smallest proposed extraction correction. "
        "State precisely which pages you inspected and which remain unchecked; sampling is not "
        "a complete review. Distinguish source-author choices from conversion errors. "
        "Give a clear verdict and unresolved limits. This review does not approve canonical mapping "
        "or change the author's free-distribution/no-alteration conditions.\n")
    outputs["review-request.txt"] = request.encode("utf-8")
    details = expected_manifest() | {"units": [{k: v for k, v in unit.items() if k != "body"}
                                              for unit in units],
                                    "output_hashes": {name: digest(data) for name, data in outputs.items()}}
    # Public provenance uses URLs/filenames, never private checkout paths.
    details.pop("pdf_path")
    details.pop("text_path")
    details["presentation"] = {"revision": 2, "text_only": True,
                               "printed_folio_pages": list(SNP_FOLIOS), "index_rows": 73,
                               "verified_verse_break_scope": "Snp 1.1, 17 repeated Thus refrains",
                               "editorial_labels_class": "editorial",
                               "other_verse_layout_visually_approved": False}
    outputs["conversion.json"] = json_bytes(details)
    return outputs


def write_review(destination: Path, root: Path = ROOT) -> set[Path]:
    outputs = payload(root)
    target = destination / ROUTE
    if target.exists():
        raise ValueError("Public review output must not replace an existing directory")
    for relative, data in outputs.items():
        path = target / relative
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError("Public review output must not follow symlinks")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return {target / name for name in outputs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-from", type=Path, required=True)
    args = parser.parse_args()
    freeze(args.freeze_from)
    print(json.dumps({"status": "FROZEN_FOR_PUBLIC_REVIEW", "source_sha256": SNP_SHA,
                      "converted_sha256": TEXT_SHA, "pdf_pages": 391, "suttas": 73}))


if __name__ == "__main__":
    main()
