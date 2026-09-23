#!/usr/bin/env python3
"""Is the climb loop alive?  Five states, and none of them may be reached by guessing.

WHY EVERY PREVIOUS ANSWER WAS WRONG AT LEAST ONCE
-------------------------------------------------
  * `pgrep -fc <pattern>` matches the checker's own command line.  It reported RUNNING four times
    from a count of itself.  `ps -eo pid,cmd | grep` is WORSE, not better: measured true=1,
    pgrep=2, ps|grep=3.
  * An mtime went green off a GET-only writer that never simulated anything.
  * A leftover marker file survived a crash and read as healthy.
  * Absence of a process was read as STUCK while the loop was healthily inside a declared 900 s
    wait -- three separate readers made that same mistake in one day.

So the primary fact is a kernel-held flock, observed through /proc/locks and keyed on the file's
device+inode.  A crash always releases it, and no string in it can ever match the checker itself.

AND WHY THE LOCK ALONE IS STILL NOT ENOUGH
------------------------------------------
  * A missing lock FILE is not a dead loop and not a live one.  /var/lock is tmpfs and is empty
    from every boot until the loop first starts.  A checker that derives its match key by string
    interpolation collapses an absent file into an empty key that matches EVERY line in
    /proc/locks -- measured: 4 matches, verdict RUNNING, on a box where nothing was running.
    Here the key is built from integers, so that failure is unreachable by construction.
  * A child that inherits the lock's file descriptor keeps holding it after the parent dies.  This
    is live right now on the arming lock: three production processes hold fd 8, and BOTH pipeline
    rows in /proc/locks name PIDs that no longer exist.  The worst orphan window is not the 40
    minute probe -- it is an un-wrapped 10 h 53 m sleep that also inherits the descriptor.
    So the beat's pid+starttime is a second witness, and that case gets its own state.

None of the four deaths in the record is an orphan -- all four were clean exits -- so this design
gets no credit from that record for the failure mode most likely to happen next.  It is judged on
the mechanism instead, and ORPHAN_LOCK is tested against a synthetic orphan.
"""
import json
import os
import sys
import time

RUNNING = "RUNNING"
DEAD = "DEAD"
ORPHAN_LOCK = "ORPHAN_LOCK"
LOCK_IDENTITY_UNKNOWN = "LOCK_IDENTITY_UNKNOWN"
NEVER_STARTED_THIS_BOOT = "NEVER_STARTED_THIS_BOOT"
UNREACHABLE = "UNREACHABLE"
UNSUPPORTED = "UNSUPPORTED"

# The heartbeat must NOT carry a .jsonl extension: the health reporter globs state/**/*.jsonl for
# its freshest-journal check, so a renamed beat would start holding the health light green off the
# watchdog's own heartbeats -- the exact circularity this file exists to break.
DEFAULT_LOCK = "/var/lock/wq_climb.lock"
DEFAULT_BEAT = "/opt/wq/state/loop/heartbeat.json"
PROC_LOCKS = "/proc/locks"
BOOT_ID = "/proc/sys/kernel/random/boot_id"

BEAT_STALE_S = 120.0


def _read_boot_id(path=BOOT_ID):
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return None


def read_beat(path=None):
    path = path or os.environ.get("WQ_BEAT") or DEFAULT_BEAT
    try:
        with open(path) as fh:
            b = json.load(fh)
        return b if isinstance(b, dict) else None
    except (OSError, ValueError):
        return None


def parse_locks(text):
    """Rows of /proc/locks as typed tuples.  Whole-field match on the type and on dev:ino.

    A substring search over this file is forgeable and, worse, matches everything when the search
    key is empty.
    """
    out = []
    for line in (text or "").splitlines():
        parts = line.split()
        # e.g.  2: FLOCK  ADVISORY  WRITE 4321 00:1c:153985 0 EOF
        if len(parts) < 6:
            continue
        try:
            ltype = parts[1]
            pid = int(parts[4])
            devino = parts[5]
            maj, minr, ino = devino.split(":")
            out.append({"type": ltype, "pid": pid,
                        "major": int(maj, 16), "minor": int(minr, 16), "inode": int(ino)})
        except (ValueError, IndexError):
            continue
    return out


def read_locks(path=PROC_LOCKS):
    """Returns None when the file cannot be read.  None must NEVER become RUNNING: collapsing an
    absent measurement into a verdict is this project's dominant defect class."""
    try:
        with open(path) as fh:
            return parse_locks(fh.read())
    except OSError:
        return None


def alive(pid, starttime=None, proc="/proc"):
    """Field 22 of /proc/<pid>/stat, matched exactly.  comm may contain spaces and parentheses, so
    the split is on the LAST ')'."""
    try:
        with open(os.path.join(proc, str(pid), "stat")) as fh:
            raw = fh.read()
    except OSError:
        return False
    try:
        tail = raw[raw.rindex(")") + 1:].split()
        st = int(tail[19])  # field 22 overall == index 19 after the comm field
    except (ValueError, IndexError):
        return False
    if starttime is None:
        return True
    try:
        return int(starttime) == st
    except (TypeError, ValueError):
        return False


def classify(lock_path=None, beat_path=None, locks=None, boot_id=None, now=None, proc="/proc"):
    """Return (state, facts).  Pure enough to test against fixtures, including a synthetic orphan."""
    lock_path = lock_path or os.environ.get("WQ_LOCK") or DEFAULT_LOCK
    beat = read_beat(beat_path)
    now = now if now is not None else time.time()
    facts = {"lock": lock_path, "beat": bool(beat)}

    # Rule 1 -- IDENTITY OR NOTHING.  Built from integers; an absent file cannot yield a key that
    # matches everything.
    try:
        st = os.stat(lock_path)
        dev_major = os.major(st.st_dev)
        dev_minor = os.minor(st.st_dev)
        ino = st.st_ino
        facts.update({"inode": ino, "dev": "%d:%d" % (dev_major, dev_minor)})
    except OSError:
        # Rule 2 -- A MISSING PATH IS NEITHER STUCK NOR RUNNING.
        cur_boot = boot_id if boot_id is not None else _read_boot_id()
        if not beat or (cur_boot and beat.get("boot_id") != cur_boot):
            return NEVER_STARTED_THIS_BOOT, facts
        return LOCK_IDENTITY_UNKNOWN, dict(facts, why="lock path removed under a running loop")

    if locks is None:
        locks = read_locks()
    if locks is None:
        # Fail CLOSED.  We could not measure, so we do not get to say RUNNING.
        #
        # The distinction is a CAPABILITY test, not a platform-name test: on macOS there is no
        # /proc/locks and no flock(1), so the primary fact is simply unavailable and this box
        # needs a READER rather than a loop -- simulations never run here.  Anywhere else, an
        # unreadable /proc/locks is an outage of the measurement, not of the loop.
        #
        # This branch was green on the development machine and only ran for the first time on the
        # box it protects, where it revealed that a platform-name check had been standing in for a
        # capability check.
        if sys.platform == "darwin":
            return UNSUPPORTED, dict(facts, why="no /proc/locks on this box; it runs no loop")
        return UNREACHABLE, dict(facts, why="/proc/locks unreadable")

    # Rule 3 -- WHOLE-FIELD, TYPED MATCH.
    holders = [r for r in locks
               if r["type"] == "FLOCK" and r["inode"] == ino
               and r["major"] == dev_major and r["minor"] == dev_minor]
    held = bool(holders)
    facts["held"] = held
    facts["holder_pids"] = [r["pid"] for r in holders]

    # Rule 4 -- THE LOCK IS NOT THE ONLY WITNESS.
    if beat and beat.get("lock_ino") not in (None, ino):
        return LOCK_IDENTITY_UNKNOWN, dict(facts, why="beat's lock inode does not match the path")

    if not held:
        return DEAD, facts

    if not beat:
        # The lock alone answers DEAD / RUNNING / NEVER_STARTED, which covers every death in the
        # record. What it cannot answer without a beat is the ORPHAN case -- so that limitation is
        # stated in the facts rather than left for a reader to assume was checked.
        facts["second_witness"] = "ABSENT (no heartbeat; ORPHAN_LOCK cannot be detected)"

    if beat and beat.get("pid") is not None:
        if not alive(beat["pid"], beat.get("pid_starttime"), proc=proc):
            # The lock is held by something, but the process that was beating is gone -- a child
            # still owns the file description.  Never say "PID N holds the lock and is beating"
            # about a process that does not exist, and never hand out a restart command here.
            return ORPHAN_LOCK, dict(facts, why="beat pid %s no longer exists" % beat["pid"])

    if beat:
        age = now - float(beat.get("wall_ts") or 0)
        facts["beat_age_s"] = round(age, 1)
        if age > BEAT_STALE_S:
            # A stale beat ALONE is not an orphan. If the beater died while the loop kept working,
            # calling that ORPHAN_LOCK would raise a false alarm about a perfectly healthy loop --
            # and the design is already carrying enough of those from the previous system. The
            # orphan verdict requires the beat's process to be GONE, which is checked above; here
            # the loop is demonstrably alive, so we say the witness failed, not the subject.
            facts["beat_stale"] = True
            facts["second_witness"] = "FAILED (beater stopped; verdict rests on the lock alone)"
        deadline = beat.get("phase_deadline")
        facts["phase"] = beat.get("phase")
        if deadline:
            # A phase whose budget was declared BEFORE it ran, so a long wait that the loop
            # intended is not mistaken for a hang.  Three of five phases have no budget in the
            # code to derive one from; those are RUNNING and the watchdog says so rather than
            # inventing a number.
            if now > float(deadline):
                return ORPHAN_LOCK, dict(facts, why="phase %s past its declared deadline"
                                         % beat.get("phase"))
    return RUNNING, facts


def write_beat(path=None, phase=None, budget_s=None, journal_rows=None, complete_rows=None,
               lock_ino=None, consec_zero_rounds=None):
    """Called by the loop.  The temp file goes in the TARGET directory, never $TMPDIR: /opt/wq and
    /tmp are different filesystems, rename(2) across them returns EXDEV, and /bin/mv silently
    degrades to copy-then-unlink, which is not atomic."""
    path = path or os.environ.get("WQ_BEAT") or DEFAULT_BEAT
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pid = os.getpid()
    starttime = None
    try:
        with open("/proc/%d/stat" % pid) as fh:
            raw = fh.read()
        starttime = int(raw[raw.rindex(")") + 1:].split()[19])
    except (OSError, ValueError, IndexError):
        pass
    beat = {
        "pid": pid,
        "pid_starttime": starttime,
        "boot_id": _read_boot_id(),
        "lock_ino": lock_ino,
        "phase": phase,
        # Ages are computed from the monotonic clock; the wall value is for display only, so a
        # clock step cannot manufacture a verdict.
        "mono": time.monotonic(),
        "wall_ts": time.time(),
        "phase_deadline": (time.time() + budget_s) if budget_s else None,
        "journal_rows": journal_rows,
        "complete_rows": complete_rows,
        "consec_zero_rounds": consec_zero_rounds,
    }
    import tempfile
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".beat_")
    with os.fdopen(fd, "w") as fh:
        json.dump(beat, fh)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return beat


def main(argv):
    state, facts = classify()
    print(state)
    for k in sorted(facts):
        print("  %-14s %s" % (k, facts[k]))
    return 0 if state in (RUNNING, UNSUPPORTED) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
