import numpy as np
import pytest

from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Series,
    Timestamp,
    concat,
    date_range,
    isna,
    notna,
)
import pandas._testing as tm

from pandas.tseries import offsets

# suppress warnings about empty slices, as we are deliberately testing
# with a 0-length Series
pytestmark = pytest.mark.filterwarnings(
    "ignore:.*(empty slice|0 for slice).*:RuntimeWarning"
)


def f(x):
    return x[np.isfinite(x)].mean()


@pytest.mark.parametrize("bad_raw", [None, 1, 0])
def test_rolling_apply_invalid_raw(bad_raw):
    with pytest.raises(ValueError, match="raw parameter must be `True` or `False`"):
        Series(range(3)).rolling(1).apply(len, raw=bad_raw)


def test_rolling_apply_out_of_bounds(engine_and_raw):
    # gh-1850
    engine, raw = engine_and_raw

    vals = Series([1, 2, 3, 4])

    result = vals.rolling(10).apply(np.sum, engine=engine, raw=raw)
    assert result.isna().all()

    result = vals.rolling(10, min_periods=1).apply(np.sum, engine=engine, raw=raw)
    expected = Series([1, 3, 6, 10], dtype=float)
    tm.assert_almost_equal(result, expected)


@pytest.mark.parametrize("window", [2, "2s"])
def test_rolling_apply_with_pandas_objects(window):
    # 5071
    df = DataFrame(
        {
            "A": np.random.default_rng(2).standard_normal(5),
            "B": np.random.default_rng(2).integers(0, 10, size=5),
        },
        index=date_range("20130101", periods=5, freq="s"),
    )

    # we have an equal spaced timeseries index
    # so simulate removing the first period
    def f(x):
        if x.index[0] == df.index[0]:
            return np.nan
        return x.iloc[-1]

    result = df.rolling(window).apply(f, raw=False)
    expected = df.iloc[2:].reindex_like(df)
    tm.assert_frame_equal(result, expected)

    with tm.external_error_raised(AttributeError):
        df.rolling(window).apply(f, raw=True)


def test_rolling_apply(engine_and_raw, step):
    engine, raw = engine_and_raw

    expected = Series([], dtype="float64")
    result = expected.rolling(10, step=step).apply(
        lambda x: x.mean(), engine=engine, raw=raw
    )
    tm.assert_series_equal(result, expected)

    # gh-8080
    s = Series([None, None, None])
    result = s.rolling(2, min_periods=0, step=step).apply(
        lambda x: len(x), engine=engine, raw=raw
    )
    expected = Series([1.0, 2.0, 2.0])[::step]
    tm.assert_series_equal(result, expected)

    result = s.rolling(2, min_periods=0, step=step).apply(len, engine=engine, raw=raw)
    tm.assert_series_equal(result, expected)


def test_all_apply(engine_and_raw):
    engine, raw = engine_and_raw

    df = (
        DataFrame(
            {"A": date_range("20130101", periods=5, freq="s"), "B": range(5)}
        ).set_index("A")
        * 2
    )
    er = df.rolling(window=1)
    r = df.rolling(window="1s")

    result = r.apply(lambda x: 1, engine=engine, raw=raw)
    expected = er.apply(lambda x: 1, engine=engine, raw=raw)
    tm.assert_frame_equal(result, expected)


def test_ragged_apply(engine_and_raw):
    engine, raw = engine_and_raw

    df = DataFrame({"B": range(5)})
    df.index = [
        Timestamp("20130101 09:00:00"),
        Timestamp("20130101 09:00:02"),
        Timestamp("20130101 09:00:03"),
        Timestamp("20130101 09:00:05"),
        Timestamp("20130101 09:00:06"),
    ]

    f = lambda x: 1
    result = df.rolling(window="1s", min_periods=1).apply(f, engine=engine, raw=raw)
    expected = df.copy()
    expected["B"] = 1.0
    tm.assert_frame_equal(result, expected)

    result = df.rolling(window="2s", min_periods=1).apply(f, engine=engine, raw=raw)
    expected = df.copy()
    expected["B"] = 1.0
    tm.assert_frame_equal(result, expected)

    result = df.rolling(window="5s", min_periods=1).apply(f, engine=engine, raw=raw)
    expected = df.copy()
    expected["B"] = 1.0
    tm.assert_frame_equal(result, expected)


def test_invalid_engine():
    with pytest.raises(ValueError, match="engine must be either 'numba' or 'cython'"):
        Series(range(1)).rolling(1).apply(lambda x: x, engine="foo")


def test_invalid_engine_kwargs_cython():
    with pytest.raises(ValueError, match="cython engine does not accept engine_kwargs"):
        Series(range(1)).rolling(1).apply(
            lambda x: x, engine="cython", engine_kwargs={"nopython": False}
        )


def test_invalid_raw_numba():
    with pytest.raises(
        ValueError, match="raw must be `True` when using the numba engine"
    ):
        Series(range(1)).rolling(1).apply(lambda x: x, raw=False, engine="numba")


@pytest.mark.parametrize("args_kwargs", [[None, {"par": 10}], [(10,), None]])
def test_rolling_apply_args_kwargs(args_kwargs):
    # GH 33433
    def numpysum(x, par):
        return np.sum(x + par)

    df = DataFrame({"gr": [1, 1], "a": [1, 2]})

    idx = Index(["gr", "a"])
    expected = DataFrame([[11.0, 11.0], [11.0, 12.0]], columns=idx)

    result = df.rolling(1).apply(numpysum, args=args_kwargs[0], kwargs=args_kwargs[1])
    tm.assert_frame_equal(result, expected)

    midx = MultiIndex.from_tuples([(1, 0), (1, 1)], names=["gr", None])
    expected = Series([11.0, 12.0], index=midx, name="a")

    gb_rolling = df.groupby("gr")["a"].rolling(1)

    result = gb_rolling.apply(numpysum, args=args_kwargs[0], kwargs=args_kwargs[1])
    tm.assert_series_equal(result, expected)


def test_nans(raw):
    obj = Series(np.random.default_rng(2).standard_normal(50))
    obj[:10] = np.nan
    obj[-10:] = np.nan

    result = obj.rolling(50, min_periods=30).apply(f, raw=raw)
    tm.assert_almost_equal(result.iloc[-1], np.mean(obj[10:-10]))

    # min_periods is working correctly
    result = obj.rolling(20, min_periods=15).apply(f, raw=raw)
    assert isna(result.iloc[23])
    assert not isna(result.iloc[24])

    assert not isna(result.iloc[-6])
    assert isna(result.iloc[-5])

    obj2 = Series(np.random.default_rng(2).standard_normal(20))
    result = obj2.rolling(10, min_periods=5).apply(f, raw=raw)
    assert isna(result.iloc[3])
    assert notna(result.iloc[4])

    result0 = obj.rolling(20, min_periods=0).apply(f, raw=raw)
    result1 = obj.rolling(20, min_periods=1).apply(f, raw=raw)
    tm.assert_almost_equal(result0, result1)


def test_center(raw):
    obj = Series(np.random.default_rng(2).standard_normal(50))
    obj[:10] = np.nan
    obj[-10:] = np.nan

    result = obj.rolling(20, min_periods=15, center=True).apply(f, raw=raw)
    expected = (
        concat([obj, Series([np.nan] * 9)])
        .rolling(20, min_periods=15)
        .apply(f, raw=raw)
        .iloc[9:]
        .reset_index(drop=True)
    )
    tm.assert_series_equal(result, expected)


def test_series(raw, series):
    result = series.rolling(50).apply(f, raw=raw)
    assert isinstance(result, Series)
    tm.assert_almost_equal(result.iloc[-1], np.mean(series[-50:]))


def test_frame(raw, frame):
    result = frame.rolling(50).apply(f, raw=raw)
    assert isinstance(result, DataFrame)
    tm.assert_series_equal(
        result.iloc[-1, :],
        frame.iloc[-50:, :].apply(np.mean, axis=0, raw=raw),
        check_names=False,
    )


def test_time_rule_series(raw, series):
    win = 25
    minp = 10
    ser = series[::2].resample("B").mean()
    series_result = ser.rolling(window=win, min_periods=minp).apply(f, raw=raw)
    last_date = series_result.index[-1]
    prev_date = last_date - 24 * offsets.BDay()

    trunc_series = series[::2].truncate(prev_date, last_date)
    tm.assert_almost_equal(series_result.iloc[-1], np.mean(trunc_series))


def test_time_rule_frame(raw, frame):
    win = 25
    minp = 10
    frm = frame[::2].resample("B").mean()
    frame_result = frm.rolling(window=win, min_periods=minp).apply(f, raw=raw)
    last_date = frame_result.index[-1]
    prev_date = last_date - 24 * offsets.BDay()

    trunc_frame = frame[::2].truncate(prev_date, last_date)
    tm.assert_series_equal(
        frame_result.xs(last_date),
        trunc_frame.apply(np.mean, raw=raw),
        check_names=False,
    )


@pytest.mark.parametrize("minp", [0, 99, 100])
def test_min_periods(raw, series, minp, step):
    result = series.rolling(len(series) + 1, min_periods=minp, step=step).apply(
        f, raw=raw
    )
    expected = series.rolling(len(series), min_periods=minp, step=step).apply(
        f, raw=raw
    )
    nan_mask = isna(result)
    tm.assert_series_equal(nan_mask, isna(expected))

    nan_mask = ~nan_mask
    tm.assert_almost_equal(result[nan_mask], expected[nan_mask])


def test_center_reindex_series(raw, series):
    # shifter index
    s = [f"x{x:d}" for x in range(12)]
    minp = 10

    series_xp = (
        series.reindex(list(series.index) + s)
        .rolling(window=25, min_periods=minp)
        .apply(f, raw=raw)
        .shift(-12)
        .reindex(series.index)
    )
    series_rs = series.rolling(window=25, min_periods=minp, center=True).apply(
        f, raw=raw
    )
    tm.assert_series_equal(series_xp, series_rs)


def test_center_reindex_frame(raw):
    # shifter index
    frame = DataFrame(range(100), index=date_range("2020-01-01", freq="D", periods=100))
    s = [f"x{x:d}" for x in range(12)]
    minp = 10

    frame_xp = (
        frame.reindex(list(frame.index) + s)
        .rolling(window=25, min_periods=minp)
        .apply(f, raw=raw)
        .shift(-12)
        .reindex(frame.index)
    )
    frame_rs = frame.rolling(window=25, min_periods=minp, center=True).apply(f, raw=raw)
    tm.assert_frame_equal(frame_xp, frame_rs)


def test_axis1(raw):
    # GH 45912
    df = DataFrame([1, 2])
    msg = "Support for axis=1 in DataFrame.rolling is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = df.rolling(window=1, axis=1).apply(np.sum, raw=raw)
    expected = DataFrame([1.0, 2.0])
    tm.assert_frame_equal(result, expected)
