#!/usr/bin/env python3
"""preflight.py <targets.json> — the gate that must pass BEFORE any simulation POST is made.

exit 0 = safe to launch. Any non-zero exit = abort, with the reason printed on stdout.

Nobody is watching the autoloop while it runs, so a defect that is merely annoying in an attended
session is unrecoverable here: platform rule G6 gives each alpha exactly ONE submit attempt ever,
and a batch that was already simulated burns POSTs that cannot be bought back. Every check below
exists because its failure mode is irreversible, not because it is tidy.

The ONLY network call is a read-only GET /users/self. Nothing here POSTs, simulates or submits.
"""
from __future__ import annotations
import glob, json, pathlib, pickle, re, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
ST = ROOT / "state"
API = "https://api.worldquantbrain.com"
MIN_FREE_GB = 2.0

TGT: pathlib.Path = None      # resolved path of the targets file under test
TARGETS: list = []            # its rows


# --------------------------------------------------------------------------- checks
def c_auth():
    """A dead cookie does not fail loudly downstream -- it fails as a batch of 401s that look like
    simulation errors, after the POSTs have already been spent."""
    import requests
    p = ST / "wq_cookies.pkl"
    if not p.exists():
        return False, "state/wq_cookies.pkl missing -- run tools/auth_only.py"
    s = requests.Session()
    c = pickle.load(open(p, "rb"))
    if isinstance(c, dict):
        s.cookies.update(c)
    else:
        for x in c:
            s.cookies.set_cookie(x)
    r = s.get(f"{API}/users/self", timeout=20)
    if r.status_code == 200:
        return True, "GET /users/self 200"
    return False, (f"GET /users/self {r.status_code} -- run tools/auth_only.py and tap the persona "
                   f"link in state/persona_url.txt")


def c_tests():
    p = ROOT / "tools/autoloop/test_pipeline.py"
    if not p.exists():
        return None, "tools/autoloop/test_pipeline.py does not exist yet -- SKIPPED"
    r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True, cwd=str(ROOT))
    tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
    return r.returncode == 0, (tail[-1][:200] if tail else f"rc={r.returncode}")


def c_validate():
    r = subprocess.run([sys.executable, str(ROOT / "tools/validate_targets.py"), str(TGT)],
                       capture_output=True, text=True, cwd=str(ROOT))
    out = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
    last = out[-1] if out else f"rc={r.returncode}"
    if r.returncode == 0:
        return True, last
    fails = [l for l in out if l.startswith("FAIL:")]
    return False, last + (" | " + " | ".join(f[:120] for f in fails[:3]) if fails else "")


def c_banned():
    """Banned fields are banned per-alpha for a reason the platform already enforced once."""
    d = json.load(open(ST / "banned_fields.json"))
    banned = set(d.get("banned_fields") or [])
    for v in (d.get("by_alpha") or {}).values():
        banned |= set(v)
    hits = []
    for t in TARGETS:
        toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", t.get("formula") or ""))
        bad = sorted(toks & banned)
        if bad:
            hits.append(f"{t.get('old_id')} uses {','.join(bad[:2])}")
    if hits:
        return False, f"{len(hits)}/{len(TARGETS)} formulas use banned fields -- " + "; ".join(hits[:3])
    return True, f"none of {len(TARGETS)} formulas touch the {len(banned)} banned fields"


def _key(t):
    """Formula + the settings that materially change the simulated alpha.

    Same distinguishing set as tools/validate_targets.py: maxPosition/maxTrade/selectionLimit/
    selectionHandling/lookback DO make a different alpha, pasteurization/unitHandling/nanHandling
    do not."""
    s = t.get("settings") or {}
    return (re.sub(r"\s+", "", t.get("formula") or ""),) + tuple(
        s.get(k) for k in ("region", "universe", "delay", "neutralization", "decay", "truncation",
                           "maxPosition", "maxTrade", "selectionLimit", "selectionHandling",
                           "lookback"))


def c_dupes():
    """Re-simulating a formula+settings pair that is already staged somewhere spends POSTs on an
    answer the journal already holds. validate_targets.py only globs state/*targets*.json and
    forgives rows that share an old_id with the batch; this walks state/** and forgives nothing
    except the file itself, because a batch staged under a second name has already been run."""
    hist = {}
    for p in glob.glob(str(ST / "**/*targets*.json"), recursive=True):
        if pathlib.Path(p).resolve() == TGT:
            continue
        try:
            rows = json.load(open(p))
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        for r in rows:
            if isinstance(r, dict) and r.get("formula"):
                hist.setdefault(_key(r), p)
    dups = [(t.get("old_id"), hist[_key(t)]) for t in TARGETS if _key(t) in hist]
    if dups:
        ex = "; ".join(f"{o} already in {pathlib.Path(p).relative_to(ROOT)}" for o, p in dups[:3])
        return False, f"{len(dups)}/{len(TARGETS)} rows are already-staged duplicates -- {ex}"
    return True, f"0/{len(TARGETS)} rows seen in {len(hist)} historical targets rows"


def c_disk():
    free = shutil.disk_usage(str(ROOT)).free / 2 ** 30
    return free > MIN_FREE_GB, f"{free:.1f} GB free (need > {MIN_FREE_GB} GB)"


def c_journal():
    """resim_results.jsonl is append-only and every downstream scorer reads it line by line. A
    half-written tail means the last simulation batch was lost mid-append."""
    p = ST / "resim_results.jsonl"
    if not p.exists():
        return False, "state/resim_results.jsonl missing"
    size = p.stat().st_size
    with open(p, "rb") as f:
        f.seek(max(0, size - 65536))
        lines = [l for l in f.read().splitlines() if l.strip()]
    if not lines:
        return False, "journal is empty"
    try:
        d = json.loads(lines[-1])
    except Exception as e:
        return False, f"last line does not parse ({e}) -- journal tail is truncated"
    return True, f"{size / 2 ** 20:.0f} MB, last line parses (old_id {d.get('old_id')})"


def c_budget():
    p = ST / "submit_budget.jsonl"
    if not p.exists():
        return True, "no state/submit_budget.jsonl yet (0 submits recorded)"
    n = 0
    for i, l in enumerate(open(p), 1):
        if not l.strip():
            continue
        try:
            json.loads(l)
        except Exception as e:
            return False, f"line {i} does not parse ({e}) -- the G6 budget would be miscounted"
        n += 1
    return True, f"{n} rows parse"


def c_op_limit():
    """FASTEXPR rejects any expression above 64 operators, and the failure is expensive twice over.

    It costs the dispatch (the row returns ERROR with no alpha id), and it costs the EXPERIMENT:
    operator cost is not uniform across structures -- an interaction leg is 4 operators where a
    plain rank leg is 1 -- so the limit silently deletes the LONGEST members of whichever arm is
    most operator-hungry. 220 of 1,096 interaction rows died this way on 2026-08-02, leaving every
    addition-vs-multiplication comparison in this project measured on a truncated arm."""
    import re as _re
    over = []
    for t in TARGETS:
        f = t.get("formula") or ""
        n = len(_re.findall(r"[A-Za-z_][A-Za-z0-9_]*\s*\(", f))
        if n > 64:
            over.append((t.get("old_id"), n))
    if over:
        ex = "; ".join(f"{o}={n}" for o, n in over[:3])
        return False, f"{len(over)}/{len(TARGETS)} rows exceed the 64-operator limit -- {ex}"
    return True, f"0/{len(TARGETS)} rows exceed the 64-operator limit"


CHECKS = [("auth", c_auth), ("test_pipeline", c_tests), ("validate_targets", c_validate),
          ("op_limit", c_op_limit),
          ("banned_fields", c_banned), ("duplicates", c_dupes), ("disk", c_disk),
          ("journal", c_journal), ("submit_budget", c_budget)]


# --------------------------------------------------------------------------- main
def main():
    global TGT, TARGETS
    if len(sys.argv) != 2:
        print("usage: preflight.py <targets.json>")
        return 2
    TGT = pathlib.Path(sys.argv[1]).resolve()
    try:
        TARGETS = json.load(open(TGT))
    except Exception as e:
        print(f"ABORT  targets file unreadable: {TGT} ({e})")
        return 2
    if not isinstance(TARGETS, list) or not TARGETS:
        print(f"ABORT  targets file is not a non-empty JSON list: {TGT}")
        return 2

    print(f"preflight {TGT.relative_to(ROOT) if ROOT in TGT.parents else TGT} -- {len(TARGETS)} targets")
    failed = []
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        print(f"{'PASS' if ok is True else 'SKIP' if ok is None else 'FAIL'}  {name}: {detail}")
        if ok is False:
            failed.append(name)

    if failed:
        print(f"PREFLIGHT ABORT -- {len(failed)} check(s) failed: {', '.join(failed)}. No POST made.")
        return 1
    print(f"PREFLIGHT OK -- safe to launch {len(TARGETS)} targets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
