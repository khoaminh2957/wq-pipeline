#!/usr/bin/env python3
"""One shared, DISK-PERSISTED backoff that every path POSTing /authentication must honour.

WHY THIS EXISTS
The daemon (harness13/runtime/auth_relay.py) already classifies a 429 and backs off, but its
`_BACKOFF` is module-level in memory and enforced by an in-process sleep. A restart DISCARDS the
remaining wait and the next line of code POSTs immediately. On 2026-08-12 eleven restarts happened
for exactly that reason, and six other modules in this repo reach the same endpoint with no 429
branch at all. A backoff that lives in one process's memory is not a backoff; it is a comment.

So the state lives in a FILE, it is READ AT STARTUP by whoever is about to POST, and the check is
one call. Nothing here opens a socket.

THE TWO RULES THAT SHAPE EVERY DECISION BELOW

1. THIS MODULE NEVER SLEEPS. `guard()` REFUSES and returns control. Sleeping is what made the old
   backoff erasable by a restart, and a caller that is refused can do something useful (write a
   status, exit non-zero, wake a human) instead of holding a process open for seven hours.

2. WHETHER A RETRY EXTENDS THE LOCK IS **MECHANISM: UNKNOWN**. No experiment in this repo has
   distinguished a fixed-duration BIOMETRICS_THROTTLED window from a rolling one that each refused
   POST pushes further out. Both fit every observation we have. Because one probe under the rolling
   hypothesis is unbounded damage and is UNDETECTABLE from the outside, the policy is the
   conservative branch: on this class we do not auto-retry early, and a fresh 429 re-arms the full
   window from the moment it was observed rather than from the original lock.

WHAT IS MEASURED AND WHAT IS POLICY

  * `BIOMETRICS_LOCK_S = 7h` is POST-HOC, n=1. `harness13/runtime/auth_relay.py` lines 27-32 record
    that ~6.7 mints/hour drew 429 BIOMETRICS_THROTTLED and it "stayed throttled" for seven more
    hours. That is one observation of one lock's duration, not a published TTL and not a threshold.
    A second, weaker data point from 2026-08-12: a POST refused after a full uninterrupted 1800s
    wait, so the window is longer than 30 minutes. `Retry-After` was ABSENT on all three refusals,
    which is why this file carries a policy number at all -- if the server stated one we would use
    it.
  * `CONCURRENT_LOCK_S = 60s` and `UNKNOWN_LOCK_S = 3600s` are copied from the daemon's
    CONCURRENT_429_BACKOFF_S / UNKNOWN_429_BACKOFF_S so the two agree. UNKNOWN is deliberately
    expensive: an unrecognised wall is never assumed to be the cheap one.
  * The DAILY boundary of 04:00Z is the daemon's (= 00:00 EDT). It is a boundary that matched
    observation in August, NOT a timezone implementation -- under EST the true boundary is 05:00Z
    and this would release an hour early. Left as-is to match the daemon rather than silently
    diverge from it; noted so nobody reads it as correct year-round.

FAIL-CLOSED, AND THE ONE PLACE IT FAILS OPEN
An ABSENT state file means this account has never been throttled -> not blocked. A PRESENT but
UNPARSEABLE one means we cannot tell whether we are throttled, and the costs are wildly asymmetric:
being wrongly blocked costs one human tap, being wrongly unblocked may extend a lock nobody can
measure. So a corrupt file BLOCKS until a human runs `unblock()`.

USAGE -- the entire integration is two calls:

    import auth_backoff
    auth_backoff.guard("auth_only")          # raises AuthThrottled if the endpoint is walled
    r = session.post(HOST + "/authentication", timeout=30)
    if r.status_code == 429:
        auth_backoff.record_429(r.text, r.headers, source="auth_only")
    elif r.status_code in (200, 201):
        auth_backoff.record_success(source="auth_only")
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Mapping, Optional

SCHEMA_VER = 1

# ---------------------------------------------------------------------------- policy constants

BIOMETRICS_LOCK_S = 7 * 3600.0   # POST-HOC n=1, auth_relay.py L27-32. See module docstring.
CONCURRENT_LOCK_S = 60.0         # mirrors auth_relay.CONCURRENT_429_BACKOFF_S
UNKNOWN_LOCK_S = 3600.0          # mirrors auth_relay.UNKNOWN_429_BACKOFF_S -- never the cheap case
DAILY_RESET_UTC_HOUR = 4         # 00:00 EDT. See docstring: not DST-correct, matches the daemon.

_LOCK_S_BY_CLASS = {
    "BIOMETRICS_THROTTLED": BIOMETRICS_LOCK_S,
    "CONCURRENT": CONCURRENT_LOCK_S,
    "UNKNOWN": UNKNOWN_LOCK_S,
}

# Classes on which an early automatic retry is forbidden outright, because the cost of being wrong
# is unbounded and undetectable (docstring rule 2). `guard(..., force=True)` is the human override.
NO_AUTO_RETRY_CLASSES = frozenset({"BIOMETRICS_THROTTLED"})

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_PATH = _REPO_ROOT / "state" / "auth_backoff.json"


# ---------------------------------------------------------------------------------- exceptions

class AuthThrottled(RuntimeError):
    """Raised by `guard()` when the endpoint is walled. Carries the record so a caller can report
    a real expiry instead of a generic failure."""

    def __init__(self, block: "Block"):
        self.block = block
        super().__init__(str(block))


class Block:
    """A live wall. `remaining_s` is a floor, not a promise -- see MECHANISM: UNKNOWN above."""

    __slots__ = ("cls", "until", "remaining_s", "recorded_at", "source", "consecutive", "note")

    def __init__(self, cls, until, remaining_s, recorded_at=None, source=None,
                 consecutive=0, note=None):
        self.cls = cls
        self.until = until
        self.remaining_s = remaining_s
        self.recorded_at = recorded_at
        self.source = source
        self.consecutive = consecutive
        self.note = note

    def as_dict(self):
        return {"class": self.cls, "until": self.until, "remaining_s": round(self.remaining_s, 1),
                "recorded_at": self.recorded_at, "source": self.source,
                "consecutive": self.consecutive, "note": self.note}

    def __str__(self):
        if self.until is None:
            return f"/authentication blocked ({self.cls}): {self.note or 'no expiry recorded'}"
        return (f"/authentication blocked ({self.cls}) for another {self.remaining_s:.0f}s "
                f"(until epoch {self.until:.0f}, recorded by {self.source})")


# ------------------------------------------------------------------------------- classification

def classify_429(body: Any) -> str:
    """DAILY vs BIOMETRICS_THROTTLED vs CONCURRENT vs UNKNOWN, from the BODY, never the status.

    A DELIBERATE COPY of `harness13/runtime/auth_relay.py:classify_429`, not an import: `tools/`
    ships without harness13 and the daemon is a separate deployable, so an import would couple two
    things that are not deployed together. The copy is pinned by a test that runs the same table of
    bodies through both and asserts they agree, so a future edit to either one fails loudly instead
    of drifting.
    """
    text = body or ""
    if not isinstance(text, str):
        try:
            text = json.dumps(text)
        except (TypeError, ValueError):
            text = str(text)
    up = text.upper()
    if "DAILY" in up:
        return "DAILY"
    if "BIOMETRIC" in up:
        return "BIOMETRICS_THROTTLED"
    if "CONCURRENT" in up or "SIMULTANEOUS" in up or "IN PROGRESS" in up:
        return "CONCURRENT"
    return "UNKNOWN"


def _next_daily_reset(now: float) -> float:
    """The next DAILY_RESET_UTC_HOUR boundary strictly after `now`, in epoch seconds."""
    day = now - (now % 86400.0)                 # 00:00Z of the current day
    boundary = day + DAILY_RESET_UTC_HOUR * 3600.0
    return boundary if boundary > now else boundary + 86400.0


def _retry_after_seconds(headers: Optional[Mapping[str, Any]]) -> Optional[float]:
    """Retry-After as seconds, or None. Only the delta-seconds form is honoured; the HTTP-date form
    is not parsed here because no observation in this repo has ever seen one from this endpoint, and
    guessing at a format we have never received would be inventing a measurement."""
    if not headers:
        return None
    raw = None
    for k, v in headers.items():
        if str(k).lower() == "retry-after":
            raw = v
            break
    if raw is None:
        return None
    try:
        val = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return val if val >= 0 else None


# -------------------------------------------------------------------------------- state on disk

def _state_path(state_path=None) -> Path:
    if state_path is not None:
        return Path(state_path)
    env = os.environ.get("WQ_AUTH_BACKOFF_PATH")
    return Path(env) if env else DEFAULT_STATE_PATH


def _read(state_path=None):
    """(record, corrupt). An absent file is (None, False); an unreadable one is (None, True)."""
    p = _state_path(state_path)
    try:
        raw = p.read_text()
    except FileNotFoundError:
        return None, False
    except OSError:
        return None, True
    try:
        rec = json.loads(raw)
    except (ValueError, TypeError):
        return None, True
    if not isinstance(rec, dict):
        return None, True
    return rec, False


def _write(rec, state_path=None) -> None:
    p = _state_path(state_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(rec, f, indent=1, sort_keys=True)
    os.replace(tmp, p)          # same atomic-replace shape auth_only.py uses for the cookie jar


# ------------------------------------------------------------------------------------ public API

def check(now: Optional[float] = None, state_path=None) -> Optional[Block]:
    """The live wall, read FROM DISK on every call, or None if the endpoint is free.

    Reading every call (rather than caching at import) is the whole point: a sibling process that
    just took a 429 must be able to stop this one before it POSTs.
    """
    now = time.time() if now is None else float(now)
    rec, corrupt = _read(state_path)
    if corrupt:
        return Block("CORRUPT_STATE", None, float("inf"), note=(
            "auth_backoff state file is unreadable, so whether the endpoint is throttled is "
            "unknown. Refusing to POST. Clear deliberately with auth_backoff.unblock()."))
    if not rec:
        return None
    until = rec.get("blocked_until")
    if until is None:
        return None
    try:
        until = float(until)
    except (TypeError, ValueError):
        return Block("CORRUPT_STATE", None, float("inf"),
                     note="blocked_until is not a number; refusing to POST.")
    if until <= now:
        return None
    return Block(rec.get("class", "UNKNOWN"), until, until - now,
                 recorded_at=rec.get("recorded_at"), source=rec.get("source"),
                 consecutive=int(rec.get("consecutive", 0) or 0), note=rec.get("note"))


def guard(source: str, now: Optional[float] = None, state_path=None, force: bool = False) -> None:
    """Call immediately before POSTing /authentication. Raises AuthThrottled, NEVER sleeps.

    `force=True` is the human override for the classes in NO_AUTO_RETRY_CLASSES. It is a parameter
    and not an env var so that it cannot be set once and forgotten in a service file.
    """
    block = check(now=now, state_path=state_path)
    if block is None:
        return
    if force and block.cls not in NO_AUTO_RETRY_CLASSES and block.cls != "CORRUPT_STATE":
        return
    raise AuthThrottled(block)


def record_429(body: Any, headers: Optional[Mapping[str, Any]] = None, source: str = "?",
               now: Optional[float] = None, state_path=None) -> Block:
    """Record a refusal and arm the wall. Returns the Block that is now in force.

    The window is armed from NOW, not from the first refusal of a streak: under the rolling-window
    hypothesis (MECHANISM: UNKNOWN) the clock restarts on every refused POST, and if that hypothesis
    is false the cost is only a longer wait.
    """
    now = time.time() if now is None else float(now)
    cls = classify_429(body)
    ra = _retry_after_seconds(headers)

    if cls == "DAILY":
        until = _next_daily_reset(now)
        if ra is not None:
            until = max(until, now + ra)
    else:
        policy = _LOCK_S_BY_CLASS.get(cls, UNKNOWN_LOCK_S)
        # max(), never min(): a server-stated Retry-After may LENGTHEN the wait but is not allowed
        # to shorten a policy window that exists precisely because the server stated nothing.
        until = now + (max(policy, ra) if ra is not None else policy)

    prev, _corrupt = _read(state_path)
    consecutive = 1
    if prev and prev.get("class") == cls:
        try:
            consecutive = int(prev.get("consecutive", 0) or 0) + 1
        except (TypeError, ValueError):
            consecutive = 1

    text = body if isinstance(body, str) else json.dumps(body, default=str)
    rec = {"schema_ver": SCHEMA_VER, "blocked_until": until, "class": cls, "recorded_at": now,
           "retry_after_s": ra, "source": source, "consecutive": consecutive,
           "body_excerpt": (text or "")[:300],
           "note": "armed from the most recent refusal; rolling-vs-fixed window is UNKNOWN"}
    _write(rec, state_path)
    return Block(cls, until, until - now, recorded_at=now, source=source,
                 consecutive=consecutive, note=rec["note"])


def record_success(source: str = "?", now: Optional[float] = None, state_path=None) -> None:
    """A 200/201 from /authentication clears the wall -- the endpoint demonstrably answered."""
    now = time.time() if now is None else float(now)
    _write({"schema_ver": SCHEMA_VER, "blocked_until": None, "class": None,
            "recorded_at": now, "source": source, "consecutive": 0,
            "note": "cleared by a successful authentication"}, state_path)


def unblock(reason: str, actor: str, now: Optional[float] = None, state_path=None) -> None:
    """The human override. Records WHO cleared the wall and WHY, because a cleared throttle that
    nobody can attribute is how the eleven restarts of 2026-08-12 became invisible."""
    now = time.time() if now is None else float(now)
    _write({"schema_ver": SCHEMA_VER, "blocked_until": None, "class": None,
            "recorded_at": now, "source": f"unblock:{actor}", "consecutive": 0,
            "note": f"manually cleared by {actor}: {reason}"}, state_path)


def describe(now: Optional[float] = None, state_path=None) -> str:
    """One human-readable line, for status tools and log headers."""
    block = check(now=now, state_path=state_path)
    return "/authentication: clear" if block is None else str(block)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "unblock":
        if len(sys.argv) < 4:
            raise SystemExit("usage: auth_backoff.py unblock <actor> <reason...>")
        unblock(" ".join(sys.argv[3:]), sys.argv[2])
        print("cleared:", describe())
    else:
        print(describe())
        raise SystemExit(1 if check() is not None else 0)
