#!/usr/bin/env python3
"""gen_flexible2.py — round 2, DATA-INFORMED flexible structures over the CONFIRMED low-prod-corr
family (Khoa 2026-07-21). Round 1 established: techindi/multifactor return-QUANTILE predictions are
directional AND low-prod-corr (max ~0.7, 0-1 breaches); value/quality fields are crowded (0.9, 171).
The pred family caps ~sh1.08 as a single churny signal (turnover 0.94). So: lift sharpe with BREADTH
across horizons/quantiles (only strong same-family legs — round 1 showed weak legs DILUTE) and fix
turnover with ts_decay_linear. Diverse structures, each chosen for THIS signal:
  conviction-spread subtract(rank(top),rank(bottom)); horizon-agreement multiply; decayed momentum;
  a JUSTIFIED multi-horizon ensemble. Still flexible — the ensemble is earned by the data, not reflex.
"""
import json, re, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAT = ROOT / "state/all_fields_usa_top1000_d1.jsonl"
OUT = ROOT / "state/funnel/flexible2_targets.json"
DS = ("techindi_model", "multifactor_return_pred")

def horizon(d):
    for kw, lab in [("one_day","1d"),("1-day","1d"),("1 day","1d"),
                    ("five_day","5d"),("5-day","5d"),("5 day","5d"),("5d","5d"),
                    ("ten_day","10d"),("10-day","10d"),("10 day","10d"),
                    ("60d","60d"),("60-day","60d"),("twenty","20d"),("20d","20d")]:
        if kw in d: return lab
    return "?"

def load():
    top, bot = [], []
    for line in open(CAT):
        try: f = json.loads(line)
        except: continue
        if f["dataset"] not in DS or f.get("type") != "MATRIX": continue
        if (f.get("coverage") or 0) < 0.95 or (f.get("alphaCount") or 9) > 3: continue
        d = (f.get("description", "") + " " + f["id"]).lower()
        if re.search(r"(f1|accuracy|precision|recall|confidence)", d): continue
        h = horizon(d)
        isT = bool(re.search(r"(fifth quantile|quantile 5|\bq5\b|fifth bucket|highest|outperform)", d))
        isB = bool(re.search(r"(first quantile|second quantile|quantile 1|quantile 2|\bq1\b|\bq2\b|lowest|underperform)", d))
        stem = re.sub(r"(_\d+)+$", "", f["id"])
        rec = {"id": f["id"], "h": h, "cov": f.get("coverage") or 0, "ac": f.get("alphaCount") or 9, "stem": stem}
        if isT and not isB: top.append(rec)
        elif isB and not isT: bot.append(rec)
    def dedup(L):
        best = {}
        for r in L:
            k = r["stem"]
            if k not in best or (r["ac"], -r["cov"]) < (best[k]["ac"], -best[k]["cov"]): best[k] = r
        return sorted(best.values(), key=lambda r: (r["ac"], -r["cov"]))
    return dedup(top), dedup(bot)

TOP, BOT = load()
def pick(L, h, n=1):  return [r["id"] for r in L if r["h"] == h][:n]
print(f"TOP {len(TOP)} / BOT {len(BOT)} legs after dedup")

# ---- structure builders (flexible; each fits the prediction family) ----
def spread(a, b):            return f"subtract(rank({a}), rank({b}))"                 # conviction: top minus bottom
def spread_dec(a, b, d):     return f"ts_decay_linear(subtract(rank({a}), rank({b})), {d})"
def agree(a, b):             return f"multiply(rank({a}), rank({b}))"                # both horizons agree -> long
def mom_dec(f, sgn, d):      return f"ts_decay_linear({sgn}rank(ts_delta({f}, 5)), {d})"  # strengthening pred, smoothed
def ens(legs, d, p):
    inner = f"add({', '.join(legs)}, filter=true)"
    s = f"zscore(ts_decay_linear({inner}, {d}))"
    return f"signed_power({s}, {p})" if p != 1 else s

def settings(neut):
    return {"instrumentType":"EQUITY","region":"USA","universe":"TOP1000","delay":1,"decay":0,
            "neutralization":neut,"truncation":0.05,"pasteurization":"ON","unitHandling":"VERIFY",
            "nanHandling":"OFF","maxTrade":"OFF","maxPosition":"OFF","language":"FASTEXPR",
            "visualization":False,"startDate":"2019-01-01","endDate":"2023-12-31"}

rows, seen = [], set()
def add(tag, formula):
    for neut in ("INDUSTRY", "SUBINDUSTRY", "MARKET"):
        k = ("".join(formula.split()), neut)
        if k in seen: continue
        seen.add(k); oid = f"fx2_{tag}_{len(rows):03d}"
        rows.append({"old_id": oid, "id": oid, "formula": formula + "\n", "settings": settings(neut)})

# matched top/bottom pairs per horizon (same model family -> a meaningful conviction spread)
for h in ("5d", "1d", "10d", "60d"):
    t, b = pick(TOP, h, 1), pick(BOT, h, 1)
    if t and b:
        add(f"spr_{h}", spread(t[0], b[0]))
        add(f"sprD_{h}", spread_dec(t[0], b[0], 10))
        add(f"sprD2_{h}", spread_dec(t[0], b[0], 20))
# horizon agreement: two top legs at different horizons multiplied
t5, t10, t1 = pick(TOP,"5d",1), pick(TOP,"10d",1), pick(TOP,"1d",1)
if t5 and t10: add("agr_5_10", agree(t5[0], t10[0]))
if t5 and t1:  add("agr_5_1",  agree(t5[0], t1[0]))
# decayed prediction-momentum on the best top legs (round-1 winner + turnover fix)
for i, fid in enumerate(pick(TOP,"5d",2) + pick(TOP,"1d",1)):
    add(f"mom_{i}_d8",  mom_dec(fid, "", 8))
    add(f"mom_{i}_d15", mom_dec(fid, "", 15))
# JUSTIFIED multi-horizon ensemble: several strong top(+)/bottom(-) legs across horizons
long_legs  = pick(TOP,"5d",2)+pick(TOP,"1d",1)+pick(TOP,"10d",1)+pick(TOP,"60d",1)
short_legs = pick(BOT,"5d",2)+pick(BOT,"1d",1)+pick(BOT,"10d",1)+pick(BOT,"60d",1)
ws = [0.7,0.6,0.55,0.5,0.5,0.45,0.45,0.4,0.4,0.4]
legs = [f"multiply(rank({x}), {ws[i]})" for i, x in enumerate(long_legs)]
legs += [f"multiply(-rank({x}), {ws[i]})" for i, x in enumerate(short_legs)]
if len(legs) >= 6:
    for d in (8, 15, 25):
        for p in (1, 2):
            add(f"ens_d{d}_p{p}", ens(legs, d, p))
# conviction-spread ensemble: add matched spreads across horizons (all-strong, diverse-horizon)
spreads = []
for h in ("5d","1d","10d","60d"):
    t, b = pick(TOP,h,1), pick(BOT,h,1)
    if t and b: spreads.append(spread(t[0], b[0]))
if len(spreads) >= 3:
    for d in (10, 20):
        add(f"sprens_d{d}", ens(spreads, d, 1))

json.dump(rows, open(OUT, "w"), indent=1)
nsk = len({re.sub(r'\d+','N',re.sub(r'[a-z][a-z0-9_]{4,}','F',r['formula'])) for r in rows})
print(f"wrote {len(rows)} rows across ~{nsk} skeletons -> {OUT}")
