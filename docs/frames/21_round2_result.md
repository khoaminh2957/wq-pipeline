# Round 2 result — FRAMES-R2 (2026-09-25, 13:36–15:24 +07): is a frame's advantage stable on fresh fields?

Read-out per docs/frames/13_preregistration.md §3.2 and §7.1 (sha256 466c0c1b…, recorded before any R2 row; plan
sha256 6ebed3db…). Script: framelib/experiments/qb.py. Inputs: frames_r1b / frames_r2 journals and plans,
recovered.jsonl (copied 15:3x).

## What ran

| arm | planned | scored | LOW_SHARPE | y08 | all 7 checks |
|---|---|---|---|---|---|
| a own-role, fresh fields (all 100 frames, 85 had enough fresh fields) | 680 | 450 | 9 | 54 | 0 |
| b other-dataset fields | 390 | 200 | 5 | 12 | 0 |

230 of arm a's and 190 of arm b's planned alphas returned no score (CANCELLED / ERROR / FAIL); round 1 lost 4 %
of arm a. Why the loss is larger today: UNKNOWN (measured next, before the loop runs).

## The pre-registered answers (75 frames with >= 3 scored own-role rows in both rounds)

- **B1 — the one claim — NOT MET.** Spearman rho of per-frame LOW_SHARPE pass rates, round 1 vs round 2 = 0.218,
  permutation p = 0.104. LOW_SHARPE passes are too sparse to rank frames: 2 frames had any in round 1, 8 in round 2.
  - Printed first (doc 13): ingredient stratum (>= half the frame's fills use option3/option8/us_short_sale),
    30 frames, rho 0.33, p 0.13; the other 45 frames: no pass in round 2, rho undefined.
- **B2 — robust frames (estimate):** all 15 of round 1's top-quintile frames scored above the round-2 median;
  the permutation null expects 7.4; one-sided p < 0.0001. 14 of the 15 are ingredient frames.
- **B3 — retained share of the top quintile's lead (estimate):** on the y08 rate 0.88, 95 % frame-bootstrap
  interval [0.58, 1.31]; on mean Sharpe/limit 0.88, [0.71, 1.01].

## Printed beside, not claims (POST-HOC reading)

- On y08 (Sharpe >= 0.8 x its bar) the per-frame ranking replicates on fresh fields: rho 0.83 over the 75 frames
  (p < 0.0001); within the 30 ingredient frames rho 0.76 (p 0.0002), mean y08 32.2 % in round 1 and 31.4 % in round 2.
- Outside the ingredient datasets the frames produced almost nothing: 45 frames, mean y08 2.8 % in round 1 and
  0 % in round 2.
- Two rounds, 2,280 sims: **0 alphas cleared all 7 binding checks**, so nothing is submittable yet.

## What this establishes, and what it does not

- Established on the pre-registered test: nothing (B1 not met).
- Estimated, not claimed: the frames that scored best in round 1 kept most of their lead (about 88 %) on fields they
  had never been filled with, and within the option/short-sale frames the ranking on y08 held (rho 0.76). This is
  the first live evidence consistent with Khoa's "khung bền" — on the y08 scale and inside those datasets only.
  Whether the stable part is the operator structure, the preset condition fields, the settings, or the datasets
  the own-role fills come from: MECHANISM: UNKNOWN (own-role fills stay in the frame's historical datasets).
- Not established: any gain in all-check passes or submittable alphas, and anything outside the option/short-sale
  datasets.
