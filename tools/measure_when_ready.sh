#!/bin/zsh
# Poll ONE alpha's correlation until the endpoint actually returns a payload, then measure a list.
#
# Why: `GET /alphas/{id}/correlations/{kind}` answers `200 + Retry-After + EMPTY BODY` while the
# platform has not produced the number. That is indistinguishable at the HTTP layer from a healthy
# "computing" response, and on 2026-08-06 it stayed that way for 600 consecutive polls / 799s on a
# single alpha -- including one that had answered normally an hour earlier. So the empty body is
# not a per-alpha condition and it is not a short wait; MECHANISM UNKNOWN.
#
# The cost of guessing wrong is real: 24 zero-fail candidates, every one in a still-short pyramid
# cell, cannot be ranked without prod/self, and re-running the measurer into a blocked endpoint
# just burns the 25-try budget per alpha and writes `None` rows that look like measurements.
# So: probe cheaply, and only spend the real measuring pass once a payload has actually landed.
#
#   tools/measure_when_ready.sh <canary-alpha-id> <id-list-file>
set -u
CANARY=$1; LIST=$2
cd /Users/kanenguyen/wq_pipeline
LOG=state/measure_when_ready.log
echo "[$(date +%H:%M:%S)] waiting on correlation endpoint (canary $CANARY)" >> $LOG
while true; do
  if python3 -c "
import sys, pathlib
sys.path.insert(0, 'tools')
import submit_alphas as SA
s = SA.session()
r = s.get('https://api.worldquantbrain.com/alphas/$CANARY/correlations/prod', timeout=45)
sys.exit(0 if (r.status_code == 200 and r.text.strip()) else 1)
" 2>/dev/null; then
    echo "[$(date +%H:%M:%S)] endpoint LIVE -- measuring $(wc -w < $LIST) alphas" >> $LOG
    python3 tools/measure_corr_incremental.py ${=$(cat $LIST)} >> state/zf_measure.log 2>&1
    echo "[$(date +%H:%M:%S)] measuring pass done" >> $LOG
    exit 0
  fi
  sleep 180
done
