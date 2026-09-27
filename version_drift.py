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
  literals          only full X.Y.Z triples, and only in pin contexts
                    that can refer to THIS project: release/tag and
                    release/download URLs on this repo, pip pins whose
                    distribution name matches the repo (apache-airflow
                    ==3.3.0 in apache/airflow), npm pins likewise, and
                    shields version badges. Fenced code is NOT stripped
                    (install pins live there). Everything else is a
                    mention, never drift: other projects' release links
                    (google/jsonnet v0.16.0 inside prometheus docs),
                    dependency pins (botocore==1.31.81 in localstack
                    docs), example placeholders ("package==1.0.0"),
                    prerelease specs (dbt-core==2.0.0rc1 is not a 2.0.0
                    pin), example release links ("For example:
                    github.com/envoyproxy/envoy/releases/tag/v1.39.0"
                    teaches the URL shape, it does not advertise the
                    current version), and CHANGELOG*/CHANGES* files
                    entirely — those are historical records by
                    definition.
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
# a pin ends after the third component: 2.0.0rc1 (prerelease) and
# 1.2.3.4 (4-part) are not X.Y.Z pins and must not be truncated
SEMVER_TAIL = r"(?!\w)(?!\.\d)"

# context patterns; pip/npm capture the distribution name and release
# links are resolved against the surrounding URL, so "self vs. other"
# can be decided honestly instead of flagging every pin on the page.
URL_TAG = re.compile(r"releases/(?:tag|download)/v?" + SEMVER + SEMVER_TAIL, re.I)
PIP_PIN = re.compile(r"(?<![\w.-])([\w][\w.-]*?)==" + SEMVER + SEMVER_TAIL)
NPM_PIN = re.compile(r"(?<![\w@./-])([\w][\w.-]*?)@" + SEMVER + SEMVER_TAIL)
BADGE = re.compile(r"badge/(?:release-)?v?" + SEMVER + r"-")
STANDALONE = re.compile(r"(?<![\w./@:=-])v?" + SEMVER + r"(?![\w.-])")

GH_RELEASE_PREFIX = re.compile(r"github\.com/([^/\"'\s>)]+)/([^/\"'\s>)]+)/?$")


def pep503(name):
    """PEP 503 normalized distribution name."""
    return re.sub(r"[-_.]+", "-", name.lower()).strip("-")


def is_self_name(name, repo_name):
    """True when a pinned distribution name can be this repository.

    Exact PEP 503 match, or the pin carries the org segment the repo
    name omits (apache-airflow in apache/airflow). Everything else is a
    dependency or an example placeholder.
    """
    n, r = pep503(name), pep503(repo_name)
    return bool(n) and (n == r or n.endswith("-" + r) or r.endswith("-" + n))


def is_changelog_path(path):
    base = path.rsplit("/", 1)[-1].upper()
    return base.startswith(("CHANGELOG", "CHANGES"))


def _release_repo(text, pos):
    """Owner/repo when a release link is rooted at github.com, else None
    (relative links inside a README refer to the repository itself)."""
    window = text[max(0, pos - 200):pos]
    m = GH_RELEASE_PREFIX.search(window)
    if m:
        return m.group(1), m.group(2)
    return None


_EXAMPLE = re.compile(r"\bfor example\b", re.I)


def _line_of(text, pos):
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return text[start:] if end == -1 else text[start:end]

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


def extract_version_literals(text, md_path="README.md", repo_full=None):
    """Return [(line_no, context, version)] for version literals.

    `text` is used verbatim — fenced code is where real install pins
    live. Drift-eligible contexts (PIN_CONTEXTS) require the pin to
    name this project: pip/npm pins must match the repo name and
    release URLs must point at this repo (repo_full = "owner/repo").
    Without repo_full, pip/npm pins are conservatively "dep-pin".
    Everything not in PIN_CONTEXTS is a mention. Changelog headings and
    runtime-version mentions are excluded entirely.
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
    for m in URL_TAG.finditer(text):
        ctx = "release-link"
        if repo_full:
            owner_repo = _release_repo(text, m.start())
            if owner_repo and "/".join(owner_repo).lower() != repo_full.lower():
                ctx = "ext-release-link"
        if ctx == "release-link" and _EXAMPLE.search(_line_of(text, m.start())):
            ctx = "example-link"
        line_no = text.count("\n", 0, m.start()) + 1
        out.append((line_no, ctx, normalize(m.group(1))))
    for pattern, self_ctx in ((PIP_PIN, "pip-pin"), (NPM_PIN, "npm-pin")):
        for m in pattern.finditer(text):
            ctx = self_ctx if repo_full and is_self_name(
                m.group(1), repo_full.split("/", 1)[1]) else "dep-pin"
            line_no = text.count("\n", 0, m.start()) + 1
            out.append((line_no, ctx, normalize(m.group(2))))
    for m in BADGE.finditer(text):
        line_no = text.count("\n", 0, m.start()) + 1
        out.append((line_no, "badge", normalize(m.group(1))))
    return out


def classify_literals(literals, declared, also_current=None):
    """Split into (current_pins, stale_pins, mentions).

    Only PIN_CONTEXTS count as drift. Everything else — bare "text",
    dependency pins, other repos' release links — is returned in
    mentions and never counted as stale. `also_current` (e.g. the
    latest published release) rescues pins that match it: main-branch
    manifests often declare an unreleased version, and a pin at the
    newest real release is honest, not drift.
    """
    current, stale, mentions = 0, [], []
    ok = {declared} | set(also_current or [])
    for line_no, ctx, v in literals:
        if ctx not in PIN_CONTEXTS:
            mentions.append({"line": line_no, "context": ctx, "version": v})
            continue
        if v in ok:
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

    latest_release = None
    try:
        rel = scan.api("/repos/%s/%s/releases/latest" % (
            scan.urllib.parse.quote(owner), scan.urllib.parse.quote(repo)), token)
        tag = (rel.get("tag_name") or "").strip()
        if re.fullmatch(r"v?\d+\.\d+\.\d+", tag):
            latest_release = normalize(tag)
    except Exception:
        pass

    all_md = sorted(
        (p for p in blobs
         if p.lower().endswith((".md", ".mdx"))
         and "/node_modules/" not in p
         and not p.lower().startswith("vendor/")),
        key=lambda p: (0 if "readme" in p.lower() else 1, p))[:MD_CAP]
    scan_mds = [p for p in all_md if not is_changelog_path(p)]
    changelog_skipped = len(all_md) - len(scan_mds)

    current, stale, mentions, scanned = 0, [], [], 0
    for path in scan_mds:
        text = scan.raw(owner, repo, sha, path)
        if not text:
            continue
        scanned += 1
        c, s, m = classify_literals(
            extract_version_literals(text, path, repo_full=slug), declared,
            also_current=[latest_release] if latest_release else None)
        current += c
        for entry in s:
            stale.append({"path": path, **entry})
        for entry in m:
            mentions.append({"path": path, **entry})
    stale = [s for s in stale if "path" in s]

    return {
        "repo": slug, "commit": sha, "defaultBranch": branch,
        "declaredVersion": declared, "declaredSource": source,
        "latestRelease": latest_release,
        "markdownFilesScanned": scanned, "markdownFilesTotal": len(all_md),
        "changelogFilesSkipped": changelog_skipped,
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
