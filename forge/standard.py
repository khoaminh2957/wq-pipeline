"""forge.standard — the mechanical half of the ratified hypothesis standard
(`fetched/hypothesis_standard.md`, Khoa 2026-07-17): the 8 hard gates, evaluated BEFORE a sim.

What a program can check: gates 1 (mechanism length, no paraphrase of the signal name), 2 (a
named agent class), 3 (a labelled, dated citation), 4 (regime sign map), 5 (declared sign, no
flip flag), 6 (>= 2 cross-family legs with a conditioning combiner), 7 (fields resolve — done by
the factory), 8 (journal collision — done by the pre-sim gate). What it cannot judge: whether the
mechanism is TRUE. That stays with the author and the sim.
A single-field hypothesis trips gate 6 by construction: it is a LEG, never an alpha on its own.
"""
from __future__ import annotations

import re

from forge import hypotheses as H

_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def hard_gates(obj) -> list:
    """List of (gate number, reason). Empty = admissible for simulation."""
    trips = []
    if isinstance(obj, H.Hypothesis):
        trips.append((6, "single-field construction (%s): a leg, not an alpha — standard Dim 5 'Law-1 null'" % obj.id))
        return trips
    c = obj
    words = str(c.mechanism).split()
    if len(words) < 25:
        trips.append((1, "mechanism under 25 words"))
    if c.id.replace("_", " ") in str(c.mechanism).lower():
        trips.append((1, "mechanism paraphrases the composite's own name"))
    if not any(w in str(c.counterparty).lower() for w in H.AGENT_WORDS):
        trips.append((2, "counterparty names no concrete agent class"))
    if not any(str(c.source).startswith(l) for l in H.LABELS) or not _YEAR.search(str(c.source)):
        trips.append((3, "source lacks a RULE-0 label or a dated citation"))
    if set(c.regimes or {}) != set(H.REGIME_KEYS):
        trips.append((4, "no per-sub-regime sign map"))
    if "flip" in str(c.notes).lower() and "no flip" not in str(c.notes).lower():
        trips.append((5, "notes plan a sign flip"))
    if len(c.legs) < 2 or len(set(c.families)) < 2:
        trips.append((6, "fewer than two cross-family legs"))
    if not set(c.combiners) <= set(H.COMBINERS):
        trips.append((6, "combiner is not a conditioning combiner"))
    return trips


def admissible(obj) -> bool:
    return not hard_gates(obj)
