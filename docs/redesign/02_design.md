# Redesign — 02. Architecture v0 (2026-08-31, before the CDP survey; to be amended)

Name: **`forge/`** — a new package. The old generator (`climb.py` moves/ladder) retires; the
infrastructure it sat on (auth chain, outbox/notifier, `layered_sim` runner, `climb_submit`
POST path with record-first + m6, adjudication recorder) is kept and called from here.

Every module below states its PURPOSE and the MEASUREMENT that justifies it (RULE 2 gates 1–2).
Gate 3 (proof over many rounds) is the canary + the 10,000-sim milestone; gate 5 (no conflict)
is the "touches" list per module.

## 0. One picture

```
 hypothesis library ──► target cells ──► candidate factory ──► pre-sim gates ──► sim runner
 (offline, by me)      (pyramid API)     (templates × fields)  (novelty, dedup,   (existing
                                                                op-cap, budget)    layered_sim)
                                                                                      │
 daily digest ◄── submitter ◄── correlation probe ◄── robust scorer ◄── result journal
 (outbox)         (existing      (DSR-gated,           (DSR, platform      (existing jsonl)
                   POST path)     read at +120s)        gates, turnover,
                                                        second-best)
```

## 1. Hypothesis library — `forge/hypotheses/*.yaml`
PURPOSE: every alpha starts from a written economic hypothesis (C5); the loop has no LLM (C7),
so hypotheses are DATA authored offline and expanded deterministically.
MEASUREMENT: playbook pass rates 40% (fundamental templates) vs 0.64% (our random grammar).
Schema (one file per hypothesis):
```yaml
id: news_neg_shock_reversal_v1
category: News            # pyramid category this targets
mechanism: "Stocks with a spike in negative-news intensity underreact for 2–10 days;
            buy the decile with the largest 5d rise in negative score, sell the smallest."
counterparty: "Attention-constrained investors selling into headlines."
expected_sign: +1         # sign of alpha vs forward return
datasets: [ai_news_scores, news_sentiment_transfer]     # candidates; 1/√users weighting picks
field_roles:
  signal: {pattern: "negative_score_*", type: MATRIX}
template: "group_rank(ts_delta({signal}, {w}), {group})"   # ≤5 ops per leg
params: {w: [5, 10, 20], group: [subindustry, industry]}
settings: {neutralization: [SUBINDUSTRY, INDUSTRY], decay: [0, 4, 8], truncation: 0.08}
regions: any            # cell targeting decides; d0 and d1 both (C11)
notes: "SOURCE: Tetlock 2007 media pessimism; POST-HOC: none yet."
```
Legs may be composed (≤3 legs, `+`/`-` of ranked legs, no price carrier — C30). Complexity is
not capped but is scored (C6) via op_count in the robust score.

## 2. Target cells — `forge/cells.py`
PURPOSE: multi-region driven by EMPTY pyramid cells (C10, C20).
INPUT: `/users/self/activities/pyramid-alphas` (key `pyramids`: category, region, delay,
alphaCount) — 201 cells with alphaCount<3 today (USA/d1 has 6 empty: Imbalance, Insiders, News,
Sentiment, Short Interest, Social Media). Plus `/data-sets?region&delay&universe` for the
category ↔ dataset join (fields: category, userCount, alphaCount, fieldCount, coverage,
pyramidMultiplier).
OUTPUT: a ranked list of (region, delay, universe, category) with weight
  w = (3 − alphaCount) × pyramidMultiplier × has_catalogue × has_hypothesis.
TOUCHES: replaces `pool_gate.next_segment` rotation; field catalogues per segment already on disk.
BUILT 2026-09-04 (`forge/cells.py`, survey extended to 11 segments): 211 cells, 201 empty, **136
reachable** (catalogue on disk). No catalogue yet for DEU, GBR, MEA (5 pairs). Top weights are
CHN/d1 Other, JPN/d0 News, JPN/d0 Sentiment (multiplier 1.9), then CHN/d0 and JPN/d0 at 1.8; the
six empty USA/d1 cells carry 1.0–1.4. OPEN (tick): d0 cells pay 1.7–1.9× but demand Sharpe 2.69
vs 1.58 — the weight does not yet price that difficulty; no number is invented for it, the
per-cell yield is reported in the digest instead.

## 3. Candidate factory — `forge/factory.py`
PURPOSE: expand hypothesis × cell × fields into concrete (formula, settings) candidates.
RULES: dataset weight 1/√userCount (C9); both delays (C11); parameters from the yaml grid;
`unit_safe` reused from climb.py; platform op-limit 64 respected; MATRIX vs VECTOR fields routed
(VECTOR → one of the 7 platform vec ops `vec_avg|vec_sum|vec_count|vec_max|vec_min|vec_stddev|
vec_range`, chosen per hypothesis — inventory: VECTOR 179 vs MATRIX 131 behind the empty cells).
BUDGET: ≈20 candidates per hypothesis-cell per round (AlphaBench: EA-20 sweet spot); 5,000/day cap.
BUILT 2026-09-04: `forge/factory.py` + `forge/hypotheses.py` + 19 hypotheses in
`forge/hypotheses/*.yaml` (News 5, Sentiment 3, Social Media 2, Insiders 1, Short Interest 2,
Institutions 1 shared, Earnings 2, Option 3; every one cites its source; fields verified against
the USA/d1 catalogue). DRY RUN on the VPS (no POST): 63 reachable cells have a hypothesis;
**1,536 candidates** after the pre-sim gates (cap 20 per hypothesis-cell; 0 not-novel, 0 duplicate
against 23,321 journalled ids). Dead as written: the 3 Option hypotheses (USA/d1 Option is not
empty; USA/d0 has only option6/option8) and `sentiment_premarket_negative_d0` (its dataset is not
in the d0 catalogue) — to be re-targeted or dropped, not silently kept.

## 4. Pre-sim gates — `forge/gates.py`
- **Novelty (hard, C12):** signature = (dataset ids, mechanism id, main transform op, region,
  delay). Reject if signature ∈ submitted/ACTIVE book (248 ACTIVE alphas seeded from
  `/users/self/alphas?stage=OS`) or already simulated ≥ N times without progress.
- **Dedup:** normalised-formula hash against the 43k-row journal (never re-sim an identical).
- **Op cap:** > 62 ops refused (platform 64).
- MEASURED 2026-09-04 (43k journal rows): the platform's `limit` differs by segment and must be
  read from the row, never hard-coded. d1: LOW_SHARPE 1.58, LOW_FITNESS 1.0, LOW_2Y/IS_LADDER
  1.58 or 2.02. **d0 (EUR/TOP2500): LOW_SHARPE 2.69, LOW_FITNESS 1.5, LOW_2Y 2.69, IS_LADDER
  2.69, plus `D0_SUBMISSION`.** JPN adds `LOW_INVESTABILITY_CONSTRAINED_SHARPE`.
  LOW_SUB_UNIVERSE_SHARPE's limit is per-alpha (ratio gate). CONCENTRATED_WEIGHT limit 0.1.
  Consequence: on d0 the platform bar (2.69) sits ABOVE the DSR pass line (1.74), so DSR is not
  the binding gate there; on d1 it is (1.74 > 1.58).
- MEASURED: the `MATCHES_PYRAMID` check dict carries `pyramids: [{name, multiplier}]` and
  `effective` — the platform's own cell assignment for every simulated alpha. The scorer stores it;
  the submitter orders by it (C20), never by our intended category.
- **Budget:** daily counter; stop at cap; per-cell fair share.

## 5. Sim runner — existing `layered_sim.py` (kept)
Batches of ≤300 candidates, concurrency 9×10, `keep_jar_fresh`, journal append. No change.

## 6. Robust scorer — `forge/score.py`
PURPOSE: rank what to measure and what to submit; turn "OS good/bad" into ex-ante proxies since
OS is unobservable (C25; verified: `os.osISSharpeRatio` is null on all 248 ACTIVE alphas).
INPUTS (all available per row): sharpe, fitness, turnover, drawdown, margin, book counts, check
values (LOW_SUB_UNIVERSE_SHARPE value, IS_LADDER_SHARPE value), op_count, PnL recordset.
GATES (hard): every platform check PASS (C14, no extra margin); turnover 2–25% else decay retry
(C15); **DSR ≥ 0.95** (C13) computed from daily PnL:
  SR₀ = √V[SR]·((1−γ)Z⁻¹(1−1/N) + γZ⁻¹(1−1/(N·e))), N = candidates in the hypothesis-cell pool,
  DSR = Z[(SR−SR₀)√(T−1)/√(1−γ₃SR+(γ₄−1)/4·SR²)]. Offline prototype on 3,058 stored curves:
  luck ceiling 1.22 (N=300), pass line ≈ annual Sharpe 1.71 at T≈2,500.
SCORE (soft, for ordering): + DSR, + sub-universe/sharpe ratio, + ladder/sharpe ratio (q),
  − op_count, − drawdown, + years-positive fraction (from PnL), − novelty distance to book.
**Second-best rule (C16):** within a hypothesis, if top-2 scores differ < 10%, promote #2.
TOUCHES: `climb.tier()` semantics retire; `climb_submit.candidates()` reads forge's queue.

## 7. Correlation probe — `forge/probe.py` (rewrite of probe.py)
PURPOSE: measure every DSR+novelty passer (C17); no fixed cap.
FACT: a GET starts compute and returns empty; numbers land ≈90–120 s later; results EXPIRE and a
later GET restarts compute (measured 2026-08-29). So: trigger → wait 120 s → read once → record;
re-read only if empty; never re-trigger a stored reading. Runs in the background alongside sims
(already the case). Rate: 60 req/min shared bucket; pace 1.1 s.

## 8. Submitter — existing `climb_submit.py` path, new selector
ORDER (C20): empty pyramid cells first (alphaCount<3, higher multiplier first), then robust
score; lower self-corr first within a cell. RULES: all gates PASS + corr under platform lines
(C18) + DSR ≥ 0.95 + MATCHES_PYRAMID PASS + **1 submit per signature per week (C19)** +
second-best. Re-read correlation ≤ 30 min before POST (C29). 403 budget: ≤1/week, else switch
to hold-for-approval and notify. Record-first, flock, m6 — unchanged.

## 9. Auth redirect — `forge/authlink.py` (C22)
One stable URL `http://160.25.88.163:<port>/a/<48-char token>` → 302 to the live persona link;
if none live, mint (respecting the shared hourly mint lock; a **second** per-hour mint is allowed
ONLY for a request carrying the token — operator-present case) then redirect. Rate-limit by IP;
log every hit; the Discord hourly message carries this URL instead of a 10-minute link.

## 10. Notifications (C24) — existing outbox
m1 hourly (now the stable URL), m6 per POST, **m12 daily digest at 11:00** (sims, submittable,
submits, cells filled, submittable/1,000 sims, DSR pass rate, queue depth), **m13 hypothesis
queue** (new batch loaded / < 5 hypotheses left).

## 11. Tests & evaluation (C26–C28)
- Offline backtest of every gate on the 43k journal + 3,058 PnL curves (must select the 9
  historical tier-4s and reject the degenerate books) — before any live sim.
- Dry run of the whole chain with `--live` off.
- **Canary: first 200 live sims with Khoa watching**, then unattended.
- Daily regression run on the VPS (systemd timer) + Discord alert on red.
- Milestone: after 10,000 sims ≥ 10 submittable and ≥ 2 new pyramid cells; else report + tick.
- Control = the measured baseline (00_baseline_and_research.md); no parallel climb.

## 11a. Build status and offline backtest (2026-09-04)

BUILT (Mac, 67 forge tests + 178 tools tests green; shipped to /opt/wq/forge, NOT started):
`forge/{dsr,signature,cells,hypotheses,factory,gates,score,harvest,probe,submit,runner,digest}.py`,
20 hypothesis files, `vps/forge_loop.sh`, additive `layered_sim.run(batch=…)` path (climb path
byte-identical, 178 tests), `msgcat.m12_forge_digest` / `m13_hypothesis_queue`.

DRY ROUND on the VPS (seed 424242, no POST): 300 constructions, 31 multisim parents, 8 cells
(JPN/d1 News 60, USA/d0 News 44, JPN/d0 News 40, USA/d0 Sentiment 40, CHN/d0 News 40, CHN/d1 News
40, USA/d0 Option 20, CHN/d1 Institutions 16). The dispatcher previewed the bodies and spent nothing.

OFFLINE BACKTEST (`forge/offline/backtest_gates.py`, 24,721 journal rows with checks):
- Q3 degenerate books: 9,793 rows with CONCENTRATED_WEIGHT adverse → 9,793 rejected. ✔
- Q1 historical forge-candidates: NOT MEASURABLE YET — 1,341 rows pass the platform gates and the
  turnover band, but **0 of the 3,058 stored PnL curves belong to any of these rows** (the curves
  are the old funnel's). A background fetch of up to 400 curves for those rows is running.
- Q2 CALIBRATION — the finding that needs Khoa's decision: of the 47 ACTIVE (platform-accepted)
  alphas with a stored curve, **6 pass DSR ≥ 0.95 at N = 300; 41 fail** (their Sharpes 1.6–2.1,
  DSR 0.3–0.85). V[SR] here is the robust (IQR) spread of the whole journal, sd 0.62 annual → luck
  ceiling ≈ 1.8, pass line ≈ 2.3. CONFOUND: the pool. With the stored curves' own spread (sd 0.42)
  the ceiling is 1.22 and the pass line 1.74, and 51% of stored curves pass. In forge the pool is
  one hypothesis-cell (N ≈ 20–100, homogeneous), whose spread is unmeasured until the canary runs.
  MY OWN ERROR, corrected: the first run used the plain sd (3.89 annual — broken formulas report
  absurd Sharpes), which put every ACTIVE alpha at DSR 0.0; `var_sr_from_annual_sharpes` is now
  IQR-based and tested to agree with the plain sd on clean pools.
- Q1 (partial, 230 platform-pass rows with a fetched curve, mostly climb.jsonl): platform Sharpe
  p50 2.22; kurtosis p50 13 (fat tails, the DSR denominator matters); T 2,493. **The verdict is
  decided by the POOL, not by the alpha:** with N = the whole climb journal as one pool (13,018,
  SR0 3.03) 0 of 230 pass; at the same spread with N = 100 → 77 of 230; with N = 20 → 173 of 230.
  (The 13,018 pool is my backtest's fault — climb rows carry no `cycle` in meta so the key
  collapsed; corrected to per-round. The sensitivity is the real result.)
- Q1 final (400 platform-pass rows with fetched curves): climb rows carry no cycle/seed in meta,
  so a round can only be approximated by (file, round, hour); under that approximation 18 of 400
  pass, with pool sd p50 1.54 annual (hour buckets mix rounds — the approximation is poor). The
  sensitivity above (N=20 → 75%, N=100 → 33%) is the usable result; the exact per-round number
  for the old generator is not recoverable from its journal.
- So the DSR gate as ticked (C13, hard ≥ 0.95) refuses most alphas the platform accepts whenever
  the selection pool is large. Forge pools are per (hypothesis, region, delay, category); whether N
  counts one round (≈20) or the cumulative history of that pool (grows 20 per round) changes the
  yield 2–3×. That definition — and whether DSR stays a hard gate at all — is Khoa's decision,
  asked as a tick with these numbers, not decided here.

## 11b. Khoa's ticks and the canary (2026-09-04 12:49)
Ticked: canary NOW (climb stopped and disabled, not restarted); DSR pool N = cumulative per
hypothesis-cell (strict); every round half d0 / half d1 (leftover flows to the other side);
forge notifications off until asked. Canary: `N=200 ROUNDS=1 ./forge_loop.sh`, seed 1788501007,
started 12:50:07 — 200 constructions, 20 parents, cells JPN/d0 News 40, USA/d0 Sentiment 40,
CHN/d0 News 20, CHN/d1 News 40, JPN/d1 News 60. RESULT (MEASURED, round 1788501007, 13:12): 200 posted, 197 landed, 3 GUARD-REFUSED (1.5%; the
platform returned one child twice for sibling pairs that differed only by the `_full_` field alias —
those twins are now dropped from the library, MECHANISM UNKNOWN). UNITS errors 0. The chain ran
unattended end to end: harvest scored 197 (all `fail`), probe 0 pending, submit 0 eligible.
**0 of 197 passed the platform gates; Sharpe max 0.79, p50 −0.14.** The failure is structural,
not statistical: `longCount` p50 = 20 names (p10 = 3). Every VECTOR-derived news signal
(`vec_count`/`vec_sum`/`vec_avg` on news29/news73) is NaN for names without an event that day, so
after `group_rank` only the few names with events carry a position → CONCENTRATED_WEIGHT value
0.5–1.0 against a limit of 0.1 (163 of 197 fail), high turnover (p50 0.39, 64 rows > 0.7), and
LOW_SUB_UNIVERSE fails. The one dense MATRIX hypothesis (`sentiment_weekly_continuation`, USA/d0)
built a full book (1,374 names, 0 concentration fails) but had no signal (Sharpe p50 0.01).
POST-HOC, not a mechanism: on CHN News all 40 rows of two hypotheses are consistently negative
(Sharpe −1.8 to −2.5, 40/40) — the attention-reversal sign from US retail literature runs the
other way there; a sign-flipped POST-HOC hypothesis is a candidate for a later round, after the
density fix, never before.
Per hypothesis-cell pool sd of Sharpe: 0.07–0.33 annual on JPN/USA (SR0 at N=300 = 0.2–0.9),
0.27–0.64 on CHN — the number the DSR gate needed; on these pools the gate is mild.

## 11c. Khoa's decision after the canary (2026-09-04 13:20)
Ticked: **stop simulating; rewrite the library first — dense MATRIX hypotheses first (fundamental /
analyst / model in JPN, CHN, EUR …), VECTOR ones later**; no POST-HOC sign flip (EX-ANTE only).
Done: the eight VECTOR hypotheses are parked in `forge/hypotheses/later/` (not loaded); the
`density` construction stays in the factory for when they return. Next: author dense-MATRIX
hypotheses from `docs/redesign/inventory_dense.json` (field descriptions first), dry-run, then ask
for the verification batch. No process spends simulations until then (wq-climb disabled, forge loop
not started).

## 11d. Dense-MATRIX library (2026-09-04 14:00) — written, dry-run, NOT simulated
23 new hypotheses from field descriptions in `docs/redesign/inventory_dense.json`, every one with
an EX-ANTE/SOURCE citation: accruals (fundamental44, fundamental89, fundamental93), balance-sheet
bloat / issuance / analyst optimism (fundamental90, other401), credit distress (model28, model25)
and SmartRatios safety (model36), analyst dispersion (analyst_consensus) and revisions
(analyst_factor_signals), earnings-call language (fundamental45), insider ratios and net value
(insider_feats, insider_matrix, insider_trx_matrix), Wikipedia attention (other571), dividend
prediction (other424), intangible intensity (model313), Stock Reports scores (model56 /
fundamental86), quality composites (model16), CHN asset growth and turnover (fundamental5),
receivables/inventory growth and cash-flow improvement (ml_factor_proj), newswire negative tone
(finnews_nlp_scores). Rejected on description: analyst_earnings_ibes and model242 (price fields —
C30), ml_factor_proj price fields. Eight VECTOR hypotheses parked in `later/` (density fix kept).
REACH (VPS, all catalogues): 34 active (3 Option ones unreachable — their datasets exist only in
USA/d1 Option, which is not empty), **92 reachable cells, 45 cells with candidates (d0 13, d1 32),
grid 5,696**. Dry plan 300 = d0 150 / d1 150 over JPN/d0 Model+Fundamental, USA/d0
Sentiment+Other, CHN/d1 Fundamental, JPN/d1 Analyst+Model+Other; 30 parents; gate refused 5
journalled duplicates. RESULT (MEASURED, round 1788503253, 13:27–13:44): 300 posted, 290 landed, 10 FAIL (all
`analyst_optimism_reversal` on JPN/d0 — platform FAIL with an empty message; now auto-quarantined
so no round re-simulates a pair that only ever fails). **0 of 290 passed the platform gates;
Sharpe p50 −0.04, max 0.75.** The construction fix worked: CONCENTRATED_WEIGHT fails 4 of 290
(canary 163 of 197) and the books are full; turnover collapsed to p50 0.027 (quarterly signals
carried by ts_backfill barely trade; 10 rows sit on the LOW_TURNOVER line). Best hypothesis-cells:
insider_net_value_eur USA/d0 max 0.75, intangible_intensity JPN/d1 0.71 (p50 0.44),
analyst_optimism JPN/d0 p50 0.46, equity_issuance JPN/d0 p50 0.35. Pool sd of Sharpe 0.02–0.63.
POST-HOC observations, recorded and not acted on (Khoa: EX-ANTE only): three hypothesis-cells ran
consistently AGAINST their sign — chn_asset_growth_reversal CHN/d1 20/20 negative (p50 −1.65,
|max| 1.77), sentiment_abnormal_coverage_reversal USA/d0 20/20 (p50 −0.58), analyst_forecast_
dispersion JPN/d1 20/20 (p50 −0.44); plus CHN News 40/40 from the canary.
Two rounds, 487 simulations, 0 platform-pass: no single-field hypothesis has come within half of
the d1 bar (1.58) on these cells, and the d0 bar is 2.69. Next step is Khoa's tick (11e).

## 11e. Ensemble mechanism (Khoa's tick 13:50) — built, dry-run, NOT simulated
RULE 2 gates. (1) PURPOSE: lift single-field legs (max Sharpe 0.75 on these cells, 487 sims)
over the platform bar by combining independent legs. (2) PROVENANCE: the 9 historical tier-4
alphas were ensembles of simple legs (00_baseline §A3); the ensemble-leg-scale law (one
normaliser per leg, weights ≤ 1) took an earlier family from 0/754 to 18/164 zero-fail —
POST-HOC on old data; the next round is the experiment. (5) CONFLICTS: none with the gates
(ensembles carry `meta.ensemble`, their own mechanism key `ens:a+b`, and the union signature);
leg selection is in-sample and the DSR pool does not see it — stated in the module docstring.
BUILT: `forge/ensemble.py` (best measured leg per hypothesis on a cell, Sharpe ≥ 0.2, EX-ANTE
sign kept, one leg per dataset, 2–3 legs, weights {1, 0.5}), `runner --ensembles off|add|only`.
DRY RUN (VPS, from the two rounds' journal): **only 4 ensemble candidates exist** — 2 cells have
two qualifying legs (USA/d0 Other: insider_net_value_eur 0.75 + finnews 0.22; JPN/d1 Model:
intangible 0.71 + credit 0.21). EX-ANTE arithmetic, not a finding: two independent legs of 0.7
and 0.4 combine to about 0.8; reaching 1.58 from 0.5-Sharpe legs needs ~10 independent legs.
The bottleneck is leg quality, not the combiner.
STANDING MEASUREMENT THE OPERATOR MUST WEIGH (memory, 2026-08): carrier-free alphas were 0/2,039
zero-fail with median ladder −0.02, against 0.53 with a light price carrier; "the carrier IS the
edge" (anti-corr M1). C30 bans the price carrier. Two rounds of the redesign (487 sims, 0 pass,
max 0.75) are consistent with that history. MECHANISM: UNKNOWN; the choice is Khoa's.

## 11f. Carrier-free levers (Khoa 14:05: "Tìm mọi cách ko phụ thuộc carrier") — built, dry-run, NOT simulated
Every lever below keeps C30 (no price carrier). Labels: EX-ANTE = from documentation/literature;
SOURCE = a named external source; nothing is measured on this data yet.
1. **Classic fundamental ratios on the non-USA Fundamental cells** (7 hypotheses, exact field ids):
   profitability (ROE, operating income/assets), asset growth, statement accruals, capex/assets,
   R&D intensity, operating-margin change, debt issuance — GLB (fundamental7), EUR (fundamental72),
   ASI/JPN (fundamental6 variants). SOURCE: the gold-medal playbook template
   `group_rank(ts_rank(ratio,126), subindustry)`, used verbatim as one of the templates.
2. **Template variants per hypothesis** (`template:` may be a list): 18 hypotheses now also try
   `group_rank(ts_rank(ts_backfill(x,63), w), g)` beside the backfill form.
3. **Neutralization sweep**: STATISTICAL added to 24 hypotheses (community consensus: stronger
   neutralization raises Sharpe of slow signals — SOURCE, community_alpha_tips §Neutralization).
4. **Ensembles** (11e) extended: same-dataset multi-field legs and cross-category legs of the same
   region/delay (the target-category leg always present → the cell is still filled; a pv-dataset
   leg is refused by construction).
5. **Quarantine** of (hypothesis, cell, field) triples the platform refuses outright.
Reach after the changes: 41 hypotheses, 45 cells with candidates, grid 11,556 (classic ratios:
profitability 192 on GLB/EUR d1, accruals 72, capex 72, R&D 96 on JPN/GLB/EUR/ASI, margin change
72, debt issuance 72, asset growth 36).
NOT built (need a tick — they change ticked rules): (a) allocation d1-first / USA-EUR-GLB first
(the current weight order spends half of every round on d0 cells whose bar is 2.69, and the new
classic-ratio cells GLB/EUR d1 are never reached before JPN/CHN); (b) POST-HOC sign-reversed
hypotheses validated on the other delay before any use; (c) regime gating (anti_corr M3).

## 11g. Khoa's question (14:10): "does the current design produce MEANINGFUL alphas?" — assessment
Measured against the standard Khoa ratified on 2026-07-17 (`fetched/hypothesis_standard.md`, 8
hard gates + composite ≥ 70): the forge hypotheses are economically grounded (typed mechanism,
named counterparty, canonical citations — gates 1–3 hold), but their CONSTRUCTIONS trip hard
gate 6: 27 of 41 are a single-field monotone re-rank (`group_rank(ts_backfill(x, w), g)`) and 14
are a two-field ratio — what the standard calls a "Law-1 null, guaranteed" (Dim 5 score 0). The
standard's own measurement: single-op constructions 0.13–0.55 Sharpe, multiply-conditioned
1.95, if_else-gated 1.58. Today's 487 simulations (max 0.75) sit in the single-op band.
Also missing per the standard: a per-sub-regime sign map (gate 4: 0 of 41), a pre-registered
strongest sub-population (2 of 41), and concrete counterparties (29 of 41 read "investors who…").
The operator/field checker (`tools/funnel/logic_check.py`) passes 188/188 simulated formulas —
they are LEGAL and respect field nature; legal is not the same as meaningful.
Consequence: the ensemble module (additive) is the weakest combiner the standard lists; what it
prescribes is ≥ 2 cross-family legs joined by multiply / if_else conditioning on rank-bounded
operands, with the regime map and the sub-population written into the hypothesis. Not built —
Khoa's call.

## 11h. Construction layer rebuilt to the ratified standard (Khoa 14:15: "1")
BUILT (95 forge tests green, shipped, NOT simulated):
- `forge/compose.py` — cross-family composites: `multiply(A⁺, B⁺)` (confirmation) and
  `if_else(greater(B⁺, 0.5), A, 0)` (conditioning) on rank-bounded legs; a `-group_rank` leg
  becomes `(1 - group_rank)`; the cell is filled by the leg of its own category, the other leg may
  come from another category of the same region/delay; no price carrier can enter (C30).
- `forge/standard.py` — the mechanical half of the 8 hard gates, evaluated before any sim; a
  single-field hypothesis trips gate 6 by construction (it is a LEG); a composite must carry a
  ≥ 25-word typed mechanism, a concrete agent class, a labelled dated citation, a 4-regime sign
  map, a strongest sub-population and a weakening condition, ≥ 2 different families, a
  conditioning combiner.
- `forge/composites/*.yaml` — 12 composites, every one admissible: profitability×accruals
  (Piotroski), investment×profitability (q-factor), accruals×capex, quality×accruals, insider×
  accruals (Beneish & Vargus), revisions×agreement, safety×revisions, tone×profitability,
  intangibles×profitability, financing×bloat, short×sentiment, options×short.
- every hypothesis now carries a `family`; `runner --mode composites` (default) simulates only
  admissible composites — singles are legs; `--mode singles|both` remain for measurement.
- daily regression timer installed on the VPS (`wq-forge-tests.timer`, 10:30; result in
  `state/forge/tests_last.json`, Discord off per Khoa).
DRY RUN (VPS, seed 5150, no POST): 300 composite constructions over 6 cells — JPN/d0 Fundamental
40, JPN/d1 Fundamental 60 + Model 40, GLB/d1 Fundamental 60 + Analyst 60 + Model 40 (d0 40 /
d1 260: few composite legs reach d0). Awaiting Khoa's tick for the verification round.

## 11i. Auth hourly link — outage found and fixed (Khoa 14:30: "Đổi lại auth gửi 1 tiếng 1 lần như cũ")
MEASURED: m1 links went out hourly 08:00–11:00; Khoa tapped at ~10:02 (session to 14:02). From
12:00 the `wq-mint.timer` (mint_link every 60 s) took the shared hourly mint lock at the top of
each hour, then refused on its OWN budget reading — `budget_left()` in mint_link ignored the ET
day, so 25 mints accumulated over several days read as "25/25 today" — and returned with the
hour already consumed. The daemon, which counts the day correctly, then logged "mint gate
already taken this hour" for 12:00, 13:00 and 14:00 and no link reached Khoa after the session
died at 14:02. Two budget cursors, one lock: the two-cursors disease at the budget layer.
FIXED (`tools/mint_link.py`, `tools/outbox.release_hour`): mint_link counts the ET day exactly as
the daemon does; a live session is refused BEFORE the gate; every non-mint outcome after taking
the gate (budget, wall, POST exception, unexpected HTTP) gives the hour back; the POST timeout is
60 s. Tests: `tools/tests/test_mint_hour.py`. The daemon is untouched (no restart).

## 11j. Verification round of composites (seed 1788506515, started 14:21) — two scoring corrections found while it ran
- MEASURED (GLB/d1 rows): the platform grades Sharpe 1.01 against the 1.58 line as **WARNING**, not
  FAIL; my scorer had read WARNING as "not a fail" and would have staged two such rows as
  candidates. Corrected in `forge/score.py`: on a binding check FAIL and WARNING both refuse
  (C21 says all gates PASS; C14 only waives EXTRA margin); PENDING on a binding check is
  "incomplete". GLB also carries `LOW_GLB_APAC_SHARPE` / `LOW_GLB_EMEA_SHARPE` (limit 1) — binding.
- The turnover floor of the 2–25% band was mine, not the platform's (LOW_TURNOVER line 1%): rows at
  1.3–1.7% pass the platform and were the best of the round. `turnover_verdict` now refuses only
  above 25% (decay retry) or when the platform itself fails LOW_TURNOVER.
- FINAL (15:14): 300 posted, 300 landed, 0 GUARD/FAIL, 0 UNITS. **0 of 300 pass**; Sharpe p50
  0.05, p90 0.52, max 1.07; turnover p50 0.065 (books full, no concentration fails). Chain ran
  unattended: harvest 300 `fail`, probe 0, submit 0. Best hypothesis-cells: intangibles×
  profitability GLB/d1 Fundamental p50 0.89 / max 1.07 (n 20); safety×revisions GLB/d1 Analyst
  p50 0.41 / max 0.91; investment×profitability GLB/d1 0.40 / 0.68; quality×accruals JPN/d1
  Model max 0.68. Binding fails at the top: LOW_SHARPE (1.58), LOW_FITNESS, IS_LADDER, and the GLB
  regional lines (APAC/EMEA/AMER Sharpe ≥ 1).
- THREE ROUNDS, 787 SIMULATIONS, 0 PASS. The construction ladder moved the best hypothesis-cell
  MEDIAN 0.46 → 0.89 and the MAX 0.75 → 1.07 (single legs → cross-family composites, as the
  standard predicted in direction), and stopped a third short of the 1.58 bar. MECHANISM of the
  remaining gap: UNKNOWN — the candidates are (i) these regions' fundamental data carry less
  cross-sectional signal than USA/d1's, (ii) the empty-cell constraint excludes the categories
  where the playbook's 40% pass rate was measured (USA Fundamental/Analyst are full), (iii) two
  legs are not enough conditioning. None is established; each would need its own round.

## 11k. Three-leg composites on the best cells (Khoa 15:20: "Viết composite 3 chân … rồi thử 100 sim")
BUILT: `compose.expand` products of three positive-form legs (gate combiner dropped for ≥ 3 legs);
runner `--cells` (shell-safe `GLB/d1:Fundamental`) and `--only` filters; `forge_loop.sh` passes
`FORGE_ARGS`. Four composites, all admissible: intangibles×profitability×accruals,
intangibles×profitability×safety, profitability×accruals×investment (GLB/d1 Fundamental),
safety×revisions×profitability (GLB/d1 Analyst). Targeted round: N=100, the two GLB/d1 cells
only. Measure: median/max Sharpe of the 3-leg cells against the 2-leg cells (0.89 / 1.07 and
0.41 / 0.91).
RESULT (seed 1788509921, 15:18–15:36, 80 landed — the 60-per-cell cap, not 100): 0 pass.
intangibles×profitability×safety GLB/d1 Fundamental **p50 1.11 / max 1.29** (n 20);
intangibles×profitability×accruals p50 0.94 / max 1.30 (n 30); profitability×accruals×investment
0.51 / 0.90; safety×revisions×profitability (Analyst) 0.46 / 0.75. Turnover p50 0.054, books
full. THE CONSTRUCTION LADDER, MEASURED ON THE SAME CELL: best median 0.46 (single field) →
0.89 (two legs) → 1.11 (three legs); best max 0.75 → 1.07 → 1.30. Bar 1.58, plus GLB's own
regional lines (Sharpe ≥ 1 in AMER, EMEA, APAC sub-books): AMER p50 1.15 PASSES, EMEA −0.36 and
APAC −0.76 FAIL on every row — the signal lives in the Americas sub-book. MECHANISM UNKNOWN
(candidates: fundamental7 coverage outside the Americas; US-centric anomalies; country tilt —
GLB offers COUNTRY neutralisation, untested). Where else the four 3-leg composites form (dry):
EUR/d1 Fundamental 60, EUR/d1 Model 40, GLB/d1 Model 60 — EUR has no regional sub-checks.
Day total: 1,167 simulations, 0 pass; every round ran unattended end to end.

## 11l. The search (Khoa 15:40: "Thử nhiều cách thay đổi pipeline để tạo tới khi ra được pass đầu tiên")
`forge/search.py` runs one-lever rounds through the same loop (harvest → probe → submit after
each) and stops at the first row that passes every binding platform check. Plan-time recipe
overrides in the runner: universe per region, neutralisation, group field, decay, truncation,
`ts_decay_linear` smoothing, and a tag written to every row's `meta.recipe`. Two four-leg
composites added (intangibles×profitability×safety × revisions / × accruals; admissible).
Recipes, in order (≈ 860 simulations if none passes):
R1 EUR/d1 Fundamental+Model, the 3-leg composites (no regional sub-checks) · R2 GLB country
neutralisation + country groups · R3 GLB universe TOP3000 · R4 four legs · R5 smoothing 10 +
decay 16 · R6 EUR TOP1200 + STATISTICAL/SLOW_AND_FAST · R7 GLB/d1 Model · R8 JPN/d1 · R9 every
admissible composite on every reachable cell (300). Results: `state/forge/search_results.jsonl`;
log `state/forge/search.log`. Every lever is EX-ANTE a settings/construction change under C30;
none is a measured mechanism until its round lands.
RESULTS SO FAR (MEASURED):
- R1 EUR/d1 (100): 0 pass; p50 0.16, max 0.65 — the same 3-leg composites are far weaker on EUR
  (fundamental72 / fundamental6 fields) than on GLB (fundamental7). Region matters more than legs.
- R2 GLB country neutralisation + country groups (60): 0 pass; p50 0.60, max 0.99. Regional
  sub-Sharpe moved: APAC −0.76 → 0.00, EMEA −0.36 → −0.15, AMER 1.15 → 0.62 — the tilt was part
  of the Americas edge; net worse than SUBINDUSTRY (1.11 median). Observation, not a mechanism.
- R3 GLB universe TOP3000 (60): 0 pass; p50 0.60, max 0.98 (best cell p50 0.73) — below MINVOL1M
  (1.11). The liquid-universe choice loses, on this data.
- R4 four legs (50 landed): 0 pass; best cell intangibles×profitability×safety×accruals p50 0.72,
  max 0.96; ×revisions p50 0.50. The ladder does not continue past three legs here
  (0.46 → 0.89 → 1.11 → 0.72): a fourth confirmation thins the book more than it sharpens it.
- R5 smoothing ts_decay_linear(10) + decay 16 (60): 0 pass; best cell p50 0.90, max 1.17 — no
  gain over the plain 3-leg (1.11 / 1.30).
- R6 EUR TOP1200 + STATISTICAL/SLOW_AND_FAST (80): 0 pass; p50 −0.10, max 0.35 — the worst so far.
- R7 GLB/d1 Model (60): 0 pass; intangibles×profitability×safety p50 0.89, max 1.26 — the same
  composite reads the same on the Model cell as on Fundamental (the leg set is identical).
- R8 JPN/d1: no candidates — the 3-leg composites' legs (fundamental7 ratios, model36 safety) do
  not exist in the JPN catalogue; the loop's one-hour "library exhausted" sleep then held the
  driver for 10 minutes until killed; `forge_loop.sh` now returns at once on a one-round run.
- R9 broad sweep (300, every admissible composite): 0 pass; p50 0.39, max 1.36; best cell
  intangibles×profitability GLB/d1 Fundamental **p50 1.23 / max 1.36** (n 20, a fresh draw of the
  same grid; the earlier draw read 0.89 / 1.07 — sampling spread of a 20-draw cell median is that
  wide), then intangibles×profitability×accruals 0.79 / 0.99. The USA composites landed on the
  d0 cells first (USA/d0 Insiders p50 0.62, bar 2.69); the USA/d1 cells are batch 2.
BATCH 1 VERDICT (R1–R9, 1,000 simulations, 0 pass; day total 2,167): no lever beat the plain
3-leg composite on GLB MINVOL1M / SUBINDUSTRY (median 1.11–1.23, max 1.30–1.36). Region (EUR,
JPN), universe (TOP3000, TOP1200), neutralisation (COUNTRY, STATISTICAL/SLOW_AND_FAST), a fourth
leg, and smoothing all read lower. The best construction sits a fifth under the 1.58 bar and GLB's
regional lines stand behind it. Batch 2 (USA/d1 empty cells with USA fundamental confirmation legs,
then the exploitation round) runs next.
- R10 USA/d1 Insiders (40 landed — the composite's grid on that cell): 0 pass; p50 0.67, max 1.05.
  The empty USA/d1 cell with a USA fundamental confirmation is in the same band as GLB.
- **R11 USA/d1 Short Interest (80): the first rows over the Sharpe bar.** `usa_short_x_
  profitability_x_accruals` p50 1.07, max 1.67 (n 40): RRVLKGLg Sharpe 1.67, turnover 0.142,
  1,165 names, fails LOW_FITNESS (0.83) and IS_LADDER (1.13); **6XrbJWM7 Sharpe 1.61 fails ONLY
  LOW_FITNESS (0.76 < 1.0)** — every other binding check PASS, ladder included. Both at decay 4,
  STATISTICAL. Fitness = Sharpe·√(|returns|/turnover) = 1.61·√(0.033/0.147) = 0.76: the gap is
  turnover, not signal. Next recipes R14/R15: decay 16/32 and whole-alpha ts_decay_linear(10)
  on the same composite (community consensus and the repo's own memory: fitness failures are
  turnover in disguise; decay is the lever). `usa_shortsurprise_x_profitability` p50 −0.23, max 1.38.
  Session expired 18:16; the hourly link went out at 18:02 (m1 #1056) — the driver resumes on the tap.
- R14 decay 16/32 (40): 0 pass; turnover p50 0.121 → 0.062 but fitness p50 0.52 → 0.45 (max 0.83
  → 0.78) and Sharpe max 1.67 → 1.53. R15 ts_decay_linear(10) (40): max 1.47, no better.
  MEASURED WHY (verified on R11 and R14 rows to ±0.01): the platform's fitness is
  Sharpe·√(|returns| / max(turnover, 0.125)) (SOURCE: repo skill boost-fitness) — below 12.5%
  turnover the denominator is fixed, so cutting turnover buys nothing; returns must reach
  0.125/Sharpe² ≈ 4.9% at Sharpe 1.6, against 3.3–3.5% now. Next: R16 truncation 0.15, R17
  signed_power 2 (tail concentration), R18 both — returns levers at held Sharpe, decay back to 4/8.
- R16 truncation 0.15 (40): **two rows at Sharpe 1.67 failing ONLY LOW_FITNESS 0.87** (E5v3J3lr,
  1YxvEvw6; turnover 0.09–0.11, returns 0.034, ladder passes). Truncation is not binding on a
  1,100-name book. R17 signed_power 2 (40): returns 0.036 but Sharpe fell to 1.46 → fitness 0.78.
  R18 both: max 1.50. Fitness ceiling so far 0.87 at Sharpe 1.67; the gap is 15% in
  returns×Sharpe. R13 (GLB exploitation, 200) running; the next Short-Interest recipes come from
  a within-cell analysis of the 240 rows (neutralisation, window, group, leg fields) — below.
- WITHIN-CELL ANALYSIS (240 rows, POST-HOC patterns, no mechanism claimed): STATISTICAL
  neutralisation Sharpe p50 1.19 vs INDUSTRY 0.95 / SUBINDUSTRY 0.85; decay 4 > 8 > 16 > 32 on
  both Sharpe and fitness; truncation 0.15 ≥ 0.08; the profitability leg `ts_backfill(income /
  equity, 126)` has the best median (fitness 0.66, Sharpe 1.36) while `operating_income / assets`
  holds the max (1.67); the short-volume window (5/10/20) barely matters. Returns sit at
  0.026–0.036 under every knob — the fitness ceiling is a returns ceiling. Queued R19–R23: untried
  neutralisations (SLOW_AND_FAST/CROWDING/MARKET), group = sector, universe TOP1000, a 100-draw
  exploit of the best settings, power 1.5 + truncation 0.2.
- R12 USA/d1 Sentiment + Social Media (80): 0 pass; twitter×profitability (Social Media) p50 0.53,
  max 1.31; sentiment×profitability×accruals (Sentiment) p50 0.39, max 0.66.
- R13 GLB exploitation, 200 draws of intangibles×profitability×safety: 0 pass; **p50 0.66, max
  1.40**. CALIBRATION: the same cell read median 1.11 on 20 draws and 1.23 on another 20 — a
  20-draw cell median wobbles by about ±0.4; only ≥ 100-draw medians are worth quoting.
- R19 SLOW_AND_FAST / CROWDING / MARKET on the Short Interest composite (40): 0 pass; p50 0.87,
  max 1.25 — below STATISTICAL (1.25 / 1.67).
- **R20 group = sector for every leg (58): THE FIRST FULL PASSERS.** Cell p50 Sharpe 1.67, max
  1.87; fitness p50 0.86, max 1.03. vRk095rv and qMWbdlmv: Sharpe 1.85, fitness 1.03, turnover
  0.08–0.10, returns 0.038, 1,180 names, decay 4, STATISTICAL, truncation 0.15 — every binding
  platform check PASS (ladder included). Four more at Sharpe 1.83–1.84 / fitness 1.01–1.02 fail
  only IS_LADDER (1.39–1.55). Formula shape: `multiply(multiply((1 − group_rank(ts_mean(short
  volume share, 10–20), sector)), group_rank(ts_backfill(operating_income / equity, 126), sector)),
  (1 − group_rank(accruals, sector)))`. MECHANISM of the sector lift: UNKNOWN (candidates:
  sector groups give the ranks more dispersion than subindustry groups; STATISTICAL neutralisation
  then removes the sector tilt). Scorer bug found by them: REGULAR_SUBMISSION (the platform's
  aggregate, PENDING at sim time) was treated as a binding pending check → "incomplete" → the
  loop's harvest/probe/submit never saw them. Fixed (non-binding; incomplete rows re-scored).
- R21 universe TOP1000 (40): 0 pass; p50 1.20, max 1.51 — below TOP3000.
**21:19 — FIRST SUBMISSION OF THE REDESIGN.** After the scorer fix, harvest staged both R20
passers as candidates (DSR 0.996 on the strict cumulative pool, N ≈ 400), the probe read prod
0.53 / 0.55 and self 0.27 / 0.29 (both under the 0.7 lines, self under the 0.30 super-gem mark),
both MATCHES_PYRAMID PASS filling USA/D1/SHORTINTEREST (count 0 → gain 3 × 1.1) and
USA/D1/FUNDAMENTAL. The submitter applied C16 (scores 0.784 vs 0.778 within 10% → second-best)
and C19 (one POST per mechanism per week): **vRk095rv POSTed, HTTP 201**; qMWbdlmv held for next
week. Day total ≈ 2,900 simulations, 24 recipes. The search driver finishes R22/R23 and stops.
**21:21 — vRk095rv is ACTIVE on the platform** (dateSubmitted 2026-09-04T10:19-04:00): the first
alpha the redesign submitted was accepted, and it fills USA/D1/SHORTINTEREST (1 of 3) and
USA/D1/FUNDAMENTAL. R22 (100 fresh draws, industry/subindustry groups): p50 1.49, max 1.77.
- SECOND BATCH queued (R10–R13): the empty USA/d1 cells (Insiders, Short Interest, Sentiment,
  Social Media — bar 1.58, no regional sub-checks) with a strong USA fundamental confirmation
  leg (new legs `usa_profitability_ratios`, `usa_accruals_cashflow`, `usa_rd_intensity` on the
  plain fundamental6 fields `operating_income`, `income`, `assets`, `equity`, `cashflow_op`,
  `rd_expense`, `sales`) beside the target-category leg; and an exploitation round on the best GLB
  composite (200 draws of its grid — selection effect stated, the DSR pool grows with it).

## 11m. What the day measured (2026-09-04, ≈ 2,900 simulations, 24 recipes, 1 ACTIVE submission)
1. The chain works unattended: 13 rounds ran plan → simulate → harvest → probe → submit with
   correct refusals; the one blocking bug was in scoring (REGULAR_SUBMISSION), not in plumbing.
2. Construction is the lever that moved: single field 0.46 → two cross-family legs 0.89 →
   three legs 1.11 (20-draw medians on GLB); the ratified standard's prediction held in direction.
3. Region and cell decided the rest: GLB is blocked by its regional sub-lines; EUR/JPN data read
   far weaker; USA/d1 Short Interest with a USA fundamental confirmation leg is where Sharpe first
   cleared 1.58 (R11), and `group = sector` (R20) lifted the same composite from 1.67/0.87 to
   1.85/1.03 — Sharpe and fitness together. MECHANISM UNKNOWN; it is one measurement on one cell.
4. Fitness on this platform is Sharpe·√(|returns|/max(turnover, 12.5%)): below 12.5% turnover
   only returns and Sharpe count — the decay/smoothing recipes could not have worked and did not.
5. Twenty-draw cell medians wobble by ±0.4; the 200-draw exploitation read 0.66 where 20 draws had
   read 1.11 and 1.23. Quote ≥ 100-draw numbers only.
6. Submitted: vRk095rv (USA/d1 Short Interest, prod 0.55, self 0.29, DSR 0.996), ACTIVE 21:21;
   qMWbdlmv identical class, held to 2026-09-11 by the one-per-mechanism-per-week rule.
Open for Khoa: whether to run the standing loop now (N=300 continuous, sector groups added to
the composite defaults, cells-first order), and the still-owed Chrome CDP survey (C23).

## 11n. Standing loop (Khoa 21:30: "Bật vòng lặp tự động: composite, ưu tiên USA/d1, có sector, không chia d0")
`wq-forge.service` (systemd, Restart=always, singleton by /var/lock/wq_forge.lock, refuses to run
beside wq-climb): `forge_loop.sh` with N=300, ROUNDS=100000, FORGE_ARGS
`--mode composites --order USA/d1,d1 --no-split`. Every round: plan (cells USA/d1 first, then every
d1, then the rest, by weight) → simulate → harvest (DSR, strict cumulative pool) → probe (+120 s)
→ submit (C21 class; one POST per mechanism per week; second-best). `sector` was added to every
leg's group grid. STOP: `touch state/STOP_FORGE` or `systemctl stop wq-forge`. Notifications stay
off (Khoa 12:49); read `venv/bin/python forge/digest.py` for the 24-hour digest.

## 11o. Two days of the standing loop (read 2026-09-06 19:55)
MEASURED: 65 rounds since 09-04 21:27; rows landed 09-04 3,019 / 09-05 3,370 / 09-06 989 (to
19:55); platform-pass 3 / 6 / 9. **Second ACTIVE submission: kqVbg1xP** (09-06 17:19 local) —
`options_x_short` (call−put IV spread × low short volume, sector groups) on USA/d1 Short Interest,
Sharpe 2.01, fitness 1.03, prod 0.54, self 0.32, DSR 1.00; fills USA/D1/SHORTINTEREST (now 2 of 3,
live counter) and OPTION. 18 candidates on file; the 16 unposted siblings of the two ACTIVE alphas
read prod-corr 0.79–0.85 (CORRECTED in 11s: most of those readings predate kqVbg1xP's POST — they
correlate with the earlier book, not with their sibling) — either way a mechanism yielded one submission.
LOSSES, MEASURED: (1) auth idle — 71 five-minute waits on 09-05 (≈6 h) and 190 on 09-06 (≈16 h,
01:00–13:00): the loop can only run while a tapped session lives (4 h); (2) from 17:14 on 09-06,
23 rounds died on `requests.ReadTimeout` inside scrape()/poll() (43 timeouts) — 117 parents /
1,170 simulations posted and never reaped; the platform still holds them. FIXES: `_get_patient`
retries in scrape(), poll() and poll_parent() (a timed-out poll repeats, never kills the round);
`forge/offline/recover_orphans.py` re-attributes orphaned children by (echoed formula, echoed
settings) against the round's plan file — running in the background (~30 min); the live pyramid
counter is now refreshed before every round and after every POST (the cached file had stood at
09-04 while Short Interest moved 0 → 2; the old crawler runs in a simulated fixture mode).
Submitter hold reasons now check the correlation line before the calendar rule.

## 11p. Submittable alphas per simulation (Khoa 2026-09-06 21:00: "cải thiện hiệu quả số alpha nộp được trên mỗi lượt sim")
MEASURED (8,652 sims since 09-04): platform-pass 0.24%, DSR 0.22%, under the correlation lines
0.035%, submitted 0.023% (1 per 4,326). Of the standing loop's 6,251 sims, 34% went to pairs with
≥ 60 sims, 0 passes and best Sharpe < 1.0 (9 pairs: GLB Fundamental/Analyst, JPN Fundamental/
Model, …) and ≈ 15% to pairs whose mechanism was already submitted (their siblings read prod-corr
0.79–0.85). About half the quota bought nothing by construction; the number of DISTINCT
mechanisms that pass, not the number of sims, decides submissions.
BUILT: `forge/allocate.py` — every (composite, cell) pair is classified from the journal:
HARVESTED (a POSTed alpha for its mechanism) and DEAD (≥ 60 sims, 0 pass, best < 1.0) are never
simulated again; NEAR_MISS (best ≥ 1.3, failing only Sharpe-like lines) gets blocks of 40 first;
PASSED (pass, nothing submitted yet) 10; UNTRIED 20; ACTIVE 20 — planner default in composites
mode (`--no-allocate` restores the old walk). Five new distinct USA composites for the empty
USA/d1 cells (insider × IV spread, sentiment × IV spread, twitter × IV spread, short-surprise × IV
spread, insider × short × profitability) — each a new mechanism, i.e. a possible new submission.
Also today: dispatcher survives read timeouts; 878 orphaned children recovered (72 unmatched);
live pyramid counter before every round. PROOF: submittable per 1,000 sims before (0.23) vs after,
read from the same journal — recorded here when the next 2,000 sims land.
TICKED (Khoa 21:20): allocator ON now; cold cells (≥ 300 sims, 0 pass) ordered last; re-measure
after 2,000 simulations. Baseline to beat, same journal: 0.23 submitted / 1,000 sims, platform-pass
2.4 / 1,000, distinct passing mechanisms 2 in 8,652 sims.

## 11q. Consequences and risks of the allocator, measured on the journal (2026-09-06 21:30)
Backtests of each rule against the 8,828 forge rows, in chronological order per pair:
- DEAD rule (≥ 60 sims, 0 pass, best < 1.0): would have stopped 9 pairs after 24% of all sims
  (2,162) had gone to them; **0 of those pairs ever passed later**, later best Sharpe ≤ 0.84.
  Risk: a dead pair revived by a settings lever (sector gave +0.18 once) — bounded by the
  best-Sharpe margin (≥ 0.16 below the line for every killed pair).
- NEAR_MISS rule: 5 pairs reached a near miss; 2 converted to a pass (after 29 and 290 more
  sims), 3 have not (short×sentiment 597 sims, twitter×profitability 601, short-surprise 40).
  RISK FOUND: short-surprise×profitability has a pool spread of 0.80 annual (N 40), so its own
  cumulative DSR pool imposes SR0 1.76 now and 2.27 after 200 more draws — a 1.65-Sharpe row
  there would read DSR 0.36 → 0.02. Exploiting it buys platform passes the DSR gate refuses.
  MITIGATION (built): a near miss is exploited only if SR0(N + 40) ≤ 1.60 − 0.54 (the margin DSR
  ≥ 0.95 needs at T = 2,493); otherwise it stays ACTIVE with small blocks.
- HARVESTED rule: the two posted pairs; siblings of options×short read prod-corr median 0.81
  (n 17). The pair has 2 mechanism keys (option8 / option3 legs) — both share the leg set, so the
  key-level rule alone would have re-simulated the other key. MITIGATION (built): a composite
  sharing > 1 leg with a POSTed composite is never simulated (leg-overlap block); measured on the
  five new composites: four share one leg (the IV-spread) with kqVbg1xP — allowed, correlation
  risk stated; insider×short×profitability shares two legs with vRk095rv — blocked.
- COLD cells (≥ 300 sims, 0 pass): as first written it would have demoted USA/d1 Sentiment
  (1,005 sims, best 1.28), Insiders (470, 1.25) and Social Media (601, 1.31) — cells failing only
  Sharpe-like lines, i.e. hard, not blocked — together with GLB (best 1.42 but LOW_GLB_APAC/EMEA
  on every best row) and JPN (best 0.73–0.84). MITIGATION (built): cold requires best < 1.2 or a
  structural failure on the best row; the three USA cells stay warm.
- Concentration: the next round puts 60/300 on USA/d1 Short Interest and 160/300 on USA/d1 in
  all; GLB/EUR/IND untried composites take the rest. Risk: no other region advances — accepted
  until a USA cell fills, then revisit.
- DSR pool growth from exploitation: usa_twitter (sd 0.27, N 601 → 801) SR0 0.85 → 0.88, a 1.65
  row stays DSR 0.99 — negligible; short×sentiment (sd 0.16) likewise.
- Submission-side: 2 of 2 POSTs accepted; the 30-minute re-read rule and record-first ordering
  bound the 403 risk; no 403 yet.
Net: the rules would have redirected ≈ 24% (dead) + ≈ 15% (harvested) of past sims with no
measured loss of a later pass; the two risks found (DSR-blocked near misses, leg-overlap
siblings) are now handled by construction.

## 11r. Consequences and risks of every listed strategy (A–E), measured where the journal allows (2026-09-06 21:50)
Retrospective on 8,828 forge rows (`forge/offline/strategy_backtests.py`); EX-ANTE where marked.
- A1 allocator (live): DEAD rule 24% of sims saved, 0 later passes; HARVESTED ≈ 15% — see 11q.
- A2 bandit allocation: NOT measurable retrospectively. Risk: noisy early reads — a 20-draw cell
  median wobbles ±0.4 and the first ≥ 1.3 row appears at draw 15 (p50) / 87 (p90) — a bandit fed
  by 10-draw estimates over-commits to luck; mitigation = a 20-draw floor. Gain over classes: unproven.
- A3 exploration blocks of 10: the first row ≥ 1.0 appears at draw 3.5 (p50), 19 (p90); 10 of 14
  strong pairs show it within 10 draws; max(first 20) − max(first 10) is 0.00 (p50), 0.14 (p90)
  over 54 pairs. Consequence: ≈ 2× more pairs screened per round for almost no loss in
  detecting strength; the 4/14 late starters stay ACTIVE and get later draws (delayed, not lost).
- A4 wave stop (first 100 < 0.8): 5 pairs, 1,451 sims saved, 0 later passes — weaker than A5 and
  needs a wave-based dispatcher; not worth the code.
- A5 DEAD at 40 vs 60 vs 100 sims: pairs killed 11 / 9 / 6, sims saved 2,341 / 2,161 / 1,861,
  later passes 0 / 0 / 0, later near-miss rows 0 / 0 / 0. 40 buys +180 sims at no measured cost.
- B6 settings prior: STATISTICAL beats INDUSTRY/SUBINDUSTRY on every USA cell (Short Interest
  1.28 vs 1.05/1.06, n 1,014/645/724; Social Media 0.86 vs 0.61/0.57; Insiders 0.66 vs
  0.54/0.57; Sentiment 0.60 vs 0.53/0.54); decay 4 > 8 > 16 (Short Interest 1.18/1.12/1.00;
  Sentiment 0.60/0.60/0.35); group sector > industry > subindustry on USA cells (Short Interest
  1.20/1.14/1.12; Social Media 0.73/0.68/0.64) but sector LOSES on GLB (0.43 vs 0.58) and nothing
  moves JPN (≈ 0). RISK of a universal prior: cell-dependent effects; joint effect of the three
  settings never measured together. Use per-cell priors with n ≥ 15, keep 20% uniform draws.
- B7 leg-quality filter: only 1 composite has all legs measured as singles — NOT measurable yet.
- B8 ladder-only failures: 8 rows above 1.58 failing only ladder/2Y (decay 4: n 6, ladder 1.40;
  decay 8: n 2, 1.48). Too few to read; decay 8 costs ≈ 0.06 mean Sharpe (B6). Test = 60 sims.
- C9 mechanism breadth: 2 distinct mechanisms in 8,652 sims; a new composite costs 40–100 sims to
  read. Risk: 4 of the 5 new USA composites share the IV-spread leg with kqVbg1xP — their
  correlation is the experiment; base rate for full siblings is 16/16 over the line.
- C10 leg-overlap block (live, > 1 shared leg): measured basis siblings 0.79–0.85; blocks 1 of 5
  new composites. Risk: a real signal sharing 2 legs is never tested — accepted while the book is
  small; revisit when the library adds datasets.
- C11 in-formula neutralisation against the book: EX-ANTE only. Upside is the largest of all —
  16 candidates at Sharpe 1.6–2.1 sit behind the correlation line; downside = Sharpe loss
  (anti_corr M1 was dead, M3 lived). Test = 60 sims on the 16 candidates' formulas.
- C12 cross-region reuse: measured proxies say no — the same composites read 0.16 (EUR), −0.10
  (EUR TOP1200), ≈ 0 (JPN, every setting), and GLB is behind regional lines. IND/ASI untested;
  probe at 20 sims per cell only.
- D weekly rule: not a lever (siblings correlate 0.8 regardless).
- E throughput: auth idle 16 h on 09-06 dominates total output; 10 vs 9 parents ≤ +11% EX-ANTE,
  risk = platform 429 throttling; one round tells.
Interactions: B6 prior + strict DSR pool reinforce (a tighter spread lowers SR0: pools of sd
0.16–0.27 impose 0.5–0.9); A3 + A5 together ≈ 2× pairs screened with DEAD firing on wall-time
later; C10 bites harder as the book grows — breadth must come from new DATA, not new leg mixes.
Recommended order (measured value / cost): A3 + A5(40) now (0 measured loss) → C11 (60 sims) →
B8 (60) → B6 per-cell prior as a 150/150 A/B → C12 probes.

## 11s. Hallucination audit (Khoa 2026-09-06 22:00: "kiểm tra hallucination") — independent recount
Every number re-derived from the raw journal files with plain JSON parsing, no forge modules:
rows 8,828; platform-pass 21 (0.24%); DSR candidates 19; under both correlation lines 3;
POSTed 2 (HTTP 201, both ACTIVE on the platform); auth idle 355 min (09-05) and 1,010 min (09-06);
26 non-zero round exits of 69. DEAD backtest re-derived raw: 40 → 11 pairs / 2,341 sims / 0 later
passes; 60 → 9 / 2,161 / 0. All agree with §11o–§11r.
TWO CLAIMS CORRECTED:
1. "Siblings of a posted alpha read prod-corr 0.79–0.85 AFTER its submission (0.53–0.55 before)"
   — WRONG as a causal story. Six of the sixteen options×short siblings were read at 0.79–0.83
   BEFORE kqVbg1xP was posted; only kqVbg1xP itself read 0.54. Their correlation is with the book
   that already existed — plausibly vRk095rv, which shares the short-volume leg (SPECULATION,
   not measured). What stands: 16 of 17 candidates of that pair are over the line and the pair's
   remaining candidates cannot be submitted; the HARVESTED rule's effect is the same, its
   mechanism is not the one I wrote. The leg-overlap block (C10) is the rule this actually supports.
2. "group = sector unlocked the pass (+0.13–0.20)" — holds only in the controlled pair R20 vs
   R22 (sector 1.63, n 58, vs industry 1.50 / subindustry 1.43 at STATISTICAL, decay 4, trunc
   0.15). In the standing-loop rows, where groups are mixed with every other setting, sector 1.09
   vs industry 1.12 vs subindustry 1.11 (n ≈ 190 each) — no advantage. NOT ESTABLISHED as a
   general lever; possibly an interaction with the other settings (unmeasured). The library grid
   keeps sector as one option, not as a default.
CONFIRMED within recipe (not a recipe confound): STATISTICAL > INDUSTRY/SUBINDUSTRY both inside
R11 (1.28 vs 0.94 / 1.02, n 10–15) and across the standing-loop rows (1.42 vs 0.96 / 0.97, n ≈ 190
each); decay 4 > 8 inside R11 (1.13 vs 1.03) and 4 > 16/32 at STATISTICAL (1.39 vs 1.17 / 1.15,
n 5–10).
Two allocator rounds for Khoa's evaluation: NOT YET RUN — the session died at 21:01 and no tap
has arrived (22:00); they run automatically after the next tap.

## 11t. Ticked 2026-09-06 22:30 — A5, A3 live; C11 experiment armed (EX-ANTE, before any result)
Khoa's ticks: A5 DEAD at 40 sims (allocate.DEAD_SIMS 60 → 40), A3 UNTRIED blocks of 10
(allocate.UNTRIED_BLOCK; ACTIVE keeps per_block 20), both shipped to /opt/wq and picked up by the
next round; measured together with the allocator after 2,000 sims against 0.23 / 1,000. Not ticked:
B6 prior, B8, C12.
C11 = `forge/offline/c11_neut.py` (plan) + `c11_run.sh` (driver: waits for auth, stops wq-forge
only between rounds, runs 60 through forge_loop.sh with `runner --plan`, probes correlation for
every row via `probe --alphas`, restarts wq-forge on exit). Arms R / RS / RV / S = 16/16/16/12, the
control is each base row already in the journal. EX-ANTE predictions P1–P3 and the LIVES criterion
are in the module docstring, written before the first simulation. Readings BEFORE / AFTER
kqVbg1xP's POST (17:19): 7 candidates read before (6 at INDUSTRY/SUBINDUSTRY 0.79–0.83; kqVbg1xP
at STATISTICAL 0.54), 10 after (0.79–0.85; 883KgXXm self = prod = 0.852 against kqVbg1xP itself).
The STATISTICAL-vs-others difference is n = 1 — arm S is the test, and P3 predicts it fails on
prod because the sibling is now in the book.

## 11u. C11 result and an allocator bug found the same night (2026-09-07 02:10)
C11 (60 sims, plus 48 wasted on `regression_neut`, an operator this account cannot use — my
error, the accessible orthogonaliser is `vector_neut`):
- R  vector_neut(F, kqVbg1xP): Sharpe p50 0.44, max 0.69 (Δ −1.31 vs base); prod 0.57 / self 0.24
  on the 6 read — the residual crosses the lines and has no signal left. P1 CONFIRMED.
- RS (+STATISTICAL): p50 0.15; RV (also ⟂ vRk095rv): p50 0.11. P1 CONFIRMED.
- S  (STATISTICAL only, 8 paired rows): Sharpe unchanged (Δ −0.05) but fitness 0.75–0.93 and
  IS_LADDER fail on 8/8 → 0 platform pass; prod/self 0.91 on the 3 read. P3 CONFIRMED.
- LIVES: none. VERDICT: in-formula neutralisation against a posted sibling is DEAD for
  same-mechanism candidates; the route past the correlation line is a new mechanism (C9).
  POST-HOC, n = 8: STATISTICAL on these formulas costs fitness at equal Sharpe — MECHANISM UNKNOWN.
Dispatcher bug fixed on the way: CANCELLED was not a terminal child status (52-minute stall).
Recovery bug fixed: one construction in two plan files was read as ambiguous (10 alphas unattributed).
ALLOCATOR BUG (mine): one bar for both delays. Five USA/d0 pairs with best 1.71–1.74 against the
d0 line 2.69 were classed NEAR_MISS and, with the same composite counted under three category
names, took ≈ 1,000 of the ≈ 2,170 sims simulated 23:00–01:53 (ET 12–14); the daily quota ran out
at 01:53. Khoa's tick was USA/d1 first, no d0. FIXED: every threshold scales with the cell's bar
(NEAR 1.3 → 2.21 on d0, DEAD 1.0 → 1.70, cold 1.2 → 2.04, DSR target likewise) and one block per
composite × region × delay. The 2,000-sim allocator measurement is contaminated by this and
restarts from the 11:00 reset; A5/A3 were live for these rounds too.

## 11v. Loop robustness fixes ticked 2026-09-07 14:10 (Khoa: "còn bug gì nghiêm trọng ko")
Live check 14:01: loop active, ≈ 360 sims/h, 0 tracebacks in 3,000 log lines, 11:05 round 300 fail /
2 incomplete, submit 0 eligible (18 over the corr line, 1 weekly rule, 2 posted). Also found and
fixed 11:30: the loop read the 01:53 "DAILY_SIMULATION_LIMIT_EXCEEDED" line inside its last-400-line
window after the first round of the new day and slept 84,880 s with a live session (2.5 h lost);
the check now reads only the current round's output.
Ticked and shipped (loop restarts on the new script at its round boundary via STOP_FORGE):
1. A round starts only with ≥ 40 min of session left (mint_link.session_left_s; None → liveness
   only). Cause: 96 AUTH-FAIL rows and 15 orphan parents from rounds started under a dying session.
2. recover_orphans --limit 30 runs after every round; a parent whose only child rows are
   machine-side statuses (AUTH-FAIL, POLL-DEADLINE, POLL-EXHAUSTED, MULTISIM-*) is still an orphan.
3. The 75-min round deadline reaches into poll()/poll_parent(): a status word the loop does not
   know returns POLL-DEADLINE naming the word, instead of 700 polls per child.
Open, not bugs: auth idle is Khoa's taps (16.8 h on 09-06); wq-harvest service is dead weight;
2 harvest rows stay "incomplete" (platform checks PENDING).

## 11w. The 2,000-sim allocator measurement (Khoa's tick 09-06 21:20), read 2026-09-07 19:05
Windows by platform dateCreated (ET); C11 rows excluded; baseline n now 9,079 (orphans recovered).
| window | n | Sharpe p50 | ≥1.58 | platform pass | DSR cand | under lines | submitted | passing mechanisms |
| baseline (before 09-06 21:10) | 9,079 | 0.58 | 475 | 21 (2.31/1k) | 21 | 3 | 2 (0.22/1k) | 2 |
| allocator, all | 4,462 | 0.83 | 142 | 0 | 0 | 0 | 0 | 0 |
| · night 09-06 (d0 bug) | 2,167 | 1.06 | 100 | 0 | 0 | 0 | 0 | 0 |
| · today 09-07 (fixed) | 2,295 | 0.68 | 42 | 0 | 0 | 0 | 0 | 0 |
CONFOUND FIRST: every baseline pass and both submissions came from the two pairs the allocator now
skips by design (HARVESTED). Baseline yield on the NON-harvested pairs: 7,223 sims, 0 passes. So
the fair comparison is 0/7,223 (baseline) vs 0/4,462 (allocator): no measured difference either way.
The allocator did what it was built to do (no sims on harvested/dead pairs; today's spend 560
near-miss / 1,800 active; d0 only at the tail, 80 rows, when d1 cells are capped) and it did NOT
do what the purpose needed: a new mechanism that passes. Gate 4 of RULE 2: NOT PASSED yet.
WHERE THE 42 ≥1.58 ROWS TODAY FAIL: the IV-spread composites (insider/sentiment/twitter/short-
surprise × IV spread, USA/d1) reach Sharpe 1.60–1.77 with fitness 0.60–0.99 and every best row
also fails LOW_SUB_UNIVERSE_SHARPE (plus ladder on most). Twitter×profitability and short×sentiment
(the two real near misses) stayed at best 1.29–1.31 after 320 / 238 more sims — their near-miss
status has not converted. Observation only; MECHANISM UNKNOWN for the sub-universe failure.
TICKED 19:10 (Khoa): d0 OFF — `runner --delays 1` in wq-forge's FORGE_ARGS (unit copy in vps/systemd_wq-forge.service); dry-run: 240 d1 constructions/round (54 reachable cells, DEAD pairs now 23 under A5). Not ticked: the sub-universe probe, new-dataset composites (C9).

## 11x. The typed grammar (Khoa's idea, 2026-09-07 19:30–21:30; every design point ticked)
Khoa: label every field of every dataset/region/delay from definition + data type, build a logic
where a function may only take certain labels, stack the logic in layers, prove it by A/B.
Ticks: as many label axes as are CORRECT; labels only from description + type + catalogue stats
(never from simulated alphas); hard rules for unit/kind/bounded/structure violations, soft for
semantic preference; fields without a stated sign only in sign-free roles (gate / condition /
magnitude); global rules, sample check and A/B on USA/d1 first; generator = random WITHIN the
grammar + the judge as the last gate (not random-then-filter: rejection sampling biases to shallow
formulas); layers L0 field → L1 time → L2 score → L3 cross-domain combine → L4 unstated-sign gate;
proof = A/B 50/50 per round, ≥ 5 rounds; no journal validation of the judge (Khoa: straight to live).
BUILT: `forge/labels.py` (127,642 fields, 404 datasets; axes domain/kind/unit/time/horizon/
sparsity/structure/crowding/sign/directional; sign + 24,260 / − 6,817 / unstated 96,565 — priors only
when the domain was READ from the description and carry their literature citation in DOMAIN_SIGN;
a difference profitability − cashflow is named accruals, Sloan −); Khoa ticked the 50-field USA/d1
sample (docs/redesign/labels/sample_usa_d1_seed11.md; my own audit ≈ 5/50 domain/kind slips, 0/50 sign).
`forge/typed.py` (parser + judge H1–H6 + soft score S1–S5): vRk095rv is REFUSED (its accrual leg
has no ts_backfill; its short leg is count/count with no labelled sign), kqVbg1xP is REFUSED (IV
levels are dispersions, sign-free) — the judge is stricter than the hand-written library, which
is the A/B question. `forge/grammar.py` (random within the grammar; 0 judge refusals on 60 draws),
`runner --ab typed` (half the round from the current planner tagged arm=current, half typed),
`forge/offline/ab_report.py` (per round and pooled: n, Sharpe p50/p90/max, ≥1.58, pass, DSR, mechanisms).
TICKED 2026-09-07 20:10 (Khoa): A/B ON in wq-forge (`--ab typed` in FORGE_ARGS), read after ≥ 5 rounds
(≈ 600 sims per arm); paired design: the typed half goes to the same cells in the same proportions
as the current half (dry-run seed 7: 60/60 Social Media, 60/60 Sentiment).
CONFOUND TO STATE FIRST when reading the A/B: the arms draw from different field sets — the typed
arm only from fields with a labelled sign — so a difference is "grammar + label vocabulary" vs
"hand-written composites", not the grammar alone.

## 11y. A/B verdict after 5 rounds (2026-09-07 21:56): the typed grammar loses as a generator
Paired rounds 20:34–21:56, same cells (USA/d1 Social Media / Sentiment / Insiders / Short Interest),
same settings grid, same gate. Pooled: current n 750, Sharpe p50 0.82, p90 1.40, max 1.81, ≥1.58 26
(3.5%); typed n 690, p50 0.11, p90 0.64, max 1.41, ≥1.58 0. Platform passes 0 in both arms. The
typed arm lost 60 of 750 sims (30 FAIL, 25 CANCELLED, 5 ERROR); the current arm lost none. Every
round, every statistic: current > typed. Round 5 (vector axes + event gates live): typed p50 0.09,
max 0.97 — no improvement. Inside the typed arm (observations, n in brackets): gate combiner 0.20
(165) vs multiply 0.11 (525); an L4 gate 0.19 (206) vs none 0.06 (474); event-intensity gate 0.26
(10); sign from description 0.08 (29) vs prior 0.12 (395) — no rescue by sign source; best pairs
sentiment × earnings-event 0.39 (28). RULE 2 gate 4: NOT PASSED for "typed grammar as the
generator". CONFOUND (stated before the run): the arms use different vocabularies — the typed arm
searched ~1,800 sentiment fields × all transforms; the current arm's 28 composites are hand-tuned
(fields, windows, groups fixed). So the result says the labelled vocabulary + random-within-grammar
does not beat hand-tuned composites on these cells; it does not say the labels are wrong or the
judge is useless. Options put to Khoa: (A) typed arm OFF; judge H1/H2/H4 (unit/kind/structure,
label-sign-independent) as a hard pre-sim gate on the current arm; (B) typed arm ON with a curated
vocabulary (description-signed fields, gate-first grammar), 5 more rounds; (C) labels as the
research vocabulary for new hand composites on untouched datasets (C9), each with an EX-ANTE
hypothesis Khoa approves; (D) continue unchanged.

## 11z. Ticked 2026-09-07 22:10: typed arm OFF; structural judge as the pre-sim gate
Retrospective on 9,896 distinct simulated formula/region pairs (POST-HOC, for gate calibration only):
accepted by all structural rules 5,451 (≥1.58: 6.8 %, passes 15); refused by H4-backfill 3,964
(≥1.58: 3.4 %, passes 2 — vRk095rv and qMWbdlmv: REFUTED as a hard rule, mechanism of why unbackfilled
quarterly fields work is UNKNOWN); refused by H4-density 1,108 (0 ≥1.58, 0 pass); H1 units 743 (0, 0);
H2 kinds 346 (0, 0). Ticked gate = H1 + H2 + H4-vector + H4-density, no backfill: `typed.judge(...,
structural=True)` inside `runner.plan` before the novelty gate (flag --no-structure-gate; unlabelled
fields pass through). Expected: ~22 % fewer constructions simulated with, on the record so far,
nothing lost. The typed arm is off (`--ab typed` removed from the unit).

## 12. Open items (refreshed 2026-09-04 14:20)
- CDP survey of the BRAIN UI (C23): Chrome MCP tools were absent for the whole session; owed.
- Climb Discord webhook is dead; forge messages (m12/m13/m6-forge) stay OFF per Khoa's tick.
- No field catalogues for DEU, GBR, MEA (5 pyramid pairs unreachable); crawl when wanted.
- Three Option hypotheses reach no empty cell (their datasets exist only in USA/d1 Option, which is
  full); they serve only as legs of `options_x_short` on USA/d1 Short Interest.
- The 8 VECTOR hypotheses stay parked in `hypotheses/later/` until dense composites are judged.
- DSR calibration (11a): Khoa chose the strict cumulative pool; the per-pool spread measured on
  composites will say how much it bites.
- The verification round of 300 composites is armed (`state/forge/launch_when_auth.sh`) and starts
  by itself once Khoa taps the 14:15 link; results go to 11h.
