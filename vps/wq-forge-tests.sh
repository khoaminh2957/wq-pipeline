#!/bin/bash
# Daily regression of the forge test suite on the VPS (C28). Writes state/forge/tests_last.json;
# the digest reads it. Forge Discord messages are OFF (Khoa 2026-09-04) so a red run is logged, not posted.
cd /opt/wq || exit 1
OUT=$(/opt/wq/venv/bin/python -m pytest forge/tests -q -p no:cacheprovider 2>&1 | tail -3)
RC=${PIPESTATUS[0]}
/opt/wq/venv/bin/python - "$RC" "$OUT" <<'PY'
import json, sys, time, pathlib
rc, out = int(sys.argv[1]), sys.argv[2]
p = pathlib.Path("/opt/wq/state/forge/tests_last.json"); p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps({"ok": rc == 0, "rc": rc, "ts": time.time(), "summary": out[-400:]}))
print("forge tests", "GREEN" if rc == 0 else "RED (rc=%d)" % rc, "|", out.strip().splitlines()[-1] if out.strip() else "")
PY
echo "$OUT" >> /opt/wq/state/forge/tests.log
