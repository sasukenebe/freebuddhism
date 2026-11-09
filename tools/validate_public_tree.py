#!/usr/bin/env python3
"""Verify every tracked source file against explicit rights and content rules."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from buddhist_canon_pipeline.public_html_policy import (
    NAVIGATION_RIGHTS_BASIS,
    NAVIGATION_SCOPE,
    SITE_RIGHTS_BASIS,
    SITE_SCOPE,
    validate_site_content_manifest,
)
from buddhist_canon_pipeline.public_candana_review import (
    LICENSE as CANDANA_REVIEW_LICENSE,
    RIGHTS_BASIS as CANDANA_REVIEW_RIGHTS_BASIS,
)


ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "metadata" / "public-file-allowlist.json"
ELIGIBLE = ROOT / "metadata" / "eligible-texts.json"
ASSETS = ROOT / "metadata" / "eligible-assets.json"
EXCLUDED = ROOT / "metadata" / "excluded-sources.json"
IMPACT_MAP = ROOT / "metadata" / "reports" / "remediation-impact-map-2026-10.json"
SELF = ALLOWLIST.relative_to(ROOT).as_posix()
IGNORED_ROOT_DIRS = {".git", ".venv", "build"}
EXCLUDED_ROUTE_NOTICE = "This edition is not included in the local website build"
ROUTE_FOOTER = "Rights clearance and translation completeness are assessed separately. An unavailable edition is not a claim that no translation exists."
PD_SCAN_ROUTE = "theravada/tipitaka/sutta/khuddaka-nikaya/milindapanha/rhys-davids-complete.html"
PETAKOPADESA_INDEX = "theravada/tipitaka/sutta/khuddaka-nikaya/petakopadesa/index.html"
PETAKOPADESA_INDEX_SHA256 = "58c1465684c782b5be7132dc0f0303c4025f491fe4c410433a539a325847591c"
PETAKOPADESA_EMBED = "../../../translations/en/licensed-sutta-books/nanamoli-petakopadesa.pdf"
LARGE_INDEX_LINK_TEXT_BUDGETS = {
    "theravada/tipitaka/sutta/samyutta-nikaya/index.html": 35930,
    "theravada/tipitaka/sutta/anguttara-nikaya/index.html": 30539,
    "theravada/tipitaka/sutta/khuddaka-nikaya/jataka/index.html": 13910,
    "theravada/tipitaka/vinaya/sutta-vibhanga/index.html": 12174,
    "theravada/tipitaka/sutta/khuddaka-nikaya/apadana/index.html": 9331,
    "theravada/tipitaka/sutta/khuddaka-nikaya/vimanavatthu/index.html": 7108,
    "theravada/tipitaka/vinaya/bhikkhu-vibhanga/index.html": 6975,
    "theravada/tipitaka/vinaya/bhikkhuni-vibhanga/index.html": 5228,
}
RIGHTS_BASIS_BY_SCOPE = {
    CANDANA_REVIEW_LICENSE: CANDANA_REVIEW_RIGHTS_BASIS,
    "0BSD": "Original project code and test fixtures are released under 0BSD in LICENSE.",
    "License text": "Standard 0BSD and CC0-1.0 license texts are included as license notices.",
    "CC0-1.0 project documentation": "Owner-authored project documentation is released under CC0-1.0 in LICENSE.",
    "CC0-1.0 project configuration": "Owner-authored project configuration is released under CC0-1.0 in LICENSE.",
    "CC0-1.0 project metadata": "Owner-authored project metadata is released under CC0-1.0; excluded source text is not copied.",
    "CC0-1.0 project source metadata": "Owner-authored provenance ledgers contain source metadata, not translated passages.",
    "CC0-1.0 SuttaCentral reference metadata": "SuttaCentral reference metadata is released under CC0-1.0; these files contain names and navigation ranges, not translated passages.",
    NAVIGATION_SCOPE: NAVIGATION_RIGHTS_BASIS,
    SITE_SCOPE: SITE_RIGHTS_BASIS,
    "CC0-1.0": "Source license and revision are recorded in the approved text or asset manifest and pinned by SHA-256.",
    "Public Domain (original English edition, published 1895–1907)": "Original edition dates and U.S. public-domain evidence are recorded in the Cowell source manifest.",
    "Public domain in the United States": "Edition-specific publication and rights evidence are recorded in the asset manifest.",
}
SELF_RIGHTS_BASIS = "This allowlist is project metadata under CC0-1.0; its own hash is intentionally self-referential."
HTML_TAGS = {
    "html", "head", "meta", "title", "body", "nav", "a", "h1", "h2", "h3",
    "p", "ul", "ol", "li", "span", "strong", "em", "table", "tr", "td",
    "th", "details", "summary", "br", "object",
}
ROUTE_TAGS = {"html", "head", "meta", "title", "body", "nav", "a", "h1", "p", "ul", "li"}
FORBIDDEN_HTML_TAGS = {"script", "style", "iframe", "audio", "video", "embed", "form", "textarea", "blockquote", "article"}


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def actual_files(root: Path = ROOT) -> set[str]:
    found = set()
    root = root.resolve()
    for directory, subdirectories, filenames in os.walk(root):
        base = Path(directory)
        for name in subdirectories:
            path = base / name
            if path.is_symlink():
                raise ValueError(f"Symlink directory is not allowed in the public source tree: {path.relative_to(root)}")
        if base == root:
            subdirectories[:] = [name for name in subdirectories if name not in IGNORED_ROOT_DIRS]
        else:
            subdirectories[:] = [name for name in subdirectories if name != "__pycache__"]
        for name in filenames:
            path = base / name
            if path.is_symlink():
                raise ValueError(f"Symlink is not allowed in the public source tree: {path.relative_to(root)}")
            relative = path.relative_to(root).as_posix()
            if root != ROOT or relative != SELF:
                found.add(relative)
    return found


class PageAudit:
    def __init__(self, source: str) -> None:
        tag_matches = list(re.finditer(r"<\s*(/?)\s*([A-Za-z][A-Za-z0-9:-]*)\b([^>]*)>", source))
        self.tags = {match.group(2).lower() for match in tag_matches}
        self.paragraphs = [self._text(match.group(1)) for match in re.finditer(
            r"<p\b[^>]*>(.*?)</p\s*>", source, flags=re.IGNORECASE | re.DOTALL)]
        self.headings = [self._text(match.group(2)) for match in re.finditer(
            r"<(h[123])\b[^>]*>(.*?)</h[123]\s*>", source, flags=re.IGNORECASE | re.DOTALL)]
        self.links = [self._attribute(match.group(1), "href") or "" for match in re.finditer(
            r"<a\b([^>]*)>", source, flags=re.IGNORECASE | re.DOTALL)]
        self.anchor_texts = [self._text(match.group(1)) for match in re.finditer(
            r"<a\b[^>]*>(.*?)</a\s*>", source, flags=re.IGNORECASE | re.DOTALL)]
        self.max_anchor_text = max(map(len, self.anchor_texts), default=0)
        self.total_anchor_text = sum(map(len, self.anchor_texts))
        text_attribute_names = {"title", "alt", "content", "placeholder", "value", "summary", "longdesc"}
        self.text_attributes = []
        for tag in tag_matches:
            for attribute in re.finditer(
                    r"([A-Za-z_:][A-Za-z0-9_:.-]*)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'=<>`]+))",
                    tag.group(3), flags=re.DOTALL):
                name = attribute.group(1).lower()
                if name in text_attribute_names or name.startswith(("aria-", "data-")):
                    value = next(value for value in attribute.groups()[1:] if value is not None)
                    self.text_attributes.append(html.unescape(value))
        self.max_text_attribute = max((len(value) for value in self.text_attributes), default=0)
        self.total_text_attributes = sum(map(len, self.text_attributes))
        self.table_cell_texts = [self._text(re.sub(
            r"<a\b[^>]*>.*?</a\s*>", " ", match.group(1), flags=re.IGNORECASE | re.DOTALL))
            for match in re.finditer(r"<(?:td|th)\b[^>]*>(.*?)</(?:td|th)\s*>",
                                     source, flags=re.IGNORECASE | re.DOTALL)]
        self.table_unlinked_text = sum(
            len(value) for value in self.table_cell_texts
            if value and value not in {"ID", "Title", "CC0/PD editions"}
            and not value.isdigit()
            and not re.fullmatch(r"[A-Za-z]{1,4}(?:\s+[A-Za-z]{1,4})?\s+[0-9][0-9.\-– ]*", value)
        )
        self.max_heading_text = max(map(len, self.headings), default=0)
        self.total_paragraph_text = sum(map(len, self.paragraphs))
        unlinked_source = re.sub(r"<a\b[^>]*>.*?</a\s*>", " ", source,
                                 flags=re.IGNORECASE | re.DOTALL)
        unlinked_source = re.sub(r"<table\b[^>]*>.*?</table\s*>", " ", unlinked_source,
                                 flags=re.IGNORECASE | re.DOTALL)
        for annotation in (
            "— eligible CC0 edition",
            "— not included under current reuse policy",
            "— CC0-1.0",
            "— Public Domain (original English edition, published 1895–1907)",
            "— Jātaka commentary narratives",
        ):
            unlinked_source = unlinked_source.replace(annotation, " ")
        self.unlinked_text = self._text(unlinked_source)
        self.embeds = [self._attribute(match.group(1), "data") or "" for match in re.finditer(
            r"<object\b([^>]*)>", source, flags=re.IGNORECASE | re.DOTALL)]
        self.comments = re.findall(r"<!--(.*?)-->", source, flags=re.DOTALL)
        self.event_attributes = re.findall(r"\s(on[a-z]+)\s*=", source, flags=re.IGNORECASE)
        self.inline_styles = len(re.findall(r"\sstyle\s*=", source, flags=re.IGNORECASE))
        self.loose_text = self._find_loose_text(source)
        self.long_titles = [self._text(match.group(1)) for match in re.finditer(
            r"<title\b[^>]*>(.*?)</title\s*>", source, flags=re.IGNORECASE | re.DOTALL)
            if len(self._text(match.group(1))) > 300]
        self.long_navigation_items = [
            self._text(match.group(1))
            for match in re.finditer(r"<(?:li|td|th|summary)\b[^>]*>(.*?)</(?:li|td|th|summary)\s*>",
                                     source, flags=re.IGNORECASE | re.DOTALL)
            if len(self._text(match.group(1))) > 500
        ]
        self.unsafe_urls = [value for value in [*self.links, *self.embeds]
                            if urlsplit(value).scheme.lower() in {"javascript", "data", "vbscript", "file"}]
        self.meta_refresh = bool(re.search(
            r"<meta\b[^>]*http-equiv\s*=\s*([\"'])?refresh\1", source, flags=re.IGNORECASE))

    @staticmethod
    def _attribute(attrs: str, name: str) -> str | None:
        match = re.search(rf"\b{re.escape(name)}\s*=\s*([\"'])(.*?)\1", attrs, flags=re.IGNORECASE | re.DOTALL)
        return html.unescape(match.group(2)) if match else None

    @staticmethod
    def _text(fragment: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", fragment))).strip()

    @staticmethod
    def _find_loose_text(source: str) -> list[str]:
        permitted = {"title", "nav", "a", "h1", "h2", "h3", "p", "li", "td", "th", "summary"}
        void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
        stack: list[str] = []
        loose = []
        for match in re.finditer(r"<!--.*?-->|<[^>]*>|[^<]+", source, flags=re.DOTALL):
            token = match.group(0)
            if token.startswith("<!--") or token.startswith("<!") or token.startswith("<?"):
                continue
            if token.startswith("<"):
                tag = re.match(r"<\s*(/?)\s*([A-Za-z][A-Za-z0-9:-]*)", token)
                if not tag:
                    continue
                name = tag.group(2).lower()
                if tag.group(1):
                    for position in range(len(stack) - 1, -1, -1):
                        if stack[position] == name:
                            del stack[position:]
                            break
                elif name not in void and not token.rstrip().endswith("/>"):
                    stack.append(name)
            elif token.strip() and not (set(stack) & permitted):
                loose.append(token.strip())
        return loose


def _expected_exclusion_details(impact: dict) -> set[str]:
    details = set()
    for row in [*impact.get("records", []), *impact.get("standalone_assets", [])]:
        if row.get("rights_status") in {"ELIGIBLE_CC0", "ELIGIBLE_PD", "CLEARED"}:
            continue
        label = row.get("source_group") or row.get("license") or "This edition"
        completeness = row.get("completeness_status")
        details.add(f"{label}. Completeness: {completeness}." if completeness else label)
    return details


def _parse_page(path: Path) -> PageAudit:
    return PageAudit(path.read_text(encoding="utf-8"))


def _validate_navigation_index(path: Path, relative: str) -> None:
    if relative == PETAKOPADESA_INDEX:
        if digest(path) != PETAKOPADESA_INDEX_SHA256:
            raise ValueError(f"The reviewed metadata-only Peṭakopadesa index changed: {relative}")
        return
    parser = _parse_page(path)
    if parser.tags & FORBIDDEN_HTML_TAGS:
        raise ValueError(f"Navigation index contains active or source-text markup: {relative}")
    unknown = parser.tags - HTML_TAGS
    if unknown:
        raise ValueError(f"Navigation index contains unreviewed HTML tags {sorted(unknown)}: {relative}")
    if (parser.event_attributes or parser.inline_styles or parser.comments or parser.unsafe_urls
            or parser.meta_refresh or parser.loose_text or parser.long_titles or parser.long_navigation_items):
        raise ValueError(f"Navigation index contains executable or unreviewed HTML: {relative}")
    if len(parser.headings) < 1 or not parser.links:
        raise ValueError(f"Navigation index lacks its heading or links: {relative}")
    link_text_budget = LARGE_INDEX_LINK_TEXT_BUDGETS.get(relative, 5000)
    if (parser.max_heading_text > 300 or parser.max_text_attribute > 300
            or parser.total_text_attributes > 1000 or parser.total_anchor_text > link_text_budget
            or any(len(paragraph) > 500 for paragraph in parser.paragraphs)
            or parser.total_paragraph_text > 1500 or len(parser.paragraphs) > 8
            or len(parser.unlinked_text) > 5000 or parser.table_unlinked_text > 2000):
        raise ValueError(f"Navigation index has excessive unlinked prose; inspect for copied text: {relative}")
    if parser.max_anchor_text > 300:
        raise ValueError(f"Navigation index has an unexpectedly long linked text block: {relative}")
    if parser.embeds:
        if relative != PETAKOPADESA_INDEX or parser.embeds != [PETAKOPADESA_EMBED]:
            raise ValueError(f"Navigation index embeds an unapproved document: {relative}")


def license_scope_for(path_text: str, approved_entries: dict[str, dict]) -> str:
    """Read rights only from an exact, explicitly approved file entry."""
    entry = approved_entries.get(path_text)
    if not isinstance(entry, dict):
        raise ValueError(f"No exact approved rights entry for repository file: {path_text}")
    scope = entry.get("license_scope")
    if scope not in RIGHTS_BASIS_BY_SCOPE:
        raise ValueError(f"No recognized license scope for repository file: {path_text}")
    if entry.get("rights_basis") != RIGHTS_BASIS_BY_SCOPE[scope]:
        raise ValueError(f"File rights basis is missing or incorrect: {path_text}")
    return scope


def validate_legacy_text_routes(content_root: Path, impact_map_path: Path = IMPACT_MAP) -> int:
    """Validate every non-index HTML route as an exact notice or approved scan index."""
    impact = json.loads(impact_map_path.read_text(encoding="utf-8"))
    details = _expected_exclusion_details(impact)
    checked = 0
    for page in content_root.rglob("*.html"):
        relative = page.relative_to(content_root).as_posix()
        if relative.startswith("site/"):
            continue
        full_relative = page.relative_to(ROOT).as_posix() if page.is_relative_to(ROOT) else relative
        if page.name == "index.html":
            _validate_navigation_index(page, full_relative)
            checked += 1
            continue

        parser = _parse_page(page)
        if parser.tags & FORBIDDEN_HTML_TAGS or parser.tags - ROUTE_TAGS:
            raise ValueError(f"Legacy route contains unapproved content markup: {full_relative}")
        if (parser.event_attributes or parser.inline_styles or parser.embeds or parser.comments
                or parser.unsafe_urls or parser.meta_refresh or parser.loose_text or parser.long_titles
                or parser.long_navigation_items):
            raise ValueError(f"Legacy route contains active or embedded content: {full_relative}")
        if len(parser.headings) != 1 or len(parser.paragraphs) not in {2, 3}:
            raise ValueError(f"Legacy route is not a metadata-only notice page: {full_relative}")
        if full_relative == PD_SCAN_ROUTE:
            if (not parser.paragraphs[0].startswith("The historical edition is cleared as public domain")
                    or parser.paragraphs[1] != "Public domain in the United States"
                    or not parser.links or any(not link for link in parser.links)):
                raise ValueError(f"Historical scan-link page no longer matches its metadata-only form: {full_relative}")
            checked += 1
            continue
        if (len(parser.paragraphs) != 3
                or not parser.paragraphs[0].startswith(EXCLUDED_ROUTE_NOTICE)
                or parser.paragraphs[1] not in details
                or parser.paragraphs[2] != ROUTE_FOOTER):
            raise ValueError(
                "Legacy route must contain exactly its approved exclusion notice and metadata, "
                f"not translation text: {full_relative}"
            )
        checked += 1
    return checked


def expected_license_scopes(
    actual: set[str], approved_entries: dict[str, dict]
) -> tuple[dict[str, str], int]:
    eligible = json.loads(ELIGIBLE.read_text(encoding="utf-8"))
    assets = json.loads(ASSETS.read_text(encoding="utf-8"))
    scope_by_path = {entry["local_path"]: entry["license"] for entry in eligible["texts"]}
    scope_by_path.update({entry["local_path"]: entry["license"] for entry in assets["assets"]})
    site_manifest = validate_site_content_manifest(ROOT)
    scope_by_path.update({path: SITE_SCOPE for path in site_manifest})
    for path_text in actual:
        if path_text not in scope_by_path:
            scope_by_path[path_text] = license_scope_for(path_text, approved_entries)

    content_root = ROOT / "theravada" / "tipitaka"
    route_count = validate_legacy_text_routes(content_root)
    for path_text in site_manifest:
        page_path = ROOT / path_text
        parser = _parse_page(page_path)
        exact_entry_redirect = (
            path_text == "site-entry/index.html"
            and re.search(
                r'<meta\s+http-equiv="refresh"\s+content="0;\s*url=/theravada/tipitaka/site/index\.html"\s*/?>',
                page_path.read_text(encoding="utf-8"), flags=re.IGNORECASE,
            ) is not None
        )
        if (parser.tags & FORBIDDEN_HTML_TAGS or parser.event_attributes or parser.inline_styles
                or parser.comments or parser.unsafe_urls or (parser.meta_refresh and not exact_entry_redirect)):
            raise ValueError(f"Project site page contains active embedded content: {path_text}")
    expected_html = {name for name in actual if name.endswith(".html") and name.startswith("theravada/tipitaka/")}
    assigned_html = expected_html & set(scope_by_path)
    if assigned_html != expected_html:
        raise ValueError("One or more Tipitaka HTML files lack explicit navigation/site rights scope")
    return scope_by_path, route_count


TEXT_EXCLUSION_FIELDS = {
    "record_id", "canonical_id", "collection", "source_group", "title", "translator",
    "translator_label", "source_url", "historical_local_paths", "license", "rights_status",
    "exclusion_reason", "rights_evidence", "completeness_status", "completeness_scope",
    "completeness_evidence", "existing_site_routes",
}
ASSET_EXCLUSION_FIELDS = {
    "record_id", "asset_type", "canonical_id", "collection", "title", "translator",
    "source_url", "license", "rights_status", "exclusion_reason", "completeness_status",
    "completeness_scope", "existing_site_routes",
}
TEXT_ROUTE_FIELDS = {
    "reader_html", "reader_txt", "reader_pdf", "source_text", "source_pdf", "canonical_index",
    "collection_index", "tipitaka_index", "downloads_index", "global_archives",
    "collection_archive", "archive_membership", "upstream_source_page",
}
EXTERNAL_ROUTE_FIELDS = {"source_page", "upstream_source_page"}
ASSET_ROUTE_FIELDS = {
    "canonical_index", "collection_index", "collection_archive", "direct_file", "direct_pdf",
    "global_archives", "reader_html", "reader_page", "source_page", "generated_story_page_count",
    "generated_story_pages",
}


def _require_https_url(value: str, label: str, *, internal_route: bool = False, allow_empty: bool = False) -> None:
    if allow_empty and not value:
        return
    if len(value) > 250:
        raise ValueError(f"Excluded-source URL metadata is too long: {label}")
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError(f"Excluded-source URL metadata is invalid: {label}")
    if internal_route:
        decoded_path = unquote(parts.path)
        segments = decoded_path.split("/")
        if (parts.netloc.lower() != "freebuddhism.org" or "\\" in decoded_path
                or "%" in parts.path or any(segment in {".", ".."} for segment in segments)
                or not decoded_path.startswith("/theravada/tipitaka/")
                or parts.query or parts.fragment):
            raise ValueError(f"Excluded-source internal route is outside the local Tipiṭaka site: {label}")


def _validate_exclusion_routes(routes: object, allowed_fields: set[str], label: str) -> None:
    if not isinstance(routes, dict) or set(routes) - allowed_fields:
        raise ValueError(f"Excluded-source routes have unknown fields: {label}")
    for key, value in routes.items():
        if key in {"global_archives", "generated_story_pages"}:
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"Excluded-source route must be a string list: {label}.{key}")
            for index, item in enumerate(value):
                _require_https_url(item, f"{label}.{key}[{index}]", internal_route=True)
        elif key == "generated_story_page_count":
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"Excluded-source route count is invalid: {label}.{key}")
        elif key == "archive_membership":
            allowed = {"all", "collection_zip", "html", "pdf", "txt"}
            if not isinstance(value, dict) or set(value) != allowed:
                raise ValueError(f"Excluded-source archive membership is malformed: {label}")
            if not all(isinstance(value[name], bool) for name in ("all", "html", "pdf", "txt")):
                raise ValueError(f"Excluded-source archive flags must be booleans: {label}")
            nested = value["collection_zip"]
            if not isinstance(nested, dict) or set(nested) != {"html", "pdf", "txt"}:
                raise ValueError(f"Excluded-source collection archive flags are malformed: {label}")
            if not all(isinstance(flag, bool) for flag in nested.values()):
                raise ValueError(f"Excluded-source collection archive flags must be booleans: {label}")
        elif not isinstance(value, str):
            raise ValueError(f"Excluded-source route value must be text metadata: {label}.{key}")
        else:
            _require_https_url(value, f"{label}.{key}", internal_route=key not in EXTERNAL_ROUTE_FIELDS,
                               allow_empty=True)


def validate_excluded_inventory(excluded: dict) -> None:
    required = {
        "schema_version", "content_policy", "counts", "license",
        "rights_and_completeness_are_independent", "text_versions", "standalone_assets",
    }
    if set(excluded) != required or excluded.get("schema_version") != 1:
        raise ValueError("Excluded-source inventory schema is not recognized")
    if excluded.get("content_policy") != "Metadata only; excluded source text is never copied here.":
        raise ValueError("Excluded-source inventory must declare metadata-only content")
    if excluded.get("license") != "CC0-1.0" or excluded.get("rights_and_completeness_are_independent") is not True:
        raise ValueError("Excluded-source inventory has an invalid rights declaration")
    if not isinstance(excluded.get("counts"), dict):
        raise ValueError("Excluded-source inventory counts are malformed")

    texts = excluded.get("text_versions")
    assets = excluded.get("standalone_assets")
    if not isinstance(texts, list) or len(texts) != 1268:
        raise ValueError("Expected exactly 1,268 excluded text-version metadata records")
    if not isinstance(assets, list) or len(assets) != 11:
        raise ValueError("Expected all 11 excluded standalone-asset records")

    text_limits = {
        "record_id": 150, "canonical_id": 50, "collection": 50, "source_group": 100,
        "title": 120, "translator": 100, "source_url": 250,
        "license": 100, "rights_status": 40, "exclusion_reason": 200,
        "completeness_status": 20, "completeness_scope": 200,
    }
    asset_limits = {
        "asset_type": 50, "collection": 50, "title": 120,
        "translator": 100, "source_url": 250, "license": 100, "rights_status": 40,
        "exclusion_reason": 200, "completeness_status": 20, "completeness_scope": 200,
    }
    for collection, expected_fields, route_fields, string_limits, label in (
        (texts, TEXT_EXCLUSION_FIELDS, TEXT_ROUTE_FIELDS, text_limits, "text_versions"),
        (assets, ASSET_EXCLUSION_FIELDS, ASSET_ROUTE_FIELDS, asset_limits, "standalone_assets"),
    ):
        identifiers = set()
        for index, row in enumerate(collection):
            row_label = f"{label}[{index}]"
            if not isinstance(row, dict) or set(row) != expected_fields:
                raise ValueError(f"Excluded-source record fields are not recognized: {row_label}")
            record_id = row.get("record_id")
            if record_id is not None:
                if not isinstance(record_id, str) or not record_id or record_id in identifiers:
                    raise ValueError(f"Excluded-source record ID is missing or duplicated: {row_label}")
                identifiers.add(record_id)
            if label == "text_versions" and not record_id:
                raise ValueError(f"Excluded text version is missing its stable record ID: {row_label}")
            for name, limit in string_limits.items():
                if not isinstance(row.get(name), str) or not row[name] or len(row[name]) > limit:
                    raise ValueError(f"Excluded-source metadata is incomplete: {row_label}.{name}")
            if label == "standalone_assets":
                for nullable_name in ("record_id", "canonical_id"):
                    value = row.get(nullable_name)
                    if value is not None and (not isinstance(value, str) or len(value) > 150):
                        raise ValueError(f"Excluded-source metadata field is invalid: {row_label}.{nullable_name}")
            if label == "text_versions" and not isinstance(row.get("canonical_id"), str):
                raise ValueError(f"Excluded text version canonical ID must be text: {row_label}")
            if label == "text_versions" and row.get("translator_label") is not None:
                if not isinstance(row["translator_label"], str) or len(row["translator_label"]) > 120:
                    raise ValueError(f"Excluded-source metadata field is invalid: {row_label}.translator_label")
            _require_https_url(row["source_url"], f"{row_label}.source_url")
            if row["rights_status"] not in {"RIGHTS_RESTRICTED", "RIGHTS_UNVERIFIED", "PERMISSION_SCOPE_UNCLEAR"}:
                raise ValueError(f"Excluded-source rights status is invalid: {row_label}")
            if row["completeness_status"] not in {"COMPLETE", "PARTIAL", "UNKNOWN"}:
                raise ValueError(f"Excluded-source completeness status is invalid: {row_label}")
            if not isinstance(row.get("historical_local_paths", []), list) or not all(
                    isinstance(path, str) for path in row.get("historical_local_paths", [])):
                raise ValueError(f"Excluded-source historical paths are malformed: {row_label}")
            for evidence_name in ("rights_evidence", "completeness_evidence"):
                if evidence_name in row:
                    evidence = row[evidence_name]
                    if (not isinstance(evidence, dict) or set(evidence) != {"note", "urls"}
                            or not isinstance(evidence["note"], str)
                            or len(evidence["note"]) > 220
                            or not isinstance(evidence["urls"], list)
                            or not all(isinstance(url, str) for url in evidence["urls"])):
                        raise ValueError(f"Excluded-source evidence is malformed: {row_label}.{evidence_name}")
                    for evidence_index, url in enumerate(evidence["urls"]):
                        _require_https_url(url, f"{row_label}.{evidence_name}.urls[{evidence_index}]")
            for index, path in enumerate(row.get("historical_local_paths", [])):
                if (len(path) > 200 or path.startswith(("/", "\\")) or ".." in Path(path).parts
                        or "\\" in path):
                    raise ValueError(f"Excluded-source historical path is unsafe: {row_label}[{index}]")
            _validate_exclusion_routes(row.get("existing_site_routes"), route_fields, row_label)

    counts = excluded["counts"]
    if set(counts) != {"excluded_text_versions", "excluded_standalone_assets", "rights_status", "completeness_status"}:
        raise ValueError("Excluded-source inventory counts have unknown fields")
    expected_status_counts = {
        "rights_status": {"RIGHTS_RESTRICTED", "RIGHTS_UNVERIFIED", "PERMISSION_SCOPE_UNCLEAR"},
        "completeness_status": {"COMPLETE", "PARTIAL", "UNKNOWN"},
    }
    for name, expected_statuses in expected_status_counts.items():
        values = counts.get(name)
        if (not isinstance(values, dict) or set(values) != expected_statuses
                or not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0
                           for value in values.values())
                or sum(values.values()) != len(texts)):
            raise ValueError(f"Excluded-source inventory {name} counts are malformed")
    if (counts.get("excluded_text_versions") != len(texts)
            or counts.get("excluded_standalone_assets") != len(assets)):
        raise ValueError("Excluded-source inventory counts do not match its records")


def check() -> dict:
    allowlist = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    entries = allowlist["files"]
    if allowlist.get("scope") != "Exact path, content hash, license scope, and rights basis are required; new files are denied by default.":
        raise ValueError("Public file allowlist has an invalid scope declaration")
    for entry in entries:
        expected_fields = {"path", "sha256", "license_scope", "rights_basis"}
        if isinstance(entry, dict) and entry.get("self_referential") is True:
            expected_fields.add("self_referential")
        if not isinstance(entry, dict) or set(entry) != expected_fields:
            raise ValueError("Public file allowlist entries must have exact path/hash/license/rights fields")
    listed = {entry["path"]: entry for entry in entries}
    if len(listed) != len(entries):
        raise ValueError("Public file allowlist contains duplicate paths")
    actual = actual_files()
    expected_paths = actual | {SELF}
    missing = sorted(set(listed) - expected_paths)
    unexpected = sorted(expected_paths - set(listed))
    changed = sorted(path for path in actual & set(listed) if digest(ROOT / path) != listed[path]["sha256"])
    self_entry = listed.get(SELF, {})
    if self_entry != {
        "path": SELF,
        "sha256": None,
        "license_scope": "CC0-1.0 project metadata",
        "rights_basis": SELF_RIGHTS_BASIS,
        "self_referential": True,
    }:
        raise ValueError("Public file allowlist must declare its self-referential metadata entry")
    if missing or unexpected or changed:
        raise ValueError(
            f"Repository allowlist mismatch: missing={missing[:10]}, "
            f"unexpected={unexpected[:10]}, changed={changed[:10]}"
        )

    scopes, route_count = expected_license_scopes(actual, listed)
    scopes[SELF] = "CC0-1.0 project metadata"
    wrong_scopes = sorted(
        path for path in actual
        if listed[path].get("license_scope") != scopes.get(path)
    )
    if wrong_scopes:
        raise ValueError(f"Public file allowlist has missing or incorrect license scopes: {wrong_scopes[:20]}")
    wrong_basis = sorted(
        path for path in actual
        if listed[path].get("rights_basis") != RIGHTS_BASIS_BY_SCOPE.get(scopes.get(path))
    )
    if wrong_basis:
        raise ValueError(f"Public file allowlist has missing or incorrect rights evidence: {wrong_basis[:20]}")

    eligible = json.loads(ELIGIBLE.read_text(encoding="utf-8"))
    expected_texts = {entry["local_path"] for entry in eligible["texts"]}
    assets = json.loads(ASSETS.read_text(encoding="utf-8"))
    expected_assets = {entry["local_path"] for entry in assets["assets"]}
    content_root = ROOT / "theravada" / "tipitaka"
    actual_sources = {
        path.relative_to(ROOT).as_posix()
        for path in content_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".txt", ".pdf"}
    }
    expected_sources = expected_texts | expected_assets
    if actual_sources != expected_sources:
        raise ValueError(
            "Translation source tree differs from the approved manifests: "
            f"unexpected={sorted(actual_sources - expected_sources)[:10]}, "
            f"missing={sorted(expected_sources - actual_sources)[:10]}"
        )
    for entry in eligible["texts"]:
        if digest(ROOT / entry["local_path"]) != entry["sha256"]:
            raise ValueError(f"Approved text changed: {entry['local_path']}")
    for entry in assets["assets"]:
        if digest(ROOT / entry["local_path"]) != entry["sha256"]:
            raise ValueError(f"Approved source asset changed: {entry['local_path']}")

    excluded = json.loads(EXCLUDED.read_text(encoding="utf-8"))
    validate_excluded_inventory(excluded)
    excluded_paths = {path for entry in excluded["text_versions"] for path in entry.get("historical_local_paths", [])}
    if excluded_paths & actual:
        raise ValueError("An excluded text path is also listed as eligible")

    return {
        "repository_files": len(actual),
        "allowlisted_files": len(listed),
        "eligible_texts": len(eligible["texts"]),
        "excluded_text_versions": len(excluded["text_versions"]),
        "excluded_standalone_assets": len(excluded["standalone_assets"]),
        "source_hashes_verified": len(expected_sources),
        "html_routes_checked": route_count,
    }


def refresh_allowlist_entries(
    actual: set[str], existing_entries: list[dict], reviewed_paths: set[str], root: Path = ROOT,
) -> list[dict]:
    """Refresh hashes only for reviewed, already-allowlisted paths; never add files."""
    existing = {entry.get("path"): entry for entry in existing_entries if isinstance(entry, dict)}
    if len(existing) != len(existing_entries):
        raise ValueError("Existing allowlist has duplicate or malformed entries")
    if set(existing) - {SELF} != actual:
        missing = sorted((set(existing) - {SELF}) - actual)
        new_paths = sorted(actual - (set(existing) - {SELF}))
        raise ValueError(
            "Refusing to add or remove files during checksum refresh: "
            f"untracked={new_paths[:10]}, missing={missing[:10]}. Add rights-reviewed entries manually first."
        )
    if SELF in reviewed_paths or reviewed_paths - actual:
        raise ValueError("Reviewed paths must be existing, non-self allowlist entries")

    refreshed = []
    for path_text in sorted(actual):
        old = existing[path_text]
        scope = old.get("license_scope")
        basis = RIGHTS_BASIS_BY_SCOPE.get(scope)
        if basis is None or old.get("rights_basis", basis) != basis:
            raise ValueError(f"Existing rights entry needs manual correction: {path_text}")
        current_hash = digest(root / path_text)
        if current_hash != old.get("sha256") and path_text not in reviewed_paths:
            raise ValueError(f"Changed file was not explicitly reviewed for checksum refresh: {path_text}")
        refreshed.append({
            "path": path_text,
            "sha256": current_hash,
            "license_scope": scope,
            "rights_basis": basis,
        })

    old_self = existing.get(SELF)
    if old_self and old_self.get("license_scope") != "CC0-1.0 project metadata":
        raise ValueError("Self-referential allowlist entry has an invalid license scope")
    refreshed.append({
        "path": SELF,
        "sha256": None,
        "license_scope": "CC0-1.0 project metadata",
        "rights_basis": SELF_RIGHTS_BASIS,
        "self_referential": True,
    })
    return refreshed


def write_allowlist(reviewed_paths: set[str]) -> dict:
    allowlist = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    actual = actual_files()
    entries = refresh_allowlist_entries(actual, allowlist.get("files", []), reviewed_paths)
    ALLOWLIST.write_text(
        json.dumps({
            "scope": "Exact path, content hash, license scope, and rights basis are required; new files are denied by default.",
            "files": entries,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"allowlisted_files": len(entries), "reviewed_paths": sorted(reviewed_paths)}


if __name__ == "__main__":
    try:
        if len(sys.argv) >= 4 and sys.argv[1:3] == ["--write", "--reviewed-files"]:
            print(json.dumps(write_allowlist(set(sys.argv[3:])), indent=2))
        elif not sys.argv[1:]:
            print(json.dumps(check(), indent=2))
        else:
            raise ValueError(
                "Usage: validate_public_tree.py [--write --reviewed-files <path> [<path> ...]]"
            )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"public-tree validation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
