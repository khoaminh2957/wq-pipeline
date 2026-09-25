# FRAMES-R3S pre-registration — screening the frames of the 245 submitted alphas (F11–F13)

Written 2026-09-25 ~16:05 +07, before any R3S row exists. Its sha256 is recorded in 00_decisions.md.

## What runs

Plan: framelib/experiments/submitted_round.py, seed 20260927 -> 740 constructions over 185 frames (4 fresh fills
each), 720 after trimming to single-(arm, universe) parents of 10. Of the 233 submitted frames: 5 are not USA/d1,
2 do not normalise, 44 are refused by forge.typed's structural gate (H1/H2/H3 — the platform accepted their
originals; the gate is stricter than the platform there, recorded, not fixed here). Each fill: the frame's OWN
original settings, universe included (F10, F13); fields only from datasets the original alpha did not use (F12);
datasets offered today (293). No submit step. Journal: frames_r3s.jsonl.

## What is measured (no hypothesis test in the screen)

Per frame, over its scored rows: LOW_SHARPE pass rate, y08 rate, mean y_ratio (Sharpe / its LOW_SHARPE limit,
clipped to ±2.5), all-7-check passes. Rows that do not score count as failures and are reported (13a's rule).

## The screening line and tomorrow's replication (fixed now)

- Eligible: >= 3 scored rows.
- Score: lexicographic (LOW_SHARPE rate, mean y_ratio, frame id) as doc 13 §7.1.
- Line: top ceil(0.2 x eligible) frames.
- Replication (next ET day): every frame above the line AND an equal number of eligible frames drawn at random
  (seed 20260928) from below the line get 4 new fresh fills each, same rules.
- Robust (per frame): above the line on day 1 and strictly above the replication-day median of the replicated
  set. The count of robust frames is compared with a permutation null (10,000) — the one claim of R3S, one-sided
  p < 0.05.
- Printed, not claimed: the same on y08; any all-7-check row, with its correlation readings.
- Comparison with the incumbent or with the library's R1/R2 rates is descriptive only (different days, F6).
