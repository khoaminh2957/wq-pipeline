#!/usr/bin/env python3
"""How many simulations are left today, and when the allowance resets.

Discovered 2026-08-02 the expensive way: the pipeline ran 4h45m creating nothing while the driver
retried and a poller checked every 120s, because both read a 429 as transient.

    POST /simulations -> 429 {"detail":"CONCURRENT_SIMULATION_LIMIT_EXCEEDED"}   # clears in minutes
    POST /simulations -> 429 {"detail":"DAILY_SIMULATION_LIMIT_EXCEEDED"}        # clears at midnight ET

**And the body does NOT tell you which one you are in.** Probing the identical request every 20
seconds with the daily allowance exhausted returned DAILY, then CONCURRENT, then CONCURRENT, then
CONCURRENT. The platform reports whichever limit check happened to fire; the message is not a
diagnosis. An earlier version of this file claimed "reading the body is the whole fix" -- that was
wrong, and acting on a single CONCURRENT reply would have resumed the same hammering.

The only trustworthy signal is COUNTING what the account actually created inside the Eastern day,
which is what budget() does. It needs no cooperation from the error path.

The daily window runs on US EASTERN, not UTC and not local: the platform's own counter read 5048
for "2026-08-01" while UTC was already 2026-08-02T02:30, and `dateCreated> 2026-08-01T04:00:00Z`
returned exactly 5048 alphas -- an exact match, so the boundary is 04:00Z = 00:00 EDT. The offset
is read back from a platform timestamp rather than hardcoded, so this keeps working through the
EST/EDT switch.

Observed ceiling: 5060 (07-30) and 5048 (08-01) on days that hit it, so the cap is ~5000 and
overshoots by up to one multisim batch. CAP is a planning estimate; the authoritative signal is
still the 429.

  python3 tools/daily_budget.py            # used / remaining / reset
  python3 tools/daily_budget.py --json
"""
import argparse, datetime, json, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import submit_alphas as SA                                            # noqa: E402

API = "https://api.worldquantbrain.com/users/self/alphas"
CAP = 5000


def platform_date():
    """Today's date in the PLATFORM's day, which is US Eastern -- not UTC and not local.

    Every local ledger that means "per platform day" must key on this. Keying on the UTC date
    opens a four-hour hole daily (00:00-04:00 UTC = 07:00-11:00 local) where the local counter has
    reset but the platform's has not: measured 2026-08-02 at 03:20 UTC, driver.budget_used()
    returned 0 while the platform reported 4/4 used. Submitting into that hole returns 403, and a
    403 permanently spends the alpha -- the exact way le391QLA and Vk35LRM0 were destroyed.

    zoneinfo rather than a hardcoded -4: the offset changes at the EST/EDT switch."""
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def et_offset(s):
    """Hours the platform's day is behind UTC, from its own newest timestamp (-4 EDT / -5 EST)."""
    r = s.get(API, params={"limit": 1, "order": "-dateCreated"}, timeout=60)
    if r.status_code == 200:
        for a in (r.json() or {}).get("results") or []:
            d = a.get("dateCreated") or ""
            if len(d) > 6 and d[-6] in "+-":
                return int(d[-6:-3])
    return -4


LIMIT_MARK = ROOT / "state/daily_limit_hit.json"


def mark_daily_limit(window_start_utc):
    """Record that the platform refused a simulation for the DAILY limit in this ET window.

    Call this from any path that sees `DAILY_SIMULATION_LIMIT_EXCEEDED`. One 429 body is not a
    reliable diagnosis on its own -- probing 20s apart returned DAILY/CONCURRENT/CONCURRENT --
    but a DAILY reply is never produced when the day is open, so it is safe in the direction that
    matters: it can only stop work early, never let it run past the ceiling."""
    try:
        # isoformat on BOTH sides. str(datetime) renders a space where isoformat renders 'T', so a
        # marker written from one and compared against the other never matches and the guard is
        # silently inert -- which is exactly how it failed its first test.
        w = window_start_utc.isoformat() if hasattr(window_start_utc, "isoformat") else str(window_start_utc)
        json.dump({"window_start_utc": w}, open(LIMIT_MARK, "w"))
    except Exception:
        pass


def _limit_hit_today(window_start_utc):
    try:
        w = window_start_utc.isoformat() if hasattr(window_start_utc, "isoformat") else str(window_start_utc)
        return json.load(open(LIMIT_MARK)).get("window_start_utc") == w
    except Exception:
        return False


def budget(s=None):
    s = s or SA.session()
    off = et_offset(s)
    now = datetime.datetime.now(datetime.timezone.utc)
    et = now + datetime.timedelta(hours=off)
    start_et = et.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_et - datetime.timedelta(hours=off)
    reset_utc = start_utc + datetime.timedelta(days=1)
    r = s.get(API, params={"limit": 1, "offset": 0,
                           "dateCreated>": start_utc.strftime("%Y-%m-%dT%H:%M:%S-00:00")},
              timeout=60)
    used = (r.json() or {}).get("count") if r.status_code == 200 else None

    # OUR OWN CEILING IS REMOVED, on Khoa's instruction 2026-08-11, and the evidence supports it:
    # CAP was never the platform's number. It was inferred from two observed days ("5060 on 07-30
    # and 5048 on 08-01, so the cap is ~5000") and it has since been measured WRONG IN BOTH
    # DIRECTIONS -- it reported 1034 remaining on 2026-08-06 while every POST was already being
    # refused, and it stopped the loop at 4999 on 2026-08-11 when only the platform can say when the
    # day is over. A guess that halts a pipeline is worse than no guess.
    #
    # `used` is still reported, because knowing how many alphas the day produced is useful. It just
    # no longer GATES anything. The only thing that closes the day now is the platform saying so,
    # which is the branch below and which no count may override.
    remaining = None

    # THE COUNT IS NOT THE QUOTA. It counts ALPHAS CREATED; the platform's ceiling counts
    # SIMULATIONS ATTEMPTED, and an attempt that errors, retries or produces no alpha still spends
    # one. Measured 2026-08-06: this function reported "3966/5000, 1034 remaining" while
    # `POST /simulations` answered 429 `DAILY_SIMULATION_LIMIT_EXCEEDED` -- roughly 300 attempts
    # that day never became alphas. The driver's own budget guard reads `remaining`, so it saw
    # headroom that did not exist and three consecutive rounds POSTed into the wall for 2h19m.
    #
    # When the platform says the day is over, that is authoritative and nothing derived from a
    # count may override it. `mark_daily_limit()` records the ET date; until it rolls over,
    # remaining is 0 whatever the alpha count says. The reverse is NOT symmetric -- a count below
    # the cap is only ever an upper bound on what is left.
    if _limit_hit_today(start_utc):
        remaining = 0
    return {"used": used, "cap": CAP, "remaining": remaining,
            "et_offset": off,
            "window_start_utc": start_utc.isoformat(),
            "reset_utc": reset_utc.isoformat(),
            "seconds_to_reset": int((reset_utc - now).total_seconds())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    b = budget()
    if args.json:
        print(json.dumps(b))
        return
    h, m = divmod(b["seconds_to_reset"] // 60, 60)
    loc = (datetime.datetime.fromisoformat(b["reset_utc"])
           .astimezone()).strftime("%H:%M %Z")
    print(f"used {b['used']}/{b['cap']}  remaining {b['remaining']}")
    print(f"resets in {h}h{m:02d}m  ({loc} local, midnight ET)")


if __name__ == "__main__":
    main()
