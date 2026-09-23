#!/usr/bin/env python3
"""check_zerofail.py — scan resim_results.jsonl for rows whose old_id starts with PREFIX and report
which gates FAIL per alpha. A candidate = COMPLETE with NO 'FAIL' check (correlation gates may be
PENDING -> confirm separately with fetch_prod_corr.py). Prints candidates first, then a fail-gate
histogram so we learn which gate is the binding one for the drive book under TOP1000/USA/d1.
Usage: python3 tools/check_zerofail.py drv_ [state/funnel/drive_b1.json]"""
import json, sys, collections, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
prefix = sys.argv[1] if len(sys.argv) > 1 else "drv_"
scope = None
if len(sys.argv) > 2:
    scope = {r["old_id"] for r in json.load(open(sys.argv[2]))}

rows = {}
for line in open(ROOT / "state/resim_results.jsonl"):
    try: r = json.loads(line)
    except: continue
    oid = r.get("old_id", "")
    if not oid.startswith(prefix): continue
    if scope and oid not in scope: continue
    rows[oid] = r                                   # keep last

cand, failhist = [], collections.Counter()
for oid, r in rows.items():
    if r.get("status") != "COMPLETE": continue
    fails = [c["name"] for c in (r.get("checks") or []) if c.get("result") == "FAIL"]
    pend  = [c["name"] for c in (r.get("checks") or []) if c.get("result") == "PENDING"]
    for f in fails: failhist[f] += 1
    if not fails:
        cand.append((oid, r.get("alpha"), r.get("sharpe"), r.get("fitness"), r.get("turnover"), pend))

print(f"scanned {len(rows)} '{prefix}' rows; {sum(1 for r in rows.values() if r.get('status')=='COMPLETE')} COMPLETE")
print(f"\nCANDIDATES (no FAIL check; confirm PENDING corr): {len(cand)}")
for oid, aid, sh, fit, to, pend in sorted(cand, key=lambda x: -(x[2] or -9)):
    print(f"  {oid}  {aid}  sh={sh} fit={fit} turn={round(to or 0,3)}  pending={pend}")
print("\nFAIL-gate histogram (binding gates for this book @ TOP1000):")
for g, c in failhist.most_common():
    print(f"  {c:4}  {g}")
