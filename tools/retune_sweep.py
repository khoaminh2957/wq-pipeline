#!/usr/bin/env python3
"""[24] F1 re-tune sweep: same formula + LOCKED region/universe/delay, vary neut/decay/trunc.
Re-sims each grid variant, pulls IS metrics + sub-universe Sharpe, ranks by fitness. Picks the
best-tuned settings. Reads state/retune_grid.json -> state/retune_results.json."""
import json, time, socket, threading, pickle
from pathlib import Path
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
import requests
socket.setdefaulttimeout(35)
H="https://api.worldquantbrain.com"; ST=Path("/Users/kanenguyen/wq_pipeline/state")
gate=threading.Lock(); lock=threading.Lock(); last=[0.0]
s=requests.Session(); s.headers.update({"Connection":"close"}); s.cookies.update(pickle.load(open(ST/"wq_cookies.pkl","rb")))
def gpost(u,**k):
    with gate:
        dt=time.time()-last[0]
        if dt<0.6: time.sleep(0.6-dt)
        last[0]=time.time(); return s.post(u,**k)
grid=json.load(open(ST/"retune_grid.json"))
import os
res=json.load(open(ST/"retune_results.json")) if os.path.exists(ST/"retune_results.json") else {}  # RESUMABLE
done=[len(res)]
def status(**k): json.dump(k, open(ST/"retune_status.json","w"))
def sim_and_metrics(g):
    body={"type":"REGULAR","settings":{"instrumentType":"EQUITY","region":g["region"],"universe":g["universe"],
          "delay":0,"decay":int(g["decay"]),"neutralization":g["neut"],"truncation":float(g["trunc"]),
          "pasteurization":"ON","unitHandling":"VERIFY","nanHandling":"ON","language":"FASTEXPR",
          "visualization":False,"testPeriod":"P0Y0M"},"regular":g["formula"]}
    r=None
    for _ in range(40):
        try:r=gpost(H+"/simulations",json=body,timeout=35)
        except Exception:time.sleep(5);continue
        if r.status_code==429:time.sleep(float(r.headers.get("Retry-After",8) or 8));continue
        break
    if r is None or r.status_code not in(200,201):return None
    loc=r.headers.get("Location");url=urljoin(H,loc) if loc and loc.startswith("/") else loc
    aid=None
    for _ in range(200):
        try:g2=s.get(url,timeout=35)
        except Exception:time.sleep(4);continue
        try:j=g2.json()
        except:j={}
        st=(j.get("status") or "").upper()
        if j.get("alpha") or st in("COMPLETE","WARNING","ERROR","FAIL"):aid=j.get("alpha");break
        time.sleep(float(g2.headers.get("Retry-After") or 3))
    if not aid:return None
    try:
        a=s.get(f"{H}/alphas/{aid}",timeout=35).json(); iss=a.get("is") or {}
        su=next((c for c in (iss.get("checks") or []) if c.get("name")=="LOW_SUB_UNIVERSE_SHARPE"),{})
        return {"alpha":aid,"sharpe":iss.get("sharpe"),"fitness":iss.get("fitness"),"turnover":iss.get("turnover"),
                "returns":iss.get("returns"),"subuniv":su.get("value"),
                "pass":sum(1 for c in (iss.get("checks") or []) if (c.get("result") or "").upper()=="PASS")}
    except:return None
def work(g):
    if g['id'] in res: return  # skip done (resumable)
    m=sim_and_metrics(g)
    with lock:
        if m: res[g["id"]]={**g,**m}; json.dump(res,open(ST/"retune_results.json","w"))
        done[0]+=1; status(stage="sweep",done=done[0],n=len(grid))
status(stage="start",n=len(grid))
with ThreadPoolExecutor(max_workers=3) as ex: list(ex.map(work,grid))
status(stage="DONE",done=done[0],n=len(grid),got=len(res))
print("DONE",len(res))
