"""tools.deploy — give the deployed pipeline a VERSION, and make shipping reversible.

WHY THIS EXISTS (measured 2026-09-22, and it blocks the benchmark itself):
  * `/opt/wq` is not a git repository -- `git -C /opt/wq rev-parse` answers "not a git repository".
  * The deployed tree has drifted: `/opt/wq/forge/submit.py` is dated 2026-09-09 14:18 while the
    local file is 2026-09-22 23:15. Thirteen days of divergence that nothing reports.
  * Khoa's agreement D1 grades "a pipeline VERSION" and D14 grades "only the alphas that version
    produced". Neither sentence has a referent while the running code has no identity.
So: a version is the CONTENT of the deployed code, hashed. Not a tag anyone remembers to bump, not a
timestamp, not the source commit alone -- the bytes that are actually running. Two trees with the same
version id run the same code; different ids ran different code, whatever anyone believes.

WHAT IS CODE AND WHAT IS NOT. `PLAN` below is the whole deployable surface and it contains no state:
`state/` and `fetched/` are data the loop writes and reads, they differ between machines by design,
and hashing them would make every version unique and the identity worthless.

RULE 1 is not weakened here. Deploying is not simulating; nothing in this module passes `--live`, and
the smoke checks are a test run and a planner DRY run, both of which spend no quota.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: {path in this repo: path under the deploy root}. A trailing "/" means "the directory, recursively".
PLAN = {
    "forge/": "forge/",
    "tools/": "tools/",
    "fingerprint.py": "fingerprint.py",
    "operators.py": "operators.py",
    "vps/auth_daemon.py": "auth_daemon.py",
    "vps/forge_loop.sh": "forge_loop.sh",
    # MEASURED 2026-09-23 by importing every live-loop entry point and listing what was loaded: the
    # dispatcher tools/layered_sim.py imports harness13.massgen.mg.simulate at MODULE level, so the
    # whole loop depends on these three files; tools/auto_submit.py and tools/submit_plan.py import
    # harness/guards.py. None was in the plan -- /opt/wq ran only because the files happened to be
    # there -- so a fresh host could not import the dispatcher, and a change to simulate.py altered
    # dispatch without changing the version id. The first GitHub Actions run found it (5 collection
    # errors, ModuleNotFoundError). tools/tests/test_deploy.py now fails if the plan and the measured
    # closure ever diverge again.
    "harness13/__init__.py": "harness13/__init__.py",
    "harness13/crawl_fields.py": "harness13/crawl_fields.py",
    "harness13/massgen/mg/simulate.py": "harness13/massgen/mg/simulate.py",
    "harness/guards.py": "harness/guards.py",
}
#: Never shipped, never hashed: build artefacts and caches differ per machine and per Python build.
SKIP_PARTS = ("__pycache__", ".pytest_cache", ".DS_Store")
SKIP_SUFFIX = (".pyc", ".pyo", ".orig", ".rej")
MANIFEST_NAME = "DEPLOYED.json"


def _shippable(p: pathlib.Path) -> bool:
    return (p.is_file()
            and not any(part in SKIP_PARTS for part in p.parts)
            and not p.name.endswith(SKIP_SUFFIX))


def file_map(root=ROOT, plan=None) -> dict:
    """{remote path: local Path} for every file the plan ships, in a deterministic order."""
    plan = plan or PLAN
    out = {}
    for src, dst in sorted(plan.items()):
        base = pathlib.Path(root) / src.rstrip("/")
        if src.endswith("/"):
            for p in sorted(base.rglob("*")):
                if _shippable(p):
                    out[dst.rstrip("/") + "/" + str(p.relative_to(base))] = p
        elif _shippable(base):
            out[dst] = base
    return out


def content_hashes(fmap: dict) -> dict:
    """{remote path: sha256 of the bytes}. The bytes, not the mtime -- a touched file is not a change."""
    return {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in sorted(fmap.items())}


def version_id(hashes: dict) -> str:
    """The version IS the content: a hash over (path, content-hash) pairs, order-independent.

    Deliberately NOT the git SHA. A commit can be deployed partially, or a file edited and shipped
    without committing -- both happened on this desk. The git SHA is recorded beside this as
    provenance, never as the identity.
    """
    h = hashlib.sha256()
    for path, digest in sorted(hashes.items()):
        h.update(path.encode())
        h.update(b"\0")
        h.update(digest.encode())
        h.update(b"\n")
    return h.hexdigest()[:16]


def git_sha(root=ROOT):
    """The source commit, or None when the tree is not a repo. Provenance only."""
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=15)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def git_dirty(root=ROOT):
    """True when tracked files differ from HEAD. A dirty deploy is allowed but always recorded."""
    try:
        r = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                           capture_output=True, text=True, timeout=20)
        return bool(r.stdout.strip()) if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def manifest(root=ROOT, plan=None, now=None, fmap=None) -> dict:
    """`fmap` lets a caller hash exactly the file set it will ship: the third audit found push hashing
    one walk of the repository and shipping a second, so a file that appeared in between shipped with
    no snapshot and no rollback entry."""
    hashes = content_hashes(fmap if fmap is not None else file_map(root, plan))
    return {"version": version_id(hashes), "files": len(hashes), "hashes": hashes,
            "git_sha": git_sha(root), "git_dirty": git_dirty(root),
            "built_at": now if now is not None else time.time()}


def drift(local: dict, deployed: dict) -> dict:
    """What differs between two manifests' hash maps: added / removed / changed remote paths."""
    a, b = local.get("hashes", {}), deployed.get("hashes", {})
    return {"added": sorted(set(a) - set(b)),
            "removed": sorted(set(b) - set(a)),
            "changed": sorted(k for k in set(a) & set(b) if a[k] != b[k])}


# --------------------------------------------------------------------------------- shipping it
# Third version. The first failed its audit with a rollback that deleted 537 files and restored none;
# the second failed with a shell loop that never tested the last path, a snapshot name that the next
# push overwrote, and three return values nobody read. What changed in kind, not just in detail:
#   * every JUDGEMENT is a pure function with its own test (_existing_from, _smoke_ok, _is_active,
#     snapshot_tag); ssh is only a pipe, so a shell quirk can no longer decide anything;
#   * path lists travel NUL-separated, so no newline, space or quote in a path can reach a shell;
#   * every return value is read, and push() has one exit code per outcome (see EXIT below).
# RULE 1 is not weakened: nothing here simulates and nothing passes --live.

HOST = "root@160.25.88.163"
REMOTE = "/opt/wq"
SNAPSHOT_DIR = ".deploy"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=30", HOST]
#: The processes that must not be running when code is swapped or the unit restarted. forge_loop.sh
#: holds /var/lock/wq_forge.lock for its whole life (`exec 9>`), so that lock cannot be borrowed;
#: these are the children that import code mid-run (submit.py and harvest.py import lazily) or that
#: a restart would SIGTERM mid-POST.
BUSY = r"forge/[a-z0-9_/]+\.py"   # third audit: recover_orphans.py and the arm drivers were invisible;
                                  # digits matter -- forge/offline/c11_neut.py (caught by its own test)
#: Stopped for the whole swap, so no process can import a half-shipped tree and nothing runs the new
#: code before the smoke has judged it (third audit). wq-harvest is its own unit and writes the journal.
UNITS = ("wq-forge", "wq-harvest")
PLANNER_SEED = 900_000_000     # far above hand-picked seeds; the smoke still walks to a free one
EXIT = {"deployed": 0, "rolled_back": 1, "refused": 2, "rollback_failed": 3, "unrecorded": 4}


def _remote(cmd: str, stdin=None, timeout=900):
    return subprocess.run(SSH + [cmd], input=stdin, capture_output=True, text=True, timeout=timeout)


# ------------------------------------------------------------------------------ pure judgements
def _existing_from(stdout: str, asked) -> set:
    """Parse the existence probe. Refuse a listing that did not check every path it was sent.

    The probe prints each existing path, then `CHECKED <n>`. The second audit showed a shell loop
    that silently skipped the last path; a count that must equal what was asked is the only
    defence that does not depend on trusting the loop.
    """
    lines = [l for l in (stdout or "").splitlines() if l.strip()]
    if not lines or not lines[-1].startswith("CHECKED "):
        raise RuntimeError("existence probe returned no CHECKED trailer")
    n = int(lines[-1].split()[1])
    if n != len(asked):
        raise RuntimeError("existence probe checked %d of %d paths" % (n, len(asked)))
    body = lines[:-1]
    bad = [l[len("BADPARENT "):] for l in body if l.startswith("BADPARENT ")]
    if bad:
        # rsync replaces a regular file that sits where a directory must go, silently (third audit,
        # reproduced on the target's rsync 3.4.1) -- that file would be lost with no snapshot of it
        raise RuntimeError("a parent of a shipped path is a regular file on the target: %s" % bad[:3])
    found = set(l for l in body if not l.startswith("BADPARENT "))
    stray = found - set(asked)
    if stray:
        raise RuntimeError("existence probe reported paths it was not asked about: %s" % sorted(stray)[:3])
    return found


def _smoke_ok(name: str, rc: int, out: str) -> bool:
    """A smoke check's verdict. The planner's exit 2 is healthy ONLY with its own message:
    runner.py returns 2 for 'the library is exhausted', and argparse ALSO exits 2 on a bad argument
    -- accepting every 2 would pass a smoke that never planned anything (audit, second pass)."""
    if name == "planner":
        return rc == 0 or (rc == 2 and "library is exhausted" in (out or ""))
    return rc == 0


def _is_active(stdout: str) -> bool:
    """`systemctl is-active` prints 'inactive' for a dead unit; 'active' is a substring of it."""
    return (stdout or "").strip().splitlines()[-1:] == ["active"]


def snapshot_tag(remote_version, now=None) -> str:
    """Unique per push. The second version derived it from the target's manifest alone, so on a
    target with no manifest every push wrote `pre-unversioned.tgz` over the previous one -- the only
    copy of the tree it was meant to restore."""
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(now if now is not None else time.time()))
    return "pre-%s-%s" % (remote_version or "unversioned", stamp)


# ----------------------------------------------------------------------------- the remote pipes
def round_in_flight() -> bool:
    """True when a forge child is running -- and True when we cannot tell. A guard that answers
    'safe' because ssh failed is not a guard (first audit: it did exactly that)."""
    try:
        r = _remote("pgrep -fc %s; true" % shlex.quote(BUSY), timeout=60)
    except (OSError, subprocess.SubprocessError):
        return True
    out = (r.stdout or "").strip().splitlines()[-1:] or [""]
    if r.returncode != 0 or not out[0].isdigit():
        return True
    return int(out[0]) > 0


def remote_manifest():
    """(manifest or None, readable). Readable is False whenever we could not ASK; only an explicit
    'absent' from the target counts as 'never deployed'. Conflating the two armed the virgin branch
    on an established target after one network blip (first audit, A3)."""
    cmd = ("cd %s && if [ -e %s ]; then cat %s; else echo __ABSENT__; fi"
           % (shlex.quote(REMOTE), MANIFEST_NAME, MANIFEST_NAME))
    try:
        r = _remote(cmd, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None, False
    if r.returncode != 0:
        return None, False
    body = (r.stdout or "").strip()
    if body == "__ABSENT__":
        return None, True
    try:
        return json.loads(body), True
    except ValueError:
        return None, False


def remote_existing(paths) -> set:
    """The subset of `paths` present on the target, verified complete (see _existing_from)."""
    prog = ("import sys,os\n"
            "ps=[p for p in sys.stdin.buffer.read().decode().split('\\0') if p]\n"
            "[print(p) for p in ps if os.path.lexists(p)]\n"
            "bad=set()\n"
            "for p in ps:\n"
            "    d=os.path.dirname(p)\n"
            "    while d:\n"
            "        if os.path.lexists(d) and not os.path.isdir(d): bad.add(d)\n"
            "        d=os.path.dirname(d)\n"
            "[print('BADPARENT '+b) for b in sorted(bad)]\n"
            "print('CHECKED %d'%len(ps))\n")
    r = _remote("cd %s && venv/bin/python -c %s" % (shlex.quote(REMOTE), shlex.quote(prog)),
                stdin="\0".join(paths) + "\0", timeout=300)
    if r.returncode != 0:
        raise RuntimeError("existence probe failed (rc %s): %s" % (r.returncode, (r.stderr or "")[:200]))
    return _existing_from(r.stdout, list(paths))


def snapshot(paths, tag, out=print):
    """(tar path, members) for the target's CURRENT copies of `paths`, verified member-for-member.
    With nothing to archive -- a genuinely virgin target -- returns ("", 0), which is a valid
    snapshot: the rollback then only has to remove what the deploy added."""
    paths = sorted(paths)
    if not paths:
        out("  snapshot: target holds none of the plan paths; nothing to archive")
        return "", 0
    tar = "%s/%s.tgz" % (SNAPSHOT_DIR, tag)
    q = shlex.quote
    cmd = ("cd %s && mkdir -p %s && tar -czf %s --null -T - && tar -tzf %s | wc -l"
           % (q(REMOTE), q(SNAPSHOT_DIR), q(tar), q(tar)))
    r = _remote(cmd, stdin="\0".join(paths) + "\0", timeout=600)
    tail = (r.stdout or "").strip().splitlines()[-1:] or ["0"]
    n = int(tail[0]) if tail[0].isdigit() else 0
    if r.returncode != 0 or n != len(paths):
        out("  snapshot FAILED: rc %s, %d of %d members  %s" % (r.returncode, n, len(paths), (r.stderr or "")[:160]))
        return None
    out("  snapshot -> %s (%d of %d members verified)" % (tar, n, len(paths)))
    return tar, n


def rollback(tar, to_delete, out=print) -> bool:
    """RESTORE FIRST, then remove only what did not exist before this deploy."""
    q = shlex.quote
    restore = ("tar -xzf %s" % q(tar)) if tar else "true"
    cmd = ("cd %s && %s && echo EXTRACTED && xargs -0 -r rm -f -- && echo REMOVED"
           % (q(REMOTE), restore))
    try:
        r = _remote(cmd, stdin="\0".join(sorted(to_delete)) + ("\0" if to_delete else ""), timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        out("  ROLLBACK COULD NOT RUN: %s" % exc)
        return False
    o = r.stdout or ""
    if "EXTRACTED" not in o or "REMOVED" not in o:
        out("  ROLLBACK INCOMPLETE (extracted=%s removed=%s): %s"
            % ("EXTRACTED" in o, "REMOVED" in o, (r.stderr or "")[:200]))
        return False
    out("  rollback: snapshot restored, %d added path(s) removed" % len(to_delete))
    return True


def write_manifest(local, out=print) -> bool:
    """Atomically: a truncate-then-write left invalid JSON on a partial write, which wedged every
    later push (second audit)."""
    q = shlex.quote
    cmd = "cd %s && cat > %s.tmp && mv -f %s.tmp %s" % (q(REMOTE), MANIFEST_NAME, MANIFEST_NAME, MANIFEST_NAME)
    r = _remote(cmd, stdin=json.dumps(local, indent=1), timeout=120)
    ok = r.returncode == 0
    out("  manifest %s" % ("written" if ok else "FAILED: " + (r.stderr or "")[:160]))
    return ok


def units_state() -> dict:
    r = _remote("systemctl is-active %s; true" % " ".join(UNITS), timeout=60)
    states = (r.stdout or "").split()
    return dict(zip(UNITS, states)) if len(states) == len(UNITS) else {}


def stop_units(out=print) -> bool:
    """Stop the loop and the harvester for the swap. True only if both are verifiably not active."""
    _remote("systemctl stop %s" % " ".join(UNITS), timeout=180)
    st = units_state()
    ok = bool(st) and all(v != "active" for v in st.values())
    out("  units stopped: %s" % (st if st else "COULD NOT READ"))
    return ok


def start_units(out=print) -> bool:
    """Start both units and confirm each reads exactly 'active' (not a substring of 'inactive')."""
    _remote("systemctl start %s" % " ".join(UNITS), timeout=180)
    time.sleep(3)
    st = units_state()
    ok = bool(st) and all(_is_active(v) for v in st.values())
    out("  units started: %s" % (st if st else "COULD NOT READ"))
    return ok


#: (name, remote shell command). Every command runs from REMOTE. The planner leaves no plan behind:
#: runner.py writes state/forge/plans/<seed>.json even on a dry run, and digest.py reads the newest
#: plan by mtime, so a smoke plan left there becomes the day's reported plan.
SMOKE = (
    ("import", "venv/bin/python -c %s" % shlex.quote(
        "import sys; sys.path[:0]=['.','tools']; import fingerprint, operators; "
        "from forge import submit, runner, harvest, novelty, allocate, score; print('imports ok')")),
    ("tests", "venv/bin/python -m pytest forge/tests -q --no-header -x"),
    # the seed is chosen FREE on the target: `rm -f plans/<seed>.json` with a fixed seed deletes a
    # pre-existing plan whenever the seed collides (measured locally 2026-09-23, 157 -> 156 plans)
    ("planner", "s=%d; while [ -e state/forge/plans/$s.json ]; do s=$((s+1)); done; "
                "venv/bin/python forge/runner.py --mode composites --order USA/d1,d1 --no-split "
                "--delays 1 --ab new -n 20 --seed $s; rc=$?; rm -f state/forge/plans/$s.json; exit $rc"
                % PLANNER_SEED),
)


def run_smoke(out=print) -> list:
    results = []
    for name, cmd in SMOKE:
        r = _remote("cd %s && %s" % (shlex.quote(REMOTE), cmd))
        text = (r.stdout or "") + (r.stderr or "")
        ok = _smoke_ok(name, r.returncode, text)
        tail = text.strip().splitlines()[-3:]
        results.append((name, ok, tail))
        out("  smoke %-8s %s (exit %s)" % (name, "ok" if ok else "FAILED", r.returncode))
        for line in tail:
            out("      %s" % line[:160])
        if not ok:
            break
    return results


def _stage(fmap) -> pathlib.Path:
    """Build the upload tree OUTSIDE the repository (the second audit found the tests leaving 5 MB of
    staged files in the repo root) and with copy2, which keeps the executable bit forge_loop.sh needs."""
    staged = pathlib.Path(tempfile.mkdtemp(prefix="wq-deploy-"))
    # mkdtemp is 0700 and `rsync -a` carries the root's mode onto the target: /opt/wq became 0700
    # (third audit, reproduced). The target's own mode is 755.
    staged.chmod(0o755)
    for remote_path, local_path in fmap.items():
        dest = staged / remote_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)
    return staged


#: One line per deploy ATTEMPT that got past the guards (refusals are not deploys). This is the raw
#: material of the four DORA keys, computed in forge/offline/benchmark.py: frequency, lead time
#: (commit -> live), change-failure rate, and time to restore.
DEPLOY_LOG = ROOT / "state/deploys.jsonl"


def git_commit_time(sha, root=ROOT):
    if not sha:
        return None
    try:
        r = subprocess.run(["git", "-C", str(root), "show", "-s", "--format=%ct", sha],
                           capture_output=True, text=True, timeout=15)
        return float(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def push(force=False, out=print) -> int:
    """Ship, verify, undo on failure -- and record every attempt that reached the swap."""
    started = time.time()
    rc = _push(force=force, out=out)
    if rc != EXIT["refused"]:
        outcome = {v: k for k, v in EXIT.items()}.get(rc, "unknown")
        local = manifest()
        row = {"started_at": started, "finished_at": time.time(), "outcome": outcome, "exit": rc,
               "version": local["version"], "git_sha": local["git_sha"], "git_dirty": local["git_dirty"],
               "commit_time": git_commit_time(local["git_sha"])}
        try:
            DEPLOY_LOG.parent.mkdir(parents=True, exist_ok=True)
            with DEPLOY_LOG.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
        except OSError as exc:
            out("  could not record the deploy in %s: %s" % (DEPLOY_LOG, exc))
    return rc


def _staged_matches(staged: pathlib.Path, hashes: dict) -> list:
    """Paths whose staged bytes differ from the hash that was checked and snapshotted."""
    return sorted(k for k, h in hashes.items()
                  if hashlib.sha256((staged / k).read_bytes()).hexdigest() != h)


def _push(force=False, out=print) -> int:
    """Ship, verify, and undo on failure. Exit codes: see EXIT.

    Order, and why: ONE file map is hashed, probed, snapshotted, staged and verified, so what ships is
    exactly what can be rolled back; the loop and the harvester are STOPPED before the swap, so no
    process runs code the smoke has not judged; they are started again only when the tree is in a
    known state (green, or restored). A FAILED rollback leaves them stopped on purpose: starting the
    loop on a half-swapped tree spends real quota on code nobody can name.
    Run it from a terminal, not inside a tool call with a short timeout: SIGKILL skips every rollback.
    """
    if not force and round_in_flight():
        out("a forge process is running (or the target could not be asked); refusing to swap code")
        return EXIT["refused"]
    fmap = file_map()
    local = manifest(fmap=fmap)
    remote, readable = remote_manifest()
    if not readable:
        out("could not read %s on the target; refusing rather than guess it was never deployed" % MANIFEST_NAME)
        return EXIT["refused"]
    out("local  %s (%d files, git %s%s)" % (local["version"], local["files"], (local["git_sha"] or "-")[:8],
                                          ", DIRTY" if local["git_dirty"] else ""))
    out("target %s" % (remote["version"] if remote else "never deployed by this tool"))
    if remote and remote.get("version") == local["version"]:
        out("nothing to do: the target already runs this exact content")
        return EXIT["deployed"]

    plan_paths = sorted(local["hashes"])
    try:
        present = remote_existing(plan_paths)
    except RuntimeError as exc:
        out("%s -- refusing to deploy blind" % exc)
        return EXIT["refused"]
    to_delete = sorted(set(plan_paths) - present)
    out("target has %d of %d plan paths; %d are new" % (len(present), len(plan_paths), len(to_delete)))

    staged = None
    try:
        staged = _stage(fmap)
        drifted = _staged_matches(staged, local["hashes"])
        if drifted:
            out("the working tree changed while staging (%s); refusing" % drifted[:3])
            return EXIT["refused"]
    except BaseException:
        if staged is not None:
            shutil.rmtree(staged, ignore_errors=True)
        raise

    snap = snapshot(present, snapshot_tag(remote.get("version") if remote else None), out=out)
    if snap is None:
        shutil.rmtree(staged, ignore_errors=True)
        out("no verified snapshot -- refusing: a deploy without a rollback is a one-way door")
        return EXIT["refused"]
    tar, _ = snap

    swapped = stopped = False
    results = []
    try:
        if not force and round_in_flight():
            out("a forge process started while preparing; refusing")
            return EXIT["refused"]
        stopped = True
        if not stop_units(out=out):
            out("could not verify the units stopped; refusing to swap under a live loop")
            start_units(out=out)
            return EXIT["refused"]
        swapped = True
        r = subprocess.run(["rsync", "-a", "--no-owner", "--no-group", str(staged) + "/", "%s:%s/" % (HOST, REMOTE)],
                           capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            out("rsync FAILED: %s" % (r.stderr or "")[:300])
            return _undo(tar, to_delete, out)
        out("shipped %d file(s)" % len(local["hashes"]))
        results = run_smoke(out=out)
        if not all(ok for _, ok, _ in results):
            failed = next(n for n, ok, _ in results if not ok)
            out("smoke FAILED at '%s' -- rolling back" % failed)
            return _undo(tar, to_delete, out)
    except BaseException as exc:  # noqa: BLE001 -- includes KeyboardInterrupt
        if swapped:
            out("deploy interrupted (%s: %s) -- rolling back" % (type(exc).__name__, exc))
            rc = _undo(tar, to_delete, out)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            return rc
        if stopped:
            start_units(out=out)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        out("deploy failed before anything was swapped (%s: %s)" % (type(exc).__name__, exc))
        return EXIT["refused"]
    finally:
        shutil.rmtree(staged, ignore_errors=True)

    recorded = write_manifest(local, out=out)
    running = start_units(out=out)
    if not recorded or not running:
        out("DEPLOYED %s but %s -- the code is live and green, and %s"
            % (local["version"], "the manifest was not written" if not recorded else "the units did not come back",
               "the record of it is not" if not recorded else "NOTHING IS RUNNING"))
        return EXIT["unrecorded"]
    out("DEPLOYED %s -- smoke green (%s), units running" % (local["version"], ", ".join(n for n, _, _ in results)))
    return EXIT["deployed"]


def _undo(tar, to_delete, out) -> int:
    """Roll back; restart the units only if the tree is back in its known state."""
    if rollback(tar, to_delete, out=out):
        start_units(out=out)
        return EXIT["rolled_back"]
    out("ROLLBACK FAILED -- wq-forge and wq-harvest are LEFT STOPPED on purpose: the tree is in an "
        "unknown state and starting the loop would spend real quota on it. Restore from %s by hand." % tar)
    return EXIT["rollback_failed"]


def _print_drift(d, header):
    n = sum(len(v) for v in d.values())
    print("%s: %d file(s) differ" % (header, n))
    for kind, paths in d.items():
        for p in paths[:20]:
            print("  %-8s %s" % (kind, p))
    return 1 if n else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("version", "manifest", "drift", "push", "remote"))
    ap.add_argument("--force", action="store_true", help="deploy even while a forge child is running")
    ap.add_argument("--against", default="", help="a DEPLOYED.json to compare with (drift)")
    a = ap.parse_args(argv)
    m = manifest()
    if a.cmd == "version":
        print("%s  (%d files, git %s%s)" % (m["version"], m["files"], (m["git_sha"] or "-")[:8],
                                            ", DIRTY" if m["git_dirty"] else ""))
        return 0
    if a.cmd == "manifest":
        print(json.dumps(m, indent=1))
        return 0
    if a.cmd == "push":
        return push(force=a.force)
    if a.against:
        return _print_drift(drift(m, json.loads(pathlib.Path(a.against).read_text())), "drift")
    rm, readable = remote_manifest()
    if not readable:
        print("could not read %s on the target" % MANIFEST_NAME)
        return 2
    if a.cmd == "remote":
        print(json.dumps(rm, indent=1) if rm else "the target carries no %s" % MANIFEST_NAME)
        return 0
    if rm is None:
        print("the target carries no %s; run `push` first" % MANIFEST_NAME)
        return 2
    return _print_drift(drift(m, rm), "drift vs target %s" % rm["version"])


if __name__ == "__main__":
    sys.exit(main())
