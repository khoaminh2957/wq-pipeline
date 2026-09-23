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
# Every test below pins a defect the 2026-09-23 audit found, which is why the names read as failures
# prevented rather than as functions exercised.


class _Calls:
    def __init__(self):
        self.snapshotted = self.rolled_back = self.rsynced = False
        self.manifest_written = self.restarted = False
        self.rollback_args = None
        self.lines = []

    def out(self, msg):
        self.lines.append(str(msg))

    def said(self, needle):
        return any(needle in l for l in self.lines)


@pytest.fixture
def nonet(monkeypatch):
    c = _Calls()
    monkeypatch.setattr(deploy, "round_in_flight", lambda: False)
    monkeypatch.setattr(deploy, "remote_manifest", lambda: ({"version": "old", "hashes": {}}, True))
    monkeypatch.setattr(deploy, "remote_existing", lambda paths: set(paths))      # target has everything
    monkeypatch.setattr(deploy, "snapshot", lambda paths, tag, out=print: (setattr(c, "snapshotted", True), ("tar", 500))[1])

    def fake_rollback(tar, to_delete, out=print):
        c.rolled_back, c.rollback_args = True, (tar, list(to_delete))
        return True
    monkeypatch.setattr(deploy, "rollback", fake_rollback)
    monkeypatch.setattr(deploy, "write_manifest", lambda local, out=print: (setattr(c, "manifest_written", True), True)[1])
    monkeypatch.setattr(deploy, "restart_loop", lambda out=print: (setattr(c, "restarted", True), True)[1])
    monkeypatch.setattr(deploy, "run_smoke", lambda out=print: [(n, True, []) for n, _, _ in deploy.SMOKE])

    real_run = deploy.subprocess.run

    def fake_run(argv, **kw):
        import types
        if argv and argv[0] == "rsync":
            c.rsynced = True
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv and argv[0] == "rm":
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv and argv[0] == "ssh":
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        return real_run(argv, **kw)
    monkeypatch.setattr(deploy.subprocess, "run", fake_run)
    return c


def test_push_refuses_while_a_round_is_dispatching(monkeypatch, nonet):
    monkeypatch.setattr(deploy, "round_in_flight", lambda: True)
    assert deploy.push(out=nonet.out) == 2
    assert not nonet.snapshotted and not nonet.rsynced


def test_push_refuses_when_the_target_manifest_cannot_be_read(monkeypatch, nonet):
    """AUDIT A3: conflating 'could not read' with 'never deployed' armed the virgin branch -- which
    removes every plan path on rollback -- on an established target, after a network blip."""
    monkeypatch.setattr(deploy, "remote_manifest", lambda: (None, False))
    assert deploy.push(out=nonet.out) == 2
    assert nonet.said("refusing rather than guess") and not nonet.rsynced


def test_push_refuses_without_a_verified_snapshot(monkeypatch, nonet):
    """AUDIT BLOCKER: snapshot() ended in '; echo done' and reported success whatever happened, so
    push shipped believing it had a rollback it did not have."""
    monkeypatch.setattr(deploy, "snapshot", lambda paths, tag, out=print: None)
    assert deploy.push(out=nonet.out) == 2
    assert nonet.said("a deploy without a rollback is a one-way door") and not nonet.rsynced


def test_only_genuinely_new_paths_may_be_deleted_on_rollback(monkeypatch, nonet):
    """AUDIT A1: 499 of 537 plan paths already existed on the target, so they are OVERWRITES. A
    rollback that deletes them drives production through a state where they do not exist."""
    all_paths = set(deploy.manifest()["hashes"])
    already = set(list(all_paths)[:-2])                       # two paths are genuinely new
    monkeypatch.setattr(deploy, "remote_existing", lambda paths: already)
    monkeypatch.setattr(deploy, "run_smoke", lambda out=print: [("import", False, ["boom"])])
    assert deploy.push(out=nonet.out) == 1
    tar, to_delete = nonet.rollback_args
    assert set(to_delete) == all_paths - already and len(to_delete) == 2


def test_an_exception_after_the_swap_still_reaches_the_rollback(monkeypatch, nonet):
    def boom(out=print):
        raise RuntimeError("ssh died mid-smoke")
    monkeypatch.setattr(deploy, "run_smoke", boom)
    assert deploy.push(out=nonet.out) == 1
    assert nonet.rolled_back and nonet.said("deploy raised")


def test_the_manifest_is_written_only_after_a_green_smoke(monkeypatch, nonet):
    monkeypatch.setattr(deploy, "run_smoke", lambda out=print: [("tests", False, ["1 failed"])])
    assert deploy.push(out=nonet.out) == 1
    assert nonet.rolled_back and not nonet.manifest_written and not nonet.restarted


def test_a_green_deploy_records_the_version_and_restarts_the_loop(nonet):
    """AUDIT A2: without a restart the target runs new Python under the old loop driver while the
    manifest asserts a single version."""
    assert deploy.push(out=nonet.out) == 0
    assert nonet.snapshotted and not nonet.rolled_back
    assert nonet.manifest_written and nonet.restarted and nonet.said("smoke green")


def test_push_is_a_no_op_when_the_target_already_runs_this_content(monkeypatch, nonet):
    m = deploy.manifest()
    monkeypatch.setattr(deploy, "remote_manifest", lambda: (m, True))
    assert deploy.push(out=nonet.out) == 0
    assert nonet.said("nothing to do") and not nonet.snapshotted


def test_the_planner_smoke_accepts_the_library_exhausted_exit_code():
    """AUDIT: forge/runner.py returns 2 for 'library exhausted for every reachable cell' and
    vps/forge_loop.sh treats that as a normal round. Accepting only 0 made a healthy pipeline
    trigger a rollback -- the most likely ignition, needing no failure of any kind."""
    codes = {n: c for n, _, c in deploy.SMOKE}
    assert codes["planner"] == (0, 2) and codes["tests"] == (0,) and codes["import"] == (0,)


def test_the_smoke_suite_never_spends_quota():
    for name, argv, _ in deploy.SMOKE:
        assert "--live" not in argv, name
