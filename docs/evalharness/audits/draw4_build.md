# Draw-4 build audits (2026-09-23)

## Draw-4 audit: pipeline (2026-09-23)

Adjudicator, module `pipeline`. Audited bytes (sha256 prefix): forge/runner.py 9cdf8d90, forge/offline/recover_orphans.py
0a5ae8a9, forge/tests/test_runner.py f1437755, forge/tests/test_recover_orphans.py db5adce5, the three conftests 24e637e0
(byte-identical); read beside them: tools/deploy.py 39c7479c (18:22), forge/offline/benchmark.py bc318f2f (18:11). All runs
were on scratchpad/d4_pipeline_adj (rsync without state/fetched/.git; state and fetched APFS-cloned in for the full suite),
`python3 -B`, `__pycache__` cleared, dead proxy. Every mutant was restored and cmp'd (scratchpad/adjd4_mut.py). VPS: one
read-only `ssh -n -o BatchMode=yes` ls/grep; nothing written there. No sim, no --live/--submit, no commit, no code edit.

### What landed

| Item | Verdict |
|---|---|
| draw3_fix 1 (BLOCKER), 2, 3, 4, 5 | LANDED (text residuals in item 5 below) |
| draw3_fix 6 (scorer acknowledgement, release note) | NOT LANDED: not the builder's files, disclosed |
| draw3_fix 7 (optional) | RecursionError LANDED, but the documented value is wrong on a target (defect 4); stamp print LANDED |
| D30 run_config, stage 0c re-stamp, D40 `+EXTRAS:<n>`, ROUND_KEYS/COHORT_KEYS | LANDED in code; 0c conflicts with recover_orphans (defect 1) |
| notify_lint COMMAND_TOKENS | NOT LANDED (disclosed). The file is unchanged, so keep its NO_LIVE_EXEMPT entry |

Re-measured: the builder's named command gives 128 passed. Full forge/tests + tools/tests (LLM tests ignored) on the
snapshot: 6 failed, 1431 passed. Five are test_ci_gate golden tests (D42: the golden was recorded at 16:44; its
scorer_closure holds runner.py at ec58c7b7, which is no longer current), and one is the known-red D23 test_layered test.
None is in this module's tests. Mutants KILLED: setdefault in stamp(), hashing seed, ROUND_KEYS without run_config.

### Defects (each verified here)

1. **SERIOUS: stage 0c breaks recover_orphans for `--plan` rounds.** MEASURED with scratchpad/adjd4_dupplan.py, which
   runs the real main(), load_plans(), match() and child_row() with LS.run replaced. The experiment plan and main()'s copy
   were placed in one plans directory, as on the VPS. The dispatched stamps were (v-running, e1f7afbdafa17d1a) in every
   case. The recovered stamps:
   - pow shape (base row of another version): (ambiguous, ambiguous)
   - c11 shape (same version, no run_config): (v-running, ambiguous)
   - llm shape (unstamped): (ambiguous, ambiguous)

   Control: with the experiment file removed, every shape recovers the dispatched pair. With the pre-builder code
   (pe3/orig), recovered equalled dispatched in every shape (for pow, the base row's stamps).

   VPS (read-only ls): /opt/wq/state/forge/plans holds c11.json, llmformula.json, llmformula_a.json, llmformula_b.json
   and pow.json among its 220 files. pow_run.sh:29, c11_run.sh:33 and llm_formula_run.sh:44 each pass
   `--plan state/forge/plans/<x>.json`.

   How often future `--plan` rounds will orphan: UNKNOWN. The defect stays latent while the arm drivers are idle.
2. **SERIOUS, cross-owner (scoring): benchmark.cohort_of() and parse_cohort() accept `run_config == "ambiguous"`.**
   MEASURED: they return ('v-running', 'ambiguous'), and 'v-running@ambiguous' parses. recover_orphans' D30 paragraph says
   readers must drop such a row. Together with defect 1, a c11-shape orphan forms a junk cohort.
3. **MINOR: mutant B03 survives.** Changing `extras(base)` to `extras(root)` in pipeline_version() leaves test_runner,
   test_recover_orphans and tools/tests/test_deploy.py green (181 passed). Production calls pipeline_version() with no
   root, so under this mutant every row would be stamped `unknown` or `+unverified` (EX-ANTE, from the code path).
4. **MINOR: RecursionError on a target.** The comment says a too-deep DEPLOYED.json gives `<on_disk>+untracked`. On a
   target-layout replica (scratchpad/adjd4_deep.py) it gives `unknown`. deploy.pipeline_version_of() and
   loop_reachable_extras() both raise RecursionError out of deploy._target_manifest(), which catches only OSError and
   ValueError. There is no crash. The test fakes pipeline_version_of(), so it cannot see this.
5. **MINOR: text.** Each of these was checked against the code or the tree:
   - (a) The comment says "(vps/forge_loop.sh), which deploy never touches", but deploy.PLAN ships vps/forge_loop.sh. What
     deploy never touches is the unit's Environment in /etc/systemd.
   - (b) RUN_CONFIG_EXCLUDED['seed'] reads "kept, it would make ...", which says the opposite of the intent.
   - (c) The value table says "any of them `+EXTRAS`", but `+unverified` and `unknown` can never carry it, because the
     same except clause zeroes the count. It also omits that `unknown` covers "no claim, and the extras count raised".
   - (d) Two places say "selects a cohort by equality on this field (build_from, compare)": the comment above runner.py's
     _VERSION, and recover_orphans' FOR THE SCORER paragraph. The scorer now selects through cohort_of() and plain_stamp().
   - (e) The `OPEN.` marker was dropped, but a `--plan` row still keeps the base row's meta.seed. pow_pairs, c11_neut and
     tvr_pairs all copy meta, and the new test pins `seed == 5` under `--seed 77`.
   - (f) test_runner's BLOCKER docstring states "every push ... would have rolled back" as fact. It is an EX-ANTE code
     read, and draw3_fix says so.
6. **PROCESS (RULE 2).**
   - Stage 0c changes behaviour that draw3_fix MINOR 6 recorded as TICK. D33-D41 cover design §8, but stage 0c is in §7,
     and no decision on file names it.
   - D30 says "changing FORGE_ARGS starts a new cohort", but the plan PATH is excluded from the hash. As a result
     pow_run and llm_formula_run rounds share one run_config (the test pins pow.json == c11.json).

### Dropped or downgraded

- "D40 can be silently disabled" (assume audit): downgraded. I renamed deploy.loop_reachable_extras, and the mutant was
  KILLED by tools/tests/test_deploy.py::test_item1_the_real_runner_does_not_stamp_the_bare_id_beside_an_unlisted_composite
  (the stamp stayed bare, 6071e3e380274822). It survives only forge/tests (51 passed, 1 skipped), which is what the deploy
  smoke runs. Dropping raising=False and the skip is optional.
- B43 (a plan entry with no meta raises KeyError): the mutant survives (63 passed). Every plan writer I read emits meta
  (EX-ANTE). A test for it is optional.
- These were not re-run by me and do not bear on sign-off: the conftest over-match and bytearray guard mutants
  (pre-existing code), `+EXTRAS` being a count rather than an identity (stated design), and the builder's "21 mutants" and
  "10 failed against the original" (the exec audit found 18 mutants in mutate.py and 11 failures after deploy.py landed at
  17:56).

### Fixes still required (exact)

- **P1 (pipeline).** The recovered (pipeline_version, run_config) of a `--plan` round must equal what it dispatched.
  Either mark main()'s own plan copy and have match() prefer marked hits before the COHORT_KEYS check, or have
  load_plans() index only runner-written `<seed>.json`. The owner picks; both only restore stage 0c's stated purpose ("before
  the plan file: recover_orphans reads the stamps there"). Test: pow.json and main()'s 77.json in one PLANS directory, and
  the recovered pair equals the dispatched pair. It must fail on today's code (adjd4_dupplan.py shows it does).
- **P2 (scoring owner).** cohort_of() and parse_cohort() reject a run_config in STAMP_MARKERS, with a test using a plain pv
  and rc 'ambiguous'. The pipeline adds a contract test that cohort_of(child_row(...)) is None for such a row.
- **P3 (pipeline).** A test that R.pipeline_version() with no root equals R.pipeline_version(R.ROOT), with R.ROOT
  monkeypatched to a replica and _VERSION reset. It must kill B03.
- **P4 (pipeline, text).** Narrow the RecursionError sentence and its test docstring to source trees, and say that a target
  gives `unknown`. Alternatively, the release owner adds RecursionError to deploy._target_manifest()'s except, with a
  target-layout test.
- **P5 (pipeline, text).** Apply 5(a) to 5(f) as worded above.
- **P6 (orchestrator, before the push).** Put on file which Khoa decision authorises stage 0c. Put the D30 plan-path
  narrowing to Khoa as a tick question, or hash the plan's content instead of dropping it.
- **P7 (carried from draw3_fix 6).** The scorer owner acknowledges the stamp vocabulary: `+EXTRAS:<n>`, meta.run_config,
  and 'ambiguous' in run_config. A release note names S1iii-NL, S7-NL and A11.
- **P8 (D42).** Re-record the golden in its own commit (ci_publish --split-golden). runner.py and benchmark.py are stale in
  scorer_closure.

Signed for push: no. Required first: P1, P2, P3, P4, P5, P6, P7, P8.

## Draw-4 audit: scoring (2026-09-23)

Adjudicator for module `scoring`. Audited bytes (sha256 prefix): forge/offline/benchmark.py bc318f2fdf9061ae,
forge/tests/test_benchmark.py 0d9d2c6b4b089a28, forge/tests/test_standard.py 27dbad31ed8cf92e. All three auditors
read these bytes, and the repo still held them when this audit ended. The quiet snapshot is
scratchpad/d4_scoring_adjud (state/forge and state/pyramid_cell_counts.json copied in, fetched symlinked).
Probes and the mutation harness are in scratchpad/adj4 (p1-p5.py, mut.py, extra.py).

Each mutant was applied to the snapshot. Then __pycache__ was cleared, this command was run:
`python3 -B -m pytest -q -p no:cacheprovider forge/tests/test_benchmark.py forge/tests/test_standard.py`,
the file was restored, and `cmp` checked it against the repo. Every restore compared equal.
Nothing ran live, no ssh was used, and nothing was written on the VPS.

Every item below is an OBSERVATION reproduced on stated inputs (RULE 0). No mechanism is claimed.

Baseline: 140 passed. Controls:
- a no-op mutant: 140 passed;
- two mutants that must be killed each fail: swapping VERDICT_ORDER fails 3 tests, and dropping G7 from
  MEANING_DECIDABLE fails 1. So the harness imports the mutated file.

### Blocking: verified defects in scoring's files

1. **SERIOUS (latent until the first `deploy.py watch`; push() prints that command as its next step).**
   live_days() and dora() read watch rows as deploys. These rows carry `watched`. tools/deploy.py's
   DEPLOY_LOG comment (WATCH ROWS) says a watch row is never a deploy, and _write_row appends watch rows to
   the target ledger that the judge reads.
   - Reproduced (p5.py): V deployed 09-09 and graded 09-20 has 10 live days. One watch_ok row one hour
     later brings that to **0**.
   - dora([deploy, deploy]) reads 2 deploys and CFR 0.0. Adding a watch_ok row and a watch `interrupted`
     row makes it 4 deploys and CFR 0.25.
   - Fix: stop counting `watched` rows as deploys in both readers, and apply their effect as the contract
     states:
     - watch_rolled_back restores previous_pipeline_version, and counts as a change failure of the push it
       names;
     - watch_ok, watch_timeout and watch_not_rolled_back leave the running version as it is;
     - any other watch outcome makes the running version UNKNOWN, which is live_days' existing rule.
   - Test: live days are unchanged by a watch_ok row, and a watch `interrupted` row is not counted as a deploy.
2. **SERIOUS (latent until run_config-stamped rows exist on the VPS and one experiment round runs).**
   Every D30 cohort (pv, rc) takes the whole live-day set of pv. That set becomes its rate denominator, its
   effective window and the pool _held_next draws from (build_from: `live_days(deploys, wanted[0], now)`).
   - Reproduced (p1.py): V deployed 09-09. (V, r1) has one row on 09-10 and (V, r2) has five rows on
     09-15..19. Graded 09-20, both cohorts read quota_days 10 and rate_days 10.
   - runner.run_config() hashes N and plan_given. So the rounds of vps/c11_run.sh, pow_run.sh and
     llm_formula_run.sh (`FORGE_ARGS="--plan ..."`, each with its own N) form a second cohort under the loop's pv.
   - Neither D30 nor its implementation note says what a cohort's exposure is.
   - Fix (this applies A3's existing rule, "exposure unknown rather than guess"): when another run_config of
     the same pv has a scored row on one of pv's live days in the window, read the cohort's exposure as
     unknown, with a note naming the other run_config(s).
   - Consequence, stated: one experiment round removes the main cohort's rate for any window that contains it.
   - Add an open_ticks item for Khoa: derive a cohort's days from its rows, or record run_config changes in
     the ledger.
   - Replace the `quota_days == 10` assertion in test_a_cohort_is_the_pair_of_stamps_and_a_suffixed_stamp_forms_none.
3. **SERIOUS (latent).** cohort_of() and parse_cohort() apply the marker rule to pipeline_version only.
   forge/offline/recover_orphans.py writes run_config = AMBIGUOUS_VERSION ("ambiguous") when the matched plan
   entries agree on the version but differ on run_config. Its contract says a reader that pools by the pair
   must drop such a row.
   - Reproduced (p1.py):
     - cohort_of({pv ec6a5cd75d58fea2, run_config "ambiguous"}) returns ('ec6a5cd75d58fea2', 'ambiguous');
     - parse_cohort("ec6a5cd75d58fea2@ambiguous") accepts it;
     - run_config "abc+x" also forms a cohort.
   - Consequence: the pseudo-cohort suppresses the "exactly one cohort" gap, and compare() can give a
     verdict on it.
   - Fix: require rc to be None or plain_stamp(rc) in both functions.
   - Test: (V, "ambiguous") forms no cohort, parse_cohort("V@ambiguous") raises, and the one-cohort gap
     still prints.
4. **MINOR, a hard-limit breach (every change needs a test that fails without it).** Each of these mutants
   leaves 140 passed (mut.py).
   - Three reverts of the builder's own stated sub-rules:
     - the status_counts branch counts refuted alphas only;
     - a missing `unproven` is read as 0 ("a hand-built axis 1 without both counts has no level 1");
     - a card without post_horizon is read as final.
   - Stated rules that change a value:
     - G8 dropped from MEANING_DECIDABLE: a generated alpha with G8 false reads PROVEN (pristine: False);
     - the lower tail of the stratified test off by one: on the suite's own [(10,100,10,500)], p is
       0.000210 instead of 0.001197. The pristine value equals a hand-computed binomial tail;
     - rank_cmp does not refuse an open SECOND card, and returns -1;
     - a card with no verdict ranks as PASS;
     - a reading exactly at its line, with the other reading missing, reads None.
   - Fix: add one assert for each.
5. **MINOR.** D27's printed date is wrong when the horizon crosses a DST change: horizon_final_at adds
   14 x 86,400 s to 00:00 ET. Reproduced (p1.py):
   - newest graded day 2026-10-18: final_after is 2026-11-01T23:00-05:00 and comparable_from_et is 2026-11-01.
     Graded at 00:00 ET on 11-01, rank_key still raises NotComparable, whose message promises "at or after
     00:00 ET that day".
   - newest 10-25: the same, on 11-08.
   - newest 2027-02-28: the threshold is 01:00 EDT on 03-15.
   - newest 10-10 and 10-17: correct.
   - Second derivation: newest + 15 ET calendar days gives 11-02 and 11-09.
   - Fix: final_at = _day_start(newest + 15 ET days), with a test at newest = 2026-10-18.
6. **MINOR.** Text in the files that the code contradicts:
   - cell_mix's docstring says "a mix difference cannot move" the verdict. A cell with an event that one
     arm never scored in is a mix difference, and compare() marks it "one arm only", so the verdict is
     indistinguishable.
   - the coverage_gap note says "the rate still counts those days". On an exposure-unknown card (p2.py)
     there is no rate.
   - build()'s cohort gap describes a row with plain pv "V" and run_config 5 as carrying "a suffixed or
     marker stamp", and says that no row carries a plain pipeline_version (p4.py).
   - dora()'s definition says "a deploy is an attempt that reached the code swap". But when stop and
     restart both fail, push() returns units_down BEFORE the swap. That row is written and counted as a
     deploy and as a failure. Decide which reading applies and name it.
   - a comment in test_an_open_card_is_not_ranked_and_prints_when_it_can_be says "cut 09-30 ... closed",
     but its assertion uses a cut of 10-06.
   - on one exposure-unknown card, window.quota_days reads 13 and window.since reads 09-10, while
     effective.rate_days and axis2 quota_days read None (p2.py).

### Verified, not blocking (should fix)
- _epoch reads a scored_at with no UTC offset in the host's time zone. The same meaning row reads gate True
  under TZ=UTC and TZ=Asia/Ho_Chi_Minh, and None under TZ=America/New_York.
- meaning_index raises TypeError when formula_sha is a list. Gates stored as objects ({value, evidence,
  label}, the row shape 04 section 4.2 describes) read null, and no gap line says so.
- load_inputs: a journal named forge[1].jsonl is read through glob, so it grades 0 rows with no gap line.
  A directory path raises IsADirectoryError.
- _corr_ok reads a NaN reading as a measured failure (REFUTED).
- cohort_label and parse_cohort do not round-trip a pv that contains '@'. Unreachable with hex stamps.
- _ab_arm_is_real still passes these runners: `a.ab = 'off'`, setattr, a local `plan` shadow, and `with` or
  `try` blocks that return. The three named holes are closed. A second binding of the parsed name gets the
  misleading message "never hands".
- An empty card outranks P+P+P+U (rank_cmp returns -1). This follows from the ticked order, but rank_key's
  docstring does not say so.
- No test fails when any of these is removed:
  - mdr['scope'];
  - render_compare's "within cell (D28)" lines;
  - post_horizon.seen_until_et;
  - provenance.not_bounded_by_now;
  - the -inf/nan mapping;
  - the coverage gap's `since` filter;
  - the parse_cohort("V@") check;
  - the meaning gates-dict filter;
  - no meaning gap when 0 generated alphas;
  - parse_known_args' same-parser check;
  - nested-def binding counts;
  - the fcntl lock.
- load_inputs stats the journal only after reading it. seen_until assumes the POST logs are at least as fresh
  as the journal; state that in the D27 limit paragraph.

### Dropped
- "stratified_rate_test_p has no computation cap" (SUSPECTED): 10 cells x 1,000 events (10,000) run in
  0.7 s, and the forge era holds 37 events. No stall reproduces.

### Confirmed
- scoring-11: re-derived from the Mac journal copy (read-only): 37 of 31,039 on 9 days, chi-square 95.956 on
  8 df. Dispersion is 11.9945 by exact fractions and 11.99 by _dispersion.
- The same per-day table has no scored row on 09-12..09-19 or on 09-21. This is the builder's POST-HOC
  interior-empty-days item. MECHANISM: UNKNOWN; it is still a decision for Khoa.
- I re-ran the three surviving reverts only. The other 47 reverts and the scoring-11 wording reverts rest
  on auditor 2's and the builder's runs.

### Cross-module (outside scoring's files; routed)
- **CI (owner of ci_gate/ci_fixture): the golden cannot be re-recorded by the tool in either order.** On the
  snapshot, with a scratch copy of the golden:
  - current scorer + current fixture: refused. The scorer moved (benchmark.py, runner.py, deploy.py), and
    so did the fixture (6035cb24 -> cb4aff28);
  - current scorer + committed fixture 6035cb24: "the scorer failed on the truth table", because case_rank
    at 09-23 raises NotComparable;
  - pristine benchmark.py 92232019 + current fixture: AttributeError on B.VERDICT_ORDER.

  tools/tests/test_ci_gate.py on the quiet snapshot: 5 failed, 115 passed. The builder's 46/26/4 predates the
  18:37 fixture. Before a green publish, and so before a deploy, this needs an interim fixture or an
  orchestrator-authorised exception to record_refusal.
- **vps/wq-judge.sh:** it counts success as exactly one more line. If the ledger ends in a cut-short line,
  record_card appends True and wc -l goes 1 -> 3. A same-key repeat appends False and stays at 3. Both runs
  log "recorded NO card" and exit 1. The script should decide from benchmark's stderr ("recorded in" or
  "NOT recorded").
- **D41 authority (orchestrator):** D41 in 00_agreements.md covers the judge on the VPS and push's
  target-ledger reconciliation. No recorded text authorises "at most one card per (cohort, graded ET day,
  host)". Record that rule under D41, or relabel the code and tests with their real authority.
- **D33 (the orchestrator names the owner):** render_compare prints the VERDICT before any confound, but D33
  requires the three cross-time confounds first. No comparison can run today (there is one cohort), so this
  is not blocking.

Signed for push: **no**.

Fixes still required:
- in scoring's files, items 1-6 above;
- outside scoring, the CI re-record path.

Then re-run the 140 tests and tools/tests/test_ci_gate.py on a quiet snapshot, and re-adjudicate.

## Draw-4 audit: release (2026-09-23)

Adjudicator, module `release`. Audited bytes (sha256 prefix; the repo copies were still identical to the snapshot
by cmp when this was written): tools/deploy.py 39c7479c, tools/ci_publish.py f2f40ac0, tools/tests/test_deploy.py
ea07b131, tools/tests/test_ci_publish.py 16dcf5b5, tools/recover_harvest.py 4e05040d, vps/wq-judge.sh dcd49f1b,
vps/wq-judge.service adaf56cd, vps/wq-judge.timer 48689419. All runs were on scratchpad/d4_release_adj, an rsync
without state, fetched, .git or the large data dirs. harness/ and harness13/ were copied back in because the
loop-import tests need them. Runs used `python3 -B` with `__pycache__` cleared. The mutants ran on the copy
d4_release_adj_w; each was restored and cmp'd (scratchpad/adj_rel_mut.py). VPS access was read-only
`ssh -n -o BatchMode=yes` (systemctl show/is-active, man, journalctl, sha256sum, systemd-analyze, stat) plus one
scp of state/forge/loop.log to this Mac. There was no sim, no --live/--submit, no commit and no code edit.

### What landed

| Item | Verdict |
|---|---|
| draw3_fix release 1-8 | LANDED. Suite: 169 passed. Control: removing the reconcile call fails the item-2 tests |
| release 9 | The builder's GUARD relabel LANDED. The audit's "D10" was a wrong citation |
| D40, D42 (publish side), harvester in PLAN, stage 0d smoke | LANDED. The parts no test covers are in defect 10 |
| D16 `deploy.py watch` | Built as specified, but NOT safe to run on the host (defects 1 and 3) |
| D41 judge files | LANDED. The "push waits for the judge" guard does not fire (defect 2); the success rule is wrong in two cases (defect 7) |

Re-measured read-only on the host:
- recover_harvest.py, harvest_loop.sh and wq-forge-tests.sh have the same sha256 as the repo copies (4e05040d,
  2ca6f331, 2f07d0be).
- The judge timer's next elapse is Thu 2026-09-24 11:30 +07.
- The wq-forge unit's Environment is N=300, FORGE_ARGS='--mode composites --order USA/d1,d1 --no-split --delays 1 --ab new'.

### Defects (each verified here)

1. **SERIOUS: push advertises `deploy.py watch`, and the judge misreads every watch row.**
   - _push_inner prints `next: tools/deploy.py watch` after every clean deploy.
   - _write_row appends each watch row to the target ledger too.
   - Measured with the real benchmark.live_days and dora on a synthetic ledger. Version V was deployed and graded
     12 days later.
     - live_days: 11 days; with one watch_ok row added, 0.
     - dora: 2 pushes read 2 deploys; adding 2 watch_ok rows reads 4; adding one watch `interrupted` row reads 3
       deploys, and CFR goes from 0.0 to 0.333.
   - This is the same defect as scoring defect 1 above, reproduced independently here.
   - The builder's own report says watch must not run until the readers map these rows. Nothing enforces that,
     which fails RULE 2 gate 5.
2. **SERIOUS: other_operator_busy() treats only the literal "active" as busy.**
   - EX-ANTE: the host's man page systemd.service(5) (systemd 259, lines 298-304) says a oneshot unit without
     RemainAfterExit "will never enter active", going straight from "activating" to deactivating or dead.
   - On the host, wq-forge-tests is Type=oneshot with RemainAfterExit=no. vps/wq-judge.service has the same shape.
   - POST-HOC and consistent with that: the 09-23 journal shows `Starting` at 10:30:13 and `Finished` at 10:31:14,
     with no `Started` line.
   - Probe, with _remote faked:
     - 'inactive\nactive' gives 'wq-judge is running';
     - 'inactive\nactivating' gives ''.
   - A mutant that counts everything except inactive/failed/unknown as busy passes all 169 tests, because the
     test feeds "active", which these units never print.
   - Not observed here: is-active printing "activating" during a live run. Seeing it would mean starting a unit.
   - Consequence: the D41 guard, and the older wq-forge-tests guard, most likely never fire. _watch_rollback does
     not call the check at all.
3. **SERIOUS (watch only): the D16 trigger fires on the incumbent at a measured rate that no text states.**
   - Data: loop.log copied at 19:10 +07, 182 headers, 181 finished rounds.
   - Two ways agree: an awk tally of the `=== round exit` lines, and deploy's own _round_verdict run on each header
     slice.
     - 153 exit 0, 5 exit 2, 22 exit 1 (each with a Traceback), 1 exit 143.
     - So 23 of 181 (12.7%) would have been rolled back.
   - CONFOUND first: 21 of the 23 fall on 09-06 between 17:00 and 20:59 +07.
   - The line before every exit-1 is a requests exception against api.worldquantbrain.com: 14 ReadTimeout,
     5 ConnectionError, 3 SSLError. That is POST-HOC. Whether the code running then contributed: MECHANISM: UNKNOWN.
   - EX-ANTE from vps/forge_loop.sh: after RC=1 the loop still runs recover_orphans, harvest, the probe and
     `forge/submit.py --submit --cap 4` before it checks STOP_FORGE. Quiesce waits for all of these.
   - D16 (00_agreements.md) says "before any quota is spent". A watch that reads the first round's exit cannot
     meet that.
4. **MINOR: live_at is set before start_units().** So a units_down row carries it, and so does a push made while
   no unit was running. The contract says such a row is null.
5. **MINOR: two texts say a refused push only reads the target.** The _push_inner docstring says so for every
   step before "units before the push", and the stage-0d banner says "Nothing was touched". In fact
   reconcile_target_ledger appends rows and snapshot() writes the tar before those points.
6. **MINOR: status() predicts the wrong stamp for one manifest shape.** For a DEPLOYED.json with a string claim
   but no hashes map, it says "the runner stamps <pv>+untracked". forge/runner.py pipeline_version() stamps the
   claim instead: bare, +MISMATCH, or +unverified.
7. **MINOR: wq-judge.sh counts two correct outcomes as failures.** It succeeds only when cards.jsonl gains
   exactly one line.
   - Measured with a fake venv python that follows record_card's documented behaviour; the assume audit ran the
     real record_card.
   - A same-day repeat (the idempotent no-op) exits 1 and logs "1 -> 1 lines".
   - An unterminated last line plus one card exits 1 and logs "1 -> 3".
8. **MINOR: watch has no limits on what it judges.** It sets no age limit on the push, does not check
   other_operator_busy before its rollback, and will watch the same push again.
9. **MINOR: an interrupt during watch's quiesce writes a row with no `undo`.** The DEPLOY_LOG text says watch rows
   carry `undo`. Found by reading _watch_rollback and _record_watch.
10. **MINOR: code with no test.** Six mutants pass all 169 tests:
    - (a) `added = to_delete`: a rollback of a virgin push no longer removes DEPLOYED.json;
    - (b) reconcile without `left += 1`;
    - (c) _target_started_from without the __END__ check;
    - (d) SCORER without tools/ci_fixture.py. The live golden's 51-key closure does not contain that file (MEASURED);
    - (e) the sign of watch's clock correction flipped;
    - (f) watch's `undo = rollback_raised` removed.

    Separately, test_blocker1_status_counts_the_extras_names_ten_and_deletes_nothing patches only ROOT, so it
    reads the desk's real DEPLOY_LOG and RECONCILED_LOG.
11. **MINOR: _target_manifest() catches only OSError and ValueError.** A DEPLOYED.json nested 100,000 levels deep
    in a target layout makes _target_manifest, loop_reachable_extras and status() raise RecursionError (probe run
    here). This is the release side of pipeline defect 4.
12. **MINOR: texts that do not hold.**
    - (a) The D16 comment says "179 rounds", but its exits 150/22/5/1 sum to 178.
    - (b) The DEPLOY_LOG NOTE says dora's failure set lacks INTERRUPTED. That is stale: dora now names interrupted
      and units_down.
    - (c) The wq-judge.sh exclusion's grep sentence says two files name cards.jsonl. Six do today.
    - (d) LIBRARY_DIRS says staged/ "is never touched by push". file_map ships forge/ by rglob with no staged
      exclusion, so push never DELETES staged/ but would copy a dev-tree staged YAML over the target's. The dev
      tree has none today.
    - (e) D40's comment does not name forge/offline/promote_staged.py. That file has been on /opt/wq since 09-10
      and no unit runs it. A mechanism promoted on the host would be deleted by the next push.

SUSPECTED, latent today, not reproduced here:
- `grep -b` is run without -a. The copied log holds 0 NUL bytes.
- _remote passes the terminal's stdin to ssh during watch.
- A FORGE_ARGS containing --seed would redirect the smoke's plan file. Today's FORGE_ARGS has none.
- What the remote quiesce does after the client dies is the builder's open item (MECHANISM: UNKNOWN); watch adds a
  second route to it.

### Dropped or not reproduced

- Planner smoke at N=300 against _remote's 900 s timeout: dropped. Plan mtime minus seed on the host's 36 newest
  timestamp-seeded plans is 18/22/24 s (min/median/max), with the hand-seeded 211.json excluded. One method only.
- golden_mixed's "49 of the 51": correct when read as "runner.py plus 49 others". The closure has 51 files and
  holds benchmark.py but not ci_fixture.py, so 50 were unpinned. Not a defect.
- One run of mutant (e) reported "1 error". Two reruns (-k watch: 16 passed; full suite: 169 passed) did not
  reproduce it. No verdict.

### Decisions, not repairs

- wq-forge-tests.sh is in PLAN and in the id (in_pipeline True), yet no decision names it. The D41 note names
  harvest_loop.sh and recover_harvest.py only. The orchestrator should record why it is included, or exclude it
  as wq-judge.sh is.
- The pre-ledger row 8f8b7517b8598d07 stays unreconciled (D33 exposure window): Khoa or the orchestrator decides.
- D40 against promote_staged run on the host: refuse, require a flag, or accept the deletion. This is Khoa's
  decision (a D40 tick).
- The D16 trigger in defect 3 goes to Khoa as a tick, with the base rate and the 09-06 cluster on the question.

Push prerequisites, not defects: tools/deploy.py is in the golden's scorer_closure, so the golden must be
re-recorded and published with --split-golden, and push needs that publish record (M9-NL).

### Fixes still required

- **R1 (release + scoring).** No watch row may reach the judge until benchmark maps watch rows (scoring defect 1).
  Until then, drop the `next:` line and make watch() refuse with exit 2 and no row. Rename the watch's interrupted
  outcome to `watch_interrupted`. Add a cross-module test that runs the real live_days over [deployed V, watch_ok V]
  and asserts V's days are kept, and runs dora over [deploy, watch interrupted, deploy] and asserts 2 deploys.
- **R2.** other_operator_busy() counts every state except inactive and failed as busy (or reads ActiveState). The
  test must feed "activating", and it must fail on today's code. _watch_rollback calls the check before
  stop_units. Correct the wq-judge.service header.
- **R3.** The D16 comment states the 23/181 base rate, the 09-06 cluster and the limit that submit runs before
  STOP_FORGE, and the 178/179 count is corrected. The trigger is ticked by Khoa before the first real watch.
- **R4.** Fix defects 4-9 and 11 as described, each with a test that fails without it (the judge's duplicate and
  repair-newline cases; status on {"pipeline_version": "x"}; RecursionError on a target layout).
- **R5.** Add tests that kill mutants 10(a)-(f), and patch DEPLOY_LOG and RECONCILED_LOG in every status test.
- **R6.** Correct texts 12(a)-(e).
- **R7.** Record the four decisions above.

Signed for push: **no**. Required first: R1, R2, R3, R4, R5, R6, R7. Then re-run tools/tests/test_deploy.py and
tools/tests/test_ci_publish.py on a quiet snapshot and re-adjudicate.

## Draw-4 audit: ci (2026-09-23)

Adjudicator, module `ci`. Audited bytes (sha256 prefix): tools/ci_gate.py b920db59, tools/ci_fixture.py cb4aff28,
tools/ci_golden_card.json e1d79f09, tools/ci_known_red.json 06f0ccc1, tools/tests/test_ci_gate.py cb5730a8,
.github/workflows/ci.yml 55d481af. Read beside them: forge/offline/benchmark.py bc318f2f, tools/ci_publish.py f2f40ac0,
tools/ci_classify.py. All runs used scratchpad/d4_ci_adj (rsync without state, fetched, .git and the three large data
directories) plus five worker copies, `python3 -B` (3.14.0, pytest 9.1.1), with `__pycache__` cleared. Every mutant was
restored and cmp'd (scratchpad/d4adj_mut.py, d4adj_moves.py). The probes are scratchpad/d4adj_probe.py and its .out. At
the end the repo's six files were cmp-identical to the audited bytes. No VPS command, no sim, no --live/--submit, no
commit, no code edit.

### What landed

| Item | Verdict |
|---|---|
| ci-2 (SERIOUS): environment, `-o addopts=`, no `-q`, run_incomplete, verdict | LANDED for what it names. Narrowing at collection is still open (defect 2) |
| ci-3 (D42 orchestrator decision) | LANDED |
| ci-4, ci-5, ci-6, ci-7 | LANDED for the audit's variants. Near variants are still open (defect 6) |
| ci-8 | LANDED, except one citation by line number (defect 8e) |
| ci-9, the notify_lint NO_LIVE_EXEMPT entry | NOT LANDED, and disclosed. tools/notify_lint.py is unchanged, so the entry stays; it is an open RULE 2 item |
| ci-10 | LANDED |
| D26, D27, D28, D29, D30, D39 cases | LANDED. The D30 marker-stamp clause is reached by no case (defect 1) |
| ci-1 CI half (the golden) | LANDED. I re-hashed it here: 17 cases, and the 51 closure hashes, fixture cb4aff28 and scorer bc318f2f all equal the bytes on disk |

Re-measured:
- tools/tests/test_ci_gate.py: 121 passed (98 s).
- check_no_live on the snapshot: ok. It read 334 Python files (8 of them outside forge/tools/vps), 1 workflow and 0
  scripts. closure_unread is tools/ci_classify.py:81 and tools/watchdog.py:253. This matches the builder and both
  execution audits.
- Mutants killed: the D27, D28, D30 and D39 case mutants each move only their own case. The control "the verdict ignores
  `incomplete`" is killed.

### Defects (each verified here)

1. **SERIOUS (the draw-3 ci SERIOUS 4 class): the D30 marker-stamp clause moves no case.** I removed
   `and v not in STAMP_MARKERS` from benchmark.plain_stamp() and recomputed the card: 0 case leaves moved. For
   comparison, no edit moves 0, the D29 mutant moves 3 and the D26 mutant moves 7. The case_cohorts docstring says "a
   '+'-suffixed or marker stamp ... form NO cohort", but no row in any case carries `unknown` or `ambiguous`. Without the
   clause, rows stamped `unknown` form a cohort, and a re-record diff shows only benchmark.py's hash moving.
2. **MINOR (downgraded from the execution audit's SERIOUS): "the run was the whole suite" claims more than
   run_incomplete reads.**
   - MEASURED on the known failure plus a NEW failure: a root conftest `collect_ignore`, a pytest.ini `python_files` and
     a `pytest_ignore_collect` hook each gave rc 1, counted 1, incomplete [] and known_red_verdict ok=True.
   - Controls: with nothing changed, the run blocks. A modifyitems hook that drops the item and a maxfail hook are both
     read as incomplete and block.
   - Why it is downgraded: each of the three needs a tree edit that the diff shows, the same as deleting the test, which
     no gate detects. None of them exists today: there is no ini file in the repository, and the three conftests
     (24e637e0) define none of these hooks.
   - The claim is made in the ci_gate module docstring, in the known_red_verdict, check_tests and run_incomplete
     docstrings, in ci_known_red.json 'what', in the ci.yml header, and in
     test_a_run_the_tree_itself_shortens_is_never_a_known_red ("Whatever shortened it, the output says so").
3. **MINOR (fails open, latent): a result with no `incomplete` key reads as complete.** known_red_verdict returned
   ok=True on it (probe B1). The same dict without `counted` blocks. Making absence block fails
   test_only_the_listed_node_failing_the_listed_way_is_allowed, because the `_result()` helper omits the key.
4. **MINOR (fails closed, as a crash): a self-referential argv binding crashes the scan.** A test holding
   `cmd = ['bash']; cmd = cmd + ['tools/x.sh']; subprocess.run(cmd)`, or `def f(cmd): cmd = cmd + ['-v']; subprocess.run(cmd)`,
   makes check_no_live raise RecursionError. _argv_elements has no depth bound, and the per-file handler catches only
   OSError, SyntaxError and ValueError. gate() and ci_publish.data_tier() then raise without naming a file.
5. **MINOR (a change with no test that fails without it): six mutants of the new code survive the whole test file (121
   passed each).**
   - K1: `_bound(n.args[0], env)` changed to `[n.args[0]]` in _scripts_python_runs().
   - K2: `skipped` dropped from _OUTCOME.
   - K3: check_no_live's closure handler narrowed to ZeroDivisionError.
   - K4: the outcomes read from the whole output instead of the last line.
   - K5: `!=` changed to `>` in run_incomplete's deselected test.
   - K6: _ARGV_LAUNCHERS reduced to ("timeout",).
6. **MINOR (fails open, latent, and not named in WHAT THIS IS NOT): forms the scan does not read.** Each of these read
   ok=True although the script or template passes the flag:
   - templates: a newline used as a separator; `nice -n 5 %s`; `timeout -s KILL 60 %s`; a template held in a name
     (`T = "%s ..."; T % s`);
   - scripts:
     - `run("timeout 60 tools/x.sh", shell=True)` and `run("A=1 tools/x.sh", shell=True)`;
     - an annotated assignment (`S: str = ...`) and `run(args=[...])`;
     - `["sudo", "-u", "wq", ...]`;
     - `os.spawnl(os.P_WAIT, ...)` and `create_subprocess_exec("bash", ...)`;
     - an absolute path, `/opt/wq/tools/x.sh`.

   The controls are flagged: `'%s <flag>' % s`, `["sudo", "tools/x.sh"]` and `["bash", "tools/x.sh"]`. The _SPAWN comment
   ("their first argument is a command") is false for spawn* (whose first argument is the mode) and for the varargs
   spawners. A sys.path write through an alias (`P = sys.path; P.insert(0, 'harness')`) is dropped with closure_unread
   [], against _sys_path_entries' "listed unread" contract. The control, `sys.path.insert`, flags harness/mod.py.
7. **MINOR (fails closed; a regression): prose f-strings that start with a value are now flagged.**
   `f"{n} alphas staged; pass <flag> to post them"` gives [2] now and [] on the pre-change gate (snap_ci_aud2). The same
   prose starting with a word gives [] in both.
8. **MINOR, text.**
   - (a) run_incomplete's docstring and ci_known_red.json say "more tests deselected", but the code tests `!=`: probe C1
     shows that fewer also blocks. --deselect also matches by prefix.
   - (b) The ci_fixture module docstring's SERIOUS 4 bullet still names case_rank's "U". The card that catches that
     mutant is now "nothing submitted".
   - (c) The same docstring says "an edit ... that the case must see", and the builder reports "removing the case
     caught". Measured: the D29 mutant moves rank_open_horizon as well as verdict_leads_rank, and the D26 mutant moves
     floors and rank. The MUTANTS test only asserts that SOME case moves.
   - (d) DECISIONS_LITERAL is headed "The decisions ticked". Its entry compare_within_cell.a_cell_one_arm_never_scored
     is "not endorsed" per case_compare_within_cell, and D28 does not settle it. D39 does not settle
     gen_two_formula_shas or gen_malformed_gate_value either.
   - (e) test_the_import_closure_is_found_by_the_syntax_tree_with_the_roots_it_derives cites tools/layered_alpha.py by
     line number.
9. **SUSPECTED, optional: pytest is not pinned.** ci.yml installs pytest without a version, while run_incomplete parses
   pytest 9.1.1's human-readable output. This fails closed, Actions only reports (D31), and it has not been observed.

### Dropped
- Skip or xfail markers added by a conftest (exec T4/T5): not a defect, because pytest reports them as outcomes.
- The builder's "104 / 20 lines": this is in the report only. The exec audit reads "20" as _diff leaves; I did not
  re-derive 104.

### Cross-module (routed)
- **X1 (D42; orchestrator and release).** There is no golden drift now. Pipeline P1/P3 (runner.py) and the scoring fixes
  (benchmark.py) will move scorer_closure.
  - Re-record after the last of those edits, in two steps: first with the fixture at cb4aff28 (a diff of the scorer
    alone), then C1's fixture change (a diff of the fixture alone). Commit each on its own (--split-golden).
  - If the current fixture crashes on the new scorer, record_refusal has no route. This is the builder's NEW item and
    the scoring section's routed item; the orchestrator authorises the path (RULE 2).
- **X2 (owner of tools/ci_classify.py).** run_arm() runs pytest with the full environment and `-q`, and reads no
  completeness. This is the ci-2 class, EX-ANTE by reading; not run.
- **X3.** The notify_lint exemption waits for Khoa's tick or for its owner to build the token.

### Fixes still required (exact)
- **C1.** case_cohorts gets rows stamped pipeline_version `unknown` and `ambiguous`. Expected: they count under "no
  cohort", and asking for them as a cohort raises ValueError. Add a MUTANTS entry that drops
  `and v not in STAMP_MARKERS` from plain_stamp(). Once scoring's P2 lands, add a row with run_config `ambiguous` and its
  mutant as well.
- **C2.** Narrow every sentence listed in defect 2 to "every test pytest collected ran and was counted". Name
  collect_ignore[_glob], pytest_ignore_collect and the ini options python_files/python_classes/python_functions as NOT
  detected, or pass `-o` for those three options and test it with the pytest.ini probe. Update the matching assertion in
  test_the_known_red_file_says_what_the_publish_path_does.
- **C3.** known_red_verdict blocks when `incomplete` is absent. `_result()` and the `publish()` helper carry
  `incomplete: []`. Add a test that a dict without the key blocks.
- **C4.** Bound _argv_elements with a depth or a visited set, and have check_no_live's per-file handler catch
  RecursionError and report the file as "cannot be checked". Test it with `cmd = cmd + [...]; subprocess.run(cmd)` in a
  test file.
- **C5.** Add tests that kill K1-K6:
  - `ARGV = ["tools/w_n.sh"]; subprocess.run(ARGV)`;
  - an outcome line with skipped, xfailed and xpassed that reads [];
  - an outcome word above the last line that is not counted;
  - an unparsable test file whose offender is named, with no raise;
  - fewer deselected than asked, which blocks (or change the code to `>` and say so);
  - the argv forms `["sudo", "tools/w_s.sh"]` and `["env", "A=1", "tools/w_e.sh"]`.
- **C6.** Correct the _SPAWN comment. Read, or name in WHAT THIS IS NOT, every form in defect 6. List an alias or a
  non-import `sys` write to sys.path as unread, or narrow that contract's text.
- **C7.** Fix the texts in 8(a)-(e) as worded above.
- **Optional.** Name or narrow defect 7. Pin pytest==9.1.1 in ci.yml.

Then re-run tools/tests/test_ci_gate.py on a quiet snapshot, with a revert of each fix showing its test fail, and
re-adjudicate.

Signed for push: **no**. Required first: C1, C2, C3, C4, C5, C6, C7, and X1's re-record after the scoring and pipeline
fixes land.
