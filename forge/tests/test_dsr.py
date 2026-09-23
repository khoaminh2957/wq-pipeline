import math
import random

import pytest

from forge import dsr


def _normal_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


class TestExpectedMax:
    def test_zero_for_single_trial_or_no_spread(self):
        assert dsr.expected_max_sharpe(1.0, 1) == 0.0
        assert dsr.expected_max_sharpe(0.0, 300) == 0.0
        assert dsr.expected_max_sharpe(1.0, 0) == 0.0
        assert dsr.expected_max_sharpe(None, 5) == 0.0

    def test_monotone_in_trials_and_spread(self):
        vals = [dsr.expected_max_sharpe(1.0, n) for n in (2, 10, 100, 300, 1000, 5000)]
        assert vals == sorted(vals) and len(set(vals)) == len(vals)
        assert dsr.expected_max_sharpe(4.0, 300) == pytest.approx(2 * dsr.expected_max_sharpe(1.0, 300))

    def test_brackets_true_expected_maximum_of_standard_normals(self):
        # E[max of 300 N(0,1)] is about 2.87 (tabulated: n=100 -> 2.508, n=1000 -> 3.241).
        assert 2.7 < dsr.expected_max_sharpe(1.0, 300) < 3.0
        assert 2.4 < dsr.expected_max_sharpe(1.0, 100) < 2.6
        assert 3.1 < dsr.expected_max_sharpe(1.0, 1000) < 3.35


class TestProbabilisticSharpe:
    def test_gaussian_no_trials_reduces_to_normal_cdf(self):
        sr, t = 0.1, 2500
        assert dsr.probabilistic_sharpe(sr, 0.0, t, 0.0, 3.0) == pytest.approx(
            _normal_cdf(sr * math.sqrt(t - 1) / math.sqrt(1 + sr * sr / 2)))

    def test_negative_skew_and_fat_tails_lower_the_probability(self):
        base = dsr.probabilistic_sharpe(0.05, 0.02, 1000, 0.0, 3.0)
        assert dsr.probabilistic_sharpe(0.05, 0.02, 1000, -1.5, 3.0) < base
        assert dsr.probabilistic_sharpe(0.05, 0.02, 1000, 0.0, 12.0) < base
        assert dsr.probabilistic_sharpe(0.05, 0.02, 1000, 0.0, 3.0) > dsr.probabilistic_sharpe(0.05, 0.04, 1000, 0.0, 3.0)

    def test_sharpe_below_luck_ceiling_is_under_one_half(self):
        assert dsr.probabilistic_sharpe(0.05, 0.08, 2500, 0.0, 3.0) < 0.5
        assert dsr.probabilistic_sharpe(0.08, 0.08, 2500, 0.0, 3.0) == pytest.approx(0.5)

    def test_rejects_too_few_observations(self):
        with pytest.raises(ValueError):
            dsr.probabilistic_sharpe(0.1, 0.0, 1, 0.0, 3.0)


class TestMoments:
    def test_normal_sample_has_near_zero_skew_and_kurtosis_three(self):
        rng = random.Random(7)
        x = [rng.gauss(0.0, 1.0) for _ in range(200_000)]
        mean, sd, skew, kurt = dsr.moments(x)
        assert abs(mean) < 0.01 and abs(sd - 1.0) < 0.01
        assert abs(skew) < 0.03 and abs(kurt - 3.0) < 0.1

    def test_flat_series_is_degenerate_not_an_error(self):
        assert dsr.moments([1.0, 1.0, 1.0]) == (1.0, 0.0, 0.0, 3.0)

    def test_var_from_annual_sharpes_is_per_period(self):
        assert dsr.var_sr_from_annual_sharpes([1.0, 1.5, 2.0]) == pytest.approx(0.25 / 252.0)   # n<4: plain sd
        assert dsr.var_sr_from_annual_sharpes([1.0]) == 0.0
        assert dsr.var_sr_from_annual_sharpes([1.0, None, float("nan"), 2.0]) == pytest.approx(0.5 / 252.0)

    def test_robust_variance_ignores_absurd_tails_and_matches_sd_on_clean_data(self):
        rng = random.Random(3)
        clean = [rng.gauss(1.0, 0.4) for _ in range(20_000)]
        plain = dsr.var_sr_from_annual_sharpes(clean, robust=False)
        assert dsr.var_sr_from_annual_sharpes(clean) == pytest.approx(plain, rel=0.05)
        dirty = clean + [-80.0, 55.0, -120.0, 300.0]
        assert dsr.var_sr_from_annual_sharpes(dirty) == pytest.approx(plain, rel=0.05)
        assert dsr.var_sr_from_annual_sharpes(dirty, robust=False) > 10 * plain


class TestCurve:
    def test_dict_curve_is_sorted_by_date_and_differenced(self):
        curve = {"2020-01-03": 2.0, "2020-01-02": 1.0, "2020-01-06": None, "2020-01-07": 3.5}
        assert dsr.daily_returns_from_curve(curve) == [1.0, 1.5]

    def test_list_forms(self):
        assert dsr.daily_returns_from_curve([["2020-01-02", 1.0], ["2020-01-01", 0.0]]) == [1.0]
        assert dsr.daily_returns_from_curve([0.0, 2.0, 1.0]) == [2.0, -1.0]
        assert dsr.daily_returns_from_curve({}) == []

    def test_evaluate_short_or_flat_curve_is_not_ok(self):
        assert dsr.evaluate([float(i) for i in range(10)], 300, 0.01)["reason"] == "short"
        assert dsr.evaluate([1.0] * 300, 300, 0.01)["reason"] == "flat"


class TestEvaluate:
    def _curve(self, annual_sharpe, t, seed=0):
        rng = random.Random(seed)
        mu = annual_sharpe / dsr.ANNUALISE
        cum, x = [0.0], 0.0
        for _ in range(t):
            x += rng.gauss(mu, 1.0)
            cum.append(x)
        return cum

    def test_recovers_annual_sharpe_and_passes_with_one_trial(self):
        out = dsr.evaluate(self._curve(1.7, 2500), n_trials=1, var_sr=0.0)
        assert out["ok"] and out["T"] == 2500
        assert abs(out["sharpe_annual"] - 1.7) < 0.7          # 1 s.e. of an annual Sharpe at T=2500 is ~0.32
        assert out["sr0_annual"] == 0.0 and out["dsr"] > 0.999

    def test_luck_ceiling_lowers_dsr_and_can_fail_a_borderline_candidate(self):
        curve = self._curve(1.3, 1250)
        pool = [rng_s for rng_s in (0.9, 1.0, 1.1, 1.2, 1.3, 0.8, 1.4, 1.05, 0.95, 1.15)]
        var_sr = dsr.var_sr_from_annual_sharpes(pool)
        alone = dsr.evaluate(curve, n_trials=1, var_sr=var_sr)
        crowd = dsr.evaluate(curve, n_trials=300, var_sr=var_sr)
        assert crowd["sr0_annual"] > 0.0 and crowd["dsr"] < alone["dsr"]
        assert crowd["sr0_annual"] == pytest.approx(
            dsr.expected_max_sharpe(var_sr, 300) * dsr.ANNUALISE)
