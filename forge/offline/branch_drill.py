"""forge.offline.branch_drill — does a new branch actually go through, or only in principle? (D8)

Khoa's third question: "có thể phát triển thêm các nhánh nhỏ để nâng cấp pipeline hay ko hay chỉ có
thể dừng". The architecture fitness functions answer it in principle -- mechanisms are YAML, a staged
area exists, there is no module-level import cycle. This module answers it in FACT: it grows a real
branch and watches the real planner carry it.

THE DRILL, and what each step rules out:
  1. copy the live library (legs + composites) into a throwaway directory -- the drill must never
     touch what the loop reads;
  2. write ONE new composite that pairs two existing legs no composite pairs today -- a genuinely
     new mechanism, not a rename of an old one;
  3. hash every forge/*.py before and after -- growing the branch must not require editing code,
     or "the library is data" is a slogan;
  4. run forge.runner.plan() on the copy with `only=[drill id]` and the structure gate ON -- the
     same function the loop calls, not a re-implementation of it;
  5. pass iff the planner emits at least one construction tagged with the drill's id.

WHAT A PASS DOES NOT SAY. It says the plumbing carries a new mechanism to the point of a simulation
request. It says nothing about whether that mechanism would pass the platform's checks -- that
question costs quota and belongs to the live loop, never to CI (RULE 1).
"""
from __future__ import annotations

import hashlib
import itertools
import pathlib
import shutil
import sys
import tempfile
import time

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from forge import hypotheses as H, runner as R  # noqa: E402


def _code_hash(root=ROOT) -> str:
    h = hashlib.sha256()
    for p in sorted((root / "forge").glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _unpaired_legs(lib, comps):
    """Two legs from different families, in a common region and delay, never paired by any composite."""
    paired = {frozenset(c.legs) for c in comps if getattr(c, "legs", None)}
    for a, b in itertools.combinations(sorted(lib, key=lambda h: h.id), 2):
        if a.family == b.family or frozenset((a.id, b.id)) in paired:
            continue
        if not (set(a.regions) & set(b.regions)) or not (set(a.delays) & set(b.delays)):
            continue
        if a.category != b.category:          # one cell, so the planner has somewhere to put it
            continue
        return a, b
    return None


def drill(root=ROOT, seed=None) -> dict:
    """Grow one branch on a copy of the library and report whether the real planner carries it."""
    if seed is None:
        # a seed whose plan file does NOT exist, so the cleanup below can only ever remove the drill's
        # own plan. Unlinking plans/<seed>.json blindly deleted a pre-existing plan when a seed
        # collided (MEASURED 2026-09-23: the local plan count went 157 -> 156 during development;
        # which file was lost is UNKNOWN, a collision on a hand-picked seed is the candidate).
        seed = 900_000_000
        while (R.PLANS / ("%d.json" % seed)).exists():
            seed += 1
    elif (R.PLANS / ("%d.json" % seed)).exists():
        raise ValueError("plan %d.json already exists; the drill will not overwrite or delete it" % seed)
    before = _code_hash(root)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="wq-drill-"))
    try:
        hyp, comp = tmp / "hypotheses", tmp / "composites"
        shutil.copytree(root / "forge/hypotheses", hyp, ignore=shutil.ignore_patterns("staged"))
        shutil.copytree(root / "forge/composites", comp, ignore=shutil.ignore_patterns("staged"))
        lib = H.load_library(hyp)
        comps = H.load_composites(comp, lib)
        pair = _unpaired_legs(lib, comps)
        if pair is None:
            return {"status": "no-branch-possible", "ok": False,
                    "note": "every eligible leg pair is already a composite; the drill has nothing new to grow"}
        a, b = pair
        drill_id = "drill_%s_x_%s" % (a.id, b.id)
        # Clone a composite the live library ALREADY admits and change only what makes it a new
        # branch: id, legs, families. Every other field has passed the hypothesis standard's eight
        # gates for real, so the drill tests the plumbing and not the author's ability to guess the
        # standard -- the first two drafts, written field by field, were refused by gates 2 and 1.
        template = next(p for p in sorted(comp.glob("*.yaml")))
        body = yaml.safe_load(template.read_text())
        body.update({"id": drill_id, "title": "BRANCH DRILL (cloned from %s) -- throwaway, never simulated" % body["id"],
                     "legs": [a.id, b.id], "families": [a.family, b.family]})
        (comp / ("%s.yaml" % drill_id)).write_text(yaml.safe_dump(body, sort_keys=False, allow_unicode=True))

        p = R.plan(root, n=20, seed=seed, library_dir=hyp, composites_dir=comp, only=[drill_id],
                   allocate=False, structure_gate=True)
        # meta["composite"] is a FLAG (1); the composite's id lives in meta["hypothesis"] -- the first
        # version of this line read the flag and reported every drill as not carried
        carried = [c for c in p["constructions"] if (c.get("meta") or {}).get("hypothesis") == drill_id]
        others = len(p["constructions"]) - len(carried)
        after = _code_hash(root)
        ok = bool(carried) and before == after
        return {"status": "carried" if carried else "not-carried", "ok": ok,
                "drill_id": drill_id, "legs": [a.id, b.id], "constructions": len(carried),
                "other_constructions": others,
                "code_unchanged": before == after,
                "gate": p.get("gate"),
                "note": ("a new mechanism reached the planner with no code edited" if ok else
                         "the planner produced no construction for the drill" if not carried else
                         "forge/*.py changed during the drill")}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        # R.plan writes state/forge/plans/<seed>.json; digest.py reads the newest plan by mtime, so a
        # drill plan left there would become the day's reported plan
        (R.PLANS / ("%d.json" % seed)).unlink(missing_ok=True)


if __name__ == "__main__":
    import json
    r = drill()
    print(json.dumps(r, indent=1, default=str))
    sys.exit(0 if r["ok"] else 1)
