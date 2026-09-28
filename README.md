# docrot

Measure documentation image rot in public Git repositories.

Documentation breaks silently. A screenshot is hot-linked from a company CDN, the
company rebrands, and the image vanishes from every version of the docs at once —
including the tags, the release notes and the archived copies. Nothing fails, no
CI job turns red, and the only signal is a reader seeing a broken image.

`docrot` reads the markdown of a repository at a named commit, resolves every
image reference, and answers two questions per image:

- does it still load?
- who has to stay online for it to keep loading?

Published dataset and report: <https://codebyaurora.com/docrot/>
Field log (what acting on the findings produced in one day and one night): <https://codebyaurora.com/docrot/story.html>

## Results

First full pass over the **100 most-used repositories** from the corpus in
`repos.txt`, scanned at default-branch HEAD on 2026-09-27. Raw data:
[`docrot-results-100.json`](docrot-results-100.json) (images) and
[`drift-results-100.json`](drift-results-100.json) (version pins);
interactive report: <https://codebyaurora.com/docrot/>.

**Image rot.** 6,179 image references resolved, covering 3,391 distinct
images; 2,615 of those (77%) load from outside the repository, 1,791 (53%)
from hosts GitHub doesn't control. 58 external images no longer load, and 87
in-repo paths resolve to nothing in the tree they name — **26 of the 100
repositories carry at least one broken documentation image.** Extremes:
`appsmithorg/appsmith` (9 dead Notion-hosted design-system screenshots, 73
missing in-repo paths — reported as
[appsmithorg/appsmith#42298](https://github.com/appsmithorg/appsmith/issues/42298))
and `tensorflow/tensorflow` (all 9 build-status badges in the README's
"Official Builds" table return 403, plus an artifact link to the
discontinued Bintray returning 410 — reported as
[tensorflow/tensorflow#128150](https://github.com/tensorflow/tensorflow/issues/128150)).

**Version drift.** Of the same 100 repos, 89 advertise their declared
release correctly, 10 declare no machine-readable version (skipped, never
guessed), and **exactly one carries a stale pin**: `apache/airflow` pins
`==3.3.0` in its README while the manifest declares 3.4.0 — reported as
[apache/airflow#73769](https://github.com/apache/airflow/issues/73769) and
fixed by [apache/airflow#73770](https://github.com/apache/airflow/pull/73770),
merged into `main` by PMC chair Jarek Potiuk on 2026-09-27).

Every number above was line-verified before reporting. Several of the
false-positive classes were found precisely by chasing a headline finding
to its source. The newest one was chased the same way: `angular/angular`'
18 "missing" tutorial images all serve HTTP 200 from angular.dev — its
docs engine (`adev/`) rewrites image roots against the site, not the
repository root — so they are now excluded as docs-site references
(dataset v3, regression-tested), which is why the missing count reads 87,
not 105.

**Second wave.** The next 100 repositories by stars (≥15k, zero overlap,
`repos2.txt`) were scanned the same day at HEAD; raw data:
[`docrot-results-wave2.json`](docrot-results-wave2.json). 14,365 references
resolved across 8,942 unique images, 77% of them external. 104 external
images are broken and 48 in-repo paths resolve to nothing — **27 of the 100
carry at least one broken documentation image**, against 26/100 in wave one:
the rate is corpus-independent, the external share stays flat (77% vs 77%
of unique images), and wave 2 leans less on independent third-party hosts
(31% vs 53%). Corrected in v1.3.1: this sentence previously compared shares
across different bases ("77% vs 29%") — the datasets were always right. Wave 2's first scan overcounted broken externals
(248) because HTML-entity-encoded `<img src>` values were live-checked in
raw form; scanner v5 decodes them, the whole wave was rescanned from
scratch, and the corrected dataset replaced the published one with md5
parity before any issue was filed on the old numbers
([v1.2.0](https://github.com/auroraxo/docrot/releases/tag/v1.2.0)).
Five findings from this wave were verified line by line and reported:
[microsoft/PowerToys#50821](https://github.com/microsoft/PowerToys/issues/50821),
[firecrawl/firecrawl#4776](https://github.com/firecrawl/firecrawl/issues/4776),
[flutter/flutter#193415](https://github.com/flutter/flutter/issues/193415),
[jackfrued/Python-100-Days#1217](https://github.com/jackfrued/Python-100-Days/issues/1217)
(with a two-line fix PR
[#1218](https://github.com/jackfrued/Python-100-Days/pull/1218)), and
[labuladong/fucking-algorithm#2653](https://github.com/labuladong/fucking-algorithm/issues/2653).

**Third wave.** One star tier down: the next 100 candidate repositories
(10k–15k stars, zero overlap with either earlier corpus, `repos3.txt`)
were scanned under scanner v5; raw data:
[`docrot-results-wave3.json`](docrot-results-wave3.json). 6,037 references
resolved across 4,457 unique images, 75% external. 1,472 external images
are broken and 25 in-repo paths resolve to nothing — **30 of the 100 carry
at least one broken documentation image** (against 27/100 in wave two and
26/100 in wave one): across three tiers and 300 repositories, the rot
share remains ~26–30%. This wave yielded the two largest single-host
rot clusters of the project:
- [Azure/azure-quickstart-templates#14882](https://github.com/Azure/azure-quickstart-templates/issues/14882):
  all 892 status badges on `azurequickstartsservice.blob.core.windows.net`
  return HTTP 409 Conflict (`PublicAccessNotPermitted`), breaking the
  status block in 146 READMEs simultaneously (prescribed by
  `1-CONTRIBUTION-GUIDE/sample-README.md`).
- [aalansehaiyang/technology-talk#84](https://github.com/aalansehaiyang/technology-talk/issues/84):
  author's personal CDN `offercome.cn` is completely unreachable (HTTPS
  timeout), rendering 477 unique off-repo images dead across `docs/md/**`.
- [sml2h3/ddddocr#317](https://github.com/sml2h3/ddddocr/issues/317):
  all 26 off-repo images on author CDN `cdn.wenanzhe.com` return HTTP 404,
  breaking sponsor badges and captcha demonstration images in READMEs.

## Usage

```sh
echo 'owner/repo' > repos.txt
export GITHUB_TOKEN="your_token_here" # or echo "$GITHUB_TOKEN" > ~/.ghtok; helps avoid rate limits
python3 scan.py repos.txt results.json
python3 generate_report.py results.json index.html [drift-results.json [outcomes.json [wave2-results.json [wave3-results.json]]]]
```

`outcomes.json` is an optional curated list (`[{"repo": …, "status": …, "text": …}]`)
rendered as "Where the findings went" — what each headline finding turned into
upstream. `wave2-results.json` and `wave3-results.json` (further 100-repo datasets from
`scan.py`) add companion sections ("A second wave", "A third wave: one star tier down")
with their own KPIs and per-wave findings tables.
Repository names are HTML-escaped; the text field is trusted author markup.

No dependencies beyond the Python 3 standard library. The token needs no scopes
for public repositories.

### Version drift

Broken images have a sibling rot class: READMEs that still advertise an old
release while the manifest declares a newer one. Five hardcoded `"0.1.5"`
fallback literals shipped inside a released Python package, and a product
landing page advertised v0.1.4 while v0.1.8 was live — nothing failed, the
documentation just lied. `version_drift.py` pins that class down:

```sh
python3 version_drift.py repos.txt drift-results.json
```

The declared version is read from `pyproject.toml`, `package.json`,
`Cargo.toml`, or `VERSION` (monorepo placeholder `0.0.0` ignored; highest
semver tag as fallback). Only pins that name *this project* count as drift:
release tag/download URLs on this repository, pip pins whose distribution
name matches the repo (`apache-airflow==3.3.0` in `apache/airflow`), npm
pins likewise, and shields version badges. Everything else is a mention,
never drift — other projects' release links (`google/jsonnet v0.16.0`
inside prometheus docs), dependency pins (`botocore==1.31.81` in localstack
docs), example placeholders (`"package==1.0.0"`), prerelease specs
(`dbt-core==2.0.0rc1` is not a `2.0.0` pin), example release links
("For example:" lines teach the URL shape, they do not advertise the
current version), bare prose versions, and
`CHANGELOG*`/`CHANGES*` files entirely. A pin matching the latest published
release also counts as current: main-branch manifests often declare an
unreleased version, and pinning the newest real release is honest.

Every finding is verified against the source line before it is reported;
the first 40-repository pass flagged six repos, five of which proved to
be the false-positive classes above — the rules here are what the hardened
scan removed them with. The corpus was then widened to 100 repositories
(see Results).

## Classification

Every image reference falls into exactly one bucket.

| Bucket | Meaning | Counted as rot |
|---|---|---|
| `in-repo` | Resolves to a blob present in the repository's own git tree at the scanned commit | no |
| `missing` | A relative path outside a docs-site tree that resolves nowhere in the git tree | **yes** |
| `external` | An absolute `http(s)` URL; fetched with HEAD, falling back to GET | **yes** if status ≥ 400 or unreachable |
| `unresolvable` | Root-relative paths inside a built docs site, template placeholders, data URIs, non-HTTP schemes | no — excluded on purpose |

Two decisions matter:

**In-repo images are verified against the git tree, not over HTTP.** Listing the
tree is authoritative and cheap, and it removes an entire class of false
positives: percent-encoded filenames, spaces, non-ASCII paths and raw-host rate
limits cannot make a present file look missing.

**Unresolvable references are excluded from every rot figure and reported in
their own column.** A path like `/img/tutorial/image01.png` in a mkdocs or
Docusaurus tree is resolved by the site build, not by the repository layout; a
static scan cannot know the published URL. Counting those as broken inflates the
headline number by an order of magnitude — an early version of this tool reported
115 broken images in one repository where the honest answer was zero. Declaring
the exclusion is the difference between a dataset and a scare.

## Known limitations

- Markdown files are capped per repository (default 150, READMEs and docs trees
  first). A repository above the cap is sampled, not censused; the report shows
  both numbers.
- Image-looking syntax inside fenced or inline code, and inside HTML comments,
  is ignored: examples and commented-out snippets do not become rendered
  documentation images.
- A host that refuses automated requests can look broken when a browser would
  load the image. Hosts are listed per image so any such case is checkable.
- Only markdown and MDX are read. Images referenced from HTML templates, RST, or
  code comments are out of scope.
- Only images are checked. Dead links generally are a larger problem and a
  different tool.

## Why off-repository hosting matters

An image outside the repository is a dependency on another publishing surface.
It may be operated by the project, GitHub, or somebody else; the scanner cannot
infer ownership from a hostname and does not claim to. The dataset therefore
reports GitHub-hosted and non-GitHub external image counts separately for every
repository scanned, not only the ones where something has already failed.

In the 100-repository corpus:

- **91 of the 100 repositories** load at least one documentation image from an
  off-GitHub host.
- Across those 91 repos, images depend on **160 distinct third-party hosts**.
- **Five hosts have failed completely:** every image the scan found on them
  no longer answers — `storage.googleapis.com` (tensorflow/tensorflow, 9/9 badges
  403), `s3-us-west-2.amazonaws.com` (appsmithorg/appsmith, 9/9 Notion-hosted
  assets 403), `repology.org` (3/3 badges across neovim, netdata, systemd),
  `api.travis-ci.org` (2/2 across nestjs, nodejs), and `strapi.io` (2/2).
  Ten additional single-image third-party hosts have completely rotted.

The interactive report tables enumerate every host, its reference count, and
which repositories depend on it: <https://codebyaurora.com/docrot/>

## Licence

MIT for the scanner. The dataset is CC0 — take it, re-run it, disagree with it.
