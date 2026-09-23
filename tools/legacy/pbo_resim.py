#!/usr/bin/env python3
"""Auth (persona) -> re-simulate a cohort of formulas -> pull each alpha's IS PnL.
Sequential (slot/rate safe). Saves PnL incrementally + raw dumps for format-debug."""
import json, time, socket
from pathlib import Path
from urllib.parse import urljoin
import requests
socket.setdefaulttimeout(35)
H="https://api.worldquantbrain.com"; OUT=Path("/tmp/harness")
def status(**k): json.dump(k, open(OUT/"pbo_status.json","w"))
d=dict(l.split("=",1) for l in (Path.home()/".wqbrain_creds").read_text().strip().split("\n") if "=" in l)
s=requests.Session(); s.auth=(d["email"], d["password"]); s.headers.update({"Connection":"close"})

# ---- persona auth ----
status(stage="auth")
r=s.post(H+"/authentication", timeout=30)
authed = r.status_code in (200,201)
if not authed and r.status_code==401 and r.headers.get("WWW-Authenticate")=="persona":
    bio=urljoin(r.url, r.headers.get("Location",""))
    (OUT/"persona_url.txt").write_text(bio); status(stage="await_biometric", persona=bio)
    for _ in range(150):              # ~12.5 min window
        time.sleep(5)
        try: rr=s.post(bio, timeout=30)
        except Exception: continue
        if rr.status_code in (200,201): authed=True; break
if not authed:
    status(stage="AUTH_FAIL", code=r.status_code, body=r.text[:200]); raise SystemExit
status(stage="authed")

specs=json.load(open(OUT/"pbo_specs.json"))
def simulate(spec, dbg=False):
    body={"type":"REGULAR","settings":dict(spec["settings"], nanHandling="ON"),"regular":spec["formula"]}
    r=s.post(H+"/simulations", json=body, timeout=35)
    if dbg: open(OUT/"pbo_first_sim.json","w").write(f"POST {r.status_code}\nHDRS {dict(r.headers)}\nBODY {r.text[:500]}")
    if r.status_code not in (200,201): return None,{"err":r.status_code,"body":r.text[:300]}
    loc=r.headers.get("Location")
    if not loc: return None,{"err":"no_location","body":r.text[:300]}
    url=urljoin(H, loc) if loc.startswith("/") else loc
    for _ in range(150):
        g=s.get(url, timeout=35); ra=g.headers.get("Retry-After")
        try: j=g.json()
        except Exception: j={}
        if dbg and _==0: open(OUT/"pbo_first_poll.json","w").write(f"{g.status_code}\nRA={ra}\n{g.text[:800]}")
        st=(j.get("status") or "").upper()
        if j.get("alpha") or st in ("COMPLETE","WARNING","ERROR","FAIL"):
            return j.get("alpha"), j
        if g.status_code>=400: return None,{"err":g.status_code,"body":g.text[:300]}
        time.sleep(float(ra) if ra else 3)
    return None,{"err":"sim_timeout"}
def get_pnl(aid, dbg=False):
    g=s.get(f"{H}/alphas/{aid}/recordsets/pnl", timeout=35)
    if dbg: open(OUT/"pbo_first_pnl.json","w").write(f"{g.status_code}\n{g.text[:800]}")
    if g.status_code!=200: return None,{"err":g.status_code,"body":g.text[:200]}
    try: return g.json(),None
    except Exception as e: return None,{"err":str(e)}

pnls={}; log=[]
for i,spec in enumerate(specs):
    status(stage="sim", i=i+1, n=len(specs), got=len(pnls), src=spec["alpha_id_src"])
    aid,meta=simulate(spec, dbg=(i==0))
    if not aid: log.append({"src":spec["alpha_id_src"],"sim_fail":meta}); json.dump(log,open(OUT/"pbo_log.json","w")); continue
    pj,perr=get_pnl(aid, dbg=(len(pnls)==0))
    if pj is None: log.append({"src":spec["alpha_id_src"],"alpha":aid,"pnl_fail":perr}); json.dump(log,open(OUT/"pbo_log.json","w")); continue
    pnls[spec["alpha_id_src"]]={"alpha":aid,"pnl":pj}
    json.dump(pnls, open(OUT/"pbo_pnl.json","w"))           # incremental
    log.append({"src":spec["alpha_id_src"],"alpha":aid,"ok":True}); json.dump(log,open(OUT/"pbo_log.json","w"))
    time.sleep(1.0)
status(stage="DONE", got=len(pnls), total=len(specs))
