"""ON THE VPS (RULE 1): merge arms a-c (built on the Mac by framelib/experiments/round1.py) with arm d (the
incumbent planner's own plan, made by frames_round.sh a minute earlier), shuffle, and dispatch in chunks
through the SAME dispatcher the loop uses (tools/layered_sim.run with batch=...), into a journal of its own
so the incumbent's harvest and submit never see these rows (docs/frames/00_decisions.md F3).

    python -u dispatch_round.py --abc plan_abc.json --d state/forge/plans/<seed>.json --seed S \
        --journal state/layered/runs/frames_r1.jsonl [--live]

Without --live nothing is spent: the dispatcher prints DRY RUN.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys

WQ = pathlib.Path("/opt/wq")
sys.path[:0] = [str(WQ), str(WQ / "tools")]

CHUNK = 300          # a forge round's size; layered_sim caps one call at MAX_ROUND_S (75 min); a multiple of BLOCK
BLOCK = 10           # MULTISIM_CHILDREN: one parent


def merged(abc: dict, d: dict, seed: int, experiment: str) -> list:
    out = [dict(c) for c in abc["constructions"]]
    for c in d["constructions"]:
        c = dict(c)
        meta = dict(c.get("meta") or {})
        meta.update({"experiment": experiment, "arm": "d", "recipe": experiment, "d_plan_seed": d.get("seed")})
        c["meta"] = meta
        out.append(c)
    seen, uniq = set(), []
    for c in out:
        key = (c["formula"].replace(" ", ""), json.dumps(c["settings"], sort_keys=True))
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    # SINGLE-ARM PARENTS. multisim_groups (harness13/massgen/mg/simulate.py) keeps the caller's order and
    # cuts consecutive runs of 10; one invalid child cancels its whole parent (measured, FRAMES-R1 attempt 1,
    # 2026-09-24 17:38: both first parents cancelled, the siblings from other arms with them). So the batch
    # is cut into blocks of 10 of ONE arm, and the BLOCKS are shuffled: arms still share every chunk and
    # every minute, and a cancellation stays inside the arm that caused it.
    rng = random.Random("%s|shuffle|%d" % (experiment, seed))
    blocks = []
    # a parent is also one (delay, region, universe) -- multisim_groups cuts a run where that key changes, which
    # would break the 10-alignment -- so blocks are cut per (arm, universe) (FRAMES-R3S: frames keep their
    # original universe, F13)
    for arm, uni in sorted({(c["meta"]["arm"], str(c["settings"].get("universe"))) for c in uniq}):
        rows = [c for c in uniq if c["meta"]["arm"] == arm and str(c["settings"].get("universe")) == uni]
        rng.shuffle(rows)
        # a short block would shift every later parent boundary and put two arms in one parent: each arm is
        # trimmed to a multiple of BLOCK (the trimmed rows are printed, never simulated)
        cut = len(rows) - len(rows) % BLOCK
        if cut < len(rows):
            print("arm %s / %s: %d row(s) trimmed to keep parents single-arm" % (arm, uni, len(rows) - cut), flush=True)
        rows = rows[:cut]
        blocks += [rows[i:i + BLOCK] for i in range(0, len(rows), BLOCK)]
    rng.shuffle(blocks)
    return [c for b in blocks for c in b]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--abc", required=True)
    ap.add_argument("--d", default="", help="arm d plan (the incumbent planner); empty = no arm d (round 2)")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--journal", required=True)
    ap.add_argument("--experiment", default="FRAMES-R1")
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args(argv)
    abc = json.loads(pathlib.Path(a.abc).read_text())
    d = json.loads(pathlib.Path(a.d).read_text()) if a.d else {"constructions": []}
    batch = merged(abc, d, a.seed, a.experiment)
    by_arm = {}
    for c in batch:
        by_arm[c["meta"]["arm"]] = by_arm.get(c["meta"]["arm"], 0) + 1
    print("frames round: %d constructions %s" % (len(batch), json.dumps(by_arm, sort_keys=True)), flush=True)
    pathlib.Path(a.journal).parent.mkdir(parents=True, exist_ok=True)
    (pathlib.Path(a.journal).with_suffix(".plan.json")).write_text(json.dumps({"seed": a.seed, "constructions": batch}))
    import layered_sim as LS
    for i in range(0, len(batch), CHUNK):
        chunk = batch[i:i + CHUNK]
        print("=== chunk %d: %d constructions ===" % (i // CHUNK + 1, len(chunk)), flush=True)
        LS.run(len(chunk), seed=a.seed + i, out_path=pathlib.Path(a.journal), live=a.live, concurrency=9,
               children=10, batch=chunk)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
