# SPDX-License-Identifier: 0BSD
"""Prepare cached individual Vv/Pv articles offline; never import or publish them.

Every protected-region text node is compared independently. Permission for a
collection download is not inferred from the individual-sutta sharing statement.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from html import escape, unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
COUNTS = {"vv": (17, 11, 10, 12, 14, 10, 11), "pv": (12, 13, 10, 16)}
MANIFEST = Path("metadata/source-manifests/suttafriends-stories.json")
MANIFEST_SHA256 = "41f42d2a4b6a21c8e880d302fc7a3444cb7f59bd2ca094f9eb2df460df8fb2fb"
SNAPSHOTS = Path("metadata/source-snapshots/suttafriends-stories")
OUT = ROOT / "build/suttafriends-gap-batch-20261112"
REGION = re.compile(r'<div\s+class="entry-content"\s*>(.*?)</div>\s*<!--\s*\.entry-content\s*-->', re.S)
BLOCKS = {"p", "div", "fieldset", "legend", "ul", "ol", "li"}
INLINE = {"a", "span", "i", "b", "em", "strong", "sup", "sub"}


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def checked(root: Path, relative: str, expected_hash: str) -> bytes:
    path = Path(relative)
    target = root / path
    if (path.is_absolute() or ".." in path.parts or target.is_symlink()
            or not target.resolve().is_relative_to(root.resolve())):
        raise ValueError("Unsafe cached source path")
    raw = target.read_bytes()
    if digest(raw) != expected_hash:
        raise ValueError("Cached source hash changed: " + relative)
    return raw


class Body(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.stack = []
        self.tags = Counter()

    def handle_starttag(self, tag, attrs):
        if tag not in BLOCKS | INLINE | {"br"}:
            raise ValueError("Unreviewed article element: " + tag)
        values = dict(attrs)
        if "hidden" in values or values.get("aria-hidden") == "true":
            raise ValueError("Hidden article text requires separate review")
        self.tags[tag] += 1
        if tag == "br": self.parts.append("\n")
        else:
            if tag in BLOCKS: self.parts.append("\n\n")
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag != "br": raise ValueError("Unexpected self-closing article element")
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "br": return
        if not self.stack or self.stack.pop() != tag:
            raise ValueError("Unbalanced article markup")
        if tag in BLOCKS: self.parts.append("\n\n")

    def handle_data(self, data):
        self.parts.append(re.sub(r"\s+", " ", data))


def article(raw: bytes) -> tuple[str, dict]:
    source = raw.decode("utf-8", errors="strict")
    regions = REGION.findall(source)
    if len(regions) != 1:
        raise ValueError("Expected exactly one complete article region")
    parser = Body()
    parser.feed(regions[0])
    parser.close()
    if parser.stack:
        raise ValueError("Unclosed article markup")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in "".join(parser.parts).splitlines()]
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"
    # Independent flat HTML lexer: every text character from the whole region,
    # not the same paragraph parser or a comparison against its own output.
    text_nodes = re.sub(r"<!--[\s\S]*?-->", "", regions[0])
    text_nodes = unescape(re.sub(r"<[^>]*>", "", text_nodes))
    if re.sub(r"\s+", "", text_nodes) != re.sub(r"\s+", "", body):
        raise ValueError("Whole-article ordered-character comparison failed")
    if len(body.strip()) < 80:
        raise ValueError("Unexpectedly short article body")
    return body, {"element_counts": dict(parser.tags), "paragraphs": parser.tags["p"],
                  "line_breaks": parser.tags["br"], "ordered_character_comparison": "PASS",
                  "scope": "Complete protected article region, including Pali, notes and list text where present"}


def source_metadata(manifest: dict) -> dict:
    expected = {f"{prefix.capitalize()} {number}" for prefix, counts in COUNTS.items()
                for number in range(1, sum(counts) + 1)}
    if set(manifest["texts"]) != expected:
        raise ValueError("Cached batch is not exactly the 85 Vv and 51 Pv individual articles")
    rows = []
    for prefix, counts in COUNTS.items():
        number = 0
        for chapter, count in enumerate(counts, 1):
            for item in range(1, count + 1):
                number += 1
                key = f"{prefix.capitalize()} {number}"
                row = manifest["texts"][key]
                publisher = f"{prefix.capitalize()} {chapter}.{item}"
                url = f"https://suttafriends.org/sutta/{prefix}{chapter}-{item}/"
                if (row["canonical_id"] != key or row["source_id"] != publisher or row["source_url"] != url
                        or row["chapter"] != chapter or row["chapter_item"] != item
                        or publisher not in row["page_heading"]):
                    raise ValueError("Cached source numbering/header disagrees: " + key)
                rows.append({**row, "prefix": prefix, "number": number})
    return {"rows": rows}


def prepare(source_root: Path, output: Path) -> dict:
    manifest_raw = checked(source_root, MANIFEST.as_posix(), MANIFEST_SHA256)
    manifest = json.loads(manifest_raw)
    originals = source_root / SNAPSHOTS
    metadata = source_metadata(manifest)
    copyright_raw = checked(originals, "rights/copyright.html.source", manifest["shared_sources"]["rights/copyright.html.source"])
    if (b"share individual suttas however you like" not in copyright_raw
            or "translations on this site are © Mahamevnawa Buddhist Monastery" not in copyright_raw.decode()):
        raise ValueError("Individual-sharing grant is absent from the pinned publisher statement")
    if output.exists():
        raise ValueError("Refusing to overwrite an existing preparation directory")
    output.mkdir(parents=True)
    prepared = []
    for row in metadata["rows"]:
        key = row["canonical_id"]
        stem = row["source_url"].rstrip("/").split("/")[-1]
        source_name = row["prefix"] + "/" + stem + "-page.html.source"
        page = checked(originals, source_name, row["page_sha256"])
        headings = re.findall(r'<h1\b[^>]*>(.*?)</h1>', page.decode(), re.S)
        heading = " ".join(unescape(re.sub(r'<[^>]*>', '', value)) for value in headings)
        if row["source_id"] not in heading:
            raise ValueError("Actual source heading disagrees with publisher ID: " + key)
        pali_name = f'pali/{row["prefix"]}{row["number"]}_root-pli-ms.json.source'
        pali = checked(originals, pali_name, row["pali_sha256"])
        pali_text = json.loads(pali)
        title_key = f'{row["prefix"]}{row["number"]}:0.' + ("4" if row["prefix"] == "vv" else "3")
        if pali_text.get(title_key, "").strip() != row["pali_title"]:
            raise ValueError("Pinned Pali reference changed: " + key)
        body, comparison = article(page)
        target = output / (stem + ".txt")
        target.write_text(body, encoding="utf-8")
        prepared.append({"id": key, "publisher_id": row["source_id"], "source_url": row["source_url"],
                         "source_sha256": row["page_sha256"], "pali_sha256": row["pali_sha256"],
                         "title": row["title"], "body_file": target.name, "body_sha256": digest(body.encode()),
                         "body_comparison": comparison,
                         "publication_status": "NOT_IMPORTED_PERMISSION_SCOPE_REVIEW",
                         "rights_evidence": "https://suttafriends.org/copyright/",
                         "limits": "Individual article sharing is stated; collection-wide ZIP or combined-book permission is not established. Translation accuracy and whole-book completeness are not certified."})
    report = {"schema_version": 1, "status": "PREPARED_NOT_IMPORTED", "network_requests": 0,
              "manifest_sha256": digest(manifest_raw), "permission_source_sha256": digest(copyright_raw),
              "prepared_units": prepared,
              "counts": dict(Counter(r["id"].split()[0] for r in prepared)),
              "scope": "Offline article preparation only. This is not an import proposal or permission to publish a combined collection."}
    (output / "report.json").write_bytes(json_bytes(report))
    links = ''.join('<li>' + escape(row["id"]) + ' · <a href="' + escape(row["source_url"], quote=True)
                    + '">Original article</a> · <a href="' + row["body_file"] + '">Prepared text</a></li>' for row in prepared)
    (output / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Individual source preparation</title>'
                                      '<h1>Prepared individual articles — not imported</h1><p>Collection permission and full human review remain separate.</p><ol>' + links + '</ol>', encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="Existing source tree with the cached manifest and snapshots; read-only")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    report = prepare(args.source_root.resolve(), args.output.resolve())
    print(json.dumps({key: value for key, value in report.items() if key != "prepared_units"}, indent=2))


if __name__ == "__main__": main()
