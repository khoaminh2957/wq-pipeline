#!/usr/bin/env python3
"""Restart the miner by RE-DERIVING its arguments, never by replaying an old command line.

watchdog.py restarts a dead driver with its original argv. On 2026-08-01 that resurrected a driver
pointing at a pool that had already been superseded; it grabbed the sim lock and the correct driver
sat blocked for 25 minutes. A restart must therefore rebuild the pool from what has actually been
simulated, and must stop any surviving watchdog first so it cannot undo the fix.
"""
import glob, json, pathlib, subprocess, sys, time
ROOT = pathlib.Path("/Users/kanenguyen/wq_pipeline")

for pat in ("autoloop/watchdog.py", "autoloop/driver.py", "run_multisim.py", "resim_bulk.py"):
    out = subprocess.run(["pgrep", "-f", pat], capture_output=True, text=True).stdout.split()
    for p in out:
        subprocess.run(["kill", p])
    if out:
        print(f"stopped {pat}: {out}")
    time.sleep(2)

subprocess.run([sys.executable, str(ROOT / "tools/supervisor/act_clear_lock.py")])

base = sorted(glob.glob(str(ROOT / "state/autoloop/pool_x*.json")))
if not base:
    print("no base pool found — escalate"); raise SystemExit(2)
staged = set()
for f in glob.glob(str(ROOT / "state/autoloop/*_targets.json")):
    try:
        for r in json.load(open(f)):
            o = r.get("old_id", "")
            staged.add(o)
            if "_" in o:
                staged.add(o.split("_", 1)[1])
    except Exception:
        pass
rows = [r for r in json.load(open(base[-1])) if r["old_id"] not in staged]
if len(rows) < 100:
    print(f"only {len(rows)} unsimulated rows left in {base[-1]} — escalate"); raise SystemExit(2)
out = ROOT / "state/autoloop/pool_auto.json"
json.dump(rows, open(out, "w"))

pf = subprocess.run([sys.executable, str(ROOT / "tools/autoloop/preflight.py"), str(out)],
                    capture_output=True, text=True, cwd=str(ROOT))
print((pf.stdout or "").strip().splitlines()[-1] if pf.stdout else "preflight: no output")
if pf.returncode != 0:
    print("preflight FAILED — not launching; escalate"); raise SystemExit(2)

log = open(ROOT / "state/autoloop/driver_auto.log", "a")
# --no-submit is MANDATORY here and was missing. `--no-submit` is an OPT-OUT flag
# (driver.py:831) and driver.py:787 reads `submit(clean) if clean and not args.no_submit`, so
# omitting it means SUBMIT. This action re-derives argv from scratch rather than replaying it —
# deliberately, for the reasons in this file's own docstring — and the rebuilt list dropped the
# flag, so an automated remediation could POST real irreversible submissions with no human in the
# loop. JOURNAL_STALE alone has fired 491 times in state/supervisor.log.
#
# That contradicts this supervisor's own charter, runbook.json _doc: "1. NOTHING IRREVERSIBLE.
# No submit, no state deletion." The driver's default is NOT the bug — unattended submitting of
# clean gems is authorised for a human-launched mining run. An automatic restart triggered by an
# ALERT is a different thing, and it may only find and bank.
p = subprocess.Popen([sys.executable, str(ROOT / "tools/autoloop/driver.py"),
                      "--pool", str(out), "--hours", "4", "--rounds", "10", "--tag", "AA",
                      "--no-submit"],
                     stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT))
time.sleep(6)
subprocess.Popen([sys.executable, str(ROOT / "tools/autoloop/watchdog.py"),
                  "--pid", str(p.pid), "--deadline-hours", "4"],
                 stdout=open(ROOT / "state/autoloop/watchdog_auto.log", "a"),
                 stderr=subprocess.STDOUT, cwd=str(ROOT))
print(f"driver restarted pid={p.pid} on {len(rows)} unsimulated rows")
