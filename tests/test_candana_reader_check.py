import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/buddhist_canon_pipeline'))
from check_candana_readers import compare, relative_url, SourceText, NoRedirect, include_website_sources


class CandanaReaderCheckTests(unittest.TestCase):
    def fixtures(self):
        text = {'canonical_id': 'Snp 1.1', 'url': '/snake/index.html',
                'editions': [{'id': 'sujato', 'url': '/other.html'},
                             {'id': 'candana', 'url': '/snake/candana.html'}]}
        sources = {'Snp 1.1': {'body': '“Snake” & word.\nThus, refrain.\n',
                              'book': 'snp', 'source_url': 'https://example.org/book.pdf#page=19'}}
        rendered = '<pre class="source-text">“Snake” &amp; word.\nThus, refrain.\n</pre>'.encode()
        return {'texts': [text]}, sources, rendered

    def test_exact_whitespace_unicode_and_html_entities(self):
        index, sources, rendered = self.fixtures()
        report = compare(index, sources, lambda _: rendered)
        self.assertEqual(report['readers_verified'], 1)
        self.assertEqual(report['model_calls'], 0)
        self.assertFalse(report['human_proofreading_approved'])
        self.assertFalse(report['layout_checked_by_this_command'])
        self.assertEqual(report['suggested_spot_checks'][0]['text_home'], '/snake/index.html')
        for broken in [rendered.replace(b'word', b'omitted'), rendered.replace(b'\nThus', b' Thus')]:
            with self.assertRaisesRegex(ValueError, 'differs'):
                compare(index, sources, lambda _: broken)

    def test_missing_duplicate_and_unexpected_edition_fails(self):
        index, sources, rendered = self.fixtures()
        for bad in [{'texts': []}, {'texts': index['texts'] * 2}]:
            with self.assertRaises(ValueError): compare(bad, sources, lambda _: rendered)
        index['texts'][0]['canonical_id'] = 'Snp 1.2'
        with self.assertRaises(ValueError): compare(index, sources, lambda _: rendered)

    def test_no_container_duplicate_nested_and_unclosed_fails(self):
        for body in ['', '<pre class="source-text">x',
                     '<pre class="source-text">x</pre><pre class="source-text">x</pre>',
                     '<pre class="source-text"><b>x</b></pre>']:
            with self.assertRaises(ValueError):
                parser = SourceText(); parser.feed(body); parser.body()

    def test_only_local_safe_reader_paths(self):
        self.assertEqual(relative_url('/texts/snake.html'), 'texts/snake.html')
        for value in ['https://other.org/x', '//other.org/x', '../x', '/x/../secret',
                      '/x/%2e%2e/secret', '/x%5csecret', '/x?query=1', '/x#fragment', '/x%00']:
            with self.assertRaises(ValueError): relative_url(value)
        with self.assertRaisesRegex(ValueError, 'redirect'):
            NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.org/x')

    def test_every_book_has_repeatable_first_middle_last_spot_checks(self):
        index, sources, rendered = self.fixtures()
        for i in range(2, 6):
            identity = f'Snp 1.{i}'
            index['texts'].append(dict(index['texts'][0], canonical_id=identity))
            sources[identity] = dict(sources['Snp 1.1'])
        first = compare(index, sources, lambda _: rendered)
        second = compare(index, sources, lambda _: rendered)
        self.assertEqual(first, second)
        self.assertEqual([r['text'] for r in first['suggested_spot_checks']],
                         ['Snp 1.1', 'Snp 1.3', 'Snp 1.5'])

    def test_only_exact_reviewed_attribute_free_italic_intervals_are_allowed(self):
        expected = [{'start': 0, 'end': 5}]
        parser = SourceText(expected)
        parser.feed('<pre class="source-text"><em>First</em> words.</pre>')
        self.assertEqual(parser.body(), 'First words.')
        for markup in ('<em>First words.</em>', '<em class="unreviewed">First</em> words.',
                       '<em><em>First</em></em> words.', 'First words.', '<em>First words.'):
            with self.subTest(markup=markup), self.assertRaises(ValueError):
                parser = SourceText(expected)
                parser.feed('<pre class="source-text">' + markup + '</pre>')
                parser.body()

    def test_website_sources_extend_rather_than_bypass_the_exact_reader_comparison(self):
        import candana_website as website
        index, sources, rendered = self.fixtures()
        row = {'canonical_id': 'SN 1.1', 'source_sha256': 'a' * 64, 'body_sha256': 'b' * 64,
               'text_sha256': 'c' * 64, 'processing_review_entry_id': 'synthetic-entry',
               'source_url': 'https://example.org/standalone.pdf', 'partition': {'italic_spans': [{'start': 0, 'end': 5}]}}
        fields = ('canonical_id', 'source_sha256', 'body_sha256', 'text_sha256', 'processing_review_entry_id')
        release = {'website_only_editions': [{key: row[key] for key in fields}]}
        with patch.object(website, 'manifest', return_value={'records': [row]}), \
                patch.object(website, 'checked_input', return_value=('', '', 'Synthetic header\n\nFirst words.')):
            include_website_sources(sources, release)
        index['texts'].append({'canonical_id': 'SN 1.1', 'url': '/standalone/index.html',
                               'editions': [{'id': 'candana', 'url': '/standalone/candana.html'}]})
        read = lambda path: (b'<pre class="source-text"><em>First</em> words.</pre>'
                             if path.startswith('/standalone/') else rendered)
        self.assertEqual(compare(index, sources, read)['readers_verified'], 2)
        with self.assertRaisesRegex(ValueError, 'differs'):
            compare(index, sources, lambda path: read(path).replace(b'First', b'Wrong'))
        with self.assertRaisesRegex(ValueError, 'missing'):
            compare({'texts': index['texts'][:1]}, sources, read)
        with patch.object(website, 'manifest', return_value={'records': [row]}):
            with self.assertRaisesRegex(ValueError, 'shadows'):
                include_website_sources(sources, release)
            changed = {'website_only_editions': [dict(release['website_only_editions'][0], text_sha256='d' * 64)]}
            with self.assertRaisesRegex(ValueError, 'manifest'):
                include_website_sources({}, changed)

    def test_default_release_does_not_open_optional_private_inputs(self):
        import candana_website as website
        with patch.object(website, 'manifest', side_effect=AssertionError('Must remain offline')):
            sources = {}
            include_website_sources(sources, {})
            self.assertEqual(sources, {})
