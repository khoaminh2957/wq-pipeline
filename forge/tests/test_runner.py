import json
import textwrap

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


def test_every_construction_carries_the_pipeline_version(tmp_path, monkeypatch):
    """D1 grades a VERSION and D14 grades the alphas that version produced. Until 2026-09-23 no row
    carried one, so both sentences had no referent and the scorecard fell back to a time window."""
    from forge import runner as R
    monkeypatch.setattr(R, "_VERSION", None)
    (tmp_path / "DEPLOYED.json").write_text(json.dumps({"version": "abc123", "files": 1}))
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
