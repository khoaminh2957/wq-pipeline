"""forge.runner — one forge ROUND: plan (cells → hypotheses → factory → pre-sim gates), then
simulate through the shared layered_sim dispatcher. RULE 1: `--live` only on the VPS.

Allocation (C10/C20, cells first): cells in weight order; within a cell every hypothesis gets a
block of ≤ `per_block` candidates (AlphaBench ~20); a cell takes ≤ `cell_cap` per round so one
round reaches several cells; the round stops at `n`. Duplicates against every journal and
non-novel signatures against the ACTIVE book are refused before anything is posted.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import random
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))          # `python forge/x.py` puts forge/ first, not the repo root
from forge import cells as C, compose as CP, ensemble as E, factory as F, gates as G, harvest as HV, hypotheses as H, signature as S, standard as ST  # noqa: E402
from forge import grammar as GR, labels as LB, typed as TY  # noqa: E402
from forge import allocate as AL  # noqa: E402

OUT = ROOT / "state/layered/runs/forge.jsonl"
PLANS = ROOT / "state/forge/plans"
QUARANTINE = "state/forge/quarantine.json"
JOURNAL_GLOB = "state/layered/runs/*.jsonl"


class Catalogues:
    """Field catalogues per (region, universe, delay), read once."""

    def __init__(self, root):
        self.root = pathlib.Path(root)
        self._idx = {}

    def index(self, region, universe, delay) -> dict:
        key = (region, universe, int(delay))
        if key not in self._idx:
            p = self.root / ("fetched/rc/fields/%s_%s_d%d.jsonl" % key)
            rows = []
            if p.exists():
                with open(p) as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            try:
                                rows.append(json.loads(line))
                            except ValueError:
                                continue
            self._idx[key] = F.catalogue_index(rows)
        return self._idx[key]


def novelty_index(root, catalogues: Catalogues) -> S.NoveltyIndex:
    """Signatures of the ACTIVE book (fetched/rc/active_book.json), catalogue-aware for USA/d1."""
    root = pathlib.Path(root)
    p = root / "fetched/rc/active_book.json"
    if not p.exists():
        return S.NoveltyIndex()
    usa = catalogues.index("USA", "TOP3000", 1)
    fd = {fid: m["dataset"] for fid, m in usa.items()} or None
    return S.NoveltyIndex.from_book(json.load(open(p)), field_datasets=fd)


#: The version of the code that produced a row, stamped into every construction so D1 ("a pipeline
#: VERSION receives the grade") and D14 ("only the alphas that version produced") have a referent.
#: Read once per process from the deploy manifest the target carries; when there is none -- a
#: hand-rsynced tree, which is how this desk ran for thirteen days -- it is computed from the bytes
#: on disk, so the answer is never absent and never a guess.
_VERSION = None


def pipeline_version(root=None) -> str:
    """The deployed version id, cached for the life of the process."""
    global _VERSION
    if _VERSION is not None:
        return _VERSION
    base = pathlib.Path(root or ROOT)
    try:
        _VERSION = json.loads((base / "DEPLOYED.json").read_text())["version"]
        return _VERSION
    except (OSError, ValueError, KeyError):
        pass
    try:
        sys.path.insert(0, str(base / "tools"))
        import deploy as DP
        _VERSION = DP.version_id(DP.content_hashes(DP.file_map(base))) + "+untracked"
    except Exception:  # noqa: BLE001 -- a version we cannot compute is named, never omitted
        _VERSION = "unknown"
    return _VERSION


def _construction(cand: dict, seed: int, recipe=None) -> dict:
    meta = dict(cand["meta"])
    formula = cand["formula"]
    recipe = recipe or {}
    if recipe.get("power"):
        formula = "signed_power(%s, %s)" % (formula, recipe["power"])   # tail concentration: returns lever
    if recipe.get("smooth"):
        formula = "ts_decay_linear(%s, %d)" % (formula, int(recipe["smooth"]))
    meta.update({"forge": 1, "cand": F.candidate_id(formula, cand["settings"]), "signature": cand["signature"]["key"],
                 "mechanism_key": cand["signature"]["mechanism_key"], "seed": seed,
                 "pipeline_version": pipeline_version()})
    if recipe.get("tag"):
        meta["recipe"] = recipe["tag"]
    return {"formula": formula, "settings": cand["settings"], "meta": meta}


def plan(root, n: int, seed: int, per_block: int = 20, cell_cap: int = 60, library_dir=None,
         split_delays: bool = True, ensembles: str = "off", mode: str = "composites", composites_dir=None,
         cells_filter=None, only=None, recipe=None, allocate: bool = True, posted_keys=None, delays=None, ab: str = "off",
         structure_gate: bool = True) -> dict:
    """Khoa 2026-09-04 (tick): every round is split half d0 / half d1 ("chia đều vòng"); a half that
    cannot fill hands its leftover to the other side so the round still reaches `n`.
    `ensembles`: "off" (single-leg hypotheses only), "add" (an ensemble block per cell that has ≥ 2
    measured legs, before the single-leg blocks), "only" (nothing but ensembles — the verification
    round Khoa ticked on 2026-09-04).
    `mode` (Khoa 2026-09-04 "1", the ratified standard): "composites" simulates only cross-family
    composites that pass the standard's hard gates — single-field hypotheses are LEGS, never alphas;
    "singles" is the pre-standard behaviour (measurement only); "both" runs composites first.
    `recipe` (Khoa 15:40 "thử nhiều cách … tới khi ra được pass đầu tiên"): plan-time overrides for
    ONE round — {"universe": {"GLB": "TOP3000"}, "neut": [...], "group": "country", "decay": [...],
    "truncation": 0.05, "smooth": 10, "tag": "R3"}; every row of the round carries meta.recipe."""
    root = pathlib.Path(root)
    lib = H.load_library(library_dir or root / "forge/hypotheses")
    lib_by_id = {h.id: h for h in lib}
    comps = []
    if mode in ("composites", "both"):
        comps = [c for c in H.load_composites(composites_dir or root / "forge/composites", lib) if ST.admissible(c)]
    cats = H.categories(lib)
    if mode == "composites":
        cats = {c for comp in comps for leg in comp.legs for c in lib_by_id[leg].categories()}
    all_cells = C.targets(root, hypotheses=cats)
    cells = [c for c in all_cells if c.weight > 0]
    if cells_filter:                                   # "GLB/d1 Fundamental" or shell-safe "GLB/d1:Fundamental"
        want = {x.strip().replace(":", " ").replace("%20", " ") for x in cells_filter if x.strip()}
        cells = [c for c in cells if "%s/d%d %s" % (c.region, c.delay, c.category) in want]
    if delays:                                         # Khoa 2026-09-07 19:10 (tick): d1 only — d0's line is 2.69, best d0 row ever 1.74
        cells = [c for c in cells if c.delay in set(delays)]
    if only:                                           # hypothesis / composite ids to include
        keep = {x.strip() for x in only if x.strip()}
        comps = [c for c in comps if c.id in keep]
        lib = [h for h in lib if h.id in keep] if mode != "composites" else lib
    recipe = dict(recipe or {})
    if recipe.get("universe"):
        cells = [c._replace(universe=recipe["universe"].get(c.region, c.universe)) for c in cells]
    if recipe.get("group"):
        for h in lib:
            if "group" in h.params:
                h.params["group"] = [recipe["group"]]
    for obj in list(lib) + list(comps):
        if recipe.get("neut"):
            obj.settings["neutralization"] = list(recipe["neut"])
        if recipe.get("decay"):
            obj.settings["decay"] = [int(d) for d in recipe["decay"]]
        if recipe.get("truncation") is not None:
            obj.settings["truncation"] = float(recipe["truncation"])
    if recipe.get("order"):
        # Khoa 2026-09-04 21:30 (standing loop): USA/d1 first, then every d1, then the rest — the day's
        # passes all came from USA/d1 (bar 1.58); d0 cells (bar 2.69) produced none in 500+ sims.
        prefixes = [x.strip() for x in recipe["order"] if x.strip()]

        def rank(c):
            key = "%s/d%d" % (c.region, c.delay)
            for i, pfx in enumerate(prefixes):
                if key == pfx or (pfx.startswith("d") and key.endswith("/" + pfx)) or key.startswith(pfx + "/"):
                    return i
            return len(prefixes)
        cells.sort(key=lambda c: (rank(c), -c.weight))
    cat = Catalogues(root)
    gate = G.PreSimGate(novelty_index(root, cat), seen_ids=G.journal_ids([root / JOURNAL_GLOB]), budget=n)
    # STRUCTURAL PRE-SIM GATE (Khoa's tick 2026-09-07 22:10): forge.typed H1 (units), H2 (kinds),
    # H4 vector / density — measured on 9,896 simulated formulas: refuses ~22 % with 0 rows ≥ 1.58
    # and 0 platform passes among them. The quarterly-backfill rule is not part of it (refuted).
    labels_path = pathlib.Path(root) / "fetched/rc/field_labels.jsonl"
    struct_labels = LB.load(labels_path) if (structure_gate and labels_path.exists()) else None
    struct_refused = collections.Counter()

    def structurally_ok(cand) -> bool:
        if struct_labels is None:
            return True
        st = cand["settings"]
        v = TY.judge(cand["formula"], struct_labels, "%s/d%s" % (st.get("region"), st.get("delay")), structural=True)
        if v["ok"]:
            return True
        struct_refused[(v["hard"][0][:2] + (" vector" if "VECTOR" in v["hard"][0] else " density" if "sparse" in v["hard"][0] else ""))] += 1
        return False
    rng = random.Random(seed)
    constructions, blocks, taken, made_ids = [], [], collections.Counter(), set()
    active_taken = [taken]              # which per-cell counter _composite_block charges (an A/B arm swaps its own in)
    qpath = root / QUARANTINE
    dead = set(json.load(open(qpath))) if qpath.exists() else set()
    journal = HV.forge_rows(root / "state/layered/runs/forge.jsonl") if (ensembles != "off" or allocate) else {}
    states = {}
    if allocate:
        if posted_keys is None:
            posted_keys = set()
            try:
                from forge import submit as SUB
                import submit_budget as SB
                posted_keys = {h["mechanism_key"] for h in SUB.posted_history(ledger=SB.LEDGER) if h.get("mechanism_key")}
            except Exception:  # noqa: BLE001 -- no ledger readable: nothing counts as harvested
                posted_keys = set()
        states = AL.pair_states(journal, posted_keys)
    posted_legs = {}
    if allocate and mode in ("composites", "both"):
        try:
            by_comp = {c.id: c for c in comps}
            for r in HV.read_jsonl(root / "state/forge/submitted.jsonl"):
                if r.get("http") in (200, 201) and r.get("hypothesis") in by_comp:
                    posted_legs[r["alpha"]] = list(by_comp[r["hypothesis"]].legs)
        except Exception:  # noqa: BLE001
            posted_legs = {}

    def _composite_block(cell, comp, room, idx, fd, cls=None) -> int:
        """One composite block on one cell (gate, quarantine, dedup); returns constructions added."""
        cands = CP.expand(comp, cell, idx, lib_by_id, rng, max_candidates=10 ** 6, field_datasets=fd)
        if not cands:
            return 0
        kept = []
        for cand in cands:
            if len(kept) >= room:
                break
            if cand["id"] in made_ids:
                continue
            if HV.quarantine_key(comp.id, cell.region, cell.delay, cell.category, cand["meta"].get("field")) in dead:
                continue
            if not structurally_ok(cand):
                continue
            if gate.check(cand) == G.OK:
                kept.append(cand)
                made_ids.add(cand["id"])
        constructions.extend(_construction(c, seed, recipe) for c in kept)
        active_taken[0][cell] += len(kept)
        blocks.append({"cell": "%s/d%d %s" % (cell.region, cell.delay, cell.category), "weight": cell.weight,
                       "hypothesis": comp.id, "grid": len(cands), "kept": len(kept), "class": cls or "-"})
        return len(kept)

    def fill_allocated(budget, comp_list=None, cell_list=None, taken_counter=None, untried_block=None) -> int:
        """Composite blocks in allocator order over every cell: near-miss (40), passed (10), untried,
        active; harvested and dead pairs are never simulated again (forge/allocate.py).
        `comp_list` / `cell_list` restrict the composites and cells (the A/B arms of a round);
        `taken_counter` gives an arm its own per-cell cap so the arms can share a cell (paired)."""
        made = 0
        tk = taken if taken_counter is None else taken_counter
        active_taken[0] = tk
        cats_of = lambda comp: {c for leg in comp.legs for c in lib_by_id[leg].categories()}  # noqa: E731
        for cell, comp, block, cls in AL.order(cell_list or cells, comp_list if comp_list is not None else comps, states, per_block,
                                               categories_of=cats_of, posted_legs=posted_legs, untried_block=untried_block):
            if made >= budget:
                break
            room = min(block, cell_cap - tk[cell], budget - made)
            if room <= 0:
                continue
            idx = cat.index(cell.region, cell.universe, cell.delay)
            fd = {fid: m["dataset"] for fid, m in idx.items()} or None
            made += _composite_block(cell, comp, room, idx, fd, cls)
        return made

    def fill(cell_list, budget) -> int:
        made = 0
        for cell in cell_list:
            if made >= budget:
                break
            idx = cat.index(cell.region, cell.universe, cell.delay)
            if ensembles != "off":
                room = min(per_block, cell_cap - taken[cell], budget - made)
                fd = {fid: m["dataset"] for fid, m in idx.items()} or None
                kept = []
                for cand in E.expand(cell, journal, rng, max_candidates=10 ** 6, field_datasets=fd):
                    if len(kept) >= room:
                        break
                    if cand["id"] in made_ids or gate.check(cand) != G.OK:
                        continue
                    kept.append(cand)
                    made_ids.add(cand["id"])
                if kept:
                    constructions.extend(_construction(c, seed, recipe) for c in kept)
                    taken[cell] += len(kept)
                    made += len(kept)
                    blocks.append({"cell": "%s/d%d %s" % (cell.region, cell.delay, cell.category),
                                   "weight": cell.weight, "hypothesis": "ensemble", "grid": len(kept), "kept": len(kept)})
                if ensembles == "only":
                    continue
            if mode in ("composites", "both") and not allocate:
                fd = {fid: m["dataset"] for fid, m in idx.items()} or None
                for comp in comps:
                    room = min(per_block, cell_cap - taken[cell], budget - made)
                    if room <= 0:
                        break
                    made += _composite_block(cell, comp, room, idx, fd)
            if mode == "composites":
                continue
            for h in lib:
                room = min(per_block, cell_cap - taken[cell], budget - made)
                if room <= 0:
                    break
                # The whole grid, shuffled by the round's rng; the gate refuses duplicates and
                # non-novel signatures one by one until the block is full.
                cands = F.expand(h, cell, idx, rng, max_candidates=10 ** 6)
                if not cands:
                    continue
                kept = []
                for cand in cands:
                    if len(kept) >= room:
                        break
                    if cand["id"] in made_ids:          # taken by an earlier pass of this plan
                        continue
                    if HV.quarantine_key(h.id, cell.region, cell.delay, cell.category, cand["meta"].get("field")) in dead:
                        continue                        # the platform refused this field here, every time
                    if not structurally_ok(cand):
                        continue
                    if gate.check(cand) == G.OK:
                        kept.append(cand)
                        made_ids.add(cand["id"])
                constructions.extend(_construction(c, seed, recipe) for c in kept)
                taken[cell] += len(kept)
                made += len(kept)
                blocks.append({"cell": "%s/d%d %s" % (cell.region, cell.delay, cell.category),
                               "weight": cell.weight, "hypothesis": h.id, "grid": len(cands), "kept": len(kept)})
        return made

    def fill_typed(budget) -> int:
        """The TYPED arm (Khoa 2026-09-07 tick: A/B 50/50 per round): random-within-the-grammar
        constructions over the same cells, judged by forge.typed, through the same gate."""
        labels = LB.load(pathlib.Path(root) / "fetched/rc/field_labels.jsonl")
        made, taken_t = 0, collections.Counter()
        # PAIRED DESIGN: the typed half goes to the same cells as the current half, in the same
        # proportions, so the arms differ only in how the formulas were written. With no current
        # half (nothing allocatable) it walks the ordered cells in blocks of per_block.
        used = [c for c in cells if taken[c] > 0]
        if used:
            tot = sum(taken[c] for c in used)
            quota = {c: max(1, round(budget * taken[c] / tot)) for c in used}
            walk = used
        else:
            quota = {c: per_block for c in cells}
            walk = [c for _ in range(max(1, cell_cap // max(1, per_block))) for c in cells]
        for cell in walk:
            if made >= budget:
                break
            room = min(quota.get(cell, per_block) - taken_t[cell], cell_cap - taken_t[cell], budget - made)
            if room <= 0:
                continue
            idx = cat.index(cell.region, cell.universe, cell.delay)
            fd = {fid: m["dataset"] for fid, m in idx.items()} or None
            res = GR.expand(labels, cell, rng, max_candidates=room * 2, field_datasets=fd)
            kept = []
            for cand in res["candidates"]:
                if len(kept) >= room:
                    break
                if cand["id"] in made_ids:
                    continue
                if gate.check(cand) == G.OK:
                    kept.append(cand)
                    made_ids.add(cand["id"])
            if kept:
                constructions.extend(_construction(c, seed, recipe) for c in kept)
                taken_t[cell] += len(kept)
                made += len(kept)
            blocks.append({"cell": "%s/d%d %s" % (cell.region, cell.delay, cell.category), "weight": cell.weight,
                           "hypothesis": "typed", "grid": len(res["candidates"]), "kept": len(kept), "class": "TYPED",
                           "refused": res["refused"], "reasons": res.get("reasons", {})})
        return made

    comps_current = [c for c in comps if getattr(c, "arm", "current") != "new"]
    comps_new = [c for c in comps if getattr(c, "arm", "current") == "new"]
    n_current = n // 2 if ab in ("typed", "new") else n
    made_alloc = fill_allocated(n_current, comps_current if ab == "new" else None) if (allocate and mode in ("composites", "both")) else 0
    made_typed = 0
    if ab == "typed":
        for c in constructions:
            c["meta"].setdefault("arm", "current")
        made_typed = fill_typed(n - n_current)
        remaining = 0
    elif ab == "new":
        # harness5 round arm: the composites marked `arm: new`, on the cells the current half used
        # (paired, Q24) first, then the rest; tagged meta.arm = "new"
        for c in constructions:
            c["meta"].setdefault("arm", "current")
        used = [c for c in cells if taken[c] > 0]
        # a round arm also reaches the FULL USA/d1 cells (weight 0): a pass there is still a
        # submission under Q2, only the pyramid gain is nil (Khoa Q18: USA/d1 first)
        full_usa = [c for c in all_cells if c.weight <= 0 and c.region == "USA" and c.delay == 1 and c not in cells]
        if delays:
            full_usa = [c for c in full_usa if c.delay in set(delays)]
        before = len(constructions)
        # the new arm keeps its own per-cell cap (paired cells) and opens each untried pair with a
        # full block (per_block), not the exploration block of 10: the round IS its exploration
        made_typed = fill_allocated(n - n_current, comps_new, used + [c for c in cells if c not in used] + full_usa,
                                    taken_counter=collections.Counter(), untried_block=per_block)
        active_taken[0] = taken
        for c in constructions[before:]:
            c["meta"]["arm"] = "new"
        remaining = 0
    else:
        remaining = n - made_alloc
    if remaining > 0 and not (allocate and mode == "composites"):
        if split_delays:
            made0 = fill([c for c in cells if c.delay == 0], remaining // 2)
            made1 = fill([c for c in cells if c.delay == 1], remaining - remaining // 2)
            left = remaining - made0 - made1
            if left > 0:
                fill(cells, left)
        else:
            fill(cells, remaining)
    return {"seed": seed, "n": n, "made_at": time.time(), "hypotheses": len(lib),
            "cells_considered": len(cells), "gate": dict(gate.counts), "blocks": blocks, "quarantined": len(dead),
            "ensembles": ensembles, "n_ensembles": sum(1 for c in constructions if c["meta"].get("ensemble")),
            "allocate": allocate, "pair_classes": AL.summary(states) if states else {},
            "ab": ab, "by_arm": dict(collections.Counter(c["meta"].get("arm", "-") for c in constructions)), "n_typed": made_typed,
            "structure_gate": struct_labels is not None, "structure_refused": dict(struct_refused),
            "typed_refused": sum(b.get("refused", 0) for b in blocks if b.get("class") == "TYPED"),
            "blocks_by_class": dict(collections.Counter(b.get("class", "-") for b in blocks)),
            "mode": mode, "composites": len(comps), "n_composites": sum(1 for c in constructions if c["meta"].get("composite")),
            "by_delay": {d: sum(1 for c in constructions if c["settings"]["delay"] == d) for d in (0, 1)},
            "constructions": constructions}


def summarize(p: dict) -> str:
    per_cell = collections.OrderedDict()
    for b in p["blocks"]:
        per_cell[b["cell"]] = per_cell.get(b["cell"], 0) + b["kept"]
    lines = ["forge plan seed %d [%s]: %d construction(s) (d0 %d / d1 %d; composites %d) from %d hypotheses, %d composites, "
             "%d reachable cell(s); gate %s"
             % (p["seed"], p.get("mode"), len(p["constructions"]), p.get("by_delay", {}).get(0, 0), p.get("by_delay", {}).get(1, 0),
                p.get("n_composites", 0), p["hypotheses"], p.get("composites", 0), p["cells_considered"], p["gate"])]
    if p.get("pair_classes"):
        lines.append("  allocator: pairs %s | blocks by class %s" % (p["pair_classes"], p.get("blocks_by_class")))
    if p.get("structure_gate"):
        lines.append("  structure gate: refused %s" % (p.get("structure_refused") or {}))
    if p.get("ab") and p.get("ab") != "off":
        lines.append("  A/B %s: by arm %s | typed judge refusals %s" % (p["ab"], p.get("by_arm"), p.get("typed_refused")))
    for cell, k in per_cell.items():
        if k:
            lines.append("  %-28s %3d" % (cell, k))
    return "\n".join(lines)


def queue_kind(p: dict, last_count) -> str | None:
    """Which m13 to send for this plan, if any: loaded / exhausted / low / None."""
    made, asked = len(p["constructions"]), p["n"]
    if last_count is not None and last_count != p["hypotheses"]:
        return "loaded"
    if made == 0:
        return "exhausted"
    if made < asked / 2:
        return "low"
    return None


def notify_queue(p: dict, root) -> None:
    """m13 hypothesis-queue alert; failure to notify never touches the round. Khoa 2026-09-04
    (tick): forge notifications are OFF until asked — sending needs WQ_FORGE_NOTIFY=1."""
    try:
        marker = pathlib.Path(root) / "state/forge/library_count"
        last = int(marker.read_text()) if marker.exists() else None
        kind = queue_kind(p, last)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(p["hypotheses"]))
        if kind and os.environ.get("WQ_FORGE_NOTIFY") == "1":
            import msgcat as MC
            MC.send(MC.m13_hypothesis_queue(kind, p["hypotheses"], len(p["constructions"]), p["n"], p["cells_considered"]))
    except Exception as exc:  # noqa: BLE001
        print("m13 notify skipped (%s: %s)" % (type(exc).__name__, exc))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--live", action="store_true", help="actually spend simulations (VPS only, RULE 1)")
    ap.add_argument("--concurrency", type=int, default=9)
    ap.add_argument("--children", type=int, default=10)
    ap.add_argument("--per-block", type=int, default=20)
    ap.add_argument("--cell-cap", type=int, default=60)
    ap.add_argument("--ensembles", choices=("off", "add", "only"), default="off",
                    help="2-3-leg ensembles of measured legs per cell (forge/ensemble.py)")
    ap.add_argument("--mode", choices=("composites", "singles", "both"), default="composites",
                    help="composites = only standard-admissible cross-family composites (default); singles = legs alone")
    ap.add_argument("--cells", default="", help='comma list of cells to plan for, e.g. "GLB/d1 Fundamental,GLB/d1 Analyst"')
    ap.add_argument("--only", default="", help="comma list of hypothesis/composite ids to include")
    ap.add_argument("--universe", default="", help="REGION:UNIVERSE[,...] override, e.g. GLB:TOP3000")
    ap.add_argument("--neut", default="", help="comma list overriding neutralization for this round")
    ap.add_argument("--group", default="", help="group field for every leg this round, e.g. country")
    ap.add_argument("--decay", default="", help="comma list overriding decay for this round")
    ap.add_argument("--truncation", type=float, default=None)
    ap.add_argument("--smooth", type=int, default=0, help="wrap every formula in ts_decay_linear(., D)")
    ap.add_argument("--power", type=float, default=0, help="wrap every formula in signed_power(., P)")
    ap.add_argument("--tag", default="", help="recipe tag written to meta.recipe")
    ap.add_argument("--order", default="", help="cell priority prefixes, e.g. USA/d1,d1 (then by weight)")
    ap.add_argument("--no-split", action="store_true", help="no half-d0/half-d1 split: cells in priority order")
    ap.add_argument("--no-allocate", action="store_true", help="disable the journal-driven allocator (forge/allocate.py)")
    ap.add_argument("--delays", default="", help="comma list of delays to plan for, e.g. 1 (d0 cells are dropped)")
    ap.add_argument("--no-structure-gate", action="store_true", help="disable the forge.typed H1/H2/H4 pre-sim gate")
    ap.add_argument("--ab", choices=("off", "typed", "new"), default="off",
                    help="typed = half from the current planner, half from forge.grammar; new = half current composites, "
                         "half the composites marked `arm: new` (harness5 round arm)")
    ap.add_argument("--plan", default="", help="prebuilt plan JSON (constructions fixed by an experiment script); skips the planner")
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(argv)
    seed = a.seed if a.seed is not None else int(time.time())
    recipe = {"tag": a.tag or None, "smooth": a.smooth or None, "power": a.power or None, "truncation": a.truncation,
              "neut": a.neut.split(",") if a.neut else None, "decay": a.decay.split(",") if a.decay else None,
              "group": a.group or None,
              "universe": dict(x.split(":", 1) for x in a.universe.split(",") if ":" in x) if a.universe else None,
              "order": a.order.split(",") if a.order else None}
    if a.plan:
        p = json.loads(pathlib.Path(a.plan).read_text())
        p["seed"] = seed
    else:
        p = plan(a.root, a.n, seed, per_block=a.per_block, cell_cap=a.cell_cap, ensembles=a.ensembles, mode=a.mode,
                 cells_filter=a.cells.split(",") if a.cells else None, only=a.only.split(",") if a.only else None,
                 recipe=recipe, split_delays=not a.no_split, allocate=not a.no_allocate,
                 delays=[int(x) for x in a.delays.split(",") if x.strip()] or None, ab=a.ab, structure_gate=not a.no_structure_gate)
    PLANS.mkdir(parents=True, exist_ok=True)
    (PLANS / ("%d.json" % seed)).write_text(json.dumps(p))
    print(summarize(p), flush=True)
    notify_queue(p, a.root)
    if not p["constructions"]:
        print("nothing to simulate: the library is exhausted for every reachable cell (m13 case)")
        return 2
    import layered_sim as LS
    LS.run(len(p["constructions"]), seed=seed, out_path=OUT, live=a.live, concurrency=a.concurrency,
           children=a.children, batch=p["constructions"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
