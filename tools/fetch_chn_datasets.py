#!/usr/bin/env python3
"""Per-dataset CHN field fetch — bypasses the global-listing alphabet cap (R1 [R1-CHN-STATUS]).
Global /data-fields for CHN caps at ~100 fields (alphabet 'a' only); dataset.id-filtered fetch
returns the full field list per dataset. Fetches the datasets named on argv (default: priority set).

Single stream, 429-aware. Out: fetched/catalog_CHN/fields_per_dataset.jsonl (append, deduped on rerun).
Run:  python tools/fetch_chn_datasets.py                 # priority set
      python tools/fetch_chn_datasets.py model175 pv1    # explicit
"""
import sys, json, time, pickle, pathlib
import requests
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config

B = config.WQ_API
OUT = pathlib.Path(__file__).resolve().parent.parent / "fetched" / "catalog_CHN"
REGION, UNIVERSE, DELAYS = "CHN", "TOP2000U", [1, 0]
MIN_GAP = 0.45
MAX_429 = 6
PRIORITY = ["pv1", "model175", "pv27", "fundamental5"]

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
                raise SystemExit(f"CIRCUIT-BREAK: {_n429[0]}x429")
            w = float(r.headers.get("Retry-After", 8) or 8)
            if w > 600: raise SystemExit("RATE-BAN — S2.5 runbook")
            print(f"  429 #{_n429[0]}, wait {w:.0f}s", flush=True); time.sleep(w + 2); continue
        if r.status_code == 401:
            raise SystemExit("401 — session expired; re-auth and rerun")
        return r
    return None


datasets = sys.argv[1:] or PRIORITY
# load existing to dedup
existing = {}
outfile = OUT / "fields_per_dataset.jsonl"
if outfile.exists():
    for l in open(outfile):
        try:
            j = json.loads(l); existing[(j.get("id"), j.get("_delay"))] = j
        except Exception:
            pass

for dsid in datasets:
    print(f"=== {dsid} ===", flush=True)
    n = 0
    for delay in DELAYS:
        base = {"instrumentType": "EQUITY", "region": REGION, "universe": UNIVERSE,
                "delay": delay, "dataset.id": dsid}
        off = 0
        while True:
            r = get("/data-fields", **base, limit=50, offset=off)
            if r is None:
                print(f"  {dsid} d{delay} off={off}: no response", flush=True); break
            j = r.json(); res = j.get("results", []); cnt = j.get("count", 0)
            for f in res:
                f["_delay"] = delay
                existing[(f.get("id"), delay)] = f; n += 1
            off += 50
            if off >= cnt or not res:
                break
    print(f"  {dsid}: {n} field-rows", flush=True)

with open(outfile, "w") as f:
    for j in existing.values():
        f.write(json.dumps(j, ensure_ascii=False) + "\n")
print(f"TOTAL {len(existing)} unique (id,delay) rows -> {outfile}", flush=True)
