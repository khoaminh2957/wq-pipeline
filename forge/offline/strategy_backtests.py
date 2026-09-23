"""Retrospective measurements for the efficiency strategies (A3, A4, A5, B6, B7, B8) on the forge
journal, chronological per (composite, cell) pair. Read-only; prints one block per strategy."""
from __future__ import annotations

import collections
import glob
import pathlib
import re
import statistics
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from forge import allocate as AL, harvest as HV, score as SC  # noqa: E402


def main() -> int:
    rows = HV.forge_rows()

    def key(r):
        m = r.get("meta") or {}
        s = r.get("settings") or {}
        return AL.pair_key(m.get("hypothesis"), s.get("region"), s.get("delay"), m.get("category"))

    seq = collections.defaultdict(list)
    for a, r in sorted(rows.items(), key=lambda t: t[1].get("dateCreated") or ""):
        if (r.get("meta") or {}).get("forge") and isinstance(r.get("sharpe"), (int, float)):
            seq[key(r)].append(r)

    def passed(r):
        return SC.stage(r)["stage"] not in ("fail", "incomplete")

    def q(xs, p):
        xs = sorted(xs)
        return xs[int(p * (len(xs) - 1))] if xs else None

    # A3 — when does a pair first show a strong row?
    idx1, idx3, within10 = [], [], 0
    for k, rs in seq.items():
        sh = [r["sharpe"] for r in rs]
        i1 = next((i for i, v in enumerate(sh, 1) if v >= 1.0), None)
        i3 = next((i for i, v in enumerate(sh, 1) if v >= 1.3), None)
        if i1:
            idx1.append(i1)
            within10 += i1 <= 10
        if i3:
            idx3.append(i3)
    print("A3 first row >=1.0: pairs %d, draw index p50 %s p90 %s, within the first 10 draws: %d/%d" % (
        len(idx1), statistics.median(idx1) if idx1 else None, q(idx1, 0.9), within10, len(idx1)))
    print("A3 first row >=1.3: pairs %d, draw index p50 %s p90 %s" % (len(idx3), statistics.median(idx3) if idx3 else None, q(idx3, 0.9)))
    gap = [max(r["sharpe"] for r in rs[:20]) - max(r["sharpe"] for r in rs[:10]) for rs in seq.values() if len(rs) >= 20]
    print("A3 max(first 20) - max(first 10): pairs %d, p50 %.2f p90 %.2f" % (len(gap), statistics.median(gap), q(gap, 0.9)))

    # A5 — DEAD threshold variants; A4 — first-wave rule
    for thr in (40, 60, 100):
        killed = saved = later_pass = near_after = 0
        for k, rs in seq.items():
            best, p = -9, 0
            for i, r in enumerate(rs, 1):
                best = max(best, r["sharpe"])
                p += passed(r)
                if i >= thr and p == 0 and best < 1.0:
                    later = rs[i:]
                    killed += 1
                    saved += len(later)
                    later_pass += sum(passed(x) for x in later)
                    near_after += any(x["sharpe"] >= 1.3 for x in later)
                    break
        print("A5 DEAD at %3d sims (best<1.0): pairs killed %d, sims saved %d, later passes %d, later near-miss rows %d" % (thr, killed, saved, later_pass, near_after))
    cut = saved = lp = 0
    for k, rs in seq.items():
        if len(rs) >= 100 and max(r["sharpe"] for r in rs[:100]) < 0.8:
            cut += 1
            saved += len(rs) - 100
            lp += sum(passed(x) for x in rs[100:])
    print("A4 wave rule (max of the first 100 < 0.8 -> stop): pairs %d, sims saved %d, later passes %d" % (cut, saved, lp))

    # B6 — settings effects by cell
    def grp(r):
        m = re.findall(r"\), (industry|subindustry|sector)\)", r["formula"] or "")
        return m[0] if m else "?"
    cells = collections.defaultdict(list)
    for k, rs in seq.items():
        cells[(k[1], k[2])].extend(rs)
    print("B6 mean Sharpe by setting on cells with >= 200 rows (mean, n):")
    for c, rs in sorted(cells.items(), key=lambda t: -len(t[1])):
        if len(rs) < 200:
            continue

        def by(f):
            g = collections.defaultdict(list)
            for r in rs:
                g[f(r)].append(r["sharpe"])
            return {kk: (round(statistics.mean(v), 2), len(v)) for kk, v in g.items() if len(v) >= 15}
        print("  %-8s %-14s n %4d | neut %s | decay %s | group %s" % (
            c[0], c[1], len(rs), by(lambda r: r["settings"].get("neutralization")), by(lambda r: r["settings"].get("decay")), by(grp)))

    # B8 — ladder-only failures above the Sharpe line, by decay
    lad = collections.defaultdict(list)
    for rs in seq.values():
        for r in rs:
            st = SC.stage(r)
            if r["sharpe"] >= 1.58 and st["stage"] == "fail" and set(st["failed"]) <= {"IS_LADDER_SHARPE", "LOW_2Y_SHARPE"}:
                v = next((c.get("value") for c in r["checks"] if isinstance(c, dict) and c.get("name") == "IS_LADDER_SHARPE"), None)
                lad[r["settings"].get("decay")].append(v)
    print("B8 rows with Sharpe >= 1.58 failing only ladder/2Y, by decay (n, median ladder): %s" % {
        d: (len(v), round(statistics.median([x for x in v if x is not None]), 2) if any(x is not None for x in v) else None) for d, v in lad.items()})

    # B7 — weakest single leg vs composite outcome on the same cell
    singles = collections.defaultdict(list)
    comp_rows = collections.defaultdict(list)
    for k, rs in seq.items():
        hyp = k[0] or ""
        if "_x_" in hyp:
            comp_rows[k].extend(r["sharpe"] for r in rs)
        elif not hyp.startswith("ens:"):
            singles[(hyp, k[1])].extend(r["sharpe"] for r in rs)
    legs_of = {}
    for f in glob.glob(str(ROOT / "forge/composites/*.yaml")):
        d = yaml.safe_load(open(f))
        legs_of[d["id"]] = d["legs"]
    out = []
    for k, sh in comp_rows.items():
        legs = legs_of.get(k[0], [])
        ms = [statistics.median(singles[(leg, k[1])]) for leg in legs if singles.get((leg, k[1]))]
        if legs and len(ms) == len(legs):
            out.append((min(ms), statistics.median(sh), max(sh), k[0][:34], k[1]))
    out.sort()
    print("B7 composite outcome vs its weakest leg's single-leg median on the same cell (%d composites with all legs measured):" % len(out))
    for w, m, mx, c, cell in out:
        print("   weakest leg %.2f -> composite p50 %.2f max %.2f  %s %s" % (w, m, mx, c, cell))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
