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


# -------------------------------------------------------------------------- axis 1's measures
def _row(alpha, sharpe, formula="rank(x)", decay=4, neut="INDUSTRY", trunc=0.08, hyp="h"):
    return {"alpha": alpha, "sharpe": sharpe, "formula": formula,
            "settings": {"region": "USA", "delay": 1, "universe": "TOP3000", "decay": decay,
                         "neutralization": neut, "truncation": trunc},
            "meta": {"hypothesis": hyp}}


def _by_formula(rows):
    import collections
    idx = collections.defaultdict(list)
    for r in rows:
        s = r["settings"]
        idx[(B._norm_formula(r["formula"]), s["region"], s["delay"], s["universe"])].append(r)
    return idx


def test_neighbourhood_uses_true_one_setting_neighbours_only():
    """Round 1, S2: the whole hypothesis group is not a neighbourhood. Only the same formula with
    exactly one of decay / neutralisation / truncation changed counts."""
    me = _row("me", 1.7)
    rows = [me, _row("d8", 0.1, decay=8), _row("sub", 0.2, neut="SUBINDUSTRY"),
            _row("two_knobs", 1.7, decay=8, neut="SECTOR"),          # two settings differ: not a neighbour
            _row("other_formula", 1.7, formula="rank(y)", decay=8)]   # a different formula: not a neighbour
    v = B.neighbourhood_stability(_by_formula(rows), me)
    assert v["n"] == 2 and v["verdict"] == "fragile"
    steady = [me, _row("d8", 1.6, decay=8), _row("sub", 1.5, neut="SUBINDUSTRY")]
    assert B.neighbourhood_stability(_by_formula(steady), me)["verdict"] == "stable"


def test_too_few_neighbours_is_unmeasured_never_a_pass_or_a_fail():
    me = _row("me", 1.7)
    assert B.neighbourhood_stability(_by_formula([me, _row("d8", 1.6, decay=8)]), me)["verdict"] == "unmeasured"


def test_a_cached_curve_is_a_date_dict_and_is_read_in_date_order():
    """Round 1, F2: all 2,810 cached curves are {date: cumulative} dicts and the first version turned
    every one into [] -- axis 1 read 'insufficient' for every alpha."""
    import datetime
    d0 = datetime.date(2019, 1, 2)
    curve = {(d0 + datetime.timedelta(days=i)).isoformat(): float(i) for i in range(400)}
    shuffled = dict(reversed(list(curve.items())))              # insertion order must not matter
    assert B.curve_values(shuffled) == [float(i) for i in range(400)]
    assert B.regime_stability(shuffled)["verdict"] == "consistent"


def test_regime_stability_separates_a_steady_alpha_from_a_one_window_bet():
    steady = [i * 1.0 for i in range(400)]
    v = B.regime_stability(steady)
    assert v["verdict"] == "consistent" and all(x == float("inf") for x in v["thirds"])
    one = [i * 1.0 for i in range(133)] + [132.0] * 267
    assert B.regime_stability(one)["verdict"] == "one-regime"
    two = [i * 1.0 for i in range(266)] + [265.0] * 134
    assert B.regime_stability(two)["verdict"] == "mixed"


def test_a_short_or_absent_curve_is_unmeasured():
    assert B.regime_stability([1, 2, 3])["verdict"] == "unmeasured"
    assert B.regime_stability(None)["verdict"] == "unmeasured"


def test_alpha_status_keeps_unmeasured_apart_from_passed_and_failed():
    assert B.alpha_status({"a": True, "b": True}) == "proven"
    assert B.alpha_status({"a": True, "b": None}) == "unproven"
    assert B.alpha_status({"a": False, "b": None}) == "refuted"


# ------------------------------------------------------------------------ axis 2 and the composite
def test_the_two_submission_readings_are_reported_separately():
    """rK5RGeqa was generated 09-10 and POSTed on the 09-22 ET quota day: not this version's product
    under D14, but today's submission to the operator."""
    rows = [{"alpha": "x", "sharpe": 1.0, "checks": [], "formula": None, "meta": {}, "settings": {}}]
    t = B.axis2_throughput(rows, [], days=1, clean_alphas=set(), posts_in_window=[{"alpha": "older"}])
    assert t["submissions_of_alphas_this_version_produced"] == 0 and t["posts_this_version_made"] == 1


def test_axis2_is_per_quota_day_and_counts_only_clean_submissions():
    """Round 1, F3 and F4: the floor is per quota day; a refuted submission is not throughput."""
    rows = [{"alpha": str(i), "checks": [], "formula": None, "meta": {}, "settings": {}} for i in range(100)]
    subs = [{"alpha": "1", "mechanism_key": "a"}, {"alpha": "2", "mechanism_key": "b"}]
    t = B.axis2_throughput(rows, subs, days=2, clean_alphas={"1"})
    assert t["clean_submissions"] == 1 and t["clean_per_quota_day"] == 0.5
    assert t["poisson_95_per_day"][0] > 0.0


def test_sustainable_needs_all_three_pieces_of_evidence():
    rows = [{"alpha": str(i), "checks": [], "formula": None, "meta": {}, "settings": {}} for i in range(100)]
    subs = [{"alpha": str(i), "mechanism_key": m} for i, m in ((1, "a"), (2, "b"), (3, "a"), (4, "b"))]
    clean = {"1", "2", "3", "4"}
    assert B.axis2_throughput(rows, subs, 2, clean, prev_rate=1.0)["sustainable"] is True
    one_mech = [{"alpha": str(i), "mechanism_key": "a"} for i in (1, 2, 3, 4)]
    assert B.axis2_throughput(rows, one_mech, 2, clean, prev_rate=1.0)["sustainable"] is False
    assert B.axis2_throughput(rows, subs, 2, clean, prev_rate=None)["sustainable"] is False


def test_the_poisson_interval_is_a_rate_per_day_and_bounds_zero_events():
    lo, hi = B.poisson_interval(0, 1)
    assert lo == 0.0 and 3.6 < hi < 3.8                      # exact upper bound for k=0 is -ln(0.025)
    lo, hi = B.poisson_interval(4, 19)
    assert 0.05 < lo < 0.06 and 0.53 < hi < 0.55             # the desk's own history, 4 over 19 days


def _card(clean, refuted, days=1):
    """A two-axis card from counts, through the real axis functions and the real scorecard."""
    a1 = {"value": (clean / (clean + refuted)) if clean + refuted else 0.0, "floor_met": refuted == 0 and clean > 0}
    a2 = {"value": clean / days, "floor_met": clean / days >= 4}
    return B.scorecard({"axis1_product": a1, "axis2_throughput": a2, "axis3_gearing": {"value": 1.0, "floor_met": True}})


def test_the_composite_is_monotone_in_clean_output_and_junk_never_beats_nothing():
    """Round 1, F4: 4 submissions with 3 clean scored below 1 clean; one bad submission scored above
    none; every card that cleared the floors read exactly 100."""
    assert _card(3, 1)["composite_0_100"] > _card(1, 0)["composite_0_100"]
    assert _card(0, 1)["composite_0_100"] <= _card(0, 0)["composite_0_100"]
    assert _card(8, 0)["composite_0_100"] > _card(4, 0)["composite_0_100"]     # no saturation at the floor


def _journal_row(alpha, day, status="COMPLETE", version=None):
    return {"alpha": alpha, "status": status, "checks": [{"name": "LOW_SHARPE", "result": "FAIL"}],
            "dateCreated": "%sT12:00:00-04:00" % day, "formula": "rank(%s)" % alpha,
            "settings": {"region": "USA", "delay": 1}, "meta": {"pipeline_version": version} if version else {}}


def test_the_window_is_whole_et_quota_days_and_never_the_unfinished_one():
    """Round 1, S5: local midnight, and a one-minute window 'met' 4 per day."""
    import datetime
    now = datetime.datetime(2026, 9, 23, 15, 0, tzinfo=B.ET).timestamp()
    rows = [_journal_row("a", "2026-09-21"), _journal_row("b", "2026-09-22"), _journal_row("c", "2026-09-23")]
    card = B.build_from(rows, {}, {}, [], {}, {}, now=now)
    assert card["window"]["quota_days"] == 2 and card["window"]["excluded_unfinished_day"] == "2026-09-23"
    assert card["axes"]["axis2_throughput"]["scored_alphas"] == 2          # c, from the unfinished day, is out


def test_warning_rows_are_scored():
    """Round 1, F3: WARNING rows (16 % of the journal, the first ACTIVE submission among them) were dropped."""
    import datetime
    now = datetime.datetime(2026, 9, 23, 15, 0, tzinfo=B.ET).timestamp()
    card = B.build_from([_journal_row("w", "2026-09-22", status="WARNING")], {}, {}, [], {}, {}, now=now)
    assert card["axes"]["axis2_throughput"]["scored_alphas"] == 1


def test_an_unknown_version_is_an_error_not_all_history():
    with pytest.raises(ValueError, match="no scored row carries"):
        B.build_from([_journal_row("a", "2026-09-22", version="v1")], {}, {}, [], {}, {}, version="nope")


def test_compare_uses_equal_quota_days_and_can_say_indistinguishable():
    import datetime
    rows = [_journal_row("a%d" % i, "2026-09-%02d" % (10 + i), version="A") for i in range(3)]
    rows += [_journal_row("b%d" % i, "2026-09-%02d" % (14 + i), version="B") for i in range(5)]
    hist = [{"alpha": "b0", "http": 201, "posted_at": datetime.datetime(2026, 9, 14, 12, tzinfo=B.ET).timestamp()}]
    out = B.compare(rows, hist, {}, {}, {}, {}, "A", "B")
    assert out["quota_days_each"] == 3                        # B is judged on its first 3 days, not 5
    assert out["verdict"] == "indistinguishable"              # 0 vs 1 over 3 days cannot be told apart


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
