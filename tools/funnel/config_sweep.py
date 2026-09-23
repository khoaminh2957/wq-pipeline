#!/usr/bin/env python3
"""config_sweep.py — STAGE-1 config generator (ALPHA_PIPELINE v7 funnel).

From ONE root single-field alpha (1 field / 1 dataset, fixed region+universe+delay),
emit DEFAULT_N (=180) UNIQUE valid FASTEXPR targets that keep (region,universe,delay) fixed
and vary neutralization x truncation x decay x pasteurization x unitHandling x
nanHandling x the single-field transform grammar. Deterministic given a seed.
Output validates through tools/validate_targets.py with 0 errors.

Signature discipline (Khoa 2026-07-16): every emitted operator call matches the FULL
documented signature in OPERATORS.md; enum-valued params are swept:
  ts_quantile(x,d,driver=)  -> gaussian/uniform/cauchy   (Khoa fix — PRESERVE)
  quantile(x,driver=)       -> gaussian/cauchy           (sigma bỏ: affine dup; uniform bỏ: ≡ rank)
  winsorize(x,std=)         -> std 3/4/5 (chỉ dưới outer shape-sensitive)
SEMANTIC-DEDUP (Khoa audit 2026-07-16): pool chỉ giữ công thức KHÁC NHAU về portfolio —
đã loại normalize/reverse(rank)/rank(winsorize)/market-group/monotone-inner-dưới-rank
(chi tiết tại khối OUTER + build_pool). Setting enums (pasteurization, unitHandling,
nanHandling, neutralization-by-region) derive từ fetched/rc/settings_options.json (S10-16).

Usage:
  python3 tools/funnel/config_sweep.py --field mdl175_gainvariance120 --dataset model175 \
      --region CHN --universe TOP2000U --delay 0 --run cs_demo --seed 7

Writes state/funnel/<run>_stage1_targets.json (a list of DEFAULT_N=180 rows, or fewer if
the formula pool is smaller / --n overrides) and prints the path.
"""
from __future__ import annotations
import argparse, json, pathlib, random, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
OPS = {o["name"] for o in json.load(open(ROOT / "fetched/rc/operators.json"))}
_SO = json.load(open(ROOT / "fetched/rc/settings_options.json"))
_CH = _SO["actions"]["POST"]["settings"]["children"]
NEU = {r: [c["value"] for c in v]
       for r, v in _CH["neutralization"]["choices"]["instrumentType"]["EQUITY"]["region"].items()}
PAST = [c["value"] for c in _CH["pasteurization"]["choices"]]
UNIT = [c["value"] for c in _CH["unitHandling"]["choices"]]
NAN = [c["value"] for c in _CH["nanHandling"]["choices"]]

BF = 22                       # sparse-field backfill lookback
WINDOWS = [5, 10, 22, 63]
TRUNC = [0.0, 0.02, 0.05, 0.08, 0.1]
DECAY = [0, 4, 8, 16, 32]
WINS_STD = [3, 4, 5]          # winsorize std sweep (S10-18)
DRIVERS = ["gaussian", "uniform", "cauchy"]

# ---- single-field transform grammar -------------------------------------------------
# inner: (name, fn(x, w) -> expr, windowed?)  operating on the backfilled field x
INNER = [
    ("raw",     lambda x, w: x,                              False),
    ("delta",   lambda x, w: f"ts_delta({x},{w})",           True),
    ("tszs",    lambda x, w: f"ts_zscore({x},{w})",          True),
    ("tsrank",  lambda x, w: f"ts_rank({x},{w})",            True),
    ("tsmean",  lambda x, w: f"ts_mean({x},{w})",            True),
    ("tsstd",   lambda x, w: f"ts_std_dev({x},{w})",         True),
    ("tsscale", lambda x, w: f"ts_scale({x},{w})",           True),
    # ts_quantile(x, d, driver=...) — Learn docs: drivers gaussian (default), uniform, cauchy (Khoa fix 2026-07-16)
    ("tsquant_gauss",  lambda x, w: f'ts_quantile({x},{w},driver="gaussian")',  True),
    ("tsquant_unif",   lambda x, w: f'ts_quantile({x},{w},driver="uniform")',   True),
    ("tsquant_cauchy", lambda x, w: f'ts_quantile({x},{w},driver="cauchy")',    True),
    ("tsdecay", lambda x, w: f"ts_decay_linear({x},{w})",    True),
    ("spow",    lambda x, w: f"signed_power({x},0.5)",       False),
] + [
    (f"wins{s}", (lambda s: lambda x, w: f"winsorize({x},std={s})")(s), False)
    for s in WINS_STD
]
# outer cross-sectional wrapper: fn(inner_expr) -> formula
# SEMANTIC-DEDUP (Khoa audit 2026-07-16 — logic OPERATORS.md; mỗi outer phải ra PORTFOLIO KHÁC NHAU
# sau neutralize + scale-to-book, không chỉ khác chuỗi):
#   BỎ normalize/normstd   — khác zscore chỉ bởi affine scalar/ngày → CÙNG portfolio
#   BỎ reverse(rank(s))    — ≡ -rank(s); giữ MỘT sign-flip (negrank)
#   BỎ rank(winsorize(s))  — winsorize đơn điệu → rank gần nguyên (chỉ tie ở đuôi)
#   BỎ quantile sigma-sweep — sigma là scale param (affine) → CÙNG portfolio; dùng sigma mặc định
#   BỎ quantile driver=uniform — uniform-reshape của rank ≡ rank(s) (affine)
#   group_* dùng SECTOR    — market là 1 nhóm duy nhất → group_rank(s,market) ≡ rank(s)
OUTER = [
    ("rank",       lambda s: f"rank({s})"),
    ("zscore",     lambda s: f"zscore({s})"),
    ("negrank",    lambda s: f"-rank({s})"),                     # sign-flip duy nhất
    ("grprank",    lambda s: f"group_rank({s},sector)"),
    ("grpzs",      lambda s: f"group_zscore({s},sector)"),
    ("quant_gauss",  lambda s: f"quantile({s},driver=gaussian)"),  # reshape gaussian: khác rank về weight-shape
    ("quant_cauchy", lambda s: f"quantile({s},driver=cauchy)"),    # fat-tail: dồn weight vào extreme
]
# outer RANK-BASED chỉ nhìn THỨ TỰ cross-section → bất biến với inner đơn điệu per-day
RANK_BASED_OUTER = {"rank", "negrank", "grprank", "quant_gauss", "quant_cauchy"}
# inner đơn điệu (theo x hoặc theo ts_rank(x,d)): dưới outer rank-based → TRÙNG raw/tsrank
MONOTONE_INNER = {"spow", "tsquant_gauss", "tsquant_unif", "tsquant_cauchy"} | {f"wins{s}" for s in WINS_STD}


# FIELD-DESCRIPTION-aware prune (Khoa 2026-07-17): field-description logic belongs HERE,
# at generation, not just as a post-hoc warn. Read the root field's description nature and
# skip transforms that CONTRADICT it (meaningless per the description), like semantic-dedup
# does for portfolio-duplicates. Maps nature -> inner transform names to drop.
def _field_nature_of(field):
    try:
        import importlib, sys, pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        lc = importlib.import_module("logic_check")
        desc = (lc.FIELDS.get(field, {}) or {}).get("description", "")
        return lc.field_nature(desc.lower()) if desc else set()
    except Exception:
        return set()


# inner transforms that are MEANINGLESS on a field of the given nature (per its description)
_NATURE_DROP_INNER = {
    "CHANGE":     {"delta"},                       # already a change -> ts_delta double-differences
    "NORMALIZED": {"tszs", "tsrank"},              # already standardized -> re-normalizing is empty
    "BOUNDED01":  set(),                           # log/inverse handled by logic_check DANGEROUS
    "NONNEG":     set(),
    "LEVEL":      set(),
}


def build_pool(field):
    """Deterministic list of PORTFOLIO-DISTINCT, FIELD-DESCRIPTION-MEANINGFUL single-field formulas.

    Two prunes: (1) semantic-dedup — monotone inners only under shape-sensitive outers
    (rank-invariance, OPERATORS.md); (2) field-description — drop inners that contradict the
    root field's description nature (e.g. ts_delta on a 'change' field = double-differencing)."""
    nature = _field_nature_of(field)
    drop_inner = set().union(*(_NATURE_DROP_INNER.get(n, set()) for n in nature)) if nature else set()
    x = f"ts_backfill({field},{BF})"
    pool, seen = [], set()
    for iname, ifn, windowed in INNER:
        if iname in drop_inner:
            continue              # field-description-meaningless on this field — skip
        for w in (WINDOWS if windowed else [None]):
            inner = ifn(x, w)
            for oname, ofn in OUTER:
                if iname in MONOTONE_INNER and oname in RANK_BASED_OUTER:
                    continue          # semantic duplicate — loại
                f = ofn(inner)
                if f not in seen:
                    seen.add(f)
                    pool.append(f)
    return pool


DEFAULT_N = 180                 # Khoa 2026-07-17: 180/sweep (fills the ~80-90 concurrent ceiling; less idle time). pool=235 caps it.


def generate(root, seed, n=DEFAULT_N):
    """Return n unique target rows for the given root spec (deterministic on seed;
    rows[0:k] are identical for any n>=k, so a run can be topped up without re-simming)."""
    region, universe, delay = root["region"], root["universe"], root["delay"]
    run = root.get("run") or "sweep"    # S10-17: no KeyError when caller omits run
    neuts = NEU[region]
    pool = build_pool(root["field"])
    if len(pool) < n:
        # Description-aware prune (NORMALIZED/CHANGE) can shrink the pool below DEFAULT_N
        # (e.g. NORMALIZED -> 179, CHANGE+NORMALIZED -> 151). Emit the whole pruned pool
        # rather than aborting the sweep with zero targets.
        print(f"formula pool {len(pool)} < n={n}; emitting {len(pool)}", file=sys.stderr)
        n = len(pool)
    rng = random.Random(seed)
    rng.shuffle(pool)

    rows = []
    for idx in range(n):
        oid = f"{run}_s1_{idx:03d}"
        rows.append({
            "id": oid,
            "old_id": oid,
            "label": f"{run}_stage1",
            "formula": pool[idx],       # pool entries are unique -> rows are unique
            "settings": {
                "instrumentType": "EQUITY",
                "region": region,
                "universe": universe,
                "delay": delay,
                # neutralization cycles so EVERY legal value for the region appears;
                # the rest are independent deterministic draws (no lockstep correlation)
                "neutralization": neuts[idx % len(neuts)],
                "decay": rng.choice(DECAY),
                "truncation": rng.choice(TRUNC),
                "pasteurization": rng.choice(PAST),
                "unitHandling": rng.choice(UNIT),
                "nanHandling": rng.choice(NAN),
                "language": "FASTEXPR",
                "visualization": False,
            },
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--field", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--region", required=True)
    ap.add_argument("--universe", required=True)
    ap.add_argument("--delay", type=int, required=True)
    ap.add_argument("--base", default=None, help="root base transform (informational)")
    ap.add_argument("--run", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n", type=int, default=DEFAULT_N, help="variants to emit (Khoa default 180; pool 235 max)")
    ap.add_argument("--out-dir", default=str(ROOT / "state/funnel"))
    ap.add_argument("--no-validate", action="store_true")
    a = ap.parse_args()

    if a.region not in NEU:
        raise SystemExit(f"unknown region {a.region}")
    root = {"field": a.field, "dataset": a.dataset, "region": a.region,
            "universe": a.universe, "delay": a.delay, "run": a.run}
    rows = generate(root, a.seed, a.n)

    out_dir = pathlib.Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{a.run}_stage1_targets.json"
    json.dump(rows, open(out, "w"), indent=1)

    if not a.no_validate:
        r = subprocess.run([sys.executable, str(ROOT / "tools/validate_targets.py"), str(out)])
        if r.returncode != 0:
            raise SystemExit(f"validate_targets FAILED on {out}")
    print(str(out))


if __name__ == "__main__":
    main()
