#!/usr/bin/env python3
"""submit_alphas.py — submit alphas to the real WQB account (Khoa authorized 2026-07-22).
POSTs /alphas/{id}/submit one at a time; the platform re-runs all IS+correlation checks and rejects
anything not genuinely passing, so only truly-submittable alphas go through. Prints each result and
records to state/funnel/submit_log.jsonl. Usage: python3 tools/submit_alphas.py <id> [<id>...]"""
import pickle, requests, json, time, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from harness.guards import reserve_submit, release_submit
ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG = ROOT / "state/funnel/submit_log.jsonl"

def session():
    c = pickle.load(open(ROOT / "state/wq_cookies.pkl", "rb"))
    s = requests.Session()
    if isinstance(c, dict): s.cookies.update(c)
    else:
        for x in c: s.cookies.set_cookie(x)
    return s

def _family_of(aid):
    """Dataset family for the G6 per-family/day cap (B10 O7). Looked up from the ledgers'
    'dataset' column; falls back to the alpha_id if unknown, so an off-ledger alpha keeps the
    1-per-alpha cap without a spurious family. Enables the family/day throttle that was inert
    while alpha_id was passed as the family. Reads near_misses.csv too: since 2026-07-25 a
    prod/self-walled zero-fail lives there, and the family cap must still see its dataset."""
    import csv
    for wc in (ROOT / "state/funnel/winners.csv", ROOT / "state/funnel/near_misses.csv"):
        if not wc.exists():
            continue
        try:
            for row in csv.DictReader(open(wc)):
                if row.get("alpha") == aid and row.get("dataset"):
                    ds = row["dataset"]
                    # The column is written by several producers and is NOT always a dataset. Some
                    # rows carry a CATEGORY label there instead -- `Risk/Risk`, `News/News
                    # Sentiment`, `Option/Option Analytics` -- and a category is not a family. On
                    # 2026-08-03 that blocked `rKPqeRVa`: it and `3qeOEbOO` come from different runs
                    # (PX51527r02 vs OT30254r04) and measure self-corr 0.6289 apart, but both rows
                    # said `Risk/Risk`, so the day's family cap treated them as siblings and refused
                    # the submit that would have completed the Risk cell.
                    # A category label always contains '/'; a real family key never does. Falling
                    # back to the alpha id keeps the 1-POST-per-alpha cap without inventing a family
                    # -- exactly what this function's fallback exists for.
                    if "/" in ds:
                        return aid
                    return ds
        except Exception:
            pass
    return aid

TRIPLE = 3                                   # a pyramid cell UNLOCKS at this many alphas
_CELL_CACHE = ROOT / "state/pyramid_cell_counts.json"
_CELL_MEMO = None                            # per-process, invalidated on a successful submit
# `_dry_check` referenced API and nothing ever defined it. Its NameError was swallowed by a bare
# `except Exception`, so the loop retried for the full 180s budget and then failed OPEN — the one
# read of the platform's own adjudicated check set before an irreversible POST has been dead the
# whole time, at ~180s of wall clock per submit. A FAIL it would have caught reaches the POST as
# a 403, which spends the alpha permanently and one of four daily slots.
API = "https://api.worldquantbrain.com"

_QUOTA_CACHE = ROOT / "state/submit_quota_seen.json"
_FIELD_CAT = None
# close/open/vwap and friends carry the Price Volume category but are not rows in
# fields_all.jsonl, so a formula holding only the carrier would otherwise look category-less.
_RAW_PV = {"close", "open", "high", "low", "vwap", "volume", "returns", "adv20", "cap"}


def _field_cat():
    """field id -> category name, from the local crawl OVERLAID with anything resolved live.

    `fetched/fields_all.jsonl` alone is not enough and the gap is not small: of 3,808 fields
    resolved field-by-field from the platform, **2,717 (71%) are absent from the crawl** and one
    (`capital_expenditure_total`) carries the wrong category there -- Model locally, Other on the
    platform. Model is full and Other sits at 1/3, so that single row flips a gate verdict from
    "advances Other" to "every cell already unlocked", which `submit_one` records as a PERMANENT
    write-off of the alpha. state/fieldmap.json comes from /data-fields/<id> and wins on conflict."""
    global _FIELD_CAT
    if _FIELD_CAT is None:
        _FIELD_CAT = {}
        for line in open(ROOT / "fetched/fields_all.jsonl"):
            try:
                d = json.loads(line)
            except Exception:
                continue
            c = d.get("category") or {}
            _FIELD_CAT[d["id"]] = (c.get("name") if isinstance(c, dict) else c) or "?"
        try:
            for fid, v in json.load(open(ROOT / "state/fieldmap.json")).items():
                if (v or {}).get("category"):
                    _FIELD_CAT[fid] = v["category"]
        except Exception:
            pass
    return _FIELD_CAT


def _cell_counts(s, region, delay):
    """Live alphaCount per pyramid cell, with a cache so a 429 does not freeze submissions.

    /users/self/activities/pyramid-alphas is the PLATFORM's own counter and is what the Genius
    dashboard shows. Do NOT derive this by summing alpha["pyramids"] over the book -- the two
    disagree, and the alpha record is the one that overcounts."""
    import re as _re
    # Memoise within the process. Taking the max of 3 reads is right but it tripled this
    # endpoint's call volume, and a submit batch calls it once per alpha -- 12 requests for four
    # alphas, on an account that returns 429 under exactly that pattern. The memo is INVALIDATED
    # by a successful submit (see _invalidate_cells), so a cell that fills mid-batch is still seen.
    global _CELL_MEMO
    mkey = (region, delay)
    if _CELL_MEMO and _CELL_MEMO["key"] == mkey and time.time() - _CELL_MEMO["ts"] < 300:
        return _CELL_MEMO["counts"], f"memo {int(time.time()-_CELL_MEMO['ts'])}s"

    def _read():
        r = s.get("https://api.worldquantbrain.com/users/self/activities/pyramid-alphas",
                  timeout=60)
        if r.status_code != 200:
            return None
        return {p["category"]["name"]: p["alphaCount"] for p in r.json()["pyramids"]
                if p["region"] == region and p["delay"] == delay}

    # TAKE THE MAX OF SEVERAL READS. This endpoint intermittently under-reports: polling it seven
    # times on 2026-08-02 gave Analyst 3 / Earnings 2 / Price Volume 22 on six reads and
    # Analyst 2 / Earnings 1 / Price Volume 18 on the seventh, with no submission in between.
    #
    # The two errors are not symmetric, so the guard must not be. An UNDER-count says a full cell
    # still needs alphas and lets an irreversible submit be spent on nothing. An OVER-count only
    # withholds a submit until the next read. Bias to the high reading: max is the safe direction.
    seen = []
    for attempt in range(4):
        try:
            v = _read()
            if v is not None:
                seen.append(v)
                if len(seen) >= 3:
                    break
        except Exception:
            pass
        time.sleep(6 * (attempt + 1))
    if seen:
        out = {k: max(v.get(k, 0) for v in seen) for k in set().union(*seen)}
        # MERGE, never replace. Measured 2026-08-10 20:03: harness13/crawl_pyramid.py had just
        # written all 16 (region, delay) pairs and 211 cells to this same path, and this line
        # clobbered it back to one pair 26 seconds later, failing REQ-L3-06 and REQ-DR-02 in a way
        # that looked like the crawler had never run. Two owners, one path, two schemas.
        # The file is now a SUPERSET: the flat region/delay/counts keys this module has always
        # read stay exactly where they were, and any `pairs` list written by the crawler is
        # carried forward with this pair's fresh counts folded in.
        doc = {}
        try:
            doc = json.load(open(_CELL_CACHE))
        except Exception:
            doc = {}
        pairs = [p for p in (doc.get("pairs") or [])
                 if not (p.get("region") == region and p.get("delay") == delay)]
        pairs.append({"region": region, "delay": delay, "counts": out, "ts": time.time()})
        doc.update({"region": region, "delay": delay, "ts": time.time(), "counts": out,
                    "pairs": pairs})
        json.dump(doc, open(_CELL_CACHE, "w"))
        _CELL_MEMO = {"key": mkey, "counts": out, "ts": time.time()}
        return out, f"live (max of {len(seen)})"
    try:
        c = json.load(open(_CELL_CACHE))
        if c["region"] == region and c["delay"] == delay and time.time() - c["ts"] < 6 * 3600:
            return c["counts"], f"cached {int((time.time()-c['ts'])/60)}min old"
    except Exception:
        pass
    return None, "unreadable"


_PENDING_CELLS = ROOT / "state/submitted_cells_today.jsonl"
_LAST_GATE = {}      # aid -> (cells, counts as read at gate time)


def _platform_day():
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        from daily_budget import platform_date
        return platform_date()
    except Exception:
        return ""


def _record_submitted_cells(aid, cats, base=None):
    """Remember which cells an alpha just entered, and the counts as they read AT THAT MOMENT.

    The baseline is what makes this self-cancelling. Adding a flat +1 per pending submit would
    double-count the moment the platform catches up -- a cell at 1/3 would read 2 (platform) + 1
    (pending) = 3 and block a legitimate third submit for the rest of the day. Storing the base
    lets the adjustment apply only while the counter still shows the pre-submit number."""
    try:
        with open(_PENDING_CELLS, "a") as f:
            f.write(json.dumps({"alpha": aid, "cells": sorted(cats), "date": _platform_day(),
                                "base": {c: (base or {}).get(c, 0) for c in cats}}) + "\n")
    except Exception:
        pass


def _submitted_today_by_cell(live):
    """cell -> alphas we POSTed successfully in THIS platform day but the counter has not credited.

    Bridges the lag between a 200 on /submit and pyramid credit, which follows the alpha going
    ACTIVE: kqZpOOJK returned 200 on 2026-08-02 and Earnings still read 2/3 minutes later. Three
    alphas aimed at one 2/3 cell would each see 2/3 and two slots would be spent for nothing."""
    today, out, seen = _platform_day(), {}, set()
    if not (today and _PENDING_CELLS.exists()):
        return {}
    try:
        for line in _PENDING_CELLS.open():
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("date") != today or d.get("alpha") in seen:
                continue
            seen.add(d["alpha"])
            base = d.get("base") or {}
            for c in d.get("cells") or []:
                # Only while the platform still reads the pre-submit number. Once it has credited
                # the alpha, live already contains it and adding again would over-count.
                if live.get(c, 0) <= base.get(c, 0):
                    out[c] = out.get(c, 0) + 1
    except Exception:
        return {}
    return out


def _cell_gate(s, aid):
    """Khoa 2026-07-31: stop spending submits on alphas whose cells are already unlocked.

    A cell counts as complete at 3 alphas and a 4th adds nothing to Genius rank -- Model sat at 18
    and Price Volume at 14 while ten cells were empty, so 30 of 42 pyramid memberships in the book
    were pure waste. Every alpha built on the standard carrier necessarily joins Price Volume, so
    the test is 'does ANY of its categories still sit below 3', not 'are all of them incomplete'.

    Fail CLOSED: an unverifiable alpha is withheld, not submitted. A wrong allow is irreversible
    (it spends a slot and raises every sibling's prod-corr to self-corr), a wrong block only waits."""
    import re as _re
    a, last = None, None
    for attempt in range(3):
        r = s.get(f"https://api.worldquantbrain.com/alphas/{aid}", timeout=60)
        if r.status_code == 401:
            # Distinguish an expired session from a malformed alpha: both used to surface as
            # "unreadable", which sent me hunting a rate limit that was never there.
            return False, "cell gate: session expired (401) -- re-auth, then retry"
        if r.status_code == 200:
            try:
                a = r.json()
                break
            except Exception:
                pass
        last = r.status_code
        time.sleep(6 * (attempt + 1))
    if a is None:
        # 429 and 401 need opposite responses -- back off vs re-auth -- so never fold them into
        # one "unreadable". Reading a 429 body as a malformed alpha sent me looking for a bug
        # in the parser when the session had simply expired underneath it.
        if last == 429:
            return False, "cell gate: rate-limited (429) -- back off and retry, alpha untouched"
        return False, f"cell gate: alpha unreadable after 3 tries (last HTTP {last})"
    try:
        code = a["regular"]["code"]
        st = a["settings"]
    except Exception as e:
        return False, f"cell gate: alpha payload missing {str(e)[:40]}"
    fc = _field_cat()
    toks = set(_re.findall(r"[A-Za-z_][A-Za-z0-9_]*", code))
    cats = {fc[t] for t in toks if t in fc}
    if toks & _RAW_PV:
        cats.add("Price Volume")
    if not cats:
        return False, "cell gate: no data category recognised in the formula"

    counts, how = _cell_counts(s, st["region"], st["delay"])
    if counts is None:
        return False, "cell gate: pyramid counts unreadable -- withheld rather than guessed"
    # The platform's counter LAGS a submission: on 2026-08-02 kqZpOOJK returned SUBMITTED 200 and
    # Earnings still read 2/3 minutes later, because pyramid credit follows the alpha going ACTIVE.
    # A batch of three aimed at one 2/3 cell would therefore see 2/3 three times and spend two
    # slots for nothing. Count what THIS platform-day has already submitted into each cell and add
    # it -- the local ledger is authoritative for our own POSTs, which is exactly the gap the
    # platform counter has not closed yet.
    _LAST_GATE[aid] = (sorted(cats), dict(counts))   # a successful POST records what it filled
    counts = dict(counts)
    for c, n in _submitted_today_by_cell(counts).items():
        counts[c] = counts.get(c, 0) + n
    open_cells = {c: counts.get(c, 0) for c in cats if counts.get(c, 0) < TRIPLE}
    if not open_cells:
        # "Every cell is full" is a PERMANENT verdict, so it may only be issued when every field
        # in the formula was actually IDENTIFIED. An unrecognised token is not a field with no
        # category -- it is a field we failed to look up, and its category could be the open cell
        # this alpha exists to fill. Withhold TRANSIENTLY instead, so a later run reconsiders it.
        # A FIELD is a bare identifier; an OPERATOR is always followed by "(". Matching on the
        # name alone flagged rank/ts_delta/add as unknown fields and would have withheld every
        # submit ever. Take only identifiers that are NOT call targets.
        called = set(_re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", code))
        # ...and a FASTEXPR keyword is not a field either. Every generated formula ends in
        # `filter=true`, so `filter` and `true` were flagged on EVERY alpha and this branch could
        # never issue its permanent verdict at all. Drop named parameters (identifier followed by
        # `=`) and the boolean literals.
        params = set(_re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*=", code))
        KEYWORDS = {"true", "false"}
        unknown = sorted(t for t in toks if t not in fc and t not in _RAW_PV
                         and t not in called and t not in params and t not in KEYWORDS
                         and _re.fullmatch(r"[a-z][a-z0-9_]{3,}", t))
        if unknown:
            return False, (f"cell gate: {len(unknown)} field(s) not in the category map "
                           f"({', '.join(unknown[:4])}) -- cannot prove the cells are full, "
                           f"withheld for re-check rather than written off")
        full = ", ".join(f"{c} {counts.get(c, 0)}/{TRIPLE}" for c in sorted(cats))
        return False, f"cell gate: every cell already unlocked ({full}) [{how}]"
    adds = ", ".join(f"{c} {n}/{TRIPLE}" for c, n in sorted(open_cells.items()))
    return True, f"cell gate: advances {adds} [{how}]"


def _only_errors(body):
    """True when a rejection body contains ERROR results but not a single FAIL.

    The distinction decides whether the alpha is dead or merely unlucky, so it is read from the
    parsed checks -- never from a substring. The bodies are also stored at 2000 chars now, not 400:
    the truncated version cut off before the failing check in every 403 this project has logged,
    which is why three separate rejections had to be re-diagnosed against the live API instead of
    being read straight out of the ledger."""
    try:
        j = json.loads(body)
    except Exception:
        return False
    results = [c.get("result") for sec in j.values() if isinstance(sec, dict)
               for c in sec.get("checks", []) if isinstance(c, dict)]
    return "ERROR" in results and "FAIL" not in results


def _quota_ok(s, aid):
    """Read the platform's OWN daily submission quota before spending the alpha's one POST.

    `REGULAR_SUBMISSION` on /alphas/<id>/check is the platform-side counter (limit 4/day). It is
    visible for free BEFORE submitting, and when it reads FAIL the POST is refused with a 403 --
    which, under G6, ADJUDICATES and therefore SPENDS the alpha's single lifetime attempt. That is
    how Vk35LRM0 (prod 0.696, sharpe 2.36, fitness 1.68, a clean gem from a diversifying dataset)
    was lost on 2026-07-30: our own ledger said 3/4 used, the platform said 4/4. Never POST into a
    quota that is already exhausted.

    /check is ASYNC: it answers 200 with an EMPTY body while it is still computing. `.json()` on
    that raises, and the old code turned the exception straight into "proceeding" -- so the single
    commonest response was read as PERMISSION. Observed live on 2026-08-01 with the quota cache
    sitting at 4/4: every candidate would have been waved through into a certain 403, and a 403
    adjudicates, so each one would have been destroyed. Poll it like every other async endpoint,
    and when it genuinely cannot be read, fall back to the last account-level reading before
    considering failing open."""
    j = None
    for attempt in range(4):
        try:
            r = s.get(f"https://api.worldquantbrain.com/alphas/{aid}/check", timeout=60)
        except Exception:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 200 and r.text:
            try:
                j = r.json()
                break
            except Exception:
                pass
        time.sleep(5 * (attempt + 1))          # 200 + empty body = still computing, not a verdict
    if j is None:
        try:
            c = json.load(open(_QUOTA_CACHE))
            age = time.time() - c["ts"]
            if age < 1800 and c.get("result") == "FAIL":
                return False, (f"quota check still computing; last reading {int(age / 60)}min ago "
                               f"on {c.get('from')} was {c.get('value')}/{c.get('limit')} — "
                               f"{aid} withheld rather than gambled on a 403")
        except Exception:
            pass
        # Before failing OPEN, ask an INDEPENDENT authority. /check is one endpoint and it is
        # async, so "unreadable" says nothing about the quota -- yet proceeding here POSTs into a
        # quota that may be exhausted, and a 403 adjudicates and destroys the alpha. The
        # submissions activity feed is a different endpoint, is not per-alpha, and reports what the
        # account actually landed inside the platform's EASTERN day (see tools/daily_budget.py).
        try:
            import sys as _sys
            _sys.path.insert(0, str(ROOT / "tools"))
            from daily_budget import platform_date
            rr = s.get("https://api.worldquantbrain.com/users/self/activities/submissions",
                       timeout=45)
            if rr.status_code == 200:
                today = platform_date()
                n = next((v for d, v in rr.json()["records"]["records"] if d == today), 0)
                if n >= 4:
                    return False, (f"quota check unreadable, but the submissions feed shows "
                                   f"{n}/4 already landed today ({today} ET) — {aid} withheld")
                return True, f"quota check unreadable; submissions feed shows {n}/4 today, proceeding"
        except Exception:
            pass
        return True, "quota unreadable and no recent exhausted reading (proceeding)"
    found = None
    for sec in ("is", "os", "train", "test", "prod"):
        for ck in (j.get(sec) or {}).get("checks", []) if isinstance(j.get(sec), dict) else []:
            if ck.get("name") == "REGULAR_SUBMISSION":
                found = ck
    if found is not None:
        # REGULAR_SUBMISSION is an ACCOUNT-level counter that merely rides on a per-alpha payload,
        # so cache it: the next alpha whose payload omits the check can still be judged against it.
        try:
            json.dump({"result": found.get("result"), "value": found.get("value"),
                       "limit": found.get("limit"), "ts": time.time(), "from": aid},
                      open(_QUOTA_CACHE, "w"))
        except Exception:
            pass
        if found.get("result") == "FAIL":
            return False, (f"platform daily submission quota exhausted "
                           f"({found.get('value')}/{found.get('limit')}) — POST withheld, "
                           f"{aid} keeps its one-shot G6 slot for tomorrow")
        return True, "ok"
    # The check can be ABSENT -- the platform omits it on an already-submitted alpha, and a partial
    # payload can drop it too. Absence used to read as permission, which is how a submit could be
    # waved straight into an exhausted quota and a 403. An absent check is not evidence of room:
    # fall back to the most recent account-level reading taken from ANY alpha.
    try:
        c = json.load(open(_QUOTA_CACHE))
        age = time.time() - c["ts"]
        if age < 1800 and c.get("result") == "FAIL":
            return False, (f"quota read {int(age/60)}min ago on {c.get('from')} was "
                           f"{c.get('value')}/{c.get('limit')} — this alpha's own check is absent, "
                           f"so {aid} is withheld rather than gambled on a 403")
    except Exception:
        pass
    return True, "quota check absent and no recent exhausted reading (proceeding)"


def _dry_check(s, aid, budget_s=180):
    """Run the platform's OWN submission check set without spending the one-shot POST.

    `GET /alphas/{id}/check` returns exactly the `is.checks` array a submit would produce -- same
    names, same limits, same PASS/FAIL -- and costs nothing. Found 2026-08-05 while trying to decide
    whether `Xg8OZYQ1` at a displayed self-corr of "0.700" was inside a limit of 0.7. It was not
    0.700: the platform reported **0.6999** against limit 0.7, a margin of one ten-thousandth that
    `fetch_prod_corr`'s 4-decimal rounding had hidden. Guessing would have been a coin flip on an
    irreversible slot.

    This does NOT replace _fresh_corr_ok. That reads the correlation endpoints directly and fails
    closed when they cannot be read at all; this reads the adjudicated verdict. Run both: a FAIL
    here is a certain 403, which is the one outcome that destroys the alpha permanently.

    Fail OPEN on an unreadable response, deliberately. An empty body means "still computing", and
    every real gate is already enforced by the checks above; refusing to submit because a redundant
    confirmation was slow would cost a submit window for nothing."""
    t0 = time.time()
    while time.time() - t0 < budget_s:
        try:
            r = s.get(f"{API}/alphas/{aid}/check", timeout=60)
        except requests.RequestException:
            time.sleep(4)
            continue
        if r.status_code == 429:
            time.sleep(10)
            continue
        if r.status_code != 200 or not r.text.strip():
            time.sleep(6)
            continue
        try:
            checks = ((r.json().get("is") or {}).get("checks")) or []
        except Exception:
            return True, "dry check unreadable -- proceeding on the direct measurements"
        if not checks:
            time.sleep(6)
            continue
        fails = [c for c in checks if c.get("result") == "FAIL"]
        if fails:
            return False, ("would FAIL: " + ", ".join(
                f"{c.get('name')}={c.get('value')} (limit {c.get('limit')})" for c in fails))
        worst = max((c for c in checks if isinstance(c.get("value"), (int, float))
                     and isinstance(c.get("limit"), (int, float))
                     and "CORREL" in (c.get("name") or "")),
                    key=lambda c: c["value"], default=None)
        margin = (f", tightest {worst['name']}={worst['value']} vs {worst['limit']}"
                  if worst else "")
        return True, f"{len(checks)} checks, 0 FAIL{margin}"
    return True, "dry check timed out -- proceeding on the direct measurements"


def _fresh_corr_ok(s, aid):
    """Re-measure prod+self RIGHT NOW. A reserve alpha's stored corr goes stale the moment a
    near-twin of it is submitted: e7x0G7ag read self 0.414 when banked, then 0.99 once its twin
    j2r0G2aj went live; YPggJ8p6 read 0.507, then 0.981 once QP99gYLM went live. Submitting on a
    stale number burns an irreversible 1-per-alpha budget slot on a certain rejection. Fail-closed:
    if the measurement can't be taken, don't submit."""
    try:
        from fetch_prod_corr import prod_maxcorr, self_maxcorr, _fetch
    except ImportError:
        sys.path.insert(0, str(ROOT / "tools"))
        from fetch_prod_corr import prod_maxcorr, self_maxcorr, _fetch
    # Retry a TRANSPORT failure before giving up. Failing closed is right, but one dropped
    # connection is not evidence about the alpha: omgZNz2E was withheld on a single
    # RemoteDisconnected while its correlations were perfectly measurable seconds later. Three
    # attempts distinguish "the network blipped" from "this cannot be measured"; the fail-closed
    # verdict below is unchanged either way.
    pc = breach = self_j = sc = None
    last = None
    for attempt in range(3):
        try:
            pc, breach = prod_maxcorr(_fetch(s, aid, "prod"))
            self_j = _fetch(s, aid, "self")
            sc = self_maxcorr(self_j)
            last = None
            break
        except Exception as e:
            last = e
            time.sleep(3 * (attempt + 1))
    if last is not None:
        return False, f"corr re-measure failed after 3 tries: {str(last)[:60]}"
    # FAIL-CLOSED, for real this time. `records: []` is the platform's "still computing" reply, and
    # `[] is not None` is True — so the previous guard let a freshly-simmed alpha through with
    # self_maxcorr() == None, and the `sc >= 0.7` test below cannot fire on None. That is exactly
    # the e7x0G7ag / YPggJ8p6 twin failure this function exists to prevent, and it would burn the
    # irreversible one-shot G6 slot. Require actual records, and require the prod side to have been
    # read at all: a failed fetch is not a clean measurement.
    if not (self_j and self_j.get("records")):
        return False, "self-corr not measurable (no records — still computing or fetch failed)"
    # Records present is NOT the same as a NUMBER. self_maxcorr() also returns None when the
    # payload has no `correlation` column, or when every row's correlation is null -- and with sc
    # None the `sc >= 0.7` test below cannot fire, so the alpha passes with its self-correlation
    # UNKNOWN. That is the same hole, one layer down, that this function exists to close: a
    # duplicate of a freshly-live alpha gets POSTed, the platform 403s it, and a 403 adjudicates
    # and permanently spends the alpha. Require the number itself.
    if sc is None:
        return False, "self-corr present but unparseable (no correlation column or all null)"
    if pc is None or breach is None:
        return False, "prod-corr not measurable (fetch failed)"
    # SELF_CORRELATION 0.7 is the documented threshold and is what actually bites: e7x0G7ag
    # (self 0.99) and YPggJ8p6 (0.98) were duplicates of freshly-live alphas.
    if sc is not None and sc >= 0.7:
        return False, f"self={sc}"
    # PROD breach is NOT disqualifying on its own — SUBMISSION_GATES.md makes the correlation
    # limits conditional, and Xg8oQJRl went ACTIVE on TOP3000 with breach=2 (max 0.8) carried by
    # ladder 3.68 and turnover 0.12. Report it and let the platform arbitrate.
    return True, f"fresh: prod breach {breach} (max {pc}), self {sc}"


def _mark_cell_filled(aid):
    """Record locally that this alpha just filled its cells, and force a re-read next time.

    The platform's pyramid counter follows the alpha going ACTIVE, which takes minutes; the local
    ledger is authoritative for our OWN posts in that window and is exactly the gap the counter has
    not closed yet."""
    global _CELL_MEMO
    _CELL_MEMO = None
    cats, base = _LAST_GATE.get(aid, ([], {}))
    try:
        _record_submitted_cells(aid, cats, base)
    except Exception as e:
        print(f"  {aid}: cell ledger write failed ({str(e)[:60]}) — next submit will re-read live")


def submit_one(s, aid, force=False):
    # Re-verify the correlation gates against the CURRENT book before spending the budget slot.
    # `force` submits anyway and lets the PLATFORM arbitrate: SUBMISSION_GATES.md documents the
    # correlation limits as CONDITIONAL ("correlation > 0.7 -> additional conditions apply"; test
    # #5 only bites when the alpha also misses 1.0x ISLadder AND runs turnover > 30%), so a strong
    # ladder with low turnover can clear despite a nonzero prod breach. The local check is a
    # cost-saver, not the rule — but a forced attempt still spends the one-shot G6 slot.
    # Quota FIRST: it is the cheapest check and the only one whose failure is guaranteed to burn
    # the one-shot slot for nothing. `force` does not override it -- forcing into an exhausted
    # quota cannot succeed, it can only destroy the alpha.
    # Cell gate BEFORE quota: a quota failure means "try tomorrow", but submitting into an
    # already-unlocked cell is a permanent waste of both the slot and the alpha's signal family.
    # `force` does not override it -- forcing an alpha into a full cell cannot buy rank.
    cok, cwhy = _cell_gate(s, aid)
    print(f"  {aid}: {cwhy}")
    if not cok:
        # The gate refuses for two very different reasons and they must not share a status.
        # "cell-already-unlocked" is a PERMANENT verdict about the alpha; a 429 or an unreadable
        # count is a TRANSIENT failure to look. P0OLx0zp was logged "cell-already-unlocked" on a
        # pure rate-limit, and anything later reading that ledger would have written off a gem
        # whose cell was still at 1/3.
        perm = "already unlocked" in cwhy
        return {"ok": False, "status": "cell-already-unlocked" if perm else "cell-check-failed",
                "body": cwhy}
    qok, qwhy = _quota_ok(s, aid)
    if not qok:
        print(f"  {aid}: {qwhy}")
        return {"ok": False, "status": "quota-exhausted", "body": qwhy}
    ok, why = _fresh_corr_ok(s, aid)
    print(f"  {aid}: pre-submit corr check -> {why}")
    if not ok and not force:
        return {"ok": False, "status": "corr-stale-or-walled", "body": why}
    if not ok:
        print(f"  {aid}: --force -> submitting anyway; the platform decides")
    dok, dwhy = _dry_check(s, aid)
    print(f"  {aid}: dry check -> {dwhy}")
    if not dok and not force:
        return {"ok": False, "status": "dry-check-failed", "body": dwhy}
    # G6: reserve the 1-per-alpha budget ATOMICALLY before POSTing, on the SAME ledger complete_/gentle_submit
    # use, so this path can't double-submit an alpha those tools already posted (and vice-versa). The true
    # dataset family (B10 O7) also engages the per-family/day submit-test cap.
    ok, why = reserve_submit(aid, _family_of(aid))
    if not ok:
        return {"ok": False, "status": "G6-blocked", "body": why}
    # WQB submit is async: POST starts it, may return 201 + Location/Retry-After to poll.
    r = s.post(f"https://api.worldquantbrain.com/alphas/{aid}/submit", timeout=40)
    # Poll on a WALL-CLOCK budget: the platform re-runs every check on submit and takes ~170-215s,
    # while 40 iterations expired in well under that. Both 3qeeOxlQ and zqRN8LGE reported
    # "REJECTED [timeout]" here — 3qeeOxlQ had genuinely failed PROD_CORRELATION, but zqRN8LGE had
    # SUCCEEDED and was already ACTIVE. A too-short poll turns a success into a false rejection.
    deadline = time.time() + 600
    while time.time() < deadline:
        if r.status_code in (200, 201) and r.text:
            # The cell bookkeeping used to live only in the fall-through branch below, which a
            # SUCCESSFUL submit never reaches — it returns here. So _CELL_MEMO was never
            # invalidated and submitted_cells_today.jsonl was never written, and the platform's
            # pyramid counter LAGS a submission by minutes. Two alphas aimed at the same cell
            # therefore both read it as still short and both POSTed. News sits at 2/3 right now,
            # so the second POST would spend an irreversible slot on an already-filled cell.
            _mark_cell_filled(aid)
            return {"ok": True, "status": r.status_code, "body": r.text[:400]}
        if r.headers.get("Retry-After") or (r.status_code in (200, 201) and not r.text):
            time.sleep(min(float(r.headers.get("Retry-After", 3)), 5))
            r = s.get(f"https://api.worldquantbrain.com/alphas/{aid}/submit", timeout=40)
            continue
        # A 4xx does NOT uniformly mean "no submission was created". Under G6 an alpha gets one
        # POST ever, and a 403 is the platform ADJUDICATING that POST and rejecting it -- the
        # attempt is spent. Releasing the slot on a 403 made six permanently-dead alphas
        # (pwKZl6Zg, O0xVZpVd, Vk35PY2J, vRvNrZXw, gJ98Vqjl, N1R7AKN8) read as submittable again:
        # all six are in state/funnel/submit_log.jsonl with a 403 and none in submit_budget.jsonl.
        # Only a 429 (throttled, never adjudicated) and a 408 (never answered) may hand the slot back.
        body = r.text or ""
        if r.status_code in (408, 429):
            release_submit(aid)
        elif r.status_code == 403 and _only_errors(body):
            # A 403 whose checks contain NO 'FAIL' -- only 'ERROR' -- is the platform failing to
            # COMPUTE, not judging the alpha. P0OLx0zp was 403'd on 2026-08-01 with a lone
            # PROD_CORRELATION:ERROR while the account was rate-limited; measured minutes later it
            # read prod 0.6549, breach 0, self 0.6549, i.e. comfortably submittable. Treating that
            # as an adjudication would have destroyed a gem over a transient platform hiccup, which
            # is the same mistake as counting a dropped connection against the alpha.
            release_submit(aid)
            print(f"  {aid}: 403 carried only ERROR (no FAIL) -- transient, G6 slot returned")
        # Do NOT truncate a rejection body. 400 chars cut off before the failing check in every
        # 403 this project logged; raising it to 2000 still cut P0OLx0zp's mid-array, so the
        # ledger row stayed unparseable and _only_errors could not tell "uncomputable" from
        # "judged". A few KB per submit is free; re-diagnosing a dead alpha against the live API
        # is not.
        keep = body if r.status_code not in (200, 201) else body[:400]
        if r.status_code in (200, 201):
            _mark_cell_filled(aid)
        return {"ok": r.status_code in (200, 201), "status": r.status_code, "body": keep}
    # The poll ran out. That is NOT a rejection and must never be reported as one: `GET
    # /alphas/{id}/submit` answers **404 when no job exists** (never POSTed, or already resolved)
    # and **200 + Retry-After with an empty body while a job is IN FLIGHT**, so the state is
    # readable and there is no reason to guess. Measured 2026-08-05: JjGwqKlW (never POSTed) 404,
    # E5ejp6JL (submitted) 404, Xg8OZYQ1 (POSTed) 200/Retry-After for 45+ minutes against a normal
    # 170-215s.
    # This matters because `/alphas/{id}/check` CANNOT tell the difference -- it returns the full
    # gate set both for an alpha with no submission and for one whose submission is still queued.
    # Reading it as "the POST never registered" is what caused a second POST to be fired while the
    # first was still in flight.
    try:
        st = s.get(f"https://api.worldquantbrain.com/alphas/{aid}/submit", timeout=30)
        if st.status_code == 200:
            return {"ok": False, "status": "in-flight",
                    "body": "poll budget exhausted but the submission is STILL QUEUED "
                            "(GET .../submit answers 200) — do NOT retry, do NOT release the slot"}
    except Exception:
        pass
    return {"ok": False, "status": "timeout", "body": "no job found on the submit endpoint"}

if __name__ == "__main__":
    args = sys.argv[1:]
    force = "--force" in args                 # let the platform arbitrate a conditional-corr case
    args = [a for a in args if a != "--force"]
    s = session(); f = open(LOG, "a")
    for aid in args:
        res = submit_one(s, aid, force=force)
        rec = {"alpha": aid, **res}
        f.write(json.dumps(rec) + "\n"); f.flush()
        print(f"{aid}: {'SUBMITTED ✓' if res['ok'] else 'REJECTED'} [{res['status']}] {res['body'][:160]}", flush=True)
        time.sleep(3)
    f.close()
