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

## Results

First full pass over the **100 most-used repositories** from the corpus in
`repos.txt`, scanned at default-branch HEAD on 2026-09-27. Raw data:
[`docrot-results-100.json`](docrot-results-100.json) (images) and
[`drift-results-100.json`](drift-results-100.json) (version pins);
interactive report: <https://codebyaurora.com/docrot/>.

**Image rot.** 6,179 image references resolved. 1,791 of them (29%) load
from hosts outside GitHub. 58 external images no longer load, and 105
in-repo paths resolve to nothing in the tree they name — **27 of the 100
repositories carry at least one broken documentation image.** Extremes:
`appsmithorg/appsmith` (9 dead Notion-hosted design-system screenshots, 73
missing in-repo paths), `angular/angular` (18 tutorial images missing),
`tensorflow/tensorflow` (all 9 build-status badges in the README's
"Official Builds" table return 403, plus an artifact link to the
discontinued Bintray returning 410 — reported as
[tensorflow/tensorflow#128150](https://github.com/tensorflow/tensorflow/issues/128150)).

**Version drift.** Of the same 100 repos, 89 advertise their declared
release correctly, 10 declare no machine-readable version (skipped, never
guessed), and **exactly one carries a stale pin**: `apache/airflow` pins
`==3.3.0` in its README while the manifest declares 3.4.0 — reported as
[apache/airflow#73769](https://github.com/apache/airflow/issues/73769) and
fixed by [apache/airflow#73770](https://github.com/apache/airflow/pull/73770).

Every number above was line-verified before reporting. Several of the
false-positive classes were found precisely by chasing a headline finding
to its source — the last one surfaced when the 100-repo pass flagged an
`"For example:"` release link that was teaching a URL shape, not
advertising a version.

## Usage

```sh
echo 'owner/repo' > repos.txt
export GITHUB_TOKEN="your_token_here" # or echo "$GITHUB_TOKEN" > ~/.ghtok; helps avoid rate limits
python3 scan.py repos.txt results.json
python3 generate_report.py results.json index.html
```

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
- Image-looking syntax inside fenced or inline code is ignored: examples do not
  become rendered documentation images.
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

## Licence

MIT for the scanner. The dataset is CC0 — take it, re-run it, disagree with it.
