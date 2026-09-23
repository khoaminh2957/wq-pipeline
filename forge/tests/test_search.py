import json

from forge import search as SR


def _row(alpha, tag, sharpe, hyp="c1", region="GLB", ok=False):
    ck = [{"name": "LOW_SHARPE", "result": "PASS" if ok else "FAIL", "limit": 1.58, "value": sharpe},
          {"name": "LOW_FITNESS", "result": "PASS" if ok else "FAIL", "limit": 1.0, "value": 1.2},
          {"name": "LOW_TURNOVER", "result": "PASS"}, {"name": "CONCENTRATED_WEIGHT", "result": "PASS"}]
    return {"alpha": alpha, "status": "COMPLETE", "sharpe": sharpe, "turnover": 0.05, "checks": ck,
            "settings": {"region": region, "delay": 1}, "meta": {"forge": 1, "recipe": tag, "hypothesis": hyp, "category": "Fundamental"}}


def test_round_summary_and_stop_condition(tmp_path):
    j = tmp_path / "forge.jsonl"
    rows = [_row("A", "R1", 0.8), _row("B", "R1", 1.2), _row("C", "R1", 1.7, ok=True), _row("D", "R2", 0.1),
            {"status": "PARENT-POSTED", "meta": {"recipe": "R1"}}, {"alpha": "E", "meta": {"forge": 1}, "sharpe": 3}]
    j.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    s = SR.round_summary("R1", j)
    assert s["rows"] == 3 and s["landed"] == 3 and s["passes"] == 1 and s["pass_alphas"] == ["C"]
    assert s["sharpe_p50"] == 1.2 and s["sharpe_max"] == 1.7
    assert s["best_cells"][0]["cell"] == "c1 GLB/d1 Fundamental" and s["best_cells"][0]["n"] == 3
    assert SR.round_summary("R2", j)["passes"] == 0
    assert SR.already_ran("R1", j, tmp_path / "none.jsonl") and not SR.already_ran("R3", j, tmp_path / "none.jsonl")
    res = tmp_path / "res.jsonl"
    res.write_text(json.dumps({"tag": "R3", "landed": 0}) + "\n")
    assert SR.already_ran("R3", j, res)


def test_recipes_are_well_formed():
    tags = [r["tag"] for r in SR.RECIPES]
    assert len(tags) == len(set(tags)) and all(r["n"] > 0 and "--mode composites" in r["args"] for r in SR.RECIPES)
    assert sum(r["n"] for r in SR.RECIPES) <= 3000
