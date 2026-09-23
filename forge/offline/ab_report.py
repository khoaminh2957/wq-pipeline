"""A/B report: the current planner vs the typed grammar, per round and pooled (Khoa 2026-09-07 tick:
50/50 per round, >= 5 rounds, same cells and settings grid).

Rows are the forge journal rows carrying meta.arm ("current" | "typed"); a round is meta.seed.
Per arm: n, Sharpe p50 / p90 / max, share >= 1.58, platform passes, DSR candidates, distinct
passing mechanisms, and the platform's most frequent failing check. Nothing here is a verdict:
the verdict is Khoa's after >= 5 rounds (RULE 2 gate 3), and the confound to state first is that
the two arms draw from different field sets (the typed arm only from fields with a stated sign).
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from forge import harvest as HV, score as SC, submit as SUB  # noqa: E402

# Every arm that has ever been tagged. A hardcoded subset drops a new arm SILENTLY, which is how an
# experiment reads as "no rows" instead of "not counted" (llmformula added 2026-09-19).
ARMS = ("current", "typed", "new", "llmformula", "pow15", "pow2")


def _q(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def arm_stats(rows: list, scored: dict, corr: dict | None = None, posted: set | None = None) -> dict:
    """The funnel per arm (harness5 leading indicators): rows ≥ bar → binding PASS → DSR → corr under
    both lines → POSTed (ACTIVE) → distinct passing mechanisms."""
    corr, posted = corr or {}, posted or set()
    sh = [r["sharpe"] for r in rows if isinstance(r.get("sharpe"), (int, float))]
    stages = [SC.stage(r) for r in rows]
    passes = [r for r, st in zip(rows, stages) if st["stage"] not in ("fail", "incomplete")]
    fails = collections.Counter(f for st in stages for f in st.get("failed", []))
    cand = [r for r in passes if (scored.get(r["alpha"], {}).get("dsr") or 0) >= 0.95]
    # "under the lines" is what the SUBMITTER accepts: the row's own PROD/SELF limits, else 0.7
    # (forge.submit.corr_lines) -- not a constant, so the funnel and the POST path cannot disagree.
    under = []
    for r in cand:
        c = corr.get(r["alpha"], {})
        pl, sl = SUB.corr_lines(r)
        if isinstance(c.get("prod"), (int, float)) and isinstance(c.get("self"), (int, float)) and c["prod"] < pl and c["self"] < sl:
            under.append(r)
    return {"n": len(rows), "sharpe_p50": round(_q(sh, 0.5), 2) if sh else None, "sharpe_p90": round(_q(sh, 0.9), 2) if sh else None,
            "sharpe_max": round(max(sh), 2) if sh else None, "ge_1_58": sum(1 for x in sh if x >= 1.58),
            "pass": len(passes), "dsr_cand": len(cand), "corr_under": len(under),
            "posted": sum(1 for r in rows if r["alpha"] in posted),
            # distinct mechanism = mechanism_key (00_agreements "derived definitions"); hypotheses kept beside it
            "mechanisms": len({(r.get("meta") or {}).get("mechanism_key") for r in passes}),
            "hypotheses": len({(r.get("meta") or {}).get("hypothesis") for r in passes}),
            "top_fail": fails.most_common(2)}


def report(journal=HV.JOURNAL, scored_path=ROOT / "state/forge/scored.jsonl") -> dict:
    latest = {}
    for r in HV.read_jsonl(journal):
        if r.get("alpha") and (r.get("meta") or {}).get("arm") in ARMS:
            latest[r["alpha"]] = r           # one alpha = one simulation (orphan recovery wrote 158 second rows, 09-06/07)
    rows = list(latest.values())
    scored = {}
    for j in HV.read_jsonl(scored_path) if pathlib.Path(scored_path).exists() else []:
        scored[j["alpha"]] = j
    corr = {}
    cpath = ROOT / "state/forge/corr.jsonl"
    for j in HV.read_jsonl(cpath) if cpath.exists() else []:
        c = corr.setdefault(j["alpha"], {})
        for k in ("prod", "self"):
            if isinstance(j.get(k), (int, float)):
                c[k] = j[k]
    lpath = ROOT / "state/forge/submitted.jsonl"
    posted = {j["alpha"] for j in HV.read_jsonl(lpath) if j.get("http") in (200, 201)} if lpath.exists() else set()
    by_round = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        by_round[(r.get("meta") or {}).get("seed")][r["meta"]["arm"]].append(r)
    out = {"rounds": [], "pooled": {}}
    for seed in sorted(k for k in by_round if k is not None):
        out["rounds"].append({"seed": seed, **{arm: arm_stats(v, scored, corr, posted) for arm, v in by_round[seed].items()}})
    for arm in sorted({r["meta"]["arm"] for r in rows}):
        out["pooled"][arm] = arm_stats([r for r in rows if r["meta"]["arm"] == arm], scored, corr, posted)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rep = report()
    if a.json:
        print(json.dumps(rep, indent=1))
        return 0
    print("A/B rounds: %d" % len(rep["rounds"]))
    for r in rep["rounds"]:
        for arm in ("current", "typed", "new"):
            s = r.get(arm)
            if s:
                print("  seed %s %-8s n %3d | sharpe p50 %s p90 %s max %s | >=1.58 %2d | pass %d | dsr %d | corr %d | posted %d | mech %d | fails %s"
                      % (r["seed"], arm, s["n"], s["sharpe_p50"], s["sharpe_p90"], s["sharpe_max"], s["ge_1_58"], s["pass"], s["dsr_cand"],
                         s["corr_under"], s["posted"], s["mechanisms"], s["top_fail"]))
    print("pooled:")
    for arm, s in rep["pooled"].items():
        print("  %-8s n %4d | sharpe p50 %s p90 %s max %s | >=1.58 %3d (%.1f%%) | pass %d | dsr %d | corr %d | posted %d | mech %d | fails %s"
              % (arm, s["n"], s["sharpe_p50"], s["sharpe_p90"], s["sharpe_max"], s["ge_1_58"], 100.0 * s["ge_1_58"] / max(1, s["n"]),
                 s["pass"], s["dsr_cand"], s["corr_under"], s["posted"], s["mechanisms"], s["top_fail"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
