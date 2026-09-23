# `vps/` — what the VPS actually runs

**The VPS is authoritative for everything in this directory.** These files are pulled FROM
`root@160.25.88.163:/opt/wq` (and `/etc/systemd/system`), not pushed to it. `/opt/wq` is not a git
repository, so until this directory existed the running miner, the auth daemon and every systemd
unit had no version history at all — 150 of 433 files on that box were untracked, including
`climb_loop.sh` itself.

## Why this is a separate directory and not an overwrite

`pipeline/climb_loop.sh` in this repo is a DIFFERENT file with different paths, and on 2026-08-16 it
had silently fallen three changes behind the box:

| | repo `pipeline/` | live VPS |
|---|---|---|
| submit cap | `--cap 1` | `--cap 4` |
| probe | `probe.py 30 900` | `probe.py 60 0` |
| fd hygiene | none | `exec 8>&-`, three `9>&-` |

A deploy from `pipeline/` would have regressed all three, including the submit cap on the
irreversible path. Keeping the live copies under their own name makes that drift visible instead of
latent.

## The bash lesson these files encode

**Editing `climb_loop.sh` while it runs changes nothing.** Bash parses a `while` compound command
once and executes it from memory, so an edit lands in the file and not in the running loop.
Measured on 2026-08-16: `probe.py 30 900` was still executing at 21:22, sixteen minutes after the
file said `probe.py 60 0`; the `--cap 1 → 4` edit was inert the same way, on the submit path.

The loop must be RESTARTED for any edit to take effect. Since `wq-climb.service` exists
(`Restart=always`, `RestartSec=300`, singleton-guarded by the loop's own flock), the way to do that
is `systemctl restart wq-climb` — and the right moment is between rounds or inside the correlation
probe, never mid-simulation.

Two more rules the same day earned:

* **Python is safe to swap, bash is not.** A `.py` file is read wholly at import, so a replacement
  takes effect at the next process. A running `bash` script is read incrementally and `scp`
  preserves the inode, so overwriting one in place can make it follow new bytes at a stale offset.
* **A lazy `import` inside a function binds at first CALL, not at process start**, so a Python swap
  can still hit a long-lived daemon mid-run.

## Contents

`climb_loop.sh` `probe.py` `auth_daemon.py` `harvest_loop.sh` `unblock.py` `mint_when_open.sh`
`arm_climb.sh`, plus every `wq-*` systemd unit as `systemd_<name>`.

Not here, deliberately: `.env` (credentials, mode 600), `state/` (runtime data), `venv/`.
