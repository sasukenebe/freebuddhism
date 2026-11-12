# Sutta Friends individual readers

Status: 136 individual articles published and technically verified.
Live source: ede22e4b1af1ebb2800f6b90671557c5a42ad04f. This follows the owner's Sutta-first
direction in [CURRENT.md](../../CURRENT.md); Abhidhamma remains deferred until last.

## Coverage and source preservation

- 85 Vimānavatthu and 51 Petavatthu articles fill 133 previously unmatched
  reference identifiers; three already have another translation.
- The pinned reference inventory now has 5,521 identifier-covered units, 101
  unmatched individual identifiers and 142 Milindapañha whole-book alignment cases.
  Counts are edition-specific reference units, not a universal remaining-sutta count.
- The remaining unmatched identifiers are Niddesa 39, Paṭisambhidāmagga 31,
  Buddhavaṃsa 29 and two Apadāna numbering cases.
- Completeness remains UNKNOWN for these new editions. Complete publisher-article
  preservation is not proof of unabridged canonical coverage, translation accuracy
  or full human proofreading.
- Every complete source region, including supplied Pāli, notes, lists and line
  breaks, is compared using a parser and a separate ordered-character lexer.
  Article-only snapshots omit unrelated page navigation and website wrappers.
- Source-page, article-fragment, Pāli-reference, preparation-manifest and text hashes
  remain distinct. Publisher chapter references and flat reference identifiers are
  retained together; this is a chapter/flat concordance, not a title-only reassignment.
- The earlier paragraph-only omissions in Vv 53, Pv 31 and Pv 38 are preserved by
  the new whole-region extraction. The original cached pages remain unchanged.

## Individual permission and distribution boundary

The publisher explicitly permits sharing individual suttas and otherwise retains
copyright. The build conservatively does not infer permission for a combined book
or collection archive. This is not a claim that the publisher expressly prohibits
every aggregation; broader rights have not been established here.

- Original publisher: https://suttafriends.org/copyright/
- Individual HTML, TXT and PDF retain attribution, source, complete permission
  notice and an explicit description of this build's distribution boundary.
- Continuous-reading data omits these editions, without removing other editions
  of the same sutta. Collection navigation and individual text homes remain available.
- Site ZIPs exclude every new HTML/TXT/PDF. Archive generation separately rejects
  an individual-only edition even if its archive flag is accidentally enabled.
- Git source exports omit both individual article snapshots and TXT files through
  committed `.gitattributes` rules. Validation checks each path's effective
  export-ignore attribute, including attempts to override it in a nested rule.
- A full build requires a Git checkout. Downloading a source archive or cloning
  the repository does not expand the publisher's grant. No collection grant, CC0
  dedication or unrestricted commercial reuse is asserted for these works.
- No publisher contact, paid service or account change was used.

The source-export mechanism is documented by Git:
https://git-scm.com/docs/gitattributes#_creating_an_archive
Actual GitHub source-archive exclusion was also checked for the released commit;
a local attribute check alone is not a deployed-archive test.

## Verification and release

Before publication: check the exact-file/rights inventory, complete regression
suite, generated readers/downloads, source export contents, archive exclusions,
continuous-reading exclusions and original homepage. Check the deployed edition
pages and source revision after a separately validated deployment.

The earlier coverage-plan checkpoint passed GitHub run 43210432388. That result
does not validate this later import. Full human proofreading remains unrecorded.

Local source checks pass across 21,718 exact-file entries and 10,067 source hashes.
The regression suite passes 281 tests, with one optional test skipped. A separate
staged-tree ZIP check confirms all 272 individual TXT/article payloads are excluded
and all 21,446 remaining source files are retained. The importer is idempotent:
repeating it adds zero editions and preserves the same article records.

### Completed release checks

- Exact-source GitHub runs 43214741302 and 43216086138 pass: source/rights,
  regressions, full website build, all reader comparisons and history secret checks.
- The normal Free Buddhism-only deployment completed from the pinned source.
  Both public hostnames return HTTP 200. The homepage remains byte-identical;
  JSON gzip and Vary: Accept-Encoding remain enabled. No image or Compose setting
  changed, and retained recovery evidence remains in the production repository.
- Complete build: 10,060 reader versions, 18,169 HTML routes, 31 ZIPs and zero
  broken local links. The production build reuses all 10,060 verified PDFs.
- All 2,821 conditionally licensed readers/TXT downloads match their pinned bodies,
  source regions and complete notices. Existing Candana checks also pass in CI.
- All 408 new public HTML/TXT/PDF files match the actual production build by
  SHA-256. All 31 deployed server ZIPs match the validated files; fresh public
  Vimana/Peta ZIP downloads match as well. No individual-only edition is bundled.
- Live browser checks pass for seven representative editions, including Vv 53,
  Pv 31 and Pv 38: source bodies/notices, canonical links, UTF-8, inherited plain
  font, mobile width, current collection notices and no page-script errors.
- Live combined-reading data omits Sutta Friends while retaining other eligible
  editions. The combined reader and download page explain this boundary.
- GitHub's actual released-source ZIP excludes all 272 individual article/TXT
  payloads. All remaining 21,446 file hashes match the exact-file inventory.

Read the individual editions from:

- https://freebuddhism.org/theravada/tipitaka/sutta/khuddaka-nikaya/vimanavatthu/index.html
- https://freebuddhism.org/theravada/tipitaka/sutta/khuddaka-nikaya/petavatthu/index.html

These results do not certify full human proofreading, unabridged canonical scope
or the semantic identity of every existing edition. The 101 unmatched reference
identifiers and 142 whole-book alignment cases remain separate follow-up work.
