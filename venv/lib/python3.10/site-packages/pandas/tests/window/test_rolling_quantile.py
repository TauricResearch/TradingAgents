from functools import partial

import numpy as np
import pytest

from pandas import (
    DataFrame,
    Series,
    concat,
    isna,
    notna,
)
import pandas._testing as tm

from pandas.tseries import offsets


def scoreatpercentile(a, per):
    values = np.sort(a, axis=0)

    idx = int(per / 1.0 * (values.shape[0] - 1))

    if idx == values.shape[0] - 1:
        retval = values[-1]

    else:
        qlow = idx / (values.shape[0] - 1)
        qhig = (idx + 1) / (values.shape[0] - 1)
        vlow = values[idx]
        vhig = values[idx + 1]
        retval = vlow + (vhig - vlow) * (per - qlow) / (qhig - qlow)

    return retval


@pytest.mark.parametrize("q", [0.0, 0.1, 0.5, 0.9, 1.0])
def test_series(series, q, step):
    compare_func = partial(scoreatpercentile, per=q)
    result = series.rolling(50, step=step).quantile(q)
    assert isinstance(result, Series)
    end = range(0, len(series), step or 1)[-1] + 1
    tm.assert_almost_equal(result.iloc[-1], compare_func(series[end - 50 : end]))


@pytest.mark.parametrize("q", [0.0, 0.1, 0.5, 0.9, 1.0])
def test_frame(raw, frame, q, step):
    compare_func = partial(scoreatpercentile, per=q)
    result = frame.rolling(50, step=step).quantile(q)
    assert isinstance(result, DataFrame)
    end = range(0, len(frame), step or 1)[-1] + 1
    tm.assert_series_equal(
        result.iloc[-1, :],
        frame.iloc[end - 50 : end, :].apply(compare_func, axis=0, raw=raw),
        check_names=False,
    )


@pytest.mark.parametrize("q", [0.0, 0.1, 0.5, 0.9, 1.0])
def test_time_rule_series(series, q):
    compare_func = partial(scoreatpercentile, per=q)
    win = 25
    ser = series[::2].resample("B").mean()
    series_result = ser.rolling(window=win, min_periods=10).quantile(q)
    last_date = series_result.index[-1]
    prev_date = last_date - 24 * offsets.BDay()

    trunc_series = series[::2].truncate(prev_date, last_date)
    tm.assert_almost_equal(series_result.iloc[-1], compare_func(trunc_series))


@pytest.mark.parametrize("q", [0.0, 0.1, 0.5, 0.9, 1.0])
def test_time_rule_frame(raw, frame, q):
    compare_func = partial(scoreatpercentile, per=q)
    win = 25
    frm = frame[::2].resample("B").mean()
    frame_result = frm.rolling(window=win, min_periods=10).quantile(q)
    last_date = frame_result.index[-1]
    prev_date = last_date - 24 * offsets.BDay()

    trunc_frame = frame[::2].truncate(prev_date, last_date)
    tm.assert_series_equal(
        frame_result.xs(last_date),
        trunc_frame.apply(compare_func, raw=raw),
        check_names=False,
    )


@pytest.mark.parametrize("q", [0.0, 0.1, 0.5, 0.9, 1.0])
def test_nans(q):
    compare_func = partial(scoreatpercentile, per=q)
    obj = Series(np.random.default_rng(2).standard_normal(50))
    obj[:10] = np.nan
    obj[-10:] = np.nan

    result = obj.rolling(50, min_periods=30).quantile(q)
    tm.assert_almost_equal(result.iloc[-1], compare_func(obj[10:-10]))

    # min_periods is working correctly
    result = obj.rolling(20, min_periods=15).quantile(q)
    assert isna(result.iloc[23])
    assert not isna(result.iloc[24])

    assert not isna(result.iloc[-6])
    assert isna(result.iloc[-5])

    obj2 = Series(np.random.default_rng(2).standard_normal(20))
    result = obj2.rolling(10, min_periods=5).quantile(q)
    assert isna(result.iloc[3])
    assert notna(result.iloc[4])

    result0 = obj.rolling(20, min_periods=0).quantile(q)
    result1 = obj.rolling(20, min_periods=1).quantile(q)
    tm.assert_almost_equal(result0, result1)


@pytest.mark.parametrize("minp", [0, 99, 100])
@pytest.mark.parametrize("q", [0.0, 0.1, 0.5, 0.9, 1.0])
def test_min_periods(series, minp, q, step):
    result = series.rolling(len(series) + 1, min_periods=minp, step=step).quantile(q)
    expected = series.rolling(len(series), min_periods=minp, step=step).quantile(q)
    nan_mask = isna(result)
    tm.assert_series_equal(nan_mask, isna(expected))

    nan_mask = ~nan_mask
    tm.assert_almost_equal(result[nan_mask], expected[nan_mask])


@pytest.mark.parametrize("q", [0.0, 0.1, 0.5, 0.9, 1.0])
def test_center(q):
    obj = Series(np.random.default_rng(2).standard_normal(50))
    obj[:10] = np.nan
    obj[-10:] = np.nan

    result = obj.rolling(20, center=True).quantile(q)
    expected = (
        concat([obj, Series([np.nan] * 9)])
        .rolling(20)
        .quantile(q)
        .iloc[9:]
        .reset_index(drop=True)
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("q", [0.0, 0.1, 0.5, 0.9, 1.0])
def test_center_reindex_series(series, q):
    # shifter index
    s = [f"x{x:d}" for x in range(12)]

    series_xp = (
        series.reindex(list(series.index) + s)
        .rolling(window=25)
        .quantile(q)
        .shift(-12)
        .reindex(series.index)
    )

    series_rs = series.rolling(window=25, center=True).quantile(q)
    tm.assert_series_equal(series_xp, series_rs)


@pytest.mark.parametrize("q", [0.0, 0.1, 0.5, 0.9, 1.0])
def test_center_reindex_frame(frame, q):
    # shifter index
    s = [f"x{x:d}" for x in range(12)]

    frame_xp = (
        frame.reindex(list(frame.index) + s)
        .rolling(window=25)
        .quantile(q)
        .shift(-12)
        .reindex(frame.index)
    )
    frame_rs = frame.rolling(window=25, center=True).quantile(q)
    tm.assert_frame_equal(frame_xp, frame_rs)


def test_keyword_quantile_deprecated():
    # GH #52550
    s = Series([1, 2, 3, 4])
    with tm.assert_produces_warning(FutureWarning):
        s.rolling(2).quantile(quantile=0.4)
