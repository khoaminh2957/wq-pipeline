"""Round 2 plan (docs/frames/13_preregistration.md §7: R2 re-fills ALL 100 frames equally, regardless of their
round-1 rank): 8 own-role fills (arm a) + 4 other-dataset fills (arm b) per frame, every fill FRESH -- no field
of it was used with that frame in round 1 -- and not in the frame's history. Settings from the same 6-cell grid.
Offline; nothing simulates here (RULE 1).

    python3 -B framelib/experiments/round2.py --seed 20260926 --r1-plan frames_r1b.plan.json \
        --datasets-ok datasets_usa_top3000_d1.json --out plan_abc_FRAMES-R2.json
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import round1 as R1                          # noqa: E402
from framelib import filler as FI            # noqa: E402
from framelib import frames as FR            # noqa: E402
from framelib import store                   # noqa: E402
from framelib.fields import FieldLibrary     # noqa: E402

EXPERIMENT = "FRAMES-R2"
PER_FRAME = {"a": 8, "b": 4}


def build(seed: int, r1_plan: list, datasets_ok=None) -> dict:
    rng = random.Random("frames-r2|%d" % seed)
    entries = store.load()
    fl = FieldLibrary.build(cells={R1.CELL})
    pruned = R1.restrict(fl, datasets_ok, None) if datasets_ok is not None else None
    hist = R1.history()
    used_r1 = collections.defaultdict(set)
    for c in r1_plan:
        m = c.get("meta") or {}
        if m.get("arm") in ("a", "b") and m.get("frame_id"):
            used_r1[m["frame_id"]].update(m.get("fill") or ())
    out, report = [], {"pruned": pruned, "short": {}, "dead": {}}
    for e in entries:
        ea, eb, note = R1.arm_entries(e, fl, hist)
        h = hist.get(e.get("canonical_key") or "")
        excl = {FR.normalize(e["text"]).fill(list(f)) for f in (h["fills"] if h else ())}
        for arm, ent in (("a", ea), ("b", eb)):
            want = PER_FRAME[arm]
            res = FI.fill(ent, fl, R1.CELL, n=10 * want + 10, seed=seed, by="dataset", exclude=excl)
            if res["dead"]:
                report["dead"].setdefault(arm, {})[e["id"]] = res["dead"]
                continue
            fresh = [x for x in res["fills"] if not (set(x["fill"]) & used_r1[e["id"]])]
            picked = fresh[:want]
            if len(picked) < want:
                report["short"].setdefault(arm, {})[e["id"]] = [want, len(picked)]
            for x in picked:
                out.append({"formula": x["formula"], "settings": R1._settings(rng),
                            "meta": {"experiment": EXPERIMENT, "arm": arm, "frame_id": e["id"],
                                     "frame_version": e.get("version"), "fill": x["fill"], "role_note": note,
                                     "hypothesis": "frames:%s" % e["id"], "recipe": EXPERIMENT,
                                     "region": "USA", "delay": 1, "seed": seed}})
    seen, uniq = set(), []
    for c in out:
        k = (c["formula"].replace(" ", ""), json.dumps(c["settings"], sort_keys=True))
        if k not in seen:
            seen.add(k)
            c["meta"]["cand"] = hashlib.sha256(("%s|%s" % k).encode()).hexdigest()[:12]
            uniq.append(c)
    report["counts"] = dict(collections.Counter(c["meta"]["arm"] for c in uniq))
    report["frames"] = {arm: len({c["meta"]["frame_id"] for c in uniq if c["meta"]["arm"] == arm}) for arm in "ab"}
    return {"experiment": EXPERIMENT, "seed": seed, "cell": R1.CELL, "constructions": uniq, "report": report}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--r1-plan", required=True)
    ap.add_argument("--datasets-ok", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    r1 = json.loads(pathlib.Path(a.r1_plan).read_text())["constructions"]
    dso = set(json.loads(pathlib.Path(a.datasets_ok).read_text())) if a.datasets_ok else None
    plan = build(a.seed, r1, dso)
    pathlib.Path(a.out).write_text(json.dumps(plan))
    rep = plan["report"]
    print("counts", rep["counts"], "frames", rep["frames"], "pruned", rep["pruned"])
    print("short:", {k: len(v) for k, v in rep["short"].items()}, "dead:", {k: len(v) for k, v in rep["dead"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
