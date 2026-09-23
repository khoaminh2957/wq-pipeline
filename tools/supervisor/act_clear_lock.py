#!/usr/bin/env python3
"""Remove state/resim.lock only when no live process holds the flock."""
import fcntl, json, os, pathlib
LOCK = pathlib.Path("/Users/kanenguyen/wq_pipeline/state/resim.lock")
if not LOCK.exists():
    print("no lock file"); raise SystemExit
h = open(LOCK, "a+")
try:
    fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fcntl.flock(h, fcntl.LOCK_UN)
except OSError:
    print("lock is HELD by a live process — leaving it alone"); raise SystemExit
finally:
    h.close()
try:
    pid = json.load(open(LOCK)).get("pid")
except Exception:
    pid = None
os.remove(LOCK)
print(f"removed stale lock (last holder pid={pid}, not running)")
