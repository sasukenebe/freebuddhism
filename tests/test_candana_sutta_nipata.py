import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/buddhist_canon_pipeline'))
from candana_sutta_nipata import BOOK_ID, REPORT, AUDIT, plan, install, reader_body, verify
from import_candana import verified_manifest
from build_eligible_readers import collect_candana_records, config_for, index_records
from render_cc0_reader import ReaderParser, render_html


class SuttaNipataImportTests(unittest.TestCase):
    def test_all_73_explicit_references_map_once_and_keep_source_hashes(self):
        book, texts, report, files = plan()
        self.assertEqual(len(texts), 73)
        self.assertEqual(len({t['canonical_id'] for t in texts}), 73)
        self.assertEqual(texts[0]['canonical_id'], 'Snp 1.1')
        self.assertEqual(texts[-1]['canonical_id'], 'Snp 5.19')
        self.assertEqual(report['source_units_not_imported'], ['front-matter', 'book-1', 'book-2', 'book-3', 'book-4', 'book-5', 'back-matter'])
        self.assertFalse(report['human_proofreading_approved'])
        for t in texts:
            raw = files[t['local_path']]
            self.assertEqual(hashlib.sha256(raw).hexdigest(), t['sha256'])
            self.assertEqual(hashlib.sha256(raw.decode().split('\n\n', 1)[1].encode()).hexdigest(), t['body_sha256'])
        self.assertIn('The Snake', texts[0]['title'])
        self.assertEqual(book['permission_pages'], [7])

    def test_reflow_keeps_hard_breaks_but_not_arbitrary_pdf_width_or_footer(self):
        unit = {'id': 'snp1.1', 'first_pdf_page': 22,
                'body': '1. “Keep every\nword.\nThus, the Bhikkhu repeats.\n\n22 \n\n\f'}
        body, folios = reader_body(unit)
        self.assertEqual(folios, [22])
        self.assertEqual(body, '1. “Keep every word.\nThus, the Bhikkhu repeats.\n')
        with self.assertRaises(ValueError):
            reader_body(dict(unit, body=unit['body'].replace('22 ', '23 ')))
        body, folios = reader_body({'id':'snp2.1','first_pdf_page':23,'body':'22 is a body number.\n\nNotes 19 and 22 remain.\f'})
        self.assertIn('Notes 19 and 22 remain.', body)
        self.assertEqual(folios, [])

    def test_installed_manifest_and_readers_match_generated_plan(self):
        manifest = verified_manifest(require_review=True)
        rows = [r for r in manifest['texts'] if r['book'] == BOOK_ID]
        self.assertEqual(len(rows),73)
        self.assertEqual(len(manifest['texts']),874)
        records = collect_candana_records(ROOT / 'build/snp-unit-readers')
        record = next(r for r in records if r['canonical_id']=='Snp 1.1')
        rendered = render_html(config_for(record,index_records(records)), record['body'])
        parser = ReaderParser(); parser.feed(rendered)
        self.assertEqual(''.join(parser.source_parts),record['body'])
        self.assertEqual(record['body'].count('\nThus, the Bhikkhu'),16)
        self.assertNotIn('\n\n22\n',record['body'])
        self.assertIn('2023',record['reuse_notice'])

    def test_changed_source_audit_reference_reader_or_report_fails_closed(self):
        manifest = json.loads((ROOT/'metadata/source-manifests/candana.json').read_text())
        original = Path.read_bytes
        for fragment in [AUDIT, 'sutta-nipata/converted.txt', 'sutta-nipata/original.pdf',
                         'suttacentral-sujato-text-ledger.tsv', 'candana/snp/snp1.1.txt']:
            def read(path, needle=fragment):
                data=original(path)
                return data+b'changed' if path.as_posix().endswith(needle) else data
            with patch.object(Path,'read_bytes',read):
                with self.assertRaises((ValueError,KeyError)):
                    verify(ROOT,manifest,True)
        bad=json.loads(json.dumps(manifest)); bad['snp_extension']['reader_count']=72
        with self.assertRaises(ValueError): verify(ROOT,bad,True)
        bad=json.loads(json.dumps(manifest)); bad['texts'][-1]['canonical_id']='Snp 5.18'
        with self.assertRaises(ValueError): verify(ROOT,bad,True)

    def test_repeated_offline_import_is_idempotent_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for relative in ['review-sources/candana-sutta-nipata/original.pdf',
                             'review-sources/candana-sutta-nipata/converted.txt', AUDIT,
                             'theravada/tipitaka/sutta/suttacentral-sujato-text-ledger.tsv',
                             'metadata/source-manifests/candana.json', 'metadata/eligible-texts.json',
                             'metadata/eligible-assets.json','metadata/public-file-allowlist.json']:
                path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/relative,path)
            result=install(root)
            before={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(result['network_requests'],0)
            self.assertEqual(result,install(root))
            self.assertEqual(before,{p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()})
            path=root/'theravada/tipitaka/translations/en/candana/snp/snp1.1.txt'
            path.write_bytes(b'different user file')
            with self.assertRaisesRegex(ValueError,'Refusing to replace'):
                install(root)
            self.assertEqual(path.read_bytes(),b'different user file')
