#!/bin/bash
# The LLM-FORMULA arm, ON THE VPS (RULE 1). Same shape as c11_run.sh and pow_run.sh: wq-forge holds
# /var/lock/wq_forge.lock for its whole life, so the service is asked to stop at its round boundary
# (STOP file), stopped, and started again afterwards whatever happens (trap).
#
# Khoa's tick 2026-09-19: run the mechanism arm and the formula arm from ONE rented-GPU session and
# measure them against each other on one quota day, rather than argue about which is better.
#   N        how many simulations this arm gets (the mechanism arm is the rest of the day)
#   PLAN     built beforehand by `forge/llm/formula.py` against the rented endpoint
set -u
cd /opt/wq || exit 1
LOG=/opt/wq/state/forge/llmformula.log
PY=/opt/wq/venv/bin/python
N=${N:-300}
PLAN=${PLAN:-state/forge/plans/llmformula.json}
echo "=== llm-formula driver start $(date) ===" | tee -a "$LOG"

if [ ! -s "$PLAN" ]; then
  echo "no plan at $PLAN -- run forge/llm/formula.py against the GPU endpoint first" | tee -a "$LOG"
  exit 1
fi
$PY -c "
import json,sys
p=json.load(open('$PLAN'))
print('plan holds %d construction(s), arm %s' % (p['n'], p['constructions'][0]['meta']['arm']))
sys.exit(0 if p['n'] else 1)" | tee -a "$LOG" || exit 1

$PY - >> "$LOG" 2>&1 <<'PY' || { echo "no auth within 2 h; giving up" | tee -a "$LOG"; exit 1; }
import sys; sys.path.insert(0, "/opt/wq")
from forge import search as S
sys.exit(0 if S.wait_for_auth(max_s=2 * 3600, out=lambda *a: print(*a, flush=True)) else 1)
PY

touch /opt/wq/state/STOP_FORGE
while ps -eo args | grep -q "^/opt/wq/venv/bin/python -u forge/runner.py"; do
  echo "$(date +%H:%M:%S) a round is in flight; waiting" >> "$LOG"; sleep 2
done
while ps -eo args | grep -Eq "forge/submit\.py"; do sleep 1; done
systemctl stop wq-forge
rm -f /opt/wq/state/STOP_FORGE
trap 'systemctl start wq-forge; echo "=== wq-forge started again $(date) ===" | tee -a "$LOG"' EXIT
sleep 5

N=$N ROUNDS=1 FORGE_ARGS="--plan $PLAN" bash /opt/wq/forge_loop.sh >> "$LOG" 2>&1

# The arm's funnel against the mechanism arm, same day, same gates.
$PY forge/offline/ab_report.py >> "$LOG" 2>&1 || true
echo "=== llm-formula driver done $(date) ===" | tee -a "$LOG"
