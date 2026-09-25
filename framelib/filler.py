"""The filler: frame x compatible fields -> formulas + settings. Seeded and deterministic.

For one frame and one cell, each draw picks slot $1, $2, ... in order, each from compat.pool given the
slots already picked and the entry's declared slot constraints (by="dataset": a dataset uniformly among those that have a compatible field, then a
field uniformly within it; by="field": a field uniformly). A finished formula is kept only if
  * structurally_ok accepts it (the gate forge.runner applies before a simulation),
  * it re-frames to this frame: frames.frame_formula gives the frame's canonical key and the fill,
  * it is new within this call and not in `exclude`.
Every rejection is counted by reason. The random stream is random.Random("seed|frame text|cell"): a str
seed is hashed with SHA-512 by CPython, so the result does not depend on PYTHONHASHSEED or on the process.

Settings: region and delay come from the cell; universe, neutralization, decay and truncation from the
frame's settings block (universe is per region), overridden by `settings`. A value nobody gave stays None
and `settings_complete` is False -- the filler never invents a setting.
"""
from __future__ import annotations

import collections
import random

from framelib import compat as CM
from framelib import frames as FR
from framelib.fields import parse_cell

SETTING_KEYS = ("universe", "neutralization", "decay", "truncation")


def _settings(entry_settings: dict, region: str, delay: int, override: dict | None) -> dict:
    st = dict(entry_settings or {})
    uni = st.get("universe")
    out = {"region": region, "delay": delay, "universe": uni.get(region) if isinstance(uni, dict) else uni}
    for k in SETTING_KEYS[1:]:
        out[k] = st.get(k)
    out.update(override or {})
    return out


def _unit_eq(cons: dict, chosen: dict, fl, cell: str):
    """A declared unit_eq ("$j") between two chosen slots must hold; None when it does (or is undecided)."""
    for k, c in cons.items():
        j = int(str((c or {}).get("unit_eq", "$0"))[1:] or 0)
        if k in chosen and j in chosen and fl.record(chosen[k], cell).get("unit") != fl.record(chosen[j], cell).get("unit"):
            return "constraint unit_eq $%d = $%d" % (k, j)
    return None


def fill(entry, fl, cell: str, n: int, seed: int, *, by: str = "dataset", settings: dict | None = None,
         exclude=(), max_attempts: int | None = None) -> dict:
    """`entry`: a library entry (dict with "text", optional "settings", "id", "version") or a frame text.
    Returns {"fills": [...], "rejected": {reason: count}, "attempts": int, "dead": [reasons] or None}."""
    if by not in ("dataset", "field"):
        raise ValueError("by must be 'dataset' or 'field'")
    if isinstance(entry, str):
        entry = {"text": entry}
    normal = FR.normalize(entry["text"])
    region, delay = parse_cell(cell)
    st = _settings(entry.get("settings"), region, delay, settings)
    out = {"frame_id": entry.get("id"), "cell": cell, "seed": seed, "by": by, "fills": [],
           "rejected": collections.Counter(), "attempts": 0, "dead": None}
    present = fl.ids_in(cell)
    missing = [f for f in list(normal.cond_fields) + list(normal.pinned.values()) if f not in present]
    if missing:
        out["dead"] = ["fixed field absent in %s: %s" % (cell, ", ".join(missing))]
        return out
    dead = CM.dead_reasons(normal, fl, cell)
    if dead:
        out["dead"] = dead
        return out
    cons = {k: (s.get("constraints") or None) for k, s in enumerate(entry.get("slots") or [], 1)}
    for k in range(1, len(normal.slots) + 1):
        if not CM.pool(normal, k, cell, fl, constraints=cons.get(k)):
            out["dead"] = ["$%d admits no field present in %s%s" % (k, cell, " under its constraints" if cons.get(k) else "")]
            return out
    rng = random.Random("%s|%s|%s" % (seed, normal.text, cell))
    key_expected = normal.key
    seen, exclude = set(), set(exclude)
    budget = max_attempts if max_attempts is not None else 20 * n
    while len(out["fills"]) < n and out["attempts"] < budget:
        out["attempts"] += 1
        chosen, why = {}, None
        for k in range(1, len(normal.slots) + 1):
            p = CM.pool(normal, k, cell, fl, chosen, cons.get(k))
            if not p:
                why = "$%d: no compatible field given the earlier slots" % k
                break
            if by == "dataset":
                fid = rng.choice(p[rng.choice(sorted(p))])
            else:
                flat = fl.memo.setdefault(("flat", id(p)), [f for ids in p.values() for f in ids])
                fid = rng.choice(flat)
            if fid in chosen.values():
                why = "field repeated in two slots"
                break
            chosen[k] = fid
            why = _unit_eq(cons, chosen, fl, cell)
            if why:
                break
        if why is None:
            fields = [chosen[k] for k in range(1, len(normal.slots) + 1)]
            formula = normal.fill(fields)
            try:
                ok, hard = CM.structurally_ok(formula, fl.labels, region, delay)
            except Exception as exc:  # noqa: BLE001 -- counted as a rejection, never kept
                ok, hard = False, ["raised %s" % type(exc).__name__]
            if not ok:
                why = "gate: %s" % hard[0][:60]
            else:
                key, kfill, _ = FR.frame_formula(formula)
                if key != key_expected or kfill != normal.key_fill(fields):
                    why = "re-frames to another frame"
                elif formula in seen or formula in exclude:
                    why = "duplicate"
        if why is not None:
            out["rejected"][why] += 1
            continue
        seen.add(formula)
        out["fills"].append({"frame_id": entry.get("id"), "frame_version": entry.get("version"), "formula": formula,
                             "fill": fields, "cell": cell, "settings": dict(st),
                             "settings_complete": all(st.get(k) is not None for k in SETTING_KEYS),
                             "seed": seed, "draw": out["attempts"]})
    out["rejected"] = dict(out["rejected"])
    return out
