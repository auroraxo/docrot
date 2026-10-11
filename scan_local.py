#!/usr/bin/env python3
"""docrot scan_local — measure documentation image rot in a local repository.

Same classification rules as scan.py (in-repo / missing / external /
unresolvable), but the inputs are a local checkout and a local tree walk
instead of the GitHub API. Designed to be the engine behind a CI/Action
runner: no GitHub token required, no network calls except external URL
checks, and a structured JSON summary that downstream tooling can both
fail on and surface as an artifact.

Usage:
  python3 scan_local.py <root> <out.json> [--fail-on-broken]

The headline figure is `externalThirdPartyBroken` + `missingInRepo`:
references whose target can be checked and is found dead. Unresolvable
references (template placeholders, docs-site root-relatives outside the
local tree) are reported separately and never count as broken.
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

# Reuse the canonical classification + extraction from scan.py. Living in the
# same package, they must stay the single source of truth for what counts as
# rot — drift between the two entry points is exactly the bug the action is
# meant to catch in user repos.
import scan


MD_SUFFIX = (".md", ".mdx")
MD_CAP = scan.MD_CAP
TIMEOUT = scan.TIMEOUT


def walk_tree(root):
    """Return the set of relative file paths under root, skipping the usual
    noise. This is a static, deterministic walk — not a `git ls-files` —
    so the action works on a clean checkout, on a tarball, and on a
    shallow clone alike.
    """
    out = set()
    skip_dirs = (".git", "node_modules", "vendor", "__pycache__",
                 ".venv", "venv", ".tox", "dist", "build", "target")
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs
                       and not d.startswith(".cache")]
        for f in filenames:
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, root)
            # Normalise to forward slashes for cross-platform parity with
            # scan.py, which speaks GitHub-tree style paths everywhere.
            out.add(rel.replace(os.sep, "/"))
    return out


def pick_markdowns(tree_paths):
    mds = [p for p in tree_paths if p.lower().endswith(MD_SUFFIX)]
    mds.sort(key=lambda p: (
        0 if "readme" in p.lower() else
        1 if p.lower().startswith(scan.DOCSITE_HINTS) else 2, p))
    return mds[:MD_CAP]


def scan_local(root, fail_on_broken=False):
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise SystemExit("not a directory: " + root)
    tree_paths = walk_tree(root)
    mds = pick_markdowns(tree_paths)

    refs = {}            # (kind, target) -> [[md_path, ref], ...]
    fetch_errors = {}    # md_path -> error string
    for path in mds:
        full = os.path.join(root, path)
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            fetch_errors[path] = "%s: %s" % (type(e).__name__, e)
            continue
        if not text:
            continue
        for ref in scan.extract_image_refs(text):
            kind, target = scan.classify(ref, path, tree_paths)
            refs.setdefault((kind, target), []).append([path, ref])

    ext_urls = [t for (k, t) in refs if k == "external"]
    statuses = {}
    if ext_urls:
        with ThreadPoolExecutor(max_workers=12) as ex:
            for url, res in zip(ext_urls, ex.map(scan.check, ext_urls)):
                statuses[url] = res

    images = []
    for (kind, target), places in refs.items():
        rec = {"kind": kind, "target": target, "refCount": len(places),
               "refs": places[:5]}
        if kind == "external":
            status, note = statuses[target]
            from urllib.parse import urlparse
            host = urlparse(target).netloc.lower()
            rec.update({"host": host, "status": status, "note": note,
                        "githubHosted": host in scan.GITHUB_OWNED,
                        "broken": status == 0 or status >= 400,
                        "originalRef": places[0][1]})
        else:
            rec["broken"] = kind == "missing"
        images.append(rec)

    ext = [i for i in images if i["kind"] == "external"]
    third = [i for i in ext if not i["githubHosted"]]
    summary = {
        "repo": os.path.basename(root.rstrip(os.sep)) or root,
        "root": root,
        "tool": "docrot-scan-local",
        "version": 1,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": {
            "markdownFileCap": MD_CAP,
            "timeoutSeconds": TIMEOUT,
            "externalBrokenDefinition": "HTTP status >= 400 or no response",
            "unresolvableExcludedFromRot": True,
        },
        "markdownFilesScanned": len(mds) - len(fetch_errors),
        "markdownFilesTotal": len([p for p in tree_paths
                                   if p.lower().endswith(MD_SUFFIX)]),
        "markdownFetchErrors": fetch_errors,
        "imageRefs": sum(i["refCount"] for i in images),
        "uniqueImages": len(images),
        "inRepo": len([i for i in images if i["kind"] == "in-repo"]),
        "missingInRepo": len([i for i in images if i["kind"] == "missing"]),
        "unresolvable": len([i for i in images if i["kind"] == "unresolvable"]),
        "external": len(ext),
        "externalThirdParty": len(third),
        "externalBroken": len([i for i in ext if i["broken"]]),
        "externalThirdPartyBroken": len([i for i in third if i["broken"]]),
        "thirdPartyHosts": sorted({i["host"] for i in third}),
        "images": images,
    }
    broken = (summary["externalThirdPartyBroken"] + summary["missingInRepo"])
    summary["brokenTotal"] = broken
    summary["actionExit"] = 1 if (fail_on_broken and broken > 0) else 0
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("root", help="local repository root to scan")
    p.add_argument("out", help="path to write the JSON summary")
    p.add_argument("--fail-on-broken", action="store_true",
                   help="exit non-zero if any broken reference is found")
    args = p.parse_args()
    summary = scan_local(args.root, fail_on_broken=args.fail_on_broken)
    with open(args.out, "w") as f:
        json.dump(summary, f, indent=1)
    print("%-20s %4d img %4d 3p-ext %3d 3p-broken %3d missing %3d unres" % (
        summary["repo"], summary["uniqueImages"],
        summary["externalThirdParty"], summary["externalThirdPartyBroken"],
        summary["missingInRepo"], summary["unresolvable"]), flush=True)
    if summary["actionExit"]:
        print("docrot: %d broken reference(s) — failing (--fail-on-broken)"
              % summary["brokenTotal"], file=sys.stderr)
    sys.exit(summary["actionExit"])


if __name__ == "__main__":
    main()
