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
    human_queue, human_queue_views, apply_human_decisions, reading_catalog,
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
    def review_row(self):
        return {"source_url": "https://www.mindreleased.com/s/example.pdf", "source_sha256": "a" * 64,
                "kind": "PDF_DRAFT", "title": "Synthetic <title>", "rights": "EXPLICIT_GRANT_DETECTED",
                "page_reviews": [{"page": 2, "flags": ["RECIPE_RECOGNIZED_PAGINATION_POSITION"]},
                                 {"page": 3, "flags": ["RAW_WORD_BOUNDARY_REVIEW"]}],
                "review_path": "sources/example/index.html", "comparison_path": "sources/example/comparison.html",
                "local_pdf_path": "sources/example/source.pdf", "resource_review": {}}

    def test_roles_separate_permissions_proofreading_and_maintainer_work(self):
        row = self.review_row()
        row["rights"] = "NEEDS_PERMISSION_REVIEW"
        queue = human_queue([row])
        rights = next(t for t in queue["tasks"] if t["role"] == "RIGHTS_REVIEWER")
        proofreading = next(t for t in queue["tasks"] if t["role"] == "PROOFREADER")
        self.assertEqual(rights["status"], "NEEDS_HUMAN")
        self.assertEqual(proofreading["status"], "WAIT_PERMISSION")
        self.assertEqual(proofreading["pages"], [3])
        self.assertFalse(queue["automatic_approval"])
        self.assertTrue(all(not t["automatic_approval"] for t in queue["tasks"]))

    def test_reading_catalog_has_one_pair_per_pdf_not_one_entry_per_check(self):
        row = self.review_row()
        missing = dict(row, kind="MISSING_SOURCE", title="Missing source", review_path=None)
        discovery = dict(row, kind="DISCOVERY_PAGE", title="Discovery page")
        output = reading_catalog([row, missing, discovery])
        visible = output.split('<details>', 1)[0]
        self.assertEqual(visible.count('>Original PDF</a>'), 1)
        self.assertEqual(visible.count('>Converted text</a>'), 1)
        self.assertIn('Synthetic &lt;title&gt;', visible)
        self.assertNotIn('Missing source', visible)
        self.assertNotIn('Discovery page', visible)
        self.assertNotIn('PROOFREADER', visible)
        self.assertNotIn('EXPLICIT_GRANT_DETECTED', visible)
        self.assertIn('technical-checks.html', output)

    def test_sutta_nipata_is_first_and_links_to_individual_text_pairs(self):
        row = self.review_row()
        snp = dict(row, title="Sutta-Nipta-raw-filename.pdf", resource_path="sources/snp/source-units.html",
                   resource_review={"kind": "SUTTA_NIPATA_SOURCE_PARTITION"})
        output = reading_catalog([row, snp])
        self.assertLess(output.index('Sutta Nipāta'), output.index('Synthetic &lt;title&gt;'))
        self.assertIn('href="sources/snp/source-units.html"', output)

    def test_check_ids_survive_reordering_and_change_with_source_bytes(self):
        row = self.review_row()
        original = human_queue([row])["tasks"][0]["id"]
        self.assertEqual(human_queue([dict(row)])["tasks"][0]["id"], original)
        row["source_sha256"] = "b" * 64
        self.assertNotEqual(human_queue([row])["tasks"][0]["id"], original)

    def test_human_decisions_require_evidence_and_partial_review_cannot_confirm_all(self):
        queue = human_queue([self.review_row()])
        task = queue["tasks"][0]
        decision = {"check_id": task["id"], "source_sha256": task["source_sha256"],
                    "reviewer": "Synthetic reviewer", "date": "2026-11-08", "outcome": "CONFIRMED",
                    "scope": "FULL_CHECK", "evidence": "Synthetic complete check, not an actual human result."}
        for wrong in (dict(decision, evidence=""), dict(decision, source_sha256="wrong"), dict(decision, scope="PARTIAL")):
            with self.assertRaises(ValueError):
                apply_human_decisions(human_queue([self.review_row()]), {"schema_version": 1, "decisions": [wrong]})
        result = apply_human_decisions(queue, {"schema_version": 1, "decisions": [decision]})
        self.assertEqual(result["tasks"][0]["status"], "HUMAN_REPORTED_CONFIRMED")
        self.assertFalse(result["automatic_approval"])
        self.assertFalse(result["tasks"][0]["automatic_approval"])
        self.assertEqual(result["human_decision_records"], 1)

    def test_stale_human_records_are_retained_and_html_is_escaped(self):
        queue = human_queue([self.review_row()])
        decision = {"check_id": "older-check", "source_sha256": "old-sha", "reviewer": "Synthetic reviewer",
                    "date": "2026-11-08", "outcome": "PARTIAL", "scope": "PARTIAL", "evidence": "Older source."}
        queue = apply_human_decisions(queue, {"schema_version": 1, "decisions": [decision]})
        self.assertEqual(queue["unmatched_decisions_preserved"], [decision])
        rendered, plain = human_queue_views(queue)
        self.assertIn("Synthetic &lt;title&gt;", rendered)
        self.assertNotIn("Synthetic <title>", rendered)
        self.assertIn("PROOFREADER", plain)
        self.assertIn("source.pdf#page=3", rendered)

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

    def test_repeated_batch_preserves_separate_human_decisions_without_reconversion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, recipe, text = batch_fixtures.BatchTests().fixture(root)
            output = root / "build/review"
            extractor = Mock(return_value=text)
            args = (root, output, [recipe], [job], 1, "test")
            prepare_batch(*args, extractor=extractor)
            simple = (output / "index.html").read_text()
            self.assertEqual(simple, (output / "human-review.html").read_text())
            self.assertNotIn('PROOFREADER', simple)
            self.assertIn('PROOFREADER', (output / "technical-checks.html").read_text())
            self.assertTrue((output / "source-inventory.html").is_file())
            task = json.loads((output / "human-review.json").read_text())["tasks"][0]
            ledger = {"schema_version": 1, "decisions": [{"check_id": task["id"],
                "source_sha256": task["source_sha256"], "reviewer": "Synthetic test reviewer",
                "date": "2026-11-08", "outcome": "PARTIAL", "scope": "PARTIAL",
                "evidence": "Synthetic page sample only; no real reviewer approval."}]}
            decision_file = output / "human-decisions.json"
            decision_file.write_text(json.dumps(ledger))
            before = decision_file.read_bytes()
            result = prepare_batch(*args, extractor=extractor)
            self.assertEqual(extractor.call_count, 2)
            self.assertEqual(result["processed_this_run"], 0)
            self.assertEqual(decision_file.read_bytes(), before)
            queue = json.loads((output / "human-review.json").read_text())
            self.assertEqual(queue["tasks"][0]["status"], "PARTIAL_HUMAN_REVIEW")
            self.assertFalse(queue["automatic_approval"])


if __name__ == "__main__":
    unittest.main()
