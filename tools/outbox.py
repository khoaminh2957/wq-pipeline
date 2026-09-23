#!/usr/bin/env python3
"""The spool. Producers call enqueue(); nothing here touches the network.

Why this module exists, in one line per measured failure:

  * 7 of 11 producers discarded their send result into /dev/null, so a channel that had been dead
    for 113 days looked healthy from every producer.  enqueue() RAISES.  It has no result to drop.
  * Sequence numbers are assigned HERE, at enqueue, not at delivery.  Numbered at delivery, a lost
    message leaves no gap and the loss is invisible.
  * A body-hash de-duplicator would have suppressed ZERO of the 36 health copies posted inside the
    2026-08-16 outage: the bodies differed ("journal 1m old" .. "journal 380m old") while the verdict
    never changed.  Suppression keys on a declared verdict_key, never on the body.
  * msg_id IS the spool filename, so two concurrent enqueues of one event collapse to one file with
    no lock and no read-modify-write.

Nothing is ever deleted here.  pending/ -> stuck/ -> expired/, 30 day retention, so "was it
delivered?" stays answerable.  Today that question cannot be answered for any message this system
has ever sent.
"""
import hashlib
import json
import os
import tempfile
import time

try:
    import fcntl  # present on Linux and macOS.  It is flock(1), the CLI, that macOS lacks.
except ImportError:  # pragma: no cover - neither box is Windows
    fcntl = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTIFY_DIR = os.path.join(ROOT, "state", "notify")
PENDING = os.path.join(NOTIFY_DIR, "pending")
STUCK = os.path.join(NOTIFY_DIR, "stuck")
EXPIRED = os.path.join(NOTIFY_DIR, "expired")
BODIES = os.path.join(NOTIFY_DIR, "bodies")
SENT_LOG = os.path.join(NOTIFY_DIR, "sent.jsonl")
CURSORS = os.path.join(NOTIFY_DIR, "cursors.json")
SEQ_FILE = os.path.join(NOTIFY_DIR, "seq")
HEALTH = os.path.join(NOTIFY_DIR, "health.json")

CHANNELS = ("auth", "climb")
CLASSES = ("attention", "routine")
RETAIN_DAYS = 30

# Discord's hard body cap is 2000 characters for `content`.  We assemble below it and leave room
# for the omission marker rather than discovering the cap at POST time.
BODY_CAP = 1900


def _root_override():
    """Tests and the VPS both need to point the spool somewhere else without editing this file."""
    return os.environ.get("WQ_NOTIFY_DIR")


def _dirs():
    base = _root_override() or NOTIFY_DIR
    return {
        "base": base,
        "pending": os.path.join(base, "pending"),
        "stuck": os.path.join(base, "stuck"),
        "expired": os.path.join(base, "expired"),
        "bodies": os.path.join(base, "bodies"),
        "sent": os.path.join(base, "sent.jsonl"),
        "cursors": os.path.join(base, "cursors.json"),
        "seq": os.path.join(base, "seq"),
        "health": os.path.join(base, "health.json"),
    }


def ensure_dirs():
    d = _dirs()
    for k in ("base", "pending", "stuck", "expired", "bodies"):
        os.makedirs(d[k], exist_ok=True)
    return d


def sha12(s):
    if isinstance(s, str):
        s = s.encode("utf-8")
    return hashlib.sha256(s).hexdigest()[:12]


def _atomic_write(path, data):
    """Write into the TARGET directory, never $TMPDIR.

    /opt/wq and /tmp are different filesystems on the VPS; rename(2) across them returns EXDEV and
    /bin/mv silently degrades to copy-then-unlink, which is not atomic.  Failure here raises.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def next_seq():
    """Monotonic, assigned at ENQUEUE.  A gap in the delivered sequence is the evidence of a loss."""
    d = ensure_dirs()
    path = d["seq"]
    if fcntl is None:  # pragma: no cover
        n = (int(open(path).read().strip()) if os.path.exists(path) else 0) + 1
        _atomic_write(path, str(n))
        return n
    lock = path + ".lock"
    with open(lock, "a+") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            try:
                with open(path) as fh:
                    n = int((fh.read() or "0").strip() or 0)
            except (OSError, ValueError):
                n = 0
            n += 1
            _atomic_write(path, str(n))
            return n
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def _read_cursors():
    d = _dirs()
    try:
        with open(d["cursors"]) as fh:
            v = json.load(fh)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_cursors(cur):
    _atomic_write(_dirs()["cursors"], json.dumps(cur, ensure_ascii=False, indent=1, sort_keys=True))


def assemble(blocks, cap=BODY_CAP):
    """Blocks are (priority, name, text).  Priority 0 is MANDATORY and is never dropped.

    Order on the wire is: the priority-0 blocks in the order given, then the rest by priority.  The
    'best alpha' block is priority 0 and is therefore rendered second, immediately after the header
    -- position in the assembly IS the fix.  Under the old `tail -3 gems.jsonl` construction that
    block sat last inside 4502 bytes and was cut off by the 1900-char slice every single time, so
    the operator's standing requirement that every announcement name the best alpha has never once
    been delivered.

    Whole blocks are dropped, never mid-block, and the omission names what went and how much.
    Returns (body, dropped) where dropped is a list of (name, chars).
    """
    ordered = sorted(range(len(blocks)), key=lambda i: (blocks[i][0], i))
    mandatory = [i for i in ordered if blocks[i][0] == 0]
    optional = [i for i in ordered if blocks[i][0] != 0]

    kept = list(mandatory)
    dropped = []

    def render(idx_list):
        return "\n".join(blocks[i][2] for i in sorted(idx_list, key=lambda i: (blocks[i][0], i)))

    body = render(kept)
    if len(body) > cap:
        # MANDATORY ALONE OVERFLOWS.
        #
        # This used to hand the sender an over-cap body on the theory that refusing to cut a
        # mandatory block was the honest choice.  It is not: Discord answered 400, a 400 is a
        # non-retryable 4xx, and the message went to stuck/ and was never seen.  The loop's own
        # "auth expired" notice died exactly that way -- 2,925 characters, HTTP 400, delivered to
        # nobody, while the loop sat dead for eight hours.
        #
        # An undeliverable message is worse than a visibly cut one.  So cut, and say precisely how
        # much was cut and why, which leaves the reader able to go and look.
        over = len(body) - cap
        marker = "\n· ⚠ CẮT %d ký tự: khối bắt buộc dài %d, trần %d. Xem đầy đủ trong log." % (
            over, len(body), cap)
        body = body[:max(0, cap - len(marker))] + marker
        return body, [("__mandatory_overflow__", over)]

    for i in optional:
        trial = render(kept + [i])
        marker_room = 80
        if len(trial) + marker_room <= cap:
            kept.append(i)
        else:
            dropped.append((blocks[i][1], len(blocks[i][2])))

    body = render(kept)
    if dropped:
        names = ", ".join("%s(%d ký tự)" % (n, c) for n, c in dropped)
        body = body + "\n· đã bỏ %d khối để vừa giới hạn: %s" % (len(dropped), names)
    return body, dropped


def release_hour(tag):
    """Give the CURRENT hour's `tag` slot back. For a winner that then produced nothing: a mint whose
    POST timed out, or a caller that took the slot and refused to mint (session still alive).
    Measured 2026-09-04: locks mint_12:00/13:00/14:00 were consumed by attempts that minted no link,
    so the daemon read "gate already taken" for three hours and the operator got no link at all.
    A slot given back re-opens the hour for the next attempt; the m1 slot stays a separate tag."""
    import os
    import pathlib
    import time as _t
    path = pathlib.Path(_dirs()["base"]) / "hourly" / ("%s_%d.lock" % (tag, int(_t.time() // 3600)))
    try:
        os.unlink(str(path))
        return True
    except OSError:
        return False


def once_per_hour(tag):
    """True exactly once per clock hour per tag, across EVERY process on this box.

    The m1 hourly rule was enforced twice, once in the auth daemon and once in mint_link, each
    against its own cursor -- so each path was individually compliant and together they sent
    doubles (11:00+11:10, 12:00+12:00, 15:00+15:01 measured 2026-08-29). Two cursors is zero
    cursors. This is one file per (tag, hour) created with O_EXCL: the winner sends, every loser
    -- same process or not, same second or not -- skips. Files older than 2 days are swept here
    so nothing else has to remember to.
    """
    import glob
    import os
    import pathlib
    import time as _t
    hd = pathlib.Path(_dirs()["base"]) / "hourly"
    hd.mkdir(parents=True, exist_ok=True)
    now = _t.time()
    for f in glob.glob(str(hd / ("%s_*.lock" % tag))):
        try:
            if now - os.path.getmtime(f) > 2 * 86400:
                os.unlink(f)
        except OSError:
            pass
    path = hd / ("%s_%d.lock" % (tag, int(now // 3600)))
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False


def enqueue(kind, channel, blocks, dedup_key, verdict_key=None, cls="routine",
            retry_on_unknown=True, meta=None):
    # THE HOURLY LAW FOR m1 LIVES HERE AND ONLY HERE. It was enforced in two callers against two
    # private cursors and the pair sent doubles (11:00+11:10, 12:00+12:00, 15:00+15:01, measured
    # 2026-08-29); a third emitter (msgcat.m1_tap_auth) had no gate at all. Every m1 must pass
    # through this function, so this is the one door the rule can guard completely. Callers must
    # NOT pre-check once_per_hour -- their check would consume the lock and this one would then
    # refuse the same message.
    if kind == "m1" and not once_per_hour("m1"):
        return "suppressed:m1-hourly"
    """Write one message into the spool.  Local only.  Raises OSError if it cannot.

    Returns the msg_id, or None when a verdict_key suppressed it (that is a decision, and it is
    recorded in cursors.json so it is auditable rather than invisible).
    """
    if channel not in CHANNELS:
        raise ValueError("unknown channel %r; known: %s" % (channel, ", ".join(CHANNELS)))
    if cls not in CLASSES:
        raise ValueError("unknown class %r" % (cls,))
    if not dedup_key:
        raise ValueError("dedup_key is required: it is the spool filename and the idempotence key")

    d = ensure_dirs()

    if verdict_key is not None:
        # SUPPRESS ON DELIVERED, NOT ON ENQUEUED.
        #
        # This used to record the verdict here, before anything was sent. A message that then died
        # -- stuck/, 400, a dead credential -- left a cursor saying the operator had been told, so
        # every later copy of that verdict was suppressed FOREVER. It is not hypothetical: the
        # "auth expired" notice has sat in stuck/ since 12:20 and no repeat of it is possible.
        #
        # That is the same failure this rebuild exists to remove, reproduced one layer down inside
        # the rebuild. The cursor is now a two-stage commit: enqueue only suppresses against a
        # verdict that was actually DELIVERED, and the sender commits it (or the spool clears it).
        cur = _read_cursors()
        prev = cur.get(kind)
        if isinstance(prev, dict) and prev.get("committed") and prev.get("verdict") == verdict_key:
            cur.setdefault("__suppressed__", {})
            cur["__suppressed__"][kind] = {
                "verdict_key": verdict_key,
                "at": time.time(),
                "n": cur["__suppressed__"].get(kind, {}).get("n", 0) + 1,
            }
            _write_cursors(cur)
            return None
        cur[kind] = {"verdict": verdict_key, "committed": False, "at": time.time()}
        cur.setdefault("__suppressed__", {}).pop(kind, None)
        _write_cursors(cur)

    body, dropped = assemble(blocks)
    msg_id = sha12(dedup_key) + sha12(kind)[:4]
    seq = next_seq()
    body = body.replace("{seq}", "#%d" % seq)

    rec = {
        "msg_id": msg_id,
        "seq": seq,
        "kind": kind,
        "channel": channel,
        "class": cls,
        "dedup_key": dedup_key,
        "verdict_key": verdict_key,
        "enqueued_at": time.time(),
        "body": body,
        "body_len": len(body),
        "body_sha256_12": sha12(body),
        "truncated": bool(dropped),
        "dropped_blocks": dropped,
        "retry_on_unknown": bool(retry_on_unknown),
        "attempts": 0,
        "meta": meta or {},
    }
    _atomic_write(os.path.join(d["pending"], msg_id + ".json"), json.dumps(rec, ensure_ascii=False))

    day = time.strftime("%Y-%m-%d", time.localtime(rec["enqueued_at"]))
    _atomic_write(os.path.join(d["bodies"], day, msg_id + ".txt"), body)
    return msg_id


def pending():
    d = ensure_dirs()
    out = []
    for name in sorted(os.listdir(d["pending"])):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(d["pending"], name)) as fh:
                out.append(json.load(fh))
        except (OSError, ValueError):
            continue
    return sorted(out, key=lambda r: r.get("seq", 0))


def record_attempt(rec, result, http=None, error=None, extra=None):
    """One row per ATTEMPT, appended.  This is the only reason anything about delivery is knowable.

    There is no back-fill: today, "did health say healthy through the outage?" can be neither
    confirmed nor refuted from anything on either machine, because no sender kept a copy of what it
    sent.  A row here plus bodies/<date>/<msg_id>.txt closes that permanently.
    """
    d = ensure_dirs()
    row = {
        "at": time.time(),
        "msg_id": rec.get("msg_id"),
        "seq": rec.get("seq"),
        "kind": rec.get("kind"),
        "channel": rec.get("channel"),
        "attempt": rec.get("attempts", 0),
        "result": result,
        "http": http,
        "error": error,
        "body_sha256_12": rec.get("body_sha256_12"),
        "body_len": rec.get("body_len"),
        "truncated": rec.get("truncated"),
    }
    row.update(extra or {})
    with open(d["sent"], "a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def commit_verdict(rec):
    """Called by the sender ONLY on a delivered message. Until this runs, the verdict can repeat."""
    kind, vk = rec.get("kind"), rec.get("verdict_key")
    if not vk:
        return
    cur = _read_cursors()
    entry = cur.get(kind)
    if isinstance(entry, dict) and entry.get("verdict") == vk:
        entry["committed"] = True
        entry["delivered_at"] = time.time()
        _write_cursors(cur)


def release_verdict(rec):
    """Called when a message will NEVER be delivered. Clears the cursor so the verdict can fire
    again -- otherwise an undelivered alarm silences its own repeats for good."""
    kind, vk = rec.get("kind"), rec.get("verdict_key")
    if not vk:
        return
    cur = _read_cursors()
    entry = cur.get(kind)
    if isinstance(entry, dict) and entry.get("verdict") == vk and not entry.get("committed"):
        cur.pop(kind, None)
        _write_cursors(cur)


def move(rec, dest):
    d = ensure_dirs()
    src = os.path.join(d["pending"], rec["msg_id"] + ".json")
    dst = os.path.join(d[dest], rec["msg_id"] + ".json")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.replace(src, dst)
    except FileNotFoundError:
        _atomic_write(dst, json.dumps(rec, ensure_ascii=False))


def update(rec):
    d = ensure_dirs()
    _atomic_write(os.path.join(d["pending"], rec["msg_id"] + ".json"),
                  json.dumps(rec, ensure_ascii=False))


def done(rec):
    d = ensure_dirs()
    try:
        os.unlink(os.path.join(d["pending"], rec["msg_id"] + ".json"))
    except FileNotFoundError:
        pass


def stats(window_s=86400):
    """(sent, enqueued, last_success_ts) over the window.  Used by the dead-man carrier line."""
    d = ensure_dirs()
    now = time.time()
    sent = enq = 0
    last_ok = None
    try:
        with open(d["sent"]) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("result") == "sent":
                    if last_ok is None or r.get("at", 0) > last_ok:
                        last_ok = r.get("at")
                    if now - r.get("at", 0) <= window_s:
                        sent += 1
                if r.get("attempt") in (0, 1) and now - r.get("at", 0) <= window_s:
                    enq += 1
    except OSError:
        pass
    return sent, enq, last_ok
