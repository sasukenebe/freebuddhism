# Repeatable local conversion review

Use this method for the next Candana source and for a local reviewer. A text-layer
comparison, a visual layout check, a translation assessment and permission to reuse
are separate results. Do not call a sampled visual check a complete proofread.

## Method adopted from the returned review

The owner supplied an external Sutta Nipāta conversion review on 2026-11-09.
Its report SHA-256 is 89ab9fdcb2926c4c0a900f6ca2a145768822e8550b2839392a985db1c16c95db.
The original report remains with the owner's downloaded review files; this document
records its method and findings, not a new license for that report.

- Freeze the exact PDF and raw UTF-8 extraction. Verify their SHA-256 values before
  comparing anything. Never replace a source merely because a newer filename exists.
- Extract every PDF page using PyMuPDF and Poppler pdftotext -raw. Compare ordered
  non-whitespace characters, both before and after Unicode NFC normalization.
  NFC joins canonically equivalent accent representations; do not use NFKC,
  character inventories, punctuation replacement or deletion of unexplained numbers.
  PyMuPDF shares the MuPDF engine with mutool; Poppler is the independent engine.
- Check every source interval's hash, contiguous character boundaries, order and
  PDF-file page range. The intervals must reconstruct the entire raw text exactly.
- Parse the complete HTML and every individual sutta HTML. Compare whitespace-split
  source words and punctuation against each raw interval, not just non-space characters.
  Only explicitly marked editorial pagination labels are excluded from source comparison.
- Verify all generated-file hashes. Check individual raw files too; reviewing a
  complete-book upload does not automatically verify the separately deployed files.
- Render original pages and HTML for layout checks: verse/refrain boundaries,
  multi-line index titles, page references, footnotes, diacritics and page folios.
  Source images have no text-layer oracle; identify the HTML as text-only.
- Keep an explicit page coverage list. Report machine results, visual samples,
  source-specific layout rules, disagreements and unexamined pages separately.
  Never approve reuse, numbering correspondence or a full human proofread by inference.

## Local command

The optional audit environment needs PyMuPDF, Poppler and Python. The current local
run uses PyMuPDF 1.26.6; it is not a runtime dependency of the website build.
The command does not modify its inputs and refuses to overwrite an existing report.

```sh
python tools/buddhist_canon_pipeline/verify_candana_conversion.py \
  --pdf REVIEW/original.pdf --text REVIEW/converted.txt \
  --metadata REVIEW/conversion.json --output NEW-REPORT.json
```

For another downloaded book without a published HTML manifest, omit --metadata.
This performs the complete per-page extraction comparison and retains all disagreement
pages, but makes no claim about that book's HTML, intervals or permission.

A future local reviewer should run this command first, inspect every disagreement and
all changed layout structures, then return PDF page numbers, source/converted passages,
specific defects and the exact visually inspected page list. No review daemon may
silently turn a machine PASS into permission or a publication approval.

## Returned Sutta Nipāta result

- Reported external automatic coverage: 391/391 pages pass both NFC comparisons;
  372 match exactly before NFC. The other 19 pages differ only in canonical composition:
  7, 9, 59, 60, 61, 171, 173, 189, 243, 244, 245, 250, 252, 258, 259, 263, 280, 386, 387.
  All 80 intervals and uploaded hashes passed. Individual published sutta files
  and the publisher's currently posted PDF were not independently checked.
- Reported visual samples: 1, 7, 8, 9, 11, 13, 17, 19, 22, 23, 33, 49, 78, 79,
  81, 147, 185, 220, 264, 300, 322, 350, 385, 386, 391. Pages 19 and 386 also
  received higher-resolution checks. The other 366 pages remain visually unchecked.
  The referenced page-coverage TSV was not supplied with the downloaded report;
  retain this explicit list rather than inventing its contents.
- Corrections: index title/page pairs on PDF pages 386–388, deliberate Snake refrain
  breaks on pages 19–22, explicit pagination styling for 73 geometrically identified
  footer numbers, and a text-only notice for omitted artwork. The raw files are unchanged.
- The layout recipe is tied to the exact source. Footer candidates were independently
  located at y > 560 points with x between 185 and 205 and right edge below 215,
  and must equal their PDF-file page number. They are not arbitrary body numerals.
  Every remaining source character and every index reference survives in HTML.
- The Snake rule covers its 17 repeated refrains; page-start continuations already
  start a paragraph. It does not claim all authored breaks elsewhere are settled.
- The source introduction says 71 suttas while the source has 73 numbered intervals.
  Preserve both source features. Do not silently reconcile them or repair the index's
  printed page references to match a different edition.

Full human proofreading, all other verse-layout decisions and canonical mapping remain
unapproved. Continue collecting and preparing permitted sources while retaining those limits.
