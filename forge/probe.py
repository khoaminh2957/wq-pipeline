"""forge.probe — prod/self correlation for scored candidates (design §7). READ ONLY.

FACT (measured 2026-08-14/16/29): the first GET on /alphas/{id}/correlations/{kind} answers 200
with an EMPTY body and starts the platform computing; numbers land about 90–120 s later; a stored
result can expire and a later GET restarts the compute. So: trigger every pending candidate, wait
`--wait` seconds once, read once, store what came; never re-trigger a stored value. Pace 1.1 s
(60 req/min bucket shared with everything else).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))          # `python forge/x.py` puts forge/ first, not the repo root
from forge import harvest as HV  # noqa: E402

API = "https://api.worldquantbrain.com"
CORR = ROOT / "state/forge/corr.jsonl"
PACE_S = 1.1
KINDS = ("prod", "self")


#: An empty 200 means the platform QUEUED the calculation, not that there is nothing to report. The
#: endpoint is asynchronous: the first GET starts the work and a later GET returns the payload.
#: MEASURED 2026-09-23 00:25: rK5RGeqa and qMWbdlmv both answered "200-empty" on two consecutive
#: submit rounds and were skipped each time; calling again moments later returned prod 0.6524 /
#: self 0.5193 and prod 0.9668 / self 0.9668 respectively, with 20 and 5 records. rK5RGeqa is under
#: both lines -- it was a submittable alpha that the probe declined to read. Retrying the empty body
#: is therefore not politeness, it is the difference between submitting and not.
EMPTY_TRIES = 5
EMPTY_WAIT_S = 4.0


def read(s, aid, kind, sleep=time.sleep, tries=3, empty_tries=EMPTY_TRIES, empty_wait=EMPTY_WAIT_S):
    """(value, why). value is the payload's `max`; None with a reason otherwise.

    A 429 is not the platform refusing the alpha, it is the shared 60-req/min bucket asking us to
    wait -- and the forge loop polls simulations out of the SAME bucket, so a probe pacing at 1.1 s
    (~55/min) on its own overflows it whenever the loop is running. MEASURED 2026-09-21: a 109-alpha
    batch took 243 429s and landed 0 of 109, while a 27-alpha batch an hour earlier landed 17 of 27
    purely because it was short enough to fit in the gaps. Honour Retry-After and try again, rather
    than storing a reason string that reads afterwards like a verdict about the alpha.

    An empty 200 is retried for the same reason: it is a "not yet", never an answer about the alpha.
    """
    for empty_attempt in range(max(1, empty_tries)):
        for attempt in range(tries):
            try:
                r = s.get("%s/alphas/%s/correlations/%s" % (API, aid, kind), timeout=30)
            except Exception as exc:  # noqa: BLE001
                return None, "exception:%s" % type(exc).__name__
            if r.status_code != 429 or attempt == tries - 1:
                break
            wait = r.headers.get("Retry-After") or r.headers.get("RateLimit-Reset") or 5
            try:
                wait = float(wait)
            except (TypeError, ValueError):
                wait = 5.0
            sleep(min(wait + 1.0, 65.0))
        if r.status_code != 200 or (r.text or "").strip():
            break
        if empty_attempt < max(1, empty_tries) - 1:
            sleep(empty_wait)
    if r.status_code != 200:
        h = {k: v for k, v in r.headers.items()
             if k.lower().startswith(("ratelimit", "x-ratelimit", "retry-after"))}
        return None, "http:%d %s" % (r.status_code, ";".join("%s=%s" % kv for kv in sorted(h.items())) or "no-rate-headers")
    body = r.text or ""
    if not body.strip():
        return None, "200-empty after %d tries (~%.0fs)" % (max(1, empty_tries), (max(1, empty_tries) - 1) * empty_wait)
    try:
        j = r.json()
    except ValueError:
        return None, "200-unparseable:%dB" % len(body)
    if isinstance(j, dict) and "max" in j:
        return j["max"], "ok"
    return None, "payload:%dB-no-max" % len(body)


def load_corr(path=CORR) -> dict:
    """alpha -> {prod, self, read_at} merging every stored reading (a value, once read, is kept)."""
    out = {}
    if pathlib.Path(path).exists():
        for r in HV.read_jsonl(path):
            a = r.get("alpha")
            if not a:
                continue
            cur = out.setdefault(a, {})
            for k in KINDS:
                if isinstance(r.get(k), (int, float)):
                    cur[k] = r[k]
            cur["read_at"] = r.get("read_at")
    return out


def append_corr(rows, path=CORR) -> None:
    """Append reading rows ({alpha, read_at, prod, self}) to the corr journal. `load_corr` keeps the
    LAST numeric value per kind, so a later reading supersedes an earlier one."""
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def pending(scored: dict, corr: dict) -> list:
    """Candidates (stage == candidate) missing at least one of prod/self, best score first."""
    todo = [x for x in scored.values() if x.get("stage") == "candidate" and x.get("pbo_pass") is not False
            and not all(isinstance(corr.get(x["alpha"], {}).get(k), (int, float)) for k in KINDS)]
    return sorted(todo, key=lambda x: -(x.get("score") or 0))


def sweep(s, alphas, corr, sleep=time.sleep, out=print) -> list:
    """One pass over `alphas`: read both kinds for each, return the new rows (values or reasons).

    Stops on the first 401. The session is 4 h and non-renewable, so once it expires every remaining
    call returns 401 too; carrying on only writes a reason string per alpha that a later reader has
    to tell apart from a real answer. MEASURED 2026-09-21: 193 of them in one run."""
    rows = []
    for aid in alphas:
        row = {"alpha": aid, "read_at": time.time()}
        for kind in KINDS:
            if isinstance(corr.get(aid, {}).get(kind), (int, float)):
                row[kind] = corr[aid][kind]           # already stored: do not re-trigger
                continue
            sleep(PACE_S)
            # forward the caller's sleep: `read` now waits out an empty 200, and a sweep that did
            # not pass it through slept for real inside the tests and ignored the caller's pacing
            v, why = read(s, aid, kind, sleep=sleep)
            row[kind] = v if v is not None else why
            if v is None and why.startswith("http:401"):
                out("  auth dead after %d alpha(s) -- stopping; the rest stay pending" % len(rows))
                rows.append(row)
                return rows
        rows.append(row)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--wait", type=int, default=120, help="seconds between trigger and read (0 = trigger only)")
    ap.add_argument("--alphas", default="", help="comma list of alpha ids to read regardless of stage (an experiment's rows)")
    a = ap.parse_args(argv)
    import layered_sim as LS
    scored = HV.load_scored()
    corr = load_corr()
    if a.alphas:
        todo = [x for x in a.alphas.split(",") if x and not all(isinstance(corr.get(x, {}).get(k), (int, float)) for k in KINDS)][:a.limit]
    else:
        todo = [x["alpha"] for x in pending(scored, corr)][:a.limit]
    print("probe: %d candidate(s) pending correlation" % len(todo), flush=True)
    if not todo:
        return 0
    s = LS.session()
    LS.keep_jar_fresh(s)
    store = append_corr
    first = sweep(s, todo, corr)
    store(first)
    got = [r for r in first if all(isinstance(r.get(k), (int, float)) for k in KINDS)]
    print("  phase 1: %d of %d already had both values" % (len(got), len(first)), flush=True)
    still = [r["alpha"] for r in first if r not in got]
    if a.wait > 0 and still:
        time.sleep(a.wait)
        second = sweep(s, still, load_corr())
        store(second)
        got2 = [r for r in second if all(isinstance(r.get(k), (int, float)) for k in KINDS)]
        print("  phase 2 (+%ds): %d of %d landed" % (a.wait, len(got2), len(second)), flush=True)
    for r in load_corr().items():
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
