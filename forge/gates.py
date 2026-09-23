"""forge.gates — pre-simulation gates (design §4): novelty (hard, C12), duplicate, operator cap,
daily budget. Post-simulation gates live in forge.score."""
from __future__ import annotations

import glob
import json
import re

from forge.factory import MAX_OPS, candidate_id, op_count

OK = "ok"
NOT_NOVEL = "not-novel"
DUPLICATE = "duplicate"
TOO_MANY_OPS = "too-many-ops"
BUDGET = "budget"


def journal_ids(paths) -> set:
    """candidate ids of everything already simulated (formula + segment settings), from journal files."""
    seen = set()
    for pattern in paths:
        for p in glob.glob(str(pattern)):
            with open(p) as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    f, st = r.get("formula"), r.get("settings")
                    if f and isinstance(st, dict):
                        seen.add(candidate_id(f, st))
    return seen


class PreSimGate:
    def __init__(self, novelty, seen_ids=(), budget: int = 10 ** 9):
        self.novelty = novelty
        self.seen = set(seen_ids)
        self.budget = int(budget)
        self.counts = {OK: 0, NOT_NOVEL: 0, DUPLICATE: 0, TOO_MANY_OPS: 0, BUDGET: 0}

    def check(self, cand: dict) -> str:
        """Returns a verdict; on OK the candidate is charged to the budget and marked seen."""
        verdict = self._verdict(cand)
        self.counts[verdict] += 1
        if verdict == OK:
            self.budget -= 1
            self.seen.add(cand["id"])
        return verdict

    def _verdict(self, cand):
        if self.budget <= 0:
            return BUDGET
        if op_count(cand["formula"]) > MAX_OPS:
            return TOO_MANY_OPS
        if cand["id"] in self.seen:
            return DUPLICATE
        if not self.novelty.is_novel(cand["signature"]):
            return NOT_NOVEL
        return OK

    def filter(self, cands) -> list:
        return [c for c in cands if self.check(c) == OK]
