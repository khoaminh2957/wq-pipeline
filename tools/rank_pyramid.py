#!/usr/bin/env python3
"""Rank the pyramid resim results: quality score, submittable-tier flag, group by pyramid cell.
'checks' in resim_results.jsonl = the checks that PASSED (engine filters result=='PASS')."""
import json
from collections import defaultdict

# checks that matter for real submittability (WQ core). MATCHES_PYRAMID = qualifies for bonus.
# Gate set: ONE definition, tools/funnel/gates.py. This literal was copied here and in
# four other files; the copies disagreed (this one had only 5 gates, dropping LOW_SHARPE and LOW_2Y_SHARPE), so the same journal
# scored to different zero-fail counts depending on which file did the scoring.
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent / "tools" / "funnel"))
from gates import BLOCKING as CORE
rows = [json.loads(l) for l in open("state/resim_results.jsonl") if l.strip()]
pyr = [j for j in rows if str(j.get("old_id", "")).startswith("pyr_") and j.get("alpha")]

def cell(oid):
    # pyr_<COMBO>_<dataset>...  or pyr_fhp_...
    p = oid.split("_")
    if p[1] == "fhp":
        return "CHN_d1 · fund_holdings_panel (×2.0 institutions)"
    combo = "_".join(p[1:4])         # CHN_TOP2000U_d0
    ds = p[4] if len(p) > 4 else "?"
    return f"{combo} · {ds}"

for j in pyr:
    ck = set(j.get("checks") or [])
    j["_npass"] = len(ck)
    j["_core"] = len(CORE & ck)
    j["_pyr"] = "MATCHES_PYRAMID" in ck
    j["_score"] = (j.get("fitness") or 0) * 0.6 + (j.get("sharpe") or 0) * 0.4

pyr.sort(key=lambda j: (-j["_core"], -(j.get("fitness") or 0), -(j.get("sharpe") or 0)))

print(f"=== {len(pyr)} pyramid alpha OK · tất cả MATCHES_PYRAMID={sum(j['_pyr'] for j in pyr)}/{len(pyr)} ===\n")
print("TOP 15 theo (core-checks, fitness, sharpe):")
print(f"{'sid':<9}{'core':>5}{'chk':>4}{'sh':>6}{'fit':>6}{'to':>7}  cell")
for j in pyr[:15]:
    print(f"{j['alpha']:<9}{j['_core']:>4}/{len(CORE)}{j['_npass']:>4}{j.get('sharpe',0):>6.2f}"
          f"{j.get('fitness',0):>6.2f}{j.get('turnover',0):>7.3f}  {cell(j['old_id'])}")

# submittable-tier: pass toàn bộ 5 core + fitness>=1
# `_core == 5` was correct when CORE was a hand-copied 5-gate literal. Line 13 later replaced it
# with `from gates import BLOCKING as CORE` — 11 gates — and this equality test was not updated,
# so an alpha passing 6, 7 or 8 blocking gates was EXCLUDED from the submittable tier while one
# passing exactly 5 was included. The tier-A count that gets read as the submit shortlist has been
# 0. An equality test against a count whose scale can change is the defect; use the verdict.
strong = [j for j in pyr if j["_core"] >= 5 and (j.get("fitness") or 0) >= 1.0]
good = [j for j in pyr if j["_core"] >= 4 and (j.get("sharpe") or 0) >= 1.25 and j not in strong]
print(f"\nHẠNG A (≥5 core + fitness≥1): {len(strong)}  -> {[j['alpha'] for j in strong]}")
print(f"HẠNG B (≥4 core + sharpe≥1.25): {len(good)}")

# theo cell: cell nào nhiều con tốt nhất
bycell = defaultdict(list)
for j in pyr:
    bycell[cell(j["old_id"])].append(j)
print("\nTheo pyramid cell (n_ok · best-sharpe · best-fit):")
for c, js in sorted(bycell.items(), key=lambda kv: -max((x.get("sharpe") or 0) for x in kv[1])):
    bs = max(js, key=lambda x: x.get("sharpe") or 0)
    print(f"  {len(js):>2} · sh {bs.get('sharpe',0):>4.2f} · fit {bs.get('fitness',0):>4.2f}  {c}")

json.dump([{"sid": j["alpha"], "old_id": j["old_id"], "sharpe": j.get("sharpe"),
            "fitness": j.get("fitness"), "turnover": j.get("turnover"),
            "core": j["_core"], "checks_pass": j["_npass"], "cell": cell(j["old_id"])}
           for j in pyr], open("state/pyramid_ranked.json", "w"), indent=1, ensure_ascii=False)
print(f"\n-> state/pyramid_ranked.json ({len(pyr)} con)")
