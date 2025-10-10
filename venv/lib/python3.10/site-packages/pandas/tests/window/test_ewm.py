import numpy as np
import pytest

from pandas import (
    DataFrame,
    DatetimeIndex,
    Series,
    date_range,
)
import pandas._testing as tm


def test_doc_string():
    df = DataFrame({"B": [0, 1, 2, np.nan, 4]})
    df
    df.ewm(com=0.5).mean()


def test_constructor(frame_or_series):
    c = frame_or_series(range(5)).ewm

    # valid
    c(com=0.5)
    c(span=1.5)
    c(alpha=0.5)
    c(halflife=0.75)
    c(com=0.5, span=None)
    c(alpha=0.5, com=None)
    c(halflife=0.75, alpha=None)

    # not valid: mutually exclusive
    msg = "comass, span, halflife, and alpha are mutually exclusive"
    with pytest.raises(ValueError, match=msg):
        c(com=0.5, alpha=0.5)
    with pytest.raises(ValueError, match=msg):
        c(span=1.5, halflife=0.75)
    with pytest.raises(ValueError, match=msg):
        c(alpha=0.5, span=1.5)

    # not valid: com < 0
    msg = "comass must satisfy: comass >= 0"
    with pytest.raises(ValueError, match=msg):
        c(com=-0.5)

    # not valid: span < 1
    msg = "span must satisfy: span >= 1"
    with pytest.raises(ValueError, match=msg):
        c(span=0.5)

    # not valid: halflife <= 0
    msg = "halflife must satisfy: halflife > 0"
    with pytest.raises(ValueError, match=msg):
        c(halflife=0)

    # not valid: alpha <= 0 or alpha > 1
    msg = "alpha must satisfy: 0 < alpha <= 1"
    for alpha in (-0.5, 1.5):
        with pytest.raises(ValueError, match=msg):
            c(alpha=alpha)


def test_ewma_times_not_datetime_type():
    msg = r"times must be datetime64 dtype."
    with pytest.raises(ValueError, match=msg):
        Series(range(5)).ewm(times=np.arange(5))


def test_ewma_times_not_same_length():
    msg = "times must be the same length as the object."
    with pytest.raises(ValueError, match=msg):
        Series(range(5)).ewm(times=np.arange(4).astype("datetime64[ns]"))


def test_ewma_halflife_not_correct_type():
    msg = "halflife must be a timedelta convertible object"
    with pytest.raises(ValueError, match=msg):
        Series(range(5)).ewm(halflife=1, times=np.arange(5).astype("datetime64[ns]"))


def test_ewma_halflife_without_times(halflife_with_times):
    msg = "halflife can only be a timedelta convertible argument if times is not None."
    with pytest.raises(ValueError, match=msg):
        Series(range(5)).ewm(halflife=halflife_with_times)


@pytest.mark.parametrize(
    "times",
    [
        np.arange(10).astype("datetime64[D]").astype("datetime64[ns]"),
        date_range("2000", freq="D", periods=10),
        date_range("2000", freq="D", periods=10).tz_localize("UTC"),
    ],
)
@pytest.mark.parametrize("min_periods", [0, 2])
def test_ewma_with_times_equal_spacing(halflife_with_times, times, min_periods):
    halflife = halflife_with_times
    data = np.arange(10.0)
    data[::2] = np.nan
    df = DataFrame({"A": data})
    result = df.ewm(halflife=halflife, min_periods=min_periods, times=times).mean()
    expected = df.ewm(halflife=1.0, min_periods=min_periods).mean()
    tm.assert_frame_equal(result, expected)


def test_ewma_with_times_variable_spacing(tz_aware_fixture, unit):
    tz = tz_aware_fixture
    halflife = "23 days"
    times = (
        DatetimeIndex(["2020-01-01", "2020-01-10T00:04:05", "2020-02-23T05:00:23"])
        .tz_localize(tz)
        .as_unit(unit)
    )
    data = np.arange(3)
    df = DataFrame(data)
    result = df.ewm(halflife=halflife, times=times).mean()
    expected = DataFrame([0.0, 0.5674161888241773, 1.545239952073459])
    tm.assert_frame_equal(result, expected)


def test_ewm_with_nat_raises(halflife_with_times):
    # GH#38535
    ser = Series(range(1))
    times = DatetimeIndex(["NaT"])
    with pytest.raises(ValueError, match="Cannot convert NaT values to integer"):
        ser.ewm(com=0.1, halflife=halflife_with_times, times=times)


def test_ewm_with_times_getitem(halflife_with_times):
    # GH 40164
    halflife = halflife_with_times
    data = np.arange(10.0)
    data[::2] = np.nan
    times = date_range("2000", freq="D", periods=10)
    df = DataFrame({"A": data, "B": data})
    result = df.ewm(halflife=halflife, times=times)["A"].mean()
    expected = df.ewm(halflife=1.0)["A"].mean()
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("arg", ["com", "halflife", "span", "alpha"])
def test_ewm_getitem_attributes_retained(arg, adjust, ignore_na):
    # GH 40164
    kwargs = {arg: 1, "adjust": adjust, "ignore_na": ignore_na}
    ewm = DataFrame({"A": range(1), "B": range(1)}).ewm(**kwargs)
    expected = {attr: getattr(ewm, attr) for attr in ewm._attributes}
    ewm_slice = ewm["A"]
    result = {attr: getattr(ewm, attr) for attr in ewm_slice._attributes}
    assert result == expected


def test_ewma_times_adjust_false_raises():
    # GH 40098
    with pytest.raises(
        NotImplementedError, match="times is not supported with adjust=False."
    ):
        Series(range(1)).ewm(
            0.1, adjust=False, times=date_range("2000", freq="D", periods=1)
        )


@pytest.mark.parametrize(
    "func, expected",
    [
        [
            "mean",
            DataFrame(
                {
                    0: range(5),
                    1: range(4, 9),
                    2: [7.428571, 9, 10.571429, 12.142857, 13.714286],
                },
                dtype=float,
            ),
        ],
        [
            "std",
            DataFrame(
                {
                    0: [np.nan] * 5,
                    1: [4.242641] * 5,
                    2: [4.6291, 5.196152, 5.781745, 6.380775, 6.989788],
                }
            ),
        ],
        [
            "var",
            DataFrame(
                {
                    0: [np.nan] * 5,
                    1: [18.0] * 5,
                    2: [21.428571, 27, 33.428571, 40.714286, 48.857143],
                }
            ),
        ],
    ],
)
def test_float_dtype_ewma(func, expected, float_numpy_dtype):
    # GH#42452

    df = DataFrame(
        {0: range(5), 1: range(6, 11), 2: range(10, 20, 2)}, dtype=float_numpy_dtype
    )
    msg = "Support for axis=1 in DataFrame.ewm is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        e = df.ewm(alpha=0.5, axis=1)
    result = getattr(e, func)()

    tm.assert_frame_equal(result, expected)


def test_times_string_col_raises():
    # GH 43265
    df = DataFrame(
        {"A": np.arange(10.0), "time_col": date_range("2000", freq="D", periods=10)}
    )
    with pytest.raises(ValueError, match="times must be datetime64"):
        df.ewm(halflife="1 day", min_periods=0, times="time_col")


def test_ewm_sum_adjust_false_notimplemented():
    data = Series(range(1)).ewm(com=1, adjust=False)
    with pytest.raises(NotImplementedError, match="sum is not"):
        data.sum()


@pytest.mark.parametrize(
    "expected_data, ignore",
    [[[10.0, 5.0, 2.5, 11.25], False], [[10.0, 5.0, 5.0, 12.5], True]],
)
def test_ewm_sum(expected_data, ignore):
    # xref from Numbagg tests
    # https://github.com/numbagg/numbagg/blob/v0.2.1/numbagg/test/test_moving.py#L50
    data = Series([10, 0, np.nan, 10])
    result = data.ewm(alpha=0.5, ignore_na=ignore).sum()
    expected = Series(expected_data)
    tm.assert_series_equal(result, expected)


def test_ewma_adjust():
    vals = Series(np.zeros(1000))
    vals[5] = 1
    result = vals.ewm(span=100, adjust=False).mean().sum()
    assert np.abs(result - 1) < 1e-2


def test_ewma_cases(adjust, ignore_na):
    # try adjust/ignore_na args matrix

    s = Series([1.0, 2.0, 4.0, 8.0])

    if adjust:
        expected = Series([1.0, 1.6, 2.736842, 4.923077])
    else:
        expected = Series([1.0, 1.333333, 2.222222, 4.148148])

    result = s.ewm(com=2.0, adjust=adjust, ignore_na=ignore_na).mean()
    tm.assert_series_equal(result, expected)


def test_ewma_nan_handling():
    s = Series([1.0] + [np.nan] * 5 + [1.0])
    result = s.ewm(com=5).mean()
    tm.assert_series_equal(result, Series([1.0] * len(s)))

    s = Series([np.nan] * 2 + [1.0] + [np.nan] * 2 + [1.0])
    result = s.ewm(com=5).mean()
    tm.assert_series_equal(result, Series([np.nan] * 2 + [1.0] * 4))


@pytest.mark.parametrize(
    "s, adjust, ignore_na, w",
    [
        (
            Series([np.nan, 1.0, 101.0]),
            True,
            False,
            [np.nan, (1.0 - (1.0 / (1.0 + 2.0))), 1.0],
        ),
        (
            Series([np.nan, 1.0, 101.0]),
            True,
            True,
            [np.nan, (1.0 - (1.0 / (1.0 + 2.0))), 1.0],
        ),
        (
            Series([np.nan, 1.0, 101.0]),
            False,
            False,
            [np.nan, (1.0 - (1.0 / (1.0 + 2.0))), (1.0 / (1.0 + 2.0))],
        ),
        (
            Series([np.nan, 1.0, 101.0]),
            False,
            True,
            [np.nan, (1.0 - (1.0 / (1.0 + 2.0))), (1.0 / (1.0 + 2.0))],
        ),
        (
            Series([1.0, np.nan, 101.0]),
            True,
            False,
            [(1.0 - (1.0 / (1.0 + 2.0))) ** 2, np.nan, 1.0],
        ),
        (
            Series([1.0, np.nan, 101.0]),
            True,
            True,
            [(1.0 - (1.0 / (1.0 + 2.0))), np.nan, 1.0],
        ),
        (
            Series([1.0, np.nan, 101.0]),
            False,
            False,
            [(1.0 - (1.0 / (1.0 + 2.0))) ** 2, np.nan, (1.0 / (1.0 + 2.0))],
        ),
        (
            Series([1.0, np.nan, 101.0]),
            False,
            True,
            [(1.0 - (1.0 / (1.0 + 2.0))), np.nan, (1.0 / (1.0 + 2.0))],
        ),
        (
            Series([np.nan, 1.0, np.nan, np.nan, 101.0, np.nan]),
            True,
            False,
            [np.nan, (1.0 - (1.0 / (1.0 + 2.0))) ** 3, np.nan, np.nan, 1.0, np.nan],
        ),
        (
            Series([np.nan, 1.0, np.nan, np.nan, 101.0, np.nan]),
            True,
            True,
            [np.nan, (1.0 - (1.0 / (1.0 + 2.0))), np.nan, np.nan, 1.0, np.nan],
        ),
        (
            Series([np.nan, 1.0, np.nan, np.nan, 101.0, np.nan]),
            False,
            False,
            [
                np.nan,
                (1.0 - (1.0 / (1.0 + 2.0))) ** 3,
                np.nan,
                np.nan,
                (1.0 / (1.0 + 2.0)),
                np.nan,
            ],
        ),
        (
            Series([np.nan, 1.0, np.nan, np.nan, 101.0, np.nan]),
            False,
            True,
            [
                np.nan,
                (1.0 - (1.0 / (1.0 + 2.0))),
                np.nan,
                np.nan,
                (1.0 / (1.0 + 2.0)),
                np.nan,
            ],
        ),
        (
            Series([1.0, np.nan, 101.0, 50.0]),
            True,
            False,
            [
                (1.0 - (1.0 / (1.0 + 2.0))) ** 3,
                np.nan,
                (1.0 - (1.0 / (1.0 + 2.0))),
                1.0,
            ],
        ),
        (
            Series([1.0, np.nan, 101.0, 50.0]),
            True,
            True,
            [
                (1.0 - (1.0 / (1.0 + 2.0))) ** 2,
                np.nan,
                (1.0 - (1.0 / (1.0 + 2.0))),
                1.0,
            ],
        ),
        (
            Series([1.0, np.nan, 101.0, 50.0]),
            False,
            False,
            [
                (1.0 - (1.0 / (1.0 + 2.0))) ** 3,
                np.nan,
                (1.0 - (1.0 / (1.0 + 2.0))) * (1.0 / (1.0 + 2.0)),
                (1.0 / (1.0 + 2.0))
                * ((1.0 - (1.0 / (1.0 + 2.0))) ** 2 + (1.0 / (1.0 + 2.0))),
            ],
        ),
        (
            Series([1.0, np.nan, 101.0, 50.0]),
            False,
            True,
            [
                (1.0 - (1.0 / (1.0 + 2.0))) ** 2,
                np.nan,
                (1.0 - (1.0 / (1.0 + 2.0))) * (1.0 / (1.0 + 2.0)),
                (1.0 / (1.0 + 2.0)),
            ],
        ),
    ],
)
def test_ewma_nan_handling_cases(s, adjust, ignore_na, w):
    # GH 7603
    expected = (s.multiply(w).cumsum() / Series(w).cumsum()).ffill()
    result = s.ewm(com=2.0, adjust=adjust, ignore_na=ignore_na).mean()

    tm.assert_series_equal(result, expected)
    if ignore_na is False:
        # check that ignore_na defaults to False
        result = s.ewm(com=2.0, adjust=adjust).mean()
        tm.assert_series_equal(result, expected)


def test_ewm_alpha():
    # GH 10789
    arr = np.random.default_rng(2).standard_normal(100)
    locs = np.arange(20, 40)
    arr[locs] = np.nan

    s = Series(arr)
    a = s.ewm(alpha=0.61722699889169674).mean()
    b = s.ewm(com=0.62014947789973052).mean()
    c = s.ewm(span=2.240298955799461).mean()
    d = s.ewm(halflife=0.721792864318).mean()
    tm.assert_series_equal(a, b)
    tm.assert_series_equal(a, c)
    tm.assert_series_equal(a, d)


def test_ewm_domain_checks():
    # GH 12492
    arr = np.random.default_rng(2).standard_normal(100)
    locs = np.arange(20, 40)
    arr[locs] = np.nan

    s = Series(arr)
    msg = "comass must satisfy: comass >= 0"
    with pytest.raises(ValueError, match=msg):
        s.ewm(com=-0.1)
    s.ewm(com=0.0)
    s.ewm(com=0.1)

    msg = "span must satisfy: span >= 1"
    with pytest.raises(ValueError, match=msg):
        s.ewm(span=-0.1)
    with pytest.raises(ValueError, match=msg):
        s.ewm(span=0.0)
    with pytest.raises(ValueError, match=msg):
        s.ewm(span=0.9)
    s.ewm(span=1.0)
    s.ewm(span=1.1)

    msg = "halflife must satisfy: halflife > 0"
    with pytest.raises(ValueError, match=msg):
        s.ewm(halflife=-0.1)
    with pytest.raises(ValueError, match=msg):
        s.ewm(halflife=0.0)
    s.ewm(halflife=0.1)

    msg = "alpha must satisfy: 0 < alpha <= 1"
    with pytest.raises(ValueError, match=msg):
        s.ewm(alpha=-0.1)
    with pytest.raises(ValueError, match=msg):
        s.ewm(alpha=0.0)
    s.ewm(alpha=0.1)
    s.ewm(alpha=1.0)
    with pytest.raises(ValueError, match=msg):
        s.ewm(alpha=1.1)


@pytest.mark.parametrize("method", ["mean", "std", "var"])
def test_ew_empty_series(method):
    vals = Series([], dtype=np.float64)

    ewm = vals.ewm(3)
    result = getattr(ewm, method)()
    tm.assert_almost_equal(result, vals)


@pytest.mark.parametrize("min_periods", [0, 1])
@pytest.mark.parametrize("name", ["mean", "var", "std"])
def test_ew_min_periods(min_periods, name):
    # excluding NaNs correctly
    arr = np.random.default_rng(2).standard_normal(50)
    arr[:10] = np.nan
    arr[-10:] = np.nan
    s = Series(arr)

    # check min_periods
    # GH 7898
    result = getattr(s.ewm(com=50, min_periods=2), name)()
    assert result[:11].isna().all()
    assert not result[11:].isna().any()

    result = getattr(s.ewm(com=50, min_periods=min_periods), name)()
    if name == "mean":
        assert result[:10].isna().all()
        assert not result[10:].isna().any()
    else:
        # ewm.std, ewm.var (with bias=False) require at least
        # two values
        assert result[:11].isna().all()
        assert not result[11:].isna().any()

    # check series of length 0
    result = getattr(Series(dtype=object).ewm(com=50, min_periods=min_periods), name)()
    tm.assert_series_equal(result, Series(dtype="float64"))

    # check series of length 1
    result = getattr(Series([1.0]).ewm(50, min_periods=min_periods), name)()
    if name == "mean":
        tm.assert_series_equal(result, Series([1.0]))
    else:
        # ewm.std, ewm.var with bias=False require at least
        # two values
        tm.assert_series_equal(result, Series([np.nan]))

    # pass in ints
    result2 = getattr(Series(np.arange(50)).ewm(span=10), name)()
    assert result2.dtype == np.float64


@pytest.mark.parametrize("name", ["cov", "corr"])
def test_ewm_corr_cov(name):
    A = Series(np.random.default_rng(2).standard_normal(50), index=range(50))
    B = A[2:] + np.random.default_rng(2).standard_normal(48)

    A[:10] = np.nan
    B.iloc[-10:] = np.nan

    result = getattr(A.ewm(com=20, min_periods=5), name)(B)
    assert np.isnan(result.values[:14]).all()
    assert not np.isnan(result.values[14:]).any()


@pytest.mark.parametrize("min_periods", [0, 1, 2])
@pytest.mark.parametrize("name", ["cov", "corr"])
def test_ewm_corr_cov_min_periods(name, min_periods):
    # GH 7898
    A = Series(np.random.default_rng(2).standard_normal(50), index=range(50))
    B = A[2:] + np.random.default_rng(2).standard_normal(48)

    A[:10] = np.nan
    B.iloc[-10:] = np.nan

    result = getattr(A.ewm(com=20, min_periods=min_periods), name)(B)
    # binary functions (ewmcov, ewmcorr) with bias=False require at
    # least two values
    assert np.isnan(result.values[:11]).all()
    assert not np.isnan(result.values[11:]).any()

    # check series of length 0
    empty = Series([], dtype=np.float64)
    result = getattr(empty.ewm(com=50, min_periods=min_periods), name)(empty)
    tm.assert_series_equal(result, empty)

    # check series of length 1
    result = getattr(Series([1.0]).ewm(com=50, min_periods=min_periods), name)(
        Series([1.0])
    )
    tm.assert_series_equal(result, Series([np.nan]))


@pytest.mark.parametrize("name", ["cov", "corr"])
def test_different_input_array_raise_exception(name):
    A = Series(np.random.default_rng(2).standard_normal(50), index=range(50))
    A[:10] = np.nan

    msg = "other must be a DataFrame or Series"
    # exception raised is Exception
    with pytest.raises(ValueError, match=msg):
        getattr(A.ewm(com=20, min_periods=5), name)(
            np.random.default_rng(2).standard_normal(50)
        )


@pytest.mark.parametrize("name", ["var", "std", "mean"])
def test_ewma_series(series, name):
    series_result = getattr(series.ewm(com=10), name)()
    assert isinstance(series_result, Series)


@pytest.mark.parametrize("name", ["var", "std", "mean"])
def test_ewma_frame(frame, name):
    frame_result = getattr(frame.ewm(com=10), name)()
    assert isinstance(frame_result, DataFrame)


def test_ewma_span_com_args(series):
    A = series.ewm(com=9.5).mean()
    B = series.ewm(span=20).mean()
    tm.assert_almost_equal(A, B)
    msg = "comass, span, halflife, and alpha are mutually exclusive"
    with pytest.raises(ValueError, match=msg):
        series.ewm(com=9.5, span=20)

    msg = "Must pass one of comass, span, halflife, or alpha"
    with pytest.raises(ValueError, match=msg):
        series.ewm().mean()


def test_ewma_halflife_arg(series):
    A = series.ewm(com=13.932726172912965).mean()
    B = series.ewm(halflife=10.0).mean()
    tm.assert_almost_equal(A, B)
    msg = "comass, span, halflife, and alpha are mutually exclusive"
    with pytest.raises(ValueError, match=msg):
        series.ewm(span=20, halflife=50)
    with pytest.raises(ValueError, match=msg):
        series.ewm(com=9.5, halflife=50)
    with pytest.raises(ValueError, match=msg):
        series.ewm(com=9.5, span=20, halflife=50)
    msg = "Must pass one of comass, span, halflife, or alpha"
    with pytest.raises(ValueError, match=msg):
        series.ewm()


def test_ewm_alpha_arg(series):
    # GH 10789
    s = series
    msg = "Must pass one of comass, span, halflife, or alpha"
    with pytest.raises(ValueError, match=msg):
        s.ewm()

    msg = "comass, span, halflife, and alpha are mutually exclusive"
    with pytest.raises(ValueError, match=msg):
        s.ewm(com=10.0, alpha=0.5)
    with pytest.raises(ValueError, match=msg):
        s.ewm(span=10.0, alpha=0.5)
    with pytest.raises(ValueError, match=msg):
        s.ewm(halflife=10.0, alpha=0.5)


@pytest.mark.parametrize("func", ["cov", "corr"])
def test_ewm_pairwise_cov_corr(func, frame):
    result = getattr(frame.ewm(span=10, min_periods=5), func)()
    result = result.loc[(slice(None), 1), 5]
    result.index = result.index.droplevel(1)
    expected = getattr(frame[1].ewm(span=10, min_periods=5), func)(frame[5])
    tm.assert_series_equal(result, expected, check_names=False)


def test_numeric_only_frame(arithmetic_win_operators, numeric_only):
    # GH#46560
    kernel = arithmetic_win_operators
    df = DataFrame({"a": [1], "b": 2, "c": 3})
    df["c"] = df["c"].astype(object)
    ewm = df.ewm(span=2, min_periods=1)
    op = getattr(ewm, kernel, None)
    if op is not None:
        result = op(numeric_only=numeric_only)

        columns = ["a", "b"] if numeric_only else ["a", "b", "c"]
        expected = df[columns].agg([kernel]).reset_index(drop=True).astype(float)
        assert list(expected.columns) == columns

        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("kernel", ["corr", "cov"])
@pytest.mark.parametrize("use_arg", [True, False])
def test_numeric_only_corr_cov_frame(kernel, numeric_only, use_arg):
    # GH#46560
    df = DataFrame({"a": [1, 2, 3], "b": 2, "c": 3})
    df["c"] = df["c"].astype(object)
    arg = (df,) if use_arg else ()
    ewm = df.ewm(span=2, min_periods=1)
    op = getattr(ewm, kernel)
    result = op(*arg, numeric_only=numeric_only)

    # Compare result to op using float dtypes, dropping c when numeric_only is True
    columns = ["a", "b"] if numeric_only else ["a", "b", "c"]
    df2 = df[columns].astype(float)
    arg2 = (df2,) if use_arg else ()
    ewm2 = df2.ewm(span=2, min_periods=1)
    op2 = getattr(ewm2, kernel)
    expected = op2(*arg2, numeric_only=numeric_only)

    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("dtype", [int, object])
def test_numeric_only_series(arithmetic_win_operators, numeric_only, dtype):
    # GH#46560
    kernel = arithmetic_win_operators
    ser = Series([1], dtype=dtype)
    ewm = ser.ewm(span=2, min_periods=1)
    op = getattr(ewm, kernel, None)
    if op is None:
        # Nothing to test
        pytest.skip("No op to test")
    if numeric_only and dtype is object:
        msg = f"ExponentialMovingWindow.{kernel} does not implement numeric_only"
        with pytest.raises(NotImplementedError, match=msg):
            op(numeric_only=numeric_only)
    else:
        result = op(numeric_only=numeric_only)
        expected = ser.agg([kernel]).reset_index(drop=True).astype(float)
        tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("kernel", ["corr", "cov"])
@pytest.mark.parametrize("use_arg", [True, False])
@pytest.mark.parametrize("dtype", [int, object])
def test_numeric_only_corr_cov_series(kernel, use_arg, numeric_only, dtype):
    # GH#46560
    ser = Series([1, 2, 3], dtype=dtype)
    arg = (ser,) if use_arg else ()
    ewm = ser.ewm(span=2, min_periods=1)
    op = getattr(ewm, kernel)
    if numeric_only and dtype is object:
        msg = f"ExponentialMovingWindow.{kernel} does not implement numeric_only"
        with pytest.raises(NotImplementedError, match=msg):
            op(*arg, numeric_only=numeric_only)
    else:
        result = op(*arg, numeric_only=numeric_only)

        ser2 = ser.astype(float)
        arg2 = (ser2,) if use_arg else ()
        ewm2 = ser2.ewm(span=2, min_periods=1)
        op2 = getattr(ewm2, kernel)
        expected = op2(*arg2, numeric_only=numeric_only)
        tm.assert_series_equal(result, expected)
