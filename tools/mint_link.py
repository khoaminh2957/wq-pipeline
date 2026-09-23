#!/usr/bin/env python3
"""Mint a persona link and queue it for Discord -- RESPECTING the biometric wall.

WHY THIS EXISTS. The daemon has always kept a persistent backoff at state/auth_mint_wall.json and
honoured it. Ad-hoc mint snippets pasted into an ssh session did not, and every attempt made while
the wall is up RE-ARMS IT FOR ANOTHER 30 MINUTES. Measured 2026-08-17: the wall stood until
06:44:30; a manual attempt at 06:44 pushed it to 07:14:30, and a second at 06:46 would have pushed
it further. Retrying does not shorten the wait, it lengthens it, and it does so silently.

So minting goes through one function that reads the wall first. `--force` exists for an operator
who has a reason, and it says out loud what it is about to cost.

Read-only against the platform except for the single POST /authentication that IS the mint.
"""
import json
import pathlib
import sys
import time
from urllib.parse import urljoin

import requests

ROOT = pathlib.Path("/opt/wq")
sys.path.insert(0, str(ROOT / "tools"))

WALL = ROOT / "state/auth_mint_wall.json"
BUDGET = ROOT / "state/auth_mint_budget.json"
LINK = ROOT / "state/auth_link.txt"
CREDS = pathlib.Path("/root/.wqbrain_creds")
#: The wall GROWS when a refusal follows a refusal. A flat 30 minutes was a trap.
#:
#: Measured 2026-08-17/18: the timer ran 1,301 times in 25 hours, 1,212 of those refused against a
#: standing wall and 18 got a fresh 429 -- and each 429 re-armed the same flat 30 minutes. Because
#: our 30-minute guess is SHORTER than the platform's real throttle, every expiry produced another
#: attempt that reset the platform's own timer. The loop could never escape: 25 hours, 8 links, and
#: 263 auth deaths behind them.
#:
#: So a 429 that arrives soon after the previous wall expired doubles the wait instead of repeating
#: it. Backing off is the only move that can find a duration we do not know.
WALL_MIN_S = 1800.0
WALL_MAX_S = 4 * 3600.0
WALL_S = WALL_MIN_S        # kept for callers; the live value is computed by next_wall()


def next_wall(prev):
    """How long to wait after this refusal, given the record of the last one."""
    if not prev:
        return WALL_MIN_S
    was = float(prev.get("duration") or WALL_MIN_S)
    since = time.time() - float(prev.get("until") or 0)
    # A refusal within 10 minutes of the last wall lifting means the wait was too short.
    if 0 <= since <= 600:
        return min(was * 2, WALL_MAX_S)
    return WALL_MIN_S

#: Mint this long BEFORE the session expires, not after it dies.
#:
#: The cookie lives exactly 4 hours and CANNOT be refreshed -- measured 2026-08-18: two
#: authenticated GETs both returned 200 with no Set-Cookie and the JWT's exp did not move. So a
#: human tap every 4 hours is a hard requirement, and the only thing engineering can change is
#: whether the gap around it is zero or hours.
#:
#: Before this, the loop died first and the link was minted afterwards, so every renewal cost at
#: least the time it took someone to notice. Measured over the last 24 h: 263 auth deaths, 7 rounds
#: run, 900 simulations against a 5,000/day quota -- 18% of capacity, because the session was alive
#: for perhaps two hours of twenty-four.
#:
#: A link lives ~10 minutes, so 8 minutes of margin puts a fresh link in front of the operator while
#: the old session is still working. If he taps, the changeover costs nothing at all.
RENEW_MARGIN_S = 8 * 60

#: Khoa, 2026-08-18: "h mặc định là 1 tiếng gửi 1 lần, 1 link còn dư thì để dành".
#:
#: One link an hour, and never spend a mint while a live one is still on the table. Two guards do
#: that, and they matter because the budget is already being overspent: measured today, `used: 33`
#: against DAILY_MINT_CAP = 25 -- 32% over. That overspend is the likeliest thing feeding the
#: BIOMETRICS_THROTTLED wall we then spent all night waiting out.
#:
#: An hourly cadence is 24 a day, which fits inside 25 only if nothing is wasted. So:
#:   * a link younger than LINK_HOLD_S is reused, not replaced -- "để dành"
#:   * the budget is checked before minting, and refusing costs nothing
#: An URGENT mint (session dead or inside RENEW_MARGIN_S) ignores the hourly cadence, because the
#: cadence exists to keep a link handy, not to delay the one renewal that actually matters.
MINT_INTERVAL_S = 3600.0
LINK_HOLD_S = 9 * 60          # a link lives ~603 s; below this it is still worth tapping
LAST_MINT = ROOT / "state/auth_last_mint.json"


def live_link():
    """A link minted recently enough to still be tappable, or None."""
    try:
        age = time.time() - LINK.stat().st_mtime
    except OSError:
        return None
    return LINK.read_text().strip() if age < LINK_HOLD_S else None


ET_RESET_UTC_HOUR = 4      # midnight ET; the daemon's constant, mirrored so both count the same day


def et_day(now=None):
    """The ET calendar day `now` belongs to, as an integer -- the daemon's own definition."""
    return int(((now if now is not None else time.time()) - ET_RESET_UTC_HOUR * 3600) // 86400)


def budget_left(now=None):
    """(remaining, used, cap). The cap is the daemon's, so the two agree on one number.

    THE DAY MATTERS. This read `used` with no day check while the daemon resets it on the ET
    rollover, so once 25 mints had accumulated over several days this tool refused every mint
    ("HET HAN MUC MINT") on a day with 4 links sent -- and, having already taken the hourly gate,
    it locked the daemon out of the hour too: no link 12:00, 13:00, 14:00 on 2026-09-04 (Khoa:
    "Đổi lại auth gửi 1 tiếng 1 lần như cũ")."""
    cap = 25
    try:
        import re as _re
        m = _re.search(r"DAILY_MINT_CAP\s*=\s*(\d+)", (ROOT / "auth_daemon.py").read_text())
        if m:
            cap = int(m.group(1))
    except OSError:
        pass
    try:
        b = json.loads(BUDGET.read_text())
        used = int(b.get("used", 0)) if int(b.get("et_day", -1)) == et_day(now) else 0
    except (OSError, ValueError, TypeError):
        used = 0
    return cap - used, used, cap


def since_last_mint():
    try:
        return time.time() - float(json.loads(LAST_MINT.read_text())["ts"])
    except (OSError, ValueError, KeyError):
        return float("inf")


def minted_this_hour():
    """Has a link already gone out in the CURRENT clock hour?

    Khoa, 2026-08-18: "các link xuất hiện vào các khoảng thời gian chẵn như 7:00 hay 8:00". On the
    hour, not an hour after the last one -- a schedule he can hold in his head beats a rolling
    window whose phase drifts with every urgent mint. The 60-second timer then delivers each link
    within a minute of the top of the hour.
    """
    try:
        last = float(json.loads(LAST_MINT.read_text())["ts"])
    except (OSError, ValueError, KeyError):
        return False
    return time.localtime(last)[:4] == time.localtime()[:4]   # same y/m/d/hour
LINK_LIFE_S = 603.0        # measured 2026-08-11: 403 until t+603s, 410 after


def wall_left():
    """Seconds remaining on the biometric wall, or 0. A missing file is NOT a wall."""
    try:
        w = json.loads(WALL.read_text())
    except (OSError, ValueError):
        return 0.0, None
    return max(0.0, float(w.get("until", 0)) - time.time()), w


def arm_wall(body):
    WALL.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    prev = None
    try:
        prev = json.loads(WALL.read_text())
    except (OSError, ValueError):
        pass
    dur = next_wall(prev)
    WALL.write_text(json.dumps({"until": now + dur, "duration": dur,
                                "why": "BIOMETRICS_THROTTLED", "ts": now,
                                "retry_after": None, "body_excerpt": body[:120]}))
    return dur


def bump_budget(now=None):
    now = now if now is not None else time.time()
    try:
        b = json.loads(BUDGET.read_text())
    except (OSError, ValueError):
        b = {}
    if int(b.get("et_day", -1)) != et_day(now):      # the ET day rolled: start the count again
        b = {}
    b["used"] = b.get("used", 0) + 1
    b["et_day"] = et_day(now)
    b["ts"] = now
    try:
        BUDGET.write_text(json.dumps(b))
    except OSError:
        pass
    return b.get("used")


def session_left_s():
    """Seconds until the session cookie expires, or None if there is no readable one.

    Split out from `session_live()` so a caller can WARN AHEAD instead of only asking "is it dead
    yet". The session lives exactly 4 hours and cannot be renewed, so its death is predictable to
    the second and nothing should have to wait for a 401 to find out -- on 2026-08-18 it died
    mid-round and took 29 of 31 rows carrying the new operators with it.
    """
    import base64
    import pickle
    try:
        jar = pickle.load(open(ROOT / "state/wq_cookies.pkl", "rb"))
    except Exception:                              # noqa: BLE001 - no jar is not a live session
        return None
    best = None
    for c in jar:
        v = getattr(c, "value", "") or ""
        if v.count(".") != 2:
            continue
        pay = v.split(".")[1]
        pay += "=" * (-len(pay) % 4)
        try:
            exp = json.loads(base64.urlsafe_b64decode(pay)).get("exp")
        except Exception:                          # noqa: BLE001
            continue
        if exp:
            left = exp - time.time()
            best = left if best is None else max(best, left)
    return best


def session_live():
    """Is the cookie jar still valid? Read the JWT's own expiry, never the file's mtime.

    Khoa, 2026-08-17: the session cookie lives exactly 4 hours -- confirmed by decoding it, issued
    22:37:32 and expiring 02:37:32. So the answer is on disk and costs nothing; asking the platform
    would cost a request against a bucket the probe is already fighting for.
    """
    import base64
    import pickle
    jar_path = ROOT / "state/wq_cookies.pkl"
    try:
        jar = pickle.load(open(jar_path, "rb"))
    except Exception:                              # noqa: BLE001 - no jar is not a live session
        return False
    for c in jar:
        v = getattr(c, "value", "") or ""
        if v.count(".") != 2:
            continue
        pay = v.split(".")[1]
        pay += "=" * (-len(pay) % 4)
        try:
            exp = json.loads(base64.urlsafe_b64decode(pay)).get("exp")
        except Exception:                          # noqa: BLE001
            continue
        if exp and exp > time.time() + RENEW_MARGIN_S:
            return True
    return False


def OB_GATE():
    """Winner-takes-the-hour across EVERY minter (daemon and this tool), via outbox.once_per_hour.

    True = this process holds the hour and may mint. The private minted_this_hour() cursor was the
    two-cursors disease at the mint layer: daemon and mint_link each counted their own mints, both
    minted in hour 11 on 2026-08-31, the second POST superseded the first inquiry, and the operator
    tapped a dead link. One lock, one cadence, whoever gets there first.
    """
    import outbox as OB
    return OB.once_per_hour("mint")


def _give_hour_back(force):
    """The hourly gate was taken and no link came of it: re-open the hour for the next minter."""
    if force:
        return
    try:
        import outbox as OB
        OB.release_hour("mint")
    except Exception:                                # noqa: BLE001
        pass


#: Quiet hours, local time, half-open [start, end). vps/auth_daemon.py carries the same two numbers
#: for its own timer; tools/tests/test_auth_quiet_hours.py fails if the two ever disagree.
QUIET_START_H, QUIET_END_H = 1, 6


def in_quiet_hours(now=None) -> bool:
    return QUIET_START_H <= time.localtime(now if now is not None else time.time()).tm_hour < QUIET_END_H


def mint(force=False, quiet=False):
    # DO NOT MINT INTO A LIVE SESSION.
    #
    # This runs on a 60-second timer, so without this guard it would mint a fresh link EVERY MINUTE
    # once the tap landed -- spending the daily mint budget, re-arming the biometric wall, and
    # burying the operator in links he does not need. The timer exists to catch a dead session, not
    # to keep replacing a working one.
    urgent = not session_live()

    # "1 link còn dư thì để dành" -- a link still inside its life is worth more than a new one,
    # and minting over it spends budget to replace something that already works.
    have = live_link()
    if have and not force:
        if not quiet:
            print("link con song (%.0fs tuoi); de danh, khong mint moi"
                  % (time.time() - LINK.stat().st_mtime))
        return 0

    if not urgent and not force:
        # A LIVE SESSION NEEDS NO LINK FROM THIS TIMER. The daemon owns the 3-hour top-up; this
        # 60-second timer exists to catch a DEAD session. Refusing BEFORE the gate is the point: a
        # refusal after taking it burned the hour for every other minter (measured 2026-09-04).
        if not quiet:
            print("phien con song; khong mint (top-up la viec cua daemon)")
        return 0

    if not force and in_quiet_hours():
        # QUIET HOURS, Khoa 2026-09-22: "cac khoang tu 1-6h se ko tu spam link va so link do de danh
        # vao nhung truong hop can thiet". The first implementation lived only in auth_daemon's
        # mint_gap() -- and this function is ALSO called by the wq-mint.timer every minute and by
        # forge_loop.sh every round, neither of which passes through the daemon. MEASURED 2026-09-23:
        # 8 routine mints between 23:25 and 09:00 against at most 4 the rule allows. Here is the one
        # place every routine minter passes through. Refused BEFORE OB_GATE, so a quiet-hours refusal
        # never burns the hour for anyone. --force (the operator asking) is untouched, by design.
        if not quiet:
            print("gio yen %02d:00-%02d:00; khong tu mint (--force van mint duoc)" % (QUIET_START_H, QUIET_END_H))
        return 0

    if not force and not OB_GATE():
        # URGENT DOES NOT JUMP THE HOUR EITHER. Khoa's rule is absolute ("chi duoc spam moi 1
        # tieng"), and the bypass turned every 5-minute loop restart into a mint attempt the
        # second a wall lifted: measured 2026-08-28, the 13:50:41 lift was POSTed at 13:51 by a
        # loop restart, the platform was still throttled, and the wall re-armed for 60 minutes --
        # the probe that was supposed to wait for the top of the hour fed the very throttle it
        # was waiting out. One mint per clock hour, from every path, session dead or not.
        if not quiet:
            print("da mint trong gio nay roi; link ke tiep vao dau gio sau")
        return 0

    left, used, cap = budget_left()
    if left <= 0:
        # THE BUDGET BLOCKS A ROUTINE MINT, NEVER AN URGENT ONE.
        #
        # 25 is OUR guess at a safe daily rate, not a number the platform publishes, and today's
        # count is already 33. Overspending is the likeliest thing feeding the wall -- but refusing
        # an urgent mint means the pipeline stays dead until the ET day rolls over, which is
        # certainly worse than a wall we now back off from. So the cap stops the hourly cadence and
        # never stops a recovery, and the overspend is stated out loud rather than hidden in a
        # counter nobody reads.
        if not force:
            # URGENT NO LONGER JUMPS THE CAP. The bypass reasoned "a paused pipeline is worse than
            # wall risk" and then produced the wall it feared: 37/25 mints on 2026-08-28 and
            # BIOMETRICS_THROTTLED from 12:50 onward, which paused the pipeline HARDER than the
            # cap ever could. With every mint path on an hourly cadence, 24/day fits under 25 --
            # reaching the cap now means something is minting too much, and the correct response
            # is to stop, not to push. --force remains for an operator's deliberate call.
            print("HET HAN MUC MINT hom nay (%d/%d): tu choi ke ca khi phien chet. Vuot tran la "
                  "cach buc tuong BIOMETRICS_THROTTLED duoc nuoi." % (used, cap))
            _give_hour_back(force)
            return 0
        print("CANH BAO --force: da dung %d/%d luot mint hom nay." % (used, cap))

    left, w = wall_left()
    if left > 0 and not force:
        until = time.strftime("%H:%M:%S", time.localtime(w["until"]))
        print("REFUSING TO MINT: biometric wall until %s (%.0f min left).\n"
              "Every attempt made while the wall is up re-arms it for another %d minutes, so "
              "retrying costs time instead of saving it.\nUse --force only if you have a reason."
              % (until, left / 60, WALL_S / 60))
        # EXIT 0: refusing because the wall is up is the CORRECT outcome, not a failure.
        #
        # It returned 2, so systemd marked wq-mint.service failed on every one of its 60-second
        # ticks -- and `systemctl --failed` is exactly what the dead-man switch reads, so a working
        # refusal would have raised a standing alarm about itself. This is the third time today I
        # have put a verdict in an exit code (health_report, deadman, now this) after writing a test
        # for the first two. An exit code answers "did this run correctly", never "is the news good".
        _give_hour_back(force)
        return 0

    creds = dict(l.split("=", 1) for l in CREDS.read_text().strip().splitlines() if "=" in l)
    s = requests.Session()
    s.headers.update({"Connection": "close"})
    s.auth = (creds["email"], creds["password"])
    try:
        r = s.post("https://api.worldquantbrain.com/authentication", timeout=60)
    except Exception as exc:                         # noqa: BLE001 -- a timeout must not eat the hour
        print("POST /authentication raised %s: %s -- hour given back" % (type(exc).__name__, exc))
        _give_hour_back(force)
        return 0
    body = (r.text or "")

    if r.status_code == 429 or "BIOMETRICS_THROTTLED" in body:
        dur = arm_wall(body)
        print("THROTTLED: %s -- wall armed for %d min (until %s)."
              % (body[:60], dur / 60,
                 time.strftime("%H:%M:%S", time.localtime(time.time() + dur))))
        # EXIT 0. Being refused by the platform is not this program failing; systemd reading it as
        # a failed unit is what put a standing alarm on the dead-man switch.
        return 0

    if r.status_code in (200, 201):
        print("already authenticated; no link needed")
        return 0

    if r.status_code != 401 or r.headers.get("WWW-Authenticate") != "persona":
        print("unexpected: HTTP %s %s" % (r.status_code, body[:120]))
        _give_hour_back(force)
        return 1

    bio = urljoin(r.url, r.headers.get("Location", ""))
    t = time.time()
    LINK.parent.mkdir(parents=True, exist_ok=True)
    LINK.write_text(bio)
    used = bump_budget()
    try:
        LAST_MINT.write_text(json.dumps({"ts": t}))
    except OSError:
        pass

    import outbox as OB
    msg = ("**CAN TAP AUTH**\n{seq} Mint %s, het han ~%s (song ~10 phut). Mint %s trong ngay.\n"
           "Loop tu chay lai <=5 phut sau khi tap.\n%s"
           % (time.strftime("%H:%M:%S", time.localtime(t)),
              time.strftime("%H:%M:%S", time.localtime(t + LINK_LIFE_S)), used, bio))
    # The hourly law is enforced INSIDE enqueue (the one door every m1 passes). Do not pre-check
    # once_per_hour here -- that would consume the lock and make enqueue refuse this same message.
    # Whatever the verdict, everything below still runs: the inquiry is bound to THIS process's
    # session, so returning early is the mint-and-exit defect (tap satisfied, cookies never
    # written, measured 2026-08-17).
    mid = OB.enqueue(kind="m1", channel="auth", cls="attention",
                     blocks=[(0, "head", msg)], dedup_key="m1:%s" % OB.sha12(bio))
    if not quiet:
        if mid == "suppressed:m1-hourly":
            print("m1: gio nay da co tin; van cho tap tren link nay (khong gui them)")
        else:
            print("minted and queued %s | expires ~%s | mint %s today"
                  % (mid, time.strftime("%H:%M:%S", time.localtime(t + LINK_LIFE_S)), used))

    # NOW WAIT FOR THE TAP, ON THIS SESSION.
    #
    # The first version of this tool minted, queued the link and exited -- and that made it useless.
    # A persona inquiry is bound to the SESSION THAT CREATED IT, so tapping authenticates `s` and
    # nothing else. Exiting here throws `s` away, the cookie is never written, and the operator taps
    # a link that authenticates a process which no longer exists. Measured 2026-08-17: Khoa tapped,
    # the platform was satisfied, and /users/self still answered 401 with a cookie jar 8 hours old.
    #
    # A tool that mints without collecting is worse than no tool: it spends a mint from the daily
    # budget, arms nothing, and looks like it worked.
    return _await_tap(s, bio, t, quiet)


def _await_tap(s, bio, minted_at, quiet=False):
    """Poll until the biometric is completed, then persist the cookie jar the pipeline reads."""
    import pickle
    # POLL THE PERSONA URL, NEVER /authentication.
    #
    # My first version polled POST /authentication every 5 seconds -- and that endpoint MINTS A NEW
    # INQUIRY each time. So the link Khoa was about to tap was being replaced by my own poller,
    # continuously. He tapped several times and every tap authenticated an inquiry that had already
    # been superseded, which is why nothing ever landed. It also spent mint budget on every poll and
    # is the likeliest reason the biometric wall kept re-arming.
    #
    # tools/auth_only.py has always had this right: `s.post(bio)` -- the persona URL itself. Posting
    # to it asks "has this inquiry been completed", it creates nothing, and it is the only poll that
    # leaves the operator's link intact.
    deadline = minted_at + LINK_LIFE_S + 120     # a little past expiry: the tap may land late
    while time.time() < deadline:
        try:
            r = s.post(bio, timeout=25)
        except Exception:
            time.sleep(5)
            continue
        if r.status_code in (200, 201):
            JAR = ROOT / "state/wq_cookies.pkl"
            tmp = JAR.with_suffix(".tmp")
            with open(tmp, "wb") as fh:
                pickle.dump(s.cookies, fh)
            tmp.replace(JAR)                     # atomic: a torn jar reads as a dead session
            if not quiet:
                print("TAPPED and saved: session live after %.0fs" % (time.time() - minted_at))
            return 0
        time.sleep(5)
    if not quiet:
        print("link expired without a tap (waited %.0fs)" % (time.time() - minted_at))
    return 1


if __name__ == "__main__":
    raise SystemExit(mint(force="--force" in sys.argv, quiet="--quiet" in sys.argv))
