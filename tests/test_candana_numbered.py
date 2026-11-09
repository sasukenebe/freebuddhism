import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
from candana_numbered_books import book_three_map, mappings, verify  # noqa: E402
from import_candana import verified_manifest, install as install_legacy  # noqa: E402


class NumberedBookTests(unittest.TestCase):
    def test_source_validator_package_entry_point(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from buddhist_canon_pipeline.import_candana import verified_manifest as package_manifest
        self.assertEqual(len(package_manifest(require_review=True)["texts"]), 874)

    def test_legacy_installer_cannot_discard_the_expanded_collection(self):
        with self.assertRaisesRegex(ValueError, "would discard numbered imports"):
            install_legacy(ROOT / "build/not-a-source-directory")

    def test_book_three_map_preserves_suffixed_and_compound_sources(self):
        mapping = book_three_map()
        self.assertEqual(set(mapping), {f"AN 3.{number}" for number in range(1, 156)})
        self.assertEqual(mapping["AN 3.81"], ["81a"])
        self.assertEqual(mapping["AN 3.82"], ["81b"])
        self.assertEqual(mapping["AN 3.93"], ["92a"])
        self.assertEqual(mapping["AN 3.94"], ["92b"])
        self.assertEqual(mapping["AN 3.99"], ["97", "98"])
        self.assertEqual(mapping["AN 3.100"], ["99"])
        self.assertEqual(mapping["AN 3.115"], ["114"])
        self.assertNotIn("AN 3.156", mapping)
        used = [label for labels in mapping.values() for label in labels]
        self.assertEqual(len(used), len(set(used)))

    def test_book_two_requires_complete_partition_and_cannot_cut_a_source_range(self):
        sections = [{"source_label": "1", "first": 1, "last": 1},
                    {"source_label": "2-479", "first": 2, "last": 479}]
        result = mappings("an-book2", sections, [{"canonical_id": "AN 2.1"}, {"canonical_id": "AN 2.2-479"}])
        self.assertEqual(result["AN 2.2-479"], ["2-479"])
        with self.assertRaisesRegex(ValueError, "split, omit or repeat"):
            mappings("an-book2", sections, [{"canonical_id": "AN 2.1-5"}])

    def test_numbered_sources_readers_and_reports_match_pinned_books(self):
        manifest = verified_manifest(require_review=True)
        rows = [row for row in manifest["texts"] if row["book"] in {"an-book2", "an-book3"}]
        self.assertEqual(len(rows), 349)
        self.assertEqual(sum(row["book"] == "an-book2" for row in rows), 194)
        combined = next(row for row in rows if row["canonical_id"] == "AN 3.99")
        self.assertEqual(combined["source_labels"], ["97", "98"])
        body = (ROOT / combined["local_path"]).read_text().split("\n\n", 1)[1]
        self.assertIn("97. Potthaka Sutta", body)
        self.assertIn("98. Kāsikam Vattha Sutta", body)
        self.assertNotIn("AN 3.163", {row["canonical_id"] for row in rows})

    def test_numbered_review_rejects_changed_report(self):
        manifest = json.loads((ROOT / "metadata/source-manifests/candana.json").read_text())
        original = Path.read_text
        def read(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            if path.name == "candana-numbered-books-2026-11-07.json":
                report = json.loads(value)
                report["recipe_sha256"] = "0" * 64
                return json.dumps(report)
            return value
        with patch.object(Path, "read_text", read):
            with self.assertRaisesRegex(ValueError, "missing or stale"):
                verify(ROOT, manifest, require_review=True)


if __name__ == "__main__":
    unittest.main()
