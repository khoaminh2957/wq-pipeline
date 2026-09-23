#!/usr/bin/env python3
"""Human directive (Khoa): IMPROVE the alpha — do NOT submit KP9pmQjz. Wait for rate-ban to clear,
then run gen-3 batch-1 (11 sims: illiquidity trunc-0.04/0.06 + quantile + momentum rk/rkneg + P1/P2' probes).
SIM ONLY — no irreversible submit."""
import time, json, pickle, requests, subprocess, shutil
from pathlib import Path
ROOT = Path("/Users/kanenguyen/wq_pipeline")
s = requests.Session(); s.headers.update({"Connection": "close"})
s.cookies.update(pickle.load(open(ROOT / "state/wq_cookies.pkl", "rb")))

print("WAIT-BAN: probing until clear (no hammer)...", flush=True)
while True:
    try:
        r = s.get("https://api.worldquantbrain.com/authentication", timeout=30)
    except requests.exceptions.RequestException as e:
        print(f"  probe network error: {e}; retry in 30s", flush=True); time.sleep(30); continue
    if r.status_code != 429:
        print(f"BAN-CLEAR: /authentication -> {r.status_code}", flush=True); break
    wait = float(r.headers.get("Retry-After", 120) or 120)
    print(f"  still banned, Retry-After={wait:.0f}s", flush=True)
    time.sleep(min(wait, 300) + 3)

shutil.copy(ROOT / "state/gen3_batch1_targets.json", ROOT / "state/resim_targets.json")
print("LAUNCH: gen-3 batch-1 (11 con) — SIM ONLY, improving toward robust-universe fix", flush=True)
subprocess.Popen(["python3", "-u", str(ROOT / "tools/resim_bulk.py")],
                 stdout=open(ROOT / "state/resim_batch1.out", "w"), stderr=subprocess.STDOUT, cwd=str(ROOT))
print("DEPLOY-DONE: batch-1 engine launched (KP9pmQjz NOT submitted — human directive: improve first)", flush=True)
