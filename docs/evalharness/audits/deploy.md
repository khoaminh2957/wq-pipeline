# Adjudicated audit — `tools/deploy.py` + `tools/tests/test_deploy.py`

Adjudicator, 2026-09-23. Three auditors (specification / destruction / assumptions) reported against
D1, D4, D14, D16. This file is the single list of what must change. Every defect below was
re-verified by me before it was kept; defects that did not reproduce are in **Dropped**, with the
measurement that dropped them.

**Method.** Local shell re-derivations, an offline trace of the real `push()` with
`subprocess.run` recorded instead of executed, and read-only `ssh -n` against `root@160.25.88.163`.
Nothing was written to the VPS and no quota was spent (CLAUDE.md RULE 1).

---

## VERDICT

**NO. `tools/deploy.py push` must not be run against `/opt/wq` as it stands.**

The single reason, measured rather than argued: **on the next push — the first one — a rollback
issues `rm -f` over 537 paths, 499 of which exist on the target right now, before it opens an
archive whose existence the module is structurally incapable of checking.** `/opt/wq` is not a git
repository (verified), so the 6 files whose target bytes differ from local exist nowhere else.

Five things must be fixed before the first push. They are C1, C2, B1, B2 and B3 below.

---

## CATASTROPHIC

### C1 — The rollback deletes 537 production files before it knows it can restore them, and the snapshot cannot report that it failed

`tools/deploy.py:201-216` (`snapshot`), `:219-227` (`rollback`), `:247` (return value discarded),
`:265` / `:275` (call sites).

Three independent breaks stack into one outcome.

**(a) `snapshot()`'s success test reads an `echo` the shell runs unconditionally.** Line 212 ends
the remote command `... --ignore-failed-read 2>/dev/null; echo done`. The `;` terminates the
`&&`-list, so `done` prints whether or not `cd`, `cat` or `tar` succeeded. Line 215 reports "ok" on
`"done" in r.stdout`. Re-derived locally:

```
$ bash -c 'cd /nonexistent-dir-xyz-abc && mkdir -p .deploy && cat > .deploy/t.files && \
           tar -czf .deploy/t.tgz -T .deploy/t.files --ignore-failed-read 2>/dev/null; echo done'
done                     # stdout=[done], python `"done" in stdout` -> True, no archive created
```

tar's stderr goes to `/dev/null` and its exit status is never read.

**(b) `push()` discards the result anyway.** Line 247 is `tar = snapshot(...)`; only the *path* is
used. The word FAILED is printed for a human and branches nothing.

**(c) `rollback()` deletes first, restores second.** Line 221 builds the `rm -f` chain, line 223 is
`"cd %s && (%s) && tar -xzf %s && echo restored"`. Re-derived locally:

```
$ bash -c 'cd /tmp/rbdemo && (rm -f a.py && rm -f sub/b.py) && tar -xzf .deploy/pre-unknown.tgz && echo restored'
tar: Error opening archive: Failed to open '.deploy/pre-unknown.tgz'
# a.py DELETED, sub/b.py DELETED, "restored" never printed
```

**End-to-end trace of the real `push()`** (subprocess recorded, snapshot ssh returning rc=255,
smoke red, virgin target):

```
local version  ec453f3eabeb4391 (537 files, git 8a806c86, DIRTY)
target version NONE (never deployed by this tool)
drift: 537 added, 0 changed, 0 removed-from-plan
  snapshot -> .deploy/pre-unknown.tgz (FAILED)     <-- printed, then ignored
shipped 537 file(s) + DEPLOYED.json                <-- ships anyway
  smoke import   FAILED
smoke FAILED at 'import' -- rolling back
  ROLLBACK FAILED: tar: not found

SSH cmd len=24157  rm-f clauses=537
   ORDER: first 'rm -f' at 15, 'tar -xzf' at 24108 -> RM BEFORE TAR
```

**Second failure mode, same root cause — the archive can exist and be empty.** GNU tar with
`--ignore-failed-read` over a list of paths that are all missing exits 0 and writes a valid,
member-less archive; extracting it also exits 0, so `echo restored` runs and `rollback()` returns
`True` having restored nothing. Measured on the target's own tar, read-only, writing only to
`/dev/shm`:

```
tar (GNU tar) 1.35
create rc=0   archive bytes: 45   members listed: 0   extract rc: 0
```

Trigger condition, stated honestly: this branch needs a target where none of the listed paths
exist. On `/opt/wq` today 499 of 537 do exist, so today's archive would have members. It is
certain on a re-provisioned target or after a changed `REMOTE`.

**Blast radius, measured.** `/opt/wq/DEPLOYED.json` does not exist (`ls` → No such file), so
`remote_manifest()` is None and `drift(local, {"hashes": {}})["added"]` is all 537 plan paths. I
re-hashed every one of them on the target read-only: **493 identical, 6 different, 38 absent — 44
of 537 drifted**, independently reproducing the figure in the brief. The 6 whose target bytes
differ are `forge/submit.py`, `forge/tests/test_probe.py`, `forge/tests/test_submit.py`,
`tools/auth_link.py`, `tools/auth_only.py`, `tools/measure_backlog.py`; `git -C /opt/wq rev-parse`
answers "not a git repository", so those bytes have no other copy anywhere. `wq-forge` is `active`
with `Restart=always`, `RestartSec=60`.

The `rm -f` chain is correctly scoped — I string-tested the real 537-clause command: `rm -f state/`,
`rm -f venv/`, `rm -f fetched/` are all absent. The journal (`/opt/wq/state`, measured 1.1 GB) is
not in the deletion set. The loss is the code tree, not the journal.

**Fix.**
1. Make the snapshot's success its own measurement: drop `; echo done`, drop `2>/dev/null`, read
   tar's exit status, then `tar -tzf <tar> | wc -l` and return the member count. Return `None` on
   failure.
2. In `push()`, `if tar is None: abort before the rsync`.
3. In `rollback()`, extract FIRST and delete second — `tar -xzf <tar> && (rm -f …)` — and only
   delete paths proven absent from the archive listing.
4. Treat a `rollback()` False as a loud, non-zero, do-not-retry state, not a discarded boolean.

---

### C2 — A rolled-back first deploy leaves `DEPLOYED.json` asserting the version that failed, and every later push then refuses to correct it

`tools/deploy.py:242-244` (the no-op guard), `:247` (snapshot list), `:256` (manifest written into
the staging tree), `:265` / `:275` (`d["added"]` cannot contain it).

`MANIFEST_NAME` is not a PLAN path, so it is never in `local["hashes"]`, so it is never in
`d["added"]` — `rollback()` never removes it. On a virgin target it also did not exist, so
`--ignore-failed-read` omitted it from the archive and the restore cannot put back "this file did
not exist". Verified in the trace above: `DEPLOYED.json in rm chain? False`.

The consequence, traced with the surviving manifest in place and an otherwise healthy target:

```
SECOND push rc = 0
  | local version  ec453f3eabeb4391 (537 files, git 8a806c86, DIRTY)
  | target version ec453f3eabeb4391
  | drift: 0 added, 0 changed, 0 removed-from-plan
  | nothing to do: the target already runs this exact content
```

The tool becomes a permanent silent no-op that certifies a version which is not running, over a
tree that may be the damaged one from C1. `drift` reports 0 files differ. Recovery requires someone
knowing to delete a file by hand.

**It is also reachable with no smoke failure at all.** `DEPLOYED.json` sorts first of 538 in the
byte-sorted transfer list (measured: index 0), so an rsync that dies partway lands the manifest and
only some of the code.

The docstring at `:204-206` claims the opposite — "restoring therefore puts the tree back to exactly
what was there, including 'this file did not exist'". That sentence is false for the one file whose
correctness the whole module exists to establish.

**Fix.** Write the manifest to the target as a separate, LAST step, after rsync and after the smoke
is green — never inside the shipped payload. Until then, pass `MANIFEST_NAME` into `rollback()`'s
removal set whenever the target had no manifest before the push.

---

## BLOCKER

### B1 — A timeout or a dropped connection bypasses the rollback entirely

`tools/deploy.py:230-276`. `sed -n '230,277p' tools/deploy.py | grep 'try\|except'` returns
**nothing**. Every remote call carries a timeout — `_ssh` 900 s (`:159`), rsync 900 s (`:261`),
snapshot/rollback 300 s, `remote_manifest` 60 s, the round guard 60 s — and `subprocess.run` raises
`TimeoutExpired`, it does not return it.

Rollback is reached only from a non-zero **exit code** (`:263`, `:270`). An exception from the rsync
at `:260` leaves the tree half-swapped, the manifest already landed (it transfers first), the
staging tree uncleaned (`:262` never runs), and no rollback attempted. An exception from
`run_smoke` at `:269` leaves the new code fully installed and unverified. The operator gets a
traceback instead of the word ROLLBACK.

The module knows the idiom — `git_sha`/`git_dirty` at `:90-107` both catch
`(OSError, subprocess.SubprocessError)`. It is applied on the two paths that cannot lose data and
omitted on the four that can.

Compounding: `grep -c BatchMode tools/deploy.py` → **0**. ssh is invoked with `capture_output=True`
and no `-o BatchMode=yes` and no `-n`, so a host-key or passphrase prompt is invisible and blocks
for the full timeout. I hit exactly this myself and had to add `BatchMode=yes` to get a readable
result.

**Fix.** Wrap everything from the snapshot onward in `try/except (subprocess.SubprocessError,
OSError)` and route the exception into the same rollback branch as a non-zero exit — "anything other
than a clean green" means undo. Add `-o BatchMode=yes` to every ssh and `-e 'ssh -o BatchMode=yes'`
to the rsync.

### B2 — The round guard fails OPEN, watches one process of five, and is a check-then-act with no lock

`tools/deploy.py:162-171`, called once at `:232`.

`int((r.stdout or "0").strip() or 0)` turns an empty stdout into 0 — "no round is running", the
answer that permits the swap — and the ssh returncode is never examined. Demonstrated by
substituting the response:

| condition | `round_in_flight()` | push |
|---|---|---|
| ssh refused (rc 255, empty stdout) | False | **PROCEEDS** |
| auth failed (rc 255, banner on stderr) | False | **PROCEEDS** |
| `pgrep` missing, masked by `\|\| true` | False | **PROCEEDS** |
| genuine idle | False | proceeds (correct) |
| genuine live round | True | refuses (correct) |

The pattern `[r]unner.py` covers one phase. `vps/forge_loop.sh` runs
`runner.py` → `forge/offline/recover_orphans.py` (timeout 900) → `forge/harvest.py` (1800) →
`forge/probe.py` (1500, backgrounded) → `forge/submit.py --submit --cap 4`. None of the last four
match, so the guard reads "idle" through the submit window — the one moment where a half-swapped
tree costs a G6 slot that memory `submit-403-spends-the-post` says is gone forever.

`forge_loop.sh:10-11` holds `/var/lock/wq_forge.lock`. `grep -n 'flock\|lockf\|Lock(' tools/deploy.py`
→ **nothing**. Between the check at `:232` and the rsync at `:260` the module hashes 537 files,
shells out to git twice, tars a snapshot over ssh and stages 537 files.

A round is dispatching **right now**: `pgrep -fc '[r]unner.py'` returned 1, and
`/bin/bash /opt/wq/forge_loop.sh` is pid 2665426.

**Fix.** Fail closed — require a numeric answer from an ssh that returned 0, and treat anything else
as "a round IS in flight". Take `/var/lock/wq_forge.lock` with `flock -n` for the duration of the
push, or stop the unit for the swap, instead of sampling `pgrep` once.

### B3 — A normal data condition fires the destructive rollback

`tools/deploy.py:149-150` (the planner smoke) and `:190`, against `forge/runner.py:494-496`.

```
forge/runner.py:  if not p["constructions"]:
                      print("nothing to simulate: the library is exhausted for every reachable cell (m13 case)")
                      return 2
vps/forge_loop.sh:63:  if [ "$RC" -eq 2 ]; then     # handled as NORMAL, logs and sleeps
tools/deploy.py:190:   ok = r.returncode == 0       # any non-zero -> rollback
```

The smoke's planner arguments are the production arguments:

```
SMOKE : --mode composites --order USA/d1,d1 --no-split --delays 1 --ab new -n 20 --seed 999
PROD  : FORGE_ARGS=--mode composites --order USA/d1,d1 --no-split --delays 1 --ab new
```

Same mode, same cells, same arm. So on a day when the library is exhausted for the USA/d1 cells,
every deploy reports `smoke FAILED at 'planner'` and executes C1's `rm -f`-then-restore path against
a perfectly good tree, for a reason that has nothing to do with the code. **This is the most likely
ignition source for C1** and it requires no failure of any kind.

**Fix.** Give each SMOKE entry an accepted-exit-code set and let the planner accept `{0, 2}`; or make
`runner.py` distinguish "library exhausted" from "error" with separate codes.

### B4 — `remote_manifest()` reads a transient ssh failure as "never deployed", which arms the full-tree delete on an established target

`tools/deploy.py:174-182`. Three different situations collapse to `None`: the target genuinely has
no manifest; the ssh failed; the manifest exists but is truncated or unparseable.

```python
if r.returncode != 0 or not r.stdout.strip():
    return None
try:    return json.loads(r.stdout)
except ValueError:  return None
```

A network blip, an sshd restart, or a manifest truncated by a previous half-rsync silently converts
an incremental deploy — where `added` would be a handful of files — into a virgin one where `added`
is everything. I demonstrated the None → 537-added path in the C1 trace. The snapshot tag also
becomes `pre-unknown` in exactly this case, so the tag collision below is not a rare retry scenario;
it is the default name for every ssh-failure-induced pseudo-virgin deploy.

This is the desk's own dominant bug class — memory `transient-read-as-truth`, 8 confirmed cases.

**Fix.** Return a distinct sentinel for "could not read" and abort on it. Only an ssh that
*succeeded* and reported a missing file may be read as "never deployed".

### B5 — D16's second trigger is implemented nowhere

`docs/evalharness/00_agreements.md:44` — "Post-deploy smoke test fails, **or the first simulation
round crashes** — before any quota is spent".

`grep -rln 'rollback' --include='*.py' --include='*.sh' --include='*.service'` outside `docs/` and
`harness13/` returns exactly two files: `tools/deploy.py` and `tools/tests/test_deploy.py`.
`vps/forge_loop.sh` contains no reference to `rollback`, `DEPLOYED` or `version`; it captures
`RC=$?`, logs `=== round exit $RC ===`, special-cases only `RC==2`, and loops. The unit is
`Restart=always, RestartSec=60`. `grep -n 'systemctl' tools/deploy.py` → nothing.

`push()` returns 0 the moment the smoke is green and the process exits. Nothing watches the next
round. A version that imports, passes `forge/tests` and plans a round, then crashes on the
dispatcher or the platform, stays deployed and crash-loops.

**Fix.** Report D16 as one-half delivered. Implementing it needs a post-deploy watcher: record the
deploy in a ledger, have `forge_loop.sh` write the first post-deploy round's exit code to a file,
and have the watcher roll back before the next round dispatches.

### B6 — D4's block-merge half does not exist, and auto-deploy has no trigger

`docs/evalharness/00_agreements.md:41` — "Block merge + auto-deploy to the VPS when green +
rollback".

`ls .github` → No such file or directory. `git remote -v` → empty. D13's private GitHub repo has not
been created, so there are no pull requests and nothing to block. Nothing in the repo invokes
`deploy.py`; `main()` at `:279-318` is a manual CLI.

Of D4's three clauses: rollback is implemented-with-defects, deploy is manual, block-merge is
absent.

**Fix.** Report D4 as one-third delivered. The missing halves are a GitHub repo + Actions workflow
running D9's gate with branch protection, and a deploy job calling `push` on green.

---

## SERIOUS

### S1 — Nothing is ever hashed on the target; `DEPLOYED.json` is an assertion, not a measurement

`remote_manifest()` at `:174-182` is `cat DEPLOYED.json` and nothing more. `manifest()` at `:110-114`
hashes the LOCAL tree. There is no `verify` subcommand in `main()`'s choices at `:281`, and no code
path anywhere computes a hash of a remote file.

Three states are therefore undetectable: a file edited directly on `/opt/wq` after a push (exactly
how the 13-day drift arose); a partially applied rsync; files on the target the plan does not cover.
D1 grades "a pipeline VERSION" and D14 grades "only alphas that version produced"; both referents
rest on a claim never checked against the thing it describes.

**Fix.** Add a `verify` step that re-hashes the target's plan paths on the box and compares to the
manifest; run it after the rsync and before the smoke; make `drift` with no `--against` compare
against that measurement. (The read-only `sha256sum` loop I used for this audit is the whole
implementation.)

### S2 — Behaviour changes without the version id moving

`PLAN` at `:34-41` covers 537 files. It omits five classes of input that change what a round does:

1. **`vps/systemd_wq-forge.service` is not in PLAN** although `vps/forge_loop.sh` beside it is. The
   unit carries `N=300`, `ROUNDS=100000` and
   `FORGE_ARGS=--mode composites --order USA/d1,d1 --no-split --delays 1 --ab new`. Editing
   `FORGE_ARGS` re-aims every round with the version id unmoved. PLAN ships 2 of the 33 entries in
   `vps/`.
2. **`/opt/wq/venv`** — measured Python 3.14.4 — and every installed package is unhashed. A
   `pip install -U` is an invisible version change.
3. **`config.py` and `robust.py`** are imported by six shipped `tools/*.py` files
   (`tools/fetch_all_data.py:22`, `fetch_alpha_recordsets.py:20`, `fetch_chn_datasets.py:13`,
   `fetch_operator_docs.py:12`, `fetch_pyramid_catalog.py:14`, `opex_singles.py:7`,
   `build_robust_select.py:7`) and are in neither PLAN nor `/opt/wq` (verified absent on the
   target). No `forge/` module imports them, so the forge loop is unaffected — but the shipped
   files are broken on arrival and the version id does not cover them.
4. **The cell-counter and catalogue inputs** `state/pyramid_cell_counts.json`,
   `fetched/rc/datasets_survey.json` and `fetched/rc/fields/`, read by `forge.cells.targets()` to
   decide which cells are reachable.
5. **Anything already on the target and not in PLAN.** There is no `--delete` (correctly — see
   Confirmed C3), so a module deleted locally survives on the target and remains importable, while
   `d["removed"]` is printed at `:241` and acted on nowhere.

The docstring's load-bearing sentence — "Two trees with the same version id run the same code" — is
false in all five ways.

**Fix.** Add the systemd units and the repo-root modules the shipped tree imports to PLAN, and record
beside the version id a second fingerprint of the environment (`venv/bin/python --version` +
`pip freeze` hash) and of the cell/catalogue inputs, as separate named manifest fields so a scorecard
can say WHICH of them moved. Make `removed` a loud warning requiring a deliberate separate act.

### S3 — PLAN ships runtime-written state, contradicting the docstring

`tools/deploy.py:13-16` asserts "PLAN below is the whole deployable surface and it contains no
state". Two shipped files are state by the module's own definition:

```
tools/alpha_loop/knowledge.json   (81,204 bytes)
tools/alpha_loop/knowledge.lock
```

`tools/alpha_loop/knowledge.py:15-16` defines `KB = <this dir>/knowledge.json` and
`LOCK = KB.with_suffix(".lock")`; `save()` writes it atomically (fsync + `os.replace`) and `load()`
explicitly refuses to overwrite learned memory with a blank KB on a torn read. The deploy bypasses
all of that: rsync replaces the target's copy with the MacBook's. It also pollutes the identity in
the other direction — editing a JSON of learned facts changes the pipeline's version id.

**Not happening today, measured.** The target's copy is byte-identical to local
(`md5 1ca7dca816e07f813220726154e313d0` both sides), dated Jul 25, owner `501:staff` — i.e. it was
rsynced there and has never been written there.

**MECHANISM: UNKNOWN** for the lock-inode claim. One auditor reported that an rsync 3.x receiver
replaces the inode so two processes can both hold the flock. The receiver here is rsync 3.4.1
(measured), so the premise holds, but I did not reproduce the broken mutual exclusion against this
target and nothing on `/opt/wq` currently runs `tools/alpha_loop`. What would settle it:
`ls -l /proc/*/fd 2>/dev/null | grep knowledge.lock` on the VPS, read-only.

**Fix.** Add a per-path exclusion list beside `SKIP_PARTS`/`SKIP_SUFFIX` (at minimum these two
paths), add `.lock` to `SKIP_SUFFIX`, and re-word the docstring — `state/` and `fetched/` are not the
only places this repo keeps state.

### S4 — 39% of the "deployable surface" is generated content the loop writes into

`forge/hypotheses/` and `forge/composites/` are runtime-written directories inside the shipped tree.
`forge/llm/author.py:36-37` stages generated mechanisms into `forge/hypotheses/staged/` and
`forge/composites/staged/`; `forge/offline/promote_staged.py` moves them **up** into
`forge/hypotheses/*.yaml` and `forge/composites/*.yaml` — paths PLAN ships and rsync overwrites.

Measured: 211 of the 537 shipped files are `.yaml` under these two directories (extension census:
312 `.py`, 211 `.yaml`, 6 `.sh`, 3 `.json`, 2 `.md`, 1 `.lock`, 1 `.js`, 1 `.txt`). On the target,
`forge/hypotheses/staged/` and `forge/composites/staged/` hold **27 files each** and both are empty
locally — so 54 desk-generated files exist on the VPS and nowhere else.

Nothing is lost today because there is no `--delete` and nothing has been promoted. The moment
`promote_staged.py` runs on the VPS, a desk-generated mechanism occupies a plan path and the next
push silently reverts it, reported only as a number in "drift: N changed".

**Fix.** Decide explicitly which of these directories is curated code and which is output; exclude
`staged/` from PLAN or move generated output under `state/`. At minimum, print `.yaml` changes by
name rather than folding them into a count.

### S5 — D14 has no key to select on: no deploy ledger, no version stamp on anything produced

```
$ grep -rn 'pipeline_version|deploy_version|DEPLOYED.json' forge/ tools/layered_sim.py
(nothing)
```

`DEPLOYED.json` records the current version only and is overwritten on every push; `built_at` is the
manifest BUILD time, not the deploy time, and it too is overwritten. After two deploys nobody can
say which version was live yesterday at 14:00. No journal row, plan file or submission carries a
version. D14's grading set — "only alphas the graded version itself produced" — cannot be
reconstructed even when the tool works perfectly, and D1's "scored over the quota days it runs" has
no day boundaries.

**Fix.** Append one line per successful deploy to an on-target `.deploy/history.jsonl`
(`{version, deployed_at, git_sha, git_dirty, previous_version}`), and have `forge/runner.py` read
`DEPLOYED.json` once and stamp `meta.pipeline_version` on every construction, so each journal row and
each submission carries the version that made it.

### S6 — The smoke certifies 216 tests and ships 537 files; the dispatcher that spends the quota has none

`SMOKE["tests"]` at `:148` is `pytest forge/tests`. Counted:

| root | test functions | files |
|---|---|---|
| `forge/tests` | 216 | — |
| `tools/tests` | **691** | 23 |

248 of the 537 shipped files are `tools/`. `tools/layered_sim.py` is the dispatcher that POSTs every
simulation and writes every journal row; it ships on every push and no smoke test exercises it. A
regression there ships green and the first thing that touches it is a live round spending quota.
`tools/tests/test_deploy.py` — this module's own suite — is in the unrun set.

Two more shipped artefacts are never checked at all: `forge_loop.sh` is never even `bash -n`'d, so a
syntax error ships green into a `Restart=always` crash loop; `auth_daemon.py` is never imported, so a
broken auth daemon ships green and every subsequent round skips on "auth dead".

The docstring at `:139` calls this "the suite the desk already maintains". The desk maintains 907 test
functions and the smoke runs 216 of them.

**Fix.** Run both roots (`pytest forge/tests tools/tests`), add `bash -n forge_loop.sh` and an import
of `auth_daemon`, or state in the docstring which suite runs and why the rest is out of scope.

### S7 — `rm -f` is built by string interpolation with no quoting

`:221` `" && ".join("rm -f %s" % p for p in sorted(added))`; `:223` `"tar -xzf %s"`; `:212-213` the
`tag` interpolated raw, where `tag` derives from the `version` field of a file read off the target.

`_ssh` at `:157` shell-quotes every argument and its docstring explains why — "joining argv on
spaces let bash tear it apart — caught by running it". Three of the four ssh call sites bypass it:
`:166` (`round_in_flight`), `:210` (`snapshot`), `:222` (`rollback`). The guard is absent from the
one function that runs `rm -f`.

**Latent, not live.** I measured all 537 shipped paths for spaces, `*?[]`, shell metacharacters,
newlines and leading dashes: **0 of 537** in every category. But the repo root already contains
`[DSC@UIT 2026] Danh sách mô hình - Sheet1.csv`, which has both a space and brackets, so the desk
does create such names; one landing under `forge/` or `tools/` arms it. GNU tar's `-T` defaults
compound it — on the target, `tar --help` documents `--no-verbatim-files-from` (a name starting with
dash is read as an option) and `--unquote` as the defaults.

**Fix.** Route all four sites through `_ssh`, or `shlex.quote` every interpolated path and the tag.
For the deletion list, pipe NUL-separated paths to `xargs -0 rm -f` rather than building a shell
chain, and pass `--verbatim-files-from` to tar.

### S8 — No mutual exclusion, and snapshot tags collide

`:246` `tag = "pre-%s" % (remote["version"] if remote else "unknown")` — derived only from the
target's version, so a retry after a failed push reuses the tag and overwrites
`.deploy/pre-<W>.tgz`. If the first rollback did not fully restore, the second snapshot captures the
damaged tree as the restore point and the original becomes unrecoverable.

No lock exists (`grep 'flock\|lockf\|Lock('` → nothing), so two operators — or an operator and a
future CI job — can interleave rsync and rollback on the same tree, both computing the same tag and
both writing the same archive. CLAUDE.md RULE 1 states the general form: one loop at a time, holding
a lock. Nothing prunes `.deploy/*.tgz` either; `/opt/wq/.deploy` does not exist yet, and the volume
also holds `/opt/wq/state` (measured 1.1 GB).

**Fix.** Put the outgoing version and a timestamp in the tag, take an flock on the target for the
whole push, and prune to the last N archives.

---

## MINOR

### M1 — The smoke is not read-only
`:126-127` says "runs read-only checks there". `forge/runner.py:491-492` does
`PLANS.mkdir(parents=True, exist_ok=True)` and writes `state/forge/plans/999.json`; `notify_queue` at
`:433-437` overwrites `state/forge/library_count` — both unconditionally, before the `not live`
branch and before `return 2`. Measured on the target: `state/forge/plans` already holds 199 files and
`state/forge/library_count` exists (3 bytes, written 2026-09-23 00:23). The smoke's `pytest` also
omits the `-p no:cacheprovider` that the desk's own `wq-forge-tests.sh` passes, so it writes
`/opt/wq/.pytest_cache`. The snapshot and rollback paths write and delete too.
**Fix:** run the planner with a scratch `--root`, add `-p no:cacheprovider`, and re-word the comment —
the true claim is "spends no quota", which is accurate.

**SUSPECTED, with the experiment that would settle it.** `forge/offline/recover_orphans.py:37-47`
globs every `*.json` in that directory, and `match()` at `:60-73` returns `None` when candidates
differ on `category` or `arm` (`meta.seed` is excluded, `category`/`arm` deliberately are not). The
smoke plans 20 constructions where production plans 300, so the same formula could be allocated a
different `category` and become permanently ambiguous — the 2026-09-09 ORPHAN-UNMATCHED regression
that file documents. Production seeds are `date +%s` so 999 never collides by seed. I did **not**
demonstrate an actual ambiguous pair. Settling experiment: compare `meta.category` / `meta.arm` for
formulas shared between a `999.json` and a production plan; where they differ, `match()` returns
`None`.

### M2 — `git_dirty` does not measure what its docstring says
`:101` says "True when tracked files differ from HEAD"; `:103` runs `git status --porcelain`, which
also reports untracked files. Measured: 1,812 porcelain lines, **52** with `-uno`. Both are non-zero
today, so the flag reads True either way right now — but with 1,760 permanently untracked entries it
can never become False, so the provenance signal it carries ("this deploy did not come from a clean
commit") can never fire.
**Fix:** pass `-uno`, matching the docstring, or record the two counts separately.

### M3 — `git_dirty` renders "I could not tell" as "clean"
`:105-107` returns `None` on any `OSError`/`SubprocessError` or non-zero git exit; `:239` and `:288`
print `", DIRTY" if local["git_dirty"] else ""`, which prints nothing for `None`.
**Fix:** render `None` as `, git-state UNKNOWN`.

### M4 — The bytes hashed and the bytes shipped are two separate reads
`:235` `local = manifest()` reads all 537 files to hash them; `:249` `fmap = file_map()` and `:255`
`dest.write_bytes(local_path.read_bytes())` read them again. An editor autosave or a background agent
between the passes makes the shipped bytes differ from the manifest that names them — the exact
failure the module exists to prevent, inside the module.
**Fix:** stage first, hash the staged tree, write the manifest from those hashes.

### M5 — The executable bit is dropped on every shipped script
`:255` copies bytes, not mode; `rsync -a` then faithfully preserves the *staged* mode. Reproduced:
source `0o755` → staged `0o644`. Ten shipped files carry the bit: `forge_loop.sh`,
`tools/{calibrate_all,measure_when_ready,queue_after,simfeed,simq}.sh`,
`tools/supervisor/act_{clear_lock,kill_extra,refresh,restart_driver}.py`. Impact is narrow and I
checked rather than assumed — the unit uses `ExecStart=/bin/bash /opt/wq/forge_loop.sh`, so the loop
survives. The real consumer is `tools/simfeed.sh` calling `tools/simq.sh` by path. Side effect:
rsync's quick check re-transfers all 538 files every deploy, and the deploy erases the mtime drift
the docstring cites at `:5-6` as its founding evidence.
**Fix:** `shutil.copy2` instead of `write_bytes`.

### M6 — There is no dry run for `push`
`main()`'s choices at `:281` are `version|manifest|drift|push|remote`. For a tool whose worst outcome
is a 537-clause `rm -f` against a possibly-nonexistent archive on a production host, the only way to
see the commands it would issue is to issue them. I had to record `subprocess.run` to see them.
**Fix:** add `--dry-run` printing the snapshot command, the rsync argv, the counts and the rollback
command.

### M7 — Nothing is verified after a rollback, and the rollback's own oracle is a string match
`:225` returns `"restored" in stdout`; `:275` discards even that boolean. The smoke is never re-run
against the restored tree, while the unit restarts onto it within 60 s.
**Fix:** re-run the smoke after a rollback and treat a failed post-check as a page-the-operator state.

### M8 — The test suite's coverage stops exactly where the danger starts
`pytest tools/tests/test_deploy.py -q` → **13 passed**. The `nonet` fixture at `:118-131` replaces
`snapshot` and `rollback` with lambdas that only set a flag, and `subprocess.run` with a fake that
always succeeds — so the two functions that issue destructive commands have **zero** coverage, and
no test covers a failing snapshot, an empty archive, a partial rsync, a timeout, a concurrent push,
`remote_manifest` returning None because ssh failed, or the state left after a failed first deploy.
Separately, `test_the_real_repo_plan_resolves_and_ships_no_state` (`:94-99`) asserts only that no
destination starts with `state/` or `fetched/`; `tools/alpha_loop/knowledge.json` and
`knowledge.lock` pass that assertion while being exactly what the test is named for.
**Fix:** assert against a declared allowlist, and add tests for snapshot/rollback against a local
fake target: missing tar, member-less tar, a path with a space, and `added == every plan path`.

---

## Positively confirmed behaviours

These were checked and are correct. Several are load-bearing and should not be "improved" away.

1. **RULE 1 is not violated.** No SMOKE entry passes `--live`; `tools/tests/test_deploy.py:162-167`
   pins that. I traced the planner end to end: `forge/runner.py` calls `layered_sim.run(..., live=False)`,
   and `_dispatch` returns `[]` inside `if not live:` **before** `session()` and before
   `open(out_path, "a")`. No session, no cookie read, no journal row, no POST, no quota.
2. **The journal is never at risk from the smoke or from the rsync.** `state/layered/runs/forge.jsonl`
   is not opened for writing by any smoke check, and `state/` is outside every plan destination.
3. **The refusal to use any `--delete` flag (`:257-259`) is correct and correctly reasoned, and is the
   single best decision in the module.** The argv is exactly
   `["rsync", "-a", <staged>+"/", "root@160.25.88.163:/opt/wq/"]` — no `--delete`, `--del`,
   `--delete-excluded`, `--remove-source-files`, `--inplace`. The staging tree holds only PLAN paths,
   so `state/` (1.1 GB measured), `venv/`, `fetched/` and `harness13/` are never candidates for
   removal. I string-tested the real 537-clause rollback chain: `rm -f state/`, `rm -f venv/`,
   `rm -f fetched/` are all absent.
4. **The content hash is sound arithmetic.** `version_id` (`:74-87`) feeds `path \0 digest \n` per
   entry over sorted items into one sha256 — order-independent, rename-sensitive, swap-sensitive.
   `content_hashes` hashes bytes, not mtime.
5. **`_shippable` (`:48-51`) is correct.** `p.name.endswith(SKIP_SUFFIX)` uses `str.endswith`'s tuple
   form and the `SKIP_PARTS` membership test over `p.parts` catches both `__pycache__` directories and
   `.DS_Store` files. Verified: 0 of 537 shipped paths contain `__pycache__` or end in `.pyc`.
6. **The library YAMLs ARE covered by the version id** — 211 `.yaml` files under `forge/` are hashed.
   A hypothesis edit does move the version. (This refutes a premise one auditor was handed; see
   S4 for the separate problem that they are also runtime-written.)
7. **`drift()` (`:117-122`)** computes added/removed/changed correctly as set operations, and its test
   pins the three-way split and the empty case.
8. **The staging directory is safe.** `staged = ROOT / ".deploy_stage"` with `ROOT` absolute and
   resolved, so `rm -rf` can never receive an empty or root argument; it is `rm -rf`'d both before
   (`:251`) and after (`:262`); it is at the repo root and PLAN ships only `forge/`, `tools/` and four
   named root files, so it cannot self-include; and it is in `.gitignore:40` so it cannot be committed.
9. **`shlex.quote()` per argv element in `_ssh` is correct** and is load-bearing for the `-c` program
   in the import smoke. (It simply does not cover three of the four call sites — S7.)
10. **`pgrep -fc '[r]unner.py'` does not self-match.** Run read-only against the target while a live
    round was dispatching: it returned 1, so the guard would correctly refuse a deploy right now.
11. **The import smoke would catch its motivating incident.** `forge/novelty.py` imports repo-root
    `fingerprint`, which PLAN ships, and `novelty` is one of the six forge modules the check names.
12. **A 24 KB remote command is not truncated by the ssh hop** — nothing saves you from the full
    537-clause chain.

---

## Dropped, corrected, or reduced

| claim | adjudication |
|---|---|
| spec: the smoke "consumes the m13 transition so the next real round never reports the library grew" | **DROPPED.** `systemctl show wq-forge -p Environment` returns `N`, `ROUNDS`, `FORGE_ARGS` only — `WQ_FORGE_NOTIFY` is not set in any unit, and `runner.py:437` gates the alert on it. There is no alert to consume. The `library_count` **write** still happens (it precedes the env check), so the write half of M1 stands; the behavioural consequence does not. |
| spec: `git_dirty` "can never be False … conveys nothing" | **REDUCED.** `--porcelain -uno` returns 52 lines, so tracked files are dirty today too; the flag is True under either definition right now. The permanent-True property is real but comes from the 1,760 untracked entries, not from a clean tracked tree being misreported. Kept as M2 with both numbers. |
| assume: openrsync may write in place, so a round could read a truncated module | **DROPPED as stated.** The receiver is rsync 3.4.1 (measured on the target) and the man page there confirms `--inplace` is opt-in, so the default is temp-file + rename. The sender being macOS openrsync does not govern the receiver's write strategy. The surviving true point — the swap is not atomic at the *set* level — is kept under M-new below. |
| assume: `config.py`/`robust.py` omission as an independent BLOCKER-grade defect | **REDUCED into S2.** Confirmed absent from both PLAN and `/opt/wq`, and imported by six shipped `tools/*.py`. But `grep 'import config\|import robust' forge/` is empty — no forge module imports them, so the forge loop is unaffected. It is a version-coverage gap, not a runtime break. |
| assume: the lost exec bit would kill the forge loop | **SELF-REFUTED by that auditor and re-confirmed by me.** `ExecStart=/bin/bash /opt/wq/forge_loop.sh`. Kept as M5 at minor severity. |
| assume: `git_dirty`'s 20 s timeout would fire on this repo | **REFUTED by measurement** (that auditor's own, re-checked): `git status --porcelain` is fast here. The `None`-renders-as-clean defect survives independently as M3. |
| destroy: rsync replacing `knowledge.lock`'s inode breaks mutual exclusion on this target | **NOT ESTABLISHED.** The container demonstration is credible and the receiver version matches, but nothing on `/opt/wq` currently runs `tools/alpha_loop`, the lock is 0 bytes from Jul 25, and the knowledge file is byte-identical to local. Recorded inside S3 as **MECHANISM: UNKNOWN** with the read-only command that would settle it. |
| destroy: stale un-deleted modules are importable and running | **SUSPECTED, kept as such.** `d["removed"]` is 0 today. The target does carry files under the shipped trees that no manifest accounts for, but I did not test whether any is importable-and-stale. Settling experiment named in S2. |
| forge/tests test count (spec "200", destroy "230 passed") | **Neither is a finding.** I counted 216 `def test_` functions; collected counts differ from function counts through `parametrize`. S6's point is the ratio — 216 run, 691 not — not the exact integer. |

---

## Found in adjudication, reported by none of the three

### A1 — `added` is semantically wrong on a first deploy, and that is what turns a recoverable failure into an unrecoverable one

All three reported "`added` = 537". None stated the consequence I measured: **499 of those 537 paths
already exist on the target** (493 byte-identical + 6 different). They are not *added* by this
deploy — they are *overwritten*.

For an overwritten file the correct undo is "restore it from the snapshot". The module's undo is
"delete it, then restore it". So even with a **perfect** snapshot, `rollback()` needlessly drives the
production tree through a state where 499 files do not exist, in a single remote shell command
24,157 bytes long. Any interruption inside that window — the ssh dropping, the 300 s timeout firing
between the last `rm -f` and the `tar` — leaves the tree destroyed with a perfectly good archive
sitting beside it, unused.

This reframes the fix. Verifying the snapshot (C1) is necessary but not sufficient: `added` must mean
"paths that did not exist on the target", which requires a remote existence test, not a subtraction
of two manifests one of which is empty. With that, a first deploy's rollback becomes pure restore and
deletes nothing at all.

### A2 — A green deploy does not take effect, and nothing says so

`grep -n 'systemctl' tools/deploy.py` → **0 occurrences**. `push()` never restarts `wq-forge`.

`/bin/bash /opt/wq/forge_loop.sh` is running right now as pid 2665426 (measured). `forge_loop.sh:57-60`
spawns a **fresh** `python forge/runner.py` per round, so shipped `.py` changes are picked up on the
next round. `forge_loop.sh` itself is not: rsync 3.4.1's default is temp-file + rename, so the running
bash keeps its descriptor on the old inode and continues executing the old script until the unit
restarts.

So after a green deploy the target runs **new Python under an old loop driver**, while `DEPLOYED.json`
asserts one coherent version. That splits D14's attribution boundary — "the alphas version X
produced" — along a seam the manifest cannot see.

Label: the fd/inode reasoning is **EX-ANTE**, from rsync's documented default plus POSIX semantics. I
did not perform a swap on the target. **Settling experiment:** on a scratch target, rsync a modified
`forge_loop.sh` under a running bash and observe whether the loop's behaviour changes before a
restart.

**Fix.** Make the deploy own the unit: `systemctl stop wq-forge` → wait for `/var/lock/wq_forge.lock`
→ rsync → smoke → `systemctl start wq-forge`. That closes B2's race in the same move.

### A3 — B4 is the ignition and it is one network blip wide

Two auditors noted `remote_manifest()`'s three-way conflation as a correctness defect. Neither
connected it to trigger probability. It is the bridge that makes C1 reachable on an **established**
target, not only a virgin one: one transient ssh failure puts all 537 paths into `added`, names the
snapshot `pre-unknown`, and arms the full-tree delete on a box that was perfectly well deployed a
minute earlier. It is promoted to BLOCKER above for that reason.

---

## What must be fixed before `push` may be run against `/opt/wq`

1. **C1** — snapshot verifies itself (member count), `push` aborts if it cannot; `rollback` extracts
   before it deletes.
2. **A1** — `added` computed from a remote existence test, so a first deploy's rollback deletes nothing.
3. **C2** — `DEPLOYED.json` written after the smoke is green, as a separate step, and removed on a
   rolled-back first deploy.
4. **B1** — `try/except` around everything from the snapshot on, routed into rollback; `BatchMode=yes`.
5. **B3** — the planner smoke accepts exit 2.
6. **B4** — "could not read the manifest" is a distinct state that aborts, never "never deployed".
7. **B2** — the round guard fails closed and the deploy holds `/var/lock/wq_forge.lock`.

D4 and D16 remain open requirements, not delivered features (B5, B6), and must be reported as such on
any scorecard that cites them.

**Data-loss risk, stated plainly.** The journal is safe: there is no `--delete` of any kind, `state/`
is outside every plan destination, and the real `rm -f` chain contains no `state/`, `venv/` or
`fetched/` clause. The loss at risk is the **code tree** — 499 existing files under
`/opt/wq/forge`, `/opt/wq/tools` and four root filenames, on a host that is not a git repository, of
which 6 differ from local and therefore exist nowhere else on earth.
