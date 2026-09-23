#!/usr/bin/env python3
"""parse_drive_alphas.py — parse accA-D CSVs from the Drive book, dedup by formula, and build a
resim target set with settings OVERRIDDEN to TOP1000/USA/delay 1 (Khoa 2026-07-21). Ranked
best-prior-first so a passing alpha surfaces soonest. Keeps each alpha's own decay+neutralization."""
import csv, glob, json, re, pathlib, collections

SRC = "/private/tmp/claude-501/-Users-kanenguyen-wq-pipeline/69a5044b-8dc6-468c-b248-166e805830bd/scratchpad/accABCD"
OUT = "state/funnel/drive_resim_all.json"

def fnum(x):
    try: return float(x)
    except Exception: return 0.0

uniq = {}
rows_seen = 0
for fp in sorted(glob.glob(SRC + "/*.csv")):
    try:
        with open(fp, newline="") as f:
            for r in csv.DictReader(f):
                fm = (r.get("formula") or "").strip()
                if not fm or fm == "formula":
                    continue
                rows_seen += 1
                sh, fit = fnum(r.get("sharpe")), fnum(r.get("fitness"))
                m = re.match(r"(\d+)\s*/\s*(\d+)", r.get("pass") or "0/8")
                ps = int(m.group(1)) if m else 0
                cand = dict(formula=fm, decay=r.get("decay") or "0",
                            neut=(r.get("neutralization") or "SUBINDUSTRY").upper(),
                            sharpe=sh, fitness=fit, pscore=ps, label=r.get("label") or "")
                prev = uniq.get(fm)
                if prev is None or (ps, sh * fit) > (prev["pscore"], prev["sharpe"] * prev["fitness"]):
                    uniq[fm] = cand
    except Exception as e:
        print("skip", fp, e)

def robust(a):
    """prior sharpe 15+ = overfit on a small original universe -> unlikely to survive TOP1000.
    Favor the PLAUSIBLE-robust band; extreme or weak priors go later."""
    return 1.3 <= a["sharpe"] <= 5.0 and 1.0 <= a["fitness"] <= 4.0

def fam(a):
    m = re.search(r"fam([A-Za-z0-9]+)", a["label"]); return m.group(1) if m else "?"

# tier 1 = plausible-robust, tier 2 = the rest; within each, round-robin across families for diversity
def order(items):
    buckets = collections.OrderedDict()
    for a in sorted(items, key=lambda a: -(a["sharpe"] * a["fitness"])):
        buckets.setdefault(fam(a), []).append(a)
    out, keys = [], list(buckets)
    while any(buckets[k] for k in keys):
        for k in keys:
            if buckets[k]: out.append(buckets[k].pop(0))
    return out

t1 = [a for a in uniq.values() if robust(a)]
t2 = [a for a in uniq.values() if not robust(a)]
ranked = order(t1) + order(t2)
print(f"plausible-robust tier1={len(t1)}  tier2={len(t2)}")

def sset(neut, decay):
    try: dc = int(float(decay))
    except Exception: dc = 0
    return {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP1000", "delay": 1, "decay": dc,
            "neutralization": neut, "truncation": 0.05, "pasteurization": "ON", "unitHandling": "VERIFY",
            "nanHandling": "OFF", "maxTrade": "OFF", "maxPosition": "OFF", "language": "FASTEXPR",
            "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31"}

targets = []
for i, a in enumerate(ranked):
    oid = f"drv_{i:05d}"
    targets.append({"old_id": oid, "id": oid, "formula": a["formula"] + "\n",
                    "settings": sset(a["neut"], a["decay"]),
                    "_prior": {"sharpe": a["sharpe"], "fitness": a["fitness"], "pass": a["pscore"],
                               "neut": a["neut"], "decay": a["decay"]}})
pathlib.Path("state/funnel").mkdir(parents=True, exist_ok=True)
json.dump(targets, open(OUT, "w"))
print(f"rows parsed: {rows_seen}   unique formulas: {len(uniq)}   -> {OUT}")
print("prior pass dist:", dict(sorted(collections.Counter(a["pscore"] for a in ranked).items())))
print("neut dist:", dict(collections.Counter(a["neut"] for a in ranked)))
print("\ntop 6 by prior:")
for a in ranked[:6]:
    print(f"  pass={a['pscore']} sh={a['sharpe']:.2f} fit={a['fitness']:.2f} neut={a['neut']} decay={a['decay']} | {a['formula'][:66]}")
