import json

import pytest

from forge import cells as C
from forge.offline import refresh_cells as RC


PAYLOAD = {"pyramids": [
    {"category": {"id": "shortinterest", "name": "Short Interest"}, "region": "USA", "delay": 1, "alphaCount": 2},
    {"category": {"id": "option", "name": "Option"}, "region": "USA", "delay": 1, "alphaCount": 4},
    {"category": {"id": "news", "name": "News"}, "region": "JPN", "delay": 0, "alphaCount": 0},
]}


def test_pairs_and_roundtrip(tmp_path):
    pairs = RC.pairs_from_payload(PAYLOAD)
    assert [(p["region"], p["delay"]) for p in pairs] == [("JPN", 0), ("USA", 1)]
    assert pairs[1]["counts"] == {"Short Interest": 2, "Option": 4}
    RC.write(pairs, tmp_path / "c.json")
    assert C.load_pair_counts(tmp_path / "c.json") == {("JPN", 0): {"News": 0}, ("USA", 1): {"Short Interest": 2, "Option": 4}}
    assert json.load(open(tmp_path / "c.json"))["ts"] > 0


def test_malformed_rows_fail_closed():
    with pytest.raises(ValueError):
        RC.pairs_from_payload({"pyramids": []})
    bad = {"pyramids": [{"category": {"name": "News"}, "region": "USA", "delay": 1}]}   # no alphaCount
    with pytest.raises(ValueError):
        RC.pairs_from_payload(bad)
