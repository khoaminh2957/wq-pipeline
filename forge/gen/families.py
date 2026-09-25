"""forge.gen.families -- the unit every spending rule and the DSR pool key on (design §3.3; D36, D38).

A family is Khoa's fingerprint family (D18: root fingerprint.py, "which he asked me to find rather than
invent a rule"). A new candidate joins the NEAREST registered family when fingerprint's near-duplicate test
fires against one of its members, else it founds a family of its own. Its hypothesis is then
`gen:<family>`, so harvest.pool_key gives the ticked DSR pool, family x cell x category (D38), and every
rule keyed on the hypothesis sees a stable key.

THE REGISTRY is a pure function of the journal: every generated row's formula under the family its own
meta.hypothesis names -- the family assigned when it was planned, never re-derived, so a later member
cannot move an old row to another family. Candidates accepted earlier in the same round are registered
as they are made, so a round cannot found one family twice.

"NEAREST". `StructuralIndex.is_dup` decides WHETHER a candidate is a near-duplicate; its returned label is
whichever member last moved it in the loop (read from fingerprint.py): a near-duplicate member always sets
it, and so does a later member with a higher similarity than any before it, near-duplicate or not. So the
label need not be a near-duplicate, nor the nearest one; on the exact-fingerprint fast path it is the LAST
member registered under that fingerprint (draw-5 gen N6 corrected "the last matching member"). This index
therefore calls fingerprint's own `near_duplicate` and `similarity` per member and takes the most similar
member that is a near-duplicate, the earliest registered on a tie (the fast path here keeps the FIRST
family registered under a fingerprint). It adds no similarity mathematics of its own.

TWO EXACT SHORTCUTS, stated so they can be checked. `near_duplicate` fires on field-family containment
>= 0.85 (with cosine >= 0.75) or on 0.6 x Jaccard + 0.4 x cosine >= 0.85, which needs Jaccard >= 0.75; and
Jaccard <= containment. So a near-duplicate always has containment >= CONTAINMENT_MIN = 0.75:
  * only members sharing a field family with the candidate can have it (plus members with no field family,
    against which fingerprint's `_overlap` reads 1.0; a candidate with no field family is compared with
    every member);
  * a member under 0.75 containment is skipped before fingerprint is asked.
Both are necessary conditions only; every verdict is still fingerprint's `near_duplicate`, and
forge/tests/test_gen_families.py holds this index equal to StructuralIndex.is_dup on every pair it draws.

KNOWN LIMIT, POST-HOC (§3.3): fingerprint and PnL disagree on 126 of 666 pass pairs (91 PnL >= 0.70 but
not near-duplicates, 35 near-duplicates under 0.70). The family is Khoa's rule; the PnL stop in
forge/gen/spend.py is the ticked complement for the first kind. MECHANISM of the disagreement: UNKNOWN.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import fingerprint as FP  # noqa: E402  -- Khoa's instrument, repository root (tools/deploy.py ships it)

PREFIX = "gen:"
#: A necessary condition of fingerprint.near_duplicate (module text): containment below it cannot fire.
CONTAINMENT_MIN = 0.75


def family_id(formula: str) -> str:
    """A founded family's id: 12 hex of sha256 over the founding formula without whitespace. Deterministic
    given the formula; the founding formula cannot be founded twice (it is a near-duplicate of itself)."""
    return hashlib.sha256("".join((formula or "").split()).encode()).hexdigest()[:12]


def family_of(row) -> str | None:
    """The family a journal row was planned into, from meta.hypothesis; None for a non-generated row."""
    h = str((row.get("meta") or {}).get("hypothesis") or "")
    return h[len(PREFIX):] if h.startswith(PREFIX) and len(h) > len(PREFIX) else None


class FamilyIndex:
    """Registered formulas and their families, with fingerprint's near-duplicate rule."""

    def __init__(self):
        self._members = []            # (signature, family, coarse fingerprint), registration order
        self._by_field = {}           # field family -> member positions
        self._fieldless = []          # members with no field family
        self._hashes = {}             # coarse fingerprint -> first family registered under it
        self._formulas = set()        # whitespace-free formulas already registered
        self.families = {}            # family -> member count

    @classmethod
    def from_rows(cls, rows):
        """The registry from journal rows, in journal order: each generated row's formula, once."""
        idx = cls()
        for r in (rows.values() if isinstance(rows, dict) else rows):
            fam = family_of(r)
            if fam and r.get("formula"):
                idx.add(r["formula"], fam)
        return idx

    def copy(self) -> "FamilyIndex":
        """An independent copy, so a round can register its own candidates without touching the state."""
        new = FamilyIndex()
        new._members = list(self._members)
        new._by_field = {k: list(v) for k, v in self._by_field.items()}
        new._fieldless = list(self._fieldless)
        new._hashes = dict(self._hashes)
        new._formulas = set(self._formulas)
        new.families = dict(self.families)
        return new

    def add(self, formula: str, family: str) -> None:
        key = "".join(formula.split())
        if key in self._formulas:
            return
        self._formulas.add(key)
        sig = FP.structural_signature(formula)
        pos = len(self._members)
        fp = FP.structural_fingerprint(formula)
        self._members.append((sig, family, fp))
        if sig[0]:
            for f in sig[0]:
                self._by_field.setdefault(f, []).append(pos)
        else:
            self._fieldless.append(pos)
        self._hashes.setdefault(fp, family)
        self.families[family] = self.families.get(family, 0) + 1

    def _peers(self, sig) -> list:
        if not sig[0]:
            return range(len(self._members))
        pos = set(self._fieldless)
        for f in sig[0]:
            pos.update(self._by_field.get(f, ()))
        return sorted(pos)

    def nearest(self, formula: str) -> tuple:
        """(family, similarity) of the most similar near-duplicate member (earliest on a tie), or (None, None)."""
        sig = FP.structural_signature(formula)
        fa = sig[0]
        best, fam = -1.0, None
        for pos in self._peers(sig):
            s, f, _ = self._members[pos]
            fb = s[0]
            if fa and fb and len(fa & fb) < CONTAINMENT_MIN * min(len(fa), len(fb)):
                continue
            if FP.near_duplicate(sig, s):
                v = FP.similarity(sig, s)
                if v > best:
                    best, fam = v, f
        if fam is None:
            hit = self._hashes.get(FP.structural_fingerprint(formula))
            if hit is not None:                  # StructuralIndex's exact-bucket path (identical signature)
                return hit, 1.0
            return None, None
        return fam, best

    def assign(self, formula: str) -> tuple:
        """(family, founded?) for a candidate. Does not register it: call add() once it is accepted."""
        fam, _ = self.nearest(formula)
        if fam is not None:
            return fam, False
        return family_id(formula), True

    def __len__(self) -> int:
        return len(self._members)

    def digest(self) -> str:
        """sha256 (16 hex) over the registered (formula signature hash, family) pairs, in order."""
        h = hashlib.sha256()
        for _, fam, fp in self._members:
            h.update(("%s|%s\n" % (fp, fam)).encode())
        return h.hexdigest()[:16]
