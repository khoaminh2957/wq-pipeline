#!/usr/bin/env python3
"""complete_submit.py — complete an async WQB submission: POST /submit ONCE, then poll GET until the
IS+correlation checks are FULLY resolved. Declares SUBMITTED only on a platform-confirmed
ACTIVE/SUBMITTED status with a resolved, FAIL-free check set — never on an empty/unparseable body,
a non-UNSUBMITTED status, or a network error (those were false-success bugs). Enforces the G6 submit
budget (1 POST per alpha, ever). Usage: complete_submit.py <alpha_id> [family]"""
import pickle, requests, time, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from harness.guards import reserve_submit, release_submit, slot_returnable
ROOT = pathlib.Path(__file__).resolve().parent.parent
aid = sys.argv[1]
family = sys.argv[2] if len(sys.argv) > 2 else aid

c = pickle.load(open(ROOT / "state/wq_cookies.pkl", "rb"))
s = requests.Session()
if isinstance(c, dict): s.cookies.update(c)
else:
    for x in c: s.cookies.set_cookie(x)

SUCCESS = {"ACTIVE", "SUBMITTED"}     # platform-confirmed terminal-good statuses ONLY

def status():
    try: return s.get(f"https://api.worldquantbrain.com/alphas/{aid}", timeout=30).json().get("status")
    except Exception: return "?"

def resolved(j):
    """(is_resolved, fail_names). A body with NO checks, or any PENDING/IN_PROGRESS check, is NOT
    resolved — 'no checks present' must never be read as 'all passed'."""
    ch = (j.get("is") or {}).get("checks") or j.get("checks") or []
    if not ch: return False, []
    res = [x.get("result") for x in ch]
    if any(r in (None, "", "PENDING", "IN_PROGRESS", "WARNING_PENDING") for r in res):
        return False, []
    return True, [x.get("name") for x in ch if x.get("result") == "FAIL"]

# G6: one POST per alpha, ever. Reserve the budget ATOMICALLY before POSTing so two concurrent runs
# can't both pass the check; already-reserved -> poll-only (no new POST).

# The two gates that these throttle-friendly paths were missing entirely. Both exist because a real
# gem was destroyed without them:
#   _quota_ok     — the platform's own 4/day counter is readable for FREE before POSTing. Vk35LRM0
#                   (prod 0.696, sharpe 2.36, fitness 1.68) was 403'd into permanent death by
#                   POSTing into an exhausted quota.
#   _fresh_corr_ok— a reserve alpha's stored correlation goes stale the moment a near-twin goes
#                   live: e7x0G7ag read self 0.414 when banked and 0.99 after its twin submitted.
# Audited 2026-08-09: this path had NEITHER, so the G6 reservation was the only thing between the
# command line and an irreversible POST. Fail closed — if a gate cannot be evaluated, do not POST.
def _pre_submit_ok(sess, alpha_id):
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import submit_alphas as SA
    except Exception as e:
        print(f"pre-submit gates unavailable ({e}) -- refusing to POST", flush=True)
        return False
    for name, fn in (("quota", SA._quota_ok), ("fresh-corr", SA._fresh_corr_ok)):
        try:
            res = fn(sess, alpha_id)
        except Exception as e:
            print(f"{name} gate raised ({e}) -- refusing to POST (fail-closed)", flush=True)
            return False
        ok_ = res[0] if isinstance(res, tuple) else res
        if not ok_:
            print(f"{name} gate BLOCKED {alpha_id}: {res} -- not POSTing", flush=True)
            return False
    return True

if not _pre_submit_ok(s, aid):
    print("pre-submit gates refused -- no reservation taken, no POST", flush=True)
    raise SystemExit(4)

ok, why = reserve_submit(aid, family)
if ok:
    try:
        r = s.post(f"https://api.worldquantbrain.com/alphas/{aid}/submit", timeout=40)
    except Exception as e:
        print(f"POST /submit raised ({e}); reservation kept (may have landed), poll-only", flush=True)
    else:
        print(f"POST /submit -> {r.status_code}", flush=True)
        # A blanket 4xx release handed the G6 slot back on a 403 -- and a 403 is an ADJUDICATION,
        # so the alpha was permanently dead while reading as never-submitted. Six alphas were lost
        # that way. Only 408/429, or a 403 whose checks carry ERROR and no FAIL, are returnable.
        if slot_returnable(r.status_code, r.text or ""):
            release_submit(aid)
            print(f"{r.status_code} at POST; reservation released, exiting to retry (re-auth if 401)", flush=True); sys.exit(2)
        if 400 <= r.status_code < 500:
            print(f"{r.status_code} at POST: ADJUDICATED -- this alpha's one POST is spent, "
                  f"reservation KEPT so it can never be re-POSTed", flush=True); sys.exit(3)
        # 2xx accepted / 5xx ambiguous -> reservation stays; polling never re-POSTs
else:
    print(f"G6: {why} -> poll-only, NOT re-POSTing", flush=True)

for i in range(120):                           # GET-only poll, ~10 min; NEVER re-POST
    try:
        r = s.get(f"https://api.worldquantbrain.com/alphas/{aid}/submit", timeout=45)
    except Exception:
        time.sleep(5); continue
    if r.status_code == 200 and r.text:
        try: done, fails = resolved(r.json())
        except Exception: time.sleep(5); continue    # unparseable != resolved
        if done:
            st = status(); good = (not fails) and st in SUCCESS
            print(f"RESOLVED: FAILs={'NONE' if not fails else ','.join(fails)}  status={st}", flush=True)
            print("SUBMITTED ✓" if good else "NOT submitted (blocking FAILs or non-active status)", flush=True)
            sys.exit(0 if good else 1)
    elif r.status_code not in (200, 201, 429):
        print(f"poll {r.status_code}: {r.text[:160]}", flush=True)
    time.sleep(5)

st = status()
print(f"did not resolve in window; final status={st}", flush=True)
sys.exit(0 if st in SUCCESS else 1)
