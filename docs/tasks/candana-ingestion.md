# Candana translations and default editions

Updated: 2026-11-07

The owner requests the largest permission-supported import of Bhikkhu Candana's
translations, with Candana preferred wherever available. Explicit permission is
an acceptable rights basis; CC0 is not required. Other translators remain
available, and existing explicit reader preferences remain respected.

## Current state and newest owner instructions

The owner requested continued imports, not just more extraction drafts.
See [the November 7 import expansion](candana-import-expansion-2026-11-07.md) for the
new 349 reader entries, completed collector queue and exact remaining book mappings.
The earlier counts and holds below describe their dated checkpoints.

- Work is prepared on the feature branch below; no Candana release has been deployed.
  The owner authorized committing and pushing this work, then testing reusable
  batch preparation on more downloaded texts. That is not public deployment approval.
- Text first: seek native editable text before converting PDFs. Use plain,
  reflowable text in the existing font and page layout. Source PDFs are evidence,
  not embedded readers or packaged whole-book blobs. Generate optional reader
  PDF exports from the checked text.
- Continuous-reading section headings must link to their canonical node pages,
  with translation choices and sources there. This supersedes the earlier
  request for unlinked headings; Contents anchors still scroll within the page.
- Collect written sources with a persistent, rate-limited timer. Audio
  transcription remains deferred until the written inventory is exhausted.
- Validate the converter against visible PDF pages before applying it to the
  rest. Do not represent engine agreement as an exhaustive human certification.

### Completed preparation

- Two exact, permission-cleared source PDFs are pinned for reproducible evidence.
  AN Book 1 supplies 627 numbered passages mapped to 452 reader units. The three
  source numbers 330–332 were absent from the previous Sujato ledger and retain
  their explicit Candana numbers; cross-edition equivalence remains unreviewed.
- Poppler and MuPDF agree on every ordered non-whitespace character across all
  175 translation pages (36–210). Codex visually compared pages 36, 39, 50, 87,
  100 and 210 with their extracted text. The comparison report pins every reader-body
  hash; the publication checks reject a missing/stale review.
- Visual review caught a mid-page subgroup heading before 235. The splitter
  now assigns it to 235, not 234. A regression test covers that boundary.
- Physical PDF line wraps/indentation are removed without changing any
  non-whitespace character. Paragraphs and repetitions remain intact. Seven
  reviewed compound spellings (including Self-Awakened and well-developed)
  rejoin line-break whitespace while retaining the author's hyphens. Unfamiliar
  hyphenated line breaks stop conversion for review rather than guessing.
- Sutta Nipāta remains held for ligature/diacritic extraction quality. Do not
  make its unchecked extraction a default or run OCR correction without review.
  MuPDF now yields an improved 364-page draft at
  build/candana-audit/sutta-nipata-mupdf-candidate.txt. Both engines have the same
  character inventory on every page, but that does not verify reading order.
  Page 20 was visually checked. Only 65 Snp-style headings were detected; the
  full text boundaries and verse order still need reconciliation before import.

### Verification and local review

- 51 unit tests pass, including persistent cooldowns, Retry-After, deferred
  redirects, robots rules, access-denial halts, no-fetch completed queues,
  conversion boundaries and unchanged reader text.
- Source-rights validation passes: 6,804 text sources and four source assets
  have verified hashes. No source PDF is embedded in the Candana readers or
  included as a whole-book blob in the new website archives.
- The full local build passes: 15,908 HTML routes, 31 archives, zero broken
  local links. It generates 452 new reader PDFs from checked text and reuses
  the existing 6,352 exports.
- Browser checks pass for Candana's initial default, saved Sujato preferences,
  missing-edition fallback, heading-to-node navigation, translation choice,
  unchanged typography, full desktop width, generated PDF exports and mobile
  width.
- Preview: http://127.0.0.1:8765/theravada/tipitaka/site/read.html?collection=anguttara-nikaya#an01-06
  Final static output: build/candana-final-review. Nothing from this task is deployed.
  The local-only preview runs as freebuddhism-candana-preview.service and can be
  stopped with systemctl --user stop freebuddhism-candana-preview.service.
  The final build and browser checks pass after the compound-word fixes.
  An archive inspection confirms no original Candana whole-book PDFs are packed.
  The owner requested a feature-branch checkpoint before the next batch-preparation
  changes. Public deployment remains separate from committing and pushing source.

### Source-collection timer

Repository units: ops/systemd/candana-source-collect.service and .timer.
Installed as user g with lingering enabled so collection survives logout.
The collector runs one bounded request per invocation, at least 120 seconds
apart. Redirects are deferred to a later invocation. It checks robots.txt,
honors longer crawl delays/request rates, and saves cooldowns before I/O.
HTTP 429 honors Retry-After plus exponential backoff starting at 15 minutes;
401/403 halt for manual review. No identity rotation or access bypass.

State: build/candana-audit/queue.json. Downloaded material stays in that ignored
cache; the worker never imports into tracked manifests or publishes the site.
For PDFs it stages both Poppler and MuPDF raw-text candidates, with page/character
inventory differences marked for review. It can convert already-cached PDFs
without making network requests during cooldown. None of these drafts is an
approved edition; reading order, boundaries and permission still gate promotion.
Initial discovery: 217 PDF links, no TXT/DOCX/EPUB/ODT/RTF links on the three
cached author pages; 221 initial jobs include the pages and sitemap. Native text
and discovery pages have priority over PDFs. Previously cached downloads are
reused, and both successful and missing results are retained.
The first live collector requests fetched robots.txt and sitemap.xml with HTTP
200. The sitemap's legacy HTTP URLs are upgraded to HTTPS on the same approved
host; ten additional author pages were added without repeating the sitemap
download. That expanded the initial queue to 231 jobs; later page discovery can
add more. Use the status command for current counts. No audio is requested.
The service currently runs code from this checkout; keep this branch available
while it is collecting, or update the unit before moving/removing the checkout.

Commands:
- python tools/buddhist_canon_pipeline/candana_queue.py status
- systemctl --user status candana-source-collect.timer
- journalctl --user -u candana-source-collect.service -n 20 --no-pager
- systemctl --user stop candana-source-collect.timer

Do not reset the queue or bypass a saved cooldown when resuming. Recheck later
downloads, especially AN Books 2 and 3, for their own permission and extraction
quality before promoting any source. Contacting the author is not authorized;
draft and obtain approval before sending any message.

### Reusable batch preparation

The existing source and Book One work was committed and pushed as 86333938.
See [batch preparation and eight-PDF findings](candana-batch-preparation.md) for
the new bounded offline command, exact trial sources, local review preview and
remaining gates. The trial produced 312 Book Two section drafts; Book Three and
the six individual PDF offers remain held for their reported exceptions.
Unchanged results are reused, with no network requests or automatic publication.

## Work chunks

1. Audit the author's current downloads, including the individual Sutta PDFs,
   Aṅguttara books 1–3 and Sutta Nipāta. Pin exact source bytes and record the
   permission applying to each work. A book's permission is not automatically
   permission for every other PDF or recording by the author.
2. Extend the default-deny publication checks to reviewed, explicit grants.
   Retain each work's own conditions, attribution and notices. Do not label
   these works CC0, public domain or freely modifiable.
3. Import original permitted PDFs unchanged. Publish plain-text readers only
   where extraction and text boundaries can be verified without inventing,
   shortening or expanding the translation. Keep original PDFs available.
4. Prefer Candana in collection readers and edition lists wherever a cleared
   local edition exists; retain chosen defaults and individual overrides.
   Fall back visibly to eligible alternatives where Candana is absent.
5. Test rights rejection, exact hashes, text integrity, edition selection,
   fallback, downloads and source links. Run the full publication checks.

## Findings and limits

- The current MN 1 PDF is 93 pages and expands repeated passages abbreviated
  in the imported Sujato edition. Its own notice says copyright; a redistribution
  grant for that standalone work has not yet been established.
- Sutta Nipāta and Aṅguttara Book 1 contain an explicit grant to distribute
  the work free of charge, without altering its contents, in any medium.
- Sutta Nipāta's PDF extraction has broken ligatures/diacritics. Do not silently
  present that extraction as a checked text or use generated prose to repair it.
- No audio transcription or publication of recordings is authorized by a
  permission found only inside an unrelated written work. Prefer existing
  written editions; record remaining permission and transcription work.
- Preserve the site's plain font, width and spacing. This is an edition import,
  not a typography redesign.

## Resume

Branch: codex/candana-permitted-editions-20261105.
Start with the source audit and this checklist; record completed counts,
verification and any unresolved source-specific limits before handing off.
