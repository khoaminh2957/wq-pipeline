#!/usr/bin/env python3
"""Comprehensive one-shot WQ Brain data fetch for later analysis.

SINGLE sequential process (one rate-gate) to avoid the 28-min concurrency ban.
Saves incrementally + resumable, into wq_pipeline/fetched/ :

  operators.json                 all operators
  datasets.jsonl                 dataset catalog (delay 0 & 1)
  fields_all.jsonl               every data field (delay 0 & 1) with coverage/counts
  alphas_all.jsonl               every account alpha: settings + formula + IS metrics + checks
  pnl/<alpha_id>.jsonl           per-alpha daily PnL series [date, pnl]  (resumable)
  _progress.json                 phase/counters

Phases run fast -> slow; PnL (last) is the multi-hour part and is resumable.
Run:  python tools/fetch_all_data.py            # all phases
      python tools/fetch_all_data.py pnl        # only (resume) the PnL phase
"""
from __future__ import annotations
import sys, json, time, pickle, pathlib
import requests
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config

B = config.WQ_API
OUT = pathlib.Path(__file__).resolve().parent.parent / "fetched"
(OUT / "pnl").mkdir(parents=True, exist_ok=True)
REGION, UNIVERSE, DELAYS = "USA", "TOP3000", [1, 0]
MIN_GAP = 0.45

s = requests.Session(); s.headers.update({"Connection": "close"})
s.cookies.update(pickle.load(open(config.COOKIE_PATH, "rb")))
_last = [0.0]
MAX_429 = 6; _n429 = [0]


def get(path, **params):
    for _ in range(50):
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
            time.sleep(w); continue
        if r.status_code == 401:
            raise SystemExit("401 — session expired; re-auth (biometric) and rerun")
        return r
    return None


def prog(**kw):
    p = {}
    pf = OUT / "_progress.json"
    if pf.exists():
        p = json.loads(pf.read_text())
    p.update(kw); p["ts"] = round(time.time(), 1)
    pf.write_text(json.dumps(p, indent=1))


def phase_catalog():
    # operators
    r = get("/operators")
    if r and r.headers.get("content-type", "").startswith("application/json"):
        (OUT / "operators.json").write_text(json.dumps(r.json(), ensure_ascii=False, indent=1))
        print(f"operators: {len(r.json())}", flush=True)
    # datasets + fields per delay
    dsf = open(OUT / "datasets.jsonl", "w")
    ff = open(OUT / "fields_all.jsonl", "w")
    nfields = 0
    for delay in DELAYS:
        base = {"region": REGION, "universe": UNIVERSE, "delay": delay, "instrumentType": "EQUITY"}
        # datasets
        off = 0
        while True:
            r = get("/data-sets", **base, limit=50, offset=off)
            j = r.json(); res = j.get("results", [])
            for d in res:
                d["_delay"] = delay; dsf.write(json.dumps(d, ensure_ascii=False) + "\n")
            off += len(res)
            if off >= j.get("count", 0):
                break
            if not res:
                raise RuntimeError(f"truncated data-sets delay {delay}: {off}/{j.get('count')}")
        # all fields (across datasets) for this delay
        off = 0
        while True:
            r = get("/data-fields", **base, limit=50, offset=off)
            j = r.json(); res = j.get("results", [])
            for f in res:
                f["_delay"] = delay; ff.write(json.dumps(f, ensure_ascii=False) + "\n"); nfields += 1
            off += len(res)
            if off >= j.get("count", 0):
                break
            if not res:
                raise RuntimeError(f"truncated data-fields delay {delay}: {off}/{j.get('count')}")
            if off % 1000 == 0:
                print(f"  delay {delay} fields {off}/{j.get('count')}", flush=True)
        ff.flush()
        print(f"delay {delay}: fields done", flush=True)
    dsf.close(); ff.close()
    print(f"fields_all: {nfields} rows", flush=True)
    prog(catalog="done", n_fields=nfields)


def phase_alphas():
    """All account alphas with inline IS metrics + formula + settings + checks."""
    path = OUT / "alphas_all.jsonl"
    f = open(path, "w")
    off, total = 0, None
    while True:
        r = get("/users/self/alphas", limit=100, offset=off)
        j = r.json(); total = j.get("count"); res = j.get("results", [])
        for a in res:
            iss = a.get("is") or {}
            row = {
                "id": a.get("id"), "formula": (a.get("regular") or {}).get("code") if isinstance(a.get("regular"), dict) else a.get("regular"),
                "settings": a.get("settings"), "category": a.get("category"),
                "grade": a.get("grade"), "stage": a.get("stage"), "status": a.get("status"),
                "dateCreated": a.get("dateCreated"), "dateSubmitted": a.get("dateSubmitted"),
                "sharpe": iss.get("sharpe"), "fitness": iss.get("fitness"), "turnover": iss.get("turnover"),
                "returns": iss.get("returns"), "drawdown": iss.get("drawdown"), "margin": iss.get("margin"),
                "longCount": iss.get("longCount"), "shortCount": iss.get("shortCount"),
                "checks": iss.get("checks"), "os_sharpe": (a.get("os") or {}).get("sharpe"),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        off += 100
        print(f"  alphas {min(off, total or off)}/{total}", flush=True)
        if not res or (total and off >= total):
            break
    f.close()
    prog(alphas="done", n_alphas=total)
    print(f"alphas_all: {total}", flush=True)


def phase_pnl():
    """Per-alpha PnL, resumable (skips existing files)."""
    ids = [json.loads(l)["id"] for l in open(OUT / "alphas_all.jsonl")]
    done = {p.stem for p in (OUT / "pnl").glob("*.jsonl")}
    todo = [a for a in ids if a and a not in done]
    print(f"PnL: {len(ids)} total, {len(done)} done, {len(todo)} to fetch", flush=True)
    for i, aid in enumerate(todo):
        recs = None
        for _ in range(6):
            r = get(f"/alphas/{aid}/recordsets/pnl")
            if r is None:
                break
            if r.status_code == 200 and (r.text or "").strip() and r.headers.get("content-type", "").startswith("application/json"):
                j = r.json(); recs = j.get("records") if isinstance(j, dict) else j
                if recs:
                    break
            time.sleep(3)
        if recs:
            with open(OUT / "pnl" / f"{aid}.jsonl", "w") as pf:
                for rec in recs:
                    pf.write(json.dumps(rec) + "\n")
        if (i + 1) % 50 == 0:
            print(f"  PnL {i+1}/{len(todo)} (last {aid}, {len(recs or [])} pts)", flush=True)
            prog(pnl_done=len(done) + i + 1, pnl_total=len(ids))
    prog(pnl="done", pnl_done=len(ids), pnl_total=len(ids))
    print("PnL: done", flush=True)


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only in (None, "catalog"):
        phase_catalog()
    if only in (None, "alphas"):
        phase_alphas()
    if only in (None, "pnl"):
        phase_pnl()
    print("FETCH COMPLETE", flush=True)
