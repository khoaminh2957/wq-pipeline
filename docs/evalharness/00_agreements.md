# evalharness — the agreements of record (Khoa, 2026-09-22)

The /goal: a multi-agent harness that builds (a) a PIPELINE EVALUATION SYSTEM producing a concrete
benchmark on three axes, and (b) a big-tech-grade CI/CD system, with the architecture drawn, attacked
and redrawn until it stops yielding defects. Every agent carries an expert job description; every new
module is examined by at least three independent hallucination auditors.

Twenty-one decisions, each a tick or a written instruction. Nothing below is my inference unless it
says so.

## The benchmark

| # | decision | Khoa's answer |
|---|---|---|
| D1 | What receives the final grade | A **pipeline VERSION**, scored over the quota days it runs |
| D2 | How the three axes combine | **Hard floor per axis, no compensation**; clearing all floors then yields a 0–100 score for ranking |
| D5 | Days per official scorecard | **1 quota day** |
| D6 | Where the floors sit | **Absolute, from the goal: 4 submitted alphas per quota day** |
| D14 | Which alphas are graded | **Only alphas the graded version itself produced** — "ko dựa trên dữ liệu cũ" (written instruction, not a tick) |

**The arithmetic consequence, stated before building (D5 × D6).** The best measured rate is 3
submissions over 31,044 simulations = 0.48 per 5,000-sim day; the floor is 8.3× that. Under a Poisson
rate of 0.5/day a single day returns 0 submissions 61 % of the time, and by the rule of three a day
with 0 events does not exclude a true rate as high as 3/day. So: every scorecard will read FAIL for
the foreseeable future, and a one-day count cannot by itself separate version A from version B.
Khoa accepted this knowingly. The reconciliation, agreed: **the floor decides PASS/FAIL and will say
FAIL honestly; the 0–100 score still ranks versions; the uncertainty is printed on the card.**

## The three axes

| axis | what it answers | decided content |
|---|---|---|
| 1 — product | is the alpha good, robust, trustworthy, with OS never observable | D3: DSR + PBO/CSCV + **parameter-neighbourhood stability** + **regime/subperiod stability**. D10: trustworthiness also requires the **8 hard gates of `fetched/hypothesis_standard.md`** — under D17 these are scored AFTER the alpha passes, not before it is simulated |
| 2 — throughput | 4 per day? how many sims per submittable alpha? sustainable or luck? | D7: all three of **Wilson confidence interval on the rate**, **distinct mechanisms among the submissions**, and **the rate holding in the next window** |
| 3 — CI/CD meshing | can branches be grown onto this pipeline, or is it a dead end | D8: **DORA four keys** + **architecture fitness functions** + **a real branch drill every release** (a throwaway component is actually plugged in and CI must carry it) |

## CI/CD

| # | decision | Khoa's answer |
|---|---|---|
| D4 | CI authority | **Block merge + auto-deploy to the VPS when green + rollback** |
| D9 | What the gate blocks on | **Regression** against the live version, plus tests/lint/schema. The 4/day floor is REPORTED, never used to block — otherwise nothing could ever merge |
| D13 | Where CI runs | **A new GitHub private repository + GitHub Actions** |
| D16 | Rollback trigger | **Post-deploy smoke test fails, or the first simulation round crashes** — before any quota is spent |

Infrastructure facts measured 2026-09-22 that constrain D13: there is **no git remote at all** today;
`.git` is 1.4 GB over 6,983 tracked files; the largest tracked file is 49.8 MB (GitHub's hard limit is
100 MB); the 84 MB journal is untracked. A credential scan of every tracked file found **no real
secret** — the two pattern hits are explicitly fake (`FAKE_URL`, "dummy webhook").

## The harness that builds it

| # | decision | Khoa's answer |
|---|---|---|
| D11 | Scale | **~40 agents per phase**, phases sequential, Khoa reviews between phases |
| D12 | Unit of hallucination audit | **Each new MODULE (file + its tests)**, examined by three independent auditors with DIFFERENT lenses: one against the specification, one re-deriving the arithmetic and running the tests, one hunting unstated assumptions and edge cases |
| D15 | When the architecture is finished | **Two consecutive adversarial rounds that find no new defect** |

## The goal amendment (Khoa, 2026-09-22, mid-session)

> "giờ sẽ ưu tiên việc tạo ra alpha submittable trước rồi sau đó mới kiểm tra nó có nghĩa hay ko …
> ưu tiên số 1 là tạo ra nhiều alpha có thể nộp được + ko tái sử dụng các cấu trúc các alpha
> (field + cách sài hàm giống) đã được nộp"

This REVERSES the desk's standing order, and the reversal is recorded rather than quietly applied.
It overrides memory `description-first-alpha-workflow` ("no hypothesis = no sim") and moves
`hypothesis-quality-standard`'s 8 gates from a pre-simulation gate to a post-pass score.

| # | decision | Khoa's answer |
|---|---|---|
| D17 | Order | **Pass first, judge meaning after.** Passes and is meaningful → submit at once; passes but meaning is unclear → weigh it |
| D18 | The no-reuse rule | **Khoa's own `fingerprint.py`**, which he asked me to find rather than invent a rule |
| D19 | Meaning threshold | **8/8 gates → submit automatically; 5–7 → Khoa ticks; under 5 → do not submit** |
| D20 | Generator freedom | **Free within the typed grammar (H1 units, H2 kinds, H4 vector — these are platform 400-errors, not economics), with a feedback loop toward passing.** The hypothesis requirement is dropped |
| D21 | Arms | **Replace wholesale — the entire quota goes to the new branch**, no 50/50 control |

### Evidence placed on the table before implementing D17, both directions

FOR: the binding wall is not the Sharpe bar but fitness / ladder / sub-universe and then correlation,
and fitness is pure arithmetic (Sharpe^1.5·√(σ/max(turnover, 0.125))) that no economic story improves;
the platform allows 85 operators and this desk has ever simulated **20** (`llm_author.md` §7).

AGAINST: the random-within-grammar generator lost **5 of 5** live A/B rounds, 0.1 % of its rows reaching
the Sharpe bar against 2.6 % for the hand-written library (`docs/redesign/02_design.md` §11y).
**MECHANISM: UNKNOWN** — no experiment distinguishes whether it lost for want of economics, for want of
a feedback loop toward passing, or because that grammar was itself too narrow. D20's generator has the
feedback loop the refuted one lacked, so the 5/5 result does not refute D17; it warns that *blind*
generation dies.

### A correction I owe the record (RULE 0 #7)

Earlier this session I told Khoa that "reusing fields does not set the correlation" and that his
no-reuse rule was therefore aimed at the wrong lever. **That was overstated and is withdrawn.** My
2026-09-09 measurement had 60 of its 62 correlation readings inside ONE mechanism, so it established
only that *within* a mechanism the field identity explains nothing and the settings do. `fingerprint.py`
measures *across* mechanisms on a 2,664-alpha pool and finds field-family Jaccard predicting PnL
correlation ≈ 0.61 and operator-multiset cosine ≈ 0.37, validated on 20 and then 23 re-simulated alphas,
flagging 10/10 known PnL-correlated pairs (0.68–0.94) with no false positives across families. The two
measurements answer different questions and do not conflict. Khoa's rule is evidence-backed.

### `fingerprint.py` as it stands (read 2026-09-22, 138 lines, NOT wired into `forge/`)

`structural_signature(formula) -> (field_families, operator_multiset)`, with `canon_field` collapsing
the horizon suffix so `implied_volatility_call_90` and `_150` are one family. `near_duplicate` fires
when field containment ≥ 0.85 AND operator cosine ≥ 0.75 (the "same core bet plus an add-on" cousin),
or when 0.6·Jaccard + 0.4·cosine ≥ 0.85 (the blatant parameter/horizon variant). `StructuralIndex`
registers what has been submitted and rejects the rest of that structural family. Numeric parameters
and neutralisation are deliberately excluded from the coarse hash so their variants share a bucket.
Verified by me on 2026-09-22: a horizon+window+group variant of one IV-spread formula scores 1.000 and
is caught; an IV-spread against a profitability ratio scores 0.200 and is not.

## Open items found while building, not yet decided

**Two tests have been red for weeks and nothing reported it.** `tools/tests/test_layered_sim.py::
test_a_crash_mid_batch_loses_no_journalled_row` fails: it asserts the dispatcher raises RuntimeError
mid-batch and it does not raise. Both `tools/layered_sim.py` and its test were last modified
2026-09-08 18:39, so the failure long predates this session — MEASURED by mtime and by the fact that
nothing in this session touched either file. The full suite is 1,024 tests, of which 1,023 pass; the
215-test `forge/tests` subset that everyone runs by hand is entirely green, which is why nobody saw it.

The CI gate's FIRST run (2026-09-23) found a second one:
`tools/tests/test_layered.py::test_the_model_names_the_operator_the_platform_named` asserts the
operator model would have prevented every journalled warning and finds 20 it would not. That file was
last modified 2026-08-13 -- SIX WEEKS red. Its traceback still names `/Users/kanenguyen/wq_pipeline/`,
the path this repository moved away from, so it may be reading a stale tree as well.

This is the argument for the CI the goal asks for, stated as a measurement rather than a principle:
the desk's manual habit cannot see a red test outside the subset it habitually runs, and the very
first automated run found two that had been invisible for two and six weeks. The gate blocked the
commit of the person who wrote it, which is the only way to know a gate works.

It also constrains the CI design. A gate on the FULL suite would be red on the first commit, so one
of three things must be true before CI can enforce green: the dispatcher test is fixed, or it is
explicitly quarantined with an expiry (the Google TAP practice for known-flaky tests), or the gate
starts on `forge/tests` and widens. Khoa decides; nothing here picks one.

The failing test guards a real property — that a crash mid-batch loses no journalled row — on the one
file that spends quota. Fixing it is not cosmetic, and it is not in this session's scope.

## Correction (2026-09-23 09:05): the quiet-hours rule was only one-third implemented

Khoa, 2026-09-22 23:4x: "các khoảng từ 1-6h sẽ ko tự spam link và số link đó để dành vào những trường
hợp cần thiết". I implemented it in `vps/auth_daemon.py:mint_gap()` and reported it as done. It was not.
There are THREE routine minters, and only one passes through that function:

| minter | passes through the daemon's mint_gap? |
|---|---|
| `auth_daemon.py` | yes |
| `wq-mint.timer` → `tools/mint_link.py --quiet`, every **minute** | no |
| `forge_loop.sh:47` → `tools/mint_link.py --quiet`, every round while auth is dead | no |

MEASURED: the mint budget went from 14 (after the operator's forced mint at 23:25) to 22 by 09:00 — 8
routine mints, against at most 4 the rule allows (the session was alive until ~03:28, then quiet until
06:00, leaving only the 06/07/08/09 hours). The sentence "daemon không còn tự mint trong khung đó" was true
of the daemon and false of what Khoa asked for; it is withdrawn.

Fix, shipped 09:05: the rule now also lives in `tools/mint_link.mint()`, the one function every routine
minter calls, placed BEFORE the hourly gate so a quiet-hours refusal never burns the hour for another
minter. `--force` (the operator asking) is untouched. A test fails if the two copies of the window ever
disagree. First night it can be observed: 2026-09-23 01:00–06:00; the check is the mint budget, which
should not move inside that window unless Khoa forces a link.

## D23 (Khoa, 2026-09-23 ~10:00): the unit-model test stays red and CI keeps blocking

`tools/tests/test_layered.py::test_the_model_names_the_operator_the_platform_named` fails on 20 forge rows
(12 formulas, hypothesis `bold_x_ivspread`, simulated 2026-09-10) where the platform reported
`Incompatible unit for input of "subtract" ... expected "Unit[CSShare:1]", found "Unit[]"`. The live
pre-sim type gate (`forge.typed.judge`, structural) PASSED all 12: the label file calls both
`count_positive_bold_estimates_quarterly_eps_long_2` and `count_negative_bold_estimates_quarterly_eps_long`
`unit=count`, while the platform gives one a unit and the other none. Why: UNKNOWN. Measured impact is low
(UNITS is a non-blocking WARNING; the rows failed LOW_SHARPE/LOW_FITNESS anyway). Offered: monitor-only,
correct the label file (a live-gate change under RULE 2), a 14-day quarantine, or leave it red. Khoa chose
**leave it red, CI keeps blocking.**

Because that test fails only with the desk's data, a hosted runner cannot see it; `tools/ci_gate.py`
`check_known_red` therefore blocks the hermetic tier on the classification's record of it, so GitHub
never shows green while a measured-red test exists.

The OTHER red test was not a decision: `test_a_crash_mid_batch_loses_no_journalled_row` had gone stale when
`_post_patient` (2026-09-08 18:35) began retrying any Exception from a POST, turning the fake's "crash"
into a transient error. The property it guards was re-measured intact (the test body run without the
raise: 20 rows on disk mid-run, all whole). The fake now raises a BaseException subclass, which models a
process death rather than a network error, and a mutation that removes the per-row flush turns it red.

## D24, D25 (Khoa, 2026-09-23 ~13:25), after architecture attack round 2

Round 2 (docs/evalharness/audits/architecture_round2.md): 12 NEW FATAL/SERIOUS defects and 10 round-1
fixes that had not landed. The FATAL one: `compare()` is powerless at the desk's real horizon. At 0.211
clean submissions per quota day, a version that produces NOTHING is flagged "worse" after 7 days with
probability 2.4e-5; telling two versions apart needs ~9 events on one side, ~43 days, while D21 and the
DORA weekly band keep a version alive about a week.

- **D24 — keep D21; compare versions on a higher-frequency, pre-registered estimand**: alphas that clear
  EVERY binding check, per 1,000 scored alphas (34 events in the forge era against 4 clean submissions).
  It is not the submission count, and every report that uses it must say so. The estimand is fixed BEFORE
  the versions run; changing it after seeing a result is exactly the post-hoc choice RULE 0 forbids.
- **D25 — rank versions LEXICOGRAPHICALLY and drop the 0–100 composite.** Order: (1) fewer REFUTED
  submitted alphas; (2) more PROVEN clean submissions per quota day; (3) axis 3. No weights, no constants
  like UNPROVEN_CREDIT, monotone by construction. The hard floors and the PASS/FAIL verdict (D2) stand.
  Round 2 showed the composite FELL when clean output was added (P 32.8 vs P+P+P+R 28.3), bunched every
  passing card into [50, 52.5], and flipped rankings at UNPROVEN_CREDIT = 0.474.

## D26–D28 (Khoa, 2026-09-23 ~15:30), after the draw-3 build audit

The scoring adjudication (docs/evalharness/audits/draw3_build.md, scoring SERIOUS 2, 3, 6) found three
places where D25/D24 as written reward the wrong thing. Khoa ticked:

- **D26 — rank level 1 counts REFUTED + UNPROVEN submitted alphas.** Before: an alpha whose neighbours
  were never measured read "unproven" and cost nothing, while one measured as fragile read "refuted" and
  cost a place, so a version that measured less ranked higher (`rank_cmp(unmeasured, measured)` = -1).
- **D27 — a card whose POST horizon has not closed is not ranked.** `rank_cmp` refuses to order it and
  prints the date from which it can be compared. Before: a live version ranked below an identical retired
  one only because its POSTs had not arrived yet (the round-2 A4 bias, moved into the rank).
- **D28 — D24's estimand is compared WITHIN each cell.** k/n per cell per version; better/worse only
  when the cells that have events agree in direction; disagreement reads INDISTINGUISHABLE. Before: raw
  pooling across cells whose share of the day ranged 0.32–0.94, with all 37 events in USA/d1 (RULE 0 #6).
  This changes the estimand D24 pre-registered; it is changed BEFORE any version comparison has been
  run, so no result was seen that could have motivated it.

## D29–D32 (Khoa, 2026-09-23 ~15:45)

- **D29 — the verdict leads the rank.** Rank key = (PASS before FAIL, then D26 level 1, level 2, level 3).
  Before: the rank ignored the verdict, so a version that missed a hard floor could rank above one that
  met every floor, against D2 ("floors first, then score").
- **D30 — the runner's own run parameters enter the pipeline version.** The arguments the runner
  actually received (argv; FORGE_ARGS and N come from the wq-forge unit on the VPS) are hashed into the
  stamp, so changing them starts a new cohort. /etc/systemd is not touched by deploy.
- **D31 — "block merge" (D4) is enforced on the operator's machine and at deploy, not by GitHub.**
  A private repository on the Free plan has no branch protection, and ci_publish pushes straight to
  main. tools/ci_publish.py runs the gate before it pushes, and tools/deploy.py refuses a tree with no
  green publish record. GitHub Actions is a second, independent run of the same gate that REPORTS; it
  does not block.
- **D32 — the four release flags are ticked and stay:** `deploy.py --force-unpublished`,
  `ci_publish.py --adopt-head SHA`, `--split-golden`, `--no-push`.

## D33–D41 (Khoa, 2026-09-23 ~17:20): the pass-first branch (docs/evalharness/04_passfirst_design.md §8) and two release items

Ticked from the merged design's questions. Every mechanism below is still a PROPOSAL until it passes
RULE 2 gates 3–4 live; the ticks authorise building it and running it under the proof plan.

- **D33 (Q1) — proof is sequential, not randomised.** The incumbent runs first for at least 7 whole
  stamped ET quota days (stamping began 2026-09-23 02:30 ET), then the branch; versions are compared on
  D24 within cell (D28). Cross-time confounds (auth outages, platform drift, incumbent exhaustion) stay
  in the comparison and every read-out lists them first (RULE 0 #6). No feedback-on/off split of rounds.
- **D34 (Q2) — the loop learns from y = 1 when Sharpe ≥ 0.8 × the row's own LOW_SHARPE limit.**
- **D35 (Q3) — priors start uniform, with a 20 % exploration floor that also reaches operators this desk
  has never simulated.** Read as the design's option (b): uniform over every level, the §2.3 exclusions
  kept (signed_power wrapper, vector_neut against a posted formula, decay 16, negated gate payoff leg,
  depth ≥ 7 — each a zero-pass count, not a prior). If Khoa meant "no exclusions either", this line is
  the one to correct.
- **D36 (Q4) — the ticked spending rules are re-keyed on Khoa's fingerprint family:** DEAD_SIMS 40,
  LADDER_DEAD, PASSED_BLOCK 40 per family; a D18 near-dup of an accepted POST is not simulated
  (fail-OPEN at plan time; D18 at submit stays fail-closed and unchanged); no further sims for a family
  whose 984-day PnL correlation with an accepted POST is ≥ 0.70 (its alphas stay eligible);
  quarantine keyed (cell, field).
- **D37 (Q5) — repair queue on:** a row failing exactly one check gets its settings grid (≤ 11 sims,
  each once), ≤ 10 % of a round, and a coin flip per trigger decides repair / no repair, so the queue
  carries its own control.
- **D38 (Q6) — the DSR pool of a generated alpha is its fingerprint family × cell × category.**
  Consequence, named: small pools, a correction near zero, PBO mostly "insufficient" (non-binding).
- **D39 (Q7, Q8 and the follow-up) — D19 is amended for generated alphas.** G1–G3 need written prose a
  generated formula does not have; they are recorded "not applicable to a generated alpha" and printed
  as UNMEASURED on every card. A generated alpha that passes EVERY decidable gate (G4's leg clause,
  G5–G8) is submitted automatically; failing any decidable gate means it is not submitted. A generated
  alpha that is a near-dup of an authored composite inherits that composite's G1–G3 text. There is **no
  5–7 tick queue** ("alpha pass 5-7/8 không thể submit nên bỏ qua") and no AUTO_SUBMIT_STOP file; the
  stop stays `systemctl stop`. For the scorecard, D10's gate half for a generated alpha is the decidable
  gates (it must not read "unproven" merely because G1–G3 cannot exist, or D26 would count every
  generated submission against its version).
- **D40 — push removes unlisted library YAML on the target.** `*.yaml` directly inside
  forge/hypotheses/ and forge/composites/ that the manifest does not list are deleted after the snapshot
  (rollback restores them); staged/ and every other directory are untouched. Measured before the tick:
  a composite deleted in dev stays on /opt/wq and the planner keeps loading it (draw3_fix release §1).
  Extras the loop can reach that remain after the push mark the stamp `+EXTRAS:<n>`. Backups and other
  strays the loop never reads (e.g. tools/*.bak_*, *.pre_*) are reported by `deploy.py status` only:
  marking them would exclude every row from every cohort, the draw-3 BLOCKER again.
- **D41 — the judge runs on the VPS.** It holds the live journal and every submitted alpha's curve; the
  Mac copy holds 0 of 4 curves. push appends its ledger row to the target (draw-3 fix) with
  reconciliation of a failed append.

Implementation note for D30 (ticked 15:45, recorded here because the scoring adjudicator found the
conflict): hashing argv INTO `meta.pipeline_version` would break `live_days`, which joins deploy-ledger
rows to journal rows on that stamp. D30 is implemented as a second stamp, `meta.run_config` (sha256 of
the runner's normalised argv), and a cohort is the pair (pipeline_version, run_config). Changing
FORGE_ARGS or N still starts a new cohort, which is what D30 asks.

Found while recording D40 (read-only ssh, 2026-09-23 ~17:25): the live wq-harvest unit runs
/opt/wq/tools/recover_harvest.py (sha256 4e05040d…) through /opt/wq/harvest_loop.sh. The script is not
in this repository and never was (`git log --all` empty), and vps/harvest_loop.sh is tracked but not in
tools/deploy.py's PLAN. Live code outside version control; the next build brings both under PLAN.

## D42 (Khoa, 2026-09-23 ~17:45) and two orchestrator decisions

- **D42 — the pinned scorer keeps its full transitive closure (51 files).** Any edit to a file the
  scorer imports, at any depth, blocks CI until the golden is re-recorded in its own commit
  (`ci_publish.py --split-golden`). ci_publish's golden-mixing refusal must read the same closure
  (draw3_fix ci SERIOUS 1), or a golden can ride in with the edit that moved it.
- Orchestrator decision (not a mechanism of the loop): the "every forge module has a test" fitness
  floor was raised 0.8 → 1.0 by the draw-3 fix task, following round 2's S4-NL ("every measured check
  must hold"). It covers top-level forge modules only; forge/llm and forge/offline are named as outside.
- Orchestrator decision: the gate no longer cites the VPS wq-forge-tests timer as covering the 37 LLM
  tests pre-merge. Nothing reads that result, and the timer tests the DEPLOYED tree, not the candidate.
  The gate reports them NOT COVERED pre-merge. Reading the timer's result would be a new mechanism and
  is not built.

## D43–D46 (Khoa, 2026-09-23 ~20:15), after the draw-4 module audits (docs/evalharness/audits/draw4_build.md)

- **D43 — `deploy.py watch` rolls back only on a crash BEFORE dispatch** (the planner or an import fails:
  code, before any simulation is spent). A round that ends in error after dispatch is REPORTED, never
  rolled back. Measured before the tick (release adjudicator, loop.log copied 19:10): 23 of 181 finished
  rounds exited in error, 21 of them on 09-06 17:00–20:59 +07, each right after a requests exception to
  api.worldquantbrain.com (14 ReadTimeout, 5 ConnectionError, 3 SSLError); whether code contributed is
  MECHANISM: UNKNOWN. submit runs before the loop reads STOP_FORGE, so no watch can act "before any quota
  is spent" once dispatch has begun; D16's first-round half is narrowed to what a watch can do.
- **D44 — D40 is amended: push REFUSES while unlisted library YAML sits on the target**, lists the files,
  and deletes them (after the snapshot) only when re-run with an explicit flag. Nothing is deleted
  silently. Reason given with the question: forge/offline/promote_staged.py is on /opt/wq, and a
  mechanism promoted on the host would otherwise vanish on the next push.
- **D45 — a cohort's exposure comes from run_config transitions the runner records.** When the runner
  starts with a run_config different from the last one recorded for its pipeline_version, it appends a
  transition row to the ledger the judge reads; a cohort's live days are the pipeline_version's live days
  on which that run_config was the recorded one. Days before any transition row for a cohort read
  "exposure unknown", never a guess.
- **D46 — rows planned from a `--plan` file carry the stamps of the code that actually ran them**
  (design stage 0c), not the base row's copied stamps; recover_orphans must recover exactly the pair that
  was dispatched (draw-4 pipeline P1).

Orchestrator decisions recorded with them (not mechanisms of the loop):
- D30 hashes the plan file's CONTENT into run_config (not its path, not nothing), so two different
  experiment plans are two cohorts.
- vps/wq-forge-tests.sh is excluded from the pipeline id, as wq-judge.sh is: it runs the tests on the
  deployed tree; the loop never runs it.
- The first deploy's ledger row (version 8f8b7517b8598d07, 2026-09-23 06:24 +07) is re-appended to the
  target ledger by the reconciliation step, so the incumbent cohort has an exposure start.
- D41's judge writes at most one card per (cohort, graded ET day, host): a re-run the same day is a no-op.
- Sign-off rule for a module: signed for push when no BLOCKER or SERIOUS defect survives its adjudicator;
  surviving MINOR items go to docs/evalharness/backlog.md with their evidence and are not silently dropped.
  Without this rule each fix round's mutation audit finds a new tail of MINORs and no module converges.

## D47–D53 (Khoa, 2026-09-23 ~21:00), after architecture round 3 (docs/evalharness/audits/architecture_round3.md)

Round 3: 1 NEW FATAL, 15 NEW SERIOUS, 20 NEW MINOR; the D15 clock does not start.

- **D47 — SUPERSEDES D33. The branch is proven by randomising ROUNDS WITHIN each ET day, 50/50 between the
  incumbent (`--mode composites`) and the branch.** D21 is reopened for the proof window only; once gates
  3–4 pass, the whole quota goes to the branch as D21 says. The test conditions on each day (a
  day-stratified exact test on the D24 estimand within cell, D28), so day-level variation cancels.
  Evidence on the tick (round 3 F1, re-derived by the adjudicator): D24 counts vary between ET days with
  dispersion 11.34 inside USA/d1 (Mac and host copies agree; 95 % interval [5.4, 37.8]); between rounds
  within a day it is 1.03. Under no version effect the sequential D33 read-out said better/worse in
  0.49–0.56 of placebo draws, and more days did not reduce it. MECHANISM of the day-level variation:
  UNKNOWN. φ for a single stamped version is unmeasured.
- **D48 — the 7-day incumbent freeze is dropped** (moot under D47: both arms run in the same deployed tree
  on the same days and are told apart by their arm stamp).
- **D49 — every accepted POST counts against rank level 1 of the version that CREATED the alpha, whatever
  its lag.** POST_HORIZON_DAYS bounds credit and finality only (round 3 S1: a POST after 14.05 days cost
  nothing; 19 of 33 unposted candidates on the Mac copy were already older than 14 days).
- **D50 — FORGE_ARGS and N move into /opt/wq/forge.env, shipped by PLAN.** Flipping the branch on or off is
  a deploy (smoked, rolled back with the code). The wq-forge unit gets a one-time attended edit to read
  that EnvironmentFile; deploy still never writes /etc/systemd (D30). run_config is still the hash of what
  the runner parsed.
- **D51 — each generated alpha that clears every check is re-simulated at two one-setting neighbours
  before it can be submitted**, so D3's neighbourhood robustness is measured for generated alphas too
  (round 3 S13: 0 of 919 typed-arm formulas ever had two neighbours, so none could be PROVEN).
- **D52 — G4's decidable clause reads as the standard writes it:** it FAILS only when EVERY leg is crowded
  (alphaCount ≥ 200); a leg's alphaCount is that of its data field(s), grouping fields (sector, industry,
  subindustry) excluded; pinned by a test on the four accepted POSTs (round 3 S12).
- **D53 — the 50/50 share of D47.**

## D54–D60 (Khoa, 2026-09-24 ~02:20), after architecture round 4 (docs/evalharness/audits/architecture_round4.md)

Round 4: 1 NEW FATAL, 5 NEW SERIOUS, 1 SERIOUS earlier fix not landed; the D15 clock does not start.
Correction of the record: the "1.03 between rounds within a day" that D47 cites is not evidence of
binomial rounds; its placebo null median is 0.67 and P = 0.108 (round 4 F1). D47's design stands; its
test is replaced (D54).

- **D54 — D47's unit of analysis is the ROUND.** Each randomised round contributes one D24 rate; the test
  is a permutation of arm labels across the rounds of each ET day (within cell, D28); only rounds the
  randomiser assigned count (search-recipe, ROUNDS=1 hand runs and --plan rounds are excluded and
  counted on the card); the branch arm counts fresh generator draws only, and D51 neighbour and D37 repair
  rows are reported beside it, never in the estimand. Before any read-out a placebo on the desk's own
  rounds must show a false-verdict rate ≤ 5 %. Evidence on the tick: with alphas as the unit, reassigning
  the real rounds at random read better/worse 0.155 of the time (variance 2.18–2.25× the assumed); with
  single alphas reassigned, 0.0375; counting the branch's neighbour rows in arm B read "better" in
  0.285–0.51 of no-effect draws (draw 5 scoring S1).
- **D55 — the read-out is group-sequential:** looks every 7 days, at most 4, with O'Brien–Fleming-type
  boundaries so the total false-verdict rate stays ≤ 5 %; an early stop is allowed only across a boundary.
  (Round 4 S1: daily looks at a fixed 5 % accumulate 0.131 false verdicts by day 28.)
- **D56 — PBO "insufficient" on a generated family pool reads NOT APPLICABLE**, printed UNMEASURED and never
  counted against the version; a generated alpha's robustness rests on DSR and the two D51 neighbours
  (round 4 S5: a D38 pool holds at most 12 settings, PBO needs 20; D39's own reasoning).
- **D57 — rank level 1 compares two cards at EQUAL post-creation exposure:** rank_cmp counts only the POSTs
  that occurred within the same lag from creation on both sides (round 4 S2: D49 × D27 ranked a newer
  identical version above an older one at the same clock).
- **D58 — the loop's memory is bounded in code and by the unit:** the runner reads the journal with bounded
  memory (with a growth test), forge_loop.sh backs off after a runner killed by a signal (exit ≥ 128), and
  wq-forge gets MemoryMax in the same attended unit edit as D50 (round 4 S4: ~17 KB per alpha, 1.5 GB on
  today's journal, no limit on the host).
- **D59 — a pinned requirements lock ships with the release**, covering what the loop imports; the deploy
  smoke checks the host venv against it and refuses a push when a package is missing or at another
  version. Deploy never installs packages itself (round 4 E1: 44 packages on the host, 158 on the Mac;
  statsmodels absent on the host).
- **D60 — rounds outside the randomiser may run during a proof window** (search recipes, hand runs,
  --plan experiments); they spend quota, are excluded from the comparison, and the card prints how many
  were excluded (round 4 S3).
