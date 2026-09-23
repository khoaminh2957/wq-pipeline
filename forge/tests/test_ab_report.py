import json

from forge.offline import ab_report as AB


def _row(alpha, arm, sharpe, seed=1, mk="c#ds#USA/d1", hyp="c", prod_limit=None):
    ck = [{"name": "LOW_SHARPE", "result": "PASS", "limit": 1.58, "value": sharpe},
          {"name": "PROD_CORRELATION", "result": "PENDING", "limit": prod_limit},
          {"name": "SELF_CORRELATION", "result": "PENDING", "limit": None}]
    return {"alpha": alpha, "sharpe": sharpe, "turnover": 0.1, "checks": ck,
            "meta": {"forge": 1, "arm": arm, "seed": seed, "hypothesis": hyp, "mechanism_key": mk}}


def test_funnel_uses_the_submitter_lines_and_mechanism_keys(tmp_path, monkeypatch):
    j = tmp_path / "forge.jsonl"
    rows = [_row("A", "new", 2.0, mk="c#ds1#USA/d1"), _row("A", "new", 2.0, mk="c#ds1#USA/d1"),      # duplicate row
            _row("B", "new", 2.1, mk="c#ds2#USA/d1"), _row("C", "current", 1.9, mk="d#ds3#USA/d1", hyp="d"),
            _row("D", "current", 1.9, mk="d#ds3#USA/d1", hyp="d", prod_limit=0.65)]
    j.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    sc = tmp_path / "scored.jsonl"
    sc.write_text("\n".join(json.dumps({"alpha": a, "dsr": 0.99}) for a in "ABCD") + "\n")
    corr = tmp_path / "corr.jsonl"
    corr.write_text("\n".join(json.dumps(x) for x in [
        {"alpha": "A", "prod": 0.705, "self": 0.3},      # under 0.71, NOT under the submitter's 0.7 line
        {"alpha": "B", "prod": 0.5, "self": 0.3},
        {"alpha": "C", "prod": 0.5, "self": 0.3},
        {"alpha": "D", "prod": 0.66, "self": 0.3},       # the row's own PROD limit 0.65 holds it
    ]) + "\n")
    monkeypatch.setattr(AB, "ROOT", tmp_path)
    (tmp_path / "state/forge").mkdir(parents=True)
    (tmp_path / "state/forge/corr.jsonl").write_text(corr.read_text())
    (tmp_path / "state/forge/submitted.jsonl").write_text(json.dumps({"alpha": "B", "http": 201}) + "\n")
    rep = AB.report(journal=j, scored_path=sc)
    new, cur = rep["pooled"]["new"], rep["pooled"]["current"]
    assert new["n"] == 2 and new["pass"] == 2 and new["dsr_cand"] == 2               # A counted once
    assert new["corr_under"] == 1 and new["posted"] == 1
    assert new["mechanisms"] == 2 and new["hypotheses"] == 1                        # one composite, two dataset sets
    assert cur["n"] == 2 and cur["corr_under"] == 1 and cur["mechanisms"] == 1
    assert rep["rounds"][0]["seed"] == 1


def test_every_tagged_arm_is_counted_not_silently_dropped():
    """A hardcoded arm list drops a new experiment's rows without saying so, so the experiment reads
    as 'no rows' rather than 'not counted'. llmformula and the POW arms must be in it."""
    from forge.offline import ab_report as AB
    assert {"current", "typed", "new", "llmformula", "pow15", "pow2"} <= set(AB.ARMS)
