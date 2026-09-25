"""What the platform accepts for USA/TOP3000/d1: the datasets it offers TODAY, and the (field, operator) inputs
it has REJECTED with "Incompatible unit".

DATASETS. WHY (00_decisions.md, round 1 attempt 1, 2026-09-24 17:38). The catalogue snapshot under fetched/rc/fields
listed fields the platform no longer offers for this setting (fundamental65, ml_factor_proj): children
failed "Invalid data field" / "unknown variable", and one invalid child cancelled its whole multisim
parent. The fix that ran in R1B and R2 is round1.restrict: drop every catalogue field whose dataset is not
in GET /data-sets for USA/TOP3000/d1 today. This module applies exactly that, from the file the loop
driver refreshes once per ET day:

    state/frames/datasets_ok.json     a JSON list of dataset ids (the same form as R1B's
                                      datasets_usa_top3000_d1.json, 293 ids on 2026-09-24)

A missing, unreadable or empty file is an error, never "no pruning": planning on the unpruned
snapshot is the attempt-1 failure. How old the file may be is not decided here; its ET day is reported.

UNIT BLACKLIST. state/frames/unit_blacklist.json, rebuilt from the frames journals by refresh_unit_blacklist
(framelib.loop.plan calls it every round) and read by load_unit_blacklist (the planner, and any module that wants
it). An ERROR row whose message reads `Incompatible unit for input of "OP" at index I` names an operator and an
input position, not a field. The field is attributed as follows (DESIGN CHOICE):
  * candidates: every field written DIRECTLY as positional argument I of a call of OP in that formula (a
    sub-expression at I names no single field: the row is reported "unattributed", nothing is blacklisted);
  * a candidate (OP, field) seen as a direct positional input of OP in a SCORED row (COMPLETE / WARNING) of any
    of these journals was accepted there, so it is not blamed;
  * every candidate left is blacklisted as (field, OP), for every index (the key is (field, operator)). More
    than one left is "ambiguous": they are all blacklisted, since one invalid child cancels its whole parent
    of 10 (00_decisions.md, round 1 attempt 1) and losing a (field, operator) input costs one input.
The file is PERSISTENT: an entry, once written, is never removed by a later refresh, so an entry learned from a
journal that is later rotated away still holds. A WARNING row carrying "Incompatible unit" was simulated and
scored (the platform warned); it is not a rejection and blacklists nothing.
POST-HOC, 2026-09-25 (FRAMES-R1B + FRAMES-R2 journals): 24 ERROR rows read "Incompatible unit", every one of them
`found "Unit[Group:1]"`; 78 scored WARNING rows carry the same phrase with other units. Why a Group unit is
refused as a numeric input: MECHANISM: UNKNOWN (the message is the platform's; no experiment separated causes).
"""
from __future__ import annotations

import json
import os
import pathlib
import re

from forge import typed as TY
from framelib.experiments import round1 as R1

ROOT = pathlib.Path(__file__).resolve().parents[2]
PATH = ROOT / "state/frames/datasets_ok.json"
UNIT_BLACKLIST = ROOT / "state/frames/unit_blacklist.json"
#: the frames journals under state/layered/runs, R1 attempt 1 included (its rows are the platform's answers too)
JOURNALS = ("frames_loop", "frames_r1", "frames_r1b", "frames_r2")
UNIT_ERROR = re.compile(r'Incompatible unit for input of "([A-Za-z_][A-Za-z0-9_]*)" at index (\d+)')
SCORED = ("COMPLETE", "WARNING")
UNIT_RULE = ("(field, operator) pairs the platform rejected with 'Incompatible unit' (status ERROR); attribution "
             "and persistence: framelib/loop/availability.py")


class AvailabilityError(ValueError):
    pass


def load(path=PATH) -> set:
    """The dataset ids offered today. Raises AvailabilityError when the file cannot be used."""
    p = pathlib.Path(path)
    if not p.exists():
        raise AvailabilityError("%s missing: refusing to plan on the unpruned catalogue (round 1 attempt 1)" % p)
    try:
        ids = json.loads(p.read_text())
    except ValueError as exc:
        raise AvailabilityError("%s is not JSON: %s" % (p, exc)) from None
    if not isinstance(ids, list) or not ids or not all(isinstance(x, str) and x for x in ids):
        raise AvailabilityError("%s must be a non-empty JSON list of dataset ids" % p)
    return set(ids)


def prune(fl, path=PATH) -> dict:
    """Prune `fl` (a framelib.fields.FieldLibrary) in place to today's datasets, as round1.restrict does."""
    from forge import submit as FS          # quota_day: the ET day, one definition
    ok = load(path)
    removed = R1.restrict(fl, ok, None)
    return {"path": str(path), "datasets": len(ok), "removed": removed,
            "file_et_day": FS.quota_day(os.path.getmtime(path))}


# ---- the unit blacklist ----------------------------------------------------------------------------------------

def direct_inputs(formula: str) -> set:
    """{(operator, positional index, field)} for every field written directly as a positional argument of a call.
    Group tokens (forge.typed.GROUPS) are not fields. Raises ValueError when the formula does not parse."""
    out = set()

    def walk(n):
        if n.op is None:
            return
        for i, a in enumerate(n.args):
            if a.op is None and a.name is not None and a.name not in TY.GROUPS:
                out.add((n.op, i, a.name))
            walk(a)
        for v in n.kw.values():
            walk(v)
    walk(TY.parse(formula))
    return out


def _rows(path, needle):
    """The JSON rows of a journal whose raw line contains `needle` (a cheap filter before json.loads)."""
    p = pathlib.Path(path)
    if not p.exists():
        return
    with open(p, errors="replace") as fh:
        for line in fh:
            if needle(line):
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    yield r


def learn_unit_blacklist(paths) -> dict:
    """{"pairs": {(field, operator): {"indices", "rows", "attribution", "example", "journal"}},
    "unattributed": [{"operator", "index", "formula", "reason", "journal"}]} from the journals `paths`."""
    errors = []
    for p in paths:
        for r in _rows(p, lambda line: "Incompatible unit" in line):
            m = UNIT_ERROR.search(str(r.get("message") or ""))
            if r.get("status") == "ERROR" and m and r.get("formula"):
                errors.append((m.group(1), int(m.group(2)), r["formula"], pathlib.Path(p).stem))
    cands, unattributed = [], []
    for op, idx, formula, src in errors:
        try:
            di = direct_inputs(formula)
        except ValueError as exc:
            unattributed.append({"operator": op, "index": idx, "formula": formula, "journal": src,
                                 "reason": "formula does not parse: %s" % str(exc)[:80]})
            continue
        fs = sorted({f for o, i, f in di if o == op and i == idx})
        if not fs:
            unattributed.append({"operator": op, "index": idx, "formula": formula, "journal": src,
                                 "reason": "no field written directly at that index"})
            continue
        cands.append((op, idx, formula, src, fs))
    names = {f for c in cands for f in c[4]}
    accepted = set()
    if names:
        for p in paths:
            for r in _rows(p, lambda line: any(f in line for f in names)):
                if r.get("status") in SCORED and r.get("formula"):
                    try:
                        di = direct_inputs(r["formula"])
                    except ValueError:
                        continue
                    accepted.update((f, o) for o, _i, f in di if f in names)
    pairs = {}
    for op, idx, formula, src, fs in cands:
        left = [f for f in fs if (f, op) not in accepted]
        if not left:
            unattributed.append({"operator": op, "index": idx, "formula": formula, "journal": src,
                                 "reason": "every candidate %s was accepted by %s in a scored row" % (fs, op)})
            continue
        for f in left:
            e = pairs.setdefault((f, op), {"indices": set(), "rows": 0, "attribution": "ambiguous",
                                           "example": formula, "journal": src})
            e["indices"].add(idx)
            e["rows"] += 1
            if len(left) == 1:
                e["attribution"] = "unique"
    return {"pairs": pairs, "unattributed": unattributed}


def _read_blacklist(path) -> dict:
    p = pathlib.Path(path)
    if not p.exists():
        return {"pairs": []}
    try:
        j = json.loads(p.read_text())
    except ValueError as exc:
        raise AvailabilityError("%s is not JSON: %s" % (p, exc)) from None
    if not isinstance(j, dict) or not isinstance(j.get("pairs"), list) or not all(
            isinstance(e, dict) and isinstance(e.get("field"), str) and isinstance(e.get("operator"), str)
            for e in j["pairs"]):
        raise AvailabilityError("%s: 'pairs' must be a list of {field, operator, ...}" % p)
    return j


def load_unit_blacklist(path=UNIT_BLACKLIST) -> frozenset:
    """{(field, operator)} never to be planned. A missing file = nothing learned yet; an unreadable one raises."""
    return frozenset((e["field"], e["operator"]) for e in _read_blacklist(path)["pairs"])


def refresh_unit_blacklist(state, path=UNIT_BLACKLIST) -> dict:
    """Learn from the frames journals under `state`/layered/runs, merge into `path` (never dropping an entry),
    write it when it changed. Returns {"pairs", "new", "unattributed", "journals"}."""
    runs = pathlib.Path(state) / "layered" / "runs"
    paths = [runs / ("%s.jsonl" % j) for j in JOURNALS]
    got = learn_unit_blacklist(paths)
    old = {(e["field"], e["operator"]): e for e in _read_blacklist(path)["pairs"]}
    merged = {k: dict(v) for k, v in old.items()}
    for (f, op), e in got["pairs"].items():
        m = merged.setdefault((f, op), {"field": f, "operator": op, "indices": [], "rows": 0,
                                        "attribution": e["attribution"], "example": e["example"],
                                        "journal": e["journal"]})
        m["indices"] = sorted(set(m.get("indices") or ()) | e["indices"])
        m["rows"] = max(int(m.get("rows") or 0), e["rows"])
        if e["attribution"] == "unique":
            m["attribution"] = "unique"
    doc = {"version": 1, "rule": UNIT_RULE, "pairs": [merged[k] for k in sorted(merged, key=lambda k: (k[1], k[0]))],
           "unattributed": got["unattributed"]}
    text = json.dumps(doc, indent=1, sort_keys=True) + "\n"
    p = pathlib.Path(path)
    if not p.exists() or p.read_text() != text:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(text)
        os.replace(tmp, p)
    return {"path": str(p), "pairs": len(merged), "new": len(set(merged) - set(old)),
            "unattributed": len(got["unattributed"]), "journals": [str(x) for x in paths if x.exists()]}


def blocked(formula: str, blacklist) -> list:
    """The blacklisted (field, operator) inputs written directly in `formula` ([] when none, or no blacklist)."""
    if not blacklist:
        return []
    return sorted({(f, o) for o, _i, f in direct_inputs(formula) if (f, o) in blacklist})
