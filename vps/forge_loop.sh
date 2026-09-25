#!/bin/bash
# The FORGE loop, ON THE VPS (CLAUDE.md RULE 1). One copy only, under its own lock. It must not run
# beside climb_loop.sh: both spend the same 5,000/day quota and the redesign replaces the climb
# outright (C26) -- stop the climb first (touch state/STOP_CLIMB), then start this.
#
#   round:  forge/runner.py  -> plan (cells -> hypotheses -> factory -> gates) -> shared dispatcher
#   then:   forge/harvest.py -> platform gates, turnover band, DSR from the PnL recordset
#   bg:     forge/probe.py   -> prod/self correlation for candidates (flock singleton, +120 s read)
#   then:   forge/submit.py  -> POST what is eligible (C21), cells first, 1/mechanism/week
#
# THE LOG IS READ BY `tools/deploy.py watch` (D43; round 3 S2-S4). Every line it reads starts "=== " and ends
# "===": the round header, `=== round exit N`, one `=== step <name> exit N, seed S ===` after each step,
# `=== round end, seed S, at <epoch> ===`, and before a round the auth gate's own markers and the pre-round
# steps' exits, each with `at <epoch>` so the watch can place it after a push. After a runner ended by a signal
# (exit >= 128, D58) the round writes `=== runner ended by signal ...` and its round end, and no step markers; the
# watch reports that exit and never rolls it back (D43). Change a marker here and tools/tests/test_deploy.py fails
# until the watch reads the new one.
exec 9>/var/lock/wq_forge.lock
if ! flock -n 9; then echo "forge loop already running; exiting"; exit 0; fi
exec 8>&-

cd /opt/wq || exit 1
LOG=/opt/wq/state/forge/loop.log
STOP=/opt/wq/state/STOP_FORGE
ROUNDS=${ROUNDS:-400}      # ROUNDS=1 for the canary
mkdir -p /opt/wq/state/forge
PY=/opt/wq/venv/bin/python
# D58's back-off after a runner ended by a signal (see the round below). 900 s is a CHOICE, not a measurement: it
# holds a runner killed at plan time to about four attempts an hour, where with no pause the next plan -- which reads
# the whole journal again -- started at once. A one-round caller (ROUNDS=1) never sleeps, as after an exit 2.
SIGNAL_BACKOFF_S=900

# D50 (Khoa, 2026-09-23): N and FORGE_ARGS live in /opt/wq/forge.env, which tools/deploy.py ships (PLAN), smokes
# and rolls back with the code, so turning the pass-first branch on or off is a deploy (round 3 S5). The file wins
# over the unit's Environment= for the standing loop, whether or not the unit's one-time EnvironmentFile= edit has
# been made (vps/systemd_wq-forge.service). ONE EXCEPTION, found while building D50: a one-round invocation
# (ROUNDS=1) keeps the N and FORGE_ARGS its caller set -- vps/c11_run.sh, pow_run.sh, llm_formula_run.sh and
# forge/search.py each run a targeted round with their own `--plan` or recipe (read 2026-09-23), and sourcing the
# file over them would have run production's arguments instead. A value the caller did not set comes from the file.
# No file: the environment's values are used, and a loud line says so.
load_forge_env() {
  local f=$1 had_n=${N+1} had_args=${FORGE_ARGS+1} env_n=${N-} env_args=${FORGE_ARGS-}
  if [ ! -f "$f" ]; then
    echo "=== D50: $f is ABSENT -- running on the environment's N=${N-<unset>} FORGE_ARGS=${FORGE_ARGS-<unset>} (the unit's Environment=), not on a shipped file ===" | tee -a "$LOG"
    return 0
  fi
  if ! . "$f"; then
    N=$env_n FORGE_ARGS=$env_args
    [ -n "$had_n" ] || unset N
    [ -n "$had_args" ] || unset FORGE_ARGS
    echo "=== D50: $f did not source cleanly -- running on the environment's N=${N-<unset>} FORGE_ARGS=${FORGE_ARGS-<unset>} ===" | tee -a "$LOG"
    return 0
  fi
  if [ "$ROUNDS" = 1 ]; then
    if [ -n "$had_n" ]; then N=$env_n; fi
    if [ -n "$had_args" ]; then FORGE_ARGS=$env_args; fi
  fi
  echo "=== D50: N=$N FORGE_ARGS=$FORGE_ARGS (ROUNDS=$ROUNDS; $f read; the environment had N=${env_n:-<unset>} FORGE_ARGS=${env_args:-<unset>}) ===" | tee -a "$LOG"
}

# Round 3 S4: the gate ran with 2>/dev/null and printed "auth dead" on ANY non-zero exit, so an import crash read as
# an auth outage (and the watch then called the silence "not a crash"). Now the check's exit says which: 0 go on;
# 1 its own verdict (not 200, or under 40 min left) -> "auth dead"; 4 an import failed -> "auth gate crashed at
# import" (code: D43's crash-before-dispatch class); any other exit -> "auth gate crashed (exit N)" (the session
# step raised, or the interpreter died). A crash prints its last line in the marker and the whole output after it.
# The loop's control flow is unchanged: any non-zero exit mints (the hourly law lives in mint_link) and sleeps.
auth_gate() {
  local r=$1 out rc last
  # Alive AND at least 40 minutes left (Khoa's tick 2026-09-07 14:10). A round is ~35 min; one that
  # starts later than that spends its simulations on a session that dies before they are read --
  # 96 AUTH-FAIL rows and 15 orphan parents by 14:00 on 09-07. An unreadable cookie jar (None)
  # falls back to the liveness answer alone.
  out=$($PY -c "
import sys, traceback
sys.path.insert(0, 'tools')
try:
    import layered_sim as LS, mint_link as M
except Exception:
    traceback.print_exc()
    sys.exit(4)
try:
    s = LS.session()
    r = s.get(LS.API + '/users/self', timeout=25)
    left = M.session_left_s()
except Exception:
    traceback.print_exc()
    sys.exit(5)
sys.exit(0 if r.status_code == 200 and (left is None or left >= 2400) else 1)
" 2>&1)
  rc=$?
  [ "$rc" -eq 0 ] && return 0
  if [ "$rc" -eq 1 ]; then
    echo "=== auth dead or under 40 min before round $r, at $(date +%s), $(date) ===" | tee -a "$LOG"
    return 1
  fi
  last=$(printf '%s\n' "$out" | grep -v '^[[:space:]]*$' | tail -n 1 | cut -c1-200)
  if [ "$rc" -eq 4 ]; then
    echo "=== auth gate crashed at import before round $r, at $(date +%s), $(date): $last ===" | tee -a "$LOG"
  else
    echo "=== auth gate crashed (exit $rc) before round $r, at $(date +%s), $(date): $last ===" | tee -a "$LOG"
  fi
  printf '%s\n' "$out" >> "$LOG"
  return 1
}

# Round 3 S9: the reset sleep used `date -d "today 11:05"` in the host's zone (+07), which is 00:05 America/New_York
# only while New York is on daylight time. zoneinfo: 00:00 ET is 11:00 +07 on 09-23 and 12:00 +07 on 11-02, so from
# 2026-11-01 a quota-spent loop would wake an hour before the reset. submit.quota_day, submit_budget and benchmark's
# ET all use America/New_York; so does this now: the first 00:05 New York time strictly after $1 (epoch seconds),
# whatever the host's TZ. Five minutes after the reset, as 11:05 +07 was in summer.
next_reset() {
  $PY -c '
import datetime, sys, zoneinfo
ny = zoneinfo.ZoneInfo("America/New_York")
now = int(sys.argv[1])
day = datetime.datetime.fromtimestamp(now, ny).date()
for k in (0, 1):
    t = int(datetime.datetime.combine(day + datetime.timedelta(days=k), datetime.time(0, 5), tzinfo=ny).timestamp())
    if t > now:
        print(t)
        break
' "$1"
}

# Seconds to sleep from $1 until next_reset; an hour if the reset cannot be computed (the old fallback).
quota_sleep() {
  local now=$1 reset
  reset=$(next_reset "$now")
  case "$reset" in ''|*[!0-9]*) reset=$((now + 3600)) ;; esac
  echo $((reset - now))
}

load_forge_env /opt/wq/forge.env
N=${N:-300}

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

  if ! auth_gate "$r"; then
    # The hourly link law lives inside mint_link/outbox; asking is free while the wall is up.
    $PY tools/mint_link.py --quiet >> "$LOG" 2>&1 9>&- || true
    sleep 300 9>&-
    continue
  fi

  $PY tools/record_adjudication.py >> "$LOG" 2>&1 9>&-
  echo "=== step record_adjudication exit $?, at $(date +%s) ===" >> "$LOG"
  # THE PLATFORM'S OWN CELL COUNTER, refreshed before every round (one GET). The cached file had
  # stood at 2026-09-04 10:20 while two submissions moved USA/d1 Short Interest 0 -> 2; the planner
  # was still aiming at a need of 3. forge/offline/refresh_cells.py fails closed (file untouched).
  timeout 120 $PY forge/offline/refresh_cells.py >> "$LOG" 2>&1 9>&-
  echo "=== step refresh_cells exit $?, at $(date +%s) ===" >> "$LOG"
  SEED=$(date +%s)
  echo "=== forge round, seed $SEED, N=$N, $(date) ===" | tee -a "$LOG"
  # FORGE_ARGS: extra runner flags for a targeted round (e.g. --cells "GLB/d1 Fundamental" --only x,y)
  $PY -u forge/runner.py -n "$N" --seed "$SEED" --live --concurrency 9 --children 10 $FORGE_ARGS 9>&- >> "$LOG" 2>&1
  RC=$?
  echo "=== round exit $RC at $(date) ===" >> "$LOG"
  if [ "$RC" -ge 128 ]; then
    # D58 (Khoa, 2026-09-24; round 4 S4): a runner ended by a signal (exit 128+N; 137 is SIGKILL, the OOM killer's)
    # used to fall through to recover_orphans, harvest, the probe and submit -- each of which reads the journal again
    # -- and the next round started with no pause. Now this round's steps are skipped and the loop backs off; the next
    # round's recover_orphans fetches whatever the killed runner had dispatched. What this does NOT cover (EX-ANTE,
    # systemd.service(5) OOMPolicy=, not observed): with the host's OOMPolicy=stop (read 2026-09-24), an OOM kill
    # inside wq-forge makes systemd stop the whole unit, this script included, and Restart=always starts it again
    # after RestartSec=60; this branch runs only when the loop outlives the kill.
    echo "=== runner ended by signal $((RC - 128)) (exit $RC): this round's steps skipped; backing off ${SIGNAL_BACKOFF_S}s (D58) ===" | tee -a "$LOG"
    echo "=== round end, seed $SEED, at $(date +%s) ===" >> "$LOG"
    if [ "$ROUNDS" -gt 1 ]; then sleep "$SIGNAL_BACKOFF_S" 9>&-; fi
    continue
  fi
  if [ "$RC" -eq 2 ]; then
    # Round 3 S2: the runner exits 2 for "nothing to simulate: the library is exhausted", and argparse ALSO exits 2
    # on an argument it refuses. Every 2 used to be logged as exhausted; now only the runner's own words say so.
    if sed -n "/=== forge round, seed $SEED,/,\$p" "$LOG" | grep -q "library is exhausted"; then
      echo "=== library exhausted for every reachable cell (m13 case) ===" | tee -a "$LOG"
    else
      echo "=== runner exit 2 WITHOUT the exhausted-library message (argparse exits 2 on arguments it refuses) ===" | tee -a "$LOG"
    fi
    echo "=== round end, seed $SEED, at $(date +%s) ===" >> "$LOG"
    # A one-round invocation (ROUNDS=1, the search driver) must return at once; only the standing
    # loop sleeps for the hour. Measured 2026-09-04 17:08: R8 found no candidates and the driver
    # sat inside this sleep while the session ran out.
    if [ "$ROUNDS" -gt 1 ]; then sleep 3600 9>&-; fi
    continue
  fi

  # Children the runner could not read (a session that died mid-round, a stall) are fetched back
  # from the platform and attributed by plan file, so the allocator and the DSR pools see every
  # simulation that was paid for (Khoa's tick 2026-09-07 14:10). Cheap when there is nothing.
  timeout 900 $PY forge/offline/recover_orphans.py --limit 30 >> "$LOG" 2>&1 9>&-
  echo "=== step recover_orphans exit $?, seed $SEED ===" >> "$LOG"

  # Score what just landed (PnL recordsets: one GET each, computed on demand).
  timeout 1800 $PY -u forge/harvest.py --limit 400 >> "$LOG" 2>&1 9>&-
  echo "=== step harvest exit $?, seed $SEED ===" >> "$LOG"

  # Correlations for the candidates, in the background, singleton. Trigger, +120 s, read once.
  (
    flock -n 8 || { echo "=== probe (bg) skipped, seed $SEED: another probe holds its lock ===" >> "$LOG"; exit 0; }
    timeout 1500 $PY -u forge/probe.py --limit 60 --wait 120 >> "$LOG" 2>&1 9>&-
    echo "=== probe (bg) done, seed $SEED, exit $?, $(date) ===" >> "$LOG"
  ) 8>/var/lock/wq_forge_probe.lock 9>&- &

  # Submit whatever is eligible. The submitter enforces every gate itself (C21) and refuses alone.
  SUBOUT=$($PY forge/submit.py --submit --cap 4 2>&1 9>&-)
  SUBRC=$?
  echo "$SUBOUT" >> "$LOG"
  echo "=== step submit exit $SUBRC, seed $SEED ===" >> "$LOG"
  if echo "$SUBOUT" | grep -q "^HTTP 20"; then
    timeout 120 $PY forge/offline/refresh_cells.py >> "$LOG" 2>&1 9>&- || true
  fi
  echo "=== round end, seed $SEED, at $(date +%s) ===" >> "$LOG"

  # Only THIS round's output may say the quota is spent. MEASURED 2026-09-07 11:30: the 01:53
  # "DAILY_SIMULATION_LIMIT_EXCEEDED" line was still inside the last 400 lines after the first
  # round of the new day, and the loop slept 84,880 s with a live session and a fresh quota.
  if sed -n "/=== forge round, seed $SEED,/,\$p" "$LOG" | grep -q "DAILY_SIMULATION_LIMIT_EXCEEDED"; then
    SLEEP=$(quota_sleep "$(date +%s)")
    # draw5_build release MINOR 7: this line named 00:05 New York even when quota_sleep fell back to an hour
    echo "=== daily quota spent; sleeping ${SLEEP}s: to 00:05 America/New_York (the quota day ends 00:00 ET), or 3600 s when that time cannot be computed ===" | tee -a "$LOG"
    sleep "$SLEEP" 9>&-
    continue
  fi
done
echo "=== forge loop ended $(date) ===" | tee -a "$LOG"
