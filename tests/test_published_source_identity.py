# SPDX-License-Identifier: 0BSD
"""Real retained sources and every known wrong association remain regression inputs."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
from publication_rights import verified_manifest, verify_published_source
from prepare_ati_licensed import split_publisher_references, region


class PublishedSourceIdentityTests(unittest.TestCase):
    def test_every_published_protected_source_recompares_with_its_actual_id_and_body(self):
        rows = json.loads((ROOT / "metadata/source-manifests/licensed-collections.json").read_text())["records"]
        selected = [row for row in rows if row.get("mapping_evidence")]
        self.assertGreater(len(selected), 1700)
        for row in selected:
            with self.subTest(source=row["source_url"]): verify_published_source(row)

    def test_all_30_corrected_associations_reject_their_previous_wrong_target(self):
        rows = json.loads((ROOT / "metadata/source-manifests/licensed-collections.json").read_text())["records"]
        changes = json.loads((ROOT / "metadata/reports/licensed-identity-corrections-2026-11-11.json").read_text())["corrections"]
        corrections = [row for row in changes if row["action"] == "CORRECTED"]
        self.assertEqual(len(corrections), 30)
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "manifest.json"
            for change in corrections:
                original = next(r for r in rows if r["source_url"] == change["source_url"] and r["version"] == change["version"])
                with self.subTest(source=change["source_url"], wrong=change["previous_canonical_id"]):
                    candidate.write_text(json.dumps({"schema_version": 1, "records": [original]}))
                    self.assertEqual(verified_manifest(ROOT, candidate)["records"][0]["canonical_id"], change["canonical_id"])
                    broken = copy.deepcopy(original)
                    broken["canonical_id"] = change["previous_canonical_id"]
                    candidate.write_text(json.dumps({"schema_version": 1, "records": [broken]}))
                    with self.assertRaisesRegex(ValueError, "does not match its content review"):
                        verified_manifest(ROOT, candidate)

    def test_actual_publisher_references_and_dn1_headings_are_preserved(self):
        rows = json.loads((ROOT / "metadata/source-manifests/licensed-collections.json").read_text())["records"]
        for url in ("https://www.dhammatalks.org/suttas/DN/DN01.html", "https://www.dhammatalks.org/suttas/AN/AN10_76.html"):
            row = next(r for r in rows if r["source_url"] == url)
            body, references = split_publisher_references(region((ROOT / row["source_snapshot"]).read_text(), "sutta"))
            self.assertNotIn("See also:", body)
            self.assertTrue(references.startswith("See also:"))
            if "DN01" in url:
                self.assertIn("Eternalism", body)
                self.assertIn("Partial Eternalism", body)

    def test_all_five_held_real_sources_are_rejected_as_single_bodies(self):
        held = json.loads((ROOT / "metadata/source-manifests/licensed-collections.json").read_text())["held_source_records"]
        self.assertEqual(len(held), 5)
        for row in held:
            with self.subTest(source=row["source_url"]), self.assertRaisesRegex(ValueError, "Multiple explicit discourse headers|Publisher-reference"):
                split_publisher_references(region((ROOT / row["source_snapshot"]).read_text(), "sutta"))
