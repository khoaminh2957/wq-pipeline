#!/usr/bin/env python3
"""corr_check.py — v3 BOOK-CORRELATION gate (2026-07-18). The v1/v2 pipelines never modeled
maxcorr-vs-the-189-book anywhere in stages 1-5 (only a prose 'refresh' at pre-submit); this makes
it a first-class, OFFLINE-checkable gate, mirroring theme_check.py.

Method: daily-PnL-CHANGE Pearson on common dates (>=MIN_OBS), from stored fetched/pnl/<id>.jsonl
(each line [date, cumulative_pnl]). This is the same statistic used to falsify the council-audit's
"srl2/dsp share a leg -> guaranteed SELF_CORRELATION fail" claim: measured corr(O0Zlk5xv,88QMjWYq)
=0.278, srl2-vs-book max 0.093 — i.e. the shared leg did NOT breach 0.7. Verify on data, not reasoning.

Pure, deterministic, no API. Usage:
  corr_check.py <alpha_id> [--book state/submitted_all_live.json] [--threshold 0.7]
  corr_check.py --self-test
  python: max_book_corr(aid, book_ids) -> (maxabs, signed, worst_id); corr_gate(aid, book_ids, thr)
"""
from __future__ import annotations
import argparse, json, os, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PNL_DIR = ROOT / "fetched" / "pnl"
MIN_OBS = 100
DEFAULT_THRESHOLD = 0.7


def _load_pnl(aid: str) -> dict | None:
    p = PNL_DIR / f"{aid}.jsonl"
    if not p.exists():
        return None
    out = {}
    for line in open(p):
        try:
            x = json.loads(line)
        except Exception:
            continue
        if isinstance(x, list) and len(x) >= 2 and isinstance(x[0], str):
            out[x[0]] = x[1]
    return out or None


def pnl_corr(a_pnl: dict, b_pnl: dict) -> float | None:
    """Pearson correlation of DAILY PnL CHANGES on common dates (cumulative-pnl series -> diffs)."""
    common = sorted(set(a_pnl) & set(b_pnl))
    if len(common) < MIN_OBS + 1:
        return None
    xa = [a_pnl[common[i]] - a_pnl[common[i - 1]] for i in range(1, len(common))]
    xb = [b_pnl[common[i]] - b_pnl[common[i - 1]] for i in range(1, len(common))]
    n = len(xa)
    ma, mb = sum(xa) / n, sum(xb) / n
    cov = sum((xa[i] - ma) * (xb[i] - mb) for i in range(n))
    va = sum((x - ma) ** 2 for x in xa)
    vb = sum((x - mb) ** 2 for x in xb)
    if va <= 0 or vb <= 0:
        return None
    return cov / (va * vb) ** 0.5


def max_book_corr(aid: str, book_ids, cand_pnl: dict | None = None):
    """Return (max_abs_corr, signed_corr, worst_id, n_compared). cand_pnl optional (else load by id)."""
    cand = cand_pnl if cand_pnl is not None else _load_pnl(aid)
    if not cand:
        return None
    worst = (0.0, 0.0, None)
    n = 0
    for b in book_ids:
        if b == aid:
            continue
        bp = _load_pnl(b)
        if not bp:
            continue
        c = pnl_corr(cand, bp)
        if c is None:
            continue
        n += 1
        if abs(c) > worst[0]:
            worst = (abs(c), c, b)
    return {"max_abs": round(worst[0], 4), "signed": round(worst[1], 4),
            "worst_id": worst[2], "n_compared": n}


def corr_gate(aid: str, book_ids, threshold: float = DEFAULT_THRESHOLD, cand_pnl: dict | None = None):
    """PASS if maxcorr-vs-book < threshold. Returns (ok, detail). n_compared==0 -> UNKNOWN (no pnl)."""
    r = max_book_corr(aid, book_ids, cand_pnl)
    if r is None or r["n_compared"] == 0:
        return None, {"reason": "no comparable PnL (candidate or book missing)", **(r or {})}
    return (r["max_abs"] < threshold), r


def _book_ids(book_path):
    data = json.load(open(book_path))
    return [a["id"] for a in data if isinstance(a, dict) and "id" in a]


def _self_test():
    # srl2 vs dsp must be well under 0.7 (the data fact that refuted the audit's shared-leg claim)
    a, b = _load_pnl("O0Zlk5xv"), _load_pnl("88QMjWYq")
    assert a and b, "champion PnL missing"
    c = pnl_corr(a, b)
    assert c is not None and abs(c) < 0.7, f"expected <0.7, got {c}"
    # symmetry + self-corr==1
    assert abs(pnl_corr(a, b) - pnl_corr(b, a)) < 1e-9
    assert abs(pnl_corr(a, a) - 1.0) < 1e-9
    # gate wiring
    ok, det = corr_gate("O0Zlk5xv", ["88QMjWYq"], 0.7)
    assert ok is True and det["max_abs"] < 0.7
    ok2, _ = corr_gate("O0Zlk5xv", ["88QMjWYq"], 0.1)  # tiny threshold -> fail
    assert ok2 is False
    print(f"corr_check self-test PASS (srl2-dsp corr={c:.3f})")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("alpha_id", nargs="?")
    ap.add_argument("--book", default=str(ROOT / "state/submitted_all_live.json"))
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        _self_test()
        return 0
    if not a.alpha_id:
        ap.error("alpha_id required (or --self-test)")
    ok, det = corr_gate(a.alpha_id, _book_ids(a.book), a.threshold)
    verdict = "PASS" if ok else ("FAIL" if ok is False else "UNKNOWN")
    print(f"{a.alpha_id}: corr-gate {verdict} | maxcorr={det.get('max_abs')} vs {det.get('worst_id')} "
          f"(n={det.get('n_compared')}, thr={a.threshold})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
