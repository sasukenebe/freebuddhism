# SPDX-License-Identifier: 0BSD
"""Regression coverage for reviewed lineation using only synthetic source text."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
import candana_website as website


HEADER = (
    "AN 4.1\nSynthetic lineation fixture\n"
    "Translated by Bhikkhu Candana\nCopyright synthetic\n\n"
)
LEGACY_CHANGES = (
    "Presentation only: original heading retained in edition details; physical line wraps reflowed; "
    "reviewed page breaks retained as paragraph breaks. "
    "No words, punctuation, notes or closings removed or repaired."
)


def recipe_for(source, **layout):
    recipe = {
        "header_characters": len(HEADER),
        "header_sha256": sha256(HEADER.encode()).hexdigest(),
        "raw_body_sha256": sha256(source.encode()).hexdigest(),
        "page_break_paragraphs": [],
        "page_break_joins": [],
    }
    recipe.update(layout)
    return recipe


class CandanaLineationTests(unittest.TestCase):
    def reviewed_record(self, root, styled):
        from test_candana_website import CandanaWebsiteTests
        fixture = CandanaWebsiteTests()
        pdf, raw, row, manifest = fixture.fixture(root)
        if styled:
            header, body = website.partition(raw, row)
            text = 'First synthetic source paragraph.'
            start = body.index(text)
            row['partition']['italic_spans'] = [{
                'start': start, 'end': start + len(text),
                'sha256': sha256(text.encode()).hexdigest(),
            }]
            row['text_sha256'] = website.sha(website.attributed_text(row, header, body).encode())
            (root / website.MANIFEST_PATH).write_text(json.dumps(manifest))
        with fixture.extractor(raw):
            website.stage(pdf, root)
            return website.collect_records(root / 'build/readers', root)[0]

    def test_reviewed_record_rejects_missing_or_changed_source_italics(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            record = self.reviewed_record(root, styled=True)
            self.assertTrue(website.verify_record(record, root))
            absent = deepcopy(record); absent.pop('body_italics')
            self.assertFalse(website.verify_record(absent, root))
            changed = deepcopy(record['body_italics'])
            changed[0]['sha256'] = '0' * 64
            for spans in ([], None, changed):
                with self.subTest(spans=spans):
                    self.assertFalse(website.verify_record(dict(record, body_italics=spans), root))

    def test_reviewed_record_requires_explicit_text_first_pdf(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            record = self.reviewed_record(root, styled=False)
            self.assertTrue(website.verify_record(record, root))
            absent = deepcopy(record); absent.pop('pdf_text_first')
            self.assertFalse(website.verify_record(absent, root))
            for value in (False, None, 1, 'true'):
                with self.subTest(value=value):
                    self.assertFalse(website.verify_record(dict(record, pdf_text_first=value), root))

    def test_unstyled_record_rejects_unreviewed_added_italics(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            record = self.reviewed_record(root, styled=False)
            self.assertTrue(website.verify_record(dict(record, body_italics=[]), root))
            text = record['body'][:5]
            spans = [{'start': 0, 'end': 5, 'sha256': sha256(text.encode()).hexdigest()}]
            self.assertFalse(website.verify_record(dict(record, body_italics=spans), root))

    def assert_reflow(self, source, expected, recipe, pdf_pages=1):
        body = website.reflow_body(source, recipe, pdf_pages)
        self.assertEqual(body, expected)
        self.assertEqual(body.split(), source.split())
        return body

    def test_separate_selected_blocks_keep_lines_and_unselected_prose_reflows(self):
        source = (
            " \t\n\n  Opening synthetic\n prose wraps here.\n\n\n"
            "\tFirst   synthetic line; \t\n    Second\tsynthetic line.\t\n\n"
            "Middle synthetic prose\n continues here.\n\n \t\n"
            "  Third synthetic line!\n\tFourth synthetic line?\n\n"
            "Trailing synthetic\n prose stays ordered.\n\n \t\f"
        )
        expected = (
            "Opening synthetic prose wraps here.\n\n"
            "First synthetic line;\nSecond synthetic line.\n\n"
            "Middle synthetic prose continues here.\n\n"
            "Third synthetic line!\nFourth synthetic line?\n\n"
            "Trailing synthetic prose stays ordered.\n"
        )
        self.assert_reflow(
            source, expected, recipe_for(source, lineated_paragraphs=[2, 4])
        )

    def test_first_and_last_nonempty_paragraphs_use_one_based_indexes(self):
        source = (
            "\n \t\n  Repeated synthetic line.\n Repeated synthetic line.\n\n"
            "Middle synthetic\n prose.\n\n\n"
            "  Last synthetic line: café.\n Last synthetic line: ‘end’.\n\n\f"
        )
        expected = (
            "Repeated synthetic line.\nRepeated synthetic line.\n\n"
            "Middle synthetic prose.\n\n"
            "Last synthetic line: café.\nLast synthetic line: ‘end’.\n"
        )
        self.assert_reflow(
            source, expected, recipe_for(source, lineated_paragraphs=[1, 3])
        )

    def test_indexes_follow_reviewed_page_joins_and_paragraph_breaks(self):
        source = (
            "  Opening synthetic\n prose.\n\n"
            "  First synthetic line.\n Second synthetic line.\n\n \t\f"
            "\n\n Third synthetic line.\n Fourth synthetic line.\n\n \f"
            "\n\n Closing synthetic\n prose.\n\f"
        )
        expected = (
            "Opening synthetic prose.\n\n"
            "First synthetic line.\nSecond synthetic line.\n"
            "Third synthetic line.\nFourth synthetic line.\n\n"
            "Closing synthetic prose.\n"
        )
        self.assert_reflow(
            source, expected,
            recipe_for(
                source, page_break_joins=[1], page_break_paragraphs=[2],
                lineated_paragraphs=[2],
            ),
            pdf_pages=3,
        )

    def test_indexes_follow_internal_paragraph_starts(self):
        source = (
            "  Opening synthetic\n prose.\n"
            "  First synthetic line.\n Second synthetic line.\n\n"
            "  Closing synthetic\n prose.\n\f"
        )
        expected = (
            "Opening synthetic prose.\n\n"
            "First synthetic line.\nSecond synthetic line.\n\n"
            "Closing synthetic prose.\n"
        )
        self.assert_reflow(
            source, expected,
            recipe_for(
                source,
                internal_paragraph_starts=[source.index("  First synthetic line.")],
                lineated_paragraphs=[2],
            ),
        )

    def test_internal_starts_and_page_joins_share_final_paragraph_indexes(self):
        source = (
            "  Opening synthetic\n prose.\n"
            "  First synthetic line.\n Second synthetic line.\n \f"
            "\n Third synthetic line.\n Fourth synthetic line.\n"
            "  Closing synthetic\n prose.\n\f"
        )
        expected = (
            "Opening synthetic prose.\n\n"
            "First synthetic line.\nSecond synthetic line.\n"
            "Third synthetic line.\nFourth synthetic line.\n\n"
            "Closing synthetic prose.\n"
        )
        self.assert_reflow(
            source, expected,
            recipe_for(
                source, page_break_joins=[1],
                internal_paragraph_starts=[
                    source.index("  First synthetic line."),
                    source.index("  Closing synthetic"),
                ],
                lineated_paragraphs=[2],
            ),
            pdf_pages=2,
        )

    def test_lineated_paragraphs_reject_invalid_containers_and_indexes(self):
        source = (
            "First synthetic\n paragraph.\n\nSecond synthetic\n paragraph.\n\n"
            "Third synthetic\n paragraph.\n\f"
        )
        invalid = (
            ("null", None), ("boolean field", True), ("integer field", 1),
            ("float field", 1.0), ("string field", "1"),
            ("tuple", (1,)), ("set", {1}), ("mapping", {"1": True}),
            ("empty", []), ("true index", [True]), ("false index", [False]),
            ("string index", ["1"]), ("float index", [1.0]),
            ("null index", [None]), ("nested list", [[1]]),
            ("mapping index", [{}]), ("zero", [0]), ("negative", [-1]),
            ("duplicates", [1, 1]), ("unsorted", [2, 1]),
            ("past final paragraph", [4]), ("mixed out of range", [1, 4]),
            ("mixed boolean", [1, True]),
        )
        for label, indexes in invalid:
            with self.subTest(case=label), self.assertRaises(ValueError):
                website.reflow_body(
                    source, recipe_for(source, lineated_paragraphs=indexes), 1
                )

    def test_out_of_range_is_checked_after_page_joins(self):
        source = "First synthetic line.\n\fSecond synthetic line.\n\f"
        self.assert_reflow(
            source, "First synthetic line.\nSecond synthetic line.\n",
            recipe_for(source, page_break_joins=[1], lineated_paragraphs=[1]),
            pdf_pages=2,
        )
        with self.assertRaises(ValueError):
            website.reflow_body(
                source,
                recipe_for(source, page_break_joins=[1], lineated_paragraphs=[2]),
                2,
            )

    def test_empty_layout_has_no_lineated_paragraph_index(self):
        for source in ("", " \t\n\n\f"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                website.reflow_body(
                    source, recipe_for(source, lineated_paragraphs=[1]), 1
                )

    def test_lineation_requires_explicit_page_break_joins_even_on_one_page(self):
        sources = (
            ("First synthetic\n line.\n\f", 1, []),
            ("First synthetic\n line.\n\fSecond synthetic\n line.\n\f", 2, [1]),
        )
        for source, pages, paragraph_breaks in sources:
            with self.subTest(pages=pages):
                recipe = recipe_for(source, page_break_paragraphs=paragraph_breaks)
                del recipe["page_break_joins"]
                legacy = website.reflow_body(source, recipe, pages)
                self.assertEqual(legacy.split(), source.split())
                recipe["lineated_paragraphs"] = [1]
                with self.assertRaises(ValueError):
                    website.reflow_body(source, recipe, pages)

    def test_recipes_without_lineation_keep_prose_bytes_and_exact_legacy_notice(self):
        source = "  First synthetic\n line.\n\nSecond synthetic\n line.\n\f"
        expected = "First synthetic line.\n\nSecond synthetic line.\n"
        for explicit in (False, True):
            with self.subTest(explicit=explicit):
                recipe = recipe_for(source)
                if not explicit:
                    del recipe["page_break_joins"]
                body = self.assert_reflow(source, expected, recipe)
                self.assertEqual(body.encode(), expected.encode())
                if not explicit:
                    self.assertEqual(website.changes_for({"partition": recipe}), LEGACY_CHANGES)
        self.assertEqual(website.CHANGES, LEGACY_CHANGES)

    def test_changes_notice_explicitly_describes_preserved_line_breaks(self):
        source = "First synthetic line.\nSecond synthetic line.\n\f"
        prose = {"partition": recipe_for(source)}
        lineated = {"partition": recipe_for(source, lineated_paragraphs=[1])}
        notice = website.changes_for(lineated)
        self.assertNotEqual(notice, website.changes_for(prose))
        self.assertNotEqual(notice, LEGACY_CHANGES)
        self.assertRegex(
            notice.casefold(),
            r"(?:preserv|retain)\w*[^.;]*line breaks|line breaks[^.;]*(?:preserv|retain)\w*",
        )

    def test_lineation_does_not_allow_original_hyphen_wraps(self):
        cases = (
            ("Synthetic-\n continuation.\n\nOther synthetic\n lines.\n\f", 1, [], [1]),
            ("Synthetic-\n continuation.\n\nOther synthetic\n lines.\n\f", 1, [], [2]),
            ("Synthetic-\n\n \f\n continuation.\n\f", 2, [1], [1]),
        )
        for source, pages, joins, selected in cases:
            with self.subTest(source=source, selected=selected), self.assertRaises(ValueError):
                website.reflow_body(
                    source,
                    recipe_for(source, page_break_joins=joins, lineated_paragraphs=selected),
                    pages,
                )

    def test_partition_still_rejects_changed_source_bytes_and_pinned_hashes(self):
        source = "  First synthetic line.\n Second synthetic line.\n\f"
        expected = "First synthetic line.\nSecond synthetic line.\n"
        raw = HEADER + source
        row = {
            "canonical_id": "AN 4.1",
            "copyright": "Copyright synthetic",
            "pdf_pages": 1,
            "raw_text_sha256": sha256(raw.encode()).hexdigest(),
            "body_sha256": sha256(expected.encode()).hexdigest(),
            "partition": recipe_for(source, lineated_paragraphs=[1]),
        }
        self.assertEqual(website.partition(raw, row), (HEADER, expected))
        for label, changed_raw in (
            ("header bytes", raw.replace("Synthetic lineation", "Changed lineation", 1)),
            ("body token", raw.replace("First synthetic", "Other synthetic", 1)),
            ("body whitespace", HEADER + source.replace("  First", "   First", 1)),
        ):
            with self.subTest(case=label), self.assertRaises(ValueError):
                website.partition(changed_raw, row)
        for field in ("header_sha256", "raw_body_sha256", "body_sha256"):
            changed = deepcopy(row)
            target = changed if field == "body_sha256" else changed["partition"]
            target[field] = "0" * 64
            with self.subTest(hash=field), self.assertRaises(ValueError):
                website.partition(raw, changed)
        changed = deepcopy(row)
        del changed["partition"]["lineated_paragraphs"]
        with self.assertRaises(ValueError):
            website.partition(raw, changed)

        for label, changed_source in (
            ("replaced token", source.replace("First synthetic", "Other synthetic", 1)),
            ("removed token", source.replace("First synthetic", "First", 1)),
            ("reordered lines", "  Second synthetic line.\n First synthetic line.\n\f"),
        ):
            changed_raw = HEADER + changed_source
            changed = deepcopy(row)
            changed["raw_text_sha256"] = sha256(changed_raw.encode()).hexdigest()
            changed["partition"]["raw_body_sha256"] = sha256(changed_source.encode()).hexdigest()
            with self.subTest(repinned_source=label), self.assertRaises(ValueError):
                website.partition(changed_raw, changed)


if __name__ == "__main__":
    unittest.main()
