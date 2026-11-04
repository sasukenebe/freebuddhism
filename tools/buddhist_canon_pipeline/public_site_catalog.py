#!/usr/bin/env python3
"""Load the text-free navigation and edition metadata used by the public build."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
_CATALOG = json.loads((ROOT / "metadata/site-catalog.json").read_text(encoding="utf-8"))
ABHIDHAMMA_BOOKS = tuple(tuple(row) for row in _CATALOG["abhidhamma_books"])
COLLECTION_TITLES = _CATALOG["collection_titles"]
SUTTA_NODE_INFO = _CATALOG["sutta_node_info"]
WHOLE_BOOK_PDF_SOURCES = _CATALOG["whole_book_pdf_sources"]


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
