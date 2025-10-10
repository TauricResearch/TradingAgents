import numpy as np
import pytest

from pandas import (
    DataFrame,
    DatetimeIndex,
    Index,
    Interval,
    IntervalIndex,
    Series,
    Timedelta,
    Timestamp,
)
import pandas._testing as tm


class TestIntervalIndexRendering:
    # TODO: this is a test for DataFrame/Series, not IntervalIndex
    @pytest.mark.parametrize(
        "constructor,expected",
        [
            (
                Series,
                (
                    "(0.0, 1.0]    a\n"
                    "NaN           b\n"
                    "(2.0, 3.0]    c\n"
                    "dtype: object"
                ),
            ),
            (DataFrame, ("            0\n(0.0, 1.0]  a\nNaN         b\n(2.0, 3.0]  c")),
        ],
    )
    def test_repr_missing(self, constructor, expected, using_infer_string, request):
        # GH 25984
        if using_infer_string and constructor is Series:
            request.applymarker(pytest.mark.xfail(reason="repr different"))
        index = IntervalIndex.from_tuples([(0, 1), np.nan, (2, 3)])
        obj = constructor(list("abc"), index=index)
        result = repr(obj)
        assert result == expected

    def test_repr_floats(self):
        # GH 32553

        markers = Series(
            [1, 2],
            index=IntervalIndex(
                [
                    Interval(left, right)
                    for left, right in zip(
                        Index([329.973, 345.137], dtype="float64"),
                        Index([345.137, 360.191], dtype="float64"),
                    )
                ]
            ),
        )
        result = str(markers)
        expected = "(329.973, 345.137]    1\n(345.137, 360.191]    2\ndtype: int64"
        assert result == expected

    @pytest.mark.filterwarnings(
        "ignore:invalid value encountered in cast:RuntimeWarning"
    )
    @pytest.mark.parametrize(
        "tuples, closed, expected_data",
        [
            ([(0, 1), (1, 2), (2, 3)], "left", ["[0, 1)", "[1, 2)", "[2, 3)"]),
            (
                [(0.5, 1.0), np.nan, (2.0, 3.0)],
                "right",
                ["(0.5, 1.0]", "NaN", "(2.0, 3.0]"],
            ),
            (
                [
                    (Timestamp("20180101"), Timestamp("20180102")),
                    np.nan,
                    ((Timestamp("20180102"), Timestamp("20180103"))),
                ],
                "both",
                [
                    "[2018-01-01 00:00:00, 2018-01-02 00:00:00]",
                    "NaN",
                    "[2018-01-02 00:00:00, 2018-01-03 00:00:00]",
                ],
            ),
            (
                [
                    (Timedelta("0 days"), Timedelta("1 days")),
                    (Timedelta("1 days"), Timedelta("2 days")),
                    np.nan,
                ],
                "neither",
                [
                    "(0 days 00:00:00, 1 days 00:00:00)",
                    "(1 days 00:00:00, 2 days 00:00:00)",
                    "NaN",
                ],
            ),
        ],
    )
    def test_get_values_for_csv(self, tuples, closed, expected_data):
        # GH 28210
        index = IntervalIndex.from_tuples(tuples, closed=closed)
        result = index._get_values_for_csv(na_rep="NaN")
        expected = np.array(expected_data)
        tm.assert_numpy_array_equal(result, expected)

    def test_timestamp_with_timezone(self, unit):
        # GH 55035
        left = DatetimeIndex(["2020-01-01"], dtype=f"M8[{unit}, UTC]")
        right = DatetimeIndex(["2020-01-02"], dtype=f"M8[{unit}, UTC]")
        index = IntervalIndex.from_arrays(left, right)
        result = repr(index)
        expected = (
            "IntervalIndex([(2020-01-01 00:00:00+00:00, 2020-01-02 00:00:00+00:00]], "
            f"dtype='interval[datetime64[{unit}, UTC], right]')"
        )
        assert result == expected
