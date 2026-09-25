"""forge.gen.spend -- the ticked spending rules, re-keyed on Khoa's fingerprint family (D36; design §3.4).

WHY THIS EXISTS (RULE 2 gate 5, design §3.4). DEAD_SIMS 40 (Khoa 09-06), LADDER_DEAD (ticked 09-09 14:50),
PASSED_BLOCK 40 (ticked 09-09 20:12), HARVESTED and `overlap_blocked` are keyed on the library's
hypothesis or composite (forge/allocate.py). On generated rows they never fire: the typed arm formed 254
allocator pair keys, only 3 with >= 40 rows (data audit Q7). D36 (Q4 option a) re-keys them on the
fingerprint family; the constants are allocate's own, imported, so a change there moves both.

WHAT THE RE-KEYING DID NOT DO: THE COUNT RULES DO NOT REACH 40 THROUGH DRAWS (draw-5 gen G3, RULE 2 gate 5;
a design-level item AWAITING KHOA'S TICK before stage 4). The code is faithful to D36 as ticked; what it
does not do is keep DEAD, LADDER_DEAD, PASSED_BLOCK and the in-round cap alive on draws.
  * MEASURED (POST-HOC), two ways, twice. propose() on the real USA/d1 labels (fetched/rc/field_labels.jsonl,
    14 serving categories, empty posterior, one round of 1,500 draws): FamilyIndex founded 1,500 families
    for 1,500 candidates, and pairwise fingerprint.near_duplicate over all 1,124,250 pairs found 0
    near-duplicate pairs (largest component 1, 0 exact-fingerprint repeats). The draw-5 adjudicator measured
    this with seed 7 (d5gen_adj_fam.py); re-derived here 2026-09-24 with seed 11 (d6gen_fam_real.py), the
    same four numbers.
  * CONSEQUENCE, EX-ANTE from the code given those singletons: a family's counted sims per cell are its
    founding draw plus the D37 repair grid of that formula (<= 11 rows; D51 neighbours are not counted,
    below), at most 12 while no later draw joins it. So the 40-row rules (DEAD, LADDER_DEAD,
    PASSED_EXHAUSTED) cannot fire, and the in-round cap (40 - sims >= 28) cannot bind on a draw. The same
    holds for the PNL_STOP (round 4 m20): it refuses only candidates assigned to a stopped family, i.e.
    repairs of its formulas and draws that are a fingerprint near-duplicate of a member; a PnL sibling that
    is a different formula founds its own family and is not refused. (Plan-time D18 is a separate rule; round 4's pf_e11 with the real state, 4 accepted
    POSTs and a complete index, refused 0 of 1,500 draws -- the auditor's run, not re-derived here.)
  * CONFOUND, stated before any reading of it: one round, an EMPTY posterior. Under a concentrated
    posterior draws may repeat structures and families may grow; family sizes under one are UNMEASURED.
    MECHANISM of the singletons: UNKNOWN (fingerprint's thresholds, the grammar's breadth over 19,596
    fields, or both; no experiment has separated them).
  * THE TICK (AskUserQuestion, not asked by this file): keep the family unit; use a coarser unit for the
    count rules; run design stage 2r's replay first; or turn the count rules off. Until it is ticked the
    precedent class applies: "a ticked rule re-keyed until it cannot fire" (RULE 2 gate 5).

THE RULES, per family x region/delay, in allocate.classify's order:
  PNL_STOP          D36: a family whose 984-day PnL correlation with an ACCEPTED POST is >= 0.70 gets no
                    further sims. The correlation is tools/self_corr_predict.predict (reproduces platform
                    SELF to <= 1e-4 in 7 of 8 cases, search F13 / data audit S3). A spend-stop, not a kill:
                    the family's alphas stay eligible and submit's own re-read decides (RULE 0 audit C9).
                    A member or POST with no cached curve gives no reading, and no reading is not a verdict
                    (memory `transient-read-as-truth`): the family is not stopped on its account. Neither
                    is a curve holding a value that is not a number (draw-5 gen N10: it used to raise
                    TypeError inside predict and end the round).
  PASSED / _EXHAUSTED  design §3.4 table: "<= 40 further sims per family after its first harvest-pass".
                    AL.PASSED_BLOCK is read here as that LIFETIME cap; in forge/allocate.py the same constant
                    is the size of a PASSED pair's block in EACH round (draw-5 gen N10: one name, two rules).
  LADDER_DEAD       >= DEAD_SIMS rows carrying a ladder verdict and none past the first (2-year) window.
  DEAD              >= DEAD_SIMS rows, no harvest-pass, best Sharpe < DEAD_BEST x the cell's bar scale.
  OPEN              otherwise.
Plan-time D18 (below) is the fifth: HARVESTED re-keyed onto the structure (§3.4).

THE IN-ROUND CAP (a choice, stated). allocate gives an undecided pair ONE block per round, which bounds how
far past 40 it can run before DEAD is read. A family has no block. So an OPEN family with fewer than
DEAD_SIMS sims may take at most DEAD_SIMS - sims more in one round, and its 40-sim verdict is read before
the 41st is spent ("dừng hẳn ở 40 sim", LADDER_DEAD's tick); a PASSED family takes at most what is left of
its 40. A family past 40 with no verdict has no cap from these rules.

UNIT TRANSFER UNTESTED (RULE 0 audit Q18). LADDER_DEAD's "58 % saved, 0 passes lost" was measured on the
hypothesis unit. Whether it holds on the fingerprint family is stage 2r's replay; re-keying the rule does not
make it proven, and it stays an open item (design §5.2).

WHAT THE D51 NEIGHBOURS DO HERE. They are not counted as the family's sims (forge/gen/repair.py says why);
every other generated row is.

tools/self_corr_predict IS IMPORTED ON FIRST USE (draw-5 gen N8). Its module body puts tools/ and
tools/autoloop at the front of sys.path; importing it here at module level did that for every importer of
forge.gen. `_predict()` imports it only when a (member, POST) pair is compared, and restores sys.path.
"""
from __future__ import annotations

import pathlib
import sys

from forge import allocate as AL
from forge.gen import families as FM
from forge.gen import posterior as PO

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: D36: "no further sims for a family whose 984-day PnL correlation with an accepted POST is >= 0.70".
PNL_LINE = 0.70
NEIGHBOUR_ROUTE = "neighbour"


def cell_of(row) -> str:
    s = row.get("settings") or {}
    return "%s/d%s" % (s.get("region"), s.get("delay"))


def family_stats(rows) -> dict:
    """{(family, "REGION/dD"): stats} over generated journal rows WITH an alpha, in journal order, D51
    neighbour rows left out. stats: sims, passes, after (sims after the first harvest-pass), best (max
    numeric Sharpe), ladder_n (rows with a ladder verdict), ladder_y2 (one of them cleared year 2), delay."""
    st = {}
    for r in (rows.values() if isinstance(rows, dict) else rows):
        fam = FM.family_of(r)
        if not fam or not r.get("alpha") or (r.get("meta") or {}).get("gen_route") == NEIGHBOUR_ROUTE:
            continue
        v = st.setdefault((fam, cell_of(r)), {"sims": 0, "passes": 0, "after": 0, "best": None,
                                              "ladder_n": 0, "ladder_y2": False,
                                              "delay": (r.get("settings") or {}).get("delay")})
        v["sims"] += 1
        if v["passes"]:
            v["after"] += 1
        if PO.harvest_pass(r):
            v["passes"] += 1
        sh = r.get("sharpe")
        if PO._num(sh) and (v["best"] is None or sh > v["best"]):
            v["best"] = float(sh)
        y2 = AL.cleared_first_window(r)
        if y2 is not None:
            v["ladder_n"] += 1
            v["ladder_y2"] = v["ladder_y2"] or y2
    return st


def _predict(a, b):
    """tools/self_corr_predict.predict, imported on first use with sys.path restored (module text, N8)."""
    saved = list(sys.path)
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import self_corr_predict as SCP  # pure predict(); the network helpers are never called here
    finally:
        sys.path[:] = saved
    return SCP.predict(a, b)


def _readable(c) -> bool:
    """A cached curve predict can read: a non-empty {date: cumulative} dict of numbers."""
    return isinstance(c, dict) and bool(c) and all(PO._num(v) for v in c.values())


def pnl_stops(rows, curves, accepted) -> dict:
    """{family: {"member", "post", "corr"}} for every family with a member whose cached curve correlates
    >= PNL_LINE with an accepted POST's cached curve (the highest such pair is kept as evidence). A curve
    that is not a readable dict of numbers gives no reading (module text)."""
    curves = {a: c for a, c in (curves or {}).items() if _readable(c)}
    posts = sorted(a for a in accepted if a in curves)
    out = {}
    for r in (rows.values() if isinstance(rows, dict) else rows):
        fam, a = FM.family_of(r), r.get("alpha")
        if not fam or a not in curves:
            continue
        for p in posts:
            v, _ = _predict(curves[a], curves[p])
            if v is not None and v >= PNL_LINE and v > out.get(fam, {}).get("corr", -2.0):
                out[fam] = {"member": a, "post": p, "corr": v}
    return out


def verdict(stats: dict | None, stopped: bool) -> tuple:
    """(state, room) for one family x cell: room = sims it may still take this round (None = no cap)."""
    if stopped:
        return "PNL_STOP", 0
    v = stats or {"sims": 0, "passes": 0, "after": 0, "best": None, "ladder_n": 0, "ladder_y2": False, "delay": 1}
    if v["passes"] > 0:
        room = AL.PASSED_BLOCK - v["after"]
        return ("PASSED", room) if room > 0 else ("PASSED_EXHAUSTED", 0)
    if AL.LADDER_DEAD and v["ladder_n"] >= AL.DEAD_SIMS and not v["ladder_y2"]:
        return "LADDER_DEAD", 0
    if v["sims"] >= AL.DEAD_SIMS and v["best"] is not None and v["best"] < AL.DEAD_BEST * AL.scale(v.get("delay")):
        return "DEAD", 0
    if v["sims"] < AL.DEAD_SIMS:
        return "OPEN", AL.DEAD_SIMS - v["sims"]
    return "OPEN", None


def d18_refuses(structures, formula: str) -> tuple:
    """(refused, similarity, twin): plan-time D18 (D36). A candidate that is a near-duplicate of an accepted
    POST is not simulated. FAIL-OPEN when the index is incomplete: a submission whose formula could not be
    read refuses nothing here (at plan time the stake is quota, not one of four daily slots; design §3.4),
    while every POST that WAS read still refuses its near-duplicates. D18 at submit (forge/novelty.py via
    forge/submit.py) stays fail-closed and unchanged. `structures` is novelty.build(...) or None."""
    if structures is None or len(structures) == 0:
        return False, 0.0, None
    rep, sim, twin = structures.verdict(formula)
    return rep is True, sim, twin
