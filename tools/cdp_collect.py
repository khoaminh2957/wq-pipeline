#!/usr/bin/env python3
"""cdp_collect.py — run a community search in the CDP Chrome and return the REAL result URLs
(decoded from Zendesk /search/click tracking links) for community posts + articles. Usage:
python3 tools/cdp_collect.py "improve alpha" """
import json, sys, time, urllib.request, urllib.parse, base64, re, pickle, pathlib
import websocket

CDP = "http://127.0.0.1:9222"
ROOT = pathlib.Path(__file__).resolve().parent.parent

def token():
    c = pickle.load(open(ROOT / "state/wq_cookies.pkl", "rb"))
    for x in (c if not isinstance(c, dict) else []):
        if x.name == "t": return x.value
    return None

def tab():
    ts = [t for t in json.load(urllib.request.urlopen(CDP + "/json"))
          if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    return ts[0]

def real_url(href):
    """decode the real target URL out of a Zendesk /search/click?data=<base64marshal> link."""
    m = re.search(r"[?&]data=([^&]+)", href)
    if not m: return href if "/community/posts/" in href or "/articles/" in href else None
    try:
        raw = base64.b64decode(urllib.parse.unquote(m.group(1)).split("--")[0] + "===")
        u = re.search(rb"https://support\.worldquantbrain\.com/hc/en-us/(?:community/posts|articles)/[0-9A-Za-z\-]+", raw)
        return u.group(0).decode() if u else None
    except Exception:
        return None

def main(query):
    t = tab()
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], max_size=None, origin="http://127.0.0.1:9222")
    _id = [0]
    def call(method, **p):
        _id[0] += 1; mid = _id[0]
        ws.send(json.dumps({"id": mid, "method": method, "params": p}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == mid: return m.get("result", {})
    call("Page.enable"); call("Runtime.enable")
    url = ("https://support.worldquantbrain.com/hc/en-us/search?filter_by=community&query="
           + urllib.parse.quote(query))
    call("Page.navigate", url=url); time.sleep(7)
    js = (r"JSON.stringify([...document.querySelectorAll('li.search-result-list-item, .search-result')]"
          r".map(li=>{const a=li.querySelector('a');const t=li.innerText.replace(/\s+/g,' ').trim();"
          r"const v=t.match(/(\d+)\s+votes?/i);const c=t.match(/(\d+)\s+comments?/i);"
          r"return{title:a?a.innerText.trim():'',href:a?a.href:'',votes:v?+v[1]:null,comments:c?+c[1]:null};})"
          r".filter(x=>x.title))")
    r = call("Runtime.evaluate", expression=js, returnByValue=True)
    ws.close()
    arr = json.loads((r.get("result", {}) or {}).get("value", "[]"))
    seen, out = set(), []
    for it in arr:
        ru = real_url(it.get("href") or "")
        if ru and ru not in seen and it.get("title") and len(it["title"]) > 8:
            seen.add(ru); out.append({"title": it["title"], "url": ru,
                                      "votes": it.get("votes"), "comments": it.get("comments")})
    print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    main(sys.argv[1])
