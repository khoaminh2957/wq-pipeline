#!/usr/bin/env python3
"""Produce a fresh WorldQuant persona auth link, idempotently.

This is the single most repeated manual sequence in the pipeline -- kill the old flow, clear the
stale URL file, start auth_only.py, wait for the URL to appear, print it. Every step is mechanical,
and getting one wrong wastes a round trip with the only human in the loop.

**The default is to ALWAYS produce a link.** Khoa taps it PRE-EMPTIVELY, before the session dies,
because he is not always free at the moment it expires -- so refusing while the session is still
healthy blocks the exact workflow this tool exists for. The earlier default refused, on the theory
that a new flow invalidates the working session. That was measured FALSE on 2026-08-01, and the
mechanism is plain: state/wq_cookies.pkl is only overwritten when a flow COMPLETES, so the current
cookie keeps working right up to the moment the new one replaces it. Tapping early costs nothing
and buys a full fresh window.

**Measured lifetime: about 4 hours.** Three consecutive observations in the driver logs --
18:28 restored -> 22:28 dead (4h00), 06:30 -> 10:33 (4h03), and the 11:23 cookie ran the same
course. So the useful moment to tap is roughly 3h30 after the last restore, and this prints the
age and the estimated expiry so that call is read off rather than guessed.

A stale state/persona_url.txt is DELETED before starting. Without that the old URL is printed back
and tapped, the tap does nothing, and the session stays 401 while everything downstream reports
auth failures that are not auth failures.

**THE WALL IS CHECKED BEFORE ANYTHING IS DESTROYED.** Minting starts with `pkill auth_only.py` and
`persona_url.txt.unlink()`. If /authentication is refusing, auth_only.py then declines to POST (it
guards) and this script waits 120s and prints "produced no URL" -- but the previous, possibly still
tappable, link is already gone and the reason is nowhere in the output. So the wall is read from
disk FIRST, and a walled run touches nothing and prints WHICH wall is up.

A wall whose expiry the SERVER stated (`Retry-After` present, seven seconds in the only observation
on disk) and a wall with no stated expiry (`BIOMETRICS_THROTTLED`, observed outlasting four
consecutive 1800s client waits) are different facts and are printed differently.

  python3 tools/auth_link.py                # a fresh link, always — the normal case
  python3 tools/auth_link.py --only-if-dead # legacy: skip while the session still answers 200
  python3 tools/auth_link.py --wait 900     # also block until the tap lands, then confirm
"""
import argparse, datetime, json, pathlib, subprocess, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import health_report

ROOT = pathlib.Path(__file__).resolve().parent.parent
ST = ROOT / "state"
URL = ST / "persona_url.txt"
REUSE_S = 25 * 60   # an armed inquiry stays tappable this long before it is worth replacing
STATUS = ST / "auth_status.json"
COOKIES = ST / "wq_cookies.pkl"
LIFETIME_H = 4.0                     # measured — see the module docstring


def authed():
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import submit_alphas as SA
        return SA.session().get("https://api.worldquantbrain.com/users/self",
                                timeout=20).status_code == 200
    except Exception:
        return False


def cookie_age_min():
    try:
        return (time.time() - COOKIES.stat().st_mtime) / 60
    except Exception:
        return None


def report_window(prefix=""):
    age = cookie_age_min()
    if age is None:
        return
    left = LIFETIME_H * 60 - age
    if left > 0:
        exp = (datetime.datetime.now() + datetime.timedelta(minutes=left)).strftime("%H:%M")
        print(f"{prefix}cookie {age:.0f}min old — about {left:.0f}min left, expires ~{exp}")
    else:
        print(f"{prefix}cookie {age:.0f}min old — past the ~{LIFETIME_H:.0f}h mark, expiry due")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-if-dead", action="store_true",
                    help="skip while the session still answers 200 (the pre-2026-08-02 default)")
    ap.add_argument("--force", action="store_true",
                    help="accepted for compatibility — producing a link is now the default")
    ap.add_argument("--wait", type=float, default=0, help="seconds to block waiting for the tap")
    args = ap.parse_args()

    # FIRST, and before any pkill/unlink: is the endpoint refusing? Minting is a POST, and a POST
    # into a wall is the one action this script must never take.
    wall = health_report.auth_wall()
    if wall is not None:
        print(health_report.operator_line())
        print(health_report.wall_line(wall).replace("**", ""))
        print(f"(recorded by {wall['source']}; no link was minted and the armed one was left alone)")
        return 4

    alive = authed()
    if args.only_if_dead and alive:
        print("SESSION OK — skipped because --only-if-dead was given")
        report_window()
        return 0
    report_window("before: ")

    before = COOKIES.stat().st_mtime if COOKIES.exists() else 0

    # REUSE a live inquiry instead of replacing it. Killing auth_only.py invalidates the URL it is
    # serving, so every extra call to this script destroyed the link already sent -- on 2026-08-05
    # four links were issued in 40 minutes and each one killed its predecessor, so any link Khoa
    # scrolled back to was dead by the time he tapped it. The failure looked like "the platform
    # expires links fast" and was entirely self-inflicted.
    # Only the ARMED flow matters: if auth_only.py is still running and its URL is recent, that URL
    # is the one Khoa may be about to tap, and handing back the same string is strictly better than
    # minting a new one.
    alive_flow = subprocess.run(["pgrep", "-f", "tools/auth_only.py"],
                                capture_output=True).returncode == 0
    if alive_flow and URL.exists() and URL.read_text().strip():
        age = time.time() - URL.stat().st_mtime
        if age < REUSE_S:
            print(URL.read_text().strip())
            print(f"(link cu van song, {age/60:.0f} phut tuoi — dung lai thay vi tao moi)")
            return 0

    subprocess.run(["pkill", "-f", "tools/auth_only.py"], capture_output=True)
    time.sleep(1)
    URL.unlink(missing_ok=True)          # a stale URL is worse than none: tapping it does nothing
    log = open(ST / "auth_only.out", "a")
    subprocess.Popen([sys.executable, str(ROOT / "tools/auth_only.py")],
                     stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT))

    for _ in range(60):
        if URL.exists() and URL.read_text().strip():
            break
        time.sleep(2)
    else:
        print("auth_only.py produced no URL in 120s — check state/auth_only.out")
        return 2
    print(URL.read_text().strip())
    if alive:
        print("(session is still live — tapping now just restarts the ~4h window; "
              "nothing breaks in the meantime)")

    if args.wait:
        deadline = time.time() + args.wait
        while time.time() < deadline:
            # Confirm from the COOKIE, not only from the status file: the tap is real once
            # wq_cookies.pkl is rewritten, and that write is what resets the window.
            try:
                if COOKIES.exists() and COOKIES.stat().st_mtime > before:
                    print("AUTHED — cookie refreshed", flush=True)
                    report_window("now: ")
                    return 0
            except Exception:
                pass
            try:
                if json.load(open(STATUS)).get("stage") == "AUTHED":
                    print("AUTHED", flush=True)
                    return 0
            except Exception:
                pass
            time.sleep(5)
        print("still waiting for the tap", flush=True)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
