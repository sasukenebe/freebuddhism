# Translation identity and publisher-reference corrections

Status: correction in progress; the November 11 published batch is not cleared for
discourse-identity accuracy. Preserve the original homepage and plain reading layout.
Do not rewrite history or remove review evidence during this correction.

## Confirmed findings

- The source headed AN 10.76, Abhabba Sutta, was attached to AN 10.100 by a
  unique-title fallback. The complete source teaches dependency chains ending in
  birth, aging and death. The existing AN 10.76 translation has those same chains;
  AN 10.100 instead lists ten direct obstacles to perfection. Restore AN 10.76 and
  preserve the publisher's original identifier and exact source snapshot.
- Publisher cross-references such as See also are editorial material, not words of
  the discourse. Retain them separately with a clear label, not in the sutta body.
- The title-only matching rule affected 83 ATI/dhammatalks edition records. That
  count is the audit scope, not a claim that all 83 were wrong. Different editions
  legitimately use different numbering; neither a similar title nor assuming all
  source numbers are identical is a sufficient correction rule.

## Required correction and evidence

- Disable automatic ID reassignment based on unique or similar Pāli titles.
- Review all 83 affected associations against distinctive discourse contents.
  Store the original source ID, the selected site ID, input hashes and comparison
  intervals. Hold unresolved associations outside publication.
- Check the new identification against the selected original canonical TXT, not
  just another generated page. Source-to-output character equality is necessary
  but does not establish discourse identity.
- Preserve full publisher snapshots unchanged. Separate only an explicitly marked
  final See also paragraph; the publisher also uses the same CSS class for real
  subsection headings in DN 1, which must remain in place.
- Preserve references in TXT metadata, a separately labelled reader appendix and
  PDF appendix. Continuous reading should display the sutta body without them.
- Rebuild reader choices, text nodes, continuous-reading metadata, review links,
  downloads and archives. The erroneous edition must not remain associated with
  AN 10.100 in any of these outputs.
- Test wrong-ID rejection, changed review inputs, missing references, subsection
  preservation and exact body/appendix comparisons. Retain all remaining questions
  on the running review list. Publish only the corrected, validated build.

The correction tool plans without writing by default. Applying it retains the old
metadata and exact text files in a private recovery directory before renaming or
removing any individually identified erroneous edition path. Source snapshots and
unrelated editions remain unchanged. Record measured results and deployment here
after the corrections actually complete; local changes are not a live correction.

## Local correction candidate

- All 83 title-only associations have content-comparison decisions: 28 need a
  different canonical target; 55 existing associations are supported. Genuine
  edition renumberings are retained, not flattened to publisher numbering.
- The complete per-source decisions, pinned inputs and comparison intervals are in
  metadata/source-manifests/licensed-identity-review-2026-11-11.json. Public metadata
  stores offsets/hashes, not private working paths or licensed passage quotations.
- The audit and all previous/new references are compiled in
  metadata/reports/licensed-identity-corrections-2026-11-11.json. This is a review of
  the 83 affected associations, not full semantic proofreading of every edition.
- Five dhammatalks sources are held for boundary review: SN 25.1, SN 25.2, SN 25.3,
  SN 25.10 and SN 44.1. Some include additional discourses after a publisher-reference
  paragraph. Retain their whole sources; do not pretend they are single bodies.
- The candidate has 2,685 licensed editions, including 661 with publisher
  references retained separately. Original snapshots are unchanged. Incorrectly
  named local text wrappers were moved/removed only after retaining recovery copies.
- Regression checks cover the known AN 10.76/10.100 error, ambiguous titles,
  content-review mutations, publisher-reference separation and DN 1 subsection
  headings that happen to share the same publisher CSS class.
- A structural scan of all 1,755 original ATI/dhammatalks source regions found
  five pages with multiple explicit discourse headers. Four were already held;
  SN 25.10 also contains all ten discourses and has only a terminal reference
  paragraph. The importer now rejects multiple explicit discourse headers even
  without an intervening reference paragraph. Single headings listing equivalent
  references and ordinary inline citations are not treated as combined bodies.

Remaining review includes the possible partial scope of Nyanaponika's SN 47.14;
the corrected discourse identity does not itself establish full translation coverage.
Build, archive, browser, public URL and deployment results remain pending.

## Completed local verification

- The complete local regression run passed: 247 tests, one optional test skipped.
- Actual AN 10.76, MN 1 and DN 1 HTML, PDF and TXT outputs passed body, rights and
  separate-reference checks. DN 1's real subsection headings remain in its body.
- Every original source snapshot still matches its pre-correction hash: 2,690
  edition records checked, without modifying any publisher snapshot.
- File/rights validation passed with 9,912 eligible editions and 9,931 verified
  source hashes. Generated exclusion metadata is current. The full production
  build and final GitHub checks must run from the committed correction revision.
