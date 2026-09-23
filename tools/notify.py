#!/usr/bin/env python3
"""Front-end over the outbox.  THIS MODULE NO LONGER TOUCHES THE NETWORK.

The command-line interface is unchanged on purpose -- seven call sites in climb_loop.sh plus
mint_when_open.sh keep working with no shell edit -- but a call now writes into the spool and
tools/sender.py is the only thing that puts bytes on the wire.

WHY THE DIRECT POST WAS REMOVED
-------------------------------
  * Eleven senders had accumulated, three webhooks, no shared state, and no sender kept a copy of
    what it sent.  "Did the health reporter say healthy through the outage?" was not merely
    unanswered, it was UNANSWERABLE from anything on either machine.
  * Every call site here was invoked as `... >/dev/null 2>&1`, so the (ok, detail) pair this module
    carefully computed was discarded seven times out of seven.  A function whose result is always
    thrown away is not a safety mechanism.
  * A 2000-character cap was applied with a bare slice, which silently removed the best-alpha block
    from every gem announcement ever sent.  The spool drops whole blocks and names what it dropped.
  * There was no retry and no rate-limit handling anywhere, and one message was lost outright to a
    read timeout.

`post()` is kept as a NAME so a forgotten call site fails loudly instead of silently reintroducing
a second transport.  `post_pinned()` is deleted: it had zero callers on either machine, and keeping
the losing half of a settled design as shipped code is how it gets re-adopted by accident.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import outbox as OB  # noqa: E402


def post(content, title=None, url=None):
    """Removed.  Raises rather than returning, so a missed call site is loud."""
    raise RuntimeError(
        "tools.notify.post() no longer sends. Use tools.outbox.enqueue() (or the notify.py CLI, "
        "which enqueues); tools/sender.py is the only module permitted to POST to Discord.")


def post_pinned(*a, **kw):
    """Removed.  The edit-one-message design lost to post-every-link and had zero callers."""
    raise RuntimeError("tools.notify.post_pinned() was removed; it had no callers.")


def enqueue_cli(text, title=None, url=None, channel="climb", cls="routine"):
    """What the CLI does.  Separated so it is testable without a subprocess."""
    head = ("**%s**\n%s" % (title, text)) if title else text
    if url:
        head += "\n" + url
    blocks = [(0, "head", head)]
    # The dedup key is content-addressed, and the hour is folded in so a genuinely repeated daily
    # message still goes out while an accidental double-call inside one run does not.  The shell
    # variable this replaces lost its value on every process restart and re-announced the same five
    # gems four times.
    key = "cli:%s:%s" % (OB.sha12((title or "") + "|" + text),
                         time.strftime("%Y-%m-%dT%H", time.localtime()))
    return OB.enqueue(kind="cli", channel=channel, blocks=blocks, dedup_key=key, cls=cls)


def main(argv):
    title = url = None
    channel = "climb"
    args = []
    i = 0
    while i < len(argv):
        if argv[i] == "--title":
            title = argv[i + 1]; i += 2
        elif argv[i] == "--url":
            url = argv[i + 1]; i += 2
        elif argv[i] == "--channel":
            channel = argv[i + 1]; i += 2
        else:
            args.append(argv[i]); i += 1
    text = sys.stdin.read() if args[:1] == ["-"] else " ".join(args)
    if not text.strip():
        print("nothing to enqueue")
        return 2
    try:
        msg_id = enqueue_cli(text, title=title, url=url, channel=channel)
    except OSError as exc:
        # The one thing this must never do is fail quietly.  A spool that cannot be written is a
        # notification system that is down, and the operator finds out here or not at all.
        print("ENQUEUE FAILED (%s: %s) -- the message was NOT recorded" % (type(exc).__name__, exc),
              file=sys.stderr)
        return 1
    if msg_id is None:
        print("suppressed: an identical message is already queued this hour")
        return 0
    print("queued %s (delivery is tools/sender.py's job; check state/notify/sent.jsonl)" % msg_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
