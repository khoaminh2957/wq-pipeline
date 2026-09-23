#!/usr/bin/env python3
"""5x unit suite for run_multisim (dry-run + plan_batches + live-path guards).

No WQ API is touched — the live launch is integration-run-by-operator. This suite
proves: (a) plan_batches replicates resim_bulk's homogeneous-batch grouping, (b) the
CLI --dry-run plans exactly ceil(N/BATCH) multi-sim POSTs, (c) live_launch is BLOCKED
by the C6 precheck before any POST (S10-20/22), and (d) the journal block-loop has a
stall/poll ceiling (S10-11/12 wrapper side) plus a completion path — all run 5x.

Run:  python3 tools/funnel/test_run_multisim.py   (prints PASS/FAIL per run, exits 0 iff 5/5)
"""
from __future__ import annotations
import json, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FIXDIR = ROOT / "state" / "benchmark" / "fixtures"
FIX = FIXDIR / "stage_homogeneous_100.json"
FIX_ILLEGAL = FIXDIR / "multisim_targets_illegal.json"
FIX_JOURNAL = FIXDIR / "multisim_journal_3rows.jsonl"
MULTISIM = HERE / "run_multisim.py"

sys.path.insert(0, str(HERE))
import run_multisim as rm  # noqa: E402


def check_homogeneous_100() -> bool:
    """plan_batches on the 100-row homogeneous fixture -> exactly 10 batches of 10."""
    targets = json.load(open(FIX))
    batch = rm._read_batch_const()
    batches = rm.plan_batches(targets, batch)
    if len(batches) != 10:
        return False
    if any(len(g) != 10 for g in batches):
        return False
    # every batch homogeneous in (delay, region, universe)
    if any(len({rm._gkey(a) for a in g}) != 1 for g in batches):
        return False
    # no row lost or duplicated
    ids = [a["id"] for g in batches for a in g]
    return len(ids) == 100 and len(set(ids)) == 100


def check_heterogeneous_grouping() -> bool:
    """Mixed keys must split into per-key runs of <=BATCH, matching resim_bulk's sort+pop.

    12 CHN + 3 JPN + 25 USA (all delay 1) -> ceil(12/10)+ceil(3/10)+ceil(25/10)=2+1+3=6 POSTs,
    every batch homogeneous, every batch <=10.
    """
    def mk(region, universe, n):
        return [{"id": f"{region}{i}", "formula": "rank(close)" + "x" * (i % 4),
                 "settings": {"delay": 1, "region": region, "universe": universe}}
                for i in range(n)]
    targets = mk("CHN", "TOP2000U", 12) + mk("JPN", "TOP1600", 3) + mk("USA", "TOP3000", 25)
    batches = rm.plan_batches(targets, 10)
    if len(batches) != 6:
        return False
    if any(len(g) > 10 for g in batches):
        return False
    if any(len({rm._gkey(a) for a in g}) != 1 for g in batches):
        return False
    ids = [a["id"] for g in batches for a in g]
    return len(ids) == 40 and len(set(ids)) == 40


def check_cli_dry_run() -> bool:
    """CLI --dry-run exits 0 and reports 10 multi-sim POSTs on the 100-row fixture."""
    r = subprocess.run([sys.executable, str(MULTISIM), str(FIX), "--dry-run"],
                       capture_output=True, text=True)
    return (r.returncode == 0
            and "planned_posts=10 expected_posts=10" in r.stdout
            and "PASS: 100 rows -> 10 multi-sim POSTs" in r.stdout)


def check_precheck_blocks_live_launch() -> bool:
    """S10-20/22: live_launch on an illegal batch (bad region) must return False
    BEFORE writing state/resim_targets.json or spawning resim_bulk (0 POSTs)."""
    import contextlib, io
    before = rm.TARGETS_LIVE.read_bytes() if rm.TARGETS_LIVE.exists() else None
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = rm.live_launch(FIX_ILLEGAL)
    after = rm.TARGETS_LIVE.read_bytes() if rm.TARGETS_LIVE.exists() else None
    out = buf.getvalue()
    return (ok is False
            and before == after                      # live targets untouched
            and "FAIL: precheck blocked launch" in out
            and "launching" not in out)              # never reached the POST path


class _FakeProc:
    """Stands in for the resim_bulk Popen handle — never touches the API."""
    def __init__(self):
        self.terminated = False
    def poll(self):
        return 1 if self.terminated else None
    def terminate(self):
        self.terminated = True
    def wait(self):
        return 1


def check_stall_ceiling() -> bool:
    """S10-11/12 wrapper side: no journal progress within stall_timeout_s =>
    _block_until_done terminates the proc and returns False (no infinite loop)."""
    import contextlib, io
    fp = _FakeProc()
    with contextlib.redirect_stdout(io.StringIO()):
        ok = rm._block_until_done(fp, {"never_journaled_zz"}, poll_s=0.01,
                                  stall_timeout_s=0.05, results_path=FIX_JOURNAL)
    return ok is False and fp.terminated


def check_block_until_done_completes() -> bool:
    """When every target id is journaled, _block_until_done returns True without
    terminating resim_bulk."""
    import contextlib, io
    fp = _FakeProc()
    with contextlib.redirect_stdout(io.StringIO()):
        ok = rm._block_until_done(fp, {"jfx_a", "jfx_b", "jfx_c"}, poll_s=0.01,
                                  stall_timeout_s=5.0, results_path=FIX_JOURNAL)
    return ok is True and not fp.terminated


def run_once() -> bool:
    return (check_homogeneous_100()
            and check_heterogeneous_grouping()
            and check_cli_dry_run()
            and check_precheck_blocks_live_launch()
            and check_stall_ceiling()
            and check_block_until_done_completes())


def main() -> int:
    passed = 0
    for i in range(1, 6):
        ok = run_once()
        passed += ok
        print(f"run {i}: {'PASS' if ok else 'FAIL'}")
    print(f"{passed}/5 runs green")
    return 0 if passed == 5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
