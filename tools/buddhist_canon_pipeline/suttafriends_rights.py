# SPDX-License-Identifier: 0BSD
"""Check individual article preservation, publisher numbering and export limits."""
from __future__ import annotations

import hashlib
from html import unescape
import re
import subprocess
from pathlib import Path

try:
    from .distribution_policy import (INDIVIDUAL_LICENSE, INDIVIDUAL_TERMS,
                                     INDIVIDUAL_CONDITIONS, distribution)
    from .prepare_suttafriends import article, COUNTS, MANIFEST_SHA256, publisher_citation_matches
except ImportError:
    from distribution_policy import (INDIVIDUAL_LICENSE, INDIVIDUAL_TERMS,
                                     INDIVIDUAL_CONDITIONS, distribution)
    from prepare_suttafriends import article, COUNTS, MANIFEST_SHA256, publisher_citation_matches

ARTICLE_DIRECTORY = "metadata/source-snapshots/suttafriends-individual/"
TEXT_DIRECTORY = "theravada/tipitaka/translations/en/licensed/suttafriends/"
EXPORT_RULES = ("/" + ARTICLE_DIRECTORY + "** export-ignore",
                "/" + TEXT_DIRECTORY + "** export-ignore")
RIGHTS_URL = "https://suttafriends.org/copyright/"
NOTICE_SOURCE_SHA256 = "b0fcb5f9a759f5763a5d35803b54b1f382d46b974f2f9a2e49f45f259ab2783b"


def verify_record(record: dict, root: Path) -> None:
    try:
        from .publication_rights import checked_path, sha256
    except ImportError:
        from publication_rights import checked_path, sha256
    if (record["license"] != INDIVIDUAL_LICENSE or record["license_notice"] != INDIVIDUAL_TERMS
            or record["copyright"] != "© Mahamevnawa Buddhist Monastery"
            or record["license_url"] != RIGHTS_URL or record["conditions"] != INDIVIDUAL_CONDITIONS
            or record.get("explicit_grant") != INDIVIDUAL_TERMS
            or record.get("permission_source_sha256") != NOTICE_SOURCE_SHA256
            or record.get("preparation_manifest_sha256") != MANIFEST_SHA256):
        raise ValueError("Individual Sutta Friends grant/notice changed")
    distribution(record)
    match = re.fullmatch(r"(Vv|Pv) ([1-9][0-9]*)", record["canonical_id"])
    if not match:
        raise ValueError("Unexpected individual article identifier")
    prefix, number = match[1].lower(), int(match[2])
    chapter, item = 1, number
    for count in COUNTS[prefix]:
        if item <= count: break
        item -= count
        chapter += 1
    if chapter > len(COUNTS[prefix]):
        raise ValueError("Article number exceeds the publisher chapter inventory")
    publisher = f"{match[1]} {chapter}.{item}"
    url = f"https://suttafriends.org/sutta/{prefix}{chapter}-{item}/"
    mapping = record.get("mapping_evidence", {})
    if (record["source_url"] != url or mapping.get("publisher_id") != publisher
            or mapping.get("method") != "Publisher chapter/flat numbering concordance"
            or not record.get("pali_title")
            or not re.fullmatch(r"[0-9a-f]{64}", record.get("source_page_sha256", ""))
            or not re.fullmatch(r"[0-9a-f]{64}", record.get("pali_source_sha256", ""))):
        raise ValueError("Individual article lacks its pinned publisher/reference correspondence")
    for key, directory in (("source_snapshot", ARTICLE_DIRECTORY), ("local_path", TEXT_DIRECTORY)):
        if not record[key].startswith(directory):
            raise ValueError("Individual-sharing source is outside its export-excluded directory")
    snapshot = checked_path(root, record["source_snapshot"])
    if sha256(snapshot) != record["source_sha256"]:
        raise ValueError("Individual source fragment changed")
    raw = snapshot.read_bytes()
    heading = re.fullmatch(r'<h1>(.*?)</h1>\n(<div class="entry-content">[\s\S]*</div><!-- .entry-content -->)\n', raw.decode())
    if not heading or not publisher_citation_matches(publisher, unescape(heading[1])):
        raise ValueError("Individual source must contain only its publisher heading and complete article")
    body, _ = article(raw)
    if hashlib.sha256(body.encode()).hexdigest() != record["body_sha256"]:
        raise ValueError("Individual article differs from its complete source region")


def verify_source_exports(records: list[dict], root: Path) -> None:
    limited = [row for row in records if row["license"] == INDIVIDUAL_LICENSE]
    if not limited:
        return
    attributes = root / ".gitattributes"
    if attributes.is_symlink() or not attributes.is_file():
        raise ValueError("Individual-sharing texts need committed source-export exclusions")
    lines = attributes.read_text().splitlines()
    if any(rule not in lines for rule in EXPORT_RULES):
        raise ValueError("Individual-sharing source export exclusion is missing")
    paths = [row[key] for row in limited for key in ("local_path", "source_snapshot")]
    result = subprocess.check_output(["git", "check-attr", "-z", "--stdin", "export-ignore"],
                                     cwd=root, input=("\0".join(paths) + "\0").encode())
    fields = result.decode().rstrip("\0").split("\0")
    if len(fields) != len(paths) * 3 or any(fields[i + 2] != "set" for i in range(0, len(fields), 3)):
        raise ValueError("A source-export rule overrides an individual article exclusion")
