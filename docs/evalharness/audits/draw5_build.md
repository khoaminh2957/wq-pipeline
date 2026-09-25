# Draw-5 build audits (2026-09-23)

## Draw-5 audit: meaning (2026-09-23)

Adjudicator, module `meaning`. Audited bytes (sha256 prefix): forge/meaning.py 01bc3c3a11921672,
forge/tests/test_meaning.py 80a55fc695552e65. I also read forge/offline/benchmark.py b30d255c alongside them;
it was modified at 22:01, after the builder's run. The repo copies were still identical to these bytes when
this section was written.

Setup:
- Snapshot: scratchpad/d5_meaning_adj. It was made with rsync, leaving out state, fetched, .git and the large
  data directories. Three files were copied in: state/forge/submitted.jsonl, fetched/rc/fields/USA_TOP3000_d1.jsonl
  and fetched/rc/field_labels.jsonl.
- Probes: scratchpad/d5adj_meaning_probe.py. The items below cite them as V1..V14.
- Mutants: scratchpad/d5adj_meaning_mut.py. Each mutant was applied to the snapshot, then `__pycache__` was
  cleared, test_meaning.py was run, the file was restored, and `cmp` checked it against the repo. Every
  restore compared equal.
- VPS: read-only `ssh -n -o BatchMode=yes` only (ls, plus a python count that reads files).
- No sim, no --live/--submit, no commit, no code edit, and no .pyc in the repo (checked with find).

Every item below is an OBSERVATION on stated inputs (RULE 0). No mechanism is claimed.

Baseline: `PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest -q -p no:cacheprovider forge/tests/test_meaning.py`
gives **100 passed** against the current benchmark.py. That settles auditor 3's point that the builder's
run predated the benchmark.py change. The no-op mutant also gives 100 passed.

### What landed (verified)
- **D52 in `_g4`.** Only the three named grouping fields are excluded, the line is 200, a leg's count is the
  minimum over its fields, and G4 fails only when every leg is crowded.
  - The four POSTs' per-leg counts, re-derived by all three auditors, match the test:
    - vRk095rv [10, 27790, 15084]
    - kqVbg1xP [6259, 10]
    - vRk1J2jd [2, 67731]
    - rK5RGeqa [1, 6259, 67731]
  - The data-tier pin runs, and passes, on the Mac files.
  - The host catalogue (dated 08-12) reads 32/33, 6 and 1 for the uncrowded leg fields, so the verdicts are
    unchanged.
- **Round-3 X4 (journal clause).** The alpha's own rows never collide, an earlier different alpha fails the
  clause, and an unknown order reads null.
- **Round-3 m18.** The narrowed claim is in the docstring and in the evidence.
- **Draw-4 schema refusals** are in `check_row`.
- **`decidable_verdict`** is D39's rule and gives the same result as `benchmark._standard_gate`.
- **`append`** is idempotent per (alpha, formula_sha) and repairs a torn last line.
- **Eight of eight on the four POSTs.** Auditor 2 re-derived this on the real Mac ledgers. The highest
  pairwise similarity is 0.495, and neither NO_GO family matches.

### Adjudication: auditor 2's SERIOUS (a null row freezes an alpha) is downgraded to MINOR (M1)
- **Reproduced (V1).**
  - vRk1J2jd scored with catalogue=None: decidable_verdict is None and `append` returns True.
  - Re-scored with the catalogue: decidable_verdict is True and `append` returns False.
  - `B._standard_gate` then reads **None**. Control: the full row on its own reads True.
  - A first row with scored_at = created-5 freezes the alpha the same way (V2). `check_row` also accepts a
    scored_at in milliseconds (V2b).
- **Not reachable through the module's own loaders on current host data:**
  - `load_ledgers` never returns None.
  - `load_catalogue` returns None only when the file is absent. /opt/wq/fetched/rc/fields holds 34
    catalogues, and each of the 13 (region, universe, delay) cells in /opt/wq/state/layered/runs/forge.jsonl
    has its file. So auditor 2's premise, "only USA_TOP3000_d1 exists on the host", is **false**.
  - The label file is present.
  - The host D18 index is complete: 5 accepted POSTs, 0 of them without a formula.
- It fails closed (no wrong submission), and nothing imports forge.meaning yet.
- The trigger needs one of: a caller that passes None or the wrong cell, a clock-skewed scored_at, or a
  future cell with no catalogue. It is cheap to fix and should be fixed before the stage-3 router calls
  `append`.

### Ticks for Khoa (decisions, not repairs) before the stage-3 router imports `decidable_verdict`
- **T1: G4 minimum vs maximum (vs leaving denominators out).**
  - By construction, `legs_of` puts every data field into exactly one leg. So under the minimum, G4 reads
    True whenever ANY non-grouping field has alphaCount < 200, and False only when every field is known and
    ≥ 200.
  - Auditor 3 measured agreement with that "any field" rule on 15,428 of 15,428 journal formulas, 49 of
    them False. I did not re-derive this.
  - The four POSTs read 4/4 under either reading.
- **T2: a vacuous G5 reads true, not null.** "Vacuous" means no leg is description-signed. 3 of the 4 POSTs
  read true with `checked: []`.
- **T3: G7 is existence only.** Point-in-time stays null and UNMEASURED. The builder raised this.
- **T4: a corrected SCORER can never re-grade a pair.** `append` and `meaning_index` both keep the earliest
  row per (alpha, formula_sha).

### Routed to other owners (not blocking meaning)
- **benchmark (scoring owner):**
  - The MEANING_DECIDABLE comment still reads G4 as `"every leg alphaCount >= 200"` … "PROVEN when every
    one of these is true", which is the opposite direction to D52.
  - Round-3 S8 item 4 is still open. `_standard_gate` routes on the `gen:` prefix of meta.hypothesis and
    never reads the row's `route` or `inherited_from`; its own docstring lists this as NOT done.
- **tools/ci_fixture.py (ci owner):** the meaning rows at `meaning = [...]` carry route "auto" and scorer
  "fixture". "auto" is not in meaning.ROUTES, so the golden card pins a row that `check_row` refuses.
- **tools/funnel/precheck_lib.py:** `extract_fields_grammar` adds `filter`/`true`, and `currency`, to a
  formula's field set (V14). So a one-field NO_GO family written with filter=true escapes precheck.
- **release/state owner:** /opt/wq/state/alpha_hypotheses.jsonl is absent (read-only ls), so the NO_GO
  clause is vacuous on the host.

### Dropped
- Auditor 2's reachability premise: false (see the adjudication above).
- Auditor 2's claim that the negative-denominator case reads decidable True: on the suite's catalogue it
  reads False, because G4 fails. The G5 error itself does reproduce (M7).
- Auditor 1's point that the MEANING_LEDGER note calls the writer non-existent: benchmark b30d255c already
  names forge/meaning.py as the writer.
- Auditor 3's point that "100 passed" predates benchmark.py: re-run here, 100 passed.

Signed for push: **yes**. No BLOCKER and no SERIOUS survives.

BLOCKER/SERIOUS fixes still required: **none**. Cheap MINORs that should land before the stage-3 router calls
`append`: M1-M4. M10 should land before the next deploy smoke.

### MINOR for backlog
- **M1 (cheap).** The freeze above (V1, V2, V2b).
  - Fix: `append` refuses any row that carries a null caused by an unread or mismatched input. The inputs
    are: catalogue None or for the wrong cell, labels None, or any ledger None. It also refuses a
    scored_at outside a plausible epoch-seconds window.
  - State T4 in `append`'s docstring.
  - Test: append a catalogue=None row first and then a full row. Either the judge reads True, or the first
    row is refused.
- **M2 (cheap).** Two `check_row` gaps.
  - `_HEX64.match` accepts a formula_sha with a trailing newline (V3). Fix: use `fullmatch`.
  - An int scored_at of 10**400 raises OverflowError instead of ValueError (V3b).
- **M3 (cheap).** `_text_gates` copies composite verdicts with `in (True, False)`. With verdicts
  {G1: 1, G2: 0}, `score` emits G1..G3 = [1, 0, True], and `check_row` refuses that row (V4). The mutant
  "copy raw verdicts" survives. Fix: use `is True or is False`.
- **M4 (cheap).** `score` raises TypeError when meta.hypothesis is a list, and AttributeError when settings
  is not a dict (V8). It should read null in both cases.
- **M5.** The G8 journal clause reads True when the candidate-id lookup misses.
  - The journal holds {B9 at 50, A1 at 100}. With the test settings (ST) it reads False. With decay 5, or
    with delay 1.0, it reads True: "no earlier alpha" (V6).
  - Fix: when the alpha has no row of its own under that cid, read null, and change the `([], True)` case.
- **M6.** A catalogue cut down with `load_catalogue(only=...)` cannot be told apart from a full one. A field
  outside `only` reads G7 False, "not in the catalogue: fb" (V7).
- **M7.** G5 orientation errors.
  - A negative-constant denominator is not flipped. `if_else(greater(group_rank(fa, sector) / -1, -0.5), …)`
    records fa at +1 and reads G5 True, while the `(1 - x)` form of the same condition reads G5 False.
  - A multiply by -1, in either form, leaves the leg unchecked (`checked: []`) (V5).
  - Auditors 2 and 3 say the pass-first grammar flips a leg only with `(1 - x)`. I did not re-read that.
- **M8.** G6 writes a false reason text (RULE 0 #4).
  - `signed_power(multiply(A, B), 2)` and a two-leg `divide` both read False with the reason "one leg: a
    monotone re-rank of one signal (the standard's Law-1 null)" (V12).
  - A leg whose only field is a denominator reads null with "a field has no label", although the field is
    labelled (V13).
  - I did not re-derive auditor 2's count of 497 formulas.
- **M9.** Rules with no test that fails without them (hard limit).
  - Each of these mutants leaves 100 passed:
    - the G5 ratio numerator carries no direction;
    - G6 drops H2;
    - G6 takes every forge.typed hard reason (so the H1/H4 exclusion is unpinned);
    - a partial leg whose known field is uncrowded reads null;
    - idempotency is keyed on alpha only;
    - the inherited route picks the least similar composite;
    - the text gates copy raw verdicts.
  - The purity test patches only `builtins.open` and `Path.open`. `io.open is builtins.open` is True, so
    patching the builtins name does not cover `io.open`. Auditor 2 also showed that a `time.time()` read
    inside `score` passes the test.
  - Fix: add one case for each.
- **M10.** test_d52_on_the_desks_own_files_when_they_are_present runs in the deploy smoke.
  - It ships (deploy PLAN `"forge/": "forge/"`) and runs under the smoke's `pytest forge/tests -q
    --no-header -x`.
  - It parses submitted.jsonl with bare `json.loads`. forge/submit.py appends with a plain `open("a")`, so
    a torn line is possible, and it would fail the smoke and roll the deploy back.
  - A catalogue refresh that crowds a leg would also turn deploys red.
  - Fix: read the log with `M._jsonl`, and ask the release owner whether data-drift pins belong in the
    smoke at all.
- **M11.** Text claims that the code does not match:
  - (a) The NO_GO clause is not "hit as precheck_lib.precheck hits it". precheck adds filter/true/currency
    to the field set, so meaning is stricter (V14).
  - (b) forge.typed does not read a denominator as directionless. In `Judge._arith`, `5/fa` takes fa's
    sign, and a signed denominator makes the ratio's sign 0.
  - (c) `meaning_index` reads alpha, gates, formula_sha and scored_at. `route` and `scorer` are read by
    `_standard_gate`, not by `meaning_index`.
  - (d) G5's label, "EX-ANTE (rule from hypothesis_standard.md gate 5)", is wrong: the value is design 04
    §4.2's sign_verdict proxy. G7's label cites the whole gate, while the value is the existence half only.
  - (e) "score reads no file" holds only after forge.llm.verify has been imported.
- **M12.** `load_ledgers` reads every absent source as empty, which is a vacuous pass. Only the NO_GO bank's
  absence is named in the evidence. Fix: name every absent source in G8's evidence, or read an absent
  source as null.
- **M13.** Corrections to the builder's report (RULE 0 #7; the files are not affected).
  - "37 of 37 mutants killed" was 36 mutants plus 1 no-op control. scratchpad/meaning/mut.py MUTANTS has 37
    entries with no "undated own row" or "string scored_at" mutant, and it was last written at 21:42,
    before test_meaning.py (21:46).
  - "94 of 94 composites have zero trips because load_composite already refuses gates 1-3" gives a false
    mechanism. `_check_composite` checks the 25-word length, the agent words and the label prefix. It does
    not run hard_gates' gate-1 paraphrase check or gate-3 dated-citation check. The zero count is POST-HOC,
    and anything beyond those three checks is MECHANISM: UNKNOWN.
- **M14 (SUSPECTED; route to forge/labels.py).** `build` writes field_labels.jsonl in place with
  `open(out_path, "w")`. A load during a rebuild could therefore read partial labels, and G5 would pass the
  missing fields vacuously. Not reproduced: that needs a concurrent rebuild.
- **M15 (SUSPECTED).** `legs_of` gives every operand of a split multiply the parent's orientation, which
  assumes the operands are non-negative. Auditor 1 says this is unreachable on the grammar; I did not
  reproduce it.

## Draw-5 audit: pipeline (2026-09-23)

Adjudicator, module `pipeline`. Audited bytes (sha256 prefix): forge/runner.py d2e84b70,
forge/offline/recover_orphans.py 99aae169, forge/tests/test_runner.py ffa78576, forge/tests/test_recover_orphans.py
59b694a9, tools/notify_lint.py 36f2d30a. They are unchanged in the repo at the time of writing. The baseline is the
builder's scratchpad/pipe_owner/orig, whose files hash to the draw-4 audited bytes (runner 9cdf8d90, recover_orphans
0a5ae8a9, notify_lint 0d52f187). tools/deploy.py was 7ff14dbc.

Setup:
- Snapshot: scratchpad/d5_pipeline_adj, made with rsync without state, fetched or .git.
- Mutants: scratchpad/d5adj_pipe_mut.py. Each one is applied, `__pycache__` is cleared, the three named test files are
  run, and the file is restored and `cmp`'d against the repo. Every restore compared equal.
- Probes: scratchpad/d5adj_pipe_probe.py (V1..V6) and d5adj_pipe_llm.py.
  - layered_sim is replaced in sys.modules by a recorder, and PLANS and RUN_CONFIG_LOG point into a tmp dir.
  - No `--live` flag is passed anywhere. V2, V3 and V6 set `live` on the parsed namespace only, as auditor 2 did.
- VPS data: only the auditors' existing scp copies (scratchpad/a3/forge.jsonl, 43,114 lines; pipe_owner/vps_plans,
  221 files). I made no new VPS access and wrote nothing on the VPS.
- No sim, no commit, no code edit. There is no .pyc in the repo newer than my first probe, and there is no
  state/forge/run_config_log.jsonl in the repo.

Every item below is an OBSERVATION on stated inputs (RULE 0). No mechanism is claimed.

Baseline: the three named files give **164 passed**. With runner.py, recover_orphans.py and notify_lint.py reverted
to the originals, **exactly the 15 new tests fail**, so the builder's claim holds. The two positive-control mutants
are both KILLED: dropping the RUNNER_PLAN filter, and taking gen_state out of ROUND_KEYS. The no-op control gives 164
passed.

### What landed (verified)
- **P1 / D46.** load_plans() indexes `<seed>.json` only, and the four-shape test uses the real main(), load_plans,
  match and child_row.
- **P2 contract test, P3 (B03), P5 (b)-(f).** Present as the spec auditor read them.
- **D30 amendment.** main() reads the plan once, and those same bytes are hashed. A round without `--plan` hashes the
  old body.
- **D45 writer.**
  - It is the host-keyed interface that benchmark.cohort_live_days reads.
  - One LOCK_EX covers the read and the append. The shared-lock separator (auditor 2's d5a2_shlock.py, re-run here)
    reads "blocked = True" on the real code and False under LOCK_SH.
  - A failure is printed, and the round continues.
- **X3.** Settled: only a live start records.
- **S15 code half.** gen_state is in ROUND_KEYS, and arm and gen_route are not. V5: entries that differ only in
  gen_route give None.
- **D47 groundwork.** The arm is set by setdefault: a.mode for a planner round, `plan` for a `--plan` round.
- **notify_lint.** The token is assembled from parts and has the same value.
- **P8 (golden re-record).** NOT landed. It is the orchestrator's to do, and it is disclosed.

### Adjudication
- **No BLOCKER or SERIOUS was raised, and none survives.** Every reproduced defect either fails closed (a row
  forms no cohort, or a log row is missing and a message is printed) or is text/test coverage.
- **The dry-copy residual stays MINOR (auditor 1 defect 6 = auditor 3 defect 1).**
  - Reproduced as V2. A dry main() writes 11.json. A later live-namespace main() of the same construction dispatches
    ('v-running', 0585931c0e23827a). The row is recovered as ('v-running', 'ambiguous'), status COMPLETE: the pair
    is lost, but no wrong pair is named.
  - The host numbers, re-derived a second way:
    - 36 of the 208 planner-made `<seed>.json` copies have no journal row carrying their seed.
    - For 32 of them, no PARENT-POSTED formula block lies wholly inside the copy. For 4, one does (ambiguous).
    - Auditor 3's split was 31 and 5, under a different second criterion.
  - Legacy copies with equal stamps can still hand a row the dry copy's seed. That is the pre-existing glob-order
    OPEN (draw3_fix pipeline 5), not a regression.
- **D45 x D47 (SUSPECTED, both auditors 1 and 3).** Kept as SUSPECTED. It follows from reading the code, and D47's
  round assignment is not built. It is routed, not blocking.

### Dropped
- **Auditor 1's SUSPECTED "llmformula evidence misses the parents' `formulas`".** Re-measured:
  - 0 of the 248 llmformula formulas appear among 39,086 `formulas` entries on 3,909 PARENT-POSTED rows, nor in any
    row's formula.
  - 0 rows have arm llmformula, and 0 have an `llm:` hypothesis.
  - Positive control: pow.json's formulas are found 300/300 both in row formulas and in parent lists.
  - Closed.
- **Auditor 1's defect 10 (untested isinstance guard and short-write check).** Merged into M8.

Signed for push: **yes**. No BLOCKER and no SERIOUS survives.

BLOCKER/SERIOUS fixes still required: **none**.
- Precondition for the push, and not a module defect: the orchestrator re-records the D42 golden (P8). It pins
  runner 9cdf8d90 and notify_lint 0d52f187.
- Release note (auditor 3, read only): the deployed /opt/wq runner and recover_orphans predate run_config, stamp()
  and A11. The next push ships all of these at once, so live rows gain run_config and D45 rows for the first time.
- Cheap MINORs that should land with this push, before D47 wiring: M1-M8.

### MINOR for backlog
- **M1 (cheap, text): the P4 text is false.** It is in the runner comment above `_VERSION` and in the docstring of
  test_a_manifest_too_deep_to_parse_is_no_claim.
  - I re-ran the builder's p4_deep.py on the current deploy.py 7ff14dbc, whose `_target_manifest` now catches
    RecursionError (release 11).
  - Result: the too-deep target reads `b46536d567b5914b+untracked`, not `unknown`, and the source reads the same.
  - The text should say both layouts give `<on_disk>+untracked`.
- **M2 (cheap, text): the D30 and D45 comments predate D50.**
  - vps/forge_loop.sh calls `load_forge_env /opt/wq/forge.env`.
  - deploy SMOKE plans with shipped_production_args.
  - The comments should say "the unit's Environment until the D50 push, then forge.env".
- **M3 (cheap, text): the pow.json/c11.json claim in `RUN_CONFIG_EXCLUDED['plan']` is wrong.**
  - vps/pow_run.sh passes N=300 and vps/c11_run.sh passes N=60, and `n` is hashed, so those two never shared a
    run_config.
  - The pair that shared one is pow_run and llm_formula_run, both N=300.
- **M4 (cheap, text): no real plan writer produces the "copied arm" case.**
  - The case is described in stamp()'s docstring and in the comment on the `_PLAN_META['pow']` fixture.
  - pow_pairs.py, c11_neut.py (both variants) and tvr_pairs.py each set `arm=` themselves.
  - The fixture's 'current' should be labelled synthetic.
- **M5 (cheap, text): note_run_config's "never a guess" holds only for the new cohort.**
  - Read in benchmark.cohort_live_days: COUNTED when the host's state at the start of the day is the cohort and no
    row falls inside the day.
  - So a failed rc1 -> rc2 append keeps crediting (pv, rc1) until some start writes the row.
  - Narrow the docstring.
- **M6 (cheap, text): the "D45 \"atomically\"" quote in test_two_starts_at_once_record_one_transition is not in any
  decision.** grep of 00_agreements, architecture_round3, draw4_build and 04 finds no "atomic". Cite the draw-4 fix
  task's interface instead.
- **M7 (cheap, code + test): a log line too deep to parse disables D45 logging (V1).**
  - A valid row followed by `'['*100000 + ']'*100000` makes record_run_config raise RecursionError.
  - Two later live starts each print "!!! D45 RUN_CONFIG LOG NOT WRITTEN", and the log keeps 1 row.
  - Fix: catch `(ValueError, RecursionError)` and add a test. That test also kills M35 (note_run_config catches
    OSError only), which survives today.
- **M8 (cheap, tests): rules with no test that fails without them.** Each of these mutants leaves 164 passed:
  - M14: LOCK_SH instead of LOCK_EX. The separator above is the kill test.
  - M15: `break` on an unparsable line.
  - M16: the isinstance(dict) guard dropped.
  - M06: main() parses a second read through read_text.
  - M51: gen_route added to ROUND_KEYS.
  - M52: gen_state set to None in the A11 branch.
  - M24: the short-write check dropped.
  - M25: the fsync dropped.
  - For M24 and M25, either add a test or drop the check as impossible-scenario handling (CLAUDE.md).
- **M9 (dry-copy residual, above; V2).**
  - Fix (behaviour change): main() writes `live` into its copy, and load_plans() skips `live: false`. Legacy copies
    stay indexed. Check digest.py's newest-*.json reader first.
  - Narrow the RUNNER_PLAN comment "the copy is what was sent" to live rounds.
  - Moving the 32-36 legacy dry copies on the host needs a VPS write, which is Khoa's call.
- **M10: re-dispatching a numeric-named plan brings back ('ambiguous', 'ambiguous') (V3).** The dispatched pair was
  ('v-running', f672c71196fb26be). No current driver does this: llm_formula_run.sh's PLAN can be overridden, but the
  pow, c11 and llmformula scripts use non-numeric names. Name the limit in the RUNNER_PLAN comment.
- **M11 (already on the builder's backlog): in the A11 branch, gen_state follows index order (V4).** Order [101, 202]
  gives aaaa, and [202, 101] gives bbbb; both give seed None with candidates [101, 202]. Pin the current behaviour
  until the generator's stage 4.
- **M12 (owner question): a live round with nothing to simulate still writes a D45 row (V6).** The run exits 2,
  dispatches 0, and leaves 1 log row. Mutant M40 (the note moved below the empty-plan return) survives. Which
  behaviour D45 intends: UNKNOWN. Ask the D45 owner, then pin it.
- **M13 (route to the owner of 04_passfirst_design.md): S15's second half is missing.** Section 5 (lines 505-571)
  has no row for recover_orphans ROUND_KEYS: gen_state joins; arm, gen_route and repair_of/neighbour_of stay
  identity.
- **M14 (decision for Khoa or the orchestrator): D47 arm under `--ab new`.**
  - vps/forge.env ships `--ab new`, so setdefault leaves every live construction 'current' or 'new'.
  - benchmark.compare_arms (ARMS composites/gen) then reads no-data. It fails closed.
  - The builder's four options stand.
- **M15 (record on file): D45's "live start only" reading is not written down.** Record it in 00_agreements under
  D45, or tick it.
- **M16 (orchestrator question): plan_sha256 hashes the raw file.** pow_pairs.py writes `made_at: time.time()` into
  the plan, so rebuilding the same constructions gives a new run_config and a new D45 row. Read, not run.
- **M17 (scoring owner).**
  - The D45 host key is socket.gethostname(). A rename would leave the old host's last row still counting days.
  - No code copies state/forge/run_config_log.jsonl off the VPS, so a card graded elsewhere reads exposure
    'unknown'.
  - Both read, not run.
- **M18 (ci owner): stale ci_gate text.**
  - tools/ci_gate.py NO_LIVE_EXEMPT still keys the old notify_lint line, which no longer exists.
  - Its OPEN ITEM comment ("still holds the literal, so the entry is kept") is false. Delete both.
  - notify_lint's own comment should read "carried, now dead".
- **SUSPECTED (orchestrator + scoring owner, before D47 is wired): D45 x D47.** If each D47 arm is its own argv, every
  round appends a transition row. cohort_live_days then marks every day mixed, and both arms' cohorts count 0 days.
  EX-ANTE, by reading only.

## Draw-5 audit: gen (2026-09-23)

Adjudicator, module `gen`. I audited these bytes (sha256 prefix):
- forge/gen: `__init__` d74ebe31, families 431a5e3d, posterior aba9c7e4, productions abd22703, propose 417df14c,
  repair 4ccd15e7, spend e5a55844, state 82a67d58.
- forge/tests/test_gen_*: families ced4280e, posterior 8027c0c7, productions 01ba184a, propose 87309340,
  repair 8be0d91d, spend 041be149, state 38a7bbf4.

Setup:
- Snapshot: scratchpad/d5_gen_adj, holding forge/, tools/*.py, fingerprint.py and operators.py, plus
  fetched/rc/{operators.json, field_labels.jsonl, settings_options.json}.
- Every gen file in the snapshot is byte-equal to the repo (`cmp`).
- Mutants: scratchpad/d5gen_adj_mut.py. Each one is applied with `__pycache__` cleared, the 7 gen test files are
  run, and the file is restored. Every restore was `cmp`-equal to the repo, and no .pyc was written anywhere.
- Probes: d5gen_adj_d51.py and d5gen_adj_fam.py, plus inline scripts.
- Journal reads were read-only, on the Mac's state/layered/runs/forge.jsonl.
- No sim, no ssh, no VPS access, no commit, and no code edited.

Every item below is an OBSERVATION on stated inputs (RULE 0). No mechanism is claimed.

Process note: my first rsync filled the Mac disk (ENOSPC, 1.0 GiB free). I removed my own copy of cyberrisk/ and
research/ and rebuilt a slim snapshot. Nothing outside my scratch directory was touched. The shared scratchpad holds
245 GB, which is the orchestrator's to clear.

Baseline: **52 passed**, with operators.json present so nothing is skipped. That matches the builder's number.

### What landed (verified)
- **D34.** Re-derived a second way with exact fractions (`Fraction(sharpe) >= 4/5 x Fraction(limit)`) over the
  32,662 latest forge rows:
  - y=1 on 4,150; y=0 on 28,506; None on 6.
  - PO.y agrees on 32,662 of 32,662.
- **Checked by the spec auditor and not contradicted by my runs:**
  - harvest-pass is kept apart from D24-pass;
  - D35 priors, exclusions, the ceil(N/5) floor and TIER_U derived from operators.json;
  - D37 trigger, coin, grid and share;
  - D38 pool key;
  - the §3.2 state rule;
  - the §4.1 contract.
- **Checked by the exec auditor, not re-run by me:**
  - 0 structural refusals by runner.plan's own closure, over 10,397 real-label draws in 9 region/delays;
  - the same output under 4 PYTHONHASHSEEDs.
- **Control mutant.** Counting neighbours as family sims is KILLED (1 failed), so the harness detects a broken rule.

### Adjudication: SERIOUS items that survive
- **G1 (spec S1 = exec S1): D51 counts neighbours from every cohort; the judge counts only the alpha's own.**
  - Reproduced (d5gen_adj_d51.py): alpha A is stamped V1 and its two one-setting rows are stamped V2.
    - `repair.neighbours` plans 0 more.
    - `neighbourhood_stability` over A's cohort pool (the one benchmark.build_from builds for a stamped version,
      S10-NL) reads `{'n': 0, 'verdict': 'unmeasured'}`.
    - Over all rows it reads n 2, stable.
  - So the loop marks D51 as met while the judge reads UNPROVEN. The repair.py docstring ("what the judge counts")
    is false for the judge as it grades.
  - How often this happens live: UNMEASURED. The exec auditor's read-only count on the VPS found 1 cohort in 13
    stamped rounds.
- **G2 (exec S3 + S4): two core draw rules have no test that fails without them.** Each of these mutants leaves
  **52 passed**:
  - O1: orientation never applied to the formula;
  - O2: orientation inverted, so every '-' leg flips sign while its meta still says '-';
  - T1: `_table` ignores theta_d;
  - T2: floor draws use theta_d;
  - T3: posterior draws drop theta_d.
  - The builder's report says "floor draws ... use base weights" is guarded. For theta_d it is not.
  - The current code is right, on reading and on the exec auditor's measurements:
    - '-' legs start with '(1 - ': 0 mismatches in 3,000 draws;
    - share of first legs drawn from the favoured dataset: 0.96 under the posterior, 0.08 in floor draws.
  - Kept SERIOUS under the house rule: a silent sign flip of generated legs would ship with CI green.
- **G3 (exec S2, design level, RULE 2 gate 5): on the fingerprint family, the D36 count rules never reach 40 through
  draws.**
  - Reproduced with seed 7: 1,500 USA/d1 draws on the real labels over 14 categories.
    - FamilyIndex founded 1,500 families.
    - Second way, pairwise `fingerprint.near_duplicate` over 1,124,250 pairs: 0 near-duplicates, largest family 1,
      0 exact-hash repeats.
  - So DEAD, LADDER_DEAD, PASSED_BLOCK and the in-round cap bind only on repair grids of at most 12 rows. That is
    the precedent class of RULE 2 gate 5: a ticked rule re-keyed until it cannot fire.
  - CONFOUND: empty posterior, one round. Family sizes under a concentrated posterior are UNMEASURED.
    MECHANISM: UNKNOWN.
  - The code is faithful to D36 as ticked. What survives is the spend.py docstring, which presents the re-keying
    as keeping the four rules alive, plus the missing tick.

### Dropped
- Nothing that I re-checked failed to reproduce.
- These were not re-run by me. They are kept on the auditors' evidence and labelled as such:
  - exec's 115 mutants beyond the 12 I ran;
  - the VPS byte-equality of the imported modules (auditor 3);
  - the curve-format counts (2,810 on the Mac and 6,538 on the VPS).

Signed for push: **no**. G1 and G2 survive, and G3's text half survives.

BLOCKER/SERIOUS fixes still required:
1. **G1.**
   - `repair.existing_neighbours` counts only rows with the alpha's own (meta.pipeline_version, meta.run_config),
     the pair benchmark.cohort_of reads.
   - Test: an out-of-cohort one-knob sibling must not reduce `need`. It must fail on today's code.
   - Narrow the docstring.
   - Name the push-split case in repair.py as a D51 x S10-NL/S14 conflict for a Khoa tick: neighbours planned in
     round r+1 get the new version's stamp if a push lands between the two rounds.
2. **G2.**
   - A test that draws legs and asserts `formula.startswith('(1 - ')` iff orientation == '-'.
   - A test that a skewed dataset posterior moves posterior draws and leaves floor draws at their base share.
   - Each test must kill O1/O2 and T1-T3 in turn.
3. **G3.**
   - Before push: spend.py's docstring states the measurement (1,500 of 1,500 singletons, 0 of 1,124,250
     near-duplicate pairs) and the confound.
   - Before stage 4: a Khoa tick (AskUserQuestion). Options: keep the family unit; use a coarser unit for the count
     rules; run stage 2r's replay first; turn the count rules off.

### MINOR for backlog
- **N1 (cheap, code + test): by_cell and `want` ignore repairs and neighbours.**
  - Probe: 40 candidates, 2 of them neighbours, give sum(by_cell) 38.
  - A round with only a handed alpha gives by_cell {}.
  - Charge them to their cell, or state the exemption.
- **N2 (cheap, code + test): `handed` is not filtered or deduplicated.**
  - Probe: a library row (hypothesis 'usa_library_hyp', checks []) handed twice gets 4 neighbours, all with arm
    'gen'.
  - Keep only rows that are generated AND harvest-pass, dedupe by alpha, and count the rows dropped.
- **N3 (cheap, code): a neighbour shortfall is silent.**
  - Probe: with 3 of the 4 variants in seen_ids, 1 setting comes back and no counter moves.
  - seen_ids is gates.journal_ids, which includes rows that never got a verdict. My read-only count:
    - 342 of 33,256 journal ids have no alpha or ERROR row ever: ORPHAN-UNMATCHED 96, AUTH-FAIL 71, FAIL 70,
      POLL-DEADLINE 60, CANCELLED 25, POST-401 20, POLL-EXHAUSTED 10, GUARD-REFUSED 6.
    - Auditor 3's 272 of 341 used a different definition.
  - Add a `neighbour-short` counter.
- **N4 (tick queue, RULE 2): choices no tick names.**
  - The D36 x D51 bypass (disclosed). It should also name the neighbour cascade: a passing neighbour gets its own
    neighbours, up to the 12-setting grid, outside family accounting. EX-ANTE, read.
  - The uncapped OPEN family past 40.
  - D47's per-round arm assignment and round-3 X1, which the report does not list.
- **N5 (cheap, tests): more rules with no test that fails without them.** Each of these mutants leaves 52 passed
  (re-run by me):
  - R07: a neighbour with no Sharpe is counted;
  - R08: a two-knob row is counted as a neighbour;
  - Q06: harvest_pass reads 'incomplete' as a pass;
  - T01: the sha drops pnl_stops;
  - T02: the sha drops the triggers;
  - S03: the PnL line becomes exclusive at 0.70.
  - Also exec's survivors, not re-run by me: T03-T08, F06, P02, P03, P13, P20, P21, P24, P32-P34, R14, X03, X22 and
    X23.
  - Also: '0 exact repeats' is true by construction, so the test should assert `counts['duplicate']` instead.
- **N6 (cheap, text): docstrings that are false or stale.**
  - posterior's "1 + 11 + 2" should be at most 12 per (formula, region, delay, universe). Draws, repairs and
    neighbours all come from the same 3 x 2 x 2 settings.
  - propose's "0.2 x 15 = 3.0000000000000004" is false. In the interpreter 0.2*15 == 3.0, and 0.2*(5j) == j for
    every j up to 100,000.
  - families.py describes `StructuralIndex.is_dup` wrongly. A later member that does not match but has a higher
    similarity also overwrites the label.
  - posterior's "(Q2 b/c)" should be (Q2 c). This is the spec auditor's reading; I did not re-read §8.
  - state.py's S15 paragraph is stale: recover_orphans.ROUND_KEYS already includes gen_state.
  - productions' TIER_U note says none of the eleven was ever simulated. In the journal, ts_delay appears in 247
    rows with an alpha and ts_decay_linear in 176 (of 32,820). The 5 operators with level None appear in 0.
  - state's sha text says every verdict input is hashed, but the D51 neighbour index (rows_by_formula) is outside
    summary().
  - FieldPool's 19,596 is Pool.directional, not the primaries. Read, not re-derived.
  - The builder's report says the runner overwrites meta.arm. runner.stamp uses setdefault, so it does not; the
    value is the same either way.
- **N7 (text): on d0, harvest-pass and the D37 trigger can never fire.**
  - D0_SUBMISSION reads PENDING on 1,647 of the 1,647 rows that carry it, all of them delay 0.
  - No live effect: the loop runs with `--delays 1`.
  - Name the limit in the docstrings. Whether PENDING should block harvest-pass on d0 is Khoa's call.
- **N8: importing self_corr_predict has side effects.**
  - spend.py imports it at module level, which puts tools/ and tools/autoloop at the front of sys.path
    (self_corr_predict's module body).
  - Latent: nothing imports a shadowed name today.
  - Import it lazily, as harvest does.
- **N9 (route to the benchmark owner): axis 3 cannot see forge/gen.**
  - `_modules_with_a_real_test` globs `forge/*.py`, and `import_cycles` globs `pkg/*.py`, so forge/gen is invisible
    to axis 3.
  - The report's "23/23, no cycle" says nothing about gen.
- **N10 (cheap, code): smaller code items.**
  - AL.PASSED_BLOCK means one thing in spend (a lifetime cap) and another in the allocator (a per-round block).
  - pnl_stops has no guard against a non-numeric curve value. Latent: 0 bad curves, per the auditors.
  - Cells without a universe, or that nothing serves, are skipped without a counter.
  - effective() and typed disagree on vec_stddev/vec_range. Latent: 0 such labels, per auditor 3's probe.
- **N11 (stage-4 interface, for the runner owner).**
  - runner._construction's recipe wrappers (power, smooth) run after gen's exclusion and depth checks.
  - field_datasets=None falls back to the legacy regex.
- **N12 (builder's own list, carried over).**
  - 5 of the 11 TIER_U operators have level None in operators.json.
  - The trigger queue has no bound.
  - repair-coin-control is counted per round.
  - The unticked draw choices named in the docstrings.
- **SUSPECTED (route, not blocking).**
  - The D37 read-out must be intention-to-treat by coin: heads refused by D36 are not counted today.
  - Later draws can reach a control-arm formula.
  - allocate.cold_cells counts gen rows, a confound for D47.
  - A leg and its '(1 - x)' flip share one fingerprint family.
  - TIER_U dispersion legs carry an orientation labelled as coming from the description (stage-3 G5).

## Draw-5 audit: scoring (2026-09-23)

Adjudicator, module `scoring`. Audited bytes (sha256 prefix): forge/offline/benchmark.py b30d255cdc58eeff,
forge/tests/test_benchmark.py cc9897c8ed9ae943. Both were unchanged in the repo when this section was written. The
pre-change baseline is scratchpad/d4_scoring_adjud/forge/offline/benchmark.py bc318f2f, the draw-4 audited bytes.

Setup:
- Snapshot: scratchpad/d5_scoring_adj. It was made with rsync of forge, tools, vps, conftest.py, .github and
  docs/evalharness. It holds no state, fetched or .git. V1 read the Mac journal (state/layered/runs/forge.jsonl) in
  place, read-only.
- Probes: scratchpad/d5adj_scoring_probe.py (V1..V6).
- Mutants: scratchpad/d5adj_scoring_mut.py, with results in d5adj_scoring_mut.json. Each mutant was applied,
  `__pycache__` was cleared, test_benchmark.py was run, and the file was restored and `cmp`'d against the repo. Every
  restore compared equal.
- VPS: one read-only `ssh -n -o BatchMode=yes` (wc and grep counts).
- No sim, no --live/--submit, no commit and no code edit. No .pyc in the repo is newer than my first probe.

Every item below is an OBSERVATION on stated inputs (RULE 0). No mechanism is claimed.

Baseline:
- test_benchmark.py on the snapshot: **137 passed**. The 2 branch-drill tests need state/fetched, which the trimmed
  snapshot lacks. They predate this change, and auditor 2 ran them green with that data (139).
- The current test file against bc318f2f: **29 failed**, 108 passed, which matches auditor 2's 29.
- The no-op mutant gives 137 passed. The positive control (watch_rolled_back reads unknown) is KILLED by
  test_a_watch_row_is_never_a_deploy.

### What landed (verified here)
- **Watch rows (draw4 scoring 1).** V6 used 3 pushes plus one watch row of each outcome.
  - Deploys stay 3 and deploys/week stays 0.75 under every outcome.
  - CFR is 0.333 for watch_rolled_back, watch_rollback_failed, watch_units_down and watch_not_rolled_back.
  - CFR is 0.0 for watch_ok, watch_timeout and watch_interrupted.
- **D24 counts on the real journal.** V1, through the module's own functions: 32,656 scored, 37 of which clear the D24
  set (1.133 per 1,000). This equals the builder's and the auditors' figure.
- **Everything else.** D45 threading, `_forms_cohort`, comparable_from, D49, S8, the S10 reader and findings 8 and 9 are
  as auditors 1 and 2 state them. I re-read the code. I did not re-derive their RSS figures, their 1,096-day
  comparable_from sweep, or their 20-seed size run.

### Adjudication
- **S1 (SERIOUS, auditor 3): UPHELD. compare_arms counts the branch's own follow-up rows as branch output.**
  - Code (EX-ANTE):
    - forge/gen/productions.from_row stamps `arm = ARM = "gen"` on every D51 neighbour and every D37 repair.
    - forge/gen/propose puts both at the head of every gen round (neighbours first, then repairs). Both are keyed on
      the branch's OWN earlier rows (repair.py TRIGGER: "a generated row").
    - `_arms_strata` admits every row whose meta.arm is in ARMS.
    - JOURNAL_KEEP_META has no gen_route, so the reader cannot tell these rows apart.
    - D51 covers generated alphas only, so the incumbent arm has no counterpart rows.
  - compare_arms' docstring says the test assumes that within a (day, cell) "the two arms' alphas differ only by arm,
    which D47's round randomisation provides". A neighbour's outcome depends on an earlier B event, so for these rows
    that assumption is not provided. The pinned size (<= 0.06) was simulated without such rows.
  - V2 is a simulation through the module's own `_arms_decision`. Design: 400 draws, one cell, 1,500 scored per arm
    per day, and a fresh-draw rate of 1.13 per 1,000 in BOTH arms. Each B event adds 2 neighbours, each clearing with
    probability q. Share of draws whose verdict reads "better":

    | q | 10 days | 20 days |
    |---|---|---|
    | 0 (control) | 0.015 | 0.018 |
    | 0.10 | 0.055 | 0.11 |
    | 0.29 | 0.285 | 0.51 |

    The false "better" grows as days are added.
  - Where q = 0.29 comes from: V1, a POST-HOC analogue from the library era, not gen rows. My method used the
    normalised-formula key, neighbourhood_stability's one-knob rule, and neighbours created after their parent. It
    found 15 later one-setting neighbours of a D24-clearing alpha, and 4 of them cleared. Auditor 3's method (the
    exact formula string) found 4 of 14. What q is on gen rows is UNMEASURED.
  - It fails OPEN on the RULE 2 gate-3 proof, the read-out D21 hands the whole quota on.
  - Nothing on file decides which rows of a branch round form arm B. 04_passfirst_design §6.2 had stamped repair rows
    apart (`gen-repair`, with their own coin). D47 is silent, and ARMS_DESIGN does not name these rows.
  - It is not reachable yet. The VPS journal, read-only at 43,268 lines, has 0 rows with arm gen or composites and 0
    with gen_route, and /opt/wq/forge/runner.py does not import forge.gen. ARMS_DESIGN can therefore still be amended
    without a post-hoc choice, but only until the first gen row lands.
  - The gen section above makes the set of such rows larger. Its N2: a library row handed to propose gets neighbours
    stamped arm 'gen'. Its N4: a passing neighbour gets neighbours of its own.
- **D45 x D47 (SUSPECTED, all three auditors; the same item as the pipeline section's SUSPECTED): KEPT and routed.**
  - V3 setup: V deployed 10-01; the run_config alternates rc_comp and rc_gen every 2 h on 10-02..10-08; graded
    10-09 12:00 ET.
  - Result: live_days gives 7 days. Both cohorts read known True, with 0 counted days and 7 excluded days.
  - This happens only if D47 gives each arm its own argv. It does not arise if one runner flag sets the arm under a
    constant run_config.
  - Routed to the orchestrator and to Khoa with D53. It is not blocking: the D47 round assignment is not built, and
    a card triggers no automatic action.
- **Auditor 2's CI hand-off: RE-SCOPED.** The CI owner's files changed after auditor 2 ran (tools/ci_fixture.py 22:57,
  tools/tests/test_ci_gate.py 23:06).
  - The "4 -> 13" count cannot be re-derived: the current fixture reads B.WATCH_KEEPS_RUNNING, so bc318f2f now fails
    64.
  - The placeholder-sha item is already fixed (ci_fixture._formula_sha).
  - On my snapshot the current state is 15 failed, 106 passed. These failures trace to this change:
    - the 4 MUTANTS anchors (A4, D28, D30, D39);
    - `KeyError: 'credited'` in the truth table, which comes from D49's new shape.
  - Routed to the CI owner (D42). It is not a scoring defect.

### Dropped
- **Auditor 3's real-case framing of the watch rollback to ec6a5cd75d58fea2.** V4 reproduces the mechanism: the
  restored version reads exposure unknown. But live_days' own docstring already records that version's exposure as
  permanently unknown, so today's loss is nil. The mechanism is kept as M9.
- **The builder's backlog line "the judge exits 2 until wq-judge.sh passes --version".** It is stale: vps/wq-judge.sh
  already runs `--record --version "$c"` per cohort.

Signed for push: **no**. One SERIOUS (S1) survives.

BLOCKER/SERIOUS fixes still required (S1, all before the first gen row):
1. Add meta.gen_route to JOURNAL_KEEP_META.
2. compare_arms and render_arms count and print arm B's rows and events by gen_route.
3. D51 neighbour and D37 repair rows do not decide the verdict until Khoa ticks arm B's definition. Fail closed:
   either withhold the verdict, or keep those rows out of the strata and count them. The tick picks which.
4. A test that fails without the fix: V2's layout (equal fresh-draw rates, neighbours clearing at 0.29, 20 days) must
   not read "better".
5. Tick questions to Khoa, with auditor 3's three options:
   - B = fresh draws only (draw + floor);
   - B = every row, with the formula clustering named and the size simulation extended to cover it;
   - neighbours out, and repairs kept under D37's coin.
   The chosen reading goes into ARMS_DESIGN.

Preconditions for the push, not module defects:
- The orchestrator re-records the D42 golden.
- The CI owner re-anchors the 4 MUTANTS and the `credited` read.

### MINOR for backlog
Test gaps. For M1-M7, my mutant SURVIVED test_benchmark.py, while the no-op survives and the positive control is
killed.
- **M1: dora is unpinned beyond watch_rolled_back.** These survive:
  - C01: only watch_rolled_back counts as a failure;
  - C02: watch_not_rolled_back is dropped from WATCH_ROUND_FAILED;
  - C07: deploys/week counts watch rows, which is scoring 1's bug class.
  - Fix: pin V6's values.
- **M2: the WATCH_KEEPS_RUNNING test iterates the module's own tuple.** B03, which drops watch_not_rolled_back from the
  tuple, survives. Fix: loop over a literal, or over deploy.WATCH_OUTCOMES filtered to "watched".
- **M3: cohort_live_days counts a day on which a second host held the cohort for only part of it.**
  - A19 (part beats whole) survives.
  - The docstring's COUNTED and EXCLUDED bullets overlap.
  - The "dry run on another machine" rationale is false: runner.note_run_config records live starts only.
  - The real consequence is unstated: a stale host's last row keeps its cohort's days (pipeline M17). SUSPECTED
    reachability, through a hostname change.
- **M4: the "log rows after now are not seen" filter cannot be observed.** A09 survives. Fix: say the filter is
  redundant, or drop the test's claim that it checks it.
- **M5: formula_sha whitespace is unpinned.** E08 (strip) survives. Fix: pin that ' rank(x)' and 'rank(x)' hash
  differently.
- **M6: the reduced-rows equality test misses two fields.** F05 (drop truncation) and F07 (drop seed) survive.
- **M7: compare_arms paths are untested.** These survive:
  - I11: the status filter is dropped;
  - I12: the Mantel-Haenszel ratio is inverted;
  - I13: data_through is ignored.
- **M8: carried from auditor 2 and not re-run here.**
  - Boundary mutants: A01, A04, A12, A20, A23, A24, E01, E06, E07, F13, I16-I21, N01, N02.
  - The MDR tolerance is loose: J12 moves the increase MDR from 2.43 to 2.511, and J02, J04, J13 and J14 survive.

Behaviour, each failing closed or display-only:
- **M9: a version put back by watch_rolled_back reads exposure unknown when no "deployed" row names it (V4).**
- **M10: dora counts watch_not_rolled_back as a change failure but not watch_interrupted (V6: 0.333 against 0.0).**
  - deploy.py says watch_not_rolled_back covers every D43-reported post-dispatch error.
  - This is an unrecorded reading. It is display-only (A9).
  - Fix: record the reading in open_ticks, or narrow it. Name watch_interrupted, not `interrupted`, in the _is_watch
    and live_days docstrings.
- **M11: load_run_config_log, load_meaning and load_deploys glob their path.** V5, a file under a directory whose name
  holds `[1]`: is_file is True and 0 rows are read. This is the class read_journal fixed.
- **M12: an arm's rows with a marker run_config are dropped by `_arms_strata` without being counted** (code reading).
- **M13: compare_arms covers one pipeline_version.** Each deploy restarts the MIN_SHARED_DAYS clock now that D48
  dropped the freeze. This is unstated.
- **M14: MIN_SHARED_DAYS = 5 has no decision on file.** D47 names no minimum. Fix: record it under D47, or tick it.
- **M15: the ARMS comment omits `--ab`.** vps/forge.env ships `--ab new`, and runner.stamp uses setdefault, so rows
  read current/new and compare_arms returns no-data. This is the same item as pipeline M14. Fix: name it in the comment
  and in the no-data `why`.
- **M16: compare() still returns "better"/"worse" in its verdict.** Under no effect that label is wrong 0.49-0.56 of
  the time, and the caveat sits in a separate key. There is no automated caller. Fix: relabel the verdict, or record
  that D47 superseded F1 item 1 for compare().

Texts the code contradicts (each confirmed by reading):
- **M17:** the coverage-gap note says the rate counts the gap days, but `empty` is never intersected with the rate's
  days.
- **M18:** `graded_by_axis1_not_in_rate` says "not live", but it now also holds D45's excluded and unknown days.
- **M19:** D45's "unknown" days include days the log attributes to another run_config (auditor 1 defect 5, auditor 2
  P1).
- **M20:** the RUN_CONFIG_LOG comment says "no runner writes it yet", but forge/runner.py main() calls
  note_run_config.
- **M21:** compare()'s design string says the between-day dispersion contradicts "independent alphas". That picks one
  mechanism (RULE 0 #3). Fix: say it contradicts "one rate per arm across days".
- **M22:** COMPARE_IS_NOT_GATE3 attributes 0.49-0.56 to the bootstrap. Per round 3 F1 the bootstrap gives
  0.486-0.501, the gamma-Poisson model 0.540-0.547, and the closed form 0.561.
- **M23:** the POST_HORIZON open tick and the rank_key docstring understate D49: a late unproven POST can also flip
  floor_met and the verdict.
- **M24:** the `_day_heterogeneous` docstring's "4.1 events a day" and "1.62 per 1,000" are not what the code draws.
  It draws p0 = 4.1/2800 over 2,376 busy-cell alphas, about 3.5 events a day.
- **M25:** the size test is model-based: one Gamma draw per day is applied to both arms. It is not F1's real-data
  placebo. Fix: say so in its docstring, or add a round-relabel placebo.
- **M26:** a (pv, None) cohort keeps every live day of its pv. This is the module's reading, and it is not in
  open_ticks.
- **M27:** the MEANING_DECIDABLE comment reads G4 opposite to D52. The meaning adjudicator already routed it; it is
  listed here once for the owner.

SUSPECTED (auditor 3, code reading, not blocking): D51 neighbours simulated after a deploy or a forge.env change fall
outside the alpha's cohort pool. The alpha then reads UNMEASURED, and so UNPROVEN, at rank level 1.

## Draw-5 audit: release (2026-09-23)

Adjudicator, module `release`. Audited bytes (sha256 prefix; at 23:26 +07 each repo copy was still cmp-equal to the
snapshot): tools/deploy.py 7ff14dbc, tools/ci_publish.py d1de5f28, tools/tests/test_deploy.py 3465d11b,
tools/tests/test_ci_publish.py d75ec10b, vps/forge_loop.sh a0b3df46, vps/forge.env c514eed8, vps/wq-judge.sh 13017d1c,
vps/wq-judge.service 27b71125, vps/systemd_wq-forge.service 6a3af0bd. Read beside them: forge/offline/benchmark.py
b30d255c and tools/ci_gate.py 62d1c28c. All runs were on scratchpad/d5_release_adj. That snapshot holds tools/, forge/,
vps/, the repo-root *.py, harness/guards.py and the three harness13 files the plan ships. It has no state, fetched or
.git, and the large data dirs are out because the disk had 0.9-2.3 GB free. Runs used `python3 -B` with
PYTHONDONTWRITEBYTECODE=1. Mutants were applied on the copy, then restored and cmp'd. There was no sim, no --live or
--submit, no ssh, no commit and no code edit. The host figures below come from the auditors' read-only copies
(scratchpad/aud2r_loop.log, vps/forge_loop.sh), which I re-counted. I did not re-read them on the host.

### Baseline

- `pytest tools/tests/test_deploy.py tools/tests/test_ci_publish.py`: **223 passed, 1 failed**.
- The failure is test_ci_publish.py::test_serious2_the_known_test_failing_as_recorded_is_allowed_and_named. The CI
  module's ci_gate (edited 23:08) now blocks a tests result with no `incomplete` key. The fixture `_tests_result`
  writes none.
- Production is unaffected, because the real check_tests always sets `incomplete`.
- Adding `"incomplete": []` to the fixture, on the copy, gives 57/57. The copy was restored and cmp'd afterwards.
- While it stays red, the suite blocks ci_publish.
- The exec lens found the same failure.

### Verdicts on the three audits

1. **SERIOUS (confirmed; upgraded from the exec lens's MINOR, agreeing with the assume lens): the watch can roll back
   a push it is not watching.**
   - _watch_inner checks that the target runs the watched push only once, before it polls, which can be for up to
     WATCH_TIMEOUT_S = 60 min.
   - _judge decides "rollback" for an import-crash marker, or for a crash before dispatch, without reading any
     version.
   - _watch_rollback then calls other_operator_busy, snapshot_readable, stop_units and _undo. None of these re-reads
     remote_manifest().
   - Nothing locks a push against a running watch: `grep -i lock` finds none, and the watch writes its row only when
     it ends.
   - REPRODUCED on the pristine snapshot with the exec lens's scratch test
     (test_aud2r_a_push_that_lands_during_the_watch_is_not_undone_by_it). remote_manifest returns V1 and then V2. The
     result was watch rc 1, rolled_back True, and the manifest was read once.
   - The consequence (EX-ANTE, read from _push_inner and _undo): _undo extracts V1's snapshot and removes V1's
     added_paths.
     - The snapshot holds every plan path that existed before V1, plus DEPLOYED.json. The target therefore ends up
       with the code from before V1, plus V2's added paths. Library YAML among those paths is loaded by glob.
     - The manifest names the code from before V1, and start_units runs this tree. That is the state _undo itself
       calls unsafe ("starting the loop would spend real quota on it").
     - The watch row sorts before V2's push row (by started_at) and says running_after 'previous'.
   - Trigger: all three of these must happen.
     - An operator pushes a second time inside the window of a running watch.
     - That push's first round crashes before dispatch.
     - The watch is armed. On the host today it is not: the R1 probe refuses benchmark 6f22ebf0. After this release
       lands, it is.
   - Why SERIOUS and not N3's MINOR: the builder's guard text ("refusing -- a rollback now would undo something
     else") claims exactly this protection, and the action is destructive.
   - Fix (cheap): in _watch_rollback, re-read remote_manifest() before stop_units and again before _undo. If it no
     longer names push_row['version'], return _not_rolled_back('the target no longer runs the watched push') and
     restart `units`. Adopt the scratch test.
2. **Downgraded from the assume lens's SERIOUS to MINOR: `reported` makes a push a change failure in DORA.**
   - CONFIRMED by reading:
     - an auth-gate exit 5 (a requests exception in `s.get`) is reported;
     - so is a refresh_cells non-200 before a round;
     - so is submit's designed exit 3 (HOLD-FOR-APPROVAL, once 403s in 7 days exceed MAX_403_PER_WEEK = 1).
   - Each of these gives watch_not_rolled_back, and benchmark.WATCH_ROUND_FAILED puts that outcome in dora's `fails`.
   - Not SERIOUS: dora_checks is "for DISPLAY on a card (A9: never in axis 3's value)", and the card prints "DORA
     (reported, not scored)". The watch's own outcome follows D43 ("REPORTED").
   - What remains:
     - The row's `why` says "errors after dispatch" for items before a round, which D43 does not cover.
     - Whether a reported item counts as a change failure is for the scoring owner or Khoa. The same question is
       SUSPECTED in the spec and exec lenses.
3. Every other defect the three lenses raised is MINOR; see the backlog list below. I reproduced or read each one as
   marked there.
4. The builder's fixes: the exec lens reverted 57 of them, and each failed its named tests. I did not repeat that.
   - I re-checked by reading: R1 (probe before ctx['push']), R2, D43's _crashed_before_dispatch, S2 through S4, D44,
     D50, S9, the judge's stderr success rule, and R4's defects 4, 6, 8, 9 and 11.
   - The one exception is defect 5's test (backlog item 3).

### Signed for push: **no**

Required first:
- **(1) Release SERIOUS 1:** the watch re-reads the target's manifest before it stops anything and before _undo, with
  its test.
- **(2) Mechanical, not a severity:** the ci_publish fixture `_tests_result` carries `incomplete` (or whatever
  contract the CI owner settles on), so the release suite is green on the current tree.

Then re-run test_deploy.py and test_ci_publish.py on a fresh snapshot, and revert (1) to show that its test fails
without it.

### MINOR for backlog

1. **The forge.env parser and bash disagree on some bytes.** REPRODUCED:
   - A CRLF file: the parser reads (300, '--mode composites --ab new'), while bash reads N=$'300\r' and ARGS ending
     in 'new\r'.
   - A `\x0c` file: the parser reads (300, '--no-split'), while bash reads one N and an empty FORGE_ARGS.
   - `N=²`: ValueError escapes and push dies with a traceback before contacting the target, instead of printing the
     refusal banner.
   - Cause: str.splitlines() and str.isdigit().
   - Cheap fix: split on '\n', refuse control characters, and use re.fullmatch('[0-9]+').
2. **The watch can conclude before the background probe finishes, so the probe's exit is unseen.** RE-DERIVED on the
   host log copy (23:06) with my own awk state machine; it matches the exec lens's figures. Of 176 `probe (bg) done`
   lines:
   - 159 come before the round's `posted` line;
   - 3 come after it, in the same round;
   - 14 come after the next round's header.
   - That is 17/176 after the point where the new script prints `round end` (POST-HOC). The mechanism is EX-ANTE:
     the probe is a background job by construction.
   - Fix: record probe_exit 'unseen', or wait within the window.
3. **The test for release defect 5 cannot catch the ordering it is named for.** REPRODUCED:
   - I moved the forge.env read back after reconcile_target_ledger (mutant RV25b). The builder's test still passes.
   - The exec lens's scratch test seeds a FAILED pending row. It passes on pristine and fails on RV25b.
4. **The unit-file test contradicts the unit header, and the first D50 change breaks CI.** REPRODUCED:
   - The header says to keep the fallback equal to forge.env's FIRST values; the test pins it to the CURRENT file.
   - Flipping forge.env to `--mode singles` makes 2 d50 tests fail. The natural way to make them green (editing the
     fallback) invites round 3's S5.
   - Fix: pin literals.
5. **R1 residual (by reading; latent).** A watch_rolled_back row is appended by _record_watch after _undo has
   restored a benchmark that was never probed.
6. **Test gaps the exec lens measured with surviving mutants.** I did not re-run these; I only confirmed that its
   scratch tests pass on pristine (8 of 9; the ninth is SERIOUS 1).
   - The per-effect checks of the probe (M71 through M74);
   - the shape of the row _record_watch actually writes (M67);
   - M9, M35, M80, M39, M105 and M18;
   - the loop's step-exit numbers (M76a through M76d, and M77);
   - the `-B` guard, masked by PYTHONDONTWRITEBYTECODE (M86b);
   - M13, which hangs as an hour-long busy poll.
7. **Texts, by reading:**
   - the _push_inner docstring says "Nothing else changes before the swap", but quiesce touches STOP_FORGE and stops
     and restarts the units;
   - the _READERS_PROBE comment claims the interleaved [deploy, watch, deploy] case, and the probe checks no CFR;
   - the quota-sleep echo names 00:05 NY even on the 3600 s fallback;
   - install step 5 of systemd_wq-forge.service restarts the unit before `rm STOP_FORGE`;
   - the `--force` help says "a forge child", but --force also skips the check for the judge and test units;
   - D44 with the flag prints counts, not names (remove_library_extras).
8. **Smoke and loop coverage (by reading):**
   - the import smoke does not import mint_link, which the auth gate imports; only forge/search.py imports it;
   - no test runs `bash -n vps/forge_loop.sh`, so a syntax error reads as silence and gives watch_timeout;
   - a `--plan` in forge.env would leave every round inconclusive, because rows keep the base meta.seed (latent).
9. **Operator concurrency (by reading; the N3 class):**
   - wq-forge in its 60 s `activating` restart window is left out of was_active and stays down after a push
     (pre-existing _is_active);
   - the judge timer is not masked during the swap and smoke;
   - a ROUNDS=1 arm-driver round in the same loop.log that crashes before dispatch can trigger a rollback once the
     driver has exited.
10. **D43 cannot tell a data-caused planner crash from a code crash.** runner.plan json.loads
    state/forge/quarantine.json, which harvest rewrites with a non-atomic write_text. That is EX-ANTE; the frequency
    is unmeasured.
11. **wq-judge.service LIMITS.**
    - The 335 MB, 1,066 MB and 5.1 s figures were measured on benchmark 76c4dba8; the shipped file is b30d255c.
    - They are not reconciled with round 3's 741 MB.
    - The cohort count grows every day under TimeoutStartSec=1h. When that bites is SPECULATION.
12. **S4 is built as timeout_cause 'auth_dead' under watch_timeout, not as a distinct outcome.** The orchestrator
    should accept this or ask for the outcome name.

Process items, routed to the orchestrator:
- The judge grades every cohort, and no decision is on file (01_architecture §5 item 3 makes it Khoa's).
- D50's ROUNDS=1 exception is not recorded.
- docs/evalharness/backlog.md does not exist, so round 3's N1-N3, m1-m20 and X1-X5 (with m12, m13 and m15 on release)
  are recorded nowhere.
- Cross-module stale texts, for their owners:
  - the runner's _VERSION comment on a too-deep manifest;
  - benchmark's `interrupted` docstrings;
  - 01_architecture's remote_production_args (3 hits);
  - 04 §7 stages 0d and 5(a);
  - the D46 note's "06:24 +07".

## Draw-5 audit: ci (2026-09-23)

Adjudicator, module `ci`. Audited bytes (sha256 prefix; the repo copies were still equal to these at 00:13 +07 on
09-24): tools/ci_gate.py 62d1c28c, tools/ci_fixture.py e2feced0, tools/ci_golden_card.json d8a0cc0e,
tools/ci_known_red.json 8867dd79, tools/ci_classify.py 54c634c3, tools/tests/test_ci_gate.py ae1b8c66,
.github/workflows/ci.yml 4c7d603a. Read beside them: tools/tests/test_ci_publish.py d75ec10b, tools/ci_publish.py
d1de5f28, forge/offline/benchmark.py b30d255c and tools/deploy.py 7ff14dbc.
- All runs used scratchpad/d5_ci_adj. It is an rsync without state, fetched, .git, AI_Innovation_Atlas_data,
  cyberrisk or research, because the disk had 2.2 GB free.
- Five hard-linked workers (adjci/w0-w4) were used. Every mutated file was unlinked before it was written, so a
  mutation never wrote through the pristine copy's file. `__pycache__` was cleared, and each file was restored and
  cmp'd. At the end, `diff -rq` shows all five workers identical to the snapshot.
- Runs used `python3 -B` with PYTHONDONTWRITEBYTECODE=1.
- The probes are adjci/probes.py, probe2.py and mutants.py, with their outputs beside them.
- Nothing else ran: no sim, no --live or --submit, no ssh, no commit and no code edit.

### Baseline and identity
- `pytest tools/tests/test_ci_gate.py tools/tests/test_ci_publish.py`: **1 failed, 244 passed** (79 s). The failure is
  test_ci_publish.py::test_serious2_the_known_test_failing_as_recorded_is_allowed_and_named (P1 below).
- The golden, re-hashed with hashlib: fixture e2feced0 and scorer b30d255c match the files on disk; all 51 closure
  hashes match; 21 cases.
- check_no_live on the snapshot: ok. closure_unread is tools/ci_classify.py:110 and tools/watchdog.py:253.
- check_test_files: 90 files, 65 under TEST_DIRS, 0 run_outside, 25 listed.

### Verdicts on the SERIOUS items raised
1. **Exec and spec lenses: C3 turns tools/tests/test_ci_publish.py red. REPRODUCED, and RE-SCOPED to a push
   precondition (P1). It is not a ci code defect.**
   - Measured: reverting C3 properly (`if False:` plus `elif result.get("incomplete")`) makes all of
     test_ci_publish.py pass, while test_ci_gate.py's C3 test fails.
   - So the red test is caused by C3 alone. C3 is the fix the draw-4 ci adjudicator required. The line that lags is
     the release owner's `_tests_result` fixture, which carries no `incomplete` key.
   - The release section above already lists this as its required fix (2).
   - The builder's report did not name this cross-module consequence. That omission is a process note.
2. **Assume lens: check_no_live cannot see the loop script at its deployed path. UPHELD as SERIOUS.**
   - REPRODUCED on a worker (probe2.py). A forge/tests file holding `subprocess.run(['bash', '/opt/wq/forge_loop.sh'])`
     gave ok=True and scripts_read []. The same held with `ROOT / 'forge_loop.sh'`.
   - Control: the same call with `'vps/forge_loop.sh'` blocks at vps/forge_loop.sh:159 (`--live`) and :196
     (`--submit --cap 4`).
   - Cause, read from the code: _resolve_script strips DEPLOYED_ROOT and looks for `forge_loop.sh` at the repo root.
     deploy.PLAN maps `vps/forge_loop.sh` to `forge_loop.sh`, so no repository file answers. The token is dropped
     without being named.
   - The unchanged tree with a copy of the loop at the root (the host's layout) BLOCKS on forge_loop.sh:159 and :196,
     reached through forge/search.py. That file's _scripts_python_runs reads `forge_loop.sh` from run_recipe.
     Today's PASS therefore rests on the layout mismatch.
   - The texts claim the opposite:
     - DEPLOYED_ROOT's comment says "the same files as this repository's";
     - check_no_live says of loop scripts "the day a test runs one, it is read";
     - _scripts_python_runs says "if a test ever RUNS one, it is read, and it blocks".
   - C6 reported "an absolute /opt/wq/... path" as read, and this is the one script it misses.
   - Exposure, EX-ANTE by reading:
     - forge/tests runs on /opt/wq in deploy.SMOKE and in vps/wq-forge-tests.sh (daily).
     - deploy's quiesce stops the units and removes STOP_FORGE before the swap and smoke. forge_loop.sh's flock on
       /var/lock/wq_forge.lock is therefore free during the smoke.
     - The conftest POST guard patches requests only inside the pytest process.
     - So a test that ran the loop at its host path during a smoke would start real simulations and a real submit
       (RULE 1).
   - Latent: no test calls run_recipe or names the host path today.
   - Kept SERIOUS under the rule the release section applied: the guard text claims exactly this protection, and the
     action is irreversible. It is not the draw-4 ci 6 case (MINOR), where the unread forms were not claimed as read.

Dropped:
- The exec lens's broader "`seen` not propagated": my form, which drops `seen` from the recursive call, is KILLED by
  test_a_name_bound_to_an_expression_that_holds_it_is_read_not_recursed. Only the narrower form in item 5 survives.
- The golden never run on Linux / Python 3.13 (SUSPECTED): no mismatch has been observed. Watch the first Actions run.

### Signed for push: **no**

Required first:
- **C8 (SERIOUS 2 above).**
  - (a) _resolve_script maps host paths through the inverse of deploy.PLAN, both the DEPLOYED_ROOT-stripped form and
    a bare token. With a test: `/opt/wq/forge_loop.sh` and `ROOT / 'forge_loop.sh'` in a test file block.
  - (b) A .sh token found as a RUN that resolves to no file is named, not dropped.
  - (c) Correct DEPLOYED_ROOT's comment, the check_no_live sentences on loop scripts and forge/search.py, and
    _scripts_python_runs' sentence.
  - (d) After (a), the real tree blocks on forge/search.py run_recipe (measured above). How that call is treated goes
    to Khoa as tick questions (RULE 2). The options:
    - an exact-line NO_LIVE_EXEMPT entry with its reason;
    - run_recipe refusing under pytest, built by forge/search.py's owner;
    - it stays blocking.
    Until the tick, the gate fails closed.
- Show that each of (a) and (b) makes its test fail when reverted.

Push preconditions (not ci defects):
- **P1.** The release owner adds `"incomplete": []` to test_ci_publish.py `_tests_result` (release fix (2)).
- **P2.** tools/ci_data_bound.json is stale: tests_hash 93e1569adb1f2226 on file against b0a2c7b16f4b37df now. The
  hosted tier blocks as STALE until tools/ci_classify.py is re-run on the desk.
- **P3.** The orchestrator commits X1's two golden steps separately (--split-golden).

### MINOR for backlog (for docs/evalharness/backlog.md, which does not exist yet)

1. **Collection can still be narrowed, and C2's texts overclaim.** REPRODUCED with check_tests on probe trees. In
   each case the known red and a NEW failure were present:
   - a pytest.ini `norecursedirs = sub` gave rc 1, counted 1, incomplete [] and verdict ok=True;
   - a conftest `pytest_pycollect_makeitem` gave the same.
   - The controls block.
   - Texts that claim more than this: the PYTHON_FILES comment ("an ini file cannot narrow what is collected") and
     known_red_verdict's bullet ("no conftest the run loads can narrow collection").
   - NARROWING_NAMES omits pytest_pycollect_makeitem, pytest_collect_directory, pytest_make_collect_report and
     pytest_collection. Outcome-rewriting hooks go unnamed too (EX-ANTE).
   - Fix: pass `-c` pointing at an empty ini, or pytest's default `norecursedirs`. Add the hooks, or say the list is
     not exhaustive. Say "counted", not "ran".
2. **A duplicated node id launders a NEW test.** REPRODUCED. With a conftest modifyitems `items[:] = keep + keep`, the
   run gave counted 2, the known node twice, incomplete [] and ok=True. The control blocks. Fix: block on a repeated
   node id.
3. **`incomplete: None` reads as complete.** REPRODUCED: None gives ok=True, and an absent key gives False. Fix:
   require a list.
4. **collectable() reads True for files pytest collects nothing from.** REPRODUCED:
   - `__test__ = False`: rc 5, "no tests ran";
   - a Test class with `__init__`: rc 5, 1 warning.
   Both were classified run_outside.
5. **Test gaps: surviving mutants.** Each mutant below gave 244 passed across both files, and the only failure was the
   P1 test. REPRODUCED:
   - check_test_files removed from CHECKS;
   - its `blocking` set to False;
   - `-o python_classes` dropped;
   - _in_test_dirs as a bare prefix;
   - collectable counting a Test class with no test;
   - run_arm without `-o addopts=`;
   - run_arm without _collection_narrowers;
   - main reading only the DATA arm;
   - narrowers ignoring import bindings;
   - C4 `seen = frozenset({id(v)})`;
   - C4 taking the last binding instead of the first.
   Not re-run here (the exec lens's own_results.json and fx2_results.json): the S6 fail-closed branches, the
   sys-alias forms, and the pytest_collect_file and makemodule names.
6. **C6 regression: a backslash-newline template is no longer flagged.** REPRODUCED:
   `"%s \\\n  <flag> --cap 4"` reads False, and True under the pre-C6 separator. EX-ANTE: a non-raw Python literal
   drops `\<newline>` itself, so only `\\\n` or raw strings reach a shell. Fix: join continuations before splitting.
7. **Unread forms that WHAT THIS IS NOT does not name.** REPRODUCED:
   - a conditional rebinding before `+` reads only tools/a.sh, while `run(X)` reads both;
   - os.posix_spawn and pty.spawn read nothing (the spawnl control does read);
   - `getattr(sys, "path").insert` gave ok=True with closure_unread [], while the `sys.path.insert` control blocks.
     This contradicts the import_closure and check_no_live sentences saying such an entry is named.
8. **Readers that crash without naming a file.** Each fails closed. REPRODUCED:
   - a non-UTF-8 workflow: check_no_live raises UnicodeDecodeError;
   - _collection_narrowers raises RecursionError on a 200k-term `1+` chain and MemoryError on 50k unary minuses;
   - a ci_fixture.py that does not parse: both raise SyntaxError, and gate() prints no verdict.
9. **Slow paths that fail closed as hangs.** MEASURED; beyond the last value is extrapolation:
   - _argv_elements with k self-rebinds: 3 ms at k=6, 21 ms at 7, 183 ms at 8, about x9 per rebind;
   - _SH_AT_COMMAND on `sudo -u ... !`: 7 ms at 20 options, 16 at 22, 42 at 24.
   Fix: memoise; use an atomic group.
10. **S6 departs from round 3's Fix, with no tick.**
    - The Fix says "blocks when ... not listed with a reason". The code instead RUNS an unlisted collectable file.
    - All 25 legacy files are listed.
    - tools/funnel/test_gate_gap.py gave 6 passed with no data (0.01 s), yet its listing reason is "not run until the
      owner decides".
    - The `_SCRIPT` reason is never re-checked by collectable().
    - An explicit path is not dropped by `--ignore`: `pytest test_ig.py --ignore test_ig.py` gave "1 failed". So a
      run_outside file in ignore_files would run while not_run says it did not. Latent: run_outside is empty.
    - To Khoa as ticks: auto-run or block; the 22 scripts; test_gate_gap and test_fault_injection; test_pipeline.py.
11. **S7 partial (by reading record_golden).** Nothing names moved closure files that no case executes, and the reader
    paths are monkeypatched, not injectable.
12. **C7(d) partial.** Two DECISIONS_LITERAL entries are scorer readings, not ticks:
    - four_shared_days "withheld" comes from benchmark's MIN_SHARED_DAYS = 5, and D47 names no day minimum;
    - V@r2's known=True is "THIS MODULE'S READING of D45" (cohort_live_days).
    Move both to READINGS_LITERAL.
13. **Texts.**
    - check_branch_drill returns ok=True, printed [PASS], in the hermetic tier (m17). REPRODUCED.
    - ci_publish.data_tier cuts the test-files summary (148 chars) at 140, ending at "25 listed as run by", and prints
      no not_run. The NOT_RUN comment's "on every run" holds only for gate(). Route to release.
    - check_tests' "everything except the LLM files" also leaves out the 25 listed files.
    - The TEST_DIRS comment still names "SUITES".
    - _flag_lines' docstring describes the pre-C6 rule.
    - ci_fixture calls case_input_layer "the one case that reads files", but _tree copies ROOT/forge/hypotheses/*.yaml.
    - ci_fixture carries `route: "auto"`, which is outside meaning.ROUTES (routed by the meaning section).
    - "Decisions NOT reached" omits COMPARE_IS_NOT_GATE3 and two WATCH outcomes.
    - test_the_exemption_list_is_empty_and_the_real_tree_passes_without_it never runs check_no_live on the real tree.
14. **Open and fail-closed.**
    - m5: `20 journalled warnings` is keyed on a moving count (not re-derived here).
    - `--deselect` matches by prefix: `--deselect test_a.py::test_load` deselected 2. REPRODUCED; the count check
      blocks.
    - The teardown double count behind `<` (by reading).
    - ci_publish.ensure_checkout installs pytest unpinned (grep); route to release.
