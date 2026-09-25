#!/bin/bash
# THE FRAMES LOOP, ON THE VPS (CLAUDE.md RULE 1). F5 (Khoa, 2026-09-24): the frame library REPLACES the forge loop and
# the quota goes to this loop (docs/frames/00_decisions.md F5-F9). Run by vps/wq-frames.service; tested by
# framelib/tests/test_loop_driver.py (bash, with python, flock, timeout, sleep, pgrep, systemctl and ssh stubbed).
#
# ONE LOOP AT A TIME. It holds /var/lock/wq_forge.lock for its whole life, the lock vps/forge_loop.sh holds, so this
# loop and the retired forge loop can never run together, whichever starts first; a second copy of either exits.
#   * The lock fd is LEFT OPEN in every child (forge_loop.sh closes it with 9>&-; this loop does not). EX-ANTE,
#     flock(2): the lock belongs to the open file description, which every child that inherited fd 9 shares, and it
#     is released when the last of them closes it. So a dispatcher that outlives a killed loop keeps the lock, and no
#     second loop starts while it is still spending. Tested with the loop killed by SIGKILL mid-dispatch.
#   * It refuses to start beside the climb loop (its lock, the check forge_loop.sh makes) and a round waits while
#     experiments/frames/frames_round.sh runs: that driver (FRAMES-R2, frames-r2.timer 2026-09-25 11:05 +07) does NOT
#     take this lock (read 2026-09-24). The wait covers a driver that is already running when a round would start; a
#     driver that starts during a round is not seen -- install this loop after FRAMES-R2 (vps/wq-frames.service).
#   * It never starts, stops or reads wq-forge: no systemctl and no ssh anywhere in this file.
#
# EACH ROUND, in this order. Every step's output goes to $LOG, then a line "=== step NAME exit RC, seed S, at T ===".
#   0. STOP file (state/STOP_FRAMES): consumed at the round boundary and the loop ends, as forge_loop.sh does. Under
#      Restart=always systemd starts it again after RestartSec, so an operator who wants it down stops the unit.
#   1. auth: forge.search.wait_for_auth (a session with more than 900 s left), up to AUTH_WAIT_S per attempt.
#   2. once per ET day: GET /data-sets for USA/TOP3000/d1 -> state/frames/datasets_ok.json, which
#      framelib/loop/availability.py reads. Written whole (tmp + rename) or not at all.
#   3. python -m framelib.loop.evidence --update
#   4. once per ET day: python -m framelib.loop.newframes --n 25                                    (F8)
#   5. python -m framelib.loop.plan --n 300 --seed <seed> --out state/frames/loop_plans/<seed>.json
#      --seed: the round's seed, so the log's header, the plan file, meta.round_seed (the evidence ledger's round key)
#      and the dispatcher's --seed are one number (without it the planner takes its own epoch second).
#      NOT state/frames/plans/: that directory is framelib/loop/evidence.py's archive, and evidence json.loads EVERY
#      *.json in it with no guard (read 2026-09-25), so one truncated or non-plan file there -- a planner killed while
#      writing -- would fail every later evidence update, and with it every later round. Tested with the real module.
#   6. framelib/experiments/vps/dispatch_round.py --abc <plan> --seed <seed>
#        --journal state/layered/runs/frames_loop.jsonl --experiment FRAMES-LOOP --live           (spends quota)
#   7. forge/probe.py --alphas <every D24 pass in the loop journal, newest first> (the probe skips alphas that
#      already carry both correlations), under the probe's own lock
#   8. python -m framelib.loop.submit --submit        (F9; the only code that POSTs a submission, and it gates itself)
#   9. one summary line: "=== frames round end, seed S: ... ===", with "posted N" read from the submitter's own
#      "posted N" line in this round's output ("posted ?" when it printed none).
# "ET day" is America/New_York's date, the platform's quota day, whatever the host's zone.
#
# FAIL CLOSED. Nothing is dispatched unless, in this round, the session was live (1), today's datasets_ok.json was
# written (2, retried every round until it is), the evidence update exited 0 or 3 (3), and the planner exited 0 and
# wrote a readable, non-empty plan (5). Evidence's exit 3 means, by its own docstring and code (read 2026-09-25), that
# the ledger WAS written and a library entry refused its evidence.live block; the planner reads the ledger, not that
# block (the block feeds schema.py's `validated` status, a status change that needs Khoa's tick), so the round goes on
# with a marker instead of stopping every round until an entry is fixed. A DESIGN CHOICE, from those reads.
# A failed newframes (4) does not stop the round -- it only adds candidates -- and is
# retried on the next round, since its day stamp is written on success only. After dispatch (6), a failure of any
# step lets the next step run, as forge_loop.sh does (the submitter enforces every gate itself); a step ENDED BY A
# SIGNAL (exit >= 128; 137 is SIGKILL, the OOM killer's) ends the round there, as D58 does for the forge runner.
#
# BACK-OFFS (CHOICES, not measurements):
#   BACKOFF_S=900 after a step ended by a signal, a failed pre-dispatch step, a dispatcher that exited non-zero, or a
#     round that journalled nothing: D58's value in forge_loop.sh. Without it a planner or dispatcher that fails fast
#     would re-run at once, forever.
#   EMPTY_PLAN_S=3600 after an empty plan: forge_loop.sh's value for "the library is exhausted".
#   BUSY_WAIT_S=300 while frames_round.sh runs: forge_loop.sh's auth-dead sleep.
#   A one-round caller (ROUNDS=1, the canary) never sleeps, as in forge_loop.sh.
#
# THE DAILY LIMIT. When THIS round's dispatcher output (only its bytes of the log, not the whole log, and not the
# probe's or the submitter's) carries DAILY_SIMULATION_LIMIT_EXCEEDED -- tools/layered_sim.py prints the 429 body
# when it stops -- the loop stops spending and sleeps to 00:05 America/New_York: the platform's day ends at 00:00 ET
# (tools/daily_budget.py, measured 2026-08-01), and the five minutes are round 3 S9's margin, reused with its function
# (next_reset below, copied from vps/forge_loop.sh). Host time is never used for it. Probe and submit still run that
# round: neither spends simulations. WHY NOT 00:00 SHARP (the margin is a CHOICE; what it guards is read from the code,
# EX-ANTE): quota_sleep sleeps to the first reset strictly AFTER now, so a round that met the limit a few seconds after
# a 00:00:00 wake -- a reset the platform applied late, which nobody has measured either way -- would sleep a whole
# further day. The five minutes cost no quota: the quota is a count per ET day, not a rate.
#
# Paths can be moved for the tests only (FRAMES_ROOT, FRAMES_PY, FRAMES_LOCK, FRAMES_CLIMB_LOCK, FRAMES_PROBE_LOCK);
# the unit sets none of them.
ROOT=${FRAMES_ROOT:-/opt/wq}
LOCK=${FRAMES_LOCK:-/var/lock/wq_forge.lock}
CLIMB_LOCK=${FRAMES_CLIMB_LOCK:-/var/lock/wq_climb.lock}
PROBE_LOCK=${FRAMES_PROBE_LOCK:-/var/lock/wq_forge_probe.lock}
PY=${FRAMES_PY:-$ROOT/venv/bin/python}

exec 9>"$LOCK"
if ! flock -n 9; then echo "$LOCK is held (the frames loop or the retired forge loop is running); exiting"; exit 0; fi

cd "$ROOT" || exit 1
LOG=$ROOT/state/frames/loop.log
STOP=$ROOT/state/STOP_FRAMES
JOURNAL=$ROOT/state/layered/runs/frames_loop.jsonl
DSOK=$ROOT/state/frames/datasets_ok.json
DAY_DATASETS=$ROOT/state/frames/loop_day.datasets
DAY_NEWFRAMES=$ROOT/state/frames/loop_day.newframes
PLANS=$ROOT/state/frames/loop_plans      # never state/frames/plans (evidence's archive; step 5 above)
DISPATCH=$ROOT/framelib/experiments/vps/dispatch_round.py
ROUNDS=${ROUNDS:-400}      # the unit sets 100000; ROUNDS=1 for the canary
N=300
AUTH_WAIT_S=1800
STEP_TIMEOUT_S=1800
BACKOFF_S=900
EMPTY_PLAN_S=3600
BUSY_WAIT_S=300
mkdir -p "$ROOT/state/frames" "$PLANS" "$(dirname "$JOURNAL")"

if flock -n "$CLIMB_LOCK" true 2>/dev/null; then :; else
  echo "the climb loop holds $CLIMB_LOCK -- refusing to run two spenders; exiting" | tee -a "$LOG"
  exit 0
fi

# Round 3 S9, copied from vps/forge_loop.sh: the first 00:05 New York time strictly after $1 (epoch seconds).
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

# Seconds to sleep from $1 until next_reset; an hour if the reset cannot be computed (forge_loop.sh's fallback).
quota_sleep() {
  local now=$1 reset
  reset=$(next_reset "$now")
  case "$reset" in ''|*[!0-9]*) reset=$((now + 3600)) ;; esac
  echo $((reset - now))
}

# The ET day with zoneinfo, which fails loudly without tzdata; `TZ=America/New_York date` silently prints the UTC
# date then (measured on the Mac with an unknown zone). Empty output = no day = no round.
et_day() { $PY -c 'import datetime, zoneinfo; print(datetime.datetime.now(zoneinfo.ZoneInfo("America/New_York")).date())'; }
log_size() { if [ -f "$1" ]; then wc -c < "$1" | tr -d ' '; else echo 0; fi; }
# log_slice FROM TO: the bytes of $LOG between two of its sizes -- one step's output, nothing before or after it.
log_slice() { if [ "$2" -gt "$1" ]; then tail -c +$(($1 + 1)) "$LOG" | head -c $(($2 - $1)); fi; }

# run_step NAME CMD...: the command's output to $LOG, then the step's marker; returns the command's exit.
run_step() {
  local name=$1 rc
  shift
  "$@" >> "$LOG" 2>&1
  rc=$?
  echo "=== step $name exit $rc, seed ${SEED:-none}, at $(date +%s) ===" >> "$LOG"
  return $rc
}

backoff() { if [ "$ROUNDS" -gt 1 ]; then sleep "$1"; fi; }

# ok_or_end NAME RC: 0 when RC is 0; otherwise the round ends here -- logged, backed off -- and 1.
ok_or_end() {
  [ "$2" -eq 0 ] && return 0
  if [ "$2" -ge 128 ]; then
    echo "=== step $1 ended by signal $(($2 - 128)) (exit $2): round $r ends here; backing off ${BACKOFF_S}s ===" | tee -a "$LOG"
  else
    echo "=== step $1 failed (exit $2): round $r ends here; backing off ${BACKOFF_S}s ===" | tee -a "$LOG"
  fi
  echo "=== frames round end, seed ${SEED:-none}: ended at step $1, at $(date +%s) ===" | tee -a "$LOG"
  backoff "$BACKOFF_S"
  return 1
}

# forge.search.wait_for_auth: exit 0 live, 1 no live session within AUTH_WAIT_S, 4 the import failed.
wait_auth() {
  "$PY" - auth "$ROOT" "$AUTH_WAIT_S" <<'PY'
import sys
root, max_s = sys.argv[2], float(sys.argv[3])
sys.path[:0] = [root, root + "/tools"]
try:
    from forge import search as S
except Exception:
    import traceback
    traceback.print_exc()
    sys.exit(4)
sys.exit(0 if S.wait_for_auth(max_s=max_s, out=lambda *a: None) else 1)
PY
}

# GET /data-sets for USA/TOP3000/d1, every page; $DSOK is replaced only when every id of the reported count was read.
refresh_datasets() {
  "$PY" - datasets "$ROOT" "$DSOK" <<'PY'
import json, os, sys, time
root, path = sys.argv[2], sys.argv[3]
sys.path[:0] = [root, os.path.join(root, "tools")]
import layered_sim as LS
s = LS.session()
ids, off, count = [], 0, 0
while True:
    for attempt in range(5):
        r = s.get(LS.API + "/data-sets", params={"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
                                                 "delay": 1, "limit": 50, "offset": off}, timeout=60)
        if r.status_code != 429:
            break
        time.sleep(min(float(r.headers.get("Retry-After") or 5), 60.0) + 1.0)
    if r.status_code != 200:
        print("datasets: GET /data-sets offset %d answered %d; %s left as it was" % (off, r.status_code, path))
        sys.exit(1)
    j = r.json()
    page = [d.get("id") for d in (j.get("results") or [])]
    count = int(j.get("count") or 0)
    ids += page
    off += len(page)
    if not page or off >= count:
        break
    time.sleep(1.1)
if not count or len(ids) != count or len(set(ids)) != count or not all(isinstance(i, str) and i for i in ids):
    print("datasets: %d id(s) read against a count of %d; %s left as it was" % (len(ids), count, path))
    sys.exit(1)
with open(path + ".tmp", "w") as fh:
    json.dump(sorted(ids), fh)
os.replace(path + ".tmp", path)
print("datasets: %d datasets offered for USA/TOP3000/d1 -> %s" % (count, path))
PY
}

# plan_size PLAN: the number of constructions, or nothing when the file is not a plan.
plan_size() {
  "$PY" - plan "$1" <<'PY' 2>> "$LOG"
import json, sys
p = json.load(open(sys.argv[2]))
c = p.get("constructions") if isinstance(p, dict) else None
if isinstance(c, list):
    print(len(c))
PY
}

# journal_read ids: every alpha of the loop journal whose last row clears the 7 binding checks (D24), newest first.
# journal_read counts OFFSET: this round's rows -- the bytes appended after OFFSET -- as one phrase.
# D24 and y08 are framelib/experiments/analyse_round.outcome, the rounds' own read-out.
journal_read() {
  "$PY" - journal "$ROOT" "$JOURNAL" "$1" "${2:-0}" <<'PY' 2>> "$LOG"
import json, os, sys
root, path, mode, off = sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
sys.path.insert(0, root)
from framelib.experiments.analyse_round import outcome
n = {"lines": 0, "rows": 0, "scored": 0, "y08": 0, "d24": 0}
last = {}
if os.path.exists(path):
    with open(path, "rb") as fh:
        fh.seek(off if mode == "counts" else 0)
        for i, line in enumerate(fh):
            n["lines"] += 1
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict) or r.get("status") in (None, "PARENT-POSTED"):
                continue
            o = outcome(r)
            n["rows"] += 1
            for k in ("scored", "y08", "d24"):
                n[k] += int(o[k])
            if r.get("alpha"):
                last[r["alpha"]] = (i, o["d24"])
if mode == "ids":
    print(",".join(a for a, (i, d) in sorted(last.items(), key=lambda kv: -kv[1][0]) if d))
else:
    print("journalled %(lines)d line(s): %(rows)d row(s), %(scored)d scored, y08 %(y08)d, D24 %(d24)d" % n)
PY
}

for r in $(seq 1 "$ROUNDS"); do
  SEED=
  if [ -f "$STOP" ]; then
    rm -f "$STOP"
    echo "=== STOP file present (consumed); ending, at $(date +%s) ===" | tee -a "$LOG"
    break
  fi
  if pgrep -f 'frames_round[.]sh' >/dev/null 2>&1; then
    echo "=== frames_round.sh is running and does not take $LOCK: round $r waits ${BUSY_WAIT_S}s, at $(date +%s) ===" | tee -a "$LOG"
    backoff "$BUSY_WAIT_S"
    continue
  fi

  wait_auth >> "$LOG" 2>&1
  RC=$?
  if [ "$RC" -eq 1 ]; then
    echo "=== no live session within ${AUTH_WAIT_S}s before round $r (forge.search.wait_for_auth), at $(date +%s) ===" | tee -a "$LOG"
    continue
  elif [ "$RC" -ne 0 ]; then
    echo "=== auth wait crashed (exit $RC) before round $r; backing off ${BACKOFF_S}s, at $(date +%s) ===" | tee -a "$LOG"
    backoff "$BACKOFF_S"
    continue
  fi

  DAY=$(et_day)
  case "$DAY" in [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;; *)
    echo "=== the ET day could not be computed ('$DAY') before round $r; backing off ${BACKOFF_S}s ===" | tee -a "$LOG"
    backoff "$BACKOFF_S"
    continue ;;
  esac
  SEED=$(date +%s)
  echo "=== frames round $r, seed $SEED, ET day $DAY, N=$N, at $SEED, $(date) ===" | tee -a "$LOG"

  if [ "$(cat "$DAY_DATASETS" 2>/dev/null)" != "$DAY" ]; then
    run_step datasets refresh_datasets
    ok_or_end datasets $? || continue
    echo "$DAY" > "$DAY_DATASETS"
  fi

  run_step evidence timeout "$STEP_TIMEOUT_S" "$PY" -m framelib.loop.evidence --update
  RC=$?
  if [ "$RC" -eq 3 ]; then
    echo "=== evidence exit 3: the ledger was written; a library entry refused its evidence.live block (named above); the round goes on ===" | tee -a "$LOG"
  else
    ok_or_end evidence "$RC" || continue
  fi

  if [ "$(cat "$DAY_NEWFRAMES" 2>/dev/null)" != "$DAY" ]; then
    run_step newframes timeout "$STEP_TIMEOUT_S" "$PY" -m framelib.loop.newframes --n 25
    RC=$?
    if [ "$RC" -eq 0 ]; then
      echo "$DAY" > "$DAY_NEWFRAMES"
    elif [ "$RC" -ge 128 ]; then
      ok_or_end newframes "$RC"
      continue
    else
      echo "=== newframes failed (exit $RC): the round goes on without today's new frames; retried next round ===" | tee -a "$LOG"
    fi
  fi

  PLAN=$PLANS/$SEED.json
  run_step plan timeout "$STEP_TIMEOUT_S" "$PY" -m framelib.loop.plan --n "$N" --seed "$SEED" --out "$PLAN"
  ok_or_end plan $? || continue
  PLANNED=$(plan_size "$PLAN")
  case "$PLANNED" in ''|*[!0-9]*) ok_or_end "plan (no readable plan at $PLAN)" 1; continue ;; esac
  if [ "$PLANNED" -eq 0 ]; then
    echo "=== plan empty: nothing to dispatch; sleeping ${EMPTY_PLAN_S}s ===" | tee -a "$LOG"
    echo "=== frames round end, seed $SEED: empty plan, at $(date +%s) ===" | tee -a "$LOG"
    backoff "$EMPTY_PLAN_S"
    continue
  fi

  J0=$(log_size "$JOURNAL")
  D0=$(log_size "$LOG")
  "$PY" -u "$DISPATCH" --abc "$PLAN" --seed "$SEED" --journal "$JOURNAL" --experiment FRAMES-LOOP --live >> "$LOG" 2>&1
  DRC=$?
  D1=$(log_size "$LOG")
  echo "=== step dispatch exit $DRC, seed $SEED, at $(date +%s) ===" >> "$LOG"
  if [ "$DRC" -ge 128 ]; then ok_or_end dispatch "$DRC"; continue; fi
  DAILY=no
  if log_slice "$D0" "$D1" | grep -q DAILY_SIMULATION_LIMIT_EXCEEDED; then DAILY=yes; fi

  IDS=$(journal_read ids)
  NIDS=0
  PRC=none
  if [ -n "$IDS" ]; then
    NIDS=$(printf '%s\n' "$IDS" | tr ',' '\n' | grep -c .)
    run_step probe flock -w 1800 "$PROBE_LOCK" timeout 1500 "$PY" -u forge/probe.py --alphas "$IDS" --limit 60 --wait 120
    PRC=$?
    if [ "$PRC" -ge 128 ]; then ok_or_end probe "$PRC"; continue; fi
  fi

  S0=$(log_size "$LOG")
  run_step submit "$PY" -m framelib.loop.submit --submit
  SRC=$?
  POSTED=$(log_slice "$S0" "$(log_size "$LOG")" | sed -n 's/^posted \([0-9][0-9]*\).*/\1/p' | tail -n 1)
  COUNTS=$(journal_read counts "$J0")
  echo "=== frames round end, seed $SEED: plan $PLANNED, dispatch exit $DRC, ${COUNTS:-journal unreadable}; probe exit $PRC ($NIDS D24 id(s)); submit exit $SRC, posted ${POSTED:-?}; daily limit $DAILY, at $(date +%s) ===" | tee -a "$LOG"
  if [ "$SRC" -ge 128 ]; then
    echo "=== step submit ended by signal $((SRC - 128)) (exit $SRC); backing off ${BACKOFF_S}s ===" | tee -a "$LOG"
    backoff "$BACKOFF_S"
    continue
  fi

  if [ "$DAILY" = yes ]; then
    SLEEP=$(quota_sleep "$(date +%s)")
    echo "=== daily simulation limit reported by this round's dispatch; sleeping ${SLEEP}s: to 00:05 America/New_York (the quota day ends 00:00 ET), or 3600 s when that time cannot be computed ===" | tee -a "$LOG"
    backoff "$SLEEP"
    continue
  fi
  if [ "$DRC" -ne 0 ] || [ "$(log_size "$JOURNAL")" = "$J0" ]; then
    echo "=== dispatch exit $DRC, $(( $(log_size "$JOURNAL") - J0 )) journal byte(s) this round: backing off ${BACKOFF_S}s ===" | tee -a "$LOG"
    backoff "$BACKOFF_S"
  fi
done
echo "=== frames loop ended $(date) ===" | tee -a "$LOG"
