""" Test cases for DataFrame.plot """

import pytest

from pandas import DataFrame
from pandas.tests.plotting.common import _check_visible

pytest.importorskip("matplotlib")


class TestDataFramePlotsGroupby:
    def _assert_ytickslabels_visibility(self, axes, expected):
        for ax, exp in zip(axes, expected):
            _check_visible(ax.get_yticklabels(), visible=exp)

    def _assert_xtickslabels_visibility(self, axes, expected):
        for ax, exp in zip(axes, expected):
            _check_visible(ax.get_xticklabels(), visible=exp)

    @pytest.mark.parametrize(
        "kwargs, expected",
        [
            # behavior without keyword
            ({}, [True, False, True, False]),
            # set sharey=True should be identical
            ({"sharey": True}, [True, False, True, False]),
            # sharey=False, all yticklabels should be visible
            ({"sharey": False}, [True, True, True, True]),
        ],
    )
    def test_groupby_boxplot_sharey(self, kwargs, expected):
        # https://github.com/pandas-dev/pandas/issues/20968
        # sharey can now be switched check whether the right
        # pair of axes is turned on or off
        df = DataFrame(
            {
                "a": [-1.43, -0.15, -3.70, -1.43, -0.14],
                "b": [0.56, 0.84, 0.29, 0.56, 0.85],
                "c": [0, 1, 2, 3, 1],
            },
            index=[0, 1, 2, 3, 4],
        )
        axes = df.groupby("c").boxplot(**kwargs)
        self._assert_ytickslabels_visibility(axes, expected)

    @pytest.mark.parametrize(
        "kwargs, expected",
        [
            # behavior without keyword
            ({}, [True, True, True, True]),
            # set sharex=False should be identical
            ({"sharex": False}, [True, True, True, True]),
            # sharex=True, xticklabels should be visible
            # only for bottom plots
            ({"sharex": True}, [False, False, True, True]),
        ],
    )
    def test_groupby_boxplot_sharex(self, kwargs, expected):
        # https://github.com/pandas-dev/pandas/issues/20968
        # sharex can now be switched check whether the right
        # pair of axes is turned on or off

        df = DataFrame(
            {
                "a": [-1.43, -0.15, -3.70, -1.43, -0.14],
                "b": [0.56, 0.84, 0.29, 0.56, 0.85],
                "c": [0, 1, 2, 3, 1],
            },
            index=[0, 1, 2, 3, 4],
        )
        axes = df.groupby("c").boxplot(**kwargs)
        self._assert_xtickslabels_visibility(axes, expected)
