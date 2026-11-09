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
            "source_sha256": row.get("source_sha256", job.get("sha256")) if row else job.get("sha256"),
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
            "resource_review": row.get("resource_review", {}) if row else {},
            "source_sections": row.get("sections", []) if row else [],
            "resource_path": f"sources/{key}/source-units.html" if row and "source-units.html" in row.get("output_hashes", {}) else None,
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
    preface += '<p><a href="human-review.html">What needs human confirmation, by review role</a></p>'
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
        if row.get("resource_path"):
            controls.append(f'<a href="{row["resource_path"]}">Smaller source sections / targeted review</a>')
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


REVIEW_ROLES = {
    "PROOFREADER": "You or another reader fluent in the source language: compare the extracted words, verse order, accents, paragraphs and footnotes with the PDF. Report differences; do not rewrite the translation.",
    "REFERENCE_REVIEWER": "A reader familiar with the sutta numbering: confirm each source section corresponds to the proposed site text, including grouped passages and different editions.",
    "RIGHTS_REVIEWER": "The project owner: provide or confirm the exact source-specific reuse notice or publisher permission. Free access alone is insufficient. No publisher contact is sent automatically.",
    "RELEASE_OWNER": "The project owner: accept the reviewed scope, attribution and placement before a separate import or public release. Do not infer approval from converter agreement.",
    "PIPELINE_MAINTAINER": "Automation / maintainer: prepare missing layouts, investigate failed sources, preserve evidence and run tests. This is not work the owner has to code.",
}


def human_queue(rows: list[dict], context: dict | None = None) -> dict:
    context = context or {}
    tasks = []
    installed = context.get("installed_by_sha256", {})
    def add(row, code, role, confirm, priority=2, status="NEEDS_HUMAN", pages=(), evidence=None):
        identity = row.get("source_sha256") or row["source_url"]
        tasks.append({
            "id": hashlib.sha256((identity + "\n" + code).encode()).hexdigest()[:20],
            "check": code, "role": role, "status": status, "priority": priority,
            "title": row["title"], "source_url": row["source_url"],
            "source_sha256": row.get("source_sha256"), "confirm": confirm,
            "source_readers_already_imported": installed.get(row.get("source_sha256"), 0),
            "review_path": evidence or row.get("resource_path") or row.get("review_path"),
            "local_pdf_path": row.get("local_pdf_path"),
            "comparison_path": row.get("comparison_path"),
            "pages": sorted(set(pages)), "automatic_approval": False,
        })
    for row in rows:
        if row["kind"] == "MISSING_SOURCE":
            add(row, "MISSING_SOURCE", "PIPELINE_MAINTAINER",
                "Find a valid source URL without repeatedly retrying the recorded missing offer.",
                priority=4, status="MAINTAINER_WORK")
            continue
        if row["kind"] != "PDF_DRAFT":
            continue
        permission = row["rights"] == "EXPLICIT_GRANT_DETECTED"
        priority = 1 if permission and row.get("resource_path") else 2 if permission else 4
        if not permission:
            add(row, "EXACT_SOURCE_PERMISSION", "RIGHTS_REVIEWER",
                "Supply permission covering this exact PDF and text redistribution, including any attribution, free-only or no-alteration conditions.",
                priority=3)
        actionable = [p["page"] for p in row["page_reviews"]
                      if set(p["flags"]) - {"RECIPE_RECOGNIZED_PAGINATION_POSITION"}]
        add(row, "VISIBLE_TEXT_AND_LAYOUT", "PROOFREADER",
            "Compare PDF and text. Confirm no omitted, duplicated or reordered wording, broken words, altered diacritics or misplaced footnotes. Known pagination movement alone is not a text error. Full-page human verification has not been recorded.",
            priority=priority, status="NEEDS_HUMAN" if permission else "WAIT_PERMISSION", pages=actionable)
        resource = row.get("resource_review", {})
        if resource.get("kind") == "SUTTA_NIPATA_SOURCE_PARTITION":
            add(row, "SNP_SECTION_BOUNDARIES_AND_EDITION", "REFERENCE_REVIEWER",
                "Check all 73 proposed source intervals and their site correspondence. Keep book dividers, front/back matter and page numbers out of sutta bodies. Reconcile the earlier 364-page edition with this 391-page edition; do not trust the back index's page references without checking.",
                priority=1)
        elif resource.get("kind") == "MANUAL_READING_ORDER_DIAGNOSTIC":
            add(row, "MANUAL_NUMBER_PLACEMENT", "PROOFREADER",
                "All listed remaining character differences are classified individually. Confirm moved numeric tokens are footnote markers, retain every marker and note, and check its attachment and reading order against the PDF. Numeric-only movement is not approval.",
                priority=1, pages=[p["pdf_page"] for p in resource["pages"]])
            add(row, "MANUAL_AUTHOR_RESOURCE_PLACEMENT", "RELEASE_OWNER",
                "Treat The Manual as a separately labeled author resource, not an invented canonical sutta. Approve its reviewed boundaries and attribution before import.",
                priority=2)
        if permission and not installed.get(row.get("source_sha256")):
            add(row, "SOURCE_LAYOUT_RECIPE", "PIPELINE_MAINTAINER",
                "Prepare a pinned layout/import recipe after the source checks. Neither raw text nor source interval generation approves publication.",
                priority=2, status="MAINTAINER_WORK")
        if "Book-3_Anguttara" in row["source_url"]:
            held = context.get("book_three_held_source_labels", [])
            sections = {s["source_label"]: s for s in row.get("source_sections", [])}
            for label in held:
                section = sections.get(label)
                add(row, "AN3_MAPPING_" + label, "REFERENCE_REVIEWER",
                    "Confirm the exact canonical scope of source group " + label
                    + "; preserve grouped repetitions and do not apply a blanket numbering offset or split an indivisible group.",
                    priority=1, pages=[section["source_page"]] if section else [],
                    evidence=row.get("review_path") + "#source-" + label if section and row.get("review_path") else None)
    tasks.sort(key=lambda t: (t["priority"], t["source_url"], t["check"]))
    return {"schema_version": 1, "automatic_approval": False,
            "human_results_recorded": False, "roles": REVIEW_ROLES,
            "source_inventory_count": len(rows), "tasks": tasks,
            "counts_by_role": dict(Counter(t["role"] for t in tasks)),
            "counts_by_status": dict(Counter(t["status"] for t in tasks))}


def apply_human_decisions(queue: dict, ledger: dict) -> dict:
    """Preserve actual human reports separately; never change publication gates."""
    if ledger.get("schema_version") != 1 or not isinstance(ledger.get("decisions"), list):
        raise ValueError("Unknown human-decision ledger")
    tasks = {task["id"]: task for task in queue["tasks"]}
    unmatched = []
    for decision in ledger["decisions"]:
        required = ("check_id", "source_sha256", "reviewer", "date", "outcome", "scope", "evidence")
        if any(not isinstance(decision.get(k), str) or not decision[k].strip() for k in required):
            raise ValueError("Human decisions require identity, exact source hash, date, outcome, scope and evidence")
        if decision["outcome"] not in {"CONFIRMED", "NEEDS_CHANGE", "PARTIAL"} or decision["scope"] not in {"FULL_CHECK", "PARTIAL"}:
            raise ValueError("Unsupported human decision outcome or scope")
        if decision["outcome"] == "CONFIRMED" and decision["scope"] != "FULL_CHECK":
            raise ValueError("A partial review cannot confirm the full check")
        task = tasks.get(decision["check_id"])
        if task is None:
            unmatched.append(decision)
            continue
        if decision["source_sha256"] != task["source_sha256"]:
            raise ValueError("Human decision refers to different source bytes")
        task["human_report"] = decision
        task["status"] = {"CONFIRMED": "HUMAN_REPORTED_CONFIRMED", "NEEDS_CHANGE": "HUMAN_REPORTED_CHANGE_NEEDED",
                          "PARTIAL": "PARTIAL_HUMAN_REVIEW"}[decision["outcome"]]
    queue["human_results_recorded"] = bool(ledger["decisions"])
    queue["human_decision_records"] = len(ledger["decisions"])
    queue["unmatched_decisions_preserved"] = unmatched
    queue["counts_by_status"] = dict(Counter(t["status"] for t in queue["tasks"]))
    return queue


def human_queue_views(queue: dict) -> tuple[str, str]:
    intro = ('<p><a href="index.html">Complete source list</a> · '
             '<a href="disagreements.html">All marked differences</a> · '
             '<a href="human-review.txt">Plain-text checklist</a> · '
             '<a href="human-review.json">Structured checklist</a></p>'
             '<p>Automatic preparation is not human verification. Stable check IDs identify the exact source hash and question. '
             'Send findings with that ID, PDF page, observation and reviewer; do not edit generated '
             'files, which the timer refreshes. Actual findings are retained separately in human-decisions.json; '
             'the generator never invents or overwrites them. A recorded human finding does not automatically approve publication.</p>')
    intro += '<p>' + str(queue.get("human_decision_records", 0)) + ' human decision records; '
    intro += str(len(queue.get("unmatched_decisions_preserved", []))) + ' older/unmatched records retained for reconciliation.</p>'
    out = [intro, '<h2>Who checks what</h2><ul>']
    plain = ["CANDANA — HUMAN CONFIRMATION CHECKLIST", "No automatic approval. Human decision records: "
             + str(queue.get("human_decision_records", 0)), ""]
    for role, instruction in queue["roles"].items():
        out.append('<li><strong>' + role + '</strong>: ' + html.escape(instruction) + '</li>')
        plain.extend((role + ": " + instruction, ""))
    out.append('</ul><h2>Checks, in priority order</h2>')
    for task in queue["tasks"]:
        title = html.escape(task["title"])
        out.append(f'<section id="check-{task["id"]}"><h3>{task["role"]}: {title}</h3>'
                   + '<p>' + html.escape(task["status"] + "; check " + task["id"] + "; " + task["check"]) + '</p>'
                   + '<p>' + html.escape(task["confirm"]) + '</p>')
        if task["source_readers_already_imported"]:
            out.append(f'<p>{task["source_readers_already_imported"]} source readers already imported; this is not a new claim of full human proofreading or public deployment.</p>')
        if task.get("human_report"):
            out.append('<p>Recorded human report: ' + html.escape(str(task["human_report"])) + '</p>')
        links = [('Publisher source', task["source_url"]), ('Text / review evidence', task["review_path"]),
                 ('Original PDF, local copy', task["local_pdf_path"])]
        out.append('<p>' + ' · '.join('<a href="' + html.escape(url, quote=True) + '">' + label + '</a>'
                                     for label, url in links if url) + '</p>')
        if task["pages"] and task["local_pdf_path"]:
            pages = []
            for number in task["pages"]:
                pdf = task["local_pdf_path"] + "#page=" + str(number)
                entry = f'<a href="{pdf}">PDF {number}</a>'
                if task["comparison_path"]:
                    entry += f' / <a href="{task["comparison_path"]}#pdf-page-{number}">marked text</a>'
                pages.append('<li>' + entry + '</li>')
            out.append('<details><summary>Every flagged page for this check</summary><ul>' + ''.join(pages) + '</ul></details>')
        out.append('</section>')
        plain.extend((task["id"] + " — " + task["role"] + " — " + task["status"],
                      task["title"], "Source SHA-256: " + str(task["source_sha256"]),
                      "Source: " + task["source_url"], task["confirm"],
                      "PDF pages: " + (", ".join(map(str, task["pages"])) or "Whole-source / scope check"), ""))
    return document("Candana — what needs human confirmation", ''.join(out)), "\n".join(plain)
