"""framelib.loop.plan and framelib.loop.availability, on a small synthetic library and synthetic evidence.

Nothing here simulates or touches the network. The field library is written in the real file formats
(framelib/tests/conftest.py's helpers): six datasets of 12 level/currency fields, one pinned-field dataset
(dsP) and one dataset whose 12 fields are one fingerprint family (dsZ: zz_1..zz_12 -> "zz", for D18).
"""
from __future__ import annotations

import collections
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import pytest

from forge import novelty as NV
from framelib import compat as CM
from framelib import frames as FR
from framelib import schema as SC
from framelib.experiments import round1 as R1
from framelib.fields import FieldLibrary
from framelib.loop import availability as AV
from framelib.loop import plan as PL
from framelib.tests import conftest as CF

REPO = pathlib.Path(__file__).resolve().parents[2]
DAY, YDAY, DAY_2 = "2026-09-25", "2026-09-24", "2026-09-23"
DATASETS = ("dsA", "dsB", "dsC", "dsD", "dsE", "dsF")
LETTERS = "abcdefghijkl"
TXT = ["rank(ts_mean($1,%d))" % w for w in range(2, 60)]


def fid(ds, i):
    return "%s_fld_%s" % (ds.lower(), LETTERS[i])


def ds_fields(ds):
    return {fid(ds, i) for i in range(12)}


def write_meta(d: pathlib.Path) -> pathlib.Path:
    labels = [CF._label(fid(ds, i), ds, "level", "currency") for ds in DATASETS for i in range(12)]
    labels += [CF._label("pin_lvl", "dsP", "level", "currency")]
    labels += [CF._label("zz_%d" % k, "dsZ", "level", "currency") for k in range(1, 13)]
    (d / "field_labels.jsonl").write_text("".join(json.dumps(x) + "\n" for x in labels))
    (d / "fields").mkdir(exist_ok=True)
    (d / "fields" / "USA_TOP3000_d1.jsonl").write_text(
        "".join(json.dumps(CF._cat(x["id"], x["dataset"], "MATRIX")) + "\n" for x in labels))
    return d


@pytest.fixture(scope="module")
def meta(tmp_path_factory):
    return write_meta(tmp_path_factory.mktemp("loopmeta"))


@pytest.fixture()
def lib(meta):
    return FieldLibrary.build(meta / "field_labels.jsonl", meta / "fields")


PROF = {"source": "designer", "neutralization": "SUBINDUSTRY", "decay": 8, "truncation": 0.15,
        "universe": {"USA": "TOP3000"}}
AT_REF = dict(PROF, neutralization="INDUSTRY", decay=4, truncation=0.08)


def ent(text, origin="novel", status="candidate", built_at="2026-09-01T00:00:00+00:00", cons=None, settings=None,
        parent=None):
    n = FR.normalize(text)
    e = {"id": SC.frame_id(n.text), "version": 1, "text": n.text, "canonical_key": n.key, "status": status,
         "provenance": {"origin": origin, "built_at": built_at}}
    if cons is not None:
        e["slots"] = [dict(s, constraints=c) for s, c in zip(n.slots, cons)]
    if settings is not None:
        e["settings"] = settings
    if parent is not None:
        e["provenance"]["parent"] = parent
    return e


def tri(st):
    return {k: st[k] for k in ("neutralization", "decay", "truncation")}


def run_at(st):
    return dict(R1.BASE, **tri(st))


def ev(frame, day, route, n=8, scored=None, y08=0):
    return {"frame_id": frame, "day": day, "route": route, "n_planned": n,
            "n_scored": n if scored is None else scored, "y08": y08}


def plan(entries, lib, n=60, evidence=(), used=None, structures=None, hist=None, seed=11, day=DAY, blacklist=frozenset()):
    used = used or {}
    return PL.build(seed, n, entries=entries, fl=lib, hist=hist or {}, evidence=list(evidence),
                    used_fields=lambda f: used.get(f, set()), structures=structures, day=day, blacklist=blacklist)


def rows_of(p, route=None, frame=None):
    return [c for c in p["constructions"] if (route is None or c["meta"]["route"] == route)
            and (frame is None or c["meta"]["frame_id"] == frame)]


def _dispatch_round():
    spec = importlib.util.spec_from_file_location("dispatch_round_under_test",
                                                  REPO / "framelib/experiments/vps/dispatch_round.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- the ET day ------------------------------------------------------------------------------------------

def test_the_plan_day_is_the_new_york_day_not_the_utc_day():
    utc = datetime.timezone.utc
    assert PL.et_day(datetime.datetime(2026, 9, 25, 3, 30, tzinfo=utc).timestamp()) == "2026-09-24"
    assert PL.et_day(datetime.datetime(2026, 9, 25, 4, 30, tzinfo=utc).timestamp()) == "2026-09-25"


# ---- the evidence ledger -----------------------------------------------------------------------------------

def test_the_ledger_is_read_strictly(tmp_path):
    with pytest.raises(FileNotFoundError):
        PL.load_evidence(tmp_path / "absent.jsonl")
    p = tmp_path / "ev.jsonl"
    p.write_text(json.dumps(ev("F1", DAY, "screen")) + "\n\n{not json\n")
    with pytest.raises(ValueError):
        PL.load_evidence(p)
    p.write_text(json.dumps(ev("F1", DAY, "screen")) + "\n")
    assert PL.load_evidence(p) == [ev("F1", DAY, "screen")]
    row = ev("F1", DAY, "screen")
    del row["day"]
    with pytest.raises(ValueError, match="day"):
        PL.ledger([row])
    with pytest.raises(ValueError, match="n_scored"):
        PL.ledger([{k: v for k, v in ev("F1", DAY, "screen").items() if k != "n_scored"}])
    led = PL.ledger([ev("F1", DAY, "screen", 8, 6, 2), dict(ev("F1", YDAY, "r1b", 3, 3, 1), day=None, plan_day=YDAY)])
    assert led["F1"] == {"y08": 3, "scored": 9, "planned": {(DAY, "screen"): 8, (YDAY, "r1b"): 3}}


# ---- which frame goes where today ----------------------------------------------------------------------------

def test_each_frame_gets_todays_route():
    L1 = ent(TXT[0])                                            # library frame: production
    R1_ = ent(TXT[1], "mutation")                               # screened yesterday: replicate 8
    R2_ = ent(TXT[2], "mined-dropped")                          # screened yesterday, 3 replicated today: 5
    R3_ = ent(TXT[3], "mutation")                               # screened two days ago, never replicated
    R4_ = ent(TXT[4], "mutation")                               # screened 09-23, replicated 09-24: production
    P_ = ent(TXT[5], "mutation")                                # 5 screen rows today: 3 due
    N1 = ent(TXT[6], "mutation")                                # never seen: screen 8
    evs = [ev(R1_["id"], YDAY, "screen"), ev(R2_["id"], YDAY, "screen"), ev(R2_["id"], DAY, "replicate", 3),
           ev(R3_["id"], DAY_2, "screen"), ev(R4_["id"], DAY_2, "screen"), ev(R4_["id"], YDAY, "replicate"),
           ev(P_["id"], DAY, "screen", 5), ev(L1["id"], YDAY, "production", 30)]
    live = {e["id"]: e for e in (L1, R1_, R2_, R3_, R4_, P_, N1)}
    st = PL.stages(live, PL.ledger(evs), DAY)
    assert st == {"replicate": {R1_["id"]: 8, R2_["id"]: 5}, "screen": {P_["id"]: 3, N1["id"]: 8},
                  "production": sorted([L1["id"], R4_["id"]]), "waiting": [R3_["id"]]}


def test_retired_frames_are_never_planned(lib):
    live, dead_new, dead_lib = ent(TXT[0]), ent(TXT[1], "mutation", status="retired"), ent(TXT[2], status="retired")
    p = plan([live, dead_new, dead_lib], lib, n=20)
    assert {c["meta"]["frame_id"] for c in p["constructions"]} == {live["id"]}
    assert p["report"]["stages"] == {"replicate": 0, "screen": 0, "production": 1, "waiting": 0}


def test_the_screen_cohort_is_capped_at_25_a_day_oldest_first():
    begun = ent(TXT[0], "mutation")
    new = [ent(TXT[1 + k], "mutation", built_at="2026-09-25T00:%02d:00+00:00" % (59 - k)) for k in range(27)]
    live = {e["id"]: e for e in [begun] + new}
    st = PL.stages(live, PL.ledger([ev(begun["id"], DAY, "screen", 2)]), DAY)
    by_age = [e["id"] for e in sorted(new, key=lambda e: e["provenance"]["built_at"])]
    assert len(st["screen"]) == 25 and st["screen"][begun["id"]] == 6
    assert set(st["screen"]) == {begun["id"]} | set(by_age[:24])
    assert st["waiting"] == sorted(by_age[24:])


# ---- screen / replicate fills -----------------------------------------------------------------------------------

def test_screen_fills_are_own_role_fresh_and_a_mined_dropped_frame_keeps_its_history_datasets(lib):
    M = ent(TXT[0], "mined-dropped")
    B = ent(TXT[1], "mutation")                                 # begun today with 5 rows: 3 due
    hist = {M["canonical_key"]: {"slot_ds": [{"dsA"}], "slot_fields": [{fid("dsA", 0)}], "fills": {(fid("dsA", 0),)}}}
    used = {M["id"]: {fid("dsA", i) for i in (1, 2, 3, 4)}}
    p = plan([M, B], lib, n=60, evidence=[ev(B["id"], DAY, "screen", 5)], used=used, hist=hist)
    m_rows = rows_of(p, "screen", M["id"])
    # dsA holds 12 fields: 4 used with M, 1 is M's canonical history formula -> 7 fresh own-role fills
    assert len(m_rows) == 7 and p["report"]["short"]["screen"][M["id"]] == [8, 7]
    assert {c["meta"]["fill"][0] for c in m_rows} == {fid("dsA", i) for i in range(5, 12)}
    assert {c["meta"]["fill_mode"] for c in rows_of(p, "screen")} == {PL.OWN}
    assert len(rows_of(p, "screen", B["id"])) == 3 and p["report"]["counts"]["screen"] == 10


def test_replicate_takes_the_budget_before_screen(lib):
    reps = [ent(TXT[k], "mutation") for k in (0, 1)]
    news = [ent(TXT[k], "mutation") for k in (2, 3)]
    p = plan(reps + news, lib, n=10, evidence=[ev(e["id"], YDAY, "screen") for e in reps])
    assert p["report"]["counts"] == {"replicate": 10, "screen": 0, "production": 0}
    assert p["report"]["deferred"] == {"replicate": 6, "screen": 16, "production": 0}


# ---- freshness ----------------------------------------------------------------------------------------------------

def test_every_fill_is_fresh_for_its_frame_across_rounds_and_within_the_plan(lib):
    one, two = ent(TXT[0]), ent("rank(subtract($1,$2))")
    used = {one["id"]: ds_fields("dsA") | ds_fields("dsB")}
    p = plan([one, two], lib, n=60, used=used)
    assert rows_of(p, frame=one["id"]) and rows_of(p, frame=two["id"])
    assert not {f for c in rows_of(p, frame=one["id"]) for f in c["meta"]["fill"]} & used[one["id"]]
    for e in (one, two):
        fields = [f for c in rows_of(p, frame=e["id"]) for f in c["meta"]["fill"]]
        assert len(fields) == len(set(fields)), e["text"]


def test_the_canonical_history_formula_of_a_pinned_frame_is_excluded(lib):
    """A pinned frame's history fill is a canonical-KEY fill (pinned field included); round2's text fill
    would raise on it and silently exclude nothing."""
    E = ent("rank(subtract($1,pin_lvl))", cons=[{"datasets": ["dsA"]}])
    hist = {E["canonical_key"]: {"slot_ds": [{"dsA"}, {"dsP"}], "slot_fields": [{fid("dsA", 0)}, {"pin_lvl"}],
                                 "fills": {(fid("dsA", 0), "pin_lvl")}}}
    P = PL.Planner(3, DAY, {E["id"]: E}, lib, hist, lambda f: set(), None)
    got = []
    while (x := P.take(E["id"], PL.OWN)) is not None:
        got.append(x["fill"][0])
    assert sorted(got) == sorted(ds_fields("dsA") - {fid("dsA", 0)})


def test_no_formula_is_planned_twice_even_from_two_frames(lib):
    """A pinned field and a slot can share a canonical key, so two frames can write one formula;
    dispatch_round would drop the copy and shift every later parent boundary."""
    A = ent("rank(subtract($1,pin_lvl))", cons=[{"datasets": ["dsA"]}])
    B = ent("rank(subtract($1,$2))", cons=[{"datasets": ["dsA"]}, {"datasets": ["dsP"]}])
    only_a = ds_fields("dsA") - {fid("dsA", 0)}
    P = PL.Planner(5, DAY, {A["id"]: A, B["id"]: B}, lib, {}, lambda f: only_a, None)
    xa = P.take(A["id"], PL.OWN)
    assert xa["formula"] == "rank(subtract(%s,pin_lvl))" % fid("dsA", 0)
    assert P.take(B["id"], PL.OWN) is None and P.report["duplicate_formula"] == 1


# ---- availability --------------------------------------------------------------------------------------------------

def test_availability_prunes_to_todays_datasets_and_refuses_an_unusable_file(lib, tmp_path):
    ok = tmp_path / "datasets_ok.json"
    ok.write_text(json.dumps(["dsA", "dsC", "dsD", "dsE", "dsF", "dsP", "dsZ"]))
    info = AV.prune(lib, ok)
    assert info["removed"] == {"dataset": 12, "field": 0} and info["datasets"] == 7
    assert not ds_fields("dsB") & set(lib.ids_in(PL.CELL)) and ds_fields("dsA") <= set(lib.ids_in(PL.CELL))
    free, pinned_b = ent(TXT[0]), ent("rank(subtract($1,%s))" % fid("dsB", 0))
    p = plan([free, pinned_b], lib, n=40)
    assert rows_of(p) and not {f for c in rows_of(p) for f in c["meta"]["fill"]} & ds_fields("dsB")
    assert "absent" in p["report"]["dead"][pinned_b["id"]][PL.OWN][0]
    for bad in (None, "{not json", "[]", '{"a": 1}', '["dsA", ""]'):
        f = tmp_path / "bad.json"
        if bad is None:
            f.unlink(missing_ok=True)
        else:
            f.write_text(bad)
        with pytest.raises(AV.AvailabilityError):
            AV.load(f)


# ---- D18 at plan time ------------------------------------------------------------------------------------------------

POST_TWIN = {"alpha": "P1", "http": 200, "formula": "rank(ts_mean(zz_1,20))"}


def test_d18_refuses_near_duplicates_of_an_accepted_post_and_fails_open_without_an_index(lib):
    R1.restrict(lib, {"dsZ"})                                         # no other-dataset fill: every fill is "zz"
    Z = ent("rank(ts_mean($1,20))", cons=[{"datasets": ["dsZ"]}])
    refused = plan([Z], lib, n=10, structures=NV.build([POST_TWIN], {}))
    assert refused["constructions"] == [] and refused["report"]["d18_refused"] == 12
    assert refused["report"]["d18_twins"] == {"P1": 12} and refused["report"]["exhausted"] == [Z["id"]]
    open_ = plan([Z], lib, n=10, structures=None)
    assert len(open_["constructions"]) == 10 and open_["report"]["d18_refused"] == 0
    rejected_post = plan([Z], lib, n=10, structures=NV.build([dict(POST_TWIN, http=403)], {}))
    assert len(rejected_post["constructions"]) == 10                  # a 403 is not an accepted POST


def test_the_d18_index_fails_open_when_it_cannot_be_built(tmp_path, monkeypatch):
    log = tmp_path / "submitted.jsonl"
    log.write_text(json.dumps(POST_TWIN) + "\n" + json.dumps({"alpha": "P2", "http": 200}) + "\n")
    s, status = PL.d18_index([log])
    assert s.verdict("rank(ts_mean(zz_7,20))")[0] is True and status.startswith("incomplete") and "P2" in status

    def boom(**kw):
        raise OSError("log unreadable")
    monkeypatch.setattr(PL.FS, "posted_history", boom)
    s, status = PL.d18_index([log])
    assert s is None and status.startswith("unavailable (OSError")


# ---- production: Thompson sampling, the floor, fill modes ------------------------------------------------------------

def test_production_follows_the_posterior_with_a_20pc_exploration_floor(lib):
    A, B = ent(TXT[0]), ent(TXT[1])
    evs = [ev(A["id"], "2026-09-20", "production", 40, 40, 30), ev(B["id"], "2026-09-20", "production", 40, 40, 0)]
    p = plan([A, B], lib, n=50, evidence=evs)
    rows = rows_of(p, "production")
    explore = [c for c in rows if c["meta"]["select"] == "explore"]
    thompson = [c for c in rows if c["meta"]["select"] == "thompson"]
    assert len(rows) == 50 and len(explore) == 10 == p["report"]["explore"]
    assert {c["meta"]["frame_id"] for c in thompson} == {A["id"]}          # Beta(31, 11) vs Beta(1, 41)
    assert {c["meta"]["frame_id"] for c in explore} == {A["id"], B["id"]}  # the floor ignores the posterior
    firsts = [c["meta"]["select"] for c in rows]
    assert all(firsts[:m].count("explore") >= -(-m // 5) for m in range(1, 51))   # spread, any prefix


def test_production_fill_modes_follow_round1_and_fall_back_when_one_is_exhausted(lib):
    M = ent(TXT[0], "mined")
    hist = {M["canonical_key"]: {"slot_ds": [{"dsA"}], "slot_fields": [set()], "fills": set()}}
    p = plan([M], lib, n=20, hist=hist)
    own = [c for c in rows_of(p) if c["meta"]["fill_mode"] == PL.OWN]
    other = [c for c in rows_of(p) if c["meta"]["fill_mode"] == PL.OTHER]
    assert own and other
    assert all(c["meta"]["fill"][0] in ds_fields("dsA") for c in own)
    assert not any(c["meta"]["fill"][0] in ds_fields("dsA") for c in other)
    p = plan([M], lib, n=20, hist=hist, used={M["id"]: ds_fields("dsA")})
    assert len(rows_of(p)) == 20 and {c["meta"]["fill_mode"] for c in rows_of(p)} == {PL.OTHER}


# ---- shape: blocks, meta, settings, determinism ---------------------------------------------------------------------

def _scenario(lib):
    reps = [ent(TXT[k], "mutation") for k in (0, 1)]
    begun, new = ent(TXT[2], "mutation"), ent(TXT[3], "mutation")
    prods = [ent(TXT[k], settings=PROF) for k in (4, 5, 6)] + [ent(TXT[7], settings=AT_REF), ent(TXT[8])]
    prods += [ent("rank(subtract($1,$2))")]
    evs = [ev(e["id"], YDAY, "screen") for e in reps] + [ev(begun["id"], DAY, "screen", 5)]
    evs += [ev(e["id"], "2026-09-20", "production", 20, 20, k) for k, e in enumerate(prods)]
    return reps + [begun, new] + prods, evs


def test_every_route_comes_in_whole_blocks_of_ten_so_dispatch_keeps_parents_single_purpose(lib, capsys):
    entries, evs = _scenario(lib)
    p = plan(entries, lib, n=64, evidence=evs)
    # 60 rows: 10 pair fills (20 rows, pair_target(60) = 10) first, then replicate, screen, production
    assert p["report"]["counts"] == {"replicate": 10, "screen": 10, "production": 40}
    assert p["report"]["fills"] == {"single": 40, "paired": 10}
    assert p["report"]["deferred"] == {"replicate": 6, "screen": 1, "production": 0}
    merged = _dispatch_round().merged(p, {"constructions": []}, 7, PL.EXPERIMENT)
    assert "trimmed" not in capsys.readouterr().out and len(merged) == 60
    for i in range(0, len(merged), 10):
        blk = merged[i:i + 10]
        assert len({(c["meta"]["route"], "pair_id" in c["meta"]) for c in blk}) == 1


def test_every_row_carries_the_shared_meta_its_profile_settings_and_passes_the_gate(lib):
    entries, evs = _scenario(lib)
    p = plan(entries, lib, n=60, evidence=evs, seed=4242)
    by_id = {e["id"]: e for e in entries}
    versions = {e["id"]: e["version"] for e in entries}
    assert {c["meta"].get("pair_member") for c in p["constructions"]} == {None, "profile", "reference"}
    for c in p["constructions"]:
        m = c["meta"]
        assert m["experiment"] == "FRAMES-LOOP" and m["route"] in ("replicate", "screen", "production")
        assert m["arm"] == m["route"] if "pair_id" not in m else m["arm"].startswith("production-pair-")
        assert (m["round_seed"], m["plan_day"]) == (4242, DAY) and m["frame_version"] == versions[m["frame_id"]]
        want = PL.REFERENCE if m.get("pair_member") == "reference" else PL.profile(by_id[m["frame_id"]], by_id)[0]
        assert c["settings"] == run_at(want)
        assert c["formula"] == FR.normalize(next(e["text"] for e in entries if e["id"] == m["frame_id"])).fill(m["fill"])
        assert CM.structurally_ok(c["formula"], lib.labels, "USA", 1)[0]
    # one construction per (formula, settings), dispatch_round's key; a formula twice only as the two pair members
    assert len({(c["formula"], json.dumps(c["settings"], sort_keys=True)) for c in p["constructions"]}) == 60
    one = [c for c in p["constructions"] if c["meta"].get("pair_member") != "reference"]
    assert len({c["formula"] for c in one}) == len(one) == 50


def test_the_plan_is_determined_by_its_seed(lib):
    entries, evs = _scenario(lib)
    a = plan(entries, lib, n=60, evidence=evs, seed=1)
    b = plan(entries, FieldLibrary.build(*_meta_paths(lib)), n=60, evidence=evs, seed=1)
    c = plan(entries, lib, n=60, evidence=evs, seed=2)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert [x["formula"] for x in a["constructions"]] != [x["formula"] for x in c["constructions"]]


def _meta_paths(lib):
    d = pathlib.Path(lib.sources["labels"]).parent
    return d / "field_labels.jsonl", d / "fields"


def plan_digest(meta_dir) -> str:
    """The scenario plan's sha256, for the cross-process test below."""
    fl = FieldLibrary.build(pathlib.Path(meta_dir) / "field_labels.jsonl", pathlib.Path(meta_dir) / "fields")
    entries, evs = _scenario(fl)
    return hashlib.sha256(json.dumps(plan(entries, fl, n=60, evidence=evs, seed=9), sort_keys=True).encode()).hexdigest()


def test_the_plan_does_not_depend_on_the_process_hash_seed(meta):
    code = "import sys; sys.path[:0] = [%r, %r]; from framelib.tests import test_loop_plan as T; print(T.plan_digest(%r))" % (
        str(REPO), str(REPO / "tools"), str(meta))
    out = set()
    for hs in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=hs, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, "-B", "-c", code], env=env, capture_output=True, text=True, cwd=str(REPO))
        assert r.returncode == 0, r.stderr[-2000:]
        out.add(r.stdout.strip().splitlines()[-1])
    assert len(out) == 1


# ---- the command line --------------------------------------------------------------------------------------------------

def test_main_prunes_by_availability_writes_the_plan_and_fails_open_on_d18(lib, tmp_path, monkeypatch):
    import types

    import framelib.loop
    from framelib import store
    entries = [ent(TXT[0], "mined"), ent(TXT[1])]
    fake = types.ModuleType("framelib.loop.evidence")
    seen_state = []
    fake.used_fields = lambda f, state: seen_state.append(state) or {fid("dsC", 0)}
    monkeypatch.setitem(sys.modules, "framelib.loop.evidence", fake)
    monkeypatch.setattr(framelib.loop, "evidence", fake, raising=False)
    monkeypatch.setattr(store, "load", lambda *a, **k: entries)
    monkeypatch.setattr(PL.FieldLibrary if hasattr(PL, "FieldLibrary") else FieldLibrary, "build",
                        classmethod(lambda cls, *a, **k: lib))

    def boom(**kw):
        raise OSError("no submit log")
    monkeypatch.setattr(PL.FS, "posted_history", boom)
    (tmp_path / "ev.jsonl").write_text(json.dumps(ev(entries[0]["id"], YDAY, "production", 10, 10, 5)) + "\n")
    (tmp_path / "ok.json").write_text(json.dumps(["dsA", "dsC", "dsD", "dsE", "dsF"]))
    (tmp_path / "hist.jsonl").write_text(json.dumps({"region": "USA", "delay": 1, "universe": "TOP3000",
                                                     "frame_key": entries[0]["canonical_key"], "fill": [fid("dsA", 0)],
                                                     "fill_types": [{"dataset": "dsA"}]}) + "\n")
    runs = tmp_path / "state" / "layered" / "runs"
    runs.mkdir(parents=True)
    (runs / "frames_loop.jsonl").write_text(json.dumps(jrow("ERROR", "rank(ts_mean(%s,2))" % fid("dsA", 1),
                                                            UNIT % ("ts_mean", 0))) + "\n")
    bl = tmp_path / "state" / "frames" / "unit_blacklist.json"
    out = tmp_path / "plan.json"
    args = ["--n", "30", "--out", str(out), "--seed", "3", "--day", DAY, "--evidence", str(tmp_path / "ev.jsonl"),
            "--datasets-ok", str(tmp_path / "ok.json"), "--state", str(tmp_path / "state"), "--unit-blacklist", str(bl),
            "--history", str(tmp_path / "hist.jsonl")]
    assert PL.main(args) == 0
    p = json.loads(out.read_text())
    fields = {f for c in p["constructions"] for f in c["meta"]["fill"]}
    assert len(p["constructions"]) == 30 and p["seed"] == 3 and p["plan_day"] == DAY
    assert AV.load_unit_blacklist(bl) == {(fid("dsA", 1), "ts_mean")} and p["report"]["unit_blacklist"]["new"] == 1
    assert seen_state and set(seen_state) == {str(tmp_path / "state")}     # --state is where used_fields reads too
    assert not fields & (ds_fields("dsB") | {"pin_lvl", fid("dsC", 0), fid("dsA", 1)} | {"zz_%d" % k for k in range(1, 13)})
    assert p["report"]["availability"]["removed"] == {"dataset": 25, "field": 0}
    assert p["report"]["d18_index"].startswith("unavailable (OSError")
    own = [c for c in p["constructions"] if c["meta"]["frame_id"] == entries[0]["id"] and c["meta"]["fill_mode"] == PL.OWN]
    assert own and all(c["meta"]["fill"][0] in ds_fields("dsA") - {fid("dsA", 0)} for c in own)
    with pytest.raises(SystemExit):
        PL.main(args[:-1] + [str(tmp_path / "absent.jsonl")])


# ---- settings profiles (F10) -------------------------------------------------------------------------------------------

def test_a_frame_runs_at_its_own_settings_profile_or_the_reference(lib):
    modal = {"source": "canonical-modal", "neutralization": "STATISTICAL", "decay": 16, "truncation": 0.15,
             "universe": {"USA": "TOP3000"}, "n_rows": 9, "n_modal": 4}
    mined, novel = ent(TXT[0], "mined", settings=modal), ent(TXT[1], settings=PROF)
    child = ent(TXT[2], "mutation", settings={"source": "none"}, parent=novel["id"])
    grandchild = ent(TXT[3], "mutation", parent=child["id"])
    orphan = ent(TXT[4], "mutation", parent="F000000000000")
    eur = ent(TXT[5], settings=dict(PROF, universe={"EUR": "TOP2500"}))
    country = ent(TXT[6], settings=dict(PROF, neutralization="COUNTRY"))
    half, bare = ent(TXT[7], settings=dict(PROF, decay=2.5)), ent(TXT[8])
    E = {e["id"]: e for e in (mined, novel, child, grandchild, orphan, eur, country, half, bare)}
    assert PL.profile(mined, E) == (tri(modal), "canonical-modal")
    assert PL.profile(novel, E) == (tri(PROF), "designer")
    assert PL.profile(child, E) == (tri(PROF), "parent %s designer" % novel["id"])
    assert PL.profile(grandchild, E) == (tri(PROF), "parent %s designer" % novel["id"])
    for e, why in ((orphan, "no profile"), (eur, "written for EUR"), (country, "'COUNTRY' not offered in USA"),
                   (half, "decay 2.5"), (bare, "no profile")):
        got, src = PL.profile(e, E)
        assert got == PL.REFERENCE and src.startswith("reference") and why in src, (e["text"], src)
    p = plan([mined, novel, bare], lib, n=60)
    seen = set()
    for c in rows_of(p):
        m = c["meta"]
        want = PL.REFERENCE if m.get("pair_member") == "reference" else PL.profile(E[m["frame_id"]], E)[0]
        assert c["settings"] == run_at(want) and m["settings_profile"] == PL.profile(E[m["frame_id"]], E)[1]
        seen.add(json.dumps(c["settings"], sort_keys=True))
    assert len(seen) == 3                                   # STATISTICAL/16/0.15, SUBINDUSTRY/8/0.15, the reference


def test_usa_neutralizations_are_the_platform_options_snapshot():
    p = REPO / "fetched/rc/settings_options_live.json"
    if not p.exists():
        pytest.skip("no OPTIONS snapshot in this tree")
    st = json.loads(p.read_text())["actions"]["POST"]["settings"]["children"]
    usa = st["neutralization"]["choices"]["instrumentType"]["EQUITY"]["region"]["USA"]
    assert {c["value"] for c in usa} == PL.USA_NEUTRALIZATIONS
    assert (st["decay"]["minValue"], st["decay"]["maxValue"], st["truncation"]["minValue"], st["truncation"]["maxValue"]) == (0, 512, 0, 1)


# ---- pairs (F10) ---------------------------------------------------------------------------------------------------------

def test_a_quarter_of_the_fills_run_as_pairs_and_each_pair_shares_one_parent(lib, capsys):
    pa = [ent(TXT[k], settings=PROF) for k in (0, 1, 2)]
    at_ref, bare = ent(TXT[3], settings=AT_REF), ent(TXT[4])
    p = plan(pa + [at_ref, bare], lib, n=100)
    rows = rows_of(p)
    pairs = collections.defaultdict(list)
    for c in rows:
        if "pair_id" in c["meta"]:
            pairs[c["meta"]["pair_id"]].append(c)
    assert len(rows) == 100 and p["report"]["fills"] == {"single": 60, "paired": 20} and len(pairs) == 20
    assert PL.pair_target(100) == 20 and PL.pair_target(300) == 60 and PL.pair_target(20) == 0
    for pid, two in pairs.items():
        a, b = sorted(two, key=lambda c: c["meta"]["pair_member"])        # profile, reference
        assert (a["meta"]["pair_member"], b["meta"]["pair_member"]) == ("profile", "reference")
        assert a["formula"] == b["formula"] and a["meta"]["fill"] == b["meta"]["fill"]
        assert a["meta"]["frame_id"] == b["meta"]["frame_id"] in {e["id"] for e in pa}   # never at_ref, never bare
        assert a["settings"] == run_at(PROF) and b["settings"] == run_at(PL.REFERENCE)
        assert a["meta"]["route"] == b["meta"]["route"] == "production"
    merged = _dispatch_round().merged(p, {"constructions": []}, 3, PL.EXPERIMENT)
    assert "trimmed" not in capsys.readouterr().out and len(merged) == 100
    for i in range(0, 100, 10):
        blk = merged[i:i + 10]
        assert len({(c["meta"]["route"], "pair_id" in c["meta"]) for c in blk}) == 1
        assert all(v == 2 for v in collections.Counter(c["meta"]["pair_id"] for c in blk if "pair_id" in c["meta"]).values())


def test_no_pairable_frame_gives_the_pair_budget_to_the_other_routes(lib):
    p = plan([ent(TXT[0], settings=AT_REF), ent(TXT[1])], lib, n=40)
    assert len(rows_of(p)) == 40 and p["report"]["fills"] == {"single": 40, "paired": 0}
    assert p["report"]["pairs"] == {"target_fills": 5, "fills": 0, "pairable_frames": 0, "frames": 0}


# ---- the unit blacklist ----------------------------------------------------------------------------------------------------

UNIT = ('Incompatible unit for input of "%s" at index %d, expected "Unit[]", found "Unit[Group:1]". '
        '<linkToCommonErrorMessages>Learn more</linkToCommonErrorMessages>')
ST_ROW = dict(R1.BASE, neutralization="INDUSTRY", decay=4, truncation=0.08)


def jrow(status, formula, message=""):
    return {"status": status, "formula": formula, "message": message, "settings": ST_ROW,
            "meta": {"experiment": "FRAMES-LOOP", "frame_id": "Fx", "fill": []}}


def _journal(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_the_unit_blacklist_learns_rejected_inputs_and_keeps_them(tmp_path):
    runs = tmp_path / "layered" / "runs"
    runs.mkdir(parents=True)
    _journal(runs / "frames_r1b.jsonl", [
        jrow("ERROR", "rank(grp_a)", UNIT % ("rank", 0)),                      # one field at that input
        jrow("ERROR", "add(rank(fa),rank(grp_b))", UNIT % ("rank", 0)),        # fa was accepted by rank below
        jrow("COMPLETE", "rank(fa)"),
        jrow("ERROR", "subtract(rank(gx),rank(gy))", UNIT % ("rank", 0)),      # ambiguous: both kept
        jrow("ERROR", "divide(ts_mean(g1,5),close)", UNIT % ("divide", 0)),    # a sub-expression: unattributed
        jrow("WARNING", "subtract(close,f_px)", 'Incompatible unit for input of "subtract" at index 1, '
                                                'expected "Unit[CSPrice:1]", found "Unit[]"'),   # scored: a warning
        jrow("ERROR", "rank(fz)", 'Attempted to use unknown variable "fz"')])
    _journal(runs / "frames_loop.jsonl", [jrow("ERROR", "ts_mean(grp_c,5)", UNIT % ("ts_mean", 0))])
    bl = tmp_path / "frames" / "unit_blacklist.json"
    assert AV.load_unit_blacklist(bl) == frozenset()                          # nothing learned yet
    rep = AV.refresh_unit_blacklist(tmp_path, bl)
    want = {("grp_a", "rank"), ("grp_b", "rank"), ("gx", "rank"), ("gy", "rank"), ("grp_c", "ts_mean")}
    assert AV.load_unit_blacklist(bl) == want and (rep["pairs"], rep["new"], rep["unattributed"]) == (5, 5, 1)
    doc = json.loads(bl.read_text())
    att = {(e["field"], e["operator"]): e["attribution"] for e in doc["pairs"]}
    assert att == {("grp_a", "rank"): "unique", ("grp_b", "rank"): "unique", ("gx", "rank"): "ambiguous",
                   ("gy", "rank"): "ambiguous", ("grp_c", "ts_mean"): "unique"}
    assert "no field written directly" in doc["unattributed"][0]["reason"]
    before = bl.read_text()
    (runs / "frames_loop.jsonl").unlink()                                      # the journal that taught grp_c is gone
    rep = AV.refresh_unit_blacklist(tmp_path, bl)
    assert AV.load_unit_blacklist(bl) == want and rep["new"] == 0 and bl.read_text() == before
    for bad in ("{not json", '{"pairs": {}}', '{"pairs": [{"field": "x"}]}'):
        bl.write_text(bad)
        with pytest.raises(AV.AvailabilityError):
            AV.load_unit_blacklist(bl)


def test_a_blacklisted_field_operator_input_is_never_planned(lib):
    bl = frozenset((fid("dsA", i), "ts_mean") for i in range(12))
    p = plan([ent("rank(ts_mean($1,20))")], lib, n=60, blacklist=bl)
    assert len(rows_of(p)) == 60 and not {f for c in rows_of(p) for f in c["meta"]["fill"]} & ds_fields("dsA")
    assert p["report"]["unit_blacklisted"] > 0 and set(p["report"]["unit_hits"]) <= {"%s|ts_mean" % f for f in ds_fields("dsA")}
    # the key is (field, operator): the same fields under another operator are planned
    q = plan([ent("rank(ts_sum($1,20))", cons=[{"datasets": ["dsA"]}])], lib, n=20, blacklist=bl)
    assert q["report"]["unit_blacklisted"] == 0 and {f for c in rows_of(q) for f in c["meta"]["fill"]} & ds_fields("dsA")


# ---- the round's size --------------------------------------------------------------------------------------------------------

def test_a_round_is_one_dispatch_chunk_at_most(lib, monkeypatch):
    assert PL.MAX_ROWS == _dispatch_round().CHUNK == 300
    monkeypatch.setattr(PL, "MAX_ROWS", 20)
    p = plan([ent(TXT[0]), ent(TXT[1])], lib, n=60)
    assert len(p["constructions"]) == 20 and p["report"]["capped"] == [60, 20]
    assert plan([ent(TXT[0])], lib, n=20)["report"]["capped"] is None


def test_a_purpose_whose_supply_runs_out_mid_block_is_cut_to_whole_blocks(lib, capsys):
    R1.restrict(lib, {"dsZ"})                                   # 12 fields: each frame has 12 fresh fills
    paired, single = ent("rank(ts_mean($1,20))", settings=PROF), ent("rank(ts_sum($1,20))")
    p = plan([paired, single], lib, n=100)                      # pair target 20 fills: 12 exist -> 10 kept
    assert p["report"]["pairs"]["fills"] == 10 and p["report"]["fills"] == {"single": 10, "paired": 10}
    assert len(rows_of(p)) == 30 and p["report"]["deferred"]["production"] == 2
    merged = _dispatch_round().merged(p, {"constructions": []}, 5, PL.EXPERIMENT)
    assert "trimmed" not in capsys.readouterr().out and len(merged) == 30
