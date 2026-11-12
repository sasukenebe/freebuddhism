# Authorised translation imports

The owner approved this requirements change on November 11, 2026. The goal is maximum
accurate, legally redistributable coverage of the English Sutta Piṭaka, followed by
comparison and selection of preferred translations for each text.

## Publication requirements

- Accept CC0, verified public domain, CC BY, BY-SA, BY-NC and BY-NC-SA editions.
- Accept explicit permission for free TXT/HTML redistribution, including grants requiring
  unchanged contents. Preserve every applicable condition.
- Record and retain attribution, copyright, source, license notice and license link in
  readers, text files, generated PDFs, archives and edition metadata.
- Keep the website noncommercial: no advertising, affiliate monetization, paid access or
  sale of downloads. Text licenses do not change the original code's 0BSD license.
- Hold unclear rights. Review no-derivatives editions separately. Never describe a
  conditionally licensed edition as unrestricted or CC0.
- Preserve wording, numbering, repetitions and verse structure. Never invent expansions.
- Track COMPLETE, ABBREVIATED, PARTIAL or UNKNOWN independently of permission and source
  extraction fidelity. An exact extraction can still contain the author's abbreviations.

The machine-readable policy is [rights-policy.json](../../metadata/rights-policy.json).
This policy supersedes the earlier CC0/public-domain-only restrictions; historical
classification reports remain evidence of that earlier decision, not current requirements.

## Execution and evidence

- Automatically reassess all 937 previously identified entries with stated conditional
  licenses or free-distribution terms. Preserve the complete result and reasons.
- Process whole eligible collections. Work on PTS, SuttaCentral, Access to Insight and
  Ancient Buddhist Texts in parallel, preferring native text, HTML or EPUB over PDF/OCR.
- Check each edition's actual rights, including editorial expansions in PTS-derived EPUBs.
- Compare complete source text, retain source hashes and spot-check representative pages.
  Put exceptions requiring human judgment into one running review list.
- Generate a coverage report showing both newly covered texts and additional editions.
  This report helps track progress; it is not a prerequisite for importing a cleared batch.
- Publish validated batches without waiting for completion of the entire canon. Keep the
  original homepage and established plain reading presentation.

## Current work

The primary worker owns policy enforcement, bulk integration and publication. Parallel
workers prepare PTS, ATI and ABT source batches with disjoint files. SuttaCentral's
previously saved source snapshots support its separate full-collection preparation.

Candana's separately published PDFs remain on the existing permission-scope review list;
that pending reply does not hold up other authorised translators. Source comparisons,
mapping questions and publication results will be added here as batches are validated.

## November 11 import batch

Imported locally: 2,690 editions across 1,923 text IDs. This supplies text for 649
previously unavailable entries; the other additions are alternative editions.

- SuttaCentral and Ireland: 649 editions, including all 601 saved Walters Apadāna
  articles, 37 Netti sections, nine Peṭakopadesa sections and two Vimānavatthu texts.
- Ancient Buddhist Texts: 286 Jātaka verse editions. These are verse sets, sometimes
  alternate Pāli readings, not 287 new stories or complete narrative translations.
- Access to Insight and dhammatalks: 1,755 editions from their original bulk archives.
  Exact per-text terms, attribution, copyright and complete notices are retained.
- All 937 earlier conditional-license exclusions reassessed: 935 imported; The Path of
  Discrimination and ABT Ja 93 remain held for source review. No permission was inferred from
  merely offering a free download.

Completeness of these editions: 889 COMPLETE within the recorded source scope,
1,659 ABBREVIATED, 32 PARTIAL and 110 UNKNOWN. Source fidelity and translation quality
are separate. Repeated passages were never manufactured or silently filled in.

The generated coverage records are under metadata/reports/translation-coverage-2026-11-11.
The exact imported texts, source hashes, license conditions and per-edition review notes
are in metadata/source-manifests/licensed-collections.json. The public build generates
/review/licensed-2026-11-11/ with Original source and Converted text links for every
edition. A review note is not necessarily an error.

### Remaining review and next batches

- The Path of Discrimination: 664 PDF pages compared with two extraction engines;
  154 pages differ in reading order. Do not publish the unreviewed conversion.
- ATI/dhammatalks: 846 source pages held, primarily for ambiguous titles, numbering,
  combined texts or unclear small-collection scope. This is not a count of unique
  missing suttas. Preserve combined passages rather than inventing individual texts.
- PTS Nikāya EPUBs: 2,663 source XHTML documents prepared. PTS permission identifies
  MN, SN and AN; verify editorial additions and exact mappings before import. DN
  needs separate edition-specific rights evidence. Expanded repetitions are the
  editor's claim, not a result established by this extraction.
  Follow-up source inspection found that the supplied MN EPUB's MN 2 and MN 5
  documents end partway through their openings, with unresolved note links. These
  are source omissions, not conversion loss. Find a better source or label those
  editions PARTIAL; do not describe this EPUB as a verified complete collection.
- Walters: retain the original source IDs and headings where their printed numbers
  differ; review notes identify the discrepancies. The 601 saved articles do not
  establish that every reference in every Apadāna numbering system is present.
- Netti and Peṭakopadesa: publisher source says the electronic texts have not been
  proofread. Source units and printed chapters differ; preserve notes and numbering.
- ABT: retain both the page's CC BY-SA 4.0 footer and the older copyright-page notice;
  scope here is the English verse sets. Narrative and commentary are not claimed.
  Ja 93 is held because its Sanskrit note uses private font code U+F82A. Its original
  source and converted draft are preserved outside publication. Verify the original
  font's mapping; do not guess a Unicode replacement or publish a broken glyph.
- Candana: separately published PDFs await clarification of the author's grant.
  The existing rolling review list remains in candana-corpus-inventory-2026-11-09.md.
- All additions still require human quality/visual spot checks. Automated full-text
  comparison proves preservation, not the quality of the translation or source.

### Validation and publication

The original homepage is unchanged. New editions use the existing plain readers,
text pages, translator choices and continuous-reading view. Full source comparisons
passed for each accepted batch. Publication is pending the complete site build,
reader/download checks and deployment; do not treat local imports as live content.
Policy-related availability notices and exclusion metadata use the revised rights
rules; historical CC0-only wording is not a current reason to exclude a work.

PDF regressions cover spaced asterisk and bracketed section markers plus the Sanskrit
root symbol. Unsupported visible glyphs use an installed supporting Unicode font.
Five discretionary soft-hyphen layout hints are omitted only in PDF presentation,
with an explicit note. Original TXT and HTML retain them. Word deletion/substitution
still fails verification. Successful exports are checkpointed; a failed export stops
the batch promptly without claiming success or discarding verified progress.
