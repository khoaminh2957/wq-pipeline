#!/usr/bin/env python3
"""One unattended cycle: screen -> gate -> correlate -> ABLATE -> present. No LLM, no submit.

This automates steps 2 and 3 of what still needed a human, and everything in step 4 EXCEPT the
irreversible POST. It deliberately stops one step short of submitting, and the reason is measured
rather than cautious:

  On 2026-08-11 `2rppNqbZ` satisfied every automatable condition the pipeline had — 17 checks, zero
  failures, ladder 2.06 over a 2.02 bar, fitness 1.26, prod-correlation 0.650 under the 0.70 line,
  predicted self-correlation 0.43, submit_safety conflict-free. Any auto-submitter with any
  threshold set would have posted it. Its ablations then showed the bare price carrier scoring
  sharpe 3.21 against the alpha's 2.18. A 403 spends an alpha permanently and there is one POST per
  alpha, so the failure is unrecoverable and the human gate stays.

What the cycle DOES do, every run:

  1. SCREEN new journal rows through the PnL screen (offline, uses cached curves).
  2. GATE them with tools/funnel/gates.zero_fail, recomputed from raw checks — never from a
     `zero_fail` field, which is None on rows nobody adjudicated and None is not False.
  3. CORRELATE survivors: production correlation against the live book, and predicted
     self-correlation against each other.
  4. ABLATE: queue each survivor's carrier-only and availability-only controls, and on the NEXT
     cycle judge them. A candidate that has not been ablated is UNDECIDED, and UNDECIDED never
     reaches the presented list.
  5. PRESENT what survived to Discord, with its ablation numbers, for a human to decide.

Everything it writes is a proposal. Nothing it writes is an action on the account.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
ST = ROOT / "state"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

PRESENTED = ST / "auto_presented.json"
CYCLE_LOG = ST / "auto_cycle.log"
PROD_CORR_MAX = 0.70          # the platform's own line
SELF_PRED_MAX = 0.70          # two candidates above this fill ONE slot, not two


def log(msg):
    line = f"[{time.strftime('%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(CYCLE_LOG, "a") as f:
        f.write(line + "\n")


def run(cmd, timeout=1800):
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def gate_passers():
    """Zero-fail rows, recomputed from raw checks. Never trusts a stored verdict."""
    from funnel import gates
    seen = {}
    with open(ST / "resim_results.jsonl", errors="ignore") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            aid = d.get("alpha")
            if aid and d.get("checks"):
                seen[aid] = d
    out = {}
    for aid, d in seen.items():
        ok, failed, missing = gates.zero_fail(d)
        if ok and not missing:
            out[aid] = d
    return out



PENDING_PRESENT = PRESENTED.parent / "auto_pending_present.json"


def _promote_delivered():
    """Mark as presented ONLY what the delivery ledger says actually went out.

    Two plain files and a lookup, no callback machinery. A message still in flight stays pending
    and is re-announced next cycle, which is the safe direction: a duplicate announcement costs a
    line, a lost one costs the alpha forever.
    """
    if not PENDING_PRESENT.exists():
        return
    try:
        pend = json.loads(PENDING_PRESENT.read_text())
    except Exception:
        return
    sent = set()
    ledger = pathlib.Path("/opt/wq/state/notify/sent.jsonl")
    if ledger.exists():
        for line in ledger.read_text(errors="ignore").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("result") == "sent" and r.get("msg_id"):
                sent.add(r["msg_id"])
    if not sent:
        return
    seen = already_presented()
    changed = False
    for mid in list(pend):
        if mid in sent:
            seen.update(pend.pop(mid).get("ids", {}))
            changed = True
    if changed:
        PRESENTED.write_text(json.dumps(seen, indent=1))
        PENDING_PRESENT.write_text(json.dumps(pend, indent=1))

def already_presented():
    try:
        return json.loads(PRESENTED.read_text())
    except Exception:
        return {}


LOCK = ST / "auto_cycle.lock"


def acquire_singleton():
    """One cycle at a time, or none. Returns the fd to hold, or None if another holds it.

    The timer fires every 2h but a cycle can outlast that: the screen step alone ran 14 minutes on
    2026-08-11 and grows with the backlog. Two concurrent cycles would both call the correlation
    endpoint against ONE account's 60 requests/minute and race on the same queue file.

    flock, not a pid file: the kernel releases an flock when the holder dies, so a cycle killed by
    OOM or a reboot cannot leave a stale lock that blocks every future run. `rm -f` on the lock
    FILE was what destroyed mutual exclusion in this repo once before -- unlinking does not release
    the lock a live holder is sitting on, it just gives the next process a different inode.
    """
    import fcntl
    fd = open(LOCK, "a+")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fd.close()
        return None
    return fd


def main():
    held = acquire_singleton()
    if held is None:
        log("another cycle holds state/auto_cycle.lock — exiting rather than double-running")
        return 0
    log("cycle start")

    # 1 + 2 ------------------------------------------------------------------------------------
    rc, out = run([sys.executable, "tools/harvest_pnl.py", "--limit", "400"], timeout=3600)
    log(f"screen rc={rc} {out.strip().splitlines()[-1] if out.strip() else ''}")

    passers = gate_passers()
    log(f"{len(passers)} zero-fail rows in the journal (recomputed from raw checks)")

    # 4b JUDGE any ablations that finished since the last cycle ----------------------------------
    import ablation_gate as AG
    verdicts = AG.judge()
    passed_abl = [a for a, v in verdicts.items() if v.get("verdict") == "PASS"]
    rejected = [a for a, v in verdicts.items() if v.get("verdict") == "REJECT"]
    undecided = [a for a, v in verdicts.items() if v.get("verdict") == "UNDECIDED"]
    log(f"ablation: {len(passed_abl)} pass, {len(rejected)} reject, {len(undecided)} undecided")

    # 3 CORRELATE the ablation survivors ---------------------------------------------------------
    presentable = []
    for aid in passed_abl:
        rc, out = run([sys.executable, "tools/fetch_prod_corr.py", aid], timeout=600)
        row = [l for l in out.splitlines() if l.startswith(aid)]
        if not row:
            log(f"  {aid}: prod-corr unreadable — NOT presentable (absent is not passing)")
            continue
        parts = row[0].split()
        try:
            prod = float(parts[1])
        except Exception:
            log(f"  {aid}: prod-corr unparseable — NOT presentable")
            continue
        if prod > PROD_CORR_MAX:
            log(f"  {aid}: prod-corr {prod} > {PROD_CORR_MAX} — rejected")
            continue
        presentable.append((aid, prod, verdicts[aid]))

    # 4c PRESENT — a proposal, never an action ---------------------------------------------------
    _promote_delivered()
    seen = already_presented()
    fresh = [(a, p, v) for a, p, v in presentable if a not in seen]
    if fresh:
        lines = ["**Candidates that survived the ablation gate** — human decision required, "
                 "nothing was submitted:"]
        for aid, prod, v in fresh:
            lines.append(f"`{aid}`  sharpe {v['sharpe_candidate']:.2f} vs carrier "
                         f"{v['sharpe_carrier_only']:.2f} / availability "
                         f"{v['sharpe_availability_only']:.2f}  ·  prod-corr {prod}")
        # NO submit command in the body. A notification must never carry an instruction that
        # spends an irreversible slot; the decision is Khoa's and it is made outside this channel.
        lines.append("Khong co lenh nop trong tin nay — quyet dinh nam ngoai kenh.")
        msg_id = None
        try:
            import sys as _sys
            _sys.path.insert(0, "/opt/wq/tools")
            import outbox as _OB
            msg_id = _OB.enqueue(
                kind="auto_cycle", channel="climb", cls="attention",
                blocks=[(0, "head", "{seq} " + "\n".join(lines))],
                dedup_key="autocycle:%s" % _OB.sha12("|".join(sorted(a for a, _, _ in fresh))))
            log(f"queued {len(fresh)} candidate(s) as {msg_id}")
        except Exception as e:
            log(f"ENQUEUE FAILED ({type(e).__name__}: {e}) -- candidates NOT queued")

        # DO NOT mark these presented yet.
        #
        # The old line ran OUTSIDE the try and unconditionally, so a failed post did not delay the
        # announcement -- it DELETED the alpha from every future one. Suppression is permanent and
        # silent, which is the worst possible pairing. The ids are parked against the message id
        # instead and promoted only once the delivery ledger shows result == "sent".
        if msg_id:
            try:
                pend = json.loads(PENDING_PRESENT.read_text()) if PENDING_PRESENT.exists() else {}
            except Exception:
                pend = {}
            pend[msg_id] = {"ts": time.time(),
                            "ids": {a: {"ts": time.time(), "prod_corr": p} for a, p, _ in fresh}}
            PENDING_PRESENT.write_text(json.dumps(pend, indent=1))
    else:
        log("nothing new survived the ablation gate this cycle")

    # 4a QUEUE ablations for gate-passers that have never been ablated ----------------------------
    need = [a for a in passers if a not in verdicts][:12]
    if need:
        rows, skipped = AG.build(need)
        if rows:
            q = ST / "simqueue" / "pool_ablation.json"
            q.parent.mkdir(parents=True, exist_ok=True)
            q.write_text(json.dumps(rows, indent=1))
            log(f"queued {len(rows)} ablation rows for {len(need)} candidates")
        for aid, why in skipped:
            log(f"  ablation skipped {aid}: {why}")
    log("cycle end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
