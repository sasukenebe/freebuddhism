# SPDX-License-Identifier: 0BSD
"""Edition notes keep their scope without describing every book as a sutta."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/buddhist_canon_pipeline"))
from render_cc0_reader import ReaderParser, render_html, render_pdf, verify_pdf_body


class ReaderNotesHeadingTests(unittest.TestCase):
    def config(self):
        return {"canonical_id": "Ps 1.0", "title": "Opening list", "translator": "Author",
                "source_url": "https://example.org/book.pdf#page=88",
                "source_repository": "", "source_revision": "",
                "license": "CC-BY-NC-4.0", "license_url": "https://creativecommons.org/licenses/by-nc/4.0/",
                "license_notice": "Noncommercial use with attribution.", "metadata_notes": [],
                "collection_label": "Book", "collection_href": "index.html",
                "local_text_href": "text.txt", "html_download_href": "reader.html",
                "pdf_download_href": "reader.pdf",
                "translations": [{"label": "Author", "current": True}],
                "publisher_references": "Original note 1: the complete note remains unchanged.\n"}

    def test_default_and_book_specific_heading_preserve_body_and_note(self):
        for heading in (None, "Original notes & references <separate>"):
            with self.subTest(heading=heading):
                config = self.config()
                if heading is not None:
                    config["publisher_references_heading"] = heading
                page = render_html(config, "Complete source body.\n")
                parser = ReaderParser()
                parser.feed(page)
                self.assertEqual("".join(parser.source_parts), "Complete source body.\n")
                self.assertIn(config["publisher_references"], page)
                self.assertIn("Publisher references (not part of the sutta)" if heading is None
                              else "Original notes &amp; references &lt;separate&gt;", page)

    def test_custom_pdf_heading_retains_note_and_rejects_missing_or_mislabelled_note(self):
        config = self.config()
        heading = "Original notes and references (separate from the main text)"
        config["publisher_references_heading"] = heading
        body = "First original line.\n\nLast original line.\n"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "reader.pdf"
            render_pdf(config, body, target)
            verify_pdf_body(target, body, config["publisher_references"], heading)
            with self.assertRaises(ValueError):
                verify_pdf_body(target, body, "Invented replacement note.", heading)
            with self.assertRaises(ValueError):
                verify_pdf_body(target, body, config["publisher_references"], "Wrong heading")


if __name__ == "__main__":
    unittest.main()
