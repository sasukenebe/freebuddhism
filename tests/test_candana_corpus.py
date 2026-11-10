from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/buddhist_canon_pipeline'))
from candana_corpus import Offers, references, group_offer, census, render, rights_signals, sha


class CandanaCorpusTests(unittest.TestCase):
    def fixtures(self):
        page = 'https://www.mindreleased.com/pali-suttas'
        url = 'https://www.mindreleased.com/s/MN-1-test.pdf'
        source = b'Frozen synthetic PDF, no source translation.'
        html = b'<a href="/s/MN-1-test.pdf">MN 1 <em>Test</em></a>'
        queue = {'jobs': [{'url': page, 'state': 'COLLECTED', 'cache': 'page.html', 'sha256': sha(html)},
                          {'url': url, 'state': 'COLLECTED', 'cache': 'source.pdf', 'sha256': sha(source)}]}
        rows = [{'source_url': url, 'rights': 'NEEDS_PERMISSION_REVIEW', 'issues': ['PERMISSION_REVIEW_REQUIRED']}]
        files = {'page.html': html, 'source.pdf': source}
        manifest = {'books': [], 'texts': []}
        return queue, rows, manifest, files

    def test_explicit_references_not_compressed_filename_guesses(self):
        self.assertEqual(references('MN22 and Ud. 2.10; Snp. 1.1'), ['MN 22', 'Snp 1.1', 'Ud 2.10'])
        self.assertEqual(references('AN VIII, Suttas 41-50'), ['AN 8.41-50'])
        self.assertEqual(references('SN 12.2 and SN 1.2'), ['SN 1.2', 'SN 12.2'])
        key, basis, issues = group_offer([], '', 'SN-12-test.pdf')
        self.assertTrue(key.startswith('unresolved:'))
        self.assertEqual(basis, 'REFERENCE_REVIEW')

    def test_label_and_opening_conflict_or_multiple_are_held(self):
        for labels, opening in [(['MN 1'], 'MN 2\nTitle'), (['MN 1', 'MN 2'], 'MN 1')]:
            key, _, issues = group_offer(labels, opening, 'test.pdf')
            self.assertTrue(key.startswith('unresolved:'))
            self.assertTrue(issues)
        self.assertEqual(group_offer(['MN 1'], 'MN 1\nBody quotes MN 2 later', 'x')[0], 'MN 1')
        self.assertEqual(group_offer([], 'Heading\nAN VIII:\nSuttas 41-50\nTitle', 'x')[0], 'AN 8.41-50')

    def test_same_reference_is_not_identical_edition_or_permission(self):
        q, rows, manifest, files = self.fixtures()
        manifest['texts'] = [{'canonical_id': 'MN 1', 'source_revision': 'a-different-book'}]
        live = {'texts': [{'canonical_id': 'MN 1', 'editions': [{'id': 'candana'}]}]}
        result = census(q, rows, manifest, files.__getitem__, live)
        offer = result['offers'][0]
        self.assertTrue(offer['same_reference_is_live'])
        self.assertTrue(offer['same_reference_is_not_edition_equivalence'])
        self.assertEqual(offer['exact_source_readers_imported'], 0)
        self.assertEqual(offer['rights'], 'NEEDS_PERMISSION_REVIEW')
        self.assertFalse(offer['publication_approved_by_census'])
        self.assertIsNone(result['summary']['whole_corpus_percentage'])
        offline = census(q, rows, manifest, files.__getitem__)
        self.assertEqual(offline['next_import_groups'], [])
        self.assertIn('has not confirmed it is live', render(offline)[0])

    def test_duplicate_bytes_and_duplicate_references_are_separate(self):
        q, rows, manifest, files = self.fixtures()
        second = dict(q['jobs'][1], url='https://www.mindreleased.com/s/second.pdf')
        q['jobs'].append(second)
        rows.append(dict(rows[0], source_url=second['url']))
        files['page.html'] += b'<a href="/s/second.pdf">MN 1</a>'
        q['jobs'][0]['sha256'] = sha(files['page.html'])
        result = census(q, rows, manifest, files.__getitem__)
        self.assertEqual(result['summary']['downloaded_offers'], 2)
        self.assertEqual(result['summary']['distinct_downloaded_file_hashes'], 1)
        self.assertEqual(len(result['exact_file_aliases']), 1)
        self.assertEqual(result['summary']['identified_standalone_reference_groups'], 1)
        self.assertIsNone(result['summary']['standalone_groups_without_live_candana_reader'])

    def test_every_missing_offer_is_retained_without_redownload(self):
        q, rows, manifest, files = self.fixtures()
        q['jobs'].append({'url': 'https://www.mindreleased.com/s/missing.pdf', 'state': 'MISSING'})
        result = census(q, rows, manifest, files.__getitem__, {'texts': []})
        self.assertEqual(result['summary']['written_offers'], 2)
        self.assertEqual(result['summary']['downloaded_offers'], 1)
        self.assertEqual(result['summary']['unresolved_offer_references'], 1)
        self.assertEqual(result['publisher_network_requests'], 0)
        self.assertEqual(result['model_calls'], 0)

    def test_changed_cache_or_duplicate_inventory_fails(self):
        q, rows, manifest, files = self.fixtures()
        for target in ['page.html', 'source.pdf']:
            changed = dict(files); changed[target] += b'changed'
            with self.assertRaises(ValueError): census(q, rows, manifest, changed.__getitem__)
        with self.assertRaises(ValueError): census(q, rows * 2, manifest, files.__getitem__)
        q['jobs'].append(q['jobs'][1])
        with self.assertRaises(ValueError): census(q, rows, manifest, files.__getitem__)

    def test_complete_rights_scan_retains_page_evidence_without_approval(self):
        rows = rights_signals('No notice\f' * 11 + 'Permission to redistribute this work.\f')
        self.assertEqual(rows[0]['pdf_page'], 12)
        self.assertIn('redistribute', rows[0]['excerpt'])
        self.assertFalse(rows[0]['permission_approved'])
        self.assertEqual(rows[0]['page_text_sha256'], sha('Permission to redistribute this work.'.encode()))

    def test_inventory_is_plain_safe_html_with_original_converted_links(self):
        q, rows, manifest, files = self.fixtures()
        rows[0]['review_path'] = 'sources/test/index.html'
        report = census(q, rows, manifest, files.__getitem__, {'texts': []})
        html, plain = render(report)
        self.assertIn('MN 1', plain)
        self.assertIn('Original PDF', html)
        self.assertIn('Converted text', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('<object', html)
        self.assertNotIn('max-width', html)

    def test_historical_manifest_source_is_retained_outside_current_offer_count(self):
        q, rows, manifest, files = self.fixtures()
        files['old.pdf'] = b'Historical edition'
        manifest['books'] = [{'id': 'old-snp', 'source_url': 'https://www.mindreleased.com/s/old.pdf',
                              'local_path': 'old.pdf', 'sha256': sha(files['old.pdf'])}]
        result = census(q, rows, manifest, files.__getitem__)
        self.assertEqual(result['summary']['written_offers'], 1)
        self.assertEqual(result['summary']['additional_historical_manifest_sources'], 1)
        self.assertEqual(result['historical_manifest_sources'][0]['reader_entries_from_exact_source'], 0)
        files['old.pdf'] += b'changed'
        with self.assertRaises(ValueError): census(q, rows, manifest, files.__getitem__)


if __name__ == '__main__':
    unittest.main()
