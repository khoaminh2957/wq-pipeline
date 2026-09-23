"""The machine grader for one LLM-proposed mechanism. No simulation, no quota, no judgement call.

WHY THIS EXISTS (measured, not assumed). The random-within-grammar generator lost 5/5 live A/B
rounds (0.1 % of its rows reached the Sharpe bar against 2.6 % for the hand-written library,
docs/redesign/02_design.md §11y). The only new mechanism ever to clear every binding platform check
came from a hand-written EX-ANTE economic hypothesis. So a generator's value is in the ECONOMICS it
states, and a local model states economics badly on its own: it invents field ids, mis-states units,
and cites papers that do not exist. Every one of those failures is DECIDABLE from files already in
this repo, so none of them should ever reach a simulation.

`verify()` runs the checks the repo can decide, cheapest first, and returns one verdict per check
with its reason. It is the evaluator in the FunSearch / AlphaEvolve sense: the model proposes, this
decides, and the model never grades itself.

Checks, in order:
  schema        both YAMLs load through the real loaders (forge.hypotheses)
  fields        every field id exists in the region catalogue with the structure the leg assumes
  density       coverage < DENSITY_COVERAGE needs a density rule; quarterly/annual needs ts_backfill
  sign          the leg's stated sign against the label file's sign for its own fields
  renders       forge.compose actually produces a candidate on a real cell
  typed         the live pre-sim gate (forge.typed structural judge: H1 units, H2 kinds, H4 vector)
  standard      the 8 hard gates of fetched/hypothesis_standard.md (forge.standard)
  distinct      the family pair is new to the library, and the fields are unburned in the journal

Usage in a generation loop: build the Context ONCE (it reads a 105 MB label file and a 52 MB
catalogue), then call verify() per candidate.
"""
from __future__ import annotations

import json
import pathlib
import random
import re

from forge import cells as C
from forge import compose as CP
from forge import hypotheses as H
from forge import labels as LB
from forge import runner as RN
from forge import standard as ST
from forge import typed as TY

ROOT = pathlib.Path(__file__).resolve().parents[2]
DENSITY_COVERAGE = 0.5          # forge/grammar.py's own threshold for "sparse enough to need a rule"
BACKFILL_CADENCE = ("quarterly", "annual")


class Context:
    """The expensive, read-once state every check shares."""

    def __init__(self, root=ROOT, region="USA", delay=1, universe="TOP3000"):
        self.root, self.region, self.delay, self.universe = pathlib.Path(root), region, delay, universe
        self.key = "%s/d%d" % (region, delay)
        self.labels = LB.load(self.root / "fetched/rc/field_labels.jsonl")
        self.library = H.load_library(str(self.root / "forge/hypotheses"))
        self.lib_by_id = {h.id: h for h in self.library}
        self.composites = H.load_composites(str(self.root / "forge/composites"), self.library)
        self.catalogue = {}
        with open(self.root / ("fetched/rc/fields/%s_%s_d%d.jsonl" % (region, universe, delay))) as fh:
            for line in fh:
                r = json.loads(line)
                self.catalogue[r["id"]] = r
        self.cells = [c for c in C.targets(self.root, self.library) if c.region == region and c.delay == delay]
        self._index = RN.Catalogues(self.root).index(region, universe, delay)
        self._burned = None

    @property
    def burned(self) -> set:
        """Field ids that already appear in a simulated formula (the journal is the record of spend)."""
        if self._burned is None:
            seen, word = set(), re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
            path = self.root / "state/layered/runs/forge.jsonl"
            if path.exists():
                with open(path) as fh:
                    for line in fh:
                        i = line.find('"formula"')
                        if i < 0:
                            continue
                        for tok in word.findall(line[i:i + 2000]):
                            if tok in self.catalogue:
                                seen.add(tok)
            self._burned = seen
        return self._burned


def _fields_of(leg: H.Hypothesis) -> list:
    out = list((leg.signal or {}).get("fields") or [])
    out += list((getattr(leg, "signal2", None) or {}).get("fields") or [])
    return out


def _templates(leg: H.Hypothesis) -> str:
    t = leg.template
    return " ".join(t) if isinstance(t, (list, tuple)) else str(t)


OVERRIDE_WORDS = ("override", "overrides", "contradict", "description says", "against the label",
                  "label file", "prior is wrong", "despite the label")


def sign_verdict(claimed: int, label: dict, notes: str, field_id: str = "") -> tuple:
    """Does the leg's stated direction survive the label file's own reading of this field?

    `claimed` is the leg's sign (+1 / -1). `label` is the label record, carrying `sign`
    ("+" / "-" / "unstated") and `sign_source` ("description" | "domain-prior" | "unstated").
    `notes` is the leg's notes block, where an author overriding a label says why.
    Returns (ok, reason); `reason` is fed back to the model so it can repair.

    THE RULE, and why each branch is where it is (Khoa's standing principle: hard for unit/kind
    errors, soft for semantic preference -- so a sign is soft UNLESS it contradicts a fact):

      no label / sign "unstated"   PASS. The label file declined to take a position; the leg's own
                                   reading of the description is then the only reading on offer.
      agreement                    PASS.
      disagreement, source
        "description"              FAIL unless the notes say so. The label was read off the field's
                                   OWN description, so contradicting it silently is a factual error,
                                   not a preference. An author who has read the description and still
                                   disagrees says so -- that is exactly what the round-1 legs did
                                   (model37 credit ranks, nlp_news_scores negative channel).
        "domain-prior"             PASS, recorded. The prior is literature, not this field: the
                                   insider-flow prior was MEASURED wrong and removed from labels.py
                                   on 2026-09-07. Blocking on it would make the label file
                                   unfalsifiable by a better-informed leg.

    ONE LINE TO CHANGE if Khoa wants it stricter: make the "domain-prior" branch return False.
    """
    if not label:
        return True, ""
    stated = label.get("sign")
    if stated not in ("+", "-"):
        return True, ""
    if (stated == "+") == (claimed > 0):
        return True, ""
    source = label.get("sign_source") or "unstated"
    said = field_id and field_id in (notes or "")
    said = said or any(w in (notes or "").lower() for w in OVERRIDE_WORDS)
    if source == "description" and not said:
        return False, ("leg claims %s but the field DESCRIPTION reads %s; say in notes why the "
                       "description is wrong, or flip the sign" % ("+" if claimed > 0 else "-", stated))
    return True, ""


def why_no_render(comp, lib_by: dict, ctx: Context) -> str:
    """"0 candidates" tells the model nothing it can act on. Walk forge.factory's own preconditions
    in order and name the first one each leg fails, in the model's vocabulary."""
    from forge import factory as F

    cell_names = sorted({c.category for c in ctx.cells})
    reasons = []
    for lid in comp.legs:
        h = lib_by.get(lid)
        if h is None:
            reasons.append("leg %s is not in the library" % lid)
            continue
        if ctx.delay not in h.delays:
            reasons.append("%s declares delays %s, this cell is d%d" % (lid, h.delays, ctx.delay))
            continue
        if h.regions != "any" and ctx.region not in h.regions:
            reasons.append("%s declares regions %s, not %s" % (lid, h.regions, ctx.region))
            continue
        cats = h.categories()
        if not set(cats) & set(cell_names):
            reasons.append("%s has category %s; the categories that exist at %s are: %s"
                           % (lid, cats, ctx.key, ", ".join(cell_names)))
            continue
        usable = F.eligible_fields(h, cats[0], ctx._index)
        if not usable:
            reasons.append("%s: none of its fields are usable in the %s catalogue (wrong region, "
                           "wrong type for the template, or a signal2 field missing its pair)" % (lid, cats[0]))
    return "; ".join(reasons) or "no cell serves both legs at once"


def verify(leg_path, comp_path, ctx: Context, seed: int = 0) -> dict:
    """Grade one proposed mechanism. Returns {ok, checks: [{name, ok, detail}], ...}."""
    checks, out = [], {"leg": str(leg_path), "composite": str(comp_path)}

    def add(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        return ok

    # --- schema -------------------------------------------------------------------------------
    try:
        leg = H.load_file(leg_path)
        ids = set(ctx.lib_by_id) | {leg.id}
        comp = H.load_composite(comp_path, ids)
    except Exception as exc:                                    # noqa: BLE001 -- the model's YAML is untrusted input
        add("schema", False, "%s: %s" % (type(exc).__name__, exc))
        return {**out, "ok": False, "checks": checks, "failed": ["schema"], "reused_fields": []}
    add("schema", True, "leg %s, composite %s" % (leg.id, comp.id))

    # --- fields exist, with the structure the leg assumes --------------------------------------
    missing, wrong = [], []
    for fid in _fields_of(leg):
        row = ctx.catalogue.get(fid)
        if row is None:
            missing.append(fid)
            continue
        want_vector = bool((leg.signal or {}).get("vector"))
        is_vector = str(row.get("type", "")).upper() == "VECTOR"
        if want_vector != is_vector:
            wrong.append("%s is %s, leg treats it as %s" % (fid, row.get("type"), "VECTOR" if want_vector else "MATRIX"))
    add("fields", not missing and not wrong,
        "; ".join(["not in %s: %s" % (ctx.key, ", ".join(missing))] if missing else []) +
        ("; " if missing and wrong else "") + "; ".join(wrong))

    # --- density and cadence -------------------------------------------------------------------
    tmpl, gaps = _templates(leg), []
    for fid in _fields_of(leg):
        lab = LB.for_region(ctx.labels.get(fid) or {}, ctx.key) or {}
        cov = lab.get("coverage")
        if isinstance(cov, (int, float)) and cov < DENSITY_COVERAGE and not (leg.signal or {}).get("density"):
            gaps.append("%s coverage %.2f needs a density rule" % (fid, cov))
        if lab.get("time") in BACKFILL_CADENCE and "ts_backfill" not in tmpl:
            gaps.append("%s is %s and the template has no ts_backfill" % (fid, lab.get("time")))
    add("density", not gaps, "; ".join(gaps))

    # --- sign against the label file (the decision lives in sign_verdict) -----------------------
    # Only the PRIMARY fields carry the leg's direction: signal2 is a denominator or a scale, and
    # its own label sign says nothing about which way the ratio predicts.
    sign_bad = []
    for fid in (leg.signal or {}).get("fields") or []:
        lab = LB.for_region(ctx.labels.get(fid) or {}, ctx.key) or {}
        ok, why = sign_verdict(leg.sign, lab, leg.notes or "", fid)
        if not ok:
            sign_bad.append("%s: %s" % (fid, why))
    add("sign", not sign_bad, "; ".join(sign_bad))

    # --- renders, and the live pre-sim gate ----------------------------------------------------
    rng = random.Random(seed)
    lib_by = dict(ctx.lib_by_id, **{leg.id: leg})
    rendered, refused = [], []
    serves = {c for lid in comp.legs if lib_by.get(lid) for c in lib_by[lid].categories()}
    for cell in ctx.cells:
        if cell.category not in serves:
            continue
        fd = {f: m["dataset"] for f, m in ctx._index.items()} or None
        rendered += CP.expand(comp, cell, ctx._index, lib_by, rng, max_candidates=8, field_datasets=fd)
        if rendered:
            break
    add("renders", bool(rendered), "%d candidate(s)" % len(rendered) if rendered else why_no_render(comp, lib_by, ctx))
    for cand in rendered[:8]:
        v = TY.judge(cand["formula"], ctx.labels, region=ctx.key, structural=True)
        if not v.get("ok", True):
            refused.append("; ".join(v.get("hard") or [str(v)])[:120])
    add("typed", not refused, " | ".join(refused[:3]))

    # --- the 8 hard gates ----------------------------------------------------------------------
    trips = ST.hard_gates(comp)
    add("standard", not trips, "; ".join("gate %d: %s" % t for t in trips))

    # --- distinct from what the library already holds ------------------------------------------
    # The family PAIR is the hard part: a second composite on the same two domains is a sibling of
    # one we already run, and siblings read prod-corr 0.79-0.85 (01_origins §5.3).
    # Reused FIELDS are only reported, never a trip: we MEASURED that field reuse does not set
    # either correlation -- the identical field set spans PROD 0.47-0.95 and SELF 0.15-0.91, and the
    # one alpha sharing no field with a submission read the second-highest SELF on file
    # (docs/harness5/round_3/prod_vs_self.md §2, §3a). Blocking on it would block on a non-effect.
    pair = tuple(sorted(set(comp.families)))
    clash = [c.id for c in ctx.composites if c.id != comp.id and tuple(sorted(set(c.families))) == pair]
    burned = [f for f in _fields_of(leg) if f in ctx.burned]
    add("distinct", not clash, "family pair %s already in %s" % ("×".join(pair), ", ".join(clash)) if clash else "")

    return {**out, "ok": all(c["ok"] for c in checks), "checks": checks,
            "reused_fields": burned,
            "failed": [c["name"] for c in checks if not c["ok"]]}


def report(v: dict) -> str:
    """One line per check, for a log or for feeding a repair prompt back to the model."""
    lines = ["%s  %s" % ("PASS" if v["ok"] else "FAIL", v.get("composite", ""))]
    for c in v.get("checks", []):
        lines.append("  %-9s %-4s %s" % (c["name"], "ok" if c["ok"] else "TRIP", c["detail"][:150]))
    return "\n".join(lines)
