# SPDX-License-Identifier: 0BSD
"""An individual-sharing permission must not become a bulk-distribution grant."""
import copy
import json
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
from distribution_policy import INDIVIDUAL_LICENSE, INDIVIDUAL_DISTRIBUTION, distribution
from archive_rights import edition_rights
from build_deploy_site import _write_continuous_reader, _zip_write
from suttafriends_rights import verify_source_exports, EXPORT_RULES


class IndividualDistributionTests(unittest.TestCase):
    def limited(self):
        return {"license": INDIVIDUAL_LICENSE, "distribution": dict(INDIVIDUAL_DISTRIBUTION),
                "source_url": "https://example.org/individual", "version": "individual"}

    def test_individual_grant_requires_exact_boolean_distribution_limits(self):
        row = self.limited()
        self.assertFalse(distribution(row)["site_archives"])
        for fault in ("missing", "archive", "continuous", "source", "integer"):
            broken = copy.deepcopy(row)
            if fault == "missing": broken.pop("distribution")
            else:
                key = {"archive": "site_archives", "continuous": "continuous_reader", "source": "source_archives", "integer": "individual_readers"}[fault]
                broken["distribution"][key] = 1 if fault == "integer" else True
            with self.subTest(fault=fault), self.assertRaises(ValueError): distribution(broken)
        with self.assertRaises(ValueError): distribution({"license": "Unreviewed", "distribution": INDIVIDUAL_DISTRIBUTION})

    def test_archive_cannot_bypass_individual_terms_by_setting_archive_true(self):
        row = self.limited()
        with self.assertRaisesRegex(ValueError, "cannot enter"): edition_rights(row)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "individual.txt"
            path.write_text("Synthetic individual article.")
            allowed = {Path(path.name): {"source": path, "archive": True, "rights": [row]}}
            with self.assertRaisesRegex(ValueError, "cannot enter"):
                _zip_write(root / "bad.zip", list(allowed), root, allowed)

    def test_individual_only_editions_do_not_enter_continuous_reader_payload(self):
        pages = {"sutta/khuddaka-nikaya/petavatthu/pv01/index.html": {
            "canonical_id": "Pv 1", "title": "Synthetic article", "collection": "khuddaka-nikaya/petavatthu",
            "eligible": [self.limited()]}}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(_write_continuous_reader(root, pages, {}), 0)
            self.assertEqual(json.loads((root / "site/reading-index.json").read_text())["texts"], [])

    def test_source_export_exclusion_cannot_be_removed_or_overridden(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            row = {**self.limited(), "local_path": "theravada/tipitaka/translations/en/licensed/suttafriends/pv1.txt",
                   "source_snapshot": "metadata/source-snapshots/suttafriends-individual/pv1-1.source"}
            attrs = root / ".gitattributes"
            with self.assertRaises(ValueError): verify_source_exports([row], root)
            attrs.write_text("\n".join(EXPORT_RULES) + "\n")
            verify_source_exports([row], root)
            attrs.write_text("\n".join(EXPORT_RULES) + "\n/" + row["local_path"] + " -export-ignore\n")
            with self.assertRaisesRegex(ValueError, "overrides"): verify_source_exports([row], root)

    def test_current_individual_sources_are_independently_recompared(self):
        from publication_rights import verified_manifest, verify_published_source
        rows = [r for r in verified_manifest()["records"] if r["license"] == INDIVIDUAL_LICENSE]
        if not rows:
            self.skipTest("Individual article import has not run")
        self.assertEqual(len(rows), 136)
        for row in rows:
            verify_published_source(row)
            self.assertFalse(distribution(row)["source_archives"])

    def test_git_archive_itself_omits_individual_article_payloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitattributes").write_text("\n".join(EXPORT_RULES) + "\n")
            (root / "README.md").write_text("Synthetic export test.\n")
            from suttafriends_rights import TEXT_DIRECTORY, ARTICLE_DIRECTORY
            limited = [TEXT_DIRECTORY + "pv1.txt", ARTICLE_DIRECTORY + "pv1-1.source"]
            for name in limited:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("Synthetic individual article.\n")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.name=Export Test", "-c", "user.email=export@example.invalid",
                            "commit", "-qm", "Synthetic source export"], cwd=root, check=True)
            exported = subprocess.check_output(["git", "archive", "--format=zip", "HEAD"], cwd=root)
            with zipfile.ZipFile(BytesIO(exported)) as archive:
                self.assertIn("README.md", archive.namelist())
                self.assertFalse(set(archive.namelist()) & set(limited))

    def test_publisher_citation_cannot_match_a_longer_sutta_number(self):
        from prepare_suttafriends import publisher_citation_matches
        self.assertTrue(publisher_citation_matches("Vv 1.1", "Vimana Vatthu Vv 1.1 Paṭhama Pīṭha"))
        self.assertTrue(publisher_citation_matches("Vv 1.1", "Vimāna VatthuVv 1.1 Paṭhama Pīṭha"))
        for heading in ("Vv 1.10 Another story", "Vv 1.1.2 Another text", "NotVv 1.1"):
            self.assertFalse(publisher_citation_matches("Vv 1.1", heading))

    def test_changed_grant_identity_and_source_fragment_are_rejected(self):
        from publication_rights import verified_manifest
        from suttafriends_rights import verify_record
        rows = [r for r in verified_manifest()["records"] if r["license"] == INDIVIDUAL_LICENSE]
        if not rows: self.skipTest("Individual article import has not run")
        row = rows[0]
        for field, value in (("license_notice", "A different permission"), ("permission_source_sha256", "0" * 64),
                             ("canonical_id", "Vv 85"), ("pali_title", "")):
            broken = {**row, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError): verify_record(broken, ROOT)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = root / row["source_snapshot"]
            snapshot.parent.mkdir(parents=True)
            snapshot.write_bytes((ROOT / row["source_snapshot"]).read_bytes() + b"Lost source boundary")
            with self.assertRaisesRegex(ValueError, "fragment changed"): verify_record(row, root)


if __name__ == "__main__": unittest.main()
