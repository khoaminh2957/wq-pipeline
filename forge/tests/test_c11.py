import json
from forge.offline import c11_neut as X


def _row(a, sharpe, neut="INDUSTRY", formula=None, recipe=None, arm=None, base=None, checks=None):
    meta = {"hypothesis": "options_x_short", "composite": 1, "category": "Short Interest"}
    if recipe:
        meta.update(recipe=recipe, arm=arm, base_alpha=base, base_sharpe=1.7)
    return {"alpha": a, "formula": formula or "multiply(rank(iv_%s), rank(short_%s))" % (a, a), "sharpe": sharpe, "fitness": 1.1,
            "turnover": 0.14, "status": "COMPLETE", "meta": meta, "checks": checks or [],
            "settings": {"region": "USA", "delay": 1, "neutralization": neut, "decay": 4, "truncation": 0.08}}


def test_variants_arms_and_settings(tmp_path):
    rows = {a: _row(a, 1.7 + i * 0.01, neut="STATISTICAL" if a == "883KgXXm" else "INDUSTRY") for i, a in enumerate(X.BASES)}
    rows["kqVbg1xP"] = _row("kqVbg1xP", 2.0, formula="KQ")
    rows["vRk095rv"] = _row("vRk095rv", 1.85, formula="VR")
    cons = X.variants(rows, {"KQ": rows["kqVbg1xP"], "VR": rows["vRk095rv"]})
    by = {}
    for c in cons:
        by[c["meta"]["arm"]] = by.get(c["meta"]["arm"], 0) + 1
    assert by == {"R": 16, "RS": 16, "RV": 16, "S": 12} and len(cons) == 60
    r = next(c for c in cons if c["meta"]["arm"] == "R")
    assert r["formula"] == "vector_neut(%s, KQ)" % rows[r["meta"]["base_alpha"]]["formula"]
    assert r["settings"]["neutralization"] == "INDUSTRY"
    rv = next(c for c in cons if c["meta"]["arm"] == "RV")
    assert rv["formula"].startswith("vector_neut(vector_neut(") and rv["formula"].endswith(", KQ), VR)")
    only = X.variants(rows, {"KQ": rows["kqVbg1xP"], "VR": rows["vRk095rv"]}, arms=("R", "RS", "RV"))
    assert len(only) == 48 and not any(c["meta"]["arm"] == "S" for c in only)
    assert all(c["settings"]["neutralization"] == "STATISTICAL" for c in cons if c["meta"]["arm"] in ("RS", "S"))
    assert all(c["meta"]["base_alpha"] != "883KgXXm" for c in cons if c["meta"]["arm"] == "S")   # already STATISTICAL
    assert all(c["meta"]["recipe"] == "C11" for c in cons)


def test_report_reads_arms_and_lives(tmp_path):
    ok = [{"name": "LOW_SHARPE", "result": "PASS"}]
    j = tmp_path / "j.jsonl"
    j.write_text("\n".join(json.dumps(r) for r in [
        _row("aaa", 0.4, recipe="C11", arm="R", base="ZY0Zowe1", checks=[{"name": "LOW_SHARPE", "result": "FAIL"}]),
        _row("bbb", 1.9, recipe="C11", arm="S", base="akLMOLZW", checks=ok),
        _row("ccc", 1.9, recipe="C11", arm="S", base="om6AY6Ml", checks=ok),
        _row("zzz", 1.9)]) + "\n")
    c = tmp_path / "c.jsonl"
    c.write_text("\n".join(json.dumps(r) for r in [
        {"alpha": "bbb", "prod": 0.55, "self": 0.4}, {"alpha": "ccc", "prod": 0.85, "self": 0.85}]) + "\n")
    rep = X.report(journal=j, corr=c)
    assert rep["rows"] == 3 and set(rep["arms"]) == {"R", "S"}
    assert rep["arms"]["R"]["platform_pass"] == 0 and rep["arms"]["R"]["lives"] == []
    s = rep["arms"]["S"]
    assert s["n"] == 2 and s["corr_read"] == 2 and s["lives"] == ["bbb"] and s["delta_vs_base_p50"] == 0.2
