#!/bin/bash
# C11 experiment driver, ON THE VPS (RULE 1): 60 sims through the ordinary forge chain.
# wq-forge holds /var/lock/wq_forge.lock for its whole life, so the service is stopped for the
# experiment and started again afterwards, whatever happens (trap). It waits for a live session
# first, because forge_loop.sh with ROUNDS=1 returns at once when auth is dead.
set -u
cd /opt/wq || exit 1
LOG=/opt/wq/state/forge/c11.log
PY=/opt/wq/venv/bin/python
echo "=== c11 driver start $(date) ===" | tee -a "$LOG"

$PY forge/offline/c11_neut.py build ${C11_ARMS:+--arms $C11_ARMS} >> "$LOG" 2>&1 || { echo "build failed" | tee -a "$LOG"; exit 1; }

$PY - >> "$LOG" 2>&1 <<'PY' || { echo "no auth within 6 h; giving up" | tee -a "$LOG"; exit 1; }
import sys; sys.path.insert(0, "/opt/wq")
from forge import search as S
sys.exit(0 if S.wait_for_auth(max_s=6 * 3600, out=lambda *a: print(*a, flush=True)) else 1)
PY

# Stop the service only between rounds: a stop kills the whole cgroup, and a runner mid-round would
# leave orphans, a submit mid-POST a phantom ledger row. The gap between rounds can be 6 s
# (measured 00:47:35 -> 00:47:41), so a 20 s poll never saw it: ask the loop to end at its round
# boundary (STOP file, consumed at the top of the loop) and poll fast for the runner to be gone.
touch /opt/wq/state/STOP_FORGE
while ps -eo args | grep -q "^/opt/wq/venv/bin/python -u forge/runner.py"; do
  echo "$(date +%H:%M:%S) a round is in flight; waiting" >> "$LOG"; sleep 2
done
while ps -eo args | grep -Eq "^/opt/wq/venv/bin/python forge/submit\.py|forge/submit\.py --submit"; do sleep 1; done
systemctl stop wq-forge
rm -f /opt/wq/state/STOP_FORGE
trap 'systemctl start wq-forge; echo "=== wq-forge started again $(date) ===" | tee -a "$LOG"' EXIT
sleep 5
N=60 ROUNDS=1 FORGE_ARGS="--plan state/forge/plans/c11.json" bash /opt/wq/forge_loop.sh >> "$LOG" 2>&1
# Correlation for EVERY C11 row, passers or not (the loop's own probe reads only candidates).
IDS=$($PY -c "
import sys; sys.path.insert(0, '/opt/wq')
from forge import harvest as HV
print(','.join(sorted({r['alpha'] for r in HV.read_jsonl(HV.JOURNAL) if r.get('alpha') and (r.get('meta') or {}).get('recipe') == 'C11'})))
")
flock -w 1800 /var/lock/wq_forge_probe.lock timeout 1500 $PY -u forge/probe.py --alphas "$IDS" --limit 60 --wait 120 >> "$LOG" 2>&1
$PY forge/offline/c11_neut.py report >> "$LOG" 2>&1
echo "=== c11 driver done $(date) ===" | tee -a "$LOG"
