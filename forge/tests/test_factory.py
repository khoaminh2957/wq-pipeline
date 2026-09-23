import random
import textwrap

import pytest

from forge import cells as C
from forge import factory as F
from forge import hypotheses as H

YAML = textwrap.dedent("""
    id: news_neg_v1
    category: News
    mechanism: negative news intensity spikes are underreacted to.
    sign: 1
    source: "EX-ANTE — Tetlock 2007"
    datasets: [news29, news73]
    signal:
      pattern: "neg|frontpage"
      vector: vec_avg
    template: "group_rank(ts_delta({signal}, {w}), {group})"
    params:
      w: [5, 10]
      group: [subindustry, industry]
    settings:
      neutralization: [SUBINDUSTRY, INDUSTRY]
      decay: [0, 4]
      truncation: 0.08
""")

ROWS = [
    {"id": "nws29_frontpage", "type": "VECTOR", "dataset": {"id": "news29"}, "category": {"name": "News"}},
    {"id": "nws73_negscore", "type": "MATRIX", "dataset": {"id": "news73"}, "category": {"name": "News"}},
    {"id": "nws73_posscore", "type": "MATRIX", "dataset": {"id": "news73"}, "category": {"name": "News"}},   # pattern miss
    {"id": "snt_neg", "type": "MATRIX", "dataset": {"id": "sentiment22"}, "category": {"name": "Sentiment"}},  # other category
    {"id": "nws99_neg", "type": "MATRIX", "dataset": {"id": "news99"}, "category": {"name": "News"}},         # dataset not listed
    {"id": "nws29_neg_grp", "type": "GROUP", "dataset": {"id": "news29"}, "category": {"name": "News"}},      # unusable type
]


@pytest.fixture
def hyp(tmp_path):
    p = tmp_path / "h.yaml"
    p.write_text(YAML)
    return H.load_file(p)


def _cell(region="USA", delay=1, universe="TOP3000", category="News"):
    return C.Cell(region, delay, category, universe, 0, 3, 1.2, 10, (("news29", 19),), 3.6)


def test_catalogue_index_and_eligible(hyp):
    idx = F.catalogue_index(ROWS)
    assert idx["nws29_frontpage"]["dataset"] == "news29" and idx["snt_neg"]["category"] == "Sentiment"
    assert F.eligible_fields(hyp, "News", idx) == [("nws29_frontpage", "VECTOR", "news29"), ("nws73_negscore", "MATRIX", "news73")]
    hyp.signal["vector"] = None
    assert F.eligible_fields(hyp, "News", idx) == [("nws73_negscore", "MATRIX", "news73")]


def test_render_vector_and_matrix(hyp):
    assert F.render(hyp, "nws29_frontpage", "VECTOR", {"w": 5, "group": "industry"}) == \
        "group_rank(ts_delta(vec_avg(nws29_frontpage), 5), industry)"
    assert F.render(hyp, "nws73_negscore", "MATRIX", {"w": 10, "group": "subindustry"}) == \
        "group_rank(ts_delta(nws73_negscore, 10), subindustry)"


def test_expand_grid_cap_and_determinism(hyp):
    idx = F.catalogue_index(ROWS)
    full = F.expand(hyp, _cell(), idx, random.Random(1), max_candidates=1000)
    assert len(full) == 2 * 2 * 2 * 2 * 2          # fields × w × group × neut × decay
    assert len({c["id"] for c in full}) == len(full)
    a = F.expand(hyp, _cell(), idx, random.Random(7), max_candidates=6)
    b = F.expand(hyp, _cell(), idx, random.Random(7), max_candidates=6)
    assert len(a) == 6 and [c["id"] for c in a] == [c["id"] for c in b]
    c0 = a[0]
    assert c0["settings"]["region"] == "USA" and c0["settings"]["universe"] == "TOP3000" and c0["settings"]["delay"] == 1
    assert c0["settings"]["unitHandling"] == "VERIFY" and c0["settings"]["truncation"] == 0.08
    assert c0["meta"]["hypothesis"] == "news_neg_v1" and c0["meta"]["category"] == "News"
    assert c0["signature"]["mechanism_key"].startswith("news_neg_v1#")
    assert c0["signature"]["datasets"] in (["news29"], ["news73"])


def test_expand_respects_cell_constraints(hyp):
    idx = F.catalogue_index(ROWS)
    assert F.expand(hyp, _cell(universe=None), idx, random.Random(1)) == []
    hyp.delays = [1]
    assert F.expand(hyp, _cell(delay=0), idx, random.Random(1)) == []
    hyp.regions = ["JPN"]
    assert F.expand(hyp, _cell(region="USA"), idx, random.Random(1)) == []
    assert F.expand(hyp, _cell(category="Sentiment"), idx, random.Random(1)) == []


def test_op_cap(hyp):
    idx = F.catalogue_index(ROWS)
    hyp.template = "group_rank(" * 40 + "{signal}" + ")" * 40 + " + {w}"
    hyp.params = {"w": [1]}
    assert F.op_count(F.render(hyp, "x", "MATRIX", {"w": 1})) == 41
    hyp.template = "rank(" * 63 + "{signal}" + ")" * 63
    hyp.params = {}
    assert F.expand(hyp, _cell(), idx, random.Random(1)) == []


def test_op_count_matches_platform_rule():
    assert F.op_count("group_rank(ts_delta(vec_avg(x), 5), industry)") == 3
    assert F.op_count("rank(a) - rank(b) * 0.5") == 4


def test_signature_uses_catalogue_datasets(hyp):
    idx = F.catalogue_index(ROWS)
    cands = F.expand(hyp, _cell(), idx, random.Random(3), max_candidates=50)
    assert {tuple(c["signature"]["datasets"]) for c in cands} == {("news29",), ("news73",)}
    assert all(c["signature"]["fields"] in (["nws29_frontpage"], ["nws73_negscore"]) for c in cands)


def test_two_leg_hypothesis_and_category_list(tmp_path):
    p = tmp_path / "h2.yaml"
    p.write_text(textwrap.dedent("""
        id: short_ratio_v1
        category: [Short Interest, Institutions]
        mechanism: informed short selling.
        sign: -1
        source: "EX-ANTE — Boehmer, Jones & Zhang 2008"
        datasets: []
        signal:
          fields: [short_vol, inst20_sv, missing_a]
        signal2:
          fields: [total_vol, inst20_tv, missing_b]
        template: "-group_rank(ts_mean({signal} / {signal2}, {w}), {group})"
        params:
          w: [5]
          group: [industry]
        settings:
          neutralization: [INDUSTRY]
          decay: [0]
    """))
    h = H.load_file(p)
    assert h.categories() == ["Short Interest", "Institutions"]
    rows = [
        {"id": "short_vol", "type": "MATRIX", "dataset": {"id": "us_short_sale"}, "category": {"name": "Short Interest"}},
        {"id": "total_vol", "type": "MATRIX", "dataset": {"id": "us_short_sale"}, "category": {"name": "Short Interest"}},
        {"id": "inst20_sv", "type": "MATRIX", "dataset": {"id": "institutions20"}, "category": {"name": "Institutions"}},
        {"id": "inst20_tv", "type": "MATRIX", "dataset": {"id": "institutions20"}, "category": {"name": "Institutions"}},
    ]
    idx = F.catalogue_index(rows)
    assert F.eligible_fields(h, "Short Interest", idx) == [("short_vol", "MATRIX", "us_short_sale", "total_vol", "MATRIX")]
    si = F.expand(h, _cell(category="Short Interest"), idx, random.Random(1))
    inst = F.expand(h, _cell(category="Institutions"), idx, random.Random(1))
    assert len(si) == 1 and si[0]["formula"] == "-group_rank(ts_mean(short_vol / total_vol, 5), industry)"
    assert len(inst) == 1 and inst[0]["formula"] == "-group_rank(ts_mean(inst20_sv / inst20_tv, 5), industry)"
    assert si[0]["signature"]["datasets"] == ["us_short_sale"] and si[0]["meta"]["field2"] == "total_vol"
    assert F.expand(h, _cell(category="News"), idx, random.Random(1)) == []
    assert H.categories([h]) == {"Short Interest", "Institutions"}


def test_density_wraps_the_leg_before_the_template(hyp):
    hyp.signal["density"] = "zero"
    assert F.render(hyp, "nws29_frontpage", "VECTOR", {"w": 5, "group": "industry"}) == \
        "group_rank(ts_delta(add(vec_avg(nws29_frontpage), 0, filter=true), 5), industry)"
    hyp.signal["density"] = "backfill"
    hyp.signal["density_window"] = 30
    assert F.render(hyp, "nws73_negscore", "MATRIX", {"w": 5, "group": "industry"}) == \
        "group_rank(ts_delta(ts_backfill(nws73_negscore, 30), 5), industry)"
    assert F.op_count(F.render(hyp, "nws73_negscore", "MATRIX", {"w": 5, "group": "industry"})) == 3


def test_template_list_expands_every_alternative(hyp):
    hyp.template = ["group_rank(ts_delta({signal}, {w}), {group})", "group_rank(ts_rank({signal}, {w}), {group})"]
    idx = F.catalogue_index(ROWS)
    cands = F.expand(hyp, _cell(), idx, random.Random(1), max_candidates=1000)
    assert len(cands) == 2 * 2 * 2 * 2 * 2 * 2                      # × 2 templates
    assert {c["meta"]["template_i"] for c in cands} == {0, 1}
    assert any("ts_rank(" in c["formula"] for c in cands) and any("ts_delta(" in c["formula"] for c in cands)
