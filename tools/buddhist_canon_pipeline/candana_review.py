#!/usr/bin/env python3
"""Private Candana review output: preserve raw text and enumerate every detected difference."""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import hashlib
import html
import re
import unicodedata
from urllib.parse import unquote, urlsplit


def pages(text: str) -> list[str]:
    result = text.split("\f")
    if len(result) > 1 and not result[-1].strip():
        result.pop()
    return result


def characters(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", text))


def words(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def spacing_pages(left: str, right: str, pagination_only=()) -> list[int]:
    """Mark word-boundary differences, not changes in the number of wrap spaces."""
    excluded = set(pagination_only)
    return [number for number, (a, b) in enumerate(zip(pages(left), pages(right)), 1)
            if number not in excluded and characters(a) == characters(b) and words(a) != words(b)]


def marked_pair(left: str, right: str) -> tuple[str, str]:
    """Highlight differing whole tokens while leaving every original character intact."""
    a, b = [list(re.finditer(r"\S+", text)) for text in (left, right)]
    spans = [[], []]
    for operation, start_a, end_a, start_b, end_b in SequenceMatcher(
        None, [m[0] for m in a], [m[0] for m in b], autojunk=False
    ).get_opcodes():
        if operation == "equal":
            continue
        for matches, start, end, target in ((a, start_a, end_a, spans[0]),
                                             (b, start_b, end_b, spans[1])):
            if start != end:
                target.append((matches[start].start(), matches[end - 1].end()))
    def render(text, ranges):
        result, position = [], 0
        for start, end in ranges:
            result.extend((html.escape(text[position:start]),
                           "<mark>" + html.escape(text[start:end]) + "</mark>"))
            position = end
        result.append(html.escape(text[position:]))
        return "".join(result)
    return render(left, spans[0]), render(right, spans[1])


def page_reviews(left: str, right: str, comparison: dict, raw: str | None,
                 hyphens: list[dict]) -> list[dict]:
    a, b = pages(left), pages(right)
    c = pages(raw) if raw is not None else []
    layout_spacing = set(spacing_pages(left, right, comparison.get("pagination_only_pages", [])))
    raw_spacing = set(spacing_pages(raw, right)) if raw is not None else set()
    primary = set(comparison["mismatched_pages"])
    pagination = set(comparison.get("pagination_only_pages", []))
    hyphen_pages = {row["page"] for row in hyphens}
    result = []
    for number in range(1, max(len(a), len(b), len(c)) + 1):
        x = a[number - 1] if number <= len(a) else None
        y = b[number - 1] if number <= len(b) else None
        z = c[number - 1] if number <= len(c) else None
        flags = []
        if number in primary:
            flags.append("LAYOUT_CHARACTER_DISAGREEMENT")
            if x is not None and y is not None and characters(x) == characters(y):
                flags.append("CANONICALLY_EQUIVALENT_UNICODE")
        if number in layout_spacing:
            flags.append("LAYOUT_WORD_BOUNDARY_REVIEW")
        if number in pagination:
            flags.append("RECIPE_RECOGNIZED_PAGINATION_POSITION")
        if number in hyphen_pages:
            flags.append("HYPHEN_WRAP_REVIEW")
        if x is None or y is None or (raw is not None and z is None):
            flags.append("MISSING_EXTRACTED_PAGE")
        if z is not None and y is not None and characters(z) != characters(y):
            flags.append("RAW_CHARACTER_DISAGREEMENT")
        if number in raw_spacing:
            flags.append("RAW_WORD_BOUNDARY_REVIEW")
        if flags:
            result.append({"page": number, "flags": flags,
                           "review_anchor": f"comparison.html#pdf-page-{number}"})
    return result


def comparison_html(title: str, left: str, right: str, raw: str | None,
                    rows: list[dict]) -> str:
    streams = [pages(left), pages(right), pages(raw) if raw is not None else []]
    out = ['<p>Private review, not approved text. All detected page differences are listed. '
           'Highlighting marks differences, not a proposed correction. '
           'Unhighlighted text is not certified accurate.</p>',
           '<p><a href="index.html">Text draft and source details</a> · '
           '<a href="source.pdf">Original PDF, local copy</a></p>']
    out.append('<ul>' + "".join(
        f'<li><a href="#pdf-page-{r["page"]}">PDF page {r["page"]}</a>: '
        + html.escape(", ".join(r["flags"])) + "</li>" for r in rows) + "</ul>")
    if not rows:
        out.append("<p>No differences detected by these comparisons. Visual and numbering review remain required.</p>")
    for row in rows:
        number = row["page"]
        text = [stream[number - 1] if number <= len(stream) else "" for stream in streams]
        left_marked, right_marked = marked_pair(text[0], text[1])
        out.append(f'<section id="pdf-page-{number}"><h2>PDF page {number}</h2>'
                   f'<p><a href="source.pdf#page={number}">Compare original PDF page {number}</a></p>'
                   '<p>' + html.escape(", ".join(row["flags"])) + "</p>")
        out.append('<details><summary>Layout extraction versus MuPDF</summary>'
                   '<h3>Poppler layout</h3><pre>' + left_marked + '</pre>'
                   '<h3>MuPDF</h3><pre>' + right_marked + '</pre></details>')
        if raw is not None:
            raw_marked, reference_marked = marked_pair(text[2], text[1])
            out.append('<details><summary>Raw extraction versus MuPDF</summary>'
                       '<h3>Poppler raw</h3><pre>' + raw_marked + '</pre>'
                       '<h3>MuPDF</h3><pre>' + reference_marked + '</pre></details>')
        out.append("</section>")
    return document(title + " — marked differences", "".join(out))


def document(title: str, body: str) -> str:
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>' + html.escape(title) + '</title><style>'
            'pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere}'
            'summary{cursor:pointer}mark{background:#ffde80;color:#000}'
            '</style></head><body><h1>' + html.escape(title) + '</h1>'
            + body + '</body></html>\n')


def inventory(jobs: list[dict], reports: list[dict]) -> list[dict]:
    by_url = {r["source_url"]: r for r in reports}
    if len(by_url) != len(reports):
        raise ValueError("Duplicate source reports")
    result, seen = [], set()
    for job in sorted(jobs, key=lambda r: r["url"]):
        url = job["url"]
        if url in seen:
            raise ValueError("Duplicate queue URL")
        seen.add(url)
        row = by_url.get(url)
        is_pdf = (job.get("cache", "").endswith(".pdf")
                  or urlsplit(url).path.casefold().endswith(".pdf"))
        key = hashlib.sha256(url.encode()).hexdigest()
        result.append({
            "source_url": url,
            "title": row["title"] if row else unquote(urlsplit(url).path.rsplit("/", 1)[-1]) or url,
            "kind": "MISSING_SOURCE" if job["state"] == "MISSING" else "PDF_DRAFT" if is_pdf else "DISCOVERY_PAGE",
            "collection_state": job["state"],
            "http_status": job.get("http_status"),
            "review_state": row["status"] if row else "WAITING_THIS_PASS" if is_pdf and job["state"] != "MISSING" else "NOT_A_TEXT_DRAFT",
            "review_path": row.get("review_path") if row else None,
            "comparison_path": f"sources/{key}/comparison.html" if row and "comparison.html" in row.get("output_hashes", {}) else None,
            "local_pdf_path": f"sources/{key}/source.pdf" if row and "source.pdf" in row.get("output_hashes", {}) else None,
            "text_paths": {name: f"sources/{key}/{name}" for name in ("poppler.txt", "mupdf.txt", "poppler-raw.txt")
                           if row and name in row.get("output_hashes", {})},
            "issues": list(row.get("issues", [])) if row else [],
            "page_reviews": row.get("page_reviews", []) if row else [],
            "rights": row.get("rights", "NOT_REVIEWED") if row else job.get("rights", "NOT_REVIEWED"),
            "publishable": False,
        })
    return result


def review_catalog(rows: list[dict]) -> tuple[str, str, str]:
    counts = Counter(row["kind"] for row in rows)
    summary = (f'{len(rows)} discovered sources: {counts["PDF_DRAFT"]} PDF drafts, '
               f'{counts["MISSING_SOURCE"]} missing sources, {counts["DISCOVERY_PAGE"]} discovery pages.')
    preface = ('<p>' + summary + '</p><p>Private raw-text review only. No automatic publication. '
               'Permission, numbering and layout holds are independent of converter agreement.</p>'
               '<p><a href="disagreements.html">All marked disagreements</a> · '
               '<a href="review-list.txt">Complete plain-text list</a> · '
               '<a href="inventory.json">Complete machine-readable inventory</a></p>')
    all_items, flagged, plain = [], [], [summary, "", "PRIVATE DRAFTS — NOT APPROVED FOR PUBLICATION", ""]
    for number, row in enumerate(rows, 1):
        title = html.escape(row["title"])
        label = f'<a href="{row["review_path"]}">{title}</a>' if row["review_path"] else title
        controls = [f'<a href="{html.escape(row["source_url"], quote=True)}">Publisher source</a>']
        if row["local_pdf_path"]:
            controls.append(f'<a href="{row["local_pdf_path"]}">Original PDF, local copy</a>')
        controls.extend(f'<a href="{path}">{name}</a>' for name, path in row["text_paths"].items())
        if row["comparison_path"]:
            controls.append(f'<a href="{row["comparison_path"]}">Marked differences</a>')
        details = (f'<li id="source-{number}"><h2>{number}. {label}</h2>'
                   '<p>' + html.escape(row["kind"] + "; " + row["collection_state"] + "; " + row["review_state"])
                   + '</p><p>' + " · ".join(controls) + '</p><p>'
                   + html.escape("Checks: " + (", ".join(row["issues"]) or "No automatic approval"))
                   + '</p><p>' + html.escape("Rights: " + row["rights"]) + '</p>')
        pages_html = []
        page_text = []
        for item in row["page_reviews"]:
            path = row["comparison_path"] + "#pdf-page-" + str(item["page"])
            flags = ", ".join(item["flags"])
            pages_html.append(f'<li><a href="{path}">PDF page {item["page"]}</a>: {html.escape(flags)}</li>')
            page_text.append(f'    PDF page {item["page"]}: {flags}')
        if pages_html:
            details += '<details><summary>All flagged pages</summary><ul>' + "".join(pages_html) + '</ul></details>'
            flagged.append(details + "</li>")
        all_items.append(details + "</li>")
        plain.extend((f'{number}. {row["title"]}', "  Source: " + row["source_url"],
                      "  State: " + row["collection_state"] + "; " + row["review_state"],
                      "  Rights: " + row["rights"],
                      "  Issues: " + (", ".join(row["issues"]) or "None detected; visual review required"),
                      "  Review: " + (row["review_path"] or "No current text draft"),
                      *page_text, ""))
    all_html = document("Candana — complete source and text review list",
                        preface + "<ol>" + "".join(all_items) + "</ol>")
    differences = document("Candana — all marked disagreements",
                           '<p><a href="index.html">Complete source list</a></p>'
                           '<p>All flagged pages are enumerated; no sample limit is applied. '
                           'Character, word-boundary, hyphen and known pagination flags are distinct.</p>'
                           "<ol>" + "".join(flagged) + "</ol>")
    return all_html, differences, "\n".join(plain)
