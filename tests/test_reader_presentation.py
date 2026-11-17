# SPDX-License-Identifier: 0BSD
"""Source-bound emphasis, reading-first PDFs and distinct edition labels."""
from copy import deepcopy
from contextlib import redirect_stdout
from hashlib import sha256
from importlib.util import find_spec
from io import StringIO
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/buddhist_canon_pipeline"))
from render_cc0_reader import ReaderParser, checked_italic_spans, render_html, render_pdf, verify_pdf_body
from build_eligible_readers import licensed_version_label, pdf_render_hash
import build_eligible_readers as builder


class ReaderPresentationTests(unittest.TestCase):
    def config(self):
        return {
            "canonical_id": "AN 4.1", "title": "Synthetic reader", "translator": "Example translator",
            "source_url": "https://example.org/source.pdf", "source_repository": "", "source_revision": "",
            "license": "Example licence", "license_url": "https://example.org/terms",
            "copyright": "Copyright Example", "metadata_notes": ["Complete notice: retain every condition.",
                "Source revision: a synthetic test receipt, not source text."],
            "collection_label": "Example collection", "collection_href": "index.html",
            "local_text_href": "text.txt", "html_download_href": "reader.html", "pdf_download_href": "reader.pdf",
            "translations": [{"label": "Example translator", "current": True}],
        }

    def span(self, body, text):
        start = body.index(text)
        return {"start": start, "end": start + len(text), "sha256": sha256(text.encode()).hexdigest()}

    def test_html_emphasis_is_escaped_without_changing_body_or_adjacent_punctuation(self):
        body = 'Opening <synthetic> & text.\n\n“Keep these\nexact words.” End.\n'
        config = self.config()
        config["body_italics"] = [self.span(body, "Keep these\nexact words.")]
        page = render_html(config, body)
        self.assertIn('“<em>Keep these\nexact words.</em>” End.', page)
        self.assertIn('&lt;synthetic&gt; &amp;', page)
        parser = ReaderParser(); parser.feed(page)
        self.assertEqual(''.join(parser.source_parts), body)
        self.assertNotIn('<em>', render_html(self.config(), body))

    def test_emphasis_rejects_changed_text_hashes_offsets_overlap_and_unknown_fields(self):
        body = "First synthetic phrase.\nSecond synthetic phrase.\n"
        span = self.span(body, "First")
        bad = [None, {}, "First", [True], [dict(span, start=True)], [dict(span, end=False)],
               [dict(span, start=-1)], [dict(span, end=999)], [dict(span, end=0)],
               [dict(span, sha256="0" * 64)], [dict(span, style="invented")], [span, span]]
        for spans in bad:
            with self.subTest(spans=spans), self.assertRaises(ValueError):
                checked_italic_spans(body, spans)
        with self.assertRaises(ValueError):
            checked_italic_spans(body.replace("First", "Other"), [span])
        second = self.span(body, "Second")
        with self.assertRaises(ValueError):
            checked_italic_spans(body, [second, span])

    def test_pdf_cache_distinguishes_emphasis_and_text_first_without_changing_legacy_key(self):
        config = self.config()
        baseline = pdf_render_hash(config)
        self.assertEqual(baseline, pdf_render_hash(dict(config, pdf_text_first=False)))
        self.assertNotEqual(baseline, pdf_render_hash(dict(config, pdf_text_first=True)))
        styled = dict(config, body_italics=[self.span("Synthetic phrase.", "Synthetic")])
        self.assertNotEqual(baseline, pdf_render_hash(styled))
        changed = deepcopy(styled); changed['body_italics'][0]['end'] -= 1
        self.assertNotEqual(pdf_render_hash(styled), pdf_render_hash(changed))

    def test_same_translator_source_labels_are_distinct_and_other_translators_unchanged(self):
        ati = dict(translator="Thanissaro Bhikkhu", version="ati-thanissaro-bhikkhu",
                   source_url="https://www.accesstoinsight.org/tipitaka/example.html")
        dt = dict(translator="Ṭhānissaro Bhikkhu", version="thanissaro-dhammatalks",
                  source_url="https://www.dhammatalks.org/suttas/example.html")
        self.assertEqual(licensed_version_label(ati), "Thanissaro Bhikkhu — Access to Insight")
        self.assertEqual(licensed_version_label(dt), "Ṭhānissaro Bhikkhu — dhammatalks.org")
        self.assertEqual(ati['translator'], "Thanissaro Bhikkhu")
        self.assertEqual(licensed_version_label(dict(ati, version="other")), ati['translator'])
        self.assertEqual(licensed_version_label(dict(ati, source_url="https://other.example.org")), ati['translator'])

    @unittest.skipUnless(find_spec('reportlab'), "ReportLab required")
    @unittest.skipUnless(shutil.which('pdftotext') and shutil.which('mutool'), "Native PDF checks required")
    def test_pdf_keeps_real_italic_font_text_order_and_complete_provenance_after_body(self):
        body = "First synthetic line.\n\nSecond line must not change.\n"
        config = self.config()
        config.update(pdf_text_first=True, body_italics=[self.span(body, "must not")])
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / 'reader.pdf'
            render_pdf(config, body, pdf)
            verify_pdf_body(pdf, body)
            text = subprocess.check_output(['pdftotext', '-layout', str(pdf), '-'], text=True)
            self.assertLess(text.index('First synthetic line.'), text.index('Source and license'))
            self.assertGreater(text.index(config['source_url']), text.index('Second line must not change.'))
            for notice in config['metadata_notes']:
                self.assertIn(' '.join(notice.split()), ' '.join(text.split()))
            xml = subprocess.check_output(['mutool', 'draw', '-F', 'stext', '-o', '-', str(pdf)], stderr=subprocess.PIPE)
            root = ET.fromstring(xml)
            italic = ''.join(''.join(c.attrib.get('c', '') for c in font.findall('char'))
                             for font in root.iter('font') if 'italic' in font.attrib.get('name', '').lower())
            self.assertEqual(italic, 'must not')
            legacy = Path(directory) / 'legacy.pdf'
            render_pdf(self.config(), body, legacy)
            legacy_text = subprocess.check_output(['pdftotext', '-layout', str(legacy), '-'], text=True)
            self.assertLess(legacy_text.index(config['source_url']), legacy_text.index('First synthetic line.'))

    @unittest.skipUnless(find_spec('reportlab') and shutil.which('pdftotext'), "ReportLab and pdftotext required")
    def test_check_requires_presentation_receipt_and_keeps_legacy_cacheless_validation(self):
        body = "First synthetic line.\n\nSecond line must not change.\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = dict(self.config(), kind="sutta", collection="anguttara-nikaya",
                          version="synthetic", version_label="Example translator", row={},
                          source_label="Synthetic source", body=body,
                          body_sha256=sha256(body.encode()).hexdigest(),
                          output_root=root, html_path=root / 'reader.html',
                          site_path=root / 'reader.html', pdf_path=root / 'reader.pdf',
                          text_path=root / 'text.txt', collection_page=root / 'index.html',
                          entry_page=root / 'index.html', entry_href='reader.html')
            with (patch.object(builder, 'ROOT', root),
                  patch.object(builder, 'TIPITAKA', root / 'theravada/tipitaka'),
                  patch.object(builder, 'PDF_CACHE', root / 'cache.json'),
                  redirect_stdout(StringIO())):
                index = builder.index_records([record])

                def write_html():
                    page = builder.expected_html(record, index)
                    record['html_path'].write_text(page, encoding='utf-8')
                    parser = ReaderParser(); parser.feed(page)
                    for href in parser.links:
                        parsed = urlsplit(href)
                        if parsed.scheme or parsed.netloc or not parsed.path:
                            continue
                        path = unquote(parsed.path)
                        target = (root / 'site-entry/index.html' if path == '/'
                                  else root / path.lstrip('/'))
                        if not target.exists():
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_text('<a href="reader.html">Reader</a>', encoding='utf-8')

                def check():
                    builder.build([record], [record], jobs=1, check=True)

                config = builder.config_for(record, index)
                render_pdf(config, body, record['pdf_path'])
                legacy_pdf = record['pdf_path'].read_bytes()
                for defaults in ({}, {'body_italics': [], 'pdf_text_first': False}):
                    with self.subTest(legacy_defaults=defaults):
                        record.update(defaults)
                        write_html()
                        check()
                        self.assertFalse(builder.PDF_CACHE.exists())
                record.pop('body_italics'); record.pop('pdf_text_first')
                record['pdf_render_sha256'] = pdf_render_hash(config)
                legacy_cache = {'version': builder.PDF_RENDERER_VERSION, 'pdfs': {}}
                builder.record_pdf_result(record, legacy_cache)
                styles = ({'pdf_text_first': True},
                          {'body_italics': [self.span(body, 'must not')]},
                          {'pdf_text_first': True, 'body_italics': [self.span(body, 'must not')]})
                for style in styles:
                    with self.subTest(style=style):
                        record.pop('body_italics', None); record.pop('pdf_text_first', None)
                        record.update(style)
                        write_html()
                        record['pdf_path'].write_bytes(legacy_pdf)
                        verify_pdf_body(record['pdf_path'], body)
                        for cache in (legacy_cache, {'version': builder.PDF_RENDERER_VERSION, 'pdfs': {}}):
                            builder.write_cache(cache)
                            receipt = builder.PDF_CACHE.read_bytes()
                            with self.assertRaisesRegex(ValueError, 'presentation.*rebuild'):
                                check()
                            self.assertEqual(record['pdf_path'].read_bytes(), legacy_pdf)
                            self.assertEqual(builder.PDF_CACHE.read_bytes(), receipt)
                        render_pdf(builder.config_for(record, index), body, record['pdf_path'])
                        verify_pdf_body(record['pdf_path'], body)
                        cache = {'version': builder.PDF_RENDERER_VERSION, 'pdfs': {}}
                        builder.record_pdf_result(record, cache)
                        builder.write_cache(cache)
                        check()
                        record['pdf_path'].write_bytes(record['pdf_path'].read_bytes() + b'\n')
                        verify_pdf_body(record['pdf_path'], body)
                        with self.assertRaisesRegex(ValueError, 'presentation.*rebuild'):
                            check()


if __name__ == '__main__':
    unittest.main()
