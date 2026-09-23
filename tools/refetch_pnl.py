#!/usr/bin/env python3
"""Re-fetch PnL recordsets for already-simulated alphas (by id), retrying past the
async-empty-200 while WQ finishes computing the recordset. Uses saved cookie (no auth, no re-sim)."""
import json, time, pickle, socket
from pathlib import Path
import requests
socket.setdefaulttimeout(40)
H="https://api.worldquantbrain.com"; OUT=Path("/Users/kanenguyen/wq_pipeline/state")
def status(**k): json.dump(k, open(OUT/"refetch_status.json","w"))
s=requests.Session(); s.headers.update({"Connection":"close"})
s.cookies.update(pickle.load(open(OUT/"wq_cookies.pkl","rb")))
log=json.load(open(OUT/"pbo_log.json"))
ids={}
for e in log:
    if e.get("alpha"): ids[e["src"]]=e["alpha"]
pnls=json.load(open(OUT/"pbo_pnl.json")) if (OUT/"pbo_pnl.json").exists() else {}
status(stage="start", total=len(ids), have=len(pnls))
got=len(pnls)
for src,aid in ids.items():
    if src in pnls: continue
    ok=False
    for attempt in range(15):
        try: g=s.get(f"{H}/alphas/{aid}/recordsets/pnl", timeout=40)
        except Exception: time.sleep(6); continue
        if g.status_code==200 and (g.text or "").strip():
            try:
                j=g.json()
                if (j.get("records") if isinstance(j,dict) else j):
                    pnls[src]={"alpha":aid,"pnl":j}; ok=True; break
            except Exception: pass
        time.sleep(6)
    if ok: got+=1; json.dump(pnls, open(OUT/"pbo_pnl.json","w"))
    status(stage="fetching", total=len(ids), got=got, last=src, last_ok=ok)
status(stage="DONE", total=len(ids), got=got)
