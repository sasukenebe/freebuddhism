# SPDX-License-Identifier: 0BSD
"""Complete-source acceptance and corruption tests for the private SC preparer."""
from collections import Counter
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
import prepare_sc_licensed as sc


class SourceComparisonTests(unittest.TestCase):
    def source(self):
        # Middle paragraphs, adjacent inline labels, line breaks and an endnote.
        return ("<article id='ne1'><header><h1>Title</h1></header>"
                "<p>First <i>word</i>.</p><p>Middle sentinel.</p>"
                "<blockquote><p>Verse one<br>Verse two</p></blockquote>"
                "<p>Last <a class='ref'>PTS 2</a><a class='ref'>PTS 3</a>text.</p>"
                "<dl><dt>1.</dt><dd>Complete note.</dd></dl>"
                "<footer><p>Entire grant.</p></footer></article>")

    def test_whole_source_rejects_omission_reordering_duplication_and_unicode_change(self):
        region = self.source()
        node = sc.Tree(region).root.find("article")[0]
        body = sc.render(node)
        self.assertEqual(sc.compare_region(region, body, node)["source_comparison"], "PASS")
        variants = [body.replace("Middle sentinel.", ""),
                    body.replace("First word.", "Last word."),
                    body.replace("Middle sentinel.", "Middle sentinel. Middle sentinel."),
                    body.replace("Complete note.", ""),
                    body.replace("Entire grant.", ""),
                    body.replace("PTS 2", ""),
                    body.replace("Verse one", "Verse оne")]
        # Reordering preserves the character multiset but must still fail.
        variants.append(body.replace("First word.", "TOKEN").replace("Middle sentinel.", "First word.").replace("TOKEN", "Middle sentinel."))
        for changed in variants:
            self.assertNotEqual(changed, body, "A corruption fixture must actually change the source")
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "Whole-source"):
                sc.compare_region(region, changed, node)

    def test_stanza_paragraph_breaks_and_inline_references_are_preserved(self):
        region = self.source()
        node = sc.Tree(region).root.find("article")[0]
        body = sc.render(node)
        self.assertIn("Verse one\nVerse two\n\n", body)
        self.assertIn("First word.\n\nMiddle sentinel.", body)
        self.assertIn("PTS 2 PTS 3 text.", body)
        with self.assertRaisesRegex(ValueError, "paragraph/stanza"):
            sc.compare_region(region, body.replace("Verse one\nVerse two", "Verse one Verse two"), node)

    def test_html_ordered_list_start_type_and_nonmonotonic_source_order_remain(self):
        region = ("<article><ol start='9'><li>Ninth</li><li>Tenth</li></ol>"
                  "<ol start='51'><li>Fifty-first</li></ol>"
                  "<ol start='48'><li>Forty-eighth</li></ol>"
                  "<ol type='i'><li>Roman one</li><li>Roman two</li></ol></article>")
        node = sc.Tree(region).root.find("article")[0]
        body = sc.render(node)
        self.assertIn("9. Ninth\n\n10. Tenth", body)
        self.assertLess(body.index("51. Fifty-first"), body.index("48. Forty-eighth"))
        self.assertIn("i. Roman one\n\nii. Roman two", body)
        sc.compare_region(region, body, node)

    def test_optional_p_before_footer_does_not_swallow_or_duplicate_footer(self):
        region = "<article><p>Original text.</p><p><footer><p>Full grant.</p></footer></article>"
        node = sc.Tree(region).root.find("article")[0]
        body = sc.render(node)
        self.assertEqual(body.count("Full grant."), 1)
        sc.compare_region(region, body, node)

    def test_changed_hash_duplicate_inventory_and_escaping_paths_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                sc.checked(source, sc.digest(b"altered"))
            for path in ("../escape", "/absolute", "a\\b"):
                with self.assertRaises(ValueError):
                    sc.safe_path(root, path)
            (root / "link").symlink_to(root / "source")
            with self.assertRaises(ValueError):
                sc.safe_path(root, "link")
        with self.assertRaisesRegex(ValueError, "inventory"):
            sc.inventory([{"id": "ne1"}, {"id": "ne1"}], {"ne1", "ne2"}, "id")

    def test_overwrite_refusal_is_preflight_and_check_is_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            files = {"one.txt": b"one", "two.txt": b"two"}
            sc.write_plan(files, output)
            sc.write_plan(files, output)
            sc.write_plan(files, output, check=True)
            (output / "two.txt").write_bytes(b"user change")
            with self.assertRaisesRegex(ValueError, "Refusing"):
                sc.write_plan({"new.txt": b"new", **files}, output)
            self.assertFalse((output / "new.txt").exists())
            self.assertEqual((output / "two.txt").read_bytes(), b"user change")
            with self.assertRaisesRegex(ValueError, "Missing"):
                sc.write_plan({"absent.txt": b"absent"}, output, check=True)
            self.assertFalse((output / "absent.txt").exists())


class AllPinnedSourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not sc.OUTPUT.joinpath("proposal.json").exists() or not sc.PTS_SNAPSHOT.exists() or not sc.LEGACY.exists():
            raise unittest.SkipTest("Original local source batch is not present; source fixtures still run")
        cls.proposal, cls.files = sc.make_plan()
        cls.rows = cls.proposal["records"]
        cls.by_id = {row["canonical_id"]: row for row in cls.rows}

    def test_all_eligible_batches_and_original_identifiers_are_present_once(self):
        self.assertEqual(len(self.rows), 649)
        self.assertEqual(Counter(r["version_slug"] for r in self.rows), {"walters": 601, "nanamoli": 46, "ireland": 2})
        self.assertEqual({r["canonical_id"] for r in self.rows if r["version_slug"] == "walters"},
                         {*(f"Tha Ap {i}" for i in range(1, 562)), *(f"Thi Ap {i}" for i in range(1, 41))})
        self.assertEqual({r["canonical_id"] for r in self.rows if r["collection"].endswith("nettipakarana")},
                         {f"Ne {i}" for i in range(1, 38)})
        self.assertEqual({r["canonical_id"] for r in self.rows if r["collection"].endswith("petakopadesa")},
                         {f"Pe {i}" for i in range(1, 10)})
        self.assertNotIn("Tha Ap 562", self.by_id)
        self.assertNotIn("Ps complete", self.by_id)

    def test_exact_import_contract_all_body_snapshot_and_rights_hashes(self):
        fields = {"canonical_id", "collection", "title", "translator", "version_slug", "source_url", "license", "license_url",
                  "copyright", "license_notice", "body_path", "body_sha256", "source_snapshot", "source_sha256",
                  "source_revision", "upstream_file", "source_comparison", "source_comparison_method",
                  "completeness_status", "completeness_scope", "exceptions", "prior_record_id"}
        from publication_rights import canonical_license, license_url
        for row in self.rows:
            with self.subTest(source=row["canonical_id"]):
                self.assertTrue(fields <= row.keys())
                self.assertTrue(row["source_url"].startswith("https://"))
                self.assertTrue(row["copyright"].strip())
                self.assertEqual(row["source_comparison"], "PASS")
                self.assertEqual(sc.digest(self.files[row["body_path"]]), row["body_sha256"])
                self.assertEqual(sc.digest(self.files[row["source_snapshot"]]), row["source_sha256"])
                self.assertTrue(self.files[row["body_path"]].endswith(b"\n"))
                if row["license"] != sc.FREE_GRANT:
                    self.assertEqual(canonical_license(row["license"]), row["license"])
                    self.assertEqual(license_url(row["license"]), row["license_url"])
        evidence = json.loads(self.files["rights-evidence.json"])
        self.assertEqual(len(evidence["records"]), 649)
        for row in evidence["records"]:
            self.assertEqual(sc.digest(self.files[row["evidence_snapshot"]]), row["evidence_sha256"])
            self.assertEqual(sc.digest(self.files[row["source_snapshot"]]), row["source_sha256"])
        checksums = json.loads(self.files["checksums.json"])
        self.assertEqual(set(checksums), set(self.files) - {"checksums.json"})
        for path, sha in checksums.items():
            self.assertEqual(sc.digest(self.files[path]), sha)

    def test_walters_exact_edition_grant_and_heading_discrepancies(self):
        for row in self.rows:
            if row["version_slug"] != "walters":
                continue
            self.assertEqual(row["license"], "CC-BY-NC-SA-3.0-US")
            self.assertIn(sc.WALTERS_NOTICE, row["license_notice"])
            self.assertIn("no separate copyright", row["copyright"].lower())
            source_id = Path(row["body_path"]).stem
            node, region, _ = sc.article(self.files[row["source_snapshot"]], source_id)
            if source_id == "tha-ap3":
                self.assertEqual(row["title"], "1. Sāriputta")
                self.assertTrue(any("source heading prints 1." in e for e in row["exceptions"]))
            footer = node.find("footer")[0]
            footer.children.append(" Changed rights.")
            with self.assertRaisesRegex(ValueError, "footer grant"):
                sc.footer_rights(node, region, True, "")

    def test_unknown_is_not_complete_and_printed_elisions_are_not_expanded(self):
        statuses = Counter(r["completeness_status"] for r in self.rows)
        self.assertEqual(statuses, {"COMPLETE": 603, "ABBREVIATED": 39, "UNKNOWN": 7})
        for canonical in ("Ne 1", "Ne 2", "Ne 3", "Ne 7", "Ne 8", "Ne 11", "Ne 22"):
            self.assertEqual(self.by_id[canonical]["completeness_status"], "UNKNOWN")
        for i in range(1, 10):
            row = self.by_id[f"Pe {i}"]
            self.assertEqual(row["completeness_status"], "ABBREVIATED")
            body = self.files[row["body_path"]].decode()
            self.assertIn("…", body)
            self.assertIn("This version has not been proofread.", body)
            self.assertIn("Prepared in laTex by Manfred Wierich", body)
        self.assertIn("51. Expressed in Terms of Our Own Statement", self.files["bodies/pe2.txt"].decode())
        self.assertTrue(any("continues into Pe 8" in e for e in self.by_id["Pe 7"]["exceptions"]))

    def test_ireland_full_grant_stanzas_speakers_and_numbered_note(self):
        for number in (16, 35):
            row = self.by_id[f"Vv {number}"]
            self.assertEqual(row["license"], sc.FREE_GRANT)
            self.assertEqual(row["explicit_grant"], sc.IRELAND_GRANT)
            self.assertIn(sc.IRELAND_GRANT, row["license_notice"])
            self.assertIn("reprint-no-more-than-50-copies", row["conditions"])
            body = self.files[row["body_path"]].decode()
            self.assertIn("[Vangisa:]", body)
            self.assertIn("©1997 John D. Ireland.", body)
            revision = "2" if number == 16 else "30"
            self.assertIn(f"Last revised for Access to Insight on {revision} November 2013.", body)
        body = self.files["bodies/vv35.txt"].decode()
        self.assertIn("Upatissa[1]", body)
        self.assertIn("Notes\n\n1.\n\nThe personal name of Sariputta", body)

    def test_held_whole_pdf_has_reproducible_evidence_without_a_publishable_record(self):
        held = self.proposal["held"]
        self.assertEqual(len(held), 1)
        row = held[0]
        self.assertEqual(row["decision"], "HOLD_EXTRACTION_ORDER")
        self.assertEqual(row["completeness_status"], "UNKNOWN")
        self.assertTrue(row["existing_matches_fresh_layout_extraction"])
        self.assertEqual((row["poppler_pages"], row["mupdf_pages"]), (664, 664))
        self.assertEqual(len(row["different_order_pages"]), 154)
        self.assertEqual(row["different_character_multiset_pages"], [])
        self.assertEqual(sc.digest(self.files[row["source_snapshot"]]), row["source_sha256"])
        self.assertEqual(len(json.loads(self.files["assessment/path-of-discrimination/comparison.json"])["page_audit"]), 664)

    def test_prepared_output_is_exact_and_all_prior_ids_match_existing_exclusions(self):
        sc.write_plan(self.files, check=True)
        prior = {r["record_key"]: r for r in json.loads((ROOT / "metadata/reports/strict-license-classification-2026-10.json").read_text())["records"]}
        for row in self.rows:
            previous = prior[row["prior_record_id"]]
            self.assertEqual((previous["canonical_id"], previous["collection_path"], previous["source_url"]),
                             (row["canonical_id"], row["collection"], row["source_url"]))


if __name__ == "__main__":
    unittest.main()
