#!/usr/bin/env python3
"""5x backtest for boost_metric.py (Khoa: tested >=5x before deploy; must ALWAYS work)."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tools.funnel.boost_metric import generate, select_boost, METRIC_SPEC

BASE = {"formula": "multiply(rank(-a_field), rank(ts_zscore(b_field, 63)))",
        "settings": {"region": "USA", "universe": "TOP1000", "delay": 1, "unitHandling": "VERIFY"}}


def check():
    e = []
    sigs = []
    for _ in range(5):
        allrows = []
        for m in METRIC_SPEC:
            rows = generate(BASE["formula"], BASE["settings"], m, n=90)
            if len(rows) != 90:
                e.append(f"{m}: {len(rows)} != 90")
            # uniqueness must match the PRECHECK's key7 (excludes past/unit/nan), else the batch is rejected
            def _k7(r):
                s = r["settings"]
                return ("".join(r["formula"].split()), s["region"], s["universe"], s["delay"],
                        s["neutralization"], s["decay"], s["truncation"])
            keys = {_k7(r) for r in rows}
            if len(keys) != 90:
                e.append(f"{m}: {len(keys)} key7-unique != 90 (would trip precheck intra-batch dup)")
            # variant 000 must be the base config VERBATIM (boost never regresses)
            if rows[0]["formula"] != BASE["formula"]:
                e.append(f"{m}: variant 0 not the base formula")
            for r in rows:
                if "{B}" in r["formula"] or "{" in r["formula"]:
                    e.append(f"{m}: unfilled wrap {r['formula'][:50]}"); break
                if r["formula"].startswith("hump(") and "hump=" not in r["formula"]:
                    e.append(f"{m}: hump missing named arg: {r['formula'][:50]}"); break
                if BASE["formula"].split("(")[0] not in r["formula"]:
                    e.append(f"{m}: base lost {r['formula'][:50]}"); break
                s = r["settings"]
                if s["region"] != "USA" or s["universe"] != "TOP1000":
                    e.append(f"{m}: cell drift"); break
                # no double-smooth: a ts_decay wrap must pin settings decay=0
                if r["formula"].startswith("ts_decay_linear") and s["decay"] != 0:
                    e.append(f"{m}: double-smooth {r['formula'][:40]} decay={s['decay']}"); break
            allrows.append((m, rows))
        sigs.append(json.dumps([(m, r) for m, r in allrows], sort_keys=True))
    if len(set(sigs)) != 1:
        e.append(f"NON-DETERMINISTIC: {len(set(sigs))} distinct across 5 runs")

    # select_boost contract: certify ONLY zero-fail + meets threshold; else honest ceiling
    #
    # Every row meant to READ as zero-fail must adjudicate the base gate set: gate_lib now treats a
    # gate that is merely ABSENT as unproven rather than passed, so `checks: []` and a lone WARNING
    # no longer certify. The rows below keep their original intent (x1 = a WARNING must not block;
    # x2 = a zero-fail below the bar is the honest ceiling) with payloads that state it.
    # exactly gates.expected_gates(("USA","TOP3000",1)) — the set the platform actually returns
    # for this segment, learned from 35,371 journal rows. Independently, gate_lib.required_present
    # ("USA", 1) derives the same six.
    BASE_GATES = ["LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER", "HIGH_TURNOVER",
                  "CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"]

    def zf(extra=()):
        return [{"name": n, "result": "PASS"} for n in BASE_GATES] + list(extra)

    # gates.zero_fail resolves a row's SEGMENT from row["settings"], falling back to a lookup of
    # old_id in the targets files — and a synthetic old_id is in none of them, so the row scores
    # (False, [], ["<unknown segment>"]) no matter what its checks say. Carrying settings is what
    # makes these rows scoreable at all; it is the same gap that makes 98% of journal rows depend
    # on a targets-file lookup instead of describing themselves.
    SEG = {"region": "USA", "universe": "TOP3000", "delay": 1}

    zf_pass = {"old_id": "x1", "settings": SEG, "sharpe": 1.7,
               "checks": zf([{"name": "UNITS", "result": "WARNING"}])}
    zf_low = {"old_id": "x2", "settings": SEG, "sharpe": 1.2, "checks": zf()}
    fail_high = {"old_id": "x3", "settings": SEG, "sharpe": 2.5, "checks": [{"name": "CONCENTRATED_WEIGHT", "result": "FAIL"}]}
    r = select_boost([zf_low, fail_high, zf_pass], "sharpe")
    if not r["certified"] or r["best"]["old_id"] != "x1":
        e.append(f"select: should certify x1 (1.7 zero-fail), got {r['best'] and r['best']['old_id']} cert={r['certified']}")
    # a FAILing 2.5-sharpe must NEVER be certified (anti-overfit): best zero-fail is x1
    r2 = select_boost([fail_high, zf_low], "sharpe")
    if r2["certified"]:
        e.append("select: certified a non-zero-fail / sub-threshold pool (must not)")
    if r2["best"]["old_id"] != "x2":  # x2 is the only zero-fail -> the honest ceiling
        e.append(f"select: ceiling should be x2, got {r2['best']['old_id']}")
    # ceiling honesty: all-fail pool -> never certified
    r3 = select_boost([fail_high], "sharpe")
    if r3["certified"]:
        e.append("select: certified an all-FAIL pool")
    # band metric (turnover): 0.3 is in [0.01,0.7] -> pass; 0.9 -> fail
    tb = select_boost([{"old_id": "t1", "settings": SEG, "turnover": 0.3, "checks": zf()}], "turnover")
    if not tb["certified"]:
        e.append("select: turnover 0.3 should certify (in band)")
    tb2 = select_boost([{"old_id": "t2", "settings": SEG, "turnover": 0.9, "checks": zf()}], "turnover")
    if tb2["certified"]:
        e.append("select: turnover 0.9 should NOT certify (out of band)")
    # robust_sharpe: value lives inside the LOW_ROBUST_UNIVERSE check (no top-level field)
    rb = select_boost([{"old_id": "rb1", "settings": SEG, "checks": zf([
        {"name": "LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO", "result": "PASS", "value": 0.6}])}], "robust_sharpe")
    if not rb["certified"] or rb["ceiling"] != 0.6:
        e.append(f"select: robust_sharpe should read 0.6 from check + certify, got {rb['ceiling']} cert={rb['certified']}")
    # max_position / max_trade: value lives inside the HT_INVESTABLE_MAX_* check, bar 2.0
    mp = select_boost([{"old_id": "mp1", "settings": SEG, "checks": zf([
        {"name": "HT_INVESTABLE_MAX_POSITION_SHARPE", "result": "PASS", "value": 2.3}])}], "max_position")
    if not mp["certified"] or mp["ceiling"] != 2.3:
        e.append(f"select: max_position should read 2.3 from check + certify vs 2.0, got {mp['ceiling']} cert={mp['certified']}")
    mt = select_boost([{"old_id": "mt1", "settings": SEG, "checks": [
        {"name": "HT_INVESTABLE_MAX_TRADE_SHARPE", "result": "PASS", "value": 1.5}]}], "max_trade")
    if mt["certified"]:
        e.append("select: max_trade 1.5 < bar 2.0 must NOT certify")
    # ESCALATION LADDER: blend_legs wraps the base as an equal-weight add-blend (Tier 2)
    bl = generate(BASE["formula"], BASE["settings"], "sharpe", n=90, blend_legs=["some_leg"])
    if not bl[0]["formula"].startswith("add(zscore(") or "zscore(rank(some_leg))" not in bl[0]["formula"]:
        e.append(f"blend: Tier-2 not an add-blend of base+leg: {bl[0]['formula'][:60]}")
    bl2 = generate(BASE["formula"], BASE["settings"], "sharpe", n=90, blend_legs=["leg1", "leg2"])
    if "zscore(rank(leg1))" not in bl2[0]["formula"] or "zscore(rank(leg2))" not in bl2[0]["formula"]:
        e.append("blend: Tier-3 two-leg blend missing a leg")
    return e


if __name__ == "__main__":
    for i in range(1, 6):
        er = check()
        print(f"RUN {i}: {'PASS' if not er else 'FAIL -> ' + '; '.join(er)}")
    er = check()
    print(f"\n{'5/5 runs PASS' if not er else 'FAILED: ' + '; '.join(er)}")
    sys.exit(0 if not er else 1)
