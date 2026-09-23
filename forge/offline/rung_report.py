"""harness5 rung report — the benchmark of record, per quota day (docs/harness5/00_agreements.md).

Per platform quota day (00:00 America/New_York): simulations landed (DISTINCT alpha ids with a
journal row, by dateCreated — a recovered duplicate row is not a second simulation), submissions
POSTed and accepted (ledger http 200/201, one per alpha), how many of those the platform has since
adjudicated ACTIVE (record_adjudication rows; Q2 says "POSTed and ACTIVE"), distinct mechanism keys
and distinct dataset sets among them, the split per arm (a submission's arm is its alpha's
meta.arm), and the rung test:
  measured day  := sims >= 4,000 (the whole day, both arms — the quota guardrail, Q6)
  rate          := submissions / sims * 5,000 (per 5,000-sim day), pooled AND per arm
  rung k passes := rate >= RUNGS[k] on the measured day(s) of the round, guardrails intact;
                   Q24: the rung is read on the NEW arm scaled to 5,000 (`--arm new`).
A day that is still open (today in ET) is flagged; its reading is partial, not a verdict.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import sys
import time
import zoneinfo

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from forge import harvest as HV, submit as SB  # noqa: E402

RUNGS = {1: 1.5, 2: 2.0, 3: 2.75, 4: 3.5, 5: 4.0}      # submissions per 5,000-sim day
MIN_SIMS = 4000
ET = zoneinfo.ZoneInfo("America/New_York")


def day_of_created(date_created: str) -> str | None:
    """dateCreated is the platform's ISO stamp with offset; its ET calendar date is the quota day."""
    if not date_created:
        return None
    try:
        return datetime.datetime.fromisoformat(date_created).astimezone(ET).strftime("%Y-%m-%d")
    except ValueError:
        return date_created[:10]


def _rate(subs: int, sims: int):
    return round(subs / sims * 5000, 2) if sims else None


def report(journal=HV.JOURNAL, ledger=ROOT / "state/forge/submitted.jsonl", days: int = 10, now=None) -> list:
    now = now or time.time()
    latest = {}
    for r in HV.read_jsonl(journal):
        if r.get("alpha"):
            latest[r["alpha"]] = r           # one alpha id = one simulation; 158 ids had two rows (orphan recovery, 2026-09-06/07)
    sims = collections.Counter()
    arms = collections.defaultdict(collections.Counter)
    arm_of = {}
    for a, r in latest.items():
        arm = (r.get("meta") or {}).get("arm", "-")
        arm_of[a] = arm
        d = day_of_created(r.get("dateCreated"))
        if d:
            sims[d] += 1
            arms[d][arm] += 1
    posts, adjudicated = {}, {}
    for h in HV.read_jsonl(ledger) if pathlib.Path(ledger).exists() else []:
        a = h.get("alpha")
        if not a:
            continue
        if h.get("kind") == "adjudication":
            adjudicated[a] = h.get("status")
        elif h.get("http") in (200, 201) and h.get("posted_at") and a not in posts:
            posts[a] = h                      # one accepted POST per alpha, ever
    subs = collections.defaultdict(list)
    for a, h in posts.items():
        subs[SB.quota_day(h["posted_at"])].append(dict(h, arm=h.get("arm") or arm_of.get(a, "-"), adjudication=adjudicated.get(a)))
    today = SB.quota_day(now)
    out = []
    for d in sorted(set(sims) | set(subs))[-days:]:
        s = subs.get(d, [])
        n = sims.get(d, 0)
        by_arm = {}
        for arm in sorted(set(arms.get(d, {})) | {h["arm"] for h in s}):
            k = sum(1 for h in s if h["arm"] == arm)
            m = arms.get(d, {}).get(arm, 0)
            by_arm[arm] = {"sims": m, "submitted": k, "rate_per_5000": _rate(k, m)}
        out.append({"day": d, "sims": n, "measured": n >= MIN_SIMS, "open": d == today, "submitted": len(s),
                    "active": sum(1 for h in s if h["adjudication"] == "ACTIVE"),
                    "unadjudicated": sum(1 for h in s if h["adjudication"] is None),
                    "mechanisms": len({h.get("mechanism_key") for h in s}),
                    "dataset_sets": len({h.get("datasets") or SB.datasets_of(h.get("mechanism_key")) for h in s}),
                    "rate_per_5000": _rate(len(s), n), "arms": dict(arms.get(d, {})), "by_arm": by_arm})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--rung", type=int, default=0, help="rung to test on the last measured day")
    ap.add_argument("--arm", default="", help="read the rung on this arm's submissions and sims (Q24: the new arm)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rows = report(days=a.days)
    if a.json:
        print(json.dumps(rows, indent=1))
        return 0
    print("%-11s %6s %-8s %4s %6s %5s %5s %9s  %s" % ("quota day", "sims", "measured", "subs", "active", "mechs", "dsets", "per5000", "by arm (sims/subs/per5000)"))
    for r in rows:
        arms = " ".join("%s=%d/%d/%s" % (k, v["sims"], v["submitted"], v["rate_per_5000"]) for k, v in r["by_arm"].items())
        print("%-11s %6d %-8s %4d %6d %5d %5d %9s  %s%s" % (r["day"], r["sims"], "yes" if r["measured"] else "no", r["submitted"],
                                                             r["active"], r["mechanisms"], r["dataset_sets"], r["rate_per_5000"], arms,
                                                             "  [OPEN: partial day]" if r["open"] else ""))
    if a.rung:
        meas = [r for r in rows if r["measured"]]
        if not meas:
            print("rung %d: no measured day yet" % a.rung)
        else:
            last = meas[-1]
            rate = last["rate_per_5000"] or 0
            label = "pooled"
            if a.arm:
                rate = (last["by_arm"].get(a.arm) or {}).get("rate_per_5000") or 0
                label = "arm %s" % a.arm
            ok = rate >= RUNGS[a.rung]
            print("rung %d (%.2f per 5,000, %s): %s on %s (%.2f)%s%s" % (
                a.rung, RUNGS[a.rung], label, "PASS" if ok else "FAIL", last["day"], rate,
                "  -- DAY STILL OPEN, not a verdict" if last["open"] else "",
                "  -- %d POST(s) not yet adjudicated ACTIVE (Q2)" % (last["submitted"] - last["active"]) if last["submitted"] != last["active"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
