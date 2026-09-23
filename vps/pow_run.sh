#!/bin/bash
# POW experiment driver, ON THE VPS (RULE 1): 300 paired signed_power twins through the ordinary
# forge chain (Khoa tick 2026-09-09 14:50 "Chạy ngay hôm nay"). Same shape as c11_run.sh: wq-forge
# holds /var/lock/wq_forge.lock for its whole life, so the service is asked to stop at its round
# boundary (STOP file), stopped, and started again afterwards whatever happens (trap).
set -u
cd /opt/wq || exit 1
LOG=/opt/wq/state/forge/pow.log
PY=/opt/wq/venv/bin/python
echo "=== pow driver start $(date) ===" | tee -a "$LOG"

$PY forge/offline/pow_pairs.py build >> "$LOG" 2>&1 || { echo "build failed" | tee -a "$LOG"; exit 1; }

$PY - >> "$LOG" 2>&1 <<'PY' || { echo "no auth within 2 h; giving up" | tee -a "$LOG"; exit 1; }
import sys; sys.path.insert(0, "/opt/wq")
from forge import search as S
sys.exit(0 if S.wait_for_auth(max_s=2 * 3600, out=lambda *a: print(*a, flush=True)) else 1)
PY

touch /opt/wq/state/STOP_FORGE
while ps -eo args | grep -q "^/opt/wq/venv/bin/python -u forge/runner.py"; do
  echo "$(date +%H:%M:%S) a round is in flight; waiting" >> "$LOG"; sleep 2
done
while ps -eo args | grep -Eq "^/opt/wq/venv/bin/python forge/submit\.py|forge/submit\.py --submit"; do sleep 1; done
systemctl stop wq-forge
rm -f /opt/wq/state/STOP_FORGE
trap 'systemctl start wq-forge; echo "=== wq-forge started again $(date) ===" | tee -a "$LOG"' EXIT
sleep 5
N=300 ROUNDS=1 FORGE_ARGS="--plan state/forge/plans/pow.json" bash /opt/wq/forge_loop.sh >> "$LOG" 2>&1
$PY forge/offline/pow_pairs.py report >> "$LOG" 2>&1
echo "=== pow driver done $(date) ===" | tee -a "$LOG"
