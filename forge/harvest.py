"""forge.harvest — score the journalled forge rows (design §6): platform gates → turnover band →
DSR from the PnL recordset → candidate for the correlation probe. Writes one JSON row per alpha to
state/forge/scored.jsonl (append; the latest row for an alpha wins on read).

DSR pool (C13): N = every forge row simulated so far for the same (hypothesis, region, delay,
category) with a numeric Sharpe; V[SR] = variance of those Sharpes, per period.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))          # `python forge/x.py` puts forge/ first, not the repo root
from forge import dsr as D, factory as F, score as SC  # noqa: E402

JOURNAL = ROOT / "state/layered/runs/forge.jsonl"
SCORED = ROOT / "state/forge/scored.jsonl"
CURVES = ROOT / "state/pnl_curves"
QUARANTINE = ROOT / "state/forge/quarantine.json"
QUARANTINE_MIN = 4      # a (hypothesis, cell, field) whose first >= 4 simulations ALL failed on the platform


def read_jsonl(path) -> list:
    out = []
    for p in glob.glob(str(path)):
        with open(p) as fh:
            for line in fh:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    return out


def quarantine_key(hypothesis, region, delay, category, field) -> str:
    return "%s|%s|%s|%s|%s" % (hypothesis, region, delay, category, field)


#: D36 (Khoa 2026-09-23 ~17:20, design Q4 option a): the generated branch's quarantine is keyed (cell, field), cell
#: = region/delay (D28). Keyed on (hypothesis, ...) as above, a generated row's hypothesis is its fingerprint family
#: (gen:<family>), which the grammar almost never repeats, so the rule could not fire: architecture round 4 m22
#: re-ran it, 4 FAIL rows of one field under 4 families gave dead keys [] (design §5.1 calls that a DELETION).
#: A (cell, field) key is dead when >= min_n GENERATED rows naming the field failed with no alpha and NO forge row
#: naming it landed there (library rows count as landed only, so the library's own rule is unchanged). A failure is
#: charged to EVERY field the row names (row_fields; round 3 m19: two of the first-leg-only keys named fields that
#: landed in other formulas of the cell). The generated prefix is written out, not imported from forge.gen: this
#: module is in the scorer's import closure (D42) and forge/gen is not.
GEN_PREFIX = "gen:"


def field_quarantine_key(region, delay, field) -> str:
    return "field|%s|%s|%s" % (region, delay, field)


def row_fields(row) -> list:
    """Every field a row or candidate names: the generator's meta.legs[*].fields, else meta.field and meta.field2."""
    m = row.get("meta") or {}
    out = {f for leg in m.get("legs") or [] if isinstance(leg, dict) for f in leg.get("fields") or [] if isinstance(f, str)}
    if not out:
        out = {f for f in (m.get("field"), m.get("field2")) if isinstance(f, str) and f}
    return sorted(out)


def quarantine(path=JOURNAL, out=QUARANTINE, min_n=QUARANTINE_MIN) -> list:
    """(hypothesis, cell, field) triples the platform refuses outright (status FAIL/ERROR, no
    alpha, every time). Measured 2026-09-04: fnd90_game_optimism_gma on JPN/d0 returned FAIL with
    an empty message for every child while its sibling field landed — a FIELD with no data there,
    not a dead hypothesis. Re-simulating it costs quota and teaches nothing, so the planner skips
    these keys. Rewritten on every harvest from the whole journal. Also the D36 (cell, field) keys of
    generated rows (field_quarantine_key, above), in the same list."""
    seen = collections.defaultdict(lambda: [0, 0])          # key -> [failed, landed]
    by_field = collections.defaultdict(lambda: [0, 0])      # D36 (cell, field) key -> [failed, landed]
    for r in read_jsonl(path):
        m = r.get("meta") or {}
        if not m.get("forge") or r.get("status") in (None, "PARENT-POSTED"):
            continue
        k = quarantine_key(m.get("hypothesis"), (r.get("settings") or {}).get("region"),
                           (r.get("settings") or {}).get("delay"), m.get("category"), m.get("field"))
        if r.get("alpha"):
            seen[k][1] += 1
        elif r.get("status") in ("FAIL", "ERROR", "FAILED"):
            seen[k][0] += 1
        generated = str(m.get("hypothesis") or "").startswith(GEN_PREFIX)
        for f in row_fields(r):
            fk = field_quarantine_key((r.get("settings") or {}).get("region"), (r.get("settings") or {}).get("delay"), f)
            if r.get("alpha"):
                by_field[fk][1] += 1
            elif generated and r.get("status") in ("FAIL", "ERROR", "FAILED"):
                by_field[fk][0] += 1
    dead = sorted(k for k, (f, ok) in list(seen.items()) + list(by_field.items()) if f >= min_n and ok == 0)
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out).write_text(json.dumps(dead))
    return dead


def forge_rows(path=JOURNAL) -> dict:
    """alpha -> latest journal row that carries an alpha id and forge meta."""
    rows = {}
    for r in read_jsonl(path):
        if r.get("alpha") and (r.get("meta") or {}).get("forge"):
            rows[r["alpha"]] = r
    return rows


def pool_key(row) -> tuple:
    m = row.get("meta") or {}
    st = row.get("settings") or {}
    return (m.get("hypothesis"), st.get("region"), st.get("delay"), m.get("category"))


def pool_stats(rows) -> dict:
    """{pool_key: (n_trials, var_sr_per_period)} over rows with a numeric Sharpe."""
    sharpes = collections.defaultdict(list)
    for r in rows.values() if isinstance(rows, dict) else rows:
        s = r.get("sharpe")
        if isinstance(s, (int, float)):
            sharpes[pool_key(r)].append(float(s))
    return {k: (len(v), D.var_sr_from_annual_sharpes(v)) for k, v in sharpes.items()}


def curve_daily(curve) -> dict:
    """{date: daily PnL} from a cumulative curve ({date: cum} or [[date, cum], ...]); the difference
    is keyed by the later date; None/NaN points are dropped before differencing (as in forge.dsr)."""
    if isinstance(curve, dict):
        pts = sorted(curve.items())
    elif curve and isinstance(curve[0], (list, tuple)):
        pts = sorted((p[0], p[1]) for p in curve)
    else:
        pts = list(enumerate(curve or []))
    clean = []
    for d, v in pts:
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v != v:
            continue
        clean.append((d, v))
    return {d2: v2 - v1 for (d1, v1), (d2, v2) in zip(clean, clean[1:])}


UNFETCHABLE = ROOT / "state/forge/pbo_unfetchable.json"


def load_unfetchable(path=UNFETCHABLE) -> set:
    try:
        return set(json.load(open(path)))
    except (OSError, ValueError):
        return set()


def save_unfetchable(items, path=UNFETCHABLE) -> None:
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(path).write_text(json.dumps(sorted(items)))


def pool_members(pool, rows) -> list:
    """One journal row per DISTINCT construction (formula + settings) in the pool, the latest row
    winning (resims of the same formula are one trial, papers_robustness §1.3 item 1)."""
    seen = {}
    for r in (rows.values() if isinstance(rows, dict) else rows):
        if pool_key(r) != pool or not isinstance(r.get("sharpe"), (int, float)) or not r.get("alpha"):
            continue
        key = (r.get("meta") or {}).get("cand") or F.candidate_id(r.get("formula") or "", r.get("settings") or {})
        seen[key] = r
    return list(seen.values())


def pool_pbo(pool, rows, fetch, budget: dict, unfetchable: set, curves_dir=None) -> dict:
    """PBO (CSCV, forge.pbo) of one DSR pool from the PnL curves of every distinct member (Khoa
    2026-09-08, Q21/Q30). A verdict ("ok" / "insufficient" / "too short") is issued only when the
    pool is COMPLETE: every member's curve is either in hand or known unfetchable; otherwise the
    status is "pending" and the next run continues fetching. `budget` = {"left": n} shared by every
    pool of the run (adversarial review 2026-09-08: a per-pool budget of 150 × 45 s could exceed the
    loop's harvest timeout; a partial-pool verdict is not the pool's PBO)."""
    from forge import pbo as P
    members = pool_members(pool, rows)
    curves, fetched, missing = {}, 0, 0
    for r in members:
        a = r["alpha"]
        c = cached_curve(a, curves_dir) if curves_dir else cached_curve(a)
        if c is None and a not in unfetchable and budget.get("left", 0) > 0:
            budget["left"] -= 1
            fetched += 1
            c = fetch(a)
            if c is None:
                unfetchable.add(a)
        if c:
            daily = curve_daily(c)
            if daily:
                curves[a] = daily
            else:
                unfetchable.add(a)
        elif a not in unfetchable:
            missing += 1
    res = P.evaluate(curves) if curves else {"pbo": None, "n_trials": 0, "status": "empty", "pass": False, "dates": 0}
    status = "pending" if missing > 0 else res["status"]
    return {"pool": list(pool), "members": len(members), "curves": len(curves), "missing": missing, "fetched": fetched,
            "unfetchable": sum(1 for r in members if r["alpha"] in unfetchable),
            "pbo": res.get("pbo") if status != "pending" else None, "pbo_n": res.get("n_trials"), "dates": res.get("dates"),
            "status": status, "pass": (True if status == "ok" and res.get("pass") else False if status == "ok" else None)}


def pbo_order(cands, rows, corr, posted) -> list:
    """The order in which candidates' pools spend the run's PBO fetch budget: candidates that could
    still be POSTed first (not posted; correlation not measured over the row's lines), newest scored
    first. MEASURED 2026-09-09 13:20 (VPS): the two legacy pools hold 1,159 + 695 distinct members,
    155 curves cached, budget 150 per run -> ~12 runs before either completes, and every one of
    their 21 candidates is already posted or over the lines; a new-arm candidate scored later in the
    file would have waited behind them for hours ("pbo-pending" on the measured day)."""
    from forge import submit as SUB

    def postable(x):
        if x["alpha"] in posted:
            return False
        r = rows.get(x["alpha"]) or {}
        c = corr.get(x["alpha"], {})
        pl, sl = SUB.corr_lines(r)
        for k, line in (("prod", pl), ("self", sl)):
            v = c.get(k)
            if isinstance(v, (int, float)) and v >= line:
                return False
        return True
    return sorted(cands, key=lambda x: (not postable(x), -(x.get("scored_at") or 0)))


def load_scored(path=SCORED) -> dict:
    out = {}
    if pathlib.Path(path).exists():
        for r in read_jsonl(path):
            if r.get("alpha"):
                out[r["alpha"]] = r
    return out


def cached_curve(alpha, curves_dir=CURVES):
    p = pathlib.Path(curves_dir) / ("%s.json" % alpha)
    if p.exists():
        try:
            return json.load(open(p))
        except ValueError:
            return None
    return None


def score_row(row, curve, pools, dataset_load: int = 0) -> dict:
    """The scored record for one journal row. `curve` may be None (DSR not yet possible)."""
    n, var_sr = pools.get(pool_key(row), (1, 0.0))
    dsr_out = D.evaluate(curve, n_trials=n, var_sr=var_sr) if curve else None
    st = SC.stage(row, dsr_out)
    m = row.get("meta") or {}
    rec = {"alpha": row["alpha"], "scored_at": time.time(), "hypothesis": m.get("hypothesis"),
           "category": m.get("category"), "region": (row.get("settings") or {}).get("region"),
           "delay": (row.get("settings") or {}).get("delay"), "mechanism_key": m.get("mechanism_key"),
           "signature": m.get("signature"), "cand": m.get("cand"), "sharpe": row.get("sharpe"),
           "fitness": row.get("fitness"), "turnover": row.get("turnover"), "pool_n": n,
           "sr0_annual": (dsr_out or {}).get("sr0_annual"), "dsr": (dsr_out or {}).get("dsr"),
           "stage": st["stage"], "failed": st["failed"], "pyramids": st["pyramids"],
           "op_count": F.op_count(row.get("formula") or ""), "formula": row.get("formula")}
    if st["stage"] in ("candidate", "dsr-fail"):
        rec["score"] = SC.robust_score(row, dsr_out, dataset_load=dataset_load, op_count=rec["op_count"])
    return rec


def run(rows, scored, pools, fetch, out=print, limit=None) -> list:
    """Score every row that is unscored or still waiting for its curve. `fetch(alpha)` returns a
    cumulative-PnL dict or None (network on the VPS; cached-only offline)."""
    todo = [r for a, r in rows.items() if a not in scored or scored[a].get("stage") in ("needs-dsr", "incomplete")]
    if limit:
        todo = todo[:limit]
    new = []
    for r in todo:
        st = SC.stage(r)
        curve = fetch(r["alpha"]) if st["stage"] == "needs-dsr" else None
        rec = score_row(r, curve, pools)
        new.append(rec)
    stages = collections.Counter(x["stage"] for x in new)
    out("harvest: %d row(s) scored %s" % (len(new), dict(stages)))
    return new


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--offline", action="store_true", help="cached curves only; no network")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--budget", type=float, default=45.0, help="seconds to wait per PnL recordset")
    ap.add_argument("--pbo-fetch", type=int, default=150, help="PnL curves fetched per run for the PBO pools of candidates")
    a = ap.parse_args(argv)
    dead = quarantine()
    if dead:
        print("quarantine: %d hypothesis-cell(s) the platform refuses: %s" % (len(dead), dead[:6]))
    rows = forge_rows()
    scored = load_scored()
    pools = pool_stats(rows)
    if a.offline:
        fetch = cached_curve
    else:
        import layered_sim as LS
        import self_corr_predict as SP
        s = LS.session()
        LS.keep_jar_fresh(s)

        def fetch(alpha, s=s):
            return cached_curve(alpha) or SP.pnl(s, alpha, budget=a.budget)
    new = run(rows, scored, pools, fetch, limit=a.limit)
    if new:
        SCORED.parent.mkdir(parents=True, exist_ok=True)
        with open(SCORED, "a") as fh:
            for rec in new:
                fh.write(json.dumps(rec) + "\n")
    # PBO (CSCV) per pool for EVERY candidate, every run (Khoa Q21: DSR + PBO before a POST). The
    # pool is cumulative, so a verdict is re-issued each run; the fetch budget is per run and each
    # pool's rows are written as soon as its verdict exists (crash-safe: a killed harvest leaves
    # earlier pools judged, the rest "pending" or unjudged — submit holds both).
    scored.update({x["alpha"]: x for x in new})
    if not a.offline:
        want = [x for x in scored.values() if x.get("stage") == "candidate"]
        try:
            from forge import probe as PR, submit as SUB
            import submit_budget as SBG
            want = pbo_order(want, rows, PR.load_corr(), {h["alpha"] for h in SUB.posted_history(ledger=SBG.LEDGER)})
        except Exception as exc:  # noqa: BLE001 -- an unreadable corr/ledger file only costs the ordering
            print("  PBO order: scored-file order (%s: %s)" % (type(exc).__name__, exc))
        pools_done, unfetchable, budget = {}, load_unfetchable(), {"left": a.pbo_fetch}
        with open(SCORED, "a") as fh:
            for x in want:
                r = rows.get(x["alpha"])
                if not r:
                    continue
                pk = pool_key(r)
                if pk not in pools_done:
                    pools_done[pk] = pool_pbo(pk, rows, fetch, budget, unfetchable)
                    save_unfetchable(unfetchable)       # per pool: a harvest killed by its timeout keeps what it learned
                    v = pools_done[pk]
                    print("  PBO pool %s: members %d curves %d missing %d unfetchable %d -> %s pbo=%s n=%s" % (
                        "/".join(str(p) for p in pk), v["members"], v["curves"], v["missing"], v["unfetchable"], v["status"], v["pbo"], v["pbo_n"]))
                v = pools_done[pk]
                if (x.get("pbo_status"), x.get("pbo"), x.get("pbo_pass")) != (v["status"], v["pbo"], v["pass"]):
                    y = dict(x, pbo=v["pbo"], pbo_n=v["pbo_n"], pbo_status=v["status"], pbo_pass=v["pass"], scored_at=time.time())
                    fh.write(json.dumps(y) + "\n")
                    fh.flush()
        save_unfetchable(unfetchable)
    cands = [x for x in new if x["stage"] == "candidate"]
    for x in sorted(cands, key=lambda x: -x.get("score", 0))[:10]:
        print("  CANDIDATE %s %s %s/d%s sharpe %s dsr %.3f score %.3f cells %s" % (
            x["alpha"], x["hypothesis"], x["region"], x["delay"], x["sharpe"], x["dsr"], x["score"], x["pyramids"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
