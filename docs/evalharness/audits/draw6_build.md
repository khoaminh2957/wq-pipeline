# Draw-6 build audits (2026-09-24)

## Draw-6 audit: submit (2026-09-24)

Adjudicator, module `submit`. Audited bytes (sha256 prefix): forge/submit.py 48b033e8a5c6ef6a (sha1 1a0372cb5d,
the bytes auditor 2 ran), forge/tests/test_submit.py 3c5fda76c75fa6d1 (sha1 4f384eb4bc8f). Read alongside:
forge/gen/repair.py 2c584c9a (modified 10:03, after the builder's evidence) and forge/meaning.py 01bc3c3a (the
draw-5 signed bytes). The repo copies were still identical to these bytes when this section was written.

Setup:
- Snapshot: scratchpad/d6_submit_adjudicator. It was code only (forge tools harness harness13 vps fingerprint.py
  operators.py conftest.py .github, with no `__pycache__`), and it is deleted.
- Probes: scratchpad/d6_submit_adj_probe.py. Output is in d6_submit_adj_ev_probes.txt and cited below as P1..P6.
- Mutants: scratchpad/d6_submit_adj_mut.py, with results in d6_submit_adj_mut_results.json. Each mutant was run
  sequentially, one pytest at a time. After each run the file was restored, and every restore was cmp-equal
  to the repo.
- Host: one read-only `ssh -n -o BatchMode=yes` (ls plus a python count), output in d6_submit_adj_ev_host.txt.
- No sim, no --live/--submit, no commit, no code edit, and no .pyc in the repo (find).

Every item below is an OBSERVATION on stated inputs (RULE 0). No mechanism is claimed.

Baseline: `PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest -q -p no:cacheprovider forge/tests/test_submit.py`
gives **31 passed** on the current tree, including repair.py as of 10:03. That settles auditor 3's open point that
the builder's green run predated that edit. The no-op mutant also gives 31 passed.

### What landed (verified)
- **D51, the submit half (round 3 S13, round 4 m19).** Lines 187-200 and 357-363. The hold sits after every
  existing gate and before choose().
  - It counts with repair.existing_neighbours, including the cohort rule.
  - A neighbour row is `gen:` too, so it meets the same hold (test 309-316).
- **D39/D52 meaning gate.** Lines 203-249, 364-367 and 421. The real scorer runs in the tests. The hold names
  each gate, scoring that raises is held as `meaning-error:<class>`, and the ledgers are read once per gate.
- **Round 3 S11, for generated picks.** Lines 252-285 and 503-507. At-or-over the line holds, and so do an absent
  curve, no prediction, or an exception.
- **Library path unchanged.** The first 230 lines of the test file are byte-identical to the original 16 tests
  (auditors 1 and 2, by diff). The no-op and every generated-path mutant leave the library tests green.
- **The new route is dormant on the host.** Re-derived today: `/opt/wq/forge/gen` is absent,
  `state/forge/meaning.jsonl` is absent, and **0 of 43,429** forge journal rows are `gen:`. Auditor 2 counted
  38,624 rows earlier, and the journal has grown since.

### Adjudication: auditor 1's SERIOUS (S11 half-landed) is SUSTAINED
- **Reproduced (P1).** This used the real main() and the builder's fake transport. The queue held generated G
  (`gen:famA`, score 0.9) and library L (`h1`, score 0.5), with different keys, dataset sets and structures.
  - L's cached curve is G's PnL twin: the real predictor gives 0.9948.
  - The platform re-read after G's POST reads L at 0.3.
  - **Result: POSTed [G, L].** The control curve also gives [G, L].
- **The text on file covers this case.** Round 3 S11's fix (architecture_round3.md:413) says "hold every
  remaining pick".
  - The builder's reason for leaving library picks alone is "library composites behave exactly as today".
    That reason does not cover a library pick after a GENERATED POST, because no generated POST exists today.
  - D47/D53 randomise rounds 50/50 within each ET day, so a queue that mixes library and generated picks is a
    ratified regime, not a corner case.
  - A refused POST is spent for good, and C29 sends every submit to HOLD-FOR-APPROVAL after a second 403 in
    7 days.
- **A fix is sketched and measured.** The sketch adds `posted_generated=is_generated(pick, pick["row"])` to
  pnl_twin_hold. After a generated POST, every remaining pick is predicted; after a library POST, library picks
  pass through as today.
  - Result: 31 of 31 builder tests still pass.
  - P1 now POSTs **[G]**, the control stays [G, L], and a library-only twin queue still POSTs **[L1, L2]**
    (today's behaviour).
- **Latent.** 0 `gen:` rows exist on the host. Round 3 graded S11 SERIOUS while it was equally latent, so this
  grade keeps that standard.
- **If the orchestrator limited S11 to generated picks on purpose,** this moves to Khoa's tick queue as the
  uncovered half of S11. Nothing on file that I could read says so.
- **One half stays uncovered either way.** A library pick after a LIBRARY POST, with differently-keyed PnL
  twins, has the same re-read exposure today, and the literal S11 text would hold it. It conflicts with
  "library as today", so it goes on the tick queue, not into this fix.

### Adjudication of the MINOR and SUSPECTED items
Reproduced here:
- **D51 aborts the whole invocation.** One journal row with `settings="bad"` made eligible() raise
  AttributeError when a generated candidate was present. The library candidate was lost with it. The same rows
  in a library-only round gave [L] (P2).
  - The docstring (line 18) says each gate is "a hold, never a POST". For D51 the code does not match it.
  - 0 of 38,624 host rows have such settings (auditor 2), so this is unreachable on current data.
- **A NaN prediction clears S11.** A predict that returns NaN kept the pick (P3). The real predictor returns
  (1.0, 984) for a NaN point on day 500, on day 999, on every day, or on half the days, so the pick is held
  today. A NaN on the first day gave 0.9948.
- **A dry run appends binding meaning rows.** main([]) wrote the G row (P4). Rows bind by earliest-row, and
  the builder's test_the_recorded_row_binds_a_fresh_all_true_scoring pins that.
- **Test gaps: five mutants survive all 31 tests.**
  - M20: scored_at=0
  - M19: only=set()
  - M25: fresh check only when appended
  - M04: prefix "gen"
  - M24: an unread recorded row passes

  Auditor 2's M05, M18, M21, M34 and M43 were not re-run here. I take them from its mut_a2_results.json.
- **The D42 scorer closure grows from 59 to 62 files** (P6): it adds forge/meaning.py, forge/llm/__init__.py and
  forge/llm/verify.py.
- **The prefix is five literals, all "gen:" today** (P5), and no test pins submit's copy.
- **The digest omits generated candidates.** forge/digest.py:86 calls SUB.eligible without a gate (grep).
- **Design 04 §5.4 was never updated.** It still reads only "NEW: meaning route, approvals, AUTO_SUBMIT_STOP"
  (read at lines 544-552).
- **C19 is still in the docstring.** Lines 5 and 9 still claim C19 and "nothing more, nothing less" (read).

Accepted on reading, not re-run:
- Inherited G1-G3 bind, which is stricter than decidable_verdict. Auditor 3 re-derived 0 of 94 composites.
- Held candidates are re-scored every round.
- One S11 exception holds every generated pick.
- The 144 host pairs are 4 × 36 (auditor 3 re-derived this by ssh).

SUSPECTED (MECHANISM: UNKNOWN; each needs a measurement or an owner):
- S11 covers one invocation only (auditor 2, Q1).
- D51's cohort for a marked stamp differs from benchmark.cohort_of (Q4).
- Host peak memory of load_ledgers (the host journals are 248 MB).
- S11 compares curves across regions.

### Dropped
- None of the defects failed to reproduce.
- One claim is corrected, per RULE 0 #7. Auditor 2 said "the real predictor clamps NaN to 1.0". That holds for
  NaN points after the first day. A NaN on the first day gives an ordinary number (P3). The verdict is
  unchanged: the pick is still held today.

Signed for push: **no**. One SERIOUS survives, S11's library-after-generated half.

Required before push (SERIOUS):
1. pnl_twin_hold takes whether the POSTed pick was generated. After a generated POST it predicts every remaining
   pick; after a library POST, library picks are unchanged.
2. Add a test that FAILS without it: after a generated POST, a library twin is held; after a library POST, a
   library twin is kept (P1 is the template).

Cheap MINORs to fold into the same fix, each with a failing-first test:
- (a) Put D51 in a try and hold as `d51-error:<class>` (P2).
- (b) Treat only a finite prediction as a number (P3).
- (c) Add auditor 2's tests t1-t7, which kill M04, M05, M18-M21, M24, M25, M34 and M43.
- (d) Pin SUB.GENERATED_PREFIX to benchmark.GENERATED_PREFIX and to productions' "gen:".
- (e) Give dry runs a no-append mode, or else state the write in `--help`.
- (f) Docstring: state 144 = 4 POSTs × 36 other candidates, and state that D51 is not a per-candidate hold
  unless (a) lands.

### Ticks for Khoa (decisions, not repairs)
1. **Inherited G1-G3.** Keep the stricter clause, or match meaning.decidable_verdict (D39's text).
2. **Earliest meaning row binds for ever,** including a null row written while an input was unreadable. Either
   keep it and write a recovery procedure, or let a newer scorer replace a null row.
3. **S11 after a library POST.** Hold library PnL twins too (the literal fix text), or keep today's behaviour.
4. **C19 (round 4 m23).** Strike it from the docstring, or implement it.

### Routed to other owners (not blocking submit)
- **Design owner:** 04 §5.4 gets D51, D39 as built, S11 and C16 with D51.
- **ci owner:** re-record the golden for the 62-file closure on its own commit.
- **gen and judge owners:** D51's cohort versus benchmark.cohort_of for marked stamps; the push-split tick.
- **D58 owner:** bound load_ledgers inside the wq-forge unit.
- **digest:** label its eligible count as library only, or pass a read-only gate.

### MINOR for backlog
- **m1.** The meaning-recorded-row-unread branch is reachable only through a glob metacharacter in the ledger
  path (harvest.read_jsonl globs). No production path has one. M24 survives.
- **m2.** Held generated candidates are re-scored each round, at about 0.63 s and 25 MB each on the Mac
  (auditor 3). submit runs with no `timeout` in forge_loop.sh:215. Fix: read the standing row first, and hold
  without re-scoring when it already fails.
- **m3.** One S11 exception holds every generated pick for that invocation (lines 282-284). Fix: catch per
  entry.
- **m4.** S11 does not cover an alpha POSTed by the previous invocation (auditor 2 Q1 POSTs the twin). Whether
  a SELF re-read 20-35 minutes after a POST can be trusted is UNMEASURED. Settle it by measurement before
  extending S11.
- **m5.** S11 compares curves across regions. Whether the platform's SELF check is per region is UNKNOWN.
- **m6.** The host peak memory of load_ledgers is UNMEASURED (host runs/ is 248 MB, against 112 MB on the Mac;
  the S4/D58 class).
- **m7.** The digest's eligible count omits generated candidates, which are held as `meaning-not-scored`
  (probe Q3 by auditor 2; grep digest.py:86).

## Draw-6 audit: gen (2026-09-24)

Adjudicator, module `gen`. Audited bytes (sha256 prefix): forge/gen/__init__.py 401172488890b8c3, families.py
0becf21ad7d9bbac, posterior.py 439e7fea2c3fafe3, productions.py 2f1d98e6057e7ea0, propose.py 0a1d26d29d549b01,
repair.py 2c584c9a1adc6236, spend.py 1dc884792a525a54, state.py 1c3a6fade5030200; tests test_gen_families
0bf1d9f3, test_gen_posterior 1cdf9ea8, test_gen_productions 7a762f90, test_gen_propose 6172d184, test_gen_repair
a3dda39c, test_gen_spend 027ba041, test_gen_state 9e033ba0. Also read: tools/layered_sim.py 73b1205161039279.

Setup: snapshot scratchpad/d6_gen_adjudicator, code only (forge tools harness harness13 vps fingerprint.py
operators.py conftest.py .github, no `__pycache__`, plus fetched/rc/operators.json), deleted after the audit.
Baseline gen suite on the snapshot: 81 passed. Every mutant below was applied on the snapshot, run with one
pytest process, then restored from the repo bytes and `cmp`-checked. Evidence kept in the scratchpad:
d6gen_adj_lone.py/.out, d6gen_adj_skew.py/.out, d6gen_adj_inf.py/.out. No VPS access, no simulation, no commit.

### Verdicts on the builder's SERIOUS items (re-run by me)
- **G1 LANDED.** Reverting the cohort filter (`or cohort(r) != own`) fails 2 tests: test_gen_repair
  ::test_an_out_of_cohort_sibling_is_not_a_neighbour_the_judge_counts and test_gen_propose
  ::test_an_existing_in_cohort_neighbour_counts_and_an_out_of_cohort_one_does_not; 79 pass.
- **G2 LANDED (tests only).** Sample mutant O1 (`formula = s`, orientation never applied) fails
  test_a_minus_leg_is_written_one_minus_and_a_plus_leg_is_not and test_orientation_reaches_the_formula_through_propose.
  The other G2/N5 kills are auditor 2's re-run with its own driver (30 of 30), not re-run by me.
- **G3 text half LANDED** (spec auditor, and auditor 2's third seed 29). The tick half is open and gates stage 4.

### The one SERIOUS that survives — outside forge/gen (owner: tools/layered_sim.py, the dispatcher)
**S1 (auditor 3), CONFIRMED by my probe.** A multisim group of ONE is posted by `post_one(s, formula,
arm=settings_arm)`, whose body is `settings_for(arm) if arm else dict(SETTINGS)`. The construction's own
settings are dropped, the single-post path arms no settings guard (`_reap` polls it without `expect_settings`),
and `_child_row` journals the PLANNED settings. Probe d6gen_adj_lone.py (fakes for session, _post_patient,
poll; nothing posted) through `LS.run(batch=...)`:
- one construction planned USA/TOP3000 decay 4 INDUSTRY trunc 0.15 -> body posted decay 0 SUBINDUSTRY 0.05;
  the journal row says decay 4 INDUSTRY 0.15.
- 11 USA constructions then 1 GLB/MINVOL1M -> bodies `[list[10], dict, dict]`; the lone GLB construction was
  posted as region USA, universe TOP3000, and journalled as GLB/MINVOL1M.
Scope, POST-HOC: on the Mac journal copy (state/layered/runs/forge.jsonl, 36,855 lines) 0 of 32,820 alpha
rows were single-posted (no parent_url), and all 32,820 carry planned settings that differ from SETTINGS on at
least one of region/universe/decay/neutralization/truncation. So the defect is not gen-specific: any lone
group on any path would be mis-simulated; it has not happened yet (auditor 3 reads 0 of 38,624 on the VPS).
Why the composites path has produced no lone group: MECHANISM UNKNOWN (not examined). Gen reaches the case
by construction: auditor 3's probe produced a lone D51 neighbour (case A) and lone groups in 4 of 41 synthetic
rounds (synthetic labels; live rate UNMEASURED).
Required fix, before stage 4 (any forge.env / FORGE_ARGS flip to `--mode gen` or `--mode randomised`): post a
group of one with the construction's own payload (as `post_many` does per child), with a test that captures
`_post_patient`'s body for a one-construction batch whose settings are not SETTINGS and fails today.

### Sign-off reasoning
No BLOCKER or SERIOUS survives in the forge/gen bytes. S1 is in another owner's file, predates this draw and
is not activated by shipping gen: the live unit runs `--mode composites` (auditor 3's read-only ssh; not
re-read by me). It does block gen going live, together with the open ticks (G3, push-split, N4, m18, m2, N7,
and the D37 trigger item below).

### MINOR — cheap, owed by the builder (text and asserts; no behaviour change)
1. test_gen_propose.py:144-145 comments say "measured 0.989" and "0.245 against 0.231". Re-measured
   (d6gen_adj_skew.out): posterior ds00 0.985, floor ds00 0.265, base 0.2313; auditor 2 got the same two numbers
   independently. Correct the comments and the builder report (RULE 0 item 5).
2. Mutant B08 (`need = RP.NEIGHBOURS`) SURVIVES: re-run by me, 81 passed. Assert `"neighbour-short" not in
   counts` in the in-cohort test. Auditor 2's other test gaps, not re-run by me: B12 (repair room ignores
   n - len(out)), B17 (repair charged before admit), B02/B04 (universe/region dropped from the charge key),
   B24 (`<= 1` knob), B27 (formula_key whitespace).
3. G1b's propose-level assertion (test_gen_propose.py:346) is inert: with the out-of-cohort re-plan guard
   removed, the propose test PASSES and only the repair test fails (re-run by me). Use two out-of-cohort
   siblings or assert the planned set.
4. spend._readable accepts +/-inf (PO._num rejects only NaN and bool). Probe d6gen_adj_inf.out: an inf curve
   is readable, and `_predict` returns 1.0 against an unrelated random walk whose clean reading is 0.0409, so a
   false PNL_STOP. Latent: my census of state/pnl_curves gives 0 of 2,810 files with a non-finite value. Fix:
   `math.isfinite` plus a test with an inf curve.
5. Text: families.py:5-7 still says every hypothesis-keyed rule "sees a stable key" (m22 half; quarantine does
   not bind on singletons), and productions.py:376 implies 04 §3.3 was corrected (it was not); spend.py's THE
   TICK paragraph does not name PNL_STOP (m20 half); productions.py:93 says `setdefault`, but in a randomised
   round runner.stamp overwrites meta.arm (same value); __init__.py:9-10 names only `--mode gen`, not
   `--mode randomised`; repair.py:40-49 names only "a push" although run_config hashes every argument except
   seed and plan (runner.py:278-294) and +EXTRAS moves pipeline_version (runner.py:259), and submit.d51_ready
   (submit.py:197-200) reads the same function, so a stranded alpha is held there permanently;
   existing_neighbours' docstring says "what the judge counts", but the judge also filters on SCORED_STATUS and
   non-empty checks (0 rows differ today, auditors 1 and 2, two ways).
6. Builder report corrections: fill_gen does NOT add by_cell into `taken` (runner.py:721ff; the only
   `taken_t[cell] +=` is fill_typed:703; fill_gen's docstring says it is not written back); gen_draw IS in
   recover_orphans ROUND_KEYS (recover_orphans.py:60), so it is not part of a construction's identity.

### MINOR for backlog / tick queue
- D37 trigger on a formula that already passes (auditor 3's probe: 10 repairs of a harvest-pass formula).
  Confirmed by reading: is_trigger/triggers (repair.py:101-141) never exclude a harvest-pass formula key. It
  changes D37's population, so it is a RULE 2 tick, not a builder fix.
- seen_ids (gates.journal_ids, forge/gates.py:18-32) has no status filter, so a variant lost to a transient
  dispatch failure is never re-planned. Mac copy: 217 of 36,855 lines carry AUTH-FAIL/POLL-DEADLINE/CANCELLED/
  POST-401/POLL-EXHAUSTED/GUARD-REFUSED (auditor 3: 233 of 39,196 on the VPS).
- Plan-time D18 and the PnL stop compare against 5 logged accepted POSTs, against 248 in active_book.json
  (auditor 3, VPS; not re-derived by me). Tick: which set D36's "accepted POST" means.
- Draw-5 survivors P23 (draw universe ignores the cell; every test cell is TOP3000) and F04 (fieldless
  member); P22, S09, X09 equivalent on reachable inputs (auditor 2).
- The G1 test builds the judge's pool with RP.cohort instead of benchmark.cohort_of (auditor 1).
- SUSPECTED, routed, not verified by me: a refused neighbour variant is not replaced within the round
  (repair.py:207); D58 x gen State memory grows with generated rows and the growth test uses library rows only
  (runner/gen owners); experiment scripts copy `gen:` meta onto derived rows (c11_neut, tvr_pairs, pow_pairs
  owners); typed.py's DISPERSION branch shadows VEC for vec_stddev/vec_range (typed owner); stage-4 wiring
  exists while the ticks are open (orchestrator holds any forge.env flip).

Signed for push: yes (the forge/gen bytes above). NOT signed for stage 4.
SERIOUS/BLOCKER fixes still required: none in forge/gen. Before stage 4: S1 in tools/layered_sim.py (dispatcher
owner), plus the open Khoa ticks listed above.
MINOR for backlog: items 1-6 above are cheap and owed by the builder; the backlog list above carries the rest
with its evidence.

## Draw-6 audit: release (2026-09-24)

Adjudicator, module `release`. Audited bytes (sha256 prefix, each repo file unchanged from the start to the end of
this audit): tools/deploy.py 81a7b3f2, tools/tests/test_deploy.py f007c9d9, tools/tests/test_ci_publish.py 05f5998f,
tools/requirements.lock 2edd6d7b, vps/forge_loop.sh 2b8283ed, vps/forge.env 1260678b, vps/systemd_wq-forge.service
d88121f6, vps/wq-judge.service a92281e8. All runs were on a code-only snapshot (scratchpad/d6_release_adjudicator,
33 MB, deleted afterwards). They used `python3 -B`, PYTHONDONTWRITEBYTECODE=1 and one pytest process at a time. The
one mutant and the one candidate fix were restored and cmp'd. There was no ssh, no sim, no code edit in the repo and
no commit. Evidence: scratchpad/d6rel_adj_ev/.

### Baseline

- `pytest tools/tests/test_deploy.py tools/tests/test_ci_publish.py`: **263 passed** (baseline.out).

### Verdicts on the three audits

1. **SERIOUS, upheld (the exec lens's SERIOUS): push reads forge.env with universal newlines, so draw5 MINOR 1 did
   not land on the path push uses.**
   - Where: shipped_production_args (deploy.py:722) calls `read_text()`, which turns every CR into "\n" before the
     control-character check runs.
   - REPRODUCED (adj_env_probe.out).
     - A CRLF copy of the shipped forge.env: the production reader ACCEPTS (300, '...--ab new'). The pure
       function, given the same bytes, refuses '\r'. bash sources N=$'300\r' and the last word $'new\r'. That word
       is not in runner.py:921's choices, so argparse exits 2 every round.
     - A lone CR: `FORGE_ARGS="--mode composites --tag x"\r#" --plan ..."` reads as (300, '--mode composites
       --tag x'). bash's argv then carries `--plan` (and `--seed 5` in the sibling case), the two flags
       _forge_env_from exists to refuse.
   - The suite cannot see it. Mutant A15 (the whole forge.env in CRLF) SURVIVES with 263 passed (mut_A15.out,
     restored cmp-equal).
   - NEW HERE, MEASURED in the test harness (test_adj_crlf_watch.py / .out): the D43 watch is blind to the round this
     produces.
     - forge_loop.sh echoes `N=$N` into the round header, so the header carries the CR. That the host writes it
       this way is EX-ANTE from the echo plus the bash result above; it was not observed on the host.
     - _markers_from uses str.splitlines(), which splits the header at the CR, so the round is never seen.
     - The same argparse round without the CR rolls back (rc 1). With the CR: rc 6, watch_timeout, cause
       "no_round_finished", nothing rolled back.
   - Why SERIOUS and not draw5's MINOR:
     - The builder reports "CRLF ... now refusals", and forge.env's header tells the operator that deploy refuses
       "a control character anywhere in the file". Both are false on the only path push() uses.
     - D43, the stated backstop, reports "no round finished" while the loop idles. Each round exits 2 and then
       sleeps 3600 s.
     - The next planned edit of this file is the D54 flip.
     - It is not destructive and it spends no quota.
   - Fix (measured cheap): `read_bytes().decode("utf-8")` at deploy.py:722 (candidate_fix.diff).
     - With it, the CRLF and both lone-CR cases are refused (adj_env_probe_fixed.out), and the suite stays at 263
       passed.
     - It needs a test that goes through shipped_production_args on files written with write_bytes: CRLF, and a
       lone CR hiding --plan and --seed.
2. **No other BLOCKER or SERIOUS was raised.** The spec and assume lenses signed nothing as SERIOUS. Every other
   item below is MINOR or SUSPECTED.
3. **The draw5 SERIOUS 1 fix, required item 2, and MINORs 2, 3, 4, 6, 7, 8, 9(a) and 11 landed**, as all three lenses
   found by reading and the exec lens found by 16 reverts. I did not repeat those reverts. MINOR 1 landed only for
   the pure function (item 1 above).

### Reproduced MINORs, cheap, owed by the builder

- a. **Round 4 m9 did not land, and the builder's report does not account for it.** It is on round 4's cheap list,
  item 5. REPRODUCED (test_adj_m9.py / adj_m9.out): with a failed local append, two watches of one push give rc
  [6, 6] and 2 target watch rows. The guard at deploy.py:2200 reads the local ledger only.
- b. **The moved path exits 7 when the units do not come back.** With the second manifest read showing V2 and
  start_units returning False: rc 7, not units_down (5), and nothing is running (adj_moved.out).
- c. **The moved-path row says `running_after` "watched" while the target runs V2** (adj_moved.out). The DEPLOY_LOG
  text for watch_not_rolled_back gives no "moved" reason. Whether DORA should charge V1 for this belongs with draw5
  verdict 2 (the scoring owner or Khoa).
- d. **A last line of only NBSP or U+2028 passes the parser, but bash's `.` returns 127 on it** (adj_env_probe.out).
  load_forge_env then puts the unit's Environment= back. Refuse non-ASCII, or skip only lines that are empty or
  start with '#'.
- e. **The D58 marker says "backing off 900s" when ROUNDS=1, which never sleeps.** Read at forge_loop.sh:176-178; the
  test pins the text.
- f. **NEW: any watch marker holding a CR is dropped by _markers_from's splitlines().** Latent once item 1 is fixed.
  Split on "\n".
- g. **Test gaps.**
  - A15: re-run here; it survives.
  - A2 and A12: the current code does refuse `N=3x` and a non-UTF-8 byte (adj_env_probe.out), so these are test
    gaps, not defects.
  - A3-A9 and A13 are the exec lens's; I did not re-run them.
  - Nothing asserts that loop_imports' visited set is shipped by PLAN (the assume lens: all 72 are, today).
- h. **Texts.**
  - forge.env:16 still says "Once forge/runner.py has `--mode randomised`". runner.py:322-334 has it.
  - The _forge_env_from docstring's "Refused" list omits control characters, --seed and --plan.
  - The watch section comment omits the signal marker.
  - The _watch_rollback docstring states its gap as seconds. EX-ANTE by reading, not reproduced: write_manifest
    runs after run_smoke, and other_operator_busy cannot see an ssh smoke, so the gap covers every push that has
    not yet written its manifest.
  - "2.9x" divides MiB by MB.
  - The 1,135 MiB read is not saved; only 1,140 is.
  - A skipped probe is recorded as "unseen / not finished".
  - The venv-check refusal drops stderr.
- i. **Builder report corrections.**
  - r2_regex_superset.out lists numpy, scipy, matplotlib, pytest and others. "requests and yaml only" is
    loop_imports' own reach filter. The independent second way is the runtime import.
  - docs/evalharness/backlog.md exists (row D5-RL-Pc).

### Dropped

- **The spec lens's "the 72-file closure count cannot be re-derived".** The exec lens (p3) and the assume lens
  (closure_vs_plan.out) each re-derived 72 from loop_imports.

### Backlog and tick queue (not reproduced by me unless stated)

- **The intermittent push test.**
  - The candidate cause (push hashes and stages the live tree) is SUFFICIENT. My 2 ms writer on a snapshot forge
    file failed 1 of 3 runs with `assert 2 == 0`; the controls failed 0 of 3 (adj_flake.out). The exec lens got
    9 of 10 against 0 of 10.
  - Which refusal fired was not captured.
  - Whether this caused the builder's one failure: MECHANISM: UNKNOWN.
- **The not-undone paths restart the watched push's units_before**, not the units that were running when the watch
  stopped them.
- **A-B-A version compare** (SUSPECTED, contrived).
- **A lock shared by push and watch** (tick).
- **Khoa's OOMPolicy tick** should also carry:
  - the 900 s value;
  - that the D58 back-off is unreachable under OOMPolicy=stop (disclosed);
  - MemorySwapMax (neither unit sets it; read);
  - that tools/watchdog.py:54-55 does not watch wq-forge (read);
  - that the smoke's planner runs outside the unit's cgroup.
- **Routed:** D58 skipping the round's steps (orchestrator), and submit's HOLD exit 3 read as an error (scoring owner
  or Khoa).
- **The builder's own not-addressed list:** MINOR 5, 9(b), 9(c), 10 and 12; the E1 residuals; the one-arm smoke; and
  pytest and scipy unpinned.

Signed for push: **no**.
SERIOUS/BLOCKER fixes still required:
- Item 1. shipped_production_args must read the bytes bash reads (one line), with a test through the production
  reader covering CRLF, a lone CR hiding --plan and a lone CR hiding --seed.
- Then re-run both test files on a fresh snapshot, and revert the line to show that the new test fails and that
  mutant A15 is killed.

MINOR for backlog:
- a-i are cheap and owed by the builder. Their evidence is in scratchpad/d6rel_adj_ev/.
- The backlog and tick list above carries the rest.
