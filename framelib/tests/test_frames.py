import json
import pathlib
import re

import pytest

from framelib import frames as FR

HERE = pathlib.Path(__file__).parent
OPERATORS = HERE.parents[1] / "fetched/rc/operators.json"


def _examples():
    return [json.loads(l) for l in open(HERE / "data/canonical_examples.jsonl")]


@pytest.mark.parametrize("row", _examples(), ids=lambda r: r["case"])
def test_frame_formula_reproduces_signed_canonical_rows(row):
    """Rows copied verbatim from frames/canonical/rows_framed.jsonl (FRAME SPEC v1): reverse(<num>) (R1),
    strings with inner spaces (R2), driver=gaussian option token (R3), keyword args, infix, condition
    fields of if_else / trade_when (R9) and trade_when's argument 2 counted as slots."""
    key, fill, cond = FR.frame_formula(row["formula"])
    assert (key, fill, cond) == (row["frame_key"], row["fill"], row["cond_fields"])
    n = FR.Normal(row["formula"])
    assert n.shape == row["shape_key"]
    frame = FR.normalize(row["frame_key"])                       # the key is its own normal form
    assert (frame.text, frame.key) == (row["frame_key"], row["frame_key"])
    assert FR.frame_formula(frame.fill(row["fill"]))[0] == row["frame_key"]


def test_normalize_renumbers_slots_and_keeps_pinned_fields():
    n = FR.normalize("divide(ts_mean($2, 20), cap) + rank($1)")
    assert n.text == "add(divide(ts_mean($1,20),cap),rank($2))"
    assert n.key == "add(divide(ts_mean($1,20),$2),rank($3))"
    assert n.pinned == {2: "cap"}
    assert n.slot_key_index == [1, 3]
    assert n.key_fill(["x", "y"]) == ["x", "cap", "y"]
    assert FR.frame_formula(n.fill(["x", "y"])) == (n.key, ["x", "cap", "y"], [])


def test_condition_fields_are_not_slots_and_not_pinned():
    n = FR.normalize("trade_when(greater(volume, adv20), rank($1), -1)")
    assert n.cond_fields == ["volume", "adv20"]
    assert n.pinned == {}
    assert n.text == n.key == "trade_when(greater(volume,adv20),rank($1),reverse(1))"


def test_slot_only_in_condition_positions_is_refused():
    with pytest.raises(FR.FrameError, match="only in condition positions"):
        FR.normalize("if_else(greater(rank($1), 0.5), 1, 0)")


def test_slot_in_two_structural_contexts_is_refused():
    with pytest.raises(FR.FrameError, match="two structural contexts"):
        FR.normalize("add(vec_avg($1), $1)")


def test_frame_without_slot_is_refused():
    with pytest.raises(FR.FrameError, match="no slot"):
        FR.normalize("rank(close)")


def test_contexts_windows_groups():
    n = FR.normalize("group_rank(ts_delta(vec_avg($1), 120), $2) + ts_corr($3, close, 20)")
    assert [s["context"] for s in n.slots] == ["VECTOR", "GROUP", "MATRIX"]
    assert n.windows == [["ts_delta", 120], ["ts_corr", 20]]
    assert n.pinned == {4: "close"}
    n2 = FR.normalize("group_neutralize(rank($1), industry)")
    assert n2.groups == ["industry"]


def test_substitute_handles_two_digit_slots_and_strings():
    text = "add(" + ",".join("$%d" % i for i in range(1, 12)) + ',bucket(rank($1),range="$1 0, 1")' + ")"
    out = FR.substitute(text, ["f%d" % i for i in range(1, 12)])
    assert "f11" in out and "f1," in out and '"$1 0, 1"' in out


def _definition_tables():
    windows, groups = {}, {}
    for op in json.load(open(OPERATORS)):
        m = re.match(r"(\w+)\((.*)\)", op["definition"].split("\n")[0])
        if not m:
            continue
        name, params = m.group(1), [p.strip() for p in m.group(2).split(",")]
        for i, p in enumerate(params):
            pname, _, default = (x.strip() for x in p.partition("="))
            if pname == "d" or default == "d":
                windows[name] = i
            if pname in ("group", "g1", "g2"):
                groups[name] = groups.get(name, ()) + (i,)
    return windows, groups


def test_window_and_group_tables_match_operators_json():
    windows, groups = _definition_tables()
    assert FR.WINDOW_ARG == windows
    assert FR.GROUP_ARGS == groups
