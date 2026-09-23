"""tools.ci_publish — the ONLY way pipeline code reaches the GitHub repository (the data-tier presubmit).

WHY THIS EXISTS (architecture round 1, missed by all three reviewers). The gate's hermetic tier skips
167 tests and the branch drill "covered instead by the data tier" -- but nothing ran the data tier
before a push, and the CI repository lived in a session scratchpad under /private/tmp, synced by hand.
The claim was false. This script makes it true, in order:

  1. DATA TIER, here, where the journal and catalogues exist: the full gate -- every test, the drill.
     A failure that is not ALREADY measured red (tools/ci_data_bound.json "red") refuses the publish.
     A known-red test (Khoa's D23) is allowed through and named: CI keeps blocking on it, as he chose.
  2. CLASSIFICATION: if tests or code changed since the last one, re-measure it (two arms, same code;
     the CI checkout itself is the clean arm -- it holds no state/ and no fetched/ data).
  3. SYNC: exactly the pipeline subset (D22) into the durable checkout, secret-scanned before commit.
  4. COMMIT + PUSH, and print the Actions run to watch.

Nothing here simulates, and nothing touches the VPS.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

DEV = pathlib.Path(__file__).resolve().parents[1]
CI = DEV.parent / "wq-pipeline"
REMOTE = "https://github.com/khoaminh2957/wq-pipeline.git"
#: D22: the pipeline, its measured dependency closure, and the evalharness documents -- nothing else.
SUBSET = ["forge", "tools", "vps", "fingerprint.py", "operators.py",
          "harness13/__init__.py", "harness13/crawl_fields.py", "harness13/massgen/mg/simulate.py",
          "harness/guards.py", "docs/evalharness"]
EXCLUDE = ["__pycache__", "*.pyc", ".pytest_cache", "staged/", ".DS_Store"]
SECRET = re.compile(r"discord\.com/api/webhooks/[0-9]{6}|BEGIN (RSA|OPENSSH) PRIVATE|"
                    r"password[\"' ]*[:=][\"' ]*[A-Za-z0-9!@#$%^&*]{8,}")


def sh(argv, cwd=None, check=True, timeout=3600):
    r = subprocess.run(argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise SystemExit("FAILED: %s\n%s" % (" ".join(map(str, argv)), (r.stderr or r.stdout)[-800:]))
    return r


def data_tier(out=print) -> bool:
    sys.path.insert(0, str(DEV / "tools"))
    import ci_gate as G
    if G.tier() != "data":
        out("not the data tier here (the desk's data is absent); refusing -- this presubmit exists to run it")
        return False
    red = set(G.classification().get("red") or [])
    results = [c() for c in G.CHECKS]
    ok = True
    for r in results:
        verdict = "PASS" if r["ok"] else "FAIL"
        if not r["ok"] and r["name"] == "tests":
            failing = {l.split(" ", 1)[1].split(" - ")[0] for l in (r.get("details") or []) if l.startswith(("FAILED ", "ERROR "))}
            new = failing - red
            if failing and not new:
                verdict = "KNOWN-RED ONLY (%s) -- allowed, CI will keep blocking (D23)" % ", ".join(sorted(failing))
            else:
                ok = False
                verdict = "FAIL -- NEW failures: %s" % ", ".join(sorted(new)) if new else "FAIL"
        elif not r["ok"] and r.get("blocking"):
            ok = False
        out("  [%s] %-13s %s" % (verdict[:4] if verdict in ("PASS", "FAIL") else "NOTE", r["name"], r["summary"][:140]))
        if verdict not in ("PASS", "FAIL"):
            out("        %s" % verdict)
    return ok


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


def sync(out=print):
    ex = sum((["--exclude", e] for e in EXCLUDE), [])
    for p in SUBSET:
        src = DEV / p
        if not src.exists():
            raise SystemExit("missing from the dev tree: %s" % p)
        dst = CI / p
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            # --delete: a file removed from the dev tree must leave the CI repository too. The first
            # publish left tools/ci_baseline.json behind (552 files on CI, 551 here). Excluded names
            # (caches) are protected from deletion; the venv sits outside every synced directory.
            sh(["rsync", "-rc", "--delete", *ex, str(src) + "/", str(dst) + "/"])
        else:
            sh(["cp", str(src), str(dst)])


def classification_current() -> bool:
    sys.path.insert(0, str(DEV / "tools"))
    import ci_classify as C
    try:
        cls = json.loads((DEV / "tools/ci_data_bound.json").read_text())
    except (OSError, ValueError):
        return False
    return cls.get("tests_hash") == C.tests_hash() and cls.get("code_version") == C.code_version()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-m", "--message", required=True, help="the commit message")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args(argv)
    print("1. DATA TIER (%s)" % DEV)
    if not data_tier():
        print("REFUSED: the data tier found a failure that is not already measured red")
        return 1
    ensure_checkout()
    print("2. CLASSIFICATION")
    if classification_current():
        print("  current")
    else:
        sync()                                     # the clean arm must run the same code
        r = sh([sys.executable, str(DEV / "tools/ci_classify.py"), "--clean", str(CI),
                "--clean-python", str(CI / ".v/bin/python")], cwd=DEV, check=False)
        print("\n".join("  " + l for l in (r.stdout or "").strip().splitlines()[-6:]))
        if r.returncode != 0:
            print("REFUSED: the classification did not complete")
            return 1
    print("3. SYNC -> %s" % CI)
    sync()
    sh(["git", "add", "-A"], cwd=CI)
    changed = sh(["git", "diff", "--cached", "--name-only"], cwd=CI).stdout.split()
    hits = [f for f in changed if (CI / f).is_file() and SECRET.search((CI / f).read_text(errors="ignore"))]
    if hits:
        print("REFUSED: a secret-shaped string in %s" % hits)
        return 1
    if not changed:
        print("nothing changed")
        return 0
    print("  %d file(s) changed, secret scan clean" % len(changed))
    sh(["git", "-c", "user.name=Nguyễn Minh Khoa", "-c", "user.email=lehoatrang27924@gmail.com",
        "commit", "-q", "-m", a.message], cwd=CI)
    if a.no_push:
        print("committed, not pushed")
        return 0
    print("4. PUSH")
    sh(["git", "push", "-q"], cwd=CI)             # -q is silent on success; sh() raises on failure
    print("  pushed")
    r = sh(["gh", "run", "list", "-R", "khoaminh2957/wq-pipeline", "--limit", "1"], check=False)
    print("  " + (r.stdout or "").strip()[:140])
    return 0


if __name__ == "__main__":
    sys.exit(main())
