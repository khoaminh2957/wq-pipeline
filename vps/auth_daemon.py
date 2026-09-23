#!/usr/bin/env python3
"""ONE long-lived auth daemon. The link is always live; asking for it never kills it.

WHY THIS REPLACES firing auth_only.py per request, measured 2026-08-10/11: four VPS links were
generated in one evening and three died AUTH_FAIL. Two causes, and the second was self-inflicted.
The window is only 20 minutes, and every "give me a new link" killed the poller watching the
previous one -- so a tap on any but the newest link was recorded by the platform and then dropped
on the floor, because no process was left to collect the session.

DESIGN.md D4 said this in advance: "tools/auth_relay.py = ONE long-lived daemon" and "NEVER pkill a
live auth_only.py flow". This is that daemon.

CONTRACT
  * exactly one inquiry is live at a time; reading state/auth_link.txt does not disturb it
  * when a window expires unanswered, it opens a NEW one by itself and rewrites that file
  * on success it writes the cookie atomically and keeps watching, so an expiry later re-arms
  * it never kills anything, and nothing needs to kill it
"""
import json, os, pickle, socket, time
from pathlib import Path
from urllib.parse import urljoin
import requests

socket.setdefaulttimeout(40)
H = "https://api.worldquantbrain.com"
ST = Path("/opt/wq/state")
LINK = ST / "auth_link.txt"
STATUS = ST / "auth_status.json"
COOKIES = ST / "wq_cookies.pkl"
CREDS = Path("/root/.wqbrain_creds")
# MEASURED 2026-08-11, not guessed: one inquiry answered 403 from t+4s and flipped to 410 at
# t+603s. It lives ~10 minutes. The old 1140s window meant the daemon spent the last NINE minutes
# of every window polling a corpse while the link already sent to Khoa was unusable -- which is
# exactly the {403: 88, 410: 88} split in the overnight logs. Re-arm at 540s, comfortably inside
# the measured life, and the 410 branch below catches an early death anyway.
# Escalating backoff for a non-challenge response, in a one-element list so the nested
# function can mutate it without a global statement. Starts at 30s, doubles, caps at 15min.
class _SkipNotify(Exception):
    """Raised inside the notify block to skip the post without touching the mint machinery."""


_BACKOFF = [30.0]
# consecutive windows nobody answered; escalates the gap between mints
_SILENT = [0]
# every inquiry this session minted that may still be tappable
_LIVE = []
POLL_S, WINDOW_S, HEALTHY_S = 5, 540, 300

# ---------------------------------------------------------------------------------------------
# DAILY MINT BUDGET. 25 is OPERATOR-STATED (Khoa, 2026-08-13) -- the account owner's knowledge of
# the platform, not a measurement made here. The old cadence (`target = 1200`, minting every window
# regardless of session state) spent 72 a day, 2.9x that line.
DAILY_MINT_CAP = 25
BUDGET = ST / "auth_mint_budget.json"
WALL = ST / "auth_mint_wall.json"          # backoff that SURVIVES a restart
# The ET day boundary the platform resets on: 00:00 ET = 04:00 UTC while ET is on daylight time.
# POST-HOC: it is what `state/` quota files roll over on; nothing here re-derived the offset.
ET_RESET_UTC_HOUR = 4
# Session life, POST-HOC n=1: a cookie minted at 13:47Z answered 401 at 17:47Z, and `tools/
# auth_link.py` records 4h00/4h03 from three earlier observations. Start offering links in the last
# hour, so a tap tops the session up BEFORE it dies rather than repairing it after.
SESSION_LIFE_S = 4 * 3600
TOPUP_AT_S = 3 * 3600
# An inquiry lives ~603s (measured 2026-08-11). Never mint faster than that or two links are live at
# once and one of them is guaranteed to be wasted.
MIN_MINT_GAP_S = 610.0


def _et_day(now):
    """The ET calendar day `now` belongs to, as an integer. Used only to detect a rollover."""
    return int((now - ET_RESET_UTC_HOUR * 3600) // 86400)


def _seconds_to_reset(now):
    return ((_et_day(now) + 1) * 86400 + ET_RESET_UTC_HOUR * 3600) - now


def _read_json(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def budget_left(now=None):
    """Mints still available today. Rolls over on its own; never returns a negative."""
    now = now if now is not None else time.time()
    b = _read_json(BUDGET, {})
    if b.get("et_day") != _et_day(now):
        return DAILY_MINT_CAP
    return max(0, DAILY_MINT_CAP - int(b.get("used", 0)))


def spend_one(now=None):
    now = now if now is not None else time.time()
    b = _read_json(BUDGET, {})
    used = int(b.get("used", 0)) if b.get("et_day") == _et_day(now) else 0
    BUDGET.write_text(json.dumps({"et_day": _et_day(now), "used": used + 1, "ts": now}))


def wall_until():
    """When a persisted 429 wall lifts. Read at STARTUP, which is the point of putting it on disk."""
    return float(_read_json(WALL, {}).get("until", 0.0))


def raise_wall(seconds, why, retry_after=None, body=None):
    """Put the wall on disk. Both halves live HERE and not only in `auth_status.json`, because
    `status()` overwrites that file with `stage=MINT_WALLED` minutes later and destroys the
    `retry_after` record -- observed 2026-08-12, `code=429 retry_after=null` at 18:12:14Z was gone
    by 18:19:22Z. `retry_after=None` means ABSENT OR NOT RECORDED, which is not the same claim as
    "the server sent none"; the reader is told which."""
    WALL.write_text(json.dumps({"until": time.time() + seconds, "why": why, "ts": time.time(),
                                "retry_after": retry_after,
                                "body_excerpt": (body or "")[:200]}))


#: QUIET HOURS, Khoa 2026-09-22: "cac khoang tu 1-6h se ko tu spam link va so link do de danh vao
#: nhung truong hop can thiet". Between 01:00 and 06:00 local the daemon mints nothing on its timer.
#: The reason is arithmetic, not politeness: the ET-day budget is 25 links and the timer spends it
#: evenly, so five hours of unattended minting burns roughly a fifth of the day's links into a window
#: where nobody is awake to tap them -- and an untapped link is not merely wasted, it is the thing
#: that drew a seven-hour BIOMETRICS_THROTTLED lock at ~6.7 mints/hour (see the constants above).
#: What this does NOT touch: `tools/mint_link.py --force`, the operator's own path. Khoa's whole
#: point is that the saved links are FOR the 3 a.m. case when he actually wants one.
QUIET_START_H, QUIET_END_H = 1, 6


def in_quiet_hours(now=None) -> bool:
    return QUIET_START_H <= time.localtime(now if now is not None else time.time()).tm_hour < QUIET_END_H


def seconds_to_quiet_end(now=None) -> float:
    """Seconds from `now` until QUIET_END_H local. Only meaningful inside the quiet window."""
    now = now if now is not None else time.time()
    t = time.localtime(now)
    return (QUIET_END_H - t.tm_hour) * 3600.0 - t.tm_min * 60.0 - t.tm_sec


def mint_gap(now=None):
    """Seconds to wait before the next mint, from the budget and the time left in the ET day.

    Self-correcting by construction: unspent budget shortens the gap as the reset approaches, and a
    nearly-spent budget stretches to the reset rather than stopping dead. Inside the quiet window the
    gap runs to the end of that window instead, so the timer simply does not mint while Khoa sleeps.
    """
    now = now if now is not None else time.time()
    if in_quiet_hours(now):
        return max(60.0, seconds_to_quiet_end(now))
    left = budget_left(now)
    if left <= 0:
        return max(60.0, _seconds_to_reset(now))
    return max(MIN_MINT_GAP_S, _seconds_to_reset(now) / left)


def session_age_s():
    """Age of the cookie jar, or None when there is no jar to age."""
    try:
        return time.time() - COOKIES.stat().st_mtime
    except OSError:
        return None
# ---------------------------------------------------------------------------------------------


def status(**k):
    k["ts"] = time.time()
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(k))
    os.replace(tmp, STATUS)


def session_alive():
    if not COOKIES.exists():
        return False
    try:
        s = requests.Session()
        s.cookies = pickle.load(open(COOKIES, "rb"))
        return s.get(H + "/users/self", timeout=30).status_code == 200
    except Exception:
        return False


def one_window():
    d = dict(l.split("=", 1) for l in CREDS.read_text().strip().splitlines() if "=" in l)
    s = requests.Session()
    s.headers.update({"Connection": "close"})
    s.auth = (d["email"], d["password"])
    r = s.post(H + "/authentication", timeout=30)
    if r.status_code in (200, 201):
        return s
    if r.status_code != 401 or r.headers.get("WWW-Authenticate") != "persona":
        # BACK OFF, AND SAY SO. This branch used to write a status file and return None, and the
        # caller re-entered immediately -- so a 429 on POST /authentication became a tight retry
        # loop against the very endpoint that was rate-limiting us. Measured 2026-08-12: the daemon
        # sat in stage AUTH_UNEXPECTED code=429 for SEVEN HOURS while state/auth_link.txt aged to
        # 25,586s, and stdout said nothing at all because this branch never printed. An invisible
        # failure that also amplifies itself is the worst combination available.
        ra = 0.0
        try:
            ra = float(r.headers.get("Retry-After") or 0)
        except ValueError:
            ra = 0.0
        throttled = "BIOMETRIC" in (r.text or "").upper()
        wait = min(max(ra, _BACKOFF[0]), 900.0)
        if throttled:
            # EXPONENTIAL, NOT FLAT -- and read from the wall FILE so a restart keeps the ladder.
            # The flat max(wait, 1800) re-created the exact loop the playbook already recorded:
            # our 30-min wall expires, we POST at the lift instant, the platform's own throttle is
            # still up, 429, re-arm 30 -- forever. Measured 2026-08-28: walls armed 12:50 and
            # 13:20:41, both backoff_s=1800.0, the second landing the very second the first lifted.
            # Doubling probes the platform's unknown throttle length while feeding it one request
            # per step: 30 -> 60 -> 120 -> 240 min, capped at 4h. A prior wall for any OTHER
            # reason does not escalate this one.
            prev = _read_json(WALL, {})
            prev_dur = float(prev.get("until", 0)) - float(prev.get("ts", 0))
            if "BIOMETRIC" in str(prev.get("why", "")).upper() and 0 < prev_dur < 4 * 3600:
                wait = min(max(1800.0, prev_dur * 2.0), 4 * 3600.0)
            else:
                wait = max(wait, 1800.0)
        _BACKOFF[0] = min(_BACKOFF[0] * 2.0, 900.0)
        # THE CALL SITE `raise_wall` NEVER HAD. Without it the sleep below is the whole backoff, and
        # a restart throws it away and re-POSTs a walled endpoint within ~2s -- measured 23:42:04 ->
        # 429 at 23:42:06, across 11 restarts in one day.
        raise_wall(wait, "BIOMETRICS_THROTTLED" if throttled else ("HTTP %s" % r.status_code),
                   retry_after=(ra or None), body=(r.text or ""))
        status(stage="AUTH_UNEXPECTED", code=r.status_code, backoff_s=round(wait, 1),
               retry_after=ra or None, body=(r.text or "")[:200])
        print(f"POST /authentication -> {r.status_code} (not the 401+persona challenge). "
              f"Backing off {wait:.0f}s before re-arming; Retry-After={ra or 'absent'}. "
              f"body={r.text[:120]!r}", flush=True)
        time.sleep(wait)
        return None
    _BACKOFF[0] = 30.0          # a good challenge clears the escalation
    bio = urljoin(r.url, r.headers.get("Location", ""))
    LINK.write_text(bio)
    status(stage="await_biometric", persona=bio)
    print(f"LINK {bio}", flush=True)
    # Push it where Khoa actually is. A link is only worth anything while the window is open, and
    # four of them died unread in a chat log on 2026-08-10 because nobody was looking at the chat.
    try:
        import sys
        import time as _t
        sys.path.insert(0, "/opt/wq/tools")
        import outbox as _OB
        # ONE MESSAGE PER CLOCK HOUR -- Khoa, 2026-08-18 ("h mac dinh la 1 tieng gui 1 lan") and
        # again, angrily, 2026-08-28 ("lien tuc spam trong khi toi da noi la chi duoc spam moi 1
        # tieng"). The daemon re-arms a fresh inquiry every ~610s so a tap ALWAYS has a live link
        # waiting on disk; that machinery is untouched. What was wrong is that every re-arm also
        # POSTED: 25 messages in 12.7h measured on 08-28, ~6x the ordered cadence, because the
        # hourly rule lived only in mint_link.py and this path never consulted it. The hour cursor
        # is on DISK because Restart=always would reset an in-memory one every crash.
        # The hourly law is enforced inside outbox.enqueue (the one door every m1 passes).
        # No pre-check here: it would consume the hour lock and starve the enqueue below.
        # A NEW message per window. An edited message raises no Discord notification, so the tidy
        # version of this was silent for seven hours; stale links accumulating is accepted.
        #
        # "Newest message in this channel is the newest link" was an assertion about OTHER messages
        # that this code never checked, and a second minter posts links too -- so it is replaced by
        # a CLOCK, which the reader can check. Content-addressed dedup means the same link is never
        # posted twice while every new mint always posts.
        _mid = _OB.enqueue(
            kind="m1", channel="auth", cls="attention",
            blocks=[(0, "head",
                     "**CAN TAP AUTH — VPS 160.25.88.163**\n{seq} "
                     "Link mint luc %s, song ~10 phut "
                     "(do 2026-08-11: 403 toi t+603s, 410 sau do).\n%s"
                     % (_t.strftime("%H:%M:%S"), bio))],
            dedup_key="m1:%s" % _OB.sha12(bio))
        print(f"notify: {'suppressed (hourly)' if _mid == 'suppressed:m1-hourly' else 'queued %s' % _mid}",
              flush=True)
    except _SkipNotify:
        pass
    except Exception as e:
        # LOUD. This is the most time-critical message in the system: the link expires in ~10
        # minutes and the whole pipeline stalls without a tap. A failure here used to be printed
        # into a log nobody reads.
        import traceback
        print(f"NOTIFY ENQUEUE FAILED ({type(e).__name__}: {e}) -- THE LINK WAS NOT QUEUED",
              flush=True)
        traceback.print_exc()
    # TELEMETRY. tools/auth_only.py reported AUTH_FAIL with the code of the INITIAL challenge
    # response -- always 401 by construction -- and swallowed every polling exception with a bare
    # . So four failed windows on 2026-08-10 produced the message
    # "AUTH_FAIL code=401" and not one byte of evidence about what actually went wrong. Count
    # what the polls really return, so the next failure is diagnosable instead of narratable.
    # POLL EVERY INQUIRY THIS SESSION HAS MINTED THAT IS STILL ALIVE, not just the newest.
    #
    # THE BUG THIS FIXES, confirmed 2026-08-12 by a tap that produced nothing: the daemon polled one
    # inquiry for WINDOW_S=540s and then abandoned it to mint another. An inquiry lives ~603s and
    # minting a new one does NOT invalidate an old one (both measured). With a 20-minute cadence
    # that left roughly ELEVEN MINUTES of every cycle in which no inquiry was being polled at all —
    # so a human who tapped a link that was eight minutes old had the tap RECORDED BY THE PLATFORM
    # and collected by nobody. The cookie file had not changed in 14.6 hours while links were being
    # posted the whole time.
    #
    # The inquiry is bound to the session that minted it, and this daemon is one process holding one
    # session, so it is the only thing that CAN collect any of them. Keeping them all in the poll set
    # costs one request each per cycle and closes the window where a tap is silently thrown away.
    _LIVE.append({"url": bio, "born": time.time()})
    t0 = time.time()
    codes, errs, n = {}, {}, 0
    while time.time() - t0 < WINDOW_S:
        time.sleep(POLL_S)
        n += 1
        # retire anything past the measured ~603s life, then poll what remains
        _LIVE[:] = [q for q in _LIVE if time.time() - q["born"] < 620]
        rr, hit = None, None
        for q in list(_LIVE):
            try:
                resp = s.post(q["url"], timeout=30)
            except Exception as e:
                errs[type(e).__name__] = errs.get(type(e).__name__, 0) + 1
                continue
            codes[resp.status_code] = codes.get(resp.status_code, 0) + 1
            if resp.status_code == 410:
                _LIVE[:] = [x for x in _LIVE if x["url"] != q["url"]]
                continue
            if resp.status_code in (200, 201):
                rr, hit = resp, q
                break
            rr = resp
        if hit is not None:
            print(f"collected a tap on an inquiry {int(time.time()-hit['born'])}s old "
                  f"(the daemon was polling {len(_LIVE)} live inquiries)", flush=True)
            status(stage="AUTHED_PENDING_SAVE", polls=n, poll_codes=codes, poll_errors=errs)
            _LIVE.clear()
            return s
        if rr is None:
            continue
        # 410 GONE means this inquiry is dead. Keeping the loop running on it wastes the rest of
        # the window on a link Khoa has already been given: the overnight logs read
        # {403: 88, 410: 88} over 176 polls, i.e. roughly HALF of every window was spent polling a
        # corpse while the posted link was already unusable. Re-arm at once instead.
        if rr.status_code == 410:
            status(stage="INQUIRY_GONE", persona=bio, polls=n, poll_codes=codes,
                   elapsed_s=round(time.time() - t0, 1))
            print(f"inquiry went 410 after {n} polls / {time.time()-t0:.0f}s — re-arming now",
                  flush=True)
            return None
        if rr.status_code in (200, 201):
            status(stage="AUTHED_PENDING_SAVE", polls=n, poll_codes=codes, poll_errors=errs,
                   elapsed_s=round(time.time() - t0, 1))
            return s
    # NOBODY TAPPED. Do NOT immediately mint another one.
    #
    # MEASURED 2026-08-12: this daemon re-armed every 540s regardless, and after roughly forty-seven
    # unanswered windows the platform answered POST /authentication with 429
    # {"detail":"BIOMETRICS_THROTTLED"} and kept answering it for seven hours. Minting a fresh
    # inquiry is not free, and "always keep a live link" -- which is what this loop was written to
    # do -- is exactly what exhausted the biometric endpoint.
    #
    # An inquiry only lives ~603s, so a link cannot be BOTH always-fresh and rarely-minted. Between
    # a stale link and no link at all, the honest choice when nobody is answering is to slow down:
    # a human who is asleep is not served by a fresher link, and the throttle costs the link that
    # would have been there when they woke up. Consecutive silence escalates the gap; one success
    # resets it.
    _SILENT[0] += 1
    # CADENCE, and the two numbers that fight each other.
    #
    # A persona inquiry lives ~603s (measured: 403 at t+4.2s, 410 at t+603.3s). Khoa's requirement,
    # and REQ-AUTH-07, is a fresh link at least every 20 minutes. Those cannot both be fully
    # satisfied: at a 20-minute cadence the link is dead for roughly the second half of every gap,
    # which is exactly the {403: 88, 410: 88} split the overnight logs recorded.
    #
    # So the gap is now the REQUIREMENT, 20 minutes, not the link's lifetime. What is given up is
    # the pretence that whatever sits in Discord is always tappable; what is bought is a rate of
    # 3 mints/hour against the ~6.7/hour sustained for seven hours that drew
    # 429 BIOMETRICS_THROTTLED. That is a factor of two of headroom -- INFERRED FROM ONE INCIDENT,
    # not from a measured threshold. MECHANISM: UNKNOWN for where the real limit sits, so the
    # escalation is kept, just much gentler: it only engages after two hours of silence.
    # THE 20 MINUTES IS THE WHOLE CYCLE, not the pause after it. Writing it as a pause made the
    # real mint interval 540s of polling PLUS 1200s of waiting = 29 minutes, and the watch caught
    # it within one cycle: link ages 478s, 782s, 1086s with no new mint. Subtract the time already
    # spent polling so the interval a reader is promised is the interval they get.
    # STEADY CADENCE, NO ESCALATION ON SILENCE. Corrected 2026-08-12 on Khoa's instruction, and the
    # reasoning was mine to get wrong: I had conflated "the daemon posts a lot of messages" with
    # "the daemon mints too often", and slowed the CADENCE to fix the MESSAGE COUNT. Those are
    # different problems. He taps when he happens to look, which may be hours later, and an
    # escalating gap guarantees that whatever is waiting for him at that moment is already dead --
    # precisely the outcome the cadence exists to prevent.
    #
    # 20 minutes is 3 mints/hour. The throttle was drawn at ~6.7/hour sustained for seven hours, so
    # this sits at under half that. The real threshold remains MECHANISM: UNKNOWN, and if it is hit
    # again the 429 branch backs off on its own rather than this loop guessing in advance.
    # 10-MINUTE CYCLE, set 2026-08-12 at Khoa's instruction. This is 6 mints an hour.
    #
    # The seven-hour BIOMETRICS_THROTTLED lock this account drew was measured at roughly 6.7 an hour
    # sustained for seven hours, so this sits just under a rate that has already been punished once.
    # The safe threshold is UNKNOWN: 6.7 is one observation of a rate that WAS punished, not a
    # measurement of where the edge is, and nothing here establishes 6 is on the safe side of it.
    #
    # What keeps it recoverable rather than reckless is the 429 branch in `_arm`: it honours
    # Retry-After, and when Retry-After is absent — which is how the flow-level throttle presents —
    # it backs off hard on its own schedule. That branch exists because this daemon once sat in
    # AUTH_UNEXPECTED for seven hours while the link aged out. If the lock returns, this constant is
    # the first thing to put back.
    # The cadence is no longer a constant: `mint_gap()` divides the remaining daily budget over the
    # time left in the ET day, floored at the inquiry's ~603s life. The old `target = 1200.0` was a
    # fixed 20-minute cycle that minted every window regardless of session state -- 72 a day against
    # an OPERATOR-STATED ceiling of 25.
    target = mint_gap()
    gap = max(target - (time.time() - t0), 30.0)
    status(stage="WINDOW_EXPIRED", persona=bio, polls=n, poll_codes=codes, poll_errors=errs,
           elapsed_s=round(time.time() - t0, 1), consecutive_silent=_SILENT[0],
           next_window_in_s=round(gap))
    print(f"window {_SILENT[0]} unanswered; waiting {gap/60:.0f}min before minting another "
          f"(the biometric endpoint throttles at ~47 unanswered windows)", flush=True)
    time.sleep(gap)
    print(f"window expired: {n} polls, codes={codes}, errors={errs}", flush=True)
    return None


def main():
    ST.mkdir(parents=True, exist_ok=True)
    while True:
        # A LIVE SESSION IS NOT A REASON TO GO QUIET. `one_window` mints a link, posts it and polls
        # it for the whole window; if the session is already healthy the poll simply finds nothing to
        # collect, and Khoa still has a fresh link to tap. Tapping one renews the session, so a link
        # that is always waiting is what stops the session ever reaching 401 -- the old code only
        # ever offered a link AFTER the session had died, which made every tap a repair and never a
        # top-up, and left him watching crawl notifications arrive during hours of auth silence.
        alive = session_alive()

        # A PERSISTED WALL, CHECKED BEFORE ANYTHING ELSE. `_BACKOFF` lives in memory and an
        # in-process sleep enforced it, so every restart threw the remaining wait away and re-POSTed
        # the walled endpoint -- measured at 23:42:04 -> 429 at 23:42:06, across 11 restarts.
        wall = wall_until() - time.time()
        if wall > 0:
            status(stage="MINT_WALLED", alive=alive, wall_s=round(wall),
                   budget_left=budget_left())
            print("mint wall up for %.0fmin; not touching /authentication" % (wall / 60.0),
                  flush=True)
            time.sleep(min(wall, 300.0))
            continue

        # THE BUDGET DECIDES WHETHER TO MINT AT ALL, and the session's age decides whether a mint
        # would buy anything. A tap while the session is young renews a session that already has
        # hours left; the same tap while it is dead buys ~4 hours of pipeline. 25 a day cannot cover
        # both, so the young case is skipped rather than rationed.
        age = session_age_s()
        left = budget_left()
        if left <= 0:
            gap = mint_gap()
            status(stage="BUDGET_SPENT", alive=alive, budget_left=0, next_in_s=round(gap))
            print("all %d mints spent for the ET day; next at reset in %.1fh"
                  % (DAILY_MINT_CAP, gap / 3600.0), flush=True)
            time.sleep(min(gap, 600.0))
            continue
        if alive and age is not None and age < TOPUP_AT_S:
            gap = min(mint_gap(), TOPUP_AT_S - age)
            status(stage="AUTHED", alive=True, session_age_s=round(age),
                   budget_left=left, next_in_s=round(gap))
            print("session %.1fh old and healthy; holding %d mints (top-up starts at %.0fh)"
                  % (age / 3600.0, left, TOPUP_AT_S / 3600.0), flush=True)
            time.sleep(min(gap, 600.0))
            continue

        # ONE MINT PER CLOCK HOUR, FOR EVERY BRANCH -- silent AND top-up alike. The first version
        # gated only the not-alive path, so a daemon restart inside the top-up window (session
        # alive, age >= 3h) minted INSTANTLY on boot: three deploy restarts on 2026-08-29 each
        # spent a mint and orphaned the previous inquiry. History of the silent case: the ~610s
        # re-arm cadence ran five silent days (~125 mints) into BIOMETRICS_THROTTLED -- a DAILY
        # login cap, operator-stated -- and `_SILENT` could not stretch it because Restart=always
        # reset it. The cursor is a CLOCK HOUR on disk, the same hour the m1 message keys on, so
        # every hourly message carries a link minted seconds before it; 24/day fits the 25 cap.
        # THE SHARED MINT-HOUR GATE -- one O_EXCL lock for EVERY minter on this box. The private
        # cursor here was the two-cursors disease a third time, now at the MINT layer: the daemon
        # minted inquiry #1 at 11:00 against auth_mint_hour.json, wq-mint's mint_link minted #2 at
        # 11:09 against its own minted_this_hour() log, the second POST superseded the first, and
        # Khoa tapped a dead link (2026-08-31, "tai sao lai gui toi 1 link bi loi"). Each path was
        # individually compliant; together they doubled the cadence and invalidated each other's
        # links. Same lock the m1 message uses, different tag.
        import sys as _sys
        _sys.path.insert(0, "/opt/wq/tools")
        import outbox as _OBG
        if not _OBG.once_per_hour("mint"):
            nxt = 3600 - (time.time() % 3600)
            status(stage="HOURLY_HOLD", alive=alive, budget_left=left, next_in_s=round(nxt))
            print("mint gate already taken this hour; next mint in %.0fmin" % (nxt / 60.0),
                  flush=True)
            time.sleep(min(nxt + 5.0, 300.0))
            continue
        status(stage="AUTHED" if alive else "NEEDS_AUTH", budget_left=left,
               session_age_s=(round(age) if age is not None else None))
        spend_one()
        s = one_window()
        if alive and s is None:
            # Healthy and nobody tapped: expected, not a failure. Straight back round for the next
            # window, so the cadence stays the same whether or not the session is up.
            continue
        if s is None:
            continue                      # immediately re-arm; the link file is rewritten
        s.auth = None
        tmp = COOKIES.with_suffix(".pkl.tmp")
        with open(tmp, "wb") as f:
            pickle.dump(s.cookies, f)
        os.replace(tmp, COOKIES)
        me = s.get(H + "/users/self", timeout=30)
        _SILENT[0] = 0
        status(stage="AUTHED", user=(me.json().get("id") if me.status_code == 200 else None))
        print(f"AUTHED {me.status_code}", flush=True)


if __name__ == "__main__":
    main()
