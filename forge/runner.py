"""forge.runner — one forge ROUND: plan (cells → hypotheses → factory → pre-sim gates), then
simulate through the shared layered_sim dispatcher. RULE 1: `--live` only on the VPS.

Allocation (C10/C20, cells first): cells in weight order; within a cell every hypothesis gets a
block of ≤ `per_block` candidates (AlphaBench ~20); a cell takes ≤ `cell_cap` per round so one
round reaches several cells; the round stops at `n`. Duplicates against every journal and
non-novel signatures against the ACTIVE book are refused before anything is posted.
"""
from __future__ import annotations

import argparse
import collections
import fcntl
import hashlib
import json
import os
import pathlib
import random
import socket
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))          # `python forge/x.py` puts forge/ first, not the repo root
from forge import cells as C, compose as CP, ensemble as E, factory as F, gates as G, harvest as HV, hypotheses as H, signature as S, standard as ST  # noqa: E402
from forge import grammar as GR, labels as LB, typed as TY  # noqa: E402
from forge import allocate as AL  # noqa: E402

OUT = ROOT / "state/layered/runs/forge.jsonl"
PLANS = ROOT / "state/forge/plans"
QUARANTINE = "state/forge/quarantine.json"
JOURNAL_GLOB = "state/layered/runs/*.jsonl"


class Catalogues:
    """Field catalogues per (region, universe, delay), read once."""

    def __init__(self, root):
        self.root = pathlib.Path(root)
        self._idx = {}

    def index(self, region, universe, delay) -> dict:
        key = (region, universe, int(delay))
        if key not in self._idx:
            p = self.root / ("fetched/rc/fields/%s_%s_d%d.jsonl" % key)
            rows = []
            if p.exists():
                with open(p) as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            try:
                                rows.append(json.loads(line))
                            except ValueError:
                                continue
            self._idx[key] = F.catalogue_index(rows)
        return self._idx[key]


#: D58 (Khoa 2026-09-24 ~02:20; architecture round 4 S4): "the runner reads the journal with bounded memory".
#: MEASURED 2026-09-24 on the Mac journal copy (36,855 lines, 32,662 distinct alphas, 116 MB) and on a 2x synthetic
#: of it (every alpha id of the second copy suffixed), peak RSS of main() planning one dry round under the live
#: FORGE_ARGS ("--mode composites --order USA/d1,d1 --no-split --delays 1 --ab new", no --live, dispatch recorded),
#: read two ways (/usr/bin/time -l and the process's ru_maxrss; scratchpad d6_pipeline_principal_evidence/measure.sh):
#: BEFORE this reader 1,434 MB at 1x and 1,966 MB at 2x (+532 MB for 32,662 alphas, 17 KB each: round 4's slope);
#: AFTER it 905 MB and 903 MB, with the same 300 constructions (only meta.arm_by and the code's own pipeline_version
#: differ). A
#: `--mode gen` round: 989 MB and 961 MB (the journal holds 0 generated rows). Before, harvest.forge_rows parsed EVERY
#: line into one list (read_jsonl) before keeping the latest row per alpha (alone 577 MB at 1x, mem_parts.py). The label
#: file (fetched/rc/field_labels.jsonl, 127,642 labels) takes 563 MB of what remains and does not grow with the journal.
#: THE READ, two passes over one file. Pass 1 (journal_index) parses each line once and keeps only {alpha: byte
#: offset of its latest forge line}; pass 2 (journal_rows) seeks to each offset and yields one row at a time. The
#: sequence is exactly harvest.forge_rows(path).values() for a literal path -- the same rows (latest wins) in the
#: same order (a dict keeps an alpha where it first appeared) -- so allocate.pair_states, whose ties are
#: order-sensitive, reads what it read before. NOT COVERED: `--ensembles add|only` still loads the whole journal
#: (harvest.forge_rows; forge/ensemble.py reads it per cell); no FORGE_ARGS on file carries --ensembles (vps/forge.env,
#: read 2026-09-24). WHAT STILL GROWS with the journal, named: the index (one entry per
#: distinct alpha), gates.journal_ids (one id per simulated construction), and what a CONSUMER keeps -- pair_states
#: keeps each pair's Sharpe list, and the generator's state keeps EVERY GENERATED ROW whole (forge/gen/state.py: the
#: state is a pure function of the journal, design §3.2, and build() takes the rows). MEASURED (tracemalloc, the
#: test's ~3 KB row shape, gen_slope.py): a gen round's peak grows 151 B per added library row and 24.9 KB per added
#: generated row; the gen owner's own State.build over the same parsed rows keeps 24.5 KB per row (22.6 KB the parsed
#: row, 2.0 KB the state; gen_slope2.py), so this reader adds about 0.4 KB. A real journal row parses to 15.0 KB
#: (rowmem.py, 3,000 rows). How many generated rows a day brings is UNMEASURED (none has run); at the median whole day
#: of 3,197 scored and D53's half, SPECULATION, about 1,600. That growth is D58 x design §3.2, not this reader's: bound
#: it and the state is no longer a function of every generated row (a window is the discounting §3.2 rejects). Routed
#: to the gen owner and Khoa. Append-only is assumed between the passes: the dispatcher, the file's only writer in a
#: round, runs after the planner (vps/forge_loop.sh, read).
FORGE_JOURNAL = "state/layered/runs/forge.jsonl"


def journal_index(path, see=None) -> dict:
    """D58 pass 1: {alpha: byte offset of its LATEST forge line}, in first-appearance order. A forge line is one
    harvest.forge_rows keeps (parsable, an alpha, meta.forge); a line that does not parse is skipped as there.
    `see(row)`, when given, is called on every forge line in file order. {} when the file does not exist."""
    out = {}
    path = pathlib.Path(path)
    if not path.exists():
        return out
    with open(path, "rb") as fh:
        off = 0
        for line in fh:
            at, off = off, off + len(line)
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("alpha") and (r.get("meta") or {}).get("forge"):
                out[r["alpha"]] = at
                if see is not None:
                    see(r)
    return out


def journal_rows(path, index=None):
    """D58 pass 2: harvest.forge_rows(path).values(), yielded one row at a time (above)."""
    path = pathlib.Path(path)
    index = journal_index(path) if index is None else index
    if not index:
        return
    with open(path, "rb") as fh:
        for off in index.values():
            fh.seek(off)
            yield json.loads(fh.readline())


def gen_state(root):
    """The pass-first generator's state (forge/gen/state.py) from the inputs forge.gen.state.load(root) reads --
    the forge journal, both submit logs, the cached PnL curves of the accepted POSTs and of generated harvest-passes
    -- with the journal read in D58's two passes and only the rows the state reads kept: every generated row, the
    rows of accepted POSTs (novelty.formula_of's fallback) and any row sharing a generated row's
    repair.formula_key (repair.existing_neighbours, D51). The Mac journal holds 32,662 alphas and 0 generated rows
    (counted 2026-09-24), so load()'s whole-journal dict is what D58 removes here. corr.jsonl is not read: state.py
    says why ("no rule ticked for this branch reads a PROD / SELF reading"). test_runner holds this equal to
    state.load(root) (sha and proposal) on a journal that exercises each kept kind."""
    from forge import submit as SUB
    from forge.gen import posterior as PO, repair as RP, state as GS
    root = pathlib.Path(root)
    history = SUB.posted_history(paths=(root / "state/forge/submitted.jsonl", root / "state/climb/submitted.jsonl"))
    posted = {h["alpha"] for h in history if h.get("alpha") and h.get("http") in (200, 201)}
    gen_keys = {}

    def see(r):
        if PO.is_generated(r):
            gen_keys[r["alpha"]] = RP.formula_key(r)
        else:
            gen_keys.pop(r["alpha"], None)
    path = root / FORGE_JOURNAL
    index = journal_index(path, see)
    keys = set(gen_keys.values())
    rows = {r["alpha"]: r for r in journal_rows(path, index)
            if PO.is_generated(r) or r["alpha"] in posted or RP.formula_key(r) in keys}
    curves = {}
    for a in sorted(posted | {a for a, r in rows.items() if PO.is_generated(r) and PO.harvest_pass(r)}):
        c = HV.cached_curve(a, root / "state/pnl_curves")
        if c:
            curves[a] = c
    return GS.build(rows, history, curves)


def novelty_index(root, catalogues: Catalogues) -> S.NoveltyIndex:
    """Signatures of the ACTIVE book (fetched/rc/active_book.json), catalogue-aware for USA/d1."""
    root = pathlib.Path(root)
    p = root / "fetched/rc/active_book.json"
    if not p.exists():
        return S.NoveltyIndex()
    usa = catalogues.index("USA", "TOP3000", 1)
    fd = {fid: m["dataset"] for fid, m in usa.items()} or None
    return S.NoveltyIndex.from_book(json.load(open(p)), field_datasets=fd)


#: The version of the code that produced a row, so D1 ("a pipeline VERSION receives the grade") and
#: D14 ("only the alphas that version produced") have a referent. Computed once per process.
#: WHICH ROWS CARRY IT (draw-3 pipeline MINOR 6; the old sentence said "every construction"): the
#: constructions plan() builds, through _construction(), and every construction main() dispatches,
#: a `--plan` round's included: main() calls stamp(), which OVERWRITES `pipeline_version` and
#: `run_config` with this process's values (D46, Khoa 2026-09-23 ~20:15; design stage 0c,
#: docs/evalharness/04_passfirst_design.md; code audit A6: setdefault would keep the wrong one).
#: Before that, main() dispatched a prebuilt plan exactly as written (vps/pow_run.sh, c11_run.sh, llm_formula_run.sh): forge/llm/formula.py writes no
#: stamp, and forge/offline/pow_pairs.py and c11_neut.py copy `meta` from a journal row, so a stamp in
#: their plans named the version that produced the BASE row, not the one that ran the round.
#: WHAT IS HASHED (architecture round 2, S1iii-NL): the bytes on disk, by the release engineer's own
#: `deploy.pipeline_version_of(root)` -- the fallback used to be the whole-tree hash over the PLAN keys,
#: a third id namespace that byte-identical code on /opt/wq could never match, and the manifest was
#: trusted over the bytes, so a hand-rsync after a deploy was stamped with a version that was not
#: running. On a deploy TARGET whose DEPLOYED.json carries a `hashes` map, pipeline_version_of hashes
#: exactly the in_pipeline files that manifest LISTS, re-read from disk (draw-3 release BLOCKER 1); a
#: file on the target that the manifest does not list never enters the id. deploy.surface_extras()
#: reports those files (`deploy.py status`), and D40 marks the ones the loop can reach (below).
#: The values a row can carry, and what each means to a scorer that pools by version:
#:   `<id>`                     DEPLOYED.json's `pipeline_version`, and the bytes of the files it lists agree.
#:   `<id>+MISMATCH:<on_disk>`  DEPLOYED.json says `<id>`, those bytes hash to `<on_disk>` (a hand edit of a
#:                              shipped file after the deploy).
#:   `<id>+unverified`          DEPLOYED.json says `<id>`; the bytes could not be hashed, or the D40 extras
#:                              could not be counted (deploy.loop_reachable_extras raised).
#:   `<on_disk>+untracked`      no usable manifest claim; `<on_disk>` is the bytes' own pipeline id.
#:   `unknown`                  no usable manifest claim, and the bytes could not be hashed or the D40
#:                              extras could not be counted (one except clause covers both calls).
#:   `+EXTRAS:<n>` suffixed to  D40 (Khoa 2026-09-23 ~17:20): deploy.loop_reachable_extras(root) named n > 0
#:   `<id>`, `<id>+MISMATCH:..` files the loop can reach that the manifest does not list. WHICH files count
#:   or `<on_disk>+untracked`   is that function's rule, not this file's. A deploy.py without the function
#:                              (one from before D40) adds nothing: the rule does not exist in that tree.
#:                              `+unverified` and `unknown` never carry it: the except clause that produces
#:                              them also zeroes the count (draw-4 pipeline 5(c)).
#: Only the bare `<id>` is a manifest the bytes confirm. The scorer forms cohorts through
#: forge/offline/benchmark.py cohort_of() and parse_cohort(), both gated by plain_stamp(): a '+'-suffixed
#: value or a marker word ('unknown', 'ambiguous') forms no cohort (read 2026-09-23; draw-4 pipeline 5(d):
#: this sentence used to say "by equality on this field (build_from, compare)"), so every suffixed value
#: keeps the row out of every version's cohort, `<id>`'s and `<on_disk>`'s alike.
#: draw-3 pipeline MINOR 3: `+MISMATCH` used to drop `<on_disk>`, which was stored nowhere, so two
#: different drifts from one manifest read as one label and such a row could never be re-attributed.
#: It is carried now.
#: draw-3 pipeline MINOR 4: the claim is DEPLOYED.json's `pipeline_version` ONLY. The old fallback to
#: `version` compared the WHOLE-TREE id with a pipeline id -- two namespaces that differ whenever a test
#: or CI file ships -- so a byte-identical tree with a pre-A10 manifest read `+MISMATCH` (the draw-3
#: adjudicator's replica: `e4726594f240aa07+MISMATCH`). A manifest without a `pipeline_version`, or with
#: one that is not a non-empty string (MINOR 5: `5` crashed the planner with TypeError; a JSON list, with
#: AttributeError), is treated as no claim at all: `<on_disk>+untracked`. On a SOURCE tree, so is one
#: nested too deeply to parse (draw3_fix pipeline 6: the adjudicator's `'['*100000 + ']'*100000` raised
#: RecursionError out of the planner). On a deploy TARGET the same file gives `unknown`, not that (draw-4
#: pipeline 4 / P4): deploy._target_manifest() reads DEPLOYED.json for its `hashes` map and catches only
#: OSError and ValueError, so deploy.pipeline_version_of() and deploy.loop_reachable_extras() both raise
#: RecursionError, which the except below takes as "the bytes could not be hashed". Re-measured 2026-09-23
#: with the real deploy.py on one set of shipped bytes: `unknown` in the target layout, `<on_disk>+untracked`
#: in the source layout. Neither crashes the planner.
_VERSION = None


def pipeline_version(root=None) -> str:
    """The deployed version id, cached for the life of the process."""
    global _VERSION
    if _VERSION is not None:
        return _VERSION
    base = pathlib.Path(root or ROOT)
    try:
        m = json.loads((base / "DEPLOYED.json").read_text())
        # the LOOP's identity, never the whole shipped tree's `version` (MINOR 4, above)
        claimed = m.get("pipeline_version") if isinstance(m, dict) else None
    except (OSError, ValueError, RecursionError):       # draw3_fix pipeline 6: too deep to parse is no claim
        claimed = None
    if not isinstance(claimed, str) or not claimed:     # MINOR 5: a claim we cannot compare is no claim
        claimed = None
    try:
        sys.path.insert(0, str(base / "tools"))
        import deploy as DP
        on_disk = DP.pipeline_version_of(base) or None
        extras = getattr(DP, "loop_reachable_extras", None)          # D40; a pre-D40 deploy.py has none
        n_extras = len(extras(base) or ()) if extras is not None else 0
    except Exception:  # noqa: BLE001 -- a version we cannot compute is named, never omitted
        on_disk, n_extras = None, 0
    if claimed is None:
        _VERSION = on_disk + "+untracked" if on_disk else "unknown"
    elif on_disk is None:
        _VERSION = claimed + "+unverified"
    else:
        _VERSION = claimed if on_disk == claimed else claimed + "+MISMATCH:" + on_disk
    if n_extras:
        _VERSION += "+EXTRAS:%d" % n_extras                         # D40
    return _VERSION


#: D30 (Khoa 2026-09-23 ~15:45; implementation note in docs/evalharness/00_agreements.md). The arguments
#: this runner received are hashed into a SECOND stamp, meta.run_config, beside meta.pipeline_version, and
#: a cohort is the pair. Second, not folded into pipeline_version, for the note's reason: benchmark's
#: live_days joins deploy-ledger rows to journal rows on pipeline_version. N and FORGE_ARGS reach the
#: runner as argv through vps/forge_loop.sh, from the wq-forge unit's Environment in /etc/systemd (read on
#: the VPS 2026-09-23: N=300, FORGE_ARGS "--mode composites --order USA/d1,d1 --no-split --delays 1 --ab
#: new"). deploy ships forge_loop.sh (it is in deploy.PLAN) but never writes /etc/systemd (draw-4 pipeline
#: 5(a): this sentence used to say deploy never touches forge_loop.sh), so before D30 a change to N or
#: FORGE_ARGS left every later row in the same cohort. D50 moves them into /opt/wq/forge.env; not built here.
#: Hashed: the PARSED namespace, defaults included, as sorted JSON (so `--cells=x` and `--cells x` agree).
#: A new option changes every run's hash; it arrives with an edit to this file, which moves
#: pipeline_version anyway. `root` is kept: it names the tree the planner reads (library, journals,
#: catalogues); its default is this file's absolute tree, so one command line hashes differently on two
#: hosts, and every row that reaches the journal is made on /opt/wq (RULE 1). The runner has no
#: output-path option (OUT and PLANS are constants). Left out, each with why:
RUN_CONFIG_EXCLUDED = {
    "seed": "forge_loop.sh passes a fresh --seed every round (SEED=$(date +%s)): were it hashed, every round "
            "would be a cohort of one",
    "plan": "the prebuilt plan file's PATH: one plan reached by two paths is one configuration. Its CONTENT "
            "is hashed instead (`plan_sha256`, beside `plan_given`), so two different experiment plans are "
            "two cohorts (D30 amendment, orchestrator decision recorded with D43-D46; before it, pow.json and "
            "c11.json rounds shared one run_config, draw-4 pipeline 6)",
}


def run_config(args, plan_bytes=None) -> str:
    """meta.run_config (D30): sha256, 16 hex, of the parsed arguments without RUN_CONFIG_EXCLUDED, as
    sorted JSON, plus `plan_given` and, for a `--plan` round, `plan_sha256` = sha256 of the plan file's
    bytes (D30 amendment). main() passes the bytes it parsed and dispatched, so the hash names what ran,
    not a second read of the file; without them the file is read here. A round without `--plan` hashes
    exactly the body it hashed before the amendment, so the live loop's run_config does not move."""
    cfg = {k: v for k, v in vars(args).items() if k not in RUN_CONFIG_EXCLUDED}
    cfg["plan_given"] = bool(getattr(args, "plan", ""))
    if cfg["plan_given"]:
        if plan_bytes is None:
            plan_bytes = pathlib.Path(args.plan).read_bytes()
        cfg["plan_sha256"] = hashlib.sha256(plan_bytes).hexdigest()
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:16]


#: meta.arm, D47 groundwork (Khoa 2026-09-23 ~21:00; the shared interface fixed for the parallel builders:
#: "the runner stamps the planning mode of every construction"). D47 randomises ROUNDS within each ET day
#: between the incumbent (`--mode composites`) and the branch, and tells them apart by this stamp. The
#: value is `--mode` for a planner round, and PLAN_FILE_ARM for a `--plan` round, whose constructions an
#: experiment script chose: `--mode` is parsed there but plans nothing, and its default ("composites") would
#: file an experiment's rows under the incumbent.
#: SET ONLY WHERE A ROW HAS NO ARM (setdefault), never overwritten: meta.arm already carries labels other
#: readers group by -- plan()'s `--ab` arms "current" / "new" / "typed" (forge/offline/ab_report.py,
#: rung_report.py) and the experiment plans' own arms (forge/llm/formula.py "llmformula"; c11_neut.py,
#: pow_pairs.py and tvr_pairs.py). The live FORGE_ARGS carry `--ab new` (read on the VPS 2026-09-23), so
#: every live construction already has an arm: overwriting would end the harness5 A/B read-out the loop runs
#: today, while setdefault leaves today's live rows unchanged. CONSEQUENCE, named for D47's owners: while
#: `--ab` is on, a reader looking for "composites" finds "current" / "new" instead. Which FORGE_ARGS the D47
#: incumbent runs with is D47 / D50's to settle, not this file's. For recover_orphans the arm is IDENTITY
#: (architecture round 3 S15: it does not join ROUND_KEYS).
#: EXCEPT IN A RANDOMISED ROUND (below): there the arm is the randomiser's draw and is OVERWRITTEN, the shared
#: interface's "stamps every construction with meta.arm (the arm)". A composites round planned under `--ab new`
#: therefore reads "composites", not "current" / "new", and forge/offline/ab_report.py (ARMS: current, typed, new,
#: llmformula, pow15, pow2; read 2026-09-24) no longer sees it; the split survives only in the plan copy's `by_arm`,
#: which plan() counts before main() stamps. Only a deploy that puts `--mode randomised` in forge.env makes such a
#: round (D50).
PLAN_FILE_ARM = "plan"

#: D47 / D53 / D54 / D60 (Khoa 2026-09-23 ~21:00, 2026-09-24 ~02:20) and the shared interface fixed for this
#: build: `--mode randomised` draws the arm of a ROUND from sha256(f"{et_day}:{seed}"), the digest read as one
#: integer: even -> "composites" (the incumbent, D47's arm A), odd -> "gen" (the branch), i.e. 50/50 (D53).
#: et_day is the ET quota day (forge.submit.quota_day: resets 00:00 America/New_York) in which the round is
#: planned; seed is the round's --seed (vps/forge_loop.sh: SEED=$(date +%s)). Nothing the round later sees enters
#: the draw, so the assignment is fixed before any row exists; plan["randomiser"] records (et_day, seed, arm), so
#: the plan copy re-derives it. Every construction of such a round is stamped meta.arm = the draw, meta.arm_by =
#: ARM_BY_RANDOMISER, meta.round = the seed. Every other round -- `--mode composites|gen|singles|both` and a
#: `--plan` round -- is stamped meta.arm_by = ARM_BY_EXPLICIT (OVERWRITTEN: a plan row copied from a randomised
#: journal row must not keep "randomiser") and carries no meta.round; D54/D60 keep such rounds out of the
#: comparison and count them.
RANDOMISED = "randomised"
RANDOMISED_ARMS = ("composites", "gen")
ARM_BY_RANDOMISER = "randomiser"
ARM_BY_EXPLICIT = "explicit"


def randomised_arm(et_day: str, seed: int) -> str:
    """The arm D53's 50/50 draw gives the round (et_day, seed) (above)."""
    return RANDOMISED_ARMS[int(hashlib.sha256(("%s:%s" % (et_day, seed)).encode()).hexdigest(), 16) % 2]


def randomise(seed: int, now=None) -> dict:
    """{"et_day", "seed", "arm"} for a `--mode randomised` round planned at `now` (default: the clock)."""
    from forge import submit as SUB
    day = SUB.quota_day(time.time() if now is None else now)
    return {"et_day": day, "seed": seed, "arm": randomised_arm(day, seed)}


def stamp(constructions, run_cfg, arm, round_seed=None) -> None:
    """Every construction main() dispatches carries THIS process's pipeline_version and run_config, and an arm.
    The two stamps are OVERWRITTEN, never setdefault (D46, Khoa 2026-09-23 ~20:15; design stage 0c; code
    audit A6): a `--plan` file built by forge/offline/pow_pairs.py or c11_neut.py carries the stamps of the
    journal row it copied. The arm is set only where the row has none (PLAN_FILE_ARM, above), unless the round
    was randomised: `round_seed` given means a `--mode randomised` round, whose arm, arm_by and round are
    overwritten; otherwise arm_by is ARM_BY_EXPLICIT and a copied `round` is dropped (RANDOMISED, above).
    OPEN (draw-4 pipeline 5(e)): meta.seed is not re-stamped. A `--plan` row keeps the seed its plan entry
    carries, and pow_pairs, c11_neut and tvr_pairs copy meta from a journal row, so that is the BASE row's
    round; forge/offline/ab_report.py groups rows into rounds by meta.seed. An arm those scripts copy from the
    base row is kept the same way."""
    version = pipeline_version()
    for c in constructions:
        c["meta"] = dict(c.get("meta") or {}, pipeline_version=version, run_config=run_cfg)
        if round_seed is None:
            c["meta"].setdefault("arm", arm)
            c["meta"]["arm_by"] = ARM_BY_EXPLICIT
            c["meta"].pop("round", None)
        else:
            c["meta"].update(arm=arm, arm_by=ARM_BY_RANDOMISER, round=round_seed)


#: D45 (Khoa 2026-09-23 ~20:15): a cohort's exposure comes from the run_config transitions the runner records.
#: The shared interface: one JSON row {"at": epoch, "pipeline_version", "run_config", "host"} appended when
#: the runner starts with a (pipeline_version, run_config) different from the last row for its host; the
#: scorer reads it for cohort exposure, the deploy ledger's readers never do.
#: ONLY A LIVE START IS RECORDED. A dry run journals nothing (tools/layered_sim.py _dispatch returns [] before
#: it opens the journal; EX-ANTE, read), so it exposes no cohort; and run_config hashes `live`, so the deploy
#: smoke's planner (tools/deploy.py SMOKE: the unit's N and FORGE_ARGS on /opt/wq, not live) would otherwise
#: append a (new version, smoke run_config) row on every push, between the loop's own rows -- architecture
#: round 3 X3, which asked for exactly this check once the writer existed.
RUN_CONFIG_LOG = ROOT / "state/forge/run_config_log.jsonl"


def record_run_config(pv, rc, path=None, host=None, now=None) -> bool:
    """Append the D45 transition row unless the last row for this host already names (pv, rc); True when a
    row was written. The read of the last row and the append happen under one exclusive flock on the log,
    so two runners starting together cannot both append or both skip. The row is one os.write of one whole
    line (a short write raises), put on a fresh line if a crash left the file without its final newline;
    lines that do not parse are skipped."""
    path = pathlib.Path(path or RUN_CONFIG_LOG)
    host = host or socket.gethostname()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        body = fh.read()
        last = None
        for line in body.splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("host") == host:
                last = r
        if last is not None and (last.get("pipeline_version"), last.get("run_config")) == (pv, rc):
            return False
        row = json.dumps({"at": time.time() if now is None else now, "pipeline_version": pv, "run_config": rc,
                          "host": host}) + "\n"
        data = (b"\n" if body and not body.endswith(b"\n") else b"") + row.encode()
        if os.write(fh.fileno(), data) != len(data):
            raise OSError("short write to %s" % path)
        os.fsync(fh.fileno())
    return True


def note_run_config(live, pv, rc, path=None) -> None:
    """main()'s D45 step: records a LIVE start only (above). A failure to record is printed, loudly, and never
    stops the round: the round's rows still carry both stamps, and D45 reads a cohort with no transition row
    as "exposure unknown", never as a guess."""
    if not live:
        return
    try:
        record_run_config(pv, rc, path)
    except Exception as exc:  # noqa: BLE001 -- the round runs; the missing exposure row is named instead
        print("!!! D45 RUN_CONFIG LOG NOT WRITTEN (%s: %s): cohort (%s, %s) has no exposure row for this start"
              % (type(exc).__name__, exc, pv, rc), flush=True)


def _construction(cand: dict, seed: int, recipe=None) -> dict:
    meta = dict(cand["meta"])
    formula = cand["formula"]
    recipe = recipe or {}
    if recipe.get("power"):
        formula = "signed_power(%s, %s)" % (formula, recipe["power"])   # tail concentration: returns lever
    if recipe.get("smooth"):
        formula = "ts_decay_linear(%s, %d)" % (formula, int(recipe["smooth"]))
    meta.update({"forge": 1, "cand": F.candidate_id(formula, cand["settings"]), "signature": cand["signature"]["key"],
                 "mechanism_key": cand["signature"]["mechanism_key"], "seed": seed,
                 "pipeline_version": pipeline_version()})
    if recipe.get("tag"):
        meta["recipe"] = recipe["tag"]
    return {"formula": formula, "settings": cand["settings"], "meta": meta}


def plan(root, n: int, seed: int, per_block: int = 20, cell_cap: int = 60, library_dir=None,
         split_delays: bool = True, ensembles: str = "off", mode: str = "composites", composites_dir=None,
         cells_filter=None, only=None, recipe=None, allocate: bool = True, posted_keys=None, delays=None, ab: str = "off",
         structure_gate: bool = True) -> dict:
    """Khoa 2026-09-04 (tick): every round is split half d0 / half d1 ("chia đều vòng"); a half that
    cannot fill hands its leftover to the other side so the round still reaches `n`.
    `ensembles`: "off" (single-leg hypotheses only), "add" (an ensemble block per cell that has ≥ 2
    measured legs, before the single-leg blocks), "only" (nothing but ensembles — the verification
    round Khoa ticked on 2026-09-04).
    `mode` (Khoa 2026-09-04 "1", the ratified standard): "composites" simulates only cross-family
    composites that pass the standard's hard gates — single-field hypotheses are LEGS, never alphas;
    "singles" is the pre-standard behaviour (measurement only); "both" runs composites first; "gen" is the
    pass-first generator (fill_gen below; design stage 4).
    `recipe` (Khoa 15:40 "thử nhiều cách … tới khi ra được pass đầu tiên"): plan-time overrides for
    ONE round — {"universe": {"GLB": "TOP3000"}, "neut": [...], "group": "country", "decay": [...],
    "truncation": 0.05, "smooth": 10, "tag": "R3"}; every row of the round carries meta.recipe."""
    root = pathlib.Path(root)
    lib = H.load_library(library_dir or root / "forge/hypotheses")
    lib_by_id = {h.id: h for h in lib}
    comps = []
    if mode in ("composites", "both"):
        comps = [c for c in H.load_composites(composites_dir or root / "forge/composites", lib) if ST.admissible(c)]
    cats = H.categories(lib)
    if mode == "composites":
        cats = {c for comp in comps for leg in comp.legs for c in lib_by_id[leg].categories()}
    if mode == "gen":                   # D20: no library; every category the pyramid still needs (cells.rank_cells)
        cats = None
    all_cells = C.targets(root, hypotheses=cats)
    cells = [c for c in all_cells if c.weight > 0]
    if cells_filter:                                   # "GLB/d1 Fundamental" or shell-safe "GLB/d1:Fundamental"
        want = {x.strip().replace(":", " ").replace("%20", " ") for x in cells_filter if x.strip()}
        cells = [c for c in cells if "%s/d%d %s" % (c.region, c.delay, c.category) in want]
    if delays:                                         # Khoa 2026-09-07 19:10 (tick): d1 only — d0's line is 2.69, best d0 row ever 1.74
        cells = [c for c in cells if c.delay in set(delays)]
    if only:                                           # hypothesis / composite ids to include
        keep = {x.strip() for x in only if x.strip()}
        comps = [c for c in comps if c.id in keep]
        lib = [h for h in lib if h.id in keep] if mode != "composites" else lib
    recipe = dict(recipe or {})
    if recipe.get("universe"):
        cells = [c._replace(universe=recipe["universe"].get(c.region, c.universe)) for c in cells]
    if recipe.get("group"):
        for h in lib:
            if "group" in h.params:
                h.params["group"] = [recipe["group"]]
    for obj in list(lib) + list(comps):
        if recipe.get("neut"):
            obj.settings["neutralization"] = list(recipe["neut"])
        if recipe.get("decay"):
            obj.settings["decay"] = [int(d) for d in recipe["decay"]]
        if recipe.get("truncation") is not None:
            obj.settings["truncation"] = float(recipe["truncation"])
    if recipe.get("order"):
        # Khoa 2026-09-04 21:30 (standing loop): USA/d1 first, then every d1, then the rest — the day's
        # passes all came from USA/d1 (bar 1.58); d0 cells (bar 2.69) produced none in 500+ sims.
        prefixes = [x.strip() for x in recipe["order"] if x.strip()]

        def rank(c):
            key = "%s/d%d" % (c.region, c.delay)
            for i, pfx in enumerate(prefixes):
                if key == pfx or (pfx.startswith("d") and key.endswith("/" + pfx)) or key.startswith(pfx + "/"):
                    return i
            return len(prefixes)
        cells.sort(key=lambda c: (rank(c), -c.weight))
    cat = Catalogues(root)
    gate = G.PreSimGate(novelty_index(root, cat), seen_ids=G.journal_ids([root / JOURNAL_GLOB]), budget=n)
    # STRUCTURAL PRE-SIM GATE (Khoa's tick 2026-09-07 22:10): forge.typed H1 (units), H2 (kinds),
    # H4 vector / density — measured on 9,896 simulated formulas: refuses ~22 % with 0 rows ≥ 1.58
    # and 0 platform passes among them. The quarterly-backfill rule is not part of it (refuted).
    labels_path = pathlib.Path(root) / "fetched/rc/field_labels.jsonl"
    struct_labels = LB.load(labels_path) if (structure_gate and labels_path.exists()) else None
    struct_refused = collections.Counter()

    def structurally_ok(cand) -> bool:
        if struct_labels is None:
            return True
        st = cand["settings"]
        v = TY.judge(cand["formula"], struct_labels, "%s/d%s" % (st.get("region"), st.get("delay")), structural=True)
        if v["ok"]:
            return True
        struct_refused[(v["hard"][0][:2] + (" vector" if "VECTOR" in v["hard"][0] else " density" if "sparse" in v["hard"][0] else ""))] += 1
        return False
    rng = random.Random(seed)
    constructions, blocks, taken, made_ids = [], [], collections.Counter(), set()
    active_taken = [taken]              # which per-cell counter _composite_block charges (an A/B arm swaps its own in)
    qpath = root / QUARANTINE
    dead = set(json.load(open(qpath))) if qpath.exists() else set()
    journal = HV.forge_rows(root / FORGE_JOURNAL) if ensembles != "off" else {}     # ensembles re-read it per cell
    states = {}
    if allocate and mode != "gen":                  # the composites allocator; the generator keeps its own rules (D36)
        if posted_keys is None:
            posted_keys = set()
            try:
                from forge import submit as SUB
                import submit_budget as SB
                posted_keys = {h["mechanism_key"] for h in SUB.posted_history(ledger=SB.LEDGER) if h.get("mechanism_key")}
            except Exception:  # noqa: BLE001 -- no ledger readable: nothing counts as harvested
                posted_keys = set()
        states = AL.pair_states(journal if ensembles != "off" else journal_rows(root / FORGE_JOURNAL), posted_keys)  # D58
    posted_legs = {}
    if allocate and mode in ("composites", "both"):
        try:
            by_comp = {c.id: c for c in comps}
            for r in HV.read_jsonl(root / "state/forge/submitted.jsonl"):
                if r.get("http") in (200, 201) and r.get("hypothesis") in by_comp:
                    posted_legs[r["alpha"]] = list(by_comp[r["hypothesis"]].legs)
        except Exception:  # noqa: BLE001
            posted_legs = {}

    def _composite_block(cell, comp, room, idx, fd, cls=None) -> int:
        """One composite block on one cell (gate, quarantine, dedup); returns constructions added."""
        cands = CP.expand(comp, cell, idx, lib_by_id, rng, max_candidates=10 ** 6, field_datasets=fd)
        if not cands:
            return 0
        kept = []
        for cand in cands:
            if len(kept) >= room:
                break
            if cand["id"] in made_ids:
                continue
            if HV.quarantine_key(comp.id, cell.region, cell.delay, cell.category, cand["meta"].get("field")) in dead:
                continue
            if not structurally_ok(cand):
                continue
            if gate.check(cand) == G.OK:
                kept.append(cand)
                made_ids.add(cand["id"])
        constructions.extend(_construction(c, seed, recipe) for c in kept)
        active_taken[0][cell] += len(kept)
        blocks.append({"cell": "%s/d%d %s" % (cell.region, cell.delay, cell.category), "weight": cell.weight,
                       "hypothesis": comp.id, "grid": len(cands), "kept": len(kept), "class": cls or "-"})
        return len(kept)

    def fill_allocated(budget, comp_list=None, cell_list=None, taken_counter=None, untried_block=None) -> int:
        """Composite blocks in allocator order over every cell: near-miss (40), passed (10), untried,
        active; harvested and dead pairs are never simulated again (forge/allocate.py).
        `comp_list` / `cell_list` restrict the composites and cells (the A/B arms of a round);
        `taken_counter` gives an arm its own per-cell cap so the arms can share a cell (paired)."""
        made = 0
        tk = taken if taken_counter is None else taken_counter
        active_taken[0] = tk
        cats_of = lambda comp: {c for leg in comp.legs for c in lib_by_id[leg].categories()}  # noqa: E731
        for cell, comp, block, cls in AL.order(cell_list or cells, comp_list if comp_list is not None else comps, states, per_block,
                                               categories_of=cats_of, posted_legs=posted_legs, untried_block=untried_block):
            if made >= budget:
                break
            room = min(block, cell_cap - tk[cell], budget - made)
            if room <= 0:
                continue
            idx = cat.index(cell.region, cell.universe, cell.delay)
            fd = {fid: m["dataset"] for fid, m in idx.items()} or None
            made += _composite_block(cell, comp, room, idx, fd, cls)
        return made

    def fill(cell_list, budget) -> int:
        made = 0
        for cell in cell_list:
            if made >= budget:
                break
            idx = cat.index(cell.region, cell.universe, cell.delay)
            if ensembles != "off":
                room = min(per_block, cell_cap - taken[cell], budget - made)
                fd = {fid: m["dataset"] for fid, m in idx.items()} or None
                kept = []
                for cand in E.expand(cell, journal, rng, max_candidates=10 ** 6, field_datasets=fd):
                    if len(kept) >= room:
                        break
                    if cand["id"] in made_ids or gate.check(cand) != G.OK:
                        continue
                    kept.append(cand)
                    made_ids.add(cand["id"])
                if kept:
                    constructions.extend(_construction(c, seed, recipe) for c in kept)
                    taken[cell] += len(kept)
                    made += len(kept)
                    blocks.append({"cell": "%s/d%d %s" % (cell.region, cell.delay, cell.category),
                                   "weight": cell.weight, "hypothesis": "ensemble", "grid": len(kept), "kept": len(kept)})
                if ensembles == "only":
                    continue
            if mode in ("composites", "both") and not allocate:
                fd = {fid: m["dataset"] for fid, m in idx.items()} or None
                for comp in comps:
                    room = min(per_block, cell_cap - taken[cell], budget - made)
                    if room <= 0:
                        break
                    made += _composite_block(cell, comp, room, idx, fd)
            if mode == "composites":
                continue
            for h in lib:
                room = min(per_block, cell_cap - taken[cell], budget - made)
                if room <= 0:
                    break
                # The whole grid, shuffled by the round's rng; the gate refuses duplicates and
                # non-novel signatures one by one until the block is full.
                cands = F.expand(h, cell, idx, rng, max_candidates=10 ** 6)
                if not cands:
                    continue
                kept = []
                for cand in cands:
                    if len(kept) >= room:
                        break
                    if cand["id"] in made_ids:          # taken by an earlier pass of this plan
                        continue
                    if HV.quarantine_key(h.id, cell.region, cell.delay, cell.category, cand["meta"].get("field")) in dead:
                        continue                        # the platform refused this field here, every time
                    if not structurally_ok(cand):
                        continue
                    if gate.check(cand) == G.OK:
                        kept.append(cand)
                        made_ids.add(cand["id"])
                constructions.extend(_construction(c, seed, recipe) for c in kept)
                taken[cell] += len(kept)
                made += len(kept)
                blocks.append({"cell": "%s/d%d %s" % (cell.region, cell.delay, cell.category),
                               "weight": cell.weight, "hypothesis": h.id, "grid": len(cands), "kept": len(kept)})
        return made

    def fill_typed(budget) -> int:
        """The TYPED arm (Khoa 2026-09-07 tick: A/B 50/50 per round): random-within-the-grammar
        constructions over the same cells, judged by forge.typed, through the same gate."""
        labels = LB.load(pathlib.Path(root) / "fetched/rc/field_labels.jsonl")
        made, taken_t = 0, collections.Counter()
        # PAIRED DESIGN: the typed half goes to the same cells as the current half, in the same
        # proportions, so the arms differ only in how the formulas were written. With no current
        # half (nothing allocatable) it walks the ordered cells in blocks of per_block.
        used = [c for c in cells if taken[c] > 0]
        if used:
            tot = sum(taken[c] for c in used)
            quota = {c: max(1, round(budget * taken[c] / tot)) for c in used}
            walk = used
        else:
            quota = {c: per_block for c in cells}
            walk = [c for _ in range(max(1, cell_cap // max(1, per_block))) for c in cells]
        for cell in walk:
            if made >= budget:
                break
            room = min(quota.get(cell, per_block) - taken_t[cell], cell_cap - taken_t[cell], budget - made)
            if room <= 0:
                continue
            idx = cat.index(cell.region, cell.universe, cell.delay)
            fd = {fid: m["dataset"] for fid, m in idx.items()} or None
            res = GR.expand(labels, cell, rng, max_candidates=room * 2, field_datasets=fd)
            kept = []
            for cand in res["candidates"]:
                if len(kept) >= room:
                    break
                if cand["id"] in made_ids:
                    continue
                if gate.check(cand) == G.OK:
                    kept.append(cand)
                    made_ids.add(cand["id"])
            if kept:
                constructions.extend(_construction(c, seed, recipe) for c in kept)
                taken_t[cell] += len(kept)
                made += len(kept)
            blocks.append({"cell": "%s/d%d %s" % (cell.region, cell.delay, cell.category), "weight": cell.weight,
                           "hypothesis": "typed", "grid": len(res["candidates"]), "kept": len(kept), "class": "TYPED",
                           "refused": res["refused"], "reasons": res.get("reasons", {})})
        return made

    gen_report = {}

    def gen_quarantined(cand) -> bool:
        """The quarantine step of the chain for a generated candidate: the composite chain's key under its
        gen:<family> hypothesis, and D36's (cell, field) key over EVERY field it names (harvest.row_fields;
        architecture round 3 m19: "charge every field"), which harvest.quarantine writes for generated rows."""
        m, st = cand["meta"], cand["settings"]
        if HV.quarantine_key(m.get("hypothesis"), st.get("region"), st.get("delay"), m.get("category"), m.get("field")) in dead:
            return True
        return any(HV.field_quarantine_key(st.get("region"), st.get("delay"), f) in dead for f in HV.row_fields(cand))

    def fill_gen(budget) -> int:
        """`--mode gen`, design stage 4 (docs/evalharness/04_passfirst_design.md §4.1): forge.gen.propose on the
        loop's state (gen_state above), handed every provable generated harvest-pass for its two D51 neighbours
        and asked for the D37 repairs by propose's own order, each candidate through the COMPOSITE chain, in
        _composite_block's order -- made_ids -> quarantine -> structurally_ok -> PreSimGate.check -- as `accept`,
        which propose calls last (§4.1: "the pre-sim chain must be the composite chain"; code audit Y23: the typed
        and ensemble arms skipped quarantine and the structure gate). The made_ids link cannot refuse here, EX-ANTE:
        a gen round plans nothing before fill_gen, and propose refuses an id in seen_ids or made this round before it
        calls accept (its `known`); it is kept so the chain is the composite one, and a mutant that drops it leaves
        test_runner green (2026-09-24). Before that chain, a candidate whose
        meta.gen_route is not one of propose.ROUTES is refused and counted: D54 reads that stamp, only "fresh"
        enters its estimand. propose reads `taken` and returns by_cell, its own charge per cell (neighbours and
        repairs included), which the blocks report; a gen round plans nothing else, so `taken` is not written back
        (§4.1's "charges the same taken counter" would have no reader). Only the recipe's tag reaches a generated
        construction: its power and smooth wrappers would add signed_power / ts_decay_linear after every check,
        and D35 keeps §2.3's signed_power exclusion; neut, decay, truncation and group act on library objects.
        WHICH ALPHAS ARE HANDED is the push-split tick forge/gen/repair.py leaves to Khoa (neighbours planned after a
        push carry the new version, and the alpha's own card never counts them). Until it is ticked every provable
        alpha of the state is handed, whatever its cohort -- D51's own words, "each generated alpha that clears every
        check" -- and an alpha that cannot be proven on its card shows in propose's `neighbour-short` count."""
        from forge.gen import propose as PR, repair as RP
        state = gen_state(root)
        labels = struct_labels if struct_labels is not None else (LB.load(labels_path) if labels_path.exists() else {})
        refused, fds = collections.Counter(), {}

        def field_datasets(region, universe, delay):
            key = (region, universe, int(delay))
            if key not in fds:
                fds[key] = {fid: m["dataset"] for fid, m in cat.index(*key).items()} or None
            return fds[key]

        def accept(cand) -> bool:
            if cand["meta"].get("gen_route") not in PR.ROUTES:
                refused["gen-route-invalid"] += 1
                return False
            if cand["id"] in made_ids:
                return False
            if gen_quarantined(cand):
                refused["quarantined"] += 1
                return False
            if not structurally_ok(cand):
                return False
            if gate.check(cand) != G.OK:
                return False
            made_ids.add(cand["id"])
            return True
        handed = [r for r in state.rows.values() if RP.provable(r)]
        res = PR.propose(state, labels, cells, budget, seed, field_datasets=field_datasets, handed=handed,
                         seen_ids=gate.seen, cell_cap=cell_cap, taken=taken, accept=accept)
        tag = {"tag": recipe["tag"]} if recipe.get("tag") else None
        constructions.extend(_construction(c, seed, tag) for c in res["candidates"])
        for cell, k in res["by_cell"].items():         # propose's charge; nothing is planned after fill_gen to read it
            blocks.append({"cell": "%s/d%d %s" % (cell.region, cell.delay, cell.category), "weight": cell.weight,
                           "hypothesis": "gen", "grid": k, "kept": k, "class": "GEN"})
        gen_report.update(gen_state=res["gen_state"], counts=dict(collections.Counter(res["counts"]) + refused),
                          by_route=res["by_route"], n_draws=res["n_draws"], n_floor=res["n_floor"], handed=len(handed))
        return len(res["candidates"])

    comps_current = [c for c in comps if getattr(c, "arm", "current") != "new"]
    comps_new = [c for c in comps if getattr(c, "arm", "current") == "new"]
    n_current = n // 2 if ab in ("typed", "new") else n
    made_alloc = fill_allocated(n_current, comps_current if ab == "new" else None) if (allocate and mode in ("composites", "both")) else 0
    made_typed = 0
    if mode == "gen":                   # the whole round; `--ab` splits the incumbent's composites, not this arm
        fill_gen(n)
        remaining = 0
    elif ab == "typed":
        for c in constructions:
            c["meta"].setdefault("arm", "current")
        made_typed = fill_typed(n - n_current)
        remaining = 0
    elif ab == "new":
        # harness5 round arm: the composites marked `arm: new`, on the cells the current half used
        # (paired, Q24) first, then the rest; tagged meta.arm = "new"
        for c in constructions:
            c["meta"].setdefault("arm", "current")
        used = [c for c in cells if taken[c] > 0]
        # a round arm also reaches the FULL USA/d1 cells (weight 0): a pass there is still a
        # submission under Q2, only the pyramid gain is nil (Khoa Q18: USA/d1 first)
        full_usa = [c for c in all_cells if c.weight <= 0 and c.region == "USA" and c.delay == 1 and c not in cells]
        if delays:
            full_usa = [c for c in full_usa if c.delay in set(delays)]
        before = len(constructions)
        # the new arm keeps its own per-cell cap (paired cells) and opens each untried pair with a
        # full block (per_block), not the exploration block of 10: the round IS its exploration
        made_typed = fill_allocated(n - n_current, comps_new, used + [c for c in cells if c not in used] + full_usa,
                                    taken_counter=collections.Counter(), untried_block=per_block)
        active_taken[0] = taken
        for c in constructions[before:]:
            c["meta"]["arm"] = "new"
        remaining = 0
    else:
        remaining = n - made_alloc
    if remaining > 0 and not (allocate and mode == "composites"):
        if split_delays:
            made0 = fill([c for c in cells if c.delay == 0], remaining // 2)
            made1 = fill([c for c in cells if c.delay == 1], remaining - remaining // 2)
            left = remaining - made0 - made1
            if left > 0:
                fill(cells, left)
        else:
            fill(cells, remaining)
    gen_key = {"gen": gen_report} if mode == "gen" else {}          # a composites plan file keeps its old keys
    return {"seed": seed, "n": n, "made_at": time.time(), "hypotheses": len(lib),
            "cells_considered": len(cells), "gate": dict(gate.counts), "blocks": blocks, "quarantined": len(dead),
            "ensembles": ensembles, "n_ensembles": sum(1 for c in constructions if c["meta"].get("ensemble")),
            "allocate": allocate, "pair_classes": AL.summary(states) if states else {},
            "ab": ab, "by_arm": dict(collections.Counter(c["meta"].get("arm", "-") for c in constructions)), "n_typed": made_typed,
            "structure_gate": struct_labels is not None, "structure_refused": dict(struct_refused),
            "typed_refused": sum(b.get("refused", 0) for b in blocks if b.get("class") == "TYPED"),
            "blocks_by_class": dict(collections.Counter(b.get("class", "-") for b in blocks)),
            "mode": mode, "composites": len(comps), "n_composites": sum(1 for c in constructions if c["meta"].get("composite")),
            "by_delay": {d: sum(1 for c in constructions if c["settings"]["delay"] == d) for d in (0, 1)},
            "constructions": constructions, **gen_key}


def summarize(p: dict) -> str:
    per_cell = collections.OrderedDict()
    for b in p["blocks"]:
        per_cell[b["cell"]] = per_cell.get(b["cell"], 0) + b["kept"]
    lines = ["forge plan seed %d [%s]: %d construction(s) (d0 %d / d1 %d; composites %d) from %d hypotheses, %d composites, "
             "%d reachable cell(s); gate %s"
             % (p["seed"], p.get("mode"), len(p["constructions"]), p.get("by_delay", {}).get(0, 0), p.get("by_delay", {}).get(1, 0),
                p.get("n_composites", 0), p["hypotheses"], p.get("composites", 0), p["cells_considered"], p["gate"])]
    if p.get("pair_classes"):
        lines.append("  allocator: pairs %s | blocks by class %s" % (p["pair_classes"], p.get("blocks_by_class")))
    if p.get("structure_gate"):
        lines.append("  structure gate: refused %s" % (p.get("structure_refused") or {}))
    if p.get("ab") and p.get("ab") != "off":
        lines.append("  A/B %s: by arm %s | typed judge refusals %s" % (p["ab"], p.get("by_arm"), p.get("typed_refused")))
    if p.get("randomiser"):
        lines.append("  randomiser: ET day %(et_day)s, seed %(seed)s -> arm %(arm)s (D47/D53)" % p["randomiser"])
    if p.get("gen"):
        g = p["gen"]
        lines.append("  gen: state %s | routes %s | draws %s (floor %s) | provable handed %s | counts %s"
                     % (g.get("gen_state"), g.get("by_route"), g.get("n_draws"), g.get("n_floor"), g.get("handed"),
                        g.get("counts")))
    for cell, k in per_cell.items():
        if k:
            lines.append("  %-28s %3d" % (cell, k))
    return "\n".join(lines)


def queue_kind(p: dict, last_count) -> str | None:
    """Which m13 to send for this plan, if any: loaded / exhausted / low / None."""
    made, asked = len(p["constructions"]), p["n"]
    if last_count is not None and last_count != p["hypotheses"]:
        return "loaded"
    if made == 0:
        return "exhausted"
    if made < asked / 2:
        return "low"
    return None


def notify_queue(p: dict, root) -> None:
    """m13 hypothesis-queue alert; failure to notify never touches the round. Khoa 2026-09-04
    (tick): forge notifications are OFF until asked — sending needs WQ_FORGE_NOTIFY=1."""
    try:
        marker = pathlib.Path(root) / "state/forge/library_count"
        last = int(marker.read_text()) if marker.exists() else None
        kind = queue_kind(p, last)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(p["hypotheses"]))
        if kind and os.environ.get("WQ_FORGE_NOTIFY") == "1":
            import msgcat as MC
            MC.send(MC.m13_hypothesis_queue(kind, p["hypotheses"], len(p["constructions"]), p["n"], p["cells_considered"]))
    except Exception as exc:  # noqa: BLE001
        print("m13 notify skipped (%s: %s)" % (type(exc).__name__, exc))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)  # S7-NL: `--li` is not `--live`
    ap.add_argument("-n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--live", action="store_true", help="actually spend simulations (VPS only, RULE 1)")
    ap.add_argument("--concurrency", type=int, default=9)
    ap.add_argument("--children", type=int, default=10)
    ap.add_argument("--per-block", type=int, default=20)
    ap.add_argument("--cell-cap", type=int, default=60)
    ap.add_argument("--ensembles", choices=("off", "add", "only"), default="off",
                    help="2-3-leg ensembles of measured legs per cell (forge/ensemble.py)")
    ap.add_argument("--mode", choices=("composites", "singles", "both", "gen", RANDOMISED), default="composites",
                    help="composites = only standard-admissible cross-family composites (default); singles = legs alone; "
                         "gen = the pass-first generator (forge/gen); randomised = composites or gen, drawn per round (D47/D53)")
    ap.add_argument("--cells", default="", help='comma list of cells to plan for, e.g. "GLB/d1 Fundamental,GLB/d1 Analyst"')
    ap.add_argument("--only", default="", help="comma list of hypothesis/composite ids to include")
    ap.add_argument("--universe", default="", help="REGION:UNIVERSE[,...] override, e.g. GLB:TOP3000")
    ap.add_argument("--neut", default="", help="comma list overriding neutralization for this round")
    ap.add_argument("--group", default="", help="group field for every leg this round, e.g. country")
    ap.add_argument("--decay", default="", help="comma list overriding decay for this round")
    ap.add_argument("--truncation", type=float, default=None)
    ap.add_argument("--smooth", type=int, default=0, help="wrap every formula in ts_decay_linear(., D)")
    ap.add_argument("--power", type=float, default=0, help="wrap every formula in signed_power(., P)")
    ap.add_argument("--tag", default="", help="recipe tag written to meta.recipe")
    ap.add_argument("--order", default="", help="cell priority prefixes, e.g. USA/d1,d1 (then by weight)")
    ap.add_argument("--no-split", action="store_true", help="no half-d0/half-d1 split: cells in priority order")
    ap.add_argument("--no-allocate", action="store_true", help="disable the journal-driven allocator (forge/allocate.py)")
    ap.add_argument("--delays", default="", help="comma list of delays to plan for, e.g. 1 (d0 cells are dropped)")
    ap.add_argument("--no-structure-gate", action="store_true", help="disable the forge.typed H1/H2/H4 pre-sim gate")
    ap.add_argument("--ab", choices=("off", "typed", "new"), default="off",
                    help="typed = half from the current planner, half from forge.grammar; new = half current composites, "
                         "half the composites marked `arm: new` (harness5 round arm)")
    ap.add_argument("--plan", default="", help="prebuilt plan JSON (constructions fixed by an experiment script); skips the planner")
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(argv)
    seed = a.seed if a.seed is not None else int(time.time())
    recipe = {"tag": a.tag or None, "smooth": a.smooth or None, "power": a.power or None, "truncation": a.truncation,
              "neut": a.neut.split(",") if a.neut else None, "decay": a.decay.split(",") if a.decay else None,
              "group": a.group or None,
              "universe": dict(x.split(":", 1) for x in a.universe.split(",") if ":" in x) if a.universe else None,
              "order": a.order.split(",") if a.order else None}
    plan_bytes, mode, drawn = None, a.mode, None
    if a.plan:
        plan_bytes = pathlib.Path(a.plan).read_bytes()     # the bytes dispatched are the bytes hashed (D30 amendment)
        p = json.loads(plan_bytes)
        p["seed"] = seed
    else:
        if a.mode == RANDOMISED:                           # D47/D53: the arm is drawn before anything is planned
            drawn = randomise(seed)
            mode = drawn["arm"]
        p = plan(a.root, a.n, seed, per_block=a.per_block, cell_cap=a.cell_cap, ensembles=a.ensembles, mode=mode,
                 cells_filter=a.cells.split(",") if a.cells else None, only=a.only.split(",") if a.only else None,
                 recipe=recipe, split_delays=not a.no_split, allocate=not a.no_allocate,
                 delays=[int(x) for x in a.delays.split(",") if x.strip()] or None, ab=a.ab, structure_gate=not a.no_structure_gate)
        if drawn:
            p["randomiser"] = drawn
    rc = run_config(a, plan_bytes)
    # before the plan file: recover_orphans reads the stamps there (D46)
    stamp(p.get("constructions") or [], rc, PLAN_FILE_ARM if a.plan else mode, seed if drawn else None)
    print("forge stamp: pipeline_version %s, run_config %s" % (pipeline_version(), rc), flush=True)  # draw3_fix pipeline 7
    note_run_config(a.live, pipeline_version(), rc)    # D45: a live start records its (pv, rc) transition
    PLANS.mkdir(parents=True, exist_ok=True)
    (PLANS / ("%d.json" % seed)).write_text(json.dumps(p))
    print(summarize(p), flush=True)
    notify_queue(p, a.root)
    if not p["constructions"]:
        print("nothing to simulate: the library is exhausted for every reachable cell (m13 case)")
        return 2
    import layered_sim as LS
    LS.run(len(p["constructions"]), seed=seed, out_path=OUT, live=a.live, concurrency=a.concurrency,
           children=a.children, batch=p["constructions"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
