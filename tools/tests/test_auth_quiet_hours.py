"""Quiet hours on the auth daemon's mint timer (Khoa 2026-09-22).

His instruction: "cac khoang tu 1-6h se ko tu spam link va so link do de danh vao nhung truong hop
can thiet nhu hien tai cua toi" -- between 01:00 and 06:00 local the TIMER mints nothing, and the
links it would have spent stay in the day's budget for a mint he asks for himself.

OFFLINE BY CONSTRUCTION: the module is loaded from its path and only the two pure time functions
plus `mint_gap` are exercised. Nothing here touches the network, the state files, or the daemon loop.
"""

import importlib.util
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def authd():
    spec = importlib.util.spec_from_file_location("authd_under_test", ROOT / "vps/auth_daemon.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _local(h, minute=0, sec=0):
    """A local-time epoch for today at h:mm:ss, so the test reads the same clock the daemon does."""
    t = time.localtime()
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, h, minute, sec, 0, 0, -1))


@pytest.mark.parametrize("hour, quiet", [(0, False), (1, True), (2, True), (5, True), (6, False),
                                         (7, False), (12, False), (23, False)])
def test_the_quiet_window_is_01_to_06_local_half_open(authd, hour, quiet):
    assert authd.in_quiet_hours(_local(hour)) is quiet


def test_the_timer_sleeps_to_the_end_of_the_window_rather_than_minting(authd):
    # inside the window the gap is the distance to 06:00, so no mint can fall inside it
    assert authd.mint_gap(_local(1)) == pytest.approx(5 * 3600, abs=1)
    assert authd.mint_gap(_local(3, 30)) == pytest.approx(2.5 * 3600, abs=1)
    assert authd.mint_gap(_local(5, 59, 0)) == pytest.approx(60, abs=1)


def test_outside_the_window_the_budget_rule_is_untouched(authd):
    # 06:00 and 00:59 both return the ordinary budget-derived gap, never the quiet-hour distance
    for t in (_local(0, 59), _local(6, 0), _local(13, 0)):
        assert authd.mint_gap(t) >= authd.MIN_MINT_GAP_S
        assert authd.mint_gap(t) != pytest.approx(authd.seconds_to_quiet_end(t), abs=1) or not authd.in_quiet_hours(t)


def test_the_gap_never_returns_a_value_that_would_busy_loop(authd):
    for hour in range(24):
        assert authd.mint_gap(_local(hour)) >= 60.0


def test_seconds_to_quiet_end_counts_down_within_the_window(authd):
    assert authd.seconds_to_quiet_end(_local(1)) > authd.seconds_to_quiet_end(_local(4))
    assert authd.seconds_to_quiet_end(_local(5, 30)) == pytest.approx(1800, abs=1)


# ---------------------------------------------------------------- the rule must hold on EVERY path
# MEASURED 2026-09-23: the first version lived only in the daemon's mint_gap(), while the wq-mint.timer
# (every minute) and forge_loop.sh (every round) both mint through tools/mint_link.py. 8 routine mints
# happened overnight against at most 4 the rule allows.

@pytest.fixture(scope="module")
def ml():
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import mint_link
    return mint_link


def test_the_two_copies_of_the_quiet_window_can_never_drift_apart(authd, ml):
    assert (ml.QUIET_START_H, ml.QUIET_END_H) == (authd.QUIET_START_H, authd.QUIET_END_H)
    for h in range(24):
        assert ml.in_quiet_hours(_local(h)) == authd.in_quiet_hours(_local(h))


def test_a_routine_mint_inside_quiet_hours_is_refused_before_the_hourly_gate(ml, monkeypatch):
    """Refused BEFORE OB_GATE: a refusal after taking the gate burns the hour for every other minter."""
    gate_taken = []
    monkeypatch.setattr(ml, "session_live", lambda: False)          # session dead: the urgent case
    monkeypatch.setattr(ml, "live_link", lambda: None)
    monkeypatch.setattr(ml, "in_quiet_hours", lambda now=None: True)
    monkeypatch.setattr(ml, "OB_GATE", lambda: gate_taken.append(1) or True)
    assert ml.mint(force=False, quiet=True) == 0
    assert gate_taken == []


class _StopHere(Exception):
    """Raised at the first step AFTER the quiet-hours check, so the test proves the force path got past
    it and then goes no further. The first draft let the flow continue: it reached the code that reads
    /root/.wqbrain_creds -- absent on the MacBook, PRESENT on the VPS, where the same test would have
    gone on to a real authentication POST."""


def test_the_operator_force_path_ignores_quiet_hours(ml, monkeypatch):
    """Khoa's whole point: the saved links are FOR the 3 a.m. case when he asks for one."""
    def stop(*a, **k):
        raise _StopHere
    monkeypatch.setattr(ml, "session_live", lambda: False)
    monkeypatch.setattr(ml, "live_link", lambda: None)
    monkeypatch.setattr(ml, "in_quiet_hours", lambda now=None: True)
    monkeypatch.setattr(ml, "OB_GATE", lambda: True)
    monkeypatch.setattr(ml, "budget_left", stop)        # the step right after the quiet-hours check
    with pytest.raises(_StopHere):
        ml.mint(force=True, quiet=True)
