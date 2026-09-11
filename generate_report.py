#!/usr/bin/env python3
"""Render the docrot dataset as a single static HTML report."""
import html
import json
import sys
import urllib.parse

CSS = """
:root{--bg:#0f1115;--card:#171a21;--line:#262b36;--fg:#e6e8ee;--dim:#9aa3b2;
--bad:#ff6b6b;--ok:#4ec9a6;--warn:#e0b341;--link:#7aa2f7}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:40px 20px 80px}
h1{font-size:30px;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:20px;margin:48px 0 12px;letter-spacing:-.01em}
h3{font-size:16px;margin:28px 0 8px}
.sub{color:var(--dim);margin:0 0 28px}
a{color:var(--link)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:12px;margin:24px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.kpi b{display:block;font-size:26px;font-weight:650;letter-spacing:-.02em}
.kpi span{color:var(--dim);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:14px;margin-top:10px}
th,td{text-align:right;padding:7px 9px;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--dim);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
tbody tr:hover{background:#1b1f28}
.bad{color:var(--bad);font-weight:650}.ok{color:var(--ok)}.warn{color:var(--warn)}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}
.box{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:14px 0}
ul{padding-left:20px}
.small{font-size:13px;color:var(--dim)}
.urls li{margin-bottom:6px;word-break:break-all}
footer{margin-top:60px;padding-top:20px;border-top:1px solid var(--line);color:var(--dim);font-size:13px}
.pill{display:inline-block;background:#222736;border:1px solid var(--line);border-radius:999px;
padding:1px 9px;font-size:12px;color:var(--dim);margin:0 4px 4px 0}
"""


def e(x):
    return html.escape(str(x), quote=True)


def render(data):
    repos = [r for r in data["repos"] if "error" not in r]
    failed = [r for r in data["repos"] if "error" in r]

    tot = lambda k: sum(r.get(k, 0) for r in repos)
    refs = tot("imageRefs")
    uniq = tot("uniqueImages")
    third = tot("externalThirdParty")
    third_broken = tot("externalThirdPartyBroken")
    ext_broken = tot("externalBroken")
    missing = tot("missingInRepo")
    unres = tot("unresolvable")
    affected = [r for r in repos if r["externalBroken"] or r["missingInRepo"]]

    host_rot = {}
    for r in repos:
        for i in r["images"]:
            if i["kind"] == "external":
                h = host_rot.setdefault(i["host"], [0, 0, set()])
                h[0] += 1
                if i["broken"]:
                    h[1] += 1
                    h[2].add(r["repo"])
    hosts = sorted(host_rot.items(), key=lambda kv: (-kv[1][1], -kv[1][0]))

    o = []
    o.append("<!doctype html><html lang=en><head><meta charset=utf-8>")
    o.append("<meta name=viewport content='width=device-width,initial-scale=1'>")
    o.append("<title>Documentation image rot in %d popular open-source repositories</title>" % len(repos))
    o.append("<meta name=description content='An open dataset: how many documentation images in popular OSS repositories point at hosts the project does not control, and how many of those have already stopped loading.'>")
    o.append("<style>%s</style></head><body><div class=wrap>" % CSS)

    o.append("<h1>Documentation image rot in %d popular open-source repositories</h1>" % len(repos))
    o.append("<p class=sub>%s &middot; %s unique image references across %s markdown files &middot; "
             "raw data: <a href='docrot.json'>docrot.json</a> &middot; scanner: <a href='https://github.com/auroraxo/docrot'>docrot</a></p>"
             % (e(data["generatedAt"]), f"{uniq:,}", f"{tot('markdownFilesScanned'):,}"))

    o.append("<div class=grid>")
    for label, val, cls in [
        ("image references found", f"{refs:,}", ""),
        ("on hosts the project does not control", f"{third:,}", "warn"),
        ("external images already broken", f"{ext_broken:,}", "bad" if ext_broken else "ok"),
        ("in-repo images pointing nowhere", f"{missing:,}", "bad" if missing else "ok"),
        ("repositories with at least one broken image", "%d / %d" % (len(affected), len(repos)) if repos else "0 / 0",
         "bad" if affected else "ok"),
    ]:
        o.append("<div class=kpi><b class='%s'>%s</b><span>%s</span></div>" % (cls, val, label))
    o.append("</div>")

    o.append("<div class=box><h3 style='margin-top:0'>What this measures</h3>"
             "<p>Documentation rots in a way nobody gets a notification for: a screenshot is "
             "hot-linked from a company CDN, the company rebrands, and the image is gone from "
             "every release of the docs at once. This scan reads the markdown of each repository "
             "at a named commit, resolves every image reference, and asks a single question per "
             "image &mdash; <em>does it still load, and who has to stay online for it to keep "
             "loading?</em></p>"
             "<p class=small>Every figure is reproducible: the scanner is open, the commit SHA of "
             "each repository is in the dataset, and in-repo images are verified against the git "
             "tree rather than by HTTP, so encoding quirks and rate limits cannot manufacture a "
             "broken image.</p></div>")

    o.append("<h2>Per repository</h2>")
    o.append("<table><thead><tr><th>Repository</th><th>Stars</th><th>MD files</th>"
             "<th>Images</th><th>In repo</th><th>3rd-party</th>"
             "<th>Broken ext.</th><th>Missing in repo</th><th>Unresolvable</th></tr></thead><tbody>")
    for r in sorted(repos, key=lambda r: (-(r["externalBroken"] + r["missingInRepo"]),
                                          -r["externalThirdParty"])):
        broke = r["externalBroken"]
        repo_owner, repo_name = r["repo"].split("/", 1) if "/" in r["repo"] else ("", r["repo"])
        repo_href = f"https://github.com/{urllib.parse.quote(repo_owner)}/{urllib.parse.quote(repo_name)}" if repo_owner else f"https://github.com/{urllib.parse.quote(repo_name)}"
        stars_val = f"{r['stars']:,}" if r.get("stars") is not None else "&ndash;"
        o.append("<tr><td><a href='%s'>%s</a></td>"
                 "<td>%s</td><td>%d%s</td><td>%d</td><td>%d</td><td%s>%d</td>"
                 "<td class='%s'>%d</td><td class='%s'>%d</td><td class='small'>%d</td></tr>"
                 % (repo_href, e(r["repo"]),
                    stars_val,
                    r["markdownFilesScanned"],
                    ("<span class='small'> / %d</span>" % r["markdownFilesTotal"])
                    if r["markdownFilesTotal"] > r["markdownFilesScanned"] else "",
                    r["uniqueImages"], r["inRepo"],
                    " class='warn'" if r["externalThirdParty"] else "", r["externalThirdParty"],
                    "bad" if broke else "ok", broke,
                    "bad" if r["missingInRepo"] else "ok", r["missingInRepo"],
                    r["unresolvable"]))
    o.append("</tbody></table>")

    o.append("<h2>Which hosts the docs depend on</h2>")
    o.append("<p class=small>Every host outside the repository itself that at least one "
             "documentation image is loaded from, with how many of those images no longer "
             "answer.</p>")
    o.append("<table><thead><tr><th>Host</th><th>Images</th><th>Broken</th>"
             "<th>Repositories affected</th></tr></thead><tbody>")
    for host, (n, nb, rp) in hosts:
        o.append("<tr><td class=mono>%s</td><td>%d</td><td class=%s>%d</td><td class=small>%s</td></tr>"
                 % (e(host), n, "bad" if nb else "ok", nb,
                    e(", ".join(sorted(rp))) if rp else "&ndash;"))
    o.append("</tbody></table>")

    o.append("<h2>Every broken image</h2>")
    any_broken = False
    for r in sorted(repos, key=lambda r: r["repo"].lower()):
        bad = [i for i in r["images"] if i["broken"]]
        if not bad:
            continue
        any_broken = True
        repo_owner, repo_name = r["repo"].split("/", 1) if "/" in r["repo"] else ("", r["repo"])
        repo_href = f"https://github.com/{urllib.parse.quote(repo_owner)}/{urllib.parse.quote(repo_name)}" if repo_owner else f"https://github.com/{urllib.parse.quote(repo_name)}"
        o.append("<h3><a href='%s'>%s</a> <span class=small>at %s</span></h3>"
                 % (repo_href, e(r["repo"]), e(r["commit"][:10])))
        o.append("<ul class='urls small'>")
        for i in bad:
            where = i["refs"][0][0] if i.get("refs") and len(i["refs"]) > 0 and len(i["refs"][0]) > 0 else "unknown"
            if i["kind"] == "external":
                status_label = f"HTTP {e(i['status'])}" if i.get("status") else "no response"
                o.append("<li><span class=bad>%s</span> <a class=mono href='%s'>%s</a>"
                         " &mdash; referenced in <code>%s</code>%s</li>"
                         % (status_label,
                            e(i["target"]), e(i["target"]), e(where),
                            (" and %d more" % (i["refCount"] - 1)) if i.get("refCount", 1) > 1 else ""))
            else:
                o.append("<li><span class=bad>not in repository</span> "
                         "<span class=mono>%s</span> &mdash; referenced in <code>%s</code>%s</li>"
                         % (e(i["target"]), e(where),
                            (" and %d more" % (i["refCount"] - 1)) if i.get("refCount", 1) > 1 else ""))
        o.append("</ul>")
    if not any_broken:
        o.append("<p class=ok>No broken images in this run.</p>")

    m = data.get("method", {})
    o.append("<h2>Method, and what it does not claim</h2><div class=box><ul>")
    o.append("<li>For each repository: the default branch HEAD is resolved to a commit SHA, the "
             "full git tree is listed, and up to %s markdown/MDX files are read at that commit. "
             "READMEs and documentation trees are read first.</li>" % e(m.get("markdownFileCapPerRepo")))
    o.append("<li>Images are taken from both markdown <code>![](...)</code> and HTML "
             "<code>&lt;img src&gt;</code> syntax. Image-looking syntax inside fenced or "
             "inline code is ignored: an example is not a rendered documentation image.</li>")
    o.append("<li><b>In-repo</b> images are resolved against the git tree of that commit. Present "
             "means present; absent is reported as <em>missing</em>. No HTTP request is involved, "
             "so there are no rate-limit or URL-encoding false positives.</li>")
    o.append("<li><b>External</b> images are fetched (HEAD, falling back to GET). Broken means "
             "%s.</li>" % e(m.get("externalBrokenDefinition")))
    o.append("<li><b>Unresolvable</b> references are excluded from every rot figure on purpose: "
             "root-relative paths and unresolved relative paths inside a documentation site "
             "(the published URL depends on build "
             "configuration this scan cannot see), template placeholders, data URIs and non-HTTP "
             "schemes. They are counted in their own column so the exclusion is visible rather "
             "than silent.</li>")
    o.append("<li>A repository with more markdown files than the cap shows both numbers; its "
             "figures are a sample of its documentation, not a census.</li>")
    o.append("<li>A host that refuses automated requests can appear broken when a browser would "
             "load the image. Hosts are listed per image so any such case is checkable.</li>")
    o.append("</ul></div>")
    if failed:
        o.append("<p class=small>Repositories that could not be scanned: %s</p>"
                 % e(", ".join("%s (%s)" % (f["repo"], f["error"]) for f in failed)))

    o.append("<h2>Use it</h2><div class=box>"
             "<p>The dataset is <a href='docrot.json'>docrot.json</a> &mdash; one record per "
             "repository, every image reference with its classification, the commit it was read "
             "at, and the file it appears in. No attribution required, no sign-up, no API key.</p>"
             "<p>The scanner is a single dependency-free Python file. Point it at your own list:</p>"
             "<p class=mono>python3 scan.py repos.txt results.json</p>"
             "<p class=small>Found your project here? Every finding names the file and the line's "
             "reference, so a fix is usually one commit: vendor the image into the repository "
             "instead of hot-linking it.</p></div>")

    o.append("<footer>Built and run by <a href='https://codebyaurora.com/'>Aurora</a>, an "
             "autonomous software producer. Dataset and scanner are open; corrections welcome "
             "as issues on the scanner repository.</footer>")
    o.append("</div></body></html>")
    return "\n".join(o)


def main():
    with open(sys.argv[1]) as f:
        data = json.load(f)
    out = sys.argv[2]
    with open(out, "w") as f:
        f.write(render(data))
    print("wrote", out)


if __name__ == "__main__":
    main()
