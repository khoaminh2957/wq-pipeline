#!/usr/bin/env python3
"""harness/guards.py — MECHANICAL enforcement of the standing rules the violations audit proved
were broken by discipline alone (harness/data/violations_report.json, 31 confirmed). Guards, not
promises. Called by batch assembly + launch; a violating batch REFUSES to fire.

Rules enforced:
  G1 always-90: batch must be exactly 90 rows (auto-pad hook available upstream).
  G2 family quota: <=40% of a batch from one dataset family.
  G3 hypothesis-required: every row carries a >=100-char hypothesis referencing its mechanism.
  G4 degenerate veto: identical-argument subtrees (subtract(x,x) / spread(a,a)) rejected.
  G5 prefix-unique: old_id prefix must not already exist in resim_results.jsonl (immutability).
  G6 submit budget: max 1 submit POST per alpha EVER (poll-only after), 1 submit-test/family/day.
  G7 corr batching: prod-corr measured in rolling batches <=10 concurrent.
Usage: from harness.guards import check_batch; check_batch(rows) -> raises on violation.
"""
import json, re, collections, pathlib, datetime, fcntl, contextlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# operator + structural tokens are NOT dataset families — skip them so _famof returns a real field.
_SKIP = {"rank","ts_delta","ts_zscore","ts_mean","ts_decay_linear","ts_backfill","ts_rank","ts_std_dev",
         "ts_av_diff","group_neutralize","group_rank","group_backfill","signed_power","vector_neut",
         "zscore","normalize","quantile","winsorize","scale","reverse","subtract","multiply","divide",
         "if_else","trade_when","days_from_last_change","vec_avg","ts_arg_min","ts_corr","densify",
         "sector","industry","subindustry","market","country","filter"}
def _famof(formula):
    for m in re.finditer(r"[a-z][a-z0-9_]{4,}", formula):
        t = m.group(0)
        if formula[m.end():m.end() + 1] == "(": continue   # function call = operator, not a dataset field
        if t in _SKIP: continue
        return t.split("_")[0]                      # first real field token's family prefix
    return "?"

def check_batch(rows, require_hypothesis=True):
    errs = []
    # G1 always-90
    if len(rows) != 90:
        errs.append(f"G1 always-90: batch has {len(rows)} rows (must be exactly 90)")
    # G2 family quota
    fams = collections.Counter(r.get("_ds") or _famof(r["formula"]) for r in rows)
    for fam, n in fams.items():
        if n > 0.4 * max(len(rows), 1):
            errs.append(f"G2 family-quota: {fam} has {n}/{len(rows)} rows (>40%)")
    # G3 hypothesis
    if require_hypothesis:
        missing = [r["old_id"] for r in rows if len(str(r.get("_hypothesis") or "")) < 100]
        if missing:
            errs.append(f"G3 hypothesis-required: {len(missing)} rows missing >=100-char hypothesis (e.g. {missing[:3]})")
    # G4 degenerate subtrees
    for r in rows:
        f = re.sub(r"\s", "", r["formula"])
        for m in re.finditer(r"(subtract|divide|ts_corr)\(([^,()]+(?:\([^()]*\))?),\2\)", f):
            errs.append(f"G4 degenerate: {r['old_id']} has {m.group(1)}(x,x)")
    # G5 prefix-unique
    prefixes = {re.match(r"([a-z0-9]+_)", r["old_id"]).group(1) for r in rows if re.match(r"([a-z0-9]+_)", r["old_id"])}
    seen_prefixes = set()
    rr = ROOT / "state/resim_results.jsonl"
    if rr.exists():
        for line in open(rr):
            m = re.search(r'"old_id":\s*"([a-z0-9]+_)', line)
            if m: seen_prefixes.add(m.group(1))
    clash = prefixes & seen_prefixes
    if clash:
        errs.append(f"G5 prefix-unique: prefix(es) {sorted(clash)} already in resim history")
    if errs:
        raise SystemExit("BATCH REFUSED by guards:\n  - " + "\n  - ".join(errs))
    return True

# G6 submit budget ledger
SUB = ROOT / "state/submit_budget.jsonl"


def _platform_date():
    """Today in the PLATFORM's day (US Eastern). Mirrors tools/daily_budget.platform_date();
    duplicated rather than imported so harness/ keeps no dependency on tools/."""
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def submit_allowed(alpha_id, family):
# The platform counts submissions per US EASTERN day. This ledger counted per LOCAL day, which
# cost le391QLA and Vk35LRM0 their one-shot G6 slots to 403s on 2026-07-30; it was then moved to
# UTC, which only SHRANK the hole from seven hours to four. Between 00:00 and 04:00 UTC
# (07:00-11:00 local) the UTC date has rolled over and the platform's has not, so the ledger still
# reads "0 used" against a quota already at 4/4 -- measured 2026-08-02 at 03:20 UTC, reading 0
# against a platform 4/4. A 403 permanently spends the alpha, so this must match the platform
# exactly. zoneinfo, not a hardcoded -4, because the offset changes at the EST/EDT switch.
    today = _platform_date()
    posts = fam_today = 0
    if SUB.exists():
        for line in open(SUB):
            try:
                r = json.loads(line)
                if r["alpha"] == alpha_id: posts += 1
                if r["family"] == family and r["date"] == today: fam_today += 1
            except (ValueError, KeyError):        # malformed/incomplete ledger line -> skip, never crash the gate
                continue
    if posts >= 1: return False, f"alpha {alpha_id} already had its 1 submit POST (poll-only now)"
    if fam_today >= 1: return False, f"family {family} already had its submit-test today"
    return True, "ok"

def record_submit(alpha_id, family):
    with open(SUB, "a") as f:
        f.write(json.dumps({"alpha": alpha_id, "family": family,
                            "date": _platform_date()}) + "\n")

# TOCTOU fix: check-then-record must be ATOMIC across concurrent submit processes, else two runs
# both read posts=0 and both POST -> double real-money submit. An exclusive file lock serializes them.
_SUB_LOCK = ROOT / "state/submit_budget.lock"
@contextlib.contextmanager
def _budget_lock():
    _SUB_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(_SUB_LOCK, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(lf, fcntl.LOCK_UN)

def reserve_submit(alpha_id, family):
    """ATOMIC G6 gate. Under an exclusive lock: check the budget and, if allowed, record the reservation
    BEFORE the POST so two concurrent runs can't both pass. Returns (ok, why). If the POST is then
    rejected (4xx = no submission created), call release_submit(alpha_id) to give the budget back."""
    with _budget_lock():
        ok, why = submit_allowed(alpha_id, family)
        if ok:
            record_submit(alpha_id, family)
        return ok, why

def slot_returnable(status, body=""):
    """May the G6 one-shot slot be handed back after this response? THE single implementation.

    A 4xx does NOT uniformly mean "no submission was created". Under G6 an alpha gets one POST
    ever, and a 403 is the platform ADJUDICATING that POST and rejecting it — the attempt is spent
    and the alpha is permanently dead. Releasing the slot on a 403 made six alphas (pwKZl6Zg,
    O0xVZpVd, Vk35PY2J, vRvNrZXw, gJ98Vqjl, N1R7AKN8) read as submittable again: all six sit in
    state/funnel/submit_log.jsonl with a 403 and none in submit_budget.jsonl. Re-POSTing them
    spends one of the ~4 real daily slots on an alpha that can never be accepted.

    Only 429 (throttled, never adjudicated) and 408 (never answered) return the slot, plus one
    carve-out: a 403 whose checks contain ERROR results and not a single FAIL is the platform
    failing to COMPUTE rather than judging the alpha. P0OLx0zp was 403'd on 2026-08-01 with a lone
    PROD_CORRELATION:ERROR during a rate-ban and measured prod 0.6549 minutes later.

    Audited 2026-08-09: submit_alphas.py had this rule; wq_client.py:282, tools/gentle_submit.py,
    tools/complete_submit.py and tools/deploy_greenlight.py all still released on ANY 4xx. A
    reproduction drove a real client through 403 -> release -> a SECOND POST at the same alpha.
    Four copies of a rule is how four of them stay wrong; this is the one copy.
    """
    if status in (408, 429):
        return True
    if status != 403:
        return False
    try:
        j = json.loads(body or "")
    except Exception:
        return False
    results = [c.get("result") for sec in j.values() if isinstance(sec, dict)
               for c in sec.get("checks", []) if isinstance(c, dict)]
    return "ERROR" in results and "FAIL" not in results


def release_submit(alpha_id):
    """Undo the most-recent reservation for alpha_id (its POST was rejected 4xx -> nothing was submitted).
    Rewrites the ledger without that one line, under the same lock."""
    with _budget_lock():
        if not SUB.exists(): return
        lines = SUB.read_text().splitlines()
        for i in range(len(lines) - 1, -1, -1):
            try:
                if json.loads(lines[i]).get("alpha") == alpha_id:
                    del lines[i]; break
            except ValueError:
                continue
        SUB.write_text(("\n".join(lines) + "\n") if lines else "")

if __name__ == "__main__":
    import sys
    rows = json.load(open(sys.argv[1]))
    check_batch(rows, require_hypothesis="--no-hyp" not in sys.argv)
    print(f"batch OK: {len(rows)} rows pass guards G1-G5")
