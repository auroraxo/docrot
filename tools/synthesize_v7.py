#!/usr/bin/env python3
"""300-repo synthesis across scanner schemas v5 / v6 / v7.

Committed BEFORE the v7 rescan results existed (methodology-first, same
discipline as ca09948 for the v5->v6 comparison): the rollup, the mover
diffs and the hard expectations are fixed code, not improvised after
seeing numbers.

Report metric (the one behind the published 26-30% band): a repository
carries rot when externalBroken + missingInRepo > 0 (externalBroken
includes GitHub-owned hosts; unresolvable refs are excluded upstream).

Hard expectations — encoded so a surprise is a signal, not a silent pass:

  E1  anthropics/skills (wave 2): v6 carried uniq=2, missing=1 — the one
      known phantom ('path from flow root', a code-span example GitHub
      renders as <code>). Under v7 (CommonMark inline-code pairing,
      docrot v1.5.1/v1.5.2) missing MUST be 0. If it is not, the phantom
      class is not closed and nothing gets published.
  E2  webpack/webpack (wave 1): v6 uniq=327 (47 reference-style badge
      defs recovered). v7 uniq must stay 327: the pairing fix must not
      re-drop any legitimately-extracted reference. If it drops, the
      fix over-strips and nothing gets published.

Usage:
    python3 tools/synthesize_v7.py [output.md]     # stdout if no arg
Exit codes:
    0  synthesis complete, expectations passed
    2  inputs incomplete (v7 waves still scanning)
    3  synthesis ran but an expectation FAILED (do not publish)
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WAVES = {
    1: ("docrot-results-100.json", "docrot-results-wave1-v6.json",
        "docrot-results-wave1-v7.json"),
    2: ("docrot-results-wave2.json", "docrot-results-wave2-v6.json",
        "docrot-results-wave2-v7.json"),
    3: ("docrot-results-wave3.json", "docrot-results-wave3-v6.json",
        "docrot-results-wave3-v7.json"),
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
    """Diff lines describing what changed between two scans of one repo."""
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

    # ---- gate: refuse partial inputs, tell the caller what is missing ----
    missing = []
    for w, (_, _, f7) in WAVES.items():
        loaded = load(f7)
        if loaded is None:
            missing.append(f"{f7} (file absent)")
            continue
        repos, total = loaded
        if total < EXPECTED_REPOS:
            missing.append(f"{f7} ({total}/{EXPECTED_REPOS} repos)")
    if missing:
        print("INCOMPLETE — synthesis is gated until all v7 waves finish:")
        for m in missing:
            print("  -", m)
        return 2

    lines = ["# 300-repo synthesis: v5 -> v6 -> v7 (report metric)", ""]

    # ---- per-wave and total rot share ----
    lines.append("## Rot share (externalBroken + missingInRepo > 0)")
    lines.append("")
    lines.append("| wave | v5 | v6 | v7 |")
    lines.append("|---|---|---|---|")
    tot5 = tot6 = tot7 = totn = 0
    uniq5 = uniq6 = uniq7 = 0
    for w, (f5, f6, f7) in WAVES.items():
        d5, d6, d7 = load(f5)[0], load(f6)[0], load(f7)[0]
        slugs = set(d5) & set(d6) & set(d7)
        n = len(slugs)
        c5 = sum(1 for s in slugs if rot(d5[s]))
        c6 = sum(1 for s in slugs if rot(d6[s]))
        c7 = sum(1 for s in slugs if rot(d7[s]))
        u5 = sum(d5[s].get("uniqueImages", 0) for s in slugs)
        u6 = sum(d6[s].get("uniqueImages", 0) for s in slugs)
        u7 = sum(d7[s].get("uniqueImages", 0) for s in slugs)
        tot5 += c5; tot6 += c6; tot7 += c7; totn += n
        uniq5 += u5; uniq6 += u6; uniq7 += u7
        lines.append(f"| {w} | {c5}/{n} ({c5/n:.0%}) | {c6}/{n} ({c6/n:.0%}) "
                     f"| {c7}/{n} ({c7/n:.0%}) |")
    lines.append(f"| **TOTAL** | **{tot5}/{totn} ({tot5/totn:.1%})** "
                 f"| **{tot6}/{totn} ({tot6/totn:.1%})** "
                 f"| **{tot7}/{totn} ({tot7/totn:.1%})** |")
    lines.append("")
    lines.append(f"Unique images over 300 repos: v5 {uniq5} / v6 {uniq6} / v7 {uniq7}.")
    lines.append("")

    # ---- movers v6 -> v7, with diff material for manual classification ----
    lines.append("## Rot-set movers v6 -> v7 (each requires manual classification "
                 "before publishing: 429/502 window drift vs upstream content "
                 "drift vs extraction change)")
    lines.append("")
    mover_count = 0
    for w, (_, f6, f7) in WAVES.items():
        d6, d7 = load(f6)[0], load(f7)[0]
        slugs = set(d6) & set(d7)
        gain = sorted(s for s in slugs if rot(d7[s]) and not rot(d6[s]))
        lose = sorted(s for s in slugs if rot(d6[s]) and not rot(d7[s]))
        if gain or lose:
            lines.append(f"### wave {w}")
            for s in gain:
                mover_count += 1
                lines.append(f"  GAINED {s} (broken {d6[s].get('externalBroken')} -> "
                             f"{d7[s].get('externalBroken')}, missing "
                             f"{d6[s].get('missingInRepo')} -> {d7[s].get('missingInRepo')})")
                lines += lines_for_mover(s, d6[s], d7[s])
            for s in lose:
                mover_count += 1
                lines.append(f"  LOST   {s} (broken {d6[s].get('externalBroken')} -> "
                             f"{d7[s].get('externalBroken')}, missing "
                             f"{d6[s].get('missingInRepo')} -> {d7[s].get('missingInRepo')})")
                lines += lines_for_mover(s, d6[s], d7[s])
            lines.append("")
    if mover_count == 0:
        lines.append("(none — rot sets identical between v6 and v7 on all three waves)")
        lines.append("")

    # ---- hard expectations gate ----
    lines.append("## Hard expectations")
    failures = []
    d2v6, d2v7 = load(WAVES[2][1])[0], load(WAVES[2][2])[0]
    sk = "anthropics/skills"
    m7 = d2v7.get(sk, {}).get("missingInRepo")
    if m7 == 0:
        lines.append(f"- [PASS] E1 phantom gone: {sk} missingInRepo v7 = 0 "
                     f"(was {d2v6.get(sk, {}).get('missingInRepo')} in v6)")
    else:
        failures.append(f"E1 FAILED: {sk} missingInRepo v7 = {m7} — phantom class "
                        "NOT closed; DO NOT PUBLISH")
        lines.append(f"- [FAIL] {failures[-1]}")
    d1v6, d1v7 = load(WAVES[1][1])[0], load(WAVES[1][2])[0]
    wk = "webpack/webpack"
    u7 = d1v7.get(wk, {}).get("uniqueImages")
    if u7 == 327:
        lines.append(f"- [PASS] E2 no over-strip: {wk} uniqueImages v7 = 327 "
                     "(47 recovered reference defs intact)")
    else:
        failures.append(f"E2 FAILED: {wk} uniqueImages v7 = {u7}, expected 327 — "
                        "pairing fix may over-strip; DO NOT PUBLISH")
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
    print("EXPECTATION GATE: GREEN — movers above still need manual "
          "classification before any story change.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
