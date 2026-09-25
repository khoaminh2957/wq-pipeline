"""forge.meaning -- the rule half of D19 for an alpha that already passed (D17, D39, D52).

WHAT THIS IS. D17 (Khoa, 2026-09-22) moved the eight hard gates of `fetched/hypothesis_standard.md` from
before a simulation to after a pass. D39 (2026-09-23 ~17:20) amended D19 for generated alphas: G1-G3
need written prose a generated formula does not have, so they are recorded "not applicable to a
generated alpha"; a generated alpha that passes EVERY decidable gate -- G4's leg clause and G5-G8 -- is
submitted automatically, and one that fails any decidable gate is not. A generated alpha that is a
near-dup of an authored composite inherits that composite's G1-G3. D52 (2026-09-23 ~21:00) fixed G4's
decidable clause after round 3 S12 showed it had no direction and no unit. This module scores those
gates and writes one row per (alpha, formula sha) to state/forge/meaning.jsonl, the ledger
forge/offline/benchmark.py's `load_meaning` / `meaning_index` read. It decides nothing about POSTing:
the submit router (design 04 section 7, stage 3) reads the row; `decidable_verdict` states D39's rule so
the router and the judge cannot read it two ways.

THE ROW (the shared interface of 2026-09-23): {"alpha", "formula_sha" (sha256 of the formula text, no
normalisation), "gates": {"G1".."G8": true | false | null}, "inherited_from": composite id | null,
"route", "scorer", "scored_at" (epoch seconds)}, plus "evidence": {gate: {...}} -- design 04 section 4.2
asks for each gate's evidence and label, and a reader that does not know the key ignores it
(benchmark.meaning_index reads `alpha`, `gates`, `formula_sha`, `route`, `scorer`, `scored_at` only). A gate
value is exactly true, false or null: the draw-4 scoring audit found gates stored as objects read null.

THE GATES, each read from the standard's own text (EX-ANTE: the rule was written from the text, before
any row was scored), and what is and is not decided:

  G1-G3  null, "not applicable to a generated alpha" (D39), unless the formula is a fingerprint near-dup
         (forge/novelty.py's instrument, root fingerprint.py) of a formula an authored composite rendered in
         the journal: then G1-G3 are that composite's `forge.standard.hard_gates` verdicts on gates 1-3 --
         form checks only, the only machine reading of the prose that exists (design 04 section 4.2).
         The composite named by `meta.hypothesis` is preferred when the formula is a near-dup of it
         (route "library"); otherwise the most similar one (route "inherited"). The label on the row is
         never believed on its own: a row whose `meta.hypothesis` names a composite whose formulas it does
         not resemble does not take that composite's text (round 3 S8: "routing follows the
         planner-written meta.hypothesis").
  G4     D52's clause only: FAILS when EVERY leg is crowded, alphaCount >= 200 from the catalogue, with the
         grouping fields sector / industry / subindustry excluded. A multi-field leg's alphaCount is the
         MINIMUM over its data fields. WHY THE MINIMUM (EX-ANTE, arithmetic, not data): the catalogue counts
         alphas per FIELD; the number of alphas that used ALL of a leg's fields cannot exceed the smallest of
         those counts, so the minimum is the tightest bound the catalogue gives on how many alphas already
         made this leg's combination. "Uncrowded" under it is proven from the catalogue; "crowded" is only
         possible. The alternative, the maximum ("the most crowded ingredient"), is NOT used; on the four
         accepted POSTs both readings give the same verdict (forge/tests/test_meaning.py), so those four do
         not choose between them, and a truth-table case pins the minimum. KNOWN LIMIT of the minimum: a
         crowded signal divided by an uncrowded field reads uncrowded, because D52 counts every data field,
         scales included. The standard's other G4 clauses -- the per-sub-regime sign map (prose), a >= 750
         field as PRIMARY (read as "any field" it tripped 37 of 37 passes, design 04 section 4.2), the
         decayed-classic haircut -- are NOT decided and are named in the evidence.
  G5     `forge.llm.verify.sign_verdict` on every DESCRIPTION-SIGNED leg: a leg whose direction is carried by
         exactly one field, reached from the leg's root through order-preserving operators only, whose label
         sign_source is "description". The leg's orientation is read from the FORMULA ((1 - SCORE) and
         `reverse` flip it; a denominator is a scale and carries no direction -- forge.typed and
         forge/llm/verify.py both read it so), never from meta. `notes` is always "": a generated alpha has no
         author to state an override, and a meta field reading "override" must not rescue a contradiction.
         NARROWED CLAIM (round 3 m18): sign_verdict passes agreement, an unstated sign and every domain-prior
         disagreement, and a spread of two fields has no labelled sign, so G5 fails ONLY when a single-field
         description-signed leg is oriented against its own description. The evidence lists the legs checked;
         "checked: []" with G5 true is a vacuous pass and says so.
  G6     construction, decidable half of standard gate 6 as design 04 section 4.2 lists it: >= 2 legs joined
         by a conditioning combiner (forge.hypotheses.COMBINERS: multiply or the if_else gate), legs from >= 2
         distinct label domains (forge.standard's "fewer than two cross-family legs", with a leg's domain read
         as forge.typed reads it: a denominator contributes none), bounded product operands and field-nature
         (forge.typed's structural judge, its H2 and H3 reasons only -- "overlaps H2/H3"), and no change
         operator (forge.typed.CHANGE) applied to something forge.typed infers is already a change ("return"
         kind: the standard's ts_delta on the already-delta change_in_eps_surprise). The NONNEG-R2 clause
         names one field and is not decided.
  G7     data existence: every field of the formula is in the catalogue of the alpha's own region, universe
         and delay. POINT-IN-TIME stays null in the evidence, UNMEASURED: no file on the desk records a
         field's point-in-time availability, and "a delay-1 simulation shows it" is SPECULATION (RULE 0 audit
         Y6, design 04 section 4.2). The gate's value is the existence half, as G4's is its leg clause; if
         that reading is wrong, G7 becomes null for every alpha and D39's automatic route never fires.
  G8     history collision, three clauses: (i) the journal holds the same candidate id (forge.factory's
         formula + settings key) under a DIFFERENT alpha created EARLIER -- the alpha's own rows never
         collide with it (round 3 X4: PreSimGate's DUPLICATE is for any id seen, which after the pass
         includes the alpha itself); (ii) D18: forge/novelty.py over the accepted POSTs other than this alpha;
         an incomplete index reads null, as it fails closed at submit; (iii) the NO_GO / TESTED-NULL /
         TESTED-REFUTED / debate_rejected bank, loaded by tools/funnel/precheck_lib.load_nogo_families (the
         ratified builder), hit as precheck_lib.precheck hits it (B10 O1, Khoa 2026-07-24: a one-field family
         needs an EXACT field set, a multi-field family a subset). The standard's `state/*targets*.json`
         greps (the funnel-era history) are NOT read: design 04 section 4.2 lists the journal in their place.

Null means "not decided", never a pass: `decidable_verdict` is true only when every decidable gate is true.

PURITY. `score` reads no file, no clock and no network; `load_catalogue` and `load_ledgers` read the desk's
files once, and `append` is the only writer. This module imports nothing from forge.submit (design 04
section 5.5: the router will import this module) and imports forge.llm.verify only inside `_g5` (that
module imports the planner, which this module does not need at import).
"""
from __future__ import annotations

import collections
import datetime
import glob
import hashlib
import importlib.util
import json
import math
import pathlib
import re

from forge import factory as F
from forge import labels as LB
from forge import novelty as NV
from forge import typed as TY

FP = NV.FP                     # Khoa's fingerprint instrument, imported once by forge.novelty

ROOT = pathlib.Path(__file__).resolve().parents[1]
#: The ledger benchmark.MEANING_LEDGER reads (forge/offline/benchmark.py; a test keeps the two equal).
LEDGER = ROOT / "state/forge/meaning.jsonl"
#: The journals forge.runner's PreSimGate reads for "already simulated" (runner.JOURNAL_GLOB; a test keeps
#: the two equal). Restated here so this module does not import the planner.
JOURNAL_GLOB = "state/layered/runs/*.jsonl"
#: The two POST logs forge.submit.posted_history reads (submit.LOG, submit.CLIMB_LOG; a test keeps them equal).
#: Its third source, the budget ledger, carries reservations with http None and no formula, which
#: forge.novelty.build ignores. Restated because this module must not import forge.submit.
POST_LOGS = ("state/forge/submitted.jsonl", "state/climb/submitted.jsonl")
#: The NO_GO bank of fetched/hypothesis_standard.md gate 8 (ALPHA_PIPELINE.md S4.1: build_nogo_list reads it).
NOGO_BANK = "state/alpha_hypotheses.jsonl"
PRECHECK = "tools/funnel/precheck_lib.py"

GATES = ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8")
#: D39: the gates a program decides for a generated alpha. benchmark.MEANING_DECIDABLE (a test keeps them equal).
DECIDABLE = ("G4", "G5", "G6", "G7", "G8")
#: D39: need written prose; "not applicable to a generated alpha" unless inherited.
NOT_APPLICABLE = ("G1", "G2", "G3")
#: D52: the grouping fields left out of a leg's alphaCount -- the three the pass-first grammar's G production
#: draws (design 04 section 2.2). D52 names these three; other group keys (market, country, ...) are NOT
#: excluded here. Under the minimum a crowded key can never make an uncrowded leg crowded, so this matters
#: only for a leg with no other field.
GROUPING = ("sector", "industry", "subindustry")
#: D52 and standard gate 4: "a composite whose every leg has alphaCount >= 200".
CROWDED = 200
#: how the G1-G3 text was reached: the composite the row names, a composite it resembles, none, or not read.
ROUTES = ("library", "inherited", "generated", "unknown")
COMBINERS = ("multiply", "gate")   # forge.hypotheses.COMBINERS; "gate" = if_else(greater(B, c), A, 0)
_COMPARE = ("greater", "greater_equal", "less", "less_equal")
#: Non-decreasing in their first argument, so a leg's direction passes through them unchanged (the platform's
#: operator definitions; forge.typed carries a sign through the same families: rank/score, smoothing,
#: backfill, change, the non-dispersion vec_ reducers). Anything else (abs, dispersion, correlation,
#: counting, logic, products, powers) makes the leg claim no direction on the field below it.
_ORDER = frozenset({
    "rank", "quantile", "ts_rank", "ts_quantile", "group_rank", "sigmoid", "tanh",
    "zscore", "ts_zscore", "group_zscore", "normalize", "scale", "ts_scale", "group_scale", "winsorize",
    "group_neutralize", "ts_mean", "ts_sum", "ts_decay_linear", "ts_decay_exp_window", "ts_delay",
    "ts_min", "ts_max", "ts_backfill", "group_backfill", "densify", "ts_delta", "ts_av_diff",
    "log", "sqrt", "signed_power", "vec_avg", "vec_sum", "vec_max", "vec_min"})
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

SCORER = "forge/meaning.py@sha256:" + hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()[:16]


def formula_sha(formula: str) -> str:
    """sha256 of the formula text exactly as simulated (the shared interface: no normalisation)."""
    return hashlib.sha256(formula.encode("utf-8")).hexdigest()


def decidable_verdict(gates: dict):
    """D39's rule on a row's gates: True when every DECIDABLE gate is exactly true (submit automatically),
    False when any is exactly false (not submitted), None otherwise (undecided: never an automatic submit).
    A value that is not exactly true / false reads as null, as benchmark._standard_gate reads it."""
    vals = [gates.get(g) if gates.get(g) is True or gates.get(g) is False else None for g in DECIDABLE]
    return False if False in vals else True if all(v is True for v in vals) else None


# ------------------------------------------------------------------------------------------- formula
def _leaves(n):
    if n.op is None:
        if n.name is not None:
            yield n.name
        return
    for a in n.args:
        yield from _leaves(a)
    for v in n.kw.values():
        yield from _leaves(v)


def _nodes(n):
    yield n
    for a in n.args:
        yield from _nodes(a)
    for v in n.kw.values():
        yield from _nodes(v)


def _has_data(n) -> bool:
    return any(x not in TY.GROUPS for x in _leaves(n))


def _const(n) -> bool:
    return n.op is None and n.name is None


def legs_of(tree) -> tuple:
    """(combiners, [(leg node, orientation)]). The pass-first grammar's productions (design 04 section 2.2):
    multiply(A, B), multiply(multiply(A, B), C) and the gate if_else(greater(B, c), A, 0); the old typed arm's
    outer gate nests the same way. A multiply with two or more data-bearing operands splits into its
    operands; a gate splits into its traded branch and its condition's data side (oriented + for greater,
    - for less, flipped when the data side is the second argument). Anything else is ONE leg."""
    def walk(n, o):
        if n.op == "multiply":
            parts = [a for a in n.args if _has_data(a)]
            if len(parts) >= 2:
                combs, legs = ["multiply"], []
                for a in parts:
                    c, l = walk(a, o)
                    combs, legs = combs + c, legs + l
                return combs, legs
        if (n.op == "if_else" and len(n.args) == 3 and not _has_data(n.args[2]) and _has_data(n.args[1])
                and n.args[0].op in _COMPARE):
            side = [i for i, a in enumerate(n.args[0].args) if _has_data(a)]
            if len(side) == 1:
                up = n.args[0].op in ("greater", "greater_equal")
                c, l = walk(n.args[1], o)
                return ["gate"] + c, l + [(n.args[0].args[side[0]], o if up == (side[0] == 0) else -o)]
        return [], [(n, o)]
    return walk(tree, 1)


def _directional(n, o) -> list:
    """[(field, orientation)] for every field whose value the leg's output moves with in a determinate
    direction. `1 - x` and `reverse` flip; `a - b` gives b the opposite orientation; a denominator is a
    scale (forge.typed: "THE DENOMINATOR IS A SCALE, NOT A LEG"); _ORDER passes through; the rest claims none."""
    if n.op is None:
        return [(n.name, o)] if n.name is not None and n.name not in TY.GROUPS else []
    a = n.args
    if n.op == "subtract" and len(a) == 2:
        if _const(a[0]) and not _const(a[1]):
            return _directional(a[1], -o)
        if _const(a[1]) and not _const(a[0]):
            return _directional(a[0], o)
        return _directional(a[0], o) + _directional(a[1], -o)
    if n.op == "reverse" and a:
        return _directional(a[0], -o)
    if n.op == "add":
        return [x for arg in a for x in _directional(arg, o)]
    if n.op == "divide" and len(a) == 2:
        return _directional(a[0], o)
    if n.op in _ORDER and a:
        return _directional(a[0], o)
    return []


def _domain_fields(n) -> list:
    """The fields that give a leg its domain: every field except a denominator's (forge.typed: "a scale
    contributes no domain")."""
    if n.op is None:
        return [n.name] if n.name is not None and n.name not in TY.GROUPS else []
    args = n.args[:1] if n.op == "divide" and len(n.args) == 2 else n.args
    return [x for arg in args for x in _domain_fields(arg)] + [x for v in n.kw.values() for x in _domain_fields(v)]


def _key(settings) -> tuple:
    s = settings or {}
    return s.get("region"), s.get("universe"), s.get("delay")


def _cat_ok(catalogue, settings) -> str:
    """"" when `catalogue` is the catalogue of the alpha's own region, universe and delay, else why not."""
    if catalogue is None:
        return "the catalogue was not read"
    want, have = _key(settings), (catalogue.get("region"), catalogue.get("universe"), catalogue.get("delay"))
    if None in want:
        return "the alpha's settings carry no region / universe / delay"
    if tuple(want) != tuple(have):
        return "the catalogue is %s/%s/d%s and the alpha ran on %s/%s/d%s" % (have + tuple(want))
    return ""


def _count(catalogue, field):
    v = ((catalogue.get("fields") or {}).get(field) or {}).get("alphaCount")
    return v if isinstance(v, int) and not isinstance(v, bool) else None


# ------------------------------------------------------------------------------------------- gates
def _g4(legs, catalogue, settings) -> tuple:
    rest = ("not decided (D52 decides only the every-leg clause): the per-sub-regime sign map is prose; "
            "'a >= 750 field as PRIMARY' has no decidable reading (read as any field it tripped 37 of 37 "
            "passes, design 04 section 4.2); the decayed-classic haircut is prose")
    ev = {"rule": "FAILS only when EVERY leg has alphaCount >= %d; a leg's alphaCount is the MINIMUM over its "
                  "data fields, %s excluded (D52)" % (CROWDED, "/".join(GROUPING)), "other_clauses": rest}
    why = _cat_ok(catalogue, settings)
    if why:
        return None, dict(ev, why=why)
    per_leg = []
    for node, _o in legs:
        fields = sorted({x for x in _leaves(node) if x not in GROUPING})
        if not fields:
            continue
        counts = {f: _count(catalogue, f) for f in fields}
        known = [c for c in counts.values() if c is not None]
        if known and (min(known) < CROWDED or len(known) == len(fields)):
            ac = min(known)
        else:
            ac = None
        per_leg.append({"fields": counts, "alphaCount": ac, "partial": len(known) != len(fields)})
    ev["legs"] = per_leg
    if not per_leg:
        return None, dict(ev, why="no leg carries a data field")
    if any(l["alphaCount"] is not None and l["alphaCount"] < CROWDED for l in per_leg):
        return True, dict(ev, why="at least one leg is uncrowded")
    if all(l["alphaCount"] is not None for l in per_leg):
        return False, dict(ev, why="every leg is crowded")
    return None, dict(ev, why="no leg is known uncrowded and a field is missing from the catalogue")


def _g5(legs, catalogue, settings) -> tuple:
    from forge.llm.verify import sign_verdict       # imports the planner; not needed at module import
    ev = {"rule": "forge.llm.verify.sign_verdict on every single-field description-signed leg; notes are "
                  "always '' (no author)", "narrowed": "fails only when such a leg is oriented against its "
                  "own description (round 3 m18)"}
    labels = (catalogue or {}).get("labels")
    if labels is None:
        return None, dict(ev, why="the label file was not read")
    key = "%s/d%s" % (_key(settings)[0], _key(settings)[2])
    checked, unchecked, bad = [], [], []
    for node, o in legs:
        occ = sorted(set(_directional(node, o)))
        if len(occ) != 1:
            unchecked.append({"leg": repr(node)[:120], "why": "no single signed field (%d signed occurrences)" % len(occ)})
            continue
        field, orient = occ[0]
        lab = LB.for_region(labels[field], key) if field in labels else {}
        if lab.get("sign_source") != "description" or lab.get("sign") not in ("+", "-"):
            unchecked.append({"leg": repr(node)[:120], "why": "%s: sign %s from %s" % (
                field, lab.get("sign", "unlabelled"), lab.get("sign_source", "no label"))})
            continue
        ok, why = sign_verdict(orient, lab, "", field)
        checked.append({"field": field, "orientation": orient, "description_sign": lab["sign"], "ok": ok})
        if not ok:
            bad.append("%s: %s" % (field, why))
    ev.update(checked=checked, unchecked=unchecked)
    if bad:
        return False, dict(ev, why="; ".join(bad))
    return True, dict(ev, why="no description-signed leg contradicts its description"
                      + ("" if checked else " (vacuous: no leg is description-signed)"))


def _g6(tree, formula, combs, legs, catalogue, settings) -> tuple:
    ev = {"rule": ">= 2 legs by a conditioning combiner (%s), >= 2 distinct leg domains, forge.typed H2/H3, "
                  "no change operator on a change" % "/".join(COMBINERS),
          "not_decided": "the NONNEG-R2 clause names one field (five_year_eps_trend_r_squared_2)",
          "combiners": combs}
    labels = (catalogue or {}).get("labels")
    if labels is None:
        return None, dict(ev, why="the label file was not read")
    key = "%s/d%s" % (_key(settings)[0], _key(settings)[2])
    reasons, undecided = [], False
    if len(legs) < 2:
        data_args = [a for a in tree.args if _has_data(a)] if tree.op in ("add", "subtract") else []
        reasons.append("additive combiner %s (a weighted sum, standard gate 6)" % tree.op if len(data_args) >= 2
                       else "one leg: a monotone re-rank of one signal (the standard's Law-1 null)")
    leg_domains = []
    for node, _o in legs:
        fs = _domain_fields(node)
        doms = {labels[f]["domain"] for f in fs if f in labels and labels[f].get("domain")}
        known = fs and all(f in labels and labels[f].get("domain") for f in fs)
        leg_domains.append(sorted(doms) if known else None)
    ev["leg_domains"] = leg_domains
    if len(legs) >= 2:
        distinct = {tuple(d) for d in leg_domains if d is not None}
        if len(distinct) < 2:
            if None in leg_domains:
                undecided = True
            else:
                reasons.append("every leg is in one domain %s" % (sorted(distinct)[0] if distinct else "-"))
    v = TY.judge(formula, labels, region=key, structural=True)
    reasons += [h for h in v["hard"] if h.startswith(("H2", "H3"))]
    for n in _nodes(tree):
        if n.op in TY.CHANGE and n.args:
            kind = TY.Judge(labels, key, structural=True).infer(n.args[0])["kind"]
            if kind == "return":
                reasons.append("%s on %r, already a change (return kind)" % (n.op, n.args[0]))
    if reasons:
        return False, dict(ev, why="; ".join(reasons))
    if undecided:
        return None, dict(ev, why="a leg's domain is unknown (a field has no label) and the known legs share one")
    return True, dict(ev, why="construction holds")


def _g7(tree, catalogue, settings) -> tuple:
    ev = {"rule": "every field of the formula is in the catalogue of the alpha's region/universe/delay",
          "point_in_time": None,
          "point_in_time_why": "UNMEASURED: no file on the desk records point-in-time availability; 'a delay-1 "
                               "simulation shows it' is SPECULATION (RULE 0 audit Y6, design 04 section 4.2)"}
    why = _cat_ok(catalogue, settings)
    if why:
        return None, dict(ev, why=why)
    fields = sorted({x for x in _leaves(tree) if x not in TY.GROUPS})
    missing = [f for f in fields if f not in (catalogue.get("fields") or {})]
    ev.update(fields=len(fields), missing=missing, source=catalogue.get("source"))
    return (False, dict(ev, why="not in the catalogue: %s" % ", ".join(missing))) if missing else \
        (True, dict(ev, why="every field exists"))


def _g8(tree, formula, alpha, settings, ledgers) -> tuple:
    clauses = {}
    j = ledgers.get("journal")
    if j is None or not isinstance(settings, dict):
        clauses["journal"] = (None, "the journal was not read" if j is None else "no settings")
    else:
        cid = F.candidate_id(formula, settings)
        rows = j.get(cid, [])
        own = [t for t, a in rows if a == alpha and t is not None]
        own_t = min(own) if own else None
        others = [(t, a) for t, a in rows if a != alpha]
        earlier = sorted({a for t, a in others if t is not None and own_t is not None and t < own_t})
        unknown = sorted({a for t, a in others if t is None or own_t is None})
        clauses["journal"] = ((False, "candidate %s was simulated earlier as %s" % (cid, ", ".join(earlier))) if earlier
                              else (None, "candidate %s also simulated as %s, order unknown" % (cid, ", ".join(unknown)))
                              if unknown else (True, "candidate %s: no earlier alpha" % cid))
    posts = ledgers.get("posts")
    if posts is None:
        clauses["d18"] = (None, "the POST logs were not read")
    else:
        idx = NV.build([h for h in posts if h.get("alpha") != alpha], ledgers.get("post_rows") or {})
        rep, sim, twin = idx.verdict(formula)
        clauses["d18"] = ((False, "near-dup of POST %s (similarity %.3f)" % (twin, sim)) if rep
                          else (None, "POST index incomplete: no formula for %s" % ", ".join(idx.missing))
                          if rep is None or not idx.complete
                          else (True, "no accepted POST is a near-dup (nearest %s, %.3f)" % (twin, sim)))
    nogo = ledgers.get("nogo")
    if nogo is None or tree is None:
        clauses["nogo"] = (None, "the NO_GO bank was not read" if nogo is None else "the formula did not parse")
    else:
        fields = frozenset(x for x in _leaves(tree) if x not in TY.GROUPS)
        hit = next((ng for ng in nogo if ng and ((ng == fields) if len(ng) == 1 else ng <= fields)), None)
        clauses["nogo"] = ((False, "reuses NO_GO family %s" % sorted(hit)) if hit is not None
                           else (True, "no NO_GO family among %d (%s)" % (len(nogo), ledgers.get("nogo_source", "-"))))
    vals = [v for v, _ in clauses.values()]
    val = False if False in vals else True if all(v is True for v in vals) else None
    return val, {"rule": "journal duplicate (earlier, other alpha) / D18 via forge.novelty / NO_GO bank",
                 "clauses": {k: {"value": v, "why": w} for k, (v, w) in clauses.items()},
                 "not_read": "state/*targets*.json (funnel era; design 04 section 4.2 names the journal)"}


def _text_gates(formula, meta, ledgers) -> tuple:
    """(G1-G3 values, route, inherited_from, evidence)."""
    comps = ledgers.get("composites")
    na = {g: None for g in NOT_APPLICABLE}
    if comps is None:
        return na, "unknown", None, {"why": "the composite index was not read"}
    sig = FP.structural_signature(formula)
    matches = {}
    for s, cid in comps.get("index") or ():
        if FP.near_duplicate(sig, s):
            matches[cid] = max(matches.get(cid, 0.0), FP.similarity(sig, s))
    named = (meta or {}).get("hypothesis")
    ev = {"near_dup_of": {c: round(v, 3) for c, v in sorted(matches.items())}}
    if named in matches:
        chosen, route = named, "library"
    elif matches:
        chosen, route = sorted(matches.items(), key=lambda kv: (-kv[1], kv[0]))[0][0], "inherited"
    else:
        note = (" (meta.hypothesis names %s, whose formulas this one does not resemble)" % named
                if named in (comps.get("verdicts") or {}) else "")
        return na, "generated", None, dict(ev, why="not applicable to a generated alpha (D39)" + note)
    verdict = (comps.get("verdicts") or {}).get(chosen)
    if verdict is None:
        return na, route, chosen, dict(ev, why="composite %s has no text verdict on file" % chosen)
    vals = {g: verdict.get(g) if verdict.get(g) in (True, False) else None for g in NOT_APPLICABLE}
    return vals, route, chosen, dict(ev, why="G1-G3 from composite %s: forge.standard.hard_gates, form checks "
                                             "only (design 04 section 4.2)" % chosen)


def score(formula: str, meta: dict, catalogue: dict, ledgers: dict, *, alpha: str, settings: dict,
          scored_at: float) -> dict:
    """The meaning row of one alpha. Pure: it reads only its arguments.

    catalogue: `load_catalogue`'s shape -- {"region", "universe", "delay", "fields": {id: {"alphaCount",
               "type"}}, "labels": {id: label record} or None, "source"}; None = not read.
    ledgers:   `load_ledgers`'s shape -- {"journal": {candidate id: [(epoch or None, alpha)]}, "posts":
               [submit-log rows], "post_rows": {alpha: {"formula"}}, "nogo": [frozenset of field ids],
               "nogo_source": str, "composites": {"verdicts": {id: {G1, G2, G3}}, "index": [(signature, id)]}};
               any key None or absent = not read, and every gate that needs it reads null.
    meta:      the journal row's meta; only `hypothesis` is read, and only as a preference (G1-G3 above).
    alpha, settings: the journal row's alpha id and settings. scored_at: epoch seconds, from the caller."""
    ledgers = ledgers or {}
    evidence = {}
    try:
        tree = TY.parse(formula)
    except ValueError as exc:
        tree = None
        parse_why = "the desk's parser (forge.typed.parse) refused the formula: %s" % exc
    gates = {}
    text, route, inherited, tev = _text_gates(formula, meta, ledgers)
    for g in NOT_APPLICABLE:
        gates[g] = text[g]
        evidence[g] = dict(tev, label={"library": "LIBRARY TEXT", "inherited": "INHERITED (D39)"}.get(
            route, "NOT APPLICABLE (D39)" if route == "generated" else "UNMEASURED"))
    if tree is None:
        for g in ("G4", "G5", "G6", "G7"):
            gates[g], evidence[g] = None, {"why": parse_why}
    else:
        combs, legs = legs_of(tree)
        gates["G4"], evidence["G4"] = _g4(legs, catalogue, settings)
        gates["G5"], evidence["G5"] = _g5(legs, catalogue, settings)
        gates["G6"], evidence["G6"] = _g6(tree, formula, combs, legs, catalogue, settings)
        gates["G7"], evidence["G7"] = _g7(tree, catalogue, settings)
    gates["G8"], evidence["G8"] = _g8(tree, formula, alpha, settings, ledgers)
    for g in DECIDABLE:
        evidence[g]["label"] = "EX-ANTE (rule from fetched/hypothesis_standard.md gate %s, D39/D52)" % g[1]
    return {"alpha": alpha, "formula_sha": formula_sha(formula), "gates": {g: gates[g] for g in GATES},
            "inherited_from": inherited, "route": route, "scorer": SCORER, "scored_at": scored_at,
            "evidence": evidence}


# ------------------------------------------------------------------------------------------- writer
def check_row(row) -> None:
    """Raises ValueError unless `row` has the shared meaning.jsonl shape. The writer refuses a malformed
    row rather than leaving the reader to guess (draw-4 scoring: object-shaped gates read null)."""
    if not isinstance(row, dict):
        raise ValueError("a meaning row is a dict")
    if not (isinstance(row.get("alpha"), str) and row["alpha"]):
        raise ValueError("alpha must be a non-empty string")
    if not (isinstance(row.get("formula_sha"), str) and _HEX64.match(row["formula_sha"])):
        raise ValueError("formula_sha must be a lower-case sha256 hex digest")
    g = row.get("gates")
    if not isinstance(g, dict) or set(g) != set(GATES) or any(not (v is True or v is False or v is None)
                                                               for v in g.values()):
        raise ValueError("gates must hold exactly %s, each true, false or null" % ", ".join(GATES))
    if row.get("route") not in ROUTES:
        raise ValueError("route must be one of %s" % (ROUTES,))
    if not (isinstance(row.get("scorer"), str) and row["scorer"]):
        raise ValueError("scorer must be a non-empty string")
    t = row.get("scored_at")
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t):
        raise ValueError("scored_at must be finite epoch seconds")
    inh = row.get("inherited_from")
    if inh is not None and not (isinstance(inh, str) and inh):
        raise ValueError("inherited_from must be a composite id or null")


def append(row: dict, path=None) -> tuple:
    """Append one row as ONE JSON line; return (path, appended?). Idempotent per (alpha, formula_sha): a
    second row for a pair already on file is NOT appended (returns False), so the earliest scoring stands --
    round 3 S8's "the earliest row per (alpha, formula_sha) decides", closed at the writer. Under an
    exclusive flock, as benchmark.record_card appends, and a last line cut short by an earlier crash gets a
    newline first so this row is whole on its own line."""
    import fcntl
    check_row(row)
    p = pathlib.Path(path or LEDGER)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, sort_keys=True, allow_nan=False, default=str)
    with p.open("a+b") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        for raw in fh:
            try:
                old = json.loads(raw)
            except ValueError:
                continue
            if isinstance(old, dict) and (old.get("alpha"), old.get("formula_sha")) == (row["alpha"], row["formula_sha"]):
                return p, False
        fh.seek(0, 2)
        if fh.tell():
            fh.seek(-1, 2)
            if fh.read(1) != b"\n":
                fh.write(b"\n")
        fh.write(line.encode() + b"\n")
    return p, True


# ------------------------------------------------------------------------------------------- loaders
def _jsonl(path):
    with open(path) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict):
                yield r


def _epoch(t):
    try:
        return datetime.datetime.fromisoformat(str(t).replace("Z", "+00:00")).timestamp() if t else None
    except ValueError:
        return None


def load_catalogue(region="USA", universe="TOP3000", delay=1, root=ROOT, only=None):
    """The field catalogue of one region/universe/delay (fetched/rc/fields/<R>_<U>_d<D>.jsonl) and the label
    file (fetched/rc/field_labels.jsonl), or None when the catalogue file does not exist. `only`: a set of
    field ids to keep (scoring a few alphas need not hold 85,612 rows). A missing label file gives
    labels None (G5 and G6 then read null)."""
    root = pathlib.Path(root)
    path = root / ("fetched/rc/fields/%s_%s_d%d.jsonl" % (region, universe, int(delay)))
    if not path.exists():
        return None
    fields = {r["id"]: {"alphaCount": r.get("alphaCount"), "type": r.get("type")}
              for r in _jsonl(path) if isinstance(r.get("id"), str) and (only is None or r["id"] in only)}
    lpath = root / "fetched/rc/field_labels.jsonl"
    labels = None
    if lpath.exists():
        keep = set(fields) | set(only or ())
        labels = {r["id"]: r for r in _jsonl(lpath) if r.get("id") in keep}
    return {"region": region, "universe": universe, "delay": int(delay), "fields": fields, "labels": labels,
            "source": str(path)}


def _nogo_families(bank: pathlib.Path, root: pathlib.Path) -> list:
    spec = importlib.util.spec_from_file_location("precheck_lib", root / PRECHECK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load_nogo_families(str(bank))


def load_ledgers(root=ROOT) -> dict:
    """Every ledger `score` reads, from the desk's files, in one pass over the journals.

    A NO_GO bank that does not exist reads as no NO_GO family (what precheck_lib.load_nogo_families returns
    for a file it cannot open) and `nogo_source` says it was absent -- MEASURED 2026-09-23 (read-only ssh):
    /opt/wq/state/alpha_hypotheses.jsonl does not exist, while the Mac copy holds 2 families."""
    from forge import hypotheses as H, standard as ST
    root = pathlib.Path(root)
    posts = []
    for rel in POST_LOGS:
        if (root / rel).exists():
            for r in _jsonl(root / rel):
                if r.get("alpha"):
                    posts.append({"alpha": r["alpha"], "mechanism_key": r.get("mechanism_key"),
                                  "posted_at": r.get("posted_at") or 0, "http": r.get("http"),
                                  "formula": r.get("formula")})
    accepted = {h["alpha"] for h in posts if h.get("http") in (200, 201)}
    comps = H.load_composites(root / "forge/composites", H.load_library(root / "forge/hypotheses"))
    ids = {c.id for c in comps}
    journal, formulas, post_rows = collections.defaultdict(list), collections.defaultdict(set), {}
    for p in sorted(glob.glob(str(root / JOURNAL_GLOB))):
        for r in _jsonl(p):
            f, st = r.get("formula"), r.get("settings")
            if not (f and isinstance(st, dict)):
                continue
            a = r.get("alpha")
            if a:
                journal[F.candidate_id(f, st)].append((_epoch(r.get("dateCreated")), a))
                if a in accepted and a not in post_rows:
                    post_rows[a] = {"formula": f}
            m = r.get("meta") or {}
            if m.get("composite") == 1 and m.get("hypothesis") in ids:
                formulas[m["hypothesis"]].add(f)
    index, seen = [], set()
    for cid in sorted(formulas):
        for f in sorted(formulas[cid]):
            k = (cid, FP.structural_fingerprint(f))
            if k not in seen:
                seen.add(k)
                index.append((FP.structural_signature(f), cid))
    verdicts = {c.id: {"G%d" % g: not any(t[0] == g for t in ST.hard_gates(c)) for g in (1, 2, 3)} for c in comps}
    bank = root / NOGO_BANK
    nogo = _nogo_families(bank, root) if bank.exists() else []
    return {"journal": dict(journal), "posts": posts, "post_rows": post_rows, "nogo": nogo,
            "nogo_source": str(bank) if bank.exists() else "%s absent: read as no NO_GO family" % bank,
            "composites": {"verdicts": verdicts, "index": index}}
