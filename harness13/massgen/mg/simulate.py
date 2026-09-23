#!/usr/bin/env python3
"""MASSGEN box 9 `simulate` + box 10 `metrics` — REQ-MG-09 and REQ-MG-10.

WHAT LICENSES THIS MODULE
  SPEC.md REQ-MG-09, verbatim: "Submit and poll to completion. `COMPLETE` and `WARNING` are both
  successes for every downstream step."
  SPEC.md REQ-MG-10, verbatim: "Fetch sharpe, fitness, turnover and the platform check set. A
  `None` sharpe is `METRICS-FAIL` and returns to resume: a network flake must never convert a good
  alpha into a permanent failure."
  SPEC.md REQ-MG-20 fixes the two fates and the vocabulary this module emits: RE-RUN is any status
  that is neither COMPLETE nor WARNING (`OP>64`, `AUTH-FAIL`, `EXC`, `METRICS-FAIL`, absent), and
  **only `EXC` carries an `err_class`**.

WHAT THIS MODULE IS NOT
  It is not a second HTTP client. The pieces it stands on already exist in this repository:
    * `harness13/crawl_fields.py` — `Response`, `SystemClock`/`VirtualClock`, `classify_429`,
      `AuthExpired`, `DailyLimitReached`. Re-exported below so a caller has one import.
    * `tools/funnel/gate_lib.py` — `required_present()`/`gate_status()`, the PRESENCE CONTRACT.
    * `tools/fetch_prod_corr.py::session()` — the repo's cookie session, imported lazily, exactly
      as `harness13/crawl_fields.py:198-211` imports it.
  `tools/resim_bulk.py` is the live simulate/poll/metrics client and is deliberately NOT imported:
  it takes an flock, loads the cookie pickle and opens journals AT MODULE IMPORT (lines 38-74), so
  importing it would start a second engine. The two things worth copying from it are copied with a
  citation: the POST body shape (`payload`, resim_bulk.py:116-120) and the age-gated poll cadence
  (R1.2, resim_bulk.py:496).

THE BEHAVIOUR THIS MODULE EXISTS TO GET RIGHT
  A transient condition must never be recorded as a permanent fact. MEMORY records 8 confirmed
  cases of that bug class in this repository; `tools/resim_bulk.py:444-458` records one of them in
  detail — 220 of 1,096 rows journalled `<no checks>` because a single failed READ was written as
  if it were a measurement, and that flipped a structural verdict. So:
    * an unreadable metrics payload is `METRICS-FAIL`, never a zero and never a drop;
    * a `None` sharpe is `METRICS-FAIL`, never a zero;
    * a payload that carried metrics but NO check row is `METRICS-FAIL` too — see the next block;
    * `METRICS-FAIL` keeps `alpha_id` and `platform_status`, so resume can RE-READ the alpha at
      zero simulation cost instead of re-simulating it.

A POLL INTERRUPTED BY A DEAD SESSION MUST NOT COST A SIMULATION (added 2026-08-12)
  The same idea as METRICS-FAIL, one box earlier. When the poll loop cannot continue — a 401, poll
  exhaustion, or a DAILY 429 arriving mid-poll — THE SIMULATION IS UNAFFECTED. It is running on the
  platform and it will finish; only our handle on it was ever at risk. `SimResult` has always kept
  `sim_url`, and `as_record()` dropped it, so the row went back to resume carrying nothing but a
  formula and the next run re-POSTed work the platform already holds.
    * `as_record()` now emits `sim_url` whenever the platform gave one.
    * `resume_handle(record)` names the handle a row carries: the alpha id when the platform's own
      DONE verdict is also on the row (one GET, no waiting), else the simulation url (poll it, no
      POST), else `None` — and `None` is the honest answer that this row really must be re-simulated.
    * `resume_one(record, transport)` spends that handle. It POSTs nothing: this module's only POST
      is in `_run`, and `resume_one` does not call it.

  WHY THIS IS NOT A NEW STATUS. REQ-MG-20's vocabulary is CLOSED and `mg/resume.py` has exactly
  three fates, none of which is "re-runnable by READING". A new status word here would be one the
  drop box cannot classify, which is the fabrication REQ-MG-20 forbids. So the distinction rides as
  DATA — the handle on the row — and the fate stays RE-RUN. Teaching resume to spend the handle is
  `resume.py` + `pipeline.py`'s change, not this module's; see OPEN_QUESTION 3.

  WEIGHT IT HONESTLY — LATENT HERE, REAL NEXT DOOR. This spine has never run: 0 rows anywhere under
  `state/` carry this module's status vocabulary, so the massgen-side loss to date is ZERO and the
  fix reclassifies nothing that exists. The CONDITION is not hypothetical. In this repository's
  other simulate/poll client (`tools/resim_bulk.py`), which persists its handles in
  `state/resim_inflight.json` and re-adopts them on restart (R1.3, resim_bulk.py:228-257),
  `state/resim_metrics.jsonl` records 47 real 401s — 13 of them on a `poll` request, 2 on an
  `adopt`, 1 on an `alpha` read — and 479 adoption events covering 4,688 old_ids, against 9 events
  / 90 ids whose handle no longer resolved and 4 / 40 dropped on the inflight deadline. That file
  holds 8 urls / 80 ids right now, left behind by the run of 2026-08-10. Those are that client's
  counts on the same account and the same API, not this module's: they establish that a poll gets
  interrupted while a simulation is live, not how often it will happen here.

  THE GUARD USED TO READ `sharpe` ONLY, AND LANDED ONE FIELD OVER (fixed 2026-08-12). A payload
  carrying sharpe/fitness/turnover with `checks: []` returned COMPLETE, `resume.classify` filed it
  FATE_DONE, and it was never re-read and never re-simulated — the record even carried
  `missing_required` naming all six USA-d1 gates and nothing read it. The check set is half of what
  REQ-MG-10 says box 10 must fetch, so a read that returned none of it is a read that half-landed.
  WEIGHT IT HONESTLY — a LATENT hole, not a measured loss. Measured 2026-08-12 over
  `state/resim_results.jsonl` two ways (raw lines and keyed by `old_id`, both giving 69,776
  COMPLETE/WARNING rows): **0 rows carry a sharpe with an empty or absent check set.** This
  repository has never observed the shape. The fix reclassifies nothing that exists; it closes the
  hole before a payload change opens it, and its cost IF the shape ever occurs is stated at
  `_finish` rather than hidden.

MULTISIM — ONE POST, MANY CHILDREN (added 2026-08-12, beside the single path, not replacing it)
  WHAT WAS MEASURED, live, at a cost of 19 ATTEMPTED / 18 ACCEPTED simulations — NOT 8.
  CORRECTED 2026-08-13: `experiments/evidence/ladder_live.jsonl` logs every POST. The 8 is
  the PARENT count at the refusal, a different quantity, and it was copied into six files as
  though it were the cost. Line 1354 of this same module already said so; the correction had
  reached one of four modules and neither .md.
    * eight single parents posted ONE AT A TIME, `alive_before` 0..7 -> all 201 ACCEPTED
    * the NINTH, at `alive_before: 8` -> **429 CONCURRENT_SIMULATION_LIMIT_EXCEEDED**
    * 1 parent / **10 children** -> ACCEPTED, 337.3s later, with the account drained to zero
  NO VERDICT. This module said "the concurrency counter counts PARENT REQUESTS" as a finding; it is
  not one. A limit on the REQUEST RATE fits every row just as well -- eight POSTs inside eight
  seconds refused on the ninth, one POST after 337 seconds of silence accepted. Two mechanisms fit
  and no experiment separated them: **MECHANISM: UNKNOWN**. The 8x10 shape actually in use is
  OPERATOR-STATED by Khoa, 2026-08-12, and is not a measurement made here.

  WHAT IS ARITHMETIC AND NOT A MEASUREMENT. `simulate_one` POSTs one construction per request, so it
  is capped at ~8 concurrent; at the 364s median latency the pre-registered 4,800-simulation
  experiment is ~60 hours, and at 10 children per parent under the same 8-parent ceiling it is ~6.
  **That factor of ten is a projection from one accepted POST, not measured throughput.** Nothing
  here has ever run 8 parents x 10 children to completion, per-child latency under a loaded parent is
  UNKNOWN, and the ceiling may move. Do not quote the 10x as an observed speed-up.

  `MULTISIM_CHILDREN = 10` IS A CHOICE, NOT AN OPTIMUM. 10 is what `tools/resim_bulk.py:25` uses and
  what the ladder accepted once. **Nothing establishes that 10 is optimal or that 20 would be
  refused** — `resim_bulk` itself carries `MAX_TRY_CONC = 20` for PARENTS, which is a different
  quantity. It is a parameter (`size=` on `multisim_groups`, and `simulate_many` simulates exactly
  the list it is handed) so a round with simulations to spend can measure it.

  THE BODY SHAPE is a JSON LIST of the same per-child payloads `payload()` already builds
  (`tools/resim_bulk.py:295`, the working shape). The three mandatory settings fields
  (`pasteurization`, `unitHandling`, `nanHandling`, added 2026-08-12 after the platform 400ed
  without them) ride on EVERY child payload because `payload_many` is `payload` per child and
  nothing strips them.

  A GROUP MUST BE HOMOGENEOUS in `(delay, region, universe)` — `tools/resim_bulk.py:207-213`
  records a mixed-region batch being rejected 400, found with the CHN/JPN pyramid set. `decay` and
  `neutralization` are NOT in that key and vary freely within one parent, which is what makes
  REQ-MG-02's grid (wrapper x decay x neutralization) shippable as multisim at all. `simulate_many`
  REFUSES a mixed list rather than spending a POST to be told; `multisim_groups` builds legal ones.

  A CHILD THAT FAILS MUST NOT TAKE ITS NINE SIBLINGS WITH IT. Each child is resolved on its own
  handle through the SAME `_poll` the single path uses, so each child gets its own status, its own
  `err_class` (only when EXC), its own metrics read and its own journal row. `_poll` never raises —
  401 and a DAILY 429 come back as that child's own outcome — so one dead child cannot unwind the
  loop over the others. Only failures of the SHARED resource (the POST, the parent poll) fan out to
  all children, and they fan out as the same status each child would have received alone.

  EVERY CHILD ROW NAMES ITS OWN ARM. `key` (its own construction id), `settings` (its own segment)
  and `meta` (its mechanic, carried by `pipeline._carry_meta`) are per-child, exactly as on the
  single path. The pre-registered analysis blocks on (base, decay) and a row that cannot name its
  arm cannot be counted, so nothing about a child is inherited from its parent except `parent_url`.

  THE LOAD-BEARING ASSUMPTION, AND IT IS UNVERIFIED HERE. `children[i]` is taken to be the outcome
  of `constructions[i]` — request order. It is inherited from `tools/resim_bulk.py:510`, the only
  client in this repository with real multisim history, and **this machine cannot check it**:
  attempted 2026-08-12 by joining the journal's requested `formula` against the platform's echoed
  `formula`, and the two corpora do not intersect (69,546 journal alpha ids, 9,984 in
  `fetched/alphas_all.jsonl`, **overlap 0**). So it is an ASSUMPTION, labelled, not a finding —
  and it is the one failure mode that would corrupt silently rather than loudly, by filing a real
  measurement under the wrong arm. Two guards, both fail-CLOSED and neither claiming more than it
  sees:
    * a children list whose LENGTH disagrees with the request refuses to attribute ANY child
      (`multisim-children-M-of-N`), rather than zipping the shorter of the two;
    * `_poll(expect_formula=...)` compares the platform's echoed `regular` against the formula this
      child was built from and refuses that child on a disagreement. If the platform echoes no
      formula, **nothing is checked and nothing is claimed** — the guard is silent, not satisfied.
  Settling it costs one live 10-child POST of observably different formulas; see OPEN_QUESTION 5.

  RESUMING A CHILD. A row carries `parent_url` + `child_index` from the moment the POST is accepted,
  so an interruption BEFORE the children were ever named is still recoverable: `resume_one` re-polls
  the parent, picks its own index and polls that child — GETs, never a POST. Once the child's own url
  is known it is on the row as `sim_url` and takes precedence, because it is the more direct handle.
  Without `HANDLE_PARENT` a parent url in `sim_url` would be a TRAP: `_poll` would read the parent's
  COMPLETE-with-no-`alpha` as METRICS-FAIL and every resume would re-derive the same non-answer
  forever. That is why the parent handle is a distinct kind and not a reused one.

DETECTION AGE — WHAT OUR POLLER SAW, WHICH IS NOT WHEN THE PLATFORM FINISHED (added 2026-08-13)
  `_poll` and `_poll_parent` already computed `clock.now() - t0` on every iteration to drive the
  age-gated cadence, and threw it away at every exit. Journalling it costs nothing — no extra
  request, no extra simulation — so `detect_age_s` and `terminal_poll` now ride on `SimResult` and
  reach the journal through `as_record()`.

  **WHAT `detect_age_s` IS NOT.** It is NOT the platform's completion time, and no arithmetic on it
  recovers one. It is the interval from the first poll of the loop that observed this outcome to
  the moment THE POLLER NOTICED a terminal status. The simulation finished at some unobserved
  instant inside the gap between the previous poll and that one, and this module never learns
  where. Every number derived from it is INTERVAL-CENSORED BY THE POLL GRID.

  **WHY `terminal_poll` IS THE HALF THAT MAKES THE CENSORING RECOVERABLE.** An age alone gives only
  the right-hand end of the interval. With the 1-based poll index and the cadence (`_poll_wait`),
  the interval is reconstructible: completion lies in `(age_at_poll k-1, age_at_poll k]`, and at
  `k == 1` the interval is `(0, FIRST_POLL_S]` — which fixes total mass and says NOTHING about
  shape. This matters at the observed rate: `tools/resim_bulk.py`'s `lat_s` (the repo's only other
  latency field, and the same launch->DETECTION quantity, not a completion time) had 22.1% of
  parents already terminal at the first poll over n=7,973. Reported by another agent 2026-08-12 and
  NOT re-derived here — it is cited as the reason the index is worth a key, not used as a result.

  **A MODE IN THIS FIELD IS A MODE OF THE INSTRUMENT.** Detections can only land on poll boundaries,
  so `detect_age_s` is supported on the cadence grid and its peaks sit on cadence edges by
  construction. Reading modality off it reads the poll schedule. MECHANISM: UNKNOWN for any
  structure seen in it, and this docstring is the reason not to invent one.

  **A RESUMED ROW CARRIES NEITHER FIELD, BY CONSTRUCTION.** `resume_one`/`resume_group` poll a
  simulation submitted in an earlier attempt, and how much earlier is recorded nowhere (`_poll`'s
  own docstring already says no age is claimed for a resumed simulation). Their clock starts at the
  RECOVERY, and with the opening wait skipped an already-finished simulation reads `0.0` — a real
  number for the wrong quantity, and one no other key on the record could be used to filter out.
  So `_no_detection_on_resume` CLEARS the pair on every row those two return, which fixes the
  invariant a reader can rely on:

      `detect_age_s` and `terminal_poll` are present IFF this row's simulation was both dispatched
      and detected within the same run.

  `polls` is untouched there and still reports what the recovery cost.

  **ON A MULTISIM CHILD, THE WAITING WAS THE PARENT'S.** A child is polled with `wait_first=False`
  only after its parent is already terminal, so the child's own loop typically detects on poll 1 at
  an age of ~0. `detect_age_s` is therefore SUMMED with the parent's, exactly as `polls` already is,
  so the field means launch->detection end to end on both paths. `terminal_poll` is NOT summed: it
  stays the index within the loop that made the observation. That leaves the parent's own index
  recoverable as `polls - terminal_poll`, which is 0 on the single path and on a parent fanout.

  **THE UNITS ARE THE CLOCK'S.** `SystemClock.now()` is `time.time()` and `VirtualClock.now()` is a
  counter from `SIM_EPOCH`, so only DIFFERENCES are portable between them. Nothing absolute is
  journalled from the clock for that reason; the only absolute instant on a row is the platform's
  own `date_created`, below.

THE PLATFORM'S OWN TIMESTAMP — IT EXISTS, ON THE ALPHA, AND ITS MEANING IS UNSETTLED (2026-08-13)
  Searched before building the censoring apparatus, reading STORED BODIES only and making no API
  call. What the corpus says:
    * `dateCreated` IS a real platform-echoed key on the ALPHA object: 9,984 / 9,984 rows of
      `fetched/alphas_all.jsonl` carry it, ISO-8601 at second precision with the platform's ET
      offset (`"2026-07-14T16:27:19-04:00"`). It is also server-side sortable and filterable —
      `tools/daily_budget.py:58-61,104` already uses `order=-dateCreated` and a `dateCreated>`
      filter to derive the platform's ET day boundary.
    * NO stored SIMULATION body carries any time key — because **no simulation body is stored
      anywhere in this repository at all**. `state/resim_results.jsonl` (78,319 rows) is not a
      stored body: `tools/resim_bulk.py:498-531` keeps `status`, `alpha` and `children` off the
      poll payload and discards the rest. So "the simulation object has no completion timestamp"
      is NOT established here; what is established is that this machine has never written one down.
      Settling it costs one live GET of a simulation url and a look at the whole body.
  `metrics_from_alpha_json` now carries `dateCreated` through as `Metrics.date_created`, verbatim,
  because the payload was already fetched and parsed and dropping it was the only reason the
  question needed a proxy at all.

  **IT IS NOT KNOWN TO BE THE COMPLETION TIME.** It is the ALPHA's creation stamp. Whether an alpha
  is created when its simulation completes is UNVERIFIED: nothing on disk pairs a client-observed
  completion instant against the same id's `dateCreated`, and the one alpha-vs-simulation
  reconciliation this repo did record (`daily_budget.py:120-131`) found the two counts disagreeing
  by ~300 in a day. `experiments/SIM_CEILING.md:24-26` is careful for the same reason: that counter
  means ALPHAS CREATED, not simulations attempted. It is journalled as the platform's string, with
  no parsing and no interpretation, so a later round can settle the question instead of assuming it.
  Rows that never produced an alpha (ERROR, a refused POST) have no such stamp and never will —
  which is why the detection-age fields are kept rather than replaced by this one.

PRESENCE CONTRACT (established in this repo, honoured here, not re-invented)
  `tools/funnel/gate_lib.py:45-95` + `tools/funnel/test_gate_lib_presence.py`: "Absence is not a
  pass." Measured 2026-08-08 over 58,383 rows — 1,022 of 2,496 "zero-fail" rows (41%) carried no
  FAIL only because the gate that would have failed them was never in the payload. Here:
    * `Metrics.check_result(name)` returns `None` when the check is ABSENT. `None` is a THIRD
      value: not a pass, not a fail. Nothing in this module maps it to PASS, FAIL, 0 or False.
    * `Metrics.missing_required` is `gate_lib.gate_status()['missing_core']` — the required gates
      for this region/delay that the payload never adjudicated — carried on every record so no
      downstream step can read absence as clearance.
    * `Metrics.present` names only the metrics whose values the payload actually carried. An
      absent sharpe/fitness/turnover is `None`, never 0.0.
  Collecting `hard_fail` (REQ-MG-11, with `SELF_CORRELATION` excluded) is the hardfail box's job,
  not this one; this module hands it the raw check rows plus the presence evidence.

429 HANDLING — POST-HOC, measured by other tools in this repo, not here
  `tools/daily_budget.py:10-14` and `tools/resim_bulk.py:331-363`: the 429 body alternates between
  DAILY and CONCURRENT on identical requests, so the body is a report of whichever limit check
  fired, not a diagnosis of which limit is actually binding. MECHANISM: UNKNOWN. `classify_429` is
  reused unchanged and a DAILY body STOPS the attempt instead of re-probing, which is the
  conservative direction: it can only end the attempt early, never push past a ceiling. Re-probing
  a daily wall is what burned 4h45m on 2026-08-02.

NO SUBMIT PATH. REQ-MG-17: the machine never submits. `LiveTransport` refuses any URL containing
`/submit` before it reaches the network.

OPEN_QUESTIONS
  1. The notes' status vocabulary (REQ-MG-03/20) has no bucket for a platform-terminal `ERROR`
     simulation. It is recorded here as `EXC` with the platform's own word and message in
     `err_class`, because `EXC` is the only status the spec allows to carry a diagnosis and the
     platform supplied one. The consequence, stated rather than hidden: RE-RUN will re-simulate a
     formula the platform already rejected. Whether the notes intended a permanent bucket for that
     is UNKNOWN.
  2. `MAX_POLLS` is a bound, not a measurement. 200 polls on the cadence below is ~87 minutes of
     virtual time, chosen to sit under `resim_bulk.MAX_INFLIGHT_AGE` (5400s) while clearing the
     57-71 min first-completion window recorded in `tools/funnel/run_multisim.py:231-234`. No
     measurement here establishes that a parent alive at poll 200 is dead.
  3. `resume_one` exists and NOTHING CALLS IT. `resume.plan` hands `pipeline.py` CONSTRUCTIONS, and
     a construction carries no handle, so the spine still re-simulates every row this module made
     recoverable (`pipeline.py` OPEN_QUESTION (a) records the same gap for METRICS-FAIL). Making
     the handle available is this module's half; spending it is the integrator's, and which module
     should own the choice is not decided here.
  4. A POST whose RESPONSE is lost — the platform accepted it, the reply never arrived — creates a
     simulation whose url this module never learns, and `_request` then retries the POST, so one
     construction can cost up to `MAX_ATTEMPTS` simulations. Not fixed here and not papered over:
     suppressing the retry would trade a duplicated simulation for a lost one, and whether the
     platform offers any idempotency key is UNKNOWN. Reach is also UNKNOWN — nothing on disk
     records "request sent, reply lost" as distinct from "request failed". MULTISIM MULTIPLIES ITS
     COST BY THE GROUP SIZE — a lost reply on a 10-child POST orphans ten simulations, not one.
  5. WHETHER `children[i]` IS `constructions[i]` IS UNVERIFIED ON THIS MACHINE (see MULTISIM above).
     One live 10-child POST of observably different formulas settles it. Until then the two
     fail-closed guards are the whole defence, and the second of them is silent if the platform
     echoes no formula — so a green run is NOT evidence that the order is right.
  6. WHETHER 10 IS THE RIGHT CHILD COUNT IS UNKNOWN. One accepted 10-child POST is one data point;
     it bounds nothing from above. `MULTISIM_CHILDREN` is a parameter so that a round with
     simulations to spend can climb it the way `resim_bulk` climbs its parent ceiling.
  7. `simulate_many` polls its parent SERIALLY inside one call, so a group's wall-clock is its
     SLOWEST child plus the parent's own latency. Whether that is better or worse than 10 separate
     parents at the same concurrency is arithmetic nobody here has run against real per-child
     latencies, which are UNKNOWN.
"""
from __future__ import annotations

import dataclasses
import pathlib
import random
import sys
from urllib.parse import urljoin

ROOT = pathlib.Path(__file__).resolve().parents[3]
API = "https://api.worldquantbrain.com"

for _p in (str(ROOT), str(ROOT / "tools" / "funnel")):
    if _p not in sys.path:
        sys.path.append(_p)                    # append, never insert: must not shadow stdlib

import gate_lib                                                        # noqa: E402
from harness13.crawl_fields import (                                   # noqa: E402
    AuthExpired, DailyLimitReached, Response, SystemClock, VirtualClock, classify_429)

__all__ = ["AuthExpired", "DailyLimitReached", "Response", "SystemClock", "VirtualClock",
           "SimTransportError", "LiveTransport", "Metrics", "SimResult",
           "DONE_STATUSES", "RESUME_STATUSES", "STATUS_EXC", "STATUS_METRICS_FAIL",
           "STATUS_AUTH_FAIL", "STATUS_OP64", "is_done", "returns_to_resume",
           "payload", "simulate_one", "fetch_metrics", "metrics_from_alpha_json",
           "HANDLE_ALPHA", "HANDLE_SIM", "HANDLE_PARENT", "resume_handle", "resume_one",
           "resume_group", "is_parent_line",
           "MULTISIM_CHILDREN", "MULTISIM_GROUP_KEYS", "PARENT_TERMINAL",
           "payload_many", "multisim_key", "multisim_groups", "simulate_many"]

# ---------------------------------------------------------------------------- status vocabulary
# REQ-MG-03 / REQ-MG-20, verbatim. This list is CLOSED: a status outside it cannot be classified by
# the drop box, so nothing here emits one.
DONE_STATUSES = ("COMPLETE", "WARNING")

STATUS_OP64 = "OP>64"                 # emitted by the opcount box (REQ-MG-08), named here so the
STATUS_AUTH_FAIL = "AUTH-FAIL"        # classification helpers cover the whole vocabulary
STATUS_EXC = "EXC"
STATUS_METRICS_FAIL = "METRICS-FAIL"
RESUME_STATUSES = (STATUS_OP64, STATUS_AUTH_FAIL, STATUS_EXC, STATUS_METRICS_FAIL)

# The three metrics REQ-MG-10 names. Absent ones stay absent; see the presence contract above.
METRIC_NAMES = ("sharpe", "fitness", "turnover")

# Poll cadence, copied from tools/resim_bulk.py:496 (R1.2 age-gated polling) rather than invented.
FIRST_POLL_S = 90.0
YOUNG_POLL_S = 120.0
OLD_POLL_S = 25.0
OLD_AFTER_S = 300.0
MAX_POLLS = 200                       # bounded: a vanished parent cannot wedge a chunk (REQ-MG-05)

#: A MULTISIM parent is terminal on any of these. The three error words are terminal for the PARENT
#: and say nothing about its children: `tools/resim_bulk.py:479-530` walks the children on every
#: terminal word, and a parent-level ERROR is not a verdict on ten formulas. So the children are
#: resolved individually under all five, and only a parent that names NO children falls back to the
#: platform's own word for all of them.
PARENT_TERMINAL = DONE_STATUSES + ("ERROR", "FAIL", "FAILED")

#: Children per multisim parent. **A CHOICE, NOT AN OPTIMUM — see the MULTISIM block above.** 10 is
#: `tools/resim_bulk.py:25`'s BATCH and the count one live POST accepted on 2026-08-12. Nothing
#: establishes that it is best or that a larger group would be refused. It is the DEFAULT of a
#: parameter, never a constant read at a call site, so measuring another value costs an argument.
MULTISIM_CHILDREN = 10

#: The settings a multisim group must AGREE on. From `tools/resim_bulk.py:207-213`, which records a
#: mixed-region batch rejected 400. `decay` and `neutralization` are deliberately absent: they vary
#: within a parent, and REQ-MG-02's grid varies exactly those two.
MULTISIM_GROUP_KEYS = ("delay", "region", "universe")

MAX_ATTEMPTS = 4                      # retries per single request; ONE retry layer, in `_request`
JITTER_S = 0.25                       # same bound as harness13/crawl_fields.py:83
MAX_RETRY_AFTER_S = 600.0             # above this the platform is not throttling, it has banned the
                                      # account (tools/resim_bulk.py:97). Stop; do not sleep on it.


def is_done(status):
    """REQ-MG-03: only COMPLETE and WARNING are done. A WARNING is a SUCCESS, not a failure."""
    return str(status or "").upper() in DONE_STATUSES


def returns_to_resume(status):
    """The status half of REQ-MG-20's RE-RUN fate: anything that is not COMPLETE/WARNING.

    The full RE-RUN vs PERMANENT adjudication also needs `hard_fail` (a COMPLETE/WARNING row with a
    hard fail is PERMANENT) and belongs to the drop box, not here.
    """
    return not is_done(status)


class SimTransportError(RuntimeError):
    """A request did not complete. TRANSIENT by construction — never a permanent verdict.

    `reason` is a description of what the transport did, not a diagnosis of the alpha. It is the
    only thing this module ever puts in an `err_class`.
    """

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


# ---------------------------------------------------------------------------- transport
class LiveTransport:
    """POST /simulations + GET, over the repo's own cookie session. Never built at import time.

    Duck-typed: `simulate_one`/`fetch_metrics` accept anything with `.post(path, body)` and
    `.get(url, params=None)` returning a `Response`, so the offline tests need no HTTP library.
    """

    def __init__(self, session=None, timeout=40):
        self._s = session if session is not None else _live_session()
        self.timeout = timeout

    @staticmethod
    def _url(target):
        if "/submit" in target:
            # REQ-MG-17: the machine stops at the leaderboard. A 403 spends the alpha permanently.
            raise SimTransportError("submit path refused: %s" % target)
        return target if target.startswith("http") else API + target

    def post(self, path, body):
        r = self._s.post(self._url(path), json=body, timeout=self.timeout)
        return Response(r.status_code, text=r.text, headers=dict(r.headers))

    def get(self, url, params=None):
        r = self._s.get(self._url(url), params=params, timeout=self.timeout)
        return Response(r.status_code, text=r.text, headers=dict(r.headers))


def _live_session():
    """The repo's cookie session, imported lazily — same source and same reason as
    harness13/crawl_fields.py:198-211 (imports cleanly with no credentials and no HTTP library)."""
    if str(ROOT) not in sys.path:
        sys.path.append(str(ROOT))
    from tools.fetch_prod_corr import session
    return session()


# ---------------------------------------------------------------------------- request layer
def _header(resp, name):
    """Case-insensitive header read. `Response.headers` is a plain dict of whatever casing the
    server sent, so `.get("Location")` alone is a silent miss on a lowercase header."""
    low = name.lower()
    for k, v in (getattr(resp, "headers", None) or {}).items():
        if str(k).lower() == low:
            return v
    return None


def _retry_after(resp, attempt, rng):
    """Retry-After is a STRING in the header map — cast it (harness13/crawl_fields.py:338-346)."""
    try:
        wait = float(_header(resp, "Retry-After") or 0)
    except (TypeError, ValueError):
        wait = 0.0
    if wait <= 0:
        wait = 2.0 ** attempt
    return wait + rng.random() * JITTER_S


def _request(transport, method, target, *, clock, rng, max_attempts=MAX_ATTEMPTS, body=None,
             params=None):
    """THE ONLY retry layer in this module (PAPERS.md: limit retries to ONE layer, jittered).

    Returns a `Response` for any status the platform actually adjudicated, including a non-429 4xx.
    Raises `AuthExpired` on 401, `DailyLimitReached` on a DAILY 429, `SimTransportError` when the
    attempt budget is spent. It never returns a fabricated response.
    """
    for attempt in range(max_attempts):
        try:
            resp = (transport.post(target, body) if method == "POST"
                    else transport.get(target, params))
        except SimTransportError:
            raise
        except Exception as exc:      # DNS, reset, timeout, TLS. Transient by construction.
            if attempt == max_attempts - 1:
                raise SimTransportError("%s-transport-%s" % (method.lower(), type(exc).__name__))
            clock.sleep(2.0 ** attempt + rng.random() * JITTER_S)
            continue
        code = resp.status_code
        if code == 401:
            raise AuthExpired("401 on %s — session expired; run tools/auth_only.py" % target)
        if code == 429:
            if classify_429(getattr(resp, "text", "")) == "DAILY":
                raise DailyLimitReached("429 DAILY on %s — the allowance resets at 00:00 ET"
                                        % target)
            wait = _retry_after(resp, attempt, rng)
            if wait > MAX_RETRY_AFTER_S:
                raise SimTransportError("429-retry-after-%.0fs" % wait)
            clock.sleep(wait)
            continue
        if code >= 500:
            if attempt == max_attempts - 1:
                raise SimTransportError("%s-%d" % (method.lower(), code))
            clock.sleep(2.0 ** attempt + rng.random() * JITTER_S)
            continue
        return resp
    raise SimTransportError("%s-attempts-exhausted" % method.lower())


def _json(resp):
    try:
        j = resp.json()
    except Exception:
        return {}
    return j if isinstance(j, dict) else {}


# ---------------------------------------------------------------------------- metrics (box 10)
@dataclasses.dataclass(frozen=True)
class Metrics:
    """One alpha's REQ-MG-10 record. Absent is a value here, and it is not zero.

    `sharpe`/`fitness`/`turnover` are `None` when the payload did not carry them; `present` names
    the ones it did. `checks` are the platform's rows verbatim. `missing_required` is the presence
    contract's answer (`gate_lib`): required gates for this region/delay that were never
    adjudicated, so no reader can mistake absence for clearance.

    `date_created` is the platform's `dateCreated` string VERBATIM — unparsed, uninterpreted, and
    NOT known to be the simulation's completion time (see the module docstring). It is `None` when
    the payload did not carry one, and it is never derived from any clock on this machine.
    """
    sharpe: object = None
    fitness: object = None
    turnover: object = None
    checks: tuple = ()
    present: frozenset = frozenset()
    missing_required: tuple = ()
    date_created: object = None

    def check_result(self, name):
        """The platform's result for `name`, or `None` when the check is ABSENT.

        `None` is a THIRD value. It is not a pass and it is not a fail. Callers that compare
        against "PASS"/"FAIL" get False both ways, which is the intended contract.
        """
        for c in self.checks:
            if c.get("name") == name:
                return c.get("result")
        return None


def metrics_from_alpha_json(alpha_json, region=None, delay=None):
    """Pure: build a `Metrics` from a GET /alphas/{id} payload. No network, no I/O.

    Same shape and same purpose as `tools/funnel/fetch_gates.gates_from_alpha_json`; this one also
    carries the three REQ-MG-10 metrics and the presence evidence.
    """
    iss = (alpha_json or {}).get("is") or {}
    settings = (alpha_json or {}).get("settings") or {}
    region = region if region is not None else settings.get("region")
    delay = delay if delay is not None else settings.get("delay")

    checks = tuple({k: c.get(k) for k in ("name", "result", "value", "limit")}
                   for c in (iss.get("checks") or []) if isinstance(c, dict))
    values = {n: iss.get(n) for n in METRIC_NAMES}
    present = frozenset(n for n in METRIC_NAMES if values[n] is not None)

    # THE PRESENCE CONTRACT. The required set comes from its owner, `gate_lib.required_present`
    # (per-region, per-delay); "adjudicated" is gate_lib's own rule, PASS or FAIL and nothing else
    # (gate_lib.py:183-187). `gate_status()` is not called for this because its no-checks branch is
    # written for short-form artifacts and leaves `missing_core` empty; a live GET /alphas payload
    # carrying no checks has adjudicated NOTHING, so every required gate is missing.
    need = set(gate_lib.required_present(region, delay))
    reported = {c.get("name") for c in checks if c.get("result") in ("PASS", "FAIL")}
    # The platform's own clock, carried verbatim. A non-string (or absent) is `None`, never coerced:
    # the point of the field is to be the platform's answer, and a value this machine manufactured
    # would be worse than no value. `present` deliberately does NOT list it — `present` names which
    # of the three REQ-MG-10 METRICS landed, and widening it would change what that word means.
    created = (alpha_json or {}).get("dateCreated")
    return Metrics(sharpe=values["sharpe"], fitness=values["fitness"],
                   turnover=values["turnover"], checks=checks, present=present,
                   missing_required=tuple(sorted(need - reported)),
                   date_created=created if isinstance(created, str) and created else None)


def fetch_metrics(alpha_id, transport, region=None, delay=None, clock=None, rng=None,
                  max_attempts=MAX_ATTEMPTS):
    """REQ-MG-10. Returns a `Metrics`, or `None` when the READ failed.

    `None` means "not read", which is a different fact from "read, and the platform reported no
    sharpe" (a `Metrics` with `sharpe=None`). Both are METRICS-FAIL upstream; keeping them apart
    keeps a failed read out of the evidence base. Raises `AuthExpired` on 401 so the chunk owner
    can mark the whole chunk AUTH-FAIL (REQ-MG-07).
    """
    clock = clock or SystemClock()
    rng = rng or random.Random(0)
    try:
        resp = _request(transport, "GET", "/alphas/%s" % alpha_id, clock=clock, rng=rng,
                        max_attempts=max_attempts)
    except (SimTransportError, DailyLimitReached):
        return None
    if resp.status_code != 200:
        return None
    body = _json(resp)
    if not body:
        return None
    return metrics_from_alpha_json(body, region=region, delay=delay)


# ---------------------------------------------------------------------------- simulate (box 9)
def payload(construction):
    """POST body, copied verbatim from tools/resim_bulk.py:116-120 so the two agree."""
    st = dict(construction.get("settings") or {})
    st.setdefault("language", "FASTEXPR")
    st["visualization"] = False
    return {"type": "REGULAR", "settings": st, "regular": construction.get("formula")}


def payload_many(constructions):
    """The MULTISIM body: a JSON LIST of the same per-child payloads (tools/resim_bulk.py:295).

    `payload` per child and nothing else, so the three mandatory settings fields
    (`pasteurization`, `unitHandling`, `nanHandling`) reach every child by construction rather than
    by a second list that could fall out of step with the single path's.
    """
    return [payload(c) for c in constructions]


def multisim_key(construction):
    """`(delay, region, universe)` — what a multisim group must agree on (MULTISIM_GROUP_KEYS)."""
    st = (construction or {}).get("settings") or {}
    return tuple(st.get(k) for k in MULTISIM_GROUP_KEYS)


def multisim_groups(constructions, size=MULTISIM_CHILDREN):
    """Split constructions into legal multisim groups: consecutive runs of one key, at most `size`.

    ORDER IS PRESERVED AND NOTHING IS SORTED. `tools/resim_bulk.py:210` sorts first because its
    targets arrive mixed; here the caller's order IS the sample — REQ-MG-02 shuffles the grid with
    `random.Random(1234 + offset)` *before* truncating to `limit`, so re-ordering the batch would
    silently re-sample it. A batch that is one segment (the massgen default) yields full groups
    anyway; a mixed one yields short groups at each boundary, which is a legal POST rather than a
    400, and saying so costs nothing.
    """
    if size < 1:
        raise ValueError("multisim group size must be >= 1 (got %r)" % (size,))
    groups, current, key = [], [], None
    for c in constructions:
        k = multisim_key(c)
        if current and (k != key or len(current) >= size):
            groups.append(current)
            current = []
        current.append(c)
        key = k
    if current:
        groups.append(current)
    return groups


@dataclasses.dataclass(frozen=True)
class SimResult:
    """One construction's outcome. `status` is from the closed REQ-MG-20 vocabulary.

    `alpha_id` and `platform_status` survive a METRICS-FAIL on purpose: an alpha that simulated
    COMPLETE and then failed to be READ can be re-read for the cost of one GET. Re-simulating it
    would spend a simulation to recover something the platform already holds.

    `sim_url` survives an interrupted POLL for the same reason and one box earlier: a 401, poll
    exhaustion or a mid-poll DAILY 429 ends OUR attempt, not the simulation. It reaches the journal
    (`as_record`) and `resume_one` polls it back, so the recovery costs GETs and not a simulation.

    `settings` is the construction's simulation settings, carried for the same reason `key` is:
    it is an INPUT, known for every outcome including the ones that never reached the platform, so
    a failed row is as self-describing as a successful one. See `as_record` for what it is for.

    `parent_url` + `child_index` are the MULTISIM handle and they are set from the moment the POST
    is accepted — before any child has been named — so an interruption in that window is still
    recoverable by GET. They are `None` on every single-path outcome, and `as_record` omits them
    there, so a single row is byte-identical to what it was before multisim existed.

    `detect_age_s` + `terminal_poll` are WHEN OUR POLLER NOTICED, not when the platform finished.
    They are `None` on every outcome that never entered a poll loop (a refused POST, OP>64), and
    the module docstring's DETECTION AGE block states in full what they are not. `detect_age_s` is
    a DIFFERENCE of clock readings, never an absolute instant, because the two clocks in this
    package do not share an origin.
    """
    status: str
    platform_status: object = None
    alpha_id: object = None
    metrics: object = None
    err_class: object = None
    polls: int = 0
    sim_url: object = None
    key: object = None
    settings: object = None
    parent_url: object = None
    child_index: object = None
    detect_age_s: object = None
    #: The ABSOLUTE instant our poller saw the terminal status, as `clock.now()` returns it —
    #: `SystemClock.now()` is `time.time()`, so this is an epoch second. It exists because
    #: `detect_age_s` is a DIFFERENCE and `date_created` is an ABSOLUTE stamp: two clocks with no
    #: shared origin cannot be subtracted, so the platform's stamp could not be compared against
    #: anything this repository observed. Journalling this one float makes `detected_at -
    #: parse(date_created)` computable, and TEN rows discriminate the three possibilities: a residual
    #: inside the censoring interval means `dateCreated` is a COMPLETION stamp (and the whole
    #: interval-censoring apparatus retires); a residual equal to `detect_age_s` means it is a
    #: DISPATCH stamp; anything outside means it is neither. MECHANISM: UNKNOWN until those rows
    #: exist — nothing here claims which it is.
    detected_at: object = None
    terminal_poll: object = None

    def __post_init__(self):
        # REQ-MG-20: "Only `EXC` carries an `err_class`; the other three do not, and inventing one
        # for them would fabricate a diagnosis."
        if self.err_class is not None and self.status != STATUS_EXC:
            raise ValueError("only EXC carries an err_class (got %r on %r)"
                             % (self.err_class, self.status))

    @property
    def is_done(self):
        return is_done(self.status)

    @property
    def returns_to_resume(self):
        return returns_to_resume(self.status)

    @property
    def created_simulation(self):
        """Did a simulation object come into existence on the platform for this outcome?

        `pipeline.py` counts the GEM_YIELD denominator off this, and SPEC.md's rule is that a
        refusal which created no simulation is not a dispatched sim. On the single path that is
        exactly "has a `sim_url`". On the multisim path a child can have a live simulation and no
        url of its own yet — the parent was accepted and the poll was interrupted before the
        children were named — and counting those as never-dispatched would understate the
        denominator by a whole group. One property so the two paths cannot answer differently.
        """
        return self.sim_url is not None or self.parent_url is not None

    def as_record(self):
        """A flat journal row, shaped like tools/resim_bulk.py's (`old_id`, `alpha`, `status`,
        then the metrics inline), which is the shape `mg/resume.py` keys on (`old_id`) and
        `mg/survivor.py` reads (`status`, `sharpe`).

        A key is EMITTED ONLY WHEN IT WAS MEASURED. When the metrics read failed there is no
        `sharpe` key at all, because writing one would put a non-measurement in the evidence base
        (tools/resim_bulk.py:444-458). `hard_fail` is deliberately absent: collecting it, with
        `SELF_CORRELATION` excluded, is REQ-MG-11's box, and this one must not pre-empt it.

        `settings` IS THE ROW'S SEGMENT, AND WITHOUT IT THE ROW CANNOT BE SCORED (added 2026-08-12).
        SPEC.md requires the headline gem number to come from `tools/funnel/gates.py::zero_fail`.
        `gates._segment` resolves a row's segment from `row["settings"]` first and otherwise looks
        `old_id` up in the batch files under `state/` — and `mg/generate.py` keys constructions by
        a content sha256 that is written to no batch file. Emitting neither key made every massgen
        row adjudicate as `<unknown segment: old_id not in any targets file>`, which can never pass,
        so the GEM_YIELD NUMERATOR was identically zero for every run whatever the run found.
        Re-derived 2026-08-12 on the 1,835 REAL gems in `state/resim_results.jsonl` rather than on
        one synthetic check set — each row re-keyed with a generate.py-shaped content sha256 and
        re-scored by `gates.zero_fail`:

            as-is, batch file resolves the old_id  -> 1835 / 1835 gems
            fresh content-hash id, no settings     -> 0 / 1835, all '<unknown segment: ...>'
            fresh content-hash id, with settings   -> 1835 / 1835 gems

        The third arm recovers exactly the first arm's set — the same rows, no extras — so
        carrying the segment restores the numerator without widening it.

        Settings are the right carrier rather than registering the id in a batch file: the segment
        is a property of the simulation, the row already knows it, and a second registry is a second
        thing that can go stale. This is NOT a measurement and is not treated as one — it is the
        request this module was handed, copied, not the platform's echo of it. It is emitted for
        every status, because a row that never reached the platform still belongs to a segment. It
        is omitted, never written as `{}` or `null`, when the construction carried none: `_segment`
        falls back to the `old_id` lookup on a falsy value, and an empty dict there would be a
        fabricated segment rather than an absent one.

        `sim_url` IS THE HANDLE ON A SIMULATION THE PLATFORM ALREADY HOLDS (added 2026-08-12), and
        dropping it is what made a mid-poll 401 cost a whole simulation. It is the platform's own
        `Location`, so unlike `settings` it IS an observation, and it is emitted for every row that
        has one — including COMPLETE ones, where it costs a key and buys the ability to re-derive
        the row from the platform without a second registry. A row with no `sim_url` is a row for
        which no simulation is known to exist, which is exactly what `resume_handle` needs to tell
        apart. `_run` sets it on every outcome after the POST is accepted; the outcomes that have
        none are the ones that never created a simulation (a refused POST, OP>64, ABSENT).
        """
        rec = {"old_id": self.key, "status": self.status, "alpha": self.alpha_id}
        if self.settings:
            rec["settings"] = dict(self.settings)   # copy: the journal row must not alias the input
        if self.sim_url is not None:
            rec["sim_url"] = self.sim_url
        # The MULTISIM handle. Emitted only when there IS one, so a single-path row is unchanged;
        # `resume_handle` needs BOTH keys, and an index without a parent names nothing.
        if self.parent_url is not None:
            rec["parent_url"] = self.parent_url
        if self.child_index is not None:
            rec["child_index"] = self.child_index
        if self.err_class is not None:
            rec["err_class"] = self.err_class
        if self.platform_status is not None and self.platform_status != self.status:
            rec["platform_status"] = self.platform_status
        # WHEN OUR POLLER NOTICED — never the platform's completion time. Emitted only for outcomes
        # that actually entered a poll loop, so a row that never reached one carries no key at all
        # rather than a fabricated 0.0 (the presence contract, applied to a measurement of our own).
        if self.detect_age_s is not None:
            rec["detect_age_s"] = self.detect_age_s
        if self.detected_at is not None:
            rec["detected_at"] = self.detected_at
        if self.terminal_poll is not None:
            rec["terminal_poll"] = self.terminal_poll
        if self.metrics is not None:
            rec.update(sharpe=self.metrics.sharpe, fitness=self.metrics.fitness,
                       turnover=self.metrics.turnover,
                       checks=[dict(c) for c in self.metrics.checks],
                       missing_required=list(self.metrics.missing_required))
            # The platform's own string, and the only absolute instant on the row. Emitted only
            # when the payload carried one: an absent stamp must stay absent, because a row that
            # says nothing is recoverable and a row that says `null` looks adjudicated.
            if self.metrics.date_created is not None:
                rec["date_created"] = self.metrics.date_created
        return rec


def _poll_wait(age_s):
    """R1.2 age gate, tools/resim_bulk.py:496 — first probe 90s, then 120s young / 25s old."""
    if age_s <= 0:
        return FIRST_POLL_S
    return OLD_POLL_S if age_s > OLD_AFTER_S else YOUNG_POLL_S


def _location(resp):
    loc = _header(resp, "Location")
    if not loc:
        return None
    return urljoin(API, loc) if loc.startswith("/") else loc


def simulate_one(construction, transport, clock=None, rng=None, max_polls=MAX_POLLS,
                 max_attempts=MAX_ATTEMPTS):
    """REQ-MG-09: submit one formula, poll to completion, return its alpha_id in a `SimResult`.

    COMPLETE and WARNING are both successes and both carry metrics. Every other outcome is a status
    from the RE-RUN vocabulary; none of them is permanent, and none of them is recorded as a
    measurement.
    """
    result = _run(construction, transport, clock=clock or SystemClock(),
                  rng=rng or random.Random(0), max_polls=max_polls, max_attempts=max_attempts)
    # The journal key and the segment both ride on EVERY outcome, so a failure is resumable by the
    # same key as a success and scorable by the same segment. One place, so the two cannot disagree.
    return dataclasses.replace(result,
                               key=construction.get("old_id") or construction.get("id"),
                               settings=construction.get("settings") or None)


def _run(construction, transport, *, clock, rng, max_polls, max_attempts):
    region = (construction.get("settings") or {}).get("region")
    delay = (construction.get("settings") or {}).get("delay")

    try:
        resp = _request(transport, "POST", "/simulations", body=payload(construction),
                        clock=clock, rng=rng, max_attempts=max_attempts)
    except AuthExpired:
        return SimResult(STATUS_AUTH_FAIL)
    except DailyLimitReached:
        return SimResult(STATUS_EXC, err_class="429-DAILY")
    except SimTransportError as exc:
        return SimResult(STATUS_EXC, err_class=exc.reason)
    if resp.status_code not in (200, 201):
        return SimResult(STATUS_EXC, err_class="post-%d" % resp.status_code)
    url = _location(resp)
    if not url:
        # A simulation may nevertheless exist and this module cannot name it. OPEN_QUESTION 4.
        return SimResult(STATUS_EXC, err_class="post-no-location")

    return _poll(url, transport, clock=clock, rng=rng, max_polls=max_polls,
                 max_attempts=max_attempts, region=region, delay=delay)


#: Settings the platform echoes that DISTINGUISH two children of one parent. `MULTISIM_GROUP_KEYS`
#: fixes delay/region/universe across a group, so those can never separate siblings; these are the
#: ones REQ-MG-02 varies and therefore the ones that can.
_CHILD_DISCRIMINATORS = ("decay", "neutralization", "truncation")


def _formula_mismatch(body, expect, expect_settings=None):
    """`err_class` when the platform's echo contradicts what we asked for, else None.

    THIS GUARD IS SILENT WHEN IT CANNOT SEE. The multisim path attributes `children[i]` to
    `constructions[i]` on an assumption this machine cannot verify, so where the platform hands back
    an echo it is compared; where it hands back none, **nothing is checked and nothing is claimed** —
    a `None` here means "no disagreement was observed", never "the mapping is correct".

    IT COMPARES SETTINGS AS WELL AS THE FORMULA, and the reason is measured. Against a replay that
    reversed the child order over 500 corpus children, a formula-only guard refused 438 and let **20
    through carrying a sibling's alpha id and metrics**. Two children differing only in `decay`,
    `neutralization` or `truncation` have the SAME formula — those live in `settings` — and they are
    precisely the axes REQ-MG-02 varies inside one parent. 8.9% of corpus children sit in a
    formula-identical sibling set within their own group of ten, so a formula-only guard covered the
    failure mode it exists for on 91% of the population and missed it on the 9% where a mix-up files
    a real measurement under the WRONG ARM — which corrupts silently, because both rows are genuine.
    """
    if not expect and not expect_settings:
        return None

    if expect:
        got = (body or {}).get("regular")
        if isinstance(got, dict):
            got = got.get("code")
        if isinstance(got, str) and got:
            if "".join(got.split()) != "".join(str(expect).split()):
                return "multisim-child-formula-mismatch"

    if expect_settings:
        echoed = (body or {}).get("settings")
        if isinstance(echoed, dict):
            for key in _CHILD_DISCRIMINATORS:
                want, saw = expect_settings.get(key), echoed.get(key)
                if want is None or saw is None:
                    continue                      # not echoed: unchecked, and nothing claimed
                if str(want) != str(saw):
                    return "multisim-child-settings-mismatch:%s" % key
    return None


def _poll(url, transport, *, clock, rng, max_polls, max_attempts, region, delay, wait_first=True,
          expect_formula=None, expect_settings=None):
    """Poll ONE simulation url to a terminal status. Creates nothing: there is no POST in here.

    Every exit carries `sim_url`, including the three that end the attempt while the simulation is
    still alive (401, DAILY 429, poll exhaustion), because the platform still holds it and the
    handle is what makes the recovery a GET instead of a simulation.

    `wait_first=False` skips only the opening `FIRST_POLL_S` sleep, which exists because a
    just-POSTed simulation has nothing to report yet. A simulation being RESUMED was submitted in an
    earlier attempt — how much earlier is not recorded, so no age is claimed for it; the reason for
    the opening wait simply does not apply. The rest of the cadence is unchanged.
    """
    t0 = clock.now()
    polls = 0

    def _stamp(result):
        """Attach WHEN THIS POLLER NOTICED to an outcome the loop already decided.

        Called on the way out of every exit and NOWHERE else, so it cannot influence which exit was
        taken: it reads `clock.now()` and `polls`, and returns a `dataclasses.replace` copy. The age
        is a DIFFERENCE from this loop's own `t0` — the same quantity `_poll_wait` is already fed on
        every iteration — and it is the detection instant, not the completion instant.
        """
        # Read the clock ONCE and derive both, so the difference and the absolute instant can never
        # disagree by the cost of the call between them.
        seen_at = clock.now()
        return dataclasses.replace(result, detect_age_s=seen_at - t0, terminal_poll=polls,
                                   detected_at=seen_at)

    for _ in range(max_polls):
        if wait_first or polls:
            clock.sleep(_poll_wait(clock.now() - t0))
        polls += 1
        try:
            r = _request(transport, "GET", url, clock=clock, rng=rng, max_attempts=max_attempts)
        except AuthExpired:
            return _stamp(SimResult(STATUS_AUTH_FAIL, polls=polls, sim_url=url))
        except DailyLimitReached:
            return _stamp(SimResult(STATUS_EXC, err_class="429-DAILY", polls=polls, sim_url=url))
        except SimTransportError:
            continue                  # a failed read of a live parent is not a failed simulation
        if r.status_code != 200:
            continue                  # ditto: the parent is still out there, keep polling (bounded)
        body = _json(r)
        st = str(body.get("status") or "").upper()
        if st in DONE_STATUSES:
            wrong = _formula_mismatch(body, expect_formula, expect_settings)
            if wrong is not None:
                # Fail CLOSED. A real measurement filed under the wrong construction is worse than
                # no measurement: it is the arm-mislabelling the pre-registered (base, decay)
                # blocking cannot survive, and it corrupts silently. Spend the row, not the truth.
                return _stamp(SimResult(STATUS_EXC, platform_status=st, polls=polls, sim_url=url,
                                        err_class=wrong))
            # READ THE CLOCK BEFORE `_finish`, NOT AFTER, AND ON ITS OWN LINE. `_finish` issues
            # another GET and `_request` SLEEPS through a 500/429 inside it, so an age taken
            # afterwards folds the cost of READING THE ALPHA into the age at which the SIMULATION
            # was noticed. Two different quantities, and the second is the one this field is for.
            # Written first as `replace(_finish(...), detect_age_s=clock.now() - t0)`, which has
            # exactly that bug because Python evaluates the argument after the call: a 500 on the
            # alpha GET inflated a 90.0s detection to 97.5s through the retry backoff. Caught by
            # `test_a_row_with_no_alpha_read_carries_no_stamp`, not by reading.
            detected_at = clock.now() - t0
            return dataclasses.replace(
                _finish(body, st, transport, region, delay, clock, rng, max_attempts, polls, url),
                detect_age_s=detected_at, terminal_poll=polls)
        if st in ("ERROR", "FAIL", "FAILED"):
            # CHECK THE ORDER HERE TOO. 42 of 500 reversed-order children were never checked at all,
            # because this branch returned before the guard ran. An ERROR filed against the wrong
            # construction is still a wrong attribution: it marks a sibling's formula as having
            # failed, and REQ-MG-20 re-queues it, so the mistake is durable.
            wrong = _formula_mismatch(body, expect_formula, expect_settings)
            if wrong is not None:
                return _stamp(SimResult(STATUS_EXC, platform_status=st, polls=polls, sim_url=url,
                                        err_class=wrong))
            # OPEN_QUESTION 1: the notes have no bucket for a platform-terminal ERROR. The word and
            # the message are the platform's, not a diagnosis invented here.
            why = str(body.get("message") or body.get("detail") or "")[:120]
            return _stamp(SimResult(STATUS_EXC, platform_status=st, polls=polls, sim_url=url,
                                    err_class="sim-%s%s" % (st, (": " + why) if why else "")))
    return _stamp(SimResult(STATUS_EXC, err_class="poll-exhausted-%d" % max_polls, polls=polls,
                            sim_url=url))


def _finish(body, st, transport, region, delay, clock, rng, max_attempts, polls, url):
    """Terminal-success branch: resolve the alpha id, then read its metrics (REQ-MG-10)."""
    alpha_id = body.get("alpha")
    if not alpha_id:
        # COMPLETE/WARNING with no alpha id: there is nothing to read a sharpe from, so this is
        # METRICS-FAIL and returns to resume. It is not a verdict about the formula.
        return SimResult(STATUS_METRICS_FAIL, platform_status=st, polls=polls, sim_url=url)
    return _read_metrics(alpha_id, st, transport, region, delay, clock, rng, max_attempts, polls,
                         url)


def _read_metrics(alpha_id, st, transport, region, delay, clock, rng, max_attempts, polls, url):
    """Box 10 for an alpha the platform already holds. One GET, no simulation.

    Split out of `_finish` so `resume_one` can reach it: a METRICS-FAIL row carries the alpha id for
    exactly this, and re-polling the simulation to re-learn an id we already recorded would be a
    second read of the same fact.
    """
    try:
        m = fetch_metrics(alpha_id, transport, region=region, delay=delay, clock=clock, rng=rng,
                          max_attempts=max_attempts)
    except AuthExpired:
        return SimResult(STATUS_AUTH_FAIL, platform_status=st, alpha_id=alpha_id, polls=polls,
                         sim_url=url)
    if m is None or m.sharpe is None or not m.checks:
        # REQ-MG-10, the whole point of the box: a flake must never convert a good alpha into a
        # permanent failure. alpha_id and platform_status ride along so resume re-READS it.
        #
        # THREE WAYS A READ CAN HALF-LAND, and REQ-MG-10 names box 10's job as "sharpe, fitness,
        # turnover AND the platform check set", so the third belongs here with the other two:
        #   m is None        the GET itself failed. No metrics object exists; `as_record` emits no
        #                    metric key at all, so the non-measurement never enters the evidence.
        #   m.sharpe is None the payload was read and reported no sharpe. REQ-MG-10, verbatim.
        #   not m.checks     the payload was read, carried metrics, and adjudicated NOTHING.
        #                    Absence is not clearance (the presence contract): `missing_required`
        #                    names every required gate for this region/delay, and before this
        #                    guard existed the row was journalled COMPLETE, filed FATE_DONE by
        #                    `resume.classify`, and never looked at again. Inside this module the
        #                    test also covers a payload whose check rows were all non-dict, since
        #                    `metrics_from_alpha_json` drops those in projection — 514 of the
        #                    69,776 real COMPLETE/WARNING rows carry bare gate-NAME strings.
        #
        # NOTHING IS FABRICATED TO SATISFY THIS. `m` is passed through untouched, so the record
        # still says `checks: []` and `missing_required: [...]`; an absent check set does not
        # become an invented one, and it does not become a FAIL either.
        #
        # THE COST, STATED NOT HIDDEN. `pipeline.py` OPEN_QUESTION (a) records that this spine
        # RE-SIMULATES every METRICS-FAIL rather than re-reading it, so if a check set genuinely
        # never lands for an alpha this costs one simulation per run, forever. Measured reach today
        # is 0 rows of 69,776 (see the module docstring), so the expected cost is 0 simulations and
        # the alternative — filing an unadjudicated alpha as finished work — is unrecoverable.
        # `resume_one` now performs that re-read for one GET; it is still the SPINE that must call
        # it, and today nothing does (OPEN_QUESTION 3).
        return SimResult(STATUS_METRICS_FAIL, platform_status=st, alpha_id=alpha_id, metrics=m,
                         polls=polls, sim_url=url)
    return SimResult(st, platform_status=st, alpha_id=alpha_id, metrics=m, polls=polls,
                     sim_url=url)


# ---------------------------------------------------------------- multisim (box 9, one POST, many)
def simulate_many(constructions, transport, clock=None, rng=None, max_polls=MAX_POLLS,
                  max_attempts=MAX_ATTEMPTS, on_post=None):
    """REQ-MG-09 for a GROUP: one POST, one parent handle, one `SimResult` PER CHILD, in order.

    Returns a list as long as `constructions`, whatever happened. Every element is a normal
    `SimResult` in REQ-MG-20's closed vocabulary carrying its OWN `key`, its OWN `settings` and its
    own status — a child is not a summary of its parent — so `as_record()` produces the same journal
    row shape the single path produces and every downstream box reads it unchanged.

    ONE CONSTRUCTION IS THE SINGLE PATH, not a one-element list. `tools/resim_bulk.py:295` sends a
    bare object rather than a list of one and this follows it: whether the platform accepts a
    one-element list is UNKNOWN, and finding out would cost a simulation to learn nothing.

    A MIXED GROUP RAISES rather than POSTing. `tools/resim_bulk.py:207-213` records a mixed-region
    batch rejected 400 — a caller error, deterministic, detectable for free, and one that would
    otherwise cost the whole parent. `multisim_groups` builds lists this accepts.

    `on_post(parent_url, constructions)` FIRES THE INSTANT THE POST RETURNS ITS LOCATION, before a
    single child is polled. That timing is the whole requirement, not a convenience:
    `mg/resume.py::parent_record` is explicit that "a parent line that reaches disk only after the
    poll finishes is worth nothing to the interruption it exists to survive" — the window this
    covers is the one where the platform holds ten simulations and NO child row exists yet, so the
    only thing that can save them is a line written before the polling starts. A caller that does
    not journal one gets today's behaviour and loses that window; nothing here writes to disk.

    An `on_post` that RAISES is not caught. The hook's job is to make the handle durable, and a
    failure to record it is exactly the condition under which continuing would spend ten
    simulations that nothing can recover — the swallowed-exception class MEMORY records.
    """
    constructions = list(constructions)
    if not constructions:
        return []
    if len(constructions) == 1:
        return [simulate_one(constructions[0], transport, clock=clock, rng=rng,
                             max_polls=max_polls, max_attempts=max_attempts)]
    keys = {multisim_key(c) for c in constructions}
    if len(keys) > 1:
        raise ValueError("a multisim group must agree on %s; got %d distinct keys: %r"
                         % (list(MULTISIM_GROUP_KEYS), len(keys), sorted(map(repr, keys))))

    results = _run_many(constructions, transport, clock=clock or SystemClock(),
                        rng=rng or random.Random(0), max_polls=max_polls,
                        max_attempts=max_attempts, on_post=on_post)
    # The journal key and the segment ride on EVERY child, for the same reason and in the same one
    # place as `simulate_one`: a failure must be as resumable and as scorable as a success.
    return [dataclasses.replace(r, key=c.get("old_id") or c.get("id"),
                                settings=c.get("settings") or None)
            for r, c in zip(results, constructions)]


def _fanout(n, template, parent_url=None):
    """One shared-resource outcome, given to all `n` children as their own.

    `parent_url` is passed only when the POST was ACCEPTED. Before that no simulation exists, the
    row must carry no handle, and `resume_handle` must answer `None` so the caller re-simulates.
    """
    if parent_url is None:
        return [dataclasses.replace(template) for _ in range(n)]
    return [dataclasses.replace(template, parent_url=parent_url, child_index=i) for i in range(n)]


def _run_many(constructions, transport, *, clock, rng, max_polls, max_attempts, on_post=None):
    n = len(constructions)
    try:
        resp = _request(transport, "POST", "/simulations", body=payload_many(constructions),
                        clock=clock, rng=rng, max_attempts=max_attempts)
    except AuthExpired:
        return _fanout(n, SimResult(STATUS_AUTH_FAIL))
    except DailyLimitReached:
        return _fanout(n, SimResult(STATUS_EXC, err_class="429-DAILY"))
    except SimTransportError as exc:
        return _fanout(n, SimResult(STATUS_EXC, err_class=exc.reason))
    if resp.status_code not in (200, 201):
        # Includes the 429 CONCURRENT the dispatcher must see: `_request` has already exhausted its
        # retries on it, and the group returns to resume intact. No simulation was created.
        return _fanout(n, SimResult(STATUS_EXC, err_class="post-%d" % resp.status_code))
    url = _location(resp)
    if not url:
        # OPEN_QUESTION 4, multiplied by the group size: up to `n` simulations may exist and this
        # module can name none of them. It says so instead of inventing a handle.
        return _fanout(n, SimResult(STATUS_EXC, err_class="post-no-location"))

    if on_post is not None:
        # BEFORE the first poll, deliberately. See `simulate_many`'s docstring: this is the only
        # moment at which the handle covering all `n` simulations exists and no child row does.
        on_post(url, list(constructions))

    # The parent's own detection age, bracketed rather than returned, so `_poll_parent` keeps its
    # signature and its three existing callers are untouched. It is the SAME interval the loop
    # measures internally: `_poll_parent`'s first statement is `t0 = clock.now()` and nothing sleeps
    # between this reading and that one, so the two origins coincide by construction.
    t_parent = clock.now()
    body, st, polls, failure = _poll_parent(url, transport, clock=clock, rng=rng,
                                            max_polls=max_polls, max_attempts=max_attempts)
    parent_age = clock.now() - t_parent
    if failure is not None:
        # The parent is alive and the platform holds every child. The handle is what makes the
        # recovery GETs instead of `n` simulations. The template was already stamped inside
        # `_poll_parent`, so every child of this fanout reports the one wait they all shared.
        return _fanout(n, failure, parent_url=url)
    return [dataclasses.replace(r, parent_url=url)
            for r in _children_outcomes(constructions, body, st, transport, clock=clock, rng=rng,
                                        max_polls=max_polls, max_attempts=max_attempts,
                                        parent_polls=polls, parent_age=parent_age)]


def _poll_parent(url, transport, *, clock, rng, max_polls, max_attempts, wait_first=True):
    """Poll a MULTISIM parent to a terminal status. Creates nothing: there is no POST in here.

    Returns `(body, status, polls, failure)`. `failure` is a `SimResult` template describing why the
    parent could not be resolved — the same three interruptions the single path has (401, DAILY 429,
    poll exhaustion), each of which ends OUR attempt and not the simulations. When it is `None` the
    body and status are the platform's own terminal answer.

    NOT `_poll`. A parent is not a simulation: it carries no `alpha`, so `_poll` would read a
    terminal parent as COMPLETE-with-no-alpha and file it METRICS-FAIL — a non-answer that would
    reproduce identically on every retry.
    """
    t0 = clock.now()
    polls = 0

    def _stamp(result):
        """As `_poll._stamp`: WHEN THIS POLLER NOTICED the parent, on the way out, deciding nothing.

        A parent fanout template gets its age here and the children inherit it verbatim, which is
        correct — the whole group waited on exactly this one loop.
        """
        return dataclasses.replace(result, detect_age_s=clock.now() - t0, terminal_poll=polls)

    for _ in range(max_polls):
        if wait_first or polls:
            clock.sleep(_poll_wait(clock.now() - t0))
        polls += 1
        try:
            r = _request(transport, "GET", url, clock=clock, rng=rng, max_attempts=max_attempts)
        except AuthExpired:
            return None, None, polls, _stamp(SimResult(STATUS_AUTH_FAIL, polls=polls))
        except DailyLimitReached:
            return None, None, polls, _stamp(SimResult(STATUS_EXC, err_class="429-DAILY",
                                                       polls=polls))
        except SimTransportError:
            continue                  # a failed read of a live parent is not a failed simulation
        if r.status_code != 200:
            continue
        body = _json(r)
        st = str(body.get("status") or "").upper()
        if st in PARENT_TERMINAL:
            return body, st, polls, None
    return None, None, polls, _stamp(SimResult(STATUS_EXC,
                                               err_class="poll-exhausted-%d" % max_polls,
                                               polls=polls))


def _children_of(body):
    """The parent's child list, verbatim (tools/resim_bulk.py:510). Absent reads as empty."""
    return list((body or {}).get("children") or [])


def _child_url(ref):
    """A child reference as a url. The platform hands back an id or a url; both are accepted."""
    if not ref or not isinstance(ref, str):
        return None
    return ref if ref.startswith("http") else "%s/simulations/%s" % (API, ref)


def _child_outcome(ref, transport, *, clock, rng, max_polls, max_attempts, region, delay,
                   expect_formula=None, expect_settings=None):
    """ONE child, resolved on its own handle. NEVER RAISES — that is what isolates the siblings.

    It is the SINGLE path minus the POST: `_poll` with the opening wait skipped, so a child that is
    already terminal (the usual case under a terminal parent) costs exactly one GET, and a child the
    parent finished ahead of is still polled to its own terminal status rather than assumed done.
    Every failure mode of the single path therefore reaches a child unchanged — including the 401
    and the DAILY 429, which `_poll` returns as this child's own outcome instead of unwinding the
    loop over the other nine.
    """
    url = _child_url(ref)
    if url is None:
        # The parent named no simulation at this position. A simulation may or may not exist and
        # this module cannot name it; it does not invent one and it does not blame the formula.
        return SimResult(STATUS_EXC, err_class="multisim-child-absent")
    return _poll(url, transport, clock=clock, rng=rng, max_polls=max_polls,
                 max_attempts=max_attempts, region=region, delay=delay, wait_first=False,
                 expect_formula=expect_formula, expect_settings=expect_settings)


def _children_outcomes(constructions, body, parent_status, transport, *, clock, rng, max_polls,
                       max_attempts, parent_polls, parent_age=None):
    """Every child of a TERMINAL parent, each on its own handle, in request order.

    THE LENGTH GUARD IS FAIL-CLOSED. `tools/resim_bulk.py:510` zips a short children list against
    the full id list and falls back to pairing everything with `None`; here a disagreement refuses
    to attribute ANY child, because attributing `min(len)` of them means every id after the first
    gap is filed under another construction's result. The count is in the `err_class` so the shape
    is diagnosable from the journal without re-running anything.
    """
    n = len(constructions)
    children = _children_of(body)
    if len(children) != n:
        if not children and parent_status not in DONE_STATUSES:
            # A parent that failed before naming any child. The word and the message are the
            # platform's own, exactly as on the single path (OPEN_QUESTION 1).
            why = str((body or {}).get("message") or (body or {}).get("detail") or "")[:120]
            template = SimResult(STATUS_EXC, platform_status=parent_status, polls=parent_polls,
                                 err_class="sim-%s%s" % (parent_status,
                                                         (": " + why) if why else ""))
        else:
            template = SimResult(STATUS_EXC, platform_status=parent_status or None,
                                 polls=parent_polls,
                                 err_class="multisim-children-%d-of-%d" % (len(children), n))
        # No child loop ran, so the only wait was the parent's and `terminal_poll` is its index.
        template = dataclasses.replace(template, detect_age_s=parent_age,
                                       terminal_poll=parent_polls)
        return [dataclasses.replace(template, child_index=i) for i in range(n)]

    out = []
    for i, construction in enumerate(constructions):
        settings = construction.get("settings") or {}
        result = _child_outcome(children[i], transport, clock=clock, rng=rng, max_polls=max_polls,
                                max_attempts=max_attempts, region=settings.get("region"),
                                delay=settings.get("delay"),
                                expect_formula=construction.get("formula"),
                                expect_settings=construction.get("settings"))
        # `polls` is a COST, so the parent's polls are charged to the children that shared them.
        #
        # `detect_age_s` IS SUMMED FOR THE SAME REASON, and it is the reason the field means the
        # same thing on both paths: a child is only polled once its parent is already terminal, so
        # its own loop measures ~one GET and the parent's loop did all the waiting. Summed, the
        # field is launch->detection end to end, matching the single path.
        #
        # `terminal_poll` IS NOT SUMMED. It is an INDEX INTO A CADENCE GRID, and two loops do not
        # share one; adding them would produce a number that indexes nothing and would destroy the
        # censoring interval the field exists to make recoverable. It stays the child's own index,
        # which leaves the parent's recoverable as `polls - terminal_poll` — and THAT is the index
        # into the grid that actually did the waiting.
        out.append(dataclasses.replace(result, child_index=i,
                                       polls=result.polls + parent_polls,
                                       detect_age_s=_sum_age(parent_age, result.detect_age_s)))
    return out


def _sum_age(parent_age, child_age):
    """Parent + child detection age, where ABSENT stays absent rather than becoming zero.

    Either side is `None` when that loop never ran or was never measured. Treating a `None` as 0.0
    would report a wait that was not observed — the presence contract, applied to this module's own
    measurement — so the sum is `None` unless both halves exist.
    """
    if parent_age is None or child_age is None:
        return None
    return parent_age + child_age


# ------------------------------------------------------- resume by READING (no POST, no new sim)
HANDLE_ALPHA = "alpha"        # the platform finished and named the alpha: one GET /alphas/{id}
HANDLE_SIM = "simulation"     # the platform holds a simulation: poll /simulations/{id}, no POST
HANDLE_PARENT = "multisim"    # the platform holds a multisim parent: poll it, take child i, no POST


def resume_handle(record):
    """What a journal row can be recovered WITH, or `None` when it can only be re-simulated.

    Returns `(HANDLE_ALPHA, alpha_id)`, `(HANDLE_SIM, sim_url)` or `(HANDLE_PARENT, parent_url)`.
    The alpha id is preferred and only when the row ALSO carries the platform's own DONE verdict,
    because that pair is a complete description of a finished simulation — the read costs one GET
    and waits for nothing. The simulation url is the next fallback, and it is the one that covers a
    poll interrupted before any alpha id existed.

    **THE VALUE IS ALWAYS A NON-EMPTY STRING.** `mg/resume.py::_pair` refuses anything else — it
    raises on a non-string value and `_handle_from` deliberately does not catch detector errors —
    so a `(url, index)` pair here would crash `resume.plan` on the first multisim row. Verified by
    execution 2026-08-12, not by reading. The child index therefore rides on the RECORD, which
    `resume_one` already receives whole and `resume.Handle.record` preserves.

    THE MULTISIM PARENT IS A DISTINCT KIND, not a `sim_url`, and TWO shapes reach it:
      * a CHILD row that knows its parent but not its own child url (`parent_url` + `child_index`);
      * a PARENT LINE — `mg/resume.py::parent_record`, `{"sim_url": ..., "members": [...]}` — which
        describes a POST covering N constructions and is checked FIRST, before `sim_url`.
    Folding either into `HANDLE_SIM` is a TRAP, not a shortcut: `_poll` on a parent reads its
    terminal-with-no-`alpha` body as METRICS-FAIL, so the retry re-derives the same non-answer every
    time — cheap on each pass and never finishing. A parent line resolving to `HANDLE_SIM` is
    exactly what this function did until it was executed against `resume.parent_record` and the trap
    came back.

    NOTHING IS INFERRED FROM ABSENCE. A row with an alpha id but no COMPLETE/WARNING anywhere on it
    is NOT treated as finished — its verdict was never observed, and assuming one would fabricate
    the platform's answer. Such a row falls through to its `sim_url`, and to `None` if it has none.

    `None` is a real answer and the caller must act on it: OP>64, a refused POST and an ABSENT row
    have no handle because no simulation was ever created for them.
    """
    rec = record or {}
    alpha = rec.get("alpha")
    verdict = rec.get("platform_status") or rec.get("status")
    if isinstance(alpha, str) and alpha and is_done(verdict):
        return (HANDLE_ALPHA, alpha)
    # A PARENT LINE FIRST. It carries `sim_url` like a construction row does, so testing `sim_url`
    # ahead of `members` would hand back the trap for every parent line in the journal.
    url = rec.get("sim_url")
    if is_parent_line(rec):
        return (HANDLE_PARENT, url) if isinstance(url, str) and url else None
    if isinstance(url, str) and url:
        return (HANDLE_SIM, url)
    parent, index = rec.get("parent_url"), rec.get("child_index")
    if isinstance(parent, str) and parent and _child_index_of(rec) is not None:
        return (HANDLE_PARENT, parent)
    return None


def is_parent_line(record):
    """True when this record describes a POST (it has `members`) rather than one construction.

    `mg/resume.py::MEMBERS_FIELD` is a RESERVED name and that module owns it: a line with `members`
    is never read as a construction row there, and nothing this module writes ever carries it —
    `as_record()` emits no such key. Read here, never written, so the two ends cannot drift.
    """
    v = (record or {}).get("members")
    return isinstance(v, (list, tuple)) and bool(v)


def _child_index_of(record):
    """This row's position in its parent's POST body, or `None` when it does not name one.

    `True` is not an index. `bool` is an `int` subclass, so a record carrying `child_index: True`
    would otherwise resolve to position 1 and recover a sibling's simulation under this row's key.
    """
    index = (record or {}).get("child_index")
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        return None
    return index


def resume_one(record, transport, clock=None, rng=None, max_polls=MAX_POLLS,
               max_attempts=MAX_ATTEMPTS):
    """Continue a journal row from its handle, spending ZERO simulations. `None` when it has none.

    This is the READ half of REQ-MG-03's "must not re-simulate finished work", applied to work the
    platform has STARTED and not only to work it has finished. There is no POST on this path:
    `_run` owns the module's only one and nothing here calls it.

      HANDLE_ALPHA  ->  box 10 again for that alpha id (one GET), at the verdict the row recorded.
      HANDLE_SIM    ->  the poll loop again on that url, opening wait skipped, then box 10.
      HANDLE_PARENT ->  poll the multisim parent, take THIS row's child, then the two above. Two
                        GETs instead of one, and still no POST: the whole group is recovered one
                        row at a time, each row independently, each for reads.

    The result is a normal `SimResult` in the closed REQ-MG-20 vocabulary, carrying the row's own
    `old_id` and `settings` so the retry journals over the same key in the same segment. A second
    interruption produces another row with another handle, so this is repeatable and each repeat
    costs GETs, never a simulation.

    A record whose status is already COMPLETE/WARNING is not refused here — re-reading a finished
    alpha is a legal, cheap thing to do — but deciding WHICH rows to resume belongs to
    `mg/resume.py`, and this module does not second-guess it.
    """
    handle = resume_handle(record)
    if handle is None:
        return None
    kind, value = handle
    clock = clock or SystemClock()
    rng = rng or random.Random(0)
    settings = (record or {}).get("settings") or None
    region = (settings or {}).get("region")
    delay = (settings or {}).get("delay")

    if kind == HANDLE_ALPHA:
        verdict = record.get("platform_status") or record.get("status")
        result = _read_metrics(value, str(verdict).upper(), transport, region, delay, clock, rng,
                               max_attempts, 0, record.get("sim_url"))
    elif kind == HANDLE_PARENT:
        index = _child_index_of(record)
        if index is None:
            # A PARENT LINE names N constructions and this function answers for ONE. Returning
            # `None` would read as "no handle" and send every member to a fresh simulation while a
            # live handle covered all of them — the exact cost `resume.parent_groups()` exists to
            # avoid. Raise, and name the function that spends it.
            raise ValueError(
                "this record is a multisim PARENT (%r members) and names no child_index; "
                "spend it with resume_group(record, transport, constructions=...), which polls the "
                "parent ONCE for every member" % (len((record or {}).get("members") or ()),))
        result = _resume_child(value, index, transport, clock=clock, rng=rng, max_polls=max_polls,
                               max_attempts=max_attempts, region=region, delay=delay,
                               expect_formula=record.get("formula"),
                               expect_settings=record.get("settings"))
    else:
        result = _poll(value, transport, clock=clock, rng=rng, max_polls=max_polls,
                       max_attempts=max_attempts, region=region, delay=delay, wait_first=False)
    return _no_detection_on_resume(
        dataclasses.replace(result,
                            key=record.get("old_id") or record.get("id"),
                            settings=settings))


def _no_detection_on_resume(result):
    """Clear `detect_age_s`/`terminal_poll` on every row a RESUME produces. The invariant:

        the pair is present IFF this row's simulation was dispatched AND detected in the same run.

    WHY THE NUMBER IS DELETED RATHER THAN LABELLED. `_poll` stamps unconditionally, so a resumed
    row would otherwise carry a real reading of the wrong quantity. The simulation was POSTed in an
    earlier attempt whose instant is recorded nowhere, and the resume skips the opening wait, so a
    row recovered from an already-finished simulation reports `detect_age_s = 0.0` — which is
    indistinguishable in the journal from a simulation that completed instantly. The record carries
    no other key that separates a resumed row from a dispatched one, so a warning in a docstring
    could not be acted on by the analysis that reads the file. This repository's dominant bug class
    is a transient condition recorded as a permanent fact (8 confirmed cases in MEMORY); a 0.0 here
    is that shape exactly, and it would pile up at the left edge of any latency distribution built
    from this field and read as a fast-completion mode.

    `polls` is untouched and still records what the recovery COST, which is the question a resumed
    row can honestly answer.

    LATENT, NOT LIVE, AND SAID SO. `resume_one` is called by nothing today (OPEN_QUESTION 3), so no
    row of this shape has ever reached a journal and this deletes no existing data.
    """
    return dataclasses.replace(result, detect_age_s=None, terminal_poll=None)


def resume_group(record, transport, constructions=None, members=None, clock=None, rng=None,
                 max_polls=MAX_POLLS, max_attempts=MAX_ATTEMPTS):
    """Spend a PARENT LINE's handle ONCE for many members. `{member key: SimResult}`, no POST.

    THIS IS THE FUNCTION `mg/resume.py::Plan.parent_groups` DEFERS TO, verbatim: "the caller can
    pair members with children positionally if the platform's answer is positional — whether it IS
    positional is `mg/simulate.py`'s question, not this module's." The answer is: it is TAKEN to be
    positional, `members[i]` <-> `children[i]`, on the same UNVERIFIED assumption the dispatch path
    runs on (see MULTISIM in the module docstring and OPEN_QUESTION 5). Both fail-closed guards
    apply here too — a length disagreement refuses every member, and a formula the platform
    contradicts refuses that member.

    ONE PARENT POLL FOR TEN MEMBERS is the whole reason this exists beside `resume_one`: ten members
    resumed one at a time cost ten parent polls for one parent's answer.

    `constructions` is a `{key: construction}` mapping and is how a recovered row keeps its SEGMENT.
    A parent line carries `sim_url` and `members` and NOTHING per-member, so without it every
    recovered row would land with `settings=None` and `gates.zero_fail` would score the whole group
    `<unknown segment>` — the failure SPEC.md's numerator was identically zero to. It is optional
    only because a caller that genuinely has no constructions should get rows rather than an
    exception; what it costs is stated here rather than discovered later.

    `members` restricts the answer to the keys the caller still wants (`parent_groups()` reports
    todo keys, which is a SUBSET when some siblings already finished). Positions always come from
    the parent line's OWN `members` list, never from the requested subset — pairing a subset
    positionally against the children is how member 7 gets filed under child 2's simulation.
    """
    record = record or {}
    if not is_parent_line(record):
        raise ValueError("resume_group needs a parent line (a record with `members`); got keys %r"
                         % (sorted(record),))
    handle = resume_handle(record)
    if handle is None:
        return {}
    all_members = list(record.get("members") or ())
    wanted = all_members if members is None else [k for k in all_members if k in set(members)]
    constructions = constructions or {}
    clock = clock or SystemClock()
    rng = rng or random.Random(0)
    parent_url = handle[1]

    body, st, polls, failure = _poll_parent(parent_url, transport, clock=clock, rng=rng,
                                            max_polls=max_polls, max_attempts=max_attempts,
                                            wait_first=False)
    out = {}
    for key in wanted:
        index = all_members.index(key)
        construction = constructions.get(key) or {}
        settings = construction.get("settings") or None
        if failure is not None:
            result = dataclasses.replace(failure, parent_url=parent_url, child_index=index)
        else:
            children = _children_of(body)
            if len(children) != len(all_members):
                result = SimResult(STATUS_EXC, platform_status=st or None, polls=polls,
                                   parent_url=parent_url, child_index=index,
                                   err_class="multisim-children-%d-of-%d"
                                             % (len(children), len(all_members)))
            else:
                child = _child_outcome(children[index], transport, clock=clock, rng=rng,
                                       max_polls=max_polls, max_attempts=max_attempts,
                                       region=(settings or {}).get("region"),
                                       delay=(settings or {}).get("delay"),
                                       expect_formula=construction.get("formula"))
                result = dataclasses.replace(child, parent_url=parent_url, child_index=index,
                                             polls=child.polls + polls)
        out[key] = _no_detection_on_resume(dataclasses.replace(result, key=key, settings=settings))
    return out


def _resume_child(parent_url, index, transport, *, clock, rng, max_polls, max_attempts, region,
                  delay, expect_formula=None, expect_settings=None):
    """One child of a live multisim parent, by index. GETs only; the parent is never re-POSTed.

    Its OWN row and no sibling's: the parent is polled, this index is taken, and nothing is written
    for the other nine — each of them carries the same handle and recovers itself. That keeps a
    resume as isolated as the original dispatch, and it keeps `resume_one` a per-row function.

    The handle survives every failure here, so a second interruption is resumable exactly like the
    first (`parent_url` and `child_index` are re-stamped on every outcome, including the ones from
    `_poll_parent` that never saw a child).
    """
    body, st, polls, failure = _poll_parent(parent_url, transport, clock=clock, rng=rng,
                                            max_polls=max_polls, max_attempts=max_attempts,
                                            wait_first=False)
    if failure is not None:
        return dataclasses.replace(failure, parent_url=parent_url, child_index=index)
    children = _children_of(body)
    if index >= len(children):
        # The parent finished and does not name this position. Fail closed, exactly as the dispatch
        # path does on a length disagreement: taking some other child would file this construction's
        # row under another construction's simulation.
        return SimResult(STATUS_EXC, platform_status=st or None, polls=polls,
                         parent_url=parent_url, child_index=index,
                         err_class="multisim-child-%d-of-%d" % (index, len(children)))
    result = _child_outcome(children[index], transport, clock=clock, rng=rng, max_polls=max_polls,
                            max_attempts=max_attempts, region=region, delay=delay,
                            expect_formula=expect_formula)
    # No detection age is composed here: `resume_one` clears the pair on every row it returns, and
    # the reason is at `_NO_DETECTION_ON_RESUME`.
    return dataclasses.replace(result, parent_url=parent_url, child_index=index,
                               polls=result.polls + polls)


# LADDER GROUND TRUTH, read off state/ladder_live.jsonl rather than recalled:
#     control  1 single  parent /  1 child   ACCEPTED
#     rung     8 singles          /  8       ACCEPTED (7 more)
#     rung    16 singles                     REFUSED, 429 CONCURRENT, 0 accepted
#     phase B  1 multisim parent  / 10       ACCEPTED
#     19 simulations attempted, 18 accepted.
# REFUTED 2026-08-13 by reading `experiments/evidence/ladder_live.jsonl` directly: the rungs step by ONE, not by 8 — the file records `alive_before` 0,1,2,3,4,5,6,7 all answered 201 and `alive_before: 8` answered 429. The refusal is PINNED at 8 concurrent parents and is printed in the log, not inferred. The [9, 16] interval was an over-correction that turned a pinned measurement into a loose one, and it spread to six files.
#
# (Superseded text: 'the rungs step by 8, so the ceiling is located only to [9, 16]'.) No
# single number names it, and any text saying "refused at 8" or "refused at 16" is quoting a RUNG.
# The cost was 19 simulations, not 8 — an earlier brief said 8 and four modules copied it.
