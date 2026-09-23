#!/usr/bin/env python3
"""knowledge.py — the alpha-loop's self-improving memory. Every successful run writes what
it learned; every run reads it back so the skill gets better each time:

  - proven WINNERS (zero-fail) become round-0 SEEDS on the next run of that dataset,
  - per-(dataset,template) SIGN is learned -> known-negative mechanics are pre-flipped,
  - per-dataset GOOD vs DEAD fields bias / prune field selection,
  - best SETTINGS (neut, decay) seed the sweep.

Stored at tools/alpha_loop/knowledge.json (human-inspectable, git-tracked).
"""
from __future__ import annotations
import json, os, pathlib, re, fcntl, contextlib

KB = pathlib.Path(__file__).resolve().parent / "knowledge.json"
LOCK = KB.with_suffix(".lock")

def _blank():
    return {"version": 1, "datasets": {}}

def load() -> dict:
    if KB.exists():
        try:
            return json.loads(KB.read_text())
        except json.JSONDecodeError:
            # A non-empty file that fails to parse is a corrupt/torn write, NOT an
            # empty KB. Silently returning _blank() here would let the next save()
            # overwrite all accumulated knowledge with a blank file. Preserve the
            # bad file for inspection and refuse to proceed.
            if KB.stat().st_size > 0:
                bad = KB.with_suffix(".corrupt")
                with contextlib.suppress(OSError):
                    os.replace(KB, bad)
                raise RuntimeError(
                    f"knowledge.json is corrupt (moved to {bad.name}); refusing to "
                    "overwrite learned memory with a blank KB")
    return _blank()

def save(k: dict):
    # Atomic write: dump to a temp file in the same dir, fsync, then os.replace().
    # An interrupted/crashing dump leaves the temp file (discarded), never a
    # truncated knowledge.json, and concurrent readers see either the old or new
    # file whole -- never a partial one.
    tmp = KB.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(k, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, KB)

@contextlib.contextmanager
def _locked():
    """Serialize the read-modify-write in record_run across concurrent loop.py
    processes so parallel runs can't clobber each other (lost update)."""
    with open(LOCK, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)

def _ds(k, dataset):
    return k["datasets"].setdefault(dataset, {
        "runs": 0, "winners": [], "template_stats": {}, "sign_flips": {},
        "good_fields": {}, "dead_fields": {}, "best_settings": None})

def _fields(formula: str):
    # A token immediately followed by "(" is an operator/function call, not a field, so gate on
    # that instead of a hand-maintained op blocklist (which went stale — zscore/signed_power/
    # ts_decay_linear/ts_av_diff/ts_std_dev/ts_delay all leaked in as fake fields). `grp` catches
    # the non-call literals/keywords fields never use (notably `filter`/`true` from add(..., filter=true)).
    grp = {"true", "false", "filter", "sector", "industry", "subindustry", "market", "country", "std"}
    out = set()
    for m in re.finditer(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", formula):
        t = m.group()
        if formula[m.end():].lstrip()[:1] == "(":   # call -> operator, skip
            continue
        if t not in grp:
            out.add(t)
    return out

def _template_of(oid_or_tag: str, dataset: str = "") -> str:
    # oid = al_<run>_r<rnd>_<ds6>_<rawtag...>_<idx>  (rawtag from strategy_lib may contain '_';
    # refine rows have a bare tag flip/valve/sweep with no <ds6> prefix). The stored key must equal
    # the RAW generator tag that strategy_lib.gen_strategies queries via sign_flip_for, so strip the
    # al_<run>_r<rnd> frame, the trailing <idx>, AND the <ds6> prefix. tag form = <ds6>_<template>.
    parts = oid_or_tag.split("_")
    # run = <tag>_<time>_<pid> is THREE tokens, so the r<rnd> frame token is not at a fixed index;
    # scan for it instead of hardcoding parts[2] (which is the time digits and never starts with 'r').
    # anchor the frame on the run's <time>_<pid> tail (two all-digit tokens, always present) so a
    # --tag that itself matches r<digits> (e.g. 'r5') can't be picked up as the frame token.
    ri = next((i for i, p in enumerate(parts)
               if re.fullmatch(r"r\d+", p) and i >= 2
               and parts[i - 1].isdigit() and parts[i - 2].isdigit()), None)
    if parts[0] == "al" and ri is not None and ri + 1 <= len(parts) - 2:
        mid = "_".join(parts[ri + 1:-1])                # <ds6>_<rawtag>  (or bare tag for refine rows)
        pref = (dataset[:6] + "_") if dataset else ""
        return mid[len(pref):] if pref and mid.startswith(pref) else mid
    return parts[1] if len(parts) >= 2 else "?"

# refine_rows (loop.py) mints oids with these BARE pseudo-tags (no <ds6> prefix). They are NOT
# mechanic templates: gen_strategies only ever queries sign_flip_for with the mechanic tags it emits
# (rev/ovr/zrev/mom/div/rrev/sfade/sride/ens*), so any template_stats/sign_flips keyed on these would
# be write-only dead memory. Refine rounds still contribute WINNERS + good/dead FIELDS below.
_REFINE_TAGS = {"flip", "valve", "sweep"}

def record_run(dataset: str, recs: list):
    """recs: list of dicts from loop.classify (oid, formula, settings, sh, ft, tv, cls)."""
    with _locked():
      k = load(); d = _ds(k, dataset); d["runs"] += 1
      # flip state in effect when THIS batch was generated (captured before the recompute below), so
      # template sign-stats accumulate in the template's NATURAL sign frame (B10 O5).
      engaged = dict(d.get("sign_flips", {}))
      for r in recs:
        sh = r.get("sh")
        if not isinstance(sh, (int, float)): continue
        tmpl = _template_of(r["oid"], dataset)
        if tmpl not in _REFINE_TAGS:   # skip refine pseudo-tags: sign learning on them is never read back
            st = d["template_stats"].setdefault(tmpl, {"pos": 0, "neg": 0, "best_sh": -9, "n": 0})
            st["n"] += 1
            # if the flip was engaged, the emitted formula was reverse(BASE) so its natural-sign
            # sharpe is -sh; without this, a WORKING flip's own positive result raises best_sh>=0.5
            # and un-learns the flip, reverting round-0 to the losing sign (B10 O5).
            sh_nat = -sh if engaged.get(tmpl) else sh
            if sh_nat > 0: st["pos"] += 1
            elif sh_nat < 0: st["neg"] += 1
            st["best_sh"] = max(st["best_sh"], sh_nat)
        # field quality: strong |sh| -> good; near-zero -> dead
        for f in _fields(r["formula"]):
            if abs(sh) >= 0.8: d["good_fields"][f] = d["good_fields"].get(f, 0) + 1
            elif abs(sh) < 0.3: d["dead_fields"][f] = d["dead_fields"].get(f, 0) + 1
        # winners
        if r.get("cls") == "ZERO_FAIL":
            d["winners"].append({"formula": r["formula"].strip(), "settings": r["settings"],
                                 "sh": sh, "ft": r.get("ft"), "alpha": r.get("alpha")})
            d["best_settings"] = {"neut": r["settings"]["neutralization"], "decay": r["settings"]["decay"]}
      # learn sign per template: if a template is negative-dominant, mark it as needing a flip
      for tmpl, st in d["template_stats"].items():
          if st["n"] >= 3:
              d["sign_flips"][tmpl] = st["neg"] > st["pos"] and st["best_sh"] < 0.5
      # dedup + cap winners (keep best 8 by sharpe)
      d["winners"] = sorted({w["formula"]: w for w in d["winners"]}.values(),
                            key=lambda w: -(w["sh"] or 0))[:8]
      save(k)
    return k

# ---- queries used by the generator ---------------------------------------------------
def seeds_for(dataset: str, k: dict | None = None) -> list:
    k = k or load()
    d = k["datasets"].get(dataset)
    return list(d["winners"]) if d else []

def sign_flip_for(dataset: str, template: str, k: dict | None = None) -> bool:
    k = k or load()
    d = k["datasets"].get(dataset) or {}
    return bool(d.get("sign_flips", {}).get(template))

def field_prefs(dataset: str, k: dict | None = None):
    k = k or load()
    d = k["datasets"].get(dataset) or {}
    good = {f for f, c in d.get("good_fields", {}).items() if c >= 2}
    dead = {f for f, c in d.get("dead_fields", {}).items()
            if c >= 3 and f not in d.get("good_fields", {})}
    return good, dead

def summary() -> str:
    k = load(); lines = []
    for ds, d in sorted(k["datasets"].items()):
        w = d.get("winners", [])
        best = f"best zero-fail sh={w[0]['sh']}" if w else "no zero-fail yet"
        flips = [t for t, v in d.get("sign_flips", {}).items() if v]
        lines.append(f"{ds}: {d['runs']} run(s), {len(w)} winner(s), {best}"
                     + (f", flip templates={flips}" if flips else ""))
    return "\n".join(lines) or "(empty)"

if __name__ == "__main__":
    print(summary())
