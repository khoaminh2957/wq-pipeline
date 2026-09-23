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
import subprocess
import sys
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


def manifest(root=ROOT, plan=None, now=None) -> dict:
    hashes = content_hashes(file_map(root, plan))
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
#: The deploy target. RULE 1: this module ships code TO the VPS and runs read-only checks there;
#: it never simulates and never passes --live.
HOST = "root@160.25.88.163"
REMOTE = "/opt/wq"
SNAPSHOT_DIR = ".deploy"

#: The smoke suite, run ON the target AFTER the files land and BEFORE the deploy is called good.
#: Each entry is (name, argv). A non-zero exit from any of them rolls the deploy back.
#: What each one buys, measured rather than assumed:
#:   import   -- the 2026-09-22 audit found forge/novelty.py importing two repo-root modules absent
#:               from /opt/wq, which killed every submit invocation while forge_loop.sh swallowed the
#:               traceback into an unchecked shell variable. An import check is the cheapest guard
#:               against exactly that class, and it is the one that would have caught it.
#:   tests    -- the suite the desk already maintains, run against the DEPLOYED bytes, not the local ones.
#:   planner  -- a real round plan with no --live: it exercises the library, the allocator, the type
#:               gate and the A/B split, and spends no quota.
#: (name, argv, exit codes that count as healthy). The third field exists because `forge/runner.py`
#: returns 2 for "the library is exhausted for every reachable cell" and `vps/forge_loop.sh:63`
#: treats that as an ordinary round outcome. Accepting only 0 would have made a perfectly healthy
#: pipeline trigger a rollback -- the audit named it the most likely ignition, needing no failure.
SMOKE = (
    ("import", ["venv/bin/python", "-c",
                "import sys; sys.path[:0]=['.','tools']; "
                "import fingerprint, operators; "
                "from forge import submit, runner, harvest, novelty, allocate, score; "
                "print('imports ok')"], (0,)),
    ("tests", ["venv/bin/python", "-m", "pytest", "forge/tests", "-q", "--no-header", "-x"], (0,)),
    ("planner", ["venv/bin/python", "forge/runner.py", "--mode", "composites", "--order", "USA/d1,d1",
                 "--no-split", "--delays", "1", "--ab", "new", "-n", "20", "--seed", "999"], (0, 2)),
)


def _ssh(args, timeout=900, raw=None):
    """Run argv (or a raw command) on the target. BatchMode refuses any interactive prompt, so a key
    problem fails fast instead of hanging a deploy at a password prompt."""
    cmd = raw if raw is not None else "cd %s && %s" % (shlex.quote(REMOTE), " ".join(shlex.quote(a) for a in args))
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=30", HOST, cmd],
                          capture_output=True, text=True, timeout=timeout)


def round_in_flight():
    """True when a round is dispatching, and True when we CANNOT TELL.

    Fails closed on purpose: the audit demonstrated the first version returning False -- "go ahead" --
    when ssh was refused, when auth failed and when pgrep was absent. A guard that answers "safe"
    because it could not look is not a guard.
    """
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", HOST,
                        "pgrep -fc '[r]unner.py'"], capture_output=True, text=True, timeout=60)
    # pgrep exits 1 with "0" when nothing matches; any other non-zero is our own failure to look
    out = (r.stdout or "").strip()
    if r.returncode not in (0, 1) or not out.isdigit():
        return True
    return int(out) > 0


def remote_manifest():
    """(manifest_or_None, readable). `readable` is False when we could not ask the target at all.

    The distinction is the whole point: the audit showed that treating "could not read" as "never
    deployed" arms the virgin-deploy branch -- which removes every plan path on rollback -- on an
    established target, after nothing worse than a network blip.
    """
    r = _ssh(["cat", MANIFEST_NAME], timeout=60)
    if r.returncode != 0:
        missing = "No such file" in (r.stderr or "")
        return None, missing            # readable only if the target genuinely has no manifest
    if not (r.stdout or "").strip():
        return None, True
    try:
        return json.loads(r.stdout), True
    except ValueError:
        return None, False


def remote_existing(paths):
    """The subset of `paths` that already exists on the target.

    Needed because "added" cannot be derived from the manifest: the audit measured 499 of 537 plan
    paths already present on a target that carries no manifest at all. Those are OVERWRITES, and a
    rollback must restore them, never delete them.
    """
    listing = "\n".join(sorted(paths))
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=30", HOST,
                        "cd %s && while IFS= read -r f; do [ -e \"$f\" ] && printf '%%s\\n' \"$f\"; done" % shlex.quote(REMOTE)],
                       input=listing, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError("could not list the target: %s" % (r.stderr or "")[:200])
    return {l for l in (r.stdout or "").splitlines() if l.strip()}


def snapshot(paths, tag, out=print):
    """Archive the target's CURRENT copies of `paths`, and VERIFY the archive before trusting it.

    Returns (tar_path, member_count), or None when the archive could not be made or is empty. The
    first version ended its remote command with `; echo done`, so it printed success whatever
    happened, and push() shipped on the strength of that word. An unverified rollback is not a
    rollback.
    """
    listing = "\n".join(sorted(paths))
    tar = "%s/%s.tgz" % (SNAPSHOT_DIR, tag)
    q = shlex.quote
    cmd = ("cd %s && mkdir -p %s && cat > %s/%s.files && "
           "tar -czf %s -T %s/%s.files --ignore-failed-read && "
           "tar -tzf %s | wc -l"
           % (q(REMOTE), q(SNAPSHOT_DIR), q(SNAPSHOT_DIR), q(tag),
              q(tar), q(SNAPSHOT_DIR), q(tag), q(tar)))
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=30", HOST, cmd],
                       input=listing, capture_output=True, text=True, timeout=600)
    count = (r.stdout or "").strip().splitlines()[-1:] or ["0"]
    try:
        n = int(count[0])
    except ValueError:
        n = 0
    if r.returncode != 0 or n <= 0:
        out("  snapshot FAILED (rc=%s, %d member(s)): %s" % (r.returncode, n, (r.stderr or "")[:160]))
        return None
    out("  snapshot -> %s (%d member(s) verified)" % (tar, n))
    return tar, n


def rollback(tar, to_delete, out=print) -> bool:
    """RESTORE FIRST, then remove only what did not exist before this deploy.

    Order matters and the first version had it backwards: it deleted every path and then extracted,
    with the extraction guarded by an `&&` that the deletions had already passed. If the archive was
    missing or empty the tree was simply gone. Here the extraction must succeed before anything is
    removed, and `to_delete` holds only paths the target did NOT have.
    """
    q = shlex.quote
    rm = " && ".join("rm -f %s" % q(p) for p in sorted(to_delete)) if to_delete else "true"
    cmd = "cd %s && tar -xzf %s && echo EXTRACTED && (%s) && echo REMOVED" % (q(REMOTE), q(tar), rm)
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=30", HOST, cmd],
                       capture_output=True, text=True, timeout=600)
    o = r.stdout or ""
    if "EXTRACTED" not in o:
        out("  ROLLBACK FAILED TO RESTORE -- the target keeps the new code: %s" % (r.stderr or "")[:200])
        return False
    out("  ROLLBACK restored the snapshot%s" % ("" if "REMOVED" in o else " (but could not remove the added paths)"))
    return True


def write_manifest(local, out=print) -> bool:
    """Record the version AFTER the smoke is green, as its own step.

    Writing it inside the same rsync as the code meant a rolled-back first deploy left a manifest
    claiming a version that is not installed -- and the next push then answered "nothing to do"
    for ever.
    """
    r = _ssh(["sh", "-c", "cat > %s" % shlex.quote(MANIFEST_NAME)]) if False else subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=30", HOST,
         "cd %s && cat > %s" % (shlex.quote(REMOTE), shlex.quote(MANIFEST_NAME))],
        input=json.dumps(local, indent=1), capture_output=True, text=True, timeout=120)
    ok = r.returncode == 0
    out("  manifest %s" % ("written" if ok else "FAILED: " + (r.stderr or "")[:160]))
    return ok


def restart_loop(out=print) -> bool:
    """Restart wq-forge so the running driver is the one that was just deployed.

    A green deploy that leaves the old `forge_loop.sh` running means the target executes new Python
    under an old driver while the manifest asserts a single version -- which is exactly the drift the
    version id exists to abolish. EX-ANTE: the loop re-reads its Python each round, so the window is
    one round; the restart closes it.
    """
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=30", HOST,
                        "systemctl restart wq-forge && sleep 3 && systemctl is-active wq-forge"],
                       capture_output=True, text=True, timeout=180)
    ok = "active" in (r.stdout or "")
    out("  wq-forge %s" % ("restarted" if ok else "RESTART FAILED: " + (r.stderr or "")[:160]))
    return ok


def run_smoke(out=print) -> list:
    """[(name, ok, tail)] for every smoke check, stopping at the first failure."""
    results = []
    for name, argv, good_codes in SMOKE:
        r = _ssh(argv)
        ok = r.returncode in good_codes
        tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
        results.append((name, ok, tail[-3:] if tail else []))
        out("  smoke %-8s %s (exit %s)" % (name, "ok" if ok else "FAILED", r.returncode))
        for line in results[-1][2]:
            out("      %s" % line[:160])
        if not ok:
            break
    return results


def push(force=False, out=print) -> int:
    """Ship the plan, verify it on the target, and undo the swap if verification fails."""
    if not force and round_in_flight():
        out("a round is dispatching (or the target could not be asked); refusing to swap code under it")
        return 2
    local = manifest()
    remote, readable = remote_manifest()
    if not readable:
        out("could not read %s on the target; refusing rather than guess that it was never deployed" % MANIFEST_NAME)
        return 2
    out("local version  %s (%d files, git %s%s)" % (local["version"], local["files"],
                                                    (local["git_sha"] or "-")[:8], ", DIRTY" if local["git_dirty"] else ""))
    out("target version %s" % (remote["version"] if remote else "NONE (never deployed by this tool)"))
    if remote and local["version"] == remote["version"]:
        out("nothing to do: the target already runs this exact content")
        return 0

    plan_paths = list(local["hashes"])
    try:
        present = remote_existing(plan_paths + [MANIFEST_NAME])
    except RuntimeError as exc:
        out("%s -- refusing to deploy blind" % exc)
        return 2
    to_delete = sorted(set(plan_paths) - present)          # only genuinely new paths may be removed
    out("target already has %d of %d plan paths; %d would be new" % (len(present & set(plan_paths)), len(plan_paths), len(to_delete)))

    snap = snapshot(sorted(present), "pre-%s" % (remote["version"] if remote else "unversioned"), out=out)
    if snap is None:
        out("no verified snapshot -- refusing to deploy, because a deploy without a rollback is a one-way door")
        return 2
    tar, _ = snap

    staged = ROOT / ".deploy_stage"
    try:
        fmap = file_map()
        subprocess.run(["rm", "-rf", str(staged)], check=True)
        for remote_path, local_path in fmap.items():
            dest = staged / remote_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(local_path.read_bytes())
        # NO --delete of any kind: /opt/wq also holds state/ (the only journal), venv/ and fetched/.
        r = subprocess.run(["rsync", "-a", str(staged) + "/", "%s:%s/" % (HOST, REMOTE)],
                           capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            out("rsync FAILED: %s" % (r.stderr or "")[:300])
            rollback(tar, to_delete, out=out)
            return 1
        out("shipped %d file(s)" % len(fmap))
        results = run_smoke(out=out)
        if not all(ok for _, ok, _ in results):
            failed = next(n for n, ok, _ in results if not ok)
            out("smoke FAILED at '%s' -- rolling back" % failed)
            rollback(tar, to_delete, out=out)
            return 1
    except Exception as exc:  # noqa: BLE001 -- ANY failure after the swap must reach the rollback
        out("deploy raised (%s: %s) -- rolling back" % (type(exc).__name__, exc))
        rollback(tar, to_delete, out=out)
        return 1
    finally:
        subprocess.run(["rm", "-rf", str(staged)], check=False)

    write_manifest(local, out=out)
    restart_loop(out=out)
    out("DEPLOYED %s -- smoke green (%s)" % (local["version"], ", ".join(n for n, _, _ in results)))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("version", "manifest", "drift", "push", "remote"))
    ap.add_argument("--force", action="store_true", help="deploy even while a round is dispatching")
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
    if a.cmd == "remote":
        rm = remote_manifest()
        print(json.dumps(rm, indent=1) if rm else "the target carries no %s" % MANIFEST_NAME)
        return 0
    if not a.against:
        # with no file given, compare against what the target reports
        rm = remote_manifest()
        if rm is None:
            print("the target carries no %s; run `push` first" % MANIFEST_NAME)
            return 2
        d = drift(m, rm)
        n = sum(len(v) for v in d.values())
        print("drift vs target %s: %d file(s) differ" % (rm["version"], n))
        for kind, paths in d.items():
            for p in paths[:20]:
                print("  %-8s %s" % (kind, p))
        return 1 if n else 0
    d = drift(m, json.loads(pathlib.Path(a.against).read_text()))
    n = sum(len(v) for v in d.values())
    print("drift: %d file(s) differ" % n)
    for kind, paths in d.items():
        for p in paths[:20]:
            print("  %-8s %s" % (kind, p))
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
