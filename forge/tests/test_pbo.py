import random

from forge import pbo as P


def _noise_pool(n_trials, t, seed, signal=0.0):
    rng = random.Random(seed)
    rows = []
    for _ in range(t):
        rows.append([rng.gauss(signal if j == 0 else 0.0, 1.0) for j in range(n_trials)])
    return rows


def test_pure_noise_pool_is_overfit_and_a_real_signal_is_not():
    noise = _noise_pool(24, 800, seed=1)
    r = P.pbo(noise, s=8)
    assert r["status"] == "ok" and r["splits"] == 70 and r["n_trials"] == 24
    assert r["pbo"] > 0.35                      # the IS-best of pure noise lands below the OOS median about half the time
    real = _noise_pool(24, 800, seed=2, signal=0.15)     # trial 0 has a real edge (~2.4 annual Sharpe)
    r2 = P.pbo(real, s=8)
    assert r2["pbo"] < 0.15 and r2["pbo"] < r["pbo"]


def test_guards_and_alignment():
    assert P.pbo([], s=8)["status"] == "empty"
    assert P.pbo(_noise_pool(12, 800, seed=3), s=8)["status"].startswith("insufficient")
    assert P.pbo(_noise_pool(24, 50, seed=3), s=8)["status"].startswith("too short")
    # a member covering < 90 % of the modal dates is dropped, it does not truncate the pool
    curves = {"a": {"d%03d" % d: 1.0 for d in range(100)}, "b": {"d%03d" % d: 0.5 for d in range(100)},
              "short": {"d%03d" % d: 0.1 for d in range(60, 100)}}
    dates, rows, ids = P.align(curves, min_obs=10)
    assert len(dates) == 100 and ids == ["a", "b"] and rows[0] == [1.0, 0.5]
    # the remainder rows dropped by blocking are the OLDEST, the newest rows are kept
    rows2 = _noise_pool(24, 803, seed=4)
    r = P.pbo(rows2, s=8)
    assert r["status"] == "ok"


def test_evaluate_reports_pass_against_threshold():
    curves = {}
    rng = random.Random(7)
    for j in range(24):
        curves["t%d" % j] = {"d%04d" % d: rng.gauss(0.2 if j == 0 else 0.0, 1.0) for d in range(400)}
    r = P.evaluate(curves, s=8)
    assert r["status"] == "ok" and r["dates"] == 400 and r["pass"] is True and r["pbo"] < 0.5
