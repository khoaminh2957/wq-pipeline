"""tools.ci_publish — the ONLY way pipeline code reaches the GitHub repository (the data-tier presubmit).

WHY THIS EXISTS (architecture round 1, missed by all three reviewers). The gate's hermetic tier skips
167 tests and the branch drill "covered instead by the data tier" -- but nothing ran the data tier
before a push, and the CI repository lived in a session scratchpad under /private/tmp, synced by hand.
The claim was false. This script makes it true, in order:

  0. THE CHECKOUT IS OURS (round 2, A12): fetch, then refuse unless HEAD is the commit this script last
     made, nothing is uncommitted, and origin/main holds nothing the checkout lacks. Checked again
     immediately before the sync, which may come many minutes later.
  1. DATA TIER, here, where the journal and catalogues exist: the full gate -- every test, the drill.
     A failure refuses the publish unless tools/ci_gate.py's known-red verdict allows it (A8: listed in
     tools/ci_known_red.json by exact node id AND failing with the listed text; draw-3 SERIOUS 2). Such a
     known-red test (Khoa's D23) is allowed through and named: CI keeps blocking on it, as he chose.
  2. CLASSIFICATION: if tests or code changed since the last one, re-measure it (two arms, same code).
     The clean arm is a THROWAWAY export of the CI repository's HEAD with the dev subset laid over it --
     it holds no state/ and no fetched/ data -- never the durable checkout (A12).
  3. SYNC: exactly the pipeline subset (D22) into the durable checkout, only now that steps 1 and 2
     passed. The synced tree must be the tested tree (M9-NL). A golden card re-recorded in the same
     commit as any file it pins -- the scorer's whole closure (D42) -- is refused (S8-NL). Secret-scanned
     before commit. Any refusal here puts the checkout back at HEAD.
  4. COMMIT + PUSH.
  5. RECORD the publish in state/ci_publish_records.jsonl: tools/deploy.py refuses to push a tree
     without one (M9-NL). Then print the Actions run to watch -- after the record, so a missing `gh`
     cannot cost it (draw-3 release adjudicator, item 11).

Nothing here simulates, and nothing touches the VPS.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

DEV = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEV / "tools"))
import deploy as D  # noqa: E402  -- the identity a publish record is keyed by is deploy's own

CI = DEV.parent / "wq-pipeline"
REMOTE = "https://github.com/khoaminh2957/wq-pipeline.git"
#: D22: the pipeline, its measured dependency closure, and the evalharness documents -- nothing else.
#: ".github" (round 2, M9-NL): the workflow that DEFINES the gate was outside the subset, so it could
#: change only through a plain push that nothing here had tested.
SUBSET = ["forge", "tools", "vps", "fingerprint.py", "operators.py",
          "harness13/__init__.py", "harness13/crawl_fields.py", "harness13/massgen/mg/simulate.py",
          "harness/guards.py", "docs/evalharness", ".github"]
EXCLUDE = ["__pycache__", "*.pyc", ".pytest_cache", "staged/", ".DS_Store"]
SECRET = re.compile(r"discord\.com/api/webhooks/[0-9]{6}|BEGIN (RSA|OPENSSH) PRIVATE|"
                    r"password[\"' ]*[:=][\"' ]*[A-Za-z0-9!@#$%^&*]{8,}")
#: A12: the commit ci_publish last made (or was told to adopt), kept inside the checkout's own .git so
#: no commit can carry it and a fresh clone starts without one.
LAST = ".git/ci_publish_last"
#: S8-NL: the golden card pins the scorer's judgement, and cac48d7 changed the scorer, the fixture and
#: the golden in ONE commit -- the judgement moved with no separate, visible act.
GOLDEN = "tools/ci_golden_card.json"
#: Always pinned with the golden, whatever its closure says: the scorer's entry point and the fixture that
#: feeds it. D42 adds every file of the golden's own `scorer_closure` (golden_mixed).
SCORER = ("forge/offline/benchmark.py", "tools/ci_fixture.py")
#: rewritten by step 2, so it is left out of the "tested bytes == synced bytes" comparison
CLASSIFICATION = "tools/ci_data_bound.json"


def sh(argv, cwd=None, check=True, timeout=3600):
    r = subprocess.run(argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise SystemExit("FAILED: %s\n%s" % (" ".join(map(str, argv)), (r.stderr or r.stdout)[-800:]))
    return r


def data_tier(out=print) -> dict:
    """Run the gate here. {"ok", "verdict": "green" | "known-red-only" | "red" | "not-run", "known_red": [...]}
    -- the verdict and the list of failing tests allowed as known red go into the publish record that
    tools/deploy.py reads (M9-NL).

    A failed tests check is allowed through ONLY on the verdict tools/ci_gate.py attaches to it,
    r["known_red"] (known_red_verdict, round 2 A8): its `ok` and its `allowed` list, nothing else. Draw-3
    release audit, SERIOUS 2: this function read the classification's "red" list and the 12-line-capped
    `details` instead and never read that verdict, so the three laundering routes A8 closed stayed open
    here -- reproduced with the real data_tier and the real known_red_verdict (the adjudicator's
    m9_known_red.py): the known test failing with 54 warnings instead of 20, a new failure put into
    "red" by a re-classification, and pytest exiting 2 each read `known-red-only`, which deploy.py
    accepts, while the gate's verdict said BLOCK. A tests failure that carries no verdict is red."""
    sys.path.insert(0, str(DEV / "tools"))
    import ci_gate as G
    if G.tier() != "data":
        out("not the data tier here (the desk's data is absent); refusing -- this presubmit exists to run it")
        return {"ok": False, "verdict": "not-run", "known_red": []}
    results = [c() for c in G.CHECKS]
    ok = True
    allowed = []
    for r in results:
        verdict = "PASS" if r["ok"] else "FAIL"
        if not r["ok"] and r["name"] == "tests":
            kr = r.get("known_red") if isinstance(r.get("known_red"), dict) else {}
            if kr.get("ok") is True and kr.get("allowed"):
                allowed = sorted(kr["allowed"])
                verdict = "KNOWN-RED ONLY (%s) -- allowed, CI will keep blocking (D23)" % ", ".join(allowed)
            else:
                ok = False
                verdict = "FAIL -- no known-red allowance applies (A8): %s" % (
                    "; ".join((kr.get("blocking") or [])[:4]) or "the gate attached no known-red verdict")
        elif not r["ok"] and r.get("blocking"):
            ok = False
        out("  [%s] %-13s %s" % (verdict[:4] if verdict in ("PASS", "FAIL") else "NOTE", r["name"], r["summary"][:140]))
        if verdict not in ("PASS", "FAIL"):
            out("        %s" % verdict)
    return {"ok": ok, "verdict": "red" if not ok else ("known-red-only" if allowed else "green"),
            "known_red": allowed if ok else []}


def _synced(rel: str) -> bool:
    """Whether sync() copies the file at this path under a SUBSET directory: EXCLUDE read the way rsync reads
    an unanchored pattern -- a name with no "/" matches any component of the path, a trailing "/" only a
    directory component. Derived from EXCLUDE itself, so the two cannot drift apart FOR THE PATTERN FORMS
    EXCLUDE USES TODAY (draw3_fix release item 8: the sentence used to stand unconditionally): single names,
    optionally with a trailing "/". An anchored pattern ("/x") or one with an inner "/" ("a/b") is matched by
    rsync against the path from the transfer root, which this reading does not do; adding one to EXCLUDE
    voids this function (tools/tests/test_ci_publish.py pins the forms)."""
    parts = rel.split("/")
    for e in EXCLUDE:
        names = parts[:-1] if e.endswith("/") else parts
        if any(fnmatch.fnmatchcase(n, e.rstrip("/")) for n in names):
            return False
    return True


def subset_hashes(root=None) -> dict:
    """{path: sha256} for every file sync() would copy from `root` (the dev tree): each SUBSET directory
    walked through the sync's own filter, each SUBSET file as it is (sync() cp's it unfiltered)."""
    root = pathlib.Path(root or DEV)
    out = {}
    for s in SUBSET:
        src = root / s
        files = sorted(p for p in src.rglob("*") if p.is_file()) if src.is_dir() else [src] if src.is_file() else []
        for p in files:
            rel = p.relative_to(root).as_posix()
            if not src.is_dir() or _synced(p.relative_to(src).as_posix()):
                out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def tree_identity() -> dict:
    """The dev tree's deploy manifest (tools/deploy.py: `version`, `pipeline_version`) plus `code`: a hash
    over everything that is either deployed or published, without the classification file, which step 2
    may rewrite. Round 2 (A8, the M9-NL record): nothing bound the published tree to the tree the data
    tier tested, so a record saying "this version passed" could name bytes that never ran through it.

    Draw-3 release audit, item 6: `code` covered the deploy PLAN only, so an edit made during the data
    tier to vps/probe.py, vps/*.sh, a unit file, .github/ or docs/evalharness was committed with no
    refusal -- and the data tier's no-live scan reads vps/ and the workflows (ci_gate.py check_no_live).
    `code` now covers the SUBSET file set through the sync's own filter (subset_hashes) AND the plan's
    hashes, under separate prefixes: the first is what reaches GitHub, the second what the record's
    `version` names for deploy.py (it includes a staged/ file the sync skips)."""
    m = D.manifest(root=DEV)
    code = {"plan:" + k: h for k, h in m["hashes"].items() if k != CLASSIFICATION}
    code.update({"sync:" + k: h for k, h in subset_hashes(DEV).items() if k != CLASSIFICATION})
    m["code"] = D.version_id(code)
    return m


def ensure_checkout(out=print):
    if not (CI / ".git").exists():
        out("cloning the durable CI checkout into %s" % CI)
        sh(["git", "clone", "-q", REMOTE, str(CI)])
    if not (CI / ".v/bin/python").exists():
        out("creating the clean arm's bare venv (pytest, pyyaml, requests -- exactly what Actions installs)")
        sh([sys.executable, "-m", "venv", str(CI / ".v")])
        sh([str(CI / ".v/bin/pip"), "-q", "install", "pytest", "pyyaml", "requests"])
    ign = CI / ".git/info/exclude"
    if ".v/" not in (ign.read_text() if ign.exists() else ""):
        with ign.open("a") as fh:
            fh.write("\n.v/\n")


def checkout_refusal():
    """None when the durable checkout may be written, else why not (round 2, A12).

    The adjudicator's reproduction on a clone of 1fce953: a commit made by hand in the checkout (an edit
    to forge/probe.py and a new forge/hotfix_guard.py) was reverted and deleted by the next sync, with
    nothing printed -- `rsync --delete` per directory, then `git add -A`. So the checkout is written only
    when it is exactly as this script left it. Each refusal names the state and the way out of it.
    """
    sh(["git", "fetch", "-q", "origin"], cwd=CI)
    head = sh(["git", "rev-parse", "HEAD"], cwd=CI).stdout.strip()
    try:
        last = (CI / LAST).read_text().strip()
    except OSError:
        last = ""
    if not last:
        return ("there is no record of the last commit ci_publish made (%s). Look at HEAD (`git -C %s log -3 "
                "--stat`); if it is the last publish, adopt it: tools/ci_publish.py --adopt-head %s"
                % (CI / LAST, CI, head))
    if head != last:
        return ("HEAD %s is not the last commit ci_publish made (%s): the checkout was committed to by hand. "
                "Inspect `git -C %s log --stat %s..HEAD`, carry what must survive into the dev tree, then "
                "`git -C %s reset --hard %s`" % (head[:12], last[:12], CI, last[:12], CI, last[:12]))
    dirty = sh(["git", "status", "--porcelain"], cwd=CI).stdout.rstrip()
    if dirty:
        return ("the checkout has uncommitted changes. If they are an interrupted publish's leftovers: "
                "`git -C %s reset --hard HEAD && git -C %s clean -fd`\n%s"
                % (CI, CI, "\n".join("      " + l for l in dirty.splitlines()[:10])))
    ahead = int(sh(["git", "rev-list", "--count", "HEAD..origin/main"], cwd=CI).stdout.strip() or 0)
    if ahead:
        # Draw-3 release audit, item 7: this used to end "bring it into the dev tree first", which does not
        # move the checkout's HEAD, so HEAD..origin/main was unchanged and every later run printed the same
        # refusal -- a loop with no exit (EX-ANTE, from the code; exec's probe found the way out below).
        origin = sh(["git", "rev-parse", "origin/main"], cwd=CI).stdout.strip()
        mine = int(sh(["git", "rev-list", "--count", "origin/main..HEAD"], cwd=CI).stdout.strip() or 0)
        head = ("origin/main has %d commit(s) this checkout lacks: something reached GitHub without ci_publish. "
                "Inspect `git -C %s log --stat HEAD..origin/main` and carry what must survive into the dev tree "
                "(the next publish syncs the dev tree over the checkout). " % (ahead, CI))
        if mine:
            # draw3_fix release item 7: when HEAD also holds commits origin lacks -- an unpushed publish after
            # --no-push, or an origin that was rewritten -- the two have diverged, `merge --ff-only` fails
            # ("Not possible to fast-forward", exit 128 in the adjudicator's reproduction) and --adopt-head then
            # refuses "not HEAD": the printed route dead-ended. The way out is to drop HEAD's own commits; what
            # they published came from the dev tree, which still holds it, and the next publish syncs it again.
            return (head + "HEAD also holds %d commit(s) origin/main lacks, so a fast-forward is impossible; "
                    "discard them (inspect `git -C %s log --stat origin/main..HEAD` first):\n"
                    "      git -C %s reset --hard origin/main\n"
                    "      tools/ci_publish.py --adopt-head %s"
                    % (mine, CI, CI, origin[:12]))
        return (head + "Then:\n"
                "      git -C %s merge --ff-only origin/main\n"
                "      tools/ci_publish.py --adopt-head %s"
                % (CI, origin[:12]))
    return None


def adopt_head(sha, out=print) -> int:
    """A12's bootstrap, and its way back after a refusal: record HEAD as this script's own. The SHA must be
    typed out -- adopting says that someone looked at that commit.

    Only a HEAD that origin/main contains (equal to it, or an ancestor of it), after a fetch. Draw-3 release
    adjudicator, "dropped or corrected": the assume audit's "adopt only when LAST is absent" would have
    broken the only working recovery from origin-ahead (merge --ff-only, then adopt); but adopting ANY HEAD
    let a hand commit that never reached GitHub be recorded as ci_publish's own, and the next sync would
    publish on top of it.

    NEEDS THE NETWORK (draw3_fix release item 7, exec P9): the containment check is against a FRESH
    origin/main, so the fetch must succeed; offline, sh() stops the run at the fetch and nothing is adopted.
    That fails closed, and is the price of never adopting against a stale origin."""
    sh(["git", "fetch", "-q", "origin"], cwd=CI)
    head = sh(["git", "rev-parse", "HEAD"], cwd=CI).stdout.strip()
    if len(sha) < 7 or not head.startswith(sha):
        out("REFUSED: %s is not HEAD (%s)" % (sha, head[:12]))
        return 1
    if sh(["git", "merge-base", "--is-ancestor", "HEAD", "origin/main"], cwd=CI, check=False).returncode != 0:
        out("REFUSED: HEAD %s is not contained in origin/main -- it holds a commit GitHub does not have. Inspect "
            "`git -C %s log --stat origin/main..HEAD`; carry what must survive into the dev tree, then "
            "`git -C %s reset --hard origin/main` and adopt that" % (head[:12], CI, CI))
        return 1
    (CI / LAST).write_text(head + "\n")
    out("adopted %s as the last commit ci_publish made" % head[:12])
    return 0


def restore(out=print):
    """Put the checkout back at HEAD after a refusal that followed the sync. Safe because the sync ran
    only on a checkout that was clean at HEAD, so everything this discards was written by this run."""
    if not sh(["git", "status", "--porcelain"], cwd=CI).stdout.strip():
        return
    sh(["git", "reset", "-q", "--hard", "HEAD"], cwd=CI)
    sh(["git", "clean", "-fdq"], cwd=CI)
    out("  the checkout is back at HEAD; nothing was committed")


def commit(message):
    sh(["git", "-c", "user.name=Nguyễn Minh Khoa", "-c", "user.email=lehoatrang27924@gmail.com",
        "commit", "-q", "-m", message], cwd=CI)
    # recorded after EVERY commit: a crash between two commits leaves HEAD and the record agreeing
    (CI / LAST).write_text(sh(["git", "rev-parse", "HEAD"], cwd=CI).stdout.strip() + "\n")


def sync(out=print, dst_root=None):
    dst_root = pathlib.Path(dst_root or CI)
    ex = sum((["--exclude", e] for e in EXCLUDE), [])
    for p in SUBSET:
        src = DEV / p
        if not src.exists():
            raise SystemExit("missing from the dev tree: %s" % p)
        dst = dst_root / p
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            # --delete: a file removed from the dev tree must leave the CI repository too. The first
            # publish left tools/ci_baseline.json behind (552 files on CI, 551 here). Excluded names
            # (caches) are protected from deletion; the venv sits outside every synced directory.
            sh(["rsync", "-rc", "--delete", *ex, str(src) + "/", str(dst) + "/"])
        else:
            sh(["cp", str(src), str(dst)])


def clean_arm(out=print) -> pathlib.Path:
    """What the CI repository will hold after this publish, in a throwaway directory: its HEAD exported,
    with the dev subset laid over it. The classification's clean arm used to run IN the durable checkout,
    so the checkout was overwritten before the classification had passed (A12: a step-2 refusal left it
    synced). The venv stays in the checkout, outside this tree. The caller removes the directory."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="wq-ci-clean-"))
    tar = tmp.parent / (tmp.name + ".tar")
    try:
        sh(["git", "archive", "--format=tar", "-o", str(tar), "HEAD"], cwd=CI)
        sh(["tar", "-xf", str(tar), "-C", str(tmp)])
        sync(out=out, dst_root=tmp)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    finally:
        tar.unlink(missing_ok=True)
    return tmp


def classification_current() -> bool:
    sys.path.insert(0, str(DEV / "tools"))
    import ci_classify as C
    try:
        cls = json.loads((DEV / "tools/ci_data_bound.json").read_text())
    except (OSError, ValueError):
        return False
    return cls.get("tests_hash") == C.tests_hash() and cls.get("code_version") == C.code_version()


def _closure_keys(text):
    """The `scorer_closure` keys of a golden card's JSON text, or None when it has no such {path: hash} map."""
    try:
        g = json.loads(text)
    except (TypeError, ValueError):
        return None
    sc = g.get("scorer_closure") if isinstance(g, dict) else None
    return set(sc) if isinstance(sc, dict) else None


def golden_mixed(changed, root=None) -> list:
    """The files the golden card pins that are committed together with it (S8-NL), sorted, or [].

    D42 (Khoa, 2026-09-23): the pinned scorer is its whole transitive closure (51 files), so an edit to ANY
    of them moves the judgement. This read benchmark.py and ci_fixture.py only, and the draw3_fix ci audit
    (SERIOUS 1) reproduced a re-recorded golden riding in with an edit to forge/runner.py -- the same for 49
    of the 51 files, forge/submit.py included. Pinned now: SCORER, plus the `scorer_closure` keys of BOTH the
    golden committed at the checkout's HEAD and the one this commit brings (a file entering or leaving the
    closure is pinned by one of them). A golden that cannot be read as a card with a closure pins EVERY other
    changed file: failing closed costs one `--split-golden`, failing open lets the judgement move unseen."""
    root = pathlib.Path(root or CI)
    if GOLDEN not in changed:
        return []
    try:
        new = (root / GOLDEN).read_text()
    except OSError:
        new = None
    head = sh(["git", "show", "HEAD:" + GOLDEN], cwd=root, check=False)
    keys = [_closure_keys(new), _closure_keys(head.stdout) if head.returncode == 0 else set()]
    if any(k is None for k in keys):
        return sorted(f for f in changed if f != GOLDEN)
    pinned = set(SCORER).union(*keys)
    return sorted(f for f in changed if f in pinned and f != GOLDEN)


def record_publish(m, dt, ci_commit, pushed, out=print) -> dict:
    """Append the publish record tools/deploy.py reads before any push (M9-NL): keyed by the dev tree's
    full content `version` -- deploy's own identity, so a record vouches for exactly one set of bytes."""
    rec = {"published_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "version": m["version"],
           "pipeline_version": m["pipeline_version"], "verdict": dt["verdict"], "known_red": dt["known_red"],
           "ci_commit": ci_commit, "pushed": pushed}
    D.PUBLISH_RECORDS.parent.mkdir(parents=True, exist_ok=True)
    with D.PUBLISH_RECORDS.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    out("5. RECORD -> %s: version %s (pipeline %s), data tier %s" % (D.PUBLISH_RECORDS, m["version"],
                                                                       m["pipeline_version"], dt["verdict"]))
    return rec


def main(argv=None) -> int:
    # allow_abbrev=False (round 3 m8, predicted by Draw 4 section 5 item 10): rebuilt from these add_argument calls,
    # `--spl` set split_golden and `--no-p` set no_push. --split-golden relaxes golden_mixed()'s refusal, so like
    # deploy.py's --force-unpublished it must be typed whole.
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    ap.add_argument("-m", "--message", help="the commit message (required to publish)")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--adopt-head", metavar="SHA",
                    help="record the checkout's HEAD (type its SHA) as the last commit ci_publish made, and stop "
                         "(fetches origin first: needs the network)")
    ap.add_argument("--split-golden", action="store_true",
                    help="when the golden card changed with the scorer, commit it ALONE after the rest (S8-NL)")
    a = ap.parse_args(argv)
    if a.adopt_head:
        return adopt_head(a.adopt_head)
    if not a.message:
        ap.error("-m/--message is required to publish")
    ensure_checkout()
    print("0. THE CHECKOUT (%s)" % CI)
    why = checkout_refusal()
    if why:
        print("REFUSED: " + why)
        return 1
    tested = tree_identity()
    print("1. DATA TIER (%s)" % DEV)
    dt = data_tier()
    if not dt["ok"]:
        print("REFUSED: the data tier found a failure that no known-red allowance covers")
        return 1
    if tree_identity()["code"] != tested["code"]:
        print("REFUSED: the dev tree changed while the data tier ran; what passed is not what would ship")
        return 1
    print("2. CLASSIFICATION")
    if classification_current():
        print("  current")
    else:
        arm = clean_arm()                          # the clean arm must run the same code
        try:
            r = sh([sys.executable, str(DEV / "tools/ci_classify.py"), "--clean", str(arm),
                    "--clean-python", str(CI / ".v/bin/python")], cwd=DEV, check=False)
        finally:
            shutil.rmtree(arm, ignore_errors=True)
        print("\n".join("  " + l for l in (r.stdout or "").strip().splitlines()[-6:]))
        if r.returncode != 0:
            print("REFUSED: the classification did not complete; the checkout was not touched")
            return 1
    print("3. SYNC -> %s" % CI)
    why = checkout_refusal()                       # again: steps 1-2 take many minutes
    if why:
        print("REFUSED: " + why)
        return 1
    done = False
    try:
        sync()
        m = tree_identity()
        if m["code"] != tested["code"]:
            print("REFUSED: the dev tree changed between the data tier and the sync; what passed is not what would ship")
            return 1
        sh(["git", "add", "-A"], cwd=CI)
        changed = sh(["git", "diff", "--cached", "--name-only"], cwd=CI).stdout.split()
        if GOLDEN in changed:
            print("  THE GOLDEN CARD CHANGED -- the scorer's pinned judgement moves with this publish:")
            diff = sh(["git", "diff", "--cached", "--no-color", "--", GOLDEN], cwd=CI).stdout
            print("\n".join("    " + l for l in diff.splitlines()))
        mixed = golden_mixed(changed)
        if mixed and not a.split_golden:
            print("REFUSED: %s changed in the same commit as %d file(s) it pins (%s%s). Re-record the golden in its "
                  "own commit (S8-NL, D42): read the diff above, then re-run with --split-golden"
                  % (GOLDEN, len(mixed), " and ".join(mixed[:5]), " ..." if len(mixed) > 5 else ""))
            return 1
        hits = [f for f in changed if (CI / f).is_file() and SECRET.search((CI / f).read_text(errors="ignore"))]
        if hits:
            print("REFUSED: a secret-shaped string in %s" % hits)
            return 1
        if changed:
            print("  %d file(s) changed, secret scan clean" % len(changed))
            if mixed:
                sh(["git", "reset", "-q", "--", GOLDEN], cwd=CI)     # everything but the golden first
                commit(a.message)
                sh(["git", "add", "--", GOLDEN], cwd=CI)
                commit("golden card re-recorded, in its own commit (S8-NL): " + a.message)
                print("  committed as two: the change, then the golden card alone")
            else:
                commit(a.message)
        done = True
    finally:
        if not done:
            restore()
    ahead = int(sh(["git", "rev-list", "--count", "origin/main..HEAD"], cwd=CI).stdout.strip() or 0)
    pushed = False
    if not ahead:
        print("nothing changed")
    elif a.no_push:
        print("committed, not pushed (%d commit(s) ahead of origin/main)" % ahead)
    else:
        print("4. PUSH (%d commit(s))" % ahead)
        sh(["git", "push", "-q"], cwd=CI)         # -q is silent on success; sh() raises on failure
        pushed = True
        print("  pushed")
    # Draw-3 release adjudicator, item 11: the record came after `gh run list`, and sh() does not catch
    # FileNotFoundError, so on a host without gh a pushed publish crashed with no record. The record is the
    # thing deploy.py reads; the Actions link is a convenience. Record first, then ask gh, and survive its
    # absence.
    record_publish(m, dt, sh(["git", "rev-parse", "HEAD"], cwd=CI).stdout.strip(), pushed)
    if pushed:
        try:
            r = sh(["gh", "run", "list", "-R", "khoaminh2957/wq-pipeline", "--limit", "1"], check=False)
            print("  " + (r.stdout or "").strip()[:140])
        except (OSError, subprocess.SubprocessError) as exc:
            print("  could not list the Actions run (%s); the publish and its record stand" % type(exc).__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
