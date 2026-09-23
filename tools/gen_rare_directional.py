#!/usr/bin/env python3
"""gen_rare_directional.py — LOW-PROD-CORR-by-construction ensembles from RARE directional
signals (Khoa 2026-07-21 goal: an alpha that passes EVERY gate incl prod-corr<0.7).

The crowded production book trades reversal/momentum/volume, so any OHLCV ensemble overlaps it
(prod-corr 0.9-1.0) and orthogonalizing it away kills the edge. Instead we build the signal from
UNDER-UTILIZED datasets whose fields have alphaCount<=3 (nobody trades them) yet coverage>=0.97
(tradeable) and are DIRECTIONAL predictions (ML return-quantile probs, analyst-revision scores,
value/quality composites, return-class predictions). Such a book cannot overlap the crowded one's
PnL shape -> prod-corr low by construction, while the signals are real (not OHLCV noise) so sharpe
can still clear 1.58. Non-pv1 + TOP1000 = the active Power-Pool theme.

Leg logic (operator matched to the field's ROLE, per trading_logic_methodology):
  probability/score/prediction that is ALREADY directional -> rank(F)  (the field IS the bet)
  the a-priori sign comes from the description; the SIM confirms it (flipped ensemble also emitted).
"""
import json, re, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAT = ROOT / "state/all_fields_usa_top1000_d1.jsonl"
OUT = ROOT / "state/funnel/rare_directional_targets.json"

# datasets: directional ML/analyst predictions, low users, aC~0-2
DATASETS = ["techindi_model", "predictive_starmine", "multi_horizon_alpha",
            "multifactor_return_pred", "ml_factor_proj"]

POS = ("upgrade", "positive", "buy", "cheap", "undervalued", "improv", "revision",
       "quality", "growth", "top", "fifth quantile", "outperform", "long")
NEG = ("downgrade", "negative", "sell", "expensive", "distress", "manipulation",
       "risk", "short", "hedge", "bottom", "first quantile", "underperform", "alert")

def sign_of(desc):
    d = desc.lower()
    p = sum(k in d for k in POS); n = sum(k in d for k in NEG)
    return -1 if n > p else 1                       # default +; description decides a-priori

def stem(fid):                                       # collapse near-dup horizon/bucket suffixes
    return re.sub(r"(_\d+)+$", "", fid)

def usable(f):
    return (f.get("type") == "MATRIX" and (f.get("coverage") or 0) >= 0.97
            and (f.get("alphaCount") or 99) <= 3
            and not re.search(r"(_flag|_id|_type|_code)$", f["id"])
            # drop raw OHLCV-like fields even inside rare datasets (they re-introduce prod-corr)
            and not re.search(r"(^|_)(close|open|high|low|volume|vwap|market_cap|price)(_|$)", f["id"]))

def load():
    by = collections.defaultdict(list)
    for line in open(CAT):
        try: f = json.loads(line)
        except: continue
        if f["dataset"] in DATASETS and usable(f):
            by[f["dataset"]].append(f)
    # dedup by stem (keep the rarest, best-covered representative per underlying)
    for ds, fs in by.items():
        best = {}
        for f in fs:
            s = stem(f["id"]); cur = best.get(s)
            key = ((f.get("alphaCount") or 9), -(f.get("coverage") or 0))
            if cur is None or key < cur[0]:
                best[s] = (key, f)
        by[ds] = [v[1] for v in best.values()]
    return by

WS = [0.7, 0.6, 0.55, 0.5, 0.5, 0.45, 0.45, 0.4, 0.4, 0.4, 0.4, 0.4]

def legs_for(fs, n):
    fs = sorted(fs, key=lambda f: ((f.get("alphaCount") or 9), -(f.get("coverage") or 0)))[:n]
    out = []
    for i, f in enumerate(fs):
        sg = sign_of(f["description"])
        pre = "-" if sg < 0 else ""
        w = WS[i] if i < len(WS) else 0.4
        out.append(f"multiply({pre}rank({f['id']}), {w})")
    return out

def ensemble(legs, decay, power):
    inner = f"add({', '.join(legs)}, filter=true)"
    return f"signed_power(zscore(ts_decay_linear({inner}, {decay})), {power})"

def flip(formula):                                   # whole-ensemble sign flip
    return f"multiply({formula}, -1)"

def settings(neut):
    return {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP1000", "delay": 1,
            "decay": 0, "neutralization": neut, "truncation": 0.05, "pasteurization": "ON",
            "unitHandling": "VERIFY", "nanHandling": "OFF", "maxTrade": "OFF", "maxPosition": "OFF",
            "language": "FASTEXPR", "visualization": False,
            "startDate": "2019-01-01", "endDate": "2023-12-31"}

by = load()
print("pool:", ", ".join(f"{k}={len(v)}" for k, v in by.items()))

bases = {}
for ds in DATASETS:
    L = legs_for(by.get(ds, []), 10)
    if len(L) >= 6:
        bases[ds] = L
# mixed: top ~3 legs from each dataset
mixed = []
for ds in DATASETS:
    mixed += legs_for(by.get(ds, []), 3)
if len(mixed) >= 8:
    bases["mixed"] = mixed[:12]

rows, seen = [], set()
def add(tag, formula, neut):
    k = ("".join(formula.split()), neut)
    if k in seen: return
    seen.add(k); oid = f"rd_{tag}_{len(rows):03d}"
    rows.append({"old_id": oid, "id": oid, "formula": formula + "\n", "settings": settings(neut)})

for tag, L in bases.items():
    for decay in (20, 45):
        f = ensemble(L, decay, 2.5)
        for neut in ("INDUSTRY", "SUBINDUSTRY", "MARKET"):
            add(f"{tag}_d{decay}", f, neut)
            add(f"{tag}_d{decay}f", flip(f), neut)      # flipped ensemble (sim learns true sign)

json.dump(rows, open(OUT, "w"), indent=1)
print(f"wrote {len(rows)} rows -> {OUT}")
