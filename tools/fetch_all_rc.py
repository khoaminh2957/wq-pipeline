#!/usr/bin/env python3
"""Research-Consultant full data crawl for WQ BRAIN.

Discovers every (region, universe, delay) combo now unlocked via OPTIONS /simulations,
then crawls into wq_pipeline/fetched/rc/ :

  settings_options.json        the full allowed-settings matrix (regions/universes/delays/…)
  operators.json               all operators at RC level
  datasets.jsonl               dataset catalog for EVERY (region, universe, delay) combo
  fields/<REGION>_<UNI>_d<D>.jsonl   every data field per combo (paged, resumable per combo)
  alphas_all.jsonl             refreshed account-alpha metadata
  _progress.json               done-combo bookkeeping

SINGLE sequential process (one rate gate, 0.45s) to respect rate limits. Resumable:
finished combos are skipped on rerun. PnL intentionally NOT crawled (per earlier call).

Run:  python tools/fetch_all_rc.py
"""
from __future__ import annotations
import sys, json, time, pickle, pathlib
import requests

H = "https://api.worldquantbrain.com"
ROOT = pathlib.Path("/Users/kanenguyen/wq_pipeline")
OUT = ROOT / "fetched" / "rc"
(OUT / "fields").mkdir(parents=True, exist_ok=True)
MIN_GAP = 0.5

s = requests.Session(); s.headers.update({"Connection": "close"})
s.cookies.update(pickle.load(open(ROOT / "state" / "wq_cookies.pkl", "rb")))
_last = [0.0]


def req(method, path, **kw):
    for attempt in range(40):
        dt = time.time() - _last[0]
        if dt < MIN_GAP:
            time.sleep(MIN_GAP - dt)
        _last[0] = time.time()
        try:
            r = s.request(method, H + path, timeout=40, **kw)
        except Exception:
            time.sleep(5); continue
        if r.status_code == 429:
            # measured live: Retry-After is ~1s — honor it with a small cushion only
            ra = float(r.headers.get("Retry-After") or 0)
            time.sleep(max(ra, 1.0) + 0.5 + min(attempt * 0.5, 5)); continue
        if r.status_code >= 500:
            # the data API throws transient 500s under load — back off and retry
            time.sleep(5 + min(attempt * 2, 30)); continue
        if r.status_code == 401:
            raise SystemExit("401 — session expired; rerun tools/auth_only.py + biometric")
        return r
    raise RuntimeError(f"throttled out after 40 attempts: {path}")


def prog(**kw):
    p = {}
    pf = OUT / "_progress.json"
    if pf.exists():
        p = json.loads(pf.read_text())
    p.update(kw); p["ts"] = round(time.time(), 1)
    pf.write_text(json.dumps(p, indent=1))


def get_progress():
    pf = OUT / "_progress.json"
    return json.loads(pf.read_text()) if pf.exists() else {}


# ---- 1. allowed-settings matrix ----
def discover_combos():
    cj = OUT / "combos.json"
    if cj.exists():                                   # reuse a prior full discovery
        combos = [tuple(x) for x in json.loads(cj.read_text())]
        if len(combos) >= 30:
            print(f"combos reused from combos.json: {len(combos)}", flush=True)
            return combos
    r = req("OPTIONS", "/simulations")
    combos, raw = [], {}
    try:
        raw = r.json()
    except Exception:
        pass
    (OUT / "settings_options.json").write_text(json.dumps(raw, ensure_ascii=False, indent=1))
    # walk the schema for instrumentType EQUITY: settings.properties.{region,universe,delay}
    # BRAIN returns per-instrument choices as a list of {region, delay, universe, ...} legs
    def walk(o):
        if isinstance(o, dict):
            if "region" in o and "universe" in o and "delay" in o:
                regs = o["region"] if isinstance(o["region"], list) else [o["region"]]
                unis = o["universe"] if isinstance(o["universe"], list) else [o["universe"]]
                dels = o["delay"] if isinstance(o["delay"], list) else [o["delay"]]
                for rg in regs:
                    for un in unis:
                        for dl in dels:
                            if isinstance(rg, str) and isinstance(un, str):
                                combos.append((rg, un, int(dl)))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(raw)
    combos = sorted(set(combos))
    if not combos:                                   # fallback probe matrix
        REGIONS = {"USA": ["TOP3000", "TOP1000", "TOP500", "TOP200", "TOPSP500", "MINVOL1M", "ILLIQUID_MINVOL1M"],
                   "GLB": ["TOP3000", "MINVOL1M"], "EUR": ["TOP2500", "TOP1200", "TOP800", "TOP400", "ILLIQUID_MINVOL1M"],
                   "ASI": ["MINVOL1M", "ILLIQUID_MINVOL1M"], "CHN": ["TOP2000U"],
                   "AMR": ["TOP600"], "JPN": ["TOP1600", "TOP1200"], "KOR": ["TOP600"],
                   "TWN": ["TOP500", "TOP100"], "HKG": ["TOP800", "TOP500"], "IND": ["TOP500", "TOP200"]}
        for rg, unis in REGIONS.items():
            for un in unis:
                for dl in (1, 0):
                    r2 = req("GET", "/data-sets", params={"region": rg, "universe": un, "delay": dl,
                                                          "instrumentType": "EQUITY", "limit": 1})
                    ok = False
                    try:
                        ok = r2.status_code == 200 and (r2.json().get("count") or 0) > 0
                    except Exception:
                        pass
                    if ok:
                        combos.append((rg, un, dl))
                    print(f"  probe {rg}/{un}/d{dl}: {'OK' if ok else '-'}", flush=True)
    print(f"combos discovered: {len(combos)}", flush=True)
    (OUT / "combos.json").write_text(json.dumps(combos, indent=1))
    return combos


# ---- 2. operators ----
def phase_operators():
    r = req("GET", "/operators")
    if r is not None and r.headers.get("content-type", "").startswith("application/json"):
        ops = r.json()
        (OUT / "operators.json").write_text(json.dumps(ops, ensure_ascii=False, indent=1))
        print(f"operators: {len(ops)}", flush=True)
        prog(operators=len(ops))


# ---- 3. datasets + fields per combo ----
def paged(path, base, tag):
    """Yield every row; raise if the server-reported count can't be reached
    (so a throttled/truncated combo is never silently marked complete)."""
    off, got, count = 0, 0, None
    while True:
        r = req("GET", path, params={**base, "limit": 50, "offset": off})
        j = r.json()                                  # req() never returns None now
        if count is None:
            count = j.get("count")
            if count is None:
                raise RuntimeError(f"no count in response: {path} {base} -> {str(j)[:120]}")
        res = j.get("results", [])
        for x in res:
            x["_region"], x["_universe"], x["_delay"] = tag
            yield x
        got += len(res); off += 50
        if got >= count:
            break
        if not res:
            raise RuntimeError(f"truncated: {path} {base} got {got}/{count}")


def phase_catalog(combos):
    done = set(tuple(x) for x in get_progress().get("combos_done", []))
    for i, (rg, un, dl) in enumerate(combos):
        if (rg, un, dl) in done:
            continue
        base = {"region": rg, "universe": un, "delay": dl, "instrumentType": "EQUITY"}
        tag = (rg, un, dl)
        try:
            ds_rows = list(paged("/data-sets", base, tag))
            # the unfiltered fields listing caps its count at 10000 — when a combo hits
            # the cap, fetch per dataset instead (exact, verified per dataset)
            probe = req("GET", "/data-fields", params={**base, "limit": 1}).json()
            if (probe.get("count") or 0) >= 10000:
                f_rows = []
                for k, d in enumerate(ds_rows):
                    f_rows += list(paged("/data-fields", {**base, "dataset.id": d["id"]}, tag))
                    if (k + 1) % 50 == 0:
                        print(f"    …{rg}/{un}/d{dl}: dataset {k+1}/{len(ds_rows)}, fields so far {len(f_rows)}",
                              flush=True)
            else:
                f_rows = list(paged("/data-fields", base, tag))
        except RuntimeError as e:                     # throttled/truncated: retry this combo later
            print(f"[{i+1:3d}/{len(combos)}] {rg:4s} {un:18s} d{dl}: RETRY-LATER ({e})", flush=True)
            time.sleep(20)
            continue
        # write only after BOTH paged() calls completed & verified against server counts
        with open(OUT / f"datasets_{rg}_{un}_d{dl}.jsonl", "w") as dsf:
            for d in ds_rows:
                dsf.write(json.dumps(d, ensure_ascii=False) + "\n")
        with open(OUT / "fields" / f"{rg}_{un}_d{dl}.jsonl", "w") as ff:
            for f in f_rows:
                ff.write(json.dumps(f, ensure_ascii=False) + "\n")
        done.add((rg, un, dl))
        prog(combos_done=[list(x) for x in done], n_combos=len(combos))
        print(f"[{i+1:3d}/{len(combos)}] {rg:4s} {un:18s} d{dl}: datasets={len(ds_rows):3d} fields={len(f_rows)}", flush=True)


# ---- 4. refresh alphas metadata ----
def phase_alphas():
    path = OUT / "alphas_all.jsonl"
    f = open(path, "w")
    off, total = 0, None
    while True:
        r = req("GET", "/users/self/alphas", params={"limit": 100, "offset": off})
        j = r.json(); total = j.get("count"); res = j.get("results", [])
        for a in res:
            iss = a.get("is") or {}
            f.write(json.dumps({
                "id": a.get("id"),
                "formula": (a.get("regular") or {}).get("code") if isinstance(a.get("regular"), dict) else a.get("regular"),
                "settings": a.get("settings"), "grade": a.get("grade"), "stage": a.get("stage"),
                "status": a.get("status"), "dateCreated": a.get("dateCreated"),
                "sharpe": iss.get("sharpe"), "fitness": iss.get("fitness"), "turnover": iss.get("turnover"),
                "returns": iss.get("returns"), "drawdown": iss.get("drawdown"), "margin": iss.get("margin"),
                "checks": iss.get("checks"), "os_sharpe": (a.get("os") or {}).get("sharpe"),
            }, ensure_ascii=False) + "\n")
        f.flush(); off += 100
        if off % 1000 == 0:
            print(f"  alphas {min(off, total or off)}/{total}", flush=True)
        if not res or (total and off >= total):
            break
    f.close()
    prog(alphas=total)
    print(f"alphas_all: {total}", flush=True)


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    combos = discover_combos()
    if only in (None, "operators"):
        phase_operators()
    if only in (None, "catalog"):
        for _pass in range(6):                        # RETRY-LATER combos get fresh passes
            phase_catalog(combos)
            left = len(combos) - len(get_progress().get("combos_done", []))
            if left == 0:
                break
            print(f"pass {_pass+1}: {left} combos remaining, sleeping 60s", flush=True)
            time.sleep(60)
    if only in (None, "alphas"):
        phase_alphas()
    print("RC FETCH COMPLETE", flush=True)
