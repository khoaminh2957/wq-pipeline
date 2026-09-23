#!/usr/bin/env python3
"""Render an alpha's fetched recordsets into chart PNGs so harness agents can SEE the diagnostics
(Khoa's rule: after sim, fetch ALL metrics/pnl/charts-as-images for harness evaluation & improvement).

Reads  fetched/recordsets/<alpha_id>/*.json  (from tools/fetch_alpha_recordsets.py)
Writes fetched/recordsets/<alpha_id>/charts/{pnl,yearly,pnl_by_sector,pnl_by_cap,coverage}.png

LOCAL ONLY — no API calls. Usage: python3 tools/render_recordset_charts.py <alpha_id...>
"""
import sys, json, pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load(d, slug):
    f = d / f"{slug}.json"
    if not f.exists():
        return None, None
    j = json.load(open(f))
    recs = j.get("records") if isinstance(j, dict) else j
    props = [p.get("name") for p in (j.get("schema", {}).get("properties") or [])] if isinstance(j, dict) else []
    return recs, props


def render(aid):
    d = ROOT / "fetched" / "recordsets" / aid
    if not d.exists():
        print(f"{aid}: no recordsets dir — run tools/fetch_alpha_recordsets.py first"); return
    out = d / "charts"; out.mkdir(exist_ok=True)
    made = []

    # 1) PnL curve
    recs, _ = load(d, "pnl")
    if recs:
        dates = [r[0] for r in recs]; vals = [r[1] for r in recs]
        plt.figure(figsize=(10, 4))
        plt.plot(range(len(vals)), vals, lw=0.8)
        step = max(1, len(dates) // 8)
        plt.xticks(range(0, len(dates), step), [dates[i] for i in range(0, len(dates), step)], rotation=30, fontsize=7)
        plt.title(f"{aid} — PnL"); plt.tight_layout()
        plt.savefig(out / "pnl.png", dpi=110); plt.close(); made.append("pnl")

    # 2) Yearly stats (sharpe + returns bars)
    recs, props = load(d, "yearly-stats")
    if recs and props:
        iy = props.index("year"); ish = props.index("sharpe")
        years = [str(r[iy]) for r in recs]; sh = [r[ish] if isinstance(r[ish], (int, float)) else 0 for r in recs]
        plt.figure(figsize=(8, 4))
        plt.bar(years, sh, color=["tab:red" if v < 0 else "tab:blue" for v in sh])
        plt.axhline(0, color="k", lw=0.8); plt.title(f"{aid} — sharpe by year"); plt.tight_layout()
        plt.savefig(out / "yearly.png", dpi=110); plt.close(); made.append("yearly")

    # 3/4) PnL by sector & by capitalization (cumulative lines per group)
    for slug, fname in (("pnl-by-sector", "pnl_by_sector"), ("pnl-by-capitalization", "pnl_by_cap")):
        recs, props = load(d, slug)
        if recs and props:
            skip = {"date", "pnlDivTwo"}
            idxs = [(i, n) for i, n in enumerate(props) if n not in skip]
            plt.figure(figsize=(10, 4.5))
            for i, n in idxs:
                series = [r[i] if i < len(r) and isinstance(r[i], (int, float)) else 0 for r in recs]
                plt.plot(range(len(series)), series, lw=0.8, label=n)
            plt.legend(fontsize=6, ncol=2); plt.title(f"{aid} — {slug} (cumulative)"); plt.tight_layout()
            plt.savefig(out / f"{fname}.png", dpi=110); plt.close(); made.append(fname)

    # 5) Coverage
    recs, _ = load(d, "coverage")
    if recs:
        vals = [r[1] for r in recs if len(r) > 1]
        plt.figure(figsize=(8, 3))
        plt.plot(range(len(vals)), vals, lw=0.8)
        plt.title(f"{aid} — instruments covered"); plt.tight_layout()
        plt.savefig(out / "coverage.png", dpi=110); plt.close(); made.append("coverage")

    print(f"{aid}: rendered {made} -> {out}")


if __name__ == "__main__":
    ids = sys.argv[1:]
    if not ids:
        raise SystemExit("usage: render_recordset_charts.py <alpha_id...>")
    for aid in ids:
        render(aid)
