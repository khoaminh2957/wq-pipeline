#!/usr/bin/env python3
"""v3_retrospective.py — OFFLINE proof that v3 beats v1/v2 on cost + correctness (2026-07-18).

Replays the WHOLE historical sim record (state/resim_results.jsonl) through v3's two core changes:
  (A) CORRECTED win-condition (submittable.py): submittable requires IS_LADDER_SHARPE PASS, not the
      v1/v2 "no hard FAIL among WARNINGs" (which never checked the real recency ladder).
  (B) EARLY-ABORT probe: v3 runs a PROBE_N-config subsample first; if a root's failure is
      CONFIG-INVARIANT (the probe gates fail on ALL of its configs) v3 aborts the root after PROBE_N
      sims instead of the full 90-180. Sims saved = (n_configs - PROBE_N) for each structurally-dead root.

Honest guardrail: early-abort is only credited when the kill is config-invariant (100% of the root's
configs fail the probe gate), so it can NEVER have discarded a would-be winner. Roots with ANY passing
config are marked NOT-safely-abortable and get NO savings credit.
"""
from __future__ import annotations
import json, pathlib, re, sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools" / "funnel"))
import submittable  # noqa: E402

PROBE_N = 12          # v3 early-abort probe size
PROBE_GATES = ("IS_LADDER_SHARPE", "LOW_SUB_UNIVERSE_SHARPE")  # config-invariant structural gates


def _root_of(old_id):
    """Group configs by their sweep root: strip trailing _<config-index> then _s<stage>."""
    if not old_id:
        return "?"
    s = re.sub(r"[_-]\d{2,4}$", "", old_id)   # drop config index (_030 / _001)
    s = re.sub(r"[_-]s\d+$", "", s)           # drop stage tag (_s1 / _s2)
    return s or old_id


def run():
    rows = []
    for l in open(ROOT / "state/resim_results.jsonl"):
        l = l.strip()
        if not l:
            continue
        try:
            rows.append(json.loads(l))
        except Exception:
            continue

    by_root = defaultdict(list)
    for r in rows:
        by_root[_root_of(r.get("old_id") or "")].append(r)

    SWEEP_MIN = 30                # a root with >=30 configs is a real 90-180 sweep (early-abort applies)
    total_sims = len(rows)
    v1v2_submittable_claims = 0   # rows v1/v2 would call zero-fail (no hard FAIL, WARNING ok, IS_LADDER ignored)
    v3_submittable = 0
    sweep_full_sims = 0           # sims spent inside real sweeps (where early-abort can act)
    sweep_v3_sims = 0
    safely_aborted_roots = 0
    kept_roots = 0
    per_root = []

    for root, cfgs in sorted(by_root.items()):
        n = len(cfgs)
        # v3 correct submittable count
        subs = [submittable.verdict(c) for c in cfgs]
        n_v3_sub = sum(1 for s in subs if s["submittable"])
        v3_submittable += n_v3_sub
        # v1/v2 "zero-fail" (ignores IS_LADDER, WARNING ok) — the old crown
        def old_zero_fail(c):
            ch = {x["name"]: x.get("result") for x in c.get("checks", []) if isinstance(x, dict) and "name" in x}
            if not ch:            # a row with NO checks is NOT a genuine crown (fixes the inflated-1000 artifact)
                return False
            return not any(v == "FAIL" for k, v in ch.items()
                           if k not in ("IS_LADDER_SHARPE",) and k not in submittable.PENDING)
        n_old = sum(1 for c in cfgs if old_zero_fail(c))
        v1v2_submittable_claims += n_old
        # early-abort: is the kill config-invariant across PROBE_GATES?
        def fails_probe(c):
            ch = {x["name"]: x.get("result") for x in c.get("checks", []) if isinstance(x, dict) and "name" in x}
            return any(ch.get(g) == "FAIL" for g in PROBE_GATES)
        n_fail_probe = sum(1 for c in cfgs if fails_probe(c))
        config_invariant_dead = (n_fail_probe == n) and (n_v3_sub == 0)
        is_sweep = n >= SWEEP_MIN
        abortable = is_sweep and config_invariant_dead and n > PROBE_N
        if is_sweep:
            sweep_full_sims += n
            if abortable:
                sweep_v3_sims += PROBE_N
                safely_aborted_roots += 1
            else:
                sweep_v3_sims += n
                kept_roots += 1
        per_root.append({"root": root, "n_configs": n, "best_sharpe": round(max((c.get("sharpe") or -9) for c in cfgs), 3),
                         "v1v2_zero_fail": n_old, "v3_submittable": n_v3_sub,
                         "probe_fail_rate": round(n_fail_probe / n, 3), "is_sweep": is_sweep, "early_abortable": abortable})

    print("=" * 78)
    print("v3 RETROSPECTIVE — replay of the full historical sim record")
    print("=" * 78)
    print(f"total roots grouped: {len(by_root)} | total sims run (v1/v2 actual): {total_sims}")
    print()
    print("CORRECTNESS (win-condition):")
    print(f"  v1/v2 'zero-fail' claims (crown, IS_LADDER ignored): {v1v2_submittable_claims}")
    print(f"  v3 TRULY submittable (IS_LADDER PASS + real gates):  {v3_submittable}")
    print(f"  -> v1/v2 falsely crowned {v1v2_submittable_claims - v3_submittable} non-submittable alphas as winners")
    print()
    # ---- cell-saturation auto-stop: process sweeps in chronological (first-seen) order; v3 stops mining
    #      the cell after STOP_AFTER consecutive 0-submittable sweeps whose best sharpe never nears the
    #      IS-Ladder floor (< NEAR_FLOOR). All sweep sims after the stop are WASTE v3 would have avoided.
    STOP_AFTER, NEAR_FLOOR = 8, 1.4
    first_seen = {}
    for i, r in enumerate(rows):
        rt = _root_of(r.get("old_id") or "")
        if rt not in first_seen:
            first_seen[rt] = i
    sweep_roots_chrono = sorted([p for p in per_root if p["is_sweep"]], key=lambda p: first_seen.get(p["root"], 1 << 30))
    consec, stop_idx, sims_before = 0, None, 0
    for i, pr in enumerate(sweep_roots_chrono):
        if stop_idx is None:
            sims_before += pr["n_configs"]
        if pr["v3_submittable"] == 0 and pr["best_sharpe"] < NEAR_FLOOR:
            consec += 1
        else:
            consec = 0
        if stop_idx is None and consec >= STOP_AFTER:
            stop_idx = i
    sims_wasted_after_stop = sum(p["n_configs"] for p in sweep_roots_chrono[stop_idx + 1:]) if stop_idx is not None else 0

    n_sweeps = safely_aborted_roots + kept_roots
    print(f"COST — early-abort on real sweeps (>= {SWEEP_MIN} configs), PROBE_N={PROBE_N}:")
    print(f"  identified sweeps: {n_sweeps} ({sweep_full_sims} sims)")
    print(f"  sims v1/v2 spent in sweeps:   {sweep_full_sims}")
    print(f"  sims v3 would spend in sweeps:{sweep_v3_sims}")
    saved = sweep_full_sims - sweep_v3_sims
    pct = 100 * saved / sweep_full_sims if sweep_full_sims else 0
    print(f"  -> sims SAVED in sweeps by v3: {saved} ({pct:.1f}%) | safely early-aborted: {safely_aborted_roots}/{n_sweeps} sweeps")
    print()
    print(f"COST — cell-saturation AUTO-STOP: RETRACTED as a headline (hindsight-fit).")
    if stop_idx is not None:
        stop_pct = 100 * sims_wasted_after_stop / sweep_full_sims if sweep_full_sims else 0
        print(f"  (illustrative only) an 8-consec/best<1.4 rule would fire at sweep #{stop_idx + 1}, nominally {stop_pct:.0f}% of sweep sims,")
        print(f"  BUT it forecloses later fresh families that EXCEED 1.4 (dsp_dmsrev 1.45, purifrev 1.43) -> NOT a safe/honest saving.")
        print(f"  Magic constants (STOP_AFTER={STOP_AFTER}, NEAR_FLOOR={NEAR_FLOOR}) lack sensitivity analysis. DO NOT cite this number.")
    print()
    print("real sweeps (n>=%d) — all v3_sub should be 0 and best_sh <1.59 if the cell is saturated:" % SWEEP_MIN)
    for pr in sorted([p for p in per_root if p["is_sweep"]], key=lambda x: -x["best_sharpe"]):
        print(f"  {pr['root'][:30]:30s} n={pr['n_configs']:3d} best_sh={pr['best_sharpe']:+.2f} "
              f"v1v2_zf={pr['v1v2_zero_fail']:3d} v3_sub={pr['v3_submittable']} probe_fail={pr['probe_fail_rate']:.2f} abort={pr['early_abortable']}")
    return {"total_sims": total_sims, "v1v2_claims": v1v2_submittable_claims, "v3_submittable": v3_submittable,
            "n_sweeps": n_sweeps, "sweep_sims": sweep_full_sims, "sweep_v3_sims": sweep_v3_sims,
            "sweep_saved": saved, "sweep_saved_pct": round(pct, 1), "safely_aborted_roots": safely_aborted_roots}


if __name__ == "__main__":
    import json as _j
    res = run()
    _j.dump(res, open(ROOT / "v3/retrospective_result.json", "w"), indent=1)
    print("\nsaved v3/retrospective_result.json")
