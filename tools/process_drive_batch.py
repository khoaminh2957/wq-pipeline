#!/usr/bin/env python3
"""process_drive_batch.py — one-shot batch processor for the drive grind. Scans a batch's results
for no-FAIL candidates, then MEASURES prod+self correlation on each (the only remaining gate). Prints
a TRUE-PASS verdict iff a candidate has prod-corr<0.7 AND self-corr<0.7. Usage:
python3 tools/process_drive_batch.py state/funnel/drive_b6.json"""
import json, sys, subprocess, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
batchfile = sys.argv[1]
scope = {r["old_id"]: r["formula"].strip() for r in json.load(open(batchfile))}

rows = {}
for line in open(ROOT / "state/resim_results.jsonl"):
    try: r = json.loads(line)
    except: continue
    if r.get("old_id") in scope: rows[r["old_id"]] = r

cand = []
for oid, r in rows.items():
    if r.get("status") != "COMPLETE": continue
    if any(c.get("result") == "FAIL" for c in (r.get("checks") or [])): continue
    cand.append((oid, r.get("alpha"), r.get("sharpe"), r.get("fitness")))

print(f"{batchfile}: {len(rows)} completed, {len(cand)} no-FAIL candidates")
if not cand:
    print("VERDICT: no candidates this batch"); sys.exit(0)

aids = [c[1] for c in cand]
out = subprocess.run([sys.executable, str(ROOT / "tools/fetch_prod_corr.py"), *aids],
                     capture_output=True, text=True)
print(out.stdout[-1500:])
measured = json.load(open(ROOT / "state/prod_corr_measured.json"))
passes = []
for oid, aid, sh, fit in cand:
    m = measured.get(aid, {})
    pc, sc = m.get("prod_maxcorr"), m.get("self_maxcorr")
    # require self actually MEASURED (B10 O6) — an empty/failed self fetch is not a clean self<0.7.
    if pc is not None and pc < 0.7 and m.get("self_measured") and (sc is None or sc < 0.7):
        passes.append((oid, aid, sh, fit, pc, sc))
if passes:
    print("\n*** TRUE ZERO-FAIL PASS FOUND ***")
    for oid, aid, sh, fit, pc, sc in passes:
        print(f"  {oid} {aid} sh={sh} fit={fit} prodCorr={pc} selfCorr={sc}")
        print(f"  formula: {scope[oid]}")
else:
    print("\nVERDICT: no true pass (all candidates fail prod/self corr)")
