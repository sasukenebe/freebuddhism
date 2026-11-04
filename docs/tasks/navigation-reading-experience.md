# Navigation and reading experience

Updated: 2026-11-04

Status: first-release implementation complete on the review branch; broader
Tipiṭaka scope and easier-expander comparison remain open
`codex/navigation-reading-experience-20261104`. The user has requested push
and production deployment after validation.

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
  chapter, and individual text. Tree, List, and Read are different views of
  that same structure.
- Offer three modes at every collection node:
  - **Tree:** expand and collapse descendants.
  - **List:** searchable flat list of descendant texts.
  - **Read:** actual text in canonical order, not a list of links.
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
  translation, then read continuously. Sujato is the preferred default only
  where that exact edition is already cleared and locally available. Allow
  “apply to all available texts” and optional per-text overrides; keep the
  individual choices hidden until the reader asks to customize them. Do not
  prompt for a translation on every text. The flow is Collection → Translation
  → Apply to available texts → optional Customize individual texts → Read.
- Remember translation preferences and overrides in local browser storage;
  require no account. Never silently switch translators. If the selected
  translation is missing, say so and explicitly offer another eligible
  edition, if one exists.
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

The first release is deliberately centered on the Sutta Pitaka, including its
mapped Nikāya and nested collection pages. The current branch implements:

- Tree and searchable flat-list views on the Sutta Pitaka index and each
  generated Sutta collection index, with separate expand and open actions.
- A continuous Sutta reader with canonical-order contents and stable text
  anchors. It contains only locally eligible editions and lazy-loads each
  existing reader page as it is approached.
- A site-wide translation default saved in browser storage, Sujato as the
  initial choice where that exact edition is eligible, and optional per-text
  overrides revealed by “Customize individual texts.” Missing editions are
  never silently replaced.
- Plain browser-default typography and page flow, with simple text-size
  controls that retain the same font; full Sutta breadcrumbs on collection,
  canonical text, and translation-reader pages; deduplicated reference/title
  labels; direct root landing page.

This does not yet implement Tree/List/Read for the Tipiṭaka basket root or
non-Sutta hierarchies, a mobile Contents panel, the A/B/C expander comparison,
or full assistive-technology and device testing. Track those separately; do
not describe the first release as complete across every canonical node.

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

- Apply Tree, List, and Read to the same recursive collection interface at all
  hierarchy depths. Search the flat list; keep expansion controls large and
  keyboard operable.
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

The first Sutta release is implemented on
`codex/navigation-reading-experience-20261104`. Baseline checks confirmed
production was pinned to an older source snapshot and served an "Enter site"
root page; the source has a direct landing page. AN 1.11 Sujato is locally
eligible under CC0; the issue was its narrow system-font reader layout, not
missing text. The strict local bundle validated 6,352 eligible readers,
6,692 Sutta index entries, 15,453 HTML routes, and zero broken local links;
the focused public-release suite passed 30 tests. After deployment, continue
with the open scope above and the deferred tree-control usability comparison.

## Review examples

- Aṅguttara index and AN 1.11 reader:
  `https://freebuddhism.org/theravada/tipitaka/sutta/anguttara-nikaya/`
  `https://freebuddhism.org/theravada/tipitaka/sutta/anguttara-nikaya/an01-11/an01-11-sujato.html`
- Majjhima MN 10 reader:
  `https://freebuddhism.org/theravada/tipitaka/sutta/majjhima-nikaya/mn10/`
- Samyutta index and site root should be captured during Chunk 0 rather than
  assumed from remembered URLs.
