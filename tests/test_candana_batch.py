import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))

from prepare_candana_batch import (  # noqa: E402
    engine_comparison, nonspace, numbered_book, prepare_batch, prepare_one,
    reflow, safe_relative, canonical_comparison,
)

GRANT = ("Copyright Bhikkhu Candana. You may copy, reprint, republish and redistribute this work "
         "in any medium, provided copies are free of charge and you do not alter its contents.")


class BatchTests(unittest.TestCase):
    def fixture(self, root):
        source = root / "build/cache/fixture.pdf"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"%PDF-fixture-source")
        job = {"url": "https://www.mindreleased.com/s/fixture.pdf", "state": "COLLECTED",
               "cache": "build/cache/fixture.pdf", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
        recipe = {"id": "fixture", "title": "Synthetic book", "source_url": job["url"],
                  "source_sha256": job["sha256"], "layout": "numbered-an-book",
                  "first_page": 2, "last_page": 3, "page_count": 3,
                  "running_heading": "AN II", "closing_marker": "(Here ends the fixture)",
                  "expected_last_number": 3}
        text = (GRANT + "\n1\n\fAN II\nSuttas 1-3\nFirst Vagga\n"
                "1. First Sutta (First teaching)\nKeep every repeated sentence.\n\n"
                "2.\nKeep every repeated sentence.\n\n"
                "   1. An ordinary numbered list, not another sutta.\n2\n\f"
                "AN II\nSuttas 3-3\nThird Vagga\n3.\nA final teaching.\n"
                "(Here ends the fixture)\n3\n\f")
        return job, recipe, text

    def test_numbered_lists_are_not_sutta_headings_and_all_characters_survive(self):
        with tempfile.TemporaryDirectory() as temporary:
            job, recipe, text = self.fixture(Path(temporary))
            result = numbered_book(text, recipe)
        self.assertEqual(result["status"], "PARTITION_CHECK_PASSED")
        self.assertEqual(len(result["sections"]), 3)
        self.assertIn("ordinary numbered list", result["sections"][1]["body"])
        self.assertNotIn("Third Vagga", result["sections"][1]["body"])
        self.assertIn("Third Vagga", result["sections"][2]["body"])
        self.assertEqual(result["sections"][2]["source_page"], 3)
        self.assertEqual(nonspace("".join(row["body"] for row in result["sections"])), nonspace(result["body"]))

    def test_gaps_duplicates_and_suffixed_numbers_are_held_not_repaired(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, recipe, text = self.fixture(Path(temporary))
        for replacement in ("4.", "1.", "2a. Other Sutta"):
            result = numbered_book(text.replace("\n2.\n", "\n" + replacement + "\n"), recipe)
            self.assertEqual(result["status"], "NUMBERING_REVIEW_REQUIRED")
            self.assertEqual(result["sections"], [])
            self.assertTrue(result["numbering_exceptions"])

    def test_grouped_source_ranges_are_preserved_without_expansion(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, recipe, text = self.fixture(Path(temporary))
        recipe["expected_last_number"] = 8
        result = numbered_book(text.replace("\n3.\n", "\n3-8.\n"), recipe)
        self.assertEqual(result["status"], "PARTITION_CHECK_PASSED")
        self.assertEqual(result["source_numbers"], 8)
        self.assertEqual(result["sections"][-1]["source_label"], "3-8")

    def test_moved_closing_marker_and_changed_page_count_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, recipe, text = self.fixture(Path(temporary))
        for wrong in (text.replace("(Here ends the fixture)", ""), text + "extra page\f"):
            with self.assertRaises(ValueError):
                numbered_book(wrong, recipe)

    def test_comparison_detects_order_accents_ligatures_and_page_count(self):
        self.assertEqual(engine_comparison("a b\f", "ab\n\f")["mismatched_pages"], [])
        for right in ("ba\f", "áb\f", "aﬂ\f", "ab\fextra\f"):
            self.assertTrue(engine_comparison("ab\f", right)["mismatched_pages"])

    def test_canonical_comparison_does_not_hide_ligatures_order_or_missing_accents(self):
        self.assertEqual(canonical_comparison("a\u0304", "ā")["mismatched_pages"], [])
        for left, right in [("ā", "a"), ("ﬁ", "fi"), ("ab", "ba"), ("word", "words")]:
            self.assertTrue(canonical_comparison(left, right)["mismatched_pages"])
        self.assertFalse(canonical_comparison("a", "a")["publication_approval"])

    def test_raw_agreement_is_diagnostic_and_never_clears_review_gates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, _, text = self.fixture(root)
            wrong = text.replace("final teaching", "teaching final")
            def extract(_path, engine):
                return wrong if engine == "poppler" else text
            report, _ = prepare_one(job, None, root, root / "build/review/source", "test", extract)
            self.assertEqual(report["raw_comparison"]["mismatched_pages"], [])
            self.assertIn("EXTRACTOR_DISAGREEMENT", report["issues"])
            self.assertIn("LAYOUT_REVIEW_REQUIRED", report["issues"])
            self.assertFalse(report["publishable"])
            self.assertEqual(report["canonical_mapping_status"], "NOT_REVIEWED")
            self.assertIn("poppler-raw.txt", report["output_hashes"])

    def test_only_pinned_recipes_can_ignore_a_unique_edge_page_number(self):
        left, right = "First teaching.\n1\n\f", "1\nFirst teaching.\n\f"
        self.assertEqual(engine_comparison(left, right)["mismatched_pages"], [1])
        result = engine_comparison(left, right, pagination=True)
        self.assertEqual(result["mismatched_pages"], [])
        self.assertEqual(result["pagination_only_pages"], [1])
        for unsafe in ("Middle\n1\nbody.\f", "1\nFirst teaching.\n1\f", "2\nFirst teaching.\f"):
            self.assertEqual(engine_comparison(left, unsafe, pagination=True)["mismatched_pages"], [1])

    def test_reflow_changes_only_whitespace_and_does_not_guess_hyphenation(self):
        self.assertEqual(reflow("  repeated\n words.\n\nAn unknown-\ncompound."),
                         "repeated words.\n\nAn unknown- compound.\n")

    def test_hyphen_policy_keeps_the_hyphen_and_never_joins_paragraphs(self):
        value = "A self-\nexplanatory phrase.\n\nAnother-\n\nparagraph."
        result = reflow(value, join_hyphen_wraps=True)
        self.assertEqual(result, "A self-explanatory phrase.\n\nAnother-\n\nparagraph.\n")
        self.assertEqual(nonspace(value), nonspace(result))

    def test_explicit_suffixed_source_sequence_preserves_both_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, recipe, text = self.fixture(Path(temporary))
        text = text.replace("\n2.\n", "\n2a.\nAn extra teaching.\n\n2b.\n")
        recipe["suffix_numbers"] = {"2": ["a", "b"]}
        result = numbered_book(text, recipe)
        self.assertEqual(result["status"], "PARTITION_CHECK_PASSED")
        self.assertEqual([row["source_label"] for row in result["sections"]], ["1", "2a", "2b", "3"])
        self.assertEqual(result["source_numbers"], 4)

    def test_unchanged_sources_are_reused_without_another_conversion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, recipe, text = self.fixture(root)
            extractor = Mock(return_value=text)
            args = (job, recipe, root, root / "build/review/source", "test-tool", extractor)
            first, reused = prepare_one(*args)
            self.assertFalse(reused)
            second, reused = prepare_one(*args)
            self.assertTrue(reused)
            self.assertEqual(extractor.call_count, 2)
            self.assertEqual(first, second)
            self.assertFalse(first["publishable"])
            self.assertEqual(first["status"], "READY_FOR_VISUAL_REVIEW")

    def test_modified_draft_or_recipe_invalidates_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, recipe, text = self.fixture(root)
            extractor = Mock(return_value=text)
            directory = root / "build/review/source"
            args = (job, recipe, root, directory, "test-tool", extractor)
            prepare_one(*args)
            (directory / "sections/1.txt").write_text("changed")
            self.assertFalse(prepare_one(*args)[1])
            recipe["title"] = "Changed configuration"
            self.assertFalse(prepare_one(*args)[1])
            self.assertEqual(extractor.call_count, 6)

    def test_modified_pdf_is_not_converted_even_with_a_cached_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, recipe, text = self.fixture(root)
            extractor = Mock(return_value=text)
            args = (job, recipe, root, root / "build/review/source", "test-tool", extractor)
            prepare_one(*args)
            (root / job["cache"]).write_bytes(b"%PDF-changed")
            with self.assertRaisesRegex(ValueError, "recorded source bytes"):
                prepare_one(*args)
            self.assertEqual(extractor.call_count, 2)

    def test_failed_source_does_not_link_to_an_old_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, recipe, text = self.fixture(root)
            args = (root, root / "build/review", [recipe], [job], 1, "test")
            prepare_batch(*args, extractor=Mock(return_value=text))
            (root / job["cache"]).write_bytes(b"%PDF-changed")
            report = prepare_batch(*args, extractor=Mock(return_value=text))
            self.assertIsNone(report["sources"][0]["review_path"])
            self.assertEqual(report["sources"][0]["status"], "SOURCE_REVIEW_REQUIRED")

    def test_missing_permission_disagreement_and_unreviewed_layout_are_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, _, text = self.fixture(root)
            raw = text.replace(GRANT, "Copyright only; free to download.")
            extractor = Mock(side_effect=[raw, raw.replace("final teaching", "teaching final")])
            report, _ = prepare_one(job, None, root, root / "build/review/source", "test", extractor)
            self.assertEqual(set(report["issues"]), {
                "PERMISSION_REVIEW_REQUIRED", "EXTRACTOR_DISAGREEMENT", "LAYOUT_REVIEW_REQUIRED"})
            self.assertFalse(report["publishable"])
            self.assertEqual(report["sections"], [])

    def test_changed_recipe_source_never_uses_old_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, recipe, text = self.fixture(root)
            recipe["source_sha256"] = "0" * 64
            report, _ = prepare_one(job, recipe, root, root / "build/review/source", "test", Mock(return_value=text))
            self.assertIn("RECIPE_SOURCE_CHANGED", report["issues"])
            self.assertEqual(report["sections"], [])

    def test_batch_is_bounded_resumable_and_does_not_modify_queue_or_public_texts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, recipe, text = self.fixture(root)
            jobs = [job, dict(job, url="https://www.mindreleased.com/s/second.pdf")]
            queue_before = json.dumps(jobs)
            extractor = Mock(return_value=text)
            args = (root, root / "build/batch-review", [recipe], jobs, 1, "test-tool")
            first = prepare_batch(*args, extractor=extractor)
            self.assertEqual(first["processed_this_run"], 1)
            self.assertEqual(first["remaining_uncached"], 1)
            second = prepare_batch(*args, extractor=extractor)
            self.assertEqual(second["processed_this_run"], 1)
            self.assertEqual(second["reused_reports"], 1)
            third = prepare_batch(*args, extractor=extractor)
            self.assertEqual(third["processed_this_run"], 0)
            self.assertEqual(third["reused_reports"], 2)
            self.assertEqual(extractor.call_count, 4)
            self.assertEqual(json.dumps(jobs), queue_before)
            self.assertFalse((root / "metadata/eligible-texts.json").exists())
            self.assertEqual(third["network_requests"], 0)

    def test_private_output_refuses_public_or_existing_unmarked_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "build/existing-site"
            output.mkdir(parents=True)
            (output / "index.html").write_text("Existing site")
            for wrong in (root, root / "theravada/review", output):
                with self.assertRaises(ValueError):
                    prepare_batch(root, wrong, [], [], 1, "test-tool")
            self.assertEqual((output / "index.html").read_text(), "Existing site")

    def test_paths_cannot_escape_through_traversal_or_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "linked").symlink_to(root)
            for wrong in ("../other", "/etc/passwd", "linked/file", "bad\\path"):
                with self.assertRaises(ValueError):
                    safe_relative(root, wrong)


if __name__ == "__main__":
    unittest.main()
