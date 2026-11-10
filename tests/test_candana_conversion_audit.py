from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/buddhist_canon_pipeline'))
from verify_candana_conversion import compare_pages, compact, source_html


class ConversionAuditTests(unittest.TestCase):
    def test_canonical_composition_is_not_a_character_loss_or_compatibility_fold(self):
        result = compare_pages(['ā word'], ['a\u0304\nword'])[0]
        self.assertFalse(result['exact_nonspace_match'])
        self.assertTrue(result['nfc_nonspace_match'])
        self.assertNotEqual(compact('ﬁ', True), compact('fi', True))

    def test_order_numbers_punctuation_and_missing_pages_cannot_be_normalized_away(self):
        for wrong in ['second first 1.', 'first second 2.', 'first second 1', 'first 1.']:
            self.assertFalse(compare_pages(['first second 1.'], [wrong])[0]['nfc_nonspace_match'])
        with self.assertRaises(ValueError):
            compare_pages(['page 1', 'page 2'], ['page 1'])

    def test_word_boundaries_and_explicit_folio_labels(self):
        comparison = compare_pages(['fi\nlling'], ['filling'])[0]
        self.assertTrue(comparison['nfc_nonspace_match'])
        self.assertFalse(comparison['nfc_word_boundaries_match'])
        data = ('<section id="snp1.1"><div class="converted-text"><p>snake bite.<br>Thus, '
                'the Bhikkhu</p><p class="source-folio">22 '
                '<span class="editorial">[printed page number]</span></p></div></section>')
        self.assertEqual(source_html(data.encode())['snp1.1'].split(),
                         'snake bite. Thus, the Bhikkhu 22'.split())
        self.assertNotEqual(source_html(data.replace('snake bite.', 'snakebite.').encode())['snp1.1'].split(),
                            'snake bite. Thus, the Bhikkhu 22'.split())

    def test_table_cells_remain_separate_words_and_duplicate_sections_fail(self):
        self.assertEqual(source_html(b'<div class="converted-text"><table><tr><td>Title</td>'
                                     b'<td>19</td></tr></table></div>')['individual'].split(), ['Title', '19'])
        with self.assertRaises(ValueError):
            source_html(b'<div class="converted-text">a</div><div class="converted-text">b</div>')
