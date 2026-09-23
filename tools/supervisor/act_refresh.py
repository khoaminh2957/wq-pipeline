#!/usr/bin/env python3
"""Re-read quota / pyramid cell counts from the platform so alerts rest on fresh evidence."""
import argparse, sys, time, pathlib
ROOT = pathlib.Path("/Users/kanenguyen/wq_pipeline")
sys.path.insert(0, str(ROOT/"tools"))
import submit_alphas as SA
ap = argparse.ArgumentParser(); ap.add_argument("--quota",action="store_true"); ap.add_argument("--cells",action="store_true")
a = ap.parse_args()
s = SA.session()
if s.get("https://api.worldquantbrain.com/users/self",timeout=20).status_code != 200:
    print("AUTH 401 — cannot refresh; escalate"); raise SystemExit(2)
if a.cells:
    c, how = SA._cell_counts(s, "USA", 1)
    print(f"cells [{how}]: {c}" if c else "cells unreadable")
if a.quota:
    # Walk a few alphas: /check is async and most return 200-empty, but one usually has a payload,
    # and REGULAR_SUBMISSION is an ACCOUNT counter riding on whichever alpha answers.
    import json
    try:
        cands = list(json.load(open(ROOT/"state/autoloop/corr_pending.json")))[:6]
    except Exception:
        cands = []
    for aid in cands:
        ok, why = SA._quota_ok(s, aid)
        if "quota" not in why or "unreadable" not in why:
            print(f"quota via {aid}: {'OPEN' if ok else 'CLOSED'} — {why[:90]}"); break
        time.sleep(3)
    else:
        print("quota still unreadable")
