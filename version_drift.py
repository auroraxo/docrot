#!/usr/bin/env python3
"""docrot version-drift — find stale version literals in OSS READMEs.

The sibling rot class to broken images: a README advertising "v0.1.4"
while the repository's manifest declares "0.1.8" misleads every visitor,
and nothing fails. Found live in the wild twice within 48 hours (five
hardcoded "0.1.5" fallback literals in a released Python package; a
product landing page four releases behind its daemon).

Method, deliberately conservative:

  declared version  read once from the first canonical manifest present:
                    pyproject.toml, package.json, Cargo.toml, VERSION.
                    Fallback: highest v-prefixed semver tag. No manifest
                    and no tags -> the repo is reported as skipped, never
                    guessed.
  literals          only full X.Y.Z triples in contexts that pin a
                    release: release/tag and release/download URLs, pip
                    pins (name==X.Y.Z), npm pins (name@X.Y.Z), shields
                    version badges. Fenced code is NOT stripped here
                    (install commands in fenced blocks are exactly where
                    pins live). Bare vX.Y.Z mentions in prose are
                    reported separately as "mentions", never as drift:
                    dogfooding showed they are other projects' versions
                    ("Prometheus v0.0.4 text format") or payload samples
                    ("python_version": "3.11.16") — legitimate text,
                    and changelog headings/runtime mentions stay
                    excluded entirely.
  classification    current | stale against the declared version.
                    Stale pins are the headline number.
"""
import json
import os
import re
import sys
import time

import scan

MD_CAP = 30
TAGS_PAGE = 100

MANIFESTS = ("pyproject.toml", "package.json", "Cargo.toml", "VERSION")

SEMVER = r"(\d+\.\d+\.\d+)"

# context patterns, tried in order; each yields (context, normalized_version)
URL_TAG = re.compile(r"releases/(?:tag|download)/v?" + SEMVER, re.I)
PIP_PIN = re.compile(r"(?<![\w.-])[\w][\w.-]*==" + SEMVER)
NPM_PIN = re.compile(r"(?<![\w@./-])[\w][\w.-]*@" + SEMVER)
BADGE = re.compile(r"badge/(?:release-)?v?" + SEMVER + r"-")
STANDALONE = re.compile(r"(?<![\w./@:=-])v?" + SEMVER + r"(?![\w.-])")

RUNTIME_NEAR = re.compile(r"(python|cpython|node\.?js?|ruby|go1\.)\s*v?$", re.I)
HEADING = re.compile(r"^\s{0,3}#+\s")


def normalize(v):
    v = v.strip()
    return v[1:] if v[:1] in ("v", "V") else v


def _pyproject(text):
    m = re.search(r'(?m)^\s*version\s*=\s*["\']([^"\']+)["\']', text)
    return m.group(1) if m else None


def _package_json(text):
    m = re.search(r'"version"\s*:\s*"([^"]+)"', text)
    return m.group(1) if m else None


def _cargo(text):
    m = re.search(r'(?m)^\s*version\s*=\s*["\']([^"\']+)["\']', text)
    return m.group(1) if m else None


def _version_file(text):
    t = text.strip()
    return t if re.fullmatch(r"v?\d+\.\d+\.\d+", t) else None


_PARSERS = {
    "pyproject.toml": _pyproject,
    "package.json": _package_json,
    "Cargo.toml": _cargo,
    "VERSION": _version_file,
}


def parse_declared_version(files):
    """files: {path: text}. Returns (version, source) or (None, None).

    Priority is the canonical manifest order; first hit wins. Values that
    are not plain semver (e.g. poetry-dynamic versioning placeholders) and
    the classic monorepo placeholder "0.0.0" are ignored, honestly — the
    scanner then falls back to tags rather than declaring a version that
    describes nothing (seen live: supabase's root package.json).
    """
    for path in MANIFESTS:
        text = files.get(path)
        if not text:
            continue
        v = _PARSERS[path](text)
        if v and normalize(v) != "0.0.0" and re.fullmatch(r"v?\d+\.\d+\.\d+", normalize(v)):
            return normalize(v), path
    return None, None


PIN_CONTEXTS = ("release-link", "pip-pin", "npm-pin", "badge")


def extract_version_literals(text, md_path="README.md"):
    """Return [(line_no, context, version)] for version literals.

    `text` is used verbatim — fenced code is where real install pins
    live. context is one of the pin contexts or "text" for bare
    mentions; changelog headings and runtime-version mentions are
    excluded entirely.
    """
    out = []
    for m in STANDALONE.finditer(text):
        line_no = text.count("\n", 0, m.start()) + 1
        line_start = text.rfind("\n", 0, m.start()) + 1
        line = text[line_start:text.find("\n", m.start()) if text.find("\n", m.start()) != -1 else len(text)]
        if HEADING.match(line):
            continue  # changelog heading, old entries are legitimate
        before = text[max(0, m.start() - 14):m.start()]
        if RUNTIME_NEAR.search(before):
            continue
        out.append((line_no, "text", normalize(m.group(1))))
    for pattern, ctx in ((URL_TAG, "release-link"), (PIP_PIN, "pip-pin"),
                         (NPM_PIN, "npm-pin"), (BADGE, "badge")):
        for m in pattern.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            out.append((line_no, ctx, normalize(m.group(1))))
    return out


def classify_literals(literals, declared):
    """Split into (current_pins, stale_pins, mentions).

    Only pin contexts count as drift. Bare "text" mentions are returned
    separately and never counted as stale: they routinely belong to
    other projects (protocol versions, runtime versions in samples).
    """
    current, stale, mentions = 0, [], []
    for line_no, ctx, v in literals:
        if ctx == "text":
            mentions.append({"line": line_no, "version": v})
            continue
        if v == declared:
            current += 1
        else:
            stale.append({"line": line_no, "context": ctx, "version": v})
    return current, stale, mentions


def _highest_tag(tags):
    vers = [normalize(t["name"]) for t in tags
            if re.fullmatch(r"v?\d+\.\d+\.\d+", t["name"])]
    if not vers:
        return None
    vers.sort(key=lambda s: [int(p) for p in s.split(".")])
    return vers[-1]


def scan_repo_version_drift(slug, token):
    owner, repo = slug.split("/", 1)
    meta = scan.api("/repos/%s/%s" % (scan.urllib.parse.quote(owner),
                                      scan.urllib.parse.quote(repo)), token)
    branch = meta["default_branch"]
    head = scan.api("/repos/%s/%s/commits/%s" % (scan.urllib.parse.quote(owner),
                                                 scan.urllib.parse.quote(repo),
                                                 scan.urllib.parse.quote(branch)), token)
    sha = head["sha"]
    tree = scan.api("/repos/%s/%s/git/trees/%s?recursive=1" % (
        scan.urllib.parse.quote(owner), scan.urllib.parse.quote(repo),
        scan.urllib.parse.quote(sha)), token)
    blobs = {t["path"] for t in tree.get("tree", []) if t["type"] == "blob"}

    files = {}
    for path in MANIFESTS:
        if path in blobs:
            files[path] = scan.raw(owner, repo, sha, path)
    declared, source = parse_declared_version(files)

    if declared is None:
        tags = scan.api("/repos/%s/%s/tags?per_page=%d" % (
            scan.urllib.parse.quote(owner), scan.urllib.parse.quote(repo),
            TAGS_PAGE), token)
        declared, source = _highest_tag(tags), "highest-semver-tag"

    if declared is None:
        return {"repo": slug, "commit": sha, "declaredVersion": None,
                "status": "skipped-no-declared-version"}

    all_md = sorted(
        (p for p in blobs
         if p.lower().endswith((".md", ".mdx"))
         and "/node_modules/" not in p
         and not p.lower().startswith("vendor/")),
        key=lambda p: (0 if "readme" in p.lower() else 1, p))[:MD_CAP]

    current, stale, mentions, scanned = 0, [], [], 0
    for path in all_md:
        text = scan.raw(owner, repo, sha, path)
        if not text:
            continue
        scanned += 1
        c, s, m = classify_literals(extract_version_literals(text, path), declared)
        current += c
        for entry in s:
            stale.append({"path": path, **entry})
        for entry in m:
            mentions.append({"path": path, **entry})
    stale = [s for s in stale if "path" in s]

    return {
        "repo": slug, "commit": sha, "defaultBranch": branch,
        "declaredVersion": declared, "declaredSource": source,
        "markdownFilesScanned": scanned, "markdownFilesTotal": len(all_md),
        "versionRefs": current + len(stale),
        "currentRefs": current,
        "staleRefs": len(stale),
        "stale": stale[:20],
        "mentionRefs": len(mentions),
        "mentions": mentions[:20],
        "status": "drift" if stale else "clean",
    }


def main():
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        tok_file = os.path.expanduser("~/.ghtok")
        if os.path.isfile(tok_file):
            token = open(tok_file).read().strip()
    slugs = [l.strip() for l in open(sys.argv[1])
             if l.strip() and not l.startswith("#")]
    out = sys.argv[2]
    repos = []
    for slug in slugs:
        t0 = time.time()
        try:
            r = scan_repo_version_drift(slug, token)
            repos.append(r)
            if r.get("declaredVersion") is None:
                print("%-34s skipped (no declared version) %.0fs"
                      % (slug, time.time() - t0), flush=True)
            else:
                print("%-34s declared %-10s %3d refs %3d stale %.0fs"
                      % (slug, r["declaredVersion"], r["versionRefs"],
                         r["staleRefs"], time.time() - t0), flush=True)
                for s in r["stale"][:5]:
                    print("    %s:%d %s %s" % (s["path"], s["line"],
                                               s["context"], s["version"]),
                          flush=True)
        except Exception as e:
            print("%-34s FAILED %s: %s" % (slug, type(e).__name__, e), flush=True)
            repos.append({"repo": slug, "error": "%s: %s" % (type(e).__name__, e)})
    with open(out, "w") as f:
        json.dump({
            "tool": "docrot-version-drift", "version": 1,
            "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method": {
                "declaredVersionSources": list(MANIFESTS) + ["highest-semver-tag"],
                "markdownFileCapPerRepo": MD_CAP,
                "literalContexts": ["release-link", "pip-pin", "npm-pin",
                                     "badge", "text"],
                "excluded": ["changelog headings", "runtime mentions "
                             "near python/cpython/node", "non-semver "
                             "manifest values"],
                "staleDefinition": "literal != declared version"},
            "repos": repos}, f, indent=1)


if __name__ == "__main__":
    main()
