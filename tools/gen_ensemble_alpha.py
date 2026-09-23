#!/usr/bin/env python3
"""gen_ensemble_alpha.py — a NEW alpha reproducing the DOMINANT structure of the WQB
unsubmitted inventory (learned from 677 realistic alphas, deduped to 105 distinct skeletons).

Winning grammar (sharpe 2.64, fitness 4.67 in the real book):
  signed_power( zscore( ts_decay_linear( add( <many ±rank(micro-signal)×w legs>, filter=true ),
                                          decay ) ),
                power )
i.e. a weighted ADDITIVE ENSEMBLE of orthogonal micro-signals -> smooth (decay) -> normalize
(zscore) -> tail-shape (signed_power). This file builds a NEW leg set (not a copy) fusing the
validated pv1 microstructure mechanics with orthogonal IV/vol/news legs.
"""
from __future__ import annotations
import json, pathlib, itertools

OUT = pathlib.Path("state/funnel/ensemble_alpha_targets.json")

# leg sets — each leg is a distinct market mechanic, ±rank bounded, weighted
FULL = [
    "-rank(returns)",                                                      # 1-day reversal
    "-rank(divide(close, open))",                                          # intraday reversal
    "multiply(-rank(ts_av_diff(close, 5)), 0.7)",                         # 5-day mean-reversion
    "multiply(-rank(divide(close, vwap)), 0.6)",                          # close-vwap dislocation
    "multiply(rank(divide(volume, adv20)), 0.8)",                        # volume climax intensity
    "multiply(rank(ts_delta(volume, 5)), 0.5)",                          # volume acceleration
    "multiply(rank(subtract(implied_volatility_call_90, implied_volatility_put_90)), 0.5)",  # IV skew
    "multiply(-rank(historical_volatility_60), 0.4)",                    # low-vol preference
    "multiply(rank(ts_backfill(news_ls, 10)), 0.4)",                     # news sentiment
]
LEAN = [   # pv1-only microstructure ensemble
    "-rank(returns)",
    "-rank(divide(close, open))",
    "multiply(-rank(ts_av_diff(close, 5)), 0.7)",
    "multiply(-rank(divide(close, vwap)), 0.6)",
    "multiply(rank(divide(volume, adv20)), 0.8)",
    "multiply(rank(ts_delta(volume, 5)), 0.5)",
]

def ensemble(legs, decay, power):
    inner = f"add({', '.join(legs)}, filter=true)"
    sig = f"ts_decay_linear({inner}, {decay})"
    sig = f"zscore({sig})"
    if power and power != 1:
        sig = f"signed_power({sig}, {power})"
    return sig

def settings(neut, trunc, decay0=0):
    return {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1,
            "decay": decay0, "neutralization": neut, "truncation": trunc, "pasteurization": "ON",
            "unitHandling": "VERIFY", "nanHandling": "OFF", "maxTrade": "OFF", "maxPosition": "OFF",
            "language": "FASTEXPR", "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31"}

rows, seen = [], set()
def add(tag, f, neut, trunc):
    k = ("".join(f.split()), neut, trunc)
    if k in seen: return
    seen.add(k)
    oid = f"ens_{tag}_{len(rows):03d}"
    rows.append({"old_id": oid, "id": oid, "formula": f + "\n", "settings": settings(neut, trunc)})

for legname, legs in [("full", FULL), ("lean", LEAN)]:
    for decay, power in itertools.product([20, 45], [1, 2.5, 3.8]):
        f = ensemble(legs, decay, power)
        for neut, trunc in itertools.product(["MARKET", "INDUSTRY", "SUBINDUSTRY"], [0.05]):
            add(f"{legname}_d{decay}_p{power}".replace(".", ""), f, neut, trunc)
# a few trunc variants on the best-guess (full, decay45, power2.5)
fbest = ensemble(FULL, 45, 2.5)
for neut, trunc in itertools.product(["MARKET", "SUBINDUSTRY"], [0.02, 0.08]):
    add("full_d45_p25", fbest, neut, trunc)

json.dump(rows, open(OUT, "w"), indent=1)
print(f"wrote {len(rows)} rows -> {OUT}")
