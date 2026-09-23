#!/usr/bin/env python3
"""The ONLY module in this tree permitted to POST to Discord.  Enforced by a test, not a convention.

Every rule below is a specific measured failure, not a preference:

  * No retry and no 429 handling existed at ANY call site.  One message was lost outright on
    2026-08-16 02:54:11 (ReadTimeout); its whole trace was three journal lines nobody reads.
  * Seven call sites in climb_loop.sh redirected their errors to /dev/null.  A channel that had been
    returning 404 for 113 days looked healthy from every one of them.
  * A wrong token on a live webhook answers 401/50027; a deleted webhook answers 404/10015.  The Mac
    credential answers 404/10015, so the webhook OBJECT was deleted -- a new token would not help.
    A dead credential must therefore be LOUD at startup, in seconds, not silent for 113 days.

THE RETRY-AFTER UNIT, measured rather than assumed
--------------------------------------------------
An unversioned webhook URL -- the form both env files use -- resolves to the PRE-v8 API.  On a real
429 provoked with GETs only, the header read `Retry-After: 1953` while `X-RateLimit-Reset-After`
read `2`.  So on this API the HEADER IS MILLISECONDS and the body's `retry_after: 0.353` is SECONDS.

That inverts the usual guidance ("headers are unambiguously seconds"), and it means the deployed
client's arithmetic is wrong in BOTH directions: notifier/webhook_client.py divides the body by 1000
(latent -- the header is present on 7 of 7 observed 429s, so that branch is never reached), while its
header path reads 1953 as 1953 seconds and sleeps a clamped 30 s where 1.953 s was needed.

The resolution here does not trust either unit convention.  `X-RateLimit-Reset-After` is a float in
seconds in every API version, so it is priority 1 and anchors everything else.  The header is used
only as a last resort and only with a magnitude heuristic, and whichever source fired is written
into the ledger so a future reader can check this reasoning instead of inheriting it.
"""
import json
import os
import random
import re
import stat
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import outbox as OB  # noqa: E402

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Both of these resolve to the SAME channel_id and guild_id (measured, read-only GET).  The
# two-channel catalogue is therefore cosmetic until a second channel actually exists, and
# "escalate to the other channel when this one dies" is useless by construction -- there is no
# other channel.  The map stays so the split is one config edit away.
CHANNEL_ENV = {
    "auth": "DISCORD_WEBHOOK_URL",
    "climb": "DISCORD_HEALTH_WEBHOOK_URL",
}
FALLBACK_ENV = "DISCORD_WEBHOOK_URL"

MAX_429_WAITS = 5
MAX_429_TOTAL_S = 120.0
MAX_FAIL_RETRIES = 4
BACKOFF = (1.0, 2.0, 4.0, 8.0)
WAIT_CLAMP = (0.05, 60.0)
DEGRADED_ESCALATE_S = 1800.0
DEGRADED_PROBE_S = 900.0
HTTP_TIMEOUT = (10, 30)

_URL_RE = re.compile(r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/(?:v\d+/)?webhooks/\d+/[\w-]+$")
_SECRET_RE = re.compile(r"https://[^\s\"']*discord(?:app)?\.com/api/\S*", re.I)


def scrub(text):
    """No exception string, no log line, no ledger row may ever carry the credential."""
    if not text:
        return text
    return _SECRET_RE.sub("<webhook url withheld>", str(text))


# --------------------------------------------------------------------------- config

def load_env_file(path):
    out = {}
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        return {}
    return out


def resolve_config(env_path=None, strict=True):
    """Resolution order is deliberately INVERTED: file first, process environment LAST.

    Both current readers check the process environment first, which lets a stale exported value in
    one shell silently outrank the file every other process reads.  Errors name the KEY and the
    FILE.  They never name the value.
    """
    env_path = env_path or os.environ.get("WQ_ENV_FILE") or os.path.join(ROOT, ".env")
    problems = []
    fromfile = {}
    if os.path.exists(env_path):
        st = os.stat(env_path)
        mode = stat.S_IMODE(st.st_mode)
        if mode & 0o077:
            problems.append("%s is mode %o; must be 0600 (no auto-chmod: a permission fix that "
                            "happens silently is how a leak stays invisible)" % (env_path, mode))
        fromfile = load_env_file(env_path)
    else:
        problems.append("%s does not exist" % env_path)

    resolved, sources = {}, {}
    for channel, key in CHANNEL_ENV.items():
        val, src = fromfile.get(key), env_path
        if not val:
            val, src = fromfile.get(FALLBACK_ENV), env_path + " (fallback %s)" % FALLBACK_ENV
        if not val:
            val, src = os.environ.get(key), "process environment"
        if not val:
            val, src = os.environ.get(FALLBACK_ENV), "process environment (fallback)"
        if not val:
            problems.append("no value for channel %r (key %s) in %s or the environment"
                            % (channel, key, env_path))
            continue
        if not _URL_RE.match(val):
            problems.append("value for key %s is not a well-formed Discord webhook URL "
                            "(value withheld)" % key)
            continue
        resolved[channel] = val
        sources[channel] = src

    if strict and problems:
        raise SystemExit("config refused:\n  - " + "\n  - ".join(problems))
    return resolved, sources, problems


def fingerprint(url):
    """Datable identity for a credential without storing it.  The record nobody could find when
    asking whether the Mac webhook had ever been rotated: its env file was never touched in 113
    days, so nothing on disk could answer."""
    try:
        wid = url.rstrip("/").split("/")[-2]
    except (AttributeError, IndexError):
        return None
    return {"webhook_id": wid, "token_sha12": OB.sha12(url.rstrip("/").split("/")[-1])}


# --------------------------------------------------------------------------- liveness of the channel

def probe(url, session=None):
    """GET the webhook.  200 -> alive, and the body names the channel.  404/10015 -> the object was
    DELETED (a wrong token would answer 401/50027 instead, which is how those two are told apart).

    This is the check that turns a 113-day silent death into a startup error."""
    s = session or requests
    try:
        r = s.get(url, timeout=HTTP_TIMEOUT)
    except Exception as exc:
        return {"ok": None, "state": "UNREACHABLE", "detail": scrub("%s: %s" % (type(exc).__name__, exc))}
    if r.status_code == 200:
        try:
            j = r.json()
        except ValueError:
            j = {}
        return {"ok": True, "state": "ALIVE", "channel_id": j.get("channel_id"),
                "guild_id": j.get("guild_id"), "name": j.get("name")}
    code = None
    try:
        code = r.json().get("code")
    except ValueError:
        pass
    if r.status_code == 404:
        return {"ok": False, "state": "DELETED", "http": 404, "discord_code": code,
                "detail": "webhook object no longer exists; a replacement token cannot fix this"}
    if r.status_code == 401:
        return {"ok": False, "state": "BAD_TOKEN", "http": 401, "discord_code": code,
                "detail": "webhook exists, credential rejected"}
    return {"ok": False, "state": "UNKNOWN", "http": r.status_code, "discord_code": code}


# --------------------------------------------------------------------------- the wait

def compute_wait(headers, body_json):
    """Return (seconds, source).  See the module docstring for why the order is what it is."""
    h = {k.lower(): v for k, v in (headers or {}).items()}

    reset_after = h.get("x-ratelimit-reset-after")
    if reset_after is not None:
        try:
            return _clamp(float(reset_after)), "x-ratelimit-reset-after"
        except (TypeError, ValueError):
            pass

    if isinstance(body_json, dict) and body_json.get("retry_after") is not None:
        try:
            # Measured seconds on this API (0.353 alongside a header of 1953).  Recorded as its own
            # source so the assumption is auditable rather than inherited.
            return _clamp(float(body_json["retry_after"])), "body_retry_after_seconds"
        except (TypeError, ValueError):
            pass

    ra = h.get("retry-after")
    if ra is not None:
        try:
            v = float(ra)
        except (TypeError, ValueError):
            v = None
        if v is not None:
            # Magnitude heuristic, and it is flagged as a heuristic.  A webhook rate limit is
            # seconds-scale; a value above 60 on this endpoint is milliseconds (measured: 1953 ms
            # against a 2 s reset-after).  Reading that as seconds is what makes the deployed
            # client sleep 30 s where 1.953 s was needed.
            if v > 60:
                return _clamp(v / 1000.0), "retry-after_header_ms_heuristic"
            return _clamp(v), "retry-after_header_seconds_heuristic"

    return 1.0, "default"


def _clamp(v):
    lo, hi = WAIT_CLAMP
    return max(lo, min(hi, v))


def _rl_fields(headers):
    h = {k.lower(): v for k, v in (headers or {}).items()}
    return {
        "rl_limit": h.get("x-ratelimit-limit"),
        "rl_remaining": h.get("x-ratelimit-remaining"),
        "rl_reset_after": h.get("x-ratelimit-reset-after"),
        "rl_bucket": h.get("x-ratelimit-bucket"),
        "rl_retry_after_hdr": h.get("retry-after"),
    }


# --------------------------------------------------------------------------- the send

def send_one(rec, url, session=None, sleep=time.sleep):
    """Deliver one message.  Three SEPARATE budgets, so a 429 -- which is not a failure -- cannot
    spend the failure budget and push a real message into stuck/.

    Returns (terminal_result, http, detail).  Never raises for a delivery problem.
    """
    s = session or requests
    n429 = 0
    total429 = 0.0
    fails = 0

    while True:
        rec["attempts"] = rec.get("attempts", 0) + 1
        try:
            r = s.post(url, json={"content": rec["body"]}, timeout=HTTP_TIMEOUT)
        except Exception as exc:
            detail = scrub("%s: %s" % (type(exc).__name__, exc))
            # A transport error after the bytes left is genuinely ambiguous: Discord exposes no
            # idempotency token, so a retry here can double-post.  We say so instead of pretending.
            if not rec.get("retry_on_unknown", True):
                OB.record_attempt(rec, "outcome_unknown", error=detail)
                return "outcome_unknown", None, detail
            fails += 1
            OB.record_attempt(rec, "retrying", error=detail,
                              extra={"reason": "transport", "outcome_unknown": True})
            if fails > MAX_FAIL_RETRIES:
                return "outcome_unknown", None, detail
            sleep(_jitter(BACKOFF[min(fails - 1, len(BACKOFF) - 1)]))
            continue

        code = r.status_code
        try:
            bj = r.json()
        except ValueError:
            bj = None

        if 200 <= code < 300:
            OB.record_attempt(rec, "sent", http=code, extra=_rl_fields(r.headers))
            return "sent", code, None

        if code == 429:
            wait, src = compute_wait(r.headers, bj)
            n429 += 1
            total429 += wait
            extra = _rl_fields(r.headers)
            extra.update({"retry_after_source": src, "wait_s": round(wait, 3),
                          "global": bool((bj or {}).get("global"))})
            OB.record_attempt(rec, "rate_limited", http=429, extra=extra)
            if n429 > MAX_429_WAITS or total429 > MAX_429_TOTAL_S:
                return "stuck", 429, "rate limited %d times, %.1fs total" % (n429, total429)
            sleep(wait)
            continue

        if 500 <= code < 600:
            fails += 1
            OB.record_attempt(rec, "retrying", http=code, extra={"reason": "server"})
            if fails > MAX_FAIL_RETRIES:
                return "stuck", code, "server error after %d retries" % fails
            sleep(_jitter(BACKOFF[min(fails - 1, len(BACKOFF) - 1)]))
            continue

        # Every other 4xx: zero retries.  Retrying a 404 is what produced 14,000+ futile requests.
        dcode = (bj or {}).get("code") if isinstance(bj, dict) else None
        OB.record_attempt(rec, "failed", http=code, extra={"discord_code": dcode})
        return "failed", code, "discord_code=%s" % (dcode,)


def _jitter(base):
    return base * random.uniform(0.75, 1.25)


# --------------------------------------------------------------------------- the drain

# DEGRADED CHANNELS MUST SURVIVE THE CALL THAT DISCOVERED THEM.
#
# `degraded` was a local, rebuilt every drain, so a channel whose webhook is deleted was
# rediscovered ten seconds later BY POSTING TO IT AGAIN. Measured 2026-08-16: 216 attempt rows for
# ONE message, 348 per hour, against a webhook already known to be gone -- which is precisely the
# behaviour this module's own docstring blames for 14,000+ futile requests on the other machine.
# I wrote the docstring and the defect in the same file.
_DEGRADED = {}


def drain(session=None, sleep=time.sleep, once=True, config=None):
    """Deliver everything pending.  Exhausted messages move to stuck/ and are NEVER deleted."""
    cfg = config
    if cfg is None:
        cfg = resolve_config()[0]
    degraded = _DEGRADED
    results = []
    for rec in OB.pending():
        ch = rec.get("channel")
        url = cfg.get(ch)
        if not url:
            OB.record_attempt(rec, "no_route", error="no webhook configured for channel %r" % ch)
            OB.move(rec, "stuck")
            results.append((rec["msg_id"], "no_route"))
            continue
        if degraded.get(ch):
            OB.record_attempt(rec, "held", error="channel %s DEGRADED; message kept in spool" % ch)
            results.append((rec["msg_id"], "held"))
            continue

        result, http, detail = send_one(rec, url, session=session, sleep=sleep)
        if result == "sent":
            # The verdict counts as told only now. See outbox.enqueue for why.
            OB.commit_verdict(rec)
            OB.done(rec)
        elif result == "failed" and http == 404:
            # The credential is gone.  Stop POSTing on this channel immediately rather than
            # discovering it 113 days and 14,192 requests later.
            degraded[ch] = True
            OB.update(rec)
            escalate("channel %s DEGRADED: webhook returns 404 (object deleted). "
                     "%d message(s) held in the spool." % (ch, len(OB.pending())))
        elif result == "outcome_unknown":
            # Not a failure and not a success. Recorded as neither -- but it must not be retried
            # forever: with no cumulative bound this re-POSTed 5x per drain, every 10 s, and EVERY
            # ONE of those may already have been delivered. Bound it, then park it.
            rec["unknown_rounds"] = rec.get("unknown_rounds", 0) + 1
            if rec["unknown_rounds"] >= 3:
                OB.record_attempt(rec, "parked_unknown",
                                  error="3 rounds of unknown outcome; parking rather than "
                                        "re-POSTing something that may already have arrived")
                OB.release_verdict(rec)
                OB.update(rec)
                OB.move(rec, "stuck")
            else:
                OB.update(rec)
        else:
            # This message will not be delivered. Release its verdict so the same alarm can fire
            # again -- an undelivered alarm must not silence its own repeats.
            OB.release_verdict(rec)
            OB.update(rec)
            OB.move(rec, "stuck")
        results.append((rec["msg_id"], result))
    write_health(results, degraded)
    return results


def escalate(text):
    """Failure is NEVER reported over the channel that may be the broken thing.

    Ordered by how little each layer depends on what is failing.
    """
    line = "[wq-outbox] " + scrub(text)
    try:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()
    except Exception:
        pass
    try:
        d = OB.ensure_dirs()
        with open(os.path.join(d["base"], "escalations.log"), "a") as fh:
            fh.write("%s %s\n" % (time.strftime("%F %T"), line))
    except OSError:
        pass


def write_health(results, degraded):
    d = OB.ensure_dirs()
    sent, enq, last_ok = OB.stats()
    payload = {
        "at": time.time(),
        "pending": len(OB.pending()),
        "sent_24h": sent,
        "enqueued_24h": enq,
        "last_success_ts": last_ok,
        "degraded_channels": sorted(degraded) if degraded else [],
        "last_drain": [{"msg_id": m, "result": r} for m, r in results[-20:]],
    }
    OB._atomic_write(d["health"], json.dumps(payload, ensure_ascii=False, indent=1))
    return payload


SERVE_INTERVAL_S = 10.0
SERVE_LOCK = "/var/lock/wq_outbox.lock"


def serve(interval=SERVE_INTERVAL_S):
    """Drain forever.  A flock makes a second copy impossible.

    The singleton matters: eleven senders accumulated in this tree one at a time, and three
    simultaneous copies of another loop once ran for 2h46m because every kill returned an error
    nobody checked.
    """
    import fcntl
    lf = open(SERVE_LOCK, "a+")
    try:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        escalate("another wq-outbox already holds %s; exiting" % SERVE_LOCK)
        return 0
    cfg, sources, problems = resolve_config(strict=False)
    for p in problems:
        escalate("config: %s" % p)
    if not cfg:
        escalate("no usable webhook configuration; refusing to start")
        return 1
    # Catch a dead credential in seconds instead of 113 days -- and, when one channel's webhook has
    # been deleted, DELIVER ANYWAY through a channel that still answers.
    #
    # The fallback used to fire only on a MISSING key, never on a dead one, so a deleted webhook
    # took its whole channel offline while a working webhook sat unused two lines away. Measured
    # 2026-08-16: the climb webhook was deleted and 145 messages failed against it while the auth
    # webhook answered 200 the entire time. Wrong channel beats no channel; the substitution is
    # announced in-band so nobody mistakes it for normal.
    live = {}
    for ch, url in sorted(cfg.items()):
        res = probe(url)
        if res.get("ok"):
            live[ch] = url
            continue
        if res.get("state") == "DELETED":
            escalate("channel %s: the webhook object no longer exists. A replacement token cannot "
                     "fix this; the webhook must be RECREATED and its URL put in .env." % ch)
        else:
            escalate("channel %s: startup probe says %s" % (ch, res.get("state")))
    for ch in list(cfg):
        if ch not in live and live:
            spare = sorted(live)[0]
            cfg[ch] = live[spare]
            escalate("channel %s is dead; routing its messages through %s so they still arrive. "
                     "Fix .env to restore the split." % (ch, spare))
    if not live:
        escalate("NO channel has a working webhook. Everything will be spooled, nothing delivered.")
    while True:
        try:
            drain(config=cfg)
        except Exception as exc:                   # noqa: BLE001 - the sender must not die quietly
            escalate("drain raised %s: %s" % (type(exc).__name__, scrub(exc)))
        time.sleep(interval)


def main(argv):
    if "--serve" in argv:
        return serve()
    if "--probe" in argv:
        cfg, sources, problems = resolve_config(strict=False)
        for p in problems:
            print("PROBLEM: %s" % p)
        for ch, url in sorted(cfg.items()):
            res = probe(url)
            fp = fingerprint(url)
            print("%-6s %-11s %s  webhook_id=%s" % (
                ch, res.get("state"), res.get("channel_id") or res.get("detail") or "",
                (fp or {}).get("webhook_id")))
        return 0
    if "--drain" in argv:
        res = drain()
        for m, r in res:
            print("%s %s" % (m, r))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
