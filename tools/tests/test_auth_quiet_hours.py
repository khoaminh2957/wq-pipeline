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
