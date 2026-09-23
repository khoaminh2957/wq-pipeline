#!/usr/bin/env python3
"""LEADER greenlight [10] deploy: wait for rate-ban to clear, submit KP9pmQjz (bank chiến thuật),
then launch gen-3 batch-1 (11 formulas incl P1/P2' probes). Prints milestones for the monitor."""
import time, json, pickle, requests, subprocess, sys
from pathlib import Path
ROOT = Path("/Users/kanenguyen/wq_pipeline")
sys.path.insert(0, str(ROOT))
from harness.guards import reserve_submit, release_submit, slot_returnable
s = requests.Session(); s.headers.update({"Connection": "close"})
s.cookies.update(pickle.load(open(ROOT / "state/wq_cookies.pkl", "rb")))

# 1) wait for ban clear — probe a LIGHT endpoint, honor Retry-After, never hammer
print("WAIT-BAN: probing until clear...", flush=True)
while True:
    try:
        r = s.get("https://api.worldquantbrain.com/authentication", timeout=30)
    except requests.exceptions.RequestException as e:
        print(f"  probe network error: {e}; retry in 30s", flush=True); time.sleep(30); continue
    if r.status_code != 429:
        print(f"BAN-CLEAR: /authentication -> {r.status_code}", flush=True); break
    wait = float(r.headers.get("Retry-After", 120) or 120)
    print(f"  still banned, Retry-After={wait:.0f}s", flush=True)
    time.sleep(min(wait, 300) + 3)   # cap single sleep, re-probe

# 2) submit KP9pmQjz — G6-gated: atomically reserve the 1-POST-per-alpha budget BEFORE POSTing
#    (same ledger as complete_/gentle_submit); already-spent -> poll-only, NEVER re-POST.
print("SUBMIT: KP9pmQjz ...", flush=True)
res = {"alpha": "KP9pmQjz"}
ok, why = reserve_submit("KP9pmQjz", "deploy_greenlight")
if not ok:
    res.update(status="G6-blocked", body=why)
    print(f"G6: {why} -> NOT POSTing", flush=True)
else:
    for attempt in range(5):
        r = s.post("https://api.worldquantbrain.com/alphas/KP9pmQjz/submit", timeout=40)
        if r.status_code == 429:
            w = float(r.headers.get("Retry-After", 30) or 30); print(f"  submit 429, wait {w:.0f}s", flush=True); time.sleep(w + 2); continue
        res.update(status=r.status_code, body=(r.text or "")[:400])
        if slot_returnable(r.status_code, r.text or ""):   # 408/429, or an ERROR-only 403
            release_submit("KP9pmQjz"); print(f"  {r.status_code} at POST; G6 reservation released", flush=True)
        elif 400 <= r.status_code < 500:
            print(f"  {r.status_code} ADJUDICATED; G6 reservation KEPT (this alpha is spent)", flush=True)
        break
    else:                                   # all 5 attempts were 429 (rate ban) -> no submission created
        res.update(status=429, body="submit rate-banned: 5x429, no submission created")
        release_submit("KP9pmQjz"); print("  5x429 at POST; G6 reservation released", flush=True)
res["ok"] = res.get("status") in (200, 201)
json.dump(res, open(ROOT / "state/KP9pmQjz_submit.json", "w"), indent=1)
print(f"SUBMIT-RESULT: HTTP {res.get('status')} ok={res['ok']} | {str(res.get('body'))[:160]}", flush=True)

# 3) launch batch-1 engine (self rate-gated, 429-aware)
import shutil
shutil.copy(ROOT / "state/gen3_batch1_targets.json", ROOT / "state/resim_targets.json")
print("LAUNCH: gen-3 batch-1 (11 con) via resim_bulk v5", flush=True)
subprocess.Popen(["python3", "-u", str(ROOT / "tools/resim_bulk.py")],
                 stdout=open(ROOT / "state/resim_batch1.out", "w"), stderr=subprocess.STDOUT, cwd=str(ROOT))
print("DEPLOY-DONE: submit fired + batch-1 engine launched", flush=True)
