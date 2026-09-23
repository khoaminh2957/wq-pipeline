# harness5 — round 1 (rung 1 = 1.5 submissions per 5,000-sim day)

## Step 1 — Diagnose (from 01_origins.md, 2026-09-08)
Last measured days: 2026-09-06 (4,824 distinct simulated alphas, 1 submission by POST time, 1 mechanism),
2026-09-07 (5,048, 0), 2026-09-08 (in progress, 0). [audit 2026-09-09: was 4,907 / 5,123 — rung_report counts
journal rows, and 83 + 75 orphan-recovered alphas sit twice in the journal on those days; the distinct counts
are 01_origins' 4,824 / 5,048.] Death stages on the forge era (17,484 alphas): Sharpe under bar 96.6 %;
of the 598 rows ≥ bar, 96.5 % die at fitness / sub-universe / ladder; 18/21 platform passers over the
correlation lines; 21 passes = 2 mechanism keys sharing one leg. **Round-1 target (Khoa Q17): the
supply of DISTINCT mechanisms — new composites on untouched USA/d1 datasets, each an EX-ANTE
hypothesis.** The A/B arm: `arm: new` composites vs the current 28, 50/50 on the same cells.

## Step 2 — Hypotheses (Researcher 18:40; Verifier scoring in progress; Khoa sees the table; sims start without a tick)
Eight new legs on untouched USA/d1 datasets (02_dataset_map.md tier U), eight composites `arm: new`,
every partner leg an existing labelled leg of a different family:
| composite | new leg (dataset, users) | partner leg | combiners | EX-ANTE source |
|---|---|---|---|---|
| newsneg_x_short | news_negative_tone_nlp (nlp_news_scores, 21) − | short_volume_ratio_informed − | multiply, gate | Tetlock 2007; Boehmer-Jones-Zhang 2008; Engelberg-Reed-Ringgenberg 2012 |
| headline_x_profitability | news_headline_tone_benzinga (news82, 52) + | usa_profitability_ratios + | multiply, gate | Tetlock 2007; Novy-Marx 2013 |
| prtone_x_accruals | news_pr_event_tone (news84, 58) + | usa_accruals_cashflow − | multiply, gate | Sloan 1996; Bernard-Thomas 1989 |
| ravenpack_x_short | news_ravenpack_composite_tone (news46, 324) + | short_volume_ratio_informed − | multiply, gate | Tetlock 2007; Boehmer-Jones-Zhang 2008 |
| creditlang_x_accruals | credit_language_safety (model37, 415) + | usa_accruals_cashflow − | multiply, gate | Campbell-Hilscher-Szilagyi 2008; Sloan 1996 |
| headline_x_momentum_gate | news_headline_tone_benzinga + | model12_momentum_component (model12, 265) as GATE only | gate | Chan 2003; Jegadeesh-Titman 1993 |
| multiwire_x_profitability | news_multiwire_headline_tone (news92 VECTOR, 120) + | usa_profitability_ratios + | multiply, gate | Tetlock 2007; Novy-Marx 2013 |
| transcriptneg_x_revision | transcript_negative_logit (news87 VECTOR, 480) − | analyst_estimate_revision_drift + | multiply, gate | Price et al. 2012; Chan-Jegadeesh-Lakonishok 1996 |
Signs read from the field DESCRIPTIONS where the label file's prior contradicted them (model37 credit
ranks: higher = safer; nlp_news_scores negative channel). VECTOR legs use vec_avg + density (zero /
backfill 63). Settings grid STATISTICAL/INDUSTRY/SUBINDUSTRY × decay 4/8 × trunc 0.08.

**Verifier verdicts (round_1/audit_hypotheses.md, 2026-09-08 18:40; applied 18:43, before the first
new-arm round):** SIM — headline_x_profitability, ravenpack_x_short, prtone_x_accruals,
creditlang_x_accruals; FIX then SIM — multiwire_x_profitability (mechanism text named no force:
rewritten), newsneg_x_short and transcriptneg_x_revision (the `gate` combiner inverts a bearish leg:
`if_else(greater(partner⁺, 0.5), A, 0)` leaves the gated-out half uniformly long after neutralisation →
combiners [multiply] only); PULLED — headline_x_momentum_gate (gate-only construction compiles to a
momentum indicator book; regime map contradicts its own weakens_when; shares the news82 leg). Other
fixes: news46 0–100 score density zero → backfill 5 (a gap is not the most negative value); Bernard &
Thomas 1989 is JAR not JAE; negative-tone leg cites Tetlock-Saar-Tsechansky-Macskassy 2008 (firm level);
transcript leg adds Larcker & Zakolyukina 2012. Facts checked: all 22 new-leg fields exist at USA d1
with the assumed type; journal/targets collisions 0; signs match descriptions. Open, harness-wide: the
8 composites are 8 mechanism keys under 00_agreements' definition (composite#datasets#cell — the 7 live ones read 7
distinct keys in the journal) but 6 leg-family pairings (two tone×short, two tone×profitability) [audit
2026-09-09: was "6 mechanism keys"]; the regime map is the same
on all 8 (copy); gate-1 "force" has no schema field. **Round 1 runs 7 composites.**

## Step 3 — Build + tests
- `--ab new` planner arm (runner.py; composites carry `arm: new`) — built, 152 tests green, shipped.
- Submission policy per Q19/Q20 (no weekly rule; ≥ 3 dataset sets per day) — built, shipped.
- Structural gate (H1/H2/H4) — live since 2026-09-07.

## Step 4 — Live A/B (Operator)
VPS dry-run seed 23 (2026-09-08 19:05): 290 constructions, current 150 (twitter×profitability 40,
short×sentiment 40, IV-spread composites 70 on Social Media / Sentiment / Insiders / Short Interest),
new 140 (7 composites × 20 on News 60 / Short Interest 40 / Model 20 / Analyst 20; prtone_x_accruals
waits for a free block). CONFOUND stated before the run: the arms do NOT sit on the same cells —
new mechanisms on untouched datasets fill different pyramid categories by construction (News,
Model, Analyst have no current composite), so Q24's "same cells" holds only on Short Interest.
The rung is read on the new arm scaled to 5,000 sims; the funnel per arm-day is the comparison.
STARTED (Khoa 'bắt đầu đi', 2026-09-08 18:45): unit switched to `--ab new`, loop restarts at the
round boundary (~19:00). Measured quota day: the first full ET day after the switch (ET 2026-09-09 = local 09-09 11:00 →
09-10 11:00); the remainder of ET 09-08 is a warm-up and is reported but not scored.

### Warm-up (ET 2026-09-08, after the 18:42 switch; NOT the measured day)
Rounds every 10–14 min (median 10.7 over the 12 post-switch rounds); quota spent 21:10 (DAILY line at the
21:10 round, last sim dateCreated 21:08 local; audit 2026-09-09: was "21:57"); day total 4,996 sims (2,348 pre-switch,
current 1,638, new 1,010). Submissions 0 in both arms. Funnel per arm (ab_report 22:35):
| arm | n | Sharpe p50 / p90 / max | ≥ 1.58 | binding pass | fails on the ≥1.58 rows |
|---|---|---|---|---|---|
| current (same day, ET 09-08) | 1,638 | 0.76 / 1.34 / 1.86 | 32 (2.0 %) | 0 | LOW_SUB_UNIVERSE 32/32, LOW_FITNESS 30, IS_LADDER 19 |
| new | 1,010 | 0.75 / 1.46 / 1.86 | 53 (5.2 %) | 0 | IS_LADDER 53/53, LOW_FITNESS 53/53, LOW_SUB_UNIVERSE 30 |

[audit 2026-09-09: the current row read "2,690 / 0.77 / 1.36 / 1.86 / 64 (2.4 %) / LOW_FITNESS, IS_LADDER" — that
is ab_report's POOLED current arm, i.e. this day's 1,638 rows plus the 1,049 current-arm rows of the 09-07 typed
A/B (a different day and pairing; 32 ≥ 1.58) and 3 rows dated ET 09-06. Recounted by meta.arm × dateCreated,
the same-day arm is the comparison; its ≥ 1.58 rows fail sub-universe first, not fitness/ladder.]
Per new composite: ravenpack_x_short n 400, p50 1.18, max 1.86, 53 rows ≥ 1.58, fitness max 0.81,
turnover p50 0.16 (NEAR_MISS, block 40); newsneg_x_short n 240, p50 0.62, max 1.30; multiwire n 80
max 0.99; headline n 80 max 0.91; prtone n 80 max 0.75; creditlang n 80 max 0.69; transcript n 50
max 0.50 (the last five — multiwire's max 0.99 is also under DEAD_BEST 1.0 with ≥ DEAD_SIMS 40, forge/allocate.py — will be
DEAD under the allocator; audit 2026-09-09: was "the last four").
OBSERVATION (POST-HOC, one evening): one new mechanism (news46 tone × short-flow) reaches the Sharpe
bar at 2–3× the current arm's rate (arm level 5.2 % vs 2.0 % same-day; ravenpack alone 53/400 = 13 %, 6.6×) and
dies at fitness like everything else: its best-fitness row (O0rZgaQb: Sharpe 1.65, turnover 0.105 → floor
0.125, returns 3.0 %, fitness 0.81) needs returns ≥ 0.125/1.65² ≈ 4.6 % for fitness 1.0; the 53 rows ≥ 1.58 sit
at median Sharpe 1.63 / turnover 0.21 / returns 3.2 % / fitness 0.66 and need 0.21/1.63² ≈ 7.8 %. [audit
2026-09-09: was "fitness 0.81 at turnover 0.16 needs ≈ 4.6 % at Sharpe 1.7 (has ≈ 3.3 %)" — at those inputs the
need is 0.16/1.7² = 5.5 %; 4.6 % is the best row's number at the 12.5 % floor.] MECHANISM of the fitness ceiling: the
platform formula (verified), not a hypothesis. This is bottleneck #2 of 01_origins, and the round-2
diagnosis candidate.

### Measured day ET 2026-09-09 — supply added mid-day (stated before the day's reading)
- 11:00–13:05 local: loop idle on auth (no session); rounds resumed 13:05. By 14:15: 820 distinct
  sims (current 600 / new 220), 0 POSTs. The new arm made 50–60 per round (four of seven round-1
  composites DEAD, ravenpack_x_short holding one 40-block: code_review_0909 F14).
- **14:27 local: the 7 staged composites the Verifier audited PROMOTE (round_1/audit_staged.md §6)
  were moved into the live library** with their 7 legs (predsurprise_x_accruals,
  accruals_x_range_volatility, netcash_x_insider, ai_disagreement_x_putpremium, downgrade_x_short,
  coverage_x_short, chartpattern_x_short). First round with them: 14:30 (new arm 140).
- **14:35 local: three sub-universe triples** (round_2/subuniverse.md §6.1:
  usa_{sentiment,insider,twitter}_x_ivspread_x_profitability, `arm: new`, [multiply]) added; new
  arm 150 from the next round. Library: 45 composites / 59 legs.
- CONFOUND for the day's new-arm reading: the arm's composition changed twice inside the measured
  day; the per-composite funnel (ab_report / diagnosis) is the comparison, the arm rate is reported
  with the split time. Reviewer fixes F1–F10 (rung_report, ab_report, submit, harvest, probe) were
  shipped 14:20; none adds a POST the old code would have made.

- **15:17 local (ET 04:17): first all-binding pass from a NEW mechanism key in the forge era** —
  Vk67oQ5V, `usa_insider_x_ivspread_x_profitability` (the 14:35 triple; Insiders cell, open 2/need 1),
  multiply, SUBINDUSTRY, decay 8: Sharpe 1.67, fitness 1.03, turnover 0.123, returns 4.7 %, sub-universe
  0.77 ≥ 0.72, ladder 2.18 ≥ 2.02, MATCHES_PYRAMID PASS, DSR 0.9999, PBO 0.43–0.48 (pool ok). Probe
  15:33: **prod 0.7323 / self 0.5232 → held `corr-over-line`** (line 0.70). The allocator now classes the
  pair PASSED (block 10/round); the probe reads every sibling. 18:35: probe launched on every row of the
  three triples to map prod-corr across the grid (state/forge/probe_triples.log).
- 14:50–15:03: POW experiment (300 sims, arms pow15/pow2, not in either A/B arm): REFUTED
  (round_2/pow_pairs.md). LADDER-DEAD allocator rule live from the 15:12 round (Khoa tick 14:50).
- 17:00–17:20: session ended, Khoa tapped; 18:30: 3,558 distinct sims (current 1,940 / new 1,318 /
  pow 300), 0 POSTs, session 150 min.

- 18:35–19:11: the 410-row probe (200 correlation reads requested at once, `--wait 120`) landed 0
  numeric readings in 35 min; the round that started 17:54 ran to its 75-min deadline with 10 parents
  at platform status '' (POLL-DEADLINE, ≈ 100 sims not landed; recover_orphans: 0 children attributed
  at 19:10). The previous round (260 landed, 0 deadline) and the loop's own probe (`--limit 60`) had
  no such stall. Probe killed 19:11. TIMELINE COINCIDENCE, MECHANISM UNKNOWN (candidates: the account's
  job queue shared by correlation and simulation jobs; platform slowness at that hour). Rule adopted:
  never request more than 20 correlation reads outside the loop's own probe; re-run the triples' map
  in batches of 20 after the measured day.

- 19:51–20:12, no simulations spent, two ticks from Khoa:
  (i) **INDUSTRY added to the three triples' neutralisation grid** — the probe showed one mechanism,
  one field set, PROD 0.54 at STATISTICAL and 0.71–0.73 at SUBINDUSTRY, while fitness only reaches 1.0
  at SUBINDUSTRY. INDUSTRY carries SUBINDUSTRY's book volatility (+43–49 %) and reads PROD under the
  line on 10 of 17 measured rows (on options×short; transfer to the triple is the experiment).
  (ii) **PASSED_BLOCK 10 → 40** (Khoa 20:12): a pair with a platform pass and no submission now gets a
  NEAR_MISS-sized block. MEASURED: of 53 USA/d1 rows failing only LOW_FITNESS at fitness ≥ 0.80, 52 are
  on the two HARVESTED keys and exactly one (RRV7e8Qo) is on a never-submitted mechanism; the triple's
  SUBINDUSTRY arm needed 120 rows for one all-binding pass, so 10 rows/round cannot search the grid.
  Both shipped, 166 tests green; dry-run seed 71 gives the Insiders cell 60 constructions (was 30).
- **The measured day did NOT reach the Q6 guardrail during the evening session**: 3,723 landed alphas
  at 20:18 with 42 min of session left, and orphan recovery attributed 0 further children in two
  cycles (the platform had not finished them). 76 children were recovered at 20:03 from parents the
  runner had not reaped, taking the day from 3,647 to 3,723. The ET day runs to 11:00 local on 09-10,
  so a further tap before then still counts toward it. Docs: round_3/prod_vs_self.md.

- 20:36 — the POLL-DEADLINE stalls, counted properly: the journal holds 30 POLL-DEADLINE rows across
  three rounds (seeds …3841, …1289, …6440, 10 rows each) but only **3 distinct parent urls** — one stuck
  parent per round, written once per child slot. The loss is ~10 simulations per occurrence, ~30 today,
  not the "10 parents / ~100 sims" this session reported at 19:10 (that read the row count as a parent
  count; corrected). Separately, the 16 true orphan parents all return an EMPTY body from the platform
  (status None, 0 children) and are unrecoverable. CANDIDATE, not established: `_post_patient` retried
  after 8 SSLError and 1 ReadTimeout in today's log, and code_review_0909 F11 notes a ReadTimeout retry
  can create a second multisim parent that the platform never populates — that would produce exactly an
  empty-status parent. No experiment distinguishes it from platform-side loss. MECHANISM: UNKNOWN.
- Identity fix for `recover_orphans` shipped 20:31 (round bookkeeping is not identity, 167 tests): the
  rematch over the 131 historical ORPHAN-UNMATCHED rows attributed only **4**; the arithmetic said 111
  would now match, so the shortfall is at the child re-fetch step and is UNEXPLAINED. The fix's value is
  forward-looking — a construction re-planned in a later round is no longer filed unmatched at all.

### Measured day ET 2026-09-09 — closed state at 00:40 local 09-10 (the day runs to 11:00)
| | |
|---|---|
| landed alphas | **4,526** — Q6 guardrail (≥ 4,000) **MET** |
| per arm | current 2,538 · new 1,688 · pow 150+150 (the POW experiment, in neither arm) |
| submissions | **0** (22 candidates scored each round; 2 already posted, 19 over a correlation line, 1 eligible-but-computing) |
| rung 1 (1.5 per 5,000 on the new arm) | reads 0.00 → **FAIL** unless a POST lands before 11:00 |
The only candidate that could still POST is a sibling of Vk67oQ5V under the lines; the loop probes and
submits every round on its own. Session died 00:33; the loop asks for a link every 5 min.

### Supply batch 3 (agents, 22:00–00:35): 22 new mechanisms staged
45 agents (Researcher → adversarial Verifier → Fixer per mechanism), 42 completed, 3 died on the model
session limit at the FIX stage (the composites for analyst_bold_estimate_conviction,
news_tone_disagreement_trna, valuation_own_history_multiple carry a Verifier verdict but no fixer pass).
`forge/composites/staged/` now holds **22 composites, all 22 load**; nothing was pulled. The agents
re-derived their own numbers and corrected the Verifier where it did not reproduce (one example on file:
a combiner-frequency count of 133/510 that reproduced only as 132/393 under the classification the
compiler actually renders). PROMOTION IS DEFERRED to the 11:00 day boundary: promoting mid-day changed
the new arm's composition twice on 09-09 and is already recorded as that day's confound.

### Promotion, prepared 00:55 for the 11:00 boundary
`forge/offline/promote_staged.py` (172 tests green) audits every staged composite before it moves and
refuses on: fails to load, `arm != new`, no new leg, leg set already live, a bearish leg with the `gate`
combiner, or a partner on the AVOID list (short_volume_ratio_informed, news_ravenpack_composite_tone,
short_interest_surprise — the legs measured never to clear the ladder's first window or carrying the
book's whole PROD history). Dry run on the 22 staged composites: **22 of 22 promotable, 0 refusals.**
Partner spread: insider_significant_buying_drift 9, usa_accruals_cashflow 5, usa_profitability_ratios 3,
sentiment_weekly_continuation 3, option_call_put_iv_spread 2. None uses an AVOID leg — the brief held.
The 9 on the insider leg are the round-3 experiment of round_3/prod_vs_self.md §5 by construction: that
leg's field carries platform alphaCount 1, so if PROD tracks a mechanism's crowding rather than its
fields, those 9 should read lower PROD than the option8 book. Not a prediction — the measurement.

## Step 5 — Audit + ship (Verifier)
_pending the measured day (ET 2026-09-09)_
Hallucination audit of Steps 1–4 (Auditor, 2026-09-09): docs/harness5/audits/origins_round1_audit.md — 9
corrections applied above in place; the arm funnel is now stated per day, not pooled.
