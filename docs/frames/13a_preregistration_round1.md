# Round 1 pre-registration — FRAMES-R1

Written 2026-09-24 ~17:05 +07, BEFORE any live row of this round exists: the driver was started at
17:01:51 and is waiting for authentication; no simulation of this round has run. The sha256 of this file
is recorded in docs/frames/00_decisions.md at the time of writing. Nothing below may be changed after the
first row lands; any later analysis is labelled POST-HOC.

## What runs (docs/frames/00_decisions.md F1–F4)

One plan, dispatched in 5 chunks (300, 300, 300, 300, 12) on the same day, arms shuffled together inside
every chunk (seed 20260924), USA / delay 1 / TOP3000, settings drawn per alpha from neutralization
{INDUSTRY, SUBINDUSTRY, STATISTICAL} x decay {4, 8}, truncation 0.08 (arm d keeps its planner's settings).
Journal: /opt/wq/state/layered/runs/frames_r1.jsonl (+ recovered.jsonl for orphans, matched by formula and
settings). No submit step.

| arm | what | planned |
|---|---|---|
| a | library frame (100) x fields of its own role, unseen with that frame | 320 |
| b | library frame (100) x fields of an admissible kind from other datasets | 309 |
| c | non-library mined frame (206) x the SAME fields and settings as one b alpha (paired) | 263 |
| d | the incumbent planner, same FORGE_ARGS as the live loop, planned at run time | 320 |

## Outcomes (per scored alpha; an ERROR or missing row counts as a failure and is reported per arm)

- **Primary:** LOW_SHARPE PASS (the outcome the discovery measured: 5.3 % base, 21.8–23.1 % top-20 %).
- Secondary: sharpe >= 0.8 x its LOW_SHARPE limit; all 7 binding checks PASS (D24); submittable = D24 and
  PROD and SELF read under their lines by the probe.

## Questions and tests (fixed now)

- **Q-C (Khoa's "tỉ lệ cải thiện bao nhiêu"): arm a vs arm d.** Rate ratio a/d of the primary outcome with a
  95 % cluster-bootstrap interval (10,000 resamples; clusters = frame for a, meta.hypothesis for d).
  "The library raises the rate" is claimed only if the lower bound exceeds 1.
- **Q-A (frame vs fields): arm b vs arm c,** paired by field tuple: the discordant pairs, an exact McNemar
  test, two-sided alpha 0.05. "Library frames beat non-library frames on the same fields" only if b > c
  and p < 0.05.
- **Q1 (own role vs foreign fields): arm a vs arm b** with the same interval method as Q-C, reported, no
  claim attached (an effect either way is informative).
- **Q-B (robust vs luck) is NOT answered by round 1.** Round 2 (F4) re-fills every frame with FRESH fields;
  the pre-registered test is the Spearman correlation of per-frame primary rates, round 1 vs round 2, over
  frames with >= 3 scored alphas in both, with a permutation p-value (10,000); "frame quality is real"
  only if rho > 0 with p < 0.05. A frame is "robust" if it is in the top quintile in round 1 and above the
  all-frame median in round 2.
- Settings balance and chunk position are reported per arm; if an arm's settings mix differs from the
  others by more than 10 percentage points in any cell of the grid, the comparison is re-run within
  settings strata and both are printed.

## What would make the answer "no"

The library claim fails if the a/d interval covers 1 (or lies below it), or if b does not beat c on the
same fields; and the robustness claim fails in round 2 if rho is not significantly above 0. Each of these
is reported as it comes out, without a new analysis chosen after seeing it.
