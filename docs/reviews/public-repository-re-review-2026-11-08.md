# Public repository re-review

Date: 2026-11-08. Scope: the November 4 public-source audit and its follow-up.
This review branch starts from the existing Candana import branch at ea4c2054.
It does not merge main, change imported texts or deploy the public website.

## Audit dispositions

- Contact address: the owner explicitly confirmed on November 8 that the existing
  ProtonMail address may remain public. No replacement or removal is needed.
- Secret-file exclusions: common environment, private-key and credential-file names
  are now ignored. Deliberately sanitized .env examples remain permitted. This does
  not delete tracked files, clear history or relax exact-file publication checks.
- README: identifies the repository as the public source for freebuddhism.org,
  while keeping source commits and separately reviewed website deployment distinct.
- Automated checks: a push/pull-request workflow runs source/rights validation,
  exclusion-metadata comparison, tests, full-history Gitleaks and the complete site
  build with archive/link checks. It has read-only permissions, pinned action revisions
  and a checksum-pinned scanner, no retained Git credentials and no deployment step
  or production secrets. The runner explicitly installs the PDF conversion tools,
  fontconfig and Noto fonts rather than depending on a developer computer's setup.
- Local prevention: the optional tracked pre-push hook runs the same pinned scanner.
  Its first use needs network access to the official release; checksum failure,
  shallow history, unavailable tools or scanner findings fail closed.
- Homepage: the live root already serves the intended homepage directly. The
  existing regression test prevents the former refresh/extra-entry behavior.
- HTML policy: unchanged. Imported/source HTML remains restricted; reviewed builder
  code supplies interactive navigation. No broad script exception was introduced.
- GitHub presentation and required merge checks: blocked on repository administrator
  access. The current API identity can read the repository but cannot administer it.
  SSH push capability does not grant API administration rights.

The earlier two-commit history observation described main, not all public branches.
The pre-change Gitleaks 8.30.1 scan covered all 11 commits reachable from the three
advertised branches and found zero matches. This is scanner evidence, not a guarantee
that every possible secret is absent. Ignored private collection caches and unrelated
repositories are outside this public-history scan.

## Administrator actions

An administrator of sasukenebe/freebuddhism should apply these repository settings
after checking the new workflow results. These settings are not established merely
because this document or a workflow exists:

- Description: Free Theravāda Buddhist texts, documented sources and redistribution rights.
- Website: https://freebuddhism.org/
- Topics: buddhism, theravada, tipitaka, pali, translations, static-site.
- Main branch rules: require a pull request, resolved review conversations and both
  named checks: Secret scan; Source, tests and site build. Block force pushes and
  branch deletion. Do not make an unavailable check required before its first run.
- Review access: assign an actual reviewer before requiring independent approval;
  do not assume the sole author can approve their own pull request.
- Inspect GitHub secret-scanning and push-protection availability/status and enable
  them where supported. Those settings were not visible through the read-only API.

The reviewed fixes still require a merge onto main. Pushing this branch does not
update the default-branch README or change production. Publication and deployment
remain separate owner decisions.

## Verification

- All 85 tests passed, including the real pre-push fixture: clean history is accepted,
  an added fake GitHub credential blocks the push, and deleting it in a later commit
  still blocks the push. The temporary remote remains at its clean commit. Scanner
  output is checked for redaction; no real credentials are used in that fixture.
- Scanner unit tests cover bad archive checksums, non-regular executable entries,
  changed cached executables, verified download/reuse, symlinks, unsupported platforms,
  shallow history, environment overrides and propagation of a failed scan.
- Source-policy validation passes for 15,905 source files, 7,153 eligible editions,
  7,159 pinned source hashes and 8,643 source HTML routes. All five new files have
  explicit rights entries. Publication rules and imported text bodies are unchanged.
- Actionlint 1.7.12 validates the workflow; shell syntax and Git whitespace checks pass.
- The full local site build passes: 16,257 HTML routes, 31 archives and zero broken
  local links. It reused all 7,153 unchanged reader PDFs. This is a local generated
  preview, not a public deployment or a fresh GitHub runner result.

The installed local pre-push hook scans the committed branch before pushing. GitHub
Actions must then run against that pushed revision; inspect its matching Secret scan
and Source, tests and site build results. A local pass is not a remote Actions result,
owner approval, branch protection or permission to deploy. Rerun checks after changes.

## Follow-up: tracked-file gap and build replacement

The newer review correctly identified two remaining issues, now addressed on this
same review branch. The public main branch was an older snapshot; it still needs a
separately reviewed merge. The previous remote run for dfade632 completed both jobs
successfully; that result does not cover these follow-up changes.

- Tracked-file boundary: Git's complete index is checked separately from filesystem
  traversal. Force-added files in excluded build, virtual-environment and bytecode
  directories fail even if somebody adds them to the allowlist. Unlisted tracked
  paths, symlinks, submodules and unresolved merge entries also fail. Git failure or
  validation below the repository root cannot silently disable this check. Both
  ordinary validation and reviewed checksum refresh enforce the boundary. The
  filesystem scan remains in place for untracked source files and hash validation.
- Recoverable replacement: generation and swaps use a nonblocking process lock.
  The old completed default build is renamed to a backup, not deleted before install.
  A small journal identifies the old and new directories. Failed installation restores
  the old build; interrupted swaps recover before the next generation. Cleanup only
  removes the identified predecessor after the new validated build exists. Unknown
  backups, altered identities, malformed state and symlinks fail closed for review.
- Scope: this protects local build replacement. There can still be a brief path gap
  between directory renames; it is not an uninterrupted live-site switching mechanism
  or certification of power-loss/filesystem durability. No deployment changed.
- Regression coverage includes real force-adds, Git failure, unusual path names,
  merge conflicts, symlink/gitlink index entries, injected rename and rollback errors,
  cleanup failure, concurrent builds, preserved custom previews and real SIGKILL
  interruptions immediately after moving the old build and after installing the new.

Follow-up verification:

- All 105 tests pass, including the real pre-push credential fixture and the new
  tracked-index and interrupted-swap regressions.
- Staged-source validation checks all 15,908 tracked files and passes the exact-path,
  rights and checksum rules. The 7,153 eligible editions and 7,159 source hashes are
  unchanged. Excluded-source metadata remains current.
- The complete local build passes: 16,257 HTML pages, 31 ZIP archives and zero broken
  local links. All 7,153 unchanged reader PDFs are reused. This output is a separate
  local preview, not a production deployment.

The pre-push scanner and GitHub workflow run again for the committed follow-up; inspect
their matching revision rather than treating the earlier dfade632 run as coverage.
GitHub settings still need an authorized administrator; pushing code does not establish
required checks or update main.
