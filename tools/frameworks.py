"""Alpha FRAMEWORKS -- many declared skeletons, each carrying a prediction that can be wrong.

WHY THIS EXISTS. `BACKBONE.md` was one fixed skeleton assembled from ten agents' insight cards, and
adversarial round 2 killed five of its eight rules. Four of those five were this project's own
generator configuration, measured back out of the corpus that generator wrote (see
`BACKBONE_V2.md`, "Why v1 failed"). A single blessed skeleton is exactly the shape that failure
takes: it cannot be compared against anything, so nothing can refute it.

So: frameworks are DATA, several of them run at once, and each one states in advance what would
show it does not work. A framework whose prediction fails is reported failed and retired. The
`flat` framework is the unconstrained composer and is the null arm -- without it, no framework can
be shown to do anything at all.

WHAT A FRAMEWORK IS NOT. It is not a claim that its structure is necessary. Two disjoint alpha
families are live on this account (`BACKBONE_V2` O5), so no skeleton is necessary and any framework
saying "you must do X" is already refuted by whichever live family lacks X.

ASSIGNMENT IS WITHIN-BATCH AND BALANCED. A before/after across two runs is confounded by time of
day, market regime and quota state. `assign()` deals frameworks out of a permuted block so every
framework gets the same share of one batch and the confounds hit all arms equally.
"""

import collections
import itertools
import random

import layered_alpha as LA


#: One declared framework.
#:
#: legs / depth   inclusive (min, max) draw ranges
#: outer          operator names applied OUTERMOST-FIRST around the blend, or () for a bare blend,
#:                or FREE to draw from pool A as the unconstrained composer does
#: leg_wrap       normaliser wrapped around every leg: a name, or FREE to draw per leg, or None
#: negate         "carrier" (the carrier leg carries the minus), "none", or FREE
#: neutralization settings value, or FREE
#: carrier        True (a close/open leg is forced), False (forbidden), or FREE
#: claims         the BACKBONE_V2 claim ids this framework is built to exercise
#: predicts       PRE-REGISTERED. What must be observed, or the framework is refuted. Written
#:                before any simulation; never edited after seeing a result.
#: decay        terminal `decay` setting, or FREE to let the settings arm own it
Framework = collections.namedtuple(
    "Framework",
    "name legs depth outer leg_wrap negate neutralization decay carrier claims predicts")

FREE = "free"

#: The carrier leaf. NOT privileged -- it has ZERO variance in the historical corpus (present in
#: 430/430 gems AND 11,301/11,301 non-gems), so it cannot discriminate anything and is here only
#: because S6 is about the sign on THIS leg specifically.
CARRIER_LEAF = "close / open"

#: Wrapped around a leg to put every leg on one scale. `rank` is the corpus default; that default is
#: this project's own generator config (`generate.py:114-116`) and is NOT evidence -- see D2, where
#: mixing classes measured +0.082 sharpe, the opposite of the retired rule.
NORMALISERS = ("rank", "zscore", "ts_rank", "group_rank")

#: DECAY IS THE ONLY NUMERIC PARAMETER MEASURED AS STEERABLE (`R3_E1_parameter_variance.md`).
#: Smaller wins, replicated four ways (0.795 over 249 shells / 0.829 / 0.833 over 30 independent
#: sweep units / 0.944 on an independent source), argmax = smallest offered in 89.2% against 29.0%
#: by chance, 114 of 130 curves monotone decreasing, +0.405 sharpe across a full 5->60 sweep.
#:
#: Every other numeric is not a lever: LOOKBACK is the cleanest null in the corpus (shorter wins
#: 48/98 shells, p 0.755; argmax = smallest 34.6% against 31.1% by chance; direction INVERTS by
#: operator), EXPONENT is significant and useless (p 1.4e-05, effect 0.040 sharpe against a 1.58
#: bar), LEG WEIGHTS are NO VERDICT at 10 shells.
#:
#: BUT THE TERMINAL DECAY SETTING IS LEFT FREE, AND THAT IS A CORRECTION TO MY OWN FIRST DESIGN.
#: I originally pinned every framework at decay 3. That silently DISABLED `layered_sim`'s settings
#: arm, which is the only running test of the largest unexplained gap in the project -- this
#: generator screened 0/129 while the resim corpus screens 6.70%, and the leading suspect is exactly
#: the settings resim used (decay 6-14 with INDUSTRY/STATISTICAL). Pinning decay turned off the
#: experiment that was testing the leading suspect. E1's decay evidence is mostly about IN-FORMULA
#: decay anyway; the terminal setting was the weaker half of it (802 formulas, +0.100, 0.734).
#: So only `margin` declares a decay, because its whole prediction is about one.
#:
#: AND THE CATCH, which is why `margin` declares one at all: small decay buys ZERO fitness.
#: The `fitness >= 1.0` pass rate is 0.451 against 0.453. Margin falls 10.82 -> 9.07 bps (84.4% of
#: shells, p 2.9e-23) exactly as much as sharpe rises, and the S2 identity closes to median error
#: 0.0029. Decay SLIDES ALONG the iso-fitness curve `sharpe * sqrt(margin) = const`. It moves
#: LOW_SHARPE and moves nothing else. MECHANISM: UNKNOWN for why decay does that to margin.
DECAY_SMALL, DECAY_LARGE = 3, 30


FRAMEWORKS = (
    # ---------------------------------------------------------------- the null arm
    Framework(
        name="flat",
        legs=(1, 9), depth=(1, 6), outer=FREE, leg_wrap=FREE, negate=FREE,
        neutralization=FREE, decay=FREE, carrier=FREE,
        claims=(),
        predicts="NOTHING. This is the unconstrained composer and exists so the others have "
                 "something to beat. If no framework beats flat, the honest report is that "
                 "structure does not matter at this sample size."),

    # ---------------------------------------------------------------- S1: the one claim that made
    # a risky prediction and survived it. Terminal group neutralization caps CONCENTRATED_WEIGHT at
    # 0.5 deductively (a neutralized group holding one name is zeroed, so the book floor is two).
    Framework(
        name="s1_neut",
        legs=(4, 9), depth=(1, 5), outer=FREE, leg_wrap=FREE, negate=FREE,
        neutralization="INDUSTRY", decay=FREE, carrier=FREE,
        claims=("S1",),
        predicts="ZERO alphas with CONCENTRATED_WEIGHT above 0.5. A single alpha above 0.5001 "
                 "refutes the deductive argument outright. "
                 "THE SECOND HALF OF THIS PREDICTION WAS WITHDRAWN 2026-08-14, BEFORE ANY BATCH, "
                 "and it was withdrawn because I had the gate wrong. It used to read 'and a "
                 "CONCENTRATED_WEIGHT fail rate strictly below flat's'. **The gate's limit is "
                 "0.1**, re-derived on two corpora (441/441 populated limits in alphas_all; "
                 "1,938/1,938 in resim, lowest FAILing value exactly 0.100000). S1 caps at 0.5, "
                 "i.e. FIVE TIMES the bar, so satisfying S1 clears nothing. 13 alphas already run "
                 "a group neutralization, sit at exactly 0.500000 as S1 predicts, and fail anyway. "
                 "At the real bar the kinds are indistinguishable: GROUP 22/5,809 = 0.38% vs "
                 "RISK 15/5,922 = 0.25%. S1 stays as a MECHANISM TEST only. What clears this gate: "
                 "MECHANISM UNKNOWN -- book size does not separate the failures either. "
                 "S7 was DROPPED from this arm's claims "
                 "on 2026-08-14 before any batch: R3_OOS refuted it -- rho(n_legs, CW_FAIL) is "
                 "+0.016 on alphas_all, +0.501 on layered, and runs +0.148 to -0.421 by decile "
                 "INSIDE its own file."),

    # ---------------------------------------------------------------- S1's SECOND risky prediction,
    # and the reason S1 is the only claim in this project that has earned trust. The two-name-floor
    # argument says a GROUP neutralization caps at 0.5 because a group holding one name is zeroed --
    # it says nothing about neutralizing against a RISK FACTOR, which does not partition the book
    # into groups at all. So risk-factor neutralization must NOT cap. It does not: 8 of 390 rows
    # above 0.5001, max 1.0, against 0 of 1,266 for the group kind across USA/EUR/ASI.
    #
    # This arm is the negative control. A control that fails is worth more than an arm that passes.
    Framework(
        name="s1_risk",
        legs=(4, 9), depth=(1, 5), outer=FREE, leg_wrap=FREE, negate=FREE,
        neutralization="STATISTICAL", decay=FREE, carrier=FREE,
        claims=("S1",),
        predicts="CONCENTRATED_WEIGHT ABOVE 0.5 on at least one alpha. This is a NEGATIVE control: "
                 "if a risk-factor neutralization also caps at 0.5, the two-name-floor mechanism is "
                 "wrong and S1 is a coincidence of the group setting rather than a consequence of "
                 "it. S1 is the only claim here that has ever made a risky prediction and survived; "
                 "this is the test that can still take it down."),

    # ---------------------------------------------------------------- S6, and the experiment the
    # corpus could not run. 87.8% of all negated legs in the corpus are the same leg. Splitting the
    # exposure gave MH OR 67.8 for carrier-leg negation against a null for every other leg -- but
    # the direct test needs a 0-negation arm, and exactly 6 matched sign-flip groups exist in 50,482
    # multi-leg rows, NONE with such an arm. These two frameworks ARE that arm.
    Framework(
        name="s6_neg",
        legs=(3, 7), depth=(1, 5), outer=FREE, leg_wrap=FREE, negate="carrier",
        neutralization=FREE, decay=FREE, carrier=True,
        claims=("S6",),
        predicts="Higher zero-fail rate than s6_pos in the same batch. If the two are "
                 "indistinguishable, the OR 67.8 was a marker for a formula family and not the "
                 "minus sign, and S6 must be rewritten. R3_OOS since found this pair is not merely "
                 "useful but MANDATORY: `rank(close/open)` occurs 39,384 times as a top-level leg "
                 "across both corpora and is negated 39,384/39,384, because "
                 "`tools/autoloop/generate.py:121` hardcodes the minus. The corpus has ZERO "
                 "un-negated observations, so S6 has zero power there and is NO VERDICT until "
                 "these two arms run."),
    Framework(
        name="s6_pos",
        legs=(3, 7), depth=(1, 5), outer=FREE, leg_wrap=FREE, negate="none",
        neutralization=FREE, decay=FREE, carrier=True,
        claims=("S6",),
        predicts="Its own failure. This is s6_neg's paired control and is expected to do worse; "
                 "if it does not, S6 falls."),

    # ---------------------------------------------------------------- the two live families. These
    # are NOT here because they are good -- they are here because they are the only structures known
    # to have passed a real submission, so they calibrate everything else.
    Framework(
        name="era_a",
        legs=(2, 6), depth=(1, 4), outer=("ts_decay_linear", "group_neutralize", "normalize"),
        leg_wrap=FREE, negate=FREE, neutralization=FREE, decay=FREE, carrier=FREE,
        claims=("O5",),
        predicts="Nothing structural. Calibration arm: 197 live alphas share its 2-level prefix, so "
                 "if it scores at flat's level the corpus's live population is not reachable from "
                 "this composer and the whole comparison is mis-scaled."),
    Framework(
        name="era_b",
        legs=(2, 6), depth=(1, 4), outer=("signed_power", "zscore", "ts_decay_linear"),
        leg_wrap=FREE, negate=FREE, neutralization=FREE, decay=FREE, carrier=True,
        claims=("O5",),
        predicts="Same calibration role as era_a. 19 of 30 accept-era alphas carry its prefix."),

    # ---------------------------------------------------------------- S2 is an IDENTITY, so it
    # cannot be refuted by a batch. What CAN be wrong is the belief that a framework can aim at
    # margin at all. Above turnover 0.125 turnover cancels out of fitness exactly, so the only
    # levers are sharpe and margin -- and no run has ever tried to steer margin.
    Framework(
        name="margin",
        legs=(2, 6), depth=(1, 3), outer=FREE, leg_wrap=FREE, negate=FREE,
        neutralization=FREE, decay=DECAY_LARGE, carrier=FREE,
        claims=("S2",),
        predicts="REVISED 2026-08-14 BEFORE ANY FRAMEWORK BATCH, on evidence from a DIFFERENT "
                 "experiment (R3_E1). It now tests E1's own decomposition. E1 found decay slides "
                 "along the iso-fitness curve sharpe*sqrt(margin)=const: margin fell 10.82->9.07 "
                 "bps as sharpe rose, and the fitness>=1.0 pass rate was 0.451 vs 0.453. So this "
                 "arm declares decay 30 against everyone else's 3 and predicts: median margin "
                 "ABOVE flat's, median sharpe BELOW flat's, and median fitness INDISTINGUISHABLE "
                 "from flat's. If fitness RISES, the curve is not iso and E1's decomposition is "
                 "wrong. If margin does not move at all, decay is not the margin lever either and "
                 "nothing found so far moves margin."),

    # ---------------------------------------------------------------- the binding constraint. S3
    # is a RATIO gate: limit = k * the alpha's own sharpe, so raising sharpe raises the bar by the
    # same factor and it cannot be bought with signal strength. Clearing it needs sub-universe
    # sharpe to rise FASTER than full-universe sharpe.
    #
    # SPECULATION, labelled as such: that restricting leaves to high-coverage fields and neutralizing
    # on a liquidity-correlated group concentrates edge in the liquid sub-universe. NO experiment
    # supports this. It is a guess, and it is here because the alternative is not measuring at all.
    # The VALUE of this arm does not depend on the guess being right: no run in this repository has
    # ever recorded sub-universe sharpe against full-universe sharpe as an outcome, so the ratio
    # itself is the deliverable.
    Framework(
        name="subu",
        legs=(3, 7), depth=(1, 4), outer=FREE, leg_wrap=FREE, negate=FREE,
        neutralization="SUBINDUSTRY", decay=FREE, carrier=FREE,
        claims=("S3",),
        predicts="A HIGHER ratio of sub-universe sharpe to full-universe sharpe than flat's. The "
                 "mechanism is SPECULATION; the ratio is measured either way, and reporting it is "
                 "the point. If the ratio is flat across every framework, then no structure in this "
                 "grammar moves it and the gate needs a different attack entirely."),
)

BY_NAME = {f.name: f for f in FRAMEWORKS}


def assign(rng, n, frameworks=FRAMEWORKS):
    """`n` framework names, dealt from permuted blocks so each gets an equal share of ONE batch.

    Balanced within-batch assignment is the whole design: a before/after across two runs is
    confounded by time of day, market regime and quota state, and randomising within removes all
    three by construction (HARNESS_SOP, "Verification is randomised WITHIN a batch").
    """
    out, names = [], [f.name for f in frameworks]
    while len(out) < n:
        block = list(names)
        rng.shuffle(block)
        out.extend(block)
    return out[:n]


def _leg(fw, pool_b, leaves, rng, leaf=None):
    """One leg: a leaf, a chain of `depth` layer-B operators, then the leg's normaliser."""
    expr = leaf if leaf is not None else rng.choice(leaves)["expr"]
    for _ in range(rng.randint(*fw.depth)):
        expr = LA._apply(rng.choice(pool_b), expr, rng)
    wrap = fw.leg_wrap
    if wrap is FREE:
        wrap = rng.choice(NORMALISERS)
    if wrap:
        expr = LA._apply({"name": wrap, "required": _required(wrap, pool_b)}, expr, rng)
    return expr


def _required(name, pool):
    for o in pool:
        if o["name"] == name:
            return o["required"]
    return []


def build(fw, pool_a, pool_b, pool_c, rng):
    """One alpha for one framework. Returns (formula, meta).

    `meta` records the framework AND every draw, so a journalled row can be assigned to its arm
    without re-deriving anything from the formula text -- the council found `meta.carrier`
    disagreeing with the formula on 3,822 rows, and a finding flipped sign between the two
    definitions. Both are recorded here for that reason.
    """
    n_legs = rng.randint(*fw.legs)
    carrier_idx = None
    if fw.carrier is True:
        carrier_idx = rng.randrange(n_legs)
    elif fw.carrier is FREE and rng.random() < 0.5:
        carrier_idx = rng.randrange(n_legs)

    legs, signs = [], []
    for i in range(n_legs):
        is_carrier = i == carrier_idx
        leaf = CARRIER_LEAF if is_carrier else None
        expr = _leg(fw, pool_b, pool_c, rng, leaf=leaf)
        if fw.negate == "carrier":
            neg = is_carrier
        elif fw.negate == "none":
            neg = False
        else:
            neg = rng.random() < 0.5
        legs.append(expr)
        signs.append(neg)

    # Arithmetic is INFIX by operator decision -- `add`/`subtract`/`multiply`/`divide` are never
    # called. Weights are drawn freely: the "non-monotone weights" rule was retired (MH OR 0.983),
    # and the 0.9-at-leg-3 signature it rested on is a hardcoded template constant that is ANTI-
    # associated with success (OR 0.605, p 3.6e-07).
    weights = [round(rng.uniform(0.2, 1.0), 2) for _ in legs]
    blend = ""
    for i, (expr, neg, w) in enumerate(zip(legs, signs, weights)):
        term = "%s * %s" % (w, expr)
        if i == 0:
            blend = ("-" + term) if neg else term
        else:
            blend += (" - " if neg else " + ") + term
    formula = "(%s)" % blend

    outer = fw.outer
    if outer is FREE:
        outer = tuple(o["name"] for o in rng.sample(pool_a, rng.randint(0, 2)))
    for name in reversed(outer):          # declared outermost-first, applied innermost-last
        formula = LA._apply({"name": name, "required": _required(name, pool_a + pool_b)},
                            formula, rng)

    meta = {
        "framework": fw.name,
        "claims": list(fw.claims),
        "n_legs": n_legs,
        "weights": weights,
        "signs": signs,
        "carrier_idx": carrier_idx,
        "carrier_declared": carrier_idx is not None,
        "carrier_in_formula": LA.carrier_present(formula),
        "outer": list(outer),
        "leg_wrap": fw.leg_wrap,
        "neutralization": fw.neutralization,
    }
    return formula, meta


def settings_for(fw, base):
    """`base` with the framework's declared settings applied. FREE leaves the base value alone."""
    s = dict(base)
    if fw.neutralization is not FREE:
        s["neutralization"] = fw.neutralization
    if fw.decay is not FREE:
        s["decay"] = fw.decay
    return s


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--framework", help="only this one")
    ap.add_argument("--predictions", action="store_true", help="print the pre-registered "
                    "predictions and exit -- run this BEFORE a batch, not after")
    a = ap.parse_args()

    if a.predictions:
        for f in FRAMEWORKS:
            print("%-10s claims=%-12s %s" % (f.name, ",".join(f.claims) or "-", f.predicts))
        return

    ops = LA.load_operators()
    pool_a, pool_b, _dropped = LA.split_layers(ops)
    pool_c = LA.build_pool_c(LA.load_fields(), rng=random.Random(a.seed))
    rng = random.Random(a.seed)
    picks = ([a.framework] * a.n) if a.framework else assign(rng, a.n)
    for name in picks:
        formula, meta = build(BY_NAME[name], pool_a, pool_b, pool_c, rng)
        print(json.dumps({"formula": formula, "meta": meta}))


if __name__ == "__main__":
    main()
