#!/bin/bash
# HARVEST, SEPARATED FROM DISPATCH.
#
# The runner used to POST and then sit polling one handle up to 220 times while its siblings sat
# finished -- which is how a batch produced POLL-EXHAUSTED rows and ~80 rows/hour. The recovery pass
# proved the other half: polled AFTER the fact, a child answers in 0.3 s, and 1,430 rows came back
# from 143 parents in minutes. So dispatch and collection stop taking turns: the loop POSTs, this
# sweeps every journal for parent handles and harvests whatever is ready.
# 2026-08-16: the harvester ran production code out of /tmp for three days. /tmp does not survive a
# reboot, so a restart would have left this loop calling a file that no longer existed -- silently,
# because the error goes to a log nobody reads. Moved to /opt/wq/tools/ and put under git.
#
# It is NOT wedged, which an audit first reported: it re-scans every journal each pass, the corpus
# has grown to ~9,800 rows, and one pass now takes longer than its own 120 s cadence. That is a
# scaling problem, not a hang.
while true; do
  /opt/wq/venv/bin/python -u /opt/wq/tools/recover_harvest.py >> /opt/wq/state/layered/runs/harvest.log 2>&1
  sleep 120
done
