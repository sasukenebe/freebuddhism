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
        body = ('<p>Private source intervals, not approved sutta readers. All MuPDF characters, '
                'including page numbers and wraps, remain unchanged. Front matter, book dividers '
                'and back matter are separate. No automatic website import.</p>'
                '<p><a href="index.html">Source details</a> · '
                '<a href="comparison.html">All differences</a></p>')
        body += '<ul>' + ''.join(f'<li><a href="#{u["id"]}">{html.escape(u["title"])}</a></li>' for u in units) + '</ul>'
        for unit in units:
            path = "source-units/" + unit["id"] + ".txt"
            outputs[path] = unit["body"].encode()
            body += (f'<section id="{unit["id"]}"><h2>{html.escape(unit["title"])}</h2>'
                     f'<p>PDF pages {unit["first_pdf_page"]}–{unit["last_pdf_page"]}; {unit["kind"]}. '
                     f'<a href="source.pdf#page={unit["first_pdf_page"]}">Original PDF</a> · '
                     f'<a href="{path}">Unchanged source text</a></p><pre>'
                     + html.escape(unit["body"]) + '</pre></section>')
        outputs["source-units.html"] = document("Sutta Nipāta — 73 proposed source sections", body)
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
