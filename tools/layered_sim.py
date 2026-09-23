#!/usr/bin/env python3
"""Draw layered alphas from the pre-built pools, simulate them, and scrape every result.

The operator's division of labour (Khoa, 2026-08-13): the pools are pre-built, "việc bạn chỉ là sim
và cào". So this file draws, POSTs, polls, and records. It composes nothing and decides nothing about
structure — `layered_alpha.py` owns that.

WHAT IT RECORDS, and why the list is long. The previous generation's journal kept `old_id` (a
sha256, not invertible) and threw the FORMULA away, so 2,639 simulated rows could not be traced back
to the structure that produced them and the whole batch was unanalysable after the fact. Every row
here carries the formula, the per-leg draw, the leg count, the chain depth, the leaf and its
description, and whether a close/open carrier was present — because the question this experiment
exists to answer is *which structures work*, and that question is unanswerable from metrics alone.

**IT NEVER SUBMITS.** A simulation is cheap and repeatable; a submission is one irreversible POST per
alpha and a 403 spends it forever. This module has no submit path, and a test walks its own AST to
prove it.

THE SHAPE: 8 MULTISIM PARENTS x 10 CHILDREN = 80 IN FLIGHT.
  **OPERATOR-STATED by Khoa 2026-08-12. THIS REPOSITORY HAS NOT MEASURED IT.** Nothing here has run
  8x10 to completion, so the 80 is the shape we are told the platform allows, not a shape observed
  to be accepted. It is two parameters (`--concurrency`, `--children`), never a constant, so the
  round that spends the simulations can move either one.

  What this file did before: one POST per simulation at `--concurrency 8`, i.e. 8 in flight — a
  tenth of that shape. What the change does NOT establish is any throughput number; see
  `simulate.py`'s MULTISIM block, which is explicit that per-child latency under a loaded parent is
  UNKNOWN and that the 10x must not be quoted as an observed speed-up. MECHANISM AND RATE: UNKNOWN
  until a live round measures them.

  A GROUP MUST AGREE ON `MULTISIM_GROUP_KEYS` = (delay, region, universe); `decay`, `neutralization`
  and `truncation` may vary within one parent. Every alpha this file draws shares one `SETTINGS`
  dict today, so every group is trivially legal — the batch is routed through `multisim_groups`
  anyway, so that stays true by construction rather than by the current value of one dict.
"""
import argparse
import collections
import json
import os
import pathlib
import random
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))                     # append, never insert: must not shadow stdlib

import layered_alpha as LA                                             # noqa: E402
import frameworks as FW                                                # noqa: E402
import gap_2x2 as GAP                                                  # noqa: E402
import climb as CLIMB                                                  # noqa: E402
#: THE MULTISIM PIECES ARE IMPORTED, NOT RE-WRITTEN. `mg/simulate.py` already carries the grouping
#: rule and the child-order guard, and both are backed by measurements this file has no way to
#: repeat: a mixed-region batch rejected 400 (`tools/resim_bulk.py:207-213`), and a replay over 500
#: corpus children in which a FORMULA-ONLY guard refused 438 and let 20 through carrying a sibling's
#: alpha id and metrics. A second copy of either would be a second thing that can drift away from
#: the evidence, so `_formula_mismatch` is imported despite the underscore.
from harness13.massgen.mg.simulate import (                            # noqa: E402
    MULTISIM_CHILDREN, MULTISIM_GROUP_KEYS, PARENT_TERMINAL,
    _formula_mismatch as child_mismatch, multisim_groups, payload_many)

POOLDIR = ROOT / "state/layered"
OUTDIR = ROOT / "state/layered/runs"
API = "https://api.worldquantbrain.com"

SETTINGS = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1,
    "decay": 0, "neutralization": "SUBINDUSTRY", "truncation": 0.05,
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
    "language": "FASTEXPR", "visualization": False,
}
#: THE SETTINGS ARM. `decay=0` + SUBINDUSTRY was MY REASONING, never a measurement: "the structure
#: carries its own smoothing, so a settings-level decay would smooth an already-smoothed signal".
#: Plausible, and it is now the leading suspect for the largest gap anyone has measured here —
#: this generator screens **0 / 129** while the older `resim` corpus screens **4,664 / 69,659 =
#: 6.70%**, and that corpus ran `decay 6-14` with `STATISTICAL`/`INDUSTRY` neutralization. Under a
#: true 6.7%, seeing 0 of 129 has p = 1.3e-4.
#:
#: Four candidates fit that gap — selection (resim is curated), settings, grammar, field pool — and
#: NONE has been tested. This arm tests settings, randomised per alpha inside one batch so market
#: regime, quota state and session age cannot be the explanation.
#:
#: MECHANISM: UNKNOWN for why either setting would matter. The arm measures whether it does.
SETTINGS_ARMS = {
    "s_flat":   {"decay": 0,  "neutralization": "SUBINDUSTRY"},   # today's, and my reasoning
    "s_resim":  {"decay": 10, "neutralization": "INDUSTRY"},      # the corpus that screens 6.70%
    "s_stat":   {"decay": 6,  "neutralization": "STATISTICAL"},
    "s_slow":   {"decay": 14, "neutralization": "INDUSTRY"},
}

#: MAX_POLLS RAISED 220 -> 700 ON 2026-08-14, FROM A MEASUREMENT, NOT A GUESS. At 8 s a poll, 220
#: put the ceiling at 29.3 minutes. A gap-2x2 parent hit 221 polls at age 1862.7 s -- 31 minutes --
#: and was abandoned AFTER its ten simulations had already been spent, so the quota was gone and the
#: rows were not collected. 700 puts the ceiling at 93 minutes. Nothing is lost when it does trip:
#: an abandoned parent journals `parent_url`/`sim_url` and the recovery path harvests it later at
#: zero quota cost (1,496 rows were recovered that way once). The ceiling exists to stop a genuinely
#: stuck handle, not to time out a slow one.
#: WHY THAT PARENT WAS SLOW: MECHANISM UNKNOWN. The corpus formulas in the RF cells are far heavier
#: expressions than ours, which is a candidate and not a finding -- no experiment separated it from
#: platform load at that hour.
POLL_FIRST_S, POLL_S, MAX_POLLS = 12.0, 8.0, 700

#: HOW LONG A HANDLE MUST HAVE EXISTED BEFORE IT IS WORTH ASKING ABOUT. A simulation takes ~335 s
#: (mean `detect_age_s` over 86 rows), so polling one 12 s after the POST asks a question whose
#: answer cannot have changed. The old loop paid `POLL_FIRST_S` INSIDE each reap, serially, on one
#: thread: with 8 parents that is ~96 s of pure sleep per cycle EVEN IF ALL 8 ARE ALREADY DONE, and
#: it caps the runner at roughly 300 rows/hour at ANY platform speed. Measured throughput was 80.
#: The wait is now measured from each handle's OWN post time and the sleep is shared, so eight
#: handles wait once between them instead of eight times in series.
MIN_HANDLE_AGE_S = 60.0
IDLE_SLEEP_S = 5.0

#: WALL-CLOCK CEILING FOR ONE ROUND, from a hang that `timeout=` did not catch. A climb round sat
#: for 43 minutes with ONE second of CPU, one ESTABLISHED socket to the API, and no journal write --
#: while every parent it had posted was already harvested, so there was nothing left to wait for.
#: `requests`' timeout is a between-bytes timeout, not a total one, so a connection that dribbles
#: or stalls mid-read can outlive it.
#:
#: Passing the ceiling is NOT an error and must not lose the round: the loop stops reaping, and
#: everything already journalled is still folded into the climb state. Losing that fold is what made
#: the hang expensive -- the round's 140 usable rows had to be folded back in by hand.
#: MECHANISM: UNKNOWN for the stall itself. This bounds the damage; it does not explain it.
MAX_ROUND_S = 75 * 60


def load_pools():
    a = json.loads((POOLDIR / "pool_a.json").read_text())
    b = json.loads((POOLDIR / "pool_b.json").read_text())
    c = json.loads((POOLDIR / "pool_c.json").read_text())
    return a, b, c


def session():
    """The VPS cookie jar. No credentials are read and no /authentication call is made here —
    a dead session must surface as a 401 the caller reports, not as a silent re-auth."""
    import pickle
    import requests
    s = requests.Session()
    for p in (ROOT / "state/wq_cookies.pkl", pathlib.Path("/opt/wq/state/wq_cookies.pkl")):
        if p.exists():
            s.cookies.update(pickle.load(open(p, "rb")))
            return s
    raise SystemExit("no cookie jar found")


def keep_jar_fresh(s, path=None, interval=20.0):
    """Swap fresh cookies from the jar file into the LIVE session, in place, mid-round.

    The round's Session object loads the jar ONCE at start and holds it in memory, so before this
    existed a tap that landed mid-round changed nothing: the round kept posting the dead cookie to
    its end. Measured cost on 2026-08-18: the 12:49 round started with a live session, outlived it,
    and lost 29 of the 31 rows carrying the new operators to AUTH-FAIL/POST-401 -- ~22% of that
    round's quota. Rounds run to 53 minutes against a session that lives exactly 4h and cannot be
    renewed, so any round can straddle an expiry.

    `Session.cookies.update()` REPLACES a same-name cookie rather than duplicating it (verified
    2026-08-18 against requests' cookiejar), and every request in this process goes through this
    one Session object -- so the swap is one in-place update, no call site changes.

    Khoa ordered this on 2026-08-28 ("bo may hoat dong ko hoan thien va tu dong hoan toan") after
    ticking the design on 08-18. The thread is a daemon: it must never keep the process alive.
    """
    import pickle
    import threading
    cand = [pathlib.Path(path)] if path else [ROOT / "state/wq_cookies.pkl",
                                              pathlib.Path("/opt/wq/state/wq_cookies.pkl")]
    jar = next((p for p in cand if p.exists()), None)
    if jar is None:
        return None
    seen = [jar.stat().st_mtime]

    def _watch():
        while True:
            time.sleep(interval)
            try:
                m = jar.stat().st_mtime
                if m == seen[0]:
                    continue
                with open(jar, "rb") as fh:
                    s.cookies.update(pickle.load(fh))
                seen[0] = m
                print("[auth] jar changed on disk -> swapped into the live session", flush=True)
            except Exception as exc:                    # noqa: BLE001
                # INSTRUMENTED, never silent -- a bare pass here is how a missing import hid for
                # days in this repository. The watcher must survive a half-written jar, so it
                # reports and keeps watching rather than dying on the first bad read.
                print("[auth] jar watcher: %r" % exc, flush=True)

    t = threading.Thread(target=_watch, daemon=True, name="jar-watcher")
    t.start()
    return t


def draw_frameworks(a, b, c, rng, n):
    """n distinct alphas, frameworks dealt BALANCED within this one batch.

    This is the framework path, parallel to `draw`'s 2^6 factorial path and never mixed with it: an
    alpha carries a cell or a framework, not both, so every journalled row is assignable to exactly
    one experiment.

    THE SETTINGS ARM STILL VARIES `decay`, but a framework that DECLARES a neutralization owns it
    (see `frameworks.settings_for`). That means framework and neutralization are deliberately
    CONFOUNDED for `s1_neut` and `subu` -- which is the point for `s1_neut`, whose prediction is
    about the setting. Its primary test is absolute ("zero alphas above 0.5") and survives the
    confound; its secondary comparison against `flat` does not, and must be reported as confounded.
    """
    seen, out = set(), []
    picks = FW.assign(rng, n * 3)          # spare picks for the dedupe guard, still block-balanced
    guard = 0
    while len(out) < n and guard < len(picks):
        name = picks[guard]
        guard += 1
        f, m = FW.build(FW.BY_NAME[name], a, b, c, rng)
        if f in seen:
            continue
        seen.add(f)
        m["settings_arm"] = rng.choice(sorted(SETTINGS_ARMS))
        m["carrier"] = m["carrier_in_formula"]      # the key `run`/`_write` already read
        out.append((f, m))
    return out


def draw(a, b, c, rng, n, assigner=None, pool_c_kept=None, gate_pool=None):
    """n distinct alphas, each carrying its own 2^4 factorial cell.

    WITHOUT `assigner` the composer falls back to a legacy-default cell and a whole round journals
    only TWO distinct cells out of sixteen -- the factorial would be assignable in principle and
    unassigned in fact, which is the shape that makes four changes land as one unattributable
    number. Khoa ratified attribution over speed on 2026-08-13, so the assigner is wired here.
    """
    seen, out = set(), []
    guard = 0
    while len(out) < n and guard < n * 20:
        guard += 1
        # The cell kwargs are passed ONLY when a caller supplied them. `compose` is monkeypatched by
        # a plain lambda in several tests, and handing it keywords it never declared turned 16 of
        # them red for a reason that had nothing to do with the behaviour under test.
        kw = {}
        if assigner is not None:
            kw = {"assigner": assigner, "pool_c_kept": pool_c_kept, "gate_pool": gate_pool}
        f, m = LA.compose(a, b, c, rng, **kw)
        if f in seen:
            continue
        seen.add(f)
        m["settings_arm"] = rng.choice(sorted(SETTINGS_ARMS))
        out.append((f, m))
    return out


def settings_for(arm, framework=None):
    """Today's settings with the arm's overrides applied, then the framework's declaration on top.

    Order matters and is deliberate: a framework that declares a neutralization is making a claim
    ABOUT that neutralization (`s1_neut`'s whole prediction is the 0.5 cap the setting produces), so
    it must win over the arm. A FREE framework changes nothing and the arm owns both fields.
    """
    st = dict(SETTINGS)
    st.update(SETTINGS_ARMS[arm])
    if framework:
        st = FW.settings_for(FW.BY_NAME[framework], st)
    return st


def settings_for_profile(profile):
    """`SETTINGS` with a gap-2x2 profile applied. The settings ARM is deliberately not consulted:
    the profile IS the factor under test, and letting the arm also move decay would confound the
    two."""
    return GAP.settings_for(profile, SETTINGS)


def post_one(s, formula, arm=None):
    body = {"type": "REGULAR",
            "settings": settings_for(arm) if arm else dict(SETTINGS),
            "regular": formula}
    r = _post_patient(s, API + "/simulations", body, timeout=40)
    return r.status_code, r.headers.get("Location"), (r.text or "")[:300]


def post_many(s, group):
    """One POST, up to `--children` simulations. The body is a JSON LIST of per-child payloads.

    `payload_many` is the single path's `payload` applied per child, so the three mandatory settings
    fields (`pasteurization`, `unitHandling`, `nanHandling` — added after the platform 400ed without
    them) reach every child by construction and cannot fall out of step with `post_one`'s body.

    A ONE-ELEMENT GROUP DOES NOT COME HERE. `tools/resim_bulk.py:295` sends a bare object for one
    and whether the platform accepts a list of one is UNKNOWN; finding out would spend a simulation
    to learn nothing. `run` routes a group of one through `post_one`.
    """
    body = payload_many(group)
    # PER-CHILD SETTINGS. `MULTISIM_GROUP_KEYS = (delay, region, universe)` fixes those three across
    # a parent and leaves `decay`/`neutralization` free to vary WITHIN it -- precisely the axis this
    # arm varies. So randomisation stays at the ALPHA level; group-level assignment would give ten
    # children one draw and cut the effective sample size to a tenth of the row count.
    # NO ARM OVERRIDE HERE ANY MORE. `payload_many` builds each child from its construction's own
    # `settings`, which now already carries the arm, so the POST body and the guard's expectation
    # are the same object's content by construction rather than by two code paths agreeing.
    r = _post_patient(s, API + "/simulations", body, timeout=40)
    return r.status_code, r.headers.get("Location"), (r.text or "")[:300]


def child_url(ref):
    """A child reference as a url. The platform hands back an id or a url; both are accepted."""
    if not ref or not isinstance(ref, str):
        return None
    return ref if ref.startswith("http") else "%s/simulations/%s" % (API, ref)


def poll_parent(s, url, sleep=time.sleep, wait_first=True, deadline=None):
    """(status, children, polls, message) for a MULTISIM parent.

    NOT `poll`. A parent is not a simulation: it carries no `alpha`, so `poll` would sit on it until
    MAX_POLLS or read a terminal parent as a simulation that produced nothing.

    THE THREE ERROR WORDS ARE TERMINAL FOR THE PARENT AND SAY NOTHING ABOUT ITS TEN CHILDREN
    (`PARENT_TERMINAL`, from `tools/resim_bulk.py:479-530`, which walks the children on every
    terminal word). So the children are resolved individually under all five, and only a parent that
    names NO children falls back to the platform's own word for all of them.
    """
    if wait_first:
        sleep(POLL_FIRST_S)
    for i in range(MAX_POLLS):
        try:
            r = s.get(url, timeout=40)
        except Exception:  # noqa: BLE001 -- a timed-out poll is a poll to repeat, never a dead round
            sleep(POLL_S)
            continue
        if r.status_code == 401:
            return "AUTH-FAIL", [], i + 1, "401 on the parent poll"
        if r.status_code != 200:
            sleep(POLL_S)
            continue
        try:
            j = r.json()
        except ValueError:
            sleep(POLL_S)
            continue
        st = (j.get("status") or "").upper()
        if st in PARENT_TERMINAL:
            return st, list(j.get("children") or []), i + 1, (j.get("message")
                                                              or j.get("detail") or "")
        if deadline is not None and time.time() > deadline:
            return "POLL-DEADLINE", [], i + 1, "parent status %r at the round deadline" % st
        sleep(POLL_S)
    return "POLL-EXHAUSTED", [], MAX_POLLS, ""


def poll(s, url, clock=time.time, sleep=time.sleep, wait_first=True,
         expect_formula=None, expect_settings=None, deadline=None):
    """(status, alpha_id, polls, message). Never treats a timeout as a rejection.

    THE MESSAGE IS THE POINT. The first live batch returned 4 ERRORs and could not be diagnosed at
    all, because this function discarded the platform's own explanation and the journal kept no
    simulation url to go back for it. An ERROR without its message is a dead end that costs a
    simulation and teaches nothing.

    `wait_first=False` skips only the opening sleep, which exists because a just-POSTed simulation
    has nothing to report yet. A multisim child is polled only after its parent is already terminal,
    so that reason does not apply to it and the wait would be pure cost.

    `expect_formula` / `expect_settings` ARM THE CHILD-ORDER GUARD, and they are passed on the
    MULTISIM path only. There `children[i]` is attributed to `group[i]` on request order — an
    assumption this machine cannot verify (`simulate.py` OPEN_QUESTION 5) — and a mix-up files a
    real measurement under the wrong construction, which corrupts silently because both rows are
    genuine. On the single path one POST returns one url and there is nothing to mis-attribute, so
    nothing is compared and a platform-side re-formatting of the formula cannot cost a good row.
    THE GUARD IS SILENT WHEN IT CANNOT SEE: an echo the platform does not send is unchecked, and a
    `None` from it means "no disagreement observed", never "the mapping is correct".
    """
    if wait_first:
        sleep(POLL_FIRST_S)
    for i in range(MAX_POLLS):
        try:
            r = s.get(url, timeout=40)
        except Exception:  # noqa: BLE001 -- a timed-out poll is a poll to repeat, never a dead round
            sleep(POLL_S)
            continue
        if r.status_code == 401:
            return "AUTH-FAIL", None, i + 1, "401 on the poll"
        if r.status_code != 200:
            sleep(POLL_S)
            continue
        try:
            j = r.json()
        except ValueError:
            sleep(POLL_S)
            continue
        st = (j.get("status") or "").upper()
        msg = j.get("message") or j.get("detail") or ""
        if st in ("COMPLETE", "WARNING", "ERROR", "FAIL", "FAILED", "CANCELLED", "CANCELED"):
            # CANCELLED IS TERMINAL. 2026-09-06 23:01: a parent whose first 8 children ERRORed
            # (unknown operator) had its last 2 children CANCELLED by the platform; this loop did
            # not know the word and polled each of them 700 times -- the runner sat 52 min at 0 %
            # CPU with 10 COMPLETE alphas of the next parent unrecorded (recovered as orphans).
            # THE GUARD RUNS ON A TERMINAL ERROR TOO. 42 of the 500 reversed-order children in the
            # replay were never checked at all, because the error branch returned before the guard
            # ran — and an ERROR filed against the wrong construction still marks a sibling's
            # formula as having failed, which is durable.
            wrong = child_mismatch(j, expect_formula, expect_settings)
            if wrong is not None:
                return "GUARD-REFUSED", None, i + 1, "%s (platform said %s)" % (wrong, st)
            return st, (j.get("alpha") if st in ("COMPLETE", "WARNING") else None), i + 1, msg
        if deadline is not None and clock() > deadline:
            # THE ROUND DEADLINE REACHES INTO THE POLL (Khoa's tick 2026-09-07 14:10). Before this,
            # the 75-minute limit was checked only between dispatches, and a status word this
            # loop did not know kept it here for 700 polls per child (CANCELLED, 52 min, 09-06).
            # The unknown word is in the message so the journal names it for the next reader.
            return "POLL-DEADLINE", None, i + 1, "status %r at the round deadline" % st
        sleep(POLL_S)
    return "POLL-EXHAUSTED", None, MAX_POLLS, ""


def _post_patient(s, url, json_body, timeout=40, tries=3, sleep=time.sleep):
    """A POST that survives a transient SSL / connection error the same way _get_patient does.
    MEASURED 2026-09-08 18:35: one `SSLZeroReturnError` on POST /simulations killed a 300-simulation
    round (exit 1). A POST that raised never reached the platform, so retrying it cannot double-spend;
    a POST that was answered is returned on the first try."""
    last = None
    for i in range(tries):
        try:
            return s.post(url, json=json_body, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 -- requests' SSLError/ConnectionError/ReadTimeout family
            last = exc
            sleep(5 * (i + 1))
    raise last


def _get_patient(s, url, timeout=40, tries=3, sleep=time.sleep):
    """A GET that survives a transient ReadTimeout / connection error: up to `tries` attempts with
    a short back-off. MEASURED 2026-09-06: 23 forge rounds died between 17:14 and 19:52 on
    `requests.exceptions.ReadTimeout` raised inside scrape()/poll() -- one slow answer killed a
    300-simulation round, its dispatch and its harvest. Raises the last error only after every try."""
    last = None
    for i in range(tries):
        try:
            return s.get(url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 -- requests' ReadTimeout/ConnectionError family
            last = exc
            sleep(5 * (i + 1))
    raise last


def scrape(s, alpha_id):
    """Everything the platform will say about one alpha: metrics AND the full check list.

    The check list is what `gates.zero_fail` adjudicates, and a row without it is unjudgeable —
    which the presence contract says is neither a pass nor a fail.
    """
    try:
        r = _get_patient(s, "%s/alphas/%s" % (API, alpha_id), timeout=40)
    except Exception as exc:  # noqa: BLE001
        return {"scrape_http": "exception:%s" % type(exc).__name__}
    if r.status_code != 200:
        return {"scrape_http": r.status_code}
    j = r.json()
    iss = j.get("is") or {}
    return {
        "sharpe": iss.get("sharpe"), "fitness": iss.get("fitness"),
        "turnover": iss.get("turnover"), "returns": iss.get("returns"),
        "drawdown": iss.get("drawdown"), "margin": iss.get("margin"),
        "longCount": iss.get("longCount"), "shortCount": iss.get("shortCount"),
        "checks": iss.get("checks") or [],
        "dateCreated": j.get("dateCreated"),
        "pyramids": j.get("pyramids"),
    }


def run(n, *, seed, out_path, live, concurrency, children=MULTISIM_CHILDREN, out=print,
        frameworks=False, gap2x2=False, climb=False, objective=CLIMB.OBJECTIVE,
        max_round_s=MAX_ROUND_S, batch=None):
    # `batch` -- THE FORGE PATH (forge/runner.py, 2026-09-04): a prebuilt list of constructions
    # {"formula", "settings", "meta"} whose settings the caller already fixed per candidate. No pool
    # is loaded and nothing is drawn; everything from grouping onward is the same code the climb
    # uses, so the dispatcher, the 429 handling, the child-order guard and the journal row shape
    # are shared rather than copied. Default None keeps every existing path byte-identical.
    if batch is not None:
        constructions = list(batch)
        out("forge: %d construction(s) supplied by the caller" % len(constructions))
        return _dispatch(constructions, n=n, seed=seed, out_path=out_path, live=live,
                         concurrency=concurrency, children=children, out=out,
                         max_round_s=max_round_s)
    a, b, c = load_pools()
    rng = random.Random(seed)
    # Permuted blocks of 16, so every cell lands exactly n/16 times rather than drifting the way
    # independent coin flips do.
    assigner = LA.CellAssigner(seed=seed)
    # `screen_pool_c` returns (kept, report) -- I used the pair as if it were the list and the
    # composer got a 2-element list of lists. The report names what each screen removed, so the D
    # treatment's actual content is journalled from the run rather than trusted from a docstring.
    if climb:
        # THE CLOSED-LOOP PATH. One call = ONE ROUND. The state lives on disk between rounds, so a
        # crash, a 401 or a quota stop costs the round in flight and nothing else -- an inner loop
        # holding the baseline in memory would lose the whole climb.
        cst = CLIMB.load_state()
        out("climb: cycle %s, round %s -> %s, baseline score %s"
            % (cst.get("cycle"), cst.get("round"), cst.get("round", 0) + 1,
               cst.get("baseline_score")))
        if cst.get("baseline"):
            out("  baseline: %s" % cst["baseline"][:160])
        # POOL C IS BUILT FRESH EVERY ROUND, never from state/layered/pool_c.json. That file was
        # written 2026-08-13 and holds 73,258 leaves of which 70,184 -- 95.8% -- come from pyramid
        # cells that are now FULL; every screen added since lives in `load_fields()`, which the
        # frozen path never calls, so neither the coverage floor nor the pyramid gate had ever
        # reached the running loop.
        # THE SEGMENT IS PART OF THE STATE, and everything downstream must agree with it: the
        # field catalogue, the pyramid counts, and the POST body. A rotation that changed the pool
        # but left the settings on USA would simulate EUR fields against a USA universe.
        seg = cst.get("segment") or ["USA", "TOP3000", 1]
        region, universe, delay = seg[0], seg[1], int(seg[2])
        SETTINGS.update({"region": region, "universe": universe, "delay": delay})
        c = LA.build_pool_c(
            LA.load_fields(path=ROOT / ("fetched/rc/fields/%s_%s_d%d.jsonl"
                                        % (region, universe, delay)),
                           region=region, universe=universe, delay=delay),
            rng=random.Random(seed))
        gate = getattr(LA.load_fields, "gate", {})
        out("segment %s/%s/d%d | pool C %d leaves%s | %d field(s) retired as spent"
            % (region, universe, delay, len(c),
               (" (pyramid gate ON: %d cell(s) disabled)" % len(gate.get("disabled") or ()))
               if gate.get("ok") else " (pyramid gate OFF)",
               getattr(LA.load_fields, "retired", 0)))
        batch = CLIMB.draw(cst, a, b, c, rng, n, out=out)
        out("drew %d candidates %s"
            % (len(batch), dict(sorted(collections.Counter(m["move"] for _, m in batch).items()))))
    elif gap2x2:
        # THE GAP PATH. Corpus formulas and ours, crossed with corpus settings and ours, balanced
        # within one batch. `RF_RS` is the positive control: it must reproduce the corpus baseline
        # or no other cell may be read.
        pool = GAP.resim_pool()
        rate, n_base = GAP.baseline(pool)
        out("corpus: %d replayable rows, baseline screen %.2f%% (n=%d) -- RF_RS must reproduce it"
            % (len(pool), 100 * (rate or 0), n_base))
        batch = GAP.draw(n, seed)
        out("drew %d across 4 cells %s"
            % (len(batch), dict(sorted(collections.Counter(m["cell"] for _, m in batch).items()))))
    elif frameworks:
        # THE FRAMEWORK PATH SKIPS THE 2^6 MACHINERY ENTIRELY. An alpha carries a cell or a
        # framework, never both, so every journalled row belongs to exactly one experiment.
        # Predictions are printed BEFORE the batch so the run's own log records what would refute
        # each arm -- a prediction read off a finished result is not a prediction.
        for f in FW.FRAMEWORKS:
            out("PREREG %-9s %s" % (f.name, f.predicts))
        batch = draw_frameworks(a, b, c, rng, n)
        counts = collections.Counter(m["framework"] for _, m in batch)
        out("drew %d distinct alphas across %d frameworks %s"
            % (len(batch), len(counts), dict(sorted(counts.items()))))
    else:
        # `screen_pool_c` returns (kept, report) -- I used the pair as if it were the list and the
        # composer got a 2-element list of lists. The report names what each screen removed, so the
        # D treatment's actual content is journalled from the run rather than trusted from a
        # docstring.
        kept, d_report = LA.screen_pool_c(c, LA.load_screens())
        gates_ = LA.load_gate_pool()
        out("layer-D screen keeps %d of %d leaves (%s); %d gate conditions"
            % (len(kept), len(c), d_report, len(gates_)))
        batch = draw(a, b, c, rng, n, assigner=assigner, pool_c_kept=kept, gate_pool=gates_)
        out("drew %d distinct alphas (carrier present in %d)"
            % (len(batch), sum(1 for _, m in batch if (m or {}).get("carrier"))))

    # One construction per alpha, in the shape `multisim_groups`/`payload_many` read. ORDER IS NOT
    # TOUCHED: the draw order IS the sample, and re-ordering it would silently re-sample the batch.
    # Grouped BEFORE the dry-run exit, so the shape can be inspected without spending a simulation.
    # THE ARM BELONGS TO THE CONSTRUCTION, NOT TO THE POST BODY. It used to be applied only inside
    # `post_many`, so `c["settings"]` still said `s_flat` while the platform ran and echoed the real
    # arm. `_reap` handed that stale dict to the child-order guard as `expect_settings`, the guard
    # compared it against a CORRECT echo, and refused every child that was not `s_flat` -- measured
    # on the smoke batch: 9 of 20 harvested, all one arm, 11 real results discarded while the run
    # looked healthy.
    #
    # Suppressing the settings comparison would have "fixed" it and reopened the hole the comparison
    # exists to close: `simulate.py` records 20 of 500 reversed children carrying a sibling's alpha
    # id when the guard is formula-only. So the fix is to make the expectation true, not to stop
    # checking it.
    def _settings(m):
        m = m or {}
        if m.get("profile"):            # gap-2x2 row: the profile IS the factor, no arm on top
            return settings_for_profile(m["profile"])
        if m.get("settings_arm"):
            return settings_for(m["settings_arm"], m.get("framework"))
        return dict(SETTINGS)

    constructions = [{"formula": f, "settings": _settings(m), "meta": m} for f, m in batch]
    results = _dispatch(constructions, n=n, seed=seed, out_path=out_path, live=live,
                        concurrency=concurrency, children=children, out=out,
                        max_round_s=max_round_s)
    if not live:
        return results
    if climb:
        cst = CLIMB.load_state()
        n_gems = CLIMB.write_gems(results, cst.get("cycle", 1))
        cst, event = CLIMB.advance(cst, results, objective=objective)
        tiers = collections.Counter(CLIMB.tier(r) for r in results)
        out("climb: %d rows, tiers %s, %d gem(s) -> %s"
            % (len(results), dict(sorted(tiers.items())), n_gems, event))
        if event in ("stall", "dead-end"):
            why = ("STALLED after %d rounds" % cst.get("round") if event == "stall"
                   else "DEAD END -- no candidate in this round cleared the baseline filters")
            out("climb: %s. %s" % (why, "gems written, " if n_gems else "no gems, ")
                + "resetting to round 1, fully random (Khoa: no banning of explored ground)")
            cst = CLIMB.reset(cst, n_gems)
        CLIMB.save_state(cst)
        out("\n".join(CLIMB.report(cst)))
    return results


def _dispatch(constructions, *, n, seed, out_path, live, concurrency, children, out,
              max_round_s):
    """Group, preview or POST, reap, journal. Shared by every draw path and the forge batch path;
    returns the journalled rows (empty on a dry run)."""
    groups = multisim_groups(constructions, size=children)
    out("%d parents x <=%d children (%s fixed per parent), <=%d in flight"
        % (len(groups), children, "/".join(MULTISIM_GROUP_KEYS), concurrency * children))

    if not live:
        for x in constructions[:8]:
            f, m = x["formula"], x["meta"] or {}
            # A framework row has no `legs` structure -- it carries `framework` instead, and the two
            # meta shapes are deliberately distinct so a journalled row cannot be read as the wrong
            # experiment. The preview reports whichever the row actually has.
            # Each experiment carries its own meta shape on purpose, so a journalled row can never be
            # read as the wrong experiment. The preview reports whichever key the row actually has.
            tag = _tag(m)
            out("  %-12s carrier=%-5s %s" % (tag, m.get("carrier", "-"), f[:140]))
        out("DRY RUN -- pass --live to spend simulations")
        return []

    s = session()
    keep_jar_fresh(s)          # a tap mid-round is picked up within ~20s instead of being lost
    deadline = time.time() + max_round_s if max_round_s else None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # THE MARKER THE HEALTH REPORT READS. Without it the monitor prints `running=none` while 300
    # simulations are in flight, which reads as a dead pipeline and is how a real run gets killed
    # by someone acting on the report. Removed in a `finally` so a crash does not leave a stale
    # marker claiming a run that is gone.
    marker = ROOT / "state/simrunning" / ("%s.json" % out_path.stem)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"pid": os.getpid(), "started": time.time(), "n": n,
                                  "journal": str(out_path), "seed": seed}))
    results, inflight = [], []
    with open(out_path, "a") as jf:
        for g in groups:
            # DISPATCH AND COLLECTION NO LONGER TAKE TURNS. The loop only blocks when the slots
            # are genuinely full AND something is old enough to be worth asking about; otherwise it
            # goes back to POSTing. Blocking on a handle that was posted 12 s ago asked a question
            # whose answer could not have changed -- a simulation takes ~335 s.
            if deadline and time.time() > deadline:
                out("ROUND DEADLINE at %d min -- stopping dispatch. Everything journalled is kept "
                    "and still folded in; the unposted remainder is simply not posted."
                    % (max_round_s // 60))
                break
            while len(inflight) >= concurrency:
                if deadline and time.time() > deadline:
                    break
                before = len(inflight)
                inflight = _reap(s, inflight, jf, results, out, deadline=deadline)
                if len(inflight) == before:
                    time.sleep(IDLE_SLEEP_S)
            # A CONCURRENT 429 IS A WAIT, NOT A REJECTION. The first attempt at this batch journalled
            # `POST-429` and moved to the next alpha, which burned 200 draws in seconds without
            # spending a single simulation. The platform is saying "all slots are busy"; the answer
            # is to reap one and try again. A DAILY 429 is different -- that one is terminal for the
            # day and must stop the run rather than spin. A 429 NOW COSTS A WHOLE GROUP, not one
            # draw, which is the same reason to wait rather than a new one.
            for attempt in range(60):
                code, loc, body = (
                    post_one(s, g[0]["formula"],
                             arm=(g[0].get("meta") or {}).get("settings_arm"))
                    if len(g) == 1 else post_many(s, g))
                if code != 429:
                    break
                if "DAILY" in (body or "").upper():
                    out("  daily simulation limit reached -- stopping: %s" % body[:110])
                    code = -1
                    break
                if inflight:
                    inflight = _reap(s, inflight, jf, results, out, deadline=deadline)
                else:
                    time.sleep(20)
            if code == -1:
                break
            if code in (200, 201) and loc:
                inflight.append({"url": loc, "group": g, "parent": len(g) > 1,
                                 "t0": time.time()})
                # THE HANDLE REACHES DISK BEFORE THE FIRST POLL, and that timing is the whole point.
                # This is the only window in which the platform holds up to ten simulations and NOT
                # ONE child row exists, so a line written after the polling finishes is worth
                # nothing to the interruption it exists to survive.
                _write(jf, results, {"status": "PARENT-POSTED", "parent_url": loc,
                                     "n_children": len(g),
                                     "formulas": [x["formula"] for x in g]})
            else:
                # THE REFUSAL FANS OUT TO EVERY CHILD as the status each would have received alone.
                # One `POST-400` row for a group of ten would lose nine formulas from the evidence
                # base -- exactly the unanalysability this module exists to prevent.
                for x in g:
                    _write(jf, results, {"status": "POST-%d" % code, "formula": x["formula"],
                                         "meta": x["meta"], "settings": x["settings"],
                                         "body": body})
                out("  POST %d (x%d): %s" % (code, len(g), body[:120]))
                if code in (401, 403):
                    out("  stopping: the session is not usable")
                    break
        while inflight:
            if deadline and time.time() > deadline:
                out("ROUND DEADLINE with %d handle(s) still in flight. They are journalled with "
                    "their parent_url, so `recover_parents.py` harvests them later at zero quota "
                    "cost." % len(inflight))
                break
            inflight = _reap(s, inflight, jf, results, out, deadline=deadline)
    try:
        marker.unlink()
    except OSError:
        pass
    return results


def _write(jf, results, rec):
    """One journal row, on disk before the caller does anything else.

    FLUSHED PER ROW, NOT PER BATCH. A crash costs the rows still in flight and NOTHING that was
    already journalled; a buffered writer would lose up to a whole batch of real measurements that
    the platform will not repeat for free.
    """
    jf.write(json.dumps(rec) + "\n")
    jf.flush()
    results.append(rec)
    return rec


def _pick(inflight, now=None):
    """The OLDEST handle that is worth asking about, or None if every handle is still too young.

    Reaping strictly in POST order made the runner wait on handle 1 while handles 2..8 sat finished,
    and paying `POLL_FIRST_S` inside each reap turned 8 parents into ~96 s of serial sleep per cycle
    even when all 8 were done. Age is measured from each handle's OWN post time, so the wait is
    shared rather than repeated.
    """
    now = now if now is not None else time.time()
    ready = [i for i in inflight if now - i["t0"] >= MIN_HANDLE_AGE_S]
    if not ready:
        return None
    return max(ready, key=lambda i: now - i["t0"])


def _reap(s, inflight, jf, results, out, block=True, deadline=None):
    """Poll ONE in-flight handle to terminal and journal EVERY construction under it, with its
    structure. A handle is a multisim parent (up to `--children` rows) or a single simulation.

    `block=False` returns without doing anything when no handle is old enough — the caller can then
    keep POSTing instead of sleeping, which is the point: dispatch and collection stop taking turns.
    """
    item = _pick(inflight)
    if item is None:
        if not block:
            return inflight
        time.sleep(IDLE_SLEEP_S)
        item = _pick(inflight) or inflight[0]
    inflight.remove(item)
    if not item["parent"]:
        c = item["group"][0]
        # WAIT_FIRST STAYS ON. Dropping it was part of a throughput change and it produced
        # POLL-EXHAUSTED on the very next smoke batch: without the opening pause the loop spends its
        # 220 polls before the platform has an answer. The throughput win that survives is the
        # AGE-BASED pick -- a handle is not asked about until it is old enough — which removes the
        # serial sleep without shortening any individual poll.
        st, alpha, polls, msg = poll(s, item["url"], deadline=deadline)
        _child_row(s, jf, results, out, c, st, alpha, polls, msg,
                   sim_url=item["url"], t0=item["t0"])
        return inflight

    g = item["group"]
    pst, children, ppolls, pmsg = poll_parent(s, item["url"], deadline=deadline)
    if len(children) != len(g):
        # FAIL CLOSED ON THE COUNT. Attributing the `min(len)` children that did arrive files every
        # id after the first gap under another construction's formula, and both rows look genuine
        # afterwards. So none is attributed, and the shape is in the message so the journal is
        # diagnosable without re-running anything.
        if not children and pst not in ("COMPLETE", "WARNING"):
            st, why = pst, "parent %s named no children: %s" % (pst, pmsg)
        else:
            st, why = "MULTISIM-CHILD-COUNT", ("children %d of %d (parent %s) %s"
                                               % (len(children), len(g), pst, pmsg))
        for i, c in enumerate(g):
            _child_row(s, jf, results, out, c, st, None, ppolls, why,
                       sim_url=None, t0=item["t0"], parent_url=item["url"], child_index=i)
        return inflight

    for i, c in enumerate(g):
        curl = child_url(children[i])
        if curl is None:
            # The parent named no simulation at this position. One may exist and this module cannot
            # name it; it does not invent a handle and it does not blame the formula.
            _child_row(s, jf, results, out, c, "MULTISIM-CHILD-ABSENT", None, ppolls,
                       "parent named no simulation at index %d" % i,
                       sim_url=None, t0=item["t0"], parent_url=item["url"], child_index=i)
            continue
        # A CHILD THAT FAILS MUST NOT TAKE ITS NINE SIBLINGS WITH IT: each is polled on its own
        # handle to its own terminal status, so an ERROR, a 401 or an exhausted poll is that
        # child's own outcome and the loop over the others continues.
        cst, alpha, cpolls, cmsg = poll(s, curl, wait_first=False,
                                        expect_formula=c["formula"],
                                        expect_settings=c["settings"], deadline=deadline)
        _child_row(s, jf, results, out, c, cst, alpha, ppolls + cpolls, cmsg,
                   sim_url=curl, t0=item["t0"], parent_url=item["url"], child_index=i)
    return inflight


def _tag(meta):
    """A short label for whichever experiment this row belongs to.

    Three experiments write rows through this module and each carries its own meta shape ON PURPOSE,
    so a journalled row can never be read as the wrong experiment: the 2^6 factorial has `legs`, a
    framework row has `framework`, a gap row has `cell`, a climb row has `move`. Nothing may index
    those keys directly -- one such index crashed a live round on its first harvested child.
    """
    m = meta or {}
    if m.get("hypothesis"):             # a forge row names its hypothesis
        return str(m["hypothesis"])[:24]
    if m.get("cell"):
        return m["cell"]
    if m.get("move"):
        return "%s/d%s" % (m["move"], m.get("depth", "?"))
    if m.get("framework"):
        return m["framework"]
    legs = m.get("legs")
    if legs:
        return "legs=%d" % len(legs)
    return "-"


def _child_row(s, jf, results, out, c, st, alpha, polls, msg, *, sim_url, t0,
               parent_url=None, child_index=None):
    """One construction's terminal row: its own status, its own formula, its own draw.

    NOTHING IS INHERITED FROM THE PARENT except `parent_url` -- `formula`, `meta` (the arm, the leg
    count, the chain, the leaf, the carrier) and `settings` are per-child, because the analysis
    blocks on those and a row that cannot name its arm cannot be counted.
    """
    rec = {"status": st, "alpha": alpha, "polls": polls, "message": msg,
           "sim_url": sim_url, "formula": c["formula"], "meta": c["meta"],
           "settings": c["settings"], "detect_age_s": round(time.time() - t0, 1)}
    if parent_url is not None:
        rec["parent_url"], rec["child_index"] = parent_url, child_index
    if alpha:
        rec.update(scrape(s, alpha))
    _write(jf, results, rec)
    out("  %-20s %-12s carrier=%-5s sharpe=%s fitness=%s %s"
        # EVERY META KEY HERE IS OPTIONAL, and that is not defensive padding -- it is the exact bug
        # that just cost a run. `n_legs` and `carrier` belong to the layered composer's meta; a
        # CLIMB row has neither (it carries `move`, `op`, `depth`). This line runs on every
        # harvested child, so the round died the moment its first child came back: parents posted,
        # quota spent, nothing collected, and the loop immediately started another round and did it
        # again -- 14 times in 25 minutes. I had already made the DRY-RUN preview tolerant of the
        # three meta shapes and missed this identical pattern 200 lines further down. Fixing one
        # site of a pattern and shipping is the same class of error as the deploy skew that
        # abandoned 1,410 simulations.
        % (st, _tag(c["meta"]), (c["meta"] or {}).get("carrier", "-"),
           rec.get("sharpe"), rec.get("fitness"), (msg or "")[:110]))
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--live", action="store_true", help="actually spend simulations")
    ap.add_argument("--concurrency", type=int, default=8,
                    help="multisim PARENTS in flight (was: single simulations in flight)")
    ap.add_argument("--children", type=int, default=MULTISIM_CHILDREN,
                    help="simulations per parent; 8x10=80 is OPERATOR-STATED, not measured here")
    ap.add_argument("--out", default=None)
    ap.add_argument("--climb", action="store_true",
                    help="one ROUND of the closed-loop builder: draw around the current baseline, "
                         "simulate, argmax the objective, fold into state/climb/state.json")
    ap.add_argument("--objective", default=CLIMB.OBJECTIVE,
                    help="metric the climb argmaxes. Sub-universe sharpe since 2026-08-15 (Khoa): "
                         "it is the value inside LOW_SUB_UNIVERSE_SHARPE, the ratio gate the "
                         "council named the binding constraint.")
    ap.add_argument("--gap2x2", action="store_true",
                    help="corpus formulas vs ours, crossed with corpus settings vs ours. Separates "
                         "the settings and grammar causes of the 0%%-vs-14%% screen gap.")
    ap.add_argument("--frameworks", action="store_true",
                    help="draw from the declared alpha frameworks instead of the 2^6 factorial "
                         "cells, balanced within the batch. A row carries a cell or a framework, "
                         "never both.")
    args = ap.parse_args()
    seed = args.seed if args.seed is not None else int(time.time())
    if args.out:
        out_path = pathlib.Path(args.out)
    elif args.climb:
        # ONE FILE FOR THE WHOLE CLIMB, not one per round. A new journal every round changes the
        # set of files the health reporter counts, and its rate guard then refuses to difference
        # across a moved set -- correctly, since widening that scan once produced a fake
        # "4,572 sims/min". With a file per round the rate would read "not measurable" forever.
        # Every row already carries its cycle and round in `meta`, so nothing is lost by appending.
        out_path = OUTDIR / "climb.jsonl"
    else:
        stem = "gap_%d" if args.gap2x2 else ("fw_%d" if args.frameworks else "run_%d")
        out_path = OUTDIR / ((stem + ".jsonl") % seed)
    print("seed %d -> %s" % (seed, out_path))
    run(args.n, seed=seed, out_path=out_path, live=args.live, concurrency=args.concurrency,
        children=args.children, frameworks=args.frameworks, gap2x2=args.gap2x2,
        climb=args.climb, objective=args.objective)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
