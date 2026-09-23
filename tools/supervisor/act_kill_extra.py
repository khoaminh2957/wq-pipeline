#!/usr/bin/env python3
"""Resolve MULTIPLE_DRIVERS — kill watchdogs first, then prune only when the choice is decidable.

A watchdog whose target dies resurrects it with the original argv, which is how a stale driver
comes back on the wrong pool. Watchdogs therefore die before drivers, always.

Choosing which driver to KEEP is the part that was wrong. The old rule was `sorted(pids)[-1]`,
"the newest", and it is unsafe twice over:

  * PID order is not start order. PIDs wrap, so the highest number is not the youngest process.
  * Even correct start order picks wrong. A resurrection is BY CONSTRUCTION younger than the
    driver it duplicates: on 2026-08-02 the intended paircell driver started 12:24:58 and the
    watchdog's resurrection of the superseded pool_struct run started 12:25:08. "Keep the newest"
    would have killed the right one and kept the stale pool.

Age cannot decide it, so this no longer pretends to. When the survivors run DIFFERENT pools the
action refuses and escalates, which matches the runbook's own standing rule — nothing irreversible,
never restart blind. When they run the SAME pool either is equivalent, so keep the one that has
been running longest and therefore has the most work already journalled.
"""
import re
import subprocess
import sys


def pids(pat):
    out = subprocess.run(["pgrep", "-f", pat], capture_output=True, text=True).stdout
    return [int(x) for x in out.split()]


def info(pid):
    """(elapsed_seconds, pool) for a running driver, from ps — there is no /proc on darwin."""
    r = subprocess.run(["ps", "-o", "etime=,command=", "-p", str(pid)],
                       capture_output=True, text=True)
    line = (r.stdout or "").strip()
    if not line:
        return None
    et, _, cmd = line.partition(" ")
    parts = et.split("-")
    days = int(parts[0]) if len(parts) == 2 else 0
    bits = [int(x) for x in parts[-1].split(":")]
    while len(bits) < 3:
        bits.insert(0, 0)
    secs = days * 86400 + bits[0] * 3600 + bits[1] * 60 + bits[2]
    m = re.search(r"--pool\s+(\S+)", cmd)
    return secs, (m.group(1) if m else "?")


w = pids("autoloop/watchdog.py")
for p in w:
    subprocess.run(["kill", str(p)])
print(f"stopped {len(w)} watchdog(s): {w}")

d = pids("autoloop/driver.py")
if len(d) <= 1:
    print(f"only {len(d)} driver — nothing to prune")
    raise SystemExit(0)

meta = {p: v for p, v in ((p, info(p)) for p in d) if v}
pools = {v[1] for v in meta.values()}
if len(pools) > 1:
    print(f"ESCALATE: {len(meta)} drivers on DIFFERENT pools {sorted(pools)} — "
          f"cannot tell which is intended, killing none")
    for p, (secs, pool) in sorted(meta.items()):
        print(f"   pid={p} running {secs}s on {pool}")
    sys.exit(3)

keep = max(meta, key=lambda p: meta[p][0])          # same pool -> keep the longest-running
for p in meta:
    if p != keep:
        subprocess.run(["kill", str(p)])
print(f"same pool {pools.pop()} — kept longest-running driver {keep}, "
      f"killed {[p for p in meta if p != keep]}")
