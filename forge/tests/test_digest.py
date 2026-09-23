import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
import msgcat as MC  # noqa: E402

from forge import digest as DG
from forge import runner as R

NOW = time.time()


def test_m12_and_m13_render_on_a_known_channel():
    m = MC.m12_forge_digest(300, 40, 5, 4, 2, 1, ["USA/d1 News"], 6.7, 0.125, "Hàng đợi: ok")
    assert m["kind"] == "m12" and m["channel"] == "climb"
    body, dropped = MC.render(m)
    assert "FORGE 24h: 300 sim" in body and "USA/d1 News" in body and "6.7" in body
    for kind in ("loaded", "low", "exhausted"):
        m = MC.m13_hypothesis_queue(kind, 20, 120, 300, 63)
        assert m["kind"] == "m13" and MC.render(m)[0]


def test_queue_kind():
    p = {"constructions": [1] * 300, "n": 300, "hypotheses": 20}
    assert R.queue_kind(p, None) is None
    assert R.queue_kind(p, 19) == "loaded"
    assert R.queue_kind({"constructions": [1] * 100, "n": 300, "hypotheses": 20}, 20) == "low"
    assert R.queue_kind({"constructions": [], "n": 300, "hypotheses": 20}, 20) == "exhausted"


def test_window_counts_only_the_last_day():
    iso_now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(NOW - 3600))
    iso_old = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(NOW - 3 * 86400))
    rows = {"A": {"alpha": "A", "dateCreated": iso_now}, "B": {"alpha": "B", "dateCreated": iso_old}, "C": {"alpha": "C"}}
    scored = {"A": {"stage": "candidate", "scored_at": NOW - 100}, "B": {"stage": "dsr-fail", "scored_at": NOW - 200},
              "D": {"stage": "fail", "scored_at": NOW - 300}, "E": {"stage": "candidate", "scored_at": NOW - 5 * 86400}}
    corr = {"A": {"prod": 0.5, "self": 0.2, "read_at": NOW - 50}, "B": {"prod": 0.5, "self": "x", "read_at": NOW - 50}}
    posted = [{"posted_at": NOW - 10}, {"posted_at": NOW - 2 * 86400}]
    w = DG.window(rows, scored, corr, posted, now=NOW)
    assert w == {"sims": 1, "platform_pass": 2, "candidates": 1, "dsr_rated": 2, "corr_measured": 1, "posted": 1, "dsr_rate": 0.5}


def test_cells_filled_diff(tmp_path):
    snap = tmp_path / "snap.json"
    counts = {("USA", 1): {"News": 3, "Model": 22, "Sentiment": 1}}
    assert DG.cells_filled(counts, snap) == []                     # first run: baseline only
    assert json.load(open(snap)) == ["USA/d1 Model", "USA/d1 News"]
    counts[("USA", 1)]["Sentiment"] = 3
    assert DG.cells_filled(counts, snap) == ["USA/d1 Sentiment"]
