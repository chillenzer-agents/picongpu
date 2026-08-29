"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: opencode
License: GPLv3+

Unit tests for the math helpers of the standalone post-simulation
validation framework (lib/python/test/testsuite/Math).
"""

import warnings

import numpy as np
from scipy.constants import c, e, epsilon_0, m_e

with warnings.catch_warnings():
    # importing testsuite falls back to the template config and warns
    warnings.simplefilter("ignore")
    from testsuite.Math import deviation as ts_deviation
    from testsuite.Math import math as ts_math
    from testsuite.Math import physics as ts_physics


class TestGrowthRate:
    def test_exponential_recovers_true_rate(self):
        time = np.arange(50.0)
        gamma_true = 0.7
        f = np.exp(gamma_true * time)
        np.testing.assert_allclose(ts_math.growthRate(f, time), gamma_true, rtol=1e-12)

    def test_exponential_no_half_factor(self):
        # regression test: growthRate used to return Gamma/2
        time = np.arange(50.0)
        f = 2.0**time
        np.testing.assert_allclose(ts_math.growthRate(f, time), np.log(2.0), rtol=1e-12)

    def test_interval_returns_bounds(self):
        time = np.arange(50.0)
        f = 2.0**time
        gamma, start, stop = ts_math.growthRate(f, time, interval=(10.0, 30.0))
        assert start == 10
        assert stop == 30
        np.testing.assert_allclose(gamma, np.log(2.0), rtol=1e-12)


class TestDeviation:
    def test_get_difference(self):
        assert ts_deviation.getDifference(2.0, 5.0) == 3.0
        np.testing.assert_allclose(ts_deviation.getDifference(1.0, np.array([1.5, 2.0])), [0.5, 1.0])

    def test_get_max_difference(self):
        assert ts_deviation.getMaxDifference(2.0, 5.0) == 3.0
        assert ts_deviation.getMaxDifference(np.array([1.0, 3.0]), np.array([1.5, 2.0])) == 1.0
        assert ts_deviation.getMaxDifference(np.ones((2, 3)), np.ones((2, 3)) * 2.0) == 1.0

    def test_get_min_difference(self):
        # regression test: built-in min() raised TypeError on scalars
        assert ts_deviation.getMinDifference(2.0, 2.5) == 0.5
        assert ts_deviation.getMinDifference(np.array([1.0, 3.0]), np.array([1.5, 2.0])) == 0.5
        assert ts_deviation.getMinDifference(np.ones((2, 3)), np.ones((2, 3)) + 2.0) == 2.0

    def test_get_difference_in_percentage_relative_to_theory(self):
        # (theory - max(simulation)) / theory * 100
        assert ts_deviation.getDifferenceInPercentage(2.0, [1.0, 1.5]) == 25.0
        # regression test: built-in max() raised TypeError on scalar simulation
        np.testing.assert_allclose(ts_deviation.getDifferenceInPercentage(2.0, 1.9), 5.0)

    def test_get_acceptance_range(self):
        low, high = ts_deviation.getAcceptanceRange(1.0, 0.2)
        assert low == 0.8
        assert high == 1.2

    def test_get_test_result(self):
        assert ts_deviation.getTestResult(0.5, np.array([0.49, 0.5]), 0.2)
        assert not ts_deviation.getTestResult(0.5, np.array([0.3]), 0.2)


class TestPhysics:
    def test_calculateV_O(self):
        np.testing.assert_allclose(ts_physics.calculateV_O(10.0), c * np.sqrt(1 - 1 / 100))

    def test_calculateBeta(self):
        np.testing.assert_allclose(ts_physics.calculateBeta(gamma=10.0), np.sqrt(0.99))
        np.testing.assert_allclose(ts_physics.calculateBeta(v_0=0.5 * c), 0.5)

    def test_plasmafrequence(self):
        density = 1.0e24
        expected = np.sqrt(density * e**2 / (epsilon_0 * m_e))
        np.testing.assert_allclose(ts_physics.plasmafrequence(density, relativistic=False), expected)
        np.testing.assert_allclose(
            ts_physics.plasmafrequence(density, gamma=2.0, relativistic=True),
            expected / np.sqrt(2.0),
        )
