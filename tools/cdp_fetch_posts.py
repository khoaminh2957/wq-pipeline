#!/usr/bin/env python3
"""cdp_fetch_posts.py — fetch full text (body + visible comments) of the top-N high-vote community
posts from state/funnel/community_ranked.json via the CDP Chrome. Saves each post's raw text to
state/funnel/community_posts_text.json for verified extraction. Usage: cdp_fetch_posts.py [N=20]"""
import json, sys, time, urllib.request, pathlib
import websocket

CDP = "http://127.0.0.1:9222"
ROOT = pathlib.Path(__file__).resolve().parent.parent
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20

posts = json.load(open(ROOT / "state/funnel/community_ranked.json"))[:N]
t = [x for x in json.load(urllib.request.urlopen(CDP + "/json"))
     if x.get("type") == "page" and x.get("webSocketDebuggerUrl")][0]
ws = websocket.create_connection(t["webSocketDebuggerUrl"], max_size=None, origin="http://127.0.0.1:9222")
_id = [0]
def call(m, **p):
    _id[0] += 1; mid = _id[0]
    ws.send(json.dumps({"id": mid, "method": m, "params": p}))
    while True:
        x = json.loads(ws.recv())
        if x.get("id") == mid: return x.get("result", {})
call("Page.enable"); call("Runtime.enable")

out = []
for i, p in enumerate(posts):
    try:
        call("Page.navigate", url=p["url"]); time.sleep(7)
        r = call("Runtime.evaluate", expression="document.body.innerText", returnByValue=True)
        txt = (r.get("result", {}) or {}).get("value", "") or ""
        # trim the Zendesk chrome (nav/footer) — keep the article + comments core
        txt = txt.replace("Skip to main content", "").strip()[:22000]
        out.append({"title": p["title"], "url": p["url"], "votes": p.get("votes"),
                    "comments": p.get("comments"), "text": txt})
        print(f"[{i+1}/{len(posts)}] {p.get('votes')}v  {p['title'][:56]}  ({len(txt)} chars)", flush=True)
    except Exception as e:
        print(f"[{i+1}] FAIL {p['title'][:40]}: {e}", flush=True)
ws.close()
json.dump(out, open(ROOT / "state/funnel/community_posts_text.json", "w"), indent=1, ensure_ascii=False)
print(f"\nsaved {len(out)} posts -> state/funnel/community_posts_text.json")
