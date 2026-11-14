# Persistent Candana processing review

The offline processing-register command preserves one stable review entry for
each converted source passage and each downloaded standalone sutta offer. It
includes existing editions, not only the newest batch. Shared source passages
remain single entries with all their associated sutta IDs; they are not split
into invented individual translations.

The register, permission evidence, original PDFs, raw extractions and attributed
review findings live in stable private storage outside the public checkout and
outside build/. Do not put private correspondence into source control. The
destination is local persistent storage, not an off-machine backup.

## Generate and resume

Use an explicit private destination and an owner-confirmed permission record:

```sh
python tools/buddhist_canon_pipeline/candana_processing_register.py \
  --destination "$CANDANA_REVIEW_DIR" \
  --permission "$CANDANA_PERMISSION_FILE"
```

The existing collected-source queue and dual-engine draft cache must be present.
The command makes no network requests, modifies no source translations, and
does not publish. It checks the cached PDF and extraction hashes, independently
compares page characters and word boundaries, and freezes inputs by content hash.
It does not run OCR, join hyphenated words, remove notes or pagination, or repair
the author's wording. Abhidhamma and separate author resources are not this batch.

- index.html links the original PDFs, preserved text, processing questions and
  recorded findings. Each entries/ID.html address remains stable.
- register.json retains every source passage and every processing revision.
  The ID depends on source bytes and the source passage selector, not the site's
  potentially corrected sutta number. A changed source PDF gets a new ID.
- artifacts/ keeps original PDFs, both standalone extractions, prior conversion
  audits and attributed existing text files. Frozen artifacts are never replaced
  with different bytes. Removed inputs remain in the register/history.
- staged-editions.json lists conservative whole-document ingestion candidates.
  Their full headings, copyright, notes and pagination remain included. This is
  not yet the sutta-only reader body or approval for a public release.
- reviews.json is the separate attributed finding ledger. Ordinary regeneration
  never writes an existing ledger. Old-revision findings remain visible but do
  not count as reviews of changed processing output.

An edition is held if source numbers conflict, grouping is unresolved, a site
reference is absent, translator attribution is unconfirmed, engines disagree,
word boundaries differ, or a hyphen/layout question remains. No title-only or
constant-offset remapping is accepted. Even an unflagged draft retains explicit
layout, boundary, identity and full-proofreading review questions.

## Record a review

A supplied finding identifies event_id, entry_id, revision_sha256, reviewer,
reviewer_kind, date, check, outcome, scope and evidence. Dates use YYYY-MM-DD.
Record the actual reviewer and review method in the private ledger; the command
validates its supported reviewer_kind values. Use check extraction, layout,
identity or translation; outcome MATCH, ISSUE or PARTIAL. Explain exactly which
pages and passages were examined in scope. MATCH concerns that scope, not the
whole text. Preserve accurate provenance; do not invent independent reviewers or
count an automated finding as human approval.

Append one supplied JSON event using the same command plus --append-review FILE.
The command rejects unknown entries/revisions, duplicate conflicting event IDs
and incomplete attribution. Add a new event to correct an earlier finding; do
not overwrite old events. Findings do not automatically clear publication gates.

For each text compare missing/repeated/reordered wording, word breaks, accents,
punctuation, paragraph/verse order, footnote attachments and source/site identity.
Do not rewrite, modernize or expand the translation. Distinguish source wording
from an extraction error, and report sampling as sampling.

## Permission and distribution

Owner-supplied correspondence and the owner's reported confirmation establish
the new website-permission record. This work does not claim independent email
retrieval. Preserve all three conditions: no content changes, free of charge
with no monetization now or in future, and no use of the content for advertising.

Do not infer a general public-repository or third-party archive grant from a
permission naming freebuddhism.org. Keep original book grants and notices as
separate evidence; do not rewrite their historical terms. Public-source delivery
and website deployment need their own checked distribution boundary. Local
staging does not change an existing reader, download, archive or live site.

## Build website-only readers

The separate candana-website.json source manifest contains provenance, permission
conditions, source/text hashes, exact header/body boundaries and content-identity
evidence. It contains no translation body, original PDF or private correspondence.
The first reviewed recipe is AN 4.171. It retains both section headings and all
three closing Sadhu words; its original printed heading and copyright remain in
the edition details. Two visually checked page breaks become paragraph breaks.
No wording, notes, punctuation or repetitions are repaired or removed.

New prose recipes may explicitly distinguish continued paragraphs from true
paragraph boundaries at physical page breaks. In partition metadata,
page_break_joins lists reviewed continuation breaks and page_break_paragraphs
lists reviewed paragraph breaks; 1 means the break after source page 1. Every
actual boundary must appear exactly once, with sorted unique integer indexes.
Unknown keys, omitted classifications, overlaps and out-of-range indexes fail.
The explicit recipe also requires the exact discourse reference as one standalone
line inside the preserved original heading. Content-identity evidence is still
required; the printed number alone is insufficient.

Continuation reflow removes only physical wrapping and page-margin whitespace;
the ordered words and punctuation must match both extractors and the pinned
source/output hashes. Older recipes retain their exact previous output and
notices. This does not infer paragraph boundaries elsewhere, join hyphenated
words or preserve deliberately lineated verse. Sources needing those operations
remain held until their layout has its own checked representation.

Stage the exact original PDF explicitly, then enable website editions:

```sh
python tools/buddhist_canon_pipeline/candana_website.py \
  --stage-pdf "$CANDANA_SOURCE_PDF"
python tools/buddhist_canon_pipeline/build_deploy_site.py \
  --include-website-editions --output build/candana-website-site-preview
python tools/buddhist_canon_pipeline/candana_website.py \
  --check-site build/candana-website-site-preview
```

Staging uses the ignored build/candana-website-inputs cache. It never fetches a
source, changes the collection queue, or writes a body into the public source
tree. A changed PDF, extraction, word boundary, reader partition, identity-review
input or notice fails verification. An enabled build requires every listed input;
it never silently falls back to a build without these editions.

The default public-source build does not enable website-only editions. Release
operators must stage the pinned inputs and explicitly use the flag after checking
the source revision. release.json records exactly which optional website editions
and source/body/download hashes were included. A successful default CI build is
not evidence that the optional editions were built or deployed.

Website-only readers use the ordinary plain reading template, with HTML/TXT/PDF
downloads retaining all three permission conditions. The current build policy
excludes them from combined readers and collection/source archives. This is the
project's conservative distribution boundary, not an assertion that the author
provided an individual-sutta-only license. Original publisher PDFs remain external
source links; no wider archive or Git-publication permission is inferred.

Before release, run the full site/link/archive build, the website-only checker,
normal reader regressions and deployed-page checks. Human proofreading and
translation-accuracy review remain separately recorded. Building a local preview
does not publish anything or authorize pushing source.
