# Candana works and next imports

The owner requests an inventory of the actual written works Candana offers, followed
by their permission-supported ingestion. Counts of downloaded PDFs are not enough.
Keep the original homepage and plain reading layout. Audio transcription stays deferred.

## Current result

The November 9 live check finds 874 Candana reader entries: 452 AN Book One,
194 Book Two, 155 Book Three and all 73 Sutta Nipāta entries. All live HTML bodies
match their pinned TXT sources. Publication and validation are recorded with source
01c2b29d in the separate deployment repository. The newer reader checker is source
tooling at 3204d177, not a different content release.

The bounded publisher inventory has 229 written offers: 227 downloaded PDFs and two
recorded missing links. All 227 downloaded file hashes are distinct. Repeated references
can therefore represent different editions or revisions, not byte-identical copies.
The older 364-page Sutta Nipāta PDF remains a separately checked historical manifest
source outside that queue; it is neither discarded nor counted as a second work.

- Standalone offers resolve to 204 explicit reference groups. Fifteen references already
  have an imported Candana book edition; the standalone versions remain separate and
  are not assumed equivalent. The other 189 groups have no live Candana reader:
  37 MN, 10 DN, 67 SN, 67 AN, four Udāna, two Theragāthā, one Dhammapada reference
  and one Milindapañha reference. This is a worklist, not 189 approved import mappings.
- Seven reference groups have two different PDF offers: AN 10.2, AN 5.79, AN 7.49,
  MN 121, SN 12.25, SN 12.67 and Snp 1.1. Preserve both sources until their edition
  relationship is checked. Do not silently discard a revision.
- The three AN books and Sutta Nipāta are separate book offers; their contained
  readers are not added to a standalone-file count as though these were equal units.
- The Manual has 11 language editions under one publisher work. The English edition's
  grant is not automatically applied to other translators' language editions. A
  dissertation remains a separate author resource, not an invented canonical text.
- The two unresolved offer references are the recorded missing MN 135 and Uraga URLs.
  Other working offers exist for those names; the missing URLs are not automatically
  equated to them from filenames. Do not retry the known failures on every tick.
- AN VIII, Suttas 41–50 is recognized from the publisher's explicit Roman-numeral
  label and printed heading. It remains one source group pending a checked splitter,
  not ten invented text bodies. Four publisher references do not exactly match an
  existing site ID: AN 8.23–24, Dhp 2.21–23, Mil 7.8.7 and SN 51.81. Verify their
  scope before generating routes or altering the site's numbering.

This accounts for the existing bounded queue, not every work online. There is no
defensible whole-Candana percentage until unresolved references, grouped passages,
editions and discovery limits have been resolved. Do not manufacture one from PDF counts.

## Repeatable command

Run python tools/buddhist_canon_pipeline/candana_corpus.py --live. It reads the existing
collector and draft cache, checks recorded publisher-page/PDF/draft hashes, extracts
references from actual publisher labels and PDF openings, and reconciles imported
readers. The optional --live makes one read-only request to this project's public
reading index. No publisher request, new extraction or model call is required.

Output is private under build/candana-corpus: inventory.json, next-imports.json,
inventory.txt and a plain index.html with original/converted links. Repeating the
command updates only its marked generated directory. It never edits eligible manifests,
source text, deployment settings, actual human findings or queue cooldowns.

All pages of every available cached extraction are searched for permission-keyword
leads, including pages beyond the older first-ten-page grant check. Every lead retains
its PDF page, text hash and excerpt. Fourteen offers contain such words; nine are not
already granted. A word such as permission in a sutta's dialogue is not a reuse grant.
No keyword match changes rights or approves publication.

## Next ingestion work

1. Resolve the 13 held source groups in the already permission-cleared AN Book Three.
   A separate worker should propose exact source-to-site correspondences and preserve
   grouped passages. Do not extend the earlier piecewise numbering map by assumption.
   Source labels: 155 through 166, and 167–352. Accept each independently; an unresolved
   group must not hold back the independently checked groups.
2. Work through next-imports.json, starting with MN 1, DN 1, DN 2, DN 16, MN 10,
   SN 22.59 and SN 56.11. The sources and extracted drafts already exist. Verify
   exact-source permission and source boundaries; do not reconvert every PDF manually.
   Explicit redistribution permission is acceptable; CC0 is not required.
3. Keep the Manual's 20 number-placement cases and detached opening letters visible.
   It belongs in a clearly labeled author-resource area, not a guessed sutta node.
4. After a checked source-specific recipe, generate the whole compatible batch,
   compare every reader automatically, spot-check changed layouts, and release only
   the accepted entries. Preserve source wording and all unrelated translations.

No supplier/author message or paid service is authorized by this worklist. If permission
cannot be established from published evidence, prepare one consolidated clarification
request for separate owner approval rather than fabricating coverage or sending it.

## Abhidhamma disposition

The isolated Dhammasaṅgaṇī handoff was read and its unchanged evidence verified on
November 9: all 101 inventoried files verify and all 18 preservation tests pass.
These are preservation results, not print-accuracy results. The retained visual report
identifies systemic OCR errors, and the later preface reports an opening Mātikā omission
in the 1900 edition. No complete book, canonical map or publication is approved.

Park the work and retain the original evidence. Do not pursue the alternative PTS
edition, fresh OCR or another Abhidhamma pilot in this batch. Further worker effort
is directed to Candana. The alternative edition's permission scope is not resolved here.
