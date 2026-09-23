#!/usr/bin/env python3
"""Persona re-auth ONLY: trigger biometric, write persona_url.txt, poll until the
user completes it in the browser, then save the session cookie for the crawlers."""
import json, time, socket, pickle, os
from pathlib import Path
from urllib.parse import urljoin
import requests

import auth_backoff

socket.setdefaulttimeout(40)
H = "https://api.worldquantbrain.com"
OUT = Path("/Users/kanenguyen/wq_pipeline/state")


def status(**k):
    json.dump(k, open(OUT / "auth_status.json", "w"))


d = dict(l.split("=", 1) for l in (Path.home() / ".wqbrain_creds").read_text().strip().splitlines() if "=" in l)
s = requests.Session(); s.headers.update({"Connection": "close"}); s.auth = (d["email"], d["password"])

# The wall is read FROM DISK before the first POST. Without this, running auth_only.py during a
# BIOMETRICS_THROTTLED lock both hits a walled endpoint and overwrites the daemon's throttle record
# (below) with a generic AUTH_FAIL that carries no expiry.
try:
    auth_backoff.guard("auth_only")
except auth_backoff.AuthThrottled as e:
    status(stage="THROTTLED", ts=time.time(), **e.block.as_dict())
    raise SystemExit(f"REFUSING to POST /authentication: {e}")

status(stage="auth_start", ts=time.time())
r = s.post(H + "/authentication", timeout=30)
authed = r.status_code in (200, 201)
if r.status_code == 429:
    block = auth_backoff.record_429(r.text, r.headers, source="auth_only")
    status(stage="THROTTLED", ts=time.time(), **block.as_dict())
    raise SystemExit(f"429 from /authentication: {block}")
if not authed and r.status_code == 401 and r.headers.get("WWW-Authenticate") == "persona":
    bio = urljoin(r.url, r.headers.get("Location", ""))
    (OUT / "persona_url.txt").write_text(bio)
    status(stage="await_biometric", persona=bio)
    print(f"PERSONA_URL: {bio}", flush=True)
    for i in range(240):                     # up to 20 min
        time.sleep(5)
        try:
            rr = s.post(bio, timeout=30)
        except Exception:
            continue
        if rr.status_code in (200, 201):
            authed = True
            break
        if rr.status_code == 429:
            # Without this the loop POSTs a walled inquiry 240 times over 20 minutes.
            block = auth_backoff.record_429(rr.text, rr.headers, source="auth_only:poll")
            status(stage="THROTTLED", ts=time.time(), **block.as_dict())
            raise SystemExit(f"429 while polling the persona inquiry: {block}")
if not authed:
    status(stage="AUTH_FAIL", ts=time.time(), code=r.status_code)
    raise SystemExit("auth failed")
auth_backoff.record_success(source="auth_only")
s.auth = None
_ck = OUT / "wq_cookies.pkl"
_tmp = _ck.with_suffix(".pkl.tmp")
with open(_tmp, "wb") as _f:
    pickle.dump(s.cookies, _f)
os.replace(_tmp, _ck)
# sanity: who am I
g = s.get(H + "/users/self", timeout=30)
me = g.json() if g.status_code == 200 else {}
status(stage="AUTHED", user=me.get("id"))
print(f"AUTHED as {me.get('id')} ({me.get('email', '')})", flush=True)
