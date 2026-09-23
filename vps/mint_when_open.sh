#!/bin/bash
# Wait for the platform's biometric window to open, mint ONE link, post it to Discord.
# Minting inside a closed window just burns polls: the last attempt got 81/81 x 403.
exec 9>/var/lock/wq_mint.lock
flock -n 9 || { echo "a mint watcher already holds the lock"; exit 0; }
cd /opt/wq || exit 1
LOG=/opt/wq/state/mint_watch.log

for i in $(seq 1 120); do
  LEFT=$(python3 -c "
import json,time
try:
    d=json.load(open('state/auth_status.json'))
    print(int(d.get('next_window_in_s',0) - (time.time()-d.get('ts',0))))
except Exception:
    print(0)
" 2>/dev/null || echo 0)
  [ "${LEFT:-0}" -le 5 ] && break
  echo "$(date +%H:%M:%S) window opens in ${LEFT}s" >> "$LOG"
  sleep 30
done

echo "=== window open, minting $(date) ===" >> "$LOG"
pkill -f auth_only.py 2>/dev/null; sleep 1
setsid python3 tools/auth_only.py >> "$LOG" 2>&1 < /dev/null &

# The link appears in the status file within a few seconds of the mint.
for i in $(seq 1 20); do
  sleep 5
  STAGE=$(python3 -c "import json;print(json.load(open('state/auth_status.json')).get('stage',''))" 2>/dev/null)
  LINK=$(python3 -c "import json;print(json.load(open('state/auth_status.json')).get('persona',''))" 2>/dev/null)
  if [ "$STAGE" = "await_biometric" ] && [ -n "$LINK" ]; then
    python3 tools/notify.py --title "Auth link moi — tap de chay tiep" --url "$LINK" \
      "Loop dung luc 01:50 vi auth 401. Cua so sinh trac hoc vua mo, day la link vua mint.
Inquiry song ~10 phut. Tap xong loop tu chay lai (cycle 4, 5 gem trong so)." >> "$LOG" 2>&1
    echo "POSTED $LINK" >> "$LOG"
    # Arm the loop to restart the moment auth lands.
    setsid /opt/wq/arm_climb.sh >> "$LOG" 2>&1 < /dev/null &
    exit 0
  fi
done
echo "=== mint did not produce a link; stage=$STAGE ===" >> "$LOG"
python3 tools/notify.py --title "Mint auth THAT BAI" \
  "Cua so da mo nhung mint khong ra link. stage=$STAGE. Can xem tay." >> "$LOG" 2>&1
