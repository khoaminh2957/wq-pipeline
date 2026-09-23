#!/usr/bin/env python3
"""What the auto-submitter is allowed to spend, and what it must never spend.

THE THREE THINGS THIS REFUSES, and the measurement behind each (all counts re-derived
2026-08-13 from state/submit_budget.jsonl (49 rows) and state/funnel/submit_log.jsonl (141 rows)):

  1. DAILY QUOTA. `REGULAR_SUBMISSION` on /alphas/<id>/check carries `limit: 4` -- read straight
     off the platform, cached in state/submit_quota_seen.json as
     `{"result":"PASS","value":2,"limit":4,...,"from":"1YppwgwX"}` written 2026-08-10T09:59 ET.
     EX-ANTE: the number is the platform's, not ours.

     The stored note saying "4/day" is therefore RIGHT, and the round-8 reading that contradicted
     it -- 9 rows on 2026-07-30 and 7 on 2026-07-29 -- was counting a different thing. Two
     reasons, both verified:

       a. submit_budget.jsonl rows are G6 SLOT RESERVATIONS written by harness/guards.record_submit
          BEFORE the POST, not landed submissions. Of the 9 rows dated 07-30 only 7 ever returned
          200; le391QLA and Vk35LRM0 are 403s. Of the 7 rows dated 07-29 only ONE landed -- the
          other six are the backfilled 403s (N1R7AKN8, O0xVZpVd, Vk35PY2J, gJ98Vqjl, pwKZl6Zg,
          vRvNrZXw), each carrying `note: 403 adjudicated`.
       b. those dates are LOCAL dates. harness/guards.py only started keying this ledger on the
          Eastern day at commit 693fb97 (2026-08-09); before that it was local, then UTC. A local
          (UTC+7) day spans 17:00Z..17:00Z and therefore straddles TWO Eastern days, whose boundary
          is 04:00Z. Seven landed submissions inside one local day is at most 4+4 across two
          Eastern days, so it never contradicted the cap.

     Every date at or after 2026-08-09 is Eastern-keyed; the max landed on any such day is 3.
     So: 4/day is a HARD platform cap, and nothing in the ledger ever exceeded it.

  2. BANNED FIELDS. state/banned_fields.json, 74 fields, `by_alpha` covering 10 alphas, the newest
     of them reserved 2026-07-29. Of the 30 alphas that returned ok in the submit log, 26 are
     absent from it, and ALL 26 are dated after 2026-07-29. It also over-bans in the other
     direction: Xg8oQJRl (403) and zqRN8LGE (timeout) are listed but never went live, so their
     fields are not in the book. Grepped the whole tree: no file anywhere writes this JSON -- ten
     readers, zero
     writers -- and it is gitignored by `state/*.json`, so the staleness leaves no trace in git.
     It is also read nowhere on the submit path: `grep -n banned` over submit_alphas.py,
     gentle_submit.py, complete_submit.py, wq_client.py and harness/guards.py returns nothing. The
     ban is enforced only at the SIM-LAUNCH gate (tools/funnel/precheck_lib.py), and there as a
     module-level constant evaluated at import, so a long-lived process never sees an update.

  3. FAMILY. See check_family(). Short version: as deployed, the rule refuses almost nothing.

WHAT THIS MODULE IS NOT. It never POSTs. It holds no session of its own; a caller that wants the
platform's own count passes one in.
"""
import argparse
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER = ROOT / "state/submit_budget.jsonl"
BANNED_PATH = ROOT / "state/banned_fields.json"
SUBMIT_LOG = ROOT / "state/funnel/submit_log.jsonl"

CAP = 4          # platform REGULAR_SUBMISSION limit. EX-ANTE, read off /alphas/<id>/check.
SUBMISSIONS_FEED = "https://api.worldquantbrain.com/users/self/activities/submissions"


def platform_date():
    """Today in the PLATFORM's day, which is US Eastern -- not UTC and not local.

    Duplicated from tools/daily_budget.platform_date() and harness/guards._platform_date() rather
    than imported: importing daily_budget pulls in submit_alphas, which builds a live session at
    import time, and a budget reader must be safe to call offline and inside a test.

    zoneinfo rather than a hardcoded -4 because the offset changes at the EST/EDT switch."""
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo("America/New_York")).date().isoformat()


# ------------------------------------------------------------------ 1. daily quota

def ledger_used(day=None, path=None):
    """(used, why). `used is None` means THE COUNT COULD NOT BE ESTABLISHED -- never zero.

    Distinguishing "no rows today" from "could not read" is the whole point. An absent or
    unreadable ledger returning 0 reads as a full allowance, which is the direction that destroys
    alphas: on 2026-07-30 our own ledger said 3/4 while the platform said 4/4, and the two POSTs
    that went out on that reading (le391QLA, Vk35LRM0) each took a 403, which ADJUDICATES and so
    spends the alpha's single lifetime attempt permanently.

    A malformed line counts as USED. harness/guards.submit_allowed() skips it, which is right for
    a per-alpha lock (a line it cannot read cannot name this alpha) and wrong here (a line it
    cannot read may well be today's fourth submit)."""
    p = pathlib.Path(path) if path else LEDGER
    day = day or platform_date()
    if not p.exists():
        return None, f"ledger absent at {p} — cannot establish today's count"
    used = bad = 0
    try:
        text = p.read_text()
    except OSError as e:
        return None, f"ledger unreadable ({e}) — cannot establish today's count"
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            d = r["date"]
        except (ValueError, KeyError, TypeError):
            bad += 1
            continue
        if d == day:
            used += 1
    if bad:
        return used + bad, f"{used} row(s) dated {day} + {bad} unparseable row(s) counted as used"
    return used, f"{used} row(s) dated {day} (ET)"


def platform_used(session, day=None):
    """(used, why) from the submissions activity feed -- an authority independent of our ledger.

    The ledger records what WE believe we POSTed. It cannot see a submission made from the web UI
    or by another process, and it is what read 3/4 against a platform 4/4 on 2026-07-30."""
    day = day or platform_date()
    try:
        r = session.get(SUBMISSIONS_FEED, timeout=45)
        if r.status_code != 200:
            return None, f"submissions feed HTTP {r.status_code}"
        recs = r.json()["records"]["records"]
    except Exception as e:                        # noqa: BLE001 - any failure is "cannot read"
        return None, f"submissions feed unreadable ({type(e).__name__}: {e})"
    return next((v for d, v in recs if d == day), 0), f"feed reports {day}"


def remaining_today(session=None, day=None, path=None):
    """How many submits are left in the platform's Eastern day. FAILS CLOSED to 0.

    `used` is the MAXIMUM of every source that answered, never the minimum and never the newest:
    each source can only miss submissions, none can invent one, so the largest reading is the only
    one that cannot overspend.

    Without a session this is LEDGER-ONLY, and a ledger-only reading is an UPPER BOUND on what is
    left -- it is blind to anything submitted outside this pipeline. `authoritative` says so; the
    number is not padded with an invented safety margin."""
    day = day or platform_date()
    lu, lwhy = ledger_used(day, path)
    pu, pwhy = (platform_used(session, day) if session is not None else (None, "no session given"))
    readings = [x for x in (lu, pu) if x is not None]
    if not readings:
        return {"remaining": 0, "cap": CAP, "used": None, "day": day, "authoritative": False,
                "why": f"NO SOURCE READABLE — ledger: {lwhy}; platform: {pwhy}. "
                       "Failing closed at 0: an unspent submit costs a day, an overspent one "
                       "costs the alpha forever."}
    used = max(readings)
    return {"remaining": max(0, CAP - used), "cap": CAP, "used": used, "day": day,
            "authoritative": pu is not None,
            "why": f"ledger: {lwhy}; platform: {pwhy}; used = max = {used}/{CAP}"}


# ------------------------------------------------------------------ 2. banned fields

def load_banned(path=None):
    """The banned set. Fails CLOSED: absent or corrupt RAISES rather than returning empty.

    tools/funnel/precheck_lib._load_banned() returns an empty set when the file is absent, which is
    a defensible default for a sim gate (a sim is cheap and reversible). It is not defensible here.
    Returning empty on the irreversible path silently converts "I could not check" into "nothing is
    banned"."""
    p = pathlib.Path(path) if path else BANNED_PATH
    if not p.exists():
        raise FileNotFoundError(f"{p} absent — cannot prove this alpha reuses no submitted field")
    d = json.loads(p.read_text())                 # a corrupt file must raise, not read as empty
    return frozenset(d.get("banned_fields") or [])


def check_banned(formula, path=None):
    """(ok, why). Refuses when the formula names any field used by an already-submitted alpha.

    Field extraction is tools/funnel/precheck_lib.extract_fields_grammar -- the same parser the sim
    gate uses, so the two gates cannot disagree about what a field is. The file is read on every
    call, not cached at import: precheck_lib's module-level `BANNED` is a startup snapshot and a
    long-running submitter would never see a newly-burnt field."""
    sys.path.insert(0, str(ROOT / "tools/funnel"))
    from precheck_lib import extract_fields_grammar
    banned = load_banned(path)
    fields, _ = extract_fields_grammar(formula or "")
    hits = sorted(fields & banned)
    if hits:
        return False, (f"banned field(s) {hits} — already used by a submitted alpha, so this "
                       "formula's self-correlation against the live book is not measurable-clean")
    return True, f"no banned field among {len(fields)} field token(s)"


def banned_coverage(ledger=None, log=None, path=None):
    """(covered, landed, missing) — is the ban list current with what has actually been submitted?

    A ban list that omits submitted alphas cannot answer the question it exists to answer, and
    there is no writer in the tree to keep it current, so this has to be measured rather than
    assumed. Compares `by_alpha` against every alpha that returned ok in the submit log."""
    p = pathlib.Path(path) if path else BANNED_PATH
    try:
        covered = set((json.loads(p.read_text()).get("by_alpha") or {}))
    except (OSError, ValueError):
        covered = set()
    landed = set()
    lp = pathlib.Path(log) if log else SUBMIT_LOG
    if lp.exists():
        for line in lp.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("ok"):
                landed.add(r.get("alpha"))
    return covered, landed, sorted(landed - covered)


# ------------------------------------------------------------------ 3. family

def submitted_families(path=None):
    """family key -> [alpha, ...] over the WHOLE ledger, not just today."""
    p = pathlib.Path(path) if path else LEDGER
    out = {}
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        try:
            r = json.loads(line)
            out.setdefault(r["family"], []).append(r["alpha"])
        except (ValueError, KeyError, TypeError):
            continue
    return out


def check_family(alpha, family, path=None):
    """(ok, why). Refuses when a sibling of the same mechanic already spent a POST -- ever.

    PROVENANCE: **POST-HOC**, and weakly so. This is not a platform rule. No submission check
    mentions a family; the platform's only per-alpha rule is G6, one POST per alpha for life. The
    family cap entered the code as bughunt owner decision B10 O7, from the observation that a pool
    of one mechanic yields many gems and one submission.

    THE OBSERVATION IS REAL AND ITS CAUSE IS UNKNOWN. Grouping state/funnel/winners.csv +
    near_misses.csv (812 rows, 807 distinct alphas) by `dataset`: 26 datasets produced at least one
    landed submission and only 3 produced two or more, i.e. 30 landed submissions over 26 datasets.
    But only 49 of those 807 alphas were EVER POSTed, so "one per family" is at least as much a
    description of what an operator chose to attempt as of anything that refused a sibling. In the
    141-row submit log the candidate refusal mechanisms rank:

        cell-already-unlocked  23   — all 23 share ONE body, "every cell already unlocked
                                      (Model 19/3, Price Volume 18/3)". Those cells were saturated
                                      long before; not a sibling killing a sibling.
        family cap fired        2   — e7xvEQbM and rKPqeRVa
        self-corr wall fired    1   — e7xvEQbM at self=0.7849
        prod-breach wall        1   — e7x0G7ag

    So the ledger contains no mechanism that killed 26 gems. MECHANISM: UNKNOWN. The experiment
    that would settle it: POST a measured-clean sibling into a cell that is still short, after a
    first sibling has gone ACTIVE, and read whether the refusal is the self-corr wall or nothing at
    all. Nobody has run it.

    AND AS DEPLOYED THE RULE REFUSES ALMOST NOTHING. harness/guards.submit_allowed() scopes it to
    `r["date"] == today`, so it delays a sibling by a day rather than killing it. Worse, the key
    itself collapses: submit_alphas._family_of() falls back to the alpha id whenever winners.csv
    has no row or its `dataset` cell holds a category label containing '/'. Of the 49 ledger rows,
    13 already carry family == alpha_id and 8 carry a '/' label that _family_of now maps to the
    alpha id -- replaying all 49 through the current key function yields 49 DISTINCT keys and zero
    collisions. It would have refused none of them.

    This function implements the LIFETIME reading asked for, which is strictly stronger than what
    ships. Its measured cost on the record: 3 of 30 landed submissions had a same-`dataset` sibling
    already landed (model27 x3, Analyst x2, Institutions/Institutions x2), so ~10% of real
    submissions would have been refused -- and Institutions was a legitimate second submission into
    a cell that was still short. Carry it as a WARNING-WEIGHT rule, not as a platform gate."""
    fams = submitted_families(path)
    sibs = [a for a in fams.get(family, []) if a != alpha]
    if sibs:
        return False, (f"family {family!r} already spent a POST on {sibs} — POST-HOC rule, "
                       "mechanism unknown, ~10% false-refusal rate on the historical record")
    return True, f"no prior POST recorded for family {family!r}"


# ------------------------------------------------------------------ the call site

def preflight(alpha, formula, family, session=None, ledger=None, banned=None):
    """(ok, reasons) — every budget-side refusal, evaluated for one alpha before any POST.

    THIS IS THE CALL SITE. Each guard above is reachable from a path that actually runs -- `python3
    tools/submit_budget.py <alpha> --formula ... --family ...` runs exactly this. A guard whose only
    caller is its own test is this project's confirmed failure mode: a wall function was found on
    2026-08-13 whose reader was wired and whose writer never existed.

    Returns ok=True only when every guard passed. Nothing here is overridable."""
    reasons, ok = [], True

    b = remaining_today(session=session, path=ledger)
    if b["remaining"] <= 0:
        ok = False
        reasons.append(f"QUOTA: 0 of {b['cap']} left for {b['day']} ET — {b['why']}")
    else:
        reasons.append(f"quota: {b['remaining']}/{b['cap']} left"
                       + ("" if b["authoritative"] else " (LEDGER-ONLY — an upper bound)"))

    try:
        bok, bwhy = check_banned(formula, path=banned)
    except (FileNotFoundError, ValueError) as e:
        bok, bwhy = False, f"ban list unusable ({e})"
    if not bok:
        ok = False
        reasons.append(f"BANNED: {bwhy}")
    else:
        reasons.append(f"banned: {bwhy}")

    _, _, missing = banned_coverage(path=banned)
    if missing:
        ok = False
        reasons.append(f"BANNED-STALE: {len(missing)} landed alpha(s) never added to the ban list "
                       f"({', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}) — no writer "
                       "exists in the tree, so the list cannot prove this formula is clean")

    fok, fwhy = check_family(alpha, family, path=ledger)
    if not fok:
        ok = False
        reasons.append(f"FAMILY: {fwhy}")
    else:
        reasons.append(f"family: {fwhy}")

    return ok, reasons


def main(argv=None):
    ap = argparse.ArgumentParser(description="submit-budget preflight (read-only; never POSTs)")
    ap.add_argument("alpha", nargs="?")
    ap.add_argument("--formula", default="")
    ap.add_argument("--family", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if not a.alpha:
        b = remaining_today()
        cov, landed, missing = banned_coverage()
        if a.json:
            print(json.dumps({**b, "banned_covered": len(cov), "landed": len(landed),
                              "banned_missing": missing}))
            return 0
        print(f"remaining {b['remaining']}/{b['cap']} for {b['day']} ET"
              f"{'' if b['authoritative'] else '  [ledger-only]'}")
        print(f"  {b['why']}")
        print(f"ban list covers {len(cov)} of {len(landed)} landed alphas; {len(missing)} missing")
        return 0

    ok, reasons = preflight(a.alpha, a.formula, a.family or a.alpha)
    if a.json:
        print(json.dumps({"alpha": a.alpha, "ok": ok, "reasons": reasons}))
    else:
        print(f"{a.alpha}: {'CLEAR' if ok else 'REFUSED'}")
        for r in reasons:
            print(f"  - {r}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
