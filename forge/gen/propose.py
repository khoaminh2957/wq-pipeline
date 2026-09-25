"""forge.gen.propose -- one generated round (design §4.1's `gen.propose`: posteriors + families + spending
rules), as a pure function of (state, labels, cells, n, seed). Nothing is simulated, written or posted.

ORDER INSIDE A ROUND, each with the decision behind it:
  1. D51 neighbours of every harvest-pass generated alpha handed in (a submission precondition; they go
     first so a round never spends its budget before the alphas it already found can be proven).
  2. D37 repairs: triggers whose coin reads "repair", oldest first, their unsimulated grid, together at
     most REPAIR_SHARE of the round.
  3. Draws for the rest, walking `cells` in the caller's order, at most `cell_cap` per cell (the runner's
     cell cap; its `taken` counter is read, never written: the result's `by_cell` is what to charge).
     Of the draws, FLOOR_SHARE ignore the posteriors and use base weights (D35's exploration floor, the
     only route to TIER_U); they are spread evenly through the round (draw k is a floor draw when fewer
     than FLOOR_SHARE x (k + 1) floor draws were kept before it, so a round of N draws holds ceil(N / 5)).

THE ROUTE STAMP (shared interface, D54): every candidate carries meta.gen_route, one of ROUTES --
  "fresh"      a draw from the grammar (steps 3); meta.gen_draw says which weights drew it: "posterior" or
               "floor". Only "fresh" enters D54's estimand.
  "neighbour"  a D51 neighbour (step 1), linked by meta.neighbour_of.
  "repair"     a D37 repair (step 2), linked by meta.repair_of.
D54 reports the last two beside the estimand, never in it (draw-5 scoring S1: counted in arm B they read
"better" in 0.285-0.51 of no-effect draws).

HANDED ROWS (draw-5 gen N2). The caller hands journal rows; only those `repair.provable` accepts (generated,
with an alpha and a formula, harvest-pass) are kept, once per alpha. The rest are counted, never given
neighbours: `handed-dropped` (not provable) and `handed-repeat` (an alpha already handed this round).

THE CELL CHARGE (draw-5 gen N1). `by_cell` counts every candidate against the runner cell it belongs to --
a draw against the cell it was drawn for, a neighbour or repair against the cell in `cells` with its row's
(region, delay, meta.category, universe) -- and a cell's draws take what is left of its cap after that
(`cell_cap - taken - by_cell`). Neighbours and repairs are CHARGED but never REFUSED by the cap: D51 makes a
neighbour a submission precondition and D37 bounds repairs by REPAIR_SHARE. A neighbour or repair whose cell
is not in `cells` is counted in `uncharged-<route>`, so a runner that charges by_cell sees what it missed.

WHAT EVERY CANDIDATE PASSES, in this order, and the counter a refusal lands in:
  excluded            a §2.3 exclusion (productions.exclusion_reason). The grammar cannot produce one; a
                      non-zero count is a bug.
  structure-refused   `runner.structurally_ok`'s call (H1-H4). Typed by construction, so also a bug count.
  duplicate           the candidate id is in `seen_ids` (the journal) or already made this round.
  d18-post-twin       plan-time D18 (D36): a near-duplicate of an accepted POST. Fail-open when the index is
                      incomplete (spend.d18_refuses).
  family-<STATE>      the family's D36 verdict refuses (PNL_STOP, PASSED_EXHAUSTED, LADDER_DEAD, DEAD), or
  family-room         its in-round room is spent.
  accept-refused      the caller's own chain (`accept`, e.g. quarantine and PreSimGate.check), called last.
The D51 neighbours take only excluded / structure-refused / duplicate / accept (forge/gen/repair.py says why).
A refused draw is redrawn, up to DRAW_TRIES per slot; the counts are returned so a round that starves shows
it (stage 5's alarm (b) watches the structural share). Other counters:
  neighbour-short     neighbours a provable alpha still lacks after its one-setting variants ran out or were
                      refused (draw-5 gen N3; a variant already in `seen_ids` -- which holds rows that never got
                      a verdict too -- is not re-planned). A round's `n` cutting the list short is not counted:
                      the next round plans the rest.
  cell-no-universe    a cell skipped because it names no universe (draw-5 gen N10);
  cell-unserved       a cell skipped because no primary field fills its category (draw-5 gen N10).

WHAT THIS FILE DOES NOT DO. It does not stamp pipeline_version, run_config, seed, arm_by or round
(runner._construction and runner.stamp do), does not read a file (forge/gen/state.load does, read-only),
and does not decide which alphas are handed in for neighbours (the caller does: every generated
harvest-pass it wants proven; the push-split case in forge/gen/repair.py is the caller's tick).
"""
from __future__ import annotations

import collections
import math
import random

from forge.gen import families as FM
from forge.gen import posterior as PO
from forge.gen import productions as P
from forge.gen import repair as RP
from forge.gen import spend as SP

#: D35: "a 20 % exploration floor" (SPECULATION in §3.2: no data sets the share; ticked as is).
FLOOR_SHARE = 0.20
#: Draw attempts per wanted candidate before a cell is given up for this round.
DRAW_TRIES = 50
#: meta.gen_route values (the shared interface; only "fresh" enters D54's estimand).
ROUTES = ("fresh", "neighbour", "repair")


def _cell_key(region, delay, category, universe) -> tuple:
    try:
        delay = int(delay)
    except (TypeError, ValueError):
        pass
    return region, delay, category, universe


def propose(state, labels: dict, cells, n: int, seed: int, field_datasets=None, handed=(), seen_ids=(),
            cell_cap: int = 60, taken=None, accept=None) -> dict:
    """One round's generated candidates, at most `n`.

    state           forge.gen.state.build(...) / load(root); read only
    labels          forge.labels.load(...): the typed vocabulary (field_labels.jsonl)
    cells           ordered cells (region, delay, category, universe), as the runner walks them
    field_datasets  callable (region, universe, delay) -> {field: dataset} from the catalogue, or None
    handed          journal rows to give D51 neighbours; only repair.provable ones are used (module text)
    seen_ids        candidate ids already simulated (gates.journal_ids)
    taken           {cell: constructions already planned this round} (read only)
    accept          callable(candidate) -> bool, the caller's own pre-sim chain, called last
    """
    rng = random.Random(seed)
    fd = field_datasets or (lambda region, universe, delay: None)
    known = set(seen_ids or ())        # the journal's ids, then every id this round makes
    index = state.families.copy()
    counts, by_route, by_cell = collections.Counter(), collections.Counter(), collections.Counter()
    rooms, out = {}, []
    cell_index = {}
    for c in cells:
        cell_index.setdefault(_cell_key(c.region, c.delay, c.category, c.universe), c)

    def charge(cand) -> None:
        """A neighbour or repair against its runner cell (module text: THE CELL CHARGE)."""
        s, m = cand["settings"], cand["meta"]
        c = cell_index.get(_cell_key(s.get("region"), s.get("delay"), m.get("category"), s.get("universe")))
        if c is None:
            counts["uncharged-" + m["gen_route"]] += 1
        else:
            by_cell[c] += 1

    def room(fam, cell):
        if (fam, cell) not in rooms:
            rooms[(fam, cell)] = list(state.verdict(fam, cell))
        return rooms[(fam, cell)]

    def admit(cand, family, cell, spend_rules=True, register=False) -> bool:
        why = P.exclusion_reason(cand["formula"], cand["settings"])
        if why:
            counts["excluded"] += 1
            return False
        if not P.structurally_ok(cand["formula"], cand["settings"], labels)[0]:
            counts["structure-refused"] += 1
            return False
        if cand["id"] in known:
            counts["duplicate"] += 1
            return False
        if spend_rules:
            if SP.d18_refuses(state.structures, cand["formula"])[0]:
                counts["d18-post-twin"] += 1
                return False
            st, left = room(family, cell)
            if st not in ("OPEN", "PASSED"):
                counts["family-" + st] += 1
                return False
            if left is not None and left <= 0:
                counts["family-room"] += 1
                return False
        if accept is not None and not accept(cand):
            counts["accept-refused"] += 1
            return False
        known.add(cand["id"])
        if spend_rules and rooms[(family, cell)][1] is not None:
            rooms[(family, cell)][1] -= 1
        if register:
            index.add(cand["formula"], family)
        by_route[cand["meta"]["gen_route"]] += 1
        out.append(cand)
        return True

    # 1. D51 neighbours
    handed_alphas = set()
    for row in handed or ():
        if not RP.provable(row):
            counts["handed-dropped"] += 1
            continue
        if row["alpha"] in handed_alphas:
            counts["handed-repeat"] += 1
            continue
        handed_alphas.add(row["alpha"])
        need = RP.NEIGHBOURS - len(RP.existing_neighbours(row, state.rows_by_formula))
        got, cut = 0, False
        for s in RP.neighbours(row, state.rows_by_formula, known):
            if len(out) >= n:
                cut = True
                break
            cand = P.from_row(row, s, "neighbour", state.sha, fd(s.get("region"), s.get("universe"), s.get("delay")),
                              neighbour_of=row.get("alpha"))
            if admit(cand, None, None, spend_rules=False):
                got += 1
                charge(cand)
        if not cut and got < need:
            counts["neighbour-short"] += need - got

    # 2. D37 repairs
    repair_room = min(int(math.floor(RP.REPAIR_SHARE * n)), n - len(out))
    used = 0
    for row in state.triggers:
        if used >= repair_room:
            break
        if not RP.coin(row["formula"]):
            counts["repair-coin-control"] += 1
            continue
        fam = FM.family_of(row)
        for s in RP.unsimulated(row, known):
            if used >= repair_room:
                break
            cand = P.from_row(row, s, "repair", state.sha, fd(s.get("region"), s.get("universe"), s.get("delay")),
                              repair_of=row.get("alpha"))
            if admit(cand, fam, SP.cell_of(row)):
                used += 1
                charge(cand)

    # 3. draws
    pools = {}
    for c in cells:
        if (c.region, int(c.delay)) not in pools:
            pools[(c.region, int(c.delay))] = P.FieldPool(labels, c.region, int(c.delay))
    datasets = sorted({d for p in pools.values() for d in p.datasets})
    W_post, theta = PO.round_weights(state.posterior, rng, datasets)
    W_floor, _ = PO.floor_weights()
    taken = taken or {}
    n_draws = n_floor = 0
    for c in cells:
        if len(out) >= n:
            break
        want = min(cell_cap - taken.get(c, 0) - by_cell[c], n - len(out))
        pool = pools[(c.region, int(c.delay))]
        if want <= 0:
            continue
        if not c.universe:
            counts["cell-no-universe"] += 1
            continue
        if not pool.serves(c.category):
            counts["cell-unserved"] += 1
            continue
        cell = "%s/d%s" % (c.region, int(c.delay))
        kept = tries = 0
        while kept < want and tries < want * DRAW_TRIES:
            tries += 1
            # round() is a guard only: 0.2 x 5j == j exactly for every j <= 100,000, and over k <= 500,000
            # round(0.2 k, 9) never moves an integer comparison (draw-5 gen N6; re-checked 2026-09-24)
            floor = n_floor < round(FLOOR_SHARE * (n_draws + 1), 9)
            W, th = (W_floor, None) if floor else (W_post, theta)
            core = P.draw(rng, pool, W, th, c.category)
            if core is None:
                counts["no-draw"] += 1
                continue
            settings = P.draw_settings(rng, W, c.region, c.universe, c.delay)
            fam, founded = index.assign(core["formula"])
            cand = P.candidate(core, settings, c.category, fam, "fresh", state.sha,
                               fd(c.region, c.universe, c.delay), draw_mode="floor" if floor else "posterior")
            if admit(cand, fam, cell, register=True):
                kept += 1
                n_draws += 1
                n_floor += floor
                by_cell[c] += 1
                counts["family-founded"] += founded
    return {"candidates": out, "gen_state": state.sha, "counts": dict(counts), "by_route": dict(by_route),
            "by_cell": dict(by_cell), "n_draws": n_draws, "n_floor": n_floor}
