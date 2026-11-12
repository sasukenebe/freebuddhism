#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Prepare (never publish) all excluded ABT Jataka verse sets from saved sources.

Code: 0BSD. Generated descriptive metadata: CC0-1.0. Source text and notices
retain their original rights. No network is used unless --refresh-evidence is set.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO / "build/abt-bulk-20261111"
BASE = "https://ancient-buddhist-texts.net/"
COPYRIGHT = BASE + "Miscellaneous/Copyright-Notice.htm"
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
# Reviewed complete exception list, fetched 2026-11-11. A changed list requires
# renewed source-specific review, even when the generic default remains present.
COPYRIGHT_SHA256 = "5331ab859a47265be7ffac6375fe1274146b956e9da0047864a178d29a3a4d68"
GROUPS = {
    "ABT Jataka English verse sets": ("abt-jataka-verses", 134),
    "ABT Jataka English verse sets (Cst4 Pali variants)": ("abt-jataka-cst4-variants", 124),
    "ABT Jataka English verse sets with source-page summaries": ("abt-jataka-summary-variants", 29),
}
EVIDENCE_URLS = {
    "copyright.html": COPYRIGHT,
    "footer.js": BASE + "includes/Footer.js",
    "english-index.html": BASE + "English-Texts/index.htm",
    "parallel-index.html": BASE + "Texts-and-Translations/index.htm",
    "document-list.html": BASE + "Miscellaneous/Document-List.htm",
    "buddhapadana.html": BASE + "English-Texts/Short-Pieces-in-English/Buddhapadana.htm",
    "short-readings.html": BASE + "English-Texts/Short-Readings/index.htm",
    "dhamma-verses.html": BASE + "English-Texts/Dhamma-Verses/index.htm",
    "exalted-utterances.html": BASE + "English-Texts/Exalted-Utterances/index.htm",
}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def no_space(value: str) -> str:
    """Exact wording comparison: no accent, case, punctuation or order folding."""
    return re.sub(r"\s+", "", value)


def layout(parts: list[str]) -> str:
    # HTML source newlines are whitespace; only <br> introduces a verse line.
    return "\n".join(re.sub(r"\s+", " ", line).strip()
                     for line in "".join(parts).split("\0")).strip()


class SourceParser(HTMLParser):
    """Read every paragraph, with notes separate and explicit HTML breaks intact.

    ABT has stray <tr> tags inside two verse paragraphs: HTMLParser intentionally
    does not repair/reparent them and therefore does not drop their wording.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.scripts = []
        self.links = []
        self.current = None
        self.note_parts = None
        self.note_depth = 0
        self.hidden_depth = 0
        self.repairs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("src"):
            self.scripts.append(attrs["src"])
        if tag == "a" and attrs.get("href"):
            self.links.append({"url": attrs["href"], "rel": attrs.get("rel", "")})
        if tag in {"script", "style"}:
            self.hidden_depth += 1
        if self.hidden_depth:
            return
        if tag == "p":
            if self.current is not None:
                raise ValueError("Nested/unclosed source paragraph")
            classes = attrs.get("class", "").split()
            kind = ("pali" if any(re.fullmatch(r"verse\d+", c) for c in classes) else
                    "english" if "translation" in classes else
                    "heading" if "Heading3" in classes else
                    "synopsis" if "summary" in classes else
                    "navigation" if any(c.startswith("NavBar") for c in classes) else "commentary")
            self.current = {"kind": kind, "parts": [], "source_parts": [], "notes": [], "classes": classes,
                            "break_count": 0}
        elif self.current is not None:
            if tag == "br":
                self.current["source_parts"].append("\0")
            if self.note_parts is not None:
                if tag not in VOID:
                    self.note_depth += 1
                if tag == "br":
                    self.note_parts.append("\0")
            elif "TT" in attrs.get("class", "").split():
                self.note_parts, self.note_depth = [], 1
            elif tag == "br":
                self.current["parts"].append("\0")
                self.current["break_count"] += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if self.current is not None and not self.hidden_depth:
            self.current["source_parts"].append(data)
            (self.note_parts if self.note_parts is not None else self.current["parts"]).append(data)

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden_depth = max(0, self.hidden_depth - 1)
            return
        if self.hidden_depth:
            return
        if self.note_parts is not None and tag == "p":
            # Ja 13 omits one </span> in a commentary tooltip. Close the tooltip
            # at its paragraph boundary, retaining every word and recording it.
            self.current["notes"].append(layout(self.note_parts))
            self.note_parts, self.note_depth = None, 0
            self.repairs.append({"paragraph": len(self.blocks), "kind": self.current["kind"],
                                 "repair": "unclosed tooltip ended at explicit paragraph boundary"})
        elif self.note_parts is not None:
            if tag not in VOID:
                self.note_depth -= 1
            if self.note_depth == 0:
                self.current["notes"].append(layout(self.note_parts))
                self.note_parts = None
            return
        if tag == "p" and self.current is not None:
            block = self.current
            block["text"] = layout(block.pop("parts"))
            block["source_text"] = layout(block.pop("source_parts"))
            self.blocks.append(block)
            self.current = None


def parse(source: bytes | str) -> SourceParser:
    parser = SourceParser()
    parser.feed(source.decode("utf-8-sig") if isinstance(source, bytes) else source)
    parser.close()
    if parser.current is not None or parser.note_parts is not None:
        raise ValueError("Unclosed source paragraph or source note")
    return parser


class VisibleBodyParser(HTMLParser):
    """Independent full-page extraction without paragraph/class/note selection."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_body, self.hidden = False, 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.in_body = True
        if tag in {"script", "style"}:
            self.hidden += 1
        if self.in_body and not self.hidden and tag in {"br", "p"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "body":
            self.in_body = False

    def handle_data(self, data):
        if self.in_body and not self.hidden:
            self.parts.append(data)


def whole_source_partition(source: bytes, blocks: list[dict]) -> dict:
    reader = VisibleBodyParser()
    reader.feed(source.decode("utf-8-sig"))
    reader.close()
    whole = no_space("".join(reader.parts))
    partition = no_space("".join(b["source_text"] for b in blocks))
    if not whole or whole != partition:
        raise ValueError("Whole source has visible wording outside the recorded paragraph partition")
    return {"status": "ALL_VISIBLE_BODY_CHARACTERS_ACCOUNTED_FOR",
            "character_count_ignoring_whitespace": len(whole),
            "whole_visible_wording_sha256": sha256(whole.encode()),
            "partition_wording_sha256": sha256(partition.encode()),
            "rule": "every visible body character in source order, including all notes/commentary; whitespace only ignored; scripts/styles excluded"}


def pali_letters(text: str) -> str:
    # This is the old manifest's edition comparison, not a wording comparison.
    value = unicodedata.normalize("NFC", text).lower().replace("ṃ", "ṁ")
    return "".join(c for c in value if c.isalpha())


def compare_source(number: int, source: bytes, root: dict, *, summary: bool) -> dict:
    parsed = parse(source)
    partition = whole_source_partition(source, parsed.blocks)
    if parsed.repairs and not (number == 13 and len(parsed.repairs) == 1
                               and parsed.repairs[0]["kind"] == "commentary"):
        raise ValueError("Unreviewed unclosed tooltip in source")
    headings = [b for b in parsed.blocks if b["kind"] == "heading"]
    if len(headings) != 1 or not headings[0]["text"].startswith(f"Ja {number} "):
        raise ValueError("Unexpected canonical source heading")
    verses = [b for b in parsed.blocks if b["kind"] in {"pali", "english"}]
    count = len(verses) // 2
    if not count or [b["kind"] for b in verses] != [k for _ in range(count) for k in ("pali", "english")]:
        raise ValueError("Incomplete or out-of-order Pali/English verse pairs")
    if any(not b["text"] for b in verses):
        raise ValueError("Empty source stanza")
    groups = {}
    segments = {}
    for key, value in root.items():
        match = re.fullmatch(rf"ja{number}:(\d+)\.(\d+)", key)
        if not match or not isinstance(value, str):
            raise ValueError("Unexpected reference segment")
        group, segment = map(int, match.groups())
        segments.setdefault(group, []).append(segment)
        groups.setdefault(group, []).append(value)
    if any(ids != list(range(1, len(ids) + 1)) for ids in segments.values()):
        raise ValueError("Missing or out-of-order reference line identifiers")
    if list(groups) != list(range(max(groups) + 1)) or not set(range(count + 2)) <= set(groups):
        raise ValueError("Reference has additional verses or an unexpected structure")
    colophon = groups[count + 1]
    if summary:
        endings = [s for s in colophon if re.search(r"jātaka[ṁṃ]?\s+dasama[ṁṃ]?", s.casefold())]
        if len(endings) != 1 or any(s not in endings and not re.search(r"vagg[oa][ṁṃ]?\b", s.casefold()) for s in colophon):
            raise ValueError("Missing expected Jataka colophon")
    elif len(colophon) != 1 or "jātaka" not in colophon[0].casefold():
        raise ValueError("Missing expected Jataka colophon")
    trailing = {k: groups[k] for k in groups if k > count + 1}
    if trailing and (not summary or not " ".join(sum(trailing.values(), [])).strip().casefold().startswith("tassuddāna")):
        raise ValueError("Unaccounted reference material after the verse set")
    if summary and not trailing:
        raise ValueError("Expected trailing collection summary missing")
    pairs, variants = [], []
    for i in range(1, count + 1):
        pali, english = verses[2 * (i - 1):2 * i]
        printed = re.match(r"^(\d+)\.\s", pali["text"])
        if printed and int(printed[1]) != i:
            raise ValueError("Source stanza numbering gap, duplicate or reordering")
        if not printed and (number, i) not in {(39, 1), (46, 1)}:
            raise ValueError("Unreviewed unnumbered source stanza")
        reference = "".join(groups[i])
        matches = pali_letters(pali["text"]) == pali_letters(reference)
        if not matches:
            variants.append(i)
        pairs.append({"ordinal": i, "printed_number": int(printed[1]) if printed else None,
                      "pali": pali, "english": english, "reference_segments": groups[i],
                      "reference_edition_match": matches,
                      "reference_comparison_rule": "NFC, lowercase, alphabetic characters, niggahita ṃ/ṁ equivalent; complete source/reference wording separately retained"})
        for block in (pali, english):
            if block["text"].count("\n") != block["break_count"]:
                raise ValueError("Source verse line break not retained")
    return {"title": headings[0]["text"].splitlines()[0], "pairs": pairs,
            "variant_verses": variants, "reference_title": groups[0],
            "reference_colophon": colophon, "trailing_summary": trailing,
            "source_blocks": parsed.blocks,
            "html_repairs": parsed.repairs,
            "whole_source_comparison": partition,
            "paragraph_partition": dict(Counter(b["kind"] for b in parsed.blocks)),
            "source_paragraph_count": len(parsed.blocks)}


def compare_original(original: bytes, comparison: dict, variant: bool, url: str) -> dict:
    text = original.decode("utf-8")
    match = re.search(r"^Verse 1(?: — Pali source)?\n", text, re.M)
    if not match:
        raise ValueError("Original TXT has no first verse boundary")
    header, body = text[:match.start()], text[match.start():]
    if header.splitlines()[0] != comparison["title"] or f"Source: {url}\n" not in header:
        raise ValueError("Original TXT title/source attribution differs")
    if f"License: CC-BY-SA-4.0 ({LICENCE_URL})" not in header:
        raise ValueError("Original TXT has conflicting licence attribution")
    expected = []
    for pair in comparison["pairs"]:
        i = pair["ordinal"]
        if variant:
            expected += [f"Verse {i} — Pali source\n{pair['pali']['text']}\n",
                         f"Verse {i} — English\n{pair['english']['text']}\n"]
        else:
            expected.append(f"Verse {i}\n{pair['english']['text']}\n")
    if no_space(body) != no_space("\n".join(expected)):
        raise ValueError("Whole original TXT body differs from pinned source verse extraction")
    return {"status": "ALL_VERSES_MATCH", "original_sha256": sha256(original),
            "original_header": header.rstrip(), "original_body_sha256": sha256(body.encode()),
            "comparison_rule": "all body characters in order, ignoring whitespace only; notes separately preserved",
            "all_body_characters_accounted_for": True,
            "source_note_count_omitted_in_original": sum(len(p[k]["notes"]) for p in comparison["pairs"] for k in (["pali", "english"] if variant else ["english"]))}


def render_body(comparison: dict, variant: bool) -> str:
    lines = []
    for pair in comparison["pairs"]:
        i = pair["ordinal"]
        for language in (["pali", "english"] if variant else ["english"]):
            label = "Pali source" if language == "pali" else "English"
            lines += [f"Verse {i} — {label}" if variant else f"Verse {i}", pair[language]["text"], ""]
            for n, note in enumerate(pair[language]["notes"], 1):
                lines += [f"Source note {i}.{n} ({label})", note, ""]
        if not variant:
            for n, note in enumerate(pair["pali"]["notes"], 1):
                lines += [f"Source note {i}.{n} (Pali source)", note, ""]
    return "\n".join(lines).rstrip() + "\n"


def verified(path: Path, digest: str) -> bytes:
    data = path.read_bytes()
    if sha256(data) != digest:
        raise ValueError(f"Pinned source hash mismatch: {path.name}")
    return data


def within(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Input path escapes source repository")
    return path


def refresh_evidence(out: Path) -> None:
    evidence = out / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    lock = {}
    for name, url in EVIDENCE_URLS.items():
        request = Request(url, headers={"User-Agent": "freebuddhism-abt-preparation/1.0"})
        with urlopen(request, timeout=40) as response:
            data = response.read()
            lock[name] = {"url": url, "sha256": sha256(data),
                          "last_modified": response.headers.get("Last-Modified"),
                          "etag": response.headers.get("ETag")}
        (evidence / name).write_bytes(data)
    write_json(evidence / "lock.json", lock)


def load_evidence(out: Path) -> dict:
    evidence = out / "evidence"
    lock = json.loads((evidence / "lock.json").read_text(encoding="utf-8"))
    if set(lock) != set(EVIDENCE_URLS):
        raise ValueError("Incomplete live evidence lock")
    for name, url in EVIDENCE_URLS.items():
        if lock[name]["url"] != url:
            raise ValueError("Unexpected evidence URL")
        verified(evidence / name, lock[name]["sha256"])
    return lock


def check_licence(source: bytes, footer: bytes, copyright: bytes, url: str) -> dict:
    parser = parse(source)
    if "../../includes/Footer.js" not in parser.scripts:
        raise ValueError("Page does not load the pinned licence footer")
    footer_text = footer.decode("utf-8-sig")
    if LICENCE_URL not in footer_text:
        raise ValueError("Pinned page footer does not grant CC BY-SA 4.0")
    page = source.decode("utf-8-sig")
    # A newly encountered local licence/copyright statement must be reviewed; a
    # permissive site footer never overrides a work-specific exception.
    if re.search(r"copyright|creativecommons\.org|\blicen[cs]e\b|all rights reserved|no.derivatives", page, re.I):
        raise ValueError("Page-specific licence/copyright statement requires review")
    if not re.fullmatch(re.escape(BASE) + r"English-Texts/Jataka-Verses/\d{3}\.htm", url):
        raise ValueError("Licence decision is restricted to reviewed Jataka-Verses pages")
    notice = copyright.decode("utf-8-sig")
    if sha256(copyright) != COPYRIGHT_SHA256 or "by-sa/3.0" not in notice or "May 2013" not in notice:
        raise ValueError("Copyright exception notice changed; review required")
    return {"licence": "CC-BY-SA-4.0", "licence_url": LICENCE_URL,
            "basis": "exact source page loads hash-verified Footer.js; no local exception; Jataka English verses are outside named copyright-page exceptions",
            "copyright_notice_default": "CC-BY-SA-3.0 (May 2013)",
            "default_url": "https://creativecommons.org/licenses/by-sa/3.0/",
            "exception_result": "NONE_APPLICABLE_TO_THIS_ENGLISH_TRANSLATION"}


def licence_notice(url: str, original_header: str) -> str:
    return "\n".join([
        "Translated by Ānandajoti Bhikkhu. Publisher: Ancient Buddhist Texts.",
        "Copyright: Ānandajoti Bhikkhu; source supplies no separate copyright year for this verse extraction.",
        f"Source: {url}",
        f"Creative Commons Attribution-ShareAlike 4.0 International: {LICENCE_URL}",
        f"Complete page-footer grant text: Creative Commons Attribution-ShareAlike 4.0 License ({LICENCE_URL}deed.en).",
        "The exact source page loads the pinned ABT Footer.js notice granting CC BY-SA 4.0.",
        f"ABT copyright notice and exceptions: {COPYRIGHT}",
        "Complete general grant text from the May 2013 copyright notice: everything except for those works covered in the listings above, including the introductions, translations, studies, and notes accompanying most of these works are subject to the following licence: Creative Commons Attribution-ShareAlike 3.0 Unported License. attribution should be made to Anandajoti Bhikkhu.",
        "General default licence URL: https://creativecommons.org/licenses/by-sa/3.0/ . The May 2013 copyright notice names a CC BY-SA 3.0 default; the page's explicit 4.0 footer is retained here. The complete exception list is retained in the linked copyright snapshot.",
        "The listed third-party editions and ambiguous BJT/GNU Pali database terms are not relabelled by this extraction.",
        "Changes: canonical verse extraction; HTML inline styling removed; explicit verse line breaks retained; embedded verse notes retained with added Source note labels. Synopsis, word commentary and site navigation are outside the body scope; preserved in source/comparison evidence.",
        "No repeated passages have been expanded or manufactured. Original wording, punctuation and source ellipses remain.",
        "Retain attribution, this notice and source/licence links; identify further changes; share adaptations under the same licence; do not impose additional restrictions. No endorsement is implied.",
        "Original saved TXT attribution and change notice:", original_header,
    ]) + "\n"


def prepare_record(record: dict, archive: Path, repo: Path, out: Path,
                   manifests: dict, evidence_lock: dict) -> tuple[dict, dict]:
    number = int(record["canonical_id"].removeprefix("Ja "))
    name, _ = GROUPS[record["source_group"]]
    manifest = manifests[name]
    entries = [e for e in manifest["texts"] if e["number"] == number]
    if len(entries) != 1:
        raise ValueError("Candidate is absent or duplicated in pinned manifest")
    entry = entries[0]
    slug = record["record_id"].rsplit(":", 1)[1]
    stem = f"ja{number}-{slug}"
    proposal = {k: record[k] for k in ("canonical_id", "collection", "title", "translator", "source_url", "source_group", "record_id")}
    proposal.update(version_slug=slug, licence=None, licence_url=None, copyright=None,
                    licence_notice=None, body_path=None, body_sha256=None,
                    source_sha256=entry["html_sha256"],
                    source_revision="sha256:" + entry["html_sha256"],
                    upstream_file=f"English-Texts/Jataka-Verses/{number:03d}.htm",
                    completeness_status="UNKNOWN", scope="Canonical Jataka verse set only; excludes narrative story and word commentary.",
                    exceptions=[], disposition="HELD")
    proposal.update(prior_record_id=record["record_id"], license=None, license_url=None,
                    license_notice=None, completeness_scope=proposal["scope"],
                    source_snapshot=None, source_comparison="FAIL",
                    source_comparison_method="", source_repository="")
    comparison = {"record_id": record["record_id"], "metadata_licence": "CC0-1.0"}
    try:
        expected_url = BASE + proposal["upstream_file"]
        if record["source_url"] != expected_url:
            raise ValueError("Candidate URL disagrees with canonical source number")
        snapshots = within(archive, manifest["snapshot_dir"])
        source = verified(snapshots / f"ja{number}.html.source", entry["html_sha256"])
        root_bytes = verified(snapshots / f"ja{number}-pali.json", entry["pali_sha256"])
        footer_hash = manifest.get("license_evidence_sha256", manifest.get("snapshot_sha256", {}).get("license-footer.js.source"))
        footer = verified(snapshots / "license-footer.js.source", footer_hash)
        verified(snapshots / "publication-index.html.source", manifest["publication_index_sha256"] if "publication_index_sha256" in manifest else manifest["snapshot_sha256"]["publication-index.html.source"])
        for file, digest in manifest.get("snapshot_sha256", {}).items():
            verified(snapshots / file, digest)
        for key in ("source_audit_report", "variant_audit_report", "audit_report"):
            if manifest.get(key + "_sha256"):
                verified(within(archive, manifest[key]), manifest[key + "_sha256"])
        summary = name == "abt-jataka-summary-variants"
        comparison.update(compare_source(number, source, json.loads(root_bytes), summary=summary))
        variant = bool(comparison["variant_verses"])
        if slug != ("anandajoti-abt-cst4" if variant else "anandajoti-abt"):
            raise ValueError("Edition slug disagrees with independently compared Pali readings")
        for key, observed in (("title", comparison["title"]), ("stanza_count", len(comparison["pairs"])), ("variant_verses", comparison["variant_verses"])):
            if key in entry and entry[key] != observed:
                raise ValueError(f"Source differs from manifest {key}")
        if "trailing_summary_group_count" in entry and entry["trailing_summary_group_count"] != len(comparison["trailing_summary"]):
            raise ValueError("Trailing summary differs from manifest")
        if comparison["title"] != f"Ja {number} {record['title']}":
            raise ValueError("Candidate title differs from source")
        if record["translator"] != manifest["translator"]:
            raise ValueError("Candidate translator differs from source manifest")
        if len(record["historical_local_paths"]) != 1:
            raise ValueError("Expected exactly one saved original TXT")
        original_path = within(archive, record["historical_local_paths"][0])
        original = original_path.read_bytes()
        comparison["original_txt"] = compare_original(original, comparison, variant, expected_url)
        comparison["original_txt"]["path"] = str(original_path.relative_to(archive))
        copyright = verified(out / "evidence/copyright.html", evidence_lock["copyright.html"]["sha256"])
        comparison["rights"] = check_licence(source, footer, copyright, expected_url)
        if sha256(footer) != evidence_lock["footer.js"]["sha256"]:
            raise ValueError("Live and pinned page licence footers differ; review required")
        comparison.update(source_sha256=sha256(source), reference_sha256=sha256(root_bytes),
                          reference_revision=manifest["pali_commit"],
                          source_manifest=f"metadata/source-manifests/{name}.json",
                          source_manifest_sha256=sha256((archive / f"metadata/source-manifests/{name}.json").read_bytes()),
                          verse_count=len(comparison["pairs"]),
                          complete_source_partition=True,
                          coverage="All source paragraphs retained and classified; all target verse blocks paired and compared. Commentary is not represented as canonical verse.")
        body = render_body(comparison, variant).encode("utf-8")
        body_path = out / "bodies" / f"{stem}.txt"
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_bytes(body)
        evidence_dir = out / "sources" / stem
        evidence_dir.mkdir(parents=True, exist_ok=True)
        for filename, data in (("page.html", source), ("reference.json", root_bytes), ("original.txt", original), ("footer.js", footer)):
            (evidence_dir / filename).write_bytes(data)
        exceptions = []
        if variant:
            exceptions.append("Cst4-based Pali alternate readings; same translator and work, not a new translation or Bilara segment alignment.")
        if comparison["trailing_summary"]:
            exceptions.append("Trailing Tassuddana Pali collection summary follows the Jataka colophon; retained in comparison evidence, outside canonical verse body.")
        if any(p["printed_number"] is None for p in comparison["pairs"]):
            exceptions.append("Source stanza is unnumbered; ordinal is editorial metadata and the Pali wording remains unnumbered.")
        if any(p[k]["notes"] for p in comparison["pairs"] for k in ("pali", "english")):
            exceptions.append("Embedded source verse notes omitted by the saved TXT are retained in prepared body and comparison evidence.")
        if comparison["html_repairs"]:
            exceptions.append("Source has an unclosed tooltip in commentary; paragraph boundary closes it with all wording retained in comparison evidence.")
        exceptions.append("Copyright page's 2013 CC BY-SA 3.0 default and page-loaded CC BY-SA 4.0 footer both retained; named third-party exceptions do not cover these English Jataka verses.")
        proposal.update(licence="CC-BY-SA-4.0", licence_url=LICENCE_URL,
                        copyright="Ānandajoti Bhikkhu; source gives no separate copyright year.",
                        licence_notice=licence_notice(expected_url, comparison["original_txt"]["original_header"]),
                        body_path=body_path.relative_to(repo).as_posix(), body_sha256=sha256(body),
                        completeness_status="COMPLETE", disposition="READY", exceptions=exceptions,
                        scope=("Complete canonical Jataka verse set in the ABT Cst4-based edition, with paired source Pali and English; " if variant else "Complete canonical Jataka English verse set; ") +
                              "source verse notes retained; narrative story, synopsis, word commentary and trailing collection index excluded. COMPLETE is for this verse set, not the complete source page or all 547 Jatakas.")
        proposal.update(license=proposal["licence"], license_url=proposal["licence_url"],
                        license_notice=proposal["licence_notice"],
                        completeness_scope=proposal["scope"],
                        source_snapshot=(evidence_dir / "page.html").relative_to(repo).as_posix(),
                        source_comparison="PASS",
                        source_comparison_method=(
                            "Offline prepare_abt_licensed.py: verify original HTML/Pali/footer/index SHA-256 against saved source manifest; "
                            "compare independent complete visible-body character stream with every classified source paragraph, including notes/commentary, ignoring whitespace only; "
                            "require all ordered source Pali/English verse pairs, printed stanza numbers or reviewed unnumbered stanzas, contiguous pinned reference IDs, Jataka colophon and exact trailing Tassuddana scope; "
                            "compare every saved original TXT body character in order against all source verse blocks (whitespace only ignored), then retain all embedded source verse notes and every explicit HTML verse break in prepared body. "
                            "Reference Pali variant comparison uses NFC/lowercase letters and niggahita equivalence; raw complete source/reference wording remains in comparison JSON. "
                            f"Evidence: {(out / 'comparisons' / (stem + '.json')).relative_to(repo).as_posix()}; reference commit {manifest['pali_commit']}. "
                            "Reproduce with python tools/buddhist_canon_pipeline/prepare_abt_licensed.py --candidates build/abt-bulk-20261111/inputs/candidates.json."
                        ))
    except (OSError, ValueError, KeyError, TypeError) as error:
        proposal["exceptions"] = [str(error)]
        comparison["failure"] = str(error)
    comparison_path = out / "comparisons" / f"{stem}.json"
    write_json(comparison_path, comparison)
    proposal["comparison_path"] = comparison_path.relative_to(repo).as_posix()
    # The shared importer uses the American field spellings. Keep one copy of
    # each complete notice/scope; the prior record ID preserves the input key.
    for field in ("licence", "licence_url", "licence_notice", "scope", "record_id"):
        proposal.pop(field, None)
    return proposal, comparison


def inventory_collections(repo: Path, out: Path, lock: dict, *, saved_inputs=False) -> dict:
    if saved_inputs:
        eligible_input = json.loads((out / "inputs/eligible-collections.json").read_text(encoding="utf-8"))
        catalog = json.loads((out / "inputs/site-catalog.json").read_text(encoding="utf-8"))
    else:
        eligible_path = repo / "metadata/eligible-texts.json"
        eligible = json.loads(eligible_path.read_text(encoding="utf-8"))
        eligible_input = {"eligible_input_sha256": sha256(eligible_path.read_bytes()),
                          "collection_counts": dict(Counter(t["collection"] for t in eligible["texts"]))}
        catalog = json.loads((repo / "metadata/site-catalog.json").read_text(encoding="utf-8"))
        write_json(out / "inputs/eligible-collections.json", eligible_input)
        write_json(out / "inputs/site-catalog.json", catalog)
    counts = Counter(eligible_input["collection_counts"])
    names = set(catalog["collection_titles"]) | {f"abhidhamma/{x[0]}" for x in catalog["abhidhamma_books"]}
    empty = sorted(c for c in names if not counts[c])
    # Whole HTML works found in both ABT English and parallel catalogues are
    # useful alternates, but all three already have native English editions.
    whole = [
        {"collection": "khuddaka-nikaya/khuddakapatha", "title": "The Short Readings", "source_url": EVIDENCE_URLS["short-readings.html"], "canonical_units": 9, "evidence": "short-readings.html"},
        {"collection": "khuddaka-nikaya/dhammapada", "title": "Dhamma Verses", "source_url": EVIDENCE_URLS["dhamma-verses.html"], "canonical_units": 423, "evidence": "dhamma-verses.html"},
        {"collection": "khuddaka-nikaya/udana", "title": "Exalted Utterances", "source_url": EVIDENCE_URLS["exalted-utterances.html"], "canonical_units": 80, "evidence": "exalted-utterances.html"},
    ]
    for row in whole:
        row.update(native_format="HTML", translator="Ānandajoti Bhikkhu", licence="CC-BY-SA-4.0 (page-loaded footer; each chapter still requires exact notice check before import)",
                   existing_eligible_versions=counts[row["collection"]], fills_empty_book=False,
                   disposition="ALTERNATE_EDITION_ONLY", evidence_sha256=lock[row["evidence"]]["sha256"])
    partial = [
        {"collection": "abhidhamma/dhammasangani", "scope": "Matrix only (Dhs 1 and 2)"},
        {"collection": "abhidhamma/vibhanga", "scope": "Chapters 6 and 7 only"},
        {"collection": "abhidhamma/patthana", "scope": "Enumeration and explanation of conditions only (1 and 2)"},
        {"collection": "khuddaka-nikaya/apadana", "scope": "Buddhapadana (Ap 1.1), and Why the Buddha Suffered (Ap 39.10 with commentary), not all Apadana",
         "exception": "Barua Buddhapadana page explicitly says copyright holders could not be traced; no redistribution grant established. HELD regardless of generic footer."},
    ]
    return {"metadata_licence": "CC0-1.0", "eligible_input_sha256": eligible_input["eligible_input_sha256"],
            "empty_books": empty, "whole_native_collections": whole,
            "whole_reusable_native_collections_filling_empty_books_found": [],
            "partial_native_sources_not_whole_books": partial,
            "catalogue_evidence": [{"file": f"evidence/{n}", **lock[n]} for n in ("english-index.html", "parallel-index.html", "document-list.html", "buddhapadana.html")],
            "limitation": "Discovery covers saved ABT English, parallel-text and document catalogues, not an assertion that no unpublished translation exists. Pali-only editions and Reference/PTS PDFs are not reusable whole English HTML/TXT collections."}


def run(repo: Path, archive: Path, out: Path, candidates_path: Path | None = None) -> dict:
    repo, archive, out = repo.resolve(), archive.resolve(), out.resolve()
    if not out.is_relative_to(repo / "build/abt-bulk-20261111"):
        raise ValueError("Output must stay inside ignored build/abt-bulk-20261111/")
    excluded_path = candidates_path or repo / "metadata/excluded-sources.json"
    excluded = json.loads(excluded_path.read_text(encoding="utf-8"))
    candidates = [r for r in excluded["text_versions"] if r.get("source_group") in GROUPS]
    expected = {g: count for g, (_, count) in GROUPS.items()}
    if Counter(r["source_group"] for r in candidates) != Counter(expected):
        raise ValueError("Expected all 287 candidates in the three approved ABT source groups")
    if len({r["record_id"] for r in candidates}) != 287 or len({r["canonical_id"] for r in candidates}) != 287:
        raise ValueError("Duplicate ABT candidate record or canonical number")
    evidence_lock = load_evidence(out)
    if candidates_path is None:
        write_json(out / "inputs/candidates.json", {"metadata_licence": "CC0-1.0", "original_excluded_input_sha256": sha256(excluded_path.read_bytes()), "text_versions": candidates})
    manifests = {}
    for name, _ in GROUPS.values():
        path = archive / f"metadata/source-manifests/{name}.json"
        manifests[name] = json.loads(path.read_text(encoding="utf-8"))
        if len({t["number"] for t in manifests[name]["texts"]}) != len(manifests[name]["texts"]):
            raise ValueError("Duplicate manifest source number")
        dest = out / "manifests" / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())
    proposals, comparisons = [], []
    for record in sorted(candidates, key=lambda r: (int(r["canonical_id"].split()[1]), r["record_id"])):
        proposal, comparison = prepare_record(record, archive, repo, out, manifests, evidence_lock)
        proposals.append(proposal)
        comparisons.append(comparison)
    (out / "proposals.jsonl").write_text("".join(compact(p) + "\n" for p in proposals), encoding="utf-8")
    ready = [p for p in proposals if p["disposition"] == "READY"]
    held = [p for p in proposals if p["disposition"] == "HELD"]
    write_json(out / "proposal.json", {"schema_version": 1, "metadata_license": "CC0-1.0",
                                      "source_comparison_method": "Full per-record comparison retained in comparisons/; see each record's source_comparison_method.",
                                      "records": ready, "held_count": len(held),
                                      "all_candidate_count": len(proposals)})
    write_json(out / "held.json", held)
    inventory = inventory_collections(repo, out, evidence_lock, saved_inputs=candidates_path is not None)
    write_json(out / "native-collections.json", inventory)
    summary = {"metadata_licence": "CC0-1.0", "code_licence": "0BSD", "text_licence": "per-record licence; no CC0 relicensing",
               "candidate_count": len(proposals), "ready": len(ready), "held": len(held),
               "groups": {g: {"total": sum(p["source_group"] == g for p in proposals), "ready": sum(p["source_group"] == g for p in ready)} for g in GROUPS},
               "verse_pairs": sum(c.get("verse_count", 0) for c in comparisons),
               "pali_matched_sets": sum(p["version_slug"] == "anandajoti-abt" for p in ready),
               "pali_variant_sets": sum(p["version_slug"] == "anandajoti-abt-cst4" for p in ready),
               "sets_with_source_verse_notes": sum(any(pair[k]["notes"] for pair in c.get("pairs", []) for k in ("pali", "english")) for c in comparisons),
               "source_verse_notes": sum(len(pair[k]["notes"]) for c in comparisons for pair in c.get("pairs", []) for k in ("pali", "english")),
               "excluded_input_sha256": excluded.get("original_excluded_input_sha256", sha256(excluded_path.read_bytes())),
               "proposals_sha256": sha256((out / "proposals.jsonl").read_bytes()),
               "import_proposal_sha256": sha256((out / "proposal.json").read_bytes()),
               "held_reasons": dict(Counter(e for p in held for e in p["exceptions"])),
               "whole_native_empty_book_additions": 0}
    write_json(out / "summary.json", summary)
    report = f"""# ABT preparation, 2026-11-11

Metadata and this handoff: CC0-1.0. Preparer/tests: 0BSD. Text keeps its original licence.

- All 287 excluded ABT Jataka candidate records processed: {len(ready)} ready, {len(held)} held.
- Complete verse sets: {summary['pali_matched_sets']} matching pinned Pali;
  {summary['pali_variant_sets']} with Cst4-based alternate readings.
- {summary['verse_pairs']} Pali/English verse pairs checked in source order, with numbering,
  canonical colophons and all trailing reference material accounted for.
- {summary['source_verse_notes']} embedded verse notes in
  {summary['sets_with_source_verse_notes']} sets preserved, including notes absent in old TXT.
- Body completeness applies to the complete canonical verse set. It does not mean
  complete narrative story, source-page commentary, or all 547 Jatakas.

## Integration

1. Import proposal.json with the main agent's import_licensed_batches.py. Its
   records contain only READY/PASS entries. proposals.jsonl retains every candidate,
   including held entries. Each record contains the
   requested attribution, complete licence/change notice, exact source pin,
   UTF-8 body_path, hashes, scope, exceptions and comparison_path.
2. Verify body_sha256 before copying to the intended tracked translation path.
   Use canonical_id and version_slug as edition identity; Cst4 variants are the
   same English translator with a different Pali basis, not new translations.
3. license/license_url/license_notice and completeness_scope match the importer
   contract directly; prior_record_id preserves the exact excluded-source identity.
   Preserve license_notice and copyright in each reader/TXT and retain linked
   comparison/source evidence. Do not mark these texts CC0 or public domain.
4. Add exact paths/hashes/rights to shared metadata and allowlists through the
   main integration agent, then run its reader/build/validator checks. This batch
   does not change those shared files, stage, commit or deploy anything.
5. Held records and reasons are in held.json. Never integrate a stale body file
   using a HELD proposal; only current READY proposals authorize body consumption.

Main integration command (the preparation agent does not run it in the shared tree):

    python tools/buddhist_canon_pipeline/import_licensed_batches.py --proposal build/abt-bulk-20261111/proposal.json

## Reproduce

Run from the freebuddhism root (offline after evidence capture):

    python tools/buddhist_canon_pipeline/prepare_abt_licensed.py
    python -m unittest discover -s tests -p test_abt_licensed.py

Use --archive-root to select the saved Buddhism repository. Use --refresh-evidence
explicitly to replace the website evidence lock; otherwise no network is used.
After shared exclusions change, use --candidates build/abt-bulk-20261111/inputs/candidates.json
to reproduce the original complete 287-record scope. The preparer always enforces
the full 134/124/29 group counts and all unique canonical/source record identities.
Saved original TXT, HTML and Pali JSON are compared against source-manifest hashes.
All original body characters must match the source extraction, ignoring whitespace
only. Source notes and formatting differences are recorded separately.
The frozen candidate input and collection-count/catalogue inputs preserve the
reviewed batch and empty-book assessment when shared metadata later changes.
Each comparison JSON preserves every source paragraph, its classification, verse
line breaks, note text and complete reference segments, colophons and summaries.
The comparison JSON contains licensed source text: its metadata is CC0, its text is not.

The tests exercise all 287 proposals through the actual shared importer in an
isolated temporary tree: complete notices in wrapped TXT, exact raw snapshots,
hash checks and repeat-import behavior. They also test full source partitioning,
verse/line numbering, embedded notes, Pali edition differences, changed sources,
licence exceptions, and deterministic offline regeneration. This does not replace
the main agent's complete public reader/build/validator checks after integration.

## Rights and exact exceptions

The page-loaded, pinned Footer.js expressly gives CC BY-SA 4.0. ABT's copyright
page gives an older May 2013 CC BY-SA 3.0 default. Both notices are retained; these
Jataka English verses are outside its named third-party exceptions. Every saved
source page must load that footer and have no conflicting local rights notice.

Copyright exceptions are not swept into the footer licence: PTS editions by
Geiger, Malalasekera and Cone; Brough's Gandhari edition; Bernard's Udanavarga;
Norman, Edgerton and Warder articles; and ambiguous BJT/GNU Pali database terms.
The exact full notice is pinned in evidence/copyright.html; page notices remain
in sources/. No ND work is admitted by this preparer.

https://ancient-buddhist-texts.net/Miscellaneous/Copyright-Notice.htm
https://ancient-buddhist-texts.net/includes/Footer.js

## Whole native collections and empty books

No whole reusable ABT English HTML/TXT collection filling an empty book was found
in the English, parallel-text and document catalogues. Khuddakapatha, Dhammapada
and Udana are whole native HTML alternatives, but already have eligible text.
Abhidhamma sources cover selected sections, and the Apadana sources are excerpts.
Barua's Buddhapadana page explicitly reports untraced copyright holders: HELD,
regardless of the generic footer. Reference/PTS PDF availability is not a licence
grant. native-collections.json records catalogue evidence and actual empty books.

https://ancient-buddhist-texts.net/English-Texts/index.htm
https://ancient-buddhist-texts.net/Texts-and-Translations/index.htm
https://ancient-buddhist-texts.net/Miscellaneous/Document-List.htm
https://ancient-buddhist-texts.net/English-Texts/Short-Pieces-in-English/Buddhapadana.htm
"""
    (out / "CURRENT.md").write_text(report, encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, default=REPO.parent / "buddhism")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--refresh-evidence", action="store_true")
    parser.add_argument("--candidates", type=Path, help="Saved candidates.json after shared exclusions change")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(DEFAULT_OUT):
        parser.error("Output must be inside build/abt-bulk-20261111/")
    if args.refresh_evidence:
        refresh_evidence(output)
    print(compact(run(REPO, args.archive_root, output, args.candidates)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
