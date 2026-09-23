#!/usr/bin/env python3
"""gen_flexible.py — compose a DIVERSE batch of alpha STRUCTURES (not one memorized skeleton).
Khoa 2026-07-21: learn the structure grammar (fetched/alpha_structure_grammar.md) and flexibly
build the structure that FITS each signal. Diverse skeletons -> diverse PnL -> a real shot at
prod-corr<0.7. Fields are the RARE directional/uncrowded ones (aC<=3, cov>=.97, non-pv1) so the
book is low-prod-corr by construction; the STRUCTURE is chosen by the signal's role.
"""
import json, re, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAT = ROOT / "state/all_fields_usa_top1000_d1.jsonl"
OUT = ROOT / "state/funnel/flexible_targets.json"

DATASETS = ["techindi_model", "predictive_starmine", "multi_horizon_alpha",
            "multifactor_return_pred", "ml_factor_proj", "mmp_nlp_sentiment"]

# ---- role classification from the DESCRIPTION (what KIND of signal is this?) ----------------
# directional cue = the field points somewhere (a return/rank/quantile/tone), not just measures the model
DIRCUE = ("return", "quantile", "outperform", "underperform", "bullish", "bearish", "trend",
          "upgrade", "downgrade", "revision", "surprise", "buy", "sell", "long", "short",
          "positive", "negative", "valuation", "earnings yield", "return on equity", "z-score",
          "z score", "margin", "quality", "cheap", "expensive", "hedge signal")
# model-quality / meta metrics carry NO direction -> never a signal (f1/accuracy/count-of-articles)
META = ("f1", "accuracy", "precision", "recall", "auc", "r-squared", "r2 ", "number of articles",
        "count of articles", "coverage", "sample size", "model score")

def role(desc):
    d = desc.lower()
    if any(k in d for k in META): return "META"
    if any(k in d for k in ("confidence", "attention", "reliability")): return "STATE"   # a gate/weight
    if any(k in d for k in ("sentiment", "positive", "negative", "tone")):  return "SENT"
    if any(k in d for k in ("revision", "upgrade", "downgrade", "surprise", "estimate")):   return "REVN"
    if any(k in d for k in ("valuation", "earnings yield", "return on equity", "z-score",
                            "z score", "margin", "ebitda", "cash flow", "quality", "leverage")): return "VALU"
    if any(k in d for k in ("probability", "likelihood", "quantile", "predict", "classif",
                            "hedge signal", "forecast")) and any(k in d for k in DIRCUE):  return "PRED"
    return "LEVEL"

def usable(f):
    return (f.get("type") == "MATRIX" and (f.get("coverage") or 0) >= 0.97
            and (f.get("alphaCount") or 99) <= 3
            and not re.search(r"(_flag|_id|_type|_code)$", f["id"])
            and not re.search(r"(f1|accuracy|precision|recall|_auc|coverage|count_\d)", f["id"])
            and not re.search(r"(^|_)(close|open|high|low|volume|vwap|market_cap|price)(_|$)", f["id"]))

DESC = {}
def load():
    by = collections.defaultdict(list)
    for line in open(CAT):
        try: f = json.loads(line)
        except: continue
        if f["dataset"] in DATASETS and usable(f):
            f["role"] = role(f.get("description", "")); DESC[f["id"]] = f.get("description", "")
            by[f["role"]].append(f)
    for r in by:                                     # rarest, best-covered first
        by[r].sort(key=lambda f: ((f.get("alphaCount") or 9), -(f.get("coverage") or 0)))
    return by

TOPQ = r"(fifth quantile|quantile 5|\bq5\b|fifth bucket|\btop\b|highest|outperform|upgrade)"
BOTQ = r"(first quantile|second quantile|quantile 1|quantile 2|\bq1\b|\bq2\b|bottom|lowest|underperform|downgrade)"
def psign(fid):
    """a top-quantile/outperform probability -> LONG (+); a bottom-quantile/underperform prob is a
    likely LOSER -> SHORT (-). Sign the field by which tail it predicts (sim still confirms). Word
    boundaries so 'fq1' (fiscal quarter) != 'q1' (quantile)."""
    d = (DESC.get(fid, "") + " " + fid).lower()
    if re.search(BOTQ, d) and not re.search(TOPQ, d): return "-"
    return ""

# ---- SKELETONS: named routes through the stage grammar (structure chosen by role) ----------
def level(f):        return f"{psign(f)}rank({f})"                           # PRED/score: field IS the bet
def mom(f, n):       return f"{psign(f)}rank(ts_delta({f}, {n}))"            # change/revision
def zfade(f, n):     return f"ts_decay_linear(reverse(rank(ts_zscore({f}, {n}))), 10)"  # overshoot reverts
def interact(f, g):  return f"multiply(rank({f}), rank({g}))"               # signal AND state
def regime(f, g):    return f"trade_when(rank({g}) > 0.6, rank({f}), -1)"   # trade only when state high
def diverge(a, b):   return f"subtract(rank({a}), rank({b}))"               # two views diverge
def skew(a, b):      return f"rank(subtract({a}, {b}))"                     # spread of a pair
def ratio_dyn(a, b): return f"rank(ts_delta(divide({a}, {b}), 22))"        # changing relationship
def ens3(l1, l2, l3):                                                       # ensemble = ONE option
    return f"signed_power(zscore(ts_decay_linear(add({l1}, {l2}, {l3}, filter=true), 20)), 2.0)"

def skeleton(formula):                                # structural signature: fields->F, ints->N
    s = re.sub(r"\b[a-z][a-z0-9_]{3,}\b", "F", formula)
    return re.sub(r"\b\d+\b", "N", s)

def settings(neut):
    return {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP1000", "delay": 1,
            "decay": 0, "neutralization": neut, "truncation": 0.05, "pasteurization": "ON",
            "unitHandling": "VERIFY", "nanHandling": "OFF", "maxTrade": "OFF", "maxPosition": "OFF",
            "language": "FASTEXPR", "visualization": False,
            "startDate": "2019-01-01", "endDate": "2023-12-31"}

by = load()
print("roles:", ", ".join(f"{k}={len(v)}" for k, v in sorted(by.items())))
PRED, VALU, SENT, REVN, STATE = (by.get(k, []) for k in ("PRED", "VALU", "SENT", "REVN", "STATE"))
def ids(fs, n): return [f["id"] for f in fs[:n]]

rows, seen, skcount = [], set(), collections.Counter()
CAP = 8                                               # max alphas per skeleton -> forces diversity
def add(tag, formula):
    sk = skeleton(formula)
    for neut in ("INDUSTRY", "SUBINDUSTRY", "MARKET"):
        if skcount[(sk, neut)] >= CAP: continue
        key = ("".join(formula.split()), neut)
        if key in seen: continue
        seen.add(key); skcount[(sk, neut)] += 1
        oid = f"flx_{tag}_{len(rows):03d}"
        rows.append({"old_id": oid, "id": oid, "formula": formula + "\n", "settings": settings(neut)})

# PRED -> level, short-horizon momentum, and (with a STATE field) interaction / regime-gate
for fid in ids(PRED, 6):
    add("pred_lvl", level(fid)); add("pred_mom", mom(fid, 5))
# gate = a model-CONFIDENCE field (trust the prediction where the model is confident), not liquidity
g = next((f["id"] for f in STATE if "confidence" in DESC.get(f["id"], "").lower()),
         STATE[0]["id"] if STATE else None)
for fid in ids(PRED, 4):
    if g: add("pred_intr", interact(fid, g)); add("pred_reg", regime(fid, g))
# VALU -> quarterly revision (change of a slow level) and raw level
for fid in ids(VALU, 6):
    add("valu_rev", mom(fid, 63)); add("valu_lvl", level(fid))
# REVN -> the revision score is already a change -> level it
for fid in ids(REVN, 5):
    add("revn_lvl", level(fid))
# SENT -> crowded-sentiment fade
for fid in ids(SENT, 5):
    add("sent_fade", zfade(fid, 10))
# PAIRS: divergence / spread / ratio-dynamics over meaningful related fields
def find(kw, pool_roles=("PRED","VALU","SENT","REVN","STATE","LEVEL")):
    for r in pool_roles:
        for f in by.get(r, []):
            if kw in f["id"].lower(): return f["id"]
    return None
cvol, pvol = find("call_option_volatility"), find("put_option_volatility")
if cvol and pvol: add("iv_skew", skew(cvol, pvol)); add("iv_ratio", ratio_dyn(cvol, pvol))
pos, neg = find("positive"), find("negative")
if pos and neg: add("sent_net", diverge(pos, neg))
# ENSEMBLE (one option, not the default): 3 DISTINCT-archetype legs
if PRED and VALU and (SENT or REVN):
    leg1 = level(ids(PRED, 1)[0])
    leg2 = mom(ids(VALU, 1)[0], 63)
    leg3 = level((SENT or REVN)[0]["id"])
    add("ens3", ens3(leg1, leg2, leg3))

json.dump(rows, open(OUT, "w"), indent=1)
nsk = len({sk for sk, _ in skcount})
print(f"wrote {len(rows)} rows across {nsk} distinct skeletons -> {OUT}")
for (sk, neut), c in sorted(skcount.items()):
    if neut == "INDUSTRY": print(f"  [{c}] {sk[:88]}")
