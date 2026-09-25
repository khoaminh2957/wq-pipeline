import json

import pytest

from framelib import build as BD
from framelib import schema as SC
from framelib import store as ST
from framelib.tests.test_evidence import row

NOW1, NOW2 = "2026-09-24T07:00:00+00:00", "2026-09-25T07:00:00+00:00"
DISCOVERY = """# Frames discovery

Background mentions `zscore($1)` which is not a candidate.

## Candidate list

| # | frame |
|---|---|
| 1 | `rank(divide($1, $2))` |
| 2 | `rank(ts_delta($1,5))` |

## Notes

`abs($1)` again not a candidate.
"""


@pytest.fixture()
def world(tmp_path):
    can = tmp_path / "canonical"
    can.mkdir()
    rows = [row("rank(divide($1,$2))", ["a", "b"]), row("rank(divide($1,$2))", ["c", "d"], d24=True),
            row("rank(divide($1,$2))", ["e", "cap"]), row("group_rank($1,industry)", ["a"]),
            row("group_rank($1,industry)", ["b"]), row("group_rank($1,industry)", ["c"])]
    (can / "rows_framed.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    summ = [{"frame_key": "rank(divide($1,$2))", "n_distinct_fills": 3},
            {"frame_key": "group_rank($1,industry)", "n_distinct_fills": 3}]
    (can / "frames_summary.jsonl").write_text("".join(json.dumps(s) + "\n" for s in summ))
    novel = tmp_path / "novel.jsonl"
    lines = [
        {"id": "NF01", "template": "rank(divide({1}, cap))", "frame": "rank(divide($1,$2))",
         "settings": {"region": "USA", "universe": "TOP3000", "neutralization": "INDUSTRY", "decay": 2, "truncation": 0.08},
         "slots": [{"slot": "$1", "role": "a sales-like level", "kind": ["level"], "structure": "MATRIX",
                    "exclude_datasets": ["pv1"], "pool_size_in_cell": 12, "note": "kept in the source only"}],
         "rationale": {"label": "SPECULATION", "text": "x"}},
        {"id": "NF05", "template": "subtract(rank({2}), rank({1}))",
         "slots": [{"slot": "$1", "role": "second written, first in normal form", "kind": ["ratio"]},
                   {"slot": "$2", "role": "first written", "kind": ["level"]}]},
        {"id": "NF02", "template": "if_else(rank({1}) > 0.5, 1, 0)"},                        # slot only in a condition
        {"id": "NF03", "frame": "ts_corr($1,$2,60)"},
        {"id": "NF04", "template": "rank({1})", "frame": "zscore($1)"},                     # template and frame disagree
    ]
    novel.write_text("".join(json.dumps(l) + "\n" for l in lines))
    disc = tmp_path / "discovery.md"
    disc.write_text(DISCOVERY)
    return {"canonical": can, "novel": novel, "discovery": disc, "out": tmp_path / "lib"}


def run(w, now=NOW1, **kw):
    return BD.build(w["canonical"], w["novel"], w["discovery"], kw.pop("k", None), w["out"], now=now, **kw)


def test_discovery_reads_only_the_candidate_section():
    spans, whole = BD.discovery_spans(DISCOVERY)
    assert [s for _, s in spans] == ["rank(divide($1, $2))", "rank(ts_delta($1,5))"] and whole is False
    spans, whole = BD.discovery_spans("# x\n`rank($1)`\n")
    assert [s for _, s in spans] == ["rank($1)"] and whole is True


def test_build_writes_valid_entries_with_provenance_and_evidence(world):
    rep = run(world, k=3)
    lib = {e["text"]: e for e in ST.load(world["out"])}
    assert set(lib) == {"rank(divide($1,$2))", "rank(ts_delta($1,5))", "group_rank($1,industry)",
                        "rank(divide($1,cap))", "ts_corr($1,$2,60)", "subtract(rank($1),rank($2))"}
    sl = lib["rank(divide($1,cap))"]["slots"][0]
    assert sl["role"] == "a sales-like level"
    assert sl["constraints"] == {"kind": ["level"], "structure": ["MATRIX"], "exclude_datasets": ["pv1"]}
    src = [x for x in lib["rank(divide($1,cap))"]["provenance"]["sources"] if x["kind"] == "novel"][0]
    assert src["slots"][0]["note"] == "kept in the source only" and src["rationale"]["label"] == "SPECULATION"
    sw = lib["subtract(rank($1),rank($2))"]["slots"]            # the designer's {2} is $1 in normal form
    assert [(s["role"], s["constraints"]) for s in sw] == [("first written", {"kind": ["level"]}),
                                                         ("second written, first in normal form", {"kind": ["ratio"]})]
    ratio = lib["rank(divide($1,$2))"]
    assert ratio["provenance"]["origin"] == "mined" and ratio["evidence"]["n_rows"] == 3
    assert {s["kind"] for s in ratio["provenance"]["sources"]} == {"discovery", "canonical"}
    pinned = lib["rank(divide($1,cap))"]                            # the designer's pinned field is kept ...
    assert pinned["pinned"] == {"2": "cap"} and pinned["evidence"]["n_rows"] == 1   # ... and selects its rows
    assert pinned["provenance"]["origin"] == "mined"                # the corpus holds it: not novel
    assert pinned["settings"] == {"source": "designer", "neutralization": "INDUSTRY", "decay": 2, "truncation": 0.08,
                                  "universe": {"USA": "TOP3000"}}
    assert lib["ts_corr($1,$2,60)"]["provenance"]["origin"] == "novel" and lib["ts_corr($1,$2,60)"]["evidence"] is None
    assert lib["group_rank($1,industry)"]["settings"]["source"] == "canonical-modal"
    errs = {e["source"].get("id"): e["error"] for e in rep["errors"]}
    assert "only in condition positions" in errs["NF02"] and "different canonical keys" in errs["NF04"]
    assert rep["new"] == 6 and (world["out"] / "INDEX.json").exists()


def test_rebuild_is_byte_identical_and_keeps_human_decisions(world):
    run(world, k=3)
    files = {p.name: p.read_text() for p in (world["out"] / "frames").glob("*.json")}
    rep = run(world, now=NOW2, k=3)
    assert rep["unchanged"] == 6 and rep.get("updated", 0) == 0
    assert {p.name: p.read_text() for p in (world["out"] / "frames").glob("*.json")} == files
    fid = SC.frame_id("ts_corr($1,$2,60)")
    p = world["out"] / "frames" / (fid + ".json")
    e = json.loads(p.read_text())
    e["status"] = "retired"
    e["status_history"].append({"status": "retired", "at": NOW2, "by": "khoa", "reason": "dead in every cell"})
    e["notes"] = "kept by hand"
    ST.save(e, world["out"])
    run(world, now=NOW2, k=3)
    again = json.loads(p.read_text())
    assert (again["status"], again["notes"], again["version"]) == ("retired", "kept by hand", 1)


def test_new_canonical_rows_bump_the_version(world):
    run(world, k=3)
    with open(world["canonical"] / "rows_framed.jsonl", "a") as fh:
        fh.write(json.dumps(row("group_rank($1,industry)", ["z"], d24=True)) + "\n")
    rep = run(world, now=NOW2, k=3)
    e = json.loads((world["out"] / "frames" / (SC.frame_id("group_rank($1,industry)") + ".json")).read_text())
    assert rep["updated"] >= 1 and e["version"] == 2 and e["evidence"]["n_rows"] == 4
    assert e["provenance"]["built_at"] == NOW2


def test_dry_run_writes_nothing_and_missing_inputs_are_reported(world, tmp_path):
    rep = BD.build(world["canonical"], tmp_path / "none.jsonl", tmp_path / "none.md", None, world["out"], now=NOW1, dry_run=True)
    assert rep["inputs"]["novel"]["missing"] and rep["inputs"]["discovery"][0]["missing"]
    assert rep["entries"] == 0 and not (world["out"] / "frames").exists()


def test_discovery_csv_keeps_candidate_rows_and_their_columns(world, tmp_path):
    csvp = tmp_path / "q4_candidates.csv"
    csvp.write_text(',mean,p_luck,candidate\n"rank(divide($1,$2))",1.03,1e-05,True\n"abs($1)",0.2,0.4,False\n')
    rep = BD.build(world["canonical"], None, [world["discovery"], csvp], None, world["out"], now=NOW1)
    assert rep["inputs"]["discovery"][1] == {"path": str(csvp), "candidates": 1}
    e = json.loads((world["out"] / "frames" / (SC.frame_id("rank(divide($1,$2))") + ".json")).read_text())
    src = [s for s in e["provenance"]["sources"] if s["path"] == str(csvp)]
    assert src == [{"kind": "discovery", "path": str(csvp), "sha256": src[0]["sha256"], "ref": "row 2",
                    "row": {"mean": "1.03", "p_luck": "1e-05", "candidate": "True"}}]
    assert not (world["out"] / "frames" / (SC.frame_id("abs($1)") + ".json")).exists()
