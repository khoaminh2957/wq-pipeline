#!/usr/bin/env python3
"""Auth (persona) -> re-simulate cohort with 3 CONCURRENT workers (WQ slot limit) -> pull IS PnL.
Saves PnL incrementally + raw dumps. Thread-safe writes."""
import json, time, socket, threading
from pathlib import Path
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
import requests
socket.setdefaulttimeout(35)
H="https://api.worldquantbrain.com"; OUT=Path("/tmp/harness")
lock=threading.Lock()
def status(**k):
    with lock: json.dump(k, open(OUT/"pbo_status.json","w"))
d=dict(l.split("=",1) for l in (Path.home()/".wqbrain_creds").read_text().strip().split("\n") if "=" in l)
s=requests.Session(); s.auth=(d["email"], d["password"]); s.headers.update({"Connection":"close"})

status(stage="auth")
r=s.post(H+"/authentication", timeout=30)
authed=r.status_code in (200,201)
if not authed and r.status_code==401 and r.headers.get("WWW-Authenticate")=="persona":
    bio=urljoin(r.url, r.headers.get("Location","")); (OUT/"persona_url.txt").write_text(bio)
    status(stage="await_biometric", persona=bio)
    for _ in range(150):
        time.sleep(5)
        try: rr=s.post(bio, timeout=30)
        except Exception: continue
        if rr.status_code in (200,201): authed=True; break
if not authed:
    status(stage="AUTH_FAIL", code=r.status_code, body=r.text[:200]); raise SystemExit
status(stage="authed")

specs=json.load(open(OUT/"pbo_specs.json"))
pnls={}; log=[]; done=[0]
def simulate(spec, dbg=False):
    body={"type":"REGULAR","settings":dict(spec["settings"], nanHandling="ON"),"regular":spec["formula"]}
    r=s.post(H+"/simulations", json=body, timeout=35)
    if dbg:
        with lock: open(OUT/"pbo_first_sim.json","w").write(f"POST {r.status_code}\n{dict(r.headers)}\n{r.text[:400]}")
    if r.status_code not in (200,201): return None,{"err":r.status_code,"body":r.text[:300]}
    loc=r.headers.get("Location")
    if not loc: return None,{"err":"no_location"}
    url=urljoin(H, loc) if loc.startswith("/") else loc
    for _ in range(180):
        g=s.get(url, timeout=35); ra=g.headers.get("Retry-After")
        try: j=g.json()
        except Exception: j={}
        st=(j.get("status") or "").upper()
        if j.get("alpha") or st in ("COMPLETE","WARNING","ERROR","FAIL"): return j.get("alpha"), j
        if g.status_code>=400: return None,{"err":g.status_code,"body":g.text[:300]}
        time.sleep(float(ra) if ra else 3)
    return None,{"err":"sim_timeout"}
def get_pnl(aid, dbg=False):
    g=s.get(f"{H}/alphas/{aid}/recordsets/pnl", timeout=35)
    if dbg:
        with lock: open(OUT/"pbo_first_pnl.json","w").write(f"{g.status_code}\n{g.text[:900]}")
    if g.status_code!=200: return None,{"err":g.status_code,"body":g.text[:200]}
    try: return g.json(),None
    except Exception as e: return None,{"err":str(e)}
def work(idx_spec):
    idx,spec=idx_spec
    aid,meta=simulate(spec, dbg=(idx==0))
    entry={"src":spec["alpha_id_src"]}
    if not aid: entry["sim_fail"]=meta
    else:
        pj,perr=get_pnl(aid, dbg=False)
        if pj is None: entry.update({"alpha":aid,"pnl_fail":perr})
        else: entry.update({"alpha":aid,"ok":True})
        with lock:
            if pj is not None:
                pnls[spec["alpha_id_src"]]={"alpha":aid,"pnl":pj}; json.dump(pnls, open(OUT/"pbo_pnl.json","w"))
    with lock:
        log.append(entry); json.dump(log, open(OUT/"pbo_log.json","w"))
        done[0]+=1; json.dump({"stage":"sim","done":done[0],"n":len(specs),"got":len(pnls)}, open(OUT/"pbo_status.json","w"))
    # ensure first PnL raw dump happens once
    if entry.get("ok") and not (OUT/"pbo_first_pnl.json").exists():
        get_pnl(entry["alpha"], dbg=True)
    return entry

with ThreadPoolExecutor(max_workers=3) as ex:
    list(ex.map(work, list(enumerate(specs))))
status(stage="DONE", got=len(pnls), total=len(specs))
