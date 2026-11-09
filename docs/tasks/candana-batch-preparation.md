# Candana batch preparation

Updated: 2026-11-08. Status: implemented and tested for private draft review;
no new editions approved or publicly deployed.

## Purpose and limits

Prepare more written translations without asking an AI to process every page.
The batch command reads the collector's existing PDF cache, checks recorded
source hashes, runs two text converters, creates plain review pages and text
files, and lists exceptions. It makes no network requests and does not change
the collector queue, public edition lists, default translator or deployed site.

Do not describe this as a complete automatic publication importer. It automates
the draft-preparation stage. Source-specific permission, visible-text review and
mapping the author's numbering to the website's text IDs remain separate gates.

## Implementation

- Command: tools/buddhist_canon_pipeline/prepare_candana_batch.py.
- Pinned layout descriptions: metadata/candana-batch-recipes.json. Adding a new
  layout means adding a source-specific recipe, not editing hundreds of pages.
- Private output: build/candana-batch-review, with index.html, report.json,
  exceptions.json and per-source text/section drafts. These are ignored by Git
  and are not included in the public build.
- An unchanged source, recipe, tool implementation and converter installation
  reuse the existing result after checking every output hash. Edited/missing
  drafts are regenerated. Changed source bytes fail closed.
- One invocation processes at most --limit uncached PDFs. Repeating the command
  advances to additional downloaded PDFs and reuses previous results.
- The whole output directory must be below build/ and carry its private-review
  marker. Existing unmarked directories, traversal and symlinks are refused.
- A dedicated output lock prevents concurrent preparation runs. The collector's
  atomic queue snapshot is read only; network cooldowns are neither reset nor
  bypassed.
- Comparison checks ordered Unicode characters, not merely a bag of characters.
  It does not normalize away ligatures or accents. Exact pinned book recipes
  recognize one unique page-number label at a page edge because MuPDF emits it
  first and Poppler last. Raw extracts remain available unchanged.
- The numbered-book splitter checks the complete source sequence, grouped
  ranges, start/end pages and closing marker. Ordinary numbered lists inside
  teachings do not become sutta headings. Missing, repeated or suffixed source
  numbers are reported, not repaired or relabeled.
- Reflow changes whitespace only. Hyphenated line breaks are flagged rather
  than silently joined or corrected. Every source and every draft remains
  publishable=false even when mechanical checks pass.

## Complete source and disagreement review

The private index now lists every collector entry, not just PDFs processed in the
latest bounded invocation. Downloaded PDFs, missing offers and discovery pages
remain distinct. During a partial pass, unprocessed PDFs are explicitly waiting;
failed source checks never link to an older, apparently valid draft.

- Open http://127.0.0.1:8766/ for the complete source list.
- Open http://127.0.0.1:8766/disagreements.html for all flagged pages, without a
  sample limit. Each source has a full-page comparison with differing words
  highlighted. Highlighting shows a disagreement, not a proposed correction.
- Every processed source links to a byte-identical local copy of its original
  PDF, both unchanged extraction files, and any diagnostic raw-mode extraction.
  PDF links include the actual PDF page number. No PDF is embedded in the text.
- review-list.txt is the complete plain-text list; inventory.json is the complete
  structured inventory. Permission, layout and numbering holds remain visible.
- Character comparisons and word-boundary comparisons are separate. For example,
  fi followed by a newline and lling must not be accepted as equivalent wording
  to filling merely because removing whitespace gives the same characters.
- Canonically equivalent Unicode accents, actual character disagreements,
  word-boundary differences, hyphenated wraps, missing pages and recognized
  pagination movement have separate flags. Recognized pagination is not a newly
  discovered text error. Every reported flag remains available for inspection.
- Raw-mode diagnostics also run on ungranted sources, privately. They never
  remove a permission hold. All outputs remain publishable=false, and no timer
  changes eligible-text manifests, translator defaults or the deployed website.
- Reuse verifies hashes of the PDF copy, comparison page and every other output.
  The tool fingerprint includes the review-output module as well as the converter
  installations, so changed comparison code cannot reuse an obsolete report.

The earlier eight-PDF trial below is retained as historical evidence, not the
current size of the prepared collection.

### Verified complete pass — 2026-11-08

- Three bounded passes prepared all 227 cached PDFs, with 481 existing section
  drafts and zero remaining conversions. No network requests occurred.
- The complete list covers 243 discovered entries: 227 PDFs, 14 discovery pages
  and two missing source offers. All 227 local original-PDF copies match their
  recorded source hashes. Every marked-page anchor exists; local links pass.
- Fourteen sources have layout-character disagreement, ten have independently
  detected word-boundary warnings, and 73 have unreviewed hyphen-wrap warnings.
  Categories overlap. Permission review is still required for 222 PDF offers;
  their private extraction is not permission to distribute the work.
- The review enumerates 3,218 flagged PDF pages. This includes 504 recognized
  pagination movements, 2,282 layout-character flags, 199 layout word-boundary
  flags, 1,433 raw word-boundary flags, 666 raw-character flags and 506 hyphen
  flags. Multiple flags can occur on one page. These are differences between
  tools or layout warnings, not 3,218 established errors in the source texts.
- All 119 source tests pass, with the opt-in secret-hook integration test skipped
  locally. Eight new tests cover complete inventories, final-page differences,
  exact displayed characters, safe HTML, word boundaries, PDF hashes, changed
  review pages and continued permission holds.
- Browser checks verify the complete 243-source index, highlighted differences,
  working original-PDF links and no embedded PDF object. Both the collector and
  bounded offline-preparation timers are active; the preview remains loopback-only.

Next: review the marked Sutta Nipāta reading-order/word-boundary differences and
The Manual's unresolved raw differences before designing their import recipes.
No new text edition, translator preference or public site content was changed by
this private review pass. Audio conversion and author contact remain deferred.

## Eight-PDF trial

The trial used only previously downloaded files: Book Two, Book Three and six
individual PDF offers. Some individual offers are versions of the same text;
eight PDFs does not mean eight distinct suttas.

- Book Two: 208 PDF pages. Both converters agree after accounting for pagination.
  All 479 source numbers partition into 312 draft sections; the author's grouped
  ranges remain grouped, with no invented repetition expansion. Concatenating
  the sections preserves all non-whitespace translation-body characters in
  source order. Two hyphen wraps need review: PDF pages 46 and 71.
- Book Three: 300 PDF pages. Both converters agree after accounting for
  pagination. The full extracted text and a reflowed translation-body draft are
  available, but section generation is held. The source uses 81a/81b and 92a/92b;
  heading 114 omits the word Sutta. These are unsupported heading/numbering
  cases, not evidence that the translation's text is missing. There are also
  32 hyphen wraps to review. Do not map these source labels to website IDs by
  stripping their suffixes.
- Six individual PDFs: 18 pages in total; both converters agree. Their own
  opening notices did not establish the reviewed free-distribution grant, and
  their layouts have no approved splitting recipes. They remain private drafts;
  the permission inside an AN book is not automatically applied to standalone
  editions. Three of these files also contain hyphen wraps.
- Combined trial: 526 PDF pages, 312 section drafts, no network requests and no
  public edition changes. Agreement between converters is not a complete human
  certification of translation accuracy or extraction quality.
- A repeat run on the same eight URLs reused all eight reports and performed
  zero conversions. This is the measured reduction in repeated work; no claim
  about a measured AI-token saving is made.
- Codex visually compared Book Two PDF page 25 with its first draft and checked
  Book Three PDF page 186, confirming the source itself prints 81a and 81b.
  This is a sample review, not page-by-page human approval.
- Regression tests cover numbering, ordinary lists, ranges, misplaced markers,
  extraction order/accents/ligatures, pagination, missing permissions, changed
  sources/recipes/drafts, safe output paths and incremental bounded runs.
- All 67 repository unit tests pass (51 existing plus 16 batch tests). Browser
  checks pass for the eight-source index, all 312 Book Two sections, unchanged
  displayed draft text, inherited font, full desktop width, mobile wrapping and
  absence of embedded PDFs. Local-link validation reports zero broken links.

Exact individual offers used:

- https://www.mindreleased.com/s/AN-101-Kimatthiya-Sutta.pdf
- https://www.mindreleased.com/s/AN-10177-Jussoi-Sutta.pdf
- https://www.mindreleased.com/s/AN-102-Cetankara-Sutta-2bw9.pdf
- https://www.mindreleased.com/s/AN-102-Cetankara-Sutta.pdf
- https://www.mindreleased.com/s/AN-1020-Dutiya-Ariyvsa-Sutta.pdf
- https://www.mindreleased.com/s/AN-1053-hiti-Sutta.pdf

## Run and review

Run python tools/buddhist_canon_pipeline/prepare_candana_batch.py --limit 8.
Use repeated --source-url arguments to rerun an exact subset without advancing
the batch. Adding --source-url never fetches a missing source; it must already
be downloaded by the paced collector.

The trial preview runs locally at http://127.0.0.1:8766/ under the user service
freebuddhism-candana-batch-preview.service. Its Book Two page is:
http://127.0.0.1:8766/sources/8866e8ec00bb8e3342184bd25a90d3dcb4ddc4ab6e71e93a1e70128e81b749ec/index.html#source-1

The existing Book One website preview remains on port 8765. Neither preview
changes the public website. Stop only the batch preview with
systemctl --user stop freebuddhism-candana-batch-preview.service.

## Next bounded work

1. Review Book Two's two hyphen wraps, paragraph boundaries and mapping from
   source ranges to existing website IDs; then prepare a separate edition import.
2. Add explicit handling for Book Three's suffixed and untitled headings without
   guessing equivalence between different numbering systems.
3. Resolve source-specific permission and layout for individual PDFs.
4. If desired, schedule this bounded offline command separately from the network
   collector. This change does not install a new batch-preparation daemon; the
   existing rate-limited collection/extraction timer continues unchanged.

Checkpoint preceding this work: 86333938 on
codex/candana-permitted-editions-20261105. Source pushes and public deployment
remain separate operations.
