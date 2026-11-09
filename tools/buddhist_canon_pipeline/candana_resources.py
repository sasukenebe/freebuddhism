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
SNP_TEXT_SHA = "fb1e36fb23c076949b15aaa3c5e738342ead95a924e376837e2921da58481087"
MANUAL_TEXT_SHA = "951f67c7671d1f900ade79f21b5b3dc602c7ea07732a0adf74dca2e9525c20b4"
MANUAL_STARTS = (
    ("front-matter", "Front matter", 1), ("preface", "Preface", 13),
    ("introduction", "Introduction", 19),
    ("individual-journey", "Buddha’s Path: Each Individual’s Own Journey", 25),
    ("four-noble-truths", "The Four Noble Truths", 29),
    ("mindfulness", "The Problem with “Mindfulness” Today", 47),
    ("precepts", "Laying the Foundations: Requesting and Taking the Precepts", 59),
    ("hindrances", "Dealing with Obstacles: Hindrances on the Path", 95),
    ("forgiveness", "Forgiveness Through Wisdom", 111),
    ("brahmavihara", "Brahmavihāra: Higher States of Being", 137),
    ("metta", "Mettā: Loving Kindness Meditation", 153),
    ("awakening-factors", "More on The Seven Factors of Awakening", 181),
    ("causal-relations", "Paṭiccasamuppāda: The Twelve Links of Causal Relations", 191),
    ("dedication", "Dedication of Merits", 209),
)
# Exact-source layout recipe: centered small numerals below y=560 PDF points.
# These are not guessed from body digits; index references are never folios.
SNP_FOLIOS = (9, 18, 22, 26, 33, 39, 47, 58, 64, 69, 73, 78, 84, 88, 90, 94,
              97, 100, 108, 111, 114, 116, 118, 123, 128, 135, 138, 142, 147,
              151, 161, 170, 183, 200, 204, 218, 228, 238, 262, 266, 268, 270,
              272, 274, 277, 280, 283, 288, 291, 296, 300, 311, 316, 321, 324,
              334, 337, 340, 343, 348, 351, 355, 360, 362, 364, 368, 370, 372,
              374, 376, 378, 380, 385)


def json_data(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def document(title: str, body: str) -> bytes:
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>' + html.escape(title) + '</title><style>'
            'pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere}'
            '.source-folio{font-size:.8em;color:#555;border-top:1px solid #ccc}'
            '.source-index{border-collapse:collapse}'
            '.source-index td{vertical-align:top;padding:.15em 1em .15em 0}'
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
                 back: str = "../../index.html", pages: str = "", *, rendered: str | None = None) -> bytes:
    """A readable private draft; retain source characters, not PDF-width wrapping."""
    label = "Original PDF" + (" (" + pages + ")" if pages else "")
    body = ('<p><a href="' + html.escape(back, quote=True) + '">All texts</a> · '
            '<a href="' + html.escape(pdf, quote=True) + '" target="_blank" rel="noopener">'
            + html.escape(label) + '</a></p><h2>Converted text</h2>'
            + (reading_body(text) if rendered is None else rendered))
    return document(title, body)


def snp_reading_body(unit: dict) -> str:
    """Presentation-only recipe for the frozen 391-page source, not arbitrary PDFs.

    Keep raw order and every source character. Only the 17 explicitly identified
    Snake refrains gain authored breaks; other stanza gaps retain their source
    spacing without claiming that all verse layout has been visually reviewed.
    """
    pieces = []
    index_rows = 0
    for page_number, page in enumerate(unit["body"].split("\f"), unit["first_pdf_page"]):
        if not page.strip():
            continue
        folio = ""
        if page_number in SNP_FOLIOS:
            match = re.search(rf"(?m)^[ \t]*{page_number}[ \t]*\n*\Z", page)
            if match is None:
                raise ValueError(f"Pinned printed folio missing on PDF page {page_number}")
            page, folio = page[:match.start()], str(page_number)
        if 386 <= page_number <= 388:
            pending, table = [], False
            for line in (line.strip() for line in page.splitlines() if line.strip()):
                if line == "List of Suttas" or line.endswith("Vagga"):
                    if pending:
                        raise ValueError("Unpaired source index title")
                    if table:
                        pieces.append('</table>')
                        table = False
                    pieces.append('<p>' + html.escape(line) + '</p>')
                elif line.isascii() and line.isdigit():
                    if not pending:
                        raise ValueError("Source index page reference has no title")
                    if not table:
                        pieces.append('<table class="source-index" aria-label="Sutta titles and printed page references">')
                        table = True
                    pieces.append('<tr><td>' + html.escape(' '.join(pending)) + '</td><td>'
                                  + line + '</td></tr>')
                    pending = []
                    index_rows += 1
                else:
                    pending.append(line)
            if pending:
                raise ValueError("Source index ends with an unpaired title")
            if table:
                pieces.append('</table>')
        else:
            for part in re.split(r"\n[ \t]*\n+", page):
                if not part.strip():
                    continue
                lines = re.split(r"(?m)\n(?=“?Thus, the Bhikkhu)", part) if unit["id"] == "snp1.1" else [part]
                pieces.append('<p>' + '<br>'.join(html.escape(' '.join(line.split()))
                                               for line in lines if line.strip()) + '</p>')
        if folio:
            pieces.append('<p class="source-folio">' + folio
                          + ' <span class="editorial">[printed page number]</span></p>')
    if unit["id"] == "back-matter" and index_rows != 73:
        raise ValueError("Pinned source index must retain all 73 title/page pairs")
    result = ''.join(pieces)
    source_only = re.sub(r'<span class="editorial">.*?</span>', '', result)
    shown = html.unescape(re.sub(r'<[^>]*>', ' ', source_only))
    if re.sub(r"\s+", "", shown) != re.sub(r"\s+", "", unit["body"]):
        raise ValueError("Sutta Nipāta layout changed source characters")
    return '<div class="converted-text">' + result + '</div>'


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


def manual_partition(text: str) -> list[dict]:
    """Exact, private chapter intervals; not a correction of drop caps or footnotes."""
    pages = text.split('\f')
    if not pages[-1].strip():
        pages.pop()
    if len(pages) != 214:
        raise ValueError("Pinned English Manual must contain 214 pages")
    offsets = [0] + [match.end() for match in re.finditer('\f', text)]
    units = []
    for index, (key, title, first) in enumerate(MANUAL_STARTS):
        if key != 'front-matter' and not ' '.join(pages[first - 1].split()).startswith(title):
            raise ValueError("Manual chapter heading moved or changed: " + key)
        last = MANUAL_STARTS[index + 1][2] - 1 if index + 1 < len(MANUAL_STARTS) else 214
        start = offsets[first - 1]
        end = offsets[last] if last < 214 else len(text)
        body = text[start:end]
        units.append({'id': key, 'title': title, 'first_pdf_page': first, 'last_pdf_page': last,
                      'start_character': start, 'end_character': end, 'body': body,
                      'sha256': hashlib.sha256(body.encode()).hexdigest(), 'publishable': False})
    if ''.join(unit['body'] for unit in units) != text:
        raise ValueError("Manual chapter partition changed raw text")
    return units


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
        pinned_layout = hashlib.sha256(mupdf.encode()).hexdigest() == SNP_TEXT_SHA
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
                                            "../source-units.html", pages,
                                            rendered=snp_reading_body(unit) if pinned_layout else None)
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
        if hashlib.sha256(mupdf.encode()).hexdigest() == MANUAL_TEXT_SHA:
            units = manual_partition(mupdf)
            report['source_intervals'] = [{k: v for k, v in unit.items() if k != 'body'} for unit in units]
            report['chapter_sections'] = 12
            report['remaining_layout'] = ['20 footnote-number placement disagreements',
                                          'Detached drop caps and paragraph flow require source-specific review']
            links = ('<p>Private chapter drafts, not approved readers. Drop caps, note markers and '
                     'paragraph layout still need review. No source characters have been repaired.</p>'
                     '<p><a href="../../index.html">All texts</a> · '
                     '<a href="source.pdf">Original PDF — whole book</a> · '
                     '<a href="source-units.html">Flagged number placement</a></p><ol>')
            for unit in units:
                prefix = 'manual-units/' + unit['id']
                pages = f'PDF pages {unit["first_pdf_page"]}–{unit["last_pdf_page"]}'
                outputs[prefix + '.txt'] = unit['body'].encode()
                outputs[prefix + '.html'] = reading_html(unit['title'], unit['body'],
                                                        '../source.pdf', '../manual-chapters.html', pages)
                links += section_link(unit['title'], prefix + '.html', pages)
            outputs['manual-chapters.html'] = document('The Manual — chapter drafts', links + '</ol>')
    if report:
        outputs["resource-review.json"] = json_data(report)
    return outputs, report
