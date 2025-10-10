from contextlib import nullcontext
import itertools
import locale
import logging
import re
from packaging.version import parse as parse_version

import numpy as np
from numpy.testing import assert_almost_equal, assert_array_equal
import pytest

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


class TestMaxNLocator:
    basic_data = [
        (20, 100, np.array([20., 40., 60., 80., 100.])),
        (0.001, 0.0001, np.array([0., 0.0002, 0.0004, 0.0006, 0.0008, 0.001])),
        (-1e15, 1e15, np.array([-1.0e+15, -5.0e+14, 0e+00, 5e+14, 1.0e+15])),
        (0, 0.85e-50, np.arange(6) * 2e-51),
        (-0.85e-50, 0, np.arange(-5, 1) * 2e-51),
    ]

    integer_data = [
        (-0.1, 1.1, None, np.array([-1, 0, 1, 2])),
        (-0.1, 0.95, None, np.array([-0.25, 0, 0.25, 0.5, 0.75, 1.0])),
        (1, 55, [1, 1.5, 5, 6, 10], np.array([0, 15, 30, 45, 60])),
    ]

    @pytest.mark.parametrize('vmin, vmax, expected', basic_data)
    def test_basic(self, vmin, vmax, expected):
        loc = mticker.MaxNLocator(nbins=5)
        assert_almost_equal(loc.tick_values(vmin, vmax), expected)

    @pytest.mark.parametrize('vmin, vmax, steps, expected', integer_data)
    def test_integer(self, vmin, vmax, steps, expected):
        loc = mticker.MaxNLocator(nbins=5, integer=True, steps=steps)
        assert_almost_equal(loc.tick_values(vmin, vmax), expected)

    @pytest.mark.parametrize('kwargs, errortype, match', [
        ({'foo': 0}, TypeError,
         re.escape("set_params() got an unexpected keyword argument 'foo'")),
        ({'steps': [2, 1]}, ValueError, "steps argument must be an increasing"),
        ({'steps': 2}, ValueError, "steps argument must be an increasing"),
        ({'steps': [2, 11]}, ValueError, "steps argument must be an increasing"),
    ])
    def test_errors(self, kwargs, errortype, match):
        with pytest.raises(errortype, match=match):
            mticker.MaxNLocator(**kwargs)

    @pytest.mark.parametrize('steps, result', [
        ([1, 2, 10], [1, 2, 10]),
        ([2, 10], [1, 2, 10]),
        ([1, 2], [1, 2, 10]),
        ([2], [1, 2, 10]),
    ])
    def test_padding(self, steps, result):
        loc = mticker.MaxNLocator(steps=steps)
        assert (loc._steps == result).all()


class TestLinearLocator:
    def test_basic(self):
        loc = mticker.LinearLocator(numticks=3)
        test_value = np.array([-0.8, -0.3, 0.2])
        assert_almost_equal(loc.tick_values(-0.8, 0.2), test_value)

    def test_zero_numticks(self):
        loc = mticker.LinearLocator(numticks=0)
        loc.tick_values(-0.8, 0.2) == []

    def test_set_params(self):
        """
        Create linear locator with presets={}, numticks=2 and change it to
        something else. See if change was successful. Should not exception.
        """
        loc = mticker.LinearLocator(numticks=2)
        loc.set_params(numticks=8, presets={(0, 1): []})
        assert loc.numticks == 8
        assert loc.presets == {(0, 1): []}

    def test_presets(self):
        loc = mticker.LinearLocator(presets={(1, 2): [1, 1.25, 1.75],
                                             (0, 2): [0.5, 1.5]})
        assert loc.tick_values(1, 2) == [1, 1.25, 1.75]
        assert loc.tick_values(2, 1) == [1, 1.25, 1.75]
        assert loc.tick_values(0, 2) == [0.5, 1.5]
        assert loc.tick_values(0.0, 2.0) == [0.5, 1.5]
        assert (loc.tick_values(0, 1) == np.linspace(0, 1, 11)).all()


class TestMultipleLocator:
    def test_basic(self):
        loc = mticker.MultipleLocator(base=3.147)
        test_value = np.array([-9.441, -6.294, -3.147, 0., 3.147, 6.294,
                               9.441, 12.588])
        assert_almost_equal(loc.tick_values(-7, 10), test_value)

    def test_basic_with_offset(self):
        loc = mticker.MultipleLocator(base=3.147, offset=1.2)
        test_value = np.array([-8.241, -5.094, -1.947, 1.2, 4.347, 7.494,
                               10.641])
        assert_almost_equal(loc.tick_values(-7, 10), test_value)

    def test_view_limits(self):
        """
        Test basic behavior of view limits.
        """
        with mpl.rc_context({'axes.autolimit_mode': 'data'}):
            loc = mticker.MultipleLocator(base=3.147)
            assert_almost_equal(loc.view_limits(-5, 5), (-5, 5))

    def test_view_limits_round_numbers(self):
        """
        Test that everything works properly with 'round_numbers' for auto
        limit.
        """
        with mpl.rc_context({'axes.autolimit_mode': 'round_numbers'}):
            loc = mticker.MultipleLocator(base=3.147)
            assert_almost_equal(loc.view_limits(-4, 4), (-6.294, 6.294))

    def test_view_limits_round_numbers_with_offset(self):
        """
        Test that everything works properly with 'round_numbers' for auto
        limit.
        """
        with mpl.rc_context({'axes.autolimit_mode': 'round_numbers'}):
            loc = mticker.MultipleLocator(base=3.147, offset=1.3)
            assert_almost_equal(loc.view_limits(-4, 4), (-4.994, 4.447))

    def test_view_limits_single_bin(self):
        """
        Test that 'round_numbers' works properly with a single bin.
        """
        with mpl.rc_context({'axes.autolimit_mode': 'round_numbers'}):
            loc = mticker.MaxNLocator(nbins=1)
            assert_almost_equal(loc.view_limits(-2.3, 2.3), (-4, 4))

    def test_set_params(self):
        """
        Create multiple locator with 0.7 base, and change it to something else.
        See if change was successful.
        """
        mult = mticker.MultipleLocator(base=0.7)
        mult.set_params(base=1.7)
        assert mult._edge.step == 1.7
        mult.set_params(offset=3)
        assert mult._offset == 3


class TestAutoMinorLocator:
    def test_basic(self):
        fig, ax = plt.subplots()
        ax.set_xlim(0, 1.39)
        ax.minorticks_on()
        test_value = np.array([0.05, 0.1, 0.15, 0.25, 0.3, 0.35, 0.45,
                               0.5, 0.55, 0.65, 0.7, 0.75, 0.85, 0.9,
                               0.95, 1.05, 1.1, 1.15, 1.25, 1.3, 1.35])
        assert_almost_equal(ax.xaxis.get_ticklocs(minor=True), test_value)

    # NB: the following values are assuming that *xlim* is [0, 5]
    params = [
        (0, 0),  # no major tick => no minor tick either
        (1, 0)   # a single major tick => no minor tick
    ]

    def test_first_and_last_minorticks(self):
        """
        Test that first and last minor tick appear as expected.
        """
        # This test is related to issue #22331
        fig, ax = plt.subplots()
        ax.set_xlim(-1.9, 1.9)
        ax.xaxis.set_minor_locator(mticker.AutoMinorLocator())
        test_value = np.array([-1.9, -1.8, -1.7, -1.6, -1.4, -1.3, -1.2, -1.1,
                               -0.9, -0.8, -0.7, -0.6, -0.4, -0.3, -0.2, -0.1,
                               0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9, 1.1,
                               1.2, 1.3, 1.4, 1.6, 1.7, 1.8, 1.9])
        assert_almost_equal(ax.xaxis.get_ticklocs(minor=True), test_value)

        ax.set_xlim(-5, 5)
        test_value = np.array([-5.0, -4.5, -3.5, -3.0, -2.5, -1.5, -1.0, -0.5,
                               0.5, 1.0, 1.5, 2.5, 3.0, 3.5, 4.5, 5.0])
        assert_almost_equal(ax.xaxis.get_ticklocs(minor=True), test_value)

    @pytest.mark.parametrize('nb_majorticks, expected_nb_minorticks', params)
    def test_low_number_of_majorticks(
            self, nb_majorticks, expected_nb_minorticks):
        # This test is related to issue #8804
        fig, ax = plt.subplots()
        xlims = (0, 5)  # easier to test the different code paths
        ax.set_xlim(*xlims)
        ax.set_xticks(np.linspace(xlims[0], xlims[1], nb_majorticks))
        ax.minorticks_on()
        ax.xaxis.set_minor_locator(mticker.AutoMinorLocator())
        assert len(ax.xaxis.get_minorticklocs()) == expected_nb_minorticks

    majorstep_minordivisions = [(1, 5),
                                (2, 4),
                                (2.5, 5),
                                (5, 5),
                                (10, 5)]

    # This test is meant to verify the parameterization for
    # test_number_of_minor_ticks
    def test_using_all_default_major_steps(self):
        with mpl.rc_context({'_internal.classic_mode': False}):
            majorsteps = [x[0] for x in self.majorstep_minordivisions]
            np.testing.assert_allclose(majorsteps,
                                       mticker.AutoLocator()._steps)

    @pytest.mark.parametrize('major_step, expected_nb_minordivisions',
                             majorstep_minordivisions)
    def test_number_of_minor_ticks(
            self, major_step, expected_nb_minordivisions):
        fig, ax = plt.subplots()
        xlims = (0, major_step)
        ax.set_xlim(*xlims)
        ax.set_xticks(xlims)
        ax.minorticks_on()
        ax.xaxis.set_minor_locator(mticker.AutoMinorLocator())
        nb_minor_divisions = len(ax.xaxis.get_minorticklocs()) + 1
        assert nb_minor_divisions == expected_nb_minordivisions

    limits = [(0, 1.39), (0, 0.139),
              (0, 0.11e-19), (0, 0.112e-12),
              (-2.0e-07, -3.3e-08), (1.20e-06, 1.42e-06),
              (-1.34e-06, -1.44e-06), (-8.76e-07, -1.51e-06)]

    reference = [
        [0.05, 0.1, 0.15, 0.25, 0.3, 0.35, 0.45, 0.5, 0.55, 0.65, 0.7,
         0.75, 0.85, 0.9, 0.95, 1.05, 1.1, 1.15, 1.25, 1.3, 1.35],
        [0.005, 0.01, 0.015, 0.025, 0.03, 0.035, 0.045, 0.05, 0.055, 0.065,
         0.07, 0.075, 0.085, 0.09, 0.095, 0.105, 0.11, 0.115, 0.125, 0.13,
         0.135],
        [5.00e-22, 1.00e-21, 1.50e-21, 2.50e-21, 3.00e-21, 3.50e-21, 4.50e-21,
         5.00e-21, 5.50e-21, 6.50e-21, 7.00e-21, 7.50e-21, 8.50e-21, 9.00e-21,
         9.50e-21, 1.05e-20, 1.10e-20],
        [5.00e-15, 1.00e-14, 1.50e-14, 2.50e-14, 3.00e-14, 3.50e-14, 4.50e-14,
         5.00e-14, 5.50e-14, 6.50e-14, 7.00e-14, 7.50e-14, 8.50e-14, 9.00e-14,
         9.50e-14, 1.05e-13, 1.10e-13],
        [-1.95e-07, -1.90e-07, -1.85e-07, -1.75e-07, -1.70e-07, -1.65e-07,
         -1.55e-07, -1.50e-07, -1.45e-07, -1.35e-07, -1.30e-07, -1.25e-07,
         -1.15e-07, -1.10e-07, -1.05e-07, -9.50e-08, -9.00e-08, -8.50e-08,
         -7.50e-08, -7.00e-08, -6.50e-08, -5.50e-08, -5.00e-08, -4.50e-08,
         -3.50e-08],
        [1.21e-06, 1.22e-06, 1.23e-06, 1.24e-06, 1.26e-06, 1.27e-06, 1.28e-06,
         1.29e-06, 1.31e-06, 1.32e-06, 1.33e-06, 1.34e-06, 1.36e-06, 1.37e-06,
         1.38e-06, 1.39e-06, 1.41e-06, 1.42e-06],
        [-1.435e-06, -1.430e-06, -1.425e-06, -1.415e-06, -1.410e-06,
         -1.405e-06, -1.395e-06, -1.390e-06, -1.385e-06, -1.375e-06,
         -1.370e-06, -1.365e-06, -1.355e-06, -1.350e-06, -1.345e-06],
        [-1.48e-06, -1.46e-06, -1.44e-06, -1.42e-06, -1.38e-06, -1.36e-06,
         -1.34e-06, -1.32e-06, -1.28e-06, -1.26e-06, -1.24e-06, -1.22e-06,
         -1.18e-06, -1.16e-06, -1.14e-06, -1.12e-06, -1.08e-06, -1.06e-06,
         -1.04e-06, -1.02e-06, -9.80e-07, -9.60e-07, -9.40e-07, -9.20e-07,
         -8.80e-07]]

    additional_data = list(zip(limits, reference))

    @pytest.mark.parametrize('lim, ref', additional_data)
    def test_additional(self, lim, ref):
        fig, ax = plt.subplots()

        ax.minorticks_on()
        ax.grid(True, 'minor', 'y', linewidth=1)
        ax.grid(True, 'major', color='k', linewidth=1)
        ax.set_ylim(lim)

        assert_almost_equal(ax.yaxis.get_ticklocs(minor=True), ref)

    @pytest.mark.parametrize('use_rcparam', [False, True])
    @pytest.mark.parametrize(
        'lim, ref', [
            ((0, 1.39),
             [0.05, 0.1, 0.15, 0.25, 0.3, 0.35, 0.45, 0.5, 0.55, 0.65, 0.7,
              0.75, 0.85, 0.9, 0.95, 1.05, 1.1, 1.15, 1.25, 1.3, 1.35]),
            ((0, 0.139),
             [0.005, 0.01, 0.015, 0.025, 0.03, 0.035, 0.045, 0.05, 0.055,
              0.065, 0.07, 0.075, 0.085, 0.09, 0.095, 0.105, 0.11, 0.115,
              0.125, 0.13, 0.135]),
        ])
    def test_number_of_minor_ticks_auto(self, lim, ref, use_rcparam):
        if use_rcparam:
            context = {'xtick.minor.ndivs': 'auto', 'ytick.minor.ndivs': 'auto'}
            kwargs = {}
        else:
            context = {}
            kwargs = {'n': 'auto'}

        with mpl.rc_context(context):
            fig, ax = plt.subplots()
            ax.set_xlim(*lim)
            ax.set_ylim(*lim)
            ax.xaxis.set_minor_locator(mticker.AutoMinorLocator(**kwargs))
            ax.yaxis.set_minor_locator(mticker.AutoMinorLocator(**kwargs))
            assert_almost_equal(ax.xaxis.get_ticklocs(minor=True), ref)
            assert_almost_equal(ax.yaxis.get_ticklocs(minor=True), ref)

    @pytest.mark.parametrize('use_rcparam', [False, True])
    @pytest.mark.parametrize(
        'n, lim, ref', [
            (2, (0, 4), [0.5, 1.5, 2.5, 3.5]),
            (4, (0, 2), [0.25, 0.5, 0.75, 1.25, 1.5, 1.75]),
            (10, (0, 1), [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]),
        ])
    def test_number_of_minor_ticks_int(self, n, lim, ref, use_rcparam):
        if use_rcparam:
            context = {'xtick.minor.ndivs': n, 'ytick.minor.ndivs': n}
            kwargs = {}
        else:
            context = {}
            kwargs = {'n': n}

        with mpl.rc_context(context):
            fig, ax = plt.subplots()
            ax.set_xlim(*lim)
            ax.set_ylim(*lim)
            ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
            ax.xaxis.set_minor_locator(mticker.AutoMinorLocator(**kwargs))
            ax.yaxis.set_major_locator(mticker.MultipleLocator(1))
            ax.yaxis.set_minor_locator(mticker.AutoMinorLocator(**kwargs))
            assert_almost_equal(ax.xaxis.get_ticklocs(minor=True), ref)
            assert_almost_equal(ax.yaxis.get_ticklocs(minor=True), ref)


class TestLogLocator:
    def test_basic(self):
        loc = mticker.LogLocator(numticks=5)
        with pytest.raises(ValueError):
            loc.tick_values(0, 1000)

        test_value = np.array([1.00000000e-05, 1.00000000e-03, 1.00000000e-01,
                               1.00000000e+01, 1.00000000e+03, 1.00000000e+05,
                               1.00000000e+07, 1.000000000e+09])
        assert_almost_equal(loc.tick_values(0.001, 1.1e5), test_value)

        loc = mticker.LogLocator(base=2)
        test_value = np.array([0.5, 1., 2., 4., 8., 16., 32., 64., 128., 256.])
        assert_almost_equal(loc.tick_values(1, 100), test_value)

    def test_polar_axes(self):
        """
        Polar Axes have a different ticking logic.
        """
        fig, ax = plt.subplots(subplot_kw={'projection': 'polar'})
        ax.set_yscale('log')
        ax.set_ylim(1, 100)
        assert_array_equal(ax.get_yticks(), [10, 100, 1000])

    def test_switch_to_autolocator(self):
        loc = mticker.LogLocator(subs="all")
        assert_array_equal(loc.tick_values(0.45, 0.55),
                           [0.44, 0.46, 0.48, 0.5, 0.52, 0.54, 0.56])
        # check that we *skip* 1.0, and 10, because this is a minor locator
        loc = mticker.LogLocator(subs=np.arange(2, 10))
        assert 1.0 not in loc.tick_values(0.9, 20.)
        assert 10.0 not in loc.tick_values(0.9, 20.)

    def test_set_params(self):
        """
        Create log locator with default value, base=10.0, subs=[1.0],
        numticks=15 and change it to something else.
        See if change was successful. Should not raise exception.
        """
        loc = mticker.LogLocator()
        loc.set_params(numticks=7, subs=[2.0], base=4)
        assert loc.numticks == 7
        assert loc._base == 4
        assert list(loc._subs) == [2.0]

    def test_tick_values_correct(self):
        ll = mticker.LogLocator(subs=(1, 2, 5))
        test_value = np.array([1.e-01, 2.e-01, 5.e-01, 1.e+00, 2.e+00, 5.e+00,
                               1.e+01, 2.e+01, 5.e+01, 1.e+02, 2.e+02, 5.e+02,
                               1.e+03, 2.e+03, 5.e+03, 1.e+04, 2.e+04, 5.e+04,
                               1.e+05, 2.e+05, 5.e+05, 1.e+06, 2.e+06, 5.e+06,
                               1.e+07, 2.e+07, 5.e+07, 1.e+08, 2.e+08, 5.e+08])
        assert_almost_equal(ll.tick_values(1, 1e7), test_value)

    def test_tick_values_not_empty(self):
        mpl.rcParams['_internal.classic_mode'] = False
        ll = mticker.LogLocator(subs=(1, 2, 5))
        test_value = np.array([1.e-01, 2.e-01, 5.e-01, 1.e+00, 2.e+00, 5.e+00,
                               1.e+01, 2.e+01, 5.e+01, 1.e+02, 2.e+02, 5.e+02,
                               1.e+03, 2.e+03, 5.e+03, 1.e+04, 2.e+04, 5.e+04,
                               1.e+05, 2.e+05, 5.e+05, 1.e+06, 2.e+06, 5.e+06,
                               1.e+07, 2.e+07, 5.e+07, 1.e+08, 2.e+08, 5.e+08,
                               1.e+09, 2.e+09, 5.e+09])
        assert_almost_equal(ll.tick_values(1, 1e8), test_value)

    def test_multiple_shared_axes(self):
        rng = np.random.default_rng(19680801)
        dummy_data = [rng.normal(size=100), [], []]
        fig, axes = plt.subplots(len(dummy_data), sharex=True, sharey=True)

        for ax, data in zip(axes.flatten(), dummy_data):
            ax.hist(data, bins=10)
            ax.set_yscale('log', nonpositive='clip')

        for ax in axes.flatten():
            assert all(ax.get_yticks() == axes[0].get_yticks())
            assert ax.get_ylim() == axes[0].get_ylim()


class TestNullLocator:
    def test_set_params(self):
        """
        Create null locator, and attempt to call set_params() on it.
        Should not exception, and should raise a warning.
        """
        loc = mticker.NullLocator()
        with pytest.warns(UserWarning):
            loc.set_params()


class _LogitHelper:
    @staticmethod
    def isclose(x, y):
        return (np.isclose(-np.log(1/x-1), -np.log(1/y-1))
                if 0 < x < 1 and 0 < y < 1 else False)

    @staticmethod
    def assert_almost_equal(x, y):
        ax = np.array(x)
        ay = np.array(y)
        assert np.all(ax > 0) and np.all(ax < 1)
        assert np.all(ay > 0) and np.all(ay < 1)
        lx = -np.log(1/ax-1)
        ly = -np.log(1/ay-1)
        assert_almost_equal(lx, ly)


class TestLogitLocator:
    ref_basic_limits = [
        (5e-2, 1 - 5e-2),
        (5e-3, 1 - 5e-3),
        (5e-4, 1 - 5e-4),
        (5e-5, 1 - 5e-5),
        (5e-6, 1 - 5e-6),
        (5e-7, 1 - 5e-7),
        (5e-8, 1 - 5e-8),
        (5e-9, 1 - 5e-9),
    ]

    ref_basic_major_ticks = [
        1 / (10 ** np.arange(1, 3)),
        1 / (10 ** np.arange(1, 4)),
        1 / (10 ** np.arange(1, 5)),
        1 / (10 ** np.arange(1, 6)),
        1 / (10 ** np.arange(1, 7)),
        1 / (10 ** np.arange(1, 8)),
        1 / (10 ** np.arange(1, 9)),
        1 / (10 ** np.arange(1, 10)),
    ]

    ref_maxn_limits = [(0.4, 0.6), (5e-2, 2e-1), (1 - 2e-1, 1 - 5e-2)]

    @pytest.mark.parametrize(
        "lims, expected_low_ticks",
        zip(ref_basic_limits, ref_basic_major_ticks),
    )
    def test_basic_major(self, lims, expected_low_ticks):
        """
        Create logit locator with huge number of major, and tests ticks.
        """
        expected_ticks = sorted(
            [*expected_low_ticks, 0.5, *(1 - expected_low_ticks)]
        )
        loc = mticker.LogitLocator(nbins=100)
        _LogitHelper.assert_almost_equal(
            loc.tick_values(*lims),
            expected_ticks
        )

    @pytest.mark.parametrize("lims", ref_maxn_limits)
    def test_maxn_major(self, lims):
        """
        When the axis is zoomed, the locator must have the same behavior as
        MaxNLocator.
        """
        loc = mticker.LogitLocator(nbins=100)
        maxn_loc = mticker.MaxNLocator(nbins=100, steps=[1, 2, 5, 10])
        for nbins in (4, 8, 16):
            loc.set_params(nbins=nbins)
            maxn_loc.set_params(nbins=nbins)
            ticks = loc.tick_values(*lims)
            maxn_ticks = maxn_loc.tick_values(*lims)
            assert ticks.shape == maxn_ticks.shape
            assert (ticks == maxn_ticks).all()

    @pytest.mark.parametrize("lims", ref_basic_limits + ref_maxn_limits)
    def test_nbins_major(self, lims):
        """
        Assert logit locator for respecting nbins param.
        """

        basic_needed = int(-np.floor(np.log10(lims[0]))) * 2 + 1
        loc = mticker.LogitLocator(nbins=100)
        for nbins in range(basic_needed, 2, -1):
            loc.set_params(nbins=nbins)
            assert len(loc.tick_values(*lims)) <= nbins + 2

    @pytest.mark.parametrize(
        "lims, expected_low_ticks",
        zip(ref_basic_limits, ref_basic_major_ticks),
    )
    def test_minor(self, lims, expected_low_ticks):
        """
        In large scale, test the presence of minor,
        and assert no minor when major are subsampled.
        """

        expected_ticks = sorted(
            [*expected_low_ticks, 0.5, *(1 - expected_low_ticks)]
        )
        basic_needed = len(expected_ticks)
        loc = mticker.LogitLocator(nbins=100)
        minor_loc = mticker.LogitLocator(nbins=100, minor=True)
        for nbins in range(basic_needed, 2, -1):
            loc.set_params(nbins=nbins)
            minor_loc.set_params(nbins=nbins)
            major_ticks = loc.tick_values(*lims)
            minor_ticks = minor_loc.tick_values(*lims)
            if len(major_ticks) >= len(expected_ticks):
                # no subsample, we must have a lot of minors ticks
                assert (len(major_ticks) - 1) * 5 < len(minor_ticks)
            else:
                # subsample
                _LogitHelper.assert_almost_equal(
                    sorted([*major_ticks, *minor_ticks]), expected_ticks)

    def test_minor_attr(self):
        loc = mticker.LogitLocator(nbins=100)
        assert not loc.minor
        loc.minor = True
        assert loc.minor
        loc.set_params(minor=False)
        assert not loc.minor

    acceptable_vmin_vmax = [
        *(2.5 ** np.arange(-3, 0)),
        *(1 - 2.5 ** np.arange(-3, 0)),
    ]

    @pytest.mark.parametrize(
        "lims",
        [
            (a, b)
            for (a, b) in itertools.product(acceptable_vmin_vmax, repeat=2)
            if a != b
        ],
    )
    def test_nonsingular_ok(self, lims):
        """
        Create logit locator, and test the nonsingular method for acceptable
        value
        """
        loc = mticker.LogitLocator()
        lims2 = loc.nonsingular(*lims)
        assert sorted(lims) == sorted(lims2)

    @pytest.mark.parametrize("okval", acceptable_vmin_vmax)
    def test_nonsingular_nok(self, okval):
        """
        Create logit locator, and test the nonsingular method for non
        acceptable value
        """
        loc = mticker.LogitLocator()
        vmin, vmax = (-1, okval)
        vmin2, vmax2 = loc.nonsingular(vmin, vmax)
        assert vmax2 == vmax
        assert 0 < vmin2 < vmax2
        vmin, vmax = (okval, 2)
        vmin2, vmax2 = loc.nonsingular(vmin, vmax)
        assert vmin2 == vmin
        assert vmin2 < vmax2 < 1


class TestFixedLocator:
    def test_set_params(self):
        """
        Create fixed locator with 5 nbins, and change it to something else.
        See if change was successful.
        Should not exception.
        """
        fixed = mticker.FixedLocator(range(0, 24), nbins=5)
        fixed.set_params(nbins=7)
        assert fixed.nbins == 7


class TestIndexLocator:
    def test_set_params(self):
        """
        Create index locator with 3 base, 4 offset. and change it to something
        else. See if change was successful.
        Should not exception.
        """
        index = mticker.IndexLocator(base=3, offset=4)
        index.set_params(base=7, offset=7)
        assert index._base == 7
        assert index.offset == 7


class TestSymmetricalLogLocator:
    def test_set_params(self):
        """
        Create symmetrical log locator with default subs =[1.0] numticks = 15,
        and change it to something else.
        See if change was successful.
        Should not exception.
        """
        sym = mticker.SymmetricalLogLocator(base=10, linthresh=1)
        sym.set_params(subs=[2.0], numticks=8)
        assert sym._subs == [2.0]
        assert sym.numticks == 8

    @pytest.mark.parametrize(
            'vmin, vmax, expected',
            [
                (0, 1, [0, 1]),
                (-1, 1, [-1, 0, 1]),
            ],
    )
    def test_values(self, vmin, vmax, expected):
        # https://github.com/matplotlib/matplotlib/issues/25945
        sym = mticker.SymmetricalLogLocator(base=10, linthresh=1)
        ticks = sym.tick_values(vmin=vmin, vmax=vmax)
        assert_array_equal(ticks, expected)

    def test_subs(self):
        sym = mticker.SymmetricalLogLocator(base=10, linthresh=1, subs=[2.0, 4.0])
        sym.create_dummy_axis()
        sym.axis.set_view_interval(-10, 10)
        assert_array_equal(sym(), [-20, -40, -2, -4, 0, 2, 4, 20, 40])

    def test_extending(self):
        sym = mticker.SymmetricalLogLocator(base=10, linthresh=1)
        sym.create_dummy_axis()
        sym.axis.set_view_interval(8, 9)
        assert (sym() == [1.0]).all()
        sym.axis.set_view_interval(8, 12)
        assert (sym() == [1.0, 10.0]).all()
        assert sym.view_limits(10, 10) == (1, 100)
        assert sym.view_limits(-10, -10) == (-100, -1)
        assert sym.view_limits(0, 0) == (-0.001, 0.001)


class TestAsinhLocator:
    def test_init(self):
        lctr = mticker.AsinhLocator(linear_width=2.718, numticks=19)
        assert lctr.linear_width == 2.718
        assert lctr.numticks == 19
        assert lctr.base == 10

    def test_set_params(self):
        lctr = mticker.AsinhLocator(linear_width=5,
                                    numticks=17, symthresh=0.125,
                                    base=4, subs=(2.5, 3.25))
        assert lctr.numticks == 17
        assert lctr.symthresh == 0.125
        assert lctr.base == 4
        assert lctr.subs == (2.5, 3.25)

        lctr.set_params(numticks=23)
        assert lctr.numticks == 23
        lctr.set_params(None)
        assert lctr.numticks == 23

        lctr.set_params(symthresh=0.5)
        assert lctr.symthresh == 0.5
        lctr.set_params(symthresh=None)
        assert lctr.symthresh == 0.5

        lctr.set_params(base=7)
        assert lctr.base == 7
        lctr.set_params(base=None)
        assert lctr.base == 7

        lctr.set_params(subs=(2, 4.125))
        assert lctr.subs == (2, 4.125)
        lctr.set_params(subs=None)
        assert lctr.subs == (2, 4.125)
        lctr.set_params(subs=[])
        assert lctr.subs is None

    def test_linear_values(self):
        lctr = mticker.AsinhLocator(linear_width=100, numticks=11, base=0)

        assert_almost_equal(lctr.tick_values(-1, 1),
                            np.arange(-1, 1.01, 0.2))
        assert_almost_equal(lctr.tick_values(-0.1, 0.1),
                            np.arange(-0.1, 0.101, 0.02))
        assert_almost_equal(lctr.tick_values(-0.01, 0.01),
                            np.arange(-0.01, 0.0101, 0.002))

    def test_wide_values(self):
        lctr = mticker.AsinhLocator(linear_width=0.1, numticks=11, base=0)

        assert_almost_equal(lctr.tick_values(-100, 100),
                            [-100, -20, -5, -1, -0.2,
                             0, 0.2, 1, 5, 20, 100])
        assert_almost_equal(lctr.tick_values(-1000, 1000),
                            [-1000, -100, -20, -3, -0.4,
                             0, 0.4, 3, 20, 100, 1000])

    def test_near_zero(self):
        """Check that manually injected zero will supersede nearby tick"""
        lctr = mticker.AsinhLocator(linear_width=100, numticks=3, base=0)

        assert_almost_equal(lctr.tick_values(-1.1, 0.9), [-1.0, 0.0, 0.9])

    def test_fallback(self):
        lctr = mticker.AsinhLocator(1.0, numticks=11)

        assert_almost_equal(lctr.tick_values(101, 102),
                            np.arange(101, 102.01, 0.1))

    def test_symmetrizing(self):
        lctr = mticker.AsinhLocator(linear_width=1, numticks=3,
                                    symthresh=0.25, base=0)
        lctr.create_dummy_axis()

        lctr.axis.set_view_interval(-1, 2)
        assert_almost_equal(lctr(), [-1, 0, 2])

        lctr.axis.set_view_interval(-1, 0.9)
        assert_almost_equal(lctr(), [-1, 0, 1])

        lctr.axis.set_view_interval(-0.85, 1.05)
        assert_almost_equal(lctr(), [-1, 0, 1])

        lctr.axis.set_view_interval(1, 1.1)
        assert_almost_equal(lctr(), [1, 1.05, 1.1])

    def test_base_rounding(self):
        lctr10 = mticker.AsinhLocator(linear_width=1, numticks=8,
                                      base=10, subs=(1, 3, 5))
        assert_almost_equal(lctr10.tick_values(-110, 110),
                            [-500, -300, -100, -50, -30, -10, -5, -3, -1,
                             -0.5, -0.3, -0.1, 0, 0.1, 0.3, 0.5,
                             1, 3, 5, 10, 30, 50, 100, 300, 500])

        lctr5 = mticker.AsinhLocator(linear_width=1, numticks=20, base=5)
        assert_almost_equal(lctr5.tick_values(-1050, 1050),
                            [-625, -125, -25, -5, -1, -0.2, 0,
                             0.2, 1, 5, 25, 125, 625])


class TestScalarFormatter:
    offset_data = [
        (123, 189, 0),
        (-189, -123, 0),
        (12341, 12349, 12340),
        (-12349, -12341, -12340),
        (99999.5, 100010.5, 100000),
        (-100010.5, -99999.5, -100000),
        (99990.5, 100000.5, 100000),
        (-100000.5, -99990.5, -100000),
        (1233999, 1234001, 1234000),
        (-1234001, -1233999, -1234000),
        (1, 1, 1),
        (123, 123, 0),
        # Test cases courtesy of @WeatherGod
        (.4538, .4578, .45),
        (3789.12, 3783.1, 3780),
        (45124.3, 45831.75, 45000),
        (0.000721, 0.0007243, 0.00072),
        (12592.82, 12591.43, 12590),
        (9., 12., 0),
        (900., 1200., 0),
        (1900., 1200., 0),
        (0.99, 1.01, 1),
        (9.99, 10.01, 10),
        (99.99, 100.01, 100),
        (5.99, 6.01, 6),
        (15.99, 16.01, 16),
        (-0.452, 0.492, 0),
        (-0.492, 0.492, 0),
        (12331.4, 12350.5, 12300),
        (-12335.3, 12335.3, 0),
    ]

    use_offset_data = [True, False]

    useMathText_data = [True, False]

    #  (sci_type, scilimits, lim, orderOfMag, fewticks)
    scilimits_data = [
        (False, (0, 0), (10.0, 20.0), 0, False),
        (True, (-2, 2), (-10, 20), 0, False),
        (True, (-2, 2), (-20, 10), 0, False),
        (True, (-2, 2), (-110, 120), 2, False),
        (True, (-2, 2), (-120, 110), 2, False),
        (True, (-2, 2), (-.001, 0.002), -3, False),
        (True, (-7, 7), (0.18e10, 0.83e10), 9, True),
        (True, (0, 0), (-1e5, 1e5), 5, False),
        (True, (6, 6), (-1e5, 1e5), 6, False),
    ]

    cursor_data = [
        [0., "0.000"],
        [0.0123, "0.012"],
        [0.123, "0.123"],
        [1.23,  "1.230"],
        [12.3, "12.300"],
    ]

    format_data = [
        (.1, "1e-1"),
        (.11, "1.1e-1"),
        (1e8, "1e8"),
        (1.1e8, "1.1e8"),
    ]

    @pytest.mark.parametrize('unicode_minus, result',
                             [(True, "\N{MINUS SIGN}1"), (False, "-1")])
    def test_unicode_minus(self, unicode_minus, result):
        mpl.rcParams['axes.unicode_minus'] = unicode_minus
        assert (
            plt.gca().xaxis.get_major_formatter().format_data_short(-1).strip()
            == result)

    @pytest.mark.parametrize('left, right, offset', offset_data)
    def test_offset_value(self, left, right, offset):
        fig, ax = plt.subplots()
        formatter = ax.xaxis.get_major_formatter()

        with (pytest.warns(UserWarning, match='Attempting to set identical')
              if left == right else nullcontext()):
            ax.set_xlim(left, right)
        ax.xaxis._update_ticks()
        assert formatter.offset == offset

        with (pytest.warns(UserWarning, match='Attempting to set identical')
              if left == right else nullcontext()):
            ax.set_xlim(right, left)
        ax.xaxis._update_ticks()
        assert formatter.offset == offset

    @pytest.mark.parametrize('use_offset', use_offset_data)
    def test_use_offset(self, use_offset):
        with mpl.rc_context({'axes.formatter.useoffset': use_offset}):
            tmp_form = mticker.ScalarFormatter()
            assert use_offset == tmp_form.get_useOffset()
            assert tmp_form.offset == 0

    @pytest.mark.parametrize('use_math_text', useMathText_data)
    def test_useMathText(self, use_math_text):
        with mpl.rc_context({'axes.formatter.use_mathtext': use_math_text}):
            tmp_form = mticker.ScalarFormatter()
            assert use_math_text == tmp_form.get_useMathText()

    def test_set_use_offset_float(self):
        tmp_form = mticker.ScalarFormatter()
        tmp_form.set_useOffset(0.5)
        assert not tmp_form.get_useOffset()
        assert tmp_form.offset == 0.5

    def test_use_locale(self):
        conv = locale.localeconv()
        sep = conv['thousands_sep']
        if not sep or conv['grouping'][-1:] in ([], [locale.CHAR_MAX]):
            pytest.skip('Locale does not apply grouping')  # pragma: no cover

        with mpl.rc_context({'axes.formatter.use_locale': True}):
            tmp_form = mticker.ScalarFormatter()
            assert tmp_form.get_useLocale()

            tmp_form.create_dummy_axis()
            tmp_form.axis.set_data_interval(0, 10)
            tmp_form.set_locs([1, 2, 3])
            assert sep in tmp_form(1e9)

    @pytest.mark.parametrize(
        'sci_type, scilimits, lim, orderOfMag, fewticks', scilimits_data)
    def test_scilimits(self, sci_type, scilimits, lim, orderOfMag, fewticks):
        tmp_form = mticker.ScalarFormatter()
        tmp_form.set_scientific(sci_type)
        tmp_form.set_powerlimits(scilimits)
        fig, ax = plt.subplots()
        ax.yaxis.set_major_formatter(tmp_form)
        ax.set_ylim(*lim)
        if fewticks:
            ax.yaxis.set_major_locator(mticker.MaxNLocator(4))

        tmp_form.set_locs(ax.yaxis.get_majorticklocs())
        assert orderOfMag == tmp_form.orderOfMagnitude

    @pytest.mark.parametrize('value, expected', format_data)
    def test_format_data(self, value, expected):
        mpl.rcParams['axes.unicode_minus'] = False
        sf = mticker.ScalarFormatter()
        assert sf.format_data(value) == expected

    @pytest.mark.parametrize('data, expected', cursor_data)
    def test_cursor_precision(self, data, expected):
        fig, ax = plt.subplots()
        ax.set_xlim(-1, 1)  # Pointing precision of 0.001.
        fmt = ax.xaxis.get_major_formatter().format_data_short
        assert fmt(data) == expected

    @pytest.mark.parametrize('data, expected', cursor_data)
    def test_cursor_dummy_axis(self, data, expected):
        # Issue #17624
        sf = mticker.ScalarFormatter()
        sf.create_dummy_axis()
        sf.axis.set_view_interval(0, 10)
        fmt = sf.format_data_short
        assert fmt(data) == expected
        assert sf.axis.get_tick_space() == 9
        assert sf.axis.get_minpos() == 0

    def test_mathtext_ticks(self):
        mpl.rcParams.update({
            'font.family': 'serif',
            'font.serif': 'cmr10',
            'axes.formatter.use_mathtext': False
        })

        if parse_version(pytest.__version__).major < 8:
            with pytest.warns(UserWarning, match='cmr10 font should ideally'):
                fig, ax = plt.subplots()
                ax.set_xticks([-1, 0, 1])
                fig.canvas.draw()
        else:
            with (pytest.warns(UserWarning, match="Glyph 8722"),
                  pytest.warns(UserWarning, match='cmr10 font should ideally')):
                fig, ax = plt.subplots()
                ax.set_xticks([-1, 0, 1])
                fig.canvas.draw()

    def test_cmr10_substitutions(self, caplog):
        mpl.rcParams.update({
            'font.family': 'cmr10',
            'mathtext.fontset': 'cm',
            'axes.formatter.use_mathtext': True,
        })

        # Test that it does not log a warning about missing glyphs.
        with caplog.at_level(logging.WARNING, logger='matplotlib.mathtext'):
            fig, ax = plt.subplots()
            ax.plot([-0.03, 0.05], [40, 0.05])
            ax.set_yscale('log')
            yticks = [0.02, 0.3, 4, 50]
            formatter = mticker.LogFormatterSciNotation()
            ax.set_yticks(yticks, map(formatter, yticks))
            fig.canvas.draw()
            assert not caplog.text

    def test_empty_locs(self):
        sf = mticker.ScalarFormatter()
        sf.set_locs([])
        assert sf(0.5) == ''


class TestLogFormatterExponent:
    param_data = [
        (True, 4, np.arange(-3, 4.0), np.arange(-3, 4.0),
         ['-3', '-2', '-1', '0', '1', '2', '3']),
        # With labelOnlyBase=False, non-integer powers should be nicely
        # formatted.
        (False, 10, np.array([0.1, 0.00001, np.pi, 0.2, -0.2, -0.00001]),
         range(6), ['0.1', '1e-05', '3.14', '0.2', '-0.2', '-1e-05']),
        (False, 50, np.array([3, 5, 12, 42], dtype=float), range(6),
         ['3', '5', '12', '42']),
    ]

    base_data = [2.0, 5.0, 10.0, np.pi, np.e]

    @pytest.mark.parametrize(
            'labelOnlyBase, exponent, locs, positions, expected', param_data)
    @pytest.mark.parametrize('base', base_data)
    def test_basic(self, labelOnlyBase, base, exponent, locs, positions,
                   expected):
        formatter = mticker.LogFormatterExponent(base=base,
                                                 labelOnlyBase=labelOnlyBase)
        formatter.create_dummy_axis()
        formatter.axis.set_view_interval(1, base**exponent)
        vals = base**locs
        labels = [formatter(x, pos) for (x, pos) in zip(vals, positions)]
        expected = [label.replace('-', '\N{Minus Sign}') for label in expected]
        assert labels == expected

    def test_blank(self):
        # Should be a blank string for non-integer powers if labelOnlyBase=True
        formatter = mticker.LogFormatterExponent(base=10, labelOnlyBase=True)
        formatter.create_dummy_axis()
        formatter.axis.set_view_interval(1, 10)
        assert formatter(10**0.1) == ''


class TestLogFormatterMathtext:
    fmt = mticker.LogFormatterMathtext()
    test_data = [
        (0, 1, '$\\mathdefault{10^{0}}$'),
        (0, 1e-2, '$\\mathdefault{10^{-2}}$'),
        (0, 1e2, '$\\mathdefault{10^{2}}$'),
        (3, 1, '$\\mathdefault{1}$'),
        (3, 1e-2, '$\\mathdefault{0.01}$'),
        (3, 1e2, '$\\mathdefault{100}$'),
        (3, 1e-3, '$\\mathdefault{10^{-3}}$'),
        (3, 1e3, '$\\mathdefault{10^{3}}$'),
    ]

    @pytest.mark.parametrize('min_exponent, value, expected', test_data)
    def test_min_exponent(self, min_exponent, value, expected):
        with mpl.rc_context({'axes.formatter.min_exponent': min_exponent}):
            assert self.fmt(value) == expected


class TestLogFormatterSciNotation:
    test_data = [
        (2, 0.03125, '$\\mathdefault{2^{-5}}$'),
        (2, 1, '$\\mathdefault{2^{0}}$'),
        (2, 32, '$\\mathdefault{2^{5}}$'),
        (2, 0.0375, '$\\mathdefault{1.2\\times2^{-5}}$'),
        (2, 1.2, '$\\mathdefault{1.2\\times2^{0}}$'),
        (2, 38.4, '$\\mathdefault{1.2\\times2^{5}}$'),
        (10, -1, '$\\mathdefault{-10^{0}}$'),
        (10, 1e-05, '$\\mathdefault{10^{-5}}$'),
        (10, 1, '$\\mathdefault{10^{0}}$'),
        (10, 100000, '$\\mathdefault{10^{5}}$'),
        (10, 2e-05, '$\\mathdefault{2\\times10^{-5}}$'),
        (10, 2, '$\\mathdefault{2\\times10^{0}}$'),
        (10, 200000, '$\\mathdefault{2\\times10^{5}}$'),
        (10, 5e-05, '$\\mathdefault{5\\times10^{-5}}$'),
        (10, 5, '$\\mathdefault{5\\times10^{0}}$'),
        (10, 500000, '$\\mathdefault{5\\times10^{5}}$'),
    ]

    @mpl.style.context('default')
    @pytest.mark.parametrize('base, value, expected', test_data)
    def test_basic(self, base, value, expected):
        formatter = mticker.LogFormatterSciNotation(base=base)
        with mpl.rc_context({'text.usetex': False}):
            assert formatter(value) == expected


class TestLogFormatter:
    pprint_data = [
        (3.141592654e-05, 0.001, '3.142e-5'),
        (0.0003141592654, 0.001, '3.142e-4'),
        (0.003141592654, 0.001, '3.142e-3'),
        (0.03141592654, 0.001, '3.142e-2'),
        (0.3141592654, 0.001, '3.142e-1'),
        (3.141592654, 0.001, '3.142'),
        (31.41592654, 0.001, '3.142e1'),
        (314.1592654, 0.001, '3.142e2'),
        (3141.592654, 0.001, '3.142e3'),
        (31415.92654, 0.001, '3.142e4'),
        (314159.2654, 0.001, '3.142e5'),
        (1e-05, 0.001, '1e-5'),
        (0.0001, 0.001, '1e-4'),
        (0.001, 0.001, '1e-3'),
        (0.01, 0.001, '1e-2'),
        (0.1, 0.001, '1e-1'),
        (1, 0.001, '1'),
        (10, 0.001, '10'),
        (100, 0.001, '100'),
        (1000, 0.001, '1000'),
        (10000, 0.001, '1e4'),
        (100000, 0.001, '1e5'),
        (3.141592654e-05, 0.015, '0'),
        (0.0003141592654, 0.015, '0'),
        (0.003141592654, 0.015, '0.003'),
        (0.03141592654, 0.015, '0.031'),
        (0.3141592654, 0.015, '0.314'),
        (3.141592654, 0.015, '3.142'),
        (31.41592654, 0.015, '31.416'),
        (314.1592654, 0.015, '314.159'),
        (3141.592654, 0.015, '3141.593'),
        (31415.92654, 0.015, '31415.927'),
        (314159.2654, 0.015, '314159.265'),
        (1e-05, 0.015, '0'),
        (0.0001, 0.015, '0'),
        (0.001, 0.015, '0.001'),
        (0.01, 0.015, '0.01'),
        (0.1, 0.015, '0.1'),
        (1, 0.015, '1'),
        (10, 0.015, '10'),
        (100, 0.015, '100'),
        (1000, 0.015, '1000'),
        (10000, 0.015, '10000'),
        (100000, 0.015, '100000'),
        (3.141592654e-05, 0.5, '0'),
        (0.0003141592654, 0.5, '0'),
        (0.003141592654, 0.5, '0.003'),
        (0.03141592654, 0.5, '0.031'),
        (0.3141592654, 0.5, '0.314'),
        (3.141592654, 0.5, '3.142'),
        (31.41592654, 0.5, '31.416'),
        (314.1592654, 0.5, '314.159'),
        (3141.592654, 0.5, '3141.593'),
        (31415.92654, 0.5, '31415.927'),
        (314159.2654, 0.5, '314159.265'),
        (1e-05, 0.5, '0'),
        (0.0001, 0.5, '0'),
        (0.001, 0.5, '0.001'),
        (0.01, 0.5, '0.01'),
        (0.1, 0.5, '0.1'),
        (1, 0.5, '1'),
        (10, 0.5, '10'),
        (100, 0.5, '100'),
        (1000, 0.5, '1000'),
        (10000, 0.5, '10000'),
        (100000, 0.5, '100000'),
        (3.141592654e-05, 5, '0'),
        (0.0003141592654, 5, '0'),
        (0.003141592654, 5, '0'),
        (0.03141592654, 5, '0.03'),
        (0.3141592654, 5, '0.31'),
        (3.141592654, 5, '3.14'),
        (31.41592654, 5, '31.42'),
        (314.1592654, 5, '314.16'),
        (3141.592654, 5, '3141.59'),
        (31415.92654, 5, '31415.93'),
        (314159.2654, 5, '314159.27'),
        (1e-05, 5, '0'),
        (0.0001, 5, '0'),
        (0.001, 5, '0'),
        (0.01, 5, '0.01'),
        (0.1, 5, '0.1'),
        (1, 5, '1'),
        (10, 5, '10'),
        (100, 5, '100'),
        (1000, 5, '1000'),
        (10000, 5, '10000'),
        (100000, 5, '100000'),
        (3.141592654e-05, 100, '0'),
        (0.0003141592654, 100, '0'),
        (0.003141592654, 100, '0'),
        (0.03141592654, 100, '0'),
        (0.3141592654, 100, '0.3'),
        (3.141592654, 100, '3.1'),
        (31.41592654, 100, '31.4'),
        (314.1592654, 100, '314.2'),
        (3141.592654, 100, '3141.6'),
        (31415.92654, 100, '31415.9'),
        (314159.2654, 100, '314159.3'),
        (1e-05, 100, '0'),
        (0.0001, 100, '0'),
        (0.001, 100, '0'),
        (0.01, 100, '0'),
        (0.1, 100, '0.1'),
        (1, 100, '1'),
        (10, 100, '10'),
        (100, 100, '100'),
        (1000, 100, '1000'),
        (10000, 100, '10000'),
        (100000, 100, '100000'),
        (3.141592654e-05, 1000000.0, '3.1e-5'),
        (0.0003141592654, 1000000.0, '3.1e-4'),
        (0.003141592654, 1000000.0, '3.1e-3'),
        (0.03141592654, 1000000.0, '3.1e-2'),
        (0.3141592654, 1000000.0, '3.1e-1'),
        (3.141592654, 1000000.0, '3.1'),
        (31.41592654, 1000000.0, '3.1e1'),
        (314.1592654, 1000000.0, '3.1e2'),
        (3141.592654, 1000000.0, '3.1e3'),
        (31415.92654, 1000000.0, '3.1e4'),
        (314159.2654, 1000000.0, '3.1e5'),
        (1e-05, 1000000.0, '1e-5'),
        (0.0001, 1000000.0, '1e-4'),
        (0.001, 1000000.0, '1e-3'),
        (0.01, 1000000.0, '1e-2'),
        (0.1, 1000000.0, '1e-1'),
        (1, 1000000.0, '1'),
        (10, 1000000.0, '10'),
        (100, 1000000.0, '100'),
        (1000, 1000000.0, '1000'),
        (10000, 1000000.0, '1e4'),
        (100000, 1000000.0, '1e5'),
    ]

    @pytest.mark.parametrize('value, domain, expected', pprint_data)
    def test_pprint(self, value, domain, expected):
        fmt = mticker.LogFormatter()
        label = fmt._pprint_val(value, domain)
        assert label == expected

    @pytest.mark.parametrize('value, long, short', [
        (0.0, "0", "0"),
        (0, "0", "0"),
        (-1.0, "-10^0", "-1"),
        (2e-10, "2x10^-10", "2e-10"),
        (1e10, "10^10", "1e+10"),
    ])
    def test_format_data(self, value, long, short):
        fig, ax = plt.subplots()
        ax.set_xscale('log')
        fmt = ax.xaxis.get_major_formatter()
        assert fmt.format_data(value) == long
        assert fmt.format_data_short(value) == short

    def _sub_labels(self, axis, subs=()):
        """Test whether locator marks subs to be labeled."""
        fmt = axis.get_minor_formatter()
        minor_tlocs = axis.get_minorticklocs()
        fmt.set_locs(minor_tlocs)
        coefs = minor_tlocs / 10**(np.floor(np.log10(minor_tlocs)))
        label_expected = [round(c) in subs for c in coefs]
        label_test = [fmt(x) != '' for x in minor_tlocs]
        assert label_test == label_expected

    @mpl.style.context('default')
    def test_sublabel(self):
        # test label locator
        fig, ax = plt.subplots()
        ax.set_xscale('log')
        ax.xaxis.set_major_locator(mticker.LogLocator(base=10, subs=[]))
        ax.xaxis.set_minor_locator(mticker.LogLocator(base=10,
                                                      subs=np.arange(2, 10)))
        ax.xaxis.set_major_formatter(mticker.LogFormatter(labelOnlyBase=True))
        ax.xaxis.set_minor_formatter(mticker.LogFormatter(labelOnlyBase=False))
        # axis range above 3 decades, only bases are labeled
        ax.set_xlim(1, 1e4)
        fmt = ax.xaxis.get_major_formatter()
        fmt.set_locs(ax.xaxis.get_majorticklocs())
        show_major_labels = [fmt(x) != ''
                             for x in ax.xaxis.get_majorticklocs()]
        assert np.all(show_major_labels)
        self._sub_labels(ax.xaxis, subs=[])

        # For the next two, if the numdec threshold in LogFormatter.set_locs
        # were 3, then the label sub would be 3 for 2-3 decades and (2, 5)
        # for 1-2 decades.  With a threshold of 1, subs are not labeled.
        # axis range at 2 to 3 decades
        ax.set_xlim(1, 800)
        self._sub_labels(ax.xaxis, subs=[])

        # axis range at 1 to 2 decades
        ax.set_xlim(1, 80)
        self._sub_labels(ax.xaxis, subs=[])

        # axis range at 0.4 to 1 decades, label subs 2, 3, 4, 6
        ax.set_xlim(1, 8)
        self._sub_labels(ax.xaxis, subs=[2, 3, 4, 6])

        # axis range at 0 to 0.4 decades, label all
        ax.set_xlim(0.5, 0.9)
        self._sub_labels(ax.xaxis, subs=np.arange(2, 10, dtype=int))

    @pytest.mark.parametrize('val', [1, 10, 100, 1000])
    def test_LogFormatter_call(self, val):
        # test _num_to_string method used in __call__
        temp_lf = mticker.LogFormatter()
        temp_lf.create_dummy_axis()
        temp_lf.axis.set_view_interval(1, 10)
        assert temp_lf(val) == str(val)

    @pytest.mark.parametrize('val', [1e-323, 2e-323, 10e-323, 11e-323])
    def test_LogFormatter_call_tiny(self, val):
        # test coeff computation in __call__
        temp_lf = mticker.LogFormatter()
        temp_lf.create_dummy_axis()
        temp_lf.axis.set_view_interval(1, 10)
        temp_lf(val)


class TestLogitFormatter:
    @staticmethod
    def logit_deformatter(string):
        r"""
        Parser to convert string as r'$\mathdefault{1.41\cdot10^{-4}}$' in
        float 1.41e-4, as '0.5' or as r'$\mathdefault{\frac{1}{2}}$' in float
        0.5,
        """
        match = re.match(
            r"[^\d]*"
            r"(?P<comp>1-)?"
            r"(?P<mant>\d*\.?\d*)?"
            r"(?:\\cdot)?"
            r"(?:10\^\{(?P<expo>-?\d*)})?"
            r"[^\d]*$",
            string,
        )
        if match:
            comp = match["comp"] is not None
            mantissa = float(match["mant"]) if match["mant"] else 1
            expo = int(match["expo"]) if match["expo"] is not None else 0
            value = mantissa * 10 ** expo
            if match["mant"] or match["expo"] is not None:
                if comp:
                    return 1 - value
                return value
        match = re.match(
            r"[^\d]*\\frac\{(?P<num>\d+)\}\{(?P<deno>\d+)\}[^\d]*$", string
        )
        if match:
            num, deno = float(match["num"]), float(match["deno"])
            return num / deno
        raise ValueError("Not formatted by LogitFormatter")

    @pytest.mark.parametrize(
        "fx, x",
        [
            (r"STUFF0.41OTHERSTUFF", 0.41),
            (r"STUFF1.41\cdot10^{-2}OTHERSTUFF", 1.41e-2),
            (r"STUFF1-0.41OTHERSTUFF", 1 - 0.41),
            (r"STUFF1-1.41\cdot10^{-2}OTHERSTUFF", 1 - 1.41e-2),
            (r"STUFF", None),
            (r"STUFF12.4e-3OTHERSTUFF", None),
        ],
    )
    def test_logit_deformater(self, fx, x):
        if x is None:
            with pytest.raises(ValueError):
                TestLogitFormatter.logit_deformatter(fx)
        else:
            y = TestLogitFormatter.logit_deformatter(fx)
            assert _LogitHelper.isclose(x, y)

    decade_test = sorted(
        [10 ** (-i) for i in range(1, 10)]
        + [1 - 10 ** (-i) for i in range(1, 10)]
        + [1 / 2]
    )

    @pytest.mark.parametrize("x", decade_test)
    def test_basic(self, x):
        """
        Test the formatted value correspond to the value for ideal ticks in
        logit space.
        """
        formatter = mticker.LogitFormatter(use_overline=False)
        formatter.set_locs(self.decade_test)
        s = formatter(x)
        x2 = TestLogitFormatter.logit_deformatter(s)
        assert _LogitHelper.isclose(x, x2)

    @pytest.mark.parametrize("x", (-1, -0.5, -0.1, 1.1, 1.5, 2))
    def test_invalid(self, x):
        """
        Test that invalid value are formatted with empty string without
        raising exception.
        """
        formatter = mticker.LogitFormatter(use_overline=False)
        formatter.set_locs(self.decade_test)
        s = formatter(x)
        assert s == ""

    @pytest.mark.parametrize("x", 1 / (1 + np.exp(-np.linspace(-7, 7, 10))))
    def test_variablelength(self, x):
        """
        The format length should change depending on the neighbor labels.
        """
        formatter = mticker.LogitFormatter(use_overline=False)
        for N in (10, 20, 50, 100, 200, 1000, 2000, 5000, 10000):
            if x + 1 / N < 1:
                formatter.set_locs([x - 1 / N, x, x + 1 / N])
                sx = formatter(x)
                sx1 = formatter(x + 1 / N)
                d = (
                    TestLogitFormatter.logit_deformatter(sx1)
                    - TestLogitFormatter.logit_deformatter(sx)
                )
                assert 0 < d < 2 / N

    lims_minor_major = [
        (True, (5e-8, 1 - 5e-8), ((25, False), (75, False))),
        (True, (5e-5, 1 - 5e-5), ((25, False), (75, True))),
        (True, (5e-2, 1 - 5e-2), ((25, True), (75, True))),
        (False, (0.75, 0.76, 0.77), ((7, True), (25, True), (75, True))),
    ]

    @pytest.mark.parametrize("method, lims, cases", lims_minor_major)
    def test_minor_vs_major(self, method, lims, cases):
        """
        Test minor/major displays.
        """

        if method:
            min_loc = mticker.LogitLocator(minor=True)
            ticks = min_loc.tick_values(*lims)
        else:
            ticks = np.array(lims)
        min_form = mticker.LogitFormatter(minor=True)
        for threshold, has_minor in cases:
            min_form.set_minor_threshold(threshold)
            formatted = min_form.format_ticks(ticks)
            labelled = [f for f in formatted if len(f) > 0]
            if has_minor:
                assert len(labelled) > 0, (threshold, has_minor)
            else:
                assert len(labelled) == 0, (threshold, has_minor)

    def test_minor_number(self):
        """
        Test the parameter minor_number
        """
        min_loc = mticker.LogitLocator(minor=True)
        min_form = mticker.LogitFormatter(minor=True)
        ticks = min_loc.tick_values(5e-2, 1 - 5e-2)
        for minor_number in (2, 4, 8, 16):
            min_form.set_minor_number(minor_number)
            formatted = min_form.format_ticks(ticks)
            labelled = [f for f in formatted if len(f) > 0]
            assert len(labelled) == minor_number

    def test_use_overline(self):
        """
        Test the parameter use_overline
        """
        x = 1 - 1e-2
        fx1 = r"$\mathdefault{1-10^{-2}}$"
        fx2 = r"$\mathdefault{\overline{10^{-2}}}$"
        form = mticker.LogitFormatter(use_overline=False)
        assert form(x) == fx1
        form.use_overline(True)
        assert form(x) == fx2
        form.use_overline(False)
        assert form(x) == fx1

    def test_one_half(self):
        """
        Test the parameter one_half
        """
        form = mticker.LogitFormatter()
        assert r"\frac{1}{2}" in form(1/2)
        form.set_one_half("1/2")
        assert "1/2" in form(1/2)
        form.set_one_half("one half")
        assert "one half" in form(1/2)

    @pytest.mark.parametrize("N", (100, 253, 754))
    def test_format_data_short(self, N):
        locs = np.linspace(0, 1, N)[1:-1]
        form = mticker.LogitFormatter()
        for x in locs:
            fx = form.format_data_short(x)
            if fx.startswith("1-"):
                x2 = 1 - float(fx[2:])
            else:
                x2 = float(fx)
            assert abs(x - x2) < 1 / N


class TestFormatStrFormatter:
    def test_basic(self):
        # test % style formatter
        tmp_form = mticker.FormatStrFormatter('%05d')
        assert '00002' == tmp_form(2)


class TestStrMethodFormatter:
    test_data = [
        ('{x:05d}', (2,), False, '00002'),
        ('{x:05d}', (2,), True, '00002'),
        ('{x:05d}', (-2,), False, '-0002'),
        ('{x:05d}', (-2,), True, '\N{MINUS SIGN}0002'),
        ('{x:03d}-{pos:02d}', (2, 1), False, '002-01'),
        ('{x:03d}-{pos:02d}', (2, 1), True, '002-01'),
        ('{x:03d}-{pos:02d}', (-2, 1), False, '-02-01'),
        ('{x:03d}-{pos:02d}', (-2, 1), True, '\N{MINUS SIGN}02-01'),
    ]

    @pytest.mark.parametrize('format, input, unicode_minus, expected', test_data)
    def test_basic(self, format, input, unicode_minus, expected):
        with mpl.rc_context({"axes.unicode_minus": unicode_minus}):
            fmt = mticker.StrMethodFormatter(format)
            assert fmt(*input) == expected


class TestEngFormatter:
    # (unicode_minus, input, expected) where ''expected'' corresponds to the
    # outputs respectively returned when (places=None, places=0, places=2)
    # unicode_minus is a boolean value for the rcParam['axes.unicode_minus']
    raw_format_data = [
        (False, -1234.56789, ('-1.23457 k', '-1 k', '-1.23 k')),
        (True, -1234.56789, ('\N{MINUS SIGN}1.23457 k', '\N{MINUS SIGN}1 k',
                             '\N{MINUS SIGN}1.23 k')),
        (False, -1.23456789, ('-1.23457', '-1', '-1.23')),
        (True, -1.23456789, ('\N{MINUS SIGN}1.23457', '\N{MINUS SIGN}1',
                             '\N{MINUS SIGN}1.23')),
        (False, -0.123456789, ('-123.457 m', '-123 m', '-123.46 m')),
        (True, -0.123456789, ('\N{MINUS SIGN}123.457 m', '\N{MINUS SIGN}123 m',
                              '\N{MINUS SIGN}123.46 m')),
        (False, -0.00123456789, ('-1.23457 m', '-1 m', '-1.23 m')),
        (True, -0.00123456789, ('\N{MINUS SIGN}1.23457 m', '\N{MINUS SIGN}1 m',
                                '\N{MINUS SIGN}1.23 m')),
        (True, -0.0, ('0', '0', '0.00')),
        (True, -0, ('0', '0', '0.00')),
        (True, 0, ('0', '0', '0.00')),
        (True, 1.23456789e-6, ('1.23457 µ', '1 µ', '1.23 µ')),
        (True, 0.123456789, ('123.457 m', '123 m', '123.46 m')),
        (True, 0.1, ('100 m', '100 m', '100.00 m')),
        (True, 1, ('1', '1', '1.00')),
        (True, 1.23456789, ('1.23457', '1', '1.23')),
        # places=0: corner-case rounding
        (True, 999.9, ('999.9', '1 k', '999.90')),
        # corner-case rounding for all
        (True, 999.9999, ('1 k', '1 k', '1.00 k')),
        # negative corner-case
        (False, -999.9999, ('-1 k', '-1 k', '-1.00 k')),
        (True, -999.9999, ('\N{MINUS SIGN}1 k', '\N{MINUS SIGN}1 k',
                           '\N{MINUS SIGN}1.00 k')),
        (True, 1000, ('1 k', '1 k', '1.00 k')),
        (True, 1001, ('1.001 k', '1 k', '1.00 k')),
        (True, 100001, ('100.001 k', '100 k', '100.00 k')),
        (True, 987654.321, ('987.654 k', '988 k', '987.65 k')),
        # OoR value (> 1000 Q)
        (True, 1.23e33, ('1230 Q', '1230 Q', '1230.00 Q'))
    ]

    @pytest.mark.parametrize('unicode_minus, input, expected', raw_format_data)
    def test_params(self, unicode_minus, input, expected):
        """
        Test the formatting of EngFormatter for various values of the 'places'
        argument, in several cases:

        0. without a unit symbol but with a (default) space separator;
        1. with both a unit symbol and a (default) space separator;
        2. with both a unit symbol and some non default separators;
        3. without a unit symbol but with some non default separators.

        Note that cases 2. and 3. are looped over several separator strings.
        """

        plt.rcParams['axes.unicode_minus'] = unicode_minus
        UNIT = 's'  # seconds
        DIGITS = '0123456789'  # %timeit showed 10-20% faster search than set

        # Case 0: unit='' (default) and sep=' ' (default).
        # 'expected' already corresponds to this reference case.
        exp_outputs = expected
        formatters = (
            mticker.EngFormatter(),  # places=None (default)
            mticker.EngFormatter(places=0),
            mticker.EngFormatter(places=2)
        )
        for _formatter, _exp_output in zip(formatters, exp_outputs):
            assert _formatter(input) == _exp_output

        # Case 1: unit=UNIT and sep=' ' (default).
        # Append a unit symbol to the reference case.
        # Beware of the values in [1, 1000), where there is no prefix!
        exp_outputs = (_s + " " + UNIT if _s[-1] in DIGITS  # case w/o prefix
                       else _s + UNIT for _s in expected)
        formatters = (
            mticker.EngFormatter(unit=UNIT),  # places=None (default)
            mticker.EngFormatter(unit=UNIT, places=0),
            mticker.EngFormatter(unit=UNIT, places=2)
        )
        for _formatter, _exp_output in zip(formatters, exp_outputs):
            assert _formatter(input) == _exp_output

        # Test several non default separators: no separator, a narrow
        # no-break space (Unicode character) and an extravagant string.
        for _sep in ("", "\N{NARROW NO-BREAK SPACE}", "@_@"):
            # Case 2: unit=UNIT and sep=_sep.
            # Replace the default space separator from the reference case
            # with the tested one `_sep` and append a unit symbol to it.
            exp_outputs = (_s + _sep + UNIT if _s[-1] in DIGITS  # no prefix
                           else _s.replace(" ", _sep) + UNIT
                           for _s in expected)
            formatters = (
                mticker.EngFormatter(unit=UNIT, sep=_sep),  # places=None
                mticker.EngFormatter(unit=UNIT, places=0, sep=_sep),
                mticker.EngFormatter(unit=UNIT, places=2, sep=_sep)
            )
            for _formatter, _exp_output in zip(formatters, exp_outputs):
                assert _formatter(input) == _exp_output

            # Case 3: unit='' (default) and sep=_sep.
            # Replace the default space separator from the reference case
            # with the tested one `_sep`. Reference case is already unitless.
            exp_outputs = (_s.replace(" ", _sep) for _s in expected)
            formatters = (
                mticker.EngFormatter(sep=_sep),  # places=None (default)
                mticker.EngFormatter(places=0, sep=_sep),
                mticker.EngFormatter(places=2, sep=_sep)
            )
            for _formatter, _exp_output in zip(formatters, exp_outputs):
                assert _formatter(input) == _exp_output


def test_engformatter_usetex_useMathText():
    fig, ax = plt.subplots()
    ax.plot([0, 500, 1000], [0, 500, 1000])
    ax.set_xticks([0, 500, 1000])
    for formatter in (mticker.EngFormatter(usetex=True),
                      mticker.EngFormatter(useMathText=True)):
        ax.xaxis.set_major_formatter(formatter)
        fig.canvas.draw()
        x_tick_label_text = [labl.get_text() for labl in ax.get_xticklabels()]
        # Checking if the dollar `$` signs have been inserted around numbers
        # in tick labels.
        assert x_tick_label_text == ['$0$', '$500$', '$1$ k']


@pytest.mark.parametrize(
    'data_offset, noise, oom_center_desired, oom_noise_desired', [
        (271_490_000_000.0,    10,         9,  0),
        (27_149_000_000_000.0, 10_000_000, 12, 6),
        (27.149,               0.01,       0, -3),
        (2_714.9,              0.01,       3, -3),
        (271_490.0,            0.001,      3, -3),
        (271.49,               0.001,      0, -3),
        # The following sets of parameters demonstrates that when
        # oom(data_offset)-1 and oom(noise)-2 equal a standard 3*N oom, we get
        # that oom_noise_desired < oom(noise)
        (27_149_000_000.0,     100,        9, +3),
        (27.149,               1e-07,      0, -6),
        (271.49,               0.0001,     0, -3),
        (27.149,               0.0001,     0, -3),
        # Tests where oom(data_offset) <= oom(noise), those are probably
        # covered by the part where formatter.offset != 0
        (27_149.0,             10_000,     0, 3),
        (27.149,               10_000,     0, 3),
        (27.149,               1_000,      0, 3),
        (27.149,               100,        0, 0),
        (27.149,               10,         0, 0),
    ]
)
def test_engformatter_offset_oom(
    data_offset,
    noise,
    oom_center_desired,
    oom_noise_desired
):
    UNIT = "eV"
    fig, ax = plt.subplots()
    ydata = data_offset + np.arange(-5, 7, dtype=float)*noise
    ax.plot(ydata)
    formatter = mticker.EngFormatter(useOffset=True, unit=UNIT)
    # So that offset strings will always have the same size
    formatter.ENG_PREFIXES[0] = "_"
    ax.yaxis.set_major_formatter(formatter)
    fig.canvas.draw()
    offset_got = formatter.get_offset()
    ticks_got = [labl.get_text() for labl in ax.get_yticklabels()]
    # Predicting whether offset should be 0 or not is essentially testing
    # ScalarFormatter._compute_offset . This function is pretty complex and it
    # would be nice to test it, but this is out of scope for this test which
    # only makes sure that offset text and the ticks gets the correct unit
    # prefixes and the ticks.
    if formatter.offset:
        prefix_noise_got = offset_got[2]
        prefix_noise_desired = formatter.ENG_PREFIXES[oom_noise_desired]
        prefix_center_got = offset_got[-1-len(UNIT)]
        prefix_center_desired = formatter.ENG_PREFIXES[oom_center_desired]
        assert prefix_noise_desired == prefix_noise_got
        assert prefix_center_desired == prefix_center_got
        # Make sure the ticks didn't get the UNIT
        for tick in ticks_got:
            assert UNIT not in tick
    else:
        assert oom_center_desired == 0
        assert offset_got == ""
        # Make sure the ticks contain now the prefixes
        for tick in ticks_got:
            # 0 is zero on all orders of magnitudes, no matter what is
            # oom_noise_desired
            prefix_idx = 0 if tick[0] == "0" else oom_noise_desired
            assert tick.endswith(formatter.ENG_PREFIXES[prefix_idx] + UNIT)


class TestPercentFormatter:
    percent_data = [
        # Check explicitly set decimals over different intervals and values
        (100, 0, '%', 120, 100, '120%'),
        (100, 0, '%', 100, 90, '100%'),
        (100, 0, '%', 90, 50, '90%'),
        (100, 0, '%', -1.7, 40, '-2%'),
        (100, 1, '%', 90.0, 100, '90.0%'),
        (100, 1, '%', 80.1, 90, '80.1%'),
        (100, 1, '%', 70.23, 50, '70.2%'),
        # 60.554 instead of 60.55: see https://bugs.python.org/issue5118
        (100, 1, '%', -60.554, 40, '-60.6%'),
        # Check auto decimals over different intervals and values
        (100, None, '%', 95, 1, '95.00%'),
        (1.0, None, '%', 3, 6, '300%'),
        (17.0, None, '%', 1, 8.5, '6%'),
        (17.0, None, '%', 1, 8.4, '5.9%'),
        (5, None, '%', -100, 0.000001, '-2000.00000%'),
        # Check percent symbol
        (1.0, 2, None, 1.2, 100, '120.00'),
        (75, 3, '', 50, 100, '66.667'),
        (42, None, '^^Foobar$$', 21, 12, '50.0^^Foobar$$'),
    ]

    percent_ids = [
        # Check explicitly set decimals over different intervals and values
        'decimals=0, x>100%',
        'decimals=0, x=100%',
        'decimals=0, x<100%',
        'decimals=0, x<0%',
        'decimals=1, x>100%',
        'decimals=1, x=100%',
        'decimals=1, x<100%',
        'decimals=1, x<0%',
        # Check auto decimals over different intervals and values
        'autodecimal, x<100%, display_range=1',
        'autodecimal, x>100%, display_range=6 (custom xmax test)',
        'autodecimal, x<100%, display_range=8.5 (autodecimal test 1)',
        'autodecimal, x<100%, display_range=8.4 (autodecimal test 2)',
        'autodecimal, x<-100%, display_range=1e-6 (tiny display range)',
        # Check percent symbol
        'None as percent symbol',
        'Empty percent symbol',
        'Custom percent symbol',
    ]

    latex_data = [
        (False, False, r'50\{t}%'),
        (False, True, r'50\\\{t\}\%'),
        (True, False, r'50\{t}%'),
        (True, True, r'50\{t}%'),
    ]

    @pytest.mark.parametrize(
            'xmax, decimals, symbol, x, display_range, expected',
            percent_data, ids=percent_ids)
    def test_basic(self, xmax, decimals, symbol,
                   x, display_range, expected):
        formatter = mticker.PercentFormatter(xmax, decimals, symbol)
        with mpl.rc_context(rc={'text.usetex': False}):
            assert formatter.format_pct(x, display_range) == expected

    @pytest.mark.parametrize('is_latex, usetex, expected', latex_data)
    def test_latex(self, is_latex, usetex, expected):
        fmt = mticker.PercentFormatter(symbol='\\{t}%', is_latex=is_latex)
        with mpl.rc_context(rc={'text.usetex': usetex}):
            assert fmt.format_pct(50, 100) == expected


def _impl_locale_comma():
    try:
        locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')
    except locale.Error:
        print('SKIP: Locale de_DE.UTF-8 is not supported on this machine')
        return
    ticks = mticker.ScalarFormatter(useMathText=True, useLocale=True)
    fmt = '$\\mathdefault{%1.1f}$'
    x = ticks._format_maybe_minus_and_locale(fmt, 0.5)
    assert x == '$\\mathdefault{0{,}5}$'
    # Do not change , in the format string
    fmt = ',$\\mathdefault{,%1.1f},$'
    x = ticks._format_maybe_minus_and_locale(fmt, 0.5)
    assert x == ',$\\mathdefault{,0{,}5},$'
    # Make sure no brackets are added if not using math text
    ticks = mticker.ScalarFormatter(useMathText=False, useLocale=True)
    fmt = '%1.1f'
    x = ticks._format_maybe_minus_and_locale(fmt, 0.5)
    assert x == '0,5'


def test_locale_comma():
    # On some systems/pytest versions, `pytest.skip` in an exception handler
    # does not skip, but is treated as an exception, so directly running this
    # test can incorrectly fail instead of skip.
    # Instead, run this test in a subprocess, which avoids the problem, and the
    # need to fix the locale after.
    proc = mpl.testing.subprocess_run_helper(_impl_locale_comma, timeout=60,
                                             extra_env={'MPLBACKEND': 'Agg'})
    skip_msg = next((line[len('SKIP:'):].strip()
                     for line in proc.stdout.splitlines()
                     if line.startswith('SKIP:')),
                    '')
    if skip_msg:
        pytest.skip(skip_msg)


def test_majformatter_type():
    fig, ax = plt.subplots()
    with pytest.raises(TypeError):
        ax.xaxis.set_major_formatter(mticker.LogLocator())


def test_minformatter_type():
    fig, ax = plt.subplots()
    with pytest.raises(TypeError):
        ax.xaxis.set_minor_formatter(mticker.LogLocator())


def test_majlocator_type():
    fig, ax = plt.subplots()
    with pytest.raises(TypeError):
        ax.xaxis.set_major_locator(mticker.LogFormatter())


def test_minlocator_type():
    fig, ax = plt.subplots()
    with pytest.raises(TypeError):
        ax.xaxis.set_minor_locator(mticker.LogFormatter())


def test_minorticks_rc():
    fig = plt.figure()

    def minorticksubplot(xminor, yminor, i):
        rc = {'xtick.minor.visible': xminor,
              'ytick.minor.visible': yminor}
        with plt.rc_context(rc=rc):
            ax = fig.add_subplot(2, 2, i)

        assert (len(ax.xaxis.get_minor_ticks()) > 0) == xminor
        assert (len(ax.yaxis.get_minor_ticks()) > 0) == yminor

    minorticksubplot(False, False, 1)
    minorticksubplot(True, False, 2)
    minorticksubplot(False, True, 3)
    minorticksubplot(True, True, 4)


def test_minorticks_toggle():
    """
    Test toggling minor ticks

    Test `.Axis.minorticks_on()` and `.Axis.minorticks_off()`. Testing is
    limited to a subset of built-in scales - `'linear'`, `'log'`, `'asinh'`
    and `'logit'`. `symlog` scale does not seem to have a working minor
    locator and is omitted. In future, this test should cover all scales in
    `matplotlib.scale.get_scale_names()`.
    """
    fig = plt.figure()
    def minortickstoggle(xminor, yminor, scale, i):
        ax = fig.add_subplot(2, 2, i)
        ax.set_xscale(scale)
        ax.set_yscale(scale)
        if not xminor and not yminor:
            ax.minorticks_off()
        if xminor and not yminor:
            ax.xaxis.minorticks_on()
            ax.yaxis.minorticks_off()
        if not xminor and yminor:
            ax.xaxis.minorticks_off()
            ax.yaxis.minorticks_on()
        if xminor and yminor:
            ax.minorticks_on()

        assert (len(ax.xaxis.get_minor_ticks()) > 0) == xminor
        assert (len(ax.yaxis.get_minor_ticks()) > 0) == yminor

    scales = ['linear', 'log', 'asinh', 'logit']
    for scale in scales:
        minortickstoggle(False, False, scale, 1)
        minortickstoggle(True, False, scale, 2)
        minortickstoggle(False, True, scale, 3)
        minortickstoggle(True, True, scale, 4)
        fig.clear()

    plt.close(fig)


@pytest.mark.parametrize('remove_overlapping_locs, expected_num',
                         ((True, 6),
                          (None, 6),  # this tests the default
                          (False, 9)))
def test_remove_overlap(remove_overlapping_locs, expected_num):
    t = np.arange("2018-11-03", "2018-11-06", dtype="datetime64")
    x = np.ones(len(t))

    fig, ax = plt.subplots()
    ax.plot(t, x)

    ax.xaxis.set_major_locator(mpl.dates.DayLocator())
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('\n%a'))

    ax.xaxis.set_minor_locator(mpl.dates.HourLocator((0, 6, 12, 18)))
    ax.xaxis.set_minor_formatter(mpl.dates.DateFormatter('%H:%M'))
    # force there to be extra ticks
    ax.xaxis.get_minor_ticks(15)
    if remove_overlapping_locs is not None:
        ax.xaxis.remove_overlapping_locs = remove_overlapping_locs

    # check that getter/setter exists
    current = ax.xaxis.remove_overlapping_locs
    assert (current == ax.xaxis.get_remove_overlapping_locs())
    plt.setp(ax.xaxis, remove_overlapping_locs=current)
    new = ax.xaxis.remove_overlapping_locs
    assert (new == ax.xaxis.remove_overlapping_locs)

    # check that the accessors filter correctly
    # this is the method that does the actual filtering
    assert len(ax.xaxis.get_minorticklocs()) == expected_num
    # these three are derivative
    assert len(ax.xaxis.get_minor_ticks()) == expected_num
    assert len(ax.xaxis.get_minorticklabels()) == expected_num
    assert len(ax.xaxis.get_minorticklines()) == expected_num*2


@pytest.mark.parametrize('sub', [
    ['hi', 'aardvark'],
    np.zeros((2, 2))])
def test_bad_locator_subs(sub):
    ll = mticker.LogLocator()
    with pytest.raises(ValueError):
        ll.set_params(subs=sub)


@pytest.mark.parametrize('numticks', [1, 2, 3, 9])
@mpl.style.context('default')
def test_small_range_loglocator(numticks):
    ll = mticker.LogLocator()
    ll.set_params(numticks=numticks)
    for top in [5, 7, 9, 11, 15, 50, 100, 1000]:
        ticks = ll.tick_values(.5, top)
        assert (np.diff(np.log10(ll.tick_values(6, 150))) == 1).all()


def test_NullFormatter():
    formatter = mticker.NullFormatter()
    assert formatter(1.0) == ''
    assert formatter.format_data(1.0) == ''
    assert formatter.format_data_short(1.0) == ''


@pytest.mark.parametrize('formatter', (
    mticker.FuncFormatter(lambda a: f'val: {a}'),
    mticker.FixedFormatter(('foo', 'bar'))))
def test_set_offset_string(formatter):
    assert formatter.get_offset() == ''
    formatter.set_offset_string('mpl')
    assert formatter.get_offset() == 'mpl'


def test_minorticks_on_multi_fig():
    """
    Turning on minor gridlines in a multi-Axes Figure
    that contains more than one boxplot and shares the x-axis
    should not raise an exception.
    """
    fig, ax = plt.subplots()

    ax.boxplot(np.arange(10), positions=[0])
    ax.boxplot(np.arange(10), positions=[0])
    ax.boxplot(np.arange(10), positions=[1])

    ax.grid(which="major")
    ax.grid(which="minor")
    ax.minorticks_on()
    fig.draw_without_rendering()

    assert ax.get_xgridlines()
    assert isinstance(ax.xaxis.get_minor_locator(), mpl.ticker.AutoMinorLocator)
