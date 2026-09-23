import json
import random

from forge import harvest as HV
from forge import dsr as D


def _row(alpha, sharpe, hyp="h1", region="USA", delay=1, turnover=0.1, fail=False):
    ck = [{"name": "LOW_SHARPE", "result": "FAIL" if fail else "PASS", "limit": 1.58, "value": sharpe},
          {"name": "LOW_FITNESS", "result": "PASS", "limit": 1.0, "value": 1.2},
          {"name": "CONCENTRATED_WEIGHT", "result": "PASS"},
          {"name": "MATCHES_PYRAMID", "result": "PASS", "pyramids": [{"name": "USA/D1/NEWS", "multiplier": 1.2}]},
          {"name": "PROD_CORRELATION", "result": "PENDING"}]
    return {"alpha": alpha, "sharpe": sharpe, "fitness": 1.2, "turnover": turnover, "drawdown": 0.1, "checks": ck,
            "formula": "group_rank(ts_sum(vec_sum(f), 5), industry)",
            "settings": {"region": region, "delay": delay, "universe": "TOP3000"},
            "meta": {"forge": 1, "hypothesis": hyp, "category": "News", "cand": alpha + "c",
                     "signature": "news29#smooth+vector#USA/d1", "mechanism_key": "h1#news29#USA/d1"}}


def _curve(annual_sharpe, t=1300, seed=0):
    rng = random.Random(seed)
    mu, x, cum = annual_sharpe / D.ANNUALISE, 0.0, {}
    for i in range(t):
        x += rng.gauss(mu, 1.0)
        cum["2020-%05d" % i] = x
    return cum


def test_forge_rows_latest_wins_and_pools(tmp_path):
    p = tmp_path / "forge.jsonl"
    rows = [_row("A", 1.0), _row("B", 2.0), _row("A", 1.5), {"alpha": "Z", "meta": {"move": "wrap"}, "sharpe": 3},
            {"status": "PARENT-POSTED"}]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\nbroken\n")
    fr = HV.forge_rows(p)
    assert set(fr) == {"A", "B"} and fr["A"]["sharpe"] == 1.5
    pools = HV.pool_stats(fr)
    n, var = pools[("h1", "USA", 1, "News")]
    assert n == 2 and var > 0


def test_score_row_stages(tmp_path):
    pools = {("h1", "USA", 1, "News"): (30, D.var_sr_from_annual_sharpes([0.5, 1.0, 1.5, 2.0]))}
    good = HV.score_row(_row("A", 2.4), _curve(2.4), pools)
    assert good["stage"] == "candidate" and good["dsr"] >= 0.95 and 0 < good["score"] <= 1
    assert good["pyramids"] == ["USA/D1/NEWS"] and good["pool_n"] == 30 and good["op_count"] == 3
    weak = HV.score_row(_row("B", 1.2), _curve(1.2), pools)
    assert weak["stage"] == "dsr-fail" and weak["dsr"] < 0.95
    assert HV.score_row(_row("C", 2.0), None, pools)["stage"] == "needs-dsr"
    assert HV.score_row(_row("D", 2.0, turnover=0.4), None, pools)["stage"] == "turnover-decay-retry"
    assert HV.score_row(_row("E", 1.0, fail=True), None, pools)["stage"] == "fail"


def test_run_scores_only_new_or_waiting(tmp_path):
    rows = {"A": _row("A", 2.4), "B": _row("B", 2.3), "C": _row("C", 1.0, fail=True)}
    pools = HV.pool_stats(rows)
    curves = {"A": _curve(2.4)}
    fetched = []

    def fetch(a):
        fetched.append(a)
        return curves.get(a)
    lines = []
    new = HV.run(rows, {}, pools, fetch, out=lines.append)
    by = {x["alpha"]: x for x in new}
    assert by["A"]["stage"] == "candidate" and by["B"]["stage"] == "needs-dsr" and by["C"]["stage"] == "fail"
    assert sorted(fetched) == ["A", "B"]            # the failed row never costs a fetch
    scored = {x["alpha"]: x for x in new}
    again = HV.run(rows, scored, pools, fetch, out=lines.append)
    assert [x["alpha"] for x in again] == ["B"]     # only the row still waiting for its curve
    scored["C"]["stage"] = "incomplete"              # a row mis-staged as incomplete is re-scored
    assert sorted(x["alpha"] for x in HV.run(rows, scored, pools, fetch, out=lines.append)) == ["B", "C"]
    sc = tmp_path / "scored.jsonl"
    sc.write_text("\n".join(json.dumps(x) for x in new) + "\n")
    assert set(HV.load_scored(sc)) == {"A", "B", "C"}


def test_quarantine_marks_only_all_fail_pairs(tmp_path):
    j = tmp_path / "forge.jsonl"
    rows = []
    for i in range(4):   # the field with no data: every child FAILs
        rows.append({"status": "FAIL", "meta": {"forge": 1, "hypothesis": "h", "category": "Fundamental", "field": "f_dead"},
                     "settings": {"region": "JPN", "delay": 0}})
    for i in range(4):   # its sibling field lands
        rows.append({"status": "COMPLETE", "alpha": "A%d" % i, "meta": {"forge": 1, "hypothesis": "h", "category": "Fundamental", "field": "f_ok"},
                     "settings": {"region": "JPN", "delay": 0}})
    for i in range(3):   # too few to judge
        rows.append({"status": "FAIL", "meta": {"forge": 1, "hypothesis": "h2", "category": "Other", "field": "f_few"},
                     "settings": {"region": "EUR", "delay": 1}})
    rows.append({"status": "PARENT-POSTED", "formulas": ["x"]})
    j.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    out = tmp_path / "q.json"
    assert HV.quarantine(j, out) == ["h|JPN|0|Fundamental|f_dead"]
    assert json.load(open(out)) == ["h|JPN|0|Fundamental|f_dead"]


def test_curve_daily_and_pool_pbo(tmp_path):
    import random
    from forge import harvest as HV
    assert HV.curve_daily({"d1": 0.0, "d2": 5.0, "d3": 3.0}) == {"d2": 5.0, "d3": -2.0}
    assert HV.curve_daily([["d1", 0.0], ["d2", None], ["d3", 4.0]]) == {"d3": 4.0}
    rng = random.Random(3)
    rows, curves = {}, {}
    for i in range(24):
        a = "A%d" % i
        rows[a] = {"alpha": a, "sharpe": 1.0, "formula": "f%d" % i, "settings": {"region": "USA", "delay": 1},
                   "meta": {"hypothesis": "h", "category": "News"}}
        cum, c = 0.0, {}
        for d in range(400):
            cum += rng.gauss(0.2 if i == 0 else 0.0, 1.0)
            c["d%04d" % d] = cum
        curves[a] = c
    rows["A0_resim"] = dict(rows["A0"], alpha="A0r")                      # same formula+settings: one trial
    curves["A0r"] = curves["A0"]
    fetched = []
    def fetch(a):
        fetched.append(a)
        return curves.get(a)
    pool = ("h", "USA", 1, "News")
    assert len(HV.pool_members(pool, rows)) == 24
    unf = set()
    v = HV.pool_pbo(pool, rows, fetch, {"left": 150}, unf, curves_dir=tmp_path)
    assert v["members"] == 24 and v["curves"] == 24 and v["status"] == "ok" and v["pass"] is True and v["missing"] == 0
    # a per-run budget too small for the pool: pending, no verdict, and the budget is consumed
    b = {"left": 5}
    v2 = HV.pool_pbo(pool, rows, fetch, b, set(), curves_dir=tmp_path)
    assert v2["status"] == "pending" and v2["pass"] is None and v2["pbo"] is None and v2["missing"] == 19 and b["left"] == 0
    # an unfetchable member does not hold the pool forever: it is remembered and the pool completes without it
    def fetch_dead(a):
        return None if a == "A5" else curves.get(a)
    unf = set()
    v3 = HV.pool_pbo(pool, rows, fetch_dead, {"left": 150}, unf, curves_dir=tmp_path)
    assert "A5" in unf and v3["status"] == "ok" and v3["curves"] == 23 and v3["unfetchable"] == 1


def test_pbo_order_puts_postable_and_newest_first():
    rows = {a: _row(a, 2.0) for a in "ABCD"}
    rows["D"]["checks"].append({"name": "PROD_CORRELATION", "result": "PENDING", "limit": 0.65})
    cands = [{"alpha": "A", "scored_at": 10}, {"alpha": "B", "scored_at": 20}, {"alpha": "C", "scored_at": 30}, {"alpha": "D", "scored_at": 40}]
    corr = {"A": {"prod": 0.5, "self": 0.3}, "B": {"prod": 0.85, "self": 0.3}, "D": {"prod": 0.66, "self": 0.3}}
    order = [x["alpha"] for x in HV.pbo_order(cands, rows, corr, posted={"C"})]
    # A: postable (under lines). B: over 0.7. C: posted. D: over its own 0.65 line. Newest first within a group.
    assert order[0] == "A" and set(order[1:]) == {"B", "C", "D"} and order[1:] == ["D", "C", "B"]


def test_main_orders_pools_and_saves_unfetchable_per_pool(tmp_path, monkeypatch):
    """The PBO stage of harvest.main: pools are judged in pbo_order and the unfetchable set is
    written after EVERY pool, so a harvest killed by the loop's timeout keeps what it learned."""
    import sys, types, random
    rows = {}
    for hyp, alphas in (("old", ["O%d" % i for i in range(3)]), ("new", ["N%d" % i for i in range(3)])):
        for a in alphas:
            r = _row(a, 2.4, hyp=hyp)
            r["meta"]["mechanism_key"] = "%s#news29#USA/d1" % hyp
            r["formula"] = "f_%s" % a
            r["meta"]["cand"] = a
            rows[a] = r
    scored = {a: {"alpha": a, "stage": "fail", "hypothesis": a[0]} for a in rows}      # nothing left for the scoring stage
    scored["O0"] = {"alpha": "O0", "stage": "candidate", "hypothesis": "old", "scored_at": 1.0}
    scored["N0"] = {"alpha": "N0", "stage": "candidate", "hypothesis": "new", "scored_at": 2.0}
    curves = {a: _curve(2.4, t=400, seed=i) for i, a in enumerate(rows)}
    fetched, saved = [], []
    fake_ls = types.ModuleType("layered_sim"); fake_ls.session = lambda: object(); fake_ls.keep_jar_fresh = lambda s: None
    fake_sp = types.ModuleType("self_corr_predict")
    fake_sp.pnl = lambda s, a, budget=0: (fetched.append(a), None if a == "N2" else curves.get(a))[1]
    monkeypatch.setitem(sys.modules, "layered_sim", fake_ls)
    monkeypatch.setitem(sys.modules, "self_corr_predict", fake_sp)
    monkeypatch.setattr(HV, "quarantine", lambda: [])
    monkeypatch.setattr(HV, "forge_rows", lambda: rows)
    monkeypatch.setattr(HV, "load_scored", lambda: dict(scored))
    monkeypatch.setattr(HV, "cached_curve", lambda a, curves_dir=None: None)
    monkeypatch.setattr(HV, "load_unfetchable", lambda: set())
    monkeypatch.setattr(HV, "save_unfetchable", lambda items: saved.append(set(items)))
    monkeypatch.setattr(HV, "SCORED", tmp_path / "scored.jsonl")
    monkeypatch.setattr(HV, "pbo_order", lambda cands, rows, corr, posted: sorted(cands, key=lambda x: -x["scored_at"]))
    HV.main(["--pbo-fetch", "4"])
    assert fetched[:3] == ["N0", "N1", "N2"] and fetched[3] == "O0"     # the newest candidate's pool spent the budget first
    assert len(saved) == 3 and saved[0] == {"N2"} and saved[-1] == {"N2"}  # after each of the 2 pools, then at the end
    out = [json.loads(l) for l in (tmp_path / "scored.jsonl").read_text().splitlines()]
    by = {x["alpha"]: x for x in out}
    assert by["N0"]["pbo_status"].startswith("insufficient") and by["O0"]["pbo_status"] == "pending"
