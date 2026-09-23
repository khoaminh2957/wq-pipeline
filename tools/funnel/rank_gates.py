#!/usr/bin/env python3
"""rank_gates.py — pure, deterministic ranker/selector for the v7 funnel.

Input: a JSONL where each line is one alpha row carrying a `checks` field that is
a PASS-name list (list[str]) OR full rows (list[{name,result,value,limit}]) OR a
{name: result} dict (fetch_gates <run>_gates.jsonl rows).
Works on gates jsonl (from fetch_gates) or on state/resim_results.jsonl rows.

Ranking (all deterministic, no API) — Khoa 2026-07-17: robust is a PRIORITY but NOT a
hard exclusion. A high-sharpe alpha must still make top-N even if it FAILS robust.
  gate order : n_pass DESC (robust counts as one of the passed gates), then sharpe DESC,
               then id ASC. Robust-passers win ties via the extra gate, but a much
               higher-sharpe robust-failer is no longer buried.
  reserve    : the top `reserve_sharpe` rows by raw sharpe are GUARANTEED a slot
               (default max(1, n//5) ~= 20% of top-N) regardless of gates/robust,
               then the rest fill by gate order.

Output: top-N to state/funnel/<run>_top{N}.json

Usage:
  rank_gates.py <input.jsonl> --n 5 --run stage1 [--reserve-sharpe K] [--out PATH]
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
ROBUST_GATE = "LOW_ROBUST_UNIVERSE_SHARPE"


try:
    from gates import BLOCKING
except ImportError:  # rank_gates is imported both as a sibling and standalone
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from gates import BLOCKING


def parse_checks(checks):
    """Return (n_pass, robust_universe_pass) from either checks representation.

    - list[str]        : each string is a check NAME that PASSED  -> counts as a pass
    - list[dict]        : full row; a pass is result == 'PASS'
    - dict{name:result}: fetch_gates jsonl form; a pass is result == 'PASS'
    - mixed / empty / None handled gracefully.
    """
    if isinstance(checks, dict):
        n_pass = sum(1 for r in checks.values() if str(r).upper() == "PASS")
        robust = any(str(k).startswith(ROBUST_GATE) and str(r).upper() == "PASS"
                     for k, r in checks.items())
        return n_pass, robust
    if not checks or not isinstance(checks, list):
        return 0, False
    # Count BLOCKING passes only. Counting every PASS makes n_pass a proxy for HOW MANY CHECKS THE
    # PLATFORM RAN, and it runs an extra HT_* battery (HT_INVESTABLE_MAX_*, HT_AFTER_COST_SHARPE,
    # HT_LIQUID_*, HT_ORTHOGONAL_RAM_NEUTRALIZATION, MATCHES_CLASSIFICATION) only once turnover
    # crosses ~0.20. Those rows carry 26-28 checks against 16-18 and bank up to ~9 free "passes".
    # gate_key = (-n_pass, ...) is the PRIMARY selection key at funnel_run.py:277/:300 and
    # funnel_stage3.py:160, so every top-N this ranker has ever produced was tilted toward high
    # turnover — against this project's own mandate that turnover is penalised hardest
    # (alpha_score.py PRIORITY_W turnover=5.0). Ranking on a count whose SCALE depends on a
    # confounder is not a quality ranking.
    n_pass = 0
    n_pass_all = 0
    robust = False
    for c in checks:
        if isinstance(c, dict):
            if str(c.get("result", "")).upper() == "PASS":
                n_pass_all += 1
                name = str(c.get("name", ""))
                if name in BLOCKING:
                    n_pass += 1
                if name.startswith(ROBUST_GATE):
                    robust = True
        else:  # PASS-name string
            n_pass_all += 1
            if str(c) in BLOCKING:
                n_pass += 1
            if str(c).startswith(ROBUST_GATE):
                robust = True
    return n_pass, robust


def row_id(row):
    return str(row.get("alpha") or row.get("sid") or row.get("id") or row.get("old_id") or "")


def _sharpe(row):
    s = row.get("sharpe")
    return s if isinstance(s, (int, float)) else float("-inf")


def rank_rows(rows, n, reserve_sharpe=None):
    """Pure. Return the top-n rows annotated with computed fields + 1-based rank.

    robust is a counted gate (priority) but NOT a hard exclusion (Khoa 2026-07-17):
    the top `reserve_sharpe` rows by raw sharpe are guaranteed a slot even if they
    FAIL robust; remaining slots fill by (n_pass DESC, sharpe DESC, id ASC).
    reserve_sharpe defaults to max(1, n//5)."""
    if reserve_sharpe is None:
        reserve_sharpe = max(1, n // 5)
    scored = []
    for idx, row in enumerate(rows):
        n_pass, robust = parse_checks(row.get("checks"))
        scored.append({"row": row, "idx": idx, "id": row_id(row),
                       "n_pass": n_pass, "robust": robust, "sharpe": _sharpe(row)})
    gate_key = lambda s: (-s["n_pass"], -s["sharpe"], s["id"])
    sharpe_key = lambda s: (-s["sharpe"], -s["n_pass"], s["id"])

    selected, seen = [], set()
    # 1) reserve the highest-sharpe rows (may be robust-failers) up to the cap
    for s in sorted(scored, key=sharpe_key)[:min(reserve_sharpe, n)]:
        if s["id"] not in seen:
            selected.append(s); seen.add(s["id"])
    # 2) fill the rest by gate order
    for s in sorted(scored, key=gate_key):
        if len(selected) >= n:
            break
        if s["id"] not in seen:
            selected.append(s); seen.add(s["id"])
    # display order: gate order (so #1 is the best all-round; reserved-only picks fall where their gates land)
    selected.sort(key=gate_key)
    out = []
    for rank, s in enumerate(selected, start=1):
        rec = dict(s["row"])
        rec["n_pass"] = s["n_pass"]
        rec["robust_universe_pass"] = s["robust"]
        rec["sharpe_reserved"] = s["id"] in {x["id"] for x in sorted(scored, key=sharpe_key)[:reserve_sharpe]} and not s["robust"]
        rec["rank"] = rank
        rec["id"] = s["id"]
        out.append(rec)
    return out


def load_rows(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="gates/resim JSONL (one alpha row per line)")
    ap.add_argument("--n", type=int, default=5, help="top-N to keep (5=stage1, 25=stage2)")
    ap.add_argument("--reserve-sharpe", type=int, default=None,
                    help="guarantee this many highest-sharpe rows a slot even if robust-fail (default max(1,n//5))")
    ap.add_argument("--run", default="run", help="run label for output filename")
    ap.add_argument("--out", default=None, help="explicit output path (overrides --run)")
    args = ap.parse_args(argv)

    rows = load_rows(args.input)
    top = rank_rows(rows, args.n, args.reserve_sharpe)

    if args.out:
        out_path = pathlib.Path(args.out)
    else:
        out_path = ROOT / "state" / "funnel" / f"{args.run}_top{args.n}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(top, indent=2))

    print(f"ranked {len(rows)} rows -> top {len(top)} written to {out_path}")
    for r in top:
        print(f"  #{r['rank']} {r['id']} robust={r['robust_universe_pass']} n_pass={r['n_pass']}")
    return top


if __name__ == "__main__":
    main()
