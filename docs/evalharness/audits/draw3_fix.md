# Draw-3 fix audits (adjudicators append one section each)

## Draw-3 fix audit: release (2026-09-23)

Adjudicator for `tools/deploy.py`, `tools/ci_publish.py`, `tools/tests/test_deploy.py` and
`tools/tests/test_ci_publish.py`. I audited deploy.py sha256 61605532, ci_publish.py 26d05649,
test_deploy.py 41defb87 and test_ci_publish.py ba3a5761. The repo still held those exact bytes when I
finished.

How I checked:
- Everything ran on a snapshot (`scratchpad/snap_release_adj3`) with an empty `state/`.
- An ssh/rsync guard was first on PATH, and its log stayed empty.
- I made no ssh contact of my own. I did not re-measure the /opt/wq figures (72 extras = 54 staged
  YAML + 4 `.pytest_cache` + 14 `tools/`). Three independent read-only captures already agree on them:
  the builder's, exec's and assume's.
- The pre-fix baseline was `scratchpad/rel/orig` (deploy.py f4902fee, ci_publish.py 143ecec6).

Test results:
- Both suites on the snapshot: 113 passed.
- The new test files against BOTH original files: 26 failed, 87 passed.

### What landed

- **BLOCKER 1, id rule: LANDED.** The id covers exactly the in_pipeline keys the manifest lists, re-read
  from disk, and a listed file that is missing hashes to `MISSING_ON_DISK`.
- **BLOCKER 1, "drift in a separate field": PARTIAL.** The drift is reported only by the manual
  `deploy.py status`. No row, manifest or stamp carries it.
- **SERIOUS 2 (data_tier): LANDED.** All 4 parametrized cases fail on the original.
- **FIX-5 (M1, K4, M2, M3): LANDED as tests.** These tests pass on the original by design, because the
  code was already right. That they kill the mutants is exec's result; I did not re-run it.
- **LANDED, each with a MINOR below:** FIX-6, FIX-7, FIX-8, the FIX-9 finally, FIX-10, the target
  ledger, and `_SUBMIT = "--" + "submit"` (test_deploy.py:431).
- **FIX-9 comments: PARTIAL.** One citation is wrong.
- **TICK items: unchanged.**
- **The target ledger was authorised by the builder's task.** The builder transcript is
  `wf_fea88979-883/agent-aed0e4fc056ad9369.jsonl`, first message (08:18Z). It says "The judge will run
  on the VPS, which has no deploy ledger: after write_manifest, push appends the same ledger row ...".
  So the spec auditor's RULE 2 suspicion is DROPPED as far as the builder is concerned. What remains
  open: no document records Khoa's decision that the judge runs on the VPS (draw3_build.md:68 lists it
  as a choice). The orchestrator must put that decision on file before the first push that uses this
  code.

### Surviving defects, ranked

**1. SERIOUS (reproduced): the target id cannot see unlisted files the planner loads.**

My probe (`scratchpad/adj3_probe_id.py`) runs the real PLAN, stage and manifest, then the real
`forge.hypotheses` loaders and `forge.runner.pipeline_version`, in a fresh interpreter.

| Case | Composites loaded | New deploy.py stamp | Original deploy.py stamp |
|---|---|---|---|
| Clean target | 94 | `6a6ccbe1baf7996c` | `6a6ccbe1baf7996c` |
| Hand-copied `forge/composites/zz_adj3_extra.yaml` | 95 | `6a6ccbe1baf7996c` (bare) | `+MISMATCH:112bf034df6a7ed6` |
| A composite dropped from the manifest but left on disk | 94 (it is still loaded) | `e7f424f697fbcea5` (bare) | `+MISMATCH` |

- The second case is what push leaves behind when a composite is removed in dev, because push has no
  `--delete`.
- NOT measured: whether the alphas produced differ.
- Today 0 of the 72 extras on /opt/wq sit where the non-recursive `glob('*.yaml')` reads.
- The wording of draw3_build item 1 ("never enter the id") produced this. The builder implemented that
  wording as written.

**2. SERIOUS (latent; the consequence was run): nothing reconciles a failed target-ledger append.**

- grep finds no reader of `target_ledger` outside deploy.py.
- I ran the snapshot's `benchmark.live_days` on two ledgers. Both hold a `deployed` row for version A on
  09-01; the first also holds a `deployed` row for version B on 09-10; now is 09-20.
  - Both rows present: A has 8 live days and B has 9.
  - B's row missing, as when its target append failed: A has 18 live days and B reads "exposure
    unknown".
- One lost append therefore gives the previous version's axis-2 rate every day that follows.

**3. MINOR (reproduced): a signal during the target append loses the local row.**

- `scratchpad/adj3_sig.py` sends the signal during the target append, after `_push` has restored the
  signal handlers:
  - SIGTERM: exit 143, 0 local rows.
  - SIGHUP: exit 129, 0 local rows.
  - SIGINT: 1 local row, target_ledger "FAILED: interrupted before the append completed".
- The window is new, up to 30 s connect plus 120 s timeout. It breaks FIX-9's one row per attempt.

**4. MINOR (reproduced by mutation): documented properties with no test.** Each of these mutants,
applied alone, still passes all 113 tests (`scratchpad/adj3_mutate.py`; every file was restored and
cmp-checked):
- `errors="ignore"` in place of `"replace"`. The test's byte `gr\xffen` still decodes to a word that
  does not vouch.
- tree_identity's `plan:` half dropped.
- `ctx["swapped"]` set after rsync. With this mutant, a Ctrl-C during rsync is NOT ROLLED BACK. No test
  interrupts rsync.
- `_record` catching `BaseException`, which swallows Ctrl-C.

**5. MINOR (run): `status` gives the wrong exit code and wording in three cases.**
- A corrupt DEPLOYED.json gives rc 0, "nothing to compare".
- A manifest with no pipeline_version gives rc 1 "MISMATCH", where the runner stamps `+untracked`.
- "the N file(s) it lists" counts every hash, not the in_pipeline subset the id covers.

**6. MINOR (read): `undo: null` has more than one meaning.** deploy.py:923-925 sets `ctx["undo"]` only
after `_undo` returns. `start_units` at :929 runs outside the try. So a rollback that raised and a new
version that is live after write_manifest both leave `undo` null.

**7. MINOR (run): ci_publish's origin-ahead advice dead-ends on a diverged checkout.** When HEAD is an
unpushed ci_publish commit (after `--no-push`), or origin was rewritten:
- the printed `merge --ff-only` fails. In a local git reproduction it exited 128, "Not possible to
  fast-forward";
- the printed `--adopt-head` then refuses with "not HEAD".

Also, adopt now needs origin to be reachable (exec P9). This fails closed, but it is not documented.

**8. MINOR (read): four comments or docstrings are wrong.**
- "forge/runner.py:103 imports this file": the import is at :118. (benchmark.py:901 has moved since, so
  I cannot tell whether it was ever right.)
- publish_record_for's "never make a record vouch" holds only because ci_publish writes vouching
  records only: it returns at ci_publish.py:348 before record_publish at :424.
- _synced's "cannot drift" holds only for unanchored single-name patterns.
- pipeline_version_of files `tools/recover_harvest.py` under "MECHANISM UNKNOWN". vps/harvest_loop.sh:9-17
  documents it: it was moved to /opt/wq/tools on 2026-08-16 and is run every 120 s by the wq-harvest
  unit (vps/systemd_wq-harvest.service).

**9. Builder claim (run): one BLOCKER-1 test passes on the original.**
`test_blocker1_a_manifest_file_whose_bytes_changed_moves_the_id` PASSES on the original deploy.py (5
failed, 1 passed). It is a guard against D10, not a fails-without-fix test.

### Dropped or reassigned

- **Assume's quiesce interrupt:** pre-existing, not a regression. The remote side after the client dies
  was not measured (MECHANISM UNKNOWN). Kept as an open item. The contract's "as a refusal" should
  become "units are not restarted".
- **print() raising EIO after a hangup:** SPECULATION, not reproduced. Dropped.
- **`dora()` not counting "interrupted":** belongs to the benchmark owner, and the builder disclosed it.

### Fixes still required (release NOT signed for push until 1 and 2 are closed)

1. **TICK for Khoa.** Unlisted files the loaders can reach are forge/hypotheses/*.yaml and
   forge/composites/*.yaml (non-recursive) and top-level *.py in forge/ and tools/. Options:
   - (a) stamp and status mark `+EXTRAS:<n>` for them;
   - (b) fold them into the id;
   - (c) a push `--delete` scoped to the two library directories. This deletes on the host.

   Now, whichever option is chosen:
   - state the blind spot in pipeline_version_of's docstring;
   - add a test that puts an unlisted top-level composite on a target replica and asserts the stamp is
     not the bare id.
2. **Reconcile the target ledger.** At the start of push() and in status:
   - re-append local rows whose `target_ledger` starts with FAILED, keyed by `started_at` so the
     re-append is idempotent;
   - or refuse to push while one is unreconciled.

   Test: the append fails on push 1 and works on push 2, and the target then holds both rows.
3. **Cover `_record` with the signal handlers.** Install `_on_signal` in push() so the handlers stay in
   place through `_record`. Test: SIGTERM during the append leaves one local row.
4. **Tests for the four mutants in item 4:**
   - the byte `gre\xffen`;
   - a `forge/hypotheses/staged/x.yaml` parameter in test_m9;
   - KeyboardInterrupt from the rsync call: the rollback runs and one row is written;
   - KeyboardInterrupt from the TARGET_LEDGER ssh call: it propagates, and a local row is written.
5. **status:**
   - an unusable manifest gives rc 1, "manifest unusable";
   - an absent claim prints "no claim";
   - print the in_pipeline count;
   - add tests for rc 0 and rc 2.
6. **undo:** set `ctx["undo"] = "rollback_raised"` before calling `_undo`, and state the new value in
   the DEPLOY_LOG text.
7. **Origin-ahead advice:** when `rev-list --count origin/main..HEAD` is greater than 0, print the
   `reset --hard origin/main` route instead. Document that adopt needs the network.
8. **Correct the item 8 texts.** Cite symbols, not line numbers, in files other owners edit.
9. **Relabel the bytes-changed test** in the builder's report as a D10 guard.

## Draw-3 fix audit: scoring (2026-09-23)

Adjudicator for `forge/offline/benchmark.py` (sha256 `922320194beb…`), `forge/tests/test_benchmark.py`
(`d8c92c09e762…`) and `forge/tests/test_standard.py` (`8e449f556991…`). When I finished, the repo still
held those exact bytes (checked with `cmp` against my snapshot). Three audits were filed: spec, exec and
assume. I kept a defect only after reproducing it myself.

How I checked:
- Everything ran on a snapshot, `scratchpad/snap_scoring_adj`. It has a private copy of `state/`, and
  `fetched` is symlinked. My scripts:
  - `adjv.py` and `adjv1.py`: the reproductions V1–V14;
  - `adjmut.py`: makes one edit, runs the test file that owns it, restores the file, and checks it with
    `cmp` against `_pristine/`. Every run ended "restored: all cmp-equal".
- The two scoring test files give 107 passed. `tools/tests/test_ci_gate.py` gives 72 passed on the same
  quiet snapshot.
- One read-only VPS read, `scratchpad/vps_count.py`. It was fed on stdin to
  `ssh -o BatchMode=yes root@160.25.88.163 'python3 -'`. That call could not use `-n`, because the script
  arrives on stdin. The script only opens the journal for reading and prints counts.
- I simulated nothing, wrote nothing on the VPS, and wrote nothing in the repo except this section.

### What landed (a revert of each is killed unless noted)

| item | verdict | how I checked |
|---|---|---|
| SERIOUS 1 | LANDED | Grading axis 1 on live days only is killed by `test_a_refutation_on_a_deploy_day_…`. A rate of 0.0 on 0 days is killed by `test_a_version_live_for_no_whole_day_…`. The rate-input half has no test (defect 3). |
| SERIOUS 4, cut-day exclusion | LANDED, HALF | `if False:` on the cut is killed by `test_the_scorecard_names_its_own_gaps`. The other half is defect 1 below. |
| SERIOUS 5 | LANDED | The fixture journal is in place. The VPS count, read now: 1,796 ids stamped, all with the one value `ec6a5cd75d58fea2`. The comment's 1,198 was the ~04:30 ET read, and the count grows. |
| SERIOUS 6, display half | LANDED | `"differs": False` is killed. The real code matches the closed form on unequal arms (26.061994), gives 0.0 for an identical mix, and flags disjoint cells (stat 200). |
| dora noop, dora restore, load_standard fail-loud, absent axis, pool bounded by `now`, named thresholds | LANDED | Each revert is killed. Control: DSR 0.95 → 0.50 is killed. |
| log-space Poisson, coverage walker, AST `--ab` check, frozen ESTIMAND literal, A2 `--compare`/`--record`/host, computed caveat, the 7 earlier mutants, wording items | LANDED | From exec's mutation run (77 of 94 killed). I did not re-run all of these myself. |
| TICK behaviour (D26–D29) | unchanged, as instructed | read |

### Dropped or resolved

- **Spec's SERIOUS (6 ci_gate MUTANTS lose their target text): RESOLVED by the ci owner.**
  - At 16:24, `tools/tests/test_ci_gate.py` retargeted those mutants to the new text: `DSR_MIN = 0.95`,
    `NEIGHBOUR_RETENTION_MIN = 0.5`, `NEIGHBOURS_MIN = 2`, `CURVE_POINTS_MIN = 300`,
    `CORR_UNDER_LINE = operator.lt`, and the new `unmet = [...]` line.
  - At 16:27, `tools/ci_golden_card.json` was re-recorded with `scorer_sha256` `922320194beb…`.
  - The file gives 72 passed on the quiet snapshot.
  - The process defect stands: the scoring report did not name this cross-module effect.
- **Exec's "7 failures in test_ci_gate.py"** no longer reproduces. It had the same cause, which is now fixed.

### Surviving defects, ranked

**SERIOUS**

1. **The other half of SERIOUS 4: finality is judged against `now`, never against the data's cut.**
   Three judgements never read `data_through`:
   - `post_horizon.final` (`now >= final_at`);
   - `_held_next` (`if now < horizon_final_at(nxt[-1])`);
   - `_submission_reading`'s "final".

   Reproductions:
   - `adjv1.py`: the window is 09-10..09-11. Alpha b was created 09-12 and POSTed 09-17. The data was cut
     09-15 12:00, and the card was graded at 09-30. With the POST history as it stood at the cut, the card
     reads `held_in_next_window` False ("no proven clean submission in the next window 2026-09-12..09-13")
     and horizon final True. With the full history it reads held True.
   - V1b: data cut 09-12, graded 10-30, and the card reads final True.

   The builder's report says the cut day is excluded from "the next-window judgement". That is true for
   the rows, not for the POST horizon.

   This is latent today: no card is mis-graded now. Exec found the Mac and VPS POST logs identical. D27
   (ticked) will make `final` a rank input, so this becomes a rank defect when D27 lands.

**MINOR**

2. **SERIOUS 4 is PARTIAL: `provenance.inputs.last_row_day` is never compared with the window.** V11: rows
   run to 09-12 and `data_through` is 09-20. The card reads a rate of 2/10 = 0.2 over 09-10..09-19, and
   `coverage_note` says only that 09-20 is excluded.
3. **Test gaps: five mutants survive the whole suite (`adjmut.py`), although the real code is correct on
   these inputs.**
   - S1f: the rate numerator is not filtered to live days. The real code gives 1 over 12 days, with
     `submissions_outside_exposure` 1.
   - S6c: the chi-square's expected count is `col/2`, which ignores arm size.
   - S4g: compare()'s secondary reading drops `data_through`.
   - S6g: cells present in only one arm are dropped.
   - EST: compare() calls `clears_every_binding_check(r)` with the default list.

   On EST: `names=BINDING` is bound when the function is defined, so monkeypatching `B.BINDING` never
   moves axis 1. V6: the default call returns True, and a call with an explicit `B.BINDING` returns False.
   The test's last line is therefore a tautology, and the report's claim that the monkeypatch "moves axis
   1's gate" is false.
4. **test_standard.py: all 5 of my independent mutants of `forge/standard.py` survive.** The mutants: the
   regime check accepts a superset, the combiner check accepts an intersection, counterparty matching drops
   `.lower()`, the label check matches a substring instead of a prefix, and one leg is allowed. The
   builder's "12 of 12 killed" does not generalise.
5. **`load_inputs` calls `stat()` on the journal unconditionally.** A missing journal raises
   FileNotFoundError. The CI step `python forge/offline/benchmark.py || true` (`ci.yml:72`) runs where the
   journal is untracked (`git ls-files`: 0), so it now crashes, and `|| true` hides the crash.
6. **`render()` wording and window fields contradict the card's own data.**
   - A card whose exposure is known with 0 whole days prints "no rate (exposure unknown)" and "from None"
     (V2).
   - A card whose exposure is unknown prints "window effective: rate on 13 day(s)" (V3).
   - No test pins this text: a mutant of the string survives.
7. **`record_card` writes `Infinity`.** Steady-curve regime thirds produce it, and a strict JSON parse of
   the line fails (V5). There is also no guard for a missing trailing newline.
8. **`dora()` does not count `interrupted` or `units_down` as failures.** The ledger
   [deployed, interrupted, units_down, deployed] reads CFR 0.0, and both band checks read ok (V8).
   `tools/deploy.py:651-653` flags this to this reader's owner. DORA is display-only (A9).
9. **The printed tick status is stale.**
   - `verdict_text` calls the within-cell comparison "Khoa's tick", but D28 is ticked
     (`00_agreements.md:214`).
   - `open_ticks` omits D29 (`:222`) and D7's "held" item (7 items, none about D7).
   - "measuring them could only move it down" is false for the rank: an alpha measured as PROVEN raises
     level 2.
10. **compare(): when the mix is flagged, the JSON and the text disagree.** The JSON `verdict` keeps its
    better/worse/indistinguishable label, while `verdict_text` says there is no verdict. `render_compare`
    prints neither `min_expected` nor `cm['note']` (V9).

    POST-HOC: the flag fired on 2 of 2 adjacent 3-day DATE windows of the Mac copy (p = 0 and 1.25e-39).
    Whether version arms differ that much is NOT established.
11. **Text that claims more than the code or the evidence supports.**
    - cell_mix: "confounded exactly when the arms weight the cells differently". A mix difference biases
      the pooled rate only when the per-cell rates also differ.
    - compare: "too optimistic whichever holds". No experiment supports this (RULE 0 #3/#4).
    - Module docstring: "created before the last whole day". The code grades rows created on whole days in
      [since, last).
    - load_standard: "names the file". The duplicate-id error (`hypotheses.py:220`) names no file.
    - ESTIMAND comment: "27,890" names no copy. I re-derived it now on the VPS as COMPLETE rows created
      before 2026-09-22 23:35 ET, so the comment should say VPS.
    - The dispersion figure includes 09-22, a day the scorer now excludes.
12. **The `pipeline_version` gap clears on any truthy stamp.** That includes `unknown`, `+untracked` and
    `+MISMATCH` (`runner.py:64-68`), and it clears with a single version. The VPS now holds one value, so
    compare() cannot run, and the card is silent about that.
13. **Structural checks: holes found only with adversarial input** (the real tree passes).
    - `_ab_arm_is_real` accepts a parse by a different parser, a rebound namespace, and a call after
      `if True: return` (V13).
    - A home-made `TYPE_CHECKING = True` makes a module-level edge read as "deferred" (V14).
    - `structural_families` calls `sys.path.insert` on every call (line 622).
14. **Re-grading is not stable.** Only the neighbour pool is bounded by `now`. scored, corr, curves and the
    live hypothesis library are not. Round 2's S10-NL bullet "freeze a D10 verdict per alpha at submit
    time" did not land, and the builder does not claim it.
15. **The check named "every forge module has a test" covers only top-level modules.** At 1.0 it globs 22
    top-level modules and leaves 19 under `forge/llm` and `forge/offline` outside. It is a blocking ci_gate
    check. The orchestrator must confirm that the builder's task authorised raising it from 0.8 to 1.0; I
    cannot see that task text.

**SUSPECTED, or outside this module**
- D30 (ticked) will hash argv into the row stamp. `live_days` joins on ledger stamp == row stamp, so
  unless that join is decided together with D30, every version card would lose its rate.
- An HTTP 201 counts as a submission (this predates draw 3). All 4 of 4 were later ACTIVE, so there is no
  impact today.
- `runner.py:88` and `deploy.py:142` cite benchmark.py line numbers that have moved.

### Open decisions (not code defects)

D26–D29 are ticked (`00_agreements.md:203-224`), and the scorer implements none of them. Its behaviour was
left unchanged under the TICK instruction, so it is out of contract with four ticked decisions until a draw
implements them. Implementing D27 turns defect 1 into a rank defect.

### Fixes still required (scoring NOT signed until 1 and 3 are closed)

1. Set `seen_until = min(now, data_through)` and use it for `post_horizon.final`, `_held_next` (return
   "not evaluable" while `horizon_final_at(nxt[-1]) > seen_until`) and `_submission_reading`. Test: a cut
   far before `now` gives final False and held "not evaluable".
2. Add `window.coverage_gap` when `last_row_day` < `until_exclusive` − 1 day, and print it.
3. Change the default to `names=None`, read as BINDING at call time. Assert through `axis1_product`. Add
   tests for S1f, S6c (an unequal-arm 2x2), S4g and S6g.
4. Add the 5 test_standard.py cases.
5. Journal missing → `data_through` None, plus a gap line and a test.
6. Render the rate wording from `quota_days` (None vs 0), and set `rate_days`, `rate_first_day` and
   `rate_last_day` to None when exposure is unknown.
7. Map ±inf to None or a string before `json.dumps(..., allow_nan=False)`, and add a newline guard.
8. Add `interrupted` and `units_down` to dora's failure set, citing `deploy.py:646-653`.
9. Update the tick texts: D28 and D29 recorded, not implemented; add a D7 item.
10. Set `verdict_withheld` when the mix is flagged (until D28), and print `min_expected` and the note.
11. Apply the six wording fixes under 11.
12. Count distinct plain stamps, with a gap for 0 and a gap for 1.
13. Document items 13–15 as limits, or close them.

## Draw-3 fix audit: pipeline (2026-09-23)

Adjudicator for the ten module files. I audited these bytes (sha256 prefix): runner.py ec58c7b7,
recover_orphans.py e8474adf, test_runner.py f0db52bf, test_recover_orphans.py cb7cdd1a, the three
conftests f5884d23 (byte-identical), climb_submit.py 25bee75a, auto_submit.py ef42a4c8 and
test_auto_submit.py 87ce9782. Context files: deploy.py 61605532 and benchmark.py 92232019. The repo still
held all of them when I finished.

How I checked:
- Snapshot `scratchpad/snap_pipeline_adj4` (no state/, fetched/ or .git). Every run used a dead proxy,
  127.0.0.1:9. The pre-task baseline is `scratchpad/pe_pipeline/orig`.
- Target-layout replica `scratchpad/adj4_target`, built with the real `deploy.file_map` over the
  snapshot: 556 files, no vps/, forge_loop.sh at the root, no root conftest.
- One read-only ssh call (`-n -o BatchMode=yes`: ls, grep -c, sha256sum). No write, no sim.
- Every mutated file was restored and then cmp-checked against the repo.

Test results:
- The named files (test_runner, test_recover_orphans, test_auto_submit): 115 passed on the current
  bytes and 97 on the pre-task bytes. This re-derives the builder's figures.
- Each mutation applied alone, run on the named files:

| Mutation | Result |
|---|---|
| MINOR 3 reverted | 2 failed |
| MINOR 4: `m.get("pipeline_version") or m.get("version")` | 5 failed |
| MINOR 5: the isinstance line removed | 3 failed |
| MINOR 7: the seed update removed | 3 failed |
| MINOR 9: allow_abbrev removed, climb_submit / auto_submit | 4 failed / 3 failed |
| SERIOUS 2: the literal put back | 1 failed |
| All three conftests reverted to pre-task | 5 failed (exec measured 4 on its selection) |

### What landed

| Item | Verdict |
|---|---|
| SERIOUS 2 | LANDED |
| MINOR 3 | LANDED in code. Its condition, the scorer owner's agreement, is NOT on file. No reader parses the suffix (grep over forge, tools, harness, harness13 and vps, tests excluded). benchmark selects cohorts by equality (build_from cohort, compare()). The scoring section's item 12 already deals with suffixed stamps in its `tagged` count. |
| MINOR 4 | LANDED |
| MINOR 5 | LANDED (RecursionError residual, item 6 below) |
| MINOR 6 | LANDED as a comment; behaviour unchanged (TICK). Every citation checked. |
| MINOR 7 | PARTIAL. The ambiguous branch is fixed. One version with several seeds still returns hits[0] (test_recover_orphans.py:149 pins it). The builder disclosed this, but the file does not record it. |
| MINOR 8 | LANDED. Its normalisation is untested (item 3 below). |
| MINOR 9 | LANDED |

### Surviving defects, ranked

**1. BLOCKER (reproduced): the new test fails on the deploy target.** The test is
`test_the_stamp_agrees_with_the_real_deploy_manifest_on_a_source_tree`.
- On `adj4_target`, `pytest forge/tests/test_runner.py forge/tests/test_recover_orphans.py`:
  - current files: 1 failed, 48 passed, 1 skipped (AssertionError at test_runner.py:470,
    `vps/forge_loop.sh` missing);
  - pre-task files: 31 passed, 1 skipped.
- /opt/wq, read now over ssh:
  - no vps/ directory;
  - forge_loop.sh and auth_daemon.py sit at the root;
  - no root conftest;
  - the test is not yet shipped (grep -c 0).
- deploy.py SMOKE runs `pytest forge/tests -q --no-header -x` on the target. `_smoke_ok` needs rc 0, and
  push then prints "smoke FAILED ... rolling back". So every push that carries this file would roll back.
  That last step is an EX-ANTE code read; I have not seen it on a real push.

**2. SERIOUS (reproduced): runner.py's value table says more than the stamp checks.** This crosses owners.
The behaviour's root is the release section's item 1, which is a TICK.
- Probe `scratchpad/adj4_stamp_probe.py`: the manifest is built from the source snapshot and written into
  the target replica.
  - Clean replica: `6a6ccbe1baf7996c`.
  - An unlisted copy of a composite at forge/composites/zz_adj4_extra.yaml, a path that hypotheses.py's
    `glob("*.yaml")` reads: still the bare `6a6ccbe1baf7996c`. surface_extras() names the file.
  - A hand edit to runner.py: `+MISMATCH:a97de5fde1868d76`.
- This is the same id the release adjudicator's probe produced.
- runner.py:77-92 still says the bytes on disk are "ALWAYS hashed" and that `<id>` means the "bytes on disk
  agree". It also still gives SERIOUS 1's 68 files as a MISMATCH case. The comment was written at 15:24,
  before deploy.py's 15:42 change.

**3. MINOR (reproduced by mutation): the guard's normalisation is untested.**
- I applied three mutants to all three conftests, each alone:
  - drop `.upper()`;
  - drop `.strip()`;
  - drop the bytes branch.
- Each still gave 69 passed on the two guard tests plus test_auto_submit.py.
- A hand-built PreparedRequest sent with Session.send (`scratchpad/adj4_guardprobe.py`):
  - the current guard refuses 'post', b'POST' and 'POST '.
  - the no-upper mutant lets 'post' out (ProxyError).
  - the no-bytes mutant lets b'POST' out (ProxyError).

**4. MINOR (reproduced): the ab_report test is not hermetic.** The test
`test_ab_report_keeps_an_ambiguous_row_out_of_every_round` reads ROOT/state/forge/corr.jsonl and
submitted.jsonl (ab_report.py:71-77).
- With one `{"prod": 0.3}` row in the snapshot's corr.jsonl: 1 failed, KeyError 'alpha' at ab_report.py:74.
- This test also runs in the `-x` smoke.

**5. MINOR (read): stale or overbroad text.**
- runner.py:88 cites benchmark.py:1104 and :1308. Today :1104 is `for m in sorted(graph.get(n, ()))` and
  :1308 is blank. The equality selections are at :1455 and :1766.
- recover_orphans.py:31 still says the runner stamps "every construction".
- recover_orphans.py:48-52 does not record the same-version, several-seed residual.
- test_runner.py:499 and :502 say "the conftest refuses any POST". It refuses only POSTs made through
  requests (conftest.py:25).
- conftest.py:6-7 says "50 lines across 3 test files". grep now finds 51 lines in 4 files; the new one is
  the docstring at test_runner.py:590.
- The test_runner.py:457-459 docstring still says the release engineer "is changing" target reads. That
  change has landed.
- The conftest docstring says the guard covers "import-time code alike". That holds only when the copy is
  an initial conftest.
  - Synthetic probe `scratchpad/adj4_initprobe`: `pytest other` with the guard only in other/zz/tests,
    and an import-time POST in other/test_early.py, gave ProxyError.
  - I found no invocation in this repo that takes this path.

**6. MINOR (reproduced): a deeply nested DEPLOYED.json escapes as RecursionError.** A file of
`'['*100000 + ']'*100000` makes pipeline_version() raise RecursionError (`adj4_target_rec`). No realistic
writer produces such a file.

**7. MINOR (read + ssh): no log line, and more ships in the next push than the builder's diff shows.**
- The runner never prints its stamp.
- /opt/wq/tools/deploy.py has no pipeline_version_of (grep -c 0). A hand-ship of runner.py alone would
  therefore stamp every row `+unverified`.
- /opt/wq has none of these yet (grep -c 0 for each):
  - pipeline_version_of and allow_abbrev in runner.py;
  - AMBIGUOUS_VERSION in recover_orphans.py.
- So the next push ships S1iii-NL, S7-NL and A11 together with the draw-3 fixes.

**8. SUSPECTED (read): backtest_gates.pkey pools rows by meta.seed** (backtest_gates.py:36-39).
- Every ambiguous row would share one pool, (file, None, None, None).
- With a single such row, n_trials is 1, so SR0 is 0 and the row gets no deflation.
- Local journal: 0 of 36,855 rows are ambiguous, and 0 rows with alpha and checks lack a seed.
- It affects an offline report only, and backtest_gates is not the builder's file.

**9. SUSPECTED (read): the MINOR 9 tests run the real climb_submit and auto_submit main().** They pass the
full live flags, and only the parse_args monkeypatch stops them. After a future parsing change,
climb_submit would write its reservation to state/submit_budget.jsonl before the POST guard fires. This
needs a second failure.

### Dropped
- Spec's claim that test_runner.py:648 "on for this directory" is out of date: it is still true. Dropped.
- The guard's urllib, http.client and PUT/PATCH/DELETE gaps: already documented at conftest.py:25. They
  are not a defect of this round.
- Assume's copying of seed and meta by pow_pairs and c11_neut: folded into MINOR 6 (OPEN, TICK) and
  MINOR 7 PARTIAL.

### Fixes still required (NOT signed for push until 1 is closed; 2 and 6 before push)
1. **test_runner.py:463-470: build the replica independently of the layout.** Replace the copy loop with
   the variant in `scratchpad/adj4_fixvariant.py`:
   `src_of = {dst: src for src, dst in DP.PLAN.items()}`, then loop over `DP._root_map(R.ROOT).items()`,
   find `head` as the PLAN destination `remote` equals or starts with (for a directory), and map the file
   to `replica / (src_of[head] + remote[len(head):])`.
   - Measured: 1 passed on the target replica, 1 passed on the source snapshot.
   - With MINOR 3 reverted on the target replica: 1 failed.
   - Fallback: skip on a target layout. That loses the check on /opt/wq.
2. **runner.py:77-92 and test_runner.py:457-459: correct the text.**
   - `<id>` means "the bytes of the files DEPLOYED.json lists agree".
   - Name surface_extras() as where unlisted files are reported.
   - Drop "ALWAYS hashed".
   - The behaviour itself waits on the release TICK. Once Khoa picks, add a target-replica test with an
     unlisted top-level composite.
3. **Guard tests:** add hand-built PreparedRequest cases ('post', b'POST', ' POST ') sent through
   Session.send, both to `_posts()` and to the subprocess test's POSTS.
4. **ab_report test:** `monkeypatch.setattr(AB, "ROOT", tmp_path)`.
5. **The item 5 texts:**
   - cite benchmark by function: build_from(version=...) and compare();
   - reword recover_orphans.py:31;
   - add an OPEN line for one version with several seeds (it cites test_recover_orphans.py:149);
   - "refuses any POST made through requests";
   - "50 code lines, docstrings excluded";
   - narrow the "before collection" sentence.
6. **Before the push:**
   - put the scorer owner's acknowledgement of the MINOR 3 vocabulary on file;
   - say in the release note that S1iii-NL, S7-NL and A11 ship with draw-3.
7. **Optional:**
   - add RecursionError to the except clause;
   - print the stamp once per round;
   - tell the owner of backtest_gates about seed=None.

## Draw-3 fix audit: ci (2026-09-23)

Adjudicator for `tools/ci_gate.py` (sha256 aec86fc2), `tools/ci_fixture.py` (6035cb24),
`tools/ci_golden_card.json` (b37c9df7), `tools/ci_known_red.json` (e0d606a6), `tools/tests/test_ci_gate.py`
(b672f101) and `.github/workflows/ci.yml` (04fa6849). Context files: ci_publish.py 26d05649, deploy.py
61605532, benchmark.py 92232019. The repo still held all of these bytes at 17:32 +07, and all 51
`scorer_closure` hashes still matched the golden then (no drift).

How I checked:
- Snapshot `scratchpad/snap_ci_adj3`; mutations only in `scratchpad/adjci_mut`, each file restored and
  cmp-identical afterwards. Probes: `adjci_nolive_probe.py`, `adjci_closure_probe.py`, `adjci_xprobe.py`.
- One read-only ssh call (`-n -o BatchMode=yes`): timer state, tests_last.json, grep for its readers.
  No simulation, no `--live`/`--submit`, no VPS write.
- Baseline `pytest tools/tests/test_ci_gate.py`: 76 passed.

### What landed

| Item | Verdict | My own evidence (the rest is exec's revert battery, not re-run by me) |
|---|---|---|
| SERIOUS 1 | LANDED | check_no_live on the real tree: ok, "325 Python, 1 workflow, 0 shell script(s)". |
| SERIOUS 2 | LANDED | ci_publish.data_tier (read) allows only on `r["known_red"]` ok+allowed; the comment and JSON say so. |
| SERIOUS 3, ci side | LANDED | Re-ran the audit's experiment: corr_lines PROD,PROD in forge/submit.py -> check_pinned_scorer ok=False, 5 differences, prod_row_limit_does_not_bind_self proven->refuted. |
| SERIOUS 3, publish side | NOT LANDED | `golden_mixed([golden, "forge/submit.py"])` returns `[]` (ci_publish.py:64, :309). Release engineer's file. |
| SERIOUS 4 | LANDED | 35 MUTANTS entries (the report's 36 is wrong). |
| SERIOUS 5 | LANDED for the audit's six placements | Near variants are open (items 4 and 5 below). |
| SERIOUS 6, SERIOUS 7, case_dora, known_red ValueError, _judgement cases-only | LANDED | Read; exec's reverts. |
| ci.yml | LANDED, two wording MINORs | Item 8. |
| Golden | LANDED | `card()` equals the golden. Axis 1 counted two ways (status_counts, and a count over per_alpha): 6/17/9, 6/32 = 0.1875. |

### Surviving defects, ranked

**1. SERIOUS (reproduced; cross-owner, and a RULE 2 gate-5 TICK): the 51-file closure against a 2-file publish rule.**
- A comment-only line appended to forge/runner.py turns check_pinned_scorer red: 1 difference,
  `scorer_closure.forge/runner.py`. `check_pinned_scorer` is in CHECKS, and data_tier treats any
  blocking failure as red. So deploy.py refuses the tree without `--force-unpublished`.
- `record_refusal` returns None for that diff, so the re-record is allowed. `golden_mixed` does not see
  runner.py, so the re-recorded golden can ride in the same commit as the edit. The same holds for 49 of
  the 51 files, forge/submit.py included.
- Fix, release engineer: `golden_mixed` reads the committed golden's `scorer_closure` keys plus
  tools/ci_fixture.py. Test: a publish with forge/submit.py and the golden changed is refused without
  `--split-golden`.
- Fix, Khoa (tick questions): the closure's scope. Options are the full transitive closure (today's
  behaviour, which blocks every live-loop hotfix until a re-record), module-level imports plus the
  deferred imports the scorer reaches, or blocking only in the hermetic tier.
- This batch has to be re-recorded after the other engineers' last save and published with
  `--split-golden`.

**2. SERIOUS (reproduced on a synthetic suite; latent, because none of these variables is set here today): the known-red verdict allows a truncated run.**
- check_tests runs pytest with `env=dict(os.environ, CI="true")` (ci_gate.py:244).
- `adjci_xprobe.py`: the known test fails first and a NEW failure comes after it, fed through the real
  `parse_summary` and `known_red_verdict`.

| Environment | pytest | Verdict |
|---|---|---|
| Clean | rc 1, 2 failed | block (correct) |
| `PYTEST_ADDOPTS=-x` | rc 1, "1 failed" | ok=True, allowed=[known] |
| `--maxfail=1` | rc 1, "1 failed" | ok=True, allowed=[known] |
| `-k known` | rc 1, "1 failed, 2 deselected" | ok=True, allowed=[known] |
| `PY_COLORS=1` | rc 1, ANSI codes around "FAILED" | 0 entries read, block (fails closed) |

- A known-red-only verdict is what deploy.py accepts (PUBLISHABLE_VERDICTS, deploy.py:681).
- Fix, ci_gate.py:
  - drop PYTEST_ADDOPTS and PYTEST_PLUGINS from the env, set PY_COLORS=0 and pass `-o addopts=`;
  - `known_red_verdict` refuses when the output holds "stopping after", "Interrupted" or "deselected",
    or when the stats-line total differs from the collected count.
- Test: the probe suite run under `PYTEST_ADDOPTS=-x` must block.

**3. SERIOUS (process gap, half TICK): the cover printed for the 37 LLM tests is a frozen reading.**
- The constant says "last read 2026-09-23, 210 passed" (ci_gate.py:190-192), and gate() prints it on
  every run.
- Nothing reads the timer's result:
  - locally, the grep hits only ci_gate.py and vps/wq-forge-tests.{sh,service};
  - on the VPS, only wq-forge-tests.{sh,service};
  - forge/digest.py does not read it, although the script header says "the digest reads it";
  - Discord is off.
- Re-read today: the timer is enabled; its run at 10:30:13 +07 wrote ok=true, "210 passed".
- ci-owned fix: take the result out of the constant, or print "result not re-read".
- A reader (the data tier reads tests_last.json and blocks on ok=false or on an age over about 26 h) is
  a new mechanism, so it waits for Khoa's tick.

**4. MINOR (reproduced; fails OPEN; latent): check_no_live misses near variants.**
- On probe trees, each of these gives ok=True:
  - `f"{script} --submit --cap 4"` (the flag-last f-string and the `%` form of the same command are both
    caught);
  - `"cd /opt/wq && %s --submit" % s`;
  - `["bash", "-e", "tools/x.sh"]`;
  - `S = "tools/x.sh"; run(["bash", S])`;
  - a test importing `harness/mod.py` that passes the flag.
- The docstring omits scripts run from an imported module, e.g. forge/search.py:162 runs forge_loop.sh.
- The real tree has none of these today: `scripts_read` is `[]`.
- Fix: read a JoinedStr as a whole template; let _TEMPLATE_COMMAND match after `&&` `;` `|`, `timeout N`
  and `env`; skip shell options; resolve Name bindings the way ci_fixture._path_values does; scan the
  import closure of the tests and conftests. Or narrow the comment at :304-306 and WHAT THIS IS NOT.

**5. MINOR (reproduced; fails CLOSED): data read as a run.**
- A tuple loop with exists(), a parametrize list and `assert plan == ["vps/forge_loop.sh"]` each give
  ok=False and read vps/forge_loop.sh.
- test_ci_gate.py itself has three such data strings: `./tools/z.sh`, `tools/nested.sh` and
  `.github/scripts/nightly.sh`. They are harmless only because those files do not exist.
- Fix: count argv[0] only for a list passed to a spawner, and pin these three placements as not-a-run.

**6. MINOR (reproduced by mutation): claimed behaviours no test holds.**
- ci_gate.py, run on the full file:
  - dropping `i == 0 or`: 76 passed, and `run(["tools/x.sh", "--verbose"])` in a test is no longer read;
  - dropping `p.name == "conftest.py" or`: 76 passed, and a script the root conftest runs is no longer
    read.
- ci_fixture.py, with the two hash tests deselected:
  - slice-assign unread: 74 passed;
  - relative imports skipped cleanly: 74 passed. My first variant, `if False:`, crashed on `None` and
    failed one test, so it did not test this.
  - The closure is unchanged under both: 51 files, same roots.
- benchmark.py: `s <= sl` in place of CORR_UNDER_LINE on the self line moves NO case; the prod-line
  control moves one.
- Fix: add these to the probe trees and to the synthetic closure tree. Add
  `self_corr_exactly_at_the_default_line` (prod 0.5, self 0.70) and its MUTANTS entry.

**7. MINOR (reproduced; one direction fails OPEN, latent): the closure walker skips some sys.path forms silently.**
- `sys.path += [...]`, `sys.path = [...] + sys.path` and `from sys import path; path.insert(...)` each
  leave the module out of the closure, with `unread=[]`.
- `self.path.append(...)` comes out as a bogus unread entry.
- None of these forms is in the 51 files today.
- Fix: handle AugAssign, Assign to sys.path and the `from sys import path` alias; require that the
  Name is `sys`; list anything else in `unread`.

**8. MINOR (text; each re-derived):**
- ci_gate.py:214: "83 characters" should be 81 (from ci_known_red.json).
- ci_fixture.py:617-618: "bound anywhere in the file" contradicts the per-function scoping at :686.
- Wrong citations: runner.py:105 should be :107, and simulate.py:308 should be :309.
- test_ci_gate.py:149: "six targets moved to the constants" should be five (DSR_MIN, NEIGHBOUR_RETENTION_MIN,
  NEIGHBOURS_MIN, CURVE_POINTS_MIN, CORR_UNDER_LINE).
- test_ci_gate.py:351: the name says "reproduces in the ci checkout", but the test asserts a SUBSET
  prefix only. Assert `ci_publish._synced(f)` instead; all 51 pass it today.
- ci.yml:19: "green publish record" should be "green or known-red-only".
- ci.yml:65: "(D9 as written)" reads as if D9 forbade the block. D9 (00_agreements.md:42) asked for it.
- ci.yml:10: "37 tests" is an unpinned count.

**9. MINOR (RULE 2):** the NO_LIVE_EXEMPT entry for tools/notify_lint.py:40 has no tick on file.
Either its owner builds the tokens as `"--" + "submit"`, or Khoa ticks the exemption and the comment
names the tick.

**10. MINOR, EX-ANTE, not reproduced:** Actions pins Python 3.13, while this machine has 3.14.0 and no
3.13. A 3.14-only syntax form in any closure file would split the tiers. I did not re-derive the
builder's 3.13 container run.

**Dropped:** none of the three audits' defects failed to reproduce. The report's "'the three parsers'
text was left" is itself wrong (the text was changed), and that is a report error only.
