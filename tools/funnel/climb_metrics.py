#!/usr/bin/env python3
"""climb_metrics.py — measure the climb: per-round best of EVERY metric, the running ceiling of each, and the
VELOCITY (rate of climb) of the composite score AND of each metric's ceiling. Saves state/funnel/climb_metrics.json
+ a readable report. (Khoa 2026-07-18: "đo đạt toàn bộ chỉ số kể cả tốc độ leo điểm, tốc độ leo trần của các chỉ số".)
"""
from __future__ import annotations
import json, pathlib, re, sys
from collections import OrderedDict

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools" / "funnel"))
import alpha_score as A  # noqa: E402

# climb-round roots are auto-discovered by pattern (baselines + every clim/fit/cc round) — no manual list to update
_CLIMB_RE = re.compile(r"^(srl2_s1|dsp_dmsrev|clim\d+|fit\d+|cc\d+)$")
def _is_climb_round(root):
    return bool(_CLIMB_RE.match(root or ""))
# metric -> higher-is-better direction for its ceiling
METRIC_DIR = {"composite": +1, "sharpe": +1, "fitness": +1, "returns": +1,
              "turnover": -1, "drawdown": -1, "sharpe_2y": +1, "sub_universe": +1}


def _best(rows, key, direction, scorer=None):
    vals = []
    for r in rows:
        if key == "composite":
            if A.AlphaScorer.ceiling_eligible(r):
                vals.append(scorer.score(r))
        else:
            m = A.extract(r).get(key)
            if isinstance(m, (int, float)):
                vals.append(m)
    if not vals:
        return None
    return max(vals) if direction > 0 else min(vals)


def run():
    scorer = A.AlphaScorer.load()
    allr = [r for r in (json.loads(l) for l in open(ROOT / "state/resim_results.jsonl") if l.strip())
            if isinstance(r, dict)]
    # group by round label (root prefix), keep only USA-d1 rounds we track, chronological by first-seen
    first_seen = {}
    groups = OrderedDict()
    for i, r in enumerate(allr):
        rt = A.root_of(r.get("old_id"))
        if not _is_climb_round(rt):
            continue
        groups.setdefault(rt, []).append(r)
        first_seen.setdefault(rt, i)
    order = sorted(groups, key=lambda L: first_seen[L])

    metrics = list(METRIC_DIR)
    ceiling = {m: None for m in metrics}     # running best-so-far
    report = []
    for ridx, lab in enumerate(order):
        rows = groups[lab]
        rb = {m: _best(rows, m, METRIC_DIR[m], scorer) for m in metrics}     # this round's best
        row = {"round": lab, "idx": ridx, "n_configs": len(rows), "round_best": {}, "ceiling": {},
               "advanced": {}, "velocity": {}}
        for m in metrics:
            b = rb[m]
            row["round_best"][m] = None if b is None else round(b, 4)
            prev = ceiling[m]
            adv = False
            if b is not None:
                if prev is None or (METRIC_DIR[m] > 0 and b > prev) or (METRIC_DIR[m] < 0 and b < prev):
                    ceiling[m] = b
                    adv = prev is not None      # first observation isn't an "advance"
            row["ceiling"][m] = None if ceiling[m] is None else round(ceiling[m], 4)
            row["advanced"][m] = adv
            # velocity = signed change of the CEILING this round (rate of climb, per round)
            row["velocity"][m] = None if (prev is None or ceiling[m] is None) else round(ceiling[m] - prev, 4)
        report.append(row)

    # ---- summary velocities (overall rate of climb) ----
    def series(m):
        return [(r["idx"], r["ceiling"][m]) for r in report if r["ceiling"][m] is not None]
    summ = {}
    for m in metrics:
        s = series(m)
        if len(s) >= 2:
            (i0, v0), (i1, v1) = s[0], s[-1]
            n_adv = sum(1 for r in report if r["advanced"][m])
            summ[m] = {"start": round(v0, 4), "end": round(v1, 4), "total_gain": round(v1 - v0, 4),
                       "rounds_span": i1 - i0, "advances": n_adv,
                       "avg_gain_per_round": round((v1 - v0) / max(i1 - i0, 1), 4),
                       "avg_gain_per_advance": round((v1 - v0) / max(n_adv, 1), 4)}
    out = {"rounds_order": order, "per_round": report, "summary_velocity": summ,
           "composite_ceiling": ceiling.get("composite"), "scorer_version": A.MODEL_VERSION}
    (ROOT / "state/funnel/climb_metrics.json").write_text(json.dumps(out, indent=1))
    return out


def _print(out):
    print("=" * 100)
    print("CLIMB METRICS — per-round best, running ceiling, and velocity (rate of climb)")
    print("=" * 100)
    hdr = f"{'round':16s}{'composite':>11s}{'sharpe':>9s}{'fitness':>9s}{'returns':>9s}{'turnover':>9s}{'drawdown':>9s}{'2Y':>7s}{'sub':>7s}"
    print(hdr)
    for r in out["per_round"]:
        c = r["ceiling"]
        def cell(m, w=9):
            v = c[m]
            mark = "^" if r["advanced"][m] else " "
            return (f"{v:>{w-1}.2f}{mark}" if v is not None else f"{'—':>{w}s}")
        print(f"{r['round'][:16]:16s}{cell('composite',11)}{cell('sharpe')}{cell('fitness')}{cell('returns')}"
              f"{cell('turnover')}{cell('drawdown')}{cell('sharpe_2y',7)}{cell('sub_universe',7)}")
    print("\n(^ = this round raised that metric's ceiling)")
    print("\nSUMMARY VELOCITY (start -> end | total gain | avg gain / advance):")
    for m, s in out["summary_velocity"].items():
        print(f"  {m:12s} {s['start']:>7.3f} -> {s['end']:>7.3f} | Δ {s['total_gain']:+.3f} over {s['advances']} advances "
              f"| {s['avg_gain_per_advance']:+.4f}/advance, {s['avg_gain_per_round']:+.4f}/round")
    print(f"\nCURRENT COMPOSITE CEILING: {out['composite_ceiling']:.2f}  (scorer v{out['scorer_version']})")
    print("saved -> state/funnel/climb_metrics.json")


if __name__ == "__main__":
    _print(run())
