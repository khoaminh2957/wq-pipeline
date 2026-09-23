import pytest

from forge import score as SC


def _row(**kw):
    ck = [{"name": "LOW_SHARPE", "result": "PASS", "limit": 1.58, "value": 2.1},
          {"name": "LOW_FITNESS", "result": "PASS", "limit": 1.0, "value": 1.3},
          {"name": "LOW_TURNOVER", "result": "PASS", "limit": 0.01, "value": 0.12},
          {"name": "HIGH_TURNOVER", "result": "PASS", "limit": 0.7, "value": 0.12},
          {"name": "CONCENTRATED_WEIGHT", "result": "PASS"},
          {"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS", "limit": 1.4, "value": 1.7},
          {"name": "IS_LADDER_SHARPE", "result": "PASS", "limit": 2.02, "value": 2.3},
          {"name": "SELF_CORRELATION", "result": "PENDING"},
          {"name": "PROD_CORRELATION", "result": "PENDING"},
          {"name": "MATCHES_PYRAMID", "result": "PASS", "pyramids": [{"name": "USA/D1/NEWS", "multiplier": 1.2}]},
          {"name": "MATCHES_COMPETITION", "result": "FAIL"}]
    row = {"alpha": "A", "checks": ck, "sharpe": 2.1, "fitness": 1.3, "turnover": 0.12, "drawdown": 0.08}
    row.update(kw)
    return row


def test_platform_pass_ignores_non_binding():
    assert SC.platform_verdict(_row()) == ("pass", [])
    assert SC.pyramids_of(_row()) == [{"name": "USA/D1/NEWS", "multiplier": 1.2}]
    assert SC.platform_verdict({"alpha": "x"}) == ("incomplete", [])


def test_platform_fail_and_warning():
    r = _row()
    r["checks"][0]["result"] = "FAIL"
    assert SC.platform_verdict(r) == ("fail", ["LOW_SHARPE"])
    r = _row()
    r["checks"][4]["result"] = "WARNING"
    assert SC.platform_verdict(r) == ("fail", ["CONCENTRATED_WEIGHT"])
    r = _row()
    r["checks"][0]["result"] = "WARNING"            # Sharpe just under the line: WARNING is not PASS
    assert SC.platform_verdict(r) == ("fail", ["LOW_SHARPE"])
    r = _row()
    r["checks"][10]["result"] = "WARNING"           # a non-binding check may warn freely
    assert SC.platform_verdict(r) == ("pass", [])
    r = _row()
    r["checks"][6]["result"] = "PENDING"            # a binding check not yet graded -> incomplete
    assert SC.platform_verdict(r) == ("incomplete", [])
    r = _row()
    r["checks"].append({"name": "REGULAR_SUBMISSION", "result": "PENDING"})   # the aggregate: never binding
    assert SC.platform_verdict(r) == ("pass", [])


def test_turnover_band():
    assert SC.turnover_verdict(_row(turnover=0.12)) == "ok"
    assert SC.turnover_verdict(_row(turnover=0.40)) == "decay-retry"
    assert SC.turnover_verdict(_row(turnover=0.015)) == "ok"          # platform LOW_TURNOVER passes -> C14
    low = _row(turnover=0.005)
    low["checks"][2]["result"] = "FAIL"
    assert SC.turnover_verdict(low) == "low"
    assert SC.turnover_verdict({"alpha": "x"}) == "unknown"


def test_stage_progression():
    assert SC.stage(_row())["stage"] == "needs-dsr"
    assert SC.stage(_row(turnover=0.5))["stage"] == "turnover-decay-retry"
    st = SC.stage(_row(), {"ok": True, "dsr": 0.97})
    assert st["stage"] == "candidate" and st["dsr"] == 0.97 and st["pyramids"] == ["USA/D1/NEWS"]
    assert SC.stage(_row(), {"ok": True, "dsr": 0.80})["stage"] == "dsr-fail"
    assert SC.stage(_row(), {"ok": False, "reason": "short"})["stage"] == "dsr-unscored"
    bad = _row()
    bad["checks"][1]["result"] = "FAIL"
    assert SC.stage(bad)["stage"] == "fail" and SC.stage(bad)["failed"] == ["LOW_FITNESS"]
    assert SC.stage({"alpha": "x"})["stage"] == "incomplete"


def test_limit_ratio_and_score_ordering():
    assert SC.limit_ratio(_row(), "IS_LADDER_SHARPE") == pytest.approx(2.3 / 2.02)
    assert SC.limit_ratio(_row(), "SELF_CORRELATION") is None
    good = SC.robust_score(_row(), {"ok": True, "dsr": 0.99}, dataset_load=0, op_count=3)
    crowded = SC.robust_score(_row(), {"ok": True, "dsr": 0.99}, dataset_load=114, op_count=3)
    complex_ = SC.robust_score(_row(), {"ok": True, "dsr": 0.99}, dataset_load=0, op_count=18)
    weak = SC.robust_score(_row(drawdown=0.5), {"ok": True, "dsr": 0.96}, dataset_load=0, op_count=3)
    assert good > crowded and good > complex_ and good > weak
    assert 0.0 <= good <= 1.0


def test_second_best_rule():
    assert SC.second_best([]) is None
    assert SC.second_best([(0.9, "a")]) == "a"
    assert SC.second_best([(0.90, "a"), (0.85, "b"), (0.5, "c")]) == "b"      # within 10% -> #2
    assert SC.second_best([(0.90, "a"), (0.70, "b")]) == "a"                  # clear winner stays
