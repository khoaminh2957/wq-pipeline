"""forge.dsr — Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014). Standard library only.

Every Sharpe ratio here is PER PERIOD (daily) unless the name says `annual`. The platform reports
annualised Sharpe = daily * sqrt(252).

  SR0 = sqrt(V[SR]) * ((1 - g) * Zinv(1 - 1/N) + g * Zinv(1 - 1/(N*e)))        g = Euler gamma
  DSR = Phi[ (SR - SR0) * sqrt(T - 1) / sqrt(1 - s3*SR + (k4 - 1)/4 * SR^2) ]

  T      number of period returns the SR was estimated on
  N      number of trials the candidate was selected from (its selection pool)
  V[SR]  variance of the trials' Sharpe ratios (per period)
  s3     skewness of the returns; k4 kurtosis, NON-excess (a normal has k4 = 3)

SR0 is the Sharpe the best of N pure-luck trials is expected to reach; DSR is the probability that
the candidate's true Sharpe exceeds it. Requirement C13: DSR >= 0.95 is a hard gate.
"""
from __future__ import annotations

import math
from statistics import NormalDist

EULER_GAMMA = 0.5772156649015329
PERIODS_PER_YEAR = 252.0
ANNUALISE = math.sqrt(PERIODS_PER_YEAR)
_NORMAL = NormalDist()


def moments(x):
    """(mean, std, skewness, kurtosis) with population denominators; kurtosis non-excess."""
    n = len(x)
    if n < 2:
        raise ValueError("need at least 2 observations, got %d" % n)
    mean = math.fsum(x) / n
    dev = [v - mean for v in x]
    m2 = math.fsum(d * d for d in dev) / n
    if m2 <= 0.0:
        return mean, 0.0, 0.0, 3.0
    sd = math.sqrt(m2)
    m3 = math.fsum(d ** 3 for d in dev) / n
    m4 = math.fsum(d ** 4 for d in dev) / n
    return mean, sd, m3 / sd ** 3, m4 / sd ** 4


def expected_max_sharpe(var_sr: float, n_trials: int) -> float:
    """SR0: expected maximum Sharpe of `n_trials` zero-skill trials with Sharpe variance `var_sr`.
    Same period units as var_sr. 0 when there is one trial or no spread."""
    if n_trials is None or n_trials <= 1 or var_sr is None or var_sr <= 0.0:
        return 0.0
    n = float(n_trials)
    z1 = _NORMAL.inv_cdf(1.0 - 1.0 / n)
    z2 = _NORMAL.inv_cdf(1.0 - 1.0 / (n * math.e))
    return math.sqrt(var_sr) * ((1.0 - EULER_GAMMA) * z1 + EULER_GAMMA * z2)


def probabilistic_sharpe(sr: float, sr0: float, n_obs: int, skew: float, kurt: float) -> float:
    """P[true SR > sr0] given the sample Sharpe `sr` over `n_obs` returns (Bailey & LdP 2012)."""
    if n_obs < 2:
        raise ValueError("need at least 2 observations, got %d" % n_obs)
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if denom <= 0.0:
        return float("nan")
    z = (sr - sr0) * math.sqrt(n_obs - 1.0) / math.sqrt(denom)
    return _NORMAL.cdf(z)


def var_sr_from_annual_sharpes(sharpes, robust: bool = True) -> float:
    """Per-period V[SR] from a pool of platform (annualised) Sharpe values. 0 for < 2 values.

    ROBUST by default: sd = IQR / 1.349 (exact for a normal). Measured 2026-09-04 on the 24,691-row
    journal: the plain sd of `sharpe` is 3.89 annual because broken formulas report absurd values;
    that put the luck ceiling at ~11 and every ACTIVE alpha at DSR 0.0. The IQR ignores those tails
    while agreeing with the plain sd on a clean pool (test)."""
    vals = sorted(float(s) for s in sharpes if s is not None and not math.isnan(float(s)))
    n = len(vals)
    if n < 2:
        return 0.0
    if robust and n >= 4:
        def q(p):
            k = (n - 1) * p
            lo, hi = int(math.floor(k)), int(math.ceil(k))
            return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)
        sd = (q(0.75) - q(0.25)) / 1.349
        return sd * sd / PERIODS_PER_YEAR
    m = math.fsum(vals) / n
    var_annual = math.fsum((v - m) ** 2 for v in vals) / (n - 1)
    return var_annual / PERIODS_PER_YEAR


def daily_returns_from_curve(curve):
    """Period returns from a cumulative-PnL curve.
    Accepts {date: cum}, [[date, cum], ...] or [cum, ...]. Dates are sorted lexically (ISO dates
    sort correctly); None/NaN points are dropped BEFORE differencing, so a gap merges two periods."""
    if isinstance(curve, dict):
        pts = sorted(curve.items())
    elif curve and isinstance(curve[0], (list, tuple)):
        pts = sorted((p[0], p[1]) for p in curve)
    else:
        pts = list(enumerate(curve))
    cum = []
    for _, v in pts:
        if v is None:
            continue
        v = float(v)
        if math.isnan(v):
            continue
        cum.append(v)
    return [b - a for a, b in zip(cum, cum[1:])]


def evaluate(curve, n_trials: int, var_sr: float, min_obs: int = 250) -> dict:
    """DSR of one cumulative-PnL curve selected from `n_trials` with per-period SR variance
    `var_sr`. Returns a dict; `ok` False with a `reason` when the curve cannot be scored."""
    rets = daily_returns_from_curve(curve)
    t = len(rets)
    if t < min_obs:
        return {"ok": False, "reason": "short", "T": t}
    mean, sd, skew, kurt = moments(rets)
    if sd <= 0.0:
        return {"ok": False, "reason": "flat", "T": t}
    sr = mean / sd
    sr0 = expected_max_sharpe(var_sr, n_trials)
    p = probabilistic_sharpe(sr, sr0, t, skew, kurt)
    return {
        "ok": not math.isnan(p), "T": t, "sr_daily": sr, "sharpe_annual": sr * ANNUALISE,
        "sr0_daily": sr0, "sr0_annual": sr0 * ANNUALISE, "skew": skew, "kurt": kurt,
        "dsr": p, "n_trials": n_trials,
    }
