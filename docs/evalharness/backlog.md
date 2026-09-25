# evalharness backlog

Owner: the evaluation system's technical programme manager. Created 2026-09-24.

**Why this file exists.** The sign-off rule recorded with D43–D46 in `00_agreements.md` says a module is signed
for push when no BLOCKER or SERIOUS defect survives its adjudicator. The same rule says the MINOR items that
survive go to this file with their evidence, and are never silently dropped. On 2026-09-23 the draw-5 release
adjudicator found that this file did not exist, so round 3's N1–N3, m1–m20 and X1–X5 were recorded nowhere
(`audits/draw5_build.md` › release › process items).

**The sources, one table each:**

1. `audits/draw4_build.md`: every item in all four module sections. This covers the defects, the "verified,
   not blocking" items, the SUSPECTED items, the items routed to other modules, the decisions, and the optional
   items. It leaves out only what that file itself dropped as a non-defect.
2. `audits/architecture_round3.md`: N1–N3, m1–m20 and X1–X5, plus the one MINOR in its Disclosures section.
3. `audits/draw5_build.md`: every "MINOR for backlog" list, including each list's SUSPECTED items and the
   release section's process items.
4. A short fourth table lists the draw-5 items that sit outside those MINOR lists: the SERIOUS items, the push
   preconditions, the ticks and the routed items. They are not backlog, because they block sign-off. They are
   listed here only so that none of them is lost.

## How each status was checked

- **Method.** Every status comes from reading the current code or document on 2026-09-24. No code was edited,
  no test was run, no mutant was applied, and nothing touched the VPS.
- **Draw-4 and round-3 items.** These were raised against the Draw-4 bytes, which draw 5 then changed, so each
  item was checked by reading the function, comment or test it names.
- **Draw-5 items.** Every file the draw-5 adjudicators audited is still byte-identical to the bytes they
  audited. The sha256 prefixes read on 2026-09-24:
  - runner d2e84b70, recover_orphans 99aae169, benchmark b30d255c, meaning 01bc3c3a, deploy 7ff14dbc;
  - ci_gate 62d1c28c, ci_fixture e2feced0, ci_publish d1de5f28, ci_classify 54c634c3, notify_lint 36f2d30a;
  - forge_loop.sh a0b3df46, forge.env c514eed8, wq-judge.sh 13017d1c, wq-judge.service 27b71125,
    systemd_wq-forge.service 6a3af0bd;
  - ci_golden_card d8a0cc0e, ci_known_red 8867dd79, ci.yml 4c7d603a;
  - the eight forge/gen modules and the seven test_gen_* files;
  - test_runner ffa78576, test_recover_orphans 59b694a9, test_meaning 80a55fc6, test_benchmark cc9897c8,
    test_deploy 3465d11b, test_ci_publish d75ec10b, test_ci_gate ae1b8c66.

  So no draw-5 item can have been fixed inside its own module since the audit. The exception is an item that
  names a file audited by a LATER draw-5 section. Those items were re-read one by one, and the row says so.
- **Not re-read.** A row marked "not re-read" names a file or host that was not opened for this backlog.

**What the statuses mean:**

| status | meaning |
|---|---|
| `open` | The code or text read today still shows the defect, or nothing read today shows a fix. |
| `fixed (draw 5)` | I read the code or test that fixes it. The row names the function or test. |
| `partly fixed (draw 5)` | Part of it is fixed. The row names the part that is still open. |
| `decided (…)` | A decision recorded in `00_agreements.md` settles it (a Khoa tick or an orchestrator decision), and the code follows that decision (read). |
| `superseded (…)` | A later decision removed the item's premise. |
| `optional` | The adjudicator marked the fix optional. |

## Counts

| source | rows | open | fixed | partly fixed | decided | superseded | optional |
|---|---|---|---|---|---|---|---|
| draw4_build.md | 81 | 9 | 56 | 6 | 7 | 1 | 2 |
| architecture_round3.md | 29 | 17 | 7 | 5 | 0 | 0 | 0 |
| draw5_build.md, MINOR lists | 113 | 111 | 1 | 1 | 0 | 0 | 0 |
| draw5_build.md, outside the MINOR lists | 19 | 19 | 0 | 0 | 0 | 0 | 0 |
| **total** | **242** | **156** | **64** | **12** | **7** | **1** | **2** |

- Rows that duplicate another row are marked "dup of …" and are still counted, so that each source's table is
  complete on its own.
- Every row carries one of the six statuses above.

---

## 1. `audits/draw4_build.md`

### 1a. Pipeline (runner.py, recover_orphans.py)

| id | file / function | defect | evidence | status |
|---|---|---|---|---|
| D4-PL-1 | forge/offline/recover_orphans.py `load_plans`, `match` | SERIOUS: stage 0c broke recovery of `--plan` rounds. The experiment plan and the runner's copy were indexed together, and a recovered row came back (ambiguous, ambiguous) or (v-running, ambiguous) instead of the dispatched pair. | draw4_build.md › pipeline › Defects 1; Fixes P1 | fixed (draw 5): `load_plans` indexes only `RUNNER_PLAN` (`<seed>.json`) copies (D46) |
| D4-PL-2 | forge/offline/benchmark.py `cohort_of`, `parse_cohort` | SERIOUS (cross-owner): a run_config of "ambiguous" formed a cohort. | draw4_build.md › pipeline › Defects 2; Fixes P2 | fixed (draw 5): `_forms_cohort` requires a plain run_config; the pipeline-side contract test is `test_a_row_ambiguous_on_either_stamp_forms_no_cohort` (test_recover_orphans.py) |
| D4-PL-3 | forge/runner.py `pipeline_version` | Mutant B03 (`extras(root)` instead of `extras(base)`) survived every test. | draw4_build.md › pipeline › Defects 3; Fixes P3 | fixed (draw 5): `test_the_version_with_no_root_is_the_version_of_the_runners_own_tree` |
| D4-PL-4 | forge/runner.py `_VERSION` comment; tools/deploy.py `_target_manifest` | A too-deep DEPLOYED.json on a target read `unknown`, while the comment promised `<on_disk>+untracked`. | draw4_build.md › pipeline › Defects 4; Fixes P4 | fixed (draw 5) in code: `_target_manifest` now catches RecursionError. The runner comment now describes the old behaviour; that is D5-PL-M1 |
| D4-PL-5a | forge/runner.py D30 comment | The comment said deploy never touches forge_loop.sh, but deploy.PLAN ships it. | draw4_build.md › pipeline › Defects 5(a) | fixed (draw 5): the comment now says deploy ships it and never writes /etc/systemd |
| D4-PL-5b | forge/runner.py `RUN_CONFIG_EXCLUDED['seed']` | The text said the opposite of what was intended ("kept, it would make…"). | draw4_build.md › pipeline › Defects 5(b) | fixed (draw 5): now reads "were it hashed, every round would be a cohort of one" |
| D4-PL-5c | forge/runner.py value table above `_VERSION` | The table implied that `+unverified` and `unknown` could carry `+EXTRAS`, and it did not say that `unknown` also covers "extras could not be counted". | draw4_build.md › pipeline › Defects 5(c) | fixed (draw 5): both are now stated |
| D4-PL-5d | runner `_VERSION` comment; recover_orphans FOR THE SCORER paragraph | Both said the scorer selects a cohort "by equality". | draw4_build.md › pipeline › Defects 5(d) | fixed (draw 5): both now name `cohort_of`/`parse_cohort`/`plain_stamp` |
| D4-PL-5e | forge/runner.py `stamp` | The OPEN marker was dropped, but `--plan` rows still keep the base row's meta.seed. | draw4_build.md › pipeline › Defects 5(e) | fixed (draw 5) as text: the OPEN marker is back in `stamp`'s docstring. The behaviour it names is still open (see D5-RL-8) |
| D4-PL-5f | forge/tests/test_runner.py BLOCKER docstring | An EX-ANTE code reading was stated as a fact. | draw4_build.md › pipeline › Defects 5(f) | fixed (draw 5): `test_the_stamp_agrees_with_the_real_deploy_manifest_on_a_source_tree` labels it EX-ANTE |
| D4-PL-6a | design stage 0c | PROCESS: no decision on file authorised stage 0c. | draw4_build.md › pipeline › Defects 6; Fixes P6 | decided (D46) |
| D4-PL-6b | forge/runner.py `run_config` | PROCESS: the plan PATH was excluded from the hash, so pow_run and llm_formula_run rounds shared one run_config. | draw4_build.md › pipeline › Defects 6; Fixes P6 | fixed (draw 5): `plan_sha256` hashes the plan's content, under the orchestrator decision recorded with D43–D46 |
| D4-PL-P7 | benchmark stamp vocabulary; release note | The scorer owner was to acknowledge `+EXTRAS:<n>`, meta.run_config and 'ambiguous', and a release note was to name S1iii-NL, S7-NL and A11. | draw4_build.md › pipeline › Fixes P7 | partly fixed (draw 5): the `STAMP_MARKERS`/`_forms_cohort` comments cover the vocabulary. No release note naming S1iii-NL, S7-NL and A11 exists under docs/evalharness |
| D4-PL-P8 | tools/ci_golden_card.json | The golden was to be re-recorded in its own commit (`ci_publish --split-golden`). | draw4_build.md › pipeline › Fixes P8 | partly fixed (draw 5): the dev-tree golden is current (all 51 closure hashes, the fixture hash and the scorer hash match disk). The CI checkout's HEAD is still 1fce953 and holds a different golden, so the commit is still to do |
| D4-PL-O1 | forge/tests/test_runner.py (`raising=False` and skip) | "D40 can be silently disabled" was downgraded; dropping `raising=False` and the skip is optional. | draw4_build.md › pipeline › Dropped or downgraded | optional (`raising=False` is still used) |
| D4-PL-O2 | recover_orphans plan entry without meta | B43: a plan entry with no meta raises KeyError, and that mutant survives. A test is optional. | draw4_build.md › pipeline › Dropped or downgraded | optional |

### 1b. Scoring (benchmark.py)

| id | file / function | defect | evidence | status |
|---|---|---|---|---|
| D4-SC-1 | benchmark `live_days`, `dora` | SERIOUS: watch rows were read as deploys. One watch_ok row took a version from 10 live days to 0, and CFR moved. | draw4_build.md › scoring › Blocking 1 | fixed (draw 5): `_is_watch`, `WATCH_KEEPS_RUNNING`, `WATCH_ROUND_FAILED` |
| D4-SC-2 | benchmark `build_from` exposure | SERIOUS: every (pv, rc) cohort took all of its pv's live days. | draw4_build.md › scoring › Blocking 2 | fixed (draw 5): `cohort_live_days` reads the D45 run_config log (the fix itself is D45) |
| D4-SC-3 | benchmark `cohort_of`, `parse_cohort` | SERIOUS: the marker rule applied to pipeline_version only. | draw4_build.md › scoring › Blocking 3 | fixed (draw 5): `_forms_cohort` (dup of D4-PL-2) |
| D4-SC-4 | forge/tests/test_benchmark.py | Eight mutants of stated sub-rules left 140 passed. | draw4_build.md › scoring › Blocking 4 | fixed (draw 5): `test_the_draw3_fix_sub_rules_are_each_pinned` |
| D4-SC-5 | benchmark `horizon_final_at`, `comparable_from` | The printed D27 date was wrong across a DST change. | draw4_build.md › scoring › Blocking 5 | fixed (draw 5): `comparable_from`; `test_the_comparable_date_holds_across_a_dst_change`. It departs from the audit's suggested fix, and its docstring gives the reason |
| D4-SC-6a | benchmark `cell_mix` docstring | The docstring said a mix difference cannot move the verdict. | draw4_build.md › scoring › Blocking 6 | fixed (draw 5) |
| D4-SC-6b | benchmark `build_from` coverage_gap note | The note said "the rate still counts those days" on cards that have no rate. | draw4_build.md › scoring › Blocking 6 | fixed (draw 5): now "a rate on this card". A new objection to the same note is D5-SC-M17 |
| D4-SC-6c | benchmark `build` cohort gap | The text called a plain-pv row "suffixed or marker". | draw4_build.md › scoring › Blocking 6 | fixed (draw 5) |
| D4-SC-6d | benchmark `dora` docstring | Its definition of a deploy did not fit a units_down row returned before the swap. | draw4_build.md › scoring › Blocking 6 | fixed (draw 5) |
| D4-SC-6e | test_benchmark `test_an_open_card_is_not_ranked_and_prints_when_it_can_be` | The comment said "cut 09-30"; the assertion uses 10-06. | draw4_build.md › scoring › Blocking 6 | fixed (draw 5) |
| D4-SC-6f | benchmark `build_from` window | On an exposure-unknown card, window.quota_days and window.since were set while rate_days was None. | draw4_build.md › scoring › Blocking 6 | fixed (draw 5) |
| D4-SC-NB1 | benchmark `_epoch` | A scored_at with no UTC offset is read in the host's time zone. | draw4_build.md › scoring › Verified, not blocking | open |
| D4-SC-NB2 | benchmark `meaning_index`, `_standard_gate` | A list formula_sha raised TypeError, and gates stored as objects read null with no gap line. | draw4_build.md › scoring › Verified, not blocking | partly fixed (draw 5): the TypeError is gone (a `!=` compare). Object-valued gates still read null with no gap line |
| D4-SC-NB3 | benchmark `load_inputs` | A journal named `forge[1].jsonl` read 0 rows through glob, and a directory path raised. | draw4_build.md › scoring › Verified, not blocking | fixed (draw 5): `read_journal` opens the path as given and checks `is_file`. The same class in other loaders is D5-SC-M11 |
| D4-SC-NB4 | benchmark `_corr_ok` | A NaN reading is read as a measured failure (REFUTED). | draw4_build.md › scoring › Verified, not blocking | open |
| D4-SC-NB5 | benchmark `cohort_label`, `parse_cohort` | A pv that contains '@' does not round-trip. This cannot happen with hex stamps. | draw4_build.md › scoring › Verified, not blocking | open (the `parse_cohort` docstring states that it cannot happen) |
| D4-SC-NB6 | benchmark `_ab_arm_is_real` | These still pass: `a.ab = 'off'`, setattr, a local `plan` shadow, and with/try blocks that return. A second binding gets the misleading message "never hands". | draw4_build.md › scoring › Verified, not blocking | open |
| D4-SC-NB7 | benchmark `rank_key` docstring | An empty card outranks P+P+P+U, and the docstring does not say so. | draw4_build.md › scoring › Verified, not blocking | partly fixed (draw 5): the docstring says P+P+P+U ranks below P. It does not say P+P+P+U ranks below an empty card |
| D4-SC-NB8 | forge/tests/test_benchmark.py | No test fails when any of 12 rules is removed: mdr scope, the "within cell (D28)" lines, seen_until_et, not_bounded_by_now, the -inf/nan mapping, the coverage gap's `since` filter, the `"V@"` check, the gates-dict filter, no meaning gap when 0 generated alphas, parse_known_args' same-parser check, nested-def binding counts, and the fcntl lock. | draw4_build.md › scoring › Verified, not blocking | open (not re-run as mutants; grep finds no test naming most of them, and only +inf of the inf/nan mapping is tested) |
| D4-SC-NB9 | benchmark D27 limit paragraph | `load_inputs` stats the journal after reading it, and nothing states the assumption that the POST logs are at least as fresh. | draw4_build.md › scoring › Verified, not blocking | open |
| D4-SC-XM1 | tools/ci_gate.py `record_golden`, `record_refusal` | The golden could not be re-recorded by the tool in either order. | draw4_build.md › scoring › Cross-module | fixed (draw 5) as state: the golden on disk matches the current scorer, fixture and closure. How it was recorded (the refusal route) is not re-verified |
| D4-SC-XM2 | vps/wq-judge.sh | The script counted success as exactly one more ledger line. | draw4_build.md › scoring › Cross-module | fixed (draw 5): success is read from benchmark's stderr |
| D4-SC-XM3 | 00_agreements D41 | No text authorised "at most one card per (cohort, graded ET day, host)". | draw4_build.md › scoring › Cross-module | decided (orchestrator decision recorded with D43–D46) |
| D4-SC-XM4 | benchmark `render_compare` | The verdict printed before D33's three cross-time confounds. | draw4_build.md › scoring › Cross-module | superseded (D47 replaced D33). `COMPARE_IS_NOT_GATE3` now prints before the verdict |

### 1c. Release (deploy.py, ci_publish.py, the judge's unit files)

| id | file / function | defect | evidence | status |
|---|---|---|---|---|
| D4-RL-1 | deploy `_push_inner`, `watch`; benchmark readers | SERIOUS: push advertised `deploy.py watch`, and the judge misread every watch row. | draw4_build.md › release › Defects 1; R1 | fixed (draw 5): the `next:` line is gone; `judge_maps_watch_rows` refuses unless the target's judge maps the rows; the outcome is renamed `watch_interrupted` |
| D4-RL-2 | deploy `other_operator_busy` | SERIOUS: only the literal "active" counted as busy, and oneshot units never print it. | draw4_build.md › release › Defects 2; R2 | fixed (draw 5): `_NOT_RUNNING`; `_watch_rollback` calls the check; the wq-judge.service header is corrected |
| D4-RL-3 | deploy D16 comment | SERIOUS: the watch trigger fired on 23 of the incumbent's 181 rounds, and no text stated that rate. | draw4_build.md › release › Defects 3; R3 | decided (D43); the section comment above `LOOP_LOG` states the base rate, the 09-06 cluster and the submit-before-STOP_FORGE limit |
| D4-RL-4 | deploy `_push_inner` live_at | live_at was set before `start_units`. | draw4_build.md › release › Defects 4 | fixed (draw 5) |
| D4-RL-5 | deploy `_push_inner` docstring; stage-0d banner | The texts said a refused push only reads the target. | draw4_build.md › release › Defects 5 | fixed (draw 5) as text. Its test cannot catch the ordering (D5-RL-3), and one sentence is still false (D5-RL-7) |
| D4-RL-6 | deploy `status` | status predicted the wrong stamp when a manifest has a claim but no hashes map. | draw4_build.md › release › Defects 6 | fixed (draw 5): `_manifest_claim` |
| D4-RL-7 | vps/wq-judge.sh | Two correct outcomes were read as failures (a same-day repeat, and a repaired cut-short line). | draw4_build.md › release › Defects 7 | fixed (draw 5): the stderr rule; the test_deploy parametrised cases |
| D4-RL-8 | deploy `_watch_inner`, `_watch_rollback` | The watch had no age limit, no busy check before its rollback, and could watch the same push again. | draw4_build.md › release › Defects 8 | fixed (draw 5): `WATCH_MAX_AGE_S`, the already-watched refusal, `other_operator_busy` |
| D4-RL-9 | deploy `_watch_rollback`, `_record_watch` | An interrupt during quiesce wrote a row with no `undo`. | draw4_build.md › release › Defects 9 | fixed (draw 5): `undo = "quiesce_interrupted"` |
| D4-RL-10 | tools/tests/test_deploy.py, test_ci_publish.py | Six mutants (a)–(f) survived, and one status test read the desk's real ledgers. | draw4_build.md › release › Defects 10; R5 | fixed (draw 5): the named tests for 10(a)–(f), `test_r10d_…`, and the autouse `_never_the_desks_ledger` |
| D4-RL-11 | deploy `_target_manifest` | RecursionError escaped on a too-deep DEPLOYED.json. | draw4_build.md › release › Defects 11 | fixed (draw 5) |
| D4-RL-12a | deploy D16 comment | The comment said "179 rounds", but its counts sum to 178. | draw4_build.md › release › Defects 12(a) | fixed (draw 5) |
| D4-RL-12b | deploy DEPLOY_LOG NOTE | The note said dora lacks interrupted. That was stale. | draw4_build.md › release › Defects 12(b) | fixed (draw 5) |
| D4-RL-12c | deploy `PIPELINE_EXCLUDED` wq-judge.sh | The note said "two files" name cards.jsonl; six do. | draw4_build.md › release › Defects 12(c) | fixed (draw 5) |
| D4-RL-12d | deploy `LIBRARY_DIRS` comment | The comment said staged/ is never touched; push can copy a dev-tree staged YAML over the target's. | draw4_build.md › release › Defects 12(d) | fixed (draw 5) |
| D4-RL-12e | deploy D40 comment | The comment did not name promote_staged.py. | draw4_build.md › release › Defects 12(e) | fixed (draw 5) |
| D4-RL-S1 | deploy `remote_log_markers` | SUSPECTED: `grep -b` ran without `-a`. | draw4_build.md › release › SUSPECTED | fixed (draw 5) |
| D4-RL-S2 | deploy `_remote` | SUSPECTED: ssh inherited the terminal's stdin during watch. | draw4_build.md › release › SUSPECTED | fixed (draw 5): `input=stdin`; `_remote_text` uses DEVNULL |
| D4-RL-S3 | deploy `_forge_env_from` | SUSPECTED: a FORGE_ARGS carrying `--seed` would redirect the smoke's plan file. | draw4_build.md › release › SUSPECTED | fixed (draw 5): refused |
| D4-RL-S4 | the remote quiesce | SUSPECTED: what the remote quiesce does after the client dies. MECHANISM: UNKNOWN. | draw4_build.md › release › SUSPECTED | open |
| D4-RL-D1 | vps/wq-forge-tests.sh in the id | DECISION: the file was in the pipeline id, and no decision named it. | draw4_build.md › release › Decisions | decided (orchestrator decision under D46); `PIPELINE_EXCLUDED` holds it |
| D4-RL-D2 | pre-ledger row 8f8b7517b8598d07 | DECISION: the row stayed unreconciled. | draw4_build.md › release › Decisions | decided (orchestrator decision under D46); the residual is R3-m9 |
| D4-RL-D3 | D40 against promote_staged on the host | DECISION: whether to refuse, require a flag, or accept the deletion. | draw4_build.md › release › Decisions | decided (D44): `--delete-unlisted-library` |
| D4-RL-D4 | the D16 trigger | DECISION: the trigger goes to Khoa as a tick. | draw4_build.md › release › Decisions | decided (D43) |
| D4-RL-P | golden / publish record | Push prerequisite: re-record the golden with `--split-golden` and publish it (M9-NL). | draw4_build.md › release › Push prerequisites | open (dup of D4-PL-P8) |

### 1d. CI (ci_gate.py, ci_fixture.py, ci.yml)

| id | file / function | defect | evidence | status |
|---|---|---|---|---|
| D4-CI-1 | tools/ci_fixture.py `case_cohorts` | SERIOUS: the D30 marker-stamp clause moved no case. | draw4_build.md › ci › Defects 1; C1 | fixed (draw 5): rows stamped unknown/ambiguous; a test_ci_gate MUTANTS entry drops the STAMP_MARKERS clause |
| D4-CI-2 | ci_gate module and `check_tests`/`known_red_verdict` texts | "The whole suite" claimed more than `run_incomplete` reads; three narrowing forms passed. | draw4_build.md › ci › Defects 2; C2 | partly fixed (draw 5): `-o` overrides; the texts now say "collected … counted". The remaining overclaims and narrowers are D5-CI-1 |
| D4-CI-3 | ci_gate `known_red_verdict` | A result with no `incomplete` key read as complete. | draw4_build.md › ci › Defects 3; C3 | fixed (draw 5). A value of `incomplete: None` is D5-CI-3 |
| D4-CI-4 | ci_gate `_argv_elements`, `check_no_live` | A self-referential argv binding crashed the scan with RecursionError. | draw4_build.md › ci › Defects 4; C4 | fixed (draw 5): the `seen` set; the per-file handler catches RecursionError |
| D4-CI-5 | tools/tests/test_ci_gate.py | Mutants K1–K6 survived. | draw4_build.md › ci › Defects 5; C5 | fixed (draw 5): the tests commented K1–K6 |
| D4-CI-6 | ci_gate `_SPAWN*`, `_LAUNCHER`, `_resolve_script`; ci_fixture `_sys_names` | Several script and template forms were not read, the _SPAWN comment was false, and a sys.path alias was dropped. | draw4_build.md › ci › Defects 6; C6 | fixed (draw 5) for every form listed. Newer residuals are D5-CI-6, D5-CI-7 and D5-X-C8 |
| D4-CI-7 | ci_gate `_template_passes` | Prose f-strings that start with a value were flagged. | draw4_build.md › ci › Defects 7 | fixed (draw 5): the rule is now applied per command |
| D4-CI-8a | ci_gate `run_incomplete`; ci_known_red.json | The texts said "more deselected", but the code tests `!=`. | draw4_build.md › ci › Defects 8(a) | fixed (draw 5) |
| D4-CI-8b | ci_fixture docstring | The SERIOUS 4 bullet named case_rank's "U". | draw4_build.md › ci › Defects 8(b) | fixed (draw 5) |
| D4-CI-8c | ci_fixture docstring; MUTANTS | "The case must see": MUTANTS only asserted that SOME case moves. | draw4_build.md › ci › Defects 8(c) | fixed (draw 5): each entry now names the case it must move |
| D4-CI-8d | test_ci_gate `DECISIONS_LITERAL` | Entries that no tick settles were listed as "decisions ticked". | draw4_build.md › ci › Defects 8(d) | partly fixed (draw 5): `READINGS_LITERAL` is split out. Two scorer readings are still listed as decisions (D5-CI-12) |
| D4-CI-8e | test_ci_gate import-closure test | The test cited layered_alpha.py by line number. | draw4_build.md › ci › Defects 8(e) | fixed (draw 5) |
| D4-CI-9 | .github/workflows/ci.yml | SUSPECTED: pytest was not pinned. | draw4_build.md › ci › Defects 9 | fixed (draw 5): `pytest==9.1.1` and `PYTEST_MEASURED`. The other unpinned tools are R3-m14 |
| D4-CI-X1 | golden re-record, two commits | Re-record in two steps and commit each one on its own. | draw4_build.md › ci › Cross-module X1 | open (the CI checkout is still at 1fce953; dup of D4-PL-P8) |
| D4-CI-X2 | tools/ci_classify.py `run_arm` | run_arm ran pytest with the full environment and `-q`, and read no completeness. | draw4_build.md › ci › Cross-module X2 | fixed (draw 5) |
| D4-CI-X3 | notify_lint exemption | The NO_LIVE_EXEMPT entry was waiting on a tick or on a token build. | draw4_build.md › ci › Cross-module X3 | fixed (draw 5): the token is assembled and `NO_LIVE_EXEMPT = {}` |

---

## 2. `audits/architecture_round3.md` (MINOR, SUSPECTED, N, m, X)

| id | file / function | defect | evidence | status |
|---|---|---|---|---|
| R3-N1 | benchmark `_held_next`, `open_ticks` | D7's "held" still means ≥ 1 proven submission in the next window. The statistician's probabilities (0.335, 0.753, 0.892) are not on the tick. | architecture_round3.md › Earlier fix did not land › N1 | open (waiting for Khoa's tick) |
| R3-N2 | deploy `UNITS` comment | The comment claimed that nothing runs the new code before the smoke. | architecture_round3.md › N2 | fixed (draw 5): the comment now names wq-mint, wq-watch, wq-auth and wq-outbox |
| R3-N3 | deploy (no lock); vps/wq-judge.sh | There is no deploy lock. The judge takes no lock and checks no STOP_FORGE, and `other_operator_busy` is read once. | architecture_round3.md › N3 | open (grep finds no flock in deploy.py; wq-judge.sh is unchanged in this respect). A related SERIOUS is D5-X-RL1 |
| R3-m1 | benchmark `provenance` | The deploy ledger is unbounded in time and is not listed in `not_bounded_by_now`. | architecture_round3.md › m1 | open |
| R3-m2 | benchmark `rank_key` docstring | D25's "monotone" fails through the neighbour pool, and no text names that route. | architecture_round3.md › m2 | open |
| R3-m3 | benchmark `compare` → `minimum_detectable_ratio` | The printed MDR uses the pooled observed rate, so it moves with B's result. | architecture_round3.md › m3 | partly fixed (draw 5): `arms_mdr` (D47) uses arm A's rate. `compare()` still passes the pooled base |
| R3-m4 | benchmark D28 direction rule | The all-cells-agree rule loses power once events spread across cells. | architecture_round3.md › m4 | open: the power simulation is in `_arms_decision`'s docstring, and `open_ticks` lists "D47 as read here". No Khoa tick yet |
| R3-m5 | tools/ci_known_red.json | D23's allowance is keyed on a count that moves with the journal ("20 journalled warnings"). | architecture_round3.md › m5 | open |
| R3-m6 | forge/runner.py `run_config` | The hash is over raw parsed strings, not a normalised argv. | architecture_round3.md › m6 | open |
| R3-m7 | benchmark `record_key`, `main` | The first card of the day wins, `--record --no-drill` is allowed, and the key ignores run_drill. | architecture_round3.md › m7 | open |
| R3-m8 | tools/ci_publish.py `main` | Abbreviated flags were accepted (`--spl`, `--no-p`). | architecture_round3.md › m8 | fixed (draw 5): `allow_abbrev=False`; `test_m8_a_flag_that_relaxes_a_refusal_is_typed_whole` |
| R3-m9 | 00_agreements D46 note; deploy RECONCILED comment | The re-appended first row cannot give ec6a5cd75d58fea2 an exposure start, and the recorded time "06:24 +07" is wrong. | architecture_round3.md › m9 | partly fixed (draw 5): the deploy.py comment states 06:24 UTC and leaves the choice to Khoa. 00_agreements still says "06:24 +07", and the choice is still open |
| R3-m10 | tools/recover_harvest.py; DEPLOYED.json; vps/*_run.sh | Live code is in no repository, the 43-file list is not recorded, and the arm drivers are not in PLAN. | architecture_round3.md › m10 | open (`git ls-files` finds no recover_harvest.py in the dev repo or in the CI checkout) |
| R3-m11 | vps/wq-judge.service | The unit had no TimeoutStartSec. | architecture_round3.md › m11 | fixed (draw 5): `TimeoutStartSec=1h` |
| R3-m12 | benchmark `dora` lead time | Lead time can never be measured, because every row is git_dirty. | architecture_round3.md › m12 | open |
| R3-m13 | deploy `manifest`; ci_publish `record_publish` | Provenance is thin: DEPLOYED.json has no ci_commit and no publish reference, and the record has no test counts or interpreter. | architecture_round3.md › m13 | open |
| R3-m14 | ci.yml; ci_publish `ensure_checkout`; requirements-lock.txt | The toolchain is unpinned, and the classifier's two arms differ. | architecture_round3.md › m14 | partly fixed (draw 5): pytest is pinned in ci.yml. pyyaml and requests are unpinned there, `ensure_checkout` is unpinned, the actions are referenced by tag, and requirements-lock.txt is untracked |
| R3-m15 | ci_publish `main` `--split-golden` | Two commits are made in one run and one push, so the first commit is red by construction. | architecture_round3.md › m15 | open |
| R3-m16 | tools/tests/test_layered_sim.py `test_a_crash_mid_batch_loses_no_journalled_row` | `LS.ROOT` is not patched, and the test leaves `state/simrunning/crash.json`. | architecture_round3.md › m16 | open (the file is still on the Mac, dated 09-23 18:05) |
| R3-m17 | ci_gate `check_branch_drill` | The hermetic tier prints `[PASS] branch-drill NOT RUN`. | architecture_round3.md › m17 | open (dup of D5-CI-13) |
| R3-m18 | forge/meaning.py G5 | G5 can fail only in narrow cases, and the claim was not narrowed. | architecture_round3.md › m18 | fixed (draw 5): the "NARROWED CLAIM" in meaning.py |
| R3-m19 | forge/harvest.py `quarantine` | The D36 quarantine charges a refusal to the first leg's `meta.field`. | architecture_round3.md › m19 | open |
| R3-m20 | docs/evalharness/01_architecture.md | Draw 4 has no row for D43–D46. | architecture_round3.md › m20 | open (no D43–D53 row; the file is dated 20:11) |
| R3-X1 | D33/D47 arms; D36 plan-time D18 | SUSPECTED: the two arms may admit different events. | architecture_round3.md › SUSPECTED X1 | open (also D5-GE-N4) |
| R3-X2 | benchmark `neighbourhood_stability` | SUSPECTED: the pipeline chooses the neighbour step. | architecture_round3.md › SUSPECTED X2 | partly fixed (draw 5): forge/gen/repair.py draws neighbour steps from the pre-registered SETTINGS levels. The judge still reads any one-knob sibling |
| R3-X3 | forge/runner.py `note_run_config` | SUSPECTED: D45 would fire on the push's own smoke. | architecture_round3.md › SUSPECTED X3 | fixed (draw 5): only a live start is recorded |
| R3-X4 | forge/meaning.py G8 journal clause | SUSPECTED: the clause could collide with the alpha's own id. | architecture_round3.md › SUSPECTED X4 | fixed (draw 5): the clause excludes the alpha's own rows |
| R3-X5 | vps/wq-judge.service | SUSPECTED: a hung judge. | architecture_round3.md › SUSPECTED X5 | partly fixed (draw 5): `TimeoutStartSec=1h` bounds a hang. No hang source is identified |
| R3-D1 | deploy `loop_closure` | MINOR (Disclosures): each call wrote .pyc files into the tree it inspects. | architecture_round3.md › Disclosures | fixed (draw 5): the probe runs with `-B` |

---

## 3. `audits/draw5_build.md` "MINOR for backlog"

Unless a row says otherwise, each row is `open` because its files are byte-identical to the audited bytes (see
"How each status was checked").

### 3a. Meaning (forge/meaning.py)

| id | file / function | defect | evidence | status |
|---|---|---|---|---|
| D5-ME-M1 | meaning `append`, `check_row` | A null row (catalogue None, or a skewed scored_at) freezes an alpha, because the earliest row wins. | draw5_build.md › meaning › MINOR M1 | open |
| D5-ME-M2 | meaning `check_row` | `_HEX64.match` accepts a trailing newline, and scored_at of 10**400 raises OverflowError. | draw5_build.md › meaning › MINOR M2 | open |
| D5-ME-M3 | meaning `_text_gates` | The `in (True, False)` test copies 1 and 0, and `check_row` then refuses the row. | draw5_build.md › meaning › MINOR M3 | open |
| D5-ME-M4 | meaning `score` | A list hypothesis or a non-dict settings raises instead of reading null. | draw5_build.md › meaning › MINOR M4 | open |
| D5-ME-M5 | meaning G8 journal clause | A miss on the candidate-id lookup reads True ("no earlier alpha"). | draw5_build.md › meaning › MINOR M5 | open |
| D5-ME-M6 | meaning `load_catalogue(only=…)` | A cut-down catalogue cannot be told apart from a full one, so G7 reads False. | draw5_build.md › meaning › MINOR M6 | open |
| D5-ME-M7 | meaning G5 / `legs_of` | A negative-constant denominator is not flipped, and multiply by -1 leaves the leg unchecked. | draw5_build.md › meaning › MINOR M7 | open |
| D5-ME-M8 | meaning G6 | False reason texts: "one leg" for two-leg forms, and "no label" for a labelled denominator. | draw5_build.md › meaning › MINOR M8 | open |
| D5-ME-M9 | forge/tests/test_meaning.py | Seven mutants survive, and the purity test misses `io.open` and `time.time`. | draw5_build.md › meaning › MINOR M9 | open |
| D5-ME-M10 | test_meaning `test_d52_on_the_desks_own_files_when_they_are_present` | A data-drift pin runs in the deploy smoke, and a torn submitted.jsonl line would roll back a deploy. | draw5_build.md › meaning › MINOR M10 | open (the adjudicator wants it fixed before the next deploy smoke) |
| D5-ME-M11 | meaning docstrings | Five text claims that the code does not match, (a)–(e). | draw5_build.md › meaning › MINOR M11 | open |
| D5-ME-M12 | meaning `load_ledgers` | Every absent source reads as empty, which is a vacuous pass. | draw5_build.md › meaning › MINOR M12 | open |
| D5-ME-M13 | builder's report | "37 of 37 mutants" and "load_composite refuses gates 1-3" are corrections owed to the report, not to the files. | draw5_build.md › meaning › MINOR M13 | open (report text only) |
| D5-ME-M14 | forge/labels.py `build` | SUSPECTED: an in-place write can expose partial labels. | draw5_build.md › meaning › MINOR M14 | open (labels.py is dated 09-07) |
| D5-ME-M15 | meaning `legs_of` | SUSPECTED: split-multiply operands take the parent's orientation. | draw5_build.md › meaning › MINOR M15 | open |

### 3b. Pipeline (runner.py, recover_orphans.py, notify_lint.py)

| id | file / function | defect | evidence | status |
|---|---|---|---|---|
| D5-PL-M1 | runner `_VERSION` comment; test_runner `test_a_manifest_too_deep_to_parse_is_no_claim` | The P4 text is false now: a too-deep target reads `<on_disk>+untracked`. | draw5_build.md › pipeline › MINOR M1 | open (read: the text still says `unknown`) |
| D5-PL-M2 | runner D30/D45 comments | The comments predate D50 (forge.env). | draw5_build.md › pipeline › MINOR M2 | open |
| D5-PL-M3 | runner `RUN_CONFIG_EXCLUDED['plan']` | The pow.json/c11.json claim is wrong: they had different N. | draw5_build.md › pipeline › MINOR M3 | open |
| D5-PL-M4 | runner `stamp` docstring; the `_PLAN_META['pow']` fixture | No real plan writer produces the "copied arm" case. | draw5_build.md › pipeline › MINOR M4 | open |
| D5-PL-M5 | runner `note_run_config` | "Never a guess" holds only for the new cohort. | draw5_build.md › pipeline › MINOR M5 | open |
| D5-PL-M6 | test_runner `test_two_starts_at_once_record_one_transition` | The test quotes "atomically" from no decision on file. | draw5_build.md › pipeline › MINOR M6 | open |
| D5-PL-M7 | runner `record_run_config` | A line too deep to parse raises RecursionError, and D45 logging stops. | draw5_build.md › pipeline › MINOR M7 | open (read: it catches `ValueError` only) |
| D5-PL-M8 | test_runner / test_recover_orphans | Eight mutants survive (M14, M15, M16, M06, M51, M52, M24, M25). | draw5_build.md › pipeline › MINOR M8 | open |
| D5-PL-M9 | runner `main`; recover_orphans `load_plans` | A dry copy loses the pair for a later live round of the same construction. | draw5_build.md › pipeline › MINOR M9 | open (the VPS move is Khoa's call) |
| D5-PL-M10 | recover_orphans `RUNNER_PLAN` comment | Re-dispatching a numeric-named plan returns (ambiguous, ambiguous), and the limit is not named. | draw5_build.md › pipeline › MINOR M10 | open |
| D5-PL-M11 | recover_orphans `match` A11 branch | gen_state follows index order. | draw5_build.md › pipeline › MINOR M11 | open |
| D5-PL-M12 | runner `main` | A live round with nothing to simulate still writes a D45 row. What D45 intends is UNKNOWN. | draw5_build.md › pipeline › MINOR M12 | open (read: `note_run_config` runs before the empty-plan return) |
| D5-PL-M13 | 04_passfirst_design.md §5 | S15's second half, the ROUND_KEYS row, is missing. | draw5_build.md › pipeline › MINOR M13 | open (the file is dated 16:52) |
| D5-PL-M14 | D47 arm under `--ab new` | forge.env ships `--ab new`, so the arms read current/new and compare_arms reads no-data. | draw5_build.md › pipeline › MINOR M14 | open (a decision) |
| D5-PL-M15 | 00_agreements D45 | The "live start only" reading is not on file. | draw5_build.md › pipeline › MINOR M15 | open |
| D5-PL-M16 | runner `plan_sha256` | It hashes the raw file, and pow_pairs writes `made_at`. | draw5_build.md › pipeline › MINOR M16 | open |
| D5-PL-M17 | runner D45 host key; run_config_log copy | A hostname change keeps the old host's days, and nothing copies the log off the VPS. | draw5_build.md › pipeline › MINOR M17 | open |
| D5-PL-M18 | ci_gate `NO_LIVE_EXEMPT`; notify_lint comment | Stale exemption text. | draw5_build.md › pipeline › MINOR M18 | partly fixed (draw 5, by the later ci build): `NO_LIVE_EXEMPT = {}` and the OPEN ITEM comment is gone. notify_lint's comment still does not say the exemption is gone |
| D5-PL-S1 | D45 × D47 | SUSPECTED: if each arm has its own argv, every day reads as mixed and both cohorts count 0 days. | draw5_build.md › pipeline › MINOR SUSPECTED | open (the scoring adjudicator kept the same item: draw5_build.md › scoring › Adjudication, D45 x D47) |

### 3c. Gen (forge/gen/*)

| id | file / function | defect | evidence | status |
|---|---|---|---|---|
| D5-GE-N1 | gen `propose` by_cell / `want` | Repairs and neighbours are not charged to their cell. | draw5_build.md › gen › MINOR N1 | open |
| D5-GE-N2 | gen `propose` handed | Handed rows are not filtered or deduplicated, so a library row gets neighbours stamped 'gen'. | draw5_build.md › gen › MINOR N2 | open |
| D5-GE-N3 | gen `repair.neighbours` | A neighbour shortfall is silent, because seen_ids includes rows that never got a verdict. | draw5_build.md › gen › MINOR N3 | open |
| D5-GE-N4 | gen tick queue | Choices that no tick names: the D36×D51 bypass and neighbour cascade, the uncapped OPEN family, D47 per-round arms, and round-3 X1. | draw5_build.md › gen › MINOR N4 | open (a decision) |
| D5-GE-N5 | forge/tests/test_gen_* | Mutants R07, R08, Q06, T01, T02 and S03 survive, plus the exec lens's list. '0 exact repeats' is true by construction. | draw5_build.md › gen › MINOR N5 | open |
| D5-GE-N6 | gen docstrings | Nine false or stale texts (posterior, propose, families, state, productions, FieldPool, the report). | draw5_build.md › gen › MINOR N6 | open |
| D5-GE-N7 | gen harvest-pass on d0 | D0_SUBMISSION reads PENDING, so harvest-pass and the D37 trigger never fire on d0. | draw5_build.md › gen › MINOR N7 | open |
| D5-GE-N8 | gen `spend` import | Importing self_corr_predict at module level changes sys.path. | draw5_build.md › gen › MINOR N8 | open |
| D5-GE-N9 | benchmark `_modules_with_a_real_test`, `import_cycles` | Axis 3 cannot see forge/gen. | draw5_build.md › gen › MINOR N9 | open (read: it still globs `forge/*.py`) |
| D5-GE-N10 | gen spend/allocator, pnl_stops, cells, effective/typed | Four small code items. | draw5_build.md › gen › MINOR N10 | open |
| D5-GE-N11 | runner `_construction`; field_datasets | Stage-4 interface: recipe wrappers run after gen's checks, and None falls back to a regex. | draw5_build.md › gen › MINOR N11 | open |
| D5-GE-N12 | gen (builder's list) | TIER_U levels None, an unbounded trigger queue, a per-round coin control, and unticked draw choices. | draw5_build.md › gen › MINOR N12 | open |
| D5-GE-S1 | D37 read-out | SUSPECTED: it must be intention-to-treat by coin. Heads that D36 refused are not counted. | draw5_build.md › gen › MINOR SUSPECTED | open |
| D5-GE-S2 | gen draws | SUSPECTED: later draws can reach a control-arm formula. | draw5_build.md › gen › MINOR SUSPECTED | open |
| D5-GE-S3 | allocate `cold_cells` | SUSPECTED: it counts gen rows, a confound for D47. | draw5_build.md › gen › MINOR SUSPECTED | open |
| D5-GE-S4 | fingerprint family | SUSPECTED: a leg and its `(1 - x)` flip share one family. | draw5_build.md › gen › MINOR SUSPECTED | open |
| D5-GE-S5 | TIER_U dispersion legs | SUSPECTED: their orientation is labelled as coming from the description (stage-3 G5). | draw5_build.md › gen › MINOR SUSPECTED | open |

### 3d. Scoring (benchmark.py)

| id | file / function | defect | evidence | status |
|---|---|---|---|---|
| D5-SC-M1 | test_benchmark dora | dora is unpinned beyond watch_rolled_back (C01, C02, C07). | draw5_build.md › scoring › MINOR M1 | open |
| D5-SC-M2 | test_benchmark WATCH_KEEPS_RUNNING | The test iterates the module's own tuple, so B03 survives. | draw5_build.md › scoring › MINOR M2 | open |
| D5-SC-M3 | benchmark `cohort_live_days` | A day on which a second host held the cohort part of the day is counted (A19). The docstring bullets overlap, and its rationale is false. | draw5_build.md › scoring › MINOR M3 | open |
| D5-SC-M4 | test_benchmark | The "log rows after now are not seen" filter cannot be observed (A09). | draw5_build.md › scoring › MINOR M4 | open |
| D5-SC-M5 | test_benchmark `formula_sha` | Whitespace handling is unpinned (E08). | draw5_build.md › scoring › MINOR M5 | open |
| D5-SC-M6 | test_benchmark reduced-rows test | Truncation and seed are missed (F05, F07). | draw5_build.md › scoring › MINOR M6 | open |
| D5-SC-M7 | test_benchmark `compare_arms` | Paths are untested (I11, I12, I13). | draw5_build.md › scoring › MINOR M7 | open |
| D5-SC-M8 | test_benchmark | Boundary mutants carried from auditor 2, and a loose MDR tolerance. Not re-run by the adjudicator. | draw5_build.md › scoring › MINOR M8 | open |
| D5-SC-M9 | benchmark `live_days` | A version put back by watch_rolled_back reads exposure unknown when no deployed row names it. | draw5_build.md › scoring › MINOR M9 | open |
| D5-SC-M10 | benchmark `dora`; `_is_watch`/`live_days` docstrings | watch_not_rolled_back is a change failure and watch_interrupted is not, which is an unrecorded reading. The docstrings name `interrupted`. | draw5_build.md › scoring › MINOR M10 | open (read: `live_days` still lists "interrupted") |
| D5-SC-M11 | benchmark `load_run_config_log`, `load_meaning`, `load_deploys` | These glob their path, so a `[1]` directory reads 0 rows. | draw5_build.md › scoring › MINOR M11 | open |
| D5-SC-M12 | benchmark `_arms_strata` | Marker-run_config rows are dropped uncounted. | draw5_build.md › scoring › MINOR M12 | open |
| D5-SC-M13 | benchmark `compare_arms` | It covers one pipeline_version, so every deploy restarts the MIN_SHARED_DAYS clock. This is unstated. | draw5_build.md › scoring › MINOR M13 | open |
| D5-SC-M14 | benchmark `MIN_SHARED_DAYS` | No decision on file sets 5. | draw5_build.md › scoring › MINOR M14 | open |
| D5-SC-M15 | benchmark `ARMS` comment | The comment omits `--ab`. | draw5_build.md › scoring › MINOR M15 | open (dup of D5-PL-M14) |
| D5-SC-M16 | benchmark `compare` | It still returns better/worse, and the caveat sits in a separate key. | draw5_build.md › scoring › MINOR M16 | open |
| D5-SC-M17 | benchmark coverage_gap note | The note says the rate counts the gap days, but `empty` is never intersected with the rate's days. | draw5_build.md › scoring › MINOR M17 | open |
| D5-SC-M18 | benchmark `graded_by_axis1_not_in_rate` | It says "not live" but also holds D45's excluded and unknown days. | draw5_build.md › scoring › MINOR M18 | open |
| D5-SC-M19 | benchmark D45 "unknown" days | These include days that the log attributes to another run_config. | draw5_build.md › scoring › MINOR M19 | open |
| D5-SC-M20 | benchmark `RUN_CONFIG_LOG` comment | The comment says "no runner writes it yet". | draw5_build.md › scoring › MINOR M20 | open (read) |
| D5-SC-M21 | benchmark `compare` design string | It picks one mechanism ("independent alphas"), against RULE 0 #3. | draw5_build.md › scoring › MINOR M21 | open (read) |
| D5-SC-M22 | benchmark `COMPARE_IS_NOT_GATE3` | It attributes 0.49–0.56 to the bootstrap. | draw5_build.md › scoring › MINOR M22 | open |
| D5-SC-M23 | benchmark POST_HORIZON tick; `rank_key` | Both understate D49: a late POST can flip floor_met and the verdict. | draw5_build.md › scoring › MINOR M23 | open |
| D5-SC-M24 | test_benchmark `_day_heterogeneous` docstring | The stated rates are not what the code draws. | draw5_build.md › scoring › MINOR M24 | open |
| D5-SC-M25 | test_benchmark size test | The test is model-based, not F1's real-data placebo, and its docstring does not say so. | draw5_build.md › scoring › MINOR M25 | open |
| D5-SC-M26 | benchmark `cohort_live_days` | That a (pv, None) cohort keeps all of its pv's days is a module reading, and it is not in open_ticks. | draw5_build.md › scoring › MINOR M26 | open |
| D5-SC-M27 | benchmark `MEANING_DECIDABLE` comment | The comment reads G4 opposite to D52. | draw5_build.md › scoring › MINOR M27 | open (read; dup of D5-X-ME-R1) |
| D5-SC-S1 | benchmark cohort pool × D51 | SUSPECTED: neighbours simulated after a deploy or a forge.env change fall outside the cohort pool, so the alpha reads UNPROVEN. | draw5_build.md › scoring › MINOR SUSPECTED | open |

### 3e. Release (deploy.py, ci_publish.py, forge_loop.sh, forge.env, the judge's unit files)

| id | file / function | defect | evidence | status |
|---|---|---|---|---|
| D5-RL-1 | deploy `_forge_env_from` | The parser and bash disagree on CRLF, `\x0c` and `N=²` (splitlines, isdigit). | draw5_build.md › release › MINOR 1 | open |
| D5-RL-2 | deploy watch / probe | The watch can conclude before the background probe finishes (17 of 176 probes). | draw5_build.md › release › MINOR 2 | open |
| D5-RL-3 | test_deploy (release defect 5 test) | The test cannot catch the reconcile-order mutant RV25b. | draw5_build.md › release › MINOR 3 | open |
| D5-RL-4 | test_deploy d50 unit-file test | The test pins the current forge.env, not literals, so the first D50 flip breaks CI. | draw5_build.md › release › MINOR 4 | open |
| D5-RL-5 | deploy `_record_watch` after `_undo` | R1 residual: the row is appended after `_undo` restores a benchmark that was never probed. | draw5_build.md › release › MINOR 5 | open |
| D5-RL-6 | test_deploy | Surviving mutants measured by the exec lens (M71–M74, M67, M9, M35, M80, M39, M105, M18, M76a–d, M77, M86b, M13). | draw5_build.md › release › MINOR 6 | open |
| D5-RL-7 | deploy texts | Six texts that do not hold (the `_push_inner` docstring, `_READERS_PROBE`, the quota-sleep echo, install step 5, `--force` help, D44 counts). | draw5_build.md › release › MINOR 7 | open (read: "Nothing else changes before the swap" is still there) |
| D5-RL-8 | deploy SMOKE; forge_loop.sh | The import smoke skips mint_link, no test runs `bash -n`, and a `--plan` in forge.env leaves rounds inconclusive. | draw5_build.md › release › MINOR 8 | open |
| D5-RL-9 | deploy operator concurrency | wq-forge's activating window, the unmasked judge timer, and ROUNDS=1 driver crashes (the N3 class). | draw5_build.md › release › MINOR 9 | open |
| D5-RL-10 | runner `plan` quarantine read | D43 cannot tell a data-caused planner crash from a code crash, because harvest writes non-atomically. | draw5_build.md › release › MINOR 10 | open |
| D5-RL-11 | vps/wq-judge.service LIMITS | The figures were measured on benchmark 76c4dba8 and are not reconciled with round 3's 741 MB. | draw5_build.md › release › MINOR 11 | open (read: the header still cites 76c4dba8) |
| D5-RL-12 | deploy `_watch_timeout` | S4 is built as `timeout_cause` 'auth_dead', not as a distinct outcome. The orchestrator is to accept this or rename it. | draw5_build.md › release › MINOR 12 | open |
| D5-RL-Pa | orchestrator | The judge grades every cohort, and no decision is on file (01 §5 item 3). | draw5_build.md › release › Process items | open |
| D5-RL-Pb | orchestrator | D50's ROUNDS=1 exception is not recorded. | draw5_build.md › release › Process items | open (00_agreements has no such text) |
| D5-RL-Pc | docs/evalharness/backlog.md | The backlog did not exist, so round 3's items were recorded nowhere. | draw5_build.md › release › Process items | fixed: this file |
| D5-RL-Pd1 | runner `_VERSION` comment | Stale text on a too-deep manifest. | draw5_build.md › release › Process items | open (dup of D5-PL-M1) |
| D5-RL-Pd2 | benchmark `interrupted` docstrings | The docstrings name `interrupted` for a watch outcome. | draw5_build.md › release › Process items | open (dup of D5-SC-M10) |
| D5-RL-Pd3 | 01_architecture.md | `remote_production_args` appears 3 times; D50 removed it. | draw5_build.md › release › Process items | open (read: 3 hits) |
| D5-RL-Pd4 | 04_passfirst_design.md §7 | Stages 0d and 5(a) predate D50. | draw5_build.md › release › Process items | open (not re-read; the file is dated 16:52) |
| D5-RL-Pd5 | 00_agreements D46 note | "06:24 +07" should be 06:24 UTC. | draw5_build.md › release › Process items | open (read; dup of R3-m9) |

### 3f. CI (ci_gate.py, ci_fixture.py, ci_classify.py, ci.yml)

| id | file / function | defect | evidence | status |
|---|---|---|---|---|
| D5-CI-1 | ci_gate `PYTHON_FILES` comment, `known_red_verdict`, `NARROWING_NAMES` | Collection can still be narrowed (`norecursedirs`, `pytest_pycollect_makeitem`), and the texts overclaim. | draw5_build.md › ci › MINOR 1 | open |
| D5-CI-2 | ci_gate `run_incomplete` | A duplicated node id launders a NEW test. | draw5_build.md › ci › MINOR 2 | open |
| D5-CI-3 | ci_gate `known_red_verdict` | `incomplete: None` reads as complete. | draw5_build.md › ci › MINOR 3 | open (read: `elif result["incomplete"]`) |
| D5-CI-4 | ci_gate `collectable` | It reads True for `__test__ = False` and for a Test class with `__init__`. | draw5_build.md › ci › MINOR 4 | open |
| D5-CI-5 | test_ci_gate / test_ci_publish | Eleven surviving mutants, plus the exec lens's unrun list. | draw5_build.md › ci › MINOR 5 | open |
| D5-CI-6 | ci_gate `_SEPARATOR` | C6 regression: a backslash-newline template is no longer flagged. | draw5_build.md › ci › MINOR 6 | open |
| D5-CI-7 | ci_gate / ci_fixture | Unread forms that WHAT THIS IS NOT does not name: conditional rebinding, posix_spawn, pty.spawn, and `getattr(sys,"path")`. | draw5_build.md › ci › MINOR 7 | open |
| D5-CI-8 | ci_gate readers | Readers crash without naming a file (a non-UTF-8 workflow, deep ASTs, an unparsable fixture). They fail closed. | draw5_build.md › ci › MINOR 8 | open |
| D5-CI-9 | ci_gate `_argv_elements`, `_SH_AT_COMMAND` | Exponential slow paths that fail closed as hangs. | draw5_build.md › ci › MINOR 9 | open |
| D5-CI-10 | ci_gate `classify_test_files` (S6) | The code departs from round 3's fix without a tick (it auto-runs rather than blocks). There are listing-reason and `--ignore` issues. | draw5_build.md › ci › MINOR 10 | open (ticks for Khoa) |
| D5-CI-11 | ci_gate `record_golden`; ci_fixture readers | S7 partial: moved closure files that no case executes are not named, and the readers are monkeypatched, not injectable. | draw5_build.md › ci › MINOR 11 | open |
| D5-CI-12 | test_ci_gate `DECISIONS_LITERAL` | Two scorer readings sit among the ticks (four_shared_days, V@r2 known). | draw5_build.md › ci › MINOR 12 | open |
| D5-CI-13 | ci_gate / ci_publish / ci_fixture texts | Nine text defects, including the `check_branch_drill` [PASS] (R3-m17), the data_tier cut at 140 characters, and `route: "auto"`. | draw5_build.md › ci › MINOR 13 | open (read: `check_branch_drill` still returns ok True on NOT RUN) |
| D5-CI-14 | ci_known_red.json; `--deselect`; teardown count; `ensure_checkout` | Open, fail-closed items: m5, prefix deselect, the double count, unpinned pytest in ensure_checkout. | draw5_build.md › ci › MINOR 14 | open |

---

## 4. `audits/draw5_build.md`: items outside the MINOR lists (not backlog; listed so none is lost)

These block sign-off, or wait on a tick or on another owner. The backlog does not track them. They are listed
because a reader of this file should not assume they are closed.

| id | file / function | item | evidence | status |
|---|---|---|---|---|
| D5-X-GE-G1 | forge/gen/repair.py `existing_neighbours` | SERIOUS: D51 counts neighbours from every cohort, but the judge counts only the alpha's own. | draw5_build.md › gen › SERIOUS G1 | open |
| D5-X-GE-G2 | forge/tests/test_gen_* | SERIOUS: the orientation and theta_d draw rules have no test that fails without them (O1, O2, T1–T3). | draw5_build.md › gen › SERIOUS G2 | open |
| D5-X-GE-G3 | forge/gen/spend.py docstring; a Khoa tick | SERIOUS: the D36 count rules never reach 40 through draws (1,500 of 1,500 singletons). | draw5_build.md › gen › SERIOUS G3 | open |
| D5-X-SC-S1 | benchmark `compare_arms`, `JOURNAL_KEEP_META` | SERIOUS: the branch's own neighbour and repair rows are counted as arm-B output. | draw5_build.md › scoring › S1 | open (read: `JOURNAL_KEEP_META` has no gen_route) |
| D5-X-RL1 | deploy `_watch_rollback` | SERIOUS: the watch can roll back a push it is not watching. It re-reads no manifest. | draw5_build.md › release › Verdicts 1 | open (read: no `remote_manifest()` call in `_watch_rollback`) |
| D5-X-RL2 | tools/tests/test_ci_publish.py `_tests_result` | Push precondition: the fixture has no `incomplete` key, so the release suite is red. | draw5_build.md › release › Required first (2); ci › P1 | open |
| D5-X-C8 | ci_gate `_resolve_script`, `DEPLOYED_ROOT` | SERIOUS: check_no_live cannot see the loop script at its deployed path. | draw5_build.md › ci › Verdicts 2; C8 | open |
| D5-X-CI-P2 | tools/ci_data_bound.json | Push precondition: the tests_hash is stale, so the hosted tier blocks. | draw5_build.md › ci › P2 | open (the file is dated 09-23 12:40) |
| D5-X-CI-P3 | golden commits | Push precondition: commit X1's two golden steps separately. | draw5_build.md › ci › P3 | open (dup of D4-PL-P8) |
| D5-X-SC-CI | test_ci_gate MUTANTS anchors; the `credited` read | The CI hand-off routed from scoring. | draw5_build.md › scoring › Adjudication (CI hand-off) | open (not re-verified here; the draw-5 ci baseline listed only P1 as red) |
| D5-X-ME-T1 | forge/meaning.py `_g4` | Tick: G4 as the minimum, the maximum, or with denominators left out. | draw5_build.md › meaning › Ticks T1 | open |
| D5-X-ME-T2 | meaning G5 | Tick: a vacuous G5 reads true, not null. | draw5_build.md › meaning › Ticks T2 | open |
| D5-X-ME-T3 | meaning G7 | Tick: G7 checks existence only, and point-in-time is UNMEASURED. | draw5_build.md › meaning › Ticks T3 | open |
| D5-X-ME-T4 | meaning `append`, benchmark `meaning_index` | Tick: a corrected SCORER can never re-grade a pair. | draw5_build.md › meaning › Ticks T4 | open |
| D5-X-ME-R1 | benchmark `MEANING_DECIDABLE` comment | Routed: the comment reads G4 opposite to D52. | draw5_build.md › meaning › Routed | open (dup of D5-SC-M27) |
| D5-X-ME-R2 | benchmark `_standard_gate` | Routed: S8 item 4. `gen:` routing ignores `route`/`inherited_from`. | draw5_build.md › meaning › Routed | open (read: the `meaning_index` docstring lists it as NOT done) |
| D5-X-ME-R3 | tools/ci_fixture.py meaning rows | Routed: `route: "auto"` is outside meaning.ROUTES. | draw5_build.md › meaning › Routed | open (read; dup of D5-CI-13) |
| D5-X-ME-R4 | tools/funnel/precheck_lib.py `extract_fields_grammar` | Routed: filter/true/currency count as fields, so a one-field NO_GO family escapes precheck. | draw5_build.md › meaning › Routed | open (not re-read) |
| D5-X-ME-R5 | /opt/wq/state/alpha_hypotheses.jsonl | Routed: the file is absent on the host, so the NO_GO clause is vacuous there. | draw5_build.md › meaning › Routed | open (host not re-read) |

## 5. Found by the orchestrator outside the audits

| id | file / function | defect | evidence | status |
|---|---|---|---|---|
| O1 | tools/mint_link.py `mint(force=True)` / state/auth_status.json | A forced mint writes state/auth_link.txt but not state/auth_status.json, so the status file keeps the previous window's stage. At 22:09–22:13 +07 on 2026-09-23 it read `WINDOW_EXPIRED` for inq_…KUkx while the forced link inq_…Nk6 was tapped and the session was live ("TAPPED and saved: session live after 171s" in /tmp/mint_force_2209.log on the VPS). Any reader of the status file (monitors, the health report) takes a stale stage as the truth: the transient-read-as-truth class. | read-only ssh, 2026-09-23 22:13:57 +07 | open |
| O2 | workflow snapshot instructions (orchestrator) | Auditor snapshots excluded state/fetched/.git only; AI_Innovation_Atlas_data (10 GB) and cyberrisk (1.8 GB) were copied every time. About 310 repo copies reached 242 GB and filled the disk (4.1 GB free) on 2026-09-23 ~23:40 +07. All copies were deleted (218 at ~23:45, 92 at 02:05); the scratchpad is 2.4 GB. Future workflows copy code only and delete their snapshots per module. | `du -sh` of the session scratchpad before/after | fixed (process) |
