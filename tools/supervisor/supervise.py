#!/usr/bin/env python3
"""Local-model supervisor: watch the pipeline, run whitelisted fixes, escalate the rest.

DIVISION OF LABOUR, and why it is drawn here:

  code   measures state and raises alerts        (tools/pipeline_status.py — thresholds only)
  model  reads the snapshot, writes the summary, and decides escalate-or-not for unknown codes
  code   executes, from a fixed table            (runbook.json — the model never writes a command)

The model is deliberately kept off the action path. Two incidents in this pipeline were caused by
automation acting without understanding: watchdog.py resurrected a driver on a superseded pool and
blocked the correct one for 25 minutes, and an unattended submitter spent a slot on an alpha whose
cells were both already full. Neither was a model failure — they were failures of authority handed
to a component that could not tell whether its action still made sense.

So: nothing irreversible is reachable from here. No submit, no state deletion. Those escalate.

  python3 tools/supervisor/supervise.py --once --dry-run     # see what it would do
  python3 tools/supervisor/supervise.py --interval 300       # supervise continuously
"""
import argparse, json, pathlib, subprocess, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
RUNBOOK = json.load(open(HERE / "runbook.json"))
OLLAMA = "http://localhost:11434/api/generate"
LOG = ROOT / "state/supervisor.log"
SEEN = ROOT / "state/supervisor_seen.json"
REPEAT_ESCALATE = 5      # same code this many passes running = the fix is not working

SYSTEM = """You are the monitoring tier of an alpha-mining pipeline. You are given a JSON snapshot
and a list of alerts that were computed by code, not by you.

Your job is exactly two things:
1. Write a two-sentence status summary in plain Vietnamese for the operator.
2. For each alert, output the alert code and either "runbook" or "escalate".

Rules you must not break:
- You never invent an alert code and never invent a command.
- Anything touching money, submissions, or deleting state is always "escalate".
- If an alert is not in the runbook map you were given, it is "escalate".
- If the snapshot looks internally inconsistent, say so in the summary and escalate.

Reply with STRICT JSON only: {"summary": "...", "decisions": [{"code": "...", "route": "runbook|escalate"}]}"""


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def snapshot():
    r = subprocess.run([sys.executable, str(ROOT / "tools/pipeline_status.py"), "--json"],
                       capture_output=True, text=True, cwd=str(ROOT))
    return json.loads(r.stdout)


def ask_model(model, snap, timeout=120):
    """Ask the local model to summarise and route. Returns None if it is unavailable or answers
    with something that is not JSON — in which case every alert routes by the table alone, which
    is the safe default rather than a reason to stop."""
    prompt = (f"{SYSTEM}\n\nRUNBOOK MAP (only these codes may route to runbook):\n"
              f"{json.dumps(RUNBOOK['map'], indent=1)}\n\n"
              f"SNAPSHOT:\n{json.dumps(snap, indent=1)[:6000]}\n")
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "format": "json", "options": {"temperature": 0}}).encode()
    try:
        req = urllib.request.Request(OLLAMA, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = json.loads(r.read())["response"]
        return json.loads(raw)
    except Exception as e:
        log(f"model unavailable ({str(e)[:60]}) — routing by table only")
        return None


def route(code, verdict):
    """The TABLE is authoritative. The model may only make a route stricter, never looser: it can
    turn a runbook action into an escalation, but it can never promote an unknown code into one."""
    action = RUNBOOK["map"].get(code, "escalate")
    if verdict == "escalate":
        return "escalate"
    return action


def run_action(name, dry):
    spec = RUNBOOK["actions"].get(name)
    if not spec or not spec.get("cmd"):
        return None
    if dry:
        log(f"    DRY-RUN would execute: {' '.join(spec['cmd'])}")
        return None
    r = subprocess.run(spec["cmd"], capture_output=True, text=True, cwd=str(ROOT))
    out = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
    for line in out[-4:]:
        log(f"    {line}")
    return r.returncode


def _streaks(codes):
    """How many consecutive passes each code has now survived.

    The model has no memory between passes, so on its own it reports the same alert identically
    forever -- 17 passes produced 17 near-identical summaries while nothing changed. An alert that
    keeps coming back is a DIFFERENT fact from one that just appeared: it means the runbook action
    is not fixing it. Counting is code's job, not the model's."""
    try:
        prev = json.load(open(SEEN))
    except Exception:
        prev = {}
    cur = {c: prev.get(c, 0) + 1 for c in codes}
    tmp = SEEN.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(cur, f)
    tmp.replace(SEEN)
    return cur


def one_pass(model, dry):
    snap = snapshot()
    alerts = snap.get("alerts", [])
    streak = _streaks([a["code"] for a in alerts])
    for a in alerts:
        a["consecutive_passes"] = streak.get(a["code"], 1)
    verdicts = {}
    ans = ask_model(model, snap) if alerts else None
    if ans:
        log(f"  model: {ans.get('summary', '')[:300]}")
        for d in ans.get("decisions", []):
            if isinstance(d, dict) and d.get("code"):
                verdicts[d["code"]] = d.get("route")
    if not alerts:
        log("  no alerts")
        return
    escalations = []
    for a in alerts:
        act = route(a["code"], verdicts.get(a["code"]))
        # A runbook action that has run REPEAT_ESCALATE times without clearing its own alert is
        # not a fix. Stop repeating it and hand the problem up.
        if act != "escalate" and a["consecutive_passes"] >= REPEAT_ESCALATE:
            log(f"  {a['code']} unresolved after {a['consecutive_passes']} passes -- "
                f"'{act}' is not fixing it, escalating instead")
            act = "escalate"
        log(f"  [{a['level']}] {a['code']} -> {act}   ({a['detail']})")
        if act == "escalate":
            escalations.append(a)
        else:
            run_action(act, dry)
    if escalations:
        note = ROOT / "state/supervisor_escalations.jsonl"
        with open(note, "a") as f:
            f.write(json.dumps({"ts": snap["ts"], "alerts": escalations,
                                "snapshot": snap}) + "\n")
        log(f"  {len(escalations)} escalation(s) written to {note.name} for the senior supervisor")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--interval", type=float, default=300.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    while True:
        try:
            one_pass(args.model, args.dry_run)
        except Exception as e:
            log(f"supervisor pass failed: {str(e)[:200]}")
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
