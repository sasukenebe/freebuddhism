#!/usr/bin/env python3
"""Build uniform readers for editions with documented redistribution rights."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from public_site_catalog import COLLECTION_TITLES, canonical_slug, collection_breadcrumbs, navigation_nodes, natural_key, slug, edition_priority
from render_cc0_reader import ReaderParser, normalized, render_html, render_pdf, verify_pdf_body
from import_candana import LICENSE as CANDANA_LICENSE, verified_manifest as candana_manifest


ROOT = Path(__file__).resolve().parents[2]
TIPITAKA = ROOT / "theravada" / "tipitaka"
CC0 = "CC0-1.0"
CC0_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
COWELL_PD = "Public Domain (original English edition, published 1895–1907)"
PDF_RENDERER_VERSION = 4
PDF_CACHE = ROOT / "build" / "eligible-reader-pdfs.json"
PDF_CONFIG_FIELDS = (
    "canonical_id", "title", "translator", "source_url", "source_revision",
    "license", "license_url", "metadata_notes",
)


@dataclass(frozen=True)
class Policy:
    ledger: str
    manifest: str
    license: str
    collection_kind: str
    repository: str


POLICIES = (
    Policy("sutta/suttacentral-sujato-text-ledger.tsv", "suttacentral-bilara.json", CC0, "sutta", "https://github.com/suttacentral/bilara-data"),
    Policy("sutta/suttacentral-bulk-text-ledger.tsv", "suttacentral-published-sutta.json", CC0, "sutta", "https://github.com/suttacentral/bilara-data"),
    Policy("sutta/suttacentral-kelly-text-ledger.tsv", "suttacentral-kelly-mil.json", CC0, "sutta", "https://github.com/suttacentral/bilara-data"),
    Policy("sutta/suttacentral-kelly-mil521-text-ledger.tsv", "suttacentral-kelly-mil521.json", CC0, "sutta", "https://github.com/suttacentral/bilara-data"),
    Policy("sutta/suttacentral-kovilo-text-ledger.tsv", "suttacentral-kovilo-pv.json", CC0, "sutta", "https://github.com/suttacentral/bilara-data"),
    Policy("sutta/cowell-jataka-text-ledger.tsv", "cowell-jataka.json", COWELL_PD, "sutta", "https://github.com/suttacentral/sc-data"),
    Policy("vinaya/suttacentral-brahmali-vinaya-ledger.tsv", "suttacentral-brahmali-vinaya.json", CC0, "vinaya", "https://github.com/suttacentral/bilara-data"),
)

VINAYA_CONTENTS = {
    "bhikkhu-patimokkha": ("sutta-vibhanga/index.html", "Monks’ Pāṭimokkha"),
    "bhikkhu-vibhanga": ("bhikkhu-vibhanga/index.html", "Mahā Vibhaṅga"),
    "bhikkhuni-patimokkha": ("sutta-vibhanga/index.html", "Nuns’ Pāṭimokkha"),
    "bhikkhuni-vibhanga": ("bhikkhuni-vibhanga/index.html", "Bhikkhunī Vibhaṅga"),
    "mahavagga": ("mahavagga/index.html", "Mahāvagga"),
    "cullavagga": ("cullavagga/index.html", "Cullavagga"),
    "parivara": ("parivara/index.html", "Parivāra"),
}


def repo_path(relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Expected a repository-relative path: {relative}")
    resolved = (ROOT / path).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as error:
        raise ValueError(f"Path resolves outside the repository: {relative}") from error
    return resolved


def version_slug(row: dict[str, str]) -> str:
    explicit = row.get("version_slug", "").strip()
    if explicit:
        return explicit
    author = re.fullmatch(r"https://suttacentral.net/[^/]+/en/([a-z0-9-]+)", row.get("source_url", ""))
    if author:
        return author.group(1)
    path_author = re.search(r"/suttacentral/([a-z0-9-]+)/", row.get("txt_path", ""))
    if path_author:
        return path_author.group(1)
    raise ValueError(f"No translation identifier for {row.get('canonical_id') or row.get('source_id')}")


def parse_source_text(path: Path, row: dict[str, str], expected_license: str) -> tuple[str, str, list[str], str, str]:
    raw = path.read_bytes()
    source = raw.decode("utf-8")
    if "\n\n" not in source:
        raise ValueError(f"Missing source metadata separator: {path.relative_to(ROOT)}")
    header, body = source.split("\n\n", 1)
    header_lines = header.splitlines()
    license_lines = [line.removeprefix("License: ") for line in header_lines if line.startswith("License: ")]
    if license_lines != [expected_license]:
        raise ValueError(f"Text header license does not match its ledger: {path.relative_to(ROOT)}")
    source_url = row.get("source_url", "")
    if not source_url or source_url not in header:
        raise ValueError(f"Source URL is absent from the text header: {path.relative_to(ROOT)}")
    translator = next((line.removeprefix("Translated by ") for line in header_lines
                       if line.startswith("Translated by ")), row.get("version_label", ""))
    metadata_notes = [line for line in header_lines[1:]
                      if not line.startswith(("Translated by ", "Source:", "Source HTML:", "License: "))]
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if not body.strip():
        raise ValueError(f"Text body is empty: {path.relative_to(ROOT)}")
    return source, body, metadata_notes, translator, body_hash


def title_for(row: dict[str, str], header: str) -> str:
    label = row.get("label", "").strip()
    if label:
        return label
    canonical_id = row.get("canonical_id") or row.get("source_id", "")
    first_line = header.splitlines()[0] if header else ""
    for separator in (" - ", " — ", ": "):
        prefix = canonical_id + separator
        if first_line.startswith(prefix):
            return first_line[len(prefix):].strip()
    return canonical_id


def verify_policy(policy: Policy, manifest: dict, row: dict[str, str]) -> None:
    if manifest.get("license") != policy.license or row.get("license") != policy.license:
        raise ValueError(f"License mismatch in {policy.ledger}: {row.get('canonical_id') or row.get('source_id')}")
    if policy.license == CC0 and manifest.get("license_url") != CC0_URL:
        raise ValueError(f"CC0 URL missing from {policy.manifest}")
    revision = row.get("source_commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError(f"Missing pinned source revision in {policy.ledger}")
    manifest_revision = manifest.get("commit") or manifest.get("source_commit")
    if manifest_revision and revision != manifest_revision:
        raise ValueError(f"Record revision differs from {policy.manifest}: {revision}")
    repository = (manifest.get("repository") or manifest.get("source_repository") or "").removesuffix(".git")
    if repository and repository != policy.repository:
        raise ValueError(f"Source repository mismatch in {policy.manifest}")
    if not repository:
        snapshot_dir = manifest.get("snapshot_dir")
        if not snapshot_dir:
            raise ValueError(f"Source repository missing from {policy.manifest}")
        publication_path = repo_path(f"{snapshot_dir}/publication.json")
        publication = json.loads(publication_path.read_text(encoding="utf-8"))
        source_url = publication.get("source_url", "")
        if not source_url.startswith(policy.repository + "/tree/"):
            raise ValueError(f"Pinned publication metadata does not verify the source repository: {policy.manifest}")
        if manifest.get("translator") and publication.get("author_name") != manifest["translator"]:
            raise ValueError(f"Pinned publication translator differs from {policy.manifest}")
    if policy.license == COWELL_PD:
        evidence = manifest.get("license_evidence", {})
        if not evidence.get("basis") or not evidence.get("smithsonian_rights_urls"):
            raise ValueError("Cowell public-domain evidence is incomplete")
        if manifest.get("scope", "").find("547 numbered") < 0:
            raise ValueError("Cowell manifest does not attest the complete 547-story scope")


def sutta_output_paths(row: dict[str, str], output_root: Path) -> tuple[Path, str, Path]:
    canonical_id = row["canonical_id"]
    version = version_slug(row)
    folder_name = canonical_slug(canonical_id)
    folder = output_root / "theravada" / "tipitaka" / "sutta" / row["collection_path"] / folder_name
    base_name = f"{folder_name}-{version}"
    return folder, base_name, folder / f"{base_name}.html"


def vinaya_output_paths(row: dict[str, str], output_root: Path) -> tuple[Path, str, Path]:
    folder = output_root / "theravada" / "tipitaka" / "vinaya" / "texts" / "pages" / slug(row["source_id"])
    base_name = slug(row["source_id"])
    return folder, base_name, folder / "index.html"


def collect_records(output_root: Path = ROOT) -> list[dict]:
    records: list[dict] = []
    for policy in POLICIES:
        manifest = json.loads(repo_path(f"metadata/source-manifests/{policy.manifest}").read_text(encoding="utf-8"))
        ledger_path = TIPITAKA / policy.ledger
        with ledger_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, dialect="excel-tab"))
        for row in rows:
            if row.get("license") != policy.license:
                raise ValueError(f"Unreviewed license in eligible ledger {policy.ledger}: {row.get('license')}")
            verify_policy(policy, manifest, row)
            if policy.collection_kind == "sutta":
                row_collection = row["collection_path"]
                folder, base_name, output_html = sutta_output_paths(row, output_root)
                site_path = ROOT / output_html.relative_to(output_root)
                entry_page = TIPITAKA / "sutta" / row_collection / canonical_slug(row["canonical_id"]) / "index.html"
                entry_href = route_for(entry_page, site_path)
                collection_relative = Path("sutta") / row_collection / "index.html"
                collection_label = COLLECTION_TITLES.get(row_collection, row_collection)
                canonical_id = row["canonical_id"]
                version = version_slug(row)
                source_label = f"SuttaCentral · {canonical_id}" if "suttacentral" in policy.manifest else "Cowell Jātaka source article"
            else:
                folder, base_name, output_html = vinaya_output_paths(row, output_root)
                if row["group"] not in VINAYA_CONTENTS:
                    raise ValueError(f"Unknown Vinaya source group: {row['group']}")
                contents_relative, collection_label = VINAYA_CONTENTS[row["group"]]
                entry_page = TIPITAKA / "vinaya" / contents_relative
                site_path = ROOT / output_html.relative_to(output_root)
                entry_href = route_for(entry_page, site_path)
                collection_relative = Path("vinaya") / contents_relative
                canonical_id = row["source_id"]
                version = "brahmali"
                source_label = f"SuttaCentral · {canonical_id}"
            text_path = repo_path(row["txt_path"])
            source, body, metadata_notes, translator, body_hash = parse_source_text(text_path, row, policy.license)
            header = source.split("\n\n", 1)[0]
            title = title_for(row, header)
            repository = manifest.get("repository", "").removesuffix(".git") or manifest.get("source_repository") or policy.repository
            record = {
                "kind": policy.collection_kind,
                "policy": policy,
                "manifest": manifest,
                "row": row,
                "canonical_id": canonical_id,
                "collection": row.get("collection_path", row.get("group", "")),
                "collection_label": collection_label,
                "collection_page": TIPITAKA / collection_relative,
                "folder": folder,
                "base_name": base_name,
                "html_path": output_html,
                "site_path": site_path,
                "output_root": output_root,
                "pdf_path": folder / f"{base_name}-reader.pdf",
                "entry_page": entry_page,
                "entry_href": entry_href,
                "version": version,
                "version_label": row.get("version_label", "Bhikkhu Brahmali translation"),
                "translator": translator,
                "title": title,
                "source_url": row["source_url"],
                "source_repository": repository,
                "source_revision": row["source_commit"],
                "upstream_file": row.get("upstream_file", ""),
                "license": policy.license,
                "license_url": manifest.get("license_url", ""),
                "source_label": source_label,
                "text_path": text_path,
                "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                "body": body,
                "body_sha256": body_hash,
                "metadata_notes": metadata_notes,
            }
            records.append(record)
    records.extend(collect_candana_records(output_root))
    keys = [(record["kind"], record["collection"], record["canonical_id"], record["version"]) for record in records]
    if len(keys) != len(set(keys)):
        raise ValueError("Eligible ledgers contain duplicate text/version identifiers")
    return records


def collect_candana_records(output_root: Path) -> list[dict]:
    manifest = candana_manifest(require_review=True)
    books = {row["id"]: row for row in manifest["books"]}
    records = []
    for item in manifest["texts"]:
        row = {**item, "collection_path": item["collection"], "txt_path": item["local_path"],
               "version_slug": "candana", "label": item["title"],
               "version_label": "Bhikkhu Candana translation"}
        folder, base_name, output_html = sutta_output_paths(row, output_root)
        site_path = ROOT / output_html.relative_to(output_root)
        entry_page = TIPITAKA / "sutta" / item["collection"] / canonical_slug(item["canonical_id"]) / "index.html"
        text_path = repo_path(item["local_path"])
        source, body, notes, translator, body_hash = parse_source_text(text_path, row, CANDANA_LICENSE)
        book = books[item["book"]]
        records.append({
            "kind": "sutta", "policy": None, "manifest": manifest, "row": row,
            "canonical_id": item["canonical_id"], "collection": item["collection"],
            "collection_label": COLLECTION_TITLES[item["collection"]],
            "collection_page": TIPITAKA / "sutta" / item["collection"] / "index.html",
            "folder": folder, "base_name": base_name, "html_path": output_html,
            "site_path": site_path, "output_root": output_root,
            "pdf_path": folder / f"{base_name}-reader.pdf", "entry_page": entry_page,
            "entry_href": route_for(entry_page, site_path), "version": "candana",
            "version_label": "Bhikkhu Candana translation", "translator": translator,
            "title": item["title"], "source_url": item["source_url"],
            "source_repository": "", "source_revision": item["source_revision"],
            "upstream_file": book["local_path"], "license": CANDANA_LICENSE,
            "license_url": book["source_url"], "source_label": "Mind Released · " + book["title"],
            "text_path": text_path, "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "body": body, "body_sha256": body_hash, "metadata_notes": notes,
            "original_book_path": repo_path(book["local_path"]),
            "original_book_url": book["source_url"],
            "reuse_notice": item.get('reuse_notice', ''),
        })
    return records


def route_for(from_path: Path, to_path: Path) -> str:
    return Path(os.path.relpath(to_path, start=from_path.parent)).as_posix()


def display_text_title(canonical_id: str, title: str) -> str:
    canonical_id = canonical_id.strip()
    title = title.strip()
    if title.casefold() == canonical_id.casefold():
        return canonical_id
    if title.casefold().startswith(canonical_id.casefold()):
        title = title[len(canonical_id):].lstrip(" \t:—–-")
    if title.casefold().endswith(canonical_id.casefold()):
        title = title[:-len(canonical_id)].rstrip(" \t:—–-")
    return f"{canonical_id} — {title}" if title else canonical_id


def index_records(records: list[dict]) -> dict:
    by_text: dict[tuple[str, str, str], list[dict]] = {}
    by_collection: dict[tuple[str, str], list[dict]] = {}
    for item in records:
        collection_key = (item["kind"], item["collection"])
        text_key = (*collection_key, item["canonical_id"])
        by_collection.setdefault(collection_key, []).append(item)
        by_text.setdefault(text_key, []).append(item)
    for items in by_collection.values():
        items.sort(key=lambda item: (natural_key(item["canonical_id"]), item["version_label"]))
    for items in by_text.values():
        items.sort(key=edition_priority)
    positions = {}
    for collection_key, items in by_collection.items():
        canonical_order = []
        for item in items:
            if not canonical_order or canonical_order[-1] != item["canonical_id"]:
                canonical_order.append(item["canonical_id"])
        positions[collection_key] = {canonical_id: index for index, canonical_id in enumerate(canonical_order)}
    return {"by_text": by_text, "by_collection": by_collection, "positions": positions}


def config_for(record: dict, reader_index: dict) -> dict:
    collection_key = (record["kind"], record["collection"])
    text_key = (*collection_key, record["canonical_id"])
    selected = reader_index["by_text"][text_key]
    translation_links = [{
        "label": item["version_label"],
        "href": route_for(record["site_path"], item["site_path"]),
        "current": item is record,
    } for item in selected]

    positions = reader_index["positions"][collection_key]
    canonical_order = list(positions)
    position = positions[record["canonical_id"]]
    nav = {}
    for key, offset, label in (("previous", -1, "Previous"), ("next", 1, "Next")):
        neighbor_position = position + offset
        if 0 <= neighbor_position < len(canonical_order):
            neighbor_id = canonical_order[neighbor_position]
            versions = reader_index["by_text"][(*collection_key, neighbor_id)]
            neighbor = next((item for item in versions if item["version"] == record["version"]), versions[0])
            if neighbor["version"] == record["version"] or record["kind"] == "vinaya":
                target = neighbor["site_path"]
            else:
                target = neighbor["entry_page"]
            nav[f"{key}_href"] = route_for(record["site_path"], target)
            nav[f"{key}_label"] = display_text_title(neighbor_id, neighbor["title"])

    row = record["row"]
    text_href = route_for(record["site_path"], record["text_path"])
    html_href = record["html_path"].name
    pdf_href = record["pdf_path"].name
    tipitaka_site = TIPITAKA / "site"
    nodes = navigation_nodes([record["collection"]] if record["kind"] == "sutta" else [])
    if record["kind"] == "sutta":
        collection_id = record["collection"]
    else:
        collection_id = "vinaya/" + record["collection_page"].parent.name
    breadcrumbs = collection_breadcrumbs(collection_id, nodes)
    return {
        "canonical_id": record["canonical_id"],
        "title": record["title"],
        "translator": record["translator"],
        "source_url": record["source_url"],
        "source_repository": record["source_repository"],
        "source_revision": record["source_revision"],
        "license": record["license"],
        "license_url": record["license_url"],
        "source_label": record["source_label"],
        "metadata_notes": record["metadata_notes"],
        "original_book_href": record.get("original_book_url", ""),
        "collection_label": record["collection_label"],
        "collection_href": route_for(record["site_path"], record["collection_page"]),
        "contents_href": route_for(record["site_path"], record["collection_page"]),
        "contents_label": record["collection_label"] + " contents",
        "previous_href": nav.get("previous_href", ""),
        "previous_label": nav.get("previous_label", ""),
        "next_href": nav.get("next_href", ""),
        "next_label": nav.get("next_label", ""),
        "local_text_href": text_href,
        "html_download_href": html_href,
        "pdf_download_href": pdf_href,
        "translations": translation_links,
        "breadcrumbs": breadcrumbs,
        "home_href": route_for(record["site_path"], tipitaka_site / "index.html"),
        "tipitaka_href": route_for(record["site_path"], tipitaka_site / "tipitaka.html"),
    }


def expected_html(record: dict, reader_index: dict) -> str:
    return render_html(config_for(record, reader_index), record["body"])


def pdf_render_hash(config: dict) -> str:
    inputs = {key: config.get(key) for key in PDF_CONFIG_FIELDS}
    encoded = json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_cache() -> dict:
    if not PDF_CACHE.is_file():
        return {"version": PDF_RENDERER_VERSION, "pdfs": {}}
    try:
        cache = json.loads(PDF_CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": PDF_RENDERER_VERSION, "pdfs": {}}
    if cache.get("version") != PDF_RENDERER_VERSION:
        return {"version": PDF_RENDERER_VERSION, "pdfs": {}}
    return cache


def pdf_cached(record: dict, cache: dict) -> bool:
    relative = record["pdf_path"].relative_to(ROOT).as_posix()
    previous = cache["pdfs"].get(relative, {})
    path = record["pdf_path"]
    if not path.is_file() or previous.get("body_sha256") != record["body_sha256"]:
        return False
    if previous.get("render_sha256") != record["pdf_render_sha256"]:
        return False
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest == previous.get("pdf_sha256")


def record_pdf_result(record: dict, cache: dict) -> None:
    relative = record["pdf_path"].relative_to(ROOT).as_posix()
    cache["pdfs"][relative] = {
        "body_sha256": record["body_sha256"],
        "render_sha256": record["pdf_render_sha256"],
        "pdf_sha256": hashlib.sha256(record["pdf_path"].read_bytes()).hexdigest(),
    }


def validate_page(record: dict, html: str, check_pdf: bool) -> None:
    path = record["html_path"]
    if not path.is_file() or path.read_text(encoding="utf-8") != html:
        raise ValueError(f"Reader page missing or stale: {path.relative_to(ROOT)}")
    parser = ReaderParser()
    parser.feed(html)
    if "".join(parser.source_parts) != record["body"]:
        raise ValueError(f"Reader text differs from source: {path.relative_to(ROOT)}")
    for href in parser.links:
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        if parsed.path == "/":
            target = ROOT / "site-entry/index.html"
        elif parsed.path.startswith("/theravada/tipitaka/"):
            target = ROOT / unquote(parsed.path).lstrip("/")
        else:
            target = (record["site_path"].parent / unquote(parsed.path)).resolve()
        try:
            target.relative_to(ROOT.resolve())
        except ValueError as error:
            raise ValueError(f"Reader link escapes repository: {href}") from error
        overlay_target = record["output_root"] / target.relative_to(ROOT.resolve())
        if overlay_target.is_file():
            target = overlay_target
        if not target.is_file():
            if not check_pdf and parsed.path.endswith("-reader.pdf"):
                continue
            # Canonical nodes for newly imported source numbers are generated
            # during bundle assembly. The final whole-site verifier checks them.
            canonical_root = TIPITAKA / "sutta" / record["collection"]
            if (target.name == "index.html" and target.is_relative_to(canonical_root)
                    and target.parent.parent == canonical_root):
                continue
            raise ValueError(f"Reader link target missing from {path.relative_to(ROOT)}: {href}")
    # New permission-cleared editions can introduce source-numbered texts absent
    # from the legacy navigation. Their canonical pages are built in the bundle.
    if record.get("version") == "candana":
        if check_pdf:
            verify_pdf_body(record["pdf_path"], record["body"])
        return
    if not record["entry_page"].is_file():
        raise ValueError(f"Reader index missing: {record['entry_page'].relative_to(ROOT)}")
    entry = ReaderParser()
    entry.feed(record["entry_page"].read_text(encoding="utf-8"))
    if record["entry_href"] not in entry.links:
        raise ValueError(f"Reader is not linked from {record['entry_page'].relative_to(ROOT)}")
    if check_pdf:
        verify_pdf_body(record["pdf_path"], record["body"])


def render_one_pdf(record: dict, reader_index: dict) -> None:
    config = config_for(record, reader_index)
    render_pdf(config, record["body"], record["pdf_path"])
    verify_pdf_body(record["pdf_path"], record["body"])


def write_cache(cache: dict) -> None:
    PDF_CACHE.parent.mkdir(parents=True, exist_ok=True)
    temp = PDF_CACHE.with_suffix(".tmp")
    temp.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(PDF_CACHE)


def prepare_clean_output(output_root: Path) -> None:
    build_root = (ROOT / "build").resolve()
    try:
        output_root.relative_to(build_root)
    except ValueError as error:
        raise ValueError("--clean-output is restricted to generated directories under build/") from error
    marker_name = ".eligible-readers-managed"
    marker = output_root / marker_name
    if output_root.exists():
        if not marker.is_file() and any(output_root.iterdir()):
            raise ValueError(f"Refusing to clean unmarked output directory: {output_root.relative_to(ROOT)}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    (output_root / marker_name).write_text("Generated by build_eligible_readers.py\n", encoding="utf-8")


def prepare_incremental_output(output_root: Path, expected_paths: set[Path]) -> None:
    """Keep current generated assets, remove stale readers, and reject unknown files."""
    build_root = (ROOT / "build").resolve()
    try:
        output_root.relative_to(build_root)
    except ValueError as error:
        raise ValueError("--prune-output is restricted to generated directories under build/") from error

    marker = output_root / ".eligible-readers-managed"
    if output_root.exists() and (not output_root.is_dir() or output_root.is_symlink()):
        raise ValueError(f"Reader output root is not a directory: {output_root.relative_to(ROOT)}")
    output_root.mkdir(parents=True, exist_ok=True)
    if marker.is_symlink():
        raise ValueError("Refusing a symlinked eligible-reader marker")
    if marker.exists():
        if not marker.is_file():
            raise ValueError("Eligible-reader marker is not a regular file")
    elif any(output_root.iterdir()):
        raise ValueError(f"Refusing to prune unmarked output directory: {output_root.relative_to(ROOT)}")
    else:
        marker.write_text("Generated by build_eligible_readers.py\n", encoding="utf-8")

    expected = set()
    for path in expected_paths:
        resolved = path.resolve()
        try:
            resolved.relative_to(output_root)
        except ValueError as error:
            raise ValueError(f"Expected reader output escapes its root: {path}") from error
        expected.add(resolved)

    stale = []
    for path in output_root.rglob("*"):
        if path == marker:
            continue
        if path.is_symlink():
            raise ValueError(f"Refusing a symlink in reader output: {path.relative_to(ROOT)}")
        if not path.is_file() or path.resolve() in expected:
            continue
        if path.suffix == ".html" or path.name.endswith("-reader.pdf"):
            stale.append(path)
        else:
            raise ValueError(f"Unexpected file in reader output: {path.relative_to(ROOT)}")
    for path in stale:
        path.unlink()


def build(records: list[dict], all_records: list[dict], jobs: int, check: bool,
          clean_output: bool = False, prune_output: bool = False) -> None:
    reader_index = index_records(all_records)
    expected = [(record, expected_html(record, reader_index)) for record in records]
    for record, _ in expected:
        record["pdf_render_sha256"] = pdf_render_hash(config_for(record, reader_index))
    if clean_output:
        prepare_clean_output(records[0]["output_root"])
    elif prune_output:
        output_paths = {
            path
            for record in records
            for path in (record["html_path"], record["pdf_path"])
        }
        prepare_incremental_output(records[0]["output_root"], output_paths)
    cache = {"version": PDF_RENDERER_VERSION, "pdfs": {}} if clean_output else load_cache()
    if prune_output:
        expected_pdfs = {record["pdf_path"].relative_to(ROOT).as_posix() for record in records}
        cache["pdfs"] = {
            path: result for path, result in cache.get("pdfs", {}).items()
            if path in expected_pdfs
        }
    if not check:
        for index, (record, content) in enumerate(expected, start=1):
            record["html_path"].parent.mkdir(parents=True, exist_ok=True)
            record["html_path"].write_text(content, encoding="utf-8", newline="\n")
            if index % 250 == 0:
                print(f"HTML readers written: {index}/{len(expected)}", flush=True)
    rendered_pdfs = 0
    cached_pdfs = 0
    if check:
        for index, (record, content) in enumerate(expected, start=1):
            cached = pdf_cached(record, cache)
            validate_page(record, content, check_pdf=not cached)
            if not cached:
                cache["pdfs"].pop(record["pdf_path"].relative_to(ROOT).as_posix(), None)
            if index % 500 == 0:
                print(f"Readers checked: {index}/{len(expected)}", flush=True)
        print(f"Validated {len(records)} HTML readers and PDF files.", flush=True)
        return

    pdf_jobs = []
    for record, content in expected:
        validate_page(record, content, check_pdf=False)
        if pdf_cached(record, cache):
            cached_pdfs += 1
        else:
            pdf_jobs.append(record)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(render_one_pdf, record, reader_index): record for record in pdf_jobs}
        for completed, future in enumerate(as_completed(futures), start=1):
            record = futures[future]
            future.result()
            record_pdf_result(record, cache)
            rendered_pdfs += 1
            if completed % 25 == 0 or completed == len(futures):
                print(f"PDFs generated and verified: {completed}/{len(futures)}", flush=True)
    for record in records:
        relative_pdf = record["pdf_path"].relative_to(ROOT).as_posix()
        cached = cache["pdfs"].get(relative_pdf, {})
        if (not record["pdf_path"].is_file()
                or cached.get("body_sha256") != record["body_sha256"]
                or not cached.get("pdf_sha256")):
            raise ValueError(f"Generated PDF is absent or stale: {record['pdf_path'].relative_to(ROOT)}")
    write_cache(cache)
    print(f"Readers complete: {len(records)} pages; {rendered_pdfs} PDFs generated; {cached_pdfs} PDFs reused.", flush=True)


def inventory(records: list[dict]) -> None:
    counts: dict[tuple[str, str], int] = {}
    for record in records:
        key = (record["kind"], record["license"])
        counts[key] = counts.get(key, 0) + 1
    for (kind, license_name), count in sorted(counts.items()):
        print(f"{kind}\t{license_name}\t{count}")
    print(f"TOTAL\t{len(records)}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", help="One sutta collection path (for example digha-nikaya) or vinaya")
    parser.add_argument("--output-root", default=".", help="Output directory mirroring the site tree, under the repository")
    parser.add_argument("--jobs", type=int, default=2, help="Parallel PDF workers, from 1 to 8")
    parser.add_argument("--check", action="store_true", help="Verify generated pages and downloads without writing")
    parser.add_argument("--inventory", action="store_true", help="Count eligible records without generating files")
    parser.add_argument("--clean-output", action="store_true", help="Replace a marked build/ output root; requires a full build")
    parser.add_argument("--prune-output", action="store_true", help="Reuse valid outputs and remove stale generated readers under build/")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not 1 <= args.jobs <= 8:
        raise ValueError("--jobs must be from 1 to 8")
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = ROOT / output_root
    output_root = output_root.resolve()
    try:
        output_root.relative_to(ROOT.resolve())
    except ValueError as error:
        raise ValueError("--output-root must stay inside the repository") from error
    all_records = collect_records(output_root)
    selected = all_records
    if args.collection == "vinaya":
        selected = [record for record in all_records if record["kind"] == "vinaya"]
    elif args.collection:
        selected = [record for record in all_records if record["kind"] == "sutta" and record["collection"] == args.collection]
    if args.clean_output and args.prune_output:
        raise ValueError("--clean-output and --prune-output cannot be used together")
    if (args.clean_output or args.prune_output) and (args.collection or args.check or args.inventory):
        raise ValueError("--clean-output and --prune-output require a full generated build")
    if args.inventory:
        inventory(selected)
        return 0
    if not selected:
        raise ValueError(f"No eligible reader records found for {args.collection}")
    build(selected, all_records, args.jobs, args.check, args.clean_output, args.prune_output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.CalledProcessError,
            json.JSONDecodeError) as error:
        print(f"eligible reader build failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
