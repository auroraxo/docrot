#!/usr/bin/env python3
"""Compare a v5 wave dataset with a v6 rescan of the same corpus.

Answers one question honestly: did the reference-image false-negative
class (fixed in scanner v6) hide rot? Reports per-repo reference deltas
and the corpus-level rot share (repos with >=1 broken image) under both
schemas. Pure read-only; prints a markdown summary and can write it.

Usage: python3 tools/compare_v5_v6.py OLD.json NEW.json [out.md]
"""
import json
import sys


def load(path):
    with open(path) as f:
        d = json.load(f)
    return {r["repo"]: r for r in d.get("repos", []) if "repo" in r and "error" not in r}


def rot_share(repos):
    """Repos with at least one broken image, over scanned repos."""
    scanned = [r for r in repos.values() if "brokenExternal" in r or "externalThirdPartyBroken" in r]
    hits = 0
    for r in scanned:
        broken = r.get("externalThirdPartyBroken", 0) + r.get("missingInRepo", 0)
        if broken > 0:
            hits += 1
    return hits, len(scanned)


def main():
    old = load(sys.argv[1])
    new = load(sys.argv[2])
    out_path = sys.argv[3] if len(sys.argv) > 3 else None

    common = sorted(set(old) & set(new))
    lines = ["# Scanner dataset comparison (older -> newer)", "",
             f"Repos compared: {len(common)} (of {len(old)} v5 / {len(new)} v6)", ""]

    grew_refs = 0
    grew_broken = 0
    ref_delta_total = 0
    rows = []
    for slug in common:
        o, n = old[slug], new[slug]
        oi, ni = o.get("uniqueImages", 0), n.get("uniqueImages", 0)
        ob = o.get("externalThirdPartyBroken", 0)
        nb = n.get("externalThirdPartyBroken", 0)
        om = o.get("missingInRepo", 0)
        nm = n.get("missingInRepo", 0)
        d = ni - oi
        if d:
            grew_refs += 1
            ref_delta_total += d
        if nb > ob or nm > om:
            grew_broken += 1
            rows.append((slug, oi, ni, ob, nb, om, nm))

    lines.append(f"Repos with NEW references found by the newer scan: {grew_refs} "
                 f"(+{ref_delta_total} unique images total)")
    lines.append(f"Repos with NEW broken findings under v6: {grew_broken}")
    if rows:
        lines += ["", "| repo | uniq old | uniq new | broken old | broken new | missing old | missing new |",
                  "|---|---|---|---|---|---|---|"]
        for r in rows:
            lines.append("| %s | %d | %d | %d | %d | %d | %d |" % r)

    oh, ot = rot_share(old)
    nh, nt = rot_share(new)
    lines += ["", f"Rot share (repos with >=1 broken): old {oh}/{ot} = {oh/ot:.0%}"
                  f" -> new {nh}/{nt} = {nh/nt:.0%}"]
    text = "\n".join(lines) + "\n"
    print(text, end="")
    if out_path:
        with open(out_path, "w") as f:
            f.write(text)
        print("written:", out_path, file=sys.stderr)


if __name__ == "__main__":
    main()
