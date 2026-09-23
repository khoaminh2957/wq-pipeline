#!/usr/bin/env python3
"""gen_structure_alphas.py — NEW alphas built from the operator-NESTING STRUCTURES learned
from the top-200 highest-PnL alphas (deduped to 58 distinct skeletons). No field-story; the
STRUCTURE is the lesson. The winning grammars:

  A (fast reversal, high sharpe / high turnover):  multiply(rank(-ts_delta(F,N)), rank(intensity))
  B (composite smoother, low turnover / smooth PnL): ts_decay_linear(group_neutralize(<sig>, sub), N)
  C (top PnL-proxy, mean-reversion x intensity):     multiply(reverse(rank(ts_zscore(F,N))), rank(F/ts_mean(F,N)))

Creation move = FUSE A's signal into B's smoother (keep A's sharpe, get B's turnover), and
instantiate C on fresh price/volume. These are new structures, not copies of any top-200 row.
"""
from __future__ import annotations
import json, pathlib, itertools

OUT = pathlib.Path("state/funnel/struct_alpha_targets.json")

REV = "multiply(rank(-ts_delta(close, 1)), rank(volume/adv20))"                       # A: panic reversal
MRV = "multiply(reverse(rank(ts_zscore(close, 21))), rank(volume/ts_mean(volume, 20)))"  # C: mean-reversion x intensity

def smoother(sig, sub, dec):        # B wrapper: in-formula neutralize + decay smoothing
    return f"ts_decay_linear(group_neutralize({sig}, {sub}), {dec})"

# NEW structure-driven alphas
STRUCTS = {
    # #1 A fused into B: reversal signal, smoothed -> high sharpe + low turnover + smooth PnL
    "S1_rev_smooth6":  smoother(REV, "subindustry", 6),
    "S1_rev_smooth12": smoother(REV, "subindustry", 12),
    "S1_rev_smoothIND":smoother(REV, "industry", 6),
    # #2 C on pv1 (highest PnL-proxy structure, fresh fields)
    "S2_meanrev":      MRV,
    # #3 C fused into B smoother
    "S3_mrv_smooth6":  smoother(MRV, "subindustry", 6),
    "S3_mrv_smoothIND":smoother(MRV, "industry", 6),
    # #4 B-grammar weighted composite of two orthogonal reversal legs (close + vwap dislocation)
    "S4_wcomposite":   smoother("0.6*rank(-ts_delta(close, 1)) + 0.4*(1 - rank(vwap/close))", "subindustry", 6),
    "S4_wcompIND":     smoother("0.6*rank(-ts_delta(close, 1)) + 0.4*(1 - rank(vwap/close))", "industry", 6),
}

def settings(neut, trunc, decay):
    return {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1,
            "decay": decay, "neutralization": neut, "truncation": trunc, "pasteurization": "ON",
            "unitHandling": "VERIFY", "nanHandling": "OFF", "maxTrade": "OFF", "maxPosition": "OFF",
            "language": "FASTEXPR", "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31"}

rows, seen = [], []
_seen = set()
def add(tag, f, neut, trunc, decay):
    k = ("".join(f.split()), neut, trunc, decay)
    if k in _seen: return
    _seen.add(k)
    oid = f"str_{tag}_{len(rows):03d}"
    rows.append({"old_id": oid, "id": oid, "formula": f + "\n", "settings": settings(neut, trunc, decay)})

# in-formula-neutralized structures use light settings neut (MARKET); pure-multiply use full sweep
for name, f in STRUCTS.items():
    infml_neut = "group_neutralize" in f
    neuts = ["MARKET"] if infml_neut else ["MARKET", "INDUSTRY", "SUBINDUSTRY"]
    for neut, trunc, decay in itertools.product(neuts, [0.02, 0.05, 0.08], [0, 4, 8]):
        add(name, f, neut, trunc, decay)

json.dump(rows, open(OUT, "w"), indent=1)
print(f"wrote {len(rows)} rows -> {OUT}")
from collections import Counter
print("by structure:", dict(Counter(r["old_id"].split("_")[1] for r in rows)))
