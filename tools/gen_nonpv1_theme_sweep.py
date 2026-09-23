#!/usr/bin/env python3
"""gen_nonpv1_theme_sweep.py — NON-pv1 paper-grounded roots for the ACTIVE USA Power-Pool
theme (2026-07-13..07-26: USA d1 TOP1000, datasets_not_in pv1, require HT_HIGH_TURNOVER_RETURNS_RATIO).

Four 2-leg CROSS-FAMILY roots, all model77/model53 (non-pv1), Law-1-safe (>=2 legs, not a bare
re-rank of one factor), unambiguous single-direction signs:

  R1 momentum x low-distress  : long high 12-2 momentum AND low default-prob (quality-momentum;
                                distressed momentum is what crashes — Asness QMJ + Daniel-Moskowitz).
  R2 quality x earnings-surprise: long high gross-profitability AND positive SUE (Novy-Marx GP + PEAD).
  R3 short-fee x low-momentum : short high loan-fee AND recent losers (shorting premium concentrates
                                in hard-to-borrow losers — Drechsler, Cohen-Diether-Malloy).
  R4 low-accruals x quality   : long low change-in-NOA AND high gross-profitability (Sloan accruals +
                                Novy-Marx: reward real, not accrual-inflated, earnings).

Every operand is a [0,1] rank -> multiply stays bounded (Law-6 safe). Plus one if_else
opportunistic-SELECTION variant per root (the lesson: SLOW signals gain from tail-selection).
"""
from __future__ import annotations
import json, pathlib, itertools

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "state/funnel/nonpv1_theme_stage1_targets.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

MOM  = "mdl177_2_pricemomentumfactor_ff10mrtn"
PD   = "annualized_pd_1_year"
GP   = "gross_profit_to_assets_ratio"
SUE  = "mdl177_v1_400_sue"
FEE  = "mdl177_5shortsentimentfactor_benchmark_fee"
NOA  = "mdl77_chgnoa"

ROOTS = {
    "R1_mom_qual":  f"multiply(rank({MOM}), rank(reverse({PD})))",
    "R2_gp_sue":    f"multiply(rank({GP}), rank({SUE}))",
    "R3_fee_rev":   f"multiply(rank({FEE}), rank(reverse({MOM})))",
    "R4_acc_gp":    f"multiply(rank(reverse({NOA})), rank({GP}))",
}
# if_else opportunistic-selection: keep only high-conviction names where BOTH legs agree strongly
SEL = {
    "R1sel": f"a = rank({MOM}); b = rank(reverse({PD})); if_else(and(a > 0.6, b > 0.6), multiply(a, b), if_else(and(a < 0.4, b < 0.4), multiply(a, b), 0.25))",
    "R3sel": f"a = rank({FEE}); b = rank(reverse({MOM})); if_else(and(a > 0.6, b > 0.6), multiply(a, b), if_else(and(a < 0.4, b < 0.4), multiply(a, b), 0.25))",
    "R2sel": f"a = rank({GP}); b = rank({SUE}); if_else(and(a > 0.6, b > 0.6), multiply(a, b), if_else(and(a < 0.4, b < 0.4), multiply(a, b), 0.25))",
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
    oid = f"npt_{tag}_{len(rows):03d}"
    rows.append({"old_id": oid, "id": oid, "formula": formula + "\n", "settings": settings(neut, trunc, decay)})

NEUT4 = ["MARKET", "SECTOR", "INDUSTRY", "SUBINDUSTRY"]
# Block A: 4 roots x full neut x decay grid at trunc 0.05
for name, f in ROOTS.items():
    for neut, decay in itertools.product(NEUT4, [0, 8, 16]):
        add(name, f, neut, 0.05, decay)                 # 4*4*3 = 48
# Block B: 4 roots x trunc extremes at mid neut/decay
for name, f in ROOTS.items():
    for neut, trunc in itertools.product(["SECTOR", "INDUSTRY"], [0.02, 0.08]):
        add(name, f, neut, trunc, 8)                    # 4*2*2 = 16
# Block C: opportunistic-selection variants
for name, f in SEL.items():
    for neut, decay in itertools.product(["SECTOR", "INDUSTRY", "SUBINDUSTRY"], [0, 8, 16]):
        add(name, f, neut, 0.05, decay)                 # 2*3*3 = 18

json.dump(rows, open(OUT, "w"), indent=1)
print(f"wrote {len(rows)} rows -> {OUT}")
from collections import Counter
print("by root:", dict(Counter("_".join(r["old_id"].split("_")[1:3]) for r in rows)))
