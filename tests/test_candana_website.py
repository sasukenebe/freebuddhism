# SPDX-License-Identifier: 0BSD
"""Website-only editions retain exact source content without public Git payloads."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
import candana_website as website
from distribution_policy import distribution, WEBSITE_LICENSE, WEBSITE_DISTRIBUTION
from archive_rights import edition_rights, write_release_metadata
from build_deploy_site import _zip_write
from build_eligible_readers import parse_args


class CandanaWebsiteTests(unittest.TestCase):
    def fixture(self, root):
        pdf = root / "supplied.pdf"
        pdf.write_bytes(b"%PDF-1.4 original synthetic test input, not a translated work")
        header = "AN 4.1\nSynthetic title\nTranslated by Bhikkhu Candana\nCopyright synthetic\n\n"
        body = "Section One:\n\nFirst synthetic source paragraph.\n\nSecond synthetic source paragraph.\n\nSadhu Sadhu Sadhu\n"
        raw = header + body + "\f"
        canonical = "AN 4.1 - Synthetic\n\nFirst synthetic source paragraph.\nSecond synthetic source paragraph.\n"
        (root / "reference.txt").write_text(canonical)
        def anchors(text, phrases):
            compact = " ".join(text.split())
            return [{"start": compact.index(p), "end": compact.index(p) + len(p),
                     "sha256": website.sha(p.encode())} for p in phrases]
        phrases = ["First synthetic source paragraph.", "Second synthetic source paragraph."]
        row = {"canonical_id": "AN 4.1", "collection": "anguttara-nikaya", "title": "Synthetic title",
               "translator": "Bhikkhu Candana", "version": "candana", "source_url": "https://www.mindreleased.com/s/test.pdf",
               "source_sha256": website.sha(pdf.read_bytes()), "copyright": "Copyright synthetic", "pdf_pages": 1,
               "raw_text_sha256": website.sha(raw.encode()), "body_sha256": website.sha(body.encode()),
               "text_sha256": "", "partition": {"header_characters": len(header),
                    "header_sha256": website.sha(header.encode()), "raw_body_sha256": website.sha((body + "\f").encode()),
                    "page_break_paragraphs": []},
               "identity_review": {"status": "VERIFIED", "review_kind": "CONTENT_IDENTITY_REVIEW",
                    "review_id": "synthetic-content-review", "review_basis": "Synthetic content comparison, no real review claimed",
                    "canonical_text_path": "reference.txt", "canonical_text_sha256": website.sha(canonical.encode()),
                    "source_anchors": anchors(raw, phrases), "canonical_anchors": anchors(canonical, phrases)},
               "processing_review_entry_id": "synthetic-entry", "completeness_status": "UNKNOWN"}
        row["text_sha256"] = website.sha(website.attributed_text(row, header, body).encode())
        manifest = {"schema_version": 1, "license": WEBSITE_LICENSE, "conditions": website.CONDITIONS,
                    "distribution": WEBSITE_DISTRIBUTION, "permission": {
                        "evidence": "OWNER_SUPPLIED_PERMISSION_AND_REPORTED_CONFIRMATION",
                        "website": "https://freebuddhism.org", "confirmation_reported": True}, "records": [row]}
        path = root / website.MANIFEST_PATH
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(manifest))
        return pdf, raw, row, manifest

    def extractor(self, raw, alternate=None):
        return patch.object(website.subprocess, "check_output", side_effect=lambda args, **kw:
                            (alternate if alternate is not None and args[0] == "mutool" else raw).encode())

    def test_default_build_stays_offline_and_opt_in_is_explicit(self):
        self.assertFalse(parse_args([]).include_website_editions)
        self.assertTrue(parse_args(["--include-website-editions"]).include_website_editions)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _pdf, _raw, row, _manifest = self.fixture(root)
            with self.assertRaisesRegex(ValueError, "input is missing"):
                website.checked_input(row, root)

    def test_website_only_readers_cannot_be_generated_into_public_source(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            for output in (root, root / "theravada/tipitaka"):
                with self.subTest(output=output), self.assertRaisesRegex(ValueError, "never into the public source"):
                    website.collect_records(output, root)
            output = root / "build/readers"
            output.mkdir(parents=True)
            (output / "theravada").symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "Symlinks"):
                website.collect_records(output, root)

    def test_manifest_requires_conditions_confirmed_scope_and_metadata_only(self):
        for fault in ("condition", "confirmation", "body", "canonical"):
            with self.subTest(fault=fault), TemporaryDirectory() as directory:
                root = Path(directory)
                _pdf, _raw, _row, value = self.fixture(root)
                if fault == "condition": value["conditions"] = value["conditions"][:2]
                if fault == "confirmation": value["permission"]["confirmation_reported"] = False
                if fault == "body": value["records"][0]["translated_content"] = "Must not be in Git"
                if fault == "canonical": (root / "reference.txt").write_text("AN 4.2 - Wrong reference\n")
                (root / website.MANIFEST_PATH).write_text(json.dumps(value))
                with self.assertRaises(ValueError): website.manifest(root)

    def test_staging_and_record_generation_preserve_body_notices_and_identity(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, raw, row, _value = self.fixture(root)
            with self.extractor(raw):
                self.assertEqual(website.stage(pdf, root), ["AN 4.1"])
                records = website.collect_records(root / "build/readers", root)
            record = records[0]
            self.assertTrue(website.verify_record(record, root))
            self.assertEqual(record["body"].split(), raw[row["partition"]["header_characters"]:].split())
            self.assertTrue(record["body"].endswith("Sadhu Sadhu Sadhu\n"))
            download = record["text_path"].read_text()
            for condition in website.CONDITIONS: self.assertIn(condition, download)
            self.assertIn("Original document heading: AN 4.1", download)
            self.assertFalse((root / website.public_text_path(row)).exists())
            website.verify_public_boundary(root)

    def test_wrong_pdf_and_mutated_cached_input_cannot_be_replaced_silently(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, raw, row, _value = self.fixture(root)
            with self.extractor(raw): website.stage(pdf, root)
            cached = root / website.CACHE_PATH / (row["source_sha256"] + ".pdf")
            cached.write_bytes(b"Changed original")
            with self.assertRaises(ValueError): website.stage(pdf, root)
            with self.assertRaises(ValueError): website.checked_input(row, root)
            pdf.write_bytes(b"Unreviewed source")
            with self.assertRaises(ValueError): website.stage(pdf, root)

    def test_word_boundaries_and_page_count_are_rechecked_not_just_character_inventory(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, raw, row, _value = self.fixture(root)
            with self.extractor(raw): website.stage(pdf, root)
            for alternate in (raw.replace("First synthetic", "Firstsynthetic"), raw + "Extra page\f"):
                with self.subTest(alternate=alternate), self.extractor(raw, alternate), self.assertRaises(ValueError):
                    website.checked_input(row, root)

    def test_source_boundaries_hyphen_wraps_and_outputs_are_exact(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _pdf, raw, row, _value = self.fixture(root)
            website.partition(raw, row)
            for changed in (raw.replace("Section One:", "Section Two:"), raw.replace("Sadhu Sadhu Sadhu", "Sadhu"),
                            raw.replace("synthetic source", "synthetic-\nsource")):
                with self.assertRaises(ValueError): website.partition(changed, row)
            for changed in (dict(row, body_sha256="0" * 64),
                            dict(row, partition=dict(row["partition"], page_break_paragraphs=[1]))):
                with self.assertRaises(ValueError): website.partition(raw, changed)

    def test_changed_record_fields_and_download_bytes_fail_permission_gate(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, raw, row, _value = self.fixture(root)
            with self.extractor(raw):
                website.stage(pdf, root)
                record = website.collect_records(root / "build/readers", root)[0]
            self.assertTrue(website.verify_record(record, root))
            for field, value in (("body", "Changed"), ("license_notice", "Reduced notice"),
                                 ("source_url", "https://example.org"), ("conditions", []),
                                 ("site_text_path", root / "wrong.txt"), ("source_sha256", "0" * 64)):
                with self.subTest(field=field): self.assertFalse(website.verify_record(dict(record, **{field: value}), root))
            record["text_path"].write_text("Changed saved download")
            self.assertFalse(website.verify_record(record, root))

    def test_archive_writer_refuses_even_an_incorrect_archive_true_flag(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            rights = {"license": WEBSITE_LICENSE, "distribution": WEBSITE_DISTRIBUTION}
            self.assertFalse(distribution(rights)["site_archives"])
            with self.assertRaises(ValueError): edition_rights(rights)
            payload = root / "website.txt"
            payload.write_text("Original synthetic words")
            allowed = {Path("website.txt"): {"source": payload, "archive": True, "rights": [rights]}}
            with self.assertRaises(ValueError): _zip_write(root / "bad.zip", list(allowed), root, allowed)
            changed = deepcopy(rights)
            changed["distribution"]["site_archives"] = True
            with self.assertRaises(ValueError): distribution(changed)

    def test_public_source_tree_cannot_contain_website_only_payloads(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _pdf, _raw, row, _value = self.fixture(root)
            target = root / website.public_text_path(row)
            target.parent.mkdir(parents=True)
            target.write_text("Accidental source publication")
            with self.assertRaises(ValueError): website.verify_public_boundary(root)

    def test_permission_page_is_generated_only_for_enabled_editions(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(website.write_permission_page(root, []), set())
            paths = website.write_permission_page(root, [{"website_record": True}])
            self.assertEqual(len(paths), 1)
            page = next(iter(paths)).read_text()
            for condition in website.CONDITIONS: self.assertIn(condition, page)
            self.assertNotIn("Ayya", page)
            self.assertIn("not CC0", page)

    def test_release_records_the_opt_in_inputs_without_private_paths(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _pdf, _raw, row, _value = self.fixture(root)
            with patch("archive_rights.subprocess.check_output", side_effect=["a" * 40 + "\n", ""]):
                write_release_metadata(root, root, [{"website_record": row}])
            release = json.loads((root / "release.json").read_text())
            self.assertEqual(release["website_only_editions"][0]["body_sha256"], row["body_sha256"])
            self.assertNotIn(str(root), json.dumps(release))


if __name__ == "__main__":
    unittest.main()
