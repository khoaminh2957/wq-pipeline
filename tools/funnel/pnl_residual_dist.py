#!/usr/bin/env python3
"""pnl_residual_dist.py — per-alpha DISTRIBUTION of the 1-day-step residual on the PnL curve.
(Khoa 2026-07-18, def confirmed: residual = daily step around drift.)

For an alpha's cumulative PnL curve pnl_cum(t):
  r_t = pnl_cum(t) - pnl_cum(t-1)      # the 1-day step ("khoảng cách 1 ngày")
  e_t = r_t - mean(r)                  # residual around the drift
  |e_t|                                # abs residual
The DISTRIBUTION of |e_t| over all trading days characterizes daily roughness. Summaries:
  sigma_day = std(e_t)                 # daily P&L volatility (the headline number)
  std_abs   = std(|e_t|)               # dispersion of the deviation MAGNITUDE (what Khoa named)
  mean_abs  = mean(|e_t|)
  cv_abs    = std_abs / mean_abs       # scale-free shape of the |residual| distribution
  daily_ir  = mean(r) / sigma_day      # 1-day info ratio (drift / noise)
  tail95    = p95(|e|) / mean_abs, kurtosis(e_t)   # fat-tail / gap-day profile
Reads state/funnel/pnl_curves.json. Exports compute() for reuse + a histogram payload for the artifact.
"""
from __future__ import annotations
import json, pathlib
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CURVES = ROOT / "state/funnel/pnl_curves.json"


def _pnl_col(rec):
    props = (rec.get("schema") or {}).get("properties") or []
    for i, p in enumerate(props):
        if p.get("name") == "pnl":
            return i
    return 1


def _cum(rec):
    ci = _pnl_col(rec)
    out = []
    for row in rec["records"]:
        v = row.get("pnl") if isinstance(row, dict) else (row[ci] if ci < len(row) else None)
        if v is not None:
            out.append(float(v))
    return np.asarray(out, float)


def compute(rec, bins=60):
    cum = _cum(rec)
    if cum.size < 40:
        return None
    r = np.diff(cum)                      # 1-day steps
    mu = float(r.mean())
    e = r - mu                            # residual around drift
    ae = np.abs(e)
    sd = float(e.std())
    std_abs = float(ae.std())
    mean_abs = float(ae.mean())
    # standardized abs residual for a scale-free, cross-alpha-comparable histogram
    z = ae / sd if sd > 0 else ae
    hist, edges = np.histogram(z, bins=bins, range=(0, min(float(z.max()), 8.0)))
    # moments of the raw residual
    m2 = float((e ** 2).mean()) or 1e-12
    skew = float((e ** 3).mean() / m2 ** 1.5)
    kurt = float((e ** 4).mean() / m2 ** 2)          # ~3 = normal
    return {
        "n_days": int(r.size),
        "sigma_day": round(sd, 1),                    # headline daily vol ($book)
        "std_abs": round(std_abs, 1),                 # std of |residual| (Khoa's number)
        "mean_abs": round(mean_abs, 1),
        "cv_abs": round(std_abs / mean_abs, 3) if mean_abs else None,   # scale-free shape
        "drift_per_day": round(mu, 1),
        "daily_ir": round(mu / sd, 4) if sd else None,
        "p95_over_mean": round(float(np.percentile(ae, 95)) / mean_abs, 2) if mean_abs else None,
        "p99_over_mean": round(float(np.percentile(ae, 99)) / mean_abs, 2) if mean_abs else None,
        "kurtosis": round(kurt, 1),
        "skew": round(skew, 2),
        # standardized |residual| histogram (x in units of sigma_day) for the artifact
        "hist_counts": hist.tolist(),
        "hist_edges": [round(x, 3) for x in edges.tolist()],
    }


def run():
    curves = json.load(open(CURVES))
    out = {}
    for oid, c in curves.items():
        d = compute(c)
        if d:
            d["round"] = c.get("round"); d["alpha"] = c.get("alpha")
            out[oid] = d
    (ROOT / "state/funnel/pnl_residual_dist.json").write_text(json.dumps(out, indent=1))
    return out


def _print(out):
    print("=" * 104)
    print("PnL 1-DAY-STEP RESIDUAL DISTRIBUTION  (e_t = Δpnl − drift; std_abs = std|e|)")
    print("=" * 104)
    print(f"{'round':18s}{'days':>5s}{'sigma_day':>10s}{'std_abs':>9s}{'mean_abs':>9s}{'cv_abs':>7s}"
          f"{'daily_IR':>9s}{'p95/mn':>7s}{'p99/mn':>7s}{'kurt':>6s}")
    # one representative per round
    seen = {}
    for oid, d in out.items():
        seen.setdefault(d["round"], (oid, d))
    for rnd, (oid, d) in seen.items():
        print(f"{str(rnd)[:18]:18s}{d['n_days']:>5d}{d['sigma_day']:>10.0f}{d['std_abs']:>9.0f}{d['mean_abs']:>9.0f}"
              f"{d['cv_abs']:>7.3f}{d['daily_ir']:>9.4f}{d['p95_over_mean']:>7.2f}{d['p99_over_mean']:>7.2f}{d['kurtosis']:>6.1f}")
    print("\nsigma_day=daily P&L vol • std_abs=std of |residual| • cv_abs=std_abs/mean_abs (shape) • "
          "daily_IR=drift/noise • p99/mn & kurt = fat-tail/gap-day risk")


if __name__ == "__main__":
    _print(run())
