#!/usr/bin/env python3
"""Read the WQ session cookie from the user-logged-in isolated Chrome (CDP Storage.getCookies),
save as wq_cookies.pkl, then verify with a REAL POST /simulations. Auth-bootstrap only — sims
run via the official REST API."""
import json, pickle, socket
import requests, websocket
socket.setdefaulttimeout(30)
H = "https://api.worldquantbrain.com"

ver = requests.get("http://localhost:9222/json/version", timeout=10).json()
ws = websocket.create_connection(ver["webSocketDebuggerUrl"], max_size=None, suppress_origin=True)
ws.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
cookies = []
for _ in range(20):
    m = json.loads(ws.recv())
    if m.get("id") == 1:
        cookies = m["result"]["cookies"]; break
ws.close()

wq = [c for c in cookies if "worldquantbrain" in c.get("domain", "")]
print(f"cookies read: {len(cookies)} total | worldquantbrain: {len(wq)}")
for c in wq:
    print(f"   {c['name']:<20} domain={c['domain']}")
jar = requests.cookies.RequestsCookieJar()
for c in wq:
    jar.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
pickle.dump(jar, open("/Users/kanenguyen/wq_pipeline/state/wq_cookies.pkl", "wb"))

# verify with a real write op
s = requests.Session(); s.headers.update({"Connection": "close"}); s.cookies.update(jar)
print("\nGET /authentication:", s.get(H + "/authentication", timeout=20).status_code)
a = json.load(open("/Users/kanenguyen/wq_pipeline/state/robust_shortlist.json"))[1]
body = {"type": "REGULAR", "settings": {"instrumentType": "EQUITY", "region": a["region"], "universe": a["universe"],
        "delay": 0, "decay": int(a["decay"] or 0), "neutralization": a["neut"], "truncation": float(a["trunc"] or 0.08),
        "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON", "language": "FASTEXPR",
        "visualization": False, "testPeriod": "P0Y0M"}, "regular": a["formula"]}
r = s.post(H + "/simulations", json=body, timeout=30)
print("POST /simulations:", r.status_code, "->", "WRITE-CAPABLE ✓" if r.status_code in (200, 201) else (r.text or "")[:150])
