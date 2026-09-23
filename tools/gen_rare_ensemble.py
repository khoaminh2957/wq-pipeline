#!/usr/bin/env python3
"""gen_rare_ensemble.py — big NO-pv1 ensembles from RARE-but-well-covered fields (Khoa 2026-07-21).

Eliminate pv1 entirely; lean on many UNUSUAL fields (low alphaCount = uncrowded -> low
prod-corr) with GOOD coverage (>=0.9 = tradeable). The winning structure is a weighted additive
ensemble of many weak orthogonal legs — here every leg is a rare non-pv1 field, so the whole
alpha is low-prod-corr by construction. Legs are built by field ROLE:
  CHANGE/revision desc -> rank(F) (already a change) ; slow LEVEL -> rank(ts_delta(F, 63)) (revision)
  ratio/score/factor   -> rank(F) ; count/intensity  -> rank(F/ts_mean(F,20))
The meaning-gate prunes degenerate legs before sim.
"""
from __future__ import annotations
import json, pathlib, re, itertools

OUT = pathlib.Path("state/funnel/rare_ensemble_targets.json")
CAT = "fetched/fields_all.jsonl"

CHANGE_KW = ("change", "growth", "revision", "momentum", "trend", "delta", "surprise")
COUNT_KW  = ("number", "count", "volume")
def role(desc):
    d = desc.lower()
    if any(k in d for k in CHANGE_KW): return "CHANGE"
    if any(k in d for k in COUNT_KW):  return "COUNT"
    return "LEVEL"

def leg(fid, ftype, desc, w):
    x = f"vec_avg({fid})" if ftype == "VECTOR" else fid
    r = role(desc)
    if r == "CHANGE": inner = f"rank({x})"                       # already a change/score
    elif r == "COUNT": inner = f"rank({x}/ts_mean({x}, 20))"     # relative intensity
    else: inner = f"rank(ts_delta({x}, 63))"                     # slow level -> quarterly revision
    return f"multiply({inner}, {w})"

def load_rare():
    pool = {}
    for line in open(CAT):
        r = json.loads(line)
        if r["delay"] != 1 or r["dataset"]["id"] == "pv1": continue
        cov = r.get("coverage") or 0; ac = r.get("alphaCount") or 0
        if cov < 0.92 or not (2 <= ac <= 40): continue
        if r.get("type") != "MATRIX": continue                  # clean scalar only
        if re.search(r"(_flag|_id|_type|_code)$", r["id"]): continue
        pool.setdefault(r["dataset"]["id"], []).append((r["id"], r["type"], r["description"], cov, ac))
    return pool

def ensemble(legs, decay, power):
    inner = f"add({', '.join(legs)}, filter=true)"
    sig = f"signed_power(zscore(ts_decay_linear({inner}, {decay})), {power})"
    return sig

def settings(neut):
    return {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1, "decay": 0,
            "neutralization": neut, "truncation": 0.05, "pasteurization": "ON", "unitHandling": "VERIFY",
            "nanHandling": "OFF", "maxTrade": "OFF", "maxPosition": "OFF", "language": "FASTEXPR",
            "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31"}

pool = load_rare()
# build 3 diverse big ensembles, each pulling from multiple datasets (coprime stride for diversity)
DATASETS = ["model77", "earnings4", "analyst4", "fundamental7", "model53"]
ws = [0.6, 0.55, 0.5, 0.5, 0.45, 0.45, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4]
rows, seen = [], set()
def add(tag, f, neut):
    k = ("".join(f.split()), neut)
    if k in seen: return
    seen.add(k); oid = f"rare_{tag}_{len(rows):03d}"
    rows.append({"old_id": oid, "id": oid, "formula": f + "\n", "settings": settings(neut)})

for variant, stride in enumerate([1, 3, 5]):
    legs = []
    for ds in DATASETS:
        fs = sorted(pool.get(ds, []), key=lambda e: (e[4], -e[3]))    # rarest first, well-covered
        pick = fs[variant::stride][:4] if len(fs) > 4 else fs[:3]     # a few per dataset
        for e in pick:
            if len(legs) >= 14: break
            legs.append(leg(e[0], e[1], e[2], ws[len(legs)]))
    if len(legs) < 6: continue
    for decay, power in ((20, 2.5), (45, 2.5)):
        f = ensemble(legs, decay, power)
        for neut in ["MARKET", "INDUSTRY", "SUBINDUSTRY"]:
            add(f"v{variant}_d{decay}", f, neut)

json.dump(rows, open(OUT, "w"), indent=1)
print(f"wrote {len(rows)} rows -> {OUT}")
print(f"pool sizes: " + ", ".join(f"{k}={len(v)}" for k, v in pool.items()))
