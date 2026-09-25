#!/bin/bash
# Frame-library round driver, ON THE VPS (RULE 1). Modelled on vps/c11_run.sh.
#   F2: the incumbent loop is stopped at a round boundary for the experiment and started again afterwards
#       (trap), so exactly one loop spends quota at a time.
#   F3: no submit step. Rows go to their own journal; the incumbent's harvest/submit read forge.jsonl only.
# Usage (on the host):  EXP=FRAMES-R1 SEED=20260924 bash /opt/wq/experiments/frames/frames_round.sh [--live]
set -u
cd /opt/wq || exit 1
EXP=${EXP:-FRAMES-R1}
SEED=${SEED:?SEED required}
DSEED=$((SEED + 7))
LIVE=${1:-}
DIR=/opt/wq/experiments/frames
OUTDIR=/opt/wq/state/frames
mkdir -p "$OUTDIR"
LOG=$OUTDIR/$(echo "$EXP" | tr 'A-Z' 'a-z').log
JOURNAL=/opt/wq/state/layered/runs/$(echo "$EXP" | tr 'A-Z-' 'a-z_').jsonl
PY=/opt/wq/venv/bin/python
echo "=== $EXP driver start $(date) live=${LIVE:-no} ===" | tee -a "$LOG"

if [ "$LIVE" = "--live" ]; then
$PY - >> "$LOG" 2>&1 <<'PY' || { echo "no auth within 6 h; giving up" | tee -a "$LOG"; exit 1; }
import sys; sys.path.insert(0, "/opt/wq")
from forge import search as S
sys.exit(0 if S.wait_for_auth(max_s=6 * 3600, out=lambda *a: print(*a, flush=True)) else 1)
PY
  # stop the incumbent only between rounds (same protocol as c11_run.sh)
  touch /opt/wq/state/STOP_FORGE
  while ps -eo args | grep -q "^/opt/wq/venv/bin/python -u forge/runner.py"; do
    echo "$(date +%H:%M:%S) a round is in flight; waiting" >> "$LOG"; sleep 2
  done
  while ps -eo args | grep -Eq "^/opt/wq/venv/bin/python forge/submit\.py|forge/submit\.py --submit"; do sleep 1; done
  WAS_ACTIVE=$(systemctl is-active wq-forge)
  systemctl stop wq-forge
  rm -f /opt/wq/state/STOP_FORGE
  # F5 (2026-09-24): the incumbent is retired (stopped and disabled); restart it only if it was running
  if [ "$WAS_ACTIVE" = "active" ]; then
    trap 'systemctl start wq-forge; echo "=== wq-forge started again $(date) ===" | tee -a "$LOG"' EXIT
  else
    echo "wq-forge was $WAS_ACTIVE before this round; it is not restarted (F5)" | tee -a "$LOG"
  fi
  sleep 5
fi

# arm d: the incumbent planner's own plan, same FORGE_ARGS as the live unit, planned now (no --live: dry dispatch)
DPLAN=""
if [ "${NO_D:-0}" != "1" ]; then
  FA=$(systemctl show wq-forge -p Environment | sed -n 's/.*FORGE_ARGS=\([^"]*\)".*/\1/p')
  echo "arm d planner args: $FA" | tee -a "$LOG"
  $PY -u forge/runner.py -n 320 --seed "$DSEED" $FA >> "$LOG" 2>&1 || { echo "arm d planning failed" | tee -a "$LOG"; exit 1; }
  DPLAN=/opt/wq/state/forge/plans/$DSEED.json
  [ -s "$DPLAN" ] || { echo "no arm d plan at $DPLAN" | tee -a "$LOG"; exit 1; }
else
  echo "no arm d this round (NO_D=1)" | tee -a "$LOG"
fi

$PY -u "$DIR/dispatch_round.py" --abc "$DIR/plan_abc_$EXP.json" --d "$DPLAN" --seed "$SEED" \
    --journal "$JOURNAL" --experiment "$EXP" $LIVE >> "$LOG" 2>&1
RC=$?
echo "dispatch rc=$RC" | tee -a "$LOG"

if [ "$LIVE" = "--live" ]; then
  # correlation for every row that clears the 7 binding checks (Q4: submittable yield). No submit (F3).
  IDS=$($PY -c "
import json
B=('LOW_SHARPE','LOW_FITNESS','LOW_SUB_UNIVERSE_SHARPE','IS_LADDER_SHARPE','CONCENTRATED_WEIGHT','HIGH_TURNOVER','LOW_TURNOVER')
ids=set()
for l in open('$JOURNAL'):
    try: r=json.loads(l)
    except Exception: continue
    c={x.get('name'):x.get('result') for x in (r.get('checks') or [])}
    if r.get('alpha') and all(c.get(n)=='PASS' for n in B): ids.add(r['alpha'])
print(','.join(sorted(ids)))
")
  echo "all-check passes: ${IDS:-none}" | tee -a "$LOG"
  if [ -n "$IDS" ]; then
    flock -w 1800 /var/lock/wq_forge_probe.lock timeout 1500 $PY -u forge/probe.py --alphas "$IDS" --limit 60 --wait 120 >> "$LOG" 2>&1
  fi
fi
echo "=== $EXP driver done $(date) ===" | tee -a "$LOG"
