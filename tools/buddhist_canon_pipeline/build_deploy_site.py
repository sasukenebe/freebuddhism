#!/usr/bin/env python3
"""Build a default-deny web bundle from explicitly eligible text editions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit

from build_eligible_readers import VINAYA_CONTENTS, collect_records
from public_html_policy import NAVIGATION_SCOPE, SITE_SCOPE, require_allowlisted_page, validate_site_content_manifest
from public_site_catalog import (
    ABHIDHAMMA_BOOKS,
    COLLECTION_TITLES,
    SUTTA_NODE_INFO,
    WHOLE_BOOK_PDF_SOURCES,
    canonical_slug,
    natural_key,
    slug,
    whole_book_pdfs,
)


ROOT = Path(__file__).resolve().parents[2]
BUILD_ROOT = ROOT / "build"
WEBROOT = BUILD_ROOT / "site-root"
BUILD_MARKER = BUILD_ROOT / ".site-root-managed"
READER_BUILDER = ROOT / "tools" / "buddhist_canon_pipeline" / "build_eligible_readers.py"
READER_OUTPUT = BUILD_ROOT / "eligible-readers"
PUBLIC_TIPITAKA = ROOT / "theravada" / "tipitaka"
IMPACT_MAP = ROOT / "metadata" / "reports" / "remediation-impact-map-2026-10.json"
SITE_ENTRY = ROOT / "site-entry" / "index.html"
ANGUTTARA_MENU = ROOT / "metadata" / "anguttara-menu.json"
VINAYA_KHANDHAKA_MENU = ROOT / "metadata" / "vinaya-khandhaka-menu.json"
CC0_LICENSE = "CC0-1.0"
COWELL_PD_LICENSE = "Public Domain (original English edition, published 1895–1907)"
US_PD_BOOK_LICENSE = "Public domain in the United States"
ARCHIVE_NOTICE = "NOTICE.txt"
TIPITAKA_URL_PREFIX = "/theravada/tipitaka/"
ARCHIVE_LINK_RE = re.compile(r'<li><a href="\.\./downloads/([^"#?]+\.zip)">([^<]+)</a></li>')
VINAYA_NODE_TITLES = {
    "sutta-vibhanga": "Sutta Vibhaṅga",
    "bhikkhu-vibhanga": "Mahā Vibhaṅga — monks’ rules",
    "bhikkhuni-vibhanga": "Bhikkhunī Vibhaṅga — nuns’ rules",
    "khandhaka": "Khandhaka",
    "mahavagga": "Mahāvagga",
    "cullavagga": "Cullavagga",
    "parivara": "Parivāra",
}
VINAYA_RULE_CLASSES = {
    "as": ("Adhikaraṇasamatha", "Settling Legal Issues"),
    "ay": ("Aniyata", "Undetermined Rules"),
    "np": ("Nissaggiya Pācittiya", "Forfeiture and Confession"),
    "pc": ("Pācittiya", "Confession Rules"),
    "pd": ("Pāṭidesanīya", "Acknowledgement Rules"),
    "pj": ("Pārājika", "Rules Entailing Defeat"),
    "sk": ("Sekhiya", "Training Rules"),
    "ss": ("Saṅghādisesa", "Rules Requiring a Formal Meeting"),
}


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record(attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record(attrs)

    def _record(self, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in {"href", "src", "data"} and value:
                self.urls.append(value)


def local_link_errors(webroot: Path) -> list[str]:
    """Return missing or escaping local href/src targets in the staged webroot."""
    root = webroot.resolve()
    errors: list[str] = []
    files: set[str] = set()
    directories: set[str] = set()
    pages: list[str] = []
    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        retained_directories = []
        for name in subdirectories:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                errors.append(f"{relative}: symlink is not allowed in the staged webroot")
            else:
                directories.add(relative)
                retained_directories.append(name)
        subdirectories[:] = retained_directories
        for name in filenames:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                errors.append(f"{relative}: symlink is not allowed in the staged webroot")
                continue
            files.add(relative)
            if path.suffix.lower() == ".html":
                pages.append(relative)

    for page_relative in sorted(pages):
        page_path = root / page_relative
        parser = LinkParser()
        parser.feed(page_path.read_text(encoding="utf-8"))
        for url in parser.urls:
            parsed = urlsplit(url)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            raw_path = unquote(parsed.path)
            target = raw_path.lstrip("/") if raw_path.startswith("/") else posixpath.join(
                PurePosixPath(page_relative).parent.as_posix(), raw_path
            )
            normalized = posixpath.normpath(target)
            if normalized == ".." or normalized.startswith("../") or normalized.startswith("/"):
                errors.append(f"{page_relative}: link escapes webroot: {url}")
                continue
            if parsed.path.endswith("/") or normalized in directories:
                normalized = posixpath.join(normalized, "index.html")
            if normalized not in files:
                errors.append(f"{page_relative}: missing local target: {url}")
    return errors


def _safe_relative(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Expected a non-empty safe relative path: {value}")
    return path


def _replace_sutta_coverage_intro(page: str, intro: str) -> str:
    """Replace either legacy or already-generated coverage text, idempotently."""
    existing_intro = re.search(
        r"<p>(?:\d+ available texts for \d+ suttas, grouped by collection\."
        r"|Source index: \d+ entries across \d+ IDs\. This build includes "
        r"\d+ CC0 or verified-public-domain editions across \d+ IDs\. A zero means "
        r"no edition cleared for local redistribution; it does not mean no translation exists\.)</p>",
        page,
    )
    if not existing_intro:
        raise ValueError("Could not locate a recognized Sutta text-index coverage statement")
    return page[:existing_intro.start()] + intro + page[existing_intro.end():]


def _replace_tipitaka_coverage_summary(page: str, summary: str) -> str:
    """Replace legacy or already-generated Tipiṭaka coverage text."""
    pattern = re.compile(
        r"<p>(?:The Sutta Piṭaka section contains .*?"
        r"|The text index retains \d+ source entries across \d+ IDs\. This build includes "
        r"\d+ CC0 or verified-public-domain Sutta editions across \d+ IDs\. The Vinaya source ledger lists "
        r"\d+ files; \d+ eligible files are hosted locally\. No Abhidhamma book currently clears the reuse policy\. "
        r"Text availability and translation completeness are separate; unavailable entries remain in the navigation\.)</p>",
        re.DOTALL,
    )
    updated, count = pattern.subn(summary, page, count=1)
    if count != 1:
        raise ValueError("Could not locate a recognized Tipiṭaka coverage summary")
    return updated


def _record_relative_path(record: dict, key: str, output_root: Path, repo_root: Path) -> Path:
    original = Path(record[key])
    if original.is_symlink():
        raise ValueError(f"Eligible record path must not be a symlink: {original}")
    source = original.resolve()
    if key in {"html_path", "pdf_path"}:
        base = output_root.resolve()
        prefix = ("theravada", "tipitaka")
    elif key == "text_path":
        base = repo_root.resolve()
        prefix = ("theravada", "tipitaka")
    else:
        raise ValueError(f"Unknown record path field: {key}")
    try:
        relative = source.relative_to(base)
    except ValueError as error:
        raise ValueError(f"Eligible record {key} escapes its approved root: {source}") from error
    if relative.parts[:2] != prefix or len(relative.parts) < 3:
        raise ValueError(f"Eligible record {key} is outside the Tipiṭaka output tree: {relative}")
    return _safe_relative(Path(*relative.parts[2:]))


def _record_license_is_allowed(record: dict) -> bool:
    if record.get("kind") == "sutta" and record.get("license") in {CC0_LICENSE, COWELL_PD_LICENSE}:
        return True
    return record.get("kind") == "vinaya" and record.get("license") == CC0_LICENSE


def _write_page(path: Path, title: str, body: str, tipitaka_root: Path) -> None:
    site_root = tipitaka_root / "site"
    home = Path(os.path.relpath(site_root / "index.html", start=path.parent)).as_posix()
    tipitaka = Path(os.path.relpath(site_root / "tipitaka.html", start=path.parent)).as_posix()
    downloads = Path(os.path.relpath(site_root / "downloads.html", start=path.parent)).as_posix()
    path.parent.mkdir(parents=True, exist_ok=True)
    document = (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{html.escape(title)}</title>\n</head>\n<body>\n"
        f'<nav><a href="{html.escape(home, quote=True)}">Home</a> · '
        f'<a href="{html.escape(tipitaka, quote=True)}">Text collections</a> · '
        f'<a href="{html.escape(downloads, quote=True)}">Downloads</a></nav>\n'
        f"{body}\n</body>\n</html>\n"
    )
    path.write_text(document, encoding="utf-8", newline="\n")


def _relative_href(from_path: Path, to_path: Path) -> str:
    return Path(os.path.relpath(to_path, start=from_path.parent)).as_posix()


def _public_relative_path(url: str) -> Path | None:
    parsed = urlsplit(url)
    if parsed.scheme and parsed.netloc not in {"freebuddhism.org", "www.freebuddhism.org"}:
        return None
    raw = unquote(parsed.path)
    if not raw.startswith(TIPITAKA_URL_PREFIX):
        return None
    return _safe_relative(PurePosixPath(raw[len(TIPITAKA_URL_PREFIX):]))


def _source_rows(page: str) -> list[dict[str, str]]:
    pattern = re.compile(
        r'<tr><td>(?P<canonical_id>.*?)</td><td><a href="(?P<href>[^"]+)">'
        r'(?P<title>.*?)</a></td><td>(?P<count>\d+)</td><td>(?P<audio>.*?)</td></tr>',
        re.DOTALL,
    )
    rows = []
    for match in pattern.finditer(page):
        href = unquote(urlsplit(match.group("href")).path)
        route = posixpath.normpath(posixpath.join("site", href))
        if route.startswith("../") or not route.startswith("sutta/"):
            raise ValueError(f"Sutta index row points outside the sutta tree: {match.group('href')}")
        parts = PurePosixPath(route).parts
        if len(parts) < 4 or parts[-1] != "index.html":
            raise ValueError(f"Unexpected sutta index row route: {match.group('href')}")
        rows.append({
            "canonical_id": html.unescape(match.group("canonical_id")),
            "title": html.unescape(match.group("title")),
            "route": Path(*parts).as_posix(),
            "collection": "/".join(parts[1:-2]),
            "audio": html.unescape(match.group("audio")).strip().casefold(),
        })
    if not rows:
        raise ValueError("The existing Sutta text index contains no parseable entries")
    return rows


def _copy_site_pages(destination: Path, allowed: dict[Path, dict], site_root: Path, site_entry: Path) -> None:
    if not site_root.is_dir():
        raise FileNotFoundError(f"Existing website pages are missing: {site_root}")
    site_manifest = validate_site_content_manifest(ROOT)
    tipitaka_root = destination / "theravada" / "tipitaka"
    for source in sorted(site_root.rglob("*")):
        if source.is_symlink():
            raise ValueError(f"Website asset must not be a symlink: {source}")
        if not source.is_file():
            continue
        source_relative = (Path("theravada/tipitaka/site") / source.relative_to(site_root)).as_posix()
        if source_relative not in site_manifest or site_manifest[source_relative].get("license_scope") != SITE_SCOPE:
            raise ValueError(f"Website page lacks its explicit CC0 manifest entry: {source_relative}")
        require_allowlisted_page(ROOT, source_relative, SITE_SCOPE)
        relative = _safe_relative(Path("site") / source.relative_to(site_root))
        target = tipitaka_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        allowed[relative] = {"source": target, "kind": source.suffix.lower().removeprefix("."), "collection": None, "archive": False}
    if site_entry.is_symlink() or not site_entry.is_file():
        raise FileNotFoundError(f"Required website entry is missing: {site_entry}")
    if "site-entry/index.html" not in site_manifest:
        raise ValueError("Site entry is absent from the explicit CC0 site-content manifest")
    require_allowlisted_page(ROOT, "site-entry/index.html", SITE_SCOPE)
    shutil.copyfile(site_entry, destination / "index.html")


def _strip_unavailable_embeds(page: str, source_relative: Path, allowed: dict[Path, dict]) -> str:
    """Replace locally embedded files unless the exact target is allowlisted."""
    object_pattern = re.compile(r"<object\b(?P<attrs>[^>]*)>.*?</object\s*>", re.IGNORECASE | re.DOTALL)
    data_pattern = re.compile(r"\bdata\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)

    def replace(match: re.Match[str]) -> str:
        attr = data_pattern.search(match.group("attrs"))
        if attr:
            value = html.unescape(attr.group(2))
            parsed = urlsplit(value)
            if not parsed.scheme and not parsed.netloc and parsed.path:
                resolved = posixpath.normpath(posixpath.join(source_relative.parent.as_posix(), unquote(parsed.path)))
                try:
                    target = _safe_relative(resolved)
                except ValueError:
                    target = None
                if target in allowed:
                    return match.group(0)
        return '<p>Embedded document omitted because it is not eligible for local redistribution.</p>'

    return object_pattern.sub(replace, page)


def _copy_collection_indexes(tipitaka_root: Path, allowed: dict[Path, dict], source_root: Path) -> None:
    collections = set(COLLECTION_TITLES) | set(SUTTA_NODE_INFO) | set(WHOLE_BOOK_PDF_SOURCES) | {"khuddaka-nikaya"}
    for collection in sorted(collections):
        relative = _safe_relative(Path("sutta") / collection / "index.html")
        source = source_root / relative
        if source.is_symlink():
            raise ValueError(f"Collection index must not be a symlink: {source}")
        if not source.is_file():
            continue
        require_allowlisted_page(ROOT, (Path("theravada/tipitaka") / relative).as_posix(), NAVIGATION_SCOPE)
        target = tipitaka_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        original = source.read_text(encoding="utf-8")
        target.write_text(_strip_unavailable_embeds(original, relative, allowed), encoding="utf-8")
        allowed[relative] = {"source": target, "kind": "html", "collection": collection, "archive": False}
    for source in sorted(source_root.glob("sutta/**/topics/**/*.html")):
        if source.is_symlink():
            raise ValueError(f"Topic index must not be a symlink: {source}")
        relative = _safe_relative(source.relative_to(source_root))
        require_allowlisted_page(ROOT, (Path("theravada/tipitaka") / relative).as_posix(), NAVIGATION_SCOPE)
        target = tipitaka_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        original = source.read_text(encoding="utf-8")
        target.write_text(_strip_unavailable_embeds(original, relative, allowed), encoding="utf-8")
        allowed[relative] = {"source": target, "kind": "html", "collection": "khuddaka-nikaya/jataka", "archive": False}


def _disable_restricted_links(tipitaka_root: Path, blocked_file_paths: set[Path]) -> int:
    """Turn old direct text/PDF links into explicit non-clickable availability labels."""
    if not blocked_file_paths:
        return 0
    anchor_re = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a\s*>", re.IGNORECASE | re.DOTALL)
    href_re = re.compile(r"\bhref\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)
    changed = 0
    for page in sorted(tipitaka_root.rglob("*.html")):
        relative_page = page.relative_to(tipitaka_root)
        source = page.read_text(encoding="utf-8")

        def replace_anchor(match: re.Match) -> str:
            nonlocal changed
            href_match = href_re.search(match.group("attrs"))
            if not href_match:
                return match.group(0)
            parsed = urlsplit(html.unescape(href_match.group(2)))
            if parsed.scheme or parsed.netloc or not parsed.path:
                return match.group(0)
            if parsed.path.startswith(TIPITAKA_URL_PREFIX):
                route = posixpath.normpath(parsed.path[len(TIPITAKA_URL_PREFIX):])
            elif parsed.path.startswith("/"):
                return match.group(0)
            else:
                route = posixpath.normpath(posixpath.join(relative_page.parent.as_posix(), unquote(parsed.path)))
            if route.startswith("../") or Path(route) not in blocked_file_paths:
                return match.group(0)
            changed += 1
            return f'<span class="unavailable">{match.group("body")} (not locally available under the reuse policy)</span>'

        updated = anchor_re.sub(replace_anchor, source)
        if updated != source:
            page.write_text(updated, encoding="utf-8", newline="\n")
    return changed


def _localize_suttafriends_story_links(
    page: Path, relative_page: Path, tipitaka_root: Path, allowed: dict[Path, dict]
) -> int:
    """Keep Sutta Friends story lists navigable without linking readers off-site."""
    anchor_re = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a\s*>", re.IGNORECASE | re.DOTALL)
    href_re = re.compile(r"\bhref\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)
    source = page.read_text(encoding="utf-8")
    changed = 0

    def localize(match: re.Match) -> str:
        nonlocal changed
        href_match = href_re.search(match.group("attrs"))
        if not href_match:
            return match.group(0)
        parsed = urlsplit(html.unescape(href_match.group(2)))
        if parsed.hostname not in {"suttafriends.org", "www.suttafriends.org"}:
            return match.group(0)
        if parsed.path.rstrip("/").endswith("/copyright"):
            return match.group(0)
        body = match.group("body")
        visible = html.unescape(re.sub(r"<[^>]+>", " ", body)).strip()
        story = re.match(r"^(Vv|Pv)\s+(\d+(?:\.\d+)*)\b", visible)
        if story:
            collection = "khuddaka-nikaya/vimanavatthu" if story.group(1) == "Vv" else "khuddaka-nikaya/petavatthu"
            canonical_id = f"{story.group(1)} {story.group(2)}"
            story_title = re.sub(r"^(?:Vv|Pv)\s+\d+(?:\.\d+)*\s*[:—-]?\s*", "", visible).strip()
            target = Path("sutta") / collection / canonical_slug(canonical_id) / "index.html"
            target_page = tipitaka_root / target
            target_relative = _safe_relative(target)
            if target_relative not in allowed:
                _write_unavailable_page(
                    target_page,
                    f"{canonical_id} — {story_title or visible}",
                    "This listed English translation is not included because its source does not establish CC0 or verified public-domain redistribution rights.",
                    tipitaka_root,
                )
                _register_generated_page(allowed, tipitaka_root, target_page, collection)
            changed += 1
            return f'<a href="{html.escape(_relative_href(tipitaka_root / relative_page, target_page), quote=True)}">{body}</a>'
        changed += 1
        return f'<span class="source-not-hosted">{body} (external full-text source; not hosted here)</span>'

    updated = anchor_re.sub(localize, source)
    if updated != source:
        page.write_text(updated, encoding="utf-8", newline="\n")
    return changed


def _update_collection_index(
    page: Path,
    relative_page: Path,
    counts_by_route: dict[str, int],
    archive_content: dict[str, bool],
) -> int:
    """Preserve existing collection page content while correcting its edition counts."""
    source = page.read_text(encoding="utf-8")
    updated = source.replace("<th>Texts</th>", "<th>CC0/PD editions</th>")
    row_re = re.compile(
        r'<tr><td>(?P<canonical_id>.*?)</td><td><a href="(?P<href>[^"]+)">(?P<title>.*?)</a></td><td>\d+</td></tr>',
        re.DOTALL,
    )
    changed_rows = 0

    def update_row(match: re.Match) -> str:
        nonlocal changed_rows
        href = unquote(urlsplit(match.group("href")).path)
        route = posixpath.normpath(posixpath.join(relative_page.parent.as_posix(), href))
        count = counts_by_route.get(route, 0)
        changed_rows += 1
        return (
            f'<tr><td>{match.group("canonical_id")}</td><td><a href="{match.group("href")}">'
            f'{match.group("title")}</a></td><td>{count}</td></tr>'
        )

    updated = row_re.sub(update_row, updated)
    anchor_re = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a\s*>", re.IGNORECASE | re.DOTALL)
    href_re = re.compile(r"\bhref\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)

    def label_empty_download(match: re.Match) -> str:
        href_match = href_re.search(match.group("attrs"))
        if not href_match:
            return match.group(0)
        parsed = urlsplit(html.unescape(href_match.group(2)))
        if parsed.scheme or parsed.netloc or not parsed.path:
            return match.group(0)
        target = posixpath.normpath(posixpath.join(relative_page.parent.as_posix(), unquote(parsed.path)))
        if not target.startswith("downloads/"):
            return match.group(0)
        name = PurePosixPath(target).name
        if name not in archive_content or archive_content[name] or "notice only" in match.group("body").casefold():
            return match.group(0)
        return f'<a{match.group("attrs")}>{match.group("body")} — no eligible files; notice only</a>'

    updated = anchor_re.sub(label_empty_download, updated)
    if changed_rows and "<th>CC0/PD editions</th>" not in updated:
        raise ValueError(f"Could not relabel edition counts in {relative_page}")
    if relative_page.as_posix() == "sutta/khuddaka-nikaya/jataka/index.html":
        updated = updated.replace(
            "Individual revised stories are available on each story page.",
            "The revised stories are not hosted in this build because their license is CC BY-SA 4.0, outside the CC0/public-domain policy.",
        )
    if relative_page.as_posix() == "sutta/khuddaka-nikaya/petakopadesa/index.html":
        updated = updated.replace(
            "Complete English text in all nine SuttaCentral sections Pe 1–9, matched to all nine Pali text IDs, plus the 223-page scan of the printed edition through page 402, including all eight divisions, indexes, glossary, and appendix.",
            "The complete source text and scan are not included here because their CC BY-NC license does not meet the CC0/public-domain policy.",
        )
    for collection in ("petavatthu", "vimanavatthu"):
        if relative_page.as_posix() == f"sutta/khuddaka-nikaya/{collection}/index.html":
            updated = updated.replace(
                "this site hosts each complete individual sutta under that permission and links to the full collection rather than reproducing it as a book.",
                "this strict build does not host those translations because the permission is not a CC0 or public-domain license.",
            )
            updated = re.sub(
                r"All (?:51|85) complete Sutta Friends .*?stories are hosted as separate texts under its individual-sutta sharing permission\.",
                "Sutta Friends translations are not hosted in this build under the CC0/public-domain-only policy.",
                updated,
                count=1,
            )
            updated = re.sub(
                r"The source index below links to all (?:51|85) Sutta Friends stories\.",
                "The list below links to local text-availability pages.",
                updated,
                count=1,
            )
    if updated != source:
        page.write_text(updated, encoding="utf-8", newline="\n")
    return changed_rows


def _text_group_label(canonical_id: str) -> str:
    match = re.match(r"^(\D+?)\s*(\d+)(?:\.(\d+))?", canonical_id)
    if not match:
        return canonical_id
    prefix, number, subsection = match.groups()
    if subsection:
        return f"{prefix.strip()} {int(number)}"
    value = int(number)
    start = ((value - 1) // 25) * 25 + 1
    end = start + 24
    return f"{prefix.strip()} {start}–{end}"


def _display_canonical_title(canonical_id: str, title: str) -> str:
    """Normalize a navigation label without repeating its canonical ID."""
    canonical_id = canonical_id.strip()
    title = title.strip()
    if title.casefold() == canonical_id.casefold():
        return canonical_id
    if title.casefold().startswith(canonical_id.casefold()):
        title = title[len(canonical_id):].lstrip(" \t:—–-")
    if title.casefold().endswith(canonical_id.casefold()):
        title = title[:-len(canonical_id)].rstrip(" \t:—–-")
    return f"{canonical_id} — {title}" if title else canonical_id


def _sutta_breadcrumb_markup(
    tipitaka_root: Path,
    current_page: Path,
    collection: str,
    canonical_id: str | None = None,
) -> str:
    """Render the full Sutta hierarchy for a collection or canonical text page."""
    items = [
        ("Home", tipitaka_root / "site/index.html"),
        ("Tipiṭaka", tipitaka_root / "site/tipitaka.html"),
        ("Sutta Piṭaka", tipitaka_root / "site/sutta.html"),
    ]
    if collection != "sutta":
        parts = collection.split("/")
        for length in range(1, len(parts) + 1):
            node = "/".join(parts[:length])
            label = COLLECTION_TITLES.get(node, parts[length - 1].replace("-", " ").title())
            items.append((label, tipitaka_root / "sutta" / Path(*parts[:length]) / "index.html"))
    links = [
        f'<a href="{html.escape(_relative_href(current_page, target), quote=True)}">{html.escape(label)}</a>'
        for label, target in items
    ]
    if canonical_id:
        links.append(f'<span aria-current="page">{html.escape(canonical_id)}</span>')
    else:
        links[-1] = f'<span aria-current="page">{html.escape(items[-1][0])}</span>'
    return '<nav aria-label="Breadcrumb">' + " → ".join(links) + "</nav>"


def _collection_browse_markup(
    tipitaka_root: Path,
    collection: str,
    canonical_pages: dict[str, dict],
    collection_names: set[str],
) -> str:
    index_path = (
        tipitaka_root / "site/sutta.html" if collection == "sutta"
        else tipitaka_root / "sutta" / collection / "index.html"
    )
    descendants = [
        (route, info) for route, info in canonical_pages.items()
        if collection == "sutta"
        or info["collection"] == collection
        or info["collection"].startswith(collection + "/")
    ]
    descendants.sort(key=lambda pair: natural_key(pair[1]["canonical_id"]))
    def render_tree(node: str) -> str:
        output: list[str] = []
        children = sorted(
            [name for name in collection_names
             if (node == "sutta" and name != "sutta" and "/" not in name)
             or (name.startswith(node + "/") and "/" not in name[len(node) + 1:])],
            key=natural_key,
        )
        for child in children:
            child_index = tipitaka_root / "sutta" / child / "index.html"
            child_title = COLLECTION_TITLES.get(child, child.rsplit("/", 1)[-1].replace("-", " ").title())
            href = html.escape(_relative_href(index_path, child_index), quote=True)
            output.append(
                f'<details><summary>{html.escape(child_title)} — expand</summary>'
                f'<p><a href="{href}">Open {html.escape(child_title)} collection page</a></p>'
                f'{render_tree(child)}</details>'
            )
        direct = [
            (route, info) for route, info in canonical_pages.items()
            if info["collection"] == node
        ]
        groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for route, info in direct:
            groups[_text_group_label(info["canonical_id"])].append((route, info))
        for label, rows in sorted(groups.items(), key=lambda pair: natural_key(pair[0])):
            rows.sort(key=lambda pair: natural_key(pair[1]["canonical_id"]))
            output.append(f'<details><summary>{html.escape(label)} — expand ({len(rows)} texts)</summary><ul>')
            for route, info in rows:
                href = html.escape(_relative_href(index_path, tipitaka_root / route), quote=True)
                label_text = html.escape(_display_canonical_title(info["canonical_id"], info["title"]))
                count = len(info["eligible"])
                availability = f"{count} eligible edition{'s' if count != 1 else ''}"
                if not count:
                    availability = "no eligible local edition"
                output.append(
                    f'<li><a href="{href}">{label_text}</a> — {availability}</li>'
                )
            output.append("</ul></details>")
        if not output:
            output.append("<p>No indexed texts or subcollections are mapped here.</p>")
        return "\n".join(output)

    tree = render_tree(collection)
    listing = []
    for route, info in descendants:
        href = html.escape(_relative_href(index_path, tipitaka_root / route), quote=True)
        title = info["title"].strip()
        label_text = html.escape(_display_canonical_title(info["canonical_id"], info["title"]))
        availability = len(info["eligible"])
        search = html.escape(f'{info["canonical_id"]} {title}'.casefold(), quote=True)
        status = f"{availability} eligible edition{'s' if availability != 1 else ''}"
        if not availability:
            status = "no eligible local edition"
        listing.append(
            f'<li data-search="{search}"><a href="{href}">Open text page: {label_text}</a> — {status}</li>'
        )

    read_url = "/theravada/tipitaka/site/read.html?collection=" + quote(collection, safe="/-")
    count = len(descendants)
    browse = (
        '<section id="collection-browser" aria-labelledby="collection-browser-title">'
        '<h2 id="collection-browser-title">Browse this collection</h2>'
        '<nav aria-label="Collection views">'
        '<button type="button" data-mode="tree" aria-pressed="true">Tree</button> '
        '<button type="button" data-mode="list" aria-pressed="false">Flat list</button> '
        f'<a href="{html.escape(read_url, quote=True)}">Read</a></nav>'
        '<div data-view="tree" aria-label="Collection tree">'
        f'<p>{count} indexed texts. Expand a group to browse; use its separate link to open a collection page.</p>'
        f'{tree}</div>'
        '<div data-view="list" hidden>'
        '<h3>Flat list</h3><p>Search all texts in this collection and its subcollections.</p>'
        '<label>Search titles and numbers: '
        '<input type="search" data-list-search autocomplete="off"></label>'
        '<ul data-list-results>' + "\n".join(listing) + "</ul></div>"
        '<script>(function(){'
        'const root=document.getElementById("collection-browser");if(!root)return;'
        'const buttons=root.querySelectorAll("button[data-mode]");'
        'const panes=root.querySelectorAll("[data-view]");'
        'const requestedMode=new URLSearchParams(location.search).get("view");'
        'const initialMode=requestedMode==="list"?"list":"tree";'
        'buttons.forEach(function(button){button.setAttribute("aria-pressed",String(button.dataset.mode===initialMode));});'
        'panes.forEach(function(pane){pane.hidden=pane.dataset.view!==initialMode;});'
        'buttons.forEach(function(button){button.addEventListener("click",function(){'
        'const mode=button.dataset.mode;buttons.forEach(function(item){'
        'item.setAttribute("aria-pressed",String(item===button));});'
        'panes.forEach(function(pane){pane.hidden=pane.dataset.view!==mode;});});});'
        'const search=root.querySelector("[data-list-search]");'
        'if(search)search.addEventListener("input",function(){const term=search.value.trim().toLocaleLowerCase();'
        'root.querySelectorAll("[data-list-results] li").forEach(function(item){'
        'item.hidden=!item.dataset.search.includes(term);});});})();</script></section>'
    )

    source = index_path.read_text(encoding="utf-8")
    if 'id="collection-browser"' in source:
        return ""
    if 'aria-label="Breadcrumb"' not in source:
        heading_end = source.lower().find("</h1>")
        if heading_end < 0:
            raise ValueError(f"Collection index has no h1 heading: {index_path}")
        heading_end += len("</h1>")
        breadcrumb = _sutta_breadcrumb_markup(tipitaka_root, index_path, collection)
        source = source[:heading_end] + "\n" + breadcrumb + source[heading_end:]
    body_end = source.lower().rfind("</body>")
    if body_end < 0:
        raise ValueError(f"Collection index has no body end tag: {index_path}")
    download = re.search(
        r'<p\b[^>]*>.*?Download this collection.*?</p>', source, re.IGNORECASE | re.DOTALL
    )
    if download:
        insertion = download.end()
    else:
        marker = re.search(
            r'<(?:table|details|h2\b|ul\b)', source, re.IGNORECASE
        )
        insertion = marker.start() if marker else source.find("</h1>") + len("</h1>")
    legacy = source[insertion:body_end].strip()
    wrapper = ""
    if legacy:
        wrapper = (
            '<details><summary>Full existing index and collection notes</summary>\n'
            + legacy + "\n</details>\n"
        )
    updated = source[:insertion] + "\n" + browse + "\n" + wrapper + source[body_end:]
    index_path.write_text(updated, encoding="utf-8", newline="\n")
    return browse


_CONTINUOUS_READER_SCRIPT = r'''<script>
(async function(){
  const dataUrl="/theravada/tipitaka/site/reading-index.json";
  const params=new URLSearchParams(location.search);
  const selectedCollection=params.get("collection")||"";
  const status=document.getElementById("reader-status");
  function setStatus(message){status.textContent=message;}
  try {
    const response=await fetch(dataUrl,{cache:"no-cache"});
    if(!response.ok)throw new Error("The reading index could not be loaded.");
    const data=await response.json();
    const collectionMap=new Map(data.collections.map(item=>[item.id,item]));
    const current=collectionMap.get(selectedCollection);
    if(!current)throw new Error("Choose a collection from its contents page.");
    document.title=current.title+" — Read continuously";
    document.getElementById("reader-title").textContent=current.title;
    const crumbs=document.getElementById("reader-breadcrumbs");
    const crumbItems=[
      ["Home","/theravada/tipitaka/site/index.html"],
      ["Tipitaka","/theravada/tipitaka/site/tipitaka.html"],
      ["Sutta Pitaka","/theravada/tipitaka/site/sutta.html"]
    ];
    const pieces=selectedCollection==="sutta"?[]:selectedCollection.split("/");
    pieces.forEach(function(_part,index){
      const id=pieces.slice(0,index+1).join("/");
      const node=collectionMap.get(id);
      if(node)crumbItems.push([node.title,"/theravada/tipitaka/sutta/"+id+"/index.html"]);
    });
    crumbItems.forEach(function(item,index){
      if(index)crumbs.append(document.createTextNode(" → "));
      const link=document.createElement("a");link.href=item[1];link.textContent=item[0];crumbs.append(link);
    });
    const collectionIndexUrl=selectedCollection==="sutta"
      ?"/theravada/tipitaka/site/sutta.html"
      :"/theravada/tipitaka/sutta/"+selectedCollection+"/index.html";
    const viewSwitch=document.getElementById("reader-view-switcher");
    [["Tree",collectionIndexUrl],["Flat list",collectionIndexUrl+"?view=list"]].forEach(function(item,index){
      if(index)viewSwitch.append(document.createTextNode(" · "));
      const link=document.createElement("a");link.href=item[1];link.textContent=item[0];viewSwitch.append(link);
    });
    viewSwitch.append(document.createTextNode(" · "));
    const currentView=document.createElement("span");currentView.setAttribute("aria-current","page");
    currentView.textContent="Read";viewSwitch.append(currentView);
    const texts=data.texts.filter(function(item){
      return selectedCollection==="sutta"||item.collection===selectedCollection||item.collection.startsWith(selectedCollection+"/");
    });
    const allChoices=new Map();
    data.texts.forEach(function(item){item.editions.forEach(function(edition){
      if(!allChoices.has(edition.id))allChoices.set(edition.id,edition.label);
    });});
    const defaultSelect=document.getElementById("default-translation");
    function getStored(key){try{return localStorage.getItem(key);}catch(_){return null;}}
    function setStored(key,value){try{localStorage.setItem(key,value);}catch(_){setStatus("Browser storage is unavailable; choices will last only while this page is open.");}}
    const savedDefault=getStored("freebuddhism-reading-default");
    const sujato=[...data.texts.flatMap(function(item){return item.editions;})]
      .find(function(edition){return /sujato/i.test(edition.translator+" "+edition.label);});
    const orderedChoices=[...allChoices.entries()].sort(function(a,b){
      const aSujato=/sujato/i.test(a[1]);const bSujato=/sujato/i.test(b[1]);
      if(aSujato!==bSujato)return aSujato?-1:1;
      return a[1].localeCompare(b[1]);
    });
    defaultSelect.add(new Option("Choose a default translation", ""));
    orderedChoices.forEach(function(item){defaultSelect.add(new Option(item[1],item[0]));});
    const initialDefault=savedDefault&&allChoices.has(savedDefault)
      ?savedDefault:(sujato?sujato.id:(orderedChoices[0]&&orderedChoices[0][0])||"");
    defaultSelect.value=initialDefault;
    const contents=document.getElementById("reader-contents");
    const sections=document.getElementById("reader-texts");
    const overridesKey="freebuddhism-reading-overrides";
    function getOverrides(){try{return JSON.parse(getStored(overridesKey)||"{}");}catch(_){return {};}}
    if(!texts.length){setStatus("No eligible local texts are available in this collection.");return;}
    setStatus("The chosen translation is used where available; otherwise the next eligible edition is used and labeled.");
    const observer="IntersectionObserver" in window?new IntersectionObserver(function(entries){
      entries.forEach(function(entry){if(entry.isIntersecting){
        entry.target.dataset.visited="true";entry.target._load();observer.unobserve(entry.target);
      }});
    },{rootMargin:"900px 0px"}):null;
    function makeSection(item){
      const section=document.createElement("section");section.className="continuous-text";
      section.id=item.slug;
      const heading=document.createElement("h2");heading.id=item.slug+"-heading";
      const anchor=document.createElement("a");anchor.href="#"+item.slug;
      anchor.textContent=item.title;heading.append(anchor);section.append(heading);
      const label=document.createElement("label");label.className="edition-choice";label.hidden=true;
      label.append(document.createTextNode("Translation for this text: "));
      const select=document.createElement("select");select.setAttribute("aria-label","Translation for "+item.canonical_id);
      select.add(new Option("Use collection default", ""));
      item.editions.forEach(function(edition){select.add(new Option(edition.label,edition.id));});
      label.append(select);section.append(label);
      const notice=document.createElement("p");notice.setAttribute("aria-live","polite");section.append(notice);
      const body=document.createElement("div");body.className="reader-text";section.append(body);
      let generation=0;
      async function display(){
        const overrides=getOverrides();
        const choice=overrides[item.key]||defaultSelect.value;
        select.value=overrides[item.key]||"";
        const fallbackIds=[choice,defaultSelect.value,sujato&&sujato.id]
          .concat(orderedChoices.map(function(entry){return entry[0];}));
        const seenIds=new Set();
        const edition=fallbackIds.filter(function(id){
          if(!id||seenIds.has(id))return false;seenIds.add(id);return true;
        }).map(function(id){
          return item.editions.find(function(entry){return entry.id===id;});
        }).find(function(entry){return Boolean(entry);});
        generation++;const currentGeneration=generation;body.replaceChildren();
        if(!edition){notice.textContent="No eligible translation is available for this text.";return;}
        notice.textContent="Loading "+edition.label+"…";
        try{
          const response=await fetch(edition.url);if(!response.ok)throw new Error("HTTP "+response.status);
          const source=new DOMParser().parseFromString(await response.text(),"text/html");
          const sourceText=source.querySelector(".source-text");
          const sourceArticle=source.querySelector("main article,article");
          const fragment=(sourceText||sourceArticle);
          if(!fragment)throw new Error("No reader text was found.");
          const copy=fragment.cloneNode(true);
          copy.querySelectorAll("script,iframe,object,embed,form").forEach(function(node){node.remove();});
          copy.querySelectorAll("[href]").forEach(function(node){
            const value=node.getAttribute("href");if(value)node.href=new URL(value,edition.url).href;
          });
          copy.querySelectorAll("[src]").forEach(function(node){
            const value=node.getAttribute("src");if(value)node.src=new URL(value,edition.url).href;
          });
          if(currentGeneration!==generation)return;
          body.replaceChildren(copy);
          notice.textContent=edition.id===choice
            ?"Translation: "+edition.label+"."
            :"Fallback translation: "+edition.label+" (the chosen translation is not available for this text).";
        }catch(error){
          if(currentGeneration!==generation)return;
          notice.textContent="Could not load this text here. Open the eligible edition directly: ";
          const link=document.createElement("a");link.href=edition.url;link.textContent=edition.label;notice.append(link);
        }
      }
      select.addEventListener("change",function(){
        const overrides=getOverrides();
        if(select.value)overrides[item.key]=select.value;else delete overrides[item.key];
        setStored(overridesKey,JSON.stringify(overrides));display();
      });
      item.display=display;item.section=section;section._load=display;
      const listItem=document.createElement("li");const link=document.createElement("a");
      link.href="#"+item.slug;link.textContent=item.title;listItem.append(link);contents.append(listItem);
      if(observer)observer.observe(section);else{
        const loadButton=document.createElement("button");loadButton.type="button";
        loadButton.textContent="Load this text";loadButton.addEventListener("click",function(){
          section.dataset.visited="true";display();loadButton.remove();
        });section.insertBefore(loadButton,body);
      }
      return section;
    }
    texts.forEach(function(item){sections.append(makeSection(item));});
    defaultSelect.addEventListener("change",function(){
      setStored("freebuddhism-reading-default",defaultSelect.value);
      texts.forEach(function(item){if(item.section.dataset.visited)item.display();});
      setStatus("Default saved on this device. Texts without it use the next eligible edition, labeled under the text.");
    });
    document.getElementById("apply-default").addEventListener("click",function(){
      setStored("freebuddhism-reading-default",defaultSelect.value);
      texts.forEach(function(item){if(item.section.dataset.visited)item.display();});
      setStatus("Default applied where available; other texts use the next eligible edition. Individual overrides are unchanged.");
    });
    document.getElementById("customize-editions").addEventListener("click",function(event){
      const expanded=event.currentTarget.getAttribute("aria-expanded")!=="true";
      event.currentTarget.setAttribute("aria-expanded",String(expanded));
      event.currentTarget.textContent=expanded?"Hide individual translation choices":"Customize individual texts";
      sections.querySelectorAll(".edition-choice").forEach(function(label){label.hidden=!expanded;});
    });
    let textScale=1;
    function updateTextScale(){sections.style.setProperty("--reader-text-size",textScale.toFixed(1)+"em");}
    document.getElementById("text-smaller").addEventListener("click",function(){
      textScale=Math.max(0.8,textScale-0.1);updateTextScale();
    });
    document.getElementById("text-larger").addEventListener("click",function(){
      textScale=Math.min(1.6,textScale+0.1);updateTextScale();
    });
    document.getElementById("contents-search").addEventListener("input",function(event){
      const term=event.target.value.trim().toLocaleLowerCase();
      contents.querySelectorAll("li").forEach(function(item){item.hidden=!item.textContent.toLocaleLowerCase().includes(term);});
    });
  }catch(error){setStatus(error.message||"The continuous reader could not be prepared.");}
})();
</script>'''


def _write_continuous_reader(
    tipitaka_root: Path,
    canonical_pages: dict[str, dict],
    allowed: dict[Path, dict],
) -> int:
    collection_names = set(COLLECTION_TITLES) | {"sutta"}
    for info in canonical_pages.values():
        parts = info["collection"].split("/")
        collection_names.update("/".join(parts[:length]) for length in range(1, len(parts) + 1))
    for name in sorted(collection_names):
        collection_names.update(
            "/".join(name.split("/")[:length]) for length in range(1, len(name.split("/")) + 1)
        )
    collection_rows = [
        {"id": name, "title": "Sutta Pitaka" if name == "sutta" else COLLECTION_TITLES.get(name, name.rsplit("/", 1)[-1].replace("-", " ").title())}
        for name in sorted(collection_names, key=natural_key)
    ]
    text_rows = []
    for route, info in sorted(
        canonical_pages.items(), key=lambda pair: (natural_key(pair[1]["canonical_id"]), pair[1]["collection"])
    ):
        if not info["eligible"]:
            continue
        editions = []
        for record in sorted(info["eligible"], key=lambda item: item["version_label"].casefold()):
            reader = _record_relative_path(record, "html_path", Path(record["output_root"]), ROOT)
            editions.append({
                "id": record["version"],
                "label": record["version_label"],
                "translator": record["translator"],
                "url": "/theravada/tipitaka/" + reader.as_posix(),
            })
        display = _display_canonical_title(info["canonical_id"], info["title"])
        text_rows.append({
            "canonical_id": info["canonical_id"],
            "title": display,
            "collection": info["collection"],
            "slug": canonical_slug(info["canonical_id"]),
            "key": route.removesuffix("/index.html"),
            "editions": editions,
        })
    payload = {
        "canonical_count": len(canonical_pages),
        "collections": collection_rows,
        "texts": text_rows,
    }
    data_path = tipitaka_root / "site" / "reading-index.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    allowed[Path("site/reading-index.json")] = {
        "source": data_path, "kind": "json", "collection": None, "archive": False
    }
    page = tipitaka_root / "site" / "read.html"
    page.write_text(
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>Read continuously</title>\n<style>.reader-text{font-size:var(--reader-text-size,1em)}.reader-text pre{font:inherit;white-space:pre-wrap}</style>\n'
        '</head>\n<body>\n<nav><a href="index.html">Home</a> · '
        '<a href="tipitaka.html">Tipitaka</a> · <a href="sutta.html">Sutta Pitaka</a></nav>\n'
        '<nav id="reader-breadcrumbs" aria-label="Breadcrumb"></nav>\n'
        '<main><h1 id="reader-title">Read continuously</h1>\n'
        '<nav id="reader-view-switcher" aria-label="Collection views"></nav>\n'
        '<p id="reader-status" role="status">Preparing the continuous reader…</p>\n'
        '<section><h2>Reading preferences</h2>\n'
        '<label>Default translation: <select id="default-translation"></select></label> '
        '<button type="button" id="apply-default">Apply to available texts</button>\n'
        '<p>Preferences are saved in this browser. If the chosen translation is missing, Sujato is tried next; otherwise the first eligible edition in the list is used. The translation used is labeled under each text.</p>\n'
        '<button type="button" id="customize-editions" aria-expanded="false">Customize individual texts</button> '
        '<button type="button" id="text-smaller" aria-label="Make text smaller">Text −</button> '
        '<button type="button" id="text-larger" aria-label="Make text larger">Text +</button></section>\n'
        '<details><summary>Contents</summary><label>Search contents: '
        '<input type="search" id="contents-search" autocomplete="off"></label>\n'
        '<ol id="reader-contents"></ol></details>\n'
        '<div id="reader-texts"></div></main>\n'
        + _CONTINUOUS_READER_SCRIPT + '\n</body>\n</html>\n',
        encoding="utf-8", newline="\n",
    )
    _register_generated_page(allowed, tipitaka_root, page, None)
    return len(text_rows)


def _write_collection_browsers(
    tipitaka_root: Path,
    canonical_pages: dict[str, dict],
    collections: dict[str, list],
) -> int:
    names = set(collections) | set(COLLECTION_TITLES) | {"sutta"}
    written = 0
    for collection in sorted(names, key=natural_key):
        index_path = (
            tipitaka_root / "site/sutta.html" if collection == "sutta"
            else tipitaka_root / "sutta" / collection / "index.html"
        )
        if not index_path.is_file():
            continue
        _collection_browse_markup(tipitaka_root, collection, canonical_pages, names)
        written += 1
    return written


def _register_generated_page(allowed: dict[Path, dict], tipitaka_root: Path, path: Path, collection: str | None) -> None:
    relative = _safe_relative(path.relative_to(tipitaka_root))
    allowed[relative] = {"source": path, "kind": "html", "collection": collection, "archive": False}


def _write_vimanavatthu_story_pages(tipitaka_root: Path, allowed: dict[Path, dict]) -> int:
    """Keep legacy individual-story links local using metadata-only availability pages."""
    collection = Path("sutta/khuddaka-nikaya/vimanavatthu")
    index = tipitaka_root / collection / "index.html"
    if not index.is_file():
        return 0
    pattern = re.compile(
        r'<li>\s*<a href="vv(?P<chapter>\d{2})-(?P<story>\d{2})/index\.html">'
        r"(?P<title>.*?)</a>\s*</li>",
        re.DOTALL,
    )
    entries = list(pattern.finditer(index.read_text(encoding="utf-8")))
    for match in entries:
        chapter = int(match.group("chapter"))
        story = int(match.group("story"))
        target = tipitaka_root / collection / f"vv{chapter:02d}-{story:02d}" / "index.html"
        relative = _safe_relative(target.relative_to(tipitaka_root))
        if relative in allowed:
            continue
        chapter_page = tipitaka_root / collection / f"vv{chapter:02d}" / "index.html"
        if not chapter_page.is_file():
            raise ValueError(f"Vimānavatthu story has no chapter availability page: Vv {chapter}.{story}")
        label = html.unescape(re.sub(r"<[^>]+>", "", match.group("title")))
        label = re.sub(r"^Vv\s+\d+\.\d+\s*", "", label)
        title = f"Vv {chapter}.{story} — {label}"
        chapter_href = html.escape(_relative_href(target, chapter_page), quote=True)
        body = (
            f"<h1>{html.escape(title)}</h1>"
            "<p>No standalone English edition for this individual story is included under the CC0 or verified-public-domain policy.</p>"
            f'<p>See <a href="{chapter_href}">Vv {chapter} edition availability</a>.</p>'
            "<p>Rights and translation completeness are assessed separately; this page does not classify the completeness of a larger edition.</p>"
        )
        _write_page(target, title, body, tipitaka_root)
        _register_generated_page(allowed, tipitaka_root, target, "khuddaka-nikaya/vimanavatthu")
    return len(entries)


def _write_unavailable_page(
    path: Path,
    title: str,
    detail: str,
    tipitaka_root: Path,
    reason: str = "This edition is not included in the local website build because it has not cleared the CC0 or verified-public-domain reuse policy.",
) -> None:
    body = (
        f"<h1>{html.escape(title)}</h1>"
        f"<p>{html.escape(reason)}</p>"
        f"<p>{html.escape(detail)}</p>"
        "<p>Rights clearance and translation completeness are assessed separately. An unavailable edition is not a claim that no translation exists.</p>"
    )
    _write_page(path, title, body, tipitaka_root)


def _vinaya_source_group(source_id: str) -> str:
    if re.fullmatch(r"pli-tv-kd\d+", source_id):
        return "khandhaka"
    if source_id == "pli-tv-bu-pm":
        return "bhikkhu-patimokkha"
    if source_id == "pli-tv-bi-pm":
        return "bhikkhuni-patimokkha"
    if source_id.startswith("pli-tv-bu-vb-"):
        return "bhikkhu-vibhanga"
    if source_id.startswith("pli-tv-bi-vb-"):
        return "bhikkhuni-vibhanga"
    if source_id.startswith("pli-tv-pvr"):
        return "parivara"
    raise ValueError(f"Unrecognized Brahmali Vinaya source identifier: {source_id}")


def _vinaya_reference(source_id: str) -> tuple[str, str]:
    if source_id == "pli-tv-bu-pm":
        return "Bhikkhu Pātimokkha", "Monks’ Rules"
    if source_id == "pli-tv-bi-pm":
        return "Bhikkhunī Pātimokkha", "Nuns’ Rules"
    rule = re.fullmatch(r"pli-tv-(bu|bi)-vb-(as|ay|np|pc|pd|pj|sk|ss)(\d+(?:-\d+)?)", source_id)
    if rule:
        person = "Bhikkhu" if rule.group(1) == "bu" else "Bhikkhunī"
        pali, english = VINAYA_RULE_CLASSES[rule.group(2)]
        number = rule.group(3).replace("-", "–")
        return f"{person} {pali} {number}", english
    parivara = re.fullmatch(r"pli-tv-pvr(\d+(?:\.\d+)?)", source_id)
    if parivara:
        return f"Parivāra {parivara.group(1)}", "Vinaya Compendium"
    khandhaka = re.fullmatch(r"pli-tv-kd(\d+)", source_id)
    if khandhaka:
        return f"Kd {khandhaka.group(1)}", "Khandhaka chapter"
    raise ValueError(f"Cannot render a readable Vinaya reference for {source_id}")


def _load_vinaya_khandhaka_menu(path: Path = VINAYA_KHANDHAKA_MENU) -> dict[str, dict[str, str]]:
    menu = json.loads(path.read_text(encoding="utf-8"))
    if menu.get("schema_version") != 1 or menu.get("source", {}).get("url") != "https://suttacentral.net/api/menu/pli-tv-kd":
        raise ValueError("Vinaya Khandhaka title metadata has an unknown schema or source")
    if menu.get("source", {}).get("license") != "CC0-1.0 reference metadata" or menu.get("source", {}).get("license_basis_url") != "https://suttacentral.net/licensing":
        raise ValueError("Vinaya Khandhaka reference metadata lacks the recorded CC0 basis")
    chapters = menu.get("chapters")
    if not isinstance(chapters, list) or len(chapters) != 22:
        raise ValueError("Vinaya Khandhaka title metadata must contain 22 chapters")
    result: dict[str, dict[str, str]] = {}
    for expected, chapter in enumerate(chapters, start=1):
        if set(chapter) != {"uid", "pali_title", "english_title", "group"}:
            raise ValueError("Vinaya Khandhaka metadata has unexpected fields")
        if chapter.get("uid") != f"pli-tv-kd{expected}" or chapter.get("group") != ("mahavagga" if expected <= 10 else "cullavagga"):
            raise ValueError("Vinaya Khandhaka metadata has an incorrect chapter order or grouping")
        if not chapter.get("pali_title") or not chapter.get("english_title"):
            raise ValueError(f"Vinaya Khandhaka metadata is incomplete: {chapter.get('uid')}")
        result[chapter["uid"]] = chapter
    return result


def _load_anguttara_menu(path: Path = ANGUTTARA_MENU) -> dict:
    menu = json.loads(path.read_text(encoding="utf-8"))
    if menu.get("schema_version") != 1 or menu.get("source", {}).get("url") != "https://suttacentral.net/api/menu/an":
        raise ValueError("Aṅguttara title metadata has an unknown schema or source")
    if menu.get("source", {}).get("license") != "CC0-1.0 reference metadata" or menu.get("source", {}).get("license_basis_url") != "https://suttacentral.net/licensing":
        raise ValueError("Aṅguttara reference metadata lacks the recorded CC0 basis")
    books = menu.get("books")
    if not isinstance(books, list) or not books:
        raise ValueError("Aṅguttara title metadata has no book hierarchy")
    seen_books: set[str] = set()
    seen_ranges: set[str] = set()
    for book in books:
        if set(book) != {"uid", "pali_title", "english_title", "range", "chapters"}:
            raise ValueError("Aṅguttara book metadata has unexpected fields")
        if book["uid"] in seen_books or not all(book.get(key) for key in ("pali_title", "english_title", "range")):
            raise ValueError("Aṅguttara book metadata is incomplete or duplicated")
        seen_books.add(book["uid"])
        if not isinstance(book["chapters"], list) or not book["chapters"]:
            raise ValueError(f"Aṅguttara book has no chapter metadata: {book['uid']}")
        for chapter in book["chapters"]:
            if set(chapter) != {"uid", "pali_title", "english_title", "range"}:
                raise ValueError("Aṅguttara chapter metadata has unexpected fields")
            if not all(chapter.get(key) for key in ("uid", "pali_title", "english_title", "range")):
                raise ValueError("Aṅguttara chapter metadata is incomplete")
            if chapter["range"] in seen_ranges:
                raise ValueError(f"Duplicate Aṅguttara chapter range: {chapter['range']}")
            seen_ranges.add(chapter["range"])
            if _parse_an_range(chapter["range"]) is None:
                raise ValueError(f"Unrecognized Aṅguttara chapter range: {chapter['range']}")
    return menu


def _parse_an_range(value: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"AN\s+(\d+)\.(\d+)(?:\s*[–-]\s*(\d+))?", value.strip())
    if not match:
        return None
    book, start, end = match.groups()
    return int(book), int(start), int(end or start)


def _update_tipitaka_tree_counts(page: str, counts: dict[str, str]) -> str:
    start = page.find('<ul id="tipitaka-tree">')
    if start < 0:
        raise ValueError("Tipiṭaka page has no canonical collection tree")
    end = page.find("</ul>\n<p>The text index retains", start)
    if end < 0:
        raise ValueError("Could not locate the end of the Tipiṭaka collection tree")
    end += len("</ul>")
    tree = page[start:end]
    tree_hrefs = re.findall(r'<a href="([^"]+)"', tree)
    labels = dict(counts)
    for href in tree_hrefs:
        if href.startswith("../sutta/"):
            labels.setdefault(href, "0 indexed entries; 0 eligible editions")
        elif href.startswith("../abhidhamma/"):
            labels.setdefault(href, "no eligible local English edition")
        elif href.startswith("../vinaya/"):
            labels.setdefault(href, "0 indexed source entries")
    for href, label in labels.items():
        if href not in tree_hrefs:
            continue
        pattern = re.compile(
            r'(<a href="' + re.escape(href) + r'"[^>]*>[^<]*</a>)'
            r'(?:\s+—\s+[^<]*)?(</summary>)'
        )
        tree, changed = pattern.subn(lambda match: f"{match.group(1)} — {html.escape(label)}{match.group(2)}", tree, count=1)
        if changed != 1:
            raise ValueError(f"Could not set the Tipiṭaka tree count for {href}")
    return page[:start] + tree + page[end:]


def _write_anguttara_index(
    tipitaka_root: Path,
    canonical_pages: dict[str, dict],
    counts_by_route: dict[str, int],
    allowed: dict[Path, dict],
) -> int:
    menu = _load_anguttara_menu()
    entries = [
        (route, info) for route, info in canonical_pages.items()
        if info["collection"] == "anguttara-nikaya"
    ]
    assigned: dict[str, list[tuple[str, dict]]] = {chapter["range"]: [] for book in menu["books"] for chapter in book["chapters"]}
    for route, info in entries:
        item_range = _parse_an_range(info["canonical_id"])
        if item_range is None:
            raise ValueError(f"Unrecognized Aṅguttara source reference: {info['canonical_id']}")
        book, item_start, item_end = item_range
        matches = []
        for book_info in menu["books"]:
            for chapter in book_info["chapters"]:
                chapter_range = _parse_an_range(chapter["range"])
                if chapter_range and chapter_range[0] == book and item_start <= chapter_range[2] and item_end >= chapter_range[1]:
                    matches.append(chapter["range"])
        if len(matches) != 1:
            raise ValueError(f"Aṅguttara reference maps to {len(matches)} chapters: {info['canonical_id']}")
        assigned[matches[0]].append((route, info))
    if sum(len(rows) for rows in assigned.values()) != len(entries):
        raise ValueError("Aṅguttara chapter groups do not cover every indexed text")

    index = tipitaka_root / "sutta/anguttara-nikaya/index.html"
    body = [
        "<h1>Aṅguttara Nikāya (Numbered Discourses)</h1>",
        "<p>Browse the numbered books and their named chapters. Many entries are numbered subdivisions rather than separately titled works; their reference is kept as the text label.</p>",
        '<p><a href="../../downloads/anguttara-nikaya.zip">Download this collection</a></p>',
    ]
    for book in menu["books"]:
        book_rows = [row for chapter in book["chapters"] for row in assigned[chapter["range"]]]
        book_editions = sum(counts_by_route.get(route, 0) for route, _ in book_rows)
        book_label = f"{book['pali_title']} ({book['english_title']}) — {len(book_rows)} indexed entries; {book_editions} eligible editions"
        body.append(f"<details><summary>{html.escape(book_label)}</summary>")
        for chapter in book["chapters"]:
            chapter_rows = sorted(assigned[chapter["range"]], key=lambda row: natural_key(row[1]["canonical_id"]))
            edition_total = sum(counts_by_route.get(route, 0) for route, _ in chapter_rows)
            label = (
                f"{chapter['pali_title']} ({chapter['english_title']}) — {chapter['range']} — "
                f"{len(chapter_rows)} indexed entries; {edition_total} eligible editions"
            )
            body.append(f"<details><summary>{html.escape(label)}</summary>")
            body.append("<table><thead><tr><th>Reference</th><th>Eligible local editions</th></tr></thead><tbody>")
            for route, info in chapter_rows:
                destination = tipitaka_root / route
                count = counts_by_route.get(route, 0)
                body.append(
                    f'<tr><td><a href="{html.escape(_relative_href(index, destination), quote=True)}">'
                    f'{html.escape(info["canonical_id"])}</a></td><td>{count}</td></tr>'
                )
            body.append("</tbody></table></details>")
        body.append("</details>")
    _write_page(index, "Aṅguttara Nikāya (Numbered Discourses)", "\n".join(body), tipitaka_root)
    _register_generated_page(allowed, tipitaka_root, index, "anguttara-nikaya")
    return len(entries)


def _write_vinaya_indexes(
    tipitaka_root: Path,
    records: list[dict],
    allowed: dict[Path, dict],
) -> dict:
    ledger_path = PUBLIC_TIPITAKA / "vinaya" / "suttacentral-brahmali-vinaya-ledger.tsv"
    with ledger_path.open(encoding="utf-8", newline="") as handle:
        ledger_rows = list(csv.DictReader(handle, dialect="excel-tab"))
    source_manifest = json.loads((ROOT / "metadata/source-manifests/suttacentral-brahmali-vinaya.json").read_text(encoding="utf-8"))
    khandhaka_titles = _load_vinaya_khandhaka_menu()
    review_ids = source_manifest.get("needs_review_source_ids", [])
    if len(ledger_rows) != source_manifest.get("imported_complete_files"):
        raise ValueError("Vinaya ledger count differs from its pinned source manifest")
    if len(review_ids) != source_manifest.get("needs_review_files") or len(set(review_ids)) != len(review_ids):
        raise ValueError("Vinaya passage-review IDs differ from their pinned source manifest")

    ledger_by_id = {row["source_id"]: row for row in ledger_rows}
    if len(ledger_by_id) != len(ledger_rows) or set(ledger_by_id) & set(review_ids):
        raise ValueError("Vinaya source IDs are duplicated or both imported and held for review")
    if len(ledger_by_id) + len(review_ids) != source_manifest.get("expected_english_files"):
        raise ValueError("Vinaya imported and review-required IDs do not cover the pinned source manifest")

    rows_by_group: dict[str, list[dict]] = defaultdict(list)
    for row in ledger_rows:
        if row["group"] != _vinaya_source_group(row["source_id"]):
            raise ValueError(f"Vinaya ledger group conflicts with source ID: {row['source_id']}")
        rows_by_group[row["group"]].append({**row, "review_required": False})
    for source_id in review_ids:
        title = khandhaka_titles[source_id]["pali_title"] + " (" + khandhaka_titles[source_id]["english_title"].capitalize() + ")" if source_id in khandhaka_titles else ""
        rows_by_group[_vinaya_source_group(source_id)].append({
            "source_id": source_id,
            "title": title,
            "group": _vinaya_source_group(source_id),
            "review_required": True,
        })
    for rows in rows_by_group.values():
        rows.sort(key=lambda row: natural_key(row["source_id"]))

    available_by_id: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        if record["kind"] == "vinaya":
            available_by_id[record["canonical_id"]].append(record)
    if set(available_by_id) != set(ledger_by_id):
        raise ValueError("Vinaya reader records do not match the file-level import ledger")

    selector_root = Path("vinaya/texts/index")
    selector_routes: dict[str, Path] = {}
    for group, rows in rows_by_group.items():
        for row in rows:
            source_id = row["source_id"]
            reference, category_english = _vinaya_reference(source_id)
            english_title = row.get("title", "")
            selector = tipitaka_root / selector_root / slug(source_id) / "index.html"
            selector_routes[source_id] = selector.relative_to(tipitaka_root)
            if source_id in khandhaka_titles:
                selector_body = [
                    f"<h1>{html.escape(english_title)}</h1>",
                    f"<p>Reference: {html.escape(reference)}</p>",
                ]
            else:
                selector_body = [f"<h1>{html.escape(reference)}</h1>"]
                if english_title:
                    selector_body.append(f"<p>{html.escape(english_title)}</p>")
            selector_body.append(f'<p><small>Source reference: {html.escape(source_id)}</small></p>')
            editions = sorted(available_by_id.get(source_id, []), key=lambda item: item["version_label"].casefold())
            if editions:
                selector_body.append("<h2>Available local editions</h2><ul>")
                for edition in editions:
                    reader = _record_relative_path(edition, "html_path", Path(edition["output_root"]), ROOT)
                    selector_body.append(
                        f'<li><a href="{html.escape(_relative_href(selector, tipitaka_root / reader), quote=True)}">'
                        f'{html.escape(edition["version_label"])}</a> — {html.escape(edition["license"])}</li>'
                    )
                selector_body.append("</ul>")
            else:
                selector_body.append(
                    "<p>No English reader is published for this source file. Its English segment coverage remains unresolved; "
                    "the text is withheld until passage-level review.</p>"
                )
            selector_body.append(f"<p>Rule category: {html.escape(category_english)}.</p>")
            _write_page(selector, reference, "\n".join(selector_body), tipitaka_root)
            _register_generated_page(allowed, tipitaka_root, selector, "vinaya")

    route_groups = {
        "bhikkhu-vibhanga": ["bhikkhu-patimokkha", "bhikkhu-vibhanga"],
        "bhikkhuni-vibhanga": ["bhikkhuni-patimokkha", "bhikkhuni-vibhanga"],
        "mahavagga": ["khandhaka"],
        "cullavagga": ["khandhaka"],
        "parivara": ["parivara"],
    }
    group_titles = {
        "bhikkhu-vibhanga": "Mahā Vibhaṅga (Monks’ Analysis)",
        "bhikkhuni-vibhanga": "Bhikkhunī Vibhaṅga (Nuns’ Analysis)",
        "mahavagga": "Mahāvagga (Great Chapter)",
        "cullavagga": "Cullavagga (Lesser Chapter)",
        "parivara": "Parivāra (Vinaya Compendium)",
    }
    group_status: dict[str, tuple[int, int, int]] = {}
    for route, groups in route_groups.items():
        rows = [row for group in groups for row in rows_by_group.get(group, [])]
        if route in {"mahavagga", "cullavagga"}:
            rows = [row for row in rows if khandhaka_titles[row["source_id"]]["group"] == route]
        eligible = sum(bool(available_by_id.get(row["source_id"])) for row in rows)
        pending = sum(row["review_required"] for row in rows)
        group_status[route] = (len(rows), eligible, pending)
        page = tipitaka_root / "vinaya" / route / "index.html"
        title = group_titles[route]
        body = [
            f"<h1>{html.escape(title)}</h1>",
            f"<p>{len(rows)} indexed source entries; {eligible} local editions; {pending} held for passage-level review. Counts describe source files, not distinct rule numbers.</p>",
        ]
        categories: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            source_id = row["source_id"]
            if row["group"].endswith("patimokkha"):
                category = ("Pātimokkha", "Monastic Rules")
            elif row["group"] == "khandhaka":
                category = ("Khandhaka", "Chapters")
            elif route == "parivara":
                category = ("Parivāra", "Vinaya Compendium")
            else:
                rule_match = re.fullmatch(r"pli-tv-(?:bu|bi)-vb-(as|ay|np|pc|pd|pj|sk|ss)\d+(?:-\d+)?", source_id)
                if not rule_match:
                    raise ValueError(f"Vinaya rule ID has no known rule category: {source_id}")
                category = VINAYA_RULE_CLASSES[rule_match.group(1)]
            categories[category].append(row)
        for (pali_category, english_category), category_rows in categories.items():
            category_available = sum(bool(available_by_id.get(row["source_id"])) for row in category_rows)
            body.append(
                f"<h2>{html.escape(pali_category)} ({html.escape(english_category)}) — "
                f"{len(category_rows)} indexed entries; {category_available} eligible editions</h2>"
            )
            body.append("<table><thead><tr><th>Reference</th><th>English title</th><th>Local editions</th></tr></thead><tbody>")
            for row in category_rows:
                source_id = row["source_id"]
                reference, _ = _vinaya_reference(source_id)
                selector = tipitaka_root / selector_routes[source_id]
                title_text = row.get("title") or "Not included — passage review required"
                count = len(available_by_id.get(source_id, []))
                status = str(count) if count else "Review required"
                body.append(
                    f'<tr><td><a href="{html.escape(_relative_href(page, selector), quote=True)}">{html.escape(reference)}</a>'
                    f'<br><small>{html.escape(source_id)}</small></td>'
                    f'<td>{html.escape(title_text)}</td><td>{status}</td></tr>'
                )
            body.append("</tbody></table>")
        _write_page(page, title, "\n".join(body), tipitaka_root)
        _register_generated_page(allowed, tipitaka_root, page, "vinaya")

    bhikkhu_total = group_status["bhikkhu-vibhanga"]
    bhikkhuni_total = group_status["bhikkhuni-vibhanga"]
    sutta_total = tuple(a + b for a, b in zip(bhikkhu_total, bhikkhuni_total))
    parivara_total = group_status["parivara"]

    sutta_index = tipitaka_root / "vinaya/sutta-vibhanga/index.html"
    sutta_body = [
        "<h1>Sutta Vibhaṅga (Analysis of the Rules)</h1>",
        "<p>The Vinaya collection that analyzes the monks’ and nuns’ Pātimokkha rules.</p>",
        f"<p>{sutta_total[0]} indexed source entries; {sutta_total[1]} local editions; {sutta_total[2]} held for passage-level review.</p>",
        "<ul>",
    ]
    for route, title, status in (
        ("bhikkhu-vibhanga", group_titles["bhikkhu-vibhanga"], bhikkhu_total),
        ("bhikkhuni-vibhanga", group_titles["bhikkhuni-vibhanga"], bhikkhuni_total),
    ):
        target = tipitaka_root / "vinaya" / route / "index.html"
        sutta_body.append(
            f'<li><a href="{html.escape(_relative_href(sutta_index, target), quote=True)}">{html.escape(title)}</a> — '
            f'{status[0]} indexed entries; {status[1]} local editions; {status[2]} held for review</li>'
        )
    sutta_body.append("</ul>")
    _write_page(sutta_index, "Sutta Vibhaṅga (Analysis of the Rules)", "\n".join(sutta_body), tipitaka_root)
    _register_generated_page(allowed, tipitaka_root, sutta_index, "vinaya")

    khandhaka_total = tuple(a + b for a, b in zip(group_status["mahavagga"], group_status["cullavagga"]))
    khandhaka = tipitaka_root / "vinaya/khandhaka/index.html"
    khandhaka_body = [
        "<h1>Khandhaka (Chapters)</h1>",
        f"<p>{khandhaka_total[0]} chapter entries; {khandhaka_total[1]} local editions; {khandhaka_total[2]} held for passage-level review.</p>",
        "<ul>",
    ]
    for route in ("mahavagga", "cullavagga"):
        status = group_status[route]
        target = tipitaka_root / "vinaya" / route / "index.html"
        khandhaka_body.append(
            f'<li><a href="{html.escape(_relative_href(khandhaka, target), quote=True)}">{html.escape(group_titles[route])}</a> — '
            f"{status[0]} chapter entries; {status[1]} local editions; {status[2]} held for review</li>"
        )
    khandhaka_body.append("</ul>")
    _write_page(khandhaka, "Khandhaka (Chapters)", "\n".join(khandhaka_body), tipitaka_root)
    _register_generated_page(allowed, tipitaka_root, khandhaka, "vinaya")

    vinaya_index = tipitaka_root / "vinaya/index.html"
    root_body = [
        "<h1>Vinaya Piṭaka (Monastic Discipline)</h1>",
        f"<p>{source_manifest['expected_english_files']} English source files are mapped: {source_manifest['imported_complete_files']} have local readers and {source_manifest['needs_review_files']} are withheld pending passage-level review. This does not certify the completeness of the whole translation.</p>",
        "<ul>",
        f'<li><a href="sutta-vibhanga/index.html">Sutta Vibhaṅga (Analysis of the Rules)</a> — {sutta_total[0]} indexed entries; {sutta_total[1]} local editions; {sutta_total[2]} held for review</li>',
        f'<li><a href="khandhaka/index.html">Khandhaka (Chapters)</a> — {khandhaka_total[0]} chapter entries; {khandhaka_total[1]} local editions; {khandhaka_total[2]} held for review</li>',
        f'<li><a href="parivara/index.html">Parivāra (Vinaya Compendium)</a> — {parivara_total[0]} indexed entries; {parivara_total[1]} local editions; {parivara_total[2]} held for review</li>',
        "</ul>",
    ]
    _write_page(vinaya_index, "Vinaya Piṭaka (Monastic Discipline)", "\n".join(root_body), tipitaka_root)
    _register_generated_page(allowed, tipitaka_root, vinaya_index, "vinaya")
    return {
        "source_files": source_manifest["expected_english_files"],
        "local_files": source_manifest["imported_complete_files"],
        "review_required_files": source_manifest["needs_review_files"],
        "sutta_vibhanga_entries": sutta_total[0],
        "sutta_vibhanga_local": sutta_total[1],
        "sutta_vibhanga_review_required": sutta_total[2],
        "bhikkhu_vibhanga_entries": bhikkhu_total[0],
        "bhikkhu_vibhanga_local": bhikkhu_total[1],
        "bhikkhu_vibhanga_review_required": bhikkhu_total[2],
        "bhikkhuni_vibhanga_entries": bhikkhuni_total[0],
        "bhikkhuni_vibhanga_local": bhikkhuni_total[1],
        "bhikkhuni_vibhanga_review_required": bhikkhuni_total[2],
        "khandhaka_entries": khandhaka_total[0],
        "khandhaka_local": khandhaka_total[1],
        "khandhaka_review_required": khandhaka_total[2],
        "mahavagga_entries": group_status["mahavagga"][0],
        "cullavagga_entries": group_status["cullavagga"][0],
        "parivara_entries": parivara_total[0],
        "parivara_local": parivara_total[1],
        "parivara_review_required": parivara_total[2],
    }


def _write_navigation_pages(
    tipitaka_root: Path,
    records: list[dict],
    allowed: dict[Path, dict],
    impact_map: dict,
    archive_names: list[str],
) -> dict:
    site_dir = tipitaka_root / "site"
    existing_text_index = (site_dir / "sutta-texts.html").read_text(encoding="utf-8")
    source_rows = _source_rows(existing_text_index)
    canonical_pages: dict[str, dict] = {}

    def page_info(route: str, canonical_id: str, collection: str, title: str = "") -> dict:
        info = canonical_pages.setdefault(route, {
            "canonical_id": canonical_id,
            "collection": collection,
            "title": title or canonical_id,
            "eligible": [],
            "restricted": [],
            "audio_available": False,
        })
        if title and info["title"] == info["canonical_id"] and title != canonical_id:
            info["title"] = title
        return info

    for row in source_rows:
        info = page_info(row["route"], row["canonical_id"], row["collection"], row["title"])
        info["audio_available"] = row["audio"] == "yes"

    collection_row_re = re.compile(
        r'<tr><td>(?P<canonical_id>.*?)</td><td><a href="(?P<href>[^"]+)">(?P<title>.*?)</a></td><td>\d+</td></tr>',
        re.DOTALL,
    )
    for relative_index, entry in sorted(allowed.items(), key=lambda pair: pair[0].as_posix()):
        if relative_index.parts[0] != "sutta" or relative_index.name != "index.html" or not entry.get("collection"):
            continue
        index_html = (tipitaka_root / relative_index).read_text(encoding="utf-8")
        for match in collection_row_re.finditer(index_html):
            href = unquote(urlsplit(match.group("href")).path)
            route = posixpath.normpath(posixpath.join(relative_index.parent.as_posix(), href))
            if route.startswith("../") or not route.startswith("sutta/") or not route.endswith("/index.html"):
                raise ValueError(f"Collection index row points outside the sutta tree: {relative_index}: {href}")
            route_parts = PurePosixPath(route).parts
            collection = "/".join(route_parts[1:-2])
            page_info(route, html.unescape(match.group("canonical_id")), collection, html.unescape(match.group("title")))

    for record in records:
        if record["kind"] != "sutta":
            continue
        route = Path("sutta") / record["collection"] / canonical_slug(record["canonical_id"]) / "index.html"
        page_info(route.as_posix(), record["canonical_id"], record["collection"], record["title"])["eligible"].append(record)

    blocked_file_paths: set[Path] = set()
    blocked_reader_routes: dict[Path, dict] = {}
    selected_reader_routes = {
        _record_relative_path(record, "html_path", Path(record["output_root"]), ROOT)
        for record in records
    }
    for item in impact_map.get("records", []):
        urls = item.get("published_urls", {})
        index_relative = _public_relative_path(urls.get("canonical_index", ""))
        if index_relative and item.get("canonical_id") and item.get("collection"):
            page_info(index_relative.as_posix(), item["canonical_id"], item["collection"], item.get("title", ""))["restricted"].append(item)
        for key in ("reader_txt", "reader_pdf", "source_text", "source_pdf"):
            relative = _public_relative_path(urls.get(key, ""))
            if relative:
                blocked_file_paths.add(relative)
        reader = _public_relative_path(urls.get("reader_html", ""))
        if reader:
            blocked_reader_routes[reader] = item

    for item in impact_map.get("standalone_assets", []):
        urls = item.get("published_urls", {})
        for key in ("reader_txt", "reader_pdf", "source_text", "source_pdf", "direct_file", "direct_pdf"):
            relative = _public_relative_path(urls.get(key, ""))
            if relative and relative not in allowed:
                blocked_file_paths.add(relative)
        for key in ("direct_source_text_files",):
            for url in urls.get(key, []):
                relative = _public_relative_path(url)
                if relative and relative not in allowed:
                    blocked_file_paths.add(relative)
        for key in ("reader_html", "reader_page"):
            reader = _public_relative_path(urls.get(key, ""))
            if reader:
                # The impact map also records eligible grouped assets (notably
                # the 292 CC0 Brahmali Vinaya readers). Those exact routes are
                # supplied by selected source-verified reader records; do not
                # replace them with a generic availability page.
                if item.get("rights_status") in {"ELIGIBLE_PD", "ELIGIBLE_CC0"} and reader in selected_reader_routes:
                    continue
                blocked_reader_routes[reader] = item
        for key in ("generated_story_pages", "reader_pages"):
            for url in urls.get(key, []):
                reader = _public_relative_path(url)
                if reader:
                    if item.get("rights_status") in {"ELIGIBLE_PD", "ELIGIBLE_CC0"} and reader in selected_reader_routes:
                        continue
                    blocked_reader_routes[reader] = item
        if urls.get("generated_story_pages") and item.get("rights_status") not in {"ELIGIBLE_PD", "ELIGIBLE_CC0"}:
            # Some current Jātaka pages use zero-padded URLs while the older
            # impact map records unpadded routes. Replace both URL generations.
            jataka_root = PUBLIC_TIPITAKA / "sutta/khuddaka-nikaya/jataka"
            if jataka_root.is_dir():
                for source in jataka_root.glob("ja*/ja*-anandajoti-revised.html"):
                    blocked_reader_routes[_safe_relative(source.relative_to(PUBLIC_TIPITAKA))] = item

    disabled_restricted_links = _disable_restricted_links(tipitaka_root, blocked_file_paths)

    for record in records:
        relative = _record_relative_path(record, "html_path", Path(record["output_root"]), ROOT)
        if relative in blocked_reader_routes:
            raise ValueError(f"A restricted mapped reader collides with an eligible reader: {relative}")
    for relative in blocked_reader_routes:
        if relative in allowed:
            raise ValueError(f"A restricted mapped page collides with an existing site page: {relative}")
    for relative in blocked_file_paths:
        if relative in allowed:
            raise ValueError(f"A restricted mapped file collides with an allowlisted file: {relative}")

    for relative, item in sorted(blocked_reader_routes.items(), key=lambda pair: pair[0].as_posix()):
        if relative.suffix.lower() != ".html":
            continue
        path = tipitaka_root / relative
        title = item.get("title") or item.get("canonical_id") or "Unavailable text"
        edition = item.get("source_group") or item.get("license") or "This edition"
        if item.get("rights_status") in {"ELIGIBLE_PD", "ELIGIBLE_CC0"}:
            collection = item.get("collection", "")
            pdfs = sorted(
                (relative_pdf for relative_pdf, entry in allowed.items()
                 if entry.get("archive") and entry.get("kind") == "pdf" and entry.get("collection") == collection),
                key=lambda value: value.as_posix(),
            )
            if pdfs:
                links = "<ul>" + "".join(
                    f'<li><a href="{html.escape(_relative_href(path, tipitaka_root / pdf), quote=True)}">{html.escape(pdf.name)}</a></li>'
                    for pdf in pdfs
                ) + "</ul>"
                body = (
                    f"<h1>{html.escape(title)}</h1>"
                    "<p>The historical edition is cleared as public domain in the United States. This former HTML route now links to the verified local scans; no unvalidated text transcription is included.</p>"
                    f"<p>{html.escape(str(edition))}</p>{links}"
                    "<p>Rights status does not establish translation completeness.</p>"
                )
                _write_page(path, title, body, tipitaka_root)
            else:
                _write_unavailable_page(
                    path, title, str(edition), tipitaka_root,
                    reason="This route is not part of the validated publishing allowlist. No text is served at this URL.",
                )
        else:
            detail = str(edition)
            if item.get("completeness_status"):
                detail += f". Completeness: {item['completeness_status']}."
            _write_unavailable_page(path, title, detail, tipitaka_root)
        _register_generated_page(allowed, tipitaka_root, path, item.get("collection"))

    # Keep every indexed Sutta route, including entries with no eligible local edition.
    for route, info in sorted(canonical_pages.items()):
        page = tipitaka_root / route
        canonical_id = info["canonical_id"]
        title = _display_canonical_title(canonical_id, info["title"] or canonical_id)
        breadcrumb = _sutta_breadcrumb_markup(
            tipitaka_root, page, info["collection"], canonical_id
        )
        body = [breadcrumb, f"<h1>{html.escape(title)}</h1>"]
        available = sorted(info["eligible"], key=lambda row: row["version_label"].casefold())
        if available:
            body.append("<h2>Locally available editions</h2><ul>")
            for edition in available:
                reader = _record_relative_path(edition, "html_path", Path(edition["output_root"]), ROOT)
                body.append(
                    f'<li><a href="{html.escape(_relative_href(page, tipitaka_root / reader), quote=True)}">'
                    f'{html.escape(edition["version_label"])}</a> — {html.escape(edition["license"])}</li>'
                )
            body.append("</ul>")
        else:
            body.append("<p>No edition for this text is currently available locally under the CC0 or verified-public-domain policy.</p>")
        audio_page = tipitaka_root / "site/sutta-audio.html"
        audio_collection = info["collection"].split("/", 1)[0]
        if info.get("audio_available") and audio_page.is_file():
            audio_source = audio_page.read_text(encoding="utf-8")
            if re.search(r'<h2\b[^>]*id="' + re.escape(audio_collection) + r'"', audio_source):
                audio_title = COLLECTION_TITLES.get(audio_collection, audio_collection.replace("-", " ").title())
                audio_href = html.escape(_relative_href(page, audio_page) + "#" + audio_collection, quote=True)
                body.append(
                    "<h2>Collection audio</h2>"
                    f'<p><a href="{audio_href}">Open {html.escape(audio_title)} recordings</a> '
                    "(recordings may cover groups of texts).</p>"
                )
        restricted = sorted(info["restricted"], key=lambda row: (row.get("source_group", "").casefold(), row.get("title", "").casefold()))
        if restricted:
            body.append("<h2>Not included in this build</h2><ul>")
            for edition in restricted:
                label = edition.get("source_group") or edition.get("license") or "Edition not cleared for reuse"
                completeness = edition.get("completeness_status", "UNKNOWN")
                scope = edition.get("completeness_scope", "")
                note = f"Completeness: {completeness}. {scope}" if scope else f"Completeness: {completeness}."
                body.append(f"<li>{html.escape(label)} — {html.escape(note)}</li>")
            body.append("</ul>")
        body.append("<p>Same-ID editions are not assumed to be equivalent or equally complete. Rights status does not establish translation completeness.</p>")
        _write_page(page, title, "\n".join(body), tipitaka_root)
        _register_generated_page(allowed, tipitaka_root, page, info["collection"])

    vimanavatthu_story_pages = _write_vimanavatthu_story_pages(tipitaka_root, allowed)

    # Rebuild collection indexes from every original source-index row, not only allowed texts.
    collections: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for route, info in canonical_pages.items():
        parts = PurePosixPath(route).parts
        collection = "/".join(parts[1:-2])
        collections[collection].append((info["canonical_id"], info["title"], route))
    for collection in list(collections):
        parent_parts = collection.split("/")
        for length in range(1, len(parent_parts)):
            collections.setdefault("/".join(parent_parts[:length]), [])
    for collection in sorted(set(collections) | set(COLLECTION_TITLES)):
        title = COLLECTION_TITLES.get(collection, collection.replace("-", " ").title())
        index = tipitaka_root / "sutta" / collection / "index.html"
        index_relative = _safe_relative(index.relative_to(tipitaka_root))
        if index.is_file() and index_relative in allowed:
            continue
        body = [f"<h1>{html.escape(title)}</h1>"]
        subcollections = sorted(
            child for child in collections
            if child.startswith(collection + "/") and "/" not in child[len(collection) + 1:]
        )
        if subcollections:
            body.extend(["<h2>Collections</h2><ul>"])
            for child in subcollections:
                child_path = tipitaka_root / "sutta" / child / "index.html"
                child_title = COLLECTION_TITLES.get(child, child.rsplit("/", 1)[-1].replace("-", " ").title())
                body.append(f'<li><a href="{html.escape(_relative_href(index, child_path), quote=True)}">{html.escape(child_title)}</a></li>')
            body.append("</ul>")
        entries = sorted(collections.get(collection, []), key=lambda row: natural_key(row[0]))
        if entries:
            body.extend(["<h2>Indexed texts</h2><ul>"])
            for canonical_id, name, route in entries:
                destination = tipitaka_root / route
                body.append(
                    f'<li><a href="{html.escape(_relative_href(index, destination), quote=True)}">'
                    f'{html.escape(canonical_id)} — {html.escape(name)}</a></li>'
                )
            body.append("</ul>")
        if not entries and not subcollections:
            body.append("<p>No source-index entries are currently mapped to this collection.</p>")
        body.append("<p>The index preserves text navigation. A missing local edition means it has not cleared the current reuse policy; it does not imply that no translation exists.</p>")
        _write_page(index, title, "\n".join(body), tipitaka_root)
        _register_generated_page(allowed, tipitaka_root, index, collection)

    # Preserve all 31 archive URLs, but rebuild their contents from eligible records only.
    known_collections = set(collections) | set(COLLECTION_TITLES) | set(WHOLE_BOOK_PDF_SOURCES)
    for name in archive_names:
        if name.startswith("abhidhamma-") and name.endswith(".zip"):
            continue
        if name == "vinaya.zip" or name in {"tipitaka-all.zip", "tipitaka-html.zip", "tipitaka-txt.zip", "tipitaka-pdf.zip"}:
            continue
        collection = _archive_collection(name, known_collections)
        if collection is None and name.startswith("khuddaka-nikaya-") and name.endswith(".zip"):
            collection = "khuddaka-nikaya/" + name.removeprefix("khuddaka-nikaya-").removesuffix(".zip")
            known_collections.add(collection)
        if collection is None:
            raise ValueError(f"Existing collection archive has no collection mapping: {name}")
        collections.setdefault(collection, [])

    archive_content: dict[str, bool] = {}
    for name in archive_names:
        if name in {"tipitaka-all.zip", "tipitaka-html.zip", "tipitaka-txt.zip", "tipitaka-pdf.zip"}:
            archive_content[name] = True
        else:
            collection = "vinaya" if name == "vinaya.zip" else None
            if name.startswith("abhidhamma-"):
                collection = None
            if collection is None and not name.startswith("abhidhamma-"):
                collection = next((value for value in sorted(known_collections, key=len, reverse=True) if f"{slug(value)}.zip" == name), None)
                if collection is None and name.startswith("khuddaka-nikaya-"):
                    collection = "khuddaka-nikaya/" + name.removeprefix("khuddaka-nikaya-").removesuffix(".zip")
            archive_content[name] = bool(collection and any(entry.get("archive") and entry.get("collection") == collection for entry in allowed.values()))

    # Update the large text table so its edition counts mean eligible local editions.
    counts_by_route: dict[str, int] = defaultdict(int)
    for record in records:
        if record["kind"] != "sutta":
            continue
        route = (Path("sutta") / record["collection"] / canonical_slug(record["canonical_id"]) / "index.html").as_posix()
        counts_by_route[route] += 1
    collection_index_routes = set(COLLECTION_TITLES) | set(SUTTA_NODE_INFO) | set(WHOLE_BOOK_PDF_SOURCES) | set(collections) | {"khuddaka-nikaya"}
    updated_collection_rows = 0
    localized_source_links = 0
    for collection in sorted(collection_index_routes):
        relative_page = Path("sutta") / collection / "index.html"
        page = tipitaka_root / relative_page
        if not page.is_file():
            continue
        updated_collection_rows += _update_collection_index(
            page, relative_page, counts_by_route, archive_content
        )
        localized_source_links += _localize_suttafriends_story_links(page, relative_page, tipitaka_root, allowed)
    unique_ids = len({row["canonical_id"] for row in source_rows})
    available_ids = len({
        (record["collection"], record["canonical_id"])
        for record in records if record["kind"] == "sutta"
    })
    intro = (
        f"<p>Source index: {len(source_rows)} entries across {unique_ids} IDs. "
        f"This build includes {sum(counts_by_route.values())} CC0 or verified-public-domain editions across {available_ids} IDs. "
        "A zero means no edition cleared for local redistribution; it does not mean no translation exists.</p>"
    )
    updated_text_index = _replace_sutta_coverage_intro(existing_text_index, intro)
    updated_text_index = updated_text_index.replace("<th>Texts</th>", "<th>CC0/PD editions</th>")
    row_pattern = re.compile(
        r'<tr><td>(?P<canonical_id>.*?)</td><td><a href="(?P<href>[^"]+)">(?P<title>.*?)</a></td>'
        r'<td>\d+</td><td>(?P<audio>.*?)</td></tr>', re.DOTALL,
    )
    replaced_rows = 0

    def replace_count(match: re.Match) -> str:
        nonlocal replaced_rows
        route = posixpath.normpath(posixpath.join("site", unquote(urlsplit(match.group("href")).path)))
        count = counts_by_route.get(route, 0)
        replaced_rows += 1
        return (
            f'<tr><td>{match.group("canonical_id")}</td><td><a href="{match.group("href")}">'
            f'{match.group("title")}</a></td><td>{count}</td><td>{match.group("audio")}</td></tr>'
        )

    updated_text_index = row_pattern.sub(replace_count, updated_text_index)
    if replaced_rows != len(source_rows):
        raise ValueError(f"Sutta text index row validation failed: parsed {len(source_rows)}, rewrote {replaced_rows}")
    (site_dir / "sutta-texts.html").write_text(updated_text_index, encoding="utf-8", newline="\n")

    sutta_page = site_dir / "sutta.html"
    sutta_html = sutta_page.read_text(encoding="utf-8")
    sutta_html, changed = re.subn(
        r'<li><a href="sutta-texts\.html">Texts</a>:.*?</li>',
        f'<li><a href="sutta-texts.html">Texts</a>: {sum(counts_by_route.values())} eligible local editions across {available_ids} indexed IDs; zeros are not claims that no translation exists.</li>',
        sutta_html,
        count=1,
    )
    if changed != 1:
        raise ValueError("Could not update the Sutta overview coverage statement")
    sutta_html, changed_download = re.subn(
        r'<li><a href="downloads\.html">Downloads</a>:.*?</li>',
        '<li><a href="downloads.html">Downloads</a>: CC0/verified-public-domain files only; collection archives with no eligible files contain a notice.</li>',
        sutta_html,
        count=1,
    )
    if changed_download != 1:
        raise ValueError("Could not update the Sutta download-coverage statement")
    sutta_page.write_text(sutta_html, encoding="utf-8", newline="\n")

    downloads_path = site_dir / "downloads.html"
    downloads_html = downloads_path.read_text(encoding="utf-8")
    downloads_html = downloads_html.replace(
        "<p>These archives contain the material currently available here; they do not yet constitute the complete Pāli Canon.</p>",
        "<p>Every archive is rebuilt from editions cleared as CC0 or verified public domain. Collections with no eligible files contain a notice only. This is not a claim of complete Tipiṭaka coverage.</p>",
    )
    if "<p>Every archive is rebuilt" not in downloads_html:
        raise ValueError("Could not replace the old archive-content claim")
    archive_link_re = ARCHIVE_LINK_RE
    linked_archives = set()

    def update_download_label(match: re.Match) -> str:
        name, label = match.group(1), html.unescape(match.group(2))
        linked_archives.add(name)
        if name not in archive_content:
            raise ValueError(f"Downloads page links to an archive not scheduled for safe rebuilding: {name}")
        if not archive_content[name]:
            label = label.replace(" — complete English book", "")
            label = label.replace(" — complete English text and scan (TXT + PDF)", "")
            label += " — no eligible files; notice only"
        return f'<li><a href="../downloads/{html.escape(name, quote=True)}">{html.escape(label)}</a></li>'

    downloads_html = archive_link_re.sub(update_download_label, downloads_html)
    if linked_archives != set(archive_names):
        raise ValueError(f"Downloads page and retained archive routes differ: page={sorted(linked_archives)}, expected={sorted(archive_names)}")
    downloads_path.write_text(downloads_html, encoding="utf-8", newline="\n")

    # Preserve all seven Abhidhamma navigation nodes without serving restricted books.
    abhidhamma_root = tipitaka_root / "abhidhamma"
    abhidhamma_index = abhidhamma_root / "index.html"
    abhidhamma_rows = []
    for book_slug, name, english, description in ABHIDHAMMA_BOOKS:
        book_path = abhidhamma_root / book_slug / "index.html"
        body = (
            f'<p><a href="{html.escape(_relative_href(book_path, abhidhamma_index), quote=True)}">Abhidhamma Piṭaka</a></p>'
            f"<h1>{html.escape(name)} ({html.escape(english)})</h1>"
            f"<p>{html.escape(description)}</p>"
            "<p>No English text or book download is included here under the CC0 or verified-public-domain policy. This availability label does not assess whether a translation is complete.</p>"
        )
        _write_page(book_path, f"{name} ({english})", body, tipitaka_root)
        _register_generated_page(allowed, tipitaka_root, book_path, "abhidhamma")
        abhidhamma_rows.append(
            f'<li><a href="{html.escape(_relative_href(abhidhamma_index, book_path), quote=True)}">{html.escape(name)} ({html.escape(english)})</a> — no eligible local text</li>'
        )
    _write_page(
        abhidhamma_index,
        "Abhidhamma Piṭaka",
        "<h1>Abhidhamma Piṭaka</h1><p>No book translations currently clear the CC0 or verified-public-domain policy.</p><ul>" + "\n".join(abhidhamma_rows) + "</ul>",
        tipitaka_root,
    )
    _register_generated_page(allowed, tipitaka_root, abhidhamma_index, "abhidhamma")

    vinaya_report = _write_vinaya_indexes(tipitaka_root, records, allowed)

    anguttara_index_entries = _write_anguttara_index(
        tipitaka_root, canonical_pages, counts_by_route, allowed
    )

    summary = (
        f"<p>The text index retains {len(source_rows)} source entries across {unique_ids} IDs. "
        f"This build includes {sum(counts_by_route.values())} CC0 or verified-public-domain Sutta editions across {available_ids} IDs. "
        f"The Vinaya source manifest maps {vinaya_report['source_files']} English files; {vinaya_report['local_files']} have local readers and {vinaya_report['review_required_files']} are held for passage-level review. "
        "No Abhidhamma book currently clears the reuse policy. Text availability and translation completeness are separate; unavailable entries remain in the navigation.</p>"
    )
    tipitaka_page = site_dir / "tipitaka.html"
    tipitaka_html = tipitaka_page.read_text(encoding="utf-8")
    tipitaka_html = _replace_tipitaka_coverage_summary(tipitaka_html, summary)
    tree_counts = {
        "../vinaya/index.html": f"5 books; {vinaya_report['source_files']} source files; {vinaya_report['local_files']} local readers",
        "../vinaya/sutta-vibhanga/index.html": f"{vinaya_report['sutta_vibhanga_entries']} indexed entries; {vinaya_report['sutta_vibhanga_local']} local readers; {vinaya_report['sutta_vibhanga_review_required']} held for review",
        "../vinaya/bhikkhu-vibhanga/index.html": f"{vinaya_report['bhikkhu_vibhanga_entries']} indexed entries; {vinaya_report['bhikkhu_vibhanga_local']} local readers; {vinaya_report['bhikkhu_vibhanga_review_required']} held for review",
        "../vinaya/bhikkhuni-vibhanga/index.html": f"{vinaya_report['bhikkhuni_vibhanga_entries']} indexed entries; {vinaya_report['bhikkhuni_vibhanga_local']} local readers; {vinaya_report['bhikkhuni_vibhanga_review_required']} held for review",
        "../vinaya/khandhaka/index.html": f"{vinaya_report['khandhaka_entries']} chapters; {vinaya_report['khandhaka_local']} local readers; {vinaya_report['khandhaka_review_required']} held for review",
        "../vinaya/mahavagga/index.html": f"{vinaya_report['mahavagga_entries']} chapters; no local reader yet",
        "../vinaya/cullavagga/index.html": f"{vinaya_report['cullavagga_entries']} chapters; no local reader yet",
        "../vinaya/parivara/index.html": f"{vinaya_report['parivara_entries']} indexed entries; {vinaya_report['parivara_local']} local readers; {vinaya_report['parivara_review_required']} held for review",
        "sutta.html": f"5 collections; {len(source_rows)} indexed text entries",
        "../abhidhamma/index.html": "7 books; no eligible local translations",
    }
    for route, info in canonical_pages.items():
        collection = info["collection"]
        if collection not in {"digha-nikaya", "majjhima-nikaya", "samyutta-nikaya", "anguttara-nikaya", "khuddaka-nikaya"} and not collection.startswith("khuddaka-nikaya/"):
            continue
        count = sum(
            row["collection"] == collection or row["collection"].startswith(collection + "/")
            for row in canonical_pages.values()
        )
        if count:
            local = sum(
                edition_count for candidate_route, edition_count in counts_by_route.items()
                if candidate_route in canonical_pages and (
                    canonical_pages[candidate_route]["collection"] == collection
                    or canonical_pages[candidate_route]["collection"].startswith(collection + "/")
                )
            )
            href = f"../sutta/{collection}/index.html"
            if f'<a href="{href}"' in tipitaka_html:
                tree_counts[href] = f"{count} indexed entries; {local} eligible editions"
    khuddaka_entries = sum(1 for row in canonical_pages.values() if row["collection"].startswith("khuddaka-nikaya"))
    khuddaka_editions = sum(
        edition_count for candidate_route, edition_count in counts_by_route.items()
        if candidate_route in canonical_pages and canonical_pages[candidate_route]["collection"].startswith("khuddaka-nikaya")
    )
    tree_counts["../sutta/khuddaka-nikaya/index.html"] = (
        f"15 core books plus edition-specific works; {khuddaka_entries} indexed entries; {khuddaka_editions} eligible editions"
    )
    for book_slug, _name, _english, _description in ABHIDHAMMA_BOOKS:
        tree_counts[f"../abhidhamma/{book_slug}/index.html"] = "no eligible local English edition"
    tipitaka_html = _update_tipitaka_tree_counts(tipitaka_html, tree_counts)
    tipitaka_page.write_text(tipitaka_html, encoding="utf-8", newline="\n")

    continuous_reader_entries = _write_continuous_reader(tipitaka_root, canonical_pages, allowed)
    collection_browsers = _write_collection_browsers(tipitaka_root, canonical_pages, collections)

    return {
        "archive_content": archive_content,
        "blocked_file_paths": blocked_file_paths,
        "blocked_reader_routes": set(blocked_reader_routes),
        "disabled_restricted_links": disabled_restricted_links,
        "collection_index_rows_updated": updated_collection_rows,
        "localized_source_links": localized_source_links,
        "canonical_pages": len(canonical_pages),
        "continuous_reader_entries": continuous_reader_entries,
        "collection_browsers": collection_browsers,
        "vimanavatthu_story_availability_pages": vimanavatthu_story_pages,
        "source_index_entries": len(source_rows),
        "available_canonical_ids": available_ids,
        "anguttara_index_entries": anguttara_index_entries,
        "vinaya_source_files": vinaya_report["source_files"],
        "vinaya_review_required_files": vinaya_report["review_required_files"],
    }


def _copy_allowlisted_files(destination: Path, allowed: dict[Path, dict]) -> None:
    for relative, entry in sorted(allowed.items(), key=lambda pair: pair[0].as_posix()):
        source = Path(entry["source"])
        target = destination / relative
        if source.is_symlink() or not source.is_file():
            raise FileNotFoundError(f"Allowlisted source is missing or not a regular file: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve():
            shutil.copyfile(source, target)


def _write_crawler_files(destination: Path) -> tuple[Path, Path]:
    """Serve the welcome page directly and expose a sitemap of built HTML routes."""
    homepage = destination / "index.html"
    if not homepage.is_file():
        raise FileNotFoundError("The public root must contain a direct index.html welcome page")
    root_html = homepage.read_text(encoding="utf-8").casefold()
    if "http-equiv=\"refresh\"" in root_html or "http-equiv='refresh'" in root_html:
        raise ValueError("The public root welcome page must not rely on a meta-refresh redirect")

    urls = ["/"]
    for path in sorted(destination.rglob("*.html")):
        relative = path.relative_to(destination).as_posix()
        if relative != "index.html":
            urls.append("/" + quote(relative, safe="/-._~"))
    if len(urls) > 50_000:
        raise ValueError(f"Sitemap exceeds the standard URL limit: {len(urls)}")
    url_items = "\n".join(
        f"  <url><loc>{html.escape('https://freebuddhism.org' + url)}</loc></url>"
        for url in urls
    )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{url_items}\n</urlset>\n"
    )
    sitemap_path = destination / "sitemap.xml"
    sitemap_path.write_text(sitemap, encoding="utf-8", newline="\n")
    robots_path = destination / "robots.txt"
    robots_path.write_text(
        "User-agent: *\nAllow: /\nSitemap: https://freebuddhism.org/sitemap.xml\n",
        encoding="utf-8",
        newline="\n",
    )
    return robots_path, sitemap_path


def _zip_write(
    path: Path,
    member_paths: list[Path],
    tipitaka_root: Path,
    allowed: dict[Path, dict],
    notice: str | None = None,
) -> None:
    unique_paths = sorted(set(member_paths), key=lambda item: item.as_posix())
    if not unique_paths and notice is None:
        raise ValueError(f"Refusing to create an empty archive without a notice: {path.name}")
    if unique_paths and notice is not None:
        raise ValueError(f"Archive notice should only be written when no eligible files exist: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in unique_paths:
            relative = _safe_relative(relative)
            if relative not in allowed or relative.parts[0] == "downloads" or not allowed[relative].get("archive"):
                raise ValueError(f"Archive member is not on the publication allowlist: {relative}")
            source = tipitaka_root / relative
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        if notice is not None:
            info = zipfile.ZipInfo(ARCHIVE_NOTICE, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, notice.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise ValueError(f"Archive integrity check failed for {path.name}: {bad_member}")
        actual = set(archive.namelist())
    expected = {item.as_posix() for item in unique_paths}
    if notice is not None:
        expected.add(ARCHIVE_NOTICE)
    if actual != expected:
        raise ValueError(f"Archive member mismatch for {path.name}")


def _archive_collection(name: str, collections: set[str]) -> str | None:
    if name == "vinaya.zip":
        return "vinaya"
    if name.startswith("abhidhamma-") and name.endswith(".zip"):
        return "abhidhamma"
    if name in {"tipitaka-all.zip", "tipitaka-html.zip", "tipitaka-txt.zip", "tipitaka-pdf.zip"}:
        return None
    match = next((value for value in sorted(collections, key=len, reverse=True) if f"{slug(value)}.zip" == name), None)
    if match:
        return match
    if name.startswith("khuddaka-nikaya-") and name.endswith(".zip"):
        return "khuddaka-nikaya/" + name.removeprefix("khuddaka-nikaya-").removesuffix(".zip")
    return None


def _write_archives(
    tipitaka_root: Path,
    allowed: dict[Path, dict],
    archive_names: list[str],
    collections: set[str],
) -> dict[str, bool]:
    payload = [path for path, entry in allowed.items() if entry.get("archive")]
    if not payload:
        raise ValueError("The default-deny build has no eligible files for its global archives")
    global_specs = {
        "tipitaka-all.zip": payload,
        "tipitaka-html.zip": [path for path in payload if path.suffix.lower() == ".html"],
        "tipitaka-txt.zip": [path for path in payload if path.suffix.lower() == ".txt"],
        "tipitaka-pdf.zip": [path for path in payload if path.suffix.lower() == ".pdf"],
    }
    has_content: dict[str, bool] = {}
    for name in archive_names:
        if name in global_specs:
            members = global_specs[name]
        else:
            collection = _archive_collection(name, collections)
            if collection is None:
                raise ValueError(f"Unrecognized existing archive route: {name}")
            members = [path for path, entry in allowed.items() if entry.get("archive") and entry.get("collection") == collection]
        has_content[name] = bool(members)
        notice = None if members else (
            f"No CC0 or verified-public-domain text files are currently available in this archive.\n"
            "The archive is retained to preserve its download URL; it contains no restricted source text.\n"
        )
        _zip_write(tipitaka_root / "downloads" / name, members, tipitaka_root, allowed, notice=notice)
    if set(has_content) != set(archive_names):
        raise ValueError("Archive output set differs from the existing public archive routes")
    return has_content


def assemble_webroot(
    destination: Path,
    records: list[dict] | None = None,
    *,
    impact_map: dict | None = None,
    site_root: Path | None = None,
    site_entry: Path | None = None,
    archive_names: list[str] | None = None,
) -> dict:
    """Assemble the existing full website while allowlisting every text payload."""
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError(f"Refusing to assemble into a non-empty directory: {destination}")
    selected = records if records is not None else collect_records(READER_OUTPUT)
    if not selected:
        raise ValueError("No CC0 or verified public-domain text versions passed the reader allowlist")

    if impact_map is None:
        if not IMPACT_MAP.is_file():
            raise FileNotFoundError(f"Approved remediation impact map is missing: {IMPACT_MAP}")
        impact_map = json.loads(IMPACT_MAP.read_text(encoding="utf-8"))
    if "records" not in impact_map or "standalone_assets" not in impact_map:
        raise ValueError("Impact map is missing its records or standalone-assets inventory")
    site_root = site_root or (PUBLIC_TIPITAKA / "site")
    site_entry = site_entry or SITE_ENTRY
    if archive_names is None:
        downloads_page = site_root / "downloads.html"
        if not downloads_page.is_file():
            raise FileNotFoundError(f"Existing downloads page is missing: {downloads_page}")
        downloads_html = downloads_page.read_text(encoding="utf-8")
        archive_names = [html.unescape(match.group(1)) for match in ARCHIVE_LINK_RE.finditer(downloads_html)]
        if not archive_names:
            raise ValueError(f"No existing ZIP routes were found in {downloads_page}")
        if len(archive_names) != len(set(archive_names)):
            raise ValueError(f"Duplicate ZIP routes were found in {downloads_page}")
        for name in archive_names:
            if (PurePosixPath(name).name != name
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.zip", name)):
                raise ValueError(f"Unsafe ZIP route in downloads page: {name}")

    allowed: dict[Path, dict] = {}
    tipitaka_root = destination / "theravada" / "tipitaka"
    source_root = ROOT.resolve()
    output_roots = {Path(record["output_root"]).resolve() for record in selected}
    if len(output_roots) != 1:
        raise ValueError("Eligible reader records do not share one generated output root")
    output_root = next(iter(output_roots))
    seen_records: set[tuple[str, str, str, str]] = set()
    content_collections: set[str] = set()

    for record in selected:
        if not _record_license_is_allowed(record):
            raise ValueError(f"Record outside the CC0/verified-PD allowlist: {record.get('license')} {record.get('canonical_id')}")
        row = record["row"]
        key = (record["kind"], record["collection"], record["canonical_id"], record["version"])
        if key in seen_records:
            raise ValueError(f"Duplicate eligible reader record: {key}")
        seen_records.add(key)
        text_relative = _record_relative_path(record, "text_path", output_root, source_root)
        html_relative = _record_relative_path(record, "html_path", output_root, source_root)
        pdf_relative = _record_relative_path(record, "pdf_path", output_root, source_root)
        for relative, source in ((text_relative, Path(record["text_path"])),
                                 (html_relative, Path(record["html_path"])),
                                 (pdf_relative, Path(record["pdf_path"]))):
            if source.is_symlink() or not source.is_file():
                raise FileNotFoundError(f"Eligible reader/source output is missing or unsafe: {source}")
            entry = {"source": source, "kind": source.suffix.lower().removeprefix("."),
                     "collection": record["collection"] if record["kind"] == "sutta" else "vinaya",
                     "archive": True}
            if relative in allowed:
                previous = allowed[relative]
                if previous["source"].resolve() != source.resolve():
                    raise ValueError(f"Two records map different files to one public path: {relative}")
            allowed[relative] = entry
        if hashlib_sha256(Path(record["text_path"])) != record["source_sha256"]:
            raise ValueError(f"Source text changed after reader validation: {row['txt_path']}")
        if record["kind"] == "sutta":
            content_collections.add(record["collection"])
        elif record["kind"] == "vinaya":
            content_collections.add("vinaya")

    # Only these two scanned books have verified U.S. public-domain status.
    for collection, book in WHOLE_BOOK_PDF_SOURCES.items():
        if book.get("license") != US_PD_BOOK_LICENSE:
            continue
        for pdf in whole_book_pdfs(book):
            relative = _safe_relative(pdf["path"])
            source = source_root / "theravada" / "tipitaka" / relative
            if source.is_symlink() or not source.is_file():
                raise FileNotFoundError(f"Verified public-domain book PDF is missing: {relative}")
            allowed[relative] = {"source": source, "kind": "pdf", "collection": collection, "archive": True}
            content_collections.add(collection)

    _copy_site_pages(destination, allowed, site_root, site_entry)
    _copy_collection_indexes(tipitaka_root, allowed, PUBLIC_TIPITAKA)
    if not archive_names:
        raise ValueError("No existing archive routes were supplied for safe rebuilding")
    archive_names = sorted(set(archive_names))
    navigation_report = _write_navigation_pages(tipitaka_root, selected, allowed, impact_map, archive_names)
    _copy_allowlisted_files(tipitaka_root, allowed)
    archive_content = _write_archives(tipitaka_root, allowed, archive_names, content_collections | set(COLLECTION_TITLES) | set(WHOLE_BOOK_PDF_SOURCES))
    if archive_content != navigation_report["archive_content"]:
        raise ValueError("Download-page archive labels differ from the built archive contents")
    crawler_files = _write_crawler_files(destination)

    expected_files = {destination / "index.html", *crawler_files} | {tipitaka_root / path for path in allowed}
    archive_paths = {path for path in (tipitaka_root / "downloads").glob("*.zip")}
    actual_files = {path for path in destination.rglob("*") if path.is_file()}
    if actual_files != expected_files | archive_paths:
        extras = sorted(path.relative_to(destination).as_posix() for path in actual_files - expected_files - archive_paths)
        missing = sorted(path.relative_to(destination).as_posix() for path in expected_files - actual_files)
        raise ValueError(f"Strict output file set mismatch; extra={extras[:10]}, missing={missing[:10]}")

    if {path.name for path in archive_paths} != set(archive_names):
        raise ValueError("Strict output contains an unexpected or missing ZIP archive")

    for archive_path in archive_paths:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate members in archive: {archive_path.name}")
        for name in names:
            if name == ARCHIVE_NOTICE:
                if archive_content[archive_path.name]:
                    raise ValueError(f"Non-empty archive unexpectedly contains a notice only: {archive_path.name}")
                continue
            relative = _safe_relative(name)
            if relative not in allowed or relative.parts[0] == "downloads" or not allowed[relative].get("archive"):
                raise ValueError(f"Archive bypassed the publishing allowlist: {archive_path.name}: {name}")
        if archive_content[archive_path.name] and ARCHIVE_NOTICE in names:
            raise ValueError(f"Archive with eligible content unexpectedly includes a notice: {archive_path.name}")
        if not archive_content[archive_path.name] and names != [ARCHIVE_NOTICE]:
            raise ValueError(f"Unavailable archive must contain only its notice: {archive_path.name}")

    leaked_blocked = [path for path in navigation_report["blocked_file_paths"] if (tipitaka_root / path).exists()]
    if leaked_blocked:
        raise ValueError(f"Restricted direct files remain in the bundle: {[path.as_posix() for path in leaked_blocked[:20]]}")
    for relative in navigation_report["blocked_reader_routes"]:
        if relative.suffix.lower() == ".html" and not (tipitaka_root / relative).is_file():
            raise ValueError(f"A restricted page lost its availability notice: {relative}")

    errors = local_link_errors(destination)
    if errors:
        detail = "\n".join(errors[:40])
        extra = f"\n... and {len(errors) - 40} more" if len(errors) > 40 else ""
        raise RuntimeError(f"strict webroot has {len(errors)} broken local links:\n{detail}{extra}")

    return {"reader_versions": len(selected), "sutta_collections": len(content_collections - {"vinaya"}),
            "vinaya_reader_versions": sum(record["kind"] == "vinaya" for record in selected),
            "allowlisted_files": len(allowed) + 1, "archives": len(archive_paths),
            "archives_with_files": sum(archive_content.values()),
            "archives_notice_only": sum(not has_files for has_files in archive_content.values()),
            "site_pages_preserved": sum(path.parts[0] == "site" for path in allowed),
            "sutta_index_entries": navigation_report["source_index_entries"],
            "sutta_ids_with_eligible_editions": navigation_report["available_canonical_ids"],
            "restricted_file_routes_blocked": len(navigation_report["blocked_file_paths"]),
            "restricted_page_routes_replaced": len(navigation_report["blocked_reader_routes"]),
            "restricted_site_links_disabled": navigation_report["disabled_restricted_links"],
            "collection_index_rows_updated": navigation_report["collection_index_rows_updated"],
            "external_story_links_localized": navigation_report["localized_source_links"],
            "sitemap_html_routes": sum(1 for _ in destination.rglob("*.html")),
            "broken_local_links": 0}


def hashlib_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_output_destination(output: Path | None = None) -> Path:
    """Normalize an output path lexically and reject symlinks before any deletion."""
    requested = output or WEBROOT
    if not requested.is_absolute():
        requested = ROOT / requested
    destination = Path(os.path.abspath(requested))
    try:
        destination.relative_to(ROOT)
    except ValueError as error:
        raise RuntimeError(f"site output must stay inside the repository: {destination}") from error

    current = Path(destination.anchor)
    for component in destination.parts[1:]:
        current = current / component
        if current.is_symlink():
            raise RuntimeError(f"refusing a symlink in the site output path: {current}")
    return destination


def normalize_webroot_permissions(root: Path) -> None:
    """Make the static bundle traversable/readable by an unprivileged web server."""
    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        current = Path(directory)
        if current.is_symlink():
            raise RuntimeError(f"refusing a symlink in the generated webroot: {current}")
        current.chmod(0o755)
        for name in subdirectories:
            child = current / name
            if child.is_symlink():
                raise RuntimeError(f"refusing a symlink in the generated webroot: {child}")
        for name in filenames:
            child = current / name
            if child.is_symlink():
                raise RuntimeError(f"refusing a symlink in the generated webroot: {child}")
            child.chmod(0o644)


def managed_webroot_marker_is_valid() -> bool:
    return (
        not BUILD_MARKER.is_symlink()
        and BUILD_MARKER.is_file()
        and BUILD_MARKER.read_text(encoding="utf-8") == "Generated by default-deny build_deploy_site.py\n"
    )


def build(reader_jobs: int = 2, output: Path | None = None) -> Path:
    if BUILD_ROOT.is_symlink():
        raise RuntimeError(f"refusing a symlinked build directory: {BUILD_ROOT}")
    BUILD_ROOT.mkdir(exist_ok=True)
    destination = safe_output_destination(output)
    default_destination = Path(os.path.abspath(WEBROOT))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = safe_output_destination(destination)
    if destination.exists():
        if destination != default_destination or not managed_webroot_marker_is_valid():
            raise RuntimeError(f"refusing to replace an existing unmanaged output directory: {destination}")
    subprocess.run([
        sys.executable, str(READER_BUILDER),
        "--output-root", READER_OUTPUT.relative_to(ROOT).as_posix(),
        "--prune-output", "--jobs", str(reader_jobs),
    ], cwd=ROOT, check=True)
    staging = Path(tempfile.mkdtemp(prefix=".site-root-", dir=destination.parent))
    try:
        report = assemble_webroot(staging)
        normalize_webroot_permissions(staging)
        if destination.exists():
            destination = safe_output_destination(destination)
            if destination != default_destination or not managed_webroot_marker_is_valid():
                raise RuntimeError(f"refusing to replace an unmanaged output directory: {destination}")
            shutil.rmtree(destination)
        staging.rename(destination)
        if destination == default_destination:
            BUILD_MARKER.write_text("Generated by default-deny build_deploy_site.py\n", encoding="utf-8")
        print(f"Strict bundle validated: {report}", flush=True)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reader-jobs", type=int, default=2, help="Parallel PDF workers, from 1 to 8")
    parser.add_argument("--output", type=Path, help="Output directory; defaults to build/site-root")
    args = parser.parse_args(argv)
    if not 1 <= args.reader_jobs <= 8:
        raise ValueError("--reader-jobs must be from 1 to 8")
    output = args.output
    if output is not None and not output.is_absolute():
        output = ROOT / output
    result = build(reader_jobs=args.reader_jobs, output=output)
    print(f"Website files ready: {result.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (FileNotFoundError, RuntimeError, ValueError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        print(f"site build failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
