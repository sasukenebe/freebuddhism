from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
from candana_review import (  # noqa: E402
    inventory, marked_pair, page_reviews, comparison_html, review_catalog, spacing_pages,
)
from prepare_candana_batch import engine_comparison, prepare_batch, prepare_one  # noqa: E402
import test_candana_batch as batch_fixtures  # noqa: E402


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


class ReviewTests(unittest.TestCase):
    def test_marks_preserve_every_original_character_and_escape_html(self):
        original = 'A <script> & ā\n\nmissing text ﬁ\tend.'
        other = 'A <script> & ā\n\ntext\tend.'
        for value, marked in zip((original, other), marked_pair(original, other)):
            parser = PlainText()
            parser.feed(marked)
            self.assertEqual("".join(parser.parts), value)
            self.assertNotIn("<script>", marked)
            self.assertIn("<mark>", marked)

    def test_word_boundary_difference_cannot_hide_behind_character_agreement(self):
        left, right = "fi\nlling a bowl\f", "filling a bowl\f"
        self.assertEqual(engine_comparison(left, right)["mismatched_pages"], [])
        self.assertEqual(spacing_pages(left, right), [1])
        self.assertEqual(spacing_pages("a\n bowl", "a bowl"), [])
        rows = page_reviews(left, right, engine_comparison(left, right), left, [])
        self.assertIn("LAYOUT_WORD_BOUNDARY_REVIEW", rows[0]["flags"])
        self.assertIn("RAW_WORD_BOUNDARY_REVIEW", rows[0]["flags"])

    def test_all_pages_including_final_missing_page_are_enumerated(self):
        left = "".join(f"wrong {i}\f" for i in range(1, 82))
        right = "".join(f"correct {i}\f" for i in range(1, 83))
        rows = page_reviews(left, right, engine_comparison(left, right), None, [])
        self.assertEqual([r["page"] for r in rows], list(range(1, 83)))
        self.assertIn("MISSING_EXTRACTED_PAGE", rows[-1]["flags"])
        page = comparison_html("Synthetic <title>", left, right, None, rows)
        self.assertIn('id="pdf-page-82"', page)
        self.assertIn('href="source.pdf#page=82"', page)
        self.assertIn("Synthetic &lt;title&gt;", page)

    def test_unicode_equivalence_pagination_and_hyphens_are_distinct(self):
        left, right = "ā\ftext\n2\fword-\nwrap\f", "ā\f2\ntext\fword-wrap\f"
        rows = page_reviews(left, right, engine_comparison(left, right, True), right,
                            [{"page": 3, "left": "word-", "right": "wrap"}])
        self.assertIn("CANONICALLY_EQUIVALENT_UNICODE", rows[0]["flags"])
        self.assertEqual(rows[1]["flags"], ["RECIPE_RECOGNIZED_PAGINATION_POSITION"])
        self.assertIn("HYPHEN_WRAP_REVIEW", rows[2]["flags"])
        self.assertNotIn("RAW_CHARACTER_DISAGREEMENT", rows[0]["flags"])

    def test_complete_inventory_includes_pending_missing_and_discovery_pages(self):
        jobs = [{"url": f"https://www.mindreleased.com/s/{i:03d}.pdf", "state": "COLLECTED",
                 "cache": f"build/cache/{i}.pdf"} for i in range(227)]
        jobs += [{"url": "https://www.mindreleased.com/s/missing.pdf", "state": "MISSING"},
                 {"url": "https://www.mindreleased.com/books", "state": "COLLECTED"}]
        rows = inventory(jobs, [])
        self.assertEqual(len(rows), 229)
        self.assertEqual(sum(r["kind"] == "MISSING_SOURCE" for r in rows), 1)
        self.assertEqual(sum(r["review_state"] == "WAITING_THIS_PASS" for r in rows), 227)
        self.assertTrue(all(r["review_path"] is None and not r["publishable"] for r in rows))
        index, _, plain = review_catalog(rows)
        self.assertIn("226.pdf", index)
        self.assertIn("missing.pdf", plain)
        with self.assertRaises(ValueError):
            inventory(jobs + jobs[:1], [])

    def test_local_pdf_is_hash_identical_and_comparison_tampering_invalidates_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, recipe, text = batch_fixtures.BatchTests().fixture(root)
            extract = Mock(return_value=text)
            directory = root / "build/review/source"
            args = (job, recipe, root, directory, "test", extract)
            report, _ = prepare_one(*args)
            self.assertEqual((directory / "source.pdf").read_bytes(), (root / job["cache"]).read_bytes())
            self.assertIn("comparison.html", report["output_hashes"])
            (directory / "comparison.html").write_text("tampered")
            self.assertFalse(prepare_one(*args)[1])
            self.assertEqual(extract.call_count, 4)

    def test_ungranted_source_stays_private_and_has_marked_comparisons(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, _, _ = batch_fixtures.BatchTests().fixture(root)
            values = {"poppler": "fi\nlling\f", "mupdf": "filling\f", "poppler-raw": "filling\f"}
            report, _ = prepare_one(job, None, root, root / "build/review/source", "test",
                                    lambda _p, engine: values[engine])
            self.assertIn("WORD_BOUNDARY_REVIEW_REQUIRED", report["issues"])
            self.assertIn("PERMISSION_REVIEW_REQUIRED", report["issues"])
            self.assertFalse(report["publishable"])
            self.assertEqual(report["raw_comparison"]["mismatched_pages"], [])
            self.assertTrue(report["page_reviews"])

    def test_master_list_retains_unprocessed_sources_and_rejects_unsafe_urls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, recipe, text = batch_fixtures.BatchTests().fixture(root)
            jobs = [job, dict(job, url="https://www.mindreleased.com/s/second.pdf")]
            output = root / "build/review"
            prepare_batch(root, output, [recipe], jobs, 1, "test", extractor=Mock(return_value=text))
            rows = json.loads((output / "inventory.json").read_text())
            self.assertEqual(len(rows), 2)
            self.assertEqual(sum(r["review_state"] == "WAITING_THIS_PASS" for r in rows), 1)
            self.assertIn("second.pdf", (output / "review-list.txt").read_text())
            with self.assertRaises(ValueError):
                prepare_batch(root, output, [], [{"url": "javascript:alert(1)", "state": "MISSING"}], 1, "test")


if __name__ == "__main__":
    unittest.main()
