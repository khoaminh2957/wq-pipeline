#!/usr/bin/env python3
"""crawl_all_fields.py — fetch EVERY field of ALL USA TOP1000 d1 datasets into one catalog.
Reads state/usa_top1000_d1_datasets.json (the 299 datasets), pages the data-fields endpoint
per dataset, writes state/all_fields_usa_top1000_d1.jsonl incrementally (resumable), and a
_progress.json. Stops cleanly on 401 (re-auth then re-run — completed datasets are skipped)."""
import pickle, requests, json, time, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "state/all_fields_usa_top1000_d1.jsonl"
PROG = ROOT / "state/all_fields_progress.json"

def session():
    c = pickle.load(open(ROOT / "state/wq_cookies.pkl", "rb"))
    s = requests.Session()
    if isinstance(c, dict): s.cookies.update(c)
    else:
        for x in c: s.cookies.set_cookie(x)
    return s

def main():
    datasets = json.load(open(ROOT / "state/usa_top1000_d1_datasets.json"))
    done = set()
    if PROG.exists():
        done = set(json.load(open(PROG)).get("done", []))
    s = session()
    if done and OUT.exists():
        # resume: drop partial rows of any interrupted (not-done) dataset before appending
        kept = []
        for ln in open(OUT):
            try:
                if json.loads(ln).get("dataset") in done:
                    kept.append(ln)
            except ValueError:
                continue
        with open(OUT, "w") as f:
            f.writelines(kept)
        fout = open(OUT, "a")
    else:
        fout = open(OUT, "w")
    total = 0
    for di, d in enumerate(datasets):
        ds = d["id"]
        if ds in done:
            continue
        off = 0; ok = True
        while True:
            url = (f"https://api.worldquantbrain.com/data-fields?instrumentType=EQUITY"
                   f"&region=USA&universe=TOP1000&delay=1&dataset.id={ds}&limit=50&offset={off}")
            try:
                r = s.get(url, timeout=40)
            except Exception as e:
                print(f"[{ds}] net error {e}; retry in 3s", flush=True); time.sleep(3); continue
            if r.status_code == 401:
                print("401 — session expired. re-run tools/auth_only.py then this script.", flush=True)
                json.dump({"done": sorted(done)}, open(PROG, "w")); fout.close(); sys.exit(2)
            if r.status_code == 429:                 # rate limit -> backoff + RETRY (never skip)
                back = 8
                for _ in range(8):
                    print(f"[{ds}] 429 rate-limit; sleep {back}s", flush=True); time.sleep(back)
                    r = s.get(url, timeout=40)
                    if r.status_code != 429: break
                    back = min(back * 2, 120)
            if r.status_code != 200:
                print(f"[{ds}] {r.status_code} {str(r.text)[:60]}; skip dataset", flush=True); ok = False; break
            j = r.json(); res = j.get("results", [])
            if not res: break
            for f in res:
                fout.write(json.dumps({
                    "id": f["id"], "dataset": ds, "category": d.get("category"),
                    "type": f.get("type"), "coverage": f.get("coverage"),
                    "alphaCount": f.get("alphaCount"), "userCount": f.get("userCount"),
                    "description": f.get("description", "")}) + "\n")
                total += 1
            off += 50
            if off >= j.get("count", 0): break
            time.sleep(0.6)                          # base rate (tuned to stay under 429)
        if ok:
            done.add(ds)
            json.dump({"done": sorted(done)}, open(PROG, "w"))
        fout.flush()
        if di % 10 == 0:
            print(f"[{di+1}/{len(datasets)}] {ds}; {total} fields so far", flush=True)
        time.sleep(0.3)
    fout.close()
    print(f"DONE: {len(done)} datasets, {total} fields -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
