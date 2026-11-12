# SPDX-License-Identifier: 0BSD
"""Mixed-license bundles retain exact per-file rights without a blanket license."""
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
from archive_rights import (
    TERMS, TERMS_NAME, MANIFEST_NAME, archive_label, edition_rights,
    verify_archive_rights, write_release_metadata,
)
from build_deploy_site import _zip_write, ARCHIVE_NOTICE


class ArchiveRightsTests(unittest.TestCase):
    def fixture(self, root):
        allowed = {}
        for name, license_name in (("free.txt", "CC0-1.0"), ("conditional.txt", "CC-BY-NC-4.0")):
            path = root / name
            path.write_text("License: " + license_name + "\n\nOriginal text.\n")
            rights = edition_rights({"canonical_id": "AN 1.1", "translator": "Example",
                                    "source_url": "https://example.org/" + name,
                                    "license_url": "https://creativecommons.org/licenses/by-nc/4.0/" if license_name != "CC0-1.0" else "https://creativecommons.org/publicdomain/zero/1.0/",
                                    "license": license_name, "license_notice": "Full original notice",
                                    "conditions": [] if license_name == "CC0-1.0" else ["noncommercial"]})
            allowed[Path(name)] = {"source": path, "archive": True, "rights": [rights]}
        return allowed

    def test_mixed_archive_manifest_covers_each_payload_and_retains_conditions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            allowed = self.fixture(root)
            target = root / "mixed.zip"
            _zip_write(target, list(allowed), root, allowed)
            with zipfile.ZipFile(target) as archive:
                report = json.loads(archive.read(MANIFEST_NAME))
                self.assertEqual(archive.read(TERMS_NAME).decode(), TERMS)
                self.assertEqual({row["path"] for row in report["files"]}, {"free.txt", "conditional.txt"})
                conditional = next(r for r in report["files"] if r["path"] == "conditional.txt")
                self.assertEqual(conditional["editions"][0]["license"], "CC-BY-NC-4.0")
                self.assertEqual(conditional["editions"][0]["conditions"], ["noncommercial"])
                verify_archive_rights(archive, report["files"])

    def test_changed_payload_license_and_missing_notice_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            allowed = self.fixture(root)
            target = root / "original.zip"
            _zip_write(target, list(allowed), root, allowed)
            with zipfile.ZipFile(target) as source:
                original = {name: source.read(name) for name in source.namelist()}
                expected = json.loads(original[MANIFEST_NAME])["files"]
            for fault in ("payload", "license", "notice", "extra"):
                parts = copy.deepcopy(original)
                if fault == "payload": parts["conditional.txt"] += b" Changed"
                if fault == "license":
                    manifest = json.loads(parts[MANIFEST_NAME])
                    manifest["files"][0]["editions"][0]["license"] = "CC0-1.0"
                    parts[MANIFEST_NAME] = json.dumps(manifest).encode()
                if fault == "notice": del parts[TERMS_NAME]
                if fault == "extra": parts["unlisted.txt"] = b"Unlisted text"
                broken = root / (fault + ".zip")
                with zipfile.ZipFile(broken, "w") as archive:
                    for name, data in parts.items(): archive.writestr(name, data)
                with self.subTest(fault=fault), zipfile.ZipFile(broken) as archive:
                    with self.assertRaises((ValueError, KeyError)):
                        verify_archive_rights(archive, expected)

    def test_missing_per_file_rights_blocks_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            allowed = self.fixture(root)
            allowed[Path("conditional.txt")].pop("rights")
            with self.assertRaisesRegex(ValueError, "lacks explicit edition terms"):
                _zip_write(root / "bad.zip", list(allowed), root, allowed)

    def test_incomplete_per_file_rights_cannot_be_the_validation_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for field in (None, "license_notice", "conditions", "license_url"):
                allowed = self.fixture(root)
                rights = allowed[Path("conditional.txt")]["rights"][0]
                if field is None: rights.clear()
                else: rights.pop(field)
                with self.subTest(field=field), self.assertRaises(ValueError):
                    _zip_write(root / "bad.zip", list(allowed), root, allowed)

    def test_candana_archive_rights_include_the_complete_pinned_book_notice(self):
        from archive_rights import CANDANA_LICENSE, CANDANA_CONDITIONS
        manifest = json.loads((ROOT / "metadata/source-manifests/candana.json").read_text())
        for book in manifest["books"]:
            record = {"canonical_id": "AN 1.1", "license": CANDANA_LICENSE,
                      "source_url": book["source_url"], "license_url": book["source_url"],
                      "source_revision": book["sha256"], "manifest": manifest,
                      "original_book_path": ROOT / book["local_path"]}
            rights = edition_rights(record)
            self.assertIn("You may copy, reprint, republish", rights["license_notice"])
            self.assertIn("Copyright © Bhikkhu Candana", rights["license_notice"])
            self.assertEqual(rights["conditions"], CANDANA_CONDITIONS)
            self.assertEqual(rights["permission_pages"], book["permission_pages"])
            self.assertEqual(edition_rights(rights), rights)
            rights.pop("license_notice")
            with self.assertRaises(ValueError): edition_rights(rights)

    def test_empty_archive_still_contains_only_its_unavailable_notice(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _zip_write(root / "empty.zip", [], root, {}, notice="No eligible texts.\n")
            with zipfile.ZipFile(root / "empty.zip") as archive:
                self.assertEqual(archive.namelist(), [ARCHIVE_NOTICE])

    def test_archive_labels_clear_stale_and_duplicate_unavailable_suffixes(self):
        stale = "Apadāna — no eligible files; notice only — no eligible files; notice only"
        self.assertEqual(archive_label(stale, True), "Apadāna")
        self.assertEqual(archive_label(stale, False), "Apadāna — no eligible files; notice only")
        self.assertEqual(archive_label(archive_label(stale, False), False), archive_label(stale, False))

    def test_release_identity_is_commit_scoped_without_paths_or_branch_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            files, revision = write_release_metadata(destination, ROOT, [{}, {}])
            result = json.loads((destination / "release.json").read_text())
            self.assertEqual(len(revision), 40)
            self.assertEqual(result["reader_versions"], 2)
            self.assertEqual(files, {destination / "release.json"})
            self.assertNotIn("branch", result)
            self.assertNotIn(str(ROOT), json.dumps(result))
