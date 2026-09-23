#!/bin/zsh
# Keep the simulator fed. Run once, in the background, for the life of the session.
#
# The simulator sat idle 11:43 -> 17:34 — nearly six hours — because the queue emptied and nothing
# refilled it. `simq.sh` had fixed the two failure modes it was written for (an orphan lock, a dead
# session) and neither of them was this one: the queue simply ran out.
#
# So this watches a QUEUE DIRECTORY. Drop a pool in, it gets simulated in order; when the directory
# empties the loop keeps waiting rather than exiting, so a pool dropped in at 03:00 runs at 03:00.
#
#   state/simqueue/*.json    pending, dispatched oldest-first
#   state/simrunning/        the ONE pool currently dispatched
#   state/simdone/           finished successfully, with its log next to it
#   state/simfailed/         REFUSED or errored — kept, never silently archived
#
# Two corrections, both paid for in idle hours on 2026-08-08:
#
#   FAILURE-BLINDNESS. This used to `mv "$POOL" state/simdone/` with no reference to the exit code,
#   so a pool the precheck refused outright — 0 POSTs, 3 seconds — was archived identically to a
#   pool that ran 572 simulations over 34 minutes. That happened at 18:17:27 and the simulator then
#   sat idle 3h11m with the log reading "done". Success and refusal must not land in the same place.
#
#   SINGLETON. The pool stayed in state/simqueue/ for the whole run, so a second feeder — or this
#   one restarted after a disconnect — picked the same pool and dispatched it again. Claiming the
#   pool by MOVING it before dispatch makes double-dispatch impossible rather than unlikely, and a
#   crash leaves the claim visible in state/simrunning/ instead of losing the pool.
#
#   tools/simfeed.sh &                                   # start the feeder
#   cp state/autoloop/pool_x.json state/simqueue/        # enqueue anything, anytime
set -u
cd /Users/kanenguyen/wq_pipeline
mkdir -p state/simqueue state/simdone state/simfailed state/simrunning
LOG=state/simfeed.log

# ONE feeder, or two feeders race for every pool and each dispatches the other's claim.
#
# macOS ships no flock(1), so the lock is taken by a python child on an fd this shell opened. The
# lock lives on the OPEN FILE DESCRIPTION, not on the fd, and the parent shell keeps fd 9 open for
# its whole life — so the lock survives the child exiting and is released by the kernel the moment
# this feeder dies. That is the property that matters: a killed feeder never blocks its
# replacement, and a live one can never be displaced. (Verified 2026-08-08 by holding it in one
# shell and failing to acquire it in a second.)
exec 9>>state/simfeed.lock
if ! python3 -c "
import fcntl, sys
try:
    fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    sys.exit(1)
" 2>/dev/null; then
  echo "[$(date +%H:%M:%S)] another feeder holds state/simfeed.lock — exiting" >> $LOG
  exit 0
fi

# A pool left in state/simrunning/ by a crashed feeder is not lost — put it back at the head.
for orphan in state/simrunning/*.json(N); do
  echo "[$(date +%H:%M:%S)] requeueing orphan $(basename $orphan) from a previous feeder" >> $LOG
  mv "$orphan" state/simqueue/ 2>/dev/null
done

echo "[$(date +%H:%M:%S)] feeder up — watching state/simqueue/" >> $LOG

# KEEP THE QUEUE DEEP, don't refill it from empty. Refilling only at depth 0 guarantees a gap the
# length of one generation on EVERY pool boundary, because the generator runs while nothing is
# simulating. Measured 2026-08-11: 00:21:58 finished, 00:31:44 launched — 9m46s of an idle engine
# between two pools, with the account's quota ticking and nothing produced. Topping up while a pool
# is still running costs nothing and removes the boundary entirely.
MIN_QUEUE=${MIN_QUEUE:-3}

top_up() {
  [ -x state/autorefill.sh ] || return 0
  NQ=$(ls -1 state/simqueue/*.json 2>/dev/null | wc -l | tr -d " ")
  [ "$NQ" -ge "$MIN_QUEUE" ] && return 0
  # background, so a slow generator never stalls dispatch of the pool already queued
  ( state/autorefill.sh >> state/autorefill.log 2>&1 ) &
  echo "[$(date +%H:%M:%S)] queue depth $NQ < $MIN_QUEUE — topping up in the background" >> $LOG
}

while true; do
  top_up
  # oldest first, so enqueue order is run order
  POOL=$(ls -1tr state/simqueue/*.json 2>/dev/null | head -1)
  if [ -z "$POOL" ]; then
    sleep 5
    continue
  fi
  NAME=$(basename "$POOL" .json)

  # CLAIM before dispatch: out of the queue, so nothing else can pick it up mid-run.
  RUNNING="state/simrunning/${NAME}.json"
  mv "$POOL" "$RUNNING" 2>/dev/null || continue

  # GATE EVERY POOL AT DISPATCH, not by convention. tools/gate_pool.py already checks operator
  # existence, arity and named arguments against OPERATORS.md and drops anything over the 64-operator
  # ceiling — but only state/autorefill.sh was calling it, so any pool written straight into
  # state/simqueue/ went to the platform unchecked. Measured over the journal 2026-08-11: 1,032
  # simulations came back "Expression with 65-72 operators exceeds limit of 64" and 240 came back
  # "Invalid number of inputs : 2, should be exactly 1 input(s)" — 1,272 spent on errors a local
  # count and an arity table would have caught for free. Generators PD, SZ and al_iter produced all
  # of them, and none of the three ran the gate.
  python3 tools/gate_pool.py "$RUNNING" --fix >> state/gate_pool.log 2>&1
  NROWS=$(python3 -c "import json;print(len(json.load(open('$RUNNING'))))" 2>/dev/null || echo 0)
  if [ "$NROWS" -lt 1 ]; then
    echo "[$(date +%H:%M:%S)] $NAME gated down to 0 rows — quarantining instead of dispatching" >> state/simq_events.log
    mv "$RUNNING" state/simfailed/ 2>/dev/null
    continue
  fi

  # TRIM TO THE REMAINDER AT CLAIM TIME, not after a failure. Any row already carrying a terminal
  # journal entry is a DUPLICATE as far as the precheck is concerned, and the precheck rejects the
  # whole batch rather than the duplicate rows — so a pool interrupted at 180/208 comes back as
  # "precheck blocked launch — 0 POSTs" and looks like a generator bug. That happened to sh791 and
  # sh792 in the same hour. Trimming here makes the retry path and the fresh path identical, and
  # for a fresh pool it is a no-op.
  KEPT=$(python3 - "$RUNNING" <<'PY'
import json, sys, pathlib
pool = pathlib.Path(sys.argv[1])
try:
    rows = json.load(open(pool))
except Exception:
    print(-1); raise SystemExit
TERMINAL = {"COMPLETE", "ERROR", "EXPIRED", "WARNING"}
done = set()
for line in open("state/resim_results.jsonl"):
    try:
        d = json.loads(line)
    except Exception:
        continue
    if d.get("status") in TERMINAL or d.get("alpha") or d.get("retried"):
        done.add(d.get("old_id"))
left = [r for r in rows if r.get("old_id") not in done]
if len(left) != len(rows) and left:
    json.dump(left, open(pool, "w"), indent=1)
print(len(left))
PY
)
  if [ "${KEPT:-0}" -eq 0 ]; then
    mv "$RUNNING" state/simdone/ 2>/dev/null
    echo "[$(date +%H:%M:%S)] skip: $NAME — every row already journaled" >> $LOG
    continue
  fi
  echo "[$(date +%H:%M:%S)] next: $NAME ($KEPT rows to simulate)" >> $LOG

  # simq.sh waits out a live flock and a 401 rather than draining the queue against either, and
  # resim_bulk.py refuses the launch outright if any formula violates the OPERATORS.md table.
  # 9<&- CLOSES the singleton lock fd for the child. Without it simq.sh — and everything it spawns —
  # inherits fd 9, and an flock lives on the OPEN FILE DESCRIPTION, not on the process. So killing
  # the feeder while a child was still running left the lock held by an orphan: `pgrep simfeed` came
  # back empty while `lsof state/simfeed.lock` showed a stray simq.sh and a sleep still on fd 9, and
  # every replacement feeder exited with "another feeder holds the lock". That is the orphan-lock
  # failure this repo has hit repeatedly, reintroduced in a new place by the singleton guard itself.
  tools/simq.sh "$RUNNING" "state/${NAME}.log" 9<&-
  RC=$?

  TAIL=$(tail -1 "state/${NAME}.log" 2>/dev/null | cut -c1-90)
  if [ $RC -eq 0 ]; then
    mv "$RUNNING" state/simdone/ 2>/dev/null
    echo "[$(date +%H:%M:%S)] done: $NAME -> $TAIL" >> $LOG
  else
    # NOT ALL FAILURES ARE THE SAME, and the first version of this branch treated them as if they
    # were. pool_sh791 reached 180/208 and then lost the session mid-run; it was filed permanently
    # into state/simfailed/ and 208 partly-paid-for rows left rotation for good.
    #
    #   REFUSED  — the precheck rejected the pool outright, 0 POSTs, ~3 seconds. That is a
    #              generator bug: re-running re-refuses it instantly and spins the queue.
    #   PARTIAL  — the launch happened and the run died part-way (auth expiry is the common one;
    #              the session lasts ~4h and needs a human tap). That is transient and the
    #              remaining rows are still worth simulating.
    #
    # The distinction is visible in the log line the wrapper already writes, and the counter is
    # capped so a pool that keeps dying cannot loop forever.
    ATTEMPTS=$(grep -c "requeued $NAME" $LOG 2>/dev/null || echo 0)
    # A refusal whose every block is DUPLICATE means the work is DONE, not that the pool is bad.
    # The claim-time trim reads the journal once, but an in-flight resim_bulk from an earlier
    # dispatch keeps journaling afterwards — killing the feeder does not kill it. sh793 was trimmed
    # to "208 rows to simulate" at 22:03, waited 16 minutes on the flock, and by the time it ran,
    # the original process had journaled all 208. The precheck refused it correctly; filing that as
    # a generator bug is what was wrong.
    if grep -q "precheck blocked launch" "state/${NAME}.log" 2>/dev/null \
       && [ "$(grep -c 'BLOCK' "state/${NAME}.log" 2>/dev/null)" -gt 0 ] \
       && [ "$(grep 'BLOCK' "state/${NAME}.log" 2>/dev/null | grep -vc 'DUPLICATE')" -eq 0 ]; then
      mv "$RUNNING" state/simdone/ 2>/dev/null
      echo "[$(date +%H:%M:%S)] done (all rows already simulated elsewhere): $NAME" >> $LOG
    elif grep -q "precheck blocked launch" "state/${NAME}.log" 2>/dev/null; then
      mv "$RUNNING" state/simfailed/ 2>/dev/null
      echo "[$(date +%H:%M:%S)] REFUSED rc=$RC: $NAME -> $TAIL   (generator bug, kept in state/simfailed/)" >> $LOG
    elif [ "$ATTEMPTS" -lt 2 ]; then
      # Requeue the REMAINDER, not the pool. A partial run has already simulated some rows, and
      # those are now in the targets history — re-submitting them makes the batch a duplicate and
      # the precheck refuses the whole thing. pool_sh791 died at 180/208, was requeued whole, and
      # came straight back as "precheck blocked launch — 0 POSTs". Only the rows that never reached
      # a terminal journal row are still worth simulating.
      LEFT=$(python3 - "$RUNNING" <<'PY'
import json, sys, pathlib
pool = pathlib.Path(sys.argv[1])
rows = json.load(open(pool))
done = set()
TERMINAL = {"COMPLETE", "ERROR", "EXPIRED", "WARNING"}
for line in open("state/resim_results.jsonl"):
    try:
        d = json.loads(line)
    except Exception:
        continue
    if d.get("status") in TERMINAL or d.get("alpha") or d.get("retried"):
        done.add(d.get("old_id"))
left = [r for r in rows if r.get("old_id") not in done]
if left:
    json.dump(left, open(pool, "w"), indent=1)
print(len(left))
PY
)
      if [ "${LEFT:-0}" -gt 0 ]; then
        mv "$RUNNING" state/simqueue/ 2>/dev/null
        echo "[$(date +%H:%M:%S)] PARTIAL rc=$RC: $NAME -> $TAIL   (requeued $LEFT unsimulated rows, attempt $((ATTEMPTS+2)))" >> $LOG
      else
        mv "$RUNNING" state/simdone/ 2>/dev/null
        echo "[$(date +%H:%M:%S)] PARTIAL rc=$RC but every row is journaled: $NAME -> done" >> $LOG
      fi
      sleep 15                       # simq.sh already waits out a dead session; do not double-wait
    else
      mv "$RUNNING" state/simfailed/ 2>/dev/null
      echo "[$(date +%H:%M:%S)] FAILED rc=$RC after $((ATTEMPTS+1)) attempts: $NAME -> $TAIL   (kept in state/simfailed/)" >> $LOG
    fi
  fi
done
