# Draw-3 build audits

One section per module, appended by that module's adjudicator. Each section lists only defects the adjudicator reproduced.

## Draw-3 build audit: scoring (2026-09-23)

Adjudicator for `forge/offline/benchmark.py` and `forge/tests/test_benchmark.py` (sha256 `0c4164d9…`, the
bytes the builder delivered). Three audits were filed: spec, exec and assume. I kept a defect only after
reproducing it myself: I ran it on a scratch copy, read the line, or ran a read-only
`ssh -n -o BatchMode=yes`. I edited no code, simulated nothing and wrote nothing on the VPS.

The scratch files are in `/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad/adj_scoring/`:
`verify.py` (S1–S15), `mut.py` with `muts.json` and `muts2.json`, `cells.py`, `pool.py` and `dc.py`.

The suite on that copy gives 53 passed. The 2 branch-drill tests fail there only because the copy has no
`plans/`.

### What landed

| id | verdict | how I checked |
|---|---|---|
| A6 (composite, WEIGHT, UNPROVEN_CREDIT gone) | LANDED | read; `test_the_composite_and_its_constants_are_gone` |
| M6 (one alpha POSTed twice counts once) | LANDED | `_submissions` is keyed by alpha |
| D24 / A1 (ESTIMAND, exact test, MDR, calendar gap) | LANDED, with the caveats below | re-counted from the local journal (`cells.py`): 37 of 32,656, per-day counts 3,6,12,0,0,1,13,1,1,0, dispersion 11.43. The overlap-rule revert is killed by the suite. |
| S3-NL (SE judgement, negative-overall) | LANDED except the shape check | the SE-multiple-0 revert is killed. The reset/jump check is absent, and the builder disclosed that. |
| S9-NL + m1 (NEXT window, "not evaluable", proven-only) | LANDED except one sub-item | read, plus exec's mutations. The redundant interval conjunct is still there (see MINOR). |
| S4-NL (1)–(4) (AST imports, real `--ab` parser, real test use, axis-3 floor 1.0) | LANDED, with holes (see MINOR) | read, plus S12–S14 |
| A5 (clean = PROVEN) | PARTIAL | the core rule landed: the unproven-as-clean revert is killed (3 tests go red). "Make `load_standard` fail loudly" (round 2, line 275) did not land. |
| A3 (exposure from the deploy ledger) | PARTIAL | the core landed: the deploy-day-exclusion revert is killed. The exclusion is also applied to axis 1 (SERIOUS 1 below). |
| A4 (POST horizon, `now` required) | PARTIAL | landed in `build_from` and in compare's secondary reading, but not in the D25 rank (SERIOUS 3) |
| D25 / F4-NL (lexicographic rank) | PARTIAL | the order is implemented as written, but see SERIOUS 1–3 |
| A9 (DORA out of axis 3) | PARTIAL | the pre-merge half landed. `dora()` still counts `noop` rows, and "count a restore only when the version changes" is absent. |
| S10-NL (provenance, own-version neighbour pool) | PARTIAL | there is no `host` field. The pool is not bounded by time. No D10 verdict is frozen at submit time, and no card ledger exists. These were round 2's four bullets. |

### Surviving defects, ranked

**SERIOUS**

1. **Deploy-day exclusion removes version-stamped rows from axis 1 and from rank level 1**
   (`build_from` 1121-1122, `_grade` 1074; exec #1 and assume #2).
   - S3: a refuted submission was created 12:00 on V's deploy day. It reads `refuted_submitted` 0 when
     the ledger is passed and 1 without it, so supplying more data hides a refutation.
   - S4: V is deployed 09-20 and replaced 09-21, and it POSTed 2 refuted alphas. It reads 0 days,
     0 refuted and a MEASURED rate of 0.0. It outranks an exposure-unknown card (`rank_cmp` = -1).
   - Fix: grade axis 1, and so level 1, on every stamped row created before today. Use live days only
     for axis 2's rate. Treat `days == []` as unmeasured (`None`), not 0.0. Test with both inputs above.
2. **Rank level 1 rewards not measuring**, so the sentence "not measuring is never rewarded (A5)" in
   `rank_key` (953-954) is false. Spec #2 and exec #2.
   - S2: 3P plus x. With x unmeasured: `{proven 3, unproven 1}`, level 1 = 0. With x's two true
     neighbours measured as fragile: `{proven 3, refuted 1}`, level 1 = 1. `rank_cmp(unmeasured, measured)` = -1.
   - This follows from D25 as ticked, so it is a question for Khoa. Tick option (a): level 1 = refuted
     + unproven. Tick option (b): keep D25 as it is, delete the sentence and print the incentive on the card.
3. **The D25 rank ignores `post_horizon.final`** (`rank_levels` 935-946). Spec #1 and assume #3.
   - S1, the builder's own A/B fixture graded 09-19: A's rank is (0, -1.0) with its horizon final. B's
     is (0, -0.667) with its horizon open. `rank_cmp(B, A)` = 1. It is 0 once the horizon closes
     (graded 09-24).
   - So a version that is still live ranks below identical retired ones. This is round 2's A4 bias,
     moved into the rank.
   - Fix (a tick for Khoa): levels 1 and 2 are `None` while the horizon is open, or `rank_cmp` refuses
     to order a non-final card.
4. **No machine holds all of the scorer's inputs** (assume #1). Read-only checks:
   - The VPS has no `/opt/wq/state/deploys.jsonl`, so every version card there reads "exposure unknown".
   - The MacBook has 0 of 4 submitted alphas' curves. The VPS has 4 of 4 (6,538 curves against 2,810).
   - The Mac's journal ends 2026-09-22T16:04 ET, has 0 stamped rows, and is graded as if 09-22 were a
     whole day. The VPS journal has 740 rows stamped `ec6a5cd75d58fea2`.
   - Nothing compares `provenance.inputs.last_row_day` with the window.
   - Fix, in the module: flag or refuse a card when `last_row_day` is earlier than the window's last day.
   - Fix, outside the module: choose where the judge runs and move the ledger or the curves there.
5. **`test_the_scorecard_names_its_own_gaps` goes red at the next journal sync** (assume #5).
   - One stamped row in a scratch journal made it FAIL, and the VPS already holds 740 such rows.
   - The ESTIMAND comment's "0 of 32,662" is true only of the local copy.
   - Fix: use a fixture journal, and reword the comment so it names the copy and its cut time.
6. **`compare()` gives better/worse verdicts on raw pooling across cells.** Assume #4; the numbers are
   POST-HOC and I re-derived them.
   - All 37 events are USA/d1 (24,195 scored). The other cells have 0 of 8,461.
   - 2,276 rows have no IS_LADDER_SHARPE check, so they can never clear.
   - USA/d1's share of each day ranges from 0.32 to 0.94.
   - RULE 0 #6: a comparison that is not pooled within the confounder has no verdict yet. MECHANISM:
     UNKNOWN.
   - Fix now: print per-cell k/n and flag a mix difference.
   - Stratifying or restricting cells is a NEW estimand, so it needs Khoa's tick.

**MINOR** (each one reproduced)

- `dora()` still counts `noop` rows (848), against `tools/deploy.py`'s contract (S6). With 1 rollback
  and 7 noop rows it reads CFR 0.111 and 2.25 per week, and both band checks read ok. With the noop rows
  skipped it reads 0.5 and 0.5 per week, and both checks fail. Nothing but the display reads it.
- `load_standard` still returns `{}` on any exception (1239). After A5 that silently sets every proven
  count to 0.
- `_submission_reading`: without a ledger the result is always "censored", and `final_after_et` moves
  forward each day (S8). The "exposure unknown" branch at 1406 cannot be reached. Also, the censored note
  prints `until_exclusive` (09-19) as the "newest day"; the real one is 09-08, with a final date of 09-23
  (S9).
- `scorecard` counts an absent axis as a met floor (925). A card with no axis 3 reads PASS (S7), and the
  new test pins that at line 148.
- `rank_key`'s "monotone by construction" holds only at fixed exposure. On the default date card, P
  alone reads 3 days at 0.333, and P+P (the second P earlier) reads 18 days at 0.111, so
  `rank_cmp(P+P, P)` = 1 (S5).
- The neighbour pool is not bounded by `now`. Two rows created 09-25 flip an alpha from unproven to
  refuted on a card graded 09-20 (`pool.py`). Provenance has no host.
- The S9-NL conjunct `interval_excludes_zero` follows from `two_or_more_mechanisms`: no case with
  k ≥ 2 has a lower bound ≤ 0 (S11). The docstring still calls the three pieces "independent".
- `poisson_interval` underflows for k above about 745: k = 800 gives [742.7, 745.1], and k = 1500 gives
  [745.1, 745.1] (S10). That is out of reach at current volume.
- RULE 0 wording at 1292-1293: "per-alpha outcome is NOT independent across days" names one mechanism.
  Dispersion cannot tell day-level heterogeneity apart from within-day clustering. Write MECHANISM:
  UNKNOWN.
- The comment at 96 says `REGIME_SE_MULTIPLE = 2.0` is "as the round-2 fix states it". Round 2
  (line 518) states no number, so it is the builder's EX-ANTE convention.
- The ESTIMAND comment says 37 events. D24 (00_agreements:194) says 34, and the difference is not
  reconciled. The numerator refers to the mutable `BINDING` rather than to a list frozen inside ESTIMAND.
- Coverage: `import forge.x` binds `forge`, so a test that uses only `forge.y` covers `x` (S12). A
  module-level `if TYPE_CHECKING:` import is read as a WALL (S13). The `ast.Lambda` branch can never
  match, because an import statement cannot appear inside a lambda.
- `_ab_arm_is_real` has four holes:
  - `plan(ab=a.ab)` inside `if False:` passes (S14).
  - Code that `main()` runs before it parses its arguments runs inside the check (S14: a file was
    written).
  - A `@dataclass` in a runner with `from __future__ import annotations` (the real runner has that
    line) makes the check read "does not import" (`dc.py`). At a floor of 1.0 that fails axis 3.
  - Each call adds 2 entries to `sys.path`.
- `test_dora_is_reported_never_scored` monkeypatches `_dora_from_ledger`, which no longer exists (697).
- The `live_days` docstring says exposure stays unknown "until deploy.py writes it". For the
  `ec6a5cd75d58fea2` cohort that will never happen (deploy.py:125-128).
- Test gaps: 7 of 7 of my mutants survive the whole file. The control mutant was killed. The survivors:
  - `rate_test_p` with pi0 swapped, and `_power` with pi0 swapped; every test uses equal arms, and
    `rate_test_p(2,1000,10,5000)` = 1.0 is not pinned;
  - the next window counting "not refuted" instead of "proven";
  - the axis-1 floor changed to "none refuted";
  - `live_days` including today;
  - None treated as 0 at level 1, and at level 3.

**Open items for Khoa (RULE 2 ticks, not code defects):**
- the rank ignores the verdict, so a FAIL card can outrank a PASS one, while D2 reads "floors, then score";
- level 1 is a raw count, not a rate per exposure;
- `POST_HORIZON_DAYS = 14` (labelled POST-HOC);
- `REGIME_SE_MULTIPLE = 2.0`;
- D7's "held" means at least one proven submission in the next window;
- the exposure rules: deploy days are excluded, and a rollback restores the previous version;
- SERIOUS 2, 3 and 6 above.

**Dropped:** none of the three audits' defects failed to reproduce. Three changes to how the audits
stated things:
- The `@dataclass` claim holds only with `from __future__ import annotations`, which the real runner has.
- I downgraded the `dora` noop item from SERIOUS to MINOR, because no verdict or rank reads it.
- My own M6 mutant (removing `or a in first`) survived only because the result dict is keyed by alpha.
  That is not a gap.

## Draw-3 build audit: release (2026-09-23)

Adjudicator for `tools/deploy.py`, `tools/ci_publish.py`, `tools/tests/test_deploy.py` and
`tools/tests/test_ci_publish.py`. Three audits were filed: spec, exec and assume. I kept a defect only after
reproducing it myself: I read the line, ran it on a scratch copy of the shipped surface, or ran a read-only
`ssh -n -o BatchMode=yes` (`find | sha256sum`, `cat DEPLOYED.json`, `systemctl cat`, `systemctl is-active`).
I edited no code. I did not run `ci_publish.py`, `deploy.py push`, git commit or git push. I simulated
nothing and wrote nothing on the VPS.

The scratch files are in `/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad/adj/`:
`vps_sha.txt` and `DEPLOYED.json` (the target, read-only), `a10_check.py`, `e2e.py`, `m9_known_red.py`,
`mut.py` and `mut2.py`, and `tree/`, the scratch copy.

Both suites on that copy: `test_deploy.py` + `test_ci_publish.py` give 79 passed. After each mutation I
restored the files and checked them with `cmp` against the repository.

### What landed

| id | verdict | how I checked |
|---|---|---|
| A12 (the checkout is ours) | LANDED | Read `checkout_refusal` (HEAD == `.git/ci_publish_last`, empty porcelain, `rev-list HEAD..origin/main` == 0, fetch first). It runs before the data tier and again before the sync. The clean arm is a `git archive` export. `restore()` runs on any exit after the sync. The real CI checkout is at 1fce953 with no `ci_publish_last`, so the first run refuses until `--adopt-head`, as disclosed. Coverage holes are listed under MINOR. |
| A9, release half (`noop`) | LANDED | Mutation K1 (noop logged as deployed) is killed. The ledger row takes version and pipeline_version from `ctx["local"]`, the manifest that was compared and shipped. |
| A9, reader half | NOT LANDED (another owner, disclosed) | `benchmark.dora():848` keeps every row that has an outcome. Re-derived: 1 `rolled_back` row plus 7 `noop` rows give deploys 8, 2.0/week, CFR 0.125, and both `dora_checks` pass. Without the noop rows the result is `insufficient`, deploys 1. "Count a restore only when the version changes" is absent. |
| M9-NL, deploy gate | LANDED | `publish_record_for` runs before `remote_manifest` and before any rsync. The latest record for the exact full `version` decides. Mutation K2 (gate removed) is killed. `allow_abbrev=False` is set. |
| M9-NL, `.github` in SUBSET | LANDED | read (`ci_publish.py:48-50`) |
| M9-NL, the record ci_publish writes | PARTIAL | A record is written (mutation K5 is killed: 5 tests fail). The verdict it carries comes from the pre-A8 allowance (SERIOUS 2). |
| M9-NL, bullet 1 (D4 "block merge" recorded as not deliverable) | NOT LANDED (not in the builder's files) | `00_agreements.md` D4 still reads "Block merge"; I found no open-item entry (grep for 403, "deliverable", "branch protection"). |
| A10 (the pipeline id is the shipped loop surface) | PARTIAL | The manifest side landed: `manifest()` and `pipeline_version_of` share `_pipeline_id`, and the deny-list is as documented. Mutation K3 (`_root_map` forced to the source layout) is killed. The target side is BLOCKER 1, and the loop's runtime arguments are SERIOUS 3. |
| S8-NL, process half | LANDED, with the disclosed `--split-golden` deviation | Read. The golden card now pins `scorer_sha256` (`ci_gate.py:459-461`, 504), so every `benchmark.py` edit must move the golden, and every scorer publish has to go through `--split-golden`. The builder's guard `test_s8_a_scorer_change_that_leaves_the_golden_alone_is_allowed` therefore tests a state the real data tier cannot reach. That is an observation, not a defect. |

### Surviving defects, ranked

**BLOCKER**

1. **On a deploy target, `pipeline_version_of()` hashes files the push never shipped** (`deploy.py:173-203`,
   together with the rsync at `:750`, which has no `--delete`). All three audits found this; I reproduced it.
   - MEASURED, read-only, 2026-09-23. `/opt/wq` holds 619 files in the `_root_map` surface; `DEPLOYED.json`
     lists 551. Of those 551, 0 are missing and 0 have different bytes. The 68 extra files all pass
     `in_pipeline`:
     - 54 are `forge/{hypotheses,composites}/staged/*.yaml`;
     - 14 are in `tools/`: `*.pre_*` and `*.bak_*` copies, `test_climb.py`, `test_notify_system.py`,
       `push_fields.py`, `recover_harvest.py`, `rpm_search.py`, `unit_rate.py` and `uwatch.sh`.
   - Ids, computed with the builder's own `_pipeline_id`:
     - target as read = `a99174770a16008b`;
     - target restricted to the DEPLOYED keys = `dc0d9f363cbdab11`;
     - after the next push, the manifest would say `e7819520bfc7fc71` while the disk hashes to `6e5840d7bba229ad`.
   - End to end (`e2e.py`), the real `forge.runner.pipeline_version` on a `_stage`d target carrying the
     manifest `push()` writes:
     - clean target: `e7819520bfc7fc71`;
     - plus one `tools/*.pre_x`: `e7819520bfc7fc71+MISMATCH`;
     - plus one `staged/x.yaml`: `e7819520bfc7fc71+MISMATCH`.
   - Consequence, EX-ANTE (code). `benchmark.compare()` selects its cohort by equality (`:1104`), so it
     raises "no scored row carries pipeline_version". D14 has no cohort from the first deploy onward.
   - Removing the files once is not enough. `forge/llm/author.py:36-37` writes into `staged/`, and no
     push deletes anything. Why each of the other files is on the host: MECHANISM UNKNOWN.
   - The builder's test builds its target with `_stage()`, which cannot hold a stray file, so it cannot see this.

**SERIOUS**

2. **`ci_publish.data_tier()` ignores the A8 verdict and records `known-red-only` from the old allowance**
   (`ci_publish.py:81-102`). It reads the classification's `red` list and the 12-line-capped `details`.
   It never reads `r["known_red"]` (grep: no hit). `ci_gate.check_tests` attaches that verdict, and its
   docstring says it is "for tools/ci_publish.py".
   - Reproduced with the real `data_tier` and the real `known_red_verdict`; only `tier`, `classification`
     and the pytest result were stubbed (`m9_known_red.py`). Three cases:
     - the known test failing with "54 journalled warnings";
     - a new failure put into `red` by a re-classification;
     - pytest exiting with rc 2.

     In all three, data_tier says `known-red-only` and the gate's verdict says BLOCK. The control (the
     known test failing as recorded) is allowed by both.
   - `deploy.publish_record_for` accepts `known-red-only`, so A8's laundering routes produce deployable records.
   - POST-HOC (mtimes): `ci_gate.py` (14:29) and `ci_known_red.json` (14:16) postdate `ci_publish.py`
     (13:52). This is an integration gap between two owners.

3. **The loop's runtime arguments are outside the id** (A10's "loop drivers"). The live unit carries
   `Environment="FORGE_ARGS=--mode composites --order USA/d1,d1 --no-split --delays 1 --ab new"` and
   `N=300` (read-only `systemctl cat wq-forge`, identical to `vps/systemd_wq-forge.service`).
   `forge_loop.sh:60` passes both to `forge/runner.py`. No unit file is in PLAN.
   - EX-ANTE (code): a change to FORGE_ARGS changes the mode, the targeting and the arm, and the id stays
     the same, so D14 pools the two. This is the same class as round 2's "forge_loop.sh concurrency 9 → 3" row.
   - Round 2 named only `forge_loop.sh`, so closing this is a scope decision for Khoa.
   - Observed, outside this module: `wq-harvest` (active) runs `/opt/wq/tools/recover_harvest.py` from
     `/opt/wq/harvest_loop.sh:17`. That file does not exist in the dev tree. Why: MECHANISM UNKNOWN.

**MINOR**

4. **A9 reader half** (row above, other owner). DORA is display-only (`benchmark.py:1157-1158`), so the
   damage is limited to the card. I downgraded exec's SERIOUS for that reason.
5. **Unticked release mechanisms (RULE 2).** Each needs a tick from Khoa:
   - `--force-unpublished`, which no decision asked for. The refusal message advertises it, and nothing
     but `deploy.py` reads `unpublished_forced` (grep).
   - A `--no-push` record vouches for a deploy: `publish_record_for` never reads `pushed`, and
     `pushed:false` also means "already on origin".
   - `--split-golden`, `--adopt-head`, push-whenever-ahead, and `_root_map`. BLOCKER 1 comes from `_root_map`.
6. **The "tested == synced" identity covers only PLAN, not SUBSET** (`tree_identity`, `ci_publish.py:105-112`).
   An edit made during the data tier to `vps/probe.py`, `vps/*.sh`, a unit file, `.github/` or
   `docs/evalharness` is committed with no refusal. The data tier's no-live scan reads `vps/` and
   `.github` workflows (`ci_gate.py:233, 314`).
7. **Following the origin-ahead refusal loops forever** (`ci_publish.py:156-160`). EX-ANTE (code): "bring it
   into the dev tree first" does not move the checkout's HEAD, so `rev-list HEAD..origin/main` is unchanged
   and the next run prints the same refusal. After a hand commit that was also pushed, `reset --hard <last>`
   (the instruction the HEAD refusal gives) leads into the same loop. What works (exec's probe):
   `merge --ff-only origin/main`, then `--adopt-head`.
8. **Coverage holes**, each a mutation the suite does not kill:
   - M1: the second checkout check dropped. 23 passed.
   - K4: the first (fail-fast) checkout check dropped. 23 passed. Each check hides the other's absence;
     losing only the first costs a data-tier run and no safety.
   - M2: `push()`'s empty-surface refusal dropped. 56 passed.
   - M3: the `ci_*` rule applied at any depth under `tools/`. 56 passed. No such file exists today.
9. **`publish_record_for` crashes on one non-UTF-8 byte** in the records file. `UnicodeDecodeError` is not
   an `OSError`. Reproduced; `--force-unpublished` is blocked too. It fails closed, but the docstring says
   a bad line is skipped.
10. **Comments that say more than the code does.**
    - `PIPELINE_EXCLUDED` gives `tools/deploy.py` the reason "not what the shipped code does". But
      `runner.py:103-104` imports it to compute every row's stamp.
    - The importer list omits `ci_gate.py:366, 392`. No loop module imports either file, so the
      conclusion holds.
    - The DEPLOY_LOG contract says "one line per attempt". An interrupt after the swap rolls back and
      re-raises (`:764-765`), and no row is written. That gap is pre-existing (G3).
11. **The `gh run list` call comes before `record_publish`, and `sh()` does not catch `FileNotFoundError`.**
    Where gh is absent, a pushed publish leaves no record, and the next run recovers it. gh is installed here.
12. **S8 scope.** `SCORER` is `benchmark.py` and `ci_fixture.py`, which matches round 2's literal text.
    `benchmark.py` also imports `forge.harvest`, `forge.submit`, `fingerprint`, `forge.hypotheses`,
    `forge.standard` and `forge.probe` (`:57, 485, 626, 1236, 1256`). Either state the limit next to
    `SCORER` or widen it. This is a tick.

### Dropped or corrected

- The assume audit's `--adopt-head` finding: its phrase "reached through the documented path" overstates
  it. The hand-commit refusal names `reset --hard`, not adopt. Its proposed fix, "adopt only when LAST is
  absent", would break the only working recovery from origin-ahead (item 7). Replaced by: adopt only a HEAD
  that is equal to, or an ancestor of, `origin/main`. Kept inside item 5.
- The spec audit rated the target-id defect SERIOUS. I raised it to BLOCKER because it reproduced end to end.
- The assume audit said the push test for the empty surface was deleted from the deployed copy. I did not
  re-check that history. The gap itself reproduces (M2).
- Every other defect in the three audits reproduced as stated.

### Fixes still required

1. BLOCKER 1. On a deploy target, `pipeline_version_of` hashes exactly the keys `DEPLOYED.json` lists and
   verifies their bytes. Files on disk that are not in the manifest are reported as drift in a separate
   field and never enter the id.
   - Test: a target holding `tools/x.py.bak` and `forge/hypotheses/staged/x.yaml` must give a runner
     stamp with no `+MISMATCH`.
   - Deleting the stray files on the VPS is a write there, so it needs a tick.
2. `data_tier`:
   - `ok` and `known_red` come only from `r["known_red"]` (`ok`, `allowed`). Drop the `details`/`red` path.
   - Tests: more than 12 failures, a listed test failing differently, rc 2, and a test in the
     classification's `red` list that is not listed. Each must give verdict `red` and write no record.
3. Put the loop's runtime arguments in the identity. Either the runner stamps a hash of its argv and
   FORGE_ARGS/N beside `pipeline_version`, or the units are shipped and hashed. Khoa ticks which.
4. `benchmark.dora()`: skip `noop` rows, and count a restore only when the version changes. Benchmark owner.
5. Add tests:
   - a hand commit made during the data tier is refused and survives;
   - a refusal before the data tier runs;
   - `push()` with `pipeline_version` None is refused with no rsync;
   - `in_pipeline("tools/funnel/ci_x.py")` is True.
6. `publish_record_for`: read the file as bytes and decode each line with `errors="replace"`, or also
   catch `UnicodeDecodeError`.
7. The origin-ahead refusal names `git -C CI merge --ff-only origin/main`, then `--adopt-head <sha>`. Add a
   test that follows the printed text. `adopt_head` refuses a HEAD that is not contained in `origin/main`.
8. `tree_identity` covers the SUBSET file set (the same filter as the sync), or the docstring says
   "the deployable surface".
9. Correct the comments listed in item 10. Write the ledger row in a `finally` (outcome `interrupted`),
   or document the gap.
10. Write the record before the `gh` call, or wrap that call in `try/except OSError`.
11. Tick questions for Khoa:
    - `--force-unpublished`: keep, remove, or keep with a second confirmation;
    - may a `--no-push` record vouch for a deploy;
    - `--split-golden`, `--adopt-head`, push-whenever-ahead and `_root_map`;
    - the scope of `SCORER`;
    - D4 "block merge" is not deliverable on this plan. The docs owner records it.

## Draw-3 build audit: ci (2026-09-23)

Adjudicator for `tools/ci_gate.py`, `tools/ci_fixture.py`, `tools/ci_golden_card.json`,
`tools/tests/test_ci_gate.py` and `tools/ci_known_red.json`. The builder's bytes are the ones I checked:
benchmark.py sha256 `0c4164d9…` and ci_fixture.py `7f82f6cd…`, both equal to the golden's recorded
hashes. All five files are untracked in the dev repo; "committed" in their text means the CI checkout.
Three audits were filed (spec, exec, assume). I kept a defect only after reproducing it myself: I ran
it on a scratch copy, read the line, or ran a read-only `ssh -n -o BatchMode=yes`. I edited no code,
simulated nothing, wrote nothing on the VPS, and ran neither ci_publish nor ci_classify.

The scratch files are in `/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad/`:
`adj_ci/` (the copy), `adj_mut.py` (on-disk scorer edits, then a fresh-interpreter card and
`check_pinned_scorer`) and `adj_gate_mut.py` (reverts in ci_gate.py, then the suite). The suite on the
copy gives 46 passed. After every edit, each file was restored byte-identical (`cmp`).

### What landed

| id | verdict | how I checked |
|---|---|---|
| A7 (truth table) | PARTIAL | There are 12 cases. All 23 MUTANTS apply exactly once and each moves a decision (the suite asserts `count == 1`). The golden reproduces with 0 diffs on the copy, and also on python:3.13-slim 3.13.15 on aarch64 and x86_64. Not every decision is reached; see SERIOUS 3 and 4. |
| A8, gate side | LANDED | The real D23 node was run as the gate runs it. With CI=true: rc 1, 1 entry, counted 1, text "AssertionError: 20 journalled warnings…", verdict allows it. Without CI: the text is empty and the verdict blocks. |
| A8, publish side | NOT LANDED (disclosed) | ci_publish.py:81-91 still reads `classification()["red"]`, matches on node id alone, and takes the ids from the 12-line `details` (ci_gate.py:216-217). grep finds no call to `known_red_verdict`. See SERIOUS 2. |
| S6-NL | LANDED, one claim false | A stale classification blocks: reverting to "stale only warns" turns 1 test red. The new coverage text is false for the DATA_BOUND files (SERIOUS 6). Two of the claimed sub-behaviours have no test (SERIOUS 7). |
| S7-NL, gate half | PARTIAL | The AST scan covers both flags in every .py under forge/, tools/ and vps/ and in every workflow. Round 1's ".sh files and conftest.py" (architecture_round1.md:404) did not land and is not disclosed (SERIOUS 5). The scan is red on the real tree (SERIOUS 1). |
| S8-NL, gate half | LANDED with gaps | The diff prints before the write. Both hashes are in the card and are compared. The recorder refuses when both hashes moved. FLOOR, RANK_ORDER, the floor semantics and best-first are pinned as literals. The gaps are listed under MINOR. |

### Surviving defects, ranked

**SERIOUS**

1. **Shipping ci_gate.py by itself freezes publish and deploy.** This is a RULE 2 gate-5 conflict.
   - `check_no_live` on the copy flags exactly `forge/tests/test_runner.py:488` and
     `tools/tests/test_deploy.py:414`. The second is a regex test-data tuple and passes nothing.
   - The chain: ci_publish.py:96 `elif not r["ok"] and r.get("blocking"): ok = False` refuses the publish,
     and deploy.py:684-689 then refuses every push that has no publish record unless
     `--force-unpublished` is passed.
   - The builder disclosed the two offenders but did not trace the effect on deploy.
   - Fix: land the two owners' assembled-flag edits (`"--" + "submit"`), or exemptions Khoa has
     ticked, in the SAME publish as ci_gate.py.
2. **A8's allowance has no consumer, but the committed text says it is enforced.**
   - `ci_known_red.json` "what" says it is "The ONLY allowance a failing test has".
   - The KNOWN_RED comment (ci_gate.py:61-62) says the red list "is never an allowance".
   - In fact publish still allows on the classification's red list (see the table). All three of
     round 2's routes, and m5, stay open in the only path that deploys.
   - Fix: `ci_publish.data_tier` decides on `r["known_red"]["ok"]` and `["allowed"]`, and stops reading
     `classification()["red"]` and `details`. Until that lands, reword the JSON and the comment.
3. **The scorer's identity hash covers benchmark.py only.** Part of its decisions live in
   forge/submit.py (`corr_lines`, `quota_day`), in forge/hypotheses.py and in the copied leg YAML.
   - Measured on the copy: the edit `corr_lines` `("PROD_CORRELATION", "SELF_CORRELATION")` →
     `("PROD_CORRELATION", "PROD_CORRELATION")` gives 0 judgement diffs, no hash moves, and
     **`check_pinned_scorer` ok=True**. So the edit passes with no re-record.
   - Control: `CORR_LINE_DEFAULT` 0.7→0.75 is caught (5 diffs).
   - ci_publish's `SCORER` tuple and `golden_mixed` do not name submit.py either.
   - Fix: hash forge/submit.py, forge/hypotheses.py and fingerprint.py into the card, `SCORER` and
     `record_refusal`. Add cases for a SELF_CORRELATION row limit and for self-corr over the line, each
     with a MUTANTS entry.
4. **The truth table does not reach several scorer decisions, so the docstrings are false.** The
   docstrings claim "one case per decision" and "each inline threshold pinned by a case on either
   side" (ci_fixture.py:14, 24-26). Each of these on-disk edits gives **0 judgement diffs**; only the
   hash moves, so a re-record diff is one sha line:
   - binding `== "PASS"` → `!= "FAIL"`: a missing or PENDING check counts as a pass. This is the
     RULE 0 #5 class.
   - `alpha_status` checks unproven before refuted.
   - the self line is dropped.
   - an unknown rate is ranked as 0/day.
   - `covered >= 0.8` → 0.5.
   - the curve bound 300 → 400 (the cases sit only at 299 and 421).
   - `dora` window 28 → 7.

   Also missing from the card: `MDR_MAX_*` and `ESTIMAND["not_the_submission_count"]`.
   Fix: add a case and a MUTANTS entry for each item, or narrow the docstrings to "every decision round 2
   listed".
5. **S7-NL's round-1 scope is incomplete, and the builder did not disclose it.**
   - A probe tree put `--live` in each of: the root `conftest.py`, `tools/x.sh`,
     `.github/scripts/nightly.sh`, `"--submit --cap 4".split()`, a `%` template and a `.format` template.
     The scan flagged none of them; it flagged only the control line.
   - Fix: scan `*.sh` and every `conftest.py`, with exemptions Khoa has ticked for the vps/*.sh loop
     drivers, and read split/template strings token by token. Or list the omission as not addressed.
6. **The coverage claim is still false for the 37 DATA_BOUND tests.**
   - The tests are test_llm_author.py (22) and test_llm_formula.py (15).
   - They are `--ignore`d in EVERY tier (ci_gate.py:189-190), yet `covered_instead_by` names the
     ci_publish data tier, which runs the same `check_tests` and so skips them too.
   - What does run them: the VPS `wq-forge-tests.timer`. It is enabled, and `/opt/wq/wq-forge-tests.sh`
     runs `pytest forge/tests` with no ignores. `tests_last.json` reads "210 passed".
   - Fix: make `covered_instead_by` per entry, and pin that mapping in the test.
7. **Six claimed behaviours have no test that fails without them.** The job's hard limit requires one.
   Each revert below leaves 46 passed; the control revert (stale only warns) turns 1 test red:
   - an unverifiable classification counted as stale;
   - `check_tests` filling `known_red`;
   - the exemption keyed by the exact line (reverted to the path alone);
   - `known_red`'s `::` check;
   - the non-list `tests` check;
   - the empty `expected_failure` check.

   Fix: one test per behaviour.

**MINOR** (each one reproduced)

- `known_red()` raises AttributeError, not ValueError, on a non-dict entry. A probe with
  `{"tests": ["x::t"]}` made `known_red`, `known_red_verdict` and `check_known_red` all raise.
  Fix: `isinstance(t, dict)`.
- Two claims hold in the hermetic tier only:
  - In the data tier, `check_known_red` returns ok=True with an unparseable list (probe).
  - Verdict condition (d), "not stale", cannot fire in the data tier: `stale` is set only under
    `if hermetic:`.
- `case_dora` says "every band check is seen both ways". In the golden, deploys/week reads True in both
  ledgers, and time-to-restore appears once, as False.
- S8-NL gaps:
  - The diff is labelled "(committed)" but is taken against the working-tree file.
  - Deleting the hash keys puts the golden back on the never-refusing bootstrap path (line 502).
  - ESTIMAND and POST_HORIZON_DAYS are not pinned as literals in a test.
  - The one-commit rule does exist, in ci_publish.py:319-323.
- `_judgement` includes the constants. The REGIME_SE_MULTIPLE and SCORED_STATUS mutants also move the
  cases today (6 and 31 diffs), so no mutant escapes now; the gap is only robustness. Assert on the cases.
- Text errors:
  - The D23 node id is 81 characters, not 83 (27 + 2 + 52).
  - "The three parsers": `tools/climb_submit.py:241` also defines `--submit` (:243) and has no
    `allow_abbrev=False`.
  - The module docstring implies lint is in the gate. `CHECKS` has no lint check.
  - test_ci_gate.py:417 says "ci_gate.py is absent on the VPS". `/opt/wq/tools/ci_gate.py` is there
    (16,144 B, 12:19) and nothing runs it. `ci_known_red.json` is absent there.
- `.github/workflows/ci.yml:7-11, 57` (not the builder's file) still says "22 of the 247", "the VPS
  deploy smoke" and "blocks on REGRESSION (D9)". This is undisclosed.
- The builder added the notify_lint `NO_LIVE_EXEMPT` entry on its own authority, while the report calls
  exemptions Khoa's decision.
- The D23 text is a count over an unbounded glob, `state/layered/runs/*.jsonl` (test_layered.py:414).
  The local per-file counts are 2, 20, 46, 15 and 2. Whether the count moves when the journal is
  re-synced from the VPS is MECHANISM: UNKNOWN. The check fails closed.
- Latent: `code_version` hashes `staged/`, and ci_publish's rsync excludes it (EXCLUDE, :51). Both
  staged dirs are empty today.

**Observation:** the classification on the real tree is already stale. `tests_hash` went
`93e1569a…` → `7d4c10b7…` and `code_version` went `18295bbf…` → `3d930a48…`. The hermetic tier
therefore blocks on STALE until someone re-runs `tools/ci_classify.py`, which this job forbids.

**Dropped:** assume's SUSPECTED "the golden may not reproduce on Linux/3.13". It reproduces with 0
diffs on python:3.13-slim (3.13.15, Debian glibc), on aarch64 and on x86_64. The Actions ubuntu image
itself was not run.


## Draw-3 build audit: pipeline (2026-09-23)

Adjudicator for `forge/runner.py`, `forge/submit.py`, `tools/layered_sim.py`,
`forge/offline/recover_orphans.py`, their two tests and the three conftests. I audited the bytes the
builder delivered: sha256 `fd0d74d2abaa…` runner, `65091cf31267…` recover_orphans, `62d242bfd11a…`
test_runner and `ebb9595492c5…` conftest.

Three audits were filed: spec, exec and assume. I kept a defect only after reproducing it myself, by one of:
- reading the line;
- running it on a scratch copy;
- a read-only `ssh -n -o BatchMode=yes` (sha256sum, and `tar cf -` to stdout).

I edited no code, simulated nothing and wrote nothing on the VPS.

The scratch files are in `/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad/adj_pipeline/`:
- `remote_hashes.txt`: /opt/wq, read at 15:01 +07;
- `extra.json` and `remote_extra/`: the 68 remote-only files;
- `replica_*`: target-layout trees;
- `probes/`, `guardprobe/`.

Named suites, run in the repo (`forge/tests tools/tests`, the llm tests ignored, a dead proxy set as a
safety net): 1 failed, the known-red `test_layered.py::test_the_model_names_the_operator_the_platform_named`;
1166 passed. On the scratch copy, the builder's two test files give 32 passed.

### What landed

| id | verdict | how I checked |
|---|---|---|
| S1iii-NL (the bytes are always hashed with `deploy.pipeline_version_of`, and a mismatch is named) | LANDED as specified; its PURPOSE is not met on /opt/wq today (SERIOUS 1) | I restored /opt/wq's pre-change body in scratch and the test FAILS with `'e3b0c44298fc1c14+untracked' == 'c1051e000000000a+untracked'`, the builder's string. On a clean target-layout replica, the real runner and the real deploy stamp the bare manifest id `e7819520bfc7fc71`. Cost: 0.015–0.09 s per call and no subprocess, so the builder's cost worry does not arise. |
| A11 (a construction planned by two versions gets `ambiguous`) | LANDED | the revert FAILS with `'B_version' == 'ambiguous'`. It returns a copy, so the index is not mutated. benchmark.py:1104 and :1308 select a cohort by equality, so an `ambiguous` row is in no version's cohort. |
| S7-NL, parser half (`allow_abbrev=False`) | LANDED on the 3 named parsers (runner:492, submit:252, layered_sim:865) | I reverted each line separately and each gives `3 failed`. Every live caller spells its flags in full. |
| S7-NL, conftest half | LANDED, narrowed: function scope, `requests` only, and only a `str` method | removing the root and forge/tests copies gives `'ConnectionError' == 'RealPostFromTest'`. The three copies are byte-identical. |
| S7-NL, check_no_live half | not the builder's file (ci_gate.py) | the rewritten gate now flags the builder's own test (SERIOUS 2) |

### Surviving defects, ranked

**SERIOUS**

1. **After the next push, every live row on /opt/wq would be stamped `<id>+MISMATCH`, and D14's bare-id
   cohort would stay empty.** The runner code and deploy.py are both involved.
   - MEASURED (read-only): /opt/wq holds 619 shippable files. 68 of them are listed by no manifest, and all 68 pass `in_pipeline`:
     - 27 `forge/composites/staged/*.yaml`;
     - 27 `forge/hypotheses/staged/*.yaml`;
     - 14 `tools/` relics: `*.pre_*` and `*.bak_*`, `push_fields.py`, `recover_harvest.py`, `rpm_search.py`, `test_climb.py`, `test_notify_system.py`, `unit_rate.py`, `uwatch.sh`.
   - Derived two ways:
     - (a) With the local deploy rules, `_pipeline_id` gives `e7819520bfc7fc71` for the local ship map and `6e5840d7bba229ad` for remote overlaid with local. Removing the 68 files from the overlay gives `e7819520bfc7fc71` again.
     - (b) On replicas built with the real bytes and a real `DP.manifest()`, the real `runner.pipeline_version()` returns:
       - `e7819520bfc7fc71` with no extra file;
       - `…+MISMATCH` with all 68;
       - `…+MISMATCH` with ONE staged YAML;
       - `…+MISMATCH` with the 14 tools/ files alone.
   - EX-ANTE (code): push runs `rsync -a` with no `--delete` (deploy.py:750), and `to_delete` holds only new paths, for rollback (:721). So a push leaves these files in place. I have not observed it on a real push. SMOKE (:506-516) does not check the stamp.
   - The staged YAMLs cannot change what the planner loads: `hypotheses.py:217/229` glob `*.yaml` non-recursively, and `ci_publish.EXCLUDE` already drops `staged/`. So the id counts files the loop never reads.
   - Why the files are there: MECHANISM UNKNOWN.
   - No quota, planning or submit path reads the stamp.
   - Fix, outside the builder's files, and an owner/Khoa decision:
     - (a) have `in_pipeline` exclude `staged/`, and have the operator clear the 14 relics; or
     - (b) have the runner hash only the paths `DEPLOYED.json["hashes"]` names and report extras separately; or
     - (c) have push delete remote-only files, with a snapshot.

     Whichever is chosen, also add a post-push smoke assertion that `runner.pipeline_version('/opt/wq')` equals the manifest, and an integration test (MINOR 4).
2. **The builder's own test blocks CI.** At `forge/tests/test_runner.py:488`,
   `SU.main(["--submit", "--cap", "4"])` passes the flag as a literal.
   - `ci_gate.check_no_live()` run now returns `ok=False, blocking=True, details=['forge/tests/test_runner.py:488', 'tools/tests/test_deploy.py:414']`.
   - ci_gate.py was rewritten at 14:29, after test_runner.py at 13:57, so "check_no_live returns ok" is out of date.
   - Fix, verified in scratch: add `_SUBMIT = "--" + "submit"` beside `_LIVE` (line 431) and use it at line 488. The gate then lists only `tools/tests/test_deploy.py:414`, which is another owner's file, and the 7 parse tests still pass.

**MINOR** (every item reproduced)

3. The `+MISMATCH` and `+unverified` stamps drop the id of the bytes on disk (`on_disk`, runner.py:109-112), which is stored nowhere. Two different drifts get one label, and a row stamped during SERIOUS 1 can never be re-attributed. Fix: carry the id, e.g. `<claimed>+MISMATCH:<on_disk>`. This changes the five-value vocabulary, so the scorer's owner must agree.
4. `claimed = m.get("pipeline_version") or m["version"]` (runner.py:98) compares the whole-tree id with a pipeline id. On a byte-identical replica:
   - a version-only manifest gives `e4726594f240aa07+MISMATCH`;
   - `pipeline_version: null` gives the same.

   test_runner.py:369 certifies this impossible agreement. Every S1iii test fakes `pipeline_version_of` with `raising=False` (lines 367, 396, 416), and no test runs the runner against the real deploy. Fix: use only `pipeline_version`, so that a missing one means untracked. Drop `raising=False`. Add a runner-plus-real-`manifest()` test, including a target with one extra `staged/*.yaml`.
5. A manifest whose id is not a string now crashes the planner: `{"pipeline_version": 5}` raises TypeError at runner.py:112. The old body returned the value unchanged. A JSON list raises AttributeError, and so did the old body. Only a hand-edited manifest reaches this. Fix: `if not isinstance(claimed, str): claimed = None`.
6. runner.py:71-73 still says the bytes are hashed only "when there is none". Line 69's "stamped into every construction" is false on the `--plan` path (runner.py:531-533), which `vps/pow_run.sh:29`, `c11_run.sh:33` and `llm_formula_run.sh:44` use. That gap predates this change. Fix: reword the comment, and either stamp `--plan` constructions that carry no stamp or say that they are unstamped.
7. A11 keeps hits[0]'s round: the probe returns meta `{'seed': 202, 'pipeline_version': 'ambiguous'}`, and `ab_report.py:82` groups by `meta.seed`. The builder disclosed this. Separately, `match()` raises TypeError on an unhashable stamp (recover_orphans.py:92); only a non-runner plan can carry one. `benchmark.py:1263` counts `ambiguous` and suffixed rows as "tagged". Fix: blank the seed in the ambiguous branch, or have ab_report drop `AMBIGUOUS_VERSION`. Build the set from `json.dumps(v, sort_keys=True)`.
8. The POST guard is narrower than round 1's "session conftest". In a scratch pytest with only the guard, each of the following reached the network (`ConnectionError` on example.invalid):
   - a POST from a module-scoped fixture;
   - `Session().request(b"POST", …)`;
   - `Session.send(prepared)`.

   The tree has no current instance: grep finds no `prepare_request` and no `b"POST"` outside tests. The guard also masks `tools/tests/test_auto_submit.py:159-165`: with that file's socket guard broken, the test still passes. Fix: patch in `pytest_configure` or at `HTTPAdapter.send`, and normalise a bytes method. The auto_submit test's owner should make it assert the socket guard's own AssertionError.
9. Two more parsers accept abbreviated irreversible flags. They are outside this module and are the owners' to fix. `climb_submit.py:241` parses `--su`, `--sub` and `--subm` as `submit=True`. `auto_submit.py:580` parses `--i` as `live=True`. Both are in `deploy.LOOP_ENTRIES`, and ci_gate's docstring says only "the three parsers". Fix: `allow_abbrev=False` on both, with parse-only tests.

**Dropped:** assume's SPECULATION that the root conftest shadows modules on a bare `pytest` run. grep finds no top-level `import config|models|llm|run|context|pipeline` in tests/, cyberrisk/, eduharness/ or harness13. cyberrisk is a package. I found no instance, and I did not run it. Spec's SUSPECTED "leftover files on /opt/wq" is now measured, as SERIOUS 1.
