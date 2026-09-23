#!/usr/bin/env python3
"""[Pyramid step 1] Fetch usable fields for the 20 pyramid target datasets with the RELAXED
filter from SESSION_LOG §5: coverage>0.3, MATRIX *and* VECTOR (generator wraps VECTOR in vec_avg).
Output: state/pyramid_fields_full.json  {combo: {dataset: [{id,type,coverage}...]}}"""
import json, pickle, time, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import requests

COMBOS = {
    "CHN_TOP2000U_d0": ("CHN", "TOP2000U", 0),
    "CHN_TOP2000U_d1": ("CHN", "TOP2000U", 1),
    "JPN_TOP1600_d0":  ("JPN", "TOP1600", 0),
    "JPN_TOP1600_d1":  ("JPN", "TOP1600", 1),
}
targets = json.load(open(ROOT / "state/pyramid_fields.json"))   # combo -> [dataset ids]

s = requests.Session(); s.headers.update({"Connection": "close"})
s.cookies.update(pickle.load(open(ROOT / "state/wq_cookies.pkl", "rb")))
MAX_429 = 6; _n429 = [0]

def fetch(region, universe, delay, dataset, limit=50):
    url = ("https://api.worldquantbrain.com/data-fields"
           f"?instrumentType=EQUITY&region={region}&universe={universe}&delay={delay}"
           f"&dataset.id={dataset}&limit={limit}")
    for attempt in range(6):
        r = s.get(url, timeout=40)
        if r.status_code == 429:
            _n429[0] += 1
            if _n429[0] > MAX_429:
                raise SystemExit(f"CIRCUIT-BREAK: {_n429[0]}x429")
            w = float(r.headers.get("Retry-After", 2) or 2)
            if w > 600: raise SystemExit("RATE-BAN — S2.5 runbook")
            time.sleep(w); continue
        if r.status_code >= 500:
            time.sleep(3); continue
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        return r.json().get("results", []), None
    return None, "retries exhausted"

out = {}
for combo, dsets in targets.items():
    region, universe, delay = COMBOS[combo]
    out[combo] = {}
    for d in dsets:
        recs, err = fetch(region, universe, delay, d)
        if err:
            print(f"  {combo}/{d}: ERR {err}", flush=True); out[combo][d] = []; continue
        keep = [{"id": r["id"], "type": r.get("type"), "coverage": r.get("coverage")}
                for r in recs
                if r.get("type") in ("MATRIX", "VECTOR") and (r.get("coverage") or 0) > 0.3]
        keep.sort(key=lambda x: -(x["coverage"] or 0))
        out[combo][d] = keep[:12]
        nm = sum(1 for x in keep if x["type"] == "MATRIX"); nv = len(keep) - nm
        print(f"  {combo}/{d}: {len(recs)} raw -> keep {len(keep[:12])} (MATRIX {nm}, VECTOR {nv})", flush=True)
        time.sleep(0.8)

json.dump(out, open(ROOT / "state/pyramid_fields_full.json", "w"), indent=1)
tot = sum(len(v) for c in out.values() for v in c.values())
print(f"\nsaved state/pyramid_fields_full.json — {tot} fields across "
      f"{sum(1 for c in out.values() for v in c.values() if v)} datasets "
      f"({sum(1 for c in out.values() for v in c.values() if not v)} empty)")
