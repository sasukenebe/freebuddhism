#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Prepare private ATI/Thanissaro native-text proposals; never import or publish.

Metadata produced here is CC0-1.0. Source and translation payloads retain their
individual licences. Run --help for the offline and explicit-download workflow.
Only Python's standard library is required.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import subprocess
import time
import unicodedata
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "build/ati-bulk-20261111"
PALI_REVISION = "3bc8665e0e28e70518eba94304a2fafcab80f933"
ATI_URL = "https://www.accesstoinsight.org/tech/download/ati.zip"
EPUB_URL = "https://www.dhammatalks.org/Archive/Writings/Ebooks/SuttaPitaka_251113.epub"
ABOUT_URL = "https://www.dhammatalks.org/suttas/about.html"
FREE_GRANT = "Free redistribution with attribution and complete notice"
COLLECTIONS = {
    "DN": "digha-nikaya", "MN": "majjhima-nikaya",
    "SN": "samyutta-nikaya", "AN": "anguttara-nikaya",
    "Kp": "khuddaka-nikaya/khuddakapatha", "Ud": "khuddaka-nikaya/udana",
    "Iti": "khuddaka-nikaya/itivuttaka", "Snp": "khuddaka-nikaya/sutta-nipata",
    "Thag": "khuddaka-nikaya/theragatha", "Thig": "khuddaka-nikaya/therigatha",
}
COMPARISON = (
    "prepare_ati_licensed.py verify: re-read original raw HTML at source_snapshot; "
    "select its one complete COPYRIGHTED_TEXT_CHUNK (ATI) or sutta div (EPUB); "
    "compare every ordered non-whitespace Unicode character from an independent "
    "HTMLParser data stream with body_path, without Unicode/punctuation/ellipsis "
    "normalization; rerender and require byte-identical paragraphs, preformatted "
    "verses, verse lines and notes. Check source, protected HTML, body and wrapped "
    "TXT SHA-256 and exact attribution/copyright/full licence notices."
)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCKS = {"div", "p", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "li", "blockquote", "table", "tr", "fieldset", "legend"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def preserve(path: Path, data: bytes) -> None:
    """Never silently replace an existing source, body, reference or report."""
    if path.is_symlink():
        raise ValueError(f"Symlink output refused: {path}")
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Existing output differs; use a fresh output directory: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def compact(text: str) -> str:
    return " ".join(text.split())


class Characters(HTMLParser):
    """Independent source comparator: no layout renderer or selected paragraphs."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain(fragment: str) -> str:
    parser = Characters()
    parser.feed(fragment)
    parser.close()
    return compact("".join(parser.parts))


class Region(HTMLParser):
    """Capture original bytes by offsets, even when legacy p tags are unclosed."""
    def __init__(self, source: str, element_id: str):
        super().__init__(convert_charrefs=True)
        self.source, self.element_id = source, element_id
        self.offsets = [0]
        self.offsets.extend(m.end() for m in re.finditer("\n", source))
        self.start = self.end = None
        self.depth = 0
        self.matches = 0

    def position(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "div" and values.get("id") == self.element_id:
            self.matches += 1
            if self.matches != 1:
                raise ValueError(f"Duplicate {self.element_id} region")
            self.start, self.depth = self.position(), 1
        elif self.depth and tag == "div":
            self.depth += 1

    def handle_endtag(self, tag):
        if self.depth and tag == "div":
            self.depth -= 1
            if not self.depth:
                self.end = self.source.index(">", self.position()) + 1

    def extract(self) -> str:
        self.feed(self.source)
        self.close()
        if self.matches != 1 or self.end is None or self.depth:
            raise ValueError(f"Missing or truncated {self.element_id} region")
        return self.source[self.start:self.end]


def region(source: str, element_id: str) -> str:
    return Region(source, element_id).extract()


class Render(HTMLParser):
    """Whitespace-only reflow, retaining every text node and source verse break."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.divs = []
        self.pre = 0

    def boundary(self, count=2):
        while self.parts and self.parts[-1] == " ":
            self.parts.pop()
        tail = "".join(self.parts[-2:])
        existing = len(tail) - len(tail.rstrip("\n"))
        if existing < count:
            self.parts.append("\n" * (count - existing))

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        classes = values.get("class", "").split()
        verse = any(self.divs)
        if tag in {"script", "style", "img", "iframe", "object", "svg", "math"}:
            raise ValueError(f"Nontext or active element in protected region: {tag}")
        if tag == "div":
            self.divs.append(verse or "verse" in classes)
        if tag in BLOCKS:
            self.boundary(1 if tag == "p" and verse else 2)
            if tag == "p" and verse:
                indent = next((int(c[1:]) for c in classes if re.fullmatch(r"v[1-6]", c)), 0)
                self.parts.append("  " * indent)
        if tag == "pre":
            self.pre += 1
        if tag == "br":
            self.boundary(1)
        if tag in {"td", "th"}:
            self.parts.append(" ")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "pre":
            self.pre -= 1
        if tag in BLOCKS:
            self.boundary(1 if tag == "p" and any(self.divs) else 2)
        if tag == "div" and self.divs:
            self.divs.pop()

    def handle_data(self, data):
        if self.pre:
            self.parts.append(data)
        else:
            value = re.sub(r"\s+", " ", data)
            if value == " " and (not self.parts or self.parts[-1].endswith("\n")):
                return
            self.parts.append(value)

    def text(self):
        return "".join(self.parts).strip() + "\n"


def render(fragment: str) -> str:
    parser = Render()
    parser.feed(fragment)
    parser.close()
    body = parser.text()
    check_characters(fragment, body)
    return body


def check_characters(fragment: str, body: str) -> None:
    reference = Characters()
    reference.feed(fragment)
    reference.close()
    expected = re.sub(r"\s", "", "".join(reference.parts))
    actual = re.sub(r"\s", "", body)
    if not expected or actual != expected:
        raise ValueError("Full ordered source/body character comparison failed")


def fields(source: str) -> dict[str, str]:
    dump = re.search(r"Begin ATIDoc metadata dump:(.*?)End ATIDoc metadata dump", source, re.S)
    if not dump:
        raise ValueError("Missing ATI metadata")
    return {key: plain(value) for key, value in re.findall(r"^\[([A-Z0-9_]+)\]=\{(.*?)\}\s*$", dump[1], re.M)}


def rights(notice: str, terms_url: str) -> dict:
    """Classify the exact source grant; unrelated site/page rights cannot clear it."""
    urls = re.findall(r"https?://creativecommons\.org/(?:licenses|publicdomain)/[^\s<>\"']+", notice)
    for url in urls:
        # The publisher prints a full stop immediately after the linked URL.
        # Trim prose punctuation for identification, never from the saved notice.
        url = url.rstrip(".,;:)")
        match = re.fullmatch(r"https?://creativecommons.org/licenses/(by(?:-nc)?(?:-sa)?(?:-nd)?)/(\d\.\d)/?", url)
        if not match:
            continue
        if "nd" in match[1]:
            raise ValueError("No-derivatives licence requires separate review")
        return {"license": f"CC-{match[1].upper()}-{match[2]}",
                "license_url": f"https://creativecommons.org/licenses/{match[1]}/{match[2]}/"}
    lower = notice.lower()
    required = ("you may copy, reformat, reprint, republish, and redistribute this work",
                "free of charge", "derived from this source document",
                "include the full text of this license", "otherwise, all rights reserved")
    if all(item in lower for item in required):
        conditions = ["attribution", "free-of-charge", "identify-derivatives", "complete-license-notice"]
        if "no more than 50 copies" in lower:
            conditions.append("printed-reproductions-no-more-than-50-copies")
        return {"license": FREE_GRANT, "license_url": terms_url,
                "explicit_grant": notice, "conditions": conditions}
    raise ValueError("Unclear or unsupported per-text redistribution grant")


def ati_rights(source: str, url: str) -> dict:
    match = re.search(r"\[DERIVED_LICENSE_DATA\]=\s*\{(.*?)\}\s*\{", source, re.S)
    if not match:
        raise ValueError("No per-text ATI licence notice")
    notice = plain(match[1])
    result = rights(notice, url + "#F_termsOfUse")
    result["license_notice"] = notice
    # Keep complete footer and publisher's colophon as attribution evidence too.
    result["attribution_notice"] = plain(region(source, "F_colophon"))
    result["copyright"] = plain(region(source, "F_sourceCopy"))
    if not result["copyright"]:
        raise ValueError("Missing per-text copyright notice")
    return result


def normal_title(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[^a-z]", "", text)
    return re.sub(r"sutt(?:am|a|as|an)?$", "", text)


def make_reference(output: Path, pali_git: Path) -> None:
    """Snapshot only site IDs and pinned Pali title metadata from a local cache."""
    eligible = json.loads((ROOT / "metadata/eligible-texts.json").read_bytes())["texts"]
    site = {r["canonical_id"]: r["collection"] for r in eligible
            if r["canonical_id"].split()[0] in COLLECTIONS}
    excluded = json.loads((ROOT / "metadata/excluded-sources.json").read_bytes())["text_versions"]
    prior = {r["source_url"].replace("http://", "https://").replace("https://accesstoinsight", "https://www.accesstoinsight"): r["record_id"]
             for r in excluded if r.get("source_url")}
    command = ["git", "--git-dir=" + str(pali_git)]
    tree = subprocess.check_output(command + ["ls-tree", "-r", PALI_REVISION, "root/pli/ms/sutta/"], text=True)
    items = []
    for line in tree.splitlines():
        info, path = line.split("\t", 1)
        if path.endswith("_root-pli-ms.json"):
            items.append((info.split()[2], path))
    if not items:
        raise ValueError("No pinned Pali titles in local Git object cache")
    # Read all blobs in one read-only process; no checkout, fetch or remote call.
    data = subprocess.check_output(command + ["cat-file", "--batch"], input="".join(blob + "\n" for blob, _ in items).encode())
    stream = io.BytesIO(data)
    titles = {}
    references = {}
    for expected_blob, path in items:
        header = stream.readline().decode().split()
        if len(header) != 3 or header[0] != expected_blob or header[1] != "blob":
            raise ValueError("Pinned Pali Git object unavailable")
        raw = stream.read(int(header[2])); stream.read(1)
        if hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() != expected_blob:
            raise ValueError("Pinned Pali Git object changed")
        for key, value in json.loads(raw).items():
            uid, segment = key.split(":", 1)
            match = re.fullmatch(r"(dn|mn|sn|an|kp|ud|iti|snp|thag|thig)([0-9][0-9.\-]*)", uid)
            if not match or not segment.startswith("0."):
                continue
            prefix = next(p for p in COLLECTIONS if p.lower() == match[1])
            canonical = prefix + " " + match[2]
            if canonical in site:
                titles.setdefault(canonical, []).append(compact(value))
                references[canonical] = {"upstream_file": path, "git_blob_sha1": expected_blob}
    reference = {"schema_version": 1, "license": "CC0-1.0", "pali_revision": PALI_REVISION,
                 "pali_repository": "https://github.com/suttacentral/bilara-data",
                 "site_ids": site, "pali_titles": titles, "pali_references": references,
                 "prior_records_by_url": prior}
    preserve(output / "canonical-reference.json", json_bytes(reference))


def resolve_id(prefix: str, number: str, title: str, reference: dict, alternate="") -> tuple[str, dict]:
    """No splitting a grouped source and no inference from a matching filename."""
    if not re.fullmatch(r"\d+(?:\.\d+)?", number):
        raise ValueError("Grouped/multi-sutta or ambiguous source numbering; retain whole source only")
    proposed = f"{prefix} {number}"
    candidate = proposed
    thai = re.search(r"Thai[: ]+(\d+\.\d+)", alternate)
    if thai:
        candidate = prefix + " " + thai[1]
    ids = reference["site_ids"]
    evidence = {"publisher_id": proposed, "publisher_alternate_id": alternate}
    # DN/MN and these small-collection numbering systems match the site's IDs.
    # AN/SN require title corroboration: both publishers use other editions.
    if prefix not in {"AN", "SN"}:
        if candidate not in ids:
            raise ValueError("Source ID does not exist in the site's canonical IDs")
        return candidate, {**evidence, "method": "publisher single-unit ID in site's canonical ID inventory"}
    target = normal_title(title)
    if not target:
        raise ValueError("No Pali title for AN/SN numbering comparison")
    def matches(canonical):
        for root in reference["pali_titles"].get(canonical, []):
            normalized = normal_title(root)
            if target == normalized or target == re.sub(r"^(pathama|dutiya|tatiya|catuttha|pancama)", "", normalized):
                return True
        return False
    if candidate in ids and matches(candidate):
        return candidate, {**evidence, "method": "single-unit ID and pinned Pali title agree",
                           "pali": reference["pali_references"].get(candidate)}
    chapter = number.split(".")[0]
    alternatives = [key for key in ids if key.startswith(f"{prefix} {chapter}.") and matches(key)]
    if len(alternatives) != 1:
        raise ValueError(f"AN/SN numbering needs review: title candidates {alternatives}")
    canonical = alternatives[0]
    return canonical, {**evidence, "method": "unique pinned Pali title within publisher chapter; numbering corrected",
                       "pali": reference["pali_references"].get(canonical)}


def completeness(body: str, *, extent="", thanissaro=False, explicit_partial=False) -> tuple[str, str]:
    if extent == "excerpt" or explicit_partial:
        return "PARTIAL", "Complete source excerpt preserved, including introductions, notes and verse structure; source omits part of the canonical discourse."
    # Ellipses remain exact source characters. Never expand them into invented text.
    if thanissaro:
        return "ABBREVIATED", ("Every source-unit character is preserved, including introductions, notes and verse structure. "
                "Thanissaro's collection-level note explicitly states that repetitions were cut: " + ABOUT_URL +
                ". This is evidence about the translation method, not an assertion that every individual unit contains an omission; no repetitions reconstructed.")
    if re.search(r"\.{3}|…|repetitions? (?:ha(?:s|ve) been )?(?:omit|abbreviat)|avoid excessive repetition", body, re.I):
        return "ABBREVIATED", "Every source-unit character is preserved; source ellipsis or repetition-omission statement retained. Canonical repetitions were not reconstructed."
    return "UNKNOWN", "Entire protected source unit, including notes and verses, preserved; canonical completeness has not been independently established."


def ati_unit(name: str, source: str, reference: dict) -> dict:
    meta = fields(source)
    prefix = meta.get("NIKAYA_ABBREV", "")
    if prefix == "KN":
        prefix = {"khp": "Kp", "ud": "Ud", "iti": "Iti", "snp": "Snp", "thag": "Thag", "thig": "Thig"}.get(name.split("/")[3], "")
    if prefix not in COLLECTIONS:
        raise ValueError("No clear supported small-collection mapping")
    number = meta.get("NUMBER", "")
    if prefix in {"AN", "SN"}:
        number = meta.get("SECTION", "") + "." + number
    canonical, mapping = resolve_id(prefix, number, meta.get("MY_TITLE", ""), reference, meta.get("ALT_ID", ""))
    url = "https://www.accesstoinsight.org/" + name.removeprefix("ati/")
    title = ": ".join(meta[k] for k in ("MY_TITLE", "SUBTITLE") if meta.get(k))
    translator = " and ".join(meta[k] for k in ("AUTHOR", "AUTHOR2") if meta.get(k))
    if not title or not translator:
        raise ValueError("Missing title or translator")
    return {"canonical_id": canonical, "collection": reference["site_ids"][canonical],
            "title": title, "translator": translator, "source_url": url, "mapping_evidence": mapping,
            "extent": meta.get("EXTENT", ""), "version_slug": "ati-" + slug(translator),
            **ati_rights(source, url)}


def epub_unit(name: str, source: str, reference: dict, epub_rights: dict) -> dict:
    title_match = re.search(r"<title>(.*?)</title>", source, re.S)
    if not title_match:
        raise ValueError("No publisher title")
    title = plain(title_match[1])
    match = re.match(r"(DN|MN|SN|AN|Khp|Ud|Iti|Sn|Thag|Thig)\s+(\d+(?:[:.]\d+)?)(?=\s|$|[–—,\-])", title)
    if not match:
        raise ValueError("No single-unit source title identifier")
    remainder = title[match.end():]
    if remainder.startswith(("–", "-", ",")):
        raise ValueError("Grouped/multi-sutta source title; do not split")
    prefix = {"Khp": "Kp", "Sn": "Snp"}.get(match[1], match[1])
    number = match[2].replace(":", ".")
    pali_title = title.split(" | ", 1)[1] if " | " in title else ""
    canonical, mapping = resolve_id(prefix, number, pali_title, reference)
    url = "https://www.dhammatalks.org/suttas/" + name
    return {"canonical_id": canonical, "collection": reference["site_ids"][canonical],
            "title": title, "translator": "Ṭhānissaro Bhikkhu", "source_url": url,
            "mapping_evidence": mapping, "extent": "", "version_slug": "thanissaro-dhammatalks",
            **epub_rights}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normal_ascii(text)).strip("-")


def normal_ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def safe_output(value: str) -> Path:
    path = Path(value).absolute()
    base = (ROOT / "build").resolve()
    if not path.resolve().is_relative_to(base) or path.resolve() == base:
        raise ValueError("Private output must be a child of repository build/")
    if any(p.is_symlink() for p in [path, *path.parents] if p != p.parent):
        raise ValueError("Symlink output path refused")
    return path


def wrapped(row: dict, body: str) -> str:
    lines = [f"{row['canonical_id']} - {row['title']}", f"Translated by {row['translator']}",
             "Source: " + row["source_url"], "License: " + row["license"],
             "License URL: " + row["license_url"], "Copyright: " + row["copyright"],
             "License notice: " + row["license_notice"],
             "Attribution: " + row["attribution_notice"],
             "Changes: HTML markup reflowed to plain text; every protected text character retained.",
             "Completeness: " + row["completeness_status"] + ". " + row["completeness_scope"]]
    return "\n".join(lines) + "\n\n" + body


def prepare(output: Path) -> dict:
    reference_path = output / "canonical-reference.json"
    reference = json.loads(reference_path.read_bytes())
    source_dir = output / "sources"
    about = (source_dir / "dhammatalks-about.html").read_bytes()
    if "cut as many of the repetitions as possible" not in plain(about.decode("utf-8")):
        raise ValueError("Missing Thanissaro repetition-abbreviation evidence")
    archives = [("ati", source_dir / "ati.zip", ATI_URL, "COPYRIGHTED_TEXT_CHUNK"),
                ("dhammatalks", source_dir / "SuttaPitaka_251113.epub", EPUB_URL, "sutta")]
    records, held, archive_locks = [], [], []
    for publisher, path, archive_url, region_id in archives:
        archive_data = path.read_bytes()
        archive_hash = sha(archive_data)
        archive_locks.append({"path": str(path.relative_to(ROOT)), "sha256": archive_hash, "source_url": archive_url})
        with ZipFile(io.BytesIO(archive_data)) as archive:
            if len(set(archive.namelist())) != len(archive.namelist()):
                raise ValueError("Duplicate archive members")
            # Full archive CRC verification, not just whichever pages happen to map.
            broken = archive.testzip()
            if broken:
                raise ValueError("Corrupt archive member: " + broken)
            epub_rights = {}
            if publisher == "dhammatalks":
                copyright_html = archive.read("Copyright.html").decode("utf-8")
                notice = plain(region(copyright_html, "copyright"))
                epub_rights = {**rights(notice, archive_url), "license_notice": notice,
                               "copyright": "Copyright 2014 Ṭhānissaro Bhikkhu, Revised edition 2017",
                               "attribution_notice": "From Handful of Leaves, Ṭhānissaro Bhikkhu; " + archive_url + ". " + notice}
                preserve(source_dir / "dhammatalks-Copyright.html", archive.read("Copyright.html"))
            for name in sorted(archive.namelist()):
                if publisher == "ati":
                    if not re.search(r"^ati/tipitaka/(dn|mn|sn|an|kn)/.*\.html$", name):
                        continue
                elif not re.fullmatch(r"(?:DN/DN\d+|MN/MN\d+|SN/SN\d+(?:_\d+)?|AN/AN\d+_\d+|KN/(?:Khp/khp\d+|Ud/ud\d+_\d+|Iti/iti\d+|StNp/StNp\d+_\d+|Thag/thag\d+(?:_\d+)?|Thig/thig\d+(?:_\d+)?))\.html", name):
                    continue
                raw = archive.read(name)
                source = raw.decode("utf-8", "strict")
                if publisher == "ati" and "[TYPE]={sutta}" not in source:
                    continue
                source_path = source_dir / "pages" / publisher / name
                preserve(source_path, raw)
                held_base = {"publisher": publisher, "upstream_file": name, "source_sha256": sha(raw),
                             "source_snapshot": str(source_path.relative_to(ROOT)), "held_reasons": []}
                try:
                    row = ati_unit(name, source, reference) if publisher == "ati" else epub_unit(name, source, reference, epub_rights)
                    fragment = region(source, region_id)
                    # ATI explicitly marks the end; a premature div close must not truncate it.
                    if publisher == "ati":
                        after = source[source.index(fragment) + len(fragment):]
                        if not re.match(r"\s*<!--\s*#COPYRIGHTED_TEXT_CHUNK\s*\(END", after):
                            raise ValueError("Protected region does not reach its publisher end marker")
                    body = render(fragment)
                    partial = publisher == "dhammatalks" and bool(re.search(r"\bExcerpt\b", row["title"], re.I))
                    status, scope = completeness(body, extent=row.pop("extent"),
                                                 thanissaro="thanissaro" in normal_ascii(row["translator"]),
                                                 explicit_partial=partial)
                    row.update(completeness_status=status, completeness_scope=scope)
                    identifier = slug(row["canonical_id"])
                    body_path = output / "bodies" / row["version_slug"] / (identifier + "-" + sha(raw)[:12] + ".txt")
                    html_path = body_path.with_suffix(".protected.html")
                    wrapped_path = body_path.with_suffix(".attributed.txt")
                    row.update(source_snapshot=str(source_path.relative_to(ROOT)), source_sha256=sha(raw),
                               body_path=str(body_path.relative_to(ROOT)), body_sha256=sha(body.encode()),
                               protected_html_path=str(html_path.relative_to(ROOT)), protected_html_sha256=sha(fragment.encode()),
                               wrapped_path=str(wrapped_path.relative_to(ROOT)),
                               source_comparison="PASS", source_comparison_method=COMPARISON,
                               source_region_id=region_id, upstream_file=name,
                               source_revision=f"sha256:{archive_hash}",
                               source_repository=archive_url, archive_sha256=archive_hash,
                               exceptions=[], prior_record_id=reference["prior_records_by_url"].get(row["source_url"]),
                               rights_status="SOURCE_LICENSE_VERIFIED", publishable=False)
                    if status in {"PARTIAL", "ABBREVIATED", "UNKNOWN"}:
                        row["exceptions"].append("Translation completeness is " + status + "; see completeness_scope.")
                    if row["mapping_evidence"]["publisher_id"] != row["canonical_id"]:
                        row["exceptions"].append("Publisher numbering differs; see mapping_evidence.")
                    text = wrapped(row, body)
                    row["wrapped_sha256"] = sha(text.encode())
                    preserve(body_path, body.encode())
                    preserve(html_path, fragment.encode())
                    preserve(wrapped_path, text.encode())
                    records.append(row)
                except ValueError as error:
                    held_base["held_reasons"].append(str(error))
                    # Private held metadata never invents a canonical ID or individual body.
                    held.append(held_base)
    # Two source pages of the same translator at one canonical ID can be alternate
    # editions. Give each an explicit version, never duplicate an import key.
    groups = defaultdict(list)
    for row in records:
        groups[(row["canonical_id"], row["version_slug"])].append(row)
    for group in groups.values():
        if len(group) > 1:
            for row in group:
                row["version_slug"] += "-" + row["source_sha256"][:8]
                row["exceptions"].append("Alternate source edition at this canonical ID; source hash distinguishes version.")
    records.sort(key=lambda r: (r["collection"], r["canonical_id"], r["version_slug"]))
    proposal = {"schema_version": 1, "metadata_license": "CC0-1.0", "code_license": "0BSD",
                "publishable": False, "source_comparison_method": COMPARISON,
                "canonical_reference_sha256": sha(reference_path.read_bytes()),
                "abbreviation_evidence": {"source_url": ABOUT_URL, "source_snapshot": str((source_dir / "dhammatalks-about.html").relative_to(ROOT)), "sha256": sha(about)},
                "archives": archive_locks, "count": len(records), "records": records,
                "held_count": len(held), "held": held}
    preserve(output / "proposal.json", json_bytes(proposal))
    return proposal


def verify(proposal_path: Path) -> dict:
    proposal = json.loads(proposal_path.read_bytes())
    for entry in proposal["archives"]:
        if sha((ROOT / entry["path"]).read_bytes()) != entry["sha256"]:
            raise ValueError("Original bulk archive changed")
    if sha((proposal_path.parent / "canonical-reference.json").read_bytes()) != proposal["canonical_reference_sha256"]:
        raise ValueError("Canonical reference changed")
    evidence = proposal["abbreviation_evidence"]
    if sha((ROOT / evidence["source_snapshot"]).read_bytes()) != evidence["sha256"]:
        raise ValueError("Abbreviation evidence changed")
    seen = set()
    for row in proposal["records"]:
        key = (row["collection"], row["canonical_id"], row["version_slug"])
        if key in seen:
            raise ValueError("Duplicate import key")
        seen.add(key)
        for path_field, hash_field in (("source_snapshot", "source_sha256"), ("body_path", "body_sha256"),
                                       ("protected_html_path", "protected_html_sha256"), ("wrapped_path", "wrapped_sha256")):
            if sha((ROOT / row[path_field]).read_bytes()) != row[hash_field]:
                raise ValueError("Changed prepared file: " + row[path_field])
        source = (ROOT / row["source_snapshot"]).read_text(encoding="utf-8")
        fragment = region(source, row["source_region_id"])
        if fragment.encode() != (ROOT / row["protected_html_path"]).read_bytes():
            raise ValueError("Protected HTML differs from original")
        body = (ROOT / row["body_path"]).read_text(encoding="utf-8")
        check_characters(fragment, body)
        if render(fragment) != body:
            raise ValueError("Paragraph or verse layout differs from original rendering")
        if wrapped(row, body).encode() != (ROOT / row["wrapped_path"]).read_bytes():
            raise ValueError("Wrapped TXT attribution/notices changed")
        if urlsplit(row["source_url"]).scheme != "https" or not row["copyright"] or not row["license_notice"]:
            raise ValueError("Missing source notices or HTTPS source")
    return {"records": len(seen), "held": len(proposal["held"]), "comparison": "PASS"}


def download(output: Path) -> None:
    """Single sequential requests, no automatic retries, honour an HTTP stop."""
    sources = output / "sources"
    requests = [("bulk.html", "https://www.accesstoinsight.org/tech/download/bulk.html"),
                ("ati.zip", ATI_URL), ("SuttaPitaka_251113.epub", EPUB_URL),
                ("dhammatalks-about.html", ABOUT_URL)]
    for name, url in requests:
        target = sources / name
        if target.exists():
            continue
        if (sources / "NETWORK-STOP.json").exists():
            raise ValueError("Previous download failure recorded; resolve NETWORK-STOP.json before new requests")
        time.sleep(2)
        try:
            with urlopen(Request(url, headers={"User-Agent": "FreeBuddhism-native-text-preparation/1.0"}), timeout=120) as response:
                raw = response.read()
                headers = dict(response.headers)
            preserve(target, raw)
            preserve(target.with_suffix(target.suffix + ".headers.json"), json_bytes(headers))
        except (OSError, HTTPError) as error:
            preserve(sources / "NETWORK-STOP.json", json_bytes({"url": url, "error": str(error), "retry_after": getattr(error, "headers", {}).get("Retry-After")}))
            raise ValueError("Download failed; stopped without retries: " + url) from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("download", "reference", "prepare", "verify"))
    parser.add_argument("--output", type=safe_output, default=DEFAULT_OUTPUT)
    parser.add_argument("--pali-git", type=Path, help="Existing .git directory containing pinned Pali revision; reference action only")
    args = parser.parse_args()
    if args.action == "download":
        download(args.output)
    elif args.action == "reference":
        if not args.pali_git:
            parser.error("reference requires --pali-git (read-only local Git cache)")
        make_reference(args.output, args.pali_git)
    elif args.action == "prepare":
        proposal = prepare(args.output)
        print(json.dumps({"records": proposal["count"], "held": proposal["held_count"],
                          "collections": dict(Counter(r["collection"] for r in proposal["records"]))}, sort_keys=True))
    else:
        print(json.dumps(verify(args.output / "proposal.json"), sort_keys=True))


if __name__ == "__main__":
    main()
