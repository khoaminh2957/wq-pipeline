# evalharness: architecture round 4, adjudication (2026-09-24)

This file rules on five attacks on Draw 5 of `docs/evalharness/01_architecture.md`: statistician, gamer, systems,
CI/CD and pass-first fit. Round 4 is the next round that can count toward D15. Every finding was checked against
`architecture_round1.md`, `architecture_round2.md`, `architecture_round3.md`, `draw4_build.md`, `draw5_build.md`
and `backlog.md`, and against `deploy.md` and `04_passfirst_design.md` where an attacker cited them.

**Snapshot judged.** These are the Draw 5 bytes (sha256 prefix), re-hashed at 01:39 +07 and again at the end, and
unchanged: runner d2e84b70, recover_orphans 99aae169, benchmark b30d255c, meaning 01bc3c3a, forge/gen (`__init__`
d74ebe31, families 431a5e3d, posterior aba9c7e4, productions abd22703, propose 417df14c, repair 4ccd15e7, spend
e5a55844, state 82a67d58), deploy 7ff14dbc, ci_gate 62d1c28c, ci_fixture e2feced0, ci_publish d1de5f28, ci_classify
54c634c3, ci_golden_card d8a0cc0e, ci_known_red 8867dd79, ci.yml 4c7d603a, forge_loop.sh a0b3df46, forge.env
c514eed8, wq-judge.sh 13017d1c, wq-judge.service 27b71125, wq-judge.timer 48689419, systemd_wq-forge.service 6a3af0bd,
submit 07df3bdf, harvest 95f2233d, test_benchmark cc9897c8, test_ci_gate ae1b8c66, test_meaning 80a55fc6.

**Method.** I re-derived every finding kept below on my own snapshot, `scratchpad/adjr4/snap` (an rsync without
.git, state, fetched and the large data directories; state and fetched are APFS clones). Everything ran with
`python3 -B` and `PYTHONDONTWRITEBYTECODE=1`. Where I used an attacker's script I first pointed it at my snapshot.
Scripts are in `scratchpad/adjr4/v/`:

| script | what it checks |
|---|---|
| `f1_load.py`, `f1_census.py` | the scored rows, days, rounds and D24 events of a journal |
| `f1_placebo.py` | round- and row-relabel placebo on the real `_arms_strata` + `_arms_decision`, plus my own z-score |
| `f1_disp_null.py` | the exact within-day null of the "1.03" statistic and of the round-weighted statistic, own code |
| `f1_ratio.py` | the placebo's share reading "better" at a Mantel-Haenszel ratio of 2 or more |
| `s1_peek.py` | daily looks at the real `_arms_decision` under no effect, and my own z-score |
| `s2_d49.py` | the statistician's D49 × D27 pair, re-pointed |
| `m1_mdr.py` | power at the printed MDR under gamma days |
| `g1_pA.py`, `g2_pB.py`, `g4_pD.py`, `g8tree/` | the gamer's probes A, B, D, re-pointed; my module-coverage probe |
| `sy_plan*.err`, `sy_judge.py`, `sy_growth.py`, `sy_quota_watch.py`, `sy_two_ledgers.py` | peak RSS, journal growth, the watch probes |
| `pf_*.py` | the pass-first probes E3, E5, E6b (5 seeds), E7, E10, E11, re-pointed |

Two files were mutated and restored on the snapshot only, each `cmp`-equal to the repository afterwards:
forge/gen/productions.py (the TRUNC mutant) and the snapshot's journal clone (swapped for a 2× synthetic). I made two
read-only ssh calls (`ssh -n -o BatchMode=yes`: `systemctl show`, `systemctl is-active`, `zcat` of one man page, two
`venv/bin/python -B -c` reads, a read of DEPLOYED.json, `ls`, `free`, `ps`). I simulated nothing, passed no --live or
--submit, wrote nothing on the VPS, committed nothing, and edited no file other than this one. No `.pyc` in the
repository is newer than backlog.md, and state/forge holds no meaning.jsonl or run_config_log.jsonl.

Origin labels follow RULE 0: `EX-ANTE (code)` read from code or spec; `POST-HOC` a regularity seen in data;
`SPECULATION` neither. No mechanism is claimed for any data regularity.

---

## Verdict

| class | FATAL | SERIOUS | MINOR |
|---|---|---|---|
| NEW | 1 | 5 | 23 |
| EARLIER FIX DID NOT LAND | 0 | 1 | 4 |

There are also 3 SUSPECTED items.

**D15 clock: does NOT start.** Round 4 found 6 NEW FATAL or SERIOUS defects. Draw 5's boxes still hold: the judged
imports nothing from the judge, the branch's switch is in the release unit, and the watch reads whole rounds. What
fails is, again, the post-deploy proof:

- **D47's read-out** decides with a test whose unit is the alpha while D47 randomises rounds, and D24 events cluster
  inside rounds (F1). It has no horizon (S1). Its arm A is a label that non-randomised rounds also carry (S3).
- **The judge's reading of a generated alpha** cannot reach PROVEN through PBO (S5), and D49 re-opens round 2's A4
  bias on rank level 1 (S2).
- **The loop itself** holds memory in proportion to all history, with no limit (S4).

F1 and S1 change D47's design and need Khoa's tick (RULE 2). The window to fix them without a post-hoc choice closes
at the first arm row: the host journal holds 0 rows with arm `composites` or `gen` (Draw 5 §0).

---

## FATAL (NEW)

### F1. D47's read-out says better or worse about 16 % of the time under no effect, on the desk's own rounds

**Source.** Statistician, FATAL.

**Where.** `ARMS_DESIGN["test"]`, `_arms_decision()` (through `stratified_rate_test_p()`), `compare_arms()`,
`_within_day_dispersion()`; forge/tests/test_benchmark.py `_day_heterogeneous()` and
`test_the_arms_decision_holds_its_size_where_the_sequential_read_out_does_not()`; D47's tick evidence in
00_agreements.md ("between rounds within a day it is 1.03").

**Defect.** D47 randomises ROUNDS. The pre-registered exact conditional test treats every scored ALPHA in a
(day, cell) as an exchangeable Poisson unit. D24 events cluster inside rounds, so under D47's own randomisation T's
variance is about twice what the test assumes. The pinned size test draws each round's count as Poisson given the
day (read: "within a day each round's count is Poisson given G"), so it has no within-round clustering and cannot see
this.

**Evidence, re-derived here** (Mac journal copy, the 9 whole ET days before its cut: 09-04..09-11 and 09-20; 37
events, all in USA/d1):

- **The real decision, round relabel** (`f1_placebo.py`: identical rows, each (day, meta.seed) assigned an arm by a
  coin, 2,000 draws): better 0.0725, worse 0.0825, **together 0.155**. A second run (`f1_ratio.py`, another seed,
  1,500 draws): 0.078 + 0.079 = 0.157, and **every** "better" had a Mantel-Haenszel ratio of 2 or more, so design 04
  §6.2's candidate rule (at least 2× with p < 0.05) does not protect.
- **Control, row relabel** (same script, each alpha its own coin): 0.0375. The test holds its size when rows are
  exchangeable.
- **Second way, no benchmark code** (my own conditional mean and variance of T per stratum): the z-score's variance
  is **2.18** under round relabel (P(|z| > 1.96) 0.19) and 0.99 under row relabel (0.044).
- **Third way** (`f1_disp_null.py`, own code): with e_r = k_r − K_d n_r / n_d over USA/d1 rounds, Σ e_r² = 72.85
  against an exact within-day null mean of 32.41 (97.5 % point 50.78): **ratio 2.25**, permutation p 0.0008 (4,000
  draws).
- **The "1.03" on D47's tick cannot certify the test.** χ² 132.3 on 129 df (re-derived). Its exact null on these
  rounds (each day's events dealt to rounds without replacement) has median 0.666 and 95 % range [0.507, 4.64]; the
  observed 1.026 sits at P = 0.108. With expected counts this small, the Pearson statistic neither supports nor
  refutes within-day exchangeability.
- **The clustering, POST-HOC** (re-derived): 37 events on 30 distinct formulas; 11 events share a formula with
  another event of the same round, and 28 share meta.hypothesis in-round; rounds carrying events hold
  {1: 9, 2: 4, 3: 3, 4: 1, 7: 1}; round 1789093524 on 09-10 holds 7. MECHANISM: UNKNOWN. Candidates, none
  established: the settings grid of one composite block; the allocator's exploit order; platform-side state.
- **Not re-derived here** (statistician): the host copy (0.154-0.173), without 09-10 (0.099), 5- and 7-day windows
  (pooled 0.150 and 0.172), and the burst generator's 0.189.

**Correction (RULE 0 #7), of round 3's own text.** Round 3 F1 read the 1.03 as "Counts at round level look binomial"
and its fix item 3 said "Within-day round randomisation is the design whose test holds (φ 1.03)". Both were wrong:
the statistic has no power at these counts. D47's tick carried that sentence as evidence.

**Severity.** Round 3's rule for this read-out: FATAL at a size of 3× nominal or more on the gate-3 evidence. Here
0.155 against 0.05. A "better" hands the whole quota to the branch (D21 after gates 3-4). Latent: `compare_arms()` has
no caller and no arm row exists.

**Fix (Khoa tick; RULE 2).**
1. Make the ROUND (or a larger randomised block) the unit of the test, as design 04 §6.2 already wrote ("rounds as
   the unit for any variance estimate"): a within-day permutation of rounds that mirrors the real assignment (D53
   must be designed first), or a round-level cluster-robust or quasi-Poisson variance.
2. Recompute `arms_mdr()` on the same unit; power will fall.
3. Replace `within_day_round_dispersion` with the round-weighted statistic and its permutation null.
4. Correct D47's evidence text, `compare_arms()`'s docstring ("which D47's round randomisation provides ... F1: 1.03")
   and ARMS_DESIGN, before the first arm row.

Tests that fail today: the round-relabel placebo on the frozen Mac copy must read better or worse at most ~0.06
(0.155 today); the pinned size test gains a generator with within-round clustering.

---

## SERIOUS (NEW)

### S1. D47's read-out has no horizon, so daily looks accumulate false verdicts

**Source.** Statistician. Draw 5 §4 item 3 names the missing horizon, and §5 item 3 predicted the peeking with "the
size under daily looks is UNMEASURED". Design 04 §7 stage 1 lists "horizon" in the pre-registration file. Counted
NEW on round 3 S14's precedent: a prediction plus the evidence it lacked.

**Where.** `compare_arms()`, `_arms_decision()`, `MIN_SHARED_DAYS`, `ARMS_DESIGN` (no horizon, no look count).

**Evidence** (`s1_peek.py`: the real `_arms_decision`, 1,000 null draws, one cell, 1,268 scored per arm per day at
1.62 per 1,000, Poisson counts with NO clustering):
- single looks at days 5 / 7 / 14 / 28: 0.022 / 0.026 / 0.034 / 0.032;
- daily looks from day 5, stopping at the first verdict: cumulative **0.037 by day 7, 0.084 by 14, 0.131 by 28**;
- second way, my own two-sided z at 1.96 on the cumulative counts: 0.071 / 0.131 / 0.188.
- Not re-derived here (statistician): 0.064 / 0.110 / 0.162 on its generator, and 0.276 / 0.443 / 0.591 with the real
  rounds' bursts (F1 compounds it).
- `compare_arms()` decides at whatever `now` it is given; each pv-moving push restarts the count (D5-SC-M13), which
  starts a fresh sequence of looks.

**Fix (Khoa tick).** Pre-register in ARMS_DESIGN a fixed horizon H (one look) or a group-sequential boundary over a
stated look schedule; `compare_arms()` refuses a verdict before H or applies the boundary; every read is recorded so
looks are counted; state how a pv restart spends the same alpha. Test: daily looks from day 5 to 28 on the pinned
generator keep the cumulative false-verdict rate at or below 0.05 (0.131 today).

### S2. D49 re-opens round 2's A4 bias on rank level 1: at one clock, identical versions rank newer above older

**Source.** Statistician. Overlap named: Draw 5 §5 item 13 and D5-SC-M23 say a final card can still lose a place.
Neither names the systematic ordering between cohorts at one clock.

**Where.** `_submissions()` (its second map), `rank_levels()`, `rank_key()`, `rank_cmp()`, `horizon_final_at()`,
`comparable_from()`; D49 × D27, a RULE 2 gate-5 conflict.

**Evidence** (`s2_d49.py`, the real `build_from` and `rank_cmp` through test_benchmark's `_card`): two identical
cohorts, one unproven alpha each, POSTed 20 days after creation; V1 created 09-10, V2 09-20.
- Graded 10-05, 10-06 and 10-09: V1 level 1 = 1, V2 level 1 = 0, **both** horizon_final True (V2 comparable from
  10-05), `rank_cmp(V2, V1) = −1`. Graded 10-11: 1 and 1, `rank_cmp` 0.
- Control, lag 10 days (inside the horizon): 0 at every date.
- Second way, arithmetic: V1's POST (09-30 12:00 ET) precedes 10-05; V2's (10-10) does not; V2's horizon closes
  10-05 00:00 ET, so D27 certifies both cards comparable while only the older one has had time to be penalised.
- `forge/submit.py eligible()` has no age filter (read), so old alphas stay POSTable. POST-HOC: 0 of the 4 real lags
  exceeded 14 days, and round 3 counted 19 of 33 unposted candidates over 14 days old. How often a late POST happens:
  UNMEASURED.

**Severity.** Round 2 A4 (the mirror bias, which D27 was ticked to remove) was SERIOUS.

**Fix (Khoa tick on D49 × D27).** (a) `rank_cmp` truncates each card's level-1 POSTs at an equal post-creation
exposure; (b) `rank_cmp` refuses while a card's `posted_beyond_the_horizon` could still differ between the two
clocks; (c) accept it and print it on every comparison. Test: the pair graded 10-06 reads 0 or refuses.

### S3. D47's arm A is a label, and rounds no randomiser drew carry it

**Source.** Gamer (SERIOUS), merged with the statistician's MINOR on the same admission.

**Where.** `_arms_strata()` (admits `meta.arm in ARMS`, "any run_config"), `compare_arms()`, `ARMS_DESIGN["arms"]`;
forge/runner.py `stamp()` (`setdefault("arm", a.mode)`); forge/search.py `run_recipe()`; forge_loop.sh
`load_forge_env` (a ROUNDS=1 caller keeps its own FORGE_ARGS).

**Evidence.**
- EX-ANTE (code): `run_recipe()` runs forge_loop.sh with ROUNDS=1 and FORGE_ARGS = "--mode composites ... --tag R..";
  `plan()` under `--ab off` sets no arm; `stamp()` then writes arm "composites" and the deployed pv.
- Run (`g1_pA.py`, the real `runner.main` with no --live and layered_sim recorded, then the real `compare_arms`, 10
  whole days, 1,500 scored per arm per day, 3 D24 events per arm per day):
  - a recipe round is stamped `{arm composites, the same pv, its own run_config}`;
  - control (randomised rounds only): indistinguishable, p = 1.0, A 30/15,000, B 30/15,000;
  - one 0-hit recipe round per day added: **better**, p = 0.0111, A 30/30,000;
  - one 9-hit recipe round per day added: **worse**, p = 0.00044.
- Under the shipped forge.env (`--ab new`), every loop row reads `current` / `new`, so arm A would hold ONLY search
  or hand-run rows: D5-PL-M14's fail-closed "no-data" becomes a verdict against a hand-picked comparator.
- Magnitude, not re-derived here (statistician): one realistic stop-at-first-pass session moved the size 0.034 →
  0.031. The admission is the defect; its size depends on what operators run.

**Severity.** The class of D5-X-SC-S1 (upheld SERIOUS): non-randomised rows inside the strata, failing open on the
gate-3 proof. S1's fix (gen_route) does not reach arm A. Latent: no randomiser, no gen row.

**Fix.** Before the first gen row, pre-register in ARMS_DESIGN that an arm is the set of rows from rounds the D47
randomiser assigned; the randomiser stamps its draw (e.g. `meta.d47 = {arm, draw}`), and `_arms_strata` admits only
stamped rows, counting and printing the rest per arm. Whether forge/search.py or any ROUNDS=1 round may run inside a
proof window is Khoa's tick. Test: pA's layout reads indistinguishable; it reads better today.

### S4. The loop's own memory grows with all history, and wq-forge has no limit

**Source.** Systems. No audit names the loop's memory (grep); round 3 S10 and Draw 5 §4 item 8 treat only the
judge as growing.

**Where.** forge/runner.py `plan()` (the whole journal through harvest's reader whenever the allocator is on);
forge/harvest.py `read_jsonl()`, `forge_rows()`; recover_orphans `load_plans()`; forge_loop.sh (exit handling);
the host's wq-forge unit; vps/wq-judge.service LIMITS ("3,197 MB still covers the loop's measured peak").

**Evidence.**
- **Measured here** (the planner exactly as production runs it, minus --live: `runner.py -n 300` with forge.env's
  FORGE_ARGS, `/usr/bin/time -l`, on my snapshot): **1,506 MB** on the Mac journal and **2,060 MB** on a 2×
  synthetic (ids suffixed): about **17 KB per distinct alpha**.
- Second way: the systems series on the host journal (38,466 alphas) was 1,612 / 2,280 / 3,613 / 6,269 MB at
  1/2/4/8×, the same slope; and the host's wq-forge MemoryPeak reads 1,521,418,240 bytes (read-only ssh today).
- Host, read-only today: wq-forge `MemoryMax=infinity`, `OOMPolicy=stop`; 7,376 MB RAM, 6,181 MB available, 2,047 MB
  swap.
- POST-HOC growth (`sy_growth.py`, the host copy): 5,024 distinct alphas and 17.7 MB dated ET 09-23; full-quota days
  run 14.9-17.7 MB.
- Projection, a straight line and not an observation: about +85 MB of planner peak per full-quota day, so past the
  3,197 MB the judge unit budgets for the loop in ~19 full-quota days, and past the host's available memory in ~54.
  Harvest (793 → 5,023 MB at 1 → 8×) and recover_orphans (255 → 1,814 MB) are the systems attacker's, not re-derived.
- forge_loop.sh branches on RC 2 and on the quota line only (read): an OOM-killed runner (137) falls through to
  recover_orphans, harvest, probe and submit, which read the journal again, and the next round starts with no sleep.
  Which process the kernel kills under global pressure: SPECULATION.

**Severity.** Round 3 S10, the same class for the judge, was SERIOUS.

**Fix.** Stream the planner's and harvest's journal reads and keep only the fields they use; build `load_plans`'s
index only for the orphan parents' formulas, and prune or bound state/forge/plans; a growth test that fails today (the
planner's peak on a k× synthetic under a fixed bound); a forge_loop.sh marker and back-off for a runner exit of 128 or
more; correct the wq-judge.service budget sentence. A MemoryMax/OOMPolicy on wq-forge changes the loop's failure mode:
Khoa's tick.

### S5. A generated submission can never be PROVEN: its D38 pool cannot reach PBO's 20 trials

**Source.** Pass-first. Round 3 S13's class (a generated alpha can never be PROVEN), reached through PBO, which
neither D38 nor D39 names for the judge. Draw 5 §5 item 6 names the DSR half only.

**Where.** benchmark `axis1_product()` (`pbo_pass`), `alpha_status()`; forge/harvest.py `pool_key()`,
`pool_members()`, `pool_pbo()`; forge/pbo.py `MIN_TRIALS`; forge/gen/productions.py `NEUT`, `DECAY`, `TRUNC`; D38 ×
D26; tools/ci_fixture.py (generated rows default to `pbo=True`).

**Evidence.**
- EX-ANTE (code): `pool_pbo` returns status "insufficient (< 20 trials)" and `pass` None; `forge/submit.py
  eligible()` holds only `pbo_pass` False, a None status or "pending", so the alpha is POSTed; `axis1_product` reads
  `pbo_pass` None as unmeasured, so the alpha is `unproven`, `floor_met` False, and D26 counts it at rank level 1.
- Arithmetic: `pool_key` is (gen:<family>, region, delay, category); `pool_members` keeps one row per construction;
  the grammar's settings are 3 × 2 × 2 = 12 per formula per cell, under `MIN_TRIALS` = 20; a family is one formula in
  1,500 of 1,500 draws (draw5_build gen G3; 1,500 family-founded again in my `pf_e11` run).
- Run (`pf_e3_pbo_unproven.py`, the real functions on synthetic rows): a pool of 3 (the alpha and its two D51
  neighbours) reads insufficient, pass None; the alpha then reads **unproven**, floor_met False; control with
  `pbo_pass` True reads proven.
- Design 04 §5.4 wrote "PBO becomes non-binding for the new branch ... Named" — at submit. At the judge it binds.
  D39's own reason ("it must not read unproven merely because G1–G3 cannot exist, or D26 would count every generated
  submission against its version") applies here word for word.

**Fix (Khoa tick on D38 × D26).** (a) PBO "insufficient" on a generated family pool reads not applicable, printed
UNMEASURED and never counted; (b) a wider, PBO-only pool for generated alphas; (c) accept it and print on every card
that the branch cannot be PROVEN. Then a truth-table case (a generated submission with `pbo_pass` None and every other
gate true reads as the tick says) that fails on today's code.

---

## EARLIER FIX DID NOT LAND

### E1 (SERIOUS). The release unit declares no dependencies; the host venv is outside the id, the smoke and the rollback

**Source.** CI/CD. deploy.md S2 item 2 (SERIOUS: "`/opt/wq/venv` ... every installed package is unhashed"; its fix: an
environment fingerprint beside the id) never landed; R3-m14 (requirements-lock.txt untracked and unread) is partly
fixed only for pytest. No backlog row tracks deploy.md (m16).

**Evidence.**
- Read: `PLAN` has no requirements or venv entry; `git ls-files` does not know requirements-lock.txt; `SMOKE`'s import
  step imports a fixed list (no forge.gen, no forge.meaning); its tests step is `pytest forge/tests` (E4).
- Host, read-only today: 44 distributions; `import statsmodels` → ModuleNotFoundError. This Mac: 158 distributions,
  statsmodels 0.14.5. Every presubmit tier runs with packages the host lacks.
- Consequence for a new forge/gen module that needs such a package, by reading: its test in forge/tests fails the
  smoke after the quiesce and rolls back (fail closed); its test in forge/gen/tests is never run by the smoke, so the
  push stands with a module that cannot import on the host (the CI/CD attacker's simulated push, not re-run); a lazy
  import in a post-dispatch step fails after quota is spent, and D43 reports it and never rolls back. The only other
  route, a hand `pip install` into the venv the incumbent shares, has no id and survives any rollback.
- Latent: the CI/CD attacker's ast walk found 0 shipped files importing a package the host lacks (not re-derived).

**Fix (Khoa tick; a new mechanism).** A hashed lock in PLAN, its hash and `python -V` in `manifest()` and the id;
push verifies the target venv against the lock, read-only, and refuses on a mismatch (installation stays attended);
the data tier and the classifier's CLEAN arm run from the same lock. Test: in a scratch copy, a forge/gen module
importing a package absent from the lock blocks the gate.

### E2 (MINOR). Round 3 S10's growth test did not land; the judge still grows linearly

- The landed test (`test_the_journal_is_read_line_by_line_reduced_and_as_named`) bounds the reader's constant on 150
  alphas (tracemalloc, read). S10 asked for "build() on a 3× synthetic stays under a fixed RSS bound".
- Measured here (`sy_judge.py`, `build(version=ec6a5cd75d58fea2, run_drill=False)` on the host copy): 233 MB at 1×,
  312 MB at 2×, about 2.0 KB per alpha. The systems attacker read 1.9 KB per alpha, and 971 → 1,483 MB at 1 → 8× with
  the drill. MemoryMax=3G makes it fail closed.
- **Correction (RULE 0 #7) of round 3 S10's "47.8 MB/day".** That was 121.72 → 136.87 MB over 7.6 h, extrapolated to
  24 h while the loop sleeps ~12.5 h after the quota. Per ET day the host journal grew 14.9-17.7 MB on full-quota days
  (POST-HOC, re-derived above).
- Fix: land S10's test as written; update the header's figures (its text half is D5-RL-11).

### E3 (MINOR). R3-X2's partial fix rests on setting levels nothing pins

- The backlog marks R3-X2 "partly fixed": repair.py draws neighbour steps from productions' `NEUT`, `DECAY`, `TRUNC`.
- Measured here: `TRUNC = (0.08, 0.081)` on the snapshot leaves the 7 test_gen files at 52 passed, as before; restored
  `cmp`-equal. productions.py is not among the golden's 51 `scorer_closure` keys (read). So a 0.001 truncation step
  would feed `neighbourhood_stability` as a true neighbour with the whole gate green.
- Fix: pin the three level sets as literals in test_gen_repair; putting the level set into benchmark's constants, so
  the judge counts only siblings on those levels, is a tick.

### E4 (MINOR). The smoke's test path was never derived from the gate's suite

- Round 3 S6's fix: "Derive TEST_DIRS, SUITES and the smoke's path from one function". `ci_gate.suite()` and
  `ci_classify.suites()` now share it; `SMOKE`'s tests step and vps/wq-forge-tests.sh still pass `forge/tests`
  literally (read). deploy.md S6 is the same item. A test the gate runs outside TEST_DIRS never runs on the target's
  interpreter.
- Fix: both take `ci_gate.suite()` evaluated on the shipped tree. Test: a `run_outside` file appears in
  `smoke_command('tests')`.

### E5 (MINOR). A rollback is still never smoked

- deploy.md M7 ("re-run the smoke after a rollback"), partial since its first pass. `_undo()` is `rollback()` then
  `start_units()` (read). The venv is not in the snapshot (E1).
- Fix: run SMOKE with the restored forge.env's (N, FORGE_ARGS) before `start_units`; leave the units down under a
  distinct EXIT if it fails.

---

## MINOR (NEW)

Each was re-derived (run or read) unless marked.

- **m1. The printed MDR's "80 % power" is not reached under the between-day dispersion D47's tick cites**
  (statistician). `m1_mdr.py`, the real `_arms_decision` at the MDR `arms_mdr()` prints, 1,500 draws: constant rate
  0.82 at 7 days and 0.83 at 14; gamma days at φ 11 (calibrated on the base day total) **0.71** and **0.75**. The
  statistician read 0.68 and 0.72. `arms_mdr()`'s docstring discloses the LIMIT; `render_arms()` prints "with 80 %
  power" without it. Fix: print the power at the measured φ, or the caveat; recompute on the round unit after F1.
- **m2. D7's "distinct mechanisms" conjunct is vacuous for the branch** (statistician). `productions.candidate()`
  passes `mechanism=gen:<family>` to `signature()`, whose `mechanism_key` is mechanism#datasets#cell (read); families
  are singletons (G3), so every generated POST is its own mechanism, while the incumbent needs two library hypotheses.
  Display-only: `sustainable` is in neither `floor_met` nor `rank_levels` (read). Fix: add to R3-N1's tick.
- **m3. D45 transition rows remove chosen days from a card's rate** (gamer). `g2_pB.py` (the real
  `record_run_config` and `build_from`): 13 log rows took rate_days 8 → 2 and the rate 0.25 → **1.0** per day with the
  same proven submissions; level 1 unchanged. A zero-quota row exists (D5-PL-M12). Distinct from D5-SC-M3, M19, M26
  and D5-PL-S1. Fix: Khoa ticks D45's reading of a mixed day (count it for the cohort held at 00:00 ET, or pro-rate);
  meanwhile print the rate with the excluded days counted.
- **m4. A back-dated meaning row moves a re-grade at the same clock** (gamer). `g4_pD.py`: unproven, level 1 = 1 →
  one real `append` with `scored_at` = created + 60 s → **proven**, level 1 = 0, at the same `now`;
  `not_bounded_by_now` unchanged. `meaning_index()`'s "a card graded later is not moved by a row written after its
  clock" is false: the bound is the caller's `scored_at`. R3-m1's class, on another ledger. Fix: `append` stamps its
  own `appended_at` and `meaning_index` bounds on it, or list meaning in `not_bounded_by_now`.
- **m5. P3's two-step golden cannot go through the release path and leaves no record** (gamer). Read:
  `record_refusal()` compares with the working-tree golden, `record_golden()` writes no record, and `--split-golden`
  splits one publish of the final tree (R3-m15's mechanics). The step-1 card (the gamer's golden_step1.json, f5458520)
  reads `generated_alpha/ledger_read` gate null where the final golden reads true: one judgement moved and moved back,
  and the net diff from the CI checkout's draw-2 golden will show neither. The gamer's "step-1 tree: 39 test_ci_gate
  failures" is not re-derived. Fix: re-word P3; keep both step diffs; `record_golden` appends a ledger row that
  ci_publish checks as a chain.
- **m6. Design 04 §6.4 C9's mitigation did not reach D47's read-out** (gamer). C9: "report ERROR and structure-refused
  counts per arm beside every rate". `_arms_strata` admits `SCORED_STATUS` rows only and `render_arms` prints no
  unscored count (read). POST-HOC unscored shares per arm (gamer: current 0.8 %, new 2.8 %, typed 6.2 %) are not
  re-derived. Fix: count and print per arm.
- **m7. Axis 3's module-test check counts a test that only names the module** (gamer). My probe (`g8tree/`): test
  bodies `eps` and `zeta.f`, over modules whose only function raises, count as tested; `assert True` does not. Fix:
  require a call of, or an assertion over, something bound from the module.
- **m8. A push made during the quota sleep can only end in watch_timeout** (systems). `sy_quota_watch.py` (the real
  `_judge` and `_watch_timeout` on a slice modelled on host seed 1788796277): decision "wait", inconclusive, then rc 6,
  `watch_timeout`, cause "inconclusive". forge_loop.sh sleeps to 00:05 ET after a DAILY 429 round (read), 12.2-13.9 h
  on full-quota days (POST-HOC, systems). Separately, `_watch_rollback` → `other_operator_busy()` refuses while
  wq-judge runs (`_OTHER_READERS`, read). Planner crashes are still caught. Fix: state the window in the watch section
  and in push's output, or make push refuse, loudly, in a quota sleep; re-arming is a tick (round 3 S4).
- **m9. The already-watched guard reads the Mac's ledger only** (systems). `sy_two_ledgers.py` (the real `watch()`,
  network stubbed): writable ledger → rc [6, 2], 1 target row; failed local append → rc **[6, 6]**, 2 target rows, 0
  local. `_write_row()` prints and swallows the local OSError (read). Fix: read the target ledger for the check
  (`read_target_ledger()` exists), or refuse after a failed local write; exit non-zero.
- **m10. The classifier labels a missing package "data-bound"** (CI/CD). `ci_classify.classify()` files any collection
  error present in CLEAN only as `ignore_files` (read); the arms differ in packages (158 against pytest, pyyaml,
  requests). The statsmodels run is the attacker's, not re-derived. R3-m14 recorded a version difference only. Fix:
  the CLEAN venv from E1's lock, or classify a ModuleNotFoundError for a non-repository module as "environment",
  which blocks.
- **m11. A change-detector pin makes the data tier red for any new test file outside TEST_DIRS** (CI/CD).
  `test_every_test_file_of_the_published_subset_is_run_or_listed_on_the_real_tree` asserts `== 25` (read). Fix: keep
  the invariants, drop the literal.
- **m12. OPERATORS.md is outside PLAN and SUBSET** (CI/CD). forge/llm/formula.py `signatures()` and `allowlist()`
  default to ROOT/OPERATORS.md; test_llm_formula reads it and runs in the smoke. Host, read-only today: the file is
  there (mtime 07-16) and is not a key of DEPLOYED.json's 551 hashes. The systems attacker independently saw
  test_llm_formula fail on a snapshot without it. A fresh host fails every push; a regenerated file never ships. Fix:
  add it to PLAN (it enters the id) and SUBSET, or test the staged artifact.
- **m13. No presubmit check reads the shipped forge.env** (CI/CD). No `CHECKS` entry reads forge.env or FORGE_ARGS
  (grep); `--mode gen` exits 2 from argparse (round 3 S2); the only presubmit signal is D5-RL-4's pin, which fails a
  valid and an invalid flip alike. Fix: a ci_gate check that parses the shipped forge.env with `_forge_env_from` and
  runs the planner dry under `_smoke_ok`'s rule.
- **m14. D8's drill plugs in YAML only** (CI/CD). branch_drill copies hypotheses and composites and plans; its
  `_code_hash()` globs `forge/*.py` (read), so forge/gen and forge/offline are invisible to it. Axis 3 answers "can
  branches be grown?" from a YAML drill while the branch being grown is code. Fix: a code-branch drill (a tick).
- **m15. `code_version()` hashes staged YAML that the CI sync never copies** (CI/CD). It hashes `deploy.file_map()`,
  which ships forge/**/staged/*.yaml (deploy.py's own comment), while ci_publish `EXCLUDE` holds "staged/", and
  ci_gate compares `code_version` on the hosted checkout (read). One staged file on the Mac makes the hosted tier
  STALE until it goes. Latent: both staged dirs are empty. Fix: hash the synced set.
- **m16. backlog.md takes no row from deploy.md** (CI/CD). `grep -c deploy.md backlog.md` = 0. deploy.md's open S2,
  S3, S6, M7 and B6 (D4's auto-deploy clause) are tracked nowhere, and "auto-deploy" is in no §4 list. Fix: a deploy.md
  table with statuses re-read; put D4's auto-deploy clause to Khoa (build it, or narrow D4 as D31 did).
- **m17. `meaning._g6()` raises on a grammar-reachable shape** (pass-first). `pf_e7_g6_crash.py`: the real
  `meaning.score` with the real catalogue raised `TypeError: not all arguments converted during string formatting` on
  `multiply((1 - rank(ts_backfill(vec_avg(anl49_vector_averageannualrelativepe) -
  anl49_annualfiscalearningspershareindicator, 126))), rank(pv87_2_epsr_af_matrix_p1_chngratio_low -
  pv87_v2_0_0_annualgrossdivyld))`; a two-field synthetic raised too. Cause, read: `"every leg is in one domain %s" %
  (sorted(distinct)[0] ...)` formats a 2-tuple. It fails closed. Fix: `% (x,)`; a test with this formula.
- **m18. The generator draws what D39's G6 always refuses** (pass-first). productions `_ts_allowed()` and
  `_tier_u_ops()` exclude CHANGE only on `typed.NON_DIFF` = {ratio, score, flag, code}; `_g6` refuses CHANGE on a
  "return" kind (read). My run (`pf_e6b.py`, 5 seeds × 300 on the runner's cells, empty posterior): **49 of 1,500**
  (3.3 %) G6 False, all change-on-change, both derivations 49/49, 20 of them floor draws (pass-first: 445/9,000 over
  30 seeds). D34's y still pays for them. Fix: a tick (a pre-sim exclusion is a new filter needing its own proof, or
  print the per-round count); correct 04 §4.2's "overlaps H2/H3".
- **m19. C16 can POST a D51 neighbour the judge reads UNPROVEN** (pass-first). `pf_e10`: 4 one-setting variants, 6
  neighbour pairs; verdicts (P, N1, N2) = (stable, stable, stable) for 1 pair and (stable, unmeasured, unmeasured) for
  5; `submit.choose` picks N1. Latent (no D51 hold). Fix: the D51 hold in `eligible()` before `choose()`, covering
  neighbours, or C16 excludes rows sharing the winner's formula; name C16 in 04 §5.4.
- **m20. PNL_STOP cannot refuse a fresh draw** (pass-first). EX-ANTE: spend refuses only candidates of a stopped
  family, and a PnL sibling that is a different formula founds its own family (G3). The plan-time D18 half is an
  observation, not a defect: `pf_e11` with the real state (4 accepted POSTs, index complete) refused 0 of 1,500 draws,
  so nothing near a POST was drawn (it bears on R3-X1: that asymmetry is nil at this rate, POST-HOC). Fix: add PNL_STOP
  to G3's tick; correct spend.py's text.
- **m21. Design stage 2r is tracked nowhere** (pass-first). 04 §7 says its five replays "go to Khoa before stage 5",
  among them C9's cancellation, which §3.2 says goes to Khoa "whatever Q3 says". grep: 2r appears only as one option
  of G3's tick in draw5_build. Fix: list it in Draw 5 §4 and the backlog.
- **m22. The (cell, field) quarantine: a false docstring and an untracked stage-4 item** (pass-first SERIOUS,
  downgraded). `pf_e5`: 4 FAIL rows of one field under 4 singleton gen families give dead keys []; the control under
  one hypothesis gives 1 key. `productions.candidate()`'s docstring (copying 04 §3.3) says the hypothesis-keyed
  quarantine "sees a stable key"; 04 §5.4 labels that reading DELETION, and D36 ticked (cell, field). Downgraded
  because 04 §4.1 places the (cell, field) quarantine in `fill_gen` at stage 4, NOT YET like `runner --mode gen`; what
  survives is the false text, no writer for (cell, field) keys named anywhere, and no line in Draw 5 §4. The quota at
  stake (5-14 of 9,000 draws) is the attacker's, not re-derived. Fix: correct the docstring and 04 §3.3; name the
  writer and reader in the stage-4 list and the backlog, with R3-m19's "charge every field".
- **m23. forge/submit.py's C19 is documented and not enforced** (found here). The docstring's ELIGIBLE list ("C21 —
  nothing more, nothing less") includes "mechanism_key not POSTed in the last 7 days (C19)". `eligible()` has no such
  check; `main()` drops same-mechanism entries only within one invocation; `WEEK_S` is used only by `recent_403()`
  (read). For generated alphas the key is a singleton anyway (m2). Fix: implement C19 or strike it; whether C19 still
  stands is the owner's or Khoa's call.

---

## SUSPECTED

- **X1. D47 may not reach adequate power within one pipeline_version's life** (statistician). 2× at the real volume
  needs about 14 shared days in one pv (statistician: 0.54 at 7 days, 0.83 at 14; not re-derived); round 3 S14 found
  no 7-day stretch without an in-pipeline edit. Settle by recording each pv's lifetime in whole shared days once D47
  runs.
- **X2. An OOM in the judge stops the whole unit, not one card** (systems). Host, read-only today:
  `DefaultOOMPolicy=stop`, and systemd.service(5) there (systemd 259): "If set to stop the event is logged and the
  unit's processes are terminated cleanly by the service manager". wq-judge.sh runs every cohort in one bash; the
  header's "the day's log says 'recorded NO card'" then needs bash to outlive the stop. Not observed; settle with an
  attended run under a small MemoryMax (Khoa's call), then set `OOMPolicy=continue` or correct the header.
- **X3. D51 neighbour rows may dilute the probe's 60 reads a round** (pass-first). Settle by replaying
  `probe.pending` on a synthetic journal, or by counting reads per family after the first live gen days.

---

## Duplicates and non-defects dropped

- **Gamer MINOR: "forge/meaning.py is outside the pin; a flattering G6 edit passes test_meaning and the golden."**
  Duplicate. Draw 5 §1 states it ("forge/meaning.py and forge/gen are outside `scorer_closure` ... a change to what
  the pipeline WRITES ... moves no case"), §5 item 10 predicted it, round 2 S8-NL (ii) is its class, and D5-ME-M9
  already records the H2 mutant surviving test_meaning. A golden with 0 diffs is certain by construction.
- **Statistician MINOR: compare_arms admits non-randomised composites rounds.** Merged into S3.
- **Statistician's interference note** (D5-GE-S3 demonstrated). Already on file; the statistician did not count it.
- **m1's burst column** (0.62-0.65) is F1's consequence and folds into F1's fix.
- **Pass-first m20's plan-time D18 half.** An observation (0 of 1,500 refused), not a defect.
- **Gamer: one alpha id under two arms.** Not filed by the gamer and not demonstrated; not filed here.
- **Systems observation: an orphaned monitor loop on the host** (pid 3258826, ppid 1, running 12 h 35 min at my
  read-only `ps`, polling `systemctl` and DEPLOYED.json). Not a Draw 5 defect and in no repository; stopping it is a
  VPS write, so it goes to the orchestrator and Khoa.

## Contradictions and severities settled

| point | report | ruling |
|---|---|---|
| arm A admits search rounds | gamer SERIOUS, statistician MINOR | SERIOUS (S3): the admission fails open on gate 3, the class of D5-X-SC-S1; the realistic magnitude of one session is small and stated |
| (cell, field) quarantine | pass-first SERIOUS | MINOR (m22): a stage-4 item in 04 §4.1; the false docstring survives |
| MDR power under φ | statistician 0.66-0.73 | kept MINOR; my second way reads 0.71-0.75, not 0.66 |
| peeking | statistician 0.064 / 0.110 / 0.162 | reproduced in direction: 0.037 / 0.084 / 0.131 on my generator; my own z 0.071 / 0.131 / 0.188 |
| venv / dependencies | CI/CD SERIOUS, EARLIER-FIX-DID-NOT-LAND | kept (E1): deploy.md S2 was SERIOUS and never landed; it does not count toward D15 |
| OOM stops the judge unit | systems SUSPECTED | SUSPECTED: documented, not observed |

## Confirmed correct (re-derived here)

- **The audited bytes are unchanged**, at the start and at the end.
- **The conditional test holds its size when rows are exchangeable:** row relabel 0.0375; my z-score variance 0.99.
- **The pinned model's own claim holds:** at a constant rate the single-look size is 0.022-0.034 over 5-28 days.
- **`arms_mdr()` is right on its own model:** 0.82 at 7 days and 0.83 at 14 at the printed ratio, constant rate.
- **Round 3's per-day and per-round counts:** 37 events on the Mac copy, χ² 132.3 on 129 df, rounds carrying events
  {1: 9, 2: 4, 3: 3, 4: 1, 7: 1}.
- **D49 is built as ticked:** a POST at lag 20 costs level 1 once it happens.
- **The planner's slope is about 17 KB per alpha two ways**, and the host's MemoryPeak (1,521 MB) matches the 1× level.
- **5,024 distinct alphas dated ET 09-23** on the host copy, consistent with the ~5,000-a-day quota.
- **PBO "insufficient" does not block at submit**, as design 04 §5.4 documents.
- **The watch's refusal to watch a push twice works when the local write succeeds** (rc [6, 2]).
- **The gen stamps and orphan keys** (pass-first E12 and the gen_state ROUND_KEYS match) were not re-run here; the
  pipeline adjudicator's V5 and the code read agree.

## What all five missed

1. **The design already required F1's fix.** 04 §6.2's test says "rounds as the unit for any variance estimate", and
   §6.4 C12 says "round-level UNMEASURED". ARMS_DESIGN made the alpha the unit. So F1 is also a written requirement
   that never reached the code, and the evidence Khoa ticked D47 on (round 3's "1.03", my predecessor's text) was
   the wrong statistic.
2. **04 §7 stage 1 lists the horizon in the pre-registration file.** ARMS_DESIGN calls itself pre-registered without
   one (S1).
3. **C19 in forge/submit.py** (m23).
4. **The fix window for F1, S1 and S3 is the same and closes at the first arm row**, the window D5-X-SC-S1 already
   named. All three belong in one ARMS_DESIGN amendment and one tick, before `runner --mode gen` exists.

## Shortest ordered fix list

1. **[Khoa tick] F1 + S1 + S3, one ARMS_DESIGN amendment before the first arm row,** with D5-X-SC-S1: the round (or
   block) as the test's unit, D53's assignment designed, a fixed horizon or a group-sequential boundary with looks
   recorded, only randomiser-stamped rows admitted; `arms_mdr()` recomputed on the unit; D47's evidence text and
   `compare_arms()`'s docstring corrected. A second tick: whether search or ROUNDS=1 rounds may run in a proof window.
   Tests: round-relabel placebo ≤ ~0.06 (0.155 today); daily-look size ≤ 0.05 (0.131 today); pA's layout reads
   indistinguishable.
2. **[Khoa tick] S5** (PBO for generated alphas, D38 × D26) and **[Khoa tick] S2** (D49 × D27), each with its
   truth-table or rank case.
3. **S4**: bound the loop's readers, the growth test, forge_loop.sh's back-off on an exit of 128 or more, the unit
   budget sentence; **[Khoa tick]** MemoryMax/OOMPolicy on wq-forge.
4. **[Khoa tick] E1** (a dependency lock in the release unit), and with it m10, E4, E5 and m12.
5. **Cheap MINORs before stages 3-4:** m17, m9, m7, m11, m15, m4, m6, E3, E2.
6. **Into the tick queue:** m18, m19, m20 (with G3), m2 (with R3-N1), m3 (D45's mixed day), m13 and m14, m23, D4's
   auto-deploy clause (m16).
7. **To backlog.md**, per the sign-off rule: m1, m5, m8, m16, m21, m22, X1-X3, and a deploy.md table.

## Disclosures

- **Attackers' scripts.** The pass-first scripts import from the repository path; the others from snapshots. I
  re-pointed every one I ran at my snapshot. No `.pyc` in the repository is newer than backlog.md (checked with
  `find`).
- **My own work.** I wrote only this file. My scratch tree is `scratchpad/adjr4/`. The 2× synthetic journals were
  deleted after measuring; `../sysr4/mkmult.py` rebuilds them. My two ssh calls were read-only.
