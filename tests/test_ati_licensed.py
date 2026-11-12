# SPDX-License-Identifier: 0BSD
"""Integrity and rights tests for private ATI/Thanissaro bulk preparation."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
import prepare_ati_licensed as ati

GRANT = (
    "You may copy, reformat, reprint, republish, and redistribute this work in any medium whatsoever, "
    "provided that: (1) you only make such copies, etc. available free of charge and, in the case of "
    "reprinting, only in quantities of no more than 50 copies; (2) you clearly indicate that any "
    "derivatives of this work (including translations) are derived from this source document; and "
    "(3) you include the full text of this license in any copies or derivatives of this work. "
    "Otherwise, all rights reserved. Documents linked from this page may be subject to other restrictions."
)


def reference():
    return {"site_ids": {"AN 3.33": "anguttara-nikaya", "AN 3.34": "anguttara-nikaya",
                         "AN 11.15": "anguttara-nikaya", "AN 11.16": "anguttara-nikaya",
                         "DN 12": "digha-nikaya", "DN 21": "digha-nikaya"},
            "pali_titles": {"AN 3.33": ["Sāriputtasutta"], "AN 3.34": ["Nidānasutta"],
                            "AN 11.15": ["Mettāsutta"], "AN 11.16": ["Aṭṭhakanāgarasutta"]},
            "pali_references": {}, "prior_records_by_url": {}}


class AtiIntegrityTests(unittest.TestCase):
    def test_only_exact_complete_protected_region_is_selected(self):
        protected = "<div id='COPYRIGHTED_TEXT_CHUNK'><div><p>Text &amp; notes.</p></div></div>"
        html = "<div>Header</div>" + protected + "<div>Footer</div>"
        self.assertEqual(ati.region(html, "COPYRIGHTED_TEXT_CHUNK"), protected)
        self.assertEqual(ati.render(protected), "Text & notes.\n")
        for bad in (protected[:-6], protected + protected, "<p>No chunk</p>"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ati.region(bad, "COPYRIGHTED_TEXT_CHUNK")

    def test_all_notes_headings_and_unwrapped_text_survive(self):
        fragment = "<div id='sutta'>Introduction<p>A <em>complete</em> discourse.</p><h2>Notes</h2><dl><dt>1.</dt><dd>Final note.</dd></dl>Colophon.</div>"
        body = ati.render(fragment)
        self.assertIn("Introduction\n\nA complete discourse.", body)
        self.assertIn("Notes\n\n1.\n\nFinal note.\n\nColophon.", body)
        ati.check_characters(fragment, body)

    def test_corruption_omission_reordering_and_normalization_fail(self):
        source = "<div><p>First: Ānanda’s text…</p><p>Second &amp; last.</p></div>"
        body = ati.render(source)
        for changed in (body.replace("First", "First changed"), body.replace("last.", ""),
                        body.replace("Ā", "A"), body.replace("…", "..."),
                        "Second & last.\n\nFirst: Ānanda’s text…\n"):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                ati.check_characters(source, changed)

    def test_paragraphs_and_explicit_linebreaks_are_distinct(self):
        body = ati.render("<div><p>Paragraph one.</p><p>Paragraph two.<br>New line.</p></div>")
        self.assertEqual(body, "Paragraph one.\n\nParagraph two.\nNew line.\n")

    def test_epub_verse_lines_stanzas_and_indentation_survive(self):
        source = '<div><p>Prose.</p><div class="verse"><p>Line one</p><p class="v2">Line two</p><div class="verse-add"><p>Next stanza</p></div></div><p>Note.</p></div>'
        body = ati.render(source)
        self.assertIn("Prose.\n\nLine one\n    Line two\n\nNext stanza\n\nNote.", body)
        self.assertNotEqual(body, " ".join(body.split()))

    def test_ati_preformatted_verse_is_not_flattened(self):
        source = "<div><pre>First line\n    indented line\n\nLast stanza</pre><p>After.</p></div>"
        self.assertEqual(ati.render(source), "First line\n    indented line\n\nLast stanza\n\nAfter.\n")

    def test_nontext_protected_content_is_held(self):
        for element in ("<img alt='verse scan'>", "<script>text</script>", "<iframe></iframe>"):
            with self.subTest(element=element), self.assertRaises(ValueError):
                ati.render("<div>Text" + element + "</div>")


class AtiRightsAndMappingTests(unittest.TestCase):
    def test_standard_license_is_per_text(self):
        result = ati.rights("This text is licensed under https://creativecommons.org/licenses/by-nc/4.0/", "https://example.org/text")
        self.assertEqual(result["license"], "CC-BY-NC-4.0")
        self.assertEqual(ati.rights("See http://creativecommons.org/licenses/by-nc/4.0/.",
                                    "https://example.org/text")["license"], "CC-BY-NC-4.0")
        for unsupported in ("Free download", "All rights reserved", "", "Site is CC BY, linked work unspecified"):
            with self.subTest(unsupported=unsupported), self.assertRaises(ValueError):
                ati.rights(unsupported, "https://example.org/text")

    def test_no_derivatives_is_separately_held(self):
        with self.assertRaisesRegex(ValueError, "separate review"):
            ati.rights("https://creativecommons.org/licenses/by-nc-nd/4.0/", "https://example.org/text")

    def test_ireland_grant_preserves_complete_terms_and_print_limit(self):
        result = ati.rights(GRANT, "https://example.org/ireland#F_termsOfUse")
        self.assertEqual(result["license"], ati.FREE_GRANT)
        self.assertEqual(result["explicit_grant"], GRANT)
        self.assertEqual(result["license_url"], "https://example.org/ireland#F_termsOfUse")
        self.assertIn("printed-reproductions-no-more-than-50-copies", result["conditions"])
        with self.assertRaises(ValueError):
            ati.rights(GRANT.replace("include the full text of this license", "permission pending"), "https://example.org/text")

    def test_site_blanket_notice_does_not_replace_missing_work_grant(self):
        source = "<div id='F_colophon'>CC BY 4.0 for site only</div><div id='F_sourceCopy'>Copyright owner</div>"
        with self.assertRaisesRegex(ValueError, "per-text"):
            ati.ati_rights(source, "https://example.org/text")

    def test_ati_an_numbering_uses_explicit_thai_and_pali_evidence(self):
        canonical, evidence = ati.resolve_id("AN", "3.33", "Nidana Sutta", reference(), "Thai 3.34; BJT 3.34")
        self.assertEqual(canonical, "AN 3.34")
        self.assertEqual(evidence["publisher_id"], "AN 3.33")

    def test_epub_wrong_number_is_corrected_only_by_unique_pali_title(self):
        canonical, evidence = ati.resolve_id("AN", "11.16", "Mettā Sutta", reference())
        self.assertEqual(canonical, "AN 11.15")
        self.assertIn("numbering corrected", evidence["method"])
        with self.assertRaisesRegex(ValueError, "needs review"):
            ati.resolve_id("AN", "11.16", "Unidentified Sutta", reference())

    def test_grouped_sources_cannot_become_invented_single_translations(self):
        for number in ("1.21-40", "1.21–30,39–40", "2.31-32", "3.100 (i-x)"):
            with self.subTest(number=number), self.assertRaisesRegex(ValueError, "Grouped"):
                ati.resolve_id("AN", number, "Title", reference())
        source = "<title>AN 2:31–32 Gratitude | Kataññu Suttas</title><div id='sutta'>Text.</div>"
        with self.assertRaisesRegex(ValueError, "Grouped"):
            ati.epub_unit("AN/AN2_31.html", source, reference(), {})

    def test_unknown_canonical_ids_are_held(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            ati.resolve_id("DN", "99", "No such discourse", reference())

    def test_partial_takes_priority_and_unknown_is_never_complete(self):
        self.assertEqual(ati.completeness("Text", extent="excerpt", thanissaro=True)[0], "PARTIAL")
        self.assertEqual(ati.completeness("Text", explicit_partial=True, thanissaro=True)[0], "PARTIAL")
        self.assertEqual(ati.completeness("Full source text", thanissaro=True)[0], "ABBREVIATED")
        self.assertEqual(ati.completeness("Text…")[0], "ABBREVIATED")
        self.assertEqual(ati.completeness("Text without evidence", extent="complete")[0], "UNKNOWN")


class AtiBatchTests(unittest.TestCase):
    def test_prepared_batch_contract_and_full_recomparison(self):
        proposal_path = ati.DEFAULT_OUTPUT / "proposal.json"
        if not proposal_path.exists():
            self.skipTest("Official private archive batch is not present")
        proposal = json.loads(proposal_path.read_bytes())
        self.assertGreater(len(proposal["records"]), 1000)
        required = {"source_snapshot", "source_sha256", "body_path", "body_sha256", "source_comparison",
                    "source_comparison_method", "version_slug", "collection", "canonical_id", "title",
                    "translator", "source_url", "license", "license_url", "copyright", "license_notice",
                    "completeness_status", "completeness_scope", "source_revision", "upstream_file", "exceptions"}
        reference_data = json.loads((ati.DEFAULT_OUTPUT / "canonical-reference.json").read_bytes())
        for row in proposal["records"]:
            self.assertLessEqual(required, row.keys())
            self.assertIn(row["canonical_id"], reference_data["site_ids"])
            self.assertTrue(row["source_url"].startswith("https://"))
            self.assertEqual(row["source_comparison"], "PASS")
            self.assertNotEqual(row["completeness_status"], "COMPLETE")
        self.assertEqual(ati.verify(proposal_path)["records"], len(proposal["records"]))


if __name__ == "__main__":
    unittest.main()
