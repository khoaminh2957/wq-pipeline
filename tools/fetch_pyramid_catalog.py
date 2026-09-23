#!/usr/bin/env python3
"""Cào FULL CHN + JPN data catalog (datasets + fields, delay 0 & 1) for gen-4 field-class mining.
We already have USA (fields_all.jsonl) + 20 hand-picked pyramid datasets; this fills the CHN/JPN gap.

SINGLE sequential stream (one rate-gate) — do NOT run alongside a sim engine (ban precedent).
Catalog only: NO alphas / NO PnL (those are the multi-hour, ban-prone phases).

Out:  fetched/catalog_<REGION>/datasets.jsonl , fields.jsonl , _done.json
Run:  python tools/fetch_pyramid_catalog.py            # CHN then JPN
"""
import sys, json, time, pickle, pathlib
import requests
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config

B = config.WQ_API
OUT = pathlib.Path(__file__).resolve().parent.parent / "fetched"
REGIONS = [("CHN", "TOP2000U"), ("JPN", "TOP1600")]
if len(sys.argv) > 1:                       # optional: restrict to named regions, e.g. `... CHN`
    want = {a.upper() for a in sys.argv[1:]}
    REGIONS = [rc for rc in REGIONS if rc[0] in want]
DELAYS = [1, 0]
MIN_GAP = 0.45
MAX_429 = 6            # circuit-breaker: abort region after this many 429s

s = requests.Session(); s.headers.update({"Connection": "close"})
s.cookies.update(pickle.load(open(config.COOKIE_PATH, "rb")))
_last = [0.0]; _n429 = [0]


def get(path, **params):
    for _ in range(40):
        dt = time.time() - _last[0]
        if dt < MIN_GAP:
            time.sleep(MIN_GAP - dt)
        _last[0] = time.time()
        try:
            r = s.get(B + path, params=params or None, timeout=40)
        except Exception:
            time.sleep(3); continue
        if r.status_code == 429:
            _n429[0] += 1
            if _n429[0] > MAX_429:
                raise SystemExit(f"CIRCUIT-BREAK: {_n429[0]} x 429 — stopping to avoid hard ban")
            w = float(r.headers.get("Retry-After", 8) or 8)
            if w > 600: raise SystemExit("RATE-BAN — S2.5 runbook")
            print(f"  429 #{_n429[0]}, wait {w:.0f}s", flush=True); time.sleep(w + 2); continue
        if r.status_code == 401:
            raise SystemExit("401 — session expired; re-auth (biometric) and rerun")
        return r
    return None


def paginate(path, base):
    off = 0
    while True:
        r = get(path, **base, limit=50, offset=off)
        if r is None:
            print(f"  {path} off={off}: no response, stop", flush=True); return
        j = r.json(); res = j.get("results", []); cnt = j.get("count", 0)
        for x in res:
            x["_delay"] = base["delay"]; yield x
        off += 50
        if off >= cnt or not res:
            return
        if off % 500 == 0:
            print(f"    {path} {off}/{cnt}", flush=True)


for region, universe in REGIONS:
    d = OUT / f"catalog_{region}"; d.mkdir(exist_ok=True)
    _n429[0] = 0
    print(f"=== {region} {universe} ===", flush=True)
    nds = nf = 0
    with open(d / "datasets.jsonl", "w") as dsf, open(d / "fields.jsonl", "w") as ff:
        for delay in DELAYS:
            base = {"region": region, "universe": universe, "delay": delay, "instrumentType": "EQUITY"}
            for ds in paginate("/data-sets", base):
                dsf.write(json.dumps(ds, ensure_ascii=False) + "\n"); nds += 1
            dsf.flush()
            for fld in paginate("/data-fields", base):
                ff.write(json.dumps(fld, ensure_ascii=False) + "\n"); nf += 1
            ff.flush()
            print(f"  delay {delay} done (running: {nds} ds, {nf} fields)", flush=True)
    json.dump({"region": region, "universe": universe, "datasets": nds, "fields": nf},
              open(d / "_done.json", "w"), indent=1)
    print(f"{region}: {nds} datasets, {nf} fields -> {d}", flush=True)

print("CATALOG-CRAWL COMPLETE (CHN+JPN)", flush=True)
