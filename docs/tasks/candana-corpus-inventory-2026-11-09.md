# Candana works and next imports

The owner requests an inventory of the actual written works Candana offers, followed
by their permission-supported ingestion. Counts of downloaded PDFs are not enough.
Keep the original homepage and plain reading layout. Audio transcription stays deferred.

For human updates, say "Candana texts not yet on our website", not "standalone
missing references". Say "downloaded copies" only when the distinction matters;
do not make the reader decode storage or internal numbering terminology.

## Current result

The latest November 9 live check finds 875 Candana reader entries: 452 AN Book One,
194 Book Two, 156 Book Three and all 73 Sutta Nipāta entries. All 875 live HTML
bodies match their pinned TXT sources. The follow-up deploys source 00a943e1 at
production pin 7b13d45, adding AN 3.156 to the preceding 874-reader release.
Publication and validation are recorded in the separate deployment repository.
Later source-only permission-policy and review notes do not change the live pin.

### AN Book Three follow-up

The separate mapping review is finished and its saved input hashes, 27 output files
and 23 tests verify. Twelve of the thirteen held source groups have supported scopes;
one remains unresolved. These are twelve source bodies, not 27 new independent suttas.

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

The remaining eleven supported groups need whole-group edition handling: source 156
covers six existing site references, and sources 157–166 each cover a conduct pair.
Do not copy one body under multiple single-sutta labels, silently split it, or invent
a combined canonical ID. Source 164's awkward printed wording remains unchanged.
Source 167–352 stays unresolved: its sixteen lettered subjects have not been matched
exactly to the site's seventeen-subject group. These are source-scope issues, not a
reason to rerun PDF conversion.

### Whole-group reader implementation checkpoints

Primary review read all eleven remaining source bodies and the 26 candidate
Sujato bodies, and checked source boundary images at PDF pages 284, 286, 289 and
293. The sealed proposal still verifies all 27 artifacts without changing its
inputs. Accept the proposed passage scopes, not word-for-word translation
equivalence or a complete human proofread. The original source 164 really prints
"or to be full of longing" in its positive paragraph; preserve and flag it rather
than silently correcting the translator.

The existing importer, node pages and continuous reader each assume one edition
body belongs to one canonical text ID. Adding the same complete source body to
every covered ID would publish six copies of source 156 and two copies of each
conduct pair. Keep canonical references separate from the source's edition units.

1. Edition metadata: add one source-group identity per intact body, an ordered
   canonical_ids list of existing IDs, source label/title, exact body hash and
   original PDF interval. Source 156 covers AN 3.157 through 3.162; source 157
   covers 3.163/164, continuing in pairs through source 166 at 3.181/182.
   These are eleven bodies covering 26 references. Do not invent range IDs in the
   canonical ledger. Reject overlapping group memberships, changed bodies,
   missing references, duplicates, reordered parts and the held 167–352 group.
2. Ordinary readers and text pages: generate each group once, clearly list its
   covered references, and link that same edition from every covered text page.
   Preserve other translators, source wording, ordinary fonts and existing layout.
   Count eleven edition bodies separately from 26 references with that edition.
3. Continuous reader: plan the chosen editions before rendering; place each
   selected group at its first covered reference and display its body only once.
   Preserve direct links for every covered text. A saved individual Sujato choice
   must not be silently applied to other group members. If other members still
   select the intact Candana group, show it once with its full coverage and show
   the individually selected different edition separately. Do not split the
   source body or silently discard the override. Test translator changes, saved
   choices, anchor navigation, fallback and stale asynchronous responses.
4. Release: compare every added body with its source hash; exercise every covered
   node, the continuous reading order, mixed translator choices and mobile/keyboard
   use. Verify the existing readers, homepage and public review files remain
   unchanged. Source 167–352 remains held regardless of the earlier groups' result.

These checkpoints specify the next implementation; they do not mark the eleven
groups as published or resolve the final group's numbering/subject-list disagreement.

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

1. Finish whole-group edition support for eleven checked AN Book Three groups:
   source 156 and the ten conduct pairs at 157–166. The primary review accepts
   source 155 at AN 3.156 independently. Keep 167–352 unresolved; do not extend
   the earlier piecewise numbering map by assumption or duplicate a grouped body.
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
