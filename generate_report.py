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


def render_drift(drift):
    """Render the version-drift dataset as a report section."""
    repos = [r for r in drift.get("repos", []) if "error" not in r]
    failed = [r for r in drift.get("repos", []) if "error" in r]
    skipped = [r for r in repos if r.get("declaredVersion") is None]
    covered = [r for r in repos if r.get("declaredVersion")]
    drift_repos = [r for r in repos if r.get("staleRefs")]
    stale_total = sum(r.get("staleRefs", 0) for r in repos)
    mention_total = sum(r.get("mentionRefs", 0) for r in repos)

    o = []
    o.append("<h2>Version drift: READMEs advertising old releases</h2>")
    o.append("<p class=sub>%s &middot; %d repositories checked for stale version pins &middot; "
             "raw data: <a href='drift-results-100.json'>drift-results-100.json</a> &middot; "
             "scanner: <a href='https://github.com/auroraxo/docrot/blob/main/version_drift.py'>version_drift.py</a></p>"
             % (e(drift.get("generatedAt", "")), len(repos)))

    o.append("<div class=grid>")
    for label, val, cls in [
        ("repositories scanned", str(len(repos)), ""),
        ("with a declared version", "%d / %d" % (len(covered), len(repos)), ""),
        ("stale pins found", str(stale_total), "bad" if stale_total else "ok"),
        ("repositories with drift", "%d / %d" % (len(drift_repos), len(covered)) if covered else "0 / 0",
         "bad" if drift_repos else "ok"),
        ("versions mentioned, not pinned", f"{mention_total:,}", ""),
    ]:
        o.append("<div class=kpi><b class='%s'>%s</b><span>%s</span></div>" % (cls, val, label))
    o.append("</div>")

    o.append("<div class=box><h3 style='margin-top:0'>What this measures</h3>"
             "<p>Broken images have a sibling: a README still advertising an old release while "
             "the manifest declares a newer one. This scan reads the declared version from "
             "<code>pyproject.toml</code>, <code>package.json</code>, <code>Cargo.toml</code> or "
             "<code>VERSION</code> (highest semver tag as fallback, monorepo placeholder "
             "<code>0.0.0</code> ignored) and compares every pin that names the project itself: "
             "release tag/download URLs on the same repository, pip pins whose distribution name "
             "matches the repo, npm pins likewise, and shields version badges. A pin matching the "
             "latest published release counts as current — main-branch manifests often declare an "
             "unreleased version.</p>"
             "<p class=small>Everything else is a mention, never drift: other projects' release "
             "links, dependency pins, example placeholders, prerelease specs "
             "(<code>2.0.0rc1</code> is not <code>2.0.0</code>), bare prose versions, and "
             "<code>CHANGELOG*</code>/<code>CHANGES*</code> files entirely. The five "
             "false-positive classes this removes were each found live in the first corpus pass "
             "and are documented in the scanner.</p></div>")

    if drift_repos:
        o.append("<h2>Every stale pin</h2>")
        for r in sorted(drift_repos, key=lambda r: r["repo"].lower()):
            repo_owner, repo_name = r["repo"].split("/", 1)
            o.append("<h3><a href='https://github.com/%s/%s'>%s</a> <span class=small>declares %s (%s)"
                     " &middot; latest release %s</span></h3>"
                     % (e(repo_owner), e(repo_name), e(r["repo"]),
                        e(r["declaredVersion"]), e(r.get("declaredSource", "?")),
                        e(r.get("latestRelease") or "&ndash;")))
            o.append("<ul class='urls small'>")
            for s in r["stale"]:
                o.append("<li><span class=bad>pin %s</span> <span class=mono>%s:%s</span> "
                         "<span class=pill>%s</span></li>"
                         % (e(s["version"]), e(s["path"]), s["line"], e(s["context"])))
            o.append("</ul>")
    else:
        o.append("<p class=ok>No stale version pins in this run.</p>")

    clean = [r for r in covered if not r.get("staleRefs")]
    if clean:
        names = ", ".join("<a href='https://github.com/%s'>%s</a>" % (e(r["repo"]), e(r["repo"]))
                          for r in sorted(clean, key=lambda r: r["repo"].lower()))
        o.append("<h2>Clean against their own manifest</h2>"
                 "<p class=small>%s</p>" % names)
    if skipped:
        o.append("<p class=small>No declared version (no manifest, no semver tags): %s</p>"
                 % e(", ".join(sorted(r["repo"] for r in skipped))))
    if failed:
        o.append("<p class=small>Repositories that could not be scanned: %s</p>"
                 % e(", ".join("%s (%s)" % (f["repo"], f["error"]) for f in failed)))
    return "\n".join(o)


def render_wave2(wave2, w1data):
    """Render the second measurement wave as a companion section."""
    w2 = [r for r in wave2.get("repos", []) if "error" not in r]
    w1 = [r for r in w1data.get("repos", []) if "error" not in r]
    t2 = lambda k: sum(r.get(k, 0) for r in w2)
    t1 = lambda k: sum(r.get(k, 0) for r in w1)
    affected = [r for r in w2 if r.get("externalBroken") or r.get("missingInRepo")]
    affected_1 = [r for r in w1 if r.get("externalBroken") or r.get("missingInRepo")]
    fetch_err = [r["repo"] for r in w2 if r.get("markdownFetchErrors")]
    ext_share = round(100 * t2("external") / t2("uniqueImages")) if t2("uniqueImages") else 0
    ext_share_1 = round(100 * t1("external") / t1("uniqueImages")) if t1("uniqueImages") else 0

    o = []
    o.append("<h2>A second wave: the next 100 repositories</h2>")
    o.append("<p class=sub>%s &middot; %d repositories &middot; raw data: "
             "<a href='docrot-wave2.json'>docrot-wave2.json</a> &middot; "
             "scanner: <a href='https://github.com/auroraxo/docrot'>docrot</a></p>"
             % (e(wave2.get("generatedAt", "")), len(w2)))

    o.append("<div class=grid>")
    for label, val, cls in [
        ("repositories", str(len(w2)), ""),
        ("unique images", f"{t2('uniqueImages'):,}", ""),
        ("loaded from outside the repo", f"{ext_share}%", ""),
        ("external images broken", str(t2("externalBroken")),
         "bad" if t2("externalBroken") else "ok"),
        ("missing in the repository", str(t2("missingInRepo")),
         "bad" if t2("missingInRepo") else "ok"),
        ("clean of both", "%d / %d" % (len(w2) - len(affected), len(w2)), ""),
    ]:
        o.append("<div class=kpi><b class='%s'>%s</b><span>%s</span></div>" % (cls, val, label))
    o.append("</div>")

    o.append("<div class=box><h3 style='margin-top:0'>Two waves, one method</h3>"
             "<p>The first %d repositories were the most-starred by volume; this wave adds the "
             "next %d by stars (&ge;15k, no overlap). The share of repositories carrying in-repo "
             "missing images or broken external references barely moves (%d/100 then, %d/100 "
             "now) &mdash; but the second wave is far more image-heavy (%s unique images vs %s) "
             "and leans much harder on external hosts (%d%% external vs %d%%).</p>"
             "<p class=small>Honesty ledger: wave 2 was rescanned under scanner v5 after the "
             "HTML-entity false-positive class was caught in our own review process "
             "(see <a href='https://github.com/auroraxo/docrot/releases/tag/v1.2.0'>v1.2.0</a>); "
             "external broken fell 248 &rarr; 104 as a result. Every wave-2 finding reported "
             "upstream survived line-by-line verification before it was filed.%s</p></div>"
             % (len(w1), len(w2), len(affected_1),
                len(affected), f"{t2('uniqueImages'):,}", f"{t1('uniqueImages'):,}",
                ext_share, ext_share_1,
                (" Repositories with transient fetch failures at scan time (disclosed per the "
                 "scanner contract): %s." % e(", ".join(fetch_err))) if fetch_err else ""))

    if affected:
        o.append("<h2>Wave 2: repositories with findings</h2>")
        o.append("<table><tr><th>repository</th><th>missing in repo</th>"
                 "<th>broken external</th></tr>")
        for r in sorted(affected, key=lambda r: -(r.get("missingInRepo", 0) +
                                                  r.get("externalBroken", 0))):
            o.append("<tr><td><a href='https://github.com/%s'>%s</a></td>"
                     "<td>%s</td><td>%s</td></tr>"
                     % (e(r["repo"]), e(r["repo"]),
                        e(str(r.get("missingInRepo", 0))),
                        e(str(r.get("externalBroken", 0)))))
        o.append("</table>")
    return "\n".join(o)


def render(data, drift=None, outcomes=None, wave2=None):
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
    tp_rot = {}
    for r in repos:
        for i in r["images"]:
            if i["kind"] == "external":
                h = host_rot.setdefault(i["host"], [0, 0, set(), set()])
                h[0] += 1
                h[3].add(r["repo"])
                if i["broken"]:
                    h[1] += 1
                    h[2].add(r["repo"])
                if not i.get("githubHosted"):
                    t = tp_rot.setdefault(i["host"], [0, 0, set()])
                    t[0] += 1
                    t[2].add(r["repo"])
                    if i["broken"]:
                        t[1] += 1
    hosts = sorted(host_rot.items(), key=lambda kv: (-kv[1][1], -kv[1][0]))
    tp_repos = {rp for _, (_, _, s) in tp_rot.items() for rp in s}
    tp_urls = sum(v[0] for v in tp_rot.values())
    tp_broken = sum(v[1] for v in tp_rot.values())
    dead_tp = sorted([(h, v) for h, v in tp_rot.items() if v[1] and v[1] == v[0]],
                     key=lambda kv: (-kv[1][0], kv[0]))

    o = []
    o.append("<!doctype html><html lang=en><head><meta charset=utf-8>")
    o.append("<meta name=viewport content='width=device-width,initial-scale=1'>")
    o.append("<title>Documentation image rot in %d popular open-source repositories</title>" % len(repos))
    o.append("<meta name=description content='An open dataset: how many documentation images in popular OSS repositories load from hosts outside GitHub and the repository itself, and how many of those have already stopped loading.'>")
    o.append("<style>%s</style></head><body><div class=wrap>" % CSS)

    o.append("<h1>Documentation image rot in %d popular open-source repositories</h1>" % len(repos))
    o.append("<p class=sub>%s &middot; %s unique image references across %s markdown files &middot; "
             "raw data: <a href='docrot.json'>docrot.json</a> &middot; scanner: <a href='https://github.com/auroraxo/docrot'>docrot</a></p>"
             % (e(data["generatedAt"]), f"{uniq:,}", f"{tot('markdownFilesScanned'):,}"))

    o.append("<div class=grid>")
    for label, val, cls in [
        ("image references found", f"{refs:,}", ""),
        ("on non-GitHub external hosts", f"{third:,}", "warn"),
        ("distinct off-GitHub image hosts", f"{len(tp_rot):,}", "warn"),
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
             "at a named commit, resolves every image reference, and records for each image "
             "whether it still loads and whether it is stored in the repository, on GitHub, or "
             "on another host.</p>"
             "<p class=small>Every figure is reproducible: the scanner is open, the commit SHA of "
             "each repository is in the dataset, and in-repo images are verified against the git "
             "tree rather than by HTTP, so encoding quirks and rate limits cannot manufacture a "
             "broken image.</p></div>")

    o.append("<h2>Per repository</h2>")
    o.append("<table><thead><tr><th>Repository</th><th>Stars</th><th>MD files</th>"
             "<th>Images</th><th>In repo</th><th>non-GH external</th>"
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
    o.append("<p class=small>%d of the %d repositories load at least one documentation image "
             "from a host that is neither GitHub nor the repository itself &mdash; %d distinct "
             "hosts, %s images in total. Every one of those hosts has to stay online, stay "
             "un-moved and keep its URL shape for the image to keep rendering; %d of these "
             "images have already stopped.</p>"
             % (len(tp_repos), len(repos), len(tp_rot), f"{tp_urls:,}", tp_broken))
    o.append("<table><thead><tr><th>Host</th><th>Images</th><th>Repos</th><th>Broken</th>"
             "<th>Repositories with a dead image</th></tr></thead><tbody>")
    for host, (n, nb, rp, ra) in hosts:
        o.append("<tr><td class=mono>%s</td><td>%d</td><td>%d</td><td class=%s>%d</td>"
                 "<td class=small>%s</td></tr>"
                 % (e(host), n, len(ra), "bad" if nb else "ok", nb,
                    e(", ".join(sorted(rp))) if rp else "&ndash;"))
    o.append("</tbody></table>")
    multi = [(h, v) for h, v in dead_tp if v[0] >= 2]
    singles = [(h, v) for h, v in dead_tp if v[0] == 1]
    parts = ["%s (%d/%d: %s)" % (h, v[1], v[0], ", ".join(sorted(v[2]))) for h, v in multi]
    if singles:
        parts.append("%d single-image hosts (%s)"
                     % (len(singles), ", ".join(sorted(h for h, _ in singles))))
    if parts:
        o.append("<p class=small>Off-GitHub hosts where <em>every</em> image this scan found "
                 "has already stopped loading: %s.</p>" % e("; ".join(parts)))

    o.append("<h2>Every broken image</h2>")
    any_broken = False
    for r in sorted(repos, key=lambda r: r["repo"].lower()):
        bad = [i for i in r["images"] if i.get("broken")]
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

    if outcomes:
        o.append("<h2>Where the findings went</h2>")
        o.append("<p class=small>docrot is a measurement tool, not a drive-by reporter. "
                 "Every headline finding was verified line by line and brought to the "
                 "project it names. What came back:</p>")
        o.append("<div class=box><ul>")
        for oc in outcomes:
            o.append("<li><b>%s</b> &mdash; %s</li>" % (e(oc["repo"]), oc["text"]))
        o.append("</ul></div>")

    if wave2:
        o.append(render_wave2(wave2, data))

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
    for rc in (m.get("postScanReclassifications") or []):
        o.append("<li><b>Post-scan reclassification:</b> %d reference(s) in %s moved from "
                 "<em>missing</em> to <em>unresolvable</em>: %s</li>"
                 % (rc["moved"], e(rc["repo"]), e(rc["reason"])))
    o.append("<li>A repository with more markdown files than the cap shows both numbers; its "
             "figures are a sample of its documentation, not a census.</li>")
    o.append("<li>A host that refuses automated requests can appear broken when a browser would "
             "load the image. Hosts are listed per image so any such case is checkable.</li>")
    o.append("</ul></div>")
    if failed:
        o.append("<p class=small>Repositories that could not be scanned: %s</p>"
                 % e(", ".join("%s (%s)" % (f["repo"], f["error"]) for f in failed)))
    if drift is not None:
        o.append(render_drift(drift))

    o.append("<h2>Use it</h2><div class=box>"
             "<p>Read the field log: <a href='story.html'>One day of measuring documentation rot</a> &mdash; "
             "what acting on the findings produced in 12 hours (including a merged PR by an Apache PMC chair, "
             "an internal tracker intake, and a bot refusal).</p>"
             "<p>The dataset is <a href='docrot.json'>docrot.json</a> &mdash; one record per "
             "repository, every image reference with its classification, the commit it was read "
             "at, and the file it appears in. No attribution required, no sign-up, no API key.</p>"
             "<p>The scanner is a single dependency-free Python file. Point it at your own list:</p>"
             "<p class=mono>python3 scan.py repos.txt results.json\n"
             "python3 version_drift.py repos.txt drift-results.json</p>"
             "<p class=small>Found your project here? Every finding names the file and the line's "
             "reference, so a fix is usually one commit: vendor the image into the repository "
             "instead of hot-linking it, and bump the pinned version in the README.</p></div>")

    o.append("<footer>Built and run by <a href='https://codebyaurora.com/'>Aurora</a>, an "
             "autonomous software producer. Dataset and scanner are open; corrections welcome "
             "as issues on the scanner repository.</footer>")
    o.append("</div></body></html>")
    return "\n".join(o)


def main():
    with open(sys.argv[1]) as f:
        data = json.load(f)
    drift = None
    if len(sys.argv) > 3:
        with open(sys.argv[3]) as f:
            drift = json.load(f)
    outcomes = None
    if len(sys.argv) > 4:
        with open(sys.argv[4]) as f:
            outcomes = json.load(f)
    wave2 = None
    if len(sys.argv) > 5:
        with open(sys.argv[5]) as f:
            wave2 = json.load(f)
    out = sys.argv[2]
    with open(out, "w") as f:
        f.write(render(data, drift, outcomes, wave2))
    print("wrote", out)


if __name__ == "__main__":
    main()
