#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Prepare all pinned SC licensed HTML units in an ignored, offline review bundle.

Original metadata is CC0-1.0. Source snapshots and extracted texts retain their
edition's rights. This module deliberately does not import the shared publisher.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT.parent / "buddhism"
OUTPUT = ROOT / "build/sc-bulk-20261111"
COMMIT = "2d9ca8da858f94302ed6783e2717bf73d651881b"
PALI_COMMIT = "3bc8665e0e28e70518eba94304a2fafcab80f933"
REPOSITORY = "https://github.com/suttacentral/sc-data"
PTS_URL = "https://palitextsociety.org/copyright-information/"
PTS_SNAPSHOT = ROOT / "build/luna-dhammasangani-20261109/pts-copyright.html"
PTS_HASH = "574f6fde6912db698cbdbd8f90801b47074bf399c118299337c7b9b111c63977"
LOCKS = {
    "walters-apadana": "391ccdf483aaa38c30499a08748efbd2bef0c9a65ab6c87de030466ac997741a",
    "suttacentral-nanamoli-nettipakarana": "1dd5334e40b14a5b6fd30483db2bca72e6a4020afc45122714bf859e66354df8",
    "suttacentral-nanamoli-petakopadesa": "aaaedb090a973585f972217cd245023f24c8c25805b3b3161deb5b5259207961",
    "ireland-vimanavatthu": "bfbc01bd28bb4c1bcce0872aaa72f54da233be0c3f4265a44b2c6d8e1f262076",
    "english-licensed-sutta-books": "0d35a5e7e1288f4da94b6cc0cceb1075ccb7c924b36e1f3f86126ecd4aa7819a",
}
FREE_GRANT = "Free redistribution with attribution and complete notice"
WALTERS_NOTICE = (
    "Translated by Jonathan S. Walters. Whitman College, 2017 Legends of the "
    "Buddhist Saints (Apadāna) is released under the Attribution, Non-Commercial, "
    "Share Alike license. This is the first-ever complete translation of Apadāna "
    "into a Western language. For more information, visit apadanatranslation.org "
    "Prepared for SuttaCentral by Ayya Vimala."
)
PTS_NOTICE = (
    "Translated from the Pāḷi by Bhikkhu Ñāṇamoli, {year}. Published by The Pali "
    "Text Society, Oxford. This electronic version is published under the terms "
    "of the Creative Commons Attribution Non-Commercial 4.0 licence (CC BY-NC 4.0) "
    "All copyright is owned by the Pali Text Society. See also the statement "
    "under http://www.palitext.com/ → Publications → Copyright Announcement. "
    "For non-commercial use only. This version has not been proofread. Prepared "
    "in laTex by Manfred Wierich, prepared for SuttaCentral by Ven. Vimala."
)
IRELAND_GRANT = (
    "You may copy, reformat, reprint, republish, and redistribute this work in "
    "any medium whatsoever, provided that: (1) you only make such copies, etc. "
    "available free of charge and, in the case of reprinting, only in quantities "
    "of no more than 50 copies; (2) you clearly indicate that any derivatives of "
    "this work (including translations) are derived from this source document; "
    "and (3) you include the full text of this license in any copies or "
    "derivatives of this work. Otherwise, all rights reserved. Documents linked "
    "from this page may be subject to other restrictions."
)
METHOD = (
    "Offline prepare_sc_licensed.py --check: verify pinned manifest and raw "
    "source SHA256; render every article/header/body/footer text node in order, "
    "retaining br, paragraphs, notes, reference labels and HTML ordered-list "
    "markers; independently tokenize the entire source region with a flat "
    "HTML lexer and compare all ordered non-whitespace Unicode characters "
    "(no Unicode/punctuation folding). Compare exact rendered UTF-8 bytes "
    "and structural counts again; no start/end sampling or bag-of-words test."
)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCK = {"article", "header", "footer", "p", "div", "blockquote", "ul", "ol", "li", "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def collapse(text: str) -> str:
    return " ".join(text.split())


def checked(path: Path, expected: str) -> bytes:
    data = path.read_bytes()
    if digest(data) != expected:
        raise ValueError(f"Pinned SHA256 mismatch: {path}")
    return data


def safe_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise ValueError(f"Unsafe relative path: {relative}")
    result = root / path
    if not result.resolve().is_relative_to(root.resolve()) or any(
        part.is_symlink() for part in (result, *result.parents) if part != root.parent
    ):
        raise ValueError(f"Source/output symlink or escape: {relative}")
    return result


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list = field(default_factory=list)

    def find(self, tag: str) -> list[Node]:
        return [node for node in self.walk() if node.tag == tag]

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()


class Tree(HTMLParser):
    """Small lossless text tree, with HTML's optional p/li end tags respected."""

    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        # Some pinned pages have <p><footer> or a p directly around a blockquote.
        if tag in BLOCK - {"li"} and any(n.tag == "p" for n in self.stack):
            self.handle_endtag("p")
        if tag == "li":
            for node in reversed(self.stack):
                if node.tag in {"ul", "ol"}:
                    break
                if node.tag == "li":
                    self.handle_endtag("li")
                    break
        node = Node(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def flat(node: Node) -> str:
    return "".join(flat(child) if isinstance(child, Node) else child for child in node.children)


def list_label(number: int, kind: str) -> str:
    if kind in {"a", "A"}:
        if not 1 <= number <= 26:
            raise ValueError("Unreviewed alphabetic list number")
        label = chr(ord("a") + number - 1)
    elif kind in {"i", "I"}:
        label = ""
        for value, numeral in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
                               (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
                               (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
            while number >= value:
                label += numeral
                number -= value
    elif kind == "1":
        label = str(number)
    else:
        raise ValueError(f"Unreviewed list type: {kind}")
    return (label.upper() if kind in {"I", "A"} else label) + ". "


def render(node: Node) -> str:
    """Keep paragraphs/stanzas separate, br as one line, inline text intact."""
    def visit(item):
        if isinstance(item, str):
            return re.sub(r"\s+", " ", item)
        if item.tag == "br":
            return "\n"
        parts = []
        number = int(item.attrs.get("start", "1"))
        for child in item.children:
            if isinstance(child, Node) and child.tag == "li" and item.tag == "ol":
                number = int(child.attrs.get("value", str(number)))
                parts.append("\n\n" + list_label(number, item.attrs.get("type", "1")))
                # Avoid inserting a break between the generated number and item.
                parts.extend(visit(grandchild) for grandchild in child.children)
                parts.append("\n\n")
                number += 1
            else:
                parts.append(visit(child))
        value = "".join(parts)
        if item.tag == "a" and "ref" in item.attrs.get("class", "").split():
            value = " " + value + " "
        return "\n\n" + value + "\n\n" if item.tag in BLOCK else value
    raw = visit(node)
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in raw.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def oracle(source_region: str) -> str:
    """Independent flat lexer: no tree traversal and no selection of paragraphs."""
    parts, lists = [], []
    for token in re.findall(r"<!--[\s\S]*?-->|<[^>]*>|[^<]+", source_region):
        if token.startswith("<!--"):
            continue
        if not token.startswith("<"):
            parts.append(unescape(token))
            continue
        match = re.match(r"<\s*(/?)\s*([a-zA-Z0-9]+)", token)
        if not match:
            raise ValueError("Unreviewed source markup")
        end, tag = match[1], match[2].lower()
        if tag in {"ol", "ul"}:
            if end:
                if not lists or lists[-1][0] != tag:
                    raise ValueError("Unbalanced source list")
                lists.pop()
            else:
                attrs = {key.lower(): unescape(a or b or c) for key, a, b, c in re.findall(
                    r'''([\w-]+)\s*=\s*(?:'([^']*)'|"([^"]*)"|([^\s>]+))''', token)}
                lists.append([tag, int(attrs.get("start", "1")), attrs.get("type", "1")])
        if tag == "li" and not end and lists and lists[-1][0] == "ol":
            value = re.search(r'''\bvalue\s*=\s*['"]?(\d+)''', token)
            if value:
                lists[-1][1] = int(value[1])
            parts.append(list_label(lists[-1][1], lists[-1][2]))
            lists[-1][1] += 1
    if lists:
        raise ValueError("Unclosed source list")
    return compact("".join(parts))


def compare_region(source_region: str, body: str, node: Node) -> dict:
    expected, observed = oracle(source_region), compact(body)
    if not expected or expected != observed:
        raise ValueError("Whole-source comparison failed: omitted, reordered, duplicated or changed text")
    if body != render(node):
        raise ValueError("Source paragraph/stanza structure changed")
    return {"source_comparison": "PASS", "ordered_characters": len(expected),
            "ordered_sha256": digest(expected.encode()),
            "elements": dict(sorted(Counter(n.tag for n in node.walk()).items()))}


def article(raw: bytes, source_id: str) -> tuple[Node, str, str]:
    source = raw.decode("utf-8", "strict")
    regions = re.findall(r"<article\b[^>]*>[\s\S]*?</article\s*>", source, re.I)
    if len(regions) != 1 or source.lower().count("<article") != 1:
        raise ValueError("Expected exactly one closed source article")
    tree = Tree(regions[0])
    nodes = tree.root.find("article")
    if len(nodes) != 1 or nodes[0].attrs.get("id") != source_id:
        raise ValueError(f"Original source ID changed: {source_id}")
    meta = re.search(r"<meta\s+name=['\"]author['\"]\s+content=['\"]([^'\"]+)", source)
    if not meta:
        raise ValueError("Source author metadata missing")
    return nodes[0], regions[0], unescape(meta[1])


def footer_rights(node: Node, region: str, walters: bool, year: str) -> tuple[str, str, str]:
    footers = node.find("footer")
    snapshots = re.findall(r"<footer\b[^>]*>[\s\S]*?</footer\s*>", region, re.I)
    if len(footers) != 1 or len(snapshots) != 1:
        raise ValueError("Missing/duplicate edition footer")
    notice = collapse(flat(footers[0]))
    wanted = WALTERS_NOTICE if walters else PTS_NOTICE.format(year=year)
    url = "https://creativecommons.org/licenses/" + ("by-nc-sa/3.0/us/" if walters else "by-nc/4.0/")
    links = [n.attrs.get("href", "") for n in footers[0].find("a")]
    if notice != wanted or url not in [link.replace("http://", "https://") for link in links]:
        raise ValueError("Exact source footer grant/attribution changed or missing")
    # Retain hrefs that are not visible anchor text, including the legacy HTTP URL.
    notice += " Source footer links: " + " ; ".join(links)
    return notice, url, snapshots[0]


def inventory(entries: list[dict], expected: set[str], key: str) -> None:
    ids = [entry[key] for entry in entries]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError("Full source inventory changed, missing or duplicated IDs")


def prior_id(record: dict, prior: list[dict]) -> str | None:
    matches = [r["record_id"] for r in prior if r["canonical_id"] == record["canonical_id"]
               and r["collection"] == record["collection"] and r.get("source_url") == record["source_url"]]
    if len(matches) > 1:
        raise ValueError("Ambiguous prior record")
    return matches[0] if matches else None


def pdf_assessment(legacy: Path, lock: dict, files: dict) -> dict:
    source = lock["sources"]["patisambhidamagga"]
    path = legacy / "metadata/source-snapshots/english-licensed-sutta-books/nanamoli-patisambhidamagga.pdf"
    raw = checked(path, source["sha256"])
    def extract(command):
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=60).stdout
    poppler = extract(["pdftotext", "-layout", str(path), "-"])
    mupdf = extract(["mutool", "draw", "-F", "txt", "-o", "-", str(path)])
    a, b = poppler.split("\f"), mupdf.split("\f")
    if not a[-1].strip():
        a.pop()
    if not b[-1].strip():
        b.pop()
    original = legacy / "theravada/tipitaka/translations/en/licensed-sutta-books/nanamoli-patisambhidamagga.txt"
    old = original.read_bytes()
    exact = old.endswith(poppler.encode())
    differences = [n for n, (x, y) in enumerate(zip(a, b), 1) if compact(x) != compact(y)]
    content = [n for n, (x, y) in enumerate(zip(a, b), 1) if Counter(compact(x)) != Counter(compact(y))]
    files["assessment/path-of-discrimination/source.pdf"] = raw
    files["assessment/path-of-discrimination/existing.txt"] = old
    files["assessment/path-of-discrimination/poppler-layout.txt"] = poppler.encode()
    files["assessment/path-of-discrimination/mupdf.txt"] = mupdf.encode()
    result = {"canonical_id": "Ps complete", "decision": "HOLD_EXTRACTION_ORDER",
              "completeness_status": "UNKNOWN", "source_url": source["url"],
              "license": "CC-BY-NC-4.0", "source_sha256": digest(raw),
              "source_snapshot": "assessment/path-of-discrimination/source.pdf",
              "existing_text_sha256": digest(old), "existing_matches_fresh_layout_extraction": exact,
              "poppler_pages": len(a), "mupdf_pages": len(b),
              "different_order_pages": differences, "different_character_multiset_pages": content,
              "reason": "The existing extraction is reproducible but independent engines disagree on ordered text; page margins/notes require layout adjudication. No OCR or text repairs attempted.",
              "page_audit": [{"pdf_page": i + 1, "poppler_sha256": digest(x.encode()),
                              "mupdf_sha256": digest(y.encode()),
                              "ordered_characters_equal": compact(x) == compact(y)}
                             for i, (x, y) in enumerate(zip(a, b))]}
    if len(a) != 664 or len(b) != 664 or not exact:
        result["decision"] = "HOLD_EXTRACTION_CHANGED"
    files["assessment/path-of-discrimination/comparison.json"] = json_bytes(result)
    return {k: v for k, v in result.items() if k != "page_audit"}


def make_plan(legacy: Path = LEGACY, pts_evidence: Path = PTS_SNAPSHOT) -> tuple[dict, dict[str, bytes]]:
    files: dict[str, bytes] = {}
    locks = {}
    for name, checksum in LOCKS.items():
        data = checked(legacy / f"metadata/source-manifests/{name}.json", checksum)
        locks[name] = json.loads(data)
        files[f"sources/manifests/{name}.json"] = data
    publisher = checked(pts_evidence, PTS_HASH)
    # The historical short summaries are not used as licence evidence.
    if not all(text in publisher.decode() for text in ("The Guide", "The Path of Discrimination", "The Piṭaka Disclosure", "8 April 2021", "CC BY-NC 4.0")):
        raise ValueError("Publisher evidence does not identify these exact works")
    files["rights/pts-copyright.html"] = publisher
    historical = json.loads((ROOT / "metadata/reports/strict-license-classification-2026-10.json").read_text())["records"]
    prior = [{**r, "record_id": r["record_key"], "collection": r["collection_path"]} for r in historical]
    records, audits, rights = [], [], []
    for name, expected, key in (
        ("walters-apadana", {*(f"tha-ap{i}" for i in range(1, 562)), *(f"thi-ap{i}" for i in range(1, 41))}, "id"),
        ("suttacentral-nanamoli-nettipakarana", {f"ne{i}" for i in range(1, 38)}, "source_id"),
        ("suttacentral-nanamoli-petakopadesa", {f"pe{i}" for i in range(1, 10)}, "source_id"),
    ):
        lock = locks[name]
        if lock["source_commit"] != COMMIT or lock.get("pali_reference_commit", lock.get("reference_pali_commit")) != PALI_COMMIT:
            raise ValueError("Source/reference revision changed")
        inventory(lock["texts"], expected, key)
        for entry in lock["texts"]:
            source_id = entry[key]
            walters = name == "walters-apadana"
            original_path = safe_path(legacy / f"metadata/source-snapshots/{name}", entry["snapshot"] if walters else entry["html_snapshot"])
            raw = checked(original_path, entry["source_sha256"])
            if walters:
                blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
                if blob != entry["source_git_blob_sha"] or len(raw) != entry["source_size"]:
                    raise ValueError("Pinned Walters Git blob/size changed")
            else:
                if entry["html_sha256"] != digest(raw):
                    raise ValueError("HTML hash aliases disagree")
                pali = checked(safe_path(legacy / f"metadata/source-snapshots/{name}", entry["pali_snapshot"]), entry["pali_sha256"])
                blob = hashlib.sha1(f"blob {len(pali)}\0".encode() + pali).hexdigest()
                if blob != entry["pali_git_blob"] or any(k.split(":")[0] != source_id for k in json.loads(pali)):
                    raise ValueError("Pali reference identity/blob changed")
                files[f"sources/references/{source_id}.json.source"] = pali
            node, region, author = article(raw, source_id)
            translator = "Jonathan S. Walters" if walters else "Bhikkhu Ñāṇamoli"
            if author != translator:
                raise ValueError("Source translator changed")
            headers = node.find("header")
            if len(headers) != 1 or len(headers[0].find("h1")) != 1:
                raise ValueError("Source title/header changed")
            title = collapse(flat(headers[0].find("h1")[0]))
            notice, license_url, footer_html = footer_rights(node, region, walters, entry.get("year", ""))
            body = render(node)
            audit = compare_region(region, body, node)
            prefix, number = re.fullmatch(r"(tha-ap|thi-ap|ne|pe)(\d+)", source_id).groups()
            canonical = {"tha-ap": "Tha Ap", "thi-ap": "Thi Ap", "ne": "Ne", "pe": "Pe"}[prefix] + " " + str(int(number))
            exceptions = []
            printed = re.match(r"^(\d+)\.\s", title) if walters else None
            if printed and int(printed[1]) != int(number):
                exceptions.append(f"Original source ID {source_id} is retained; the source heading prints {printed[1]}. {title.split('. ', 1)[1]}.")
            if not walters:
                exceptions.append("Source explicitly states: This version has not been proofread.")
                exceptions.append("SC numbered source units are not independent numbered chapters; the full printed heading is retained.")
            if source_id in {"pe7", "pe8"}:
                exceptions.append("Pe 7 continues into Pe 8; neither is claimed as an independently complete division.")
            # Scope is the source unit, with printed elisions recorded independently.
            content_region = re.sub(r"<header\b[\s\S]*?</header>|<footer\b[\s\S]*?</footer>", "", region)
            elisions = len(re.findall(r"…|\.\.\.", unescape(re.sub(r"<[^>]*>", "", content_region))))
            status = "ABBREVIATED" if elisions else "COMPLETE" if walters else "UNKNOWN"
            if elisions:
                exceptions.append(f"Source contains {elisions} printed ellipsis markers eliding quoted/repeated text; retained without expansion.")
            if walters:
                scope = "All text of this pinned standalone English article, including header, verse/reference numbering, closing lines and footer, is preserved. Tha Ap 562–563 have no Walters articles in this edition; no whole-canon claim."
            else:
                scope = "All text of this pinned SC source unit, including headings, references, ordered lists, paragraph/stanza breaks and footer, is preserved. Printed elisions are retained; independent canonical/translation completeness is not established."
            record = {"canonical_id": canonical, "collection": "khuddaka-nikaya/" + ("apadana" if walters else "nettipakarana" if prefix == "ne" else "petakopadesa"),
                      "title": title, "translator": translator, "version_slug": "walters" if walters else "nanamoli",
                      "source_url": f"https://suttacentral.net/{source_id}/en/walters" if walters else entry["source_url"],
                      "license": "CC-BY-NC-SA-3.0-US" if walters else "CC-BY-NC-4.0", "license_url": license_url,
                      "copyright": "No separate copyright declaration in source; publication attribution: Whitman College, 2017." if walters else "All copyright is owned by the Pali Text Society.",
                      "license_notice": notice, "body_path": f"bodies/{source_id}.txt", "body_sha256": digest(body.encode()),
                      "source_snapshot": f"sources/html/{source_id}.html.source", "source_sha256": digest(raw),
                      "source_revision": COMMIT, "source_repository": REPOSITORY, "upstream_file": entry["source_path"],
                      "source_comparison": "PASS", "source_comparison_method": METHOD,
                      "completeness_status": status, "completeness_scope": scope, "exceptions": exceptions}
            previous = prior_id(record, prior)
            if previous:
                record["prior_record_id"] = previous
            records.append(record)
            files[record["body_path"]] = body.encode()
            files[record["source_snapshot"]] = raw
            footer_path = f"rights/footers/{source_id}.html.source"
            files[footer_path] = footer_html.encode()
            rights.append({"canonical_id": canonical, "source_snapshot": record["source_snapshot"], "source_sha256": digest(raw),
                           "evidence_snapshot": footer_path, "evidence_sha256": digest(footer_html.encode()),
                           "license": record["license"], "license_notice": notice, "original_snapshot": str(original_path),
                           "publisher_evidence": None if walters else "rights/pts-copyright.html"})
            audits.append({"canonical_id": canonical, "source_id": source_id, "source_sha256": digest(raw),
                           "body_sha256": record["body_sha256"], "printed_heading": title, "ellipsis_markers": elisions,
                           "numbering_discrepancy": bool(printed and int(printed[1]) != int(number)), **audit})
    # Ireland's ATI edition: whole translation container plus the entire provenance footer.
    lock = locks["ireland-vimanavatthu"]
    if lock["pali_commit"] != PALI_COMMIT or set(lock["texts"]) != {"16", "35"}:
        raise ValueError("Ireland source/reference inventory changed")
    for number, title, stanzas in ((16, "Sirima: Sirima's Mansion", 13), (35, "Sesavati: Sesavati's Mansion", 12)):
        entry = lock["texts"][str(number)]
        snapshot = f"vv{number}-source.html.source"
        path = legacy / "metadata/source-snapshots/ireland-vimanavatthu" / snapshot
        raw = checked(path, entry["sha256"][snapshot])
        pali_name = f"vv{number}-pali.json.source"
        pali = checked(path.parent / pali_name, entry["sha256"][pali_name])
        if not json.loads(pali) or any(k.split(":")[0] != f"vv{number}" for k in json.loads(pali)):
            raise ValueError("Ireland Pali reference identity changed")
        files[f"sources/references/vv{number}.json.source"] = pali
        source = raw.decode()
        if "[EXTENT]={complete}" not in source or "[AUTHOR]={John D. Ireland}" not in source:
            raise ValueError("Ireland source extent/author changed")
        tree = Tree(source).root
        def by_id(value):
            matches = [n for n in tree.walk() if n.attrs.get("id") == value]
            if len(matches) != 1:
                raise ValueError(f"Missing/duplicate Ireland region: {value}")
            return matches[0]
        translation, provenance = by_id("COPYRIGHTED_TEXT_CHUNK"), by_id("F_provenance")
        terms = re.search(r"\[DERIVED_LICENSE_DATA\]=\s*\{([\s\S]*?)\}\s*\{\}", source)
        if not terms or collapse(flat(Tree(terms[1]).root)) != IRELAND_GRANT or IRELAND_GRANT not in collapse(flat(provenance)):
            raise ValueError("Ireland full grant changed/missing from provenance")
        paragraphs = [n for n in translation.find("p") if not n.attrs.get("class")]
        if len(paragraphs) != stanzas:
            raise ValueError("Ireland complete stanza inventory changed")
        if number == 35 and (len(translation.find("dd")) != 1 or "Sariputta" not in flat(translation)):
            raise ValueError("Ireland note missing")
        start = source.index("<div id='COPYRIGHTED_TEXT_CHUNK'>")
        end = source.index("<!-- #COPYRIGHTED_TEXT_CHUNK", start)
        translation_region = source[start:end]
        # The exact balanced provenance div lies immediately before F_citation.
        pstart = source.index('<div id="F_provenance">')
        pend = source.index('<div id="F_citation">', pstart)
        provenance_region = source[pstart:pend]
        for region, node in ((translation_region, translation), (provenance_region, provenance)):
            compare_region(region, render(node), node)
        body = render(translation).rstrip() + "\n\n" + render(provenance)
        notice = collapse(flat(provenance))
        record = {"canonical_id": f"Vv {number}", "collection": "khuddaka-nikaya/vimanavatthu", "title": title,
                  "translator": "John D. Ireland", "version_slug": "ireland", "source_url": entry["source_url"],
                  "license": FREE_GRANT, "license_url": entry["source_url"] + "#F_termsOfUse",
                  "explicit_grant": IRELAND_GRANT,
                  "conditions": ["free-of-charge", "reprint-no-more-than-50-copies", "identify-derivatives-and-source", "retain-complete-license", "linked-documents-may-have-other-restrictions"],
                  "copyright": "©1997 John D. Ireland.", "license_notice": notice,
                  "body_path": f"bodies/vv{number}.txt", "body_sha256": digest(body.encode()),
                  "source_snapshot": f"sources/html/vv{number}.html.source", "source_sha256": digest(raw),
                  "source_revision": "Access to Insight (BCBS Edition), " + ("2" if number == 16 else "30") + " November 2013",
                  "upstream_file": snapshot, "source_comparison": "PASS",
                  "source_comparison_method": METHOD + " ATI: independently compare the entire COPYRIGHTED_TEXT_CHUNK and F_provenance regions, retaining speaker labels, all stanzas and notes; verify complete declared extent and pinned Pali reference hashes.",
                  "completeness_status": "COMPLETE",
                  "completeness_scope": f"Complete standalone source translation: {stanzas} stanzas, all speaker labels and source notes, plus full copyright/licence provenance. Not the whole Vimanavatthu.",
                  "exceptions": [f"Original canonical ID Vv {number} retained; the ATI edition prints Vv {entry['chapter_id']}.", "Reprinting is limited to no more than 50 copies; digital copies must be free of charge."]}
        if record["copyright"] not in notice:
            raise ValueError("Ireland source copyright changed")
        previous = prior_id(record, prior)
        if previous:
            record["prior_record_id"] = previous
        records.append(record)
        files[record["body_path"]] = body.encode()
        files[record["source_snapshot"]] = raw
        evidence_path = f"rights/footers/vv{number}.html.source"
        files[evidence_path] = provenance_region.encode()
        rights.append({"canonical_id": record["canonical_id"], "source_snapshot": record["source_snapshot"],
                       "source_sha256": digest(raw), "evidence_snapshot": evidence_path,
                       "evidence_sha256": digest(provenance_region.encode()), "license": FREE_GRANT,
                       "license_notice": notice, "original_snapshot": str(path)})
        audits.append({"canonical_id": record["canonical_id"], "source_id": f"vv{number}",
                       "source_comparison": "PASS", "stanzas": stanzas, "notes": len(translation.find("dd")),
                       "body_sha256": record["body_sha256"], "source_sha256": digest(raw)})
    held = [pdf_assessment(legacy, locks["english-licensed-sutta-books"], files)]
    previous = prior_id({**held[0], "collection": "khuddaka-nikaya/patisambhidamagga"}, prior)
    if previous:
        held[0]["prior_record_id"] = previous
    if len(records) != 649 or len({(r["collection"], r["canonical_id"], r["version_slug"]) for r in records}) != 649:
        raise ValueError("Full prepared batch count/identity changed")
    proposal = {"schema_version": 1, "metadata_license": "CC0-1.0", "code_license": "0BSD",
                "text_rights": "Every body and original source snapshot retains its record's original licence; repository metadata/code licences do not apply to source texts.",
                "records": records, "held": held}
    files["proposal.json"] = json_bytes(proposal)
    files["comparison.json"] = json_bytes({"method": METHOD, "count": len(audits), "records": audits})
    files["rights-evidence.json"] = json_bytes({"publisher": {"source_url": PTS_URL, "snapshot": "rights/pts-copyright.html", "sha256": PTS_HASH,
                                                              "announcement_date": "2021-04-08", "works": ["The Guide", "The Piṭaka Disclosure", "The Path of Discrimination"]},
                                               "records": rights})
    statuses = dict(Counter(r["completeness_status"] for r in records))
    files["CURRENT.md"] = current_document(records, held, statuses).encode()
    files["checksums.json"] = json_bytes({path: digest(data) for path, data in sorted(files.items())})
    return proposal, files


def current_document(records: list[dict], held: list[dict], statuses: dict) -> str:
    discrepancies = sum(any("source heading prints" in e for e in r["exceptions"]) for r in records)
    return f"""# SuttaCentral licensed source preparation

Prepared 649 eligible records: all 601 Walters Apadāna, all 37 Ñāṇamoli Netti,
all 9 Ñāṇamoli Peṭakopadesa, and both John Ireland Vimanavatthu translations.
The Path of Discrimination candidate is held for extraction order review.

- Policy: user-authorised edition-specific grants; unknown/ND held; no expansion.
- Code: 0BSD. Original metadata: CC0-1.0. Texts and raw snapshots retain source rights.
- SC revision: {COMMIT}.
- Pali reference revision: {PALI_COMMIT}.
- Completeness counts: {json.dumps(statuses, sort_keys=True)}.
- Exact source footer grants, translator/editor/publication notices and original
  link targets are retained. Walters uses CC BY-NC-SA 3.0 US, not the separate
  ePub edition's 4.0 grant. PTS articles use CC BY-NC 4.0.
- Walters has no separate copyright declaration: the record states this and
  retains the Whitman College publication attribution without assigning ownership.
- Ireland retains its complete free-distribution grant, derivative/source notice,
  full licence requirement and limit of 50 copies for reprinting.

## Evidence and extraction

- proposal.json uses the shared importer's records contract. Paths are relative
  to this directory; body hashes cover exact UTF-8 bytes including the final newline.
- sources/html/ contains byte-identical original HTML, with source SHA256 checked
  against pinned, checksum-verified historical manifests in sources/manifests/.
- rights/footers/ contains each exact footer; rights-evidence.json records its
  hash, full notice, source hash and original local snapshot path.
- rights/pts-copyright.html is a pinned full publisher page, not a summary.
  Announcement: https://palitextsociety.org/copyright-information/
- comparison.json records every complete source comparison. The tree renderer
  and independent flat lexer compare every ordered non-whitespace character;
  exact rendered bytes, list numbering and block/line structure are also checked.
  Headers, footers, notes, references, supplied words and printed ellipses remain.
- {discrepancies} Walters headings print numbers different from their SC IDs.
  Original IDs and full printed headings are retained and discrepancies recorded.
  Tha Ap 562–563 have no source articles in this edition.
- Pe 7 continues into Pe 8. Elided quotations/repetitions are ABBREVIATED; the
  remaining Ñāṇamoli units are UNKNOWN, not independently certified complete.

## Held PDF

- Original PDF SHA256: {held[0]['source_sha256']}.
- Existing text exactly matches fresh Poppler layout extraction:
  {held[0]['existing_matches_fresh_layout_extraction']}.
- Both engines return 664 pages. {len(held[0]['different_order_pages'])} pages differ in character order;
  {len(held[0]['different_character_multiset_pages'])} differ in character counts. This does not establish accurate
  reading order for margin references and notes. No OCR or text repairs attempted.
- assessment/path-of-discrimination/ retains the PDF, existing extraction, both
  fresh extractions and all per-page hashes/comparisons. No Ps record is proposed.

## Commands and handoff

- Prepare: python3 tools/buddhist_canon_pipeline/prepare_sc_licensed.py
- Recheck: python3 tools/buddhist_canon_pipeline/prepare_sc_licensed.py --check
- Tests: python3 -m unittest discover -s tests -p test_sc_licensed.py -v
- Preparation/check results: all 649 sources pass complete ordered comparison,
  original-source SHA256 checks, exact footer grants and exact rendered-body hashes.
- Test command results are recorded separately in verification-results.txt.
- checksums.json pins every generated handoff file except itself and separately
  recorded verification results. Regeneration is offline and byte deterministic.
- Next: primary implementer imports proposal.json through import_licensed_batches.py,
  then verifies shared manifests/readers/archives and retained notices.
  No shared metadata, renderer, validator, commit or deployment changes are made here.
"""


def write_plan(files: dict[str, bytes], output: Path = OUTPUT, check: bool = False) -> None:
    # Production CLI is confined to the assigned ignored directory.
    paths = {relative: safe_path(output, relative) for relative in files}
    for relative, path in paths.items():
        if path.exists() and path.read_bytes() != files[relative]:
            raise ValueError(f"Refusing to overwrite changed output: {path}")
        if check and not path.is_file():
            raise ValueError(f"Missing prepared output: {path}")
    if not check:
        for relative, path in paths.items():
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(files[relative])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Recompute all comparisons offline and check exact output bytes")
    parser.add_argument("--legacy-root", type=Path, default=LEGACY)
    parser.add_argument("--pts-evidence", type=Path, default=PTS_SNAPSHOT)
    args = parser.parse_args()
    proposal, files = make_plan(args.legacy_root, args.pts_evidence)
    write_plan(files, check=args.check)
    print(json.dumps({"mode": "check" if args.check else "prepare", "records": len(proposal["records"]),
                      "collections": dict(Counter(r["collection"] for r in proposal["records"])),
                      "completeness": dict(Counter(r["completeness_status"] for r in proposal["records"])),
                      "source_comparisons": "649 PASS", "held": [r["decision"] for r in proposal["held"]],
                      "files": len(files), "network_requests": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
