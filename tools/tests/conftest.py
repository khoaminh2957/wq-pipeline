"""No test may make a real HTTP POST (architecture round 2, S7-NL; round 1, S7; draw-3 pipeline MINOR 8).

WHY. RULE 1: simulation quota is spent on the VPS only, and a POST to /alphas/<id>/submit is
irreversible. Round 1 found the tests' only backstop was "a hosted runner holds no platform
credential" -- but the data tier runs on the laptop, where `state/wq_cookies.pkl` lives, and the
deploy smoke runs `pytest forge/tests` on the VPS, which runs the live loop. `live=True` appears as
code on 50 lines across 3 test files, docstrings and comments excluded (re-counted 2026-09-23 over
the tokens; a plain grep also counts docstrings, draw3_fix pipeline 5), each safe only because that
test monkeypatched its own transport. One forgotten monkeypatch would POST for real. This guard is the
backstop: for the whole pytest process, a POST through `requests` raises before a socket is opened.

WHERE, AND FOR HOW LONG (draw-3 pipeline MINOR 8). The first version was a FUNCTION-scoped autouse
fixture patching `requests.post`, `Session.post` and `Session.request` for a `str` method. The draw-3
adjudicator showed, in a scratch pytest with only that guard, three POSTs reaching the network
(ConnectionError on example.invalid): one from a MODULE-scoped fixture (it runs before any
function-scoped fixture), `Session().request(b"POST", ...)` (`str(b"POST").upper()` is "B'POST'"),
and `Session.send(prepared)` (never passes through `request`). Re-measured 2026-09-23 with a dead
proxy set: all three ended in ProxyError, i.e. left the process. So the guard now:
  * is installed in `pytest_configure` and never removed while the process lives. For an INITIAL
    conftest -- one pytest loads before collecting: in the directory of a path given on the command
    line or an ancestor of it (`pytest forge/tests`, `pytest tools/tests`, `pytest` at the repository
    root) -- that is before collection, so it covers module- and session-scoped fixtures and
    import-time code alike. A copy pytest meets only while collecting is installed when collection
    reaches its directory, AFTER the modules collected earlier were imported (draw3_fix pipeline 5,
    the adjudicator's probe adj4_initprobe: `pytest other` with the guard only in other/zz/tests, and
    an import-time POST in other/test_early.py, ended in ProxyError through a dead proxy, not in a
    refusal; they found no invocation in this repository that takes that path);
  * sits at the TRANSPORT, `requests.adapters.HTTPAdapter.send` -- the one call every `requests`
    path (`requests.post`, `Session.post`, `Session.request`, `Session.send`) goes through before
    urllib3 opens a socket, as read from requests' own source;
  * matches the method case-insensitively for a `str` and for `bytes`.
GET is untouched. `urllib`, `http.client`, raw urllib3 and raw sockets are NOT covered.

WHY A BaseException. `layered_sim._post_patient` retries ANY `Exception` from a POST (3 tries,
5+10+15 s of sleep; EX-ANTE, read from the code). An Exception would be swallowed and retried; this
one ends the test at the first POST.

A test that needs a POST gives the code a fake session, or monkeypatches the attribute itself (its
own monkeypatch wins for that test only). A test that must see what lies BELOW this guard (a socket
guard of its own, tools/tests/test_auto_submit.py) takes the real method from
`inspect.unwrap(HTTPAdapter.send)` -- functools.wraps records it as `__wrapped__` -- and points its
request at a host that cannot resolve.

The same file lives at /conftest.py, forge/tests/conftest.py and tools/tests/conftest.py: the CI
checkout and /opt/wq carry forge/ and tools/ but not the repository root. Whichever copy pytest
configures first installs the guard; the others see it installed and leave it alone.
"""
import functools


class RealPostFromTest(BaseException):
    """A test reached a real HTTP POST. BaseException so no `except Exception` can retry it."""


def _is_post(method) -> bool:
    if isinstance(method, (bytes, bytearray)):
        method = bytes(method).decode("latin-1")
    return isinstance(method, str) and method.strip().upper() == "POST"


def _refuse_real_http_post():
    try:
        from requests.adapters import HTTPAdapter
    except ImportError:                 # no HTTP client installed: nothing to guard
        return
    real_send = HTTPAdapter.send
    if getattr(real_send, "_refuses_real_post", False):
        return                          # another copy of this file got there first

    @functools.wraps(real_send)
    def send(self, request, *args, **kwargs):
        if _is_post(getattr(request, "method", None)):
            raise RealPostFromTest("a test tried a real HTTP POST to %s; give the code a fake session (S7-NL)"
                                   % getattr(request, "url", None))
        return real_send(self, request, *args, **kwargs)
    send._refuses_real_post = True
    HTTPAdapter.send = send


def pytest_configure(config):
    _refuse_real_http_post()
