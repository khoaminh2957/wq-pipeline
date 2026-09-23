import random

from forge import cells as C
from forge import grammar as GR
from forge import typed as T


def _lab(i, domain, kind, unit, sign, time="daily", sparsity="dense", structure="MATRIX", cat="Fundamental", users=0, ds="fnd"):
    return {"id": i, "domain": domain, "kind": kind, "unit": unit, "sign": sign, "time": time, "sparsity": sparsity,
            "structure": structure, "category": cat, "users": users, "dataset": ds, "regions": ["USA/d1"], "sign_source": "domain-prior"}


LABS = {x["id"]: x for x in [
    _lab("op_inc", "profitability", "level", "currency", "+", time="quarterly", sparsity="medium"),
    _lab("cfo", "cashflow", "level", "currency", "+", time="quarterly", sparsity="medium"),
    _lab("assets", "size", "level", "currency", "unstated", time="quarterly", sparsity="medium"),
    _lab("equity", "size", "level", "currency", "unstated", time="quarterly", sparsity="medium"),
    _lab("short_q", "short-flow", "level", "shares", "-", cat="Short Interest", ds="short"),
    _lab("vol_q", "volume-activity", "level", "shares", "unstated", cat="Price Volume", ds="pv"),
    _lab("sent", "sentiment", "score", "score", "+", cat="Sentiment", ds="snt"),
    _lab("news_sent", "sentiment", "score", "score", "+", structure="VECTOR", cat="News", ds="nws"),
    _lab("beta", "risk-factor", "coefficient", "unitless", "unstated", cat="Risk"),
    _lab("turn", "volume-activity", "ratio", "ratio", "unstated", cat="Price Volume", ds="pv"),
]}
CELL = C.Cell("USA", 1, "Short Interest", "TOP3000", 2, 1, 1.1, 10, (), 1.1)


def test_every_generated_candidate_passes_the_judge_and_serves_the_cell():
    rng = random.Random(3)
    res = GR.expand(LABS, CELL, rng, max_candidates=30, groups=["sector", "industry"])
    assert res["refused"] == 0, res["reasons"]
    assert len(res["candidates"]) >= 10
    for c in res["candidates"]:
        v = T.judge(c["formula"], LABS)
        assert v["ok"] and v["type"]["sign"] == 1
        assert c["meta"]["arm"] == "typed" and c["meta"]["hypothesis"].startswith("typed:")
        assert "short_q" in c["meta"]["legs"]                      # the only field that fills Short Interest
        assert len(set(c["meta"]["families"])) == len(c["meta"]["families"])   # distinct domains
        assert "short_q / vol_q" in c["formula"]                    # a share level is scaled by a share level
    kinds = {c["meta"]["combiner"] for c in res["candidates"]}
    assert "multiply" in kinds


def test_pool_roles():
    p = GR.Pool(LABS, "USA", 1)
    assert {v["id"] for v in p.directional} == {"op_inc", "cfo", "short_q", "sent", "news_sent"}
    assert {v["id"] for v in p.gates} >= {"vol_q", "turn"} and "beta" not in {v["id"] for v in p.directional}
    assert {v["id"] for v in p.scales["currency"]} == {"assets", "equity"}


def test_no_field_serving_the_cell_gives_nothing():
    cell = C.Cell("USA", 1, "Option", "TOP3000", 2, 1, 1.1, 10, (), 1.1)
    assert GR.expand(LABS, cell, random.Random(1), groups=["sector"])["candidates"] == []
