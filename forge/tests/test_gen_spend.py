"""forge.gen.spend: each D36 rule on synthetic families (allocate's constants, re-keyed on the family)."""
import random

from forge import allocate as AL
from forge import novelty as NV
from forge.gen import spend as SP
from forge.tests.test_gen_productions import POSTS

BINDING = ("LOW_SHARPE", "LOW_FITNESS", "LOW_SUB_UNIVERSE_SHARPE", "IS_LADDER_SHARPE", "CONCENTRATED_WEIGHT",
           "HIGH_TURNOVER", "LOW_TURNOVER")


def frow(alpha, fam="famA", sharpe=0.5, passed=False, ladder=("FAIL", 2), route="draw", region="USA", delay=1):
    cks = [{"name": n, "result": "PASS" if passed or n not in ("LOW_SHARPE", "IS_LADDER_SHARPE") else "FAIL"}
           for n in BINDING]
    cks[0].update(limit=1.58, value=sharpe)                           # LOW_SHARPE, as real rows carry it
    lad = [c for c in cks if c["name"] == "IS_LADDER_SHARPE"][0]
    if ladder is None:
        cks.remove(lad)
    elif not passed:
        lad.update(result=ladder[0], year=ladder[1])
    return {"alpha": alpha, "sharpe": sharpe, "formula": "rank(x_%s)" % alpha, "checks": cks,
            "settings": {"region": region, "delay": delay},
            "meta": {"hypothesis": "gen:" + fam, "gen_route": route}}


def rows_of(*groups):
    out = {}
    for g in groups:
        for r in g:
            out[r["alpha"]] = r
    return out


def verdict(rows, fam="famA", cell="USA/d1", stopped=()):
    return SP.verdict(SP.family_stats(rows).get((fam, cell)), fam in stopped)


def test_dead_sims_40_and_the_in_round_cap_to_the_decision_point():
    assert AL.DEAD_SIMS == 40 and AL.DEAD_BEST == 1.0
    cleared = [frow("c0", sharpe=0.9, ladder=("PASS", 5))]            # ladder cleared: only DEAD can fire
    assert verdict(rows_of(cleared, [frow("a%d" % i, sharpe=0.9) for i in range(39)])) == ("DEAD", 0)
    assert verdict(rows_of(cleared, [frow("a%d" % i, sharpe=0.9) for i in range(38)])) == ("OPEN", 1)
    assert verdict(rows_of(cleared, [frow("a%d" % i, sharpe=1.0) for i in range(39)])) == ("OPEN", None)
    assert verdict({}) == ("OPEN", 40)                                  # a new family: 40 before any verdict


def test_dead_best_scales_with_the_cells_bar():
    d0 = rows_of([frow("c", sharpe=1.5, ladder=("PASS", 5), delay=0)], [frow("a%d" % i, sharpe=1.5, delay=0) for i in range(39)])
    d1 = rows_of([frow("c", sharpe=1.5, ladder=("PASS", 5))], [frow("a%d" % i, sharpe=1.5) for i in range(39)])
    assert verdict(d0, cell="USA/d0") == ("DEAD", 0)                   # 1.5 < 1.0 x 2.69 / 1.58
    assert verdict(d1) == ("OPEN", None)


def test_ladder_dead_at_40_rows_none_past_year_two_whatever_the_sharpe():
    assert AL.LADDER_DEAD is True
    stuck = [frow("a%d" % i, sharpe=1.9, ladder=("FAIL", 2)) for i in range(40)]
    assert verdict(rows_of(stuck)) == ("LADDER_DEAD", 0)
    one_past = stuck[:39] + [frow("z", sharpe=1.9, ladder=("FAIL", 3))]
    assert verdict(rows_of(one_past)) == ("OPEN", None)
    no_verdict = [frow("a%d" % i, sharpe=1.9, ladder=None) for i in range(40)]      # ERROR-like: no evidence
    assert verdict(rows_of(no_verdict)) == ("OPEN", None)


def test_passed_block_40_further_sims_after_the_first_harvest_pass_neighbours_not_counted():
    assert AL.PASSED_BLOCK == 40
    before = [frow("b%d" % i) for i in range(5)]
    first = [frow("p0", passed=True, sharpe=1.9)]
    after = [frow("x%d" % i) for i in range(39)]
    assert verdict(rows_of(before, first, after)) == ("PASSED", 1)
    assert verdict(rows_of(before, first, after, [frow("x39")])) == ("PASSED_EXHAUSTED", 0)
    nbrs = [frow("n%d" % i, route="neighbour") for i in range(5)]
    assert verdict(rows_of(before, first, after, nbrs)) == ("PASSED", 1)


def test_families_are_counted_per_cell_and_per_family():
    rows = rows_of([frow("a%d" % i, sharpe=0.5, ladder=("PASS", 5)) for i in range(40)],
                   [frow("g%d" % i, sharpe=0.5, region="GLB") for i in range(3)],
                   [frow("o%d" % i, fam="famB") for i in range(3)])
    assert verdict(rows) == ("DEAD", 0)
    assert verdict(rows, cell="GLB/d1") == ("OPEN", 37)
    assert verdict(rows, fam="famB") == ("OPEN", 37)


def _walk(rng, n=1000):
    x, out = 0.0, []
    for _ in range(n):
        x += rng.gauss(0, 1)
        out.append(x)
    return out


def _curve(values):
    return {"2020-%04d" % i: v for i, v in enumerate(values)}


def test_pnl_stop_at_0_70_on_the_984_day_predictor_and_no_reading_is_no_verdict():
    rng = random.Random(31)
    post = _walk(rng)
    twin = [p + 0.3 * rng.gauss(0, 1) for p in post]          # daily PnL almost the POST's
    other = _walk(rng)
    rows = rows_of([frow("m1", fam="famT")], [frow("m2", fam="famO")], [frow("m3", fam="famL")])
    curves = {"POST": _curve(post), "m1": _curve(twin), "m2": _curve(other), "m3": [[0, 1.0], [1, 2.0]]}
    stops = SP.pnl_stops(rows, curves, ["POST"])
    assert set(stops) == {"famT"} and stops["famT"]["post"] == "POST" and stops["famT"]["corr"] >= SP.PNL_LINE
    assert SP.pnl_stops(rows, {k: v for k, v in curves.items() if k != "POST"}, ["POST"]) == {}
    assert SP.verdict({"sims": 1, "passes": 1, "after": 0, "best": 1.9, "ladder_n": 0, "ladder_y2": True, "delay": 1},
                      True) == ("PNL_STOP", 0)                  # the stop outranks PASSED
    assert SP.PNL_LINE == 0.70


def test_plan_time_d18_refuses_post_twins_and_fails_open_on_an_incomplete_index():
    hist = [{"alpha": "kq", "http": 201, "formula": POSTS["kqVbg1xP"]}]
    twin = POSTS["kqVbg1xP"].replace("_30", "_90").replace(", 5)", ", 10)")
    other = "rank(operating_income / assets)"
    full = NV.build(hist, {})
    assert SP.d18_refuses(full, twin)[0] is True and SP.d18_refuses(full, other)[0] is False
    part = NV.build(hist + [{"alpha": "ghost", "http": 200}], {})       # a POST whose formula nobody has
    assert not part.complete
    assert SP.d18_refuses(part, twin)[0] is True                        # what WAS read still refuses
    assert SP.d18_refuses(part, other)[0] is False                      # incompleteness refuses nothing
    assert SP.d18_refuses(None, twin) == (False, 0.0, None)
    assert SP.d18_refuses(NV.build([{"alpha": "r", "http": 403, "formula": POSTS["kqVbg1xP"]}], {}), twin)[0] is False


def test_the_pnl_line_is_inclusive(monkeypatch):
    """Draw-5 gen N5 (S03): D36 stops a family at a correlation >= 0.70, so exactly 0.70 stops it."""
    rows = rows_of([frow("m1", fam="famT")])
    curves = {"POST": _curve([0.0, 1.0]), "m1": _curve([0.0, 2.0])}
    monkeypatch.setattr(SP, "_predict", lambda a, b: (0.70, 984))
    assert set(SP.pnl_stops(rows, curves, ["POST"])) == {"famT"}
    monkeypatch.setattr(SP, "_predict", lambda a, b: (0.6999, 984))
    assert SP.pnl_stops(rows, curves, ["POST"]) == {}


def test_a_curve_holding_a_non_number_gives_no_reading_and_does_not_raise():
    """Draw-5 gen N10: a cached curve with a null (or text) value used to raise TypeError inside predict, which
    ended the round in State(); no reading is not a verdict, so the family is simply not stopped on it."""
    rng = random.Random(31)
    post = _walk(rng)
    twin = [p + 0.3 * rng.gauss(0, 1) for p in post]
    rows = rows_of([frow("m1", fam="famT")])
    bad_member = dict(_curve(twin), **{"2020-0500": None})
    bad_post = dict(_curve(post), **{"2020-0400": "n/a"})
    assert SP.pnl_stops(rows, {"POST": _curve(post), "m1": bad_member}, ["POST"]) == {}
    assert SP.pnl_stops(rows, {"POST": bad_post, "m1": _curve(twin)}, ["POST"]) == {}
    assert set(SP.pnl_stops(rows, {"POST": _curve(post), "m1": _curve(twin)}, ["POST"])) == {"famT"}   # control


def test_importing_spend_leaves_sys_path_and_self_corr_predict_alone():
    """Draw-5 gen N8: spend imported tools/self_corr_predict at module level, whose body puts tools/ and
    tools/autoloop at the front of sys.path for every importer of forge.gen. Run in a fresh interpreter."""
    import pathlib
    import subprocess
    import sys
    root = pathlib.Path(__file__).resolve().parents[2]
    code = (
        "import sys, random\n"
        "before = list(sys.path)\n"
        "from forge.gen import spend as SP\n"
        "assert 'self_corr_predict' not in sys.modules, 'imported at module level'\n"
        "assert not any(p.endswith('autoloop') for p in sys.path), sys.path[:3]\n"
        "from forge.tests.test_gen_spend import _curve, _walk, frow, rows_of\n"
        "rng = random.Random(31); post = _walk(rng)\n"
        "rows = rows_of([frow('m1', fam='famT')])\n"
        "p = list(sys.path)\n"
        "out = SP.pnl_stops(rows, {'POST': _curve(post), 'm1': _curve([x + 0.3 * rng.gauss(0, 1) for x in post])}, ['POST'])\n"
        "assert set(out) == {'famT'}, out\n"
        "assert sys.path == p, 'pnl_stops changed sys.path'\n"
    )
    env = {k: v for k, v in __import__("os").environ.items() if k != "PYTHONPATH"}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(root))
    r = subprocess.run([sys.executable, "-B", "-c", code], cwd=str(root), env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
