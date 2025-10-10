from datetime import datetime

import numpy as np
import pytest

import pandas.util._test_decorators as td

from pandas import (
    DataFrame,
    DatetimeIndex,
    Series,
    concat,
    isna,
    notna,
)
import pandas._testing as tm

from pandas.tseries import offsets


@pytest.mark.parametrize(
    "compare_func, roll_func, kwargs",
    [
        [np.mean, "mean", {}],
        [np.nansum, "sum", {}],
        [
            lambda x: np.isfinite(x).astype(float).sum(),
            "count",
            {},
        ],
        [np.median, "median", {}],
        [np.min, "min", {}],
        [np.max, "max", {}],
        [lambda x: np.std(x, ddof=1), "std", {}],
        [lambda x: np.std(x, ddof=0), "std", {"ddof": 0}],
        [lambda x: np.var(x, ddof=1), "var", {}],
        [lambda x: np.var(x, ddof=0), "var", {"ddof": 0}],
    ],
)
def test_series(series, compare_func, roll_func, kwargs, step):
    result = getattr(series.rolling(50, step=step), roll_func)(**kwargs)
    assert isinstance(result, Series)
    end = range(0, len(series), step or 1)[-1] + 1
    tm.assert_almost_equal(result.iloc[-1], compare_func(series[end - 50 : end]))


@pytest.mark.parametrize(
    "compare_func, roll_func, kwargs",
    [
        [np.mean, "mean", {}],
        [np.nansum, "sum", {}],
        [
            lambda x: np.isfinite(x).astype(float).sum(),
            "count",
            {},
        ],
        [np.median, "median", {}],
        [np.min, "min", {}],
        [np.max, "max", {}],
        [lambda x: np.std(x, ddof=1), "std", {}],
        [lambda x: np.std(x, ddof=0), "std", {"ddof": 0}],
        [lambda x: np.var(x, ddof=1), "var", {}],
        [lambda x: np.var(x, ddof=0), "var", {"ddof": 0}],
    ],
)
def test_frame(raw, frame, compare_func, roll_func, kwargs, step):
    result = getattr(frame.rolling(50, step=step), roll_func)(**kwargs)
    assert isinstance(result, DataFrame)
    end = range(0, len(frame), step or 1)[-1] + 1
    tm.assert_series_equal(
        result.iloc[-1, :],
        frame.iloc[end - 50 : end, :].apply(compare_func, axis=0, raw=raw),
        check_names=False,
    )


@pytest.mark.parametrize(
    "compare_func, roll_func, kwargs, minp",
    [
        [np.mean, "mean", {}, 10],
        [np.nansum, "sum", {}, 10],
        [lambda x: np.isfinite(x).astype(float).sum(), "count", {}, 0],
        [np.median, "median", {}, 10],
        [np.min, "min", {}, 10],
        [np.max, "max", {}, 10],
        [lambda x: np.std(x, ddof=1), "std", {}, 10],
        [lambda x: np.std(x, ddof=0), "std", {"ddof": 0}, 10],
        [lambda x: np.var(x, ddof=1), "var", {}, 10],
        [lambda x: np.var(x, ddof=0), "var", {"ddof": 0}, 10],
    ],
)
def test_time_rule_series(series, compare_func, roll_func, kwargs, minp):
    win = 25
    ser = series[::2].resample("B").mean()
    series_result = getattr(ser.rolling(window=win, min_periods=minp), roll_func)(
        **kwargs
    )
    last_date = series_result.index[-1]
    prev_date = last_date - 24 * offsets.BDay()

    trunc_series = series[::2].truncate(prev_date, last_date)
    tm.assert_almost_equal(series_result.iloc[-1], compare_func(trunc_series))


@pytest.mark.parametrize(
    "compare_func, roll_func, kwargs, minp",
    [
        [np.mean, "mean", {}, 10],
        [np.nansum, "sum", {}, 10],
        [lambda x: np.isfinite(x).astype(float).sum(), "count", {}, 0],
        [np.median, "median", {}, 10],
        [np.min, "min", {}, 10],
        [np.max, "max", {}, 10],
        [lambda x: np.std(x, ddof=1), "std", {}, 10],
        [lambda x: np.std(x, ddof=0), "std", {"ddof": 0}, 10],
        [lambda x: np.var(x, ddof=1), "var", {}, 10],
        [lambda x: np.var(x, ddof=0), "var", {"ddof": 0}, 10],
    ],
)
def test_time_rule_frame(raw, frame, compare_func, roll_func, kwargs, minp):
    win = 25
    frm = frame[::2].resample("B").mean()
    frame_result = getattr(frm.rolling(window=win, min_periods=minp), roll_func)(
        **kwargs
    )
    last_date = frame_result.index[-1]
    prev_date = last_date - 24 * offsets.BDay()

    trunc_frame = frame[::2].truncate(prev_date, last_date)
    tm.assert_series_equal(
        frame_result.xs(last_date),
        trunc_frame.apply(compare_func, raw=raw),
        check_names=False,
    )


@pytest.mark.parametrize(
    "compare_func, roll_func, kwargs",
    [
        [np.mean, "mean", {}],
        [np.nansum, "sum", {}],
        [np.median, "median", {}],
        [np.min, "min", {}],
        [np.max, "max", {}],
        [lambda x: np.std(x, ddof=1), "std", {}],
        [lambda x: np.std(x, ddof=0), "std", {"ddof": 0}],
        [lambda x: np.var(x, ddof=1), "var", {}],
        [lambda x: np.var(x, ddof=0), "var", {"ddof": 0}],
    ],
)
def test_nans(compare_func, roll_func, kwargs):
    obj = Series(np.random.default_rng(2).standard_normal(50))
    obj[:10] = np.nan
    obj[-10:] = np.nan

    result = getattr(obj.rolling(50, min_periods=30), roll_func)(**kwargs)
    tm.assert_almost_equal(result.iloc[-1], compare_func(obj[10:-10]))

    # min_periods is working correctly
    result = getattr(obj.rolling(20, min_periods=15), roll_func)(**kwargs)
    assert isna(result.iloc[23])
    assert not isna(result.iloc[24])

    assert not isna(result.iloc[-6])
    assert isna(result.iloc[-5])

    obj2 = Series(np.random.default_rng(2).standard_normal(20))
    result = getattr(obj2.rolling(10, min_periods=5), roll_func)(**kwargs)
    assert isna(result.iloc[3])
    assert notna(result.iloc[4])

    if roll_func != "sum":
        result0 = getattr(obj.rolling(20, min_periods=0), roll_func)(**kwargs)
        result1 = getattr(obj.rolling(20, min_periods=1), roll_func)(**kwargs)
        tm.assert_almost_equal(result0, result1)


def test_nans_count():
    obj = Series(np.random.default_rng(2).standard_normal(50))
    obj[:10] = np.nan
    obj[-10:] = np.nan
    result = obj.rolling(50, min_periods=30).count()
    tm.assert_almost_equal(
        result.iloc[-1], np.isfinite(obj[10:-10]).astype(float).sum()
    )


@pytest.mark.parametrize(
    "roll_func, kwargs",
    [
        ["mean", {}],
        ["sum", {}],
        ["median", {}],
        ["min", {}],
        ["max", {}],
        ["std", {}],
        ["std", {"ddof": 0}],
        ["var", {}],
        ["var", {"ddof": 0}],
    ],
)
@pytest.mark.parametrize("minp", [0, 99, 100])
def test_min_periods(series, minp, roll_func, kwargs, step):
    result = getattr(
        series.rolling(len(series) + 1, min_periods=minp, step=step), roll_func
    )(**kwargs)
    expected = getattr(
        series.rolling(len(series), min_periods=minp, step=step), roll_func
    )(**kwargs)
    nan_mask = isna(result)
    tm.assert_series_equal(nan_mask, isna(expected))

    nan_mask = ~nan_mask
    tm.assert_almost_equal(result[nan_mask], expected[nan_mask])


def test_min_periods_count(series, step):
    result = series.rolling(len(series) + 1, min_periods=0, step=step).count()
    expected = series.rolling(len(series), min_periods=0, step=step).count()
    nan_mask = isna(result)
    tm.assert_series_equal(nan_mask, isna(expected))

    nan_mask = ~nan_mask
    tm.assert_almost_equal(result[nan_mask], expected[nan_mask])


@pytest.mark.parametrize(
    "roll_func, kwargs, minp",
    [
        ["mean", {}, 15],
        ["sum", {}, 15],
        ["count", {}, 0],
        ["median", {}, 15],
        ["min", {}, 15],
        ["max", {}, 15],
        ["std", {}, 15],
        ["std", {"ddof": 0}, 15],
        ["var", {}, 15],
        ["var", {"ddof": 0}, 15],
    ],
)
def test_center(roll_func, kwargs, minp):
    obj = Series(np.random.default_rng(2).standard_normal(50))
    obj[:10] = np.nan
    obj[-10:] = np.nan

    result = getattr(obj.rolling(20, min_periods=minp, center=True), roll_func)(
        **kwargs
    )
    expected = (
        getattr(
            concat([obj, Series([np.nan] * 9)]).rolling(20, min_periods=minp), roll_func
        )(**kwargs)
        .iloc[9:]
        .reset_index(drop=True)
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "roll_func, kwargs, minp, fill_value",
    [
        ["mean", {}, 10, None],
        ["sum", {}, 10, None],
        ["count", {}, 0, 0],
        ["median", {}, 10, None],
        ["min", {}, 10, None],
        ["max", {}, 10, None],
        ["std", {}, 10, None],
        ["std", {"ddof": 0}, 10, None],
        ["var", {}, 10, None],
        ["var", {"ddof": 0}, 10, None],
    ],
)
def test_center_reindex_series(series, roll_func, kwargs, minp, fill_value):
    # shifter index
    s = [f"x{x:d}" for x in range(12)]

    series_xp = (
        getattr(
            series.reindex(list(series.index) + s).rolling(window=25, min_periods=minp),
            roll_func,
        )(**kwargs)
        .shift(-12)
        .reindex(series.index)
    )
    series_rs = getattr(
        series.rolling(window=25, min_periods=minp, center=True), roll_func
    )(**kwargs)
    if fill_value is not None:
        series_xp = series_xp.fillna(fill_value)
    tm.assert_series_equal(series_xp, series_rs)


@pytest.mark.parametrize(
    "roll_func, kwargs, minp, fill_value",
    [
        ["mean", {}, 10, None],
        ["sum", {}, 10, None],
        ["count", {}, 0, 0],
        ["median", {}, 10, None],
        ["min", {}, 10, None],
        ["max", {}, 10, None],
        ["std", {}, 10, None],
        ["std", {"ddof": 0}, 10, None],
        ["var", {}, 10, None],
        ["var", {"ddof": 0}, 10, None],
    ],
)
def test_center_reindex_frame(frame, roll_func, kwargs, minp, fill_value):
    # shifter index
    s = [f"x{x:d}" for x in range(12)]

    frame_xp = (
        getattr(
            frame.reindex(list(frame.index) + s).rolling(window=25, min_periods=minp),
            roll_func,
        )(**kwargs)
        .shift(-12)
        .reindex(frame.index)
    )
    frame_rs = getattr(
        frame.rolling(window=25, min_periods=minp, center=True), roll_func
    )(**kwargs)
    if fill_value is not None:
        frame_xp = frame_xp.fillna(fill_value)
    tm.assert_frame_equal(frame_xp, frame_rs)


@pytest.mark.parametrize(
    "f",
    [
        lambda x: x.rolling(window=10, min_periods=5).cov(x, pairwise=False),
        lambda x: x.rolling(window=10, min_periods=5).corr(x, pairwise=False),
        lambda x: x.rolling(window=10, min_periods=5).max(),
        lambda x: x.rolling(window=10, min_periods=5).min(),
        lambda x: x.rolling(window=10, min_periods=5).sum(),
        lambda x: x.rolling(window=10, min_periods=5).mean(),
        lambda x: x.rolling(window=10, min_periods=5).std(),
        lambda x: x.rolling(window=10, min_periods=5).var(),
        lambda x: x.rolling(window=10, min_periods=5).skew(),
        lambda x: x.rolling(window=10, min_periods=5).kurt(),
        lambda x: x.rolling(window=10, min_periods=5).quantile(q=0.5),
        lambda x: x.rolling(window=10, min_periods=5).median(),
        lambda x: x.rolling(window=10, min_periods=5).apply(sum, raw=False),
        lambda x: x.rolling(window=10, min_periods=5).apply(sum, raw=True),
        pytest.param(
            lambda x: x.rolling(win_type="boxcar", window=10, min_periods=5).mean(),
            marks=td.skip_if_no("scipy"),
        ),
    ],
)
def test_rolling_functions_window_non_shrinkage(f):
    # GH 7764
    s = Series(range(4))
    s_expected = Series(np.nan, index=s.index)
    df = DataFrame([[1, 5], [3, 2], [3, 9], [-1, 0]], columns=["A", "B"])
    df_expected = DataFrame(np.nan, index=df.index, columns=df.columns)

    s_result = f(s)
    tm.assert_series_equal(s_result, s_expected)

    df_result = f(df)
    tm.assert_frame_equal(df_result, df_expected)


def test_rolling_max_gh6297(step):
    """Replicate result expected in GH #6297"""
    indices = [datetime(1975, 1, i) for i in range(1, 6)]
    # So that we can have 2 datapoints on one of the days
    indices.append(datetime(1975, 1, 3, 6, 0))
    series = Series(range(1, 7), index=indices)
    # Use floats instead of ints as values
    series = series.map(lambda x: float(x))
    # Sort chronologically
    series = series.sort_index()

    expected = Series(
        [1.0, 2.0, 6.0, 4.0, 5.0],
        index=DatetimeIndex([datetime(1975, 1, i, 0) for i in range(1, 6)], freq="D"),
    )[::step]
    x = series.resample("D").max().rolling(window=1, step=step).max()
    tm.assert_series_equal(expected, x)


def test_rolling_max_resample(step):
    indices = [datetime(1975, 1, i) for i in range(1, 6)]
    # So that we can have 3 datapoints on last day (4, 10, and 20)
    indices.append(datetime(1975, 1, 5, 1))
    indices.append(datetime(1975, 1, 5, 2))
    series = Series(list(range(5)) + [10, 20], index=indices)
    # Use floats instead of ints as values
    series = series.map(lambda x: float(x))
    # Sort chronologically
    series = series.sort_index()

    # Default how should be max
    expected = Series(
        [0.0, 1.0, 2.0, 3.0, 20.0],
        index=DatetimeIndex([datetime(1975, 1, i, 0) for i in range(1, 6)], freq="D"),
    )[::step]
    x = series.resample("D").max().rolling(window=1, step=step).max()
    tm.assert_series_equal(expected, x)

    # Now specify median (10.0)
    expected = Series(
        [0.0, 1.0, 2.0, 3.0, 10.0],
        index=DatetimeIndex([datetime(1975, 1, i, 0) for i in range(1, 6)], freq="D"),
    )[::step]
    x = series.resample("D").median().rolling(window=1, step=step).max()
    tm.assert_series_equal(expected, x)

    # Now specify mean (4+10+20)/3
    v = (4.0 + 10.0 + 20.0) / 3.0
    expected = Series(
        [0.0, 1.0, 2.0, 3.0, v],
        index=DatetimeIndex([datetime(1975, 1, i, 0) for i in range(1, 6)], freq="D"),
    )[::step]
    x = series.resample("D").mean().rolling(window=1, step=step).max()
    tm.assert_series_equal(expected, x)


def test_rolling_min_resample(step):
    indices = [datetime(1975, 1, i) for i in range(1, 6)]
    # So that we can have 3 datapoints on last day (4, 10, and 20)
    indices.append(datetime(1975, 1, 5, 1))
    indices.append(datetime(1975, 1, 5, 2))
    series = Series(list(range(5)) + [10, 20], index=indices)
    # Use floats instead of ints as values
    series = series.map(lambda x: float(x))
    # Sort chronologically
    series = series.sort_index()

    # Default how should be min
    expected = Series(
        [0.0, 1.0, 2.0, 3.0, 4.0],
        index=DatetimeIndex([datetime(1975, 1, i, 0) for i in range(1, 6)], freq="D"),
    )[::step]
    r = series.resample("D").min().rolling(window=1, step=step)
    tm.assert_series_equal(expected, r.min())


def test_rolling_median_resample():
    indices = [datetime(1975, 1, i) for i in range(1, 6)]
    # So that we can have 3 datapoints on last day (4, 10, and 20)
    indices.append(datetime(1975, 1, 5, 1))
    indices.append(datetime(1975, 1, 5, 2))
    series = Series(list(range(5)) + [10, 20], index=indices)
    # Use floats instead of ints as values
    series = series.map(lambda x: float(x))
    # Sort chronologically
    series = series.sort_index()

    # Default how should be median
    expected = Series(
        [0.0, 1.0, 2.0, 3.0, 10],
        index=DatetimeIndex([datetime(1975, 1, i, 0) for i in range(1, 6)], freq="D"),
    )
    x = series.resample("D").median().rolling(window=1).median()
    tm.assert_series_equal(expected, x)


def test_rolling_median_memory_error():
    # GH11722
    n = 20000
    Series(np.random.default_rng(2).standard_normal(n)).rolling(
        window=2, center=False
    ).median()
    Series(np.random.default_rng(2).standard_normal(n)).rolling(
        window=2, center=False
    ).median()


@pytest.mark.parametrize(
    "data_type",
    [np.dtype(f"f{width}") for width in [4, 8]]
    + [np.dtype(f"{sign}{width}") for width in [1, 2, 4, 8] for sign in "ui"],
)
def test_rolling_min_max_numeric_types(data_type):
    # GH12373

    # Just testing that these don't throw exceptions and that
    # the return type is float64. Other tests will cover quantitative
    # correctness
    result = DataFrame(np.arange(20, dtype=data_type)).rolling(window=5).max()
    assert result.dtypes[0] == np.dtype("f8")
    result = DataFrame(np.arange(20, dtype=data_type)).rolling(window=5).min()
    assert result.dtypes[0] == np.dtype("f8")


@pytest.mark.parametrize(
    "f",
    [
        lambda x: x.rolling(window=10, min_periods=0).count(),
        lambda x: x.rolling(window=10, min_periods=5).cov(x, pairwise=False),
        lambda x: x.rolling(window=10, min_periods=5).corr(x, pairwise=False),
        lambda x: x.rolling(window=10, min_periods=5).max(),
        lambda x: x.rolling(window=10, min_periods=5).min(),
        lambda x: x.rolling(window=10, min_periods=5).sum(),
        lambda x: x.rolling(window=10, min_periods=5).mean(),
        lambda x: x.rolling(window=10, min_periods=5).std(),
        lambda x: x.rolling(window=10, min_periods=5).var(),
        lambda x: x.rolling(window=10, min_periods=5).skew(),
        lambda x: x.rolling(window=10, min_periods=5).kurt(),
        lambda x: x.rolling(window=10, min_periods=5).quantile(0.5),
        lambda x: x.rolling(window=10, min_periods=5).median(),
        lambda x: x.rolling(window=10, min_periods=5).apply(sum, raw=False),
        lambda x: x.rolling(window=10, min_periods=5).apply(sum, raw=True),
        pytest.param(
            lambda x: x.rolling(win_type="boxcar", window=10, min_periods=5).mean(),
            marks=td.skip_if_no("scipy"),
        ),
    ],
)
def test_moment_functions_zero_length(f):
    # GH 8056
    s = Series(dtype=np.float64)
    s_expected = s
    df1 = DataFrame()
    df1_expected = df1
    df2 = DataFrame(columns=["a"])
    df2["a"] = df2["a"].astype("float64")
    df2_expected = df2

    s_result = f(s)
    tm.assert_series_equal(s_result, s_expected)

    df1_result = f(df1)
    tm.assert_frame_equal(df1_result, df1_expected)

    df2_result = f(df2)
    tm.assert_frame_equal(df2_result, df2_expected)
