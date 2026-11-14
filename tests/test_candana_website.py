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
import build_eligible_readers as readers


class CandanaWebsiteTests(unittest.TestCase):
    def test_incremental_output_preserves_active_download_and_removes_only_known_stale_text(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "build/readers"
            output.mkdir(parents=True)
            (output / ".eligible-readers-managed").write_text("Generated reader output")
            text = output / "theravada/tipitaka/translations/en/candana-website/an-4-1-candana.txt"
            text.parent.mkdir(parents=True)
            text.write_bytes(b"Synthetic reviewed download")
            with patch.object(readers, "ROOT", root):
                for _ in range(2):
                    readers.prepare_incremental_output(output, {text}, {text})
                    self.assertEqual(text.read_bytes(), b"Synthetic reviewed download")
                unknown = output / "unreviewed.txt"
                unknown.write_text("Unknown input; do not remove")
                with self.assertRaisesRegex(ValueError, "Unexpected file"):
                    readers.prepare_incremental_output(output, {text}, {text})
                self.assertTrue(unknown.is_file())
                unknown.unlink()
                readers.prepare_incremental_output(output, set(), {text})
                self.assertFalse(text.exists())

    def fixture(self, root, *, header_prefix="", source=None, page_break_paragraphs=None, page_break_joins=None):
        pdf = root / "supplied.pdf"
        pdf.write_bytes(b"%PDF-1.4 original synthetic test input, not a translated work")
        header = header_prefix + "AN 4.1\nSynthetic title\nTranslated by Bhikkhu Candana\nCopyright synthetic\n\n"
        body = "Section One:\n\nFirst synthetic source paragraph.\n\nSecond synthetic source paragraph.\n\nSadhu Sadhu Sadhu\n"
        source = body + "\f" if source is None else source
        raw = header + source
        pdf_pages = len(website.pages_of(raw))
        canonical = "AN 4.1 - Synthetic\n\nFirst synthetic source paragraph.\nSecond synthetic source paragraph.\n"
        (root / "reference.txt").write_text(canonical)
        def anchors(text, phrases):
            compact = " ".join(text.split())
            return [{"start": compact.index(p), "end": compact.index(p) + len(p),
                     "sha256": website.sha(p.encode())} for p in phrases]
        phrases = ["First synthetic source paragraph.", "Second synthetic source paragraph."]
        row = {"canonical_id": "AN 4.1", "collection": "anguttara-nikaya", "title": "Synthetic title",
               "translator": "Bhikkhu Candana", "version": "candana", "source_url": "https://www.mindreleased.com/s/test.pdf",
               "source_sha256": website.sha(pdf.read_bytes()), "copyright": "Copyright synthetic", "pdf_pages": pdf_pages,
               "raw_text_sha256": website.sha(raw.encode()), "body_sha256": website.sha(body.encode()),
               "text_sha256": "", "partition": {"header_characters": len(header),
                    "header_sha256": website.sha(header.encode()), "raw_body_sha256": website.sha(source.encode()),
                    "page_break_paragraphs": list(range(1, pdf_pages)) if page_break_paragraphs is None else page_break_paragraphs},
               "identity_review": {"status": "VERIFIED", "review_kind": "CONTENT_IDENTITY_REVIEW",
                    "review_id": "synthetic-content-review", "review_basis": "Synthetic content comparison, no real review claimed",
                    "canonical_text_path": "reference.txt", "canonical_text_sha256": website.sha(canonical.encode()),
                    "source_anchors": anchors(raw, phrases), "canonical_anchors": anchors(canonical, phrases)},
               "processing_review_entry_id": "synthetic-entry", "completeness_status": "UNKNOWN"}
        if page_break_joins is not None:
            row["partition"]["page_break_joins"] = page_break_joins
        row["text_sha256"] = website.sha(website.attributed_text(row, header, body).encode())
        manifest = {"schema_version": 1, "license": WEBSITE_LICENSE, "conditions": website.CONDITIONS,
                    "distribution": WEBSITE_DISTRIBUTION, "permission": {
                        "evidence": "OWNER_SUPPLIED_PERMISSION_AND_REPORTED_CONFIRMATION",
                        "website": "https://freebuddhism.org", "confirmation_reported": True}, "records": [row]}
        path = root / website.MANIFEST_PATH
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(manifest))
        return pdf, raw, row, manifest

    def prose_fixture(self, root):
        source = ("  \nSection One:\n\nFirst synthetic source\n\n \t\f\n \t\nparagraph.\n\n  \f"
                  "\n\n Second synthetic source\nparagraph.\n\nSadhu Sadhu Sadhu\n\f")
        return self.fixture(root, header_prefix="Synthetic collection\n", source=source,
                            page_break_paragraphs=[2], page_break_joins=[1])

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

    def test_legacy_fixture_bytes_hashes_and_notice_are_unchanged(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _pdf, raw, row, _value = self.fixture(root)
            header, body = website.partition(raw, row)
            changes = ("Presentation only: original heading retained in edition details; physical line wraps reflowed; "
                       "reviewed page breaks retained as paragraph breaks. No words, punctuation, notes or closings removed or repaired.")
            expected_body = ("Section One:\n\nFirst synthetic source paragraph.\n\n"
                             "Second synthetic source paragraph.\n\nSadhu Sadhu Sadhu\n")
            expected = (
                "AN 4.1 - Synthetic title\n"
                "Translated by Bhikkhu Candana\n"
                "Source: https://www.mindreleased.com/s/test.pdf\n"
                "License: Candana — permission for freebuddhism.org\n"
                "License URL: https://freebuddhism.org/theravada/tipitaka/site/candana-permission.html\n"
                "Copyright: Copyright synthetic\n"
                "License notice: No part of the content of the translations may be changed or altered; "
                "Available free of charge and never monetized in any way, now or in the future; "
                "The content of these translations must never be used for advertisements. "
                "Permission is for republication on freebuddhism.org; no general public-repository or third-party archive grant is claimed.\n"
                "Original document heading: AN 4.1 Synthetic title Translated by Bhikkhu Candana Copyright synthetic\n"
                "Distribution: Website-only edition; excluded from combined readers and site/source archives in this build.\n"
                "Changes: " + changes + "\n"
                "Completeness: UNKNOWN. Whole reviewed source translation, including section headings and closings; "
                "completeness and translation accuracy remain unverified.\n\n" + expected_body)
            self.assertEqual(body.encode(), expected_body.encode())
            self.assertEqual(website.attributed_text(row, header, body).encode(), expected.encode())
            self.assertEqual(row["body_sha256"], website.sha(expected_body.encode()))
            self.assertEqual(row["text_sha256"], website.sha(expected.encode()))
            self.assertEqual(website.changes_for(row), changes)
            self.assertEqual(website.CHANGES, changes)

    def test_explicit_prose_joins_continuation_and_preserves_true_paragraph(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _pdf, raw, row, _value = self.prose_fixture(root)
            source = raw[row["partition"]["header_characters"]:]
            body = website.reflow_body(source, row["partition"], row["pdf_pages"])
            self.assertEqual(body, "Section One:\n\nFirst synthetic source paragraph.\n\n"
                                   "Second synthetic source paragraph.\n\nSadhu Sadhu Sadhu\n")
            self.assertEqual(body.split(), source.split())
            header, checked_body = website.partition(raw, row)
            self.assertEqual(checked_body, body)
            self.assertTrue(header.startswith("Synthetic collection\nAN 4.1\n"))
            self.assertEqual(raw.split(), (header + "\n" + body).split())

    def test_empty_joins_selects_explicit_header_review_and_paragraph_layout(self):
        sources = (None, "Section One:\n\nFirst synthetic source paragraph.\n\n\f\n\n"
                         "Second synthetic source paragraph.\n\nSadhu Sadhu Sadhu\n\f")
        for source in sources:
            with self.subTest(source=source), TemporaryDirectory() as directory:
                root = Path(directory)
                _pdf, raw, row, _value = self.fixture(root, header_prefix="Synthetic collection\n",
                                                    source=source, page_break_joins=[])
                header, body = website.partition(raw, row)
                self.assertTrue(header.startswith("Synthetic collection\nAN 4.1\n"))
                self.assertIn("First synthetic source paragraph.\n\nSecond synthetic source paragraph.", body)
                self.assertIn("reviewed paragraph boundaries retained", website.changes_for(row))
                self.assertIn("continued prose reflowed without word changes", website.changes_for(row))
                legacy = deepcopy(row)
                del legacy["partition"]["page_break_joins"]
                with self.assertRaisesRegex(ValueError, "Source identity"):
                    website.partition(raw, legacy)

    def test_explicit_classifications_reject_duplicates_types_gaps_overlap_and_range(self):
        invalid = (
            ("duplicate joins", [2], [1, 1]), ("duplicate paragraphs", [2, 2], [1]),
            ("boolean join", [2], [True]), ("boolean paragraph", [True, 2], []),
            ("float join", [2], [1.0]), ("float paragraph", [1.0, 2], []),
            ("unsorted joins", [], [2, 1]), ("unsorted paragraphs", [2, 1], []),
            ("missing one", [2], []), ("missing all", [], []),
            ("overlap", [1, 2], [1]), ("zero index", [2], [0, 1]),
            ("negative index", [2], [-1, 1]), ("past final page", [2], [1, 3]),
            ("paragraph past final page", [2, 3], [1]),
            ("joins not list", [2], "1"), ("paragraphs not list", None, [1, 2]),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _pdf, raw, row, value = self.prose_fixture(root)
            source = raw[row["partition"]["header_characters"]:]
            for fault, paragraphs, joins in invalid:
                with self.subTest(fault=fault):
                    changed = deepcopy(row)
                    changed["partition"].update(page_break_paragraphs=paragraphs, page_break_joins=joins)
                    with self.assertRaises(ValueError):
                        website.reflow_body(source, changed["partition"], changed["pdf_pages"])
                    with self.assertRaises(ValueError):
                        website.partition(raw, changed)
                    value["records"] = [changed]
                    (root / website.MANIFEST_PATH).write_text(json.dumps(value))
                    with self.assertRaises(ValueError):
                        website.manifest(root)

    def test_partition_keys_cannot_be_missing_or_unknown(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _pdf, raw, row, value = self.prose_fixture(root)
            for fault in ("missing paragraphs", "unknown key"):
                with self.subTest(fault=fault):
                    changed = deepcopy(row)
                    if fault == "missing paragraphs":
                        del changed["partition"]["page_break_paragraphs"]
                    else:
                        changed["partition"]["unreviewed_layout"] = True
                    with self.assertRaises(ValueError):
                        website.partition(raw, changed)
                    value["records"] = [changed]
                    (root / website.MANIFEST_PATH).write_text(json.dumps(value))
                    with self.assertRaises(ValueError):
                        website.manifest(root)

    def test_explicit_reference_must_occur_once_as_standalone_line_inside_header(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _pdf, raw, row, _value = self.prose_fixture(root)
            offset = row["partition"]["header_characters"]
            header, source = raw[:offset], raw[offset:]
            variants = (
                (header.replace("AN 4.1\n", ""), "AN 4.1\n" + source),
                ("AN 4.1\n" + header, source),
                (header.replace("AN 4.1\n", "Reference: AN 4.1\n"), source),
                (header.replace("Copyright synthetic", "Copyright changed"), source),
                (header.replace("Translated by Bhikkhu Candana", "Translated by Unknown"), source),
            )
            for changed_header, changed_source in variants:
                with self.subTest(header=changed_header):
                    changed_raw = changed_header + changed_source
                    changed = deepcopy(row)
                    changed["raw_text_sha256"] = website.sha(changed_raw.encode())
                    changed["partition"].update(header_characters=len(changed_header),
                        header_sha256=website.sha(changed_header.encode()),
                        raw_body_sha256=website.sha(changed_source.encode()))
                    with self.assertRaisesRegex(ValueError, "Source identity"):
                        website.partition(changed_raw, changed)

    def test_explicit_staging_records_and_download_use_same_changes_notice(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, raw, row, value = self.prose_fixture(root)
            with self.extractor(raw):
                website.stage(pdf, root)
                record = website.collect_records(root / "build/readers", root)[0]
                self.assertTrue(website.verify_record(record, root))
                self.assertEqual(record["changes"], website.changes_for(row))
                self.assertIn("Changes: " + record["changes"] + "\n", record["text_path"].read_text())
                self.assertFalse(website.verify_record(dict(record, changes=website.CHANGES), root))
                value["records"][0]["identity_review"]["source_anchors"][0]["sha256"] = "0" * 64
                (root / website.MANIFEST_PATH).write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "Identity review content interval changed"):
                    website.collect_records(root / "build/readers", root)

    def test_explicit_layout_still_requires_pinned_words_and_extractor_agreement(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, raw, row, _value = self.prose_fixture(root)
            with self.extractor(raw):
                website.stage(pdf, root)
            for changed_raw in (raw.replace("First synthetic", "Changed synthetic"),
                                raw.replace("Sadhu Sadhu Sadhu", "Sadhu"),
                                raw.replace("paragraph.", "paragraph!")):
                with self.subTest(changed_raw=changed_raw):
                    with self.assertRaises(ValueError):
                        website.partition(changed_raw, row)
                    with self.extractor(changed_raw), self.assertRaises(ValueError):
                        website.checked_input(row, root)
                    changed = deepcopy(row)
                    changed["raw_text_sha256"] = website.sha(changed_raw.encode())
                    source = changed_raw[row["partition"]["header_characters"]:]
                    changed["partition"]["raw_body_sha256"] = website.sha(source.encode())
                    with self.assertRaisesRegex(ValueError, "differs from reviewed output"):
                        website.partition(changed_raw, changed)
            for alternate in (raw.replace("First synthetic", "Firstsynthetic"), raw + "Extra page\f"):
                with self.subTest(alternate=alternate), self.extractor(raw, alternate), self.assertRaises(ValueError):
                    website.checked_input(row, root)

    def test_explicit_reflow_rejects_hyphen_wraps_within_and_across_pages(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _pdf, raw, row, _value = self.prose_fixture(root)
            source = raw[row["partition"]["header_characters"]:]
            for changed in (source.replace("synthetic source", "synthetic-\nsource", 1),
                            source.replace("source\n\n \t\f", "source-\n\n \t\f", 1)):
                with self.subTest(source=changed), self.assertRaisesRegex(ValueError, "hyphen-wrap"):
                    website.reflow_body(changed, row["partition"], row["pdf_pages"])

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
                                 ("site_text_path", root / "wrong.txt"), ("source_sha256", "0" * 64),
                                 ("changes", "Unreviewed presentation changes")):
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
