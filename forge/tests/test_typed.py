from forge import typed as T


def _lab(i, domain, kind, unit, sign, time="daily", sparsity="dense", structure="MATRIX"):
    return {"id": i, "domain": domain, "kind": kind, "unit": unit, "sign": sign, "time": time, "sparsity": sparsity, "structure": structure}


LABS = {x["id"]: x for x in [
    _lab("op_inc", "profitability", "level", "currency", "+", time="quarterly", sparsity="medium"),
    _lab("equity", "size", "level", "currency", "unstated", time="quarterly", sparsity="medium"),
    _lab("short_q", "short-flow", "level", "shares", "-"),
    _lab("vol_q", "volume-activity", "level", "shares", "unstated"),
    _lab("sent", "sentiment", "score", "score", "+"),
    _lab("news_code", "news", "code", "code", "unstated", structure="VECTOR"),
    _lab("news_cnt", "news", "count", "count", "unstated", structure="VECTOR"),
    _lab("beta", "risk-factor", "coefficient", "unitless", "unstated"),
    _lab("thin", "sentiment", "score", "score", "+", sparsity="sparse"),
    _lab("cfo", "cashflow", "level", "currency", "+", time="quarterly", sparsity="medium"),
    dict(_lab("hl_sent", "sentiment", "score", "score", "+", structure="VECTOR"), vec_role="event-value", vec_reducers=["vec_avg", "vec_max", "vec_min"], vec_after={"vec_avg": "score", "vec_max": "score", "vec_min": "score"}),
    dict(_lab("ev_code", "news", "code", "code", "unstated", structure="VECTOR"), vec_role="event-code", vec_reducers=["vec_count"], vec_after={"vec_count": "count"}),
    dict(_lab("dual", "insider-flow", "ratio", "ratio", "+"), by_region={"USA/d1": {"structure": "VECTOR", "coverage": 0.88, "sparsity": "medium"}}, vec_role="event-value", vec_reducers=["vec_avg"], vec_after={"vec_avg": "ratio"}),
    _lab("assets", "size", "level", "currency", "unstated", time="quarterly", sparsity="medium"),
]}


def test_income_minus_cashflow_is_accruals_with_sloan_sign():
    r = T.judge("1 - group_rank(ts_backfill((op_inc - cfo) / assets, 126), sector)", LABS)
    assert r["ok"], r["hard"]
    assert r["type"]["domains"] == ["accruals"] and r["type"]["sign"] == 1
    assert not T.judge("group_rank(ts_backfill((op_inc - cfo) / assets, 126), sector)", LABS)["ok"]      # wrong way up


def test_parser_handles_calls_infix_keywords_and_strings():
    n = T.parse('if_else(greater(rank(a), 0.8), add(x, 0, filter=true), 0)')
    assert n.op == "if_else" and n.args[1].op == "add" and "filter" in n.args[1].kw
    n = T.parse("(1 - group_rank(a / b, sector)) * rank(c)")
    assert n.op == "multiply" and n.args[0].op == "subtract" and n.args[0].args[1].op == "group_rank"
    n = T.parse('group_neutralize(x, bucket(rank(y), range="0,1,0.1"))')
    assert n.args[1].op == "bucket" and n.args[1].kw["range"].value == "0,1,0.1"


def test_good_two_leg_composite_passes_with_positive_orientation():
    f = "multiply(group_rank(ts_backfill(op_inc / equity, 126), sector), (1 - group_rank(ts_mean(short_q / vol_q, 20), sector)))"
    r = T.judge(f, LABS)
    assert r["ok"], r["hard"]
    assert r["type"]["sign"] == 1 and r["type"]["layer"] == 3 and r["soft"] >= 0.8
    assert set(r["type"]["domains"]) >= {"profitability", "short-flow"}


def test_h1_units():
    assert any(h.startswith("H1") for h in T.judge("rank(ts_backfill(op_inc / short_q, 126))", LABS)["hard"])
    assert any(h.startswith("H1") for h in T.judge("rank(ts_backfill(op_inc, 126) + short_q)", LABS)["hard"])


def test_h2_kinds():
    assert any(h.startswith("H2") for h in T.judge("rank(ts_delta(ts_backfill(op_inc / equity, 126), 5))", LABS)["hard"])
    assert any(h.startswith("H2") for h in T.judge("rank(vec_avg(news_code))", LABS)["hard"])


def test_h3_bounded():
    assert any(h.startswith("H3") for h in T.judge("multiply(ts_backfill(op_inc, 126), rank(sent))", LABS)["hard"])
    assert any(h.startswith("H3") for h in T.judge("if_else(greater(rank(vol_q), 0.5), ts_backfill(op_inc, 126), 0)", LABS)["hard"])


def test_h4_structure():
    assert any(h.startswith("H4") for h in T.judge("rank(news_cnt)", LABS)["hard"])                    # VECTOR outside vec_*
    assert any(h.startswith("H4") for h in T.judge("rank(op_inc / equity)", LABS)["hard"])            # quarterly, no backfill
    assert any(h.startswith("H4") for h in T.judge("rank(thin)", LABS)["hard"])                       # sparse, no density
    assert T.judge("rank(add(thin, 0, filter=true))", LABS)["ok"]


def test_h5_roles_and_h6_orientation():
    assert any(h.startswith("H5") for h in T.judge("rank(vol_q)", LABS)["hard"])                      # unstated sign, directional
    assert any(h.startswith("H5") for h in T.judge("rank(beta)", LABS)["hard"])                       # sign-free kind, directional
    ok = T.judge("if_else(greater(rank(vol_q), 0.8), rank(sent), 0)", LABS)                            # unstated sign as a gate
    assert ok["ok"] and ok["type"]["sign"] == 1
    neg = T.judge("group_rank(ts_mean(short_q / vol_q, 20), sector)", LABS)                            # a short leg the wrong way up
    assert any(h.startswith("H6") for h in neg["hard"])
    assert T.judge("1 - group_rank(ts_mean(short_q / vol_q, 20), sector)", LABS)["ok"]


def test_soft_score_rewards_layers_and_penalises_wasted_normalizer():
    a = T.judge("rank(sent)", LABS)["soft"]
    b = T.judge("multiply(rank(ts_mean(sent, 5)), 1 - group_rank(ts_mean(short_q / vol_q, 20), sector))", LABS)["soft"]
    c = T.judge("rank(rank(sent))", LABS)
    assert b > a and c["soft"] < T.judge("rank(sent)", LABS)["soft"]


def test_vector_reducers_and_region_structure():
    assert T.judge("rank(vec_avg(hl_sent))", LABS)["ok"]
    assert any("reducer" in h for h in T.judge("rank(vec_sum(hl_sent))", LABS)["hard"])            # a sum of scores is not meaningful
    g = T.judge("if_else(greater(rank(add(vec_count(ev_code), 0, filter=true)), 0.7), rank(sent), 0)", LABS)
    assert g["ok"], g["hard"]
    assert any(h.startswith("H2") for h in T.judge("rank(vec_avg(ev_code))", LABS)["hard"]) or not T.judge("rank(vec_avg(ev_code))", LABS)["ok"]
    assert T.judge("rank(dual)", LABS, region="EUR/d1")["ok"]                                       # MATRIX there
    assert any(h.startswith("H4") for h in T.judge("rank(dual)", LABS, region="USA/d1")["hard"])    # VECTOR here
    assert T.judge("rank(vec_avg(dual))", LABS, region="USA/d1")["ok"]


def test_structural_mode_keeps_units_kinds_structure_and_drops_sign_and_backfill_rules():
    ok = T.judge("group_rank(ts_rank((op_inc - cfo) / assets, 126), sector)", LABS, structural=True)        # no backfill, no sign check
    assert ok["ok"], ok["hard"]
    assert T.judge("rank(vol_q)", LABS, structural=True)["ok"]                                              # unstated sign is fine here
    assert T.judge("rank(unknown_field_zzz)", LABS, structural=True)["ok"]                                  # unlabelled passes through
    assert not T.judge("rank(op_inc / short_q)", LABS, structural=True)["ok"]                               # H1 still bites
    assert not T.judge("rank(ts_delta(op_inc / equity, 5))", LABS, structural=True)["ok"]                    # H2 still bites
    assert not T.judge("rank(news_cnt)", LABS, structural=True)["ok"]                                       # H4 vector still bites
    assert not T.judge("rank(thin)", LABS, structural=True)["ok"]                                           # H4 density still bites
