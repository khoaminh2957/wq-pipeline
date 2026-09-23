"""Suite for tools/deploy.py -- the version identity of the deployed pipeline.

The contract these tests pin: a version is the CONTENT of the shipped code. Nothing about the clock,
the filename mtimes, the git SHA or the machine may change it, and any byte of shipped code must.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import deploy  # noqa: E402


@pytest.fixture
def tree(tmp_path):
    """A miniature repo laid out like the real one, with the traps: caches, .pyc, nested dirs."""
    (tmp_path / "forge").mkdir()
    (tmp_path / "forge" / "a.py").write_text("A\n")
    (tmp_path / "forge" / "sub").mkdir()
    (tmp_path / "forge" / "sub" / "b.py").write_text("B\n")
    (tmp_path / "forge" / "__pycache__").mkdir()
    (tmp_path / "forge" / "__pycache__" / "a.cpython-314.pyc").write_bytes(b"\x00binary")
    (tmp_path / "forge" / "stale.pyc").write_bytes(b"\x00")
    (tmp_path / "vps").mkdir()
    (tmp_path / "vps" / "auth_daemon.py").write_text("D\n")
    (tmp_path / "root_mod.py").write_text("R\n")
    return tmp_path


PLAN = {"forge/": "forge/", "root_mod.py": "root_mod.py", "vps/auth_daemon.py": "auth_daemon.py"}


def test_the_plan_ships_code_and_skips_caches_and_bytecode(tree):
    fmap = deploy.file_map(tree, PLAN)
    assert sorted(fmap) == ["auth_daemon.py", "forge/a.py", "forge/sub/b.py", "root_mod.py"]
    # the path a file lands on is the REMOTE path, so vps/auth_daemon.py is deployed at the root
    assert fmap["auth_daemon.py"].name == "auth_daemon.py"


def test_the_version_is_the_content_not_the_clock_or_the_path_on_disk(tree, tmp_path):
    v1 = deploy.version_id(deploy.content_hashes(deploy.file_map(tree, PLAN)))
    # touching a file changes its mtime and nothing else
    (tree / "forge" / "a.py").touch()
    assert deploy.version_id(deploy.content_hashes(deploy.file_map(tree, PLAN))) == v1
    # a copy of the same tree at another location is the same version
    import shutil
    other = tmp_path / "elsewhere"
    shutil.copytree(tree, other)
    assert deploy.version_id(deploy.content_hashes(deploy.file_map(other, PLAN))) == v1


def test_any_byte_of_shipped_code_changes_the_version(tree):
    v1 = deploy.version_id(deploy.content_hashes(deploy.file_map(tree, PLAN)))
    (tree / "forge" / "sub" / "b.py").write_text("B \n")          # one space
    assert deploy.version_id(deploy.content_hashes(deploy.file_map(tree, PLAN))) != v1


def test_a_new_or_deleted_file_changes_the_version(tree):
    v1 = deploy.version_id(deploy.content_hashes(deploy.file_map(tree, PLAN)))
    (tree / "forge" / "c.py").write_text("A\n")                   # same CONTENT as a.py, new path
    v2 = deploy.version_id(deploy.content_hashes(deploy.file_map(tree, PLAN)))
    assert v2 != v1
    (tree / "forge" / "c.py").unlink()
    assert deploy.version_id(deploy.content_hashes(deploy.file_map(tree, PLAN))) == v1


def test_changing_untracked_state_does_not_change_the_version(tree):
    v1 = deploy.version_id(deploy.content_hashes(deploy.file_map(tree, PLAN)))
    (tree / "state").mkdir()
    (tree / "state" / "journal.jsonl").write_text('{"alpha": "x"}\n')
    assert deploy.version_id(deploy.content_hashes(deploy.file_map(tree, PLAN))) == v1


def test_drift_names_exactly_what_differs(tree):
    local = {"hashes": {"a": "1", "b": "2", "c": "3"}}
    deployed = {"hashes": {"a": "1", "b": "CHANGED", "d": "4"}}
    assert deploy.drift(local, deployed) == {"added": ["c"], "removed": ["d"], "changed": ["b"]}
    assert deploy.drift(local, local) == {"added": [], "removed": [], "changed": []}


def test_manifest_carries_provenance_without_letting_it_set_the_identity(tree):
    m = deploy.manifest(tree, PLAN, now=1_790_000_000.0)
    assert m["built_at"] == 1_790_000_000.0 and m["files"] == 4
    assert m["version"] == deploy.version_id(m["hashes"])
    # git provenance is recorded; tmp_path is not a repo, so both read None and that is not an error
    assert "git_sha" in m and "git_dirty" in m
    assert json.loads(json.dumps(m))["version"] == m["version"]      # the manifest round-trips


def test_the_real_repo_plan_resolves_and_ships_no_state(tree):
    fmap = deploy.file_map()
    assert len(fmap) > 50, "the real plan should resolve to the live code set"
    assert not any(p.startswith(("state/", "fetched/")) for p in fmap)
    assert not any("__pycache__" in p or p.endswith(".pyc") for p in fmap)
    assert "forge/submit.py" in fmap and "auth_daemon.py" in fmap and "forge_loop.sh" in fmap


# ------------------------------------------------------- the shipping decisions, with no network
# Each test pins a defect one of the two audits found (docs/evalharness/audits/deploy.md).


# ----- the pure judgements: these decide everything, so they are tested without any ssh at all
def test_the_existence_probe_must_account_for_every_path_it_was_sent():
    """AUDIT 2: a `while read` loop never tested the last path (no trailing newline) and exited with
    the status of its last test. The count trailer is the defence that does not trust the loop."""
    asked = ["a.py", "b.py", "z_last.py"]
    assert deploy._existing_from("a.py\nz_last.py\nCHECKED 3\n", asked) == {"a.py", "z_last.py"}
    with pytest.raises(RuntimeError, match="checked 2 of 3"):
        deploy._existing_from("a.py\nCHECKED 2\n", asked)          # the silently-skipped last path
    with pytest.raises(RuntimeError, match="no CHECKED"):
        deploy._existing_from("a.py\nb.py\n", asked)                 # a truncated listing
    with pytest.raises(RuntimeError, match="not asked about"):
        deploy._existing_from("state/journal.jsonl\nCHECKED 3\n", asked)


def test_the_planner_exit_2_is_healthy_only_with_its_own_message():
    """AUDIT 2: argparse also exits 2. Accepting every 2 passes a smoke that never planned."""
    assert deploy._smoke_ok("planner", 0, "")
    assert deploy._smoke_ok("planner", 2, "nothing to simulate: the library is exhausted for every reachable cell")
    assert not deploy._smoke_ok("planner", 2, "usage: runner.py [-h] ...\nerror: unrecognized arguments")
    assert not deploy._smoke_ok("tests", 2, "library is exhausted")         # only the planner has the exception


def test_inactive_is_not_active():
    """AUDIT 2: `'active' in 'inactive'` is True, so the restart check passed a dead unit."""
    assert deploy._is_active("active\n")
    assert not deploy._is_active("inactive\n")
    assert not deploy._is_active("failed\n") and not deploy._is_active("")


def test_every_push_gets_its_own_snapshot():
    """AUDIT 2 CATASTROPHIC: with no manifest on the target every push wrote pre-unversioned.tgz over
    the last one -- the only copy of the tree it existed to restore."""
    a = deploy.snapshot_tag(None, now=1_790_000_000)
    b = deploy.snapshot_tag(None, now=1_790_000_001)
    assert a != b and a.startswith("pre-unversioned-")


def test_the_smoke_never_spends_quota_and_leaves_no_plan_behind():
    for name, cmd in deploy.SMOKE:
        assert "--live" not in cmd, name
    planner = dict(deploy.SMOKE)["planner"]
    # the plan it removes is one it just created: the seed is walked to a FREE file first
    assert "while [ -e state/forge/plans/$s.json ]" in planner
    assert "rm -f state/forge/plans/$s.json" in planner and "exit $rc" in planner


def test_staging_happens_outside_the_repository_and_keeps_the_executable_bit(tmp_path):
    """AUDIT 2: the stage lived in the repo root (5 MB left behind by the tests) and write_bytes
    stripped the executable bit that forge_loop.sh carries."""
    src = tmp_path / "loop.sh"
    src.write_text("#!/bin/bash\n")
    src.chmod(0o755)
    staged = deploy._stage({"forge_loop.sh": src})
    try:
        assert not str(staged).startswith(str(deploy.ROOT))
        assert (staged / "forge_loop.sh").stat().st_mode & 0o111
    finally:
        import shutil
        shutil.rmtree(staged)


# ----- push(): the decisions, with every remote pipe replaced
class _Calls:
    def __init__(self):
        self.snapshotted = self.rolled_back = self.rsynced = self.manifest_written = False
        self.restart = None
        self.rollback_args = None
        self.lines = []

    def out(self, msg):
        self.lines.append(str(msg))

    def said(self, needle):
        return any(needle in l for l in self.lines)


@pytest.fixture
def nonet(monkeypatch, tmp_path):
    c = _Calls()
    monkeypatch.setattr(deploy, "DEPLOY_LOG", tmp_path / "deploys.jsonl")   # never the real ledger
    monkeypatch.setattr(deploy, "loop_closure", lambda root=None: ["forge/runner.py"])
    monkeypatch.setattr(deploy, "round_in_flight", lambda: False)
    monkeypatch.setattr(deploy, "remote_manifest", lambda: ({"version": "old", "hashes": {}}, True))
    monkeypatch.setattr(deploy, "remote_existing", lambda paths: set(paths))
    monkeypatch.setattr(deploy, "snapshot", lambda paths, tag, out=print: (setattr(c, "snapshotted", True), ("tar", len(paths)))[1])

    def fake_rollback(tar, to_delete, out=print):
        c.rolled_back, c.rollback_args = True, (tar, list(to_delete))
        c.events.append("rollback")
        return True
    monkeypatch.setattr(deploy, "rollback", fake_rollback)
    monkeypatch.setattr(deploy, "write_manifest", lambda local, out=print: (setattr(c, "manifest_written", True), True)[1])

    c.events = []

    def fake_stop(out=print):
        c.events.append("stop")
        return True

    def fake_start(out=print):
        c.events.append("start")
        c.restart = "restarted"
        return True
    monkeypatch.setattr(deploy, "stop_units", fake_stop)
    monkeypatch.setattr(deploy, "start_units", fake_start)
    monkeypatch.setattr(deploy, "run_smoke", lambda out=print: [(n, True, []) for n, _ in deploy.SMOKE])

    def fake_run(argv, **kw):
        import types
        if argv and argv[0] == "rsync":
            c.rsynced = True
            c.events.append("rsync")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(deploy.subprocess, "run", fake_run)
    return c


def test_push_refuses_while_a_forge_child_runs(monkeypatch, nonet):
    monkeypatch.setattr(deploy, "round_in_flight", lambda: True)
    assert deploy.push(out=nonet.out) == deploy.EXIT["refused"]
    assert not nonet.snapshotted and not nonet.rsynced


def test_push_refuses_when_the_target_manifest_cannot_be_read(monkeypatch, nonet):
    """AUDIT 1 A3: 'could not read' treated as 'never deployed' armed the virgin branch."""
    monkeypatch.setattr(deploy, "remote_manifest", lambda: (None, False))
    assert deploy.push(out=nonet.out) == deploy.EXIT["refused"] and not nonet.rsynced


def test_push_refuses_without_a_verified_snapshot(monkeypatch, nonet):
    """AUDIT 1: snapshot() printed success whatever happened and push shipped on that word."""
    monkeypatch.setattr(deploy, "snapshot", lambda paths, tag, out=print: None)
    assert deploy.push(out=nonet.out) == deploy.EXIT["refused"]
    assert nonet.said("one-way door") and not nonet.rsynced


def test_push_refuses_when_the_existence_probe_is_incomplete(monkeypatch, nonet):
    def bad(paths):
        raise RuntimeError("existence probe checked 536 of 537 paths")
    monkeypatch.setattr(deploy, "remote_existing", bad)
    assert deploy.push(out=nonet.out) == deploy.EXIT["refused"] and not nonet.rsynced


def test_a_virgin_target_can_be_deployed_to(monkeypatch, nonet):
    """AUDIT 2: with nothing on the target the snapshot was 'empty', read as failure, and the first
    deploy could never happen. Nothing to archive is a valid snapshot."""
    monkeypatch.setattr(deploy, "remote_manifest", lambda: (None, True))
    monkeypatch.setattr(deploy, "remote_existing", lambda paths: set())
    monkeypatch.setattr(deploy, "snapshot", lambda paths, tag, out=print: ("", 0))
    assert deploy.push(out=nonet.out) == deploy.EXIT["deployed"]


def test_only_genuinely_new_paths_may_be_deleted_on_rollback(monkeypatch, nonet):
    """AUDIT 1 A1: 499 of 537 plan paths already existed; deleting them on rollback drives production
    through a state where they do not exist."""
    all_paths = set(deploy.manifest()["hashes"])
    already = set(sorted(all_paths)[:-2])
    monkeypatch.setattr(deploy, "remote_existing", lambda paths: already)
    monkeypatch.setattr(deploy, "run_smoke", lambda out=print: [("import", False, ["boom"])])
    assert deploy.push(out=nonet.out) == deploy.EXIT["rolled_back"]
    _, to_delete = nonet.rollback_args
    assert set(to_delete) == all_paths - already and len(to_delete) == 2


def test_a_failed_rollback_is_its_own_loud_exit_code(monkeypatch, nonet):
    """AUDIT 2: rollback() returned False and push() discarded it, returning the same 1 either way."""
    monkeypatch.setattr(deploy, "run_smoke", lambda out=print: [("tests", False, ["1 failed"])])
    monkeypatch.setattr(deploy, "rollback", lambda tar, to_delete, out=print: False)
    assert deploy.push(out=nonet.out) == deploy.EXIT["rollback_failed"]


def test_an_interrupt_after_the_swap_still_rolls_back_and_re_raises(monkeypatch, nonet):
    """AUDIT 2 CATASTROPHIC: `except Exception` does not catch KeyboardInterrupt."""
    def ctrl_c(out=print):
        raise KeyboardInterrupt
    monkeypatch.setattr(deploy, "run_smoke", ctrl_c)
    with pytest.raises(KeyboardInterrupt):
        deploy.push(out=nonet.out)
    assert nonet.rolled_back


def test_the_manifest_is_written_only_after_a_green_smoke(monkeypatch, nonet):
    monkeypatch.setattr(deploy, "run_smoke", lambda out=print: [("tests", False, ["1 failed"])])
    deploy.push(out=nonet.out)
    # a successful rollback puts the tree back in its known state and restarts the units by design;
    # what must never happen is a manifest recording code that is not installed
    assert nonet.rolled_back and not nonet.manifest_written
    assert nonet.events[-2:] == ["rollback", "start"]


def test_a_deploy_whose_record_failed_says_so(monkeypatch, nonet):
    """AUDIT 2: push printed 'DEPLOYED -- smoke green' and returned 0 when the manifest was not written."""
    monkeypatch.setattr(deploy, "write_manifest", lambda local, out=print: False)
    assert deploy.push(out=nonet.out) == deploy.EXIT["unrecorded"]
    assert nonet.said("the record of it is not")


def test_a_green_deploy_records_the_version_and_restarts_the_loop(nonet):
    assert deploy.push(out=nonet.out) == deploy.EXIT["deployed"]
    assert nonet.snapshotted and not nonet.rolled_back and nonet.manifest_written and nonet.restart == "restarted"


def test_push_is_a_no_op_when_the_target_already_runs_this_content(monkeypatch, nonet):
    m = deploy.manifest()
    monkeypatch.setattr(deploy, "remote_manifest", lambda: (m, True))
    assert deploy.push(out=nonet.out) == deploy.EXIT["deployed"] and not nonet.snapshotted


def test_every_attempt_past_the_guards_is_recorded_and_refusals_are_not(monkeypatch, nonet):
    """DORA's raw material. A refusal swapped nothing, so it is not a deploy and must not dilute the
    change-failure rate."""
    assert deploy.push(out=nonet.out) == deploy.EXIT["deployed"]
    monkeypatch.setattr(deploy, "run_smoke", lambda out=print: [("tests", False, ["x"])])
    assert deploy.push(out=nonet.out) == deploy.EXIT["rolled_back"]
    monkeypatch.setattr(deploy, "round_in_flight", lambda: True)
    assert deploy.push(out=nonet.out) == deploy.EXIT["refused"]
    rows = [json.loads(l) for l in deploy.DEPLOY_LOG.read_text().splitlines()]
    assert [r["outcome"] for r in rows] == ["deployed", "rolled_back"]
    assert all(r["finished_at"] >= r["started_at"] and r["version"] for r in rows)


def test_the_plan_covers_every_file_the_live_loop_actually_imports():
    """MEASURED 2026-09-23: the dispatcher imported harness13/ at module level and the plan did not ship it."""
    missing = sorted(set(deploy.loop_closure()) - set(deploy.file_map()))
    assert not missing, "the live loop imports files the deploy plan does not ship: %s" % missing


def test_a_ci_only_change_does_not_change_the_pipeline_version(tmp_path, monkeypatch):
    """Round 1, S1 ii: tools/ci_baseline.json and friends sat inside the version hash, so recording a CI
    number made the pipeline a 'new version' and split D14's cohorts."""
    m1 = deploy.manifest()
    closure = set(deploy.loop_closure())
    ci_only = [p for p in m1["hashes"] if p.startswith("tools/ci_") and p not in closure]
    assert ci_only, "expected CI files outside the loop's closure"
    fmap = deploy.file_map()
    f = tmp_path / "changed"
    f.write_text("a different CI file")
    fmap2 = dict(fmap, **{ci_only[0]: f})
    m2 = deploy.manifest(fmap=fmap2)
    assert m2["version"] != m1["version"]                     # the shipped bytes did change
    assert m2["pipeline_version"] == m1["pipeline_version"]   # the pipeline did not


def test_the_units_are_stopped_before_the_swap_and_started_after_a_green_smoke(nonet):
    """Nothing may run code the smoke has not judged."""
    assert deploy.push(out=nonet.out) == deploy.EXIT["deployed"]
    assert nonet.events.index("stop") < nonet.events.index("rsync") < nonet.events.index("start")


def test_a_successful_rollback_restarts_the_units(monkeypatch, nonet):
    monkeypatch.setattr(deploy, "run_smoke", lambda out=print: [("tests", False, ["x"])])
    assert deploy.push(out=nonet.out) == deploy.EXIT["rolled_back"]
    assert nonet.events[-2:] == ["rollback", "start"]


def test_a_failed_rollback_leaves_the_units_stopped(monkeypatch, nonet):
    """Starting the loop on a half-swapped tree spends real quota on code nobody can name."""
    monkeypatch.setattr(deploy, "run_smoke", lambda out=print: [("tests", False, ["x"])])
    monkeypatch.setattr(deploy, "rollback", lambda tar, to_delete, out=print: False)
    assert deploy.push(out=nonet.out) == deploy.EXIT["rollback_failed"]
    assert "start" not in nonet.events and nonet.said("LEFT STOPPED")


def test_units_that_will_not_stop_mean_no_swap(monkeypatch, nonet):
    monkeypatch.setattr(deploy, "stop_units", lambda out=print: False)
    assert deploy.push(out=nonet.out) == deploy.EXIT["refused"] and not nonet.rsynced


def test_what_ships_is_exactly_what_was_hashed(monkeypatch, nonet):
    """The third audit reproduced a second walk of the repository shipping files the first walk
    never hashed, probed or snapshotted. The staged bytes are now checked against the manifest."""
    monkeypatch.setattr(deploy, "_staged_matches", lambda staged, hashes: ["forge/changed.py"])
    assert deploy.push(out=nonet.out) == deploy.EXIT["refused"]
    assert not nonet.rsynced and not nonet.snapshotted


def test_the_stage_root_is_755_not_mkdtemps_700(tmp_path):
    """rsync -a carries the root's mode onto the target: /opt/wq became 0700 (reproduced)."""
    src = tmp_path / "x.py"
    src.write_text("x")
    staged = deploy._stage({"x.py": src})
    try:
        assert (staged.stat().st_mode & 0o777) == 0o755
    finally:
        import shutil
        shutil.rmtree(staged)


def test_the_busy_pattern_sees_every_forge_python_process():
    import re
    pat = re.compile(deploy.BUSY)
    for cmd in ("forge/runner.py -n 300", "forge/offline/recover_orphans.py", "forge/offline/c11_neut.py",
                "forge/harvest.py", "forge/submit.py --submit"):
        assert pat.search(cmd), cmd
    assert not pat.search("pgrep -fc '%s'" % deploy.BUSY)          # never matches its own pattern text


def test_push_refuses_when_the_loop_closure_cannot_be_measured(monkeypatch, nonet):
    """No pipeline version means no D1/D14 attribution for anything this deploy produces."""
    def boom(root=None):
        raise RuntimeError("could not import the loop")
    monkeypatch.setattr(deploy, "loop_closure", boom)
    assert deploy.push(out=nonet.out) == deploy.EXIT["refused"] and not nonet.rsynced
