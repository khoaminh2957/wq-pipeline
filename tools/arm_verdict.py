#!/usr/bin/env python3
"""Judge each arm against the prediction ITERATIONS.md I3/I4 registered BEFORE the simulations ran.

The comparison that matters is the prod-correlation DISTRIBUTION per arm, measured on a random
sample regardless of gate outcome (see tools/measure_arms.py for why). Gate yield is reported
alongside but never substituted for it: A4 and A5 were predicted to lose most rows to the gates,
and judging them on yield would answer a question nobody asked.

Registered thresholds, repeated here so the verdict cannot drift from them:

    A1 speed      supported if median prod <= A0 median - 0.05 ; refuted if within 0.02
    A2 skeleton   supported if median prod <= A0 median - 0.05 ; refuted if within 0.02
    A3 universe   supported ONLY if some alpha has prod < 0.70 AND sharpe >= 1.58
    A4 carrier    control -- judged on its prod distribution, not its yield
    A5 field set  supported if median prod < 0.70, or <= A0 median - 0.08 ; refuted if within 0.03

A median difference is reported with the per-arm sample size next to it. With ~30 per arm a gap of
0.05 in medians is not a formality -- it is roughly the resolution this design can see, which is
why the thresholds were set there rather than lower.
"""
import argparse, collections, json, pathlib, statistics as stt

ROOT = pathlib.Path(__file__).resolve().parent.parent

THRESH = {"A1": ("drop", 0.05, 0.02), "A2": ("drop", 0.05, 0.02),
          "A3": ("joint", None, None), "A4": ("control", None, None),
          "A5": ("drop", 0.08, 0.03)}


def load(pool_paths):
    arm_of, cell_of = {}, {}
    for p in pool_paths:
        for r in json.load(open(ROOT / p)):
            arm_of[r["old_id"]] = r["meta"]["arm"]
            cell_of[r["old_id"]] = r["meta"]["cell"]
    sim = {}
    for line in open(ROOT / "state/resim_results.jsonl"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("old_id") in arm_of:
            sim[r["old_id"]] = r
    corr = {}
    f = ROOT / "state/funnel/arm_corr.jsonl"
    if f.exists():
        for line in open(f):
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("prod") is not None:
                corr[d["old_id"]] = d
    return arm_of, cell_of, sim, corr


def zero_fail(row):
    ck = row.get("checks") or []
    if not ck or not any(isinstance(c, dict) for c in ck):
        return False
    return not any(isinstance(c, dict) and c.get("result") == "FAIL" for c in ck)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pools", nargs="+",
                    default=["state/autoloop/pool_arms_t3.json", "state/autoloop/pool_arms_t1.json"])
    args = ap.parse_args()
    arm_of, cell_of, sim, corr = load(args.pools)

    per = collections.defaultdict(lambda: {"sim": 0, "zf": 0, "err": 0, "prod": [], "self": [],
                                           "clean": []})
    for oid, arm in arm_of.items():
        r = sim.get(oid)
        if r:
            per[arm]["sim"] += 1
            # HYPOTHESES.md measurement precondition 3: report the ERROR rate per arm BEFORE
            # comparing anything. An arm that loses a third of its rows to simulation errors is not
            # comparable to one that loses a tenth -- the survivors are a filtered sample, and the
            # filter is not random with respect to structure (more legs, rarer fields, and the
            # operator ceiling all bite unevenly across arms).
            if r.get("status") == "ERROR" or not r.get("checks"):
                per[arm]["err"] += 1
            elif zero_fail(r):
                per[arm]["zf"] += 1
        c = corr.get(oid)
        if c:
            per[arm]["prod"].append(c["prod"])
            if c.get("self") is not None:
                per[arm]["self"].append(c["self"])
            if c["prod"] < 0.70 and (c.get("self") is None or c["self"] < 0.70):
                per[arm]["clean"].append((oid, sim.get(oid, {}).get("alpha"), c["prod"], c.get("self")))

    print(f"{'arm':4} {'simmed':>7} {'ERROR':>12} {'zero-fail':>12} {'measured':>9} "
          f"{'medProd':>8} {'minProd':>8} {'<0.70':>6}")
    for arm in sorted(per):
        d = per[arm]
        p = d["prod"]
        med = f"{stt.median(p):.4f}" if p else "-"
        mn = f"{min(p):.4f}" if p else "-"
        n70 = sum(1 for x in p if x < 0.70)
        ok = d["sim"] - d["err"]
        errs = f"{d['err']}/{d['sim']} {100*d['err']/d['sim']:.0f}%" if d["sim"] else "-"
        zfr = f"{d['zf']}/{ok} {100*d['zf']/ok:.0f}%" if ok else "-"
        print(f"{arm:4} {d['sim']:7} {errs:>12} {zfr:>12} {len(p):9} {med:>8} {mn:>8} {n70:6}")
    print("  (zero-fail is a rate over EVALUABLE rows, not over rows dispatched)")

    base = per.get("A0", {}).get("prod") or []
    if not base:
        print("\nA0 has no measurement yet — no verdict can be issued.")
        return
    b = stt.median(base)
    print(f"\nA0 median prod = {b:.4f}  (n={len(base)})\n")
    for arm in sorted(THRESH):
        p = per.get(arm, {}).get("prod") or []
        if not p:
            print(f"{arm}: not measured yet")
            continue
        m = stt.median(p)
        kind, sup, ref = THRESH[arm]
        delta = m - b
        line = f"{arm}: median {m:.4f}  ({delta:+.4f} vs A0, n={len(p)})  -> "
        if kind == "drop":
            if delta <= -sup:
                line += f"SUPPORTED (predicted <= -{sup})"
            elif abs(delta) <= ref:
                line += f"REFUTED (within {ref})"
            else:
                line += "INCONCLUSIVE against the registered thresholds"
        elif kind == "joint":
            ok = [c for c in per[arm]["clean"]
                  if (sim.get(c[0]) or {}).get("sharpe", 0) >= 1.58]
            line += (f"SUPPORTED — {len(ok)} alpha(s) with prod<0.70 AND sharpe>=1.58"
                     if ok else "NOT SUPPORTED — no alpha cleared prod<0.70 with sharpe>=1.58")
        else:
            line += f"control — {sum(1 for x in p if x < 0.70)}/{len(p)} under 0.70"
        print(line)

    # CORR-CLEAN is not SUBMITTABLE. `ak1Mz5px` came back prod 0.6876 / self 0.674 with sharpe
    # 2.09 and fitness 1.30 and still FAILED on IS_LADDER_SHARPE 1.47 (limit 1.58) and
    # LOW_SUB_UNIVERSE_SHARPE 0.76 (limit 0.9). Printing it under a bare "CLEAN" invites exactly
    # the misreading this project keeps paying for, so the gate verdict prints on the same line.
    print()
    for arm in sorted(per):
        for oid, aid, pr, sf in per[arm]["clean"]:
            r = sim.get(oid) or {}
            ck = r.get("checks") or []
            fails = [c["name"] for c in ck if isinstance(c, dict) and c.get("result") == "FAIL"]
            tag = "SUBMITTABLE" if (ck and not fails) else f"corr-clean, GATES FAIL {fails}"
            print(f"  {arm} {aid} prod={pr} self={sf} sharpe={r.get('sharpe')} "
                  f"fitness={r.get('fitness')} cell={cell_of.get(oid)}\n      -> {tag}")


if __name__ == "__main__":
    raise SystemExit(main())
