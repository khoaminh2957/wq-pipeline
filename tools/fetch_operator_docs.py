#!/usr/bin/env python3
"""Khoa directive: cào TRIỆT ĐỂ mục Learn — full 'show more' documentation cho từng operator.
Probes the documentation endpoint shape on the first operator, then crawls all 85.

Out: fetched/rc/operator_docs/<name>.json   (raw response per operator)
     fetched/rc/operator_docs/_probe.json   (probe results: which URL pattern worked)
Single stream, 429-aware, circuit-breaker. Run only when no sim engine is active.
"""
import sys, json, time, pickle, pathlib
import requests
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config

B = config.WQ_API
OUT = pathlib.Path(__file__).resolve().parent.parent / "fetched" / "rc" / "operator_docs"
OUT.mkdir(parents=True, exist_ok=True)
MIN_GAP = 0.45
MAX_429 = 6

s = requests.Session(); s.headers.update({"Connection": "close"})
s.cookies.update(pickle.load(open(config.COOKIE_PATH, "rb")))
_last = [0.0]; _n429 = [0]


def get(url):
    for _ in range(30):
        dt = time.time() - _last[0]
        if dt < MIN_GAP:
            time.sleep(MIN_GAP - dt)
        _last[0] = time.time()
        try:
            r = s.get(url, timeout=40)
        except Exception:
            time.sleep(3); continue
        if r.status_code == 429:
            _n429[0] += 1
            if _n429[0] > MAX_429:
                raise SystemExit(f"CIRCUIT-BREAK: {_n429[0]}x429")
            w = float(r.headers.get("Retry-After", 8) or 8)
            if w > 600: raise SystemExit("RATE-BAN — S2.5 runbook")
            print(f"  429 #{_n429[0]}, wait {w:.0f}s", flush=True); time.sleep(w + 2); continue
        if r.status_code == 401:
            raise SystemExit("401 — re-auth needed")
        return r
    return None


ops = json.load(open(pathlib.Path(__file__).resolve().parent.parent / "fetched/rc/operators.json"))

# ---- probe phase: find the URL pattern that returns detailed docs ----
probe_op = ops[0]  # 'add', documentation='/operators/add'
patterns = [
    B + probe_op.get("documentation", ""),                          # api/operators/add
    B + "/operators/" + probe_op["name"] + "/documentation",
    B + "/learn" + probe_op.get("documentation", ""),
    B + "/documentation" + probe_op.get("documentation", ""),
    B + "/content" + probe_op.get("documentation", ""),
]
probe_results = []
working = None
for u in patterns:
    r = get(u)
    st = r.status_code if r is not None else None
    body = (r.text or "")[:200] if r is not None else ""
    ctype = r.headers.get("content-type", "") if r is not None else ""
    probe_results.append({"url": u, "status": st, "ctype": ctype, "head": body})
    print(f"PROBE {st} {ctype[:30]} {u}", flush=True)
    if r is not None and st == 200 and body.strip():
        working = u.replace(probe_op["name"], "{name}")
        break
json.dump(probe_results, open(OUT / "_probe.json", "w"), indent=1)
if not working:
    raise SystemExit("NO working doc endpoint — inspect _probe.json, need different approach")
print(f"WORKING PATTERN: {working}", flush=True)

# ---- crawl all 85 ----
ok = fail = 0
for o in ops:
    name = o["name"]
    f = OUT / f"{name}.json"
    if f.exists():
        ok += 1; continue
    r = get(working.replace("{name}", name))
    if r is not None and r.status_code == 200 and (r.text or "").strip():
        try:
            j = r.json()
            json.dump(j, open(f, "w"), ensure_ascii=False, indent=1)
        except Exception:
            f.with_suffix(".html").write_text(r.text)
        ok += 1
        print(f"  {name}: OK", flush=True)
    else:
        fail += 1
        print(f"  {name}: HTTP {r.status_code if r else 'none'}", flush=True)
print(f"DOCS-CRAWL COMPLETE: {ok} ok, {fail} fail -> {OUT}", flush=True)
