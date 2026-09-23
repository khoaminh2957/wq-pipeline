#!/usr/bin/env python3
"""fetch_region_catalog.py — pull the dataset + field catalog for ONE region/universe.

Built 2026-07-29 for GAC2026 (Global Alpha Competition, 2026-07-27..08-30), whose theme is
region GLB / universe TOPDIV3000. `fetched/fields_all.jsonl` holds 22,506 USA fields and ZERO
for any other region, so nothing can be generated for GLB until this runs.

Deliberately NOT reusing tools/fetch_all_data.py: that script hardcodes REGION="USA" and opens
fields_all.jsonl in "w" mode, so pointing it at another region would erase the USA catalog that
every existing generator depends on. This writes to fetched/fields_<REGION>.jsonl instead.

Khoa 2026-07-29: "các field ở USA khác với GLB dù trùng tên" — confirmed by the same class of bug
found earlier today, where `trend_strength_score` is VECTOR in CHN and MATRIX in USA and the flat
id->type index made logic_check reject a legal USA formula. So GLB metadata must be fetched, never
inferred from the USA catalog: same id, different type/coverage/dataset.

Fetches EVERY universe of the region and unions the fields, recording which universes each field
appears in (availability differs by universe), so one file serves any GLB universe.

Usage:
  python3 tools/fetch_region_catalog.py GLB [delay]          # all universes of the region
  python3 tools/fetch_region_catalog.py GLB TOPDIV3000 [delay]
"""
from __future__ import annotations
import sys, json, time, pickle, pathlib
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "fetched"
B = "https://api.worldquantbrain.com"
# ADAPTIVE pacing (AIMD, Khoa 2026-07-29: "tăng tốc độ cào, nếu rate limit thì giảm xuống 1 xíu").
# A fixed 0.5s gap was the bottleneck — measured latency is only ~0.31s, so more than half the
# wall-clock was self-imposed waiting. Start fast, shave the gap a little on every clean response,
# and back off multiplicatively the moment the server throttles. Additive-decrease /
# multiplicative-increase converges on the highest rate the API will tolerate without earning the
# multi-minute rate-ban that stalled the pipeline three times today.
# Tuning note: the first pass used x2 increase / -0.005 additive decrease. Five 429s drove the gap
# 0.05 -> 2.04s and the additive recovery would have needed ~400 clean calls to come back, so net
# throughput fell BELOW the fixed-gap version. Backing off gently and recovering geometrically
# keeps the controller responsive in both directions.
GAP = [0.25]
GAP_MIN, GAP_MAX = 0.05, 3.0
STATS = {"calls": 0, "429s": 0}

region = sys.argv[1] if len(sys.argv) > 1 else "GLB"
_rest = sys.argv[2:]
if _rest and not _rest[0].isdigit():
    universes = [_rest[0]]
    delay = int(_rest[1]) if len(_rest) > 1 else 1
else:
    # every universe legal for this region, read from the platform's own settings options
    _so = json.load(open(ROOT / "fetched/rc/settings_options.json"))

    def _find(o, key):
        if isinstance(o, dict):
            if key in o:
                return o[key]
            for v in o.values():
                r = _find(v, key)
                if r is not None:
                    return r
        return None

    _u = _find(_so, "universe")
    universes = [x["value"] for x in _u["choices"]["instrumentType"]["EQUITY"]["region"][region]]
    # Crawl the COMPETITION universe first so its catalog is usable before the rest finishes:
    # GAC2026 (2026-07-27..08-30) runs on GLB / TOPDIV3000.
    _first = {"GLB": "TOPDIV3000"}.get(region)
    if _first in universes:
        universes = [_first] + [u for u in universes if u != _first]
    delay = int(_rest[0]) if _rest else 1

s = requests.Session()
# NOTE: no `Connection: close`. fetch_all_data.py sets it, and copying that here cost 4x:
# measured 1.104 s/call with the header vs 0.280 s/call on the default keep-alive, because it
# forces a fresh TCP+TLS handshake per request. With ~650 calls per universe that is the single
# largest cost in the crawl — far larger than the request pacing it was competing with.
c = pickle.load(open(ROOT / "state/wq_cookies.pkl", "rb"))
(s.cookies.update(c) if isinstance(c, dict) else [s.cookies.set_cookie(x) for x in c])
_last = [0.0]


def get(path, **params):
    """One rate-gated GET. 429 backs off on Retry-After instead of giving up — a throttled read
    is a transient condition, not a missing resource (the lesson that cost a day's measurements)."""
    for _ in range(60):
        dt = time.time() - _last[0]
        if dt < GAP[0]:
            time.sleep(GAP[0] - dt)
        try:
            r = s.get(B + path, params=params, timeout=60)
        except Exception as e:
            print(f"  conn error {str(e)[:50]} — retry", flush=True)
            GAP[0] = min(GAP_MAX, GAP[0] * 2 + 0.05)
            time.sleep(5)
            continue
        _last[0] = time.time()
        STATS["calls"] += 1
        if r.status_code == 429:
            STATS["429s"] += 1
            GAP[0] = min(GAP_MAX, GAP[0] * 1.6 + 0.05)    # back off, but not so hard it can't return
            time.sleep(min(float(r.headers.get("Retry-After", 10)), 60))
            continue
        if r.status_code == 200 and not r.text:
            time.sleep(1)
            continue
        GAP[0] = max(GAP_MIN, GAP[0] * 0.97)              # geometric recovery: ~120 calls from 2.0s
        return r
    return None


def page(path, **base):
    """Yield every result across pages, failing loudly rather than silently truncating."""
    off = 0
    while True:
        r = get(path, **base, limit=50, offset=off)
        if r is None:
            raise RuntimeError(f"{path}: no response at offset {off}")
        j = r.json()
        res = j.get("results", [])
        for x in res:
            yield x
        off += len(res)
        total = j.get("count", 0)
        if off >= total:
            return
        if not res:
            raise RuntimeError(f"{path}: truncated at {off}/{total}")


T0 = time.time()
print(f"region={region} delay={delay} universes={universes}", flush=True)

# The global /data-fields query CAPS at 10,000 results per universe — verified: it reports
# count=10000 for every GLB universe, while summing fieldCount over just the first 50 of 138
# datasets already gives 14,581. Paging per dataset (`dataset.id=<id>`) returns the true count
# (analyst14 -> 925, exactly its fieldCount), so that is the only way to crawl the region in full.
# RESUME: reload whatever a previous run already wrote, so tuning restarts cost nothing.
datasets, fields = {}, {}
for _name, _store in ((f"datasets_{region}.jsonl", datasets), (f"fields_{region}.jsonl", fields)):
    _p = OUT / _name
    if _p.exists():
        for _line in open(_p):
            try:
                _r = json.loads(_line)
            except Exception:
                continue
            _store[_r.get("id")] = _r
if fields:
    print(f"resume: {len(datasets)} datasets / {len(fields)} fields already on disk", flush=True)
_done_ds = {(d.get("id"), u) for d in datasets.values() for u in (d.get("_fields_done") or [])}

for universe in universes:
    base = {"region": region, "universe": universe, "delay": delay, "instrumentType": "EQUITY"}
    ds_list = list(page("/data-sets", **base))
    for d in ds_list:
        rec = datasets.setdefault(d.get("id"), {**d, "_delay": delay, "_universes": []})
        rec["_universes"].append(universe)
    n_f, before = 0, len(fields)
    for i, d in enumerate(ds_list, 1):
        did = d.get("id")
        if (did, universe) in _done_ds:
            continue
        try:
            for x in page("/data-fields", **base, **{"dataset.id": did}):
                rec = fields.setdefault(x.get("id"), {**x, "_delay": delay, "_universes": []})
                if universe not in rec["_universes"]:
                    rec["_universes"].append(universe)
                if (x.get("coverage") or 0) > (rec.get("coverage") or 0):
                    rec["coverage"] = x.get("coverage")
                n_f += 1
            _done_ds.add((did, universe))
            datasets[did]["_fields_done"] = sorted(
                set(datasets[did].get("_fields_done") or []) | {universe})
        except Exception as e:
            print(f"    ! {did}: {str(e)[:60]}", flush=True)
        if i % 20 == 0:
            with open(OUT / f"fields_{region}.jsonl", "w") as _f:
                for _x in fields.values():
                    _f.write(json.dumps(_x, ensure_ascii=False) + "\n")
            with open(OUT / f"datasets_{region}.jsonl", "w") as _f:
                for _d in datasets.values():
                    _f.write(json.dumps(_d, ensure_ascii=False) + "\n")
            el = time.time() - T0
            print(f"    {universe} {i}/{len(ds_list)} ds, {n_f} rows, union {len(fields)}"
                  f" | {STATS['calls']} calls {STATS['429s']} x429"
                  f" | gap={GAP[0]:.3f}s rate={STATS['calls']/max(el,1):.1f}/s", flush=True)
    print(f"  {universe:12} datasets={len(ds_list):5} field-rows={n_f:6}"
          f"   NEW={len(fields) - before:6}  (union: {len(datasets)} ds / {len(fields)} fields)",
          flush=True)
    # flush after every universe: a multi-hour crawl must be usable before it finishes
    with open(OUT / f"datasets_{region}.jsonl", "w") as _f:
        for _d in datasets.values():
            _f.write(json.dumps(_d, ensure_ascii=False) + "\n")
    with open(OUT / f"fields_{region}.jsonl", "w") as _f:
        for _x in fields.values():
            _f.write(json.dumps(_x, ensure_ascii=False) + "\n")
    print(f"    [flushed {len(fields)} fields to fields_{region}.jsonl]", flush=True)

ds_path = OUT / f"datasets_{region}.jsonl"
with open(ds_path, "w") as f:
    for d in datasets.values():
        f.write(json.dumps(d, ensure_ascii=False) + "\n")

f_path = OUT / f"fields_{region}.jsonl"
with open(f_path, "w") as f:
    for x in fields.values():
        f.write(json.dumps(x, ensure_ascii=False) + "\n")

print(f"\nUNION: {len(datasets)} datasets -> {ds_path.name}", flush=True)
print(f"UNION: {len(fields)} fields   -> {f_path.name}", flush=True)
import collections
print("by type:", dict(collections.Counter(x.get("type") for x in fields.values())), flush=True)
