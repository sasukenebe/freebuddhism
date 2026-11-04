#!/usr/bin/env python3
"""Import the complete 547-story Cowell Jataka edition from pinned source HTML."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_FIELDS = (
    "canonical_id",
    "collection_path",
    "txt_path",
    "label",
    "version_label",
    "source_url",
    "license",
    "source_commit",
    "upstream_file",
)

REPOSITORY = "suttacentral/sc-data"
SOURCE_PATH = "html_text/en/pli/sutta/kn/ja"
API_ROOT = f"https://api.github.com/repos/{REPOSITORY}"
LOCK_PATH = Path("metadata/source-manifests/cowell-jataka.json")
OUTPUT_DIR = Path("theravada/tipitaka/translations/en/cowell/jataka-commentary")
LEDGER_PATH = Path("theravada/tipitaka/sutta/cowell-jataka-text-ledger.tsv")
LICENSE = "Public Domain (original English edition, published 1895–1907)"
VERSION_LABEL = "Cowell et al. — Jātaka commentary narratives"
VOLUMES = (
    {"number": 1, "start": 1, "end": 150, "translator": "Robert Chalmers", "author": "Robert Chalmers", "year": 1895},
    {"number": 2, "start": 151, "end": 300, "translator": "W. H. D. Rouse", "author": "W.H.D. Rouse", "year": 1895},
    {"number": 3, "start": 301, "end": 438, "translator": "H. T. Francis and R. A. Neil", "author": "H.T. Francis, R.A. Neil", "year": 1897},
    {"number": 4, "start": 439, "end": 510, "translator": "W. H. D. Rouse", "author": "W.H.D. Rouse", "year": 1901},
    {"number": 5, "start": 511, "end": 537, "translator": "H. T. Francis", "author": "H.T. Francis", "year": 1905},
    {"number": 6, "start": 538, "end": 547, "translator": "E. B. Cowell and W. H. D. Rouse", "author": "E.B. Cowell, W.H.D. Rouse", "year": 1907},
)
SMITHSONIAN_RIGHTS_URLS = [
    "https://library.si.edu/digital-library/book/jaytaka1chal",
    "https://library.si.edu/digital-library/book/jaytaka3chal",
    "https://library.si.edu/digital-library/book/jaytaka4chal",
    "https://library.si.edu/digital-library/book/jaytaka5chal",
    "https://library.si.edu/digital-library/book/jaytaka6chal",
    "https://library.si.edu/digital-library/book/jaytaka00chal",
]
SUTTACENTRAL_PD_EVIDENCE_URLS = [
    "https://suttacentral.net/ja1/en/chalmers",
    "https://suttacentral.net/ja457/en/rouse",
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> bytes:
    request = Request(url, headers={
        "User-Agent": "buddhism-text-corpus/1.0 (source preservation; see repository README)",
        "Accept": "application/vnd.github+json, text/html, application/json, */*",
    })
    for attempt in range(5):
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError):
            if attempt == 4:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise AssertionError("unreachable")


def latest_commit() -> str:
    data = json.loads(fetch(f"{API_ROOT}/commits/main"))
    commit = data.get("sha", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Could not resolve a full SuttaCentral sc-data commit")
    return commit


def index_url(volume: int, commit: str) -> str:
    path = quote(f"{SOURCE_PATH}/vol{volume}", safe="/")
    return f"{API_ROOT}/contents/{path}?ref={commit}"


def raw_url(relative_path: str, commit: str) -> str:
    return f"https://raw.githubusercontent.com/{REPOSITORY}/{commit}/{relative_path}"


def parse_volume_index(data: bytes, volume: dict) -> list[str]:
    listing = json.loads(data)
    if not isinstance(listing, list):
        raise ValueError(f"Volume {volume['number']} source index is not a file list")
    names = {item.get("name") for item in listing if item.get("type") == "file"}
    expected = {f"ja{number}.html" for number in range(volume["start"], volume["end"] + 1)}
    if names != expected:
        missing = sorted(expected - names)
        unexpected = sorted(names - expected)
        raise ValueError(f"Volume {volume['number']} source-file mismatch; missing={missing[:8]}, unexpected={unexpected[:8]}")
    return [f"{SOURCE_PATH}/vol{volume['number']}/ja{number}.html"
            for number in range(volume["start"], volume["end"] + 1)]


def load_sources(lock: dict | None, commit_override: str | None) -> tuple[str, dict[int, tuple[str, bytes]], dict[int, bytes]]:
    if commit_override and not re.fullmatch(r"[0-9a-f]{40}", commit_override):
        raise ValueError("--source-commit must be a full 40-character Git commit")
    if lock and commit_override and commit_override != lock["source_commit"]:
        raise ValueError("--source-commit differs from the existing manifest; audit before changing the lock")
    commit = lock["source_commit"] if lock else commit_override or latest_commit()
    old_by_number = {entry["number"]: entry for entry in lock["texts"]} if lock else {}
    old_volumes = {entry["number"]: entry for entry in lock["volume_indexes"]} if lock else {}
    indexes: dict[int, bytes] = {}
    paths: dict[int, str] = {}

    for volume in VOLUMES:
        number = volume["number"]
        url = index_url(number, commit)
        data = fetch(url)
        if lock and sha256(data) != old_volumes[number]["index_sha256"]:
            raise ValueError(f"Volume {number} source listing changed from its locked hash")
        for relative_path in parse_volume_index(data, volume):
            match = re.fullmatch(re.escape(SOURCE_PATH) + r"/vol(\d+)/ja(\d+)\.html", relative_path)
            assert match
            paths[int(match.group(2))] = relative_path
        indexes[number] = data

    expected_numbers = set(range(1, 548))
    if set(paths) != expected_numbers:
        raise ValueError("Pinned SuttaCentral volume listings do not cover Ja 1–547 exactly")

    def load_one(number: int) -> tuple[int, bytes]:
        relative_path = paths[number]
        data = fetch(raw_url(relative_path, commit))
        if lock and sha256(data) != old_by_number[number]["sha256"]:
            raise ValueError(f"Pinned source changed for Ja {number}")
        return number, data

    sources: dict[int, tuple[str, bytes]] = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        pending = {pool.submit(load_one, number): number for number in range(1, 548)}
        errors: list[str] = []
        for future in as_completed(pending):
            number = pending[future]
            try:
                _number, data = future.result()
                sources[number] = (raw_url(paths[number], commit), data)
                if len(sources) % 100 == 0:
                    print(f"Fetched {len(sources)}/547 pinned Jātaka source pages", file=sys.stderr)
            except Exception as error:
                errors.append(f"Ja {number}: {error}")
    if errors:
        raise ValueError("Source download errors:\n" + "\n".join(errors))
    return commit, sources, indexes


class StoryParser(HTMLParser):
    BLOCKS = {"p", "h2", "h3", "h4", "h5", "h6", "blockquote", "li", "div", "br", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.article_id: int | None = None
        self.article_open = False
        self.article_closed = False
        self.header_open = False
        self.h1_open = False
        self.title_parts: list[str] = []
        self.author = ""
        self.paragraphs = 0
        self.parts: list[str] = []

    def _newline(self) -> None:
        if self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "meta" and attr.get("name", "").lower() == "author":
            self.author = (attr.get("content") or "").strip()
        if tag == "article":
            if self.article_open:
                raise ValueError("Nested article element in source HTML")
            match = re.fullmatch(r"ja(\d+)", attr.get("id") or "")
            self.article_id = int(match.group(1)) if match else None
            self.article_open = True
            return
        if not self.article_open:
            return
        if tag == "header":
            self.header_open = True
            return
        if self.header_open:
            if tag == "h1":
                self.h1_open = True
                self.title_parts = []
            return
        if tag == "p":
            self.paragraphs += 1
        if tag in self.BLOCKS:
            self._newline()

    def handle_endtag(self, tag: str) -> None:
        if tag == "article" and self.article_open:
            self._newline()
            self.article_open = False
            self.article_closed = True
            return
        if not self.article_open:
            return
        if tag == "h1":
            self.h1_open = False
        if tag == "header":
            self.header_open = False
        if not self.header_open and tag in self.BLOCKS:
            self._newline()

    def handle_data(self, data: str) -> None:
        if not self.article_open:
            return
        if self.header_open:
            if self.h1_open:
                self.title_parts.append(data)
            return
        self.parts.append(data)

    @property
    def title(self) -> str:
        title = re.sub(r"\s+", " ", "".join(self.title_parts)).strip()
        return re.sub(r"^\d+\.\s*", "", title)

    @property
    def text(self) -> str:
        raw = "".join(self.parts).replace("\r\n", "\n").replace("\r", "\n")
        lines = [re.sub(r"[\t\xa0 ]+", " ", line).strip() for line in raw.split("\n")]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def volume_for(number: int) -> dict:
    for volume in VOLUMES:
        if volume["start"] <= number <= volume["end"]:
            return volume
    raise ValueError(f"Jātaka number out of range: {number}")


def validate_sources(sources: dict[int, tuple[str, bytes]], lock: dict | None) -> tuple[list[dict], dict[int, str]]:
    if set(sources) != set(range(1, 548)):
        raise ValueError("Expected exactly one source page for every Ja 1–547")
    old_by_number = {entry["number"]: entry for entry in lock["texts"]} if lock else {}
    entries: list[dict] = []
    bodies: dict[int, str] = {}
    for number in range(1, 548):
        url, data = sources[number]
        if not data.lstrip().lower().startswith((b"<!doctype html", b"<html")):
            raise ValueError(f"Source is not an HTML page: Ja {number}")
        parser = StoryParser()
        parser.feed(data.decode("utf-8", errors="strict"))
        parser.close()
        title, body = parser.title, parser.text
        volume = volume_for(number)
        digest = sha256(data)
        if lock and old_by_number[number]["sha256"] != digest:
            raise ValueError(f"Source checksum changed for Ja {number}")
        if (not parser.article_closed or parser.article_id != number or not title
                or not re.search(r"Jātaka|Jataka|Pañha|Panha", title, re.I)
                or parser.author != volume["author"]
                or parser.paragraphs == 0 or len(body) < 30):
            raise ValueError(
                f"Incomplete or misidentified source article Ja {number}: "
                f"article={parser.article_id}, title={title!r}, author={parser.author!r}, "
                f"paragraphs={parser.paragraphs}, body_chars={len(body)}"
            )
        entries.append({
            "number": number,
            "title": title,
            "volume": volume["number"],
            "translator": volume["translator"],
            "publication_year": volume["year"],
            "source_url": url,
            "source_path": f"{SOURCE_PATH}/vol{volume['number']}/ja{number}.html",
            "sha256": digest,
            "paragraphs": parser.paragraphs,
            "body_characters": len(body),
        })
        bodies[number] = body
    return entries, bodies


def make_text(entry: dict, body: str, commit: str, *, legacy_markers: bool = False) -> bytes:
    number = entry["number"]
    volume = entry["volume"]
    source_commit_url = f"https://github.com/{REPOSITORY}/commit/{commit}"
    if not legacy_markers:
        body = re.sub(r"\bPTS vp (?:Pali|En) \d+\b", "", body)
        body = re.sub(r"[ \t]{2,}", " ", body)
        body = re.sub(r"[ \t]+$", "", body, flags=re.MULTILINE)
    lines = [
        f"Ja {number}: {entry['title']}",
        f"Translated by {entry['translator']}",
        "Edited by E. B. Cowell",
        f"Original edition: Cambridge University Press, volume {volume}, {entry['publication_year']}",
        f"Source HTML: {entry['source_url']}",
        f"Pinned source revision: {source_commit_url}",
        f"License: {LICENSE}",
        "Scope: Complete numbered source article from the traditional Jātaka commentary; canonical verses appear in story context. This is not a verse-only edition.",
        ("Changes: Converted the pinned SuttaCentral HTML article to plain text; normalized whitespace only."
         if legacy_markers else
         "Changes: Converted the pinned SuttaCentral HTML article to plain text; removed inline print page-reference labels and normalized whitespace. The original source retains references."),
        "",
        body,
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def write_if_new(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Refusing to overwrite different existing content: {path.relative_to(REPO_ROOT)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def make_manifest(commit: str, indexes: dict[int, bytes], entries: list[dict]) -> dict:
    return {
        "name": "Cowell et al. complete English Jātaka commentary translation",
        "source_repository": f"https://github.com/{REPOSITORY}",
        "source_commit": commit,
        "source_commit_url": f"https://github.com/{REPOSITORY}/commit/{commit}",
        "source_path": SOURCE_PATH,
        "source_edition": "E. B. Cowell (ed.), The Jātaka: or Stories of the Buddha’s Former Births, translated by Robert Chalmers, W. H. D. Rouse, H. T. Francis, and R. A. Neil, Cambridge University Press, volumes I–VI, 1895–1907.",
        "license": LICENSE,
        "license_evidence": {
            "basis": "The original printed translations were published in 1895–1907. Smithsonian Libraries marks its digitized Cowell volumes as No Copyright—United States and states that the works are public domain and may be copied, modified, and distributed. SuttaCentral identifies the legacy Cowell story translations and states that they are public domain.",
            "smithsonian_rights_urls": SMITHSONIAN_RIGHTS_URLS,
            "suttacentral_translation_urls": SUTTACENTRAL_PD_EVIDENCE_URLS,
            "scope_note": "Rights apply to the original published translation. This import preserves attribution and source links; no modern commentary or newly translated text is added.",
        },
        "scope": "All 547 numbered Jātaka articles across six volumes, imported as complete source units. These are commentary-story translations with canonical verses in context, not verse-only translations.",
        "audited": date.today().isoformat(),
        "output_dir": OUTPUT_DIR.as_posix(),
        "ledger": LEDGER_PATH.as_posix(),
        "volume_indexes": [
            {
                "number": volume["number"],
                "start": volume["start"],
                "end": volume["end"],
                "translator": volume["translator"],
                "publication_year": volume["year"],
                "index_url": index_url(volume["number"], commit),
                "index_sha256": sha256(indexes[volume["number"]]),
            }
            for volume in VOLUMES
        ],
        "texts": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Fetch pinned sources, verify hashes, and compare every output without writing files")
    parser.add_argument("--refresh-texts", action="store_true", help="Replace only verified previous text outputs with cleaned reading text")
    parser.add_argument("--source-commit", help="Pin a full SuttaCentral sc-data Git commit for the first import")
    args = parser.parse_args()
    lock_file = REPO_ROOT / LOCK_PATH
    lock = json.loads(lock_file.read_text(encoding="utf-8")) if lock_file.exists() else None
    commit, sources, indexes = load_sources(lock, args.source_commit)
    entries, bodies = validate_sources(sources, lock)
    manifest = make_manifest(commit, indexes, entries) if not lock else lock

    volumes = {volume["number"]: volume for volume in VOLUMES}
    rows = []
    for entry in entries:
        number = entry["number"]
        rows.append({
            "canonical_id": f"Ja {number}",
            "collection_path": "khuddaka-nikaya/jataka",
            "txt_path": (OUTPUT_DIR / f"ja{number}.txt").as_posix(),
            "label": entry["title"],
            "version_label": VERSION_LABEL,
            "source_url": entry["source_url"],
            "license": LICENSE,
            "source_commit": commit,
            "upstream_file": entry["source_path"],
            "version_slug": "cowell-jataka",
        })
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=(*LEDGER_FIELDS, "version_slug"),
                            dialect="excel-tab", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    planned: dict[Path, bytes] = {REPO_ROOT / LEDGER_PATH: buffer.getvalue().encode("utf-8")}
    for entry in entries:
        planned[REPO_ROOT / OUTPUT_DIR / f"ja{entry['number']}.txt"] = make_text(entry, bodies[entry["number"]], commit)
    planned[lock_file] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    total_chars = sum(entry["body_characters"] for entry in entries)
    short_entries = [entry["number"] for entry in entries if entry["body_characters"] < 250]
    if args.check_only:
        mismatches = [str(path.relative_to(REPO_ROOT)) for path, expected in planned.items()
                      if not path.is_file() or path.read_bytes() != expected]
        if mismatches:
            raise ValueError("Generated Cowell outputs differ from the checked-in files:\n" + "\n".join(mismatches[:30]))
        print(f"Validated {len(entries)} complete source articles across {len(volumes)} volumes; {len(short_entries)} source units are under 250 characters; {total_chars:,} translated body characters.")
        if short_entries:
            print("Short source units retained as published: " + ", ".join(f"Ja {number}" for number in short_entries))
        return

    legacy = {REPO_ROOT / OUTPUT_DIR / f"ja{entry['number']}.txt":
              make_text(entry, bodies[entry["number"]], commit, legacy_markers=True)
              for entry in entries}
    conflicts = [path for path, data in planned.items() if path.exists() and path.read_bytes() != data
                 and not (args.refresh_texts and path in legacy and path.read_bytes() == legacy[path])]
    if conflicts:
        raise ValueError("Refusing to overwrite different existing content:\n" +
                         "\n".join(str(path.relative_to(REPO_ROOT)) for path in conflicts[:30]))
    for path, data in planned.items():
        if args.refresh_texts and path in legacy and path.exists() and path.read_bytes() == legacy[path]:
            path.write_bytes(data)
        else:
            write_if_new(path, data)
    print(f"Imported all {len(rows)} Cowell Jātaka source articles (Ja 1–547) from six pinned volumes; {len(short_entries)} brief source units retained; {total_chars:,} translated body characters.")


if __name__ == "__main__":
    main()
