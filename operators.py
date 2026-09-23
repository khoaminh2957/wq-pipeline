"""[13] B5 — operator allowlist (authoritative) / blocklist (tier-derived).

The STANDARD-tier blocklist below is verified 2026-04-20 via inaccessible-operator
sim errors (batches ZY24/ZY66/batch35). enum is CLOSED for the frozen tier: the
generator [19] may only emit operators in ALLOWLIST.
"""
from __future__ import annotations
import re
import ast as _ast

# verified STANDARD-tier inaccessible (consultant-only). mult is a deprecated alias -> use multiply.
BLOCKLIST = frozenset({
    "vector_neut", "hump_decay", "tail", "regression_neut",
    "ts_decay_exp_window", "s_log_1p", "mult",
})

# ts_regression IS available (keyword rettype) — explicitly NOT blocked.
EXPLICITLY_AVAILABLE = frozenset({"ts_regression"})

# baseline allowlist of common Fast Expression operators (arity hints for the validator).
# This is the closed enum the generator samples from. Extend cautiously + re-verify live.
ALLOWLIST_ARITY: dict[str, tuple[int, int]] = {
    # arithmetic
    "add": (2, 99), "subtract": (2, 2), "multiply": (2, 99), "divide": (2, 2),
    "reverse": (1, 1), "abs": (1, 1), "sign": (1, 1), "signed_power": (2, 2),
    "log": (1, 1), "sqrt": (1, 1), "power": (2, 2), "inverse": (1, 1),
    "max": (2, 99), "min": (2, 99),
    # time-series
    "ts_rank": (2, 2), "ts_zscore": (2, 2), "ts_mean": (2, 2), "ts_std_dev": (2, 2),
    "ts_delta": (2, 2), "ts_delay": (2, 2), "ts_sum": (2, 2), "ts_product": (2, 2),
    "ts_min": (2, 2), "ts_max": (2, 2), "ts_arg_min": (2, 2), "ts_arg_max": (2, 2),
    "ts_corr": (3, 3), "ts_covariance": (3, 3), "ts_regression": (3, 4),
    "ts_decay_linear": (2, 2), "ts_scale": (2, 2), "ts_quantile": (2, 3),
    "ts_backfill": (2, 3), "ts_step": (1, 1), "hump": (2, 2), "days_from_last_change": (1, 1),
    "ts_av_diff": (2, 2),                       # x - ts_mean(x,d); verified (used in submitted alphas)
    # vector (multi-value field reducers)
    "vec_avg": (1, 1),                          # verified (used in 9020 submitted formulas, e.g. vec_avg(anl4_*))
    # cross-sectional
    "rank": (1, 2), "zscore": (1, 1), "scale": (1, 3), "winsorize": (1, 3),
    "normalize": (1, 3), "quantile": (1, 3),
    # group
    "group_neutralize": (2, 2), "group_rank": (2, 2), "group_zscore": (2, 2),
    "group_mean": (3, 3), "group_scale": (2, 2), "group_sum": (2, 2),
    "group_backfill": (3, 4), "bucket": (1, 9),
    # logic / conditional
    "if_else": (3, 3), "trade_when": (3, 3), "keep": (2, 3),
    "and": (2, 2), "or": (2, 2), "less": (2, 2), "greater": (2, 2),
    "equal": (2, 2), "not": (1, 1), "is_nan": (1, 1),
}

ALLOWLIST = frozenset(ALLOWLIST_ARITY)

# group operators usable for neutralization-style grouping (dataset-category aware).
GROUP_FIELDS = (
    "industry", "subindustry", "sector", "market",
)

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# operator = identifier immediately followed by '('
_CALL = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def operators_in(formula: str) -> list[str]:
    """Extract operator names (identifiers used as function calls) from a formula."""
    return [m.group(1) for m in _CALL.finditer(formula)]


def fields_in(formula: str) -> list[str]:
    """Extract candidate data-field identifiers (tokens NOT used as calls and not operators)."""
    calls = set(operators_in(formula))
    out = []
    for m in _TOKEN.finditer(formula):
        tok = m.group(0)
        nxt = formula[m.end():m.end() + 1]
        prev = formula[m.start() - 1:m.start()] if m.start() > 0 else ""
        if nxt == "(":            # it's an operator call
            continue
        if nxt == "=":            # kwarg NAME (filter=, std=, hump=) — not a data field
            continue
        if prev == "=":           # kwarg VALUE (=true, =false) — not a data field
            continue
        if tok in ("true", "false"):
            continue
        if tok in ALLOWLIST or tok in BLOCKLIST or tok in calls:
            continue
        if tok in GROUP_FIELDS:
            continue
        if re.fullmatch(r"\d+", tok):
            continue
        out.append(tok)
    # dedupe preserve order
    seen = set(); res = []
    for t in out:
        if t not in seen:
            seen.add(t); res.append(t)
    return res


def blocklist_violations(formula: str) -> list[str]:
    return sorted({op for op in operators_in(formula) if op in BLOCKLIST})


def unknown_operators(formula: str) -> list[str]:
    """Operators used that are neither in the allowlist nor explicitly available."""
    return sorted({
        op for op in operators_in(formula)
        if op not in ALLOWLIST and op not in EXPLICITLY_AVAILABLE
    })


# ─────────────────────────────────────────────────────────────────────────────
# AST validation (structure-aware). FASTEXPR is a syntactic SUBSET of a Python
# expression (`op(arg, ...)` nesting, infix > < + - * /, unary -, numbers, and
# kwargs like `filter=true`), so Python's `ast` module gives a real parse tree.
# Unlike the regex scan this knows nesting + ARITY (positional arg count per op).
# ─────────────────────────────────────────────────────────────────────────────
def parse_ast(formula: str):
    """Parse FASTEXPR into a Python expression AST. Returns the tree, or None if the
    formula is unparseable (malformed: unbalanced parens, stray tokens, ...)."""
    try:
        return _ast.parse(formula or "", mode="eval")
    except SyntaxError:
        return None


def _ast_calls(tree):
    """Every Call whose function is a bare name -> that name is the operator."""
    return [n for n in _ast.walk(tree) if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)]


def ast_operators(tree) -> list[str]:
    return [n.func.id for n in _ast_calls(tree)]


def ast_fields(tree) -> list[str]:
    """Leaf Name nodes that are NOT operator-call funcs, group tokens, kwarg values,
    or booleans -> candidate data fields (deduped, order-preserved)."""
    call_func_ids = {id(n.func) for n in _ast_calls(tree)}
    seen, out = set(), []
    for n in _ast.walk(tree):
        if isinstance(n, _ast.Name) and id(n) not in call_func_ids:
            t = n.id
            if t in ALLOWLIST or t in BLOCKLIST or t in GROUP_FIELDS or t in ("true", "false"):
                continue
            if t not in seen:
                seen.add(t); out.append(t)
    return out


def ast_arity_violations(tree) -> list[str]:
    """Operators whose POSITIONAL arg count is outside ALLOWLIST_ARITY[min,max].
    kwargs (filter=, std=) are not counted toward arity. This is the AST-only check
    the regex validator could not do."""
    bad = []
    for n in _ast_calls(tree):
        op = n.func.id
        if op in ALLOWLIST_ARITY:
            cnt = len(n.args)                  # positional only
            lo, hi = ALLOWLIST_ARITY[op]
            if not (lo <= cnt <= hi):
                bad.append(f"{op}({cnt} args, expected {lo}-{hi})")
    return bad


# two-operand ops where passing the SAME expression twice is degenerate (divide->1,
# subtract->0, corr/regression of x on x). Catches the template-generator bug
# `ts_regression(field, field, w)` that errors at sim time. (AST-only: needs structural eq.)
_SELF_DEGENERATE = {"divide", "subtract", "ts_corr", "ts_covariance", "ts_regression"}
def ast_degenerate_self_args(tree) -> list[str]:
    bad = []
    for n in _ast_calls(tree):
        if n.func.id in _SELF_DEGENERATE and len(n.args) >= 2:
            if _ast.dump(n.args[0]) == _ast.dump(n.args[1]):     # identical first two operands
                bad.append(f"{n.func.id}(X, X) — same operand twice (degenerate)")
    return bad
