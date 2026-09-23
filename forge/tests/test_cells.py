import json

import pytest

from forge import cells as C


@pytest.fixture
def root(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "fetched/rc/fields").mkdir(parents=True)
    json.dump({"pairs": [
        {"region": "USA", "delay": 1, "counts": {"News": 0, "Model": 22, "Sentiment": 1}},
        {"region": "EUR", "delay": 0, "counts": {"News": 0}},
    ], "ts": 1.0}, open(tmp_path / "state/pyramid_cell_counts.json", "w"))
    json.dump({
        "USA_TOP3000_d1": [
            {"id": "news29", "category": {"name": "News"}, "userCount": 19, "pyramidMultiplier": 1.2},
            {"id": "news73", "category": {"name": "News"}, "userCount": 52, "pyramidMultiplier": 1.2},
            {"id": "sentiment22", "category": {"name": "Sentiment"}, "userCount": 229, "pyramidMultiplier": 1.4},
            {"id": "model1", "category": {"name": "Model"}, "userCount": 5, "pyramidMultiplier": 1.3},
        ],
        "EUR_TOP2500_d0": {"results": [
            {"id": "news29", "category": {"name": "News"}, "userCount": 4, "pyramidMultiplier": 1.0}]},
        "junk": [],
    }, open(tmp_path / "fetched/rc/datasets_survey.json", "w"))
    with open(tmp_path / "fetched/rc/fields/USA_TOP3000_d1.jsonl", "w") as fh:
        for i in range(3):
            fh.write(json.dumps({"id": "news29_f%d" % i, "category": {"name": "News"}}) + "\n")
        fh.write(json.dumps({"id": "sentiment22_x", "category": {"name": "Sentiment"}}) + "\n")
        fh.write("\n")
    # EUR d0 has NO catalogue on disk -> unreachable
    return tmp_path


def test_load_pair_counts_both_schemas(tmp_path):
    p = tmp_path / "a.json"
    json.dump({"pairs": [{"region": "USA", "delay": 1, "counts": {"News": 2}}]}, open(p, "w"))
    assert C.load_pair_counts(p) == {("USA", 1): {"News": 2}}
    json.dump({"by_pair": {"JPN:0": {"counts": {"Risk": 0}}}}, open(p, "w"))
    assert C.load_pair_counts(p) == {("JPN", 0): {"Risk": 0}}
    json.dump({"nope": 1}, open(p, "w"))
    with pytest.raises(ValueError):
        C.load_pair_counts(p)


def test_survey_and_catalogue(root):
    s = C.load_survey(root / "fetched/rc/datasets_survey.json")
    assert set(s) == {("USA", 1), ("EUR", 0)}
    usa = s[("USA", 1)]
    assert usa["universe"] == "TOP3000"
    assert usa["categories"]["News"]["multiplier"] == 1.2
    assert usa["categories"]["News"]["datasets"] == [("news29", 19), ("news73", 52)]
    assert C.catalogue_categories(root / "fetched/rc/fields", "USA", 1, "TOP3000") == {"News": 3, "Sentiment": 1}
    assert C.catalogue_categories(root / "fetched/rc/fields", "USA", 1) == {"News": 3, "Sentiment": 1}
    assert C.catalogue_categories(root / "fetched/rc/fields", "EUR", 0) == {}


def test_ranking(root):
    cells = C.targets(root)
    by = {(c.region, c.delay, c.category): c for c in cells}
    news = by[("USA", 1, "News")]
    assert news.need == 3 and news.weight == pytest.approx(3 * 1.2) and news.datasets[0] == ("news29", 19)
    sent = by[("USA", 1, "Sentiment")]
    assert sent.need == 2 and sent.weight == pytest.approx(2 * 1.4)
    assert by[("USA", 1, "Model")].need == 0 and by[("USA", 1, "Model")].weight == 0
    eur = by[("EUR", 0, "News")]
    assert eur.need == 3 and eur.n_fields == 0 and eur.weight == 0      # no catalogue -> unreachable
    assert [c.category for c in cells[:2]] == ["News", "Sentiment"]


def test_hypothesis_factor(root):
    cells = C.targets(root, hypotheses={"Sentiment"})
    top = cells[0]
    assert top.category == "Sentiment" and top.weight > 0
    assert all(c.weight == 0 for c in cells if c.category != "Sentiment")
