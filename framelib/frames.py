"""Frame text: the normal form, the slots, and every fact derived from the text alone.

A FRAME is a FASTEXPR formula in which some data fields are SLOTS, written $1..$n. The rest is fixed
text: operators, numbers, strings, the six group tokens, CONDITION fields and PINNED fields.

  condition field  a named field whose every occurrence sits under argument 0 of if_else / trade_when
                   (FRAME SPEC v1, ruling R9; trade_when's argument 2 is NOT a condition under v1)
  pinned field     any other named field written into the frame text (a fixed leg, e.g. a scale)
  slot             $k; a slot may not occur only in condition positions (a condition field is pinned
                   text under v1, so such a slot could never re-frame to the same key)

NORMAL FORM = FRAME SPEC v1 (frames/canonical/RECONCILIATION.md), applied to forge.typed's own tree:
functional form, no whitespace outside string literals, `a+b` -> add(a,b), `-x` -> reverse(x) (R1),
numbers / strings / true / false written exactly as in the source (R2, R4), a bare identifier as a
keyword value is an option token (R3), slots renumbered $1..$n by first appearance in pre-order.

CANONICAL KEY = the spec's frame_key: every non-condition field, slot or pinned, becomes a numbered
slot. A frame without pinned fields has text == canonical key. With pinned fields, its canonical rows
are those whose fill holds each pinned field at its canonical position (`Normal.pinned`).
"""
from __future__ import annotations

import re

from forge import typed as TY

GROUP_TOKENS = frozenset({"sector", "industry", "subindustry", "market", "country", "exchange"})   # R11 (six)
COND_OPS = frozenset({"if_else", "trade_when"})
VECTOR_OPS = frozenset({"vec_min", "vec_count", "vec_sum", "vec_max", "vec_avg", "vec_stddev", "vec_range"})

# EX-ANTE, transcribed from fetched/rc/operators.json definitions (tests/test_frames.py re-derives both
# tables from that file and fails on any difference). Operators absent from operators.json have no entry.
WINDOW_ARG = {   # op -> positional index of the look-back `d`
    "ts_corr": 2, "ts_zscore": 1, "ts_product": 1, "ts_std_dev": 1, "ts_backfill": 1, "last_diff_value": 1,
    "ts_scale": 1, "ts_entropy": 1, "ts_sum": 1, "ts_av_diff": 1, "ts_mean": 1, "ts_min_max_diff": 1,
    "ts_arg_max": 1, "ts_min_max_cps": 1, "ts_rank": 1, "ts_delay": 1, "ts_quantile": 1, "ts_count_nans": 1,
    "ts_covariance": 2, "ts_min_diff": 1, "ts_decay_linear": 1, "ts_arg_min": 1, "ts_regression": 2,
    "ts_skewness": 1, "kth_element": 1, "ts_delta": 1, "group_backfill": 2,
}
GROUP_ARGS = {   # op -> positional indices that take a group
    "group_mean": (2,), "group_rank": (1,), "group_extra": (2,), "group_backfill": (1,), "group_scale": (1,),
    "group_zscore": (1,), "group_neutralize": (1,), "group_cartesian_product": (0, 1),
}

_STR = re.compile(r'"[^"]*"')
_SLOT = re.compile(r"\$(\d+)")
_PH = "__slot%d__"
_PH_RE = re.compile(r"^__slot(\d+)__$")


class FrameError(ValueError):
    pass


def _outside_strings(src: str, fn) -> str:
    out, pos = [], 0
    for m in _STR.finditer(src):
        out.append(fn(src[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(fn(src[pos:]))
    return "".join(out)


def substitute(text: str, fields) -> str:
    """Put fields[k-1] in place of every $k (outside string literals)."""
    fields = list(fields)

    def one(m):
        k = int(m.group(1))
        if not 1 <= k <= len(fields):
            raise FrameError("$%d has no field (fill has %d)" % (k, len(fields)))
        return str(fields[k - 1])
    return _outside_strings(text, lambda s: _SLOT.sub(one, s))


def _literals(src: str) -> list:
    toks, pos, s = [], 0, src.strip()
    while pos < len(s):
        m = TY._TOK.match(s, pos)
        if not m or m.end() == pos:
            raise FrameError("cannot tokenise at %d: %r" % (pos, s[pos:pos + 20]))
        toks.append(m.groups())
        pos = m.end()
    out = []
    for i, (num, ident, _sym, st) in enumerate(toks):
        nxt = toks[i + 1] if i + 1 < len(toks) else (None, None, None, None)
        if num is not None:
            out.append(("num", num))
        elif st is not None:
            out.append(("str", st))
        elif ident in ("true", "false") and nxt[2] not in ("(", "="):
            out.append(("bool", ident))
    return out


def _is_option(v) -> bool:
    return v.op is None and v.name is not None


class Normal:
    """A parsed frame. Attributes (all derived from the text):
    text, key, shape            normal text, canonical key (spec frame_key), key with numbers as '#'
    slots                       [{"slot": "$k", "context": MATRIX|VECTOR|GROUP, "positions": [[op, arg], ...]}]
    pinned                      {canonical index (int): field}
    slot_key_index              [canonical index of $1, of $2, ...]
    cond_fields, groups         in first-appearance order
    windows                     [[op, number], ...] in pre-order
    operators                   sorted distinct operators
    tree, lit                   typed's tree and {id(value leaf): (kind, text)}
    """

    def __init__(self, src: str):
        parse_src = _outside_strings(src, lambda s: _SLOT.sub(lambda m: _PH % int(m.group(1)), s))
        try:
            self.tree = TY.parse(parse_src)
        except ValueError as exc:
            raise FrameError("parse: %s" % exc) from None
        lits = _literals(parse_src)
        self.lit = {}
        self._bind(self.tree, lits, [0])
        if len(self.lit) != len(lits):
            raise FrameError("literal count %d != %d" % (len(self.lit), len(lits)))
        occ, order, ctx = {}, [], {}
        self._walk(self.tree, False, None, occ, order, ctx)
        self.cond_fields = [f for f in order if all(occ[f]) and not _PH_RE.match(f)]
        phs = [f for f in order if _PH_RE.match(f)]
        for f in phs:
            if all(occ[f]):
                raise FrameError("slot $%s occurs only in condition positions; pin the condition field instead"
                                 % _PH_RE.match(f).group(1))
        noncond = [f for f in order if not all(occ[f])]
        self._slot_of = {f: "$%d" % (i + 1) for i, f in enumerate(phs)}
        key_of = {f: "$%d" % (i + 1) for i, f in enumerate(noncond)}
        self.pinned = {i + 1: f for i, f in enumerate(noncond) if not _PH_RE.match(f)}
        self.slot_key_index = [noncond.index(f) + 1 for f in phs]
        self.slots = []
        for f in phs:
            kinds = {c for c, _ in ctx[f]}
            if len(kinds) > 1:
                raise FrameError("slot %s is used in two structural contexts %s" % (self._slot_of[f], sorted(kinds)))
            self.slots.append({"slot": self._slot_of[f], "context": kinds.pop(), "positions": [list(p) for _, p in ctx[f]]})
        self.text = self._render(self.tree, lambda f: self._slot_of.get(f, f), False)
        self.key = self._render(self.tree, lambda f: key_of.get(f, f), False)
        self.shape = self._render(self.tree, lambda f: key_of.get(f, f), True)
        self.groups, self.windows, ops = [], [], set()
        self._facts(self.tree, ops)
        self.operators = sorted(ops)

    # ---- literal recovery: the source's literal tokens, matched to typed's value leaves in pre-order
    def _bind(self, n, lits, k):
        if n.op is not None:
            for a in n.args:
                self._bind(a, lits, k)
            for v in n.kw.values():
                self._bind(v, lits, k)
            return
        if n.name is not None:
            return
        if k[0] >= len(lits):
            raise FrameError("more value leaves than literal tokens")
        kind, text = lits[k[0]]
        v = n.value
        ok = ((kind == "num" and isinstance(v, float) and float(text) == v)
              or (kind == "str" and isinstance(v, str) and text[1:-1] == v)
              or (kind == "bool" and v == (1.0 if text == "true" else 0.0)))
        if not ok:
            raise FrameError("literal mismatch %r vs %r" % ((kind, text), v))
        self.lit[id(n)] = (kind, text)
        k[0] += 1

    def _walk(self, n, in_cond, parent, occ, order, ctx):
        if n.op is not None:
            for i, a in enumerate(n.args):
                self._walk(a, in_cond or (n.op in COND_OPS and i == 0), (n.op, i), occ, order, ctx)
            for kname, v in n.kw.items():
                if not _is_option(v):
                    self._walk(v, in_cond, (n.op, kname), occ, order, ctx)
            return
        if n.name is None or n.name in GROUP_TOKENS:
            return
        if n.name not in occ:
            order.append(n.name)
            occ[n.name] = []
            ctx[n.name] = []
        occ[n.name].append(in_cond)
        op, pos = parent if parent else (None, None)
        c = ("VECTOR" if op in VECTOR_OPS and pos == 0 else
             "GROUP" if isinstance(pos, int) and pos in GROUP_ARGS.get(op, ()) else "MATRIX")
        ctx[n.name].append((c, (op, pos)))

    def _render(self, n, name, shape):
        if n.op is not None:
            parts = [self._render(a, name, shape) for a in n.args]
            for k, v in n.kw.items():
                parts.append("%s=%s" % (k, v.name if _is_option(v) else self._render(v, name, shape)))
            return "%s(%s)" % (n.op, ",".join(parts))
        if n.name is not None:
            return n.name if n.name in GROUP_TOKENS else name(n.name)
        kind, text = self.lit[id(n)]
        return "#" if (shape and kind == "num") else text

    def _facts(self, n, ops):
        if n.op is None:
            if n.name in GROUP_TOKENS and n.name not in self.groups:
                self.groups.append(n.name)
            return
        ops.add(n.op)
        i = WINDOW_ARG.get(n.op)
        if i is not None and i < len(n.args):
            a = n.args[i]
            if a.op is None and a.name is None and self.lit[id(a)][0] == "num":
                v = float(self.lit[id(a)][1])
                self.windows.append([n.op, int(v) if v.is_integer() else v])
        for a in n.args:
            self._facts(a, ops)
        for v in n.kw.values():
            if not _is_option(v):
                self._facts(v, ops)

    # ---- helpers on a parsed frame
    def is_slot(self, name) -> bool:
        return name in self._slot_of

    def renumbered(self, k: int) -> int | None:
        """The normal-form number of the slot the SOURCE text wrote as $k (None if it wrote no $k)."""
        s = self._slot_of.get(_PH % k)
        return int(s[1:]) if s else None

    def fill(self, fields) -> str:
        """The formula with fields[k-1] in slot $k."""
        if len(fields) != len(self.slots):
            raise FrameError("frame has %d slots, fill has %d" % (len(self.slots), len(fields)))
        return substitute(self.text, fields)

    def key_fill(self, fields) -> list:
        """The canonical-key fill (the spec's `fill` list) of the formula self.fill(fields)."""
        out = [None] * (len(self.pinned) + len(self.slots))
        for i, f in self.pinned.items():
            out[i - 1] = f
        for k, f in enumerate(fields):
            out[self.slot_key_index[k] - 1] = f
        return out


def normalize(text: str) -> Normal:
    """Parse a frame text; raises FrameError. A frame needs at least one slot."""
    n = Normal(text)
    if not n.slots:
        raise FrameError("no slot ($1..$n) in %r" % text[:80])
    return n


def frame_formula(formula: str) -> tuple:
    """(frame_key, fill, cond_fields) of a simulated formula under FRAME SPEC v1."""
    n = Normal(formula)
    fill = [n.pinned[i] for i in sorted(n.pinned)]
    return n.key, fill, list(n.cond_fields)
