# Candana human verification

November 12 continuation: use the
[persistent per-passage review register](../candana-processing-review.md) for
current Candana work. It includes the existing converted passages and standalone
offers, freezes their original inputs outside build/, and preserves separate
revision-bound findings with reviewer provenance and separate human approval. The owner-confirmed website permission
now covers the standalone sutta question under no-alteration, no-monetization
and no-advertising conditions. The older generated WAIT_PERMISSION tasks below
describe the prior exact-book-only evidence; they must not be treated as a
revocation of that new permission or as proof that other processing holds cleared.

Updated: 2026-11-09. Written-source ingestion is not complete. Automatic draft
preparation, a source import, human checking and public deployment are separate.
This checkpoint supplements [the import plan](candana-import-expansion-2026-11-07.md)
and [private batch preparation](candana-batch-preparation.md); it does not change
permissions or approve a new canonical edition. The separately authorized public
Sutta Nipāta conversion draft is recorded in
[the external-review release](../reviews/candana-snp-external-review-2026-11-09.md).

## Compare original and converted text

Open the local review at http://127.0.0.1:8766/. Each downloaded PDF appears once,
with two choices: **Original PDF** and **Converted text**. Books with prepared
sections show one whole-book PDF link, then individual converted texts with plain
PDF page references. Repeated links to the same original have been removed. Start with
Sutta Nipāta, which has 73 separately accessible suttas. This is not just one sample.

- Open the original and converted version beside each other. Compare the same
  passage for missing words, wrong characters, order, paragraph and verse breaks.
- Converted HTML wraps to the browser width. Paragraph/stanza gaps remain; physical
  PDF-width line breaks are treated as whitespace. No words, punctuation, page
  numbers or notes are removed. Raw extractions remain unchanged for inspection.
- The owner reported garbled quotations such as `â€œ`. The saved text contained
  correct Unicode quotation marks; the previous plain-text preview omitted a
  charset. The loopback preview now explicitly serves text as UTF-8, with no-store
  caching. This is a preview correction, not a rewritten translation.
- The old human-review.html address also opens the simple comparison list.
  Permission, numbering, source inventory and converter evidence are separate
  technical pages, available under **Technical details**. They are not repeated
  between the reader and the text being checked.
- The review is private and drafts remain unapproved. No public site, translator
  preference, imported edition or actual human decision is changed by this display fix.

Verification of the 2026-11-09 preview fix:

- The project environment runs 136 tests: 135 pass and one opt-in secret-hook test
  is skipped. The system Python lacks ReportLab; use the project's prepared
  environment for the complete suite rather than treating that missing dependency
  as a converter failure.
- Browser checks confirm 227 original/converted source pairs, 73 separate Sutta
  Nipāta sutta pairs, correct quotations on both HTML and older plain-text URLs,
  keyboard links, natural desktop wrapping and no mobile horizontal overflow.
- All 2,731 generated source-output hashes verify. All 1,012 generated reading
  views retain their source's non-whitespace characters, including quotations and
  numbers; these views include whole-book and duplicate navigation views, not
  1,012 distinct suttas. All 27,743 checked internal links and anchors resolve.
- Original PDF and raw-text hashes, the imported Candana manifest and the actual
  human-decision ledger are unchanged. No source-content approval is inferred.

For local preview recovery, run
`python3 tools/buddhist_canon_pipeline/serve_candana_review.py` from this checkout.
It binds only 127.0.0.1:8766 and refuses an unmarked or non-build directory.
Do not return to a bare `python -m http.server` command that omits text encoding.

## Current scope

The November 9 import update prepares 874 ordinary Candana readers: 801 AN entries
plus all 73 Sutta Nipāta entries. The new source recipe verifies their exact Snp
references and source text automatically. The older preparation notes below remain
historical; see [the current import/release checkpoint](candana-snp-import-2026-11-09.md)
for deployment status. Full human proofreading is still not claimed.

The reusable check_candana_readers.py command compares every prepared or public
Candana reader with its pinned TXT and supplies original/converted links for three
layout samples per book. This supplements the full source-PDF audit; it does not
clear the Manual's 20 number-placement cases, 13 held AN groups or ungranted sources.

- The discovered queue contains 227 downloaded PDFs, 14 discovery pages and two
  missing offers. Completing that queue is not proof that every work on the
  internet has been found.
- There are 874 Candana reading entries imported into the source collection.
  This is not 874 books, a full-page human proofread, or proof of a public-site release.
  This checklist does not roll back those earlier imports or invent new results.
- Continue permitted written sources first. Audio transcription remains a later
  stage; no audio conversion, author message or paid service is authorized here.

## What was advanced

- The exact 391-page Sutta Nipāta PDF now has 73 separately reviewable sutta
  source intervals. Front matter, five book dividers and back matter are separate,
  giving 80 intervals altogether. Concatenating them reproduces every character
  of the unchanged MuPDF extraction, including wraps and page numbers.
- These are proposed source intervals, not approved website text bodies. Check
  verse order, paragraph/word boundaries, accents, printed page numbers and the
  correspondence with site IDs before importing. The last interval covers source
  5.19 on PDF pages 381–385; back matter begins on PDF page 386. The back index
  contains page references that need reconciliation with the actual body.
- All 20 remaining English Manual raw-character disagreements classify as moved
  numeric tokens with the other compared characters unchanged after canonical
  Unicode normalization and ignoring whitespace. They appear to concern footnote
  markers, but this is a diagnostic hypothesis, not visual proof or a correction.
  Keep every number and note, and verify where it attaches in the PDF.
- Neither work has been automatically imported, made the default or deployed as
  an approved canonical reader. The public Sutta Nipāta conversion review is a
  separate owner-authorized draft publication, not an automated import.

## Human roles

These are different checks, not a requirement to find or hire five people.
One person may cover several roles if they can verify the relevant evidence.

- Proofreader: the owner or another person fluent in the source language.
  Compare the original PDF with the extracted section. Confirm all wording and
  verse order, word breaks, Pāli diacritics, paragraph boundaries and footnotes.
  Start with Sutta Nipāta 1.1, PDF pages 19–22, then expand the review. English
  comparison does not require retranslating Pāli. A fluent-language reviewer is
  needed for a non-English source rather than guessing from its appearance.
- Text-reference reviewer: a reader familiar with the canon's reference systems.
  Confirm Sutta Nipāta source/site correspondence and the 13 held AN Book Three
  groups. Do not apply a blanket offset, remove source suffixes, expand omitted
  repetitions or split grouped texts merely to make numbering match.
- Rights reviewer: the owner supplies or confirms the exact permission evidence
  for each source still lacking it. A book's grant is not automatically applied
  to a standalone edition or translation of The Manual. Publisher clarification
  may be necessary; draft any message for separate approval before sending it.
- Release owner: accept the reviewed scope and attribution before a separate
  import/release. The Manual belongs in a labeled author-resource section, not
  an invented canonical location. A human finding alone does not run a release.
- Pipeline maintainer: implement pinned layouts, diagnose extraction failures,
  preserve hashes, run tests and prepare import candidates. This is automation
  work, not something the owner must implement personally.

## One accumulating checklist

The existing private batch command generates technical-checks.html, human-review.txt
and human-review.json beside its complete inventory and marked differences.
Every check has a stable ID, exact source hash, role, question, state and links
to the original PDF and relevant text. All applicable flagged pages are listed.
Recognized pagination movement is retained as evidence but is not automatically
presented as an author error or an extra proofreading defect.

- Work with a detected grant is prioritized. Sources still needing permission
  have a rights task; their proofreading task waits for permission rather than
  asking the owner to spend time approving unusable editions first.
- Existing imported-reader counts are shown separately from pending source
  checks. AN Book Three's 13 unresolved groups remain individually listed.
- Missing offers remain visible as maintainer work. Do not repeatedly retry 404s
  or speed up the network collector to advance a completed queue.
- No human result has been fabricated. Actual findings are stored separately in
  the private human-decisions.json ledger; the timer never replaces that file.
  Generated checklists can therefore be refreshed without losing human reports.
- A decision must identify the check and exact source SHA-256, reviewer, date,
  outcome, scope and evidence. Partial review cannot confirm the full check.
  Changed or unmatched source records remain preserved for reconciliation.
- A recorded decision changes only the checklist's reported state. It never
  clears source rights, mapping, import validation or deployment gates by itself.

## Returning a human finding

Send the check ID, PDF page or exact interval, what you compared, what matched
or differed, reviewer and scope. For example, report a sample as a sample; do not
say an entire book was verified after checking one section. Do not edit generated
HTML or overwrite the raw text with a proposed correction. Preserve the original
wording and attach any proposed extraction repair as separate review evidence.

## Next work

### Returned external review and local rerun — 2026-11-09

The owner supplied a report comparing every Sutta Nipāta PDF page against the raw
text. It reports 391/391 automatic text-layer matches, all 80 intervals and hashes,
and 25 visually sampled pages, leaving 366 pages visually unchecked. Its supplied
evidence does not include the referenced page-coverage TSV or an executed test script.
The method, exact sample list and report hash are recorded in
[local conversion testing](../reviews/candana-local-conversion-testing.md).

The local repeatable audit reproduces the 391-page result with PyMuPDF 1.26.6 and
Poppler, and additionally checks the 73 separate sutta HTML/TXT files. Exact matching
before NFC succeeds on 372 pages; the same 19 canonical-composition pages require
NFC. All 80 intervals, generated hashes and source word boundaries pass. Layout
revision 2 addresses the index, Snake refrains, proven folios and text-only labeling.
It does not claim complete visual approval or silently approve the other verse breaks.

The same audit was applied to the next permitted work, the 214-page English Manual.
Both comparators retain the same 20 flagged number-placement pages. They are not
erased by normalization or treated as permission to delete or relocate notes.
The generated per-page records are metadata/reports/candana-snp-conversion-2026-11-09.json
and metadata/reports/candana-manual-conversion-2026-11-09.json. These machine records
do not overwrite the private human-decision ledger or invent human approvals.

The Manual's raw extraction now also has 14 exact source intervals: 12 chapters,
front matter and dedication/end matter. Concatenating them reproduces every byte
of the 214-page MuPDF extraction. Open its local Converted text, then Choose a
chapter. Detached opening letters and the 20 number-placement cases are unresolved;
these are private preparation outputs, not new approved translations or sutta IDs.

The local method was also run against the exact AN Books One, Two and Three:
212, 208 and 300 PDF pages respectively. Both PyMuPDF and raw Poppler agree with
each complete MuPDF text after NFC on every page, with no disagreement pages.
Per-page reports are metadata/reports/candana-an-book1-conversion-2026-11-09.json,
candana-an-book2-conversion-2026-11-09.json and candana-an-book3-conversion-2026-11-09.json.
That brings the full-source machine coverage to all 1,325 pages of the five
explicitly granted queue works; only the Manual retains its 20 flagged pages.
These runs do not change the existing 801 imported entries or the 13 held AN groups.

All 227 cached PDF drafts have finished the changed-tool pass with zero new
network requests and no source-preparation failures. The new Manual intervals,
all saved output hashes and local links are checked separately. Both timers
and the UTF-8 loopback review remain active. The existing 14 layout-engine
disagreement records are retained; a successful raw-mode diagnostic does not erase them.

1. Review Sutta Nipāta 1.1 and representative verse, paragraph and book boundaries;
   retain any disagreements instead of treating converter agreement as proof.
2. Verify the Manual's 20 number-placement cases visually, then implement a
   source-specific footnote/layout recipe without silently dropping markers.
3. Resolve the 13 held AN groups individually; continue other cleared sources
   while permission-dependent offers remain visible in the checklist.
4. Import only the source units whose applicable checks are resolved, validate
   the complete source/build and stage a separate release for public review.

## Original checkpoint verification, 2026-11-08

- All 130 unit tests pass; the opt-in secret-hook integration is skipped locally.
  Tests cover lossless section partitioning, changed source boundaries, numeric
  diagnostics, source-bound check IDs, partial-review limits, stale records,
  safe HTML and preserving actual decisions across a cached timer rerun.
- Browser checks pass for the roles/checklist, all 80 Sutta Nipāta intervals,
  exact displayed text for 1.1, links to the original PDF, all 13 AN mapping
  checks, all 20 Manual number-placement pages, ordinary font, mobile width and
  the absence of embedded PDF objects.
- Visible assistant samples of Manual PDF pages 20 and 29 confirm the presence
  of superscript footnote markers 1 and 4/5 respectively. This supports the
  diagnostic interpretation on those pages only. It is not a full-page human
  approval of every section or every unresolved case.
- All 227 cached sources have completed the changed-tool pass. The complete
  inventory still lists 243 discovered offers. No network request, new public
  edition, translator-default change or website deployment occurred.
- The generated checklist contains 469 checks: 14 reference checks, 228
  proofreading checks, 222 rights checks, four maintainer tasks and one author-
  resource placement decision. Roles overlap by source; this is not 469 books.
  Of these, 222 proofreading checks wait for permission. No actual human
  decision has been recorded or invented.
- The network collector, bounded private updater and loopback review service
  remain active. The saved network queue is complete and keeps its 120-second
  pacing/backoff policy; it does not refetch successful downloads on idle ticks.
