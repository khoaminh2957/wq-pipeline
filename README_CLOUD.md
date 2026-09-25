# frames-lab — working branch for a cloud session

Pushed 2026-09-25 from the MacBook dev tree (branch audit-bac0, commit 8a806c8 + uncommitted work) so a Claude Code
cloud session can continue the frame-library work. This branch is NOT the CI-published `main`.

## What is here

- `framelib/` — the frame library (100 candidate frames in `framelib/library/`), the field library, the filler, the
  loop modules (`framelib/loop/`), the round builders and read-outs (`framelib/experiments/`).
- `docs/frames/` — decisions F1–F14 (`00_decisions.md`), discovery, the audits, the pre-registrations (13a, 13, 13c,
  13d) and the results (20 round 1, 21 round 2, 22 the submitted-frame screen).
- `docs/evalharness/` — the evaluation-system decisions D1–D60 and audits.
- `forge/`, `tools/`, `vps/`, `harness*/`, `fingerprint.py`, `operators.py` — the pipeline code the rounds run on.
- `CLAUDE.md` — the operator's rules (RULE 0/1/2). Read it first.

## Data (not in git)

The data bundle is the GitHub release `frames-lab-data-20260925` of this repository:

    gh release download frames-lab-data-20260925 -p 'frames-lab-data-20260925.tar.gz'
    tar xzf frames-lab-data-20260925.tar.gz            # creates data/
    mkdir -p fetched/rc/fields && cp data/fetched/rc/field_labels.jsonl data/fetched/rc/operators.json fetched/rc/ \
        && cp data/fetched/rc/fields/USA_TOP3000_d1.jsonl fetched/rc/fields/
    export FRAMES_CANONICAL=$PWD/data/frames/canonical/rows_framed.jsonl

`data/frames/rounds/` holds every live round's journal and plan (R1B, R2, R3S, R3SB) plus `recovered.jsonl`, and
the R4 plan; `data/frames/submitted/` the 245 submitted alphas and their frames. The read-out scripts take these
paths as arguments (see each script's docstring).

## What a cloud session can and cannot do

- CAN: read, analyse, write code and tests, run `python3 -B -m pytest framelib/tests`, build plans offline.
- CANNOT: reach the VPS (`root@160.25.88.163`); its SSH key is not on GitHub and must not be. Every simulation,
  deploy and live round runs on the VPS (RULE 1) and is started from the MacBook. Live rounds already scheduled on the
  VPS: FRAMES-R4 at 2026-09-26 11:05 +07 (systemd timer `frames-r4`).
