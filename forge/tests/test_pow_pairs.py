import json

from forge.offline import pow_pairs as P


def _row(alpha, hyp, sharpe, formula, neut="SUBINDUSTRY", fitness=0.8, returns=0.04, turnover=0.15, recipe=None, ladder=("FAIL", 2)):
    checks = [{"name": "LOW_SHARPE", "result": "PASS" if sharpe >= 1.58 else "FAIL", "limit": 1.58, "value": sharpe},
              {"name": "LOW_FITNESS", "result": "PASS" if fitness >= 1 else "FAIL"}, {"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS"},
              {"name": "IS_LADDER_SHARPE", "result": ladder[0], "year": ladder[1], "limit": 1.58},
              {"name": "CONCENTRATED_WEIGHT", "result": "PASS"}, {"name": "LOW_TURNOVER", "result": "PASS"}, {"name": "HIGH_TURNOVER", "result": "PASS"}]
    meta = {"forge": 1, "hypothesis": hyp, "category": "Short Interest", "arm": "current", "mechanism_key": hyp + "#k"}
    if recipe:
        meta["recipe"] = recipe
    return {"alpha": alpha, "status": "COMPLETE", "formula": formula, "sharpe": sharpe, "fitness": fitness, "returns": returns,
            "turnover": turnover, "checks": checks, "meta": meta,
            "settings": {"region": "USA", "delay": 1, "neutralization": neut, "decay": 8, "truncation": 0.08, "universe": "TOP3000"}}


def _journal(tmp_path, rows):
    p = tmp_path / "forge.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def test_base_rows_select_per_stratum_and_skip_wrapped_low_and_duplicate_rows(tmp_path):
    rows = [_row("a1", "usa_short_x_profitability_x_accruals", 1.7, "multiply(x, y)"),
            _row("a2", "usa_short_x_profitability_x_accruals", 1.7, "multiply(x, y)"),                 # duplicate construction
            _row("a3", "usa_short_x_profitability_x_accruals", 1.2, "multiply(x, z)"),                 # under MIN_SHARPE
            _row("a4", "usa_short_x_profitability_x_accruals", 1.9, "signed_power(multiply(x, w), 2)"),  # already wrapped
            _row("b1", "options_x_short", 1.8, "multiply(o, s)", neut="STATISTICAL"),
            _row("b2", "options_x_short", 1.9, "multiply(o, t)", neut="INDUSTRY"),                    # wrong neutralisation for the stratum
            _row("c1", "ravenpack_x_short", 1.6, "multiply(r, s)"),
            _row("d1", "some_other", 2.0, "multiply(p, q)")]
    got = P.base_rows(_journal(tmp_path, rows))
    assert [r["alpha"] for r in got] == ["a1", "b1", "c1"]
    tw = P.twins(got)
    assert len(tw) == 6
    assert tw[0]["formula"] == "signed_power(multiply(x, y), 1.5)" and tw[1]["formula"] == "signed_power(multiply(x, y), 2)"
    m = tw[1]["meta"]
    assert m["recipe"] == "POW" and m["arm"] == "pow2" and m["base_alpha"] == "a1" and m["base_sharpe"] == 1.7
    assert m["cand"] != got[0]["meta"].get("cand") and tw[0]["meta"]["cand"] != tw[1]["meta"]["cand"]
    assert tw[0]["settings"] == got[0]["settings"]


def test_report_pairs_twins_with_their_base_rows(tmp_path):
    base = _row("a1", "usa_short_x_profitability_x_accruals", 1.7, "multiply(x, y)", fitness=0.9, returns=0.04, turnover=0.10)
    twin = _row("t1", "usa_short_x_profitability_x_accruals", 1.65, "signed_power(multiply(x, y), 2)", fitness=1.02, returns=0.048,
                turnover=0.11, ladder=("FAIL", 3))
    twin["meta"].update({"recipe": "POW", "arm": "pow2", "base_alpha": "a1"})
    orphan = dict(_row("t2", "options_x_short", 1.5, "signed_power(q, 2)"), meta=dict(twin["meta"], base_alpha="missing"))
    rep = P.report(_journal(tmp_path, [base, twin, orphan]))
    s = rep["arms"]["pow2"]["all"]
    assert s["n"] == 1 and rep["arms"]["pow15"]["all"]["n"] == 0
    # sigma = |returns| / sharpe: 0.048/1.65 vs 0.04/1.7 -> +23.6 %
    assert abs(s["d_sigma_pct_p50"] - 23.6) < 0.2
    assert abs(s["d_sharpe_p50"] + 0.05) < 1e-9 and abs(s["d_fitness_p50"] - 0.12) < 1e-9
    assert (s["fit1_base"], s["fit1_twin"]) == (0, 1) and (s["y2_base"], s["y2_twin"]) == (0, 1)
