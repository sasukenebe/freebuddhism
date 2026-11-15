# SPDX-License-Identifier: 0BSD
"""Navigation regressions; search execution uses an optional saved browser DOM.

Generate a small offline page with --write-browser-fixture PATH, run Chromium
on PATH's file URL with ?view=list and --dump-dom, then validate that saved DOM
with --check-browser-result PATH. Browser execution stays with the operator.
Ordinary unittest skips only the browser-result test unless
FREEBUDDHISM_NAVIGATION_DOM names that saved result. No JS runtime is required.
"""

import argparse
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unicodedata
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
import build_deploy_site as site
from public_site_catalog import canonical_slug, navigation_nodes


# Synthetic navigation titles, not translation text. DN 1 deliberately has title
# matches before the exact AN/MN IDs in the original collection order.
TEXTS = (
    ("DN 1", "A guide to AN 1.1 and MN 1", "digha-nikaya", True),
    ("MN 1", "Mūlapariyāya", "majjhima-nikaya", True),
    ("MN 2", "About MN 1", "majjhima-nikaya", True),
    ("MN 3", 'Ñāṇa & "notes"', "majjhima-nikaya", False),
    ("MN 10", "Other Majjhima discourse", "majjhima-nikaya", True),
    ("AN 1.1", "Rūpa", "anguttara-nikaya", True),
    ("AN 1.10", "Other Aṅguttara discourse", "anguttara-nikaya", True),
    ("AN 8.82", "Puṇṇiya", "anguttara-nikaya", True),
)
ALL_IDS = tuple(row[0] for row in TEXTS)
AN_MATCHES = ("AN 1.1", "DN 1", "AN 1.10")
MN_MATCHES = ("MN 1", "DN 1", "MN 2", "MN 10")
VECTORS = (
    ("AN1.1", AN_MATCHES),
    ("AN 1.1", AN_MATCHES),
    ("an1.1", AN_MATCHES),
    ("  An \t1.1  ", AN_MATCHES),
    ("MN1", MN_MATCHES),
    ("MN 1", MN_MATCHES),
    ("mn1", MN_MATCHES),
    ("MN\t1", MN_MATCHES),
    ("AN8.82", ("AN 8.82",)),
    ("an 8.82", ("AN 8.82",)),
    ("Puṇṇiya", ("AN 8.82",)),
    ("PUNNIYA", ("AN 8.82",)),
    (unicodedata.normalize("NFD", "Puṇṇiya"), ("AN 8.82",)),
    ("mūlapariyāya", ("MN 1",)),
    ("MULAPARIYAYA", ("MN 1",)),
    (unicodedata.normalize("NFD", "Mūlapariyāya"), ("MN 1",)),
    ("ÑĀṆA", ("MN 3",)),
    ("nana", ("MN 3",)),
    (unicodedata.normalize("NFD", "Ñāṇa"), ("MN 3",)),
    ('& "notes"', ("MN 3",)),
    ("1.1", ("DN 1", "AN 1.1", "AN 1.10")),
    ("AN1.1 and MN1", ("DN 1",)),
    ("AN 1.1 and MN 1", ("DN 1",)),
    ("MN 99", ()),
    ("no matching synthetic title", ()),
    (" \t ", ALL_IDS),
    ("", ALL_IDS),
)


class PageProbe(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.links = []
        self.buttons = []
        self.scripts = []
        self.report = ""
        self._link = self._button = self._script = None
        self._in_report = False
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self._link = {"href": attrs.get("href"), "label": ""}
            self.links.append(self._link)
        elif tag == "button":
            self._button = {**attrs, "label": ""}
            self.buttons.append(self._button)
        elif tag == "script":
            self._script = len(self.scripts)
            self.scripts.append("")
        elif tag == "pre" and attrs.get("id") == "navigation-search-results":
            self._in_report = True

    def handle_endtag(self, tag):
        if tag == "a":
            self._link = None
        elif tag == "button":
            self._button = None
        elif tag == "script":
            self._script = None
        elif tag == "pre":
            self._in_report = False

    def handle_data(self, data):
        if self._link is not None:
            self._link["label"] += data
        if self._button is not None:
            self._button["label"] += data
        if self._script is not None:
            self.scripts[self._script] += data
        if self._in_report:
            self.report += data


def collection_fixture():
    nodes = navigation_nodes()
    pages = {
        f"sutta/{collection}/{canonical_slug(reference)}/index.html": {
            "canonical_id": reference, "title": title, "collection": collection,
            "eligible": [{}] if available else [],
        }
        for reference, title, collection, available in TEXTS
    }
    with TemporaryDirectory() as directory:
        root = Path(directory)
        for key in {"tipitaka", "sutta", *(row[2] for row in TEXTS)}:
            page = root / nodes[key]["route"]
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(
                '<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<title>Navigation fixture</title></head><body>'
                '<h1>Navigation fixture</h1></body></html>', encoding="utf-8",
            )
        site._collection_browse_markup(root, "tipitaka", pages, set(nodes), nodes)
        return (root / nodes["tipitaka"]["route"]).read_text(encoding="utf-8")


_BROWSER_RUNNER = r'''<pre id="navigation-search-results">NOT_RUN</pre>
<script>(function(){
const output=document.getElementById("navigation-search-results");
try{
  const root=document.getElementById("collection-browser");
  const search=root.querySelector("[data-list-search]");
  const list=root.querySelector("[data-list-results]");
  const snapshot=()=>Array.from(list.querySelectorAll("li")).filter(item=>!item.hidden).map(item=>({
    id:item.dataset.canonicalId,label:item.textContent,href:item.querySelector("a")?.getAttribute("href")??null
  }));
  const mode=()=>({
    treeHidden:root.querySelector('[data-view="tree"]').hidden,
    listHidden:root.querySelector('[data-view="list"]').hidden,
    pressed:Array.from(root.querySelectorAll("button[data-mode]")).map(button=>button.getAttribute("aria-pressed"))
  });
  const report={initial:snapshot(),initialMode:mode(),queries:[]};
  for(const query of __QUERIES__){
    search.value=query;search.dispatchEvent(new Event("input",{bubbles:true}));
    report.queries.push({query,visible:snapshot()});
  }
  root.querySelector('button[data-mode="tree"]').click();
  report.treeMode=mode();report.treeURL=new URLSearchParams(location.search).get("view");
  root.querySelector('button[data-mode="list"]').click();
  report.listMode=mode();report.listURL=new URLSearchParams(location.search).get("view");
  report.status="COMPLETE";output.textContent=JSON.stringify(report);
}catch(error){output.textContent=JSON.stringify({status:"ERROR",message:String(error.stack||error)});}
})();</script>'''


def browser_fixture():
    queries = json.dumps([query for query, _expected in VECTORS])
    runner = _BROWSER_RUNNER.replace("__QUERIES__", queries)
    return collection_fixture().replace("</body>", runner + "\n</body>")


class NavigationMarkupTests(unittest.TestCase):
    def test_homepage_links_directly_to_existing_flat_list(self):
        page = PageProbe((ROOT / "site-entry/index.html").read_text(encoding="utf-8"))
        self.assertEqual(
            [link for link in page.links if link["label"] == "Find a text by ID or title"],
            [{"label": "Find a text by ID or title",
              "href": "/theravada/tipitaka/site/tipitaka.html?view=list"}],
        )

    def test_collection_tree_control_keeps_its_label(self):
        page = PageProbe(collection_fixture())
        self.assertEqual([button["label"] for button in page.buttons if button.get("data-mode") == "tree"], ["Tree"])

    def test_translation_readers_return_to_unchanged_shared_page(self):
        nodes = navigation_nodes()
        route = "sutta/anguttara-nikaya/an01-01/index.html"
        node_url = site.TIPITAKA_URL_PREFIX + route
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tipitaka = root / "theravada/tipitaka"
            shared = tipitaka / route
            shared.parent.mkdir(parents=True)
            shared.write_text(
                '<html><head><title>Shared</title></head><body><h1>Shared</h1>'
                '<h2>Locally available editions</h2><ul></ul></body></html>', encoding="utf-8",
            )
            records = []
            originals = []
            for version in ("first", "second"):
                reader_route = str(Path(route).with_name(f"an01-01-{version}.html"))
                record = {
                    "html_path": root / "readers/theravada/tipitaka" / reader_route,
                    "output_root": root / "readers", "version_label": version,
                }
                records.append(record)
                preserved = (
                    '<pre class="source-text">Synthetic body &amp; original punctuation.\n\nSecond paragraph.</pre>'
                    '<p>Complete synthetic copyright and licence notice.</p>'
                    f'<a href="https://example.org/{version}.pdf#page=2">Original source</a>'
                    f'<a href="{version}.txt">TXT</a><a href="{version}.html">HTML</a>'
                    f'<a href="{version}.pdf">PDF</a>'
                )
                reader = tipitaka / reader_route
                reader.write_text('<html><head><title>Reader</title></head><body><h1>Reader</h1>'
                                  + preserved + '</body></html>', encoding="utf-8")
                originals.append((reader, preserved))
            pages = {route: {"canonical_id": "AN 1.1", "title": "Synthetic title",
                             "collection": "anguttara-nikaya", "eligible": records}}
            site._finish_page_navigation(root, pages, nodes, records, set())
            for reader, preserved in originals:
                with self.subTest(reader=reader.name):
                    result = reader.read_text(encoding="utf-8")
                    self.assertIn(preserved, result)
                    links = PageProbe(result).links
                    self.assertIn({"label": "All translations for AN 1.1", "href": node_url}, links)
                    self.assertIn({"label": "Flat list", "href": node_url + "?view=list"}, links)
                    self.assertFalse(any(link["label"] == "Tree" for link in links))
            shared_page = PageProbe(shared.read_text(encoding="utf-8"))
            self.assertEqual([button["label"] for button in shared_page.buttons
                              if button.get("data-mode") == "tree"], ["Tree"])
            for version in ("first", "second"):
                self.assertIn({"label": version, "href": f"an01-01-{version}.html"}, shared_page.links)


class BrowserSearchTests(unittest.TestCase):
    def test_actual_browser_filter_and_ordering(self):
        path = os.environ.get("FREEBUDDHISM_NAVIGATION_DOM")
        if not path:
            self.skipTest("Run the offline Chromium fixture and supply FREEBUDDHISM_NAVIGATION_DOM")
        page = PageProbe(Path(path).read_text(encoding="utf-8"))
        self.assertIn(site._BROWSE_SCRIPT.removeprefix("<script>").removesuffix("</script>"), page.scripts,
                      "Browser evidence must execute the current generated search implementation")
        self.assertNotEqual(page.report, "NOT_RUN", "Chromium did not execute the fixture")
        report = json.loads(page.report)
        self.assertEqual(report.get("status"), "COMPLETE", report)
        expected = {
            reference: {
                "id": reference,
                "label": f"{reference} — {title} — " + ("1 eligible edition" if available else "no eligible local edition"),
                "href": f"../sutta/{collection}/{canonical_slug(reference)}/index.html" if available else None,
            }
            for reference, title, collection, available in TEXTS
        }
        self.assertEqual(report["initial"], [expected[reference] for reference in ALL_IDS])
        self.assertEqual(len(report["queries"]), len(VECTORS))
        for actual, (query, references) in zip(report["queries"], VECTORS):
            with self.subTest(query=query):
                self.assertEqual(actual["query"], query)
                self.assertEqual(actual["visible"], [expected[reference] for reference in references])
        list_mode = {"treeHidden": True, "listHidden": False, "pressed": ["false", "true"]}
        self.assertEqual(report["initialMode"], list_mode, "Open the fixture URL with ?view=list")
        self.assertEqual(report["treeMode"], {"treeHidden": False, "listHidden": True, "pressed": ["true", "false"]})
        self.assertEqual(report["listMode"], list_mode)
        self.assertEqual(report["treeURL"], "tree")
        self.assertEqual(report["listURL"], "list")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--write-browser-fixture", type=Path)
    action.add_argument("--check-browser-result", type=Path)
    args, remaining = parser.parse_known_args()
    if args.write_browser_fixture:
        args.write_browser_fixture.parent.mkdir(parents=True, exist_ok=True)
        with args.write_browser_fixture.open("x", encoding="utf-8") as output:
            output.write(browser_fixture())
        print(args.write_browser_fixture.resolve().as_uri() + "?view=list")
    else:
        if args.check_browser_result:
            os.environ["FREEBUDDHISM_NAVIGATION_DOM"] = str(args.check_browser_result)
            remaining = ["BrowserSearchTests", *remaining]
        unittest.main(argv=[sys.argv[0], *remaining])
