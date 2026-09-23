#!/usr/bin/env python3
"""gen_fresh_nonpv1_sweep.py — FRESH non-pv1 roots for the active USA theme (TOP1000 d1,
non-pv1, HT ratio). Two event-driven / hard-to-arbitrage families the crowded factor
classics couldn't touch. Options fields have ~0.98 coverage on liquid TOP1000 names, so
they DON'T concentrate in the excluded small-cap tail (the sub-universe killer).

OPTIONS-IV (sign committed to the paper; a negative sim is informative, not a flip license):
  O1 skew x VRP (bearish): high put-call skew (Xing-Zhang-Zhao 2010 smirk -> LOW returns)
       AND high IV/HV ex-earnings ratio (Bali-Hovakimian variance premium -> LOW returns)
       => reverse the double-bearish product (short high-skew high-VRP).
  O2 IV-change (An-Ang-Bali-Cakici 2014): a FALLING 30d IV predicts HIGHER returns; take it
       where the IV level is elevated (more room to fall). long -d(IV) x rank(IV percentile).
  O3 informed put activity: low skew (bullish) confirmed by heavy put volume (informed flow).

PEAD event-timing (the validated entry-logic lesson: SLOW signal + trade_when event clock):
  age = days_from_last_change(quarterly EPS actual) = days since the last earnings report.
  P1 SUE drift: enter the standardized-surprise signal in the post-announcement window
       (Bernard-Thomas PEAD drifts ~1-3 months), hold, exit after ~9 months (drift exhausted).
  P2 SUE x announcement-move: surprise confirmed by a large realized announcement move.
"""
from __future__ import annotations
import json, pathlib, itertools

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "state/funnel/fresh_nonpv1_stage1_targets.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

SKEW="opt6_slope"; VRP="opt6_ivhvxernratio"; IVL="opt6_ivpctile1y"; IV1="opt6_vimta1m"; PVOL="opt6_pvolu"
SUE="mdl177_v1_400_sue"; EPS="anl4_fs_actuals_basic_qf_nd_eps_value"; AMOVE="absolute_average_announcement_percent_move"

ROOTS = {
    "O1_skew_vrp":  f"reverse(multiply(rank({SKEW}), rank({VRP})))",
    "O2_ivchg":     f"multiply(rank(reverse(ts_delta({IV1}, 21))), rank({IVL}))",
    "O3_skew_pvol": f"multiply(rank(reverse({SKEW})), rank({PVOL}))",
    "P2_sue_move":  f"multiply(rank({SUE}), rank({AMOVE}))",
}
# PEAD event-timing needs the earnings age clock -> semicolon form
PEAD = {
    "P1_sue_evt":  f"age = days_from_last_change({EPS}); trade_when(age < 63, rank({SUE}), age > 189)",
    "P1b_sue_evt2": f"age = days_from_last_change({EPS}); trade_when(age < 42, rank({SUE}), age > 252)",
}

def settings(neut, trunc, decay):
    return {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP1000", "delay": 1,
            "decay": decay, "neutralization": neut, "truncation": trunc,
            "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
            "maxTrade": "OFF", "maxPosition": "OFF", "language": "FASTEXPR",
            "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31"}

rows, seen = [], set()
def add(tag, formula, neut, trunc, decay):
    k = ("".join(formula.split()), neut, trunc, decay)
    if k in seen: return
    seen.add(k)
    oid = f"fnp_{tag}_{len(rows):03d}"
    rows.append({"old_id": oid, "id": oid, "formula": formula + "\n", "settings": settings(neut, trunc, decay)})

NEUT4 = ["MARKET", "SECTOR", "INDUSTRY", "SUBINDUSTRY"]
# Block A: options + P2 roots x full neut x decay at trunc 0.05
for name, f in ROOTS.items():
    for neut, decay in itertools.product(NEUT4, [0, 8, 16]):
        add(name, f, neut, 0.05, decay)                 # 4*4*3 = 48
# Block B: same roots x trunc extremes at mid settings
for name, f in ROOTS.items():
    for neut, trunc in itertools.product(["SECTOR", "INDUSTRY"], [0.02, 0.08]):
        add(name, f, neut, trunc, 8)                    # 4*2*2 = 16
# Block C: PEAD event-timing x neut x decay
for name, f in PEAD.items():
    for neut, decay in itertools.product(NEUT4, [0, 8, 16]):
        add(name, f, neut, 0.05, decay)                 # 2*4*3 = 24
# Block D: PEAD trunc extremes (reach >=90, more turnover-band coverage)
for name, f in PEAD.items():
    for trunc in [0.02, 0.08]:
        add(name, f, "INDUSTRY", trunc, 8)              # 2*2 = 4

json.dump(rows, open(OUT, "w"), indent=1)
print(f"wrote {len(rows)} rows -> {OUT}")
from collections import Counter
print("by root:", dict(Counter("_".join(r["old_id"].split("_")[1:3]) for r in rows)))
