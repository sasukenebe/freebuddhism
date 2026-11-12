# Sutta Piṭaka coverage-first checkpoint

Status: active path recorded; reference inventory implemented and first gap-filling
batch prepared offline. No new edition has been imported or deployed by this batch.
The owner's November 12 direction is recorded in [CURRENT.md](../../CURRENT.md).
Abhidhamma is deferred until last; earlier sources and audit evidence remain intact.

## Reference inventory and current coverage

The reference is the complete `root/pli/ms/sutta` tree of SuttaCentral Bilara at
d26ba0072c9e1f7a238159f583720edacb9f05f9. It contains 5,764 file units across
the four main Nikāyas and the broad existing Khuddaka scope. The inventory pins
every path and Git blob, retains grouped numbers and includes empty books and both
Niddesa subdivisions. It is not a universal sutta count across editions.

- 5,388 reference units have identifier coverage from at least one eligible edition.
  This does not certify complete translations, numbering identity or proofreading.
- 234 reference units have no matching eligible individual-reader identifier:
  Vimānavatthu 83, Petavatthu 50, Niddesa 39, Paṭisambhidāmagga 31,
  Buddhavaṃsa 29 and two Apadāna numbering cases.
- Another 142 Milindapañha units need alignment to an existing whole-book source.
  The two verified public-domain Rhys Davids scans are already available; do not
  report this as 142 missing English translations. Their source hashes are checked.
- Every identifier group in the four main Nikāyas has an eligible reader. Most
  existing edition completeness fields remain UNKNOWN, so this is not a complete
  translation or repetition-expansion certificate.
- COMPLETE describes only the recorded source scope. A complete verse-only Jātaka
  edition does not establish a complete narrative. Netti and Peṭakopadesa retain
  their partial/abbreviated and publisher-proofreading caveats.

The machine-readable [reference inventory](../../metadata/sutta-reference-units.json),
[coverage report](../../metadata/reports/sutta-coverage-current.json) and
[unresolved-coverage CSV](../../metadata/reports/sutta-gaps-current.csv) distinguish
availability, source scope and unverified semantic identity. Reference and input
hashes make regeneration checkable. The report is not limited to existing pages.

Commands:

```sh
python tools/buddhist_canon_pipeline/sutta_coverage.py
python tools/buddhist_canon_pipeline/sutta_coverage.py --check
python tools/buddhist_canon_pipeline/sutta_coverage.py --check --verify-reference PATH_TO_REFERENCE_GIT_CHECKOUT
```

The last command compares the entire inventory against its pinned upstream tree;
it does not advance the reference to a newer revision. No translated passages are
copied into reference metadata. CI checks for stale coverage after source changes.

## First prepared batch: Vimānavatthu and Petavatthu

All 85 Vimānavatthu and 51 Petavatthu individual Sutta Friends articles were
prepared from previously cached sources, without new network requests. They could
fill 133 currently unmatched reference units; three already have another edition.
The preparation is not a publishable import proposal and changes no eligible text.

- Pin the source-manifest SHA-256, every article and Pāli-reference hash, publisher
  chapter/flat identifiers, actual page heading and Pāli title.
- Parse the entire protected article region, preserving every text node in order,
  paragraphs, explicit line breaks, translator notes, list text and included Pāli.
  An independent flat HTML lexer compares all ordered non-whitespace characters.
- The older paragraph-only extraction omitted nonparagraph text in Vv 53 (source
  Vv 5.3), Pv 31 (source Pv 3.6), and Pv 38 (source Pv 4.3). The new preparation
  retains the missing note/legend/list contents. Original cached files are unchanged.
- Unknown elements, hidden text requiring judgment, unbalanced/duplicate regions,
  changed hashes or mismatched headers block preparation instead of omitting text.
- Full human proofreading and translation accuracy are not established by parser
  agreement. The English publisher attributes these texts to Sinhala translations.

Sutta Friends explicitly permits sharing individual suttas, while retaining its
copyright. The current site builder also concatenates editions for continuous
reading and packs collection ZIPs. Do not infer collection-book or archive rights
from the individual-sharing statement. Before publication, either retain individual
readers with safely separated distribution rules or establish the broader scope.
No publisher contact or paid service has been used.

Primary publisher evidence:

- https://suttafriends.org/copyright/
- https://suttafriends.org/vimana-vatthu/
- https://suttafriends.org/vimana-vatthu-numbering/
- https://suttafriends.org/peta-vatthu/

## Other gap tracks

- Niddesa: PTS reports no translation for its Niddesa edition. This is bounded
  publisher evidence, not proof that no English translation exists anywhere.
  Continue checking other primary publishers; do not manufacture a translation.
  https://palitextsociety.org/product/niddesa-3-volume-set/
- Buddhavaṃsa: the Horner translation exists. Its permission is not established
  by the PTS notice covering different works; find exact-edition rights evidence
  and a usable source before import.
  https://palitextsociety.org/product/chronicle-and-basket/
  https://palitextsociety.org/copyright-information/
- Paṭisambhidāmagga: the PTS CC-BY-NC-4.0 grant is established. The retained
  conversion still has 154 reading-order disagreements among 664 pages. Find a
  better source or resolve those disagreements before publishing its text. This
  remains Sutta Piṭaka work despite a source host containing “abhidhamma”.
- Apadāna: unmatched reference IDs tha-ap562/563 name Upavāna and Raṭṭhapāla.
  Existing Walters articles also use those names under other numbers. Neither
  title equality nor a count difference authorizes reassignment; compare contents
  before claiming two missing translations or changing any association.

Next: resolve the individual-reader distribution boundary for the prepared Vv/Pv
batch, validate and publish the permitted forms, then continue the other gap tracks.
Preserve the homepage, all existing editions, complete notices and recovery evidence.

## Checkpoint verification

- The pinned inventory matches the complete upstream Git tree at the recorded
  revision; regeneration reproduces the checked-in JSON and CSV exactly.
- All 136 cached articles pass the whole-region ordered-character comparison,
  pinned manifest/source hashes, publisher-heading and Pāli-title checks.
- The local suite passes 273 tests, with one optional test skipped. This includes
  eight coverage tests and five source-preparation tests; failures for truncated
  HTML, omitted reference subdivisions, changed hashes and unsafe paths are covered.
- These are source/preparation checks, not new reader publication, a fresh live
  deployment check or full human proofreading. No eligible text or homepage changed.
