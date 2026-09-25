"""Q-B read-out (docs/frames/13_preregistration.md §3.2, §7.1): is a frame's advantage stable on fresh fields?

Round-1 rows: arm a of FRAMES-R1B. Round-2 rows: own-role (arm a) rows of FRAMES-R2. Offline, read-only.

    python3 -B framelib/experiments/qb.py --r1 frames_r1b.jsonl --r1-plan frames_r1b.plan.json \
        --r2 frames_r2.jsonl --r2-plan frames_r2.plan.json [--recovered recovered.jsonl]

B1 (the one claim): Spearman rho of per-frame LOW_SHARPE pass rates, R1 vs R2, frames with >= 3 scored own-role rows
in both; permutation p (10,000); claim only if rho > 0 and p < 0.05.
B2: robust frames (top ceil(0.2 x eligible) in R1 by the lexicographic score, strictly above the R2 median score)
minus its permutation null (R2 scores shuffled across frames), one-sided.
B3: retained share of the top-quintile gap, (R2 top - R2 all) / (R1 top - R1 all), on the y08 rate and on mean
y_ratio, with a frame-bootstrap 95 % interval (10,000).
Printed first: B1 within frames whose own-role fills carry the ingredient (option3/option8/us_short_sale) in at least
half of them, and within the rest (doc 13 §3.2 "stratified report").
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import random
import re
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import analyse_round as AR   # noqa: E402

INGREDIENT = {"option3", "option8", "us_short_sale"}


def per_frame(journal, plan_path, recovered, arm, cat):
    plan = json.loads(pathlib.Path(plan_path).read_text())["constructions"]
    rows = AR._rows(recovered)
    rows.update(AR._rows(journal))
    out = collections.defaultdict(lambda: {"ls": [], "y08": [], "yr": [], "ing": []})
    for c in plan:
        m = c["meta"]
        if m.get("arm") != arm:
            continue
        r = rows.get(AR._key(c["formula"], c["settings"]))
        o = AR.outcome(r)
        if not o["scored"]:
            continue
        ch = {x.get("name"): x for x in (r.get("checks") or [])}
        try:
            yr = max(-2.5, min(2.5, float(r["sharpe"]) / float((ch.get("LOW_SHARPE") or {}).get("limit"))))
        except (TypeError, ValueError, ZeroDivisionError):
            yr = None
        toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", c["formula"]))
        f = out[m["frame_id"]]
        f["ls"].append(o["ls"])
        f["y08"].append(o["y08"])
        if yr is not None:
            f["yr"].append(yr)
        f["ing"].append(any(cat.get(t) in INGREDIENT for t in toks))
    return out


def score(f):
    """Lexicographic (LS rate, mean y_ratio) -- frame id breaks ties at the caller."""
    return (sum(f["ls"]) / len(f["ls"]), statistics.mean(f["yr"]) if f["yr"] else -9.0)


def _rank(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2.0 + 1
        i = j + 1
    return r


def spearman(x, y):
    rx, ry = _rank(x), _rank(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def perm_p(x, y, n=10000, seed=1):
    rho = spearman(x, y)
    if rho != rho:
        return rho, float("nan")
    rng = random.Random(seed)
    yy = list(y)
    ge = 0
    for _ in range(n):
        rng.shuffle(yy)
        if spearman(x, yy) >= rho:
            ge += 1
    return rho, (ge + 1) / (n + 1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--r1", required=True)
    ap.add_argument("--r1-plan", required=True)
    ap.add_argument("--r2", required=True)
    ap.add_argument("--r2-plan", required=True)
    ap.add_argument("--recovered", default="")
    ap.add_argument("--catalogue", default="fetched/rc/fields/USA_TOP3000_d1.jsonl")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    cat = {}
    for line in open(a.catalogue):
        j = json.loads(line)
        cat[j["id"]] = (j.get("dataset") or {}).get("id")
    f1 = per_frame(a.r1, a.r1_plan, a.recovered, "a", cat)
    f2 = per_frame(a.r2, a.r2_plan, a.recovered, "a", cat)
    elig = sorted(k for k in f1 if len(f1[k]["ls"]) >= 3 and len(f2.get(k, {"ls": []})["ls"]) >= 3)
    rep = {"eligible": len(elig)}

    def b1(keys):
        x = [sum(f1[k]["ls"]) / len(f1[k]["ls"]) for k in keys]
        y = [sum(f2[k]["ls"]) / len(f2[k]["ls"]) for k in keys]
        rho, p = perm_p(x, y) if len(keys) >= 4 else (float("nan"), float("nan"))
        return {"n": len(keys), "rho": rho, "p": p, "claim": bool(rho == rho and rho > 0 and p < 0.05),
                "frames_with_any_ls_r1": sum(1 for v in x if v > 0), "frames_with_any_ls_r2": sum(1 for v in y if v > 0)}
    ing = [k for k in elig if sum(f1[k]["ing"] + f2[k]["ing"]) * 2 >= len(f1[k]["ing"] + f2[k]["ing"])]
    rep["B1_strata_printed_first"] = {"ingredient": b1(ing), "rest": b1([k for k in elig if k not in ing])}
    rep["B1"] = b1(elig)
    # y08 version, printed, not claimed (doc 13 orders y08 first for the other questions)
    xy = [sum(f1[k]["y08"]) / len(f1[k]["y08"]) for k in elig]
    yy = [sum(f2[k]["y08"]) / len(f2[k]["y08"]) for k in elig]
    rep["B1_on_y08_printed"] = dict(zip(("rho", "p"), perm_p(xy, yy))) if len(elig) >= 4 else None
    # B2: robust frames
    s1 = {k: score(f1[k]) for k in elig}
    s2 = {k: score(f2[k]) for k in elig}
    top = sorted(elig, key=lambda k: (s1[k], k), reverse=True)[: math.ceil(0.2 * len(elig))] if elig else []
    med = sorted(s2.values())[len(s2) // 2] if s2 else None
    robust = [k for k in top if s2[k] > med]
    rng = random.Random(2)
    vals = list(s2.values())
    null = []
    for _ in range(10000):
        rng.shuffle(vals)
        perm = dict(zip(elig, vals))
        null.append(sum(1 for k in top if perm[k] > med))
    rep["B2"] = {"top": len(top), "robust": len(robust), "robust_ids": robust,
                 "null_mean": statistics.mean(null) if null else None,
                 "p_one_sided": (sum(1 for v in null if v >= len(robust)) + 1) / (len(null) + 1) if null else None}

    # B3: retained share of the top-quintile gap on y08 rate and mean y_ratio, frame bootstrap
    def gap(keys, fr, metric):
        if metric == "y08":
            vals = {k: sum(fr[k]["y08"]) / len(fr[k]["y08"]) for k in keys}
        else:
            vals = {k: statistics.mean(fr[k]["yr"]) if fr[k]["yr"] else 0.0 for k in keys}
        t = [k for k in keys if k in set(top)]
        return (statistics.mean(vals[k] for k in t) - statistics.mean(vals.values())) if t else float("nan")
    for metric in ("y08", "yr"):
        g1, g2 = gap(elig, f1, metric), gap(elig, f2, metric)
        share = g2 / g1 if g1 else float("nan")
        boots = []
        rng = random.Random(3)
        for _ in range(10000):          # doc 13 §3.2: frame bootstrap, 10,000
            sample = [rng.choice(elig) for _ in elig]
            b1g, b2g = gap(sample, f1, metric), gap(sample, f2, metric)
            if b1g and b1g == b1g and b2g == b2g:
                boots.append(b2g / b1g)
        boots.sort()
        ci = [boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots)) - 1]] if len(boots) > 40 else None
        rep["B3_" + metric] = {"r1_gap": g1, "r2_gap": g2, "retained_share": share, "ci95": ci}
    txt = json.dumps(rep, indent=1, default=str)
    if a.out:
        pathlib.Path(a.out).write_text(txt)
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
