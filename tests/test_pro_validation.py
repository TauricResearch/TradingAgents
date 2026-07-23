"""Overfitting-aware validation guards (roadmap P2 / track T3): PSR, expected
max Sharpe, deflated Sharpe, and PBO via CSCV. Checked against their defining
properties and simple worked cases."""

import random

import pytest

from tradingagents.pro.backtest.validation import (
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
    probability_of_backtest_overfitting,
)


class TestPSR:
    def test_equals_benchmark_is_half(self):
        assert probabilistic_sharpe_ratio(0.5, 0.5, 250) == pytest.approx(0.5)

    def test_above_benchmark_with_many_obs_is_confident(self):
        assert probabilistic_sharpe_ratio(0.3, 0.0, 500) > 0.95

    def test_more_observations_raise_confidence(self):
        few = probabilistic_sharpe_ratio(0.2, 0.0, 30)
        many = probabilistic_sharpe_ratio(0.2, 0.0, 1000)
        assert 0.5 < few < many

    def test_negative_skew_fat_tails_lower_confidence(self):
        normal = probabilistic_sharpe_ratio(0.3, 0.0, 250, skew=0.0, kurtosis=3.0)
        ugly = probabilistic_sharpe_ratio(0.3, 0.0, 250, skew=-1.5, kurtosis=9.0)
        assert ugly < normal


class TestExpectedMaxSharpe:
    def test_single_trial_no_selection(self):
        assert expected_max_sharpe(0.04, 1) == 0.0

    def test_grows_with_trials_and_variance(self):
        assert expected_max_sharpe(0.04, 100) > expected_max_sharpe(0.04, 10) > 0
        assert expected_max_sharpe(0.09, 50) > expected_max_sharpe(0.04, 50)


class TestDeflatedSharpe:
    def test_single_impressive_trial_is_credible(self):
        # one trial, strong Sharpe, long sample → high DSR
        dsr = deflated_sharpe_ratio(0.35, [0.35], n_obs=750)
        assert dsr > 0.9

    def test_best_of_many_noisy_trials_deflates(self):
        # the same headline Sharpe, but selected as the best of 200 scattered
        # trials → the benchmark rises and the DSR collapses
        rng = random.Random(1)
        trials = [rng.gauss(0.0, 0.25) for _ in range(200)]
        trials[0] = 0.35
        dsr = deflated_sharpe_ratio(0.35, trials, n_obs=750)
        assert dsr < 0.5


class TestPBO:
    def _matrix(self, rows, cols, fn):
        return [[fn(c, t) for t in range(cols)] for c in range(rows)]

    def test_dominant_config_has_low_pbo(self):
        # config 0 is best every period → the IS winner is always the OOS
        # winner → PBO ~ 0
        m = self._matrix(8, 40, lambda c, t: (10.0 if c == 0 else float(c % 3)))
        assert probability_of_backtest_overfitting(m, n_slices=8) < 0.1

    def test_pure_noise_is_overfit_prone(self):
        # no persistent edge: the in-sample winner is just the luckiest sample
        # and reverses out-of-sample → high PBO (the correct "don't deploy"
        # signal), well separated from the dominant-config case (~0)
        rng = random.Random(7)
        m = self._matrix(10, 80, lambda c, t: rng.gauss(0, 1))
        pbo = probability_of_backtest_overfitting(m, n_slices=8)
        assert pbo > 0.5

    def test_too_few_configs_returns_zero(self):
        assert probability_of_backtest_overfitting([[1.0, 2.0, 3.0]]) == 0.0
