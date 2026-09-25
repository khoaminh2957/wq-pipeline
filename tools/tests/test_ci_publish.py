"""Suite for tools/ci_publish.py -- the only path from the dev tree to the GitHub repository.

Round 2 of the architecture attack (docs/evalharness/audits/architecture_round2.md) found the publisher
untested (m8) and named four of its defects, each pinned here against REAL git repositories built in a
temporary directory: a bare "origin", the durable checkout cloned from it, and a dev tree. Nothing here
reaches the network: origin is a local path, the data tier and the classifier are stubbed, and `gh` is
intercepted.

  A12     the sync overwrote a checkout that had diverged, and deleted what it could not see
  M9-NL   nothing recorded that published code passed the data tier; .github was outside the subset
  S8-NL   the golden card could be re-recorded inside the commit that changed the scorer
"""

import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ci_publish as P  # noqa: E402
import deploy as D  # noqa: E402

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]

#: One file under every SUBSET entry, the three S8 files, and a classification file step 2 may rewrite.
DEV_FILES = {
    "forge/probe.py": "PROBE = 1\n",
    "forge/offline/benchmark.py": "SCORER = 1\n",
    "forge/hypotheses/h.yaml": "h: 1\n",
    "tools/t.py": "T = 1\n",
    "tools/ci_fixture.py": "FIXTURE = 1\n",
    "tools/ci_golden_card.json": '{\n "composite_0_100": 25.8\n}\n',
    "tools/ci_data_bound.json": '{"red": []}\n',
    "vps/forge_loop.sh": "#!/bin/bash\n",
    "vps/auth_daemon.py": "AD = 1\n",
    "fingerprint.py": "F = 1\n",
    "operators.py": "O = 1\n",
    "harness13/__init__.py": "\n",
    "harness13/crawl_fields.py": "C = 1\n",
    "harness13/massgen/mg/simulate.py": "S = 1\n",
    "harness/guards.py": "G = 1\n",
    "docs/evalharness/README.md": "doc\n",
    ".github/workflows/ci.yml": "on: push\n",
}


def git(cwd, *args):
    r = subprocess.run(GIT + list(args), cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, "git %s: %s" % (" ".join(args), r.stderr)
    return r.stdout.strip()


def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


class World:
    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.dev, self.origin, self.ci = tmp_path / "dev", tmp_path / "origin.git", tmp_path / "ci"
        self.records = tmp_path / "ci_publish_records.jsonl"
        self.lines = []
        self.data_tier = {"ok": True, "verdict": "green", "known_red": []}
        self.on_data_tier = None
        self.classify = None                        # None: the classification is current

    def head(self):
        return git(self.ci, "rev-parse", "HEAD")

    def origin_head(self):
        return git(self.origin, "rev-parse", "main")

    def status(self):
        return git(self.ci, "status", "--porcelain")

    def said(self, needle):
        return any(needle in l for l in self.lines)

    def records_written(self):
        return [json.loads(l) for l in self.records.read_text().splitlines()] if self.records.exists() else []

    def publish(self, *argv):
        return P.main(["-m", "publish under test", *argv])


@pytest.fixture
def world(tmp_path, monkeypatch):
    w = World(tmp_path)
    for rel, text in DEV_FILES.items():
        write(w.dev, rel, text)
    # origin holds the subset as it stands, plus files outside it (as the real repository does)
    subprocess.run(["git", "init", "-q", "--bare", "--initial-branch=main", str(w.origin)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(w.origin), str(seed)], check=True, capture_output=True)
    for rel, text in DEV_FILES.items():
        write(seed, rel, text)
    write(seed, "README.md", "outside the subset\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "initial")
    git(seed, "push", "-q", "origin", "HEAD:main")
    subprocess.run(["git", "clone", "-q", str(w.origin), str(w.ci)], check=True, capture_output=True)
    (w.ci / P.LAST).write_text(w.head() + "\n")            # ci_publish made this commit

    monkeypatch.setattr(P, "DEV", w.dev)
    monkeypatch.setattr(P, "CI", w.ci)
    monkeypatch.setattr(D, "PUBLISH_RECORDS", w.records)
    monkeypatch.setattr(P, "ensure_checkout", lambda out=print: None)

    def fake_data_tier(out=print):
        if w.on_data_tier:
            w.on_data_tier()
        return dict(w.data_tier)
    monkeypatch.setattr(P, "data_tier", fake_data_tier)
    monkeypatch.setattr(P, "classification_current", lambda: w.classify is None)

    real_sh = P.sh

    def sh(argv, cwd=None, check=True, timeout=3600):
        if argv and argv[0] == "gh":
            return types.SimpleNamespace(returncode=0, stdout="(gh intercepted)\n", stderr="")
        if any(str(a).endswith("ci_classify.py") for a in argv):
            return w.classify(argv)
        return real_sh(argv, cwd=cwd, check=check, timeout=timeout)
    monkeypatch.setattr(P, "sh", sh)
    monkeypatch.setattr("builtins.print", lambda *a, **k: w.lines.append(" ".join(str(x) for x in a)))
    return w


# ------------------------------------------------------------------------------------ the happy path
def test_a_publish_commits_pushes_and_leaves_the_record_deploy_reads(world):
    """M9-NL: the record is keyed by deploy's own full content version, so tools/deploy.py can find it."""
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    assert world.publish() == 0
    assert world.origin_head() == world.head()
    assert git(world.ci, "show", "HEAD:forge/probe.py") == "PROBE = 2"
    assert (world.ci / P.LAST).read_text().strip() == world.head()
    (rec,) = world.records_written()
    m = D.manifest(root=world.dev)
    assert rec["version"] == m["version"] and rec["pipeline_version"] == m["pipeline_version"]
    assert rec["verdict"] == "green" and rec["known_red"] == [] and rec["published_at"]
    assert rec["ci_commit"] == world.head() and rec["pushed"] is True
    assert D.publish_record_for(m["version"]) == rec


def test_a_known_red_only_data_tier_is_recorded_as_such(world):
    world.data_tier = {"ok": True, "verdict": "known-red-only", "known_red": ["tools/tests/test_layered.py::t"]}
    write(world.dev, "tools/t.py", "T = 2\n")
    assert world.publish() == 0
    (rec,) = world.records_written()
    assert rec["verdict"] == "known-red-only" and rec["known_red"] == ["tools/tests/test_layered.py::t"]


# ------------------------------------------------------------------------------------------- A12
def test_a12_a_hand_commit_in_the_checkout_is_refused_and_survives(world):
    """The adjudicator's reproduction: a HOTFIX committed in the checkout was reverted (forge/probe.py)
    and deleted (forge/hotfix_guard.py) by the next sync, with nothing printed."""
    write(world.ci, "forge/probe.py", "PROBE = 1\n# HOTFIX\n")
    write(world.ci, "forge/hotfix_guard.py", "GUARD = 1\n")
    git(world.ci, "add", "-A")
    git(world.ci, "commit", "-q", "-m", "HOTFIX")
    hotfix, before = world.head(), world.origin_head()
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    assert world.publish() == 1
    assert world.said("is not the last commit ci_publish made")
    assert "HOTFIX" in (world.ci / "forge/probe.py").read_text()
    assert (world.ci / "forge/hotfix_guard.py").exists()
    assert world.head() == hotfix and world.status() == "" and world.origin_head() == before
    assert world.records_written() == []


def test_a12_uncommitted_changes_in_the_checkout_are_refused_and_kept(world):
    write(world.ci, "forge/probe.py", "PROBE = 1\n# an edit nobody committed\n")
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    assert world.publish() == 1 and world.said("uncommitted changes")
    assert "nobody committed" in (world.ci / "forge/probe.py").read_text()


def test_a12_origin_ahead_of_the_checkout_is_refused_before_anything_is_written(world):
    other = world.tmp / "other"
    subprocess.run(["git", "clone", "-q", str(world.origin), str(other)], check=True, capture_output=True)
    write(other, "forge/pushed_elsewhere.py", "X = 1\n")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "pushed without ci_publish")
    git(other, "push", "-q", "origin", "HEAD:main")
    head = world.head()
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    assert world.publish() == 1 and world.said("origin/main has 1 commit(s) this checkout lacks")
    assert world.head() == head and world.status() == ""
    assert (world.ci / "forge/probe.py").read_text() == "PROBE = 1\n"


def test_a12_without_a_record_of_its_last_commit_it_refuses_until_one_is_adopted(world):
    (world.ci / P.LAST).unlink()
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    assert world.publish() == 1 and world.said("--adopt-head")
    assert world.status() == ""
    head = world.head()
    assert P.main(["--adopt-head", "0000000"]) == 1                  # not HEAD
    assert P.main(["--adopt-head", head[:6]]) == 1                   # too short to be a statement
    assert P.main(["--adopt-head", head[:12]]) == 0
    assert (world.ci / P.LAST).read_text().strip() == head
    assert world.publish() == 0


def test_a12_the_checkout_is_untouched_until_the_data_tier_and_the_classification_pass(world):
    """A12: the classification's clean arm used to be the checkout itself, so it was synced BEFORE the
    classification ran -- a step-2 refusal left the checkout overwritten."""
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    head = world.head()
    world.data_tier = {"ok": False, "verdict": "red", "known_red": []}
    assert world.publish() == 1 and world.status() == "" and world.head() == head

    world.data_tier = {"ok": True, "verdict": "green", "known_red": []}
    seen = {}

    def classify(argv):
        arm = Path(argv[argv.index("--clean") + 1])
        seen["arm"] = arm
        seen["checkout_status"] = world.status()                                 # while the arm runs
        seen["arm_probe"] = (arm / "forge/probe.py").read_text()                 # the dev tree's code
        seen["arm_readme"] = (arm / "README.md").read_text()                     # the repository's other files
        seen["arm_has_venv"] = (arm / ".v").exists()
        return types.SimpleNamespace(returncode=1, stdout="INVALID\n", stderr="")
    world.classify = classify
    assert world.publish() == 1 and world.said("the classification did not complete")
    assert seen["checkout_status"] == "" and seen["arm"] != world.ci
    assert seen["arm_probe"] == "PROBE = 2\n" and seen["arm_readme"] == "outside the subset\n"
    assert not seen["arm_has_venv"] and not seen["arm"].exists()                # thrown away afterwards
    assert world.status() == "" and world.head() == head and world.records_written() == []


def test_a12_a_refusal_after_the_sync_puts_the_checkout_back_at_head(world):
    head = world.head()
    write(world.dev, "tools/t.py", "HOOK = 'https://discord.com/api/webhooks/1234567/abc'\n")
    write(world.dev, "forge/brand_new.py", "N = 1\n")
    assert world.publish() == 1 and world.said("secret-shaped")
    assert world.status() == "" and world.head() == head
    assert not (world.ci / "forge/brand_new.py").exists()


def test_a_commit_that_was_not_pushed_is_pushed_by_the_next_run(world):
    """A failed or skipped push used to leave a commit the next run called 'nothing changed'."""
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    before = world.origin_head()
    assert world.publish("--no-push") == 0 and world.origin_head() == before
    assert world.publish() == 0 and world.origin_head() == world.head()
    assert [r["pushed"] for r in world.records_written()] == [False, True]


# ----------------------------------------------------------------------------------------- M9-NL
def test_m9_the_tree_the_data_tier_tested_must_be_the_tree_that_ships(world):
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    head = world.head()
    world.on_data_tier = lambda: write(world.dev, "forge/probe.py", "PROBE = 3  # edited mid-test\n")
    assert world.publish() == 1 and world.said("changed while the data tier ran")
    assert world.status() == "" and world.head() == head and world.records_written() == []

    world.on_data_tier = None

    def edit_during_classification(argv):
        write(world.dev, "forge/probe.py", "PROBE = 4  # edited after the data tier\n")
        return types.SimpleNamespace(returncode=0, stdout="ok\n", stderr="")
    world.classify = edit_during_classification
    assert world.publish() == 1 and world.said("changed between the data tier and the sync")
    assert world.status() == "" and world.head() == head and world.records_written() == []


def test_m9_a_rewritten_classification_is_not_a_changed_tree_and_the_record_covers_it(world):
    """Step 2 rewrites tools/ci_data_bound.json by design; that must not refuse, and the record must name
    the version deploy will compute -- the one WITH the new classification."""
    write(world.dev, "forge/probe.py", "PROBE = 2\n")

    def reclassify(argv):
        write(world.dev, "tools/ci_data_bound.json", '{"red": [], "measured_at": "now"}\n')
        return types.SimpleNamespace(returncode=0, stdout="written\n", stderr="")
    world.classify = reclassify
    assert world.publish() == 0
    (rec,) = world.records_written()
    assert rec["version"] == D.manifest(root=world.dev)["version"]
    assert "measured_at" in git(world.ci, "show", "HEAD:tools/ci_data_bound.json")


def test_m9_the_workflow_that_defines_the_gate_is_published_through_the_gate(world):
    assert ".github" in P.SUBSET
    write(world.dev, ".github/workflows/ci.yml", "on: [push, pull_request]\n")
    assert world.publish() == 0
    assert git(world.ci, "show", "HEAD:.github/workflows/ci.yml") == "on: [push, pull_request]"


def test_m9_a_red_data_tier_writes_no_record(world):
    world.data_tier = {"ok": False, "verdict": "red", "known_red": []}
    assert world.publish() == 1 and world.records_written() == []


# ----------------------------------------------------------------------------------------- S8-NL
NEW_GOLDEN = '{\n "composite_0_100": 27.5\n}\n'


@pytest.mark.parametrize("scorer", ["forge/offline/benchmark.py", "tools/ci_fixture.py"])
def test_s8_the_golden_card_with_the_scorer_in_one_commit_is_refused(world, scorer):
    """cac48d7 changed the scorer, the fixture and the golden in one commit."""
    head = world.head()
    write(world.dev, scorer, "CHANGED = 1\n")
    write(world.dev, P.GOLDEN, NEW_GOLDEN)
    assert world.publish() == 1 and world.said("Re-record the golden in its own commit")
    assert world.said('- "composite_0_100": 25.8') and world.said('+ "composite_0_100": 27.5')
    assert world.status() == "" and world.head() == head and world.records_written() == []


def test_s8_split_golden_commits_the_golden_alone_after_the_rest(world):
    """The data tier requires golden == scorer's output, so the two can only be published together; the
    split is how they reach the repository as two commits without a red commit ever being published alone."""
    base = world.head()
    write(world.dev, "forge/offline/benchmark.py", "SCORER = 2\n")
    write(world.dev, P.GOLDEN, NEW_GOLDEN)
    assert world.publish("--split-golden") == 0
    assert git(world.ci, "diff", "--name-only", "HEAD~1", "HEAD").split() == [P.GOLDEN]
    assert git(world.ci, "diff", "--name-only", base, "HEAD~1").split() == ["forge/offline/benchmark.py"]
    assert world.origin_head() == world.head() == (world.ci / P.LAST).read_text().strip()
    assert len(world.records_written()) == 1


def test_s8_a_golden_change_alone_is_allowed_and_its_diff_is_printed(world):
    write(world.dev, P.GOLDEN, NEW_GOLDEN)
    assert world.publish() == 0
    assert world.said("THE GOLDEN CARD CHANGED") and world.said('+ "composite_0_100": 27.5')


def test_s8_a_scorer_change_that_leaves_the_golden_alone_is_allowed(world):
    write(world.dev, "forge/offline/benchmark.py", "SCORER = 2  # a refactor\n")
    assert world.publish() == 0 and not world.said("THE GOLDEN CARD CHANGED")


# ------------------------------------------------------------------------- data_tier's verdict
def _check(name, ok, details=(), known_red=None):
    r = {"name": name, "ok": ok, "summary": name, "details": list(details), "blocking": True}
    if known_red is not None:
        r["known_red"] = known_red
    return lambda: dict(r)


_ALLOWED = {"ok": True, "allowed": ["a.py::known"], "blocking": [], "why": "only known red"}
_BLOCKED = {"ok": False, "allowed": [], "blocking": ["a.py::new -- NEW: not in tools/ci_known_red.json"], "why": "1"}


# Draw-3 SERIOUS 2: the allowance is the gate's own verdict (r["known_red"]); the classification's "red"
# list, stubbed below to name every failing test, no longer allows anything.
@pytest.mark.parametrize("checks,red,want", [
    ([_check("schema", True), _check("tests", True)], [], ("green", [])),
    ([_check("tests", False, ["FAILED a.py::known - boom"], _ALLOWED)], ["a.py::known"], ("known-red-only", ["a.py::known"])),
    ([_check("tests", False, ["FAILED a.py::known - x", "FAILED a.py::new - y"], _BLOCKED)], ["a.py::known", "a.py::new"],
     ("red", [])),
    ([_check("tests", False, ["FAILED a.py::known - boom"])], ["a.py::known"], ("red", [])),     # no verdict attached
    ([_check("schema", False), _check("tests", True)], [], ("red", [])),
])
def test_the_data_tier_returns_the_verdict_the_record_carries(monkeypatch, checks, red, want):
    import ci_gate as G
    monkeypatch.setattr(G, "tier", lambda root=None: "data")
    monkeypatch.setattr(G, "classification", lambda root=None: {"red": red})
    monkeypatch.setattr(G, "CHECKS", tuple(checks))
    r = P.data_tier(out=lambda *a: None)
    assert (r["verdict"], r["known_red"]) == want and r["ok"] == (want[0] != "red")


def test_the_data_tier_off_the_desk_is_not_run_and_not_ok(monkeypatch):
    import ci_gate as G
    monkeypatch.setattr(G, "tier", lambda root=None: "hermetic")
    assert P.data_tier(out=lambda *a: None) == {"ok": False, "verdict": "not-run", "known_red": []}


# ============================================================ draw-3 release audit (draw3_build.md, release)
import ci_gate as G  # noqa: E402  -- the real known_red_verdict; tier/CHECKS/classification are stubbed per test

#: The real data_tier, kept before the world fixture replaces it.
_REAL_DATA_TIER = P.data_tier
KN = "tools/tests/test_layered.py::test_the_model_names_the_operator_the_platform_named"
NEW = "forge/tests/test_submit.py::test_something_new"
KNOWN = [{"node_id": KN, "expected_failure": "20 journalled warnings"}]
AS_RECORDED = "AssertionError: 20 journalled warnings the model would not have prevented"


def _tests_result(failures, rc=1, known=KNOWN):
    """A failed tests check as ci_gate.check_tests builds it -- `details` capped at 12 lines, as its log is --
    with the verdict it attaches, computed by the REAL known_red_verdict.

    `incomplete` is present and empty, as the real check_tests always sets it for a whole-suite run (draw5_build
    release, required item 2: ci_gate now blocks a result without the key -- draw4_build ci 3 -- and this fixture
    wrote none, so the control below read red while production was unaffected)."""
    out = {"name": "tests", "ok": False, "summary": "tests", "blocking": True,
           "details": ["FAILED %s - %s" % (n, t) for n, t in failures][:12],
           "returncode": rc, "failures": [list(f) for f in failures], "counted": len(failures), "stale": None,
           "incomplete": []}
    out["known_red"] = G.known_red_verdict(out, known=known)
    return out


@pytest.fixture
def real_data_tier(world, monkeypatch):
    """The world, with the REAL data_tier over a stubbed gate. The classification names every failing test
    as red -- A8's re-classification route -- so only the gate's own verdict can refuse."""
    monkeypatch.setattr(sys, "path", list(sys.path))       # data_tier inserts DEV/tools; undone after the test
    monkeypatch.setattr(P, "data_tier", _REAL_DATA_TIER)
    monkeypatch.setattr(G, "tier", lambda root=None: "data")

    def use(result):
        monkeypatch.setattr(G, "CHECKS", (lambda: result,))
        monkeypatch.setattr(G, "classification", lambda root=None: {"red": [n for n, _ in result.get("failures", [])]})
    return use


LISTED_12 = [{"node_id": "tools/tests/test_k.py::t%02d" % i, "expected_failure": "20 journalled warnings"}
             for i in range(12)]


@pytest.mark.parametrize("case", ["more than 12 failures", "failing differently", "pytest rc 2", "red but not listed"])
def test_serious2_a_failure_the_gates_verdict_blocks_is_red_and_writes_no_record(world, real_data_tier, case):
    """SERIOUS 2: data_tier read the classification's "red" list and the 12-line `details`, never the gate's
    A8 verdict, and said known-red-only in each of these cases (m9_known_red.py; the 12-line cap is round 2's
    m5). deploy.py accepts known-red-only, so each was a deployable record."""
    result = {
        "more than 12 failures": lambda: _tests_result([(t["node_id"], AS_RECORDED) for t in LISTED_12]
                                                       + [(NEW, "boom")], known=LISTED_12),
        "failing differently": lambda: _tests_result([(KN, "AssertionError: 54 journalled warnings the model...")]),
        "pytest rc 2": lambda: _tests_result([(KN, AS_RECORDED)], rc=2),
        "red but not listed": lambda: _tests_result([(KN, AS_RECORDED), (NEW, "boom")]),
    }[case]()
    assert result["known_red"]["ok"] is False                       # the gate blocks each (the control below)
    real_data_tier(result)
    assert P.data_tier(out=lambda *a: None) == {"ok": False, "verdict": "red", "known_red": []}
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    head = world.head()
    assert world.publish() == 1 and world.said("no known-red allowance covers")
    assert world.records_written() == [] and world.head() == head and world.status() == ""


def test_serious2_the_known_test_failing_as_recorded_is_allowed_and_named(world, real_data_tier):
    """The control: the one listed test, failing with its listed text, pytest rc 1 -- allowed by both."""
    real_data_tier(_tests_result([(KN, AS_RECORDED)]))
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    assert world.publish() == 0
    (rec,) = world.records_written()
    assert rec["verdict"] == "known-red-only" and rec["known_red"] == [KN]


# ----- FIXES REQUIRED 5: A12 coverage holes (mutations M1 and K4 survived)
def _hand_commit(world, msg="HOTFIX"):
    write(world.ci, "forge/probe.py", "PROBE = 1\n# %s\n" % msg)
    write(world.ci, "forge/hotfix_guard.py", "GUARD = 1\n")
    git(world.ci, "add", "-A")
    git(world.ci, "commit", "-q", "-m", msg)
    return world.head()


def test_a12_a_hand_commit_made_while_the_data_tier_runs_is_refused_and_survives(world):
    """M1 (the second checkout check dropped) survived 23 tests: the first check had passed, the data tier
    takes many minutes, and a commit made in that window was overwritten by the sync."""
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    before, made = world.origin_head(), []
    world.on_data_tier = lambda: made.append(_hand_commit(world))
    assert world.publish() == 1 and world.said("is not the last commit ci_publish made")
    assert world.head() == made[0] and world.status() == "" and world.origin_head() == before
    assert "HOTFIX" in (world.ci / "forge/probe.py").read_text() and (world.ci / "forge/hotfix_guard.py").exists()
    assert world.records_written() == []


def test_a12_a_checkout_that_is_not_ours_is_refused_before_the_data_tier_runs(world):
    """K4 (the first, fail-fast check dropped) survived 23 tests: the second check hid its absence, at the
    cost of a whole data-tier run."""
    hotfix = _hand_commit(world)
    ran = []
    world.on_data_tier = lambda: ran.append(1)
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    assert world.publish() == 1 and world.said("is not the last commit ci_publish made")
    assert ran == [] and world.head() == hotfix


# ----- FIXES REQUIRED 7: the origin-ahead refusal must lead out of itself
def test_a12_following_the_origin_ahead_refusal_word_for_word_ends_in_a_publish(world):
    """Item 7: "bring it into the dev tree first" does not move the checkout's HEAD, so every later run
    printed the same refusal. The refusal now names `merge --ff-only origin/main`, then `--adopt-head`."""
    import re
    import shlex
    other = world.tmp / "other"
    subprocess.run(["git", "clone", "-q", str(world.origin), str(other)], check=True, capture_output=True)
    write(other, "forge/pushed_elsewhere.py", "X = 1\n")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "pushed without ci_publish")
    git(other, "push", "-q", "origin", "HEAD:main")
    assert world.publish() == 1 and world.said("origin/main has 1 commit(s) this checkout lacks")
    text = "\n".join(world.lines)
    merge = re.search(r"^\s*(git -C \S+ merge --ff-only origin/main)\s*$", text, re.M)
    adopt = re.search(r"^\s*tools/ci_publish\.py (--adopt-head \S+)\s*$", text, re.M)
    assert merge and adopt, text
    assert text.index(merge.group(1)) < text.index(adopt.group(1))
    subprocess.run(shlex.split(merge.group(1)), check=True, capture_output=True)
    assert P.main(shlex.split(adopt.group(1))) == 0
    write(world.dev, "forge/pushed_elsewhere.py", "X = 1\n")         # "carry what must survive into the dev tree"
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    assert world.publish() == 0 and world.origin_head() == world.head()
    assert git(world.ci, "show", "HEAD:forge/pushed_elsewhere.py") == "X = 1"


def test_a12_adopt_refuses_a_head_that_origin_main_does_not_contain(world, capsys):
    """The adjudicator's correction: adopt only a HEAD equal to, or an ancestor of, origin/main. A hand commit
    GitHub never received must not become "the last commit ci_publish made"."""
    head = _hand_commit(world)
    (world.ci / P.LAST).unlink()
    assert P.main(["--adopt-head", head[:12]]) == 1                    # adopt_head's out=print is the real one
    assert "not contained in origin/main" in capsys.readouterr().out
    assert not (world.ci / P.LAST).exists()
    git(world.ci, "reset", "-q", "--hard", "origin/main")               # what the refusal says to do
    assert P.main(["--adopt-head", world.head()[:12]]) == 0


# ----- FIXES REQUIRED 8: "tested == synced" covers the whole SUBSET
@pytest.mark.parametrize("path", ["vps/probe.py", "vps/systemd_wq-forge.service", ".github/workflows/ci.yml",
                                  "docs/evalharness/README.md",
                                  # draw3_fix release item 4: tree_identity's `plan:` half could be dropped with
                                  # every test still green. A staged YAML is outside the sync but inside the plan,
                                  # so the record's `version` names it: only the plan half sees it change.
                                  "forge/hypotheses/staged/x.yaml"])
def test_m9_an_edit_anywhere_in_the_subset_while_the_data_tier_runs_is_refused(world, path):
    """Item 6: `code` hashed the deploy PLAN only, so an edit to vps/probe.py, a unit file, .github/ or
    docs/evalharness during the data tier was committed with no refusal -- and the no-live scan reads vps/."""
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    head = world.head()
    world.on_data_tier = lambda: write(world.dev, path, "# edited while the data tier ran\n")
    assert world.publish() == 1 and world.said("changed while the data tier ran")
    assert world.records_written() == [] and world.head() == head and world.status() == ""


@pytest.mark.parametrize("path", ["forge/__pycache__/probe.cpython-314.pyc", "vps/.DS_Store",
                                  "docs/evalharness/.pytest_cache/v/cache/nodeids"])
def test_m9_a_file_the_sync_never_copies_does_not_refuse(world, path):
    """The identity covers what is synced, through the sync's own EXCLUDE list -- not every byte on disk."""
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    world.on_data_tier = lambda: write(world.dev, path, "cache\n")
    assert world.publish() == 0 and len(world.records_written()) == 1


def test_the_sync_filter_reads_exclude_the_way_rsync_does():
    assert not P._synced("hypotheses/staged/x.yaml") and not P._synced("a/__pycache__/m.pyc")
    assert not P._synced("x.pyc") and not P._synced(".pytest_cache/v/n") and not P._synced("sub/.DS_Store")
    assert P._synced("staged") and P._synced("stagedx/y.py") and P._synced("pycache.py")   # a FILE called staged


# ----- FIXES REQUIRED 10: the record before gh, and a missing gh is not a crash
def test_the_publish_record_is_written_before_gh_and_survives_its_absence(world, monkeypatch):
    """Item 11: `gh run list` ran before record_publish and sh() does not catch FileNotFoundError, so on a host
    without gh a PUSHED publish crashed and left no record."""
    inner, seen = P.sh, {}

    def sh(argv, cwd=None, check=True, timeout=3600):
        if argv and argv[0] == "gh":
            seen["records_when_gh_ran"] = len(world.records_written())
            raise FileNotFoundError(2, "No such file or directory", "gh")
        return inner(argv, cwd=cwd, check=check, timeout=timeout)
    monkeypatch.setattr(P, "sh", sh)
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    assert world.publish() == 0 and world.origin_head() == world.head()
    assert seen == {"records_when_gh_ran": 1} and len(world.records_written()) == 1
    assert world.said("could not list the Actions run")


# ============================================================ draw3_fix (docs/evalharness/audits/draw3_fix.md)
def _golden(value, closure):
    return json.dumps({"composite_0_100": value, "scorer_closure": {f: "0" * 64 for f in closure}}, indent=1) + "\n"


CLOSURE = ["forge/offline/benchmark.py", "forge/submit.py", "harness/guards.py"]


def _commit_golden(world, closure=CLOSURE):
    """Publish a golden that carries a scorer_closure, alone: HEAD then holds the committed closure."""
    write(world.dev, P.GOLDEN, _golden(25.8, closure))
    assert world.publish() == 0 and world.said("THE GOLDEN CARD CHANGED")
    world.lines.clear()
    return world.head()


def test_d42_the_golden_with_forge_submit_in_one_commit_is_refused(world):
    """D42 and draw3_fix ci SERIOUS 1: the refusal read benchmark.py and ci_fixture.py only, so a re-recorded
    golden rode in with an edit to any other of the 51 closure files -- forge/submit.py included."""
    head = _commit_golden(world)
    write(world.dev, "harness/guards.py", "G = 2\n")          # never read the old way: guards.py is closure-only
    write(world.dev, P.GOLDEN, _golden(27.5, CLOSURE))
    write(world.dev, "forge/submit.py", "SUBMIT = 2\n")
    assert world.publish() == 1 and world.said("Re-record the golden in its own commit")
    assert world.said("forge/submit.py") and world.said("harness/guards.py")
    assert world.head() == head and world.status() == "" and len(world.records_written()) == 1


def test_d42_a_file_outside_the_closure_may_ride_with_the_golden(world):
    _commit_golden(world)
    write(world.dev, "docs/evalharness/README.md", "doc 2\n")
    write(world.dev, P.GOLDEN, _golden(27.5, CLOSURE))
    assert world.publish() == 0
    assert set(git(world.ci, "diff", "--name-only", "HEAD~1", "HEAD").split()) == {P.GOLDEN, "docs/evalharness/README.md"}


def test_d42_a_file_the_new_golden_adds_to_the_closure_is_pinned_too(world):
    _commit_golden(world)
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    write(world.dev, P.GOLDEN, _golden(27.5, CLOSURE + ["forge/probe.py"]))
    assert world.publish() == 1 and world.said("forge/probe.py")


def test_d42_a_file_leaving_the_closure_in_this_commit_is_still_pinned_by_the_committed_golden(world):
    """The audit's text: the COMMITTED golden's closure. A re-record that drops forge/submit.py from the closure
    must not thereby let an edit to forge/submit.py ride with it."""
    _commit_golden(world)
    write(world.dev, "forge/submit.py", "SUBMIT = 2\n")
    write(world.dev, P.GOLDEN, _golden(27.5, [f for f in CLOSURE if f != "forge/submit.py"]))
    assert world.publish() == 1 and world.said("forge/submit.py")


def test_d42_a_golden_with_no_readable_closure_pins_every_other_file(world):
    """Fail closed: the world's first golden has no scorer_closure, so nothing says what it pins."""
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    write(world.dev, P.GOLDEN, '{\n "composite_0_100": 27.5\n}\n')
    assert world.publish() == 1 and world.said("forge/probe.py")
    assert world.publish("--split-golden") == 0
    assert git(world.ci, "diff", "--name-only", "HEAD~1", "HEAD").split() == [P.GOLDEN]


def test_d42_split_golden_still_commits_the_closure_edit_first_and_the_golden_alone(world):
    _commit_golden(world)
    base = world.head()
    write(world.dev, "forge/submit.py", "SUBMIT = 2\n")
    write(world.dev, P.GOLDEN, _golden(27.5, CLOSURE))
    assert world.publish("--split-golden") == 0
    assert git(world.ci, "diff", "--name-only", "HEAD~1", "HEAD").split() == [P.GOLDEN]
    assert git(world.ci, "diff", "--name-only", base, "HEAD~1").split() == ["forge/submit.py"]


def test_item7_a_diverged_checkout_is_told_the_reset_route_and_following_it_ends_in_a_publish(world):
    """draw3_fix release item 7: after a --no-push publish, a commit pushed elsewhere left the checkout diverged;
    the printed `merge --ff-only` failed (exit 128) and `--adopt-head` then refused "not HEAD" -- a dead end."""
    import re
    import shlex
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    assert world.publish("--no-push") == 0                      # HEAD now holds a commit origin lacks
    other = world.tmp / "other"
    subprocess.run(["git", "clone", "-q", str(world.origin), str(other)], check=True, capture_output=True)
    write(other, "forge/pushed_elsewhere.py", "X = 1\n")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "pushed without ci_publish")
    git(other, "push", "-q", "origin", "HEAD:main")
    world.lines.clear()
    assert world.publish() == 1 and world.said("HEAD also holds 1 commit(s) origin/main lacks")
    text = "\n".join(world.lines)
    assert "merge --ff-only" not in text
    reset = re.search(r"^\s*(git -C \S+ reset --hard origin/main)\s*$", text, re.M)
    adopt = re.search(r"^\s*tools/ci_publish\.py (--adopt-head \S+)\s*$", text, re.M)
    assert reset and adopt and text.index(reset.group(1)) < text.index(adopt.group(1)), text
    subprocess.run(shlex.split(reset.group(1)), check=True, capture_output=True)
    assert P.main(shlex.split(adopt.group(1))) == 0
    write(world.dev, "forge/pushed_elsewhere.py", "X = 1\n")     # "carry what must survive into the dev tree"
    assert world.publish() == 0 and world.origin_head() == world.head()
    assert git(world.ci, "show", "HEAD:forge/probe.py") == "PROBE = 2"       # the dropped commit's content, re-synced
    assert git(world.ci, "show", "HEAD:forge/pushed_elsewhere.py") == "X = 1"


def test_item8_exclude_holds_only_the_pattern_forms_synced_reads():
    """A GUARD for _synced's docstring (draw3_fix release item 8): its reading matches rsync's only for unanchored
    single names, optionally with a trailing "/". A pattern of another form must come with a new reading."""
    for e in P.EXCLUDE:
        assert not e.startswith("/") and "/" not in e.rstrip("/"), e


# ============================================================ draw4_build release 10(d); architecture round 3 m8
def test_r10d_the_fixture_is_pinned_with_the_golden_even_when_the_closure_does_not_name_it(world):
    """draw4_build release 10(d): the live golden's 51-key closure does not contain tools/ci_fixture.py (MEASURED by
    that adjudicator), so dropping it from SCORER left every test green -- the one fixture case above uses a golden
    with no closure, which pins every changed file anyway. CLOSURE here lacks it too."""
    head = _commit_golden(world)
    assert "tools/ci_fixture.py" not in CLOSURE
    write(world.dev, "tools/ci_fixture.py", "FIXTURE = 2\n")
    write(world.dev, P.GOLDEN, _golden(27.5, CLOSURE))
    assert world.publish() == 1 and world.said("Re-record the golden in its own commit")
    assert world.said("tools/ci_fixture.py") and world.head() == head and world.status() == ""


@pytest.mark.parametrize("argv", [["--spl"], ["--split"], ["--no-p"], ["--no-pu"], ["--adopt", "abc1234"]])
def test_m8_a_flag_that_relaxes_a_refusal_is_typed_whole(world, argv):
    """Round 3 m8 (Draw 4 section 5 item 10 predicted it): rebuilt from main()'s own add_argument calls, `--spl` set
    split_golden and `--no-p` set no_push. --split-golden relaxes golden_mixed()'s refusal, as --force-unpublished
    relaxes deploy's, and deploy.main() already refused abbreviations."""
    write(world.dev, "forge/probe.py", "PROBE = 2\n")
    head = world.head()
    with pytest.raises(SystemExit) as e:
        P.main(["-m", "publish under test"] + argv)
    assert e.value.code == 2 and world.head() == head and world.records_written() == []
