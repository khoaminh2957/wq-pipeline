#!/bin/bash
# The FORGE loop, ON THE VPS (CLAUDE.md RULE 1). One copy only, under its own lock. It must not run
# beside climb_loop.sh: both spend the same 5,000/day quota and the redesign replaces the climb
# outright (C26) -- stop the climb first (touch state/STOP_CLIMB), then start this.
#
#   round:  forge/runner.py  -> plan (cells -> hypotheses -> factory -> gates) -> shared dispatcher
#   then:   forge/harvest.py -> platform gates, turnover band, DSR from the PnL recordset
#   bg:     forge/probe.py   -> prod/self correlation for candidates (flock singleton, +120 s read)
#   then:   forge/submit.py  -> POST what is eligible (C21), cells first, 1/mechanism/week
exec 9>/var/lock/wq_forge.lock
if ! flock -n 9; then echo "forge loop already running; exiting"; exit 0; fi
exec 8>&-

cd /opt/wq || exit 1
LOG=/opt/wq/state/forge/loop.log
STOP=/opt/wq/state/STOP_FORGE
N=${N:-300}
ROUNDS=${ROUNDS:-400}      # ROUNDS=1 for the canary
mkdir -p /opt/wq/state/forge
PY=/opt/wq/venv/bin/python

if flock -n /var/lock/wq_climb.lock true 2>/dev/null; then :; else
  echo "climb loop holds /var/lock/wq_climb.lock -- refusing to run two spenders; exiting" | tee -a "$LOG"
  exit 0
fi

for r in $(seq 1 "$ROUNDS"); do
  if [ -f "$STOP" ]; then
    rm -f "$STOP"
    echo "STOP file present (consumed); ending" | tee -a "$LOG"
    break
  fi

  # Alive AND at least 40 minutes left (Khoa's tick 2026-09-07 14:10). A round is ~35 min; one that
  # starts later than that spends its simulations on a session that dies before they are read --
  # 96 AUTH-FAIL rows and 15 orphan parents by 14:00 on 09-07. An unreadable cookie jar (None)
  # falls back to the liveness answer alone.
  if ! $PY -c "
import sys; sys.path.insert(0,'tools')
import layered_sim as LS, mint_link as M
s=LS.session(); r=s.get(LS.API+'/users/self', timeout=25)
left=M.session_left_s()
sys.exit(0 if r.status_code==200 and (left is None or left>=2400) else 1)
" 2>/dev/null; then
    echo "=== auth dead or under 40 min before round $r, $(date) ===" | tee -a "$LOG"
    # The hourly link law lives inside mint_link/outbox; asking is free while the wall is up.
    $PY tools/mint_link.py --quiet >> "$LOG" 2>&1 9>&- || true
    sleep 300 9>&-
    continue
  fi

  $PY tools/record_adjudication.py >> "$LOG" 2>&1 9>&- || true
  # THE PLATFORM'S OWN CELL COUNTER, refreshed before every round (one GET). The cached file had
  # stood at 2026-09-04 10:20 while two submissions moved USA/d1 Short Interest 0 -> 2; the planner
  # was still aiming at a need of 3. forge/offline/refresh_cells.py fails closed (file untouched).
  timeout 120 $PY forge/offline/refresh_cells.py >> "$LOG" 2>&1 9>&- || true
  SEED=$(date +%s)
  echo "=== forge round, seed $SEED, N=$N, $(date) ===" | tee -a "$LOG"
  # FORGE_ARGS: extra runner flags for a targeted round (e.g. --cells "GLB/d1 Fundamental" --only x,y)
  $PY -u forge/runner.py -n "$N" --seed "$SEED" --live --concurrency 9 --children 10 $FORGE_ARGS 9>&- >> "$LOG" 2>&1
  RC=$?
  echo "=== round exit $RC at $(date) ===" >> "$LOG"
  if [ "$RC" -eq 2 ]; then
    echo "=== library exhausted for every reachable cell (m13 case) ===" | tee -a "$LOG"
    # A one-round invocation (ROUNDS=1, the search driver) must return at once; only the standing
    # loop sleeps for the hour. Measured 2026-09-04 17:08: R8 found no candidates and the driver
    # sat inside this sleep while the session ran out.
    if [ "$ROUNDS" -gt 1 ]; then sleep 3600 9>&-; fi
    continue
  fi

  # Children the runner could not read (a session that died mid-round, a stall) are fetched back
  # from the platform and attributed by plan file, so the allocator and the DSR pools see every
  # simulation that was paid for (Khoa's tick 2026-09-07 14:10). Cheap when there is nothing.
  timeout 900 $PY forge/offline/recover_orphans.py --limit 30 >> "$LOG" 2>&1 9>&- || true

  # Score what just landed (PnL recordsets: one GET each, computed on demand).
  timeout 1800 $PY -u forge/harvest.py --limit 400 >> "$LOG" 2>&1 9>&-

  # Correlations for the candidates, in the background, singleton. Trigger, +120 s, read once.
  (
    flock -n 8 || exit 0
    timeout 1500 $PY -u forge/probe.py --limit 60 --wait 120 >> "$LOG" 2>&1 9>&-
    echo "=== probe (bg) done, $(date) ===" >> "$LOG"
  ) 8>/var/lock/wq_forge_probe.lock 9>&- &

  # Submit whatever is eligible. The submitter enforces every gate itself (C21) and refuses alone.
  SUBOUT=$($PY forge/submit.py --submit --cap 4 2>&1 9>&-)
  echo "$SUBOUT" >> "$LOG"
  if echo "$SUBOUT" | grep -q "^HTTP 20"; then
    timeout 120 $PY forge/offline/refresh_cells.py >> "$LOG" 2>&1 9>&- || true
  fi

  # Only THIS round's output may say the quota is spent. MEASURED 2026-09-07 11:30: the 01:53
  # "DAILY_SIMULATION_LIMIT_EXCEEDED" line was still inside the last 400 lines after the first
  # round of the new day, and the loop slept 84,880 s with a live session and a fresh quota.
  if sed -n "/=== forge round, seed $SEED,/,\$p" "$LOG" | grep -q "DAILY_SIMULATION_LIMIT_EXCEEDED"; then
    NOW=$(date +%s)
    RESET=$(date -d "today 11:05" +%s 2>/dev/null || echo $((NOW + 3600)))
    [ "$RESET" -le "$NOW" ] && RESET=$(date -d "tomorrow 11:05" +%s)
    SLEEP=$((RESET - NOW))
    echo "=== daily quota spent; sleeping ${SLEEP}s until the 11:00 reset ===" | tee -a "$LOG"
    sleep "$SLEEP" 9>&-
    continue
  fi
done
echo "=== forge loop ended $(date) ===" | tee -a "$LOG"
