#!/bin/zsh
# Run one simulation batch, correctly: respect a live lock, wait for auth, and REPORT THE OUTCOME.
#
# Every ad-hoc queue wrapper written for this repo got one of these wrong, and each cost hours:
#
#   * `while [ -e state/resim.lock ]; do sleep 30; done` waited 305 minutes on a lock whose pid
#     (39723) had been dead since 15:50. A lock FILE is not evidence that anything is running.
#   * A wrapper with no auth check drained 14 calibration pairs in 2 minutes against a 401 —
#     run_multisim prints "401" and exits in 11 seconds, so a dead session empties a queue rather
#     than delaying it.
#   * `pgrep -f <poolname>` matches the WAITING wrapper as well as the running simulation, so
#     "is it running?" answered yes while nothing was being simulated.
#   * `exit 0` unconditionally. This one cost 3h11m of idle simulator on 2026-08-08: pool_shape3
#     was refused by the precheck at 18:17:27, run_multisim returned 1, this script reported 0, and
#     the feeder archived a pool that ran ZERO sims as though it had succeeded — then waited for a
#     queue that nothing would ever refill. A wrapper that cannot fail cannot be supervised.
#
# LOCK PROTOCOL. state/resim.lock is a real fcntl flock (resim_bulk.py:38) and flock AUTO-RELEASES
# when its holder dies, so a failed non-blocking acquire ALWAYS means a live holder and the pid
# stamp is never needed. The previous `kill -0 $pid` version was wrong twice over: the holder
# stamps its pid a few statements AFTER acquiring the lock, so a freshly-started run reads as
# dead — and the `rm -f state/resim.lock` that followed UNLINKS the file out from under that live
# holder, which keeps its flock on the now-orphaned inode while the next process creates a new
# file and acquires a new flock on a different inode. That does not clear a stale lock; it deletes
# mutual exclusion, and two simulators then run against one account writing one journal.
# So: probe the flock, never stat the file, never remove it.
#
#   tools/simq.sh state/autoloop/pool_x.json state/x.log
set -u
POOL=$1; LOG=${2:-state/simq.log}
cd /Users/kanenguyen/wq_pipeline

# exit 0 = a live process holds the flock; exit 1 = nobody does (absent or stale)
held() {
  python3 - <<'PY'
import fcntl, pathlib, sys
f = pathlib.Path("state/resim.lock")
if not f.exists():
    sys.exit(1)
h = open(f, "a+")
try:
    fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fcntl.flock(h, fcntl.LOCK_UN)
    sys.exit(1)                                  # acquired it ourselves => nobody holds it
except OSError:
    sys.exit(0)                                  # someone holds it => a run is live
finally:
    h.close()
PY
}

while true; do
  if held; then
    sleep 30; continue                           # a real run holds it — wait, do not touch the file
  fi

  ST=$(python3 -c "
import sys,pathlib
sys.path.insert(0,str(pathlib.Path.cwd()/'tools'))
import submit_alphas as SA
try: print(SA.session().get('https://api.worldquantbrain.com/users/self',timeout=25).status_code)
except Exception: print(0)
" 2>/dev/null)
  if [ "$ST" != "200" ]; then
    echo "[$(date +%H:%M:%S)] auth=$ST — holding $POOL" >> state/simq_events.log
    # 20s, not 120s. Measured 2026-08-09 over the event log: 218 "auth=401 — holding" against 35
    # launches, so this branch is where the pipeline spends most of its life. The wait itself is
    # unavoidable (only a human tap restores the session) but the LATENCY AFTER the tap is not —
    # at 120s the pipeline sat idle up to two minutes past every restoration, and there are
    # roughly six restorations a day.
    sleep 20; continue
  fi

  echo "[$(date +%H:%M:%S)] launching $POOL" >> state/simq_events.log
  python3 tools/funnel/run_multisim.py --sweep --stall-timeout 900 "$POOL" > "$LOG" 2>&1
  RC=$?
  echo "[$(date +%H:%M:%S)] finished $POOL rc=$RC -> $(tail -1 $LOG)" >> state/simq_events.log

  # A DAILY CAP IS NOT A CRASH, and treating it as one cost 5h47m on 2026-08-11. The account hit
  # 4999/5000 at 01:19; resim_bulk correctly refused to re-probe "a wall that will not move" and
  # returned non-zero; simq propagated that as failure; systemd restarted the feeder; six pools
  # burned in five minutes; StartLimitBurst tripped and wq-loop went to `failed` and STAYED there
  # while the wall itself expired hours earlier.
  #
  # So: put the pool back, wait out the reset, and exit 0. The queue is not the casualty here — the
  # pool never ran, and re-queueing it is what makes the wait free.
  if grep -q "DAILY CAP REACHED" "$LOG" 2>/dev/null; then
    SECS=$(sed -n 's/.*resets in \([0-9.]*\)h.*/\1/p' "$LOG" | head -1)
    SECS=${SECS:-1}
    SLEEP=$(python3 -c "print(int(min(max(float('$SECS')*3600, 300), 43200)))" 2>/dev/null || echo 3600)
    mv "$POOL" state/simqueue/ 2>/dev/null
    echo "[$(date +%H:%M:%S)] DAILY CAP — requeued $(basename $POOL), sleeping ${SLEEP}s until the quota resets (this is NOT a failure)" >> state/simq_events.log
    sleep "$SLEEP"
    exit 0
  fi
  exit $RC
done
