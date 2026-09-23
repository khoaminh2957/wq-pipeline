#!/usr/bin/env python3
"""frontier_analyze.py — map the carrier x orthogonalization frontier from sim results, then MEASURE
prod-corr on the sharpe>=THRESH cells to find a SUBMITTABLE point (sharpe>=1.58 AND prod-corr<0.7).
Usage: python3 tools/frontier_analyze.py"""
import json, subprocess, sys, pathlib, collections
ROOT = pathlib.Path(__file__).resolve().parent.parent
THRESH = 1.4   # measure prod-corr on anything near/over the sharpe bar
PREFIX = sys.argv[1] if len(sys.argv) > 1 else "fr_"

rows = {}
for line in open(ROOT / "state/resim_results.jsonl"):
    try: r = json.loads(line)
    except: continue
    o = r.get("old_id","")
    if o.startswith(PREFIX) and r.get("status") == "COMPLETE": rows[o] = r

def tag(o):                       # fr_<carrier>_<orth>_d<decay>_<idx>
    p = o.split("_"); return p[1], p[2], p[3]

# best sharpe per (carrier, orth), keep the alpha id + whether zero-fail
grid = collections.defaultdict(lambda: {"best": -9, "aid": None, "oid": None, "zf": False, "fit": None})
for o, r in rows.items():
    c, orth, dec = tag(o)
    sh = r.get("sharpe") or -9
    zf = not any(ch.get("result")=="FAIL" for ch in (r.get("checks") or []))
    g = grid[(c, orth)]
    if sh > g["best"]:
        g.update(best=sh, aid=r.get("alpha"), oid=o, zf=zf, fit=r.get("fitness"))

CARR = ["full","light","min","none"]; ORTH = ["o0","o1","o2","o3"]
print("BEST SHARPE grid (rows=carrier, cols=orth level 0..3 factors stripped):")
print(f"{'carrier':8}" + "".join(f"{o:>10}" for o in ORTH))
for c in CARR:
    print(f"{c:8}" + "".join(f"{grid[(c,o)]['best']:>10.2f}" for o in ORTH))

# measure prod-corr on cells with best sharpe >= THRESH
cands = [(c,o,grid[(c,o)]) for c in CARR for o in ORTH if grid[(c,o)]["best"] >= THRESH and grid[(c,o)]["aid"]]
print(f"\ncells with sharpe>={THRESH}: {len(cands)} — measuring prod-corr...")
if cands:
    aids = [g["aid"] for _,_,g in cands]
    subprocess.run([sys.executable, str(ROOT/"tools/fetch_prod_corr.py"), *aids], capture_output=True)
    m = json.load(open(ROOT/"state/prod_corr_measured.json"))
    print(f"\n{'carrier':8}{'orth':6}{'sharpe':8}{'fit':7}{'zeroFail':9}{'prodCorr':9}{'breach>0.7':11}{'SUBMITTABLE':12}")
    for c,o,g in sorted(cands, key=lambda x:-x[2]['best']):
        pc = m.get(g["aid"], {})
        prod, breach = pc.get("prod_maxcorr"), pc.get("prod_breach_count")
        sub = (g["best"]>=1.58 and g["zf"] and breach==0)
        print(f"{c:8}{o:6}{g['best']:<8.2f}{str(g['fit']):7}{str(g['zf']):9}{str(prod):9}{str(breach):11}{'YES ***' if sub else 'no':12}")
