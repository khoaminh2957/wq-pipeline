#!/usr/bin/env python3
"""stage_submittable.py — turn an iteration's ZERO-FAIL winners into a growing reserve of genuinely
SUBMITTABLE alphas. A sim zero-fail is NOT automatically submittable: the platform enforces
PROD_CORRELATION<0.7 & SELF_CORRELATION<0.7 at submit (0mM8r3L2 cleared it -> ACTIVE). So for each
winner: measure prod+self corr, and stage ONLY breach-0 & self<0.7 into submittable_reserve.jsonl
(dedup by alpha). Khoa taps to submit from the reserve on days the daily limit allows.
Usage: stage_submittable.py <winners.json> [family_tag]"""
import json, sys, subprocess, pathlib, csv, datetime, fcntl
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
RESERVE = ROOT / "state/funnel/submittable_reserve.jsonl"
CORR = ROOT / "state/funnel/corr_results.jsonl"
WINCSV = ROOT / "state/funnel/winners.csv"   # WINNER = zero-fail AND breach 0 AND self<0.7 (Khoa 2026-07-25)
NEARCSV = ROOT / "state/funnel/near_misses.csv"   # zero-fail but prod/self-walled -> kept here, not a winner
CSV_HDR = ["date","iter","alpha","dataset","category","sharpe","fitness","turnover","warnings",
           "prod_max","breach","self_corr","submittable","status","neut","decay","formula"]

def log_csv(row, clean):
    # a sim zero-fail is NOT a winner: it must also clear PROD_CORRELATION and SELF_CORRELATION.
    path = WINCSV if clean else NEARCSV
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(CSV_HDR)
        w.writerow([row.get(k, "") for k in CSV_HDR])

winners = json.load(open(sys.argv[1]))
fam = sys.argv[2] if len(sys.argv) > 2 else None
iter_tag = sys.argv[3] if len(sys.argv) > 3 else "?"
ids = [w["alpha"] for w in winners if w.get("alpha")]
if not ids:
    print("no winner alpha ids to stage"); sys.exit(0)

# 1) measure prod+self corr for each winner (fixed measure_corr: fail-closed, self_ok)
print(f"measuring prod+self corr for {len(ids)} winners...", flush=True)
subprocess.run([sys.executable, str(ROOT / "tools/measure_corr_incremental.py"), *ids], check=False)

# 2) read the latest corr row per alpha
corr = {}
if CORR.exists():
    for line in open(CORR):
        try: r = json.loads(line)
        except: continue
        if r.get("alpha") in ids:
            corr[r["alpha"]] = r

# --- concurrency guard (B1): overlapping runs must NOT both snapshot `logged`/`staged` before either
# appends, or they double-log the same winners. Hold an exclusive lock across the read+append section. ---
LOCK = WINCSV.with_suffix(".lock")
LOCK.parent.mkdir(parents=True, exist_ok=True)
_lf = open(LOCK, "w")
fcntl.flock(_lf, fcntl.LOCK_EX)

# 3) already-staged (dedup)
staged = set()
if RESERVE.exists():
    for line in open(RESERVE):
        try: staged.add(json.loads(line)["alpha"])
        except: continue
# already-logged alpha ids (BOTH ledgers), so overlapping re-runs don't double-log the same alpha (B1)
logged = set()
for _p in (WINCSV, NEARCSV):
    if not _p.exists(): continue
    import csv as _c
    try:
        for r in _c.DictReader(open(_p)):
            if r.get("alpha"): logged.add(r["alpha"])
    except Exception: pass

added = 0
by_win = {w["alpha"]: w for w in winners if w.get("alpha")}
with open(RESERVE, "a") as f:
    for aid in ids:
        c = corr.get(aid)
        if not c:
            print(f"  {aid}: no corr measured (skip)"); continue
        clean = c.get("clean") and c.get("breach") == 0 and (c.get("self") is None or c["self"] < 0.7)
        w = by_win[aid]
        status = "SUBMITTABLE" if clean else f"not-clean (prod-breach={c.get('breach')} self={c.get('self')})"
        print(f"  {aid}: sh={w.get('sh')} fit={w.get('ft')} prod={c.get('prod_max')} breach={c.get('breach')} self={c.get('self')} -> {status}")
        # STANDING RULE: log every zero-fail — clean ones to winners.csv, walled ones to
        # near_misses.csv (Khoa 2026-07-25: only prod+self passers count as winners) — once per alpha
        st = (w.get("settings") or {})
        if aid in logged:
            print(f"  {aid}: already logged (skip re-log)")
        else:
            logged.add(aid)
            log_csv({"date": datetime.date.today().isoformat(), "iter": iter_tag, "alpha": aid,
                 "dataset": w.get("_ds") or fam or "?", "category": fam or w.get("_ds") or "?",
                 "sharpe": w.get("sh"), "fitness": w.get("ft"), "turnover": w.get("tv"),
                 "prod_max": c.get("prod_max"), "breach": c.get("breach"), "self_corr": c.get("self"),
                 "submittable": "yes" if clean else "no", "status": "RESERVE" if clean else "prod-walled",
                 "neut": st.get("neutralization"), "decay": st.get("decay"),
                 "formula": (w.get("formula") or "").strip()}, clean)
        if clean and aid not in staged:
            rec = {"alpha": aid, "sharpe": w.get("sh"), "fitness": w.get("ft"), "turnover": w.get("tv"),
                   "prod_max": c.get("prod_max"), "self": c.get("self"), "family": fam or w.get("_ds") or "?",
                   "neut": (w.get("settings") or {}).get("neutralization"), "formula": (w.get("formula") or "").strip()}
            f.write(json.dumps(rec) + "\n"); added += 1

fcntl.flock(_lf, fcntl.LOCK_UN)
_lf.close()

total = sum(1 for _ in open(RESERVE)) if RESERVE.exists() else 0
print(f"\nstaged {added} new SUBMITTABLE -> {RESERVE}  (reserve total: {total})")
