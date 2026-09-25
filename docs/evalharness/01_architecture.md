# evalharness — architecture, draw 1 (2026-09-23)

This is the first drawing, written to be attacked. D15 says it is finished when two consecutive
adversarial rounds find no new defect; one round has not yet run against it.

## 1. The three systems and what separates them

```
            ┌──────────────────────────── THE PIPELINE (what is judged) ────────────────────────────┐
            │  library YAML → planner → allocator → type gate → dispatcher → harvest → robustness   │
            │       ↑            │                                              │          │        │
            │   fingerprint ─────┘ (pre-sim novelty)                            ↓          ↓        │
            │                                                     correlation probe → submitter     │
            └────────────────────────────────────┬─────────────────────────────────────────────────┘
                                                 │ writes: journal, scored, corr, submit ledger
                                                 ↓
            ┌──────────────────── THE SCORECARD (forge/offline/benchmark.py) ──────────────────────┐
            │  axis 1 product      axis 2 throughput      axis 3 gearing                           │
            │  DSR · PBO ·         per 5,000 scored ·     fitness functions ·                      │
            │  neighbourhood ·     Wilson · families ·    DORA · branch drill                      │
            │  regime · 8 gates    diversity · repeat                                              │
            │                    ↓ hard floors, no compensation ↓                                  │
            │                 verdict PASS/FAIL  +  composite 0–100 (ranking only)                 │
            └────────────────────────────────────┬─────────────────────────────────────────────────┘
                                                 │ the composite is the gate's regression signal
                                                 ↓
            ┌──────────────────────── THE GATE (tools/ci_gate.py) ─────────────────────────────────┐
            │  no-live · schema · version · fitness · tests · regression                           │
            │        ↓ PASS                                                                        │
            │  tools/deploy.py: existence probe → snapshot → rsync → smoke → manifest → restart    │
            │        ↓ smoke red                                                                    │
            │  rollback: extract first, then remove only what was genuinely new                     │
            └──────────────────────────────────────────────────────────────────────────────────────┘
```

The separation that matters: **the thing judged never imports the thing judging it.** `forge/` has no
dependency on `benchmark.py` or `ci_gate.py`, so the scorecard cannot influence what it scores. The
arrow from the scorecard to the gate carries one number, the composite, and that number can only
block a merge — never change a simulation.

## 2. Why each piece is where it is

| piece | why not somewhere else |
|---|---|
| the scorecard reads FILES, not the live loop | the loop must be scoreable after the fact, from any machine, and a scorer that has to be running when the thing happens measures only what it was awake for |
| the gate is a Python module, not YAML steps | the same command must give the same verdict on a laptop, on the host and in Actions; a gate that only exists inside a CI runner teaches people to distrust it |
| the version is a content hash | a tag is a promise someone remembers to keep; the bytes are what ran. `/opt/wq` is not a git repo and drifted 13 days without anything reporting it |
| the version is stamped by the PLANNER | the alternative — attributing by time window — puts a hand-rsynced tree's alphas in the wrong bucket, which is exactly what this desk did for 13 days |
| deploy refuses while a round dispatches | swapping code under a live round produces alphas that no version can claim, which destroys D14 |
| the novelty index fails closed | an index that could not read a submission does not mean "novel"; a submission slot is one of four in a day |

## 3. The flows that are not obvious from the diagram

**A submission has two owners.** The alpha was produced by the version that planned it; the POST was
made by the version whose submitter ran. `rK5RGeqa` was generated 09-10 and POSTed 09-23. Axis 2
reports both and collapses neither, because D14 asks the first question and "did we get four today?"
asks the second.

**The correlation probe is asynchronous and the pipeline did not know it.** `GET
/alphas/{id}/correlations/{kind}` answers 200-with-an-empty-body while it computes and returns the
payload on a later call. `forge/probe.py` treated the empty body as an answer, so an alpha whose
correlations were both comfortably under the lines was skipped every round. Measured 2026-09-23;
`read()` now retries.

**The gate's regression signal is the only part of the scorecard that can stop anything**, and it
compares against a recorded baseline rather than against the floor. At a measured 0.48 submissions
per 5,000 against a floor of 4, a gate on the floor would block every merge for months.

## 4. What this drawing does NOT yet contain

- **DORA has no data.** Lead time, deploy frequency, change-failure rate and MTTR need at least two
  recorded deploys, and `DEPLOYED.json` does not exist on the host because `tools/deploy.py push` has
  never been allowed to run.
- **The branch drill is not implemented.** Axis 3 scores the fitness functions alone, so it is
  currently answering "is the architecture extensible in principle" rather than "did a real branch go
  through the gate this release".
- **The deploy half of CI/CD is not wired to Actions.** Deliberate: `tools/deploy.py` has failed two
  audits (91 defects) and must not be driven unattended against the host that holds the only journal.
- **The Actions workflow is not in `.github/`.** The OAuth token lacks the `workflow` scope, so the
  file sits at `ci_pending/ci.yml` in the pushed repository until that scope is granted.
- **22 of 247 tests cannot run on a hosted runner.** They need a 101 MB label file and a 50 MB
  catalogue. The gate names them rather than hiding the gap.

## 5. The attack surface for the next adversarial round

Where I expect a reviewer to find something, written before they look:

1. The scorecard reads the journal by alpha id with "last row wins". Orphan recovery writes second
   rows. Does any axis double-count, and is the dedupe the same one `rung_report` uses?
2. `axis1_product` scores only what a version SUBMITTED. With zero submissions the floor is unmet —
   but is "no product" really the same verdict as "bad product", and does the composite treat them
   identically?
3. The composite divides by the floor. An axis whose floor is 4 and whose value is 40 clamps to 1.0,
   so ten times the goal and exactly the goal score the same. Is that intended? It hides progress
   above the line.
4. `neighbourhood_stability` groups peers by (hypothesis, region, delay, category) — which is not the
   same key the allocator uses, and not the mechanism key either. A third key for the same idea.
5. `check_no_live` greps for a string. A test that builds the flag from parts passes the check.
6. `check_regression` writes the baseline on first run, so the first run can never fail it, and
   nothing stops a change from rewriting `state/ci_baseline.json` to lower the bar.

---

# Draw 2 (2026-09-23 ~11:30), after adversarial round 1

Round 1 (docs/evalharness/audits/architecture_round1.md, 46 findings, adjudicated on commit 5281873)
kept the three boxes, the judged-never-imports-judge direction and the non-compensatory floors. It
broke one arrow and four measurements. This drawing changes exactly those.

## The arrow that was wrong, and its replacement

Draw 1: `scorecard composite ──▶ gate (regression)`. Wrong because, under D14, a candidate version has
produced no rows at merge time; the composite a pre-merge gate computes is a function of the journal
that ALREADY exists, so no diff can move axes 1–2, an unchanged tree can "regress" when the journal
grows (committed 25.5, the VPS computes 25.4), and on a hosted runner axes 1–2 are always zero.

Draw 2 splits it by WHAT CAN KNOW WHAT:

```
   PRE-MERGE  (tools/ci_gate.py — judges the DIFF)            POST-DEPLOY (benchmark.compare — judges the VERSION)
   ├─ tests (two tiers, measured classification)               ├─ cohort A = rows stamped version A
   ├─ schema · no-live · version · fitness · branch drill      ├─ cohort B = rows stamped version B
   ├─ known-red                                                ├─ equal numbers of ET quota days each
   └─ PINNED SCORER: the scorecard run on a FROZEN fixture     ├─ clean submissions per quota day, Wilson interval
      cohort must reproduce a committed golden card.            └─ verdict: better / worse / INDISTINGUISHABLE
      A change to FLOOR / WEIGHT / any gate is a change to
      the golden file — visible in the diff (fixes S8).
```

## The four measurements that were wrong

| | draw 1 | draw 2 |
|---|---|---|
| F2 axis 1 regime | curves read as lists; every cached curve is a `{date: cumulative}` dict → `[]` → "insufficient" → fail | curves sorted by date, cumulative VALUES passed in |
| F3 axis 2 unit | per 5,000 COMPLETE rows against a per-quota-day floor; WARNING rows (16 %, incl. vRk095rv) dropped | per ET quota day; COMPLETE and WARNING both scored |
| F4 composite | flat at 100 above the floors; 4 subs/3 clean (56.4) < 1 clean (61.6); junk (21.8) > nothing (20.0) | axis 2 counts CLEAN submissions only; composite monotone in clean count, not clamped at the floor (floor = 50, 2× floor = 100) |
| S5 window | local midnight; a 1-minute window "meets" 4/day; an unknown `--version` graded all history | ET quota days, whole days only; unknown version is an error |

Plus: S2 neighbourhood uses TRUE one-setting neighbours (same formula, exactly one of decay /
neutralisation / truncation different) and reports "unmeasured" separately from "fail"; D10's eight
hypothesis-standard gates enter axis 1; DORA enters axis 3's value when measured; the pipeline version
is the hash of the loop's MEASURED import closure, so recording a CI baseline no longer changes it (S1 ii).

## What draw 2 still does not do (for round 2 to attack)

- The post-deploy comparison needs two stamped versions with equal quota days; until the first stamped
  deploy there is exactly zero data for it.
- Axis 1 on submitted alphas needs their PnL curves, which live only on the VPS.
- The fixture cohort for the pinned scorer is synthetic: it proves the scorer did not CHANGE, not that it
  is RIGHT.

---

# Draw 4 (2026-09-23)

Drawn from the code as it stands, not from intentions, by the chief architect, 2026-09-23 ~19:50-20:30 +07. The
bytes read (sha256 prefix): forge/offline/benchmark.py bc318f2f, tools/ci_gate.py b920db59, tools/ci_classify.py
6978aced, tools/ci_publish.py f2f40ac0, tools/deploy.py 39c7479c, forge/runner.py 9cdf8d90, tools/ci_fixture.py
cb4aff28, tools/ci_golden_card.json e1d79f09, tools/ci_known_red.json 06f0ccc1, .github/workflows/ci.yml 55d481af,
forge/offline/recover_orphans.py 0a5ae8a9, vps/wq-judge.sh dcd49f1b. They are the bytes the four draw-4 build
adjudicators audited (`audits/draw4_build.md`), so every defect open there is open here, and all four of its sections
end "Signed for push: no". The host was read with `ssh -n -o BatchMode=yes` only (ls, stat, grep, sha256sum,
`systemctl is-enabled / is-active / list-timers`, one python count of the journal passed on the command line);
GitHub with `gh api` and `gh run list`. Nothing was simulated, written on the VPS, committed or pushed.

No draw 3 was ever written into this file, so this draw covers everything since draw 2. D15's clock has not started:
round 2 found new defects, and the audits since (draw3_build, draw3_fix, draw4_build) are module audits under D12, not
adversarial rounds on the architecture. Round 3 is the first round that can count toward D15.

## 0. Three places, three different trees (MEASURED 2026-09-23 ~19:55 +07)

| where | what is there | read how |
|---|---|---|
| dev tree (this Mac) | the draw-4 code: D26-D32 and D39-D42 built; pass-first stages 0b-0e built (runner `run_config()`, `stamp()`; deploy `remote_production_args()`, `watch()`; benchmark `_standard_gate()`) | the hashes above |
| GitHub `khoaminh2957/wq-pipeline` | `main` = 1fce953 (draw 2, 05:40Z); the newest Actions run, 35823401832, concluded failure | `gh api .../commits/main` and the local CI checkout's HEAD agree |
| `/opt/wq`, the host | the one push on record, 02:24-02:30 ET: DEPLOYED.json `version` 8f8b7517b8598d07, `pipeline_version` ec6a5cd75d58fea2. Its runner.py (f36911ae) names `run_config` 0 times; its deploy.py (398706c5) has no `loop_reachable_extras()`; its benchmark.py is 6f22ebf0. No `state/deploys.jsonl`, no `wq-judge.sh`, `wq-judge.timer` not-found. `wq-forge` and `wq-harvest` active; `wq-forge.service` and `wq-forge-tests.timer` enabled | ssh, read-only |

The host journal: 43,094 rows, 38,316 alpha ids. 3,570 rows carry `meta.pipeline_version` (a `grep -o | uniq -c` and a
python count agree); 3,565 distinct ids, every one (ec6a5cd75d58fea2, no run_config): ONE cohort.

The release path has never run with this code. `state/ci_publish_records.jsonl` does not exist on the Mac, and the CI
checkout has no `.git/ci_publish_last`. EX-ANTE (code): `deploy._push_inner()` therefore refuses every tree unless
`--force-unpublished` is passed (`publish_record_for()` returns None), and `ci_publish.checkout_refusal()` refuses the
first publish until `--adopt-head` records a HEAD. The one row in the Mac's `state/deploys.jsonl` is that 02:30 push:
it carries `version` and no `pipeline_version`, `publish` or `target_ledger` field.

## 1. The three systems as they now run

Legend: [HOST] runs on /opt/wq today. [DEV] built and tested in the dev tree, not shipped. [PLANNED] not built.

```
┌─ THE PIPELINE, judged ── [HOST] runs the 02:30 ET push ── [DEV] the stamp code marked below ─────────────────────┐
│ systemd wq-forge: N=300, FORGE_ARGS="--mode composites --order USA/d1,d1 --no-split --delays 1 --ab new"         │
│ vps/forge_loop.sh, one round:                                                                                    │
│ refresh_cells -> runner.main() -> layered_sim.run -> recover_orphans -> harvest -> probe (bg) -> submit (cap 4)  │
│                     |                                                                                            │
│                     |- plan(), _construction():  meta.pipeline_version = runner.pipeline_version() =   [DEV]     │
│                     |      deploy.pipeline_version_of(root) when DEPLOYED.json agrees with the bytes, else       │
│                     |      <id>+MISMATCH:<on_disk> | <on_disk>+untracked | <id>+unverified | unknown,            │
│                     |      then +EXTRAS:<n> from deploy.loop_reachable_extras() (not on the last two)            │
│                     |- stamp(p, run_config(a)):  meta.run_config = sha256 of the parsed argv (D30)  [DEV]        │
│                     |      overwriting the stamps a --plan file carries (stage 0c)                               │
│                     '-> state/layered/runs/forge.jsonl   host: ONE cohort (ec6a5cd75d58fea2, no run_config)      │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
        |  files, nothing else: journal, scored, corr, pnl_curves, POST history,
        |  state/forge/meaning.jsonl (no writer exists), state/deploys.jsonl (absent on the host)
        v
┌─ THE SCORECARD, judge ── forge/offline/benchmark.py ── D41: on the VPS ── [DEV] files; host: NOT INSTALLED ──────┐
│ wq-judge.timer 00:30 ET -> wq-judge.sh -> main(['--record']) -> build(version=None) -> record_card()             │
│      -> state/benchmark/cards.jsonl, at most one line per record_key() = (cohort, graded ET day, host)           │
│ build_from():  cohort_of() = (pipeline_version, run_config); plain_stamp() drops '+...' and marker stamps        │
│   axis 1   _grade() -> axis1_product() -> _standard_gate(): load_standard(), or meaning_index() for gen: (D39)   │
│   axis 2   axis2_throughput(); a version card's days = live_days(deploy ledger), joined on pipeline_version      │
│   horizon  post_horizon.final judged at seen_until = min(now, data_through) (D27)                                │
│   verdict  scorecard(): hard floors, no compensation (D2)                                                        │
│   rank     rank_levels() -> rank_key() / rank_cmp(): verdict (D29), refuted+unproven (D26), proven clean         │
│            per quota day, axis 3 held fraction; NotComparable while the POST horizon is open (D27)               │
│ compare(): the D24 estimand within cell (D28); reached only by `benchmark.py --compare` by hand: NO caller       │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
        |  only the scorer's BYTES cross this line: the truth table is re-scored and compared (D42)
        v
┌─ THE GATE + DEPLOY ──────────────────────────────────────────────────────────────────────────────────────────────┐
│ tools/ci_gate.py: the same CHECKS in gate() (Actions) and in ci_publish.data_tier() (the Mac):                   │
│   no-live, schema, version, fitness (axis3_gearing), branch-drill, tests (known_red_verdict, run_incomplete),    │
│   known-red, pinned-scorer: ci_fixture.card() (17 cases) must equal tools/ci_golden_card.json =                  │
│   {scorer_sha256, fixture_sha256, scorer_closure = import_closure(benchmark.py): 51 files, 48 in the id} (D42)   │
│                                                                                                                  │
│ MAC  tools/ci_publish.py main()  [DEV]            GITHUB, hermetic tier                                          │
│   0 checkout_refusal()                            ci.yml: ci_gate.py, then benchmark.py || true                  │
│   1 data_tier(): the CHECKS, data tier            REPORTS, blocks nothing (D31)                                  │
│   2 ci_classify.py when the record is stale       main = 1fce953 (draw 2); newest run concluded failure          │
│   3 sync(); golden_mixed() refuses a mixed golden (D42)                                                          │
│   4 commit, push --------------------------------> the repository                                                │
│   5 record_publish() -> state/ci_publish_records.jsonl on the Mac (the file does not exist today)                │
│                               |                                                                                  │
│                               v                                                                                  │
│ MAC -> VPS  tools/deploy.py push -> _push_inner()  [DEV]  (runs on the Mac, acts on /opt/wq over ssh)            │
│   publish_record_for(): no record -> refuse (M9-NL, D31);  reconcile_target_ledger();  remote_manifest()         │
│   other_operator_busy();  remote_production_args() (stage 0d);  snapshot() -> stop_units() (quiesce)             │
│   -> remove_library_extras() (D40) -> rsync -> run_smoke() -> write_manifest() -> start_units()                  │
│   -> _record() -> _write_row(): append_target_ledger() -> /opt/wq/state/deploys.jsonl -> the judge's             │
│      live_days(); then the Mac's state/deploys.jsonl, marked with that append's result                           │
│ deploy.py watch (D16)  [DEV, NOT SAFE: draw4_build release 1-3]: the first round after live_at failed -> _undo() │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌╌ [PLANNED] THE PASS-FIRST BRANCH ── 04_passfirst_design.md; D33-D39 ticked; stages 1-5 unbuilt ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┐
╎ stage 2  forge/gen/: D34 y, D35 priors, D36 spending rules, D37 repair  -> meta.hypothesis = gen:<family>        ╎
╎          (D38: harvest.pool_key() then gives the family x cell x category DSR pool unchanged)                    ╎
╎ stage 3  forge/meaning.py, harvest rule part, submit route (D39)        -> state/forge/meaning.jsonl             ╎
╎ stage 4  runner --mode gen, fill_gen   (runner --mode accepts composites | singles | both today)                 ╎
╎ ORDER, each with its source:                                                                                     ╎
╎   1  stage 0 (D30 run_config, 0c re-stamp, 0d smoke) on the host   04 s5.5; host runner names run_config 0 times ╎
╎   2  one incumbent cohort for 7 whole stamped ET days, no push     D33; compare() takes ONE cohort per arm       ╎
╎      that moves pipeline_version or run_config inside the window                                                 ╎
╎   3  the pre-registration committed                                 04 s7 stage 1                                ╎
╎   4  stage 3 live before or with stage 4                            forge_loop.sh: submit, no meaning gate       ╎
╎   5  no `deploy.py watch` until live_days() and dora() map watch    draw4_build scoring 1, release 1 and 3       ╎
╎      rows, and Khoa has ticked the D16 trigger                                                                   ╎
└╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┘
```

Reading it:

- **The judged still never imports the judge.** A grep of forge/, tools/ and vps/ outside tests/ finds benchmark named
  in runner.py, recover_orphans.py and deploy.py in comments only. The loop's one import of a release tool is
  `runner.pipeline_version()` -> `deploy.pipeline_version_of()`; `PIPELINE_EXCLUDED` keeps deploy.py out of the id,
  and deploy.py imports no judge.
- **New since draw 2: the pin reaches into the judged surface (D42).** Of the 51 files in the golden's
  `scorer_closure`, 48 are `in_pipeline()`. Counted two ways: `deploy.in_pipeline()` over the golden's keys, and 51
  minus the three `PIPELINE_EXCLUDED` names in the closure (benchmark.py, branch_drill.py, deploy.py). An edit to any
  of the 48 turns `check_pinned_scorer()` red until the golden is re-recorded in its own commit (`golden_mixed()`,
  `--split-golden`). MEASURED now: `check_pinned_scorer()` ok, 0 of 51 hashes drifted.
- **Two ledgers are the only arrows between the machines.** `record_publish()` -> `state/ci_publish_records.jsonl` ->
  `publish_record_for()` (D31, round 2 M9-NL), and `_write_row()` -> `append_target_ledger()` -> the host's
  `state/deploys.jsonl` -> `live_days()` (D41, draw3_fix release 2). Neither file exists where it is read today (§0).
- **What the judge would grade.** `wq-judge.sh` passes `--record` and no `--version`, so `benchmark.main()` calls
  `build(version=None)`: the WEAK whole-history date-window card, pooling every cohort and every unstamped row, filed
  by `record_key()` under `{"date_window": {"since": null, "until_exclusive": null}}`. Re-derived two ways in
  `scratchpad/d4_judge_card.py`: the arguments the real `main(["--record"])` hands `build()`, and the real
  `build_from()` on three synthetic cohorts. D1 and D14 grade a VERSION; this card grades none.

## 2. D26-D42: where each is implemented

No row below runs on the host: /opt/wq runs the 02:30 ET push, which predates every one of them (§0). "Open" lists
the defects filed against the implementation, by id; a mutant that survives is written "no test pins".

| # | decision | implemented in | state, and what is open against it |
|---|---|---|---|
| D26 | rank level 1 = REFUTED + UNPROVEN submitted | benchmark `rank_levels()` (`refuted_or_unproven_submitted`), `RANK_ORDER`, `rank_key()` | [DEV]. No test pins the `status_counts` branch or a missing `unproven` read as 0 (draw4_build scoring 4) |
| D27 | an open POST horizon is not ranked | `rank_key()` raises `NotComparable`; `build_from()` judges `post_horizon.final` at seen_until = min(now, data_through); `horizon_final_at()`; `_held_next()` | [DEV]. The printed date is wrong across a DST change (draw4_build scoring 5). No test pins that `rank_cmp()` refuses an open SECOND card (scoring 4) |
| D28 | D24 compared within cell | `compare()`: `stratified_rate_test_p()` over the shared cells, the same-direction rule; `ESTIMAND` (`stratum`, `test`, `decides`); `cell_of()` | [DEV]. Reading a cell one arm never scored as "no direction" is the code's reading, printed by `open_ticks()`; D28's words do not settle it (draw4_build ci 8d) |
| D29 | the verdict leads the rank | `VERDICT_ORDER`; element 0 of `rank_key()` | [DEV]. No test pins that a card with no verdict ranks below FAIL (scoring 4) |
| D30 | run parameters start a new cohort | runner `run_config()` (sha256 of the parsed argv without `RUN_CONFIG_EXCLUDED`), `stamp()` in `main()`; recover_orphans `ROUND_KEYS`, `COHORT_KEYS`; benchmark `cohort_of()`, `parse_cohort()`; `live_days()` joins on pipeline_version only | [DEV]; the host runner has no `run_config` and 0 rows carry one. Open: stage 0c makes `recover_orphans` recover `--plan` rounds as `ambiguous` (draw4_build pipeline 1); a run_config of `ambiguous` forms a cohort (scoring 3, pipeline 2); every run_config of a pipeline_version takes its whole live-day set (scoring 2); the plan PATH is outside the hash, so pow and c11 rounds share one run_config (pipeline 6, P6); the marker-stamp clause moves no truth-table case (ci 1) |
| D31 | block-merge enforced on the Mac and at deploy; Actions reports | `ci_publish.main()` runs `data_tier()` before `sync()` and the push; `deploy._push_inner()` refuses without `publish_record_for()`; ci.yml reports | [DEV], never run end to end: no publish record exists (§0). "The run was the whole suite" claims more than `run_incomplete()` reads (ci 2); a result with no `incomplete` key reads complete (ci 3) |
| D32 | the four release flags stay | `deploy.main()` `--force-unpublished` (abbreviations off); `ci_publish.main()` `--adopt-head` (`adopt_head()`), `--split-golden`, `--no-push` | [DEV]. Nothing open by id |
| D33 | proof is sequential: incumbent 7 whole stamped days, then the branch; confounds first | `compare()` returns `design` ("sequential, confounded by calendar date") and `calendar`, which `render_compare()` prints after the verdict. Nothing counts the incumbent's days | PARTIAL. `render_compare()` prints the VERDICT before any confound (draw4_build scoring, cross-module). The 7-day rule is a process rule no code enforces; the host has one cohort (§0) |
| D34 | learn from Sharpe >= 0.8 x the row's LOW_SHARPE limit | nothing | NOT YET: no forge/gen/ (`ls`, 2026-09-23) |
| D35 | uniform priors, 20 % exploration floor | nothing | NOT YET |
| D36 | spending rules keyed on the fingerprint family | nothing | NOT YET |
| D37 | repair queue with its own coin | nothing | NOT YET |
| D38 | DSR pool = family x cell x category | nothing as a mechanism | NOT YET. EX-ANTE (code): `harvest.pool_key()` = (meta.hypothesis, region, delay, category) gives that pool unchanged once a generator writes `hypothesis = gen:<family>`; no generator writes it |
| D39 | D19 amended for generated alphas | scorer half: `_standard_gate()`, `meaning_index()`, `MEANING_DECIDABLE`, `MEANING_NOT_APPLICABLE`, `load_meaning()`, the gap line in `build()` | PARTIAL, [DEV]. The writer and the submit route are NOT YET (no forge/meaning.py; forge/submit.py has no meaning route). The reader assumes a schema no writer produces (the `MEANING_LEDGER` comment); gates stored as objects, the shape 04 §4.2 describes, read null with no gap line (draw4_build scoring, verified-not-blocking). No test pins G8 in `MEANING_DECIDABLE` (scoring 4) |
| D40 | push removes unlisted library YAML; `+EXTRAS:<n>` | `_push_inner()`: `remote_library_yaml()` -> `_library_extras()` -> `snapshot()` -> `remove_library_extras()`; `LIBRARY_DIRS`; `loop_reachable_extras()`; runner `pipeline_version()`; `status()` | [DEV]; the host deploy.py lacks it. Open: a mutant that has `pipeline_version()` count the extras of `root` instead of `base` survives (draw4_build pipeline 3); `staged/` is overwritten though never deleted, and a mechanism promoted on the host by `promote_staged.py` would be deleted (release 12d, 12e: a decision for Khoa) |
| D41 | the judge runs on the VPS; push appends its row to the target, with reconciliation | vps/wq-judge.sh, .service, .timer; benchmark `main()` `--record` -> `record_card()`, `record_key()`; deploy `append_target_ledger()`, `reconcile_target_ledger()`, `unreconciled_rows()`, `read_target_ledger()`; `_OTHER_READERS` in `other_operator_busy()` | [DEV]; NOT INSTALLED on the host (timer not-found, `wq-judge.sh` absent, no target ledger). Open: the busy guard reads only `active`, which a oneshot never prints (release 2); success is "exactly one more line" (release 7); the per-key idempotence has no recorded authority (scoring, cross-module); the judge grades no version (§1, measured here) |
| D42 | the pinned scorer is its full closure; publish reads the same closure | `ci_fixture.import_closure()`; `ci_gate.check_pinned_scorer()`, `scorer_moved()`, `record_refusal()`, `record_golden()`; `ci_publish.golden_mixed()` (`SCORER` plus both goldens' `scorer_closure` keys) | [DEV]; MEASURED green now (51 of 51). Open: tools/ci_fixture.py is outside the closure and a mutant dropping it from `SCORER` survives (release 10d); `record_refusal()` has no route when the old fixture crashes on the new scorer (scoring, cross-module; ci X1) |

The two orchestrator decisions recorded under D42 are implemented as `MODULE_TEST_COVERAGE_MIN` = 1.0 (checked by
`fitness_functions()` over top-level forge/*.py only) and `NOT_COVERED_PRE_MERGE` in ci_gate.py.

## 3. What changed since draw 2, and why

Draw 2 had three boxes and one new arrow, `compare()` judging a version after it ran. Round 2 kept the boxes and broke
that arrow (A1: blind at the desk's rate). What changed, by box, each with the finding or decision that produced it:

**The scorecard (forge/offline/benchmark.py)**

| change | where | why |
|---|---|---|
| the 0-100 composite, WEIGHT and UNPROVEN_CREDIT deleted; a lexicographic rank | `rank_key()`, `rank_levels()`, `RANK_ORDER` | round 2 F4-NL, A6; D25 |
| the verdict leads the rank; level 1 counts refuted + unproven; an open horizon is not ranked | `VERDICT_ORDER`, `rank_levels()`, `NotComparable` | D29; draw3_build scoring SERIOUS 2 and D26; draw3_build scoring SERIOUS 3, round 2 A4 and D27 |
| clean means proven; unproven is reported and never counted | `alpha_status()`, `axis1_product()`, `axis2_throughput()` | round 2 A5 |
| a version's days come from the deploy ledger, for the rate only | `live_days()`, `build_from()` | round 2 A3; draw3_build scoring SERIOUS 1 |
| a POST counts within 14 days of creation; the clock is an argument | `_submissions()`, `horizon_final_at()`, `POST_HORIZON_DAYS` | round 2 A4 |
| the data's own cut: the day the copy was cut is not whole; finality at seen_until | `load_inputs()`, `build_from()`, `_held_next()` | draw3_build scoring SERIOUS 4; draw3_fix scoring 1 |
| `compare()` judges a pre-registered estimand, within cell, and says what it could have detected | `compare()`, `ESTIMAND`, `stratified_rate_test_p()`, `minimum_detectable_ratio()` | round 2 A1; D24; draw3_build scoring SERIOUS 6; D28 |
| a cohort is (pipeline_version, run_config); suffixed and marker stamps form none | `cohort_of()`, `parse_cohort()`, `plain_stamp()`, `STAMP_MARKERS` | D30; draw3_fix scoring 12 |
| every card says what produced it; an append-only card ledger | `provenance()`, `record_card()`, `record_key()` | round 2 S10-NL, A2; D41 |
| DORA is reported, never scored; `noop` skipped; `interrupted` and `units_down` are failures | `dora()`, `dora_checks()`, `axis3_gearing()` | round 2 A9; draw3_fix scoring 8 |
| axis 3's floor is 1.0, and three of its checks read structure | `FLOOR`, `_ab_arm_is_real()`, `import_cycles()`, `_modules_with_a_real_test()` | round 2 S4-NL |
| a regime third is judged against its own standard error | `regime_stability()`, `REGIME_SE_MULTIPLE` | round 2 S3-NL |
| D7's "held" is read on the NEXT window, or "not evaluable" | `_held_next()` | round 2 S9-NL, m1 |
| the neighbour pool is the cohort's own rows, bounded by the clock | `build_from()`, `_visible_at()` | round 2 S10-NL |
| a generated alpha reads the meaning ledger | `_standard_gate()`, `meaning_index()`, `load_meaning()` | D39; 04 §4.4 |
| the library loader fails loudly | `load_standard()` | round 2 A5 |

**The gate (tools/ci_gate.py, tools/ci_fixture.py, the golden, the known-red list)**

| change | where | why |
|---|---|---|
| the pinned scorer is a 17-case truth table carrying the scorer's, the fixture's and the closure's hashes | `ci_fixture.card()`, `import_closure()`, `check_pinned_scorer()` | round 2 A7, S8-NL; draw3_build ci SERIOUS 3; D42 |
| a re-record prints its diff and refuses a scorer change mixed with a fixture change | `record_golden()`, `record_refusal()`, `scorer_moved()` | round 2 S8-NL |
| D23's allowance is one committed node id with its failure text | `known_red()`, `known_red_verdict()`, `check_known_red()` | round 2 A8; D23 |
| a pytest run that was not the whole collected suite blocks | `run_incomplete()`, `_pytest_env()` | draw3_fix ci 2 |
| a stale classification blocks | `check_tests()` | round 2 S6-NL |
| the no-live scan reads the syntax tree of tests, conftests, the scripts they run and the workflows | `check_no_live()` | round 2 S7-NL; draw3_build ci SERIOUS 5; draw3_fix ci 4 |
| the LLM test files are reported NOT COVERED pre-merge | `NOT_COVERED_PRE_MERGE` | draw3_fix ci 3; the orchestrator decision under D42 |

**Publish (tools/ci_publish.py)**

| change | where | why |
|---|---|---|
| the checkout is written only as ci_publish left it | `checkout_refusal()`, `adopt_head()` | round 2 A12 |
| the synced tree is the tested tree | `tree_identity()`, `subset_hashes()` | round 2 A8, M9-NL; draw3_build release 6 |
| the data tier allows a failure only on the gate's known-red verdict | `data_tier()` | draw3_build release SERIOUS 2 |
| the golden cannot ride in with a file it pins | `golden_mixed()` | round 2 S8-NL; draw3_fix ci SERIOUS 1; D42 |
| one record per publish, written before `gh` is asked | `record_publish()` | round 2 M9-NL; draw3_build release 11 |
| .github is in the published subset | `SUBSET` | round 2 M9-NL |

**Deploy (tools/deploy.py) and the pipeline's stamp (forge/runner.py, forge/offline/recover_orphans.py)**

| change | where | why |
|---|---|---|
| the id is the shipped in_pipeline surface; on a target, exactly the files DEPLOYED.json lists | `pipeline_version_of()`, `in_pipeline()`, `_target_manifest()` | round 2 A10; draw3_build release BLOCKER 1 |
| push deletes unlisted library YAML; the stamp marks what remains | `_push_inner()`, `remove_library_extras()`, `loop_reachable_extras()` | draw3_fix release 1; D40 |
| push refuses a tree no publish record vouches for | `publish_record_for()` | round 2 M9-NL; D31, D32 |
| a no-op push is logged `noop` | `_push_inner()` | round 2 A9 |
| the ledger row reaches the target; a lost append is re-appended or push refuses | `append_target_ledger()`, `reconcile_target_ledger()`, `_with_signals()` | D41; draw3_fix release 2, 3 |
| the smoke plans with the unit's N and FORGE_ARGS | `remote_production_args()`, `smoke_command()` | 04 §7 stage 0d |
| a first-round watch | `watch()`, `_round_verdict()`, `_watch_rollback()` | deploy.md B5 (D16's second trigger); 04 §7 stage 0d |
| harvest_loop.sh, recover_harvest.py, wq-forge-tests.sh and wq-judge.sh are shipped | `PLAN` | the note under D41 |
| the runner's fallback stamp is the same function over the bytes; a mismatch carries its own id | runner `pipeline_version()` | round 2 S1iii-NL; draw3_build pipeline MINOR 3 |
| run_config, and `--plan` rounds re-stamped | runner `run_config()`, `stamp()` | D30; 04 §7 stage 0c |
| an orphan matched to plans of two versions is marked, not guessed | recover_orphans `match()`, `AMBIGUOUS_VERSION`, `ROUND_KEYS`, `COHORT_KEYS` | round 2 A11 |
| `--li` is not `--live` | runner `main()` (`allow_abbrev=False`) | round 2 S7-NL |

## 4. What draw 4 still does not do

1. **None of it runs.** The host runs the 02:30 ET push, GitHub holds draw 2, and no publish record exists (§0). Every
   draw4_build section ends "Signed for push: no", requiring P1-P8, scoring 1-6, R1-R7 and C1-C7 first.
2. **The judge grades no version, and nothing it records can be ranked.** (a) `build(version=None)`, §1. (b) At the
   judge's own clock, 00:30 ET with the journal written up to that minute, the newest graded day is the day before, so
   `post_horizon.final` is False and `rank_key()` raises `NotComparable`. Reproduced (`d4_judge_card.py`, part 3):
   rows through 09-23, graded 09-24 00:30 ET, comparable from 10-08. EX-ANTE from `build_from()` and
   `horizon_final_at()`: while the loop writes a row every day, every card the judge appends is unrankable when it is
   appended, and a ledger line is never re-graded. Which cohort the daily judge should grade is decided nowhere. The
   owners are wq-judge.sh (release) and `benchmark.main()` (scoring); neither is edited here.
3. **D9's regression half is enforced nowhere** (round 2 A2, unchanged). `compare()` has no caller: the judge records
   scorecards, and `main()` refuses `--record` together with `--compare`.
4. **The incumbent's rate can never be measured.** `live_days()` needs a ledger row naming ec6a5cd75d58fea2. The host
   has no ledger, and `live_days()`'s docstring records that the next push writes a different id for the same
   bytes. So axis 2 reads "exposure unknown" for the only stamped cohort for ever. `compare()` on D24 needs no
   exposure, so D33 is not blocked by this.
5. **A cohort's exposure is undefined when one pipeline_version runs under two run_configs** (draw4_build scoring 2).
   `live_days()` joins on pipeline_version only, and the ledger row carries `production_args`, not a run_config.
6. **Axis 3 measures the tree that runs it** (round 2 F4-NL; `axis3_gearing()` says so in `measured_on`). The check
   "the deployed code has a version" in `fitness_functions()` is still an existence test on tools/deploy.py, a kind
   S4-NL named; draw 3 converted the other three. The module-test check reads top-level forge/*.py only
   (`_modules_with_a_real_test()`; draw3_fix scoring 15).
7. **Axis 1's instruments are still the pipeline's own** (round 2 S8-NL ii). `axis1_product()` reads DSR and PBO from
   harvest's scored store and the correlation lines from `SUB.corr_lines()`. No judge-owned DSR from curves exists.
8. **A card can still move after the fact** (draw3_fix scoring 14). Only the neighbour pool and the meaning rows are
   bounded by the clock; `provenance()` lists the rest under `not_bounded_by_now`.
9. **D16's first-round trigger cannot meet "before any quota is spent"** (draw4_build release 3). The incumbent's own
   rounds fail the watch's rule 23 times in 181 (12.7 %; 21 of the 23 on 09-06 17:00-20:59 +07; POST-HOC, MECHANISM:
   UNKNOWN), and forge_loop.sh runs submit before it checks `STOP_FORGE`.
10. **"The run was the whole suite" is narrower than written** (draw4_build ci 2): `collect_ignore`,
    `pytest_ignore_collect` and `python_files` each shorten a run that `run_incomplete()` reads as complete.
11. **The pass-first branch is unbuilt**: stages 1-5, D34-D38, and the writer half of D39 (§2).
12. **The two LLM test files are covered by nothing before a merge** (`DATA_BOUND`, `NOT_COVERED_PRE_MERGE`).
13. **The exact tests assume independent alphas** (round 2 X1). Dispersion across days was 11.99 on 9 days of the Mac
    copy (draw4_build scoring, confirmed); dispersion within a cell is unmeasured.

## 5. The attack surface I expect round 3 to find, written before any attack

Each item is a prediction, not a finding; its label says what it rests on. None has been run as an attack.

1. **Cohort churn under D33 and D42** (EX-ANTE, code). D33 needs ONE incumbent cohort for 7 whole stamped days, and
   `compare()` takes one cohort per arm (`parse_cohort()`). An edit to any in_pipeline file re-keys
   `pipeline_version_of()`; for the 48 of them in the scorer's closure it also needs a golden re-record in its own
   commit, then a publish and a push. A change of N or FORGE_ARGS re-keys `run_config()`. The draw-4 fixes alone edit
   runner.py (P1, P3). Expected finding: no start date for D33's window survives the fix queue, and under D42 every
   live-loop hotfix is a new cohort by construction.
2. **The judge, a push and the loop share the host's tree and plan directory with no lock between them** (EX-ANTE,
   code). `wq-judge.sh` takes no lock; the push's guard reads only `active` (draw4_build release 2). `build()` runs
   the branch drill by default (`axis3_gearing(run_drill=True)`), and `branch_drill.drill()` writes and removes
   state/forge/plans/<seed>.json in the directory `recover_orphans.load_plans()` reads; draw4_build pipeline 1
   showed that two plan files holding one construction make a recovered stamp `ambiguous`. That a drill
   construction ever matches an orphan is SPECULATION: the drill plans a synthetic composite.
3. **The judge's date card** (MEASURED, §1 and §4 item 2) will be read as a D1/D14 violation. Choosing the cohort is a
   decision for Khoa, not a repair.
4. **`run_config()` hashes `live` and `root`** (EX-ANTE, code: it keeps every parsed argument except seed and plan;
   reproduced with the real parser in `scratchpad/d4_runcfg.py`: the production arguments give ddc3ca582fd73753 with
   `--live` and e5a81af5c610a5d6 without, and a second seed changes nothing). So no dry run, the stage-0d smoke
   included, can name the cohort a live round will write. The `RUN_CONFIG_EXCLUDED` comment states the `root`
   consequence and not the `live` one. Whether any reader needs that name before rows exist: not established.
5. **The pass-first ordering is documentation** (EX-ANTE). Nothing in forge_loop.sh or deploy.py refuses `--mode gen`
   before stage 3 is live; today only argparse does, because runner `main()` offers no `gen` mode.
6. **The module-test fitness check will not see forge/gen/** (EX-ANTE, code: `_modules_with_a_real_test()` globs
   forge/*.py). 04 §4.4 says each new module needs its own test "or axis 3 fails outright"; for forge/gen/* and
   forge/offline/tick.py it would not.
7. **The hermetic tier prints PASS for a check that did not run** (EX-ANTE, code): `check_branch_drill()` returns
   ok=True with "NOT RUN on this tier". Actions only reports (D31), so the harm is in what a reader believes: round
   1's S4 in a new place.
8. **The golden re-record path** (draw4_build scoring, cross-module; ci X1). The first re-record after P1, P3 and the
   scoring fixes moves the scorer and, with C1, the fixture. `record_refusal()` is the only route and has no
   exception path when the old fixture fails on the new scorer.
9. **meaning.jsonl written in 04 §4.2's shape reads null** (draw4_build scoring, verified-not-blocking). Every
   generated submission would then count against its version under D26, the failure D39 was ticked to prevent. It
   becomes blocking the day stage 3 writes its first row.
10. **`ci_publish.main()` parses with abbreviations on** (EX-ANTE, code). `deploy.main()` turned them off because a
    flag that relaxes a gate must be typed whole; `--split-golden` relaxes `golden_mixed()`'s refusal and is
    reachable as `--split`.

The check behind this section is `scratchpad/d4_doccheck.py`, kept out of the repository for two reasons: this task
owns this file only, and a new test file under forge/tests or tools/tests moves `ci_classify.tests_hash()`, which
makes the classification stale and blocks the hermetic tier until it is re-measured (`check_tests()`). It resolves
every call written with parentheses and every backticked constant above against the syntax trees of the files named
in §0 plus forge/harvest.py, forge/submit.py, forge/offline/branch_drill.py and tools/layered_sim.py, requires a
row for each of D26-D42, and requires every cited audit section and round-2 id to exist. It fails on this file
without this section, and each of five mutants (a renamed function, a function under the wrong module, a dropped
D35 row, a round-2 id that does not exist, a misspelt constant) fails it.

---

# Draw 5 (2026-09-23)

Drawn from the code as it stands, by the chief architect, 2026-09-24 00:20-00:50 +07 (ET quota day 2026-09-23). The
bytes read (sha256 prefix) are the bytes the six draw-5 module adjudicators audited (`audits/draw5_build.md`), and
none changed between their audits and this drawing, so every defect open there is open here: forge/runner.py
d2e84b70, forge/offline/recover_orphans.py 99aae169, forge/offline/benchmark.py b30d255c, forge/meaning.py 01bc3c3a,
forge/gen (propose 417df14c, repair 4ccd15e7, spend e5a55844, state 82a67d58, productions abd22703, posterior
aba9c7e4, families 431a5e3d, `__init__` d74ebe31), tools/deploy.py 7ff14dbc, tools/ci_gate.py 62d1c28c,
tools/ci_fixture.py e2feced0, tools/ci_publish.py d1de5f28, tools/ci_classify.py 54c634c3, tools/ci_golden_card.json
d8a0cc0e, tools/ci_known_red.json 8867dd79, .github/workflows/ci.yml 4c7d603a, vps/forge_loop.sh a0b3df46,
vps/forge.env c514eed8, vps/wq-judge.sh 13017d1c, vps/wq-judge.service 27b71125, vps/wq-judge.timer 48689419,
vps/systemd_wq-forge.service 6a3af0bd. Read beside them, unchanged since round 3: forge/submit.py 07df3bdf,
forge/harvest.py 95f2233d. The host was read with `ssh -n -o BatchMode=yes` only (ls, sha256sum, `systemctl
is-active / is-enabled / show`, one python count and three grep counts of the journal passed on the command line, a
tail of loop.log); GitHub with `gh api` and `gh run list`. Nothing was simulated, written on the VPS, committed or
pushed, and no test file was added. Ids of the form D4-.., R3-.. and D5-.. are rows of `backlog.md`.

**D15.** Round 3 found 1 NEW FATAL and 15 NEW SERIOUS (`audits/architecture_round3.md`, Verdict); the clock did not
start. The draw-5 audits are module audits under D12, not adversarial rounds. Round 4, against this drawing, is the
next round that can count.

## 0. Three places, three trees (MEASURED 2026-09-24 00:30 +07)

| where | what is there | read how |
|---|---|---|
| dev tree (this Mac) | draw 5: D43-D47 and D49-D52 built, as §2 maps. `deploy.pipeline_version_of()` of the dev root is b46536d567b5914b, equal to `manifest()`'s `pipeline_version`; its 497 in_pipeline files include forge.env, the 8 forge/gen files and forge/meaning.py | `python3 -B`, the two functions |
| GitHub `khoaminh2957/wq-pipeline` | `main` = 1fce953 (draw 2, 09-23 05:40Z); the newest Actions run, 35823401832, concluded failure | `gh api .../commits/main`, `gh run list` |
| `/opt/wq`, the host | unchanged since draw 4: DEPLOYED.json `version` 8f8b7517b8598d07, `pipeline_version` ec6a5cd75d58fea2; runner.py f36911ae, benchmark.py 6f22ebf0, deploy.py 398706c5, forge_loop.sh a9f2c313, submit.py 02706d61, recover_orphans.py f0b146fd. ABSENT: forge.env, wq-judge.sh, forge/gen, forge/meaning.py, state/deploys.jsonl, state/forge/run_config_log.jsonl, state/forge/meaning.jsonl, state/benchmark/cards.jsonl. `wq-judge.timer` not-found; `wq-forge-tests.timer` enabled; `wq-forge` and `wq-harvest` active; the `wq-forge` Environment is draw 4's, and it has no EnvironmentFiles | ssh, read-only |

The host journal: 43,268 lines. 3,730 rows carry `meta.pipeline_version`, every one ec6a5cd75d58fea2 (a python count
and `grep -c` agree); 0 carry a `run_config` (both ways again). So there is ONE cohort, `(ec6a5cd75d58fea2, None)`.
Its rows' arms: `current` 1,930, `new` 1,800. No row anywhere carries arm `composites` or `gen` (grep over every line:
current 11,836, new 9,030, typed 980, pow15 150, pow2 150). Stamping began 2026-09-23 02:30 ET, so no whole stamped ET
day has closed: φ for one stamped version is still UNMEASURED (round 3 F1, its Caveat).

The Mac: `state/ci_publish_records.jsonl` is absent; `state/deploys.jsonl` holds the one 02:30 ET row, without a
`pipeline_version`; there is no run_config log and no meaning ledger. EX-ANTE (code), unchanged from draw 4:
`_push_inner()` refuses every tree unless `--force-unpublished` is passed (`publish_record_for()` returns None).

**Sign-off (the rule recorded with D43-D46).** `audits/draw5_build.md`: meaning **yes**; pipeline **yes**; gen **no**
(D5-X-GE-G1, D5-X-GE-G2, D5-X-GE-G3); scoring **no** (D5-X-SC-S1); release **no** (D5-X-RL1, D5-X-RL2); ci **no**
(D5-X-C8; D5-X-CI-P2, D5-X-CI-P3). A push ships the whole tree (`file_map()` over `PLAN`), so this tree cannot be
pushed under that rule until all four modules are signed.

## 1. The three systems and the branch, as they run now

Legend: [HOST] runs on /opt/wq today. [DEV] built and tested in the dev tree, not shipped. [BUILT] in the dev tree
and imported by no module the loop runs. [NOT YET] not built. The diagram is generated by `scratchpad/d5_diagram.py`,
which refuses a line wider than its box.

```
┌─ THE PIPELINE, judged ── [HOST] the 02:30 ET push (runner f36911ae, forge_loop.sh a9f2c313) ── [DEV] below ──────────┐
│ vps/forge.env [DEV; absent on the host]  N=300  FORGE_ARGS="--mode composites --order USA/d1,d1 --no-split           │
│   --delays 1 --ab new"   D50. In the pipeline id (deploy in_pipeline()), so flipping it is a new version.            │
│   sourced by forge_loop.sh load_forge_env (a ROUNDS=1 caller keeps its own values); the unit's                       │
│   EnvironmentFile=-/opt/wq/forge.env is a one-time attended edit, not made (host: EnvironmentFiles empty)            │
│       |                                                                                                              │
│       v                                                                                                              │
│ vps/forge_loop.sh, one round. Every line the watch reads is "=== ... ===" (D43; round 3 S2-S4):                      │
│   auth_gate -> "auth dead" | "auth gate crashed at import" (exit 4) | "auth gate crashed (exit N)"                   │
│   record_adjudication, refresh_cells -> "=== step <name> exit N, at <epoch> ==="                                     │
│   "=== forge round, seed S" -> runner main() -n $N $FORGE_ARGS: THE SAME ARGUMENTS EVERY ROUND                       │
│        |                                    (no round randomiser: D47, D53 NOT YET)                                  │
│        |- plan(): --mode composites; --ab new stamps meta.arm current | new (setdefault)                             │
│        |- stamp(): meta.pipeline_version = pipeline_version(), OVERWRITTEN (D46); meta.run_config =                  │
│        |           run_config(): the parsed argv + plan_sha256 (D30); meta.arm setdefault a.mode | PLAN_FILE_ARM     │
│        |- note_run_config(): a LIVE start appends (pv, rc, host) if new -> state/forge/run_config_log.jsonl          │
│        |           (D45; record_run_config() under one LOCK_EX)   [DEV; the file is absent on the host]              │
│        '- layered_sim.run -> state/layered/runs/forge.jsonl                                                          │
│                   host: 3,730 stamped rows, ONE cohort (ec6a5cd75d58fea2, run_config absent)                         │
│   "=== round exit N"; exit 2 is "exhausted" only with the runner's own words (round 3 S2)                            │
│   recover_orphans (ROUND_KEYS seed, pv, rc, gen_state) -> harvest -> probe (bg) -> submit --submit --cap 4           │
│   each followed by "=== step <name> exit N, seed S ==="; then "=== round end, seed S, at <epoch> ==="                │
│   a quota-spent round sleeps to next_reset: 00:05 America/New_York (round 3 S9)                                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
        |  files only: journal, scored, corr, pnl_curves, POST history, run_config_log.jsonl (D45),
        |  meaning.jsonl (no caller writes it), the host's deploys.jsonl (push's append_target_ledger())
        v
┌─ THE SCORECARD, judge ── forge/offline/benchmark.py b30d255c ── D41: [DEV]; host runs 6f22ebf0, no judge unit ───────┐
│ wq-judge.timer 00:30 America/New_York -> wq-judge.sh: COHORTS = cohort_label(cohort_of(r)) over scored rows          │
│   -> per cohort: benchmark.py --record --version <cohort> -> main() -> build() -> record_card() -> cards.jsonl       │
│      at most one line per record_key() = (cohort, graded ET day, host); success read from stderr;                    │
│      wq-judge.service MemoryMax=3G, Nice=19, TimeoutStartSec=1h (round 3 S10, m11)      [host: timer not-found]      │
│ load_inputs(): read_journal() (last row wins, _reduced() to JOURNAL_KEEP_META etc.; round 3 S10),                    │
│   load_meaning(), load_run_config_log(), load_deploys()                                                              │
│ build_from(): cohort_of() = (pv, rc), _forms_cohort(); exposure = cohort_live_days() (D45) over live_days(),         │
│   which reads watch rows by WATCH_KEEPS_RUNNING / WATCH_ROUND_FAILED (D43; draw4_build scoring 1)                    │
│   axis 1  _grade() -> axis1_product() -> _standard_gate(): library -> load_standard();                               │
│           gen: -> meaning_index(): formula_sha must match, not before creation, earliest row wins (round 3 S8)       │
│   D49     _submissions(): every accepted POST counts against rank level 1; POST_HORIZON_DAYS bounds credit only      │
│   rank    rank_key(): verdict (D29), refuted + unproven (D26), proven clean per day, axis 3; NotComparable           │
│           until comparable_from() (D27)                                                                              │
│ compare():      version against version, COMPARE_IS_NOT_GATE3 printed first (round 3 F1)  <- main() --compare        │
│ compare_arms(): D47. ARMS ("composites", "gen") within ONE pipeline_version; strata (ET day, cell);                  │
│                 _arms_decision(), MIN_SHARED_DAYS 5, arms_mdr().  NO CALLER: not in main(), not in wq-judge.sh;      │
│                 only ci_fixture case_compare_arms().  On the shipped forge.env (--ab new) every live row             │
│                 reads arm current | new, so it returns "no-data" (draw5_build pipeline M14, scoring M15)             │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
        |  only the scorer's BYTES cross this line: the truth table is re-scored and compared (D42)
        v
┌─ THE GATE + DEPLOY + WATCH ── [DEV]; none of it has run against the host ────────────────────────────────────────────┐
│ ci_gate gate(): CHECKS = no-live, schema, version, fitness, branch-drill, test-files (round 3 S6), tests,            │
│   known-red, pinned-scorer                                                                                           │
│ PINNED SCORER  check_pinned_scorer(): ci_fixture card() = 21 cases, new since draw 4: case_input_layer()             │
│   (round 3 S7), case_compare_arms() (D47), case_run_config_exposure() (D45), case_watch_rows(); must equal           │
│   tools/ci_golden_card.json d8a0cc0e: scorer b30d255c, fixture e2feced0, scorer_closure 51 files, 48 in the          │
│   id, 0 drifted (hashlib, 2026-09-24 00:47 +07). forge/meaning.py and forge/gen/* are NOT in the closure             │
│ MAC  ci_publish main() (allow_abbrev off, round 3 m8): checkout_refusal() -> data_tier() -> sync() ->                │
│   golden_mixed() -> commit, push -> record_publish() -> state/ci_publish_records.jsonl  [never run: absent]          │
│ GITHUB  main = 1fce953 (draw 2); ci.yml runs ci_gate.py, then benchmark.py || true: REPORTS, blocks nothing          │
│ MAC -> VPS  deploy.py push -> _push_inner():                                                                         │
│   publish_record_for() -> shipped_production_args(): the SHIPPED forge.env through _forge_env_from() (D50)           │
│   -> reconcile_target_ledger() -> remote_manifest() -> noop? -> other_operator_busy()                                │
│   -> _library_extras(): REFUSE, naming them, unless --delete-unlisted-library (D44) -> snapshot() -> stop_units()    │
│   -> remove_library_extras() -> rsync -> run_smoke(prod): import; pytest forge/tests -x; the planner with            │
│      the shipped N and FORGE_ARGS -> write_manifest() -> start_units() (live_at) -> _record() ->                     │
│      _write_row() -> append_target_ledger() -> the host's state/deploys.jsonl (absent today)                         │
│ deploy.py watch  BY HAND, within WATCH_MAX_AGE_S of live_at (push no longer prints it; draw4_build release R1)       │
│   _watch_inner(): last_push_row(), remote_manifest() ONCE, judge_maps_watch_rows() (release R1)                      │
│   poll remote_log_markers() -> _judge(), walking rounds with _round_report() through `round end`:                    │
│     "auth gate crashed at import", or _crashed_before_dispatch() -> ROLLBACK: _watch_rollback() ->                   │
│         other_operator_busy(), snapshot_readable(), stop_units(), _undo()                      (D43)                 │
│     anything else that failed, _round_problems() -> REPORTED, never rolled back: watch_not_rolled_back               │
│     the FIRST round that did work on the pushed pv, nothing failed -> watch_ok;  60 min -> _watch_timeout()          │
│   _record_watch() -> a ledger row with running_after from WATCH_OUTCOMES                                             │
│   OPEN: _watch_rollback() re-reads no manifest (draw5_build release SERIOUS 1, D5-X-RL1)                             │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌╌ THE PASS-FIRST BRANCH ── D34-D39, D47, D51-D53 ── [BUILT] and [NOT YET INTEGRATED] ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┐
╎ BUILT [DEV], imported by NO module the loop runs (grep of forge/ tools/ vps/ outside tests/, 2026-09-24):            ╎
╎   forge/gen   propose(): 1. D51 neighbours of the rows `handed` in (repair neighbours())                             ╎
╎                          2. D37 repairs (repair triggers(), coin(), grid(); REPAIR_SHARE 0.10)                       ╎
╎                          3. draws (productions draw(); posterior round_weights() | floor_weights(), FLOOR_SHARE)     ╎
╎               each through spend verdict() (D36 on families FamilyIndex) and d18_refuses(); state build()            ╎
╎               gives meta.gen_state; every candidate: hypothesis gen:<family> (D38 via harvest pool_key()),           ╎
╎               arm "gen" (productions ARM), gen_route draw | floor | repair | neighbour                               ╎
╎   forge/meaning.py   score() -> check_row() -> append() -> state/forge/meaning.jsonl (absent everywhere)             ╎
╎               decidable_verdict() = D39's rule; _g4() = D52; SCORER = the file's own sha                             ╎
╎ NOT YET INTEGRATED:                                                                                                  ╎
╎   runner --mode gen ................ runner main(): --mode choices are composites | singles | both                   ╎
╎   the round randomiser (D47, D53) .. forge_loop.sh passes $FORGE_ARGS unchanged to every round                       ╎
╎   D51 re-sims, live ................ nothing calls propose(); forge/submit.py holds nothing for want of neighbours   ╎
╎   submit meaning route (D39) ....... forge/submit.py (07df3bdf, unchanged since round 3) names no meaning row;       ╎
╎                                      nothing calls meaning append(), so load_meaning() reads None                    ╎
╎   in-invocation twin hold .......... round 3 S11: submit main() unchanged                                            ╎
└╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┘
```

Reading it:

- **The judged still never imports the judge.** forge/gen and forge/meaning.py import nothing from forge/offline:
  their imports are forge.allocate, factory, grammar, harvest, hypotheses, labels, novelty, score, signature,
  standard, submit and typed, forge.llm.verify, the root fingerprint.py, tools/self_corr_predict.py, and
  tools/funnel/precheck_lib.py loaded by path (`_nogo_families()`). benchmark reads meaning.jsonl as a FILE
  (`load_meaning()`) and imports no forge.meaning. The two new arrows from the pipeline to the judge are files:
  `record_run_config()` -> run_config_log.jsonl -> `cohort_live_days()`, and `append()` -> meaning.jsonl ->
  `meaning_index()`. Nothing calls the second writer.
- **Where the D47 arms are told apart, and where they are not.** The one reader is `_arms_strata()`: `meta.arm` in
  `ARMS`, within one plain pipeline_version, any run_config. The writers: runner `stamp()` sets `a.mode` only where a
  row has no arm; `plan()` under `--ab new` has already set `current` or `new`; forge/gen sets `ARM` ("gen") on every
  candidate, the D51 neighbours and D37 repairs included (`from_row()`). EX-ANTE from those three, and consistent with
  the host (no composites or gen row): on the forge.env this tree ships, `compare_arms()` reads "no-data" (D5-PL-M14).
- **forge.env, forge/gen and forge/meaning.py are all in the version.** `in_pipeline()` is a deny-list and excludes
  none of them. Nothing the loop runs imports forge/gen or meaning.py, and they still moved the dev id (round 3 S14's
  "an unimported file moves the id", now nine files). Turning the branch on is a forge.env edit (D50), hence a new
  pipeline_version, and `compare_arms()` compares within one.
- **The pinned scorer reaches the arms' reader, not their writers.** `case_compare_arms()` pins `compare_arms()` on
  synthetic rows. forge/meaning.py and forge/gen are outside `scorer_closure` (benchmark imports neither), so a change
  to what the pipeline WRITES (`ARM`, a meaning row, `gen_route`) moves no case. `JOURNAL_KEEP_META` has no
  `gen_route` (D5-X-SC-S1).
- **The watch is a command, not a daemon.** `_push_inner()` neither starts nor prints it (its draw4_build release R1
  comment), and `_watch_inner()` refuses a push older than `WATCH_MAX_AGE_S` (60 min). D43's rollback happens only if
  a person runs `deploy.py watch` inside that hour.

## 2. D43-D53: where each is implemented

No row runs on the host (§0). "Open" lists the ids filed against the implementation.

| # | decision | implemented in | state, and what is open against it |
|---|---|---|---|
| D43 | the watch rolls back only a crash before dispatch; an error after dispatch is reported | deploy `_judge()`, `_round_report()`, `_crashed_before_dispatch()`, `_round_problems()`, `_watch_inner()`, `_watch_rollback()`, `_watch_timeout()`, `_not_rolled_back()`, `_record_watch()`, `WATCH_OUTCOMES`; forge_loop.sh `auth_gate` and the step markers; benchmark `WATCH_KEEPS_RUNNING`, `WATCH_ROUND_FAILED`, `_is_watch()` | [DEV]. Open: the watch can roll back a push it is not watching (D5-X-RL1, SERIOUS); the background probe's exit can go unseen (D5-RL-2); S4 is a `timeout_cause`, not an outcome (D5-RL-12); a data-caused planner crash reads as code (D5-RL-10); `watch_not_rolled_back` is a DORA change failure (D5-SC-M10) |
| D44 | push refuses while unlisted library YAML sits on the target, and deletes only with a flag | deploy `_push_inner()` (the refusal names every file), `_library_extras()`, `remote_library_yaml()`, `remove_library_extras()`, `main()` `--delete-unlisted-library` | [DEV]. With the flag, the removal prints counts, not names (D5-RL-7) |
| D45 | a cohort's exposure comes from the run_config transitions the runner records | runner `record_run_config()`, `note_run_config()` (live starts only: round 3 X3), `RUN_CONFIG_LOG`; benchmark `cohort_live_days()`, `load_run_config_log()` | [DEV]; no log on the host. Open: a too-deep line disables the log (D5-PL-M7); an exit-2 round writes a row (D5-PL-M12); "live start only" is unrecorded (D5-PL-M15); the host key, and no copy off the VPS (D5-PL-M17); a part-day host counts (D5-SC-M3); SUSPECTED D45 x D47 (D5-PL-S1) |
| D46 | `--plan` rows carry the stamps of the code that ran them; orphans recover the dispatched pair | runner `stamp()` (overwrite), `run_config()` (`plan_sha256`); recover_orphans `load_plans()` (`<seed>.json` only), `match()`, `ROUND_KEYS`, `COHORT_KEYS` | [DEV]. Open: a dry copy's pair is lost as `ambiguous` (D5-PL-M9); a re-dispatched numeric plan (D5-PL-M10); `made_at` in a plan re-keys run_config (D5-PL-M16) |
| D47 | the branch is proven by rounds randomised within each ET day, with a day-stratified exact test within cell | benchmark `compare_arms()`, `ARMS`, `ARMS_DESIGN`, `_arms_strata()`, `_arms_decision()`, `arms_mdr()`, `MIN_SHARED_DAYS`, `render_arms()`, `COMPARE_IS_NOT_GATE3`; runner `stamp()` (the arm), `PLAN_FILE_ARM` | the READ-OUT is [DEV]; the RANDOMISER is NOT YET, and the read-out has no caller (§1). Open: the branch's own neighbour and repair rows count as arm B (D5-X-SC-S1, SERIOUS); `--ab new` leaves no composites row (D5-PL-M14 = D5-SC-M15); `MIN_SHARED_DAYS` has no decision (D5-SC-M14); one pipeline_version per read-out (D5-SC-M13); rows with a marker run_config are dropped uncounted (D5-SC-M12); round 3 X1 (R3-X1) |
| D48 | the 7-day incumbent freeze is dropped | nothing to build, and no code names D48; `compare()` carries no window rule | decided. What remains is D5-SC-M13: every pv-moving push restarts `compare_arms()`'s day count |
| D49 | every accepted POST counts against the version that created the alpha, whatever its lag | benchmark `_submissions()` (its second map), `_grade()`, `axis1_product()` | [DEV]. Open: the texts understate it, since a late POST can flip `floor_met` and the verdict (D5-SC-M23) |
| D50 | FORGE_ARGS and N in /opt/wq/forge.env, shipped by PLAN | vps/forge.env; deploy `PLAN`, `FORGE_ENV`, `_forge_env_from()`, `shipped_production_args()`, `smoke_command()`, `run_smoke()`; forge_loop.sh `load_forge_env`; vps/systemd_wq-forge.service `EnvironmentFile=` | [DEV]; on the host the file is absent and the unit edit is not made (§0). Open: the parser and bash disagree on CRLF, `\x0c` and `N=²` (D5-RL-1); the unit test pins the current file (D5-RL-4); the ROUNDS=1 exception is unrecorded (D5-RL-Pb) |
| D51 | each generated alpha that clears every check is re-simulated at two one-setting neighbours before it can be submitted | forge/gen repair `neighbours()`, `existing_neighbours()`, `one_setting_variants()`, `NEIGHBOURS`; propose `propose()` (neighbours first, from `handed`) | [BUILT], NOT INTEGRATED: nothing calls `propose()`, and forge/submit.py holds no alpha for want of neighbours. Open: neighbours are counted from every cohort while the judge counts the alpha's own (D5-X-GE-G1, SERIOUS); `handed` is unfiltered (D5-GE-N2); a shortfall is silent (D5-GE-N3); the neighbour cascade (D5-GE-N4); a push between the rounds splits the pool (D5-SC-S1) |
| D52 | G4 fails only when every leg is crowded; grouping fields excluded; pinned on the four POSTs | forge/meaning `_g4()`, `legs_of()`, `_count()`, `GROUPING`, `CROWDED`; forge/tests/test_meaning.py | [BUILT] (meaning is signed); called by nothing the loop runs. Open: the minimum or the maximum per leg (D5-X-ME-T1, a tick); benchmark's `MEANING_DECIDABLE` comment reads G4 the other way (D5-SC-M27) |
| D53 | the 50/50 share of D47 | NOT YET: there is no randomiser to hold a share | EX-ANTE (code): `ARMS_DESIGN`'s test conditions each stratum on n_b / (n_a + n_b), so the read-out does not assume 50/50 |

## 3. What changed since draw 4, and why

Round 3 kept draw 4's boxes and broke its post-deploy half: the D33 read-out (F1, S14) and the watch (S2-S5). Draw 5
changes those, adds the branch's first code, and moves the branch's switch into the release unit. Each row names the
function and the finding or decision that produced it.

**The scorecard (benchmark bc318f2f -> b30d255c)**

| change | where | why |
|---|---|---|
| the branch is read against the incumbent within (ET day, cell), withheld below 5 shared days, with its own MDR at arm A's rate | `compare_arms()`, `ARMS_DESIGN`, `_arms_strata()`, `_arms_decision()`, `arms_mdr()`, `MIN_SHARED_DAYS` | round 3 F1; D47; round 3 m3 for `arms_mdr()` |
| `compare()` prints that it is not gate-3 evidence before anything else | `COMPARE_IS_NOT_GATE3`, `compare()` | round 3 F1, its fix item 4 |
| every accepted POST costs rank level 1, whatever its lag | `_submissions()` | round 3 S1; D49 |
| a meaning row counts only for its own formula, only after creation, earliest first | `meaning_index()` | round 3 S8 (b) items 1-3; item 4 is NOT done (its docstring) |
| a run_config cohort takes only the days the log gives it | `cohort_live_days()`, `load_run_config_log()` | D45; draw4_build scoring 2 |
| an `ambiguous` run_config forms no cohort | `_forms_cohort()` | draw4_build scoring 3 and pipeline 2 |
| the comparable-from date survives the DST change | `comparable_from()` | draw4_build scoring 5 |
| journal rows are reduced to the fields a card reads | `read_journal()`, `_reduced()`, `JOURNAL_KEEP_META` | round 3 S10 (the reader's half; "STILL LINEAR", its docstring says) |
| watch rows are read, and never counted as deploys | `WATCH_KEEPS_RUNNING`, `WATCH_ROUND_FAILED`, `_is_watch()`, `live_days()`, `dora()` | draw4_build scoring 1; D43 |
| `--record` needs `--version` | `main()` | draw 4 §4 item 2 and §5 item 3 |

**The pipeline (runner 9cdf8d90 -> d2e84b70; recover_orphans 0a5ae8a9 -> 99aae169)**

| change | where | why |
|---|---|---|
| a live start appends its (pv, rc) transition under one exclusive lock | `record_run_config()`, `note_run_config()` | D45; round 3 X3 |
| run_config hashes the plan's bytes | `run_config()`, `RUN_CONFIG_EXCLUDED` | the orchestrator decision recorded with D43-D46; draw4_build pipeline 6 |
| the plan index is `<seed>.json` only, and the stamps are overwritten | `load_plans()`, `stamp()` | D46; draw4_build pipeline 1 |
| gen_state joins the round key | `ROUND_KEYS` | round 3 S15 |
| a row with no arm gets its planning mode | `stamp()`, `PLAN_FILE_ARM` | D47 |

**The branch (new files: forge/gen, forge/meaning.py)**

| change | where | why |
|---|---|---|
| the generator as pure functions: reward, priors, posterior, family, spending rules, repair, neighbours, state sha | `propose()`, `posterior.y()`, `FamilyIndex`, `spend.verdict()`, `repair.neighbours()`, `state.build()` | D34-D38, D51; round 3 S13 |
| the rule half of D19 for an alpha that passed | `meaning.score()`, `_g4()`, `_g8()`, `check_row()`, `append()`, `decidable_verdict()` | D39 (the writer); D52; round 3 S12, m18, X4 |

**The release (deploy 39c7479c -> 7ff14dbc; forge_loop.sh a9f2c313 -> a0b3df46; forge.env and the unit files)**

| change | where | why |
|---|---|---|
| N and FORGE_ARGS ship, smoke and roll back with the code | `PLAN`, `_forge_env_from()`, `shipped_production_args()`, `run_smoke()`; forge_loop.sh `load_forge_env`; the unit's `EnvironmentFile=` | round 3 S5; D50 |
| the watch reads a round through `round end`, rolls back only a crash before dispatch, and reports the rest | `_round_report()`, `_crashed_before_dispatch()`, `_round_problems()`, `_judge()` | round 3 S2, S3; D43 |
| exit 2 means "exhausted" only with the runner's own words | forge_loop.sh (its RC = 2 branch), `_crashed_before_dispatch()` | round 3 S2 |
| an auth-gate crash has its own marker, and an import crash is D43's class | forge_loop.sh `auth_gate`; `_judge()` | round 3 S4 |
| the quota sleep is computed in New York time | forge_loop.sh `next_reset`, `quota_sleep` | round 3 S9 |
| push refuses on unlisted library YAML unless told to delete it | `_push_inner()`, `remove_library_extras()` | D44 |
| the watch refuses until the target's judge reads its rows | `judge_maps_watch_rows()` | draw4_build release R1 |
| the judge records one card per cohort, with limits | wq-judge.sh; wq-judge.service `MemoryMax=3G`, `Nice=19`, `TimeoutStartSec=1h` | draw 4 §4 item 2; round 3 S10, m11 |
| measuring the loop's closure writes no bytecode | `loop_closure()` (`-B`) | round 3, Disclosures (R3-D1) |

**The gate (ci_gate b920db59 -> 62d1c28c; ci_fixture cb4aff28 -> e2feced0; golden e1d79f09 -> d8a0cc0e)**

| change | where | why |
|---|---|---|
| test files outside TEST_DIRS are classified, and an unlisted collectable one is run | `check_test_files()`, `NOT_RUN_OUTSIDE_TEST_DIRS` | round 3 S6 (its fix said "block"; the code runs it: D5-CI-10) |
| one case runs `build()` on a frozen miniature state | `case_input_layer()` | round 3 S7 (partial: D5-CI-11) |
| cases for the arms, the run_config exposure and the watch rows | `case_compare_arms()`, `case_run_config_exposure()`, `case_watch_rows()` | D47; D45; draw4_build scoring 1 |
| a tests result with no `incomplete` key blocks | `known_red_verdict()` | draw4_build ci 3 (it turned test_ci_publish.py red: D5-X-RL2) |
| ci_publish's flags must be typed whole | ci_publish `main()` | round 3 m8 |

## 4. What draw 5 still does not do

1. **None of it runs, and none of it can ship yet** (§0). The host runs the 02:30 ET push, GitHub holds draw 2, and no
   publish record exists. Four of six draw-5 modules are unsigned, and three push preconditions are open (D5-X-RL2,
   D5-X-CI-P2, D5-X-CI-P3).
2. **The branch produces nothing.** Four integrations are NOT YET (§1, the dashed box): `runner --mode gen`, the round
   randomiser (D47, D53), live D51 re-simulations, and the submit meaning route (D39); round 3 S11's twin hold with
   them. No row carries arm `gen` anywhere (§0). These are design 04 §7 stages 3 and 4.
3. **D47's read-out cannot be read.** It has no caller (`main()` has no flag for it; wq-judge.sh does not run it); on
   the shipped forge.env it reads "no-data"; and it cannot tell the branch's fresh draws from its own follow-ups
   (D5-X-SC-S1). `ARMS_DESIGN` pre-registers a direction at α. The gate-3 rule design 04 §6.2 recommends (at least 2x
   with p < 0.05 at a stated horizon; gate 4 on S3) is in no code and no decision.
4. **D51 and the judge count different neighbours** (D5-X-GE-G1): `existing_neighbours()` counts every cohort's rows;
   `neighbourhood_stability()` sees the alpha's own cohort pool only.
5. **D36's count rules cannot fire through draws** (D5-X-GE-G3). 1,500 of 1,500 draws founded their own family, and 0
   of 1,124,250 pairs were near-duplicates. POST-HOC, one seed, an empty posterior; family sizes under a concentrated
   posterior are UNMEASURED. The tick is pending.
6. **The judge still grades with the pipeline's own instruments** (round 2 S8-NL ii; round 3 S8 option (a) not
   taken). The meaning rows come from forge/meaning.py, DSR and PBO from harvest, the correlation lines from the probe.
   `_standard_gate()` still routes on the `gen:` prefix of `meta.hypothesis` (S8 (b) item 4, in `meaning_index()`'s
   docstring).
7. **Axis 3 cannot see forge/gen** (D5-GE-N9): `_modules_with_a_real_test()` globs forge/*.py, and `import_cycles()`
   reads a package's top level only.
8. **The judge's memory is still linear in the journal** (`read_journal()`: "STILL LINEAR"; streaming by quota day is
   not built), and wq-judge.sh runs one `build()`, which re-reads the whole journal, per cohort.
9. **D9's regression half is run by hand only.** `compare()` is reached only from `main()` `--compare`, and nothing
   records a comparison (round 2 A2).
10. **D16 cannot meet "before any quota is spent"** (D43 narrowed it), and the watch exists only when a person runs it
    within 60 min of the push (§1).
11. **Decisions still open:** φ for one stamped version is UNMEASURED (§0); D7's "held" waits on a tick (R3-N1); D28's
    direction rule loses power once events spread over cells (R3-m4); the meaning ticks (D5-X-ME-T1 to D5-X-ME-T4);
    the arm-B definition (D5-X-SC-S1); how check_no_live treats forge/search.py's run_recipe (D5-X-C8).
12. **The backlog:** 156 of 242 rows open (`backlog.md`, Counts).

## 5. The attack surface I expect round 4 to find, written before any attack

Each item is a prediction, not a finding, and none has been run as an attack. Its label says what it rests on.

1. **Where the round randomiser lives decides what breaks** (EX-ANTE, code; the randomiser is not designed). If
   forge_loop.sh gives each arm its own FORGE_ARGS, `run_config()` hashes `mode`, `note_run_config()` appends a row at
   every switch, and `cohort_live_days()` excludes every day on which the run_config changed: both arms' cohorts count
   0 days (D5-PL-S1). If the runner picks the arm under one argv, one run_config holds both arms, and wq-judge.sh's one
   card per cohort grades incumbent and branch rows pooled as one version (D1, D14). No decision chooses.
2. **D43's watch and D50's smoke each see one arm** (EX-ANTE, code). `_judge()` stops at the first round that did work
   on the pushed pv; `run_smoke()` plans the one (N, FORGE_ARGS) that `shipped_production_args()` returns. Under D47 a
   push whose gen planner crashes before dispatch stands whenever the first round after it is an incumbent round. If
   the arm is a function of the seed, the smoke's seed (`PLANNER_SEED`, walked to the first free one) would pick the
   same arm on every push (SPECULATION: it depends on item 1's design).
3. **The D47 read-out can be peeked** (EX-ANTE, code). `ARMS_DESIGN` holds a minimum (`MIN_SHARED_DAYS`), no horizon
   and no ratio threshold. `compare_arms()` decides at whatever `now` it is given past 5 shared days, and no caller
   fixes that clock (§1). The size test_benchmark pins is a single-look size; the size under daily looks is
   UNMEASURED.
4. **Incumbent exhaustion starves the branch** (EX-ANTE, forge_loop.sh; the frequency is POST-HOC: round 3 S2 counted
   5 exhausted rounds in 182). An exit 2 with "library is exhausted" sleeps the whole loop 3,600 s, whichever arm would
   run next. A day whose incumbent rounds exhaust leaves strata that only one arm scored in, which `_arms_decision()`
   counts and never decides on.
5. **The arms share state the test assumes they do not** (EX-ANTE for the paths; the size is UNMEASURED). One journal
   feeds the allocator (D5-GE-S3: `cold_cells` counts gen rows) and harvest's quarantine; one submitter serves both
   arms, under the one daily limit of 4 submissions and one SELF line against the accepted POSTs. `compare_arms()`'s
   docstring assumes that within a (day, cell) the two arms' alphas "differ only by arm". Design 04 §6.2 named
   interference between feedback-on and feedback-off rounds; D47 moves it between the incumbent and the branch,
   where no text names it.
6. **A generated alpha's DSR is a PSR against zero** (EX-ANTE, code; the input is POST-HOC, D5-X-GE-G3). D38's pool is
   `harvest.pool_key()` with hypothesis gen:<family>; G3 found every draw its own family; `dsr.expected_max_sharpe()`
   returns 0 for one trial, and `dsr.var_sr_from_annual_sharpes()` returns 0 for fewer than two values. A library alpha
   is deflated over its hypothesis pool. D38 named "a correction near zero"; the asymmetry it creates in harvest's
   submittable set between D47's arms (gate 4, design 04 §6.2 S3) is named nowhere. D24 is unaffected: no DSR check is
   in `BINDING`.
7. **The pass-first order is still documentation, now with three holds missing** (EX-ANTE, code). The day
   `--mode gen` exists, forge_loop.sh runs `forge/submit.py --submit --cap 4` with no meaning route (D39: a failed
   decidable gate must not POST), no D51 hold (two neighbours before a submit) and no S11 twin hold. Nothing calls
   `meaning.append()`, so `load_meaning()` returns None, `_standard_gate()` reads None, and every generated submission
   counts against rank level 1 (D26). Draw 4 §5 item 5 predicted the first half; architecture_round3.md does not
   mention it (grep).
8. **An in-pipeline fix resets the D47 clock for both arms** (EX-ANTE; the edit rate is round 3 S14's POST-HOC lower
   bound). The queued gen fixes (D5-X-GE-G1, D5-X-GE-G2), a meaning MINOR or a forge.env flip each move the
   pipeline_version (§1), and `compare_arms()` counts shared days within one. Round 3 S14 found no 7-day stretch
   without an in-pipeline edit while the loop ran; D47 needs 5 shared days per version.
9. **The watch is armed by a person, within an hour** (EX-ANTE, code). Nothing starts `deploy.py watch` or records that
   it was not run; `_watch_inner()` refuses after `WATCH_MAX_AGE_S`. D43's rollback is as reliable as the operator, and
   `dora()` reads a push nobody watched as no change failure.
10. **The judge still believes the pipeline's meaning** (EX-ANTE; round 2 S8-NL ii, round 3 S8 option (a)).
    forge/meaning.py is outside `scorer_closure`, so an edit to `_g4()` changes real verdicts and moves no golden case;
    under D5-X-ME-T4 (the earliest row wins) a corrected scorer never re-grades an alpha already scored. D39's rule is
    written twice, in `decidable_verdict()` and `_standard_gate()`, and test_meaning ties them, not the golden.
11. **No test crosses the arm seam** (EX-ANTE; grep of forge/tests and tools/tests). test_benchmark pins `ARMS` against
    a literal, and nothing runs a runner-stamped or forge/gen-stamped row through `_arms_strata()`. A rename on either
    side reads "no-data": it fails closed, so MINOR.
12. **The first push is a big bang** (MEASURED host bytes, §0; the rest EX-ANTE). It ships D30, D43, D45, D46, D50,
    forge/gen and forge/meaning.py at once onto a host that has none of them. The smoke's `pytest forge/tests -x` now
    runs the gen and meaning tests, one of which reads the host's submitted.jsonl (D5-ME-M10). A red smoke rolls the
    whole release back, and the three-line tail `run_smoke()` prints does not say which change failed.
13. **D49 un-finalises a final card** (EX-ANTE; D5-SC-M23). A POST of an old alpha after `comparable_from()` changes
    rank level 1 for every card built after it; `record_key()` keeps the first card of each day, so two recorded cards
    of one cohort can disagree with no row saying why. D27's finality now covers credit only.

The check behind this section is `scratchpad/d5_doccheck.py`, kept out of the repository for draw 4's two reasons:
this task owns this file only, and a new test file under forge/tests or tools/tests moves `ci_classify.tests_hash()`,
which makes the classification stale and blocks the hermetic tier (`check_tests()`; D5-X-CI-P2 is that stale state
already). Over this section it checks that every call written with parentheses, bare or behind a module prefix, is a
def or class in the files of §0 (plus forge/submit.py, forge/harvest.py, forge/dsr.py, forge/offline/branch_drill.py
and tools/layered_sim.py); every upper-case name with an underscore, backticked or in the diagram, is a module-level
assignment there; every forge_loop.sh function named is defined in it; a table row exists for each of D43-D53; every
backlog id cited is a row of `backlog.md`; every "round 3 <id>" is a heading or bold id of `architecture_round3.md`;
and every "draw4_build <module>" and "draw5_build <module>" section exists. It fails on this file without this
section, and on each of the mutants listed in its own header.
