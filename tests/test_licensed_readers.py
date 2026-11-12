# SPDX-License-Identifier: 0BSD
"""Published body/download/rights corruption must fail independently of rendering."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/buddhist_canon_pipeline"))
from check_licensed_readers import check_reader
from build_eligible_readers import validate_page
from render_cc0_reader import render_pdf, verify_pdf_body


class LicensedReaderTests(unittest.TestCase):
    def test_pdf_preserves_spaced_asterisk_separator_and_all_words(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "separator.pdf"
            config = {"canonical_id": "AN 10.71", "title": "Example", "translator": "Author",
                      "source_url": "https://example.org/original", "license": "CC-BY-NC-4.0",
                      "license_url": "https://creativecommons.org/licenses/by-nc/4.0/", "metadata_notes": []}
            body = "First paragraph.\n\n* * *\n\n[ I ]\n\nPali root marker: √bhā.\n\nWord bound\u00adary.\n\nLast paragraph.\n"
            render_pdf(config, body, target)
            verify_pdf_body(target, body)
            with self.assertRaises(ValueError):
                verify_pdf_body(target, body.replace("Last", "Invented"))

    def test_new_edition_links_are_validated_after_text_nodes_are_generated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            page = root / "reader.html"
            body = "Complete original text.\n"
            html = '<pre class="source-text">' + body + '</pre>'
            page.write_text(html, encoding="utf-8")
            record = {"html_path": page, "body": body, "licensed_record": {"verified": True},
                      "entry_page": root / "not-generated-yet.html"}
            validate_page(record, html, check_pdf=False)
            record.pop("licensed_record")
            with self.assertRaises(ValueError):
                validate_page(record, html, check_pdf=False)

    def test_reader_download_and_notice_faults_are_rejected(self):
        for fault in (None, "body", "download", "notice", "source", "pdf"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                site = root / "site"
                row = {"canonical_id": "MN 1", "collection": "majjhima-nikaya", "version": "example",
                       "local_path": "translations/example.txt", "license": "CC-BY-NC-4.0",
                       "license_url": "https://creativecommons.org/licenses/by-nc/4.0/",
                       "source_url": "https://example.org/original", "license_notice": "Preserve this notice.",
                       "copyright": "Copyright Author", "translator": "Author", "completeness_status": "UNKNOWN"}
                source = root / row["local_path"]
                source.parent.mkdir(parents=True)
                source.write_text("Header\n\nFirst line\nSecond line.\n", encoding="utf-8")
                download = site / row["local_path"]
                download.parent.mkdir(parents=True)
                download.write_bytes(b"Wrong" if fault == "download" else source.read_bytes())
                page = site / "theravada/tipitaka/sutta/majjhima-nikaya/mn01/mn01-example.html"
                page.parent.mkdir(parents=True)
                body = "Changed" if fault == "body" else "First line\nSecond line.\n"
                rights = "Wrong notice" if fault == "notice" else row["license_notice"]
                url = "https://wrong.example" if fault == "source" else row["source_url"]
                page.write_text(f'<pre class="source-text">{body}</pre><p>{row["license"]} {rights} {row["copyright"]}</p><a href="{url}">Source</a><a href="{row["license_url"]}">License</a>', encoding="utf-8")
                page.with_name("mn01-example-reader.pdf").write_bytes(b"Wrong" if fault == "pdf" else b"%PDF-test")
                if fault is None:
                    self.assertEqual(check_reader(row, root, site)["text"], "MN 1")
                else:
                    with self.assertRaises(ValueError):
                        check_reader(row, root, site)


if __name__ == "__main__":
    unittest.main()
