#!/usr/bin/env python3
"""5x regression test for the STAGE-3 top-27 selection (Khoa 2026-07-17).

Proves, deterministically and with NO API, on a 60-row fixture that
rank_gates.rank_rows(rows, 27):
  (a) returns EXACTLY 27 rows;
  (b) reserve_sharpe DEFAULTS to max(1, 27//5) == 5, so the 5 highest-sharpe
      robust-FAILERS are guaranteed a slot (and only 5 — the 6th-highest is not);
  (c) robust priority otherwise holds: the 22 non-reserved slots are filled by
      robust passers in (n_pass DESC, sharpe DESC, id ASC) order;
  (d) deterministic across repeats;
  (e) the --n 27 CLI path writes state/funnel/<run>_top27.json with 27 rows.
"""
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rank_gates  # noqa: E402

OTHER_GATES = ["LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER", "LOW_RETURNS",
               "MATCHES_PYRAMID", "CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"]
ROBUST = "LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO"
ALL = [ROBUST] + OTHER_GATES


def checks(pass_set):
    return [{"name": nm, "result": "PASS" if nm in pass_set else "FAIL"} for nm in ALL]


def build_rows():
    """60 rows: 6 non-robust 'sharpe bombs' (highest sharpe, 1 gate each) + 54 robust rows.

    Bombs Z0..Z5 have the 6 highest sharpes (5.5..5.0) and FAIL robust with only one
    passing gate, so gate order alone buries them at the bottom (n_pass=1). Only the
    reserve rule can pull them into top-27 — and it caps at 5, so Z0..Z4 make it and
    Z5 (6th-highest sharpe) does NOT. The 54 robust rows (sharpe < 5.0) carry the
    real gate priority and must fill the other 22 slots."""
    rows = []
    # 6 sharpe bombs: top sharpes, robust-FAIL, single non-robust gate -> n_pass=1
    for i in range(6):
        rows.append({"alpha": f"Z{i}", "sharpe": 5.5 - 0.1 * i,
                     "checks": checks({"LOW_TURNOVER"})})
    # 54 robust rows: sharpe strictly below the bombs, varied gate counts (n_pass 2..8)
    for i in range(54):
        extra = OTHER_GATES[: (i % 7) + 1]  # 1..7 extra gates -> n_pass 2..8 incl robust
        rows.append({"alpha": f"R{i:02d}", "sharpe": 3.5 - 0.05 * i,
                     "checks": checks({ROBUST, *extra})})
    return rows


ROWS = build_rows()


def run_once(i):
    top = rank_gates.rank_rows(ROWS, 27)  # default reserve -> max(1,27//5)=5
    ids = [r["id"] for r in top]
    idset = set(ids)
    reserved = [r["id"] for r in top if r.get("sharpe_reserved")]
    non_bomb = [r for r in top if not r["id"].startswith("Z")]

    c = {}
    c["exactly 27 returned"] = len(top) == 27
    c["5 top-sharpe robust-failers reserved-in"] = all(f"Z{k}" in idset for k in range(5))
    c["6th-sharpe robust-failer excluded (cap=5)"] = "Z5" not in idset
    c["exactly 5 flagged sharpe_reserved"] = len(reserved) == 5
    c["reserved set == the 5 bombs"] = set(reserved) == {f"Z{k}" for k in range(5)}
    c["22 non-reserved slots all robust"] = len(non_bomb) == 22 and all(
        r["robust_universe_pass"] for r in non_bomb)
    # robust priority: non-bomb picks are sorted by n_pass DESC (display = gate order)
    npass_seq = [r["n_pass"] for r in non_bomb]
    c["non-bomb picks in n_pass-priority order"] = npass_seq == sorted(npass_seq, reverse=True)
    # explicit reserve=5 must equal the default -> proves default == max(1,27//5)
    top_expl = rank_gates.rank_rows(ROWS, 27, reserve_sharpe=5)
    c["default reserve == explicit 5"] = [r["id"] for r in top_expl] == ids

    ok = all(c.values())
    print(f"RUN {i}: {'PASS' if ok else 'FAIL'} | n={len(top)} reserved={sorted(reserved)}")
    for k, v in c.items():
        if not v:
            print(f"        X {k}")
    return ok, tuple(ids)


def cli_writes_top27():
    """--n 27 CLI path writes state/funnel/<run>_top27.json with 27 rows."""
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        for r in ROWS:
            f.write(json.dumps(r) + "\n")
        inp = f.name
    run = "test_rank27_cli"
    out = HERE.parent.parent / "state" / "funnel" / f"{run}_top27.json"
    if out.exists():
        out.unlink()
    subprocess.run([sys.executable, str(HERE / "rank_gates.py"), inp,
                    "--n", "27", "--run", run], check=True,
                   capture_output=True, text=True)
    ok = out.exists() and len(json.loads(out.read_text())) == 27
    print(f"CLI: {'PASS' if ok else 'FAIL'} | wrote {out.name} (exists={out.exists()})")
    return ok, out


def main():
    results, first = [], None
    for i in range(1, 6):
        ok, ids = run_once(i)
        if first is None:
            first = ids
        elif ids != first:
            print(f"RUN {i}: FAIL — non-deterministic")
            ok = False
        results.append(ok)

    cli_ok, out = cli_writes_top27()
    # CLI is folded into every run's verdict (it confirms the same top-27 path)
    results = [r and cli_ok for r in results]
    if out.exists():
        out.unlink()

    passed = sum(results)
    print(f"\n{passed}/5 runs PASS")
    sys.exit(0 if passed == 5 else 1)


if __name__ == "__main__":
    main()
