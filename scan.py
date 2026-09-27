#!/usr/bin/env python3
"""docrot v2 — measure documentation image rot in public OSS repositories.

Classification, deliberately conservative:

  in-repo   a relative or root-relative path that resolves to a blob present in
            the repository's own git tree at the scanned commit. Verified
            against the tree listing, not by HTTP, so encoding and rate limits
            cannot produce a false "broken".
  missing   a relative path that resolves nowhere in the tree AND whose
            containing document is not part of a docs site that rewrites roots.
  external  an absolute http(s) URL. Checked by HTTP: >=400 or unreachable
            counts as broken. GitHub-owned and other hosts are tallied separately.
  unresolvable
            root-relative paths inside a documentation site (mkdocs, docusaurus,
            mintlify, hugo...), template placeholders ({{ }}, {% %}, $VAR),
            and non-http schemes such as cid:. These are NOT counted as broken:
            the published URL depends on build configuration a static scan
            cannot see. Reported separately and honestly.

The headline number is verified rot among references whose targets can be
resolved statically or checked over HTTP.
"""
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = "docrot/2.0 (+https://codebyaurora.com/docrot/)"
MD_CAP = 150
TIMEOUT = 15

MD_IMG = re.compile(
    r"!\[[^\]]*\]\(\s*(?:<([^>\n]*)>|([^\s()]+))"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)"
)
HTML_IMG = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", re.I)

GITHUB_OWNED = ("raw.githubusercontent.com", "github.com", "gist.github.com",
                "user-images.githubusercontent.com", "camo.githubusercontent.com",
                "avatars.githubusercontent.com", "github.githubassets.com",
                "private-user-images.githubusercontent.com")

# A document under one of these trees belongs to a built docs site whose URL
# root is not the repository root.
# `adev/` is Angular's docs engine (angular.dev): its content tree
# (adev/src/content/**) rewrites references against the site root via
# <base href="/">; all 13 image targets flagged from adev/ markdown were
# verified serving HTTP 200 from https://angular.dev/assets/ on 2026-09-27.
DOCSITE_HINTS = ("docs/", "doc/", "website/", "web/", "site/", "documentation/",
                 "adev/")

TEMPLATEY = re.compile(r"\{\{|\}\}|\{%|<%|\$\{|\$[A-Z_]{3,}|^\{.*\}$", re.S)


def strip_code(text):
    """Remove fenced and inline code before looking for rendered Markdown.

    Image syntax inside examples is not a rendered image and must not enter the
    dataset. This deliberately handles Markdown's common backtick/tilde forms;
    it is not intended to be a complete Markdown parser.
    """
    text = re.sub(r"(?ms)^[ \t]{0,3}(`{3,}|~{3,})[^\n]*\n.*?^[ \t]{0,3}\1[ \t]*$", "", text)
    text = re.sub(r"(?s)(`+).*?\1", "", text)
    return text


def extract_image_refs(text):
    text = strip_code(text)
    out = []
    for m in MD_IMG.finditer(text):
        ref = m.group(1) if m.group(1) is not None else m.group(2)
        if ref:
            out.append(ref)
    for m in HTML_IMG.finditer(text):
        ref = next((g for g in m.groups() if g is not None), "")
        if ref:
            # Browsers decode HTML entities in attribute values before fetching;
            # check and record the decoded URL, keep raw value in originalRef.
            out.append(html.unescape(ref))
    return out


def api(path, token):
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(4 * (attempt + 1))


def raw(owner, repo, sha, path, token=""):
    """Fetch raw markdown text. Returns (text, error_or_none)."""
    url = "https://raw.githubusercontent.com/%s/%s/%s/%s" % (
        urllib.parse.quote(owner), urllib.parse.quote(repo),
        urllib.parse.quote(sha), urllib.parse.quote(path))
    headers = {"User-Agent": UA}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        return "", "HTTP %d" % e.code
    except Exception as e:
        return "", type(e).__name__


def check(url):
    """(status, note). status is an HTTP code, or 0 for no response at all."""
    last = (0, "unreachable")
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method,
                                     headers={"User-Agent": UA,
                                              "Accept": "image/*,*/*"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                if method == "GET":
                    r.read(2048)
                return r.status, r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (400, 403, 404, 405, 429, 500, 501):
                last = (e.code, "head-refused")
                continue
            return e.code, "http-error"
        except Exception as e:
            last = (0, type(e).__name__)
    return last


def normalize_http_url(url):
    """Percent-encode spaces/non-ASCII without altering URL delimiters."""
    return urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%")


def classify(ref, md_path, tree_paths):
    """Return (kind, target) where kind is external|in-repo|missing|unresolvable."""
    ref = ref.strip()
    if not ref:
        return "unresolvable", "empty"
    if TEMPLATEY.search(ref):
        return "unresolvable", "template-placeholder"
    low = ref.lower()
    if low.startswith("data:"):
        return "unresolvable", "data-uri"
    if ":" in ref.split("/")[0] and not low.startswith(("http://", "https://")) \
            and not ref.startswith("//"):
        return "unresolvable", "non-http-scheme"
    if ref.startswith("//"):
        return "external", normalize_http_url("https:" + ref)
    if low.startswith(("http://", "https://")):
        return "external", normalize_http_url(ref)

    path = urllib.parse.unquote(ref.split("#")[0].split("?")[0])
    if not path:
        return "unresolvable", "fragment-only"
    if path.startswith("/"):
        in_docsite = md_path.lower().startswith(DOCSITE_HINTS)
        target = os.path.normpath(path.lstrip("/"))
        if target in tree_paths:
            return "in-repo", target
        if in_docsite:
            # a docs site rewrites "/" to the site root, not the repo root
            return "unresolvable", "docsite-root-relative"
        return "missing", target
    target = os.path.normpath(os.path.join(os.path.dirname(md_path), path))
    if target.startswith(".."):
        return "unresolvable", "escapes-repo-root"
    if target in tree_paths:
        return "in-repo", target
    if md_path.lower().startswith(DOCSITE_HINTS):
        return "unresolvable", "docsite-relative-missing"
    return "missing", target


def scan_repo(slug, token):
    owner, repo = slug.split("/", 1)
    meta = api("/repos/%s/%s" % (urllib.parse.quote(owner), urllib.parse.quote(repo)), token)
    branch = meta["default_branch"]
    head = api("/repos/%s/%s/commits/%s" % (urllib.parse.quote(owner), urllib.parse.quote(repo), urllib.parse.quote(branch)), token)
    sha = head["sha"]
    tree = api("/repos/%s/%s/git/trees/%s?recursive=1" % (urllib.parse.quote(owner), urllib.parse.quote(repo), urllib.parse.quote(sha)), token)
    blobs = [t["path"] for t in tree.get("tree", []) if t["type"] == "blob"]
    tree_paths = set(blobs)
    truncated = bool(tree.get("truncated"))

    all_md = [p for p in blobs
              if p.lower().endswith((".md", ".mdx"))
              and "/node_modules/" not in p
              and not p.lower().startswith("vendor/")]
    mds = sorted(all_md, key=lambda p: (
        0 if "readme" in p.lower() else
        1 if p.lower().startswith(DOCSITE_HINTS) else 2, p))[:MD_CAP]

    refs = {}            # (kind, target) -> [[md_path, ref], ...]
    fetch_errors = {}    # md_path -> error string
    for path in mds:
        text, err = raw(owner, repo, sha, path, token=token)
        if err:
            fetch_errors[path] = err
            continue
        if not text:
            continue
        for ref in extract_image_refs(text):
            kind, target = classify(ref, path, tree_paths)
            refs.setdefault((kind, target), []).append([path, ref])

    ext_urls = [t for (k, t) in refs if k == "external"]
    statuses = {}
    if ext_urls:
        with ThreadPoolExecutor(max_workers=12) as ex:
            for url, res in zip(ext_urls, ex.map(check, ext_urls)):
                statuses[url] = res

    images = []
    for (kind, target), places in refs.items():
        rec = {"kind": kind, "target": target, "refCount": len(places),
               "refs": places[:5]}
        if kind == "external":
            status, note = statuses[target]
            host = urllib.parse.urlparse(target).netloc.lower()
            rec.update({"host": host, "status": status, "note": note,
                        "githubHosted": host in GITHUB_OWNED,
                        "broken": status == 0 or status >= 400,
                        "originalRef": places[0][1]})
        else:
            rec["broken"] = kind == "missing"
        images.append(rec)

    ext = [i for i in images if i["kind"] == "external"]
    third = [i for i in ext if not i["githubHosted"]]
    return {
        "repo": slug, "stars": meta.get("stargazers_count"),
        "defaultBranch": branch, "commit": sha,
        "treeTruncated": truncated,
        "markdownFilesScanned": len(mds) - len(fetch_errors),
        "markdownFilesTotal": len(all_md),
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
            r = scan_repo(slug, token)
            repos.append(r)
            print("%-34s %4d img %4d 3p-ext %3d 3p-broken %3d missing %3d unres %.0fs"
                  % (slug, r["uniqueImages"], r["externalThirdParty"],
                     r["externalThirdPartyBroken"], r["missingInRepo"],
                     r["unresolvable"], time.time() - t0), flush=True)
        except Exception as e:
            print("%-34s FAILED %s: %s" % (slug, type(e).__name__, e), flush=True)
            repos.append({"repo": slug, "error": "%s: %s" % (type(e).__name__, e)})
        with open(out, "w") as f:
            json.dump({
                "tool": "docrot", "version": 5,
                "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "method": {
                    "markdownFileCapPerRepo": MD_CAP,
                    "timeoutSeconds": TIMEOUT,
                    "inRepoVerifiedAgainst": "git tree at scanned commit",
                    "externalBrokenDefinition": "HTTP status >= 400 or no response",
                    "unresolvableExcludedFromRot": True,
                    "userAgent": UA},
                "repos": repos}, f, indent=1)


if __name__ == "__main__":
    main()
