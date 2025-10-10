import operator

import numpy as np
import pytest

from pandas.core.dtypes.common import is_list_like

import pandas as pd
from pandas import (
    Categorical,
    Index,
    Interval,
    IntervalIndex,
    Period,
    Series,
    Timedelta,
    Timestamp,
    date_range,
    period_range,
    timedelta_range,
)
import pandas._testing as tm
from pandas.core.arrays import (
    BooleanArray,
    IntervalArray,
)
from pandas.tests.arithmetic.common import get_upcast_box


@pytest.fixture(
    params=[
        (Index([0, 2, 4, 4]), Index([1, 3, 5, 8])),
        (Index([0.0, 1.0, 2.0, np.nan]), Index([1.0, 2.0, 3.0, np.nan])),
        (
            timedelta_range("0 days", periods=3).insert(3, pd.NaT),
            timedelta_range("1 day", periods=3).insert(3, pd.NaT),
        ),
        (
            date_range("20170101", periods=3).insert(3, pd.NaT),
            date_range("20170102", periods=3).insert(3, pd.NaT),
        ),
        (
            date_range("20170101", periods=3, tz="US/Eastern").insert(3, pd.NaT),
            date_range("20170102", periods=3, tz="US/Eastern").insert(3, pd.NaT),
        ),
    ],
    ids=lambda x: str(x[0].dtype),
)
def left_right_dtypes(request):
    """
    Fixture for building an IntervalArray from various dtypes
    """
    return request.param


@pytest.fixture
def interval_array(left_right_dtypes):
    """
    Fixture to generate an IntervalArray of various dtypes containing NA if possible
    """
    left, right = left_right_dtypes
    return IntervalArray.from_arrays(left, right)


def create_categorical_intervals(left, right, closed="right"):
    return Categorical(IntervalIndex.from_arrays(left, right, closed))


def create_series_intervals(left, right, closed="right"):
    return Series(IntervalArray.from_arrays(left, right, closed))


def create_series_categorical_intervals(left, right, closed="right"):
    return Series(Categorical(IntervalIndex.from_arrays(left, right, closed)))


class TestComparison:
    @pytest.fixture(params=[operator.eq, operator.ne])
    def op(self, request):
        return request.param

    @pytest.fixture(
        params=[
            IntervalArray.from_arrays,
            IntervalIndex.from_arrays,
            create_categorical_intervals,
            create_series_intervals,
            create_series_categorical_intervals,
        ],
        ids=[
            "IntervalArray",
            "IntervalIndex",
            "Categorical[Interval]",
            "Series[Interval]",
            "Series[Categorical[Interval]]",
        ],
    )
    def interval_constructor(self, request):
        """
        Fixture for all pandas native interval constructors.
        To be used as the LHS of IntervalArray comparisons.
        """
        return request.param

    def elementwise_comparison(self, op, interval_array, other):
        """
        Helper that performs elementwise comparisons between `array` and `other`
        """
        other = other if is_list_like(other) else [other] * len(interval_array)
        expected = np.array([op(x, y) for x, y in zip(interval_array, other)])
        if isinstance(other, Series):
            return Series(expected, index=other.index)
        return expected

    def test_compare_scalar_interval(self, op, interval_array):
        # matches first interval
        other = interval_array[0]
        result = op(interval_array, other)
        expected = self.elementwise_comparison(op, interval_array, other)
        tm.assert_numpy_array_equal(result, expected)

        # matches on a single endpoint but not both
        other = Interval(interval_array.left[0], interval_array.right[1])
        result = op(interval_array, other)
        expected = self.elementwise_comparison(op, interval_array, other)
        tm.assert_numpy_array_equal(result, expected)

    def test_compare_scalar_interval_mixed_closed(self, op, closed, other_closed):
        interval_array = IntervalArray.from_arrays(range(2), range(1, 3), closed=closed)
        other = Interval(0, 1, closed=other_closed)

        result = op(interval_array, other)
        expected = self.elementwise_comparison(op, interval_array, other)
        tm.assert_numpy_array_equal(result, expected)

    def test_compare_scalar_na(self, op, interval_array, nulls_fixture, box_with_array):
        box = box_with_array
        obj = tm.box_expected(interval_array, box)
        result = op(obj, nulls_fixture)

        if nulls_fixture is pd.NA:
            # GH#31882
            exp = np.ones(interval_array.shape, dtype=bool)
            expected = BooleanArray(exp, exp)
        else:
            expected = self.elementwise_comparison(op, interval_array, nulls_fixture)

        if not (box is Index and nulls_fixture is pd.NA):
            # don't cast expected from BooleanArray to ndarray[object]
            xbox = get_upcast_box(obj, nulls_fixture, True)
            expected = tm.box_expected(expected, xbox)

        tm.assert_equal(result, expected)

        rev = op(nulls_fixture, obj)
        tm.assert_equal(rev, expected)

    @pytest.mark.parametrize(
        "other",
        [
            0,
            1.0,
            True,
            "foo",
            Timestamp("2017-01-01"),
            Timestamp("2017-01-01", tz="US/Eastern"),
            Timedelta("0 days"),
            Period("2017-01-01", "D"),
        ],
    )
    def test_compare_scalar_other(self, op, interval_array, other):
        result = op(interval_array, other)
        expected = self.elementwise_comparison(op, interval_array, other)
        tm.assert_numpy_array_equal(result, expected)

    def test_compare_list_like_interval(self, op, interval_array, interval_constructor):
        # same endpoints
        other = interval_constructor(interval_array.left, interval_array.right)
        result = op(interval_array, other)
        expected = self.elementwise_comparison(op, interval_array, other)
        tm.assert_equal(result, expected)

        # different endpoints
        other = interval_constructor(
            interval_array.left[::-1], interval_array.right[::-1]
        )
        result = op(interval_array, other)
        expected = self.elementwise_comparison(op, interval_array, other)
        tm.assert_equal(result, expected)

        # all nan endpoints
        other = interval_constructor([np.nan] * 4, [np.nan] * 4)
        result = op(interval_array, other)
        expected = self.elementwise_comparison(op, interval_array, other)
        tm.assert_equal(result, expected)

    def test_compare_list_like_interval_mixed_closed(
        self, op, interval_constructor, closed, other_closed
    ):
        interval_array = IntervalArray.from_arrays(range(2), range(1, 3), closed=closed)
        other = interval_constructor(range(2), range(1, 3), closed=other_closed)

        result = op(interval_array, other)
        expected = self.elementwise_comparison(op, interval_array, other)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize(
        "other",
        [
            (
                Interval(0, 1),
                Interval(Timedelta("1 day"), Timedelta("2 days")),
                Interval(4, 5, "both"),
                Interval(10, 20, "neither"),
            ),
            (0, 1.5, Timestamp("20170103"), np.nan),
            (
                Timestamp("20170102", tz="US/Eastern"),
                Timedelta("2 days"),
                "baz",
                pd.NaT,
            ),
        ],
    )
    def test_compare_list_like_object(self, op, interval_array, other):
        result = op(interval_array, other)
        expected = self.elementwise_comparison(op, interval_array, other)
        tm.assert_numpy_array_equal(result, expected)

    def test_compare_list_like_nan(self, op, interval_array, nulls_fixture):
        other = [nulls_fixture] * 4
        result = op(interval_array, other)
        expected = self.elementwise_comparison(op, interval_array, other)

        tm.assert_equal(result, expected)

    @pytest.mark.parametrize(
        "other",
        [
            np.arange(4, dtype="int64"),
            np.arange(4, dtype="float64"),
            date_range("2017-01-01", periods=4),
            date_range("2017-01-01", periods=4, tz="US/Eastern"),
            timedelta_range("0 days", periods=4),
            period_range("2017-01-01", periods=4, freq="D"),
            Categorical(list("abab")),
            Categorical(date_range("2017-01-01", periods=4)),
            pd.array(list("abcd")),
            pd.array(["foo", 3.14, None, object()], dtype=object),
        ],
        ids=lambda x: str(x.dtype),
    )
    def test_compare_list_like_other(self, op, interval_array, other):
        result = op(interval_array, other)
        expected = self.elementwise_comparison(op, interval_array, other)
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize("length", [1, 3, 5])
    @pytest.mark.parametrize("other_constructor", [IntervalArray, list])
    def test_compare_length_mismatch_errors(self, op, other_constructor, length):
        interval_array = IntervalArray.from_arrays(range(4), range(1, 5))
        other = other_constructor([Interval(0, 1)] * length)
        with pytest.raises(ValueError, match="Lengths must match to compare"):
            op(interval_array, other)

    @pytest.mark.parametrize(
        "constructor, expected_type, assert_func",
        [
            (IntervalIndex, np.array, tm.assert_numpy_array_equal),
            (Series, Series, tm.assert_series_equal),
        ],
    )
    def test_index_series_compat(self, op, constructor, expected_type, assert_func):
        # IntervalIndex/Series that rely on IntervalArray for comparisons
        breaks = range(4)
        index = constructor(IntervalIndex.from_breaks(breaks))

        # scalar comparisons
        other = index[0]
        result = op(index, other)
        expected = expected_type(self.elementwise_comparison(op, index, other))
        assert_func(result, expected)

        other = breaks[0]
        result = op(index, other)
        expected = expected_type(self.elementwise_comparison(op, index, other))
        assert_func(result, expected)

        # list-like comparisons
        other = IntervalArray.from_breaks(breaks)
        result = op(index, other)
        expected = expected_type(self.elementwise_comparison(op, index, other))
        assert_func(result, expected)

        other = [index[0], breaks[0], "foo"]
        result = op(index, other)
        expected = expected_type(self.elementwise_comparison(op, index, other))
        assert_func(result, expected)

    @pytest.mark.parametrize("scalars", ["a", False, 1, 1.0, None])
    def test_comparison_operations(self, scalars):
        # GH #28981
        expected = Series([False, False])
        s = Series([Interval(0, 1), Interval(1, 2)], dtype="interval")
        result = s == scalars
        tm.assert_series_equal(result, expected)
