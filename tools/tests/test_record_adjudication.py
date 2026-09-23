import importlib.util
import pathlib
import sys

_SPEC = importlib.util.spec_from_file_location(
    "record_adjudication", pathlib.Path(__file__).resolve().parents[1] / "record_adjudication.py")
RA = importlib.util.module_from_spec(_SPEC)
sys.modules["record_adjudication"] = RA
_SPEC.loader.exec_module(RA)


def _post(alpha):
    return {"alpha": alpha, "http": 201, "posted_at": 1.0}


def _adj(alpha, status, at=2.0):
    return {"kind": "adjudication", "alpha": alpha, "status": status, "at": at}


def test_an_alpha_with_no_adjudication_is_pending():
    assert RA.pending([_post("a1")]) == {"a1"}


def test_a_terminal_status_is_never_read_again():
    assert RA.pending([_post("a1"), _adj("a1", "ACTIVE")]) == set()
    assert RA.pending([_post("a1"), _adj("a1", "DECOMMISSIONED")]) == set()


def test_a_non_terminal_snapshot_is_read_again():
    """MEASURED 2026-09-20: vRk1J2jd was recorded UNSUBMITTED on 09-10 -- the state it held for the
    minutes before the platform finished adjudicating -- and because ANY adjudication row counted as
    'done', that snapshot stood for ten days while the alpha was ACTIVE at stage OS. A transient
    condition must never be written down as a permanent fact."""
    assert RA.pending([_post("a1"), _adj("a1", "UNSUBMITTED")]) == {"a1"}
    assert RA.pending([_post("a1"), _adj("a1", None)]) == {"a1"}
    assert RA.pending([_post("a1"), _adj("a1", "")]) == {"a1"}


def test_the_last_row_wins_so_a_settled_alpha_stops_being_read():
    rows = [_post("a1"), _adj("a1", "UNSUBMITTED", at=2.0), _adj("a1", "ACTIVE", at=3.0)]
    assert RA.pending(rows) == set()
    # and an alpha that later leaves ACTIVE is picked up again
    rows.append(_adj("a1", "PENDING", at=4.0))
    assert RA.pending(rows) == {"a1"}


def test_status_case_does_not_matter():
    assert RA.pending([_post("a1"), _adj("a1", "active")]) == set()


def test_rows_that_are_not_accepted_posts_are_ignored():
    rows = [{"alpha": "a1", "http": 403}, {"alpha": "a2", "http": None}, _post("a3")]
    assert RA.pending(rows) == {"a3"}
