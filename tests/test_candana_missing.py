import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/buddhist_canon_pipeline'))
from check_candana_missing import candidates, check_one, run_batch, sha, json_bytes, OUTPUT, MARKER


class MissingCandanaTests(unittest.TestCase):
    def fixture(self, root, count=1):
        rows = []
        for i in range(1, count + 1):
            folder = root / f'build/candana-batch-review/sources/{i}'
            folder.mkdir(parents=True)
            pdf, text = b'%PDF-synthetic-fixture', f'MN {i}\nCopyright Candana\n\nEvery word survives.\f'.encode()
            (folder/'source.pdf').write_bytes(pdf); (folder/'mupdf.txt').write_bytes(text)
            (folder/'report.json').write_bytes(json_bytes({'source_sha256': sha(pdf), 'output_hashes': {
                'source.pdf': sha(pdf), 'mupdf.txt': sha(text)}}))
            rows.append({'source_url':f'https://www.mindreleased.com/s/text{i}.pdf',
                         'source_sha256':sha(pdf), 'draft_sha256':sha(text), 'reference_group':f'MN {i}',
                         'state':'COLLECTED','draft_review':f'sources/{i}/index.html',
                         'same_site_reference_has_candana':False, 'exact_source_readers_imported':0,
                         'rights':'NEEDS_PERMISSION_REVIEW'})
        inventory = {'offers':rows,'next_import_groups':[{'source_urls':[r['source_url']]} for r in rows]}
        path=root/'build/candana-corpus/inventory.json';path.parent.mkdir(parents=True)
        path.write_bytes(json_bytes(inventory))
        def compare(pdf, text):
            return {'pdf_sha256':sha(pdf.read_bytes()),'text_sha256':sha(text.read_bytes()),
                    'pdf_pages':1,'status':'TEXT_COMPARISON_PASS','disagreements':[], 'image_only_pages':[]}
        return inventory, Mock(side_effect=compare)

    def test_verified_result_is_reused_without_new_conversion_or_permission(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inventory,audit=self.fixture(root)
            target=root/OUTPUT/'one'
            result, reused=check_one(root,target,inventory['offers'][0],'tools-v1',audit)
            self.assertFalse(reused);self.assertEqual(audit.call_count,1)
            self.assertFalse(result['permission_approved_by_this_check'])
            self.assertFalse(result['publication_approved'])
            self.assertEqual(result['suggested_pdf_spot_checks'],[1])
            self.assertEqual((result,True),check_one(root,target,inventory['offers'][0],'tools-v1',audit))
            self.assertEqual(audit.call_count,1)
            self.assertEqual(result['copyright_notices'][0]['pdf_page'],1)

    def test_changed_comparison_or_tools_are_checked_again(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inv,audit=self.fixture(root);target=root/OUTPUT/'one';row=inv['offers'][0]
            check_one(root,target,row,'v1',audit)
            (target/'comparison.json').write_bytes(b'changed')
            self.assertFalse(check_one(root,target,row,'v1',audit)[1])
            self.assertFalse(check_one(root,target,row,'v2',audit)[1])
            self.assertEqual(audit.call_count,3)

    def test_changed_source_or_draft_never_reuses_old_success(self):
        for filename in ['source.pdf','mupdf.txt']:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);inv,audit=self.fixture(root);target=root/OUTPUT/'one';row=inv['offers'][0]
                check_one(root,target,row,'v1',audit)
                (root/'build/candana-batch-review/sources/1'/filename).write_bytes(b'changed')
                with self.assertRaises(ValueError): check_one(root,target,row,'v1',audit)
                self.assertEqual(audit.call_count,1)

    def test_batch_limit_progresses_and_repeated_run_performs_zero_conversions(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inv,audit=self.fixture(root,3)
            first=run_batch(root,2,auditor=audit,identity='v1')
            self.assertEqual((first['checked_now'],first['waiting']),(2,1))
            second=run_batch(root,2,auditor=audit,identity='v1')
            self.assertEqual((second['checked_now'],second['unchanged_checks_reused'],second['waiting']),(1,2,0))
            third=run_batch(root,2,auditor=audit,identity='v1')
            self.assertEqual((third['checked_now'],third['unchanged_checks_reused']),(0,3))
            self.assertEqual(audit.call_count,3)
            changed=run_batch(root,1,auditor=audit,identity='v2')
            self.assertEqual((changed['checked_now'],changed['waiting']),(1,2))
            self.assertEqual(changed['network_requests'],0)

    def test_disagreement_and_failed_checks_stay_visible_and_unpublished(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inv,audit=self.fixture(root)
            original=audit.side_effect
            audit.side_effect=lambda p,t:dict(original(p,t),status='DISAGREEMENTS_RETAINED',disagreements=['page 1'],
                                             word_boundary_disagreements=['poppler_raw: page 1'])
            result=run_batch(root,1,auditor=audit,identity='v1')
            self.assertEqual(result['results'][0]['disagreements'],['page 1'])
            self.assertFalse(result['results'][0]['publication_approved'])
            self.assertIn('source.pdf#page=1', (root/OUTPUT/'index.html').read_text())
            audit.side_effect=RuntimeError('Deliberate test failure')
            result=run_batch(root,1,auditor=audit,identity='v2')
            self.assertEqual(result['results'][0]['status'],'CHECK_FAILED')
            self.assertNotIn('comparison_status',result['results'][0])

    def test_existing_unmarked_output_and_unknown_text_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inv,audit=self.fixture(root)
            with self.assertRaises(ValueError): run_batch(root,texts=['MN 99'],auditor=audit,identity='v1')
            output=root/OUTPUT;output.mkdir();(output/'personal-note').write_text('Do not overwrite')
            with self.assertRaises(ValueError): run_batch(root,auditor=audit,identity='v1')
            self.assertEqual((output/'personal-note').read_text(),'Do not overwrite')

    def test_only_unpublished_texts_and_safe_paths_are_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inv,audit=self.fixture(root)
            inv['offers'][0]['same_site_reference_has_candana']=True
            with self.assertRaises(ValueError): candidates(inv)
            inv['offers'][0]['same_site_reference_has_candana']=False
            inv['offers'][0]['draft_review']='../../outside/index.html'
            with self.assertRaises(ValueError): check_one(root,root/OUTPUT/'one',inv['offers'][0],'v1',audit)


if __name__ == '__main__':
    unittest.main()
