import pytest

from framelib import frames as FR
from framelib import taxonomy as TX


def ch(text, evidence=None):
    return TX.classify(FR.normalize(text), evidence)


@pytest.mark.parametrize("text,combiner,n_legs", [
    ("rank($1)", "SINGLE", 1),
    ("rank(ts_delta($1,5))", "SINGLE", 1),
    ("add(rank($1),zscore($2))", "SUM", 2),
    ("add(add(multiply(rank($1),0.5),multiply(rank($2),-0.3)),multiply(rank($3),0.2))", "WEIGHTED_SUM", 3),
    ("add(multiply(rank($1),0.5),rank($2))", "SUM", 2),
    ("rank(subtract($1,$2))", "SPREAD", 2),
    ("multiply(rank($1),rank($2))", "PRODUCT", 2),
    ("rank(divide($1,$2))", "RATIO", 2),
    ("ts_corr($1,$2,20)", "RELATION", 2),
    ("if_else(greater(volume,adv20),rank($1),rank($2))", "SWITCH", 2),
    ("max($1,$2)", "OTHER", 2),
    ("trade_when(greater(volume,adv20),rank($1),reverse(1))", "SINGLE", 1),
    ("rank(divide($1,cap))", "RATIO", 2),                     # a pinned field is a leg
])
def test_combiner(text, combiner, n_legs):
    c = ch(text)
    assert (c["combiner"], c["n_legs"]) == (combiner, n_legs)


@pytest.mark.parametrize("text,cond,cin", [
    ("rank($1)", "NONE", "NONE"),
    ("trade_when(greater(volume,adv20),rank($1),-1)", "TRADE_WHEN", "FIXED"),
    ("if_else(greater($1,0),rank($1),0.5)", "IF_ELSE", "SLOT"),
    ("if_else(greater($1,volume),rank($1),0.5)", "IF_ELSE", "MIXED"),
    ("if_else(greater(1,0),rank($1),0.5)", "IF_ELSE", "CONSTANT"),
    ("trade_when(greater(volume,adv20),if_else(greater(volume,1),rank($1),0.5),-1)", "MULTI", "FIXED"),
    ("trade_when(greater(volume,adv20),rank($1),greater($2,1))", "TRADE_WHEN", "MIXED"),   # exit holds a slot
])
def test_conditioning(text, cond, cin):
    c = ch(text)
    assert (c["conditioning"], c["condition_input"]) == (cond, cin)


@pytest.mark.parametrize("text,fn", [
    ("rank($1)", "LEVEL"),
    ("rank(ts_delta($1,5))", "CHANGE"),
    ("ts_std_dev(ts_delta($1,5),20)", "DISPERSION"),           # the outermost defining operator wins
    ("add(rank(ts_delta($1,5)),rank(ts_std_dev($2,20)))", "MIXED"),
    ("rank(divide(ts_delta($1,5),$2))", "CHANGE"),              # the denominator is a scale
    ("rank(ts_corr($1,$2,60))", "CO_MOVEMENT"),
    ("days_from_last_change($1)", "COUNT_TIMING"),
    ("trade_when(greater(ts_delta(volume,5),0),rank($1),-1)", "LEVEL"),   # conditions do not count
])
def test_economic_function(text, fn):
    assert ch(text)["economic_function"] == fn


@pytest.mark.parametrize("text,hz", [
    ("rank($1)", "NONE"), ("ts_delta($1,5)", "DAYS"), ("ts_delta($1,6)", "MONTH"), ("ts_mean($1,63)", "QUARTER"),
    ("ts_mean($1,252)", "YEAR"), ("ts_mean($1,253)", "MULTIYEAR"), ("add(ts_mean($1,5),ts_mean($2,120))", "YEAR"),
])
def test_horizon(text, hz):
    assert ch(text)["horizon"] == hz


def test_grouping():
    assert ch("group_rank($1,industry)")["grouping"] == "TOKEN"
    assert ch("group_rank($1,$2)")["grouping"] == "SLOT"
    assert ch("group_rank(group_rank($1,$2),sector)")["grouping"] == "BOTH"
    assert ch("rank($1)")["grouping"] == "NONE"


def test_turnover_class_is_per_cell_and_never_pooled():
    def ev(*meds):
        return {"cells": {"C%d" % i: {"turnover_median": m} for i, m in enumerate(meds)}}
    assert TX.turnover_class(None) == "UNKNOWN"
    assert TX.turnover_class(ev(0.05, 0.08)) == "LOW"
    assert TX.turnover_class(ev(0.05, 0.5)) == "MIXED"
    assert TX.turnover_class(ev(0.005)) == "BELOW_MIN"
    assert TX.turnover_class(ev(0.7)) == "ABOVE_MAX"
    assert ch("rank($1)", ev(0.2))["turnover_class"] == "MID"


def test_every_value_is_in_the_taxonomy_and_family_is_composed():
    for text in ("rank($1)", "if_else(greater(volume,adv20),rank(ts_delta($1,5)),rank($2))", "ts_corr($1,$2,300)"):
        c = ch(text)
        for dim, allowed in TX.DIMENSIONS.items():
            assert c[dim] in allowed
        assert c["family"] == "%s.%s.%s" % (c["combiner"], c["conditioning"], c["economic_function"])
    assert ch("add(vec_avg($1),group_rank($2,$3))")["slot_kinds"] == "GROUP*1+MATRIX*1+VECTOR*1"
