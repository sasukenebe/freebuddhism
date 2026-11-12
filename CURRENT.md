# Current path: complete Sutta Piṭaka coverage

Owner direction: November 12, 2026. This is the active project path, not a claim
that every text or translation has already been published.

## Priority and completion target

1. Provide at least one complete, correctly identified, legally redistributable
   English edition of every text in the Theravāda Sutta Piṭaka, including the
   Khuddaka collections represented by the reference inventory.
2. Fill missing texts and replace partial-only coverage before increasing the
   number of alternative translations of already covered texts.
3. Publish checked gap-filling batches without waiting for the entire collection.
4. Defer Abhidhamma until last. Preserve its existing sources and audit records,
   but do not resume Abhidhamma conversion, OCR, import or publication work while
   the Sutta Piṭaka coverage path remains unfinished.

Use the broad existing Khuddaka collection scope, including Netti, Peṭakopadesa
and Milindapañha. Record the reference edition and grouped numbering explicitly;
do not pretend that different traditions have identical book or discourse counts.
Vinaya already published remains available; unrelated Vinaya expansion and
noncanonical author resources do not outrank missing Sutta Piṭaka texts.

## Current execution

- Build a reproducible inventory against pinned reference sources, not only the
  site's existing reader pages. Empty books must not disappear from the report.
- Keep text availability, completeness, source identity, reuse rights and actual
  deployment as separate fields. An unknown field is not a pass.
- Prioritize empty and thinly covered Khuddaka books: Niddesa, Buddhavaṃsa,
  Paṭisambhidāmagga and Vimānavatthu. Check every other collection too; a large
  translation count is not a complete-canon certificate.
- For each missing unit record a candidate source and its precise next blocker.
  Prefer existing native text/HTML/EPUB over a new OCR project. A complete verified
  source book can be presented intact while individual segmentation is reviewed.
- Prepare the largest cleared gap-filling batch. Keep source hashes, complete
  notices, numbering evidence, repetitions, notes and verse structure intact.
- Continue other cleared sources when one work needs permission or source review.
  Unavailable English translations or unresolved rights remain explicit gaps;
  never fabricate a translation, expansion or permission grant.

## Required release checks

Follow [authorised import requirements](docs/tasks/authorised-bulk-imports-2026-11-11.md)
and the [identity and archive safeguards](docs/tasks/license-archives-and-identity-gates-2026-11-12.md).
Require source preservation, discourse-content evidence for changed IDs, full
file-specific rights, reader/download regressions, clean builds and deployed-page
checks. Preserve the original homepage and established plain reading presentation.
Human proofreading remains separately recorded; automated agreement is not its
replacement. Author contact requires a separately approved exact message.

The previous correction release used source commit
885f3b3463f24036f87399096bae6d7e7d3888dc. The latest individual-reader release is
live at ede22e4b1af1ebb2800f6b90671557c5a42ad04f, with 10,060 reader versions.
These include alternative editions and Vinaya, not 10,060 distinct complete suttas.

## First execution checkpoint

The [coverage-first checkpoint](docs/tasks/sutta-coverage-first-2026-11-12.md)
records the pinned reference inventory, gap counts and the next prepared batch.
Machine-readable outputs are
[coverage](metadata/reports/sutta-coverage-current.json) and
[unresolved coverage CSV](metadata/reports/sutta-gaps-current.csv).
Regenerate with `python tools/buddhist_canon_pipeline/sutta_coverage.py` after
updating edition coverage; `--check` rejects stale outputs in local tests and CI.
These are source/build reports, not an assertion that unimported drafts are live.

The [individual-reader import](docs/tasks/suttafriends-individual-readers-2026-11-12.md)
publishes all 136 prepared Vv/Pv articles, filling 133 identifier gaps. It keeps
the original notices and excludes these editions from combined readers and site/
source archives. All 408 public HTML/TXT/PDF payloads match the validated build.
There remain 101 unmatched reference identifiers and 142 Milindapañha whole-book
alignment cases. Continue source/rights work on Niddesa, Paṭisambhidāmagga and
Buddhavaṃsa, plus content review of the two Apadāna numbering cases. Complete
publisher articles and matching identifiers do not close unverified completeness.

## Candana permission and processing review

On November 12 the owner supplied permission to republish Candana's sutta
translations on freebuddhism.org and reported sending the required confirmation.
Retain all three conditions: no content alterations, free of charge with no
monetization now or in future, and no use of the content for advertising. Keep
the correspondence private; do not infer public-repository or third-party archive
rights from the website permission or overwrite earlier exact-book grants.

The [persistent processing-register procedure](docs/candana-processing-review.md)
covers existing converted passages and standalone drafts. It preserves stable
IDs, original PDFs, both extractions, processing history and separate attributed
review findings outside the disposable build cache, with reviewer provenance
retained privately and human proofreading recorded separately. The first local batch
contains 123 whole-document drafts with matching text layers and clear opening
references, of which 115 lack an existing Candana reference. Another 89 standalone
offers remain held. These counts are source offers, not new public sutta readers
or full semantic/proofreading approval. No new edition was deployed by this work.

AN 4.171 now has an opt-in website-only reader recipe with pinned source/body/TXT
hashes and content-identity evidence. The original heading is retained in edition
details; both numbered sections and the closing words survive unchanged. PDFs and
translation bodies stay out of Git, and enabled builds require explicit staged
inputs. The full local preview passes with 10,061 reader versions, 31 archives and
zero broken local links. All 875 existing Candana readers and 2,821 other licensed
editions retain their checked bodies; the new HTML/TXT/PDF notices and archive/
combined-reader exclusions pass. This adds a Candana edition of an already covered
reference, not a newly filled identifier gap. Nothing new is live. The owner has
authorized the prepared source push and deployment after exact-source CI. Publication needs
production staging/opt-in and deployed-page checks. A successful default build
does not include these optional editions.
