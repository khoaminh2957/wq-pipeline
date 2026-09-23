"""forge.novelty — the structural no-repeat rule on the SUBMIT path.

Khoa 2026-09-22 (agreements D18): "ko tái sử dụng các cấu trúc các alpha (field + cách sài hàm
giống) đã được nộp", and: use the fingerprint he already built. This module is the wiring between
that instrument and `forge.submit`; it adds no similarity mathematics of its own.

WHAT ALREADY EXISTS BESIDE IT (RULE 2 gate 5 -- named, because the first version of this file did
not and three auditors called it). `forge.signature.NoveltyIndex`, built by `forge.runner:58` from
`fetched/rc/active_book.json`, is a PRE-SIMULATION gate: an EXACT match on the coarse key
`datasets|families#cell`, asked before a candidate is simulated. This module is a SUBMIT-time gate
on a FUZZY key (field-family Jaccard + operator-multiset cosine). They do not overlap and neither
subsumes the other: the pre-sim gate stops a construction whose dataset/family/cell triple is
already in the book, this one stops a construction that merely PRODUCES the same book. The class
here is deliberately NOT called NoveltyIndex, so that the two never read as one thing.

WHAT THE INSTRUMENT MEASURES (root `fingerprint.py`, Khoa's, not vendored and not modified): on a
2,664-alpha pool, field-family Jaccard predicts realised PnL correlation ~0.61 and operator-multiset
cosine ~0.37, tuned on 20 and then 23 re-simulated alphas. POST-HOC on that pool; MECHANISM of why
field families track PnL correlation: UNKNOWN.

WHERE THE FORMULAS COME FROM, and why this changed. The first version read the formula out of the
journal only, and was wrong in production: of the four accepted POSTs `submit.posted_history` sees,
`mL516W9W` (climb era, 2026-08-14) has no journal row, so the index was permanently incomplete and
the fail-closed branch would have held every candidate forever. MEASURED 2026-09-22 on the VPS. The
submit-log row the same function already reads carries `formula` itself, so that is the first source
and the journal is the fallback.

WHY IT STILL FAILS CLOSED. An index that could not read a submission does not mean "everything is
novel", it means novelty is unknown, and a submission slot is one of four in a day. Both sides fail
closed: an unreadable SUBMISSION holds the round, and an unreadable CANDIDATE is held too -- a
candidate we cannot fingerprint is a candidate we cannot clear.

WHAT THIS MODULE CANNOT SEE. `posted_history` reads local logs. A POST accepted by the platform but
absent from both logs is invisible here, and the earlier code review measured exactly that case
(three 403s reading ALREADY_SUBMITTED for a first POST no local ledger holds). This gate is
therefore a floor, not a proof.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    import fingerprint as FP           # Khoa's instrument, repo root
except ImportError as exc:             # pragma: no cover -- exercised on a machine missing the file
    raise ImportError(
        "forge.novelty needs the repo-root modules 'fingerprint' and 'operators'. MEASURED "
        "2026-09-22: neither exists under /opt/wq, so importing this module there raised "
        "ModuleNotFoundError inside forge/submit.py and killed every submit invocation while "
        "vps/forge_loop.sh swallowed the traceback. Deploy them (tools/deploy.py ships both) "
        "before importing this. Original error: %s" % exc) from exc


class SubmittedStructures:
    """Every structural family already POSTed, and the submissions whose formula could not be read."""

    def __init__(self, index, missing):
        self.index = index
        self.missing = list(missing)

    @property
    def complete(self) -> bool:
        return not self.missing

    def __len__(self) -> int:
        return len(self.index.seen)

    def verdict(self, formula: str):
        """(is_repeat, similarity, twin) for one candidate.

        `similarity` is the highest structural similarity to any registered submission and is
        reported even when the verdict is False, so a 0.83 near-miss is visible in the log.
        A missing formula is NOT "novel": it returns is_repeat=None, which the caller must hold on.
        """
        if not formula:
            return None, 0.0, None
        is_dup, score, twin = self.index.is_dup(formula)
        return bool(is_dup), float(score), twin

    def register(self, formula: str, alpha: str) -> bool:
        """Add a just-accepted POST so the NEXT pick in the same invocation sees it.

        The diversity rule needed exactly this fix (code review F4, 2026-09-09): a rule evaluated
        once per invocation lets two members of one family POST in the same run. Returns False when
        there is no formula to register, which the caller must treat as a reason to stop.
        """
        if not formula:
            return False
        self.index.register(formula, alpha)
        return True


def formula_of(alpha: str, history_by_alpha: dict, rows: dict):
    """The formula of a submitted alpha: the submit-log row first, the journal second.

    The submit log is authoritative because it is written AT the POST and carries the exact string
    that was submitted; the journal is a fallback for rows the log predates.
    """
    h = (history_by_alpha or {}).get(alpha) or {}
    if h.get("formula"):
        return h["formula"]
    return ((rows or {}).get(alpha) or {}).get("formula") or None


def build(history, rows) -> SubmittedStructures:
    """Register every ACCEPTED POST's structure.

    history: `submit.posted_history()` rows -- {alpha, http, formula, ...}. Only http 200/201 count
             as submitted; a 403 was refused, not submitted, and an http of None is an outcome
             nobody recorded. Both are left out here and both are policy questions for Khoa, not
             facts this module may decide (audit 2026-09-22).
    rows:    {alpha id: journal row}, the fallback source for a formula.
    """
    by_alpha = {}
    for h in history or []:
        a = h.get("alpha")
        if a and h.get("http") in (200, 201) and a not in by_alpha:
            by_alpha[a] = h
    index = FP.StructuralIndex()
    missing = []
    for alpha in by_alpha:
        f = formula_of(alpha, by_alpha, rows)
        if not f:
            missing.append(alpha)
            continue
        index.register(f, alpha)
    return SubmittedStructures(index, sorted(missing))
