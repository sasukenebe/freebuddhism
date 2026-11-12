# SPDX-License-Identifier: 0BSD
from copy import deepcopy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
from candana_processing_register import (
    CONDITIONS, append_review, collect, current, encoded, merge_register, run,
    sha, stable_id, validate_reviews, verify_permission, views,
)


class CandanaProcessingRegisterTests(unittest.TestCase):
    def permission(self):
        return {"schema_version": 1, "permission_id": "synthetic-grant",
                "evidence_type": "OWNER_SUPPLIED_CORRESPONDENCE_AND_CONFIRMATION",
                "translator": "Bhikkhu Candana", "website": "https://freebuddhism.org",
                "conditions": list(CONDITIONS), "owner_confirmation_sent": True,
                "public_repository_or_third_party_archive_grant_inferred": False}

    def observation(self, **changes):
        row = {"source_sha256": sha(b"source"), "source_selector": "printed:1",
               "canonical_ids": ["AN 1.1"], "body_sha256": sha(b"body")}
        return row | changes

    def register(self, row=None):
        return merge_register({"schema_version": 1, "entries": []}, [row or self.observation()])

    def event(self, register, kind="human", **changes):
        entry = register["entries"][0]
        return {"event_id": "finding-1", "entry_id": entry["id"],
                "revision_sha256": entry["current_revision"], "reviewer": "Synthetic reviewer",
                "reviewer_kind": kind, "date": "2026-11-12", "check": "extraction",
                "outcome": "PARTIAL", "scope": "PDF page 1, opening only",
                "evidence": "Synthetic scoped comparison; not an actual corpus review"} | changes

    def test_permission_is_confirmed_website_only_and_retains_every_condition(self):
        permission = self.permission()
        verify_permission(permission)
        for field, value in (("owner_confirmation_sent", False), ("conditions", CONDITIONS[:2]),
                             ("public_repository_or_third_party_archive_grant_inferred", True),
                             ("website", "https://example.org")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_permission(permission | {field: value})

    def test_remapping_preserves_id_history_and_does_not_transfer_review(self):
        original = self.register()
        ledger = {"schema_version": 1, "events": [self.event(original)]}
        changed = merge_register(original, [self.observation(canonical_ids=["AN 1.2"])])
        self.assertEqual(original["entries"][0]["id"], changed["entries"][0]["id"])
        self.assertEqual(len(changed["entries"][0]["revisions"]), 2)
        self.assertNotEqual(ledger["events"][0]["revision_sha256"], changed["entries"][0]["current_revision"])
        self.assertEqual(validate_reviews(ledger, changed), ledger["events"])
        self.assertEqual(changed, merge_register(changed, [self.observation(canonical_ids=["AN 1.2"])]))

    def test_source_replacement_keeps_old_entry_and_all_findings(self):
        original = self.register()
        changed = merge_register(original, [self.observation(source_sha256=sha(b"new PDF"))])
        self.assertEqual(len(changed["entries"]), 2)
        old = next(e for e in changed["entries"] if e["id"] == original["entries"][0]["id"])
        self.assertFalse(old["active"])
        self.assertEqual(old["revisions"], original["entries"][0]["revisions"])
        validate_reviews({"schema_version": 1, "events": [self.event(original)]}, changed)

    def test_history_tampering_duplicate_passages_and_bad_hashes_are_rejected(self):
        original = self.register()
        original["entries"][0]["revisions"][0]["observation"]["canonical_ids"] = ["changed"]
        with self.assertRaises(ValueError): merge_register(original, [])
        with self.assertRaises(ValueError): merge_register(self.register(), [self.observation()] * 2)
        with self.assertRaises(ValueError): stable_id("bad hash", "source")

    def test_review_events_are_revision_bound_attributed_and_append_only(self):
        register = self.register()
        ledger = {"schema_version": 1, "events": []}
        event = self.event(register, kind="model")
        added = append_review(ledger, event, register)
        self.assertEqual(ledger["events"], [])
        self.assertEqual(append_review(added, event, register), added)
        with self.assertRaises(ValueError): append_review(added, event | {"outcome": "MATCH"}, register)
        with self.assertRaises(ValueError): append_review(ledger, event | {"reviewer": ""}, register)
        with self.assertRaises(ValueError): append_review(ledger, event | {"revision_sha256": sha(b"other")}, register)
        with self.assertRaises(ValueError): append_review(ledger, event | {"reviewer_kind": "automatic-human"}, register)

    def fixture(self, root, *, left=None, right=None, printed="AN 4.1"):
        root.mkdir()
        url = "https://www.mindreleased.com/s/synthetic.pdf"
        page_url = "https://www.mindreleased.com/pali-suttas"
        pdf = b"%PDF-1.4 synthetic fixture, not a real translation"
        page = b'<a href="/s/synthetic.pdf">AN 4.1 synthetic</a>'
        text = (printed + "\nSynthetic title\nTranslated by Bhikkhu Candana\n\n"
                "Copyright synthetic.\nAll source words and notes stay.\n\f").encode()
        left = text if left is None else left
        right = left if right is None else right
        key = sha(url.encode())
        relative = "sources/" + key
        report = {"source_url": url, "source_sha256": sha(pdf), "fingerprint": sha(b"converter"),
                  "output_hashes": {"poppler.txt": sha(left), "mupdf.txt": sha(right)}}
        inventory = [{"source_url": url, "source_sha256": sha(pdf), "issues": ["PERMISSION_REVIEW_REQUIRED", "LAYOUT_REVIEW_REQUIRED"],
                      "page_reviews": [], "rights": "NEEDS_PERMISSION_REVIEW",
                      "text_paths": {name: relative + "/" + name for name in ("poppler.txt", "mupdf.txt")}}]
        files = {"build/page.html": page, "build/source.pdf": pdf,
                 "metadata/source-manifests/candana.json": encoded({"books": [], "texts": []}),
                 "metadata/eligible-texts.json": encoded({"texts": [{"canonical_id": "AN 4.1"}]}),
                 "build/candana-audit/queue.json": encoded({"jobs": [
                     {"url": page_url, "state": "COLLECTED", "cache": "build/page.html", "sha256": sha(page)},
                     {"url": url, "state": "COLLECTED", "cache": "build/source.pdf", "sha256": sha(pdf)}]}),
                 "build/candana-batch-review/inventory.json": encoded(inventory),
                 "build/candana-batch-review/" + relative + "/report.json": encoded(report),
                 "build/candana-batch-review/" + relative + "/poppler.txt": left,
                 "build/candana-batch-review/" + relative + "/mupdf.txt": right}
        for relative, value in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        return left

    def test_standalone_staging_preserves_complete_source_bytes_and_flags(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            text = self.fixture(root)
            rows, artifacts = collect(root, self.permission())
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["state"], "STAGED_UNALTERED_DOCUMENT_REVIEW")
            self.assertEqual(rows[0]["body_sha256"], sha(text))
            self.assertEqual(artifacts[rows[0]["artifacts"]["poppler_text"]["path"]], text)
            self.assertTrue(rows[0]["processing"]["no_notes_headers_or_pagination_removed"])
            self.assertIn("DOCUMENT_TO_SUTTA_BOUNDARY_REVIEW", rows[0]["risk_flags"])
            self.assertEqual(rows[0]["public_repository_or_archive_distribution"], "NOT_INFERRED_FROM_WEBSITE_PERMISSION")

    def test_fresh_word_boundary_character_and_id_disagreements_are_held(self):
        for change in ("words", "characters", "mapping", "hyphen"):
            with self.subTest(change=change), TemporaryDirectory() as directory:
                root = Path(directory) / "source"
                left = b"AN 4.1\nTranslated by Bhikkhu Candana\n\nnot ever\f"
                right = left.replace(b"not ever", b"notever") if change == "words" else left
                if change == "characters": right = right.replace(b"not ever", b"new wording")
                if change == "hyphen": left = right = left.replace(b"not ever", b"well-\ndeveloped")
                if change == "mapping": left = right = left.replace(b"AN 4.1", b"AN 4.2")
                self.fixture(root, left=left, right=right)
                rows, _ = collect(root, self.permission())
                self.assertEqual(rows[0]["state"], "HELD_PROCESSING_OR_IDENTITY")
                if change == "words":
                    self.assertEqual(rows[0]["fresh_character_disagreement_pages"], [])
                    self.assertEqual(rows[0]["fresh_word_boundary_disagreement_pages"], [1])

    def test_changed_cached_inputs_fail_before_durable_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            self.fixture(root)
            (root / "build/source.pdf").write_bytes(b"changed")
            destination = Path(directory) / "review"
            permission = Path(directory) / "permission.json"
            permission.write_bytes(encoded(self.permission()))
            with self.assertRaises(ValueError): run(root, destination, permission)
            self.assertFalse((destination / "register.json").exists())

    def test_regeneration_preserves_reviews_bytes_and_links_outside_build(self):
        with TemporaryDirectory() as directory:
            root, destination = Path(directory) / "source", Path(directory) / "private"
            self.fixture(root)
            permission = Path(directory) / "permission.json"
            permission.write_bytes(encoded(self.permission()))
            result = run(root, destination, permission)
            self.assertEqual(result["published_new_editions"], 0)
            register = json.loads((destination / "register.json").read_bytes())
            event = self.event(register, kind="model")
            supplied = Path(directory) / "finding.json"
            supplied.write_bytes(encoded(event))
            run(root, destination, permission, supplied)
            before = (destination / "reviews.json").read_bytes()
            index_before = (destination / "index.html").read_bytes()
            register_before = (destination / "register.json").read_bytes()
            run(root, destination, permission)
            self.assertEqual((destination / "reviews.json").read_bytes(), before)
            self.assertEqual((destination / "register.json").read_bytes(), register_before)
            self.assertEqual((destination / "index.html").read_bytes(), index_before)
            page = next((destination / "entries").glob("*.html")).read_text()
            self.assertIn("human findings: 0; model findings: 1", page)
            for entry in register["entries"]:
                for artifact in current(entry)["artifacts"].values():
                    self.assertEqual(sha((destination / artifact["path"]).read_bytes()), artifact["sha256"])
            with self.assertRaises(ValueError): run(root, root / "build/review", permission)


if __name__ == "__main__":
    unittest.main()
