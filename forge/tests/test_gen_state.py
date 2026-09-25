"""forge.gen.state: §3.2's state rule -- a pure function of the journal, the submit logs and the cached curves,
stamped as meta.gen_state; load() only reads."""
import copy
import json
import os
import random

from forge.gen import state as ST
from forge.tests.test_gen_productions import POSTS
from forge.tests.test_gen_spend import _curve, _walk, frow


def journal():
    rows = {}
    for i in range(3):
        rows["g%d" % i] = frow("g%d" % i, fam="famG", sharpe=1.9 - i)
        rows["g%d" % i]["meta"].update(gen_alpha="conf2", legs=[{"sig": "single", "ts": "ts_mean", "score": "rank",
                                                                 "windows": [["W_SHORT", 5]], "dataset": "dsG"}])
    rows["t0"] = frow("t0", fam="famT", sharpe=1.4)
    rows["t0"]["checks"] = [dict(c, result="FAIL" if c["name"] == "LOW_FITNESS" else "PASS") for c in rows["t0"]["checks"]]
    rows["lib"] = dict(frow("lib", sharpe=1.2), meta={"hypothesis": "usa_short_x_profitability", "forge": 1})
    return rows


HIST = [{"alpha": "kq", "http": 201, "formula": POSTS["kqVbg1xP"]}, {"alpha": "no", "http": 403, "formula": "rank(x)"}]


def test_the_sha_is_a_function_of_the_inputs_and_moves_with_what_the_loop_uses():
    a, b = ST.build(journal(), HIST), ST.build(list(journal().values()), HIST)
    assert a.sha == b.sha and len(a.sha) == 16
    moved = journal()
    moved["g0"]["sharpe"] = 0.2                                 # y 1 -> 0 on a generated row with levels
    assert ST.build(moved, HIST).sha != a.sha
    levelless = journal()
    levelless["t0"]["sharpe"] = 0.2                             # a row with no grammar level: no count moves
    assert ST.build(levelless, HIST).sha == a.sha
    lib = journal()
    lib["lib"]["sharpe"] = 0.1                                  # a library row the branch never reads
    assert ST.build(lib, HIST).sha == a.sha
    assert ST.build(journal(), HIST[:1] + [{"alpha": "new", "http": 200, "formula": "rank(y)"}]).sha != a.sha


def test_the_state_holds_posts_triggers_family_counts_and_pnl_stops():
    rng = random.Random(3)
    post = _walk(rng)
    curves = {"kq": _curve(post), "g0": _curve([p + 0.2 * rng.gauss(0, 1) for p in post])}
    st = ST.build(journal(), HIST, curves)
    assert st.accepted == ["kq"]                                # a 403 was refused, not submitted
    assert st.structures.complete and len(st.structures) == 1
    assert [r["alpha"] for r in st.triggers] == ["t0"]          # t0 fails only LOW_FITNESS
    assert st.stats[("famG", "USA/d1")]["sims"] == 3
    assert set(st.stopped) == {"famG"} and st.verdict("famG", "USA/d1") == ("PNL_STOP", 0)
    assert st.verdict("famNew", "USA/d1") == ("OPEN", 40)
    assert st.posterior.n_obs == 4 and len(st.families) == 4


def _snapshot(root):
    out = {}
    for d, dirs, files in os.walk(root):
        for f in files + dirs:
            p = os.path.join(d, f)
            st = os.stat(p)
            out[p] = (st.st_size, st.st_mtime_ns)
    return out


def test_load_reads_the_tree_and_writes_nothing(tmp_path):
    rows = journal()
    (tmp_path / "state/layered/runs").mkdir(parents=True)
    (tmp_path / "state/forge").mkdir(parents=True)
    (tmp_path / "state/climb").mkdir(parents=True)
    (tmp_path / "state/pnl_curves").mkdir(parents=True)
    with open(tmp_path / "state/layered/runs/forge.jsonl", "w") as fh:
        for r in rows.values():
            fh.write(json.dumps(dict(r, meta=dict(r["meta"], forge=1))) + "\n")
        fh.write("not json\n")
    with open(tmp_path / "state/forge/submitted.jsonl", "w") as fh:
        for h in HIST:
            fh.write(json.dumps(h) + "\n")
    rng = random.Random(3)
    post = _walk(rng)
    json.dump(_curve(post), open(tmp_path / "state/pnl_curves/kq.json", "w"))
    before = _snapshot(tmp_path)
    st = ST.load(tmp_path)
    assert _snapshot(tmp_path) == before
    assert st.accepted == ["kq"] and st.posterior.n_obs == 4
    ref = {a: dict(r, meta=dict(r["meta"], forge=1)) for a, r in copy.deepcopy(rows).items()}
    hist = [{"alpha": h["alpha"], "mechanism_key": None, "posted_at": 0, "http": h["http"], "formula": h["formula"]}
            for h in HIST]
    assert st.sha == ST.build(ref, hist, {"kq": _curve(post)}).sha


def test_each_part_of_the_summary_moves_the_sha_on_its_own():
    """Draw-5 gen N5 (T01, T02 and exec T03-T05): every input the docstring names as hashed moves the sha when
    it alone changes -- the PnL-stop evidence, the trigger queue, the registry, a family verdict, and the POSTs
    whose formula could not be read."""
    rng = random.Random(3)
    post = _walk(rng)
    noise = [rng.gauss(0, 1) for _ in post]

    def curves(k):
        return {"kq": _curve(post), "g0": _curve([p + k * e for p, e in zip(post, noise)])}
    a, b = ST.build(journal(), HIST, curves(0.2)), ST.build(journal(), HIST, curves(0.3))
    assert set(a.stopped) == set(b.stopped) == {"famG"} and a.stopped["famG"]["corr"] != b.stopped["famG"]["corr"]
    assert a.summary()["verdicts"] == b.summary()["verdicts"] and a.sha != b.sha                    # T01
    base = ST.build(journal(), HIST)
    two = journal()
    two["t0"]["checks"] = [dict(c, result="FAIL") if c["name"] == "CONCENTRATED_WEIGHT" else c for c in two["t0"]["checks"]]
    st2 = ST.build(two, HIST)
    assert st2.triggers == [] and st2.summary()["verdicts"] == base.summary()["verdicts"] and st2.sha != base.sha  # T02
    ren = journal()
    ren["g1"]["formula"] = "rank(y_g1)"                             # not a trigger: only the registry sees it
    st3 = ST.build(ren, HIST)
    assert st3.families.digest() != base.families.digest() and st3.sha != base.sha                 # T03
    dead, alive = journal(), journal()
    for i in range(40):
        for rows, sh in ((dead, 0.5), (alive, 1.1)):
            r = frow("v%d" % i, fam="famV", sharpe=sh, ladder=("PASS", 5))
            del r["formula"]                                        # no registry entry, no trigger
            rows["v%d" % i] = r
    sd, sa = ST.build(dead, HIST), ST.build(alive, HIST)
    assert sd.verdict("famV", "USA/d1") == ("DEAD", 0) and sa.verdict("famV", "USA/d1") == ("OPEN", None)
    assert sd.summary()["posterior"] == sa.summary()["posterior"] and sd.sha != sa.sha              # T04
    read = ST.build(journal(), [{"alpha": "gh", "http": 200, "formula": "rank(z)"}])
    unread = ST.build(journal(), [{"alpha": "gh", "http": 200}])
    assert read.accepted == unread.accepted == ["gh"] and unread.structures.missing == ["gh"]
    assert read.sha != unread.sha                                                                    # T05


def test_load_reads_member_and_post_curves_and_the_climb_log(tmp_path):
    """Draw-5 gen N5 (exec T06-T08): the PnL stop through load() needs the generated harvest-pass members' curves,
    the accepted POSTs' curves and both submit logs (a POST made by the climb loop is a POST)."""
    rows = journal()
    rows["hp"] = frow("hp", fam="famH", sharpe=1.9, passed=True)
    for d in ("state/layered/runs", "state/forge", "state/climb", "state/pnl_curves"):
        (tmp_path / d).mkdir(parents=True)
    with open(tmp_path / "state/layered/runs/forge.jsonl", "w") as fh:
        for r in rows.values():
            fh.write(json.dumps(dict(r, meta=dict(r["meta"], forge=1))) + "\n")
    with open(tmp_path / "state/climb/submitted.jsonl", "w") as fh:
        fh.write(json.dumps({"alpha": "cl", "http": 201, "formula": "rank(close)"}) + "\n")
    rng = random.Random(5)
    post = _walk(rng)
    json.dump(_curve(post), open(tmp_path / "state/pnl_curves/cl.json", "w"))
    json.dump(_curve([p + 0.2 * rng.gauss(0, 1) for p in post]), open(tmp_path / "state/pnl_curves/hp.json", "w"))
    st = ST.load(tmp_path)
    assert st.accepted == ["cl"]                                    # T08: the climb log is read
    assert set(st.stopped) == {"famH"} and st.stopped["famH"]["post"] == "cl"      # T06 and T07
