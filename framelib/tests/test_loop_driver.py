"""vps/frames_loop.sh and vps/wq-frames.service, run by bash with every outside command stubbed.

Nothing here reaches the platform or the VPS (RULE 1). The script runs under /bin/bash in a scratch root:
  * python is a fake that records each step (module or script, and its arguments) and plays a scenario; the loop's
    inline snippets (`python -` and `python -c`) run on the real interpreter against a fake forge/search.py and a fake
    tools/layered_sim.py in the scratch root, and against the real framelib (symlinked) for analyse_round.outcome;
  * flock and timeout are small python fakes with util-linux's and coreutils' exit codes (a command ended by a
    signal returns 128+N; a timeout returns 124); the fake flock takes a real flock(2), so the lock tests are real;
  * sleep records its argument and returns; pgrep matches its pattern against a fake process table (the loop's own
    command line, plus the host's round driver while a counter file says so); systemctl and ssh record any call,
    and every test run asserts they were never called.
  * the ET-day tests run under a host zone whose date differs from New York's at the moment of the run.
FRAMES_LOOP_SH / FRAMES_UNIT point the tests at another copy (used to check that each test fails without the
behaviour it names); by default they read the repository's files.
"""
from __future__ import annotations

import datetime
import fcntl
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import zoneinfo

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = pathlib.Path(os.environ.get("FRAMES_LOOP_SH") or REPO / "vps" / "frames_loop.sh")
UNIT = pathlib.Path(os.environ.get("FRAMES_UNIT") or REPO / "vps" / "wq-frames.service")
NY = zoneinfo.ZoneInfo("America/New_York")
REAL = sys.executable
BINDING = ("LOW_SHARPE", "LOW_FITNESS", "LOW_SUB_UNIVERSE_SHARPE", "IS_LADDER_SHARPE", "CONCENTRATED_WEIGHT",
           "HIGH_TURNOVER", "LOW_TURNOVER")
DAILY_BODY = '  daily simulation limit reached -- stopping: {"detail":"DAILY_SIMULATION_LIMIT_EXCEEDED"}'

FAKE_PY = r'''#!%(real)s
import json, os, pathlib, signal, sys, time
argv = sys.argv[1:]
calls = os.environ["FAKE_CALLS"]
def record(key, args):
    with open(calls, "a") as fh:
        fh.write(json.dumps({"key": key, "args": args}) + "\n")
if argv[:1] == ["-c"] or argv[:1] == ["-"]:
    record("inline:" + (argv[1] if argv[0] == "-" else "c"), argv[2:] if argv[0] == "-" else argv[2:])
    os.execv(%(real)r, [%(real)r, "-B"] + argv)
while argv and argv[0] in ("-u", "-B"):
    argv.pop(0)
key, args = (argv[1], argv[2:]) if argv[0] == "-m" else (os.path.basename(argv[0]), argv[1:])
prev = 0
if os.path.exists(calls):
    prev = sum(1 for l in open(calls) if json.loads(l)["key"] == key)
record(key, args)
sc = json.load(open(os.environ["FAKE_SCENARIO"]))
outs = sc.get(key) or [{}]
o = outs[min(prev, len(outs) - 1)]
def arg(name):
    return args[args.index(name) + 1]
if "plan" in o and o["plan"] is not None:
    pathlib.Path(arg("--out")).write_text(o["plan"] if isinstance(o["plan"], str) else json.dumps(o["plan"]))
if o.get("rows"):
    with open(arg("--journal"), "a") as fh:
        for r in o["rows"]:
            fh.write(json.dumps(r) + "\n")
if o.get("touch"):
    pathlib.Path(o["touch"]).write_text("")
if o.get("hold_until"):
    open(o["started"], "w").close()
    t = time.time()
    while not os.path.exists(o["hold_until"]) and time.time() - t < 60:
        time.sleep(0.05)
if o.get("stdout"):
    print(o["stdout"], flush=True)
if o.get("signal"):
    os.kill(os.getpid(), getattr(signal, o["signal"]))
sys.exit(o.get("rc", 0))
'''

FAKE_FLOCK = r'''#!%(real)s
import fcntl, os, subprocess, sys, time
a = sys.argv[1:]
nb, wait = False, None
while a and a[0].startswith("-"):
    if a[0] == "-n":
        nb = True
        a.pop(0)
    elif a[0] == "-w":
        wait = float(a[1])
        del a[:2]
    else:
        sys.exit(64)
target, cmd = a[0], a[1:]
fd = int(target) if target.isdigit() and not cmd else os.open(target, os.O_RDWR | os.O_CREAT, 0o644)
t0 = time.time()
while True:
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        break
    except OSError:
        if nb or (wait is not None and time.time() - t0 >= wait):
            sys.exit(1)
        time.sleep(0.05)
if not cmd:
    sys.exit(0)
rc = subprocess.Popen(cmd, close_fds=False).wait()
sys.exit(128 - rc if rc < 0 else rc)
'''

FAKE_TIMEOUT = r'''#!%(real)s
import os, subprocess, sys
with open(os.environ["FAKE_TIMEOUTS"], "a") as fh:
    fh.write(sys.argv[1] + "\n")
p = subprocess.Popen(sys.argv[2:], close_fds=False)
try:
    rc = p.wait(timeout=float(sys.argv[1]))
except subprocess.TimeoutExpired:
    p.terminate()
    p.wait()
    sys.exit(124)
sys.exit(128 - rc if rc < 0 else rc)
'''

FAKE_SLEEP = '#!/bin/bash\necho "$1" >> "$FAKE_SLEEPS"\n'
FAKE_PGREP = r'''#!/bin/bash
# pgrep -f PATTERN over a fake process table: the loop's own command line always, and the round driver as the host
# runs it while the counter file holds a number above 0 (decremented per call). The pattern is really matched.
pat=${!#}
n=$(cat "$FAKE_PGREP" 2>/dev/null || echo 0)
rows="1000 /bin/bash /opt/wq/frames_loop.sh"
if [ "$n" -gt 0 ]; then
  echo $((n - 1)) > "$FAKE_PGREP"
  rows="$rows
4242 /bin/bash /opt/wq/experiments/frames/frames_round.sh --live"
fi
hit=$(printf '%s\n' "$rows" | while read -r pid cmd; do printf '%s\n' "$cmd" | grep -Eq -- "$pat" && echo "$pid"; done)
[ -n "$hit" ] && { echo "$hit"; exit 0; }
exit 1
'''
FAKE_FORBIDDEN = '#!/bin/bash\necho "$(basename "$0") $*" >> "$FAKE_FORBIDDEN"\nexit 1\n'

FAKE_SEARCH = '''import os
if os.environ.get("FAKE_AUTH") == "import":
    raise ImportError("fake: forge.search cannot import")
def wait_for_auth(max_s=3 * 3600, poll_s=30.0, out=print):
    with open(os.environ["FAKE_AUTH_LOG"], "a") as fh:
        fh.write("%s\\n" % max_s)
    return os.environ.get("FAKE_AUTH", "ok") == "ok"
'''

FAKE_LAYERED_SIM = '''import json, os
API = "https://example.invalid"
class _R:
    def __init__(self, code, body):
        self.status_code, self._b, self.headers = code, body, {}
    def json(self):
        return self._b
class _S:
    def get(self, url, params=None, timeout=None):
        spec = json.load(open(os.environ["FAKE_DATASETS"]))
        with open(os.environ["FAKE_DATASETS_LOG"], "a") as fh:
            fh.write(json.dumps({"url": url, "params": params}) + "\\n")
        if spec.get("status", 200) != 200:
            return _R(spec["status"], {})
        ids, off, lim = spec["ids"], params["offset"], params["limit"]
        return _R(200, {"count": spec.get("count", len(ids)), "results": [{"id": i} for i in ids[off:off + lim]]})
def session():
    return _S()
'''


def row(alpha, d24=True, sharpe=2.0, status="COMPLETE"):
    checks = [{"name": n, "result": "PASS" if (d24 or n != "LOW_FITNESS") else "FAIL"} for n in BINDING]
    checks[0]["limit"] = 1.58
    return {"alpha": alpha, "status": status, "sharpe": sharpe, "formula": "rank(x_%s)" % alpha,
            "settings": {"region": "USA"}, "checks": checks, "meta": {"experiment": "FRAMES-LOOP"}}


PLAN_OK = {"constructions": [{"formula": "rank(x)", "settings": {}, "meta": {"arm": "screen"}}] * 3}


class Rig:
    """A scratch /opt/wq for one test: fakes on PATH, a scenario per step, and readers for what the loop did."""

    def __init__(self, tmp: pathlib.Path):
        self.tmp, self.root, self.bin = tmp, tmp / "root", tmp / "bin"
        for d in (self.root / "forge", self.root / "tools", self.bin):
            d.mkdir(parents=True)
        (self.root / "framelib").symlink_to(REPO / "framelib")
        (self.root / "forge" / "__init__.py").write_text("")
        (self.root / "forge" / "search.py").write_text(FAKE_SEARCH)
        (self.root / "tools" / "layered_sim.py").write_text(FAKE_LAYERED_SIM)
        for name, text in (("python", FAKE_PY), ("flock", FAKE_FLOCK), ("timeout", FAKE_TIMEOUT), ("sleep", FAKE_SLEEP),
                           ("pgrep", FAKE_PGREP), ("systemctl", FAKE_FORBIDDEN), ("ssh", FAKE_FORBIDDEN)):
            p = self.bin / name
            p.write_text(text % {"real": REAL} if "%(real)" in text else text)
            p.chmod(0o755)
        self.f = {k: tmp / ("%s.txt" % k) for k in ("calls", "timeouts", "sleeps", "pgrep", "forbidden", "auth",
                                                   "datasets_log")}
        self.f["calls"] = tmp / "calls.jsonl"
        self.scenario_path, self.datasets_path = tmp / "scenario.json", tmp / "datasets.json"
        self.lock, self.climb_lock, self.probe_lock = tmp / "wq_forge.lock", tmp / "wq_climb.lock", tmp / "probe.lock"
        self.scenario()
        self.datasets(["ds_b", "ds_a", "ds_c"])

    # ----- inputs
    def scenario(self, **steps):
        base = {"framelib.loop.plan": [{"plan": PLAN_OK}],
                "dispatch_round.py": [{"rows": [row("A1"), row("A2", d24=False)], "stdout": "forge: 3 construction(s)"}]}
        base.update({k.replace("__", "."): v for k, v in steps.items()})
        self.scenario_path.write_text(json.dumps(base))

    def datasets(self, ids, status=200, count=None):
        spec = {"ids": ids, "status": status}
        if count is not None:
            spec["count"] = count
        self.datasets_path.write_text(json.dumps(spec))

    def env(self, rounds=1, **extra):
        e = {"PATH": "%s:/usr/bin:/bin" % self.bin, "HOME": str(self.tmp), "TZ": "Asia/Ho_Chi_Minh",
             "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "", "ROUNDS": str(rounds),
             "FRAMES_ROOT": str(self.root), "FRAMES_PY": str(self.bin / "python"), "FRAMES_LOCK": str(self.lock),
             "FRAMES_CLIMB_LOCK": str(self.climb_lock), "FRAMES_PROBE_LOCK": str(self.probe_lock),
             "FAKE_CALLS": str(self.f["calls"]), "FAKE_TIMEOUTS": str(self.f["timeouts"]),
             "FAKE_SLEEPS": str(self.f["sleeps"]), "FAKE_PGREP": str(self.f["pgrep"]),
             "FAKE_FORBIDDEN": str(self.f["forbidden"]), "FAKE_AUTH_LOG": str(self.f["auth"]),
             "FAKE_SCENARIO": str(self.scenario_path), "FAKE_DATASETS": str(self.datasets_path),
             "FAKE_DATASETS_LOG": str(self.f["datasets_log"])}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def run(self, rounds=1, **extra):
        r = subprocess.run(["/bin/bash", str(SCRIPT)], env=self.env(rounds, **extra), capture_output=True, text=True,
                           timeout=120, cwd=str(self.tmp))
        assert not self.f["forbidden"].exists(), self.f["forbidden"].read_text()     # never systemctl, never ssh
        return r

    # ----- outputs
    def calls(self):
        p = self.f["calls"]
        return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []

    def keys(self, inline=False):
        return [c["key"] for c in self.calls() if inline or not c["key"].startswith("inline:")]

    def args(self, key):
        return [c["args"] for c in self.calls() if c["key"] == key]

    def lines(self, k):
        p = self.f[k]
        return p.read_text().split() if p.exists() else []

    def log(self):
        p = self.root / "state/frames/loop.log"
        return p.read_text() if p.exists() else ""

    def markers(self):
        return [l for l in self.log().splitlines() if l.startswith("=== ")]

    @property
    def journal(self):
        return self.root / "state/layered/runs/frames_loop.jsonl"

    @property
    def state(self):
        return self.root / "state/frames"


@pytest.fixture()
def rig(tmp_path):
    return Rig(tmp_path)


def et_today():
    return datetime.datetime.now(NY).date().isoformat()


def zone_off_new_york_date() -> str:
    """A host zone whose date differs from New York's right now, so a host-date bug cannot pass by the hour of the
    run: UTC+14 is a day ahead from 05:00-06:00 New York time on, UTC-12 a day behind until 07:00-08:00."""
    for z in ("Pacific/Kiritimati", "Etc/GMT+12"):
        if datetime.datetime.now(zoneinfo.ZoneInfo(z)).date().isoformat() != et_today():
            return z
    raise AssertionError("no zone off New York's date")


STEPS = ["framelib.loop.evidence", "framelib.loop.newframes", "framelib.loop.plan", "dispatch_round.py", "probe.py",
         "framelib.loop.submit"]


# ============================================================================== one round, the shared interface
def test_a_round_runs_every_step_in_order_with_the_shared_interface_arguments(rig):
    r = rig.run()
    assert r.returncode == 0, r.stderr
    assert rig.keys() == STEPS
    assert rig.keys(inline=True) == ["inline:auth", "inline:c", "inline:datasets", "framelib.loop.evidence",
                                     "framelib.loop.newframes", "framelib.loop.plan", "inline:plan",
                                     "dispatch_round.py", "inline:journal", "probe.py", "framelib.loop.submit",
                                     "inline:journal"]
    head = [m for m in rig.markers() if m.startswith("=== frames round 1, seed ")]
    assert len(head) == 1
    seed = re.match(r"=== frames round 1, seed (\d+), ET day (\S+), N=300, ", head[0]).group(1)
    plan = str(rig.state / "loop_plans" / ("%s.json" % seed))
    assert rig.args("framelib.loop.evidence") == [["--update"]]
    assert rig.args("framelib.loop.newframes") == [["--n", "25"]]
    # the planner gets the round's seed: one number for the log, the plan file, meta.round_seed and the dispatcher
    assert rig.args("framelib.loop.plan") == [["--n", "300", "--seed", seed, "--out", plan]]
    assert rig.args("dispatch_round.py") == [["--abc", plan, "--seed", seed, "--journal", str(rig.journal),
                                              "--experiment", "FRAMES-LOOP", "--live"]]
    assert [c for c in rig.calls() if c["key"] == "dispatch_round.py"] and \
        pathlib.Path(plan).exists()
    assert rig.args("probe.py") == [["--alphas", "A1", "--limit", "60", "--wait", "120"]]
    assert rig.args("framelib.loop.submit") == [["--submit"]]
    # evidence, newframes and plan run under `timeout 1800`, the probe under `timeout 1500` (inside its lock)
    assert rig.lines("timeouts") == ["1800", "1800", "1800", "1500"]
    # each step is followed by its marker, in order
    steps = [m.split()[2] for m in rig.markers() if m.startswith("=== step ")]
    assert steps == ["datasets", "evidence", "newframes", "plan", "dispatch", "probe", "submit"]
    assert rig.lines("sleeps") == []


def test_the_summary_line_counts_this_rounds_rows_only(rig):
    rig.journal.parent.mkdir(parents=True)
    rig.journal.write_text("".join(json.dumps(row("OLD%d" % i)) + "\n" for i in range(5)))    # an earlier round
    rig.scenario(dispatch_round__py=[{"rows": [{"status": "PARENT-POSTED", "parent_url": "u"}, row("A1"),
                                                row("A2", d24=False, sharpe=0.5),
                                                {"status": "ERROR", "formula": "f", "settings": {}}]}])
    assert rig.run().returncode == 0
    ends = [m for m in rig.markers() if m.startswith("=== frames round end, seed ")]
    assert len(ends) == 1
    assert ("plan 3, dispatch exit 0, journalled 4 line(s): 3 row(s), 2 scored, y08 1, D24 1; probe exit 0 "
            "(6 D24 id(s)); submit exit 0, posted ?; daily limit no, at ") in ends[0]      # the fake submit printed nothing


def test_the_summary_line_carries_the_submitters_own_posted_count_from_this_round_only(rig):
    """framelib.loop.submit's cli() ends with "posted N[: ids]" (read 2026-09-25); a "posted" line in the probe's
    output or in an earlier round's output is not the submitter's."""
    rig.state.mkdir(parents=True)
    (rig.state / "loop.log").write_text("posted 7: OLD1\n")
    rig.scenario(probe__py=[{"stdout": "posted 9: NOT_THE_SUBMITTER"}],
                 framelib__loop__submit=[{"stdout": "frames submit: 2 loop row(s)\nposted 2: A1, B2"}, {"stdout": ""}])
    assert rig.run(rounds=2).returncode == 0
    ends = [m for m in rig.markers() if m.startswith("=== frames round end, seed ")]
    assert len(ends) == 2
    assert "; submit exit 0, posted 2; daily limit no, at " in ends[0]
    assert "; submit exit 0, posted ?; daily limit no, at " in ends[1]


# ============================================================================== the probe's list
def test_the_probe_is_asked_for_every_d24_pass_of_the_journal_newest_first(rig):
    rig.journal.parent.mkdir(parents=True)
    old = [row("OLD1"), row("OLD2"), row("NOPE", d24=False), {"status": "PARENT-POSTED"}, "not json"]
    rig.journal.write_text("".join((json.dumps(x) if isinstance(x, dict) else x) + "\n" for x in old))
    # this round: NEW1 passes; OLD2's LAST row fails, so OLD2 is no longer a pass; a WARNING row can pass too
    rig.scenario(dispatch_round__py=[{"rows": [row("NEW1"), row("OLD2", d24=False), row("NEW2", status="WARNING"),
                                               row("ERR", status="ERROR")]}])
    assert rig.run().returncode == 0
    assert rig.args("probe.py") == [["--alphas", "NEW2,NEW1,OLD1", "--limit", "60", "--wait", "120"]]


def test_without_a_d24_pass_the_probe_is_not_run_and_submit_still_is(rig):
    rig.scenario(dispatch_round__py=[{"rows": [row("A2", d24=False)]}])
    assert rig.run().returncode == 0
    assert rig.keys() == ["framelib.loop.evidence", "framelib.loop.newframes", "framelib.loop.plan",
                          "dispatch_round.py", "framelib.loop.submit"]
    assert "probe exit none (0 D24 id(s))" in rig.log()


# ============================================================================== once per ET day
def test_the_daily_steps_run_once_per_et_day_and_stamp_the_new_york_date(rig):
    assert rig.run(rounds=3, TZ=zone_off_new_york_date()).returncode == 0
    k = rig.keys()
    assert k.count("framelib.loop.newframes") == 1 and k.count("framelib.loop.plan") == 3
    assert rig.keys(inline=True).count("inline:datasets") == 1
    assert (rig.state / "loop_day.datasets").read_text().strip() == et_today()
    assert (rig.state / "loop_day.newframes").read_text().strip() == et_today()


@pytest.mark.parametrize("stamp,runs", [("today", 0), ("2020-01-01", 1)])
def test_a_stamp_of_today_skips_the_daily_steps_and_any_other_day_runs_them(rig, stamp, runs):
    rig.state.mkdir(parents=True)
    for name in ("loop_day.datasets", "loop_day.newframes"):
        (rig.state / name).write_text((et_today() if stamp == "today" else stamp) + "\n")
    assert rig.run().returncode == 0
    assert rig.keys().count("framelib.loop.newframes") == runs
    assert rig.keys(inline=True).count("inline:datasets") == runs
    assert rig.keys().count("dispatch_round.py") == 1


def test_a_failed_newframes_lets_the_round_go_on_and_is_retried_next_round(rig):
    rig.scenario(framelib__loop__newframes=[{"rc": 1}, {"rc": 0}])
    assert rig.run(rounds=3).returncode == 0
    k = rig.keys()
    assert k.count("framelib.loop.newframes") == 2 and k.count("dispatch_round.py") == 3
    assert "=== newframes failed (exit 1): the round goes on without today's new frames; retried next round ===" \
        in rig.markers()
    assert (rig.state / "loop_day.newframes").read_text().strip() == et_today()


# ============================================================================== datasets_ok.json
def test_datasets_ok_is_every_page_of_the_usa_top3000_d1_listing_sorted(rig):
    ids = ["ds%03d" % i for i in range(60, 0, -1)]                      # two pages of 50
    rig.datasets(ids)
    assert rig.run().returncode == 0
    assert json.loads((rig.state / "datasets_ok.json").read_text()) == sorted(ids)
    gets = [json.loads(l) for l in rig.f["datasets_log"].read_text().splitlines()]
    assert [g["url"] for g in gets] == ["https://example.invalid/data-sets"] * 2
    assert [g["params"] for g in gets] == [{"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
                                            "delay": 1, "limit": 50, "offset": o} for o in (0, 50)]
    assert not (rig.state / "datasets_ok.json.tmp").exists()
    from framelib.loop import availability as AV                        # the reader on the other side of the file
    assert AV.load(rig.state / "datasets_ok.json") == set(ids)


@pytest.mark.parametrize("status,count", [(500, None), (200, 5)])
def test_no_round_is_dispatched_without_todays_datasets_and_the_old_file_is_kept(rig, status, count):
    rig.state.mkdir(parents=True)
    (rig.state / "datasets_ok.json").write_text('["yesterday"]')
    rig.datasets(["ds_a", "ds_b", "ds_c"], status=status, count=count)
    assert rig.run(rounds=2).returncode == 0
    assert rig.keys() == []                                            # no evidence, plan, dispatch, probe or submit
    assert rig.keys(inline=True).count("inline:datasets") == 2         # retried on the next round
    assert (rig.state / "datasets_ok.json").read_text() == '["yesterday"]'
    assert not (rig.state / "loop_day.datasets").exists()
    assert rig.lines("sleeps") == ["900", "900"]
    assert sum(m.startswith("=== step datasets failed (exit 1): round ") for m in rig.markers()) == 2


# ============================================================================== fail closed before dispatch
@pytest.mark.parametrize("case", ["evidence_fails", "evidence_times_out", "plan_fails", "plan_not_json",
                                  "plan_not_a_plan", "plan_missing"])
def test_nothing_is_dispatched_unless_evidence_and_a_readable_plan_succeeded(rig, case):
    steps = {"evidence_fails": {"framelib__loop__evidence": [{"rc": 1}]},
             "evidence_times_out": {"framelib__loop__evidence": [{"rc": 124}]},
             "plan_fails": {"framelib__loop__plan": [{"plan": PLAN_OK, "rc": 2}]},
             "plan_not_json": {"framelib__loop__plan": [{"plan": "{not json"}]},
             "plan_not_a_plan": {"framelib__loop__plan": [{"plan": [1, 2]}]},
             "plan_missing": {"framelib__loop__plan": [{"plan": None}]}}[case]
    rig.scenario(**steps)
    assert rig.run(rounds=2).returncode == 0
    for k in ("dispatch_round.py", "probe.py", "framelib.loop.submit"):
        assert k not in rig.keys(), case
    assert rig.lines("sleeps") == ["900", "900"]
    assert any(" failed (exit " in m and "round 1 ends here" in m for m in rig.markers())


def test_evidence_exit_3_ledger_written_library_refused_lets_the_round_go_on(rig):
    """framelib/loop/evidence.py: exit 3 = the ledger was written and a library entry refused evidence.live."""
    rig.scenario(framelib__loop__evidence=[{"rc": 3}, {"rc": 1}])
    assert rig.run(rounds=2).returncode == 0
    k = rig.keys()
    assert k.count("framelib.loop.evidence") == 2 and k.count("dispatch_round.py") == 1       # round 2's exit 1 stops
    assert k[:6] == STEPS
    assert ("=== evidence exit 3: the ledger was written; a library entry refused its evidence.live block (named "
            "above); the round goes on ===") in rig.markers()
    assert "=== step evidence failed (exit 1): round 2 ends here; backing off 900s ===" in rig.markers()


@pytest.mark.parametrize("bad", ["{not json", "[1, 2]"])
def test_the_plan_is_kept_out_of_evidences_archive_so_a_broken_plan_cannot_fail_later_evidence_updates(rig, bad):
    """The REAL framelib.loop.evidence, on the state the round left: it json.loads every state/frames/plans/*.json."""
    from framelib.loop import evidence as EV
    rig.scenario(framelib__loop__plan=[{"plan": bad}])
    assert rig.run(rounds=1).returncode == 0
    assert "dispatch_round.py" not in rig.keys()
    kept = list((rig.state / "loop_plans").glob("*.json"))
    assert len(kept) == 1 and kept[0].read_text() == bad                # kept for the post-mortem, where evidence
    assert not list(rig.state.glob("plans/*"))                          # ...does not look
    recs, report = EV.constructions(rig.root / "state")                 # raises if the broken plan were in plans/
    assert recs == [] and report["plans_counted"] == [] and report["plans_not_run"] == []


def test_an_empty_plan_dispatches_nothing_and_waits_an_hour(rig):
    rig.scenario(framelib__loop__plan=[{"plan": {"constructions": []}}])
    assert rig.run(rounds=2).returncode == 0
    assert "dispatch_round.py" not in rig.keys() and "framelib.loop.submit" not in rig.keys()
    assert rig.lines("sleeps") == ["3600", "3600"]


# ============================================================================== signals
def test_a_dispatcher_ended_by_a_signal_skips_probe_and_submit_and_backs_off(rig):
    rig.scenario(dispatch_round__py=[{"rows": [row("A1")], "signal": "SIGKILL"}, {"rows": [row("B1")]}])
    assert rig.run(rounds=2).returncode == 0
    k = rig.keys()
    assert k.count("dispatch_round.py") == 2 and k.count("probe.py") == 1 and k.count("framelib.loop.submit") == 1
    assert k.index("probe.py") > [i for i, x in enumerate(k) if x == "dispatch_round.py"][1]
    assert "=== step dispatch ended by signal 9 (exit 137): round 1 ends here; backing off 900s ===" in rig.markers()
    assert rig.lines("sleeps") == ["900"]


@pytest.mark.parametrize("step,skipped", [("framelib__loop__evidence", ["framelib.loop.plan"]),
                                          ("framelib__loop__plan", ["dispatch_round.py"]),
                                          ("framelib__loop__newframes", ["framelib.loop.plan"]),
                                          ("probe__py", ["framelib.loop.submit"])])
def test_any_step_ended_by_a_signal_ends_the_round_there(rig, step, skipped):
    rig.scenario(**{step: [{"signal": "SIGKILL"}]})
    assert rig.run(rounds=2).returncode == 0
    for k in skipped:
        assert k not in rig.keys()
    name = {"framelib__loop__evidence": "evidence", "framelib__loop__plan": "plan",
            "framelib__loop__newframes": "newframes", "probe__py": "probe"}[step]
    assert "=== step %s ended by signal 9 (exit 137): round 1 ends here; backing off 900s ===" % name in rig.markers()
    assert rig.lines("sleeps")[:1] == ["900"]


def test_a_submitter_ended_by_a_signal_still_gets_its_summary_then_backs_off(rig):
    rig.scenario(framelib__loop__submit=[{"signal": "SIGTERM"}])
    assert rig.run(rounds=2).returncode == 0
    m = rig.markers()
    end = next(i for i, x in enumerate(m) if x.startswith("=== frames round end, seed ") and "submit exit 143" in x)
    assert m[end + 1] == "=== step submit ended by signal 15 (exit 143); backing off 900s ==="
    assert rig.lines("sleeps")[:1] == ["900"]


def test_a_one_round_caller_never_sleeps(rig):
    rig.scenario(dispatch_round__py=[{"signal": "SIGKILL"}])
    assert rig.run(rounds=1).returncode == 0
    assert "=== step dispatch ended by signal 9 (exit 137): round 1 ends here; backing off 900s ===" in rig.markers()
    assert rig.lines("sleeps") == []


# ============================================================================== after dispatch
def test_a_failed_dispatcher_still_probes_and_submits_then_backs_off(rig):
    rig.scenario(dispatch_round__py=[{"rows": [row("A1")], "rc": 1}])
    assert rig.run(rounds=2).returncode == 0
    assert rig.keys()[:6] == STEPS
    assert rig.lines("sleeps")[:1] == ["900"]
    assert "=== dispatch exit 1, " in rig.log()


def test_a_round_that_journalled_nothing_backs_off_and_one_that_did_does_not(rig):
    rig.scenario(dispatch_round__py=[{"rows": []}, {"rows": [row("A1")]}, {"rows": [row("A2")]}])
    assert rig.run(rounds=3).returncode == 0
    assert rig.keys().count("dispatch_round.py") == 3
    assert rig.lines("sleeps") == ["900"]
    assert "=== dispatch exit 0, 0 journal byte(s) this round: backing off 900s ===" in rig.markers()


# ============================================================================== the daily limit
def _next_0005_ny(t: float) -> int:
    """By hand, not by the code under test: 00:05 New York on the NY date of t, else on the next NY date."""
    d = datetime.datetime.fromtimestamp(t, NY).date()
    for k in (0, 1):
        x = datetime.datetime(d.year, d.month, d.day, 0, 5, tzinfo=NY) + datetime.timedelta(days=k)
        x = datetime.datetime(x.year, x.month, x.day, 0, 5, tzinfo=NY)
        if x.timestamp() > t:
            return int(x.timestamp())
    raise AssertionError


def test_the_daily_limit_from_this_dispatch_stops_spending_until_0005_new_york(rig):
    rig.scenario(dispatch_round__py=[{"rows": [row("A1")], "stdout": DAILY_BODY}, {"rows": [row("B1")]}])
    t0 = time.time()
    assert rig.run(rounds=2).returncode == 0
    t1 = time.time()
    k = rig.keys()
    assert k.count("probe.py") == 2 and k.count("framelib.loop.submit") == 2     # neither spends simulations
    sleeps = rig.lines("sleeps")
    assert len(sleeps) == 1
    reset = _next_0005_ny(t1)
    assert int(t0) - 1 <= reset - int(sleeps[0]) <= int(t1) + 1, (sleeps, reset, t0, t1)
    assert any(m.startswith("=== daily simulation limit reported by this round's dispatch; sleeping %s s" % sleeps[0])
               or m.startswith("=== daily simulation limit reported by this round's dispatch; sleeping %ss" % sleeps[0])
               for m in rig.markers())
    assert "daily limit yes" in rig.log() and "daily limit no" in rig.log()


@pytest.mark.parametrize("where", ["earlier_round", "submit_output", "probe_output"])
def test_a_daily_limit_line_outside_this_rounds_dispatch_does_not_stop_the_loop(rig, where):
    if where == "earlier_round":
        rig.state.mkdir(parents=True)
        (rig.state / "loop.log").write_text("=== frames round 7, seed 1 ===\n%s\n" % DAILY_BODY)
    elif where == "submit_output":
        rig.scenario(framelib__loop__submit=[{"stdout": DAILY_BODY}])
    else:
        rig.scenario(probe__py=[{"stdout": DAILY_BODY}])
    assert rig.run(rounds=2).returncode == 0
    assert DAILY_BODY in rig.log()
    assert rig.lines("sleeps") == []
    assert rig.keys().count("dispatch_round.py") == 2


def _function(name):
    lines = SCRIPT.read_text().splitlines()
    i = lines.index("%s() {" % name)
    j = next(k for k in range(i, len(lines)) if lines[k] == "}")
    return "\n".join(lines[i:j + 1]) + "\n"


def test_the_reset_is_0005_new_york_on_both_sides_of_the_dst_change_whatever_the_hosts_zone():
    """Round 3 S9's cases, re-derived by hand: EDT = UTC-4 until 02:00 on 2026-11-01, EST = UTC-5 after."""
    import calendar
    fns = _function("next_reset") + _function("quota_sleep")
    cases = {(2026, 10, 31, 4, 0): (2026, 10, 31, 4, 5), (2026, 10, 31, 12, 0): (2026, 11, 1, 4, 5),
             (2026, 11, 1, 15, 0): (2026, 11, 2, 5, 5), (2026, 11, 2, 5, 2): (2026, 11, 2, 5, 5)}
    for tz in ("Asia/Ho_Chi_Minh", "UTC"):
        for now_t, reset_t in cases.items():
            now, reset = calendar.timegm(now_t + (0,)), calendar.timegm(reset_t + (0,))
            r = subprocess.run(["/bin/bash", "-c", fns + 'echo "$(next_reset %d) $(quota_sleep %d)"' % (now, now)],
                               env={"PATH": "/usr/bin:/bin", "TZ": tz, "PY": REAL}, capture_output=True, text=True)
            assert r.stdout.split() == [str(reset), str(reset - now)], (tz, now_t, r.stdout, r.stderr)
    r = subprocess.run(["/bin/bash", "-c", fns + "quota_sleep 1000"], env={"PATH": "/usr/bin:/bin",
                       "PY": "/nonexistent/python"}, capture_output=True, text=True)
    assert r.stdout.strip() == "3600"


def test_the_et_day_is_new_yorks_date_and_a_day_that_cannot_be_computed_stops_the_round(rig):
    fn = _function("et_day") if "et_day() {\n" in SCRIPT.read_text() else \
        next(l for l in SCRIPT.read_text().splitlines() if l.startswith("et_day() {")) + "\n"
    r = subprocess.run(["/bin/bash", "-c", "PY=%s\n%set_day" % (REAL, fn)], env={"PATH": "/usr/bin:/bin",
                       "TZ": zone_off_new_york_date()}, capture_output=True, text=True)
    assert r.stdout.strip() == et_today()
    # a python without zoneinfo data (here: an interpreter that cannot start) gives no day, and no round runs
    broken = rig.bin / "python_nozone"
    broken.write_text('#!/bin/bash\nfor a in "$@"; do case "$a" in *zoneinfo.ZoneInfo*America*) exit 1;; esac; done\n'
                      'exec %s "$@"\n' % (rig.bin / "python"))
    broken.chmod(0o755)
    assert rig.run(rounds=2, FRAMES_PY=broken).returncode == 0
    assert rig.keys() == []
    assert sum(m.startswith("=== the ET day could not be computed ('') before round ") for m in rig.markers()) == 2
    assert rig.lines("sleeps") == ["900", "900"]


# ============================================================================== STOP
def test_a_stop_file_present_at_the_start_is_consumed_and_nothing_runs(rig):
    (rig.root / "state").mkdir()
    (rig.root / "state/STOP_FRAMES").write_text("")
    assert rig.run(rounds=5).returncode == 0
    assert rig.calls() == [] and not (rig.root / "state/STOP_FRAMES").exists()
    assert rig.markers()[0].startswith("=== STOP file present (consumed); ending, at ")


def test_a_stop_file_written_during_a_round_ends_the_loop_at_the_next_boundary(rig):
    rig.scenario(framelib__loop__submit=[{"touch": str(rig.root / "state/STOP_FRAMES")}])
    assert rig.run(rounds=5).returncode == 0
    assert rig.keys() == STEPS                                          # round 1 finished, round 2 never started
    m = rig.markers()
    assert m.index(next(x for x in m if x.startswith("=== frames round end, seed "))) < \
        m.index(next(x for x in m if x.startswith("=== STOP file present (consumed)")))
    assert not (rig.root / "state/STOP_FRAMES").exists()


# ============================================================================== one loop at a time
def _hold(path):
    fh = open(path, "a+")
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fh


def _held(path) -> bool:
    with open(path, "a+") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        return False


def test_the_loop_takes_the_retired_forge_loops_lock():
    text = SCRIPT.read_text()
    assert "LOCK=${FRAMES_LOCK:-/var/lock/wq_forge.lock}" in text
    assert "exec 9>/var/lock/wq_forge.lock" in (REPO / "vps" / "forge_loop.sh").read_text()


def test_a_held_lock_ends_the_loop_before_anything_runs(rig):
    fh = _hold(rig.lock)
    try:
        r = rig.run(rounds=3)
    finally:
        fh.close()
    assert r.returncode == 0 and "is held" in r.stdout
    assert rig.calls() == [] and rig.log() == ""


def test_a_held_climb_lock_ends_the_loop_before_anything_runs(rig):
    fh = _hold(rig.climb_lock)
    try:
        r = rig.run(rounds=3)
    finally:
        fh.close()
    assert r.returncode == 0 and "the climb loop holds" in r.stdout
    assert rig.calls() == []


def test_a_round_waits_while_frames_round_sh_runs(rig):
    rig.f["pgrep"].write_text("2")                      # seen by the first two round boundaries
    assert rig.run(rounds=3).returncode == 0
    assert rig.lines("sleeps") == ["300", "300"]
    assert rig.keys() == STEPS                          # only the third round ran
    assert rig.keys(inline=True)[0] == "inline:auth"
    assert sum("frames_round.sh is running and does not take" in m for m in rig.markers()) == 2


def test_a_dispatcher_that_outlives_a_killed_loop_keeps_the_lock(rig):
    """EX-ANTE, flock(2): the lock is the open file description's, shared by every child that inherited fd 9."""
    started, release = rig.tmp / "started", rig.tmp / "release"
    rig.scenario(dispatch_round__py=[{"rows": [row("A1")], "hold_until": str(release), "started": str(started)}])
    p = subprocess.Popen(["/bin/bash", str(SCRIPT)], env=rig.env(1), stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, cwd=str(rig.tmp))
    try:
        t = time.time()
        while not started.exists() and time.time() - t < 30:
            time.sleep(0.05)
        assert started.exists(), rig.log()
        second = rig.run(rounds=1)                                     # a second loop while the first dispatches
        assert "is held" in second.stdout and rig.keys().count("dispatch_round.py") == 1
        p.kill()
        p.wait(timeout=10)
        assert _held(rig.lock)                                         # the loop is gone; its dispatcher is not
    finally:
        release.write_text("")
        p.kill() if p.poll() is None else None
    t = time.time()
    while _held(rig.lock) and time.time() - t < 20:
        time.sleep(0.05)
    assert not _held(rig.lock)                                         # released when the dispatcher ends


# ============================================================================== auth
def test_no_live_session_runs_nothing_and_asks_forge_search_for_thirty_minutes(rig):
    assert rig.run(rounds=2, FAKE_AUTH="dead").returncode == 0
    assert rig.keys() == [] and rig.keys(inline=True) == ["inline:auth", "inline:auth"]
    assert rig.lines("auth") == ["1800.0", "1800.0"]
    assert sum(m.startswith("=== no live session within 1800s before round ") for m in rig.markers()) == 2
    assert rig.lines("sleeps") == []                                   # wait_for_auth itself waited


def test_an_auth_wait_that_cannot_import_backs_off(rig):
    assert rig.run(rounds=2, FAKE_AUTH="import").returncode == 0
    assert rig.keys() == []
    assert sum(m.startswith("=== auth wait crashed (exit 4) before round ") for m in rig.markers()) == 2
    assert rig.lines("sleeps") == ["900", "900"]
    assert "fake: forge.search cannot import" in rig.log()


# ============================================================================== nothing else is touched
def test_the_loop_never_names_systemctl_ssh_or_wq_forge_outside_its_comments():
    code = "\n".join(re.sub(r"(^|\s)#.*$", "", l) for l in SCRIPT.read_text().splitlines())
    for word in ("systemctl", "ssh ", "wq-forge", "forge_loop"):
        assert word not in code, word


def test_the_script_parses():
    r = subprocess.run(["/bin/bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ============================================================================== the unit
def _unit_keys():
    out = {}
    for line in UNIT.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out.setdefault(k.strip(), []).append(v.strip())
    return out


def test_the_unit_runs_the_loop_restarts_always_and_is_memory_bounded():
    k = _unit_keys()
    assert k["ExecStart"] == ["/bin/bash /opt/wq/frames_loop.sh"]
    assert k["Restart"] == ["always"] and k["RestartSec"] == ["60"] and k["MemoryMax"] == ["3G"]
    assert k["WorkingDirectory"] == ["/opt/wq"] and k["Type"] == ["simple"]
    assert k["Environment"] == ["ROUNDS=100000"] and k["WantedBy"] == ["multi-user.target"]
    code = [l for l in UNIT.read_text().splitlines() if not l.startswith("#")]
    for word in ("wq-forge", "forge_loop", "forge.service"):             # it never starts, wants or orders on wq-forge
        assert not any(word in l for l in code), word
    assert not any(l.split("=")[0] in ("Wants", "Requires", "BindsTo", "Conflicts", "OnFailure", "ExecStartPre",
                                       "ExecStartPost", "ExecStopPost") for l in code)


def test_the_units_header_carries_the_attended_install_steps():
    head = " ".join(l.lstrip("#").strip() for l in UNIT.read_text().splitlines() if l.startswith("#"))
    for step in ("ONE-TIME ATTENDED INSTALL", "frames-r2.timer", "systemctl is-enabled wq-forge",
                 "rsync -a --exclude __pycache__ framelib/ root@160.25.88.163:/opt/wq/framelib/",
                 "scp vps/frames_loop.sh root@160.25.88.163:/opt/wq/frames_loop.sh", "bash -n /opt/wq/frames_loop.sh",
                 "scp vps/wq-frames.service root@160.25.88.163:/etc/systemd/system/wq-frames.service",
                 "systemd-analyze verify /etc/systemd/system/wq-frames.service", "systemctl daemon-reload",
                 "systemctl enable --now wq-frames", "touch state/STOP_FRAMES", "UNDO:", "systemctl is-active wq-auth"):
        assert step in head, step
    assert head.index("frames-r2.timer") < head.index("systemctl enable --now wq-frames")
