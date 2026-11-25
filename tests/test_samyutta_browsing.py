"""Thematic browsing must not mutate text, edition, route or archive identity."""
import copy
from html.parser import HTMLParser
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
import build_deploy_site as site
from public_site_catalog import collection_path, navigation_nodes


class TreeProbe(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.details = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        if tag == "details":
            self.details.append(dict(attrs))


class SamyuttaBrowsingTests(unittest.TestCase):
    route = "sutta/samyutta-nikaya/sn47-41/index.html"

    def pages(self):
        return {self.route: {"canonical_id": "SN 47.41", "title": "The Deathless",
                            "collection": "samyutta-nikaya", "eligible": [{}]}}

    def test_source_records_and_stable_routes_are_not_reclassified(self):
        source = self.pages()
        original = copy.deepcopy(source)
        pages = site._samyutta_browse_pages(source)
        self.assertEqual(source, original)
        self.assertEqual(set(source), set(pages))
        self.assertIs(pages[self.route]["eligible"], source[self.route]["eligible"])
        self.assertEqual(pages[self.route]["source_collection"], "samyutta-nikaya")
        self.assertEqual(pages[self.route]["collection"], "samyutta-nikaya/sn47-amatavagga")
        self.assertFalse(pages[self.route]["thematic_unmapped"])

    def test_every_structural_page_has_shared_views_closed_branches_and_source_links(self):
        nodes = navigation_nodes()
        pages = site._samyutta_browse_pages(self.pages())
        with TemporaryDirectory() as directory:
            root = Path(directory)
            allowed = {}
            self.assertEqual(site._write_samyutta_navigation_pages(root, allowed, nodes), 300)
            self.assertEqual(len(allowed), 300)
            self.assertTrue(all(not value["archive"] for value in allowed.values()))
            for key in ("samyutta-nikaya/sn-mahavaggasamyutta", "samyutta-nikaya/sn47",
                        "samyutta-nikaya/sn47-amatavagga"):
                markup = site._collection_browse_markup(root, key, pages, set(nodes), nodes)
                result = (root / nodes[key]["route"]).read_text()
                self.assertIn("Find by sutta number/title", markup)
                self.assertIn("All Text on One Page", markup)
                self.assertIn("SN 47.41", markup)
                self.assertIn("pinned chapter membership", result)
                self.assertIn("The Deathless", result)
                self.assertTrue(all("open" not in attrs for attrs in TreeProbe(result).details))
            chapter = (root / nodes["samyutta-nikaya/sn47-amatavagga"]["route"]).read_text()
            self.assertNotIn("SN 47 (1 texts)", chapter)
            self.assertIn("Mindfulness Meditation", chapter)
            self.assertIn("Freedom From Death", chapter)
            self.assertIn('data-search="SN 47.41', chapter)
            self.assertIn("Mindfulness Meditation", chapter.split('data-search="', 1)[1].split('"', 1)[0])

    def test_breadcrumbs_include_the_sourced_book_collection_and_chapter(self):
        nodes = navigation_nodes()
        path = collection_path("samyutta-nikaya/sn47-amatavagga", nodes)
        self.assertEqual([node["id"] for node in path][-4:], ["samyutta-nikaya",
                         "samyutta-nikaya/sn-mahavaggasamyutta", "samyutta-nikaya/sn47",
                         "samyutta-nikaya/sn47-amatavagga"])
        self.assertIn("SN 47", path[-2]["title"])
        self.assertIn("Mindfulness", path[-2]["tree_title"])

    def test_numeric_flat_order_does_not_change_with_chapter_ancestry(self):
        source = self.pages()
        for reference in ("SN 47.50", "SN 47.2", "SN 47.1", "SN 47.11-20"):
            source[reference] = {"canonical_id": reference, "collection": "samyutta-nikaya",
                                 "title": reference, "eligible": []}
        nodes = navigation_nodes()
        pages = site._samyutta_browse_pages(source)
        ordered = sorted(pages.values(), key=lambda info: site._browse_order(info, nodes))
        self.assertEqual([info["canonical_id"] for info in ordered],
                         ["SN 47.1", "SN 47.2", "SN 47.11-20", "SN 47.41", "SN 47.50"])

    def test_translation_panel_remains_expanded(self):
        info = site._samyutta_browse_pages(self.pages())[self.route]
        info["eligible"] = []
        result = site._text_node_browser(ROOT, self.route, info)
        self.assertIn('<details open><summary>Translations</summary>', result)


if __name__ == "__main__":
    unittest.main()
