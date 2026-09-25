"""The slot-compatibility rule: which fields may fill which slot.

RULE. Field f may fill slot $k of frame F in cell c, given the fields already chosen for other slots, iff
  1. f is in c's catalogue (fields.FieldLibrary is the authority on presence);
  2. the structural gate accepts F with $k := a field of f's type signature, every chosen slot := its
     field, and every other slot := a STAND-IN for its context, a refusal caused by a stand-in not counted:
         MATRIX -> a dense MATRIX field whose kind and unit are the marker `__standin__`
         VECTOR -> the same marker as a dense VECTOR field     GROUP -> the token industry
  3. f's record in c satisfies the slot's DECLARED constraints, when the entry declares any (a designer's
     semantic typing: allowed kind / unit / time / domain / sparsity / sign / structure / vec_role /
     crowding / category / datasets, exclude_datasets, vec_reducers_all, unit_eq = "$j"). The gate says
     what is legal; constraints say what the frame is for. Mined frames declare none.
The gate is forge.runner's structurally_ok (forge.typed.judge in structural mode), called here the way
runner.plan calls it (`structurally_ok` below; tests/test_compat.py checks the call has not drifted).

Rule 2 is the gate's own judgment, not a second copy of its rules, so it follows any change in
forge/typed.py. It is exact for one slot at a time (tests/test_compat.py; and on 21,450 real field x
single-slot-frame pairs, 2026-09-24). Joint constraints between slots (H1: add / subtract / divide /
compare need one unit) are met by conditioning each slot on the fields already chosen; the filler
re-checks every finished formula with the gate, so no formula leaves the filler unchecked.

WHY A MARKED STAND-IN. It must act like "some field" (unbounded, dense, MATRIX, never refused by a kind
rule) without imposing its unit on the probed slot: every refusal its own kind or unit causes names the
marker and is dropped (`_probe`); a refusal that survives holds for any real field in that slot.
Measured 2026-09-24 on the 134-frame scratch build (no declared constraints yet), USA/d1, seed 7, 10
fills per frame: with the constant 1 as the stand-in, 5,815 of 7,793 draws stopped at "$3: no compatible
field"; with the marked stand-in, 40 of 1,650. (The constant carries unit '*' upward, and divide(1,1) raises IndexError inside forge.typed,
which made the probe admit every signature for the earlier slot -- read from typed's code and seen in
the probe log, not separately measured per cause.)
"""
from __future__ import annotations

from forge import typed as TY

from framelib.fields import UNLABELLED, parse_cell

PROBE = "__framelib_probe__"
STAND_IN = "__framelib_standin__"
STAND_IN_VECTOR = "__framelib_standin_vec__"
MARKER = "__standin__"
NEUTRAL = {"MATRIX": STAND_IN, "GROUP": "industry", "VECTOR": STAND_IN_VECTOR}
_STAND_IN_LABELS = {
    STAND_IN: {"kind": MARKER, "unit": MARKER, "sign": "+", "domain": "probe", "time": "daily", "sparsity": "dense",
               "structure": "MATRIX", "vec_reducers": None, "vec_after": None},
    STAND_IN_VECTOR: {"kind": MARKER, "unit": MARKER, "sign": "+", "domain": "probe", "time": "daily",
                      "sparsity": "dense", "structure": "VECTOR", "vec_reducers": None, "vec_after": None},
}


CONSTRAINT_ATTR = {"kind": "kind", "unit": "unit", "time": "time", "domain": "domain", "sparsity": "sparsity",
                   "sign": "sign", "structure": "structure", "vec_role": "vec_role", "crowding": "crowding",
                   "category": "category", "datasets": "dataset"}
CONSTRAINT_KEYS = tuple(CONSTRAINT_ATTR) + ("exclude_datasets", "vec_reducers_all", "unit_eq")


def satisfies(rec: dict, cons: dict | None) -> bool:
    """Does a field record (FieldLibrary.record) meet a slot's declared constraints? unit_eq is joint and
    is checked by the filler once both slots hold a field."""
    for key, attr in CONSTRAINT_ATTR.items():
        if cons and key in cons and rec.get(attr) not in cons[key]:
            return False
    if cons and rec.get("dataset") in cons.get("exclude_datasets", ()):
        return False
    if cons and "vec_reducers_all" in cons and not set(cons["vec_reducers_all"]) <= set(rec.get("vec_reducers") or ()):
        return False
    return True


def structurally_ok(formula: str, labels: dict, region, delay) -> tuple:
    """(ok, hard reasons). Same call as forge/runner.py plan().structurally_ok."""
    v = TY.judge(formula, labels, "%s/d%s" % (region, delay), structural=True)
    return v["ok"], v["hard"]


def probe_label(sig: tuple) -> dict | None:
    """A synthetic label carrying exactly one type signature (None for UNLABELLED: an unknown field)."""
    if sig == UNLABELLED:
        return None
    structure, sparsity, kind, unit, reducers, after = sig
    return {"kind": kind, "unit": unit, "sign": "+", "domain": "probe", "time": "daily", "sparsity": sparsity,
            "structure": structure, "vec_reducers": list(reducers) if reducers else None,
            "vec_after": dict(after) if after else None}


def _fixed_labels(normal, fl, chosen) -> dict:
    out = dict(_STAND_IN_LABELS)
    for name in list(normal.cond_fields) + list(normal.pinned.values()) + list(chosen.values()):
        if name in fl.labels:
            out[name] = fl.labels[name]
    return out


def neutral_fill(normal, chosen=None, probe_slot=None) -> list:
    chosen = chosen or {}
    out = []
    for k, s in enumerate(normal.slots, 1):
        out.append(PROBE if k == probe_slot else chosen.get(k, NEUTRAL[s["context"]]))
    return out


def _probe(formula, labels, region, delay, fl) -> list:
    """The gate's refusals of a probe formula that are about the probed field, not about a stand-in (a
    refusal naming the marker is dropped; the judge collects every failure, so a genuine refusal next to
    one still counts). forge.typed raises on some all-constant sub-expressions written into a frame
    (divide(1,1): IndexError in Judge._arith, seen 2026-09-24); such a probe is counted in
    fl.memo["probe_errors"] and refuses nothing. Both rules only ever widen the admissible set; the
    filler's final gate check on the real formula decides."""
    try:
        ok, hard = structurally_ok(formula, labels, region, delay)
    except Exception as exc:  # noqa: BLE001 -- counted, and the real formula is gated later
        errs = fl.memo.setdefault("probe_errors", {})
        errs[type(exc).__name__] = errs.get(type(exc).__name__, 0) + 1
        return []
    return [] if ok else [h for h in hard if MARKER not in h and STAND_IN not in h]


def dead_reasons(normal, fl, cell) -> list:
    """The gate's genuine refusals of the frame with every slot a stand-in: non-empty = no fill can pass."""
    region, delay = parse_cell(cell)
    hard = _probe(normal.fill(neutral_fill(normal)), _fixed_labels(normal, fl, {}), region, delay, fl)
    return [h.replace(STAND_IN_VECTOR, "<VECTOR stand-in>") for h in hard]


def admissible(normal, k: int, cell: str, fl, chosen: dict | None = None) -> frozenset:
    """The type signatures the gate accepts in slot $k, given `chosen` ({slot number: field id})."""
    chosen = dict(chosen or {})
    ckey = ("admissible", normal.text, cell, k, tuple(sorted((j, fl.signature(f, cell)) for j, f in chosen.items())))
    if ckey in fl.memo:
        return fl.memo[ckey]
    base = _fixed_labels(normal, fl, chosen)
    formula = normal.fill(neutral_fill(normal, chosen, k))
    region, delay = parse_cell(cell)
    ok = set()
    for sig in fl.signatures(cell):
        labels = dict(base)
        lab = probe_label(sig)
        if lab is not None:
            labels[PROBE] = lab
        if not _probe(formula, labels, region, delay, fl):
            ok.add(sig)
    fl.memo[ckey] = frozenset(ok)
    return fl.memo[ckey]


def pool(normal, k: int, cell: str, fl, chosen: dict | None = None, constraints: dict | None = None) -> dict:
    """dataset -> sorted field ids whose signature is admissible in $k and whose record satisfies the
    slot's declared `constraints`, minus the frame's fixed fields (a fixed field in a slot would change
    the frame the formula re-frames to). Cached; do not mutate."""
    sigs = admissible(normal, k, cell, fl, chosen)
    pkey = ("pool", normal.text, cell, sigs, repr(sorted((constraints or {}).items())))
    if pkey not in fl.memo:
        fixed = set(normal.cond_fields) | set(normal.pinned.values())
        idx, out = fl.index(cell), {}
        for sig in sigs:
            for ds, ids in idx.get(sig, {}).items():
                keep = [f for f in ids if f not in fixed and (not constraints or satisfies(fl.record(f, cell), constraints))]
                if keep:
                    out.setdefault(ds, []).extend(keep)
        fl.memo[pkey] = {ds: sorted(ids) for ds, ids in sorted(out.items())}
    return fl.memo[pkey]


def compatible_fields(normal, k: int, cell: str, fl, chosen: dict | None = None, constraints: dict | None = None) -> dict:
    """dataset -> sorted field ids that may fill $k: `pool` minus the fields already chosen."""
    taken = set((chosen or {}).values())
    out = {ds: [f for f in ids if f not in taken] for ds, ids in pool(normal, k, cell, fl, chosen, constraints).items()}
    return {ds: ids for ds, ids in out.items() if ids}
