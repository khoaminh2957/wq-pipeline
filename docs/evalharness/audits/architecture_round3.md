# evalharness: architecture round 3, adjudication (2026-09-23)

This file rules on five attacks on Draw 4 of `docs/evalharness/01_architecture.md`: statistician, gamer, systems,
CI/CD and pass-first fit. Round 3 is the first round that can count toward D15. Every finding was checked
against `architecture_round1.md`, `architecture_round2.md`, `draw3_fix.md` and `draw4_build.md`, and against
`deploy.md` where an attacker cited it.

**Snapshot judged.** These are the Draw 4 bytes (sha256 prefix): benchmark.py bc318f2f, ci_gate.py b920db59,
ci_classify.py 6978aced, ci_publish.py f2f40ac0, deploy.py 39c7479c, runner.py 9cdf8d90, ci_fixture.py cb4aff28,
ci_golden_card.json e1d79f09, ci_known_red.json 06f0ccc1, ci.yml 55d481af, recover_orphans.py 0a5ae8a9 and
wq-judge.sh dcd49f1b. I also read vps/forge_loop.sh a9f2c313 and forge/submit.py 07df3bdf. I re-hashed all of
them at 21:06 +07 and they were unchanged.

**Method.** I re-derived every finding kept below myself, on a quiet snapshot
(`scratchpad/adjr3/snap`: an rsync without .git, state and fetched; state is an APFS clone; fetched is a symlink).
Everything ran with `python3 -B` and no `__pycache__`. Where I used an attacker's script, I first pointed it at my
snapshot instead of the repository. Scripts are in `scratchpad/adjr3/v/`:

| script | what it checks |
|---|---|
| `v1_disp.py` | per-day D24 counts within cell, written without benchmark.py |
| `v2_placebo.py` | the size of the D28 decision under H0 |
| `v3_unanimity.py` | the power of D28's direction rule |
| `v4_gen.py` | generated alphas and the meaning reader |
| `s5_rank_and_finality.py`, `s4_mdr.py`, `g_late_post.py`, `p_quar.py` | attacker scripts, re-pointed |
| `../rss/run.py` | peak RSS |

Two files were mutated and restored, and each was cmp-equal to the repository afterwards: mint_link.py, and the
Mac journal (swapped for the host copy). I simulated nothing and passed no --live or --submit. I made no ssh call
of my own. The host files I read are the attackers' read-only scp copies: loop.log, forge.jsonl, DEPLOYED.json
and a copy of the host's deploy.py. I edited no file other than this one.

Origin labels follow RULE 0:
- `EX-ANTE (code)`: read from the code or spec.
- `POST-HOC`: a regularity seen in data.
- `SPECULATION`: neither.

No mechanism is claimed for any data regularity.

---

## Verdict

| class | FATAL | SERIOUS | MINOR |
|---|---|---|---|
| NEW | 1 | 15 | 20 |
| EARLIER FIX DID NOT LAND | 0 | 0 | 3 |

There are also 5 SUSPECTED items.

**D15 clock: does NOT start.** Round 3 found 16 NEW FATAL or SERIOUS defects. Draw 4's structure holds: three
boxes, the judged never imports the judge, and pre-merge is split from post-deploy. What fails is two things:

- **D33's proof protocol.** Its statistical test is invalid at the only dispersion ever measured (F1). Its 7-day
  window cannot survive the release path as built (S14).
- **The D16/D43 watch.** It reads the runner's lines only. It cannot tell a crash from an exhausted library or
  from an auth outage, and the config switch that turns a branch on lies outside the release unit (S2, S3, S4,
  S5).

Fixing F1 changes the design, so Khoa must tick it (RULE 2). A partial redraw is needed for the post-deploy half:
the D33 read-out and the watch. Everything else can be fixed inside Draw 4.

---

## FATAL (NEW)

### F1. D33's sequential proof decides with a test whose false-verdict rate is about 50 % at the measured dispersion

**Source.** Statistician, FATAL.

**Root.** Round 2 X1 was SUSPECTED at the time. It is now measured on the D24 estimand itself, inside the one cell
that holds every event. Draw 4 §4 item 13 and compare()'s docstring say "no dispersion WITHIN cell has been
measured". That is no longer true.

**Where.** `compare()` (the `stratified_rate_test_p()` p-value plus the rule that every event cell points the same
way), `_dispersion()`, `ESTIMAND["test"]` and `["decides"]`; D28 × D33.

**Evidence.** All of this was re-derived by me.

- **Within-cell dispersion** (`v1_disp.py`, independent code). All 37 D24 events lie in USA/d1.
  - Mac copy, 9 whole ET days: 37 of 22,815, χ² 90.73 on 8 df, **dispersion 11.34**.
  - Host copy (statistician's scp), 10 days: 37 of 24,845, χ² 102.09 on 9 df, **11.34**. The 95 % interval for φ
    from the χ² quantiles is [5.4, 37.8].
  - All cells pooled: 11.99 (Mac) and 11.80 (host).
  - So a cell mix that shifts by day, the third candidate in the docstring, does not account for the dispersion.
  - Per day: 09-04 3/958, 09-05 6/1,680, 09-06 12/2,977, 09-07 0/3,908, 09-08 0/4,317, 09-09 1/4,266,
    09-10 13/1,340, 09-11 1/1,080, 09-20 1/2,289, and on the host also 09-22 0/2,030.
- **Within a day, across rounds (meta.seed):** χ² 132.3 on 129 df, dispersion 1.03. This is POST-HOC. Counts at
  round level look binomial, and the extra variation sits between days. MECHANISM: UNKNOWN.
- **Size of the real decision under H0** (`v2_placebo.py`: the real `stratified_rate_test_p` plus the direction
  rule):

  | model | 7 days/arm | 14 days/arm | 28 days/arm |
  |---|---|---|---|
  | day-block bootstrap of the 9 real days | 0.488 | 0.501 | 0.486 |
  | gamma-Poisson days, φ = 1 (control) | 0.036 | | 0.045 |
  | gamma-Poisson days, φ = 2 | 0.148 | | 0.168 |
  | gamma-Poisson days, φ = 4 | 0.300 | | 0.307 |
  | gamma-Poisson days, φ = 11.34 | 0.540 | | 0.547 |

  - The closed form 2(1 − Φ(1.96/√φ)) gives 0.166, 0.327 and 0.561 at φ = 2, 4 and 11.34.
  - More days do not reduce the size.
- **A real pair of adjacent windows** (Mac, USA/d1):
  - 09-04..06 is 21 of 5,615 and prints dispersion 0.09.
  - 09-07..09 is 1 of 12,491 and prints 0.96.
  - The stratified p is 6.5e-10, a verdict of "worse". Neither arm's printed dispersion shows anything, because a
    step BETWEEN windows is invisible to a dispersion computed WITHIN each one.
  - Whether code, allocation state or the platform changed between those days: UNKNOWN. The era is unstamped.
- **What 7 days can detect** (the real `minimum_detectable_ratio`, 7 × 3,197 × 0.87 scored per arm, exposure
  divided by φ):
  - at φ = 1: 1.87–2.10× upward;
  - at φ = 11.34: 5.3–6.8× upward, and no decrease is detectable (the range is over the bases 37/22,815 and
    37/33,436).
  - The statistician's days-per-arm for a 2× MDR at φ = 1, 5.37 and 11.34 are 7, 33 and 70. I did not re-derive
    these.

**Caveat, first.** No stamped version has ever run a whole day, so φ for ONE version is UNMEASURED. The 11.34 is
the unstamped era's. It may include code changes. Even φ = 2 triples the nominal 5 % size.

**Consequence.** D33 accepts calendar confounds and lists them. It does not account for this: under no version
effect, the ticked D24/D28 read-out says "better" or "worse" about half the time. That read-out is the gate-3
evidence RULE 2 asks for.

**Fix (Khoa tick; RULE 2).**
1. Make the whole ET day the unit in compare(). Use a within-cell permutation of whole-day blocks, or a
   quasi-Poisson / negative-binomial rate ratio with φ estimated from each arm. Withhold the verdict below a
   minimum day count, and print the MDR on the same unit.
2. Measure the stamped incumbent's φ over its first ≥ 7 whole days before any D33 read-out.
3. Put the arithmetic on the tick: at φ ≈ 11, 7 days cannot show 2× with any valid test. Within-day round
   randomisation is the design whose test holds (φ 1.03), and it needs D21 reopened (round 2 A1 option (a)).
4. Correct compare()'s docstring and §4 item 13.

Test: the day-block placebo must read "better" or "worse" at most about 5 % of the time.

---

## SERIOUS (NEW)

### S1. An unproven or refuted alpha POSTed more than 14 days after creation costs its version nothing

**Source.** Gamer.

`_submissions()` drops any POST with `t − created > POST_HORIZON_DAYS`. Rank level 1 (D26) counts only what
`_submissions()` credits. So the horizon from A4, which was meant to bound credit, also bounds the penalty.
`forge/submit.py eligible()` has no age filter (EX-ANTE, read).

**Evidence** (`g_late_post.py`, real `build_from` and `rank_key`):

| u0 (unproven) POSTed after | rank_key |
|---|---|
| 13.00 d | (1, 1, −1.0, −1.0) |
| 14.00 d | (1, 1, −1.0, −1.0) |
| 14.05 d | (1, **0**, −1.0, −1.0) |
| 15.00 d | (1, **0**, −1.0, −1.0) |

- Second way, calling `_submissions` directly: u0 is credited at a lag of 13 d and not at 15 d.
- `posts_this_version_made` counts it, but only as a report.
- POST-HOC, Mac copy at 09-23 00:00 ET: 19 of the 33 unposted `candidate` alphas are already more than 14 d old.
  The real lags so far were 0.01, 0.77, 0.02 and 11.49 d.

**Fix (tick; D26 × A4).**
- (a) Count every accepted POST of a cohort's alpha against level 1 whatever its lag, and keep the horizon for
  credit and finality only.
- (b) Or attribute a late POST to the version that made it.

Test: the 15-day case must read level 1 = 1.

### S2. The watch reads any exit 2 with no Traceback as healthy, and a round that simulated nothing as a pass

**Source.** Merged from gamer (SERIOUS), CI/CD (SERIOUS) and pass-first (part of its SERIOUS 1).

`_round_failed()` accepts `_ROUND_OK_EXITS = (0, 2)`. argparse also exits 2. So does `runner.main()`'s
"nothing to simulate".

**Evidence:**

- **argparse.** On my snapshot, `forge/runner.py ... --mode gen` (no --live) gave rc 2 and "argument --mode:
  invalid choice: 'gen'". No plan was written (156 plans before and after). Fed through the real functions in the
  loop's log layout:
  - `_round_verdict` gives {exit 2, traceback False};
  - `_round_failed` gives **False**, i.e. watch_ok;
  - `_smoke_ok('planner', 2, same text)` gives False.
- **The loop.** `vps/forge_loop.sh` logs every RC 2 as "library exhausted" and sleeps 3600 s.
- **D43.** A planner that fails is D43's pre-dispatch crash class, and the watch passes it.
- **Rounds that did no work.** POST-HOC, on the host loop.log copied at 20:20: 182 finished rounds, of which the
  watch would pass 159. 8 of the 159 dispatched nothing:
  - 5 exited 2, and each printed "library is exhausted", so the smoke's message test does separate the two cases
    on real data;
  - 3 exited 0 with no COMPLETE/WARNING line after hitting the daily limit (seeds 1788720800, 1788796277 and
    1788876631).

deploy.md B3 offered two fixes. The {0, 2}-plus-message rule landed for the smoke only. Distinct runner exit codes
never landed.

**Fix.**
- `_round_failed` applies `_smoke_ok`'s rule: exit 2 is healthy only with "library is exhausted".
- Give argparse errors their own code, e.g. `ArgumentParser.error` exits 64.
- Or give "exhausted" a distinct exit code (a tick, because it changes forge_loop.sh's contract).
- A round with no scored journal row of the pushed pipeline_version reads "inconclusive", and the watch keeps
  waiting.

Test: the argparse slice must give `_round_failed` True.

### S3. The watch judges only the runner's lines; harvest, recover_orphans, probe and submit are outside it

**Source.** Missed by all five; found here.

`_round_verdict()` returns at the first `=== round exit` line. `forge_loop.sh` prints that line right after the
runner. recover_orphans, harvest, the probe and `forge/submit.py --submit` all run AFTER it. So does D39's planned
auto-submit route.

**Evidence** (EX-ANTE, read, then run). I built a slice: header, runner output, `=== round exit 0`, then a
Traceback from `forge/submit.py` failing on its lazy `import submit_budget`. The real `_round_verdict` returns
{exit 0, traceback False}, `_round_failed` False, so "the deploy stands".

The smoke's import step imports `forge.submit` and `forge.harvest` at module level only. The lazy imports inside
`submit.main()` (layered_sim, submit_budget, climb_submit, msgcat) are never smoked.

**Consequence.** D43 says an error after dispatch is REPORTED. The watch cannot report one it never reads. A push
that breaks harvest or submit spends every day's quota with nothing scored or posted, and the watch says it stands.

**Fix.** Read the round through the next round header, or add explicit step markers to forge_loop.sh. Report
(D43) any Traceback or non-zero exit of harvest, recover_orphans or submit in the first round after the push.

Test: the slice above must read "reported: post-dispatch error in submit".

### S4. The auth gate hides an import crash as "auth dead", and the watch then says silence is not a crash

**Source.** Systems.

**Root.** deploy.md F14 recorded the same masking for the smoke ("not armed"). The watch (Draw 4) and D43 inherit
it, and that is new.

**Evidence:**
- forge_loop.sh's gate runs `import layered_sim as LS, mint_link as M; LS.session()...` with `2>/dev/null`, and on
  any non-zero exit logs `=== auth dead ...` and `continue`s. It prints no round header.
- On my snapshot, with one unparsable line appended to mint_link.py, the gate's own snippet exits 1 with nothing
  printed. The file was then restored and cmp-equal.
- The smoke's import step leaves `layered_sim` and `mint_link` out of `sys.modules` (both False, measured).
- `_watch_inner` then times out after 60 min with "Nothing was rolled back: D16's trigger is a crash, and silence
  is not one".
- POST-HOC: the copied loop.log holds 4,077 auth-dead lines. With gaps of up to 15 min they form 14 stretches of
  1 h or more; the longest is 81 h. With a looser join the systems attacker found 7 stretches, up to 223 h. Every
  one of them is longer than the watch window. MECHANISM of the outages: UNKNOWN.
- The same blindness covers the two pre-header steps, record_adjudication.py and refresh_cells.py, which run with
  `|| true`.

**Fix.** The gate prints a distinct marker on an exception in the import or session step, e.g.
`=== auth gate crashed: <exc> ===`, with the traceback, and the watch treats that marker after live_at as D43's
pre-dispatch crash. On timeout, the watch prints its count of auth-dead lines and records a distinct outcome.
Re-arming a watch when auth returns is a new mechanism and needs a tick.

### S5. The switch that turns a branch on lies outside the release unit, and a rollback restarts old code under new arguments

**Source.** Merged from CI/CD (SERIOUS 1) and pass-first (SERIOUS 1).

EX-ANTE (read), with the argparse step run:

- **No smoke on the switch.** `_push_inner()` returns `noop` before it reads the unit's arguments. So after an edit
  to FORGE_ARGS (D30: deploy never touches /etc/systemd), pushing the same tree runs no smoke and records no
  `production_args`.
- **Rollback under the new arguments.** `_undo()` restores the tree and calls `start_units()` with no planner smoke
  on the restored tree under the unit's current arguments. With the unit already on `--mode gen`, the restored
  runner exits 2 from argparse (measured above).
- **The result.** forge_loop.sh then sleeps 3600 s every round. push reports `rolled_back`, and S2's watch reads
  that exit as healthy.
- **Either order of the flip loses D16 for the branch.** Flipping after the push means the smoke planned
  composites. Flipping before means any rollback strands the loop.
- **Latent** until design stage 5.

**Fix (tick; touches D30).** Choose one:
- (a) FORGE_ARGS and N move to an EnvironmentFile that PLAN ships.
- (b) push refuses when the unit's arguments differ from the last deployed row's.
- (c) `_undo()` re-runs the planner smoke with `remote_production_args()` on the restored tree, and leaves the units
  down, loudly, if it fails.
- (d) A written procedure only.

Test: a rollback with the unit on args the restored runner rejects must not end in "units started".

### S6. Tests outside forge/tests and tools/tests are run by no tier; a failing branch test publishes

**Source.** CI/CD. Draw 4 §5 item 6 predicted only the fitness-check half.

**Evidence** (EX-ANTE, read):
- `ci_gate.TEST_DIRS`, `ci_classify.SUITES` and the deploy smoke (`pytest forge/tests`) all pass explicit
  directories.
- In a scratch tree, the gate's own argv (`pytest forge/tests tools/tests -o addopts=`) gave "2 passed", while
  `forge/gen/tests/test_b.py` (assert False) alone gave "1 failed".
- The CI/CD attacker ran the real `data_tier()`. It returned `known-red-only`, which deploy accepts. The control,
  with the same file in forge/tests, returned red.
- In the repository today, 25 shipped `test_*.py` files lie outside TEST_DIRS, all `in_pipeline()`: tools/funnel/*
  (24) and tools/autoloop/test_pipeline.py.

**Fix.** ci_gate blocks when a test file under the published SUBSET lies outside TEST_DIRS and is not listed with a
reason. Derive TEST_DIRS, SUITES and the smoke's path from one function. Extend `_modules_with_a_real_test()` to
forge/**. The 25 legacy files need an owner's decision: run, move or list.

### S7. The D42 truth table never enters the scorer's input layer

**Source.** Gamer.

**Root.** Round 2 A7's class, the golden not pinning decisions, in an area A7's fix did not reach. draw4_build ci 1
found one clause. This is the whole layer.

**Evidence** (EX-ANTE, read):
- `ci_fixture._Desk.card()` calls `build_from()` directly. The fixture never calls `load_inputs`, `build`,
  `load_standard`, `load_meaning`, `load_curves` or `load_deploys`.
- It never reaches the closure code they call: `SUB.posted_history`, `HV.load_scored`, `P.load_corr`, and the
  journal's "last row wins".
- So an edit there that changes real cards moves no case. The re-record diff is hash lines only, the same shape as
  a comment edit.
- The gamer measured one such edit (load_inputs keeps only the last 7 days of POSTs): the real Mac card went from
  level 1 = 4 to 1, 0 case leaves moved, and the tests stayed at the pristine 2 failed. I did not re-run that
  mutant. By the code read it is certain that no case can move.

**Fix.** Add a truth-table case that runs `build()` on a frozen miniature `state/`, with repeated rows per alpha,
POST stage rows, scored, corr, curves, meaning and deploys, and make the paths injectable. `record_golden` names
the moved closure files that no case executes.

Test: the 7-day-POST mutant must move a case.

### S8. The D39 meaning reader believes any row

**Source.** Gamer. Latent: no writer exists.

**Root.** Round 2 S8-NL(ii), "the judge uses the pipeline's own instruments", on a new instrument.

**Evidence** (`v4_gen.py`, real `build_from` on the fixture's desk; the alpha has two neighbours, so only the
meaning gate decides):

| row given to the reader | status |
|---|---|
| a row whose formula_sha is another formula's | proven |
| route "hand-typed", scorer "nobody" | proven |
| scored_at = 1 (1970) | proven |
| G5 False, then a later all-true row, same sha | proven |
| the reverse of that order | refuted |
| no row, hypothesis h_bad (library) | refuted |
| the same formula labelled `gen:h_bad`, all-true row | proven |

The latest row wins, the sha is compared with nothing, and routing follows the planner-written `meta.hypothesis`.

**Fix (tick with the scoring owner).**
- (a) The judge computes G4's leg clause and G5–G8 itself.
- (b) At minimum:
  - the earliest row per (alpha, formula_sha) decides;
  - the sha is recomputed from the journal's formula and must match;
  - a row scored before the alpha's dateCreated is ignored;
  - `gen:` routing applies only when no library composite matches.

Each needs a test using the rows above.

### S9. The loop's quota sleep uses 11:05 host time; every other part of the desk uses 00:00 America/New_York

**Source.** Systems.

**Evidence:**
- EX-ANTE (read): forge_loop.sh sets `RESET=$(date -d "today 11:05")` in the host zone, which is +07; the log's own
  `$(date)` lines print +07.
- `submit.quota_day()` ("resets 00:00 America/New_York"), submit_budget ("zoneinfo rather than a hardcoded −4") and
  benchmark `ET` all use New York.
- zoneinfo: 00:00 ET is 11:00 +07 on 09-23 and 12:00 +07 on 11-02. 11:05 +07 on 11-02 is 23:05 EST on 11-01.
- No audit names the 11:05 (grep).

**Consequence.** From 2026-11-01 the two encodings of one fact disagree by an hour. Which one the platform follows in
winter is UNKNOWN; it was observed in EDT only.
- If the platform follows New York, a quota-spent loop wakes before the reset, reads the limit again and sleeps
  24 h. The systems model gives 54–56 % of the quota; by hand, (5,000 + 500·55/60)/10,000 = 54.6 %.
- Otherwise, every ET day on the desk misdates the 23:00–24:00 EST hour.
- Either way, a D33 window that straddles 11-01 carries an unlisted confound.

**Fix.** Compute the reset from America/New_York, e.g. `TZ=America/New_York date -d 'tomorrow 00:05'` with the
same guard, and add a test at 2026-11-02. Observe the first EST reset on 11-02 (11:00 against 12:00 +07), and add
DST to D33's confound list.

### S10. The judge's memory grows linearly with the journal, and D41 runs it beside the loop with no limit

**Source.** Systems. This settles round 1 M10, which was SUSPECTED.

**Evidence.** Peak RSS of the real `build(run_drill=False)` (`/usr/bin/time -l`):

| journal | size | peak RSS |
|---|---|---|
| Mac journal | 115.7 MB | 741 MB |
| 3× synthetic, ids suffixed | 347.4 MB | 1,938 MB |

- That is 5.17 MB of RSS per MB of journal. The systems attacker's 1×–8× series gave 4.7–5.1, and 4.52 GB at
  926 MB.
- POST-HOC journal growth while the loop runs: 121.72 MB at 12:38 (deploy.md) to 136.87 MB at 20:14 is
  47.8 MB/day. The systems attacker read 48–50 MB/day in two windows.
- About 16 more live days reach ~0.93 GB and ~4.5–4.9 GB RSS. The host reads 7.4 GB total and about 5.0 GB
  available (systems, read-only).
- `wq-judge.service` has no MemoryMax, Nice or TimeoutStartSec. Latent: the judge is not installed.

**Fix.** Bound build()'s memory: read only the fields a card needs, or stream by quota day. Add MemoryMax= and Nice=
to the unit.

Test: build() on a 3× synthetic stays under a fixed RSS bound.

### S11. The in-invocation twin guard keys on the hypothesis; `gen:<family>` keys remove it

**Source.** Pass-first. Latent: stage 2 is unbuilt.

**Evidence:**
- EX-ANTE (read): after each POST, `submit.main()` drops only entries with the same `mechanism_key` =
  `mechanism#datasets#cell`, and the D18 near-dups.
- 04 §3.3 sets mechanism = `gen:<fingerprint family>`. 04 §5.4 lists the other rules that change and not this one.
- 04 §3.6 records that SELF read minutes after a POST is not trusted: 6 of 8 readings were low.
- The pass-first attacker ran the real `submit.main` with the network stubbed on one real PnL-twin pair (predicted
  SELF 0.994, not near-dups): "posted 1" under the incumbent's keys, "posted 2" under family keys. I did not re-run
  it; the code read supports it.

**Fix.** After each accepted POST, hold every remaining pick whose locally predicted SELF against the just-POSTed
alpha is at or over its line. Alternatively, allow one generated POST per invocation. Name the rule in 04 §5.4.

### S12. D39's "G4 leg clause" has no fixed direction and no unit, and it decides auto-submission

**Source.** Pass-first. Latent.

**Evidence:**
- `fetched/hypothesis_standard.md` gate 4 FAILS "a composite whose every leg has alphaCount >= 200".
- The `MEANING_DECIDABLE` comment reads G4 as the clause "every leg alphaCount >= 200", with PROVEN when it is true.
  04 §4.2 gives no direction.
- Nothing defines a multi-field leg's alphaCount. The four POSTs mix fields from 1 to 446,847 (catalogue, Mac copy):
  sector 446,847, subindustry 379,228, industry 327,837, against executed_short_trade_share_count 10,
  diff_current_vs_hist_price_ratio_earnings 2 and directional_significant_value_1 1.
- Depending on the reading, G4 passes 0 or 4 of the 4 ACTIVE submissions.

**Fix (tick).** Fix the direction to the standard's: trip only when every leg is crowded. Define a leg's alphaCount,
excluding grouping fields. Add a pinned test on the four POST formulas and a truth-table case.

### S13. A generated submission can never be PROVEN: it never has one-setting neighbours

**Source.** Pass-first. This defeats D39's stated purpose by a route D39 did not name.

**Evidence:**
- `v4_gen.py`: a `gen:` alpha with every decidable meaning gate true and no neighbours reads `unproven`; the only
  non-true gate is `neighbourhood_stable: None`. With two neighbours it reads `proven`.
- POST-HOC, Mac journal:
  - the typed arm, the only generated rows on file: 919 rows, 919 distinct formulas, 0 simulated under ≥ 2
    settings, 0 with two one-setting neighbours;
  - the library arms: 7,532 of 19,229 formulas were simulated under ≥ 2 settings.
- 04's generator draws settings per candidate, and only a D37 repair grid re-simulates a formula.

**Consequence.** Under D26 every generated submission counts against its version, and the branch loses every
D25/D26 rank by construction. D33's D24 read-out is row-level and unaffected.

**Fix (tick).**
- (a) Re-simulate each generated harvest-pass at ≥ 2 one-setting neighbours (quota).
- (b) Record neighbourhood as not applicable to generated alphas (a D39 amendment).
- (c) Accept it, and print it on every card.

### S14. D33's 7-day incumbent window cannot survive the release path as built

**Source.** Pass-first. Draw 4 §5 item 1 predicted it; §2's D33 row says "no code enforces". Evidence the
prediction lacked:

- **An unimported file moves the id.** Adding an empty `forge/gen/__init__.py` moves `pipeline_version_of()` from
  b6e639e2674a4dac to b816fad490d0cb2b. A benchmark.py-only edit leaves it at b6e639e2674a4dac. Both were run on my
  snapshot and restored.
- **So building stage 2 in the dev tree splits the incumbent** at the next push of any kind. Under D41, a judge fix
  needs a push, and push ships the whole tree.
- **The dev tree has already moved.** It differs from the host manifest (8f8b7517, pv ec6a5cd75d58fea2) in 9
  in-pipeline files:
  - 6 changed: recover_orphans.py, runner.py, submit.py, auto_submit.py, climb_submit.py and layered_sim.py;
  - 3 new: harvest_loop.sh, recover_harvest.py and wq-forge-tests.sh.
- **D33's text contradicts Draw 4's ORDER.** D33 says "stamping began 2026-09-23 02:30 ET". The ORDER puts the
  stage-0 push first, which re-keys the id. So no ec6a5cd75d58fea2 row can join the incumbent.
- **The measured edit rate** (POST-HOC, pass-first; a lower bound from mtimes): no 7-day stretch without an
  in-pipeline edit has occurred while the loop ran.

**Fix.**
- Record the window's start in the target ledger.
- push refuses, without a named flag, a push whose local pipeline_version differs from the target's while a window
  is open.
- The release note names the frozen checkout.
- Correct D33's start sentence.
- Whether the id should cover files no loop entry reaches is a tick (A10's deny-list).

Test: with a window row present, a pv-moving push is refused.

### S15. A per-round `meta.gen_state` breaks orphan matching for generated rows

**Source.** Pass-first. Latent design conflict, the class of round 1 S1-i.

**Evidence:**
- 04 §3.2 recomputes the loop's state every round and stamps its sha256 on every construction as
  `meta.gen_state`.
- `recover_orphans.ROUND_KEYS` = (seed, pipeline_version, run_config).
- The real `match()`: two plan entries differing in seed only return the construction. Differing in seed and
  gen_state, they return **None**, which is ORPHAN-UNMATCHED with alpha None.
- On 2026-09-09 the same class filed 131 rows unmatched.

**Fix.** Put gen_state, and any other per-round key the generator stamps, into ROUND_KEYS (not `arm`), and name it
among 04 §5's gate-5 rules. Test: the pair above matches.

---

## EARLIER FIX DID NOT LAND

- **N1 (MINOR). D7's "held" is still "≥ 1 proven clean submission in the next window".**
  - History: round 1 S9 asked for an interval statement per quota day. Round 2 S9-NL said "implement D7 as
    written, or tick a change". `open_ticks()` prints it as open, so it is not landed and waits on Khoa.
  - The statistician's numbers belong on that tick, and I re-derived them by closed form with Poisson days:
    - `sustainable` reads True with probability 0.335 on a 7-day card at the measured 0.211/day;
    - 0.753 on a 14-day card;
    - 0.892 for a version exactly at the floor on a one-day card, which therefore fails 10.8 % of the time.
- **N2 (MINOR). deploy.md F12: the UNITS comment** ("so no process can import a half-shipped tree and nothing runs
  the new code before the smoke has judged it") is unchanged. Timers such as wq-mint and wq-watch run tools/*.py
  during the swap, and wq-auth and wq-outbox (in_pipeline) are never restarted. The systems attacker read this
  from the host; I read the comment.
- **N3 (MINOR). deploy.md F16: there is no deploy lock** (grep: no flock in deploy.py). The fifth pass required a
  host-side flock before an unattended or second push.
  - New instance: `wq-judge.sh` takes no lock and checks no STOP_FORGE.
  - `other_operator_busy()` is read once, at push start.
  - So a judge fired during the rsync, smoke or rollback grades a mixed tree. D41's first-card-wins rule then makes
    that card the day's record.

---

## MINOR (NEW)

Each was re-derived (read or run) unless marked.

- **m1. The deploy ledger's rows are unbounded in time, and `provenance()` does not list it** (statistician,
  (2b)).
  - `not_bounded_by_now` lists scored, corr, curves and standard only.
  - `reconcile_target_ledger()` re-appends a row with its original timestamps. s5 (re-pointed): a final card went
    from 14 rate days to 8, and `rank_cmp` flipped.
  - Draw 4 §4 item 8 omits the ledger.
  - Fix: add deploys to the list and correct item 8. An append timestamp would let a re-grade reproduce an old
    card.
- **m2. D25's "monotone by construction" is false through the neighbour pool** (statistician).
  - s5: A reads PASS (0, 4.0). A + y, with y PROVEN, reads FAIL (1, 4.0): y enters x's pool and moves x's
    three-neighbour median to 0.85/1.8 = 0.472 < 0.5.
  - The POSTed form needs a POST from outside forge's submitter, because novelty holds y. The reachable form is a
    later neighbour refuting x, which the gate is meant to do.
  - Fix: name the route in `rank_key`'s docstring and narrow D25's words.
- **m3. The printed MDR uses the pooled observed rate, so it changes with B's result** (statistician).
  - Real `minimum_detectable_ratio`, with A = 27/3,000 throughout:
    - B = 0 gives 2.47/0.16;
    - B = 27 gives 1.957/0.348;
    - B = 81 gives 1.637/0.516.
  - At A's own rate, which is the function's contract, it is 1.957/0.348 every time.
  - Fix: pass A's rate or a pre-registered base.
- **m4. D28's all-cells-agree rule loses its power once events spread over cells** (statistician; latent while all
  events are in USA/d1).
  - `v3_unanimity.py`: a uniform 2× with one big cell and five sparse cells has power 0.92 under the stratified
    test and 0.14 under the rule. A 3× in the big cell with 2 null sparse cells: 1.00 against 0.18. A single cell:
    0.89 against 0.89.
  - This is D28 as worded, so it goes on Khoa's tick with the rule's simulated power.
- **m5. D23's allowance is keyed on a count that moves with the journal** (gamer; downgraded).
  - The D23 test gives "20 journalled warnings" on the Mac journal and "30 journalled warnings" on the host copy
    (both run on my snapshot, and the journal restored cmp-equal).
  - `_says("20 journalled warnings", <30-text>)` is False, so the next journal refresh blocks every publish.
  - It fails closed, and 10 new unit mismatches are arguably a new failure, which ci_known_red.json says needs a
    tick.
  - Fix: key the allowance on the missed row ids, or run D23 on a frozen corpus.
- **m6. `run_config()` hashes raw parsed strings, not the "normalised argv" D30's note promises** (gamer;
  downgraded).
  - `--order 'USA/d1, d1'`, a trailing comma, `--delays 1,1` and `--root /opt/wq/` each mint a cohort for an
    identical plan.
  - `--tag` and `--concurrency` minting cohorts is D30 as ticked.
  - A fresh cohort outranking on a raw level-1 count is the known open tick ("level 1 is a raw count").
  - Fix: hash the normalised planning inputs.
- **m7. The card ledger's first card of the day wins, and `record_key()` ignores `run_drill`** (gamer).
  `main()` allows `--record --no-drill`. A hand-run card takes the judge's slot, and axis 3 then lacks the drill.
  Fix: refuse `--record` with `--no-drill`, or key on it.
- **m8. `ci_publish.main()` parses with abbreviations on** (gamer; §5 item 10 predicted it). Rebuilt from the real
  `add_argument` calls, `--spl` sets split_golden True and `--no-p` sets no_push True. Fix:
  `allow_abbrev=False`; test: `--spl` exits 2.
- **m9. The orchestrator's re-append of the first deploy row cannot give ec6a5cd75d58fea2 an exposure start**
  (systems; downgraded).
  - The row's keys are commit_time, exit, finished_at, git_dirty, git_sha, outcome, started_at and version. There
    is no pipeline_version, so the real `live_days` returns known False. With the field added it returns 7 days.
  - `unreconciled_rows()` never selects the row, because it has no target_ledger field.
  - D45 voids days before any transition row.
  - The recorded time "06:24 +07" is 06:24 UTC, i.e. 13:24 +07 and 02:24 ET.
  - It fails closed to "exposure unknown", and D33's estimand needs no exposure.
  - Fix: correct the decision text, and put the choice to Khoa.
- **m10. Live code and the tool that computed the incumbent's id are in no repository** (systems).
  - tools/recover_harvest.py (blob b15a104…) appears in no commit of the dev repository or the CI checkout. PLAN
    ships it, but PLAN is not version control.
  - The host's deploy.py 398706c5, which computed ec6a5cd75d58fea2, is in no history. DEPLOYED.json records only
    `closure_files: 43`.
  - The arm drivers (vps/*_run.sh) are on GitHub but not in PLAN.
  - Fix: commit recover_harvest.py, record the 43-file list, and decide whether the arm drivers join PLAN.
- **m11. `wq-judge.service` has no TimeoutStartSec** (systems). A oneshot's start timeout is disabled by default,
  so a hung judge never reads "failed" to deadman, and nothing checks the timer or cards.jsonl. The hang source is
  SUSPECTED. Fix: set TimeoutStartSec=.
- **m12. DORA lead time can never be measured** (CI/CD).
  - dora() keeps only rows that are not git_dirty.
  - `git_sha()` is the dev repository's HEAD. That repository tracks no forge file (`git ls-tree 8a806c86 -- forge
    tools/deploy.py`: 0 paths), so every row is dirty.
  - Fix: read lead time from the publish record's ci_commit.
- **m13. Provenance is thin** (CI/CD).
  - DEPLOYED.json carries no ci_commit and no publish reference.
  - A hand-written two-key line in `ci_publish_records.jsonl` vouches, and the push logs `unpublished_forced`
    false.
  - The record carries no test counts or interpreter.
  - D31 puts authority on the Mac, which is ticked. The logging gap is not ticked.
- **m14. The toolchain is unpinned, and the classifier's two arms differ** (CI/CD).
  - The clean arm's `.v` has requests 2.34.2. The Mac and the VPS have 2.33.1.
  - ci.yml and `ensure_checkout` install unpinned packages, and the actions are referenced by tag.
  - requirements-lock.txt is untracked, and nothing reads it.
  - Draw4_build ci 9 named pytest only.
- **m15. `--split-golden` makes two commits in one run and one push** (merged: CI/CD, gamer).
  - The first commit holds the closure edit without its golden, so it is red by construction (draw3_fix ci 1).
  - Actions runs only the pushed tip, and `cancel-in-progress: true`.
  - D42 said "its own commit", which is met literally. Bisectability and a separate review are not.
- **m16. The data tier leaves a false simulation-running marker in the Mac's live state** (CI/CD). The repo's
  `state/simrunning/crash.json` (18:05) points at a pytest tmp journal.
  `test_a_crash_mid_batch_loses_no_journalled_row` does not patch `LS.ROOT`. Fix: patch it to tmp_path.
- **m17. The hermetic tier prints `[PASS] branch-drill NOT RUN`** (CI/CD; §5 item 7 predicted it).
  `check_branch_drill()` returns ok True, against its docstring's "never as a pass". Fix: a third, NOT RUN state.
- **m18. G5 can fail only in narrow cases** (pass-first). `sign_verdict` passes agreement, "unstated" and every
  domain-prior disagreement. 04 §4.2's "this gate discriminates here" is labelled SPECULATION there; the code read
  narrows it. I did not re-derive the 3,361/19,596 field count. Fix: state the narrowed claim.
- **m19. D36's (cell, field) quarantine charges a refusal to the first leg's `meta.field`** (pass-first; latent).
  `p_quar.py`, re-pointed: 8 dead keys under either key. 2 of the D36 keys name a field that landed in other
  formulas of the cell: tcm_ta50_d1_natr, 10 failed, in 8 landed formulas; negative_percent_change_count, 20, in 2.
  This is POST-HOC with N = 2. Fix: charge every field of the row.
- **m20. Draw 4 maps D26–D42 only; D43–D46, ticked at ~20:15 while it was being drawn, have no row** (found here).
  The code predates them, so every one is a queued change (the systems list). The drawing does not say so.

---

## SUSPECTED

- **X1. The two D33 arms may admit different events** (statistician). D36's plan-time D18 applies to the branch
  only.
  - 2 of the 37 historical hits were created after a matching POST.
  - Settle: classify each window's D24 hits by D18 against earlier POSTs, and report D24 with and without them,
    pre-registered.
- **X2. The pipeline chooses the neighbour step** (gamer). The real `neighbourhood_stability` reads stable for
  decay 3/5 and truncation 0.0801/0.0799. Settle: once D37 grids exist, compare against a pre-registered knob set.
- **X3. D45 as worded would fire on the push's own smoke** (systems). `run_config` hashes `live`
  (ddc3ca582fd73753 against e5a81af5c610a5d6, per the architect and the systems attacker; not re-derived here). Settle when the writer exists: run the SMOKE planner on a replica
  and count ledger rows.
- **X4. The G8 journal clause could self-collide** (pass-first). `PreSimGate._verdict` returns DUPLICATE for any id
  in `seen`. Settle in the stage-3 spec.
- **X5. A hung judge** (systems). No hang source was identified (see m11).

---

## Duplicates and non-defects dropped

- **Statistician (2a): a final card moves as later neighbours enter the pool.** Duplicate of draw3_fix scoring 14
  and round 2 S10-NL ("re-grading is not stable", filed as a LIMIT). Reproduced (s5: rank_cmp flips −1 → +1). One
  correction is kept: "bounded by the clock" in §4 item 8 does not make a D27-final card stable. D27's finality
  covers POSTs only.
- **Systems (d): nothing reads cards.jsonl.** Round 2 A2, listed by the architect in §4 item 3.
- **Systems: the zero-yield harvester sits in the id.** The zero yield is deploy.md F11's observation. The cohort
  churn it causes is part of S14.
- **Systems: the code contradicts D43–D46.** Those decisions postdate the audited bytes, so they are the fix queue,
  not defects. The one defective decision is m9. The drawing gap is m20.
- **CI/CD: no rollback verb.** deploy.md B5 and its third pass named it and judged it no loss. It is a new
  mechanism for Khoa, not a defect.
- **CI/CD: DORA's CFR is 0 on a re-ship, and TTR after a smoke rollback.** These follow from round 2 A9's own rule
  ("a restore only on a version change"). DORA is display-only. Only lead time is kept (m12).
- **Gamer: `--tag` and `--concurrency` mint cohorts.** D30 as ticked. The rank effect is the known "level 1 is a
  raw count" tick.
- **Duplicates within round 3, merged:**
  - CI/CD SERIOUS 3, gamer SERIOUS 2 and pass-first's argparse half went into S2;
  - CI/CD SERIOUS 1 and pass-first's rollback half into S5;
  - the gamer's split-golden remark and CI/CD's into m15;
  - systems (a) into N3.

## Contradictions and severities settled

| point | report | ruling |
|---|---|---|
| Overdispersion | round 2 demoted it to SUSPECTED (X1) | FATAL now: measured on the D24 estimand within its only cell; size ≥ 3× nominal already at φ = 2. Per-version φ is UNMEASURED, and that is stated first |
| Final card moves (statistician) | SERIOUS | (a) duplicate of draw3_fix 14; (b) MINOR m1 |
| D23 count (gamer) | SERIOUS | MINOR: fails closed; the precedents (draw3_fix ci 5, draw4_build ci 4 and 7) rate fail-closed as MINOR |
| run_config escape (gamer) | SERIOUS | MINOR: tag and concurrency are D30 as ticked; only normalisation is a defect |
| Incumbent row (systems) | SERIOUS | MINOR: fails closed to "exposure unknown"; D33 needs no exposure; ec6a ends at the stage-0 push |
| Watch exit 2 | three attackers | one finding (S2) |

## Confirmed correct (re-derived here)

- **The Draw 4 bytes are unchanged:** all twelve hashes, at the start and at 21:06 +07.
- **D28's stratified test controls its size under independence:** 0.034–0.045 in my Poisson controls, against the
  pooled test's inflation (statistician's s2).
- **`_dispersion()` agrees with an exact recount:** 11.99 on the Mac (all cells), 11.80 on the host.
- **The smoke's rule on exit 2 is right**; the watch's differs (S2).
- **Watch rows and no-op rows are skipped** by `last_push_row()`.
- **`post_horizon.final` and `_held_next()` judge at `seen_until`, as draw3_fix scoring 1 required** (read; the
  s5 outputs read final as documented).
- **The judge's timer is DST-safe** (`OnCalendar ... America/New_York`, read). The loop's reset is not (S9).
- **The branch drill plans only its own synthetic composite** (`only=[drill_id]`, read), so §5 item 2's worry that
  the drill's plan file could match a real orphan is not supported. It stays SPECULATION.
- **Bytecode never enters the id:** `file_map()` ships through `_shippable`.
- **A clean snapshot gives b6e639e2674a4dac for `pipeline_version_of()`**, the value the pass-first attacker
  reported. I did not re-derive the run_config values ddc3/e5a8; they rest on the architect's and the systems
  attacker's runs.

## Missed by all five

1. **S3.** The watch never reads harvest, recover_orphans, probe or submit, which run after `=== round exit`. D43's
   REPORT half therefore has nothing to report from, and D39's auto-submit route will sit in the unread part.
2. **The pre-header steps** (record_adjudication.py, refresh_cells.py, `|| true`) share S4's blindness.
3. **m20.** Draw 4 does not map D43–D46.
4. **F1's decisive pair.** Two adjacent real windows of one era read "worse" at p 6.5e-10 while both print a
   dispersion ≤ 1 (0.09 and 0.96). The printed diagnostic cannot see the thing that breaks the test.

## Shortest ordered fix list

1. **Khoa ticks F1:** the day becomes the unit in compare(), with a minimum-day rule and the incumbent's φ measured
   first; or D21 is reopened for round-level randomisation. Correct compare()'s docstring and §4 item 13.
2. **S14:** record a D33 window, refuse pv-moving pushes inside it, freeze the checkout, correct D33's start
   sentence. Tick whether unimported files enter the id.
3. **The watch, before its first run** (release R1 already bars it): S2 (the exit-2 rule, argparse's own code,
   "inconclusive" without work), S3 (read the whole round and report D43 errors), S4 (a gate crash marker). Then
   S5's tick on config in the release unit.
4. **S1:** count late POSTs against level 1 (tick D26 × A4).
5. **S6:** block on test files outside TEST_DIRS; decide the 25 legacy files.
6. **S7:** an input-layer truth-table case through `build()`.
7. **Before stages 2–4:** S13 (neighbourhood for `gen:`, tick), S12 (G4 direction and unit, tick), S8 (meaning-row
   rules), S11 (the in-invocation twin hold), S15 (gen_state in ROUND_KEYS).
8. **S9** (the New York reset plus a test at 11-02) and **S10** (bounded judge memory; MemoryMax, Nice and
   TimeoutStartSec on the unit).
9. **The rest to `docs/evalharness/backlog.md`,** per the 20:15 sign-off rule: N1–N3, m1–m20 and X1–X5.

## Disclosures

- **Pass-first.** Its `p_churn.py` called `deploy.loop_closure()`, which starts an interpreter without -B. At 20:22
  that wrote `.pyc` files into the repository's `forge/`, `forge/offline/`, `tools/` and `tools/funnel/`
  `__pycache__` (`forge/__pycache__` shows 20:22 files). They are compiled from the current sources and are outside
  the id (`_shippable`). Any later audit should still clear `__pycache__`, as the task requires. The same behaviour
  means every call of `loop_closure()` writes bytecode into the tree it inspects (MINOR, not counted above).
- **Gamer.** Its first rsync landed in `scratchpad/snap`, another session's directory. It overlaid files there and
  deleted nothing.
- **My own work.** I wrote only this file. My scratch trees are under `scratchpad/adjr3/`. I deleted the 347 MB
  synthetic journal after measuring it.
