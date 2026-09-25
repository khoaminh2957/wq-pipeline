"""forge.gen.repair -- the near-passer repair queue (D37, design §3.5) and the D51 neighbours.

D37 (Khoa 2026-09-23 ~17:20, Q5 option a): "a row failing exactly one check gets its settings grid (<= 11
sims, each once), <= 10 % of a round, and a coin flip per trigger decides repair / no repair, so the queue
carries its own control."
  * TRIGGER: a generated row with an alpha whose check set has exactly ONE harvest-pass check that reads
    FAIL / WARNING / ERROR (every check outside score.NON_BINDING, the §0 definition) and none pending.
  * GRID: the other neutralization x decay x truncation combinations of the grammar's SETTINGS
    (3 x 2 x 2 - 1 = 11), region / universe / delay kept, minus every combination already simulated
    (its candidate id is in the journal) -- "each once": simulation is deterministic on the 4 duplicate
    pairs on file (RULE 0 audit Q7).
  * COIN: fair, keyed on the trigger's FORMULA (sha256 of a fixed salt and the formula's sha), not on the
    round seed and not on the alpha id. The repair's object is the formula's grid; a coin per alpha would
    let a second trigger row of one formula repair a formula the first row's coin had put in the control.
    The same formula always gets the same coin, on any host and in any round, so the control can be
    re-derived from the journal alone. Independent of D47's round arm by construction (the arm is a
    round-level draw; this is a hash of the formula).
  * ORDER: oldest trigger first (journal order), so a partly repaired grid is finished before a newer
    one is opened and no trigger starves. A choice; the design names none.
  * WHAT THE EVIDENCE SAYS, POST-HOC (§3.5): later settings-siblings of a trigger passed at 37.8 per 1,000
    against 0.6 per 1,000 for other rows -- 9 alphas from 6 formulas in 2 hypotheses; "not a transferable
    repair law". The coin exists because nothing on file answers whether repair is worth its sims.

D51 (Khoa 2026-09-23 ~21:00): "each generated alpha that clears every check is re-simulated at two
one-setting neighbours before it can be submitted", so D3's neighbourhood stability is measured for
generated alphas too (round 3 S13: 0 of 919 typed-arm formulas ever had two). A NEIGHBOUR here is a row
that benchmark.neighbourhood_stability counts WHEN IT GRADES THE ALPHA'S OWN VERSION CARD: the same
formula, region, delay and universe, differing in exactly one of decay, neutralization, truncation, with a
numeric Sharpe, AND carrying the alpha's own (meta.pipeline_version, meta.run_config) -- the pair
benchmark.cohort_of reads, because build_from draws a stamped card's neighbour pool from that cohort only
(S10-NL). A date-window card (no version) pools every scored row, so it can count more than this does, never
fewer. The knob values are the grammar's pre-registered SETTINGS levels (round 3 X2: the pipeline must not
choose the step per alpha). Existing in-cohort neighbours (a repair grid may already hold some) count toward
the two; the missing ones are taken in an order keyed on the alpha id, skipping any combination already
simulated in ANY cohort (a neighbour that ERRORed is replaced by the next, not retried; re-simulating a
construction the journal holds is refused as a duplicate).
  * DRAW-5 GEN G1 (fixed here): the count used to take one-knob siblings from every cohort, so an alpha
    stamped V1 whose two siblings were stamped V2 planned 0 more while the judge read it UNMEASURED on V1's
    card (d5gen_adj_d51.py). forge/tests/test_gen_repair.py pins the cohort rule.
  * THE PUSH-SPLIT CASE, a D51 x S10-NL / round-3 S14 conflict FOR A KHOA TICK (EX-ANTE, read from the code;
    not measured live). The runner stamps every construction with the version that PLANS it. An alpha found
    in round r under version V1 gets its neighbours planned in round r+1; if a push lands between the two
    rounds they carry V2, and V1's card never counts them. With this file's cohort rule the loop then plans
    the remaining one-knob variants (there are 4: NEUT has 2 other levels, DECAY 1, TRUNC 1), still under V2,
    and after at most 4 sims in all the alpha is `neighbour-short` for good: D51 cannot be met for it on V1's
    card by any number of sims. Without the cohort rule the loop spent 2 and stopped, and V1's card read the
    alpha's neighbourhood UNMEASURED anyway. Options for the tick, none chosen here: hand propose() only
    alphas of the round's own cohort (an alpha found just before a push is then never proven); let the judge
    count neighbours across one push; or accept the loss and count it (the `neighbour-short` counter).

D51 x D36, NAMED (RULE 2 gate 5). D36 stops a family's sims (DEAD, LADDER_DEAD, PASSED_BLOCK, the PnL
stop, plan-time D18) and says a PnL-stopped family's alphas "stay eligible"; D51 makes neighbours a
precondition of submitting them and of the scorecard reading them PROVEN (D26 counts UNPROVEN against the
version). Applying the stops to the neighbours would void D36's "stay eligible" and D51's purpose alike, so
propose() emits the neighbours of every harvest-pass alpha handed to it through the §2.3 exclusions, the
structural gate, the duplicate check and the caller's own chain only, and spend.family_stats does not count
them as the family's sims. Which alphas to hand over is the caller's decision; propose() keeps only the ones
`provable()` accepts. This resolution is not a tick; it is on the report for Khoa. THE NEIGHBOUR CASCADE,
named with it (draw-5 gen N4, EX-ANTE, read): a neighbour or repair row that is itself harvest-pass is a
generated alpha clearing every check, so D51 applies to it too and it gets neighbours of its own -- all of
them on the same formula's 12-setting grid (3 x 2 x 2), so at most 12 rows per (formula, region, delay,
universe) -- and none of the cascade is family accounting. Not a tick either.
"""
from __future__ import annotations

import hashlib
import random

from forge import score as SC
from forge.factory import candidate_id
from forge.gen import posterior as PO
from forge.gen import productions as P

#: D37: at most this share of a round goes to repairs.
REPAIR_SHARE = 0.10
COIN_SALT = "forge.gen D37 repair coin v1|"
#: D51: "two one-setting neighbours" (the judge's NEIGHBOURS_MIN is also 2; the loop does not import the
#: judge -- Draw 4: the judged never imports the judge).
NEIGHBOURS = 2
ORDER_SALT = "forge.gen D51 neighbour order v1|"
KNOBS = (("neutralization", P.NEUT), ("decay", P.DECAY), ("truncation", P.TRUNC))
#: D30 / S10-NL: the stamps a version card's neighbour pool is keyed on (benchmark.cohort_of reads this pair).
COHORT_KEYS = ("pipeline_version", "run_config")


def failing(row) -> tuple:
    """(bad, pending): harvest-pass checks that read FAIL / WARNING / ERROR, and those that read anything
    else but PASS -- score.platform_verdict's reading, split so "exactly one" can be asked."""
    bad, pending = [], []
    for name, c in SC.checks(row).items():
        if name in SC.NON_BINDING:
            continue
        res = c.get("result")
        if res in ("FAIL", "WARNING", "ERROR"):
            bad.append(name)
        elif res != "PASS":
            pending.append(name)
    return sorted(bad), sorted(pending)


def is_trigger(row) -> bool:
    if not PO.is_generated(row) or not row.get("alpha") or not row.get("formula"):
        return False
    bad, pending = failing(row)
    return len(bad) == 1 and not pending


def coin(formula: str) -> bool:
    """True = repair, False = the control arm. A fair coin keyed on the formula (see the module text)."""
    return hashlib.sha256((COIN_SALT + P.formula_sha(formula)).encode()).digest()[0] & 1 == 1


def _norm(knob, v):
    try:
        return int(v) if knob == "decay" else float(v) if knob == "truncation" else str(v)
    except (TypeError, ValueError):
        return v


def grid(settings: dict) -> list:
    """Every other SETTINGS combination, region / universe / delay kept, in a fixed order."""
    own = tuple(_norm(k, settings.get(k)) for k, _ in KNOBS)
    out = []
    for neut in P.NEUT:
        for decay in P.DECAY:
            for trunc in P.TRUNC:
                if (neut, decay, trunc) != own:
                    out.append(dict(settings, neutralization=neut, decay=decay, truncation=trunc))
    return out


def triggers(rows) -> list:
    """The first trigger row of each distinct formula, oldest first."""
    out, seen = [], set()
    for r in (rows.values() if isinstance(rows, dict) else rows):
        if is_trigger(r):
            key = "".join(r["formula"].split())
            if key not in seen:
                seen.add(key)
                out.append(r)
    return out


def unsimulated(row, seen_ids) -> list:
    """The trigger's grid minus every combination already simulated."""
    return [s for s in grid(row.get("settings") or {}) if candidate_id(row["formula"], s) not in seen_ids]


def one_setting_variants(settings: dict) -> list:
    """Every grammar setting that differs from `settings` in exactly one knob, in KNOBS order."""
    out = []
    for knob, levels in KNOBS:
        for lv in levels:
            if lv != _norm(knob, settings.get(knob)):
                out.append(dict(settings, **{knob: lv}))
    return out


def formula_key(row) -> tuple:
    s = row.get("settings") or {}
    return ("".join((row.get("formula") or "").split()), s.get("region"), s.get("delay"), s.get("universe"))


def cohort(row) -> tuple:
    """(meta.pipeline_version, meta.run_config) of a row, compared by equality (the loop does not import the
    judge, so benchmark.cohort_of's plain-stamp rule is not applied here: two rows with the same marked stamp
    are one cohort to this file and to no version card)."""
    m = row.get("meta") or {}
    return tuple(m.get(k) for k in COHORT_KEYS)


def provable(row) -> bool:
    """Whether D51 applies to a handed row: a generated row (meta.hypothesis gen:<family>) with an alpha and a
    formula that is harvest-pass. Draw-5 gen N2: a library row (hypothesis 'usa_library_hyp', checks []) handed
    twice used to get 4 neighbours, all stamped arm 'gen'."""
    return PO.is_generated(row) and bool(row.get("alpha")) and bool(row.get("formula")) and PO.harvest_pass(row)


def existing_neighbours(row, rows_by_formula) -> list:
    """Journal rows the judge counts as this row's one-setting neighbours on the row's OWN version card
    (benchmark's rule: str() comparison of the three knobs, a numeric Sharpe, another alpha; and build_from's
    cohort pool, S10-NL: the same (pipeline_version, run_config), draw-5 gen G1)."""
    s = row.get("settings") or {}
    own = cohort(row)
    out = []
    for r in rows_by_formula.get(formula_key(row), ()):
        if r.get("alpha") == row.get("alpha") or not PO._num(r.get("sharpe")) or cohort(r) != own:
            continue
        rs = r.get("settings") or {}
        if sum(1 for k, _ in KNOBS if str(rs.get(k)) != str(s.get(k))) == 1:
            out.append(r)
    return out


def neighbours(row, rows_by_formula, seen_ids) -> list:
    """The settings to simulate so `row` reaches NEIGHBOURS one-setting neighbours (D51)."""
    need = NEIGHBOURS - len(existing_neighbours(row, rows_by_formula))
    if need <= 0:
        return []
    # every setting the journal holds for this formula, in any cohort: re-simulating one would repeat a
    # construction (G1 counts only in-cohort rows as neighbours; it must not re-plan out-of-cohort ones)
    taken = {tuple(str((r.get("settings") or {}).get(k)) for k, _ in KNOBS) for r in rows_by_formula.get(formula_key(row), ())}
    opts = [s for s in one_setting_variants(row.get("settings") or {})
            if candidate_id(row["formula"], s) not in seen_ids and tuple(str(s.get(k)) for k, _ in KNOBS) not in taken]
    seed = int.from_bytes(hashlib.sha256((ORDER_SALT + str(row.get("alpha"))).encode()).digest()[:8], "big")
    random.Random(seed).shuffle(opts)
    return opts[:need]
