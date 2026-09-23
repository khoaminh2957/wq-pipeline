# evalharness: architecture round 1, adjudication (2026-09-23)

The adjudicator's single list, built from three attacks (statistician, gamer, systems) on
`forge/offline/benchmark.py`, `forge/tests/test_benchmark.py`, `tools/ci_gate.py` and
`docs/evalharness/01_architecture.md`, checked against `00_agreements.md`.

**Snapshot judged.** The files changed while the reviewers worked. `benchmark.py` changed at 09:42,
`ci_gate.py` and `test_ci_gate.py` at 10:09, `ci_classify.py` at 10:46, `deploy.py` at 10:28, and
commit `5281873` was pushed at 10:50. The reviewers attacked the 08:59 state. This adjudication is
against commit `5281873`, and the dev tree matches it byte for byte: I ran `cmp` on the 10 relevant
files, and both trees have pipeline version `bd323ecf690b29e5` (549 files). Where a 10:09 change fixed
a reviewer's finding, the finding is listed under DROPPED/SUPERSEDED with the evidence.

**Method.** I re-ran every finding kept below myself. The scripts are in the session scratchpad
(`scratchpad/adjr1/`: `v1_curves.py`, `v2_cohort.py`, `v3_composite.py`, `v5_neigh.py`,
`v5b_typed.py`, `nolive/`, `cyc/`, `curves/`). Their outputs are quoted inline so this file stands on
its own. Nothing was simulated and `--live` was never passed. The VPS was touched only through
`ssh -n -o BatchMode=yes` running `ls`/`stat`/`grep`/`python3 -B -c` reads, plus one `scp` of the 4
submitted alphas' PnL curves into the scratchpad. The GitHub Actions logs were read with
`gh run view --log`.

Origin labels follow RULE 0:
- `EX-ANTE (code)`: read from the code or spec before looking at the data.
- `POST-HOC`: a regularity seen in the data.
- `SPECULATION`: neither.

No mechanism is claimed for any data regularity below.

---

## Verdict

**(a) Fix before the scorecard can be trusted to rank two pipeline versions:** F1, F2, F3 and F4, then
S1, S2, S5 and S8. Three of these carry most of the weight:

- **F2:** axis 1 is structurally zero.
- **F3:** axis 2 measures per-5,000-COMPLETE-rows against a per-quota-day floor.
- **F4:** the composite is flat above the floors and non-monotone below them.

Together they mean today's composite moves only with `10 × per_5000`. That term is a function of journal
volume and of how rows get a WARNING status, not of product.

**(b) Round 2 should attack the FIXED version, not a redesign, with one redraw.** What holds up:

- The three boxes (pipeline, then files, then scorecard, then gate).
- The judged-never-imports-judge direction.
- Non-compensatory floors. The random-card test confirmed they cannot be bypassed.

The arrow that does not hold is **"the composite is the gate's regression signal"** (F1). Under D14
a candidate version has no rows at merge time, so a pre-merge gate cannot measure axes 1 and 2. Draw 2
must split that arrow in two:

- a **pre-merge gate** on what a diff can change: tests, schema, no-live, fitness, drill, and a
  pinned scorer;
- a **post-deploy comparison** of version-tagged cohorts over equal quota-day exposure, with
  intervals.

That split replaces one interface. It does not redesign the system. Round 2 should attack draw 2 plus
the fixes. Attacking today's code again would only rediscover F1–F4.

---

## FATAL

### F1. The regression gate grades the journal on the machine, not the change

Found by: all three (statistician SERIOUS #5, gamer FATAL #1/#2 and SERIOUS "all-time", systems
FATAL #1/#2). **Partly fixed at 10:09**: the baseline is now committed per tier in
`tools/ci_baseline.json`, and a missing baseline fails closed. What remains:

- **No window, no version.** `ci_gate._composite` calls `B.build()` (ci_gate.py:228). That grades all
  history in whatever journal sits on the machine. `EX-ANTE (code) + D14`: a candidate's axes 1–2 are
  undefined before it has run, so no diff can move 80% of the weight at merge time.
- **Data tier moves with data.** With k=3 and axis 1 = 0, the committed data baseline of 25.5 first
  reads lower at n = 27,523 scored (+173 rows, no code change): `v3_composite.py` →
  `first n that reads < 25.5: 27523`, and by hand 0.4·(round(3/27523·5000, 2)=0.54)/4·100 + 20 = 25.4.
  **On the VPS today:** COMPLETE+checks = 28,020 and k = 3, which gives per5000 0.54 and composite 25.4
  against the committed 25.5 (read-only census). An unchanged tree would therefore **BLOCK** there now.
  The composite was computed from the formula with axis 3 = 20 and axis 1 = 0, not by running `build()`
  on the VPS.
- **One "data" baseline, two machines.** The MacBook journal (115.7 MB, mtime 03:05) and the VPS
  journal (118.4 MB) differ. So do the ledgers: the VPS has `state/climb/submitted.jsonl` with
  mL516W9W 201, and the laptop has none. The curves differ too: 2,810 on the laptop and 6,538 on the
  VPS. After F2 is fixed, the VPS reads axis 1 = 1.0 and the laptop reads 0, because it has none of the
  4 submitted curves. That is a 40-point gap between two "data tier" runs of one tree.
- **Hermetic tier: axes 1–2 are constant 0.** Actions run 35813131506 printed
  `0 scored alphas`, `composite 20.0 vs committed 20.0`. The hermetic regression is therefore a
  fitness count under another name. It also disagrees with `check_fitness` about the same defect.
  Measured with one static fitness function broken:

  | check | held | floor | points |
  |---|---|---|---|
  | hermetic `check_fitness` (drill not run) | 5/6 | met, PASS | — |
  | hermetic composite (drill crashes) | 5/7 | unmet | 17.8, which BLOCKS |
  | data tier (drill runs) | 6/7 | met | 20.0, PASS |

  So one tree gets three different verdicts. `01_architecture.md` §2 says the same command gives the
  same verdict on a laptop, on the host and in Actions; this contradicts it.
- **No ratchet.** An improvement is never locked in unless someone runs `--record-baseline`, and
  nothing records why the line moved. A committed baseline of `{"hermetic": {"composite": 0}}` passes.
  `{"hermetic": {}}` raises an uncaught `KeyError` out of `gate()`, which gives an exit code but no
  verdict line. Measured in a scratch run.

**Fix.** Split per the Verdict:

- Pre-merge blocks only on diff-movable checks.
- The post-deploy comparison uses version-tagged cohorts at equal exposure. It passes when the
  interval of the difference excludes a fall, not when `now < base` on a number rounded to 0.1.
- The baseline records the scorer hash, FLOOR/WEIGHT, fitness count and input identity (host, bytes,
  row count, max `dateCreated`). Comparing baselines whose definitions differ is refused.

### F2. Axis 1 cannot pass for any version: the curve loader discards every real curve

Found by: all three. The finding is `EX-ANTE (code)` and was re-derived two ways.

- **Loader output.** `v1_curves.py` over `state/pnl_curves/`: every file is a `{date: cumulative}` dict,
  `formats {'dict:date': 2810}`. The loader at benchmark.py:518,
  `j if isinstance(j, list) else (j.get('pnl') or j.get('curve') or [])`, turns each one into `[]`,
  giving `{'insufficient': 2810}`. The `regime_not_one_sided` gate (:157) counts 'insufficient' as a
  FAIL.
- **What `build()` reports.** A full `build()` gives composite 25.5. Each of kqVbg1xP, vRk1J2jd and
  rK5RGeqa fails **only** `regime_not_one_sided`, with verdict `insufficient`. The card prints
  "3 of 3 fail a robustness gate", while the `gaps` text says such alphas are "not judged".
- **Correct parse, second way.** The 4 submitted curves were copied from the VPS read-only (the laptop
  has none of them). Sorted by date, they all read `consistent`: kqVbg1xP thirds [2.891, 0.944, 2.238],
  rK5RGeqa [1.826, 1.142, 2.032], vRk095rv, vRk1J2jd. On all 2,810 local curves:
  `consistent 2756 / mixed 14 / one-regime 40`. CONFOUND: curves are only fetched for pre-selected
  candidates, so this is not the gate's pass rate on arbitrary alphas.
- **The statistician's fix, as worded, is wrong.** He said to "parse curves through
  `dsr.daily_returns_from_curve`". That function returns DAILY RETURNS, and `regime_stability`
  differences its input again. Measured: kqVbg1xP then reads `one-regime`, and the 2,810 curves split
  1128 one-regime / 280 consistent / 1402 mixed. The fix must feed the sorted **cumulative** values, or
  change `regime_stability` to take returns and drop its own differencing. Either way it needs a
  shape assertion (see S3).

**Fix.**

1. Parse `{date: cum}` sorted, with None dropped.
2. Treat 'insufficient', for both regime and neighbourhood, as NOT JUDGED. Show it on the card, keep it
   out of the pass count, and let the floor read "not evaluable" rather than failing.
3. Add a test that runs `build()` on a fixture curve in the on-disk dict format.
4. Version the scorer, because this fix alone moves the composite +40 (25.5 → 65.5 wherever the
   curves exist). Under the current baseline that would read as pipeline progress.

### F3. Axis 2 measures the wrong quantity against its floor

Found by: statistician (SERIOUS ×2), gamer (SERIOUS), systems (SERIOUS). Merged here because each
part changes the number the floor is compared with.

- **Unit.** The floor is 4 submissions per quota day (D6). The value is `k / n_COMPLETE × 5000`
  (:225). `POST-HOC`: COMPLETE+checks alphas per ET creation day were 1,997, 3,375, 3,841, 3,718, 3,936,
  3,697, 1,460, 1,190, 2,529 and 1,607, with a median of 2,952; no day reaches 5,000. Measured with the
  real function:

  | case | per5000 | Wilson ×5000 |
  |---|---|---|
  | 1 POST on the 09-11 day (1,190 alphas) | 4.20 | [0.74, 23.72] |
  | 3 POSTs on a median day (2,952 alphas) | 5.08 | [1.73, 14.92] |
  | the real 09-22 day (1,607 alphas, 0 own submissions) | — | [0, 11.92] |
  | n = 0 | — | [0, 5000] |

  The first case meets the 4/day floor with one submission. The break-even is n ≤ 1,250 per POST. The
  upper limbs exceed what the platform allows: the submit cap is 4 per day.
- **Cohort.** :500 keeps only `status == "COMPLETE"`. The latest-row census gives
  `('COMPLETE', True) 27350`, `('WARNING', True) 5306`, and 5,306 of the 5,306 WARNING alphas sit in
  scored.jsonl. `grep` counts 5,310 raw WARNING lines. **vRk095rv, the first ACTIVE submission, is
  WARNING**, so it is in neither k nor n. The module's own denominator definition (docstring :23–24) is
  "a distinct alpha id carrying a check set", which includes WARNING. `POST-HOC`: counting
  COMPLETE+WARNING per day reaches 4,826–5,048 on 09-06 to 09-08. What sets WARNING is UNKNOWN.
- **Estimator.** The algebra of `wilson()` is right (see CONFIRMED). The problem is the estimand, not
  the interval.

**Fix.**

- Estimate per quota day: K POSTs over D whole ET quota days of exposure, with an interval that stays
  inside [0, 4]. The statistician's slot model, Clopper-Pearson on K/(4D) × 4, re-derived:

  | K | D | interval per day |
  |---|---|---|
  | 0 | 1 | [0, 2.41] |
  | 1 | 1 | [0.025, 3.22] |
  | 4 | 1 | [1.59, 4.00] |
  | 4 | 19 | [0.058, 0.517] |

  Its independence assumption is SPECULATION until D is large enough to test for overdispersion.
- Keep "per 5,000 scored" only as a secondary efficiency ratio, never compared with the floor.
- Define "scored" once, as the set of alphas that carry checks (COMPLETE ∪ WARNING). `build()` and
  `rung_report` should both use that one function.
- Count k by alpha id, deduplicated.

### F4. The composite cannot rank: flat above the floors, non-monotone below them

Found by: statistician (SERIOUS), gamer (SERIOUS), and the author's own §5.2/§5.3. All numbers below
were re-derived with the real `scorecard()` in `v3_composite.py`.

- **Flat above the floors.** 100,000 random PASS cards (axis 2 from 4 to 1,000, axis 3 from 0.8 to 1)
  give the composite set `{100.0}`. The module says the composite's "only job is to RANK versions"
  (:11), and it cannot rank any two versions that both pass.
- **Non-monotone below them** (n = 31,044):

  | subs | clean | composite |
  |---|---|---|
  | 1 | 1 | 61.6 |
  | 4 | 3 | 56.4 |
  | 2 | 1 | 43.2 |

  Hand check: 40·1 + 40·(0.16/4) + 20 = 61.6. The version with three times as many clean submissions
  ranks lower, and D9 would BLOCK it against a 1-submission baseline.
- **Junk beats abstention** (n = 27,350):

  | case | composite |
  |---|---|
  | nothing | 20.0 |
  | 1 bad | 21.8 |
  | 4 bad | 27.3 |
  | 1 good | 61.8 |
  | 4 good + 1 bad | 61.1 |

- **Axis 3 is constant 20 on this repo**, of today's 25.5; see S4.

**Fix.**

- Rank lexicographically, or on unclamped, uncertainty-aware quantities (the lower limit of the per-day
  rate).
- Score axis 1 as a count of clean submissions, with a bad POST costing more than it earns on axis 2.
- Leave out of the ranking any axis that is identical across the versions being compared.

---

## SERIOUS

### S1. Version attribution (D1/D14) breaks at the first stamped deploy

- **(i) The stamp breaks orphan recovery.** `EX-ANTE (code)`, confirmed with the real `R.match`:

  | plans | match |
  |---|---|
  | same stamp, two rounds | True |
  | **pre-stamp + stamped** | **False** |
  | **two different stamps** | **False** |
  | unstamped, two rounds | True |

  `recover_orphans.ROUND_KEYS = ("seed",)` treats `meta.pipeline_version`, which runner.py:106–107 now
  writes, as part of a construction's identity. Such rows are filed ORPHAN-UNMATCHED with alpha=None,
  which is the 2026-09-09 class again. 149 ORPHAN-UNMATCHED rows exist today. VPS: 0 of 205 plans and
  0 journal rows carry the stamp yet, so this has not fired. It fires on the first deploy of the
  stamped runner. (systems)
- **(ii) The judge and the CI files are inside the pipeline's version hash.** `deploy.file_map()`
  includes `forge/offline/benchmark.py`, `branch_drill.py`, `tools/ci_gate.py`, 57 files under `tests/`, **and
  `tools/ci_baseline.json` and `tools/ci_data_bound.json`**. Recording a baseline or re-running the
  classifier therefore mints a new pipeline version and empties the D14 cohort of the unchanged
  pipeline. The baseline/classification half is new: all three reviewers missed it because the files
  were added at 10:02/10:50. (systems for the judge and test files)
- **(iii) The on-target fallback id can never equal the manifest id.** The runner's fallback calls
  `DP.file_map(/opt/wq)` with PLAN keys `vps/auth_daemon.py` and `vps/forge_loop.sh`. `/opt/wq/vps`
  does not exist (checked read-only), while `/opt/wq/auth_daemon.py` and `/opt/wq/forge_loop.sh` do.
  So byte-identical code gets a different `+untracked` id. `DEPLOYED.json` is trusted over the bytes
  (runner.py:83–87), so a hand-rsync after the first deploy is stamped with a version that is not
  running. (systems)

**Fix.**

- Add `pipeline_version` (and `arm` review) to ROUND_KEYS, with a two-plan test.
- Hash only what the live loop imports: exclude tests, the judge and CI data files.
- Compute the fallback with the remote-path map.
- Stamp from the bytes loaded at process start, compared with DEPLOYED.json, and mark a mismatch
  explicitly.

### S2. `neighbourhood_stability` does not measure a neighbourhood

Found by: all three and author §5.4. `EX-ANTE (code)`: the key is (hypothesis, region, delay,
category), and no formula or one-setting comparison exists.

- **Peers are the whole hypothesis group.** `v5_neigh.py` gives kqVbg1xP 762 peers, vRk1J2jd 49 and
  rK5RGeqa 919. **Zero** of them have the same formula with exactly one setting changed. Over the whole
  journal, the only same-formula rows (88362eJz, blR6zw0M) differ in two settings (decay +
  neutralization).
- **The ratio flips on sign and scale.** With the real function: own 0.01 vs peers 1.5 gives stable;
  −1 vs −2 gives stable; −2 vs −1 gives stable; own 0.0 or None gives *fragile*, not insufficient; own
  2.0 gives stable against 1.00 and fragile against 0.99.
- **It does not discriminate.** `POST-HOC`: it labelled 34 of 34 qualified COMPLETE rows stable.
- **Typed groups read fragile.** `POST-HOC`, on 4 small typed groups (14, 9, 6 and 4 rows), the best
  row reads fragile: retained 0.44, −0.20, 0.121 and −0.145. Whether a typed alpha at the submit bar
  would read fragile is not measured.
- **Thin groups count as failures.** 35 of 198 groups have ≤ 3 rows, so any submission from one of
  them gets 'insufficient', which counts as FAIL.

**Fix.** Use the same normalised formula with exactly one of decay/neutralization/truncation changed.
Measure a difference in SE units, or the share of one-notch neighbours still clearing the platform
Sharpe bar, not a ratio. No proper neighbours means 'insufficient', which means not judged. Mark the
0.5 threshold as unmeasured.

### S3. `regime_stability` decides on endpoints and accepts any input shape

Found by: statistician. `EX-ANTE (algebra)`: a third's mean of first differences telescopes to
(end − start)/len.

- **One reset flips a third.** +1/day with a single reset reads `mixed [1.0, 1.0, −1.256]`.
- **'mixed' passes the gate.** Two near-flat thirds plus one losing third reads `mixed`, and the gate
  passes it, although the whole-curve Sharpe is −10.88 and the PnL is −672. The statistician's draw gave
  −10.90 and −1,464.8; the numbers differ by random draw and the verdict is the same.
- **No shape check.** Nothing checks whether the input is cumulative or daily; F2's daily-returns
  experiment above is the demonstration.

**Fix.** Judge each third against its own standard error (for example, the lower limit of the third's
Sharpe > 0), and do not let 'mixed' pass without a threshold. Assert a cumulative input, and reject
resets or jumps larger than N daily sd.

### S4. Axis 3 is a constant, and it hides a failed drill (confirmed live on Actions)

Found by: all three; the gamer rated it MINOR and the systems reviewer SERIOUS. **Settled SERIOUS**,
because it is observed, not constructed. Actions run 35813131506's scorecard step printed
`6 of 7 … hold`, `[NO] a real branch goes through the planner`, `branch drill: crashed`, and
`AXIS 3 GEARING FLOOR MET`, with composite 20.0. D8 requires the drill "every release".

- **Existence checks.** Fitness functions 3 and 4 check a substring (`"--ab" in runner`) and a file's
  existence (`tools/deploy.py`).
- **The import-cycle detector is blind.** In `cyc/`, `import forge.zb as B` plus a parenthesised
  multi-line `from forge import (za,)` gives `{'module_level': [], 'deferred': []}`. The detector sees
  neither.
- **DORA is displayed but never enters the axis value**, although D8 names it. This was missed by all
  three.
- The tier disagreement is in F1.

**Fix.** Make every fitness function and the drill blocking in their own right, or set the floor to
1.0. Use AST import analysis. Test `--ab` through argparse. Score DORA, or state in the spec that it
is display-only.

### S5. The window: local-midnight post cut, free-form flags, a silent version fallback

Found by: statistician (MINOR), gamer (SERIOUS) and systems (SERIOUS). **Settled SERIOUS**, because
each part changes a number on the card.

- **Timezone.** For `since=2026-09-22, until=2026-09-23`, rK5RGeqa is counted as a post in UTC and
  in New York and not counted in Asia/Ho_Chi_Minh; with `since=2026-09-23` the reverse holds. Measured
  under 3 TZ values. rK5RGeqa was POSTed 2026-09-22 17:23 UTC, which is 13:23 ET, so it belongs to the
  **09-22** quota day. The brief's "POSTed 2026-09-23" is the +07 calendar date.
- **Free-form window.** `since=2026-09-05T11:53, until=…11:54` gives n = 50, k = 1, per5000 = 100 and
  the axis-2 floor MET. Nothing enforces D5's whole quota day.
- **Silent version fallback.** `rows_of_version(rows, version='deadbeefdeadbeef')` grades all 27,350
  alphas under that name. With every row tagged and no version given, the label still reads
  "time-window (weak: no row carries a version)". The `gaps` list is hard-coded, and
  `test_the_scorecard_names_its_own_gaps` asserts the hard-coded strings, so it will stay green after
  the stamp makes them false.

**Fix.**

- Use one ET quota-day function (rung_report's) for both cuts, and grade only whole quota days.
- Refuse `--version` when no row carries it.
- Compute the attribution label and the gaps from counts of tagged, untagged, `unknown` and
  `+untracked` rows.

### S6. The hermetic tier's "covered instead by" is false, and classification can go stale silently

**Missed by all three**, because it postdates their review.

- **Coverage.** The gate prints "covered instead by: the DATA tier … (MacBook pre-push, VPS), which runs
  them all". Of the 167 deselected tests, 165 are in `tools/tests`, plus `test_submit_plan.py` whole.
  - The VPS deploy smoke runs `pytest forge/tests -x` only (deploy.py SMOKE).
  - `ci_gate.py` and both CI JSON files are not on the VPS (read-only `ls`).
  - Neither the dev repo nor the pushed repo has a pre-push hook: `.git/hooks` holds samples only,
    and there is no `core.hooksPath`.
  - So those 166 items run only when someone runs the data tier by hand.
- **Staleness.** `ci_classify.tests_hash()` hashes test files only, so a **code** change that turns a
  deselected test red leaves the hermetic tier green, with no staleness warning. When the hash does
  differ, staleness is appended to the summary as a WARNING, and `ok` stays `returncode == 0`
  (ci_gate.py:102). `EX-ANTE (code)`: not observed. Today's only red test is known and blocks through
  `check_known_red`.

**Fix.**

- Hash the code under test into the classification too, or re-classify on every data-tier run.
- Make staleness block.
- Install a real pre-push hook, or run the data tier on the VPS as part of deploy, and print only the
  coverage that actually exists.

### S7. `check_no_live` is a tripwire whose stated backstop is absent where credentials exist

Found by: gamer (SERIOUS) and systems (MINOR). **Settled SERIOUS**, because of RULE 1.

- **Bypasses.** A scratch fixture passes the check (`ok: True`) while containing:
  - `R.main(["--liv"])`
  - `"--" + "live"`
  - `LS.run(90, live=True)`
  - `assert R.main([... "--live"]) == 0`
  - `S.main(["--submit", ...])`
  - a root `conftest.py` that runs `forge/runner.py --live`
  - `.github/scripts/nightly.sh`

  The control line `R.main(["--live"])` IS caught.
- **Abbreviations.** None of runner, layered_sim or submit sets `allow_abbrev=False`, and each has
  exactly one option starting `--li`/`--su`. `argparse` parses `--liv` as `live=True` (measured on a
  mirror parser).
- **No backstop on the credentialed tiers.** The docstring's backstop is "a hosted runner holds no
  platform credential". The data tier runs where credentials exist: `state/wq_cookies.pkl` is on the
  laptop, and the VPS runs the live loop. `live=True` appears on 50 lines across 3 test files, each
  made safe only by its own monkeypatch. There is no conftest network guard.
- **Actual quota spend:** SUSPECTED. No current test was found that would spend.

**Fix.**

- Add a session conftest that makes the platform session raise under pytest.
- Set `allow_abbrev=False` on the three parsers.
- Scan `.sh` files and `conftest.py`, and look for `--submit` as well.

### S8. The judge's rules and instruments are editable by the judged commit

- **Unpinned constants.** `FLOOR`/`WEIGHT` are not pinned: `test_all_floors_met_is_the_only_way_to_pass`
  and `…cannot_exceed_100…` compute their expectations from `B.FLOOR`. Arithmetic: setting the axis-2
  floor to 0.5 gives 0.4·min(1, 0.55/0.5)·100 + 20 = 60.0. (gamer)
- **Borrowed instruments.** Axis 1 grades with the judged pipeline's own instruments. DSR comes from
  `scored.jsonl`, written by `forge/harvest.py` via `forge/dsr.py` with a pipeline-chosen `n_trials`.
  The correlation line falls back to `forge/submit.CORR_LINE_DEFAULT`. So a commit to `forge/dsr.py`,
  `harvest.py` or `submit.py` can raise axis 1 with no change in product, and version A's alphas may
  carry DSR computed by version B's harvest. `EX-ANTE (code)`; **missed by all three.** §1's separation
  holds in only one direction.

**Fix.** Pin the FLOOR/WEIGHT literals in a test, and record a scorer hash with the baseline. Give the
judge its own DSR computation from curves, with a judge-owned `n_trials` and fixed corr defaults.

### S9. Spec items the card names but does not score

- **D10 is absent from axis 1.** The axis-1 docstring cites D10, and the diagram prints "8 gates", but
  no `hypothesis_standard` gate is computed (`grep` finds none). Axis 1's 100% floor can therefore be
  met without D10. D19's 8/8 automatic submit has nothing to read from the card. **Missed by all
  three.**
- **D7 is not wired.** `build()` never passes `prev_window_rate` (:528), so 'sustainable' is False on
  every real card. That was confirmed in the scorecard log of Actions run 35813131506 and in my `build()`. D7 says the NEXT
  window, the code says the previous one, and the Wilson conjunct is redundant with k ≥ 2.
  (statistician, gamer)
- **Families are display-only.** (gamer)

**Fix.** Implement D10 or strike it from the axis and the diagram. Wire and redefine sustainability as
an interval statement per quota day across windows.

### S10. A card cannot say which code, data or definition produced it

Found by: systems. The card lacks generated_at, host, TZ, scorer hash, FLOOR/WEIGHT, fitness count,
input sizes and row counts, missing ledger files and curve coverage. Laptop and VPS verifiably
differ on:

| input | laptop | VPS |
|---|---|---|
| climb ledger | absent | present (mL516W9W) |
| all-time posts | 4 | 5 |
| cached curves | 2,810 | 6,538 |

`forge/` is untracked in the dev repo (`git ls-files forge` gives 0). The CI repository lives in a
session scratchpad (see M9).

**Fix.** Add a provenance block to every card and baseline.

---

## MINOR

- **M1.** At `k=0` the Wilson lower limb is a float residue > 0. For example, `wilson(0, 27350)[0]` is
  1.36e-20, and 14,375 values of n in 1..200,000 behave this way. At n = 11 the card prints
  `ci_excludes_zero: True` with zero submissions. Fix: return 0.0 when k == 0. (statistician)
- **M2.** Wilson is anti-conservative near p = 0. At k=3, n=31,044 the lower limb is 0.164 per 5,000
  against Clopper-Pearson's 0.0996. The docstring's "factor of ~3.4" is 8.645. The card prints a
  one-sided rule-of-three bound next to a two-sided Wilson limit, which gives two different "95%"
  upper bounds. Fix: one convention, on the per-day unit. (statistician)
- **M3.** The "61% zero days" caveat assumes 5,000 scored per day. With λ taken from measured
  exposure, P(0) is 0.67–0.81 depending on the exposure definition:
  - median 2,952 COMPLETE/day gives λ = 0.285 and P(0) = 0.752;
  - 4 POSTs over the 10 active days gives P(0) = 0.67;
  - 4 POSTs over 19 calendar days gives P(0) = 0.81.

  Fix: derive λ from the POST ledger and the quota-day exposure. (statistician)
- **M4.** "rK5RGeqa generated 09-10" (benchmark.py:239, test_benchmark.py:106, arch §3) is wrong: its
  row says `2026-09-11T01:32:06-04:00`, and 09-10 is vRk1J2jd. (statistician)
- **M5.** Stale counts in the docs:
  - "22 of 247": the two LLM files collect 37 tests and forge/tests collects 252.
  - "15 tests": test_benchmark.py has 20.
  - §4 says the drill is not implemented and the workflow is not in `.github/`; both exist.
  - The same "22 of 247" appears in the ci.yml and ci_gate docstrings.

  (gamer, systems)
- **M6.** `subs` is not deduplicated by alpha, and `wilson` raises when k > n. SUSPECTED only: on the
  VPS ledgers, each of the 5 accepted alphas has exactly one 201 and none overlap. Fix: dedupe and
  assert k ≤ n. (statistician)
- **M7.** A POST counts on http 201 whatever the later status. SUSPECTED only: on the VPS, all 5 ended
  ACTIVE. Fix: count by latest status ACTIVE. (gamer)
- **M8.** Quarantine growth is unguarded. `DATA_BOUND` entries and xfail/skip leave rc = 0, the
  executed-test count is never compared with a baseline, and there is no expiry. (gamer; the 10:09
  classification makes the data-bound list measured rather than hand-written, which narrows this.)
- **M9.** The CI repository's working copy is `scratchpad/wqrepo` under `/private/tmp`, which is
  session-scoped. The dev tree holds the same files **untracked**, and the two are synced by hand.
  Today they are identical (`cmp` on 10 files, and both have version bd323ecf690b29e5), but nothing
  checks that the version Actions passed is the version `deploy.py` ships. **Missed by all three.**
- **M10.** Peak RSS of `build()` is 1.44 GB (`/usr/bin/time -l`), and the test suite runs `build()` on
  the production journal. The ~6-month out-of-memory projection is a straight line through two points:
  SUSPECTED until measured at size. (systems)
- **M11.** Axis 2 credits only the planning version; the submitter's version gets no floor credit.
  This is a spec question for Khoa, not a bug. (systems)
- **M12.** POST-HOC: all 2,810 local curves and the 4 VPS curves jump from 2020-02-28 to 2020-04-01.
  The verdict uses telescoped means, so it is unaffected. Cause UNKNOWN. (statistician)

---

## Positively confirmed

These were verified by me:

- **`wilson()` is the Wilson score interval.** `wilson(3, 31044) × 5000` = [0.164, 1.421], which
  matches the test.
- **Non-compensation holds.** Read at benchmark.py:448–450 and pinned by
  `test_a_failed_floor_is_a_fail_however_high_the_composite`: any unmet floor gives FAIL.
- **The dedupe matches `rung_report`.** It is last row wins by alpha id (rung_report.py
  `latest[r["alpha"]] = r`), so §5.1's feared double count does not occur.
- **Import direction.** Nothing in `forge/`, `tools/`, `vps/`, `fingerprint.py` or `operators.py`
  imports the scorecard or the gate. `deploy.py` names it only in text.
- **The branch drill leaves no plan.** Plans are written only by `runner.main` (runner.py:520–521).
  The drill's `unlink` removes only a seed it proved free.
- **The 10:09 changes work as stated:**
  - A missing baseline fails.
  - `{}` fails.
  - The "staged" fitness function now tests the loader's behaviour, not whether a directory exists.
  - A known-red test blocks the hermetic tier: the latest Actions run 35815959688 was BLOCKED on
    `known-red`.
  - `ci_classify` refuses a run whose test files moved.
- **`check_no_live` catches the unexempted control line.**
- **The composite decomposition** 25.5 = 0 (axis 1) + 5.5 (axis 2) + 20 (axis 3) was
  reproduced by `build()` itself.

## Dropped or superseded, and why

- **Baseline gitignored, recorded on first run, `{}` passes** (gamer FATAL #1, statistician SERIOUS #5,
  systems FATAL #2, and arch §5.6). **Fixed at 10:09.** The baseline is now
  `tools/ci_baseline.json`, committed per tier, and a missing baseline or `{}` fails. Verified in a
  scratch run. What survives is in F1.
- **"Empty staged dirs flip the fitness function on CI"** (gamer M). **Fixed at 09:42.** Function 2
  now drops a broken leg into `staged/` in a temp copy and loads the library.
- **"The deploy starts a round between rsync and manifest"** (systems S5(b)). **Superseded by deploy v4
  (10:28)**, which stops the `wq-forge` and `wq-harvest` units before rsync and re-checks
  `round_in_flight`. It is not re-attacked here; deploy has its own audit (`audits/deploy.md`).
- **"tests/ (87 tests) never run by the gate"** (gamer). **Dropped.** `tests/` is not in the pushed
  repository (`ls wqrepo/tests` finds nothing) and not in the deploy PLAN, so it is not part of what the
  gate governs.
- **The neighbourhood selection simulation as evidence** (statistician). I re-derived the numbers (MC:
  P(fragile) 0.83 at SR 0.8 with 49 peers, and 0.95 at SR 1.2 with 762 peers). The data do not match
  the model: 34 of 34 real qualified rows read stable. The model (ρ = 0, equal true SR) does not
  describe the desk, so it is **dropped as evidence**. S2 stands on its definition defect alone.
- **"The 2 failing tests of 1,003"** (brief). **Stale.** The crash-mid-batch test was repaired (D23
  paragraph). The data arm now reads `1 failed, 1036 passed`; the remaining red test is D23's, kept red
  by Khoa's choice.
- **"31,044 scored alphas"** (brief). This is a historical count. Neither cohort the code computes
  equals it today: the laptop has 27,350 COMPLETE (+5,306 WARNING) and the VPS 28,020 (+5,326).

## Contradictions settled

| point | reviewers | ruling |
|---|---|---|
| Severity of the axis-3 clamp | gamer MINOR vs systems SERIOUS | SERIOUS: observed live on Actions (S4) |
| Severity of `check_no_live` | gamer SERIOUS vs systems MINOR | SERIOUS: the stated backstop is absent on the credentialed tier (S7) |
| How to parse curves | statistician's "use `daily_returns_from_curve`" | Wrong as worded; it double-differences and flips kqVbg1xP to one-regime. Feed cumulative values (F2) |
| "Regression can never fail on Actions" | statistician, gamer | True of the 08:59 code. At 10:09 it can fail, but only as a fitness count, since axes 1–2 are 0 (F1) |
| §5.6 framing | systems: "wrong as framed" | Moot after 10:09. The line now moves by a visible commit, and nothing ratchets it or records why (F1) |

## Missed by all three

1. `tools/ci_baseline.json` and `tools/ci_data_bound.json` are inside the pipeline version hash
   (S1-ii).
2. The hermetic tier's coverage claim is false, and classification staleness ignores code changes
   (S6).
3. The two tiers give different verdicts on one broken fitness function (F1).
4. The judge grades with the judged pipeline's DSR and correlation instruments (S8).
5. D10's 8 gates are absent from axis 1, and DORA is outside axis 3's value (S9, S4).
6. The CI repository lives in a session scratchpad, hand-synced to an untracked dev tree (M9).
7. On the VPS today, the committed data baseline would already block an unchanged tree (F1).
