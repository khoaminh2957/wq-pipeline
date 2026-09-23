#!/usr/bin/env python3
"""test_gate_gap.py — anchor the v4 baseline-selection metric to ground-truth cases (harness Round-1 static battery)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gate_gap as GG


def _row(sharpe=None, fitness=None, turnover=None, checks=None):
    return {"old_id": "t", "sharpe": sharpe, "fitness": fitness, "turnover": turnover, "checks": checks or []}


def test_full_passer_is_zero():
    r = _row(1.7, 1.2, 0.1, [
        {"name": "LOW_SHARPE", "result": "PASS", "value": 1.7},
        {"name": "LOW_2Y_SHARPE", "result": "PASS", "value": 1.9},
        {"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS"},
        {"name": "CONCENTRATED_WEIGHT", "result": "PASS"},
        {"name": "LOW_FITNESS", "result": "PASS", "value": 1.2},
        {"name": "HT_HIGH_TURNOVER_RETURNS_RATIO", "result": "PASS"}])
    d = GG.gate_distance(r)
    assert d == (0.0, 0.0), d


def test_9q7Z9N02_fitness_binding():
    """The rejected submit: all sharpe gates PASS, fitness 0.52 -> binding shortfall 0.48."""
    r = _row(1.61, 0.52, 0.3803, [
        {"name": "LOW_SHARPE", "result": "PASS", "value": 1.61},
        {"name": "LOW_2Y_SHARPE", "result": "PASS", "value": 2.11},
        {"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS"},
        {"name": "CONCENTRATED_WEIGHT", "result": "PASS"},
        {"name": "LOW_FITNESS", "result": "WARNING", "value": 0.52, "limit": 1.0},
        {"name": "HT_HIGH_TURNOVER_RETURNS_RATIO", "result": "PASS"}])
    g = GG.gate_gaps(r)
    assert abs(g["LOW_FITNESS"] - 0.48) < 1e-9, g
    assert max(g, key=g.get) == "LOW_FITNESS"


def test_chn_row_not_mistaken_for_passer():
    """CHN semantics: LOW_SHARPE FAIL at value 1.78 (regional bar higher) must NOT score 0."""
    r = _row(1.78, 2.1, 0.05, [
        {"name": "LOW_SHARPE", "result": "FAIL", "value": 1.78, "limit": 2.0},
        {"name": "LOW_2Y_SHARPE", "result": "PASS", "value": 2.5}])
    g = GG.gate_gaps(r)
    assert g["LOW_SHARPE"] > 0, g


def test_missing_checks_not_free_pass():
    """No checks at all: judged from raw metrics; theme unknown = 0.5 (never counts as pass)."""
    r = _row(1.2, 0.5, 0.3, [])
    g = GG.gate_gaps(r)
    assert g["LOW_SHARPE"] > 0 and g["LOW_FITNESS"] > 0
    assert g["THEME_RETURNS_RATIO"] == 0.5


def test_pick_baseline_prefers_closest_not_highest_sharpe():
    close = _row(1.45, 0.9, 0.1, [{"name": "LOW_SHARPE", "result": "WARNING", "value": 1.45, "limit": 1.58},
                                  {"name": "LOW_2Y_SHARPE", "result": "PASS", "value": 1.6},
                                  {"name": "LOW_FITNESS", "result": "WARNING", "value": 0.9, "limit": 1.0},
                                  {"name": "HT_HIGH_TURNOVER_RETURNS_RATIO", "result": "PASS"}])
    close["old_id"] = "close"
    flashy = _row(2.5, 0.2, 0.5, [{"name": "LOW_SHARPE", "result": "PASS", "value": 2.5},
                                  {"name": "LOW_2Y_SHARPE", "result": "PASS", "value": 2.2},
                                  {"name": "LOW_FITNESS", "result": "FAIL", "value": 0.2, "limit": 1.0},
                                  {"name": "HT_HIGH_TURNOVER_RETURNS_RATIO", "result": "PASS"}])
    flashy["old_id"] = "flashy"
    best, dist = GG.pick_baseline([flashy, close])
    assert best["old_id"] == "close", (best["old_id"], dist)


def test_turnover_hard_guard():
    r = _row(1.7, 1.1, 0.75, [])
    assert GG.gate_gaps(r)["HIGH_TURNOVER"] == 1.0


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted({k: v for k, v in globals().items() if k.startswith("test_")}.items()):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            fails += 1; print(f"FAIL {name}: {e}")
    print(f"\n{'ALL PASS' if not fails else f'{fails} FAIL'}")
    sys.exit(1 if fails else 0)
