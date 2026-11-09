from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
from public_candana_review import (  # noqa: E402
    INPUT, MANIFEST, ROUTE, SNP_SHA, TEXT_SHA, digest, expected_manifest, payload, write_review,
)


class BodyText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = False
        self.parts = []
        self.editorial = False

    def handle_starttag(self, tag, attrs):
        if tag == "div" and ("class", "converted-text") in attrs:
            self.active = True
        if tag == "span" and ("class", "editorial") in attrs:
            self.editorial = True

    def handle_endtag(self, tag):
        if tag == "div":
            self.active = False
        if tag == "span":
            self.editorial = False

    def handle_data(self, data):
        if self.active and not self.editorial:
            self.parts.append(data)


class PublicCandanaReviewTests(unittest.TestCase):
    def test_complete_snapshot_contains_391_pages_73_suttas_and_unchanged_raw_text(self):
        files = payload()
        self.assertEqual(len(files), 152)
        self.assertEqual(digest(files["original.pdf"]), SNP_SHA)
        self.assertEqual(digest(files["converted.txt"]), TEXT_SHA)
        manifest = json.loads(files["conversion.json"])
        self.assertEqual(manifest["pdf_pages"], 391)
        self.assertEqual(len(manifest["units"]), 80)
        self.assertEqual(sum(u["kind"] == "SUTTA_SOURCE_INTERVAL" for u in manifest["units"]), 73)
        self.assertFalse(manifest["canonical_mapping_approval"])
        self.assertFalse(manifest["full_human_proofread_approval"])
        for name, expected in manifest["output_hashes"].items():
            self.assertEqual(digest(files[name]), expected)

    def test_all_book_characters_survive_including_front_and_end_matter(self):
        files = payload()
        parser = BodyText()
        parser.feed(files["converted.html"].decode("utf-8"))
        shown = "".join("".join(parser.parts).split())
        self.assertEqual(shown, "".join(files["converted.txt"].decode("utf-8").split()))
        self.assertIn('“The Snake”', files["suttas/snp1.1.html"].decode("utf-8"))
        self.assertIn('first_pdf_page', files["conversion.json"].decode("utf-8"))

    def test_index_has_one_original_link_not_one_per_sutta_and_no_private_inventory(self):
        files = payload()
        index = files["index.html"].decode("utf-8")
        self.assertEqual(index.count('href="original.pdf"'), 1)
        self.assertEqual(index.count('>Converted text</a>'), 73)
        self.assertIn('href="converted.html"', index)
        self.assertNotIn('original.pdf#page=', index)
        for content in (files["index.html"], files["conversion.json"], files["review-request.txt"]):
            for private in (b'/home/', b'/tmp/', b'build/candana-', b'human-decisions', b'WAIT_PERMISSION'):
                self.assertNotIn(private, content)
        self.assertNotIn('PRIVATE', index)
        self.assertIn('not an approved new edition', index)

    def test_source_index_verse_breaks_and_folios_are_not_body_paragraphs(self):
        files = payload()
        snake = files["suttas/snp1.1.html"].decode()
        self.assertEqual(snake.count('<br>Thus, the Bhikkhu'), 16)
        self.assertEqual(snake.count('<br>“Thus, the Bhikkhu'), 0)  # page-start continuation
        self.assertIn('snake bite.<br>Thus,', snake)
        self.assertIn('<p class="source-folio">22 ', snake)
        self.assertNotIn('<p>22</p>', snake)
        full = files["converted.html"].decode()
        self.assertEqual(full.count('<tr><td>'), 73)
        self.assertIn('<td>Uraga Sutta “The Snake”</td><td>19</td>', full)
        self.assertIn('Mahābyūha Sutta “Greater Discourse on Getting Ready for Battle”</td><td>286', full)
        self.assertIn('Text-only rendering', full)
        self.assertNotIn('max-width', full)

    def test_changed_manifest_pdf_or_text_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / INPUT, root / INPUT)
            (root / MANIFEST).parent.mkdir(parents=True)
            (root / MANIFEST).write_text(json.dumps(expected_manifest()))
            for relative in (INPUT / "original.pdf", INPUT / "converted.txt", MANIFEST):
                path = root / relative
                before = path.read_bytes()
                path.write_bytes(before + b'changed')
                with self.assertRaises(ValueError):
                    payload(root)
                path.write_bytes(before)
            manifest = expected_manifest()
            manifest["canonical_mapping_approval"] = True
            (root / MANIFEST).write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                payload(root)

    def test_generated_set_is_exact_and_cannot_replace_a_site_or_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            generated = write_review(destination)
            self.assertEqual(len(generated), 152)
            self.assertEqual(generated, {p for p in destination.rglob('*') if p.is_file()})
            with self.assertRaises(ValueError):
                write_review(destination)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            (destination / "reviews").symlink_to(destination, target_is_directory=True)
            with self.assertRaises(ValueError):
                write_review(destination)


if __name__ == "__main__":
    unittest.main()
