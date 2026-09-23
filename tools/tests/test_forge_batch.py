"""layered_sim.run(batch=...) — the forge path: no pool, no draw, shared dispatcher."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import layered_sim as LS  # noqa: E402


def _c(formula, region="USA", delay=1, hyp="news_x"):
    return {"formula": formula,
            "settings": {"instrumentType": "EQUITY", "region": region, "universe": "TOP3000", "delay": delay,
                         "neutralization": "INDUSTRY", "decay": 4, "truncation": 0.08, "pasteurization": "ON",
                         "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR", "visualization": False},
            "meta": {"forge": 1, "hypothesis": hyp, "category": "News"}}


def test_dry_run_with_batch_previews_and_spends_nothing(tmp_path):
    lines = []
    batch = [_c("group_rank(ts_sum(vec_sum(nws29_frontpage), 5), industry)"),
             _c("group_rank(ts_delta(vec_avg(nws73_globalsent_fearscore), 5), industry)", region="EUR", delay=0)]
    res = LS.run(2, seed=1, out_path=tmp_path / "forge.jsonl", live=False, concurrency=1, children=10,
                 out=lines.append, batch=batch)
    assert res == []
    text = "\n".join(lines)
    assert "forge: 2 construction(s)" in text and "DRY RUN" in text
    assert "2 parents" in text                      # (delay, region, universe) differ -> two groups
    assert "news_x" in text and "nws29_frontpage" in text
    assert not (tmp_path / "forge.jsonl").exists()   # nothing journalled on a dry run


def test_tag_names_the_hypothesis():
    assert LS._tag({"hypothesis": "news_frontpage_attention_reversal_extra_long_name"}) == "news_frontpage_attention"
    assert LS._tag({"move": "wrap", "depth": 2}) == "wrap/d2"
    assert LS._tag(None) == "-"
