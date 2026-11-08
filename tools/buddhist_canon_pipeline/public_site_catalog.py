#!/usr/bin/env python3
"""Load the text-free navigation and edition metadata used by the public build."""

from __future__ import annotations

import json
import html
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
_CATALOG = json.loads((ROOT / "metadata/site-catalog.json").read_text(encoding="utf-8"))
ABHIDHAMMA_BOOKS = tuple(tuple(row) for row in _CATALOG["abhidhamma_books"])
COLLECTION_TITLES = _CATALOG["collection_titles"]
SUTTA_NODE_INFO = _CATALOG["sutta_node_info"]
WHOLE_BOOK_PDF_SOURCES = _CATALOG["whole_book_pdf_sources"]


def site_navigation() -> str:
    return (
        '<nav aria-label="Site"><a href="/">Home</a> · '
        '<a href="/theravada/tipitaka/site/dhamma.html">Dhamma</a> · '
        '<a href="/theravada/tipitaka/site/tipitaka.html">Buddhist Texts</a></nav>'
    )


def navigation_nodes(extra_collections=()) -> dict[str, dict]:
    """One collection hierarchy for browsing, breadcrumbs, and continuous reading."""
    nodes = {}

    def add(key, title, route, parent=None, label=None):
        nodes[key] = {"id": key, "title": title, "label": label or title,
                      "route": route, "parent": parent, "order": len(nodes)}

    add("tipitaka", "Buddhist Texts", "site/tipitaka.html", label="Tipiṭaka")
    add("vinaya", "Vinaya Piṭaka", "vinaya/index.html", "tipitaka")
    for key, title, parent in (
        ("sutta-vibhanga", "Sutta Vibhaṅga (Analysis of the Rules)", "vinaya"),
        ("bhikkhu-vibhanga", "Mahā Vibhaṅga (Monks’ Analysis)", "vinaya/sutta-vibhanga"),
        ("bhikkhuni-vibhanga", "Bhikkhunī Vibhaṅga (Nuns’ Analysis)", "vinaya/sutta-vibhanga"),
        ("khandhaka", "Khandhaka (Chapters)", "vinaya"),
        ("mahavagga", "Mahāvagga (Great Chapter)", "vinaya/khandhaka"),
        ("cullavagga", "Cullavagga (Lesser Chapter)", "vinaya/khandhaka"),
        ("parivara", "Parivāra (Vinaya Compendium)", "vinaya"),
    ):
        add("vinaya/" + key, title, "vinaya/" + key + "/index.html", parent)
    add("sutta", "Sutta Piṭaka", "site/sutta.html", "tipitaka")
    names = list(dict.fromkeys([*SUTTA_NODE_INFO, *COLLECTION_TITLES, *extra_collections]))
    for name in names:
        if name == "sutta":
            continue
        parts = name.split("/")
        for length in range(1, len(parts) + 1):
            key = "/".join(parts[:length])
            if key in nodes:
                continue
            title = SUTTA_NODE_INFO[key][0] if key in SUTTA_NODE_INFO else COLLECTION_TITLES.get(key, parts[length - 1].replace("-", " ").title())
            parent = "/".join(parts[:length - 1]) if length > 1 else "sutta"
            add(key, title, "sutta/" + key + "/index.html", parent)
    add("abhidhamma", "Abhidhamma Piṭaka", "abhidhamma/index.html", "tipitaka")
    for key, title, english, _description in ABHIDHAMMA_BOOKS:
        add("abhidhamma/" + key, title + " (" + english + ")", "abhidhamma/" + key + "/index.html", "abhidhamma")
    descriptions = {
        "tipitaka": "The Theravāda Buddhist texts, arranged in three baskets.",
        "vinaya": "Rules and procedures for Buddhist monks and nuns.",
        "vinaya/sutta-vibhanga": "Explanations of the monks’ and nuns’ training rules.",
        "vinaya/bhikkhu-vibhanga": "The monks’ training rules and their explanations.",
        "vinaya/bhikkhuni-vibhanga": "The nuns’ training rules and their explanations.",
        "vinaya/khandhaka": "Chapters on ordination, communal life and monastic procedures.",
        "vinaya/mahavagga": "The first division of the Khandhaka.",
        "vinaya/cullavagga": "The second division of the Khandhaka.",
        "vinaya/parivara": "A review and classification of the monastic discipline.",
        "abhidhamma": "Systematic analyses of phenomena and their relationships.",
    }
    descriptions.update({key: english + ". " + description
                         for key, (_title, english, description) in SUTTA_NODE_INFO.items()})
    descriptions.update({"abhidhamma/" + key: english + ". " + description
                         for key, _title, english, description in ABHIDHAMMA_BOOKS})
    for key, node in nodes.items():
        node["tree_title"] = node["title"].split(" (", 1)[0]
        node["description"] = descriptions.get(key, "")
    return nodes


def collection_path(collection: str, nodes: dict[str, dict]) -> list[dict]:
    path = []
    while collection:
        node = nodes[collection]
        path.append(node)
        collection = node["parent"]
    return list(reversed(path))


def collection_breadcrumbs(collection: str, nodes: dict[str, dict]) -> list[dict]:
    return [{"label": "Home", "href": "/"}] + [
        {"label": node["label"], "href": "/theravada/tipitaka/" + node["route"]}
        for node in collection_path(collection, nodes)
    ]


def breadcrumb_markup(items: list[dict]) -> str:
    parts = [
        f'<a href="{html.escape(item["href"], quote=True)}">{html.escape(item["label"])}</a>'
        if index < len(items) - 1 else f'<span aria-current="page">{html.escape(item["label"])}</span>'
        for index, item in enumerate(items)
    ]
    return '<nav aria-label="Breadcrumb">' + " → ".join(parts) + '</nav>'


def canonical_slug(canonical_id: str) -> str:
    match = re.fullmatch(r"([A-Za-z]+)\s+(.+)", canonical_id.strip())
    if not match:
        return slug(canonical_id)
    prefix = match.group(1).lower()
    value = match.group(2).lower()
    if re.fullmatch(r"\d+", value):
        return f"{prefix}{int(value):02d}"
    if re.fullmatch(r"\d+\.\d+", value):
        book, number = value.split(".")
        return f"{prefix}{int(book):02d}-{int(number):02d}"
    if re.fullmatch(r"\d+\.\d+-\d+", value):
        book, rest = value.split(".")
        start, end = rest.split("-")
        return f"{prefix}{int(book):02d}-{int(start):02d}-{int(end):02d}"
    if value == "complete":
        return f"{prefix}-complete"
    return slug(canonical_id)


def slug(value: str) -> str:
    value = value.strip().lower().replace(".", "-")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def natural_key(value: str) -> list[int | str]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def whole_book_pdfs(source: dict) -> list[dict[str, str]]:
    if source.get("pdfs"):
        return source["pdfs"]
    return [{
        "path": source["pdf_path"],
        "label": "Complete scanned book (PDF)",
        "source_url": source.get("source_url", ""),
    }]
