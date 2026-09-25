# Frames loop build audit

One section per module, appended by its adjudicator. Append only.

## Loop build audit: validator

2026-09-25. Adjudicator for `framelib/schema.py` and `framelib/tests/test_schema.py`. I verified every defect myself on
a scratch copy of the framelib package: `$A` = `/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad/frames/loop/adj_validator/`.
Scripts: `probe.py`, `probe2.py`, `real.py`, `mut.py`. The repo was never written, apart from this appended section.
`cmp` confirms repo schema.py == `$A/schema.pristine.py` == scratch after every mutation.
Nothing was simulated or POSTed. The VPS was only read (ssh -n BatchMode): `/opt/wq/framelib` is absent, `wq-frames`
is inactive and there is no `frames_loop.jsonl`. So 0 production rows exist, and every defect below is latent today.

**Re-derived as claimed**
- test_schema.py: 54 passed, both in the repo and on the scratch copy.
- Real R1B/R2 ledger rebuilt with the current `framelib/loop/evidence.py` from the builder's copied journals: 2,280
  constructions and 200 rows (screen 2026-09-24 x100, replicate 2026-09-25 x100). All 100 real live blocks are valid on
  candidates, and 0 frames reuse a field across rows.
- `test_schema_store.py::test_validated_needs_rounds_a_verdict_and_the_operators_tick` fails (1 failed, 16 passed).
- Nothing outside schema.py writes `validated` or `approval`, and nothing reads them to gate a POST (grep). F9 is N/A.

### SERIOUS (validator-owned; required before any entry is marked validated)

**S1. A production day with 0 scored fills counts as one of the MIN_ROUNDS days** (schema.py:240).
- Reproduced end to end through `evidence.ledger_rows` and `live_block` (`probe.py` P1). Rows 09-27 (31 scored),
  09-28 (10 unposted) and 09-29 (10 cancelled) VALIDATE with Khoa's tick.
- These rows are reachable, EX-ANTE: `evidence.counts` makes a row for every planned construction, with the day taken
  from `meta.plan_day`.
- Fix: `days = {r["day"] for r in prod if r["n_scored"] > 0}`. On the scratch copy it refuses P1 ("has 1") and keeps
  54/54 passing. The pristine suite does not catch it, so add a test that fails without the fix.
- Whether a day needs more than 0 scored fills to count is a threshold for Khoa.

**S2. The docstring cites doc 13 §7.3 and Q5 A as if both were implemented, but the checks cover only part of them**
(schema.py:42-47 and 233-257).
- Q5 A says "MIN_ROUNDS = 3 **post-replication** days", and §7.3 items 3 and 4 say "replicated" and "rows after its
  replication day". Neither is checked, and these all VALIDATE (P3):
  - production rows only, with no screen or replicate row: `validated(novel())`, the builder's own good-path fixture;
  - production days that fall before the replicate day;
  - production days that fall on the replicate day.
- The original validator required reliability.verdict ROBUST (`../architect/schema.orig.py:190`). That requirement was
  removed, and nothing replaces item 3.
- Items 2, 5 and 6 are also not checked:
  - Item 2: 21_round2_result.md records R2's B1 as NOT MET.
  - Item 5: y08 4/30 against 0.1236 VALIDATES, with one-sided exact P = 0.517.
  - Item 6: daily y08 of 11/11, 0/11 and 0/11 VALIDATES (P4).
- Fix, part (a): require at least one replicate row, and count only production rows dated strictly after the frame's
  last replicate day. All 100 current frames have a replicate row on 2026-09-25 (real.py), so the rule can be met.
- Fix, part (b): rewrite the docstring to say that items 2, 3 (robust), 5 and 6 are NOT checked. Relabel the effect
  message, which says "(F7)" but checks a point estimate with no 1.5x bound.
- Put items 2, 5 and 6 to Khoa as tick questions. Q5 has no tick in 00_decisions.md, and F6 removed the same-day
  comparator that item 5 needs.

**S3. F10 pairs are double-counted as fresh fills** (schema.py:241, 245, 249).
- plan.py (modified 15:49:44, after schema.py at 15:32:24) routes both pair members to "production" with the same
  fill, so the builder's not_done reason ("no pair code in plan.py") is out of date.
- `probe.py` P2 runs through the real ledger writer: 15 distinct fills run as pairs over 3 days give n_scored 30 and
  VALIDATE. Reference-profile fills also go into the frame's y08 rate.
- `by_pair_member` is already in every live row, because `live_block` copies every key except frame_id.
- Fix: fresh fills = n_scored - `by_pair_member.reference.n_scored` (0 when absent), plus a test. Whether reference
  members count in the rate is a decision for Khoa or the orchestrator.

**S4. The validated thresholds are re-checked on every save, so a declining frame's library entry keeps stale evidence**
(schema.py:249-257 via store.save).
- `probe2.py` P12: a validated frame at 9/33 gets later rows of 0/20 and 0/30. `write_library` refuses the write
  (rate 0.1084), and the file on disk still shows 3 rows at 9/33 while the true pooled rate is 9/83.
- In effect this is a retirement rule nobody ticked (doc 13's rule: last 3 days, p <= 0.05, by Khoa's tick), and it
  hides the rows a retirement decision needs. The builder's note (3) disclosed the exit 3 but not the stale entry.
- Fix: apply the thresholds only to the evidence the tick approved (production rows dated on or before approval.at,
  with approval.at on or after the last counted day). Keep writing later rows, and report the decline.

### SERIOUS, cross-module (not validator files, but they conflict with its format; fix before Khoa's first tick)

**X1. framelib/build.py (lines 205-223) drops `evidence.live` on a rebuild** (`probe2.py` P11).
- A candidate that carries a live block is rebuilt without it and bumped to version 2.
- A validated entry gives the build error "validated needs a valid evidence.live block", and `build.main` returns 1.
- frames_loop.sh never runs build (grep), so only a manual rebuild reaches this.
- Owner: build.py. Carry `old["evidence"]["live"]` into the rebuilt entry and add a test.

**X2. No code applies Khoa's tick.**
- A correct tick edited in by hand makes INDEX.json stale (its status axis). `ST.load` then raises LibraryError
  (`probe2.py` P13).
- plan.py:514 calls `store.load()` with no guard, and frames_loop.sh:320 ends the round on that error. So the loop
  stops at the first tick, and it fails closed: no POST is made.
- Owner: the orchestrator and store. Needs one command that validates the tick, saves the entry and rewrites the index
  in one step.

### MINOR for backlog

- test_schema_store.py is still red: it asserts that the B3 defect (`[ROUND]*3` with no live block) is valid. Its
  owner should delete or rewrite that test.
- Canonical reliability rounds:
  - no effect > 0 check (12 B3 item 2): ROBUST with 3 rounds at effect -0.5 is VALID;
  - the rounds are not checked at all when the verdict is UNMEASURED (arm 'none' x3 is VALID);
  - the (round, date) key can be evaded (round 1, 1.0 or True; a date with a trailing space);
  - the test name `..._on_every_count` claims more than the test checks.
- Retiring a validated frame needs no tick, and the approval can be erased in the same edit (P6 VALID).
- The tick is not tied to anything else: approval.at may come before every row, and the history's 'validated' entry
  may be by 'claude' (P7).
- comparison.y08_rate is supplied by the entry itself: 0.0 is accepted, and so is 1 y08 in 33 (P4c).
- The fresh check has blind spots:
  - rows with `fields=[]`;
  - 'close', 'Close' and ' close' counted as three different fields;
  - rows with day 'unknown';
  - the R1-attempt-1 and R3S journals, which sit outside the ledger.
  The docstring names only two blind spots.
  POST-HOC, MECHANISM UNKNOWN: 18 of the 200 real rows have fewer distinct fields than n_scored.
- The predicates are narrow: arm 'n/a', 'null', '-' and 'none' followed by U+200B are accepted, and so is approval.ref ' '.
- Some malformed entries crash validate() with AttributeError: a string in status_history, evidence='live', and a
  string round under ROBUST. `write_library` catches only LibraryError.
- Test gaps: these mutants survive all 54 tests (`mut.py`): n_planned counted as fills, screen and replicate fills
  counted, `<=` at 30, MIN_FRESH_FILLS=28, no lower bound on the rate, and no YYYY-MM-DD regex. The current code
  itself refuses '20260927' as a day.
- test_schema.py line 90 goes red once any real entry is validated. The assertion on line 230 can never fail.
- F10, F11 and F13 have no schema names yet: settings.source parent/learned, an origin for submitted-alpha frames, and
  a universe check. These await Khoa. Audit M7 (early return) is also still open.
- Docstring line 6 (the version rule) is contradicted by evidence.write_library, which makes no bump, and by build,
  which bumps. The live `source.sha256` cannot be verified after the next ledger rewrite (evidence owner).

Dropped: no auditor defect failed to reproduce. The '20260927' second-day case is a test gap only, because the
current code refuses it.

Signed: no.

## Loop build audit: submit

2026-09-25. Adjudicator for `framelib/loop/submit.py` (md5 1107294b…, unchanged before and after this audit) and
`framelib/tests/test_loop_submit.py`. Every defect below was reproduced by me, in memory or on the fake transport; the
repo file was never written. Scratch: `$A` = `/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad/frames/loop/adj_submit/`.
- `test_adj.py`: 12 probes. Each one PASSES when its defect reproduces on the unmodified module, and all 12 pass.
- `test_killers.py`: 6 tests. All pass on the real module.
- `adjmut.py` + `mut/`: mutants loaded in memory. Canary check: the identity mutant gives 25 passed, and the "dry run
  POSTs" mutant is killed.

Nothing was simulated or POSTed. The VPS was only read (ssh -n BatchMode). It has no `framelib/loop`, no
`forge/meaning.py`, no `vps/frames_loop.sh` and no `fetched/rc/fields/USA_TOP2000_d1.jsonl`, and its
`forge/submit.py` has 0 matches for `meaning_gate|SUBMIT_LOCK`. So the builder's not_done #1 (deploy precondition)
holds, and nothing below has affected a POST yet.

**Re-derived as claimed**
- Repo tests: 25 passed.
- F9's named rules are wired as described: D39 through the real `forge.submit.meaning_gate`, D18 fail-closed with
  registration inside the run, the fresh re-read under the row's own lines, the shared ledger with reservation before
  the POST, and the 403 count. F3 holds too: only `FRAMES-LOOP` rows with a frame_id are candidates.
- POST-HOC, read on the VPS (last row per alpha): 0 D24 rows in R1B (1,083 scored), R2 (650) and R3S (300 so far).

### SERIOUS (required before the first `--submit`)

**S1. C14 and C15 (part of forge's `stage == candidate`) are not applied, and the docstring's "RULES NOT APPLIED" list
does not name them.**
- `test_adj.py::test_d1` POSTs both of these rows:
  - turnover 0.45, which forge's `turnover_verdict` reads as `decay-retry`;
  - a `LOW_2Y_SHARPE` FAIL, which forge's `platform_verdict` reads as `fail`.
- POST-HOC, VPS: turnover > 0.25 on 277 of 1,083 R1B rows, 212 of 650 R2 rows and 30 of 300 R3S rows. It is 0 on D24
  rows today, because there are none.
- Fix: hold unless `platform_verdict(row)[0] == 'pass'` and `turnover_verdict(row) == 'ok'`, or put both to Khoa as
  ticks before deploy. Add a test.

**S2. DSR >= 0.95 and PBO (C13, Q21) are waived by default.**
- The docstring says "none decided here", but the code POSTs without them.
- F9 ("every other submit rule stays") does not settle this.
- Fix: a tick question to Khoa before the first `--submit`, and the docstring must state the current default.

**S3. Several gates are read before the flock and never re-read inside it.** These are the one-POST-ever set, D18,
Q20 and the 403 count. Inside the flock only the budget is read.
- `test_d3`: another invocation POSTs A between our history read and our lock, and we POST A a second time. The
  ledger ends with [A, A].
- `test_d3b`: a twin POSTed in that window passes D18. The control, with the same twin on file before the run, is held.
- The docstring's "no other submitter can POST" is also false for `tools/auto_submit.py`, `submit_alphas.py`,
  `complete_submit.py` and `gentle_submit.py`, which POST without the flock (grep).
- Fix: re-read `posted_history` inside the flock, rebuild the index, the day count and the 403 count, and re-filter
  the queue. Narrow the docstring claim to submitters that take the flock. Keep `test_d3` and `test_d3b`.

**S4. A ledger-only budget is treated as authoritative.** This is inherited from forge, and it contradicts the
module's own "fails CLOSED" claim.
- `test_d4`: the real `tools/submit_budget.py` with the submissions feed answering 429 gives `authoritative False`,
  0/4 used, and the module POSTs.
- This is the failure mode behind the 2026-07-30 incident (le391QLA, Vk35LRM0), recorded in submit_budget's docstring.
- Fix: retry the feed, honouring Retry-After, then hold unless `authoritative` is True. Otherwise, Khoa's tick.

**S5. The 403 budget cannot see refusals that arrive on the submit poll.** This is inherited from forge.
- `climb_submit.post` never polls `GET /alphas/{id}/submit`.
- `recent_403` counts only `http == 403` on the POST itself. `test_d5`: three 201 POSTs later adjudicated REJECTED,
  and the next alpha POSTs.
- EX-ANTE, from `tools/submit_alphas.py:596-626`: the POST answers 201 with Retry-After, and the verdict (403 plus its
  checks) comes on the poll. The local forge log agrees: 4 of 4 POSTs are 201 with an empty body.
- `vps/frames_loop.sh` does not run `record_adjudication` (grep), so a frame POST's verdict is never recorded.
- Fix: poll after a 201, or run `record_adjudication`, and count REJECTED toward C29. Whether an async refusal counts
  toward C29 is Khoa's tick.

**S6. RULE 0: the S11 paragraph of the docstring states an unsupported claim.** It says "a POST made by an earlier
invocation is covered by the fresh platform reading alone".
- `test_d6`: a PnL twin held in run k is POSTed in run k+1.
- The only measurement on file contradicts the claim: docs/evalharness/04 §3.6 found 6 of 8 SELF readings low 2–2.5
  minutes after a POST (MECHANISM: UNKNOWN). At the distance of one round it is UNMEASURED.
- Fix: reword the claim as UNMEASURED. Running S11 against recent POSTs across invocations is Khoa's call.

**S7. Six behaviours the builder claims have no test that fails without them.** Each of these mutants survives all
25 repo tests, and each is killed by one test in `test_killers.py`:
- `posted_at = 0` in the record, which switches off cross-run Q20 and the 403 count;
- a 200 answer stops the run;
- the flock is released before the POST;
- a reading exactly AT the line POSTs (`<=`);
- `CLIMB_LOG` is dropped from the history;
- the first row per alpha is used instead of the last.

Fix: add the six tests.

### MINOR for backlog
- **Unknown-outcome POSTs.** A POST with http None is outside the next run's D18 index and Q20 count (`test_d7`: its
  twin POSTs). This is inherited, and a policy question already named in novelty.py. Likewise, a 429 or 408 answer
  retires the alpha for good.
- **Alpha ids are reused.** POST-HOC, VPS: of 13 (formula, settings) pairs simulated more than once, 9 returned the
  same alpha id. So a loop fill that repeats an R-round construction would make that experiment alpha a candidate
  without the tick F3 requires. Across the frames journals today there are 0 cross-experiment ids.
- **The D18 index holds only the logged POSTs** (5 on the VPS), not the 245 ACTIVE alphas. This is inherited, and
  `fetched/rc/active_book.json` is absent on the Mac. Tick: should frame D18 cover the whole book?
- **F13 universes.** A universe with no catalogue snapshot is held for good (it fails closed). The VPS has no
  USA_TOP2000_d1, so fetching it is a precondition for F13.
- **Docstring gaps.** A dry run appends the binding meaning row, and the docstring does not say so (`test_d11`). The
  gate-3 note "reads G7 false below" is wrong: such a row is never scored (`test_d12`).
- **No RULE 1 host guard.** `LS.session()` loads the Mac's `state/wq_cookies.pkl`, which exists (2026-08-14).
- **S11 order.** S11 fetches curves before D18 drops a twin (`test_d15`: a GET for B's curve), and `SCP.pnl` is not
  paced.
- **The CLI exits 0 on every refusal** (`test_d16`).
- **A non-object journal line crashes main** (`test_d17`). It fails closed.
- **Loose test attribution.** The reservation-order test does not check order (the mutant passes it, and only the
  unwritable-ledger test kills it). The unsorted dataset-set mutant survives under PYTHONHASHSEED 0, 4 and 6 (3 of
  8 seeds).
- **Untested branches.** Mutants of these survive: cached curve before GET (a claimed behaviour), the malformed
  catalogue line, the None-delay guard, and `''` for a formula with only GROUP fields.

Dropped: none. Every auditor defect reproduced. The builder's 666 of 1,430 meaning-all-true figure was not
re-derived.

Signed: no.

## Loop build audit: evidence

2026-09-25. Adjudicator for `framelib/loop/evidence.py` and `framelib/tests/test_loop_evidence.py`. I re-ran every
defect myself on a scratch copy of framelib, `$E` = `/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad/frames/loop/adj_evidence/`
(scripts `wit1_unposted.py` .. `wit7_rewrite.py`, `mut.py`, `real1.py`, `gen_scale.py`, `measure.py`). The repo was not
written apart from this section: after the mutants `cmp` gives restored == repo, and no file under framelib/library or
state/frames changed. Nothing was simulated or POSTed. The VPS was only read (ssh -n BatchMode): the six R1B / R2 /
recovered / attempt-1 files I used are md5-identical to `/opt/wq/state/layered/runs`; `/opt/wq/framelib` is absent and
`wq-frames` is inactive, so every defect below is latent today.

**Re-derived as claimed**
- test_loop_evidence.py: 19 passed, in the repo and on the scratch copy.
- Real data (`real1.py`). Ledger, screen (R1B a+b): 630 planned / 555 scored / 7 ERROR / 68 CANCELLED / 47 y08 / 6 LS.
  Replicate (R2 a+b): 1,070 / 650 / 13 / 107 / 30 other / 270 missing / 180 unposted / 66 y08 / 14 LS. 0 D24.
  Second way, my own raw parser (last row per key, arms a/b): R1B 555 / 47 / 6 / 68 / 7; R2 650 / 66 / 14 / 107 / 13,
  plus 20 FAIL and 10 POLL-DEADLINE (= 30 other). Both agree with the per-arm sums of docs 20 and 21.
- R2 unposted = 180 two ways: the ledger, and the plan's formula multiset minus the 890 formulas named by 89 parents.
- `--update` twice on the real copies: exit 0 both times, identical md5 over state/frames and the library; 100 entries
  written, then 100 unchanged; 0 invalid; every status still candidate.

### SERIOUS (evidence / interface; required before the loop runs)

**E1. n_planned counts never-sent constructions; plan.stages reads it as "already dispatched"** (evidence.py 52-57,
236, 277; plan.py 168-195).
- `wit1_unposted.py`, through the real planner: a frame whose 8 screen constructions got no parent and no row has
  ledger planned 8, unposted 8. stages gives it screen due 0 on 09-26 and replicate 8 on 09-27, with 0 scored.
- Reachable: R2 left 180 of 1,070 unsent. POST-HOC, real R2: 5 of the 85 frames with >= 8 planned replicate rows had
  fewer than 8 sent.
- The naive fix is not enough. With n_planned - n_unposted the all-unsent frame goes to `waiting`: it has a ledger
  row, so it is not unseen, and its planned count of 0 means it is not begun either (witnessed in the same script).
- Fix: publish n_sent (or have plan subtract n_unposted), AND make plan treat a frame with 0 sent as not yet screened.
  Test through the real stages: an all-unsent screen frame keeps screen due 8 the same day and is not replicated the
  next day. Owners: evidence and plan together.

**E2. A truncated dispatcher plan is archived, then every later `--update` fails** (evidence.py 187-189, 427-440;
writer dispatch_round.py:81, a plain write_text).
- `wit2_truncplan.py`: exit 1 (JSONDecodeError). The live plan is then rewritten whole and parses; the next update
  exits 1 again, because the archive keeps the truncated copy. The error names no file.
- frames_loop.sh 297-302 ends every round at step 3 and backs off 900 s. The loop stops (fail-closed, no spend) until
  someone deletes the archived file by hand. The driver's own comment (29-31) names this hazard for the planner's file
  only. How often a kill or a full disk hits that write: UNKNOWN.
- Fix: archive only bytes that parse to a dict with a constructions list; in _source skip unreadable plans and report
  them (plans_unreadable). Tests with a truncated live plan and a truncated archived plan.

### SERIOUS, cross-module (not this module's files)

- **X1. plan.stages replicates a new frame only if it was screened exactly yesterday** (plan.py 185, 195-196).
  `wit1_unposted.py`: with no round on 09-27, both frames are in `waiting` on 09-28 and nothing ever moves them out.
  Owner: plan.py.
- **X2. Confirms the validator's X1:** `framelib.build` drops evidence.live and bumps the version (`wit4_build.py`:
  live rows 1, version 1 -> no live block, version 2). The loop never runs build.

### MINOR for backlog

- The F6 note goes on every day. The real daily row for 2026-09-24 lists FRAMES-R1B/d (320 planned: the same-day
  incumbent arm) next to "no control arm runs on these days".
- Recovered rows WITH settings match without round_seed (line 227). `wit3b.py`: one alpha is credited to two rounds of
  two frames (n_scored and y08 +1 each). Latent: all 16,468 real recovered rows have settings None.
- The docstring differs from the code (`wit3_misc.py`):
  - (a) a dry-run plan holding a posted parent's formula makes that parent unassigned, and the posted round then
    vanished from the ledger entirely (ledger []);
  - (b) AUTH-FAIL and MULTISIM-CHILD-ABSENT stay n_other, while POLL-DEADLINE yields to the same recovered row;
  - (c) the modal day counts unscored rows (witness: 09-24 from two ERROR rows, against the scored row's 09-25).
    0 real unscored rows carry dateCreated.
- test_loop_evidence.py:18 picks NOVEL from the real library with evidence None. After `--update` with the default
  library, the module errors at collection (IndexError). Reproduced on scratch, then restored.
- Test gaps: 11 mutants survive all 19 tests (`mut.py`; the control mutant is killed). So claim 11's "fails_without"
  is false for R2 and arm b. The survivors:
  - R2 -> screen; R2 not read; arm b dropped;
  - a parent of any round (claim 3); several rounds -> pick one (claim 7);
  - daily POSTs not filtered by day; accepted = 201 only;
  - a non-JSON line raises; CLI read mode writes; hits[0]; comparison text without DESCRIPTIVE.
- Malformed input crashes the build, so evidence exits 1 and the round ends (`wit5_hostile.py`): posted_at NaN (346),
  a reservation whose alpha is an int (369), plan settings None, and journal settings as a list (analyse_round.py:25).
  A string meta.fill is split into characters (fields c, e, l, o, s). None of these shapes exists in the real copies.
- A frame that leaves the ledger keeps a stale evidence.live, whose sha no longer matches the ledger (`wit6_stale.py`).
- A missing or renamed loop journal reads as empty: exit 0, 0 ledger rows, used_fields empty, so the planner would
  reuse fields (`wit6_stale.py`). No code rotates the journal today (grep).
- Every round rewrites every library entry that has rows, because the ledger sha is in each one, and it does so
  through store.save's non-atomic write_text. `wit7_rewrite.py`: a round touching only a frame outside the library
  rewrote 2 entries.
- Memory, POST-HOC (Mac, a synthetic journal built from real R2 rows): 18k rows 139 MB, 72k rows 479 MB, build 2.0 s;
  about 6 KB a row. SPECULATION (linear; 5,000 rows a day; VPS `free -m` shows 6,183 MB available): about 6 months to
  an OOM.
- main prints every archived plan path each round into loop.log (code read, lines 498-500).
- RULE 0 labels: the counts in docstring lines 59-61 are neither labelled nor dated (they are true: 0 of 42 and 0 of 51
  repeated formulas span two frames in R1B and R2). `_slim`'s "a month of full rows would not fit" was not measured.
- F7: no module computes the y08 ratio against 0.1236 with its 1.5x lower bound. This is outside this module and goes
  to the orchestrator.

Dropped:
- Auditor 1's "stale plan.py comment". plan.py:76 now names by_pair_member as a DESIGN CHOICE. Whether reference
  members count in the posterior is Khoa's F10 question, not an evidence defect.
- Auditor 3's concurrent `--update` race. Not reproduced; the loop holds a flock.
- "accepted = POST 2xx" and the deploy-identity conflict. Both are SPECULATION with nothing to reproduce, and
  `/opt/wq/framelib` is absent.

Signed: no.

## Loop build audit: planner

2026-09-25. Adjudicator for `framelib/loop/plan.py`, `availability.py`, `__init__.py` and
`framelib/tests/test_loop_plan.py`. I re-ran every defect myself on a scratch overlay of framelib,
`$P` = `/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad/frames/loop/adj_planner/`
(scripts `probe1.py` synthetic, `probe2.py` journals, `probe3.py` real-input plans, `mut.py`). The repo was not written
apart from this section: the four files `cmp` equal to `$P/orig/` at the end, and state/frames/unit_blacklist.json keeps
mtime 15:40:57. Nothing was simulated or POSTed. The VPS was only read (ssh -n BatchMode; scp of frames_r3s/r3sb and the
two POST logs into `$P/in/`). frames_r1/r1b/r2 md5 equal the VPS copies. `/opt/wq/framelib` is absent and `wq-frames` is
inactive, so every defect below is latent today.

**Re-derived as claimed**
- test_loop_plan.py: 28 passed, in the repo and on the overlay. A control mutant (no blacklist filter) is killed.
- Real-input plans at seeds 1, 2, 3 (day 09-26, the 293 datasets, the R1B/R2 ledger): 300 rows each, 30 parents. The
  D18 index over the VPS logs reads "complete: 5 accepted POST structure(s)".

### SERIOUS (required before the loop runs)

**P1. A new frame that gets 0 replicate rows on day t+1 waits for ever** (plan.py 185, 195-196, 443-444).
- The block cut. m frames screened yesterday, full supply, 4 rounds (`probe1.py` P2). m = 1, 6 and 11 leave 1 frame with
  0 rows in every round; m = 2 leaves none. That frame is in `waiting` on 09-26 and still on 10-25. For m = 6 the rows
  per round were [40, 0, 0, 0]: the frame's 8 rows are fewer than 10, so every later round cuts them to 0.
- A missed day (auth down all day): the frame is in `waiting` on 09-26 and still on 12-31 (probe1 P3).
- Short own-role supply makes remainders common. POST-HOC, R2: 15 of 100 frames had fewer than 8 fresh fills.
- Nothing reports it except the `waiting` count. The evidence adjudicator's X1 names the same code.
- Fix: keep a screened, unreplicated frame on the replicate route until it has a replicate row, or let the cut drop
  rows of frames that already have rows today. Test: 6 frames screened yesterday, two rounds, none waiting.

**P2. Unsent rows count as done** (plan.py 170, 183-190; evidence n_planned includes n_unposted). This is the
evidence adjudicator's E1, reproduced here through stages (probe1 P4).
- A ledger row with 8 planned, 8 unposted and 0 scored gives screen due 0 the same day, then replicate 8 the next day.
- R2 left 180 of 1,070 constructions unsent. The daily limit cuts every day's last round the same way.
- Fix: joint with evidence (E1).

**P3. GROUP-type catalogue fields are planned into signal slots, and the unit blacklist does not stop them.** POST-HOC
(`probe2.py`, `probe3.py`):
- Every row whose fill held a catalogue-type GROUP field was an ERROR: 69 of 69 (R1B 11, R2 13, R3S 45). One invalid
  child cancels its parent of 10.
- A blacklist learned from R1+R1B blocks 0 of R2's 13 unit errors. One learned from R1..R2 blocks 1 of R3S's 45.
- Real-input plans hold such rows: 5 at the builder's seed 20260926, then 3, 0 and 0 at my seeds 1 to 3, and 0 at the
  exec auditor's 777. The 3 rows at seed 1 touch 2 of 30 parents.
- 00_decisions.md (16:18) records the R3SB rule "GROUP fields never fill a slot" (submitted_round.py:36-44). AV.prune
  does not apply it. Why the platform refuses a Group unit: MECHANISM: UNKNOWN.
- Fix: apply that rule in availability.prune, with a test. It is a new mechanism, so its RULE 2 status goes to Khoa.

**P4. Retiring a mutation's parent switches the child to the reference profile** (plan.py 312, 402-405). probe1 P1:
- parent candidate: child rows use 'parent F09c… designer', SUBINDUSTRY/8;
- parent retired: 20 of 20 child rows use 'reference: no profile', INDUSTRY/4.
- Fix: resolve profiles over all entries, retired ones included, and add a test.

**P5. F8's gate is missing: a new frame joins production after replication whatever it scored** (plan.py 195-196).
- probe1 P5: 0 y08 in 8 screen and 8 replicate rows, and the frame is in production.
- F8 cites doc 13 Q7 A. Doc 13 §7.2 says "Frames robust within their cohort join the L library". §7.3 retires frames
  that were not screened or not replicated.
- No loop module computes the §7.1 line or the robust test (grep).
- Fix: implement §7.1 as the gate between replicate and production, or put the choice to Khoa as a tick.

**P6. Some claimed `fails_without` are false** (`mut.py`, each run restored and cmp-checked). These mutants survive, with
28 passed each time:
- `blacklist=frozenset()` passed to build in main;
- the blacklist loaded before it is refreshed;
- the decay range removed;
- the truncation range removed.
At seed 3 the test's blacklisted input is never drawn, so its "absent" assertion is vacuous. Fix: a seed that draws
it, assert unit_blacklisted > 0, and cases for decay 600 / -1 and truncation 1.5 / -0.1.

**P7. Deploy preconditions not named** (they fail closed: no round, no spend).
- plan.py imports `forge.gen.spend`. forge/gen is untracked locally and absent on /opt/wq, and spend imports
  forge.gen.families and forge.gen.posterior.
- `state/frames/history_usa_d1_top3000.jsonl` is written by nothing (grep). Its only source is round1.CANONICAL, a
  104 MB file in this session's /private/tmp scratchpad. The driver passes no --history.
- Fix: name both as deploy steps, and keep a copy of the history outside /tmp.

### MINOR for backlog
- JOURNALS is a fixed list of four, so frames_r3s and frames_r3sb are not read. With them the learned blacklist has 92
  pairs, 42 ambiguous and 70 new. Whether to glob, and whether ambiguous rows should blacklist anything, is Khoa's call.
- A direct field is blamed "unique" when a sub-expression sits at the same operator and index (probe1 P7: `fa`
  in add(rank(fa),rank(ts_mean(grp_b,5)))). The docstring says such rows are unattributed.
- `--unit-blacklist` does not follow `--state`. A CLI run with a scratch --state wrote `<ROOT>/state/frames/
  unit_blacklist.json` from the scratch journal, and that file never drops an entry.
- Crashes instead of falling back or skipping: decay NaN or inf, a list neutralization (probe1 P6), and a non-string journal
  formula (probe1 P8: AttributeError).
- --n below 10 plans nothing. A screen or replicate remainder under 10 rows is cut in every round (probe1 P10).
- An "unknown variable" in an offered dataset is never learned. There are 4 ERROR rows: R1B 2 and R3S 2, all model165
  (offered, 441 fields). A field blacklist would be a new mechanism and needs a tick.
- On ET 2026-09-25 the real ledger puts all 100 library frames on replicate (60 rows due) and none in production. Do
  not start the loop before 11:00 +07 on 09-26, or send only new-origin frames to replicate.
- The D18 status says "complete" over 5 logged POSTs; the account holds 245 ACTIVE. Same tick as submit's.
- Untested, mutants survive: pairs following the posterior, P_OWN, the TY.GROUPS filter, the journal names.
- Text:
  - PER_FRAME 8 is credited to F8, which states no count; doc 13 §4 says 6, and R2 used 8.
  - "measured to finish" for MAX_ROWS: CHUNK was set as "a forge round's size", and R2 #2 stalled.
  - __init__ omits the datasets and probe steps (vps/frames_loop.sh 22-35).
  - "fresh" follows round2 and drops round1's `_unseen >= 1`: label it a DESIGN CHOICE.
  - No ingredient or fresh_family meta is recorded.
- Open RULE 2 / decision items, none ticked:
  - Thompson with its 20 % floor, PAIR_SHARE 0.25, REFERENCE, P_OWN 0.5, PER_FRAME 8, MAX_ROWS 300, pairs first, and
    the unit blacklist;
  - F10's "learned over rounds" and D51 one setting away (not landed, disclosed);
  - F11-F13 (not landed, disclosed).

Dropped:
- Auditor 1's SUSPECTED crash in blocked() on an unparsable fill. Not reproduced: blocked() ran on every candidate of 3
  real 300-row plans with a 22-pair blacklist, with 0 exceptions.
- F7 PARTIAL is not planner-owned.

Signed: no.

## Loop build audit: driver

2026-09-25. Adjudicator for `vps/frames_loop.sh`, `vps/wq-frames.service` and `framelib/tests/test_loop_driver.py`.
I re-ran every defect I keep on scratch copies, `$J` = `/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad/frames/loop/adjudicator_driver/`
(`run.py` = one pytest process over a node list with `FRAMES_LOOP_SH`/`FRAMES_UNIT` pointed at a copy; mutants
`m_probe_lock.sh`, `m_dups.sh`, `m_combined.sh`, `m_chicago.sh`, `u_*.service`; `fix_scored.sh` = auditor 3's candidate
fix), and replayed auditors 2 and 3's scratch tests (`auditor2_driver/test_hostile.py`, `auditor3_driver/test_a3_driver.py`).
The repo was not written apart from this section: the sha256 of the three files is unchanged, and no `__pycache__`
appeared. Nothing was simulated or POSTed. On the VPS (ssh -n BatchMode) I only listed, hashed and grepped files. I
also ran `timeout`/`gnutimeout` over a shell or python that signals itself; that wrote no file.

**Re-derived as claimed**
- test_loop_driver.py: 50 passed (25 in 41.3 s + 25 in 30.5 s).
- The shared-interface arguments (lines 297-351) match framelib/loop/__init__.py.
- The builder's 75 mutants all being KILLED is auditor 2's result; I did not re-run it.
- Host tools the loop parses with: pgrep procps-ng 4.0.4, GNU sed 4.9, GNU grep 3.12. uutils `seq 1 100000`, `tr`
  and the `posted N` sed parse give what the loop expects.

### SERIOUS (driver-owned; required before install)

**D1. On the host, `timeout` does not report a signal as 128+N** (lines 297, 306, 319, 345; the rig's FAKE_TIMEOUT).
- Measured, read-only, 2026-09-25 16:3x +07: `/usr/bin/timeout` is uutils coreutils 0.8.0. It returns TERM 15,
  INT 2, HUP 1 and python SIGQUIT 3; KILL gives 137.
- The rig's fake timeout returns 128+N, and every signal test uses SIGKILL, the one case where the two agree.
- Replayed against the real script with the host's codes (test_hostile.py::test_H8, 4 passed):
  - evidence + SIGQUIT -> "evidence exit 3: the ledger was written ... the round goes on", then dispatch, in both
    rounds;
  - newframes + SIGTERM -> "failed (exit 15): the round goes on";
  - probe + SIGTERM -> submit runs with no signal marker;
  - plan + SIGTERM ends the round, but labelled "failed".
- The OOM path (SIGKILL, 137) is correct. How often a catchable signal reaches a child: UNKNOWN.
- Fix: run steps under GNU timeout. `/usr/bin/gnutimeout` (GNU coreutils 9.7) exists on the host and returns 143 for
  TERM and 131 for python SIGQUIT (measured). Fail closed if it is absent. Give the rig a host-code fake, and add
  SIGTERM cases plus a SIGQUIT-on-evidence case, each failing without the fix.

**D2. A round whose POSTs were all refused gets no back-off** (line 368).
- dispatch_round.main returns 0 always (read). layered_sim journals one POST-<code> row per child, with meta. That
  happens on a 5xx or a 400, and on a 401/403 the dispatch stops. evidence.used_fields_map counts meta.fill of
  every row, "any status" (evidence.py:465).
- Reproduced (test_a3_driver.py, 4 passed): for 503, 401 and 400 alike, 3 rounds gave 3 dispatches, 0 sleeps and
  summaries of "30 row(s), 0 scored". The real used_fields returns all 5 POST-503 fills.
- So during an outage, or with a cookie the platform refuses before its exp, each round (about a minute) marks up to
  300 fills used.
- Frequency UNKNOWN (host logs: 0 "POST 5xx" lines; 2 "session is not usable" lines in forge/loop.log).
- Fix: back off when this round scored 0 rows (auditor 3's one line, `fix_scored.sh`). It keeps the builder's
  50/50 and flips the 3 refusal probes (3 failed, i.e. the loop now sleeps). Add a test that fails without it.

### SERIOUS (need Khoa's tick first: RULE 2 gate 5)

**D3. The auth gate relaxes a ticked rule** (lines 159-173, 271).
- wait_for_auth accepts more than 900 s left, read only from the JWT exp in the local cookie jar
  (search.py:103-108; mint_link.py:195-223). It never GETs /users/self.
- forge_loop.sh's gate (Khoa 2026-09-07 14:10, after 96 AUTH-FAIL rows and 15 orphans) is /users/self == 200 AND
  at least 2400 s left.
- The gate also runs before datasets, evidence, newframes and plan (up to 3 x 1800 s), not just before dispatch.
- A 300-row dispatch spans 8.8-25.6 min (plan.py:61-63, POST-HOC). The builder disclosed the threshold; I confirm
  it and add the missing liveness call and the placement.
- Tick question: keep 900 s, or apply forge_loop's rule immediately before dispatch.

**D4. F2 does not reach the new incumbent** (line 265; frames_round.sh:27-41, repo and host).
- frames_round.sh stops only wq-forge. The loop checks pgrep once per round, before an auth wait of up to 1800 s
  and the pre-dispatch steps, so a driver started after that check runs beside a dispatching round.
- POST-HOC: at 16:34 +07 today FRAMES-R3SB was dispatching on the host (frames_round.sh pid 3540290, seed
  20260929). Header precondition 0a checks only FRAMES-R2, and F11 schedules R3S's replication for the next day.
- Tick question: either frames_round.sh pauses wq-frames at a round boundary (STOP_FRAMES, wait, stop, and restart
  in its trap only if it was active), or experiment drivers take /var/lock/wq_forge.lock. In both cases widen 0a.

### SERIOUS, cross-module (not the driver's files; before install)

- **X1. tools/deploy.py does not know the frames loop.**
  - `tools/tests/test_deploy.py::test_every_script_a_vps_unit_runs_is_shipped_by_the_plan` FAILS now: 1 failed,
    with the single gap "wq-frames.service runs frames_loop.sh, which the plan does not ship".
  - Shipping frames_loop.sh alone would not clear it: the test's regex then reads
    `ROOT/framelib/experiments/vps/dispatch_round.py` and `frames_round.sh` from the script (measured).
  - The quiesce touches only STOP_FORGE, stops only UNITS = (wq-forge, wq-harvest), and waits on
    `forge/[a-z0-9_/]+\.py`, which the loop matches only while its probe runs. So a push can swap forge/ and tools/
    under a running frames round.
  - Owner: deploy, with a tick. Either ship vps/frames_loop.sh and framelib/ and quiesce wq-frames/STOP_FRAMES, or
    exempt the unit in UNITS_NOT_SHIPPED and refuse a push while wq-frames is active.
- **X2. The attended install cannot produce a working loop.**
  - Read-only, 2026-09-25 16:34 +07, the host has none of these: /opt/wq/framelib, forge/gen/spend.py,
    forge/meaning.py, state/frames/canonical.
  - The host's forge/submit.py (md5 6e3218d…) has 0 matches for meaning_gate or SUBMIT_LOCK. The Mac's (019f403…)
    has 3.
  - state/frames/history_usa_d1_top3000.jsonl and state/frames/canonical/frames_summary.jsonl exist neither on the
    host nor in the repo. plan.py:505-506 raises SystemExit without the first, and newframes requires both.
  - Header steps 1-2 ship only framelib/ and the script, and check imports only.
  - Doc 21's "measured next, before the loop runs" (R2's no-score loss) is not a precondition.
  - Every other loop module in this file is "Signed: no". Yet round 1 runs `submit --submit`, and header step 5
    says only "spends quota".
  - Fix:
    - Ship forge/ and tools/ first.
    - Ship both canonical inputs.
    - Add a no-spend host check (`plan --n 10 --out /tmp/p.json`, `newframes --dry-run`, submit without
      `--submit`).
    - Add doc 21's measurement and every module's sign-off to precondition 0.
    - Say in step 5 that round 1 may POST.

### MINOR for backlog

- **Orphans.** A correction to both the builder and auditor 1:
  - The host harvester (tools/recover_harvest.py, sha256 4e05040d… = repo) does glob every journal, frames ones
    included.
  - POST-HOC, it harvested rows in 25 of 18,004 logged cycles. The last cycles read "parents held 0 | gone 5478 |
    ROWS HARVESTED 0", and recovered.jsonl was last written 2026-08-18 17:37. Why every parent is "gone":
    MECHANISM UNKNOWN.
  - R2 had 1 ROUND DEADLINE with 9 parents in flight. Probe and submit never read recovered rows.
  - A decision for Khoa: recover, or write those simulations off.
- **B1 vs F11.** Doc 13 says new cohorts stop after B1 fails at R2 "unless Khoa ticks otherwise". Doc 21 (last
  written 15:25:40) reports B1 NOT MET. F11 (~15:50) says the loop "returns to 25 new frames a day". Whether F11 was
  meant to override: UNKNOWN. One tick question.
- **Test gaps**, reproduced here (whole suite 50/50 on each mutant unless noted):
  - the probe lock removed;
  - the dataset duplicate-id check removed;
  - one combined mutant: datasets written in place, empty-id check off, no 429 retry, daily-limit slice starting at
    the round header, quota sleep computed from $SEED;
  - America/Chicago in et_day passes the 4 ET-day tests (only those were run) at 05:42 EDT;
  - `_unit_keys` ignores [Section], so MemoryMax moved into [Unit] passes both unit tests, and so does
    KillMode=process plus OOMPolicy=continue.
- **Replayed, hypothetical triggers:**
  - One journal row with a non-string alpha id disables the probe for every alpha. The summary then reads
    "D24 1; probe exit none (0 D24 id(s))" (H1).
  - A loop run by hand and SIGTERMed during a back-off leaves its orphaned `sleep` holding the lock, and a second
    loop exits (H4). Fix: `sleep "$1" 9>&-`.
  - A datasets_ok.json lost after today's stamp is not fetched again that ET day (H6).
- **Read, not run:**
  - c11_run.sh:31, pow_run.sh:27 and llm_formula_run.sh:41 run `systemctl start wq-forge` in their EXIT trap
    unconditionally.
  - The loop drops forge_loop.sh's record_adjudication.py (line 155) and refresh_cells.py (lines 160, 220) steps
    unnamed.
  - `rsync -a framelib/` after the first install overwrites the host's INDEX.json. store.problems then reports it
    stale and plan fails closed every round (store.py:94-108).
  - newframes exits 0 on a short day (newframes.py:607), so the stamp ends that day's retries.
  - Dispatch and submit have no outer timeout.
- **Text:**
  - line 18: auth writes no step marker;
  - lines 21/41: "live" means only the cookie's exp;
  - line 58: ROUNDS=1 can still wait 1800 s inside wait_for_auth;
  - unit line 3 says it names no other unit, but After= names network-online.target, without Wants=;
  - UNDO's `disable --now` stops mid-round;
  - the OOM story ignores 2 GB of swap and no MemorySwapMax (EX-ANTE).
- **Growth.** loop_plans/, loop.log and the whole-journal read each round are not pruned. Size: SPECULATION.
- **Already recorded, cross-referenced here:**
  - a truncated dispatcher plan stalls evidence = evidence E2 (and lines 29-31 claim a wider protection than they
    give);
  - never-sent fills counted as used = evidence E1 and auditor 3's quota-sizing point.

Dropped:
- Auditor 2's H5 (dict "constructions" dispatched). The real script refuses it; their expectation was wrong.
- Auditor 3's "no dry mode" as a separate item; it is folded into X2's no-spend check.

Signed: no.

## Loop build audit: newframes

2026-09-25. Adjudicator for `framelib/loop/newframes.py`, `framelib/tests/test_loop_newframes.py` and
`framelib/loop/dropped_mined/`. I re-ran every defect myself on a scratch overlay,
`$N` = `/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad/frames/loop/adj_newframes/`
(scripts `run.py`, `mainrun.py`, `outside.py`, `supply.py`, `libsupply.py`, `rerun.py`, `groupmoves.py`, `wedge.py`,
`partial.py`, `hostile.py`, `mut.py`; my own FieldLibrary and history pickles, built from the scratch
canonical/rows_framed.jsonl, 18,934 keys). The repo was not written apart from this section: newframes.py sha256
ff3e76d2…, the test 35d10cc0… and filler.py are unchanged, and no .pyc was written. Every mutant was restored and
`cmp`-checked. Nothing was simulated or POSTed. The VPS was only read (one `ssh -n -o BatchMode=yes` of `ls`).

**Re-derived as claimed**
- test_loop_newframes.py: 34 passed, in the repo and on the overlay. A control mutant (no corpus check) is killed.
- The dropped list: selection.json sha256 33048f78… equals the curator's. 34/34 frames `cmp` equal curator/lib134. None
  is in framelib/library.
- Real-input dry run (seed 20260925, R1B's 293 datasets): 19 mined-dropped plus 6 mutations (window 2; group, opswap,
  condition and combine 1 each). 40 checks, 13.5 s. The 15 other dropped frames are refused for fewer than 3 disjoint fills.

### BLOCKER

**N1. The mutation branch has no Khoa tick (RULE 2), and its alphas reach F9's automatic POST.**
- The source order is set by F8 → doc 13 Q7 A → §7.2 (13_preregistration.md:352): the 34 dropped mined frames, then
  designer frames (after S8 is fixed), then frames mined from the incumbent's recent y08 rows.
- No entry F1-F13 names mutation. `grep -i mutat docs/frames` finds only statistical permutation tests.
- Day 2, reproduced: a run on the library filed on day 1 (seed 20260926, `r_d2.json`) gave 25 of 25 mutations, one
  per kind in turn, from 164 checks. The same 15 dropped frames were refused again.
- framelib/loop/submit.py `candidates()` takes every FRAMES-LOOP row with a frame_id at D24. It never reads origin
  (grep: 0 hits for origin/provenance).
- Fix: ship with the mutation half off by default (e.g. `MUTATIONS = ()` or a flag), with a test. Then put tick
  questions to Khoa: each of the five kinds on or off; the parent rule (any non-retired frame, evidence unused);
  §7.2's sources 2-3; off.
- Facts for the ticks, re-derived here:
  - all 34 dropped frames, and both of day 1's window children, share a shape with a library frame (`frames.shape`);
  - opswap turns SCORE01 into ZSCORE under an existing if_else and keeps its else 0.5, e.g.
    `if_else(less(rank(mdl177…),0.5),group_rank(ts_zscore(…),industry),0.5)`. Effect UNKNOWN.
- With the half off, newframes files 0 frames a day from day 2 on. How F8's 25 a day is then filled is Khoa's decision.

### SERIOUS (required before the loop runs)

**N2. An empty or wrong-form history fails OPEN** (newframes.py:636-643 check only that the file exists).
- `main` with a 0-byte `--history`, or with frames_summary.jsonl as the history, returns 0. It files 25 dropped frames
  instead of 19, with 0 rejections.
- Checked against the real history: 165 of 165 of those fills' slot-fields lie outside the frames' historic slot datasets.
  The real run has 0 of 57 outside.
- n=40 written: the opswap child Ffdc4a1101ddc of mined F3aa9bc7acdd6 is filed with constraints [None]×5. With the real
  history it gets `{"datasets": …}` per slot. This is persistent library state, so fixing the file later does not undo it.
- Fix: exit 2 when any dropped entry or non-retired mined parent lacks a per-slot history (a dataset set for every slot).
  Today 77 of 77 mined entries have one, so real inputs pass. Add a test with an empty file. plan.py has the same
  existence-only check (planner owner).

**N3. The code ship wedges the loop once a cohort is on the host.**
- newframes writes into `store.LIBRARY` = framelib/library, inside the tree that wq-frames.service step 1 ships with
  `rsync -a framelib/`.
- Reproduced (`wedge.py`): rsync the repo library over a library that holds a 25-frame cohort. The result is 125 files
  and INDEX.json with 100 entries, so store.load raises "stale".
  - newframes then exits 2;
  - plan.main's unguarded `store.load()` raises, so every round ends before dispatch until someone rebuilds the index;
  - the same rsync also reverts the evidence.live blocks that evidence.py:410 writes on the host.
- Fix: keep the library in host state (e.g. state/frames/library, default for newframes, plan and evidence), or exclude
  framelib/library from the ship after one seed. Add a test that a code ship leaves store.load valid.

**N4. Host preconditions are missing and not named.** Read-only ssh, 16:4x: /opt/wq holds none of the following.
- `state/frames/history_usa_d1_top3000.jsonl` and `state/frames/canonical/frames_summary.jsonl` are absent;
- `forge/meaning.py` is absent. It is untracked in git (`?? forge/meaning.py`), and newframes.py:101 imports it for
  `_COMPARE`;
- `/opt/wq/framelib` is absent.
- Install step 1 ships only framelib/ and frames_loop.sh, so step 2's import check would fail. That is fail-safe: no
  quota is spent, but F8 is not landed on the host.
- Fix: add all three, with their sha256, to step 0/1. Or pin `_COMPARE` locally with a test that it equals
  forge.meaning's.
- Cross-module, not repeated here: planner P5 (every replicated frame joins production, and §7.2's "robust within the
  cohort" is not applied) and planner P7 (forge/gen).

### MINOR for backlog
- Same-day re-run: `used` starts empty, so "a re-run continues the same sequence" is false.
  - Reproduced on the real library: n=21 then n=25 files a different set from a single n=25;
  - F1796d81631e5 and Fa241acdc0590 each gave 2 frames that day.
  - Fix: seed `used` from provenance.parents of today's cohort.
- Tracebacks exit 1 instead of the documented 2 (the driver retries, and nothing is written):
  - `{"dropped_mined": null}` raises TypeError;
  - `--day 25/09/2026` raises ValueError, because the seed is computed outside the try;
  - `_rungs(0)` raises ZeroDivisionError. No input today has a zero window.
- Group mutation rewrites any group token, including `country`: 6 candidates on F041679f42cfe and F8e6f66619180. The
  n=40 real run filed Ff758f997d277. The builder claims "GICS only", and no test covers it. Khoa or the builder decides.
- Docstring (lines 72-73): "a slot-free condition does not change which fields a slot admits" is false.
  compat.pool (147-156) removes cond_fields and pinned fields from every slot's pool.
- The commit is not atomic, and main's message is wrong: ENOSPC on the 3rd save (`partial.py`) gives exit 2 with
  "nothing written", 2 frame files on disk, and a stale INDEX, the same wedge as N3. Write through tmp + os.replace and
  report what was written.
- A missing `--library` directory loads as 0 entries (store.load), so newframes exits 0 and starts a new library.
- frames_loop.sh:306 passes no `--day`, so a round that crosses 00:00 ET stamps one day and files the next.
- MIN_FILLS 3 is below what the planner needs: at least 9 fresh own-role fills for any replicate row, and at least 11
  for ≥ 3 on both days.
  - Latent on today's inputs. The planner's own-role supply (`supply.py`, `libsupply.py`, no used fields, cap 17) is 17
    for 65 of 65 cohort frames (day 1 n=25 and n=40, day 2).
  - For the 100 library frames it is either 2 (21 frames) or 17 (79 frames); none fall in 3..8.
- The 15 unfillable dropped frames are re-checked and refused every day (reproduced on day 2). Record them as exhausted.
- Test gaps. These survive the 34 tests: filler's `structurally_ok` gate plus dead_reasons disabled (the H3 case dies in
  compat.pool first), `WINDOW_STEP = 1.0001`, the preset slot clause removed, and MUTATIONS reordered.
- A mutation's settings come from `parents[0]` through plan.profile; for a combine that is the lower id. This is
  undocumented. F10 follow-up for Khoa; the retired-parent fallback is planner P4.
- Owner evidence.py: 5 of the 19 filed dropped frames were R1B arm-c controls. There are 19 rows over 15 frames, all
  with `meta.frame_id` "nonlib:…". used_fields(F-id) cannot see those fields.
- RULE 1 incident during this audit: auditor 3's ssh created 6 files, `/dev/shm/audit_USA_*_d1.ids` (~16 MB, 16:13).
  They are still there (read-only ls). I did not remove them, because that is a write. The owner runs
  `rm -f /dev/shm/audit_USA_*_d1.ids`.

Dropped:
- Auditor 1's MIN_FILLS item as SERIOUS: 0 reach measured (above), so it is kept as MINOR.
- Auditor 1's "admission skips blacklist/D18/used_fields" and auditor 2's SUSPECTED unit-blacklist gap. No failure
  reproduced: the planner finds 17 fresh fills for every cohort frame, and auditor 2 measured 0 of 195 fills blocked.
- Auditor 3's SUSPECTED submitted-frame novelty gap: 0 hits in the first generation, not reproduced.

Signed: no.
