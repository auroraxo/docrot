# Contributing to docrot

Thanks for considering a contribution. docrot measures documentation image
rot in public Git repositories, and every published number has been
line-verified before it left this repository — that verification rule is
the one thing we ask all contributors to keep.

## Ground rules

1. **No unverified headline numbers.** If your change alters a count in the
   README or in a published dataset, chase the mover to its source (fetch
   the URL, open the file at the named commit) before publishing it.
2. **Phantom findings are treated as bugs, not findings.** Several classes
   of false positives (code fences, inline code, docs-site image-root
   rewrites) were found by chasing headline findings to source. If you find
   another, that is a scanner fix plus a regression test — not a footnote.
3. **Never publish a dataset with a known unexplained phantom.** The v7
   wave datasets were withheld for exactly this reason; a schema-8 rescan
   superseded them.

## Development setup

```bash
git clone https://github.com/auroraxo/docrot.git
cd docrot
python3 -m unittest discover -v        # or: python3 test_docrot.py
```

The suite is pure standard library (no dependencies) and currently sits at
**70 tests**; keep it green.

## Where to start

- **Scanner accuracy** (`scan.py`): reference extraction and classification
  live here. Every fix needs a regression test in `test_docrot.py` that
  fails before the fix.
- **Version drift** (`version_drift.py`): stale version pins in READMEs.
  Context rules are deliberately conservative — a contribution that widens
  them must show on real READMEs that it does not create false positives.
- **Synthesis / gates** (`tools/`): the comparison scripts that gate
  dataset publication (hard expectations are written *before* the new
  results exist).

## Reporting a bug

Use the bug report issue template. The most useful report contains:

- the repository and commit you scanned,
- the exact image reference and what you observed (404? 200 but wrong
  image? timeout?),
- why you believe it is a phantom (for example: the image loads in a
  browser, or GitHub renders the surrounding block as code).

## Pull request checklist

- [ ] `python3 -m unittest discover` passes locally.
- [ ] New behaviour has a regression test that fails without the fix.
- [ ] README / CHANGELOG updated if user-visible behaviour or published
      numbers change.
- [ ] No dataset is published from a run with an unexplained phantom.

## Licence

Contributions are accepted under the repository's existing licence (see
[LICENSE](LICENSE)).
