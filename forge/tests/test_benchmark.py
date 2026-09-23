"""Suite for forge/offline/benchmark.py -- the pipeline scorecard.

What these pin is the SHAPE of the judgement, not any particular number: floors that cannot be
compensated, uncertainty that cannot be omitted, and two submission readings that cannot be
silently collapsed into one.
"""
import math

import pytest

from forge.offline import benchmark as B


# ----------------------------------------------------------------------------- the scoring frame
def test_a_failed_floor_is_a_fail_however_high_the_composite():
    """D2 is the whole design: no weighted sum may let a strong axis hide a dead one."""
    axes = {"axis1_product": {"value": 1.0, "floor_met": True},
            "axis2_throughput": {"value": 40.0, "floor_met": True},     # ten times the floor
            "axis3_gearing": {"value": 0.0, "floor_met": False}}        # dead
    card = B.scorecard(axes)
    assert card["verdict"] == "FAIL" and card["floors_unmet"] == ["axis3_gearing"]
    # the composite still exists, because D9's gate compares two FAILING versions
    assert 0 < card["composite_0_100"] <= 100


def test_the_composite_cannot_exceed_100_by_overshooting_one_axis():
    axes = {k: {"value": B.FLOOR[k] * 50, "floor_met": True} for k in B.FLOOR}
    assert B.scorecard(axes)["composite_0_100"] == pytest.approx(100.0)


def test_all_floors_met_is_the_only_way_to_pass():
    axes = {k: {"value": B.FLOOR[k], "floor_met": True} for k in B.FLOOR}
    assert B.scorecard(axes)["verdict"] == "PASS"


# ------------------------------------------------------------------------------- the uncertainty
def test_wilson_widens_as_the_sample_shrinks_and_never_leaves_zero_one():
    wide = B.wilson(1, 300)
    narrow = B.wilson(100, 30000)
    assert (wide[1] - wide[0]) > (narrow[1] - narrow[0])
    for k, n in ((0, 10), (3, 31044), (1, 1), (0, 0)):
        lo, hi = B.wilson(k, n)
        assert 0.0 <= lo <= hi <= 1.0


def test_the_desks_own_numbers_come_out_where_they_should():
    lo, hi = B.wilson(3, 31044)               # 3 submissions in the whole forge era
    assert lo * 5000 == pytest.approx(0.16, abs=0.02) and hi * 5000 == pytest.approx(1.42, abs=0.05)
    lo, hi = B.wilson(1, 300)                 # one submission in a 300-alpha window
    assert hi / max(lo, 1e-9) > 20            # an interval spanning a factor of twenty says nothing


def test_a_window_with_no_events_still_bounds_the_rate():
    """One clean quota day does not exclude a true rate of 3 per day -- the reason D5's one-day
    window cannot rank two versions on the count alone."""
    assert B.rule_of_three(5000) * 5000 == pytest.approx(3.0)
    assert math.isinf(B.rule_of_three(0))


# -------------------------------------------------------------------------- axis 1's two measures
def _row(alpha, sharpe, hyp="h", cat="News", decay=4):
    return {"alpha": alpha, "sharpe": sharpe, "settings": {"region": "USA", "delay": 1, "decay": decay},
            "meta": {"hypothesis": hyp, "category": cat}}


def test_neighbourhood_stability_calls_a_settings_fitted_alpha_fragile():
    key = ("h", "USA", 1, "News")
    peers = {key: [_row("a", 1.7), _row("b", 0.1), _row("c", 0.2), _row("d", 0.15)]}
    fragile = B.neighbourhood_stability(peers, _row("a", 1.7))
    assert fragile["verdict"] == "fragile" and fragile["retained"] < 0.5
    steady = {key: [_row("a", 1.7), _row("b", 1.6), _row("c", 1.5), _row("d", 1.65)]}
    assert B.neighbourhood_stability(steady, _row("a", 1.7))["verdict"] == "stable"


def test_neighbourhood_stability_says_insufficient_rather_than_guessing():
    assert B.neighbourhood_stability({}, _row("a", 1.7))["verdict"] == "insufficient"
    thin = {("h", "USA", 1, "News"): [_row("a", 1.7), _row("b", 1.6)]}
    assert B.neighbourhood_stability(thin, _row("a", 1.7))["verdict"] == "insufficient"


def test_regime_stability_separates_a_steady_alpha_from_a_one_window_bet():
    steady = [i * 1.0 for i in range(400)]                      # a straight line: every third earns
    v = B.regime_stability(steady)
    assert v["verdict"] == "consistent" and v["positive_thirds"] == 3
    # a third with gains and NO dispersion has an unbounded Sharpe, and reporting it as 0.0 made
    # this very curve read "one-regime" until the test caught it
    assert all(x == float("inf") for x in v["thirds"])

    # everything earned inside the FIRST third (399 returns -> thirds of 133), flat thereafter
    one = [i * 1.0 for i in range(133)] + [132.0] * 267
    w = B.regime_stability(one)
    assert w["positive_thirds"] == 1 and w["verdict"] == "one-regime"

    # gains in two of the three thirds read as mixed, not as either extreme
    two = [i * 1.0 for i in range(266)] + [265.0] * 134
    assert B.regime_stability(two)["verdict"] == "mixed"


def test_regime_stability_refuses_to_judge_a_short_curve():
    assert B.regime_stability([1, 2, 3])["verdict"] == "insufficient"
    assert B.regime_stability(None)["verdict"] == "insufficient"


# ------------------------------------------------------------------------ axis 2's two readings
def test_the_two_submission_readings_are_reported_separately():
    """MEASURED 2026-09-23: rK5RGeqa was generated on 09-10 and POSTed on 09-23. Under D14 it is not
    this version's product; to the operator it is today's submission. Collapsing them would answer
    one of Khoa's questions while silently discarding the other."""
    rows = [{"alpha": "x", "sharpe": 1.0, "checks": [], "formula": None, "meta": {}, "settings": {}}]
    t = B.axis2_throughput(rows, submissions=[], posts_in_window=[{"alpha": "older"}])
    assert t["submissions_of_alphas_this_version_produced"] == 0
    assert t["posts_this_version_made"] == 1
    assert t["per_5000_scored"] == 0.0 and not t["floor_met"]


def test_sustainable_needs_all_three_pieces_of_evidence():
    rows = [{"alpha": str(i), "sharpe": 1.0, "checks": [], "formula": None,
             "meta": {}, "settings": {}} for i in range(1000)]
    subs = [{"mechanism_key": "a#x#USA/d1"}, {"mechanism_key": "b#y#USA/d1"}]
    both = B.axis2_throughput(rows, subs, prev_window_rate=1.0)
    assert both["sustainable"] is True
    one_mechanism = B.axis2_throughput(rows, [{"mechanism_key": "a#x#USA/d1"}] * 2, prev_window_rate=1.0)
    assert one_mechanism["sustainable"] is False
    no_history = B.axis2_throughput(rows, subs, prev_window_rate=None)
    assert no_history["sustainable"] is False


# -------------------------------------------------------------------------------- axis 3 is real
def test_the_fitness_functions_run_against_the_real_repository():
    ffs = B.fitness_functions()
    assert len(ffs) >= 6
    for name, ok, evidence in ffs:
        assert isinstance(ok, bool) and evidence, name


def test_a_deferred_import_cycle_is_a_smell_and_a_module_level_one_is_a_wall(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("def f():\n    from forge import b\n")      # deferred
    (pkg / "b.py").write_text("from forge import a\n")                    # module level
    cyc = B.import_cycles(pkg)
    assert cyc["module_level"] == [] and cyc["deferred"]                  # b->a is top-level but a->b is not
    (pkg / "a.py").write_text("from forge import b\n")
    assert B.import_cycles(pkg)["module_level"]


def test_the_scorecard_names_its_own_gaps():
    card = B.build(since="2026-09-22")
    assert card["gaps"] and any("pipeline_version" in g for g in card["gaps"])
    assert "weak" in card["version_attribution"]


# ----------------------------------------------------------------------------- the branch drill
def test_the_branch_drill_grows_a_real_branch_without_touching_code():
    """D8: the fitness functions say a branch COULD be grown; the drill grows one on a copy of the
    library and requires the real planner to carry it with no forge/*.py changed."""
    from forge.offline import branch_drill as BD
    r = BD.drill()
    assert r["ok"] is True and r["status"] == "carried"
    assert r["constructions"] > 0 and r["other_constructions"] == 0
    assert r["code_unchanged"] is True


def test_the_branch_drill_never_deletes_a_plan_it_did_not_write(tmp_path):
    """MEASURED 2026-09-23: unlinking plans/<seed>.json blindly deleted a pre-existing plan when the
    seed collided (157 -> 156). An explicit seed that already has a plan is refused outright."""
    from forge.offline import branch_drill as BD
    from forge import runner as R
    existing = sorted(R.PLANS.glob("*.json"))[0]
    seed = int(existing.stem) if existing.stem.isdigit() else None
    if seed is None:
        pytest.skip("no numeric plan file to collide with")
    before = existing.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        BD.drill(seed=seed)
    assert existing.read_bytes() == before


def test_axis3_counts_the_drill_as_a_fitness_function():
    a = B.axis3_gearing(drill={"ok": False, "status": "not-carried", "note": "x"})
    names = [f["name"] for f in a["fitness_functions"]]
    assert "a real branch goes through the planner" in names
    assert a["held"] < a["of"]


# -------------------------------------------------------------------------------------- DORA
def test_dora_refuses_to_compute_from_one_point():
    assert B.dora([])["status"] == "insufficient"
    assert B.dora([{"outcome": "deployed", "started_at": 1, "finished_at": 2}])["status"] == "insufficient"


def test_dora_computes_the_four_keys_on_a_known_ledger():
    H = 3600.0
    rows = [
        {"outcome": "deployed", "started_at": 0, "finished_at": 1 * H, "commit_time": 0, "git_dirty": False},
        {"outcome": "rolled_back", "started_at": 10 * H, "finished_at": 11 * H, "commit_time": 9 * H, "git_dirty": False},
        {"outcome": "deployed", "started_at": 13 * H, "finished_at": 14 * H, "commit_time": 12 * H, "git_dirty": False},
        {"outcome": "deployed", "started_at": 20 * H, "finished_at": 21 * H, "commit_time": 20 * H, "git_dirty": True},
    ]
    d = B.dora(rows, now=21 * H, window_days=28)
    assert d["status"] == "measured" and d["deploys"] == 4
    assert d["change_failure_rate"] == pytest.approx(0.25)
    assert d["time_to_restore_hours_median"] == pytest.approx(3.0)       # 11h fail -> 14h clean
    # lead time uses clean deploys only: 1h and 2h -> median 1.5h; the dirty one has no honest commit
    assert d["lead_time_hours_median"] == pytest.approx(1.5)
    assert d["deploys_per_week"] == pytest.approx(1.0)
