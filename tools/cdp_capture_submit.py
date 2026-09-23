#!/usr/bin/env python3
"""Connect to Chrome via DevTools Protocol (port 9222), enable Network tracking on
the competition tab, and print any submit-like request (POST/PUT/PATCH to the
xalpha API, or anything with 'submit'/'event' in the URL) with its full body +
response. The user just clicks Submit in the browser — we capture it.

Writes each captured call to state/submit_capture.jsonl and exits after the first
arena write request (or on timeout)."""
import json, time, urllib.request
import websocket

CDP = "http://127.0.0.1:9222"
OUT = "/Users/kanenguyen/wq_pipeline/state/submit_capture.jsonl"


def pick_tab():
    """Wait for a logged-in xnoquant page tab (not the login page)."""
    for _ in range(240):                 # up to 20 min for the user to log in + navigate
        tabs = json.load(urllib.request.urlopen(CDP + "/json"))
        pages = [t for t in tabs if t.get("type") == "page" and "xnoquant" in (t.get("url") or "")
                 and "dang-nhap" not in (t.get("url") or "") and "login" not in (t.get("url") or "")]
        if pages:
            return pages[0]
        time.sleep(5)
    tabs = json.load(urllib.request.urlopen(CDP + "/json"))
    return [t for t in tabs if t.get("type") == "page"][0]


tab = pick_tab()
print(f"attached to: {tab.get('url')}", flush=True)
ws = websocket.create_connection(tab["webSocketDebuggerUrl"], max_size=None,
                                 origin="http://127.0.0.1:9222")
_id = [0]


def send(method, **params):
    _id[0] += 1
    ws.send(json.dumps({"id": _id[0], "method": method, "params": params}))


send("Network.enable")
print("Network tracking ON — bấm Submit trên trang competition đi. Đang nghe...", flush=True)

req_bodies = {}          # requestId -> request meta
INTEREST = ("submit", "/events/", "/alphas", "/registrations", "compete", "participate")
out_f = open(OUT, "a")
t0 = time.time()
captured = 0

while time.time() - t0 < 7200:
    try:
        ws.settimeout(5)
        msg = json.loads(ws.recv())
    except websocket.WebSocketTimeoutException:
        continue
    except Exception:
        break
    m = msg.get("method")
    p = msg.get("params", {})
    if m == "Network.requestWillBeSent":
        r = p.get("request", {})
        url = r.get("url", "")
        meth = r.get("method", "")
        if meth in ("POST", "PUT", "PATCH", "DELETE") and ("xalpha" in url or any(k in url.lower() for k in INTEREST)):
            req_bodies[p["requestId"]] = {"url": url, "method": meth,
                                          "postData": r.get("postData"),
                                          "headers": {k: v for k, v in (r.get("headers") or {}).items()
                                                      if k.lower() in ("content-type", "authorization")}}
            print(f"\n>>> {meth} {url}", flush=True)
            if r.get("postData"):
                print(f"    body: {r['postData'][:400]}", flush=True)
    elif m == "Network.responseReceived":
        rid = p.get("requestId")
        if rid in req_bodies:
            req_bodies[rid]["status"] = p.get("response", {}).get("status")
    elif m == "Network.loadingFinished":
        rid = p.get("requestId")
        if rid in req_bodies:
            meta = req_bodies.pop(rid)
            # fetch response body
            send("Network.getResponseBody", requestId=rid)
            body = None
            try:
                ws.settimeout(5)
                for _ in range(10):
                    resp = json.loads(ws.recv())
                    if resp.get("id") == _id[0]:
                        body = (resp.get("result") or {}).get("body")
                        break
            except Exception:
                pass
            meta["response"] = (body or "")[:600]
            print(f"    status={meta.get('status')}  resp={str(body)[:300]}", flush=True)
            out_f.write(json.dumps(meta, ensure_ascii=False) + "\n"); out_f.flush()
            captured += 1
            if meta["method"] in ("POST", "PUT", "PATCH") and any(k in meta["url"].lower() for k in ("submit", "event", "alpha")):
                print("\n=== CAPTURED SUBMIT — đủ để tự động hóa ===", flush=True)
                print(json.dumps(meta, ensure_ascii=False, indent=1), flush=True)
                break

print(f"\ndone. captured={captured} calls -> {OUT}", flush=True)
ws.close()
