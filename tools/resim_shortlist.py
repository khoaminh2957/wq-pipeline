#!/usr/bin/env python3
"""Re-simulate the robust shortlist (delay-0, settings from CSV) to fetch IS PnL,
so the full pipeline robust test (holdout + DSR-on-returns + CSCV PBO + self-corr)
can run. Cookie reuse, 3 workers, 0.6s gated POST, 429-retry, async-empty-200 PnL."""
import json, time, socket, threading, pickle
from pathlib import Path
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
import requests
socket.setdefaulttimeout(40)
H="https://api.worldquantbrain.com"; OUT=Path("/Users/kanenguyen/wq_pipeline/state")
lock=threading.Lock(); gate=threading.Lock(); last=[0.0]
def status(**k): json.dump(k, open(OUT/"resim_status.json","w"))
s=requests.Session(); s.headers.update({"Connection":"close"})
s.cookies.update(pickle.load(open(OUT/"wq_cookies.pkl","rb")))
def gpost(url,**kw):
    with gate:
        dt=time.time()-last[0]
        if dt<0.6: time.sleep(0.6-dt)
        last[0]=time.time(); return s.post(url,**kw)
shortlist=json.load(open("/Users/kanenguyen/wq_pipeline/state/robust_shortlist.json"))
pnls=json.load(open(OUT/"robust_pnl.json")) if (OUT/"robust_pnl.json").exists() else {}
done=[len(pnls)]
def settings(a):
    return {"instrumentType":"EQUITY","region":a["region"],"universe":a["universe"],
            "delay":0,"decay":int(a["decay"] or 0),"neutralization":a["neut"],
            "truncation":float(a["trunc"] or 0.08),"pasteurization":"ON","unitHandling":"VERIFY",
            "nanHandling":"ON","language":"FASTEXPR","visualization":False,"testPeriod":"P0Y0M"}
def simulate(a):
    body={"type":"REGULAR","settings":settings(a),"regular":a["formula"]}
    r=None
    for _ in range(50):
        try: r=gpost(H+"/simulations", json=body, timeout=35)
        except Exception: time.sleep(5); continue
        if r.status_code==429: time.sleep(float(r.headers.get("Retry-After",8) or 8)); continue
        break
    if r is None: return None,{"err":"conn"}
    if r.status_code not in (200,201): return None,{"err":r.status_code,"body":(r.text or '')[:200]}
    loc=r.headers.get("Location");  url=urljoin(H,loc) if loc and loc.startswith("/") else loc
    if not url: return None,{"err":"no_loc"}
    for _ in range(200):
        try: g=s.get(url, timeout=35)
        except Exception: time.sleep(4); continue
        ra=g.headers.get("Retry-After")
        try: j=g.json()
        except: j={}
        st=(j.get("status") or "").upper()
        if j.get("alpha") or st in ("COMPLETE","WARNING","ERROR","FAIL"): return j.get("alpha"), j
        if g.status_code>=400: return None,{"err":g.status_code}
        time.sleep(float(ra) if ra else 3)
    return None,{"err":"timeout"}
def get_pnl(aid):
    for _ in range(15):
        try: g=s.get(f"{H}/alphas/{aid}/recordsets/pnl", timeout=35)
        except Exception: time.sleep(5); continue
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
def work(a):
    if a["id"] in pnls: return
    try:
        aid,meta=simulate(a)
        rec={"src":a["id"]}
        if aid:
            pnl=get_pnl(aid)
            if pnl:
                with lock: pnls[a["id"]]={"alpha":aid,"pnl":pnl}; json.dump(pnls,open(OUT/"robust_pnl.json","w"))
            rec.update(alpha=aid, n=len(pnl))
        else: rec.update(fail=meta)
    except Exception as e:
        rec={"src":a["id"],"err":str(e)[:120]}
    with lock:
        done[0]+=1; status(stage="resim", done=done[0], n=len(shortlist), got=len(pnls), last=rec)
status(stage="start", n=len(shortlist))
with ThreadPoolExecutor(max_workers=3) as ex:
    list(ex.map(work, shortlist))
status(stage="DONE", got=len(pnls), n=len(shortlist))
print("DONE", len(pnls))
