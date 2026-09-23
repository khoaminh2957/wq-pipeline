#!/usr/bin/env python3
"""Pipeline health to the health webhook. Measured numbers only, with their denominators.

Every metric here exists because something went wrong today and the existing reporting could not
have caught it:

  * SIM RATE over a moving window, never a cumulative total. Throughput fell to zero twice on
    2026-08-10 while the cumulative count kept looking healthy.
  * AUTH state AND session age. Auth expiry is the pipeline's dominant failure: 2h09m lost in one
    stall, and 218 `auth=401 — holding` events against 35 launches in the log before that.
  * JOURNAL AGE. The queue can look full while nothing lands.
  * SCREEN, split into measured and NEVER-MEASURED. `pipeline_status` counted 988 alphas whose PnL
    fetch returned nothing as screen FAILURES, reporting 7.3% where the honest figure was 15.0%.
    A metric absent from a record is not a metric that failed.
  * CELLS SHORT, read from the platform's own counter rather than derived.
  * API ERRORS by class in the window, so a 429 wall is distinguishable from an auth death.
  * THE AUTH WALL, by CLASS, with the origin of its expiry. Two different 429s reach
    /authentication and they were rendering identically. `{"message":"API rate limit exceeded"}`
    arrives WITH `Retry-After: 7.0` -- a seven-second wait the server itself stated.
    `{"detail":"BIOMETRICS_THROTTLED"}` arrives with `Retry-After` ABSENT and has been observed
    outlasting four consecutive 1800 s client waits. Both used to print as "auth AUTH_UNEXPECTED",
    so a reader could not tell seven seconds from an unbounded lock. See `auth_wall()`.

Nothing here is a forecast. Where a number is an extrapolation it says so.

  python3 tools/health_report.py             # post
  python3 tools/health_report.py --print     # stdout only, post nothing
  python3 tools/health_report.py --operator  # the single phone line, nothing else
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
ST = ROOT / "state"
WINDOW_MIN = 60


def _env(key):
    v = os.environ.get(key)
    if v:
        return v.strip()
    try:
        for line in (ROOT / ".env").read_text().splitlines():
            k, _, val = line.partition("=")
            if k.strip() == key:
                return val.strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def _tail(path, n=4000):
    try:
        return (ST / path).read_text(errors="ignore").splitlines()[-n:]
    except OSError:
        return []


MARK = ST / "health_last_count.json"


def sim_rate():
    """(sims since the previous report, per-minute) by DIFFERENCING the row count.

    The first version searched each row for a "ts" field and windowed on it. Journal rows carry no
    timestamp at all -- keys are alpha/checks/drawdown/fitness/formula/meta/old_id/returns/settings/
    sharpe/status/turnover and nothing else -- so it matched nothing and reported 0.00 sims/min
    while the pool log beside it read "journaled 10/208". A health metric that reads zero while the
    engine is working is worse than no metric: it would have cried wolf every 30 minutes until the
    alarm meant nothing. Count rows, remember the count, and difference it.
    """
    # COUNT EVERY JOURNAL, not one hardcoded name. On 2026-08-13 this counted only the old funnel's
    # `resim_results.jsonl` and reported `0.0/min` while a run wrote 18 rows a minute into
    # `state/harness13/sim_ceiling2/journal.jsonl`. Same defect as `journal_age_min` had, in the one
    # number an operator actually reads to decide whether the pipeline is working.
    n = 0
    seen = 0
    for f in ST.glob("**/*.jsonl"):
        if not f.is_file():
            continue
        try:
            with open(f, "rb") as fh:
                fh.seek(0, 2)
                fh.seek(max(0, fh.tell() - 4096))
                tail = fh.read().decode("utf-8", "ignore")
                if not any('"%s"' % st in tail for st in _JOURNAL_STATUSES):
                    continue
                fh.seek(0)
                n += sum(1 for _ in fh)
                seen += 1
        except OSError:
            continue
    if not seen:
        return None, None, None
    # THE RATE IS ONLY MEANINGFUL IF THE SAME FILES WERE COUNTED BOTH TIMES. When this scan was
    # widened from a name list to a content check, the very first reading compared a new, larger
    # total against the old mark and printed **4,572 sims/min** -- an artifact of the change, not a
    # measurement of anything. Recording how many files went into the total lets the next reading
    # say "not measurable" instead of inventing a number.
    now = time.time()
    prev = None
    try:
        prev = json.loads(MARK.read_text())
    except Exception:
        pass
    try:
        MARK.write_text(json.dumps({"count": n, "ts": now, "files": seen}))
    except OSError:
        pass
    if not prev or prev.get("count") is None or now - prev.get("ts", now) < 30:
        return n, None, None          # first run since boot: a total, honestly labelled as one
    if prev.get("files") != seen:
        return n, None, None          # the counted set moved; a difference across it means nothing
    dn = n - prev["count"]
    dt_min = (now - prev["ts"]) / 60
    return n, dn, round(dn / dt_min, 2) if dt_min > 0 else None


def auth_state():
    try:
        d = json.loads((ST / "auth_status.json").read_text())
        age = int((time.time() - d.get("ts", 0)) / 60) if d.get("ts") else None
        return d.get("stage", "?"), age
    except Exception:
        return "unknown", None


# ------------------------------------------------------------------------------------ auth wall
#
# TWO WRITERS, TWO SHAPES, AND ONLY ONE OF THEM RECORDS THE BODY.
#
#   tools/auth_backoff.py -> state/auth_backoff.json
#       {"blocked_until", "class", "recorded_at", "retry_after_s", "source", "consecutive",
#        "body_excerpt"}                     -- classified from the body; Retry-After preserved.
#   the VPS daemon (/opt/wq/auth_daemon.py) -> state/auth_mint_wall.json
#       {"until": 1786560134.137, "why": "BIOMETRICS_THROTTLED", "ts": ...}
#                                            -- the CLASS is here, but not Retry-After.
#   the same daemon                          -> state/auth_status.json
#       {"stage":"AUTH_UNEXPECTED", "code":429, "backoff_s":1800.0, "retry_after":null, "ts":...}
#                                            -- Retry-After is here, but NO body, so no class.
#
# Three files, and no single one of them holds both halves. So all three are read, in that order,
# and each field is reported from the writer that actually recorded it. `retry_after` therefore has
# THREE states and not two -- PRESENT, ABSENT, and NOT RECORDED -- because "the writer did not keep
# it" is not the same claim as "the server did not send it", and collapsing them would manufacture
# a measurement out of a gap in the logging.
#
# The distinction that matters is not which file we read, it is WHERE THE EXPIRY CAME FROM:
#
#   SERVER-STATED  -- `Retry-After` was present. The endpoint told us when to come back. This is a
#                     wall with a real, short, known expiry (the only observation on disk is 7.0 s).
#   CLIENT POLICY  -- `Retry-After` was ABSENT. `backoff_s`/`blocked_until` is then OUR OWN sleep,
#                     a number this repo chose. It is NOT when the wall lifts and must never be
#                     printed as one. Measured 2026-08-12: four consecutive 1800 s client waits
#                     were each followed by another BIOMETRICS_THROTTLED refusal, so on that
#                     episode the true lift was more than 90 min after the client's first guess.
#   NOT RECORDED   -- the writer kept neither body nor Retry-After. Say so; do not infer a class
#                     from the backoff length, which would be reading our own policy back as if it
#                     were the server's answer.
#
# MECHANISM: UNKNOWN for how long a BIOMETRICS_THROTTLED lock lasts. Two on-disk episodes give two
# different answers (one cleared inside ~43 min, one exceeded 90 min) and no fixed number fits
# both, so this function never prints a predicted lift for a client-policy wall.

WALL = ST / "auth_backoff.json"
MINT_WALL = ST / "auth_mint_wall.json"
LINK_LIVE_S = 600.0     # the window length the daemon itself quotes to the operator ("~10 minutes")


def _wall_from_backoff_file(now):
    """Delegates the blocked/not-blocked decision to auth_backoff.check().

    Re-implementing that decision here would fail OPEN on a corrupt state file -- an unreadable
    record would parse as "no wall" and this report would say the endpoint is free when nobody can
    tell. auth_backoff fails CLOSED on exactly that case, so the answer is taken from it and only
    `retry_after_s`, which Block does not carry, is read from the raw record.
    """
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import auth_backoff
        # WALL is passed explicitly: auth_backoff resolves its own default path from ITS location,
        # so leaving it implicit lets this report answer about a different file than the one it
        # then reads `retry_after_s` out of.
        block = auth_backoff.check(now=now, state_path=WALL)
    except Exception:
        return None
    if block is None:
        return None
    ra = None
    try:
        ra = json.loads(WALL.read_text()).get("retry_after_s")
    except Exception:
        pass
    return {"cls": block.cls, "retry_after": ra, "retry_after_recorded": True, "until": block.until,
            "source": block.source or "auth_backoff",
            "consecutive": block.consecutive}


def _daemon_429_record():
    """The daemon's own 429 status line, or None. This is the only place Retry-After survives."""
    try:
        d = json.loads((ST / "auth_status.json").read_text())
    except Exception:
        return None
    return d if d.get("code") == 429 and d.get("ts") is not None else None


def _wall_from_mint_wall(now):
    """The daemon's restart-surviving wall. Carries the CLASS in `why`, but no Retry-After."""
    try:
        d = json.loads(MINT_WALL.read_text())
    except Exception:
        return None
    until = d.get("until")
    if until is None or float(until) <= now:
        return None
    rec = _daemon_429_record()
    return {"cls": d.get("why") or "UNRECORDED",
            "retry_after": rec.get("retry_after") if rec else None,
            "retry_after_recorded": rec is not None,
            "until": float(until), "source": "auth-daemon", "consecutive": 0}


def _wall_from_status_file(now):
    """The daemon's status line alone. Retry-After is recorded here; the body never is."""
    d = _daemon_429_record()
    if d is None or d.get("backoff_s") is None:
        return None
    until = float(d["ts"]) + float(d["backoff_s"])
    if until <= now:
        return None
    return {"cls": "UNRECORDED", "retry_after": d.get("retry_after"),
            "retry_after_recorded": True, "until": until,
            "source": "auth-daemon", "consecutive": 0}


def auth_wall(now=None):
    """The live /authentication wall, or None. Never guesses a class it was not given.

    `until` may be None (a corrupt backoff record blocks with no expiry at all), so every consumer
    must handle a wall that has no time on it -- which is the honest shape of most of these walls.
    """
    now = time.time() if now is None else float(now)
    w = (_wall_from_backoff_file(now) or _wall_from_mint_wall(now)
         or _wall_from_status_file(now))
    if w is None:
        return None
    # A server-stated expiry requires BOTH that the writer kept the header AND that it was there.
    w["expiry_is_server_stated"] = w["retry_after_recorded"] and w["retry_after"] is not None
    w["remaining_s"] = None if w["until"] is None else w["until"] - now
    return w


def wall_line(w):
    """One line naming the class, the origin of the expiry, and whether Retry-After was present."""
    if w is None:
        return "**auth wall** none — /authentication is not refusing"
    cls = w["cls"] if w["cls"] != "UNRECORDED" else "UNRECORDED (the daemon does not keep the body)"
    streak = f" · {w['consecutive']} refusals in a row" if w["consecutive"] > 1 else ""
    if w["until"] is None:
        return f"**auth wall** {cls} · **no expiry recorded at all** — treat as up until proven off"
    when = time.strftime("%H:%M:%S", time.localtime(w["until"]))
    mins = w["remaining_s"] / 60
    if w["expiry_is_server_stated"]:
        return (f"**auth wall** {cls} · Retry-After PRESENT ({w['retry_after']}s) → "
                f"lifts {when}, {mins:.1f}m — a **server-stated** expiry{streak}")
    ra = "Retry-After ABSENT" if w["retry_after_recorded"] else "Retry-After NOT RECORDED"
    return (f"**auth wall** {cls} · {ra} → **expiry UNKNOWN**; "
            f"{when} ({mins:.0f}m) is only our own next retry, not a lift{streak}")


def link_age_s(now=None):
    """Age of the armed persona link, from whichever file this box writes."""
    now = time.time() if now is None else float(now)
    ages = []
    for name in ("persona_url.txt", "auth_link.txt"):
        try:
            ages.append(now - (ST / name).stat().st_mtime)
        except OSError:
            pass
    return min(ages) if ages else None


def operator_line(now=None):
    """THE ONE LINE FOR A PHONE. Exactly three outcomes, and they must not blur together."""
    now = time.time() if now is None else float(now)
    w = auth_wall(now)
    if w is not None:
        if w["until"] is None:
            return f"⛔ WAIT — {w['cls']} wall, no expiry recorded at all. Nothing to tap."
        when = time.strftime("%H:%M", time.localtime(w["until"]))
        if w["expiry_is_server_stated"]:
            return f"⏳ WAIT — {w['cls']} wall, lifts {when} (server said so). Nothing to tap."
        return (f"⛔ WAIT — {w['cls']} wall, no known expiry. Next retry {when}; that is a "
                f"guess, not a lift. Nothing to tap.")
    stage, _ = auth_state()
    if stage == "AUTHED":
        return "✅ AUTHED — nothing to do."
    age = link_age_s(now)
    if age is None:
        return "⚠️ no link armed and no wall up — the auth flow is not running."
    if age <= LINK_LIVE_S:
        return f"👉 TAP NOW — a link is live ({age / 60:.0f}m old)."
    return (f"⚠️ the armed link is {age / 60:.0f}m old (windows last ~{LINK_LIVE_S / 60:.0f}m) — "
            "tapping it will do nothing; mint a fresh one.")


#: Every journal a run may write to. `resim_results.jsonl` is the OLD funnel's; massgen runs write
#: under `state/harness13/<run>/journal.jsonl` and nothing here knew that.
#: Journals are found by SHAPE, not by NAME. The name list was `("resim_results.jsonl",
#: "harness13/**/journal.jsonl", "**/journal.jsonl")` and it broke twice in one day: first it was a
#: single hardcoded path and reported "🔴 pipeline NOT producing" while a run wrote 18 rows a minute
#: elsewhere; then it was widened to those globs, and the very next runner wrote `loop_*.jsonl`,
#: which matches none of them -- so it reported a 77-minute-old journal while the live one was 0
#: minutes old. A name list is a promise that every future writer will be told about it, and that
#: promise has now failed twice. A journal is any .jsonl under state/ whose last line carries a
#: simulation `status`; that is a property of the file, and a new runner cannot forget to have it.
_JOURNAL_STATUSES = ("COMPLETE", "WARNING", "ERROR", "AUTH-FAIL", "FAIL")


def freshest_journal():
    """(path, age_minutes) of the most recently written journal, or (None, None).

    WHY IT IS A SEARCH AND NOT A CONSTANT. This function read `resim_results.jsonl` and nothing
    else, so on 2026-08-13 it reported `journal 2316m old` and the report printed
    "🔴 pipeline NOT producing" while a run was writing 18 rows a minute into
    `state/harness13/sim_ceiling2/journal.jsonl` with 19 of 19 POSTs answering 201. The pipeline was
    healthy; the instrument was pointed at a file that had been dead for 38 hours.

    That is this project's dominant defect class -- a transient or moved condition read as a
    permanent fact -- and a health check is the worst place for it, because the one reader who would
    catch it is the person being told not to bother looking.
    """
    best = None
    for f in ST.glob("**/*.jsonl"):
        if not f.is_file():
            continue
        try:
            m = f.stat().st_mtime
            if best is not None and m <= best[1]:
                continue                       # cheaper than reading it
            with open(f, "rb") as fh:
                fh.seek(0, 2)
                fh.seek(max(0, fh.tell() - 4096))
                tail = fh.read().decode("utf-8", "ignore")
        except OSError:
            continue
        if not any('"%s"' % st in tail for st in _JOURNAL_STATUSES):
            continue
        best = (f, m)
    if best is None:
        return None, None
    return best[0], int((time.time() - best[1]) / 60)


def journal_age_min():
    return freshest_journal()[1]


def screen():
    """measured / passed / never-measured — the split that was being collapsed."""
    try:
        d = json.loads((ST / "pnl_screen.json").read_text())
    except Exception:
        return None
    ev = {a: v for a, v in d.items() if isinstance(v.get("pnl_sharpe"), (int, float))}
    ok = sum(1 for v in ev.values() if v.get("screen_ok"))
    return {"measured": len(ev), "passed": ok, "never_measured": len(d) - len(ev),
            "rate": round(ok / len(ev), 3) if ev else None}


def cells_short():
    try:
        d = json.loads((ST / "pyramid_cell_counts.json").read_text())
        pairs = d.get("pairs") or [d]
        usa = next((p for p in pairs if p.get("region") == "USA" and p.get("delay") == 1), None)
        if not usa:
            return None
        short = {k: v for k, v in usa["counts"].items() if v < 3}
        return {"short": short, "alphas_needed": sum(3 - v for v in short.values())}
    except Exception:
        return None


def api_errors():
    pat = {"401": 0, "429": 0, "5xx": 0}
    for line in _tail("simq_events.log", 400) + _tail("simfeed.log", 400):
        if "auth=401" in line or "auth= " in line:
            pat["401"] += 1
        if "429" in line:
            pat["429"] += 1
        if re.search(r"\b5\d\d\b", line):
            pat["5xx"] += 1
    return pat


def running():
    d = ST / "simrunning"
    q = ST / "simqueue"
    return {"running": [p.name for p in d.glob("*.json")] if d.is_dir() else [],
            "queued": len(list(q.glob("*.json"))) if q.is_dir() else 0}


def build():
    total, dn, per_min = sim_rate()
    stage, auth_age = auth_state()
    ja = journal_age_min()
    sc = screen()
    ce = cells_short()
    err = api_errors()
    run = running()
    host = subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()

    # Judge on the journal clock, not on the rate: the rate is None on the first run after a boot
    # and treating "not yet measurable" as "broken" is the same absent-means-failed error that made
    # the screen report 7.3% instead of 15.0%.
    wall = auth_wall()
    healthy = (stage in ("AUTHED", "AUTHED_PENDING_SAVE") and ja is not None and ja < 20
               and wall is None)
    head = ("🟢 pipeline healthy" if healthy else "🔴 pipeline NOT producing")
    rate = (f"**{per_min}/min** ({dn} new since the last report)" if per_min is not None
            else "not measurable yet — first report since restart")
    L = [f"**{head}**  ·  `{host}`",
         operator_line(),
         f"**sims** {rate}  ·  {total} rows total",
         f"**auth** {stage}" + (f", {auth_age}m since last change" if auth_age is not None else ""),
         wall_line(wall),
         f"**journal** {ja}m old" if ja is not None else "**journal** missing",
         f"**pools** running={run['running'] or 'none'} queued={run['queued']}"]
    if sc:
        L.append(f"**screen** {sc['passed']}/{sc['measured']} measured = "
                 f"{(sc['rate'] or 0) * 100:.0f}%  ·  {sc['never_measured']} never measured "
                 f"(not failures)")
    if ce:
        L.append(f"**cells short** {ce['short']}  → {ce['alphas_needed']} alphas to unlock all")
    L.append(f"**api errors ({WINDOW_MIN}m window)** 401={err['401']} 429={err['429']} 5xx={err['5xx']}")
    # EVERY REPORT NAMES THE BEST ALPHA WE HOLD (Khoa, 2026-08-14). A status line says how the
    # machine is doing; it does not say what the machine has produced, and those are different
    # questions. Wrapped because a report that fails to send because the lookup broke is worse than
    # a report without the block.
    try:
        import climb as _climb
        L.append("")
        L.append(_climb.best_line())
    except Exception as exc:                       # noqa: BLE001 - the report must still go out
        L.append(f"best alpha: unavailable ({type(exc).__name__})")
    return "\n".join(L), healthy


def main(argv):
    if "--operator" in argv:
        print(operator_line())
        return 0
    text, healthy = build()
    if "--print" in argv:
        print(text)
        return 0
    # THE POST IS GONE.  THE TIMER AND THE SENSOR ARE NOT.
    #
    # This one timer accounted for 142 of the ~199 messages a day -- 36 of them delivered inside a
    # six-hour outage, every one of them saying nothing about the loop that was down.  So the
    # verdict is deleted from the channel and the beat is kept: the unit keeps firing every ten
    # minutes, this function keeps computing, and the result lands on disk where the dead-man timer
    # and the operator digest read it.
    #
    # A verdict is deleted; a beat is not.  Deleting the beat as well would have made a dead
    # notifier indistinguishable from a healthy system for up to a day.
    import json
    import time as _time
    out = {
        "at": _time.time(),
        "healthy": bool(healthy),
        "text": text,
        "source": "tools/health_report.py",
    }
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "state", "notify", "health_report.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(out, fh, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    if "--quiet" not in argv:
        print(text)
    # AN EXIT CODE ANSWERS "did this program run correctly", NOT "is the news good".
    #
    # Returning 1 for an unhealthy pipeline made systemd mark this unit FAILED, which the dead-man
    # switch then reported as a failed unit -- and the dead-man's own non-zero exit made IT a
    # failed unit too, so the next run reported itself. A verdict smuggled into an exit code turned
    # both reporters into alarms about themselves.
    #
    # The verdict lives in state/notify/health_report.json, where the readers look for it.
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
