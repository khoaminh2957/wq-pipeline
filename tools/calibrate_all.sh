#!/bin/zsh
# Calibrate every (region, delay) pair the pyramid has cells in, one batch at a time.
#
# Why this can run today, before any field crawl: the probes use only raw price fields
# (close/open/high/low/vwap/cap), which exist in every region. The 4,865-row DEU crawl was needed
# to build ALPHAS there; it was never needed to ask what the market pays.
#
# Why it runs serially: run_multisim takes state/resim.lock and refuses to double-run, and
# validate_targets requires one region+universe per batch. 16 pairs x 66 rows = 1,056 simulations,
# about 5 minutes each.
#
# What it buys, measured: porting the USA recipe into DEU without this cost 945 simulations and
# returned 0 zero-fail at median Sharpe 0.08 — while the 66-row probe showed the DEU carrier pays
# 1.02 and that DEU's best neutralization is NONE, the exact setting the 945-row batch never drew.
set -u
cd /Users/kanenguyen/wq_pipeline
LOG=state/calibrate_all.log

# region:delay:universe — universes measured live from OPTIONS /simulations, not guessed.
PAIRS=(
  "JPN:1:TOP1600" "GBR:1:TOP700" "ASI:1:TOP500" "IND:1:TOP500" "EUR:1:TOP800"
  "CHN:1:TOP2000U" "GLB:1:TOP3000" "MEA:1:TOP400"
  "USA:0:TOP3000" "DEU:0:TOP500" "GBR:0:TOP700" "EUR:0:TOP800"
  "JPN:0:TOP1600" "CHN:0:TOP2000U"
)

echo "[$(date +%H:%M:%S)] calibrating ${#PAIRS[@]} pairs" >> $LOG
for p in $PAIRS; do
  REG=${p%%:*}; rest=${p#*:}; DLY=${rest%%:*}; UNI=${rest#*:}
  OUT="state/autoloop/pool_cal_${REG}${DLY}.json"

  python3 tools/breakthrough/gen_calibrate.py --region $REG --delay $DLY --universe $UNI \
      --out $OUT >> $LOG 2>&1 || { echo "[$(date +%H:%M:%S)] $REG d$DLY GEN FAILED" >> $LOG; continue; }

  if ! python3 tools/validate_targets.py $OUT >> $LOG 2>&1; then
    echo "[$(date +%H:%M:%S)] $REG d$DLY VALIDATE FAILED — skipped" >> $LOG; continue
  fi

  # state/resim.lock is an fcntl flock and flock AUTO-RELEASES when its holder dies, so a stale
  # lock cannot exist and there is nothing to clear. The previous code here stat'd the file, read a
  # pid stamp, and `rm -f`'d it — the exact anti-pattern tools/simq.sh was rewritten to retire on
  # 2026-08-08 and which was left live in this file. Two things were wrong with it: the live holder
  # stamps its pid a few statements AFTER acquiring the lock, so a freshly-started run reads as
  # dead; and removing the file UNLINKS it under that holder, which keeps its flock on the orphaned
  # inode while the next process creates a new file and locks a different inode. That does not
  # clear a stale lock — it deletes mutual exclusion, and two simulators then run against one
  # account writing one journal.
  #
  # Probe the lock. Never stat it, never remove it.
  while python3 -c "
import fcntl, pathlib, sys
f = pathlib.Path('state/resim.lock')
if not f.exists(): sys.exit(1)
h = open(f, 'a+')
try:
    fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB); fcntl.flock(h, fcntl.LOCK_UN); sys.exit(1)
except OSError: sys.exit(0)
finally: h.close()
"; do sleep 30; done

  # A dead session does not slow this loop down -- it makes it FAIL 14 pairs in 2 minutes, which
  # is exactly what happened at 13:40. run_multisim prints "401" and exits in 11 seconds, so the
  # whole queue drains against a session that cannot POST. Wait for auth instead of burning it.
  while true; do
    st=$(python3 -c "
import sys,pathlib
sys.path.insert(0,str(pathlib.Path.cwd()/'tools'))
import submit_alphas as SA
try: print(SA.session().get('https://api.worldquantbrain.com/users/self',timeout=25).status_code)
except Exception: print(0)
" 2>/dev/null)
    [ "$st" = "200" ] && break
    echo "[$(date +%H:%M:%S)] auth=$st — waiting before $REG d$DLY" >> $LOG
    sleep 120
  done

  echo "[$(date +%H:%M:%S)] $REG d$DLY ($UNI) simulating" >> $LOG
  python3 tools/funnel/run_multisim.py --sweep --stall-timeout 900 $OUT \
      > state/cal_${REG}${DLY}.log 2>&1
  echo "[$(date +%H:%M:%S)] $REG d$DLY done" >> $LOG
done
echo "[$(date +%H:%M:%S)] ALL PAIRS DONE" >> $LOG
