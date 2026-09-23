# harness5 — 01. Origins: why three attempts did not reach 4 submissions per 5,000-sim day

Verifier document, 2026-09-08. Audited 2026-09-09 (docs/harness5/audits/origins_round1_audit.md): every
number re-derived from the VPS journal by a second agent; the four corrections are marked in place.
Every number below was read from the files named beside it and
re-derived a second way (both derivations stated). Labels per CLAUDE.md RULE 0: **MEASURED** (a
count from a journal), **EX-ANTE** (from documentation before the data), **POST-HOC** (a pattern
seen in data — never an explanation), **SPECULATION**. Where no experiment separated candidate
mechanisms the text says **MECHANISM: UNKNOWN**. No simulation was run and nothing was written on
the VPS; the VPS journal was read over `ssh -n` with `forge.score.stage(row)` for the pass verdict.

Target (00_agreements Q1–Q3): 4 POSTed-and-ACTIVE alphas per 5,000-sim quota day = **0.8 per
1,000 sims**. Measured forge yield: **2 / 17,484 = 0.11 per 1,000** (all rows) or **0.22 per 1,000**
on the 9,079-row baseline window (02_design §11w). Gap: **4–7×**.

## Summary table

| era | dates | what generated | sims (MEASURED) | pass platform | submitted ACTIVE | per 1,000 sims | where it stopped |
|---|---|---|---|---|---|---|---|
| harness v0 (`harness/`, HARNESS_DESIGN.md) | 2026-07-22..24 | LLM generators + shadow-sim surrogate, ≤90-sim human-run batches | 26 batch files, 2,101 planned entries (`harness/data/sim_ready*.json`) | iter1 1/90 zero-fail; iter2 60.6%; iter3 33/90 (all crowded) | 3 on 07-23 (gJ9mPgGl, 9q7JLQLe, MPLkl7mk) | ≈1.4 per 1,000 *planned* entries — NOT comparable: July gate suite, hand-driven submits, no DSR/corr-line policy (confound, see §3) | surrogate OOS AUC 0.438; prod-corr has no offline labels; HT family ceiling 0.93 of bar |
| harness13 (`harness13/`, docs/harness13) | 2026-08-10..16 | 13-round × 10-agent build plan; templates + field sampler + MAP-Elites archive; `massgen` | massgen live: 1,120 children accepted (08-12, session died) + 2,000 (08-13) | 2 gems / 2,000 = 0.10 % | 0 (no submit record anywhere) | 0 | round map stopped at R6 of 13 (gate ledger); massgen 0.10 % vs the 2.16 % journal baseline it was to beat |
| climb (`tools/climb.py`, layered A/B/C grammar) | 2026-08-14..09-04 | random grammar over random fields, no hypothesis | 21,972 distinct alphas with checks (`climb.jsonl`) | 1,665 ≥ bar; 873 pass all binding checks (retro rule) | 0 from the generator in 3 weeks (00_baseline §A1) | 0 | 56 correlation reads total, prod-corr median 0.90 (00_baseline §A2) |
| forge (`forge/`, docs/redesign/02_design §11a–11z) | 2026-09-04..08 | hypothesis-first composites on empty pyramid cells, DSR, corr probe, auto-submit class | 17,484 distinct alphas with checks (`forge.jsonl`) | 598 ≥ own bar → 21 pass | 2 (vRk095rv 09-04, kqVbg1xP 09-06) | 0.11 (all) / 0.22 (baseline window) | 19 of 21 passers are one mechanism; 18 of 21 over the prod-corr line; 335 of 337 (hypothesis, cell) pairs never passed |

Ranked bottlenecks (forge era, by candidates dying at the stage; details §5):

| rank | stage | die / enter | share | origin |
|---|---|---|---|---|
| 1 | Sharpe below the cell bar (LOW_SHARPE) | 16,886 / 17,484 | 96.6 % | MEASURED |
| 2 | fitness / sub-universe / ladder on rows ≥ bar | 577 / 598 | 96.5 % | MEASURED; fitness identity EX-ANTE (platform formula), verified on 140 rows |
| 3 | correlation lines (prod < 0.71, self < 0.70) | 18 / 21 | 86 % | MEASURED; mechanism of the 0.79–0.85 readings UNKNOWN |
| 4 | one submission per mechanism: 21 passes = 2 mechanisms | 19 / 21 passers unusable | 90 % | MEASURED (rule + readings) |
| 5 | quota not spent: 2 of 4 full days ≥ 4,000 sims; auth-dead waits 355 / 1,070 min | ≈ 3,600 sims not run on 09-04/05 | — | MEASURED (loop.log) |

Not binding on this data: DSR ≥ 0.95 (21 / 21 candidates pass; the §11a calibration confound
stands — at N = 300 the same gate refuses 41 of 47 ACTIVE alphas); the one-per-mechanism-per-week
rule (held 1 candidate, qMWbdlmv; dropped by Q19).

## 1. The forge funnel (2026-09-04 12:50 → 09-08 16:39 local)

Source: `/opt/wq/state/layered/runs/forge.jsonl` (19,881 lines), `state/forge/scored.jsonl`,
`state/forge/corr.jsonl`, `state/forge/submitted.jsonl`.

Row accounting (MEASURED): 18,061 child rows carry the `alpha` key (17,647 a non-null id; the 414 null
ones are failed POSTs — audit 2026-09-09); 17,642 carry `checks`; 419 do not
(AUTH-FAIL 96, ORPHAN-UNMATCHED 141, ERROR 89, FAIL 40, CANCELLED 25, POLL-* 20, other 8); 158
alpha ids appear twice (orphan recovery) → **17,484 distinct simulated alphas with checks**.
Second derivation: `scored.jsonl` holds 17,269 distinct alphas (215 fewer: rows scored before
recovery or not yet harvested) with stages fail 17,243 / candidate 21 / incomplete 5.

Pass verdict, two derivations: (A) `forge.score.stage(row)["platform"] == "pass"` → **21**;
(B) an independent re-implementation (binding check ≠ NON_BINDING list; FAIL/WARNING/ERROR refuse;
non-PASS is incomplete) → **21**, identical alpha set. Third: `scored.jsonl` candidate = 21.

| stage | count | of previous | note |
|---|---|---|---|
| simulated (checks present) | 17,484 | — | |
| Sharpe ≥ own cell bar | 598 | 3.4 % | 687 rows have Sharpe ≥ 1.58 but 89 sit on d0 cells whose bar is 2.69 |
| every binding check PASS | 21 | 3.5 % | all on USA/d1 Short Interest |
| DSR ≥ 0.95 (strict cumulative pool) | 21 | 100 % | DSR 0.996–0.99999 |
| correlation read (numeric) | 21 | 100 % | 63 alphas with a numeric read (74 attempted), 262 corr.jsonl lines |
| under both lines | 3 | 14 % | vRk095rv, qMWbdlmv, kqVbg1xP; the other 18 read prod 0.79–0.85 |
| POSTed HTTP 201 → ACTIVE | 2 | 67 % | qMWbdlmv held by the 1-per-mechanism-per-week rule |

Per ET quota day (dateCreated of the simulated alpha; a POST is attributed to its alpha's day):

| ET day | sims | ≥ bar | pass | submitted | ≥ 4,000 (Q6 measured day)? |
|---|---|---|---|---|---|
| 09-04 | 3,019 | 119 | 3 | 1 | no |
| 09-05 | 3,375 | 114 | 6 | 1 (kqVbg1xP, POSTed 09-06 06:19 ET) | no |
| 09-06 | 4,824 | 265 | 12 | 0 | yes → 0 submissions |
| 09-07 | 5,048 | 82 | 0 | 0 | yes → 0 submissions |
| 09-08 (partial) | 1,218 | 18 | 0 | 0 | — |

Second derivation: §11o reports 3,019 / 3,370 / 989 (to 19:55 on 09-06) with passes 3 / 6 / 9;
§11w reports 9,079 baseline rows with 21 passes and 475 ≥ 1.58, then 4,462 allocator rows with
0 passes. Both agree with the table (09-05 gained 5 rows from orphan recovery; no pass has landed
since 09-06 21:10 local). On the two days that qualify as measured days under Q6 the submission
count was **0 and 0**; attributing kqVbg1xP by POST time instead gives 1 and 0.

Per cell (MEASURED; pass/1k = platform passes per 1,000 sims):

| cell | sims | ≥ bar | pass | DSR cand | under lines | submitted | pass/1k |
|---|---|---|---|---|---|---|---|
| USA/d1 Short Interest | 3,607 | 487 | 21 | 21 | 3 | 2 | 5.82 |
| USA/d1 Sentiment | 2,853 | 40 | 0 | 0 | 0 | 0 | 0 |
| USA/d1 Social Media | 2,821 | 31 | 0 | 0 | 0 | 0 | 0 |
| USA/d1 Insiders | 1,139 | 40 | 0 | 0 | 0 | 0 | 0 |
| GLB/d1 Fundamental | 2,381 | 0 | 0 | 0 | 0 | 0 | 0 |
| JPN/d1 Fundamental + Model | 1,356 | 0 | 0 | 0 | 0 | 0 | 0 |
| USA/d0 (5 cells; audit 2026-09-09: was "4") | 1,430 | 0 | 0 | 0 | 0 | 0 | 0 |
| GLB/d1 Analyst + Model | 850 | 0 | 0 | 0 | 0 | 0 | 0 |
| EUR/d1 Fundamental + Model | 600 | 0 | 0 | 0 | 0 | 0 | 0 |
| all other cells (10; audit 2026-09-09: was "9") | 447 | 0 | 0 | 0 | 0 | 0 | 0 |

USA/d1 took 10,420 sims (59.6 %); the 7,064 sims outside USA/d1 (40.4 %) produced **0 rows at
their bar**. Second derivation of the USA/d1 count: per-day region table sums 958 + 1,680 + 2,975 +
3,908 + 899 = 10,420.

Which binding check fails the 598 rows ≥ bar (all USA/d1, bar 1.58; a row can fail several):

| failing check | rows | sole failure | limit |
|---|---|---|---|
| LOW_FITNESS | 447 | 79 | 1.0 |
| LOW_SUB_UNIVERSE_SHARPE | 389 | 64 | row-specific (seen −0.66 … 0.90) |
| IS_LADDER_SHARPE | 347 | 8 | 1.58 (9,929 rows) / 2.02 (469) / 2.37 (3) |
| none (pass) | 21 | — | CONCENTRATED_WEIGHT and HIGH_TURNOVER: 1 row each |

Failure sets: all three 180; ladder+fitness 101; fitness+sub-universe 86; fitness only 79;
sub-universe only 64; ladder+sub-universe 58; ladder only 8. Rows failing exactly one check: 151.
Second derivation of the fitness count: 598 − 21 pass − 64 sub-only − 8 ladder-only − 58
ladder+sub = 447. ✔

By hypothesis among the 598 (n, pass | rows failing fitness / sub-universe / ladder | p50 fitness /
ladder / sub-universe Sharpe / turnover / returns):

| hypothesis | n | pass | fit | sub | lad | p50 values |
|---|---|---|---|---|---|---|
| options_x_short | 342 | 19 | 200 | 273 | 182 | 0.95 / 1.56 / 0.65 / 0.157 / 0.049 |
| usa_short_x_profitability_x_accruals | 140 | 2 | 132 | 0 | 85 | 0.86 / 1.53 / 1.19 / 0.103 / 0.034 |
| usa_sentiment_x_ivspread | 40 | 0 | 40 | 40 | 32 | 0.69 / 1.48 / 0.04 / 0.258 / 0.044 |
| usa_insider_x_ivspread | 40 | 0 | 39 | 40 | 16 | 0.79 / 2.06 / 0.06 / 0.192 / 0.045 |
| usa_twitter_x_ivspread | 30 | 0 | 30 | 30 | 27 | 0.59 / 1.44 / 0.21 / 0.323 / 0.044 |
| usa_shortsurprise_x_ivspread (+1 typed row) | 6 | 0 | 6 | 6 | 5 | 0.74 / 1.11 / 0.42 / 0.212 / 0.046 |

EX-ANTE (platform formula, SOURCE `.claude/skills/boost-fitness`, §11l): fitness =
Sharpe·√(|returns| / max(turnover, 0.125)). Verified here on the 140 usa_short rows: max |error|
0.005. Consequence, arithmetic not mechanism: at turnover ≤ 12.5 % fitness is a **returns**
ceiling — Sharpe 1.6 needs returns ≥ 0.125/1.6² ≈ 4.9 %; usa_short rows sit at p50 3.4 %.
The IV-spread composites fail sub-universe on every row ≥ bar (115 / 115); MECHANISM: UNKNOWN
(§11w said the same; no probe has been run).

## 2. Where the sims went, and what each bought

232 distinct hypotheses over 337 (hypothesis, cell) pairs. **Passing mechanism keys: 2**
(`options_x_short#option8|us_short_sale#USA/d1` 19 passes; `usa_short_x_profitability_x_accruals#
fundamental6|us_short_sale#USA/d1` 2). Both share the `us_short_sale` short-volume leg.
**15,577 sims (89.1 %) went to the 335 pairs that never passed.** Second derivation: 17,484 −
1,159 (usa_short pair) − 748 (options_x_short pair) = 15,577. ✔

Largest pairs (sims / ≥ bar / pass / best Sharpe / pass per 1,000):

| hypothesis · cell | sims | ≥ bar | pass | best | pass/1k |
|---|---|---|---|---|---|
| usa_twitter_x_profitability · USA/d1 Social Media | 1,741 | 0 | 0 | 1.41 | 0 |
| short_x_sentiment · USA/d1 Sentiment | 1,404 | 0 | 0 | 1.31 | 0 |
| usa_short_x_profitability_x_accruals · USA/d1 Short Interest | 1,159 | 140 | 2 | 1.87 | 1.73 |
| short_x_sentiment · USA/d1 Short Interest | 890 | 0 | 0 | 1.31 | 0 |
| options_x_short · USA/d1 Short Interest | 748 | 342 | 19 | 2.09 | 25.4 |
| usa_twitter_x_ivspread · USA/d1 Social Media | 690 | 30 | 0 | 1.76 | 0 |
| intangibles_x_profitability (+accruals, +safety) · GLB/d1 Fundamental | 1,814 | 0 | 0 | 1.42 | 0 |
| usa_sentiment_x_ivspread · USA/d1 Sentiment | 550 | 40 | 0 | 1.75 | 0 |
| usa_insider_x_ivspread · USA/d1 Insiders | 529 | 40 | 0 | 1.81 | 0 |
| usa_*_x_ivspread · USA/d0 (5 pairs on 4 cells, bar 2.69; audit 2026-09-09: was "5 cells") | 1,210 | 0 | 0 | 1.74 | 0 — the §11u allocator bug night |
| quality_x_accruals / financing_x_bloat · JPN/d1 | 1,296 | 0 | 0 | 0.84 | 0 |

Arms (MEASURED): standing/search rows 15,462 (646 ≥ 1.58, 21 pass); A/B `current` 1,050 (32, 0);
A/B `typed` 919 (1, 0); C11 arms 53 (8 ≥ 1.58, 0 pass) — §11y's vocabulary confound stands.

POST-HOC pattern, not a mechanism: every pass came from a composite that contains the short-volume
share leg on the one cell (Short Interest) where that leg is the category leg. Candidates for why
the other three USA/d1 cells (6,813 sims, 111 rows ≥ bar, 0 pass) did not convert: (i) their
category legs (sentiment, twitter, insider fields) carry less cross-sectional signal; (ii) the
IV-spread partner leg fails sub-universe by construction; (iii) 20–40-draw cells are under-sampled
(§11l: a 20-draw median wobbles ±0.4). None is established.

## 3. Harness v0 (July 2026): what the surrogate promised and what was measured

Sources: `HARNESS_DESIGN.md` (blueprint + VERIFIER CAVEATS), memory `alpha-harness.md`,
`harness/data/iter1_breakthrough.json`, `iter3_breakthrough.json`, `FINAL_REPORT.json`,
`iter_ledger.jsonl`.

Promise (memory, verbatim): "harness/surrogate.py → HistGBT gate-predictor: **grouped-CV (unseen
skeletons) AUC 0.965, precision@100 = 62% vs 4.7% base = 13× lift** … → the single-stream human sim
becomes ~13× more efficient."

Measured on the first live batch (memory, verbatim): "simmed 90 fresh surrogate-vetted candidates
(harness/generate.py output). REAL zero-fail = 1.1% (1/90) vs surrogate's predicted 55.8%;
out-of-sample AUC 0.438 (worse than random); top-third-by-P had 0% real zero-fail." Second source,
`iter1_breakthrough.json`: `"real_zero_fail_rate": "1.1% (1/90)", "predicted": "55.8%",
"out_of_sample_AUC": 0.438, "top_third_real_zf": "0%"`. ✔ The in-sample number was later corrected
twice by audits: 0.965 → 0.949 (formula-join poisoning, 1,004 old_ids) → 0.944 (field-swap CV leak,
ledger B8).

The memory's own diagnosis is "surrogate distribution shift — grouped-CV 0.965 was in-distribution
(ranked variants of PAST generators, dominated by crowded OHLCV ensembles); generate.py made NOVEL
non-pv1 single-signal alphas across 29 families = out of distribution". That is a POST-HOC
diagnosis written after the 1/90. Candidate mechanisms the record does not separate: (a) covariate
shift as stated; (b) wrong label — the training target was the historical resim check set, which
HARNESS_DESIGN's caveat says "does NOT include the currently binding Power-Pool gates (LOW_2Y,
LOW_SUB_UNIVERSE, active weekly theme)"; (c) settings blindness (the caveat "SURROGATE IS BLIND
WHERE THE GATE IS DECIDED"). Iteration 2 (seeding from 566 known zero-fail structures) read 60.6 %
zero-fail — consistent with (a), but also with "a generator seeded from known passers passes
regardless of the surrogate": no arm ran the seeded generator without the surrogate filter.
**MECHANISM: UNKNOWN.**

What the memory states as the deeper limit, verbatim: "the surrogate predicts ZERO-FAIL, but the
BINDING submittability gate is PROD-CORR<0.7, which needs the realized PnL curve and has ~no
offline labels — so the harness can accelerate the EASY part (finding zero-fail) but NOT the HARD
part (prod-clean)." Iteration 3 (`iter3_breakthrough.json`): 33/90 zero-fail, "with_crowded_
reversal_core: 27/27 (100%)", prod-corr 0.9 / 0.8 — none clean. FINAL_REPORT: the HT
fast-prediction family's "joint ceiling = 0.93 of bar"; three submit tests pinned fitness ≥ 1.0 as
a hard gate and IS_LADDER as a dynamic-limit submit check.

Throughput fact (EX-ANTE from the design, MEASURED by the batch files): the human ran ≤ 90 sims per
batch, single-stream, on the Mac; 26 batch files hold 2,101 entries over 07-22..24. Three ACTIVE
submissions on 07-23 came from breadth scans + 3–4-family blends, not from the surrogate loop.
Yield per planned entry (≈ 1.4 per 1,000) is NOT comparable with forge's 0.11–0.22: different
check suite (memory: "h6 had no ladder check; next day it did"), hand-driven submit decisions, no
DSR or correlation-line policy, and the 4-submit/day quota was the ceiling, not sims. Confound
reported; no verdict on which era's generator was better.

## 4. harness13 (August 2026): what exists, what ran, where it stopped

Exists (`harness13/`, 28 entries — audit 2026-09-09: was "30"; docs/harness13/{DESIGN,DECISIONS,PAPERS,PROMPT}.md): D1–D10 spec
(13 rounds × 10 agents, LLM-free runtime), `templates.py`, `field_sampler.py`, `cell_archive.py`,
`filler.py`, `marginal_score.py`, `gate_r1..r6.py`, `crawl_fields.py`, `crawl_pyramid.py`,
`auth_relay.py`, `notify_relay.py`, `runtime/`, `ops/deploy.sh`, 10 frozen test files (R2 suite
sha 40ab3963…), and `massgen/` (run_massgen.py 85 KB, `mg/`, 4 fidelity audits, 85 experiment
cards). DECISIONS.md records the VPS purchase (160.25.88.163) and experiments E1–E4 (datacenter IP
not blocked; session mintable on the VPS; home + VPS sessions coexist).

Ran (MEASURED):
- Gate ledger `state/harness13/gate_runs.jsonl` (40 entries): R1 PASS, R2 lock (flipped when R3
  shipped code — recorded as not a regression), R3 PASS, **R4 exit 1, R5 exit 0, R6 exit 1**. No
  entry for R7–R13 (stats, orchestrator, harden, chaos, gap, eval, approve). Second derivation: the
  entry counts by round are R3 15 / R5 8 / R4 7 / R6 5 / R2 3 / R1 2 and nothing else.
- `crawl_fields` live: 1,772 calls, 6 catalogues written, 4 failed — the status file's own note:
  "429 BIOMETRICS_THROTTLED on the auth path … this daemon minted persona windows every 540s
  indefinitely, which is the behaviour that drew it." `crawl_pyramid`: fixture dry-run only
  (`r4/crawl_pyramid_dryrun.json`, "SIMULATED" throughout).
- `massgen` live on the VPS, `state/harness13/sim_ceiling*`: run 1 (08-12 16:50–18:00 UTC): 360
  POSTs, 140 accepted (HTTP 201) / 220 refused 401 → 1,120 children, verdict `STOPPED_NOT_429`
  (three probes: "no live session"). Run 2 (08-13, `sim_ceiling2.log`): **GEM_YIELD 2/2000 =
  0.10 %**, MECHANIC_YIELD 1/2000, Wilson [0.03 %, 0.36 %] with the run's own warning that
  clustering (DEFF 14.3) makes the interval ~3× too narrow; a further run started with 21.5 h of
  quota left and has no headline in the log (journal 3,650 rows). The baseline massgen's SPEC set
  out to beat: **600 / 27,826 = 2.156 %** zero-fail over seven days of the pre-existing journal.
- Submissions attributable to harness13: **none found** (`submitted.jsonl` is forge-only; the
  00_baseline tier-4 lineage of 08-14 belongs to the layered generator).

Where it stopped: the round map at R6 of 13 (auth relay; the statistical spine D5, the orchestrator
D8 and the eval/approve rounds were never gated), and massgen at 0.10 % gems against a 2.16 %
baseline. On 08-13 Khoa specified the layered A/B/C random generator (memory
`layered-alpha-generator.md`); the climb loop ran it from 08-14 (`climb.jsonl`, 21,972 distinct
alphas with checks over 12 quota days; 1,665 ≥ bar; 873 pass every binding check by the forge rule
applied retroactively — a retro count, check suites differed by day). 00_baseline §A1–A2
(MEASURED there): screen-passers all time 10,159, correlation readings ever obtained 56, prod-corr
median 0.90, "Submissions from the climb generator in three weeks: 0." The 08-16 `pipeline_harness`
10 × 10 audit rounds (R1 ten cards, R2 ten attack cards) produced audits, not alphas.

## 5. Top five measured bottlenecks between "a formula is simulated" and "an alpha is submitted"

Ranked by how many candidates die at the stage (forge era, 17,484 rows). Confounds named; no fixes
proposed.

1. **Sharpe below the cell bar — 16,886 of 17,484 (96.6 %).** MEASURED. Second derivation: §11w
   baseline 9,079 rows / 475 ≥ 1.58 (5.2 %) + allocator 4,462 / 142 (3.2 %) + A/B 1,440 / 27
   (1.9 %) — all in the same band. 40.4 % of sims were on cells (GLB, JPN, EUR, IND, CHN, every d0)
   with 0 rows at the bar. Confound: the bar differs by cell (1.58 d1 USA; 2.69 d0; GLB adds
   regional sub-lines), and 20–40-draw cells under-sample the tail. §11l's construction ladder
   (single 0.46 → two legs 0.89 → three 1.11 median on GLB) is the only controlled series; it was
   never run on USA/d1.
2. **Fitness / sub-universe / ladder on rows over the bar — 577 of 598 (96.5 %).** MEASURED
   (LOW_FITNESS 447, LOW_SUB_UNIVERSE_SHARPE 389, IS_LADDER_SHARPE 347; sole failures 79 / 64 / 8).
   EX-ANTE + verified: fitness is a returns ceiling below 12.5 % turnover, so decay/smoothing
   recipes could not move it (§11l R14/R15 measured no gain). Confound: these three checks are
   computed on the same book, so their failures are not independent trials (180 rows fail all
   three). Sub-universe failure of every IV-spread row: MECHANISM UNKNOWN.
3. **Correlation lines — 18 of 21 platform passers (86 %) read prod 0.79–0.85.** MEASURED
   (`corr.jsonl`). Confound stated in §11s: 6 of the options×short siblings (16 at §11s's 09-06 count,
   18 at this snapshot) were read 0.79–0.83 *before* kqVbg1xP was posted (audit 2026-09-09: recounted
   from corr.jsonl read_at against the ledger's posted_at) — the correlation is with the book that already existed
   (SPECULATION: via the short-volume leg shared with vRk095rv); C11 (§11u) showed the
   vector_neut residual crosses the lines at Sharpe p50 0.44. Climb era, same wall: 56 reads,
   median 0.90 (00_baseline §A2). Harness v0: "prod-corr … has ~no offline labels."
4. **Mechanism collapse — 21 passes from 2 mechanism keys; one submission per mechanism.**
   MEASURED. 19 of 21 passers belong to `options_x_short` and yielded exactly one POST; 335 of 337
   (hypothesis, cell) pairs and 89.1 % of sims never produced a pass. Per-1,000 pass yield:
   options_x_short 25.4, usa_short 1.73, everything else 0. Confound: the allocator (§11w) skipped
   the two harvested pairs by design, so the 0 / 4,462 after 09-06 21:10 measures only unproven
   pairs; fair baseline on non-harvested pairs was also 0 / 7,223.
5. **Quota not spent — auth-dead waits and crashes.** MEASURED: `loop.log` "auth dead before round"
   lines 71 on 09-05 and 214 on 09-06 (five-minute waits → 355 and 1,070 min; §11s counted 355 and
   1,010 from timestamps — the two methods agree within 6 %); 09-06 17:14 ReadTimeout crashes
   orphaned 1,170 sims (878 recovered); the 09-07 01:53 DAILY line made the loop sleep 84,880 s (audit 2026-09-09: the sleep was
   issued at 11:30, after the reset — the 01:53 line was still inside the loop's grep window,
   forge_loop.sh / §11v — and the loop was restarted 13:57: ≈ 2.5 h lost, not 23.6 h).
   Days with ≥ 4,000 sims: 2 of 4 complete days. This stage removes sims, not candidates; its
   effect on submissions is bounded by the yields above (≈ 3,600 unrun sims × 0.11–0.22 / 1,000
   ≈ 0.4–0.8 submissions).

Stages measured as **not** binding here, kept on record: DSR ≥ 0.95 passed 21 / 21 (pool spreads
0.16–0.27 annual on these cells; §11a's N = 300 calibration refusing 41 / 47 ACTIVE alphas is a
different pool — the confound is the pool definition, ticked strict cumulative by Khoa); the weekly
rule held 1 of 3 under-line candidates (dropped, Q19); GUARD/UNITS refusals 3 and 0.

## 6. What this document does not establish

- Whether any of the five stages would move under a different generator: every number is from one
  library (28 hand-written composites + the typed grammar) on mostly one region. No arm without
  the short-volume leg has ever passed on USA/d1, and no arm has run the GLB construction ladder on
  USA/d1.
- The out-of-sample behaviour of anything: DSR and PBO read in-sample statistics (harness13
  SPEC.md said the same of `eff_floor`). OS is unobservable (Q22). Era yields are not comparable
  (§3); the 0.22 / 1,000 baseline (Q3) is the forge window only.
