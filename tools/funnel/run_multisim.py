#!/usr/bin/env python3
"""run_multisim — 10x10 multi-sim launcher wrapper around tools/resim_bulk.py.

ALPHA_PIPELINE v7 funnel. Given a stage targets file with N homogeneous rows
(fixed universe/delay/region), it:
  1. plans the multi-sim batches by REPLICATING resim_bulk's grouping logic
     (sort by (delay,region,universe,-len(formula)) then greedily pop up to
     BATCH rows sharing the same (delay,region,universe) key),
  2. --dry-run: asserts the plan yields exactly ceil(N/BATCH) multi-sim POSTs
     and that every batch is homogeneous — WITHOUT calling the WQ API,
  3. live (default): runs the BLOCKING C6 precheck (precheck_lib novelty/dupe/
     legality + tools/validate_targets.py) — any finding means ZERO POSTs
     (S10-20/22: v6.2 blocking validate restored) — then copies the file to
     state/resim_targets.json, launches resim_bulk.py (which POSTs one multi-sim
     per <=BATCH homogeneous children, => ceil(N/BATCH) POSTs), and blocks until
     all N ids are journaled, with a stall ceiling: if the journal makes no
     progress for --stall-timeout seconds the wrapper terminates resim_bulk and
     FAILs instead of looping forever (S10-11/12 wrapper side; the manual-break
     rule is retired for this path).

The live launch is INTEGRATION-RUN-BY-OPERATOR (single-stream account rule);
subagents run only --dry-run. This wrapper does NOT re-implement the API client.
"""
from __future__ import annotations
import argparse, json, math, pathlib, re, subprocess, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import precheck_lib  # noqa: E402  (sibling module; blocking C6 gate)

ROOT = pathlib.Path("/Users/kanenguyen/wq_pipeline")
ST = ROOT / "state"
RESIM_BULK = ROOT / "tools" / "resim_bulk.py"
RESULTS = ST / "resim_results.jsonl"
TARGETS_LIVE = ST / "resim_targets.json"


def _read_batch_const() -> int:
    """Derive BATCH from resim_bulk.py source so grouping stays in lock-step (no drift)."""
    m = re.search(r"^BATCH\s*=\s*(\d+)", RESIM_BULK.read_text(), re.M)
    if not m:
        raise SystemExit("could not parse BATCH from tools/resim_bulk.py")
    return int(m.group(1))


def _gkey(a: dict):
    """Multi-sim homogeneity key — identical to resim_bulk.gkey()."""
    s = a.get("settings") or {}
    return (s.get("delay"), s.get("region"), s.get("universe"))


def plan_batches(targets: list, batch: int) -> list:
    """Replicate resim_bulk's sort + greedy same-key pop. One batch == one POST."""
    src = sorted(
        targets,
        key=lambda a: ((a.get("settings") or {}).get("delay", 1),
                       (a.get("settings") or {}).get("region", ""),
                       (a.get("settings") or {}).get("universe", ""),
                       -len(a.get("formula") or "")),
    )
    batches = []
    i = 0
    while i < len(src):
        k0 = _gkey(src[i])
        group = []
        while i < len(src) and len(group) < batch and _gkey(src[i]) == k0:
            group.append(src[i]); i += 1
        batches.append(group)
    return batches


def dry_run(targets_path: pathlib.Path) -> bool:
    """Plan-only verification. Prints PASS/FAIL. Returns True on PASS."""
    batch = _read_batch_const()
    targets = json.load(open(targets_path))
    n = len(targets)
    batches = plan_batches(targets, batch)
    expected_posts = math.ceil(n / batch)

    ok = True
    reasons = []
    if len(batches) != expected_posts:
        ok = False
        reasons.append(f"POST count {len(batches)} != ceil({n}/{batch})={expected_posts}")
    # every batch must be homogeneous and within cap
    for bi, g in enumerate(batches):
        if len(g) > batch:
            ok = False; reasons.append(f"batch {bi} oversized ({len(g)}>{batch})")
        if len({_gkey(a) for a in g}) != 1:
            ok = False; reasons.append(f"batch {bi} not homogeneous")
    # ids must all be accounted for exactly once
    if sum(len(g) for g in batches) != n:
        ok = False; reasons.append("row count lost in batching")

    sizes = [len(g) for g in batches]
    distinct_keys = sorted({_gkey(a) for a in targets})
    print(f"targets={n} BATCH={batch} planned_posts={len(batches)} "
          f"expected_posts={expected_posts} batch_sizes={sizes} "
          f"distinct_(delay,region,universe)={distinct_keys}")
    if ok:
        print(f"PASS: {n} rows -> {len(batches)} multi-sim POSTs "
              f"({'x'.join(str(s) for s in sizes) if len(set(sizes))>1 else f'{len(sizes)}x{sizes[0]}' if sizes else '0'})")
    else:
        print("FAIL: " + "; ".join(reasons))
    return ok


TERMINAL_STATUS = {"COMPLETE", "ERROR", "EXPIRED", "WARNING"}


def _terminal(j) -> bool:
    """Has the platform finished with this row, whatever the verdict?

    The previous rule was `status == "COMPLETE" or alpha or retried`, which reads an ERRORED
    simulation as UNFINISHED. It is finished — it errored. Measured over the live journal:
    COMPLETE 60,116 / ERROR 8,363 / EXPIRED 40 / WARNING 29, and 5,667 rows carry no alpha, no
    COMPLETE and no retried flag, so any batch containing one could never satisfy
    `done >= len(target_ids)`.

    That mattered little while the wrapper's exit code was discarded. It matters now: _block_until_done
    ends in `return scan() >= len(target_ids)`, run_multisim turns False into exit 1, and tools/simq.sh
    (fixed 2026-08-08 to stop swallowing exit codes) then has tools/simfeed.sh quarantine the pool into
    state/simfailed/. A batch that ran perfectly except for one errored alpha would be filed as a
    failure. Waiting on an errored row to become un-errored is not patience, it is a hang.
    """
    return (j.get("status") in TERMINAL_STATUS or bool(j.get("alpha"))
            or bool(j.get("retried")))


def _journaled_ids(target_ids: set, results_path: pathlib.Path = RESULTS) -> set:
    """ids in the results journal that belong to this stage and reached a terminal row."""
    if not results_path.exists():
        return set()
    seen = set()
    for line in open(results_path):
        try:
            j = json.loads(line)
        except Exception:
            continue
        oid = j.get("old_id")
        # a genuinely terminal row counts as done: COMPLETE, or has an alpha, or retry-exhausted
        # (matches resim_bulk's own done-set so the wrapper never FAILs a stage resim_bulk finished).
        if oid in target_ids and _terminal(j):
            seen.add(oid)
    return seen


class _JournalScanner:
    """Stateful incremental scanner over the results journal for the poll loop.

    Same terminal-row semantics as _journaled_ids, but reads only newly-appended
    bytes each scan (seek to the saved offset) instead of full-parsing the whole
    (34MB+, append-only) journal every poll. Handles truncation/rotation and
    mid-write partial trailing lines.
    """
    def __init__(self, target_ids: set, results_path: pathlib.Path = RESULTS):
        self.t = target_ids
        self.p = results_path
        self.off = 0
        self.ino = None
        self.seen: set = set()
        self.buf = b""

    def scan(self) -> set:
        if not self.p.exists():
            return self.seen
        st = self.p.stat()
        # truncation (shrunk) or rotation (inode changed) => restart clean from 0
        if st.st_size < self.off or (self.ino is not None and st.st_ino != self.ino):
            self.off = 0; self.buf = b""; self.seen = set()
        self.ino = st.st_ino
        if st.st_size == self.off:
            return self.seen
        with open(self.p, "rb") as f:
            f.seek(self.off)
            chunk = f.read()
            self.off = f.tell()
        data = self.buf + chunk
        nl = data.rfind(b"\n")
        if nl == -1:                       # no complete line yet — carry partial
            self.buf = data
            return self.seen
        complete, self.buf = data[:nl], data[nl + 1:]   # keep incomplete tail for next scan
        for line in complete.split(b"\n"):
            if not line:
                continue
            try:
                j = json.loads(line)
            except Exception:
                continue
            oid = j.get("old_id")
            if oid in self.t and _terminal(j):
                self.seen.add(oid)
        return self.seen


def precheck_gate(targets: list, targets_path: pathlib.Path, sweep: bool = False) -> bool:
    """S10-20/22: v6.2 C6 blocking validate restored. precheck_lib (novelty, dupe,
    settings legality) AND tools/validate_targets.py must BOTH pass; any finding
    blocks the launch — zero POSTs. No WQ API calls.
    sweep=True: same-root-field config sweep — skip family-novelty (Khoa 2026-07-17)."""
    # L0: 3-layer LOGIC gate (Khoa 2026-07-17) — operator-usage + field-description + economic
    try:
        import logic_check  # noqa: E402 (sibling)
        lg = logic_check.check(targets, strict=False)
        if not lg["ok"]:
            for r in lg["rows"]:
                if r["blocking"]:
                    print(f"  LOGIC-BLOCK {r['id']} [{r['verdict']}]: "
                          + "; ".join(f["reason"] for f in r["findings"] if f["verdict"] in ("ILLEGAL", "DANGEROUS")), flush=True)
            print(f"FAIL: logic_check blocked {lg['n_block']} rows — 0 POSTs made", flush=True)
            return False
    except Exception as e:
        print(f"  (logic_check unavailable: {e} — proceeding with precheck only)", flush=True)
    out = precheck_lib.precheck(targets, run_validate=True, targets_path=targets_path, sweep=sweep)
    if not out["ok"]:
        for tag in sorted(out["per_row_errors"]):
            for msg in out["per_row_errors"][tag]:
                print(f"  BLOCK {msg}", flush=True)
        print("FAIL: precheck blocked launch — 0 POSTs made", flush=True)
    return out["ok"]


HARD_STALL_S = 2700.0   # 45min with ZERO journalled rows = hung, whatever the metrics say


def _block_until_done(proc, target_ids: set, poll_s: float, stall_timeout_s: float,
                      results_path: pathlib.Path = RESULTS) -> bool:
    """Block until every target id is journaled. S10-11/12 wrapper side: a poll
    ceiling — no NEW journal rows for stall_timeout_s => terminate resim_bulk and
    FAIL (replaces the interim manual-break rule for this path)."""
    # B2 fix: the stall clock must detect a HUNG ENGINE, not "no completions" — real sims take 57-71
    # min to first-complete, so terminal-row-only progress falsely trips the 30-min stall and abandons
    # the whole inflight wave (this lost iter26/38/43's sims). resim_bulk emits metric events every
    # few seconds to state/resim_metrics.jsonl; its GROWTH is engine liveness -> reset the clock on it.
    metrics_path = results_path.parent / "resim_metrics.jsonl"
    scanner = _JournalScanner(target_ids, results_path)   # incremental: read only appended bytes per poll
    last_done = -1
    last_msz = -1
    last_progress = time.time()
    last_journal = time.time()
    while proc.poll() is None:
        done = len(scanner.scan())
        msz = metrics_path.stat().st_size if metrics_path.exists() else 0
        if done > last_done:
            last_journal = time.time()
        if done > last_done or msz > last_msz:         # terminal row OR live engine (metrics growing)
            last_done = done; last_msz = msz; last_progress = time.time()
        print(f"  journaled {done}/{len(target_ids)}", flush=True)
        if done >= len(target_ids):
            return True
        if time.time() - last_progress > stall_timeout_s:
            print(f"STALL: no engine activity for {stall_timeout_s:.0f}s — "
                  f"terminating resim_bulk (hung)", flush=True)
            proc.terminate()
            proc.wait()
            return False
        # SECOND CLOCK, on real progress only. The clock above resets whenever resim_metrics.jsonl
        # grows, and that file grows every few seconds for as long as the engine is ALIVE -- a
        # process stuck in a retry loop keeps writing metrics, keeps resetting the clock, and never
        # trips. Measured 2026-08-06: a round ran 50 minutes with 400 targets and ZERO journalled
        # rows while --stall-timeout 600 sat there doing nothing, and three earlier hangs the same
        # day cost roughly 2.5 hours of a 4-hour window.
        # Liveness is not progress. If nothing has been JOURNALLED for HARD_STALL_S the engine is
        # hung however busy it looks. The bound has to clear the slowest legitimate first
        # completion, which is what the metrics clock was introduced to protect.
        if time.time() - last_journal > HARD_STALL_S:
            print(f"HARD STALL: {done}/{len(target_ids)} journalled and nothing new for "
                  f"{HARD_STALL_S/60:.0f}min — engine alive but not progressing, terminating",
                  flush=True)
            proc.terminate()
            proc.wait()
            return False
        time.sleep(poll_s)
    return len(scanner.scan()) >= len(target_ids)


def live_launch(targets_path: pathlib.Path, poll_s: float = 10.0,
                stall_timeout_s: float = 5400.0, sweep: bool = False) -> bool:
    """INTEGRATION-RUN-BY-OPERATOR: precheck (blocking), copy targets, run
    resim_bulk, block until all journaled or the stall ceiling trips.

    The 429/rate breaker lives inside resim_bulk.req(); this wrapper reads only
    the local journal and makes no API calls itself.
    """
    targets = json.load(open(targets_path))
    if not precheck_gate(targets, targets_path, sweep=sweep):
        return False
    target_ids = {a["id"] for a in targets}
    batch = _read_batch_const()
    print(f"launching {len(targets)} sims as {math.ceil(len(targets)/batch)} multi-sim POSTs "
          f"via {RESIM_BULK}", flush=True)
    TARGETS_LIVE.write_text(json.dumps(targets, indent=1))
    proc = subprocess.Popen([sys.executable, str(RESIM_BULK)])
    try:
        ok = _block_until_done(proc, target_ids, poll_s, stall_timeout_s)
    finally:
        if proc.poll() is None:
            proc.wait()
    done = _journaled_ids(target_ids)
    ok = ok and len(done) >= len(target_ids)
    print(f"{'PASS' if ok else 'FAIL'}: journaled {len(done)}/{len(target_ids)}", flush=True)
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("targets", help="stage targets JSON (list of N homogeneous rows)")
    ap.add_argument("--dry-run", action="store_true",
                    help="verify batch grouping (ceil(N/BATCH) POSTs) without calling the API")
    ap.add_argument("--stall-timeout", type=float, default=5400.0,
                    help="live mode: FAIL if the ENGINE (metrics journal) is silent this many seconds")
    ap.add_argument("--sweep", action="store_true",
                    help="same-root-field config sweep: skip family-novelty block (exact-dup/NO_GO still enforced)")
    args = ap.parse_args(argv)
    tp = pathlib.Path(args.targets)
    if not tp.exists():
        print(f"FAIL: targets file not found: {tp}")
        return 2
    try:
        json.load(open(tp))
    except (json.JSONDecodeError, ValueError) as e:
        print(f"FAIL: targets file is not valid JSON: {tp}: {e}")
        return 2
    ok = dry_run(tp) if args.dry_run else live_launch(tp, stall_timeout_s=args.stall_timeout, sweep=args.sweep)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
