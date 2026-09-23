#!/usr/bin/env python3
"""The dead-man's switch: it fires when the NOTIFIER ITSELF stops delivering.

THE CONTROL EXPERIMENT THAT DICTATES THIS DESIGN
------------------------------------------------
For 113 days a notification daemon on the other machine had a PID, was health-managed by the OS,
wrote a heartbeat every 2 seconds, and logged 14,192 accurate self-diagnoses.  Every on-box
liveness predicate returned TRUE the whole time.  The only false statement in the entire system
was "a message arrived", and nothing was checking that.

So this switch has exactly two properties, each taken from a distinct measured failure:

  1. RECEIPT-GATED.  The clock is renewed only inside the 2xx branch of a real POST.  A process
     being alive renews nothing.  The receipt already existed in the old code and was thrown away
     at every call site.
  2. READ OFF-BOX.  Receipt-gating alone is provably insufficient -- the daemon that died was
     already receipt-gated and stayed dead for 113 days -- because on-box detection is 0-for-4 in
     this system.  So a second reader lives on a different machine.

And it never escalates over Discord.  The channel is a candidate for the broken thing, so the
alarm goes to the journal, to the unit status, and to a local file.  When healthy it costs ZERO
operator messages, because the beat is machine-to-machine and never enters the channel.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import outbox as OB  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STALE_S = 1800.0          # 30 min with work waiting and nothing delivered
REPEAT_S = 1800.0


def _state_path():
    """Beside the spool it watches, not at a fixed path.

    A constant computed at import time ignored the configured spool directory, so a run against
    one spool throttled the alarm for a different one. The state of a watcher belongs with the
    thing it is watching.
    """
    return os.path.join(OB.ensure_dirs()["base"], "deadman.json")


def escalate(lines):
    """Ordered by how little each layer depends on the thing that may be broken."""
    text = "\n".join(lines)
    try:
        subprocess.run(["systemd-cat", "-t", "wq-outbox", "-p", "err"],
                       input=text, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass
    sys.stderr.write(text + "\n")
    try:
        d = OB.ensure_dirs()
        with open(os.path.join(d["base"], "escalations.log"), "a") as fh:
            fh.write("%s DEADMAN\n%s\n" % (time.strftime("%F %T"), text))
    except OSError:
        pass


def failed_units():
    """Nothing on either machine polls this today, which is how a unit stayed dead for four days
    without a single message."""
    try:
        out = subprocess.run(["systemctl", "--failed", "--no-legend", "--plain"],
                             capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode not in (0, 1):
        return None
    return [l.split()[0] for l in out.stdout.splitlines() if l.strip()]


def check(now=None):
    now = now if now is not None else time.time()
    d = OB.ensure_dirs()
    health = {}
    try:
        with open(d["health"]) as fh:
            health = json.load(fh)
    except (OSError, ValueError):
        pass

    pending = len(OB.pending())
    _, _, last_ok = OB.stats()
    problems = []

    if pending > 0:
        if last_ok is None:
            problems.append("%d tin đang chờ và CHƯA TỪNG có tin nào gửi được -- kênh chưa bao "
                            "giờ hoạt động trên máy này" % pending)
        elif now - last_ok > STALE_S:
            problems.append("%d tin đang chờ, lần gửi được cuối cách đây %.0f phút"
                            % (pending, (now - last_ok) / 60.0))
    for ch in (health.get("degraded_channels") or []):
        problems.append("kênh %s đang DEGRADED (credential trả 404 -- webhook đã bị xoá, đổi "
                        "token không cứu được)" % ch)
    fu = failed_units()
    if fu:
        problems.append("systemd units failed: " + ", ".join(fu))
    elif fu is None:
        # Absence of a measurement is not a clean bill of health, and saying so is the whole
        # discipline this system was rebuilt around.
        problems.append("KHÔNG đọc được `systemctl --failed` -- trạng thái unit: chưa đo")
    return {"at": now, "pending": pending, "last_success_ts": last_ok, "problems": problems}


def main(argv):
    r = check()
    st = {}
    try:
        with open(_state_path()) as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        pass

    if not r["problems"]:
        st["last_ok"] = r["at"]
        st.pop("last_alarm", None)
        _save(st)
        if "--quiet" not in argv:
            print("deadman: ok (%d pending)" % r["pending"])
        return 0

    last = st.get("last_alarm", 0)
    if r["at"] - last >= REPEAT_S:
        escalate(["[wq-notify-deadman] BỘ BÁO KHÔNG GIAO ĐƯỢC TIN"] +
                 ["  - " + p for p in r["problems"]] +
                 ["  (cảnh báo này KHÔNG đi qua Discord, vì Discord có thể chính là chỗ hỏng)"])
        st["last_alarm"] = r["at"]
    _save(st)
    for p in r["problems"]:
        print("PROBLEM: %s" % p)
    # Exit 0: the check RAN, and running correctly is what an exit code reports. Returning 1 here
    # made systemd mark this unit failed, so the next run found a failed unit -- itself -- and
    # reported it. The alarm is the escalation above, not the exit status.
    #
    # A non-zero code is reserved for "the check could not be performed", which is a different
    # fact and the only one an operator can act on differently.
    return 0


def _save(st):
    path = _state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(st, fh)
    os.replace(tmp, path)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
