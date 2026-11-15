# SPDX-License-Identifier: 0BSD
"""Reviewed source-line paragraph breaks never permit textual repairs."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/buddhist_canon_pipeline"))
import candana_website as website


class CandanaInternalParagraphTests(unittest.TestCase):
    def fixture(self):
        header = "SN 55.21\nTranslated by Bhikkhu Candana\nCopyright synthetic\n"
        source = "First line\ncontinued.\n  Second paragraph.\nThird paragraph.\n\f"
        recipe = {"header_characters": len(header), "header_sha256": website.sha(header.encode()),
                  "raw_body_sha256": website.sha(source.encode()), "page_break_paragraphs": [],
                  "page_break_joins": [], "internal_paragraph_starts": [
                      source.index("  Second"), source.index("Third")]}
        body = "First line continued.\n\nSecond paragraph.\n\nThird paragraph.\n"
        row = {"partition": recipe, "pdf_pages": 1, "canonical_id": "SN 55.21",
               "copyright": "Copyright synthetic", "body_sha256": website.sha(body.encode())}
        return header, source, row, body

    def test_exact_source_words_and_reviewed_internal_paragraphs_survive(self):
        header, source, row, expected = self.fixture()
        self.assertEqual(website.partition(header + source, row), (header, expected))
        self.assertEqual(source.split(), expected.split())

    def test_existing_recipe_without_new_field_is_unchanged(self):
        _header, source, row, _body = self.fixture()
        del row["partition"]["internal_paragraph_starts"]
        self.assertEqual(website.reflow_body(source, row["partition"], 1),
                         "First line continued. Second paragraph. Third paragraph.\n")

    def test_invalid_metadata_is_rejected(self):
        _header, source, row, _body = self.fixture()
        for starts in (None, "21", [True], [0], [-1], [21, 21], [40, 21], [1.0]):
            with self.subTest(starts=starts), self.assertRaises(ValueError):
                recipe = dict(row["partition"], internal_paragraph_starts=starts)
                website.reflow_body(source, recipe, 1)
        recipe = deepcopy(row["partition"])
        del recipe["page_break_joins"]
        with self.assertRaises(ValueError):
            website.reflow_body(source, recipe, 1)

    def test_character_offsets_cannot_split_words_or_indentation(self):
        _header, source, row, _body = self.fixture()
        for offset in (1, source.index("Second"), len(source), len(source) + 1):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                website.reflow_body(source, dict(row["partition"], internal_paragraph_starts=[offset]), 1)

    def test_blank_lines_and_page_breaks_cannot_be_reclassified(self):
        _header, _source, row, _body = self.fixture()
        for source, index, count in (("First.\n\nSecond.\f", 7, 1),
                                     ("First.\n\nSecond.\f", 8, 1),
                                     ("First.\f\nSecond.\f", 8, 2),
                                     ("First.\n\fSecond.\f", 7, 2)):
            recipe = dict(row["partition"], page_break_paragraphs=list(range(1, count)),
                          internal_paragraph_starts=[index])
            with self.subTest(source=source, index=index), self.assertRaises(ValueError):
                website.reflow_body(source, recipe, count)

    def test_source_and_output_hashes_still_pin_whitespace_and_words(self):
        header, source, row, _body = self.fixture()
        with self.assertRaisesRegex(ValueError, "exact reader boundary changed"):
            website.partition(header + source.replace("Second", "Different"), row)
        changed = deepcopy(row)
        changed["partition"]["internal_paragraph_starts"].pop()
        with self.assertRaisesRegex(ValueError, "differs from reviewed output"):
            website.partition(header + source, changed)


if __name__ == "__main__":
    unittest.main()
