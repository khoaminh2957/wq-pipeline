#!/usr/bin/env python3
"""GATES-ONLY fetcher for the v7 funnel (saves API vs full recordsets).

Given alpha sids, GET /alphas/{id}, extract ONLY is.checks (name/result) and write
state/funnel/<run>_gates.jsonl with one row per sid:
    {sid, n_pass, robust_universe_pass, fails:[...], checks:{name:result}}

Ranking downstream is by n_pass, prioritizing robust_universe_pass==True
(LOW_ROBUST_UNIVERSE_SHARPE result==PASS).

The live GET is single-stream + MIN_GAP + 429/401-aware (pattern copied from
tools/fetch_alpha_recordsets.py). The PURE function gates_from_alpha_json() has no
network and is what the offline 5x tests exercise.

Usage:
  python tools/funnel/fetch_gates.py <run> <sid1> <sid2> ...
  python tools/funnel/fetch_gates.py --self-test        # run offline fixture tests
"""
from __future__ import annotations
import sys, json, time, pickle, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "state" / "funnel"

# Robust-Universe-Sharpe gate. The live platform emits the check as
# "LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO" (150/150 rows in state/resim_results.jsonl;
# the bare name never appears), so match by PREFIX. This deliberately does NOT match
# "LOW_ROBUST_UNIVERSE_RETURNS".
ROBUST_PREFIX = "LOW_ROBUST_UNIVERSE_SHARPE"


def _is_robust_gate(name):
    return str(name).startswith(ROBUST_PREFIX)


# ------------------------------------------------------------------ pure logic
def _iter_checks(alpha_json):
    """Locate the checks list in any of the accepted shapes and yield (name, result).

    Accepted shapes for `alpha_json`:
      - full GET /alphas/{id} response:  {"is": {"checks": [...]}}
      - an `is` dict:                    {"checks": [...]}
      - the checks list itself:          [...]
      - checks as a {name: result} dict (our own <run>_gates.jsonl rows
        round-tripped; same dict-form rank_gates.parse_checks accepts)
    Each check element may be:
      - a full row dict {"name","result","value","limit"}  -> use its result
      - a bare string (a PASS-name list)                   -> result is "PASS"
    """
    checks = None
    if isinstance(alpha_json, dict):
        iss = alpha_json.get("is")
        if isinstance(iss, dict) and "checks" in iss:
            checks = iss.get("checks")
        elif "checks" in alpha_json:
            checks = alpha_json.get("checks")
    elif isinstance(alpha_json, list):
        checks = alpha_json
    if not checks:
        return
    if isinstance(checks, dict):  # {name: result} form (gates.jsonl round-trip)
        for name, result in checks.items():
            yield name, result
        return
    for c in checks:
        if isinstance(c, dict):
            name = c.get("name")
            if name is None:
                continue
            yield name, c.get("result")
        elif isinstance(c, str):
            # PASS-name list: presence == passed
            yield c, "PASS"


def gates_from_alpha_json(alpha_json):
    """Pure: derive gate summary from an alpha JSON. No network, no I/O."""
    checks = {}
    n_pass = 0
    robust = False
    fails = []
    for name, result in _iter_checks(alpha_json):
        checks[name] = result
        res = str(result).upper()  # normalize like rank_gates.parse_checks
        if res == "PASS":
            n_pass += 1
            if _is_robust_gate(name):
                robust = True
        elif res == "FAIL":
            fails.append(name)
    return {
        "n_pass": n_pass,
        "robust_universe_pass": robust,
        "fails": fails,
        "checks": checks,
    }


# ------------------------------------------------------------------ live fetch
def _load_session():
    import requests
    sys.path.insert(0, str(ROOT))
    import config
    s = requests.Session()
    s.headers.update({"Connection": "close"})
    s.cookies.update(pickle.load(open(config.COOKIE_PATH, "rb")))
    return s, config.WQ_API


MIN_GAP = 0.45
MAX_429 = 6


def fetch_gates(sids, run):
    """Live: GET /alphas/{sid} for each sid, extract gates, write <run>_gates.jsonl.

    integration-run-by-operator — this touches the WQ API (single stream).
    """
    s, base = _load_session()
    last = [0.0]
    n429 = [0]

    def get(path):
        for _ in range(30):
            dt = time.time() - last[0]
            if dt < MIN_GAP:
                time.sleep(MIN_GAP - dt)
            last[0] = time.time()
            try:
                r = s.get(base + path, timeout=40)
            except Exception:
                time.sleep(4); continue
            if r.status_code == 429:
                n429[0] += 1
                if n429[0] > MAX_429:
                    raise SystemExit(f"CIRCUIT-BREAK: {n429[0]}x429 — stop to avoid hard ban")
                w = float(r.headers.get("Retry-After", 8) or 8)
                if w > 600:
                    raise SystemExit("RATE-BAN — stop and follow runbook")
                print(f"    429 #{n429[0]}, wait {w:.0f}s", flush=True)
                time.sleep(w + 2); continue
            if r.status_code == 401:
                raise SystemExit("401 — session expired; re-auth (biometric) and rerun")
            return r
        return None

    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / f"{run}_gates.jsonl"
    with open(out_path, "w") as f:
        for sid in sids:
            r = get(f"/alphas/{sid}")
            if r is None or r.status_code != 200:
                code = r.status_code if r is not None else "none"
                print(f"[{sid}] GET failed ({code})", flush=True)
                row = {"sid": sid, "n_pass": 0, "robust_universe_pass": False,
                       "fails": [], "checks": {}, "error": str(code)}
            else:
                g = gates_from_alpha_json(r.json())
                row = {"sid": sid, **g}
                print(f"[{sid}] n_pass={g['n_pass']} robust={g['robust_universe_pass']} "
                      f"fails={len(g['fails'])}", flush=True)
            f.write(json.dumps(row) + "\n")
    print(f"wrote {out_path}", flush=True)
    return out_path


# ------------------------------------------------------------------ self-test
def _self_test():
    fx = ROOT / "state" / "benchmark" / "fixtures"
    cases = json.load(open(fx / "fetch_gates_cases.json"))
    passed = 0
    for i, case in enumerate(cases, 1):
        got = gates_from_alpha_json(case["alpha_json"])
        exp = case["expect"]
        ok = (got["n_pass"] == exp["n_pass"]
              and got["robust_universe_pass"] == exp["robust_universe_pass"]
              and sorted(got["fails"]) == sorted(exp["fails"]))
        print(f"RUN {i} [{case['name']}]: {'PASS' if ok else 'FAIL'}"
              f"  got n_pass={got['n_pass']} robust={got['robust_universe_pass']} "
              f"fails={sorted(got['fails'])}"
              + ("" if ok else f"  EXPECTED n_pass={exp['n_pass']} "
                               f"robust={exp['robust_universe_pass']} fails={sorted(exp['fails'])}"))
        passed += ok
    print(f"\n{passed}/{len(cases)} test runs PASS")
    return passed == len(cases)


def main(argv):
    if not argv or argv[0] == "--self-test":
        sys.exit(0 if _self_test() else 1)
    run, sids = argv[0], argv[1:]
    if not sids:
        raise SystemExit("usage: fetch_gates.py <run> <sid1> <sid2> ...")
    fetch_gates(sids, run)


if __name__ == "__main__":
    main(sys.argv[1:])
