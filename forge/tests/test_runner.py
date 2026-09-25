import hashlib
import json
import os
import pathlib
import socket
import subprocess
import sys
import textwrap

import pytest

from forge import runner as R

HYP = textwrap.dedent("""
    id: news_test_v1
    category: News
    mechanism: test.
    sign: -1
    source: "EX-ANTE — test"
    datasets: [news29]
    signal:
      fields: [nws29_frontpage]
      vector: vec_sum
    template: "-group_rank(ts_sum({signal}, {w}), {group})"
    params:
      w: [3, 5, 10]
      group: [subindustry, industry]
    settings:
      neutralization: [SUBINDUSTRY, INDUSTRY]
      decay: [4, 8]
""")


def _root(tmp_path):
    (tmp_path / "state/layered/runs").mkdir(parents=True)
    (tmp_path / "fetched/rc/fields").mkdir(parents=True)
    (tmp_path / "hyp").mkdir()
    (tmp_path / "hyp/a.yaml").write_text(HYP)
    json.dump({"pairs": [{"region": "USA", "delay": 1, "counts": {"News": 0, "Model": 22}},
                         {"region": "EUR", "delay": 1, "counts": {"News": 1}}]},
              open(tmp_path / "state/pyramid_cell_counts.json", "w"))
    json.dump({"USA_TOP3000_d1": [{"id": "news29", "category": {"name": "News"}, "userCount": 19, "pyramidMultiplier": 1.2}],
               "EUR_TOP2500_d1": [{"id": "news29", "category": {"name": "News"}, "userCount": 21, "pyramidMultiplier": 1.0}]},
              open(tmp_path / "fetched/rc/datasets_survey.json", "w"))
    row = json.dumps({"id": "nws29_frontpage", "type": "VECTOR", "dataset": {"id": "news29"}, "category": {"name": "News"}})
    (tmp_path / "fetched/rc/fields/USA_TOP3000_d1.jsonl").write_text(row + "\n")
    (tmp_path / "fetched/rc/fields/EUR_TOP2500_d1.jsonl").write_text(row + "\n")
    return tmp_path


def test_plan_allocates_cells_first_and_respects_caps(tmp_path):
    root = _root(tmp_path)
    p = R.plan(root, n=100, seed=1, per_block=5, cell_cap=5, library_dir=root / "hyp", mode="singles")
    # 12 grid points per cell (3 w × 2 group × 2 neut × 1... = 3*2*2*2 = 24), capped to 5 per block/cell
    assert len(p["constructions"]) == 10 and p["gate"]["ok"] == 10
    cells = [b["cell"] for b in p["blocks"]]
    assert cells == ["USA/d1 News", "EUR/d1 News"]          # USA weight 3*1.2 > EUR 2*1.0
    c0 = p["constructions"][0]
    assert c0["settings"]["region"] == "USA" and c0["settings"]["universe"] == "TOP3000"
    assert c0["meta"]["forge"] == 1 and c0["meta"]["hypothesis"] == "news_test_v1"
    assert c0["meta"]["signature"] == "news29#smooth+vector#USA/d1"
    assert c0["meta"]["mechanism_key"] == "news_test_v1#news29#USA/d1"
    assert "vec_sum(nws29_frontpage)" in c0["formula"]
    assert "USA/d1 News" in R.summarize(p)


def test_plan_stops_at_n_and_skips_journalled_duplicates(tmp_path):
    root = _root(tmp_path)
    first = R.plan(root, n=4, seed=2, per_block=20, cell_cap=60, library_dir=root / "hyp", mode="singles")
    assert len(first["constructions"]) == 4 and first["gate"]["ok"] == 4
    with open(root / "state/layered/runs/forge.jsonl", "w") as fh:
        for c in first["constructions"]:
            fh.write(json.dumps({"alpha": "x", "formula": c["formula"], "settings": c["settings"]}) + "\n")
    second = R.plan(root, n=100, seed=2, per_block=20, cell_cap=60, library_dir=root / "hyp", mode="singles")
    ids = {c["meta"]["cand"] for c in second["constructions"]}
    assert not ids & {c["meta"]["cand"] for c in first["constructions"]}
    # the 4 journalled points are refused in the d1 pass AND again in the leftover pass (8 refusals)
    assert second["gate"]["duplicate"] == 8
    # USA grid 24 points, 4 journalled -> 20 novel; EUR 24. The d1 half takes 20+20, the leftover
    # pass tops up EUR's remaining 4: everything available is used, nothing journalled is re-simulated.
    assert len(second["constructions"]) == 20 + 24 and second["blocks"][0]["grid"] == 24


def test_plan_with_empty_library_dir(tmp_path):
    root = _root(tmp_path)
    (tmp_path / "empty").mkdir()
    p = R.plan(root, n=10, seed=3, library_dir=tmp_path / "empty", mode="singles")
    assert p["constructions"] == [] and p["hypotheses"] == 0


def test_plan_splits_each_round_half_d0_half_d1(tmp_path):
    root = _root(tmp_path)
    json.dump({"pairs": [{"region": "USA", "delay": 1, "counts": {"News": 0}},
                         {"region": "USA", "delay": 0, "counts": {"News": 0}}]},
              open(root / "state/pyramid_cell_counts.json", "w"))
    json.dump({"USA_TOP3000_d1": [{"id": "news29", "category": {"name": "News"}, "userCount": 19, "pyramidMultiplier": 1.2}],
               "USA_TOP3000_d0": [{"id": "news29", "category": {"name": "News"}, "userCount": 3, "pyramidMultiplier": 1.8}]},
              open(root / "fetched/rc/datasets_survey.json", "w"))
    row = json.dumps({"id": "nws29_frontpage", "type": "VECTOR", "dataset": {"id": "news29"}, "category": {"name": "News"}})
    (root / "fetched/rc/fields/USA_TOP3000_d0.jsonl").write_text(row + "\n")
    p = R.plan(root, n=10, seed=5, per_block=20, cell_cap=60, library_dir=root / "hyp", mode="singles")
    assert p["by_delay"] == {0: 5, 1: 5} and len(p["constructions"]) == 10
    # Khoa 2026-09-07 (tick): d1 only -- the d0 cell is dropped before planning, whole round goes to d1
    p = R.plan(root, n=10, seed=5, per_block=20, cell_cap=60, library_dir=root / "hyp", mode="singles",
               split_delays=False, delays=[1])
    assert p["by_delay"] == {0: 0, 1: 10}
    # d0 side cannot fill (no catalogue) -> its half flows to d1
    (root / "fetched/rc/fields/USA_TOP3000_d0.jsonl").unlink()
    p = R.plan(root, n=10, seed=5, per_block=20, cell_cap=60, library_dir=root / "hyp", mode="singles")
    assert p["by_delay"] == {0: 0, 1: 10}
    assert "d0 0 / d1 10" in R.summarize(p)


def test_plan_skips_quarantined_pairs(tmp_path):
    root = _root(tmp_path)
    (root / "state/forge").mkdir(parents=True)
    (root / "state/forge/quarantine.json").write_text(json.dumps(["news_test_v1|USA|1|News|nws29_frontpage"]))
    p = R.plan(root, n=10, seed=1, library_dir=root / "hyp", mode="singles")
    assert p["quarantined"] == 1
    assert all(c["settings"]["region"] == "EUR" for c in p["constructions"]) and len(p["constructions"]) == 10


def test_plan_ensembles_only_uses_measured_legs(tmp_path):
    root = _root(tmp_path)
    (root / "hyp/b.yaml").write_text(HYP.replace("news_test_v1", "news_test_v2").replace("datasets: [news29]", "datasets: [news73]")
                                     .replace("fields: [nws29_frontpage]", "fields: [nws73_neg]"))
    row2 = json.dumps({"id": "nws73_neg", "type": "MATRIX", "dataset": {"id": "news73"}, "category": {"name": "News"}})
    with open(root / "fetched/rc/fields/USA_TOP3000_d1.jsonl", "a") as fh:
        fh.write(row2 + "\n")
    legs = [
        {"alpha": "L1", "sharpe": 0.7, "formula": "-group_rank(ts_sum(vec_sum(nws29_frontpage), 5), industry)",
         "meta": {"forge": 1, "hypothesis": "news_test_v1", "category": "News", "dataset": "news29", "field": "nws29_frontpage"},
         "settings": {"region": "USA", "delay": 1, "universe": "TOP3000", "neutralization": "INDUSTRY", "decay": 8, "truncation": 0.08}},
        {"alpha": "L2", "sharpe": 0.4, "formula": "-group_rank(ts_sum(nws73_neg, 5), industry)",
         "meta": {"forge": 1, "hypothesis": "news_test_v2", "category": "News", "dataset": "news73", "field": "nws73_neg"},
         "settings": {"region": "USA", "delay": 1, "universe": "TOP3000", "neutralization": "INDUSTRY", "decay": 8, "truncation": 0.08}},
    ]
    with open(root / "state/layered/runs/forge.jsonl", "w") as fh:
        for r in legs:
            fh.write(json.dumps(r) + "\n")
    p = R.plan(root, n=50, seed=1, library_dir=root / "hyp", ensembles="only", mode="singles")
    assert p["n_ensembles"] == 2 and len(p["constructions"]) == 2          # one pair × weights {1.0, 0.5}
    c = p["constructions"][0]
    assert c["meta"]["ensemble"] == 1 and c["meta"]["hypothesis"] == "ens:news_test_v1+news_test_v2"
    assert c["settings"]["region"] == "USA" and "nws73_neg" in c["formula"] and "nws29_frontpage" in c["formula"]
    assert c["meta"]["signature"] == "news29|news73#smooth+vector#USA/d1"
    p2 = R.plan(root, n=50, seed=1, library_dir=root / "hyp", ensembles="add", mode="singles")
    assert p2["n_ensembles"] == 2 and len(p2["constructions"]) > 2         # ensembles first, then single legs
    assert p2["constructions"][0]["meta"].get("ensemble") == 1
    p3 = R.plan(root, n=50, seed=1, library_dir=root / "hyp", ensembles="off", mode="singles")
    assert p3["n_ensembles"] == 0


def test_plan_composites_mode_simulates_only_admissible_composites(tmp_path):
    root = _root(tmp_path)
    (root / "hyp/b.yaml").write_text(HYP.replace("news_test_v1", "news_test_v2").replace("datasets: [news29]", "datasets: [news73]")
                                     .replace("fields: [nws29_frontpage]", "fields: [nws73_neg]").replace("    vector: vec_sum\n", ""))
    for name, fam in (("a", "attention"), ("b", "tone")):
        p = root / ("hyp/%s.yaml" % name)
        p.write_text(p.read_text().replace("\ncategory:", "\nfamily: %s\ncategory:" % fam, 1))
    row2 = json.dumps({"id": "nws73_neg", "type": "MATRIX", "dataset": {"id": "news73"}, "category": {"name": "News"}})
    with open(root / "fetched/rc/fields/USA_TOP3000_d1.jsonl", "a") as fh:
        fh.write(row2 + "\n")
    (root / "comps").mkdir()
    (root / "comps/c.yaml").write_text(textwrap.dedent("""
        id: attention_x_tone
        legs: [news_test_v1, news_test_v2]
        families: [attention, tone]
        combiners: [multiply, gate]
        mechanism: >
          attention-driven buying reverses fastest when the accompanying news tone is negative, because
          the buyers were reacting to salience rather than content; the product of the two ranks keeps
          the salient-but-negative names and retail buyers supply the reversal on those.
        counterparty: "Retail investors who buy salient headlines regardless of tone"
        source: "EX-ANTE — Barber & Odean 2008; Tetlock 2007"
        regimes: {value_winter_2014_2020: "+", momentum_crash_2016: "+", covid_2020: "0", rate_shock_2022: "+"}
        strongest_in: "small caps"
        weakens_when: "market-wide news dominates"
        settings:
          neutralization: [INDUSTRY]
          decay: [4]
    """))
    p = R.plan(root, n=40, seed=1, library_dir=root / "hyp", composites_dir=root / "comps", mode="composites")
    assert p["composites"] == 1 and p["n_composites"] == len(p["constructions"]) > 0
    c = p["constructions"][0]
    assert c["meta"]["composite"] == 1 and c["meta"]["hypothesis"] == "attention_x_tone"
    assert c["formula"].startswith(("multiply(", "if_else(greater("))
    assert "nws29_frontpage" in c["formula"] and "nws73_neg" in c["formula"]
    assert "USA/d1 News" in R.summarize(p) and "[composites]" in R.summarize(p)
    both = R.plan(root, n=200, seed=1, library_dir=root / "hyp", composites_dir=root / "comps", mode="both")
    assert both["n_composites"] > 0 and len(both["constructions"]) > both["n_composites"]
    assert both["constructions"][0]["meta"].get("composite") == 1


def test_plan_cells_and_only_filters(tmp_path):
    root = _root(tmp_path)
    p = R.plan(root, n=10, seed=1, library_dir=root / "hyp", mode="singles", cells_filter=["EUR/d1 News"])
    assert p["constructions"] and all(c["settings"]["region"] == "EUR" for c in p["constructions"])
    p = R.plan(root, n=10, seed=1, library_dir=root / "hyp", mode="singles", cells_filter=["EUR/d1:News"])
    assert p["constructions"] and all(c["settings"]["region"] == "EUR" for c in p["constructions"])
    p = R.plan(root, n=10, seed=1, library_dir=root / "hyp", mode="singles", cells_filter=["EUR/d1:%20News"])
    assert p["constructions"] == []                      # "EUR/d1  News" (double space) matches nothing
    p = R.plan(root, n=10, seed=1, library_dir=root / "hyp", mode="singles", cells_filter=["USA/d0 Model"])
    assert p["constructions"] == []
    p = R.plan(root, n=10, seed=1, library_dir=root / "hyp", mode="singles", only=["nope"])
    assert p["constructions"] == []


def test_plan_recipe_overrides(tmp_path):
    root = _root(tmp_path)
    row = json.dumps({"id": "nws29_frontpage", "type": "VECTOR", "dataset": {"id": "news29"}, "category": {"name": "News"}})
    (root / "fetched/rc/fields/USA_TOP1000_d1.jsonl").write_text(row + "\n")
    rec = {"universe": {"USA": "TOP1000"}, "neut": ["MARKET"], "group": "country", "decay": [4], "truncation": 0.05,
           "smooth": 10, "power": 2, "tag": "R9"}
    p = R.plan(root, n=10, seed=1, library_dir=root / "hyp", mode="singles", cells_filter=["USA/d1 News"], recipe=rec)
    assert p["constructions"]
    c = p["constructions"][0]
    assert c["settings"]["universe"] == "TOP1000" and c["settings"]["neutralization"] == "MARKET"
    assert c["settings"]["decay"] == 4 and c["settings"]["truncation"] == 0.05
    assert c["formula"].startswith("ts_decay_linear(signed_power(") and c["formula"].endswith(", 2), 10)") and ", country)" in c["formula"]
    assert c["meta"]["recipe"] == "R9"
    # a universe with no catalogue on disk yields nothing, visibly
    p2 = R.plan(root, n=10, seed=1, library_dir=root / "hyp", mode="singles", cells_filter=["USA/d1 News"],
                recipe={"universe": {"USA": "TOP200"}})
    assert p2["constructions"] == []


def test_plan_order_and_no_split(tmp_path):
    root = _root(tmp_path)
    json.dump({"pairs": [{"region": "USA", "delay": 1, "counts": {"News": 0}},
                         {"region": "USA", "delay": 0, "counts": {"News": 0}},
                         {"region": "EUR", "delay": 1, "counts": {"News": 0}}]},
              open(root / "state/pyramid_cell_counts.json", "w"))
    json.dump({"USA_TOP3000_d1": [{"id": "news29", "category": {"name": "News"}, "userCount": 19, "pyramidMultiplier": 1.0}],
               "USA_TOP3000_d0": [{"id": "news29", "category": {"name": "News"}, "userCount": 3, "pyramidMultiplier": 1.9}],
               "EUR_TOP2500_d1": [{"id": "news29", "category": {"name": "News"}, "userCount": 21, "pyramidMultiplier": 1.5}]},
              open(root / "fetched/rc/datasets_survey.json", "w"))
    row = json.dumps({"id": "nws29_frontpage", "type": "VECTOR", "dataset": {"id": "news29"}, "category": {"name": "News"}})
    (root / "fetched/rc/fields/USA_TOP3000_d0.jsonl").write_text(row + "\n")
    # default: half d0 / half d1, weight order -> d0 (1.9) gets its half first
    p = R.plan(root, n=8, seed=1, library_dir=root / "hyp", mode="singles")
    assert p["by_delay"] == {0: 4, 1: 4}
    # standing-loop order: USA/d1, then any d1, then the rest; no split
    p = R.plan(root, n=8, seed=1, library_dir=root / "hyp", mode="singles", split_delays=False,
               recipe={"order": ["USA/d1", "d1"]})
    regs = [(c["settings"]["region"], c["settings"]["delay"]) for c in p["constructions"]]
    assert regs[0] == ("USA", 1) and p["by_delay"][0] == 0 and len(p["constructions"]) == 8


def test_plan_allocator_skips_harvested_and_dead_and_exploits_near_miss(tmp_path):
    """Composites mode with the allocator: a journal marks one pair harvested (mechanism posted),
    one dead (70 sims, best 0.5) and one near miss (best 1.45, LOW_SHARPE only)."""
    import textwrap
    root = _root(tmp_path)
    # two legs on USA/d1 News + Sentiment, three composites over them
    (root / "hyp/s.yaml").write_text(HYP.replace("news_test_v1", "sent_leg").replace("category: News", "category: Sentiment")
                                     .replace("datasets: [news29]", "datasets: [snt1]").replace("fields: [nws29_frontpage]", "fields: [snt1_score]")
                                     .replace("  vector: vec_sum\n", ""))
    (root / "hyp/a.yaml").write_text(HYP.replace("news_test_v1", "news_leg"))
    (root / "hyp/f.yaml").write_text(HYP.replace("news_test_v1", "fund_leg").replace("category: News", "category: Fundamental")
                                     .replace("datasets: [news29]", "datasets: [fnd9]").replace("fields: [nws29_frontpage]", "fields: [fnd9_roe]")
                                     .replace("  vector: vec_sum\n", "").replace("sign: -1", "sign: 1"))
    rows = [json.dumps({"id": "nws29_frontpage", "type": "VECTOR", "dataset": {"id": "news29"}, "category": {"name": "News"}}),
            json.dumps({"id": "snt1_score", "type": "MATRIX", "dataset": {"id": "snt1"}, "category": {"name": "Sentiment"}}),
            json.dumps({"id": "fnd9_roe", "type": "MATRIX", "dataset": {"id": "fnd9"}, "category": {"name": "Fundamental"}})]
    (root / "fetched/rc/fields/USA_TOP3000_d1.jsonl").write_text("\n".join(rows) + "\n")
    json.dump({"pairs": [{"region": "USA", "delay": 1, "counts": {"News": 0, "Sentiment": 0, "Fundamental": 22}}]},
              open(root / "state/pyramid_cell_counts.json", "w"))
    json.dump({"USA_TOP3000_d1": [{"id": "news29", "category": {"name": "News"}, "userCount": 19, "pyramidMultiplier": 1.2},
                                  {"id": "snt1", "category": {"name": "Sentiment"}, "userCount": 5, "pyramidMultiplier": 1.4},
                                  {"id": "fnd9", "category": {"name": "Fundamental"}, "userCount": 5, "pyramidMultiplier": 1.1}]},
              open(root / "fetched/rc/datasets_survey.json", "w"))
    comps = root / "comps"; comps.mkdir()
    COMP = textwrap.dedent("""
        id: %s
        title: t
        legs: [%s, fund_leg]
        families: [%s, profitability]
        combiners: [multiply]
        mechanism: "Retail investors chase headlines and buy attention-grabbing names, which pushes prices above value for several days; the pressure then reverts as the attention fades, so shorting the most-covered names earns the reversal while profitable firms are spared."
        counterparty: "Retail investors who chase headlines and index funds that rebalance mechanically"
        source: "EX-ANTE — a canonical anomaly (Sloan 1996)"
        regimes: {value_winter_2014_2020: "+", momentum_crash_2016: "0", covid_2020: "+", rate_shock_2022: "0"}
        strongest_in: "small caps"
        weakens_when: "rates rise"
        settings: {neutralization: [INDUSTRY], decay: [4], truncation: 0.08}
    """)
    (comps / "harv.yaml").write_text(COMP % ("harv_x_fund", "news_leg", "tone"))
    (comps / "near.yaml").write_text(COMP % ("near_x_fund", "sent_leg", "tone2"))
    (comps / "dead.yaml").write_text(COMP % ("dead_x_fund", "news_leg", "tone3"))
    def jrow(alpha, comp, cat, sharpe, passed, mk):
        ck = [{"name": "LOW_SHARPE", "result": "PASS" if passed else "FAIL"}, {"name": "LOW_FITNESS", "result": "PASS"},
              {"name": "CONCENTRATED_WEIGHT", "result": "PASS"}]
        return {"alpha": alpha, "sharpe": sharpe, "turnover": 0.1, "checks": ck, "formula": "x" + alpha,
                "settings": {"region": "USA", "delay": 1, "universe": "TOP3000"},
                "meta": {"forge": 1, "hypothesis": comp, "category": cat, "mechanism_key": mk, "seed": 1}}
    with open(root / "state/layered/runs/forge.jsonl", "w") as fh:
        fh.write(json.dumps(jrow("H1", "harv_x_fund", "News", 1.9, True, "harv#k")) + "\n")
        fh.write(json.dumps(jrow("N1", "near_x_fund", "Sentiment", 1.45, False, "near#k")) + "\n")
        for i in range(70):
            fh.write(json.dumps(jrow("D%d" % i, "dead_x_fund", "News", 0.5, False, "dead#k")) + "\n")
    p = R.plan(root, n=100, seed=1, library_dir=root / "hyp", composites_dir=comps, mode="composites",
               posted_keys={"harv#k"}, allocate=True)
    assert p["pair_classes"] == {"HARVESTED": 1, "NEAR_MISS": 1, "DEAD": 1}
    hyps = [b["hypothesis"] for b in p["blocks"] if b["kept"]]
    assert "harv_x_fund" not in hyps and "dead_x_fund" not in hyps
    assert p["blocks"][0]["hypothesis"] == "near_x_fund" and p["blocks"][0]["class"] == "NEAR_MISS"
    assert p["blocks"][0]["kept"] <= 40 and p["constructions"]
    # allocator off: the legacy per-cell walk simulates everything again
    q = R.plan(root, n=100, seed=1, library_dir=root / "hyp", composites_dir=comps, mode="composites", allocate=False)
    assert {b["hypothesis"] for b in q["blocks"] if b["kept"]} >= {"harv_x_fund", "dead_x_fund", "near_x_fund"}


def test_ab_new_splits_the_round_between_current_and_new_composites(tmp_path):
    """harness5 (Khoa Q24): `--ab new` = half the round from the current composites, half from those
    marked `arm: new`, tagged meta.arm, on the cells the current half used first."""
    import textwrap
    root = _root(tmp_path)
    (root / "hyp/s.yaml").write_text(HYP.replace("news_test_v1", "sent_leg").replace("category: News", "category: Sentiment")
                                     .replace("datasets: [news29]", "datasets: [snt1]").replace("fields: [nws29_frontpage]", "fields: [snt1_score]")
                                     .replace("  vector: vec_sum\n", ""))
    (root / "hyp/a.yaml").write_text(HYP.replace("news_test_v1", "news_leg"))
    (root / "hyp/f.yaml").write_text(HYP.replace("news_test_v1", "fund_leg").replace("category: News", "category: Fundamental")
                                     .replace("datasets: [news29]", "datasets: [fnd9]").replace("fields: [nws29_frontpage]", "fields: [fnd9_roe]")
                                     .replace("  vector: vec_sum\n", "").replace("sign: -1", "sign: 1"))
    rows = [json.dumps({"id": "nws29_frontpage", "type": "VECTOR", "dataset": {"id": "news29"}, "category": {"name": "News"}}),
            json.dumps({"id": "snt1_score", "type": "MATRIX", "dataset": {"id": "snt1"}, "category": {"name": "Sentiment"}}),
            json.dumps({"id": "fnd9_roe", "type": "MATRIX", "dataset": {"id": "fnd9"}, "category": {"name": "Fundamental"}})]
    (root / "fetched/rc/fields/USA_TOP3000_d1.jsonl").write_text("\n".join(rows) + "\n")
    json.dump({"pairs": [{"region": "USA", "delay": 1, "counts": {"News": 0, "Sentiment": 0, "Fundamental": 22}}]},
              open(root / "state/pyramid_cell_counts.json", "w"))
    json.dump({"USA_TOP3000_d1": [{"id": "news29", "category": {"name": "News"}, "userCount": 19, "pyramidMultiplier": 1.2},
                                  {"id": "snt1", "category": {"name": "Sentiment"}, "userCount": 5, "pyramidMultiplier": 1.4},
                                  {"id": "fnd9", "category": {"name": "Fundamental"}, "userCount": 5, "pyramidMultiplier": 1.1}]},
              open(root / "fetched/rc/datasets_survey.json", "w"))
    comps = root / "comps"; comps.mkdir()
    COMP = textwrap.dedent("""
        id: %s
        title: t
        legs: [%s, fund_leg]
        families: [%s, profitability]
        combiners: [multiply]
        mechanism: "Retail investors chase headlines and buy attention-grabbing names, which pushes prices above value for several days; the pressure then reverts as the attention fades, so shorting the most-covered names earns the reversal while profitable firms are spared."
        counterparty: "Retail investors who chase headlines and index funds that rebalance mechanically"
        source: "EX-ANTE — a canonical anomaly (Sloan 1996)"
        regimes: {value_winter_2014_2020: "+", momentum_crash_2016: "0", covid_2020: "+", rate_shock_2022: "0"}
        strongest_in: "small caps"
        weakens_when: "rates rise"
        settings: {neutralization: [INDUSTRY], decay: [4], truncation: 0.08}
    """)
    (comps / "old.yaml").write_text(COMP % ("old_x_fund", "news_leg", "tone"))
    (comps / "new.yaml").write_text(COMP % ("new_x_fund", "sent_leg", "tone2") + "arm: new\n")
    p = R.plan(root, n=40, seed=1, library_dir=root / "hyp", composites_dir=comps, mode="composites", allocate=True, ab="new")
    arms = p["by_arm"]
    assert set(arms) == {"current", "new"} and arms["current"] > 0 and arms["new"] > 0
    assert all(c["meta"]["hypothesis"] == "old_x_fund" for c in p["constructions"] if c["meta"]["arm"] == "current")
    assert all(c["meta"]["hypothesis"] == "new_x_fund" for c in p["constructions"] if c["meta"]["arm"] == "new")
    assert p["ab"] == "new" and "A/B new" in R.summarize(p)
    # without --ab the new composite is just another composite, untagged
    q = R.plan(root, n=40, seed=1, library_dir=root / "hyp", composites_dir=comps, mode="composites", allocate=True)
    assert all("arm" not in c["meta"] for c in q["constructions"])


@pytest.fixture
def no_extras(monkeypatch):
    """D40: the version tests below fake deploy.pipeline_version_of, so they fake the extras count too. The
    real deploy.loop_reachable_extras is the release engineer's half of D40 and may or may not be in this tree
    (raising=False); these tests are about how pipeline_version() combines the answers, not which files count.
    The real function is exercised by test_an_unlisted_composite_on_a_target_marks_the_stamp_extras."""
    import deploy as DP
    monkeypatch.setattr(DP, "loop_reachable_extras", lambda root: [], raising=False)


def test_every_construction_carries_the_pipeline_version(tmp_path, monkeypatch, no_extras):
    """D1 grades a VERSION and D14 grades the alphas that version produced. Until 2026-09-23 no row
    carried one, so both sentences had no referent and the scorecard fell back to a time window."""
    from forge import runner as R
    import deploy as DP                  # tools/ is on sys.path: forge.runner puts it there
    # the bytes are always hashed now (S1iii-NL, next test); here they agree with the manifest's
    # PIPELINE id. The whole-tree `version` is another namespace and is never the claim (draw-3 pipeline
    # MINOR 4: this test used to certify a manifest carrying only `version` as agreeing with the bytes).
    # No raising=False (MINOR 4): if deploy.pipeline_version_of were renamed, the fake would have been
    # added beside it and this test would still pass while the runner fell to `unverified` for real.
    monkeypatch.setattr(DP, "pipeline_version_of", lambda root: "abc123")
    monkeypatch.setattr(R, "_VERSION", None)
    (tmp_path / "DEPLOYED.json").write_text(json.dumps({"version": "whole0tree000000", "pipeline_version": "abc123",
                                                        "files": 1}))
    assert R.pipeline_version(tmp_path) == "abc123"

    # no manifest: the version is COMPUTED from the bytes and marked, never omitted
    monkeypatch.setattr(R, "_VERSION", None)
    v = R.pipeline_version(tmp_path / "nothing-here")
    assert v.endswith("+untracked") or v == "unknown"

    # and it reaches the construction the planner emits
    monkeypatch.setattr(R, "_VERSION", "v-under-test")
    c = R._construction({"formula": "rank(x)", "settings": {"delay": 1}, "meta": {"hypothesis": "h"},
                         "signature": {"key": "k", "mechanism_key": "m"}}, seed=1)
    assert c["meta"]["pipeline_version"] == "v-under-test"


def test_the_version_stamp_hashes_the_bytes_and_checks_the_manifest_against_them(tmp_path, monkeypatch, no_extras):
    """Architecture round 2, S1iii-NL. The fallback was the WHOLE-TREE hash over the PLAN keys plus
    `+untracked` -- a third namespace that byte-identical code on /opt/wq could never match -- and a
    DEPLOYED.json was trusted over the bytes, so a hand-rsync after a deploy stamped rows with a version
    that was not running. Now the bytes are hashed by the release engineer's own
    deploy.pipeline_version_of(root) every time, and a manifest the bytes contradict is named, not trusted."""
    import deploy as DP
    asked = []

    def of(root):
        asked.append(pathlib.Path(root))
        return "c1051e000000000a"
    monkeypatch.setattr(DP, "pipeline_version_of", of)

    # no manifest: the bytes' own closure id, marked untracked
    monkeypatch.setattr(R, "_VERSION", None)
    assert R.pipeline_version(tmp_path) == "c1051e000000000a+untracked"
    assert asked == [tmp_path]

    # a manifest the bytes agree with: the manifest's id, unmarked
    (tmp_path / "DEPLOYED.json").write_text(json.dumps({"version": "whole0tree000000", "pipeline_version": "c1051e000000000a"}))
    monkeypatch.setattr(R, "_VERSION", None)
    assert R.pipeline_version(tmp_path) == "c1051e000000000a"

    # a manifest the bytes contradict (the hand-rsync after a deploy): never the bare manifest id, and
    # the bytes' own id is carried (draw-3 pipeline MINOR 3: it used to be dropped, so two different
    # drifts read as one label and the row could never be re-attributed)
    (tmp_path / "DEPLOYED.json").write_text(json.dumps({"version": "whole0tree000000", "pipeline_version": "01d0000000000000"}))
    monkeypatch.setattr(R, "_VERSION", None)
    assert R.pipeline_version(tmp_path) == "01d0000000000000+MISMATCH:c1051e000000000a"

    # bytes that cannot be hashed: the manifest is not vouched for either
    def broken(root):
        raise RuntimeError("could not import the loop")
    monkeypatch.setattr(DP, "pipeline_version_of", broken)
    monkeypatch.setattr(R, "_VERSION", None)
    assert R.pipeline_version(tmp_path) == "01d0000000000000+unverified"
    (tmp_path / "DEPLOYED.json").unlink()
    monkeypatch.setattr(R, "_VERSION", None)
    assert R.pipeline_version(tmp_path) == "unknown"


@pytest.mark.parametrize("manifest", [
    {"version": "e4726594f240aa07", "files": 3},                             # a pre-A10 manifest: `version` only
    {"version": "e4726594f240aa07", "pipeline_version": None},               # the adjudicator's `null` case
    {"version": "e4726594f240aa07", "pipeline_version": ""},
    {"version": "e4726594f240aa07", "pipeline_version": 5},                  # MINOR 5: TypeError at the `+`
    {"version": "e4726594f240aa07", "pipeline_version": ["c1051e000000000a"]},
    ["c1051e000000000a"],                                                    # a JSON list: AttributeError
])
def test_only_a_pipeline_version_string_is_a_claim(tmp_path, monkeypatch, manifest, no_extras):
    """draw-3 pipeline MINOR 4 and 5. The claim used to be `pipeline_version or version`: the whole-tree
    `version` is another id namespace, so a byte-identical tree with a manifest that lacked the pipeline id
    was stamped `<version>+MISMATCH`, and a non-string id crashed the planner (TypeError, or AttributeError
    for a list). Every one of these is now no claim at all -- the bytes' own id, marked untracked."""
    import deploy as DP
    monkeypatch.setattr(DP, "pipeline_version_of", lambda root: "c1051e000000000a")
    (tmp_path / "DEPLOYED.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(R, "_VERSION", None)
    assert R.pipeline_version(tmp_path) == "c1051e000000000a+untracked"


def test_a_manifest_too_deep_to_parse_is_no_claim(tmp_path, monkeypatch, no_extras):
    """draw3_fix pipeline 6 (the fix is item 7): a DEPLOYED.json of `'['*100000 + ']'*100000` made
    pipeline_version() raise RecursionError -- the adjudicator's replica adj4_target_rec -- and so crashed the
    planner, which MINOR 5 had fixed for every other unusable manifest. It is no claim, like those.
    SOURCE TREES ONLY (draw-4 pipeline 4 / P4): deploy.pipeline_version_of is faked here, so this cannot see a
    target. On a deploy TARGET the real deploy._target_manifest() lets the RecursionError out of
    pipeline_version_of and loop_reachable_extras, and the stamp is `unknown` (re-measured 2026-09-23 with the
    real deploy.py). No crash either way."""
    import deploy as DP
    monkeypatch.setattr(DP, "pipeline_version_of", lambda root: "c1051e000000000a")
    (tmp_path / "DEPLOYED.json").write_text("[" * 100000 + "]" * 100000)
    monkeypatch.setattr(R, "_VERSION", None)
    assert R.pipeline_version(tmp_path) == "c1051e000000000a+untracked"


@pytest.mark.parametrize("claim, on_disk, extras, want", [
    ("c1051e000000000a", "c1051e000000000a", ["forge/composites/zz.yaml"], "c1051e000000000a+EXTRAS:1"),
    ("c1051e000000000a", "c1051e000000000a", ["forge/composites/zz.yaml", "tools/zz.py"], "c1051e000000000a+EXTRAS:2"),
    ("c1051e000000000a", "c1051e000000000a", [], "c1051e000000000a"),
    ("c1051e000000000a", "c1051e000000000a", None, "c1051e000000000a"),      # not a target: nothing to be extra to
    ("01d0000000000000", "c1051e000000000a", ["tools/zz.py"], "01d0000000000000+MISMATCH:c1051e000000000a+EXTRAS:1"),
    (None, "c1051e000000000a", ["tools/zz.py"], "c1051e000000000a+untracked+EXTRAS:1"),
])
def test_files_the_loop_can_reach_outside_the_manifest_mark_the_stamp(tmp_path, monkeypatch, claim, on_disk, extras, want):
    """D40 (Khoa 2026-09-23 ~17:20): extras the loop can reach that remain after a push mark the stamp
    `+EXTRAS:<n>`, n = the files deploy.loop_reachable_extras(root) names. Before, the target id covered only
    the files DEPLOYED.json lists, so an unlisted composite the planner loads left the stamp bare (draw3_fix
    release 1, pipeline 2: `6a6ccbe1baf7996c` with and without forge/composites/zz_adj4_extra.yaml)."""
    import deploy as DP
    monkeypatch.setattr(DP, "pipeline_version_of", lambda root: on_disk)
    monkeypatch.setattr(DP, "loop_reachable_extras", lambda root: extras, raising=False)   # written in parallel
    if claim:
        (tmp_path / "DEPLOYED.json").write_text(json.dumps({"pipeline_version": claim}))
    monkeypatch.setattr(R, "_VERSION", None)
    assert R.pipeline_version(tmp_path) == want


def test_extras_that_cannot_be_counted_vouch_for_nothing_and_a_pre_d40_deploy_adds_nothing(tmp_path, monkeypatch):
    """D40, the two edges. A count that raises cannot say the bytes are only the listed ones, so the claim is
    `+unverified`, as when the bytes cannot be hashed. A deploy.py with no loop_reachable_extras (one from
    before D40) has no extras rule, and the stamp is what it was before D40: marking it would put every row of
    such a tree outside every cohort (D40's own warning, the draw-3 BLOCKER class)."""
    import deploy as DP
    monkeypatch.setattr(DP, "pipeline_version_of", lambda root: "c1051e000000000a")
    (tmp_path / "DEPLOYED.json").write_text(json.dumps({"pipeline_version": "c1051e000000000a"}))

    def broken(root):
        raise OSError("a directory the walk cannot read")
    monkeypatch.setattr(DP, "loop_reachable_extras", broken, raising=False)
    monkeypatch.setattr(R, "_VERSION", None)
    assert R.pipeline_version(tmp_path) == "c1051e000000000a+unverified"
    monkeypatch.delattr(DP, "loop_reachable_extras")
    monkeypatch.setattr(R, "_VERSION", None)
    assert R.pipeline_version(tmp_path) == "c1051e000000000a"


def test_the_stamp_agrees_with_the_real_deploy_manifest_on_a_source_tree(tmp_path, monkeypatch):
    """draw-3 pipeline MINOR 4: every other version test fakes deploy.pipeline_version_of, so nothing showed
    that the runner and the REAL tools/deploy.py agree. Here nothing is faked: a SOURCE-tree replica of the
    shipped surface (the real bytes, copied at their repository paths, so forge_loop.sh sits under vps/),
    the real deploy.manifest() written as its DEPLOYED.json, and the real runner reading it.

    The replica is a source tree WHEREVER this test runs (draw3_fix pipeline 1, the BLOCKER): it used to
    copy `local.relative_to(R.ROOT)`, which on a deploy target -- /opt/wq, where deploy's smoke runs
    `pytest forge/tests -x` -- keeps forge_loop.sh at the root, so the vps/ assertion below failed there,
    and a push carrying this file would then have rolled back (EX-ANTE: a read of deploy's smoke, not an
    observed rollback, as draw3_fix says; draw-4 pipeline 5(f)). Each file is now put at the SOURCE path the
    PLAN maps to its remote path, from deploy._root_map(), which reads either layout. The target-layout
    case of the stamp (a manifest with a `hashes` map; D40's extras) is the next test."""
    import deploy as DP
    monkeypatch.setattr(sys, "path", list(sys.path))      # the runner prepends <root>/tools; undo it after
    replica = tmp_path / "src"
    src_of = {dst: src for src, dst in DP.PLAN.items()}
    for remote, local in DP._root_map(R.ROOT).items():
        head = next(d for d in src_of if remote == d or (d.endswith("/") and remote.startswith(d)))
        dst = replica / (src_of[head] + remote[len(head):])
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            dst.write_bytes(local.read_bytes())
        except FileNotFoundError:                          # deleted by another engineer mid-copy: not shipped
            continue
    assert (replica / "vps/forge_loop.sh").exists()        # the source layout, so the plan moves it
    m = DP.manifest(root=replica)
    # the precondition that makes the old `or m["version"]` fallback observable: two different namespaces
    assert m["pipeline_version"] and m["version"] != m["pipeline_version"]

    def stamp(manifest):
        (replica / "DEPLOYED.json").write_text(json.dumps(manifest))
        monkeypatch.setattr(R, "_VERSION", None)
        return R.pipeline_version(replica)

    # the manifest the release engineer writes, over the bytes it describes: the bare id, D14's cohort
    assert stamp(m) == m["pipeline_version"]
    # the same bytes under a manifest that carries only the whole-tree id: untracked, not a MISMATCH
    # (before the fix: `<m["version"]>+MISMATCH`)
    assert stamp({k: v for k, v in m.items() if k != "pipeline_version"}) == m["pipeline_version"] + "+untracked"
    # a hand edit after the deploy (the S1iii case): named, with the id of the bytes that actually run
    with open(replica / "forge/runner.py", "a") as fh:
        fh.write("\n# a hand-rsynced edit\n")
    on_disk = DP.pipeline_version_of(replica)
    assert on_disk != m["pipeline_version"]
    assert stamp(m) == "%s+MISMATCH:%s" % (m["pipeline_version"], on_disk)


def test_an_unlisted_composite_on_a_target_marks_the_stamp_extras(tmp_path, monkeypatch):
    """draw3_fix pipeline 2 and release 1, decided by D40. A TARGET-layout replica (every file at its REMOTE
    path, so forge_loop.sh at the root and no vps/), the real deploy.manifest() of exactly those files as its
    DEPLOYED.json, the real deploy.loop_reachable_extras and the real runner. MEASURED before D40 by the
    adjudicators (scratchpad/adj4_stamp_probe.py, adj3_probe_id.py): a composite copied into
    forge/composites/ without the manifest listing it -- the planner's glob("*.yaml") loads it -- left the
    stamp the bare `6a6ccbe1baf7996c`, the clean replica's own id."""
    import deploy as DP
    if not hasattr(DP, "loop_reachable_extras"):
        pytest.skip("tools/deploy.py has no loop_reachable_extras yet: D40's release half (draw3_fix release 1) "
                    "has not landed in this tree, so the stamp cannot count extras")
    monkeypatch.setattr(sys, "path", list(sys.path))      # the runner prepends <root>/tools; undo it after
    target = tmp_path / "opt_wq"
    for remote, local in DP._root_map(R.ROOT).items():
        dst = target / remote
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            dst.write_bytes(local.read_bytes())
        except FileNotFoundError:                          # deleted by another engineer mid-copy: not shipped
            continue
    assert (target / "forge_loop.sh").exists() and not (target / "vps").exists()      # the target layout
    m = DP.manifest(root=target, fmap=DP._root_map(target))
    (target / "DEPLOYED.json").write_text(json.dumps(m))

    def stamp():
        monkeypatch.setattr(R, "_VERSION", None)
        return R.pipeline_version(target)

    assert stamp() == m["pipeline_version"]                # the clean target: the bare id, D14's cohort
    composite = next(p for p in sorted((target / "forge/composites").glob("*.yaml")))
    (target / "forge/composites/zz_unlisted_extra.yaml").write_bytes(composite.read_bytes())
    assert stamp() == m["pipeline_version"] + "+EXTRAS:1"


# ------------------------------------------------------------------------------------------------ S7
# Architecture rounds 1 and 2, S7 / S7-NL: argparse's default allow_abbrev=True parsed `--liv` as
# `--live` (measured on a mirror parser in round 1), and there was no test-session network guard.


#: The dangerous flag, assembled: tools/ci_gate.check_no_live is a string tripwire and would fire on it
#: as test DATA. Every main() below stops inside parse_args (parse_only), and the conftest refuses any POST
#: made through requests (draw3_fix pipeline 5: not urllib, http.client or a raw socket).
_LIVE = "--" + "live"
#: The dangerous flag, assembled: tools/ci_gate.check_no_live is a string tripwire and would fire on it
#: as test DATA. Every main() below stops inside parse_args (parse_only), and the conftest refuses any POST
#: made through requests (draw3_fix pipeline 5: not urllib, http.client or a raw socket).
#: draw-3 pipeline SERIOUS 2: the literal used to be passed below, and the rewritten gate (2026-09-23 14:29)
#: listed this file as an offender, blocking CI (test_this_file_passes_no_dangerous_flag_literally).
_SUBMIT = "--" + "submit"


class _Parsed(BaseException):
    """Raised INSTEAD of returning from parse_args, so nothing after parsing ever runs in these tests --
    without the fix, an abbreviated live flag would otherwise go on to plan and dispatch."""


@pytest.fixture
def parse_only(monkeypatch):
    import argparse
    real = argparse.ArgumentParser.parse_args

    def stop(self, args=None, namespace=None):
        raise _Parsed(real(self, args, namespace), self)          # the parser too (D30's test reads its options)
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", stop)


def _parsed(call):
    """The namespace main() parsed, or the exit code argparse refused with."""
    try:
        call()
    except _Parsed as p:
        return p.args[0]
    except SystemExit as e:
        return e.code
    raise AssertionError("main() returned without parsing")


@pytest.mark.parametrize("flag", ["--l", "--li", "--liv"])
def test_an_abbreviated_live_is_refused_not_obeyed(parse_only, monkeypatch, flag):
    import layered_sim as LS
    assert _parsed(lambda: R.main([flag])) == 2
    monkeypatch.setattr(sys, "argv", ["layered_sim.py", flag])
    assert _parsed(LS.main) == 2


@pytest.mark.parametrize("flag", ["--s", "--sub", "--subm"])
def test_an_abbreviated_submit_is_refused_not_obeyed(parse_only, flag):
    from forge import submit as SU
    assert _parsed(lambda: SU.main([flag])) == 2


def test_every_command_line_the_live_loop_uses_still_parses(parse_only, monkeypatch):
    """allow_abbrev=False breaks any caller that abbreviates. Every call site, read 2026-09-23: forge_loop.sh
    :60 with wq-forge's FORGE_ARGS (`systemctl show` on the VPS), forge_loop.sh:88, the deploy smoke's
    planner, forge/search.py's recipe flags, climb_loop.sh:112 and /opt/wq's factorial/settings/smoke loops."""
    import layered_sim as LS
    from forge import submit as SU
    ns = _parsed(lambda: R.main(["-n", "300", "--seed", "1", _LIVE, "--concurrency", "9", "--children", "10",
                                 "--mode", "composites", "--order", "USA/d1,d1", "--no-split", "--delays", "1", "--ab", "new"]))
    assert ns.live is True and ns.no_split and ns.delays == "1" and ns.ab == "new"
    ns = _parsed(lambda: R.main(["--mode", "composites", "--cells", "USA/d1:Short%20Interest", "--only", "x", "--cell-cap", "100",
                                 "--per-block", "100", "--decay", "4", "--truncation", "0.15", "--neut", "STATISTICAL",
                                 "--group", "sector", "--universe", "USA:TOP1000", "--smooth", "10", "--power", "2",
                                 "--tag", "R20", "--plan", "p.json"]))
    assert ns.live is False and ns.cell_cap == 100 and ns.per_block == 100 and ns.tag == "R20"
    ns = _parsed(lambda: SU.main([_SUBMIT, "--cap", "4"]))
    assert ns.submit is True and ns.cap == 4
    assert _parsed(lambda: SU.main([])).submit is False
    for argv in (["-n", "90", "--seed", "1", "--climb", _LIVE],
                 ["-n", "320", "--seed", "1", _LIVE, "--concurrency", "8", "--out", "o.jsonl"]):
        monkeypatch.setattr(sys, "argv", ["layered_sim.py"] + argv)
        assert _parsed(LS.main).live is True


@pytest.mark.parametrize("flag", ["--su", "--sub", "--subm", "--submi"])
def test_climb_submit_refuses_an_abbreviated_submit(parse_only, monkeypatch, flag):
    """draw-3 pipeline MINOR 9: tools/climb_submit.py (in deploy.LOOP_ENTRIES; the POST path of the climb)
    parsed `--su`, `--sub` and `--subm` as `submit=True` -- MEASURED before the fix by this very test. Its
    one live caller, climb_loop.sh:210 (read locally and on /opt/wq 2026-09-23), spells `--submit --cap 4`."""
    import climb_submit as CS
    monkeypatch.setattr(sys, "argv", ["climb_submit.py", flag])
    assert _parsed(CS.main) == 2
    monkeypatch.setattr(sys, "argv", ["climb_submit.py", _SUBMIT, "--cap", "4"])
    ns = _parsed(CS.main)
    assert ns.submit is True and ns.cap == 4
    monkeypatch.setattr(sys, "argv", ["climb_submit.py", "--list", "--alpha", "X", "--override-root", "why"])
    ns = _parsed(CS.main)
    assert ns.submit is False and ns.list and ns.alpha == "X" and ns.override_root == "why"


@pytest.mark.parametrize("flag", ["--i", "--i-am", "--i-am-spending-real"])
def test_auto_submit_refuses_an_abbreviated_live_flag(parse_only, flag):
    """draw-3 pipeline MINOR 9: tools/auto_submit.py (in deploy.LOOP_ENTRIES) parsed `--i` as its LIVE flag
    -- `live=True`, irreversible submissions -- MEASURED before the fix by this very test. No shell caller
    exists (grep, locally and on /opt/wq, 2026-09-23); its tests spell the flag in full through AS.LIVE_FLAG."""
    import auto_submit as AS
    assert _parsed(lambda: AS.main(["--region", "USA", "--delay", "1", flag])) == 2
    assert _parsed(lambda: AS.main(["--region", "USA", "--delay", "1", AS.LIVE_FLAG])).live is True
    assert _parsed(lambda: AS.main(["--region", "USA", "--delay", "1"])).live is False


# ------------------------------------------------------------------------------- D30 and design stage 0c
def _differing_argv(action) -> list:
    """An argv that gives one option of the runner's parser a value other than its default, built from the
    parser's own definition of it (so an option added later is covered without editing this test)."""
    opt = max(action.option_strings, key=len)
    if action.nargs == 0:                                  # store_true
        return [opt]
    if action.choices:
        return [opt, next(c for c in action.choices if c != action.default)]
    if action.type is int:
        return [opt, str((action.default or 0) + 7)]
    if action.type is float:
        return [opt, str((action.default or 0) + 0.5)]
    return [opt, "x-" + action.dest]


def test_run_config_ignores_the_round_and_moves_with_every_other_argument(parse_only, tmp_path):
    """D30 (Khoa 2026-09-23 ~15:45; the implementation note in docs/evalharness/00_agreements.md): the arguments
    the runner received are a second stamp, meta.run_config, so a change to N or FORGE_ARGS starts a new
    cohort. Before, nothing but the code's bytes named a cohort, and the wq-forge unit's N and FORGE_ARGS live
    in /etc/systemd, which deploy never writes. The per-round fields (R.RUN_CONFIG_EXCLUDED) must NOT move
    it, or every round would be a cohort of one.
    The D30 amendment (orchestrator decision recorded with D43-D46): the plan file's CONTENT is hashed, not its
    path and not nothing. Before it, the plan path was dropped and this test pinned pow.json == c11.json: two
    different experiment plans were one cohort (draw-4 pipeline 6)."""
    def cfg(argv):
        return R.run_config(_parsed(lambda: R.main(argv)))
    base = cfg([])
    assert len(base) == 16 and int(base, 16) >= 0
    assert set(R.RUN_CONFIG_EXCLUDED) == {"seed", "plan"}
    assert cfg(["--seed", "1"]) == cfg(["--seed", "2"]) == base
    assert cfg(["-n", "300", "--seed", "1"]) != cfg(["-n", "320", "--seed", "1"])
    # the plan's PATH is not configuration, its CONTENT is: one plan under two paths is one cohort, two plans two
    pow_, c11, moved_pow = tmp_path / "pow.json", tmp_path / "c11.json", tmp_path / "elsewhere/pow.json"
    moved_pow.parent.mkdir()
    pow_.write_text(json.dumps({"constructions": [{"formula": "rank(a)", "settings": {}, "meta": {}}]}))
    c11.write_text(json.dumps({"constructions": [{"formula": "rank(b)", "settings": {}, "meta": {}}]}))
    moved_pow.write_bytes(pow_.read_bytes())
    assert cfg(["--plan", str(pow_)]) == cfg(["--plan", str(moved_pow)]) != cfg(["--plan", str(c11)])
    assert base not in (cfg(["--plan", str(pow_)]), cfg(["--plan", str(c11)]))
    # the bytes main() hands over are what is hashed, not a second read of the path
    assert R.run_config(_parsed(lambda: R.main(["--plan", str(pow_)])), c11.read_bytes()) == cfg(["--plan", str(c11)])
    try:
        R.main([])
    except _Parsed as p:
        parser = p.args[1]
    moved = {a.dest: cfg(_differing_argv(a)) != base for a in parser._actions
             if a.option_strings and a.dest != "help" and a.dest not in R.RUN_CONFIG_EXCLUDED}
    assert all(moved.values()), [k for k, v in moved.items() if not v]
    # among them: forge_loop.sh's own flags (read 2026-09-23) and the FORGE_ARGS options that
    # test_every_command_line_the_live_loop_uses_still_parses records for the wq-forge unit
    assert {"n", "live", "concurrency", "children", "mode", "order", "no_split", "delays", "ab", "cells", "only",
            "tag"} <= set(moved)
    # the definition, re-derived here from the namespace: sha256 of the sorted JSON, first 16 hex
    ns = _parsed(lambda: R.main(["--seed", "9", "--mode", "both", "--plan", str(pow_)]))
    body = {k: v for k, v in vars(ns).items() if k not in ("seed", "plan")}
    body.update(plan_given=True, plan_sha256=hashlib.sha256(pow_.read_bytes()).hexdigest())
    assert R.run_config(ns) == hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
    # without --plan the body is exactly the pre-amendment one, so the live loop's run_config does not move
    # (the unit's FORGE_ARGS, read on the VPS 2026-09-23)
    ns = _parsed(lambda: R.main(["-n", "300", "--seed", "1", "--concurrency", "9", "--children", "10", "--mode",
                                 "composites", "--order", "USA/d1,d1", "--no-split", "--delays", "1", "--ab", "new"]))
    body = {k: v for k, v in vars(ns).items() if k not in ("seed", "plan")}
    body["plan_given"] = False
    assert R.run_config(ns) == hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


def _round_through_main(monkeypatch, tmp_path, argv, events=None):
    """main() run to its dispatch with nothing dispatched: the plan file goes to tmp_path/plans, the D45 log to
    tmp_path, no m13 is sent, and layered_sim.run only records the batch it was handed (and "dispatch" in
    `events`, when given). Returns (batch, parsed namespace)."""
    import argparse
    import layered_sim as LS
    parsed, sent = [], []
    real = argparse.ArgumentParser.parse_args

    def keep(self, args=None, namespace=None):
        parsed.append(real(self, args, namespace))
        return parsed[-1]

    def run(n, **kw):
        sent.append(kw["batch"])
        if events is not None:
            events.append("dispatch")
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", keep)
    monkeypatch.setattr(R, "PLANS", tmp_path / "plans")
    monkeypatch.setattr(R, "RUN_CONFIG_LOG", tmp_path / "run_config_log.jsonl")
    monkeypatch.setattr(R, "notify_queue", lambda p, root: None)
    monkeypatch.setattr(LS, "run", run)
    assert R.main(argv) == 0 and len(sent) == 1 and len(parsed) == 1
    return sent[0], parsed[0]


def test_a_plan_round_is_restamped_with_this_process_values(tmp_path, monkeypatch, capsys):
    """D46 (Khoa 2026-09-23 ~20:15), design stage 0c (docs/evalharness/04_passfirst_design.md section 7; code
    audit A6) and D30. main() dispatched a `--plan` file exactly as written: forge/offline/pow_pairs.py and
    c11_neut.py copy `meta` from a journal row, so the round's rows carried the version (and now the
    run_config) of the BASE row, and forge/llm/formula.py's plans carried none. Both stamps are OVERWRITTEN
    with this process's values -- in the batch handed to the dispatcher and in the plan file recover_orphans
    reads -- and printed once (draw3_fix pipeline 7: the runner never printed its stamp). The arm (D47
    groundwork) is PLAN_FILE_ARM where the entry has none, and an arm the plan carries is kept.
    OPEN, pinned as it stands (draw-4 pipeline 5(e)): meta.seed is NOT re-stamped -- the copied row keeps the
    base row's seed 5 under `--seed 77`, and ab_report groups rounds by meta.seed."""
    monkeypatch.setattr(R, "_VERSION", "v-running")
    copied = {"formula": "rank(x)", "settings": {"region": "USA", "delay": 1},
              "meta": {"hypothesis": "h", "recipe": "POW", "seed": 5, "arm": "current",
                       "pipeline_version": "v-of-the-base-row", "run_config": "rc-of-the-base-row"}}
    unstamped = {"formula": "rank(y)", "settings": {"region": "USA", "delay": 1}, "meta": {"hypothesis": "g"}}
    plan = {"seed": 5, "n": 2, "hypotheses": 0, "cells_considered": 0, "gate": {}, "blocks": [],
            "constructions": [copied, unstamped]}
    (tmp_path / "pow.json").write_text(json.dumps(plan))
    reads, real_read = [], pathlib.Path.read_bytes

    def read_bytes(self):
        reads.append(self)
        return real_read(self)
    monkeypatch.setattr(pathlib.Path, "read_bytes", read_bytes)
    batch, ns = _round_through_main(monkeypatch, tmp_path, ["--plan", str(tmp_path / "pow.json"), "--seed", "77"])
    # the plan is read ONCE: the bytes hashed into run_config are the bytes dispatched (D30 amendment)
    assert reads.count(tmp_path / "pow.json") == 1
    rc = R.run_config(ns)
    on_file = json.loads((tmp_path / "plans/77.json").read_text())["constructions"]
    for rows in (batch, on_file):
        assert [c["meta"]["pipeline_version"] for c in rows] == ["v-running", "v-running"]
        assert [c["meta"]["run_config"] for c in rows] == [rc, rc]
        assert [c["meta"]["arm"] for c in rows] == ["current", R.PLAN_FILE_ARM] == ["current", "plan"]
        assert rows[0]["meta"]["hypothesis"] == "h" and rows[0]["meta"]["recipe"] == "POW" and rows[0]["meta"]["seed"] == 5
    assert capsys.readouterr().out.count("forge stamp: pipeline_version v-running, run_config %s\n" % rc) == 1


def test_a_planned_round_carries_the_run_config(tmp_path, monkeypatch):
    """D30 on the planner's own path: every construction main() dispatches carries run_config beside the
    pipeline_version _construction() wrote, and (D47 groundwork) the planning mode as meta.arm."""
    import shutil
    (tmp_path / "tree").mkdir()
    root = _root(tmp_path / "tree")
    shutil.copytree(root / "hyp", root / "forge/hypotheses")
    monkeypatch.setattr(R, "_VERSION", "v-running")
    batch, ns = _round_through_main(monkeypatch, tmp_path, ["--root", str(root), "--mode", "singles", "--no-allocate",
                                                            "-n", "4", "--seed", "3"])
    assert len(batch) == 4
    assert {(c["meta"]["pipeline_version"], c["meta"]["run_config"]) for c in batch} == {("v-running", R.run_config(ns))}
    assert {c["meta"]["arm"] for c in batch} == {"singles"}


def test_the_arm_is_the_planning_mode_and_never_replaces_an_arm_a_row_has(monkeypatch):
    """D47 groundwork (Khoa 2026-09-23 ~21:00): D47 compares ROUNDS of the incumbent (`--mode composites`) with
    rounds of the branch, told apart by meta.arm, which the runner stamps with the planning mode. Before, a
    round without `--ab` carried no arm at all. meta.arm already holds labels other readers group by -- the
    `--ab` arms ab_report and rung_report read, and the live FORGE_ARGS carry `--ab new` -- and the experiment
    plans' own arms, so the stamp fills an ABSENT arm only: today's live rows do not change."""
    monkeypatch.setattr(R, "_VERSION", "v-running")
    rows = [{"formula": "a", "meta": {}}, {"formula": "b"}, {"formula": "c", "meta": {"arm": "current"}},
            {"formula": "d", "meta": {"arm": "new"}}, {"formula": "e", "meta": {"arm": "typed"}},
            {"formula": "f", "meta": {"arm": "llmformula"}}]
    R.stamp(rows, "rc1", "composites")
    assert [r["meta"]["arm"] for r in rows] == ["composites", "composites", "current", "new", "typed", "llmformula"]
    assert {(r["meta"]["pipeline_version"], r["meta"]["run_config"]) for r in rows} == {("v-running", "rc1")}


# ------------------------------------------------------------------------------------------------ D45
def test_a_live_start_records_a_run_config_transition_once(tmp_path, monkeypatch):
    """D45 (Khoa 2026-09-23 ~20:15): a cohort's exposure comes from run_config transitions the runner records.
    The shared interface: {"at", "pipeline_version", "run_config", "host"} appended when the runner starts with
    a (pv, rc) different from the LAST ROW FOR ITS HOST. Before, nothing recorded a transition, so a cohort's
    live days could only be guessed."""
    log = tmp_path / "state/forge/run_config_log.jsonl"
    steps = [("V1", "r1", "vps", True),        # the first start
             ("V1", "r1", "vps", False),       # the loop restarts unchanged: nothing
             ("V1", "r2", "vps", True),        # FORGE_ARGS changed
             ("V1", "r2", "mac", True),        # another host: its last row is its own
             ("V1", "r2", "vps", False),       # ... and does not count as this host's
             ("V2", "r2", "vps", True),        # a deploy moved the version
             ("V1", "r1", "vps", True)]        # a rollback to an earlier pair is a transition too
    for i, (pv, rc, host, wrote) in enumerate(steps):
        assert R.record_run_config(pv, rc, log, host=host, now=float(i)) is wrote, (i, pv, rc, host)
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert rows == [{"at": float(i), "pipeline_version": pv, "run_config": rc, "host": host}
                    for i, (pv, rc, host, wrote) in enumerate(steps) if wrote]
    # a torn last line (a crash mid-write) is skipped, and the next row starts on a line of its own
    with open(log, "a") as fh:
        fh.write('{"at": 9, "pipeline_ver')
    monkeypatch.setattr(R, "RUN_CONFIG_LOG", log)                    # the defaults: this log, this machine's name
    assert R.record_run_config("V3", "r3", now=10.0) is True
    lines = log.read_text().splitlines()
    assert lines[-2] == '{"at": 9, "pipeline_ver'
    assert json.loads(lines[-1]) == {"at": 10.0, "pipeline_version": "V3", "run_config": "r3",
                                     "host": socket.gethostname()}


def test_two_starts_at_once_record_one_transition(tmp_path):
    """D45 "atomically": the read of the last row and the append are one step under an exclusive flock on the log.
    This test holds that lock while a second process calls record_run_config for the same (pv, rc, host), writes
    the row itself, then lets go: the other process must find the row and write nothing. Without the lock it
    reads the empty log at once and appends a second row for one transition."""
    import fcntl
    import time
    log = tmp_path / "run_config_log.jsonl"
    child = textwrap.dedent("""
        import sys
        sys.path.insert(0, %r)
        from forge import runner as R
        print("ready", flush=True)
        print(R.record_run_config("V1", "r1", %r, host="vps", now=2.0), flush=True)
    """ % (str(R.ROOT), str(log)))
    with open(log, "a+b") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        p = subprocess.Popen([sys.executable, "-B", "-c", child], stdout=subprocess.PIPE, text=True,
                             env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        assert p.stdout.readline().strip() == "ready"
        time.sleep(0.5)                                  # the other process is at (or blocked in) its read
        row = json.dumps({"at": 1.0, "pipeline_version": "V1", "run_config": "r1", "host": "vps"}) + "\n"
        os.write(fh.fileno(), row.encode())
    out, _ = p.communicate(timeout=60)
    assert p.returncode == 0 and out.strip() == "False", out
    assert [json.loads(line)["at"] for line in log.read_text().splitlines()] == [1.0]


def test_only_a_live_start_is_recorded_and_a_failure_never_stops_the_round(tmp_path, capsys):
    """D45 as the runner applies it. A dry run journals nothing (tools/layered_sim.py _dispatch), and run_config
    hashes `live`, so the deploy smoke's planner on /opt/wq would otherwise append a (new version, smoke
    run_config) row on every push (architecture round 3 X3). A log that cannot be written is printed, loudly,
    and the round goes on (the task's rule for D45)."""
    log = tmp_path / "log.jsonl"
    R.note_run_config(False, "V1", "r1", log)
    assert not log.exists()
    R.note_run_config(True, "V1", "r1", log)
    assert [json.loads(line)["run_config"] for line in log.read_text().splitlines()] == ["r1"]
    blocked = tmp_path / "blocked"
    blocked.mkdir()                                                  # a directory where the log should be
    R.note_run_config(True, "V1", "r2", blocked)                      # returns: nothing raised
    out = capsys.readouterr().out
    assert "!!! D45 RUN_CONFIG LOG NOT WRITTEN (IsADirectoryError" in out and "(V1, r2)" in out


def test_main_notes_the_start_once_before_it_dispatches(tmp_path, monkeypatch):
    """main() hands note_run_config the parsed `live`, the stamp and the run_config, once, before dispatch (a
    round that dies mid-dispatch still has its exposure row). Run without the live flag (RULE 1): the call is
    recorded, not executed."""
    monkeypatch.setattr(R, "_VERSION", "v-running")
    events = []
    monkeypatch.setattr(R, "note_run_config", lambda live, pv, rc, path=None: events.append((live, pv, rc)))
    (tmp_path / "exp.json").write_text(json.dumps({"n": 1, "hypotheses": 0, "cells_considered": 0, "gate": {},
                                                   "blocks": [], "constructions": [{"formula": "rank(x)",
                                                                                     "settings": {"delay": 1},
                                                                                     "meta": {}}]}))
    batch, ns = _round_through_main(monkeypatch, tmp_path, ["--plan", str(tmp_path / "exp.json"), "--seed", "4"],
                                    events=events)
    assert events == [(False, "v-running", R.run_config(ns)), "dispatch"]


# ------------------------------------------------------------------------------------------------ P3
def test_the_version_with_no_root_is_the_version_of_the_runners_own_tree(tmp_path, monkeypatch):
    """draw-4 pipeline 3 / P3: production calls pipeline_version() with NO root, and mutant B03 -- `extras(root)`
    for `extras(base)` -- left every test green (181 passed), while in production it would stamp every row
    `unknown` or `+unverified` (EX-ANTE, the adjudicator's code path). The no-root call must ask deploy about
    R.ROOT, for the bytes AND for the D40 extras, and give what the explicit call gives."""
    import deploy as DP
    monkeypatch.setattr(sys, "path", list(sys.path))      # the runner prepends <root>/tools; undo it after
    replica = tmp_path / "replica"
    replica.mkdir()
    (replica / "DEPLOYED.json").write_text(json.dumps({"pipeline_version": "c1051e000000000a"}))
    asked = []

    def of(root):
        asked.append(("bytes", pathlib.Path(root)))
        return "c1051e000000000a"

    def extras(root):
        asked.append(("extras", pathlib.Path(root)))
        return ["forge/composites/zz.yaml"]
    monkeypatch.setattr(DP, "pipeline_version_of", of)
    monkeypatch.setattr(DP, "loop_reachable_extras", extras, raising=False)
    monkeypatch.setattr(R, "ROOT", replica)
    monkeypatch.setattr(R, "_VERSION", None)
    rooted = R.pipeline_version(replica)
    asked.clear()
    monkeypatch.setattr(R, "_VERSION", None)
    assert R.pipeline_version() == rooted == "c1051e000000000a+EXTRAS:1"
    assert asked == [("bytes", replica), ("extras", replica)]


def test_this_file_passes_no_dangerous_flag_literally(tmp_path):
    """draw-3 pipeline SERIOUS 2: this file passed the submit flag as a literal, and the rewritten
    ci_gate.check_no_live (2026-09-23 14:29) named it `forge/tests/test_runner.py:488` -- a blocking
    offender. The real gate, run over a tree that holds only this file at its repository path."""
    import ci_gate as CG
    here = pathlib.Path(__file__)
    dst = tmp_path / "forge/tests" / here.name
    dst.parent.mkdir(parents=True)
    dst.write_text(here.read_text())
    got = CG.check_no_live(tmp_path)
    assert got["ok"] and got["details"] == [], got["details"]


def test_notify_lint_passes_no_flag_without_its_exemption(tmp_path, monkeypatch):
    """draw3_fix ci 9 / draw-4 build (notify_lint COMMAND_TOKENS NOT LANDED): tools/notify_lint.py spelled the
    submit flag as a literal in the tuple of tokens it SEARCHES messages for, and ci_gate kept an exemption for
    that exact line with no tick on file. The token is now assembled; the real gate, with its exemption list
    emptied, finds nothing in the real file at its repository path. The lint still refuses the flag."""
    import ci_gate as CG
    import notify_lint as NL
    dst = tmp_path / "tools/notify_lint.py"
    dst.parent.mkdir(parents=True)
    dst.write_text((R.ROOT / "tools/notify_lint.py").read_text())
    monkeypatch.setattr(CG, "NO_LIVE_EXEMPT", {})
    got = CG.check_no_live(tmp_path)
    assert got["ok"] and got["details"] == [], got["details"]
    assert _SUBMIT in NL.COMMAND_TOKENS
    assert [rule for rule, _ in NL.check_message("run it with " + _SUBMIT)] == ["IRREVERSIBLE_COMMAND"]


_NOWHERE = "https://example.invalid/simulations"   # RFC 6761: never resolves, so a missing guard reaches no one


def _refused(post) -> str:
    """The name of what a POST attempt raised ("returned" if nothing did)."""
    try:
        post()
    except BaseException as e:                              # noqa: BLE001 -- RealPostFromTest is one
        return type(e).__name__
    return "returned"


def _posts(url):
    """Every requests path to a POST the guard must refuse. Under the first, function-scoped guard the bytes
    method and Session.send reached the network (draw-3 pipeline MINOR 8; re-measured 2026-09-23: ProxyError
    through a dead proxy); the lower-case method was already refused and is here so that it stays refused.
    The last three hand-build the PreparedRequest (draw3_fix pipeline 3): Session.request upper-cases and
    str()s the method before the transport sees it, so the guard's own .upper(), .strip() and bytes branch
    were untested -- the adjudicator's three mutants, each alone, still passed every guard test -- while a
    hand-built request reaches the transport with the method exactly as written."""
    import requests

    def send():
        s = requests.Session()
        return s.send(s.prepare_request(requests.Request("POST", url)), timeout=1)

    def send_as(method):
        def go():
            prepared = requests.Request("GET", url).prepare()
            prepared.method = method
            return requests.Session().send(prepared, timeout=1)
        return go
    return {"requests.post": lambda: requests.post(url, json={}, timeout=1),
            "Session.post": lambda: requests.Session().post(url, json={}, timeout=1),
            "Session.request": lambda: requests.Session().request("POST", url, json={}, timeout=1),
            "Session.request(bytes)": lambda: requests.Session().request(b"POST", url, timeout=1),
            "Session.request(lower)": lambda: requests.Session().request("post", url, timeout=1),
            "Session.send": send,
            "Session.send(prepared 'post')": send_as("post"),
            "Session.send(prepared b'POST')": send_as(b"POST"),
            "Session.send(prepared ' POST ')": send_as(" POST ")}


@pytest.fixture(scope="module")
def _a_module_scoped_post():
    """draw-3 pipeline MINOR 8: a module-scoped fixture runs BEFORE any function-scoped one, so the first
    guard (function-scoped autouse) was not yet installed when this POSTed. It is attempted once, here."""
    return {name: _refused(post) for name, post in _posts(_NOWHERE).items()}


def test_no_test_can_make_a_real_post(_a_module_scoped_post):
    """The conftest guard is on for this directory: every requests POST path raises, and the dispatcher's
    own retrying POST (`_post_patient` retries any Exception) stops at the first try."""
    import requests
    import layered_sim as LS
    assert {name: _refused(post) for name, post in _posts(_NOWHERE).items()} == dict.fromkeys(_posts(_NOWHERE),
                                                                                             "RealPostFromTest")
    assert _a_module_scoped_post == dict.fromkeys(_posts(_NOWHERE), "RealPostFromTest")
    slept = []
    with pytest.raises(BaseException) as e:
        LS._post_patient(requests.Session(), _NOWHERE, {}, timeout=1, sleep=slept.append)
    assert type(e.value).__name__ == "RealPostFromTest" and slept == []


@pytest.mark.parametrize("where", ["conftest.py", "forge/tests/conftest.py", "tools/tests/conftest.py"])
def test_each_copy_of_the_post_guard_works_on_its_own(tmp_path, where):
    """The CI checkout and /opt/wq carry forge/ and tools/ but not the repository root, so each copy of
    the guard must stand alone: a fresh pytest, outside the repository, with only that copy."""
    src = R.ROOT / where
    if not src.exists():
        pytest.skip("%s is not in this tree (the repository-root file is not shipped)" % where)
    (tmp_path / "conftest.py").write_text(src.read_text())
    (tmp_path / "test_guard.py").write_text(textwrap.dedent('''
        import pytest
        import requests
        URL = %r

        def _send():
            s = requests.Session()
            return s.send(s.prepare_request(requests.Request("POST", URL)), timeout=1)

        def _send_as(method):                   # draw3_fix pipeline 3: the method exactly as written
            def go():
                prepared = requests.Request("GET", URL).prepare()
                prepared.method = method
                return requests.Session().send(prepared, timeout=1)
            return go

        POSTS = [
            lambda: requests.post(URL, timeout=1),
            lambda: requests.Session().post(URL, timeout=1),
            lambda: requests.Session().request("POST", URL, timeout=1),
            lambda: requests.Session().request(b"POST", URL, timeout=1),     # draw-3 pipeline MINOR 8
            lambda: requests.Session().request("post", URL, timeout=1),
            _send,
            _send_as("post"),
            _send_as(b"POST"),
            _send_as(" POST "),
        ]

        def _raised(post):
            try:
                post()
            except BaseException as e:
                return e
            return None

        @pytest.fixture(scope="module")
        def module_posts():                     # before any function-scoped fixture (MINOR 8)
            return [_raised(p) for p in POSTS]

        @pytest.mark.parametrize("i", range(len(POSTS)))
        def test_post_is_refused(i, module_posts):
            for e in (_raised(POSTS[i]), module_posts[i]):
                assert type(e).__name__ == "RealPostFromTest" and not isinstance(e, Exception), repr(e)
    ''' % _NOWHERE))
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(tmp_path)],
                       cwd=str(tmp_path), capture_output=True, text=True, timeout=180)
    assert r.returncode == 0 and "9 passed" in r.stdout, r.stdout[-2000:]


# ------------------------------------------------------------------------------ design stage 4: `--mode gen`
def _gen_root(tmp_path, rows=()):
    """A tree the pass-first generator can plan on: the gen tests' synthetic label vocabulary (hermetic; shared by every
    test_gen_*.py) as fetched/rc/field_labels.jsonl and as the USA/TOP3000/d1 catalogue, the five USA/d1 pyramid
    categories with nothing filled, an empty library (lib/ and forge/hypotheses/), and `rows` as the forge journal."""
    from forge.tests.test_gen_productions import CATS, synthetic_labels
    labs = synthetic_labels()
    for d in ("state/layered/runs", "fetched/rc/fields", "lib", "forge/hypotheses"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "fetched/rc/field_labels.jsonl").write_text("".join(json.dumps(v) + "\n" for v in labs.values()))
    (tmp_path / "fetched/rc/fields/USA_TOP3000_d1.jsonl").write_text("".join(
        json.dumps({"id": v["id"], "type": v["structure"], "dataset": {"id": v["dataset"]},
                    "category": {"name": v["category"]}}) + "\n" for v in labs.values()))
    json.dump({"pairs": [{"region": "USA", "delay": 1, "counts": dict.fromkeys(CATS, 0)}]},
              open(tmp_path / "state/pyramid_cell_counts.json", "w"))
    json.dump({"USA_TOP3000_d1": [{"id": "ds%02d" % i, "category": {"name": CATS[i % len(CATS)]}, "userCount": 5,
                                   "pyramidMultiplier": 1.0} for i in range(40)]},
              open(tmp_path / "fetched/rc/datasets_survey.json", "w"))
    _journal(tmp_path, rows)
    return tmp_path


def _journal(root, rows):
    (root / "state/layered/runs/forge.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def _gen_plan(root, n=40, seed=3, **kw):
    return R.plan(root, n=n, seed=seed, library_dir=root / "lib", mode="gen", **kw)


def _jrow(cand, alpha, sharpe=2.0, fails=(), **meta):
    """A journal row for a planned construction: COMPLETE, the two Sharpe-like checks PASS unless named in `fails`."""
    checks = [{"name": n, "result": "FAIL" if n in fails else "PASS", "limit": lim, "value": sharpe}
              for n, lim in (("LOW_SHARPE", 1.58), ("LOW_FITNESS", 1.0))]
    return {"alpha": alpha, "status": "COMPLETE", "formula": cand["formula"], "settings": cand["settings"],
            "sharpe": sharpe, "checks": checks, "meta": dict(cand["meta"], run_config="rc", **meta)}


def test_a_gen_round_is_planned_by_the_generator_and_stamped_by_the_runner(tmp_path):
    """Design stage 4 (docs/evalharness/04_passfirst_design.md §4.1, §7; D20, D35): `--mode gen` plans the round from
    forge.gen.propose on the loop's state -- no library hypothesis, no composite -- and every construction goes
    through _construction. Before, plan(mode="gen") took the library's categories, found no cell for an empty
    library and planned nothing, and argparse refused `--mode gen` (architecture round 4 m13)."""
    import collections
    from forge import factory as F
    from forge.gen import propose as PR
    root = _gen_root(tmp_path)
    p = _gen_plan(root)
    cs = p["constructions"]
    assert len(cs) == 40 and p["mode"] == "gen" and p["gate"]["ok"] == 40 and p["by_arm"] == {"gen": 40}
    sha = R.gen_state(root).sha
    for c in cs:
        m = c["meta"]
        assert m["hypothesis"].startswith("gen:") and m["gen_route"] in PR.ROUTES and m["gen_state"] == sha
        assert m["forge"] == 1 and m["seed"] == 3 and m["cand"] == F.candidate_id(c["formula"], c["settings"])
        assert m["pipeline_version"] == R.pipeline_version() and m["arm"] == "gen"
    assert p["gen"]["by_route"] == {"fresh": 40} and p["gen"]["n_floor"] == 8 and p["gen"]["gen_state"] == sha
    kept = collections.Counter()
    for b in p["blocks"]:
        kept[b["cell"]] += b["kept"]
    assert sum(kept.values()) == 40 and max(kept.values()) <= 60 and p["blocks_by_class"] == {"GEN": len(p["blocks"])}
    assert "gen: state %s" % sha in R.summarize(p)
    assert R.plan(root, n=40, seed=3, library_dir=root / "lib", mode="composites")["constructions"] == []
    # a recipe's wrappers never reach a generated formula (D35 keeps §2.3's signed_power exclusion); its tag does
    r = _gen_plan(root, recipe={"power": 2, "smooth": 10, "tag": "R9"})
    assert [c["formula"] for c in r["constructions"]] == [c["formula"] for c in cs]
    assert {c["meta"]["recipe"] for c in r["constructions"]} == {"R9"}


def test_every_generated_candidate_passes_the_composite_chain_in_its_order(tmp_path, monkeypatch):
    """§4.1: "the pre-sim chain must be the composite chain" -- made_ids -> quarantine -> structurally_ok ->
    PreSimGate.check, _composite_block's order (code audit Y23: the typed and ensemble arms skipped quarantine and
    the structure gate). Each link refuses here on its own, and a candidate a link before the gate refused never
    reached the gate, which charges its budget and marks the id seen for what it passes."""
    from forge import harvest as HV
    root = _gen_root(tmp_path)
    first = _gen_plan(root)["constructions"]
    # the journal's ids reach the generator: the same seed with the first round journalled (no alpha, so the state
    # is unchanged and the round's first draw is the first round's) re-plans none of it
    _journal(root, [{"formula": c["formula"], "settings": c["settings"], "status": "ERROR"} for c in first])
    again = _gen_plan(root)
    assert not {c["meta"]["cand"] for c in again["constructions"]} & {c["meta"]["cand"] for c in first}
    assert again["gen"]["counts"]["duplicate"] >= 1 and len(again["constructions"]) == 40   # the first draw recurs
    _journal(root, [])
    # quarantine, D36's (cell, field) key: every field of the first draw
    f0 = HV.row_fields(first[0])
    (root / "state/forge").mkdir(parents=True)
    (root / R.QUARANTINE).write_text(json.dumps([HV.field_quarantine_key("USA", 1, f) for f in f0]))
    q = _gen_plan(root)
    assert q["gen"]["counts"]["quarantined"] >= 1 and len(q["constructions"]) == 40
    assert not any(set(HV.row_fields(c)) & set(f0) for c in q["constructions"])
    m0 = first[0]["meta"]           # and the composite chain's own key, under the draw's gen:<family> hypothesis
    (root / R.QUARANTINE).write_text(json.dumps([HV.quarantine_key(m0["hypothesis"], "USA", 1, m0["category"], m0["field"])]))
    h = _gen_plan(root)
    assert h["gen"]["counts"]["quarantined"] >= 1 and first[0]["meta"]["cand"] not in {c["meta"]["cand"] for c in h["constructions"]}
    (root / R.QUARANTINE).write_text("[]")
    # the runner's OWN structural gate (propose checks with forge.typed directly; this stub reaches the runner only)
    real = R.TY

    class Judge:
        @staticmethod
        def judge(formula, labels, cell, structural=False):
            if "ts_rank(" in formula:
                return {"ok": False, "hard": ["H1 stub refusal"]}
            return real.judge(formula, labels, cell, structural=structural)
    monkeypatch.setattr(R, "TY", Judge)
    s = _gen_plan(root)
    assert s["structure_refused"].get("H1", 0) >= 1 and not any("ts_rank(" in c["formula"] for c in s["constructions"])
    assert sum(s["gate"].values()) == s["gate"]["ok"] == len(s["constructions"]) == 40
    monkeypatch.setattr(R, "TY", real)
    # the gate: an active book that already holds the first draw's signature
    sig0 = first[0]["meta"]["signature"]

    class Book:
        @staticmethod
        def is_novel(sig):
            return sig["key"] != sig0
    monkeypatch.setattr(R, "novelty_index", lambda root, cat: Book())
    g = _gen_plan(root)
    assert g["gate"]["not-novel"] >= 1 and sig0 not in {c["meta"]["signature"] for c in g["constructions"]}


def test_a_generated_candidate_off_the_route_interface_is_refused(tmp_path, monkeypatch):
    """The shared interface: a generated construction carries meta.gen_route in {"fresh", "neighbour", "repair"}, and
    D54 counts only "fresh". A candidate carrying anything else -- "draw", the value forge/gen/propose.py stamped in
    the Draw 5 tree -- is refused before the chain and counted, so no such row reaches the journal."""
    from forge.gen import productions as P
    real = P.candidate

    def old_route(*a, **k):
        c = real(*a, **k)
        c["meta"]["gen_route"] = "draw"
        return c
    monkeypatch.setattr(P, "candidate", old_route)
    p = _gen_plan(_gen_root(tmp_path), n=2)
    assert p["constructions"] == [] and p["gen"]["counts"]["gen-route-invalid"] >= 2 and p["gate"]["ok"] == 0


def test_a_generated_pass_gets_its_d51_neighbours_first_and_a_trigger_its_d37_repairs(tmp_path):
    """D51 (each generated alpha that clears every check is re-simulated at two one-setting neighbours) and D37 (a row
    failing exactly one check gets its settings grid, at most 10 % of a round, by its coin). The runner hands
    propose every provable row of its state: G1 has no neighbour and gets two, first; G2 already has two in the
    journal -- one of them a LIBRARY row with G2's formula, cohort and cell, which gen_state must keep
    (repair.existing_neighbours counts it) -- and gets none; the trigger T gets floor(0.1 x 30) = 3 repairs."""
    from forge.gen import repair as RP
    root = _gen_root(tmp_path)
    made = _gen_plan(root, n=60)["constructions"]
    g1, g2 = made[0], made[1]
    trig = next(c for c in made[2:] if RP.coin(c["formula"]))
    lib_n, gen_n = RP.one_setting_variants(g2["settings"])[:2]
    rows = [_jrow(g1, "G1"), _jrow(g2, "G2"),
            _jrow(dict(g2, settings=lib_n, meta={"forge": 1, "hypothesis": "lib_h", "category": g2["meta"]["category"],
                                                   "pipeline_version": g2["meta"]["pipeline_version"]}), "N2a", sharpe=1.0,
                  fails=("LOW_SHARPE", "LOW_FITNESS")),
            _jrow(dict(g2, settings=gen_n), "N2b", sharpe=1.0, fails=("LOW_SHARPE", "LOW_FITNESS"), gen_route="neighbour"),
            _jrow(trig, "T1", sharpe=1.7, fails=("LOW_FITNESS",))]
    _journal(root, rows)
    p = _gen_plan(root, n=30, seed=4)
    cs = p["constructions"]
    assert p["gen"]["handed"] == 2 and p["gen"]["by_route"] == {"neighbour": 2, "repair": 3, "fresh": 25}
    assert [c["meta"].get("neighbour_of") for c in cs[:2]] == ["G1", "G1"]
    for c in cs[:2]:
        assert c["meta"]["gen_route"] == "neighbour" and c["formula"] == g1["formula"]
        assert sum(str(c["settings"][k]) != str(g1["settings"][k]) for k in ("neutralization", "decay", "truncation")) == 1
    assert not any(c["meta"].get("neighbour_of") == "G2" for c in cs)
    reps = [c for c in cs if c["meta"]["gen_route"] == "repair"]
    assert len(reps) == 3 and {(c["meta"]["repair_of"], c["formula"]) for c in reps} == {("T1", trig["formula"])}
    assert sum(b["kept"] for b in p["blocks"]) == 30               # neighbours and repairs are charged to their cell


def test_the_runners_generator_state_is_the_generators_own(tmp_path):
    """D58 x design §3.2. gen_state(root) reads the journal in two passes and keeps only the rows the state reads; it
    must give exactly what forge.gen.state.load(root) gives -- the same sha, the same proposal -- on a journal holding
    every kind it keeps and several it drops: a POSTed library alpha whose submit-log row has no formula (novelty's
    journal fallback), a library row that is a generated pass's one-setting neighbour, cached curves of a POST and of
    a generated pass (the PnL stop), a trigger, repeats, library rows, a PARENT-POSTED row and a broken line. And the
    latest line decides, as in forge_rows: alpha X was generated on an earlier line and is a library row on its latest,
    so neither X nor a library row Y sharing X's old formula key is kept (a key kept from X's earlier line would keep
    both)."""
    import random
    from forge.gen import propose as PR, repair as RP, state as GS
    from forge.tests.test_gen_productions import CELLS, LABS
    from forge.tests.test_gen_spend import _curve, _walk
    root = _gen_root(tmp_path)
    made = _gen_plan(root, n=40)["constructions"]
    g1, trig = made[0], next(c for c in made[1:] if RP.coin(c["formula"]))
    c2 = next(c for c in made[1:] if c["formula"] not in (g1["formula"], trig["formula"]))
    as_lib = {"forge": 1, "hypothesis": "lib_h", "category": "Option"}
    was_gen = [_jrow(c2, "X"), _jrow(dict(c2, meta=as_lib), "X"),
               _jrow(dict(c2, settings=RP.one_setting_variants(c2["settings"])[0], meta=as_lib), "Y")]
    lib = [{"alpha": "L%d" % i, "status": "COMPLETE", "formula": "rank(x%d)" % i, "sharpe": 0.5, "checks": [],
            "settings": {"region": "USA", "delay": 1, "universe": "TOP3000"},
            "meta": {"forge": 1, "hypothesis": "lib_h", "category": "Option"}} for i in range(5)]
    posted = dict(lib[0], alpha="P1", formula="multiply(rank(x1), rank(x2))")
    lib_neighbour = _jrow(dict(g1, settings=RP.one_setting_variants(g1["settings"])[0],
                               meta={"forge": 1, "hypothesis": "lib_h", "pipeline_version": g1["meta"]["pipeline_version"]}),
                          "LN", sharpe=1.2, fails=("LOW_SHARPE",))
    rows = lib + [posted, _jrow(g1, "G1"), lib_neighbour, _jrow(trig, "T1", sharpe=1.7, fails=("LOW_FITNESS",)),
                  {"status": "PARENT-POSTED", "parent_url": "u"}, dict(lib[1], sharpe=0.6)] + was_gen
    _journal(root, rows)
    with open(root / "state/layered/runs/forge.jsonl", "a") as fh:
        fh.write("broken\n")
    (root / "state/forge").mkdir(parents=True)
    (root / "state/forge/submitted.jsonl").write_text(json.dumps({"alpha": "P1", "http": 200}) + "\n")
    (root / "state/pnl_curves").mkdir(parents=True)
    walk = _walk(random.Random(5))
    for a in ("P1", "G1"):
        (root / ("state/pnl_curves/%s.json" % a)).write_text(json.dumps(_curve(walk)))
    mine, theirs = R.gen_state(root), GS.load(root)
    assert mine.sha == theirs.sha and mine.stopped and not mine.structures.missing
    assert set(mine.rows) == {"P1", "G1", "LN", "T1"} and len(theirs.rows) == 11
    kw = dict(labels=LABS, cells=CELLS, n=10, seed=9, handed=[r for r in theirs.rows.values() if RP.provable(r)])
    assert PR.propose(mine, **kw) == PR.propose(theirs, **kw)


# ---------------------------------------------------------------------------------------------- D58
def test_the_bounded_reader_gives_what_forge_rows_gives_in_its_order(tmp_path):
    """D58: journal_rows(path) must be harvest.forge_rows(path).values() -- the latest row of each alpha, in the order
    the alphas FIRST appeared -- because allocate.pair_states keeps the first best Sharpe on a tie (`sh > best`), so
    the order decides a pair's best_fails. Repeats (A's latest line comes after B), non-forge rows, a PARENT-POSTED
    row, a blank, a broken and a torn last line."""
    from forge import allocate as AL, harvest as HV, score as SC

    def row(a, fail):
        return {"alpha": a, "sharpe": 1.5, "status": "COMPLETE", "formula": "f", "settings": {"region": "USA", "delay": 1},
                "checks": [{"name": "LOW_SHARPE", "result": "PASS"}, {"name": fail, "result": "FAIL"}],
                "meta": {"forge": 1, "hypothesis": "h", "category": "News"}}
    rows = [row("A", "LOW_FITNESS"), row("B", "CONCENTRATED_WEIGHT"), {"status": "PARENT-POSTED", "parent_url": "u"},
            row("A", "LOW_SUB_UNIVERSE_SHARPE"), {"alpha": "Z", "meta": {"move": "wrap"}}, row("C", "LOW_FITNESS")]
    p = tmp_path / "forge.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows) + "\nbroken\n" + '{"alpha": "D", "meta": {"forge"')
    want = list(HV.forge_rows(p).values())
    assert list(R.journal_rows(p)) == want and [r["alpha"] for r in want] == ["A", "B", "C"]
    st = AL.pair_states(R.journal_rows(p), set())
    assert st == AL.pair_states(HV.forge_rows(p), set())
    assert st[("h", "USA/d1", "News")]["best_fails"] == SC.stage(rows[3])["failed"] == ["LOW_SUB_UNIVERSE_SHARPE"]
    assert list(R.journal_rows(tmp_path / "absent.jsonl")) == [] and R.journal_index(tmp_path / "absent.jsonl") == {}


def _heavy_rows(n, pad=0):
    """n forge rows shaped like the journal's (~3 KB each: twelve checks with themes and pyramids, settings, meta),
    spread over 12 hypotheses so the allocator's pair count does not grow with n; `pad` bytes more per row."""
    names = ("LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER", "HIGH_TURNOVER", "CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE",
             "IS_LADDER_SHARPE", "LOW_2Y_SHARPE", "SELF_CORRELATION", "PROD_CORRELATION", "MATCHES_PYRAMID", "MATCHES_THEMES")
    for i in range(n):
        checks = [{"name": nm, "result": "PASS", "limit": 1.0, "value": 1.2 + i % 7, "startDate": "2020-01-01",
                   "themes": [{"id": "theme%d" % k, "name": "a theme name", "multiplier": 1.5} for k in range(2)],
                   "pyramids": [{"name": "USA/D1/NEWS", "multiplier": 1.2}]} for nm in names]
        if pad:
            checks[0]["junk"] = "x" * pad
        yield {"alpha": "A%06d" % i, "status": "COMPLETE", "sharpe": 0.5 + (i % 13) / 10, "fitness": 0.8, "turnover": 0.1,
               "formula": "multiply(group_rank(ts_mean(fld_%d, 5), sector), rank(other_%d))" % (i, i),
               "settings": {"region": "USA", "universe": "TOP3000", "delay": 1, "neutralization": "INDUSTRY", "decay": 4,
                            "truncation": 0.08, "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF"},
               "checks": checks, "sim_url": "https://example.invalid/%d" % i, "parent_url": "https://example.invalid/p",
               "meta": {"forge": 1, "hypothesis": "hyp_%d" % (i % 12), "category": "News", "field": "fld_%d" % i,
                        "mechanism_key": "hyp_%d#news29#USA/d1" % (i % 12), "signature": "news29#smooth#USA/d1",
                        "seed": 1, "cand": "c%d" % i, "legs": ["l1", "l2"]}}


def test_the_planners_peak_memory_does_not_grow_with_the_journal(tmp_path):
    """D58 (Khoa 2026-09-24 ~02:20; architecture round 4 S4: ~17 KB per distinct alpha, 1,506 MB on the Mac journal,
    no limit on the host): the runner reads the journal with bounded memory. MEASURED (python peak, tracemalloc)
    for the allocator's planner (composites' journal path: mode singles here, the allocator on) and for a gen round,
    each on 1,000 and on 4,000 journal alphas, and on 1,000 alphas each 20 KB heavier. Before (harvest.forge_rows)
    the peak grew with every byte of every row; after, only the per-alpha index remains (bound: 1,024 bytes per added
    alpha, and 1 MB for 20 MB of added row bytes). Measured on the Mac journal, peak RSS of the live composites planner:
    1,434 MB before and 905 MB after at 1x, 1,966 and 903 MB at 2x (the D58 comment in forge/runner.py). The heavy rows
    are LIBRARY rows: a generated row is kept whole by the generator's state (design §3.2), which this test does not
    bound (the D58 comment names that growth and routes it)."""
    import tracemalloc

    def peak(n, pad, gen, traced=True):
        root = _gen_root(tmp_path / ("t%d" % len(list(tmp_path.iterdir()))))
        (root / "lib/a.yaml").write_text(HYP)
        _journal(root, _heavy_rows(n, pad))
        if traced:
            tracemalloc.start()
        try:
            if gen:
                p = _gen_plan(root, n=20)
            else:
                p = R.plan(root, n=20, seed=1, library_dir=root / "lib", mode="singles", allocate=True)
            return (tracemalloc.get_traced_memory()[1] if traced else 0), p
        finally:
            tracemalloc.stop()
    for gen in (False, True):
        peak(10, 0, gen, traced=False)          # lazy imports and caches first: the first traced plan would carry them
        small, p = peak(1000, 0, gen)
        big, _ = peak(4000, 0, gen)
        fat, _ = peak(1000, 20000, gen)
        assert (not gen and p["pair_classes"]) or (gen and p["gen"]["n_draws"] == 20 and not p["pair_classes"])
        assert (big - small) / 3000 < 1024, (gen, small, big)
        assert fat - small < 2 ** 20, (gen, small, fat)


# ------------------------------------------------------------------------------------ D47 / D53 / D54 / D60
def test_the_randomiser_is_the_parity_of_sha256_of_day_and_seed_and_splits_the_rounds_50_50():
    """The shared interface (D47, D53): the arm of a `--mode randomised` round is composites when sha256(f"{et_day}:
    {seed}") read as an integer is even, gen when odd. Re-derived a second way (the digest's last byte), the 50/50
    share over 4,000 seeds, the two seeds of the 2026-09-24 local dry run, and the ET quota day of the clock
    (2026-09-24 02:30 UTC is 2026-09-23 22:30 EDT: the day the platform's quota belongs to)."""
    import datetime
    for s in range(4000):
        low = hashlib.sha256(("2026-09-24:%d" % s).encode()).digest()[-1] & 1
        assert R.randomised_arm("2026-09-24", s) == ("gen" if low else "composites")
    share = sum(R.randomised_arm("2026-09-24", s) == "gen" for s in range(4000)) / 4000
    assert 0.47 < share < 0.53
    assert (R.randomised_arm("2026-09-23", 1790218807), R.randomised_arm("2026-09-23", 1790218808)) == ("gen", "composites")
    t = datetime.datetime(2026, 9, 24, 2, 30, tzinfo=datetime.timezone.utc).timestamp()
    assert R.randomise(7, now=t) == {"et_day": "2026-09-23", "seed": 7, "arm": R.randomised_arm("2026-09-23", 7)}
    assert R.randomise(7, now=t + 3 * 3600)["et_day"] == "2026-09-24"


def test_a_randomised_round_plans_the_drawn_arm_and_stamps_arm_arm_by_and_round(tmp_path, monkeypatch):
    """D47/D54/D60 and the shared interface: main() draws the arm BEFORE planning, plans it with the round's own
    `--ab`, and stamps every construction meta.arm = the draw (overwriting the `--ab` labels "current" / "new"),
    meta.arm_by = "randomiser", meta.round = the seed; the plan copy records the draw. Before, `--mode randomised`
    did not parse (exit 2) and no row could say whether a randomiser assigned it (round 4 S3)."""
    import datetime
    t = datetime.datetime(2026, 9, 24, 2, 30, tzinfo=datetime.timezone.utc).timestamp()
    real = R.randomise
    monkeypatch.setattr(R, "randomise", lambda seed, now=None: real(seed, now=t))
    monkeypatch.setattr(R, "_VERSION", "v-running")
    seeds = {arm: next(s for s in range(100) if R.randomised_arm("2026-09-23", s) == arm) for arm in R.RANDOMISED_ARMS}
    asked = {}

    def fake_plan(root, n, seed, **kw):
        asked.update(kw)
        return {"seed": seed, "n": n, "hypotheses": 0, "cells_considered": 0, "gate": {}, "blocks": [],
                "constructions": [{"formula": "rank(a)", "settings": {"delay": 1}, "meta": {"arm": "current"}},
                                  {"formula": "rank(b)", "settings": {"delay": 1}, "meta": {"arm": "new"}}]}
    real_plan = R.plan
    monkeypatch.setattr(R, "plan", fake_plan)
    s = seeds["composites"]
    batch, ns = _round_through_main(monkeypatch, tmp_path, ["--mode", R.RANDOMISED, "--ab", "new", "--seed", str(s)])
    assert asked["mode"] == "composites" and asked["ab"] == "new" and ns.mode == R.RANDOMISED
    assert [(c["meta"]["arm"], c["meta"]["arm_by"], c["meta"]["round"]) for c in batch] == [("composites", "randomiser", s)] * 2
    on_file = json.loads((tmp_path / ("plans/%d.json" % s)).read_text())
    assert on_file["randomiser"] == {"et_day": "2026-09-23", "seed": s, "arm": "composites"}
    assert "randomiser: ET day 2026-09-23, seed %d -> arm composites" % s in R.summarize(on_file)
    # D45 x D47 (draw5 pipeline SUSPECTED, D5-PL-S1): the rounds of both arms run ONE argv but the seed, so they carry
    # one run_config and a start of either arm writes no D45 transition row (one per round would mark every day mixed)
    other, ns_other = _round_through_main(monkeypatch, tmp_path / "o", ["--mode", R.RANDOMISED, "--ab", "new", "--seed",
                                                                        str(seeds["gen"])])
    assert asked["mode"] == "gen" and {c["meta"]["arm"] for c in other} == {"gen"}
    assert {c["meta"]["run_config"] for c in batch + other} == {R.run_config(ns)} == {R.run_config(ns_other)}
    log = tmp_path / "d45.jsonl"
    assert R.record_run_config("v-running", R.run_config(ns), log) and not R.record_run_config("v-running", R.run_config(ns_other), log)
    monkeypatch.setattr(R, "plan", real_plan)
    root = _gen_root(tmp_path / "tree")
    s = seeds["gen"]
    batch, ns = _round_through_main(monkeypatch, tmp_path / "g", ["--root", str(root), "--mode", R.RANDOMISED, "-n", "12",
                                                                  "--seed", str(s)])
    assert len(batch) == 12 and {(c["meta"]["arm"], c["meta"]["arm_by"], c["meta"]["round"], c["meta"]["gen_route"])
                                 for c in batch} == {("gen", "randomiser", s, "fresh")}
    rc = R.run_config(ns)
    assert {c["meta"]["run_config"] for c in batch} == {rc}
    # the same round asked for explicitly: explicit, no round, and another run_config (D30: another cohort)
    batch, ns = _round_through_main(monkeypatch, tmp_path / "e", ["--root", str(root), "--mode", "gen", "-n", "12",
                                                                  "--seed", str(s)])
    assert {(c["meta"]["arm"], c["meta"]["arm_by"], "round" in c["meta"]) for c in batch} == {("gen", "explicit", False)}
    assert R.run_config(ns) != rc


def test_a_round_the_randomiser_did_not_assign_is_explicit_whatever_its_rows_carried(tmp_path, monkeypatch):
    """D54/D60: only rounds the randomiser assigned enter the comparison. A `--plan` round (even under `--mode
    randomised`: the planner, and so the draw, is skipped) and every explicit mode are stamped arm_by "explicit",
    OVERWRITTEN, and a `round` a plan row copied from a randomised journal row is dropped (forge/offline/pow_pairs.py
    and c11_neut.py copy meta from a journal row). The arm keeps its old rule (setdefault). The default mode is still
    composites: nothing changes for the running loop until forge.env names another."""
    monkeypatch.setattr(R, "_VERSION", "v-running")
    copied = {"formula": "rank(x)", "settings": {"delay": 1},
              "meta": {"arm": "gen", "arm_by": "randomiser", "round": 99, "gen_route": "fresh"}}
    (tmp_path / "exp.json").write_text(json.dumps({"n": 1, "hypotheses": 0, "cells_considered": 0, "gate": {},
                                                   "blocks": [], "constructions": [copied]}))
    batch, ns = _round_through_main(monkeypatch, tmp_path, ["--plan", str(tmp_path / "exp.json"), "--mode", R.RANDOMISED,
                                                            "--seed", "5"])
    assert [(c["meta"]["arm"], c["meta"]["arm_by"], "round" in c["meta"]) for c in batch] == [("gen", "explicit", False)]
    assert "randomiser" not in json.loads((tmp_path / "plans/5.json").read_text())
    rows = [{"formula": "a", "meta": {}}, {"formula": "b", "meta": {"arm": "current", "arm_by": "randomiser", "round": 3}}]
    R.stamp(rows, "rc1", "composites")
    assert [(r["meta"]["arm"], r["meta"]["arm_by"], "round" in r["meta"]) for r in rows] == \
        [("composites", "explicit", False), ("current", "explicit", False)]
    R.stamp(rows, "rc1", "gen", round_seed=12)
    assert [(r["meta"]["arm"], r["meta"]["arm_by"], r["meta"]["round"]) for r in rows] == [("gen", "randomiser", 12)] * 2


def test_the_default_mode_is_still_composites_and_the_new_modes_parse(parse_only):
    """A PIN, not a fix: the default stays `--mode composites`, so the running loop changes only when a deploy puts
    another mode in forge.env (D50). `gen` and `randomised` parse (round 4 m13: `--mode gen` exited 2)."""
    assert _parsed(lambda: R.main([])).mode == "composites"
    assert [_parsed(lambda m=m: R.main(["--mode", m])).mode for m in ("gen", R.RANDOMISED)] == ["gen", "randomised"]
