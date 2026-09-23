#!/bin/zsh
# Fire a driver run once an already-running PID exits.
#
# Why: the concurrent-simulation ceiling (~80-90) is the binding constraint, not the daily budget.
# Two drivers dispatching at once do not share it -- they collide, and the loser journals 0 rows.
# That is exactly how the Imbalance probe was lost on 2026-08-06: it launched 140 targets at
# 10:30 while the daily wall was still shut and got 0/140 back, and re-launching it alongside the
# P2 run would have lost it a second way. Sequencing costs wall-clock and nothing else.
#
#   tools/queue_after.sh <pid-to-wait-for> <pool.json> <tag> <rounds> <hours>
set -u
WAIT_PID=$1; POOL=$2; TAG=$3; ROUNDS=$4; HOURS=$5
cd /Users/kanenguyen/wq_pipeline
LOG=state/autoloop/queue_${TAG}.log
echo "[$(date +%H:%M:%S)] waiting on pid $WAIT_PID before launching $TAG ($POOL)" >> $LOG
while kill -0 $WAIT_PID 2>/dev/null; do sleep 60; done
echo "[$(date +%H:%M:%S)] pid $WAIT_PID gone -- launching $TAG" >> $LOG
nohup python3 tools/autoloop/driver.py --pool $POOL --hours $HOURS --rounds $ROUNDS \
      --tag $TAG --no-submit >> state/autoloop/driver_${TAG}.log 2>&1 &
echo "[$(date +%H:%M:%S)] $TAG launched pid $!" >> $LOG
