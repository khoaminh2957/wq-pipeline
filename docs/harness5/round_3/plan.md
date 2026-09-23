# harness5 — round 3 · the day's four: pre-POST correlation screen (Portfolio, 2026-09-09 14:40 local)

Scope (03_design §5, R3): the day's four candidates are measured against each other **before the first POST**
so that no submission kills the next. Inputs read READ-ONLY from the VPS: `state/forge/corr.jsonl` (262
lines, 74 alphas, last read 2026-09-07 02:51), `state/forge/submitted.jsonl` (2 POSTs, both ACTIVE),
`state/pnl_curves/` (3,479 curves; the 21 forge candidates' curves copied to the scratchpad),
`state/forge/scored.jsonl`, `state/pyramid_cell_counts.json`. Labels per RULE 0. Nothing simulated, nothing
written on the VPS, no yaml / unit / arm changed.

## 0. Summary
- **The predictor is exact, and the memory's formula in the task brief is the superseded one.** Memory
  `pnl-distance-predicts-self-corr` (2026-08-05) replaced `0.0662 + 0.9675·pearson(full history)` with plain
  `pearson(daily PnL, last 984 trading days)`. On the forge pairs — an out-of-sample test, every alpha created
  after the window was fixed — the 984-day Pearson reproduces the platform's SELF_CORRELATION in **12 / 12
  labelled pairs to ≤ 1e-4** (median |err| 0.0000, max 0.0001); the old formula misses all 12 (bias +0.025 …
  +0.073, 0 / 12 inside ±0.022). The window sweep re-derives it: median |err| 0.0205 (W = 900), 0.0014 (950),
  **0.0000 (984)**, 0.0001 (1,000), 0.0066 (1,050), 0.0147 (2,493).
- **The book updates late.** A read 119 s after the kqVbg1xP POST still returned the pre-POST maximum (0.4396,
  true 0.6316); reads at +1,578 s and later returned the new one. Latency ∈ (2 min, 26 min] — MEASURED once.
- **Prod = self when the maximum is our own alpha** (883KgXXm: prod 0.852 = self 0.852 = pearson 0.8520).
  A pair over the line therefore fails *both* lines after the first POST. The 18 options_x_short siblings read
  prod 0.79–0.85 *before* kqVbg1xP existed in the book (E5vYKpq1 0.8262 at −19 h) — that maximum is against
  an external production alpha; which one: UNKNOWN.
- **Today's pool cannot supply four**: 21 candidates = 2 mechanism keys; under both lines 3 (vRk095rv and
  kqVbg1xP ACTIVE, qMWbdlmv dead-by-sibling at 0.9668 with vRk095rv); the largest mutually-uncorrelated set
  among the 21 at θ = 0.68 has size **3** (and only because the two ACTIVE ones sit in it). Pairs across
  hypotheses read 0.18–0.25 (n = 38); within one mechanism 0.58–0.97 (p10–p90, n = 172). The screen's job is
  to make four land when rounds 1–2 deliver four mechanisms; it cannot create them.
- Design (§3): pairwise threshold **θ = 0.69** on the 984-day Pearson; effective correlation = max(platform
  reading, predicted pair against every alpha POSTed today); POST order = the existing (cell_gain, score,
  self) order restricted greedily to the uncorrelated set, with alternates; a platform reading younger than
  30 min after an own POST is treated as stale; disagreement rules in §4.

## 1. What was measured
### 1.1 The predictor on the forge pairs (MEASURED, two derivations)
Label = the platform's `SELF_CORRELATION` maximum for alpha X, read after kqVbg1xP entered the book (so the
maximum is the pair (X, kqVbg1xP) — every X is an options_x_short sibling), plus kqVbg1xP's own reading
(maximum = (kqVbg1xP, vRk095rv)). Curves: 2,494 points, 2014-01-02 … 2023-12-29, zero frozen days.

| X | partner | platform self | pearson 984 d (new) | 0.0662 + 0.9675·pearson full (old) | pearson full, raw |
|---|---|---|---|---|---|
| 6XrqWXQP | kqVbg1xP | 0.6159 | **0.6159** | 0.6782 | 0.6326 |
| 883KgXXm | kqVbg1xP | 0.8520 | **0.8520** | 0.8912 | 0.8528 |
| E5vajP2r | kqVbg1xP | 0.6463 | **0.6462** | 0.6987 | 0.6537 |
| MP15omYr | kqVbg1xP | 0.5350 | **0.5350** | 0.5980 | 0.5497 |
| O0rmL0j1 | kqVbg1xP | 0.6040 | **0.6040** | 0.6640 | 0.6179 |
| RRVawW0b | kqVbg1xP | 0.5803 | **0.5802** | 0.6475 | 0.6008 |
| akLP09Gv | kqVbg1xP | 0.6455 | **0.6455** | 0.7015 | 0.6567 |
| d5OlwP5X | kqVbg1xP | 0.5669 | **0.5669** | 0.6397 | 0.5928 |
| e79qeMZN | kqVbg1xP | 0.6434 | **0.6434** | 0.6954 | 0.6503 |
| j23w75Yo | kqVbg1xP | 0.6093 | **0.6093** | 0.6526 | 0.6061 |
| vRkzEqlG | kqVbg1xP | 0.6077 | **0.6077** | 0.6684 | 0.6225 |
| kqVbg1xP | vRk095rv | 0.3224 | **0.3224** | 0.3471 | 0.2903 |
| pwPzpKMj (read at +119 s) | kqVbg1xP | 0.4396 (stale) | 0.6316 | 0.6970 | 0.6520 |

New: 12 / 12 within ±0.022 (11 exact to 4 decimals, one off by 0.0001). Old: 0 / 12; the old formula would have
called akLP09Gv a breach (0.7015 vs a true 0.6455). Raw full-history Pearson: 10 / 12 within ±0.022, bias
+0.02 — the window, not a calibration, is what the platform uses (the memory's claim, confirmed out of sample).
Prior evidence (memory): 136 labelled pairs, max |err| 4.9e-5. Running total **148 / 148**.

### 1.2 Timeline of reads around the kqVbg1xP POST (MEASURED)
POST `posted_at` 2026-09-06 06:19:23 ET (platform `dateSubmitted` 06:19:18; HTTP 201; adjudicated ACTIVE +47 s). Self reads relative to it: +119 s pwPzpKMj
0.4396 (= pre-POST maximum; true pair 0.6316); +1,578 s 6XrqWXQP 0.6159 (= pair); +1,590 s, +1,598 s, +2,643 s …
+12,585 s all = pair. No read exists between +119 s and +1,578 s, so the update latency is bounded, not known.

### 1.3 The pool today (MEASURED, scored.jsonl + corr.jsonl)
21 `candidate` rows: options_x_short 19, usa_short_x_profitability_x_accruals 2; PBO status `pending` on all
21 (curves not yet complete for the pools); correlation numeric on all 21; under both lines 3. Pairwise Pearson
(984 d) among the 21: 210 pairs, min 0.170, p25 0.569, p50 0.905, p75 0.949, max 0.999; 72 / 210 under 0.68.
Largest mutually-uncorrelated set at θ 0.60 / 0.68 / 0.70: size 3 in each case, e.g. {6XrqWXQP, 883KgXXm,
qMWbdlmv} — and 883KgXXm is at 0.852 with the ACTIVE kqVbg1xP, qMWbdlmv at 0.9668 with the ACTIVE vRk095rv, so
the real number of POSTable alphas today is **0**. Pyramid counts (live read 09-09 13:58): USA/d1 Short
Interest 2, Sentiment 1, Insiders 2, News 2, Social Media 0, Imbalance 0 — open cells exist; candidates do not.

## 2. What the screen must guarantee (EX-ANTE, from the platform facts on record)
1. Each of the four passes the platform lines at its own POST: prod < 0.70 and self < 0.70 as the platform
   computes them **at that moment**, with the earlier POSTs of the day already in the book.
2. Because prod = self = pair when our own alpha is the maximum (§0), the number that decides #k after #1..#k−1
   is `max(platform_prod_k, platform_self_k, max_{j<k} pair(j, k))`, where the platform values are the
   *pre-day* readings and the pairs are computed locally.
3. Q20: ≥ 3 distinct dataset sets among the four (2 + 1 + 1 at most), applied to the *planned* set, not only
   to the posted history (`submit.eligible` today checks history only; the set rule is added).
4. Q19: no weekly rule; siblings of one mechanism may both go if their pair is under θ — the platform allows
   it (6XrqWXQP vs kqVbg1xP 0.6159 would pass self; it fails prod 0.8166 against the external book).
5. A POST is irreversible; a 403 spends the alpha (memory `submit-403-spends-the-post`). The screen fails
   closed: unmeasured → hold; stale → assume the worse number.

## 3. The screen — which pairs, the threshold, the order
### 3.1 Which pairs
`E` = `forge.submit.eligible(...)` output at the start of the quota day (platform PASS, turnover band, DSR,
PBO not failed, MATCHES_PYRAMID PASS, prod/self measured and under the lines, not yet posted). Compute the
984-day Pearson for **every pair in E × E** (|E| ≤ 30 → ≤ 435 pairs, milliseconds; curves already in
`state/pnl_curves` because harvest fetched them for DSR; a candidate without a curve is held `no-curve`,
never assumed uncorrelated). Pairs against the ACTIVE book are **not** computed locally — the platform's
self/prod maximum already covers the whole team book, which cannot be enumerated (`GET /teams/{id}/alphas`
403; memory). Frozen-curve rule from `tools/self_corr_predict.predict` applies (> 20 % zero-change days →
`no-curve`); all 21 forge curves have 0 such days.

### 3.2 Threshold
**θ = 0.69** on the predicted pair. Rationale, EX-ANTE: the self line is 0.70 and the predictor's worst error is
1e-4, so the margin is 100× the error; the prod line is recomputed at submit time and has passed at 0.7077 /
0.7078 and failed at 0.7031 / 0.7320 (memory `exact-prod-corr-metric`), i.e. ± 0.005 noise around 0.70 — 0.69
sits under every observed refusal and under the unexplained 0.6999 UNSUBMITTED case (Xg8OZYQ1). A pair at
0.69–0.70 is not "worth a try": the cost of a wrong try is the alpha. The conservative alternative for Khoa to
tick is θ = 0.65 (costs nothing today: no cross-mechanism pair in the pool exceeds 0.25).

### 3.3 Order of POSTs (greedy, alternates kept)
1. Sort `E` by the existing key `(−cell_gain, −score, self)` (submit.py C20) with the second-best rule (C16)
   applied inside a hypothesis.
2. Walk the list: accept candidate `c` if (a) `pair(c, s) < θ` for every already-accepted `s`, (b) the
   dataset-set rule 2 + 1 + 1 still holds for accepted ∪ {c}, (c) its mechanism key is not already accepted
   unless (a) holds (Q19). Stop at four. Continue walking to collect up to four **alternates** that pass (a)–(b)
   against the accepted set, so a refusal can be replaced without recomputing.
3. Within the accepted four, POST in acceptance order (highest cell_gain first). Rationale: if the day ends
   early (auth, quota, a 403 stop), the cells with the largest need are filled first; correlation does not
   depend on order once (a) holds for all pairs.
4. Between POSTs: wait for the previous POST to resolve (`GET /alphas/{id}/submit` → 404 then `status`; 170–
   215 s typical; memory `submit-inflight-vs-never-posted`). Do **not** wait for the platform's correlation
   store (up to 26 min): the local pair stands in for it (§2 item 2).
5. Fresh-read rule (C29, 30 min) stays, with one change: a platform reading taken **less than 30 min after any
   own POST of the day** is marked `stale-wrt-post` and is used only through `max(platform, predicted pairs)`.
6. After the last POST + 30 min: re-read self/prod of all four and append `{alpha, partner, predicted, platform,
   read_at, post_at}` to `state/forge/pair_audit.jsonl`. This is the running validation of the predictor
   (148 / 148 today); the Verifier reads it every round.
7. A correlation 403 (body names SELF_CORRELATION or PROD_CORRELATION) stops the day's POSTs immediately —
   stricter than C29's MAX_403_PER_WEEK = 1, because the second 403 would spend a second alpha on the same
   unknown. The body's value is written to the audit file beside the predicted pair.

### 3.4 Where it lives (Builder, one layer — Q16)
`forge/portfolio.py` (new): `pair_matrix(curves, ids)`, `days_four(elig, curves, theta, today_sets)` →
`(accepted, alternates, held: Counter)`, `effective_corr(cand, platform, posted_today, pairs)`.
`forge/submit.main` calls `days_four` after `eligible` and before `choose`; `held` gains the reasons
`pair-corr`, `no-curve`, `dataset-set-planned`, `stale-wrt-post`. Tests: synthetic curves (three constructed
series with known Pearson, a frozen series, a short series) + an integration test on the 13 rows of §1.1 that
runs when the curves are present in `state/pnl_curves` (they are, on the VPS) and asserts ≤ 1e-3 on the 12
clean pairs and the stale flag on the 13th. `tools/self_corr_predict.predict` is reused, not re-implemented.
Nothing in `forge/hypotheses`, `forge/composites`, the unit or the VPS changes for this layer.

## 4. When the screen and the platform disagree
The platform is the only truth for a gate (Q10) — but a *reading* of the platform is a measurement with a
known staleness and a known scope. The rules, in order:

| case | observation | verdict | action |
|---|---|---|---|
| A | platform self/prod for `c` **above** every predicted pair (and above θ) | the maximum is an alpha we did not model (team book, external production) — no predictor failure | hold `c` (`corr-over-line`); nothing to fix |
| B | platform **below** a predicted pair by > 0.001, read < 30 min after the partner's POST | stale store (measured: +119 s returned the old maximum) | use the predicted pair; re-read after 30 min and log to `pair_audit` |
| C | platform **below** a predicted pair by > 0.001, read ≥ 30 min after the partner's POST | predictor failure (window or curve assumption broken for this pair) | hold `c` for the day; write `pair_disagree`; Verifier re-runs the window sweep on that pair before the next day; the platform's number is not used to POST until the disagreement is explained |
| D | platform returns `200-empty (computing)` for `c` | unmeasured | hold (existing rule); never POST on a local number alone |
| E | POST of `c` returns 403 naming SELF_/PROD_CORRELATION with a value | the platform adjudicated | stop the day (§3.3 item 7); if the value equals a predicted pair we accepted under θ, the θ margin was insufficient — report to Khoa with the numbers, do not auto-tighten |
| F | POST of `c` resolves `UNSUBMITTED` with no error body | unexplained (seen once, Xg8OZYQ1 at 0.6999) | treat as E without a value; `GET /alphas/{id}/submit` first (in-flight vs resolved) |

Two things this table does not do: it never overrides a platform *refusal* with a local number, and it never
POSTs on a local number when the platform reading is *missing*. The local number only ever makes the screen
stricter (max with the platform) or fills the interval in which the platform's own store is behind its book.

## 5. Measurement for the round (Q4–Q6, honest about what one day can show)
- Rung: submissions per 5,000-sim day on the day the screen is live (rung 3 = 2.75). The screen changes
  nothing unless ≥ 2 candidates from ≥ 2 mechanisms are eligible on the same day — today 0. So the round's
  funnel row that the screen owns is **"candidates eligible at reset / accepted by the screen / POSTed /
  ACTIVE"**, plus `pair_audit` exactness (must stay ≤ 1e-3) and correlation-403s (must be 0). A day with < 2
  eligible candidates is a null day for this layer and is reported as such, not as a pass.
- Confounds: the pool's composition (rounds 1–2), auth idle time, and the external prod maximum (0.79–0.85 on
  the one productive mechanism) — none of which the screen touches. The sibling-kill it prevents has already
  happened once (qMWbdlmv), so the counterfactual on that day would have been 0 → 0 anyway (prod line).

## 6. Preconditions the other roles owe this layer
- Round 1–2: ≥ 4 mechanism keys with a candidate under the external prod line on the same day (today: 1
  mechanism under 0.71 — usa_short's, exhausted; options_x_short's 18 read 0.79–0.85 externally).
- Harvest: PBO pools completed (all 21 candidates read `pending`; `submit.eligible` holds `pbo-pending`).
- Operator: the four are pre-screened ≥ 60 min before the 11:00 local reset and the session has ≥ 40 min.
