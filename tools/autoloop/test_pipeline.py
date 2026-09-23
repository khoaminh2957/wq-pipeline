#!/usr/bin/env python3
"""test_pipeline.py — regression suite for the decisions that spend irreversible budget.

Run: python3 tools/autoloop/test_pipeline.py      (exits non-zero on any failure)

Motivating incident (iter49): tools/funnel/gates.py scored a simulation with an ALLOWLIST of gate
names and silently skipped any check whose name was not listed. The platform returned
`IS_LADDER_SHARPE FAIL value=1.4 limit=1.58` on pwKZl6Zg / O0xVZpVd / Vk35PY2J; the name was not in
the allowlist, zero_fail() answered (True, []), all three were auto-submitted, and all three came
back 403. Platform rule G6 gives each alpha exactly ONE submit POST ever, so those three alphas are
permanently dead.

The bug class is wider than that one function: an UNANTICIPATED VALUE READ AS SUCCESS. An unlisted
gate name, an empty `records: []` list, a 4xx status, a rate-limit JSON body, a substring match on
"ALREADY_SUBMITTED" -- each is a condition the code did not enumerate, and each defaulted to "fine".
Every test here pins one such default to the safe side, in the four places that can spend a real
budget slot: the gate scorer, the correlation reader, the submit guard, and the autoloop driver.

Rules this suite obeys:
  * NO network. Every platform call is mocked; the session object passed into production code
    raises on ANY attribute access, so a real request would fail the test rather than fire.
  * NO writes to repo state. Anything the code under test would write is redirected to a tmpdir.
  * Ground truth over invention: the pass/fail fixtures are the real journal rows of the 5 alphas
    that are LIVE on the account and the 3 that were 403-rejected.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import ast
import copy
import glob
import json
import os
import pathlib
import re
import tempfile
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "tools", ROOT / "tools" / "funnel", ROOT / "tools" / "autoloop"):
    sys.path.insert(0, str(p))

import gates                                  # noqa: E402  tools/funnel/gates.py
import boost_metric                           # noqa: E402  tools/funnel/boost_metric.py
import fetch_prod_corr                        # noqa: E402  tools/fetch_prod_corr.py
import submit_alphas                          # noqa: E402  tools/submit_alphas.py
import driver                                 # noqa: E402  tools/autoloop/driver.py
from harness.guards import submit_allowed     # noqa: E402

RESULTS = ROOT / "state/resim_results.jsonl"
SUBMIT_LOG = ROOT / "state/funnel/submit_log.jsonl"
BANNED = ROOT / "state/banned_fields.json"

# The 5 alphas that are ACTIVE on the real account. Rejecting any of these is a FALSE BLOCK: the
# funnel would throw away work that the platform itself has already accepted.
LIVE = ["QP99gYLM", "Xg8oQJRl", "zqRN8LGE", "KPE7nLX8", "e7xG3nrM"]
# The 3 alphas whose journal row carried IS_LADDER_SHARPE FAIL, were scored as passes, submitted,
# and 403'd. Each burned its one lifetime POST.
DEAD_403 = ["pwKZl6Zg", "O0xVZpVd", "Vk35PY2J"]


# --------------------------------------------------------------------------- fixtures
def _load_journal():
    """ONE pass over the 41MB journal: ground-truth rows, every gate name ever seen FAIL, and a
    legacy row whose `checks` are bare strings (the old presence-only format)."""
    wanted = set(LIVE) | set(DEAD_403)
    rows, fail_names, legacy = {}, set(), None
    with open(RESULTS) as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            checks = d.get("checks") or []
            if d.get("alpha") in wanted:
                rows[d["alpha"]] = d
            for c in checks:
                if isinstance(c, dict) and c.get("result") == "FAIL":
                    fail_names.add(c.get("name"))
            if legacy is None and checks and all(isinstance(c, str) for c in checks):
                legacy = d
    return rows, {n for n in fail_names if n}, legacy


JOURNAL, FAIL_GATE_NAMES, LEGACY_ROW = _load_journal()


def base_row(alpha="QP99gYLM"):
    """A deep copy of a real LIVE alpha's journal row: scores (True, [], []) untouched, so any
    later assertion is attributable to the single field the test mutates."""
    return copy.deepcopy(JOURNAL[alpha])


def set_check(row, name, **kw):
    for c in row["checks"]:
        if isinstance(c, dict) and c.get("name") == name:
            c.update(kw)
            return c
    raise AssertionError(f"fixture drift: {name} not in the base row's checks")


def drop_key(row, name, key):
    for c in row["checks"]:
        if isinstance(c, dict) and c.get("name") == name:
            c.pop(key, None)
            return c
    raise AssertionError(f"fixture drift: {name} not in the base row's checks")


# Correlation payloads. Shape taken from tools/fetch_prod_corr.py's own docstring: the prod side is
# a histogram of |corr| in 0.1 buckets ([min, max, alphas]) that carries the true extremes at the
# TOP level as j['max'] / j['min'].
def prod_payload(max_corr=0.5, buckets=((0.0, 0.1, 3), (0.4, 0.5, 5))):
    return {"schema": {"name": "prod_correlation",
                       "properties": [{"name": "min"}, {"name": "max"}, {"name": "alphas"}]},
            "records": [list(b) for b in buckets], "max": max_corr, "min": -0.31}


def self_payload(corrs):
    """corrs=None -> the platform's 'still computing' answer (schema present, records empty)."""
    return {"schema": {"name": "self_correlation",
                       "properties": [{"name": "alphas"}, {"name": "correlation"}]},
            "records": [] if corrs is None else [[f"a{i}", c] for i, c in enumerate(corrs)]}


RATE_LIMIT_BODY = {"message": "API rate limit exceeded"}


class NoNetworkSession:
    """Any use at all is a test failure. Production code gets this instead of requests.Session."""

    def __getattr__(self, name):
        raise AssertionError(f"NETWORK ACCESS ATTEMPTED: session.{name}(...) — the test must mock it")


# =========================================================================== 1. GATE CORRECTNESS
class TestGateCorrectness(unittest.TestCase):
    """tools/funnel/gates.py — the allowlist trap and its whole family."""

    def test_live_alphas_still_pass(self):
        """GROUND TRUTH, no-false-block direction: the 5 ACTIVE alphas must all score zero-fail."""
        for a in LIVE:
            with self.subTest(alpha=a):
                self.assertIn(a, JOURNAL, f"{a} has no journal row — fixture lost")
                passed, failed, missing = gates.zero_fail(JOURNAL[a])
                self.assertTrue(passed, f"FALSE BLOCK on LIVE alpha {a}: failed={failed} missing={missing}")

    def test_403_alphas_are_rejected(self):
        """GROUND TRUTH, no-false-pass direction: the 3 alphas that 403'd on IS_LADDER_SHARPE."""
        for a in DEAD_403:
            with self.subTest(alpha=a):
                passed, failed, _ = gates.zero_fail(JOURNAL[a])
                self.assertFalse(passed, f"{a} scored as a PASS — this is the iter49 bug back")
                self.assertIn("IS_LADDER_SHARPE", failed,
                              f"{a} was rejected, but not for the gate the platform failed it on")

    def test_fail_blocks_for_a_gate_name_no_one_has_seen(self):
        """The core anti-allowlist property: a FAIL blocks even under a name the code cannot know."""
        for name in ("BRAND_NEW_2027_GATE", "IS_LADDER_SHARPE_V2", "", "low_sharpe"):
            with self.subTest(gate=name):
                row = base_row()
                row["checks"].append({"name": name, "result": "FAIL", "value": 1.4, "limit": 1.58})
                passed, failed, _ = gates.zero_fail(row)
                self.assertFalse(passed, f"unknown gate {name!r} FAILED and the row still passed")
                self.assertIn(name, failed)

    def test_every_gate_name_ever_seen_failing_blocks(self):
        """Parameterized over every gate the platform has ever returned FAIL for in the journal, so
        a gate introduced by the platform tomorrow is covered the moment it appears in one row."""
        self.assertGreaterEqual(len(FAIL_GATE_NAMES), 10, "journal scan found suspiciously few gates")
        for name in sorted(FAIL_GATE_NAMES):
            with self.subTest(gate=name, in_allowlist=name in gates.BLOCKING):
                row = base_row()
                row["checks"].append({"name": name, "result": "FAIL", "value": 0.1, "limit": 9.9})
                passed, failed, _ = gates.zero_fail(row)
                self.assertFalse(passed, f"{name} FAILED and the row still scored zero-fail")
                self.assertIn(name, failed)

    def test_some_failing_gates_are_outside_the_allowlist(self):
        """Proves the previous test is not vacuous: the platform really does fail alphas on gates
        that BLOCKING does not list, which is exactly why membership must not be the rule."""
        outside = FAIL_GATE_NAMES - set(gates.BLOCKING)
        self.assertTrue(outside, "no observed FAIL gate lies outside BLOCKING — check the fixture")

    def test_row_without_checks_never_passes(self):
        for row in ({}, {"checks": []}, {"checks": None}, {"old_id": "x", "alpha": "y"}):
            with self.subTest(row=row):
                passed, _, missing = gates.zero_fail(row)
                self.assertFalse(passed, "a row carrying no platform verdict scored as a pass")
                self.assertTrue(missing)

    def test_unknown_segment_never_passes(self):
        """A row whose old_id is in no targets file has no known (region, universe, delay), so the
        applicable gate set is unknown. Unknown must not default to USA/TOP3000 and pass."""
        row = base_row()
        row["old_id"] = "___old_id_that_is_in_no_targets_file___"
        row.pop("settings", None)
        self.assertEqual(gates._segment(row), (None, None, None))
        passed, _, missing = gates.zero_fail(row)
        self.assertFalse(passed, "unknown segment scored as a pass")
        self.assertTrue(any("unknown segment" in m for m in missing))

    def test_warning_on_the_failing_side_of_its_limit_blocks(self):
        """A WARNING is not automatically a pass. Below the ladder waiver bar, a hard gate whose
        value sits on the wrong side of its own limit is a genuine block."""
        row = base_row()
        set_check(row, "IS_LADDER_SHARPE", value=1.50)          # under _LADDER_WAIVER -> no waiver
        set_check(row, "LOW_FITNESS", result="WARNING", value=0.55, limit=1.0)
        passed, failed, _ = gates.zero_fail(row)
        self.assertFalse(passed, "WARNING with fitness 0.55 against a 1.0 bar scored as a pass")
        self.assertTrue(any(f.startswith("LOW_FITNESS") for f in failed), failed)

    def test_warning_inside_its_limit_does_not_block(self):
        """The mirror of the above — the WARNING rule must not become a blunt reject-all."""
        row = base_row()
        set_check(row, "IS_LADDER_SHARPE", value=1.50)
        set_check(row, "LOW_FITNESS", result="WARNING", value=1.20, limit=1.0)
        passed, failed, missing = gates.zero_fail(row)
        self.assertTrue(passed, f"FALSE BLOCK: fitness 1.20 clears its 1.0 bar. {failed} {missing}")

    def test_high_side_warning_breach_blocks(self):
        """HIGH_TURNOVER fails ABOVE its limit — the direction table must be applied, not assumed."""
        row = base_row()
        set_check(row, "IS_LADDER_SHARPE", value=1.50)
        set_check(row, "HIGH_TURNOVER", result="WARNING", value=0.95, limit=0.7)
        passed, failed, _ = gates.zero_fail(row)
        self.assertFalse(passed, "turnover 0.95 against a 0.7 ceiling scored as a pass")
        self.assertTrue(any(f.startswith("HIGH_TURNOVER") for f in failed), failed)

    def test_unmeasured_hard_gate_is_not_a_pass(self):
        """A hard gate the platform did NOT evaluate must not read as satisfied.

        This is the iter49 mistake in its next costume. `result: "ERROR"` is a value gates.py does
        not enumerate, so the check falls through both branches and the gate is treated as present
        and fine. It is not synthetic: LOW_FITNESS appears with result=ERROR 125 times in
        state/resim_results.jsonl and LOW_SUB_UNIVERSE_SHARPE 144 times."""
        cases = [("ERROR", lambda r: set_check(r, "LOW_FITNESS", result="ERROR", value=None)),
                 ("PENDING", lambda r: set_check(r, "LOW_SHARPE", result="PENDING", value=None)),
                 ("missing-result-key", lambda r: drop_key(r, "LOW_SHARPE", "result"))]
        for label, mutate in cases:
            with self.subTest(unmeasured=label):
                row = base_row()
                mutate(row)
                passed, failed, missing = gates.zero_fail(row)
                self.assertFalse(passed, f"a hard gate with result={label} was counted as passed "
                                         f"(failed={failed} missing={missing})")

    def test_legacy_presence_only_row_never_passes(self):
        """Rows from before the platform returned verdicts carry `checks` as bare gate NAMES. A name
        list says nothing about pass or fail, so such a row must never score zero-fail."""
        self.assertIsNotNone(LEGACY_ROW, "no legacy string-checks row in the journal")
        passed, _, _ = gates.zero_fail(LEGACY_ROW)
        self.assertFalse(passed, "a presence-only row (checks = list of names) scored as a pass")

    def test_zero_fail_contract(self):
        """Callers unpack three values (tools/autoloop/driver.py:365). Lock the shape."""
        out = gates.zero_fail(base_row())
        self.assertEqual(len(out), 3)
        self.assertIsInstance(out[0], bool)
        self.assertIsInstance(out[1], list)
        self.assertIsInstance(out[2], list)


class TestBoostMetricGate(unittest.TestCase):
    """tools/funnel/boost_metric.py keeps its OWN copy of the zero-fail rule (_is_zero_fail). A
    second copy of the rule is how the original disagreement happened, so it gets the same tests."""

    def test_boost_rejects_failing_rows(self):
        row = base_row()
        row["checks"].append({"name": "IS_LADDER_SHARPE", "result": "FAIL", "value": 1.4, "limit": 1.58})
        self.assertFalse(boost_metric._is_zero_fail(row))

    def test_boost_accepts_live_alphas(self):
        for a in LIVE:
            with self.subTest(alpha=a):
                self.assertTrue(boost_metric._is_zero_fail(JOURNAL[a]))

    def test_boost_requires_an_actual_verdict(self):
        """No checks == no evidence of a pass. `[]` has zero FAILs, which is not the same thing."""
        for row in ({}, {"checks": []}, {"old_id": "x"},
                    {"checks": ["LOW_SHARPE", "LOW_FITNESS"]}):    # legacy presence-only format
            with self.subTest(row=row):
                self.assertFalse(boost_metric._is_zero_fail(row),
                                 "a row with no platform verdict was certified zero-fail")


# =========================================================================== 2. CORRELATION READER
class TestCorrelationReader(unittest.TestCase):
    """tools/fetch_prod_corr.py — the number the PROD_CORRELATION gate is actually taken on."""

    def test_prod_maxcorr_is_the_exact_max_not_a_bucket_edge(self):
        """GROUND TRUTH: 3qeeOxlQ's platform rejection read `PROD_CORRELATION value=0.7031`. The
        payload's top non-empty bucket is [0.7, 0.8], so a bucket-edge reader answers 0.8 and the
        real number is invisible. The gate is on j['max']."""
        j = prod_payload(max_corr=0.7031,
                         buckets=((0.0, 0.1, 4), (0.6, 0.7, 9), (0.7, 0.8, 2), (0.8, 0.9, 0), (0.9, 1.0, 0)))
        pc, breach = fetch_prod_corr.prod_maxcorr(j)
        self.assertEqual(pc, 0.7031, "prod_maxcorr returned a quantised bucket edge, not j['max']")
        self.assertEqual(breach, 2, "the >0.7 production-alpha count is wrong")

    def test_prod_maxcorr_survives_a_non_payload_200(self):
        """A 200 can carry JSON that is not a correlation payload. It must read as UNMEASURED, and
        it must not raise — a KeyError here takes down a whole batch mid-run."""
        for body in (RATE_LIMIT_BODY, None, {}, [], "text", {"schema": None}, {"schema": {}},
                     {"records": [[0.0, 0.1, 1]]}):
            with self.subTest(body=body):
                try:
                    pc, breach = fetch_prod_corr.prod_maxcorr(body)
                except Exception as e:
                    self.fail(f"prod_maxcorr raised {type(e).__name__} on {body!r}")
                self.assertEqual((pc, breach), (None, None), f"{body!r} did not read as unmeasured")

    def test_prod_maxcorr_absent_max_is_unmeasured(self):
        j = prod_payload()
        j.pop("max")
        pc, _ = fetch_prod_corr.prod_maxcorr(j)
        self.assertIsNone(pc, "a payload with no 'max' must not yield a number")

    def test_self_maxcorr_empty_records_is_none(self):
        """THE fail-closed guard. `records: []` is the platform saying 'still computing'. It is not
        'no correlated alphas', and `[] is not None` is True — which is how a freshly-simmed alpha
        used to slip through as a clean self-corr."""
        self.assertIsNone(fetch_prod_corr.self_maxcorr(self_payload(None)))

    def test_self_maxcorr_unreadable_inputs_are_none(self):
        for body in (None, {}, [], RATE_LIMIT_BODY, {"schema": {"properties": [{"name": "alphas"}]},
                                                     "records": [["a"]]}):
            with self.subTest(body=body):
                try:
                    self.assertIsNone(fetch_prod_corr.self_maxcorr(body))
                except Exception as e:
                    self.fail(f"self_maxcorr raised {type(e).__name__} on {body!r}")

    def test_self_maxcorr_reads_the_maximum(self):
        self.assertEqual(fetch_prod_corr.self_maxcorr(self_payload([0.41, 0.99, 0.12])), 0.99)
        self.assertIsNone(fetch_prod_corr.self_maxcorr(self_payload([None, None])))

    def test_both_readers_of_the_same_payload_agree(self):
        """tools/measure_corr_incremental.py reads the SAME prod payload and records its answer as
        `prod_max`. Two readers of one payload that disagree is the duplicated-rule failure that
        produced the original gate bug; the platform's number is one number.

        prod_breach is exec'd from source because importing that module runs its CLI body (it opens
        state/funnel/corr_results.jsonl for append)."""
        src = (ROOT / "tools/measure_corr_incremental.py").read_text()
        fn = next(n for n in ast.parse(src).body
                  if isinstance(n, ast.FunctionDef) and n.name == "prod_breach")
        ns: dict = {}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "<mci>", "exec"), ns)
        j = prod_payload(max_corr=0.7031,
                         buckets=((0.0, 0.1, 4), (0.6, 0.7, 9), (0.7, 0.8, 2)))
        mine, _ = ns["prod_breach"](j)
        theirs, _ = fetch_prod_corr.prod_maxcorr(j)
        self.assertEqual(mine, theirs,
                         "measure_corr_incremental.prod_breach and fetch_prod_corr.prod_maxcorr "
                         "report different PROD_CORRELATION values for the same payload")


# =========================================================================== 3. SUBMIT GUARD
class TestSubmitGuard(unittest.TestCase):
    """tools/submit_alphas.py::_fresh_corr_ok — the last check before an irreversible POST.

    Every case mocks fetch_prod_corr._fetch (which _fresh_corr_ok re-imports at call time) and hands
    the guard a session that raises on any use, so nothing can reach the network and nothing is
    POSTed. The invariant is FAIL-CLOSED: anything short of a completed measurement blocks."""

    def setUp(self):
        self._orig = fetch_prod_corr._fetch
        self.addCleanup(lambda: setattr(fetch_prod_corr, "_fetch", self._orig))

    def _guard(self, prod, selfj):
        fetch_prod_corr._fetch = lambda s, aid, kind, budget_s=420: prod if kind == "prod" else selfj
        return submit_alphas._fresh_corr_ok(NoNetworkSession(), "TESTALPHA")

    def test_blocks_when_self_corr_is_still_computing(self):
        ok, why = self._guard(prod_payload(), self_payload(None))
        self.assertFalse(ok, f"submit allowed on an unmeasured self-corr ({why})")

    def test_blocks_when_self_fetch_failed(self):
        ok, why = self._guard(prod_payload(), None)
        self.assertFalse(ok, f"submit allowed on a failed self-corr fetch ({why})")

    def test_blocks_when_prod_fetch_failed(self):
        for prod in (None, RATE_LIMIT_BODY, {}):
            with self.subTest(prod=prod):
                ok, why = self._guard(prod, self_payload([0.4]))
                self.assertFalse(ok, f"submit allowed on an unmeasured prod-corr ({why})")

    def test_blocks_a_near_duplicate(self):
        ok, why = self._guard(prod_payload(), self_payload([0.41, 0.99]))
        self.assertFalse(ok, "submit allowed at self-corr 0.99 (the e7x0G7ag twin failure)")

    def test_blocks_when_the_measurement_raises(self):
        def boom(*a, **k):
            raise RuntimeError("connection reset by peer")
        fetch_prod_corr._fetch = boom
        ok, why = submit_alphas._fresh_corr_ok(NoNetworkSession(), "TESTALPHA")
        self.assertFalse(ok, "submit allowed after the correlation fetch threw")

    def test_allows_a_genuinely_clean_measurement(self):
        """Fail-closed must not mean fail-always, or the pipeline can never submit anything."""
        ok, why = self._guard(prod_payload(max_corr=0.42), self_payload([0.41]))
        self.assertTrue(ok, f"FALSE BLOCK on a clean measurement: {why}")

    def test_guard_never_touches_the_network_itself(self):
        """_fresh_corr_ok must delegate every request; it must not build its own session."""
        ok, _ = self._guard(prod_payload(), self_payload([0.4]))   # NoNetworkSession would raise
        self.assertTrue(ok)


class TestSubmitBudgetG6(unittest.TestCase):
    """harness/guards.py — the one-POST-per-alpha ledger. Read-only: submit_allowed() never writes,
    and reserve_submit()/record_submit() are deliberately NOT called here."""

    @staticmethod
    def _log_rows():
        rows = []
        if SUBMIT_LOG.exists():
            for line in open(SUBMIT_LOG):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
        return rows

    def test_live_alphas_cannot_be_resubmitted(self):
        for a in LIVE:
            with self.subTest(alpha=a):
                ok, why = submit_allowed(a, f"__test_family_{a}__")
                self.assertFalse(ok, f"{a} is ACTIVE and the budget ledger would let it POST again")

    def test_alphas_the_platform_403d_cannot_be_resubmitted(self):
        """G6 gives each alpha ONE POST ever, and a 403 carrying a FAIL is the platform JUDGING
        that POST — spent, alpha dead.

        A 403 whose checks hold only ERROR is a different animal: the platform could not COMPUTE
        the check. P0OLx0zp was 403'd on 2026-08-01 with a lone PROD_CORRELATION:ERROR while the
        account was rate-limited, then measured prod 0.6549 / breach 0 / self 0.6549 minutes later
        and is still UNSUBMITTED platform-side. Counting that as an adjudication destroys a healthy
        gem over a transient hiccup, so those slots are released — but the distinction is read from
        the parsed checks, never from a substring, and a body with any FAIL stays blocked."""
        import submit_alphas as _sa
        rows = [r for r in self._log_rows() if str(r.get("status")) == "403" and r.get("alpha")]
        self.assertTrue(rows, "no 403 in the submit log — fixture lost")
        judged = sorted({r["alpha"] for r in rows if not _sa._only_errors(str(r.get("body", "")))})
        self.assertTrue(judged, "every logged 403 was an ERROR-only body — fixture lost its teeth")
        for a in judged:
            with self.subTest(alpha=a):
                ok, why = submit_allowed(a, f"__test_family_{a}__")
                self.assertFalse(ok, f"{a} was JUDGED by a 403 (its body carries a FAIL) and the "
                                     f"ledger would allow another POST: {why}")

    def test_ledger_survives_a_corrupt_line(self):
        """A half-written ledger line must not crash the gate open or closed."""
        import harness.guards as g
        tmp = pathlib.Path(tempfile.mkdtemp()) / "budget.jsonl"
        tmp.write_text('{"alpha": "AAA", "family": "f", "date": "2020-01-01"}\n'
                       'not json at all\n'
                       '{"alpha": "BBB"}\n')
        orig = g.SUB
        g.SUB = tmp
        self.addCleanup(lambda: setattr(g, "SUB", orig))
        self.assertFalse(g.submit_allowed("AAA", "f")[0])
        self.assertTrue(g.submit_allowed("CCC", "other")[0])


# =========================================================================== 4. BANNED FIELDS
class TestBannedFields(unittest.TestCase):

    @staticmethod
    def _banned():
        b = json.load(open(BANNED))
        return set(b["banned_fields"] if isinstance(b, dict) else b)

    @staticmethod
    def _latest_targets():
        files = glob.glob(str(ROOT / "state/funnel/*targets*.json"))
        return pathlib.Path(max(files, key=os.path.getmtime))

    def test_latest_batch_uses_no_banned_field(self):
        banned, path = self._banned(), self._latest_targets()
        rows = json.load(open(path))
        self.assertIsInstance(rows, list)
        offenders = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", r.get("formula") or ""))
            for f in toks & banned:
                offenders.setdefault(f, []).append(r.get("old_id"))
        self.assertEqual(offenders, {}, f"{path.name} uses banned fields: "
                                        f"{ {k: v[:3] for k, v in offenders.items()} }")

    def test_banned_list_is_loadable_and_non_empty(self):
        """A banned list that silently reads as empty is a filter that passes everything."""
        self.assertGreater(len(self._banned()), 0)


# =========================================================================== 5. AUTOLOOP DRIVER
class TestDriver(unittest.TestCase):
    """tools/autoloop/driver.py — the process that decides, unattended, what to submit."""

    def setUp(self):
        self._saved = {k: getattr(driver, k) for k in ("PC", "PEND", "session", "fetch_corr",
                                                       "subprocess", "budget_used", "log",
                                                       "stream_busy")}
        self.addCleanup(lambda: [setattr(driver, k, v) for k, v in self._saved.items()])
        tmp = pathlib.Path(tempfile.mkdtemp())
        driver.PC = tmp / "prod_corr_measured.json"       # never repo state
        driver.PEND = tmp / "corr_pending.json"           # measure() parks unmeasured ids here
        driver.session = lambda: NoNetworkSession()
        driver.log = lambda *a, **k: None          # the driver's progress log is not under test

    def test_measure_treats_still_computing_self_corr_as_unmeasured(self):
        """driver.measure()'s guard is `sj.get("records") is None`, but the platform's
        still-computing reply is `records: []`, and `[] is None` is False. self_maxcorr then returns
        None, `sc is None` reads as 'no self-correlation', and the alpha is logged '*** CLEAN' and
        handed to submit(). This is the exact `[] is not None` defect that tools/submit_alphas.py
        was fixed for, reintroduced one layer up."""
        driver.fetch_corr = lambda s, aid, kind, budget=90.0: (
            prod_payload(max_corr=0.5) if kind == "prod" else self_payload(None))
        clean, store, _ = driver.measure(["FAKE0001"], {})
        self.assertEqual(clean, [], "an alpha whose self-corr was still computing was marked CLEAN "
                                    "and queued for submission")
        self.assertFalse(store.get("FAKE0001", {}).get("corr_ok", False))

    def test_measure_accepts_a_fully_measured_clean_alpha(self):
        driver.fetch_corr = lambda s, aid, kind, budget=90.0: (
            prod_payload(max_corr=0.42) if kind == "prod" else self_payload([0.31]))
        clean, store, _ = driver.measure(["FAKE0002"], {})
        self.assertEqual([a for _, a, _ in clean], ["FAKE0002"], "FALSE BLOCK on a clean alpha")

    def test_measure_rejects_a_correlated_alpha(self):
        driver.fetch_corr = lambda s, aid, kind, budget=90.0: (
            prod_payload(max_corr=0.95) if kind == "prod" else self_payload([0.31]))
        clean, _, _ = driver.measure(["FAKE0003"], {})
        self.assertEqual(clean, [], "prod-corr 0.95 was accepted as clean")

    def test_measure_rejects_an_unfetchable_alpha(self):
        driver.fetch_corr = lambda s, aid, kind, budget=90.0: None
        clean, store, _ = driver.measure(["FAKE0004"], {})
        self.assertEqual(clean, [])
        self.assertNotIn("FAKE0004", store)

    def test_unmeasured_alpha_is_parked_and_resolved_in_a_later_round(self):
        """Correlations are computed lazily, so a fresh alpha usually reads UNMEASURED. Dropping it
        there threw the alpha away: 27 minutes of the 2026-07-31 run went into 3-minute waits that
        returned nothing, and every one of those gate-passers was then invisible to the ledger and
        to submit(). measure() must PARK it and resolve it on a later call -- including a call with
        no passers of its own, which is exactly when the queue would otherwise strand forever."""
        driver.fetch_corr = lambda s, aid, kind, budget=90.0: None
        clean, store, measured = driver.measure(["FAKE0005"], {"FAKE0005": {"sharpe": 2.4}})
        self.assertEqual((clean, measured), ([], []))
        self.assertIn("FAKE0005", json.load(open(driver.PEND)), "unmeasured alpha was dropped, not parked")

        driver.fetch_corr = lambda s, aid, kind, budget=90.0: (
            prod_payload(max_corr=0.42) if kind == "prod" else self_payload([0.31]))
        clean, store, measured = driver.measure([], {})          # no passers THIS round
        self.assertEqual([a for a, _ in measured], ["FAKE0005"], "parked alpha was never retried")
        self.assertEqual(measured[0][1].get("sharpe"), 2.4,
                         "the parked result row was lost, so the ledger row would have no metrics")
        self.assertEqual([a for _, a, _ in clean], ["FAKE0005"])
        self.assertEqual(json.load(open(driver.PEND)), {}, "resolved alpha stayed in the queue")

    def test_parked_alpha_is_dropped_after_the_retry_cap(self):
        """Parking without a cap is a leak: an id that can never resolve is retried at the FULL
        aged budget every round, forever. Two stray test fixtures left in the live queue cost the
        driver 6 minutes a round before anyone noticed, and a genuinely dead alpha would do the
        same indefinitely."""
        driver.fetch_corr = lambda s, aid, kind, budget=90.0: None
        for i in range(driver.MAX_PARK_TRIES):
            driver.measure(["FAKE0006"] if i == 0 else [], {"FAKE0006": {"sharpe": 1.9}})
            self.assertIn("FAKE0006", json.load(open(driver.PEND)),
                          f"dropped too early, after {i + 1} tries")
        driver.measure([], {})
        self.assertNotIn("FAKE0006", json.load(open(driver.PEND)),
                         "an unmeasurable alpha stayed queued past the retry cap")

    def test_sim_stall_timeout_is_not_a_half_hour_of_dead_waiting(self):
        """run_multisim gives up only after N seconds of SILENCE, and that wait is paid in full by
        every batch that does not complete. At 1800s, PE round 3 journaled 83/93 and then sat idle
        for 30 minutes with 1.56h left on the deadline. The grace loop after run_sim already
        re-harvests stragglers, so this must stay far below that."""
        seen = {}

        def run(cmd, **kw):
            seen["cmd"] = [str(c) for c in cmd]

            class R:
                returncode, stdout, stderr = 0, "journaled 1/1", ""
            return R()

        driver.subprocess = type("S", (), {"run": staticmethod(run)})
        driver.stream_busy = lambda: False
        driver.run_sim("/tmp/batch.json")
        i = seen["cmd"].index("--stall-timeout")
        self.assertLessEqual(float(seen["cmd"][i + 1]), 900,
                             "stall timeout is back above 15 minutes of dead waiting per batch")

    def test_measure_stops_paying_once_the_correlation_service_is_clearly_down(self):
        """Correlation availability is a property of the SERVICE, not the alpha: when it is
        computing, every id returns empty. Paying the full budget per alpha to rediscover that cost
        PU round 1 twelve minutes across 18 consecutive misses. After BREAK_AFTER misses the rest
        must be parked for free -- and crucially WITHOUT burning a park try, or an outage would
        exhaust MAX_PARK_TRIES and discard alphas that were never actually looked at."""
        calls = []

        def counting_fetch(s, aid, kind, budget=90.0):
            calls.append(aid)
            return None

        driver.fetch_corr = counting_fetch
        triggered = []

        class TriggerSession(NoNetworkSession):
            def get(self, url, **kw):
                triggered.append(url)
                return type("R", (), {"status_code": 200, "text": "", "headers": {}})()

        driver.session = lambda: TriggerSession()
        ids = [f"FAKE10{i:02d}" for i in range(12)]
        driver.measure(ids, {a: {"sharpe": 1.9} for a in ids})
        # Skipped ids must still get ONE cheap request each: these recordsets are computed on
        # demand, so an id that is never requested never starts computing and parks forever.
        skipped_ids = [a for a in ids if a not in set(calls)]
        for a in skipped_ids:
            self.assertTrue(any(a in u for u in triggered),
                            f"{a} was parked without ever triggering its recordset computation")
        self.assertLessEqual(len(set(calls)), driver.BREAK_AFTER,
                             f"kept paying after the service was clearly down: probed {len(set(calls))} ids")
        parked = json.load(open(driver.PEND))
        self.assertEqual(len(parked), len(ids), "skipped alphas were dropped instead of parked")
        skipped = [a for a in ids if a not in set(calls)]
        self.assertTrue(all(parked[a]["tries"] == 0 for a in skipped),
                        "an alpha the breaker never probed still had a park try deducted")

    def _submit_returning(self, stdout):
        seen = {}

        def run(cmd, **kw):
            seen["cmd"] = cmd
            return types.SimpleNamespace(stdout=stdout, stderr="", returncode=0)

        driver.subprocess = types.SimpleNamespace(run=run)
        driver.budget_used = lambda: 0
        return seen

    def test_a_403_rejection_is_not_counted_as_a_submission(self):
        """driver.submit() decides success with `if "SUBMITTED" in out`. The platform's
        already-submitted rejection body is
        {"is":{"checks":[{"name":"ALREADY_SUBMITTED","result":"FAIL"}]}} — printed verbatim by
        submit_alphas.py on the REJECTED line — and "ALREADY_SUBMITTED" contains "SUBMITTED". The
        real 403 line below is copied from state/funnel/submit_log.jsonl (Xg8oQJRl)."""
        out = ('  Xg8oQJRl: pre-submit corr check -> fresh: prod breach 2 (max 0.8), self 0.41\n'
               'Xg8oQJRl: REJECTED [403] '
               '{"is":{"checks":[{"name":"ALREADY_SUBMITTED","result":"FAIL"}]}}\n')
        self._submit_returning(out)
        done = driver.submit([(0.5, "Xg8oQJRl", {"old_id": "xb_n6p4_w50_p35_t02_179"})])
        self.assertEqual(done, [], "a 403 ALREADY_SUBMITTED rejection was recorded as a successful "
                                   "submit")

    def test_a_plain_rejection_is_not_counted_as_a_submission(self):
        self._submit_returning("pwKZl6Zg: REJECTED [403] {\"is\":{\"checks\":[]}}\n")
        self.assertEqual(driver.submit([(0.5, "pwKZl6Zg", {"old_id": "i49_x_061"})]), [])

    def test_a_real_submission_is_counted(self):
        self._submit_returning("QP99gYLM: SUBMITTED ✓ [200] {\"is\":{\"checks\":[]}}\n")
        self.assertEqual(driver.submit([(0.5, "QP99gYLM", {"old_id": "d16_x_042"})]), ["QP99gYLM"])

    def test_submit_respects_the_daily_cap(self):
        self._submit_returning("X: SUBMITTED ✓ [200]\n")
        driver.budget_used = lambda: driver.DAILY_CAP
        self.assertEqual(driver.submit([(0.5, "AAA1", {"old_id": "a_1"})]), [],
                         "the daily submit cap did not stop a submission")

    def test_one_submit_per_formula_family(self):
        """iter49 burned three lifetime POSTs on three alphas that differed only by truncation."""
        self._submit_returning("X: SUBMITTED ✓ [200]\n")
        clean = [(0.1, "AAA1", {"old_id": "i49_mlabel_pw20_STAT_d14_t2_061"}),
                 (0.2, "AAA2", {"old_id": "i49_mlabel_pw20_STAT_d14_t2_062"}),
                 (0.3, "AAA3", {"old_id": "i49_mlabel_pw20_STAT_d14_t2_063"})]
        self.assertEqual(len(driver.submit(clean)), 1)

    def test_driver_scores_with_the_canonical_gate_module(self):
        """The driver must not grow its own copy of the rule; that divergence is the whole story."""
        self.assertIs(driver.gates, gates)
        src = (ROOT / "tools/autoloop/driver.py").read_text()
        self.assertNotIn("def zero_fail", src, "driver.py defines its own zero_fail")


if __name__ == "__main__":
    # The repo's prevailing idiom is json.load(open(path)); on CPython 3.14 that emits a
    # ResourceWarning per call and buries the test results. It is not what this suite measures.
    import warnings
    warnings.simplefilter("ignore", ResourceWarning)
    # warnings=False stops unittest's runner from resetting the filter above. The repo's prevailing
    # json.load(open(path)) idiom emits a ResourceWarning per call and otherwise buries the results.
    unittest.main(warnings=False)      # honours -v / -q / a test name on the command line
