#!/usr/bin/env python3
"""cdp_browse.py — drive the CDP Chrome (port 9222) to a URL, wait for load, and dump the page's
visible text + links. Injects the WQB `t` token across worldquantbrain.com domains so authenticated
pages work. Usage: python3 tools/cdp_browse.py "<url>" [wait_secs]"""
import json, sys, time, urllib.request, pickle, pathlib
import websocket

CDP = "http://127.0.0.1:9222"
ROOT = pathlib.Path(__file__).resolve().parent.parent

def token():
    c = pickle.load(open(ROOT / "state/wq_cookies.pkl", "rb"))
    if isinstance(c, dict): return c.get("t")
    for x in c:
        if x.name == "t": return x.value
    return None

def new_tab():
    tabs = [t for t in json.load(urllib.request.urlopen(CDP + "/json"))
            if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if not tabs:                                             # create one via PUT (Chrome 150+)
        req = urllib.request.Request(CDP + "/json/new?about:blank", method="PUT")
        urllib.request.urlopen(req)
        tabs = [t for t in json.load(urllib.request.urlopen(CDP + "/json")) if t.get("type") == "page"]
    return tabs[0]

def main(url, wait=8):
    tab = new_tab()
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], max_size=None,
                                     origin="http://127.0.0.1:9222")
    _id = [0]; pend = {}
    def call(method, **params):
        _id[0] += 1; mid = _id[0]
        ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == mid: return m.get("result", {})
    call("Network.enable"); call("Page.enable"); call("Runtime.enable")
    tk = token()
    if tk:
        for dom in (".worldquantbrain.com", ".api.worldquantbrain.com", "support.worldquantbrain.com"):
            call("Network.setCookie", name="t", value=tk, domain=dom, path="/", httpOnly=True, secure=True)
    call("Page.navigate", url=url)
    time.sleep(wait)
    txt = call("Runtime.evaluate", expression="document.body.innerText", returnByValue=True)
    links = call("Runtime.evaluate",
                 expression="JSON.stringify([...document.querySelectorAll('a')].map(a=>[a.innerText.trim(),a.href]).filter(x=>x[0]))",
                 returnByValue=True)
    body = (txt.get("result", {}) or {}).get("value", "") or ""
    lk = (links.get("result", {}) or {}).get("value", "") or "[]"
    print("URL:", url)
    print("=== TEXT ===")
    print(body[:6000])
    print("\n=== LINKS ===")
    try:
        for t, h in json.loads(lk)[:60]:
            if t: print(f"  {t[:60]:62} {h}")
    except Exception: pass
    ws.close()

if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8)
