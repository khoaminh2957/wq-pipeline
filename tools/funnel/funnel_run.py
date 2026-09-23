#!/usr/bin/env python3
"""funnel_run.py — ALPHA_PIPELINE v7 funnel orchestrator (funnel_orch component).

CHAINS the real funnel tools (does NOT reimplement them):

  STAGE 1   config_sweep.generate       -> 100 single-field config variants
            run_multisim.plan_batches   -> verified 10 multi-sim POSTs x 10 children
            [sim]                       -> gate results (mock in --dry-run)
            fetch_gates.gates_from_alpha_json -> gate summaries (gates ONLY, no recordsets)
            rank_gates.rank_rows        -> TOP 5
  STAGE 2   for each top-5 seed: second_field_sweep.generate (operator/LLM-chosen
            second field from the SAME dataset in a DIFFERENT structure) -> 100
            variants each -> sim -> gates -> pooled 500
            rank_gates.rank_rows        -> TOP 25
  BENCHMARK alpha_benchmark.score_alphas -> deterministic quality scores; written to
            state/benchmark/<run>_benchmark.json

Run-spec json (see state/funnel/example_spec.json):
  {run, root:{field,dataset,region,universe,delay},
   stage2:[{second_field,structure}, ... x5]}   # structures: multiply|if_else|divide

--dry-run replaces the sim with a deterministic MOCK that stamps fake gate results
(alternating the two journal check encodings: full rows vs PASS-name list) so the
whole funnel wires end-to-end WITHOUT the WQ API. The live path (run_multisim ->
resim_bulk, one POST per 10 homogeneous children) is integration-run-by-operator.

v7 iteration-2 fixes:
  S10-20/22  every stage batch is BLOCKED behind precheck_lib.precheck(...,
             run_validate=True) (novelty + dup + legality + validate_targets.py,
             the v6.2 C6 blocking validate) BEFORE any live POST; the same gate
             runs in --dry-run to prove the wiring. All local, no API.
  S10-21     stage2 is enforced: EXACTLY 5 second-field choices (one per top-5
             seed), each second field verified to belong to the root's dataset
             via the local field catalogs (fetched/*), structure valid and
             different from the root's structure, second field != root field.

Determinism: everything derives from the run name + spec; no timestamps in output.
Emits state/funnel/<run>_manifest.json tracking each stage.
"""
from __future__ import annotations
import argparse, hashlib, json, math, pathlib, random, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import config_sweep                     # noqa: E402  stage-1 generator (Khoa ts_quantile pool)
import second_field_sweep as sfs        # noqa: E402  stage-2 two-field structure sweep
import run_multisim as rms              # noqa: E402  resim_bulk 10x10 batch planner/launcher
import fetch_gates as fg                # noqa: E402  gates-only parser (pure part)
import rank_gates as rg                 # noqa: E402  deterministic robust-first top-N selector
import alpha_benchmark as ab            # noqa: E402  deterministic post-crawl scorer
import precheck_lib                     # noqa: E402  C5/C6 novelty+dup+legality+validate gate

ST = ROOT / "state"
FUN = ST / "funnel"
BENCH = ST / "benchmark"
RESULTS = ST / "resim_results.jsonl"
ROBUST_PREFIX = "LOW_ROBUST_UNIVERSE_SHARPE"

# gate names the MOCK stamps (real sims return whatever the platform sends; nothing
# downstream hard-codes this list — fetch_gates/rank_gates read the returned checks)
MOCK_GATES = ["LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER", "HIGH_TURNOVER",
              "LOW_SUB_UNIVERSE_SHARPE", "LOW_2Y_SHARPE", "LOW_RETURNS",
              "CONCENTRATED_WEIGHT", "LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO"]


def _seed(*parts) -> int:
    h = hashlib.blake2b(json.dumps(parts, sort_keys=True).encode(), digest_size=8)
    return int.from_bytes(h.digest(), "big")


# ------------------------------------------------------------------ field catalogs (local)
# Every locally crawled field catalog that maps field id -> dataset id.
FIELD_CATALOG_GLOBS = ["fetched/fields_all.jsonl", "fetched/rc/fields/*.jsonl",
                       "fetched/catalog_*/fields.jsonl",
                       "fetched/catalog_*/fields_per_dataset.jsonl"]


def field_datasets(field: str) -> set:
    """All dataset ids the local catalogs record for `field` (empty if unknown).
    Cheap substring prefilter, then exact-id JSON check. LOCAL FILES ONLY."""
    needle = f'"{field}"'
    out = set()
    for pat in FIELD_CATALOG_GLOBS:
        for p in sorted(ROOT.glob(pat)):
            try:
                lines = open(p)
            except OSError:
                continue
            for line in lines:
                if needle not in line:
                    continue
                try:
                    j = json.loads(line)
                except ValueError:
                    continue
                if j.get("id") == field and isinstance(j.get("dataset"), dict):
                    ds = j["dataset"].get("id")
                    if ds:
                        out.add(ds)
    return out


def _assert_same_dataset(field: str, dataset: str, what: str):
    """S10-21: `field` must belong to `dataset` per the local catalogs. A field
    absent from every catalog cannot be verified -> hard stop (crawl it first)."""
    found = field_datasets(field)
    if not found:
        raise SystemExit(f"{what}: field {field!r} not in any local field catalog "
                         f"({', '.join(FIELD_CATALOG_GLOBS)}) — cannot verify it belongs "
                         f"to dataset {dataset!r}; crawl the catalog first")
    if dataset not in found:
        raise SystemExit(f"{what}: field {field!r} belongs to dataset(s) {sorted(found)}, "
                         f"not the root dataset {dataset!r} — stage2 second field must "
                         f"come from the SAME dataset")


# ------------------------------------------------------------------ precheck (C6 blocking)
def precheck_gate(variants, tpath, tag: str) -> dict:
    """S10-20/22: blocking pre-sim gate for EVERY stage batch, live AND dry-run.
    Chains precheck_lib (novelty + dup + settings legality) WITH run_validate=True
    (tools/validate_targets.py, the v6.2 C6 blocking validate). Local files only."""
    # sweep=True: every funnel_run batch is a SANCTIONED same-root-field config sweep
    # (stage1 = config_sweep of ONE field; stage2 = second_field_sweep of a fixed
    # field-pair), so the coarse (fields,grammar) family-novelty block must be skipped
    # here — mirrors run_multisim.precheck_gate / funnel_stage3 (Khoa 2026-07-17).
    # Without it, one prior-simulated family collision falsely NOT-NOVELs a row and
    # SystemExits the whole 180-config batch. Exact dup, legality, NO_GO still apply.
    res = precheck_lib.precheck(variants, run_validate=True, targets_path=tpath, sweep=True)
    n_errs = sum(len(v) for v in res["per_row_errors"].values())
    if not res["ok"]:
        for row_tag, msgs in sorted(res["per_row_errors"].items())[:8]:
            for m in msgs[:2]:
                print(f"  [{tag}] PRECHECK {row_tag}: {m}", file=sys.stderr)
        raise SystemExit(f"[{tag}] PRECHECK FAILED ({n_errs} errors in "
                         f"{len(res['per_row_errors'])} rows) — no sim POST for this batch")
    return {"ok": True, "n_rows": len(variants), "n_errors": 0, "validate_targets": True}


# ------------------------------------------------------------------ mock sim (dry-run)
def mock_sim(variants, salt: str):
    """Deterministic fake gate results. Alternates the two journal check encodings
    (full rows / PASS-name list) so both downstream parse paths are exercised."""
    out = []
    for i, v in enumerate(variants):
        rng = random.Random(_seed(salt, v["old_id"], v["formula"]))
        st = v["settings"]
        bar = ab.lookup_bar(st["region"], st["delay"], 1.25)
        sharpe = round(rng.uniform(0.5, 1.9) * bar, 3)
        rows, pass_names = [], []
        for g in MOCK_GATES:
            if g == "LOW_SHARPE":
                res, val, lim = ("PASS" if sharpe >= bar else "FAIL"), sharpe, bar
            else:
                res = "PASS" if rng.random() > 0.35 else "FAIL"
                val, lim = round(rng.uniform(0, 2), 3), 1.0
            rows.append({"name": g, "result": res, "value": val, "limit": lim})
            if res == "PASS":
                # journal PASS-name lists carry the bare robust name; full rows the .WITH_RATIO one
                pass_names.append(ROBUST_PREFIX if g.startswith(ROBUST_PREFIX) else g)
        out.append({"id": v["old_id"], "old_id": v["old_id"], "alpha": f"MOCK_{v['old_id']}",
                    "status": "COMPLETE", "sharpe": sharpe,
                    "checks": rows if i % 2 == 0 else pass_names,
                    "region": st["region"], "delay": st["delay"],
                    "formula": v["formula"], "settings": st})
    return out


# ------------------------------------------------------------------ sim dispatch
def _verify_batch_plan(variants, tag: str) -> int:
    """Chain run_multisim's planner: N homogeneous rows -> ceil(N/BATCH) multi-sim POSTs."""
    batch = rms._read_batch_const()
    batches = rms.plan_batches(variants, batch)
    expected = math.ceil(len(variants) / batch)
    if len(batches) != expected:
        raise SystemExit(f"[{tag}] batch plan {len(batches)} POSTs != ceil({len(variants)}/{batch})")
    for bi, g in enumerate(batches):
        if len(g) > batch or len({rms._gkey(a) for a in g}) != 1:
            raise SystemExit(f"[{tag}] batch {bi} oversized or not homogeneous")
    return len(batches)


def _journal_results(variants, tag: str):
    """Live: read state/resim_results.jsonl rows for these old_ids; merge variant context.
    Rows journaled without checks get their gates fetched (gates ONLY) via fetch_gates."""
    by = {}
    if RESULTS.exists():
        for line in open(RESULTS):
            try:
                j = json.loads(line)
            except Exception:
                continue
            if j.get("old_id"):
                by[j["old_id"]] = j
    results, missing = [], []
    for v in variants:
        j = by.get(v["old_id"])
        if not j:
            missing.append(v["old_id"])
            continue
        st = v["settings"]
        results.append({**j, "id": v["old_id"], "region": st["region"], "delay": st["delay"],
                        "formula": v["formula"], "settings": st})
    if missing:
        print(f"  [{tag}] {len(missing)}/{len(variants)} sims not in resim_results.jsonl "
              f"— operator must complete the resim_bulk run", file=sys.stderr)
    need = [r for r in results if not r.get("checks") and r.get("alpha")]
    if need:  # gates-only top-up (integration-run-by-operator; never in --dry-run)
        gp = fg.fetch_gates([r["alpha"] for r in need], f"{tag}_gatefix")
        gmap = {json.loads(l)["sid"]: json.loads(l) for l in open(gp)}
        for r in need:
            g = gmap.get(r["alpha"])
            if g:
                r["checks"] = g["checks"]
    return results


def run_sims(variants, tag: str, dry_run: bool):
    """Write stage targets, verify the 10x10 multi-sim plan, run the BLOCKING
    precheck gate (S10-20/22), then sim (mock or live)."""
    FUN.mkdir(parents=True, exist_ok=True)
    tpath = FUN / f"{tag}_targets.json"
    json.dump(variants, open(tpath, "w"), indent=1)
    n_posts = _verify_batch_plan(variants, tag)
    pre = precheck_gate(variants, tpath, tag)   # raises before any live POST
    if dry_run:
        return mock_sim(variants, tag), n_posts, tpath, pre
    rms.live_launch(tpath)   # integration-run-by-operator (single-stream, resim_bulk)
    return _journal_results(variants, tag), n_posts, tpath, pre


# ------------------------------------------------------------------ gates
def summarize_gates(sim_rows):
    """Chain fetch_gates' pure parser over each sim row (handles BOTH check encodings);
    annotate n_pass / fails / prefix-matched robust pass. Ranking itself is rank_gates'."""
    for r in sim_rows:
        g = fg.gates_from_alpha_json({"checks": r.get("checks") or []})
        r["n_pass"] = g["n_pass"]
        r["fails"] = g["fails"]
        r["robust_universe_pass"] = any(
            str(n).startswith(ROBUST_PREFIX) and res == "PASS"
            for n, res in g["checks"].items())
    return sim_rows


# ------------------------------------------------------------------ orchestrator
def run_funnel(spec: dict, dry_run: bool):
    run = spec["run"]
    root = spec["root"]
    region, universe, delay = root["region"], root["universe"], root["delay"]
    root_structure = root.get("structure")
    choices = spec.get("stage2") or []
    # S10-21: EXACTLY 5 choices (one per top-5 seed), structure legal and != root's,
    # second field a DIFFERENT field from the SAME dataset (verified vs local catalogs).
    if len(choices) != 5:
        raise SystemExit(f"spec.stage2 must list EXACTLY 5 second-field/structure "
                         f"choices (one per top-5 seed), got {len(choices)}")
    _assert_same_dataset(root["field"], root["dataset"], "root")
    for i, c in enumerate(choices):
        if c["structure"] not in sfs.STRUCTURES:
            raise SystemExit(f"stage2[{i}] structure {c['structure']!r} not in {list(sfs.STRUCTURES)}")
        if c.get("root_structure", root_structure) == c["structure"]:
            raise SystemExit(f"stage2[{i}] structure {c['structure']!r} must DIFFER "
                             f"from the root structure")
        if c["second_field"] == root["field"]:
            raise SystemExit(f"stage2[{i}] second_field must differ from root field "
                             f"{root['field']!r}")
        _assert_same_dataset(c["second_field"], root["dataset"], f"stage2[{i}]")

    # STAGE 1 — root single field -> 100 configs -> sim -> gates -> top5
    v1 = config_sweep.generate({"field": root["field"], "dataset": root["dataset"],
                                "region": region, "universe": universe, "delay": delay,
                                "run": run}, seed=_seed(run, "s1"))
    r1, posts1, t1, pre1 = run_sims(v1, f"{run}_stage1", dry_run)
    g1 = summarize_gates(r1)
    top5 = rg.rank_rows(g1, 5)

    # STAGE 2 — per top-5 seed: second field (SAME dataset) in a DIFFERENT structure
    stage2_rows, seeds_manifest = [], []
    for i, seed_row in enumerate(top5):
        choice = choices[i]              # exactly one choice per top-5 seed (S10-21)
        v2 = sfs.generate(root["field"], choice["second_field"], choice["structure"],
                          region, universe, delay,
                          root_structure=choice.get("root_structure", root_structure),
                          n=100, label=f"{run}_stage2_seed{i}")
        for r in v2:  # namespace ids per seed (sfs ids repeat across seeds)
            r["id"] = r["old_id"] = f"{run}_seed{i}_{r['old_id']}"
        r2, posts2, t2, pre2 = run_sims(v2, f"{run}_stage2_seed{i}", dry_run)
        stage2_rows.extend(summarize_gates(r2))
        seeds_manifest.append({"seed_root": seed_row["old_id"],
                               "seed_root_robust": seed_row["robust_universe_pass"],
                               "second_field": choice["second_field"],
                               "same_dataset_verified": True,   # _assert_same_dataset gate
                               "structure": choice["structure"],
                               "targets_file": str(t2.relative_to(ROOT)),
                               "n_variants": len(v2), "n_posts": posts2,
                               "n_simmed": len(r2), "precheck": pre2})

    top25 = rg.rank_rows(stage2_rows, 25)

    # BENCHMARK — chain alpha_benchmark's deterministic scorer (no timestamp: repeatable)
    bench_alphas = ab.score_alphas(top25)
    bench = {"run": run, "n": len(bench_alphas),
             "bars": {f"{k[0]}_d{k[1]}": v for k, v in ab.LOW_SHARPE_BARS.items()},
             "alphas": bench_alphas}
    BENCH.mkdir(parents=True, exist_ok=True)
    bench_path = BENCH / f"{run}_benchmark.json"
    json.dump(bench, open(bench_path, "w"), indent=1, sort_keys=True)

    manifest = {
        "run": run, "dry_run": dry_run, "root": root,
        "stage1": {"targets_file": str(t1.relative_to(ROOT)),
                   "n_variants": len(v1), "n_posts": posts1, "n_simmed": len(r1),
                   "precheck": pre1,
                   "top5": [t["old_id"] for t in top5],
                   "top5_robust_pass": [t["robust_universe_pass"] for t in top5],
                   "top5_n_pass": [t["n_pass"] for t in top5]},
        "stage2": {"seeds": seeds_manifest,
                   "total_variants": sum(m["n_variants"] for m in seeds_manifest),
                   "total_posts": sum(m["n_posts"] for m in seeds_manifest),
                   "total_simmed": sum(m["n_simmed"] for m in seeds_manifest)},
        "top25": [t["old_id"] for t in top25],
        "top25_robust_pass": [t["robust_universe_pass"] for t in top25],
        "benchmark_file": str(bench_path.relative_to(ROOT)),
        "benchmark_top1": bench_alphas[0] if bench_alphas else None,
    }
    man_path = FUN / f"{run}_manifest.json"
    json.dump(manifest, open(man_path, "w"), indent=1, sort_keys=True)
    return manifest, bench, man_path, bench_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", required=True, help="run-spec json")
    ap.add_argument("--run", help="override run name from spec")
    ap.add_argument("--dry-run", action="store_true",
                    help="mock sim; proves the wiring end-to-end without the WQ API")
    a = ap.parse_args()
    spec = json.load(open(a.spec))
    if a.run:
        spec["run"] = a.run
    manifest, bench, man_path, bench_path = run_funnel(spec, a.dry_run)
    s1, s2 = manifest["stage1"], manifest["stage2"]
    print(f"STAGE1: {s1['n_variants']} variants -> {s1['n_posts']} POSTs -> top5 {s1['top5']}")
    print(f"STAGE2: {s2['total_variants']} variants -> {s2['total_posts']} POSTs "
          f"({len(s2['seeds'])} seeds)")
    print(f"TOP25 ({len(manifest['top25'])}): {manifest['top25'][:5]} ...")
    top1 = manifest["benchmark_top1"]
    print(f"benchmark top1: {top1['id'] if top1 else None} "
          f"composite={top1['composite'] if top1 else None}")
    print(f"manifest -> {man_path}")
    print(f"benchmark -> {bench_path}")


if __name__ == "__main__":
    main()
