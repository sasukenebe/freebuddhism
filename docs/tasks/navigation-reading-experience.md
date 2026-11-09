# Navigation and reading experience

Updated: 2026-11-08

Status: the recursive navigation corrections are live from source commit
`2c0e99d2` on `codex/navigation-reading-experience-20261104`. The easier-expander
comparison, mobile Contents panel and broader assistive-technology testing
remain follow-on work.

This is the durable handoff for simplifying Free Buddhism's Tipiṭaka browsing
and reading experience. It records the requested behavior, phased work, visual
guardrails, and where to resume. Publish only rights-cleared local editions;
deployment is authorized for this task after validation and production preflight.

## Goal

Make it easy to find a text, understand where it sits in the collection, and
read several consecutive texts without repeatedly navigating away. Use one
reusable interface throughout the hierarchy; do not design a separate system
for each Nikāya or book.

## Adopted behavior

- Keep one canonical hierarchy from Tipiṭaka through basket, collection, book,
  chapter, and individual text. Tree, Flat list, and All Text on One Page are
  different views of that same structure.
- Offer three modes at every collection node:
  - **Tree:** expand and collapse descendants.
  - **Flat list:** searchable list of descendant texts.
  - **All Text on One Page:** actual text in canonical order, not a list of links.
- Make expanding a branch visibly different from opening its page. Prototype
  the three requested controls on identical content: (A) large full-width
  expandable rows, preferred; (B) a traditional indented tree with larger
  controls; (C) simple lists with expandable subsection headings. The whole
  row should be easy to operate; do not make users target a tiny arrow. Keep
  the expand action separate from an explicit link that opens the collection.
- Give every page a complete clickable breadcrumb, mark the current location,
  and provide Previous/Next links in canonical order. Keep a contents panel
  available on desktop; on mobile, collapse it behind a clear Contents button.
- For continuous reading, show a compact contents list and actual texts in
  canonical order. Give each text a stable linkable location. Include simple
  controls for Contents, text size, and changing translation; text-size
  controls retain the existing font. For very large collections, generate
  static chapter-sized pages or chunks and load them as needed; do not create
  one enormous page.
- Offer an optional Read setup: choose a collection and one default
  translation, then read continuously. Sujato is the preferred initial default
  where that exact edition is cleared and locally available. Allow “apply to
  all available texts” and optional per-text overrides; keep individual
  choices hidden until requested. Do not prompt for a translation on every
  text. The flow is Collection → Translation → Apply to available texts →
  optional Customize individual texts → Read.
- Remember translation preferences and overrides in local browser storage;
  require no account. Use the selected edition where available. If absent for a
  text, automatically fall back to Sujato when eligible, then to the first
  eligible edition alphabetically. Clearly label the translator used under
  every text; never hide a substitution.
- Make every Flat list text link open its canonical node page. That page links
  to eligible text editions and, where mapped, the related collection audio.
  Include a text's supplied name in its heading and list label; do not invent
  titles when the source only provides a reference number.
- A link to a translation must lead to actual text. Missing or restricted
  translations are plain status text, not dead-end links. Keep “no locally
  eligible text” distinct from “no translation exists.”
- Remove the extra “Enter site” step at the root so the root opens the library.
  Also audit inconsistent indexes, omitted breadcrumb levels, duplicate
  reference numbers in titles, and links to unavailable-content notices.

## Visual guardrail — do not lose this

Keep the site's existing plain-text presentation: the same established font,
font treatment, paragraph spacing, and general page rhythm. Do not introduce
new fonts, decorative reading styles, gratuitous whitespace, or a separate
phone-like layout on desktop. The current pages can feel too narrow on desktop;
use more of the available width while preserving the existing typography and
spacing. Mobile responsiveness is an addition, not a reason to force a narrow
desktop column or redesign the text.

Use ordinary, readable HTML and lightweight static output. No database,
accounts, or server-side application. Do not change the translation text or
its formatting as part of navigation work.

## Keep three kinds of information separate

1. **Canonical structure:** stable IDs, parent/child relationships, order,
   titles, and routes.
2. **Edition availability:** translator, exact edition, rights eligibility,
   completeness, and the route for each text.
3. **Presentation:** Tree/List/Read mode, expanded branches, selected default
   translation, and per-text overrides.

Generate choices and pages from these records; do not hard-code a fixed set of
translators into a collection template. The public-source repository's rights
policy is a hard limit: only cleared local editions may be included in the
generated reader. Do not copy an excluded translation into a concatenated
page. If Sujato is not cleared for a particular local text, do not select or
silently substitute it; show the actual eligible choices.

## First implementation scope

### Continuous text headings — 2026-11-08

Each text heading in All Text on One Page is a conventional bold h2 containing
a link to that text's home node, not a self-link to its continuous-reader anchor
or a link to one chosen edition. The home node offers all eligible translations
and any mapped audio/video sources. Existing Contents links still jump within
the continuous page.

Keep headings at 1.5 times the reading-body size, including after Font Size +,
Font Size - and Reset. Inherit the existing font and browser zoom; do not change
page width, margins or translated text. Apply the shared renderer throughout
the library, not just Dīgha Nikāya. This supersedes the historical request for
plain, unlinked continuous headings recorded in the November 5 pass below.

Before publication, verify node destinations, unchanged inline text, large and
small reading sizes, Reset, keyboard navigation and mobile wrapping. Publish
through the isolated production source pin without including unrelated drafts.

### Recursive correction pass — 2026-11-05

The owner requested the following corrections throughout the library and
authorized pushing and publishing the completed corrections:

1. Remove the invented groups of 25. Retain actual numbered books or source
   subdivisions where recorded; otherwise list texts directly in order.
2. Show the global Home / Dhamma / Buddhist Texts menu on every HTML page.
   Consolidate the collection breadcrumb immediately before the page title,
   removing the redundant standalone parent link and displaced breadcrumb.
3. Use the same collection title and breadcrumb in Tree, Flat list, and
   continuous reading. Extend these modes to the Tipiṭaka root, Vinaya,
   Sutta Vibhaṅga and the other mapped collection branches.
4. Render the current translation as a plain selected label. Keep genuine
   alternate-edition links.
5. Remove the "Open text page:" prefix from text labels.
6. Display unavailable texts, empty collection branches and notice-only
   downloads without links. Preserve their routes for existing external URLs
   and retain the full underlying structure and availability records.
7. Rename Read to "All Text on One Page" throughout the browsing controls.
8. Give Contents the same heading level and size as Reading preferences.
   Text headings within the continuous page are plain headings; the contents
   list retains useful links that scroll to those headings.
9. Label the font controls "Font Size +" and "Font Size -".

Release chunks:
- Shared headers and controls: implemented.
- Recursive collection views, individual text/edition views, and unavailable
  link cleanup: implemented.
- Meaningful regression coverage for full Vinaya ancestry, unavailable link
  removal, ordering across the old 25-item boundary, current-edition labels,
  and unchanged source bodies: implemented; 33 tests pass.
- Full build, browser checks, source push, pinned deployment and live review:
  complete. Source `2c0e99d2` was deployed from production commit `4477813`;
  both review branches are pushed. The release verified 15,453 HTML routes,
  31 archives and zero broken local links. It normalized 15,452 static page
  headers (the continuous reader uses the shared header template) and removed
  3,495 residual links to unavailable pages or notice-only downloads.

Browser verification passes for matching headers across all modes, every
collection URL, Majjhima ordering/search, the Tipiṭaka root, Vinaya and Sutta
Vibhaṅga descendants, unavailable labels, automatic translation fallback,
Contents jumps, font controls, the Milindapañha node/edition/single-text flow,
and mobile width. The same browser checks pass on the public site, including
the Mil 2 edition page. Both public hostnames returned HTTP 200. Retained
rollback point: `20261105T192820Z-4150489`.
The link verifier now resolves both `/` and `./` to the built root index.
Collection coverage totals are computed once per collection rather than once
per text; this retains the same totals while avoiding repeated full scans.

The A/B/C expander comparison remains the separate follow-on task below.

### Original first release — 2026-11-04

The first release is deliberately centered on the Sutta Pitaka, including its
mapped Nikāya and nested collection pages. The current branch implements:

- Tree and searchable flat-list views on the Sutta Pitaka index and each
  generated Sutta collection index, with separate expand and open actions.
- A continuous Sutta reader with canonical-order contents and stable text
  anchors. It contains only locally eligible editions and lazy-loads each
  existing reader page as it is approached.
- Tree, Flat list, and Read controls; the reader keeps visible links back to
  Tree and Flat list. Flat-list links open the canonical text node, which
  links to its eligible editions and mapped collection audio.
- A site-wide translation default saved in browser storage, Sujato as the
  initial choice where eligible, and optional per-text overrides revealed by
  “Customize individual texts.” Missing editions fall back automatically in
  the stated order, and the actual translator is labeled under each text.
- Text headings and index labels include supplied titles when available;
  reference-only source records remain reference-only.
- Plain browser-default typography and page flow, with simple text-size
  controls that retain the same font; full Sutta breadcrumbs on collection,
  canonical text, and translation-reader pages; deduplicated reference/title
  labels; direct root landing page.

The original first release did not cover the Tipiṭaka root or non-Sutta
hierarchies; those are covered by the recursive correction pass. A mobile
Contents panel, the A/B/C expander comparison and full assistive-technology
and device testing remain follow-on work.

## Work chunks

### 0. Re-establish the baseline

- Read this brief and the repository README first. The source checkout at
  planning time was clean on main at `2462764f`.
- Inspect the live pages and the local source/build output before editing;
  record the current font, spacing, desktop width, mobile behavior, routes,
  and page templates. Do not assume the live site and source tree are identical.
- Trace the existing hierarchy, edition records, and rights checks. Starting
  points: `metadata/site-catalog.json`, `metadata/site-content.json`,
  `metadata/eligible-texts.json`, `metadata/excluded-sources.json`,
  `tools/buddhist_canon_pipeline/public_site_catalog.py`, and
  `tools/buddhist_canon_pipeline/build_deploy_site.py`.
- Check the reported problem routes: long AN and SN indexes; AN 1.11 Sujato
  reader; MN 10 breadcrumb; root landing page; and edition links that lead to
  unavailable-content notices. Verify what is actually served before fixing.

### 1. Correct the hierarchy and links

- Define or normalize reusable canonical nodes and routes from existing
  metadata; do not create translator-specific navigation trees.
- Fix complete breadcrumbs, current-location marking, Previous/Next order,
  duplicate titles, inconsistent collection indexes, and the root landing
  route.
- Make absent/restricted text routes non-clickable and explain actual local
  availability. Preserve external links only when they genuinely lead to an
  available source and are clearly labeled.

### 2. Make local visual prototypes

- Use the same real collection and content for expander options A, B, and C.
  A is the preferred first implementation; retain B/C for a later local
  comparison rather than changing the established typeface.
- Keep the existing font and plain text styling in every option. Compare
  target size, row behavior, indentation, and the distinction between
  expanding and opening. Do not prototype font changes unless that constraint
  is explicitly revisited.
- Include one continuous-reading sample with real eligible texts and stable
  anchors. The user has requested implementation and release, so do not stop
  for separate prototype approval if validation and rights gates pass.

### 3. Build the reusable collection views

- Apply Tree, Flat list, and All Text on One Page to the same recursive
  collection interface at all hierarchy depths. Search the flat list; keep
  expansion controls large and keyboard operable.
- Ensure Tree/List/Read never imply that unavailable text exists. Where a
  collection has no locally eligible text, explain that directly instead of
  showing an empty reader or dead-end link.
- Keep each mode's hierarchy and canonical order consistent. Preserve stable
  URLs for collection nodes and individual texts.

### 4. Add continuous reading and translation preferences

- Generate continuous readers from canonical order plus actual edition
  availability. Do not hand-maintain a list of translators in page code.
- Start with the optional collection/translation setup, then “Read
  continuously.” Make the selected translator visible. Use a local preference
  for the default and optional per-text overrides; never switch silently.
- For long AN/SN-scale collections, split output into static chapter-sized
  chunks with a contents list and linkable text headings.
- Test missing editions, partial editions, rights exclusions, and explicit
  alternate choices before calling a collection complete.

### 5. Validate, push the review branch, and deploy

- Verify every breadcrumb and Previous/Next pair against the canonical tree;
  every translation link must resolve to actual eligible text.
- Test the three modes, text anchors, search, browser-local preferences,
  keyboard operation, screen-reader labels, narrow screens, and large-index
  performance. Check that desktop width improves without changing the
  established font or spacing.
- Run the public-tree rights validator, repository tests, static build, and
  generated-site link checks. Add any new public source files to
  `metadata/public-file-allowlist.json` with their reviewed license scope and
  exact hash.
- Push the source changes to the named review branch, then deploy via a clean
  production worktree that pins that exact source commit. Do not touch the
  user's unrelated production-repository branch.
- Verify production URLs and deployed content after release. Give the user a
  concise review block with branch, commit, site URL, test results, and rollback
  point.

## Deferred follow-on task — easier tree controls

After this first navigation release, compare tree-expander treatments locally
on the same collection: full-width rows, a traditional tree with larger
disclosure targets, and expandable subsection headings. Check whether larger
text, taller rows, clearer arrows, or other disclosure controls make expanding
easier without changing the site's established font, paragraph spacing, or
plain-text presentation. Keep the user's preferred full-row option as the
baseline. This is a later usability investigation, not a reason to delay this
release.

## Resume point

The 2026-11-05 recursive correction pass is published and verified. Source
commit `2c0e99d2` and production commit `4477813` identify the deployed build.
The owner can review the public navigation now. The later A/B/C expander
comparison remains a separate usability task; keep the plain font and layout.

### Previous first-release record — 2026-11-04

The first Sutta release is implemented on
`codex/navigation-reading-experience-20261104`. Baseline checks confirmed
production was pinned to an older source snapshot and served an "Enter site"
root page; the source now opens directly to the library. AN 1.11 Sujato is
locally eligible under CC0. Its local metadata has no individual title beyond
the reference number; the collection index supplies its parent chapter name.
Do not invent a per-sutta title. The strict bundle validates 6,352 eligible
readers, 6,692 Sutta index entries, 15,453 HTML routes, and zero broken local
links; all 32 public-release tests pass.

Deployment record: source commit `f66ecfe6` is deployed via production review
branch `codex/freebuddhism-navigation-deploy-20261104` at `9d13b2d`. The first
attempt was automatically rolled back after detecting that the temporary
webroot was not traversable by nginx. The build now normalizes generated
directories to 755 and files to 644, with a regression test. The retry passed
production preflight and returned HTTP 200 for both public hostnames. Retained
rollback point: `20261104T231531Z-4108804`. Continue with the open scope above
and the deferred tree-control usability comparison.

## Review examples

- Aṅguttara index and AN 1.11 reader:
  `https://freebuddhism.org/theravada/tipitaka/sutta/anguttara-nikaya/`
  `https://freebuddhism.org/theravada/tipitaka/sutta/anguttara-nikaya/an01-11/an01-11-sujato.html`
- Majjhima MN 10 reader:
  `https://freebuddhism.org/theravada/tipitaka/sutta/majjhima-nikaya/mn10/`
- Samyutta index and site root should be captured during Chunk 0 rather than
  assumed from remembered URLs.
