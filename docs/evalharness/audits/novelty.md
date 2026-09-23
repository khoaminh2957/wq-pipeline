# Audit — `forge/novelty.py` and its submit-path wiring (D18)

Adjudicated 2026-09-22. Module written 2026-09-22. Three auditors (spec / exec / assume) reported
independently; this file is the single list of what must change. Every defect below was re-verified
here before it was kept — the command or the line is named. Defects that did not reproduce are in
§4 with the measurement that killed them.

**Scope.** `forge/novelty.py`, `forge/tests/test_novelty.py`, the `novelty` parameter and two hold
reasons in `forge/submit.py:eligible()`, `main()`'s index build, and the four tests appended to
`forge/tests/test_submit.py`. `fingerprint.py` is Khoa's and out of scope for modification; where a
defect is inherited from it, the fix is stated on the `forge/` side.
**Specification:** `docs/evalharness/00_agreements.md` D18 + the `fingerprint.py` paragraph.
**Constraint that sets the severity bar:** a submission is irreversible, a 403 permanently spends an
alpha, there are 4 slots per quota day, and the desk's whole history is 4 accepted POSTs.

**RULE 0 note.** Nothing below explains *why* field-family overlap tracks PnL correlation. The
thresholds are POST-HOC regularities from `fingerprint.py`'s own 2,664-alpha pool. **MECHANISM:
UNKNOWN.** No experiment in this audit distinguishes the candidates. The rule is a screen.

**RULE 1 note.** Every VPS interaction was `ssh -n` running `ls`, `find`, `grep`, `sed`, `cat` and
read-only `python3 -c` / `python -B -c`. Nothing was written to the VPS, no simulation was run
anywhere, `--submit` and `--live` were never passed. The one local execution was
`python3 forge/submit.py` with no `--submit`, which returns before `LS.session()` (line 273) and
makes no network call.

---

## 1. Verdict

**Not safe to keep in the submit path as it stands.** Three blockers, and they point in opposite
directions: on the VPS the module posts nothing, ever, silently; on the MacBook it declares itself
complete over half the real submissions; and once the first two are fixed, the third lets one
invocation spend two irreversible slots on one structure.

The module is **not deployed** (`ls /opt/wq/forge/novelty.py` → No such file; the deployed
`forge/submit.py` contains no `novelty` reference), so nothing is live-broken today. These are
deploy-time blockers.

---

## 2. Surviving defects

### BLOCKER 1 — the submitter cannot even import on the VPS, and the loop swallows the traceback
**Where:** `forge/novelty.py:32` (`import fingerprint as FP`, module level) reached from
`forge/submit.py:253` (`from forge import novelty as NV`), which sits **above** the dry-run return
at `forge/submit.py:266`.
**Found by:** assume only. spec and exec both missed it.

**Evidence.**
```
ssh -n root@160.25.88.163 'ls -la /opt/wq/fingerprint.py /opt/wq/operators.py'
  → No such file or directory (both)
ssh -n … 'find /opt/wq -name "operators.py" -o -name "fingerprint.py"'
  → (empty)
ssh -n … 'ls /opt/wq/venv/lib/python3.14/site-packages/ | grep -iE "^(fingerprint|operators)"'
  → (empty)  — no site-packages module shadows the names either
ssh -n … 'cd /opt/wq && venv/bin/python -B -c "<submit.py's own sys.path, then import>"'
  → IMPORT FAIL: ModuleNotFoundError No module named 'fingerprint'
  → operators FAIL: ModuleNotFoundError No module named 'operators'
```
`/opt/wq` is a hand-curated subset — 13 top-level `.py` files, no deploy script anywhere in
`vps/` or `tools/`; CLAUDE.md:57 documents the habit as "`scp`/`rsync` to `/opt/wq`". Shipping
`forge/` alone, which is the habit, leaves the import unresolvable.
`vps/forge_loop.sh:88` is `SUBOUT=$($PY forge/submit.py --submit --cap 4 2>&1 9>&-)` — command
substitution into a variable, exit code never tested, and the only thing read out of it is
`grep -q "^HTTP 20"`. A traceback becomes one unread block in `loop.log`; the loop sleeps and
continues spending sim quota with no submit path.

**Fix.** Ship `fingerprint.py` **and** `operators.py` to `/opt/wq` in the same step, and add an
import-time assertion in `forge/novelty.py` that names both files when it fails, so the failure is
a message and not a traceback. `grep '^import\|^from' operators.py` → stdlib only (`re`, `ast`), so
the dependency closure is exactly those two files. Vendoring them into `forge/` is the alternative;
the module docstring's "deliberately not vendored" is a choice that, against the actual deploy
footprint, breaks the only POST path.

---

### BLOCKER 2 — on the VPS the index is permanently incomplete, so every candidate is held forever
**Where:** `forge/submit.py:250,254-255` (`rows = HV.forge_rows()`; `accepted` from
`posted_history()` which reads **both** submit logs) with `forge/novelty.py:65-81` and
`forge/harvest.py:69-75`.
**Found by:** all three.

**Evidence.** The accepted POSTs (`http in (200,201)`) across the two logs `posted_history()`
reads, from a read-only dump of `/opt/wq/state/{forge,climb}/submitted.jsonl`:

| alpha | log | http | formula on the row | POSTed (UTC) |
|---|---|---|---|---|
| mL516W9W | climb | 201 | 543 chars | 2026-08-14 |
| vRk095rv | forge | 201 | 273 chars | 2026-09-04 |
| kqVbg1xP | forge | 201 | 213 chars | 2026-09-06 |
| vRk1J2jd | forge | 201 | 177 chars | 2026-09-11 |

`HV.forge_rows()` keeps a journal row only when `r["alpha"] and (r["meta"] or {}).get("forge")`
(`forge/harvest.py:69-75`). Replicating that filter over `/opt/wq/state/layered/runs/forge.jsonl`
(35,115 lines → 31,084 rows): `kqVbg1xP True, vRk095rv True, vRk1J2jd True, mL516W9W **False**`.
Second, independent derivation — per-file `grep -c` over `/opt/wq/state/layered/runs/*.jsonl`:
`mL516W9W` appears in `climb.jsonl`, `climb_rescored.jsonl`, `recovered.jsonl`; **not** in
`forge.jsonl`. It is a climb POST; no future event puts a climb alpha into the forge journal.

End-to-end reproduction with the real VPS inputs and one perfectly novel, fully-passing candidate
(scratchpad `adj/t3.py`):
```
len(index)=3 complete=False missing=['mL516W9W']
banner: forge submit: novelty index over 3 submitted structure(s); FORMULA MISSING for ['mL516W9W'] -- holding the round
eligible=[] held={'novelty-index-incomplete': 1}
```
`elig == []` → `choose()` returns None → `posted 0`, every round, indefinitely. The only signal is
one print line inside a log the loop does not read.

**The module docstring asserts the opposite** (`forge/novelty.py:21-22`): "On the VPS, where the
loop actually runs against the complete journal, the incomplete branch is expected never to fire."
Measured, it fires on every candidate, forever.

**Fix.** Do not look the formula up in the forge journal. Every accepted row in **both** submit logs
already carries its own formula — verified above, and both writers persist it
(`forge/submit.py:233`, `tools/climb_submit.py:226`). Carry `formula` through `posted_history()`
(it currently reads the row and discards the field, `forge/submit.py:57-58`) and have `build()` take
it from the history row, falling back to the journal only when the log row has none. Delete the
docstring sentence.

**Cross-check available and not used (found in this adjudication, missed by all three):** the
formula is in the repo a *second* time. `fetched/rc/active_book.json` on the VPS (248 rows, each
with `regular.code`) contains `mL516W9W` with a 543-character code whose length and prefix match the
climb-log formula exactly. That file is already the source for the *pre-simulation* novelty gate
(`forge/runner.py:58-66` → `forge.signature.NoveltyIndex.from_book`). It is stale (dated
2026-09-04, so it holds none of the three later submissions) and is therefore not a drop-in fix —
but it is the existing "what the platform says is in the book" mechanism, and the new module named
neither it nor the gate that uses it.

---

### BLOCKER 3 — two structural twins can both be POSTed inside one invocation
**Where:** `forge/submit.py:294-342`. The index is built once at 255, before the loop, and
`novelty` is never referenced again after line 200.
**Found by:** all three (all rated SERIOUS). Raised here to BLOCKER: the harm is precisely what D18
forbids, it is irreversible, and it becomes reachable the moment blockers 1 and 2 are fixed — so it
must ship in the same change, or a submitter that posts nothing becomes one that can spend two of
four daily slots on one structure.

**Evidence.** Replaying only the loop's filtering statements — 298 (alpha id), 316 (mechanism_key),
338-339 (dataset diversity) — with no network call (scratchpad `adj/t4.py`):
```
sim(A,B) = 1.0000  near_dup=True
index complete: True len 1
eligible: [('A', 0.3234, 'S'), ('B', 0.3234, 'S')] held {}
would POST, in order: ['A', 'B']
```
A and B differ only by horizon, window and group; their `mechanism_key` and dataset sets differ, so
316 does not fire and `diversity_ok` explicitly permits a second POST (`forge/submit.py:118-123`).
Nothing recomputes novelty.

The identical bug class was already found and fixed one rule over, and is pinned by a test —
`forge/tests/test_submit.py`, "inside ONE invocation the counter advances with each accepted POST
… (before this rule lived only in eligible(), read once per invocation)". The lesson was not
applied here.

**Fix.** After an accepted POST, register the posted formula into the live index and re-filter
`elig`, in the same place and the same shape as line 339:
```python
if http in (200, 201):
    ...
    nov.index.register(pick["row"]["formula"], pick["alpha"])
    elig = [e for e in elig if not nov.verdict(e["row"].get("formula") or "")[0]]
```

---

### SERIOUS 1 — "already submitted" is two local files, not the platform: the fail-open twin
**Where:** `forge/submit.py:254`, `forge/novelty.py:36-48,65-81`.
**Found by:** spec (assume covers the same fact as a docstring defect).

An alpha submitted but absent from those two files is not `missing` — it is **invisible**, so the
index reports itself COMPLETE while a whole submitted structural family is unregistered and its
variants pass the gate as novel.

**Evidence.** The real local dry run, `python3 forge/submit.py` (no `--submit`):
```
forge submit: novelty index over 2 submitted structure(s)
forge submit: 21 candidate(s) scored, 0 eligible; held {'already-posted': 2, 'pbo-pending': 1, 'corr-over-line': 18}
```
No "FORMULA MISSING" warning: `complete` is True over **2 of the 4** real submissions.
`state/climb/submitted.jsonl` does not exist on this machine (`ls` → No such file) and
`HV.read_jsonl` globs a missing path to `[]` (`forge/harvest.py:30-39`), so `mL516W9W` is invisible;
`vRk1J2jd` is not in the local forge submit log either (`grep -rn vRk1J2jd state/` → nothing).

**Fix.** Make the authoritative submitted set the platform's own roster — `fetched/rc/active_book.json`
refreshed, or the submit-status endpoint, or a checked-in roster — and treat any id in it without a
readable formula as `missing`. Union the local logs into that set rather than letting them define it.

---

### SERIOUS 2 — a POST whose outcome is UNKNOWN registers no structure
**Where:** `forge/submit.py:254` (`accepted` = `http in (200, 201)`).
**Found by:** exec and assume. They disagree about 403; settled below.

**Evidence.** `tools/climb_submit.py:203-218` states the doctrine in its own docstring: "A RAISE IS
NOT A NON-EVENT. The request may have reached the platform and been adjudicated before the timeout
fired, so an exception says 'outcome unknown', never 'did not happen'. The caller must record it and
retire the lineage exactly as for a refusal." `post()` returns `None` on a raise;
`forge/submit.py:326-327` then calls `record(pick, None, body)`, writing a row with an alpha, a
formula, and `http: None`. `accepted` skips it: `[{X,None},{Y,403},{Z,200},{W,201}] → ['Z','W']`
(scratchpad `adj/t5.py` section B). The individual alpha is still blocked by the already-posted check
at `forge/submit.py:157`, but its structural family stays open.

**On 403 — exec and assume contradict each other, and the code makes no explicit decision.** D18's
wording is "cấu trúc các alpha … **đã được nộp**". A 403 was refused: it is not in the book, so it
is not a submitted structure — exec's reading. assume's concern is different and also real: the
`MAX_403_PER_WEEK = 1` budget (`forge/submit.py:35,270`) means a second 403 freezes submissions for a
week, so re-attempting a refused family carries its own cost. **Both readings are defensible and
neither is established by any experiment here.** What is a defect regardless of the choice is that
`forge/novelty.py:36` documents the class as "Every structural family that has already been POSTed"
while the code registers only *accepted* POSTs. **This one needs Khoa's tick, not an auditor's
preference.**

**Fix.** Register `http is None` rows (the pipeline treats them as spent everywhere else). State the
403 rule explicitly in the code and the docstring, whichever way Khoa ticks.

**Note on today's data, so this is not mis-read:** the `http: None` rows now in
`state/forge/submitted.jsonl` are **not** failed POSTs — they are `kind: adjudication` rows with
`status: ACTIVE`, written by `tools/record_adjudication.py`. Both kinds of `http: None` row land in
the same file. The failure above is latent, not currently firing.

---

### SERIOUS 3 — a candidate with no formula fails OPEN, contradicting "WHY IT FAILS CLOSED"
**Where:** `forge/novelty.py:59-60` (`if not formula: return False, 0.0, None`) called from
`forge/submit.py:197` (`novelty.verdict(row.get("formula") or "")`).
**Found by:** all three.

The module holds an entire round when a *submitted* alpha's formula is unreadable, and declares a
*candidate* with the same missing datum novel.

**Evidence** (scratchpad `adj/t5.py` section A): a candidate row with `formula: None`, against a
complete index over one real submission →
```
eligible: [('A', 0.0, None)] held {}
verdict('') -> (False, 0.0, None)   verdict(None) -> (False, 0.0, None)
```
The row reaches `out` with `structural_sim` 0.0, and `record()` (`forge/submit.py:233`) then writes
`"formula": null` into the submit log, which under the BLOCKER 2 fix would make the *next* round's
index incomplete.
`forge/tests/test_novelty.py:44-46` pins the fail-open as intended behaviour.

**Reachability, measured: zero today.** 0 of 25,150 local forge journal rows and 0 of 31,084 VPS
forge rows with an alpha id have an empty or missing formula. This is a latent asymmetry, not a live
failure.

**Fix.** Return a third state for an unreadable candidate formula and have `eligible()` hold it under
its own named reason; change the test to pin the hold.

---

### SERIOUS 4 — the only periodic report contradicts the submitter, and nothing monitors the hold
**Where:** `forge/digest.py:86`.
**Found by:** spec (MINOR) and assume (SERIOUS). assume's severity is right.

**Evidence.** `elig, _ = SUB.eligible(scored, corr, rows, pair_counts, posted)` — five positional
arguments, `novelty` left at its `None` default (`forge/submit.py:140`), which
`forge/tests/test_submit.py::test_without_a_novelty_index_the_old_behaviour_is_unchanged` confirms
means no structural gating at all. The m12 digest therefore reports an eligible count, and a
"submittable per 1,000 sims" derived from it, that the submitter will refuse to act on.
`grep -rn "novelty-index-incomplete"` across the repo hits only `forge/novelty.py`,
`forge/submit.py` and the two test files — the hold reason reaches no monitor.
`vps/forge_loop.sh:88-91` reads the submitter's output only through `grep -q "^HTTP 20"`.
At a base rate of 4 accepted POSTs in the desk's entire history, weeks of zero submissions are
indistinguishable from a normal quiet stretch.

**Fix.** Build the index in `digest.py` too and pass it, so both reports answer the same question;
and make an incomplete index a loud event (an m6/m12 message, or a distinct exit code the loop tests)
rather than one line in `loop.log`.

---

### MINOR 1 — `test_novelty.py`'s "ground truth" constants are not the submitted formulas
**Where:** `forge/tests/test_novelty.py:3-9` and the `# measured 0.457` comment at line 35.
**Found by:** exec, rated SERIOUS. **Downgraded to MINOR here, with a correction to exec.**

**Evidence** (scratchpad `adj/t1.py`, against the real formulas pulled from the VPS submit logs):
```
TEST SUBMITTED_SHORT == real vRk095rv ? False
TEST SUBMITTED_IV    == real kqVbg1xP ? False
sim(TEST_SHORT, TEST_IV)          = 0.464270   <- the pair the comment calls "measured 0.457"
sim(REAL vRk095rv, REAL kqVbg1xP) = 0.456714
sim(TEST_SHORT, REAL vRk095rv)    = 0.740864
sim(TEST_IV,    REAL kqVbg1xP)    = 1.000000
```
Re-derived by hand for the first two: fields ∩=2 ∪=8 → J=0.25; op cosine 10/(√18·3)=0.785674;
0.6·0.25+0.4·0.785674 = 0.46427. And ∩=2 ∪=9 → J=0.22222; 10/(√17·3)=0.80845;
0.6·0.22222+0.4·0.80845 = 0.456714. Both match.

**Correction to exec:** `SUBMITTED_IV` is *not* byte-identical to `kqVbg1xP` (window 5 vs 20, sector
vs subindustry) but its structural signature is **identical** — similarity 1.000 — so as a stand-in
in a *structural* test it is exactly the real alpha. Only `SUBMITTED_SHORT` is unrepresentative
(0.7409 against the real `vRk095rv`: it uses `accrual` + `ts_rank:2` where the real one uses
`income`, `cashflow_op`, `abs` + `ts_backfill:1`/`ts_rank:1`). And the test's own conclusion holds:
the two real submissions do not read as repeats of each other (0.4567 < 0.85). The defect is a
measurement attached to the wrong pair and a comment that names neither — documentation, not logic.

**Fix.** Load the formulas from the submit log, or paste the exact strings; correct the comment to
`0.4643` and name the pair it was measured on.

### MINOR 2 — `test_a_horizon_window_and_group_variant_…_is_a_repeat` does not exercise what it names
**Where:** `forge/tests/test_novelty.py:22-28`. **Found by:** exec, rated SERIOUS. **Downgraded.**

**Evidence** (scratchpad `adj/t2.py`):
```
hash equal(IV, VARIANT)? True    sig equal? True    similarity = 1.0
window+group ONLY change -> identical signature? True
verdict with similarity()/near_duplicate() sabotaged -> (True, 1.0, 'kqVbg1xP')
```
The verdict comes from `fingerprint.py:116-118`'s exact-hash fast path, so the `score >= 0.85`
threshold the test names is never evaluated; and "window" and "group" are no-ops, because
`operators.fields_in` drops bare digits (`operators.py:88-89`) and `GROUP_FIELDS`
(`operators.py:86-87`). Only the horizon collapse is exercised.
**Downgraded because the asserted number is not wrong:** with identical signatures the full
similarity path also returns exactly 1.0 (measured above), so the test passes for a true reason via
a path it did not intend.

**Fix.** Split it: one case whose coarse hash differs (add one extra term) to force the similarity
path and assert the real combined score; rename this one to the horizon collapse it actually tests.

### MINOR 3 — a measured similarity of exactly 0.0 prints as "not measured"
**Where:** `forge/submit.py:264` — `… if e.get("structural_sim") else "-"` tests truthiness.
**Evidence:** `sim=0.0 renders '-'`; `sim=0.31 renders '0.31 vs vRk095rv'`; `sim=None renders '-'`
(scratchpad `adj/t5.py` section C). An empty index returns exactly 0.0, so this is the normal case
before the first submission. **Fix:** `is not None`.

### MINOR 4 — `__len__` counts registrations, not structures; a non-dict row raises out of the submit path
**Where:** `forge/novelty.py:50-51,74-80`. `main()` prints that number as "submitted structure(s)".
**Evidence:** `NV.build(["S","S"], {...})` → `len = 2, seen labels = ['S','S']`;
`NV.build(["S"], {"S": "oops"})` → `AttributeError: 'str' object has no attribute 'get'`
(scratchpad `adj/t5.py` sections D, E). Duplicate ids are plausible — the VPS forge submit log holds
`vRk1J2jd` on three lines — though only one carries `http: 201` today, so the inflation is latent.
**Fix:** de-duplicate `posted_alphas` in `build()`; count distinct labels in `__len__`.

### MINOR 5 — `verdict()`'s similarity and its label can describe different alphas
**Where:** `forge/novelty.py:53-62`, inherited from `fingerprint.py:123-130`
(`best, lab = max(best, v), l`) and `fingerprint.py:116-118` (fast path returns a hard-coded 1.0).
**Evidence** (scratchpad `adj/t6.py`), and it is order-independent:
```
sim(cand,A1)=0.8286 near_dup=False      sim(cand,A2)=0.5000 near_dup=True
is_dup(cand) -> (True, 0.8285714285714287, 'A2')      # the score belongs to A1
reversed registration order -> (True, 0.8285714285714287, 'A1')   # dup=True, but A1 is not the dup
```
Impact is presentational only in the current wiring: when `repeat` is True the candidate is held at
`forge/submit.py:198-200` and neither value is written. `fingerprint.py` is out of scope.
**Fix:** weaken `novelty.verdict`'s docstring to what the instrument returns, or report the pair via
`index.nearest()`, which keeps score and label consistent.

### MINOR 6 — two docstring claims the code does not meet
**Where:** `forge/novelty.py:36` and `forge/novelty.py:16-22`.
(a) "Every structural family that has already been POSTed" — `forge/submit.py:254` registers only
`http in (200, 201)`; see SERIOUS 2.
(b) "MEASURED 2026-09-22: the MacBook's journal copy holds the formula for 2 of the 3 submitted
alphas (vRk1J2jd … is absent), so this is not a hypothetical. The builder therefore reports every
unreadable submission, and `submit.eligible` holds the whole round." **The named consequence does
not reproduce on the machine it describes:** the local dry run prints `novelty index over 2
submitted structure(s)` with no warning, because `vRk1J2jd` is absent from the local *submit log*,
so it never enters `accepted`, never enters `missing`, and the branch never fires. The desk has 4
accepted POSTs, not 3. This is a mechanism written into a file whose experiment gives the opposite
result — CLAUDE.md RULE 0 #4.
**Fix.** Restate both to what is checkable: which files the index reads, that an alpha absent from
them is invisible rather than missing, and (from BLOCKER 2) that on the VPS the incomplete branch
fires on every candidate until the formula is read from the submit log.

### MINOR 7 — the structural decision is not persisted, so no POST can be audited afterwards
**Where:** `forge/submit.py:227-239`. `eligible()` computes `structural_sim` / `structural_twin`
(line 211) and `record()` writes neither, nor the thresholds in force. `fingerprint.py`'s
`SIM_THRESHOLD`/`OVERLAP_T`/`OPCOS_T` are shared with five generation-time callers
(`models.py`, `context.py`, `stages/generation.py`, `tools/validate_gen.py`,
`tools/build_robust_select.py`), where a false positive costs one simulation rather than a slot;
nothing pins them for the submit path. **Fix:** persist `structural_sim`, `structural_twin` and the
three threshold values in the submitted-log row, and assert the thresholds at import time.

### MINOR 8 — the horizon regex merges fields that are different line items, not different horizons
**Where:** `fingerprint.py:21,32-34` (`_HORIZON = re.compile(r"_\d+[a-z]?$")`), adopted unguarded by
`forge/novelty.py`. Direction of the error is **over**-blocking, which costs submittable yield —
Khoa's priority #1.
**Evidence** (scratchpad `adj/t7.py`, over the 24,992 local forge formulas): 2,104 distinct field
tokens collapse to 2,012 families; **65 families merge more than one token**, including
`fnd28_annualperf_value ← [09111a, 09400a, 09426a, 09621a]`, `fnd28_anlev_value ← [08230a, 08906a]`,
`aggregated_sentiment_value ← 18 distinct tokens`.
**Contained, measured:** the whole rule flags 908 of 24,992 rows (3.63%), re-derived a second way by
calling `FP.structural_fingerprint`/`FP.near_duplicate` directly (also 908). `fingerprint.py` is
Khoa's; the minimum is to record this as a known over-merge.

### MINOR 9 (SUSPECTED — not demonstrated) — the signature is settings-blind, so one structure may block across pyramid cells
`structural_signature` reads only the formula string, never `row["settings"]`, so the same
construction in a different region/delay/universe/neutralization would read as a repeat — which
collides with the `cell_gain` ordering at `forge/submit.py:212`, whose purpose is to fill open cells.
**I could not demonstrate it:** all 908 currently-flagged journal rows are USA/d1, because recent
rounds are d1-only. **What would settle it:** run the index over a journal slice holding the same
construction in two regions and read the hold reason. **Decision needed:** is D18's "same structure"
per-cell or global? If per-cell, key the index on `(signature, region, delay)`.

### MINOR 10 — the index is built before the lock is taken
`forge/submit.py:255` builds the index; `forge/submit.py:284-287` takes
`/var/lock/wq_submit.lock`, which `tools/climb_submit.py:363` also uses. A POST by the other
submitter inside that window leaves the forge round working from a stale index. **Fix:** build
history and the index after the lock is held.

### MINOR 11 (found in this adjudication; missed by all three) — a second `NoveltyIndex` in the same package
`forge/signature.py:77` already defines a class called `NoveltyIndex` — "Signatures of everything
already in the book (ACTIVE/submitted)" — used as the **hard pre-simulation** novelty gate
(`forge/gates.py:58` → `forge/runner.py:146`), and `forge/__init__.py:3` labels `signature` as
"(novelty)". The new module is `forge/novelty.py` and defines a second class of the same name with a
different definition of "novel" (structural fingerprint vs. exact signature key), a different source
of truth (local submit logs vs. `fetched/rc/active_book.json`) and different `__len__` semantics.
**I could not demonstrate a runtime failure** — the two are separate modules and nothing imports both
— so this is a naming and review hazard, not a bug. It matters because CLAUDE.md RULE 2 gate 5
requires naming every existing rule and gate a new mechanism touches, and neither `forge/novelty.py`
nor `00_agreements.md` D18 names the pre-sim gate it sits beside.

---

## 3. Positively confirmed (re-verified here, not taken on the auditors' word)

- **The wiring is faithful to the instrument.** `forge/novelty.py` contains no similarity arithmetic
  of its own — read line by line, it only calls `FP.StructuralIndex`, `register` and `is_dup`. Both
  of `fingerprint.py`'s mechanisms are genuinely in play: `register()` populates `self.hashes`
  (`fingerprint.py:132-134`) so the coarse exact bucket is live on the fast path (116-118), and the
  containment rule runs through `near_duplicate` (127). Of the 908 flagged local rows, 32 are flagged
  by the containment branch at a combined score below 0.85, i.e. both branches fire in practice.
- **The same key on both sides.** `build()` registers `row["formula"]` (`novelty.py:76`), `eligible()`
  checks `row["formula"]` (`submit.py:197`), and that is the key `record()` writes
  (`submit.py:233`). No silent field mismatch.
- **Neutralization and grouping are correctly outside the comparison**, as D18's paragraph describes:
  `operators.fields_in` skips `GROUP_FIELDS` (`operators.py:86-87`), verified —
  `structural_signature` of a sector version and an industry version of the same formula are equal.
- **Placement inside `eligible()` is safe.** The novelty block (`submit.py:193-203`) is the last hold,
  after stage, no-journal-row, already-posted, pyramid, corr-unmeasured, corr-over-line, PBO and
  diversity. Reading every path from 150 to the single `out.append` at 208, no branch reaches
  `out.append` without passing 193.
- **`novelty` defaults to `None` and that path is unchanged**, pinned by
  `test_without_a_novelty_index_the_old_behaviour_is_unchanged`; the new parameter gates no other
  caller by accident.
- **The fix for BLOCKER 2 is viable.** The formula stored in the submit log is byte-identical to the
  journal's for all three forge alphas (`log == journal: True`), and `mL516W9W`'s climb-log formula
  (543 chars) matches its `regular.code` in `fetched/rc/active_book.json` in length and prefix.
- **`http` is an int on every real path** — `tools/climb_submit.py:218` returns `r.status_code`; the
  VPS logs parse as `int` for 201 and `NoneType` for the adjudication rows, so the `in (200, 201)`
  membership test is not silently missing a string `"201"`.
- **No module shadowing for `fingerprint`/`operators`**, locally or on the VPS (no such file under
  `/opt/wq`, and nothing by those names in the VPS venv's site-packages).
- **Tests.** `python3 -m pytest forge/tests -q` → **225 passed in 15.29s**.
  `forge/tests/test_novelty.py` collects 6, `forge/tests/test_submit.py` collects 14 (4 appended).
- **Blast radius, measured not guessed.** An index over all four real submissions flags 908 of
  24,992 local forge formulas (3.63%), re-derived independently; it blocks **9 of the 21** currently
  scored candidates. The 2-submission index and the 4-submission index block the same 9 — today's
  two extra submissions add no blocks. The rule is a screen at this pool size, not a strangler, but
  43% of the current candidate list is not a small number against priority #1, and it is a number
  Khoa should see before this ships.
- **Cost is not an issue.** exec measured 4.89 ms per candidate at 1,460 registered submissions
  (one year at 4/day) with the fast path forced to miss, re-derived at 2.39 ms via `nearest()`.
  I did not re-run this; it is not load-bearing for any decision here.

---

## 4. Dropped, and why

- **exec's BLOCKER detail that the VPS `missing` list is `['mL516W9W', 'vRk1J2jd']`** — **refuted.**
  `vRk1J2jd` *is* in `/opt/wq/state/layered/runs/forge.jsonl` with `meta.forge` and a formula,
  confirmed two ways (the `forge_rows` replication, and `grep -c vRk1J2jd forge.jsonl` = 1). The
  correct VPS state is `len=3, missing=['mL516W9W']`. exec appears to have replayed the VPS *logs*
  against the *local* journal. spec and assume were right. **The blocker itself is unaffected** —
  one unreadable submission is enough to hold every round forever.
- **assume's MODERATE that the C16 second-best rule now picks one rung lower** — **not a defect of
  this module.** `choose()` operates on whatever `eligible()` returns, so *every* hold reason —
  `corr-over-line`, `pbo-fail`, `dataset-set-repeated-today` — has had exactly this interaction since
  before this change. Reported as an observation: if Khoa wants the second-best rule to run over the
  pre-hold ranking, that is a change to `choose()`, not to novelty. Worth logging which higher-ranked
  alphas a hold removed, which folds into MINOR 7.
- **spec's SERIOUS that D19 is implemented nowhere on the POST path** — **true but out of scope.**
  Verified: `grep` over `forge/submit.py` for `standard`/`admissible`/`hard_gates`/`meaning` returns
  nothing, and `forge/standard.py`'s 8 gates still run pre-simulation at `forge/runner.py:104`
  (`if ST.admissible(c)`), which is the order D17 reverses. But this module's specification is D18
  plus the `fingerprint.py` paragraph; D19 is a separate unimplemented decision. Recorded as an
  **open spec item**, below, not as a defect in the code under audit. spec is right that if the
  interlock is ever built it belongs in `submit.py`, because that is the only irreversible POST path.
- **assume's MINOR that `sys.path` order could shadow Khoa's `fingerprint`** — kept only as
  hardening, labelled **SPECULATION**: `find . -name fingerprint.py` returns only `./fingerprint.py`
  and there is no `tools/fingerprint.py` or `tools/operators.py`, so it is not demonstrable today.
  `forge/submit.py:27` already forces ROOT ahead of `tools`, making
  `forge/novelty.py:30-31`'s guarded insert a no-op in the submit path. An
  `assert FP.__file__ == str(ROOT / "fingerprint.py")` after the import would settle it permanently
  and costs one line.
- **exec's note that `tools/tests/test_layered_sim.py::test_a_crash_mid_batch_loses_no_journalled_row`
  fails** — not re-run here (275 s), and not attributable: exec showed it fails in isolation and that
  `grep -c novelty` over that file and `tools/layered_sim.py` is 0/0, and `git status` shows
  `tools/layered_sim.py` as separately modified uncommitted work. Not a regression from this module.

---

## 5. Open items that are not this module's defects

- **D19 is unimplemented.** `main()` POSTs every eligible candidate up to `--cap` with no meaning
  score consulted; the "5–7 → Khoa ticks" and "<5 → do not submit" branches do not exist, and the
  8 gates still run pre-simulation. Needs its own module and its own tick.
- **RULE 2 has not been run on this mechanism.** Gate 3 asks for proof across many live rounds against
  the arm without it; there is none — the module has never run live. Gate 5 asks for every existing
  rule it touches to be named; the pre-simulation novelty gate (`forge/signature.py` +
  `forge/gates.py`, C12) is not named anywhere in the module or in D18. Both are open.
- **The 403 policy (SERIOUS 2) is Khoa's decision, not an auditor's.**

---

## 6. What must be fixed before this goes in the submit path

1. Ship `fingerprint.py` + `operators.py` to `/opt/wq`, and fail loudly by name if they are missing
   (BLOCKER 1).
2. Read the submitted formula from the submit-log row, not from the forge journal (BLOCKER 2), and
   correct the two docstring sentences that state the opposite.
3. Register each accepted POST into the live index and re-filter `elig` before the next pick
   (BLOCKER 3).
4. Hold — do not pass — a candidate whose own formula is unreadable (SERIOUS 3).
5. Register `http is None` POSTs; get Khoa's tick on 403 (SERIOUS 2).
6. Pass the index to `forge/digest.py`, and make an incomplete index a loud event (SERIOUS 4).

Items 1–4 are mechanical and testable. Item 5 needs a tick. SERIOUS 1 (platform as the authority) is
the right long-term shape and can follow, because items 1–3 make the local logs complete for every
POST this pipeline makes itself.
