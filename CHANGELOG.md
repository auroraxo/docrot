# Changelog

All notable changes to **docrot** (the open-source documentation rot scanner)
are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.6.0] — 2026-09-29

### Fixed
- **Fenced-code stripping tolerates deep indentation (0-7 spaces).** Fences
  inside list items (CommonMark allows up to 3 spaces of indent for the list
  plus more for the fence content) rendered as code on GitHub but were not
  stripped: an image example inside a 4-space-indented ```jsx fence in
  airbnb/javascript's react/README.md entered the v7 wave-2 dataset as a
  phantom "missing" finding. Verified against GitHub's rendered HTML.
- **Inline-code pairing is list-item-local.** A backtick pair spanning a
  blank line at a list-item boundary still closes (CommonMark: each list
  item is its own block). The paragraph-local-only rule left an
  `![alt](URL)` example in a leaked-prompts file live (jujumilk3/
  leaked-system-prompts, wave-3 v7 dataset, also verified as `<code>` in
  GitHub HTML). Pairing now splits at item starts before matching runs.
- Dataset schema `version` bumps 7 → **8**.

### Process
- Found during the manual classification of the v7 rescan (the
  before-publishing rule, again): BOTH defects were phantom findings in
  freshly produced v7 datasets. Nothing was published from v7; a schema-8
  rescan supersedes it. synthesize_v8.py encodes the success expectations
  (both new phantoms absent, the original skills phantom still absent,
  webpack's 327 references intact) BEFORE the v8 results exist.
- Suite 87 → **89 green**.

## [1.5.2] — 2026-09-29

### Fixed
- Separator routing in the paragraph-local inline-code pairing: a content
  part starting with a single newline (triple-newline sequences) was
  misrouted as a blank-line separator and skipped pairing. Discriminator
  is now a full match on the blank-line pattern. Suite 86 → 87.

## [1.5.1] — 2026-09-29

### Fixed
- **Inline-code stripping is CommonMark-accurate (Scanner v7).** Image syntax
  inside code spans (doc examples like `` `![](<path from flow root>)` ``) is
  no longer extracted. The previous regex paired backtick runs positionally
  instead of by equal length, paragraph-locally; on real documents with
  interleaved run lengths it left phantom references in the dataset. Found
  while manually verifying the wave-2/wave-3 v6 deltas: anthropics/skills
  `eval-hillclimb.md` — GitHub renders the span as `<code>`, scanner v6 had
  counted it as a missing image (verified against GitHub's rendered HTML).
- Dataset schema `version` bumps 6 → **7**.
- **Honesty note:** the wave-2 v6 dataset published today contains exactly
  one known phantom (`path from flow root`, anthropics/skills, reported as
  missing). A 300-repo v7 rescan supersedes the v6 wave datasets; the story
  is NOT updated until that synthesis is complete and every mover verified.

### Added
- 4 regression tests (span example, paragraph locality, interleaved literal
  ticks, real reference between spans); suite 82 → **86 green**.

---

## [1.5.0] — 2026-09-29

### Added
- **Reference-style images are counted (Scanner v6):** `![alt][label]`,
  collapsed `![alt][]`, and shorthand `![label]` uses now resolve against
  their `[label]: url` definitions and enter the dataset. Precision guards:
  a definition referenced only by a plain text link remains a link target,
  not an image; unresolved uses render as literal text and produce nothing;
  labels match case-insensitively; definitions inside code blocks or HTML
  comments are excluded by the existing strips.

### Fixed
- **Tag repointed after a red-suite ship (process correction):** v1.5.0 was
  initially tagged on a commit whose new tests still called
  `extract_image_refs` unqualified while the module is imported as `scan`
  (8 NameErrors; the suite run happened, but its red result was not
  heeded before the release chain continued). Product code was unaffected
  and separately verified by the extraction repro. Tests now use the
  module namespace; the tag and release point at a commit where the full
  suite is **82/82 green**.
- **False-negative class closed:** reference-style images were silently
  skipped, under-counting references in repositories that use them. Found
  by a scanner-vs-API parity probe — the paid API's Markdown extractor
  already consumed reference definitions while the open-source scanner did
  not (the mirror image of the v1.4.0 comment find). Dataset schema
  `version` bumps to 6; suite 74 → **82 green**.

---

## [1.4.0] — 2026-09-28

### Fixed
- **HTML comments no longer counted as image references:** Image syntax inside
  `<!-- ... -->` comments is blanked before extraction. Comment content is never
  rendered — closing the fourth false-positive family (code examples → HTML
  entities → code fences/inline in the sibling API → HTML comments).
- **Parity ritual:** Found by cross-checking the scanner against
  `docrot-scan-api v1.3.0`, which already stripped comments; checking scanner↔API
  parity pointed the audit back at the open-source scanner itself.
- **Line-number provenance:** `strip_html_comments` replaces comment contents
  with same-length whitespace and preserves newlines, keeping line offsets exact.
- **Verification:** 2 new regression tests (inline + multiline comments);
  suite 72 → **74 green**.

---

## [1.3.1] — 2026-09-28

### Added
- **Tier chart:** Inline SVG ("The same finding, drawn") at the end of the
  wave-3 report section, comparing the three star tiers on like-for-like
  metrics without external requests or JavaScript.

### Fixed
- **Public correction on mixed-basis comparison:** Corrected earlier prose that
  compared external-per-unique-image against third-party-per-reference across
  different bases. The datasets were always correct; the narrative was aligned
  to true like-for-like figures (external share 77% → 77% → 75%, third-party
  share 53% → 31% → 57%).
- **Verification:** 3 new tests covering the tier chart; suite 69 → **72 green**.

---

## [1.3.0] — 2026-09-28

### Added
- **Wave-3 report section (`generate_report.py`):** Optional 6th CLI argument
  (`wave3-results.json`) rendering *"A third wave: one star tier down"* with
  tier-3 KPIs and cross-wave narratives.
- **Empirical milestone:** 300 repositories scanned across three tiers (top-100,
  ≥15k stars, 10k–15k stars), proving documentation rot holds steady across
  popularity tiers (**26/100 → 27/100 → 30/100**).
- **Upstream outcomes (18 receipts):** Added verified findings for
  `sml2h3/ddddocr#317` (26 dead images on author CDN),
  `Azure/azure-quickstart-templates#14882` (892 CI badges returning 409), and
  `aalansehaiyang/technology-talk#84` (477 dead images on dead author docsite).
- **Verification:** Suite expanded to 69 tests (+5 covering report generation
  and HTML escaping).

---

## [1.2.0] — 2026-09-27

### Fixed
- **HTML entity decode in image URLs (Scanner v5):** Attribute values in `<img src>`
  tags are now decoded (`html.unescape`) before live HTTP checks. Browsers unescape
  entities prior to request dispatch, so raw checks previously recorded false 400
  verdicts on working URLs (e.g. `?v&#x3D;4&amp;s&#x3D;18`).
- **Corrected wave-2 dataset:** Rescan under v5 eliminated 144 false positives
  (externalBroken 248 → 104; `axios/axios` contributor avatars corrected 136 → 0).
- **Verification:** 2 new regression tests; suite expanded to **60 green**.

---

## [1.1.0] — 2026-09-27

### Fixed
- **Transparent fetch errors (Scanner v4):** `scan.py` now returns `(text, error)`
  from `raw()` instead of silently swallowing network failures. Errored files are
  recorded under `markdownFetchErrors` and subtracted from `markdownFilesScanned`.

### Added
- **"Where the findings went":** Upstream outcome table rendered directly in the
  HTML report (tracking PR merges, issue assignments, and vendor intakes).

---

## [1.0.1] — 2026-09-27

### Fixed
- **Docs-site root false-positive correction:** Eliminated 18 false "missing"
  images in `angular/angular` where `<base href="/">` rewrites paths to the
  hosted site. Added `adev/` to `DOCSITE_HINTS` and reclassified non-rot site
  assets to `unresolvable/docsite-relative-missing` (missing count 105 → 87,
  affected repos 27 → 26).
- **Verification:** 4 new unit tests in `AdevDocsiteTests`; suite **36 green**.

### Added
- **Third-party host fragility section:** Quantifies reliance on 160 external hosts
  across the 100-repository corpus (with 5 completely failed hosting domains
  identified).

---

## [1.0.0] — 2026-09-27

### Added
- Initial public release of the docrot scanner suite.
- **Image rot scanner (`scan.py`):** Resolves in-repo, missing, and external
  image references at a specific commit.
- **Version drift detector (`version_drift.py`):** Flags stale project-own
  version pins with six hardened false-positive exclusions.
- **Interactive report generator (`generate_report.py`):** Zero-dependency HTML
  report with client-side sortable tables and JSON datasets.
- Initial 100-repository corpus scan results and 19 baseline unit tests.
