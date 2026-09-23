#!/usr/bin/env python3
"""The liveness checker.  Runs on a 60 s timer OUTSIDE the loop it watches.

It must run outside, because a watchdog inside the process it supervises cannot report that
process dying -- the same circularity that let an auth unit crash-loop 44 times on a syntax error
inside its own notification string, reporting nothing, because the thing that would have reported
it was the thing that was broken.

DEBOUNCE, AND WHY IT IS TICKS AND NOT AN AGE
-------------------------------------------
No scalar age threshold can work here, and that is a measured result rather than a preference.
Over 149 measured gaps, the longest silence from a HEALTHY loop (excluding its declared quota
sleep) was 67.0 minutes, while the shortest interval in which the loop was genuinely DEAD was
about 26 minutes.  The two populations overlap, so every threshold either raises false alarms or
misses a real death.  A 25-minute threshold, tried on the record, produced false DOWN/UP pairs
because the loop's natural period is ~31.5 minutes.

So DOWN is decided by the LOCK, never by an age, and the debounce is two consecutive ticks of the
same verdict -- which costs at most 60 extra seconds and removes the single-sample race entirely.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loopstate as LS  # noqa: E402
import msgcat as MC     # noqa: E402
import outbox as OB     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# One writer only: the box that runs the loop.  Two unsynchronised writers lose last_notified,
# whose entire job is suppressing repeats.
WATCH = os.path.join(ROOT, "state", "loop", "watch.json")
DEBOUNCE_TICKS = 2
#: RECOVERY IS CONFIRMED SLOWER THAN DEATH. While auth is dead the loop restarts every ~5 minutes
#: and holds its flock for the ~1-2 minute auth-check, so the classifier sees a short RUNNING
#: window on many restarts. With a symmetric debounce of 2 that window kept CONFIRMING a recovery
#: that had not happened: 117 DEAD / 59 RUNNING verdicts and 16 m3 messages in one day of a
#: constant outage (measured 2026-08-28) -- the "one message per outage" rule broken by flapping.
#: A real recovery holds RUNNING for a whole round (median 7 min), so it clears 5 ticks easily;
#: the auth-check flap (<=2 min) never does. Death still confirms at 2 ticks -- fast to alarm,
#: slow to all-clear.
DEBOUNCE_TICKS_UP = 5

# The supervised set.  A thing nobody would notice stopping is either watched or deliberately
# abandoned; watching everything reproduces the 142-messages-a-day noise that made the previous
# system unreadable, so each entry is here for a stated reason.
# wq-climb.service is FIRST because it is the one unit that keeps mining alive, and it was missing
# from this list for the whole evening -- the watchdog watched four units and not the miner's own
# supervisor. wq-outbox is here for the same reason: if the sender dies, every other alarm in this
# file goes nowhere.
UNITS = ("wq-climb.service", "wq-harvest.service", "wq-outbox.service", "wq-auth.service",
         "wq-cycle.service", "wq-health.service", "wq-loop.service")


def _read(path, default=None):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default if default is not None else {}


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def unit_state(unit):
    """Exit RECORDS, not the restart counter.

    The restart counter is not a usable trigger: an auth unit crash-looped 44 times in 14 minutes
    and its NRestarts reads 0 today.
    """
    try:
        out = subprocess.run(
            ["systemctl", "show", unit, "--property=ActiveState,SubState,Result,ExecMainStatus,"
             "ExecMainExitTimestamp,NRestarts"],
            capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    d = {}
    for line in out.stdout.splitlines():
        k, _, v = line.partition("=")
        d[k] = v
    return d


def best_now():
    """Never let a lookup failure suppress the alarm the message exists to carry."""
    try:
        import climb  # noqa: PLC0415
        b, _ = climb.best_alpha("sub_sharpe")
        return b
    except Exception:                              # noqa: BLE001
        return None


def tick(now=None, state=None, emit=True):
    now = now if now is not None else time.time()
    st = state if state is not None else _read(WATCH, {})
    verdict, facts = LS.classify(now=now)

    pending = st.get("pending_state")
    ticks = st.get("pending_ticks", 0)
    if verdict == pending:
        ticks += 1
    else:
        pending, ticks = verdict, 1

    confirmed = st.get("confirmed_state")
    out = {"verdict": verdict, "facts": facts, "fired": None}

    need = DEBOUNCE_TICKS_UP if verdict == LS.RUNNING else DEBOUNCE_TICKS
    if ticks >= need and verdict != confirmed:
        # "transition" is not "message". A cold start into RUNNING is a transition that says
        # nothing, and a label that reports it as a send is exactly the kind of overstatement this
        # rebuild exists to remove.
        out["transition"] = (confirmed, verdict)
        out["sent"] = _fire(verdict, confirmed, facts, now) if emit else None
        confirmed = verdict

    st.update({"at": now, "pending_state": pending, "pending_ticks": ticks,
               "confirmed_state": confirmed, "last_facts": facts})
    if state is None:
        _write(WATCH, st)
    out["state"] = st
    return out


def _fire(verdict, previous, facts, now):
    """Returns the msg_id actually enqueued, or None when the transition warrants no message."""
    if verdict == LS.RUNNING:
        if previous not in (None, LS.RUNNING):
            return MC.send(MC.m3_up(previous, now, best=best_now()))
        return None                                # a cold start into RUNNING is not news
    if verdict == LS.UNSUPPORTED:
        return None                                # this box runs no loop; nothing to report
    return MC.send(MC.m3_down(
        verdict, facts.get("lock", "?"), now,
        phase=facts.get("phase"),
        complete_rows=facts.get("complete_rows"),
        # A REAL COMMAND, NOT A PLACEHOLDER.
        #
        # This rendered the literal string "<start command>". The DOWN alert IS the recovery
        # mechanism when there is no actuator, so a placeholder inside it is a first-order defect,
        # not a cosmetic one -- and the loop lay dead 8h07m after an alert that told nobody what to
        # type. There is an actuator now (wq-climb.service, Restart=always/300s), so the message
        # says what will happen by itself and what to type to skip the wait.
        remedy="Tự chạy lại trong <=5 phút (wq-climb.service). Muốn ngay: "
               "systemctl start wq-climb",
        best=best_now()))


def units_tick(state=None, emit=True):
    """M9.  The probe for a unit is run by this process, whose own unit is not any of them."""
    st = state if state is not None else _read(WATCH, {})
    seen = st.setdefault("units", {})
    fired = []
    for u in UNITS:
        d = unit_state(u)
        if d is None:
            continue
        # KEY ON THE OUTCOME, NOT ON THE ACTIVITY CYCLE.
        #
        # This used to key on ActiveState/SubState, so a oneshot on a timer -- which necessarily
        # goes active then inactive on every single firing -- looked like a state change every
        # time. Measured: 13 messages about a healthy 10-minute health unit, and 26 unit messages
        # in total against ONE real event. That is the 142-a-day disease growing back under a new
        # name, and the rebuild is worthless if I let it.
        #
        # A completed oneshot and a running service are both "fine"; what the operator needs is
        # the transition into and out of NOT-fine.
        failed = (d.get("ActiveState") == "failed"
                  or (d.get("Result") or "success") != "success")
        key = "failed(%s/%s)" % (d.get("Result"), d.get("ExecMainStatus")) if failed else "ok"
        prev = seen.get(u, {}).get("key")
        if prev is not None and key != prev:
            fired.append(u)
            if emit:
                MC.send(MC.m9_member_changed(
                    u, prev, key, seen.get(u, {}).get("NRestarts"), d.get("NRestarts"),
                    d.get("ExecMainExitTimestamp") or "chưa ghi", d.get("ExecMainStatus")))
        seen[u] = {"key": key, "NRestarts": d.get("NRestarts")}
    if state is None:
        _write(WATCH, st)
    return fired


#: Ladder events worth a message. A round-by-round `progress` is noise; these three are the only
#: transitions that change where the phase stands.
LADDER_EVENTS = ("cycle-advanced", "cycle-retry", "phase-reset")

#: Warn this far ahead of the session's death. The session lives exactly 4h and cannot be renewed,
#: so the warning is scheduled off the JWT `exp`, never off a 401.
AUTH_WARN_MIN = 25


def climb_tick(state=None, emit=True):
    """M7 / M10 / M11 -- the three things Khoa asked to be told about on 2026-08-18.

    All three are EDGE-triggered against a cursor held in the watchdog's own state. The failure this
    avoids is the one that produced 262 "auth het han" messages against 8 actual links: a condition
    that is true for hours must be reported when it BECOMES true, not on every tick that observes
    it still being true.
    """
    st = state if state is not None else _read(WATCH, {})
    fired = []

    # --- M7: the benchmark ladder moved -------------------------------------------------
    try:
        climb_state = json.loads(open(os.path.join(ROOT, "state", "climb", "state.json")).read())
    except (OSError, ValueError):
        climb_state = {}
    hist = climb_state.get("history") or []
    cur = st.get("climb_hist_cursor", 0)
    if cur > len(hist):
        # The history was truncated under us; re-anchor rather than replay the whole thing.
        if emit:
            MC.send(MC.m7_history_truncated(cur, len(hist)))
        cur = len(hist)
    for h in hist[cur:]:
        if h.get("event") in LADDER_EVENTS:
            fired.append(h["event"])
            if emit:
                MC.send(MC.m7_cycle(h.get("event"), h.get("cycle"), h.get("round"), h.get("kind"),
                                    h.get("n"), h.get("best_score"), h.get("prev_baseline_score"),
                                    h.get("screened"), h.get("tier3"), best=best_now()))
    st["climb_hist_cursor"] = len(hist)

    # --- M10: gem candidates appeared ----------------------------------------------------
    # Read off the history the loop already writes, so this cannot disagree with what the loop
    # counted. A candidate is tier 3 -- through the screen, not yet measured.
    total = sum(int(h.get("tier3") or 0) for h in hist)
    prev_total = st.get("climb_tier3_total", 0)
    if total > prev_total:
        fired.append("gem-candidate")
        if emit:
            MC.send(MC.m10_gem_candidate(total - prev_total, total, best=best_now()))
    st["climb_tier3_total"] = total

    # --- M11: the session is about to die ------------------------------------------------
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import mint_link as ML
        left = ML.session_left_s()
    except Exception:                              # noqa: BLE001
        # INSTRUMENTED, never silent. A bare pass here is how a missing import hid
        # for days in this repository.
        left = None
        print("climb_tick: khong doc duoc han phien", file=sys.stderr)
    if isinstance(left, (int, float)):
        mins = int(left // 60)
        # ONE WARNING PER SESSION, keyed on the JWT's own expiry instant -- which is constant for
        # the session's whole life -- not on the minutes-left bucket. The bucket version fired
        # THREE times per expiry (25' -> 18' -> 8' cross three //10 buckets; measured quadruples
        # of triples in sent.jsonl, 08-18..08-23). //300 gives a 5-minute tolerance so clock skew
        # between ticks cannot mint a second key for the same session.
        exp_key = int((time.time() + left) // 300)
        if 0 < mins <= AUTH_WARN_MIN and st.get("auth_warned_for") != exp_key:
            fired.append("auth-expiring")
            if emit:
                url = None
                try:
                    url = ML.live_link()
                except Exception:
                    pass
                MC.send(MC.m11_auth_expiring(mins, url))
            st["auth_warned_for"] = exp_key

    if state is None:
        _write(WATCH, st)
    return fired


def main(argv):
    dry = "--dry-run" in argv
    r = tick(emit=not dry)
    note = ""
    if r.get("transition"):
        old, new = r["transition"]
        note = "  [%s -> %s, %s]" % (old, new,
                                     "queued %s" % r["sent"] if r.get("sent") else "no message")
    print("%s%s" % (r["verdict"], note))
    for k in sorted(r["facts"]):
        print("  %-14s %s" % (k, r["facts"][k]))
    if "--units" in argv:
        print("unit changes:", units_tick(emit=not dry) or "none")
    print("climb events:", climb_tick(emit=not dry) or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
