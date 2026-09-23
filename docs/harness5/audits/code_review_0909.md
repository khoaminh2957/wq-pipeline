# harness5 — adversarial code review of the round-1 build (Reviewer, 2026-09-09 13:00–14:10 local)

Scope: everything built 2026-09-07/08 and uncommitted — `forge/pbo.py`, `forge/harvest.py` (curve_daily,
pool_members, pool_pbo, the PBO stage), `forge/submit.py` (quota_day, datasets_of, diversity rule, PBO
holds), `forge/probe.py`, `forge/offline/rung_report.py`, `forge/offline/ab_report.py`, `forge/runner.py`
(`--ab new`, paired arm, structural gate), `forge/allocate.py`, `tools/layered_sim.py` (`_post_patient`,
CANCELLED, poll deadline). Question asked: what produces a WRONG NUMBER in the round-1 verdict or a
WRONG SUBMISSION. RULE 1: nothing simulated; the VPS was read over `ssh -n` (journal, scored, corr,
ledger, loop.log, unit file, process list, PnL-cache mtimes) and nothing was written there. The live
library (`forge/hypotheses/*.yaml`, `forge/composites/*.yaml`, staged/, the systemd unit) is untouched.
Parity: the 17 reviewed files have the SAME md5 locally and on `/opt/wq` (MEASURED 13:12) — the review
is of the code that is running.

Labels per CLAUDE.md RULE 0: MEASURED (counted from a file, second derivation stated), EX-ANTE
(from the agreements or platform documentation), POST-HOC, SPECULATION.

## Findings, most damaging first

| # | severity | file:line (before fix) | defect | status |
|---|---|---|---|---|
| F1 | verdict WRONG NUMBER | `forge/offline/rung_report.py:42-61` | the rung rate was POOLED (all arms); Q24 reads the rung on the NEW arm scaled to 5,000; no per-arm rate existed and the ledger row carries no arm | FIXED |
| F2 | verdict WRONG NUMBER | `rung_report.py:42-48`, `ab_report.py:51` | sims counted journal LINES, not alphas: 158 alpha ids have two rows (155 from orphan recovery, ET 09-06: 83, 09-07: 75) → 09-06 read 4,909 (true 4,826), 09-07 5,123 (5,048) | FIXED |
| F3 | WRONG SUBMISSION (403 risk) | `forge/submit.py:247` | a corr reading < 30 min old was trusted even if a POST had been accepted AFTER it was read; a sibling of a just-ACTIVE alpha then POSTs on a stale self-corr → 403 = alpha burned + 403 budget (MAX 1/week) → hold-for-approval for the rest of the measured day | FIXED (necessary, not sufficient — see caveat) |
| F4 | WRONG SUBMISSION (Q20) | `forge/submit.py:160` vs `:242-283` | the ≥ 3-dataset-sets rule was evaluated ONCE per invocation from history; inside the `--cap 4` loop only the same mechanism_key was pruned, so 3 composites on one dataset set could all POST in one invocation | FIXED |
| F5 | verdict WRONG NUMBER (time) | `forge/harvest.py:268-287` | PBO pools were judged in scored-file order and the unfetchable set saved only at the end; the two legacy pools (1,159 + 695 distinct members, 155 curves cached, budget 150/run ≈ 12 runs) are judged before any new-arm pool, whose candidates would sit `pbo-pending` for hours on the measured day | FIXED |
| F6 | funnel WRONG NUMBER | `forge/submit.py:247-257` | the fresh re-read was never persisted: corr.jsonl kept the stale under-line value, `eligible()` listed the same alpha every round (qMWbdlmv: 22 re-reads, fresh reading 0.9668/0.9668) and `ab_report` counted it "corr under" | FIXED |
| F7 | funnel WRONG NUMBER | `ab_report.py:40-41` | "under the lines" used constants 0.71/0.70; the submitter uses the row's limits (all 21,474 rows carry `limit: None` → 0.7/0.7). A 0.70–0.71 reading counted as under in the funnel and held at POST | FIXED (aligned to the submitter; the 0.71 in Q2 is flagged for Khoa) |
| F8 | funnel definition | `ab_report.py:46` | "mechanisms" counted distinct `hypothesis`; 00_agreements defines distinct mechanism = `mechanism_key` (composite + datasets + cell) | FIXED (both reported) |
| F9 | verdict WRONG NUMBER (Q2) | `rung_report.py:50-52` | "submitted" = HTTP 201; Q2 says POSTed AND ACTIVE. `record_adjudication` rows (`kind: adjudication`, status) were ignored, and a second 201 row for one alpha would count twice | FIXED (`active`, `unadjudicated`, one POST per alpha) |
| F10 | verdict misread | `rung_report.py:79-86` | `--rung` tested the LAST measured day even while it is still open (today ET) — a partial day read as a verdict | FIXED (`open` flag, printed) |
| F11 | RULE 0 in code | `tools/layered_sim.py:418` | "A POST that raised never reached the platform, so retrying it cannot double-spend" — false for `ReadTimeout` (request sent, answer late): the retry can create a second multisim parent with no journal row (≤ 10 sims per retry, ≤ 20 per POST, invisible to `sims`) | LEFT (docstring claim; behaviour change to the live dispatcher mid-round is not a safe fix) |
| F12 | allocator waste | `forge/allocate.py:163-167` | the one-block-per-composite×region×delay rule is applied per round, but DEAD is classified per CATEGORY; a composite DEAD as "Sentiment" is ACTIVE as "Social Media" with the same simulations. MEASURED: 3 such composite×cell pairs (typed:sentiment_x_cashflow, typed:sentiment_x_profitability on USA/d1; intangibles_x_… on GLB/d1); none in the round-1 library | LEFT (changes allocation mid-A/B = confound) |
| F13 | structural gate | `forge/typed.py:55`; `fetched/rc/field_labels.jsonl` (vwap) | (a) the tokenizer has no exponent form: `1e-3` → parse refusal; (b) `vwap` is labelled unit `shares` → `close / vwap` refused as "H1 divide price by shares". Round-1 impact 0: dry-runs seed 23 and the live rounds show `structure gate: refused {}`, no composite uses pv fields or exponents | LEFT (whether the platform accepts `1e-3` is unverified; the label file is data, not in git) |
| F14 | design confound | `forge/runner.py:343,365` | `--ab new` gives the new arm `n - n//2` but the new composites' grids are exhausted: today's rounds made current 150 / new 60 and 150 / 50 (`duplicate: 68`). Day so far (ET 09-09, 13:40 local): current 600, new 220. The per-arm rate has a small denominator: one new-arm submission at 1,000 new-arm sims reads 5.0 per 5,000 = rung 5 | LEFT (supply, not code; stated for the record) |

## What was measured (VPS, read-only, 13:05–13:40 local)

- Journal `state/layered/runs/forge.jsonl`: 24,246 rows, 21,595 with an alpha, 158 alpha ids twice
  (155 second rows carry `recovered_at`; 2 RS/RS, 1 R/RS). Per ET day, rows vs DISTINCT alphas:
  09-06 4,909 / 4,826; 09-07 5,123 / 5,048; 09-08 4,996 / 4,996; 09-09 (open) 820 / 820.
  Second derivation: the new `rung_report.report()` run in memory against the same file gives
  4,826 / 5,048 / 4,996 / 820 — identical. Both days stay ≥ 4,000 (F2 changes the rate by 1.5–1.7 %,
  not the measured-day flag).
- Ledger `state/forge/submitted.jsonl`: 4 rows = 2 POSTs (vRk095rv 201 at ET 09-04 10:19, kqVbg1xP
  201 at ET 09-06 06:19) + 2 adjudication rows, both `status: ACTIVE`. New report: 09-04 1/3,019
  (1.66), 09-06 1/4,826 (1.04, measured day), 09-07 0, 09-08 0. `01_origins` attributes kqVbg1xP to
  its alpha's day (09-05); the benchmark of record attributes by POST time (Q1 = submissions per
  quota day) — the two conventions differ by one day for that alpha and the record must say which.
- `scored.jsonl`: 21 candidates, `pbo_status` None on all 21 at 13:10 — the PBO stage had NEVER run
  (0 "PBO pool" lines in loop.log; `pbo_unfetchable.json` absent). The first run with the PBO code
  began 13:17 (PnL-cache mtimes: 31, 32, 31, 34, 22 files per minute 13:17–13:21 → ≈ 32 curves/min,
  so 150 fetches ≈ 5 min, inside the 1,800 s harvest timeout). Pools: usa_short_x_profitability_x_
  accruals 1,159 distinct members, options_x_short 695; 155 cached → ≈ 12 runs to complete both;
  all 21 of their candidates are already posted (2) or over the lines (18) or the stale qMWbdlmv.
- `submit` on every round since 09-08: "21 candidate(s) scored, 1 eligible; held {'already-posted':
  2, 'corr-over-line': 18}" then "qMWbdlmv: stale reading re-read as {'prod': 0.9668, 'self':
  0.9668} -- skipped for now" (22 occurrences; some re-reads `None, None` = computing). The fresh
  re-read protects the POST (F3's path works when the value is fresh) but was never stored (F6).
- Unit `wq-forge.service`: `FORGE_ARGS=--mode composites --order USA/d1,d1 --no-split --delays 1
  --ab new`, N=300. Rounds today 13:05→13:16, 13:21→13:39. Arms per round: current 150 / new 60, 150/50.
- Arm labels: `meta.arm` is set by the planner (`runner.py:354-369`); orphan-recovered rows take meta
  from the plan file (arm included); no alpha row today lacks an arm. Arm MISLABELLING: none found.
  Both arms in one round share `meta.seed` (1 of 1 seeds today has both).
- Corr check rows: PROD/SELF `limit: None` on all 21,474 rows → the submitter's lines are 0.7/0.7.
- Structural gate on real formulas (local, `TY.judge(structural=True)`): the two ACTIVE formulas,
  `if_else(greater(...), x, 0)`, unary minus, `signed_power`, `ts_decay_linear`, `vec_avg` under
  `ts_backfill`, `densify(industry)` all pass; `rank(close / vwap)` refused (vwap unit "shares");
  `1e-3` refused (parse). Live rounds: `structure gate: refused {}`.

## Fixes applied (all covered by tests; `python3 -m pytest forge/tests -q` → 163 passed, was 154)

1. `forge/offline/rung_report.py` (rewritten): one simulation per alpha id (latest row wins); one
   accepted POST per alpha; `active` / `unadjudicated` from adjudication rows; per-arm `by_arm`
   {sims, submitted, rate_per_5000} with the arm taken from the ledger row or the alpha's journal
   `meta.arm`; `open` flag for today (ET); `--arm new` on the rung test; the rung line names an open
   day and un-adjudicated POSTs. Tests: `forge/tests/test_rung_report.py` (ET boundary 23:30 vs
   00:10, duplicate row, duplicate 201 row, adjudication, per-arm rates, `--arm`).
2. `forge/offline/ab_report.py`: rows deduped by alpha; `corr_under` uses `submit.corr_lines(row)`;
   `mechanisms` = distinct mechanism_key, `hypotheses` kept beside it. Test: `test_ab_report.py`.
3. `forge/submit.py`: `today_dataset_sets`, `diversity_ok` (the Q20 rule as a per-POST test, applied
   in `eligible()` AND after every accepted POST in the loop, line 316); `last_accepted_post` +
   `needs_reread` (re-read when > 30 min old OR older than the last accepted POST; the loop advances
   `last_post_at` after each 201, so every later pick in the same invocation is re-read); a complete
   fresh reading is persisted to corr.jsonl (`probe.append_corr`, line 286) so the stored value
   supersedes; `record()` writes `arm`. Tests in `test_submit.py` (3 new).
4. `forge/probe.py`: `append_corr(rows, path)` shared by the probe and the submitter. Test in
   `test_probe.py`.
5. `forge/harvest.py`: `pbo_order()` — postable candidates (not posted, corr not measured over the
   row's lines) first, newest `scored_at` first — applied in `main`; `save_unfetchable` after every
   pool. Tests in `test_harvest.py` (pure ordering + a `main()` run with fake session/fetch asserting
   fetch order and the per-pool save).

Effect on the loop when shipped: no POST it would have made is added; two are removed (a stale
sibling after a POST, a third same-dataset-set POST in one invocation). The PBO verdict order changes;
the verdicts themselves do not.

## Caveats the fixes do not remove (stated, not solved)

- F3 is necessary, not sufficient: if the platform answers the re-read from its own cache computed
  before the new ACTIVE alpha, the stale value returns and the POST goes out. Only round 3's PnL-curve
  pre-screen (design §5 R3) closes that. SPECULATION about the platform cache; not measured.
- Q20 "≥ 3 distinct datasets" is implemented as distinct dataset SETS (`ds1|ds2` strings), as built;
  `option8|us_short_sale` and `fundamental6|us_short_sale` are two sets sharing a dataset. Which
  reading Khoa meant is not decidable from the code.
- Q2's "prod < 0.71" vs the submitter's 0.7 (row limit absent → default): the funnel now follows the
  submitter. If 0.71 is intended, `CORR_LINE_DEFAULT` is the one line to change — a policy question.
- `sims` counts landed alphas; quota SPENT also includes ERROR/FAIL/CANCELLED children (174 rows) and
  any F11 duplicate parent. The ≥ 4,000 guardrail is read on landed alphas.
- The PBO pool splits one composite across category names (pool key includes category); the DSR pool
  has the same split by construction (C13). Smaller pools → "insufficient" more often → no hold.
  Not a wrong number, a weaker test.
- The day-attribution convention: sims by `dateCreated`, POSTs by POST time. A candidate simulated at
  23:30 ET and posted at 00:30 ET lands on the next day's numerator with the previous day's
  denominator. The pipeline's own lag (harvest → probe +120 s → next round's submit) makes this a
  systematic edge effect at 11:00 local; the record must state it.

## Not touched, deliberately

`forge/pbo.py` (algorithm reviewed: rank fraction (n+1), ties to the lower rank — the degenerate
all-tied OOS case yields PBO 1.0, a hold, which is the conservative side), `forge/allocate.py`
(F12), `forge/runner.py` (no defect found in the arm tagging), `tools/layered_sim.py` (F11 is a
docstring claim; CANCELLED-terminal and the poll deadline were traced through `_reap` and
`recover_orphans.orphans()`: a POLL-DEADLINE child row carries no alpha and is not platform-terminal,
so the parent is recovered later with one alpha row — no double count), the library, the unit, the VPS.
