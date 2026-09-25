"""Screening round for the frames of the 245 submitted alphas (docs/frames/00_decisions.md F11-F13). Offline.

Each frame (FRAME SPEC v1 of a submitted alpha's code) gets `--per-frame` fresh fills:
  * at its OWN settings, universe included (F10, F13);
  * with fields only from datasets the ORIGINAL alpha did not use, in any slot (F12);
  * from datasets the platform offers today for USA/d1 (293 for every universe on 2026-09-25);
  * structurally_ok and re-framing to the same frame (framelib.filler).
The platform settings keys are copied from the original alpha, so nothing but the fields changes.

    python3 -B framelib/experiments/submitted_round.py --frames frames_from_submitted.json \
        --active active_alphas.json --datasets-ok datasets.json --per-frame 4 --seed 20260927 --out plan.json
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import round1 as R1                          # noqa: E402
from framelib import filler as FI            # noqa: E402
from framelib import frames as FR            # noqa: E402
from framelib.fields import FieldLibrary     # noqa: E402

EXPERIMENT = "FRAMES-R3S"
KEEP = ("instrumentType", "region", "universe", "delay", "decay", "neutralization", "truncation", "pasteurization",
        "unitHandling", "nanHandling", "language", "visualization", "maxTrade", "maxPosition")


def build(frames: list, active: dict, datasets_ok: set, per_frame: int, seed: int, only=None, same_dataset=False) -> dict:
    fl = FieldLibrary.build(cells={R1.CELL})
    pruned = R1.restrict(fl, datasets_ok, None)
    # FRAMES-R3S (2026-09-25 16:14): 46 fills used catalogue type GROUP fields in signal slots; the platform
    # rejected each ("Incompatible unit ... found Unit[Group:1]") and every rejection cancelled its parent of 10
    # (303 CANCELLED). forge.typed's gate let them through. GROUP fields never fill a slot here: a frame's group
    # arguments are its verbatim group tokens.
    cat = fl.catalogue.get(R1.CELL, {})
    for fid in [f for f, e in cat.items() if e.get("type") == "GROUP"]:
        del cat[fid]
    fl._index = {}
    fl.memo.clear()
    out, report = [], {"pruned": pruned, "skipped": collections.Counter(), "short": {}, "per_frame": {}}
    for f in frames:
        if only is not None and ("S:" + f["id"]) not in only:
            continue
        a = active.get(f["id"]) or {}
        st = a.get("settings") or {}
        if (st.get("region"), st.get("delay")) != ("USA", 1):
            report["skipped"]["not USA/d1"] += 1
            continue
        orig_ds = sorted({R1._dataset(fl, x) or "" for x in f["fill"]} - {""})
        try:
            normal = FR.normalize(f["key"])
        except Exception:  # noqa: BLE001
            report["skipped"]["frame does not normalise"] += 1
            continue
        n = len(normal.slots)
        if n == 0:
            report["skipped"]["no slot to fill"] += 1
            continue
        if same_dataset:
            # F14: each slot draws from the dataset its ORIGINAL field came from; the original fields themselves are
            # never reused (filtered below), so only the field changes
            per_slot = [R1._dataset(fl, x) for x in f["fill"]]
            if len(per_slot) != n or not all(per_slot):
                report["skipped"]["same-dataset: slot dataset unknown"] += 1
                continue
            cons = [{"datasets": [d]} for d in per_slot]
        else:
            cons = [{"exclude_datasets": orig_ds} for _ in range(n)]
        entry = {"id": "S:" + f["id"], "text": f["key"], "version": 1, "slots": [{"constraints": c} for c in cons]}
        res = FI.fill(entry, fl, R1.CELL, n=4 * per_frame + 4, seed=seed, by="dataset", settings={})
        if res["dead"]:
            report["skipped"]["dead: " + res["dead"][0][:50]] += 1
            continue
        pool = [x for x in res["fills"] if not (set(x["fill"]) & set(f["fill"]))]
        picked = pool[:per_frame]
        if len(picked) < per_frame:
            report["short"][entry["id"]] = [per_frame, len(picked)]
        settings = {k: st.get(k) for k in KEEP if k in st}
        for x in picked:
            out.append({"formula": x["formula"], "settings": dict(settings),
                        "meta": {"experiment": EXPERIMENT, "arm": "same" if same_dataset else "rep", "frame_id": entry["id"], "source_alpha": f["id"],
                                 "fill": x["fill"], "orig_datasets": orig_ds, "hypothesis": "frames:" + entry["id"],
                                 "recipe": EXPERIMENT, "region": "USA", "delay": 1, "seed": seed}})
        report["per_frame"][entry["id"]] = len(picked)
    seen, uniq = set(), []
    for c in out:
        k = (c["formula"].replace(" ", ""), json.dumps(c["settings"], sort_keys=True))
        if k not in seen:
            seen.add(k)
            c["meta"]["cand"] = hashlib.sha256(("%s|%s" % k).encode()).hexdigest()[:12]
            uniq.append(c)
    report["skipped"] = dict(report["skipped"])
    report["n"] = len(uniq)
    report["frames"] = len({c["meta"]["frame_id"] for c in uniq})
    report["universes"] = dict(collections.Counter(c["settings"].get("universe") for c in uniq))
    return {"experiment": EXPERIMENT, "seed": seed, "constructions": uniq, "report": report}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--active", required=True)
    ap.add_argument("--datasets-ok", required=True)
    ap.add_argument("--per-frame", type=int, default=4)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="", help="file of frame ids (S:<alpha>) to plan, one per line")
    ap.add_argument("--experiment", default=EXPERIMENT)
    ap.add_argument("--same-dataset", action="store_true", help="F14: fields from the original datasets, never the original fields")
    a = ap.parse_args(argv)
    frames = json.loads(pathlib.Path(a.frames).read_text())
    active = {x["id"]: x for x in json.loads(pathlib.Path(a.active).read_text())}
    dso = set(json.loads(pathlib.Path(a.datasets_ok).read_text()))
    only = set(pathlib.Path(a.only).read_text().split()) if a.only else None
    plan = build(frames, active, dso, a.per_frame, a.seed, only, a.same_dataset)
    for c in plan["constructions"]:
        c["meta"]["experiment"] = c["meta"]["recipe"] = a.experiment
    plan["experiment"] = a.experiment
    pathlib.Path(a.out).write_text(json.dumps(plan))
    r = plan["report"]
    print("constructions", r["n"], "frames", r["frames"], "universes", r["universes"])
    print("skipped", r["skipped"], "short", len(r["short"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
