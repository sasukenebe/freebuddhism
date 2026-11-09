from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
from candana_resources import (  # noqa: E402
    snp_partition, manual_partition, MANUAL_STARTS, numeric_movement, resource_outputs, reading_html, pair_links, SNP_SHA, MANUAL_SHA,
)


class ReadingText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "div" and ("class", "converted-text") in attrs:
            self.active = True

    def handle_endtag(self, tag):
        if tag == "div":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


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
        self.assertIn(b"PDF pages 19", outputs["source-units.html"])
        self.assertEqual(outputs["source-units.html"].count(b'href="source.pdf"'), 1)
        self.assertNotIn(b'source.pdf#page=', outputs["source-units.html"])
        self.assertIn(b'source-units/snp1.1.html', outputs["source-units.html"])
        self.assertIn(b'../source.pdf#page=19', outputs["source-units/snp1.1.html"])
        self.assertNotIn(b'<pre>', outputs["source-units/snp1.1.html"])
        self.assertIn(b'<details>', outputs["source-units.html"])

    def test_reading_view_keeps_quotes_accents_numbers_and_stanzas_without_fixed_width(self):
        text = '“The Snake”\n\n1. “Keep every\nword and ā accent.”\n\n2. Preserve <script> & notes.\f19\n'
        output = reading_html("A <title>", text).decode("utf-8")
        parsed = ReadingText()
        parsed.feed(output)
        self.assertEqual("".join("".join(parsed.parts).split()), "".join(text.split()))
        self.assertIn('“The Snake”', output)
        self.assertIn('1. “Keep every word and ā accent.”', output)
        self.assertNotIn("â€œ", output)
        self.assertNotIn("<script>", output)
        self.assertNotIn("<pre>", output)
        self.assertNotIn("max-width", output)
        self.assertEqual(output.count('<p>'), 5)
        self.assertIn('<meta charset="utf-8">', output)

    def test_two_link_labels_are_literal_and_escape_source_titles(self):
        output = pair_links('A <title>', 'source.pdf#page=2', 'section.html', 'source-2')
        self.assertIn('A &lt;title&gt;', output)
        self.assertIn('id="source-2"', output)
        self.assertEqual(output.count('<a '), 2)
        self.assertIn('>Original PDF</a>', output)
        self.assertIn('>Converted text</a>', output)

    def test_manual_lists_every_supplied_page_and_never_repairs_numbers(self):
        raw = "a1 word\fnext2 word\f"
        mu = "a word1\fnext word2\f"
        outputs, report = resource_outputs(MANUAL_SHA, mu, raw, {"mismatched_pages": [1, 2]})
        self.assertEqual([r["pdf_page"] for r in report["pages"]], [1, 2])
        self.assertEqual(report["counts"], {"NUMERIC_TOKEN_RELOCATION": 2})
        self.assertIn(b'comparison.html#pdf-page-2', outputs["source-units.html"])
        self.assertFalse(report["publishable"])

    def test_manual_chapters_cover_all_pages_without_repairing_raw_text(self):
        pages = [f'Page {n}\nKeep every character.\n' for n in range(1, 215)]
        for key, title, first in MANUAL_STARTS:
            pages[first - 1] = title + '\n\nT\n\nhis raw text stays unchanged.\n'
        raw = '\f'.join(pages) + '\f\n'
        units = manual_partition(raw)
        self.assertEqual(len(units), 14)
        self.assertEqual(''.join(unit['body'] for unit in units), raw)
        self.assertEqual(units[-1]['last_pdf_page'], 214)
        self.assertTrue(all(not unit['publishable'] for unit in units))
        self.assertIn('T\n\nhis', units[1]['body'])
        with self.assertRaises(ValueError):
            manual_partition(raw.replace('Preface', 'Missing heading'))
        with self.assertRaises(ValueError):
            manual_partition(raw + 'extra page\f')


if __name__ == "__main__":
    unittest.main()
