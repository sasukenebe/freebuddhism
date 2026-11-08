# Theravāda Buddhist Text Library

Public source for [freebuddhism.org](https://freebuddhism.org/), a locally readable
English Theravāda collection. The repository contains texts
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
and `pdftotext` commands, fontconfig and the Noto Sans regular/bold fonts. Then run
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

## Repository safety checks

GitHub Actions runs the exact-file/rights validator, exclusion-metadata check, unit
tests, complete-history secret scan and full static-site build on pushes and pull
requests. The build also checks archives and local links. Checks do not deploy the site.
The workflow uses read-only repository access, pinned action revisions, no saved Git
credentials and no production secrets. Repository administrators must separately make
the two checks required on main; adding a workflow does not enable branch protection.

Before pushing, run `python3 tools/check_secrets.py`. It downloads Gitleaks 8.30.1
from its official release on first use, verifies the pinned SHA-256 and caches it
under ignored build output. Later runs recheck the archive and need no download.
The helper supports Linux x86-64, scans all locally available Git refs, rejects
shallow history and redacts findings. It cannot scan remote branches not fetched
locally or prove that every possible secret is absent.

To run that scan automatically before every local push, first check for an existing
hook setup, then enable the tracked hook with `git config --local core.hooksPath .githooks`.
Do not overwrite another hook arrangement. A failed or unavailable scan blocks the
push. Local hooks are optional and bypassable; they complement, not replace, GitHub
checks and administrator-managed merge rules.

The .gitignore excludes common secret-file names. Sanitized .env example, sample
and template names remain available, but must never contain real credentials.
Git ignores do not remove tracked files or old commits, and they do not exempt a
file from the exact-file publication validator. If a real secret is exposed,
revoke or rotate it first; deleting the file or adding an ignore pattern is not enough.

The [public repository re-review](docs/reviews/public-repository-re-review-2026-11-08.md)
records the audit fixes, verification and remaining administrator actions.

## Publishing

The [current Candana import checkpoint](docs/tasks/candana-import-expansion-2026-11-07.md)
records imported editions, background draft preparation, verification and remaining
source/permission work. Extra translations and filling previously empty canon books
are tracked separately; edition counts are not counts of complete books.

This repository contains the source used to build the site. The live site is
hosted separately; commits here do not publish changes. Site updates require a
separately reviewed deployment.
