from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
from candana_resources import snp_partition, numeric_movement, resource_outputs, SNP_SHA, MANUAL_SHA  # noqa: E402


class ResourceTests(unittest.TestCase):
    def source(self):
        pages = ["\n"] * 391
        for book, (word, cover, count) in enumerate(zip(
            ("One", "Two", "Three", "Four", "Five"), (17, 75, 137, 263, 323), (12, 14, 12, 16, 19)
        ), 1):
            pages[cover - 1] = "\nBook " + word + "\n—\nCover\n"
            for number in range(1, count + 1):
                pages[cover + number] = f"\nSnp. {book}.{number}\n\nTitle {book}.{number}\n\nEvery word stays.\n"
        pages[385] = "\nList of Suttas\nAn index\n"
        pages[390] = "End matter and final character."
        return "\f".join(pages) + "\f"

    def test_73_sutta_intervals_and_surrounding_matter_preserve_all_characters(self):
        text = self.source()
        units = snp_partition(text)
        self.assertEqual(sum(u["kind"] == "SUTTA_SOURCE_INTERVAL" for u in units), 73)
        self.assertEqual(sum(u["kind"] == "BOOK_DIVIDER" for u in units), 5)
        self.assertEqual("".join(u["body"] for u in units), text)
        self.assertEqual(units[-1]["kind"], "BACK_MATTER")
        self.assertTrue(all(not u["publishable"] for u in units))
        self.assertEqual(next(u for u in units if u["id"] == "snp1.1")["first_pdf_page"], 19)

    def test_changed_numbering_missing_cover_or_end_boundary_fail_closed(self):
        text = self.source()
        for wrong in (text.replace("Snp. 1.2", "Snp. 1.1"), text.replace("Book Two", "Book Changed"),
                      text.replace("List of Suttas", "Changed end"), text + "extra\f"):
            with self.assertRaises(ValueError):
                snp_partition(wrong)

    def test_numeric_marker_movement_is_not_approval_and_other_changes_are_not_hidden(self):
        result = numeric_movement("a1 word.\nNote text.", "a word.\n1Note text.")
        self.assertEqual(result["classification"], "NUMERIC_TOKEN_RELOCATION")
        self.assertFalse(result["publication_approval"])
        for other in ("a word.\n2Note text.", "a changed word.\n1Note text.", "a word.\nNote text."):
            self.assertEqual(numeric_movement("a1 word.\nNote text.", other)["classification"], "OTHER_CHARACTER_DIFFERENCE")

    def test_only_pinned_sources_get_resource_drafts_and_raw_text_is_unchanged(self):
        self.assertEqual(resource_outputs("0" * 64, self.source(), None, None), ({}, {}))
        text = self.source()
        outputs, report = resource_outputs(SNP_SHA, text, None, None)
        self.assertEqual(report["sutta_source_intervals"], 73)
        self.assertEqual(b"".join(outputs["source-units/" + u["id"] + ".txt"] for u in report["units"]), text.encode())
        self.assertFalse(report["publishable"])
        self.assertIn(b"source.pdf#page=19", outputs["source-units.html"])

    def test_manual_lists_every_supplied_page_and_never_repairs_numbers(self):
        raw = "a1 word\fnext2 word\f"
        mu = "a word1\fnext word2\f"
        outputs, report = resource_outputs(MANUAL_SHA, mu, raw, {"mismatched_pages": [1, 2]})
        self.assertEqual([r["pdf_page"] for r in report["pages"]], [1, 2])
        self.assertEqual(report["counts"], {"NUMERIC_TOKEN_RELOCATION": 2})
        self.assertIn(b'comparison.html#pdf-page-2', outputs["source-units.html"])
        self.assertFalse(report["publishable"])


if __name__ == "__main__":
    unittest.main()
