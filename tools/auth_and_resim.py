#!/usr/bin/env python3
"""Persona re-auth (poll while user does biometric) -> save cookie -> re-sim the d0
shortlist -> robust_pnl.json. One background process; writes persona_url.txt + status."""
import json, time, socket, threading, pickle
from pathlib import Path
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
import requests
socket.setdefaulttimeout(40)
H="https://api.worldquantbrain.com"; OUT=Path("/Users/kanenguyen/wq_pipeline/state")
def status(**k): json.dump(k, open(OUT/"auth_resim_status.json","w"))
d=dict(l.split("=",1) for l in (Path.home()/".wqbrain_creds").read_text().strip().splitlines() if "=" in l)
s=requests.Session(); s.headers.update({"Connection":"close"}); s.auth=(d["email"],d["password"])

# ---- persona auth ----
status(stage="auth_start")
r=s.post(H+"/authentication", timeout=30); authed=r.status_code in (200,201)
if not authed and r.status_code==401 and r.headers.get("WWW-Authenticate")=="persona":
    bio=urljoin(r.url, r.headers.get("Location","")); (OUT/"persona_url.txt").write_text(bio)
    status(stage="await_biometric", persona=bio)
    for i in range(150):
        time.sleep(5)
        try: rr=s.post(bio, timeout=30)
        except Exception: continue
        if rr.status_code in (200,201): authed=True; break
        status(stage="await_biometric", waited=i*5, persona=bio)
if not authed:
    status(stage="AUTH_FAIL", code=r.status_code); raise SystemExit("auth failed")
s.auth=None; pickle.dump(s.cookies, open(OUT/"wq_cookies.pkl","wb")); status(stage="authed")

# ---- re-sim d0 shortlist ----
gate=threading.Lock(); lock=threading.Lock(); last=[0.0]
def gpost(url,**kw):
    with gate:
        dt=time.time()-last[0]
        if dt<0.6: time.sleep(0.6-dt)
        last[0]=time.time(); return s.post(url,**kw)
shortlist=json.load(open("/Users/kanenguyen/wq_pipeline/state/robust_shortlist.json"))
pnls={}
def settings(a):
    return {"instrumentType":"EQUITY","region":a["region"],"universe":a["universe"],"delay":0,
            "decay":int(a["decay"] or 0),"neutralization":a["neut"],"truncation":float(a["trunc"] or 0.08),
            "pasteurization":"ON","unitHandling":"VERIFY","nanHandling":"ON","language":"FASTEXPR",
            "visualization":False,"testPeriod":"P0Y0M"}
def simulate(a):
    body={"type":"REGULAR","settings":settings(a),"regular":a["formula"]}
    for _ in range(50):
        r=gpost(H+"/simulations", json=body, timeout=35)
        if r.status_code==429: time.sleep(float(r.headers.get("Retry-After",8) or 8)); continue
        break
    if r.status_code not in (200,201): return None
    loc=r.headers.get("Location"); url=urljoin(H,loc) if loc and loc.startswith("/") else loc
    if not url: return None
    for _ in range(200):
        g=s.get(url,timeout=35); ra=g.headers.get("Retry-After")
        try: j=g.json()
        except: j={}
        st=(j.get("status") or "").upper()
        if j.get("alpha") or st in ("COMPLETE","WARNING","ERROR","FAIL"): return j.get("alpha")
        if g.status_code>=400: return None
        time.sleep(float(ra) if ra else 3)
    return None
def get_pnl(aid):
    for _ in range(15):
        g=s.get(f"{H}/alphas/{aid}/recordsets/pnl",timeout=35)
        if g.status_code==200 and (g.text or "").strip():
            try:
                j=g.json(); recs=j.get("records") if isinstance(j,dict) else j
                if recs:
                    out=[]
                    for rr in recs:
                        if isinstance(rr,(list,tuple)):
                            v=next((x for x in rr[1:] if isinstance(x,(int,float))),None)
                            out.append((str(rr[0]), float(v) if v is not None else 0.0))
                    return out
            except: pass
        time.sleep(5)
    return []
done=[0]
def work(a):
    aid=simulate(a)
    if aid:
        pnl=get_pnl(aid)
        if pnl:
            with lock: pnls[a["id"]]={"alpha":aid,"pnl":pnl}; json.dump(pnls,open(OUT/"robust_pnl.json","w"))
    with lock:
        done[0]+=1; status(stage="resim", done=done[0], n=len(shortlist), got=len(pnls))
with ThreadPoolExecutor(max_workers=3) as ex:
    list(ex.map(work, shortlist))
status(stage="DONE", got=len(pnls), n=len(shortlist))
