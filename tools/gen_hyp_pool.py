#!/usr/bin/env python3
"""Emit a simulation pool from the meaning-gated cell hypotheses, varying the SETTINGS only.

state/cell_hypotheses.json holds 21 designs that survived a description-first design pass and an
adversarial meaning gate (39 of 60 were rejected). Each one is a claim about a market mechanic, so
the formula is not something to randomise — what is still unknown is the setting it wants.

The distinct settings grid is 3 neutralizations x 3 decays x 3 truncations = 27 per hypothesis,
567 rows in total, and the precheck refuses a duplicate formula+settings pair. So this walks the
grid with an offset and reports honestly when a hypothesis is exhausted rather than emitting rows
that will be refused at the door.

STATISTICAL is tried first: measured 24.1% prod-clean (n=294) against INDUSTRY 4.3% (n=351) and
SUBINDUSTRY 5.9% (n=136). That comparison is NOT pool-controlled, so it orders the grid rather
than restricting it.

  python3 tools/gen_hyp_pool.py --out state/autoloop/pool_hyp2.json --offset 12
"""
import argparse, collections, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import opcheck                                                          # noqa: E402

HYP = ROOT / "state/cell_hypotheses.json"
SETTINGS = {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1,
            "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
            "maxTrade": "OFF", "maxPosition": "OFF", "language": "FASTEXPR",
            "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31"}

# STATISTICAL ONLY. Measured 2026-08-10 on a BALANCED design — the same 21 formulas, the same
# decays and truncations, n=189 per arm, neutralization the only variable:
#
#     STATISTICAL   medSharpe 0.82   medLadder 0.61   P(sharpe>=1.58) 11.1%
#     SUBINDUSTRY             0.48             0.27                    0.0%
#     INDUSTRY                0.45             0.14                    0.0%
#
# This is a controlled comparison, not a pooled one, and the other two arms produced not one row
# above the bar in 378 attempts.
#
# The first version of this walked a grid ordered STATISTICAL-first, so every refill stepped
# FURTHER into the losing arms — a generator that degrades deterministically the longer it runs
# unattended. Its second round measured medSharpe 0.47 against the first round's 0.81.
#
# The consequence is that this family has only 9 settings per hypothesis (3 decays x 3
# truncations), 189 rows, and they are ALL SIMULATED. Saying so and returning nothing is correct;
# emitting the losing arms to look productive is not.
GRID = [("STATISTICAL", d, t) for d in (10, 16, 22) for t in (0.015, 0.02, 0.05)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="state/autoloop/pool_hyp.json")
    ap.add_argument("--offset", type=int, default=0, help="where in the 27-wide grid to start")
    ap.add_argument("--per", type=int, default=12)
    args = ap.parse_args()

    if not HYP.exists():
        print("no state/cell_hypotheses.json — nothing to emit")
        return 1
    hyps = json.load(open(HYP))
    sigs = opcheck.load_signatures()

    rows, exhausted = [], 0
    for hi, h in enumerate(hyps):
        f = h["formula"]
        if opcheck.check(f, sigs):
            continue                                  # never emit what the launcher will refuse
        cell = re.sub(r"[^A-Za-z]", "", h["cell"])[:4].upper()
        for k in range(args.per):
            idx = args.offset + k
            if idx >= len(GRID):
                exhausted += 1
                break
            n_, d_, t_ = GRID[idx]
            oid = f"HYP{cell}{hi:02d}_{idx:02d}"
            rows.append({"old_id": oid, "id": oid, "formula": f,
                         "settings": dict(SETTINGS, neutralization=n_, decay=d_, truncation=t_),
                         "meta": {"kind": "cell-hypothesis", "cell": h["cell"],
                                  "family": f"hyp:{h['cell']}", "name": h["name"][:60],
                                  "mechanic": h.get("mechanic", "")[:180]}})

    json.dump(rows, open(ROOT / args.out, "w"), indent=1)
    by = collections.Counter(r["meta"]["cell"] for r in rows)
    print(f"{len(rows)} rows -> {args.out}  {dict(by)}")
    if exhausted:
        print(f"   {exhausted} hypotheses hit the end of the 27-wide settings grid at offset "
              f"{args.offset} — they have nothing new left to try")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
