#!/usr/bin/env python3
"""Render an audited rights-cleared text as a uniform reader."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import threading
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from public_site_catalog import site_navigation


ROOT = Path(__file__).resolve().parents[2]
CC0_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
_FONT_LOCK = threading.Lock()
_PDF_RENDER_LOCK = threading.Lock()
_FONT_PATHS: tuple[str, str] | None = None


class ReaderParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.in_source = False
        self.source_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag == "pre" and "source-text" in values.get("class", "").split():
            self.in_source = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "pre" and self.in_source:
            self.in_source = False

    def handle_data(self, data: str) -> None:
        if self.in_source:
            self.source_parts.append(data)


def repo_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Expected a repository-relative path without '..': {value}")
    resolved = (ROOT / path).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as error:
        raise ValueError(f"Path resolves outside the repository: {value}") from error
    return resolved


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_source(config: dict) -> str:
    """Return the unmodified text body after checking its recorded source."""
    source_path = repo_path(config["local_text"])
    source_bytes = source_path.read_bytes()
    actual_hash = hashlib.sha256(source_bytes).hexdigest()
    if actual_hash != config["source_sha256"]:
        raise ValueError(f"Local source changed: {config['local_text']}")
    source = source_bytes.decode("utf-8")
    try:
        header, body = source.split("\n\n", 1)
    except ValueError as error:
        raise ValueError("Source text has no metadata/body separator") from error
    expected_header = "\n".join((
        f"{config['canonical_id']} - {config['title']}",
        f"Translated by {config['translator']}",
        f"Source: {config['source_url']}",
        f"License: {config['license']}",
    ))
    if header != expected_header:
        raise ValueError("Source header no longer matches the recorded translation and license")
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != config["body_sha256"]:
        raise ValueError("Source text body hash does not match the pilot record")
    if not body.strip():
        raise ValueError("Source text body is empty")

    manifest = read_json(repo_path(config["source_manifest"]))
    manifest_repository = manifest.get("repository", "").removesuffix(".git")
    if (config["license"] != "CC0-1.0" or config["license_url"] != CC0_URL
            or manifest_repository != config["source_repository"]
            or manifest.get("commit") != config["source_revision"]
            or manifest.get("translator") != config["translator"]
            or manifest.get("license") != "CC0-1.0"
            or manifest.get("license_url") != CC0_URL):
        raise ValueError("Pinned source manifest does not verify the translator, revision, and CC0 license")

    ledger_path = repo_path(config["ledger"])
    with ledger_path.open(encoding="utf-8", newline="") as handle:
        matches = [row for row in csv.DictReader(handle, dialect="excel-tab")
                   if row.get("canonical_id") == config["canonical_id"]]
    if len(matches) != 1:
        raise ValueError(f"Expected one source-ledger record for {config['canonical_id']}; found {len(matches)}")
    record = matches[0]
    expected_record = {
        "txt_path": config["local_text"],
        "source_url": config["source_url"],
        "license": "CC0-1.0",
        "source_commit": config["source_revision"],
        "upstream_file": config["upstream_file"],
    }
    if any(record.get(key) != value for key, value in expected_record.items()):
        raise ValueError("Source-ledger record does not match the pilot provenance")

    with repo_path(config["coverage_report"]).open(encoding="utf-8", newline="") as handle:
        coverage = [row for row in csv.DictReader(handle, delimiter="\t")
                    if row.get("canonical_id") == config["canonical_id"]]
    if (len(coverage) != 1 or coverage[0].get("status") != "PRESENT"
            or coverage[0].get("english_paths") != config["local_text"]
            or coverage[0].get("english_records") != "1"):
        raise ValueError("Coverage report does not confirm exactly one local English text")
    return body


def render_html(config: dict, body: str) -> str:
    def esc(value: str) -> str:
        return html.escape(value, quote=True)

    if not config["translations"] or sum(bool(item.get("current")) for item in config["translations"]) != 1:
        raise ValueError("Translation list must contain exactly one selected version")
    translations = "\n".join(
        f'<li><span aria-current="page">{html.escape(item["label"])}</span></li>'
        if item.get("current") else
        f'<li><a href="{esc(item["href"])}">{html.escape(item["label"])}</a></li>'
        for item in config["translations"]
    )
    source_link = f'{esc(config["source_url"])}'
    license_link = esc(config.get("license_url", ""))
    license_text = html.escape(config["license"])
    if license_link:
        license_text = f'<a rel="license external" href="{license_link}">{license_text}</a>'
    revision_target = config["source_repository"] + "/tree/" + config["source_revision"] if "github.com/" in config["source_repository"] else config["source_url"]
    revision_href = esc(revision_target)
    navigation = []
    if config.get("previous_href"):
        navigation.append(
            f'<li><a rel="prev" href="{esc(config["previous_href"])}">'
            f'Previous: {html.escape(config["previous_label"])}</a></li>'
        )
    if config.get("contents_href"):
        navigation.append(
            f'<li><a rel="up" href="{esc(config["contents_href"])}">'
            f'{html.escape(config["contents_label"])}</a></li>'
        )
    if config.get("next_href"):
        navigation.append(
            f'<li><a rel="next" href="{esc(config["next_href"])}">'
            f'Next: {html.escape(config["next_label"])}</a></li>'
        )
    sequence_navigation = (
        '<nav aria-label="Discourse navigation"><h2>Read in sequence</h2><ul>'
        + "".join(navigation) + "</ul></nav>"
        if navigation else ""
    )
    source_label = config.get("source_label", f'SuttaCentral · {config["canonical_id"]}')
    canonical_id = config["canonical_id"].strip()
    display_reference = config.get("group_reference", "").strip() or canonical_id
    display_title = config["title"].strip()
    if config.get("group_reference"):
        display_title = f"{display_reference} — {display_title}" if display_title else display_reference
    else:
        if display_title.casefold().startswith(canonical_id.casefold()):
            display_title = display_title[len(canonical_id):].lstrip(" \t:—–-")
        if display_title.casefold().endswith(canonical_id.casefold()):
            display_title = display_title[:-len(canonical_id)].rstrip(" \t:—–-")
        display_title = f"{canonical_id} — {display_title}" if display_title else canonical_id
    breadcrumb_items = config.get("breadcrumbs") or [
        {"label": "Tipitaka", "href": config.get("tipitaka_href", "")},
        {"label": config["collection_label"], "href": config["collection_href"]},
    ]
    breadcrumbs = " → ".join(
        f'<a href="{esc(item["href"])}">{html.escape(item["label"])}</a>'
        for item in breadcrumb_items
    )
    breadcrumbs += f' → <span aria-current="page">{html.escape(display_reference)}</span>'
    group_members = config.get("group_members", [])
    group_navigation = (
        '<section aria-labelledby="group-references"><h2 id="group-references">Text pages covered</h2><ul>'
        + "".join(f'<li><a href="{esc(item["href"])}">{html.escape(item["label"])}</a></li>'
                  for item in group_members)
        + "</ul></section>"
        if group_members else ""
    )
    metadata_notes = config.get("metadata_notes", [])
    details_html = (
        '<details><summary>Edition details</summary><ul>'
        + "".join(f"<li>{html.escape(note)}</li>" for note in metadata_notes)
        + "</ul></details>"
        if metadata_notes else ""
    )
    revision_row = (
        f'<dt>Source revision</dt><dd><a rel="external" href="{revision_href}">'
        f'{html.escape(config["source_revision"])}</a></dd>'
        if config.get("source_revision") and config.get("source_repository") else ""
    )
    original_book = (
        f'<p><a href="{esc(config["original_book_href"])}">Original book PDF and complete permission notice</a></p>'
        if config.get("original_book_href") else ""
    )
    rights_notice = (
        '<p>' + html.escape(config.get("copyright", "")) + '</p><p>'
        + html.escape(config.get("license_notice", "")) + '</p>'
        if config.get("license_notice") else ""
    )
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(display_title)}</title>
<style>
.source-text {{ white-space: pre-wrap; font: inherit; }}
@media print {{ nav, .downloads {{ display: none; }} }}
</style>
</head>
<body>
{site_navigation()}
<header>
<nav aria-label="Breadcrumb">
{breadcrumbs}
</nav>
<h1>{html.escape(display_title)}</h1>
<p>English translation by {html.escape(config['translator'])}.</p>
</header>
<section aria-labelledby="translation-heading">
<h2 id="translation-heading">Translation</h2>
<ul>{translations}</ul>
</section>
{group_navigation}
<nav aria-label="Downloads" class="downloads">
<h2>Download</h2>
<a href="{esc(config['local_text_href'])}" download>TXT</a>
<a href="{esc(config['html_download_href'])}" download>HTML</a>
<a href="{esc(config['pdf_download_href'])}" download>PDF</a>
</nav>
{sequence_navigation}
<main>
<article>
<h2>Text</h2>
<pre class="source-text">{html.escape(body, quote=False)}</pre>
</article>
</main>
<footer>
<h2>Source and license</h2>
{rights_notice}
<dl>
<dt>Translator</dt><dd>{html.escape(config['translator'])}</dd>
<dt>Source</dt><dd><a rel="external" href="{source_link}">{html.escape(source_label)}</a></dd>
<dt>License</dt><dd>{license_text}</dd>
{revision_row}
</dl>
{details_html}
{original_book}
</footer>
</body>
</html>
'''


def render_pdf(config: dict, body: str, target: Path) -> None:
    global _FONT_PATHS
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError as error:
        raise RuntimeError("reportlab is required to generate reader PDFs; install tools/buddhist_canon_pipeline/requirements.txt") from error

    with _FONT_LOCK:
        if _FONT_PATHS is None:
            fontconfig = shutil.which("fc-match")
            if not fontconfig:
                raise RuntimeError("fontconfig is required to locate the Noto Sans reader fonts")
            regular_font = subprocess.run(
                [fontconfig, "-f", "%{file}", "Noto Sans"], check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            bold_font = subprocess.run(
                [fontconfig, "-f", "%{file}", "Noto Sans:style=Bold"], check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            if not regular_font or not Path(regular_font).is_file() or not bold_font or not Path(bold_font).is_file():
                raise RuntimeError("Noto Sans regular and bold fonts are required to generate reader PDFs")
            _FONT_PATHS = (regular_font, bold_font)
        registered = pdfmetrics.getRegisteredFontNames()
        if "ReaderNotoSans" not in registered:
            pdfmetrics.registerFont(TTFont("ReaderNotoSans", _FONT_PATHS[0]))
        if "ReaderNotoSansBold" not in registered:
            pdfmetrics.registerFont(TTFont("ReaderNotoSansBold", _FONT_PATHS[1]))
    styles = {
        "title": ParagraphStyle(
            "ReaderTitle", fontName="ReaderNotoSansBold", fontSize=16, leading=20,
            spaceAfter=6 * mm,
        ),
        "metadata": ParagraphStyle(
            "ReaderMetadata", fontName="ReaderNotoSans", fontSize=9, leading=13,
            spaceAfter=1 * mm,
        ),
        "heading": ParagraphStyle(
            "ReaderHeading", fontName="ReaderNotoSansBold", fontSize=12, leading=16,
            spaceBefore=6 * mm, spaceAfter=3 * mm,
        ),
        "body": ParagraphStyle(
            "ReaderBody", fontName="ReaderNotoSans", fontSize=10.5, leading=15,
            spaceAfter=3 * mm,
        ),
    }

    fallback_names = {}

    def pdf_markup(value: str) -> str:
        # Noto Sans lacks some scholarly symbols (for example the Pali root
        # marker √). Select a real Unicode glyph instead of silently dropping it.
        primary = pdfmetrics.getFont("ReaderNotoSans").face.charToGlyph
        parts = []
        # U+00AD is a discretionary line-layout hint, not a printed hyphen.
        # Keep it in source TXT/HTML, but do not create a visible PDF hyphen.
        value = value.replace("\u00ad", "")
        for position, character in enumerate(value):
            if (character == " " and position and position + 1 < len(value)
                    and all(unicodedata.category(c)[0] in "PS"
                            for c in (value[position - 1], value[position + 1]))):
                parts.append("&#160;&#160;")
                continue
            escaped = html.escape(character)
            if character.isspace() or ord(character) in primary:
                parts.append(escaped)
                continue
            if character in fallback_names:
                parts.append(f'<font name="{fallback_names[character]}">{escaped}</font>')
                continue
            with _FONT_LOCK:
                path = subprocess.run(["fc-match", "-f", "%{file}", f":charset={ord(character):x}"],
                                      check=True, capture_output=True, text=True).stdout.strip()
                name = "ReaderFallback" + hashlib.sha256(path.encode()).hexdigest()[:12]
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, path))
                if ord(character) not in pdfmetrics.getFont(name).face.charToGlyph:
                    raise ValueError(f"No installed PDF font for U+{ord(character):04X}")
            fallback_names[character] = name
            parts.append(f'<font name="{name}">{escaped}</font>')
        return "".join(parts)
    metadata = [
        "Source: " + config["source_url"],
        *(["Covers: " + ", ".join(item["label"] for item in config["group_members"])]
          if config.get("group_members") else []),
        *(["Source revision: " + config["source_revision"]] if config.get("source_revision") else []),
        "License: " + config["license"] + (" — " + config["license_url"] if config.get("license_url") else ""),
        *config.get("metadata_notes", []),
        *(["PDF presentation: discretionary soft-hyphen layout hints are omitted; original TXT and HTML retain them."]
          if "\u00ad" in body else []),
    ]
    display_reference = config.get("group_reference", "").strip() or config["canonical_id"]
    story = [
        Paragraph(pdf_markup(display_reference + " — " + config["title"]), styles["title"]),
        Paragraph("English translation by " + pdf_markup(config["translator"]) + ".", styles["metadata"]),
        *(Paragraph(pdf_markup(line), styles["metadata"]) for line in metadata),
        Paragraph("Text", styles["heading"]),
    ]
    for line in body.splitlines():
        if line:
            rendered = pdf_markup(line)
            # ReportLab/Poppler otherwise collapse the publisher's spaced
            # ornamental separator into "***". Preserve its visible spacing.
            if re.fullmatch(r"\s*(?:\*(?:\s+\*)+|\[[ \t]+[IVXLCDM]+[ \t]+\])\s*", line):
                rendered = rendered.replace(" ", "&#160;&#160;")
            story.append(Paragraph(rendered, styles["body"]))
        else:
            story.append(Spacer(1, 2 * mm))

    target.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(target), pagesize=A4, rightMargin=24 * mm, leftMargin=24 * mm,
        topMargin=24 * mm, bottomMargin=24 * mm,
        title=display_reference + " — " + config["title"],
        author=config["translator"],
    )

    def invariant_canvas(*args, **kwargs):
        kwargs["invariant"] = 1
        return Canvas(*args, **kwargs)

    # ReportLab reads shared TTFont file handles while building a PDF. Protect
    # that section when the eligible-reader builder renders PDFs concurrently.
    with _PDF_RENDER_LOCK:
        document.build(story, canvasmaker=invariant_canvas)


def normalized(value: str) -> str:
    return " ".join(value.split())


def verify_pdf_body(pdf_path: Path, body: str) -> None:
    """Check that extracted PDF text contains the complete source in order."""
    if not pdf_path.is_file() or not pdf_path.stat().st_size:
        raise ValueError(f"PDF is missing or empty: {pdf_path}")
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        raise RuntimeError("pdftotext is required to validate reader PDFs")
    extracted = subprocess.run(
        [pdftotext, "-layout", "-nopgbrk", str(pdf_path), "-"],
        check=True, capture_output=True, text=True,
    ).stdout
    if "\nText\n" not in extracted:
        raise ValueError("PDF is missing its source-text heading")
    extracted = extracted.split("\nText\n", 1)[1]
    if normalized(body.replace("\u00ad", "")) not in normalized(extracted):
        raise ValueError(f"PDF text does not contain the complete source body in order: {pdf_path}")


def validate_outputs(config: dict, body: str, expected_html: str) -> None:
    html_path = repo_path(config["output_html"])
    pdf_path = repo_path(config["output_pdf"])
    if not html_path.is_file() or html_path.read_text(encoding="utf-8") != expected_html:
        raise ValueError(f"Generated HTML is missing or out of date: {config['output_html']}")
    parser = ReaderParser()
    parser.feed(expected_html)
    if "".join(parser.source_parts) != body:
        raise ValueError("Rendered HTML text differs from the complete imported source body")
    for href in parser.links:
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        target = (html_path.parent / unquote(parsed.path)).resolve()
        try:
            target.relative_to(ROOT.resolve())
        except ValueError as error:
            raise ValueError(f"Reader link escapes the repository: {href}") from error
        if not target.is_file():
            raise ValueError(f"Reader link target is missing: {href}")
    entry_path = repo_path(config["entry_page"])
    entry_parser = ReaderParser()
    entry_parser.feed(entry_path.read_text(encoding="utf-8"))
    if config["entry_href"] not in entry_parser.links:
        raise ValueError(f"Reader pilot is not linked from {config['entry_page']}")
    verify_pdf_body(pdf_path, body)


def run(manifest_path: Path, check: bool) -> None:
    config = read_json(manifest_path)
    body = verify_source(config)
    expected_html = render_html(config, body)
    html_path = repo_path(config["output_html"])
    pdf_path = repo_path(config["output_pdf"])
    if not check:
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(expected_html, encoding="utf-8")
        render_pdf(config, body, pdf_path)
    validate_outputs(config, body, expected_html)
    print(f"Verified {config['canonical_id']}: {len(body.splitlines())} source lines; HTML, TXT link, and PDF text match.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="repository-relative JSON provenance and reader configuration")
    parser.add_argument("--check", action="store_true", help="verify committed outputs without rewriting them")
    arguments = parser.parse_args()
    manifest = arguments.manifest if arguments.manifest.is_absolute() else ROOT / arguments.manifest
    try:
        run(manifest, arguments.check)
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"reader generation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
