#!/usr/bin/env python3
"""submit_plan.py — DRY-RUN driver that wires the automatic submitter together and prints the plan.

This module CANNOT submit. It imports no HTTP client, holds no session, issues no request, and
hands `tools/auto_submit.py` a transport whose every method raises. The irreversible POST belongs to
auto_submit; this driver rehearses the chain around it and stops.

Scope: USA delay 1, by construction (SCOPE). A piece that reports any other pair does not get its
row skipped — it REFUSES THE WHOLE RUN. Silently dropping an out-of-scope row hides the bug whose
cheapest symptom is an irreversible submit in a book we were not aiming at.

THE CHAIN AS IT ACTUALLY EXISTS (2026-08-13)
--------------------------------------------
  pyramid_gate.cell_state()  -> CellState (counts, age, source)      [LANDED]
  pyramid_gate.priority()    -> [CellNeed] fewest-still-needed first [LANDED]
  cell_map.cells_for(code)   -> which cell(s) that formula fills     [LANDED]
  submit_rank.rank_for_cell  -> which alpha to spend on a cell       [LANDED]
        |
        v   the seam between them is state/auto_submit_decisions.json
  auto_submit.run(cfg, transport, live=False)                        [LANDED]

All four landed. NOTHING IN THE REPO WRITES state/auto_submit_decisions.json — the seam that turns
a ranking into the submitter's input is unowned, and this driver writes only a scratch copy.

WHAT THIS DRIVER ADDS, BECAUSE THE LANDED PIECES DO NOT DO IT
  auto_submit.preflight() never calls pyramid_gate. It checks that a decision NAMES a cell; it
  never checks that the cell still NEEDS an alpha. A hand-written decisions file naming a full cell
  (Price Volume, 40/3) passes preflight and reaches the POST. This driver runs pyramid_gate.decide()
  over every row before emitting it, and reports the missing wire rather than papering over it.

  auto_submit.corr_verdict() reads prod_maxcorr only. There is no self-correlation gate anywhere on
  that path, and self-corr is the one that bites (e7x0G7ag read self 0.414 when banked and 0.99 once
  its twin went live). This driver requires BOTH numbers.

GUARDS THIS DRIVER OWNS (it does not trust the pieces to be safe)
  1. scope lock      every row is USA/1 or the run refuses
  2. freshness       counts must be source="live" AND younger than MAX_COUNT_AGE_S
  3. capacity        a cell's remaining need is decremented inside the run
  4. one mechanic    a row sharing a planned mechanic is DROPPED loudly, never silently
  5. corr verdict    prod AND self both measured, or the alpha is dropped
  6. provenance      a cell_map UNKNOWN (unresolved token / >=3-cell forfeit) is refused
  7. kill switch     re-read before EVERY row, and both switch paths are honoured
  8. crash window    auto_submit.post_permitted() adjudicates unresolved intents
  9. never arm       refuses to write auto_submit's real decisions path

Usage:
  python3 tools/submit_plan.py            dry run against the real counts (refuses if not live)
  python3 tools/submit_plan.py --rehearse plan against the CACHED counts, stamped REHEARSAL
  python3 tools/submit_plan.py --blast    print the blast-radius arithmetic and exit

--rehearse exists so the plan can be READ when there is no live session. It relabels the cached
counts as live and says so on every line. It cannot submit: this module has no live mode, and the
transport it hands auto_submit raises on every verb.
"""
import json, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

SCOPE = ("USA", 1)                 # the ONLY pair this driver may plan for
UNLOCK_AT = 3
MAX_COUNT_AGE_S = 3600             # stricter than pyramid_gate's 6h: see BLAST/laundering note
KILL = ROOT / "state/SUBMIT_KILL"
SCRATCH_DECISIONS = ROOT / "state/submit_plan_dryrun_decisions.json"


class Refusal(Exception):
    """Raised when the chain cannot proceed HONESTLY. Never caught to produce a default."""


class NoTransport:
    """The transport handed to auto_submit in a rehearsal. Every attribute raises.

    A dry run that merely *intends* not to POST is one branch away from POSTing. This makes the
    absence of a POST a property of the object, not of the control flow."""
    def __getattr__(self, name):
        def boom(*a, **k):
            raise AssertionError(f"the rehearsal reached the network: transport.{name}{a}")
        return boom


PIECES = {
    "pyramid_gate": ("cell_state", "priority", "decide", "SUBMIT"),
    "cell_map": ("cells_for", "Verdict"),
    "submit_rank": ("rank_for_cell",),
    "auto_submit": ("run", "post_permitted", "read_journal", "DECISIONS"),
}


def bind(missing_ok=False):
    """Import the four pieces and bind their contract names. Never manufactures a substitute."""
    got, gone = {}, []
    for mod, names in PIECES.items():
        try:
            m = __import__(mod)
        except ImportError:
            gone.append(f"{mod}.py — module absent")
            continue
        absent = [n for n in names if not hasattr(m, n)]
        if absent:
            gone.append(f"{mod}: contract name(s) absent: {', '.join(absent)}")
            continue
        got[mod] = m
    if gone and not missing_ok:
        raise Refusal("cannot plan; missing pieces:\n    " + "\n    ".join(gone))
    return got, gone


# ---------------------------------------------------------------- guards

def kill_engaged():
    if KILL.exists():
        return True
    try:
        import auto_submit
        return auto_submit.kill_switch_engaged()[0]
    except ImportError:
        return False


def check_counts(st):
    """Validate a pyramid_gate CellState before any decision rests on it."""
    if (getattr(st, "region", None), getattr(st, "delay", None)) != SCOPE:
        raise Refusal(f"pyramid_gate returned {getattr(st,'region',None)}/"
                      f"{getattr(st,'delay',None)}, this driver is scoped to "
                      f"{SCOPE[0]}/{SCOPE[1]} — refusing the whole run")
    if st.counts is None:
        raise Refusal(f"pyramid_gate has no cell data ({st.source}: {st.error})")
    if st.source != "live":
        raise Refusal(f"pyramid_gate counts are source={st.source!r}, not 'live' — a cached count "
                      "cannot authorise spending an alpha, however fresh its file mtime looks")
    if st.age_s is None or st.age_s > MAX_COUNT_AGE_S:
        raise Refusal(f"pyramid_gate counts are age={st.age_s} (limit {MAX_COUNT_AGE_S}s) — "
                      "refusing to plan on a stale count")
    return dict(st.counts)


def check_mapping(aid, v):
    """Validate a cell_map Verdict. Returns the cell set, or None with a reason to drop.

    `v.refuse` is cell_map's own UNKNOWN, which covers three distinct dangers it measured: an
    unresolved formula token, no recognised field at all, and the >=3-cell forfeit (both 3-cell
    alphas on this account read pyramidThemes.effective == 0 and were credited NOWHERE). Any of
    them means the cell is not established, and a guessed cell is not a cell."""
    if not hasattr(v, "cells") or not hasattr(v, "confidence"):
        raise Refusal(f"{aid}: cell_map.cells_for() did not return a Verdict")
    if v.refuse:
        return None, f"cell_map refuses ({v.confidence}): {v.reason[:110]}"
    if v.confidence != "high":
        return None, (f"cell_map confidence {v.confidence!r} — catalog {v.catalog} is not the "
                      "region/delay-matched dump R1 was measured on")
    if not v.cells:
        return None, "cell_map resolved no cell — this submit would be credited nowhere"
    return set(v.cells), None


def mechanic_of(formula):
    """The alpha's signal identity. Owned by submit_rank (the set of non-carrier fields it reads)."""
    import submit_rank
    return submit_rank.mechanic_of(formula or "")


def g6_family_of(formula):
    """The key the G6 per-family/day cap will actually be taken under.

    THESE TWO KEYS DISAGREE, and the disagreement is load-bearing. harness.guards.reserve_submit
    refuses a second submit-test for the same `family` on one platform day, and `family` is whatever
    string the decisions file carries. `_famof` collapses a formula to the FIRST field token's
    prefix, so news_relevance_score_2 (News cell) and news_sentiment_score (Sentiment cell) are both
    'news' — two DIFFERENT cells that G6 will not let us fill on the same day. Write the fine
    mechanic there instead and the family cap stops binding at all.

    The plan reports the collisions rather than choosing a side, because choosing one silently is
    how a cap gets disabled or a cell gets starved without anyone reading it."""
    from harness.guards import _famof
    return _famof(formula or "")


def corr_verdict(cand):
    """BOTH prod and self must be measured numbers. None is not a pass.

    auto_submit.corr_verdict reads prod_maxcorr only; nothing on that path reads self-corr."""
    p, sc = cand.get("prod_max"), cand.get("self_corr")
    if not isinstance(p, (int, float)) or isinstance(p, bool):
        return None, f"no measured prod verdict (prod={p!r})"
    if not isinstance(sc, (int, float)) or isinstance(sc, bool):
        return None, f"no measured SELF verdict (self={sc!r}) — auto_submit would not have noticed"
    if sc >= 0.7:
        return None, f"self-corr {sc:.4f} >= 0.70"
    if p >= 0.7:
        return None, f"prod-corr {p:.4f} >= 0.70"
    return f"prod {p:.4f} / self {sc:.4f}", "ok"


# ---------------------------------------------------------------- plan

def build_plan(pieces, candidates, cells_state):
    """Return (rows, notes). Every unrecoverable disagreement raises; nothing here defaults."""
    pg = pieces["pyramid_gate"]
    counts = check_counts(cells_state)
    need = {c.category: c.needs for c in pg.priority(cells_state, max_age_s=MAX_COUNT_AGE_S)}
    if not need:
        raise Refusal("pyramid_gate.priority() returned no cells — either every cell is unlocked "
                      "or the state is untrustworthy; it does not say which, so refuse")
    notes = [f"counts {cells_state.source}, {int(cells_state.age_s)}s old; {len(need)} cells short, "
             f"{sum(need.values())} submits to unlock {SCOPE[0]} d{SCOPE[1]}"]

    by_id = {c["alpha"]: c for c in candidates}
    rows, used_mech = [], {}
    for cell in sorted(need, key=lambda c: (need[c], c)):
        ranked = pieces["submit_rank"].rank_for_cell(cell, list(by_id))
        if not ranked:
            # AN EMPTY PLAN MUST SAY WHY. "0 rows" with no reason is indistinguishable from a
            # broken wire, and on an irreversible pipeline that silence is how a dead seam survives
            # a review. submit_rank.rank() carries the per-candidate refusal codes; use them.
            detail = ""
            rankfn = getattr(pieces["submit_rank"], "rank", None)
            if callable(rankfn):
                try:
                    import collections
                    _, rej = rankfn(cell, list(by_id))
                    codes = collections.Counter(r[1] if isinstance(r, tuple) else str(r)
                                                for r in rej)
                    detail = (f"; {len(rej)} claimant(s) refused: "
                              f"{', '.join(f'{k}x{v}' for k, v in codes.most_common())}"
                              if rej else "; no candidate even CLAIMS this cell")
                except Exception as e:
                    detail = f"; (rank() diagnostics unavailable: {type(e).__name__})"
            notes.append(f"  {cell}: needs {need[cell]}, ranker returned NOTHING{detail}")
            continue
        for aid in ranked:
            if need[cell] <= 0:
                break
            cand = by_id.get(aid)
            if cand is None:
                raise Refusal(f"submit_rank returned {aid!r}, which is not a candidate — the "
                              "ranker and the pool disagree about what exists")
            if any(r["alpha"] == aid for r in rows):
                continue
            formula = (cand.get("formula") or "").strip()
            if not formula:
                notes.append(f"  skip {aid} for {cell}: no formula on record — cell_map cannot "
                             "establish a cell and auto_submit.preflight needs one")
                continue
            cells, why = check_mapping(aid, pieces["cell_map"].cells_for(
                formula, region=SCOPE[0], delay=SCOPE[1]))
            if cells is None:
                notes.append(f"  skip {aid} for {cell}: {why}")
                continue
            if cell not in cells:
                notes.append(f"  skip {aid} for {cell}: cell_map says {sorted(cells)}")
                continue
            mech = mechanic_of(formula)
            # THE WIRE auto_submit DOES NOT HAVE. Re-ask the gate about this exact cell.
            d = pg.decide(cell, cells_state, max_age_s=MAX_COUNT_AGE_S)
            if d.action != pg.SUBMIT:
                notes.append(f"  skip {aid} for {cell}: gate says {d.explain()}")
                continue
            if mech in used_mech:
                # DROP the row, do not refuse the run. Dropping already prevents the harm (a second
                # submit on one mechanic), and a whole-run refusal on a mechanic clash would let one
                # collision cost the other twelve cells. Loud, never silent.
                notes.append(f"  DROP {aid} for {cell}: shares mechanic {mech!r} with "
                             f"{used_mech[mech]}, already planned — a second submit on one "
                             "mechanic buys no cell and raises the first one's prod-corr")
                continue
            verdict, why = corr_verdict(cand)
            if verdict is None:
                notes.append(f"  skip {aid} for {cell}: {why}")
                continue
            rows.append({"cell": cell, "alpha": aid, "cells": sorted(cells), "mechanic": mech,
                         "family": g6_family_of(formula), "formula": formula, "corr": verdict,
                         "reason": f"{cell} at {counts[cell]}/{UNLOCK_AT}, needs {need[cell]}"})
            used_mech[mech] = aid
            need[cell] -= 1

    # G6 will take ONE submit-test per `family` per platform day. Rows that collide there cannot
    # both land today however different their cells are. Report it; do not silently drop a cell.
    fams = {}
    for r in rows:
        fams.setdefault(r["family"], []).append(f"{r['alpha']}({r['cell']})")
    for fam, who in fams.items():
        if len(who) > 1:
            notes.append(f"  G6 COLLISION: {', '.join(who)} all key to family {fam!r} — "
                         "harness.guards allows ONE per platform day, so these cannot all land "
                         "today even though their cells differ")
    return rows, notes


def to_decisions(rows, path):
    """Write the auto_submit decisions contract to `path`. REFUSES the real path.

    Writing state/auto_submit_decisions.json is not a report, it is ARMING: it is the only input
    `auto_submit --i-am-spending-real-submissions` reads, and a dry-run driver that writes it has
    loaded the gun it claims not to be holding."""
    import auto_submit
    if pathlib.Path(path).resolve() == pathlib.Path(auto_submit.DECISIONS).resolve():
        raise Refusal(f"refusing to write auto_submit's live decisions path ({path}) from a "
                      "dry-run driver — that would arm the irreversible tool")
    doc = {"as_of": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
           "decisions": {r["alpha"]: {"cell": r["cell"], "region": SCOPE[0], "delay": SCOPE[1],
                                      "reason": r["reason"], "formula": r["formula"],
                                      "family": r["family"]} for r in rows}}
    pathlib.Path(path).write_text(json.dumps(doc, indent=2))
    return doc


def run(candidates, *, dry_run=True, cells_state=None, decisions_path=None, out=print):
    """Wire the chain, print the plan, hand it to auto_submit in dry-run behind a dead transport."""
    if not dry_run:
        raise Refusal("submit_plan.py is a rehearsal driver and has no live mode; the irreversible "
                      "POST belongs to tools/auto_submit.py, invoked deliberately")
    if kill_engaged():
        raise Refusal("kill switch present — nothing planned")

    pieces, _ = bind()
    pg, aus = pieces["pyramid_gate"], pieces["auto_submit"]

    if cells_state is None:
        # session=False -> cache only, no network. The freshness guard then refuses it, which is
        # the honest outcome: this driver has no licence to open a socket.
        cells_state = pg.cell_state(session=False)

    rows, notes = build_plan(pieces, candidates, cells_state)

    # The crash window: auto_submit owns the intent journal, so ask IT, not a reimplementation.
    records = aus.read_journal()
    for r in list(rows):
        ok, why = aus.post_permitted(r["alpha"], records)
        if not ok:
            notes.append(f"  drop {r['alpha']}: {why}")
            rows.remove(r)

    for r in rows:
        # Re-read the kill switch HERE, per row. Read once at the top it stops nothing.
        if kill_engaged():
            r["handoff"] = "HALTED by kill switch"
            break
        r["handoff"] = "planned"

    live_rows = [r for r in rows if r.get("handoff") == "planned"]
    to_decisions(live_rows, decisions_path or SCRATCH_DECISIONS)
    aus.run({"region": SCOPE[0], "delay": SCOPE[1]}, transport=NoTransport(), live=False,
            ctx={"decisions": str(decisions_path or SCRATCH_DECISIONS)}, out=out)
    return rows, notes


# ---------------------------------------------------------------- blast radius

def blast_radius():
    """How many alphas could ONE run irreversibly spend, tier by tier. Arithmetic, not opinion."""
    import auto_submit as A
    return {
        "driver guards intact (dry run)": 0,
        "auto_submit run cap": A.MAX_ALPHAS_PER_RUN,
        "POST requests at that cap": A.MAX_ALPHAS_PER_RUN * A.MAX_ATTEMPTS_PER_ALPHA,
        "G6 ledger cap (1 POST/alpha ever, 1/family/day)": "1 per distinct family per platform day",
        "platform daily quota": A.DAILY_SUBMIT_QUOTA,
        "if every LOCAL guard fails open, platform intact":
            f"{A.DAILY_SUBMIT_QUOTA} accepted, every further POST 403s and a 403 ADJUDICATES — "
            f"so the alphas DESTROYED is the whole list handed in, not {A.DAILY_SUBMIT_QUOTA}",
    }


# RESERVE = banked, unspent. PENDING_KHOA = gate-passing but awaiting the human's authority to
# submit (submit-authority-boundary). Both are PLANNABLE; neither is submittable by this driver,
# which has no live mode. Measured 2026-08-13: every alpha whose category covers one of the six open
# USA-d1 cells is PENDING_KHOA, so a RESERVE-only pool plans nothing at all and says nothing useful.
PLANNABLE = ("RESERVE", "PENDING_KHOA")


def load_candidates():
    import csv
    path = ROOT / "state/funnel/winners.csv"
    if not path.exists():
        raise Refusal(f"no candidate ledger at {path}")
    out = []
    for row in csv.DictReader(open(path)):
        if row.get("status") not in PLANNABLE or not row.get("alpha"):
            continue
        def num(k):
            try:
                return float(row[k])
            except (KeyError, ValueError, TypeError):
                return None
        out.append({"alpha": row["alpha"], "prod_max": num("prod_max"),
                    "self_corr": num("self_corr"), "dataset": row.get("dataset") or "",
                    "formula": row.get("formula") or "", "status": row.get("status")})
    return out


def main(argv):
    if "--blast" in argv:
        for k, v in blast_radius().items():
            print(f"  {k:52} {v}")
        return 0
    rehearse = "--rehearse" in argv
    cells = None
    if rehearse:
        import pyramid_gate
        st = pyramid_gate.cell_state(session=False)
        if st.counts is None:
            print(f"\nREFUSED: no cached counts to rehearse against ({st.error})\n")
            return 2
        cells = st._replace(source="live", age_s=0.0, ts=time.time())
        print(f"\n*** REHEARSAL — counts are the {int((st.age_s or 0)/3600)}h-old CACHE relabelled "
              f"as live. NOT a submit plan. ***")
    try:
        rows, notes = run(load_candidates(), dry_run=True, cells_state=cells)
    except Refusal as e:
        print(f"\nREFUSED: {e}\n")
        return 2
    tag = "REHEARSAL (cached counts)" if rehearse else "DRY RUN"
    print(f"\n{tag} — {SCOPE[0]} delay {SCOPE[1]} — {len(rows)} row(s), 0 submits\n")
    for n in notes:
        print(f"  {n}")
    for r in rows:
        print(f"\n  {r['cell']:15} {r['alpha']:10}  cells={','.join(r['cells'])}")
        print(f"  {'':15} {'':10}  corr={r['corr']}  mechanic={r['mechanic']}")
        print(f"  {'':15} {'':10}  {r['reason']}  [{r['handoff']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
