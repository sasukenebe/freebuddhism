# Theravāda Buddhist Text Library

Locally readable English Theravāda collection. The repository contains texts
with documented redistribution rights: CC0, verified public domain, or an
explicit source-specific grant. Some works permit free, unaltered distribution
but not modification or sale. Excluded editions appear as metadata only.

## Rights

- Original build code is 0BSD; original documentation and project metadata are
  CC0-1.0.
- Each imported text keeps its own recorded license and source attribution.
- Public-domain status is scoped and evidenced; no repository-wide license
  overrides third-party rights.
- Explicit grants are reviewed for each exact work, not inferred from a free
  download or from another work by the same author. Candana's included books
  retain their free-distribution/no-alteration terms and original PDFs.
- Rights and translation completeness are separate fields. Unknown completeness
  is not represented as complete.
- `metadata/excluded-sources.json` records excluded editions and assets without
  including their text.

## Build and verify

Use Python 3.12, install `requirements.txt`, and provide Poppler's `pdfinfo`
and `pdftotext` commands. Then run
`python tools/buddhist_canon_pipeline/build_deploy_site.py` to create the local
static site in `build/site-root/`. The build does not publish or deploy. It
rebuilds downloads from the allowlist and checks links, text integrity, archive
members, and blocked routes.

Candana extraction review also uses MuPDF's `mutool` for an independent text
comparison. The source-collection timer stages raw text with both engines in
the ignored build cache; those drafts are never automatically published.

Run `python tools/validate_public_tree.py` and
`python -m unittest discover -s tests` before review. The repository file
allowlist records an exact path, content hash, license scope, and rights basis
for each source file. New paths are denied until an explicit entry is reviewed;
directory names and extensions do not grant a license. It lists itself with an
explicit self-reference marker because a file cannot contain its own stable
checksum. The generated site output is checked separately by the build.

Cowell Jātaka source wrappers are not redistributed here. The importer fetches
the pinned upstream revision, verifies every source hash, and compares all 547
generated texts in check-only mode:
`python tools/buddhist_canon_pipeline/import_cowell_jataka.py --check-only`.

Regenerate the excluded-source metadata only from the checked-in classification
and impact records with `python tools/build_excluded_inventory.py`; use
`--check` to detect stale output. After reviewing a change to an already-
allowlisted file, name every reviewed path explicitly, for example:
`python tools/validate_public_tree.py --write --reviewed-files tools/example.py`.
This command cannot add or remove paths. Add a new file's exact license scope,
rights basis, and checksum to the allowlist manually after rights review, then
run the validator.

## Publishing

The [current Candana import checkpoint](docs/tasks/candana-import-expansion-2026-11-07.md)
records imported editions, background draft preparation, verification and remaining
source/permission work. Extra translations and filling previously empty canon books
are tracked separately; edition counts are not counts of complete books.

This repository contains the source used to build the site. The live site is
hosted separately; commits here do not publish changes. Site updates require a
separately reviewed deployment.
