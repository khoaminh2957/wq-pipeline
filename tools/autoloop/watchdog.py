#!/usr/bin/env python3
"""watchdog.py --pid <pid> --deadline-hours 4 — supervises an unattended driver.py run.

Every line on stdout becomes an operator notification, so stdout carries EVENTS ONLY -- things a
human would act on. Routine polling, and every exception this loop swallows, go to stderr. A
watchdog that dies is worse than no watchdog, so nothing inside the loop is allowed to propagate.

Events: DRIVER_DEAD / RESTART_OK / RESTART_FAILED / STALL / AUTH_NEEDED / WINNER / DEADLINE_REACHED
"""
from __future__ import annotations
import argparse, csv, os, pathlib, re, shlex, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
ST = ROOT / "state"
JOURNAL = ST / "resim_results.jsonl"
WINNERS = ST / "funnel/winners.csv"
PERSONA = ST / "persona_url.txt"
STALL_MIN = 25.0
AUTH_RE = re.compile(r"\b401\b|AUTH: 401|Unauthorized", re.I)


def emit(line):
    print(line, flush=True)


def note(line):
    print(f"[{time.strftime('%H:%M:%S')}] {line}", file=sys.stderr, flush=True)


def read_argv(pid):
    """Capture the driver's argv WHILE IT IS ALIVE -- after it dies there is nothing left to read."""
    proc = pathlib.Path(f"/proc/{pid}/cmdline")
    if proc.exists():                                    # linux: exact argv, NUL separated
        return [a for a in proc.read_bytes().decode().split("\0") if a]
    r = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True)
    cmd = (r.stdout or "").strip()
    return shlex.split(cmd) if cmd else []


def alive(pid, child):
    if child is not None:
        return child.poll() is None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def winner_rows():
    out = {}
    if not WINNERS.exists():
        return out
    for r in csv.DictReader(open(WINNERS)):
        if r.get("alpha"):
            out[r["alpha"]] = r.get("prod_max") or "?"
    return out


def safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:
        note(f"{getattr(fn, '__name__', fn)} raised {type(e).__name__}: {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--deadline-hours", type=float, required=True)
    ap.add_argument("--log", default=str(ST / "autoloop/driver.log"),
                    help="driver stdout log, scanned for auth failures")
    ap.add_argument("--interval", type=int, default=20)
    a = ap.parse_args()

    t0 = time.time()
    deadline = t0 + a.deadline_hours * 3600
    pid, child, restarts_left = a.pid, None, 1
    argv = safe(read_argv, a.pid) or []
    log = pathlib.Path(a.log)
    offset = log.stat().st_size if log.exists() else 0
    jsize = JOURNAL.stat().st_size if JOURNAL.exists() else 0
    # Baseline the stall clock at launch, not at the journal's mtime: a driver that has not simmed
    # yet inherits a cold file and would trip STALL before it had a chance to write anything.
    last_append, stalled = time.time(), False
    seen = safe(winner_rows) or {}

    emit(f"WATCHING pid={pid} deadline={a.deadline_hours}h "
         f"restart_argv={'ok' if argv else 'UNAVAILABLE -- no restart possible'}")

    while True:
        try:
            now = time.time()
            if now >= deadline:
                emit("DEADLINE_REACHED")
                return 0

            # --- process liveness (checked first: everything else is diagnostics) -------------
            if not alive(pid, child):
                info = (f"exit={child.returncode}" if child is not None
                        else "no exit status (not a child of the watchdog)")
                emit(f"DRIVER_DEAD pid={pid} {info} after {(now - t0) / 60:.0f} min, "
                     f"{(deadline - now) / 60:.0f} min left on the deadline")
                if not restarts_left:
                    emit("RESTART_FAILED one restart already used -- driver is down, run is over")
                    return 1
                if not argv:
                    emit("RESTART_FAILED argv was never readable -- driver is down, run is over")
                    return 1
                # A driver that was DELIBERATELY replaced must not be resurrected. This watchdog
                # only knows its own pid died, not why -- so when an operator stops a run and
                # starts a different one, it dutifully relaunches the superseded pool and two
                # drivers then contend for the resim lock. That happened on 2026-07-30 (25 minutes
                # of contention) and again on 2026-08-02 at 12:25, ten seconds after the pool was
                # switched to pool_paircell. If any other driver is alive, this run is over.
                try:
                    others = subprocess.run(["pgrep", "-f", "autoloop/driver.py"],
                                            capture_output=True, text=True).stdout.split()
                    others = [int(x) for x in others if int(x) != pid]
                except Exception:
                    others = []
                if others:
                    emit(f"SUPERSEDED another driver is already running {others} -- "
                         f"not resurrecting this one, watchdog exiting")
                    return 0
                restarts_left -= 1
                # Relaunch with the time that is LEFT, not the window the run started with. argv
                # is captured verbatim, so a driver that died five hours into a 9.5h run was
                # restarted with `--hours 9.5` and ran until nearly five hours past the deadline
                # this watchdog exists to enforce -- unattended, and on a submitting run that
                # reaches into the next day's quota.
                relaunch = list(argv)
                try:
                    hi = relaunch.index("--hours")
                    left_h = max(0.05, (deadline - time.time()) / 3600)
                    relaunch[hi + 1] = f"{left_h:.2f}"
                    emit(f"RESTART re-scoping --hours {argv[hi + 1]} -> {left_h:.2f} (deadline)")
                except (ValueError, IndexError):
                    pass                                 # no --hours to rewrite; run as captured
                try:
                    log.parent.mkdir(parents=True, exist_ok=True)
                    lf = open(log, "a")
                    child = subprocess.Popen(relaunch, cwd=str(ROOT), stdout=lf,
                                             stderr=subprocess.STDOUT)
                    pid = child.pid
                    time.sleep(5)                        # long enough to catch an instant failure
                    if child.poll() is None:
                        emit(f"RESTART_OK new pid={pid} argv={' '.join(argv)}")
                    else:
                        emit(f"RESTART_FAILED relaunch exited immediately rc={child.returncode}")
                        return 1
                except Exception as e:
                    emit(f"RESTART_FAILED {type(e).__name__}: {e}")
                    return 1

            # --- journal stall ---------------------------------------------------------------
            def _stall():
                nonlocal jsize, last_append, stalled
                size = JOURNAL.stat().st_size if JOURNAL.exists() else 0
                if size != jsize:
                    jsize, last_append, stalled = size, time.time(), False
                    return
                mins = (time.time() - last_append) / 60
                if mins > STALL_MIN and not stalled:
                    stalled = True
                    emit(f"STALL {mins:.0f} minutes with no new row in state/resim_results.jsonl")
            safe(_stall)

            # --- auth failure in the driver log ----------------------------------------------
            def _auth():
                nonlocal offset
                if not log.exists():
                    return
                size = log.stat().st_size
                if size < offset:                        # log rotated/truncated
                    offset = 0
                if size == offset:
                    return
                with open(log, "rb") as f:
                    f.seek(offset)
                    chunk = f.read().decode("utf-8", "replace")
                offset = size
                if AUTH_RE.search(chunk):
                    url = PERSONA.read_text().strip() if PERSONA.exists() else "state/persona_url.txt missing"
                    emit(f"AUTH_NEEDED {url}")
            safe(_auth)

            # --- new winners -----------------------------------------------------------------
            def _winners():
                nonlocal seen
                cur = winner_rows()
                for aid in [k for k in cur if k not in seen]:
                    emit(f"WINNER {aid} prod_max={cur[aid]}")
                if cur:
                    seen = cur
            safe(_winners)

        except Exception as e:                            # belt and braces -- never exit the loop
            note(f"loop iteration raised {type(e).__name__}: {e}")
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
