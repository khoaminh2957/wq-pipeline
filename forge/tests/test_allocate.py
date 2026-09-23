from forge import allocate as A
from forge import cells as C


class _Comp:
    def __init__(self, id, cats):
        self.id, self.categories = id, cats


def _row(alpha, hyp, sharpe, region="USA", delay=1, cat="Short Interest", passed=False, fails=("LOW_SHARPE",), mk="k"):
    ck = [{"name": "LOW_SHARPE", "result": "PASS" if passed else "FAIL"},
          {"name": "LOW_FITNESS", "result": "PASS"}, {"name": "CONCENTRATED_WEIGHT", "result": "PASS"}]
    if not passed:
        ck = [{"name": n, "result": "FAIL"} for n in fails] + [{"name": "LOW_FITNESS", "result": "PASS"}]
    return {"alpha": alpha, "sharpe": sharpe, "checks": ck, "turnover": 0.1,
            "settings": {"region": region, "delay": delay}, "meta": {"forge": 1, "hypothesis": hyp, "category": cat, "mechanism_key": mk}}


def test_classes():
    rows = {}
    for i in range(70):
        rows["d%d" % i] = _row("d%d" % i, "dead", 0.5, mk="kd")                       # dead: 70 sims, best 0.5
    rows["n1"] = _row("n1", "near", 1.45, mk="kn")                                     # near miss: 1.45, LOW_SHARPE only
    rows["g1"] = _row("g1", "glb", 1.45, region="GLB", cat="Fundamental", fails=("LOW_SHARPE", "LOW_GLB_APAC_SHARPE"), mk="kg")
    rows["p1"] = _row("p1", "passed", 1.9, passed=True, mk="kp")
    rows["h1"] = _row("h1", "harv", 1.9, passed=True, mk="kh")
    rows["a1"] = _row("a1", "active", 0.9, mk="ka")
    st = A.pair_states(rows, posted_keys={"kh"})
    cls = {k[0]: A.classify(v) for k, v in st.items()}
    assert cls == {"dead": "DEAD", "near": "NEAR_MISS", "glb": "ACTIVE", "passed": "PASSED", "harv": "HARVESTED", "active": "ACTIVE"}
    assert A.classify(None) == "UNTRIED"
    assert st[("dead", "USA/d1", "Short Interest")]["sims"] == 70
    assert A.summary(st)["DEAD"] == 1


def test_order_skips_and_prioritises():
    rows = {"n1": _row("n1", "near", 1.45, mk="kn"), "h1": _row("h1", "harv", 1.9, passed=True, mk="kh"),
            "p1": _row("p1", "passed", 1.9, passed=True, mk="kp")}
    for i in range(70):
        rows["d%d" % i] = _row("d%d" % i, "dead", 0.5, mk="kd")
    st = A.pair_states(rows, posted_keys={"kh"})
    cells = [C.Cell("USA", 1, "Short Interest", "TOP3000", 2, 1, 1.1, 10, (), 1.1),
             C.Cell("USA", 1, "Insiders", "TOP3000", 2, 1, 1.1, 10, (), 1.1)]
    comps = [_Comp("dead", ["Short Interest"]), _Comp("near", ["Short Interest"]), _Comp("harv", ["Short Interest"]),
             _Comp("passed", ["Short Interest"]), _Comp("fresh", ["Short Interest", "Insiders"]), _Comp("other", ["News"])]
    got = [(cell.category, comp.id, block, cls) for cell, comp, block, cls in A.order(cells, comps, st, per_block=20)]
    # "fresh" fills Short Interest and Insiders on the same USA/d1: one block, its alphas count for both cells
    assert got == [("Short Interest", "near", 40, "NEAR_MISS"), ("Short Interest", "passed", A.PASSED_BLOCK, "PASSED"),
                   ("Short Interest", "fresh", 10, "UNTRIED")]
    assert A.PASSED_BLOCK == 40      # Khoa 2026-09-09: a pair with a platform pass and no submission gets a real block


def test_cold_cells_go_after_warm_ones():
    rows = {}
    for i in range(320):                                                       # GLB Fundamental: 320 sims, 0 pass
        rows["g%d" % i] = _row("g%d" % i, "compA", 0.8, region="GLB", cat="Fundamental", mk="ka")
    rows["u1"] = _row("u1", "compA", 0.8, region="USA", cat="Fundamental", mk="kb")   # USA: 1 sim, active
    st = A.pair_states(rows, posted_keys=set())
    assert A.cold_cells(st) == {("GLB/d1", "Fundamental")}
    cells = [C.Cell("GLB", 1, "Fundamental", "MINVOL1M", 0, 3, 1.4, 10, (), 4.2),
             C.Cell("USA", 1, "Fundamental", "TOP3000", 0, 3, 1.1, 10, (), 3.3)]
    comps = [_Comp("compA", ["Fundamental"]), _Comp("compB", ["Fundamental"])]
    got = [(cell.region, comp.id, cls) for cell, comp, block, cls in A.order(cells, comps, st, per_block=20)]
    # GLB compA itself is DEAD (320 sims, 0 pass, best 0.8) and absent; GLB's untried composite goes after USA's
    assert got == [("USA", "compB", "UNTRIED"), ("GLB", "compB", "UNTRIED"), ("USA", "compA", "ACTIVE")]


def test_near_miss_needs_dsr_headroom_and_cold_needs_structural_failure():
    rows = {}
    # wide-spread pair: best 1.45 but sharpes all over the place -> SR0 too high -> stays ACTIVE
    for i, sh in enumerate([-1.5, -1.0, 0.2, 0.6, 1.45, -0.8, 1.2, -1.3, 0.1, 0.9] * 4):
        rows["w%d" % i] = _row("w%d" % i, "wide", sh, mk="kw")
    # tight pair: best 1.45 with a tight spread -> NEAR_MISS
    for i, sh in enumerate([1.1, 1.2, 1.3, 1.45, 1.15, 1.25, 1.0, 1.35, 1.2, 1.3] * 4):
        rows["t%d" % i] = _row("t%d" % i, "tight", sh, region="USA", cat="Insiders", mk="kt")
    st = A.pair_states(rows, posted_keys=set())
    assert A.classify(st[("wide", "USA/d1", "Short Interest")]) == "ACTIVE"
    assert A.classify(st[("tight", "USA/d1", "Insiders")]) == "NEAR_MISS"
    assert A.dsr_headroom(st[("wide", "USA/d1", "Short Interest")]) > A.dsr_headroom(st[("tight", "USA/d1", "Insiders")])
    # cold cells: 320 sims, 0 pass, best 1.28 with Sharpe-like fails -> NOT cold; GLB with a regional fail -> cold
    rows2 = {}
    for i in range(320):
        rows2["s%d" % i] = _row("s%d" % i, "c1", 1.28 if i == 0 else 0.4, region="USA", cat="Sentiment", mk="k1")
    for i in range(320):
        rows2["g%d" % i] = _row("g%d" % i, "c2", 1.42 if i == 0 else 0.4, region="GLB", cat="Fundamental",
                                fails=("LOW_SHARPE", "LOW_GLB_APAC_SHARPE"), mk="k2")
    st2 = A.pair_states(rows2, posted_keys=set())
    assert A.cold_cells(st2) == {("GLB/d1", "Fundamental")}


def test_overlap_blocked():
    posted = {"vRk": ["short_volume_ratio_informed", "usa_profitability_ratios", "usa_accruals_cashflow"]}
    assert A.overlap_blocked(_Comp("x", []), posted) is False
    c = _Comp("y", []); c.legs = ["insider_significant_buying_drift", "short_volume_ratio_informed", "usa_profitability_ratios"]
    assert A.overlap_blocked(c, posted) is True                 # two shared legs
    c.legs = ["insider_significant_buying_drift", "option_call_put_iv_spread"]
    assert A.overlap_blocked(c, posted) is False                # none shared
    c.legs = ["short_volume_ratio_informed", "option_call_put_iv_spread"]
    assert A.overlap_blocked(c, posted) is False                # one shared leg is allowed


def test_d0_pairs_are_judged_against_the_d0_bar():
    """2026-09-07: USA/d0 pairs with best 1.74 against a 2.69 line were exploited as near misses."""
    rows = {"z%d" % i: _row("z%d" % i, "ivs", 1.74 if i == 0 else 1.2, delay=0, cat="Sentiment", mk="k0") for i in range(10)}
    st = A.pair_states(rows, posted_keys=set())
    assert A.classify(st[("ivs", "USA/d0", "Sentiment")]) == "ACTIVE"          # 1.74 < 1.3 * 2.69/1.58
    rows1 = {"y%d" % i: _row("y%d" % i, "ivs", 1.74 if i == 0 else 1.2, delay=1, cat="Sentiment", mk="k1") for i in range(10)}
    assert A.classify(A.pair_states(rows1, set())[("ivs", "USA/d1", "Sentiment")]) == "NEAR_MISS"
    dead0 = {"w%d" % i: _row("w%d" % i, "slow", 1.4, delay=0, cat="Sentiment", mk="k2") for i in range(45)}
    assert A.classify(A.pair_states(dead0, set())[("slow", "USA/d0", "Sentiment")]) == "DEAD"   # 1.4 < 1.0 * 1.70


def test_one_block_per_composite_region_delay():
    st = {}
    cells = [C.Cell("USA", 0, "Other", "TOP3000", 2, 1, 1.1, 10, (), 1.1),
             C.Cell("USA", 0, "Option", "TOP3000", 2, 1, 1.1, 10, (), 1.1),
             C.Cell("USA", 1, "Option", "TOP3000", 2, 1, 1.1, 10, (), 1.1)]
    comps = [_Comp("ivs", ["Other", "Option"])]
    got = [(cell.delay, cell.category) for cell, comp, block, cls in A.order(cells, comps, st, per_block=20)]
    assert got == [(0, "Other"), (1, "Option")]


def test_ladder_dead_kills_pairs_that_never_cleared_the_first_window(monkeypatch):
    def ladder(row, result, year):
        row["checks"].append({"name": "IS_LADDER_SHARPE", "result": result, "year": year, "limit": 1.58})
        return row
    rows = {}
    for i in range(40):                                                     # 40 rows, best 1.2, none past year 2
        rows["x%d" % i] = ladder(_row("x%d" % i, "stuck", 1.2, mk="ks"), "FAIL", 2)
    for i in range(40):                                                     # 40 rows, one FAIL reported at year 3 = window cleared
        rows["y%d" % i] = ladder(_row("y%d" % i, "climbs", 1.2, mk="kc"), "FAIL", 3 if i == 7 else 2)
    rows["z1"] = ladder(_row("z1", "young", 1.2, mk="ky"), "FAIL", 2)         # 1 row: too few to judge
    for i in range(25):                                                     # a NEAR_MISS-grade best (1.7) split over two categories
        rows["s%d" % i] = ladder(_row("s%d" % i, "split", 1.7, cat="Short Interest", mk="kp"), "FAIL", 2)
        rows["t%d" % i] = ladder(_row("t%d" % i, "split", 1.7, cat="News", mk="kp"), "FAIL", 2)
    st = A.pair_states(rows, posted_keys=set())
    assert A.cleared_first_window(rows["y7"]) and not A.cleared_first_window(rows["x1"])
    assert st[("stuck", "USA/d1", "Short Interest")]["ladder_y2"] is False
    assert st[("climbs", "USA/d1", "Short Interest")]["ladder_y2"] is True
    monkeypatch.setattr(A, "LADDER_DEAD", False)
    assert A.classify(st[("stuck", "USA/d1", "Short Interest")]) == "ACTIVE"      # OFF: nothing changes
    monkeypatch.setattr(A, "LADDER_DEAD", True)                                   # ON (Khoa 2026-09-09)
    assert A.classify(st[("stuck", "USA/d1", "Short Interest")]) == "DEAD"
    assert A.classify(st[("climbs", "USA/d1", "Short Interest")]) == "ACTIVE"
    assert A.classify(st[("young", "USA/d1", "Short Interest")]) == "ACTIVE"
    # 25 + 25 rows over two category names = 50 on USA/d1, none past the window: DEAD under both names,
    # even though its 5-year best (1.7) would otherwise make it a NEAR_MISS
    assert st[("split", "USA/d1", "News")]["sims_rd"] == 50
    assert A.classify(st[("split", "USA/d1", "News")]) == "DEAD" and A.classify(st[("split", "USA/d1", "Short Interest")]) == "DEAD"
    monkeypatch.setattr(A, "LADDER_DEAD", False)
    assert A.classify(st[("split", "USA/d1", "News")]) in ("NEAR_MISS", "ACTIVE")
