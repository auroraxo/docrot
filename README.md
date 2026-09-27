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
semver tag as fallback). Only pin contexts count as drift: release
tag/download URLs, `pip` pins (`name==X.Y.Z`), `npm` pins (`name@X.Y.Z`),
and shields version badges. Bare `vX.Y.Z` prose mentions are reported
separately as `mentions` and never counted — they routinely belong to other
projects (protocol versions like "Prometheus v0.0.4", runtime versions in
payload samples). Changelog headings and runtime requirements are excluded.

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
