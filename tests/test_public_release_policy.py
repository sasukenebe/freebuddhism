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
from build_deploy_site import (  # noqa: E402
    local_link_errors,
    safe_output_destination,
    _replace_sutta_coverage_intro,
    _replace_tipitaka_coverage_summary,
    _strip_unavailable_embeds,
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


class PublicReleasePolicyTests(unittest.TestCase):
    def test_root_welcome_page_is_direct_and_general(self):
        page = (ROOT / "site-entry/index.html").read_text(encoding="utf-8")
        self.assertNotIn("http-equiv=\"refresh\"", page.casefold())
        self.assertIn("A free resource for exploring Theravāda Buddhism", page)
        self.assertIn("Learn the Dhamma", page)
        self.assertIn("Read Buddhist texts", page)
        self.assertIn("/theravada/tipitaka/site/tipitaka.html", page)

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
        self.assertEqual(manifest["count"], 6352)
        self.assertEqual(len(manifest["texts"]), 6352)
        self.assertEqual({row["license"] for row in manifest["texts"]}, {
            "CC0-1.0", "Public Domain (original English edition, published 1895–1907)"
        })
        self.assertTrue(all(row["rights_status"] == "CLEARED" for row in manifest["texts"]))
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

    def test_local_link_check_resolves_within_bundle_without_path_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs").mkdir()
            (root / "index.html").write_text(
                "<a href='docs/'>Docs</a><a href='../escape.html'>Escape</a><a href='missing.txt'>Missing</a>",
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
        self.assertIn("width: min(100%, 76ch)", page)
        self.assertIn("@media print { body { width: auto; max-width: none; }", page)
        self.assertIn("white-space: pre-wrap", page)
        self.assertIn("overflow-wrap: anywhere", page)
        self.assertIn("@media (max-width: 32rem)", page)

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
