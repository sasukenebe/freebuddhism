#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Offline, persistent Candana processing register and standalone ingestion drafts.

No network, public-tree writes or publication. Keep the destination outside build/
and outside the public source checkout. Review events are never generated.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import fcntl
import hashlib
import html
import json
from pathlib import Path
import re

try:
    from .candana_corpus import census, references
    from .import_candana import ROOT
    from .prepare_candana_batch import safe_relative, write_file, pages_of
except ImportError:
    from candana_corpus import census, references
    from import_candana import ROOT
    from prepare_candana_batch import safe_relative, write_file, pages_of

CONDITIONS = [
    "No part of the content of the translations may be changed or altered",
    "Available free of charge and never monetized in any way, now or in the future",
    "The content of these translations must never be used for advertisements",
]
MARKER = {"kind": "private-candana-processing-register", "schema_version": 1,
          "automatic_publication": False}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def stable_id(source_hash: str, selector: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash) or not selector:
        raise ValueError("A register ID needs exact source bytes and a source selector")
    return "candana-" + sha((source_hash + "\n" + selector).encode())[:24]


def verify_permission(value: dict) -> None:
    if (value.get("schema_version") != 1
            or value.get("evidence_type") != "OWNER_SUPPLIED_CORRESPONDENCE_AND_CONFIRMATION"
            or value.get("translator") != "Bhikkhu Candana"
            or value.get("website") != "https://freebuddhism.org"
            or value.get("conditions") != CONDITIONS
            or value.get("owner_confirmation_sent") is not True
            or value.get("public_repository_or_third_party_archive_grant_inferred") is not False
            or not value.get("permission_id")):
        raise ValueError("Confirmed website permission and all three conditions are required")


def revision_hash(value: dict) -> str:
    return sha(encoded(value))


def merge_register(previous: dict, observations: list[dict]) -> dict:
    """Append changed revisions; never erase vanished entries or earlier observations."""
    if previous.get("schema_version") != 1 or not isinstance(previous.get("entries"), list):
        raise ValueError("Unknown processing register")
    entries = {}
    for original in previous["entries"]:
        entry = deepcopy(original)
        if entry["id"] in entries or not entry.get("revisions"):
            raise ValueError("Duplicate register entry or missing history")
        for version in entry["revisions"]:
            if (version["sha256"] != revision_hash(version["observation"])
                    or entry["id"] != stable_id(version["observation"]["source_sha256"],
                                                 version["observation"]["source_selector"])):
                raise ValueError("Register history changed or identity is inconsistent")
        if entry["current_revision"] not in {v["sha256"] for v in entry["revisions"]}:
            raise ValueError("Register revision pointer is invalid")
        entry["active"] = False
        entries[entry["id"]] = entry
    seen = set()
    for row in observations:
        key = stable_id(row["source_sha256"], row["source_selector"])
        if key in seen:
            raise ValueError("Duplicate current source passage")
        seen.add(key)
        entry = entries.setdefault(key, {"id": key, "revisions": []})
        digest = revision_hash(row)
        if digest not in {r["sha256"] for r in entry["revisions"]}:
            entry["revisions"].append({"sha256": digest, "observation": deepcopy(row)})
        entry.update(active=True, current_revision=digest)
    return {"schema_version": 1, "automatic_publication": False,
            "scope": "Candana converted source passages and standalone sutta offers; not a translation-quality certificate",
            "entries": sorted(entries.values(), key=lambda row: row["id"])}


def current(entry: dict) -> dict:
    return next(r["observation"] for r in entry["revisions"]
                if r["sha256"] == entry["current_revision"])


def validate_reviews(ledger: dict, register: dict) -> list[dict]:
    """Validate reported findings; model checks never count as human approval."""
    if ledger.get("schema_version") != 1 or not isinstance(ledger.get("events"), list):
        raise ValueError("Unknown review-event ledger")
    entries = {entry["id"]: entry for entry in register["entries"]}
    ids = set()
    for event in ledger["events"]:
        required = ("event_id", "entry_id", "revision_sha256", "reviewer", "reviewer_kind",
                    "date", "check", "outcome", "scope", "evidence")
        if any(not isinstance(event.get(key), str) or not event[key].strip() for key in required):
            raise ValueError("A finding needs an attributed, scoped, revision-bound review")
        if event["event_id"] in ids:
            raise ValueError("Review event IDs must be unique")
        ids.add(event["event_id"])
        entry = entries.get(event["entry_id"])
        if entry is None or event["revision_sha256"] not in {r["sha256"] for r in entry["revisions"]}:
            raise ValueError("Finding refers to an unknown passage or processing revision")
        if (event["reviewer_kind"] not in {"human", "model"}
                or event["check"] not in {"extraction", "layout", "identity", "translation"}
                or event["outcome"] not in {"MATCH", "ISSUE", "PARTIAL"}):
            raise ValueError("Unsupported review kind, check or outcome")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", event["date"]):
            raise ValueError("Review dates must identify a calendar day")
    return ledger["events"]


def append_review(ledger: dict, event: dict, register: dict) -> dict:
    result = deepcopy(ledger)
    previous = next((r for r in result["events"] if r["event_id"] == event.get("event_id")), None)
    if previous is not None:
        if previous != event:
            raise ValueError("Refusing to overwrite a review event; append a new finding")
    else:
        result["events"].append(event)
    validate_reviews(result, register)
    return result


def checked_bytes(root: Path, relative: str, digest: str) -> bytes:
    data = safe_relative(root, relative).read_bytes()
    if sha(data) != digest:
        raise ValueError("Review input changed: " + relative)
    return data


def source_selector(row: dict) -> str:
    if row.get("source_labels"):
        return "printed-labels:" + ",".join(row["source_labels"])
    if row.get("source_numbers"):
        return "printed-numbers:" + "-".join(map(str, row["source_numbers"]))
    # Snp has explicit printed chapter/sutta IDs and a pinned raw interval hash.
    if row.get("source_interval_sha256"):
        return "raw-interval:" + row["source_interval_sha256"]
    raise ValueError("Published passage lacks a stable source selector")


def collect(root: Path, permission: dict) -> tuple[list[dict], dict[str, bytes]]:
    """Preflight every input before writing any durable output; no source rewriting."""
    verify_permission(permission)
    manifest = json.loads((root / "metadata/source-manifests/candana.json").read_bytes())
    jobs = json.loads((root / "build/candana-audit/queue.json").read_bytes())["jobs"]
    inventory = json.loads((root / "build/candana-batch-review/inventory.json").read_bytes())
    corpus = census({"jobs": jobs}, inventory, manifest,
                    lambda path: safe_relative(root, path).read_bytes())
    offers = {row["source_url"]: row for row in corpus["offers"]}
    by_url = {row["source_url"]: row for row in inventory}
    job_by_url = {job["url"]: job for job in jobs}
    existing_ids = {r["canonical_id"] for r in json.loads(
        (root / "metadata/eligible-texts.json").read_bytes())["texts"]}
    existing_candana = {r["canonical_id"] for r in manifest["texts"]}
    artifacts, observations = {}, []

    def freeze(data: bytes, suffix: str) -> dict:
        digest = sha(data)
        relative = f"artifacts/{digest}{suffix}"
        artifacts[relative] = data
        return {"path": relative, "sha256": digest}

    books = {row["id"]: row for row in manifest["books"]}
    frozen_books = {key: freeze(checked_bytes(root, book["local_path"], book["sha256"]), ".pdf")
                    for key, book in books.items()}
    frozen_audits = [freeze(path.read_bytes(), ".json") for path in
                     sorted((root / "metadata/reports").glob("candana-*.json"))]
    generator_hash = sha(Path(__file__).read_bytes())
    for row in manifest["texts"] + manifest.get("group_texts", []):
        text = checked_bytes(root, row["local_path"], row["sha256"])
        body = text.decode("utf-8").split("\n\n", 1)[1].encode()
        if sha(body) != row["body_sha256"]:
            raise ValueError("Published Candana body differs from its manifest")
        flags = ["PDF_TEXT_EXTRACTION", "SOURCE_BOUNDARY_SELECTION", "CANONICAL_IDENTITY_REVIEW",
                 "PARAGRAPH_OR_VERSE_LAYOUT_REVIEW", "FULL_HUMAN_PROOFREAD_NOT_RECORDED"]
        if row.get("source_numbers") or row.get("source_labels"):
            flags.extend(["PRINTED_PAGINATION_HANDLING", "PHYSICAL_LINE_REFLOW"])
        if row.get("group_id") or row.get("source_numbers", [0, 0])[0] != row.get("source_numbers", [0, 0])[-1]:
            flags.append("GROUPED_OR_RENUMBERED_PASSAGE")
        if row["book"] == "an-book1":
            flags.append("REVIEWED_HYPHEN_WRAP_JOINS_POSSIBLE")
        observations.append({
            "source_sha256": row["source_revision"], "source_selector": source_selector(row),
            "source_url": row["source_url"], "canonical_ids": row.get("canonical_ids", [row["canonical_id"]]),
            "canonical_ids_status": "RECORDED_MAPPING_NOT_FULL_SEMANTIC_AUDIT",
            "title": row["title"], "state": "EXISTING_SOURCE_MANIFEST_EDITION",
            "source_pages": row.get("source_pdf_pages", [row.get("source_page"), row.get("source_last_page")]),
            "page_scope": "Recorded endpoints only; null end means last page not established here",
            "body_sha256": row["body_sha256"], "risk_flags": flags,
            "permission_id": permission["permission_id"], "website_conditions": CONDITIONS,
            "original_book_conditions": books[row["book"]]["conditions"],
            "artifacts": {"original_pdf": frozen_books[row["book"]], "attributed_text": freeze(text, ".txt")},
            "processing": {"method": "Existing exact-book conversion; original recipe and audits retained",
                           "book": row["book"], "source_text_path": row["local_path"],
                           "register_generator_sha256": generator_hash,
                           "frozen_prior_conversion_audits": frozen_audits},
            "full_human_review": "NOT_RECORDED_IN_THIS_REGISTER",
        })

    for url, offer in sorted(offers.items()):
        # Books already have passage-level rows; author resources and Abhidhamma
        # are explicitly outside this sutta-ingestion batch.
        reference = offer["reference_group"]
        if reference.startswith(("book:", "resource:")) or offer["state"] != "COLLECTED":
            continue
        row, job = by_url[url], job_by_url[url]
        key = sha(url.encode())
        report_path = "build/candana-batch-review/sources/" + key + "/report.json"
        report_raw = safe_relative(root, report_path).read_bytes()
        report = json.loads(report_raw)
        if report["source_sha256"] != offer["source_sha256"] or report["source_url"] != url:
            raise ValueError("Standalone report belongs to a different source")
        pdf = checked_bytes(root, job["cache"], offer["source_sha256"])
        if not pdf.startswith(b"%PDF-"):
            raise ValueError("Standalone original is not a PDF")
        texts = {}
        for engine in ("poppler.txt", "mupdf.txt"):
            texts[engine] = checked_bytes(root, "build/candana-batch-review/" + row["text_paths"][engine],
                                          report["output_hashes"][engine])
        body = texts["poppler.txt"]
        a, b = [pages_of(texts[name].decode("utf-8")) for name in ("poppler.txt", "mupdf.txt")]
        mismatch = [n for n, (left, right) in enumerate(zip(a, b), 1)
                    if re.sub(r"\s+", "", left) != re.sub(r"\s+", "", right)]
        if len(a) != len(b):
            mismatch.extend(range(min(len(a), len(b)) + 1, max(len(a), len(b)) + 1))
        word_disagreements = [n for n, (left, right) in enumerate(zip(a, b), 1)
                              if " ".join(left.split()) != " ".join(right.split())]
        hyphen_pages = [n for n, text in enumerate(a, 1) if re.search(r"\w-\n[ \t]*\w", text)]
        heading = "\n".join(body.decode("utf-8").splitlines()[:8])
        printed = references(heading)
        mapping_clear = (len(printed) == 1 and printed == [reference]
                         and reference in existing_ids and not offer["reference_issues"]
                         and "-" not in reference)
        flags = ["PDF_TEXT_EXTRACTION", "DOCUMENT_TO_SUTTA_BOUNDARY_REVIEW",
                 "PARAGRAPH_OR_VERSE_LAYOUT_REVIEW", "FULL_HUMAN_PROOFREAD_NOT_RECORDED"]
        flags.extend(issue for issue in row["issues"] if issue != "PERMISSION_REVIEW_REQUIRED")
        if not mapping_clear:
            flags.append("CANONICAL_IDENTITY_OR_GROUP_SCOPE_HOLD")
        if mismatch:
            flags.append("EXTRACTOR_CHARACTER_DISAGREEMENT_HOLD")
        if word_disagreements:
            flags.append("EXTRACTOR_WORD_BOUNDARY_DISAGREEMENT_HOLD")
        if hyphen_pages:
            flags.append("HYPHEN_WRAP_REVIEW_REQUIRED")
        if not re.search(r"\bTranslated\s+by\s+Bhikkhu\s+Candana\b", body.decode("utf-8"), re.I):
            flags.append("TRANSLATOR_ATTRIBUTION_HOLD")
        serious = (not mapping_clear or bool(mismatch) or "TRANSLATOR_ATTRIBUTION_HOLD" in flags
                   or bool(word_disagreements) or bool(hyphen_pages)
                   or bool(set(row["issues"]) - {"PERMISSION_REVIEW_REQUIRED", "LAYOUT_REVIEW_REQUIRED"})
                   or any(p.get("flags") for p in row["page_reviews"]))
        observations.append({
            "source_sha256": offer["source_sha256"], "source_selector": "whole-standalone-document",
            "source_url": url, "canonical_ids": [reference] if not reference.startswith("unresolved:") else [],
            "canonical_ids_status": "PUBLISHER_AND_OPENING_AGREE_NOT_CONTENT_AUDITED" if mapping_clear else "HELD",
            "existing_candana_reference": reference in existing_candana,
            "printed_references": printed, "publisher_references": offer["publisher_references"],
            "title": offer["filename"],
            "state": "HELD_PROCESSING_OR_IDENTITY" if serious else "STAGED_UNALTERED_DOCUMENT_REVIEW",
            "source_pages": [1, len(a)], "body_sha256": sha(body),
            "risk_flags": sorted(set(flags)), "flagged_pages": row["page_reviews"],
            "fresh_character_disagreement_pages": mismatch,
            "fresh_word_boundary_disagreement_pages": word_disagreements,
            "hyphen_wrap_pages": hyphen_pages,
            "permission_id": permission["permission_id"], "website_conditions": CONDITIONS,
            "public_repository_or_archive_distribution": "NOT_INFERRED_FROM_WEBSITE_PERMISSION",
            "artifacts": {"original_pdf": freeze(pdf, ".pdf"),
                          "poppler_text": freeze(body, ".txt"),
                          "mupdf_text": freeze(texts["mupdf.txt"], ".txt"),
                          "conversion_report": freeze(report_raw, ".json")},
            "processing": {"method": "Whole document Poppler extraction retained byte-for-byte; no sutta-only cropping",
                           "extractor_fingerprint": report["fingerprint"],
                           "register_generator_sha256": generator_hash,
                           "fresh_page_character_comparison": "FAIL" if mismatch else "PASS",
                           "no_ocr_or_word_repair": True, "no_hyphen_joining": True,
                           "no_notes_headers_or_pagination_removed": True,
                           "no_automatic_publication": True},
            "full_human_review": "NOT_RECORDED_IN_THIS_REGISTER",
        })
    return observations, artifacts


def html_document(title: str, body: str) -> bytes:
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + html.escape(title) + '</title><style>'
            'pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere}'
            'body{overflow-wrap:anywhere}summary{cursor:pointer}</style></head><body>'
            '<h1>' + html.escape(title) + '</h1>' + body + '</body></html>\n').encode()


def views(register: dict, reviews: dict, artifacts: dict[str, bytes], destination: Path) -> dict[str, bytes]:
    events = validate_reviews(reviews, register)
    outputs = {}
    intro = ('<p>Private processing-risk register. Staged documents are not published sutta readers. '
             'Machine agreement is not canonical identification or human proofreading. '
             'Abhidhamma is deferred until last.</p><p>Review source wording, order, notes, '
             'diacritics, paragraph/verse breaks and sutta identity separately. Do not rewrite '
             'the translation. Record findings against the stable entry ID and processing revision; '
             'a model review never substitutes for a human result.</p>'
             '<p>Website conditions: ' + html.escape('; '.join(CONDITIONS)) + '.</p>'
             '<p><a href="register.json">Complete register/history</a> · '
             '<a href="reviews.json">Attributed review findings</a> · '
             '<a href="staged-editions.json">Standalone ingestion batch</a></p>')
    rows = []
    for entry in register["entries"]:
        row = current(entry)
        label = ", ".join(row["canonical_ids"]) or "Unresolved source reference"
        title = label + " — " + row["title"]
        local_events = [event for event in events if event["entry_id"] == entry["id"]]
        current_events = [event for event in local_events if event["revision_sha256"] == entry["current_revision"]]
        links = []
        for kind, artifact in row["artifacts"].items():
            links.append('<a href="../' + html.escape(artifact["path"], quote=True) + '">'
                         + html.escape(kind.replace("_", " ")) + '</a>')
        pdf = row["artifacts"]["original_pdf"]["path"]
        first_page = row["source_pages"][0] or 1
        header = ('<p><a href="../index.html">Complete list</a> · <a href="../' + pdf
                  + '#page=' + str(first_page) + '">Original PDF at passage</a></p><p>'
                  + " · ".join(links) + '</p><p><a href="' + html.escape(row["source_url"], quote=True)
                  + '">Publisher source</a></p><p>' + html.escape(row["state"]) + '</p><p>Entry: '
                  + entry["id"] + '<br>Revision: ' + entry["current_revision"] + '</p><p>Conditions: '
                  + html.escape('; '.join(CONDITIONS)) + '</p><p>Source PDF pages: '
                  + html.escape(str(row["source_pages"])) + '</p><h2>Review questions</h2><ul>'
                  + ''.join('<li>' + html.escape(flag) + '</li>' for flag in row["risk_flags"]) + '</ul>')
        header += '<p>Current-revision human findings: ' + str(sum(e["reviewer_kind"] == "human" for e in current_events))
        header += '; model findings: ' + str(sum(e["reviewer_kind"] == "model" for e in current_events)) + '.</p>'
        if local_events:
            header += '<h2>Reported findings (including older revisions)</h2><pre>' + html.escape(encoded(local_events).decode()) + '</pre>'
        text_artifact = row["artifacts"].get("attributed_text", row["artifacts"].get("poppler_text"))
        text_path = text_artifact["path"]
        raw = artifacts.get(text_path)
        if raw is None:
            raw = checked_bytes(destination, text_path, text_artifact["sha256"])
        header += '<h2>Preserved text</h2><pre>' + html.escape(raw.decode("utf-8")) + '</pre>'
        outputs["entries/" + entry["id"] + ".html"] = html_document(title, header)
        rows.append('<li id="' + entry["id"] + '"><a href="entries/' + entry["id"] + '.html">'
                    + html.escape(title) + '</a> — ' + html.escape(row["state"])
                    + ('' if entry["active"] else ' — RETAINED, NO LONGER IN CURRENT INPUTS')
                    + '<br>' + entry["id"] + '</li>')
    outputs["index.html"] = html_document("Candana — stable processing review register", intro + '<ol>' + ''.join(rows) + '</ol>')
    return outputs


def staged_editions(register: dict) -> dict:
    records = []
    for entry in register["entries"]:
        row = current(entry)
        if not entry["active"] or row["state"] != "STAGED_UNALTERED_DOCUMENT_REVIEW":
            continue
        records.append({"entry_id": entry["id"], "revision_sha256": entry["current_revision"],
                        "canonical_id": row["canonical_ids"][0], "source_url": row["source_url"],
                        "source_sha256": row["source_sha256"], "body_sha256": row["body_sha256"],
                        "permission_id": row["permission_id"], "conditions": row["website_conditions"],
                        "artifacts": row["artifacts"], "risk_flags": row["risk_flags"],
                        "existing_candana_reference": row["existing_candana_reference"],
                        "body_scope": "Complete source document, including headings/copyright/notes/pagination; not cropped sutta-only text",
                        "publication_status": "NOT_PUBLISHED",
                        "next_gate": "Source layout and discourse identity review; website-only delivery, not public repository/archive permission"})
    return {"schema_version": 1, "automatic_publication": False, "records": records,
            "count": len(records), "scope": "Locally ingested standalone documents, not approved public sutta bodies"}


def frozen_references(value):
    """Walk current and historical revisions, including earlier conversion audits."""
    if isinstance(value, dict):
        if set(value) == {"path", "sha256"}:
            yield value
        else:
            for child in value.values():
                yield from frozen_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from frozen_references(child)


def run(root: Path, destination: Path, permission_path: Path, review_path: Path | None = None) -> dict:
    root, destination = root.resolve(), destination.absolute()
    if destination.resolve().is_relative_to(root):
        raise ValueError("Keep private permission/review storage outside the public source checkout")
    if "build" in destination.parts or any(path.is_symlink() for path in (destination, *destination.parents)):
        raise ValueError("Use stable non-build storage without symlinks")
    marker = destination / ".candana-processing-register.json"
    if marker.exists() and json.loads(marker.read_bytes()) != MARKER:
        raise ValueError("Wrong private register marker")
    if destination.exists() and any(p.name not in {permission_path.name} for p in destination.iterdir()) and not marker.exists():
        raise ValueError("Refusing an unmarked existing review directory")
    destination.mkdir(parents=True, exist_ok=True)
    lock_path = safe_relative(destination, ".lock")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Retain a valid storage marker even when input validation fails; a later
        # retry must not mistake our own leftover lock for an unrelated directory.
        write_file(marker, encoded(MARKER))
        permission = json.loads(permission_path.read_bytes())
        observations, artifacts = collect(root, permission)
        path = safe_relative(destination, "register.json")
        previous = json.loads(path.read_bytes()) if path.exists() else {"schema_version": 1, "entries": []}
        register = merge_register(previous, observations)
        checked_artifacts = set()
        for artifact in frozen_references(register):
            identity = (artifact["path"], artifact["sha256"])
            if identity in checked_artifacts:
                continue
            checked_artifacts.add(identity)
            if artifact["path"] in artifacts:
                if sha(artifacts[artifact["path"]]) != artifact["sha256"]:
                    raise ValueError("Historical artifact hash collision")
            else:
                checked_bytes(destination, artifact["path"], artifact["sha256"])
        ledger_path = safe_relative(destination, "reviews.json")
        ledger = json.loads(ledger_path.read_bytes()) if ledger_path.exists() else {"schema_version": 1, "events": []}
        if review_path:
            ledger = append_review(ledger, json.loads(review_path.read_bytes()), register)
        outputs = views(register, ledger, artifacts, destination)
        # Preflight immutable artifacts before installing anything. Never substitute
        # changed bytes at an old source/review link.
        for relative, data in artifacts.items():
            target = safe_relative(destination, relative)
            if target.exists() and target.read_bytes() != data:
                raise ValueError("Frozen review artifact changed: " + relative)
        for relative, data in artifacts.items():
            target = safe_relative(destination, relative)
            if not target.exists():
                write_file(target, data)
        write_file(path, encoded(register))
        # The generator never replaces a real review ledger unless an explicitly
        # supplied finding was validated and appended without changing old events.
        if not ledger_path.exists() or review_path:
            write_file(ledger_path, encoded(ledger))
        for relative, data in outputs.items():
            write_file(safe_relative(destination, relative), data)
        batch = staged_editions(register)
        write_file(safe_relative(destination, "staged-editions.json"), encoded(batch))
        summary = {"entries": len(register["entries"]), "active": len(observations),
                   "states": dict(Counter(row["state"] for row in observations)),
                   "review_events": len(ledger["events"]), "frozen_artifacts": len(artifacts),
                   "network_requests": 0, "published_new_editions": 0,
                   "staged_documents_without_existing_candana_reference": sum(
                       not row["existing_candana_reference"] for row in batch["records"]),
                   "conditions": CONDITIONS, "abhidhamma": "DEFERRED_UNTIL_LAST"}
        write_file(safe_relative(destination, "summary.json"), encoded(summary))
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--permission", required=True, type=Path, help="Private owner-confirmed permission JSON")
    parser.add_argument("--append-review", type=Path, help="One explicitly supplied human/model finding; never inferred")
    args = parser.parse_args()
    print(json.dumps(run(ROOT, args.destination, args.permission, args.append_review), indent=2))


if __name__ == "__main__":
    main()
