#!/usr/bin/env python3
"""gen_rev_entry_sweep.py — trade_when / if_else / hump ENTRY variants to push the
near-pass USA reversal alphas over the FITNESS bar.

Near-pass targets (USA d1 TOP3000, strong sharpe but fitness<1.0 because turnover is high):
  B1 = multiply(rank(-returns), rank(volume/adv20), filter=true)  [mLbWXMkX sh1.95 fit0.83 tvr0.73]
  B2 = -ts_delta(close, 3)                                        [JjOJdajA core sh1.58 fit0.74 tvr0.61]
fitness = sharpe * sqrt(|returns| / max(turnover,0.125)); at tvr 0.6-0.9 the turnover term
crushes it. Every entry below CUTS turnover with real logic, aiming fitness >= 1.0 while
holding sharpe >= 1.58:

  hump           = the turnover valve (docs: limits frequency/magnitude of position changes).
  trade_when vol = the reversal is trustworthy AFTER a volume shock (liquidity provision to
                   volume-driven order imbalance; the multiply leg already encodes this) — so
                   TRADE only on high-volume days and HOLD between, cutting churn.
  if_else tail   = the reversal signal lives in the extreme tails; zero the noisy middle ->
                   fewer names -> lower turnover.
"""
from __future__ import annotations
import json, pathlib, itertools

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "state/funnel/rev_entry_stage1_targets.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

B1 = "multiply(rank(-returns), rank(volume/adv20), filter=true)"
B2 = "-ts_delta(close, 3)"

def entries(base, rankexpr):
    # rankexpr = the [0,1] reversal rank used for tail-selection
    return {
        "base":      base,
        "hump005":   f"hump({base}, hump=0.005)",
        "hump01":    f"hump({base}, hump=0.01)",
        "hump02":    f"hump({base}, hump=0.02)",
        "twv1":      f"trade_when(volume > adv20, {base}, -1)",
        "twv15":     f"trade_when(volume > 1.5 * adv20, {base}, -1)",
        "twv2":      f"trade_when(volume > 2 * adv20, {base}, -1)",
        "tail":      f"if_else(abs({rankexpr} - 0.5) > 0.35, {base}, 0)",
        "twhump":    f"trade_when(volume > adv20, hump({base}, hump=0.01), -1)",
    }

B1E = entries(B1, "rank(-returns)")
B2E = entries(B2, "rank(-ts_delta(close, 3))")

def settings(neut, trunc, decay):
    return {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1,
            "decay": decay, "neutralization": neut, "truncation": trunc,
            "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
            "maxTrade": "OFF", "maxPosition": "OFF", "language": "FASTEXPR",
            "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31"}

rows, seen = [], set()
def add(tag, formula, neut, trunc, decay):
    k = ("".join(formula.split()), neut, trunc, decay)
    if k in seen: return
    seen.add(k)
    oid = f"rve_{tag}_{len(rows):03d}"
    rows.append({"old_id": oid, "id": oid, "formula": formula + "\n", "settings": settings(neut, trunc, decay)})

# Block A — B1 core entries across neut x decay (the star: mLbWXMkX -> fitness lift)
for name in ["base", "hump005", "hump01", "twv1", "twv15", "tail"]:
    for neut, decay in itertools.product(["MARKET", "INDUSTRY", "SECTOR"], [0, 4, 8]):
        add(f"B1_{name}", B1E[name], neut, 0.02, decay)          # 6*3*3 = 54

# Block B — B1 heavier turnover cuts / combo
for name in ["hump02", "twv2", "twhump"]:
    for neut, decay in itertools.product(["MARKET", "INDUSTRY"], [0, 4, 8]):
        add(f"B1_{name}", B1E[name], neut, 0.02, decay)          # 3*2*3 = 18

# Block C — B2 (-ts_delta close3) entries
for name in ["base", "hump01", "twv1", "tail"]:
    for neut, decay in itertools.product(["MARKET", "INDUSTRY"], [0, 4, 8]):
        add(f"B2_{name}", B2E[name], neut, 0.02, decay)          # 4*2*3 = 24

json.dump(rows, open(OUT, "w"), indent=1)
print(f"wrote {len(rows)} rows -> {OUT}")
from collections import Counter
print("blocks:", dict(Counter(r["old_id"].split("_")[1] for r in rows)))
