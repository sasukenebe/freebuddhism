# SPDX-License-Identifier: 0BSD
"""Source integrity, whole-verse coverage, exact rights and importer contract."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/buddhist_canon_pipeline"))
import prepare_abt_licensed as abt


def source(number=2, pali="1. Ānandaṁ vadati,<br>puna vadati.", english="He speaks.<br>He speaks.", extra=""):
    return (f'<html><head><title>unused title</title></head><body>'
            f'<p class="Heading3">Ja {number} Test<br>(Testajātaka)</p>'
            '<p class="summary">A story synopsis.</p>'
            f'<p class="verse3">{pali}</p><p class="translation">{english}</p>'
            f'<p>A whole word commentary.</p>{extra}'
            '<script src="../../includes/Footer.js"></script></body></html>').encode()


def reference(number=2):
    return {f"ja{number}:0.1": "Jātaka", f"ja{number}:1.1": "Ānandaṁ vadati, ",
            f"ja{number}:1.2": "puna vadati.", f"ja{number}:2.1": "Testajātakaṁ dutiyaṁ."}


class ExtractionTests(unittest.TestCase):
    def test_whole_source_and_repeated_source_verses_remain_in_order(self):
        result = abt.compare_source(2, source(), reference(), summary=False)
        self.assertEqual(result["pairs"][0]["english"]["text"], "He speaks.\nHe speaks.")
        self.assertEqual(result["pairs"][0]["pali"]["break_count"], 1)
        self.assertEqual(result["variant_verses"], [])
        whole = result["whole_source_comparison"]
        self.assertEqual(whole["whole_visible_wording_sha256"], whole["partition_wording_sha256"])
        self.assertEqual(result["paragraph_partition"]["commentary"], 1)

    def test_note_words_and_breaks_are_preserved_but_do_not_become_verse_words(self):
        page = source(english='He <span class="TT"><span>Note ā.<br>Note two.</span><sup></sup></span>speaks.<br>He speaks.')
        result = abt.compare_source(2, page, reference(), summary=False)
        pair = result["pairs"][0]
        self.assertEqual(pair["english"]["text"], "He speaks.\nHe speaks.")
        self.assertEqual(pair["english"]["notes"], ["Note ā.\nNote two."])
        body = abt.render_body(result, False)
        self.assertIn("Note ā.\nNote two.", body)
        self.assertEqual(body.count("He speaks."), 2)

    def test_unselected_visible_source_words_fail_whole_source_comparison(self):
        with self.assertRaisesRegex(ValueError, "visible wording"):
            abt.compare_source(2, source(extra='<div>Previously unrecorded words.</div>'), reference(), summary=False)

    def test_missing_english_and_unpaired_source_order_are_rejected(self):
        for original in (source().replace(b'<p class="translation">He speaks.<br>He speaks.</p>', b''),
                         source().replace(b'<p class="verse3">', b'<p class="translation">', 1)):
            with self.subTest(original=original), self.assertRaisesRegex(ValueError, "verse pairs"):
                abt.compare_source(2, original, reference(), summary=False)

    def test_source_number_duplicates_gaps_and_unreviewed_unnumbered_stanzas_fail(self):
        for first in ("2.", "3.", ""):
            with self.subTest(first=first), self.assertRaisesRegex(ValueError, "number|unnumbered"):
                abt.compare_source(2, source(pali=f"{first} Ānandaṁ vadati,<br>puna vadati."), reference(), summary=False)

    def test_two_reviewed_unnumbered_sources_do_not_receive_inserted_numbers(self):
        for number in (39, 46):
            result = abt.compare_source(number, source(number=number, pali="Ānandaṁ vadati,<br>puna vadati."), reference(number), summary=False)
            self.assertIsNone(result["pairs"][0]["printed_number"])
            self.assertTrue(result["pairs"][0]["pali"]["text"].startswith("Ānandaṁ"))

    def test_additional_reference_verses_cannot_be_passed_as_colophon(self):
        root = reference()
        root["ja2:2.1"] = "More canonical verse."
        root["ja2:3.1"] = "Testajātakaṁ dutiyaṁ."
        with self.assertRaisesRegex(ValueError, "colophon"):
            abt.compare_source(2, source(), root, summary=False)

    def test_reference_line_gaps_reordering_and_wrong_canonical_ids_fail(self):
        root = reference()
        for wrong in ({**root, "ja2:1.4": "lost line"},
                      {**root, "ja3:1.1": "wrong work"},
                      dict(reversed(list(root.items())))):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                abt.compare_source(2, source(), wrong, summary=False)

    def test_trailing_uddana_is_separate_apparatus_and_other_extra_text_fails(self):
        page = source(number=10)
        root = reference(10)
        root.update({"ja10:2.1": "Testajātakaṁ dasamaṁ.", "ja10:2.2": "Apaṇṇakavaggo paṭhamo.",
                     "ja10:3.1": "Tassuddānaṁ", "ja10:4.1": "A collection index."})
        result = abt.compare_source(10, page, root, summary=True)
        self.assertEqual(len(result["pairs"]), 1)
        self.assertEqual(result["trailing_summary"][4], ["A collection index."])
        self.assertNotIn("collection index", abt.render_body(result, False))
        root["ja10:3.1"] = "Another verse, not an index."
        with self.assertRaisesRegex(ValueError, "Unaccounted"):
            abt.compare_source(10, page, root, summary=True)

    def test_different_pali_readings_are_classified_not_retranslated(self):
        page = source(pali="1. Ānandaṁ na vadati,<br>puna vadati.")
        result = abt.compare_source(2, page, reference(), summary=False)
        self.assertEqual(result["variant_verses"], [1])
        self.assertIn("Ānandaṁ na vadati,\npuna vadati.", abt.render_body(result, True))

    def test_stray_table_tags_do_not_drop_source_verse_text(self):
        page = source(pali="<tr>1. Ānandaṁ vadati,<br>puna vadati.")
        result = abt.compare_source(2, page, reference(), summary=False)
        self.assertEqual(result["pairs"][0]["printed_number"], 1)
        self.assertEqual(result["variant_verses"], [])

    def test_unclosed_commentary_tooltip_stays_in_its_source_paragraph(self):
        page = source(number=13, extra='<p>Before <span class="TT"><span>Note.</span><sup></sup> trailing.</p><p>After.</p>')
        result = abt.compare_source(13, page, reference(13), summary=False)
        self.assertEqual(len(result["html_repairs"]), 1)
        self.assertEqual(result["source_blocks"][-1]["text"], "After.")
        self.assertEqual(result["source_blocks"][-2]["notes"], ["Note. trailing."])

    def test_unreviewed_unclosed_tooltips_in_verses_are_held(self):
        page = source(english='He speaks.<span class="TT"><span>Note.</span><sup></sup> More verse.')
        with self.assertRaisesRegex(ValueError, "Unreviewed unclosed"):
            abt.compare_source(2, page, reference(), summary=False)

    def test_all_original_body_wording_is_compared_no_prefix_or_count_shortcuts(self):
        result = abt.compare_source(2, source(), reference(), summary=False)
        url = abt.BASE + "English-Texts/Jataka-Verses/002.htm"
        original = (f"Ja 2 Test\nSource: {url}\nLicense: CC-BY-SA-4.0 ({abt.LICENCE_URL})\n"
                    "Changes: Original extraction notice.\n\nVerse 1\nHe speaks. He speaks.\n").encode()
        self.assertEqual(abt.compare_original(original, result, False, url)["status"], "ALL_VERSES_MATCH")
        for wrong in (original.replace(b"He speaks. He speaks.", b"He speaks."),
                      original + b"Manufactured repeat.\n", original.replace(b"speaks.", b"spoke.", 1),
                      original.replace(b"Test\n", b"Other\n", 1)):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                abt.compare_original(wrong, result, False, url)

    def test_source_pin_rejects_changed_content_and_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source"
            path.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                abt.verified(path, abt.sha256(b"changed"))
            with self.assertRaisesRegex(ValueError, "escapes"):
                abt.within(Path(directory), "../outside")


class RightsTests(unittest.TestCase):
    def copyright(self):
        path = abt.DEFAULT_OUT / "evidence/copyright.html"
        if not path.is_file():
            self.skipTest("Saved reviewed ABT copyright evidence unavailable")
        return path.read_bytes()

    def test_exact_page_footer_and_copyright_exception_list_are_required(self):
        footer = f'Creative Commons Attribution-ShareAlike 4.0 License {abt.LICENCE_URL}'.encode()
        url = abt.BASE + "English-Texts/Jataka-Verses/002.htm"
        self.assertEqual(abt.check_licence(source(), footer, self.copyright(), url)["licence"], "CC-BY-SA-4.0")
        for copyright in (self.copyright() + b"New Jataka-specific exception", b"by-sa/3.0 May 2013"):
            with self.assertRaisesRegex(ValueError, "exception notice changed"):
                abt.check_licence(source(), footer, copyright, url)

    def test_local_nd_or_copyright_exception_never_inherits_generic_footer(self):
        for notice in ('Copyright third party. All rights reserved.',
                       'License: CC BY-ND 4.0', 'https://creativecommons.org/licenses/by-nc-nd/4.0/'):
            with self.subTest(notice=notice), self.assertRaisesRegex(ValueError, "Page-specific"):
                abt.check_licence(source(extra=f'<p>{notice}</p>'), abt.LICENCE_URL.encode(), self.copyright(), abt.BASE + "English-Texts/Jataka-Verses/002.htm")

    def test_other_work_does_not_inherit_the_jataka_rights_decision(self):
        with self.assertRaisesRegex(ValueError, "restricted to reviewed"):
            abt.check_licence(source(), abt.LICENCE_URL.encode(), self.copyright(), abt.BASE + "English-Texts/Short-Pieces-in-English/Buddhapadana.htm")

    def test_missing_licence_footer_cannot_be_replaced_with_generic_default(self):
        with self.assertRaisesRegex(ValueError, "does not load"):
            abt.check_licence(source().replace(b'../../includes/Footer.js', b'other.js'), abt.LICENCE_URL.encode(), self.copyright(), abt.BASE + "English-Texts/Jataka-Verses/002.htm")

    def test_notice_retains_original_grant_attribution_and_change_notice(self):
        original = "Publisher: Original publisher\nLicense: CC-BY-SA-4.0\nChanges: Original change notice."
        notice = abt.licence_notice("https://example.org/source", original)
        self.assertIn(original, notice)
        self.assertIn("Creative Commons Attribution-ShareAlike 4.0 License", notice)
        self.assertIn("attribution should be made to Anandajoti Bhikkhu", notice)
        self.assertIn("https://example.org/source", notice)


class SavedBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = abt.DEFAULT_OUT / "proposal.json"
        if not path.is_file():
            raise unittest.SkipTest("Run the preparer to validate the local saved 287-record batch")
        cls.batch = json.loads(path.read_text(encoding="utf-8"))
        cls.rows = cls.batch["records"]

    def test_all_287_identity_scope_and_exact_payload_hashes(self):
        rows = self.rows
        self.assertEqual(len(rows), 287)
        self.assertEqual(self.batch["held_count"], 0)
        self.assertEqual(len({r["prior_record_id"] for r in rows}), 287)
        fields = {"source_snapshot", "source_sha256", "body_path", "body_sha256", "source_comparison", "source_comparison_method", "version_slug", "collection", "canonical_id", "title", "translator", "source_url", "license", "license_url", "copyright", "license_notice", "completeness_status", "completeness_scope", "source_revision", "upstream_file", "exceptions"}
        for row in rows:
            with self.subTest(record=row["canonical_id"]):
                self.assertFalse(fields - row.keys())
                self.assertEqual(row["source_comparison"], "PASS")
                self.assertEqual(row["completeness_status"], "COMPLETE")
                self.assertTrue(row["source_url"].startswith("https://"))
                self.assertEqual(abt.sha256((abt.REPO / row["body_path"]).read_bytes()), row["body_sha256"])
                self.assertEqual(abt.sha256((abt.REPO / row["source_snapshot"]).read_bytes()), row["source_sha256"])
                comparison = json.loads((abt.REPO / row["comparison_path"]).read_text(encoding="utf-8"))
                self.assertEqual(comparison["original_txt"]["status"], "ALL_VERSES_MATCH")
                self.assertEqual(comparison["whole_source_comparison"]["status"], "ALL_VISIBLE_BODY_CHARACTERS_ACCOUNTED_FOR")
                self.assertIn(comparison["original_txt"]["original_header"], row["license_notice"])

    def test_repreparation_is_deterministic_and_needs_no_network(self):
        proposal = abt.DEFAULT_OUT / "proposal.json"
        before = abt.sha256(proposal.read_bytes())
        files = [abt.DEFAULT_OUT / n for n in ("summary.json", "CURRENT.md", "native-collections.json", "proposals.jsonl")]
        original_hashes = {p.name: abt.sha256(p.read_bytes()) for p in files}
        with patch.object(abt, "urlopen", side_effect=AssertionError("Offline preparer attempted network")):
            summary = abt.run(abt.REPO, abt.REPO.parent / "buddhism", abt.DEFAULT_OUT,
                              abt.DEFAULT_OUT / "inputs/candidates.json")
        self.assertEqual(summary["ready"], 287)
        self.assertEqual(abt.sha256(proposal.read_bytes()), before)
        self.assertEqual({p.name: abt.sha256(p.read_bytes()) for p in files}, original_hashes)

    def test_changed_source_hash_holds_one_record_with_no_importable_body(self):
        archive = abt.REPO.parent / "buddhism"
        candidate = json.loads((abt.DEFAULT_OUT / "inputs/candidates.json").read_text())["text_versions"][0]
        name = abt.GROUPS[candidate["source_group"]][0]
        manifest = json.loads((archive / f"metadata/source-manifests/{name}.json").read_text())
        number = int(candidate["canonical_id"].split()[1])
        next(e for e in manifest["texts"] if e["number"] == number)["html_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row, comparison = abt.prepare_record(candidate, archive, root, root / "build/abt-bulk-20261111", {name: manifest}, {})
            self.assertEqual(row["disposition"], "HELD")
            self.assertEqual(row["source_comparison"], "FAIL")
            self.assertIsNone(row["body_path"])
            self.assertIn("Pinned source hash mismatch", comparison["failure"])

    def test_actual_main_importer_accepts_entire_batch_in_isolated_tree(self):
        # Exercise the real integration contract without touching shared files.
        import import_licensed_batches as importer
        import publication_rights as rights

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "metadata"
            metadata.mkdir()
            for name, value in (("eligible-texts.json", {"texts": []}),
                                ("excluded-sources.json", {"text_versions": []}),
                                ("public-file-allowlist.json", {"files": []})):
                abt.write_json(metadata / name, value)
            rows = [dict(r, body_path=str(abt.REPO / r["body_path"]), source_snapshot=str(abt.REPO / r["source_snapshot"])) for r in self.rows]
            proposal = root / "proposal.json"
            abt.write_json(proposal, {"records": rows})
            manifest_path = metadata / "source-manifests/licensed-collections.json"
            with patch.object(importer, "ROOT", root), patch.object(importer, "MANIFEST", manifest_path), patch.object(importer, "verified_manifest", lambda: rights.verified_manifest(root=root, manifest_path=manifest_path)):
                self.assertEqual(importer.import_proposal(proposal), 286)
                manifest = rights.verified_manifest(root=root, manifest_path=manifest_path)
                self.assertEqual(len(manifest["records"]), 286)
                by_id = {r["prior_record_id"]: r for r in manifest["records"]}
                for row in self.rows:
                    if row["canonical_id"] == "Ja 93":
                        self.assertNotIn(row["prior_record_id"], by_id)
                        continue
                    imported = by_id[row["prior_record_id"]]
                    wrapped = (root / imported["local_path"]).read_text(encoding="utf-8")
                    self.assertIn(" ".join(row["license_notice"].split()), wrapped)
                    self.assertEqual((root / imported["source_snapshot"]).read_bytes(), (abt.REPO / row["source_snapshot"]).read_bytes())
                # Existing identical records are idempotent; changed hashes fail.
                self.assertEqual(importer.import_proposal(proposal), 0)
                changed = dict(rows[0], body_sha256="0" * 64)
                abt.write_json(proposal, {"records": [changed]})
                with self.assertRaisesRegex(ValueError, "body changed"):
                    importer.import_proposal(proposal)


if __name__ == "__main__":
    unittest.main()
