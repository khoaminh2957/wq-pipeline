# FRAMES-R3S + R3SB result — screening the frames of the 245 submitted alphas (2026-09-25, 16:06–16:46 +07)

Read-out per docs/frames/13c_preregistration_r3s.md and the R3SB deviation in 00_decisions.md. Script:
framelib/experiments/screen.py on R3S + R3SB rows together (journals and plans concatenated), recovered.jsonl.

## What ran

1,250 planned over 184 frames (R3S 720 + R3SB 530), each at its original settings and universe, fields only from
datasets the original alpha did not use (F12). 830 scored; 303 CANCELLED, 70 FAIL, 47 ERROR — all 47 ERRORs and the
cancellations were R3S's GROUP-field fills (fixed in R3SB, which had 0 ERROR).

## Screen

| scored | LOW_SHARPE | y08 | all 7 checks |
|---|---|---|---|
| 830 | 4 (0.48 %) | 7 (0.84 %) | 0 |

183 frames eligible (>= 3 scored); the line is the top 37 by (LOW_SHARPE rate, mean Sharpe/limit). 33 of the 37 have no
LOW_SHARPE pass, so the line is set almost entirely by mean Sharpe/limit, whose top values are 0.12–0.52.
Replication set for the next ET day (13c): the 37 above the line + 37 drawn at random below it (seed 20260928),
4 fresh fills each, same rules: ~296 sims.

## POST-HOC observations (not explanations)

- Frames taken from alphas that passed every check when submitted, filled with fields from OTHER datasets at their
  own settings, reached the 0.8 x bar on 0.84 % of scored rows. For comparison (different days, descriptive only,
  F6): the library's own-role fills 11–12 % (R1, R2); its other-dataset fills 3.9 % (R1) and 3.1 % (R2); the retired
  incumbent 8.4 % (R1).
- Across four rounds (R1B, R2, R3S, R3SB; 3,530 simulations) no alpha cleared all 7 binding checks.
- Every comparison that moved a frame away from the datasets it was written for lost most of its rate (R1 arm b,
  R2 arm b, R3S). Whether the structure needs its original datasets, its original fields, or something those
  datasets share: MECHANISM: UNKNOWN. F12 (other datasets only) was chosen to respect the no-reuse rule; the data
  so far says that choice costs almost all of the signal.
