#!/usr/bin/env python3
"""tools/auto_submit.py -- pyramid-cell-driven AUTOMATIC submission to WorldQuant BRAIN.

THE ONE IRREVERSIBLE ACTION. `POST /alphas/{alpha}/submit` exists exactly once per alpha. The repo's
own recorded outcomes, which this module is built around:

  * A 403 is the platform ADJUDICATING the POST. The alpha's single lifetime attempt is spent and
    the alpha is permanently dead. Six alphas (pwKZl6Zg, O0xVZpVd, Vk35PY2J, vRvNrZXw, gJ98Vqjl,
    N1R7AKN8) sit in state/funnel/submit_log.jsonl with a 403. Only 408 and 429 are retryable
    (harness/guards.py:slot_returnable).
  * A transport exception is NOT a rejection. `GET /alphas/{alpha}/submit` answers 404 for "no job"
    and 200 for "queued"; `/check` cannot tell them apart. So a POST that raised may well have
    landed, and this module treats that state as terminal-unknown and never re-POSTs.

DRY RUN IS THE DEFAULT. `plan()` and `main()` refuse to POST unless the caller passes the explicit
affirmative flag --i-am-spending-real-submissions, and `submit_one()` raises if handed live=False.

IDEMPOTENCY IS JOURNAL-FIRST. The INTENT is written to disk and fsync'd BEFORE the request leaves,
and the G6 ledger reservation (harness/guards.reserve_submit) is taken under an exclusive flock
before that. If this process dies between the intent record and the outcome record, the next run
reads an intent with no outcome and refuses that alpha FOREVER. Losing one alpha to a crash is
recoverable by a human; a second POST is not.

BLAST RADIUS: MAX_ALPHAS_PER_RUN alphas (4). See the module docstring section at the bottom of
main(). Even with every preflight guard returning ok, the run loop stops after 4 distinct alphas
have been POSTed.

RULE 0: nothing in this file explains WHY the platform returns any status. The 429 body strings
are documented for POST /simulations only (tools/daily_budget.py); for POST /submit the body
taxonomy is MECHANISM: UNKNOWN and an unrecognised 429 body is therefore treated as the
run-stopping case, not the retryable one.

Usage:
    python3 tools/auto_submit.py --region USA --delay 1                 # DRY RUN (default)
    python3 tools/auto_submit.py --region USA --delay 1 \
            --i-am-spending-real-submissions                            # LIVE, irreversible
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.guards import (SUB as BUDGET_LEDGER, _platform_date, release_submit,  # noqa: E402
                            reserve_submit)

# ------------------------------------------------------------------------------------- constants

API = "https://api.worldquantbrain.com"
LIVE_FLAG = "--i-am-spending-real-submissions"

KILL_SWITCH = ROOT / "state/AUTO_SUBMIT_STOP"          # human stop, read from disk before each POST
JOURNAL = ROOT / "state/auto_submit_journal.jsonl"     # intent-before-request audit + idempotency
DECISIONS = ROOT / "state/auto_submit_decisions.json"  # pyramid cell decisions (the input contract)
CORR = ROOT / "state/prod_corr_measured.json"          # written by tools/fetch_prod_corr.py
BANNED = ROOT / "state/banned_fields.json"

PROD_CORR_MAX = 0.70          # prod >= this is a refusal (state/prod_corr_measured.json:prod_maxcorr)
#: Same limit, same reason. The platform's SELF_CORRELATION check carries limit 0.70; a stored
#: reading of 0.7031 was rejected verbatim, which is what pins the number rather than 0.71.
SELF_CORR_MAX = 0.70
MAX_DECISION_AGE_S = 3600     # cell data older than this is STALE -> refuse
DAILY_SUBMIT_QUOTA = 4        # platform REGULAR_SUBMISSION limit, resets 00:00 ET
MAX_ALPHAS_PER_RUN = 4        # POSTs ACCEPTED per run. NOT the blast radius -- see below.

#: THE REAL BLAST RADIUS BOUND, and the reason it is a separate constant.
#:
#: `MAX_ALPHAS_PER_RUN` counts POSTs that SUCCEED. A 403 does not succeed -- and a 403 ADJUDICATES:
#: that alpha's one and only submission is spent forever. So a cap on successes bounds nothing that
#: matters when the guards fail. Measured in the round-10 rehearsal: with `preflight` forced open,
#: 4 alphas were accepted and **up to 97 more could be destroyed in the same run**, because the loop
#: kept walking the candidate list. There was no structural bound below the list's own length.
#:
#: This caps the READ, not the POST. Whatever writes the decisions file, a single run can only ever
#: touch this many alphas -- so the worst case is bounded by a number in this file rather than by
#: the size of a JSON document some other process produced.
MAX_DECISIONS_PER_RUN = 8
MAX_ATTEMPTS_PER_ALPHA = 3    # only 429-concurrent and 408 consume an attempt
BACKOFF_S = (20, 60)          # sleep before retry attempt 2, attempt 3

# Outcomes after which a further POST for the same alpha is permitted. Everything else -- including
# "no outcome recorded at all" -- is terminal.
RETRYABLE = "retryable"
TERMINAL = "terminal"


# --------------------------------------------------------------------------------------- journal

def _append(path, rec):
    """Append one JSON record and force it to the platter before returning.

    The whole idempotency argument rests on the intent record surviving a process death that
    happens microseconds later, so a buffered write is not good enough: flush + fsync, then fsync
    the directory so the new size is durable too."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
        f.flush()
        os.fsync(f.fileno())
    dfd = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def read_journal(path=None):
    path = pathlib.Path(path or JOURNAL)
    out = []
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:          # a torn last line -> skip, never crash the gate
            continue
    return out


def post_permitted(alpha, records):
    """(ok, why) -- may a POST be issued for `alpha` given the journal so far?

    THE crash rule. Intent and outcome are appended in order for a given alpha, so an outcome
    deficit means a request left (or may have left) and this process never learned what happened.
    That is unknown, and unknown is terminal: never POST again."""
    mine = [r for r in records if r.get("alpha") == alpha]
    intents = [r for r in mine if r.get("event") == "intent"]
    outcomes = [r for r in mine if r.get("event") == "outcome"]
    if not intents:
        return True, "no prior POST intent journalled"
    if len(outcomes) < len(intents):
        return False, (f"{alpha}: intent #{len(intents)} has NO recorded outcome -- a POST may have "
                       f"landed and this process died before it learned. Terminal, never re-POST. "
                       f"Resolve by hand: GET {API}/alphas/{alpha} -- status/dateSubmitted decide. "
                       f"DO NOT re-POST. GET /alphas/{alpha} (status + dateSubmitted) is the ONLY disambiguator. /alphas/{alpha}/submit answers 404 for a SUBMITTED alpha too -- measured 2026-08-05 (E5ejp6JL, submitted, 404) and re-confirmed 2026-08-16 on mL516W9W while ACTIVE. Reading 404 as 'not submitted' is how an alpha gets re-POSTed into a 403 that spends its slot forever.")
    last = outcomes[-1]
    if last.get("disposition") == RETRYABLE:
        return True, f"prior outcome {last.get('status')} was retryable ({last.get('classification')})"
    return False, (f"{alpha}: prior outcome {last.get('status')} "
                   f"({last.get('classification')}) is TERMINAL")


# ------------------------------------------------------------------------------------ kill switch

def kill_switch_engaged(path=None):
    """(engaged, text). Read from DISK every time -- a human drops the file to stop a running
    process without killing it. Unreadable-but-present counts as engaged."""
    p = pathlib.Path(path or KILL_SWITCH)
    if not p.exists():
        return False, ""
    try:
        return True, p.read_text().strip()[:200]
    except OSError as e:
        return True, f"<present but unreadable: {e}>"


# -------------------------------------------------------------------------------------- preflight

def load_decisions(path=None, now=None, max_age_s=MAX_DECISION_AGE_S):
    """(decisions, err). The cell-decision file is the ONLY source of "which cell and why".

    Contract:
      {"as_of": "<ISO8601 UTC>", "decisions": {"<alphaId>": {
          "cell": "Institutions", "region": "USA", "delay": 1,
          "reason": "<free text: why this alpha into this cell>",
          "formula": "<the alpha expression>", "family": "<G6 family key>"}}}

    Fail closed on: file absent, unparseable, no as_of, as_of unparseable, as_of older than
    max_age_s. A stale cell count is how an alpha gets POSTed into a cell that filled an hour ago.
    """
    import datetime
    p = pathlib.Path(path or DECISIONS)
    if not p.exists():
        return {}, f"no cell decision file at {p} -- refusing (fail-closed)"
    try:
        j = json.loads(p.read_text())
    except (ValueError, OSError) as e:
        return {}, f"cell decision file unreadable ({e}) -- refusing (fail-closed)"
    as_of = j.get("as_of")
    if not as_of:
        return {}, "cell decision file has no as_of -- cannot prove freshness, refusing"
    try:
        ts = datetime.datetime.fromisoformat(as_of)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
    except ValueError as e:
        return {}, f"cell decision as_of={as_of!r} unparseable ({e}) -- refusing"
    age = (now if now is not None else time.time()) - ts.timestamp()
    if age > max_age_s:
        return {}, (f"cell data STALE: as_of {as_of} is {int(age)}s old "
                    f"(max {max_age_s}s) -- refusing")
    if age < -300:
        return {}, f"cell data as_of {as_of} is in the FUTURE by {int(-age)}s -- refusing"
    return (j.get("decisions") or {}), None


def load_banned(path=None):
    p = pathlib.Path(path or BANNED)
    try:
        return set(json.loads(p.read_text())["banned_fields"]), None
    except (OSError, ValueError, KeyError, TypeError) as e:
        return set(), f"banned-field list unreadable ({e}) -- refusing (fail-closed)"


def banned_in(formula, banned):
    """Banned field tokens present in `formula`, as whole identifiers."""
    toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", formula or ""))
    return sorted(toks & banned)


def corr_verdict(alpha, corr_path=None):
    """(ok, why). Missing verdict, unreadable file, non-numeric or >= PROD_CORR_MAX -> refuse.

    prod_maxcorr is `j['max']` of the platform correlation histogram (state/prod_corr_measured.json)."""
    p = pathlib.Path(corr_path or CORR)
    try:
        j = json.loads(p.read_text())
    except (OSError, ValueError) as e:
        return False, f"correlation store unreadable ({e}) -- refusing (fail-closed)"
    row = j.get(alpha)
    if not isinstance(row, dict) or "prod_maxcorr" not in row:
        return False, f"no prod-correlation verdict for {alpha} -- refusing (fail-closed)"
    v = row["prod_maxcorr"]
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return False, f"prod_maxcorr for {alpha} is {v!r}, not a number -- refusing"
    if v >= PROD_CORR_MAX:
        return False, f"prod_maxcorr {v} >= {PROD_CORR_MAX} -- refusing"

    # SELF-CORRELATION IS A GATE TOO, and its absence here was a hole on the irreversible path
    # (round-10 rehearsal, H3). The submission checks carry SELF_CORRELATION with the same 0.70
    # limit as PROD, so an alpha clean on prod and dirty on self is refused by the platform after
    # the POST has already been spent. Measured: 61.5% of gems pass self, so this refuses fewer than
    # the prod gate does -- but the ones it refuses are ones we would otherwise burn.
    sv = row.get("self_maxcorr")
    if row.get("self_measured") is False or sv is None:
        return False, (f"no self-correlation verdict for {alpha} -- refusing (fail-closed). "
                       f"Absent is neither pass nor fail.")
    if not isinstance(sv, (int, float)) or isinstance(sv, bool):
        return False, f"self_maxcorr for {alpha} is {sv!r}, not a number -- refusing"
    if sv >= SELF_CORR_MAX:
        return False, f"self_maxcorr {sv} >= {SELF_CORR_MAX} -- refusing"

    breaches = row.get("prod_breach_count")
    if isinstance(breaches, int) and breaches > 0:
        return False, f"prod_breach_count {breaches} > 0 -- refusing"

    return True, f"prod_maxcorr {v} < {PROD_CORR_MAX}, self_maxcorr {sv} < {SELF_CORR_MAX}"


def already_submitted(alpha, ledger=None):
    """(spent, why) from the G6 ledger -- the record of EVERY tool's POSTs, not just this one's.

    Found by running the dry run against real state: 1YppwgwX has sat in
    state/submit_budget.jsonl since 2026-08-10 and this module's own journal knew nothing about
    it, so the dry run announced it would POST an alpha whose one attempt was already spent.
    reserve_submit() would have refused at POST time, but a preflight that says "would POST" about
    a dead alpha is a lie a human acts on."""
    p = pathlib.Path(ledger or BUDGET_LEDGER)
    if not p.exists():
        return False, ""
    for line in p.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("alpha") == alpha:
            return True, (f"{alpha} already had its one submit POST on {r.get('date')} "
                          f"(family {r.get('family')}, G6 ledger) -- refusing")
    return False, ""


def submits_used_today(ledger=None, today=None):
    """Reservations recorded in the G6 ledger for the current PLATFORM (US Eastern) day.

    Counts EVERY tool's reservations, not just this module's -- the platform's 4/day counter does
    not care which script spent it."""
    p = pathlib.Path(ledger or BUDGET_LEDGER)
    today = today or _platform_date()
    if not p.exists():
        return 0
    n = 0
    for line in p.read_text().splitlines():
        try:
            if json.loads(line).get("date") == today:
                n += 1
        except ValueError:
            continue
    return n


def preflight(alpha, decision, cfg, records, ctx):
    """(ok, reason). THE refusal chain. Every branch fails CLOSED: anything that cannot be
    evaluated is a refusal, never a pass. Order is cheapest-and-most-permanent first."""
    if not decision:
        return False, "no cell decision for this alpha -- refusing"
    for k in ("cell", "region", "delay", "reason", "formula", "family"):
        if decision.get(k) in (None, ""):
            return False, f"cell decision missing {k!r} -- refusing"

    if (decision["region"], int(decision["delay"])) != (cfg["region"], cfg["delay"]):
        return False, (f"alpha is {decision['region']}/d{decision['delay']}, this run is configured "
                       f"for {cfg['region']}/d{cfg['delay']} only -- refusing")

    spent, why = already_submitted(alpha, ctx.get("ledger"))
    if spent:
        return False, why

    ok, why = post_permitted(alpha, records)
    if not ok:
        return False, why

    used = submits_used_today(ctx.get("ledger"), ctx.get("today"))
    if used >= DAILY_SUBMIT_QUOTA:
        return False, (f"daily submit quota exhausted: {used}/{DAILY_SUBMIT_QUOTA} recorded for "
                       f"platform day {ctx.get('today') or _platform_date()} -- refusing")

    ok, why = corr_verdict(alpha, ctx.get("corr"))
    if not ok:
        return False, why
    corr_note = why

    banned, err = load_banned(ctx.get("banned"))
    if err:
        return False, err
    hits = banned_in(decision["formula"], banned)
    if hits:
        return False, f"formula uses banned field(s) {hits} -- refusing"

    # THE CELL IS RE-CHECKED AGAINST LIVE COUNTS, HERE, ON THE IRREVERSIBLE PATH.
    #
    # This module used to trust the decisions file's word about which cell an alpha fills and how
    # full that cell was. That word is only as fresh as the file: the round-10 rehearsal drove a
    # decision naming `Price Volume` (live count 40, unlocks at 3) straight through `preflight` to a
    # POST. A cell that filled between planning and POSTing is exactly the case an unattended
    # machine cannot notice, and the cost of not noticing is one alpha spent for nothing.
    #
    # `cell_ok` is injectable so tests need no network; the default asks `pyramid_gate`, which reads
    # the count three times and keeps the MAX (an under-count says a full cell still needs alphas —
    # asymmetric error, asymmetric guard) and REFUSES on data it considers stale.
    checker = ctx.get("cell_ok") or _live_cell_ok
    ok, why = checker(decision["cell"], cfg)
    if not ok:
        return False, why

    return True, f"{corr_note}; {why}"


def _live_cell_ok(cell, cfg):
    """(ok, why) from the LIVE pyramid counts. Fail closed on anything unreadable or stale."""
    try:
        import pyramid_gate
    except Exception as e:                                   # noqa: BLE001 - refusing is the point
        return False, f"cannot import pyramid_gate ({e}) -- refusing (fail-closed)"
    try:
        cells = pyramid_gate.cell_state(cfg["region"], cfg["delay"])
    except Exception as e:                                   # noqa: BLE001
        return False, f"live cell read failed ({e}) -- refusing (fail-closed)"
    d = pyramid_gate.decide(cell, cells)
    if getattr(d, "action", None) != "SUBMIT":
        return False, (f"live cell check refuses {cell}: "
                       f"{getattr(d, 'reason', 'no reason given')} -- refusing")
    return True, (f"live cell {cell} at {getattr(d, 'count', '?')}/3, "
                  f"needs {getattr(d, 'needs', '?')}")


# ----------------------------------------------------------------------------------------- plan

def describe(alpha, decision, note, live):
    """The EXACT request this module would issue, plus which cell and why."""
    return "\n".join([
        f"{'LIVE POST' if live else 'DRY RUN -- would POST'}",
        f"  request : POST {API}/alphas/{alpha}/submit",
        "  headers : (session cookies from state/wq_cookies.pkl)",
        "  body    : <none>   (the endpoint takes no payload)",
        "  timeout : 40s",
        f"  alpha   : {alpha}",
        f"  cell    : {decision['cell']}  [{decision['region']}/d{decision['delay']}]",
        f"  family  : {decision['family']}",
        f"  formula : {decision['formula']}",
        f"  why     : {decision['reason']}",
        f"  corr    : {note}",
    ])


# --------------------------------------------------------------------------------- status handling

def classify_429(body):
    """('daily'|'concurrent'|'ambiguous', why) from a 429 body.

    The only documented strings are the SIMULATION ones (tools/daily_budget.py:7-14):
    DAILY_SIMULATION_LIMIT_EXCEEDED clears at midnight ET, CONCURRENT_SIMULATION_LIMIT_EXCEEDED
    clears in minutes. For POST /submit the body taxonomy is MECHANISM: UNKNOWN -- no observation
    of a submit 429 body is recorded anywhere in this repo. That is exactly why 'ambiguous' stops
    the run instead of retrying, and why even a 'concurrent' reading is only trusted for
    MAX_ATTEMPTS_PER_ALPHA attempts: daily_budget.py records probes 20s apart answering
    DAILY / CONCURRENT / CONCURRENT for one exhausted daily allowance, so the string is not a
    reliable diagnosis on its own."""
    t = (body or "").upper()
    if "DAILY" in t:
        return "daily", "body names the DAILY limit -- clears at 00:00 ET, stop the run"
    if "CONCURRENT" in t:
        return "concurrent", "body names the CONCURRENT limit -- back off and retry"
    return "ambiguous", ("429 body matches no known limit string -- treated as DAILY (fail-closed); "
                         "submit-429 bodies are undocumented in this repo")


def classify(status, body):
    """(classification, disposition, note). disposition is RETRYABLE or TERMINAL."""
    if status in (200, 201):
        return "accepted", TERMINAL, "platform accepted the submission"
    if status == 403:
        return ("spent", TERMINAL,
                "403 = the platform ADJUDICATED this POST. The alpha's one lifetime attempt is "
                "gone. Never retry, never release the G6 slot.")
    if status == 408:
        return "timeout", RETRYABLE, "408 = never answered; the slot is returnable"
    if status == 429:
        kind, why = classify_429(body)
        return (f"throttled-{kind}", RETRYABLE if kind == "concurrent" else TERMINAL, why)
    return ("unexpected", TERMINAL,
            f"HTTP {status} is not in the handled set -- STOP and escalate to a human. "
            f"Guessing at an unknown status is how an alpha gets spent.")


# ------------------------------------------------------------------------------------ the one POST

def submit_one(alpha, decision, note, transport, live, ctx=None, sleep=time.sleep, now=time.time):
    """Issue at most MAX_ATTEMPTS_PER_ALPHA POSTs for one alpha. Returns a result dict.

    Sequence per attempt, and the order is the whole safety argument:
      1. kill switch read from disk        (a human can stop the machine here)
      2. reserve_submit()                  (atomic flock'd G6 ledger write -- BEFORE the request)
      3. journal 'intent' + fsync          (BEFORE the request)
      4. POST
      5. journal 'outcome'                 (AFTER; its ABSENCE is what blocks a second POST)

    Between (1) and (4) lie two local file writes. That is the window in which the kill switch
    cannot help; there is no way to close it further without moving the switch inside the socket.
    """
    ctx = ctx or {}
    journal = ctx.get("journal") or JOURNAL
    if live is not True:
        raise RuntimeError(f"submit_one called without live=True; pass {LIVE_FLAG} to spend a "
                           f"real submission")

    for attempt in range(1, MAX_ATTEMPTS_PER_ALPHA + 1):
        engaged, txt = kill_switch_engaged(ctx.get("kill"))
        if engaged:
            return {"alpha": alpha, "result": "killed", "attempts": attempt - 1,
                    "note": f"KILL SWITCH engaged ({ctx.get('kill') or KILL_SWITCH}): {txt}"}

        reserved, why = reserve_submit(alpha, decision["family"])
        if not reserved:
            return {"alpha": alpha, "result": "refused", "attempts": attempt - 1,
                    "note": f"G6 ledger refused the reservation: {why}"}

        url = f"{API}/alphas/{alpha}/submit"
        _append(journal, {"event": "intent", "alpha": alpha, "attempt": attempt,
                          "ts": now(), "date": _platform_date(), "method": "POST", "url": url,
                          "body": None, "cell": decision["cell"], "region": decision["region"],
                          "delay": decision["delay"], "family": decision["family"],
                          "reason": decision["reason"], "corr": note})

        try:
            r = transport.post(url, timeout=40)
        except Exception as e:                  # noqa: BLE001 -- ANY transport failure lands here
            # The request may have left the machine. `/check` cannot distinguish "never posted"
            # from "queued", so this is unknown, and unknown is terminal. Keep the G6 slot spent.
            _append(journal, {"event": "outcome", "alpha": alpha, "attempt": attempt,
                              "ts": now(), "status": None, "classification": "transport-error",
                              "disposition": TERMINAL, "error": repr(e)})
            return {"alpha": alpha, "result": "escalate", "attempts": attempt,
                    "note": (f"transport raised {e!r} -- the POST MAY have landed. Not retrying. "
                             f"Resolve by hand: GET {API}/alphas/{alpha} -- status/dateSubmitted decide. "
                             f"DO NOT re-POST. GET /alphas/{alpha} (status + dateSubmitted) is the ONLY disambiguator. /alphas/{alpha}/submit answers 404 for a SUBMITTED alpha too -- measured 2026-08-05 (E5ejp6JL, submitted, 404) and re-confirmed 2026-08-16 on mL516W9W while ACTIVE. Reading 404 as 'not submitted' is how an alpha gets re-POSTed into a 403 that spends its slot forever.")}

        status = getattr(r, "status_code", None)
        body = getattr(r, "text", "") or ""
        cls, disp, cnote = classify(status, body)
        _append(journal, {"event": "outcome", "alpha": alpha, "attempt": attempt, "ts": now(),
                          "status": status, "classification": cls, "disposition": disp,
                          "body": body[:400], "note": cnote})

        if disp == RETRYABLE:
            release_submit(alpha)               # 408 / 429-concurrent: never adjudicated
            if attempt < MAX_ATTEMPTS_PER_ALPHA:
                sleep(BACKOFF_S[min(attempt - 1, len(BACKOFF_S) - 1)])
                continue
            return {"alpha": alpha, "result": "retry-exhausted", "attempts": attempt,
                    "note": f"{status} {cls}: {cnote} (slot returned, {attempt} attempts)"}

        if cls == "accepted":
            return {"alpha": alpha, "result": "accepted", "attempts": attempt,
                    "note": f"HTTP {status}: {cnote}"}
        if cls == "spent":
            return {"alpha": alpha, "result": "spent", "attempts": attempt,
                    "note": f"HTTP 403: {cnote}"}
        return {"alpha": alpha, "result": "escalate", "attempts": attempt,
                "note": f"HTTP {status} ({cls}): {cnote}", "stop_run": True}


# ------------------------------------------------------------------------------------------- run

def run(cfg, transport=None, live=False, ctx=None, out=print, sleep=time.sleep, now=time.time):
    """Plan every candidate, print exactly what would be POSTed, and (only when live) POST."""
    ctx = ctx or {}
    results = []
    engaged, txt = kill_switch_engaged(ctx.get("kill"))
    if engaged:
        out(f"REFUSED: kill switch present ({ctx.get('kill') or KILL_SWITCH}): {txt}")
        return results

    decisions, err = load_decisions(ctx.get("decisions"), now=now())
    if err:
        out(f"REFUSED: {err}")
        return results

    records = read_journal(ctx.get("journal"))

    # BOUND THE CANDIDATE LIST ITSELF. A 403 spends an alpha permanently without consuming a
    # success, so capping successes leaves the number of alphas this run can DESTROY equal to the
    # length of a file written elsewhere. Refuse the surplus loudly rather than trimming quietly --
    # a silent truncation reads as "everything was considered".
    order = sorted(decisions)
    if len(order) > MAX_DECISIONS_PER_RUN:
        out(f"REFUSED: decisions file names {len(order)} alphas, above MAX_DECISIONS_PER_RUN="
            f"{MAX_DECISIONS_PER_RUN}. A 403 spends an alpha permanently, so the blast radius is "
            f"the LIST length, not the success cap. Split the file or raise the constant "
            f"deliberately.")
        return results

    posted = 0
    for alpha in order:
        if posted >= MAX_ALPHAS_PER_RUN:
            out(f"STOP: run cap reached -- {MAX_ALPHAS_PER_RUN} alphas POSTed this run "
                f"(BLAST RADIUS cap)")
            break
        d = decisions[alpha]
        ok, why = preflight(alpha, d, cfg, records, ctx)
        if not ok:
            out(f"SKIP {alpha}: {why}")
            results.append({"alpha": alpha, "result": "skipped", "note": why})
            continue

        out(describe(alpha, d, why, live))
        if not live:
            results.append({"alpha": alpha, "result": "dry-run", "note": why})
            continue

        res = submit_one(alpha, d, why, transport, True, ctx, sleep=sleep, now=now)
        results.append(res)
        out(f"  -> {res['result']}: {res['note']}")
        posted += 1 if res.get("attempts", 0) > 0 else 0   # count POSTs that actually left
        records = read_journal(ctx.get("journal"))
        if res.get("stop_run") or res["result"] in ("killed", "escalate"):
            out("STOP: run halted -- a human must look at this before anything else is POSTed.")
            break
    return results


def _session():
    import pickle

    import requests
    c = pickle.load(open(ROOT / "state/wq_cookies.pkl", "rb"))
    s = requests.Session()
    if isinstance(c, dict):
        s.cookies.update(c)
    else:
        for x in c:
            s.cookies.set_cookie(x)
    return s


def main(argv=None, transport=None, out=print, ctx=None, sleep=time.sleep, now=time.time):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)  # draw-3 MINOR 9: `--i` is not live
    ap.add_argument("--region", required=True, help="the SINGLE region this run may submit into")
    ap.add_argument("--delay", required=True, type=int, help="the SINGLE delay this run may submit into")
    ap.add_argument(LIVE_FLAG, dest="live", action="store_true",
                    help="spend REAL, IRREVERSIBLE submissions. Without this the run is a dry run.")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)

    cfg = {"region": a.region, "delay": a.delay}
    if not a.live:
        out(f"=== DRY RUN (default). Nothing will be POSTed. Add {LIVE_FLAG} to spend "
            f"submissions. ===")
    else:
        out(f"=== LIVE. Up to {MAX_ALPHAS_PER_RUN} alphas may be IRREVERSIBLY spent. "
            f"Kill switch: touch {KILL_SWITCH} ===")
        if transport is None:
            transport = _session()
    return run(cfg, transport, a.live, ctx, out=out, sleep=sleep, now=now)


if __name__ == "__main__":
    main()
