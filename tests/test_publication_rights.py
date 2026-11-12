"""Conditional-license boundaries under the owner-approved publication policy."""

import sys
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/buddhist_canon_pipeline"))
from publication_rights import canonical_license, license_conditions, license_url, verified_manifest, identity_for_source, IDENTITY_REVIEWS
from repair_licensed_identity import content_intervals


class PublicationRightsTests(unittest.TestCase):
    def test_accepted_families_preserve_conditions(self):
        self.assertEqual(canonical_license("CC BY-NC 4.0"), "CC-BY-NC-4.0")
        self.assertIn("noncommercial", license_conditions("CC-BY-NC-4.0"))
        self.assertIn("share-alike", license_conditions("CC-BY-NC-SA-3.0-US"))
        self.assertNotIn("noncommercial", license_conditions("CC-BY-SA-4.0"))
        self.assertEqual(license_conditions("CC0-1.0"), [])

    def test_unknown_and_no_derivatives_cannot_be_autoapproved(self):
        for label in ("UNSTATED", "CC-BY-ND-4.0", "CC-BY-NC-ND-3.0", "CC-BY-NC-SA-3.0-US+extra", "free download", "Copyright 2026"):
            with self.subTest(label=label):
                self.assertIsNone(canonical_license(label))
                with self.assertRaises(ValueError):
                    license_conditions(label)

    def test_version_and_jurisdiction_retained_in_license_link(self):
        self.assertEqual(license_url("CC-BY-NC-SA-3.0-US"), "https://creativecommons.org/licenses/by-nc-sa/3.0/us/")
        self.assertEqual(license_url("CC-BY-SA-4.0"), "https://creativecommons.org/licenses/by-sa/4.0/")

    def fixture(self, root):
        body = "First verse\nSecond verse\n\nNext stanza.\n"
        text = ("X 1 - Example\nTranslated by Example Author\nSource: https://example.org/text\n"
                "License: CC-BY-NC-4.0\nCopyright Example Author\nAttribution and noncommercial use.\n\n" + body)
        (root / "text.txt").write_text(text)
        (root / "source.html.source").write_text("<article>First verse<br>Second verse</article>")
        row = {"canonical_id": "X 1", "collection": "examples", "version": "example", "translator": "Example Author",
               "source_url": "https://example.org/text", "license": "CC-BY-NC-4.0",
               "license_url": license_url("CC-BY-NC-4.0"), "conditions": license_conditions("CC-BY-NC-4.0"),
               "license_notice": "Attribution and noncommercial use.", "copyright": "Copyright Example Author",
               "local_path": "text.txt", "sha256": hashlib.sha256(text.encode()).hexdigest(),
               "body_sha256": hashlib.sha256(body.encode()).hexdigest(), "source_snapshot": "source.html.source",
               "source_sha256": hashlib.sha256((root / "source.html.source").read_bytes()).hexdigest(),
               "completeness_status": "ABBREVIATED", "completeness_scope": "Publisher explicitly abbreviates repeats.",
               "source_comparison": "PASS"}
        path = root / "manifest.json"
        path.write_text(json.dumps({"schema_version": 1, "records": [row]}))
        return path, row

    def test_source_and_translation_mutation_cannot_pass(self):
        for source in ("text.txt", "source.html.source"):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path, _ = self.fixture(root)
                self.assertEqual(len(verified_manifest(root, path)["records"]), 1)
                (root / source).write_text("changed")
                with self.assertRaises(ValueError):
                    verified_manifest(root, path)

    def test_license_relabelling_and_missing_notice_fail(self):
        for field, value in (("license", "CC0-1.0"), ("license_notice", "Missing notice"), ("conditions", []),
                             ("source_comparison", "NOT_RUN")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path, row = self.fixture(root)
                row[field] = value
                path.write_text(json.dumps({"schema_version": 1, "records": [row]}))
                with self.assertRaises(ValueError):
                    verified_manifest(root, path)

    def test_title_only_remapping_is_not_publishable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, row = self.fixture(root)
            row["mapping_evidence"] = {"method": "unique pinned Pali title within publisher chapter; numbering corrected"}
            path.write_text(json.dumps({"schema_version": 1, "records": [row]}))
            with self.assertRaisesRegex(ValueError, "Title-only"):
                verified_manifest(root, path)

    def test_held_source_rights_do_not_make_a_reader_eligible(self):
        for fault in (None, "license", "source_sha256", "conditions"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path, row = self.fixture(root)
                source = root / "held.source"
                source.write_text("<p>Unchanged source awaiting discourse-boundary review.</p>")
                held = {key: row[key] for key in ("source_url", "license", "license_url", "conditions", "copyright", "license_notice")}
                held.update(source_snapshot=source.name, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                            status="SOURCE_RIGHTS_VERIFIED_READER_SCOPE_HELD")
                if fault == "license": held["license"] = "CC0-1.0"
                if fault == "source_sha256": held["source_sha256"] = "0" * 64
                if fault == "conditions": held["conditions"] = []
                path.write_text(json.dumps({"schema_version": 1, "records": [row], "held_source_records": [held]}))
                if fault is None:
                    result = verified_manifest(root, path)
                    self.assertEqual(len(result["records"]), 1)
                    self.assertEqual(len(result["held_source_records"]), 1)
                else:
                    with self.assertRaises(ValueError):
                        verified_manifest(root, path)

    def test_review_inputs_intervals_and_selected_canonical_id_are_pinned(self):
        for fault in (None, "source", "canonical", "interval", "canonical_id", "status"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "original.source"
                target = root / "canonical.txt"
                source.write_text("<article><p>First distinctive teaching.</p><p>Second distinctive conclusion.</p></article>")
                target.write_text("X 1 - Example\n\nFirst matching teaching.\nSecond matching conclusion.\n")
                row = {"review_id": "example-comparison", "status": "VERIFIED", "canonical_id": "X 1",
                       "publisher_id": "X 1", "source_url": "https://example.org/text",
                       "source_snapshot": source.name, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                       "canonical_text_path": target.name, "canonical_text_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                       "source_anchors": content_intervals(source, ["First distinctive teaching.", "Second distinctive conclusion."]),
                       "canonical_anchors": content_intervals(target, ["First matching teaching.", "Second matching conclusion."]),
                       "review_basis": "The teaching sequence and conclusion identify the same discourse."}
                if fault == "source": source.write_text("changed original")
                if fault == "canonical": target.write_text("changed comparison")
                if fault == "interval": row["source_anchors"][0]["sha256"] = "0" * 64
                if fault == "canonical_id": row["canonical_id"] = "X 2"
                if fault == "status": row["status"] = "HOLD"
                path = root / IDENTITY_REVIEWS
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps({"records": [row]}))
                if fault is None:
                    self.assertEqual(identity_for_source(row["source_url"], row["source_sha256"], root)["canonical_id"], "X 1")
                    self.assertIsNone(identity_for_source(row["source_url"], "unknown-source-hash", root))
                else:
                    with self.assertRaises(ValueError):
                        identity_for_source(row["source_url"], row["source_sha256"], root)


if __name__ == "__main__":
    unittest.main()
