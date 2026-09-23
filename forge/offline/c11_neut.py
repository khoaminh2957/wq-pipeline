"""C11 — in-formula neutralisation against the posted book, 60 simulations (Khoa's tick, 2026-09-06 22:30).

THE QUESTION. Sixteen options×short candidates pass every platform gate (Sharpe 1.64–2.08, DSR ≥ 0.997)
and sit behind the correlation lines: prod 0.79–0.85 read on 6 of them BEFORE kqVbg1xP was posted
(their correlation is with the platform book, mechanism unknown) and self 0.58–0.85 on the 10 read
AFTER (kqVbg1xP itself is now in the book; 883KgXXm reads self = prod = 0.852 against it). Can a
cross-sectional residual against the posted formulas keep the platform pass and cross the lines?

ARMS (base = the candidate's own formula F and settings; KQ / VR = the two POSTed formulas):
  R   vector_neut(F, KQ)                          base settings            16
  RS  vector_neut(F, KQ)                          neutralization STATISTICAL 16
  RV  vector_neut(vector_neut(F, KQ), VR)          base settings            16
  (first written with regression_neut — "inaccessible or unknown operator" for this account, 48
  ERROR rows 23:01; the accessible orthogonaliser per GET /operators is vector_neut(x, y): x* ⟂ y)
  S   F unchanged                                 neutralization STATISTICAL 12 (top-Sharpe non-STATISTICAL bases)
The control for every arm is the base row already in the journal (same formula, same settings).

EX-ANTE PREDICTIONS, written before any of the 60 ran (RULE 0):
  P1  R/RS/RV: residualising on a sibling built from the same two legs removes most of the signal —
      median Sharpe < 1.0 in each arm.
  P2  If a residual variant still clears Sharpe ≥ 1.58 and fitness ≥ 1.0, its self-corr reads < 0.7
      (the regression makes it orthogonal to kqVbg1xP by construction); prod is unknown.
  P3  S: prod-corr stays ≥ 0.71 (kqVbg1xP is in the book and STATISTICAL siblings correlate ~0.85 with
      it, cf. 883KgXXm); Sharpe within ±0.2 of the base.
LIVES if ≥ 1 variant has every binding check PASS, prod < 0.71 and self < 0.7. Otherwise C11 is
dead for same-mechanism siblings and the only route past the line is a new mechanism (C9).

    build   → state/forge/plans/c11.json (run on the VPS; reads the journal)
    report  → per-arm outcome against the base rows
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from forge import harvest as HV, score as SC  # noqa: E402

BASES = ["ZY0Zowe1", "akLMOLZW", "om6AY6Ml", "E5vYKpq1", "ZY0qaNQx", "KPOqgZgk", "pwPzpKMj", "vRkzEqlG",
         "O0rmL0j1", "6XrqWXQP", "j23w75Yo", "akLP09Gv", "E5vajP2r", "e79qeMZN", "883KgXXm", "RRVawW0b"]
BOOK = {"KQ": "kqVbg1xP", "VR": "vRk095rv"}
TAG = "C11"
PLAN = ROOT / "state/forge/plans/c11.json"
CORR = ROOT / "state/forge/corr.jsonl"
PROD_LINE, SELF_LINE = 0.71, 0.70
OP = "vector_neut"          # cross-sectional orthogonalisation the account can use (GET /operators, 2026-09-06)
ALL_ARMS = ("R", "RS", "RV", "S")


def _formula(row) -> str:
    return row.get("formula") or row.get("code") or row.get("regular") or ""


def journal_rows(ids, journal=HV.JOURNAL) -> dict:
    """alpha id -> its journal row (the last one wins: a re-harvested row carries the metrics)."""
    want = set(ids)
    out = {}
    for r in HV.read_jsonl(journal):
        a = r.get("alpha")
        if a in want and _formula(r):
            out[a] = r
    missing = want - set(out)
    if missing:
        raise SystemExit("journal has no formula for %s" % sorted(missing))
    return out


def variants(base_rows: dict, book: dict, arms=ALL_ARMS) -> list:
    kq, vr = _formula(book["KQ"]), _formula(book["VR"])
    out = []
    for a in BASES:
        r = base_rows[a]
        f, st, meta = _formula(r), dict(r.get("settings") or {}), dict(r.get("meta") or {})
        three = [("R", "%s(%s, %s)" % (OP, f, kq), st),
                 ("RS", "%s(%s, %s)" % (OP, f, kq), dict(st, neutralization="STATISTICAL")),
                 ("RV", "%s(%s(%s, %s), %s)" % (OP, OP, f, kq, vr), st)]
        for arm, formula, settings in three:
            if arm in arms:
                out.append({"formula": formula, "settings": settings,
                            "meta": dict(meta, recipe=TAG, arm=arm, base_alpha=a, base_sharpe=r.get("sharpe"))})
    if "S" not in arms:
        return out
    non_stat = sorted((base_rows[a] for a in BASES if (base_rows[a].get("settings") or {}).get("neutralization") != "STATISTICAL"),
                      key=lambda r: -(r.get("sharpe") or 0))[:12]
    for r in non_stat:
        out.append({"formula": _formula(r), "settings": dict(r.get("settings") or {}, neutralization="STATISTICAL"),
                    "meta": dict(r.get("meta") or {}, recipe=TAG, arm="S", base_alpha=r["alpha"], base_sharpe=r.get("sharpe"))})
    return out


def build(out_path=PLAN, arms=ALL_ARMS) -> dict:
    rows = journal_rows(BASES + list(BOOK.values()))
    cons = variants(rows, {k: rows[v] for k, v in BOOK.items()}, arms)
    plan = {"seed": 0, "n": len(cons), "made_at": time.time(), "hypotheses": 1, "cells_considered": 1, "gate": {},
            "blocks": [{"cell": "USA/d1 Short Interest", "weight": 0, "kept": len(cons), "class": TAG}],
            "quarantined": 0, "ensembles": "off", "n_ensembles": 0, "allocate": False, "pair_classes": {},
            "blocks_by_class": {TAG: len(cons)}, "mode": "composites", "composites": 1, "n_composites": len(cons),
            "by_delay": {0: 0, 1: len(cons)}, "experiment": TAG, "predictions": ["P1", "P2", "P3"], "constructions": cons}
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out_path).write_text(json.dumps(plan))
    return plan


def _corr(alpha, corr_rows) -> tuple:
    prod = self_ = None
    for j in corr_rows:
        if j.get("alpha") == alpha:
            if isinstance(j.get("prod"), (int, float)):
                prod = j["prod"]
            if isinstance(j.get("self"), (int, float)):
                self_ = j["self"]
    return prod, self_


def report(journal=HV.JOURNAL, corr=CORR) -> dict:
    rows = [r for r in HV.read_jsonl(journal) if (r.get("meta") or {}).get("recipe") == TAG and r.get("alpha")]
    corr_rows = HV.read_jsonl(corr) if pathlib.Path(corr).exists() else []
    arms = {}
    for r in rows:
        m = r["meta"]
        st = SC.stage(r)
        prod, self_ = _corr(r["alpha"], corr_rows)
        passed = st["stage"] not in ("fail", "incomplete")
        lives = passed and prod is not None and self_ is not None and prod < PROD_LINE and self_ < SELF_LINE
        arms.setdefault(m["arm"], []).append({"alpha": r["alpha"], "base": m["base_alpha"], "base_sharpe": m.get("base_sharpe"),
                                              "sharpe": r.get("sharpe"), "fitness": r.get("fitness"), "turnover": r.get("turnover"),
                                              "stage": st["stage"], "failed": st.get("failed"), "prod": prod, "self": self_, "lives": lives})
    out = {"rows": len(rows), "arms": {}}
    for arm, v in sorted(arms.items()):
        sh = [x["sharpe"] for x in v if isinstance(x["sharpe"], (int, float))]
        d = [x["sharpe"] - x["base_sharpe"] for x in v if isinstance(x["sharpe"], (int, float)) and isinstance(x["base_sharpe"], (int, float))]
        out["arms"][arm] = {"n": len(v), "sharpe_p50": round(statistics.median(sh), 2) if sh else None,
                            "sharpe_max": round(max(sh), 2) if sh else None,
                            "delta_vs_base_p50": round(statistics.median(d), 2) if d else None,
                            "platform_pass": sum(1 for x in v if x["stage"] not in ("fail", "incomplete")),
                            "corr_read": sum(1 for x in v if x["prod"] is not None),
                            "prod_p50": round(statistics.median([x["prod"] for x in v if x["prod"] is not None]), 2) if any(x["prod"] is not None for x in v) else None,
                            "self_p50": round(statistics.median([x["self"] for x in v if x["self"] is not None]), 2) if any(x["self"] is not None for x in v) else None,
                            "lives": [x["alpha"] for x in v if x["lives"]], "rows": v}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("build", "report"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--arms", default=",".join(ALL_ARMS), help="which arms to plan, e.g. R,RS,RV after the S arm already ran")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        p = build(arms=tuple(a.arms.split(",")))
        by = {}
        for c in p["constructions"]:
            by[c["meta"]["arm"]] = by.get(c["meta"]["arm"], 0) + 1
        print("C11 plan: %d constructions %s -> %s" % (len(p["constructions"]), by, PLAN))
        for c in p["constructions"][:1] + p["constructions"][-1:]:
            print("  [%s/%s] %s | %s" % (c["meta"]["arm"], c["meta"]["base_alpha"], c["settings"].get("neutralization"), c["formula"][:160]))
        return 0
    rep = report()
    if a.json:
        print(json.dumps(rep, indent=1))
        return 0
    print("C11 rows landed: %d" % rep["rows"])
    for arm, s in rep["arms"].items():
        print("  %-3s n %2d | sharpe p50 %s max %s (Δ vs base p50 %s) | platform pass %d | corr read %d prod p50 %s self p50 %s | LIVES %s"
              % (arm, s["n"], s["sharpe_p50"], s["sharpe_max"], s["delta_vs_base_p50"], s["platform_pass"], s["corr_read"],
                 s["prod_p50"], s["self_p50"], s["lives"] or "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
