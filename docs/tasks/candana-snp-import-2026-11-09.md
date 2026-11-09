# Candana Sutta Nipāta import and reader release

The owner authorized completing the next verified reader import and publishing it on
2026-11-09, with automation and spot checks instead of repeated per-text conversion work.
The homepage and existing plain reading layout must remain unchanged. Luna's separate
missing-book investigation is not part of this release.

## Source and checks

Use only the frozen 391-page PDF and raw text already published for comparison.
Their exact pins and source-specific redistribution grant remain in
metadata/source-manifests/candana-snp-review.json. Neither original is rewritten.
The [local conversion method](../reviews/candana-local-conversion-testing.md) records
complete automatic comparison, the returned external review and limited visual samples.

- All 73 explicit Snp book/text references match the existing 73 site references
  one-to-one. The import report retains source titles and existing translated titles
  separately. No numbering offset or invented reference is used.
- Generate every reader from its exact source interval. Reflow physical whitespace,
  preserve source paragraph gaps and the Snake's verified refrain starts, and omit only
  the exact-source footer numerals identified geometrically in the prior layout review.
  Retain every other word, punctuation mark, accent, note and number in order.
- Front matter, five book dividers and back matter remain in the original and review
  snapshot; they are not duplicated into individual suttas.
- The earlier 364-page PDF remains pinned as historical evidence, not overwritten or
  promoted as this source. Ordinary readers use the separately identified 391-page book.
- Automatic text fidelity and direct-reference mapping are verified. Full human
  proofreading and translation-accuracy certification are not claimed. Completeness
  metadata remains UNKNOWN, not silently promoted by successful automation.

## Repeatable automation

Run python tools/buddhist_canon_pipeline/import_candana.py --install-sutta-nipata.
This checks the frozen source, complete audit and exact reference set, then generates
all 73 TXT files, source/book metadata and a reproducible mapping report in one run.
It preserves the earlier AN imports and unrelated editions. Repeating it is byte-for-byte
idempotent; changed existing readers, source pins or mappings fail rather than being
silently overwritten. It makes no network requests or model calls.

The ordinary validator reconstructs all 73 readers on each release check. Tests cover
changed sources/audits/readers, duplicate IDs, missing folios, actual body numerals,
preserved hard breaks, stale reports and repeat installation. The build verifies reader
text, generated PDF text, archive membership and site links. It reuses unchanged PDFs.

Continue using the existing background collector and private draft timer. They cache
and compare unfamiliar sources but never update the eligible manifests or publish.
New layouts need a checked recipe, not a new model-driven conversion for every sutta.
Rights, layout and mapping exceptions remain explicit rather than being auto-approved.

## Release scope and spot checks

- Prepared ordinary editions: 874 Candana entries, comprising 452 AN Book One,
  194 Book Two, 155 Book Three and 73 Sutta Nipāta entries. These are reader units,
  not 874 books. The earlier 801 AN entries had not yet been deployed.
- Before this release, live ordinary readers contain no Candana editions. The live
  navigation and public conversion review already reflect earlier website work.
- Prefer Candana when available, retain every other eligible translation, respect
  saved choices and identify any fallback explicitly. Carry the Sutta Nipāta source's
  correct 2023 notice in both individual and continuous readers.
- Browser samples: the Snake, wrapped titles at Snp 2.12 and 5.3, the long Snp 3.12,
  final Snp 5.19, AN Books One–Three, source suffixes, the combined cloth text,
  translator switching and a held-AN fallback. Check node links, natural desktop/mobile
  wrapping, Unicode, preserved verse starts and unchanged displayed source text.
- Verify all 73 generated Sutta Nipāta HTML bodies automatically, not just samples.
  Keep the homepage hash, existing translation files and public review snapshot unchanged.

The 13 later AN Book Three source groups and the Manual's 20 number-placement cases
remain unresolved and outside the reader import. Sources lacking source-specific
permission remain private. Publication status is recorded with the exact source pin
in the separate deployment repository after the live checks complete.
