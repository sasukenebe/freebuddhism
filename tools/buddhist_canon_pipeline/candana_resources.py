"""Private, lossless source-unit drafts and diagnostics for two pinned Candana works."""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import hashlib
import html
import json
import re
import unicodedata

SNP_SHA = "ff6fa85ebaed058886a2d52b1b0d3e1b29eeca3b26995a23bff6a50066e84495"
MANUAL_SHA = "1edc8f3010f636dbabdc0fcfbded0d8820095e549bc2c5536dbb4bdc23da9152"


def json_data(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def document(title: str, body: str) -> bytes:
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>' + html.escape(title) + '</title><style>'
            'pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere}'
            '</style><h1>' + html.escape(title) + '</h1>' + body + '</html>\n').encode()


def reading_body(text: str) -> str:
    """Retain every source character except physical whitespace layout."""
    paragraphs = [" ".join(part.split()) for part in re.split(r"\n[ \t]*\n+|\f", text)
                  if part.strip()]
    if re.sub(r"\s+", "", "".join(paragraphs)) != re.sub(r"\s+", "", text):
        raise ValueError("Reading presentation changed a source character")
    return ('<div class="converted-text">' + ''.join('<p>' + html.escape(part) + '</p>'
                                                   for part in paragraphs) + '</div>')


def reading_html(title: str, text: str, pdf: str = "source.pdf",
                 back: str = "../../index.html", pages: str = "") -> bytes:
    """A readable private draft; retain source characters, not PDF-width wrapping."""
    label = "Original PDF" + (" (" + pages + ")" if pages else "")
    body = ('<p><a href="' + html.escape(back, quote=True) + '">All texts</a> · '
            '<a href="' + html.escape(pdf, quote=True) + '" target="_blank" rel="noopener">'
            + html.escape(label) + '</a></p><h2>Converted text</h2>' + reading_body(text))
    return document(title, body)


def pair_links(title: str, pdf: str, converted: str, anchor: str = "") -> str:
    """The same two clearly named choices for a whole source or an individual text."""
    identifier = ' id="' + html.escape(anchor, quote=True) + '"' if anchor else ""
    return ('<li' + identifier + '>' + html.escape(title) + ' — '
            '<a href="' + html.escape(pdf, quote=True) + '" target="_blank" rel="noopener">Original PDF</a> · '
            '<a href="' + html.escape(converted, quote=True) + '">Converted text</a></li>')


def section_link(title: str, converted: str, page_label: str, anchor: str = "") -> str:
    identifier = ' id="' + html.escape(anchor, quote=True) + '"' if anchor else ""
    return ('<li' + identifier + '>' + html.escape(title) + ' — ' + html.escape(page_label) + ' — '
            '<a href="' + html.escape(converted, quote=True) + '">Converted text</a></li>')


def snp_partition(text: str) -> list[dict]:
    """Partition source intervals exactly; do not call them approved website suttas."""
    pages = text.split("\f")
    if pages[-1].strip() == "":
        pages.pop()
    if len(pages) != 391:
        raise ValueError("Pinned Sutta Nipāta must have 391 PDF pages")
    headers = list(re.finditer(r"(?m)^[ \t]*Snp\.[ \t]*(\d+\.\d+)[ \t]*$", text))
    expected = [f"{book}.{number}" for book, count in enumerate((12, 14, 12, 16, 19), 1)
                for number in range(1, count + 1)]
    if [m[1] for m in headers] != expected:
        raise ValueError("Sutta Nipāta source references are missing, repeated or reordered")
    covers = list(re.finditer(r"(?m)^Book (One|Two|Three|Four|Five)[ \t]*$", text))
    if [m[1] for m in covers] != ["One", "Two", "Three", "Four", "Five"]:
        raise ValueError("Sutta Nipāta book-cover boundaries changed")
    endings = list(re.finditer(r"(?m)^List of Suttas[ \t]*$", text))
    if len(endings) != 1 or text[:endings[0].start()].count("\f") + 1 != 386:
        raise ValueError("Sutta Nipāta back-matter boundary changed")
    markers = [(0, "front-matter", "FRONT_MATTER", "Front matter")]
    markers += [(m.start(), "book-" + str(n), "BOOK_DIVIDER", "Book " + m[1])
                for n, m in enumerate(covers, 1)]
    for match in headers:
        following = [line.strip() for line in text[match.end():].splitlines() if line.strip()]
        title = f"Snp. {match[1]} — {following[0]}"
        markers.append((match.start(), "snp" + match[1], "SUTTA_SOURCE_INTERVAL", title))
    markers.append((endings[0].start(), "back-matter", "BACK_MATTER", "List of Suttas and end matter"))
    markers.sort()
    units = []
    for i, (start, key, kind, title) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else len(text)
        body = text[start:end]
        units.append({"id": key, "kind": kind, "title": title, "body": body,
                      "start_character": start, "end_character": end,
                      "first_pdf_page": text[:start].count("\f") + 1,
                      "last_pdf_page": min(391, text[:max(start, start + len(body.rstrip()) - 1)].count("\f") + 1),
                      "sha256": hashlib.sha256(body.encode()).hexdigest(),
                      "canonical_mapping_status": "PROPOSED_NOT_APPROVED", "publishable": False})
    if "".join(unit["body"] for unit in units) != text:
        raise ValueError("Source partition omitted, duplicated or changed characters")
    return units


def compact(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", text))


def numeric_movement(left: str, right: str) -> dict:
    """Diagnostic classification, never permission to remove or reposition numbers."""
    a, b = compact(left), compact(right)
    changes = [{"operation": op, "left": a[i:j], "right": b[k:l],
                "left_context": a[max(0, i - 35):min(len(a), j + 35)],
                "right_context": b[max(0, k - 35):min(len(b), l + 35)]}
               for op, i, j, k, l in SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
               if op != "equal"]
    insertions = [r["right"] for r in changes if r["operation"] == "insert"]
    deletions = [r["left"] for r in changes if r["operation"] == "delete"]
    numeric_only = bool(changes) and all(
        r["operation"] in {"insert", "delete"} and (r["left"] or r["right"]).isascii()
        and (r["left"] or r["right"]).isdigit() for r in changes
    ) and Counter(insertions) == Counter(deletions)
    return {"classification": "NUMERIC_TOKEN_RELOCATION" if numeric_only else "OTHER_CHARACTER_DIFFERENCE",
            "changes": changes, "human_confirmation": "Confirm number placement against the PDF; do not delete it.",
            "publication_approval": False}


def resource_outputs(sha: str, mupdf: str, raw: str | None, raw_comparison: dict | None) -> tuple[dict, dict]:
    """Return only private outputs. Exact source bytes are checked by the caller."""
    outputs, report = {}, {}
    if sha == SNP_SHA:
        units = snp_partition(mupdf)
        metadata = [{k: v for k, v in unit.items() if k != "body"} for unit in units]
        report = {"kind": "SUTTA_NIPATA_SOURCE_PARTITION", "sutta_source_intervals": 73,
                  "all_source_characters_preserved": True, "canonical_mapping_status": "NOT_APPROVED",
                  "human_checks": ["Verse and reading order", "Word/paragraph boundaries and diacritics",
                                   "Start/end boundaries, chapter dividers and page numbers", "Canonical ID correspondence"],
                  "units": metadata, "publishable": False}
        body = ('<p>Choose a sutta. Open the original and converted text side by side.</p>'
                '<p><a href="../../index.html">All texts</a> · '
                '<a href="source.pdf" target="_blank" rel="noopener">Original PDF — whole book</a></p><ol>')
        extra = []
        for unit in units:
            path = "source-units/" + unit["id"] + ".txt"
            outputs[path] = unit["body"].encode()
            readable = "source-units/" + unit["id"] + ".html"
            pages = f'PDF pages {unit["first_pdf_page"]}–{unit["last_pdf_page"]}'
            outputs[readable] = reading_html(unit["title"], unit["body"],
                                            "../source.pdf#page=" + str(unit["first_pdf_page"]),
                                            "../source-units.html", pages)
            pair = section_link(unit["title"], readable, pages, unit["id"])
            if unit["kind"] == "SUTTA_SOURCE_INTERVAL":
                body += pair
            else:
                extra.append(pair)
        body += ('</ol><details><summary>Front matter, book dividers and end matter</summary><ul>'
                 + ''.join(extra) + '</ul></details><p><a href="details.html">Technical details</a></p>')
        outputs["source-units.html"] = document("Sutta Nipāta — 73 suttas", body)
    elif sha == MANUAL_SHA and raw is not None and raw_comparison is not None:
        a, b = raw.split("\f"), mupdf.split("\f")
        rows = [{"pdf_page": n, **numeric_movement(a[n - 1], b[n - 1])}
                for n in raw_comparison["mismatched_pages"]]
        report = {"kind": "MANUAL_READING_ORDER_DIAGNOSTIC", "pages": rows,
                  "counts": dict(Counter(row["classification"] for row in rows)),
                  "publishable": False, "human_confirmation": "Verify footnote-marker positions and text flow visually."}
        body = ('<p>Private diagnostic. These are differences between converters, not author errors. '
                'A moved numeric token may be a footnote marker; only the original PDF can confirm it. '
                'No numbers or words have been removed, repaired or repositioned.</p>'
                '<p><a href="index.html">Source details</a></p><ol>')
        for row in rows:
            n = row["pdf_page"]
            body += (f'<li id="pdf-page-{n}"><h2>PDF page {n}</h2><p>{row["classification"]}. '
                     f'<a href="source.pdf#page={n}">Original PDF</a> · '
                     f'<a href="comparison.html#pdf-page-{n}">Full marked comparison</a></p><pre>'
                     + html.escape(json.dumps(row["changes"], ensure_ascii=False, indent=2)) + '</pre></li>')
        outputs["source-units.html"] = document("The Manual — unresolved number placement", body + '</ol>')
    if report:
        outputs["resource-review.json"] = json_data(report)
    return outputs, report
