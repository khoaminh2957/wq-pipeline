#!/usr/bin/env python3
"""Run the 9 remaining opex example alphas as TRUE single sims (engine re-batches retries →
poison child kills all). Captures per-sim status + exact error message; journals results.
Out: appends state/resim_results.jsonl (old_id=opex_*), prints per-con verdict."""
import json, time, pickle, requests, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config

ROOT = pathlib.Path(__file__).resolve().parent.parent
s = requests.Session(); s.headers.update({"Connection": "close"})
s.cookies.update(pickle.load(open(config.COOKIE_PATH, "rb")))

DEFAULT_IDS = ['opex_hump','opex_if_else','opex_is_nan','opex_kth_element','opex_multiply',
               'opex_power_1','opex_quantile','opex_ts_product','opex_ts_regression']
IDS = sys.argv[1:] or DEFAULT_IDS          # S2.0 patch 6: target ids as CLI args
targets = {t['id']: t for t in json.load(open(ROOT / 'state/opex_targets.json'))}

# launch all 9 as individual sims
sims = {}
for tid in IDS:
    t = targets[tid]
    payload = {'type': 'REGULAR', 'settings': t['settings'], 'regular': t['formula']}
    for attempt in range(6):
        r = s.post(config.WQ_API + '/simulations', json=payload, timeout=40)
        if r.status_code == 429:
            w = float(r.headers.get('Retry-After', 10) or 10); time.sleep(w + 2); continue
        break
    loc = r.headers.get('Location')
    if r.status_code in (200, 201) and loc:
        sims[tid] = loc if loc.startswith('http') else config.WQ_API + loc
        print(f"LAUNCH {tid}: OK", flush=True)
    else:
        print(f"LAUNCH {tid}: HTTP {r.status_code} {(r.text or '')[:150]}", flush=True)
    time.sleep(1.2)

# poll all until terminal
results = {}
deadline = time.time() + 20 * 60
while sims and time.time() < deadline:
    time.sleep(15)
    for tid, url in list(sims.items()):
        try:
            g = s.get(url, timeout=40)
        except Exception:
            continue
        if g.status_code == 429:
            time.sleep(float(g.headers.get('Retry-After', 5) or 5)); continue
        j = g.json() if (g.text or '').strip() else {}
        st = j.get('status')
        if st and st not in ('RUNNING', 'PENDING'):
            results[tid] = j
            del sims[tid]
            msg = j.get('message') or ''
            print(f"DONE {tid}: {st} alpha={j.get('alpha')} msg={str(msg)[:150]}", flush=True)

# S2.0 patch 6: journal sims still pending at the deadline as TIMEOUT rows
for tid in list(sims):
    results[tid] = {'status': 'TIMEOUT', 'alpha': None}

# journal + report
out = open(ROOT / 'state/resim_results.jsonl', 'a')
for tid, j in results.items():
    aid = j.get('alpha')
    row = {'old_id': tid, 'status': j.get('status'), 'alpha': aid, 'message': j.get('message')}
    if aid:
        a = s.get(f"{config.WQ_API}/alphas/{aid}", timeout=40).json()
        iss = a.get('is') or {}
        row.update(sharpe=iss.get('sharpe'), fitness=iss.get('fitness'), turnover=iss.get('turnover'),
                   returns=iss.get('returns'), drawdown=iss.get('drawdown'),
                   checks=[c['name'] for c in (iss.get('checks') or []) if c.get('result') == 'PASS'])
        time.sleep(0.6)
    out.write(json.dumps(row, ensure_ascii=False) + '\n')
out.close()
print(f"SINGLES COMPLETE: {sum(1 for j in results.values() if j.get('alpha'))} OK / {len(results)} done / {len(sims)} timeout", flush=True)
