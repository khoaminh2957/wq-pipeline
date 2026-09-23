"""forge.hypotheses — the offline-authored hypothesis library (C5, C7).

One YAML file per hypothesis under forge/hypotheses/. The loop has no LLM, so a hypothesis is
DATA: a written mechanism, the datasets and fields that carry it, a formula template and the
parameter/settings grid the factory expands. RULE 0 applies to the files: `source` must begin
with EX-ANTE, SOURCE, POST-HOC or SPECULATION.
"""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field

import yaml

CATEGORIES = ("Analyst", "Broker", "Earnings", "Fundamental", "Imbalance", "Insiders", "Institutions",
              "Macro", "Model", "News", "Option", "Other", "Price Volume", "Risk", "Sentiment",
              "Short Interest", "Social Media")
VEC_OPS = ("vec_avg", "vec_sum", "vec_count", "vec_max", "vec_min", "vec_stddev", "vec_range")
# MEASURED on the canary (2026-09-04, 197 rows): a sparse signal (NaN for names without an event)
# ranks into a 3–20-name book and fails CONCENTRATED_WEIGHT (163/197). `density` makes the leg
# dense BEFORE the template: "zero" (a missing count IS zero: add(x, 0, filter=true)) or
# "backfill" (a missing score is "no news yet": ts_backfill(x, density_window)).
DENSITY = ("zero", "backfill")
LABELS = ("EX-ANTE", "SOURCE", "POST-HOC", "SPECULATION")
REQUIRED = ("id", "category", "mechanism", "sign", "source", "datasets", "signal", "template", "params", "settings")
OPTIONAL_SIGNAL2 = "signal2"     # {"fields": [...]} paired index-by-index with signal.fields
_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


class HypothesisError(ValueError):
    pass


@dataclass
class Hypothesis:
    id: str
    category: object            # pyramid category name, or a list of them
    mechanism: str
    sign: int
    source: str
    datasets: list
    signal: dict                # {"fields": [...], "vector": "vec_avg"|None, "pattern": regex|None}
    template: object            # a format string, or a list of alternative format strings
    params: dict                # name -> list of values
    settings: dict              # neutralization: [...], decay: [...], truncation: float
    signal2: dict | None = None # {"fields": [...]} — second leg, paired with signal.fields by index
    regions: object = "any"     # "any" or list of region codes
    delays: list = field(default_factory=lambda: [0, 1])
    family: str = ""            # cross-family combiners need this (standard Dim 5): accruals, profitability, ...
    title: str = ""
    counterparty: str = ""
    notes: str = ""
    path: str = ""

    def templates(self) -> list:
        return list(self.template) if isinstance(self.template, list) else [self.template]

    def placeholders(self) -> set:
        return {ph for t in self.templates() for ph in _PLACEHOLDER.findall(t)}

    def categories(self) -> list:
        return list(self.category) if isinstance(self.category, list) else [self.category]


def _check(h: dict, path) -> None:
    missing = [k for k in REQUIRED if k not in h]
    if missing:
        raise HypothesisError("%s: missing %s" % (path, missing))
    cats = h["category"] if isinstance(h["category"], list) else [h["category"]]
    for c in cats:
        if c not in CATEGORIES:
            raise HypothesisError("%s: unknown category %r" % (path, c))
    if h["sign"] not in (-1, 1):
        raise HypothesisError("%s: sign must be -1 or 1" % path)
    if not any(str(h["source"]).startswith(l) for l in LABELS):
        raise HypothesisError("%s: source must start with one of %s (RULE 0)" % (path, LABELS))
    sig = h["signal"]
    if not isinstance(sig, dict) or not (sig.get("fields") or sig.get("pattern")):
        raise HypothesisError("%s: signal needs `fields` or `pattern`" % path)
    if sig.get("vector") is not None and sig["vector"] not in VEC_OPS:
        raise HypothesisError("%s: signal.vector %r not a vec_* operator" % (path, sig["vector"]))
    if sig.get("density") is not None and sig["density"] not in DENSITY:
        raise HypothesisError("%s: signal.density must be one of %s" % (path, DENSITY))
    if sig.get("density_window") is not None and (not isinstance(sig["density_window"], int) or sig["density_window"] <= 0):
        raise HypothesisError("%s: signal.density_window must be a positive int" % path)
    allowed = set(h["params"]) | {"signal"}
    s2 = h.get(OPTIONAL_SIGNAL2)
    if s2 is not None:
        if not isinstance(s2, dict) or not s2.get("fields") or not sig.get("fields"):
            raise HypothesisError("%s: signal2 needs `fields`, and signal must list explicit `fields`" % path)
        if len(s2["fields"]) != len(sig["fields"]):
            raise HypothesisError("%s: signal2.fields must pair 1:1 with signal.fields" % path)
        allowed.add("signal2")
    templates = h["template"] if isinstance(h["template"], list) else [h["template"]]
    if not templates or not all(isinstance(t, str) and t for t in templates):
        raise HypothesisError("%s: template must be a string or a non-empty list of strings" % path)
    ph = set()
    for t in templates:
        tph = set(_PLACEHOLDER.findall(t))
        if "signal" not in tph:
            raise HypothesisError("%s: every template must use {signal}" % path)
        if s2 is not None and "signal2" not in tph:
            raise HypothesisError("%s: signal2 given but a template does not use {signal2}" % path)
        ph |= tph
    bad = ph - allowed
    if bad:
        raise HypothesisError("%s: template placeholders without params: %s" % (path, sorted(bad)))
    for k, v in h["params"].items():
        if not isinstance(v, list) or not v:
            raise HypothesisError("%s: params.%s must be a non-empty list" % (path, k))
    st = h["settings"]
    if not isinstance(st.get("neutralization"), list) or not isinstance(st.get("decay"), list):
        raise HypothesisError("%s: settings.neutralization and settings.decay must be lists" % path)
    if h.get("regions", "any") != "any" and not isinstance(h["regions"], list):
        raise HypothesisError("%s: regions must be 'any' or a list" % path)
    if not set(h.get("delays", [0, 1])) <= {0, 1}:
        raise HypothesisError("%s: delays must be within {0, 1}" % path)


def load_file(path) -> Hypothesis:
    path = pathlib.Path(path)
    h = yaml.safe_load(path.read_text())
    if not isinstance(h, dict):
        raise HypothesisError("%s: not a mapping" % path)
    _check(h, path)
    known = {f for f in Hypothesis.__dataclass_fields__}
    extra = set(h) - known
    if extra:
        raise HypothesisError("%s: unknown keys %s" % (path, sorted(extra)))
    return Hypothesis(path=str(path), **h)


COMBINERS = ("multiply", "gate")
REGIME_KEYS = ("value_winter_2014_2020", "momentum_crash_2016", "covid_2020", "rate_shock_2022")
# a concrete losing agent class (hypothesis_standard gate 2): the counterparty must NAME one of these
AGENT_WORDS = ("retail", "individual", "analyst", "institution", "fund", "index", "arbitrage", "manager", "insider",
               "short seller", "dealer", "market maker", "creditor", "follower", "momentum trader", "trend follower",
               "quant", "passive", "pension", "insurer", "bank", "broker", "value investor", "growth investor",
               "shareholder", "holder", "equity-only institution")


@dataclass
class Composite:
    """A cross-family composite per the ratified hypothesis standard (Dim 5): >= 2 legs of different
    families joined by a conditioning combiner, with a regime sign map and a pre-registered
    strongest sub-population. Legs are hypothesis ids from the library."""
    id: str
    legs: list
    families: list
    mechanism: str
    counterparty: str
    source: str
    regimes: dict
    strongest_in: str
    weakens_when: str
    settings: dict
    combiners: list = field(default_factory=lambda: ["multiply"])
    title: str = ""
    notes: str = ""
    path: str = ""
    arm: str = "current"        # harness5 A/B (Khoa Q24): "new" composites form the new arm of a round


COMPOSITE_REQUIRED = ("id", "legs", "families", "mechanism", "counterparty", "source", "regimes", "strongest_in",
                      "weakens_when", "settings")


def _check_composite(c: dict, path, library_ids) -> None:
    missing = [k for k in COMPOSITE_REQUIRED if k not in c]
    if missing:
        raise HypothesisError("%s: missing %s" % (path, missing))
    legs = c["legs"]
    if not isinstance(legs, list) or len(legs) < 2:
        raise HypothesisError("%s: a composite needs >= 2 legs" % path)
    unknown = [l for l in legs if l not in library_ids]
    if unknown:
        raise HypothesisError("%s: legs not in the library: %s" % (path, unknown))
    fams = c["families"]
    if not isinstance(fams, list) or len(fams) != len(legs) or len(set(fams)) != len(fams):
        raise HypothesisError("%s: families must pair 1:1 with legs and all differ (cross-family, standard Dim 5)" % path)
    if not any(str(c["source"]).startswith(l) for l in LABELS):
        raise HypothesisError("%s: source must start with one of %s (RULE 0)" % (path, LABELS))
    reg = c["regimes"]
    if not isinstance(reg, dict) or set(reg) != set(REGIME_KEYS) or not all(str(v) in ("+", "-", "0") for v in reg.values()):
        raise HypothesisError("%s: regimes must give a sign (+/-/0) for each of %s (standard gate 4)" % (path, REGIME_KEYS))
    if not str(c["strongest_in"]).strip() or not str(c["weakens_when"]).strip():
        raise HypothesisError("%s: strongest_in and weakens_when must be stated (standard Dim 4)" % path)
    cp = str(c["counterparty"]).lower()
    if not any(w in cp for w in AGENT_WORDS):
        raise HypothesisError("%s: counterparty must name a concrete agent class (standard gate 2), e.g. %s" % (path, AGENT_WORDS[:6]))
    if len(str(c["mechanism"]).split()) < 25:
        raise HypothesisError("%s: mechanism must be a real typed chain (>= 25 words), not a signal paraphrase (standard gate 1)" % path)
    comb = c.get("combiners", ["multiply"])
    if not isinstance(comb, list) or not comb or not set(comb) <= set(COMBINERS):
        raise HypothesisError("%s: combiners must be a non-empty subset of %s" % (path, COMBINERS))
    st = c["settings"]
    if not isinstance(st.get("neutralization"), list) or not isinstance(st.get("decay"), list):
        raise HypothesisError("%s: settings.neutralization and settings.decay must be lists" % path)


def load_composite(path, library_ids) -> Composite:
    path = pathlib.Path(path)
    c = yaml.safe_load(path.read_text())
    if not isinstance(c, dict):
        raise HypothesisError("%s: not a mapping" % path)
    _check_composite(c, path, set(library_ids))
    extra = set(c) - set(Composite.__dataclass_fields__)
    if extra:
        raise HypothesisError("%s: unknown keys %s" % (path, sorted(extra)))
    return Composite(path=str(path), **c)


def load_composites(directory, library) -> list:
    ids = {h.id for h in library}
    out, seen = [], set()
    for p in sorted(pathlib.Path(directory).glob("*.yaml")):
        c = load_composite(p, ids)
        if c.id in seen:
            raise HypothesisError("duplicate composite id %r" % c.id)
        seen.add(c.id)
        out.append(c)
    return sorted(out, key=lambda c: c.id)


def load_library(directory) -> list:
    """All *.yaml in `directory`, sorted by id. Duplicate ids are an error."""
    out, seen = [], {}
    for p in sorted(pathlib.Path(directory).glob("*.yaml")):
        h = load_file(p)
        if h.id in seen:
            raise HypothesisError("duplicate hypothesis id %r in %s and %s" % (h.id, seen[h.id], p))
        seen[h.id] = p
        out.append(h)
    return sorted(out, key=lambda h: h.id)


def categories(library) -> set:
    return {c for h in library for c in h.categories()}
