#!/usr/bin/env python3
"""theme_check.py — Power Pool THEME gate (Khoa 2026-07-17). A "zero-fail" alpha is only
POWER-POOL-submittable if it ALSO matches the ACTIVE weekly Power Pool theme
(state/power_pool_themes.json): region, delay, universe, dataset exclusions, and any
required IS check (e.g. HT_HIGH_TURNOVER_RETURNS_RATIO). Regular/pyramid submission is
SEPARATE and does not need this — CHN pyramid alphas still qualify there.

Pure, deterministic, no API. Usage:
  theme_check.py <alpha_or_targets.json> [--date YYYY-MM-DD]
  python: theme_check.active_theme(date), theme_match(alpha, theme)
"""
from __future__ import annotations
import argparse, json, pathlib, re, sys, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
THEMES = json.load(open(ROOT / "state/power_pool_themes.json"))


def active_theme(date=None):
    # B2 fix: default to the REAL current date, not the pinned active_today (which goes stale and
    # returns the wrong week's theme once the pin is old).
    date = date or datetime.date.today().isoformat()
    for w in THEMES["weeks"]:
        lo, hi = w["range"].split("..")
        if lo <= (date or "") <= hi:
            return w
    return None


# bare pv1 fields carry no underscore-prefix token, so the regex below misses them -> a pure-pv1
# alpha would never trip datasets_not_in=['pv1']. Map them to the 'pv1' dataset explicitly (B2 fix).
PV1_FIELDS = {"open", "close", "high", "low", "volume", "vwap", "returns", "cap", "adv20",
              "sharesout", "dividend", "split"}

def _dataset_of(formula, fields_meta=None):
    f = formula or ""
    # underscore-prefixed dataset fields; (?!\s*\() drops operator calls like ts_delta(/vec_avg(
    # whose prefix ('ts','vec',...) would otherwise be captured as a phantom dataset id.
    m = set(re.findall(r"\b([a-z]+\d*)_[a-z0-9_]+\b(?!\s*\()", f))
    if any(re.search(r"\b" + tok + r"\b", f) for tok in PV1_FIELDS):
        m.add("pv1")                                            # bare pv1 field -> pv1 dataset
    return m


def theme_match(alpha, theme):
    """Return (ok, reasons[]). alpha: {settings, formula, checks?}."""
    if not theme:
        return False, ["no active Power Pool theme for the date"]
    s = alpha.get("settings") or {}
    reasons = []
    if s.get("region") != theme.get("region"):
        reasons.append(f"region {s.get('region')} != theme {theme.get('region')}")
    if theme.get("delay") is not None and s.get("delay") != theme["delay"]:
        reasons.append(f"delay {s.get('delay')} != theme {theme['delay']}")
    if s.get("universe") != theme.get("universe"):
        reasons.append(f"universe {s.get('universe')} != theme {theme.get('universe')}")
    if "neutralization_in" in theme and s.get("neutralization") not in theme["neutralization_in"]:
        reasons.append(f"neutralization {s.get('neutralization')} not in {theme['neutralization_in']}")
    # dataset exclusion
    dsets = _dataset_of(alpha.get("formula", ""))
    for bad in theme.get("datasets_not_in", []):
        if bad in dsets:
            reasons.append(f"uses excluded dataset {bad}")
    # required IS check PASS
    req = theme.get("require_check_pass")
    if req:
        ck = alpha.get("checks") or []
        passed = any((c.get("name") == req and c.get("result") == "PASS") for c in ck if isinstance(c, dict))
        if not passed:
            reasons.append(f"required check {req} not PASS (theme demands it)")
    return len(reasons) == 0, reasons


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--date", default=None)
    a = ap.parse_args(argv)
    th = active_theme(a.date)
    data = json.load(open(a.input))
    rows = data if isinstance(data, list) else [data]
    print(f"active Power Pool theme: {th}")
    nok = 0
    for r in rows:
        ok, reasons = theme_match(r, th)
        nok += ok
        sid = r.get("alpha") or r.get("id") or r.get("old_id")
        print(f"  {sid}: {'POWER-POOL-OK' if ok else 'NO-MATCH: ' + '; '.join(reasons)}")
    print(f"{nok}/{len(rows)} match the active Power Pool theme")
    return 0 if nok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
