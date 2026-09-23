#!/usr/bin/env python3
"""ab_analyze.py — compare control vs treatment alpha quality from sim results, per round + overall.
Effectiveness metrics (higher = better generation): mean |sharpe| (signal strength, sign-agnostic —
both groups face the same flip-once rule), mean fitness, mean gates-passed (hard gates), and counts
of |sharpe|>=1.0 and zero-fail. Reports per-round winner (mean |sharpe|) so we see if the effect is
CONSISTENT across the 5 rounds. Usage: python3 tools/ab_analyze.py"""
import json, collections, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
# Gate set: ONE definition, tools/funnel/gates.py. This literal was copied here and in
# four other files; the copies disagreed (this one had IS_LADDER_SHARPE, which GLB does not even have), so the same journal
# scored to different zero-fail counts depending on which file did the scoring.
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent / "tools" / "funnel"))
from gates import BLOCKING as HARD
rows = {}
for line in open(ROOT / "state/resim_results.jsonl"):
    try: r = json.loads(line)
    except: continue
    oid = r.get("old_id","")
    if oid.startswith("ab_") and r.get("status") == "COMPLETE": rows[oid] = r
# credit both groups for exact-duplicate alphas (treatment reproduced control): copy kept result
try:
    dupmap = json.load(open(ROOT / "state/funnel/ab_dupmap.json"))
    for dropped, kept in dupmap.items():
        if kept in rows and dropped not in rows: rows[dropped] = rows[kept]
except FileNotFoundError:
    pass

def parse(oid):
    m = oid.split("_"); return ("control" if m[1]=="c" else "treatment"), int(m[2][1:])

def gates_passed(r):
    ch = r.get("checks") or []
    return sum(1 for c in ch if c.get("name") in HARD and c.get("result") in ("PASS","WARNING"))

data = collections.defaultdict(list)
for oid, r in rows.items():
    g, rd = parse(oid)
    sh = r.get("sharpe") or 0; fit = r.get("fitness") or 0
    nofail = not any(c.get("result")=="FAIL" for c in (r.get("checks") or []))
    data[(g,rd)].append({"sh":sh,"absh":abs(sh),"fit":fit,"gp":gates_passed(r),"zf":nofail})

def agg(items):
    n=len(items) or 1
    return dict(n=len(items),
        mean_absh=round(sum(x["absh"] for x in items)/n,3),
        mean_sh=round(sum(x["sh"] for x in items)/n,3),
        mean_fit=round(sum(x["fit"] for x in items)/n,3),
        mean_gp=round(sum(x["gp"] for x in items)/n,2),
        n_sh1=sum(x["absh"]>=1.0 for x in items),
        n_zf=sum(x["zf"] for x in items))

print(f"{'round':7}{'group':11}{'n':4}{'mean|sh|':10}{'meanFit':9}{'gatesP':8}{'|sh|>=1':8}{'zeroFail':9}")
wins={"control":0,"treatment":0,"tie":0}
for rd in range(1,6):
    a={g:agg(data.get((g,rd),[])) for g in ("control","treatment")}
    for g in ("control","treatment"):
        s=a[g]; print(f"{rd:<7}{g:11}{s['n']:<4}{s['mean_absh']:<10}{s['mean_fit']:<9}{s['mean_gp']:<8}{s['n_sh1']:<8}{s['n_zf']:<9}")
    c,t=a["control"]["mean_absh"],a["treatment"]["mean_absh"]
    w="treatment" if t>c else "control" if c>t else "tie"; wins[w]+=1
    print(f"       -> round {rd} winner (mean|sh|): {w}")
allc=[x for (g,_),it in data.items() if g=="control" for x in it]
allt=[x for (g,_),it in data.items() if g=="treatment" for x in it]
print("\n=== AGGREGATE ===")
for g,items in (("control",allc),("treatment",allt)):
    s=agg(items); print(f"  {g:11} {s}")
print(f"\nper-round wins on mean|sharpe|: {wins}")
ac,at=agg(allc)["mean_absh"],agg(allt)["mean_absh"]
lift = round((at-ac)/ac*100,1) if ac else None
print(f"treatment mean|sharpe| lift over control: {lift}%")
