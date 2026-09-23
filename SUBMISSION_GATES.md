# SUBMISSION_GATES.md — Consultant submission tests (VERBATIM from the platform page)

**MANDATORY reading before building any alpha, AFTER forming the hypothesis** (Khoa 2026-07-17). Content below is
transcribed VERBATIM from `platform.worldquantbrain.com/learn/documentation/consultant-information/consultant-submission-tests`
(the page is a login-gated SPA; Khoa supplied the screenshots). This is the authoritative source. Region×delay
cutoffs and the USA-d1 observed values follow at the end.

---
## Interpreting Status Messages in Simulation Results
When **Check Submission** or **Submit Alpha** is pressed, tests run IN THE ORDER below. If the Alpha fails a test,
its Test Message is shown. Example: clears 1,2,3 but fails 4 → message "Improve Sharpe or reduce turnover".

| # | TEST RESULT | TEST MESSAGE |
|---|---|---|
| 1 | Alpha fails checkWeight test | Maximum weight on an instrument is greater than 10% OR Weight is too strongly concentrated or too few instruments are assigned weight. |
| 2 | Alpha fails CheckCorr test | Reduce max correlation |
| 3 | Alpha fails 0.75*ISLadder | Improve Sharpe |
| 4 | Alpha clears 0.75*ISLadder, fails 0.85*ISLadder and turnover > 10% | Improve Sharpe or reduce turnover |
| 5 | Alpha clears 0.85*ISLadder, fails 1.0*ISLadder, turnover > 30% and correlation > 0.3 | Improve Sharpe or reduce turnover or reduce correlation |
| 6 | Alpha fails fitness test | Improve fitness |
| 7 | Delay 0 Alpha fails checkDelay1Sharpe | Alpha better suited for Delay 1 |
| 8 | Alpha fails SubUniverse test | Improve Sharpe in SubUniverse |
| 9 | Most illiquid 50% instruments after cost Sharpe of x is below cutoff of y (z original universe after cost Sharpe) | Improve alpha performance in top illiquid quantile |

## Check-IS-Sharpe or IS-Ladder test (the REAL Sharpe gate — not a single "2Y" number)
`Sharpe = sqrt(250) * IR ≈ 15.8 * IR`, where `IR = avg(dailyPNL) / StdDev(dailyPNL)`.
Iterative test comparing average IS performance to a series of benchmarks. Starts with the most recent **2 years**
of IS data; each iteration ADDS a year. Logic:
1. if Sharpe for the whole history < FAIL_THRESHOLD → test FAILED
2. Else:
3. Start with N_YEARS = 2
4. if Sharpe[N_YEARS] < FAIL_THRESHOLD → test FAILED
5. else if Sharpe[N_YEARS] > PASS_THRESHOLDS[N_YEARS] → test PASSED
6. else if (Sharpe[N_YEARS] > FAIL_THRESHOLD) and (Sharpe[N_YEARS] < PASS_THRESHOLDS[N_YEARS]) → N_YEARS += 1
7. Go to step 4 with the updated N_YEARS.
- Sharpe[N_YEARS] = Sharpe over the most recent N_YEARS of the IS period.
- **If turnover < 30%, the PASS_THRESHOLDS are multiplied by 0.85** (FAIL_THRESHOLD is NOT).

### IS-Ladder thresholds (D1 / D0)
| No. YEARS | D1 THRESHOLD | D0 THRESHOLD |
|---|---|---|
| **FAIL_THRESHOLD** | **1.59** | **2.69** |
| 2 | 2.38 | 3.96 |
| 3 | 2.38 | 3.96 |
| 4 | 2.38 | 3.96 |
| 5 | 2.38 | 3.96 |
| 6 | 2.22 | 3.64 |
| 7 | 2.06 | 3.33 |
| 8 | 1.90 | 3.17 |
| 9 | 1.74 | 2.85 |
| 10 | 1.59 | 2.69 |

## Weight test
Fails if: (a) too few stocks are assigned weight for a significant number of days in a year (all-zero weights at
the START of the sim do NOT fail — only after weights begin; min-stock count varies by universe); OR (b) weight is
too concentrated in one stock (e.g. one stock holding 30% of all weight → fail). Max weight > 10% also fails.

## Sub universe test
- **For TOPXXX universes:** `subuniverse_sharpe >= 0.75 * sqrt(subuniverse_size / alpha_universe_size) * alpha_sharpe`
- **For non-TOPXXX universes:** `subuniverse_sharpe >= subuniverse_ratio * alpha_sharpe`, where subuniverse_ratio =
  ASI MINVOL1M 0.295 · USA ILLIQUID_MINVOL1M 0.41 · EUR ILLIQUID_MINVOL1M 0.355.

## Self-Correlation
Checks if the submitted alpha is highly correlated to the user's PREVIOUS submissions. **Threshold 0.7** — if
correlation > 0.7, additional conditions apply (reduce correlation; ties into test #2 CheckCorr and #5).

## Cluster Test (tagging only)
A cluster = a group of related instruments. **Threshold: Cluster Sharpe >= 1.58.** If Cluster Sharpe >= 1.58 the
Alpha is TAGGED `Cluster`; otherwise no tag. **Effect: tagging only — submission conditions unchanged. Failing does
NOT block submission** and does not affect other classifications. (A "Cluster Test check error" is a compute error.)

## Superalphas
Same submission criteria as alphas EXCEPT turnover: **2% <= turnover < 40%.**

## Alphas in ILLIQUID_MINVOL1M universes
Illiquid instruments have high slippage / wide spreads → the **after-cost sharpe** scores returns net of those
costs. Additional condition: after-cost sharpe for the most-illiquid 50% instruments must be > ~**52.5%** of the
original-universe after-cost sharpe (test #9).

## ASI / JPN / HKG / TWN / KOR — Investability Sharpe test
Pass EITHER way: (1) set **maxtrade=ON**; OR (2) set maxtrade=OFF and ensure `"investability constraint Sharpe" >
"original Sharpe" * 0.7`.

## ASI — Robust Universe Test
Passes if performance on the adjusted (more-scalable) universe retains **>= 90%** of the returns AND Sharpe vs the
original submission. Tip: build broad, economically-motivated signals; test across universe configs; aim for higher
returns / wider margin.

## Alphas in CHN region (SEPARATE, higher bars — this project targets USA so these do not apply)
- **D1: Sharpe >= 2.08, Returns >= 8%, Fitness >= 1.0.  D0: Sharpe >= 3.5, Returns >= 12%, Fitness >= 1.5.**
- Robust-universe test: retains at least **40%** of returns and Sharpe of the submission version.

---
## Observed USA d1 TOP1000 cutoffs (live-sim, "excluding CHN" set — cross-check with the verbatim above)
LOW_SHARPE / LOW_2Y_SHARPE band 1.58 (WARNING below, submittable; the IS-Ladder FAIL_THRESHOLD is 1.59) · LOW_FITNESS 1.0 ·
LOW_RETURNS 0.12 · LOW_TURNOVER 0.01 · HIGH_TURNOVER 0.70 · CONCENTRATED_WEIGHT 0.10 (max weight 10%) ·
LOW_SUB_UNIVERSE_SHARPE (= 0.75·sqrt(sub/alpha)·alpha_sharpe) · HT_HIGH_TURNOVER_RETURNS_RATIO 0.75 ·
HT_LIQUID_TOP200_SHARPE 1.0 · HT_AFTER_COST_SHARPE 1.0 · HT_INVESTABLE_MAX_TRADE/POSITION_SHARPE 2.0 ·
HT_ORTHOGONAL_RAM_NEUTRALIZATION = RAM · SELF/PROD/POWER_POOL correlation < 0.7.

**Result buckets:** PASS / WARNING (not a hard fail — an alpha with only WARNINGs is submittable "zero-fail") /
ERROR (check could not compute — e.g. Cluster Test, usually transient) / PENDING (evaluated at submit — correlations, quota, theme).

## The two binding gates on USA d1 (empirical this project) + KEY correction from the verbatim page
Strong signals died on the **IS-Ladder** (recency) and **Sub-universe** tests. Two corrections from the real docs:
1. The Sharpe gate is the **IS-LADDER** (iterative 2→10 years), not a single 2Y number — and **turnover < 30% gets a
   0.85× discount on PASS thresholds**, so a LOWER-turnover version of a signal has an EASIER ladder. (This partly
   revises the srl2 "high turnover is pure cost" view — cutting turnover under 30% also relaxes the Sharpe ladder.)
2. Sub-universe cutoff is `0.75·sqrt(sub_size/alpha_size)·alpha_sharpe` — a HIGHER alpha_sharpe RAISES the bar it
   must clear, so sub-universe is about CONSISTENCY (the sub must scale with the whole), not an absolute number.

**Before simming any root:** read this file after forming the hypothesis; confirm the hypothesis plausibly clears
the IS-Ladder (recent-years Sharpe) + Sub-universe + Weight, and won't trip CONCENTRATED_WEIGHT / HIGH_TURNOVER.
