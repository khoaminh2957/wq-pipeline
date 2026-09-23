"""The judge — type inference over a FASTEXPR formula against the field labels (Khoa 2026-09-07, ticked).

HARD rules (a violation refuses the formula before it is simulated):
  H1 unit      add / subtract / divide only between operands of the same UNIT (a count over a count,
               a currency over a currency); a constant is unit-free
  H2 kind      ts_delta / ts_returns / ts_av_diff / last_diff_value on a ratio, score, flag or code;
               rank / zscore / quantile / normalize / scale / group_* on a flag or code
  H3 bounded   multiply and if_else take only bounded operands: a SCORE in [0,1] (rank, quantile,
               ts_rank, ts_quantile, group_rank, sigmoid, 1 - score), a z-score, a constant, or a
               product of those
  H4 structure a VECTOR field is read only through vec_*; a quarterly / annual field passes through
               ts_backfill or group_backfill before any cross-sectional or time-series operator;
               a sparse field (coverage < 0.5) passes through a density operator (ts_backfill,
               add(x, 0, filter=true), densify, group_backfill)
  H5 role      a field whose SIGN is unstated may only stand in a sign-free role: the condition of
               if_else / trade_when, a bucket group, or inside a dispersion / abs / correlation
  H6 orient    the finished formula has a determinate orientation (the product of the signs along
               every directional path is +1, i.e. higher value = long)
SOFT score in [0, 1] (never refuses; the generator uses it as a draw weight):
  S1 cross-domain composition at L3 (two legs from different DOMAINs)
  S2 every leg reaches L2 (a SCORE) before L3
  S3 a time transform (L1) sits between the field and its score
  S4 a gate (L4) with an unstated-sign field
  S5 no wasted normalizer (rank of a rank, zscore of a rank)

`judge(formula, labels)` -> {"ok": bool, "hard": [reasons], "soft": float, "type": {...}}.
"""
from __future__ import annotations

import re

SCORE01 = {"rank", "quantile", "ts_rank", "ts_quantile", "group_rank", "sigmoid"}
ZSCORE = {"zscore", "ts_zscore", "group_zscore", "normalize", "scale", "ts_scale", "group_scale", "winsorize"}
CS_NORM = SCORE01 | ZSCORE | {"group_neutralize", "group_mean", "regression_proj", "vector_neut", "vector_proj"}
CHANGE = {"ts_delta", "ts_returns", "ts_av_diff", "last_diff_value", "ts_min_diff", "ts_min_max_diff"}
SMOOTH = {"ts_mean", "ts_sum", "ts_decay_linear", "ts_decay_exp_window", "hump", "ts_delay", "ts_product", "ts_min", "ts_max",
          "kth_element", "ts_step", "ts_target_tvr_decay"}
BACKFILL = {"ts_backfill", "group_backfill"}
DENSITY = BACKFILL | {"densify"}
DISPERSION = {"ts_std_dev", "ts_skewness", "ts_kurtosis", "ts_moment", "ts_entropy", "vec_stddev", "vec_range", "ts_min_max_cps"}
RELATE = {"ts_corr", "ts_covariance", "ts_regression", "ts_co_kurtosis", "ts_co_skewness"}
COUNTING = {"ts_count_nans", "days_from_last_change", "ts_arg_min", "ts_arg_max", "vec_count"}
VEC = {"vec_avg", "vec_sum", "vec_max", "vec_min", "vec_count", "vec_stddev", "vec_range"}
LOGIC = {"greater", "less", "greater_equal", "less_equal", "equal", "not_equal", "and", "or", "not", "is_nan"}
PASS = {"abs", "log", "sqrt", "sign", "signed_power", "power", "inverse", "reverse", "tanh", "max", "min", "densify"}
GROUPS = {"industry", "subindustry", "sector", "market", "country", "exchange", "currency"}
SIGN_FREE_KINDS = {"flag", "code", "count", "dispersion", "days", "coefficient"}
NON_RANKABLE = {"flag", "code"}
NON_DIFF = {"ratio", "score", "flag", "code"}
# A difference of two labelled quantities can name a third construct with its own literature sign.
# EX-ANTE definitions, not data: accruals = income - cash flow (Sloan 1996, sign -).
DIFF_DOMAINS = {("profitability", "cashflow"): ("accruals", -1)}

# ------------------------------------------------------------------------------------ parser
_TOK = re.compile(r"\s*(?:(\d+\.\d*|\.\d+|\d+)|([A-Za-z_][A-Za-z0-9_]*)|(>=|<=|==|!=|[-+*/(),=<>])|(\"[^\"]*\"))")


class Node:
    __slots__ = ("op", "args", "kw", "name", "value")

    def __init__(self, op=None, args=None, kw=None, name=None, value=None):
        self.op, self.args, self.kw, self.name, self.value = op, args or [], kw or {}, name, value

    def __repr__(self):
        if self.op:
            return "%s(%s)" % (self.op, ", ".join(map(repr, self.args)))
        return self.name if self.name is not None else str(self.value)


def tokens(src: str) -> list:
    out, pos = [], 0
    src = src.strip()
    while pos < len(src):
        m = _TOK.match(src, pos)
        if not m or m.end() == pos:
            raise ValueError("cannot tokenise at %d: %r" % (pos, src[pos:pos + 20]))
        num, ident, sym, s = m.groups()
        if num is not None:
            out.append(("num", float(num)))
        elif ident is not None:
            out.append(("id", ident))
        elif sym is not None:
            out.append(("sym", sym))
        else:
            out.append(("str", s.strip('"')))
        pos = m.end()
    return out


class Parser:
    def __init__(self, src):
        self.t, self.i = tokens(src), 0

    def peek(self, k=0):
        return self.t[self.i + k] if self.i + k < len(self.t) else (None, None)

    def take(self, kind=None, val=None):
        tk = self.peek()
        if tk[0] is None or (kind and tk[0] != kind) or (val and tk[1] != val):
            raise ValueError("expected %s %s at token %d, got %r" % (kind, val, self.i, tk))
        self.i += 1
        return tk

    def parse(self):
        n = self.expr()
        if self.peek()[0] is not None:
            raise ValueError("trailing tokens at %d: %r" % (self.i, self.peek()))
        return n

    def expr(self):                     # comparison
        n = self.sum()
        while self.peek() == ("sym", ">") or self.peek() == ("sym", "<") or self.peek()[1] in (">=", "<=", "==", "!="):
            op = {">": "greater", "<": "less", ">=": "greater_equal", "<=": "less_equal", "==": "equal", "!=": "not_equal"}[self.take()[1]]
            n = Node(op, [n, self.sum()])
        return n

    def sum(self):
        n = self.term()
        while self.peek()[1] in ("+", "-") and self.peek()[0] == "sym":
            op = "add" if self.take()[1] == "+" else "subtract"
            n = Node(op, [n, self.term()])
        return n

    def term(self):
        n = self.unary()
        while self.peek()[1] in ("*", "/") and self.peek()[0] == "sym":
            op = "multiply" if self.take()[1] == "*" else "divide"
            n = Node(op, [n, self.unary()])
        return n

    def unary(self):
        if self.peek() == ("sym", "-"):
            self.take()
            return Node("reverse", [self.unary()])
        if self.peek() == ("sym", "+"):
            self.take()
            return self.unary()
        return self.atom()

    def atom(self):
        kind, val = self.peek()
        if kind == "num":
            self.take()
            return Node(value=val)
        if kind == "str":
            self.take()
            return Node(value=val)
        if kind == "sym" and val == "(":
            self.take()
            n = self.expr()
            self.take("sym", ")")
            return n
        if kind == "id":
            self.take()
            if self.peek() == ("sym", "("):
                self.take()
                args, kw = [], {}
                if self.peek() != ("sym", ")"):
                    while True:
                        if self.peek()[0] == "id" and self.peek(1) == ("sym", "="):
                            k = self.take()[1]
                            self.take()
                            kw[k] = self.expr()
                        else:
                            args.append(self.expr())
                        if self.peek() == ("sym", ","):
                            self.take()
                            continue
                        break
                self.take("sym", ")")
                return Node(val, args, kw)
            if val in ("true", "false"):
                return Node(value=1.0 if val == "true" else 0.0)
            return Node(name=val)
        raise ValueError("unexpected token %r" % ((kind, val),))


def parse(src: str) -> Node:
    return Parser(src).parse()


# ------------------------------------------------------------------------------------ types
def _leaf(name: str, labels: dict, region: str | None = None) -> dict:
    if name in GROUPS:
        return {"cls": "group", "kind": "group", "unit": "group", "sign": 0, "bounded": False, "domains": set(), "layer": 0}
    lab = labels.get(name)
    if lab is not None and region and lab.get("by_region", {}).get(region):
        lab = dict(lab, **lab["by_region"][region])       # structure / sparsity as they hold in this region
    if lab is None:
        return {"cls": "unknown", "kind": "level", "unit": "unitless", "sign": 0, "bounded": False, "domains": {"?"},
                "layer": 0, "unknown_field": name}
    return {"cls": "field", "kind": lab["kind"], "unit": lab["unit"], "sign": {"+": 1, "-": -1}.get(lab["sign"], 0),
            "bounded": lab["kind"] in ("score",) and lab["unit"] == "score" and False,   # a raw score is not known to be in [0,1]
            "domains": {lab["domain"]}, "layer": 0, "time": lab["time"], "sparsity": lab["sparsity"],
            "structure": lab["structure"], "field": name, "needs_backfill": lab["time"] in ("quarterly", "annual"),
            "needs_density": lab["sparsity"] == "sparse", "is_vector": lab["structure"] == "VECTOR",
            "vec_reducers": lab.get("vec_reducers"), "vec_after": lab.get("vec_after")}


def _const(v) -> dict:
    return {"cls": "const", "kind": "const", "unit": "*", "sign": 0, "bounded": True, "domains": set(), "layer": 0, "value": v}


def _merge_domains(*ts):
    out = set()
    for t in ts:
        out |= t.get("domains", set())
    return out


def _carry(t, **over) -> dict:
    n = dict(t)
    n.pop("field", None)
    n["cls"] = "expr"
    n.update(over)
    return n


class Judge:
    def __init__(self, labels: dict, region: str | None = None, structural: bool = False):
        """`structural`: only the label-sign-independent rules H1, H2, H4-vector, H4-density (Khoa's
        tick 2026-09-07 22:10 for the pre-sim gate on the current arm). The quarterly-backfill rule
        is OFF in both modes' gate use: measured 2026-09-07 on 9,896 simulated formulas it refused
        3,964 including 2 of the 17 platform passes (vRk095rv, qMWbdlmv) — refuted. Unknown fields
        do not refuse in structural mode (a construction from an unlabelled catalogue passes)."""
        self.labels, self.region, self.structural = labels, region, structural
        self.hard, self.notes = [], []
        self.legs = []              # (domains, reached_score, had_time_transform)
        self.has_gate = False
        self.wasted_norm = 0

    def fail(self, msg):
        self.hard.append(msg)

    def infer(self, n: Node, role: str = "dir", norm_above: bool = False, backfilled: bool = False, densified: bool = False) -> dict:
        if n.op is None:
            if n.name is not None:
                t = _leaf(n.name, self.labels, self.region)
                if t["cls"] == "unknown" and not self.structural:
                    self.fail("unknown field %s" % n.name)
                if t["cls"] == "field":
                    if t["is_vector"] and role != "vec":
                        self.fail("H4 VECTOR field %s used outside vec_*" % n.name)
                    if t["needs_backfill"] and not backfilled and role != "vec" and not self.structural:
                        self.fail("H4 %s is %s and has no ts_backfill above it" % (n.name, t["time"]))
                    if t["needs_density"] and not densified and not backfilled:
                        self.fail("H4 %s is sparse (coverage < 0.5) and has no density operator above it" % n.name)
                    if not self.structural:
                        if role == "dir" and t["sign"] == 0 and t["kind"] not in SIGN_FREE_KINDS:
                            self.fail("H5 %s has no stated sign but stands in a directional role" % n.name)
                        if role == "dir" and t["kind"] in SIGN_FREE_KINDS and t["kind"] not in ("count",):
                            self.fail("H5 %s is a %s (sign-free kind) in a directional role" % (n.name, t["kind"]))
                return t
            return _const(n.value)
        op = n.op
        args = n.args
        # ---- roles for sub-expressions
        if op == "if_else":
            if len(args) != 3:
                self.fail("if_else needs 3 arguments")
                return _const(0)
            cond = self.infer(args[0], "cond", norm_above, backfilled, densified)
            a = self.infer(args[1], role, norm_above, backfilled, densified)
            b = self.infer(args[2], role, norm_above, backfilled, densified)
            if cond["kind"] != "flag":
                self.fail("H3 if_else condition is not a logical expression")
            for x, nm in ((a, "then"), (b, "else")):
                if not x["bounded"]:
                    self.fail("H3 if_else %s-branch is not bounded (score / zscore / constant)" % nm)
            self.has_gate = True
            out = _carry(a, domains=_merge_domains(a, b), layer=max(a["layer"], b["layer"], 3), bounded=a["bounded"] and b["bounded"])
            out["sign"] = a["sign"] if b["cls"] == "const" else (a["sign"] if a["sign"] == b["sign"] else 0)
            return out
        if op == "trade_when":
            cond = self.infer(args[0], "cond", norm_above, backfilled, densified)
            a = self.infer(args[1], role, norm_above, backfilled, densified)
            self.infer(args[2], "cond", norm_above, backfilled, densified) if len(args) > 2 else None
            self.has_gate = True
            return _carry(a, layer=max(a["layer"], 4))
        if op == "bucket":
            self.infer(args[0], "cond", norm_above, backfilled, densified)
            return {"cls": "group", "kind": "group", "unit": "group", "sign": 0, "bounded": False, "domains": set(), "layer": 0}
        if op in LOGIC:
            ts = [self.infer(a, "cond", norm_above, backfilled, densified) for a in args]
            if op in ("greater", "less", "greater_equal", "less_equal") and len(ts) == 2:
                u = {t["unit"] for t in ts if t["cls"] != "const"}
                if len(u) > 1:
                    self.fail("H1 comparison across units %s" % sorted(u))
            return {"cls": "expr", "kind": "flag", "unit": "bool", "sign": 0, "bounded": True, "domains": _merge_domains(*ts), "layer": 4}
        if op in DISPERSION or op in RELATE:
            ts = [self.infer(a, "cond", norm_above, backfilled, densified) for a in args if a.op is not None or a.name is not None]
            kind = "dispersion" if op in DISPERSION else "coefficient"
            return {"cls": "expr", "kind": kind, "unit": "unitless", "sign": 0, "bounded": False, "domains": _merge_domains(*ts), "layer": 1}
        if op in COUNTING:
            ts = [self.infer(a, "cond" if op != "vec_count" else "vec", norm_above, backfilled, densified) for a in args if a.op is not None or a.name is not None]
            return {"cls": "expr", "kind": "count", "unit": "count", "sign": 0, "bounded": False, "domains": _merge_domains(*ts), "layer": 1}
        if op in VEC:
            t = self.infer(args[0], "vec", norm_above, backfilled, densified)
            if t.get("cls") == "field" and not t.get("is_vector"):
                self.fail("H4 %s applied to a MATRIX field" % op)
            if t.get("cls") != "field":
                self.fail("H4 %s takes a raw VECTOR field" % op)
            if t.get("vec_reducers") and op not in t["vec_reducers"] and op not in ("vec_stddev", "vec_range"):
                self.fail("H4 %s is not a meaningful reducer for %s (%s allows %s)" % (op, args[0], t.get("vec_role", "?"), "/".join(t["vec_reducers"])))
            kind = "dispersion" if op in ("vec_stddev", "vec_range") else (t.get("vec_after") or {}).get(op) or ("count" if op == "vec_count" else t["kind"])
            out = _carry(t, kind=kind, layer=1, is_vector=False)
            if kind == "count":
                out["unit"] = "count"
            if kind in ("dispersion", "count"):
                out["sign"] = 0
            if role == "dir" and out["sign"] == 0 and kind not in SIGN_FREE_KINDS and not self.structural:
                self.fail("H5 %s(%s) has no stated sign in a directional role" % (op, args[0]))
            return out
        if op in BACKFILL:
            t = self.infer(args[0], role, norm_above, True, True)
            return _carry(t, layer=max(t["layer"], 1))
        if op == "add" and "filter" in n.kw:
            ts = [self.infer(a, role, norm_above, backfilled, True) for a in args]
            return self._arith("add", ts)
        if op in SMOOTH or op in PASS:
            ts = [self.infer(a, role, norm_above, backfilled, densified) for a in args]
            t = ts[0]
            if op == "log" and t.get("directional", False):
                self.notes.append("log of a signed quantity")
            out = _carry(t, layer=max(t["layer"], 1))
            if op == "reverse":
                out["sign"] = -t["sign"]
            if op == "abs":
                out["sign"] = 0
            if op in ("sigmoid",):
                out["bounded"] = True
            if op in ("max", "min") and len(ts) == 2 and ts[1]["cls"] == "const":
                pass
            return out
        if op in CHANGE:
            t = self.infer(args[0], role, norm_above, backfilled, densified)
            if t["kind"] in NON_DIFF:
                self.fail("H2 %s on a %s" % (op, t["kind"]))
            out = _carry(t, kind="return", unit="return" if op == "ts_returns" else t["unit"], layer=max(t["layer"], 1), bounded=False)
            return out
        if op in CS_NORM or op in ("ts_rank", "ts_zscore", "ts_quantile", "ts_scale"):
            t = self.infer(args[0], role, True, backfilled, densified)
            if t["kind"] in NON_RANKABLE:
                self.fail("H2 %s on a %s" % (op, t["kind"]))
            if t["kind"] == "score" and t.get("bounded"):
                self.wasted_norm += 1          # rank of a rank: order-only consumption twice (logic_operators.md law 1)
            for g in args[1:]:
                gt = self.infer(g, "cond", norm_above, backfilled, densified)
                if op.startswith("group_") and gt["kind"] != "group":
                    self.fail("%s group argument is not a group" % op)
            bounded = op in SCORE01 or op in ZSCORE
            out = _carry(t, kind="score", unit="score", bounded=bounded, layer=max(t["layer"], 2))
            if op in ("group_neutralize", "group_mean", "regression_proj", "vector_neut", "vector_proj", "winsorize"):
                out["kind"], out["unit"], out["bounded"] = t["kind"], t["unit"], t.get("bounded", False)
            return out
        if op == "divide" and len(args) == 2:
            # THE DENOMINATOR IS A SCALE, NOT A LEG: dividing income by equity does not make equity
            # a directional bet, so its unstated sign is allowed there (H5 does not apply); H1 still
            # requires the same unit, and a score / return / flag cannot serve as a scale.
            num = self.infer(args[0], role, norm_above, backfilled, densified)
            den = self.infer(args[1], "scale", norm_above, backfilled, densified)
            if den["cls"] != "const" and den["kind"] not in ("level", "count", "ratio", "dispersion"):
                self.fail("H1 denominator is a %s, not a scale" % den["kind"])
            out = self._arith("divide", [num, den])
            out["domains"] = set(num.get("domains", set()))       # a scale contributes no domain
            return out
        if op in ("multiply", "add", "subtract", "power"):
            ts = [self.infer(a, role, norm_above, backfilled, densified) for a in args]
            return self._arith(op, ts)
        self.fail("unknown operator %s" % op)
        return _const(0)

    def _arith(self, op, ts) -> dict:
        real = [t for t in ts if t["cls"] != "const"]
        doms = _merge_domains(*ts)
        if op in ("add", "subtract"):
            units = {t["unit"] for t in real}
            if len(units) > 1:
                self.fail("H1 %s across units %s" % (op, sorted(units)))
            t = real[0] if real else ts[0]
            # 1 - score keeps a score bounded and flips its orientation
            if op == "subtract" and ts[0]["cls"] == "const" and ts[0]["value"] == 1 and len(ts) == 2 and ts[1].get("bounded"):
                return _carry(ts[1], sign=-ts[1]["sign"], domains=doms)
            signs = {t["sign"] for t in real}
            sign = signs.pop() if len(signs) == 1 else 0
            if op == "subtract" and len(real) == 2:
                sign = real[0]["sign"] if real[0]["sign"] == -real[1]["sign"] and real[0]["sign"] != 0 else 0
                key = (next(iter(real[0]["domains"]), None), next(iter(real[1]["domains"]), None))
                if key in DIFF_DOMAINS and len(real[0]["domains"]) == 1 and len(real[1]["domains"]) == 1:
                    named, sign = DIFF_DOMAINS[key]
                    doms = {named}
            return _carry(t, sign=sign, bounded=all(t.get("bounded") for t in ts) and op == "add" and len(real) == 1, domains=doms,
                          layer=max(t["layer"] for t in ts))
        if op == "divide":
            if len(real) == 2 and real[0]["unit"] != real[1]["unit"]:
                self.fail("H1 divide %s by %s" % (real[0]["unit"], real[1]["unit"]))
            t = real[0] if real else ts[0]
            sign = t["sign"] if len(real) == 1 else (real[0]["sign"] if real[1]["sign"] == 0 else 0)
            return _carry(t, kind="ratio", unit="ratio", sign=sign, bounded=False, domains=doms, layer=max(x["layer"] for x in ts))
        if op == "power":
            return _carry(ts[0], bounded=False, domains=doms)
        # multiply
        for t in real:
            if not t.get("bounded"):
                self.fail("H3 multiply operand is not bounded (score / zscore / constant): kind=%s" % t["kind"])
        sign = 1
        for t in real:
            sign *= t["sign"]
        if len(real) >= 2:
            self.legs.append([t["domains"] for t in real])
        return {"cls": "expr", "kind": "score", "unit": "score", "sign": sign, "bounded": all(t.get("bounded") for t in ts),
                "domains": doms, "layer": 3 if len(real) >= 2 else max(t["layer"] for t in ts)}


def judge(formula: str, labels: dict, region: str | None = None, structural: bool = False) -> dict:
    """`region` is "USA/d1"-style; with it, a field's structure and sparsity are read for that region.
    `structural=True` applies only H1 / H2 / H4-vector / H4-density (the pre-sim gate)."""
    try:
        tree = parse(formula)
    except ValueError as exc:
        return {"ok": False, "hard": ["parse: %s" % exc], "soft": 0.0, "type": None}
    j = Judge(labels, region, structural)
    t = j.infer(tree)
    if t["sign"] != 1 and not j.hard and not structural:
        j.fail("H6 orientation is %s, not +1 (higher = long)" % ("unknown" if t["sign"] == 0 else "negative"))
    soft = 0.0
    domains = t.get("domains", set())
    cross = any(len(set.union(*legs)) >= 2 and all(legs) for legs in j.legs) if j.legs else False
    soft += 0.35 if cross else 0.0
    soft += 0.25 if t.get("layer", 0) >= 3 and t.get("bounded") else 0.0
    soft += 0.15 if t.get("layer", 0) >= 1 else 0.0
    soft += 0.15 if j.has_gate else 0.0
    soft += 0.10 if j.wasted_norm == 0 else 0.0
    return {"ok": not j.hard, "hard": j.hard, "soft": round(soft, 2),
            "type": {k: (sorted(v) if isinstance(v, set) else v) for k, v in t.items() if k in ("kind", "unit", "sign", "bounded", "domains", "layer")}}
