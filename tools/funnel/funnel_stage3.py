#!/usr/bin/env python3
"""funnel_stage3.py — STAGE-3 conditional-escalation orchestrator (funnel_wire).

The v7 funnel is Stage-1 (1 root field -> 180 -> TOP-3) -> Stage-2 (3 seeds, each
+ a 2nd same-dataset field via multiply/if_else/divide -> 3x180 -> TOP-9). This
tool is the CONDITIONAL Stage-3 that ESCALATES only when warranted:

  ESCALATION TRIGGER (gate_lib): IF the TOP-9 contains NO alpha that passes ALL
  the checks the platform returned for that region x delay (zero-fail via
  gate_lib.gate_status), escalate; otherwise Stage-3 is a NO-OP (manifest records
  escalation_triggered=false, no sims).

  ESCALATED SWEEP: take the 9 seeds and, per seed, add a THIRD field (same
  dataset, structure DIFFERING from the seed's) chosen upstream by the runtime
  harness (>=majority debate-approved, no hallucination/veto). Each seed +
  choice -> second_field_sweep.generate 180 configs -> 9x180 = 1620 targets ->
  run_multisim --sweep (10x10 multi-sim POSTs, live=operator) -> gates from the
  journal -> rank_gates TOP-27 (reserve-sharpe rule: robust priority but the
  highest-sharpe rows are still guaranteed a slot) -> logic_check L0 report.
  NEVER auto-submits.

This is the ORCHESTRATOR only — it CHAINS the real tools (second_field_sweep,
run_multisim, rank_gates, gate_lib, logic_check, funnel_run's mock/summarize
helpers), it does NOT reimplement any of them.

Third-field mechanic:
  A Stage-2 seed is the 2-field composite `seed_structure(t1(field1), t2(field2))`.
  Stage-3 ESCALATES that seed by layering a THIRD field on top of the WHOLE seed:
  `structure3(<seed>, t3(field3))` with structure3 DIFFERING from seed_structure.
  This is produced by third_field_sweep.generate (the purpose-built 3-operand
  generator — 180 configs/seed, all of field1/field2/field3 present, SIGN 50/50,
  same-dataset + field3-is-MATRIX + structure3!=seed guards). The seed's root
  (field1) is PRESERVED, not dropped. field3 is validated here (before any sim)
  to be a genuinely new field (not field1 or field2) from the SAME dataset.

REFUSES (hard stop, before any sim): != 9 choices, a cross-dataset field3, or a
field3 that equals the seed's field1 or field2.

--dry-run: mock sim (deterministic, API-free) proving the wiring end-to-end; the
live launch is INTEGRATION-RUN-BY-OPERATOR (single-stream account, resim_bulk).
"""
from __future__ import annotations
import argparse, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import second_field_sweep as sfs   # noqa: E402  STRUCTURES / _dataset_prefix (validation reuse)
import third_field_sweep as tfs    # noqa: E402  3-operand generator: structure3(seed, t3(field3))
import run_multisim as rms         # noqa: E402  10x10 batch planner + --sweep precheck/logic gate
import rank_gates as rg            # noqa: E402  deterministic reserve-sharpe TOP-N selector
import gate_lib                    # noqa: E402  C7 zero-fail verdict (escalation trigger)
import logic_check                 # noqa: E402  L0 3-layer logic report
import funnel_run as fr            # noqa: E402  reuse mock_sim / summarize_gates / journal reader

ST = ROOT / "state"
FUN = ST / "funnel"

N_SEEDS = 9
N_CONFIGS = 180
TOP_N = 27


def load_rows(path: pathlib.Path):
    data = json.load(open(path))
    if isinstance(data, dict):
        data = data.get("top") or data.get("rows") or data.get("targets") or [data]
    return data


def escalation_triggered(top9: list) -> tuple[bool, list]:
    """Trigger iff NO seed is zero-fail over the checks the platform returned.
    Returns (triggered, per-seed [{id, zero_fail, fails}])."""
    per = []
    any_pass = False
    for r in top9:
        gs = gate_lib.gate_status(r)
        any_pass = any_pass or gs["zero_fail"]
        per.append({"id": rg.row_id(r), "zero_fail": gs["zero_fail"], "fails": gs["fails"]})
    return (not any_pass), per


def validate_choice(i: int, choice: dict):
    """Hard refusals for one seed's third-field pick. Raises SystemExit on any."""
    f1, f2, f3 = choice["field1"], choice["field2"], choice["third_field"]
    struct, seed_struct = choice["structure"], choice["seed_structure"]
    if struct not in sfs.STRUCTURES:
        raise SystemExit(f"choice[{i}]: structure {struct!r} not in {list(sfs.STRUCTURES)}")
    if struct == seed_struct:
        raise SystemExit(f"choice[{i}]: structure {struct!r} must DIFFER from the seed structure")
    if f3 == f1 or f3 == f2:
        raise SystemExit(f"choice[{i}]: third_field {f3!r} must differ from field1 {f1!r} "
                         f"and field2 {f2!r} (field3 in {{field1,field2}})")
    if sfs._dataset_prefix(f3) != sfs._dataset_prefix(f2):
        raise SystemExit(f"choice[{i}]: third_field {f3!r} is cross-dataset "
                         f"(prefix {sfs._dataset_prefix(f3)!r} != seed dataset "
                         f"{sfs._dataset_prefix(f2)!r}) — field3 must be SAME dataset")


def build_targets(run: str, top9: list, choices: list) -> list:
    """Per seed: third_field_sweep.generate(field1, field2, field3, structure3) -> 180
    3-operand rows structure3(seed_structure(t1(field1),t2(field2)), t3(field3)) — the
    seed (root+field2) is preserved. Ids namespaced per seed so the pool is unique."""
    targets = []
    for i, (seed, ch) in enumerate(zip(top9, choices)):
        validate_choice(i, ch)
        st = seed.get("settings") or {}
        region, universe, delay = st["region"], st["universe"], st["delay"]
        v = tfs.generate(ch["field1"], ch["field2"], ch["third_field"], ch["structure"],
                         region, universe, delay,
                         seed_structure=ch["seed_structure"],
                         n=N_CONFIGS, label=f"{run}_stage3_seed{i}")
        for r in v:
            r["id"] = r["old_id"] = f"{run}_s3seed{i}_{r['old_id']}"
        targets.extend(v)
    return targets


def run_sims(targets: list, tag: str, tpath: pathlib.Path, dry_run: bool):
    """Verify the 10x10 plan, run the BLOCKING --sweep gate (logic_check L0 +
    precheck, family-novelty skipped), then sim (mock in dry-run, else operator
    resim_bulk). Returns (sim_rows, n_posts)."""
    n_posts = fr._verify_batch_plan(targets, tag)      # ceil(N/BATCH) homogeneous POSTs
    if not rms.precheck_gate(targets, tpath, sweep=True):
        raise SystemExit(f"[{tag}] --sweep gate blocked launch (logic_check/precheck) — 0 sims")
    if dry_run:
        return fr.mock_sim(targets, tag), n_posts
    if not rms.live_launch(tpath, sweep=True):          # integration-run-by-operator
        raise SystemExit(f"[{tag}] live_launch did not journal all sims")
    return fr._journal_results(targets, tag), n_posts


def run_stage3(run: str, top9: list, choices: list, dry_run: bool) -> dict:
    if len(choices) != N_SEEDS:
        raise SystemExit(f"REFUSE: need EXACTLY {N_SEEDS} third-field/structure choices "
                         f"(one per top-9 seed), got {len(choices)}")
    if len(top9) != N_SEEDS:
        raise SystemExit(f"REFUSE: top-9 must contain EXACTLY {N_SEEDS} seeds, got {len(top9)}")

    triggered, per_seed = escalation_triggered(top9)
    FUN.mkdir(parents=True, exist_ok=True)
    man_path = FUN / f"{run}_stage3_manifest.json"

    if not triggered:
        manifest = {"run": run, "dry_run": dry_run, "escalation_triggered": False,
                    "reason": "a top-9 seed already passes ALL gates (zero-fail) — no escalation",
                    "seed_gates": per_seed, "top27": None}
        json.dump(manifest, open(man_path, "w"), indent=1, sort_keys=True)
        return manifest

    tag = f"{run}_stage3"
    targets = build_targets(run, top9, choices)         # 9x180 = 1620, refusals enforced here
    tpath = FUN / f"{tag}_targets.json"
    json.dump(targets, open(tpath, "w"), indent=1)

    sim_rows, n_posts = run_sims(targets, tag, tpath, dry_run)
    fr.summarize_gates(sim_rows)                         # annotate n_pass / fails / robust
    reserve = max(1, TOP_N // 5)                         # reserve-sharpe rule (rank_gates default)
    top27 = rg.rank_rows(sim_rows, TOP_N, reserve_sharpe=reserve)

    lg = logic_check.check(targets, strict=False)        # L0 report over the swept targets
    top_path = FUN / f"{run}_stage3_top{TOP_N}.json"
    json.dump(top27, open(top_path, "w"), indent=2)

    manifest = {
        "run": run, "dry_run": dry_run, "escalation_triggered": True,
        "seed_gates": per_seed,
        "n_seeds": N_SEEDS, "n_configs_per_seed": N_CONFIGS,
        "n_targets": len(targets), "n_posts": n_posts, "n_simmed": len(sim_rows),
        "targets_file": str(tpath.relative_to(ROOT)),
        "reserve_sharpe": reserve,
        "logic_check": {"n_block": lg["n_block"], "ok": lg["ok"]},
        "choices": [{"seed": per_seed[i]["id"], "field1": c["field1"], "field2": c["field2"],
                     "third_field": c["third_field"], "seed_structure": c["seed_structure"],
                     "structure": c["structure"]} for i, c in enumerate(choices)],
        "top27_file": str(top_path.relative_to(ROOT)),
        "top27": [r["id"] for r in top27],
        "top27_robust_pass": [r["robust_universe_pass"] for r in top27],
        "top27_sharpe_reserved": [r.get("sharpe_reserved", False) for r in top27],
    }
    json.dump(manifest, open(man_path, "w"), indent=1, sort_keys=True)
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top9", required=True, help="top-9 seeds json (rank_gates output)")
    ap.add_argument("--choices", required=True,
                    help="json list of EXACTLY 9 {field1,field2,seed_structure,third_field,structure}")
    ap.add_argument("--run", required=True, help="run name (namespaces all output)")
    ap.add_argument("--dry-run", action="store_true",
                    help="mock sim; proves wiring end-to-end without the WQ API")
    a = ap.parse_args(argv)

    top9 = load_rows(pathlib.Path(a.top9))
    choices = json.load(open(a.choices))
    if isinstance(choices, dict):
        choices = choices.get("choices") or choices.get("stage3") or []

    m = run_stage3(a.run, top9, choices, a.dry_run)
    if not m["escalation_triggered"]:
        print(f"NO ESCALATION: {m['reason']}")
        return 0
    print(f"ESCALATED: {m['n_targets']} targets -> {m['n_posts']} multi-sim POSTs "
          f"({m['n_simmed']} simmed)")
    print(f"logic_check: blocking={m['logic_check']['n_block']} ok={m['logic_check']['ok']}")
    print(f"TOP{TOP_N} ({len(m['top27'])}): {m['top27'][:5]} ...")
    print(f"manifest -> {FUN / (a.run + '_stage3_manifest.json')}")
    print(f"top{TOP_N} -> {m['top27_file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
