"""Submit the ROOT gem of a lineage, at most one a day. The only module here that POSTs.

AUTHORITY. Khoa authorised full automation with a cap (2026-08-14) after being told, in the same
turn, that I had twice today called something a gem that was not one. That authorisation is why the
POST path exists at all; every constraint below is what makes it defensible.

THE ROOT RULE, Khoa's words: "6 gem đó thật sự chỉ là từ 1 gem mà ra nên chỉ cần nộp gem gốc là
được". A hill climb grows ONE baseline, so its gems are a lineage, not a population. The six that
first reached tier 4 shared the same six core fields at Jaccard 0.75-0.86 and differed only in the
OUTERMOST operator -- sqrt, log, winsorize, group_zscore, group_neutralize. Submitting more than one
of them spends the day's quota on a single mechanic, which this project has already measured:
"464 rows of one mechanic = 26 gems but 1 submission."

So the submitter groups gems by structural lineage -- ancestry compared with parameters NORMALISED
AWAY, because a tune round changes the numbers inside and literal text comparison then finds zero
ancestors where there are 210 -- and offers the SHALLOWEST tier-4 member of each lineage.

WHAT MAKES A POST ALLOWED HERE, all of it required:
  * tier 4: screened, every scored gate PASS, and prod/self correlation MEASURED under their lines
  * the shallowest tier-4 member of its lineage
  * its lineage has never been submitted before
  * the daily cap has room

A 403 IS FINAL. The platform adjudicates once per alpha and the slot is gone forever; only 408 and
429 are retryable. So the full response body is recorded, not the first 400 characters -- every 403
body ever stored in this repository was truncated at 400 and the platform's actual refusal reason is
nowhere on disk.
"""

import argparse
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import climb as C  # noqa: E402
import layered_alpha as LA  # noqa: E402
import layered_sim as LS  # noqa: E402

LOG = ROOT / "state/climb/submitted.jsonl"

#: One a day. Khoa authorised "tự nộp hoàn toàn, có trần"; this is the trần.
DAILY_CAP = 1


def normalise(formula):
    """A formula with its tuned parameters removed, so ancestry survives a tune round.

    Literal comparison finds ZERO ancestors of a deep gem; normalised comparison finds 210. The
    difference is entirely the tune rounds rewriting windows, exponents and group names in place.
    """
    if not formula:
        return ""
    f = re.sub(r"(?<=[,(])\s*\d+(\.\d+)?\s*(?=[,)])", "#", formula)
    for g in LA.GROUPS:
        f = f.replace(g, "@")
    return re.sub(r"\s+", "", f)


def lineages(gems):
    """Group gems into lineages and return the SHALLOWEST member of each.

    Two alphas share a lineage when one's normalised formula is contained in the other's -- that is
    what "grew from" means for a climb. Shallowest is by normalised length: the root gem is the
    least-wrapped alpha that is itself a gem.
    """
    rows = sorted(gems, key=lambda r: len(normalise(r.get("formula"))))
    roots, claimed = [], []
    for r in rows:
        n = normalise(r.get("formula"))
        if any(root in n for root in claimed):
            continue                      # a descendant of a root already taken
        claimed.append(n)
        roots.append(r)
    return roots


def submitted_ids(path=LOG):
    """Return (ids, readable).

    `readable` is the whole point. An EMPTY id set is NOT evidence that nothing was submitted: this
    ledger is written only on the machine that POSTs, and this project's one real submission is
    ACTIVE on the platform while no file on either machine records it. Collapsing "I checked and
    found none" into "none" is how a burned alpha gets announced as still available, so the caller
    is handed both facts instead of a bare list that reads as authoritative.
    """
    p = pathlib.Path(path)
    if not p.exists():
        return set(), False
    try:
        text = p.read_text(errors="ignore")
    except OSError:
        return set(), False
    ids = set()
    for line in text.splitlines():
        if not line.startswith("{"):
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("alpha"):
            ids.add(r["alpha"])
    return ids, True


def already_submitted(path=LOG):
    """Normalised formulas whose lineage has been POSTed. A lineage is spent once any member is."""
    out = []
    p = pathlib.Path(path)
    if not p.exists():
        return out
    for line in p.read_text(errors="ignore").splitlines():
        if line.startswith("{"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("normalised"):
                out.append(r["normalised"])
    return out


def submitted_today(path=LOG):
    p = pathlib.Path(path)
    if not p.exists():
        return 0
    # The platform's day resets 00:00 ET, which is 11:00 local. Counting on that boundary rather
    # than on local midnight is what keeps the cap aligned with the quota it exists to respect.
    now = time.time()
    day_start = now - ((now - 4 * 3600) % 86400)
    n = 0
    for line in p.read_text(errors="ignore").splitlines():
        if line.startswith("{"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            # A RAISED POST STILL SPENDS THE DAY.
            #
            # This required `http is not None`, so a POST that raised -- recorded as
            # `"http": null` -- was counted as if it had never happened, and the loop went on to
            # POST a SECOND lineage the same day while the first may already have landed. That is
            # the one direction with an irreversible cost: an unspent submit costs a day, an
            # overspent one costs the alpha. `record()` is written for exactly this reason
            # ("whatever happened, the lineage is spent"); the counter disagreed with it.
            if r.get("posted_at", 0) >= day_start:
                n += 1
    return n


#: Below this self-corr a gem is a SUPER GEM. It no longer restricts the unattended path -- Khoa
#: widened auto-submit on 2026-08-29 ("neu alpha nop duoc thi hay cu nop") -- but the label still
#: orders the queue: when several roots are eligible the least self-correlated goes first.
SUPER_GEM_SELF_CORR = 0.30


def pyramid_ok(row):
    """Does the platform's own MATCHES_PYRAMID check PASS on this row?

    This is the "phu hop voi pyramid hien tai" half of Khoa's 2026-08-29 auto-submit order, taken
    from the platform's grading rather than re-derived here. Measured before adoption (RULE 2):
    PASS on 99.0% of 38,055 journal rows and on 254 of 254 current tier-4s, adverse on zero -- so
    requiring PASS starves nothing, unlike the three zero-variance-adverse MATCHES_* gates.
    Fails closed on unscored (1% of rows): unknown is not a match.
    """
    for ch in (row.get("checks") or []):
        if isinstance(ch, dict) and ch.get("name") == "MATCHES_PYRAMID":
            return ch.get("result") == "PASS"
    return False


def candidates(objective="fitness"):
    """(root gems eligible to POST, all tier-4 gems) -- ranked by LOWEST prod correlation.

    Ranked on prod-corr and not on fitness because prod-corr is what the submission is judged
    against; among a lineage's members fitness varies by ~0.3 while prod-corr varies by 0.16, and
    0.71 is the line that actually refuses.
    """
    measured = C.measured_corr()
    rows = {}
    for r in C._journal_rows():
        if r.get("alpha") and r.get("formula"):
            rows[r["alpha"]] = r
    gems = [r for r in rows.values() if C.tier(r, measured) == 4]
    spent = already_submitted()
    out = []
    for r in lineages(gems):
        n = normalise(r["formula"])
        if any(s in n or n in s for s in spent):
            continue
        r = dict(r)
        r["prod_corr"] = (measured.get(r["alpha"]) or {}).get("prod")
        r["self_corr"] = (measured.get(r["alpha"]) or {}).get("self")
        out.append(r)
    out.sort(key=lambda r: (r.get("prod_corr") if r.get("prod_corr") is not None else 9e9))
    return out, gems


def post(alpha_id, session=None):
    """The single irreversible call. Returns (status, full_body); status is None if it RAISED.

    A RAISE IS NOT A NON-EVENT. The request may have reached the platform and been adjudicated
    before the timeout fired, so an exception says "outcome unknown", never "did not happen". The
    caller must record it and retire the lineage exactly as for a refusal -- the alternative, which
    this module did until it was audited, is that the loop re-POSTs the same alpha next round, and
    that is the only path in the whole pipeline that can spend TWO irreversible slots on one alpha.
    """
    s = session or LS.session()
    try:
        r = s.post("%s/alphas/%s/submit" % (LS.API, alpha_id), timeout=60)
    except Exception as exc:                       # noqa: BLE001 - the outcome is what matters
        return None, "EXCEPTION %s: %s -- OUTCOME UNKNOWN, the POST may have been adjudicated" % (
            type(exc).__name__, exc)
    return r.status_code, (r.text or "")


def record(row, http, body, path=LOG):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps({
            "alpha": row.get("alpha"), "formula": row.get("formula"),
            "normalised": normalise(row.get("formula")),
            "fitness": row.get("fitness"), "sharpe": row.get("sharpe"),
            "turnover": row.get("turnover"),
            "prod_corr": row.get("prod_corr"), "self_corr": row.get("self_corr"),
            "http": http,
            "root_override": row.get("root_override"),
            # THE WHOLE BODY. Every 403 ever stored here was truncated at 400 characters, so the
            # platform's actual refusal reason is nowhere on disk.
            "body": body,
            "posted_at": time.time(),
        }) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)  # draw-3 MINOR 9: `--sub` is not `--submit`
    ap.add_argument("--list", action="store_true", help="show what would be submitted and exit")
    ap.add_argument("--submit", action="store_true",
                    help="ACTUALLY POST. Irreversible: a 403 spends the alpha forever.")
    ap.add_argument("--alpha", help="submit this id specifically, still subject to every gate")
    ap.add_argument("--cap", type=int, default=DAILY_CAP)
    ap.add_argument("--override-root", metavar="REASON",
                    help="submit a named alpha that is NOT its lineage root. The ROOT RULE is a "
                         "heuristic I built; the account is Khoa's and so is the call. Every OTHER "
                         "gate still applies -- tier 4, measured correlations under both lines, "
                         "lineage unspent, cap. The reason is written to the log so a waived rule "
                         "is never a silent one.")
    a = ap.parse_args()

    eligible, gems = candidates()
    done = submitted_today()
    print("%d tier-4 gem(s) -> %d lineage root(s) never submitted; %d posted today, cap %d"
          % (len(gems), len(eligible), done, a.cap))
    for r in eligible[:8]:
        print("  %-10s prod %-8s self %-8s fit %-6s sh %-6s tvr %-7s depth %d"
              % (r["alpha"], r.get("prod_corr"), r.get("self_corr"), r.get("fitness"),
                 r.get("sharpe"), r.get("turnover"), len(normalise(r["formula"]))))
        print("      %s" % (r["formula"] or "")[:150])

    # `--submit` IS THE ONLY PATH THAT POSTS, and now that is true.
    #
    # It used to read `not (a.submit or a.alpha)`, so `--alpha <id>` alone fell straight through to
    # the POST -- while printing the sentence below claiming it could not. A flag that contradicts
    # its own help text on an irreversible path is worse than no flag.
    if a.list or not a.submit:
        print("\nnothing posted. --submit is the only path that POSTs."
              + ("  (--alpha selects WHICH alpha; it does not authorise a POST.)" if a.alpha else ""))
        return 0

    # ONE BUDGET, SHARED, FAIL-CLOSED.
    #
    # This counted `submitted_today()` from a PRIVATE ledger against a private cap. The platform's
    # real allowance is 4 per Eastern day and `state/submit_budget.jsonl` is the ledger that tracks
    # it -- but that module was never deployed here, so on this box the shared budget answered
    # "fine" to everything while the climb counted only itself. Two counters, one allowance: the
    # arithmetic that put five POSTs against a cap of four, and the fifth is a 403, which
    # ADJUDICATES and spends the alpha's one lifetime attempt.
    #
    # remaining_today() takes the MAX of the ledger and the platform feed -- each source can only
    # MISS a submission, never invent one, so the largest reading is the only one that cannot
    # overspend -- and returns 0 when nothing is readable. An unspent submit costs a day; an
    # overspent one costs the alpha forever.
    try:
        import submit_budget as SB
        budget = SB.remaining_today(session=LS.session())
    except Exception as exc:                       # noqa: BLE001 - unreadable budget = no POST
        print("REFUSING TO POST: the shared submit budget could not be read (%s: %s). "
              "Failing closed." % (type(exc).__name__, exc))
        return 1
    print("shared budget: %s" % budget["why"])
    if not budget.get("authoritative"):
        print("  NOTE: the platform feed did not answer, so this is a LEDGER-ONLY upper bound -- "
              "it cannot see a submission made outside this pipeline.")
    if budget["remaining"] <= 0:
        print("cap reached for today (%s/%s); nothing posted" % (budget["used"], budget["cap"]))
        return 0
    if done >= a.cap:
        print("loop's own cap reached (%d/%d); nothing posted" % (done, a.cap))
        return 0
    pick = None
    if a.alpha:
        pick = next((r for r in eligible if r["alpha"] == a.alpha), None)
        if not pick and a.override_root:
            # Operator override of the ROOT RULE ONLY. The alpha must still be tier 4 with measured
            # correlations under both lines and belong to an unspent lineage.
            measured = C.measured_corr()
            rows = {r["alpha"]: r for r in C._journal_rows() if r.get("alpha")}
            cand = rows.get(a.alpha)
            if not cand:
                print("REFUSED: %s is not in any journal" % a.alpha)
                return 1
            if C.tier(cand, measured) != 4:
                print("REFUSED: %s is tier %d, not 4. The root rule is overridable; the gates are "
                      "not." % (a.alpha, C.tier(cand, measured)))
                return 1
            n = normalise(cand["formula"])
            if any(s in n or n in s for s in already_submitted()):
                print("REFUSED: %s belongs to a lineage that has already been submitted." % a.alpha)
                return 1
            pick = dict(cand)
            pick["prod_corr"] = (measured.get(a.alpha) or {}).get("prod")
            pick["self_corr"] = (measured.get(a.alpha) or {}).get("self")
            pick["root_override"] = a.override_root
            print("ROOT RULE OVERRIDDEN: %s" % a.override_root)
        if not pick:
            print("REFUSED: %s is not a lineage root eligible to submit. Every gate applies to a "
                  "named alpha too -- naming one does not waive them. Use --override-root REASON "
                  "to waive the ROOT RULE only." % a.alpha)
            return 1
    else:
        # THE UNATTENDED PATH. Khoa, 2026-08-29: "neu alpha nop duoc thi hay cu nop" -- any alpha
        # that passes EVERY gate (tier 4: screened, every scored gate PASS, both correlations
        # measured under their lines) and matches the current pyramid is posted without waiting
        # for a human. This supersedes the 2026-08-18 super-gem-only restriction by his explicit
        # order. What still stands, because a 403 is final and one POST exists per alpha, ever:
        # the root rule, one POST per lineage, the daily cap, record-first ordering, the flock.
        #
        # ORDER: least self-correlated first (super gems lead), then lowest prod-corr -- the
        # eligible list already arrives prod-corr-sorted, and this sort is stable.
        auto = [r for r in eligible if pyramid_ok(r)]
        held = len(eligible) - len(auto)
        if held:
            print("%d eligible root(s) held back: MATCHES_PYRAMID not PASS (unscored counts as "
                  "not a match)." % held)
        auto.sort(key=lambda r: (r.get("self_corr") if isinstance(r.get("self_corr"),
                                                                  (int, float)) else 9e9))
        pick = auto[0] if auto else None
    if not pick:
        print("no eligible root gem; nothing posted")
        return 0

    # A LOCK, BECAUSE THE CHECK AND THE POST MUST BE ONE STEP.
    #
    # There was none. Two invocations could both read "0 posted today" and both POST the same
    # alpha; the second one is a 403 and the alpha is gone. The window is the whole POST, up to 60
    # seconds wide.
    import fcntl
    lockf = open("/var/lock/wq_submit.lock", "a+")
    try:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another submitter holds /var/lock/wq_submit.lock; refusing to POST")
        return 0

    print("\nPOSTING %s (prod %s, self %s) -- irreversible"
          % (pick["alpha"], pick.get("prod_corr"), pick.get("self_corr")))

    # RECORD FIRST, ALWAYS -- and now the code does what the comment always said.
    #
    # `record()` ran AFTER `post()`. A kill inside the POST window left NO row, so
    # `submitted_today()` read 0 and `already_submitted()` read empty, and the submitter re-armed
    # on an alpha that may already have been adjudicated. The reservation is written to the SHARED
    # ledger before a single byte leaves, so a crash counts as spent. Over-counting costs a day;
    # under-counting costs the alpha.
    try:
        SB.LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with SB.LEDGER.open("a") as fh:
            fh.write(json.dumps({"date": SB.platform_date(), "alpha": pick["alpha"],
                                 "source": "climb_submit", "stage": "reserved",
                                 "reserved_at": time.time()}) + "\n")
    except OSError as exc:
        print("REFUSING TO POST: could not reserve a slot in the shared ledger (%s). "
              "Failing closed." % exc)
        return 1

    http, body = post(pick["alpha"])
    # The detailed outcome goes to the loop's own log; the shared ledger already holds the slot.
    record(pick, http, body)
    print("HTTP %s\n%s" % (http, body[:2000]))
    # ANNOUNCE EVERY UNATTENDED POST. Under Khoa's 2026-08-29 auto-submit order the loop spends
    # an irreversible slot with nobody watching, so silence here is not acceptable: m6 existed in
    # the catalogue since the notifier rebuild and NOTHING called it. Failure to notify must not
    # un-post or re-post anything -- the ledger rows above are already written -- so this block
    # reports loudly and never raises.
    try:
        import msgcat as MC
        MC.send(MC.m6_post_outcome(pick["alpha"], http, time.time(),
                                   exc_class=(None if http is not None else "post-raised")))
    except Exception as exc:                            # noqa: BLE001
        print("NOTIFY FAILED (%s: %s) -- the POST above still happened; see the ledger."
              % (type(exc).__name__, exc))
    if http is None:
        # The old text sent the operator to /alphas/{id}/submit and told them 404 meant no job was
        # created. That is FALSE and this repo measured it false twice: E5ejp6JL answered 404 while
        # submitted (2026-08-05), and mL516W9W answered 404 on 2026-08-16 while ACTIVE. A 404 is the
        # union of "never POSTed" and "POSTed, landed, finished" -- so the advice pointed straight
        # at a re-POST, i.e. the 403 that spends the alpha's slot forever. Printed, of all moments,
        # right after a POST whose outcome is unknown.
        print("OUTCOME UNKNOWN: the POST raised. The POST MAY HAVE LANDED. DO NOT POST AGAIN.\n"
              "The lineage is retired anyway, because the platform may have adjudicated it.\n"
              "Read the state with EXACTLY one command:  GET /alphas/%s\n"
              "  · status != UNSUBMITTED, or dateSubmitted != null -> a submission EXISTS. STOP.\n"
              "  · status = UNSUBMITTED and dateSubmitted = null   -> no submission is recorded.\n"
              "Only Khoa may decide to POST again, and only on the second branch."
              % pick["alpha"])
        return 1
    return 0 if http in (200, 201) else 1


if __name__ == "__main__":
    raise SystemExit(main())
