# 13 — Pre-registration of the live rounds that test the frame-library hypothesis (round 2 onward)

2026-09-24, written 17:07–17:35 +07. Role: experiment designer. Nothing was simulated, nothing touched the VPS,
no `--live` or `--submit` (RULE 1). Nothing here runs live or ships (RULE 2). The only repo write is this file.
Scripts and outputs: `$P` = `/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/
822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad/frames/prereg/` (§12).

Labels (RULE 0). **EX-ANTE**: from documentation, code, definitions or arithmetic. **POST-HOC**: a regularity
measured in data. **SPECULATION**: neither. **DESIGN CHOICE**: a decision made here, not a finding; it can be
wrong but it cannot be false. Where a pattern has no experiment behind its reason: **MECHANISM: UNKNOWN**.

**Timing, stated first.** Round 1 was pre-registered in `13a_preregistration_round1.md` (17:02, sha256
`b45ea1ec…2531`, re-checked 17:25: unchanged) and its driver started at 17:01:51, waiting for authentication
(`00_decisions.md`). This document was written AFTER round 1 began. Its author has read no round-1 row: this
phase has no VPS access, so whether rows existed while it was being written is UNKNOWN to the author. Any rule
below that touches round-1 data is marked **[after R1 start, blind]**. Round 2 has not started, so no round-2
row exists. The sha256 of this file should be recorded in `00_decisions.md` before round 2's first row. After
that, nothing below may change. A later analysis is labelled POST-HOC.

**What this document may not change.** 13a governs round 1 and stays as written. F1–F4 (Khoa's ticks) stand.
§1 lists five reading notes on 13a. They are printed beside 13a's results and never replace them.

---

## 0. On one screen

1. **The three questions, each with an estimand, a unit and a test fixed before its data (§3).**
   - **Q-A**, frame vs structure at the same fields. Unit: pairs dispatched in the same round. Test: McNemar.
   - **Q-B**, robust vs luck on fresh fields. Unit: the frame. Tests: 13a's Spearman, the robust count against
     its permutation null, and regression to the mean.
   - **Q-C**, how much the library raises the rate against the incumbent. Unit: the round, randomised within
     each ET day. Test: within-day permutation.
   - Q-C and Q-A test y08 → LOW_SHARPE → D24 as a fixed sequence, each against O'Brien–Fleming looks at 7, 14,
     21 and 28 experiment days (D55's boundaries).
2. **The live baseline (POST-HOC, §2).**
   - 4 accepted forge POSTs in about 20 quota days: 0.2 per day.
   - Since 09-12: 1 alpha cleared every binding check out of 10,748 scored (my recount; the brief says 10,578).
     All of these rows fall on 09-20..09-24.
   - In USA/d1/TOP3000 over 09-20..09-24, 39.0 % of the incumbent's rows carry an option3, option8 or
     us_short_sale field. Those rows reach 0.8 × the Sharpe bar 29.4 % of the time; the others reach it 1.44 %
     of the time. On LOW_SHARPE the rows without such a field pass 0 of 5,557.
   - Every comparison below is therefore also reported split by this "ingredient" flag. The reason for the gap:
     MECHANISM: UNKNOWN.
3. **The smallest effects the design can detect at the real volume (§6), for 3 library rounds a day.** Each
   value is the smallest rate ratio with 80 % power, at 7 / 14 / 21 / 28 experiment days. The model's inputs are
   POST-HOC; the arithmetic is EX-ANTE.

   | outcome | incumbent rate | 7 days | 14 days | 21 days | 28 days |
   |---|---|---|---|---|---|
   | y08 (Sharpe ≥ 0.8 × the bar) | 12.3 % | 1.5× | 1.3× | 1.2× | 1.2× |
   | LOW_SHARPE pass | 2.27 % | 2.0× | 1.5× | 1.3× | 1.3× |
   | every binding check (D24), recent rate | 0.11 per 1,000 | none ≤ 50× | 10× | 7× | 5× |
   | D24, forge-era rate | 1.15 per 1,000 | 10× | 4× | 2.5× | 2.5× |

   - Spending more quota barely helps y08 and LOW_SHARPE: 4, 6 or 8 library rounds reach 1.4× at 7 days. Days,
     not sims, are the constraint.
   - D24, the outcome RULE 2 gate 4 needs, can only show a large effect within 28 days.
4. **One statistic was replaced.** compare_arms' count-weighted form was replaced by the round-rate form. In the
   model (EX-ANTE), with library rounds of 300 in-estimand rows against incumbent rounds of 200 and 3–4 library
   rounds out of 15, the count form reads better or worse 7.7–10.6 % of the time under no effect. The rate form
   reads it 3.3–4.2 % of the time. The two forms agree when rounds are the same size (§6.1).
   - On the desk's own rounds, relabelled at random, the rate form reads a false verdict 4.2–5.1 % of the time
     (the D54 placebo).
5. **The plan (§7).**
   - R1 (13a) screens.
   - R2 (tomorrow, F4) re-fills all 100 frames equally: 8 fresh own-role fills plus 4 fresh other-dataset
     fills, 1,200 sims, in the same block form as R1.
   - From R3, each experiment day interleaves library (L), paired (P) and screen/replication (S/R) rounds with
     the incumbent's own rounds, at pre-drawn random positions.
   - Promotion runs candidate → screened → replicated → validated (Khoa's tick) → retired.
6. **Quota (§8).** R1 is 1,212 sims and R2 is 1,200. Template A for R3+ is 1,500 a day, leaving the incumbent
   about 3,500. There is no submit step until Khoa ticks otherwise (§9).
7. **Seven tick questions (§11).** The round-1 versions of quota, pause and submission were answered by F1–F3.
   These questions are for round 2 onward.

---

## 1. Round 1 (13a): reading notes, not changes

Each note is printed beside 13a's result when that result is read. None changes 13a's test or its verdict.

| # | 13a item | note | label |
|---|---|---|---|
| N1 | Q-C a vs d | Arm d is planned with the live FORGE_ARGS, and on 09-23 the incumbent put 850 of 5,024 rows (17 %) in GLB/d1/MINVOL1M. Arm d's own share is UNKNOWN until it is planned. 13a's rate ratio pools cells, and D28 says compare within cell. Printed beside it: a/d restricted to d's USA/d1/TOP3000 rows. | POST-HOC share; EX-ANTE rule |
| N2 | Q-C a vs d | Arm a draws settings from 6 cells: {INDUSTRY, SUBINDUSTRY, STATISTICAL} × decay {4, 8} × truncation 0.08. In 09-20..09-24 the incumbent put 18.9 % of its cell rows at truncation 0.15 and 1.6 % at decay 16, so 20.5 % of its rows lie outside arm a's support. Arm d's own mix is UNKNOWN until it runs. If it resembles those rows, no single grid cell differs by more than 4.1 pp, and 13a's 10-pp balance rule will not fire. Printed beside it: a/d on d's rows inside the 6-cell support. | POST-HOC |
| N3 | Q-C a vs d | Arm d is ONE planner call of 320. D54 measured round-level clustering 2.2× the exchangeable null. A cluster bootstrap by `meta.hypothesis` resamples inside that one draw and does not see the between-round variance. The interval is read as a lower bound on the uncertainty. | EX-ANTE (D54) |
| N4 | Q-C a vs d | Ingredient share in the plan: arm a 46.9 %; incumbent recent rows 39.0 %. At the incumbent's within-stratum rates, composition alone gives a/d ≈ 1.18 on y08 and ≈ 1.20 on LOW_SHARPE. Printed beside it: a/d within each ingredient stratum. | EX-ANTE arithmetic on POST-HOC rates |
| N5 | Q-A b vs c (McNemar) | 85 of 254 matched plan pairs (33 %; 9 of the 263 arm-c alphas found no arm-b partner by key) differ in ingredient status, counting fields pinned in the frame text: 47 have it only on the control side, 38 only on the library side. Shares: b 22.3 %, c 31.6 %. Composition alone favours the control by about 1.34× on y08. Printed beside it: McNemar on the 169 ingredient-concordant pairs. **[after R1 start, blind]** | EX-ANTE arithmetic on POST-HOC rates |

The plan counts above come from the Mac copy `r1/plan_abc.json` (sha256 `e7732ed0…`). Its identity with the file
the VPS dispatched was not checked.

**13a's Q-B is ambiguous. It is disambiguated here, before any round-2 row exists [after R1 start, blind].**
- "Per-frame primary rates, round 1 vs round 2" is read as: the round-1 rate uses the frame's arm-a rows, and the
  round-2 rate uses its round-2 own-role fresh rows (like with like).
- Printed beside it, not deciding: the round-1 rate from arm a + arm b rows.

---

## 2. The live baseline (measured here, two ways where a second way exists)

Source: the Mac copy of `forge.jsonl` (12:42 +07). Last row per alpha id, status COMPLETE or WARNING with a check
set: 39,228 ids, 0 unparsable lines. ET quota days.

| quantity | value | second way / note |
|---|---|---|
| accepted forge POSTs 09-04..09-24 | 4 (vRk095rv 09-04, kqVbg1xP 09-06, vRk1J2jd 09-10, rK5RGeqa 09-22) → **0.2 per quota day** | `state/forge/submitted.jsonl`, Mac copy of 09-23 00:49 |
| scored since 09-12 / cleared all 7 binding checks | **10,748 / 1** (gJboG8mv, 09-20, USA/d1/TOP3000) | The brief says 10,578 / 1. COMPLETE-only gives 9,270. The 170-row gap is not resolved; its cause is UNKNOWN. The copy holds no row on 09-12..09-19. |
| USA/d1/TOP3000, 09-20..09-24: rows / y08 / LOW_SHARPE / D24 | 9,111 / 12.36 % / 2.26 % / 1 | Restricted to rounds with ≥ 100 cell rows: 8,931 / 12.34 % / 2.27 % / 1 |
| the same, whole forge era (rounds ≥ 100 cell rows) | 27,767 / 14.36 % / 3.50 % / 32 (1.15 per 1,000) | — |
| rows carrying option3 / option8 / us_short_sale (cell, 09-20..24) | 3,554 of 9,111 (39.0 %): y08 29.4 %, LS 5.80 %, D24 1. Without: 5,557, y08 1.44 %, LS **0**, D24 0 | Formula tokens → catalogue dataset, and `meta` signature strings: identical split |
| rounds in the cell: size, per day | median 250 cell rows per 300-sim round; up to 17 rounds per day (09-23) | — |
| between rounds within a day, Pearson χ²/df (recent; whole era) | y08 3.18 (df 33); 4.32 (121) · LS 2.07; 2.90 · D24 1.12 (df 8); 1.59 (60) | Deviance/df: y08 3.30; 4.31 · LS 2.04; 2.98 · D24 0.58; 1.26 |
| between days, Pearson χ²/df | y08 7.6 (3 df); 25.8 (11) · LS 0.86; 47.3 · D24 0.97; 11.8 | Doc 10 §2.1: d24 11.73, LS 51.06 on its own row set |
| incumbent settings in the cell, 09-20..24 | 79.5 % in the R1 grid; 18.9 % at truncation 0.15; 1.6 % at decay 16 | — |

What the gap between days means for the design (EX-ANTE, D47 and D54): rates move between days far more than
between rounds of one day. So a comparison that is not made within a day has no verdict. MECHANISM of either
variation: UNKNOWN.

---

## 3. Questions, estimands, units, tests

### 3.1 Outcomes (per scored alpha; fixed)

- **y08.** The row's Sharpe ≥ 0.8 × its own LOW_SHARPE limit (D34's y = 1).
- **LS.** LOW_SHARPE = PASS.
- **D24.** Each of `benchmark.ESTIMAND["binding_checks"]` reads PASS: LOW_SHARPE, LOW_FITNESS,
  LOW_SUB_UNIVERSE_SHARPE, IS_LADDER_SHARPE, CONCENTRATED_WEIGHT, HIGH_TURNOVER, LOW_TURNOVER. The tuple is
  frozen there.
- **Scored.** Status COMPLETE or WARNING with a check set, last row per alpha id. This is D24's denominator.
  - Printed beside it: the rate per dispatched construction, with ERROR and unscored rows counted as failures.
  - If the arms' unscored shares differ by more than 5 pp, that is printed first.
- **Reported, never tested.**
  - Submittable: D24, and PROD and SELF under their lines by the probe.
  - Distinct fingerprint families among the y08 and D24 rows (D7).
  - The IS_LADDER end date of each row (12 M5).
- **Recorded per alpha at plan time.** These are pre-treatment covariates.
  - `ingredient`: any option3, option8 or us_short_sale field, pinned fields included.
  - `fresh_id`: no field id in any slot was ever used with that frame, in canonical or in an earlier live round.
  - `fresh_family`: the same test, by `fingerprint.canon_field`.
  - The fingerprint family.
  - An exact repeat of any journalled formula and settings is removed from the plan before dispatch.

### 3.2 Table

| | Q-A: does a library frame beat a control structure at the same fields? | Q-B: is a frame's advantage stable on fresh fields? | Q-C: by how much does the library raise the rate against the incumbent? |
|---|---|---|---|
| arms | P rounds: each pair = library frame × fill F × settings s, and a control structure × the same F and s, **both in the same round** | R2, then each new cohort's replication day: every frame of the cohort gets equal fresh fills | L rounds (library, fresh fills) vs I rounds (the incumbent's own rounds), randomised within each ET day |
| unit | the pair, grouped by day | the frame | **the round** (D54) |
| estimand | conditional odds n10/n01 and the rate difference Y_L − Y_C, for each outcome | (B1) 13a's Spearman ρ of per-frame LS rates, R1 vs R2. (B2) number of "robust" frames minus its null expectation. (B3) retained share of the top-quintile gap, (R2 top − R2 all) / (R1 top − R1 all), on y08 rate and on mean y_ratio | rate ratio RR = mean over shared days of the day's mean L-round rate, divided by the same for I rounds; also the difference per 1,000 |
| test | exact McNemar on cumulative n10, n01, compared with each look's nominal p | (B1) 13a's permutation test, 10,000, claim when ρ > 0 and p < 0.05. (B2) permutation of R2 scores across frames, 10,000, one-sided. (B3) interval only | within-day permutation of arm labels, holding each day's number of L rounds fixed. Statistic S = Σ_d Σ_{r ∈ L_d} (r_r − r̄_d), with r_r = k_r / n_r and r̄_d the unweighted mean round rate of day d. Two-sided sequential Monte Carlo p (the benchmark's `ARMS_PERM_*`) |
| multiplicity | fixed sequence y08 → LS → D24: a later outcome can be claimed only at or after the look where the earlier one was claimed. Each uses its own O'Brien–Fleming boundary at total two-sided 0.05. FWER ≤ 0.05 (EX-ANTE: a false claim needs the first true null in the sequence to cross its own valid boundary) | one claim (B1) per replication. B2 and B3 are estimates | same as Q-A |
| interval | at look k, a repeated confidence interval at level 1 − nominal p_k: exact binomial on n10 / (n10 + n01), and a pair bootstrap for the difference | frame bootstrap, 10,000, 95 % | at look k, a repeated confidence interval at 1 − nominal p_k by day-stratified bootstrap (days, then rounds within arm, 10,000). The plain 95 % interval is printed and labelled "not adjusted for looks" |
| stratified report, printed first | within ingredient-concordant pairs (all pairs are concordant from R3 on, §4) | B1 within frames whose own-role fills carry the ingredient in ≥ half of them, and within the rest | Q-C within each ingredient stratum, plus Q-C on all incumbent cell rows (not only the R1 settings grid) |
| what "no" looks like | y08 crosses "worse", or no crossing by look 4 | ρ not > 0 at p < 0.05. Robust count inside its null range. Retained share interval covering 0 | y08 crosses "worse", or no crossing by look 4. For RULE 2: D24 not "better" by look 4 means gate 4 is not met, whatever y08 says |

**Why Q-A and Q-B do not use the round as their unit (EX-ANTE).** D54 made the round the unit for a reason.
Alphas of one round share something that rounds of other arms do not: at least the time slot, and for a
generator also its plan. MECHANISM: UNKNOWN. A Q-A pair puts both members in one round, so whatever the round
shares falls on both sides of the difference. A Q-B claim is about individual frames, so the frame is the thing
replicated.

**The Q-A inference is conditional on this library (DESIGN CHOICE).** The frames are fixed; the fills and the
control draws are random. For "frames like these", the frame-clustered sign-flip test (10,000 flips over library
frames) is printed beside it. It carries no claim.

**"Robust" is 13a's definition.** A frame is robust when it is in the top quintile in R1 and above the
all-frame median in R2. Scores and ties are fixed in §7.1.

---

## 4. Arms and randomisation (rounds 2 onward)

- **Fill modes.** Both use the rules of `framelib/experiments/round1.py`.
  - **own-role** (arm a's rules). A mined frame keeps each slot's historic datasets. A novel frame keeps its
    declared constraints. At least one slot is `fresh_id`.
  - **other-dataset** (arm b's rules).
- **Settings (DESIGN CHOICE).** Every L, P and S/R alpha draws uniformly from R1's grid: 6 cells, truncation
  0.08. The two members of a pair share settings.
  - The Q-C estimand keeps the incumbent's rows inside that grid (79.5 % of its recent cell rows). The rest are
    counted beside it (N2).
- **L rounds (Q-C).** The library in test, filled own-role and fresh.
  - The library in test is the replicated frames of every cohort (§7), plus any validated frames.
  - Allocation is equal across those frames, at most 60 fresh fills per frame per day (DESIGN CHOICE: no frame
    above about 7 % of a 900-fill L arm).
  - The day's L rounds = min(template count, ⌊available fresh fills / 300⌋). With 0 L rounds the day is not a
    shared day.
  - Only fresh fills count. D51 neighbours and re-sims are reported beside (as in D54).
- **P rounds (Q-A).** 150 pairs per round of 300.
  - The library member is an own-role fresh fill of a frame in test.
  - The control is drawn uniformly from the control pool (tick Q6) among structures that:
    - take the same fields in the same slot order;
    - pass `structurally_ok`;
    - re-frame to themselves;
    - have the same ingredient status, counting pinned fields.
  - A fill with no control is dropped before dispatch, and the drop is counted.
- **S/R rounds.** The S half screens today's new cohort: 25 frames × 6 own-role fresh fills. The R half
  replicates yesterday's cohort: every frame, 6 fresh fills.
- **I rounds.** The incumbent exactly as deployed. Its FORGE_ARGS are untouched; D30 and D50 stamp them.
- **The randomiser (tick Q2 = A).** Before each ET day starts (00:00 ET = 11:00 +07), a seeded draw places the
  day's experiment rounds at uniformly random positions among the day's expected round slots.
  - The draw is written to the experiment ledger with its seed before the first round of that day.
  - The seed is 20260924 + the day's ordinal. The kinds are shuffled among the chosen positions.
  - A round that does not run where the draw put it (an outage, a crash) is not re-placed. It is counted as
    missing.
  - Only rounds in the draw count. Hand runs are excluded and counted (D60's rule).
- **Journals.** Experiment rows go to their own journal (F3). Each row carries `meta.experiment`,
  `meta.round_kind ∈ {L, P, S, R}`, `meta.day_draw_seed`, `meta.frame_id`, `meta.fill_mode`, `meta.pair_id`
  (P rounds) and the plan-time covariates of §3.1.
  - The I rounds are the incumbent's own rows in `forge.jsonl`, identified by `meta.round`.

---

## 5. Looks, boundaries, stopping, placebo, minimum rounds

- **Looks (Q-A and Q-C).** After 7, 14, 21 and 28 **shared experiment days**. A shared day is a whole ET day
  with ≥ 1 L round and ≥ 2 I rounds in the estimand (for Q-A: ≥ 1 P round). A look reads every round up to its
  last shared day.
  - Boundaries are the benchmark's: `ARMS_OBF_C` = 2.024296, z = 4.0486 / 2.8628 / 2.3375 / 2.0243, nominal
    two-sided p = 5.153e-05 / 0.004199 / 0.01942 / 0.04294.
  - Reading the data daily adds no look.
- **Rounds excluded from the estimand, counted.** A round with fewer than 50 in-estimand scored rows. If more than
  10 % of either arm's rounds are excluded, that is printed first.
- **Stopping.**
  - Q-C y08 crosses "worse": the L rounds stop and Khoa is told.
  - Each Q-C hypothesis is decided at its first crossing. The L rounds continue until D24 is decided or look 4
    is reached. Continuing after an earlier claim does not change that claim's error rate (EX-ANTE).
  - Q-A decided on all three outcomes, or any "worse": P rounds stop.
  - Q-B B1 fails at R2: new cohorts stop unless Khoa ticks otherwise. Q-A and Q-C continue, because they ask
    other questions.
- **Placebo before look 1 (D54).** The same test is run on the incumbent's own rounds of the first 7 shared days.
  Each day gets b_d I rounds relabelled L at random, over 2,000 draws.
  - A read-out needs a false-verdict rate at one look at 0.05 of ≤ 0.06 (0.05 + 2 SE). Otherwise there is no
    read-out and Khoa is told.
  - Measured now on the desk's historic rounds (§6.1): 0.042–0.051.
- **Minimum rounds.**
  - No Q-A or Q-C verdict before 7 shared days; at most 28.
  - Q-B: R2, one block.
  - Validation of any frame: MIN_ROUNDS distinct post-replication days (tick Q5).

---

## 6. Power and MDR at the real volume

Model (`$P/qc_power.py`). Each round's rate is lognormal around the day's rate. Its sd reproduces the measured
within-day dispersion at 250 rows: σ = 0.245 for y08, 0.411 for LS, 1.06 for D24 (era) and 1.29 for D24
(recent). A day effect with sd 0.15 cancels in the within-day test. Binomial rows: n_L = 300 per L round,
n_I = 200 in-estimand rows per I round. The library arm is the same process at RR × the rate (an ASSUMPTION;
the σ_L × 1.5 variant is below). 4,000 replicates, normal reading of the permutation distribution (way 1). A
Monte Carlo permutation (way 2) checks selected points.

### 6.1 Why the rate form (`$P/qc_size.py`, `$P/placebo.py`)

Null size, better + worse over the four looks (20,000 replicates):

| b of R rounds library | outcome | count form, n 300/200 | rate form, n 300/200 | both, n 250/250 |
|---|---|---|---|---|
| 3 of 15 | y08 / LS / D24 | 0.106 / 0.101 / 0.087 | 0.040 / 0.036 / 0.033 | 0.055 / 0.051 / 0.051 |
| 4 of 15 | y08 / LS / D24 | 0.087 / 0.083 / 0.077 | 0.042 / 0.041 / 0.037 | 0.050 / 0.049 / 0.047 |
| 8 of 16 | y08 / LS / D24 | 0.039 / 0.040 / 0.040 | 0.049 / 0.050 / 0.046 | 0.052 / 0.051 / 0.049 |

- The count form's size depends on the size ratio and the allocation. The rate form stays at or below 0.05.
  - EX-ANTE reading: the relabelling treats rounds as exchangeable, and rounds of different n are not.
  - compare_arms' own docstring flags this as UNMEASURED.
  - For D47 this matters only when the branch's rounds differ in n from the incumbent's. Nothing was changed
    there.
- **Placebo on the desk's own rounds.** 133 rounds on 12 days, dealt to 28 days, 4,000 draws, no effect:

  | way | b/R | y08 | LS | D24 |
  |---|---|---|---|---|
  | rate form, way 1 | 0.27 | 0.044 | 0.047 | 0.051 |
  | rate form, way 1 | 0.5 | 0.050 | 0.042 | 0.044 |
  | count form, way 1 | 0.27 / 0.5 | 0.052 / 0.048 | 0.046 / 0.050 | 0.048 / 0.044 |
  | rate form, way 2 (Monte Carlo permutation, 600 draws, SE 0.009) | 0.27 | 0.047 | 0.055 | — |

  All rounds here are the incumbent's, so they do not differ in n by arm. That is why both forms pass.

### 6.2 Q-C: the smallest RR with ≥ 80 % power of "better" by the look (7 / 14 / 21 / 28 shared days)

| template (per day) | y08 | LS | D24 at 0.11 per 1,000 | D24 at 1.15 per 1,000 | null size (y08) |
|---|---|---|---|---|---|
| T1: 3 L + 12 I | 1.5 / 1.3 / 1.2 / 1.2 | 2.0 / 1.5 / 1.3 / 1.3 | 50 / 10 / 7 / 5 | 10 / 4 / 2.5 / 2.5 | 0.037 |
| T2: 4 L + 11 I | 1.4 / 1.2 / 1.2 / 1.1 | 2.0 / 1.4 / 1.3 / 1.3 | >50 / 10 / 7 / 4 | 10 / 4 / 2.5 / 2.0 | 0.049 |
| T3: 6 L + 9 I | 1.4 / 1.2 / 1.2 / 1.1 | 2.0 / 1.4 / 1.3 / 1.2 | >50 / 15 / 7 / 4 | 10 / 3 / 2.5 / 2.0 | 0.050 |
| T4: 8 L + 8 I | 1.4 / 1.2 / 1.2 / 1.1 | 2.0 / 1.4 / 1.3 / 1.2 | >50 / 10 / 5 / 4 | 15 / 3 / 2.5 / 2.0 | 0.049 |
| T2, σ_L × 1.5 | 1.5 / 1.3 / 1.2 / 1.2 | 2.5 / 1.5 / 1.4 / 1.3 | — | — | — |

- Grid: 1.1, 1.2, 1.3, 1.4, 1.5, 1.75, 2, 2.5, 3, 4, 5, 7, 10, 15, 20, 30, 50.
- In absolute terms, T1 at 28 days: y08 12.3 % → 14.8 %; LS 2.27 % → 2.95 %; D24 at the recent rate 0.11 → 0.56
  per 1,000.
- Way 2 (T2, 300 replicates × 2,000 permutations):

  | outcome | false verdicts at RR 1 | "better" at |
  |---|---|---|
  | y08 | 0.047 | RR 1.2: 1.00 |
  | LS | 0.037 | RR 1.4: 1.00 |
  | D24 (era) | 0.033 | RR 3: 0.997 |

  2,000 permutations cannot reach look 1's nominal p. Live read-outs use up to 100,000.

### 6.3 Q-A (`$P/qa_power.py`): pairs independent given the fill

Positive correlation within a pair would raise power. Values are the smallest RR at 7 / 14 / 21 / 28 days.

| pairs per day | y08, control 12 % | LS, control 2.3 % | D24, control 0.1 % | null size |
|---|---|---|---|---|
| 150 (1 P round) | 1.75 / 1.4 / 1.3 / 1.2 | 3 / 2 / 1.75 / 1.5 | — / 10 / 7 / 4 | 0.036–0.047 |
| 300 (2 P rounds) | 1.5 / 1.3 / 1.2 / 1.2 | 2.5 / 1.75 / 1.5 / 1.4 | 15 / 7 / 4 / 3 | 0.037–0.050 |

Way 2, exact conditional binomial: the same MDRs for y08 and LS at 150 per day.

### 6.4 Q-B (`$P/qb_power.py`): power of 13a's test with 100 frames, R1 3 own-role fills, R2 8

| frame heterogeneity | LS base 5 % | LS base 2.3 % |
|---|---|---|
| Gamma shape 0.2 (doc 10's forge value; curated pools, so an UPPER reference) | 0.99 | 0.77 |
| Gamma shape 1.0 | 0.46 | 0.19 |
| none (false claims) | 0.026 | 0.036 |

- The y_ratio variant is printed beside it; it carries no claim. Its power: τ² 0.018 (doc 10) 1.00; 0.006 1.00;
  0.002 0.58; 0 (false claims) 0.028.
- Way 2, permutation p: 0.957 vs 0.971 (LS, shape 0.2, 3/6 fills); 0.990 vs 0.996 (y_ratio, τ² 0.006, 3/6).
- Reading (EX-ANTE): if frame differences on fresh fields are as large as in the curated history, R2 detects
  them. If they are several times smaller (12 §2: the history never left the role pools), R2 on LOW_SHARPE
  alone probably does not.

---

## 7. Multi-round plan and promotion

### 7.1 Scores and the line [after R1 start, blind]

- **The frame score in a round** is lexicographic: (LS pass rate, mean y_ratio, frame id ascending).
  - y_ratio = Sharpe / the row's LOW_SHARPE limit, clipped to ±2.5.
  - The score is computed over the frame's scored own-role rows of that round.
  - There is no settings adjustment. Settings are randomised per alpha from one grid in every mode, so no
    adjustment is needed for unbiasedness (EX-ANTE).
- **Eligible:** ≥ 3 scored own-role rows in the round (13a's rule).
- **The line** is the top ⌈0.2 × eligible⌉ frames by R1 score.
- **Robust** means above the line in R1 and strictly above the median R2 score of the eligible frames, both in
  the same lexicographic order.

### 7.2 The rounds

| round | when | what | sims | incumbent |
|---|---|---|---|---|
| R1 | 09-24 (13a) | a 320 (own role, 80 frames × 3 and 20 × 4), b 309, c 263 (pairs of b), d 320 (one planner call) | 1,212 in 5 chunks | paused for the block (F2), rest of the day |
| R2 | after R1 is scored (F4: 09-25) | **all 100 frames, equal allocation regardless of rank**. Each gets 8 own-role + 4 other-dataset fills, all `fresh_id` and none used with that frame in R1; mode shuffled within chunks; the 6-cell settings grid. Q-B on own-role rows; the other-dataset rows are reported (13a's Q1 again) | 1,200 in 4 chunks | paused for the block (F2), rest of the day |
| R3 onward (one experiment day per ET day, F4) | from the day after R2 is scored, if Q2 = A | template A: 3 L + 1 P + 1 S/R rounds, interleaved (§4) | 1,500 | the other ~12 rounds, interleaved |
| cohorts | every R3+ day | 25 new frames. Sources, in order: the 34 mined frames the curator dropped (window variants), then new designer frames (after S8 is fixed), then frames mined from the incumbent's recent y08 rows. Each is screened on day t and replicated on day t+1. Frames robust within their cohort join the L library on day t+2 | inside S/R | — |

Equal allocation in R2 is deliberate. Doc 10 §2.2 found that history re-filled frames by their first score, and a
frame's mean then mixed its selecting data with its test data. R2 allocates without looking at R1. Only the line
uses R1.

### 7.3 Promotion (framelib `status` plus the experiment ledger's stage)

`candidate` → *screened* (above the line) → *replicated* (robust) → `validated` → `retired`.

**`validated`** requires all of the following. Items 1 and 8 are gates of RULE 2; the rest are DESIGN CHOICES.
1. B3 is fixed in `framelib/schema.py` (12 §3). Before that, no reliability block is written.
2. Q-B B1 made its claim at R2 ("frame quality is real").
3. The frame is replicated.
4. Its rows **after** its replication day cover ≥ MIN_ROUNDS distinct experiment days and ≥ 30 fresh fills. Its
   screen and replication rows never count here, because they selected it.
5. Its y08 rate over those rows beats the same days' pooled in-estimand incumbent y08 rate. The one-sided exact
   binomial p must survive Benjamini–Hochberg at q = 0.10 across the frames evaluated that day.
6. Its daily point estimate is above the incumbent's on ≥ ⌈2/3⌉ of those days.
7. At least one D24 row is among those rows. This is gate 4 at frame level: the purpose is to clear every
   binding check.
8. Khoa ticks it: `approval.by` = Khoa.

Each reliability round is one distinct (experiment, ET day). It names its comparison arm ("incumbent, same-day
I rounds, 6-cell grid") and its effect (frame rate minus incumbent rate, which is > 0).

**`retired`**, with the reason written:
- Not screened, or not replicated. Automatic, after B3.
- "Fell below the incumbent": over its last 3 experiment days (≥ 30 fills), the one-sided exact p ≤ 0.05.
- "Exhausted": fewer than 3 own-role fresh fills remain.
- "Family submitted": an accepted POST exists in its fingerprint family, and D18 refuses near-dups.

For a validated frame, retirement is put to Khoa as a tick.

---

## 8. Quota, and what the experiment touches (RULE 2 gate 5)

| template (R3+) | experiment sims per day | incumbent sims (of ~5,000) | Q-C y08 MDR, 7 / 28 days |
|---|---|---|---|
| A: 3 L + 1 P + 1 S/R | 1,500 | ~3,500 | 1.5× / 1.2× |
| B: 4 L + 2 P + 1 S/R | 2,100 | ~2,900 | 1.4× / 1.1× |
| C: 6 L + 2 P + 1 S/R | 2,700 | ~2,300 | 1.4× / 1.1× |

The MDRs come from T1, T2 and T3 of §6.2. Their incumbent round counts (12, 11, 9) are approximate for these
templates.

Outside the estimand: 2 D51 neighbour sims per all-check pass. The correlation probe spends no sims.

**What the experiment touches, and what could break (EX-ANTE from code and decisions unless marked):**

| existing structure | contact | status |
|---|---|---|
| F2 / `frames_round.sh` stop-start protocol | Template A needs it up to 5 times a day, at each experiment round boundary | new scheduler code (§10). The lock keeps one loop at a time (RULE 1) |
| D47 / D53 randomiser (composites vs gen 50/50), if live | The frames rounds take about 30 % of the day from both D47 arms, so D47 has fewer rounds and less power | D47 stays valid within day. Its power loss is not measured |
| D60 "excluded rounds are counted on the card" | Frames rows sit in another journal. The card neither sees nor counts them | a card under-reports quota spent elsewhere; printed in the experiment report |
| incumbent harvest, submit, D18, D36 | They read `forge.jsonl` only (`forge/harvest.py` JOURNAL, Mac copy) | isolated **unless** orphan recovery writes an experiment orphan into `forge.jsonl`. 1,554 journal rows carry `recovered_at`, and `recover_harvest.py` is outside version control (D40 note). Which journal it writes a frames orphan to: UNKNOWN. **Check read-only before R2** |
| a submission during the window | An accepted POST changes the incumbent's D18/D36 state and the frames' fresh supply | the reason for §9's default |
| D43 watch, D45 run_config transitions | Repeated systemctl stop/start with unchanged FORGE_ARGS gives the same run_config, so no transition row is expected | not verified; check in the scheduler's dry run |
| `framelib` validator | It accepts copied rounds, negative effects and approval "claude" (12 B3) | must be fixed before any reliability block |

---

## 9. Submission policy for experiment alphas

- **Default: no submit step** (F3, continued).
- Each experiment alpha that clears every binding check is listed. The list shows its decidable gates (D39: G4's
  leg clause and G5–G8), its PROD and SELF readings and its two D51 neighbours.
- Khoa ticks each POST. A ticked POST is logged in the experiment ledger as an **interference event**. Its
  fingerprint family is then excluded from later estimand rows of both arms, and the count is printed.
- Reasons, both EX-ANTE:
  1. The brief says the D39 meaning router is not live. `forge/submit.py` has `meaning_gate` in the Mac tree;
     whether the VPS runs it was not checked in this phase.
  2. A POST changes what the incumbent may plan (D18, D36) in the middle of a comparison.

---

## 10. Preconditions (none built here)

Before R2:
1. The R2 plan builder: a variant of `round1.py` (§7.2). Dry run only; the plan's sha256 is recorded before
   dispatch.
2. The line and score script (§7.1), hashed before any R1 row is read.
3. The plan-time covariates of §3.1 in `meta`.
4. A read-only check of which journal orphan recovery writes a frames orphan to (§8).

Before R3:
5. B3, the validator fix.
6. S8, before any new designer frame is built.
7. The interleaving scheduler (if Q2 = A): offline tests and a dry run on the VPS without `--live`.
8. The analysis script implementing §3 and §5 exactly, with this document's placebo in its test suite. Its sha256
   is recorded in `00_decisions.md` before R3's first row.
9. The control pool with ingredient matching (Q6).

---

## 11. Tick questions for Khoa (round 2 onward; F1–F3 answered the round-1 versions)

**Q1 — Quota share.** How many sims per day go to the experiment from round 3 (R2 = 1,200 under F4)?
- (A) About 1,500 a day (3 L + 1 P + 1 S/R rounds); the incumbent keeps about 3,500. Q-C y08 MDR 1.5× at 7 days,
  1.2× at 28. **Recommended.**
- (B) About 2,100 a day (4 L + 2 P + 1 S/R); MDR 1.4× / 1.1×, and Q-A becomes faster.
- (C) About 2,700 a day (6 L + 2 P + 1 S/R), close to D53's 50/50; MDR 1.4× / 1.1×.
- (D) Off after R2: only Q-B is answered; Q-A and Q-C stay open.

**Q2 — Sharing the day with the incumbent (F2 covered round 1 only).**
- (A) Interleave: experiment rounds at pre-drawn random positions in each ET day. The incumbent is stopped at a
  round boundary for each one (the F2 protocol per round). This is required for Q-C's round-level test.
  **Recommended.**
- (B) One block per day, as in round 1. The incumbent arm is then one planner call per day. Q-C's power cannot be
  computed, because it depends on why rounds cluster (D54: MECHANISM UNKNOWN).
- (C) Pause the incumbent for the whole window. There is then no incumbent comparison, and Q-C is unanswerable.
- (D) Off: no experiment rounds after R2.

**Q3 — Submission policy.**
- (A) No submit step. All-check alphas are listed with their decidable gates, correlation readings and D51
  neighbours; Khoa ticks each POST; each POST is logged as an interference event. **Recommended; F3 continued.**
- (B) Hold every experiment alpha until the window closes, then Khoa ticks.
- (C) Send them through `forge/submit.py` automatically. Not recommended: the brief says the D39 router is not
  live, and a POST changes the incumbent's D18/D36 state mid-comparison.
- (D) Never submit experiment alphas.

**Q4 — What counts as proof (RULE 2 gates 3–4).**
- (A) Gate 3: y08 "better", with the lower repeated-CI bound ≥ 1.5×. Gate 4: D24 "better", tested as y08 → LS →
  D24. **Recommended.**
- (B) Gate 3: any significant y08 gain. Gate 4: D24 "better".
- (C) D24 only; about 5× is needed to show within 28 days.
- (D) Off: measurement only, no RULE 2 use.

**Q5 — `validated`.**
- (A) MIN_ROUNDS = 3 post-replication days, ≥ 30 fresh fills, ≥ 1 D24 row, approver Khoa only, B3 fixed first.
  **Recommended.**
- (B) MIN_ROUNDS = 5, otherwise the same.
- (C) Off: no frame is validated in this window; all stay candidates.

**Q6 — Control structures for Q-A.**
- (A) Round 1's arm-c pool (non-library mined frames), ingredient-matched. Exists. **Recommended.**
- (B) forge.gen draws constrained to the same fields. New code, under RULE 2.
- (C) Both, as two control arms: +300 sims a day.
- (D) Off: Q-A is answered by round 1 only.

**Q7 — New frames.**
- (A) 25 a day: screen on day t, replicate on day t+1, one S/R round. The 34 dropped mined frames go first.
  **Recommended.**
- (B) 50 a day: two S/R rounds.
- (C) Off: test only the first 100.

**RULE 2 status.** The frame library is an open item. Gates 3–4 have not started. The scheduler, the R2 builder
and the analysis script are new code, and each needs Khoa's tick.

---

## 12. Files

Everything is under `$P`. Run each with `PYTHONDONTWRITEBYTECODE=1 python3 -B <script>` from that directory.

| script | output |
|---|---|
| `load.py` | `rows.pkl`: last row per alpha, outcomes, cell and settings |
| `rounds.py` | round tables, dispersion two ways, settings mix; `rounds.pkl` |
| `ingredient.py` | the ingredient split. The meta-string second way ran inline |
| `qc_size.py` | null size of the count form against the rate form |
| `qc_power.py` (`mc` for way 2) | Q-C MDR tables; `qc_power.json` |
| `placebo.py` | the D54 placebo on the desk's rounds |
| `qa_power.py` | Q-A MDR |
| `qb_power.py` | Q-B power |

The R1 plan counts, the ingredient shares and the 85/254 discordant pairs ran inline on `r1/plan_abc.json`.

---

**Tóm tắt cho Khoa (tiếng Việt).**
- Vòng 1 đang chạy theo 13a, không đổi. Tài liệu này đăng ký trước cho vòng 2 trở đi. Tôi viết sau khi driver
  vòng 1 đã khởi động, nhưng chưa đọc dòng kết quả nào của vòng 1.
- Ba câu hỏi được cố định trước dữ liệu.
  - Q-A: khung thư viện có hơn cấu trúc đối chứng khi dùng cùng field không? So theo cặp trong cùng round.
  - Q-B: khung có bền trên field mới hay chỉ ăn may? Vòng 2 lắp lại cả 100 khung bằng field mới, chia đều,
    không nhìn thứ hạng vòng 1.
  - Q-C: thư viện tăng tỉ lệ bao nhiêu so với loop hiện tại? Đơn vị là round, ngẫu nhiên hoá trong từng ngày
    ET, kiểm định hoán vị trong ngày, xem kết quả ở ngày 7/14/21/28 với biên O'Brien–Fleming.
- Nền hiện tại: 0,2 submission mỗi ngày; từ 09-12 có 1 alpha qua đủ 7 check trên 10.748 alpha. 39 % dòng của
  loop dùng field option/short-sale. Nhóm này đạt 0,8 × ngưỡng Sharpe 29 %, nhóm còn lại 1,4 % và qua
  LOW_SHARPE 0/5.557. Vì vậy mọi so sánh đều phải tách theo yếu tố này. Nguyên nhân: chưa biết.
- Hiệu ứng nhỏ nhất đo được, với 3 round thư viện mỗi ngày:
  - y08: 1,5 lần sau 7 ngày, 1,2 lần sau 28 ngày;
  - LOW_SHARPE: 2 lần → 1,3 lần;
  - qua đủ 7 check: chỉ thấy được nếu gấp khoảng 5 lần sau 28 ngày.
  Tăng quota cho thí nghiệm gần như không rút ngắn thời gian. Số ngày mới là giới hạn.
- Mặc định không submit alpha thí nghiệm. Khoa tick từng alpha. Có 7 câu hỏi tick ở §11.
