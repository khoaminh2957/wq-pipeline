"""Suite for forge/standard.py -- the mechanical half of the ratified hypothesis standard's 8 hard gates.

Why this file exists (draw-3 scoring task): forge/standard.py was the one forge module with no test, so
axis 3's fitness function "every forge module has a test" could only hold at draw 2's 0.8 threshold
(21 of 22). With this file it holds at 1.0, which is what its name says.

What these pin is standard.py's PUBLIC behaviour -- hard_gates() and admissible() -- one gate at a time:
a composite that clears every gate, then that same composite with exactly ONE field broken, which must
trip exactly that gate and nothing else. The gate numbers and reasons are the ones standard.py returns
(fetched/hypothesis_standard.md numbering); nothing here decides what the gates SHOULD be.
"""
import dataclasses
import pathlib

import pytest

from forge import hypotheses as H
from forge import standard as ST

#: 25+ words, names no agent verbatim from the id, carries no paraphrase of the id: gate 1 holds
MECHANISM = ("Firms whose accruals run far ahead of cash earnings report profits that later reverse, because "
             "managers pull revenue forward and investors anchor on the headline number instead of the cash "
             "flow statement, so the price corrects once the accruals unwind over the next several quarters.")


def _clean(**changes) -> H.Composite:
    """A composite that clears every mechanical gate, with `changes` applied."""
    base = H.Composite(
        id="accruals_x_capex", legs=["leg_a", "leg_b"], families=["accruals", "investment"],
        mechanism=MECHANISM, counterparty="retail investors who anchor on reported earnings",
        source="EX-ANTE -- Sloan 1996; Titman, Wei & Xie 2004", regimes={k: "+" for k in H.REGIME_KEYS},
        strongest_in="small caps", weakens_when="rate shocks", settings={"neutralization": ["INDUSTRY"], "decay": [4]},
        combiners=["multiply"], notes="")
    return dataclasses.replace(base, **changes)


def _gates(obj) -> list:
    return sorted({g for g, _ in ST.hard_gates(obj)})


def test_a_composite_that_clears_every_gate_is_admissible():
    c = _clean()
    assert ST.hard_gates(c) == [] and ST.admissible(c) is True


@pytest.mark.parametrize("change, gate", [
    ({"mechanism": "accruals reverse because managers pull revenue forward"}, 1),        # under 25 words
    ({"mechanism": MECHANISM + " In short: accruals x capex."}, 1),                       # paraphrases its own id
    ({"counterparty": "the market as a whole"}, 2),                                        # no agent class named
    ({"source": "Sloan 1996; Titman, Wei & Xie 2004"}, 3),                                 # no RULE-0 label
    ({"source": "EX-ANTE -- Sloan, Titman, Wei & Xie"}, 3),                                # no dated citation
    ({"regimes": {k: "+" for k in H.REGIME_KEYS[:-1]}}, 4),                                # a regime missing
    ({"notes": "flip the sign in 2022"}, 5),                                               # a planned sign flip
    ({"legs": ["leg_a"], "families": ["accruals"]}, 6),                                    # one leg
    ({"families": ["accruals", "accruals"]}, 6),                                           # two legs, one family
    ({"combiners": ["add"]}, 6),                                                           # not a conditioning combiner
])
def test_each_broken_field_trips_exactly_its_own_gate(change, gate):
    c = _clean(**change)
    assert _gates(c) == [gate], ST.hard_gates(c)
    assert ST.admissible(c) is False
    assert all(isinstance(reason, str) and reason for _, reason in ST.hard_gates(c))


def test_a_note_that_says_no_flip_is_not_a_planned_flip():
    """Gate 5 fires on "flip" only when the note does not say "no flip"."""
    assert ST.hard_gates(_clean(notes="checked: no flip across regimes")) == []
    assert _gates(_clean(notes="FLIP in the covid regime")) == [5]            # case does not hide it


def test_every_broken_field_is_reported_not_just_the_first():
    """hard_gates lists every tripped gate, so a composite broken three ways reads three gates."""
    c = _clean(counterparty="nobody in particular", regimes={}, combiners=["add"])
    assert _gates(c) == [2, 4, 6]


def test_a_single_field_hypothesis_is_a_leg_never_an_alpha():
    """A Hypothesis trips gate 6 by construction, whatever its content, and names itself in the reason."""
    h = H.Hypothesis(id="lonely_leg", category="Fundamental", mechanism=MECHANISM, sign=1, source="EX-ANTE 2020",
                     datasets=["d"], signal={"fields": ["f"]}, template="rank({signal})", params={},
                     settings={"neutralization": ["INDUSTRY"], "decay": [4]})
    trips = ST.hard_gates(h)
    assert [g for g, _ in trips] == [6] and "lonely_leg" in trips[0][1]
    assert ST.admissible(h) is False


def test_the_real_library_reads_as_the_gates_say():
    """On the live library: every leg is a single-field Hypothesis and so trips gate 6 exactly; every
    composite yields well-formed (gate, reason) pairs, and admissible() agrees with hard_gates()."""
    forge_dir = pathlib.Path(__file__).resolve().parents[1]
    lib = H.load_library(forge_dir / "hypotheses")
    comps = H.load_composites(forge_dir / "composites", lib)
    assert lib and comps
    assert all(_gates(h) == [6] for h in lib)
    for c in comps:
        trips = ST.hard_gates(c)
        assert all(isinstance(g, int) and 1 <= g <= 8 and isinstance(r, str) for g, r in trips), c.id
        assert ST.admissible(c) is (trips == [])


def test_gate_one_sits_at_exactly_twenty_five_words():
    """Gate 1's length rule on each side of its line: 24 words trip it, 25 do not."""
    words = MECHANISM.split()
    assert len(words) >= 25
    assert _gates(_clean(mechanism=" ".join(words[:24]))) == [1]
    assert ST.hard_gates(_clean(mechanism=" ".join(words[:25]))) == []


# ------------------------------------------------------------ draw3_fix scoring 4: the five surviving mutants
# docs/evalharness/audits/draw3_fix.md (scoring, defect 4): five independent mutants of forge/standard.py
# survived this file, so "12 of 12 killed" did not generalise. One case each; the comment names the mutant.

def test_a_regime_map_with_an_extra_key_is_not_the_standard_map():
    """Mutant: the regime check accepts a SUPERSET of REGIME_KEYS. The gate asks for exactly the per-sub-regime
    sign map, so a map with an extra key trips gate 4."""
    regimes = dict({k: "+" for k in H.REGIME_KEYS}, extra_regime_2030="+")
    assert _gates(_clean(regimes=regimes)) == [4]


def test_a_non_conditioning_combiner_beside_a_conditioning_one_still_trips():
    """Mutant: the combiner check accepts an INTERSECTION with COMBINERS. Every combiner must condition, so
    ["multiply", "add"] trips gate 6."""
    assert "add" not in H.COMBINERS and "multiply" in H.COMBINERS
    assert _gates(_clean(combiners=["multiply", "add"])) == [6]


def test_the_counterparty_match_ignores_case():
    """Mutant: counterparty matching drops .lower(). AGENT_WORDS are lower case, so a capitalised agent class
    must still be found, and capitals must not turn a text naming no agent class into one that passes."""
    assert all(w == w.lower() for w in H.AGENT_WORDS)
    assert ST.hard_gates(_clean(counterparty="Retail Investors Who Anchor On Reported Earnings")) == []
    assert _gates(_clean(counterparty="Nobody In Particular")) == [2]


def test_the_label_must_open_the_source():
    """Mutant: the label check matches a SUBSTRING instead of a prefix. A RULE-0 label buried after the
    citation trips gate 3."""
    assert _gates(_clean(source="Sloan 1996 (EX-ANTE)")) == [3]
    assert ST.hard_gates(_clean(source="EX-ANTE -- Sloan 1996")) == []


def test_one_leg_trips_gate_six_even_with_two_families():
    """Mutant: one leg allowed (len(legs) < 1). The existing one-leg case also had one family, so the family
    clause alone caught it; here the families are two and only the leg count can trip."""
    assert _gates(_clean(legs=["leg_a"], families=["accruals", "investment"])) == [6]
