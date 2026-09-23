"""forge.allocate — where the next round's simulations go (Khoa 2026-09-06: "cải thiện hiệu quả số
alpha nộp được trên mỗi lượt sim").

MEASURED on the standing loop (6,251 sims, 09-04 21:27 → 09-06 20:50): 34% of simulations went to
(composite, cell) pairs that had ≥ 60 sims, no platform pass and a best Sharpe under 1.0; another
≈ 15% went to pairs whose mechanism had ALREADY produced a submitted alpha — their siblings read
prod-corr 0.79–0.85 against it and can never be submitted. Half the quota bought nothing by
construction. The allocator classifies every pair from the journal and orders the round:

  HARVESTED  a POSTed alpha exists for the pair's mechanism        → skipped
  DEAD       sims ≥ DEAD_SIMS, 0 platform-pass, best Sharpe < DEAD_BEST  → skipped
  NEAR_MISS  best Sharpe ≥ NEAR_BEST and its only failing checks are Sharpe-like (not a regional
             or investability line), no submission yet                    → first, block NEAR_BLOCK
  PASSED     a platform pass exists but nothing submitted (probe / corr pending) → next, block 10
  UNTRIED    no simulation yet                                            → then, block UNTRIED_BLOCK (10)
  ACTIVE     under DEAD_SIMS with no verdict                              → last, block BLOCK
Thresholds are EX-ANTE (bar 1.58; a "near miss" is within 0.3 of it); the proof is the yield per
1,000 simulations before and after, recorded in 02_design.
"""
from __future__ import annotations

import collections

from forge import dsr as D
from forge import score as SC

BAR = 1.58
BAR_BY_DELAY = {0: 2.69, 1: 1.58}   # platform LOW_SHARPE lines; every threshold below scales with the cell's bar


def scale(delay) -> float:
    """MEASURED 2026-09-07 01:53: with one bar for both delays, five USA/d0 pairs (best 1.71-1.74
    against a 2.69 line) were classed NEAR_MISS and took ~1,000 of the day's last ~2,100 sims,
    three of them the same composite under three category names; the daily quota ran out at
    14:53 ET. Khoa's tick was USA/d1 first and no d0 split."""
    return BAR_BY_DELAY.get(int(delay) if delay is not None else 1, BAR) / BAR
DSR_MARGIN = 0.54         # annual: DSR >= 0.95 at T=2493 needs SR - SR0 >= 1.645*sqrt(1.05)/sqrt(2492)*sqrt(252)
DSR_TARGET = 1.60         # the platform-passing Sharpe a near miss is expected to reach
OVERLAP_MAX = 1           # composites sharing more than this many legs with a POSTed alpha are not simulated
DEAD_SIMS = 40            # Khoa 2026-09-06 22:30 (A5): 40 vs 60 backtested 11/9 pairs, 2,341/2,161 sims saved, 0 later passes either way
DEAD_BEST = 1.0
NEAR_BEST = 1.3
NEAR_BLOCK = 40
PASSED_BLOCK = 40         # Khoa ticked 2026-09-09 20:12 (10 -> 40, the NEAR_MISS block). A pair that has already
                          # produced an alpha over every binding check but has not been submitted is the closest thing
                          # in the system to a submission. MEASURED that evening: of 53 USA/d1 rows failing only
                          # LOW_FITNESS at fitness >= 0.80, 52 belong to the two HARVESTED keys and exactly one
                          # (RRV7e8Qo, insider x IV-spread x profitability) to a never-submitted mechanism, with
                          # PROD 0.544 / SELF 0.365 clear of both lines; its SUBINDUSTRY arm needed 120 rows to
                          # produce one all-binding pass, so 10 rows/round cannot search a settings grid.
                          # Live measure: simulations per submission on PASSED pairs, over 5 rounds.
UNTRIED_BLOCK = 10        # Khoa 2026-09-06 22:30 (A3): max(first 20) - max(first 10) = 0.00 p50 over 54 pairs; ~2x pairs screened per round
SHARPE_LIKE = {"LOW_SHARPE", "LOW_FITNESS", "LOW_2Y_SHARPE", "IS_LADDER_SHARPE", "LOW_SUB_UNIVERSE_SHARPE",
               "LOW_TURNOVER", "HIGH_TURNOVER"}
# LADDER-DEAD (Khoa ticked 2026-09-09 14:50: "Bật ngay, dừng hẳn ở 40 sim"; live measure = sims per pass, 5 rounds). A pair with >= DEAD_SIMS rows none of which cleared the
# IS-ladder's first window (2022-01-03 -> 2024-01-02, limit 1.58) is DEAD whatever its 5-year Sharpe.
# RETROSPECTIVE on 11,298 USA/d1 rows (docs/harness5/round_2/diagnosis_ladder.md §4, 2026-09-09): every one
# of the 18 all-binding passers sits in a pair that had cleared the window by row 40; the rule would have
# stopped ~6,500 sims (58 %) and lost 0 passes. In-sample; the live measurement is sims per pass with vs without.
LADDER_DEAD = True
ORDER = {"NEAR_MISS": 0, "PASSED": 1, "UNTRIED": 2, "ACTIVE": 3, "DEAD": 8, "HARVESTED": 9}
COLD_CELL_SIMS = 300      # a cell with this many sims and no platform pass (e.g. GLB's regional lines) goes last
COLD_BEST = 1.2           # a cell whose best row is at least this (and fails only Sharpe-like lines) is hard, not cold


def pair_key(hypothesis, region, delay, category) -> tuple:
    return (hypothesis, "%s/d%s" % (region, delay), category)


def cleared_first_window(row):
    """True when the row's IS_LADDER_SHARPE check got past the first (2-year) window: the check
    reports the rung it stopped at, so PASS, or a FAIL/WARNING reported at year >= 3, both mean the
    year-2 window was cleared (API-OBSERVED on 11,298 rows, diagnosis_ladder.md §1). None when the
    row carries no ladder check (ERROR / incomplete rows): such a row is not evidence either way."""
    for c in row.get("checks") or []:
        if c.get("name") == "IS_LADDER_SHARPE":
            return c.get("result") == "PASS" or (c.get("year") or 0) >= 3
    return None


def pair_states(rows, posted_keys, bar: float = BAR) -> dict:
    """{pair: {"sims", "passes", "best", "best_fails", "keys", "harvested"}} from forge journal rows."""
    st = {}
    for r in rows.values() if isinstance(rows, dict) else rows:
        m = r.get("meta") or {}
        if not m.get("forge") or not r.get("alpha"):
            continue
        s = r.get("settings") or {}
        k = pair_key(m.get("hypothesis"), s.get("region"), s.get("delay"), m.get("category"))
        v = st.setdefault(k, {"sims": 0, "passes": 0, "best": None, "best_fails": [], "keys": set(), "harvested": False,
                              "sharpes": [], "delay": s.get("delay"), "ladder_y2": False, "ladder_n": 0})
        v["sims"] += 1
        y2 = cleared_first_window(r)
        if y2 is not None:
            v["ladder_n"] += 1
            v["ladder_y2"] = v["ladder_y2"] or y2
        if isinstance(r.get("sharpe"), (int, float)):
            v["sharpes"].append(float(r["sharpe"]))
        if m.get("mechanism_key"):
            v["keys"].add(m["mechanism_key"])
        stage = SC.stage(r)
        if stage["stage"] not in ("fail", "incomplete"):
            v["passes"] += 1
        sh = r.get("sharpe")
        if isinstance(sh, (int, float)) and (v["best"] is None or sh > v["best"]):
            v["best"], v["best_fails"] = float(sh), list(stage["failed"])
    # The ladder verdict is read per composite x region/delay: the same formulas and settings sit under
    # several category names (usa_insider_x_ivspread as Other / Option / Insiders, 2026-09-07), so a
    # per-category count would let a composite DEAD as one category re-run as another (code_review F12).
    agg = {}
    for k, v in st.items():
        a = agg.setdefault(k[:2], {"sims": 0, "y2": False})
        a["sims"] += v["ladder_n"]                    # rows that carry a ladder verdict
        a["y2"] = a["y2"] or v["ladder_y2"]
    for k, v in st.items():
        v["harvested"] = bool(v["keys"] & set(posted_keys))
        v["sims_rd"], v["ladder_y2_rd"] = agg[k[:2]]["sims"], agg[k[:2]]["y2"]
    return st


def dsr_headroom(v: dict, extra: int = NEAR_BLOCK) -> float:
    """SR0 (annual) the pair's cumulative DSR pool would impose after `extra` more draws."""
    sh = v.get("sharpes") or []
    if len(sh) < 4:
        return 0.0
    return D.ANNUALISE * D.expected_max_sharpe(D.var_sr_from_annual_sharpes(sh), len(sh) + extra)


def classify(v: dict | None) -> str:
    if v is None or v["sims"] == 0:
        return "UNTRIED"
    if v["harvested"]:
        return "HARVESTED"
    if v["passes"] > 0:
        return "PASSED"
    sc = scale(v.get("delay"))
    if LADDER_DEAD and v.get("sims_rd", 0) >= DEAD_SIMS and not v.get("ladder_y2_rd"):
        return "DEAD"          # whatever its 5-year best: ravenpack_x_short best 1.86, 0/300 past the window
    if v["best"] is not None and v["best"] >= NEAR_BEST * sc and set(v["best_fails"]) <= SHARPE_LIKE:
        # MEASURED 2026-09-06: a near miss whose own pool spread is wide (usa_shortsurprise: sd 0.80
        # annual, N 40) would impose SR0 1.76 -> 2.27 on itself; a 1.65 row there reads DSR 0.36 ->
        # 0.02. Exploiting it buys platform passes that the strict pool then refuses. Such a pair
        # is left ACTIVE (small blocks), never exploited.
        if dsr_headroom(v) <= DSR_TARGET * sc - DSR_MARGIN:
            return "NEAR_MISS"
        return "ACTIVE"
    if v["sims"] >= DEAD_SIMS and v["best"] is not None and v["best"] < DEAD_BEST * sc:
        return "DEAD"
    return "ACTIVE"


def cold_cells(states) -> set:
    """Cells (region/dD, category) with >= COLD_CELL_SIMS simulations, no platform pass, and no
    sign of being crackable: the cell's best row is under NEAR_BEST or fails a structural line
    (a regional / investability check). MEASURED 2026-09-06: USA/d1 Sentiment (1,005 sims, best
    1.28), Insiders (470, 1.25) and Social Media (601, 1.31) fail only Sharpe-like lines — hard,
    not cold; GLB/d1 (1,463, best 1.42) fails LOW_GLB_APAC/EMEA on its best row — cold."""
    agg = collections.defaultdict(lambda: {"sims": 0, "passes": 0, "best": None, "best_fails": []})
    for (hyp, cell, cat), v in states.items():
        a = agg[(cell, cat)]
        a["sims"] += v["sims"]
        a["passes"] += v["passes"]
        if v["best"] is not None and (a["best"] is None or v["best"] > a["best"]):
            a["best"], a["best_fails"] = v["best"], list(v["best_fails"])
    out = set()
    for k, a in agg.items():
        if a["sims"] < COLD_CELL_SIMS or a["passes"] > 0:
            continue
        sc = scale(k[0].rsplit("/d", 1)[-1] if "/d" in k[0] else 1)
        crackable = a["best"] is not None and a["best"] >= COLD_BEST * sc and set(a["best_fails"]) <= SHARPE_LIKE
        if not crackable:
            out.add(k)
    return out


def overlap_blocked(comp, posted_legs: dict) -> bool:
    """True when the composite shares more than OVERLAP_MAX legs with any POSTed composite.
    MEASURED 2026-09-06: every sibling of a POSTed alpha (same legs) read prod-corr 0.79-0.85; a
    composite that reuses two of three legs is a sibling with a different name."""
    legs = set(getattr(comp, "legs", ()))
    return any(len(legs & set(pl)) > OVERLAP_MAX for pl in posted_legs.values())


def order(cells, comps, states, per_block: int, categories_of=None, posted_legs=None, untried_block: int | None = None) -> list:
    """[(cell, composite, block, class)] in simulation priority; skipped classes are left out.
    Within a class, warm cells come before cold ones and the cells' own order is kept.
    `categories_of(comp)` -> the pyramid categories the composite's legs can fill (the planner
    derives it from the legs' hypotheses); default: the composite's own `categories` attribute."""
    categories_of = categories_of or (lambda comp: set(getattr(comp, "categories", ())))
    cold = cold_cells(states)
    posted_legs = posted_legs or {}
    out, seen = [], set()
    for cell in cells:
        for comp in comps:
            if cell.category not in categories_of(comp):
                continue
            if overlap_blocked(comp, posted_legs):
                continue
            # One block per composite x region x delay: the same settings on another category cell
            # are the same simulations under another name (usa_insider_x_ivspread took three
            # 40-blocks per round on USA/d0 as Other / Option / Insiders, 2026-09-07).
            if (comp.id, cell.region, cell.delay) in seen:
                continue
            k = pair_key(comp.id, cell.region, cell.delay, cell.category)
            cls = classify(states.get(k))
            if cls in ("HARVESTED", "DEAD"):
                continue
            seen.add((comp.id, cell.region, cell.delay))
            block = {"NEAR_MISS": NEAR_BLOCK, "PASSED": PASSED_BLOCK, "UNTRIED": untried_block or UNTRIED_BLOCK}.get(cls, per_block)
            out.append((cell, comp, block, cls))
    is_cold = lambda t: ("%s/d%d" % (t[0].region, t[0].delay), t[0].category) in cold   # noqa: E731
    out.sort(key=lambda t: (ORDER[t[3]], is_cold(t)))   # stable: cell order preserved inside a class
    return out


def summary(states) -> dict:
    return dict(collections.Counter(classify(v) for v in states.values()))
