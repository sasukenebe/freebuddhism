import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))

from import_candana import (  # noqa: E402
    LICENSE, audit_one, granted_notice, split_an_one, verified_manifest, reflow_text,
)
from build_eligible_readers import collect_candana_records, config_for, index_records  # noqa: E402
from render_cc0_reader import ReaderParser, render_html  # noqa: E402
from public_site_catalog import edition_priority  # noqa: E402
from build_deploy_site import _record_license_is_allowed  # noqa: E402


class CandanaTests(unittest.TestCase):
    def test_reflow_removes_pdf_width_without_changing_words_or_paragraphs(self):
        self.assertEqual(reflow_text("  Ānanda spoke\n about the Dhamma.\n\nAgain and\n again.\n"),
                         "Ānanda spoke about the Dhamma.\n\nAgain and again.\n")
        self.assertEqual(reflow_text("Perfectly Self-\nAwakened.\n"), "Perfectly Self-Awakened.\n")
        with self.assertRaisesRegex(ValueError, "Unreviewed hyphenated"):
            reflow_text("An unreviewed-\ncompound.\n")
    def test_explicit_grant_does_not_require_cc0(self):
        grant = ("Copyright Candana. You may copy, reprint, republish and redistribute this work "
                 "in any medium, provided copies are free of charge and you do not alter its contents.")
        self.assertTrue(granted_notice(grant))
        self.assertFalse(granted_notice("Copyright Candana. Free download for all."))
        self.assertFalse(granted_notice(grant.replace("not alter its contents", "edit freely")))

    def test_uncached_sources_never_bypass_the_timer(self):
        self.assertEqual(audit_one("https://www.mindreleased.com/s/not-a-real-fixture.pdf")["rights"], "PENDING_TIMER")

    def test_splitting_retains_repetitions_and_moves_chapter_headers_forward(self):
        first = "AN I\nSuttas 1-10\nChapter One\n" + "".join(f"{i}.\nRepeated teaching {i}.\n\n" for i in range(1, 11)) + "1\n\f"
        rest = "AN I\nSuttas 11-627\nChapter Two\n" + "".join(f"{i}.\nRepeated teaching {i}.\n\n" for i in range(11, 628))
        rest = rest.replace("\n235.\n", "\n             Pañcama Vagga\n             The Fifth Sub Group\n\n235.\n")
        text = first + rest + "(Here ends Book of the Ones)\nAuthor's final note\n2\n\f"
        sections, pages = split_an_one(text)
        self.assertEqual(len(sections), 627)
        self.assertIn("Chapter One", sections[1])
        self.assertNotIn("Chapter Two", sections[10])
        self.assertIn("Chapter Two", sections[11])
        self.assertNotIn("final note", sections[627])
        self.assertNotIn("Pañcama Vagga", sections[234])
        self.assertIn("Pañcama Vagga", sections[235])
        self.assertEqual(pages[11], 2)
        self.assertEqual(sum("Repeated teaching" in part for part in sections.values()), 627)
        with self.assertRaisesRegex(ValueError, "ordered headings"):
            split_an_one(text.replace("312.\n", "313.\n", 1))

    def test_every_imported_unit_matches_the_original_book(self):
        manifest = verified_manifest()
        self.assertEqual(len([row for row in manifest["texts"] if row["book"] == "an-book1"]), 452)
        self.assertEqual(len(manifest["texts"]), 801)
        self.assertEqual(manifest["source_units"], 627)
        self.assertEqual(len(manifest["books"]), 4)
        self.assertEqual(next(book for book in manifest["books"] if book["id"] == "sutta-nipata")["plain_text_status"], "HOLD_EXTRACTION_QUALITY")
        self.assertNotIn("MN 1", {row["canonical_id"] for row in manifest["texts"]})

    def test_publication_rejects_a_stale_extraction_review(self):
        original = Path.read_text
        def read(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            if path.name == "candana-extraction-2026-11-05.json":
                report = json.loads(value)
                report["source_sha256"] = "0" * 64
                return json.dumps(report)
            return value
        with patch.object(Path, "read_text", read):
            with self.assertRaisesRegex(ValueError, "missing or stale"):
                verified_manifest(require_review=True)

    def test_candana_is_first_without_removing_other_editions(self):
        versions = [{"version": "other", "version_label": "Another translator"},
                    {"version": "sujato", "version_label": "Bhikkhu Sujato"},
                    {"version": "candana", "version_label": "Bhikkhu Candana"}]
        self.assertEqual([row["version"] for row in sorted(versions, key=edition_priority)], ["candana", "sujato", "other"])

    def test_reader_body_is_unchanged_and_displays_permission_source(self):
        records = collect_candana_records(ROOT / "build/candana-test-readers")
        first = next(row for row in records if row["canonical_id"] == "AN 1.1")
        config = config_for(first, index_records(records))
        html = render_html(config, first["body"])
        parser = ReaderParser()
        parser.feed(html)
        self.assertEqual("".join(parser.source_parts), first["body"])
        self.assertIn("Original book PDF and complete permission notice", html)
        self.assertIn("Free distribution only; do not alter the contents", html)
        self.assertTrue(_record_license_is_allowed(first))
        self.assertFalse(_record_license_is_allowed({**first, "source_sha256": "0" * 64}))
        self.assertEqual(hashlib.sha256(first["body"].encode()).hexdigest(), first["body_sha256"])

    def test_reader_uses_server_preference_order_and_respects_saved_choices(self):
        from build_deploy_site import _CONTINUOUS_READER_SCRIPT
        self.assertIn("data.preferred_translators", _CONTINUOUS_READER_SCRIPT)
        self.assertIn("savedDefault&&allChoices.has(savedDefault)", _CONTINUOUS_READER_SCRIPT)
        self.assertIn("const fallbackIds=[choice,defaultSelect.value].concat(preferred)", _CONTINUOUS_READER_SCRIPT)
        self.assertIn("edition.reuse_notice", _CONTINUOUS_READER_SCRIPT)


if __name__ == "__main__":
    unittest.main()
