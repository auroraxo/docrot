#!/usr/bin/env python3
"""300-repo synthesis across scanner schemas v5 / v6 / v7 / v8.

Committed BEFORE the v8 rescan results exist (methodology-first, same
discipline as ca09948 for v6 and 88874d0 for v7): the rollup, the mover
diffs, and the hard expectations are fixed code, not improvised after
seeing numbers.

Report metric: rot when externalBroken + missingInRepo > 0.

Hard expectations — gates that prevent publishing if any phantom survives
or if real references are over-stripped:

  E1a airbnb/javascript (wave 2): v7 had missing=1 (react/hello.jpg, deep
      4-space fence inside list item). Under v8 missing MUST be 0.
  E1b jujumilk3/leaked-system-prompts (wave 3): v7 had missing=3 (including
      'URL' inside backticks shifted by odd backtick in prior item).
      Under v8 missing MUST be 2 (the two real missing images; 'URL' gone).
  E1c anthropics/skills (wave 2): v6 had missing=1 ('path from flow root').
      Under v8 missing MUST stay 0.
  E2  webpack/webpack (wave 1): uniqueImages MUST stay 327 (all 47 recovered
      reference defs intact).

Usage:
    python3 tools/synthesize_v8.py [output.md]     # stdout if no arg
Exit codes:
    0  synthesis complete, expectations passed
    2  inputs incomplete (v8 waves still scanning)
    3  synthesis ran but an expectation FAILED (do not publish)
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WAVES = {
    1: ("docrot-results-100.json", "docrot-results-wave1-v6.json",
        "docrot-results-wave1-v7.json", "docrot-results-wave1-v8.json"),
    2: ("docrot-results-wave2.json", "docrot-results-wave2-v6.json",
        "docrot-results-wave2-v7.json", "docrot-results-wave2-v8.json"),
    3: ("docrot-results-wave3.json", "docrot-results-wave3-v6.json",
        "docrot-results-wave3-v7.json", "docrot-results-wave3-v8.json"),
}

EXPECTED_REPOS = 100


def load(fname):
    path = os.path.join(BASE, fname)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    repos = data.get("repos", [])
    ok = [r for r in repos if "repo" in r and "error" not in r]
    return {r["repo"]: r for r in ok}, len(repos)


def rot(rec):
    return (rec.get("externalBroken", 0) + rec.get("missingInRepo", 0)) > 0


def broken_targets(rec):
    return {i["target"]: i for i in rec.get("images", []) if i.get("broken")}


def lines_for_mover(slug, old, new):
    out = []
    ob, nb = broken_targets(old), broken_targets(new)
    for t in sorted(set(nb) - set(ob)):
        i = nb[t]
        refs = [list(r) for r in i.get("refs", [])][:2]
        out.append(f"    + NEW-BROKEN kind={i.get('kind')} status={i.get('status')} "
                   f"{t[:100]} refs={refs}")
    for t in sorted(set(ob) - set(nb)):
        i = ob[t]
        out.append(f"    - LOST-BROKEN (was status={i.get('status')}) {t[:100]}")
    om = {i["target"] for i in old.get("images", []) if i.get("kind") == "missing"}
    nm = {i["target"] for i in new.get("images", []) if i.get("kind") == "missing"}
    for t in sorted(nm - om):
        out.append(f"    + NEW-MISSING {t[:100]}")
    for t in sorted(om - nm):
        out.append(f"    - LOST-MISSING {t[:100]}")
    return out


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else None

    missing = []
    for w, (_, _, _, f8) in WAVES.items():
        loaded = load(f8)
        if loaded is None:
            missing.append(f"{f8} (file absent)")
            continue
        repos, total = loaded
        if total < EXPECTED_REPOS:
            missing.append(f"{f8} ({total}/{EXPECTED_REPOS} repos)")
    if missing:
        print("INCOMPLETE — synthesis is gated until all v8 waves finish:")
        for m in missing:
            print("  -", m)
        return 2

    lines = ["# 300-repo synthesis: v5 -> v6 -> v7 -> v8 (report metric)", ""]

    lines.append("## Rot share (externalBroken + missingInRepo > 0)")
    lines.append("")
    lines.append("| wave | v5 | v6 | v7 | v8 |")
    lines.append("|---|---|---|---|---|")
    tot5 = tot6 = tot7 = tot8 = totn = 0
    uniq5 = uniq6 = uniq7 = uniq8 = 0
    for w, (f5, f6, f7, f8) in WAVES.items():
        d5 = load(f5)[0]
        d6 = load(f6)[0]
        d7 = load(f7)[0]
        d8 = load(f8)[0]
        slugs = set(d5) & set(d6) & set(d7) & set(d8)
        n = len(slugs)
        c5 = sum(1 for s in slugs if rot(d5[s]))
        c6 = sum(1 for s in slugs if rot(d6[s]))
        c7 = sum(1 for s in slugs if rot(d7[s]))
        c8 = sum(1 for s in slugs if rot(d8[s]))
        u5 = sum(d5[s].get("uniqueImages", 0) for s in slugs)
        u6 = sum(d6[s].get("uniqueImages", 0) for s in slugs)
        u7 = sum(d7[s].get("uniqueImages", 0) for s in slugs)
        u8 = sum(d8[s].get("uniqueImages", 0) for s in slugs)
        tot5 += c5; tot6 += c6; tot7 += c7; tot8 += c8; totn += n
        uniq5 += u5; uniq6 += u6; uniq7 += u7; uniq8 += u8
        lines.append(f"| {w} | {c5}/{n} ({c5/n:.0%}) | {c6}/{n} ({c6/n:.0%}) "
                     f"| {c7}/{n} ({c7/n:.0%}) | {c8}/{n} ({c8/n:.0%}) |")
    lines.append(f"| **TOTAL** | **{tot5}/{totn} ({tot5/totn:.1%})** "
                 f"| **{tot6}/{totn} ({tot6/totn:.1%})** "
                 f"| **{tot7}/{totn} ({tot7/totn:.1%})** "
                 f"| **{tot8}/{totn} ({tot8/totn:.1%})** |")
    lines.append("")
    lines.append(f"Unique images over 300 repos: v5 {uniq5} / v6 {uniq6} / v7 {uniq7} / v8 {uniq8}.")
    lines.append("")

    lines.append("## Rot-set movers v7 -> v8 (each requires manual classification)")
    lines.append("")
    mover_count = 0
    for w, (_, _, f7, f8) in WAVES.items():
        d7 = load(f7)[0]
        d8 = load(f8)[0]
        slugs = set(d7) & set(d8)
        gain = sorted(s for s in slugs if rot(d8[s]) and not rot(d7[s]))
        lose = sorted(s for s in slugs if rot(d7[s]) and not rot(d8[s]))
        if gain or lose:
            lines.append(f"### wave {w}")
            for s in gain:
                mover_count += 1
                lines.append(f"  GAINED {s} (broken {d7[s].get('externalBroken')} -> "
                             f"{d8[s].get('externalBroken')}, missing "
                             f"{d7[s].get('missingInRepo')} -> {d8[s].get('missingInRepo')})")
                lines += lines_for_mover(s, d7[s], d8[s])
            for s in lose:
                mover_count += 1
                lines.append(f"  LOST   {s} (broken {d7[s].get('externalBroken')} -> "
                             f"{d8[s].get('externalBroken')}, missing "
                             f"{d7[s].get('missingInRepo')} -> {d8[s].get('missingInRepo')})")
                lines += lines_for_mover(s, d7[s], d8[s])
            lines.append("")
    if mover_count == 0:
        lines.append("(none — rot sets identical between v7 and v8 on all three waves)")
        lines.append("")

    lines.append("## Hard expectations")
    failures = []

    # E1a: airbnb/javascript missing == 0 in wave 2 v8
    d2v7, d2v8 = load(WAVES[2][2])[0], load(WAVES[2][3])[0]
    ab = "airbnb/javascript"
    m_ab = d2v8.get(ab, {}).get("missingInRepo")
    if m_ab == 0:
        lines.append(f"- [PASS] E1a airbnb phantom gone: {ab} missingInRepo v8 = 0 "
                     f"(was {d2v7.get(ab, {}).get('missingInRepo')} in v7)")
    else:
        failures.append(f"E1a FAILED: {ab} missingInRepo v8 = {m_ab}, expected 0 — "
                        "deep fence phantom NOT closed; DO NOT PUBLISH")
        lines.append(f"- [FAIL] {failures[-1]}")

    # E1b: jujumilk3 missing == 2 in wave 3 v8 (was 3 in v7)
    d3v7, d3v8 = load(WAVES[3][2])[0], load(WAVES[3][3])[0]
    jj = "jujumilk3/leaked-system-prompts"
    m_jj = d3v8.get(jj, {}).get("missingInRepo")
    if m_jj == 2:
        lines.append(f"- [PASS] E1b jujumilk3 phantom gone: {jj} missingInRepo v8 = 2 "
                     f"(was {d3v7.get(jj, {}).get('missingInRepo')} in v7)")
    else:
        failures.append(f"E1b FAILED: {jj} missingInRepo v8 = {m_jj}, expected 2 — "
                        "list-item pairing phantom NOT closed; DO NOT PUBLISH")
        lines.append(f"- [FAIL] {failures[-1]}")

    # E1c: anthropics/skills missing == 0 in wave 2 v8
    sk = "anthropics/skills"
    m_sk = d2v8.get(sk, {}).get("missingInRepo")
    if m_sk == 0:
        lines.append(f"- [PASS] E1c skills phantom still gone: {sk} missingInRepo v8 = 0")
    else:
        failures.append(f"E1c FAILED: {sk} missingInRepo v8 = {m_sk}, expected 0; DO NOT PUBLISH")
        lines.append(f"- [FAIL] {failures[-1]}")

    # E2: webpack uniqueImages == 327 in wave 1 v8
    d1v7, d1v8 = load(WAVES[1][2])[0], load(WAVES[1][3])[0]
    wk = "webpack/webpack"
    u_wk = d1v8.get(wk, {}).get("uniqueImages")
    if u_wk == 327:
        lines.append(f"- [PASS] E2 no over-strip: {wk} uniqueImages v8 = 327 "
                     "(47 recovered reference defs intact)")
    else:
        failures.append(f"E2 FAILED: {wk} uniqueImages v8 = {u_wk}, expected 327; DO NOT PUBLISH")
        lines.append(f"- [FAIL] {failures[-1]}")

    lines.append("")
    text = "\n".join(lines) + "\n"
    if out_path:
        with open(out_path, "w") as f:
            f.write(text)
        print(f"wrote {out_path}")
    print(text)
    if failures:
        print("EXPECTATION GATE: RED — publication blocked.")
        return 3
    print("EXPECTATION GATE: GREEN — movers above still need manual classification.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
