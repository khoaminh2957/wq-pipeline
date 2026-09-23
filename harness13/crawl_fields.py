#!/usr/bin/env python3
"""R4 / L2 — crawl the platform's field catalogue for every (region, universe, delay) triple.

WHAT LICENSES THIS MODULE
  DESIGN.md D1 line 8, verbatim: "R4 FIELDS: low-usercount+high-coverage+ratio+empty-cell catalog;
  gate: forall ID resolved by live API call, >=1 field/empty cell."
  DESIGN.md D3 line 35 (L2), verbatim: "src fetched/rc/fields/USA_TOP3000_d1.jsonl".
  DECISIONS.md Q3: no region / universe / delay is pinned -- the archive selects count==0 cells
  itself -- so a catalogue covering one triple cannot serve it.
  REQ-L2-09 (state/harness13/r1_reqs.json) asks for at least 16 catalogue files on disk;
  REQ-D1-07 asks that every catalogue row carry the HTTP status and timestamp of the live call
  that resolved it; REQ-D1-08 asks for at least one field per count==0 pyramid cell.

MEASURED PRECONDITION -- POST-HOC, read off this disk on 2026-08-10, no API call involved:
  `ls fetched/rc/fields/` returns exactly ONE file, USA_TOP3000_d1.jsonl, 85,612 rows / 52 MB,
  written by tools/fetch_all_rc.py. fetched/rc/combos.json lists 33 (region, universe, delay)
  triples discovered from OPTIONS /simulations. state/pyramid_cell_counts.json covers USA d1 only.

WHAT A ROW'S PROVENANCE MEANS, EXACTLY (REQ-D1-07)
  Every emitted row carries `resolved_http`, `resolved_at` and `resolved_url` of THE PAGE REQUEST
  THAT RETURNED IT -- a GET on /data-fields, optionally narrowed by `dataset.id`. That is a live
  BRAIN call which returned the field id in a 200 body. It is NOT a per-field GET
  /data-fields/<id>: at the account's 60 requests/minute, resolving each id of a multi-million-row
  crawl one at a time is not reachable in the round, and that choice is recorded here rather than
  hidden. `resolved_at` is the client-side clock reading taken when the response arrived.
  The crawler never writes a row it did not receive: pages are buffered in memory and the file is
  published with os.replace only after the server's own `count` for that query has been reached,
  so a throttled or truncated crawl leaves NO file rather than a short one (the same rule
  tools/fetch_all_rc.py:188 states: "write only after BOTH paged() calls completed & verified").
  On resume, an existing file is read back and any row lacking a 200 + timestamp is DROPPED from
  the aggregate catalogue and counted in `dropped_no_provenance`; today's USA_TOP3000_d1.jsonl
  predates this schema and will drop entirely until it is re-crawled with --refresh.

THE ENDPOINT'S `count` SATURATES -- POST-HOC, measured by other tools in this repo, not here:
  tools/crawl_fields.py:21-24 records that `/data-fields` reports exactly 10000 for several
  categories, which is the ceiling and not a measurement; tools/fetch_all_rc.py:173-181 handles it
  by paging per dataset instead. MECHANISM: UNKNOWN for why the endpoint reports the ceiling.
  This module copies the handling, not an explanation: when the unfiltered probe reports >= 10000
  it pages /data-sets and then /data-fields per `dataset.id`.

RATE AND RETRY -- EX-ANTE, taken from documentation before any request was made here:
  PAPERS.md line 71, verbatim: retries are "selfish", 5 deep = 243x amplification; token-bucket-
  limit retries at ONE layer; jitter; never retry client errors. The ONE layer here is
  `Crawler.request`; `paged`, `crawl_triple` and `crawl` never retry anything. The default budget
  is 60 requests/minute with burst 1 -- the account limit named in the R4 brief -- and that budget
  is SHARED with whatever else holds the same cookie.

DAILY vs CONCURRENT 429
  tools/daily_budget.py:10-14 records, verbatim: "Probing the identical request every 20 seconds
  with the daily allowance exhausted returned DAILY, then CONCURRENT, then CONCURRENT, then
  CONCURRENT." So the body is a report of whichever limit check fired, not a diagnosis.
  MECHANISM: UNKNOWN. `classify_429` therefore reads the body, and `LimitLatch` latches DAILY
  one-way: a later CONCURRENT body may never reopen the day. A DAILY verdict aborts the crawl
  instead of backing off and re-probing. Those bodies were measured on POST /simulations; whether
  GET /data-fields ever emits either one is UNKNOWN -- no request was made while writing this
  module -- so a 429 matching neither is classified RATE and retried on Retry-After.

DRY-RUN IS THE DEFAULT (D10 SIM-FIRST)
  --dry-run is on unless --live is passed. It runs the identical crawl code against `FakeClient`,
  which opens no socket and imports no HTTP library, on a virtual clock, and writes under
  state/harness13/dryrun/crawl_fields/ -- never into fetched/rc/fields/ and never into
  state/harness13/field_catalog.jsonl, so no gate can ever read simulated rows as live evidence.
  Every dry-run row carries "label": "SIMULATED:crawl_fields" and every dry-run stdout line starts
  with "SIMULATED:". Two dry-runs at the same seed produce byte-identical files.

NO SUBMIT PATH. The live transport exposes GET only; this module issues no POST of any kind.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
API = "https://api.worldquantbrain.com"

PAGE = 50                       # page size used by tools/fetch_all_rc.py:146 for the same endpoints
COUNT_CAP = 10000               # the endpoint's own ceiling (tools/crawl_fields.py:37); not a count
JITTER_S = 0.25                 # upper bound of the seeded jitter added to every wait
SIM_EPOCH = 1786300000.0        # fixed origin of the dry-run virtual clock; carries no meaning
SIM_LABEL = "SIMULATED:crawl_fields"

TRIPLES_PATH = ROOT / "fetched/rc/combos.json"
LIVE_FIELDS_DIR = ROOT / "fetched/rc/fields"
LIVE_CATALOG = ROOT / "state/harness13/field_catalog.jsonl"
DRYRUN_ROOT = ROOT / "state/harness13/dryrun/crawl_fields"
CELL_COUNTS = ROOT / "state/pyramid_cell_counts.json"


class CrawlError(RuntimeError):
    """Any failure that leaves the requested triple uncrawled."""


class AuthExpired(CrawlError):
    """401 -- the cookie is dead. Minting a new one belongs to D4/R6, not to a crawler."""


class DailyLimitReached(CrawlError):
    """A 429 whose body named the DAILY limit. Stop; do not re-probe until 00:00 ET."""


class Truncated(CrawlError):
    """The server's own `count` was not reached, so no file is published for this triple."""


# ---------------------------------------------------------------------------- clocks

class SystemClock:
    def now(self):
        return time.time()

    def sleep(self, seconds):
        if seconds > 0:
            time.sleep(seconds)


class VirtualClock:
    """Dry-run clock: sleeping advances a counter, so a rehearsal costs no wall time."""

    def __init__(self, start=SIM_EPOCH):
        self._t = float(start)

    def now(self):
        return self._t

    def sleep(self, seconds):
        self._t += max(0.0, float(seconds))


# ---------------------------------------------------------------------------- rate + limits

class TokenBucket:
    """One bucket, `rpm` requests per minute, `burst` capacity, seeded jitter on every wait."""

    def __init__(self, rpm=60, burst=1, clock=None, rng=None):
        self.rate = float(rpm) / 60.0
        self.capacity = float(burst)
        self.tokens = float(burst)
        self.clock = clock or SystemClock()
        self.rng = rng or random.Random(0)
        self._last = self.clock.now()

    def take(self):
        while True:
            now = self.clock.now()
            self.tokens = min(self.capacity, self.tokens + (now - self._last) * self.rate)
            self._last = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            self.clock.sleep((1.0 - self.tokens) / self.rate + self.rng.random() * JITTER_S)


def classify_429(body):
    """"DAILY" | "CONCURRENT" | "RATE" from the response body. Reading only; see the module doc."""
    up = str(body or "").upper()
    if "DAILY" in up:
        return "DAILY"
    if "CONCURRENT" in up:
        return "CONCURRENT"
    return "RATE"


class LimitLatch:
    """One-way latch: once DAILY is seen, a later CONCURRENT body does not reopen the day."""

    def __init__(self):
        self.verdict = None

    def observe_429(self, body):
        kind = classify_429(body)
        if self.verdict != "DAILY":
            self.verdict = kind
        return kind


# ---------------------------------------------------------------------------- transports

class Response:
    __slots__ = ("status_code", "headers", "text", "_payload")

    def __init__(self, status_code, payload=None, headers=None, text=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload
        self.text = text if text is not None else (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is not None:
            return self._payload
        return json.loads(self.text)


def _live_session():
    """The repo's own cookie session, imported as a library from tools/fetch_prod_corr.py:15-21.

    Imported lazily so this module imports cleanly with no BRAIN credentials and HOME=/nonexistent,
    and so the dry-run path never imports an HTTP library at all.
    tools/fetch_all_rc.py's session is NOT importable: it loads the cookie pickle and mkdirs at
    module import time (lines 26-30). tools/daily_budget.py's DAILY-limit ledger is deliberately
    NOT imported either: its module-level `import submit_alphas` would pull the real-account submit
    POST into this process, and no submit path may exist under harness13/.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tools.fetch_prod_corr import session
    return session()


class LiveClient:
    """GET-only transport over the account cookie. It never retries and it never POSTs."""

    def __init__(self, session=None, timeout=60):
        self._s = session if session is not None else _live_session()
        self.timeout = timeout

    def get(self, path, params):
        r = self._s.get(API + path, params=params, timeout=self.timeout)
        return Response(r.status_code, text=r.text, headers=dict(r.headers))


def _cell_names():
    """category id -> pyramid cell name, reused from tools/crawl_fields.py:39-43."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tools.crawl_fields import NAMES
    return NAMES


class FakeClient:
    """Offline transport for the rehearsal. No socket, no HTTP library, seeded content.

    It serves the same two endpoints with the same paging protocol as the live one, so --dry-run
    exercises the real crawl code rather than a shortcut. Faults are injected on fixed request
    indices per triple (one CONCURRENT 429 carrying Retry-After, one 500) so the single retry layer
    is rehearsed; `n_per_cell` fields are minted for every pyramid category name, and the first
    triple in sorted order reports a count at the endpoint ceiling so the per-dataset branch is
    rehearsed too.
    """

    def __init__(self, triples, seed=0, n_per_cell=3, inject_faults=True):
        self.seed = seed
        self.n_per_cell = n_per_cell
        self.inject_faults = inject_faults
        self.sockets_opened = 0
        self._cap_triple = sorted(tuple(t) for t in triples)[0] if triples else None
        self._cache = {}
        self._seen = {}

    # -- content ---------------------------------------------------------------
    def _rows(self, triple):
        key = tuple(triple)
        if key in self._cache:
            return self._cache[key]
        rg, un, dl = key
        rng = random.Random("%s|%s|%s|%s" % (self.seed, rg, un, dl))
        rows = []
        for cat_id, cat_name in sorted(_cell_names().items()):
            for i in range(self.n_per_cell):
                rows.append({
                    "id": "sim_%s_%s_%s_d%s_%02d" % (cat_id, rg.lower(), un.lower(), dl, i),
                    "description": "SIMULATED %s field %d for %s/%s/d%s" % (cat_name, i, rg, un, dl),
                    "dataset": {"id": "sim_ds_%s_%d" % (cat_id, i % 3),
                                "name": "SIMULATED %s dataset %d" % (cat_name, i % 3)},
                    "category": {"id": cat_id, "name": cat_name},
                    "subcategory": {"id": "%s-sub%d" % (cat_id, i % 2),
                                    "name": "SIMULATED %s sub %d" % (cat_name, i % 2)},
                    "type": "MATRIX" if i % 2 == 0 else "VECTOR",
                    "coverage": round(rng.uniform(0.30, 0.99), 4),
                    "dateCoverage": round(rng.uniform(0.30, 0.99), 4),
                    "userCount": rng.randint(0, 40),
                    "alphaCount": rng.randint(0, 40),
                    "pyramidMultiplier": 1.0,
                    "themes": [],
                    "dateCreated": "20%02d-%02d-01" % (16 + i % 10, 1 + i % 12),
                    "region": rg, "universe": un, "delay": dl,
                })
        self._cache[key] = rows
        return rows

    # -- protocol --------------------------------------------------------------
    def get(self, path, params):
        triple = (params["region"], params["universe"], int(params["delay"]))
        n = self._seen.get(triple, 0) + 1
        self._seen[triple] = n
        if self.inject_faults and n == 2:
            return Response(429, payload={"detail": "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"},
                            headers={"Retry-After": "1"})
        if self.inject_faults and n == 5:
            return Response(503, text="SIMULATED upstream error")

        rows = self._rows(triple)
        if path == "/data-sets":
            ds = sorted({r["dataset"]["id"]: dict(r["dataset"]) for r in rows}.values(),
                        key=lambda d: d["id"])
            return self._page(ds, params)
        if params.get("limit") == 1 and "dataset.id" not in params:
            # the unfiltered probe: one designated triple reports the ceiling, not a count
            count = COUNT_CAP if triple == self._cap_triple else len(rows)
            return Response(200, payload={"count": count, "results": rows[:1]})
        if "dataset.id" in params:
            rows = [r for r in rows if r["dataset"]["id"] == params["dataset.id"]]
        return self._page(rows, params)

    @staticmethod
    def _page(rows, params):
        off = int(params.get("offset", 0))
        lim = int(params.get("limit", PAGE))
        page = [dict(r) for r in rows[off:off + lim]]     # copies: the caller stamps provenance
        return Response(200, payload={"count": len(rows), "results": page})


# ---------------------------------------------------------------------------- crawler

def _url(path, params):
    return API + path + "?" + "&".join("%s=%s" % (k, params[k]) for k in sorted(params))


class Crawler:
    """The crawl, with exactly one retry layer (`request`) and one rate gate (`bucket`)."""

    def __init__(self, client, clock=None, rng=None, rpm=60, burst=1, max_attempts=3,
                 simulated=False):
        self.client = client
        self.clock = clock or SystemClock()
        self.rng = rng or random.Random(0)
        self.bucket = TokenBucket(rpm=rpm, burst=burst, clock=self.clock, rng=self.rng)
        self.max_attempts = max_attempts
        self.simulated = simulated
        self.latch = LimitLatch()
        self.calls = 0
        self.retries = 0

    def _retry_after(self, resp, attempt):
        """Retry-After is a STRING in the header map -- cast it (tools/funnel/resilience_lib.py:73)."""
        try:
            wait = float(resp.headers.get("Retry-After") or 0)
        except (TypeError, ValueError):
            wait = 0.0
        if wait <= 0:
            wait = 2.0 ** attempt
        return wait + self.rng.random() * JITTER_S

    def request(self, path, params):
        """THE ONLY retry layer. Returns (Response, arrival_timestamp). Never retries a non-429 4xx."""
        for attempt in range(self.max_attempts):
            self.bucket.take()
            self.calls += 1
            resp = self.client.get(path, params)
            at = self.clock.now()
            if resp.status_code == 200:
                return resp, at
            if resp.status_code == 401:
                raise AuthExpired("401 on %s -- session expired; run tools/auth_only.py" % path)
            if resp.status_code == 429:
                kind = self.latch.observe_429(resp.text)
                if kind == "DAILY":
                    raise DailyLimitReached(
                        "429 DAILY on %s -- stopping; the allowance resets at 00:00 ET" % path)
                self.retries += 1
                self.clock.sleep(self._retry_after(resp, attempt))
                continue
            if resp.status_code >= 500:
                self.retries += 1
                self.clock.sleep(2.0 ** attempt + self.rng.random() * JITTER_S)
                continue
            raise CrawlError("%s on %s %s -- 4xx is not retried" % (resp.status_code, path, params))
        raise CrawlError("%d attempts exhausted on %s %s" % (self.max_attempts, path, params))

    def paged(self, path, base, triple):
        """Every row of a query, or raise. A short page before `count` is a truncation, never a stop."""
        rows, off, got, count = [], 0, None, None
        while True:
            params = dict(base, limit=PAGE, offset=off)
            resp, at = self.request(path, params)
            body = resp.json()
            if count is None:
                count = body.get("count")
                if count is None:
                    raise CrawlError("no count in response: %s %s" % (path, base))
            results = body.get("results") or []
            for row in results:
                row["_region"], row["_universe"], row["_delay"] = triple
                row["resolved_http"] = resp.status_code
                row["resolved_at"] = round(at, 3)
                row["resolved_url"] = _url(path, params)
                if self.simulated:
                    row["label"] = SIM_LABEL
                rows.append(row)
            got = len(rows)
            off += PAGE
            if got >= count:
                return rows, count
            if not results:
                raise Truncated("%s %s stopped at %d/%s" % (path, base, got, count))

    def crawl_triple(self, triple):
        """All rows of one (region, universe, delay), received in 200 responses. Raises otherwise."""
        rg, un, dl = triple
        base = {"region": rg, "universe": un, "delay": dl, "instrumentType": "EQUITY"}
        probe, _ = self.request("/data-fields", dict(base, limit=1, offset=0))
        count = probe.json().get("count") or 0
        if count >= COUNT_CAP:
            datasets, _ = self.paged("/data-sets", base, triple)
            rows = []
            for d in datasets:
                part, _ = self.paged("/data-fields", dict(base, **{"dataset.id": d["id"]}), triple)
                rows.extend(part)
            return rows, count
        rows, _ = self.paged("/data-fields", base, triple)
        return rows, count


# ---------------------------------------------------------------------------- artifacts

def load_triples(path=TRIPLES_PATH):
    """[(region, universe, delay)] the archive may select, from the OPTIONS /simulations discovery."""
    raw = json.loads(pathlib.Path(path).read_text())
    return sorted((str(r), str(u), int(d)) for r, u, d in raw)


def triple_filename(triple):
    return "%s_%s_d%d.jsonl" % (triple[0], triple[1], triple[2])


def _write_atomic(path, lines):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with open(tmp, "w") as fh:
        for line in lines:
            fh.write(line + "\n")
    os.replace(tmp, path)


def _resolved(row):
    """True iff this row carries the live-call evidence REQ-D1-07 demands."""
    return row.get("resolved_http") == 200 and bool(row.get("resolved_at"))


def catalog_rows(rows, triple, per_cell):
    """Per-cell candidates for the aggregate catalogue: highest coverage first, ties by field id.

    Ranking on coverage is a CHOICE, not a finding: DESIGN.md D1 line 8 names "high-coverage" and
    D3 line 35 pins LOW_USERCOUNT_PRIOR at 0 until an A/B is run, so userCount is carried in the
    row and is not part of the sort key. `cell_field_total` records how many fields the crawl saw
    in that cell, so the `per_cell` cap is visible in the artifact instead of hidden.
    """
    by_cell = {}
    for row in rows:
        if not _resolved(row):
            continue
        cell = (row.get("category") or {}).get("name")
        if not cell:
            continue
        by_cell.setdefault(cell, []).append(row)
    out = []
    for cell, cell_rows in sorted(by_cell.items()):
        ranked = sorted(cell_rows, key=lambda r: (-(r.get("coverage") or 0.0), str(r.get("id"))))
        keep = ranked if per_cell <= 0 else ranked[:per_cell]
        for rank, row in enumerate(keep):
            entry = {
                "field_id": row.get("id"),
                "region": triple[0], "universe": triple[1], "delay": triple[2],
                "cell": cell,
                "subcategory": (row.get("subcategory") or {}).get("name"),
                "dataset": (row.get("dataset") or {}).get("id"),
                "coverage": row.get("coverage"),
                "userCount": row.get("userCount"),
                "type": row.get("type"),
                "selection_rank": rank,
                "cell_field_total": len(cell_rows),
                "resolved_http": row["resolved_http"],
                "resolved_at": row["resolved_at"],
                "resolved_url": row.get("resolved_url"),
            }
            if row.get("label"):
                entry["label"] = row["label"]
            out.append(entry)
    return out


def merge_catalog(per_triple, per_cell):
    """Collapse per-triple candidates onto the (region, delay, cell) key the pyramid counts use."""
    by_key = {}
    for entries in per_triple:
        for e in entries:
            by_key.setdefault((e["region"], e["delay"], e["cell"]), []).append(e)
    merged = []
    for key in sorted(by_key):
        seen, ranked = set(), []
        for e in sorted(by_key[key],
                        key=lambda r: (-(r["coverage"] or 0.0), r["universe"], str(r["field_id"]))):
            if e["field_id"] in seen:
                continue
            seen.add(e["field_id"])
            ranked.append(e)
        total = len(ranked)
        keep = ranked if per_cell <= 0 else ranked[:per_cell]
        for rank, e in enumerate(keep):
            e = dict(e, selection_rank=rank, cell_field_total=total)
            merged.append(e)
    return merged


def read_back(path):
    """Rows of an existing catalogue file, keeping only those carrying live-call provenance."""
    kept, dropped = [], 0
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                dropped += 1
                continue
            if _resolved(row):
                kept.append(row)
            else:
                dropped += 1
    return kept, dropped


def empty_cell_report(catalog, counts_path=CELL_COUNTS):
    """Which count==0 pyramid cells the catalogue covers (REQ-D1-08). Reporting only, no verdict."""
    path = pathlib.Path(counts_path)
    if not path.is_file():
        return {"counts_file": str(path), "present": False}
    data = json.loads(path.read_text())
    pairs = data.get("pairs") or data.get("by_pair")
    entries = list(pairs.values()) if isinstance(pairs, dict) else (pairs or [data])
    empty = {(e["region"], int(e["delay"]), cell)
             for e in entries for cell, n in (e.get("counts") or {}).items() if n == 0}
    have = {(r["region"], int(r["delay"]), r["cell"]) for r in catalog}
    missing = sorted(empty - have)
    return {"counts_file": str(path), "present": True, "empty_cells": len(empty),
            "covered": len(empty) - len(missing), "missing": missing}


# ---------------------------------------------------------------------------- driver

def crawl(triples, crawler, out_dir, catalog_path, per_cell=50, refresh=False,
          counts_path=CELL_COUNTS, log=print):
    """Crawl each triple to <out_dir>/<REGION>_<UNIVERSE>_d<DELAY>.jsonl, then write the catalogue.

    Returns a summary dict. Raises nothing on a per-triple failure: the triple is recorded in
    `failed` and left with no file, which is the only honest state for an unfinished crawl.
    AuthExpired and DailyLimitReached stop the whole run -- neither clears by trying again.
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"triples": len(triples), "written": [], "reused": [], "failed": [],
               "rows": 0, "dropped_no_provenance": 0, "calls": 0, "retries": 0,
               "limit_verdict": None, "stopped": None}
    per_triple = []

    for triple in triples:
        dest = out_dir / triple_filename(triple)
        if dest.is_file() and not refresh:
            rows, dropped = read_back(dest)
            summary["reused"].append(dest.name)
            summary["dropped_no_provenance"] += dropped
            log("reuse  %-28s rows=%d dropped_no_provenance=%d" % (dest.name, len(rows), dropped))
        else:
            try:
                rows, count = crawler.crawl_triple(triple)
            except (AuthExpired, DailyLimitReached) as exc:
                summary["stopped"] = str(exc)
                break
            except CrawlError as exc:
                summary["failed"].append({"triple": list(triple), "error": str(exc)})
                log("FAIL   %-28s %s" % (dest.name, exc))
                continue
            _write_atomic(dest, [json.dumps(r, ensure_ascii=False) for r in rows])
            summary["written"].append(dest.name)
            log("write  %-28s rows=%d server_count=%s" % (dest.name, len(rows), count))
        summary["rows"] += len(rows)
        per_triple.append(catalog_rows(rows, triple, per_cell))

    catalog = merge_catalog(per_triple, per_cell)
    _write_atomic(catalog_path, [json.dumps(r, ensure_ascii=False) for r in catalog])
    summary["catalog_path"] = str(catalog_path)
    summary["catalog_rows"] = len(catalog)
    summary["calls"] = crawler.calls
    summary["retries"] = crawler.retries
    summary["limit_verdict"] = crawler.latch.verdict
    summary["empty_cells"] = empty_cell_report(catalog, counts_path)
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true",
                    help="issue real BRAIN requests; without it the run is a dry rehearsal")
    ap.add_argument("--dry-run", action="store_true", default=True, help=argparse.SUPPRESS)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--triples", default=str(TRIPLES_PATH))
    ap.add_argument("--triple", action="append", default=None,
                    help="REGION_UNIVERSE_dDELAY, repeatable; default is every discovered triple")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--catalog", default=None)
    ap.add_argument("--cell-counts", default=str(CELL_COUNTS))
    ap.add_argument("--per-cell", type=int, default=50,
                    help="catalogue rows kept per (region, delay, cell); 0 keeps all")
    ap.add_argument("--rpm", type=int, default=60)
    ap.add_argument("--burst", type=int, default=1)
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--refresh", action="store_true", help="re-crawl triples that already have a file")
    ap.add_argument("--fake-per-cell", type=int, default=3, help="dry-run fields minted per cell")
    ap.add_argument("--no-inject-faults", action="store_true",
                    help="dry-run only: skip the injected 429/5xx that rehearse the retry layer")
    args = ap.parse_args(argv)

    dry = not args.live
    prefix = "SIMULATED: " if dry else ""

    def log(msg):
        print(prefix + msg, flush=True)

    triples = load_triples(args.triples)
    if args.triple:
        wanted = set(args.triple)
        triples = [t for t in triples if triple_filename(t)[:-len(".jsonl")] in wanted]
        if not triples:
            print("no triple matched %s" % sorted(wanted), file=sys.stderr)
            return 1

    out_dir = pathlib.Path(args.out_dir) if args.out_dir else (
        LIVE_FIELDS_DIR if args.live else DRYRUN_ROOT / "fields")
    catalog_path = pathlib.Path(args.catalog) if args.catalog else (
        LIVE_CATALOG if args.live else DRYRUN_ROOT / "field_catalog.jsonl")

    if dry:
        # A rehearsal may not write where the round's gates read: simulated rows carrying
        # resolved_http 200 would be indistinguishable from live evidence in the artifact.
        live_paths = {LIVE_CATALOG.resolve(), LIVE_FIELDS_DIR.resolve()}
        for p in (out_dir, catalog_path):
            rp = p.resolve()
            if rp in live_paths or live_paths & set(rp.parents):
                print("refusing to write dry-run output to the live path %s; pass --live to crawl"
                      % rp, file=sys.stderr)
                return 1

    rng = random.Random(args.seed)
    if args.live:
        clock, client = SystemClock(), LiveClient()
    else:
        clock = VirtualClock()
        client = FakeClient(triples, seed=args.seed, n_per_cell=args.fake_per_cell,
                            inject_faults=not args.no_inject_faults)

    crawler = Crawler(client, clock=clock, rng=rng, rpm=args.rpm, burst=args.burst,
                      max_attempts=args.max_attempts, simulated=dry)

    log("mode=%s triples=%d out=%s catalog=%s" % (
        "LIVE" if args.live else "dry-run", len(triples), out_dir, catalog_path))
    summary = crawl(triples, crawler, out_dir, catalog_path, per_cell=args.per_cell,
                    refresh=args.refresh, counts_path=args.cell_counts, log=log)
    summary["mode"] = "live" if args.live else "dry-run"
    summary["seed"] = args.seed
    if dry:
        summary["label"] = SIM_LABEL
    log(json.dumps(summary, sort_keys=True))

    if summary["stopped"]:
        return 2 if "401" in summary["stopped"] else 3
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
