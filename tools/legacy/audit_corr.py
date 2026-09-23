#!/usr/bin/env python3
"""Hallucination check on the cohort: pairwise daily-return correlation + Sharpe spread.
If variants are near-duplicates (corr>=0.9), PBO/robust-ranking are noise (not informative)."""
import json,math,itertools
from pathlib import Path
D=json.load(open("/tmp/harness/pbo_pnl.json"))
def extract(pj):
    recs=pj.get("records") if isinstance(pj,dict) else pj; out=[]
    for r in recs:
        if isinstance(r,(list,tuple)):
            v=next((x for x in r[1:] if isinstance(x,(int,float))),None); out.append((str(r[0]),float(v) if v is not None else 0.0))
    return out
ser={s:dict(extract(o["pnl"])) for s,o in D.items() if len(extract(o["pnl"]))>50}
common=sorted(set.intersection(*[set(v) for v in ser.values()])) if ser else []
ids=sorted(ser)
cum={s:[ser[s][d] for d in common] for s in ids}
ret={s:[cum[s][t]-cum[s][t-1] for t in range(1,len(common))] for s in ids}
def corr(a,b):
    n=len(a); ma=sum(a)/n; mb=sum(b)/n
    va=sum((x-ma)**2 for x in a); vb=sum((x-mb)**2 for x in b)
    return sum((a[i]-ma)*(b[i]-mb) for i in range(n))/math.sqrt(va*vb) if va>0 and vb>0 else 1.0
cs=sorted(corr(ret[a],ret[b]) for a,b in itertools.combinations(ids,2))
print(f"\n=== HALLUCINATION CHECK: cohort homogeneity ({len(ids)} variants, {len(cs)} pairs) ===")
if cs:
    print(f"pairwise daily-return corr: min={cs[0]:.3f} median={cs[len(cs)//2]:.3f} max={cs[-1]:.3f} mean={sum(cs)/len(cs):.3f}")
    print(f"pairs corr>=0.9: {sum(1 for c in cs if c>=0.9)}/{len(cs)} | >=0.7: {sum(1 for c in cs if c>=0.7)}/{len(cs)} | <0.5: {sum(1 for c in cs if c<0.5)}/{len(cs)}")
    med=cs[len(cs)//2]
    verdict=("NEAR-DUPLICATE -> PBO/ranking la NHIEU, vo nghia" if med>=0.85 else
             "KHA TUONG QUAN -> phan biet han che" if med>=0.6 else
             "DA DANG THAT -> PBO/ranking CO Y NGHIA phan biet")
    print("VERDICT:",verdict)
def sh(xs): m=sum(xs)/len(xs); sd=math.sqrt(sum((x-m)**2 for x in xs)/(len(xs)-1)); return m/sd if sd>0 else 0
shs=sorted(sh(ret[s]) for s in ids)
print(f"daily-Sharpe spread: {shs[0]:.3f}..{shs[-1]:.3f} (annualized {shs[0]*15.87:.2f}..{shs[-1]*15.87:.2f})")
json.dump({"variants":len(ids),"corr_median":cs[len(cs)//2] if cs else None,"corr_max":cs[-1] if cs else None}, open("/tmp/harness/corr_audit.json","w"))
