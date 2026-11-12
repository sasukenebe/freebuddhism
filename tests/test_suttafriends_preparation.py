# SPDX-License-Identifier: 0BSD
"""Full protected articles include notes outside paragraphs; no implicit publish."""
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/buddhist_canon_pipeline"))
from prepare_suttafriends import article, source_metadata, checked


class SuttaFriendsPreparationTests(unittest.TestCase):
    def page(self, body):
        return ('<h1>Not article</h1><div class="entry-content">' + body
                + '</div><!-- .entry-content --><p>Outside text</p>').encode()

    def test_notes_lists_and_line_breaks_survive_independent_region_comparison(self):
        raw = self.page('<p>' + 'Original discourse. ' * 8 + '</p><fieldset><legend>Translator note</legend>'
                        '<ul><li>First &amp; second</li><li>Last note</li></ul></fieldset><p>Verse<br>Next line</p>')
        body, report = article(raw)
        for text in ('Translator note', 'First & second', 'Last note', 'Verse\nNext line'):
            self.assertIn(text, body)
        self.assertNotIn('Outside text', body)
        self.assertEqual(report['ordered_character_comparison'], 'PASS')
        self.assertEqual(report['element_counts']['li'], 2)

    def test_unknown_hidden_duplicate_and_incomplete_regions_are_rejected(self):
        for raw in (self.page('<p>' + 'Word ' * 30 + '</p><script>Not approved</script>'),
                    self.page('<p aria-hidden="true">' + 'Word ' * 30 + '</p>'),
                    self.page('<p>' + 'Word ' * 30 + '</p>') * 2,
                    self.page('<p>' + 'Word ' * 30 + '</p>')[:-100]):
            with self.subTest(raw=raw[:100]), self.assertRaises(ValueError): article(raw)

    def test_unbalanced_markup_and_nontext_payloads_cannot_be_silently_dropped(self):
        for body in ('<p>' + 'Word ' * 30 + '</p><img src="verse.png">',
                     '<p>' + 'Word ' * 30 + '</span>'):
            with self.assertRaises(ValueError): article(self.page(body))

    def test_incomplete_cached_selection_is_not_a_complete_batch(self):
        with self.assertRaisesRegex(ValueError, 'exactly'): source_metadata({'texts': {}})

    def test_changed_source_and_unsafe_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = b'Original cached bytes'
            (root / 'source.html').write_bytes(raw)
            expected = hashlib.sha256(raw).hexdigest()
            self.assertEqual(checked(root, 'source.html', expected), raw)
            with self.assertRaisesRegex(ValueError, 'hash changed'): checked(root, 'source.html', '0' * 64)
            with self.assertRaisesRegex(ValueError, 'Unsafe'): checked(root, '../source.html', expected)
            (root / 'link.html').symlink_to(root / 'source.html')
            with self.assertRaisesRegex(ValueError, 'Unsafe'): checked(root, 'link.html', expected)


if __name__ == '__main__': unittest.main()
