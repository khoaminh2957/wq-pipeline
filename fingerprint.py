"""[21] D2 — structural fingerprint + near-duplicate detection (STRICT).

Correlation is driven by STRUCTURE, not the PnL path. Validated on 20 re-simmed alphas
(pairwise structural-similarity vs realized PnL daily-return correlation):
  - field-family Jaccard predicts PnL corr ~0.61  (shared data fields = the dominant driver)
  - operator-multiset cosine predicts ~0.37        (similar function composition = secondary)
So we dedup on a structural SIMILARITY score, NOT a brittle exact hash. Param/horizon
(`implied_volatility_call_90` vs `_150`), neutralization (SUBINDUSTRY vs SECTOR), and
term-reorder/extra-term variants of one thesis — which carry ~0.9 PnL correlation — are
caught as near-duplicates (they hash differently but score sim≈1.0). On a real 2664-alpha pool:
the previous loose fingerprint gave 1354 distinct; this similarity dedup gives 691 clusters
(new coarse exact-hash: 1173) — stricter, not collapsed (cross-family pairs score ~0.2-0.4,
well under the 0.85 threshold; verified 0 wrongful merges across fundamental vs IV families).
"""
from __future__ import annotations
import hashlib, re, math
from collections import Counter

from operators import operators_in, fields_in

_HORIZON = re.compile(r"_\d+[a-z]?$")   # field horizon suffix: _90, _150, _60d
SIM_THRESHOLD = 0.85                     # >= combined similarity => near-duplicate (blatant variants)
W_FIELD = 0.6                            # field-family weight (dominant PnL-corr driver)
W_OPS = 0.4                              # operator-composition weight
# STRICTER containment rule (catches "same core + extra add-on fields" cousins that Jaccard misses):
# tuned on 23 re-simmed alphas — (overlap>=0.85 AND op_cos>=0.75) flags 10/10 known PnL-correlated
# top picks (PnL corr 0.68-0.94) with 0 false positives across fundamental-vs-IV families.
OVERLAP_T = 0.85                         # field-family CONTAINMENT (|A∩B|/min(|A|,|B|))
OPCOS_T = 0.75                           # operator-multiset cosine gate (prevents tiny-subset false dups)


def canon_field(tok: str) -> str:
    """collapse a parametrized field family: implied_volatility_call_90 -> implied_volatility_call."""
    return _HORIZON.sub("", tok)


def field_families(formula: str) -> frozenset:
    return frozenset(canon_field(t) for t in fields_in(formula))


def op_multiset(formula: str) -> Counter:
    return Counter(operators_in(formula))

"cosine similarity" 
def _cos(a: Counter, b: Counter) -> float:
    ks = set(a) | set(b)
    dot = sum(a[k] * b[k] for k in ks)
    na = math.sqrt(sum(v * v for v in a.values())); nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def _jac(a: frozenset, b: frozenset) -> float:
    u = a | b
    return len(a & b) / len(u) if u else 1.0


def _overlap(a: frozenset, b: frozenset) -> float:
    """Containment / overlap coefficient = |A∩B| / min(|A|,|B|). 1.0 when one field-set is a
    subset of the other ("same core bet + extra add-on fields") — which Jaccard wrongly penalizes."""
    m = min(len(a), len(b))
    return len(a & b) / m if m else 1.0


def near_duplicate(sig_a: tuple, sig_b: tuple) -> bool:
    """STRICT near-dup test. True if the two alphas are the same structural bet via EITHER:
      (1) field-family CONTAINMENT >= OVERLAP_T AND operator cosine >= OPCOS_T  (core+add-on cousins), OR
      (2) combined similarity >= SIM_THRESHOLD                                  (blatant param/horizon variants).
    """

    fa, oa = sig_a; fb, ob = sig_b
    cos = _cos(oa, ob)
    if _overlap(fa, fb) >= OVERLAP_T and cos >= OPCOS_T:
        return True
    return (W_FIELD * _jac(fa, fb) + W_OPS * cos) >= SIM_THRESHOLD


def structural_signature(formula: str) -> tuple[frozenset, Counter]:
    return (field_families(formula), op_multiset(formula))


def similarity(sig_a: tuple, sig_b: tuple) -> float:
    """Structural similarity in [0,1] — empirically predicts PnL correlation."""
    return W_FIELD * _jac(sig_a[0], sig_b[0]) + W_OPS * _cos(sig_a[1], sig_b[1])


def structural_fingerprint(formula: str, neutralization: str = "", thesis_key: str = "") -> str:
    """Coarse exact bucket hash = field-family set + operator signature. Numeric params AND
    neutralization are intentionally EXCLUDED so their variants share a bucket. Same hash =>
    certain near-dup; near-dups that differ by an extra term need the similarity check below."""
    fams, ops = structural_signature(formula)
    payload = "FAM:" + ",".join(sorted(fams)) + "|OPS:" + ",".join(f"{k}:{v}" for k, v in sorted(ops.items()))
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


class StructuralIndex:
    """Near-duplicate detector. An alpha is a dup if its structural similarity to ANY registered
    alpha >= threshold — so once one member of a structural family is seen/submitted, the rest of
    the family (e.g. Vk8kX7Xw after 9qRq6579, sim=1.00) is rejected. Backward-compat name: DupDetector."""

    def __init__(self, threshold: float = SIM_THRESHOLD):
        self.threshold = threshold
        self.seen: list[tuple[tuple, str]] = []     # (signature, label)
        self.hashes: dict[str, str] = {}            # coarse fingerprint -> label (fast exact bucket)

    def nearest(self, formula: str) -> tuple[float, str | None]:
        sig = structural_signature(formula)
        best, lab = 0.0, None
        for s, l in self.seen:
            v = similarity(sig, s)
            if v > best:
                best, lab = v, l
        return best, lab

    def is_dup(self, formula: str) -> tuple[bool, float, str | None]:
        # fast path: identical coarse fingerprint
        fp = structural_fingerprint(formula)
        if fp in self.hashes:
            return True, 1.0, self.hashes[fp]
        # STRICT containment rule against every seen alpha (catches core+add-on cousins)
        sig = structural_signature(formula)
        best, lab = 0.0, None
        dup = False
        for s, l in self.seen:
            v = similarity(sig, s)
            if v > best:
                best, lab = v, l
            if near_duplicate(sig, s):
                dup = True
                best, lab = max(best, v), l
        return dup, best, lab

    def register(self, formula: str, label: str = ""):
        self.seen.append((structural_signature(formula), label))
        self.hashes[structural_fingerprint(formula)] = label


# backward-compatible alias (older code imports DupDetector)
DupDetector = StructuralIndex
