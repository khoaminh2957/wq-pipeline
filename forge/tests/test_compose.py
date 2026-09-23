import random
import textwrap

import pytest

from forge import cells as C
from forge import compose as CP
from forge import hypotheses as H
from forge import standard as ST
from forge import factory as F

LEG_A = textwrap.dedent("""
    id: prof_leg
    family: profitability
    category: Fundamental
    mechanism: profitable firms outperform.
    sign: 1
    source: "EX-ANTE — Novy-Marx 2013"
    datasets: [fundamental7]
    signal:
      fields: [fnd7_qin]
    signal2:
      fields: [fnd7_qta]
    template: "group_rank(ts_rank({signal} / {signal2}, {w}), {group})"
    params:
      w: [126]
      group: [subindustry]
    settings:
      neutralization: [SUBINDUSTRY]
      decay: [8]
""")
LEG_B = LEG_A.replace("prof_leg", "acc_leg").replace("family: profitability", "family: accruals") \
    .replace("fields: [fnd7_qin]", "fields: [fnd7_acc]").replace("fields: [fnd7_qta]", "fields: [fnd7_qta]") \
    .replace('template: "group_rank', 'template: "-group_rank')
LEG_C = LEG_A.replace("prof_leg", "ins_leg").replace("family: profitability", "family: insider").replace("category: Fundamental", "category: Other") \
    .replace("datasets: [fundamental7]", "datasets: [insider_feats]").replace("fields: [fnd7_qin]", "fields: [ins_ratio]") \
    .replace("signal2:\n  fields: [fnd7_qta]\n", "").replace('template: "group_rank(ts_rank({signal} / {signal2}, {w}), {group})"', 'template: "group_rank(ts_backfill({signal}, {w}), {group})"')
COMP = textwrap.dedent("""
    id: prof_x_accruals
    title: Profitable and cash-backed
    legs: [prof_leg, acc_leg]
    families: [profitability, accruals]
    combiners: [multiply, gate]
    mechanism: >
      Profitability predicts returns only when the profits are backed by cash; high accruals mark
      earnings that later reverse, so the product of the two ranks is high for firms that are both
      profitable and low-accrual, which is the logic of the Piotroski score in two legs.
    counterparty: "Retail investors and earnings-chasing funds who buy headline profits without checking accruals"
    source: "EX-ANTE — Piotroski 2000; Novy-Marx 2013"
    regimes: {value_winter_2014_2020: "+", momentum_crash_2016: "+", covid_2020: "0", rate_shock_2022: "+"}
    strongest_in: "small, low-coverage value names"
    weakens_when: "earnings are dominated by one-off items"
    settings:
      neutralization: [SUBINDUSTRY, STATISTICAL]
      decay: [8]
      truncation: 0.08
""")
ROWS = [
    {"id": "fnd7_qin", "type": "MATRIX", "dataset": {"id": "fundamental7"}, "category": {"name": "Fundamental"}},
    {"id": "fnd7_qta", "type": "MATRIX", "dataset": {"id": "fundamental7"}, "category": {"name": "Fundamental"}},
    {"id": "fnd7_acc", "type": "MATRIX", "dataset": {"id": "fundamental7"}, "category": {"name": "Fundamental"}},
    {"id": "ins_ratio", "type": "MATRIX", "dataset": {"id": "insider_feats"}, "category": {"name": "Other"}},
]


@pytest.fixture
def lib(tmp_path):
    for name, text in (("a", LEG_A), ("b", LEG_B), ("c", LEG_C)):
        (tmp_path / ("%s.yaml" % name)).write_text(text)
    return H.load_library(tmp_path)


def _cell(cat="Fundamental"):
    return C.Cell("GLB", 1, cat, "MINVOL1M", 0, 3, 1.4, 50, (), 4.2)


def test_positive_form_and_combine():
    assert CP.positive_form("-group_rank(x, g)") == "(1 - group_rank(x, g))"
    assert CP.positive_form("group_rank(x, g)") == "group_rank(x, g)"
    assert CP.combine("group_rank(a, g)", "-group_rank(b, g)", "multiply") == "multiply(group_rank(a, g), (1 - group_rank(b, g)))"
    assert CP.combine("-group_rank(a, g)", "group_rank(b, g)", "gate") == "if_else(greater(group_rank(b, g), 0.5), -group_rank(a, g), 0)"
    with pytest.raises(ValueError):
        CP.combine("a", "b", "average")


def test_composite_loads_and_passes_hard_gates(tmp_path, lib):
    (tmp_path / "comps").mkdir()
    (tmp_path / "comps/p.yaml").write_text(COMP)
    comps = H.load_composites(tmp_path / "comps", lib)
    assert len(comps) == 1 and comps[0].combiners == ["multiply", "gate"]
    assert ST.hard_gates(comps[0]) == []
    assert ST.hard_gates(lib[0]) and ST.hard_gates(lib[0])[0][0] == 6      # a single-field hypothesis is a leg


@pytest.mark.parametrize("edit,msg", [
    (("families: [profitability, accruals]", "families: [profitability, profitability]"), "cross-family"),
    (("legs: [prof_leg, acc_leg]", "legs: [prof_leg, nope]"), "not in the library"),
    (('rate_shock_2022: "+"', 'rate_shock_2022: "?"'), "regimes"),
    (("Retail investors and earnings-chasing funds", "People"), "agent class"),
    (("combiners: [multiply, gate]", "combiners: [average]"), "combiners"),
    (('source: "EX-ANTE', 'source: "maybe'), "RULE 0"),
])
def test_composite_validation(tmp_path, lib, edit, msg):
    text = COMP.replace(*edit)
    assert text != COMP
    (tmp_path / "bad.yaml").write_text(text)
    with pytest.raises(H.HypothesisError, match=msg):
        H.load_composite(tmp_path / "bad.yaml", {h.id for h in lib})


def test_expand_builds_rank_bounded_products(tmp_path, lib):
    (tmp_path / "comps").mkdir()
    (tmp_path / "comps/p.yaml").write_text(COMP)
    comp = H.load_composites(tmp_path / "comps", lib)[0]
    idx = F.catalogue_index(ROWS)
    by = {h.id: h for h in lib}
    fd = {fid: m["dataset"] for fid, m in idx.items()}
    cands = CP.expand(comp, _cell(), idx, by, random.Random(1), max_candidates=100, field_datasets=fd)
    # 1 leg formula each × 2 combiners × 2 neutralizations × 1 decay
    assert len(cands) == 4
    forms = {c["meta"]["combiner"]: c["formula"] for c in cands}
    assert forms["multiply"] == "multiply(group_rank(ts_rank(fnd7_qin / fnd7_qta, 126), subindustry), (1 - group_rank(ts_rank(fnd7_acc / fnd7_qta, 126), subindustry)))"
    assert forms["gate"].startswith("if_else(greater((1 - group_rank(ts_rank(fnd7_acc / fnd7_qta, 126), subindustry)), 0.5), group_rank(")
    c0 = cands[0]
    assert c0["meta"]["composite"] == 1 and c0["meta"]["legs"] == ["prof_leg", "acc_leg"] and c0["meta"]["families"] == ["profitability", "accruals"]
    assert c0["settings"]["neutralization"] in ("SUBINDUSTRY", "STATISTICAL") and c0["settings"]["universe"] == "MINVOL1M"
    assert c0["signature"]["datasets"] == ["fundamental7"] and c0["signature"]["mechanism_key"].startswith("prof_x_accruals#")
    assert F.op_count(forms["multiply"]) == 8      # 4 calls + 2 divisions + 1 subtraction + multiply, as the platform counts


def test_expand_cross_category_and_refusals(tmp_path, lib):
    (tmp_path / "comps").mkdir()
    (tmp_path / "comps/x.yaml").write_text(COMP.replace("legs: [prof_leg, acc_leg]", "legs: [prof_leg, ins_leg]")
                                          .replace("families: [profitability, accruals]", "families: [profitability, insider]"))
    comp = H.load_composites(tmp_path / "comps", lib)[0]
    idx = F.catalogue_index(ROWS)
    by = {h.id: h for h in lib}
    # target cell Fundamental: served by prof_leg; ins_leg joins from Other
    cands = CP.expand(comp, _cell("Fundamental"), idx, by, random.Random(1))
    assert cands and all("ins_ratio" in c["formula"] and "fnd7_qin" in c["formula"] for c in cands)
    # target cell Other: served by ins_leg
    assert CP.expand(comp, _cell("Other"), idx, by, random.Random(1))
    # a cell no leg serves -> nothing; no universe -> nothing
    assert CP.expand(comp, _cell("News"), idx, by, random.Random(1)) == []
    assert CP.expand(comp, _cell()._replace(universe=None), idx, by, random.Random(1)) == []


def test_three_leg_composite_is_a_product_of_three(tmp_path, lib):
    (tmp_path / "comps").mkdir()
    (tmp_path / "comps/t.yaml").write_text(COMP.replace("legs: [prof_leg, acc_leg]", "legs: [prof_leg, acc_leg, ins_leg]")
                                          .replace("families: [profitability, accruals]", "families: [profitability, accruals, insider]"))
    comp = H.load_composites(tmp_path / "comps", lib)[0]
    idx = F.catalogue_index(ROWS)
    by = {h.id: h for h in lib}
    cands = CP.expand(comp, _cell(), idx, by, random.Random(1), max_candidates=100)
    assert cands and all(c["meta"]["combiner"] == "multiply" for c in cands)      # gate dropped for 3 legs
    f = cands[0]["formula"]
    assert f.startswith("multiply(multiply(") and "ins_ratio" in f and "fnd7_acc" in f and "fnd7_qin" in f
    assert cands[0]["meta"]["legs"] == ["prof_leg", "acc_leg", "ins_leg"] and F.op_count(f) <= F.MAX_OPS
