#!/usr/bin/env python3
"""meaning_gate.py — pre-sim MEANING validation for the alpha-loop skill (Khoa 2026-07-21).

Before an alpha is simmed, every leg of its `add(...)` ensemble is checked INSIDE-OUT: does
each successive operator-nesting layer still carry economic MEANING? A cheap 3-agent panel
votes yes/no per layer; when the majority says NO, the structure is TRIMMED at that layer
(the leg is cut back to its last meaningful layer, or dropped entirely if the innermost fails).

This module is the mechanical half: (1) split an ensemble into legs, (2) decompose each leg
into its inside-out layers with a human gloss (for the agents to judge), (3) rebuild the
ensemble from the surviving/trimmed legs. The yes/no voting is done by the skill via the
Agent/Workflow tool (kept out of here so this stays pure + importable).
"""
from __future__ import annotations
import json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CATALOG = ROOT / "fetched/fields_all.jsonl"

_DESC = None
def field_desc(fid: str) -> str:
    global _DESC
    if _DESC is None:
        _DESC = {}
        for line in open(CATALOG):
            try: r = json.loads(line)
            except: continue
            _DESC.setdefault(r["id"], r.get("description", ""))
    return _DESC.get(fid, "")

def split_legs(alpha: str):
    """Return (prefix, legs, suffix) where legs are the top-level args of the ensemble's add(...).
    prefix/suffix are the wrapper text so we can rebuild. If no add(), the whole alpha is one leg."""
    m = re.search(r"add\(", alpha)
    if not m:
        return None, [alpha.strip()], None
    i = m.end(); depth = 1; start = i; args = []
    while i < len(alpha) and depth > 0:
        ch = alpha[i]
        if ch == "(": depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0: break
        elif ch == "," and depth == 1:
            args.append(alpha[start:i].strip()); start = i + 1
        i += 1
    args.append(alpha[start:i].strip())
    legs = [a for a in args if not re.match(r"[a-z_]+\s*=", a)]      # drop filter=true etc.
    tail = [a for a in args if re.match(r"[a-z_]+\s*=", a)]
    prefix = alpha[:m.end()]; suffix = ")" + alpha[i + 1:]
    return (prefix, tail, suffix), legs, None

def layers(leg: str):
    """Inside-out list of (layer_expr, gloss) for one leg — peel outer operators one at a time."""
    leg = leg.strip()
    out = []
    def peel(expr):
        expr = expr.strip()
        m = re.match(r"^([a-z_]+)\((.*)\)$", expr, re.S)
        # unwrap a leading unary minus / weight-multiply first
        if expr.startswith("-") and not m:
            inner = expr[1:].strip(); peel(inner)
            out.append((expr, f"negate ({_gloss_op('reverse')})")); return
        if not m:
            # base field or field-arithmetic (e.g. F/ts_mean(F,20) or F1/F2)
            out.append((expr, _gloss_base(expr))); return
        op, args = m.group(1), m.group(2)
        # split top-level args
        parts, depth, s = [], 0, 0
        for i, ch in enumerate(args):
            if ch == "(": depth += 1
            elif ch == ")": depth -= 1
            elif ch == "," and depth == 0: parts.append(args[s:i]); s = i + 1
        parts.append(args[s:])
        primary = parts[0].strip()
        peel(primary)
        out.append((expr, _gloss_op(op, parts)))
    peel(leg)
    # dedup consecutive identical
    seen, res = set(), []
    for e, g in out:
        if e in seen: continue
        seen.add(e); res.append((e, g))
    return res

def _gloss_base(expr):
    fids = re.findall(r"[a-z_][a-z0-9_]+", expr)
    fids = [f for f in fids if f not in ("ts_mean", "ts_delay", "divide", "vec_avg", "subtract")]
    descs = "; ".join(f"{f}=«{field_desc(f)[:60]}»" for f in fids[:3] if field_desc(f))
    return f"base value: {expr}  [{descs}]" if descs else f"base value: {expr}"

def _gloss_op(op, parts=None):
    G = {"ts_av_diff": "deviation from its own recent mean (mean-reversion signal)",
         "ts_delta": "change over d days (momentum/acceleration)",
         "ts_zscore": "standardized vs its own recent history",
         "ts_decay_linear": "time-smoothed (turnover valve)", "ts_mean": "recent average",
         "rank": "cross-sectional rank [0,1] across stocks",
         "reverse": "sign-flipped (bet the opposite direction)",
         "zscore": "cross-sectional standardization", "signed_power": "sign-preserving tail-shape",
         "divide": "ratio of two quantities", "subtract": "difference of two quantities",
         "multiply": "scaled by a weight / interacted", "add": "additive ensemble of legs"}
    return G.get(op, op)

def rebuild(wrap, legs):
    """Rebuild the ensemble from (possibly trimmed) legs. wrap=(prefix,tail,suffix) or None
    (single-leg alpha). legs=[] -> alpha is dropped (returns None)."""
    if wrap is None:                              # single-leg alpha
        return legs[0] if legs else None
    prefix, tail, suffix = wrap
    if not legs: return None
    return prefix + ", ".join(legs + tail) + suffix

def prune_from_verdicts(alpha: str, verdicts: list):
    """Apply the 3-agent meaning-gate result. verdicts = [{leg_index, trimmed_expr, full_kept}].
    Keep full-kept legs verbatim; keep a trimmed leg only if it is still a usable SIGNAL
    (contains rank/zscore/a transform) — a leg trimmed down to a bare field is dropped
    ('cắt tới không còn chỗ để xét nữa thì thôi'). Returns (pruned_alpha, kept_count, dropped)."""
    parsed, _, _ = split_legs(alpha)
    kept, dropped = [], []
    for v in sorted(verdicts, key=lambda x: x["leg_index"]):
        e = v.get("trimmed_expr")
        usable = bool(e) and bool(re.search(r"[a-z_]+\(", e))   # any operator application = still a signal; only a bare field is dropped
        if v.get("full_kept") or usable:
            kept.append(e)
        else:
            dropped.append(v["leg_index"])
    return rebuild(parsed, kept), len(kept), dropped

if __name__ == "__main__":
    import sys
    alpha = sys.argv[1] if len(sys.argv) > 1 else \
        "signed_power(zscore(ts_decay_linear(add(multiply(-rank(ts_av_diff(min_adjusted_net_income_guidance, 5)), 0.55), multiply(rank(sales_estimate_count/ts_mean(sales_estimate_count, 20)), 0.4), filter=true), 20)), 2.5)"
    parsed, legs, _ = split_legs(alpha)
    print(f"{len(legs)} legs\n")
    for i, leg in enumerate(legs):
        print(f"LEG {i}: {leg}")
        for j, (e, g) in enumerate(layers(leg)):
            print(f"   L{j} {e}\n        -> {g}")
        print()
