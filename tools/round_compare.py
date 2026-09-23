#!/usr/bin/env python3
"""Did this round beat the last one? Answered with a number, and with the confound named.

Every "we improved" claim in this project has had the same shape: a rate computed over a pooled
batch, compared against a rate computed over a differently-composed pooled batch. Two of those
reversed sign once pooled within the confounding variable (3.38% vs 4.86% raw, 4.16% vs 3.05%
within cell), so an uncontrolled comparison here has no verdict — it has a number that looks like
one.

WHAT THIS DOES

  * Groups journal rows by generation FAMILY (meta.family, falling back to the old_id prefix for
    the 98% of rows written before treatment was journaled).
  * Reports, per family: n, strict zero-fail (gate_lib's presence-checked rule), median Sharpe,
    and P(Sharpe >= 1.58) — the USA d1 bar.
  * For the cell-targeted families it ALSO reports within-cell, because the cells differ enormously
    in difficulty (Imbalance median 1.46 against Short Interest -0.17 in the same round) and a
    pooled cell comparison measures which cells a round happened to sample.
  * Prints a Wilson 95% interval on the zero-fail rate, so "0 of 252" is visibly different from
    "0 of 12". A rate with an interval spanning the comparison is NOT an improvement.

WHAT IT DELIBERATELY DOES NOT DO

  It does not declare a winner on medians alone. A median Sharpe that rises while zero-fail stays
  at 0 means the round got closer to the bar without clearing it, and only the second of those is
  the deliverable.

  python3 tools/round_compare.py                    # every family
  python3 tools/round_compare.py --cells            # cell-targeted families, split by cell
"""
import argparse, collections, json, math, pathlib, re, statistics, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "funnel"))
import gate_lib as G                                                    # noqa: E402

BAR = 1.58


def wilson(k, n, z=1.96):
    """95% interval for a rate. 0/12 and 0/252 are not the same evidence and must not print alike."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    s = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - s) / d, (c + s) / d)


def load():
    byid = {}
    for line in open(ROOT / "state/resim_results.jsonl"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("old_id"):
            byid[d["old_id"]] = d              # last write wins; 4,868 lines are re-writes
    return byid


def famof(oid, d):
    m = d.get("meta") or {}
    if m.get("family"):
        return m["family"]
    if m.get("kind"):
        return m["kind"]
    p = re.match(r"^([A-Za-z]+)", oid or "")
    return f"prefix:{p.group(1)}" if p else "?"


def summarise(rows):
    ev = [d for d in rows if d.get("checks")]
    sh = [d["sharpe"] for d in ev if isinstance(d.get("sharpe"), (int, float))]
    zf = sum(1 for d in ev if G.gate_status(d)["zero_fail"])
    lo, hi = wilson(zf, len(ev))
    return {
        "n": len(ev),
        "zf": zf,
        "zf_rate": zf / len(ev) if ev else 0.0,
        "zf_lo": lo, "zf_hi": hi,
        "med": statistics.median(sh) if sh else float("nan"),
        "p_bar": sum(1 for x in sh if x >= BAR) / len(sh) if sh else 0.0,
    }


def line(label, s):
    return (f"  {label:26} n={s['n']:5}  zf={s['zf']:3} ({s['zf_rate']:6.2%} "
            f"[{s['zf_lo']:.2%},{s['zf_hi']:.2%}])  medSh={s['med']:6.2f}  P>=bar={s['p_bar']:6.1%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", action="store_true")
    ap.add_argument("--min-n", type=int, default=30)
    args = ap.parse_args()

    byid = load()
    fams = collections.defaultdict(list)
    for oid, d in byid.items():
        fams[famof(oid, d)].append(d)

    rows = [(f, summarise(v)) for f, v in fams.items()]
    rows = [(f, s) for f, s in rows if s["n"] >= args.min_n]
    rows.sort(key=lambda r: -r[1]["p_bar"])

    print(f"FAMILIES (n>={args.min_n}), ranked by P(Sharpe>={BAR}):")
    for f, s in rows:
        print(line(f[:26], s))

    if args.cells:
        print("\nWITHIN CELL — the pooled numbers above mix cells of very different difficulty:")
        cells = collections.defaultdict(lambda: collections.defaultdict(list))
        for oid, d in byid.items():
            c = (d.get("meta") or {}).get("cell")
            if c:
                cells[c][famof(oid, d)].append(d)
        for c in sorted(cells):
            print(f"\n  == {c} ==")
            for f, v in sorted(cells[c].items()):
                s = summarise(v)
                if s["n"]:
                    print("  " + line(f[:24], s))

    # The verdict is about the DELIVERABLE, which is a filled cell, not a median.
    total_zf = sum(s["zf"] for _, s in rows)
    print(f"\nDELIVERABLE: strict zero-fail across all families shown = {total_zf}")
    if total_zf == 0:
        print("  No round has produced a gate-passing alpha in these families. A rising median is")
        print("  movement toward the bar, not a result — say so rather than reporting the median.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
