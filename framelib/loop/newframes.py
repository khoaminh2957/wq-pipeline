"""framelib.loop.newframes -- the day's cohort of NEW candidate frames (docs/frames/00_decisions.md F8).

F8: 25 new frames a day, screened on day t and replicated on fresh fields on day t+1 (doc 13 Q7 A). This
module only MAKES the candidates and files them in the library with status candidate; the planner
(framelib.loop.plan) screens them and the evidence ledger scores them. Nothing here simulates, POSTs or
talks to the network (RULE 1).

    python3 -B -m framelib.loop.newframes --n 25 [--seed S] [--day YYYY-MM-DD] [--library DIR]
        [--datasets-ok state/frames/datasets_ok.json] [--history state/frames/history_usa_d1_top3000.jsonl]
        [--canonical state/frames/canonical/frames_summary.jsonl] [--dropped-ids DIR/selection.json]
        [--dropped-lib DIR] [--now ISO] [--dry-run]

SOURCES, in this order (doc 13 section 7.2 and Q7 A: "the 34 dropped mined frames go first"):
  mined-dropped  the mined frames the curator left out of the first 100 (doc 11 section 2.2): the ids under
                 "dropped_mined" in the curator's selection.json, each entry as the curator's full build
                 (lib134) wrote it, in id order. Both are kept in this package, byte for byte, under
                 framelib/loop/dropped_mined/ (selection.json and frames/<id>.json), so they ship with the code.
                 provenance.origin "mined-dropped"; its canonical evidence stays.
  mutation       a library frame (not retired, not from today's cohort) changed by ONE operator below.
                 provenance: origin "mutation", parent (the first parent), parents (all), mutation (what was
                 applied), cohort_day. The kinds take turns in MUTATIONS order. Within a kind the parents are
                 in a seeded shuffle and each parent's candidates in a seeded shuffle, drawn lazily (DESIGN
                 CHOICE: the combine pairs grow as the square of the library, about 360,000 pairs at 850
                 frames, so nothing enumerates them); a parent gives at most one new frame per call.

MUTATIONS. Each rule is a DESIGN CHOICE of this module. Statements about operators are EX-ANTE (their
definitions in fetched/rc/operators.json and forge/typed.py). Nothing here claims a mutation does better;
that is what the screen measures, MECHANISM: UNKNOWN until an experiment separates it.
  window     one window site moves to the nearest rung of WINDOW_LADDER at least WINDOW_STEP x away, down or
             up. A site is every occurrence of one identical subtree, changed together (a spread of a
             quantity against its own neutralised copy keeps one window on both sides). ts_backfill /
             group_backfill keep theirs (d bounds how far back a NaN is filled) and so does ts_delay (d is a lag).
  group      one group-token site becomes another of GICS_GROUPS.
  opswap     one operator site becomes another operator of its SWAP_GROUPS set: the same positional arguments
             and the same taxonomy role (framelib.taxonomy's economic function; for the operators it files
             under LEVEL, forge.typed's smoothing (SMOOTH) / normalising (SCORE01 | ZSCORE) split). Sites with
             keyword arguments or inside any condition are left alone.
  condition  replace: the slot-free condition of an if_else / trade_when (a trade_when only when its exit
             holds no field) becomes another PRESET. add: an unconditioned frame X becomes if_else(P, X, c),
             c = 0.5 when X's root is a [0, 1] score (forge.typed SCORE01), else 0.
             PRESETS are the slot-free conditions written in library frames that compare ONE data-bearing side
             with a constant -- the gate that forge.meaning.legs_of splits into two legs for D39's G6, the gate
             F9's automatic submit reads -- and whose every field is in today's catalogue.
  combine    multiply(a, b): a a leg of frame A, b a leg of another frame B, A the lower id of the two (so a
             product and its commuted copy are never both made). A frame's legs are the operands of a root
             multiply that carry data, split again when one is itself such a multiply (forge.meaning
             legs_of's multiply production); any other frame is one leg. Legs of one structure are not paired.
  Window, group and opswap sites inside a slot-free condition are left alone: a condition changes whole.

SLOT ROLES FOLLOW THEIR SLOT (DESIGN CHOICE). Each slot of a new frame carries the role its parent's slot has
in OWN-ROLE mode, as framelib.experiments.round1.arm_entries defines it and the planner fills it: a mined
(or mined-dropped) parent with a dataset per slot in its canonical history -> "datasets" = those datasets; any
other parent -> its declared role and constraints. So a mutation's own-role fills stay in the parent's own
role pools and its other-dataset fills leave them, as the parent's do; without this, a mutation of a mined
frame would declare nothing and both of its fill modes would draw any field the gate admits. A unit_eq value
is renumbered with its slot (phase-A audit S8) and dropped when its partner slot is not in the new frame.
Settings stay {"source": "none"}: F10's per-frame profile has no schema source for "copied from the parent".

EVERY NEW FRAME (a failure is counted by reason in the report):
  1. parses (frames.normalize) and passes schema.validate;
  2. has a NEW canonical key: no library frame's, none taken earlier in the call, and -- for a mutation --
     none in the canonical corpus (a mined-dropped frame is in the corpus by definition);
  3. fills >= MIN_FILLS times in USA/d1 through framelib.filler (structurally_ok on every formula, and the
     formula re-frames to the frame), on the field library pruned to today's datasets by
     framelib.loop.availability (= round1.restrict), in own-role mode, none a formula of the frame's canonical
     history -- and the MIN_FILLS fills use pairwise DISJOINT fields: the planner never reuses a field with a
     frame (framelib.loop.evidence.used_fields), so fills that share a field cannot all be dispatched;
  4. carries provenance (origin, parents, mutation, cohort_day) and its taxonomy (`characteristics`).
BOUNDED EFFORT (DESIGN CHOICES; the driver runs this step under `timeout 1800`, and a step that times out is
retried every round). After a candidate falls short of MIN_FILLS, the rest of its group -- the same parent's
candidates of that kind, or the same pair's for combine -- is skipped for this call: they keep the parent's
slots and role pools (EX-ANTE reading of forge.typed's H1-H4, which read a field's unit, kind and structure: a
window number, a group token or a slot-free condition does not change which fields a slot admits; an operator
swap can, so a swap that would have filled may be skipped). Seen on 2026-09-25 (POST-HOC, the real library,
R1B's 293 datasets): in 15 of the 34 dropped frames two slots draw, in own-role mode, from one pool of the same
4 us_short_sale fields, so no more than 2 fills can be disjoint (EX-ANTE arithmetic: 2 distinct fields per
fill), and a library frame of that form passes the limit to each such mutation; without the skip, a dry run for
n = 80 had spent 196 fill checks when it was stopped at 100 s. And
one call makes at most CHECKS_PER_FRAME x (frames still wanted) fill checks, then stops and files what it has.
FAIL-CLOSED: a missing input (today's datasets, the canonical keys, the history, the dropped list) or an
invalid library writes nothing and exits 2. Idempotent per ET day: entries already filed for the day count
toward --n, and today's cohort is never a parent, so a re-run continues the same sequence.
"""
from __future__ import annotations

import argparse
import collections
import copy
import datetime as DT
import json
import pathlib
import random
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(ROOT / "tools"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from forge import meaning as MN                    # noqa: E402  the gate form G6 reads (_COMPARE)
from forge import typed as TY                      # noqa: E402
from framelib import evidence as EV                # noqa: E402
from framelib import filler as FI                  # noqa: E402
from framelib import frames as FR                  # noqa: E402
from framelib import schema as SC                  # noqa: E402
from framelib import store as ST                   # noqa: E402
from framelib.experiments import round1 as R1      # noqa: E402
from framelib.loop import availability as AV       # noqa: E402

BUILT_BY = "framelib.loop.newframes v2"
CELL = R1.CELL
MIN_FILLS = 3
FILL_N0, FILL_NMAX = 8, 64          # filler draws per check: doubled until MIN_FILLS disjoint fills or the cap
CHECKS_PER_FRAME = 12               # the call's fill-check budget = this x the frames still wanted
HISTORY = ROOT / "state/frames/history_usa_d1_top3000.jsonl"
CANONICAL = ROOT / "state/frames/canonical/frames_summary.jsonl"
DROPPED_LIB = pathlib.Path(__file__).resolve().parent / "dropped_mined"
DROPPED_IDS = DROPPED_LIB / "selection.json"
MUTATIONS = ("window", "group", "opswap", "condition", "combine")
WINDOW_LADDER = (5, 10, 20, 60, 120, 250)
WINDOW_STEP = 1.5
WINDOW_KEEP = frozenset({"ts_backfill", "group_backfill", "ts_delay"})
GICS_GROUPS = ("sector", "industry", "subindustry")
SWAP_GROUPS = {
    "smooth": ("ts_mean", "ts_decay_linear"),
    "ts_normalise": ("ts_zscore", "ts_rank", "ts_scale"),
    "group_normalise": ("group_rank", "group_zscore"),
    "change": ("ts_delta", "ts_av_diff", "ts_min_diff"),
    "dispersion": ("ts_std_dev", "ts_skewness", "ts_entropy"),
    "co_movement": ("ts_corr", "ts_covariance"),
    "count_timing": ("ts_arg_max", "ts_arg_min"),
}
SWAP_OF = {op: g for g, ops in SWAP_GROUPS.items() for op in ops}
COND_POS = frozenset({("if_else", 0), ("trade_when", 0), ("trade_when", 2)})
COND_OPS = ("if_else", "trade_when")


# ---------------------------------------------------------------------------------------------- the tree
def _is_option(v) -> bool:
    return v.op is None and v.name is not None


def _kids(n) -> list:
    return list(n.args) + [v for v in n.kw.values() if not _is_option(v)]


def _names(n) -> list:
    if n.op is None:
        return [n.name] if n.name is not None else []
    return [x for k in _kids(n) for x in _names(k)]


def _slot_num(nm, name):
    s = nm._slot_of.get(name)            # frames.Normal: the parse placeholder -> "$k" of the normal form
    return int(s[1:]) if s else None


def _has_slot(nm, n) -> bool:
    return any(nm.is_slot(x) for x in _names(n))


def _fields(nm, n) -> list:
    """The named fields under n (no slots, no group tokens)."""
    return [x for x in _names(n) if not nm.is_slot(x) and x not in FR.GROUP_TOKENS]


def render(nm, node, *, sub=None, ops=None, offset=0) -> str:
    """The text of `node` of the parsed frame `nm` (frames.Normal) in frames.py's normal spelling, with
    {id(node): text} substituted, {id(node): operator} renamed and every slot $k written $(k + offset)."""
    sub, ops = sub or {}, ops or {}

    def r(n):
        if id(n) in sub:
            return sub[id(n)]
        if n.op is not None:
            parts = [r(a) for a in n.args]
            parts += ["%s=%s" % (k, v.name if _is_option(v) else r(v)) for k, v in n.kw.items()]
            return "%s(%s)" % (ops.get(id(n), n.op), ",".join(parts))
        if n.name is not None:
            k = _slot_num(nm, n.name)
            return n.name if k is None else "$%d" % (k + offset)
        return nm.lit[id(n)][1]
    return r(node)


def walk(nm) -> list:
    """[(node, parent, position, in_fixed_condition, in_condition)] in pre-order. A condition is a subtree at
    COND_POS; a fixed condition is one that holds no slot."""
    out = []

    def w(n, parent, pos, fixed, cond):
        out.append((n, parent, pos, fixed, cond))
        if n.op is None:
            return
        for i, a in enumerate(n.args):
            c = (n.op, i) in COND_POS
            w(a, n, i, fixed or (c and not _has_slot(nm, a)), cond or c)
        for k, v in n.kw.items():
            if not _is_option(v):
                w(v, n, k, fixed, cond)
    w(nm.tree, None, None, False, False)
    return out


def legs(nm) -> list:
    """The frame's legs for `combine`: a root multiply's data-bearing operands (split again when one is such a
    multiply itself), else the whole tree."""
    def split(n):
        parts = [a for a in n.args if any(x not in FR.GROUP_TOKENS for x in _names(a))] if n.op == "multiply" else []
        return [x for a in parts for x in split(a)] if len(parts) >= 2 else [n]
    return split(nm.tree)


# ------------------------------------------------------------------------------------------ mutations
def _cand(kind, text, parents, mutation, offsets=None, preset_from=None) -> dict:
    return {"kind": kind, "text": text, "parents": parents, "offsets": offsets or [0] * len(parents),
            "mutation": mutation, "preset_from": preset_from}


def _rungs(w: float) -> list:
    down = [v for v in WINDOW_LADDER if w / v >= WINDOW_STEP]
    up = [v for v in WINDOW_LADDER if v / w >= WINDOW_STEP]
    return ([max(down)] if down else []) + ([min(up)] if up else [])


def _num(text: str):
    v = float(text)
    return int(v) if v.is_integer() else v


def window_mutations(e: dict, nm) -> list:
    sites = {}
    for n, _p, _i, fixed, _c in walk(nm):
        i = FR.WINDOW_ARG.get(n.op) if n.op is not None else None
        if i is None or n.op in WINDOW_KEEP or i >= len(n.args):
            continue
        a = n.args[i]
        if a.op is None and a.name is None and nm.lit[id(a)][0] == "num":
            sites.setdefault(render(nm, n), []).append((n, a, fixed))
    out = []
    for members in sites.values():
        if any(f for _n, _a, f in members):
            continue
        w = _num(nm.lit[id(members[0][1])][1])
        for v in _rungs(float(w)):
            text = render(nm, nm.tree, sub={id(a): str(v) for _n, a, _f in members})
            out.append(_cand("window", text, [e], {"kind": "window", "op": members[0][0].op, "from": w, "to": v,
                                                   "sites": len(members)}))
    return out


def group_mutations(e: dict, nm) -> list:
    sites = {}
    for n, p, i, fixed, _c in walk(nm):
        if n.op is None and n.name in FR.GROUP_TOKENS and p is not None:
            sites.setdefault((render(nm, p), i), []).append((n, p, fixed))
    out = []
    for members in sites.values():
        if any(f for _n, _p, f in members):
            continue
        cur = members[0][0].name
        for g in GICS_GROUPS:
            if g != cur:
                text = render(nm, nm.tree, sub={id(n): g for n, _p, _f in members})
                out.append(_cand("group", text, [e], {"kind": "group", "op": members[0][1].op, "from": cur, "to": g,
                                                      "sites": len(members)}))
    return out


def opswap_mutations(e: dict, nm) -> list:
    sites = {}
    for n, _p, _i, _f, cond in walk(nm):
        if n.op in SWAP_OF and not n.kw:
            sites.setdefault(render(nm, n), []).append((n, cond))
    out = []
    for members in sites.values():
        if any(c for _n, c in members):
            continue
        op = members[0][0].op
        for new in SWAP_GROUPS[SWAP_OF[op]]:
            if new != op:
                text = render(nm, nm.tree, ops={id(n): new for n, _c in members})
                out.append(_cand("opswap", text, [e], {"kind": "opswap", "role": SWAP_OF[op], "from": op, "to": new,
                                                       "sites": len(members)}))
    return out


def presets(entries: list, fl) -> dict:
    """condition text -> sorted ids of the library frames that write it. Slot-free, a compare (forge.meaning's
    _COMPARE) with exactly one data-bearing side, every field in today's catalogue of the cell (`fl` pruned)."""
    present = fl.ids_in(CELL)
    out = {}
    for e in entries:
        nm = FR.normalize(e["text"])
        for n, *_rest in walk(nm):
            if n.op not in COND_OPS or not n.args:
                continue
            c = n.args[0]
            if (c.op in MN._COMPARE and len(c.args) == 2 and not _has_slot(nm, c)
                    and sum(1 for a in c.args if _fields(nm, a)) == 1 and all(f in present for f in _fields(nm, c))):
                out.setdefault(render(nm, c), set()).add(e["id"])
    return {k: sorted(v) for k, v in out.items()}


def condition_mutations(e: dict, nm, pre: dict) -> list:
    conds = [n for n, *_rest in walk(nm) if n.op in COND_OPS]
    out = []
    if not conds:
        c = "0.5" if nm.tree.op in TY.SCORE01 else "0"
        for p, src in pre.items():
            out.append(_cand("condition", "if_else(%s,%s,%s)" % (p, nm.text, c), [e],
                             {"kind": "condition", "action": "add", "from": None, "to": p, "else": c, "preset_from": src},
                             preset_from=src))
    for n in conds:
        a0 = n.args[0]
        if _has_slot(nm, a0) or not _fields(nm, a0):
            continue
        if n.op == "trade_when" and len(n.args) > 2 and any(x not in FR.GROUP_TOKENS for x in _names(n.args[2])):
            continue
        cur = render(nm, a0)
        for p, src in pre.items():
            if p != cur:
                out.append(_cand("condition", render(nm, nm.tree, sub={id(a0): p}), [e],
                                 {"kind": "condition", "action": "replace", "from": cur, "to": p, "preset_from": src},
                                 preset_from=src))
    return out


def _leg_rows(nm) -> list:
    """[(leg node, leg text, leg structure)]; the structure is the leg renumbered from $1."""
    rows = []
    for l in legs(nm):
        t = render(nm, l)
        try:
            rows.append((l, t, FR.Normal(t).text))
        except FR.FrameError:
            rows.append((l, t, t))
    return rows


def combine_pair(a: dict, b: dict, normals: dict) -> list:
    """Every multiply(leg of a, leg of b) of one pair; b's slots are written after a's."""
    na, nb = normals[a["id"]], normals[b["id"]]
    out = []
    for _la, ta, ka in _leg_rows(na):
        for lb, tb, kb in _leg_rows(nb):
            if ka == kb:
                continue
            text = "multiply(%s,%s)" % (ta, render(nb, lb, offset=len(na.slots)))
            out.append(_cand("combine", text, [a, b], {"kind": "combine", "op": "multiply", "legs": [ta, tb]},
                             offsets=[0, len(na.slots)]))
    return out


def candidates(kind: str, parents: list, normals: dict, pre: dict, rng, used: set, spent: set):
    """One kind's candidates, lazily: the parents in a seeded shuffle, each parent's candidates in a seeded
    shuffle (for combine, each first parent's partners in a seeded shuffle, then that pair's candidates).
    Each candidate carries its "group": (kind, parent id), or ("combine", id, id) for a pair. Both sets are read
    as the call goes: a parent in `used` is skipped, and so is the rest of a group in `spent`."""
    order = list(parents)
    rng.shuffle(order)

    def feed(cs, g, ids):
        rng.shuffle(cs)
        for c in cs:
            if g in spent or used & ids:
                return
            c["group"] = g
            yield c
    for e in order:
        if e["id"] in used:
            continue
        if kind == "combine":
            partners = [p for p in parents if p["id"] != e["id"]]
            rng.shuffle(partners)
            for p in partners:
                if e["id"] in used:
                    break
                if p["id"] in used:
                    continue
                a, b = sorted((e, p), key=lambda x: x["id"])
                yield from feed(combine_pair(a, b, normals), ("combine", a["id"], b["id"]), {a["id"], b["id"]})
            continue
        nm = normals[e["id"]]
        cs = (window_mutations(e, nm) if kind == "window" else group_mutations(e, nm) if kind == "group"
              else opswap_mutations(e, nm) if kind == "opswap" else condition_mutations(e, nm, pre))
        yield from feed(cs, (kind, e["id"]), {e["id"]})


def slot_specs(cand: dict, nm2, roles: list) -> dict:
    """The parents' own-role slot roles and constraints (`roles`: one slot list per parent, aligned with
    cand["parents"]), keyed by the new frame's slot numbers. The new text wrote parent p's slot $k as
    $(k + offset_p); nm2.renumbered maps that to the normal form. unit_eq moves with its partner and is dropped
    when the partner is not in the new frame."""
    out = {}
    for slots, off in zip(roles, cand["offsets"]):
        for k, sl in enumerate(slots or [], 1):
            j = nm2.renumbered(k + off)
            if j is None:
                continue
            spec = {x: copy.deepcopy(sl[x]) for x in SC.SLOT_GIVEN if sl.get(x)}
            cons = dict(spec.get("constraints") or {})
            if "unit_eq" in cons:
                t = nm2.renumbered(int(str(cons["unit_eq"])[1:]) + off)
                if t is None:
                    del cons["unit_eq"]
                else:
                    cons["unit_eq"] = "$%d" % t
            if cons:
                spec["constraints"] = cons
            else:
                spec.pop("constraints", None)
            if spec:
                out[j] = spec
    return out


# ------------------------------------------------------------------------------------------- entries
def _view(entry: dict) -> dict:
    """round1.arm_entries fills a frame by its canonical history only when origin == "mined"."""
    pv = entry.get("provenance") or {}
    return dict(entry, provenance=dict(pv, origin="mined")) if pv.get("origin") == "mined-dropped" else entry


def own_role(entry: dict, fl, hist: dict) -> dict:
    """The entry as the planner fills it in own-role mode (round1.arm_entries' arm a)."""
    return R1.arm_entries(_view(entry), fl, hist)[0]


def _source(kind: str, root, fid: str) -> dict:
    p = ST.frames_dir(root) / ("%s.json" % fid)
    return {"kind": kind, "path": str(p), "sha256": EV.sha256(p), "ref": fid}


def mutation_entry(cand: dict, nm2, root, day: str, now: str, roles: list) -> dict:
    parents = [e["id"] for e in cand["parents"]]
    srcs = [_source("mutation-parent", root, p) for p in parents]
    if cand["preset_from"]:
        srcs.append(_source("condition-preset", root, cand["preset_from"][0]))
    e = SC.new_entry(nm2.text, sources=srcs, built_by=BUILT_BY, built_at=now, slot_specs=slot_specs(cand, nm2, roles))
    e["provenance"].update({"origin": "mutation", "parent": parents[0], "parents": parents,
                            "mutation": cand["mutation"], "cohort_day": day})
    return e


def dropped_entry(src: dict, ids_path, day: str, now: str) -> dict:
    e = copy.deepcopy(src)
    pv = e["provenance"]
    pv.update({"origin": "mined-dropped", "parents": [], "mutation": None, "cohort_day": day})
    pv["sources"] = list(pv["sources"]) + [{"kind": "mined-dropped", "path": str(ids_path),
                                            "sha256": EV.sha256(ids_path), "ref": "dropped_mined"}]
    e["status_history"] = list(e["status_history"]) + [{
        "status": "candidate", "at": now, "by": BUILT_BY,
        "reason": "cohort %s: a mined frame the curator dropped from the first 100 (doc 11 section 2.2)" % day}]
    return e


def fills_today(entry: dict, fl, hist: dict, seed: int) -> list:
    """Up to MIN_FILLS own-role fills of the entry on today's (already pruned) field library whose fields are
    pairwise disjoint, none a formula of the frame's canonical history. The filler's stream is
    random.Random(seed|text|cell), so a larger n extends a smaller call's list."""
    own = own_role(entry, fl, hist)
    h = hist.get(entry["canonical_key"])
    excl = set()
    for f in (h["fills"] if h else ()):
        try:
            excl.add(FR.substitute(entry["canonical_key"], f))
        except FR.FrameError:
            continue
    n = FILL_N0
    while True:
        res = FI.fill(own, fl, CELL, n=n, seed=seed, by="dataset", exclude=excl)
        if res["dead"]:
            return []
        picked, taken = [], set()
        for x in res["fills"]:
            if taken.isdisjoint(x["fill"]):
                picked.append(x)
                taken.update(x["fill"])
                if len(picked) == MIN_FILLS:
                    return picked
        if len(res["fills"]) < n or n >= FILL_NMAX:
            return picked
        n *= 2


# ------------------------------------------------------------------------------------------------ run
def corpus_keys(path) -> set:
    """Every canonical frame key of the corpus: the "frame_key" of each JSON line (rows_framed.jsonl and
    frames_summary.jsonl both carry it; on 2026-09-24 both gave the same 33,007 keys, re-counted 2026-09-25)."""
    out = set()
    with open(path) as fh:
        for line in fh:
            if line.strip():
                out.add(json.loads(line)["frame_key"])
    if not out:
        raise ValueError("%s holds no frame_key: refusing to call every key new" % path)
    return out


def load_dropped(ids_path, lib_dir) -> list:
    d = json.loads(pathlib.Path(ids_path).read_text())
    ids = d["dropped_mined"] if isinstance(d, dict) else d
    return [json.loads((ST.frames_dir(lib_dir) / ("%s.json" % i)).read_text()) for i in sorted(ids)]


def run(n: int, *, seed: int, day: str, now: str, root, fl, datasets_ok, hist: dict, corpus: set,
        dropped: list, dropped_ids, dry_run: bool = False) -> dict:
    """Make up to n new frames for ET day `day` and file them in the library at `root` (not when dry_run).
    `fl` is pruned here, in place, to today's datasets (framelib.loop.availability)."""
    avail = AV.prune(fl, datasets_ok)
    entries = ST.load(root)
    lib_keys = {e["canonical_key"] for e in entries}
    already = sorted(e["id"] for e in entries if (e.get("provenance") or {}).get("cohort_day") == day)
    want = max(0, n - len(already))
    max_checks = CHECKS_PER_FRAME * want
    rep = {"day": day, "seed": seed, "n": n, "already": already, "availability": avail, "added": [],
           "rejected": collections.Counter(), "exhausted": [], "checks": 0, "check_budget": max_checks,
           "written": False}
    new, taken, used, spent = [], set(), set(), set()

    def check(entry, kind, parents) -> str | None:
        """None when the entry is taken; else why not ("fills" when it fell short of MIN_FILLS)."""
        errs = SC.validate(entry)
        if errs:
            rep["rejected"]["%s: schema: %s" % (kind, errs[0][:80])] += 1
            return "schema"
        rep["checks"] += 1
        fills = fills_today(entry, fl, hist, seed)
        if len(fills) < MIN_FILLS:
            rep["rejected"]["%s: fewer than %d disjoint fills today" % (kind, MIN_FILLS)] += 1
            return "fills"
        new.append(entry)
        taken.add(entry["canonical_key"])
        used.update(parents)
        rep["added"].append({"id": entry["id"], "origin": entry["provenance"]["origin"], "kind": kind,
                             "parents": parents, "mutation": entry["provenance"]["mutation"],
                             "family": entry["characteristics"]["family"], "text": entry["text"],
                             "fills": [x["fill"] for x in fills]})
        return None

    for src in dropped:
        if len(new) >= want or rep["checks"] >= max_checks:
            break
        if src["canonical_key"] in lib_keys or src["canonical_key"] in taken:
            rep["rejected"]["mined-dropped: already in the library"] += 1
            continue
        check(dropped_entry(src, dropped_ids, day, now), "mined-dropped", [])

    parents = [e for e in entries if e["status"] != "retired" and (e.get("provenance") or {}).get("cohort_day") != day]
    by_id = {e["id"]: e for e in parents}
    normals = {e["id"]: FR.normalize(e["text"]) for e in parents}
    roles = {}
    pre = presets(parents, fl)
    rep["presets"] = len(pre)
    streams = {k: candidates(k, parents, normals, pre, random.Random("framelib.loop.newframes|%d|%s" % (seed, k)),
                             used, spent) for k in MUTATIONS}

    def role_slots(pid):
        if pid not in roles:
            roles[pid] = own_role(by_id[pid], fl, hist).get("slots")
        return roles[pid]

    def attempt(c) -> bool:
        kind, pids = c["kind"], [e["id"] for e in c["parents"]]
        if used & set(pids):
            rep["rejected"]["%s: parent already used this call" % kind] += 1
            return False
        try:
            nm2 = FR.normalize(c["text"])
        except FR.FrameError:
            rep["rejected"]["%s: does not parse" % kind] += 1
            return False
        key = nm2.key
        why = ("canonical key in the library" if key in lib_keys else
               "canonical key made earlier in this call" if key in taken else
               "canonical key in the canonical corpus" if key in corpus else None)
        if why:
            rep["rejected"]["%s: %s" % (kind, why)] += 1
            return False
        why = check(mutation_entry(c, nm2, root, day, now, [role_slots(p) for p in pids]), kind, pids)
        if why == "fills":
            spent.add(c["group"])
        return why is None

    def one(kind):
        """True: one frame made; False: the kind has no candidate left; None: the check budget is spent."""
        for c in streams[kind]:
            if rep["checks"] >= max_checks:
                return None
            if attempt(c):
                return True
        return False

    active = list(MUTATIONS)
    while len(new) < want and active and rep["checks"] < max_checks:
        for kind in list(active):
            if len(new) >= want or rep["checks"] >= max_checks:
                break
            if one(kind) is False:
                active.remove(kind)
                rep["exhausted"].append(kind)
    rep["groups_spent"] = len(spent)
    rep["rejected"] = dict(sorted(rep["rejected"].items()))
    rep["short"] = want - len(new)
    if not dry_run and new:
        for e in new:
            ST.save(e, root)
        ST.write_index(list(ST.read_all(root).values()), root)
        rep["written"] = True
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    ap.add_argument("--n", type=int, default=25)
    ap.add_argument("--seed", type=int, default=None, help="default: the ET day as YYYYMMDD")
    ap.add_argument("--day", default="", help="ET day YYYY-MM-DD; default: today's (forge.submit.quota_day)")
    ap.add_argument("--library", default=str(ST.LIBRARY))
    ap.add_argument("--datasets-ok", default=str(AV.PATH))
    ap.add_argument("--history", default=str(HISTORY), help="canonical rows of USA/d1/TOP3000 (rows_framed form)")
    ap.add_argument("--canonical", default=str(CANONICAL),
                    help="JSON lines with frame_key over the WHOLE canonical corpus (frames_summary.jsonl or rows_framed.jsonl)")
    ap.add_argument("--dropped-ids", default=str(DROPPED_IDS))
    ap.add_argument("--dropped-lib", default=str(DROPPED_LIB))
    ap.add_argument("--now", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    from forge import submit as FS
    day = a.day or FS.quota_day(time.time())
    seed = a.seed if a.seed is not None else int(day.replace("-", ""))
    now = a.now or DT.datetime.now(DT.timezone.utc).replace(microsecond=0).isoformat()
    try:
        AV.load(a.datasets_ok)
        for p in (a.history, a.canonical, a.dropped_ids):
            if not pathlib.Path(p).exists():
                raise FileNotFoundError("%s missing" % p)
        corpus = corpus_keys(a.canonical)
        dropped = load_dropped(a.dropped_ids, a.dropped_lib)
        from framelib.fields import FieldLibrary
        rep = run(a.n, seed=seed, day=day, now=now, root=pathlib.Path(a.library), fl=FieldLibrary.build(cells={CELL}),
                  datasets_ok=a.datasets_ok, hist=R1.history(a.history), corpus=corpus, dropped=dropped,
                  dropped_ids=a.dropped_ids, dry_run=a.dry_run)
    except (AV.AvailabilityError, OSError, ValueError, KeyError) as exc:     # store.LibraryError is a ValueError
        print(json.dumps({"error": "fail-closed, nothing written: %s: %s" % (type(exc).__name__, str(exc)[:500])}))
        return 2
    print(json.dumps(rep, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
