#!/usr/bin/env python3
"""docrot — measure documentation image rot in public OSS repositories.

For each repo: list markdown files on the default branch, extract every image
reference, resolve it, and check whether it still loads. Output: raw JSON.

No authentication needed for the image checks; the GitHub API calls use a PAT
only to avoid the unauthenticated rate limit.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

TOKEN = open(os.path.expanduser("~/.ghtok")).read().strip()
UA = "docrot/1.0 (+https://codebyaurora.com/docrot/)"
MD_CAP = 120          # markdown files inspected per repo
TIMEOUT = 15

MD_IMG = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)>?[^)]*\)")
HTML_IMG = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)


def api(path):
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Authorization": "Bearer " + TOKEN, "User-Agent": UA,
                 "Accept": "application/vnd.github+json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))


def raw(owner, repo, sha, path):
    url = "https://raw.githubusercontent.com/%s/%s/%s/%s" % (
        owner, repo, sha, urllib.parse.quote(path))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return ""


def check(url):
    """Return (status, note). status is an int HTTP code or 0 for a network error."""
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method,
                                     headers={"User-Agent": UA,
                                              "Accept": "image/*,*/*"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                ctype = r.headers.get("Content-Type", "")
                if method == "GET":
                    r.read(2048)
                return r.status, ctype
        except urllib.error.HTTPError as e:
            if e.code in (403, 405, 501) and method == "HEAD":
                continue
            return e.code, "http-error"
        except Exception as e:
            if method == "HEAD":
                continue
            return 0, type(e).__name__
    return 0, "unreachable"


def resolve(ref, owner, repo, sha, md_path):
    ref = ref.strip().split("#")[0]
    if not ref or ref.startswith("data:") or ref.startswith("mailto:"):
        return None
    if ref.startswith("//"):
        return "https:" + ref
    if ref.startswith("http://") or ref.startswith("https://"):
        return ref
    base_dir = os.path.dirname(md_path)
    if ref.startswith("/"):
        target = ref.lstrip("/")
    else:
        target = os.path.normpath(os.path.join(base_dir, ref))
    return "https://raw.githubusercontent.com/%s/%s/%s/%s" % (
        owner, repo, sha, urllib.parse.quote(target))


def scan_repo(slug):
    owner, repo = slug.split("/")
    meta = api("/repos/%s/%s" % (owner, repo))
    branch = meta["default_branch"]
    stars = meta.get("stargazers_count")
    head = api("/repos/%s/%s/commits/%s" % (owner, repo, branch))
    sha = head["sha"]
    tree = api("/repos/%s/%s/git/trees/%s?recursive=1" % (owner, repo, sha))
    mds = [t["path"] for t in tree.get("tree", [])
           if t["type"] == "blob"
           and t["path"].lower().endswith((".md", ".mdx"))
           and "/node_modules/" not in t["path"]
           and not t["path"].lower().startswith("vendor/")]
    # prefer README and docs/ trees, then the rest
    mds.sort(key=lambda p: (0 if "readme" in p.lower() else
                            1 if p.lower().startswith(("docs/", "doc/", "website/")) else 2,
                            p))
    mds = mds[:MD_CAP]

    refs = {}  # resolved url -> list of (md_path, original ref)
    for path in mds:
        text = raw(owner, repo, sha, path)
        if not text:
            continue
        for m in list(MD_IMG.finditer(text)) + list(HTML_IMG.finditer(text)):
            ref = m.group(1)
            url = resolve(ref, owner, repo, sha, path)
            if url:
                refs.setdefault(url, []).append([path, ref])

    urls = list(refs)
    results = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        for url, (status, note) in zip(urls, ex.map(check, urls)):
            results[url] = (status, note)

    images = []
    for url, places in refs.items():
        status, note = results[url]
        host = urllib.parse.urlparse(url).netloc.lower()
        internal = host in ("raw.githubusercontent.com", "github.com",
                            "user-images.githubusercontent.com",
                            "camo.githubusercontent.com")
        images.append({
            "url": url, "host": host, "external": not internal,
            "status": status, "note": note,
            "broken": status == 0 or status >= 400,
            "refs": places[:5], "refCount": len(places),
        })

    ext = [i for i in images if i["external"]]
    broken = [i for i in images if i["broken"]]
    return {
        "repo": slug, "stars": stars, "defaultBranch": branch, "commit": sha,
        "markdownFilesScanned": len(mds), "markdownFilesTotal": len(
            [t for t in tree.get("tree", []) if t["type"] == "blob"
             and t["path"].lower().endswith((".md", ".mdx"))]),
        "imageRefs": sum(i["refCount"] for i in images),
        "uniqueImages": len(images),
        "externalImages": len(ext),
        "externalHosts": sorted({i["host"] for i in ext}),
        "brokenImages": len(broken),
        "brokenExternal": len([i for i in broken if i["external"]]),
        "images": images,
    }


def main():
    slugs = [l.strip() for l in open(sys.argv[1]) if l.strip() and not l.startswith("#")]
    out = sys.argv[2]
    repos = []
    for slug in slugs:
        t0 = time.time()
        try:
            r = scan_repo(slug)
            repos.append(r)
            print("%-40s %4d imgs  %3d ext  %3d broken  %.0fs" % (
                slug, r["uniqueImages"], r["externalImages"], r["brokenImages"],
                time.time() - t0), flush=True)
        except Exception as e:
            print("%-40s FAILED %s: %s" % (slug, type(e).__name__, e), flush=True)
            repos.append({"repo": slug, "error": "%s: %s" % (type(e).__name__, e)})
        with open(out, "w") as f:
            json.dump({"tool": "docrot",
                       "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "method": {
                           "markdownFileCapPerRepo": MD_CAP,
                           "timeoutSeconds": TIMEOUT,
                           "brokenDefinition": "HTTP status >= 400 or no response",
                           "userAgent": UA},
                       "repos": repos}, f, indent=1)


if __name__ == "__main__":
    main()
