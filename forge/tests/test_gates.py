import json

from forge import gates as G
from forge import signature as S
from forge.factory import candidate_id


def _cand(formula, region="USA", delay=1, mech="h1"):
    settings = {"region": region, "universe": "TOP3000", "delay": delay, "neutralization": "INDUSTRY", "decay": 0, "truncation": 0.08}
    return {"id": candidate_id(formula, settings), "formula": formula, "settings": settings,
            "signature": S.signature(formula, region, delay, mechanism=mech)}


def test_gate_order_and_counts():
    idx = S.NoveltyIndex([S.signature("rank(ts_decay_linear(fnd6_x, 5))", "USA", 1)])
    g = G.PreSimGate(idx, budget=2)
    fresh = _cand("group_rank(ts_delta(news29_a, 5), industry)")
    assert g.check(fresh) == G.OK
    assert g.check(fresh) == G.DUPLICATE                      # same id, second time
    assert g.check(_cand("zscore(ts_backfill(fnd6_y, 3))")) == G.NOT_NOVEL
    assert g.check(_cand("rank(" * 63 + "x" + ")" * 63)) == G.TOO_MANY_OPS
    assert g.check(_cand("group_rank(ts_delta(news73_b, 5), industry)")) == G.OK
    assert g.check(_cand("group_rank(ts_delta(news51_c, 5), industry)")) == G.BUDGET
    assert g.counts == {G.OK: 2, G.NOT_NOVEL: 1, G.DUPLICATE: 1, G.TOO_MANY_OPS: 1, G.BUDGET: 1}


def test_journal_ids_and_filter(tmp_path):
    f = "group_rank(ts_delta(news29_a, 5), industry)"
    st = {"region": "USA", "universe": "TOP3000", "delay": 1, "neutralization": "INDUSTRY", "decay": 0, "truncation": 0.08}
    p = tmp_path / "climb.jsonl"
    p.write_text(json.dumps({"alpha": "A", "formula": f, "settings": st}) + "\nnot json\n" + json.dumps({"alpha": "B"}) + "\n")
    seen = G.journal_ids([tmp_path / "*.jsonl"])
    assert seen == {candidate_id(f, st)}
    g = G.PreSimGate(S.NoveltyIndex(), seen_ids=seen)
    kept = g.filter([_cand(f), _cand("group_rank(ts_delta(news29_a, 10), industry)")])
    assert len(kept) == 1 and kept[0]["formula"].endswith("10), industry)")
