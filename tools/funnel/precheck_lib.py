#!/usr/bin/env python3
"""precheck_lib.py — ALPHA_PIPELINE v7 pre-sim mechanical checks, as pure Python.

Replaces the C5 "convert_validate_novelty" step of ALPHA_PIPELINE.md:
  1. novelty        — normalized formula + (fields,grammar) family vs simulated
                      history (state/resim_results.jsonl joined old_id->formula
                      through state/*targets*.json) and NO_GO / TESTED-NULL /
                      TESTED-REFUTED / debate_rejected families in
                      state/alpha_hypotheses.jsonl.
  2. duplicate guard — identical formula+settings 7-tuple within the batch or in
                      history. This is the SAME key validate_targets.py / the md
                      dedupe on, so config-sweep variants that differ only in
                      neutralization / decay / truncation are NOT rejected.
  3. settings legality — universe and neutralization legal for the region per
                      fetched/rc/settings_options.json (CHN=>TOP2000U,
                      JPN=>TOP1600|TOP1200 — never hardcoded, S10-19/S10-23),
                      0<=truncation<=1, and neutralization setting == group
                      used in group_neutralize(...).
  4. thin wrapper over tools/validate_targets.py (optional, run_validate=True).

When targets_path is given, that file is EXCLUDED from the history scan so a
batch already staged under state/ never flags itself as its own duplicate
(resumability, S10-24 — mirrors validate_targets.py).

Public API:
    precheck(targets, ...) -> {"ok": bool, "per_row_errors": {tag: [msg, ...]}}

No WQ API calls. History is read from local files only.
"""
import json, re, glob, subprocess, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

def _load_settings_options():
    """region -> legal universes / neutralizations, derived from the platform's
    own fetched/rc/settings_options.json (same source as validate_targets.py).
    Never hardcode these lists (S10-19/S10-23: JPN legally allows TOP1200 too)."""
    try:
        ch = json.load(open(ROOT / "fetched/rc/settings_options.json"))["actions"]["POST"]["settings"]["children"]
        by_reg = lambda node: {r: {c["value"] for c in v}
                               for r, v in node["choices"]["instrumentType"]["EQUITY"]["region"].items()}
        return by_reg(ch["universe"]), by_reg(ch["neutralization"])
    except Exception:
        return {"CHN": {"TOP2000U"}, "JPN": {"TOP1600", "TOP1200"}}, {}


REGION_UNIVERSE, REGION_NEUTRALIZATION = _load_settings_options()
# Neutralization-group tokens that may appear as a group arg (not data fields).
GROUP_TOKENS = {"market", "sector", "industry", "subindustry", "country", "exchange"}


def _load_banned():
    """Fields used in ANY submitted alpha are BANNED forever (standing self-correlation rule,
    Khoa 2026-07-24). Enforced HERE at the universal sim-launch gate so the ban holds for EVERY
    generator, not just strategy_lib (B10 O2). File absent -> empty (no bans yet). File PRESENT
    but corrupt -> json.load RAISES (fail-closed): silently returning empty would let a
    live-submitted field re-enter sim and the tap-submit reserve."""
    p = ROOT / "state/banned_fields.json"
    if not p.exists():
        return set()
    return set(json.load(open(p)).get("banned_fields", []))


BANNED = _load_banned()

_CALL = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_GN_CALL = re.compile(r"\bgroup_neutralize\s*\(")
_BARE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _split_top_args(s):
    """Split a call's argument string on top-level commas (respecting nested parens)."""
    args, depth, cur = [], 0, []
    for ch in s:
        if ch == "(":
            depth += 1; cur.append(ch)
        elif ch == ")":
            depth -= 1; cur.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(cur)); cur = []
        else:
            cur.append(ch)
    if cur:
        args.append("".join(cur))
    return [a.strip() for a in args]


def group_neutralize_groups(formula):
    """Return the group arg of every group_neutralize(signal, group) call.

    The group is the LAST top-level argument (top-level comma split, so a
    composite signal like divide(close,vwap) is not mistaken for the group).
    Only bare-identifier groups are returned — those are the ones the
    neutralization-setting match check compares against."""
    groups = []
    for m in _GN_CALL.finditer(formula or ""):
        i = m.end() - 1          # index of the '(' after group_neutralize
        depth = 0
        for j in range(i, len(formula)):
            if formula[j] == "(":
                depth += 1
            elif formula[j] == ")":
                depth -= 1
                if depth == 0:
                    args = _split_top_args(formula[i + 1:j])
                    if len(args) >= 2 and _BARE_IDENT.match(args[-1]):
                        groups.append(args[-1])
                    break
    return groups


def _load_ops():
    try:
        return {o["name"] for o in json.load(open(ROOT / "fetched/rc/operators.json"))}
    except Exception:
        return set()


OPS = _load_ops()


def norm(f):
    """Whitespace-insensitive normalization (matches validate_targets.py)."""
    return re.sub(r"\s+", "", f or "")


def key7(t):
    """formula+settings dedupe key — byte-identical to validate_targets.py:key().

    (norm_formula, region, universe, delay, neutralization, decay, truncation).
    Two rows are duplicates only if this whole 7-tuple matches; config-sweep
    variants that differ in neut/decay/truncation are therefore distinct."""
    s = t.get("settings") or {}
    return (norm(t.get("formula")), s.get("region"), s.get("universe"), s.get("delay"),
            s.get("neutralization"), s.get("decay"), s.get("truncation"),
            # maxPosition/maxTrade/selectionLimit/selectionHandling/lookback change the simulated alpha
            # (Khoa 2026-07-17) — a maxPosition=ON variant is NOT a dup of OFF. Sync w/ validate_targets.key().
            s.get("maxPosition"), s.get("maxTrade"), s.get("selectionLimit"),
            s.get("selectionHandling"), s.get("lookback"))


def extract_fields_grammar(formula):
    """Return (frozenset(field_ids), frozenset(grammar_ops)) for a FASTEXPR string."""
    f = formula or ""
    calls = set(_CALL.findall(f))
    grammar = frozenset(c for c in calls if c in OPS)
    fields = set()
    for m in _IDENT.finditer(f):
        tok = m.group(0)
        if tok in calls:            # operator / function name
            continue
        if tok in GROUP_TOKENS:     # neutralization group arg
            continue
        if tok in OPS:              # bare operator token (rare)
            continue
        fields.add(tok)
    return frozenset(fields), grammar


def _family(formula):
    fields, grammar = extract_fields_grammar(formula)
    return (fields, grammar)


def load_formula_history(state_dir, exclude_path=None, exclude_oids=None):
    """Scan every *targets*.json / .bak under state_dir.

    Returns (hist_keys:set[key7], oid_to_formula:dict). hist_keys is the same
    formula+settings 7-tuple corpus validate_targets.py dedupes against, so the
    two agree on what counts as a duplicate. exclude_path (the batch file being
    prechecked) is skipped so a staged batch never duplicates itself (S10-24).

    EXCLUDE BY OLD_ID TOO, added 2026-08-11. Path exclusion alone is not enough and
    validate_targets.py has known this since the 2026-07-24 audit: run_multisim STAGES the batch to
    state/resim_targets.json before launching, so by the time the precheck runs, the same rows exist
    at TWO paths. Excluding only the batch path let the staged copy of the batch duplicate the batch.
    Measured on the VPS 2026-08-11: pool_filter lost all 11 rows to
    "DUPLICATE formula+settings already in state/*targets*.json history", and pool_carrier then
    burned a whole launch the same way — every pool paid one failed launch before its retry.
    A row can never be a duplicate of ITSELF.
    """
    hist_keys = set()
    oid_to_formula = {}
    excl = pathlib.Path(exclude_path).resolve() if exclude_path else None
    skip_oids = set(exclude_oids or ())
    if not skip_oids and exclude_path:
        try:
            rows = json.load(open(exclude_path))
            skip_oids = {o for r in rows if isinstance(r, dict)
                         for o in (r.get("old_id") or r.get("id"),) if o}
        except Exception:
            skip_oids = set()
    patterns = [str(state_dir / "*targets*.json"), str(state_dir / "resim_targets_*.bak")]
    for p in sorted(set(g for pat in patterns for g in glob.glob(pat))):
        if excl and pathlib.Path(p).resolve() == excl:
            continue
        try:
            rows = json.load(open(p))
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            f = r.get("formula")
            if not f:
                continue
            oid = r.get("old_id") or r.get("id")
            if oid in skip_oids:
                continue          # this IS the batch, staged under another name
            hist_keys.add(key7(r))
            if oid:
                oid_to_formula[oid] = f
    return hist_keys, oid_to_formula


def load_tested_families(results_path, oid_to_formula):
    """Families (fields,grammar) of alphas actually SIMULATED (present in
    resim_results.jsonl) and joinable to a formula via oid_to_formula."""
    fams = set()
    try:
        lines = open(results_path)
    except Exception:
        return fams
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        oid = r.get("old_id")
        f = oid_to_formula.get(oid)
        if f:
            fams.add(_family(f))
    return fams


# md canonical NO_GO status set — EXACTLY these four markers. Deliberately does
# NOT match gate_fail (a per-gate diagnostic, not a hypothesis verdict) nor a
# bare "refut" substring. Word-bound (v7.1 fix, S10-6a): free text like
# "sign flip no good" must NOT match ('no go' inside 'no good' used to).
_NOGO_RE = re.compile(r"\b(?:NO[_-]?GO|TESTED[_-]?NULL|TESTED[_-]?REFUTED|debate_rejected)\b", re.I)
_LEAD_ID = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)")


def _roles_field_ids(roles):
    """Harvest field ids from a hypothesis `roles` value, handling BOTH shapes:
      A) {role: "field_id (dataset - desc)"}            -> leading token
      B) {role: [{"field_id": ..., ...}, ...]}          -> each field_id
    """
    ids = set()
    if not isinstance(roles, dict):
        return ids
    for v in roles.values():
        if isinstance(v, str):
            m = _LEAD_ID.match(v)
            if m and m.group(1) not in GROUP_TOKENS:
                ids.add(m.group(1))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict) and item.get("field_id"):
                    ids.add(item["field_id"])
    return ids


def load_nogo_families(hypotheses_path):
    """Field-combos of hypotheses marked NO_GO / TESTED-NULL / TESTED-REFUTED /
    debate_rejected. Returns a list of frozenset(field_ids). A target is a NO_GO
    reuse only if it CONTAINS the whole rejected combo (subset match) - a
    single-field root sweep is not nuked merely because a multi-field NO_GO
    mentions the root field."""
    fams = []
    try:
        lines = open(hypotheses_path)
    except Exception:
        return fams
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        status = str(r.get("status") or "")
        if not _NOGO_RE.search(status):
            continue
        ids = _roles_field_ids(r.get("roles"))
        if ids:
            fams.append(frozenset(ids))
    return fams


def build_nogo_list(hypotheses_path):
    """S4.1 {NOGO_LIST} builder (v6.2 L115 driver prose -> code, S10-10).

    Bank merge law: last-row-per-id with latest-NON-NULL per key (a later row's
    null/missing key never erases an earlier value), then keep rows whose merged
    status matches EXACTLY the four canonical markers (NO_GO / TESTED-NULL /
    TESTED-REFUTED / debate_rejected — word-bound _NOGO_RE, same regex as the
    precheck NO_GO family check, so harness and precheck can never disagree).
    Returns [{id, class, hypothesis, status}] in first-seen id order.
    """
    merged, order = {}, []
    try:
        lines = open(hypotheses_path)
    except Exception:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        rid = r.get("id")
        if not rid:
            continue
        if rid not in merged:
            merged[rid] = {}
            order.append(rid)
        for k, v in r.items():
            if v is not None:
                merged[rid][k] = v
    out = []
    for rid in order:
        m = merged[rid]
        status = str(m.get("status") or "")
        if _NOGO_RE.search(status):
            out.append({"id": rid, "class": m.get("class"),
                        "hypothesis": m.get("hypothesis"), "status": status})
    return out


def settings_legality(settings, formula, tag):
    errs = []
    s = settings or {}
    reg = s.get("region")
    uni = s.get("universe")
    if reg in REGION_UNIVERSE and uni not in REGION_UNIVERSE[reg]:
        errs.append(f"{tag}: universe {uni!r} illegal for {reg} (legal: {sorted(REGION_UNIVERSE[reg])})")
    neu_legal = REGION_NEUTRALIZATION.get(reg)
    if neu_legal and s.get("neutralization") not in neu_legal:
        errs.append(f"{tag}: neutralization {s.get('neutralization')!r} illegal for {reg}")
    trunc = s.get("truncation")
    try:
        if not (0 <= float(trunc) <= 1):
            errs.append(f"{tag}: truncation {trunc} out of [0,1]")
    except (TypeError, ValueError):
        errs.append(f"{tag}: truncation {trunc!r} not numeric")
    # neutralization setting must match the group used in group_neutralize(...)
    groups = set(group_neutralize_groups(formula or ""))
    if groups:
        neu = str(s.get("neutralization") or "").upper()
        for g in groups:
            if g.upper() != neu:
                errs.append(f"{tag}: formula group {g!r} != settings.neutralization {neu!r}")
    return errs


def precheck(targets, state_dir=None, results_path=None, hypotheses_path=None,
             run_validate=False, targets_path=None, sweep=False):
    """Run all pre-sim mechanical checks over a list of target rows.

    Returns {"ok": bool, "per_row_errors": {tag: [msg, ...]}}.
    A batch is ok iff no row has any error and the optional validate_targets
    wrapper (run_validate=True) exits 0. Pass targets_path whenever the batch
    is already staged on disk — it is excluded from the history scan (S10-24).

    sweep=True (Khoa 2026-07-17): SKIP the (fields,grammar) family-novelty block —
    a config sweep is a SANCTIONED same-root-field exploration (100/180 configs of
    ONE field), so "family already simulated" is expected, not a violation. Exact
    (formula+settings) dup, settings legality, intra-batch dup and the NO_GO ledger
    still apply, so identical configs and rejected fields are still blocked.
    """
    state_dir = pathlib.Path(state_dir) if state_dir else (ROOT / "state")
    results_path = results_path or (state_dir / "resim_results.jsonl")
    hypotheses_path = hypotheses_path or (state_dir / "alpha_hypotheses.jsonl")

    hist_keys, oid_to_formula = load_formula_history(state_dir, exclude_path=targets_path)
    tested_fams = load_tested_families(results_path, oid_to_formula)
    nogo_fams = load_nogo_families(hypotheses_path)

    per_row = {}

    def add(tag, msg):
        per_row.setdefault(tag, []).append(msg)

    batch_keys = {}  # key7 -> first tag (intra-batch duplicate guard)
    for i, t in enumerate(targets):
        tag = t.get("old_id") or t.get("id") or f"row{i}"
        errs = []
        formula = t.get("formula") or ""
        nf = norm(formula)
        k = key7(t)

        # settings legality
        errs += settings_legality(t.get("settings"), formula, tag)

        # duplicate formula+settings guard: intra-batch (7-tuple, not formula alone)
        if not nf:
            errs.append(f"{tag}: empty formula")
        elif k in batch_keys:
            errs.append(f"{tag}: DUPLICATE formula+settings of {batch_keys[k]} within batch")
        else:
            batch_keys[k] = tag

        # duplicate vs history (same 7-tuple)
        if nf and k in hist_keys:
            errs.append(f"{tag}: DUPLICATE formula+settings already in state/*targets*.json history")

        # novelty: (fields,grammar) family vs simulated history — SKIP in sweep mode
        fam = _family(formula)
        if nf and not sweep and fam in tested_fams:
            errs.append(f"{tag}: NOT NOVEL — (fields,grammar) family already simulated")

        # novelty: reuses the WHOLE field-combo of a NO_GO / tested-null hypothesis.
        # A SINGLE-field NO_GO requires an EXACT field-set match (ng == fields), not subset:
        # subset for a singleton degenerates to "formula merely CONTAINS that field", which would
        # nuke every novel multi-field combo (incl. carrier ensembles) reusing a lone tested-null
        # field — a yield-killer (B10 O1, Khoa 2026-07-24). Multi-field NO_GOs keep subset semantics.
        fields = fam[0]
        # banned-field gate (B10 O2): a field used in any SUBMITTED alpha is banned forever. Enforced
        # here so EVERY generator (not just strategy_lib) is ban-safe. Reuses the extracted field set.
        if fields:
            banned_hit = sorted(BANNED & fields)
            if banned_hit:
                errs.append(f"{tag}: BANNED field(s) {banned_hit} (live-submitted; standing self-corr rule)")
        if fields:
            for ng in nogo_fams:
                if not ng:
                    continue
                hit = (ng == fields) if len(ng) == 1 else ng.issubset(fields)
                if hit:
                    errs.append(f"{tag}: NO_GO family — reuses rejected field-combo {sorted(ng)}")
                    break

        for e in errs:
            add(tag, e)

    ok = len(per_row) == 0

    # thin wrapper over validate_targets.py (optional)
    if run_validate:
        if not targets_path:
            add("_validate", "run_validate=True but no targets_path given")
            ok = False
        else:
            r = subprocess.run([sys.executable, str(ROOT / "tools/validate_targets.py"), str(targets_path)],
                               capture_output=True, text=True)
            if r.returncode != 0:
                for ln in r.stdout.splitlines():
                    if ln.startswith("FAIL:"):
                        add("_validate", ln)
                if not any(kk == "_validate" for kk in per_row):
                    add("_validate", f"validate_targets exit {r.returncode}")
                ok = False

    return {"ok": ok, "per_row_errors": per_row}


if __name__ == "__main__":
    tgts = json.load(open(sys.argv[1]))
    out = precheck(tgts, run_validate=("--validate" in sys.argv), targets_path=sys.argv[1])
    print(json.dumps(out, indent=2))
    sys.exit(0 if out["ok"] else 1)
