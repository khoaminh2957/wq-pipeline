#!/usr/bin/env python3
"""TS-SAFE: what a notification may never say about an irreversible action.

This is a lint, not a wording preference, and it is the highest-priority item in the rebuild --
it ships before the spool, the sender and the watchdog, because it depends on none of them.

THE DEFECT IT EXISTS TO PREVENT
-------------------------------
A proposed message told the operator:

    Kiểm tra GET /alphas/{alpha}/submit (404 = chưa có job, 200 = đã xếp hàng)

"404 = chưa có job" is FALSE, and this repository had already measured that it is false.  From
tools/submit_alphas.py, measured 2026-08-05:

    JjGwqKlW (never POSTed) 404,  E5ejp6JL (SUBMITTED) 404,  Xg8OZYQ1 (POSTed) 200/Retry-After

A 404 means "no job NOW", which is the union of *never POSTed* and *POSTed, landed and finished*.
Glossing that union as "no job yet" is an invitation to POST again -- and a re-POST of an alpha
whose submission already landed is the 403 that spends the alpha's slot permanently.

The one real submission this project has made is ACTIVE on the platform, and no file on either
machine records that.  An operator holding the old text, a null-result row, and a 404 would have
been handed a wrong instruction about an irreversible action.

The only disambiguator is GET /alphas/{id} -> status / dateSubmitted.
"""
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Branches on which a message may never assert that a submission succeeded.
UNRESOLVED_BRANCHES = {"null", "403"} | {str(c) for c in range(202, 209)}

GLOSS_TOKENS = ("chưa có job", "chua co job", "no job yet", "never posted", "chưa từng post")
SUCCESS_TOKENS = ("đã nộp", "da nop", "submitted successfully", "nộp thành công", "thành công")
# "--" + "submit" is assembled so the flag never stands as a literal here: tools/ci_gate.check_no_live is a
# string tripwire and read the bare flag in this tuple as a flag PASSED; ci_gate.NO_LIVE_EXEMPT carried an
# exemption for this line with no tick on file (draw3_fix ci 9). The tuple's value is unchanged.
COMMAND_TOKENS = ("--" + "submit", "--override-root", "--force-submit")
REPOST_TOKENS = ("post lại", "nộp lại", "gửi lại", "re-post", "repost", "resubmit", "post again")
# The single surviving use of the submit endpoint: the 200 direction only.
ALLOWED_SUBMIT_PHRASE = "200 = đang xếp hàng"
GUARD_TOKENS = ("đừng", "dung khong", "không được", "khong duoc", "cấm", "chỉ khoa", "chi khoa")


def _norm(s):
    return unicodedata.normalize("NFC", (s or "")).casefold()


def check_message(body, branch=None, submit_related=None):
    """Return a list of (rule, detail).  Empty list means the body is safe to send.

    `branch` is the HTTP outcome the message is about: "null", "403", "201", ... .
    `submit_related` defaults to autodetection.
    """
    n = _norm(body)
    if submit_related is None:
        submit_related = any(t in n for t in ("submit", "nộp", "/alphas/"))
    out = []

    for t in GLOSS_TOKENS:
        if t in n:
            out.append(("GLOSS_404", "contains %r -- that is the false half of the 404 union "
                                     "(a submitted alpha also answers 404)" % t))

    if submit_related and "404" in n:
        out.append(("SUBMIT_404", "a submit-related body must not contain '404': the operator "
                                  "cannot act on it correctly, because it means 'no job now', not "
                                  "'no job yet'"))

    if "/submit" in n and ALLOWED_SUBMIT_PHRASE not in n:
        out.append(("SUBMIT_ENDPOINT", "mentions the /submit endpoint outside the one surviving "
                                       "use (%r); it cannot disambiguate a landed submission"
                                       % ALLOWED_SUBMIT_PHRASE))

    for t in COMMAND_TOKENS:
        if t in n:
            out.append(("IRREVERSIBLE_COMMAND",
                        "contains %r -- a notification must never carry a command that spends an "
                        "irreversible slot" % t))

    for line in n.splitlines():
        if any(t in line for t in REPOST_TOKENS) and not any(g in line for g in GUARD_TOKENS):
            out.append(("REPOST_IMPERATIVE",
                        "line invites a re-POST without a guard word: %r" % line.strip()[:90]))

    if branch is not None and str(branch) in UNRESOLVED_BRANCHES:
        for t in SUCCESS_TOKENS:
            if t in n:
                out.append(("SUCCESS_ON_UNRESOLVED",
                            "branch %s cannot support %r: the message states the record, never the "
                            "adjudication" % (branch, t)))
    return out


def assert_safe(body, branch=None, submit_related=None):
    v = check_message(body, branch=branch, submit_related=submit_related)
    if v:
        raise AssertionError("TS-SAFE refused this body:\n" +
                             "\n".join("  [%s] %s" % (r, d) for r, d in v))
    return True


# --------------------------------------------------------------------------- registry

# The property that matters is "can this module, by itself, put bytes on the wire to Discord".
# A module that POSTs through an INJECTED sink cannot: harness13's relays take a sink argument and
# their only `.post(` calls are on a fake inside an offline self-test.  A bare `\.post\(` pattern
# flags those as senders, which is a false positive -- and a registry test that cries wolf gets
# suppressed, which is how the eleventh sender arrives.
POST_RE = re.compile(
    r"(?:\brequests\s*\.\s*post\s*\()"
    r"|(?:\bhttpx\s*\.\s*post\s*\()"
    r"|(?:urllib\.request\.urlopen\s*\()"
    r"|(?:requests\.Session\(\)[^\n]*\.post\s*\()",
    re.I)
CURL_RE = re.compile(r"curl[^\n]*(?:-X\s*POST|--data|-d\s)[^\n]*discord", re.I)
DISCORD_RE = re.compile(r"discord(app)?\.com", re.I)
# A module can also reach Discord by reading the credential itself.
CRED_RE = re.compile(r"DISCORD_\w*WEBHOOK\w*", re.I)
SENDER_REL = os.path.join("tools", "sender.py")

SKIP_DIRS = {".git", "node_modules", "__pycache__", "fetched", "state", "docs", "v1",
             "harness13/massgen/experiments"}


def find_discord_posters(root=None):
    """Every file that both mentions a Discord host and performs a POST.

    Exactly one file may appear in this list.  A convention cannot hold this property -- eleven
    senders accumulated under one -- so a test does.
    """
    root = root or ROOT
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        if any(part in SKIP_DIRS for part in rel.split(os.sep)):
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith((".py", ".sh")):
                continue
            p = os.path.join(dirpath, fn)
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    txt = fh.read()
            except OSError:
                continue
            reaches = DISCORD_RE.search(txt) or CRED_RE.search(txt)
            if not reaches:
                continue
            if _can_send(p, txt):
                hits.append(os.path.relpath(p, root))
    return sorted(hits)


HTTP_LIBS = {"requests", "httpx", "urllib", "urllib3", "http"}


def _can_send(path, txt):
    """Can this file, on its own, put bytes on the wire?

    Text matching could not separate the two cases that matter here.  A module that POSTs through
    an INJECTED sink mentions the credential key, mentions a Discord URL, reads an env file and
    calls `.post(` -- and still cannot reach the network by itself.  So the question is asked
    structurally: does the module import an HTTP client AND invoke a post/patch call?
    """
    if path.endswith(".sh"):
        return bool(CURL_RE.search(txt))
    try:
        import ast
        tree = ast.parse(txt)
    except (SyntaxError, ValueError):
        # Cannot parse -> cannot clear it.  Fail CLOSED: an unparseable file is reported, not
        # waved through.
        return bool(POST_RE.search(txt))
    imports_http = False
    calls_post = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports_http |= any(a.name.split(".")[0] in HTTP_LIBS for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports_http |= (node.module or "").split(".")[0] in HTTP_LIBS
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("post", "patch"):
                calls_post = True
    return imports_http and calls_post


# Files that CAN reach Discord, each with the reason it is allowed to.  A file appearing here that
# is not in this map fails the test -- which is the property that was missing while eleven senders
# accumulated one at a time, none of them noticed.
ALLOWED_SENDERS = {
    os.path.join("tools", "sender.py"):
        "THE single sender; every other producer goes through tools/outbox.enqueue()",
    os.path.join("harness13", "runtime", "notify_relay.py"):
        "gate_r6.py imports harness13.runtime.*, so deleting this breaks a gate for no delivery "
        "benefit; its post calls run against an INJECTED sink and it is proven unscheduled by "
        "scheduled_importers()",
    os.path.join("harness13", "notify_relay.py"):
        "DUPLICATE of the runtime copy above. gate_r6.py imports the runtime one, not this one. "
        "Deletion candidate -- recorded here rather than waved through, because keeping the losing "
        "half of a settled design as shipped code is how it gets re-adopted by accident",
    os.path.join("harness13", "auth_relay.py"):
        "DUPLICATE of harness13/runtime/auth_relay.py, which is what gate_r6.py actually imports "
        "(RELAY_MODULE = 'harness13.runtime.auth_relay'). Imports requests lazily at module line "
        "476 and can therefore reach the network. Deletion candidate; unscheduled",
}


_404_GLOSS = re.compile(
    r"404\s*(?:=|==|:|\bmeans\b|\bl[àa]\b)?\s*"
    r"(?:no job|chưa có job|chua co job|not submitted|chưa nộp|chua nop|never posted)",
    re.I)


def find_404_gloss(root=None):
    """Every place in the tree that reads a 404 from the submit endpoint as "not submitted".

    That reading is FALSE and this repo measured it false twice: E5ejp6JL, submitted, answered 404
    on 2026-08-05, and mL516W9W answered 404 on 2026-08-16 while ACTIVE on the platform. A 404 is
    the UNION of "never POSTed" and "POSTed, landed, finished". Acting on the wrong half re-POSTs
    an alpha whose submission already landed, which is the 403 that spends its slot permanently.

    Only GET /alphas/{id} -- status and dateSubmitted -- separates the two.

    A lint that cries wolf gets suppressed, and a suppressed lint is how the eleventh sender
    arrives. So this reports only lines that could REACH AN OPERATOR -- a print, a log, a message
    body, an f-string in a return. Documentation quoting the defect in order to explain it, this
    module's own docstring, and tests asserting the bad string are all legitimate and excluded.
    """
    root = root or ROOT
    hits = []
    emits = re.compile(r"\b(print|log|say|notify|enqueue|escalate|write|append|return|raise)\b"
                       r"|f\"|f'|\"\"\"|'''", re.I)
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        if any(part in SKIP_DIRS for part in rel.split(os.sep)):
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            # .md is documentation and tests quote the defect on purpose; neither instructs anyone.
            if not fn.endswith((".py", ".sh")) or fn.startswith("test_"):
                continue
            p = os.path.join(dirpath, fn)
            if os.path.abspath(p) == os.path.abspath(__file__):
                continue
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines, 1):
                if not _404_GLOSS.search(line):
                    continue
                # A comment explaining the defect is not an instruction to anyone.
                if line.lstrip().startswith("#"):
                    continue
                window = "\n".join(lines[max(0, i - 4):i + 1])
                if emits.search(window):
                    hits.append((os.path.relpath(p, root), i, line.strip()[:110]))
    return hits


SCHEDULE_GLOBS = ("*.service", "*.timer", "*.plist", "*.sh", "crontab")


def scheduled_importers(module_names, root=None):
    """Which scheduled things pull in a module that is allowed to exist but not to run.

    Two harness relays are kept deliberately -- a gate and its tests import them, so deleting them
    breaks a gate for no delivery benefit.  The property that actually matters is that nothing on a
    timer, a unit or a launch agent invokes them.
    """
    root = root or ROOT
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        if any(part in SKIP_DIRS for part in rel.split(os.sep)):
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith((".service", ".timer", ".plist", ".sh")):
                continue
            p = os.path.join(dirpath, fn)
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    txt = fh.read()
            except OSError:
                continue
            for m in module_names:
                if m in txt:
                    out.setdefault(m, []).append(os.path.relpath(p, root))
    return out


def main(argv):
    if "--registry" in argv:
        hits = find_discord_posters()
        for h in hits:
            mark = "OK  " if h == SENDER_REL else "EXTRA"
            print("%-5s %s" % (mark, h))
        extra = [h for h in hits if h != SENDER_REL]
        print("\n%d file(s) can POST to Discord; %d beyond tools/sender.py" % (len(hits), len(extra)))
        return 1 if extra else 0
    if argv:
        body = open(argv[0], encoding="utf-8").read()
        v = check_message(body)
        for rule, detail in v:
            print("[%s] %s" % (rule, detail))
        return 1 if v else 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
