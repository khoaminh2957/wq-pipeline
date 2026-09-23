#!/usr/bin/env python3
"""cell_map.py -- which pyramid cell(s) does an alpha count toward?

READ-ONLY, OFFLINE. Opens no socket. Never submits.

WHAT IS ESTABLISHED (measured 2026-08-12 against the platform's own answer)
--------------------------------------------------------------------------
Ground truth is `GET /users/self/alphas` -> alpha["pyramids"], a LIST of cells, and
alpha["pyramidThemes"]["effective"], an integer. 48 ACTIVE alphas on this account carry
pyramid tags (all USA delay 1; all submitted 2026-07-17 or later -- credit is not retroactive).

R1  CELL SET = the UNION of the pyramid CATEGORY of every FIELD appearing in the formula.
    Measured: 48/48 exact set match (precision 1.000, recall 1.000, 94 memberships) when the
    field catalog is the region/delay-matched dump fetched/rc/fields/USA_TOP3000_d1.jsonl.
    Zero formula tokens were left unresolved. Ablation: the "raw price-volume token" special
    case in tools/submit_alphas.py::_cell_gate is NOT load-bearing here -- all nine of
    close/open/high/low/vwap/volume/returns/adv20/cap are already in the catalog as
    "Price Volume" -- but it is kept as a harmless fallback for thinner catalogs.
    Re-derived a second way with the older, thinner catalog (fetched/fields_all.jsonl +
    state/fieldmap.json): 46/48 exact. Both misses were fields ABSENT from that catalog, and
    both were flagged by the unresolved-token test below, so on its confident subset that
    derivation scored 44/44. The rule is the same; only catalog coverage differed.

R2  MULTI-MEMBERSHIP IS REAL AND THE SUBMITTER MUST PLAN FOR A SET, NOT A VALUE.
    Observed distribution over the 48: 4 alphas in 1 cell, 42 in 2 cells, 2 in 3 cells.
    A 2-cell alpha is credited +1 in BOTH cells -- summing memberships over the alphas with
    effective>0 reproduces /users/self/activities/pyramid-alphas exactly in all 16 USA-d1
    cells (Price Volume 40, Model 19, Fundamental/Option/Analyst/Other/Earnings/Risk/
    Institutions/Macro 3 each, News 2, Insiders 2, Sentiment 1, Social Media / Short Interest
    / Imbalance 0). So one submit can close two cells at once.

R3  A 3-CELL ALPHA IS CREDITED NOWHERE. Both 3-cell alphas (MPLkl7mk, Xg8oQJRl) carry
    pyramidThemes.effective == 0 and the platform counter excludes them from all three cells:
    the naive membership sums are PV 42 / Model 21 / News 4, the counter reads 40 / 19 / 2,
    and the difference is exactly those two alphas. This settles the question left open in the
    project's `pyramid-multi-membership` note, in favour of the counter and against the
    "+1 to each of the three" reading.
    MECHANISM: UNKNOWN. n = 2, and both were submitted in the same 2026-07-23/25 batch, so
    "3 cells forfeits everything" is not separated from "these two alphas specifically", nor
    is ">= 3" separated from "== 3". What WOULD settle it: submit one 4-cell alpha, or one
    3-cell alpha from an unrelated family, and read pyramidThemes.effective.
    Until then this module treats >= 3 predicted cells as a REFUSAL, because the error is
    asymmetric: an irreversible submit that lands nowhere costs a whole daily slot.

R4  CONFIDENCE / REFUSAL. Any bare identifier in the formula that is neither a call target,
    nor a named parameter, nor a boolean literal, and that the catalog cannot resolve, makes
    the verdict UNKNOWN. An unresolved token is not "a field with no category" -- it is a
    field we failed to look up, and its category could be the very cell the alpha exists to
    fill. On the thin-catalog derivation this test caught 2 of 2 errors at a cost of 4/48
    refusals. The submitter MUST treat UNKNOWN as a refusal and never guess a category.

Usage:
    from tools.cell_map import cells_for, platform_cells
    v = cells_for(code, region="USA", delay=1, universe="TOP3000")
    if v.refuse: ...withhold...
    else: ...v.cells is the set of cells this submit would fill...

    python3 tools/cell_map.py "<formula>"        # one-off check from the shell
"""
from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The 16 pyramid categories, and the id the platform uses in a cell name "USA/D1/<ID>".
# Sourced from GET /users/self/activities/pyramid-alphas (211 rows, category.id + category.name).
CATEGORY_ID = {
    "Price Volume": "pv", "Model": "model", "Fundamental": "fundamental", "Option": "option",
    "Analyst": "analyst", "Other": "other", "Earnings": "earnings", "Risk": "risk",
    "Institutions": "institutions", "Macro": "macro", "News": "news", "Insiders": "insiders",
    "Sentiment": "sentiment", "Social Media": "socialmedia", "Short Interest": "shortinterest",
    "Imbalance": "imbalance",
}
ID_CATEGORY = {v: k for k, v in CATEGORY_ID.items()}

# Kept only as a fallback for catalogs thinner than the per-(region,universe,delay) dump; the
# ablation above shows it changes nothing when the matched dump is available.
RAW_PV = {"close", "open", "high", "low", "vwap", "volume", "returns", "adv20", "cap"}

# R3: the count of predicted cells at or above which the platform credited nothing.
FORFEIT_AT = 3

_CATALOGS: dict[str, dict[str, str]] = {}


def _load(path: pathlib.Path) -> tuple[dict[str, str], set[str]]:
    """Returns (field id -> category, ids whose type is GROUP).

    GROUP fields are tracked separately because of an UNTESTED edge: every classifier
    (sector, industry, subindustry, market, country, exchange) carries category
    "Price Volume" in the catalog, so `group_neutralize(x, industry)` alone would place a
    pure-Fundamental alpha in Price Volume too. Six ground-truth alphas use a classifier and
    all six matched -- but all six ALSO carry real price-volume data, so the classifier's own
    contribution is fully confounded and zero unconfounded cases exist. See CONFERRED_BY_GROUP.
    """
    out: dict[str, str] = {}
    group: set[str] = set()
    with open(path) as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            cat = d.get("category")
            if isinstance(cat, dict):
                cat = cat.get("name")
            if d.get("id") and cat:
                out.setdefault(d["id"], cat)
                if d.get("type") == "GROUP":
                    group.add(d["id"])
    return out, group


def catalog(region: str, delay: int, universe: str) -> tuple[dict[str, str], set[str], str, str]:
    """Field id -> category, plus the catalog's name and its confidence tier.

    "matched"  -- the dump for this exact (region, universe, delay); the tier R1 was measured on.
    "region"   -- same region and delay, a different universe. The 9 TOP1000 alphas in the
                  ground-truth set were scored against the TOP3000 dump and all 9 matched, so
                  this tier is not untested, but it is tested on one substitution only.
    "generic"  -- fetched/fields_all.jsonl + state/fieldmap.json, no region/delay filter. This
                  is the tier that scored 46/48; use it only when nothing better exists.
    """
    key = f"{region}_{universe}_d{delay}"
    if key not in _CATALOGS:
        exact = ROOT / f"fetched/rc/fields/{key}.jsonl"
        if exact.exists():
            m, g = _load(exact)
            _CATALOGS[key] = (m, g, key, "matched")
        else:
            sibs = sorted((ROOT / "fetched/rc/fields").glob(f"{region}_*_d{delay}.jsonl"))
            if sibs:
                m, g = _load(sibs[0])
                _CATALOGS[key] = (m, g, sibs[0].stem, "region")
            else:
                m, g = _load(ROOT / "fetched/fields_all.jsonl")
                try:
                    for fid, rec in json.load(open(ROOT / "state/fieldmap.json")).items():
                        if fid not in m and rec.get("category"):
                            m[fid] = rec["category"]
                except Exception:
                    pass
                _CATALOGS[key] = (m, g, "fields_all+fieldmap", "generic")
    return _CATALOGS[key]


def field_tokens(code: str) -> set[str]:
    """Bare identifiers that could be fields: not call targets, not named params, not literals.

    Matching on the name alone flags rank/ts_delta/add as unknown fields; every generated
    formula also ends in `filter=true`, so `filter` and `true` must go too. Checked against
    fetched/operators.json: none of the 67 operator names collides with a field id in the
    USA TOP3000 d1 catalog, so dropping call targets loses no field.
    """
    toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", code))
    called = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", code))
    params = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*=", code))
    return toks - called - params - {"true", "false"}


@dataclass(frozen=True)
class Verdict:
    cells: frozenset          # cells this alpha would be credited in, [] when it is credited nowhere
    predicted: frozenset      # cells its fields place it in, before the R3 forfeit rule
    confidence: str           # "high" | "low" | "unknown"
    unresolved: tuple         # tokens the catalog could not identify
    catalog: str              # which catalog answered, e.g. "USA_TOP3000_d1"
    reason: str

    @property
    def refuse(self) -> bool:
        """True when the submitter must withhold. UNKNOWN is a refusal, never a guess."""
        return self.confidence == "unknown"


def cells_for(code: str, region: str = "USA", delay: int = 1,
              universe: str = "TOP3000") -> Verdict:
    fc, group, name, tier = catalog(region, delay, universe)
    toks = field_tokens(code)
    cats = {fc[t] for t in toks if t in fc}
    if toks & RAW_PV:
        cats.add("Price Volume")
    unresolved = tuple(sorted(t for t in toks if t not in fc and t not in RAW_PV))
    # A category owed ENTIRELY to a GROUP classifier is the one untested case; see _load.
    solely_group = {c for c in cats
                    if {t for t in toks if t in fc and fc[t] == c} <= group
                    and not (c == "Price Volume" and toks & RAW_PV)}

    if unresolved:
        return Verdict(frozenset(), frozenset(cats), "unknown", unresolved, name,
                       f"{len(unresolved)} formula token(s) absent from catalog {name}; "
                       "an unidentified field may carry the very category this alpha targets")
    if not cats:
        return Verdict(frozenset(), frozenset(), "unknown", (), name,
                       "no field recognised in the formula -- category cannot be established")
    if len(cats) >= FORFEIT_AT:
        return Verdict(frozenset(), frozenset(cats), "unknown", (), name,
                       f"{len(cats)} cells; both 3-cell alphas on this account read "
                       "pyramidThemes.effective == 0 and were credited in NO cell (n=2, "
                       "MECHANISM UNKNOWN) -- withheld rather than spend a slot on nothing")
    conf = "high" if tier == "matched" else "low"
    note = (f"union of field categories over catalog {name} (tier {tier}); "
            f"fills {len(cats)} cell(s) with one submit")
    if solely_group:
        conf = "low"
        note += (f"; {sorted(solely_group)} is owed ONLY to a GROUP classifier token, and no "
                 "unconfounded ground-truth case exists for that -- treat the set as provisional")
    return Verdict(frozenset(cats), frozenset(cats), conf, (), name, note)


def platform_cells(alpha_json: dict) -> tuple[frozenset, int | None]:
    """The platform's OWN answer, from a GET /alphas/{id} or /users/self/alphas record.

    Returns (cells, effective). This is ground truth and outranks cells_for(); it is only
    available AFTER the alpha is submitted and has gone ACTIVE, which is why cells_for()
    exists at all. `effective` is the platform's count of cells actually credited -- it was 0
    for every 3-cell alpha observed, and equal to len(cells) otherwise.
    """
    cells = frozenset(ID_CATEGORY.get(p["name"].rsplit("/", 1)[-1].lower(),
                                      p["name"].rsplit("/", 1)[-1])
                      for p in (alpha_json.get("pyramids") or []))
    eff = (alpha_json.get("pyramidThemes") or {}).get("effective")
    return cells, eff


if __name__ == "__main__":
    import sys
    v = cells_for(sys.argv[1] if len(sys.argv) > 1 else "close")
    print(f"cells      : {sorted(v.cells) or '(none -- credited nowhere)'}")
    print(f"predicted  : {sorted(v.predicted)}")
    print(f"confidence : {v.confidence}{'   <-- REFUSE' if v.refuse else ''}")
    print(f"catalog    : {v.catalog}")
    if v.unresolved:
        print(f"unresolved : {list(v.unresolved)}")
    print(f"reason     : {v.reason}")
