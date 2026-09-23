#!/usr/bin/env python3
"""loop.py — the automated alpha-loop driver (core of the alpha-loop skill).

Runs end-to-end until it finds trading-logic alphas that pass ALL hard gates (zero-fail),
or a round budget is spent. Each round:
  GEN   trading-logic strategies for the target dataset(s)  (strategy_lib, dataset-agnostic)
  SIM   validate -> run_multisim (live, --sweep)            (blocking; operator single-stream)
  READ  parse results by old_id from state/resim_results.jsonl
  KEEP  any ZERO-FAIL -> collect as winners
  REFINE next round from the signal the data gave:
        - FLIP: a strongly-NEGATIVE-sharpe strategy is the right mechanic with the wrong sign
                -> emit the opposite sign (toggle a leading reverse()).
        - VALVE: a strong-sharpe strategy failing only via high turnover/fitness
                 -> re-emit with decay + INDUSTRY/SUBINDUSTRY neutralization (the gentle valve).
        - SWEEP: promising positive strategies -> wider neut/decay/trunc.
        - DROP dead mechanics (|sharpe|<0.4).
Stops when >=`target_winners` zero-fail found or `max_rounds` reached.

Usage:
  python3 tools/alpha_loop/loop.py --datasets option6,analyst4 --universe TOP3000 \
      --max-rounds 4 --target-winners 3
"""
from __future__ import annotations
import argparse, json, pathlib, subprocess, sys, re, itertools, time, os
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import strategy_lib as sl
import knowledge as kb

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools" / "funnel"))
import submittable as sub   # real submit gate (WARNING-below-bar + non-HARD FAIL aware)
RESULTS = ROOT / "state/resim_results.jsonl"
FUNNEL = ROOT / "state/funnel"
VALIDATE = ROOT / "tools/validate_targets.py"
RUNSIM = ROOT / "tools/funnel/run_multisim.py"
# Gate set: ONE definition, tools/funnel/gates.py. This literal was copied here and in
# four other files; the copies disagreed (this one had LOW_RETURNS but the others did not), so the same journal
# scored to different zero-fail counts depending on which file did the scoring.
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent.parent / "tools" / "funnel"))
from gates import BLOCKING as HARD
def settings(neut, trunc, decay, universe):
    return {"instrumentType": "EQUITY", "region": "USA", "universe": universe, "delay": 1,
            "decay": decay, "neutralization": neut, "truncation": trunc, "pasteurization": "ON",
            "unitHandling": "VERIFY", "nanHandling": "OFF", "maxTrade": "OFF", "maxPosition": "OFF",
            "language": "FASTEXPR", "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31"}

def flip(formula: str) -> str:
    f = formula.strip()
    if f.startswith("reverse(") and f.endswith(")"):
        return f[len("reverse("):-1]
    return f"reverse({f})"

def write_targets(rows, path):
    json.dump(rows, open(path, "w"), indent=1)

def _fair_cap(rows, n=180):
    """Cap to n rows with per-dataset FAIRNESS: round-robin across _ds groups (preserving each
    group's internal order) instead of a position-based rows[:n] cut, so a multi-dataset batch
    never drops whole tail datasets (B10 O3: 10 datasets -> the last 2 got 0 sims). Single-dataset
    batches and batches already <= n are returned unchanged. n stays the sim-budget."""
    if len(rows) <= n:
        return rows
    groups = {}
    for r in rows:
        groups.setdefault(r.get("_ds"), []).append(r)
    queues = list(groups.values())
    out = []
    while len(out) < n and any(queues):
        for q in queues:
            if q and len(out) < n:
                out.append(q.pop(0))
    return out

def validate_drop(path, rows):
    """Validate; on failure DROP only the individually-failing rows (parsed from the per-row
    `FAIL: <old_id>: ...` lines validate_targets already emits) and re-validate the survivors,
    instead of discarding the WHOLE batch — and every remaining round — on one poison row
    (dup/bad-operator/unbalanced-paren). Rewrites `path` to the survivors and returns them (possibly
    empty). validate_targets.py keeps its strict all-or-nothing exit for other callers; the
    drop-and-continue is scoped here (B9 yield fix, Khoa 2026-07-24)."""
    r = subprocess.run([sys.executable, str(VALIDATE), str(path)], capture_output=True, text=True)
    if r.returncode == 0:
        return rows
    bad = set()
    for ln in r.stdout.splitlines():
        m = re.match(r"FAIL:\s*([^:]+):", ln)
        if m: bad.add(m.group(1).strip())
    survivors = [row for row in rows if str(row.get("old_id") or row.get("id")) not in bad]
    if not survivors or len(survivors) == len(rows):   # all bad, or a batch-level error (no row to drop)
        print(r.stdout[-1500:]); return []
    write_targets(survivors, path)
    r2 = subprocess.run([sys.executable, str(VALIDATE), str(path)], capture_output=True, text=True)
    if r2.returncode != 0:                              # residual batch-level error -> can't salvage
        print(r2.stdout[-1500:]); return []
    print(f"  [validate] dropped {len(bad)} poison row(s); {len(survivors)}/{len(rows)} survive", flush=True)
    return survivors

def sim(path) -> bool:
    """Live multisim (blocking). Returns True if it completed."""
    print(f"  [sim] launching {path.name} ...", flush=True)
    r = subprocess.run([sys.executable, str(RUNSIM), "--sweep", "--stall-timeout", "1000", str(path)],
                       capture_output=True, text=True)
    tail = r.stdout.strip().splitlines()[-2:] if r.stdout else []
    print("   ", " | ".join(tail), flush=True)
    return "RESIM COMPLETE" in (r.stdout or "")

def read_results(oids: set) -> dict:
    """Latest result row per old_id in `oids`."""
    out = {}
    for line in open(RESULTS):
        try: d = json.loads(line)
        except: continue
        if isinstance(d, dict) and d.get("old_id") in oids:
            out[d["old_id"]] = d
    return out

def classify(d, formula, s):
    raw = d.get("checks")
    chk = {c["name"]: c for c in raw if isinstance(c, dict)} if isinstance(raw, list) else {}
    verified = isinstance(raw, list) and len(chk) > 0   # gates actually evaluated (not None/malformed)
    fails = [n for n in HARD if chk.get(n, {}).get("result") == "FAIL"]
    sh = d.get("sharpe"); ft = d.get("fitness"); tv = d.get("turnover")
    rec = dict(oid=d.get("old_id"), alpha=d.get("alpha"), formula=formula, settings=s,
               sh=sh, ft=ft, tv=tv, ret=d.get("returns"), nfail=len(fails), fails=fails)
    if not isinstance(sh, (int, float)):
        rec["cls"] = "DEAD"; return rec
    # ZERO_FAIL must match the REAL submit gate, not just "no HARD FAIL": a WARNING-below-bar must-pass
    # gate (e.g. LOW_2Y_SHARPE/LOW_SHARPE) or a non-HARD IS-check FAIL (e.g. LOW_ROBUST_UNIVERSE_SHARPE)
    # blocks submission even when fails==[]. submittable.verdict() encodes that (incl. IS_LADDER waiver).
    # sub.verdict() is the AUTHORITATIVE bar: [sharpe>=1.58 AND fitness>=1.0 AND 2Y ok] OR
    # IS_LADDER_SHARPE>=2.02 (A17YGP7d precedent). Do NOT re-AND sh>=1.58/ft>=1.0 here or the ladder-escape
    # path is lost (a sh1.0/ft0.54 alpha with ladder 2.08 is submittable but would misclassify as SWEEP).
    if verified and len(fails) == 0 and sub.verdict(d).get("submittable") is True:
        rec["cls"] = "ZERO_FAIL"
    elif sh <= -0.85:
        rec["cls"] = "FLIP"         # right mechanic, wrong sign -> emit the opposite sign
    elif sh >= 1.3:
        rec["cls"] = "VALVE"        # strong but fails a gate (usually fitness via turnover)
    elif abs(sh) >= 0.55:
        rec["cls"] = "SWEEP"        # promising -> wider settings (flip if negative)
    else:
        rec["cls"] = "DEAD"
    return rec

def refine_rows(recs, universe, seen, run, rnd):
    """Next-round targets from this round's classification. `run` = per-run nonce and `rnd` = the
    round index -> old_ids are UNIQUE per (run, round). Without `rnd` the index restarts at 000 every
    refine round and the flip/valve/sweep tags repeat, so round N and round N+1 mint the SAME oid for
    DIFFERENT formulas; resim_bulk then skips the round-N+1 row (its oid is already 'done' in the
    accumulating journal) and read_results pairs round N's stale metrics with round N+1's formula."""
    rows = []
    NEUT = ["INDUSTRY", "SUBINDUSTRY"]; DEC = [6, 12, 20]
    def add(tag, f, neut, trunc, decay, ds):
        k = ("".join(f.split()), neut, trunc, decay)
        if k in seen: return
        seen.add(k)
        oid = f"al_{run}_r{rnd}_{tag}_{len(rows):03d}"
        rows.append({"old_id": oid, "id": oid, "formula": f + "\n", "_ds": ds,
                     "settings": settings(neut, trunc, decay, universe)})
    for r in recs:
        base = r["formula"].strip(); ds = r.get("ds")
        if r["cls"] == "FLIP":
            g = flip(base)                                    # right mechanic, wrong sign
            for neut, decay in itertools.product(NEUT, DEC): add("flip", g, neut, 0.05, decay, ds)
        elif r["cls"] == "VALVE":                             # strong -> just cut turnover
            for neut, decay in itertools.product(NEUT, DEC): add("valve", base, neut, 0.05, decay, ds)
        elif r["cls"] == "SWEEP":                             # promising -> the turnover VALVE
            g = base if r["sh"] > 0 else flip(base)           #   (decay+neut) is the main lever
            for neut, decay in itertools.product(NEUT, DEC): add("sweep", g, neut, 0.05, decay, ds)
    return rows

def gen_round0(datasets, per, universe, seen, run):
    rows = []
    # YIELD-optimal (iter26b A/B, Khoa 2026-07-24): INDUSTRY/SUBINDUSTRY gave ALL zero-fails +
    # highest median sharpe + fewest warnings; CROWDING/STATISTICAL de-crowding HALVED sharpe and
    # RAISED warnings (a regression). Decay 6/12 (not 0) lowers turnover -> fewer HT_* warnings.
    combos = list(itertools.product(["INDUSTRY", "SUBINDUSTRY", "MARKET"], [6, 12]))
    for ds in datasets:
        # proven winners are re-seeded (tag *_seed) by gen_strategies but emit formula-only, so map
        # each back to its OWN proven neut/decay/trunc and re-sim there — NOT a positional round-0
        # combo (B10 O4): a decay-20 refine-winner re-simmed at INDUSTRY/dc6 may not reproduce
        # zero-fail. Universe stays the run's choice. Non-seed rows keep the positional combos.
        proven = {"".join(w["formula"].split()): w.get("settings") for w in kb.seeds_for(ds)}
        si = 0
        for tag, f in sl.gen_strategies(ds, n=per * 3):
            ps = proven.get("".join(f.split())) if tag.endswith("_seed") else None
            if ps:
                neut, decay, trunc = ps.get("neutralization", "INDUSTRY"), ps.get("decay", 6), ps.get("truncation", 0.05)
            else:
                neut, decay = combos[si % len(combos)]; si += 1; trunc = 0.05
            k = ("".join(f.split()), neut, trunc, decay)
            if k in seen: continue
            seen.add(k)
            oid = f"al_{run}_r0_{tag}_{len(rows):03d}"
            rows.append({"old_id": oid, "id": oid, "formula": f + "\n", "_ds": ds,
                         "settings": settings(neut, trunc, decay, universe)})
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", required=True)
    ap.add_argument("--universe", default="TOP3000")
    ap.add_argument("--per", type=int, default=8)
    ap.add_argument("--max-rounds", type=int, default=4)
    ap.add_argument("--target-winners", type=int, default=3)
    ap.add_argument("--tag", default="al")
    a = ap.parse_args()
    datasets = [d.strip() for d in a.datasets.split(",") if d.strip()]
    run = f"{a.tag}_{int(time.time())%100000:05d}_{os.getpid()%1000:03d}"   # per-run nonce -> oids unique per run (zero-padded + delimited so distinct (time,pid) can't concat-collide)
    seen = set(); winners = []
    rows = gen_round0(datasets, a.per, a.universe, seen, run)

    for rnd in range(a.max_rounds):
        if not rows:
            print(f"[round {rnd}] no candidates to sim — stop."); break
        rows = _fair_cap(rows, 180)
        path = FUNNEL / f"{a.tag}_r{rnd}_targets.json"
        write_targets(rows, path)
        print(f"[round {rnd}] {len(rows)} strategies -> {path.name}", flush=True)
        rows = validate_drop(path, rows)
        if not rows:
            print(f"[round {rnd}] no rows survived validation — stop."); break
        if not sim(path):
            print(f"[round {rnd}] sim did not complete — stop."); break
        oid2f = {r["old_id"]: (r["formula"], r["settings"]) for r in rows}
        oid2ds = {r["old_id"]: r.get("_ds") for r in rows}
        res = read_results(set(oid2f))
        recs = [classify(d, oid2f[oid][0], oid2f[oid][1]) for oid, d in res.items()]
        for r in recs: r["ds"] = oid2ds.get(r["oid"])         # carry dataset explicitly (not parsed from oid)
        from collections import Counter
        dist = Counter(r["cls"] for r in recs)
        print(f"[round {rnd}] results: {dict(dist)}  (simmed {len(recs)}/{len(rows)})", flush=True)
        # SELF-UPGRADE: record what this round learned (winners, sign-flips, good/dead fields) per
        # dataset. Uses rec["ds"] (carried), so it also learns from REFINE rounds (flip/valve/sweep),
        # which is where zero-fails actually emerge — the old oid-parse missed all of them.
        for ds in datasets:
            kb.record_run(ds, [r for r in recs if r.get("ds") == ds])
        print(f"[round {rnd}] knowledge upgraded -> {kb.KB.name}", flush=True)
        zf = [r for r in recs if r["cls"] == "ZERO_FAIL"]
        zf.sort(key=lambda r: -(r["sh"] or 0))
        for r in zf:
            print(f"   ZERO-FAIL {r['alpha']} sh={r['sh']} fit={r['ft']} tvr={r['tv']} :: {r['formula'][:90]}")
        winners += zf
        if len(winners) >= a.target_winners:
            print(f"[stop] {len(winners)} zero-fail winners reached at round {rnd}."); break
        # promise-order recs before refine so the strongest near-winners' variants survive the
        # per-round cap (B10 O3): VALVE/FLIP (near-winners) first, then by |sharpe| desc.
        _PRIO = {"VALVE": 0, "FLIP": 1, "SWEEP": 2}
        recs.sort(key=lambda r: (_PRIO.get(r["cls"], 3), -abs(r.get("sh") or 0)))
        rows = refine_rows(recs, a.universe, seen, run, rnd + 1)

    print("\n===== ALPHA-LOOP DONE =====")
    print(f"zero-fail winners: {len(winners)}")
    winners.sort(key=lambda r: -(r["sh"] or 0))
    outp = FUNNEL / f"{a.tag}_winners.json"
    json.dump([{k: r[k] for k in ("oid","alpha","formula","settings","sh","ft","tv","ret")} for r in winners],
              open(outp, "w"), indent=1)
    print(f"winners -> {outp}")
    for r in winners[:10]:
        print(f"  {r['alpha']} sh={r['sh']} fit={r['ft']} tvr={r['tv']} | {r['settings']['neutralization']}/dc{r['settings']['decay']} :: {r['formula'].strip()[:100]}")

if __name__ == "__main__":
    main()
