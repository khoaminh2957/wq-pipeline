#!/usr/bin/env python3
"""gen_frontier.py — map the CARRIER x ORTHOGONALIZATION frontier on the proven strong ensemble
(Khoa 2026-07-21: find a SUBMITTABLE alpha = sharpe>=1.58 AND prod-corr<0.7). The champion
JjvRMjom (sh2.39) is strong but crowded (prod-corr ~0.9) because of its OHLCV carrier. This sweeps
how much crowded carrier we can strip / orthogonalize away before sharpe falls under 1.58, and
whether prod-corr drops under 0.7 at that point. Applies community tips (complementary legs, keep
structure controlled) and the stage grammar (orthogonalize = stage 5 to remove common exposure).
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
UNIV = sys.argv[1] if len(sys.argv) > 1 else "TOP1000"
OUT = ROOT / f"state/funnel/frontier_{UNIV.lower()}_targets.json"

# JjvRMjom decomposed: crowded OHLCV legs (the prod-corr source) vs orthogonal dataset legs
OHLCV = ["-rank(returns)", "-rank(divide(close, open))",
         "multiply(-rank(ts_av_diff(close, 5)), 0.7)", "multiply(-rank(divide(close, vwap)), 0.6)",
         "multiply(rank(divide(volume, adv20)), 0.8)", "multiply(rank(ts_delta(volume, 5)), 0.5)"]
LIGHT = ["-rank(returns)", "multiply(rank(divide(volume, adv20)), 0.6)"]
MIN   = ["-rank(returns)"]
# orthogonal, less-crowded dataset legs (options skew, vol, news, directional prediction, analyst)
DS = ["multiply(rank(subtract(implied_volatility_call_90, implied_volatility_put_90)), 0.6)",
      "multiply(-rank(historical_volatility_60), 0.4)",
      "multiply(rank(ts_backfill(news_ls, 10)), 0.5)",
      "multiply(rank(likelihood_fifth_quantile_five_day_bucket_zero_32), 0.6)",
      "multiply(rank(ts_delta(analyst_upward_revision_count_fq1_earnings_30d, 20)), 0.4)",
      "multiply(-rank(implied_volatility_put_60), 0.4)"]

CARRIERS = {"full": OHLCV, "light": LIGHT, "min": MIN, "none": []}
# crowded factors to orthogonalize AGAINST (stage 5): reversal, momentum, volume-intensity
FACTORS = ["rank(-returns)", "rank(ts_delta(close, 20))", "rank(divide(volume, adv20))"]
ORTH = {"o0": 0, "o1": 1, "o2": 2, "o3": 3}   # how many factors to strip

def ensemble(legs, decay=20, power=2.5):
    inner = f"add({', '.join(legs)}, filter=true)"
    return f"signed_power(zscore(ts_decay_linear({inner}, {decay})), {power})"

def orthogonalize(expr, k):
    for i in range(k):
        expr = f"vector_neut({expr}, {FACTORS[i]})"
    return expr

def settings(neut):
    return {"instrumentType":"EQUITY","region":"USA","universe":UNIV,"delay":1,"decay":0,
            "neutralization":neut,"truncation":0.05,"pasteurization":"ON","unitHandling":"VERIFY",
            "nanHandling":"OFF","maxTrade":"OFF","maxPosition":"OFF","language":"FASTEXPR",
            "visualization":False,"startDate":"2019-01-01","endDate":"2023-12-31"}

rows, seen = [], set()
def add(tag, formula, neut):
    k = ("".join(formula.split()), neut)
    if k in seen: return
    seen.add(k); oid = f"fr{UNIV[3:]}_{tag}_{len(rows):03d}"
    rows.append({"old_id": oid, "id": oid, "formula": formula + "\n", "settings": settings(neut)})

for cname, carrier in CARRIERS.items():
    legs = carrier + DS
    if len(legs) < 3: continue
    for decay in (20, 35):
        base = ensemble(legs, decay=decay)
        for oname, k in ORTH.items():
            f = orthogonalize(base, k)
            for neut in ("INDUSTRY", "SUBINDUSTRY", "MARKET"):
                add(f"{cname}_{oname}_d{decay}", f, neut)

json.dump(rows, open(OUT, "w"), indent=1)
print(f"wrote {len(rows)} rows (carrier x orth x neut) -> {OUT}")
