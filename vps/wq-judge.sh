#!/bin/bash
# D41 (Khoa, 2026-09-23): THE JUDGE RUNS ON THE VPS. It holds the live journal and every submitted alpha's
# PnL curve; the MacBook's copy held 0 of the 4 curves. Once per closed ET quota day (wq-judge.timer, 00:30
# America/New_York, when the day before has just closed) this records ONE SCORECARD PER COHORT:
#     forge/offline/benchmark.py --record --version <cohort>   ->   state/benchmark/cards.jsonl (append-only)
# It grades what the loop already did. It simulates nothing and submits nothing (RULE 1): benchmark.py has
# no flag that spends quota, and its branch drill plans on a COPY of the library and removes its own plan.
#
# ONE CARD PER COHORT (the orchestrator's instruction for this build; Draw 4 section 4 item 2 and section 5 item 3:
# `--record` with no --version built the WEAK date-window card, which pools every cohort and grades no version,
# against D1 and D14). The cohorts are the (pipeline_version, run_config) pairs benchmark.cohort_of() finds on the
# journal's SCORED rows (status COMPLETE or WARNING), labelled by benchmark.cohort_label() -- the judge's own
# functions, so this file decides nothing about what a cohort is. Scored only: MEASURED 2026-09-23 on a snapshot,
# `benchmark.py --version <a stamp no scored row carries>` raises ValueError and records nothing.
#
# SUCCESS IS READ FROM benchmark's STDERR, per cohort (draw4_build release 7 and scoring's cross-module note): it
# prints "recorded in <path>" when it appended the card, and "NOT recorded: ... already holds a card for this cohort,
# graded ET day and host (D41)" for the idempotent same-day repeat -- both are success. Its exit code cannot say
# (1 is a FAIL verdict, the expected one for now, D5 x D6, and also an uncaught exception), and the old line count
# called both a same-day repeat (1 -> 1 lines) and a card written after a repaired cut-short line (1 -> 3) failures.
#
# Run from the directory this file sits in (/opt/wq, where tools/deploy.py ships it), so a copy of the tree
# can be judged the same way. tools/deploy.py ships this file and never installs its unit (D30); the
# attended install is in wq-judge.service's header.
cd "$(dirname "$0")" || exit 1
LOG=state/benchmark/judge.log
ERR=state/benchmark/judge.err
mkdir -p state/benchmark
echo "=== judge started $(date) ===" >> "$LOG"
# The cohort list, from the judge's own functions. The program is one single-quoted word (it holds no single
# quote); its errors go to the log, and a non-zero exit records no card.
COHORTS=$(venv/bin/python -B -c '
import json, sys
sys.path[:0] = [".", "tools"]
from forge.offline import benchmark as B
seen = set()
with open(B.HV.JOURNAL, "rb") as fh:
    for raw in fh:
        if b"pipeline_version" not in raw:
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("status") in B.SCORED_STATUS:
            c = B.cohort_of(row)
            if c is not None:
                seen.add(B.cohort_label(c))
print("\n".join(sorted(seen)))
' 2>> "$LOG")
listed=$?
if [ "$listed" -ne 0 ]; then
  echo "=== judge could NOT list the cohorts (exit $listed); recorded NO card $(date) ===" >> "$LOG"
  exit 1
fi
if [ -z "$COHORTS" ]; then
  echo "=== judge found no cohort on the journal's scored rows: nothing to grade, no card $(date) ===" >> "$LOG"
  exit 0
fi
failed=0
total=0
for c in $COHORTS; do
  total=$((total + 1))
  venv/bin/python -u forge/offline/benchmark.py --record --version "$c" >> "$LOG" 2> "$ERR"
  rc=$?
  cat "$ERR" >> "$LOG"
  if grep -q -e '^recorded in ' -e '^NOT recorded: ' "$ERR"; then
    echo "=== judge: cohort $c recorded (or already recorded today); benchmark exit $rc (0 = PASS, 1 = FAIL) ===" >> "$LOG"
  else
    failed=$((failed + 1))
    echo "=== judge: cohort $c recorded NO card (benchmark exit $rc, and its stderr says neither 'recorded in' nor 'NOT recorded') ===" >> "$LOG"
  fi
done
rm -f "$ERR"
if [ "$failed" -eq 0 ]; then
  echo "=== judge done: $total cohort(s), every one recorded $(date) ===" >> "$LOG"
  exit 0
fi
echo "=== judge done: $failed of $total cohort(s) recorded NO card $(date) ===" >> "$LOG"
exit 1
