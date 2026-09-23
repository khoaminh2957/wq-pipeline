"""Suite for tools/auth_backoff.py -- the shared, disk-persisted /authentication wall.

OFFLINE BY CONSTRUCTION. `_no_network` is autouse and replaces socket.socket with something that
raises, so a test that reaches the network FAILS instead of quietly succeeding. Time is a fake
counter; nothing here sleeps, so the 7-hour window is exercised in microseconds.

RULE 0: every test asserts an OBSERVABLE CONTRACT -- which request was made, what landed in the
state file, what the next process reads back. None asserts why the platform throttles.
"""

import importlib
import json
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth_backoff  # noqa: E402


# ------------------------------------------------------------------------------------- fixtures

@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Any socket at all is a test failure."""
    def _boom(*a, **k):
        raise AssertionError("a test opened a socket; this suite must be fully offline")
    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)


class FakeClock:
    """A clock whose only motion is `advance`. No test may sleep."""

    def __init__(self, t=1_000_000.0):
        self.t = float(t)

    def now(self):
        return self.t

    def advance(self, seconds):
        self.t += float(seconds)
        return self.t


class FakeTransport:
    """Scripted /authentication. Records every call so 'made no request' is assertable."""

    def __init__(self, script):
        self.script = list(script)      # list of (status, body, headers)
        self.calls = []

    def post(self, url, **kw):
        self.calls.append(url)
        if not self.script:
            raise AssertionError(f"unscripted request to {url}")
        status, body, headers = self.script.pop(0)
        return _Resp(status, body, headers)


class _Resp:
    def __init__(self, status, body="", headers=None):
        self.status_code = status
        self.text = body
        self.headers = headers or {}


@pytest.fixture
def state(tmp_path):
    return tmp_path / "auth_backoff.json"


@pytest.fixture
def clock():
    return FakeClock()


# ------------------------------------------------------------- the driver under test (auth_only)

AUTH_URL = "https://api.worldquantbrain.com/authentication"


def drive_auth(transport, clock, state_path, source="test"):
    """The `tools/auth_only.py` POST sequence, reduced to the part the wall governs.

    Returns "THROTTLED" without touching the transport when the wall is up. This mirrors the real
    integration exactly: guard -> POST -> record.
    """
    try:
        auth_backoff.guard(source, now=clock.now(), state_path=state_path)
    except auth_backoff.AuthThrottled:
        return "THROTTLED"
    r = transport.post(AUTH_URL)
    if r.status_code == 429:
        auth_backoff.record_429(r.text, r.headers, source=source,
                                now=clock.now(), state_path=state_path)
        return "429"
    if r.status_code in (200, 201):
        auth_backoff.record_success(source=source, now=clock.now(), state_path=state_path)
        return "AUTHED"
    return str(r.status_code)


# --------------------------------------------------------------------------------- clean state

def test_absent_state_file_is_not_blocked(state, clock):
    assert auth_backoff.check(now=clock.now(), state_path=state) is None
    auth_backoff.guard("t", now=clock.now(), state_path=state)   # must not raise


def test_success_on_a_clean_wall_makes_exactly_one_request(state, clock):
    tr = FakeTransport([(201, "", {})])
    assert drive_auth(tr, clock, state) == "AUTHED"
    assert tr.calls == [AUTH_URL]


# --------------------------------------------------------------------- arming and honouring it

def test_biometrics_429_arms_a_seven_hour_wall(state, clock):
    tr = FakeTransport([(429, '{"detail":"BIOMETRICS_THROTTLED"}', {})])
    assert drive_auth(tr, clock, state) == "429"

    block = auth_backoff.check(now=clock.now(), state_path=state)
    assert block is not None
    assert block.cls == "BIOMETRICS_THROTTLED"
    assert block.remaining_s == pytest.approx(auth_backoff.BIOMETRICS_LOCK_S)


def test_a_second_module_makes_zero_requests_while_walled(state, clock):
    """The requirement in one test: module A takes the 429, module B must not touch the endpoint."""
    a = FakeTransport([(429, '{"detail":"BIOMETRICS_THROTTLED"}', {})])
    drive_auth(a, clock, state, source="auth_only")

    clock.advance(60)
    b = FakeTransport([])            # unscripted: any request at all raises
    assert drive_auth(b, clock, state, source="auth_and_resim") == "THROTTLED"
    assert b.calls == []


def test_wall_expires_after_the_window_and_one_attempt_is_allowed(state, clock):
    drive_auth(FakeTransport([(429, "BIOMETRICS_THROTTLED", {})]), clock, state)

    clock.advance(auth_backoff.BIOMETRICS_LOCK_S - 1)
    assert auth_backoff.check(now=clock.now(), state_path=state) is not None

    clock.advance(2)
    assert auth_backoff.check(now=clock.now(), state_path=state) is None
    tr = FakeTransport([(201, "", {})])
    assert drive_auth(tr, clock, state) == "AUTHED"
    assert len(tr.calls) == 1


# ------------------------------------------------------- persistence across a process restart

def test_wall_survives_a_process_restart(state, clock):
    """`_BACKOFF` in memory was erased by eleven restarts on 2026-08-12. This is that test.

    The module is re-imported from scratch, which is the strongest available stand-in for a new
    process: any reliance on in-memory state would be dropped by the reload.
    """
    drive_auth(FakeTransport([(429, "BIOMETRICS_THROTTLED", {})]), clock, state)

    del sys.modules["auth_backoff"]
    fresh = importlib.import_module("auth_backoff")
    assert fresh is not None

    clock.advance(1800)              # the full uninterrupted wait that was tried on 2026-08-12
    block = fresh.check(now=clock.now(), state_path=state)
    assert block is not None, "a restart must NOT clear the wall"
    assert block.cls == "BIOMETRICS_THROTTLED"

    tr = FakeTransport([])
    with pytest.raises(fresh.AuthThrottled):
        fresh.guard("restarted-daemon", now=clock.now(), state_path=state)
    assert tr.calls == []


def test_state_file_is_json_a_human_can_read(state, clock):
    drive_auth(FakeTransport([(429, '{"detail":"BIOMETRICS_THROTTLED"}', {})]), clock, state)
    rec = json.loads(state.read_text())
    assert rec["class"] == "BIOMETRICS_THROTTLED"
    assert rec["blocked_until"] > clock.now()
    assert rec["source"] == "test"
    assert rec["schema_ver"] == auth_backoff.SCHEMA_VER


# ------------------------------------------------------------------- the rolling-window policy

def test_each_refusal_rearms_the_full_window_from_that_refusal(state, clock):
    drive_auth(FakeTransport([(429, "BIOMETRICS_THROTTLED", {})]), clock, state)
    first_until = auth_backoff.check(now=clock.now(), state_path=state).until

    clock.advance(3600)
    auth_backoff.record_429("BIOMETRICS_THROTTLED", {}, source="t2",
                            now=clock.now(), state_path=state)
    block = auth_backoff.check(now=clock.now(), state_path=state)

    assert block.until == pytest.approx(first_until + 3600)
    assert block.consecutive == 2
    assert block.remaining_s == pytest.approx(auth_backoff.BIOMETRICS_LOCK_S)


def test_force_cannot_bypass_a_biometrics_wall(state, clock):
    auth_backoff.record_429("BIOMETRICS_THROTTLED", {}, now=clock.now(), state_path=state)
    with pytest.raises(auth_backoff.AuthThrottled):
        auth_backoff.guard("t", now=clock.now(), state_path=state, force=True)


def test_force_may_bypass_a_concurrent_wall(state, clock):
    auth_backoff.record_429("CONCURRENT simulations", {}, now=clock.now(), state_path=state)
    auth_backoff.guard("t", now=clock.now(), state_path=state, force=True)   # must not raise
    with pytest.raises(auth_backoff.AuthThrottled):
        auth_backoff.guard("t", now=clock.now(), state_path=state)


# ------------------------------------------------------------------------------- Retry-After

def test_retry_after_may_lengthen_the_wall(state, clock):
    auth_backoff.record_429("BIOMETRICS_THROTTLED", {"Retry-After": "36000"},
                            now=clock.now(), state_path=state)
    block = auth_backoff.check(now=clock.now(), state_path=state)
    assert block.remaining_s == pytest.approx(36000)


def test_retry_after_may_not_shorten_a_biometrics_wall(state, clock):
    auth_backoff.record_429("BIOMETRICS_THROTTLED", {"retry-after": "5"},
                            now=clock.now(), state_path=state)
    block = auth_backoff.check(now=clock.now(), state_path=state)
    assert block.remaining_s == pytest.approx(auth_backoff.BIOMETRICS_LOCK_S)


def test_unparseable_retry_after_falls_back_to_policy(state, clock):
    auth_backoff.record_429("BIOMETRICS_THROTTLED", {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
                            now=clock.now(), state_path=state)
    block = auth_backoff.check(now=clock.now(), state_path=state)
    assert block.remaining_s == pytest.approx(auth_backoff.BIOMETRICS_LOCK_S)


# ------------------------------------------------------------------------------ classification

@pytest.mark.parametrize("body,expected", [
    ('{"detail":"BIOMETRICS_THROTTLED"}', "BIOMETRICS_THROTTLED"),
    ("DAILY simulation limit reached", "DAILY"),
    ("CONCURRENT simulation limit", "CONCURRENT"),
    ("too many simultaneous requests", "CONCURRENT"),
    ("a simulation is already in progress", "CONCURRENT"),
    ("", "UNKNOWN"),
    ("something nobody has seen before", "UNKNOWN"),
    ({"detail": "BIOMETRICS_THROTTLED"}, "BIOMETRICS_THROTTLED"),
])
def test_classify_429(body, expected):
    assert auth_backoff.classify_429(body) == expected


def test_classifier_agrees_with_the_daemon_it_was_copied_from():
    """Pins the deliberate copy. If either classifier is edited, this fails instead of drifting."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    try:
        from harness13.runtime.auth_relay import classify_429 as daemon_classify
    except Exception as exc:                                   # pragma: no cover
        pytest.skip(f"daemon module not importable here: {exc}")
    bodies = ['{"detail":"BIOMETRICS_THROTTLED"}', "DAILY limit", "CONCURRENT limit",
              "simultaneous", "in progress", "", "gibberish", "DAILY and BIOMETRIC both"]
    for b in bodies:
        assert auth_backoff.classify_429(b) == daemon_classify(b), b


def test_unknown_body_is_treated_as_expensive_not_cheap(state, clock):
    auth_backoff.record_429("nothing recognisable", {}, now=clock.now(), state_path=state)
    block = auth_backoff.check(now=clock.now(), state_path=state)
    assert block.cls == "UNKNOWN"
    assert block.remaining_s == pytest.approx(auth_backoff.UNKNOWN_LOCK_S)
    assert block.remaining_s > auth_backoff.CONCURRENT_LOCK_S


def test_concurrent_is_a_short_wall(state, clock):
    auth_backoff.record_429("CONCURRENT", {}, now=clock.now(), state_path=state)
    assert auth_backoff.check(now=clock.now(),
                              state_path=state).remaining_s == pytest.approx(60.0)


def test_daily_wall_runs_to_the_next_reset_boundary(state, clock):
    clock.t = 1_754_000_000.0                       # arbitrary fixed instant
    auth_backoff.record_429("DAILY limit", {}, now=clock.now(), state_path=state)
    until = auth_backoff.check(now=clock.now(), state_path=state).until

    assert until > clock.now()
    assert until - clock.now() <= 86400.0
    assert (until % 86400.0) == pytest.approx(auth_backoff.DAILY_RESET_UTC_HOUR * 3600.0)


# ------------------------------------------------------------------------------- fail-closed

def test_corrupt_state_file_blocks(state, clock):
    state.write_text("{not json at all")
    block = auth_backoff.check(now=clock.now(), state_path=state)
    assert block is not None and block.cls == "CORRUPT_STATE"

    tr = FakeTransport([])
    assert drive_auth(tr, clock, state) == "THROTTLED"
    assert tr.calls == []


def test_non_numeric_blocked_until_blocks(state, clock):
    state.write_text(json.dumps({"schema_ver": 1, "blocked_until": "soon"}))
    block = auth_backoff.check(now=clock.now(), state_path=state)
    assert block is not None and block.cls == "CORRUPT_STATE"


def test_unblock_clears_a_corrupt_file_and_records_the_actor(state, clock):
    state.write_text("{not json at all")
    auth_backoff.unblock("verified clear with Khoa", "khoa", now=clock.now(), state_path=state)
    assert auth_backoff.check(now=clock.now(), state_path=state) is None
    assert "khoa" in json.loads(state.read_text())["note"]


def test_success_clears_the_wall(state, clock):
    auth_backoff.record_429("BIOMETRICS_THROTTLED", {}, now=clock.now(), state_path=state)
    auth_backoff.record_success(source="t", now=clock.now(), state_path=state)
    assert auth_backoff.check(now=clock.now(), state_path=state) is None


def test_writes_are_atomic_no_tmp_left_behind(state, clock):
    auth_backoff.record_429("BIOMETRICS_THROTTLED", {}, now=clock.now(), state_path=state)
    leftovers = list(state.parent.glob("*.tmp"))
    assert leftovers == []


# ---------------------------------------------------------------------------------- reporting

def test_describe_is_one_line_either_way(state, clock):
    assert "clear" in auth_backoff.describe(now=clock.now(), state_path=state)
    auth_backoff.record_429("BIOMETRICS_THROTTLED", {}, now=clock.now(), state_path=state)
    line = auth_backoff.describe(now=clock.now(), state_path=state)
    assert "BIOMETRICS_THROTTLED" in line and "\n" not in line


def test_block_carries_a_real_expiry_for_status_files(state, clock):
    block = auth_backoff.record_429("BIOMETRICS_THROTTLED", {}, source="auth_only",
                                    now=clock.now(), state_path=state)
    d = block.as_dict()
    assert d["class"] == "BIOMETRICS_THROTTLED"
    assert d["until"] == pytest.approx(clock.now() + auth_backoff.BIOMETRICS_LOCK_S)
    assert d["source"] == "auth_only"
