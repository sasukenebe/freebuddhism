# Translation identity and publisher-reference corrections

Status: correction implemented, published and technically verified; full human
proofreading remains unapproved. The original homepage and plain reading layout
are unchanged. No history rewrite or review-evidence removal occurred.

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
The release checks below do not close those remaining content-review questions.

## Completed local verification

- The complete local regression run passed: 247 tests, one optional test skipped.
- Actual AN 10.76, MN 1 and DN 1 HTML, PDF and TXT outputs passed body, rights and
  separate-reference checks. DN 1's real subsection headings remain in its body.
- Every original source snapshot still matches its pre-correction hash: 2,690
  edition records checked, without modifying any publisher snapshot.
- File/rights validation passed with 9,912 eligible editions and 9,931 verified
  source hashes. Generated exclusion metadata is current. The full production
  build and final GitHub checks must run from the committed correction revision.

## Published correction and final verification

- Deployed source: bb323f3406c9386a84a258ece0c568f91fe1f600. GitHub's exact-revision
  file validation, secret scan, regressions, complete clean build and reader checks
  passed: https://github.com/sasukenebe/freebuddhism/actions/runs/43156267856.
  The clean environment ran 236 tests with ten optional checks skipped, plus ten
  separate secret-hook tests. Local preparation includes additional source fixtures.
- The independent build and deployment build both passed with 9,924 reader
  versions, 18,169 HTML routes, 31 archives and zero broken local links.
- All 2,685 licensed HTML bodies, TXT downloads and rights notices passed their
  comparison checks. All 83 reviewed associations are under the correct generated
  text nodes and all five held sources are absent from the continuous-reading
  index. All 875 individual Candana readers also match their saved source texts.
- The corrected AN 10.76 reader, PDF and TXT match the validated public bytes.
  The old AN 10.100 edition URL returns HTTP 404, not the wrong discourse.
- Live browser checks pass for 2,685 original/converted review pairs, the corrected
  AN 10.76 identification, separate publisher references, continuous-reader text,
  UTF-8, plain fonts, mobile wrapping, larger linked headings and keyboard
  expansion, with no page-script errors. Both public hostnames return HTTP 200.
- The homepage is byte-identical to its pre-correction build. Reading-index gzip
  compression remains enabled. No other website or shared proxy was changed.
- Review and every remaining held-source question:
  https://freebuddhism.org/review/licensed-2026-11-11/.
- Corrected text:
  https://freebuddhism.org/theravada/tipitaka/sutta/anguttara-nikaya/an10-76/an10-76-thanissaro-dhammatalks.html.

This technical release does not grant full semantic or human proofreading approval
to every imported translation. The reviewed identity decisions cover the identified
83 title-remapped associations; the wider corpus retains its recorded review limits.
