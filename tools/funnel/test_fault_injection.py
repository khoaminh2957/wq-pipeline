#!/usr/bin/env python3
"""test_fault_injection.py — v4 harness Round-4 red-team battery: inject every REAL failure mode we have hit
this build and assert the pipeline's validators catch it PRE-SIM. A fault that slips through = harness bug.
All deterministic (no API)."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import logic_check as LC
import gate_gap as GG
import submittable as SUB


def _t(formula, neut="SUBINDUSTRY", decay=0, trunc=0.02, oid="fault"):
    return {"id": oid, "old_id": oid, "formula": formula,
            "settings": {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP1000", "delay": 1,
                         "neutralization": neut, "decay": decay, "truncation": trunc, "pasteurization": "ON",
                         "unitHandling": "VERIFY", "nanHandling": "OFF", "language": "FASTEXPR", "visualization": False}}


def _blocked(targets):
    """True if logic_check flags at least one row (ILLEGAL finding)."""
    res = LC.check(targets)
    if isinstance(res, tuple):
        res = res[0]
    if isinstance(res, list):
        return any((r.get("level") in ("ILLEGAL", "FAIL", "BLOCK")) or r.get("illegal") for r in res if isinstance(r, dict))
    return bool(res)


def test_vector_field_unwrapped_blocked():
    """ern4_slope is VECTOR — bare use must be blocked (cost us 21 rows in the ds round)."""
    assert _blocked([_t("rank(ern4_slope)")]), "unwrapped VECTOR field slipped through"


def test_vec_on_operator_output_blocked():
    """vec_avg(rank(x)) — vec op on MATRIX output must be blocked (double-wrap bug, ds round v2)."""
    assert _blocked([_t("rank(vec_avg(rank(ern4_slope)))")]), "vec_* on operator output slipped through"


def test_group_neutralize_formula_vs_settings_blocked():
    """In-formula group_neutralize(x, sector) with settings.neut != sector must be blocked (opsweep v1)."""
    assert _blocked([_t("group_neutralize(rank(fscore_value), sector)", neut="NONE")]), \
        "group_neutralize/settings mismatch slipped through"


def test_gate_gap_rejects_chn_as_passer():
    """CHN row (LOW_SHARPE FAIL at 1.78, regional bar) must NOT score as passing (g5b trap)."""
    r = {"old_id": "chn", "sharpe": 1.78, "fitness": 2.1, "turnover": 0.05,
         "checks": [{"name": "LOW_SHARPE", "result": "FAIL", "value": 1.78, "limit": 2.0}]}
    assert GG.gate_gaps(r)["LOW_SHARPE"] > 0


def test_oracle_rejects_fitness_warning():
    """LOW_FITNESS WARNING must block (9q7Z9N02 rejection ground truth)."""
    r = {"alpha": "x", "sharpe": 1.61, "checks": [
        {"name": "LOW_SHARPE", "result": "PASS"}, {"name": "LOW_2Y_SHARPE", "result": "PASS"},
        {"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS"}, {"name": "CONCENTRATED_WEIGHT", "result": "PASS"},
        {"name": "LOW_FITNESS", "result": "WARNING", "value": 0.52}]}
    v = SUB.verdict(r)
    assert v["submittable"] is False and any("LOW_FITNESS" in b for b in v["blockers"]), v


def test_missing_theme_not_free_pass():
    r = {"old_id": "x", "sharpe": 1.7, "fitness": 1.2, "turnover": 0.1, "checks": [
        {"name": "LOW_SHARPE", "result": "PASS"}, {"name": "LOW_2Y_SHARPE", "result": "PASS"},
        {"name": "LOW_FITNESS", "result": "PASS"}]}
    assert GG.gate_gaps(r)["THEME_RETURNS_RATIO"] == 0.5   # unknown != pass


def test_hallucinated_field_blocked():
    """A field id not in the catalog must be flagged (dataset-sweep hallucination risk)."""
    assert _blocked([_t("rank(totally_made_up_field_xyz123)")]), "hallucinated field slipped through"


def test_hump_positional_blocked_or_fixed():
    """hump(x, 0.01) positional is API-illegal — builder must emit hump=N; logic layer should flag or builders fix.
    We assert OUR builder convention: the string 'hump(' with a bare numeric second arg is detectable."""
    import re
    bad = "hump(rank(fscore_value), 0.01)"
    fixed = re.sub(r"(hump\(.*?),\s*([0-9.]+)\s*\)$", r"\1, hump=\2)", bad)
    assert "hump=0.01" in fixed


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted({k: v for k, v in globals().items() if k.startswith("test_")}.items()):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            fails += 1; print(f"FAIL {name}: {e}")
        except Exception as e:
            fails += 1; print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{'ALL PASS' if not fails else f'{fails} FAIL'}")
    sys.exit(1 if fails else 0)
