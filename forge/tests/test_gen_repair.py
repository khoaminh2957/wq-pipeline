"""forge.gen.repair: the D37 trigger, coin and grid; the D51 neighbours, counted by the judge's own rule."""
import hashlib

from forge.factory import candidate_id
from forge.gen import productions as P
from forge.gen import repair as RP
from forge.offline import benchmark as BM

BINDING = BM.ESTIMAND["binding_checks"]
BASE = {"region": "USA", "universe": "TOP3000", "delay": 1, "neutralization": "INDUSTRY", "decay": 4, "truncation": 0.08}


def trow(alpha="A", formula="multiply(rank(g01_f01), rank(g02_f03))", fails=("LOW_FITNESS",), extra=(), hyp="gen:famR",
         sharpe=1.5, settings=None):
    cks = [{"name": n, "result": "FAIL" if n in fails else "PASS"} for n in BINDING]
    cks += [{"name": "SELF_CORRELATION", "result": "PENDING"}, {"name": "MATCHES_THEMES", "result": "WARNING"}]
    cks += [dict(c) for c in extra]
    return {"alpha": alpha, "formula": formula, "sharpe": sharpe, "checks": cks, "settings": dict(settings or BASE),
            "meta": {"hypothesis": hyp}}


def test_a_trigger_fails_exactly_one_harvest_pass_check_and_nothing_is_pending():
    assert RP.is_trigger(trow())
    assert RP.is_trigger(trow(fails=(), extra=[{"name": "UNITS", "result": "WARNING"}]))      # UNITS binds harvest
    assert not RP.is_trigger(trow(fails=("LOW_FITNESS", "LOW_SHARPE")))
    assert not RP.is_trigger(trow(extra=[{"name": "LOW_2Y_SHARPE", "result": "PENDING"}]))
    assert not RP.is_trigger(trow(fails=()))                                                    # a pass is no trigger
    assert not RP.is_trigger(trow(hyp="usa_short_x_profitability"))                            # generated rows only
    assert not RP.is_trigger(dict(trow(), alpha=None))
    assert RP.failing(trow()) == (["LOW_FITNESS"], [])


def test_the_coin_is_keyed_on_the_formula_reproducible_and_fair():
    f = "multiply(rank(g01_f01), rank(g02_f03))"
    want = hashlib.sha256((RP.COIN_SALT + hashlib.sha256(f.encode()).hexdigest()).encode()).digest()[0] & 1 == 1
    assert RP.coin(f) is want and RP.coin(f) is RP.coin(f)
    heads = sum(RP.coin("rank(g%02d_f%04d)" % (i % 40, i)) for i in range(2000))
    assert 900 <= heads <= 1100                                # fair: 2,000 flips, +-4.5 sd
    assert RP.COIN_SALT == "forge.gen D37 repair coin v1|"    # pre-registered: changing it re-draws the control


def test_the_grid_is_the_eleven_other_settings_each_once():
    g = RP.grid(BASE)
    keys = {(s["neutralization"], s["decay"], s["truncation"]) for s in g}
    assert len(g) == 11 == len(keys) and ("INDUSTRY", 4, 0.08) not in keys
    assert keys <= {(n, d, t) for n in P.NEUT for d in P.DECAY for t in P.TRUNC}
    assert all((s["region"], s["universe"], s["delay"]) == ("USA", "TOP3000", 1) for s in g)
    r = trow()
    seen = {candidate_id(r["formula"], s) for s in g[:4]}
    assert RP.unsimulated(r, seen) == g[4:]


def test_triggers_are_one_per_formula_oldest_first():
    rows = {"A": trow("A", formula="rank(a1)"), "B": trow("B", formula="rank(b1)"),
            "C": trow("C", formula="rank( a1 )", settings=dict(BASE, decay=8)), "D": trow("D", formula="rank(d1)", fails=())}
    assert [r["alpha"] for r in RP.triggers(rows)] == ["A", "B"]


def _index(rows):
    idx = {}
    for r in rows:
        idx.setdefault(RP.formula_key(r), []).append(r)
    return idx


def test_neighbours_are_two_one_setting_moves_the_judge_counts():
    base = trow("P", fails=(), sharpe=2.0)
    got = RP.neighbours(base, _index([base]), set())
    assert len(got) == 2
    sims = [dict(trow("N%d" % i, fails=(), sharpe=1.8), settings=s) for i, s in enumerate(got)]
    by_formula = {}
    for r in [base] + sims:
        by_formula.setdefault((BM._norm_formula(r["formula"]), "USA", 1, "TOP3000"), []).append(r)
    assert BM.neighbourhood_stability(by_formula, base)["n"] == 2          # the judge sees both
    assert RP.neighbours(base, _index([base] + sims), set()) == []        # nothing more once two exist


def test_neighbours_count_existing_ones_skip_simulated_ones_and_keep_a_keyed_order():
    base = trow("P", fails=(), sharpe=2.0)
    one = dict(trow("R", sharpe=1.1), settings=dict(BASE, decay=8))         # e.g. a repair row, one knob away
    got = RP.neighbours(base, _index([base, one]), set())
    assert len(got) == 1 and got[0]["decay"] == 4
    first = RP.neighbours(base, _index([base]), set())
    errored = {candidate_id(base["formula"], first[0])}
    again = RP.neighbours(base, _index([base]), errored)
    assert first[0] not in again and len(again) == 2
    assert RP.neighbours(base, _index([base]), set()) == first               # keyed on the alpha: reproducible
    orders = {tuple((s["neutralization"], s["decay"], s["truncation"]) for s in
                    RP.neighbours(dict(base, alpha="P%d" % i), _index([base]), set())) for i in range(20)}
    assert len(orders) > 1                                                   # not one fixed knob for every alpha
    assert all(sum(s[k] != BASE[k] for k in ("neutralization", "decay", "truncation")) == 1
               for s in RP.one_setting_variants(BASE)) and len(RP.one_setting_variants(BASE)) == 4


def _stamped(r, pv="V1", rc="rc1"):
    return dict(r, meta=dict(r["meta"], pipeline_version=pv, run_config=rc))


def test_an_out_of_cohort_sibling_is_not_a_neighbour_the_judge_counts():
    """Draw-5 gen G1 (d5gen_adj_d51.py): alpha A stamped V1, its two one-setting rows stamped V2. The judge's V1
    card draws neighbours from V1's rows only (benchmark.build_from, S10-NL) and read A UNMEASURED, while this
    file planned 0 more. Out-of-cohort siblings must not reduce `need`, and must not be re-planned either."""
    base = _stamped(trow("P", fails=(), sharpe=2.0))
    v = RP.one_setting_variants(BASE)
    sibs = [_stamped(dict(trow("S%d" % i, fails=(), sharpe=1.8), settings=s), pv="V2") for i, s in enumerate(v[:2])]
    idx = _index([base] + sibs)
    assert RP.existing_neighbours(base, idx) == []
    got = RP.neighbours(base, idx, set())
    assert len(got) == 2 and not any(s in v[:2] for s in got)
    pool = [r for r in [base] + sibs if RP.cohort(r) == RP.cohort(base)]                 # the V1 card's pool
    by_formula = {}
    for r in pool:
        by_formula.setdefault((BM._norm_formula(r["formula"]), "USA", 1, "TOP3000"), []).append(r)
    assert BM.neighbourhood_stability(by_formula, base)["verdict"] == "unmeasured"      # what the judge reads
    same = [_stamped(dict(s, alpha="Q%d" % i)) for i, s in enumerate(sibs)]            # the same rows under V1
    assert len(RP.existing_neighbours(base, _index([base] + same))) == 2
    assert RP.neighbours(base, _index([base] + same), set()) == []
    other_rc = _stamped(dict(sibs[0], alpha="R0"), rc="rc2")                              # D30: the pair, not pv
    assert RP.existing_neighbours(base, _index([base, other_rc])) == []


def test_a_neighbour_needs_a_sharpe_one_knob_and_the_same_universe():
    """Draw-5 gen N5: R07 (an ERRORed row counted), R08 (a two-knob row counted), exec R14 (universe ignored)."""
    base = trow("P", fails=(), sharpe=2.0)
    one = RP.one_setting_variants(BASE)[0]
    errored = dict(trow("E", sharpe=None), settings=one)
    two_knob = dict(trow("K", sharpe=1.5), settings=dict(BASE, decay=8, truncation=0.15))
    other_u = dict(trow("U", sharpe=1.5), settings=dict(one, universe="TOP1000"))
    for r in (errored, two_knob, other_u):
        idx = {}
        for x in (base, r):
            idx.setdefault(RP.formula_key(x), []).append(x)
        assert RP.existing_neighbours(base, idx) == [], r["alpha"]
        assert len(RP.neighbours(base, idx, set())) == 2, r["alpha"]
    assert RP.existing_neighbours(base, _index([base, dict(trow("G", sharpe=1.5), settings=one)]))   # control


def test_the_setting_levels_are_pinned():
    """Architecture round 4 E3: repair and D51 take their steps from productions' NEUT / DECAY / TRUNC, and
    TRUNC = (0.08, 0.081) left every gen test green. The judge counts any one-knob sibling, so a 0.001 step
    would feed neighbourhood_stability as a true neighbour. Changing a level set is a decision, not an edit."""
    assert P.NEUT == ("STATISTICAL", "INDUSTRY", "SUBINDUSTRY")
    assert P.DECAY == (4, 8)
    assert P.TRUNC == (0.08, 0.15)
    assert [k for k, _ in RP.KNOBS] == ["neutralization", "decay", "truncation"]


def test_provable_is_generated_with_an_alpha_and_a_formula_and_harvest_pass():
    assert RP.provable(trow(fails=()))
    assert not RP.provable(trow())                                                         # fails one check
    assert not RP.provable(trow(fails=(), hyp="usa_library_hyp"))                          # draw-5 gen N2
    assert not RP.provable(trow(fails=(), extra=[{"name": "LOW_2Y_SHARPE", "result": "PENDING"}]))
    assert not RP.provable(dict(trow(fails=()), alpha=None))
    assert not RP.provable(dict(trow(fails=()), formula=None))
