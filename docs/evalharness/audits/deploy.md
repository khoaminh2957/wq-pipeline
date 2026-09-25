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


---

# Third pass (2026-09-23)

Adjudicator, third pass. Three auditors reported: **regression**, **destroy** and **assume**. I
re-verified every defect kept below, using one of four means:

- reading the line in the pinned file;
- an offline harness that drives the real `deploy.main(["push"])` with every `subprocess.run`
  replaced (scratchpad `h.py`);
- a container running **rsync 3.4.1 and GNU tar 1.35**, the target's exact versions, with this Mac's
  openrsync as the sender and the production argv (scratchpad `rs.py`);
- read-only `ssh -n -o BatchMode=yes` (`cat`, `ls`, `stat`, `pgrep`, `systemctl is-active`).

Nothing was written on the VPS and nothing was simulated.

**Pinned.** `tools/deploy.py` is sha256 `db14370d…` (520 lines, mtime 09:42:36).
`tools/tests/test_deploy.py` is `0b2acf1b…`. The file changed under the auditors. *assume* audited
`ec241e14…` (472 lines). *regression* audited an intermediate version. *destroy* audited `db14370d`.
Every line number below refers to `db14370d`. If the file changes again, this verdict lapses.

## Contradictions settled

| claim | settled |
|---|---|
| The brief says both earlier reports are in this file | **False.** Before this section the file held only the first-pass adjudication (695 lines). A grep for `inactive`, `pre-unversioned`, `while read`, `argparse` and `chown` found nothing in `docs/`. The second pass (46 defects) is not on disk, so only the 10 second-pass items the brief names are graded. |
| Test count: 26 (brief and *assume*), 27 (*regression*), 28 (*destroy*) | The current file has **28** `def test_`, and `pytest tools/tests/test_deploy.py -q` reports **28 passed**. The other counts belong to earlier versions of the file. |
| Plan and target counts: 540/499/41 (brief), 546/503/43 (*destroy*) | At 10:01 I measured **547 plan paths: 503 present on the target (493 byte-identical, 10 different) and 44 new.** At 10:05 the plan had **549** paths, because `tools/ci_baseline.json` (created 10:02:35) and `tools/tests/test_ci_gate.py` had been added. The counts move with local edits. The four harness files added to PLAN at 09:42 are all present on the target. |
| Files that differ: 6 (first pass), 9 (*destroy*) | **10.** `forge/{probe,runner,submit}.py` and their three tests, `tools/{auth_link,auth_only,measure_backlog}.py`, and `tools/tests/test_layered_sim.py`, which was edited locally at 09:54. Every one differs in size, so rsync's quick check skips none of them today. |
| *destroy*: file-to-directory loss "not tested on rsync 3.4.1" | **Now tested on 3.4.1**, and it reproduces (see Survives, D1). |
| *assume*: the rsync quick-check skip is SUSPECTED | **Demonstrated on 3.4.1** (see Introduced, I2). It does not fire for today's diff. |

## Earlier findings: what genuinely landed

**First pass.**
- **C1 landed.** The snapshot checks rc and requires member count = `len(paths)` (`:267-274`). `push` refuses when there is no snapshot (`:430-432`). The rollback extracts before it removes (`:282-284`). An empty present-set is handled (`:262-264`). The residual is new and listed as I4.
- **A1 landed.** `to_delete` = plan paths minus the remote existence probe (`:426`).
- **C2 landed.** The manifest is written only after the `try` (`:469`), atomically via tmp then `mv` (`:303`), and is never staged. A rolled-back first deploy leaves no `DEPLOYED.json` (harness case `smoke_red`: no manifest call).
- **B3 landed** (`_smoke_ok`, `:187-193`).
- **B4 landed** (`:223-241`). The residue is minor: non-dict JSON crashes at `:415` with exit 1 before any swap (harness cases `listjson` → TypeError, `nover` → KeyError).
- **S7 landed.** Paths travel NUL-separated on stdin, and every interpolation is `shlex`-quoted.
- **M5 landed** (`copy2`).
- **Partial:** B1, B2, M1, M7, M8, S5, S8 and A2. The detail is under Survives.
- **Not landed:** B5, B6, S1, S2, S3, S4, S6, M2, M3, M4 and M6.

**Second pass (only the 10 named items).**
- **Landed:** the `while read` last-path skip (Python probe plus `CHECKED n`); the constant snapshot name (a UTC stamp at 1-second resolution); `'active' in 'inactive'` (`_is_active`); argparse exit 2 (`_smoke_ok`); the left-over `plans/999.json` (seed walk, and the smoke removes only its own plan); the stripped exec bit; the rsync chown (`--no-owner --no-group`); and staging in the repo root (`mkdtemp`).
- **Partial:** "`except Exception` misses KeyboardInterrupt" and "return values discarded". The detail is in S-a below.

## What survives (re-verified)

**D1 — rsync silently deletes a target FILE where the plan now has a DIRECTORY. CATASTROPHIC mechanism, not armed today.**
- *Mechanism.* The probe (`:244-254`) and the snapshot test only leaf paths, so the displaced file is never archived.
- *Reproduced with rsync 3.4.1.* `/opt/wq/tools/fixtures` held `TARGET-ONLY DATA`. I shipped `tools/fixtures/x.json` through `_stage` and the production argv. rsync returned rc 0, `fixtures` became a directory, and the data was gone.
- *Target today (read-only `stat`).* All 20 existing ancestor directories of the 547 plan paths are directories. The 21st, `tools/tests/fixtures`, is absent. So no instance exists today, but every push that introduces a new directory reopens the case.
- *Fix.* The probe reports any ancestor that exists as a non-directory, and push refuses.

**D2 (was M4) — the bytes hashed, probed and snapshotted come from one walk (`:408`); the bytes shipped come from a second walk (`:438`). DEMONSTRATED.**
- *Harness.* A path that appears between the two walks is staged and rsynced. It is absent from the probe stdin, the snapshot stdin, the manifest written to the target and the rollback's `to_delete`. The run exited 0, and exited 1 with a red smoke.
- *Irrecoverable case.* If the late path already exists on the target as a target-only file, its bytes are overwritten and no copy exists anywhere. `tools/recover_harvest.py` is such a file: it runs under `wq-harvest` (pid 3235634) and does not exist locally.
- *Measured edit rate.* 9 shipped files were edited in the last 60 minutes, and the ship set grew by 2 during this adjudication. On this desk the window is live, not hypothetical.
- *Fix.* Stage once from the fmap that was hashed, and refuse if any staged sha256 differs from `local["hashes"]`.

**D3 — the smoke runs after the swap, and nothing holds the loop off. BLOCKER** (all three auditors; B2 and A2 were only partly addressed).
- *Code order.* `swapped = True`, then rsync (`:442-443`), then the smoke (`:449`). The rollback (`:279-296`) has no busy check at all.
- *What BUSY matches (tested).* It matches `runner`, `submit`, `harvest` and `probe`. It does **not** match `forge/offline/recover_orphans.py`, which appends to `state/layered/runs/forge.jsonl` (`recover_orphans.py:26,200,205`). It does not match `refresh_cells.py`, `record_adjudication.py`, `/opt/wq/tools/recover_harvest.py` (which imports `layered_sim` and appends `recovered.jsonl`, as read on the target) or `sleep 300/3600`.
- *Live at 10:01.* `forge/runner.py --live` (pid 3235675, seed = 09:40:08) and `wq-forge`, `wq-harvest`, `wq-auth` and `wq-outbox` were all `active`.
- *Why it matters today.* The first push ships a new `forge/runner.py`, which dispatches live sims, and a new `forge/submit.py`, which makes real POSTs (`forge_loop.sh:88`, `--submit --cap 4`). These are the modules the smoke exists to vet, and a round that starts in the window runs them unvetted.
- *Fix (for this push).* Quiesce the writers for the duration.

**D4 — a restart SIGTERMs the whole unit, and the guard misses journal writers. SERIOUS.**
- The unit file has no `KillMode` line (so the default, control-group, applies) and sets `Restart=always` (read on the target). `restart_loop` (`:313`) guards only with BUSY, so `recover_orphans.py` (up to 900 s per round) is killable.
- A torn or lost journal row is **SUSPECTED, not demonstrated.** To settle it, SIGTERM a writer during a multi-chunk flush in a scratch harness.
- `systemctl restart` also starts a unit that was deliberately stopped. This is EX-ANTE, from systemd's documented behaviour. The arm drivers do exactly that stop (`c11_run.sh:46`, `pow_run.sh:85`, `systemctl stop wq-forge`). No arm driver was running at 10:01.

**D5 — SIGTERM, SIGHUP and SIGKILL skip the rollback. SERIOUS.**
- `deploy.py` has no `signal` handling (grep). Python's default SIGTERM action terminates without running `except` or `finally` (EX-ANTE, from the language documentation).
- An agent's Bash call has a 120 s default timeout, and the target's own forge suite takes about 61 s (`tests_last.json`). So a push run under that default can be killed mid-smoke. The result would be new code live, unsmoked, with no manifest and no rollback.

**S-a — exit codes are not "one per outcome", and the ledger misrecords. SERIOUS for anyone reading the result.** Measured with the harness driving `main(["push"])`:
- A timeout in `write_manifest` after a green smoke exits **1** (= `rolled_back`). The new code is live, and no ledger row is written.
- `CHECKED x` from the probe produces a ValueError and exit **1** (`:177`, not caught at `:423`).
- Ctrl-C mid-smoke exits **130** whether the rollback succeeded or failed (`ctrlc_smoke` vs `ctrlc_rbfail`). No ledger row is written.
- A deferred restart exits **0** and logs `deployed`.
- A no-op push logs `deployed`.
- A failed restart exits 4 and prints "the record of it is not", although the manifest was written (`:471-473`).
- argparse errors exit 2 (= `refused`).
- No automated caller exists (`.github/workflows/ci.yml:13` says deployment is not wired), so these codes mislead a human, not a pipeline.

**Other survivors, each re-verified.**
- **B5 not landed.** No trigger after the deploy. After a green push there is also no recorded undo: `to_delete` is persisted nowhere, and `main()` has no `rollback` command. The undo can be reconstructed by hand (DEPLOYED.json keys minus the `.tgz` members), so this is not a loss.
- **B6 not landed** (ci.yml:13).
- **S1 not landed.** No remote re-hash.
- **S2 not landed.** `wq-harvest` runs `harvest_loop.sh` and `tools/recover_harvest.py`, neither of which is in PLAN.
- **S3 not landed.** `knowledge.json` and `knowledge.lock` are shipped (today byte-identical), and now `tools/ci_baseline.json` too.
- **S6 not landed.** The smoke runs `forge/tests` only.
- **S8 partial.** There is no lock and no pruning.
- **M1 partial.** `library_count` is still written (`runner.py:460`), and pytest still lacks `-p no:cacheprovider`.
- **M2 and M3 not landed** (`:117`, `:413-414`).
- **M6 not landed.** There is no dry run.
- **M7 partial.** There is still a string oracle and no smoke after a rollback.
- **M8 partial.** The `nonet` fixture (`:182-209`) replaces `snapshot`, `rollback`, the probe and `restart_loop`, so no test executes a destructive shell string. The "virgin target" test fakes a probe result that the real probe cannot return on a host without `venv/`.
- **Minor.**
  - `_remote` has no `-n` (`:152,163`).
  - rsync has no `-e 'ssh -o BatchMode=yes'` (`:443`).
  - The planner smoke's `cd /opt/wq &&` binds only to `s=…` (`:333`, `:343`). This is harmless today.
  - `_stage` leaks its tempdir if `copy2` raises (`:359-364`).
  - `.deploy/` grows without bound. A snapshot is also written for attempts that the re-check at `:439` then refuses.

## What this rewrite introduced

- **I1 — `/opt/wq` becomes mode 0700.** `mkdtemp` makes the stage root 0700, and `rsync -a stage/` copies that mode to the destination root. The rollback does not restore it. Reproduced with rsync 3.4.1: 755 before, 700 after. The target is 755 today. There is no functional effect today, because every wq process runs as root.
- **I2 — `copy2` preserves local mtimes, so rsync's size+mtime quick check can now skip a changed file.** Reproduced: the target kept `print('OLD')` while the manifest would name `NEW`. The earlier `write_bytes` re-sent every file. Today's 10 differing files all differ in size, so nothing is skipped this time.
- **I3 — the rollback removes plan paths that were absent at probe time, using a list computed minutes earlier.** A target-side file created at such a path in the meantime would be deleted. **SUSPECTED.** No target writer to a plan path has been identified.
- **I4 — the snapshot's `tar -tzf … | wc -l` takes `wc`'s exit status.** Reproduced with GNU tar 1.35: an archive truncated by 8 bytes listed 2 members with pipeline rc 0, which `snapshot()` accepts, while `tar -xzf` on it returned rc 2.
- **I5 — the restart path added `systemctl restart`,** with its control-group kill and its start-when-stopped behaviour (D4). The "deferred" branch is final and reports success.
- **I6 — the DORA ledger** (`:384-400`) is written on the MacBook. It re-hashes the tree after the push (`:390`), a third read, logs a no-op as a deploy, and loses every attempt that ended in an exception or a signal.
- **I7 — the EXIT map** collides with Python's own exit 1 for uncaught exceptions and argparse's 2 (S-a).

Carried over from earlier versions, not introduced, and demonstrated now: the rollback's `tar -xzf` unlinks and recreates each file (the inode changed, 20 → 21). Under ENOSPC it leaves a live module truncated, belonging to neither version. The container run gave "Wrote only 2560 of 10240 bytes", rc 2, and a size of 12,288 against 202,632. The bytes survive in the `.tgz`. The target has about 80 GB free.

## Missed by all three auditors

- **N1 — for today's push, several SERIOUS findings are inert, and D3 is sharper.** Byte comparison on the target shows `forge_loop.sh`, `auth_daemon.py`, `tools/sender.py` and `tools/layered_sim.py` are **identical**. A2's point that never-restarted units keep old code, and the deferred-restart staleness, therefore change nothing on this particular push. Conversely, the forge files that do change are exactly the live-path modules (`runner.py`, `submit.py`, `probe.py`). The tools files that change are `auth_link.py`, `auth_only.py` and `measure_backlog.py`. No timer's `ExecStart` runs one of them directly: the timers run `mint_link.py`, `watchdog.py`, `auto_cycle.py`, `health_report.py` and `deadman.py`, as read on the target. Whether one of those imports a changed file was not checked.
- **N2 — `wq-forge-tests.timer` runs the same `forge/tests` in the same `/opt/wq` daily at 10:30** (`OnCalendar=*-*-* 10:30:00`) and writes `state/forge/tests_last.json`, which the digest reads. A push overlapping that run lets `tests_last.json` record the verdict on code that is then rolled back. Both runs' `BD.drill()` walk seeds from 900000000 (check, then write), so they can pick the same throwaway seed. Minor. The only files involved are throwaway plans.
- **N3 — a killed local ssh does not stop the remote command. SUSPECTED, EX-ANTE from OpenSSH semantics without `-t`.** This applies to a smoke step as much as to rsync. After Ctrl-C or a `TimeoutExpired` during the smoke, the remote pytest or planner keeps running while `rollback()` extracts under it. *regression*'s rsync-receiver race is one instance of this. To settle it, on a scratch sshd, kill the client during a long remote `sleep` and check `pgrep` on the server.
- **N4 — `--force` skips both busy checks (`:405`, `:439`),** and the ledger row does not record that it was used. Minor.

## Dropped or reduced

- *regression*'s "the brief's premise is wrong": **kept.** The second pass is not on disk (see Contradictions settled).
- *destroy* ranked D2 CATASTROPHIC: **kept as a demonstrated mechanism.** The irrecoverable case needs a local file to appear at a target-only path during the window. Its other cases (a file shipped outside the manifest and outside the rollback) are the likely ones.
- The *assume* claims that `promote_staged` could overwrite shipped files, and that 68 files are target-only: **not re-measured by me.** They stay attributed and SUSPECTED.
- The inode-swap break of `knowledge.lock` stays **MECHANISM: UNKNOWN on this target**, as in the first pass. `knowledge.py` does use `fcntl.flock` (`:52-60`). No `alpha_loop` process was running at 10:01. The file is byte-identical on both sides.

## VERDICT (third pass)

**NO. `python3 tools/deploy.py push` must not run against the live `/opt/wq` as it stands.** It would
refuse right now anyway, because a `--live` runner is in flight. The first idle gap, however, lets it
swap code that has not passed the smoke under a live loop, and a `wq-harvest` process that no guard
sees is running the whole time.

**Shortest ordered list to YES** (for `db14370d` plus these changes, and only for them):
1. **Code:** stage once from the fmap that `manifest()` hashed. Refuse if any staged sha256 differs from `local["hashes"]` (D2).
2. **Code:** make the existence probe report any ancestor of a plan path that is a non-directory, and refuse (D1). The condition was satisfied at 10:01 but is not guaranteed at push time.
3. **Run condition:** stop `wq-forge` and `wq-harvest` at an idle point: no BUSY child, no `recover_orphans.py`, no arm driver. Push while they are stopped. On green, `restart_loop` starts `wq-forge` and `wq-harvest` is started by hand. On a rollback, start both by hand (D3, D4).
4. **Run condition:** run from a real terminal, or a detached process with its log kept, never inside a tool call with a timeout under about 20 minutes (D5). After any Ctrl-C, trust the printed `rollback:` or `ROLLBACK INCOMPLETE` line, not the exit code (S-a).
5. *(Optional, one line)* `os.chmod(staged, 0o755)` before the rsync (I1).

**Data-loss risk, stated plainly.**
- **The journal** (`state/layered/runs/forge.jsonl`): push, snapshot and rollback have no byte path to it. There is no `--delete`, no plan destination lies under `state/`, and the rm list is a subset of the plan paths. The residual risk is indirect: rows appended by unsmoked code during the window are not undone, and a restart can SIGTERM `recover_orphans.py` mid-append (a torn or lost row is SUSPECTED). Step 3 removes both.
- **The code tree:** 10 target files differ from local and exist only there. The snapshot preserves them, so the `.tgz` in `.deploy/` becomes their only copy and must not be pruned. Two demonstrated mechanisms can destroy target bytes with no copy (D1 and D2). Neither was armed at 10:01, and steps 1 and 2 close both.
- **A rollback under a full disk** truncates live modules. The bytes survive in the `.tgz`, and the risk is negligible with about 80 GB free.

# Fourth pass (2026-09-23)

Adjudicator, fourth pass. Three auditors reported: **regression**, **destroy** and **assume**. I kept
a defect only after I had re-verified it myself, using one of four means:

- reading the line in the pinned file;
- an offline harness (scratchpad `adj4/h.py`) that drives the real `push()`. It replaces only `_remote`,
  rsync and `loop_closure`, so the real `stop_units`, `start_units`, `units_state`, `snapshot`,
  `rollback`, `write_manifest`, `run_smoke`, `_stage`, `_staged_matches` and `_undo` run;
- running the real existence-probe program on a scratch tree;
- read-only `ssh -n -o BatchMode=yes` (`cat`, `ls`, `stat`, `pgrep`, `systemctl is-active/list-units`),
  between 12:40 and 12:50.

Nothing was written on the VPS and nothing was simulated. My harness leaked stage directories into
`$TMPDIR` (4 of them, see F7), and I removed them.

**Pinned.** `tools/deploy.py` is sha256 `47db4007…` (648 lines, mtime 12:18:33), and
`tools/tests/test_deploy.py` is `ccec9015…` (37 tests, `pytest -q`: 37 passed). Every line number
below refers to `47db4007`. If the file changes again, this verdict lapses.

## Contradictions settled

| claim | settled |
|---|---|
| The brief, *regression* and *assume* audit `c8d499dd` (599 lines, 36 tests) | **The file changed at 12:18:33.** A diff against the `c8d499dd` copy in the scratchpad shows only these changes: `loop_closure()`/`LOOP_ENTRIES` (`:124-156`); `pipeline_version` in `manifest()` (`:164-176`); a refusal when the closure cannot be measured (`:504-507`); and test edits. The push path (`:375-604`) is textually unchanged. So every push-path finding carries over. Old line L maps to L+45 for L between 130 and 458, and to L+49 after that. |
| 36 vs 37 tests | 37. The rewrite added two tests and **deleted `test_a_regular_file_where_a_directory_must_go_is_refused`** (see F15). |
| Plan and target counts | Measured 12:41: **551 plan paths. 503 are present on the target and 48 are new. Of the 503, 491 are byte-identical and 12 differ.** I hashed all 491 locally from `cat` output, split at the known sizes: the 327 files with the same size and mtime, and the 164 with the same size but another mtime. The 12 that differ are those *destroy* names. |
| *assume* ranks the silent-stop class BLOCKER | **Reduced to SERIOUS.** It is demonstrated, but it loses no data, and one `systemctl is-active` after the push detects it (see the verdict). |

## The five third-pass items

1. **One file list, refuse on staged drift: LANDED for the ship path.** The walk at `:502` feeds the
   hash (`:503`), the probe (`:519-521`), `to_delete` (`:525`), the stage (`:530`) and the verification
   (`:531`). In harness case `drift_refusal`, a real byte change made during staging was refused, and
   the only remote calls were busy, read_manifest and probe. Residuals: F6, F7 and F8.
2. **Regular-file parent: LANDED.** The real probe program, run on a scratch tree, printed
   `BADPARENT regfile` and `BADPARENT dangling`, and `remote_existing` raised. A symlink to a directory
   passed (F9). Its only test was deleted (F15).
3. **Stop the units for the swap: PARTIAL.** The main paths are right. In harness case
   `green_paused_units` the order was stop, is_active, rsync, smoke, write_manifest, start, is_active.
   A failed rollback leaves the units stopped (`:602-604`). What is wrong is listed in F1 to F5 and F10
   to F12.
4. **Real terminal: still only a condition.** No signal handler exists (grep `signal` finds only the
   comment at `:204`). **SIGTERM during the smoke: exit 143. The tree is NEW, both units are inactive,
   `DEPLOYED.json` is old, there is no ledger row and the stage leaks** (harness `sigterm`).
5. **Stage root mode: LANDED** (`:439`, test `:382`). Subdirectories follow the umask, which is 022
   here. The target's `/opt/wq` is 755 (stat).

## What survives (re-verified)

**SERIOUS. All demonstrated. They cost production time, not data.**
- **F1. Paths that end with the loop stopped and no warning.** `write_manifest` and the final
  `start_units` (`:586-587`) sit outside the guard.
  - Harness `manifest_timeout_after_green`: TimeoutExpired escapes `push()`. The tree is NEW,
    `DEPLOYED.json` is old, the units are inactive/inactive, there is no ledger row and no unit
    warning.
  - Harness `red_start_timeout`: rollback, start, rollback, start, then TimeoutExpired. The units are
    inactive (F10).
  - SIGTERM: see item 4.
  - Nothing on the VPS would notice. `watchdog.py:54-55` UNITS has no `wq-forge`. `deadman.py:65-104`
    alarms only on `systemctl --failed`, and a clean stop leaves the unit `inactive`, not failed. grep
    finds no `forge` liveness check in `watchdog.py`, `deadman.py` or `health_report.py`.
- **F2. The `start_units` verdict is thrown away at `:556`, `:578` and `:600`.** The comment at `:194`
  says the opposite. Harness `red_rollback_ok_start_fails`: rc 1 `rolled_back` and ledger
  `rolled_back`, with the units `failed/failed`. The only trace is the line `units started: {…failed…}`.
- **F3. The state of the units before the push is never read.** Harness `green_paused_units`:
  inactive/inactive before, active/active after, rc 0. Harness `stop_unreadable_paused`: rc 2
  "refused", no ledger row, and the paused units end active. The arm drivers stop `wq-forge` and then
  run `forge_loop.sh` outside its cgroup, with `trap 'systemctl start wq-forge' EXIT`
  (`vps/c11_run.sh:29-33`).
- **F4. `--force` now kills live children.**
  - Harness `force_skips_busy`: there is no busy call, and stop is issued. The help text at `:619` is
    unchanged.
  - A SIGTERM that lands after `submit.py:330` writes `stage: reserved` and before `record()` leaves a
    row with no `http`. `record_adjudication.pending()` (`:32-35`) adjudicates only `http` 200 or 201,
    so it never picks that row up.

**MINOR, or not armed on today's target.**
- **F5.** `:385` treats any state other than `active` as stopped (harness: `deactivating` and
  `activating` let rsync run, rc 0). The rc of `systemctl stop` is ignored (`:383`).
- **F6.** The ledger's version comes from a second walk and a second closure import (`:470`), not from
  the manifest that was shipped. A no-op push is logged as `deployed` (`:515-517`).
- **F7. The stage leaks.**
  - On the drift refusal: `return` inside a `try` that has no `finally` (`:532-534`). Harness:
    leaked=1.
  - When `snapshot` raises (`:540`, outside any try).
  - **The test suite leaks one 5.4 MB stage per run.** `test_what_ships_is_exactly_what_was_hashed`
    takes that path. Measured: the count of `wq-deploy-*` went from 25 to 26 in one run. 22 others are
    sitting in `$TMPDIR`.
- **F8.** There is no `--checksum` (`:559`), and `copy2` keeps mtimes (`:443`). **Not armed:** 0 of the
  327 target files with the same size and mtime differ in content.
- **F9.** `:311` `isdir` follows symlinks. **Not armed:** `ls -laR` of forge, tools, harness13 and
  harness on the target shows 0 symlinks, and no plan path or ancestor is a non-directory.
- **F10.** When `start_units` raises inside `_undo`, that is caught at `:570`, and the rollback runs a
  second time (harness `red_start_timeout`).
- **F11. BUSY (`:205`) does not see `recover_harvest.py`, `harvest_loop.sh`, `record_adjudication.py`,
  `mint_link.py`, `*_run.sh` or `pytest forge/tests`** (regex run). It does see `forge/harvest.py` and
  `recover_orphans.py`. The harm is dormant: `recovered.jsonl` was last written 2026-08-18 17:37:49
  (stat). `recover_harvest.py:35-46` does key `done` on `parent_url`, and `:119-121` writes one row per
  child (read on the target).
- **F12. Only 2 units are stopped. The docstring's claim at `:493-494` overstates.** For today's push,
  a static recursive import scan of the timer and daemon entry points (`mint_link`, `watchdog`,
  `auto_cycle`, `health_report`, `deadman`, `sender`, `auth_daemon`) found one link into the changed
  or new files: `health_report.py:187` imports the **new** `tools/auth_backoff.py` lazily, inside
  try/except. `wq-health` "does not post" (unit description). `wq-forge-tests` runs `forge/tests` at
  10:30. The scan cannot see dynamic imports.
- **F13.** The probe and the snapshot run before the stop (`:521`, `:540` < `:554`). No target writer
  to a plan path has been identified (third pass, *destroy*). I did not re-derive this.
- **F14. The smoke never loads `mint_link` or `layered_sim`** (measured locally in a fresh interpreter).
  `runner.py:527-529` returns 2 before importing `layered_sim`. `forge_loop.sh:38-44` sends import
  failures to `2>/dev/null` and logs them as "auth dead". **Not armed today:** both files are
  byte-identical on the target (hashed).
- **F15. The tests.** `nonet` replaces `stop_units` and `start_units` (test `:209-210`), and the drift
  test fakes `_staged_matches` (`:377`). **New: the 12:18 rewrite deleted the only BADPARENT test.** grep
  finds `BADPARENT` in 0 test files, so item 2 now has no test at all.
- **F16.** There is no deploy lock. The failed-rollback message (`:602-603`) does not persist
  `to_delete`, which can be rebuilt as the plan paths absent from the `.tgz`.
- **F17.** A straggler on the target after a Ctrl-C (N3) is still SUSPECTED and unchanged.
- **F18.** After an exit 4 with no manifest, `runner.pipeline_version()` falls back to
  `<full version>+untracked` (`runner.py:83-95`). That affects D14 attribution only.

## Dropped or reduced

- *regression*: "subdirectory modes follow the umask". **Dropped as a defect.** It was not reproduced,
  the umask here is 022, and the target's directories are 755.
- *destroy* (h): "wq-auth keeps old `auth_daemon.py` after a green deploy". **Inert for this push.**
  `auth_daemon.py` is byte-identical on the target.
- *regression* and *assume*: "timers import a half-shipped tree". **Reduced to the one measured link**
  (F12).
- *assume*: "a restart discards `sleep until`". **Carried as MINOR.** It is read from
  `forge_loop.sh:48` (`sleep 300` in-process). The quota-exhausted interaction was not verified.
- *assume*: "the 3-second check sees only a bash fork". **Kept as F14, and not armed today.**

## Target state at 12:40 (read-only)

- `wq-forge` and `wq-harvest` are both `active`.
- `forge/runner.py --live` (pid 3248119) is in flight, so push would refuse right now.
- No arm driver is running.
- `wq-cycle.service` is `activating`.
- There is no `DEPLOYED.json` and no `.deploy/`.
- `forge.jsonl` holds 121,722,274 bytes, last written 12:38:57.

## VERDICT (fourth pass)

**NO. The two stated conditions (a real terminal, and no forge process) are not enough.**
- Under them, F1 and F2 can still end with both units stopped, with an exit code that says
  `rolled_back` or nothing at all, and no VPS monitor watches `wq-forge`.
- F3 restarts any unit that someone else paused.
- An idle moment caught by chance leaves the ~1 s race between the second BUSY check (`:550`) and
  the stop (`:554`) (SUSPECTED).

**The shortest ordered list to YES**, for one attended push of `47db4007`:
1. **Before.**
   - `pgrep -fa '_run\.sh'` returns nothing.
   - Nobody else has paused either unit.
   - The clock is not between 10:25 and 10:45 (`wq-forge-tests`).
   - `--force` is not used.
2. **Idle at a round boundary, not by chance.** Touch `state/STOP_FORGE`, wait until no `forge/*.py`
   remains, then `systemctl stop wq-forge` and `rm -f state/STOP_FORGE`. This is the
   `vps/c11_run.sh:24-30` sequence.
3. **Run `python3 tools/deploy.py push` in a terminal that stays open.** Do not interrupt it after
   the line `units stopped`.
4. **After, whatever the exit code, run `systemctl is-active wq-forge wq-harvest`.**
   - The smoke was green, or the output says `rollback: snapshot restored`, and the units are not
      active: start them.
   - The output says `ROLLBACK FAILED`: restore from the printed `.tgz`, remove the 48 new paths,
      and only then start anything.
5. **Keep `.deploy/pre-*.tgz`.**

**Before a second push, or any push nobody watches, these must land in code.** Each is small.
- F1 and F2: every path that called `stop_units` must end in a `start_units` whose verdict sets the
  exit code, with `:586-587` inside the guard.
- F10: catch a failed start inside `_undo`, so the rollback cannot run twice.
- Item 4: SIGTERM and SIGHUP handlers that raise into the existing `except` path.
- F3 and F5: read the prior unit state and restart only the units that were active; count only
  `inactive` and `failed` as stopped.
- F15: restore a BADPARENT test that runs the real probe program.

**Data-loss risk, stated plainly.**
- **The journal** (`state/layered/runs/forge.jsonl`): **no path found.**
  - No plan destination lies under `state/`, and rsync runs without `--delete`.
  - The rollback's rm list holds only the 48 plan paths that are absent on the target.
  - The snapshot writes only under `.deploy/`.
  - The dry planner returns before it opens the journal (`layered_sim.py:616-627`; the open is at
    `:642`).
  - The indirect risks are SUSPECTED only. The `wq-harvest` stop can SIGTERM `recover_harvest.py`,
    which writes `recovered.jsonl`, not the journal, and has been dormant since 2026-08-18. The ~1 s
    race can kill a runner that has just started. Step 2 removes the race.
- **The code tree:** **12 files are overwritten and 48 are added.** The other 491 are byte-identical.
  - After a green push, the target's versions of those 12 exist only in the `.tgz`. 9 of them contain
    target-only lines. I spot-checked 5 of the 9, and each of those lines is an older form of a line
    that exists, extended, locally. This is not a full semantic check.
  - Every measured mechanism that would destroy bytes with no copy is closed or not armed today: D2
    (demonstrated refusal), a regular-file parent (0), a symlinked parent (0), and a quick-check skip
    (0 of 327).
  - Files outside the plan are never touched.
  - A failed rollback leaves a mixed tree, and every byte is still in the `.tgz`.

---

# Fifth pass (2026-09-23)

Adjudicator, fifth pass. Three auditors reported: **regression**, **destroy** and **assume**. I kept a
defect only after I had reproduced it myself, using one of these means:

- reading the line in the pinned file;
- my own harness (scratchpad `adj5/h.py`). It runs the real `push()` in a child process, one case per
  process, and records the real exit code. It fakes only `_remote`, rsync, `loop_closure` and
  `time.sleep`. The real `_push`, `quiesce`, `start_units`, `units_state`, `other_operator_busy`,
  `rollback`, `write_manifest`, `run_smoke`, `_undo` and the signal handlers all run. 23 cases;
  `wq-deploy-*` stage count was 26 before and 26 after;
- `adj5/hup2.py`: a fresh interpreter on a pty (so stdout is a line-buffered tty, as in a real
  terminal), with the pty master closed while the fake rsync blocks;
- the real `quiesce` shell string, run locally against stub `pgrep` and `systemctl` (`adj5/q/`);
- the real existence-probe program, run on a scratch tree (`adj5/bp/`);
- read-only `ssh -n -o BatchMode=yes` between 13:15 and 13:22 (`systemctl is-active/show`, `ls`,
  `stat`, `pgrep`, `ps`, `cat`). Disclosure: one call piped into `head` and used `$(pgrep …)` inside
  `ps`. Both are read-only but outside the literal list.

Nothing was written on the VPS, nothing was simulated and nothing was fixed.

**Pinned.** `tools/deploy.py` is sha256 `398706c5…` (679 lines, mtime 12:52:07), re-hashed at the
end. `tools/tests/test_deploy.py` is `45b9548f…` (44 tests; `pytest -q`: 44 passed). Every line number
below refers to `398706c5`. If the file changes, this verdict lapses.

## Contradictions settled

| claim | settled |
|---|---|
| SIGHUP from a closed terminal skips the rollback (*regression*, *assume*) | **Reproduced, with a condition attached.** My first try forked the child from a parent whose stdout was a pipe. The child inherited a block-buffered `sys.stdout`, so it rolled back and restarted. With a fresh interpreter on the pty (`hup2.py`) the result was: `OSError: [Errno 5]` with context `_Signalled('signal 1')`, exit 120, order ending `…,quiesce,is_active,rsync`, tree PARTIAL, units inactive/inactive, no ledger row. So the failure needs stdout to be a tty. A real terminal is exactly that case. |
| *destroy* ranks the quiesce-exception path BLOCKER; the others rank it SERIOUS | **SERIOUS**, by the fourth pass's standard. It is demonstrated. It loses no data. When someone is watching, it shows up as a traceback or a non-zero exit. The exception is the orphan-waiter sub-case (S1), which is SUSPECTED and would be silent. |
| "exit 130" vs "rc −2" | These are the same result. An uncaught `KeyboardInterrupt`, including the `_Signalled` subclass, ends the process with SIGINT, which the shell reports as 130 (`h.py` cases). |
| *assume*: "inactive left by an earlier deploy reads as a pause" is SERIOUS | **Reduced to MINOR (G14).** It needs an earlier push to have left the units down. Every such path is loud except G2. |

## The fourth-pass items

- **F1 (write_manifest outside the try): LANDED** (`:604`). Harness `manifest_raises_before_mv`: rc 1,
  ledger `rolled_back`, tree OLD, units active/active. **The start after a green smoke (`:611`) is
  still unguarded**: see G3.
- **F2 (start results discarded): LANDED on every path that does not raise.** `start_fails_after_green`
  gives rc 5, ledger `units_down`, and "NOTHING IS RUNNING". On a path that raises, the result is lost
  (G3).
- **F3 (paused units restarted): LANDED for `inactive`** (`:580-581`). A unit that reads `activating`
  is still counted as not running (G8).
- **F5: NOT LANDED.** `:398` still counts anything other than `active` as stopped.
- **F10 (start raising re-enters the rollback): NOT LANDED.** `smoke_red_start_raises` ran
  `rollback,start,rollback,start`, then exited 1 with a traceback and no ledger row.
- **SIGTERM/SIGHUP handlers: PARTIAL.**
  - `sigterm_during_rsync`: rollback, start, is-active, re-raise. rc 130, tree OLD, units active/active,
    no ledger row.
  - A real closed terminal does not roll back (G2).
  - `quiesce` sits outside the guard (G1).
  - A second signal aborts the rollback (G6).
- **F15 (BADPARENT test): PARTIAL.** The test at `:419-423` exercises only the parser. The real probe
  program still raises `a parent of a shipped path is a regular file on the target: ['forge/sub']`
  (run on `adj5/bp/`), but no test runs that program.
- **The ~1 s race: LANDED for the runner.** `forge_loop.sh:28-31` consumes STOP_FORGE at the top of a
  round, before `refresh_cells` or the runner can start.
  - The real shell string, run against stubs: the QUIET branch polled until pgrep cleared, then made
    one call, `systemctl stop wq-forge wq-harvest`, removed STOP_FORGE and printed QUIET. The TIMEOUT
    branch removed STOP_FORGE, printed TIMEOUT and made no systemctl call.
  - BUSY does not match its own command text: Python `re.search` returns None. On the host,
    `pgrep -fa` with the BUSY pattern did not match my own ssh command, which contained that pattern.
    It matched only runner.py.
- **round_in_flight(): removed.** A grep finds no caller.

## What survives (re-verified)

**SERIOUS. Demonstrated locally. They cost production time, not data.**
- **G1. The quiesce stage is unguarded.** `stop_units` at `:586` is outside the only try (`:592-610`)
  that restarts the units, and `push()` writes nothing when `_push` raises. The stage prints nothing
  for up to 45 min.
  - `sigint_during_quiesce` and `sigterm_during_quiesce`: rc 130. No start, no ledger row, and the
    STOP_FORGE left behind on the target is not cleaned up.
  - `quiesce_local_timeout`: rc 1, traceback.
  - `isactive_raises_after_quiet`: rc 1, traceback. Units inactive/inactive, tree OLD, no ledger row.
    The units are certainly stopped here, because QUIET has already been printed.
  - `quiesce_ssh_drop` (rc 255, empty stdout): prints `STOP_FORGE removed, nothing stopped` and returns
    2 (not logged). Nothing it observed supports either half of that sentence (`:394-395` never looks
    for the TIMEOUT token).
  - What the remote shell does after the client is lost is **S1** below.
- **G2. SIGHUP from a closed terminal does not roll back.** `out()` is the first statement of the
  except block (`:606`) and raises EIO before `_undo` runs. See the table above. The end state is a
  PARTIAL tree, both units stopped, no ledger row, exit 120.
- **G3. On paths that end in an exception, the exit code and the ledger row are lost.** The docstring
  at `:525` says "a unit left down is exit 5 whatever else happened". Measured:
  - `sigterm_rsync_rollback_fails`: rc 130, not 3. Tree MIXED, units inactive/inactive.
  - `sigterm_rsync_start_fails`: rc 130, not 5. Units failed/failed.
  - `start_raises_after_green`: rc 1, the number of `rolled_back`, with a traceback. Tree NEW,
    DEPLOYED.json NEW, units inactive in the fake.
  - None of the three writes a ledger row. The first two do print `ROLLBACK FAILED` or
    `NOTHING IS RUNNING`.
- **G4. DEPLOYED.json is outside the rollback.** Moving `write_manifest` into the try created this.
  Neither `snapshot` nor `to_delete` covers the manifest. `manifest_raises_after_mv` (the remote `mv`
  completes, then the local ssh raises): rc 1, ledger `rolled_back`, tree OLD, **manifest NEW**. The
  next push of the same content (`manifest_raises_after_mv:second`) prints `nothing to do`, returns
  rc 0 and logs `deployed`. The premise (the remote side completes, the local side raises) was not
  demonstrated on the target.

**MINOR.**
- **G5.** F10, above.
- **G6. A second signal during `_undo` aborts it.** `double_sigterm_rollback`: the order ends
  `rsync,rollback`. Units inactive/inactive, rc 130, and nothing is printed to say the rollback did
  not finish.
- **G7. `other_operator_busy` (`:370-380`).**
  - **The wq-forge-tests branch cannot fire.** Host: `Type=oneshot`, `RemainAfterExit=no`. EX-ANTE
    (systemd.service(5)): a oneshot unit reads `activating` while ExecStart runs. I did not observe it
    during a run of this unit. `forge_tests_activating`: rc 0, deployed.
  - **It fails open.** `busy_ssh_fails` (rc 255): rc 0, deployed.
  - It is checked once, before a wait of up to 45 min.
  - There is still no deploy lock (grep finds only comments).
- **G8. `activating` before the push is never restarted.** `harvest_activating_before`: rc 0,
  `units running again: wq-forge`, wq-harvest left inactive. Not armed today: NRestarts=0 on both units.
- **G9. quiesce removes a STOP_FORGE it did not create** (`:390-392`, code read).
- **G10. QUIESCE_TIMEOUT (45 min) is shorter than the measured round tail** (POST-HOC; mechanism
  UNKNOWN). Re-derived from the 13:02 copy of `loop.log`, over pairs of consecutive N=300 rounds with
  no sleep, auth, STOP or quota marker between them and exit 0:
  - all such rounds: n=93, p50 24.2, p90 36.5, max 106.0 min, 5 of them over 45 min;
  - since 09-16: n=19, p50 26.6, max 81.8 min, 1 over 45 min.
  A timeout refuses safely (`quiesce_timeout`: rc 2, STOP_FORGE removed, `systemctl start` sent only to
  units that were already active).
- **G11.** When the units fail to start after a green smoke, nothing is rolled back: tree NEW, rc 5,
  loud. No smoke step runs `forge_loop.sh`.
- **G12.** The SIGHUP handler replaces nohup's SIG_IGN. `nohup_sighup` rolled back and restarted,
  rc 130. The `--force` help text (`:650`) is stale.
- **G13. The tests.**
  - `nonet` fakes `stop_units`, `start_units`, `units_state` and `other_operator_busy`.
  - The only quiesce test returns QUIET.
  - No test raises inside quiesce, or covers TIMEOUT, rc 255 or `activating`.
- **G14.** Units that a push itself left stopped read as a deliberate pause to the next push, which
  then leaves them down and exits 0 (`:581`, `:411-413`).
- **Carried, not re-derived:**
  - F11: BUSY misses `tools/record_adjudication.py`, `mint_link.py` and `recover_harvest.py`.
    wq-harvest is stopped mid-pass. It writes `recovered.jsonl` only (`recover_harvest.py:30,77`),
    last modified 2026-08-18 (stat).
  - F12: the timers run `tools/*.py` during the swap. `wq-cycle` runs `auto_cycle.py`, `wq-mint` runs
    `mint_link.py` and `wq-watch` runs `watchdog.py` (ExecStart read on the host).
  - F16: no deploy lock.
  - F18.
  - The rollback's `rm -f` does not remove directories that rsync created.

**SUSPECTED.**
- **S1. The orphan waiter.** EX-ANTE: OpenSSH signals a remote command only through a pty, and none
  is requested. If the client is lost during the wait (Ctrl-C, SIGTERM, the local 3,000 s timeout, a
  dropped connection, or the Mac sleeping, with no ServerAliveInterval set), the remote shell would
  keep polling. At the round boundary it would run `systemctl stop wq-forge wq-harvest`, after the push
  has already exited with 130, 1 or 2. Restart=always does not undo an explicit stop.
  - Not demonstrated: there is no local sshd, and the target is read-only.
  - To settle it, on a non-production host: `ssh h 'sleep 30; touch /tmp/m'`, kill -9 the client
    after 2 s, and look for `/tmp/m` at 35 s.
  - This is the only path found that could leave the loop stopped with nothing printed.
- **S2. A pgrep sample that falls in the millisecond gap between two loop steps.** It would end the
  quiesce mid-round, and the stop would catch a step that is just starting. Not measured on the host.
  What such a process has done by then is SPECULATION.
- **S3. The background probe is SIGTERMed when the loop exits.** EX-ANTE, from `ExitType=main` and
  `KillMode=control-group`, both read on the host at 13:15. The probe appends to
  `state/forge/corr.jsonl` (`forge/probe.py:23,101-105`), not to the journal.

## Dropped or reduced

- *assume*: "push() from a thread raises ValueError". **Dropped.** No caller does this, and it fails
  before any remote call.
- *destroy*: BLOCKER, **reduced to SERIOUS (G1)**. *assume*: SERIOUS, **reduced to MINOR (G14)**. See
  the table above.
- *regression*: "exit 1 is the same number as `rolled_back`". **Folded into G3.**
- The auditors' own out-of-list commands: *regression* ran `date`, `grep` and `systemctl --version`,
  and *assume* ran a 450-sample `systemctl is-active` loop. All of these are read-only. I did not use
  their output for any finding I kept, except the observation that other oneshot units read
  `activating`, which only supports G7.

## Target state at 13:15 (read-only)

- `wq-forge` and `wq-harvest` are both `active`. NRestarts=0 since 2026-09-10 06:36:11. Restart=always,
  RestartUSec=1min, KillMode=control-group, ExitType=main.
- `forge/runner.py --live` (pid 3252128) is in flight, so a push started now would wait in quiesce.
- No `*_run.sh` is running. `wq-forge-tests` is inactive; its last run was 10:30:13 to 10:31:14.
- There is no STOP_FORGE, no DEPLOYED.json and no `.deploy/`.
- `forge.jsonl` holds 122,951,729 bytes, last written 13:15:20.
- `recover_harvest.py` (pid 3235634, wq-harvest) is mid-pass.

## VERDICT (fifth pass)

**YES, for one attended push of `398706c5` from a real terminal, under the conditions below.
NO for a push nobody watches, a push run through an agent's Bash tool (its 2 or 10 min timeout lands
inside the quiesce wait), or a second push, until the fix list lands.** Whether to run it is Khoa's
decision.

What changed since the fourth pass: every outcome that involves no signal, no lost connection and no
ssh timeout now ends named and correct.

| outcome | rc | end state |
|---|---|---|
| green | 0 | units back |
| red | 1 | units back |
| rollback failed | 3 | named |
| units down | 5 | named |
| quiesce timeout | 2 | nothing swapped |

What remains either needs an event the conditions exclude, or shows up as a traceback or a non-zero
exit that step 4 checks for. S1 is the one path that could stay invisible, and step 4b checks for it.

**Conditions, in order:**
1. **Before.**
   - `pgrep -fa '_run\.sh'` returns nothing.
   - Nobody else will push or touch the VPS during the run.
   - The clock is not between 10:25 and 10:45 (G7).
   - `systemctl is-active wq-forge wq-harvest` prints `active` twice.
   - There is no `/opt/wq/state/STOP_FORGE`.
   - `--force` is not used.
2. **Run it in Terminal or iTerm, not under nohup, with the Mac kept awake**, on a stable network:
   `caffeinate -i python3 tools/deploy.py push`. Expect up to 45 min of silence after
   `units before the push`, and keep the window open.
3. **Never press Ctrl-C.** To abort during the wait, abort on the VPS instead:
   `pkill -f '[t]ouch state/STOP_FORGE'; rm -f /opt/wq/state/STOP_FORGE`. The bracket stops pkill from
   matching its own ssh command. The push then refuses and restarts only the units that were already
   active.
4. **After, whatever the exit code:**
   - (a) `systemctl is-active wq-forge wq-harvest` must print `active` twice, unless the output says
     `ROLLBACK FAILED`. If not, and the output shows a green smoke, `rollback: snapshot restored`, or
     a traceback before `shipped`, run `systemctl start wq-forge wq-harvest`.
   - (b) `pgrep -fa '[t]ouch state/STOP_FORGE'` must return nothing, and STOP_FORGE must be absent.
     If the waiter is there, kill it, remove the file, then repeat (a).
   - (c) If the exit was not 0, `/opt/wq/DEPLOYED.json` must not exist, because the target has none
     today (G4). If it exists, remove it.
   - (d) If the output says `ROLLBACK FAILED`, or the exit is 120, or there is a traceback after
     `shipped`: restore from the printed `.tgz`, remove the plan paths the `.tgz` does not hold, and
     only then start anything.
5. **Keep `.deploy/pre-*.tgz`.**

**Before an unattended or second push, these must land, in this order:**
1. **G1.** Guard `stop_units`. On any exception or any result other than QUIET: kill the remote waiter
   by a unique marker, remove STOP_FORGE only if this push created it (G9), re-read the units, start
   `was_active`, and return 5 if they are not back. Print TIMEOUT only when the token was seen.
2. **G2, G6, G12.** Mask SIGINT, SIGTERM and SIGHUP for the duration of `_undo`. Give it an `out()`
   that cannot raise. Keep SIG_IGN when that is the prior disposition.
3. **G3, G5.** Keep `_undo`'s return code and write the ledger on the exception paths. Guard `:611` and
   `units_state`.
4. **G4.** Put DEPLOYED.json in the snapshot, or in `to_delete` when it is absent.
5. **G7, G8, F16.** Count `activating` as running. Fail closed when the busy probe's ssh fails. Take a
   host-side flock and re-check before rsync.
6. **G13.** Tests that raise inside quiesce, cover TIMEOUT, rc 255 and `activating`, and run the real
   quiesce and probe programs.

**Journal risk** (`state/layered/runs/forge.jsonl`): **no path found.**
- No plan destination lies under `state/`, and rsync runs without `--delete`.
- The rollback's rm list holds only plan paths.
- The smoke planner is a dry run.
- quiesce waits out every `forge/*.py`, which covers the runner, harvest, submit and recover_orphans.
- `wq-harvest` writes `recovered.jsonl`, not the journal.
- Indirect risk: S2 only, SUSPECTED.

**Code-tree risk:**
- Every overwritten byte is recoverable on every demonstrated path. The snapshot is verified
  member-for-member before the stop, and the PARTIAL (G2) and MIXED (G6, rollback failed) trees keep
  every original in the `.tgz`.
- The identity can lie (G4). Condition 4c excludes that.
- I did not re-measure how many files this push overwrites and adds. The fourth pass's 12 and 48 were
  measured on the 12:41 content.
