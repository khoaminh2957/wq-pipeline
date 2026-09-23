#!/usr/bin/env python3
"""Robust re-sim: cookie-reuse + persona fallback; 2 workers; POST retries on
429 CONCURRENT_SIMULATION_LIMIT (waits Retry-After, never drops a spec); global
min-gap mutex (avoid req/min ban). Pulls IS PnL, saves incrementally."""
import json, time, socket, threading, pickle
from pathlib import Path
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
import requests
socket.setdefaulttimeout(40)
H="https://api.worldquantbrain.com"; OUT=Path("/tmp/harness"); CK=OUT/"wq_cookies.pkl"
lock=threading.Lock(); post_gate=threading.Lock(); last=[0.0]
def status(**k):
    with lock: json.dump(k, open(OUT/"pbo_status.json","w"))
def gated_post(url, **kw):
    with post_gate:
        dt=time.time()-last[0]
        if dt<0.6: time.sleep(0.6-dt)
        last[0]=time.time()
        return s.post(url, **kw)
d=dict(l.split("=",1) for l in (Path.home()/".wqbrain_creds").read_text().strip().split("\n") if "=" in l)
s=requests.Session(); s.headers.update({"Connection":"close"})

# ---- auth: reuse cookie else persona ----
authed=False
if CK.exists():
    try:
        s.cookies.update(pickle.load(open(CK,"rb")))
        authed = s.get(H+"/authentication", timeout=20).status_code in (200,201)
    except Exception: authed=False
if not authed:
    s.auth=(d["email"], d["password"])
    status(stage="auth"); r=s.post(H+"/authentication", timeout=30)
    authed=r.status_code in (200,201)
    if not authed and r.status_code==401 and r.headers.get("WWW-Authenticate")=="persona":
        bio=urljoin(r.url, r.headers.get("Location","")); (OUT/"persona_url.txt").write_text(bio)
        status(stage="await_biometric", persona=bio)
        for _ in range(150):
            time.sleep(5)
            try: rr=s.post(bio, timeout=30)
            except Exception: continue
            if rr.status_code in (200,201): authed=True; break
    if not authed: status(stage="AUTH_FAIL", code=r.status_code, body=r.text[:200]); raise SystemExit
    try: pickle.dump(s.cookies, open(CK,"wb"))
    except Exception: pass
status(stage="authed")

specs=json.load(open(OUT/"pbo_specs.json")); pnls={}; log=[]; done=[0]
def simulate(spec, dbg=False):
    body={"type":"REGULAR","settings":dict(spec["settings"], nanHandling="ON"),"regular":spec["formula"]}
    r=None
    for _ in range(60):                       # retry on concurrency limit
        r=gated_post(H+"/simulations", json=body, timeout=35)
        if r.status_code==429 and "CONCURRENT" in (r.text or ""):
            time.sleep(float(r.headers.get("Retry-After",6) or 6)); continue
        if r.status_code==429:                # req/min ban -> wait the full Retry-After
            time.sleep(float(r.headers.get("Retry-After",30) or 30)); continue
        break
    if dbg:
        with lock: open(OUT/"pbo_first_sim.json","w").write(f"{r.status_code}\n{dict(r.headers)}\n{r.text[:300]}")
    if r.status_code not in (200,201): return None,{"err":r.status_code,"body":(r.text or '')[:300]}
    loc=r.headers.get("Location")
    if not loc: return None,{"err":"no_location"}
    url=urljoin(H, loc) if loc.startswith("/") else loc
    for _ in range(200):
        g=s.get(url, timeout=35); ra=g.headers.get("Retry-After")
        try: j=g.json()
        except Exception: j={}
        st=(j.get("status") or "").upper()
        if j.get("alpha") or st in ("COMPLETE","WARNING","ERROR","FAIL"): return j.get("alpha"), j
        if g.status_code>=400: return None,{"err":g.status_code,"body":(g.text or '')[:300]}
        time.sleep(float(ra) if ra else 3)
    return None,{"err":"sim_timeout"}
def get_pnl(aid, dbg=False):
    g=s.get(f"{H}/alphas/{aid}/recordsets/pnl", timeout=35)
    if dbg:
        with lock: open(OUT/"pbo_first_pnl.json","w").write(f"{g.status_code}\n{(g.text or '')[:900]}")
    if g.status_code!=200: return None,{"err":g.status_code,"body":(g.text or '')[:200]}
    try: return g.json(),None
    except Exception as e: return None,{"err":str(e)}
firstpnl=[False]
def work(ix):
    idx,spec=ix
    aid,meta=simulate(spec, dbg=(idx==0))
    e={"src":spec["alpha_id_src"]}
    if not aid: e["sim_fail"]=meta
    else:
        dbg=False
        with lock:
            if not firstpnl[0]: firstpnl[0]=True; dbg=True
        pj,perr=get_pnl(aid, dbg=dbg)
        if pj is None: e.update({"alpha":aid,"pnl_fail":perr})
        else:
            e.update({"alpha":aid,"ok":True})
            with lock: pnls[spec["alpha_id_src"]]={"alpha":aid,"pnl":pj}; json.dump(pnls, open(OUT/"pbo_pnl.json","w"))
    with lock:
        log.append(e); json.dump(log, open(OUT/"pbo_log.json","w"))
        done[0]+=1; json.dump({"stage":"sim","done":done[0],"n":len(specs),"got":len(pnls)}, open(OUT/"pbo_status.json","w"))
    return e
with ThreadPoolExecutor(max_workers=3) as ex:
    list(ex.map(work, list(enumerate(specs))))
status(stage="DONE", got=len(pnls), total=len(specs))
