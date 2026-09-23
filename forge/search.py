"""forge.search — Khoa 2026-09-04 15:40: "Thử nhiều cách thay đổi pipeline để tạo tới khi ra được
pass đầu tiên". A sequence of ONE-lever rounds, each a recipe for forge/runner.py, run through
forge_loop.sh (so harvest → probe → submit still follow every round), summarised per recipe and
STOPPED at the first row that passes every binding platform check. Every row carries meta.recipe.

Runs detached on the VPS:  setsid nohup venv/bin/python -u forge/search.py > state/forge/search.log
Resumable: a recipe whose tag already has rows in the journal is skipped. Between rounds it
waits (up to 3 h) for a live session — the hourly link law brings Khoa a link by itself.
"""
from __future__ import annotations

import json
import os
import pathlib
import statistics
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
from forge import harvest as HV, score as SC  # noqa: E402

RESULTS = ROOT / "state/forge/search_results.jsonl"
THREE = "intangibles_x_profitability_x_accruals,intangibles_x_profitability_x_safety,profitability_x_accruals_x_investment,safety_x_revisions_x_profitability"
FOUR = "intangibles_x_profitability_x_safety_x_revisions,intangibles_x_profitability_x_safety_x_accruals"

RECIPES = [
    {"tag": "R1", "n": 100, "args": "--mode composites --cells EUR/d1:Fundamental,EUR/d1:Model --only %s" % THREE,
     "lever": "region: EUR/d1 (no regional sub-checks), same 3-leg composites"},
    {"tag": "R2", "n": 60, "args": "--mode composites --cells GLB/d1:Fundamental --only %s --neut COUNTRY,SUBINDUSTRY --group country" % THREE,
     "lever": "GLB country neutralisation + country groups (regional sub-books)"},
    {"tag": "R3", "n": 60, "args": "--mode composites --cells GLB/d1:Fundamental --only %s --universe GLB:TOP3000" % THREE,
     "lever": "GLB universe TOP3000 instead of MINVOL1M"},
    {"tag": "R4", "n": 60, "args": "--mode composites --cells GLB/d1:Fundamental --only %s" % FOUR,
     "lever": "four legs (adds revisions / accruals to the best 3-leg)"},
    {"tag": "R5", "n": 60, "args": "--mode composites --cells GLB/d1:Fundamental --only %s --smooth 10 --decay 16" % THREE,
     "lever": "ts_decay_linear(10) smoothing + decay 16 (ladder / 2-year stability)"},
    {"tag": "R6", "n": 80, "args": "--mode composites --cells EUR/d1:Fundamental,EUR/d1:Model --only %s --universe EUR:TOP1200 --neut STATISTICAL,SLOW_AND_FAST" % THREE,
     "lever": "EUR TOP1200 + statistical / slow-and-fast neutralisation"},
    {"tag": "R7", "n": 60, "args": "--mode composites --cells GLB/d1:Model --only %s" % THREE,
     "lever": "GLB/d1 Model cell (target leg = intangible model313)"},
    {"tag": "R8", "n": 80, "args": "--mode composites --cells JPN/d1:Fundamental,JPN/d1:Model --only %s" % THREE,
     "lever": "region: JPN/d1"},
    {"tag": "R9", "n": 300, "args": "--mode composites",
     "lever": "every admissible composite on every reachable cell (broad sweep)"},
    # --- second batch (16:55): the empty USA/d1 cells, bar 1.58 and no regional sub-checks, with a
    # strong USA fundamental confirmation leg (fundamental6 plain fields) beside the target-category leg
    {"tag": "R10", "n": 80, "args": "--mode composites --cells USA/d1:Insiders --only usa_insider_x_profitability_x_accruals --cell-cap 80",
     "lever": "USA/d1 Insiders: insider buying × USA profitability × USA accruals"},
    {"tag": "R11", "n": 100, "args": "--mode composites --cells USA/d1:Short%20Interest --only usa_short_x_profitability_x_accruals,usa_shortsurprise_x_profitability --cell-cap 100",
     "lever": "USA/d1 Short Interest: short volume / short surprise × USA fundamentals"},
    # --- 18:05: R11 put Sharpe 1.61-1.67 on USA/d1 Short Interest (usa_short_x_profitability_x_accruals)
    # failing ONLY LOW_FITNESS (0.76-0.83 < 1.0; turnover 0.14-0.15 at decay 4). Fitness = Sharpe *
    # sqrt(|returns| / turnover): the lever is turnover (community consensus + memory "fitness failures
    # are turnover in disguise, decay is the lever"). Two ways to cut it, one recipe each.
    {"tag": "R14", "n": 100, "args": "--mode composites --cells USA/d1:Short%20Interest --only usa_short_x_profitability_x_accruals --cell-cap 100 --decay 16,32 --neut STATISTICAL,SUBINDUSTRY",
     "lever": "same composite, decay 16/32 (turnover -> fitness)"},
    {"tag": "R15", "n": 100, "args": "--mode composites --cells USA/d1:Short%20Interest --only usa_short_x_profitability_x_accruals --cell-cap 100 --smooth 10 --decay 8,16 --neut STATISTICAL,SUBINDUSTRY",
     "lever": "same composite, ts_decay_linear(10) on the whole alpha + decay 8/16"},
    {"tag": "R12", "n": 100, "args": "--mode composites --cells USA/d1:Sentiment,USA/d1:Social%20Media --only usa_sentiment_x_profitability_x_accruals,usa_twitter_x_profitability --cell-cap 60",
     "lever": "USA/d1 Sentiment + Social Media: tone × USA fundamentals"},
    # --- 20:10: R14/R15 MEASURED — decay 16/32 halved turnover (0.121 -> 0.062) but fitness did not
    # move (0.83 -> 0.78) because the platform's fitness uses max(turnover, 0.125) (SOURCE: repo
    # skill boost-fitness; verified on R11/R14 rows to 0.01) and Sharpe fell. Below 12.5% turnover
    # only |returns| and Sharpe count: returns must reach 0.125/Sharpe^2 (4.9% at 1.6; we have 3.3%).
    # Levers for returns at held Sharpe: wider weights (truncation) and tail concentration (power).
    {"tag": "R16", "n": 100, "args": "--mode composites --cells USA/d1:Short%20Interest --only usa_short_x_profitability_x_accruals --cell-cap 100 --decay 4,8 --neut STATISTICAL --truncation 0.15",
     "lever": "same composite, truncation 0.15 (returns lever), decay 4/8, STATISTICAL"},
    {"tag": "R17", "n": 100, "args": "--mode composites --cells USA/d1:Short%20Interest --only usa_short_x_profitability_x_accruals --cell-cap 100 --decay 4,8 --neut STATISTICAL --power 2",
     "lever": "same composite, signed_power 2 (tail concentration -> returns), decay 4/8"},
    {"tag": "R18", "n": 100, "args": "--mode composites --cells USA/d1:Short%20Interest --only usa_short_x_profitability_x_accruals --cell-cap 100 --decay 4,8 --neut STATISTICAL --power 2 --truncation 0.15",
     "lever": "both: power 2 + truncation 0.15"},
    {"tag": "R13", "n": 200, "args": "--mode composites --cells GLB/d1:Fundamental --only intangibles_x_profitability_x_safety --per-block 200 --cell-cap 200",
     "lever": "exploit the best GLB composite: sample its whole grid (selection effect noted; DSR pool grows to N=220)"},
    # --- 20:30: within-cell analysis of 240 rows on USA/d1 Short Interest (POST-HOC patterns, not
    # mechanisms): STATISTICAL >> INDUSTRY/SUBINDUSTRY (Sharpe p50 1.19 vs 0.85-0.95), decay 4 best,
    # truncation 0.15 >= 0.08, profitability leg ts_backfill(income/equity,126) best median (fit 0.66,
    # Sharpe 1.36), returns stuck at 0.026-0.036 whatever the knob. Fitness ceiling 0.87 at Sharpe 1.67.
    # One lever per recipe, all STATISTICAL / decay 4 / truncation 0.15 unless the lever is the setting.
    {"tag": "R19", "n": 60, "args": "--mode composites --cells USA/d1:Short%20Interest --only usa_short_x_profitability_x_accruals --cell-cap 60 --decay 4 --truncation 0.15 --neut SLOW_AND_FAST,CROWDING,MARKET",
     "lever": "neutralisations never tried on this cell: SLOW_AND_FAST / CROWDING / MARKET"},
    {"tag": "R20", "n": 100, "args": "--mode composites --cells USA/d1:Short%20Interest --only usa_short_x_profitability_x_accruals --cell-cap 100 --per-block 100 --decay 4 --truncation 0.15 --neut STATISTICAL --group sector",
     "lever": "group = sector for every leg (broader groups, larger dispersion)"},
    {"tag": "R21", "n": 60, "args": "--mode composites --cells USA/d1:Short%20Interest --only usa_short_x_profitability_x_accruals --cell-cap 60 --decay 4 --truncation 0.15 --neut STATISTICAL --universe USA:TOP1000",
     "lever": "universe TOP1000 (fewer, larger names)"},
    {"tag": "R22", "n": 100, "args": "--mode composites --cells USA/d1:Short%20Interest --only usa_short_x_profitability_x_accruals --cell-cap 100 --per-block 100 --decay 4 --truncation 0.15 --neut STATISTICAL",
     "lever": "exploit: 100 fresh draws of the best settings (selection effect stated; DSR pool N grows)"},
    {"tag": "R23", "n": 60, "args": "--mode composites --cells USA/d1:Short%20Interest --only usa_short_x_profitability_x_accruals --cell-cap 60 --decay 4 --truncation 0.2 --neut STATISTICAL --power 1.5",
     "lever": "milder tail concentration (power 1.5) with truncation 0.2"},
]


def session_left() -> int:
    try:
        import mint_link as M
        return int(M.session_left_s() or 0)
    except Exception:  # noqa: BLE001
        return 0


def wait_for_auth(max_s: float = 3 * 3600, poll_s: float = 30.0, out=print) -> bool:
    t0 = time.time()
    while time.time() - t0 < max_s:
        left = session_left()
        if left > 900:
            return True
        out("%s auth dead (%ds); waiting for the hourly link to be tapped" % (time.strftime("%H:%M:%S"), left))
        time.sleep(poll_s)
    return False


def round_summary(tag: str, journal=HV.JOURNAL) -> dict:
    rows = [r for r in HV.read_jsonl(journal) if (r.get("meta") or {}).get("recipe") == tag and r.get("status") not in (None, "PARENT-POSTED")]
    landed = [r for r in rows if r.get("alpha")]
    passes = [r for r in landed if SC.stage(r)["stage"] not in ("fail", "incomplete")]
    by = {}
    for r in landed:
        st = r.get("settings") or {}
        k = "%s %s/d%s %s" % ((r.get("meta") or {}).get("hypothesis"), st.get("region"), st.get("delay"), (r.get("meta") or {}).get("category"))
        if isinstance(r.get("sharpe"), (int, float)):
            by.setdefault(k, []).append(float(r["sharpe"]))
    cells = sorted(((statistics.median(v), max(v), len(v), k) for k, v in by.items()), reverse=True)
    sh = [r["sharpe"] for r in landed if isinstance(r.get("sharpe"), (int, float))]
    return {"tag": tag, "rows": len(rows), "landed": len(landed), "passes": len(passes),
            "pass_alphas": [r["alpha"] for r in passes][:10],
            "sharpe_p50": statistics.median(sh) if sh else None, "sharpe_max": max(sh) if sh else None,
            "best_cells": [{"cell": k, "p50": round(m, 2), "max": round(mx, 2), "n": n} for m, mx, n, k in cells[:3]]}


def already_ran(tag: str, journal=HV.JOURNAL, results=RESULTS) -> bool:
    """Done when the journal holds rows for the tag OR a result line was recorded (a recipe that
    found no candidates has no rows and must not run again on every restart)."""
    if any((r.get("meta") or {}).get("recipe") == tag for r in HV.read_jsonl(journal)):
        return True
    return pathlib.Path(results).exists() and any(r.get("tag") == tag for r in HV.read_jsonl(results))


LOCK = "/var/lock/wq_forge.lock"


def wait_for_lock(max_s: float = 2 * 3600, poll_s: float = 30.0, out=print) -> bool:
    """A restarted driver must not race a round still running under the previous one."""
    import fcntl
    t0 = time.time()
    while time.time() - t0 < max_s:
        try:
            with open(LOCK, "a+") as fh:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            return True
        except OSError:
            out("%s a forge round is still running; waiting" % time.strftime("%H:%M:%S"))
            time.sleep(poll_s)
    return False


def run_recipe(rec: dict, out=print) -> dict:
    env = dict(os.environ, N=str(rec["n"]), ROUNDS="1", FORGE_ARGS="%s --tag %s" % (rec["args"], rec["tag"]))
    out("%s === %s: %s (N=%d) ===" % (time.strftime("%H:%M:%S"), rec["tag"], rec["lever"], rec["n"]))
    subprocess.run(["bash", str(ROOT / "forge_loop.sh")], env=env, cwd=str(ROOT), check=False)
    return round_summary(rec["tag"])


def main() -> int:
    out = lambda *a: print(*a, flush=True)  # noqa: E731
    for rec in RECIPES:
        if already_ran(rec["tag"]):
            out("%s skipped (already in the journal)" % rec["tag"])
            continue
        if not wait_for_lock(out=out):
            out("a round has held the forge lock for 2 h; stopping")
            return 3
        if not wait_for_auth(out=out):
            out("no live session for 3 h; stopping")
            return 2
        summ = run_recipe(rec, out=out)
        summ.update({"lever": rec["lever"], "at": time.time()})
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        with open(RESULTS, "a") as fh:
            fh.write(json.dumps(summ) + "\n")
        out("%s result: landed %d, passes %d, sharpe p50 %s max %s, best %s" % (
            rec["tag"], summ["landed"], summ["passes"], summ["sharpe_p50"], summ["sharpe_max"], summ["best_cells"][:2]))
        if summ["passes"]:
            out("FIRST PASS at %s: %s -- stopping the search (harvest/probe/submit already ran in the loop)" % (rec["tag"], summ["pass_alphas"]))
            return 0
    out("search exhausted with no pass")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
