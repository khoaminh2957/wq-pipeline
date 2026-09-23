#!/bin/bash
# Wait for Khoa's tap on the VPS, then start the climb loop there.
exec 8>/var/lock/wq_arm.lock
flock -n 8 || { echo "arm already waiting"; exit 0; }
cd /opt/wq || exit 1
for i in $(seq 1 240); do
  if python3 -c "
import sys; sys.path.insert(0,'tools')
import layered_sim as LS
s=LS.session(); r=s.get(LS.API+'/users/self', timeout=20)
sys.exit(0 if r.status_code==200 else 1)
" 2>/dev/null; then
    echo "auth live at attempt $i, $(date)"
    setsid /opt/wq/climb_loop.sh > /opt/wq/state/climb_boot.log 2>&1 < /dev/null &
    exit 0
  fi
  sleep 15
done
echo "auth never arrived within 60 min"
