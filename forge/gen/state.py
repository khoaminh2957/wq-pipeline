"""forge.gen.state -- the loop's state as a pure function of what is already on disk (design §3.2).

§3.2: "The loop's state is a pure function of the journal, corr.jsonl and the submit logs, recomputed each
round (the pattern allocate.pair_states already uses), so a crash loses nothing and no new state file
exists. Its sha256 is stamped on every construction as meta.gen_state for stratification."

WHAT ENTERS, AND WHAT DOES NOT (stated against §3.2's list):
  * the journal (forge rows, latest per alpha): the posteriors (D34/D35), the family registry and the
    per-family counts (D36), the repair triggers (D37), the neighbour index (D51);
  * the submit logs (`submit.posted_history`): the accepted POSTs for plan-time D18 and the PnL stop (D36),
    read through `novelty.build`, the same projection D18 at submit reads;
  * the cached PnL curves of the accepted POSTs and of generated harvest-passes: D36's PnL stop needs them
    and §3.2's list does not name them. Named here so the input set is not silently wider than the design;
  * corr.jsonl is NOT an input: no rule ticked for this branch (D34-D38, D51) reads a PROD / SELF reading.
    The spend-stop is computed locally (§3.6: "indifferent to which" SELF mechanism).

THE SHA (meta.gen_state): sha256, 16 hex like run_config, over the DERIVED state -- the Beta counts, the
registry digest, every family's verdict, the accepted POSTs and the ones whose formula could not be read,
the PnL stops and the trigger queue with its coins. Two journals that yield the same state give the same
sha; an input that changes a draw's odds, a family verdict or the trigger queue changes it.
A LIMIT, stated (draw-5 gen N6): the D51 neighbour index (`rows_by_formula`, which also holds library rows)
is NOT hashed, so two journals that differ only in the one-setting siblings of a handed alpha give one sha
and different neighbour plans; the neighbours carry meta.neighbour_of instead.

ROUND_KEYS (architecture round 3 S15): forge/offline/recover_orphans.py's ROUND_KEYS already hold gen_state
(read 2026-09-24), so plan entries of one construction that differ in seed and gen_state match (draw-5 gen
N6: this paragraph still called it an open conflict). meta.gen_route stays in that file's identity.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

from forge.gen import families as FM
from forge.gen import posterior as PO
from forge.gen import productions as P
from forge.gen import repair as RP
from forge.gen import spend as SP


class State:
    """Everything one round needs, derived. Treated as read-only by propose()."""

    def __init__(self, rows, history, curves):
        from forge import novelty as NV
        self.rows = rows if isinstance(rows, dict) else {r["alpha"]: r for r in rows if r.get("alpha")}
        self.posterior = PO.Posterior(self.rows)
        self.families = FM.FamilyIndex.from_rows(self.rows)
        self.stats = SP.family_stats(self.rows)
        self.structures = NV.build(history, self.rows)
        self.accepted = sorted({h["alpha"] for h in history or [] if h.get("alpha") and h.get("http") in (200, 201)})
        self.stopped = SP.pnl_stops(self.rows, curves, self.accepted)
        self.triggers = RP.triggers(self.rows)
        self.rows_by_formula = {}
        for r in self.rows.values():
            if r.get("alpha") and r.get("formula"):
                self.rows_by_formula.setdefault(RP.formula_key(r), []).append(r)
        self.sha = hashlib.sha256(json.dumps(self.summary(), sort_keys=True).encode()).hexdigest()[:16]

    def verdict(self, family: str, cell: str) -> tuple:
        return SP.verdict(self.stats.get((family, cell)), family in self.stopped)

    def summary(self) -> dict:
        verdicts = {"%s|%s" % k: list(self.verdict(*k)) for k in sorted(self.stats)}
        for fam in sorted(self.stopped):
            verdicts.setdefault("%s|*" % fam, ["PNL_STOP", 0])
        return {"posterior": self.posterior.as_json(), "registry": self.families.digest(),
                "families": len(self.families.families), "verdicts": verdicts, "accepted": self.accepted,
                "unreadable_posts": list(self.structures.missing), "pnl_stops": self.stopped,
                "triggers": [[P.formula_sha(r["formula"]), RP.coin(r["formula"])] for r in self.triggers]}


def build(rows, history=(), curves=None) -> State:
    """The state from journal rows ({alpha: latest row} or a list), submit-log history
    (`submit.posted_history` rows) and {alpha: cached cumulative curve}."""
    return State(rows, list(history or ()), curves or {})


def load(root) -> State:
    """READ-ONLY: the journal, both submit logs and the cached curves under `root`. Writes nothing."""
    from forge import harvest as HV
    from forge import submit as SUB
    root = pathlib.Path(root)
    rows = HV.forge_rows(root / "state/layered/runs/forge.jsonl")
    history = SUB.posted_history(paths=(root / "state/forge/submitted.jsonl", root / "state/climb/submitted.jsonl"))
    want = {h["alpha"] for h in history if h.get("alpha") and h.get("http") in (200, 201)}
    want |= {a for a, r in rows.items() if PO.is_generated(r) and PO.harvest_pass(r)}
    curves = {}
    for a in sorted(want):
        c = HV.cached_curve(a, root / "state/pnl_curves")
        if c:
            curves[a] = c
    return build(rows, history, curves)
