import numpy as np
import pytest

from pandas import (
    MultiIndex,
    Series,
    date_range,
)
import pandas._testing as tm


def test_nlargest():
    a = Series([1, 3, 5, 7, 2, 9, 0, 4, 6, 10])
    b = Series(list("a" * 5 + "b" * 5))
    gb = a.groupby(b)
    r = gb.nlargest(3)
    e = Series(
        [7, 5, 3, 10, 9, 6],
        index=MultiIndex.from_arrays([list("aaabbb"), [3, 2, 1, 9, 5, 8]]),
    )
    tm.assert_series_equal(r, e)

    a = Series([1, 1, 3, 2, 0, 3, 3, 2, 1, 0])
    gb = a.groupby(b)
    e = Series(
        [3, 2, 1, 3, 3, 2],
        index=MultiIndex.from_arrays([list("aaabbb"), [2, 3, 1, 6, 5, 7]]),
    )
    tm.assert_series_equal(gb.nlargest(3, keep="last"), e)


def test_nlargest_mi_grouper():
    # see gh-21411
    npr = np.random.default_rng(2)

    dts = date_range("20180101", periods=10)
    iterables = [dts, ["one", "two"]]

    idx = MultiIndex.from_product(iterables, names=["first", "second"])
    s = Series(npr.standard_normal(20), index=idx)

    result = s.groupby("first").nlargest(1)

    exp_idx = MultiIndex.from_tuples(
        [
            (dts[0], dts[0], "one"),
            (dts[1], dts[1], "one"),
            (dts[2], dts[2], "one"),
            (dts[3], dts[3], "two"),
            (dts[4], dts[4], "one"),
            (dts[5], dts[5], "one"),
            (dts[6], dts[6], "one"),
            (dts[7], dts[7], "one"),
            (dts[8], dts[8], "one"),
            (dts[9], dts[9], "one"),
        ],
        names=["first", "first", "second"],
    )

    exp_values = [
        0.18905338179353307,
        -0.41306354339189344,
        1.799707382720902,
        0.7738065867276614,
        0.28121066979764925,
        0.9775674511260357,
        -0.3288239040579627,
        0.45495807124085547,
        0.5452887139646817,
        0.12682784711186987,
    ]

    expected = Series(exp_values, index=exp_idx)
    tm.assert_series_equal(result, expected, check_exact=False, rtol=1e-3)


def test_nsmallest():
    a = Series([1, 3, 5, 7, 2, 9, 0, 4, 6, 10])
    b = Series(list("a" * 5 + "b" * 5))
    gb = a.groupby(b)
    r = gb.nsmallest(3)
    e = Series(
        [1, 2, 3, 0, 4, 6],
        index=MultiIndex.from_arrays([list("aaabbb"), [0, 4, 1, 6, 7, 8]]),
    )
    tm.assert_series_equal(r, e)

    a = Series([1, 1, 3, 2, 0, 3, 3, 2, 1, 0])
    gb = a.groupby(b)
    e = Series(
        [0, 1, 1, 0, 1, 2],
        index=MultiIndex.from_arrays([list("aaabbb"), [4, 1, 0, 9, 8, 7]]),
    )
    tm.assert_series_equal(gb.nsmallest(3, keep="last"), e)


@pytest.mark.parametrize(
    "data, groups",
    [([0, 1, 2, 3], [0, 0, 1, 1]), ([0], [0])],
)
@pytest.mark.parametrize("dtype", [None, *tm.ALL_INT_NUMPY_DTYPES])
@pytest.mark.parametrize("method", ["nlargest", "nsmallest"])
def test_nlargest_and_smallest_noop(data, groups, dtype, method):
    # GH 15272, GH 16345, GH 29129
    # Test nlargest/smallest when it results in a noop,
    # i.e. input is sorted and group size <= n
    if dtype is not None:
        data = np.array(data, dtype=dtype)
    if method == "nlargest":
        data = list(reversed(data))
    ser = Series(data, name="a")
    result = getattr(ser.groupby(groups), method)(n=2)
    expidx = np.array(groups, dtype=int) if isinstance(groups, list) else groups
    expected = Series(data, index=MultiIndex.from_arrays([expidx, ser.index]), name="a")
    tm.assert_series_equal(result, expected)
