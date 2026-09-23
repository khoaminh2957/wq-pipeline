"""Suite for the auth-wall rendering in tools/health_report.py.

WHAT THESE TESTS ARE FOR. Two 429s reach POST /authentication and until now they rendered
identically, as `auth AUTH_UNEXPECTED`. On disk (`/opt/wq/state/wq-auth.out`) they are:

    429 `{"message":"API rate limit exceeded"}`   Retry-After: 7.0     (1 occurrence)
    429 `{"detail":"BIOMETRICS_THROTTLED"}`       Retry-After: absent  (7 occurrences)

The first has a SERVER-STATED expiry seven seconds away. The second has none, and on
2026-08-12 it survived four consecutive 1800 s client waits. Every test below asserts that the
two do not produce the same string, and that a client-chosen `backoff_s` is never printed as if
the server had promised a lift.

OFFLINE BY CONSTRUCTION, like test_auth_backoff.py: any socket is a failure.
"""

import json
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import health_report  # noqa: E402

NOW = 1_786_556_531.0          # the epoch of the real refusal recorded in state/auth_status.json


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("a test opened a socket; this suite must be fully offline")
    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)


@pytest.fixture
def st(tmp_path, monkeypatch):
    """Point health_report at an empty state dir; nothing here reads the real one."""
    monkeypatch.setattr(health_report, "ST", tmp_path)
    monkeypatch.setattr(health_report, "WALL", tmp_path / "auth_backoff.json")
    monkeypatch.setattr(health_report, "MINT_WALL", tmp_path / "auth_mint_wall.json")
    monkeypatch.setenv("WQ_AUTH_BACKOFF_PATH", str(tmp_path / "auth_backoff.json"))
    return tmp_path


def _daemon_429(st, retry_after, backoff_s=1800.0, ts=NOW):
    """The VPS daemon's shape: no body, so no class -- exactly what /opt/wq writes today."""
    (st / "auth_status.json").write_text(json.dumps(
        {"stage": "AUTH_UNEXPECTED", "code": 429, "backoff_s": backoff_s,
         "retry_after": retry_after, "ts": ts}))


def _backoff_record(st, cls, retry_after_s, until, consecutive=1):
    (st / "auth_backoff.json").write_text(json.dumps(
        {"schema_ver": 1, "blocked_until": until, "class": cls, "recorded_at": NOW,
         "retry_after_s": retry_after_s, "source": "auth_only", "consecutive": consecutive,
         "body_excerpt": "x", "note": "n"}))


# ------------------------------------------------------- the two classes must not read the same

def test_the_two_429_classes_do_not_render_identically(st):
    _backoff_record(st, "BIOMETRICS_THROTTLED", None, NOW + 1800)
    hard = health_report.wall_line(health_report.auth_wall(NOW))
    _backoff_record(st, "RATE_LIMIT", 7.0, NOW + 7)
    mild = health_report.wall_line(health_report.auth_wall(NOW))
    assert hard != mild
    assert "BIOMETRICS_THROTTLED" in hard and "RATE_LIMIT" in mild


def test_retry_after_present_is_reported_as_a_server_stated_expiry(st):
    _backoff_record(st, "RATE_LIMIT", 7.0, NOW + 7.0)
    line = health_report.wall_line(health_report.auth_wall(NOW))
    assert "Retry-After PRESENT (7.0s)" in line
    assert "server-stated" in line
    assert "UNKNOWN" not in line


def test_retry_after_absent_is_reported_as_expiry_unknown(st):
    _backoff_record(st, "BIOMETRICS_THROTTLED", None, NOW + 1800)
    line = health_report.wall_line(health_report.auth_wall(NOW))
    assert "Retry-After ABSENT" in line
    assert "expiry UNKNOWN" in line


def test_a_client_backoff_is_never_called_a_lift(st):
    """The 1800s is OUR sleep. Four of them in a row were each followed by another refusal."""
    _backoff_record(st, "BIOMETRICS_THROTTLED", None, NOW + 1800, consecutive=4)
    line = health_report.wall_line(health_report.auth_wall(NOW))
    assert "our own next retry, not a lift" in line
    assert "lifts" not in line
    assert "4 refusals in a row" in line


# ------------------------------------------------------------------ the daemon's poorer record

def test_daemon_shape_says_the_class_was_not_recorded_rather_than_guessing(st):
    """auth_daemon.py keeps no body. Inferring BIOMETRICS from backoff_s=1800 would be reading our
    own policy back as though the server had said it."""
    _daemon_429(st, retry_after=None)
    w = health_report.auth_wall(NOW + 60)
    assert w["cls"] == "UNRECORDED"
    line = health_report.wall_line(w)
    assert "UNRECORDED" in line and "does not keep the body" in line
    assert "BIOMETRIC" not in line


def test_daemon_shape_still_distinguishes_retry_after_presence(st):
    """Presence IS recorded by the daemon even though the body is not -- so the mild wall with its
    seven-second server expiry stays distinguishable from the one with none."""
    _daemon_429(st, retry_after=7.0, backoff_s=30.0)
    mild = health_report.wall_line(health_report.auth_wall(NOW + 1))
    _daemon_429(st, retry_after=None, backoff_s=1800.0)
    hard = health_report.wall_line(health_report.auth_wall(NOW + 1))
    assert "server-stated" in mild
    assert "expiry UNKNOWN" in hard


def test_an_expired_daemon_backoff_is_not_a_wall(st):
    _daemon_429(st, retry_after=None, backoff_s=1800.0)
    assert health_report.auth_wall(NOW + 1801) is None


def test_a_non_429_status_is_not_a_wall(st):
    (st / "auth_status.json").write_text(json.dumps({"stage": "AUTH_FAIL", "code": 401, "ts": NOW}))
    assert health_report.auth_wall(NOW) is None


# -------------------------------------------------------------------------------- fail-closed

def test_a_corrupt_backoff_record_reports_a_wall_with_no_expiry(st):
    """auth_backoff fails CLOSED on an unreadable record; this report must not fail OPEN behind it."""
    (st / "auth_backoff.json").write_text("{not json")
    w = health_report.auth_wall(NOW)
    assert w is not None and w["cls"] == "CORRUPT_STATE" and w["until"] is None
    assert "no expiry recorded at all" in health_report.wall_line(w)
    assert "no expiry recorded at all" in health_report.operator_line(NOW)


def test_no_state_at_all_is_no_wall(st):
    assert health_report.auth_wall(NOW) is None
    assert health_report.wall_line(None) == "**auth wall** none — /authentication is not refusing"


def test_the_backoff_file_wins_over_the_daemon_status(st):
    """auth_backoff.json keeps the body and the header; auth_status.json keeps neither."""
    _daemon_429(st, retry_after=None)
    _backoff_record(st, "BIOMETRICS_THROTTLED", None, NOW + 1800)
    assert health_report.auth_wall(NOW)["cls"] == "BIOMETRICS_THROTTLED"


# ------------------------------------------------- the daemon's restart-surviving mint wall

def _mint_wall(st, why, until):
    (st / "auth_mint_wall.json").write_text(json.dumps({"until": until, "why": why, "ts": NOW}))


def test_the_mint_wall_supplies_the_class_the_status_file_lacks(st):
    """/opt/wq/state/auth_mint_wall.json records `why`. Missing it was why the live VPS report
    could only ever say UNRECORDED while the class was sitting in the next file along."""
    _mint_wall(st, "BIOMETRICS_THROTTLED", NOW + 1445)
    _daemon_429(st, retry_after=None)
    w = health_report.auth_wall(NOW)
    assert w["cls"] == "BIOMETRICS_THROTTLED"
    assert w["source"] == "auth-daemon"
    assert "BIOMETRICS_THROTTLED" in health_report.wall_line(w)


def test_retry_after_has_three_states_not_two(st):
    """PRESENT / ABSENT / NOT RECORDED. Collapsing the last two would turn a hole in our logging
    into a claim about what the server sent."""
    _mint_wall(st, "BIOMETRICS_THROTTLED", NOW + 1445)
    not_recorded = health_report.wall_line(health_report.auth_wall(NOW))

    _daemon_429(st, retry_after=None)
    absent = health_report.wall_line(health_report.auth_wall(NOW))

    _daemon_429(st, retry_after=7.0)
    present = health_report.wall_line(health_report.auth_wall(NOW))

    assert "Retry-After NOT RECORDED" in not_recorded
    assert "Retry-After ABSENT" in absent
    assert "Retry-After PRESENT (7.0s)" in present
    assert len({not_recorded, absent, present}) == 3


def test_a_lapsed_mint_wall_falls_through_to_the_status_file(st):
    _mint_wall(st, "BIOMETRICS_THROTTLED", NOW - 1)
    _daemon_429(st, retry_after=None, backoff_s=1800.0)
    assert health_report.auth_wall(NOW)["cls"] == "UNRECORDED"


# ------------------------------------------------------------------- the one line for a phone

def test_operator_line_has_three_distinguishable_outcomes(st):
    _backoff_record(st, "RATE_LIMIT", 7.0, NOW + 7)
    known = health_report.operator_line(NOW)

    _backoff_record(st, "BIOMETRICS_THROTTLED", None, NOW + 1800)
    unknown = health_report.operator_line(NOW)

    (st / "auth_backoff.json").unlink()
    (st / "auth_status.json").write_text(json.dumps({"stage": "await_biometric", "ts": NOW}))
    (st / "persona_url.txt").write_text("https://example.invalid/inquiry")
    tap = health_report.operator_line()

    assert "lifts" in known and "server said so" in known
    assert "no known expiry" in unknown and "guess, not a lift" in unknown
    assert "TAP NOW" in tap
    assert len({known, unknown, tap}) == 3


def test_operator_line_never_says_tap_while_a_wall_is_up(st):
    (st / "persona_url.txt").write_text("https://example.invalid/inquiry")
    _backoff_record(st, "BIOMETRICS_THROTTLED", None, NOW + 1800)
    line = health_report.operator_line(NOW)
    assert "TAP" not in line.upper().replace("TAP.", "")
    assert "Nothing to tap" in line


def test_a_stale_link_is_not_offered_as_tappable(st):
    """The failure this exists for: an armed URL long past its window reads as an action."""
    p = st / "persona_url.txt"
    p.write_text("https://example.invalid/inquiry")
    import os
    old = NOW - 4 * 3600
    os.utime(p, (old, old))
    line = health_report.operator_line(NOW)
    assert "TAP NOW" not in line
    assert "240m old" in line


def test_authed_needs_no_action(st):
    (st / "auth_status.json").write_text(json.dumps({"stage": "AUTHED", "ts": NOW}))
    assert "AUTHED" in health_report.operator_line(NOW)


def test_no_link_and_no_wall_is_reported_as_a_stopped_flow(st):
    (st / "auth_status.json").write_text(json.dumps({"stage": "AUTH_FAIL", "code": 401, "ts": NOW}))
    assert "no link armed" in health_report.operator_line(NOW)


# -------------------------------------------------------------------- the whole report body

def test_build_is_not_healthy_while_a_wall_is_up(st):
    """AUTHED + a fresh journal used to be enough for a green light. A walled endpoint means the
    next re-auth cannot happen, so it is not healthy however good the journal looks."""
    import time as _t
    (st / "auth_status.json").write_text(json.dumps({"stage": "AUTHED", "ts": _t.time()}))
    (st / "resim_results.jsonl").write_text("{}\n")
    _backoff_record(st, "BIOMETRICS_THROTTLED", None, _t.time() + 1800)
    text, healthy = health_report.build()
    assert healthy is False
    assert "BIOMETRICS_THROTTLED" in text
    assert "expiry UNKNOWN" in text


# ------------------------------------------------------------ auth_link must not mint into a wall

def test_auth_link_refuses_before_it_kills_the_armed_flow(st, monkeypatch):
    """The defect: auth_link.py pkills auth_only.py and unlinks persona_url.txt BEFORE anything
    consults the wall. auth_only.py then guards and declines to POST, so the run ends with
    "produced no URL in 120s" -- and the previous, possibly still tappable, link is gone with no
    reason given. The wall must be read first and nothing may be touched."""
    import auth_link

    import time as _t
    url = st / "persona_url.txt"
    url.write_text("https://example.invalid/inquiry")
    _backoff_record(st, "BIOMETRICS_THROTTLED", None, _t.time() + 1800)

    monkeypatch.setattr(auth_link, "URL", url)
    monkeypatch.setattr(auth_link, "authed", lambda: pytest.fail("probed the network while walled"))
    monkeypatch.setattr(auth_link.subprocess, "run",
                        lambda *a, **k: pytest.fail(f"ran {a[0]!r} while walled"))
    monkeypatch.setattr(auth_link.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("started auth_only.py while walled"))
    monkeypatch.setattr(sys, "argv", ["auth_link.py"])

    assert auth_link.main() == 4
    assert url.exists(), "the armed link was destroyed by a run that could not mint a new one"
