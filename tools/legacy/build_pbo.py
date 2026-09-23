#!/usr/bin/env python3
"""CSCV -> PBO from collected per-alpha IS PnL (pbo_pnl.json).
Robust to WQ recordset format. Reports PBO + lambda distribution."""
import json, math, itertools, sys
from pathlib import Path
OUT=Path("/tmp/harness")
D=json.load(open(OUT/"pbo_pnl.json"))
print(f"alphas with PnL: {len(D)}")

def extract(pj):
    """return list of (date_str, cumulative_value)"""
    recs = pj.get("records") if isinstance(pj,dict) else pj
    if not recs: return []
    out=[]
    # detect schema column order
    props=[]
    if isinstance(pj,dict) and isinstance(pj.get("schema"),dict):
        props=[p.get("name") for p in pj["schema"].get("properties",[])]
    for r in recs:
        if isinstance(r,(list,tuple)):
            date=r[0]; val=None
            for v in r[1:]:
                if isinstance(v,(int,float)): val=v; break
            out.append((str(date), float(val) if val is not None else 0.0))
        elif isinstance(r,dict):
            date=r.get("date") or r.get("Date")
            val=next((r[k] for k in r if k!="date" and isinstance(r[k],(int,float))), 0.0)
            out.append((str(date), float(val)))
    return out

series={}
for sid,obj in D.items():
    s=extract(obj["pnl"])
    if len(s)>50: series[sid]=dict(s)
print(f"usable series (>50 pts): {len(series)}")
if len(series)<6:
    print("Not enough series for CSCV (need >=6, ideally >=10). Got",len(series)); sys.exit(0)

# common dates
common=set.intersection(*[set(v.keys()) for v in series.values()])
dates=sorted(common)
print(f"common dates T = {len(dates)}")
ids=sorted(series.keys())
# cumulative -> daily returns (diff)
import statistics as st
R={}  # id -> list of daily diffs aligned to dates[1:]
cum={sid:[series[sid][d] for d in dates] for sid in ids}
for sid in ids:
    c=cum[sid]; R[sid]=[c[t]-c[t-1] for t in range(1,len(c))]
T=len(dates)-1
def sharpe(xs):
    if len(xs)<2: return float('-inf')
    m=sum(xs)/len(xs); v=sum((x-m)**2 for x in xs)/(len(xs)-1)
    sd=math.sqrt(v)
    return (m/sd) if sd>1e-12 else (float('inf') if m>0 else (float('-inf') if m<0 else 0.0))

# CSCV
S=16
while S>4 and T//S < 20: S-=2     # ensure blocks have >=~20 obs
blocks=[list(range(i*T//S,(i+1)*T//S)) for i in range(S)]
combos=list(itertools.combinations(range(S), S//2))
print(f"CSCV: S={S} blocks (~{T//S} obs each), {len(combos)} combinations")
N=len(ids)
lambdas=[]; below=0
for c in combos:
    isb=set(c); IS=[i for b in c for i in blocks[b]]
    OOS=[i for b in range(S) if b not in isb for i in blocks[b]]
    is_sh={sid:sharpe([R[sid][t] for t in IS]) for sid in ids}
    nstar=max(ids, key=lambda sid: is_sh[sid])
    oos_sh={sid:sharpe([R[sid][t] for t in OOS]) for sid in ids}
    # relative rank of n* among OOS (1=best ... 0=worst)
    order=sorted(ids, key=lambda sid: oos_sh[sid])   # ascending
    rank=order.index(nstar)                           # 0..N-1
    w=(rank+0.5)/N
    w=min(max(w,1e-6),1-1e-6)
    lam=math.log(w/(1-w)); lambdas.append(lam)
    if lam<0: below+=1
PBO=below/len(combos)
lambdas.sort()
import statistics as st
print("\n================ RESULT ================")
print(f"PBO = {PBO:.3f}   ({below}/{len(combos)} combinations where IS-best fell below OOS median)")
print(f"lambda: mean={sum(lambdas)/len(lambdas):.2f}  median={lambdas[len(lambdas)//2]:.2f}  min={lambdas[0]:.2f} max={lambdas[-1]:.2f}")
def interp(p):
    if p<0.1: return "RAT THAP -> chon lua robust, IS-best dang tin OOS"
    if p<0.25: return "THAP -> chap nhan duoc"
    if p<0.5: return "TRUNG BINH-CAO -> co dau hieu overfit selection"
    return "CAO (>=0.5) -> selection overfit nang, IS-best ~ tung dong xu OOS"
print("Doc:", interp(PBO))
json.dump({"PBO":PBO,"N":N,"T":T,"S":S,"combos":len(combos),"below":below}, open(OUT/"pbo_result.json","w"))
