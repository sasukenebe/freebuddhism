"""Conditional-license boundaries under the owner-approved publication policy."""

import sys
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/buddhist_canon_pipeline"))
from publication_rights import canonical_license, license_conditions, license_url, verified_manifest


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


if __name__ == "__main__":
    unittest.main()
