#!/usr/bin/env python3
"""boost_metric.py — metric-BOOST engine (Khoa 2026-07-17 goal). After the funnel finds a GOOD
config, this exhausts EVERY legitimate lever to push ONE target metric over its threshold, 90 sims
at a time (max sim resources), and CERTIFIES a pass ONLY when the metric truly clears the bar AND
the alpha stays ZERO-FAIL — otherwise it reports the honest CEILING (no overfit fake-pass).

Why not "always reach 1.58 by any means": sharpe is bounded by the SIGNAL — a dead root (proven
550/550 null, cap 0.92) cannot be tuned to 1.58 without in-sample overfitting that dies OOS. So the
guarantee this tool makes is: it ALWAYS runs, ALWAYS emits 90 unique valid lever-variants, ALWAYS
returns a ranked zero-fail result, and certifies PASS iff the metric genuinely clears its bar
zero-fail; else it returns the true achievable ceiling with the reason.

Levers (grounded in logic_operators.md + ALPHA_PIPELINE S5/S7):
  settings   — neutralization breadth × decay × truncation × pasteurization × nanHandling
  formula    — whole-signal risk-adjusted valves: ts_decay_linear (smooth/turnover), hump (jump filter)
Each metric emphasizes the levers that move IT (turnover→more decay; returns→less smoothing; etc.).

Two modes:
  generate — write 90 lever-variants of a base {formula,settings} → run_multisim → fetch_gates/metrics
  select   — read the simmed rows, rank by the target metric among ZERO-FAIL rows, certify vs threshold
Deterministic: same inputs → byte-identical output (coprime-stride mixed-radix, no RNG/clock).
"""
from __future__ import annotations
import argparse, json, math, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.funnel.second_field_sweep import (  # noqa: E402
    NEUT_BY_REGION, DECAY, TRUNC, PASTEUR, UNIT, NANH, _mixed_radix, STRIDE_PRIME,
)

# whole-signal wrap levers ({B} = the base formula). Each is a legal risk-adjusted transform.
_WRAP_SMOOTH = ["{B}", "ts_decay_linear({B}, 4)", "ts_decay_linear({B}, 8)", "ts_decay_linear({B}, 16)"]
_WRAP_JUMP = ["{B}", "hump({B}, hump=0.005)", "hump({B}, hump=0.01)"]  # hump's 2nd arg is NAMED (OPERATORS.md L564)

# metric -> how to boost it. thr defaults are USA-d1-TOP1000 gate limits (parameterizable).
METRIC_SPEC = {
    # key: the sim-result field; dir: max|min|band; thr/band: pass condition; wraps: formula levers
    "sharpe":        {"key": "sharpe",   "dir": "max",  "thr": 1.58, "wraps": _WRAP_SMOOTH + _WRAP_JUMP[1:]},
    "fitness":       {"key": "fitness",  "dir": "max",  "thr": 1.0,  "wraps": _WRAP_SMOOTH + _WRAP_JUMP[1:]},
    "turnover":      {"key": "turnover", "dir": "band", "band": [0.01, 0.7], "wraps": _WRAP_SMOOTH + _WRAP_JUMP[1:]},
    "returns":       {"key": "returns",  "dir": "max",  "thr": 0.12, "wraps": ["{B}"]},   # returns: don't over-smooth
    "drawdown":      {"key": "drawdown", "dir": "min",  "thr": 0.50, "wraps": _WRAP_SMOOTH},
    "robust_sharpe": {"key": "robust",   "dir": "max",  "thr": 0.48, "wraps": ["{B}"]},   # needs neut breadth
    # HT investability (Khoa 2026-07-17): sharpe under a max-position / max-trade cap; de-concentrate + cut turnover
    "max_position":  {"key": "max_position_sharpe", "dir": "max", "thr": 2.0, "wraps": _WRAP_SMOOTH + _WRAP_JUMP[1:]},
    "max_trade":     {"key": "max_trade_sharpe",    "dir": "max", "thr": 2.0, "wraps": _WRAP_SMOOTH + _WRAP_JUMP[1:]},
}


def _wrap_list(metric):
    seen, out = set(), []
    for w in METRIC_SPEC[metric]["wraps"]:
        if w not in seen:
            seen.add(w); out.append(w)
    return out


def generate(base_formula: str, base_settings: dict, metric: str, region: str | None = None,
             n: int = 90, label: str = "boost", blend_legs: list[str] | None = None) -> list[dict]:
    """90 unique lever-variants of the base config, tuned for `metric`.

    ESCALATION LADDER (the "bằng mọi cách" part — Khoa 2026-07-17). Tier 1 = settings+valve sweep on
    the base alone (blend_legs=None). Tier 2+ = pass one or more ORTHOGONAL liquid legs to blend in —
    `add(zscore(base), zscore(rank(leg1)), zscore(rank(leg2)), …)`, an equal-weight Law-6 blend that
    DIVERSIFIES the base past its tuning ceiling. The skill loops Tier1→Tier2→Tier3 (each 90 sims)
    until sharpe is certified >= bar zero-fail; a settings ceiling is NEVER the stopping point."""
    if metric not in METRIC_SPEC:
        raise ValueError(f"unknown metric {metric!r}; options={list(METRIC_SPEC)}")
    if blend_legs:
        legs = " ".join(f", zscore(rank({leg}))" for leg in blend_legs)
        base_formula = f"add(zscore({base_formula}){legs})"
    region = region or base_settings["region"]
    if region not in NEUT_BY_REGION:
        raise ValueError(f"no neutralization list for region {region!r}")
    universe, delay = base_settings["universe"], base_settings["delay"]
    wraps = _wrap_list(metric)
    neut = NEUT_BY_REGION[region]
    axes = [wraps, neut, DECAY, TRUNC, PASTEUR, NANH]
    radices = [len(a) for a in axes]
    total = math.prod(radices)
    if total < n:
        raise ValueError(f"lever space {total} < requested {n}")
    if math.gcd(STRIDE_PRIME, total) != 1:
        raise AssertionError("stride not coprime to lever space")

    def _full(s):  # complete a settings dict so the base config sims exactly as-found
        return {"instrumentType": "EQUITY", "region": s["region"], "universe": s["universe"],
                "delay": s["delay"], "neutralization": s.get("neutralization", neut[0]),
                "decay": s.get("decay", 0), "truncation": s.get("truncation", 0.0),
                "pasteurization": s.get("pasteurization", PASTEUR[0]),
                "unitHandling": s.get("unitHandling", UNIT[0]),
                "nanHandling": s.get("nanHandling", NANH[0]),
                "language": "FASTEXPR", "visualization": False}

    rows, seen, i = [], set(), 0
    # variant 000 = the base config VERBATIM — guarantees the boost NEVER regresses below the base
    # (the ceiling is always >= the base's own metric).
    bset = _full(base_settings)
    rows.append({"id": f"{label}_{metric}_000", "old_id": f"{label}_{metric}_000",
                 "formula": base_formula, "label": f"{label}_{metric}", "settings": bset})
    seen.add((re.sub(r"\s+", "", base_formula), region, universe, delay,
              bset["neutralization"], bset["decay"], bset["truncation"]))
    while len(rows) < n:
        idx = (i * STRIDE_PRIME) % total
        i += 1
        d = _mixed_radix(idx, radices)
        wrap = wraps[d[0]]
        formula = wrap.format(B=base_formula)
        decay = DECAY[d[2]]
        # avoid the degenerate double-smooth: a ts_decay wrap already smooths, so pin settings decay=0 there
        if wrap.startswith("ts_decay_linear"):
            decay = 0
        settings = {
            "instrumentType": "EQUITY", "region": region, "universe": universe, "delay": delay,
            "neutralization": neut[d[1]], "decay": decay, "truncation": TRUNC[d[3]],
            "pasteurization": PASTEUR[d[4]], "unitHandling": base_settings.get("unitHandling", UNIT[0]),
            "nanHandling": NANH[d[5]], "language": "FASTEXPR", "visualization": False,
        }
        # dedup on the PRECHECK's key7 (formula, region, universe, delay, neut, decay, truncation) —
        # it EXCLUDES pasteurization/unitHandling/nanHandling, so those must NOT be uniqueness axes
        # (else two key7-identical rows slip my dedup and the precheck rejects the batch).
        k = (re.sub(r"\s+", "", formula), region, universe, delay,
             settings["neutralization"], settings["decay"], settings["truncation"])
        if k in seen:
            continue
        seen.add(k)
        rid = f"{label}_{metric}_{len(rows):03d}"
        rows.append({"id": rid, "old_id": rid, "formula": formula, "label": f"{label}_{metric}",
                     "settings": settings})
    return rows


# metrics that live INSIDE a check (no top-level field) — pull the check's value
_CHECK_FOR = {"robust": "LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO",
              "max_position_sharpe": "HT_INVESTABLE_MAX_POSITION_SHARPE",
              "max_trade_sharpe": "HT_INVESTABLE_MAX_TRADE_SHARPE"}


def _metric_val(row, key):
    """Metric value: prefer the top-level field, else the mapped check's value (so robust works)."""
    if row.get(key) is not None:
        return row[key]
    cn = _CHECK_FOR.get(key)
    if cn:
        for c in row.get("checks", []):
            if isinstance(c, dict) and c.get("name") == cn:
                return c.get("value")
    return None


def _is_zero_fail(row) -> bool:
    """Delegate to the canonical rule. A second copy of "what counts as passing" is the exact
    divergence gates.py was written to end: this one returned True for {}, for {"checks": []},
    and for the 614 legacy rows whose checks are bare gate-name strings -- certifying a row the
    platform never gave a verdict on."""
    import gates
    return gates.zero_fail(row)[0]


def _meets(val, spec) -> bool:
    if val is None:
        return False
    if spec["dir"] == "max":
        return val >= spec["thr"]
    if spec["dir"] == "min":
        return val <= spec["thr"]
    lo, hi = spec["band"]
    return lo <= val <= hi


def _rank_val(val, spec):
    """sort key so the BEST is first (descending). band: distance-to-mid ascending -> negate."""
    if val is None:
        return -1e9
    if spec["dir"] == "max":
        return val
    if spec["dir"] == "min":
        return -val
    mid = (spec["band"][0] + spec["band"][1]) / 2
    return -abs(val - mid)


def select_boost(rows: list[dict], metric: str, threshold=None):
    """Rank simmed rows by `metric` among ZERO-FAIL rows; certify vs threshold, else report ceiling."""
    spec = dict(METRIC_SPEC[metric])
    if threshold is not None:
        if spec["dir"] == "band":
            spec["band"] = threshold
        else:
            spec["thr"] = threshold
    key = spec["key"]
    zf = [r for r in rows if _is_zero_fail(r)]
    pool = zf or rows  # if nothing is zero-fail, still report the honest best (never certify it)
    ranked = sorted(pool, key=lambda r: _rank_val(_metric_val(r, key), spec), reverse=True)
    best = ranked[0] if ranked else None
    best_val = _metric_val(best, key) if best else None
    certified = bool(best) and _is_zero_fail(best) and _meets(best_val, spec)
    return {
        "metric": metric, "threshold": spec.get("thr") or spec.get("band"),
        "certified": certified,
        "best": {"old_id": best.get("old_id"), "alpha": best.get("alpha"), key: best_val,
                 "zero_fail": _is_zero_fail(best), "formula": best.get("formula"),
                 "settings": best.get("settings")} if best else None,
        "ceiling": best_val, "n": len(rows), "n_zero_fail": len(zf),
        "verdict": ("PASS-CERTIFIED" if certified else
                    f"CEILING {best_val} < bar {spec.get('thr') or spec.get('band')} "
                    f"({'no zero-fail variant' if not zf else 'signal ceiling — needs a stronger leg, not more tuning'})"),
    }


def _cli():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="mode", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--base", required=True, help="JSON {formula, settings} of the good config")
    g.add_argument("--metric", required=True, choices=list(METRIC_SPEC))
    g.add_argument("--n", type=int, default=90)
    g.add_argument("--blend-leg", action="append", default=None,
                   help="Tier-2+ escalation: an orthogonal field to equal-weight blend in (repeatable)")
    g.add_argument("--out", required=True)
    s = sub.add_parser("select")
    s.add_argument("--results", required=True, help="simmed rows JSON (with checks + metric fields)")
    s.add_argument("--metric", required=True, choices=list(METRIC_SPEC))
    s.add_argument("--threshold", type=float, default=None)
    a = ap.parse_args()
    if a.mode == "generate":
        base = json.load(open(a.base))
        rows = generate(base["formula"], base["settings"], a.metric, n=a.n, blend_legs=a.blend_leg)
        pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        json.dump(rows, open(a.out, "w"), indent=1)
        print(f"wrote {len(rows)} {a.metric}-boost variants -> {a.out}")
    else:
        rows = json.load(open(a.results))
        res = select_boost(rows, a.metric, a.threshold)
        print(json.dumps(res, indent=1))


if __name__ == "__main__":
    _cli()
