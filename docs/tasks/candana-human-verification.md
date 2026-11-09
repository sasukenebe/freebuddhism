# Candana human verification

Updated: 2026-11-08. Written-source ingestion is not complete. Automatic draft
preparation, a source import, human checking and public deployment are separate.
This checkpoint supplements [the import plan](candana-import-expansion-2026-11-07.md)
and [private batch preparation](candana-batch-preparation.md); it does not change
permissions or approve publication.

## Current scope

- The discovered queue contains 227 downloaded PDFs, 14 discovery pages and two
  missing offers. Completing that queue is not proof that every work on the
  internet has been found.
- There are 801 Candana reading entries imported into the source collection.
  This is not 801 books, a full-page human proofread, or a public-site release.
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
- Neither work has been automatically imported, made the default or deployed.

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

The existing private batch command generates human-review.html, human-review.txt
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

1. Review Sutta Nipāta 1.1 and representative verse, paragraph and book boundaries;
   retain any disagreements instead of treating converter agreement as proof.
2. Verify the Manual's 20 number-placement cases visually, then implement a
   source-specific footnote/layout recipe without silently dropping markers.
3. Resolve the 13 held AN groups individually; continue other cleared sources
   while permission-dependent offers remain visible in the checklist.
4. Import only the source units whose applicable checks are resolved, validate
   the complete source/build and stage a separate release for public review.

## Verification of this checkpoint

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
