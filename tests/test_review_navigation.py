# SPDX-License-Identifier: 0BSD
"""Available readers, excluded sources and combined views retain distinct scopes."""
from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
import build_deploy_site as site
from distribution_policy import WEBSITE_DISTRIBUTION, WEBSITE_LICENSE
from public_site_catalog import navigation_nodes


class NavigationProbe(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.links = []
        self.details = []
        self.inputs = []
        self.active_link = None
        self.body_parts = []
        self.in_source = False
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.active_link = {"href": attrs.get("href"), "label": "", "parents": list(self.stack)}
        if tag == "details":
            self.details.append(attrs)
        if tag == "input":
            self.inputs.append(attrs)
        if tag == "pre" and attrs.get("class") == "source-text":
            self.in_source = True
        if tag not in {"meta", "link", "input", "br", "hr", "img"}:
            self.stack.append((tag, attrs))

    def handle_endtag(self, tag):
        if tag == "a" and self.active_link is not None:
            self.links.append(self.active_link)
            self.active_link = None
        if tag == "pre":
            self.in_source = False
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, value):
        if self.active_link is not None:
            self.active_link["label"] += value
        if self.in_source:
            self.body_parts.append(value)


class ReviewNavigationTests(unittest.TestCase):
    collection = "anguttara-nikaya"
    route = "sutta/anguttara-nikaya/an01-01/index.html"
    body = "Synthetic source & punctuation.\n\nSecond original paragraph.\n"
    preserved = (
        '<pre class="source-text">Synthetic source &amp; punctuation.\n\n'
        'Second original paragraph.\n</pre>'
        '<p>Complete synthetic copyright and licence notice. Completeness: UNKNOWN.</p>'
        '<a href="https://example.org/original.pdf">Original source</a>'
        '<a href="synthetic.txt">TXT</a><a href="synthetic.pdf">PDF</a>'
    )

    def records(self, root):
        records = []
        for version, website_only in (("candana-website", True), ("other", False)):
            record = {
                "kind": "sutta", "canonical_id": "AN 1.1", "title": "Synthetic title",
                "collection": self.collection, "version": version,
                "version_label": "Candana website edition" if website_only else "Other translation",
                "translator": "Synthetic translator", "source_url": "https://example.org/source",
                "license": WEBSITE_LICENSE if website_only else "CC0-1.0",
                "license_url": "https://example.org/terms",
                "license_notice": "Complete synthetic copyright and licence notice.",
                "completeness_status": "UNKNOWN", "output_root": root / "readers",
                "html_path": root / "readers/theravada/tipitaka" / Path(self.route).with_name(
                    f"an01-01-{version}.html"),
            }
            if website_only:
                record.update(website_record={"canonical_id": "AN 1.1"},
                              distribution=dict(WEBSITE_DISTRIBUTION))
            records.append(record)
        return records

    def info(self, records):
        return {"canonical_id": "AN 1.1", "title": "Synthetic title",
                "collection": self.collection, "eligible": records, "restricted": [{
                    "source_group": "Mind Released — Bhikkhu Candana PDFs",
                    "rights_status": "RIGHTS_UNVERIFIED", "completeness_status": "UNKNOWN",
                    "completeness_scope": "Exact standalone source boundary remains unverified.",
                }]}

    def test_source_exclusions_preserve_metadata_and_explain_available_candana(self):
        with TemporaryDirectory() as directory:
            info = self.info(self.records(Path(directory)))
            original = deepcopy(info)
            section = site._excluded_editions_markup(info)
        self.assertEqual(info, original)
        self.assertIn("<h2>Excluded source files and editions</h2>", section)
        self.assertIn("Individually reviewed Candana readers remain available above.", section)
        self.assertIn("their original PDFs remain excluded from local publication", section)
        self.assertIn("Mind Released — Bhikkhu Candana PDFs", section)
        self.assertIn("Completeness: UNKNOWN. Exact standalone source boundary remains unverified.", section)
        self.assertNotIn("Not included in this build", section)

    def test_candana_coexistence_note_is_not_added_for_unrelated_or_missing_editions(self):
        with TemporaryDirectory() as directory:
            records = self.records(Path(directory))
            for eligible, source_group in ((records[1:], "Mind Released — Bhikkhu Candana PDFs"),
                                           (records, "Another publisher"), ([], "Another publisher")):
                with self.subTest(source_group=source_group, eligible=len(eligible)):
                    info = self.info(eligible)
                    info["restricted"][0]["source_group"] = source_group
                    section = site._excluded_editions_markup(info)
                    self.assertNotIn("Candana readers remain available", section)
                    self.assertIn("Completeness: UNKNOWN", section)
            info = self.info(records)
            info["restricted"] = []
            self.assertEqual(site._excluded_editions_markup(info), "")

    def test_shared_and_current_reader_links_explain_only_the_website_edition_exclusion(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tipitaka = root / "theravada/tipitaka"
            records = self.records(root)
            info = self.info(records)
            node = tipitaka / self.route
            node.parent.mkdir(parents=True)
            node.write_text('<html><head><title>Shared</title></head><body><h1>Shared</h1>'
                            '<h2>Locally available editions</h2><ul></ul>'
                            + site._excluded_editions_markup(info) + '</body></html>', encoding="utf-8")
            readers = []
            for record in records:
                reader = tipitaka / Path(self.route).with_name(record["html_path"].name)
                reader.write_text('<html><head><title>Reader</title></head><body><h1>Reader</h1>'
                                  + self.preserved + '</body></html>', encoding="utf-8")
                readers.append(reader)
            homepage = root / "index.html"
            homepage.write_text("Synthetic homepage must remain byte-identical.\n", encoding="utf-8")
            original_homepage = homepage.read_bytes()
            site._finish_page_navigation(root, {self.route: info}, navigation_nodes(), records, set())
            shared = node.read_text(encoding="utf-8")
            shared_probe = NavigationProbe(shared)
            label = "All Text on One Page (website-only edition not included)"
            shared_control = next(link for link in shared_probe.links if link["label"] == label)
            self.assertIn("&text=" + self.route.removesuffix("/index.html"), shared_control["href"])
            self.assertIn("Use the individual reader", shared)
            self.assertIn("Excluded source files and editions", shared)
            self.assertIn("Candana readers remain available above", shared)
            self.assertIn('data-view="tree"><details open><summary>Translations</summary>', shared)
            for reader, website_only in zip(readers, (True, False)):
                with self.subTest(reader=reader.name):
                    result = reader.read_text(encoding="utf-8")
                    probe = NavigationProbe(result)
                    self.assertIn(self.preserved, result)
                    self.assertEqual("".join(probe.body_parts), self.body)
                    combined = [link for link in probe.links if link["label"].startswith("All Text on One Page")]
                    self.assertEqual(len(combined), 1)
                    self.assertEqual(combined[0]["label"], label if website_only else "All Text on One Page")
                    self.assertEqual('class="combined-reader-exclusion"' in result, website_only)
                    if website_only:
                        self.assertTrue(any(link["href"] == reader.name and link["label"] == records[0]["version_label"]
                                            for link in probe.links))
            self.assertTrue(any(link["href"] == readers[0].name and link["label"] == records[0]["version_label"]
                                for link in shared_probe.links))
            self.assertEqual(homepage.read_bytes(), original_homepage)

    def test_unrestricted_shared_page_keeps_its_unqualified_combined_link(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            info = self.info(self.records(root)[1:])
            markup = site._text_node_browser(root / "theravada/tipitaka", self.route, info)
        combined = [link for link in NavigationProbe(markup).links
                    if link["label"].startswith("All Text on One Page")]
        self.assertEqual([link["label"] for link in combined], ["All Text on One Page"])
        self.assertNotIn("combined-reader-exclusion", markup)

    def test_combined_payload_still_excludes_website_only_edition(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            records = self.records(root)
            info = self.info(records)
            tipitaka = root / "theravada/tipitaka"
            self.assertEqual(site._write_continuous_reader(tipitaka, {self.route: info}, {}), 1)
            payload = json.loads((tipitaka / "site/reading-index.json").read_text(encoding="utf-8"))
            editions = payload["texts"][0]["editions"]
            self.assertEqual([edition["id"] for edition in editions], ["other"])
            self.assertEqual(editions[0]["license_notice"], records[1]["license_notice"])
            self.assertEqual(editions[0]["completeness_status"], "UNKNOWN")
            info["eligible"] = records[:1]
            self.assertEqual(site._write_continuous_reader(tipitaka, {self.route: info}, {}), 0)
            payload = json.loads((tipitaka / "site/reading-index.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["texts"], [])

    def test_search_link_is_visible_outside_closed_tree_and_reuses_the_flat_list(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            nodes = navigation_nodes()
            index = root / nodes[self.collection]["route"]
            index.parent.mkdir(parents=True)
            index.write_text('<html><head><title>Collection</title></head><body>'
                             '<h1>Collection</h1></body></html>', encoding="utf-8")
            info = self.info(self.records(root))
            site._collection_browse_markup(root, self.collection, {self.route: info}, {self.collection}, nodes)
            page = index.read_text(encoding="utf-8")
        probe = NavigationProbe(page)
        links = [link for link in probe.links if link["label"] == "Find by sutta number/title"]
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["href"], "?view=list#collection-browser")
        self.assertFalse(any(tag == "details" or "data-view" in attrs for tag, attrs in links[0]["parents"]))
        self.assertTrue(probe.details)
        self.assertTrue(all("open" not in attrs for attrs in probe.details))
        self.assertEqual(len([attrs for attrs in probe.inputs if "data-list-search" in attrs]), 1)
        self.assertIn('show(new URLSearchParams(location.search).get("view")==="list"?"list":"tree")', page)
        self.assertIn('data-canonical-id="AN 1.1"', page)


if __name__ == "__main__":
    unittest.main()
