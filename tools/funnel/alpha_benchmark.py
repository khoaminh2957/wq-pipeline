#!/usr/bin/env python3
"""alpha_benchmark.py - deterministic post-crawl alpha quality scorer.

Khoa: "benchmark rieng danh cho viec danh gia alpha sau khi cao" (a separate
benchmark for evaluating alphas AFTER crawling). This is NOT the funnel ranker;
it is a repeatable, deterministic scorer that ranks crawled alphas by quality.

SCORING MODEL (single composite scalar, strictly lexicographic):
  PRIMARY  (always available from gate crawl):
    - gates_passed            : count of checks whose result == PASS
    - robust_universe_pass    : LOW_ROBUST_UNIVERSE_SHARPE* result == PASS
  SECONDARY (only when recordsets / IS metrics are present):
    - gate-margin vs the region x delay LOW_SHARPE bar table
    - fitness, sharpe, drawdown, turnover
    - yearly min-sharpe & negative-year count

RANKING ORDER — pinned to match the funnel SELECTORS (rank_gates.py and
funnel_run.rank_by_gates), which both sort robust-universe-pass FIRST, then
number of gates passed. The v7 spec says "rank ... PRIORITIZING alphas that
PASS the Robust-Universe-Sharpe gate", so robust-pass is the PRIMARY key.
Scoring in any other order would make the benchmark's top-N disagree with the
alphas the funnel actually selects. The composite encodes this lexicographically
(robust, gates, secondary):

    composite = 100000*robust_pass + 100*gates_passed + secondary
    secondary is clamped to [-19, +19]

  => a robust pass (100000) always outranks any gates+secondary swing a
     non-robust alpha can muster; at equal robust status one extra gate (100)
     always outranks any secondary swing (<=19); secondary only breaks the
     remaining ties.  [Khoa may veto and choose gates-primary instead; if so,
     flip ROBUST_W/GATES_W and rank_gates/funnel_run must flip too.]

CHECK FORMS handled (all three shapes the funnel feeds this scorer):
  - full rows : [{"name","result","value","limit"}, ...]
  - PASS list : ["LOW_SHARPE", "LOW_FITNESS", ...]  (names of PASSED gates)
  - dict      : {"LOW_SHARPE": "PASS", ...}  (fetch_gates.gates_from_alpha_json
                output, merged into rows by funnel_run._journal_results'
                gates-only top-up — the live path; S10-26 fix)

Usage:
    python alpha_benchmark.py --selftest
    python alpha_benchmark.py --run NAME --input alphas.json
"""
import argparse
import datetime as _dt
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "state", "benchmark"))
FIXTURE_DIR = os.path.join(BENCH_DIR, "fixtures")

# GROUND TRUTH region x delay LOW_SHARPE bars (verified 2026-07-16,
# platform tightened severity). Keys are (REGION, delay_int).
LOW_SHARPE_BARS = {
    ("CHN", 0): 3.49,
    ("JPN", 0): 2.69,
    ("CHN", 1): 2.07,
    ("JPN", 1): 1.58,
    ("USA", 1): 1.58,
}

ROBUST_PREFIX = "LOW_ROBUST_UNIVERSE_SHARPE"
SECONDARY_CLAMP = 19.0
ROBUST_W = 100000.0   # primary key: robust-universe-sharpe pass
GATES_W = 100.0       # secondary key: number of gates passed (dominates secondary)


# ---------------------------------------------------------------- helpers
def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def lookup_bar(region, delay, fallback=None):
    """Ground-truth LOW_SHARPE bar for a region x delay, else fallback."""
    if region is None or delay is None:
        return fallback
    key = (str(region).upper(), int(delay))
    return LOW_SHARPE_BARS.get(key, fallback)


def predicted_fitness(sharpe, returns, turnover):
    """v6.2 C7 offline fitness pre-screen (verified EXACT on 614/614 crawled
    rows): fitness = sharpe * sqrt(|returns| / max(turnover, 0.125)).
    Pure local arithmetic — usable as a sweep pre-filter BEFORE any sim
    (S10-28 port; the platform's own fitness formula)."""
    return sharpe * math.sqrt(abs(returns) / max(turnover, 0.125))


def parse_checks(checks):
    """Return (gates_passed, robust_pass, low_sharpe_limit).

    Handles the full-row form, the PASS-name-list form, and the dict form
    {name: result} that fetch_gates produces and funnel_run feeds the live path.
    low_sharpe_limit is the platform limit if it appears in full rows, else None.
    """
    if not checks:
        return 0, False, None
    # dict form: {name: result} (S10-26 — previously crashed KeyError: 0 here).
    if isinstance(checks, dict):
        passed = 0
        robust = False
        for name, result in checks.items():
            if str(result).upper() == "PASS":
                passed += 1
                if str(name).startswith(ROBUST_PREFIX):
                    robust = True
        return passed, robust, None
    # PASS-name-list form: list of strings = names of gates that passed.
    if isinstance(checks[0], str):
        names = [str(c) for c in checks]
        robust = any(n.startswith(ROBUST_PREFIX) for n in names)
        return len(names), robust, None
    # Full-row form.
    passed = 0
    robust = False
    low_sharpe_limit = None
    for row in checks:
        name = str(row.get("name", ""))
        result = str(row.get("result", "")).upper()
        if result == "PASS":
            passed += 1
        if name.startswith(ROBUST_PREFIX) and result == "PASS":
            robust = True
        if name == "LOW_SHARPE" and row.get("limit") is not None:
            low_sharpe_limit = float(row["limit"])
    return passed, robust, low_sharpe_limit


def _get_metrics(record):
    """Pull IS metrics from either the flat form or the nested 'is' form."""
    src = record.get("is") if isinstance(record.get("is"), dict) else record
    out = {}
    for k in ("sharpe", "fitness", "turnover", "drawdown", "returns"):
        v = src.get(k)
        if v is not None:
            out[k] = float(v)
    return out


def _yearly(record):
    """Return (min_year_sharpe, neg_year_count) or (None, None)."""
    ys = record.get("yearly_sharpes")
    if isinstance(ys, list) and ys:
        vals = [float(v) for v in ys]
        return min(vals), sum(1 for v in vals if v < 0)
    mn = record.get("min_year_sharpe")
    nn = record.get("neg_year_count")
    if mn is not None or nn is not None:
        return (None if mn is None else float(mn),
                None if nn is None else int(nn))
    return None, None


# ---------------------------------------------------------------- scoring
def score_alpha(record):
    """Score one crawled alpha. Returns a per-alpha report dict."""
    aid = record.get("id") or record.get("alpha") or record.get("name") or "?"
    region = record.get("region")
    delay = record.get("delay")

    gates_passed, robust_pass, ls_limit = parse_checks(record.get("checks"))
    metrics = _get_metrics(record)
    has_metrics = "sharpe" in metrics

    bar = lookup_bar(region, delay, fallback=ls_limit)
    sharpe = metrics.get("sharpe")
    margin = (sharpe - bar) if (has_metrics and bar is not None) else None

    min_yr, neg_yr = _yearly(record)

    # ---- secondary (metrics-driven refinement, bounded) ----
    secondary_raw = 0.0
    if has_metrics:
        if margin is not None:
            secondary_raw += 3.0 * _clamp(margin, -5.0, 5.0)      # +/-15
        if "fitness" in metrics:
            secondary_raw += 1.5 * _clamp(metrics["fitness"] - 1.5, -1.5, 3.5)
        secondary_raw += 1.0 * _clamp(sharpe, 0.0, 5.0)
        if "drawdown" in metrics:
            secondary_raw -= 6.0 * _clamp(metrics["drawdown"], 0.0, 1.0)
        if "turnover" in metrics:
            # penalize only excessive turnover (>0.5/day = cost drag); max -2
            secondary_raw -= 2.0 * _clamp(metrics["turnover"] - 0.5, 0.0, 1.0)
        if min_yr is not None:
            secondary_raw += 2.0 * _clamp(min_yr, -3.0, 3.0)
        if neg_yr is not None:
            secondary_raw -= 3.0 * neg_yr
    secondary = _clamp(secondary_raw, -SECONDARY_CLAMP, SECONDARY_CLAMP)

    composite = (ROBUST_W * (1 if robust_pass else 0)
                 + GATES_W * gates_passed + secondary)

    return {
        "id": aid,
        "region": region,
        "delay": delay,
        "gates_passed": gates_passed,
        "robust_universe_pass": robust_pass,
        "has_metrics": has_metrics,
        "sharpe_bar": bar,
        "sharpe_margin": None if margin is None else round(margin, 4),
        "min_year_sharpe": min_yr,
        "neg_year_count": neg_yr,
        "metrics": metrics,
        "secondary_raw": round(secondary_raw, 4),
        "secondary": round(secondary, 4),
        "composite": round(composite, 4),
    }


def score_alphas(records):
    """Score and rank. Stable sort: composite desc, then id asc."""
    reports = [score_alpha(r) for r in records]
    reports.sort(key=lambda r: (-r["composite"], str(r["id"])))
    for i, r in enumerate(reports, 1):
        r["rank"] = i
    return reports


def build_output(run_name, records):
    reports = score_alphas(records)
    return {
        "run": run_name,
        "generated": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "count": len(reports),
        "bar_table": {f"{k[0]}/d{k[1]}": v for k, v in LOW_SHARPE_BARS.items()},
        "alphas": reports,
    }


def run(run_name, input_path):
    with open(input_path) as f:
        data = json.load(f)
    records = data["alphas"] if isinstance(data, dict) and "alphas" in data else data
    out = build_output(run_name, records)
    os.makedirs(BENCH_DIR, exist_ok=True)
    out_path = os.path.join(BENCH_DIR, f"{run_name}_scores.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {out_path}  ({out['count']} alphas)")
    for r in out["alphas"]:
        print(f"  #{r['rank']:>2} {r['id']:<12} gates={r['gates_passed']} "
              f"robust={int(r['robust_universe_pass'])} "
              f"comp={r['composite']:.3f}")
    return out


# ---------------------------------------------------------------- selftest
def _load_fixtures():
    with open(os.path.join(FIXTURE_DIR, "alphas.json")) as f:
        records = json.load(f)
    with open(os.path.join(FIXTURE_DIR, "expected_scores.json")) as f:
        expected = json.load(f)
    return records, expected


def _rank_gates_order(records):
    """Full ranked id-order produced by the funnel selector rank_gates, for the
    cross-tool consistency check. Returns None if rank_gates is unavailable."""
    try:
        import rank_gates
    except Exception:
        return None
    top = rank_gates.rank_rows(list(records), len(records))
    return [str(r["id"]) for r in top]


def selftest(runs=5, tol=1e-6):
    records, expected = _load_fixtures()
    exp_by_id = {e["id"]: e for e in expected["alphas"]}
    exp_order = [e["id"] for e in expected["alphas"]]

    all_pass = True
    first_order = None
    for run_i in range(1, runs + 1):
        reports = score_alphas(records)
        order = [r["id"] for r in reports]
        ok = True
        msgs = []

        # value check vs golden (within tolerance)
        for r in reports:
            e = exp_by_id.get(r["id"])
            if e is None:
                ok = False
                msgs.append(f"unexpected id {r['id']}")
                continue
            if abs(r["composite"] - e["composite"]) > tol:
                ok = False
                msgs.append(f"{r['id']} composite {r['composite']} != {e['composite']}")
            if r["gates_passed"] != e["gates_passed"]:
                ok = False
                msgs.append(f"{r['id']} gates {r['gates_passed']} != {e['gates_passed']}")
            if bool(r["robust_universe_pass"]) != bool(e["robust_universe_pass"]):
                ok = False
                msgs.append(f"{r['id']} robust mismatch")

        # S10-26 regression (non-tautological): dict-form {name: result} must
        # parse identically to the equivalent full rows, and must not crash.
        for r in records:
            ch = r.get("checks")
            if isinstance(ch, list) and ch and isinstance(ch[0], dict):
                as_dict = {c["name"]: c.get("result") for c in ch}
                gp_l, rb_l, _ = parse_checks(ch)
                gp_d, rb_d, _ = parse_checks(as_dict)
                if (gp_l, rb_l) != (gp_d, rb_d):
                    ok = False
                    msgs.append(f"{r['id']} dict-form parse mismatch "
                                f"({gp_d},{rb_d}) != ({gp_l},{rb_l})")

        # S10-28 port: predicted_fitness must reproduce the platform's own
        # fitness on SAVED crawled rows (was exact on 614/614; fixture holds 12
        # saved rows incl. 4 below the 0.125 turnover floor).
        pf_path = os.path.join(FIXTURE_DIR, "predicted_fitness_rows.json")
        with open(pf_path) as f:
            for row in json.load(f):
                pred = predicted_fitness(row["sharpe"], row["returns"], row["turnover"])
                if abs(pred - row["fitness"]) > 0.005 + 1e-9:
                    ok = False
                    msgs.append(f"predicted_fitness({row['id']}) {pred:.4f} "
                                f"!= saved {row['fitness']}")

        # ordering vs golden
        if order != exp_order:
            ok = False
            msgs.append(f"order {order} != golden {exp_order}")
        # ordering stable across runs
        if first_order is None:
            first_order = order
        elif order != first_order:
            ok = False
            msgs.append("order unstable across runs")

        # independent structural invariants (not golden-tautological):
        comps = [r["composite"] for r in reports]
        if comps != sorted(comps, reverse=True):
            ok = False
            msgs.append("composite not monotonic desc")
        for a, b in zip(reports, reports[1:]):
            # PRIMARY: robust-pass first (a non-robust must never precede a robust)
            if (not a["robust_universe_pass"]) and b["robust_universe_pass"]:
                ok = False
                msgs.append("robust lexicography violated")
            # SECONDARY: within the same robust bucket, gates descending
            if (a["robust_universe_pass"] == b["robust_universe_pass"]
                    and a["gates_passed"] < b["gates_passed"]):
                ok = False
                msgs.append("gate lexicography violated")

        # cross-tool diagnostic (NON-FATAL): the benchmark order SHOULD equal the
        # funnel selector (rank_gates) order once both detect the robust gate the
        # same way. It currently can differ because rank_gates/fetch_gates match
        # the robust gate by EXACT name == 'LOW_ROBUST_UNIVERSE_SHARPE' while this
        # benchmark, funnel_run, and gate_lib match by PREFIX (the real gate is
        # 'LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO'). We print a WARN but do NOT fail
        # our own suite on a sibling's matching bug.
        if run_i == 1:
            sel_order = _rank_gates_order(records)
            if sel_order is not None and order != sel_order:
                print(f"[warn] benchmark order {order} != rank_gates selector "
                      f"{sel_order} (rank_gates uses exact robust-gate match; "
                      f"fix rank_gates/fetch_gates to prefix-match)")

        tag = "PASS" if ok else "FAIL"
        print(f"[run {run_i}/{runs}] {tag}" + ("" if ok else "  :: " + "; ".join(msgs)))
        all_pass = all_pass and ok

    print(f"RESULT: {'PASS' if all_pass else 'FAIL'} ({runs} runs)")
    return all_pass


# ---------------------------------------------------------------- fixtures
def write_fixtures():
    """(Re)generate fixtures and golden expected scores. Dev use only."""
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    records = [
        # 1. full-row form, CHN d0, strong, with yearly -> top tier
        {
            "id": "AAA_chn_d0", "region": "CHN", "delay": 0,
            "checks": [
                {"name": "LOW_SHARPE", "result": "PASS", "value": 3.9, "limit": 3.49},
                {"name": "LOW_FITNESS", "result": "PASS", "value": 2.1, "limit": 1.5},
                {"name": "LOW_TURNOVER", "result": "PASS"},
                {"name": "HIGH_TURNOVER", "result": "PASS"},
                {"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS"},
                {"name": "LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO", "result": "PASS"},
                {"name": "SELF_CORRELATION", "result": "PENDING"},
                {"name": "MATCHES_PYRAMID", "result": "PASS"},
            ],
            "is": {"sharpe": 3.9, "fitness": 2.1, "turnover": 0.12,
                   "drawdown": 0.08, "returns": 0.31},
            "yearly_sharpes": [3.2, 3.8, 4.1, 3.5],
        },
        # 2. PASS-name-list form (resim_results style), USA d1, robust passes
        {
            "id": "BBB_usa_d1", "region": "USA", "delay": 1,
            "checks": ["LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER",
                       "HIGH_TURNOVER", "LOW_ROBUST_UNIVERSE_SHARPE",
                       "MATCHES_PYRAMID"],
            "sharpe": 1.9, "fitness": 1.7, "turnover": 0.25,
            "drawdown": 0.12, "returns": 0.14,
        },
        # 3. full-row, JPN d1, robust FAILS, mediocre, one negative year
        {
            "id": "CCC_jpn_d1", "region": "JPN", "delay": 1,
            "checks": [
                {"name": "LOW_SHARPE", "result": "PASS", "value": 1.7, "limit": 1.58},
                {"name": "LOW_FITNESS", "result": "PASS", "value": 1.6, "limit": 1.5},
                {"name": "LOW_TURNOVER", "result": "PASS"},
                {"name": "HIGH_TURNOVER", "result": "PASS"},
                {"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS"},
                {"name": "LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO", "result": "FAIL"},
                {"name": "MATCHES_PYRAMID", "result": "PASS"},
            ],
            "is": {"sharpe": 1.7, "fitness": 1.6, "turnover": 0.3,
                   "drawdown": 0.22, "returns": 0.11},
            "yearly_sharpes": [-0.4, 1.2, 2.1, 1.9],
        },
        # 4. gates-only (no metrics), CHN d1, robust passes — DICT form
        #    (fetch_gates {name: result}; the live funnel_run shape — S10-26)
        {
            "id": "DDD_chn_d1_nomet", "region": "CHN", "delay": 1,
            "checks": {
                "LOW_SHARPE": "PASS",
                "LOW_FITNESS": "PASS",
                "LOW_TURNOVER": "PASS",
                "LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO": "PASS",
                "SELF_CORRELATION": "PENDING",
            },
        },
        # 5. weak: high drawdown, two negative years, robust fail, JPN d0
        {
            "id": "EEE_jpn_d0_weak", "region": "JPN", "delay": 0,
            "checks": [
                {"name": "LOW_SHARPE", "result": "FAIL", "value": 2.4, "limit": 2.69},
                {"name": "LOW_FITNESS", "result": "PASS", "value": 1.55, "limit": 1.5},
                {"name": "LOW_TURNOVER", "result": "PASS"},
                {"name": "LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO", "result": "FAIL"},
            ],
            "is": {"sharpe": 2.4, "fitness": 1.55, "turnover": 0.6,
                   "drawdown": 0.45, "returns": 0.09},
            "yearly_sharpes": [-1.1, -0.3, 2.0, 1.4],
        },
    ]
    with open(os.path.join(FIXTURE_DIR, "alphas.json"), "w") as f:
        json.dump(records, f, indent=2)
    reports = score_alphas(records)
    golden = {
        "note": "golden scores for alpha_benchmark selftest",
        "alphas": [
            {"id": r["id"], "composite": r["composite"],
             "gates_passed": r["gates_passed"],
             "robust_universe_pass": r["robust_universe_pass"],
             "rank": r["rank"]}
            for r in reports
        ],
    }
    with open(os.path.join(FIXTURE_DIR, "expected_scores.json"), "w") as f:
        json.dump(golden, f, indent=2)
    print("Fixtures written to", FIXTURE_DIR)
    for r in reports:
        print(f"  #{r['rank']} {r['id']:<18} comp={r['composite']}")


# ---------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description="Deterministic post-crawl alpha benchmark")
    ap.add_argument("--selftest", action="store_true", help="run 5x fixture regression")
    ap.add_argument("--write-fixtures", action="store_true", help="(re)generate golden fixtures")
    ap.add_argument("--run", metavar="NAME", help="score alphas from --input, write <NAME>_scores.json")
    ap.add_argument("--input", metavar="PATH", help="JSON list of alpha records (or {alphas:[...]})")
    args = ap.parse_args()

    if args.write_fixtures:
        write_fixtures()
        return
    if args.selftest:
        ok = selftest()
        sys.exit(0 if ok else 1)
    if args.run:
        if not args.input:
            ap.error("--run requires --input")
        run(args.run, args.input)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
