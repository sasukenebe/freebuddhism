# Candana import expansion

Updated: 2026-11-08. The owner requested continued imports at the fastest reasonable pace,
including as much of Candana's work as permissions allow. This is not approval to ignore
permissions, invent missing text, mislabel different numbering systems, or deploy publicly.

## Current result

- The saved collector plan is complete: 241 successful downloads, including 227 PDFs, and
  two explicit 404 results. This finishes the discovered queue, not the whole internet.
- The two missing links are standalone MN 135 and Sn 1.1 offers. Retain their failures;
  do not reset the queue or hammer the publisher with retries.
- Offline preparation now handles the downloaded PDF collection with exact-source hashes,
  two converters, reusable results, plain review pages and exceptions. Collection and
  private draft preparation are separate from importing an edition or public deployment.
- 349 new Candana reader entries have been added to the source collection: all 194 existing
  site units in AN Book Two, and 155 mapped site units from Book Three. Combined with the
  previous 452 Book One entries, Candana supplies 801 reader entries. These are reading
  units, not 801 different books or a certification of the whole canon's completeness.
- New book source files and their explicit free-distribution grants are pinned. The
  original PDF contents are not embedded in readers or packed as whole-book blobs in
  website downloads. Reader text and optional generated exports use the ordinary pipeline.

These are additional Candana editions of existing site texts, not 349 newly filled canon
gaps. The strict build still has 5,907 Sutta IDs with an eligible edition. Completing empty
books across the canon remains a separate source/permission priority alongside Candana.

## Verified checkpoint

- All 75 unit tests pass, including the standalone source-validator package entry point,
  explicit source mappings, retained suffixed labels, grouped cloth sections, changed
  reports, and refusal to let the legacy importer discard the expanded collection.
- Source-policy validation passes with 7,153 eligible editions and 7,159 verified source
  hashes. Completeness remains UNKNOWN; permission checks do not certify accuracy.
- The full site build passes: 16,257 HTML routes, 31 archives and zero broken local links.
  It generated and checked 349 new reader PDFs while reusing 6,804 unchanged PDFs.
  Archive inspection finds no original Candana whole-book PDFs in those 31 archives.
- Browser checks pass for Book Two, suffixed Book Three numbering, the combined cloth
  reader, the last mapped Book Three text, exact displayed text, ordinary font/width,
  generated PDF download, Candana default, explicitly labeled Sujato fallback at a held
  mapping, node-heading navigation and mobile width.
- All 227 downloaded PDF offers now have private batch review results; no source-preparation
  failures remain. A transient timeout on the Thai Manual cleared on a bounded retry.
  Fourteen extractor disagreements remain review exceptions, not approved text imports.
- Expanded local preview: http://127.0.0.1:8767/theravada/tipitaka/site/read.html?collection=anguttara-nikaya#an02-01.
  Its user service is freebuddhism-candana-expanded-preview.service. The older previews on
  ports 8765 and 8766 remain available. None of these is a public deployment.

## Mapping and extraction

The source recipe pins the exact PDF bytes, page count, translation-page range, running
heading and closing marker. Both converters agree on ordered Unicode characters after
accounting for one printed edge page-number label. Whitespace-only reflow retains all
hyphens and never removes a paragraph break when rejoining a hyphenated physical wrap.
It does not expand abbreviated passages or rewrite the author's words.

- Book Two: source pages 25–207 of 208 pages. All 479 source numbers are accounted for.
  The source's 312 sections are assembled into the site's 194 existing reader units;
  source ranges are never split through an indivisible section.
- Book Three: source pages 20–299 of 300 pages. All source section boundaries are parsed,
  including 81a/81b, 92a/92b and the untitled-style Appameyya heading at 114.
  The full source has 169 sections. The first 156 source sections map to 155 site IDs,
  through AN 3.155. Source 97 and 98 are the coarse-jute and fine-Kāsi-cloth parts that
  occur together in the site's AN 3.99; both remain in source order in that reader.
  Exact source labels remain visible in metadata and in the unaltered body headings.
- Thirteen later Book Three source groups remain held: 155, 156, 157–166, and 167–352.
  They contain grouped practices, paired good/evil conduct and passion repetitions whose
  site correspondence is not one text per printed source number. They must not be assigned
  to single site texts using a blanket offset or by stripping suffixes. Full source text
  remains in the private batch review while those grouped mappings are resolved.
- Visual source samples from the previous batch remain recorded. Additional visible checks
  covered Book Two pages 46 and 71, confirming the printed self-explanatory and
  non-interventionist hyphens, and Book Three page 211 at the coarse-cloth boundary.
  Converter agreement and these samples are not an exhaustive human proof of accuracy.
- The extended source/mapping report is metadata/reports/candana-numbered-books-2026-11-07.json.
  Publication validation reconstructs reader bodies from the pinned source and rejects
  changed text, mapping, recipes, permission or a missing/stale report.

## Permissions and remaining works

A full-text scan of all downloaded PDF drafts found the reviewed explicit redistribution
grant in five queue offers: AN Books One, Two and Three, the newly discovered Sutta Nipāta
PDF, and The Manual. The earlier Sutta Nipāta PDF is also pinned with its own grant; the
two Sutta Nipāta PDFs are versions of a work, not two different canonical collections.

Four other keyword hits refer to permission within the translated discourse, not a reuse
grant. Do not treat a character asking permission to ordain or to leave as publication
permission. No broader author-wide grant was found in the saved publisher pages. A free
download or copyright notice alone is not permission to redistribute every standalone PDF.

- Sutta Nipāta: the newly discovered source has 391 PDF pages and 73 Snp-style headings,
  compared with the earlier 364-page source. Its extra sections and numbering need exact
  reconciliation. Ligature/diacritic and reading-order verification remains necessary;
  do not silently patch the text or assume the old extraction report covers the new PDF.
- The Manual: its own grant was detected, but it is not automatically a canonical sutta.
  Prepare its plain text as a separately labeled author resource after checking extraction
  and chapter boundaries; do not insert it into an invented Tipiṭaka location.
- The remaining standalone offers still need source-specific permission. Keep their
  extracted drafts private while maintaining source links and the missing-permission list.
- Audio/video transcription remains a later stage, after written editions and their
  permissions. No author contact, message, purchase or paid transcription occurred.

## Repeatable commands

- Import the checked numbered sources: python tools/buddhist_canon_pipeline/import_candana.py --install-numbered.
- Advance private drafts: python tools/buddhist_canon_pipeline/prepare_candana_batch.py --limit 100.
- Validate source policy: python tools/validate_public_tree.py.
- Run regressions: python -m unittest discover -s tests.
- Build a fresh separate preview: python tools/buddhist_canon_pipeline/build_deploy_site.py --output build/candana-expanded-review-20261107.

The new numbered-book module checks both source files and every mapping before writing
the import. Repeating the import refuses different existing source files/readers. It
adds exact newly generated paths to the allowlist but does not silently refresh hashes
for previously reviewed code or metadata. Review and refresh those named paths separately.

## Background work

The existing rate-limited network collector remains unchanged. The separate
candana-batch-prepare timer invokes a bounded offline batch every five minutes. It uses
no network, honors the output lock, reuses checked results, and never imports into the
eligible edition lists or publishes. Its repository units are under ops/systemd/.
Keep this checkout available while the services point to it.

## Next bounded imports

### Reading-order diagnostic update — 2026-11-08

- The network queue is still complete: 241 downloads and two recorded missing
  offers. All 227 PDF offers have private drafts. The 120-second network
  interval is our conservative setting; saved robots responses did not
  declare Crawl-delay or Request-rate. Earlier bulk requests received 429s.
  Increasing the request rate cannot advance this completed queue, so it is
  unchanged. Future requests must retain robots and Retry-After checks.
- Added a third, raw Poppler extraction for explicitly granted works whose
  layout extraction disagrees with MuPDF. Keep both original extractions,
  the raw candidate and per-page comparisons. This diagnostic does not clear
  layout, mapping, permission or publication holds.
- Sutta Nipāta, 391 pages: layout-mode disagreement on 297 pages becomes zero
  pages with raw-mode comparison after NFC Unicode normalization and ignoring
  whitespace. Nineteen pages differ before NFC, which joins equivalent
  combining accents; no compatibility folding or punctuation repair occurs.
- Manual, 214 pages: 193 layout-mode disagreement pages become 20 remaining
  raw/NFC disagreement pages. Those still need investigation.
- Visible sample: Sutta Nipāta PDF page 25 confirms “filling” in verse 30.
  MuPDF retains that word; raw Poppler emits fi and lling across separate
  physical lines. Character agreement therefore does not prove correct word
  spacing or paragraph layout. Do not publish a blind whitespace reflow.
- Original permission notices, PDF hashes, mappings and installed editions
  are unchanged. No new translation is approved or deployed by this update.
- The existing bounded offline timer is running again. Recipes and detected
  grants are prioritized. Its changed tool fingerprint triggers safe
  revalidation of cached drafts in batches; successful network downloads are
  not repeated. No author contact or paid transcription occurred.
- Completed the changed-tool revalidation of all 227 cached PDFs. Two bounded
  manual runs processed the remaining 121 sources, reusing checked reports
  and making zero network requests. No uncached drafts remain. The main
  layout-versus-MuPDF comparison still records 14 disagreement exceptions;
  the new raw-mode diagnostic does not erase those evidence records.
- Both user timers are active. The collector's last recorded network request
  was November 6 at 14:40 Eastern; subsequent complete-queue ticks do not
  request or download sources. The offline timer is ready for new sources or
  changed review recipes. Completion here means draft preparation, not new
  approved editions or public publication.

1. Resolve Book Three's thirteen grouped source mappings without duplicating continuous
   reading or attaching a combined text to an incorrectly narrow site ID.
2. Verify and map the new Sutta Nipāta source, including extra front/end sections, using
   visible source checks rather than a character-inventory-only test.
3. Prepare The Manual as a distinct noncanonical author resource.
4. Seek an actual grant for standalone texts not covered by the existing book notices.
   Any author email requires a complete draft and separate approval before sending.

Work remains in the existing freebuddhism Candana feature checkout. The separate Buddhism
checkout has pre-existing audit-note changes and was not modified or reorganized here.
Source imports, feature-branch publication, integration into the deployment checkout and
public website deployment remain separate statuses.
