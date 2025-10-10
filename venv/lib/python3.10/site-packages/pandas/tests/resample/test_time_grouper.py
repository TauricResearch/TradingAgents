from datetime import datetime
from operator import methodcaller

import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    Series,
    Timestamp,
)
import pandas._testing as tm
from pandas.core.groupby.grouper import Grouper
from pandas.core.indexes.datetimes import date_range


@pytest.fixture
def test_series():
    return Series(
        np.random.default_rng(2).standard_normal(1000),
        index=date_range("1/1/2000", periods=1000),
    )


def test_apply(test_series):
    grouper = Grouper(freq="YE", label="right", closed="right")

    grouped = test_series.groupby(grouper)

    def f(x):
        return x.sort_values()[-3:]

    applied = grouped.apply(f)
    expected = test_series.groupby(lambda x: x.year).apply(f)

    applied.index = applied.index.droplevel(0)
    expected.index = expected.index.droplevel(0)
    tm.assert_series_equal(applied, expected)


def test_count(test_series):
    test_series[::3] = np.nan

    expected = test_series.groupby(lambda x: x.year).count()

    grouper = Grouper(freq="YE", label="right", closed="right")
    result = test_series.groupby(grouper).count()
    expected.index = result.index
    tm.assert_series_equal(result, expected)

    result = test_series.resample("YE").count()
    expected.index = result.index
    tm.assert_series_equal(result, expected)


def test_numpy_reduction(test_series):
    result = test_series.resample("YE", closed="right").prod()

    msg = "using SeriesGroupBy.prod"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        expected = test_series.groupby(lambda x: x.year).agg(np.prod)
    expected.index = result.index

    tm.assert_series_equal(result, expected)


def test_apply_iteration():
    # #2300
    N = 1000
    ind = date_range(start="2000-01-01", freq="D", periods=N)
    df = DataFrame({"open": 1, "close": 2}, index=ind)
    tg = Grouper(freq="ME")

    grouper, _ = tg._get_grouper(df)

    # Errors
    grouped = df.groupby(grouper, group_keys=False)

    def f(df):
        return df["close"] / df["open"]

    # it works!
    result = grouped.apply(f)
    tm.assert_index_equal(result.index, df.index)


@pytest.mark.parametrize(
    "index",
    [
        Index([1, 2]),
        Index(["a", "b"]),
        Index([1.1, 2.2]),
        pd.MultiIndex.from_arrays([[1, 2], ["a", "b"]]),
    ],
)
def test_fails_on_no_datetime_index(index):
    name = type(index).__name__
    df = DataFrame({"a": range(len(index))}, index=index)

    msg = (
        "Only valid with DatetimeIndex, TimedeltaIndex "
        f"or PeriodIndex, but got an instance of '{name}'"
    )
    with pytest.raises(TypeError, match=msg):
        df.groupby(Grouper(freq="D"))


def test_aaa_group_order():
    # GH 12840
    # check TimeGrouper perform stable sorts
    n = 20
    data = np.random.default_rng(2).standard_normal((n, 4))
    df = DataFrame(data, columns=["A", "B", "C", "D"])
    df["key"] = [
        datetime(2013, 1, 1),
        datetime(2013, 1, 2),
        datetime(2013, 1, 3),
        datetime(2013, 1, 4),
        datetime(2013, 1, 5),
    ] * 4
    grouped = df.groupby(Grouper(key="key", freq="D"))

    tm.assert_frame_equal(grouped.get_group(datetime(2013, 1, 1)), df[::5])
    tm.assert_frame_equal(grouped.get_group(datetime(2013, 1, 2)), df[1::5])
    tm.assert_frame_equal(grouped.get_group(datetime(2013, 1, 3)), df[2::5])
    tm.assert_frame_equal(grouped.get_group(datetime(2013, 1, 4)), df[3::5])
    tm.assert_frame_equal(grouped.get_group(datetime(2013, 1, 5)), df[4::5])


def test_aggregate_normal(resample_method):
    """Check TimeGrouper's aggregation is identical as normal groupby."""

    data = np.random.default_rng(2).standard_normal((20, 4))
    normal_df = DataFrame(data, columns=["A", "B", "C", "D"])
    normal_df["key"] = [1, 2, 3, 4, 5] * 4

    dt_df = DataFrame(data, columns=["A", "B", "C", "D"])
    dt_df["key"] = Index(
        [
            datetime(2013, 1, 1),
            datetime(2013, 1, 2),
            datetime(2013, 1, 3),
            datetime(2013, 1, 4),
            datetime(2013, 1, 5),
        ]
        * 4,
        dtype="M8[ns]",
    )

    normal_grouped = normal_df.groupby("key")
    dt_grouped = dt_df.groupby(Grouper(key="key", freq="D"))

    expected = getattr(normal_grouped, resample_method)()
    dt_result = getattr(dt_grouped, resample_method)()
    expected.index = date_range(start="2013-01-01", freq="D", periods=5, name="key")
    tm.assert_equal(expected, dt_result)


@pytest.mark.xfail(reason="if TimeGrouper is used included, 'nth' doesn't work yet")
def test_aggregate_nth():
    """Check TimeGrouper's aggregation is identical as normal groupby."""

    data = np.random.default_rng(2).standard_normal((20, 4))
    normal_df = DataFrame(data, columns=["A", "B", "C", "D"])
    normal_df["key"] = [1, 2, 3, 4, 5] * 4

    dt_df = DataFrame(data, columns=["A", "B", "C", "D"])
    dt_df["key"] = [
        datetime(2013, 1, 1),
        datetime(2013, 1, 2),
        datetime(2013, 1, 3),
        datetime(2013, 1, 4),
        datetime(2013, 1, 5),
    ] * 4

    normal_grouped = normal_df.groupby("key")
    dt_grouped = dt_df.groupby(Grouper(key="key", freq="D"))

    expected = normal_grouped.nth(3)
    expected.index = date_range(start="2013-01-01", freq="D", periods=5, name="key")
    dt_result = dt_grouped.nth(3)
    tm.assert_frame_equal(expected, dt_result)


@pytest.mark.parametrize(
    "method, method_args, unit",
    [
        ("sum", {}, 0),
        ("sum", {"min_count": 0}, 0),
        ("sum", {"min_count": 1}, np.nan),
        ("prod", {}, 1),
        ("prod", {"min_count": 0}, 1),
        ("prod", {"min_count": 1}, np.nan),
    ],
)
def test_resample_entirely_nat_window(method, method_args, unit):
    ser = Series([0] * 2 + [np.nan] * 2, index=date_range("2017", periods=4))
    result = methodcaller(method, **method_args)(ser.resample("2d"))

    exp_dti = pd.DatetimeIndex(["2017-01-01", "2017-01-03"], dtype="M8[ns]", freq="2D")
    expected = Series([0.0, unit], index=exp_dti)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "func, fill_value",
    [("min", np.nan), ("max", np.nan), ("sum", 0), ("prod", 1), ("count", 0)],
)
def test_aggregate_with_nat(func, fill_value):
    # check TimeGrouper's aggregation is identical as normal groupby
    # if NaT is included, 'var', 'std', 'mean', 'first','last'
    # and 'nth' doesn't work yet

    n = 20
    data = np.random.default_rng(2).standard_normal((n, 4)).astype("int64")
    normal_df = DataFrame(data, columns=["A", "B", "C", "D"])
    normal_df["key"] = [1, 2, np.nan, 4, 5] * 4

    dt_df = DataFrame(data, columns=["A", "B", "C", "D"])
    dt_df["key"] = Index(
        [
            datetime(2013, 1, 1),
            datetime(2013, 1, 2),
            pd.NaT,
            datetime(2013, 1, 4),
            datetime(2013, 1, 5),
        ]
        * 4,
        dtype="M8[ns]",
    )

    normal_grouped = normal_df.groupby("key")
    dt_grouped = dt_df.groupby(Grouper(key="key", freq="D"))

    normal_result = getattr(normal_grouped, func)()
    dt_result = getattr(dt_grouped, func)()

    pad = DataFrame([[fill_value] * 4], index=[3], columns=["A", "B", "C", "D"])
    expected = pd.concat([normal_result, pad])
    expected = expected.sort_index()
    dti = date_range(
        start="2013-01-01",
        freq="D",
        periods=5,
        name="key",
        unit=dt_df["key"]._values.unit,
    )
    expected.index = dti._with_freq(None)  # TODO: is this desired?
    tm.assert_frame_equal(expected, dt_result)
    assert dt_result.index.name == "key"


def test_aggregate_with_nat_size():
    # GH 9925
    n = 20
    data = np.random.default_rng(2).standard_normal((n, 4)).astype("int64")
    normal_df = DataFrame(data, columns=["A", "B", "C", "D"])
    normal_df["key"] = [1, 2, np.nan, 4, 5] * 4

    dt_df = DataFrame(data, columns=["A", "B", "C", "D"])
    dt_df["key"] = Index(
        [
            datetime(2013, 1, 1),
            datetime(2013, 1, 2),
            pd.NaT,
            datetime(2013, 1, 4),
            datetime(2013, 1, 5),
        ]
        * 4,
        dtype="M8[ns]",
    )

    normal_grouped = normal_df.groupby("key")
    dt_grouped = dt_df.groupby(Grouper(key="key", freq="D"))

    normal_result = normal_grouped.size()
    dt_result = dt_grouped.size()

    pad = Series([0], index=[3])
    expected = pd.concat([normal_result, pad])
    expected = expected.sort_index()
    expected.index = date_range(
        start="2013-01-01",
        freq="D",
        periods=5,
        name="key",
        unit=dt_df["key"]._values.unit,
    )._with_freq(None)
    tm.assert_series_equal(expected, dt_result)
    assert dt_result.index.name == "key"


def test_repr():
    # GH18203
    result = repr(Grouper(key="A", freq="h"))
    expected = (
        "TimeGrouper(key='A', freq=<Hour>, axis=0, sort=True, dropna=True, "
        "closed='left', label='left', how='mean', "
        "convention='e', origin='start_day')"
    )
    assert result == expected

    result = repr(Grouper(key="A", freq="h", origin="2000-01-01"))
    expected = (
        "TimeGrouper(key='A', freq=<Hour>, axis=0, sort=True, dropna=True, "
        "closed='left', label='left', how='mean', "
        "convention='e', origin=Timestamp('2000-01-01 00:00:00'))"
    )
    assert result == expected


@pytest.mark.parametrize(
    "method, method_args, expected_values",
    [
        ("sum", {}, [1, 0, 1]),
        ("sum", {"min_count": 0}, [1, 0, 1]),
        ("sum", {"min_count": 1}, [1, np.nan, 1]),
        ("sum", {"min_count": 2}, [np.nan, np.nan, np.nan]),
        ("prod", {}, [1, 1, 1]),
        ("prod", {"min_count": 0}, [1, 1, 1]),
        ("prod", {"min_count": 1}, [1, np.nan, 1]),
        ("prod", {"min_count": 2}, [np.nan, np.nan, np.nan]),
    ],
)
def test_upsample_sum(method, method_args, expected_values):
    ser = Series(1, index=date_range("2017", periods=2, freq="h"))
    resampled = ser.resample("30min")
    index = pd.DatetimeIndex(
        ["2017-01-01T00:00:00", "2017-01-01T00:30:00", "2017-01-01T01:00:00"],
        dtype="M8[ns]",
        freq="30min",
    )
    result = methodcaller(method, **method_args)(resampled)
    expected = Series(expected_values, index=index)
    tm.assert_series_equal(result, expected)


def test_groupby_resample_interpolate():
    # GH 35325
    d = {"price": [10, 11, 9], "volume": [50, 60, 50]}

    df = DataFrame(d)

    df["week_starting"] = date_range("01/01/2018", periods=3, freq="W")

    msg = "DataFrameGroupBy.resample operated on the grouping columns"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = (
            df.set_index("week_starting")
            .groupby("volume")
            .resample("1D")
            .interpolate(method="linear")
        )

    volume = [50] * 15 + [60]
    week_starting = list(date_range("2018-01-07", "2018-01-21")) + [
        Timestamp("2018-01-14")
    ]
    expected_ind = pd.MultiIndex.from_arrays(
        [volume, week_starting],
        names=["volume", "week_starting"],
    )

    expected = DataFrame(
        data={
            "price": [
                10.0,
                9.928571428571429,
                9.857142857142858,
                9.785714285714286,
                9.714285714285714,
                9.642857142857142,
                9.571428571428571,
                9.5,
                9.428571428571429,
                9.357142857142858,
                9.285714285714286,
                9.214285714285714,
                9.142857142857142,
                9.071428571428571,
                9.0,
                11.0,
            ],
            "volume": [50.0] * 15 + [60],
        },
        index=expected_ind,
    )
    tm.assert_frame_equal(result, expected)
