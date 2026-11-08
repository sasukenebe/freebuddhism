#!/usr/bin/env python3
"""Prepare reproducible PRIVATE review drafts from cached PDFs, without network or publication."""

from __future__ import annotations

import argparse
from collections import Counter
import fcntl
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import unicodedata
from urllib.parse import unquote, urlsplit

if __package__:
    from .import_candana import ROOT, granted_notice
    from .candana_queue import checked_url
else:
    from import_candana import ROOT, granted_notice
    from candana_queue import checked_url

RECIPES = ROOT / "metadata/candana-batch-recipes.json"
QUEUE = ROOT / "build/candana-audit/queue.json"
OUTPUT = ROOT / "build/candana-batch-review"
MARKER = ".candana-private-review.json"
MARKER_VALUE = {"kind": "candana-private-review", "automatic_publication": False}
HEADING = re.compile(
    r"(?m)^[ \t]*(\d+)([a-z]?)(?:[ \t]*[-–][ \t]*(\d+))?\.[ \t]*"
    r"((?:[^\n]*\bSutta\b[^\n]*)?)$"
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def safe_relative(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or "\\" in value:
        raise ValueError("Unsafe relative path")
    path = root / relative
    if any(part.is_symlink() for part in [path, *path.parents] if part != root.parent):
        raise ValueError("Symlinks are not accepted")
    path.resolve().relative_to(root.resolve())
    return path


def write_file(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlink")
    temporary = path.with_name(path.name + ".pending")
    if temporary.is_symlink():
        raise ValueError("Refusing a symlink temporary file")
    temporary.write_bytes(body)
    temporary.replace(path)


def pdf_text(path: Path, engine: str) -> str:
    if engine in {"poppler", "poppler-raw"}:
        command = ["pdftotext", "-raw" if engine == "poppler-raw" else "-layout", str(path), "-"]
    elif engine == "mupdf":
        command = ["mutool", "draw", "-F", "txt", "-o", "-", str(path)]
    else:
        raise ValueError("Unknown extraction engine")
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=30).stdout


def pages_of(text: str) -> list[str]:
    pages = text.split("\f")
    if len(pages) > 1 and not pages[-1].strip():
        pages.pop()
    return pages


def nonspace(text: str) -> str:
    # Do not normalize ligatures, punctuation or accents into apparent agreement.
    return re.sub(r"\s+", "", text)


def page_without_label(text: str, number: int) -> str | None:
    """Recognize one edge pagination label, not arbitrary body digits."""
    labels = list(re.finditer(rf"(?m)^[ \t]*{number}[ \t]*$", text))
    if len(labels) != 1:
        return None
    label = labels[0]
    if text[:label.start()].strip() and text[label.end():].strip():
        return None
    return text[:label.start()] + text[label.end():]


def engine_comparison(left: str, right: str, pagination: bool = False) -> dict:
    a, b = pages_of(left), pages_of(right)
    mismatches, pagination_only = [], []
    for number, (x, y) in enumerate(zip(a, b), 1):
        if nonspace(x) == nonspace(y):
            continue
        xx = page_without_label(x, number) if pagination else None
        yy = page_without_label(y, number) if pagination else None
        if xx is not None and yy is not None and nonspace(xx) == nonspace(yy):
            pagination_only.append(number)
        else:
            mismatches.append(number)
    if len(a) != len(b):
        mismatches.extend(range(min(len(a), len(b)) + 1, max(len(a), len(b)) + 1))
    return {"poppler_pages": len(a), "mupdf_pages": len(b), "mismatched_pages": mismatches,
            "pagination_only_pages": pagination_only,
            "comparison": "Exact ordered Unicode characters, ignoring whitespace; pinned book recipes also recognize one edge page-number label"}


def reflow(body: str, join_hyphen_wraps: bool = False) -> str:
    original = body
    if join_hyphen_wraps:
        # Keep the printed hyphen. Remove one physical wrap, never a paragraph break.
        body = re.sub(r"([^\W\d_]+(?:-[^\W\d_]+)*-)\n[ \t]*([^\W\d_]+)", r"\1\2", body)
    paragraphs = re.split(r"\n[ \t]*\n+", body.strip())
    result = "\n\n".join(" ".join(part.split()) for part in paragraphs if part.strip()) + "\n"
    if nonspace(result) != nonspace(original):
        raise ValueError("Reflow changed a non-whitespace character")
    return result


def canonical_comparison(left: str, right: str) -> dict:
    """Diagnostic only: canonical Unicode equivalence, never compatibility folding."""
    result = engine_comparison(unicodedata.normalize("NFC", left),
                               unicodedata.normalize("NFC", right))
    result["normalization"] = "NFC only; no compatibility folding, punctuation repair or reordering"
    result["publication_approval"] = False
    return result


def numbered_book(text: str, recipe: dict) -> dict:
    """Partition only a fully continuous source sequence; never repair or renumber it."""
    if recipe.get("layout") != "numbered-an-book":
        raise ValueError("Unreviewed layout recipe")
    pages = pages_of(text)
    first, last = recipe["first_page"], recipe["last_page"]
    if len(pages) != recipe["page_count"] or not 1 <= first <= last <= len(pages):
        raise ValueError("PDF page count or translation boundaries changed")
    pieces, page_starts, offset, removed = [], [], 0, []
    for number in range(first, last + 1):
        lines = pages[number - 1].splitlines()
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and lines[-1].strip() == str(number):
            lines.pop()
            removed.append(number)
        part = "\n".join(lines).rstrip() + "\n\n"
        page_starts.append((offset, number))
        pieces.append(part)
        offset += len(part)
    body = "".join(pieces)
    if body.count(recipe["closing_marker"]) != 1 or recipe["closing_marker"] not in pages[last - 1]:
        raise ValueError("Missing, duplicate or moved end-of-translation marker")
    body = body.split(recipe["closing_marker"], 1)[0].rstrip() + "\n"
    if not re.match(r"\s*" + re.escape(recipe["running_heading"]) + r"\s*\n", body):
        raise ValueError("Unexpected first translation-page heading")
    all_headings = re.compile(r"(?m)^[ \t]*(\d+)([a-z]?)(?:[ \t]*[-–][ \t]*(\d+))?\.[ \t]*([^\n]*)$")
    extras = recipe.get("untitled_numbered_headings", {})
    headings = [match for match in all_headings.finditer(body)
                if not match[4] or re.search(r"\bSutta\b", match[4])
                or extras.get(match[1] + match[2]) == match[4]]
    suffixes = recipe.get("suffix_numbers", {})
    expected_labels = [f"{number}{suffix}" for number in range(1, recipe["expected_last_number"] + 1)
                       for suffix in suffixes.get(str(number), [""])]
    observed = []
    problems = []
    for heading in headings:
        start, end = int(heading[1]), int(heading[3] or heading[1])
        if end < start or (heading[2] and heading[3]):
            problems.append({"found": heading[0].strip(), "reason": "Invalid source range"})
        observed.extend([heading[1] + heading[2]] if heading[2] else [str(n) for n in range(start, end + 1)])
    if observed != expected_labels:
        first_difference = next((i for i, pair in enumerate(zip(observed, expected_labels)) if pair[0] != pair[1]),
                                min(len(observed), len(expected_labels)))
        problems.append({"expected": expected_labels[first_difference:first_difference + 5],
                         "found": observed[first_difference:first_difference + 5],
                         "expected_count": len(expected_labels), "found_count": len(observed)})
    if not headings:
        problems.append({"reason": "No numbered headings"})
    join_wraps = recipe.get("hyphen_wrap_policy") == "retain-hyphen-join-single-wrap"
    if problems:
        return {"status": "NUMBERING_REVIEW_REQUIRED", "numbering_exceptions": problems,
                "detected_headings": len(headings), "sections": [], "body": reflow(body, join_wraps),
                "footer_pages_removed": removed}
    starts = [heading.start() for heading in headings]
    for index, heading in enumerate(headings):
        page_start = next(offset for offset, _ in reversed(page_starts) if offset <= heading.start())
        prefix = body[page_start:heading.start()]
        if re.match(r"\s*" + re.escape(recipe["running_heading"]) + r"\s*\n", prefix):
            if not any(page_start <= old.start() < heading.start() for old in headings):
                starts[index] = page_start
        # A subsection heading belongs to the next sutta, not to the preceding one.
        if index:
            previous_end = headings[index - 1].end()
            between = body[previous_end:heading.start()]
            chapter = re.search(r"(?m)^[ \t]{6,}[^\n]*Vagga[ \t]*$", between)
            if chapter:
                starts[index] = min(starts[index], previous_end + chapter.start())
    starts[0] = 0  # Preserve the opening collection/chapter headings as well.
    sections = []
    for index, heading in enumerate(headings):
        end = starts[index + 1] if index + 1 < len(starts) else len(body)
        raw = body[starts[index]:end]
        if not raw.strip() or not re.search(r"[A-Za-z]{3}", body[heading.end():end]):
            raise ValueError("Empty numbered source unit")
        number, last_number = int(heading[1]), int(heading[3] or heading[1])
        label = heading[1] + heading[2] if number == last_number else f"{number}-{last_number}"
        page = next(number for offset, number in reversed(page_starts) if offset <= heading.start())
        sections.append({"source_label": label, "title": heading[0].strip(), "source_page": page,
                         "first": number, "last": last_number, "body": reflow(raw, join_wraps)})
    if nonspace("".join(section["body"] for section in sections)) != nonspace(body):
        raise ValueError("Section partition lost, repeated or reordered source characters")
    return {"status": "PARTITION_CHECK_PASSED", "sections": sections, "body": reflow(body, join_wraps),
            "source_numbers": len(expected_labels), "detected_headings": len(headings),
            "footer_pages_removed": removed, "numbering_exceptions": []}


def page_html(title: str, content: str) -> str:
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>body{{margin:1em}}'
            'pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere}</style>'
            f'<h1>{html.escape(title)}</h1>{content}</html>\n')


def cached_report(directory: Path, fingerprint: str) -> dict | None:
    path = directory / "report.json"
    if not path.is_file() or path.is_symlink():
        return None
    try:
        report = json.loads(path.read_text())
        if report["fingerprint"] != fingerprint or report["publishable"] is not False:
            return None
        for relative, expected in report["output_hashes"].items():
            file = safe_relative(directory, relative)
            if not file.is_file() or digest(file.read_bytes()) != expected:
                return None
        if not report["output_hashes"]:
            return None
        return report
    except (KeyError, ValueError, OSError):
        return None


def prepare_one(job: dict, recipe: dict | None, root: Path, directory: Path,
                tool_identity: str, extractor=pdf_text) -> tuple[dict, bool]:
    url = checked_url(job["url"])
    source = safe_relative(root, job["cache"])
    data = source.read_bytes()
    if source.suffix != ".pdf" or not data.startswith(b"%PDF-") or digest(data) != job["sha256"]:
        raise ValueError("Cached PDF does not match recorded source bytes")
    fingerprint = digest(json_bytes({"source": job["sha256"], "recipe": recipe, "tool": tool_identity, "url": url}))
    previous = cached_report(directory, fingerprint)
    if previous is not None:
        return previous, True
    left, right = extractor(source, "poppler"), extractor(source, "mupdf")
    pinned = recipe is not None and recipe["source_sha256"] == job["sha256"]
    comparison = engine_comparison(left, right, pagination=pinned)
    permission = all(granted_notice("\f".join(pages_of(value)[:10])) for value in (left, right))
    raw = None
    raw_comparison = None
    if permission and comparison["mismatched_pages"]:
        raw = extractor(source, "poppler-raw")
        raw_comparison = canonical_comparison(raw, right)
        raw_comparison["exact_unicode_mismatched_pages"] = engine_comparison(raw, right)["mismatched_pages"]
    issues = []
    if not permission:
        issues.append("PERMISSION_REVIEW_REQUIRED")
    if comparison["mismatched_pages"]:
        issues.append("EXTRACTOR_DISAGREEMENT")
    partition = None
    if recipe is None:
        issues.append("LAYOUT_REVIEW_REQUIRED")
    elif recipe["source_sha256"] != job["sha256"]:
        issues.append("RECIPE_SOURCE_CHANGED")
    else:
        try:
            partition = numbered_book(left, recipe)
            if partition["status"] != "PARTITION_CHECK_PASSED":
                issues.append(partition["status"])
        except (ValueError, KeyError) as error:
            issues.append("BOUNDARY_REVIEW_REQUIRED")
            partition = {"error": str(error), "sections": []}
    hyphens = [{"page": number, "left": match[1], "right": match[2]}
               for number, page in enumerate(pages_of(left), 1)
               for match in re.finditer(r"(\w+-)\n[ \t]*(\w+)", page)]
    if hyphens and not (pinned and recipe.get("hyphen_wrap_policy") == "retain-hyphen-join-single-wrap"):
        issues.append("HYPHEN_WRAP_REVIEW_REQUIRED")
    title = recipe["title"] if recipe else unquote(Path(urlsplit(url).path).name)
    contents = {"poppler.txt": left.encode(), "mupdf.txt": right.encode()}
    if raw is not None:
        contents["poppler-raw.txt"] = raw.encode()
    section_rows = []
    if partition and partition.get("body"):
        contents["body.txt"] = partition["body"].encode()
    for section in (partition or {}).get("sections", []):
        relative = f'sections/{section["source_label"]}.txt'
        contents[relative] = section["body"].encode()
        section_rows.append({key: value for key, value in section.items() if key != "body"} | {"text_path": relative})
    summary = '<p>Private draft. Not approved for publication. Source numbering is not yet mapped to website text IDs.</p>'
    summary += f'<p><a href="{html.escape(url, quote=True)}">Original PDF</a> · <a href="poppler.txt">Full extracted text</a></p>'
    summary += '<p><a href="mupdf.txt">MuPDF text</a></p>'
    if raw_comparison is not None:
        summary += ('<p><a href="poppler-raw.txt">Alternative raw extraction</a>: '
                    + str(len(raw_comparison["mismatched_pages"]))
                    + ' pages still disagree after canonical Unicode comparison. '
                    'Diagnostic only; layout, visual and text-ID review are still required.</p>')
    summary += '<p>Review: ' + html.escape(", ".join(issues) if issues else "Visual and text-ID review still required") + '</p>'
    for section in (partition or {}).get("sections", []):
        label = html.escape(section["source_label"])
        summary += (f'<section id="source-{label}"><h2>{html.escape(section["title"])}</h2>'
                    f'<p><a href="{html.escape(url, quote=True)}#page={section["source_page"]}">Source PDF page {section["source_page"]}</a>'
                    f' · <a href="sections/{label}.txt">Plain text</a></p><pre>{html.escape(section["body"])}</pre></section>')
    if not section_rows:
        summary += '<pre>' + html.escape((partition or {}).get("body", left)) + '</pre>'
    contents["index.html"] = page_html(title, summary).encode()
    for relative, body in contents.items():
        write_file(safe_relative(directory, relative), body)
    report = {"schema_version": 1, "fingerprint": fingerprint, "source_url": url,
              "source_sha256": job["sha256"], "title": title,
              "status": "EXCEPTIONS_REVIEW_REQUIRED" if issues else "READY_FOR_VISUAL_REVIEW",
              "publishable": False, "canonical_mapping_status": "NOT_REVIEWED",
              "rights": "EXPLICIT_GRANT_DETECTED" if permission else "NEEDS_PERMISSION_REVIEW",
              "issues": issues, "comparison": comparison, "raw_comparison": raw_comparison,
              "hyphen_wraps": hyphens,
              "partition": {key: value for key, value in (partition or {}).items() if key not in {"sections", "body"}},
              "sections": section_rows, "output_hashes": {name: digest(body) for name, body in contents.items()}}
    write_file(directory / "report.json", json_bytes(report))
    return report, False


def prepare_batch(root: Path, output: Path, recipes: list[dict], jobs: list[dict],
                  limit: int, tool_identity: str, source_urls: list[str] | None = None,
                  extractor=pdf_text) -> dict:
    if not 1 <= limit <= 100:
        raise ValueError("Batch limit must be between 1 and 100")
    relative = output.absolute().relative_to(root.absolute())
    if len(relative.parts) < 2 or relative.parts[0] != "build":
        raise ValueError("Private output must be a dedicated directory below build/")
    safe_relative(root, relative.as_posix())
    marker = output / MARKER
    if output.exists() and any(output.iterdir()) and not marker.is_file():
        raise ValueError("Refusing an existing directory without the private review marker")
    if marker.exists() and json.loads(marker.read_text()) != MARKER_VALUE:
        raise ValueError("Invalid private review marker")
    write_file(marker, json_bytes(MARKER_VALUE))
    recipe_map = {row["source_url"]: row for row in recipes}
    if len(recipe_map) != len(recipes):
        raise ValueError("Duplicate source recipes")
    selected = [job for job in jobs if job["state"] == "COLLECTED" and job.get("cache", "").endswith(".pdf")
                and (source_urls is None or job["url"] in source_urls)]
    if source_urls and set(source_urls) - {job["url"] for job in selected}:
        raise ValueError("Requested source is not an already-collected PDF")
    selected.sort(key=lambda row: (row["url"] not in recipe_map,
                                  row.get("rights") != "EXPLICIT_FREE_UNALTERED", row["url"]))
    reports, processed, reused, pending = [], 0, 0, 0
    with safe_relative(output, ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for job in selected:
            key = digest(job["url"].encode())
            directory = safe_relative(output, "sources/" + key)
            recipe = recipe_map.get(job["url"])
            fingerprint = digest(json_bytes({"source": job["sha256"], "recipe": recipe, "tool": tool_identity, "url": job["url"]}))
            cached = cached_report(directory, fingerprint)
            # Check source integrity even when reusing generated files.
            try:
                if cached is not None or processed < limit:
                    report, was_cached = prepare_one(job, recipe, root, directory, tool_identity, extractor)
                    processed += not was_cached
                    reused += was_cached
                else:
                    pending += 1
                    continue
            except (ValueError, OSError, subprocess.SubprocessError) as error:
                processed += 1
                report = {"title": job["url"], "source_url": job["url"], "publishable": False,
                          "status": "SOURCE_REVIEW_REQUIRED", "issues": [str(error)], "sections": []}
            reports.append(report | {"review_path": f"sources/{key}/index.html" if "output_hashes" in report else None})
        exceptions = [{"source_url": row["source_url"], "issues": row["issues"],
                       "numbering": row.get("partition", {}).get("numbering_exceptions", []),
                       "mismatched_pages": row.get("comparison", {}).get("mismatched_pages", []),
                       "hyphen_wrap_count": len(row.get("hyphen_wraps", []))} for row in reports if row["issues"]]
        result = {"schema_version": 1, "automatic_publication": False, "network_requests": 0,
                  "processed_this_run": processed, "reused_reports": reused, "remaining_uncached": pending,
                  "sources_reviewed": len(reports), "section_drafts": sum(len(row["sections"]) for row in reports),
                  "issue_counts": dict(Counter(issue for row in reports for issue in row["issues"])),
                  "sources": reports, "exceptions": exceptions}
        write_file(output / "report.json", json_bytes(result))
        write_file(output / "exceptions.json", json_bytes(exceptions))
        links = '<p>Local drafts only. No new translations have been approved or published.</p><ul>'
        for row in reports:
            title = html.escape(row["title"])
            label = f'<a href="{row["review_path"]}">{title}</a>' if row["review_path"] else title
            links += (f'<li>{label}'
                      f' — {len(row["sections"])} section drafts; {html.escape(", ".join(row["issues"]) or "visual review required")}</li>')
        links += '</ul><p><a href="exceptions.json">Exceptions</a> · <a href="report.json">Complete report</a></p>'
        write_file(output / "index.html", page_html("Candana batch review", links).encode())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=8, help="Maximum uncached PDFs per invocation; cached results are reused")
    parser.add_argument("--source-url", action="append", help="Optional exact collected URL, repeatable")
    args = parser.parse_args()
    config = json.loads(RECIPES.read_text())
    if config.get("schema_version") != 1:
        raise ValueError("Unknown recipe schema")
    state = json.loads(QUEUE.read_text())  # Read only; never reset or modify the collector's queue.
    binaries = {name: (Path(shutil.which(name)).stat().st_size, Path(shutil.which(name)).stat().st_mtime_ns)
                for name in ("pdftotext", "mutool")}
    identity = digest(Path(__file__).read_bytes() + json_bytes(binaries))
    result = prepare_batch(ROOT, OUTPUT, config["recipes"], state["jobs"], args.limit, identity, args.source_url)
    print(json.dumps({key: value for key, value in result.items() if key not in {"sources", "exceptions"}}, indent=2))


if __name__ == "__main__":
    main()
