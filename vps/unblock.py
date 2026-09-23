"""Probe the biometric throttle; the moment it lifts, mint a link and put it in Discord.

Counting an idle machine every five minutes is not monitoring. The pipeline is down for two named
reasons and neither is fixed by observing it: the account carries a DAILY simulation cap until
11:00 local, and the persona endpoint is answering 429 BIOMETRICS_THROTTLED because this daemon
minted a window every 540s indefinitely. So this waits on the wall that can lift early, and turns
the wait into an action the moment it does.
"""
import json, pathlib, time, sys
import requests
from urllib.parse import urljoin

ROOT = pathlib.Path("/opt/wq")
CREDS = pathlib.Path("/root/.wqbrain_creds")
LOG = ROOT / "state/unblock_watch.log"


sys.path.insert(0, str(ROOT / "tools"))


def env_webhook(key):
    """Removed. This module no longer resolves the credential or touches the network.

    It used to POST directly and then log `posted to Discord: HTTP {code}` on ANY response -- so a
    404 from a dead webhook was written into the log as a success. A failure recorded as a success
    is worse than no record at all: it is what let a channel stay dead for 113 days while every
    log on the box said delivery was fine.
    """
    raise RuntimeError("unblock.py no longer sends; it enqueues via tools/outbox.py")


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def main():
    creds = dict(l.split("=", 1) for l in CREDS.read_text().strip().splitlines() if "=" in l)
    for i in range(72):                      # up to 12h, one probe every 10 minutes
        s = requests.Session()
        s.headers.update({"Connection": "close"})
        s.auth = (creds["email"], creds["password"])
        try:
            r = s.post("https://api.worldquantbrain.com/authentication", timeout=30)
        except Exception as e:
            log(f"probe {i}: {type(e).__name__}")
            time.sleep(600); continue
        body = (r.text or "")[:80]
        if r.status_code == 401 and r.headers.get("WWW-Authenticate") == "persona":
            url = urljoin(r.url, r.headers.get("Location", ""))
            (ROOT / "state/auth_link.txt").write_text(url)
            log(f"THROTTLE LIFTED after {i*10} min -> minted {url[-28:]}")
            # The claim "every earlier link in this channel is dead" was an assertion about other
            # messages that this code never checked, and a second minter posts links too. It is
            # replaced by a clock, which is checkable.
            try:
                import outbox as OB
                msg_id = OB.enqueue(
                    kind="unblock", channel="auth",
                    blocks=[(0, "head",
                             "**BRAIN auth — hết chặn**\n{seq} Link mint lúc %s, sống ~10 phút.\n%s"
                             % (time.strftime("%H:%M:%S"), url))],
                    dedup_key="unblock:%s" % OB.sha12(url), cls="attention")
                log(f"queued for delivery: {msg_id} (see state/notify/sent.jsonl for the outcome)")
            except Exception as e:
                # Loud, and honest about what is NOT known: the message was not recorded, so it
                # will not be delivered, and nothing here should imply otherwise.
                log(f"ENQUEUE FAILED ({type(e).__name__}: {e}) -- the link was NOT queued")
            # hand the live inquiry to the daemon by letting it poll: it reads auth_link.txt
            return 0
        log(f"probe {i}: {r.status_code} {body}")
        time.sleep(600)
    log("still throttled after 12h")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
