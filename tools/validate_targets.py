#!/usr/bin/env python3
"""validate_targets.py <targets.json> — API-free pre-batch validator (ALPHA_PIPELINE.md C5).
Exit 0 = safe to cp into state/resim_targets.json. Any finding -> exit 1."""
import json, re, sys, glob, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ops = {o["name"] for o in json.load(open(ROOT / "fetched/rc/operators.json"))}
so = json.load(open(ROOT / "fetched/rc/settings_options.json"))
ch = so["actions"]["POST"]["settings"]["children"]
UNI = {r: [c["value"] for c in v] for r, v in ch["universe"]["choices"]["instrumentType"]["EQUITY"]["region"].items()}
NEU = {r: [c["value"] for c in v] for r, v in ch["neutralization"]["choices"]["instrumentType"]["EQUITY"]["region"].items()}
DLY = {r: [c["value"] for c in v] for r, v in ch["delay"]["choices"]["instrumentType"]["EQUITY"]["region"].items()}

def norm(f): return re.sub(r"\s+", "", f or "")
def key(t):
    s = t.get("settings") or {}
    return (norm(t.get("formula")), s.get("region"), s.get("universe"), s.get("delay"),
            s.get("neutralization"), s.get("decay"), s.get("truncation"),
            # maxPosition/maxTrade/selectionLimit/selectionHandling/lookback materially change the
            # simulated alpha (Khoa 2026-07-17), so they ARE distinguishing — a maxPosition=ON variant
            # is NOT a duplicate of the OFF one. (past/unit/nan stay non-distinguishing by design.)
            s.get("maxPosition"), s.get("maxTrade"), s.get("selectionLimit"),
            s.get("selectionHandling"), s.get("lookback"))

hist = set()
# audit 2026-07-24: a row can never be a duplicate of ITSELF — exclude the batch's own old_ids so a
# staged COPY of this batch (in resim_targets.json or a _r0 file) can't false-block the whole batch.
_batch_oids = {oid for t in json.load(open(sys.argv[1])) if isinstance(t, dict) and (oid := t.get("old_id"))}
for p in glob.glob(str(ROOT / "state/*targets*.json")) + glob.glob(str(ROOT / "state/resim_targets_*.bak")):
    if pathlib.Path(p).resolve() == pathlib.Path(sys.argv[1]).resolve(): continue
    try: rows = json.load(open(p))
    except Exception: continue
    if isinstance(rows, list):
        for r in rows:
            if isinstance(r, dict) and r.get("formula") and r.get("old_id") not in _batch_oids:
                hist.add(key(r))

def selfarg(f):
    # degenerate self-args in ANY paren group, incl nested/compound args op(g(x), g(x))
    # that the old flat regex missed. Splits each group at top-level commas and compares.
    n, i = len(f), 0
    while i < n:
        if f[i] == "(":
            depth, j, start, args = 1, i + 1, i + 1, []
            while j < n and depth:
                c = f[j]
                if c == "(": depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0: args.append(f[start:j])
                elif c == "," and depth == 1:
                    args.append(f[start:j]); start = j + 1
                j += 1
            na = [re.sub(r"\s+", "", a) for a in args if a.strip()]
            for a in range(len(na)):
                for b in range(a + 1, len(na)):
                    if na[a] and na[a] == na[b]: return na[a]
        i += 1
    return None

targets = json.load(open(sys.argv[1]))
errs, seen_oid, combos = [], set(), set()
CALL = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
for t in targets:
    oid, f, s = t.get("old_id"), t.get("formula") or "", t.get("settings") or {}
    tag = oid or t.get("id") or "?"
    if not oid or oid in seen_oid: errs.append(f"{tag}: missing/duplicate old_id")
    seen_oid.add(oid)
    # operators exact-case
    for fn in CALL.findall(f):
        if fn not in ops: errs.append(f"{tag}: operator '{fn}' not in RC allowlist (case-sensitive)")
    # empty-arg operator calls e.g. add() — no RC operator is nullary, so the platform rejects these
    for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\)", f):
        errs.append(f"{tag}: empty-arg call '{m.group(1)}()' — no operator is nullary")
    # balanced brackets
    depth = 0
    for c in f:
        depth += (c == "(") - (c == ")")
        if depth < 0: errs.append(f"{tag}: unbalanced ')'"); break
    if depth > 0: errs.append(f"{tag}: unbalanced '('")
    # semicolon statements: every defined var consumed, no bare unused statements
    parts = [p.strip() for p in f.split(";") if p.strip()]
    for i, p in enumerate(parts[:-1]):
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=", p)
        if not m: errs.append(f"{tag}: bare unused statement '{p[:40]}'")
        elif not any(re.search(rf"\b{m.group(1)}\b", q) for q in parts[i+1:]):
            errs.append(f"{tag}: variable '{m.group(1)}' defined but never consumed (case-sensitive)")
    # degenerate self-args e.g. op(x, x) — incl nested/compound op(g(x), g(x))
    _sa = selfarg(f)
    if _sa: errs.append(f"{tag}: degenerate self-args '{_sa}'")
    # settings enums
    reg = s.get("region")
    if s.get("instrumentType") != "EQUITY": errs.append(f"{tag}: instrumentType must be EQUITY")
    if reg not in UNI: errs.append(f"{tag}: bad region {reg}")
    else:
        if s.get("universe") not in UNI[reg]: errs.append(f"{tag}: universe {s.get('universe')} illegal for {reg}")
        if s.get("neutralization") not in NEU[reg]: errs.append(f"{tag}: neutralization {s.get('neutralization')} illegal for {reg}")
        if s.get("delay") not in DLY[reg]: errs.append(f"{tag}: delay {s.get('delay')} illegal for {reg}")
    if not (0 <= float(s.get("truncation", -1)) <= 1): errs.append(f"{tag}: truncation out of [0,1]")
    if not (0 <= int(s.get("decay", -1)) <= 512): errs.append(f"{tag}: decay out of [0,512]")
    combos.add((s.get("delay"), s.get("region"), s.get("universe")))
    # normalized-formula dedupe vs history
    if key(t) in hist: errs.append(f"{tag}: DUPLICATE formula+settings already in state/*targets*.json history")
if len(combos) > 1: errs.append(f"batch not homogeneous in (delay,region,universe): {combos}")
for e in errs: print("FAIL:", e)
print(f"{len(targets)} targets, {len(errs)} errors")
sys.exit(1 if errs else 0)
