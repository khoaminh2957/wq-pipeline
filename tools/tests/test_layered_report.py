"""The report must compute the factorial contrast, and must refuse when the rows are not there.

Why this file exists, stated plainly: the only test of `layered_report.py` before it read the
module's SOURCE and grepped it for three strings. It stayed GREEN with the refusal thresholds set
to 0, because a string in a docstring is not a refusal. That was the THIRD guard test of that class
found in this project. Every assertion below drives the real code path and checks the printed
output, and each threshold is exercised on BOTH sides of its boundary, so mutating the constant to
0 turns this file red instead of leaving it green.

No network, no simulation, no submit.
"""
import math
import pathlib
import random
import socket
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import layered_report as LR  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a test opened a socket")
    monkeypatch.setattr(socket, "socket", boom)


def mk(cell, sharpe=0.1, fitness=0.2, turnover=0.3, returns=0.02, **kw):
    """One terminal journal row in the shape `layered_sim._child_row` writes."""
    r = {"status": "COMPLETE", "sharpe": sharpe, "fitness": fitness, "turnover": turnover,
         "returns": returns, "meta": {"factors": dict(cell), "n_legs": 1, "legs": [{}]}}
    r.update(kw)
    return r


def run(blocks):
    lines = []
    LR.report(blocks, out=lambda s="": lines.append(str(s)))
    return "\n".join(lines)


# ------------------------------------------------------------------ the statistics, re-derived

def test_mann_whitney_agrees_with_scipy_to_machine_precision():
    """RULE 0 §5: derive it a second way before reporting it. scipy is not a dependency of the
    module, so it is the independent derivation, not the implementation."""
    scipy_stats = pytest.importorskip("scipy.stats")
    rng = random.Random(7)
    worst = 0.0
    for _ in range(120):
        a = [round(rng.gauss(0, 1), 2) for _ in range(rng.randint(5, 60))]     # 2dp -> heavy ties
        b = [round(rng.gauss(0.3, 1), 2) for _ in range(rng.randint(5, 60))]
        u1, p1 = LR.mannwhitney(a, b)
        u2, p2 = scipy_stats.mannwhitneyu(a, b, alternative="two-sided", method="asymptotic")
        assert u1 == pytest.approx(u2)
        worst = max(worst, abs(p1 - p2))
    assert worst < 1e-12


def test_the_hl_shift_is_the_median_pairwise_difference_and_its_ci_covers():
    rng = random.Random(11)
    for _ in range(20):
        a = [rng.gauss(0, 1) for _ in range(rng.randint(20, 60))]
        b = [rng.gauss(0.5, 1) for _ in range(rng.randint(20, 60))]
        shift, lo, hi, _note = LR.hl_shift(a, b)
        pairs = sorted(x - y for x in a for y in b)
        ref = (pairs[len(pairs) // 2] if len(pairs) % 2
               else (pairs[len(pairs) // 2 - 1] + pairs[len(pairs) // 2]) / 2.0)
        assert shift == pytest.approx(ref)
        assert lo <= shift <= hi
    cov = sum(1 for _ in range(300)
              if (lambda t: t[1] <= 0.5 <= t[2])(
                  LR.hl_shift([rng.gauss(0.5, 1) for _ in range(40)],
                              [rng.gauss(0.0, 1) for _ in range(40)])))
    assert 0.90 <= cov / 300 <= 1.0, "a 95%% CI that covers a known shift 90%% of the time is broken"


def test_holm_is_applied_over_the_family_of_sixteen_and_is_the_conservative_one():
    p = [0.001, 0.02, 0.04, 0.30]
    assert LR.holm(p) == pytest.approx([0.004, 0.06, 0.08, 0.30])
    assert LR.holm(p) == sorted(LR.holm(p)), "Holm must be monotone in the raw p order"
    sixteen = LR.holm([0.001] + [0.5] * 15)[0]
    four = LR.holm([0.001] + [0.5] * 3)[0]
    assert sixteen > four, "the 16-test family must be more conservative than the 4-test family"


def test_the_returns_floor_is_the_fitness_identity_not_a_typed_in_number():
    """fitness = sharpe*sqrt(|returns|/max(turnover,0.125)) was verified exact on 69,659 rows.
    Changing a gate constant without changing the floor must break this."""
    implied = (LR.GATE_FITNESS / LR.GATE_SHARPE) ** 2 * 0.125
    assert LR.FITNESS_RETURNS_FLOOR == pytest.approx(implied, abs=5e-5)


# ------------------------------------------------------------------ reading the cell

@pytest.mark.parametrize("meta,want", [
    ({"factors": {"D": 1, "C": 0, "U": True, "S": "off"}}, {"D": 1, "C": 0, "U": 1, "S": 0}),
    ({"cell": "D1C0U1S1"}, {"D": 1, "C": 0, "U": 1, "S": 1}),
    ({"cell": "s0u0d1c1"}, {"D": 1, "C": 1, "U": 0, "S": 0}),
    ({"arm": "units"}, {"U": 1}),
    ({"arm": "control"}, {"U": 0}),
    ({"arm": "free"}, {"S": 1}),
    ({"arm": "ordered"}, {"S": 0}),
    ({"n_legs": 3}, {}),
])
def test_every_producer_shape_is_read_and_an_absent_factor_stays_unknown(meta, want):
    assert LR.cell_of({"meta": meta}) == want


# ------------------------------------------------------------------ the factorial

def sixteen_cells(n_per_cell=25, block="r1", effect=0.0):
    """A balanced 2^4. `effect` is added to sharpe when D is on, and to nothing else."""
    rng = random.Random(3)
    rows = []
    for i in range(16):
        cell = {"D": (i >> 3) & 1, "C": (i >> 2) & 1, "U": (i >> 1) & 1, "S": i & 1}
        for _ in range(n_per_cell):
            rows.append(mk(cell, sharpe=rng.gauss(0, 1) + effect * cell["D"],
                           fitness=rng.gauss(0.3, 0.2), turnover=abs(rng.gauss(0.3, 0.1)) + 0.01,
                           returns=rng.gauss(0.02, 0.01)))
    return [(block, rows)]


def test_sixteen_cells_produce_four_main_effects_and_never_the_false_one_arm_sentence():
    """The bug this replaces: `if len(arms)==2` fell through to `elif arms:` and printed
    'only one arm present' on a 16-cell corpus -- a false sentence with no contrast behind it."""
    txt = run(sixteen_cells())
    assert "only one arm present" not in txt
    assert "cells present: 16" in txt
    for f in "DCUS":
        assert "FACTOR %s" % f in txt
    # 4 factors x 4 metrics, all computable at 200 rows per side
    assert "16 of 16 tests were computable." in txt
    for m in ("sharpe", "fitness", "turnover", "|returns|"):
        assert m in txt


def test_every_row_enters_every_contrast_which_is_what_makes_the_factorial_free():
    blocks = sixteen_cells(n_per_cell=25)
    total = len(blocks[0][1])
    txt = run(blocks)
    ons = [int(l.split("ON=")[1].split()[0]) for l in txt.splitlines()
           if l.strip().startswith("rows ON=")]
    offs = [int(l.split("OFF=")[1].split()[0]) for l in txt.splitlines()
            if l.strip().startswith("rows ON=")]
    # The fixture varies only the first four factors, so E and W legitimately read 0/0 -- the
    # report says NOT ASSIGNED for them rather than inventing a contrast, and that is the behaviour
    # under test. Asserting `[total//2] * len(FACTORS)` would demand the report fabricate rows for
    # factors the corpus never varied.
    varied, unassigned = ons[:4], ons[4:]
    assert varied == [total // 2] * 4 and offs[:4] == [total // 2] * 4
    assert all(x == 0 for x in unassigned), ons


def test_a_real_effect_on_one_factor_is_found_and_is_not_smeared_onto_the_other_three():
    txt = run(sixteen_cells(n_per_cell=40, effect=0.8))
    d = txt.split("FACTOR D")[1].split("FACTOR C")[0]
    sharpe = [l for l in d.splitlines() if l.strip().startswith("sharpe")][0]
    assert float(sharpe.split()[5]) > 0.5, sharpe          # HL(ON-OFF) recovers the injected shift
    assert float(sharpe.split()[-2]) < 0.01, sharpe        # p_h16 survives the 16-test correction
    for other in ("C", "U"):
        blk = txt.split("FACTOR %s" % other)[1].split("FACTOR")[0]
        line = [l for l in blk.splitlines() if l.strip().startswith("sharpe")][0]
        assert float(line.split()[-2]) > 0.05, line        # no effect leaks onto an untouched factor


def test_two_corpora_with_different_arm_vocabularies_pool_by_factor():
    """The pooled read that used to vanish silently: {ordered,free} + {units,control} produced four
    'arms', `len(arms)==2` never fired, and the comparison block disappeared with no message."""
    old = [mk({}, sharpe=0.1 + 0.001 * i, meta_arm="free" if i % 2 else "ordered")
           for i in range(60)]
    for i, r in enumerate(old):
        r["meta"] = {"arm": "free" if i % 2 else "ordered"}
        del r["meta_arm"]
    new = []
    for i in range(60):
        r = mk({}, sharpe=0.2 + 0.001 * i)
        r["meta"] = {"arm": "units" if i % 2 else "control"}
        new.append(r)
    txt = run([("baseline", old), ("round1", new)])
    s = txt.split("FACTOR S")[1]
    u = txt.split("FACTOR U")[1].split("FACTOR S")[0]
    assert "rows ON=30 OFF=30" in s and "identifying blocks (both levels present): baseline" in s
    assert "rows ON=30 OFF=30" in u and "identifying blocks (both levels present): round1" in u
    assert "NOT ASSIGNED in this corpus" in txt.split("FACTOR D")[1].split("FACTOR C")[0]


def test_a_factor_whose_two_levels_live_in_different_blocks_gets_no_verdict():
    """Within-batch or nothing: ON in one batch and OFF in another is the before/after comparison
    HARNESS_SOP.md forbids, and it must not silently produce a contrast."""
    a = [mk({"C": 1}, sharpe=1.0) for _ in range(40)]
    b = [mk({"C": 0}, sharpe=0.0) for _ in range(40)]
    txt = run([("r1", a), ("r2", b)])
    c = txt.split("FACTOR C")[1].split("FACTOR")[0]
    assert "IDENTIFIED ONLY BETWEEN BLOCKS" in c
    assert "HL(ON-OFF)" not in c, "a between-block contrast was computed anyway"
    # and the same rows inside ONE block do produce a contrast -- so the refusal is about the
    # design, not about the data being unusable
    txt2 = run([("r1", a + b)])
    assert "HL(ON-OFF)" in txt2.split("FACTOR C")[1].split("FACTOR")[0]


def test_a_sign_reversal_between_blocks_is_named():
    rows_a = [mk({"U": 1}, sharpe=1.0) for _ in range(25)] + \
             [mk({"U": 0}, sharpe=0.0) for _ in range(25)]
    rows_b = [mk({"U": 1}, sharpe=0.0) for _ in range(25)] + \
             [mk({"U": 0}, sharpe=1.0) for _ in range(25)]
    txt = run([("r1", rows_a), ("r2", rows_b)])
    assert "SIGN REVERSED ACROSS BLOCKS" in txt.split("FACTOR U")[1]


# ------------------------------------------------------------------ the three refusals, mutated

def test_the_twenty_row_refusal_fires_below_the_floor_and_lifts_above_it():
    """Both sides of the boundary. Set MIN_JUDGEABLE_PER_ARM to 0 in the module and the first
    assertion fails; delete the check entirely and it fails too."""
    def corpus(n):
        return [("r1", [mk({"D": 1}, sharpe=0.5) for _ in range(n)] +
                       [mk({"D": 0}, sharpe=0.0) for _ in range(n)])]
    below = run(corpus(LR.MIN_JUDGEABLE_PER_ARM - 1))
    above = run(corpus(LR.MIN_JUDGEABLE_PER_ARM + 1))
    d_below = below.split("FACTOR D")[1].split("FACTOR C")[0]
    d_above = above.split("FACTOR D")[1].split("FACTOR C")[0]
    assert "NO VERDICT: need >= %d judgeable rows per arm" % LR.MIN_JUDGEABLE_PER_ARM in d_below
    assert "p_raw" not in d_below or "0." not in d_below.split("sharpe")[1].split("\n")[0][40:]
    assert "NO VERDICT: need >=" not in d_above


def test_the_twenty_row_threshold_is_live_and_not_a_string_in_the_source(monkeypatch):
    """The mutation the previous guard test could not see: with the floor at 0 the SAME 3-row
    corpus produces a contrast. If this passes with the floor unread, the constant is decorative."""
    tiny = [("r1", [mk({"D": 1}, sharpe=0.5) for _ in range(3)] +
                   [mk({"D": 0}, sharpe=0.0) for _ in range(3)])]
    assert "NO VERDICT: need >=" in run(tiny)
    monkeypatch.setattr(LR, "MIN_JUDGEABLE_PER_ARM", 0)
    assert "NO VERDICT: need >=" not in run(tiny).split("FACTOR D")[1].split("FACTOR C")[0]


def test_the_ten_passer_refusal_fires_below_the_floor_and_lifts_above_it():
    def corpus(n_pass):
        rows = []
        for i in range(60):
            passing = i < n_pass
            rows.append(mk({"D": i % 2},
                           sharpe=2.0 if passing else 0.1,
                           fitness=1.5 if passing else 0.1,
                           turnover=0.3, returns=0.06))
        return [("r1", rows)]
    below = run(corpus(LR.MIN_SCREEN_PASSERS - 1)).split("FACTOR D")[1].split("FACTOR C")[0]
    above = run(corpus(LR.MIN_SCREEN_PASSERS + 1)).split("FACTOR D")[1].split("FACTOR C")[0]
    assert "TOO FEW to compare rates (need %d)" % LR.MIN_SCREEN_PASSERS in below
    assert "screen rate ON" in above and "TOO FEW to compare rates" not in above


def test_the_ten_passer_threshold_is_live(monkeypatch):
    rows = []
    for i in range(60):
        rows.append(mk({"D": i % 2}, sharpe=2.0 if i < 2 else 0.1,
                       fitness=1.5 if i < 2 else 0.1, turnover=0.3, returns=0.06))
    assert "TOO FEW to compare rates" in run([("r1", rows)])
    monkeypatch.setattr(LR, "MIN_SCREEN_PASSERS", 0)
    assert "TOO FEW to compare rates" not in run([("r1", rows)]).split("FACTOR D")[1]


def test_the_rank_test_is_labelled_dominance_wherever_a_p_value_is_printed():
    """`wilcoxon-is-not-a-mean-test`: on skewed payoffs every random control passes a rank test read
    as a mean test. The label must sit on the OUTPUT, not in a docstring."""
    txt = run(sixteen_cells())
    assert "p_raw" in txt
    assert "DOMINANCE, not means" in txt
    for bad in ("difference in means", "mean sharpe improved", "the means differ"):
        assert bad not in txt


# ------------------------------------------------------------------ the C x turnover confound

def c_cuts_turnover_only(n=60, seed=5):
    """C halves turnover and touches NOTHING else. Fitness is computed from the identity, so the
    raw C-on-fitness contrast is positive with zero signal change -- the confound, constructed."""
    rng = random.Random(seed)
    rows = []
    for c in (0, 1):
        for _ in range(n):
            sh = rng.gauss(0.5, 0.3)
            ret = abs(rng.gauss(0.03, 0.005))
            to = (0.5 if c == 0 else 0.25) * (1 + rng.gauss(0, 0.05))
            fit = sh * math.sqrt(ret / max(to, 0.125))
            rows.append(mk({"C": c}, sharpe=sh, fitness=fit, turnover=to, returns=ret))
    return [("r1", rows)]


def test_the_c_fitness_contrast_is_reported_within_turnover_bands_and_the_raw_one_is_marked():
    txt = run(c_cuts_turnover_only())
    sec = txt.split("C x TURNOVER")[1]
    assert "C on FITNESS, RAW POOLED" in sec
    assert "RAW, NOT A VERDICT" in sec
    assert "pooled WITHIN turnover band" in sec
    assert "fetched/community_alpha_tips.md" in sec, "the documented confound must be cited, EX-ANTE"
    raw = float(sec.split("C on FITNESS, RAW POOLED: HL ")[1].split()[0])
    assert raw > 0.05, "the constructed confound should raise raw fitness"
    # every band line either reports a contrast or refuses; none is silently skipped
    bands = [l for l in sec.splitlines() if l.strip().startswith("band ")]
    assert len(bands) == len(LR.TURNOVER_BANDS)


def test_c_on_fitness_has_no_verdict_when_no_turnover_band_holds_enough_rows():
    """The pre-registered consequence: pooled within the confound, or no verdict at all."""
    txt = run(c_cuts_turnover_only(n=25))
    sec = txt.split("C x TURNOVER")[1]
    assert "C ON FITNESS: NO VERDICT" in sec
    assert "MECHANISM IS UNKNOWN" in sec


def test_within_band_the_constructed_turnover_only_effect_disappears():
    """C=on and C=off rows that share a turnover band differ only by noise, so the within-band
    contrast must be far smaller than the raw one. This is what makes the pooling load-bearing."""
    rows = []
    ret = 0.03
    for c in (0, 1):
        n_low = 160 if c else 40            # C moves 80% vs 20% of its rows into the low band
        for to, n in ((0.05, n_low), (0.40, 200 - n_low)):
            for k in range(n):
                sh = 0.2 + 0.6 * k / (n - 1)   # the SAME sharpe grid in both arms of both bands
                rows.append(mk({"C": c}, sharpe=sh, turnover=to, returns=ret,
                               fitness=sh * math.sqrt(ret / max(to, 0.125))))
    sec = run([("r1", rows)]).split("C x TURNOVER")[1]
    raw = abs(float(sec.split("C on FITNESS, RAW POOLED: HL ")[1].split()[0]))
    band_hl = [abs(float(l.split(" HL ")[1].split()[0]))
               for l in sec.splitlines() if l.strip().startswith("band ") and " HL " in l]
    assert band_hl, sec
    assert max(band_hl) < raw / 2, (raw, band_hl)


# ------------------------------------------------------------------ the other deliverables

def test_all_four_metrics_including_abs_returns_are_reported_per_factor():
    txt = run(sixteen_cells())
    d = txt.split("FACTOR D")[1].split("FACTOR C")[0]
    for m in LR.METRICS:
        assert any(l.strip().startswith(m) for l in d.splitlines()), m
    assert "med|returns|" in d and "floor" in d


def test_a_factor_that_moves_sharpe_without_moving_returns_is_shown_to_be_unable_to_open_fitness():
    rows = [mk({"D": 1}, sharpe=2.0, returns=0.02) for _ in range(30)] + \
           [mk({"D": 0}, sharpe=0.1, returns=0.02) for _ in range(30)]
    d = run([("r1", rows)]).split("FACTOR D")[1].split("FACTOR C")[0]
    assert "NEITHER ARM CLEARS" in d
    assert "cannot open the fitness gate" in d
    ok = [mk({"D": 1}, sharpe=2.0, returns=0.08) for _ in range(30)] + \
         [mk({"D": 0}, sharpe=0.1, returns=0.08) for _ in range(30)]
    assert "BOTH CLEAR" in run([("r1", ok)]).split("FACTOR D")[1].split("FACTOR C")[0]


def test_multiplicity_is_stated_and_both_families_are_printed():
    txt = run(sixteen_cells())
    assert "4 factors x 4 metrics = 16 tests" in txt
    assert "Holm-Bonferroni over the family of 16 is applied" in txt
    assert "p_h16" in txt and "p_h4" in txt


def parse_pvals(txt):
    """(factor, metric) -> (p_raw, p_h16, p_h4) off the printed table."""
    out, factor = {}, None
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("FACTOR "):
            factor = s.split()[1]
        elif factor and s.split(" ")[0] in LR.METRICS and "[" in s:
            parts = s.split()
            out[(factor, parts[0])] = tuple(float(x) for x in parts[-3:])
    return out


def test_the_holm_correction_is_actually_applied_to_the_printed_column():
    """Printing a column headed p_h16 that holds the raw p is the failure this catches: the earlier
    mutation battery found that deleting the Holm call left every other test green."""
    rng = random.Random(21)
    rows = []
    for i in range(16):
        cell = {"D": (i >> 3) & 1, "C": (i >> 2) & 1, "U": (i >> 1) & 1, "S": i & 1}
        for _ in range(30):
            rows.append(mk(cell,
                           sharpe=rng.gauss(0, 1) + 0.55 * cell["D"] + 0.30 * cell["C"],
                           fitness=rng.gauss(0.3, 0.2) + 0.10 * cell["U"],
                           turnover=abs(rng.gauss(0.3, 0.1)) + 0.01 + 0.02 * cell["S"],
                           returns=rng.gauss(0.02, 0.01) + 0.002 * cell["C"]))
    got = parse_pvals(run([("r1", rows)]))
    assert len(got) == 16, got
    raw = [v[0] for v in got.values()]
    want16 = dict(zip(got, LR.holm(raw)))
    for key, (p, h16, h4) in got.items():
        # tolerance: the printed p is rounded to 4dp, so re-deriving Holm from the PRINTED raw
        # p carries up to (family size) x 5e-5 of rounding error.
        assert h16 == pytest.approx(want16[key], abs=1e-3), key
        fam = {k: v[0] for k, v in got.items() if k[1] == key[1]}
        want4 = dict(zip(fam, LR.holm(list(fam.values()))))
        assert h4 == pytest.approx(want4[key], abs=3e-4), key
        assert h16 >= h4 - 3e-4 >= p - 6e-4, key
    moved = sum(1 for p, h16, _ in got.values() if h16 - p > 1e-3)
    assert moved >= 3, "this corpus does not discriminate an applied correction from an absent one"


def test_the_round_over_round_median_still_prints_and_carries_no_verdict_authority():
    a = [mk({"D": i % 2}, sharpe=0.1) for i in range(40)]
    b = [mk({"D": i % 2}, sharpe=0.9) for i in range(40)]
    txt = run([("r1", a), ("r2", b)])
    mon = txt.split("ROUND-OVER-ROUND MEDIAN")[1]
    assert "MONITOR ONLY, NO VERDICT AUTHORITY" in txt.split("ROUND-OVER-ROUND")[1][:80]
    assert "47.8%" in mon and "delta +0.8000" in mon
    assert "r1" in mon and "r2" in mon


def test_an_unassigned_factor_is_reported_as_unassigned_and_never_as_a_null():
    txt = run([("r1", [mk({"D": i % 2}) for i in range(60)])])
    for f in ("C", "U", "S"):
        blk = txt.split("FACTOR %s" % f)[1].split("FACTOR")[0]
        assert "NOT ASSIGNED in this corpus" in blk
        assert "an unassigned factor is not a null result" in blk.lower()


def test_one_journal_holding_two_rounds_splits_into_two_blocks(tmp_path, monkeypatch, capsys):
    """`meta['round']` is what makes within-round blocking possible when a loop writes one file."""
    import json
    p = tmp_path / "j.jsonl"
    rows = []
    for rd in ("r1", "r2"):
        for i in range(30):
            r = mk({"D": i % 2})
            r["meta"]["round"] = rd
            rows.append(r)
    p.write_text("\n".join(json.dumps(r) for r in rows))
    monkeypatch.setattr(sys, "argv", ["layered_report.py", str(p)])
    LR.main()
    txt = capsys.readouterr().out
    assert "blocks 2: r1(30), r2(30)" in txt
    assert "identifying blocks (both levels present): r1, r2" in txt


def test_the_real_baseline_journal_still_reads_end_to_end():
    p = ROOT / "state" / "layered" / "runs" / "loop_1786608562.jsonl"
    if not p.exists():
        pytest.skip("baseline journal absent")
    rows = LR.load(p)
    txt = run([(p.stem, rows)])
    assert "terminal 86" in txt
    # the baseline's {ordered,free} labels are the S factor, and it is identified within the batch
    s = txt.split("FACTOR S")[1]
    assert "rows ON=42 OFF=44" in s
    assert "IDENTIFIED ONLY BETWEEN BLOCKS" not in s
