import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
sys.path.insert(0, str(ROOT / "tools"))
from render_cc0_reader import ReaderParser, render_html, render_pdf, verify_pdf_body  # noqa: E402
from build_eligible_readers import display_text_title  # noqa: E402
from build_deploy_site import (  # noqa: E402
    local_link_errors,
    normalize_webroot_permissions,
    safe_output_destination,
    _replace_sutta_coverage_intro,
    _replace_tipitaka_coverage_summary,
    _strip_unavailable_embeds,
    _display_canonical_title,
    _finish_page_navigation,
    _source_rows,
    _sutta_breadcrumb_markup,
    _text_group_label,
    _write_collection_browsers,
    _collection_browse_markup,
    _text_node_browser,
    _write_continuous_reader,
    _load_anguttara_menu,
    _load_vinaya_khandhaka_menu,
    _parse_an_range,
    _update_tipitaka_tree_counts,
    _vinaya_reference,
    _vinaya_source_group,
    _write_anguttara_index,
    _write_crawler_files,
    _write_vimanavatthu_story_pages,
)
from validate_public_tree import (  # noqa: E402
    PageAudit,
    actual_files,
    license_scope_for,
    refresh_allowlist_entries,
    RIGHTS_BASIS_BY_SCOPE,
    validate_excluded_inventory,
    validate_legacy_text_routes,
)
from buddhist_canon_pipeline.public_html_policy import (  # noqa: E402
    SITE_RIGHTS_BASIS,
    SITE_SCOPE,
    sha256_file,
    validate_site_content_manifest,
)
from public_site_catalog import collection_path, navigation_nodes  # noqa: E402


class PublicReleasePolicyTests(unittest.TestCase):
    def test_root_homepage_preserves_original_copy_with_root_safe_links(self):
        page = (ROOT / "site-entry/index.html").read_text(encoding="utf-8")
        original = (ROOT / "theravada/tipitaka/site/index.html").read_text(encoding="utf-8")
        for name in ("index.html", "dhamma.html", "tipitaka.html", "theravada.html",
                     "four-noble-truths.html", "four-noble-truths.html#cessation", "eightfold-path.html"):
            target = "/" if name == "index.html" else "/theravada/tipitaka/site/" + name
            original = original.replace('href="' + name + '"', 'href="' + target + '"')
        footer = ('<p>This page is open source, Contribute here: '
                  '<a href="https://github.com/sasukenebe/freebuddhism">GitHub repository</a></p>\n')
        original = original.replace("</body>", footer + "</body>")
        self.assertEqual(page, original)
        self.assertEqual(page.count("This page is open source, Contribute here:"), 1)
        self.assertNotIn("http-equiv=\"refresh\"", page.casefold())
        self.assertNotIn("A free resource for exploring", page)

    def test_navigation_build_preserves_original_homepage_paragraphs(self):
        original = (ROOT / "site-entry/index.html").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(original, encoding="utf-8")
            _finish_page_navigation(root, {}, {}, [], set())
            result = (root / "index.html").read_text(encoding="utf-8")
        self.assertEqual(PageAudit(result).paragraphs, PageAudit(original).paragraphs[1:])
        self.assertIn("<h1>Home</h1>", result)
        self.assertIn("<title>Home</title>", result)

    def test_tipitaka_tree_counts_are_added_recursively_and_idempotently(self):
        page = (
            '<ul id="tipitaka-tree"><li><details><summary><a href="../sutta/anguttara-nikaya/index.html">'
            "Aṅguttara Nikāya</a></summary></details></li></ul>\n"
            "<p>The text index retains 1 source entries across 1 IDs.</p>"
        )
        updated = _update_tipitaka_tree_counts(page, {
            "../sutta/anguttara-nikaya/index.html": "2,034 indexed entries; 2,034 eligible editions",
        })
        self.assertIn("Aṅguttara Nikāya</a> — 2,034 indexed entries; 2,034 eligible editions</summary>", updated)
        self.assertEqual(_update_tipitaka_tree_counts(updated, {
            "../sutta/anguttara-nikaya/index.html": "2,034 indexed entries; 2,034 eligible editions",
        }), updated)

    def test_sutta_source_rows_keep_node_routes_and_audio_availability(self):
        page = (
            '<tr><td>AN 1.2</td><td><a href="../sutta/anguttara-nikaya/an01-02/index.html">'
            'AN 1.2 — Example title</a></td><td>1</td><td>yes</td></tr>'
        )
        row = _source_rows(page)[0]
        self.assertEqual(row["route"], "sutta/anguttara-nikaya/an01-02/index.html")
        self.assertEqual(row["title"], "AN 1.2 — Example title")
        self.assertEqual(row["audio"], "yes")

    def test_anguttara_index_uses_verified_bilingual_chapter_titles(self):
        menu = _load_anguttara_menu()
        self.assertEqual((len(menu["books"]), sum(len(book["chapters"]) for book in menu["books"])), (11, 52))
        self.assertEqual(_parse_an_range("AN 1.175–186"), (1, 175, 186))
        canonical_pages = {
            "sutta/anguttara-nikaya/an01-01/index.html": {
                "canonical_id": "AN 1.1", "collection": "anguttara-nikaya", "title": "AN 1.1"
            },
            "sutta/anguttara-nikaya/an01-02/index.html": {
                "canonical_id": "AN 1.2", "collection": "anguttara-nikaya", "title": "AN 1.2"
            },
        }
        counts = {"sutta/anguttara-nikaya/an01-01/index.html": 1, "sutta/anguttara-nikaya/an01-02/index.html": 2}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            allowed = {}
            self.assertEqual(_write_anguttara_index(root, canonical_pages, counts, allowed), 2)
            page = (root / "sutta/anguttara-nikaya/index.html").read_text(encoding="utf-8")
            self.assertIn("Ekakanipāta (The Book of the Ones)", page)
            self.assertIn("Cittapariyādānavagga (The Chapter on What Occupies the Mind)", page)
            self.assertIn("AN 1.1", page)
            self.assertIn("Eligible local editions", page)
            self.assertIn(Path("sutta/anguttara-nikaya/index.html"), allowed)

    def test_vinaya_ids_have_readable_labels_and_verified_khandhaka_hierarchy(self):
        chapters = _load_vinaya_khandhaka_menu()
        self.assertEqual(len(chapters), 22)
        self.assertEqual(sum(row["group"] == "mahavagga" for row in chapters.values()), 10)
        self.assertEqual(sum(row["group"] == "cullavagga" for row in chapters.values()), 12)
        self.assertEqual(chapters["pli-tv-kd1"]["pali_title"], "Mahākhandhaka")
        self.assertEqual(chapters["pli-tv-kd22"]["pali_title"], "Sattasatikakkhandhaka")
        self.assertEqual(_vinaya_source_group("pli-tv-kd1"), "khandhaka")
        self.assertEqual(
            _vinaya_reference("pli-tv-bu-vb-pc1"),
            ("Bhikkhu Pācittiya 1", "Confession Rules"),
        )
        self.assertEqual(
            _vinaya_reference("pli-tv-bi-vb-as1-7"),
            ("Bhikkhunī Adhikaraṇasamatha 1–7", "Settling Legal Issues"),
        )
        self.assertEqual(
            license_scope_for("metadata/anguttara-menu.json", {
                "metadata/anguttara-menu.json": {
                    "license_scope": "CC0-1.0 SuttaCentral reference metadata",
                    "rights_basis": "SuttaCentral reference metadata is released under CC0-1.0; these files contain names and navigation ranges, not translated passages.",
                }
            }),
            "CC0-1.0 SuttaCentral reference metadata",
        )

    def test_crawler_files_list_only_built_html_and_keep_root_direct(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text("<h1>Welcome</h1>", encoding="utf-8")
            (root / "theravada/collection").mkdir(parents=True)
            (root / "theravada/collection/index.html").write_text("<h1>Texts</h1>", encoding="utf-8")
            (root / "downloads").mkdir()
            (root / "downloads/file.zip").write_bytes(b"archive")
            robots, sitemap = _write_crawler_files(root)
            self.assertIn("Allow: /", robots.read_text(encoding="utf-8"))
            self.assertIn("Sitemap: https://freebuddhism.org/sitemap.xml", robots.read_text(encoding="utf-8"))
            xml = ElementTree.parse(sitemap).getroot()
            locations = [node.text for node in xml.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
            self.assertEqual(locations, ["https://freebuddhism.org/", "https://freebuddhism.org/theravada/collection/index.html"])
            self.assertFalse(any(location.endswith(".zip") for location in locations))

    def test_sutta_coverage_rewrite_accepts_legacy_and_current_pages(self):
        intro = (
            "<p>Source index: 10 entries across 9 IDs. This build includes 8 CC0 or "
            "verified-public-domain editions across 7 IDs. A zero means no edition "
            "cleared for local redistribution; it does not mean no translation exists.</p>"
        )
        pages = (
            "<h1>Sutta texts</h1><p>12 available texts for 10 suttas, grouped by collection.</p>",
            "<h1>Sutta texts</h1><p>Source index: 10 entries across 9 IDs. This build includes 8 CC0 or verified-public-domain editions across 7 IDs. A zero means no edition cleared for local redistribution; it does not mean no translation exists.</p>",
        )
        for page in pages:
            with self.subTest(page=page[:40]):
                updated = _replace_sutta_coverage_intro(page, intro)
                self.assertEqual(updated.count(intro), 1)
                self.assertEqual(_replace_sutta_coverage_intro(updated, intro), updated)

    def test_tipitaka_coverage_rewrite_accepts_legacy_and_current_pages(self):
        summary = (
            "<p>The text index retains 10 source entries across 9 IDs. This build includes "
            "8 CC0 or verified-public-domain Sutta editions across 7 IDs. The Vinaya source ledger lists "
            "3 files; 2 eligible files are hosted locally. No Abhidhamma book currently clears the reuse policy. "
            "Text availability and translation completeness are separate; unavailable entries remain in the navigation.</p>"
        )
        pages = (
            "<h1>Tipiṭaka</h1><p>The Sutta Piṭaka section contains 10 texts.</p>",
            "<h1>Tipiṭaka</h1><p>The text index retains 10 source entries across 9 IDs. This build includes 8 CC0 or verified-public-domain Sutta editions across 7 IDs. The Vinaya source ledger lists 3 files; 2 eligible files are hosted locally. No Abhidhamma book currently clears the reuse policy. Text availability and translation completeness are separate; unavailable entries remain in the navigation.</p>",
        )
        for page in pages:
            with self.subTest(page=page[:40]):
                updated = _replace_tipitaka_coverage_summary(page, summary)
                self.assertEqual(updated.count(summary), 1)
                self.assertEqual(_replace_tipitaka_coverage_summary(updated, summary), updated)

    def test_vimanavatthu_legacy_links_get_metadata_only_local_pages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "sutta/khuddaka-nikaya/vimanavatthu"
            collection.mkdir(parents=True)
            (collection / "index.html").write_text(
                '<li><a href="vv01-01/index.html">Vv 1.1 Story One</a></li>\n'
                '<li><a href="vv02-03/index.html">Vv 2.3 Story Three</a></li>\n',
                encoding="utf-8",
            )
            (collection / "vv01").mkdir()
            (collection / "vv02").mkdir()
            (collection / "vv01/index.html").write_text("chapter 1 status", encoding="utf-8")
            (collection / "vv02/index.html").write_text("chapter 2 status", encoding="utf-8")
            allowed = {}
            count = _write_vimanavatthu_story_pages(root, allowed)
            self.assertEqual(count, 2)
            page = collection / "vv01-01/index.html"
            html_page = page.read_text(encoding="utf-8")
            self.assertIn("Vv 1.1 — Story One", html_page)
            self.assertIn("Vv 1 edition availability", html_page)
            self.assertNotIn("story text", html_page.casefold())
            self.assertIn(Path("sutta/khuddaka-nikaya/vimanavatthu/vv01-01/index.html"), allowed)

    def test_text_rights_and_completeness_are_separate(self):
        manifest = json.loads((ROOT / "metadata/eligible-texts.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["count"], 7153)
        self.assertEqual(len(manifest["texts"]), 7153)
        self.assertEqual({row["license"] for row in manifest["texts"]}, {
            "CC0-1.0", "Public Domain (original English edition, published 1895–1907)",
            "Candana — free distribution, unaltered contents",
        })
        self.assertTrue(all(row["rights_status"] in {"CLEARED", "EXPLICIT_PERMISSION_VERIFIED"} for row in manifest["texts"]))
        self.assertTrue(all(row["completeness_status"] == "UNKNOWN" for row in manifest["texts"]))

    def test_exclusion_inventory_is_metadata_only_and_complete_at_baseline(self):
        inventory = json.loads((ROOT / "metadata/excluded-sources.json").read_text(encoding="utf-8"))
        validate_excluded_inventory(inventory)
        self.assertEqual(len(inventory["text_versions"]), 1268)
        for row in inventory["text_versions"]:
            for key in ("title", "translator", "source_url", "license", "exclusion_reason",
                        "rights_status", "completeness_status"):
                self.assertTrue(row.get(key), f"missing {key} for {row.get('record_id')}")
            self.assertNotIn("text", row)
            self.assertNotIn("body", row)

    def test_exclusion_inventory_rejects_unknown_nested_payload_fields(self):
        inventory = json.loads((ROOT / "metadata/excluded-sources.json").read_text(encoding="utf-8"))
        inventory["text_versions"][0]["rights_evidence"]["source_excerpt"] = "copied source text"
        with self.assertRaisesRegex(ValueError, "evidence is malformed"):
            validate_excluded_inventory(inventory)

    def test_exclusion_inventory_rejects_nested_ids_and_external_local_routes(self):
        inventory = json.loads((ROOT / "metadata/excluded-sources.json").read_text(encoding="utf-8"))
        inventory["text_versions"][0]["canonical_id"] = {"text": "not an ID"}
        with self.assertRaisesRegex(ValueError, "metadata is incomplete"):
            validate_excluded_inventory(inventory)
        inventory = json.loads((ROOT / "metadata/excluded-sources.json").read_text(encoding="utf-8"))
        inventory["text_versions"][0]["existing_site_routes"]["reader_html"] = "https://example.org/reader.html"
        with self.assertRaisesRegex(ValueError, "outside the local Tipiṭaka site"):
            validate_excluded_inventory(inventory)

    def test_exclusion_inventory_rejects_open_counts_long_urls_and_path_traversal(self):
        inventory = json.loads((ROOT / "metadata/excluded-sources.json").read_text(encoding="utf-8"))
        inventory["counts"]["other"] = {"text": 1}
        with self.assertRaisesRegex(ValueError, "counts have unknown fields"):
            validate_excluded_inventory(inventory)
        inventory = json.loads((ROOT / "metadata/excluded-sources.json").read_text(encoding="utf-8"))
        inventory["text_versions"][0]["existing_site_routes"]["upstream_source_page"] = "https://example.org/" + ("x" * 300)
        with self.assertRaisesRegex(ValueError, "too long"):
            validate_excluded_inventory(inventory)
        inventory = json.loads((ROOT / "metadata/excluded-sources.json").read_text(encoding="utf-8"))
        inventory["text_versions"][0]["existing_site_routes"]["reader_html"] = (
            "https://freebuddhism.org/theravada/tipitaka/../../outside.html"
        )
        with self.assertRaisesRegex(ValueError, "outside the local Tipiṭaka site"):
            validate_excluded_inventory(inventory)
        inventory = json.loads((ROOT / "metadata/excluded-sources.json").read_text(encoding="utf-8"))
        inventory["text_versions"][0]["existing_site_routes"]["reader_html"] = (
            "https://freebuddhism.org/theravada/tipitaka/%252e%252e/outside.html"
        )
        with self.assertRaisesRegex(ValueError, "outside the local Tipiṭaka site"):
            validate_excluded_inventory(inventory)

    def test_site_content_manifest_requires_explicit_reviewed_paths_and_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entry = root / "site-entry/index.html"
            site_page = root / "theravada/tipitaka/site/index.html"
            entry.parent.mkdir()
            site_page.parent.mkdir(parents=True)
            entry.write_text("<h1>Entry</h1>", encoding="utf-8")
            site_page.write_text("<h1>Library</h1>", encoding="utf-8")
            files = []
            for path in (entry, site_page):
                files.append({
                    "path": path.relative_to(root).as_posix(),
                    "sha256": sha256_file(path),
                    "license_scope": SITE_SCOPE,
                    "rights_basis": SITE_RIGHTS_BASIS,
                })
            manifest = root / "metadata/site-content.json"
            manifest.parent.mkdir()
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "scope": "Only owner-approved project-authored pages with CC0-1.0 rights are included.",
                "files": files,
            }), encoding="utf-8")
            self.assertEqual(len(validate_site_content_manifest(root)), 2)
            (root / "theravada/tipitaka/site/unreviewed.html").write_text("<p>New page</p>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unlisted"):
                validate_site_content_manifest(root)

    def test_repository_legacy_text_routes_must_be_notices_not_text_bodies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "sutta/item").mkdir(parents=True)
            impact = root / "impact.json"
            impact.write_text(json.dumps({"records": [{
                "rights_status": "RIGHTS_RESTRICTED", "source_group": "Example edition",
                "completeness_status": "UNKNOWN",
            }], "standalone_assets": []}), encoding="utf-8")
            route = root / "sutta/item/item.html"
            valid = (
                "<nav><a href='../index.html'>Collection</a></nav><h1>Item 1</h1>"
                "<p>This edition is not included in the local website build because rights are unclear.</p>"
                "<p>Example edition. Completeness: UNKNOWN.</p>"
                "<p>Rights clearance and translation completeness are assessed separately. "
                "An unavailable edition is not a claim that no translation exists.</p>"
            )
            route.write_text(valid, encoding="utf-8")
            self.assertEqual(validate_legacy_text_routes(root, impact), 1)
            route.write_text(valid.replace("no translation exists.</p>", "no translation exists. Restricted text.</p>"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "approved exclusion notice"):
                validate_legacy_text_routes(root, impact)
            route.write_text(valid + " Unwrapped source text.", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "active or embedded content"):
                validate_legacy_text_routes(root, impact)

    def test_navigation_index_rejects_long_text_even_if_notice_remains(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "sutta/item").mkdir(parents=True)
            impact = root / "impact.json"
            impact.write_text('{"records": [], "standalone_assets": []}', encoding="utf-8")
            (root / "sutta/item/index.html").write_text(
                "<h1>Item</h1><a href='item.html'>Read</a><p>" + ("x" * 501) + "</p>",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "excessive unlinked prose"):
                validate_legacy_text_routes(root, impact)

    def test_navigation_index_rejects_long_heading_and_split_prose(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "sutta/item").mkdir(parents=True)
            impact = root / "impact.json"
            impact.write_text('{"records": [], "standalone_assets": []}', encoding="utf-8")
            route = root / "sutta/item/index.html"
            route.write_text("<h1>" + ("x" * 301) + "</h1><a href='item.html'>Read</a>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "excessive unlinked prose"):
                validate_legacy_text_routes(root, impact)
            route.write_text(
                "<h1>Item</h1>" + "".join(
                    "<a href='item.html'>" + ("linked text " * 8) + "</a>" for _ in range(75)
                ), encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "excessive unlinked prose"):
                validate_legacy_text_routes(root, impact)
            route.write_text(
                "<h1>Item</h1><a href='item.html' title=" + ("x" * 301) + ">Read</a>",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "excessive unlinked prose"):
                validate_legacy_text_routes(root, impact)
            route.write_text(
                "<h1>Item</h1><a href='item.html' aria-description='" + ("x" * 301) + "'>Read</a>",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "excessive unlinked prose"):
                validate_legacy_text_routes(root, impact)
            route.write_text(
                "<h1>Item</h1><a href='item.html'>Read</a><table><tr>"
                + "".join("<td>" + ("fragment " * 35) + "</td>" for _ in range(8))
                + "</tr></table>", encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "excessive unlinked prose"):
                validate_legacy_text_routes(root, impact)
            route.write_text(
                "<h1>Item</h1><a href='item.html'>Read</a>" + "".join(
                    "<p>" + ("short prose " * 20) + "</p>" for _ in range(9)
                ), encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "excessive unlinked prose"):
                validate_legacy_text_routes(root, impact)

    def test_public_source_scan_includes_nested_build_and_rejects_symlink_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nested = root / "docs/build"
            nested.mkdir(parents=True)
            (nested / "source.txt").write_text("must be scanned", encoding="utf-8")
            (root / "build").mkdir()
            (root / "build/generated.txt").write_text("ignored build output", encoding="utf-8")
            self.assertEqual(actual_files(root), {"docs/build/source.txt"})
            linked = root / "linked"
            linked.symlink_to(nested, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "Symlink directory"):
                actual_files(root)

    def test_unavailable_object_embed_is_removed_from_site_output(self):
        page = '<details><summary>Scan</summary><object data="book.pdf"><p>Fallback</p></object></details>'
        cleaned = _strip_unavailable_embeds(page, Path("sutta/book/index.html"), {})
        self.assertNotIn("<object", cleaned)
        self.assertIn("Embedded document omitted", cleaned)
        kept = _strip_unavailable_embeds(
            page, Path("sutta/book/index.html"), {Path("sutta/book/book.pdf"): {}}
        )
        self.assertIn("<object", kept)

    def test_unknown_public_file_has_no_default_license(self):
        for path in ("unexpected.bin", "tools/new.py", "metadata/new.json"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "No exact approved rights entry"):
                license_scope_for(path, {})
        approved = {
            "tools/reviewed.py": {
                "license_scope": "0BSD",
                "rights_basis": RIGHTS_BASIS_BY_SCOPE["0BSD"],
            }
        }
        self.assertEqual(license_scope_for("tools/reviewed.py", approved), "0BSD")

    def test_allowlist_refresh_never_adds_files_and_requires_review_for_hash_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            known = root / "tools/reviewed.py"
            known.parent.mkdir()
            known.write_text("original code", encoding="utf-8")
            entries = [{
                "path": "tools/reviewed.py",
                "sha256": sha256_file(known),
                "license_scope": "0BSD",
            }]
            known.write_text("changed code", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not explicitly reviewed"):
                refresh_allowlist_entries({"tools/reviewed.py"}, entries, set(), root)
            refreshed = refresh_allowlist_entries(
                {"tools/reviewed.py"}, entries, {"tools/reviewed.py"}, root
            )
            self.assertEqual(refreshed[0]["rights_basis"], RIGHTS_BASIS_BY_SCOPE["0BSD"])
            self.assertEqual(refreshed[0]["sha256"], sha256_file(known))

            new_path = root / "tools/new.py"
            new_path.write_text("unreviewed content", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Refusing to add or remove files"):
                refresh_allowlist_entries(
                    {"tools/reviewed.py", "tools/new.py"}, refreshed,
                    {"tools/new.py"}, root,
                )

    def test_build_output_refuses_symlinked_destination_before_following_it(self):
        build_root = ROOT / "build"
        build_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build_root) as temporary:
            root = Path(temporary)
            protected = root / "protected"
            protected.mkdir()
            link = root / "site-root"
            link.symlink_to(protected, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "symlink in the site output path"):
                safe_output_destination(link)
            self.assertTrue(protected.is_dir())

    def test_generated_webroot_permissions_allow_unprivileged_static_server(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "site-root"
            nested = root / "theravada"
            nested.mkdir(parents=True)
            page = nested / "index.html"
            page.write_text("<h1>Local site</h1>", encoding="utf-8")
            root.chmod(0o700)
            nested.chmod(0o700)
            page.chmod(0o600)

            normalize_webroot_permissions(root)

            self.assertEqual(root.stat().st_mode & 0o777, 0o755)
            self.assertEqual(nested.stat().st_mode & 0o777, 0o755)
            self.assertEqual(page.stat().st_mode & 0o777, 0o644)

    def test_local_link_check_resolves_within_bundle_without_path_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs").mkdir()
            (root / "index.html").write_text(
                "<a href='/'>Home</a><a href='./'>Home again</a><a href='docs/'>Docs</a><a href='../escape.html'>Escape</a><a href='missing.txt'>Missing</a>",
                encoding="utf-8",
            )
            (root / "docs/index.html").write_text("<h1>Docs</h1>", encoding="utf-8")
            errors = local_link_errors(root)
            self.assertEqual(len(errors), 2)
            self.assertTrue(any("escapes webroot" in error for error in errors))
            self.assertTrue(any("missing local target" in error for error in errors))

    def test_cowell_provenance_uses_hashes_without_redistributing_source_wrappers(self):
        manifest = json.loads((ROOT / "metadata/source-manifests/cowell-jataka.json").read_text(encoding="utf-8"))
        self.assertNotIn("snapshot_dir", manifest)
        self.assertTrue(all("snapshot" not in row for row in manifest["texts"]))
        self.assertTrue(all("index_snapshot" not in row for row in manifest["volume_indexes"]))
        self.assertFalse((ROOT / "metadata/source-snapshots/cowell-jataka").exists())

    def test_reader_preserves_paragraphs_and_reflows_long_lines(self):
        config = {
            "canonical_id": "TEST 1", "title": "Synthetic layout test", "translator": "Test fixture",
            "source_url": "https://example.invalid/source", "source_repository": "",
            "source_revision": "", "license": "CC0-1.0", "license_url": "",
            "collection_href": "index.html", "collection_label": "Test collection",
            "local_text_href": "test.txt", "html_download_href": "test.html",
            "pdf_download_href": "test.pdf", "translations": [{
                "label": "Test fixture", "href": "test.html", "current": True
            }],
        }
        body = "paragraph one\n\n" + ("unbrokentoken" * 20) + "\nparagraph three"
        page = render_html(config, body)
        parser = ReaderParser()
        parser.feed(page)
        self.assertEqual("".join(parser.source_parts), body)
        self.assertIn('name="viewport"', page)
        self.assertNotIn("width: min(100%, 76ch)", page)
        self.assertNotIn("font-family:", page)
        self.assertIn("white-space: pre-wrap", page)
        self.assertIn("font: inherit", page)
        self.assertNotIn("overflow-wrap: anywhere", page)

    def test_reader_has_full_breadcrumb_and_deduplicates_reference_title(self):
        self.assertEqual(display_text_title("AN 1.10", "AN 1.10"), "AN 1.10")
        self.assertEqual(display_text_title("AN 1.10", "AN 1.10 — Title"), "AN 1.10 — Title")
        self.assertEqual(
            display_text_title("AN 5.140", "AN 5.140 — Sota Sutta (Attentive Listener) AN 5.140"),
            "AN 5.140 — Sota Sutta (Attentive Listener)",
        )
        self.assertEqual(
            _display_canonical_title("AN 5.140", "AN 5.140 — Sota Sutta (Attentive Listener) AN 5.140"),
            "AN 5.140 — Sota Sutta (Attentive Listener)",
        )
        config = {
            "canonical_id": "AN 1.11", "title": "AN 1.11", "translator": "Bhikkhu Sujato",
            "source_url": "https://example.invalid/source", "source_repository": "",
            "source_revision": "", "license": "CC0-1.0", "license_url": "",
            "collection_href": "../index.html", "collection_label": "Anguttara Nikaya",
            "breadcrumbs": [
                {"label": "Tipitaka", "href": "../../../site/tipitaka.html"},
                {"label": "Sutta Pitaka", "href": "../../../site/sutta.html"},
                {"label": "Anguttara Nikaya", "href": "../index.html"},
            ],
            "local_text_href": "text.txt", "html_download_href": "text.html", "pdf_download_href": "text.pdf",
            "translations": [
                {"label": "Bhikkhu Sujato", "href": "text.html", "current": True},
                {"label": "Alternate edition", "href": "alternate.html", "current": False},
            ],
        }
        page = render_html(config, "Text")
        self.assertIn("Tipitaka</a> →", page)
        self.assertIn("Sutta Pitaka</a> →", page)
        self.assertIn("Anguttara Nikaya</a> →", page)
        self.assertEqual(page.count("<h1>AN 1.11</h1>"), 1)
        self.assertNotIn("AN 1.11 — AN 1.11", page)
        self.assertIn('<span aria-current="page">Bhikkhu Sujato</span>', page)
        self.assertNotIn('href="text.html" aria-current', page)
        self.assertIn('href="alternate.html">Alternate edition</a>', page)
        config["title"] = "AN 1.11 — A Title AN 1.11"
        page = render_html(config, "Text")
        self.assertIn("<h1>AN 1.11 — A Title</h1>", page)

    def test_collection_navigation_has_tree_flat_list_read_and_text_page_links(self):
        self.assertEqual(_text_group_label("AN 1.11"), "AN 1")
        self.assertEqual(_text_group_label("Dhp 31"), "")
        self.assertEqual(_text_group_label("MN 26"), "")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "theravada" / "tipitaka"
            index = root / "sutta/majjhima-nikaya/index.html"
            index.parent.mkdir(parents=True)
            index.write_text(
                '<!doctype html><html><body><h1>Majjhima Nikaya</h1>'
                '<p><a href="../../downloads/majjhima-nikaya.zip">Download this collection</a></p>'
                '<table><tr><th>ID</th></tr><tr><td>MN 1</td></tr></table></body></html>',
                encoding="utf-8",
            )
            pages = {
                "sutta/majjhima-nikaya/mn01/index.html": {
                    "canonical_id": "MN 1", "collection": "majjhima-nikaya", "title": "MN 1",
                    "eligible": [{"version_label": "Bhikkhu Sujato translation"}],
                },
                "sutta/majjhima-nikaya/mn02/index.html": {
                    "canonical_id": "MN 2", "collection": "majjhima-nikaya", "title": "MN 2",
                    "eligible": [],
                },
            }
            for number in (25, 26, 152):
                pages[f"sutta/majjhima-nikaya/mn{number:02d}/index.html"] = {
                    "canonical_id": f"MN {number}", "collection": "majjhima-nikaya", "title": f"MN {number}",
                    "eligible": [{"version_label": "Bhikkhu Sujato translation"}],
                }
            self.assertEqual(_write_collection_browsers(root, pages, {"majjhima-nikaya": []}), 1)
            result = index.read_text(encoding="utf-8")
            self.assertIn("Browse this collection", result)
            self.assertIn('data-mode="tree"', result)
            self.assertIn('data-mode="list"', result)
            self.assertIn("Flat list", result)
            self.assertIn('data-browse-font="decrease">Font Size -</button>', result)
            self.assertIn('data-browse-font="increase">Font Size +</button>', result)
            self.assertIn("freebuddhism-browse-font-scale", result)
            self.assertIn('aria-label="Reset browsing font size">Reset</button>', result)
            self.assertIn("localStorage.removeItem", result)
            self.assertIn("min-height:max(2.75em,44px)", result)
            self.assertIn("details>details{margin-inline-start:1.25em}", result)
            self.assertIn("4 with local translations; 4 local editions", result)
            self.assertIn("Availability does not establish translation completeness", result)
            self.assertNotIn(" — expand", result)
            self.assertIn('>All Text on One Page</a>', result)
            self.assertNotIn("Open text page:", result)
            self.assertIn('href="mn01/index.html">MN 1</a>', result)
            self.assertNotIn('href="mn02/index.html"', result)
            self.assertNotIn("MN 1–25", result)
            self.assertNotIn("MN 151–175", result)
            self.assertLess(result.index('>MN 25</a>'), result.index('>MN 26</a>'))
            self.assertLess(result.index('aria-label="Breadcrumb"'), result.index('<h1>'))
            self.assertIn("no eligible local edition", result)
            self.assertIn("Full existing index and collection notes", result)
            self.assertIn('aria-label="Breadcrumb"', result)
            text_breadcrumb = _sutta_breadcrumb_markup(
                root, root / "sutta/majjhima-nikaya/mn01/index.html", "majjhima-nikaya", "MN 1"
            )
            self.assertIn("Sutta Piṭaka</a>", text_breadcrumb)
            self.assertIn("Majjhima Nikāya</a>", text_breadcrumb)
            self.assertIn('<span aria-current="page">MN 1</span>', text_breadcrumb)

    def test_browsing_controls_and_descriptions_apply_recursively(self):
        nodes = navigation_nodes()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for node in nodes.values():
                index = root / node["route"]
                index.parent.mkdir(parents=True, exist_ok=True)
                index.write_text("<html><body><h1>Existing title</h1></body></html>", encoding="utf-8")
            pages = {
                "sutta/anguttara-nikaya/an01-01/index.html": {
                    "canonical_id": "AN 1.1", "title": "AN 1.1",
                    "collection": "anguttara-nikaya", "eligible": [],
                },
            }
            for key in nodes:
                with self.subTest(collection=key):
                    markup = _collection_browse_markup(root, key, pages, set(nodes), nodes)
                    self.assertIn('data-browse-font="increase"', markup)
                    self.assertIn('data-browse-font="decrease"', markup)
                    self.assertIn('data-browse-font="reset"', markup)
                    self.assertNotIn(" — expand", markup)
                    self.assertNotIn("font-family:", markup)
                    self.assertNotIn("max-width:", markup)
                    result = (root / nodes[key]["route"]).read_text(encoding="utf-8")
                    self.assertIn('class="collection-description"', result)
                    self.assertTrue(nodes[key]["description"])
                    self.assertNotIn(" (", nodes[key]["tree_title"])
            markup = _text_node_browser(root, "sutta/anguttara-nikaya/an01-01/index.html", {
                "collection": "anguttara-nikaya", "eligible": [],
            })
            self.assertIn('data-browse-font="increase"', markup)
            self.assertIn('data-browse-font="decrease"', markup)

    def test_tipitaka_tree_is_the_complete_existing_hierarchy_without_wrapper(self):
        nodes = navigation_nodes()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            page = root / nodes["tipitaka"]["route"]
            page.parent.mkdir(parents=True)
            hierarchy = (
                '<h2>Pāli Tipiṭaka</h2><p>Follow a linked name to read its texts.</p>'
                '<ul id="tipitaka-tree"><li>Tipiṭaka<ul><li>Vinaya Piṭaka'
                '<ul><li>Sutta Vibhaṅga</li></ul></li><li>Sutta Piṭaka</li>'
                '<li>Abhidhamma Piṭaka</li></ul></li></ul>'
                '<p>The text index retains 6692 source entries. Availability is separate.</p>'
            )
            page.write_text(
                '<html><body><h1>Buddhist Texts</h1>' + hierarchy
                + '<h2>Available here</h2><p><a href="sutta-texts.html">Texts</a> | '
                '<a href="downloads.html">Downloads</a></p></body></html>', encoding="utf-8",
            )
            _collection_browse_markup(root, "tipitaka", {}, set(nodes), nodes)
            result = page.read_text(encoding="utf-8")
            tree_pane = result.split('<div data-view="tree"', 1)[1].split('</div>', 1)[0]
            self.assertIn(hierarchy, tree_pane)
            self.assertEqual(result.count('id="tipitaka-tree"'), 1)
            self.assertNotIn("Full existing index and collection notes", result)
            self.assertNotIn("Available here", result)
            self.assertNotIn("Expand a group to browse", result)
            self.assertNotIn("Open Vinaya", result)
            self.assertIn('data-mode="list"', result)
            self.assertIn('data-browse-font="reset"', result)
            self.assertNotIn("font-family:", result)
            self.assertNotIn("max-width:", result)

    def test_collection_names_and_counts_are_not_completeness_claims(self):
        nodes = navigation_nodes()
        self.assertIn("Stories of Departed Spirits", nodes["khuddaka-nikaya/petavatthu"]["description"])
        self.assertIn("Accounts of Past Deeds", nodes["khuddaka-nikaya/apadana"]["description"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            index = root / nodes["majjhima-nikaya"]["route"]
            index.parent.mkdir(parents=True)
            index.write_text("<html><body><h1>Majjhima</h1></body></html>", encoding="utf-8")
            pages = {
                "one/index.html": {"collection": "majjhima-nikaya", "canonical_id": "MN 1",
                                   "title": "MN 1", "eligible": [{}, {}, {}]},
                "two/index.html": {"collection": "majjhima-nikaya", "canonical_id": "MN 2",
                                   "title": "MN 2", "eligible": []},
            }
            markup = _collection_browse_markup(root, "majjhima-nikaya", pages, set(nodes), nodes)
            self.assertIn("2 indexed text entries; 1 with local translations; 3 local editions", markup)
            self.assertIn("Availability does not establish translation completeness", markup)
            self.assertNotIn("zoom:", markup)
            self.assertNotIn("preventDefault", markup)

    def test_continuous_reader_preferences_keep_global_default_and_hide_overrides(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "theravada" / "tipitaka"
            allowed = {}
            self.assertEqual(_write_continuous_reader(root, {}, allowed), 0)
            page = (root / "site/read.html").read_text(encoding="utf-8")
            self.assertIn('id="customize-editions" aria-expanded="false"', page)
            self.assertIn("freebuddhism-reading-default\"", page)
            self.assertIn("freebuddhism-reading-overrides\"", page)
            self.assertIn('id="reader-view-switcher"', page)
            self.assertIn('aria-label="Collection views"', page)
            self.assertIn("Fallback translation:", page)
            self.assertIn("If the chosen translation is missing", page)
            self.assertNotIn('id="omissions-note"', page)
            self.assertNotIn("This continuous view contains", page)
            self.assertIn("Font Size +", page)
            self.assertIn("Font Size -", page)
            self.assertIn('id="text-reset"', page)
            self.assertIn('aria-label="Reset reading font size">Reset</button>', page)
            self.assertNotIn("maximum-scale", page)
            self.assertNotIn("user-scalable=no", page)
            self.assertIn('<summary><h2>Contents</h2></summary>', page)
            self.assertIn("font:inherit", page)
            self.assertNotIn("Loading translations", page)
            self.assertNotIn("font-family:", page)

    def test_continuous_reader_manifest_contains_only_eligible_editions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root = root / "reader-output"
            page_root = root / "web" / "theravada" / "tipitaka"
            record = {
                "version": "sujato", "version_label": "Bhikkhu Sujato translation",
                "translator": "Bhikkhu Sujato", "output_root": output_root,
                "html_path": output_root / "theravada/tipitaka/sutta/majjhima-nikaya/mn01/mn01-sujato.html",
            }
            pages = {
                "sutta/majjhima-nikaya/mn01/index.html": {
                    "canonical_id": "MN 1", "collection": "majjhima-nikaya", "title": "MN 1",
                    "eligible": [record],
                },
                "sutta/majjhima-nikaya/mn02/index.html": {
                    "canonical_id": "MN 2", "collection": "majjhima-nikaya", "title": "MN 2",
                    "eligible": [],
                },
            }
            allowed = {}
            self.assertEqual(_write_continuous_reader(page_root, pages, allowed), 1)
            manifest = (page_root / "site/reading-index.json").read_text(encoding="utf-8")
            reader = (page_root / "site/read.html").read_text(encoding="utf-8")
            self.assertIn('"canonical_id":"MN 1"', manifest)
            self.assertNotIn('"canonical_id":"MN 2"', manifest)
            self.assertIn("freebuddhism-reading-overrides", reader)
            self.assertIn('collectionIndexUrl+"?view=list"', reader)
            self.assertIn('currentView.textContent="All Text on One Page"', reader)
            self.assertNotIn('heading.append(anchor)', reader)
            self.assertIn('nodeLink.href=item.url', reader)
            self.assertIn('heading.append(nodeLink)', reader)
            self.assertIn("Fallback translation:", reader)
            self.assertIn('"title":"MN 1"', manifest)
            self.assertIn(Path("site/reading-index.json"), allowed)
            self.assertIn(Path("site/read.html"), allowed)

    def test_navigation_is_shared_by_vinaya_and_sutta_and_preserves_reader_body(self):
        nodes = navigation_nodes()
        path = collection_path("vinaya/bhikkhu-vibhanga", nodes)
        self.assertEqual([node["id"] for node in path], [
            "tipitaka", "vinaya", "vinaya/sutta-vibhanga", "vinaya/bhikkhu-vibhanga"
        ])
        with tempfile.TemporaryDirectory() as temporary:
            webroot = Path(temporary)
            tipitaka = webroot / "theravada/tipitaka"
            route = "vinaya/texts/index/pli-tv-bu-vb-pc1/index.html"
            reader_route = "vinaya/texts/pages/pli-tv-bu-vb-pc1/index.html"
            reader = tipitaka / reader_route
            reader.parent.mkdir(parents=True)
            body = "An unchanged passage.\n\nAnother paragraph."
            reader.write_text(
                '<html><head><title>Old</title></head><body><nav>Old global menu</nav>'
                '<p><a href="../../../index.html">Vinaya</a></p><h1>Old heading</h1>'
                '<nav aria-label="Breadcrumb">Old breadcrumb</nav>'
                '<a href="/theravada/tipitaka/vinaya/texts/index/unavailable/index.html">Missing text</a>'
                '<pre class="source-text">' + body + '</pre></body></html>', encoding="utf-8")
            record = {"html_path": webroot / "readers/theravada/tipitaka" / reader_route,
                      "output_root": webroot / "readers", "version": "brahmali",
                      "version_label": "Bhikkhu Brahmali translation", "translator": "Bhikkhu Brahmali"}
            pages = {route: {"canonical_id": "pli-tv-bu-vb-pc1", "title": "A named rule",
                             "display_title": "Bhikkhu Pācittiya 1 — A named rule",
                             "collection": "vinaya/bhikkhu-vibhanga", "eligible": [record]}}
            _finish_page_navigation(webroot, pages, nodes, [], {Path("vinaya/texts/index/unavailable/index.html")})
            result = reader.read_text(encoding="utf-8")
            parser = ReaderParser()
            parser.feed(result)
            self.assertEqual("".join(parser.source_parts), body)
            self.assertEqual(result.count('aria-label="Site"'), 1)
            self.assertEqual(result.count('aria-label="Breadcrumb"'), 1)
            self.assertNotIn("Old global menu", result)
            self.assertNotIn("Old breadcrumb", result)
            self.assertNotIn('href="../../../index.html"', result)
            self.assertNotIn('href="/theravada/tipitaka/vinaya/texts/index/unavailable/index.html"', result)
            self.assertIn('<span class="unavailable">Missing text</span>', result)
            self.assertLess(result.index('aria-label="Site"'), result.index('aria-label="Breadcrumb"'))
            self.assertLess(result.index('aria-label="Breadcrumb"'), result.index('<h1>'))
            self.assertIn("Sutta Vibhaṅga (Analysis of the Rules)</a>", result)
            allowed = {}
            _write_continuous_reader(tipitaka, pages, allowed, nodes)
            manifest = json.loads((tipitaka / "site/reading-index.json").read_text(encoding="utf-8"))
            text = manifest["texts"][0]
            self.assertEqual(text["title"], "Bhikkhu Pācittiya 1 — A named rule")
            self.assertEqual(text["ancestors"], [node["id"] for node in path])
            self.assertNotIn("sutta", text["ancestors"])

    def test_parallel_reader_pdf_rendering_is_safe(self):
        config = {
            "canonical_id": "TEST 1", "title": "Concurrent rendering", "translator": "Test fixture",
            "source_url": "https://example.invalid/source", "source_revision": "", "license": "CC0-1.0",
            "license_url": "", "metadata_notes": [],
        }
        bodies = [f"Saññā, Mahākhandhaka, pācittiya — reader {index}.\n" * 12 for index in range(8)]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def render(index, body):
                pdf = root / f"reader-{index}.pdf"
                render_pdf(config, body, pdf)
                verify_pdf_body(pdf, body)

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda item: render(*item), enumerate(bodies)))


if __name__ == "__main__":
    unittest.main()
