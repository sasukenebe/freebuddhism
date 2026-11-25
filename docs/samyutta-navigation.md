# Saṃyutta thematic navigation

The Saṃyutta tree uses five books, 56 named saṃyuttas, 229 smaller vaggas and ten
additional source-defined divisions. Collection branches start closed; the
Translations branch on an individual text page starts open. Flat search accepts
numbers, titles and the thematic names, including accentless input.

The tree, group pages, breadcrumbs and combined-reader scopes share one graph.
Existing text IDs, text URLs, edition records, source wording and download rights
are unchanged. Numeric Flat list and combined-reader order remain numeric, even
when a grouped reference belongs at a common ancestor rather than a single chapter.
These are navigation changes, not new translations or a completeness certificate.

## Sources and numbering

The text-free map is [samyutta-navigation.json](../metadata/samyutta-navigation.json).
It records the exact source revision, path and SHA-256 for every input:

- Structure: sc-data commit `c8b50ad760f8dbf74a883bce9b35a3db0a95f503`,
  [SN tree](https://github.com/suttacentral/sc-data/blob/c8b50ad760f8dbf74a883bce9b35a3db0a95f503/structure/tree/sutta/sn-tree.json).
- Names: Bilara commit `d26ba0072c9e1f7a238159f583720edacb9f05f9`,
  [Pāli names](https://github.com/suttacentral/bilara-data/blob/d26ba0072c9e1f7a238159f583720edacb9f05f9/root/misc/site/name/sutta/sn-name_root-misc-site.json)
  and [Sujato English names](https://github.com/suttacentral/bilara-data/blob/d26ba0072c9e1f7a238159f583720edacb9f05f9/translation/en/sujato/name/sutta/sn-name_translation-en-sujato.json).

The selected structure's mirrored Bilara root and the reference pin's root both
equal Git tree `3648b2f3d1e7373d0338426dbeb5ecf35450065f`. Its terminal identifiers
also match all 1,819 SN units in the pinned reference inventory exactly once,
including 134 grouped identifiers. That is not a count of distinct single suttas.
The names preserve the source spellings; only outer whitespace is removed. English
labels identify Sujato's navigation choices and do not rename another translator's
text or heading.

Membership comes from explicit source edges, not guessed groups of ten. For
example, SN 47.41 belongs to the Mahāvagga book, SN 47 Satipaṭṭhānasaṁyutta and
Amatavagga. Its pinned Pāli header separately confirms the chapter name. Other
chapter memberships are checked against the compatible source tree, not claimed
to have received individual passage-level Pāli review.

An edition reference is joined to the explicit reference-unit intervals. A range
crossing chapters belongs at their nearest shared ancestor. Incomplete or unknown
numbering matches remain visibly at the SN root; no historical numbering
equivalence is silently invented. Source collection identity is retained separately
from browsing placement, so this join does not change archive inclusion.

## Rights and checks

Bilara navigation names carry its CC0 dedication. The structure here is a factual
list of identifiers and ordered edges, not publisher prose; no blanket sc-data
repository license or new right to translated passages is asserted. The map
contains no sutta bodies, blurbs or video transcripts.

The loader rejects missing or duplicated reference units, invalid parents,
unreachable nodes, cycles, invalid labels and a mismatched reference pin. Unit tests
cover grouped joins, unchanged source records/routes, shared controls, numeric
ordering and closed collection branches with open Translations.

Release verification must additionally compare every prior reading-index edition
record, source-text body, TXT and PDF payload; run the full build and local-link
checks; and exercise topic-to-text navigation with native keyboard controls on
desktop and narrow viewports. Automated agreement is not human proofreading,
assistive-technology certification or Pāli translation approval.
