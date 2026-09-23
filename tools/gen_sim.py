#!/usr/bin/env python3
"""Simulate session-generated formulas: sim -> metrics + warnings + PnL.
Reads state/gen_shortlist.json -> state/gen_results.json (resumable)."""
import json, time, socket, threading, pickle, os
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
grid=json.load(open(ST/"gen_shortlist.json"))
res=json.load(open(ST/"gen_results.json")) if os.path.exists(ST/"gen_results.json") else {}
def status(**k): json.dump(k, open(ST/"gen_status.json","w"))
def pnl_of(aid):
    for _ in range(10):
        g=s.get(f"{H}/alphas/{aid}/recordsets/pnl",timeout=35)
        if g.status_code==200 and (g.text or '').strip():
            j=g.json(); recs=j.get("records") if isinstance(j,dict) else j
            if recs:
                out=[]
                for r in recs:
                    if isinstance(r,(list,tuple)):
                        v=next((x for x in r[1:] if isinstance(x,(int,float))),None); out.append((str(r[0]),float(v) if v is not None else 0))
                return out
        time.sleep(4)
    return []
def sim(g):
    body={"type":"REGULAR","settings":{"instrumentType":"EQUITY","region":g["region"],"universe":g["universe"],
          "delay":int(g.get("sim_delay",0)),"decay":int(g["decay"]),"neutralization":g["neut"],"truncation":float(g["trunc"]),
          "pasteurization":"ON","unitHandling":"VERIFY","nanHandling":"ON","language":"FASTEXPR",
          "visualization":False,"testPeriod":"P0Y0M"},"regular":g["formula"]}
    r=None
    for _ in range(40):
        try:r=gpost(H+"/simulations",json=body,timeout=35)
        except Exception:time.sleep(5);continue
        if r.status_code==429:time.sleep(float(r.headers.get("Retry-After",8) or 8));continue
        break
    if r is None or r.status_code not in(200,201):
        return {"err":f"sim_post {None if r is None else r.status_code}"}
    loc=r.headers.get("Location"); url=urljoin(H,loc) if loc and loc.startswith("/") else loc
    aid=None; detail=None
    for _ in range(200):
        try:g2=s.get(url,timeout=35)
        except Exception:time.sleep(4);continue
        try:j=g2.json()
        except:j={}
        st=(j.get("status") or "").upper()
        if j.get("alpha") or st in("COMPLETE","WARNING","ERROR","FAIL"):
            aid=j.get("alpha"); detail=(j.get("message") or st); break
        time.sleep(float(g2.headers.get("Retry-After") or 3))
    if not aid: return {"err":f"no_alpha:{detail}"}
    try:
        a=s.get(f"{H}/alphas/{aid}",timeout=35).json(); iss=a.get("is") or {}
        ch=iss.get("checks") or []
        su=next((c for c in ch if c.get("name")=="LOW_SUB_UNIVERSE_SHARPE"),{})
        warn=[c.get("name") for c in ch if (c.get("result") or "").upper()=="WARNING"]
        return {"alpha":aid,"sharpe":iss.get("sharpe"),"fitness":iss.get("fitness"),"turnover":iss.get("turnover"),
                "returns":iss.get("returns"),"subuniv":su.get("value"),"warnings":warn,
                "pass":sum(1 for c in ch if (c.get("result") or "").upper()=="PASS"),"pnl":pnl_of(aid)}
    except Exception as e: return {"err":f"metrics:{e}"}
def work(g):
    if g["id"] in res: return
    m=sim(g)
    with lock:
        res[g["id"]]={**{k:g[k] for k in ("id","theme","formula","neut","decay")},**m}
        json.dump(res, open(ST/"gen_results.json","w"))
        status(stage="sim", done=len(res), n=len(grid))
status(stage="start", n=len(grid))
with ThreadPoolExecutor(max_workers=3) as ex: list(ex.map(work, grid))
status(stage="DONE", done=len(res), n=len(grid))
print("DONE", len(res))
