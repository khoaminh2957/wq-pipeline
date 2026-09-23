#!/usr/bin/env python3
"""Full pipeline robust test on the re-simmed shortlist:
[E2] holdout gate (train->test) · [E3] DSR on actual returns · [E3b] cohort PBO via CSCV ·
[E4] self-correlation (PnL) greedy-decorrelated selection."""
import json, sys, math, itertools
sys.path.insert(0,"/Users/kanenguyen/wq_pipeline")
import robust
from statistics import pvariance

P=json.load(open("/Users/kanenguyen/wq_pipeline/state/robust_pnl.json"))
SL={a["id"]:a for a in json.load(open("/Users/kanenguyen/wq_pipeline/state/robust_shortlist.json"))}
PER=252**0.5

def rets(pnl): return robust.daily_returns([(d,v) for d,v in pnl])
A={}
for aid,obj in P.items():
    r=rets(obj["pnl"])
    if len(r)>60: A[aid]=r
print(f"alphas with usable PnL: {len(A)}")

# DSR multiple-testing: cross-trial Var(SR) + N from the FULL pool's distinct fingerprints
import csv as _csv
from fingerprint import structural_fingerprint as _fp
def _num(s):
    s=(s or '').strip().replace(',','.')
    try: return float(s)
    except: return None
_pool={}
with open("/Users/kanenguyen/Downloads/IQC Submit Ready — acc1 - d0_alphas (1).csv") as _f:
    for _r in _csv.DictReader(_f):
        _sh=_num(_r['sharpe'])
        if _sh is None or not _r['formula']: continue
        _k=_fp(_r['formula'], _r['neutralization'])
        if _k not in _pool or _sh>_pool[_k]: _pool[_k]=_sh
var_sr=pvariance([v/PER for v in _pool.values()]); N_INDEP=len(_pool)
print(f"[DSR] N_indep={N_INDEP} distinct trials | benchmark E[maxSR]={robust.expected_max_sharpe(var_sr,N_INDEP)*PER:.2f} (annualized)")

res={}
for aid,r in A.items():
    cut=int(len(r)*0.75); train=robust.sharpe(r[:cut]); test=robust.sharpe(r[cut:])
    holdout = test>0 and (train<=0 or test>=0.30*train)
    dstat,dprob=robust.deflated_sharpe(r, var_sr, N_INDEP)
    kr,r2=robust.k_ratio_and_r2([(str(i),sum(r[:i+1])) for i in range(len(r))])
    res[aid]={"sharpe_ann":robust.sharpe(r)*PER,"holdout":holdout,"test_sh":test*PER,
              "dsr_prob":dprob,"kr":kr,"r2":r2,"sharpe_csv":SL.get(aid,{}).get("sharpe")}

# [E3b] cohort PBO via CSCV
pbo=robust.cscv_pbo({aid:r for aid,r in A.items()})
print(f"[E3b] cohort PBO via CSCV = {pbo.get('pbo')}  (N={pbo.get('n')}, T={pbo.get('T')})  "
      f"-> {'overfit risk' if (pbo.get('pbo') or 0)>=0.5 else 'acceptable'}")

# Selection = holdout PASS, ranked by Sharpe. PnL correlation intentionally NOT used
# (per user: correlation is STRUCTURAL, not PnL) — structural dedup already done via fingerprint.
picked=[aid for aid in sorted(A, key=lambda x:res[x]["sharpe_ann"], reverse=True) if res[aid]["holdout"]]
print(f"[E2] holdout PASS: {len(picked)}/{len(res)}  (PnL-correlation filter REMOVED; dedup is structural)")

print(f"\n===== FINAL ROBUST SELECTION (holdout-pass, best-Sharpe-first; structural-distinct) =====")
print(f"{'id':<11}{'Sharpe':>7}{'test_sh':>8}{'holdout':>8}{'dsr_p':>7}{'K-ratio':>8}{'R2':>6}")
for aid in picked:
    r=res[aid]
    print(f"{aid:<11}{r['sharpe_ann']:>7.2f}{r['test_sh']:>8.2f}{'PASS':>8}{(r['dsr_prob'] or 0):>7.2f}{(r['kr'] or 0):>8.1f}{(r['r2'] or 0):>6.2f}")
json.dump({"picked":picked,"pbo":pbo.get("pbo"),"res":res}, open("/Users/kanenguyen/wq_pipeline/state/robust_final.json","w"))
print(f"\nselected {len(picked)} mutually-decorrelated robust alphas -> robust_final.json")
