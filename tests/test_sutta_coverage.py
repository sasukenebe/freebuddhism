# SPDX-License-Identifier: 0BSD
"""Empty books, grouped IDs and unverified completeness must remain visible."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
from sutta_coverage import atoms, build_report, COLLECTIONS, output_payloads, validate_reference


class SuttaCoverageTests(unittest.TestCase):
    def reference(self):
        prefixes = {value: key.split('/')[-1] for key, value in COLLECTIONS.items()}
        units = [{"id": prefix + "1", "collection": collection, "path": "test", "git_blob": "a" * 40}
                 for collection, prefix in prefixes.items()]
        return {"schema_version": 1, "commit": "f" * 40, "unit_count": len(units), "units": units}

    def edition(self, identifier, collection="anguttara-nikaya", completeness="UNKNOWN", state="BUILD_ELIGIBLE"):
        return {"canonical_id": identifier, "collection": collection, "completeness": completeness,
                "state": state, "source_url": "https://example.org/" + identifier.replace(" ", "")}

    def test_grouped_ranges_are_numbering_only_and_aliases_match(self):
        self.assertEqual(atoms("AN 1.01–3"), {"an1.1", "an1.2", "an1.3"})
        self.assertEqual(atoms("Tha Ap 23"), atoms("tha-ap23"))
        self.assertEqual(atoms("Khp 1"), atoms("kp1"))
        self.assertEqual(atoms("Mil complete"), set())
        for invalid in ("AN 1.3-2", "AN 1.1-10002"):
            with self.assertRaises(ValueError): atoms(invalid)

    def test_unknown_completeness_is_not_complete_and_excluded_sources_do_not_count(self):
        ref = self.reference()
        result = build_report(ref, [self.edition("AN 1"), self.edition("Bv 1", "khuddaka-nikaya/buddhavamsa", state="RIGHTS_UNVERIFIED")], {})
        row = next(r for r in result["units"] if r["id"] == "an1")
        self.assertEqual(row["availability"], "AVAILABLE")
        self.assertEqual(row["completeness"], "AVAILABLE_COMPLETENESS_UNVERIFIED")
        self.assertFalse(row["semantic_identity_fully_audited"])
        self.assertEqual(next(r for r in result["units"] if r["id"] == "bv1")["availability"], "NO_LOCAL_EDITION")

    def test_group_is_not_available_when_one_member_is_missing(self):
        ref = self.reference()
        row = next(r for r in ref["units"] if r["id"] == "an1")
        row["id"] = "an1.1-3"
        report = build_report(ref, [self.edition("AN 1.1-2", completeness="COMPLETE")], {})
        row = next(r for r in report["units"] if r["id"] == "an1.1-3")
        self.assertEqual(row["availability"], "PARTLY_AVAILABLE")
        self.assertEqual(row["missing_atoms"], ["an1.3"])
        self.assertNotEqual(row["completeness"], "COMPLETE_WITHIN_RECORDED_SCOPE")

    def test_empty_books_remain_and_absent_reference_book_is_an_error(self):
        ref = self.reference()
        report = build_report(ref, [], {})
        self.assertEqual(len(report["collections"]), len(set(COLLECTIONS.values())))
        self.assertEqual(report["availability"], {"NO_LOCAL_EDITION": ref["unit_count"]})
        ref["units"].pop()
        ref["unit_count"] -= 1
        with self.assertRaisesRegex(ValueError, "disappeared"): build_report(ref, [], {})

    def test_complete_label_is_scope_limited_and_whole_books_not_silently_expanded(self):
        report = build_report(self.reference(), [self.edition("AN 1", completeness="COMPLETE"),
                              self.edition("Mil complete", "khuddaka-nikaya/milindapanha", "COMPLETE")], {})
        self.assertEqual(next(r for r in report["units"] if r["id"] == "an1")["completeness"], "COMPLETE_WITHIN_RECORDED_SCOPE")
        self.assertEqual(len(report["unmatched_edition_identifiers"]), 1)
        self.assertEqual(next(r for r in report["units"] if r["id"] == "mil1")["availability"], "NO_LOCAL_EDITION")

    def test_verified_whole_book_is_not_falsely_reported_as_missing_english_text(self):
        report = build_report(self.reference(), [], {}, {"khuddaka-nikaya/milindapanha": {
            "pdfs": [{"source_url": "https://example.org/original-complete-book"}]}})
        row = next(r for r in report["units"] if r["id"] == "mil1")
        self.assertEqual(row["availability"], "WHOLE_BOOK_ALIGNMENT_PENDING")
        self.assertEqual(row["unsegmented_book_sources"], ["https://example.org/original-complete-book"])
        self.assertEqual(row["completeness"], "WHOLE_BOOK_SCOPE_ALIGNMENT_UNVERIFIED")
        self.assertFalse(row["semantic_identity_fully_audited"])

    def test_checked_in_report_is_reproducible_and_has_deferred_abhidhamma(self):
        ref = json.loads((ROOT / "metadata/sutta-reference-units.json").read_text())
        for path, expected in output_payloads(ref).items():
            self.assertEqual((ROOT / path).read_bytes(), expected)
        report = json.loads((ROOT / "metadata/reports/sutta-coverage-current.json").read_text())
        self.assertIn("Abhidhamma deferred until last", report["active_path"])
        self.assertFalse(any("abhidhamma" in row["collection"] for row in report["units"]))

    def test_reference_cannot_drop_a_niddesa_half_or_change_collection(self):
        ref = json.loads((ROOT / "metadata/sutta-reference-units.json").read_text())
        validate_reference(ref)
        import copy
        for fault in ("subdivision", "collection", "duplicate", "path"):
            broken = copy.deepcopy(ref)
            if fault == "subdivision":
                broken["units"] = [row for row in broken["units"] if not row["id"].startswith("mnd")]
                broken["unit_count"] = len(broken["units"])
            elif fault == "collection": broken["units"][0]["collection"] = "abhidhamma"
            elif fault == "duplicate": broken["units"][0] = broken["units"][1]
            elif fault == "path": broken["units"][0]["path"] = "../escape.json"
            with self.subTest(fault=fault), self.assertRaises(ValueError): validate_reference(broken)


if __name__ == "__main__": unittest.main()
