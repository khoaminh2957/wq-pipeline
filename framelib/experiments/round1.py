"""Live round 1 of Khoa's frame-library hypothesis: build the plan for arms a, b, c (docs/frames/00_decisions.md F1).

Arm d (the current generator) is planned ON THE VPS by the incumbent's own planner (vps side: frames_round.sh),
so this file writes arms a-c only. Nothing here simulates or talks to the network (RULE 1).

    python3 -B framelib/experiments/round1.py --seed 20260924 --per-arm 320 --out <plan.json>

ARMS (F1, sizes from docs/frames/10_frames_discovery.md §6):
  a  library frame x fields from the frame's OWN role, unseen with that frame:
       mined frame -> each slot restricted to the datasets its historical fills used in that slot, and at
                      least one slot holds a field that slot never held (all-new preferred);
       novel frame -> the designer's declared slot constraints (the filler applies them).
  b  library frame x fields of an admissible kind from OTHER datasets:
       mined frame -> each slot excludes the datasets its historical fills used there;
       novel frame -> declared constraints dropped, except that datasets the designer listed are excluded
                      (a novel frame has no history, so "other" can only mean "not what it was written for").
  c  a NON-library mined frame x the SAME fields and settings as one arm-b alpha (paired), so a vs b vs c can
     separate "the frame" from "the fields" (Q1, Q2 of §6).
Settings for a, b, c: one draw per alpha from the same grid (neutralization x decay, truncation 0.08); a c alpha
copies its b partner's settings. EX-ANTE choice, stated so nothing about settings differs by arm.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from framelib import compat as CM          # noqa: E402
from framelib import filler as FI          # noqa: E402
from framelib import frames as FR          # noqa: E402
from framelib import store                 # noqa: E402
from framelib.fields import FieldLibrary   # noqa: E402

CELL = "USA/d1"
EXPERIMENT = "FRAMES-R1"
BASE = {"instrumentType": "EQUITY", "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
        "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF", "maxPosition": "OFF",
        "region": "USA", "universe": "TOP3000", "delay": 1}
GRID = [(n, d) for n in ("INDUSTRY", "SUBINDUSTRY", "STATISTICAL") for d in (4, 8)]
TRUNCATION = 0.08
import os  # noqa: E402
#: the canonical corpus (phase A); FRAMES_CANONICAL overrides it (a cloud session unpacks the data bundle elsewhere)
CANONICAL = pathlib.Path(os.environ.get("FRAMES_CANONICAL") or
                         "/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/"
                         "822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad/frames/canonical/rows_framed.jsonl")


def history(path=CANONICAL, cell=("USA", 1, "TOP3000")) -> dict:
    """frame_key -> {"slot_ds": [set of datasets per slot], "slot_fields": [set per slot], "formulas": set}.
    USA/d1/TOP3000 rows only: the arms run there, and the discovery measured there."""
    out = {}
    with open(path) as fh:
        for line in fh:
            r = json.loads(line)
            if (r.get("region"), r.get("delay"), r.get("universe")) != cell:
                continue
            h = out.setdefault(r["frame_key"], {"slot_ds": [], "slot_fields": [], "fills": set()})
            fill = list(r.get("fill") or [])
            types = r.get("fill_types") or r.get("slot_types") or []
            while len(h["slot_ds"]) < len(fill):
                h["slot_ds"].append(set())
                h["slot_fields"].append(set())
            for i, f in enumerate(fill):
                h["slot_fields"][i].add(f)
                ds = None
                if i < len(types) and isinstance(types[i], dict):
                    ds = types[i].get("dataset")
                if ds:
                    h["slot_ds"][i].add(ds)
            h["fills"].add(tuple(fill))
    return out


def _dataset(fl, fid):
    rec = fl.record(fid, CELL) or {}
    return rec.get("dataset")


def _settings(rng) -> dict:
    n, d = rng.choice(GRID)
    s = dict(BASE)
    s.update({"neutralization": n, "decay": d, "truncation": TRUNCATION})
    return s


def _entry_with(entry: dict, per_slot: list) -> dict:
    """A copy of `entry` whose slot k carries constraints per_slot[k-1] (None = no constraint)."""
    e = dict(entry)
    n = len(FR.normalize(entry["text"]).slots)
    slots = [dict(s) for s in (entry.get("slots") or [{} for _ in range(n)])]
    while len(slots) < n:
        slots.append({})
    for k in range(n):
        slots[k]["constraints"] = per_slot[k]
    e["slots"] = slots
    return e


def arm_entries(entry: dict, fl, hist: dict) -> tuple:
    """(entry for arm a, entry for arm b, note) for one library entry."""
    n = len(FR.normalize(entry["text"]).slots)
    declared = [((entry.get("slots") or [{}] * n)[k] or {}).get("constraints") if k < len(entry.get("slots") or []) else None
                for k in range(n)]
    origin = ((entry.get("provenance") or {}).get("origin"))
    h = hist.get(entry.get("canonical_key") or "")
    if origin == "mined" and h and len(h["slot_ds"]) == n and all(h["slot_ds"]):
        a = _entry_with(entry, [{"datasets": sorted(h["slot_ds"][k])} for k in range(n)])
        b = _entry_with(entry, [{"exclude_datasets": sorted(h["slot_ds"][k])} for k in range(n)])
        return a, b, "mined: own datasets vs other datasets"
    # novel (or a mined frame whose history has no dataset per slot): declared constraints define the role
    a = entry
    b = _entry_with(entry, [({"exclude_datasets": sorted(c["datasets"])} if c and c.get("datasets") else None)
                            for c in declared])
    return a, b, "novel: declared constraints vs dropped" if origin != "mined" else "mined without slot history"


def _unseen(fill: list, h: dict | None) -> int:
    """How many slots hold a field that slot never held with this frame (0 when there is no history)."""
    if not h:
        return len(fill)
    return sum(1 for i, f in enumerate(fill) if i >= len(h["slot_fields"]) or f not in h["slot_fields"][i])


def restrict(fl, datasets_ok=None, fields_ok=None) -> dict:
    """Prune the field library to what the platform offers TODAY (round 1, 17:38: "Invalid data field" /
    "unknown variable" for fields the catalogue snapshot lists; one invalid child cancels its multisim
    parent). `datasets_ok`: dataset ids from GET /data-sets for USA/TOP3000/d1; `fields_ok`: field ids from
    GET /data-fields?dataset.id=... for the same setting. Returns counts removed."""
    cat = fl.catalogue.get(CELL, {})
    removed = {"dataset": 0, "field": 0}
    for fid in list(cat):
        if datasets_ok is not None and cat[fid].get("dataset") not in datasets_ok:
            del cat[fid]
            removed["dataset"] += 1
        elif fields_ok is not None and fid not in fields_ok:
            del cat[fid]
            removed["field"] += 1
    fl._index = {}
    fl.memo.clear()
    return removed


def build(seed: int, per_arm: int, library=None, fl=None, hist=None, nonlib_min_fills=4,
          datasets_ok=None, fields_ok=None) -> dict:
    rng = random.Random("frames-r1|%d" % seed)
    entries = library if library is not None else store.load()
    fl = fl or FieldLibrary.build(cells={CELL})
    pruned = restrict(fl, datasets_ok, fields_ok) if (datasets_ok is not None or fields_ok is not None) else None
    hist = hist if hist is not None else history()
    lib_keys = {e.get("canonical_key") for e in entries}
    quotas = [per_arm // len(entries) + (1 if i < per_arm % len(entries) else 0) for i in range(len(entries))]
    order = list(range(len(entries)))
    rng.shuffle(order)
    arms = {"a": [], "b": []}
    report = {"per_frame": {}, "dead": {}, "short": {}, "pruned": pruned}
    for i in order:
        e = entries[i]
        ea, eb, note = arm_entries(e, fl, hist)
        h = hist.get(e.get("canonical_key") or "")
        for arm, ent in (("a", ea), ("b", eb)):
            want = quotas[i]
            res = FI.fill(ent, fl, CELL, n=6 * want + 6, seed=seed, by="dataset",
                          exclude={FR.normalize(e["text"]).fill(list(f)) for f in (h["fills"] if h else ())})
            if res["dead"]:
                report["dead"].setdefault(arm, {})[e["id"]] = res["dead"]
                continue
            fills = res["fills"]
            if arm == "a" and h:
                fills = sorted(fills, key=lambda x: -_unseen(x["fill"], h))
                fills = [x for x in fills if _unseen(x["fill"], h) >= 1]
            picked = fills[:want]
            if len(picked) < want:
                report["short"].setdefault(arm, {})[e["id"]] = [want, len(picked)]
            for x in picked:
                st = _settings(rng)
                arms[arm].append({"formula": x["formula"], "settings": st,
                                  "meta": {"experiment": EXPERIMENT, "arm": arm, "frame_id": e["id"],
                                           "frame_version": e.get("version"), "fill": x["fill"],
                                           "unseen_slots": _unseen(x["fill"], h), "role_note": note,
                                           "hypothesis": "frames:%s" % e["id"], "recipe": EXPERIMENT,
                                           "region": "USA", "delay": 1, "seed": seed}})
        report["per_frame"][e["id"]] = note
    # arm c: pair every arm-b alpha with a non-library mined frame that accepts the same fields
    arms["c"], report["c_unpaired"] = pair_c(arms["b"], fl, hist, lib_keys, rng, nonlib_min_fills)
    # one construction per (formula, settings): a novel frame's a and b draws can coincide, and so can two
    # c partners; the second copy would simulate the same alpha twice and count it in two arms
    constructions, seen, report["dropped_duplicates"] = [], set(), collections.Counter()
    for arm in ("a", "b", "c"):
        kept = []
        for c in arms[arm]:
            key = (c["formula"].replace(" ", ""), json.dumps(c["settings"], sort_keys=True))
            if key in seen:
                report["dropped_duplicates"][arm] += 1
                continue
            seen.add(key)
            kept.append(c)
        arms[arm] = kept
        constructions += kept
    for c in constructions:
        c["meta"]["cand"] = hashlib.sha256(("%s|%s" % (c["formula"], json.dumps(c["settings"], sort_keys=True))).encode()).hexdigest()[:12]
    report["counts"] = {k: len(v) for k, v in arms.items()}
    report["frames_per_arm"] = {k: len({c["meta"]["frame_id"] for c in v}) for k, v in arms.items()}
    return {"experiment": EXPERIMENT, "seed": seed, "cell": CELL, "constructions": constructions, "report": report}


def pair_c(b_alphas, fl, hist, lib_keys, rng, min_fills=4, tries=400):
    """For each arm-b alpha: a non-library frame (USA/d1/TOP3000 history, >= min_fills distinct fills, same
    slot count) that accepts the same fields in the same order, keeps the same frame after filling, and
    passes the structural gate. Returns (arm-c constructions, number of b alphas with no partner)."""
    pool = collections.defaultdict(list)
    for key, h in hist.items():
        if key in lib_keys or len(h["fills"]) < min_fills:
            continue
        try:
            nm = FR.normalize(key)
        except Exception:  # noqa: BLE001 -- an unparseable key is simply not a candidate
            continue
        pool[len(nm.slots)].append(nm)
    for k in pool:
        pool[k].sort(key=lambda x: x.text)
    out, unpaired = [], 0
    for b in b_alphas:
        fields = list(b["meta"]["fill"])
        cands = pool.get(len(fields), [])
        if not cands:
            unpaired += 1
            continue
        found = None
        for _ in range(min(tries, len(cands) * 2)):
            nm = rng.choice(cands)
            formula = nm.fill(fields)
            ok, _hard = CM.structurally_ok(formula, fl.labels, "USA", 1)
            if not ok:
                continue
            key, kfill, _ = FR.frame_formula(formula)
            if key != nm.key or list(kfill) != list(nm.key_fill(fields)):
                continue
            found = (nm, formula)
            break
        if not found:
            unpaired += 1
            continue
        nm, formula = found
        out.append({"formula": formula, "settings": dict(b["settings"]),
                    "meta": {"experiment": EXPERIMENT, "arm": "c", "frame_id": "nonlib:" + hashlib.sha256(nm.key.encode()).hexdigest()[:12],
                             "frame_key": nm.key, "fill": fields, "paired_b": b["meta"]["frame_id"],
                             "hypothesis": "frames:nonlib", "recipe": EXPERIMENT, "region": "USA", "delay": 1,
                             "seed": b["meta"]["seed"]}})
    return out, unpaired


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--per-arm", type=int, default=320)
    ap.add_argument("--out", required=True)
    ap.add_argument("--datasets-ok", default="", help="JSON list of dataset ids available today")
    ap.add_argument("--fields-ok", default="", help="file of field ids available today, one per line")
    a = ap.parse_args(argv)
    dso = set(json.loads(pathlib.Path(a.datasets_ok).read_text())) if a.datasets_ok else None
    fok = set(pathlib.Path(a.fields_ok).read_text().split()) if a.fields_ok else None
    plan = build(a.seed, a.per_arm, datasets_ok=dso, fields_ok=fok)
    pathlib.Path(a.out).write_text(json.dumps(plan))
    print(json.dumps(plan["report"]["counts"]), json.dumps(plan["report"]["frames_per_arm"]))
    print("pruned:", plan["report"]["pruned"])
    print("dead:", {k: len(v) for k, v in plan["report"]["dead"].items()}, "short:",
          {k: len(v) for k, v in plan["report"]["short"].items()}, "c unpaired:", plan["report"]["c_unpaired"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
