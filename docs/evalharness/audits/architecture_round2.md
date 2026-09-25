# evalharness: architecture round 2, adjudication (2026-09-23)

This file merges three attacks on draw 2 (statistician, gamer, systems) into one ruled list. Draw 2 is
the section "Draw 2" of `docs/evalharness/01_architecture.md`, as implemented in
`forge/offline/benchmark.py`, `tools/ci_gate.py`, `tools/ci_classify.py`, `tools/ci_publish.py`,
`tools/ci_fixture.py`, `tools/ci_golden_card.json`, `tools/deploy.py`, `forge/runner.py` and
`forge/offline/recover_orphans.py`.

**Snapshot judged.** The snapshot is published commit `1fce953`. I ran `cmp` on 17 files. The dev tree is
byte-identical to the CI checkout for every judged file except `tools/deploy.py` and
`tools/tests/test_deploy.py`. Both of those were edited at 12:52, after the commit, under deploy's own
audit. The defect this file cites from `deploy.py` (a no-op push is logged as `deployed`) exists in both
versions.

**Method.** I re-ran every kept finding myself. The scripts are in the session scratchpad under
`scratchpad/adjr2/`:

| script | what it checks |
|---|---|
| `load.py` | loads the real inputs |
| `v1_card.py` | the card |
| `v2_composite.py` | the composite |
| `v3_compare.py` | exposure and censoring |
| `v4_power.py` | power |
| `v5_misc.py` | interval, dedupe, caveat, regime |
| `v6_census.py` | the gate census |
| `v7_publish.py` | the real `data_tier` with stubbed pytest results |
| `v8_golden.py` | scorer edits against the golden card |
| `v9_dora.py` | DORA |
| `v10_closure.py` | the closure |
| `v11_orph.py` | orphan attribution |
| `v12_decay.py` | card decay |
| `clone/` | a clone of `1fce953` used for mutations |

What I did not do:

- Nothing was simulated, and `--live` was never passed.
- The VPS was touched once, with `ssh -n -o BatchMode=yes` running `ls` and `grep -c` only.
- GitHub was read with `gh api` and `gh run view --log`.

Origin labels follow RULE 0:

- `EX-ANTE (code)`: read from the code or the spec.
- `POST-HOC`: a regularity seen in data.
- `SPECULATION`: neither.

No mechanism is claimed for any data regularity below.

**Classification.** Each finding is marked in one of two ways:

- **NEW**: the defect did not exist in round 1, or round 1 did not name it.
- **NOT-LANDED**: round 1 named it and prescribed a fix, and the fix is absent from `1fce953`. The
  evidence is shown.

Anything that only restates a round-1 item that draw 2 did fix has been dropped. See "Dropped,
merged, corrected".

---

## Verdict

**Counts of surviving findings:**

| class | FATAL | SERIOUS | MINOR |
|---|---|---|---|
| NEW | 1 | 11 | 9 |
| NOT-LANDED | 0 | 10 | 5 |

Plus 2 SUSPECTED.

**D15 clock: does not start.** Round 2 found NEW defects.

**A partial draw 3 is needed. It covers the post-deploy comparison only (A1–A4).** That arrow is the
one draw 2 added, and it cannot judge a version at this desk's rate, for three reasons:

- The effect is too rare to detect. A version that stops producing entirely reads "worse" with
  P = 2.4e-5 after 7 quota days.
- Versions do not live long enough to accumulate evidence. D21 replaces a version wholesale, and
  DORA's band asks for at least one deploy a week.
- No concurrent control exists, because D21 forbids one.

Every repair changes a recorded decision (D9, D21) or the estimand. Under RULE 2, that is Khoa's
choice, made by tick. It is not a code fix.

Everything else can be fixed inside draw 2's structure. That covers the axis-1/axis-2 scoring, the
golden card, the known-red allowance, DORA in the gate, the version hash, orphan attribution, the sync,
and the round-1 leftovers. Draw 2 kept three things from draw 1: the three boxes, the one-way
judged-never-imports-judge direction, and the pre-merge half of the split. Those still hold.

---

## FATAL (NEW)

### A1. The post-deploy comparison cannot detect a regression within a version's lifetime

Source: statistician SERIOUS "non-overlap is not a 5 % test", and systems SERIOUS "compare() is nearly
blind; the DORA band works against it". I merged the two and raised the severity. This is the only arrow
draw 2 introduced, and at the measured rate it cannot do its job.

**Evidence.** I ran the real `poisson_interval` over the card's rounded limits under an assumed
independent-Poisson model. The model is SPECULATION; see X1. Version A runs at the measured
4/19 = 0.211 per day. Script: `v4_power.py`.

| quota days each | P(worse \| B produces 0) | P(worse \| B = A/2) | P(better \| B = 2A) | size under H0 |
|---|---|---|---|---|
| 7 | 2.4e-05 | 0.000 | 0.001 | 0.0000 |
| 14 | 0.0034 | 0.001 | 0.011 | 0.0004 |
| 19 | 0.021 | 0.003 | 0.023 | 0.0009 |
| 28 | 0.14 | 0.011 | 0.050 | 0.0018 |
| 60 | 0.88 | 0.057 | 0.193 | 0.0029 |

- **A total collapse needs 9 events in A.** A B with 0 clean submissions reads "worse" only when A has
  at least 9: `lower(8) = 3.454 < upper(0) = 3.689 < lower(9) = 4.115` (per day, with d cancelling).
  At 0.211 per day, 9 events take about 43 quota days.
- **The rule is not a 5 % test.** Non-overlap of two 95 % intervals has size ≤ 0.3 %. The
  statistician's exact enumeration agrees (0.0008 at 0.2/day, 19 d).
- **Versions do not live that long.** EX-ANTE (spec): D21 says a version replaces its predecessor
  wholesale with no control, and axis 3's DORA band scores `deploys_per_week ≥ 1`. So a version
  lives about a week, and at 7 days even a total collapse is invisible.

**Fix: a decision for Khoa, by tick (RULE 2).** Each option below also carries A2–A4:

- (a) Reopen D21 and randomise at the round level within each quota day. `runner.py --ab` already
  tags `meta.arm`. Test the rate ratio with an exact conditional binomial test, pre-registered d and
  α, and a day-block permutation for dispersion.
- (b) Keep D21 and move the estimand to a pre-registered quantity with enough events per day, such
  as rows clearing every binding check per 1,000 sims. The measured counts per active day are
  3, 6, 12, 0, 0, 1, 13, 1, 1, 0, which are overdispersed (see X1). Label the comparison as
  sequential and confounded by date.
- (c) Withdraw D9's "regression against the live version" and say so in `00_agreements.md`.

The statistician estimates about 120 days per arm to detect a doubling at 0.2/day even with the
correct test.

---

## SERIOUS (NEW)

### A2. `compare()` has no caller, and D9's regression gate is enforced nowhere

Source: systems, rated FATAL. I settled it at SERIOUS. Even with a caller, today it has no data (0
stamped rows) and, per A1, no power. The defect is the claim that it exists.

Evidence, `EX-ANTE (code)`:

- `grep` finds one call site, `forge/tests/test_benchmark.py:211`.
- `benchmark.main()` exposes `--since`, `--until` and `--version` only.
- No `vps/` unit or timer invokes `benchmark`.
- Nothing persists or reads a verdict.

The documents still claim the gate:

- `tools/ci_gate.py:3` says "the gate blocks on REGRESSION against the live version".
- `.github/workflows/ci.yml:57` says "tools/ci_gate.py blocks on REGRESSION instead (D9)".

VPS, read-only, today:

- `/opt/wq/DEPLOYED.json` is absent.
- `forge/offline/benchmark.py` is absent.
- `grep -c pipeline_version` on the forge journal returns 0.
- The runner has no stamping (`def pipeline_version` count 0).
- There are 209 plans, and `wq-forge` is active.

**Fix.** After A1's decision, either give `compare()` a scheduled caller, a persisted verdict ledger
and a named consumer (an alert or a rollback), or strike D9's post-deploy half from the docstring,
`ci.yml` and the draw-2 diagram.

### A3. Exposure is not the version's live time, in `compare()` or in a version card

Source: statistician SERIOUS, and systems SERIOUS, "exposure" and "a card is not a fixed fact". Merged.

**The mechanism, `EX-ANTE (code)`.**

- `compare()` sets d = the count of quota days that carry at least one row. The inner `build_from`
  then grades every calendar day from `min(use)` to `max(use)`, gaps included.
- `build_from(version=V)` grades from V's first row to **today**, so a retired version's rate keeps
  falling.
- A deploy day counts as a whole day for both versions.

**Evidence.**

- **Gaps, measured with the real `compare()` (`v3_compare.py`).** A has one clean submission on 09-01
  and rows on 09-01..03. B has one clean submission on 09-05 and rows on 09-05, 09-10 and 09-15.
  Result: `quota_days_each 3`, with A at 0.333/day and B at 0.091/day (1/11). Same k, same reported d,
  a 3.7× ratio.
- **The desk's own history has the same shape.** `POST-HOC`: scored rows exist on only 10 of the 19
  days 09-04..09-22. The days 09-12..19 and 09-21 are empty (`v1_card.py`). Stamped as one version,
  compare would report d = 10 and divide by 19.
- **Decay, measured with the real `build_from` (`v12_decay.py`).** V makes 20 clean submissions on
  09-10..14:

  | graded on | clean / days | rate | floor | composite |
  |---|---|---|---|---|
  | 09-15 | 20 / 5 | 4.0 | met, PASS | 52.5 |
  | 09-23 | 20 / 13 | 1.538 | unmet, FAIL | 40.2 |

  The rows are identical in both cases.

**Fix.** Exposure = the ET quota days on which the version was the running version, taken from the
deploy ledger. Split deploy days or exclude them. Use one exposure function in `build_from` and in
`compare()`.

### A4. A later POST is credited to an older cohort, so identical versions read "worse"

Source: statistician SERIOUS, systems SERIOUS, and gamer MINOR ("a closed window rises"). Merged.

`EX-ANTE (code)`: `build_from` credits every accepted POST in the ledger at read time to the version
that produced the alpha (lines 563–570). There is no follow-up horizon. `compare()` also reads the
wall clock (`current_quota_day()` with no `now`), so its result depends on when it is run.

Evidence:

- **Measured (`v3_compare.py`).** Two identical cohorts each make 12 clean alphas over 7 days, and
  each alpha is POSTed 10 days after creation. With the ledger as of 09-23 15:00 ET, A reads 1.714/day
  [0.886, 2.995] and B reads 0 [0, 0.527]. **Verdict: `worse`.**
- **The lags this rests on.** `POST-HOC`, N = 4 (`v1_card.py`): creation-to-POST lags were 0.01, 0.77,
  0.02 and 11.49 days, the last for rK5RGeqa. Why rK5RGeqa waited is UNKNOWN.
- **Retroactive credit.** POST-HOC, from the gamer and re-derived as algebra: window 09-04..11 reads
  3/8 as of 09-12 and 4/8 today, because of rK5RGeqa.

Two further confounds have no magnitude measured:

- Calendar time between sequential versions.
- The shared 4/day cap: B's submitter can POST A's backlog.

**Fix.** Count only POSTs within a fixed horizon h of creation, the same h for both arms. Compare only
after h has elapsed for the newer cohort. Pass `now` explicitly. Print the date gap between the
compared windows.

### A5. "Not refuted" rewards not measuring, and axis 2 counts unproven as clean

Source: statistician SERIOUS (6) and gamer SERIOUS (rank 1). Merged. This is new in draw 2: round 1's
F2 fix made "unmeasured" not-a-fail, and draw 2 then counted it as clean throughput.

**The rule, `EX-ANTE (code)`.** `clean = status != "refuted"` (:574), and a gate that could not be
measured reads None. So a missing measurement can move an alpha only toward clean, never away from it.

**Measured through the real `build_from` (`v2_composite.py`).**

| the same fragile alpha | status | clean | axis 1 | composite |
|---|---|---|---|---|
| neighbours measured (fragile) | refuted | 0 | 0 | 12.5 |
| neighbours never simulated | unproven | 1 | 0.5 | 22.8 |

**The real census** (`v6_census.py`): 37 rows clear every binding check, graded as if submitted.

| gate | result |
|---|---|
| binding | True 37 |
| dsr | True 37 |
| pbo | True 37 |
| D10 | True 37 |
| corr | False 32 / True 5 |
| neighbourhood | None 26 / True 11 |
| regime | None 37 |

Withholding the correlation readings turns this from `{refuted 32, unproven 5}` into `{unproven 37}`.

**The D10 gate cannot return False.**

- `EX-ANTE (code)`: the runner simulates only composites that `ST.admissible()` accepts
  (`runner.py:135`), and the card re-runs the same `hard_gates`.
- `POST-HOC`: 0 of 94 composites trip a hard gate today.
- 207 of 290 hypothesis ids in scored rows (1,416 rows) are absent from the map, so their gate reads
  None.
- `load_standard()` swallows any exception into `{}` (:614).

**On real data today:**

- All 4 submissions are `unproven`, with neighbourhood n = 0 and regime unmeasured (`v1_card.py`).
- Axis 1 therefore equals `UNPROVEN_CREDIT` exactly.
- Axis 2's "clean" equals "submitted".

**Fix.** Count clean-and-proven separately from clean-but-unproven, and put the floor and the rate on
the proven count only. Make `load_standard` fail loudly. See also S8-NL for which gates are independent
of the pipeline.

### A6. Rankings flip on an unmeasured constant, `UNPROVEN_CREDIT`

Source: statistician SERIOUS (3). This is NEW because the constant is new in draw 2. It shares its fix
with F4-NL.

Measured with the real functions over 19 days, varying c (`v2_composite.py`):

- **Four unproven against two proven plus two refuted.** 4 unproven reads 21.6 / 22.6 / 23.0 / 23.2
  and 2P+2R reads 23.0, at c = 0.40 / 0.45 / 0.47 / 0.48. By hand the crossover is
  `20c + 20/19 = 10 + 10/19`, giving c* = 0.4737.
- **One more clean-but-unproven alpha lowers the score.** P+U reads 27.0 to 32.7 against P's 32.8 for
  c from 0.40 to 0.97. Adding a clean unproven alpha lowers the composite for every c < 0.974.
- **The golden card makes the change visible, but not justified.** It pins the constant. G-S1 below
  shows the pin is absorbed by a re-record.

**Fix.** Remove the constant. Rank lexicographically on (proven, then refuted count as a penalty), and
show unproven without scoring it.

### A7. The golden card does not pin the scorer's decisions

Source: gamer SERIOUS (rank 4), and the axis-3/compare part of systems' S8 finding. The golden card is
draw 2's mechanism, so its coverage gap is NEW. The re-record process is S8-NL.

Method: I applied each edit in memory to `benchmark.py` and ran the real `ci_fixture.card()` against
the committed golden (`v8_golden.py`).

| edit | golden diffs | real 2026-09-04 card |
|---|---|---|
| axis-1 floor `proven == n` → `refuted == 0` | **0** | unmet drops to axis 2 only |
| axis-2 floor `rate >= 4` → `hi >= 4` | **0** | unmet drops to axis 1 only |
| **both** | **0** | **FAIL → PASS** (composite 27.5) |
| DSR threshold 0.95 → 0.50 | **0** | — |
| `compare()` verdict hard-wired to "indistinguishable" | **0** | — |
| DORA CFR check → always True | **0** | — |
| import-cycle fitness → always True | **0** | — |
| neighbour threshold 0.5 → 0.05 | 1 (caught) | — |
| control: UNPROVEN_CREDIT 0.5 → 1.0, not re-recorded | 3 (caught) | — |

On the clone, `test_benchmark.py` plus `test_ci_gate.py` give an identical `2 failed, 36 passed` for the
original and for the two-floor mutant. The 2 failures are the data-bound drill tests.

`01_architecture.md` claims that "a change to FLOOR / WEIGHT / any gate is a change to the golden file".
That claim is false for predicates and thresholds.

**Fix.** Make the fixture a truth table:

- one alpha per gate that fails only that gate;
- one alpha per gate where only that gate is None;
- cases at each floor boundary;
- `compare()` cases for better, worse and indistinguishable;
- a `dora_checks` case.

Put every numeric threshold into the pinned constants.

### A8. D23's one-test exception is implemented as an open-ended allowance

Source: gamer SERIOUS (ranks 2 and 5), systems SERIOUS. Merged. I measured it with the real
`ci_publish.data_tier` and `ci_classify.classify`, with only the pytest result stubbed
(`v7_publish.py`):

1. **Committed classification plus a new failure.** Result: `False`,
   `FAIL -- NEW failures: forge/tests/test_submit.py::test_something_new`.
2. **Re-classification.** `classify()` puts every DATA-arm failure into `red`, giving `red` = both
   tests. `data_tier` then returns `True`: `KNOWN-RED ONLY (…test_something_new, …) -- allowed`.
3. **The same node id, a different failure** ("54 journalled" instead of "20"). Result: `True`,
   allowed. The match is on node id only (`ci_publish.py:57-61`).

There are two routes to step 2:

- By hand. The gate's own staleness warning says "re-run tools/ci_classify.py".
- Inside `ci_publish.main()`. Step 1 tests the tree at time T1. If the code changes before step 2,
  step 2 re-classifies. The new failures become `red`, and step 3 syncs and pushes the tree as it is at
  T3. `EX-ANTE (code)`: nothing binds the published tree to the tree the data tier tested.

**Fix.**

- Put the allowance in a committed file listing D23's one node id and its expected failure (or turn the
  test into a ratchet, `miss <= 20`).
- A newly measured red test blocks until Khoa ticks it.
- Record the tree hash at step 1 and refuse to publish a different one.

### A9. DORA inside axis 3 makes the pre-merge gate depend on deploy history, and no-op deploys pad it

Source: gamer SERIOUS (rank 6) and systems SERIOUS. Merged. This is NEW: round 1's S4 fix was "score
DORA, or say it is display-only", and scoring it created this.

`EX-ANTE (code)`:

- `check_fitness` → `axis3_gearing()` → `_dora_from_ledger(ROOT)` reads `state/deploys.jsonl`, which
  `deploy.py` writes on the same machine.
- `push()` logs every rc other than `refused`. The "nothing to do" path returns `EXIT["deployed"]`.
  That is line 516 in `1fce953` and line 553 in the dev tree.

Measured with the real `dora` and `axis3_gearing`, drill stubbed ok (`v9_dora.py`):

| ledger | DORA | axis 3 |
|---|---|---|
| none | — | 7/7, met |
| a rollback, then a deploy 30 h later | CFR 0.5, 0.5/week, TTR 30 h | 7/10 = 0.70, **floor unmet** (any diff blocks) |
| 1 rollback + 7 no-op "deployed" rows | CFR 0.125, 2.0/week, TTR 1.0 h | all three checks True |

A tree failing 2 of 7 architecture checks scores 5/7 = 0.714 and is blocked. Adding the three passing
DORA checks gives 8/10 = 0.800, which meets the floor.

**Latent.** `state/deploys.jsonl` does not exist today.

**Fix.**

- Take DORA out of every pre-merge blocking check. Report it post-deploy.
- Log a no-op push as `noop` and exclude it from DORA.
- Count a restore only when the version changes.

### A10. `pipeline_version` misses the modules the loop imports lazily, the library and the loop driver

Source: systems SERIOUS. This is NEW: the closure hash is draw 2's fix for S1-ii.

**The comment is wrong.** `deploy.py:124-125` says the closure includes modules imported "lazily,
inside functions". `loop_closure()` records `sys.modules` after the entry points are imported, so
imports inside function bodies never run.

Measured on the `1fce953` clone with the CI venv (`v10_closure.py`):

- The closure has 43 files, `pipeline_version ec6a5cd75d58fea2`.
- Absent from it:
  - `forge/pbo.py`, imported inside a function at `harvest.py:151` and used to compute `pbo_pass`,
    which is an axis-1 gate;
  - `tools/self_corr_predict.py` (`harvest.py:274`);
  - `forge/offline/refresh_cells.py` and `tools/record_adjudication.py`, which `forge_loop.sh` runs
    every round;
  - every YAML file.

Which edits move the id:

| edit | `pipeline_version` | whole-tree `version` |
|---|---|---|
| `pbo.evaluate` threshold 0.5 → 0.9 | unchanged | changes |
| a composite YAML | unchanged | changes |
| `forge_loop.sh` concurrency 9 → 3 | unchanged | changes |
| control: a `runner.py` edit | moves to `98b4fb752f04a362` | — |

**Consequence.** D14 cohorts would pool alphas made by different code.

**Fix.**

- Hash the shipped loop surface: `forge/`, the loop drivers and the library YAML, minus the named judge
  and CI files.
- Or assert, at the end of a real round, that `sys.modules` is a subset of the closure.

### A11. Orphan recovery assigns an ambiguous construction to whichever plan `glob` lists first

Source: systems SERIOUS. This is NEW: round 1's S1-i fix added `pipeline_version` to `ROUND_KEYS`.

`EX-ANTE (code)`: `match()` returns `hits[0]` when the identities agree after `ROUND_KEYS` are removed,
and `child_row` copies `con.meta`.

Measured (`v11_orph.py`):

- Plans `101.json {A_version}` and `202.json {B_version}` hold the same construction.
- `glob` order is `['202.json', '101.json']`.
- The recovered meta reads `{'seed': 202, 'pipeline_version': 'B_version'}`, whichever round
  actually POSTed it.

Draw 2 turns an honest `ORPHAN-UNMATCHED` into a permanent mis-attribution under D14.

**Fix.** When the matched hits disagree on `pipeline_version`, write `pipeline_version = "ambiguous"` and
exclude that row from cohorts. Alternatively, stamp seed and version into the `PARENT-POSTED` row and
match on them.

### A12. `ci_publish.sync()` overwrites a checkout that has diverged, and deletes what it cannot see

Source: systems SERIOUS. `EX-ANTE (code)`: `rsync -rc --delete` runs per SUBSET directory, then
`git add -A`. There is no HEAD check, no `git status` check and no fetch.

Measured (clone of `1fce953`, real `sync()` with `P.CI` pointed at the clone):

- I committed `HOTFIX`, which appends to `forge/probe.py` and adds `forge/hotfix_guard.py`.
- After `sync()`, `git status` shows ` M forge/probe.py` and ` D forge/hotfix_guard.py`, and
  `grep -c HOTFIX forge/probe.py` returns 0.

**Correction to the systems report.** It said a *refused* publish has already overwritten the
checkout. That is true only for a refusal at step 2 (classification). A step-1 refusal (data tier)
returns before any sync.

**Fix.** Refuse to sync unless HEAD equals the last commit `ci_publish` itself recorded and the tree is
clean. Fetch first, and refuse if `origin/main` is ahead. Sync only after steps 1 and 2 pass.

---

## SERIOUS (NOT-LANDED)

### F4-NL. The composite still falls when clean output is added, is almost flat above the floors, and axis 3 decides it

Round 1's F4 fix was:

- "score axis 1 as a count";
- "leave out of the ranking any axis that is identical across the versions".

Neither landed. Source: statistician SERIOUS (4) and (6), merged.

**Adding clean output lowers the composite.** Real `build_from`, 19 days (`v2_composite.py`):

| card | composite |
|---|---|
| P | 32.8 |
| P+U | 28.0 |
| P+P+P | 33.3 |
| P+P+P+U | 31.1 |
| P+P+P+R | **28.3** |

P+P+P+R reads 28.3 against P's 32.8. That is round 1's own counter-example back again: three clean
submissions rank below one. The repo test passes only because `_card()` substitutes
`clean/(clean+refuted)` for axis 1 and uses `days=1` (`test_benchmark.py:162-174`).

**The scale.** `EX-ANTE (algebra)`: composite = 20·a1 + 5·a2 + 12.5·a3. Axis 1's floor is its maximum
(1.0), and axis 2's floor is the platform cap (4/day). So "twice the floor" is unreachable on both, and
every PASS card lies in [50.0, 52.5]; I checked both ends with the real `scorecard()`. Only axis 3 moves
a PASS card.

Below the floors:

- One axis-3 check out of 7 is worth 1.79 points.
- One clean submission over 19 days is worth 0.263 points.
- So one check equals 6.8 submissions.
- Axis 2's whole 95 % interval, [0.057, 0.539], spans 22.8–25.2.

**NEW element.** `build()` measures axis 3 on the checkout that runs it (`:629`, `root=ROOT`), never
on the version being graded. Two version cards built from one checkout carry the same axis 3.

**Fix.**

- Replace the composite with a lexicographic ranking.
- Test monotonicity through `axis1_product` at the desk's real exposure.
- Measure axis 3 on the graded version's DEPLOYED tree, or drop it from the ranking.

### S3-NL. `regime_stability` still passes "mixed" and still decides on the endpoints

The code is unchanged in kind. Re-measured with the current function (`v5_misc.py`): two near-flat
thirds and one losing third give `mixed [1.145, 1.806, -10.293]`. The gate passes it, while the whole
curve has PnL −101.4 and Sharpe −2.58. Source: statistician.

**Fix.** As round 1 said: judge each third against its own SE, and require a cumulative shape (a
reset/jump check).

### S4-NL. Axis 3's checks are still existence checks, and a crashed drill still reads FLOOR MET

What has not changed:

| check | code |
|---|---|
| `--ab` | still a substring (`:347`) |
| the version check | `tools/deploy.py` `.exists()` (`:351`) |
| the import scan | still a regex (`:408`) |
| "every forge module has a test" | a file-stem match, so an empty file satisfies it |
| the floor | still 0.80, so one check in 7 may fail |

**Observed on Actions (missed by all three).** Both draw-2 runs (35822646606 and 35823401832) print
`[NO] a real branch goes through the planner` and `AXIS 3 GEARING FLOOR MET 6 of 7`. That is round 1's
headline S4 observation again. Source: gamer.

**Fix.** As round 1 said: AST import graph, an argparse-level `--ab` test, and each check blocking on
its own (or floor 1.0).

### S6-NL. A stale classification still passes, and the stated coverage still does not exist

- `ok = r.returncode == 0` (`ci_gate.py:98`). Actions run 35822646606 printed
  `[PASS] tests … WARNING: tests or code changed since the classification`.
- `covered_instead_by` still says "(MacBook pre-push, VPS)" (`:101`). There is no hook in either repo
  (`core.hooksPath` unset, samples only), and `ci_gate.py` is absent on the VPS.

Source: gamer, systems.

**Fix.** Stale means BLOCK. Print "ci_publish.py data tier, when run".

### S7-NL. `check_no_live` and the parsers are unchanged, so the credentialed tiers still have no backstop (missed by all three)

None of round 1's S7 fixes landed:

- `grep allow_abbrev` finds nothing in `forge/runner.py`, `tools/layered_sim.py` or `forge/submit.py`,
  which define `--live`, `--live` and `--submit`.
- There is no `conftest.py` at the root, in `forge/tests` or in `tools/tests`.
- `check_no_live` still scans only `*.py` under the test directories and `.github/*.yml`, and does not
  look for `--submit`.

Actual quota spend remains SUSPECTED; no test that would spend was found.

**Fix.** As round 1 said.

### S8-NL. The judge is still editable by the judged commit, and still uses the pipeline's own instruments

**(i) The process.** Source: gamer rank 3.

- `--record-golden` writes the new card and prints it, with no diff (`ci_gate.py:297-302`).
- `ci_publish` commits and pushes to `main` without showing the golden diff.
- `gh api …/branches/main/protection` and `…/rulesets` both return HTTP 403 ("Upgrade to GitHub Pro").
- No test pins FLOOR or WEIGHT as literals: the tests at `test_benchmark.py:27,32` read `B.FLOOR`.
- The golden card carries no scorer hash.
- `cac48d7` changed the scorer, the fixture and the golden in one commit.

**(ii) The instruments (missed by all three).** DSR is still read from `scored.jsonl` (the pipeline's
own harvest), and the correlation lines come from `SUB.corr_lines`. `EX-ANTE (code)`: for anything the
forge submitter POSTs, 5 of axis 1's 7 gates are the pipeline's own admission filters, re-read:

| axis-1 gate | the pipeline's own admission filter |
|---|---|
| binding | `score.platform_verdict` requires PASS before stage `candidate` |
| DSR | `candidate` requires `dsr ≥ DSR_MIN = 0.95` |
| PBO | `submit.eligible` holds `pbo-fail` |
| corr | `submit.eligible` holds `corr-over-line` and `corr-unmeasured` |
| D10 | `runner.plan` simulates only `ST.admissible` composites |

Those five can disagree with admission only if a threshold, a line or the library changes in between.
The two independent gates, neighbourhood and regime, are the two that are unmeasured for all 4 real
submissions.

**Fix.**

- Re-record the golden in a separate commit, refused when the same commit touches the scorer.
- Pin literals in a test.
- Put the scorer hash in the golden.
- Give the judge its own DSR from curves, with a judge-owned `n_trials`.

### S9-NL. Sustainability (D7) is always False on the whole-history and version cards, and "False" stands for "not evaluable"

`EX-ANTE (code)`: with `since=None`, `first = min(by_day)`, so the previous window lies wholly before the
cohort's first row. `prev_rows` is then empty and `held_in_previous_window` is False. `compare()` passes
`since = min(use)` on rows filtered to its own days, with the same effect.

Measured on the real journal (`v1_card.py`):

| window | clean / days | rate | sustainable |
|---|---|---|---|
| whole history | 4/19 | 0.211 | False |
| since 09-05 | 3/18 | 0.167 | True |
| since 09-06 | 2/17 | 0.118 | True |
| since 09-10 | 2/13 | 0.154 | True |

A version at 4.0/day reads False as well (`v12_decay.py`).

Other parts of round 1's S9 that did not land:

- D7 says the NEXT window; the code still uses the previous one.
- `interval_excludes_zero` is implied by `two_or_more_mechanisms`.

Sources: statistician, gamer, systems.

**Fix.** Print "not evaluable". Implement D7 as written, or tick a change to it.

### S10-NL. A card still cannot say what produced it, and it changes after the fact

- There is no provenance field (generated_at, host, scorer hash, input identity) in `benchmark.py`, and
  no card is persisted.
- The standard and library are loaded at grading time (`load_standard()`).

`EX-ANTE (code)`, missed by all three: the neighbour pool is `all_rows=scored_rows` (`:573`), every
scored row of every version and every date. So version B's simulations can refute or prove version A's
alphas after the fact.

Source: systems, with the neighbour-pool element added.

**Fix.**

- Add a provenance block.
- Freeze a D10 verdict per alpha at submit time.
- Bound the neighbour pool, or record it.
- Append official cards to a ledger.

### S1iii-NL. The runner's fallback stamp is still the whole-tree hash with `+untracked`

`runner.py:93-95` computes `version_id(content_hashes(file_map(base))) + "+untracked"`:

- it hashes the whole tree, not the closure;
- it uses the PLAN keys, not the remote-path map.

`EX-ANTE (code)`. The VPS has no `DEPLOYED.json`, so the first stamped rows would land in this third
namespace (systems measured three ids for the same bytes). Source: systems.

**Fix.** Make the fallback the same closure function over the remote-path map, and mark a
manifest-versus-bytes mismatch.

### M9-NL. Nothing enforces that published or deployed code passed the gate

This is round 1's M9 and S6 ("install a real pre-push hook") together, now with evidence that branch
protection cannot be had on the current plan (403 above).

- All 6 Actions runs concluded `failure`, and all 7 commits sit on `main`.
- `deploy.py` never consults CI or `ci_publish`.
- `.github/` is outside `ci_publish.SUBSET`, so the workflow that defines the gate can change only
  through a plain push.

Sources: systems, gamer.

**Correction to the systems report.** "5 of 7 commits bypassed ci_publish" is not evidence: `ci_publish`
first exists in the 6th commit, `cac48d7`.

**Fix.**

- Record D4's "block merge" as not deliverable on this plan, or change the plan or the enforcement point.
- `deploy.py` refuses a pipeline hash without a green or known-red-only publish record.
- Add `.github` to SUBSET.

---

## MINOR (NEW)

- **m1. The previous-window count includes refuted POSTs.** It counts every accepted POST
  (`:581-582`), and the fixture never reaches the branch. `EX-ANTE (code)`; gamer demonstrated it.
  Fix: filter by the window's own axis-1 status.
- **m2. `_poisson_cdf` underflows.** `exp(-λ)` underflows at λ ≈ 746 (`math.exp(-746) = 0.0`).
  Measured: k = 700 gives an upper limit of 745.133 against scipy's 753.833, and k = 1000 gives
  [742.0, 745.1] against [939.0, 1064.0]. It is exact to ≤ 2e-6 for k ≤ 685. Unreachable today (needs
  ≥ 172 quota days at the cap). Fix: `scipy.stats.chi2.ppf`, or log space.
- **m3. `compare()`'s only test compares 0 against 0.** Row `b0` carries a LOW_SHARPE FAIL, so it is
  refuted. Measured: A and B are both `[0.0, 1.23]`, "indistinguishable". The comment "0 vs 1" is wrong.
  Fix: fixture cases where the rule must say better and worse.
- **m4. A refusal is labelled `[NOTE]`.** `verdict[:4] if verdict in ("PASS","FAIL") else "NOTE"`, so
  `FAIL -- NEW failures` prints as `[NOTE]` (`v7_publish.py` output). Fix: label by `ok`.
- **m5. The 12-line `details` cap hides new failures in one configuration.** Exactly 11 import-error
  lines followed by the known-red line lets new failures through. Measured: `data_tier` returns True.
  The failure count is never compared with the size of `red`. Fix: parse the full `-rfE` summary.
- **m6. The clean arm's venv sits inside the checkout, and that misclassifies a test.** Measured on the
  clone: `test_the_plan_covers_every_file_the_live_loop_actually_imports` gives `1 passed` with the
  venv outside the tree and `AssertionError` with `.v` copied inside it. The test is in the committed
  `deselect` list. Fix: put the venv outside the checkout.
- **m7. Fitness function 2 blames `staged/` for any loader failure,** including a broken top-level
  file. `EX-ANTE (code)`. The schema check still blocks, so no gate passes wrongly. Fix: load the copy
  without `staged/` first.
- **m8. `ci_publish.py` and `ci_classify.py` have no tests** (D12). `tools/tests` has
  `test_ci_gate.py` and `test_deploy.py` only.
- **m9. The record contradicts the code, with no tick on the deviations.**
  - `ci_publish` cites "D22", which `00_agreements.md` does not contain.
  - The draw-2 diagram says "Wilson interval"; the code uses Poisson.
  - D8's lead time is computed but not scored.
  - D5 is 1 quota day; `build()` defaults to all history.
  - The only MEASURED card is the weak date-window card D14 excludes.

  Fix: list each as an open item for Khoa.

## MINOR (NOT-LANDED)

- **F3 remainder. The per-day interval still leaves [0, 4], and the floor is judged on the point
  estimate.** Measured: (1, 1) gives [0.025, 5.572], and (4, 1) gives [1.09, 10.24] with `floor_met`
  True.
- **M3. The caveat is still hard-coded.** It prints "61 %"; the card's own rate implies
  e^−0.211 = 0.81.
- **M5. Stale counts remain in the docs.** "22 of the 247" and "blocks on REGRESSION (D9)" are still in
  the `ci_gate.py` docstring and `ci.yml`.
- **M6/M7. POSTs are not deduplicated and not checked for later status.** Measured: one alpha with two
  accepted POSTs gives `clean_submissions 2`. A POST still counts on 201 whatever its later status.
  Real impact today: none (4 distinct alphas).
- **S2 remainder (missed by all three). Neighbourhood is still a ratio against 0.5, and the 0.5 is
  not marked unmeasured.** Round 1 asked for "not a ratio". The one-setting definition did land.

## SUSPECTED

- **X1. Overdispersion.** Rows clearing every binding check per active ET day are
  `3,6,12,0,0,1,13,1,1,0`: dispersion 6.73, χ² 60.6 on 9 df, p = 1e-9. I re-derived this
  (`POST-HOC`). Whether clean submissions inherit this is unmeasured (4 events). If they do, every
  Poisson interval on the card is too narrow, and the statistician's 25–27 % false-alarm rate for
  `compare()` applies. Mechanism UNKNOWN. To settle: ≥ 30 quota days of per-day clean counts and a
  dispersion test, or a day-block bootstrap.
- **X2. Single run per classifier arm.** A flaky test that fails once in CLEAN is deselected
  indefinitely. No flaky test has been identified. To settle: ≥ 3 runs per arm, classifying on
  agreement.

---

## Confirmed correct (re-derived by me)

- **The brief's MEASURED card reproduces** (`v1_card.py`): 4 clean over 19 whole ET quota days
  (09-04..09-22, with 09-23 excluded), 0.211/day, Poisson 95 % [0.057, 0.539]. Axis 1 is
  `{unproven: 4}` with value 0.5. Composite 23.6 = 10.0 + 1.05 + 12.5 (axis 3 fixed at 1.0).
- **The creation-to-POST timings.** Creation ET days: vRk095rv 09-04, kqVbg1xP 09-05, vRk1J2jd 09-10,
  rK5RGeqa 09-11. POST quota days: 09-04, 09-06, 09-10, 09-22. Lags: 0.01, 0.77, 0.02, 11.49 d.
- **`poisson_interval` is exact Garwood for k ≤ 685.** It matches scipy at every tested (k, d).
- **Round-1 fixes that landed:**

  | item | what landed |
  |---|---|
  | F2 | the dict-curve parse; "unmeasured" is not a fail |
  | F3 | the unit is per ET quota day; WARNING rows are scored |
  | S5 | whole ET days; the unfinished day is excluded; an unknown `--version` raises |
  | S1-i | `pipeline_version` is in `ROUND_KEYS` locally. The VPS still has `("seed",)` |
  | S1-ii | on the manifest path, CI files do not move `pipeline_version` |
  | S2 | the one-setting neighbour definition |
  | S9 | D10 is present in axis 1 |
  | S4 | DORA is in the value |
  | F1 | the pre-merge gate no longer grades the journal |
  | M1/M2 | Wilson removed |

- **Non-compensation still holds.** A floor edit is what flips PASS; the composite cannot.
- **The judged-never-imports-judge direction holds.** Only `ci_fixture`, `ci_gate`, `deploy.py`
  (text) and `ci.yml` name `benchmark`.
- **Making a red test also fail without data does not launder it into data-bound.** `classify()` puts
  every DATA-arm failure in `red` first. The laundering route is into `red` (A8).
- **A total break of the known-red test's subject is caught,** because other node ids fail. (gamer; I
  confirmed it by reading the code.)
- **The latest Actions run is BLOCKED only on known-red.** Run 35823401832: pinned scorer 25.8,
  hermetic 826 passed / 13 skipped / 167 deselected.
- **The VPS matches draw 2's admission of zero data** (read-only): no `DEPLOYED.json`, 0 stamped rows,
  the stamping runner not deployed.

## Dropped, merged, corrected

- **Merged.** Each row is one finding here, reported by more than one attacker:

  | finding | reports merged |
  |---|---|
  | A1 | statistician S3 and systems "compare power / DORA band" |
  | A3 | statistician S1, systems "exposure" and systems "retired card decays" |
  | A4 | statistician S2, systems "right-censoring" and gamer "a closed window rises" |
  | A5 | statistician S8 and gamer S1 |
  | A8 | gamer S2, gamer S5 and systems "known-red" |
  | A9 | gamer S6 and systems "DORA blocks publishes" |
  | F4-NL | statistician S4 (F4) and S6 (composite scale) |
  | S9-NL + m1 | statistician S7, gamer "prev window counts refuted" and systems D7 |
  | F3 remainder | statistician "interval exceeds 4" and systems F3 |
  | M6/M7 | statistician M6 and gamer M6/M7 |
  | S6-NL | gamer S6 and systems S6 |
  | M9-NL | systems "D4 block merge" and systems "only path" |
  | m4 | gamer and systems `[NOTE]` |

- **Severity changed.**
  - systems' "compare() has no caller" was FATAL; it is **A2, SERIOUS**. The FATAL is the design
    (A1), which a caller would not cure.
  - statistician's overdispersed false-alarm rate is demoted to **SUSPECTED (X1)**. The dispersion was
    measured on qualified rows, not on submissions.
- **Corrected.**
  - **A7:** gamer said "neighbour ratio 0.5 edits leave the golden identical". The neighbour-threshold
    edit IS caught (1 diff). The DSR edit is not.
  - **A12:** systems said "even a REFUSED publish has already overwritten". That holds only for a
    step-2 refusal.
  - **M9-NL:** systems' "5 of 7 commits did not go through ci_publish" is dropped as evidence. The
    tool did not exist for 5 of them.
- **Classification ruled.** The golden card's coverage gap is NEW (A7), because the mechanism is new in
  draw 2. The re-record process is S8-NL, and systems' "pinned scorer does not pin axis 3/compare" is
  merged into A7.
- **Not re-reported.** Round-1 F1, F2 and the F3 unit are fixed as listed above.
- **Disclosure carried forward.** The gamer's first `push()` experiment made 8 read-only
  `ssh … pgrep -fc` calls to the VPS before its stub was installed. Nothing was written.

## Contradictions settled

| point | reviewers | ruling |
|---|---|---|
| Severity of `compare()` having no caller | systems FATAL | SERIOUS (A2). The FATAL is A1, the design |
| Whether the non-overlap rule's size is 0.5 % or 26 % | statistician (both) | ≤ 0.3 % under Poisson (measured); the 26 % needs X1 to hold |
| Whether the golden card's gaps are NEW or S8 | gamer NEW, systems NOT-LANDED | Coverage is NEW (A7); the re-record process and instruments are S8-NL |
| The fix for A4 | statistician: randomise within the day | That contradicts D21. It is Khoa's decision (A1 fix (a)), not a code fix |
| Whether "clean" differs from "submitted" | gamer: identical on real data | True today (POST-HOC, 4/4), because neighbourhood and regime are unmeasured; not true by construction |

## Missed by all three

1. **The remaining round-1 S7 fixes did not land.** There is no `allow_abbrev=False`, no conftest
   network guard, and `check_no_live` is unchanged (S7-NL).
2. **The judge re-reads the pipeline's own admission filters.** 5 of 7 axis-1 gates are binding, DSR,
   PBO, corr and D10 as the pipeline itself applied them before POSTing. Only neighbourhood and regime
   are independent, and both are unmeasured for every real submission (S8-NL ii). So axis 1's value on
   real data equals `UNPROVEN_CREDIT` because of how the gates are wired (A5, A6). The census that
   shows it is `POST-HOC`.
3. **Both draw-2 Actions runs repeat round 1's S4 observation.** The drill crashed and axis 3 read
   FLOOR MET 6/7 (S4-NL).
4. **The neighbour pool is every version's rows at every date,** so one version's simulations change
   another version's axis-1 status after the fact (S10-NL).
5. **D21 blocks the statistically correct fix.** Randomised concurrent arms contradict "replace
   wholesale". The post-deploy half therefore has no workable design without a Khoa decision (A1).
   Systems noted that D21 forces a sequential comparison; nobody drew the conclusion that it needs a
   tick.
6. **Round 1's S2 "not a ratio" did not land** (S2 remainder).

## Shortest ordered fix list

1. **Khoa ticks A1's option (a), (b) or (c).** Then give `compare()` a caller or strike it (A2). Use
   ledger-based exposure (A3) and a fixed POST horizon with an explicit `now` (A4).
2. **Scoring.** Put clean and the floors on the PROVEN count only, and delete `UNPROVEN_CREDIT`
   (A5, A6). Replace the composite with a lexicographic ranking, and measure axis 3 on the graded tree
   or drop it from ranking (F4-NL). Mark sustainability "not evaluable" (S9-NL). Add provenance
   (S10-NL).
3. **Pinning.** Use a truth-table fixture with `compare()` and DORA cases, and thresholds among the
   pinned constants (A7). Re-record the golden in a separate commit, with literal pins and a scorer
   hash (S8-NL).
4. **CI allowances.** Make D23 a committed one-id allowlist with its expected failure, and bind publish
   to the tested tree hash (A8). Refuse a divergent sync (A12). Stale means BLOCK (S6-NL). Take DORA
   out of the pre-merge gate and log no-ops as `noop` (A9).
5. **Attribution.** Hash `forge/`, the loop drivers and the YAML library (A10). Use the same function
   for the runner's fallback (S1iii-NL). Mark orphans ambiguous across versions (A11).
6. **Round-1 leftovers.** S3, S4, S7 and M9 (NOT-LANDED above), then the MINOR items.
