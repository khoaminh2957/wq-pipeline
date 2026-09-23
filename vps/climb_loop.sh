#!/bin/bash
# The closed loop, ON THE VPS. CLAUDE.md RULE 1: simulations never run on the MacBook.
# One copy only -- flock exists on Linux, unlike macOS.
exec 9>/var/lock/wq_climb.lock
if ! flock -n 9; then echo "climb loop already running; exiting"; exit 0; fi
# Drop the ARMING lock inherited from arm_climb.sh. It leaks in through fd 8 and keeps
# reading as held long after the arming process is gone.
exec 8>&-

# THE SECOND WITNESS.
#
# The lock says a process holds it. It cannot say that process is still working -- a hang keeps the
# descriptor held, so a hung loop and a healthy one look identical from /proc/locks. loopstate.py
# has carried write_beat() and an ORPHAN_LOCK state since it was written; nothing ever called it,
# so the watchdog printed "second_witness ABSENT" every 60 s and the hang case stayed undetectable.
#
# Beat every 30 s in the background, carrying THIS shell's pid and start time so the watchdog can
# tell "the lock is held" from "the holder still exists". 9>&- so the beater cannot itself hold the
# climb lock, and the trap kills it with the loop.
LOOP_PID=$$
( while kill -0 "$LOOP_PID" 2>/dev/null; do
    python3 - "$LOOP_PID" <<'BEATEOF' 9>&- 2>/dev/null
import sys, os
sys.path.insert(0, "/opt/wq/tools")
import loopstate as LS
pid = int(sys.argv[1])
try:
    ino = os.stat("/var/lock/wq_climb.lock").st_ino
except OSError:
    ino = None
try:
    with open("/proc/%d/stat" % pid) as fh:
        raw = fh.read()
    st = int(raw[raw.rindex(")") + 1:].split()[19])
except (OSError, ValueError, IndexError):
    st = None
beat = LS.write_beat(lock_ino=ino, phase=os.environ.get("WQ_PHASE") or "loop")
# write_beat records ITS OWN pid; the watchdog needs the LOOP's, so correct it in place.
import json, tempfile
path = LS.DEFAULT_BEAT
beat["pid"], beat["pid_starttime"] = pid, st
d = os.path.dirname(path)
fd, tmp = tempfile.mkstemp(dir=d, prefix=".beat_")
with os.fdopen(fd, "w") as fh:
    json.dump(beat, fh)
os.replace(tmp, path)
BEATEOF
    sleep 30 9>&-
  done ) 9>&- &
BEATER_PID=$!
trap 'kill $BEATER_PID 2>/dev/null' EXIT INT TERM

cd /opt/wq || exit 1
LOG=/opt/wq/state/climb_loop.log
STOP=/opt/wq/state/STOP_CLIMB
# 100 A ROUND, Khoa 2026-08-15. Was 300. A cycle still runs many rounds until it stalls or dead-ends;
# the rounds are simply three times smaller, so the baseline turns over faster and a dead branch is
# abandoned after 100 simulations instead of 300.
# Khoa, 2026-08-17: 200 candidates a round, up from 100.
#
# At ~25 min a round that is ~11,500 simulations a day against a hard 5,000/day platform cap, so the
# cap binds after about 25 rounds (~10.4 h) and the loop then sleeps to the 11:00 reset. Intended: a
# bigger draw buys a better argmax, and the quota was already binding at 100. The
# DAILY_SIMULATION_LIMIT_EXCEEDED guard below reads a 400-line window, wide enough for the ~194-line
# block a full round writes.
# Khoa, 2026-08-29: 300 per growth round (seed round is SEED_N=350 in climb.py). A probe
# costs ~30 min regardless of round size, so a bigger round is a better sim:wait ratio.
N=${N:-300}

for r in $(seq 1 200); do
  # THE STOP FILE IS CONSUMED WHEN IT IS HONOURED. Leaving it on disk is how a loop gets killed by
  # a request nobody remembers making: this file has ended the loop TWICE in one evening, both times
  # left behind by a restart command whose ssh died before its own `rm` ran. The loop was then
  # reported as running, from a `ps` read taken before the file appeared.
  if [ -f "$STOP" ]; then
    rm -f "$STOP"
    echo "STOP file present (consumed); ending" | tee -a "$LOG"
    python3 tools/notify.py --title "Climb loop da DUNG theo yeu cau (STOP file)" 9>&- \
    "$(python3 tools/climb.py --brief "DUNG theo STOP file" 2>&1 9>&-)" >/dev/null 2>&1
    break
  fi

  if ! python3 -c "
import sys; sys.path.insert(0,'tools')
import layered_sim as LS
s=LS.session(); r=s.get(LS.API+'/users/self', timeout=25)
sys.exit(0 if r.status_code==200 else 1)
" 2>/dev/null; then
    echo "=== auth dead before round $r, $(date) ===" | tee -a "$LOG"
    # ONE MESSAGE PER OUTAGE, NOT ONE PER RETRY. Measured 2026-08-17/18: 262 of these against
    # 8 actual links -- the operator buried in restatements of a condition he already knew,
    # while the message that needed acting on was rare. mint_link.py below still runs every
    # retry: asking for a link is the useful half and it is free while the wall is up.
    if [ ! -f /opt/wq/state/auth_notified ]; then
      touch /opt/wq/state/auth_notified
    python3 tools/notify.py --title "VPS climb dừng: auth hết hạn" 9>&- \
    "$(python3 tools/climb.py --brief "AUTH HET HAN — dang xin link moi" 2>&1 9>&-)" >/dev/null 2>&1 9>&-
    fi
    # A "loop stopped" note with no link gives the operator nothing to act on.
    # mint_link.py reads the biometric wall and refuses instead of extending it.
    python3 tools/mint_link.py --quiet >> "$LOG" 2>&1 9>&- || true
    break
  fi

  SEED=$(date +%s)
  rm -f /opt/wq/state/auth_notified
  # Auth is alive from here. Record any missing platform adjudication for POSTed alphas
  # (notify_lint's standing finding: the one real submission is ACTIVE and no file said so).
  # Idempotent and free once recorded; runs HERE so recovery depends on nothing outside this box.
  python3 tools/record_adjudication.py >> "$LOG" 2>&1 9>&- || true
  echo "=== VPS climb round, seed $SEED, $(date) ===" | tee -a "$LOG"
  python3 -u tools/layered_sim.py -n "$N" --seed "$SEED" --climb --live 9>&- \
          --concurrency 9 --children 10 >> "$LOG" 2>&1
  echo "=== round exit $? at $(date) ===" >> "$LOG"

  # EVERY ROUND REPORTS, not only the cycle boundaries. Khoa asked that every Discord message name
  # the best alpha at the moment it is sent, which only means something if messages actually arrive
  # between boundaries -- a cycle can run many rounds.
  # PER-ROUND PROGRESS IS NOT NEWS. Removed 2026-08-16: this fired every round, ~60/day,
# and with the rest projected 288 messages a day -- more than the 199 the notifier
# rebuild was built to cut. A progress ping is not one of the nine catalogue messages.
# Gems, submits, auth death, quota exhaustion, cycle boundaries and STOP all still report.
# : # (removed)

  # ---- MEASURE THE CANDIDATES. Khoa, 2026-08-14: "nếu đạt được các gem đầu thì bắt buộc phải đo
  # và restart rồi chứ tại sao ko làm v". He is right and this was the hole: tier 3 means the
  # correlation probe is now worth paying for, and nothing was paying for it -- so PROD_CORRELATION
  # and SELF_CORRELATION stayed PENDING on all 569 candidates and the pipeline could never produce
  # a gem at all. A PENDING gate is unmeasured, never passed.
  NCAND=$(python3 tools/climb.py --candidates 2>/dev/null | tail -1 9>&-)
  if [ "${NCAND:-0}" -gt 0 ] 2>/dev/null; then
    echo "=== $NCAND tier-3 candidate(s): measuring correlations, $(date) ===" | tee -a "$LOG"
    # THE FIRST GET TRIGGERS THE COMPUTATION AND RETURNS 200 WITH AN EMPTY BODY. All 12 of the
    # first probe came back that way, which is not a failure -- it is the platform starting work.
    # So the probe runs EVERY round and picks up what the previous round set going.
    #
    # DEDUPLICATED, on Khoa's instruction: 752 candidates collapse to 77 distinct signals, because
    # a hill climb grows ONE baseline and consecutive rounds differ by a single wrapper over the
    # same data. A probe on the 40th reshape answers the same question as the 1st, and this is the
    # scarcest channel in the pipeline.
    # TRIGGER, WAIT DOING NOTHING, READ. Khoa: "thử tăng thời gian chờ prod corr lên và ko làm gì
    # hết trong lúc chờ". The loop BLOCKS here on purpose -- simulating during the wait would spend
    # quota making more candidates for the channel that is already the bottleneck.
    # BACKGROUND, OVERLAPPING THE NEXT ROUND'S SIMS -- Khoa, 2026-08-29, reversing his own
    # 2026-08-14 do-nothing rule on new evidence: the two 900s waits made PROBE wall-time (232
    # min) exceed SIM wall-time (222 min) on a day that used only 34% of the sim quota, so the
    # quota-spend argument for blocking no longer holds. The wait itself is unchanged -- the
    # probe still triggers, sleeps 900s doing nothing ON ITS OWN CLOCK, then reads; only the
    # miner no longer stands still behind it. A flock keeps the probe a singleton, and the
    # rescore is chained BEHIND the read so tiers only update from landed numbers. KNOWN RISK,
    # stated not hidden: corr reads have 429'd with our bucket nearly full while sims flew
    # (mechanism unknown); unread candidates re-queue next cycle, so the failure mode is a
    # slower probe, never a lost one.
    (
      flock -n 8 || exit 0
      timeout 2400 python3 -u probe.py 60 900 >> "$LOG" 2>&1 9>&-
      python3 -u tools/climb.py --rescore >> "$LOG" 2>&1 9>&-
      echo "=== probe+rescore (nen) xong, $(date) ===" >> "$LOG"
    ) 8>/var/lock/wq_probe.lock 9>&- &
  fi

  # ---- A GEM ENDS THE CYCLE. Khoa's original spec ends a cycle on a stall; he then made explicit
  # that finding gems must also end it -- there is no reason to keep climbing past the thing the
  # climb exists to find.
  # DISTINCT ALPHAS, not lines. Counting lines made every cycle end on the same five stale gems:
  # the ledger grew because write_gems re-appended them, the loop read "grew" as "found", and seven
  # cycles spent 330 simulations each going in a circle.
  NG_NOW=$(python3 -c "
import sys; sys.path.insert(0,'tools')
import climb as C
print(len(C.ledger_alphas()))
" 2>/dev/null || echo 0)
  # LAST_NG LIVES ON DISK, NOT IN A SHELL VARIABLE.
  #
  # It was a shell variable, so it reset to 0 on every start and the comparison fired
  # UNCONDITIONALLY on the first round after ANY restart -- announcing gems that were already
  # known and, worse, calling `climb.py --reset`, which discards the baseline and starts a new
  # cycle. Measured twice on 2026-08-16: the 20:27 restart logged "rescored 111 candidate(s); 0
  # became gems" and on the very next line "GEM(S) FOUND: 7 ... cycle reset -> cycle 7, round 0,
  # no baseline", throwing away a baseline scoring 0.54.
  #
  # Restart=always turns that from a rare annoyance into a per-restart tax, so the actuator
  # installed to stop the loop dying would have been destroying its progress every time it fired.
  NG_FILE=/opt/wq/state/climb/last_ng
  LAST_NG=$(cat "$NG_FILE" 2>/dev/null || echo "")
  if [ -z "$LAST_NG" ]; then
    # FIRST EVER RUN, not "zero gems": seed from the current ledger so a restart cannot be
    # mistaken for a discovery. A missing file and a zero count are different facts.
    LAST_NG="${NG_NOW:-0}"
    mkdir -p "$(dirname "$NG_FILE")" && echo "$LAST_NG" > "$NG_FILE"
    echo "=== last_ng seeded at $LAST_NG (first run on this box) ===" | tee -a "$LOG"
  fi
  if [ "${NG_NOW:-0}" -gt "${LAST_NG:-0}" ]; then
    echo "=== GEM(S) FOUND: $NG_NOW in the ledger. Ending the cycle and resetting. ===" | tee -a "$LOG"
    python3 tools/notify.py --title "GEM: $NG_NOW trong so (CHUA nop)" 9>&- \
    "$(python3 tools/climb.py --brief "GEM MOI: $NG_NOW trong so, CHUA nop" 2>&1 9>&-)" >/dev/null 2>&1 9>&-
    # PASS THE GEM COUNT. Without it every cycle -- including the ones that found gems -- counts
    # towards the gemless streak, and the loop would eventually rotate away from a segment that was
    # working.
    python3 tools/climb.py --reset --gems "$((NG_NOW - LAST_NG))" >> "$LOG" 2>&1 9>&-
    echo "$NG_NOW" > "$NG_FILE"
    LAST_NG=$NG_NOW
  fi

  # ---- AUTO-SUBMIT, CAPPED. Khoa authorised "tự nộp hoàn toàn, có trần" (2026-08-14).
  # The submitter enforces every gate itself and refuses on its own: tier 4 with MEASURED
  # correlations under both lines, shallowest member of its lineage, lineage never spent, cap 1/day.
  # It is called WITHOUT --override-root, so the loop can only ever post a lineage ROOT -- the
  # override exists for an operator decision and must never be something a loop can take.
  SUBOUT=$(python3 tools/climb_submit.py --submit --cap 4 2>&1 9>&-)
  echo "$SUBOUT" >> "$LOG"
  # ---- A GEM MOVES THE PYRAMID, so re-read it here and nowhere else. Khoa's ruling: the counts
  # only change when WE submit, so polling every round would re-read a number that cannot have
  # moved. If the standing baseline uses a cell that has just filled, the cycle ends -- every
  # descendant of that baseline carries its fields, so climbing on spends quota on a branch that
  # can no longer advance any pyramid.
  if [ "${NG_NOW:-0}" -gt "${LAST_NG_SEEN:-0}" ]; then
    python3 -u tools/climb.py --on-gem >> "$LOG" 2>&1 9>&-
    LAST_NG_SEEN=$NG_NOW
  fi

  if echo "$SUBOUT" | grep -q "^HTTP 20"; then
    python3 tools/notify.py --title "DA NOP TU DONG (1/ngay)" 9>&- \
    "$(python3 tools/climb.py --brief "DA NOP TU DONG" 2>&1 9>&-)" >/dev/null 2>&1 9>&-
  fi

  # ---- THE DAILY QUOTA IS A WAIT, NOT AN END. The loop used to `break` here, so it stopped for
  # good at the first exhausted day and nothing restarted it -- it sat idle through the reset. The
  # quota resets 00:00 ET = 11:00 local, so sleep to just past that and carry on. The correlation
  # probe and the submitter both still run before the sleep: they cost no simulations, and the
  # candidates already on hand are exactly what should be measured while no more can be made.
  # 400, NOT 80. The median round appends 194 lines and 51 of 68 rounds exceed 80, so a DAILY
  # refusal arriving mid-round fell out of the window and the loop never slept. It caught the two
  # 2026-08-14 events only because a zero-row round writes a SHORT block (65-71 lines).
  if tail -400 "$LOG" | grep -q "DAILY_SIMULATION_LIMIT_EXCEEDED"; then
    NOW=$(date +%s)
    RESET=$(date -d "today 11:05" +%s 2>/dev/null || echo $((NOW + 3600)))
    [ "$RESET" -le "$NOW" ] && RESET=$(date -d "tomorrow 11:05" +%s)
    SLEEP=$((RESET - NOW))
    echo "=== daily quota spent; sleeping ${SLEEP}s until the 11:00 reset ===" | tee -a "$LOG"
    python3 tools/notify.py --title "Het quota ngay — cho toi 11:00 roi tu chay tiep" 9>&- \
    "$(python3 tools/climb.py --brief "HET QUOTA — ngu toi 11:00" 2>&1 9>&-)" >/dev/null 2>&1 9>&-
    sleep "$SLEEP" 9>&-
    echo "=== quota window reopened, $(date) ===" | tee -a "$LOG"
    continue
  fi
  if tail -50 "$LOG" | grep -q "STALLED"; then
    python3 tools/notify.py --title "Chu kỳ kết thúc, reset về đợt 1" 9>&- \
    "$(python3 tools/climb.py --brief "CHU KY KET THUC — reset ve vong 1" 2>&1 9>&-)" >/dev/null 2>&1 9>&-
  fi
done
echo "=== VPS climb loop ended $(date) ===" | tee -a "$LOG"
