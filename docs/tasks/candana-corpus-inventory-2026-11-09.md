# Candana works and next imports

The owner requests an inventory of the actual written works Candana offers, followed
by their permission-supported ingestion. Counts of downloaded PDFs are not enough.
Keep the original homepage and plain reading layout. Audio transcription stays deferred.

For human updates, say "Candana texts not yet on our website", not "standalone
missing references". Say "downloaded copies" only when the distinction matters;
do not make the reader decode storage or internal numbering terminology.

## Current result

The November 11 release has 875 individual Candana reader entries: 452 AN Book One,
194 Book Two, 156 Book Three and all 73 Sutta Nipāta entries. It also publishes twelve
intact Book Three group passages. All 875 individual HTML bodies match their pinned
TXT sources. Grouped bodies and shared-passage behavior are checked separately.
Live content source: 4e222f56; content deployment pin: 0732bcc; configuration follow-up:
eea021a. Publication, browser verification and rollback points are recorded in the
separate deployment repository. Source-only follow-up notes do not change the live
content pin. The homepage and unrelated translations remain unchanged.

### AN Book Three follow-up

As of November 10, every one of the book's 169 extracted source sections is now
represented locally: 156 individual reader entries plus 12 intact group passages.
The group passages cover 27 existing site references: 26 individual entries and
the single existing AN 3.183–352 group. They are additional editions, not 27 new
independent suttas. All twelve passages are published by the November 11 release.

One source group fits the existing reader model: Candana's source 155, Modes of
Practice – Part 1, corresponds to site AN 3.156. Both complete texts teach the three
practices and the four foundations of mindfulness. The original PDF starts this
source on page 284; its closing sentence appears on page 286 before source 156.
The reviewed import preserves that sentence and every source character. Its body
SHA-256 is f80281a815c59dc42c6eff8c204a0534a4fd6b86ec8d08c84b291d0bebc88f51.
This source has the already verified exact-book sharing grant; no new permission
is inferred from another work.

The follow-up now publishes 875 Candana readers: 452 AN Book One, 194 Book Two,
156 Book Three and 73 Sutta Nipāta. The complete public exact-text check passes
for all 875. The existing 874 readers, other translations, source PDFs, raw
extractions and homepage are unchanged. No additional individual-PDF permission
is established by this exact-book import.

### Rolling human-review list

This is the running list of converted Candana material that still needs a human
decision. The private queue at `build/candana-final-review-20261110/index.html`
puts each original PDF beside its extracted text and review evidence. Nothing in
that queue is public unless marked live below.

- Book Three: all 169 source sections are represented. Its 156 individual readers
  and twelve additional intact passages are live; compare the
  final source, printed 167–352, with the existing AN 3.183–352 page. Its 16
  subject headings and the other edition's 17 do not match one-to-one. Also review
  source 164's printed wording and the continuous-reader behavior.
  Original final passage: https://freebuddhism.org/theravada/tipitaka/translations/en/candana/books/an-book3.pdf#page=295
  Converted final passage: https://freebuddhism.org/theravada/tipitaka/sutta/anguttara-nikaya/candana-groups/an3-183-352/an3-183-352-candana.html
- Standalone texts: 196 downloaded PDFs cover 190 not-yet-live Candana reference
  groups. Automated comparison covers 1,728 pages, but these are still private
  drafts. The additional AN 4.171 PDF has no extractor character mismatch and all
  three pages were visually checked. The earlier batch's flags remain review
  prompts. Resolve permission scope, reference and
  layout flags before importing any. There are 14 extractor-difference flags,
  225 layout flags, 73 possible line-wrap-hyphen flags, 10 word-boundary flags,
  and 222 permission leads. These counts overlap and are review prompts, not
  confirmed errors or approvals.
- Sutta Nipāta: 73 texts are live. All 391 PDF pages passed automated text
  comparison, but only 25 pages were visually sampled. Finish visual review and
  confirm its numbering against the original.
- English Manual: its own permission covers that English work. It is a separate
  author resource, not a sutta; review 20 footnote-number placements and decide
  its final presentation. The other language editions are not covered by this
  notice.
- Dissertation: one separate PDF; confirm author, permission, and extraction.
- Dhammasaṅgaṇī: conversion is stopped. The 1900 scan has serious recognition
  errors and is not ready to import.

Earlier background check, November 10 at 15:55 Eastern: all 195 saved text
comparisons were reused; zero new conversions, publisher requests, or model
calls. Later that evening, the paced collector added and fetched one newly found
PDF. Current collector state: 244 URLs total; 242 collected (228 PDFs and 14
publisher pages); two offers remain missing. This bounded list still does not
prove that every Candana work online has been found.

New find, November 10: “Catukka Sañcetanā Sutta” (AN 4.171) appeared without a
download link on the publisher's Pāli Suttas index, but its official Squarespace
file host has a matching Candana PDF. The paced collector downloaded it; its
SHA-256 is `5bc3eb8b95469186e701c51cbb1d5052f76c4dd4728d3c01621cbeadd463e495`.
The PDF is 3 pages. Poppler and MuPDF extractions agree on every page after
whitespace normalization; all three page images were visually inspected. The
PDF prints a 2022 copyright notice but no reuse grant in its extracted text.
The site already has the canonical AN 4.171 page with Sujato's edition, so this
would be an additional translation on that page, not a new canonical sutta.
Keep it private until the permission scope is resolved.

- Index: https://www.mindreleased.com/pali-suttas
- PDF: https://static1.squarespace.com/static/578af02af5e231074e974635/t/62e54c29ea7101690954f258/1659194412183/AN%2B4.171%2B-%2BCatukka%2BSa%C3%B1cetana%2BSutta.pdf
- Local original: `build/candana-audit/78c31923bc789c5163e38694dbc69ee9af217e84eeb7329bba911ddfb423496a.pdf`
- Local text: `build/candana-audit/78c31923bc789c5163e38694dbc69ee9af217e84eeb7329bba911ddfb423496a.poppler.txt`

Sources 156–166 are eleven intact passages: source 156 covers six individual site
references, and sources 157–166 each cover a conduct pair. They are each stored once;
no passage is copied under several single-sutta labels or split into invented texts.
Source 164's awkward printed wording remains unchanged.

The final source passage, printed as 167–352, is now stored once under the site's
existing AN 3.183–352 group. This is a whole-chapter placement only. Its 16 lettered
subject headings do not map one-to-one to the other translation's 17 topic names,
and the printed number ranges differ. The internal topics are not mapped or matched
individually; keep that discrepancy on the final review list. The source passage is
preserved complete and unchanged.

### Whole-group reader import status

Primary review read the 12 grouped source bodies and compared their proposed
references against the local site texts. The saved Book Three proposal still
verifies its original 27 artifacts without changing its inputs. The final group
addition uses only the broad AN 3.183–352 reference; it does not claim internal
word-for-word or topic-by-topic correspondence. This is not a complete human
proofread. The original source 164 really prints "or to be full of longing" in its
positive paragraph; preserve and flag it rather than silently correcting it.

The importer, text pages, and continuous reader now support one intact source
passage covering multiple existing sutta pages. Each body is stored and generated
once; every covered page links to it. The continuous reader displays it once at
the first selected reference while retaining separate per-text translation choices.
No combined canonical IDs were created.

The November 11 release publishes all 12 intact group passages alongside the 875
individual Candana readers. The complete site, including other translators' additions,
has 9,929 reader versions, 18,174 sitemap HTML routes, 31 archives and no broken local
links. All 875 individual bodies match their pinned text; grouped-body preservation
and per-text preference behavior are checked separately. All 12 passages use the exact
Book Three reuse notice. That grant is not applied to separately published PDFs.

The full suite passes in a temporary environment with the pinned project
dependencies: 177 tests run, 176 passed and one optional integration test was
skipped. The homepage-preservation check confirms the original copy is unchanged.

For final review, compare the original PDF pages 295–299 with the converted passage
and confirm that displaying the whole passage under AN 3.183–352 is acceptable
despite the printed-number and topic-count differences. Do not split it or infer
individual topic matches. Also inspect the reader and continuous view, confirm a
per-text translation override does not alter other selections, and verify the
homepage and unrelated readers remain unchanged. Preserve source 164's printed
"or to be full of longing"; do not silently edit it.

### Candidate review batches collected November 10

The private final review queue is at
`build/candana-final-review-20261110/index.html`. It links the original PDFs,
extracted text, saved comparisons, proposed site locations, and known questions
in one place. It is local-only and is not part of the public website. Review it
after the remaining discovery/import work is finished.

The latest automatic pass reused all 227 saved PDF reports without another
download and prepared 481 passage drafts. Its overlapping flags are 14 extractor
differences, 225 layout checks, 73 hyphen-wrap checks, 10 word-boundary checks,
and 222 permission checks. These are review prompts, not confirmed text errors.

The owner says the Sutta Nipāta permission should apply to Candana's other
suttas too. The saved notice itself says “this work,” and the publisher's Pāli
Suttas page calls its list a selection without stating a general text-reuse
grant. This one scope question is recorded in the final checklist; individual
PDFs remain private until that interpretation is settled. This does not affect
the exact Book Three reuse notice used for the 12 locally prepared group passages.

- Dīgha and Majjhima: 47 reference groups and 48 PDF offers. Forty-six groups
  have straightforward proposed mappings; the two MN 121 PDF offers remain
  separate editions. The missing MN 135 offer stays recorded as missing. One
  MN 1 page-1 spacing difference needs visual confirmation. Every offer remains
  marked as needing permission review.
- Saṃyutta and remaining Aṅguttara: 134 reference groups and 139 PDF offers.
  The batch reports 105 clear reference matches and 34 scope/identification
  questions, including opening-page labels the automatic check did not recognize
  and SN 51.81, which has no matching existing site text. Five groups have more
  than one offer and remain separate. Forty-six pages across 24 PDFs are flagged
  for visual inspection of line-wrap hyphens. AN 8.12 and SN 12.2 also have
  publisher filenames that do not match the printed reference. All need
  permission review.
- Other small collections: eight offers cover Udāna (four), Theragāthā (two),
  Dhammapada (one grouped passage), and Milindapañha (one). Six have proposed
  one-to-one mappings. Dhammapada 2.21–23 remains grouped pending alignment to
  three site entries; Udāna 1.10 needs its opening-page reference confirmed.
  All need permission review.
- The existing Sutta Nipāta book conversion covers all 73 suttas. Automated
  comparison passed all 391 PDF pages, and all 80 source intervals and hashes
  were checked. Twenty-five pages were visually sampled, not all 391. Its saved
  review records the index layout, stanza breaks, footer labels, and omitted
  image-only artwork; the latest revision addresses those presentation findings.
  Remaining review is full visual coverage and the exact numbering correspondence.
- The English Manual is a separate author resource, not a sutta. Its own grant
  covers that English work only. Twenty pages have flagged footnote-number
  placement differences; 21 of 214 pages were visually checked. Its other ten
  language editions are not included by that grant.
- One doctoral-dissertation PDF is listed separately, not as a sutta. Its exact
  author identity, reuse permission, and extraction/layout still need review.
- The 1900 Dhammasaṅgaṇī extraction remains stopped because page images show
  serious recognition errors. It is not a complete book and is not ready to add.
- The publisher's Sutta Nipāta page currently lists six audio parts. These are
  not extra written translations and are outside the text counts. Keep them for
  a separate later audio inventory/transcription stage; no audio reuse right is
  recorded here.

The 48 + 139 + 8 candidate offers are saved review material, not 195 newly
approved translations. The known queue covers 189 reference groups but is a
bounded discovery, not proof that every work Candana has made is accounted for.
The final queue must keep rights, mapping, and text-accuracy decisions separate.
Do not publish a standalone offer merely because it is freely downloadable or
because another Candana book has a reuse notice.

The bounded publisher inventory has 229 written offers: 227 downloaded PDFs and two
recorded missing links. All 227 downloaded file hashes are distinct. Repeated references
can therefore represent different editions or revisions, not byte-identical copies.
The older 364-page Sutta Nipāta PDF remains a separately checked historical manifest
source outside that queue; it is neither discarded nor counted as a second work.

The separate rate-limited source collector currently records 243 URLs: 241 collected
and two missing. Of the collected URLs, 227 are PDFs and 14 are publisher-site pages
used to find or describe works. Therefore 241 collected URLs does not mean 241
distinct translation offers. The numbered-book inventory reconciles the 227 PDFs
and two missing offers above. The collector timer remains enabled at one request
per 120 seconds, and there is no automatic publication.

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

The follow-up whole-PDF pass is complete for all 195 downloaded files representing
the 189 pending texts or small groups. All 1,725 pages pass ordered-character
comparison with PyMuPDF and raw Poppler after NFC. No image-only page or comparison
failure was reported. The only word-boundary disagreement is the MN 1 heading
described below. A repeated pass reuses all 195 results and performs zero new
conversions. These are extraction checks, not a complete visual proofread, approved
text-to-site mapping, or redistribution permission.

The new seven regression tests cover bounded progress, no repeated conversion,
changed inputs/tools/results, disagreements, failed checks, unsafe paths and output
ownership. The complete suite runs 173 methods: 172 pass and one optional integration
is skipped. Browser checks verify all 195 original/converted link pairs, readable
plain-language labels, ordinary fonts and mobile wrapping. The private permission
request is a draft only; no message was sent. At that download-check checkpoint
the live site had 874 Candana entries; the later AN 3.156 release above adds one.
The homepage is unchanged.

## Next ingestion work

### Automatic checks for the next texts

The command python tools/buddhist_canon_pipeline/check_candana_missing.py --limit 25
continues independent whole-PDF comparisons for the 195 downloaded files representing
the 189 pending texts or small text groups. It makes no publisher request, model call,
or website change. Existing comparisons are reused only after their input/output
hashes and tool versions still match. An interrupted or changed result cannot silently
become a successful old check. Failed checks and every disagreement stay visible.

The installed candana-text-check user timer runs a bounded batch of at most 25
new checks, then waits one minute after completion. This is local processing only;
the network collector retains its existing 120-second pacing and backoff. A lock
prevents overlapping check workers. Use systemctl --user stop candana-text-check.timer
to stop only this new check timer; stopping it does not erase results.

The optional audit Python environment needs PyMuPDF and the existing Poppler tools.
Set CANDANA_AUDIT_PYTHON in the user's untracked text-checks.env under
.config/freebuddhism to select that environment. The published units contain no
machine-specific Python path, account detail or credential. A missing dependency
fails the job; it must not be reported as a text PASS.

Results remain private in build/candana-text-checks: a plain index.html with
Original PDF / Converted text links, per-text comparison.json and result.json,
and an aggregate report.json. No draft becomes an eligible public edition automatically.

The first seven complete texts cover 330 PDF pages: MN 1 (93), DN 1 (67), DN 2
(49), DN 16 (88), MN 10 (24), SN 22.59 (4) and SN 56.11 (5). Every page passes
ordered-character comparison with PyMuPDF and raw Poppler after NFC. Word boundaries
are checked separately, not hidden by ignoring whitespace. MN 1 page 1 has one
spacing disagreement: raw Poppler joins A. to Puthujjana; MuPDF retains the space
visible in the source image. The other six texts have no word-boundary disagreement.
Both original extractions remain unchanged. No complete human proofread is claimed.

Assistant image samples: MN 1 pages 1, 47 and 93; DN 16 pages 1, 44 and 88.
Opening/closing text, the sampled repeated MN 1 passages and DN 16 verse are visible
and retained. DN 16's verse-line structure must be preserved in any later reader recipe.
These six images are not evidence of visual coverage of all 330 pages.

The seven exact PDFs show copyright notices, but this check did not find their own
redistribution grant. Searching the downloaded publisher pages and indexed publisher
permission statements did not establish a broader grant. The earlier AN/Snp book
notices are not silently applied to different PDFs. A publisher-wide grant is
acceptable when its actual scope is recorded; permission need not be printed inside
every PDF, and CC0 is not required. A book notice granting reuse of "this work"
does not, by itself, establish explicit coverage of every other separately published
file. Prepare one consolidated request if clarification is needed; no message has
been sent.

1. At final review, check the Book Three original and published readers described above.
   All source sections are represented, but the final source's internal topic mapping
   remains deliberately unresolved.
2. Next is the 195 downloaded standalone-PDF offer batch for 189 text groups. The
   PDFs, extracted text, and automated comparisons are already prepared; do not spend
   time converting them again. Resolve the one permission-scope question and the
   listed reference/layout flags, then bulk-import only the approved sources.
3. Keep the English Manual's 20 number-placement cases and detached opening letters
   visible. It is a separate author resource, not a guessed sutta node.
4. Preserve the existing Sutta Nipāta text and its review findings; full visual
   proofreading and numbering correspondence remain open. After a checked
   source-specific recipe, compare every generated reader automatically, spot-check
   changed layouts, and preserve all unrelated translations.

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
