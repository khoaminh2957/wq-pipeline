#!/usr/bin/env python3
"""next_drive_batch.py — emit the next resim batch from the drive book, RE-RANKED by field
UNCROWDEDNESS (Khoa 2026-07-21). Batch 1 showed the wall is PROD_CORRELATION: alphas that survive
TOP1000 sharpe are mostly fnd6 value/quality -> crowded (prod-corr 0.9). So prioritize alphas whose
formulas lean on UNCROWDED field families (news/social/sentiment/options/analyst) over fnd6/pv
value, which are the ones with a real shot at prod-corr<0.7. Tracks already-simmed drv ids so
successive calls walk the queue. Usage: python3 tools/next_drive_batch.py [N=90] [out.json]"""
import json, re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ALL = ROOT / "state/funnel/drive_resim_all.json"
RES = ROOT / "state/resim_results.jsonl"

N = int(sys.argv[1]) if len(sys.argv) > 1 else 90
OUT = sys.argv[2] if len(sys.argv) > 2 else "state/funnel/drive_next.json"

CROWDED = ("fnd6", "pv1", "pv13", "mkt", "mfm")                       # value/price complex -> crowded
# plain-named fundamentals are ALSO value -> crowded (batch1/2: prod-corr 0.8-0.9 whenever present)
VALUE = ("eps", "operating", "cap", "equity", "debt", "revenue", "revt", "asset", "income",
         "cash", "book", "margin", "oiadp", "oibdp", "ebit", "sales", "gp", "ni", "act",
         "invt", "lct", "ceq", "csho", "dvc", "dlc", "xsga", "xint", "profit", "earnings",
         "dividend", "cogs", "capex", "accrual", "roe", "roa", "yield", "pretax", "netinc")
UNCROWDED = ("rp_", "scl", "snt", "pcr", "option", "anl", "news", "nws", "rating", "social",
             "buzz", "sentiment", "css", "ess", "nip", "insider", "star", "guidance")

# WQB operators (NOT fields) — everything else alphabetic is a field, incl. plain-word value fields
OPS = {"ts_delta","ts_mean","ts_zscore","ts_backfill","ts_decay_linear","ts_rank","ts_arg_min",
       "ts_arg_max","ts_std_dev","ts_sum","ts_corr","ts_regression","group_neutralize","group_rank",
       "group_backfill","group_mean","rank","zscore","normalize","quantile","winsorize","scale",
       "hump","reverse","signed_power","log","abs","sqrt","min","max","add","subtract","multiply",
       "divide","if_else","trade_when","densify","vec_avg","power","sign","tail","bucket","last_diff_value"}

def fields_of(formula):
    toks = re.findall(r"[a-z][a-z0-9_]{2,}", formula)
    return [t for t in toks if t not in OPS and not t.startswith(("ts_", "group_", "vec_"))]

def is_value(t):
    return t.startswith(CROWDED) or any(v in t for v in VALUE)
def is_unc(t):
    return (t.startswith(UNCROWDED) or any(u in t for u in UNCROWDED)) and not is_value(t)

# least-crowded families (evidence: QP9qle8K options-vol+sentiment = only 9 prod breaches vs
# analyst-value le3kzxoe = 264). Rank options-vol/sentiment/news ABOVE analyst within uncrowded.
LEAST = ("implied_volatility", "option", "pcr", "_iv", "volatility", "scl", "snt", "buzz",
         "sentiment", "rp_css", "rp_ess", "news", "nws", "social")

def score(formula):
    fields = fields_of(formula)
    if not fields: return -9.0
    cro = sum(is_value(t) for t in fields)
    unc = sum(is_unc(t) for t in fields)
    if cro > 0: return -1.0 - cro          # ANY value/fundamental field -> crowded -> deprioritize hard
    if unc == 0: return -0.5               # no value but no clearly-uncrowded field either
    least = sum(any(k in t for k in LEAST) for t in fields)
    return unc / max(len(fields), 1) + 0.5 * least   # bonus for the genuinely uncrowded families

done = set()
for line in open(RES):
    try: r = json.loads(line)
    except: continue
    if str(r.get("old_id", "")).startswith("drv_"): done.add(r["old_id"])

pool = [t for t in json.load(open(ALL)) if t["old_id"] not in done]
for t in pool:
    p = t.get("_prior", {})
    robust = 1 if (1.3 <= p.get("sharpe", 0) <= 5 and 1.0 <= p.get("fitness", 0) <= 4) else 0
    t["_key"] = (round(score(t["formula"]), 3), robust, p.get("sharpe", 0) * p.get("fitness", 0))
pool.sort(key=lambda t: t["_key"], reverse=True)

batch = []
for t in pool[:N]:
    batch.append({"old_id": t["old_id"], "id": t["id"], "formula": t["formula"], "settings": t["settings"]})
json.dump(batch, open(OUT, "w"), indent=1)
print(f"already simmed: {len(done)}   remaining: {len(pool)}   -> next {len(batch)} to {OUT}")
print("uncrowdedness of this batch (top5 / bottom5 by score):")
for t in pool[:3]:  print(f"  score={t['_key'][0]:+.2f} | {t['formula'][:70]}")
for t in pool[N-3:N]: print(f"  score={t['_key'][0]:+.2f} | {t['formula'][:70]}")
