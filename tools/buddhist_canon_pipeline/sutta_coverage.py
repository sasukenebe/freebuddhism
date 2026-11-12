# SPDX-License-Identifier: 0BSD
"""Inventory pinned Sutta Piṭaka reference units independently of existing readers.

This reports identifier coverage, not translation quality or semantic clearance.
Range expansion is only a numbering operation; it never creates translated text.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "metadata/sutta-reference-units.json"
PRIORITIES = ROOT / "metadata/sutta-coverage-priorities.json"
EDITIONS = ROOT / "metadata/reports/translation-coverage-2026-11-11.json"
REPORT = ROOT / "metadata/reports/sutta-coverage-current.json"
GAPS = ROOT / "metadata/reports/sutta-gaps-current.csv"
PREFIX = "root/pli/ms/sutta/"
REPOSITORY = "https://github.com/suttacentral/bilara-data"
COLLECTIONS = {
    "dn": "digha-nikaya", "mn": "majjhima-nikaya", "sn": "samyutta-nikaya", "an": "anguttara-nikaya",
    **{"kn/" + key: "khuddaka-nikaya/" + value for key, value in {
        "kp": "khuddakapatha", "dhp": "dhammapada", "ud": "udana", "iti": "itivuttaka",
        "snp": "sutta-nipata", "vv": "vimanavatthu", "pv": "petavatthu", "thag": "theragatha",
        "thig": "therigatha", "ja": "jataka", "mnd": "niddesa", "cnd": "niddesa",
        "ps": "patisambhidamagga", "tha-ap": "apadana", "thi-ap": "apadana", "bv": "buddhavamsa",
        "cp": "cariyapitaka", "mil": "milindapanha", "ne": "nettipakarana", "pe": "petakopadesa",
    }.items()},
}


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def atoms(identifier: str) -> set[str]:
    match = re.fullmatch(r"([A-Za-z][A-Za-z -]*?)\s*(\d+(?:\.\d+)*(?:[-–]\d+)?)", identifier.strip())
    if not match:
        return set()
    prefix = re.sub(r"[ -]", "", match[1]).lower()
    prefix = {"khp": "kp"}.get(prefix, prefix)
    interval = match[2].replace("–", "-").split("-")
    numbers = [int(number) for number in interval[0].split(".")]
    first, last = numbers[-1], int(interval[1]) if len(interval) == 2 else numbers[-1]
    if last < first or last - first > 10000:
        raise ValueError("Invalid or unbounded reference range: " + identifier)
    parent = ".".join(map(str, numbers[:-1]))
    return {prefix + (parent + "." if parent else "") + str(number) for number in range(first, last + 1)}


def capture_reference(repository: Path, revision: str) -> dict:
    commit = subprocess.check_output(["git", "rev-parse", revision + "^{commit}"], cwd=repository, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", commit + ":root/pli/ms/sutta"], cwd=repository, text=True).strip()
    raw = subprocess.check_output(["git", "ls-tree", "-r", commit, "--", PREFIX], cwd=repository, text=True)
    units = []
    seen = set()
    for line in raw.splitlines():
        metadata, path = line.split("\t")
        mode, kind, blob = metadata.split()
        if mode != "100644" or kind != "blob" or not re.fullmatch(r"[0-9a-f]{40}", blob):
            raise ValueError("Unexpected reference tree entry")
        tail = path.removeprefix(PREFIX)
        parts = tail.split("/")
        key = "/".join(parts[:2]) if parts[0] == "kn" else parts[0]
        if key not in COLLECTIONS or not path.endswith("_root-pli-ms.json"):
            raise ValueError("Unreviewed Sutta reference path: " + path)
        identifier = parts[-1].removesuffix("_root-pli-ms.json")
        if not atoms(identifier) or identifier in seen:
            raise ValueError("Missing or duplicate reference ID: " + identifier)
        seen.add(identifier)
        units.append({"id": identifier, "collection": COLLECTIONS[key], "path": path, "git_blob": blob})
    present = {("kn/" + r["path"].split(PREFIX, 1)[1].split("/")[1])
               if "/kn/" in r["path"] else r["path"].split(PREFIX, 1)[1].split("/")[0] for r in units}
    if present != set(COLLECTIONS):
        raise ValueError("Reference tree omits an expected book; do not silently drop empty collections")
    return {"schema_version": 1, "repository": REPOSITORY, "commit": commit, "sutta_tree": tree,
            "scope": "All root/pli/ms/sutta JSON units at this revision, including broad Khuddaka scope; grouped units remain explicit. Not a universal count across traditions.",
            "unit_count": len(units), "units": units}


def validate_reference(reference: dict) -> None:
    if (reference.get("repository") != REPOSITORY or reference.get("schema_version") != 1
            or reference.get("unit_count") != len(reference["units"])
            or not re.fullmatch(r"[0-9a-f]{40}", reference.get("commit", ""))
            or not re.fullmatch(r"[0-9a-f]{40}", reference.get("sutta_tree", ""))):
        raise ValueError("Reference inventory is not pinned to a complete Git source tree")
    families, paths, identifiers = set(), set(), set()
    for row in reference["units"]:
        path = row["path"]
        if not path.startswith(PREFIX) or ".." in Path(path).parts:
            raise ValueError("Unsafe reference path")
        parts = path.removeprefix(PREFIX).split("/")
        family = "/".join(parts[:2]) if parts[0] == "kn" else parts[0]
        if (family not in COLLECTIONS or row["collection"] != COLLECTIONS[family]
                or parts[-1] != row["id"] + "_root-pli-ms.json"
                or not re.fullmatch(r"[0-9a-f]{40}", row.get("git_blob", ""))
                or path in paths or row["id"] in identifiers or not atoms(row["id"])):
            raise ValueError("Duplicate, mismatched or unrecognized reference unit")
        families.add(family)
        paths.add(path)
        identifiers.add(row["id"])
    if families != set(COLLECTIONS):
        raise ValueError("Reference inventory omits a book or Niddesa subdivision")


def build_report(reference: dict, editions: list[dict], priorities: dict, whole_books: dict | None = None) -> dict:
    if reference.get("schema_version") != 1 or reference.get("unit_count") != len(reference["units"]):
        raise ValueError("Inconsistent reference inventory")
    by_atom = {}
    unmatched = []
    for index, edition in enumerate(editions):
        if edition["state"] != "BUILD_ELIGIBLE" or edition["collection"] not in set(COLLECTIONS.values()):
            continue
        ids = atoms(edition["canonical_id"])
        if not ids:
            unmatched.append({key: edition[key] for key in ("collection", "canonical_id", "source_url")})
        for identifier in ids:
            by_atom.setdefault((edition["collection"], identifier), set()).add(index)
    rows = []
    seen = set()
    for unit in reference["units"]:
        if unit["id"] in seen or unit["collection"] not in set(COLLECTIONS.values()):
            raise ValueError("Duplicate ID or out-of-scope reference collection")
        seen.add(unit["id"])
        identifiers = atoms(unit["id"])
        if not identifiers:
            raise ValueError("Unrecognized reference ID")
        matches = {i for identifier in identifiers for i in by_atom.get((unit["collection"], identifier), set())}
        covered = {identifier for identifier in identifiers if by_atom.get((unit["collection"], identifier))}
        complete = {identifier for identifier in identifiers
                    if any(editions[i]["completeness"] == "COMPLETE"
                           for i in by_atom.get((unit["collection"], identifier), set()))}
        states = sorted({editions[i]["completeness"] for i in matches})
        book = (whole_books or {}).get(unit["collection"], {})
        availability = ("AVAILABLE" if covered == identifiers else "WHOLE_BOOK_ALIGNMENT_PENDING" if book else
                        "PARTLY_AVAILABLE" if covered else "NO_LOCAL_EDITION")
        status = ("WHOLE_BOOK_SCOPE_ALIGNMENT_UNVERIFIED" if not matches and book else
                  "NO_LOCAL_EDITION" if not matches else
                  "COMPLETE_WITHIN_RECORDED_SCOPE" if complete == identifiers else
                  "AVAILABLE_COMPLETENESS_UNVERIFIED" if "UNKNOWN" in states else
                  "PARTIAL_OR_ABBREVIATED_COVERAGE")
        action = priorities.get(unit["collection"], {})
        rows.append({**unit, "availability": availability, "reference_atom_count": len(identifiers),
                     "available_atom_count": len(covered), "missing_atoms": sorted(identifiers - covered),
                     "edition_count": len(matches), "completeness": status, "edition_completeness_labels": states,
                     "source_urls": sorted({editions[i]["source_url"] for i in matches}),
                     "next_action": action.get("next_action", "Verify complete source scope, including repetitions, before closing this unit."),
                     "candidate_sources": action.get("sources", []),
                     "unsegmented_book_sources": [pdf["source_url"] for pdf in book.get("pdfs", [])],
                     "semantic_identity_fully_audited": False})
    summaries = []
    for collection in dict.fromkeys(COLLECTIONS.values()):
        selected = [row for row in rows if row["collection"] == collection]
        if not selected:
            raise ValueError("Expected collection disappeared from reference inventory: " + collection)
        summaries.append({"collection": collection, "reference_units": len(selected),
                          "availability": dict(Counter(r["availability"] for r in selected)),
                          "completeness": dict(Counter(r["completeness"] for r in selected))})
    return {"schema_version": 1, "reference_commit": reference["commit"], "reference_units": len(rows),
            "active_path": "Complete Sutta Pitaka coverage before alternative editions; Abhidhamma deferred until last",
            "limits": ["Identifier coverage is not semantic or translation-quality proof.",
                       "COMPLETE applies only to the recorded edition scope; verse-only or abbreviated editions cannot certify a whole book.",
                       "Whole-book/grouped identifiers not parsed here need explicit correspondence; they are not silently counted as complete.",
                       "Availability is validated source/build inclusion, not a fresh public deployment check.",
                       "Reference files/grouping differ by edition; no universal remaining-sutta count is claimed."],
            "availability": dict(Counter(r["availability"] for r in rows)), "collections": summaries,
            "unmatched_edition_identifiers": unmatched, "units": rows}


def output_payloads(reference: dict, root: Path = ROOT) -> dict[Path, bytes]:
    validate_reference(reference)
    editions_raw = (root / EDITIONS.relative_to(ROOT)).read_bytes()
    priorities_raw = (root / PRIORITIES.relative_to(ROOT)).read_bytes()
    catalog_raw = (root / "metadata/site-catalog.json").read_bytes()
    assets_raw = (root / "metadata/eligible-assets.json").read_bytes()
    assets = {row["local_path"]: row for row in json.loads(assets_raw)["assets"]}
    whole_books = {}
    for key, book in json.loads(catalog_raw)["whole_book_pdf_sources"].items():
        if book.get("license") != "Public domain in the United States": continue
        for pdf in book["pdfs"]:
            relative = "theravada/tipitaka/" + pdf["path"]
            asset = assets.get(relative, {})
            path = root / relative
            if (path.is_symlink() or not path.is_file() or asset.get("license") != book["license"]
                    or hashlib.sha256(path.read_bytes()).hexdigest() != asset.get("sha256")):
                raise ValueError("Whole-book coverage needs its verified asset bytes: " + relative)
        whole_books[key] = book
    report = build_report(reference, json.loads(editions_raw)["records"], json.loads(priorities_raw)["collections"], whole_books)
    report["input_sha256"] = {REFERENCE.relative_to(ROOT).as_posix(): hashlib.sha256(json_bytes(reference)).hexdigest(),
                              EDITIONS.relative_to(ROOT).as_posix(): hashlib.sha256(editions_raw).hexdigest(),
                              "metadata/site-catalog.json": hashlib.sha256(catalog_raw).hexdigest(),
                              "metadata/eligible-assets.json": hashlib.sha256(assets_raw).hexdigest(),
                              PRIORITIES.relative_to(ROOT).as_posix(): hashlib.sha256(priorities_raw).hexdigest()}
    from io import StringIO
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["collection", "reference_id", "availability", "completeness", "missing_atoms", "next_action"], lineterminator="\n")
    writer.writeheader()
    for row in report["units"]:
        if row["availability"] != "AVAILABLE" or row["completeness"] != "COMPLETE_WITHIN_RECORDED_SCOPE":
            writer.writerow({"collection": row["collection"], "reference_id": row["id"],
                             **{key: row[key] for key in ("availability", "completeness", "next_action")},
                             "missing_atoms": " ".join(row["missing_atoms"])})
    return {REPORT.relative_to(ROOT): json_bytes(report), GAPS.relative_to(ROOT): buffer.getvalue().encode()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-reference", type=Path)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--verify-reference", type=Path, help="Recompare the full metadata inventory with its pinned Git tree; read-only")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check and args.capture_reference:
        parser.error("Capture and check are separate operations")
    if args.capture_reference:
        REFERENCE.write_bytes(json_bytes(capture_reference(args.capture_reference, args.revision)))
    reference = json.loads(REFERENCE.read_text())
    if args.verify_reference and capture_reference(args.verify_reference, reference["commit"]) != reference:
        raise ValueError("Reference inventory differs from its pinned Git tree")
    for relative, expected in output_payloads(reference).items():
        target = ROOT / relative
        if args.check:
            if not target.is_file() or target.read_bytes() != expected:
                raise ValueError("Coverage output is stale: " + relative.as_posix())
        else:
            target.write_bytes(expected)
    report = json.loads(REPORT.read_text())
    print(json.dumps({key: report[key] for key in ("reference_commit", "reference_units", "availability", "collections")}, indent=2))


if __name__ == "__main__":
    main()
