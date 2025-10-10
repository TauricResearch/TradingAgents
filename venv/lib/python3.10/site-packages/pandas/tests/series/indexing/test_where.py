import numpy as np
import pytest

from pandas.core.dtypes.common import is_integer

import pandas as pd
from pandas import (
    Series,
    Timestamp,
    date_range,
    isna,
)
import pandas._testing as tm


def test_where_unsafe_int(any_signed_int_numpy_dtype):
    s = Series(np.arange(10), dtype=any_signed_int_numpy_dtype)
    mask = s < 5

    s[mask] = range(2, 7)
    expected = Series(
        list(range(2, 7)) + list(range(5, 10)),
        dtype=any_signed_int_numpy_dtype,
    )

    tm.assert_series_equal(s, expected)


def test_where_unsafe_float(float_numpy_dtype):
    s = Series(np.arange(10), dtype=float_numpy_dtype)
    mask = s < 5

    s[mask] = range(2, 7)
    data = list(range(2, 7)) + list(range(5, 10))
    expected = Series(data, dtype=float_numpy_dtype)

    tm.assert_series_equal(s, expected)


@pytest.mark.parametrize(
    "dtype,expected_dtype",
    [
        (np.int8, np.float64),
        (np.int16, np.float64),
        (np.int32, np.float64),
        (np.int64, np.float64),
        (np.float32, np.float32),
        (np.float64, np.float64),
    ],
)
def test_where_unsafe_upcast(dtype, expected_dtype):
    # see gh-9743
    s = Series(np.arange(10), dtype=dtype)
    values = [2.5, 3.5, 4.5, 5.5, 6.5]
    mask = s < 5
    expected = Series(values + list(range(5, 10)), dtype=expected_dtype)
    warn = (
        None
        if np.dtype(dtype).kind == np.dtype(expected_dtype).kind == "f"
        else FutureWarning
    )
    with tm.assert_produces_warning(warn, match="incompatible dtype"):
        s[mask] = values
    tm.assert_series_equal(s, expected)


def test_where_unsafe():
    # see gh-9731
    s = Series(np.arange(10), dtype="int64")
    values = [2.5, 3.5, 4.5, 5.5]

    mask = s > 5
    expected = Series(list(range(6)) + values, dtype="float64")

    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        s[mask] = values
    tm.assert_series_equal(s, expected)

    # see gh-3235
    s = Series(np.arange(10), dtype="int64")
    mask = s < 5
    s[mask] = range(2, 7)
    expected = Series(list(range(2, 7)) + list(range(5, 10)), dtype="int64")
    tm.assert_series_equal(s, expected)
    assert s.dtype == expected.dtype

    s = Series(np.arange(10), dtype="int64")
    mask = s > 5
    s[mask] = [0] * 4
    expected = Series([0, 1, 2, 3, 4, 5] + [0] * 4, dtype="int64")
    tm.assert_series_equal(s, expected)

    s = Series(np.arange(10))
    mask = s > 5

    msg = "cannot set using a list-like indexer with a different length than the value"
    with pytest.raises(ValueError, match=msg):
        s[mask] = [5, 4, 3, 2, 1]

    with pytest.raises(ValueError, match=msg):
        s[mask] = [0] * 5

    # dtype changes
    s = Series([1, 2, 3, 4])
    result = s.where(s > 2, np.nan)
    expected = Series([np.nan, np.nan, 3, 4])
    tm.assert_series_equal(result, expected)

    # GH 4667
    # setting with None changes dtype
    s = Series(range(10)).astype(float)
    s[8] = None
    result = s[8]
    assert isna(result)

    s = Series(range(10)).astype(float)
    s[s > 8] = None
    result = s[isna(s)]
    expected = Series(np.nan, index=[9])
    tm.assert_series_equal(result, expected)


def test_where():
    s = Series(np.random.default_rng(2).standard_normal(5))
    cond = s > 0

    rs = s.where(cond).dropna()
    rs2 = s[cond]
    tm.assert_series_equal(rs, rs2)

    rs = s.where(cond, -s)
    tm.assert_series_equal(rs, s.abs())

    rs = s.where(cond)
    assert s.shape == rs.shape
    assert rs is not s

    # test alignment
    cond = Series([True, False, False, True, False], index=s.index)
    s2 = -(s.abs())

    expected = s2[cond].reindex(s2.index[:3]).reindex(s2.index)
    rs = s2.where(cond[:3])
    tm.assert_series_equal(rs, expected)

    expected = s2.abs()
    expected.iloc[0] = s2[0]
    rs = s2.where(cond[:3], -s2)
    tm.assert_series_equal(rs, expected)


def test_where_error():
    s = Series(np.random.default_rng(2).standard_normal(5))
    cond = s > 0

    msg = "Array conditional must be same shape as self"
    with pytest.raises(ValueError, match=msg):
        s.where(1)
    with pytest.raises(ValueError, match=msg):
        s.where(cond[:3].values, -s)

    # GH 2745
    s = Series([1, 2])
    s[[True, False]] = [0, 1]
    expected = Series([0, 2])
    tm.assert_series_equal(s, expected)

    # failures
    msg = "cannot set using a list-like indexer with a different length than the value"
    with pytest.raises(ValueError, match=msg):
        s[[True, False]] = [0, 2, 3]

    with pytest.raises(ValueError, match=msg):
        s[[True, False]] = []


@pytest.mark.parametrize("klass", [list, tuple, np.array, Series])
def test_where_array_like(klass):
    # see gh-15414
    s = Series([1, 2, 3])
    cond = [False, True, True]
    expected = Series([np.nan, 2, 3])

    result = s.where(klass(cond))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "cond",
    [
        [1, 0, 1],
        Series([2, 5, 7]),
        ["True", "False", "True"],
        [Timestamp("2017-01-01"), pd.NaT, Timestamp("2017-01-02")],
    ],
)
def test_where_invalid_input(cond):
    # see gh-15414: only boolean arrays accepted
    s = Series([1, 2, 3])
    msg = "Boolean array expected for the condition"

    with pytest.raises(ValueError, match=msg):
        s.where(cond)

    msg = "Array conditional must be same shape as self"
    with pytest.raises(ValueError, match=msg):
        s.where([True])


def test_where_ndframe_align():
    msg = "Array conditional must be same shape as self"
    s = Series([1, 2, 3])

    cond = [True]
    with pytest.raises(ValueError, match=msg):
        s.where(cond)

    expected = Series([1, np.nan, np.nan])

    out = s.where(Series(cond))
    tm.assert_series_equal(out, expected)

    cond = np.array([False, True, False, True])
    with pytest.raises(ValueError, match=msg):
        s.where(cond)

    expected = Series([np.nan, 2, np.nan])

    out = s.where(Series(cond))
    tm.assert_series_equal(out, expected)


def test_where_setitem_invalid():
    # GH 2702
    # make sure correct exceptions are raised on invalid list assignment

    msg = (
        lambda x: f"cannot set using a {x} indexer with a "
        "different length than the value"
    )
    # slice
    s = Series(list("abc"), dtype=object)

    with pytest.raises(ValueError, match=msg("slice")):
        s[0:3] = list(range(27))

    s[0:3] = list(range(3))
    expected = Series([0, 1, 2])
    tm.assert_series_equal(s.astype(np.int64), expected)

    # slice with step
    s = Series(list("abcdef"), dtype=object)

    with pytest.raises(ValueError, match=msg("slice")):
        s[0:4:2] = list(range(27))

    s = Series(list("abcdef"), dtype=object)
    s[0:4:2] = list(range(2))
    expected = Series([0, "b", 1, "d", "e", "f"])
    tm.assert_series_equal(s, expected)

    # neg slices
    s = Series(list("abcdef"), dtype=object)

    with pytest.raises(ValueError, match=msg("slice")):
        s[:-1] = list(range(27))

    s[-3:-1] = list(range(2))
    expected = Series(["a", "b", "c", 0, 1, "f"])
    tm.assert_series_equal(s, expected)

    # list
    s = Series(list("abc"), dtype=object)

    with pytest.raises(ValueError, match=msg("list-like")):
        s[[0, 1, 2]] = list(range(27))

    s = Series(list("abc"), dtype=object)

    with pytest.raises(ValueError, match=msg("list-like")):
        s[[0, 1, 2]] = list(range(2))

    # scalar
    s = Series(list("abc"), dtype=object)
    s[0] = list(range(10))
    expected = Series([list(range(10)), "b", "c"])
    tm.assert_series_equal(s, expected)


@pytest.mark.parametrize("size", range(2, 6))
@pytest.mark.parametrize(
    "mask", [[True, False, False, False, False], [True, False], [False]]
)
@pytest.mark.parametrize(
    "item", [2.0, np.nan, np.finfo(float).max, np.finfo(float).min]
)
# Test numpy arrays, lists and tuples as the input to be
# broadcast
@pytest.mark.parametrize(
    "box", [lambda x: np.array([x]), lambda x: [x], lambda x: (x,)]
)
def test_broadcast(size, mask, item, box):
    # GH#8801, GH#4195
    selection = np.resize(mask, size)

    data = np.arange(size, dtype=float)

    # Construct the expected series by taking the source
    # data or item based on the selection
    expected = Series(
        [item if use_item else data[i] for i, use_item in enumerate(selection)]
    )

    s = Series(data)

    s[selection] = item
    tm.assert_series_equal(s, expected)

    s = Series(data)
    result = s.where(~selection, box(item))
    tm.assert_series_equal(result, expected)

    s = Series(data)
    result = s.mask(selection, box(item))
    tm.assert_series_equal(result, expected)


def test_where_inplace():
    s = Series(np.random.default_rng(2).standard_normal(5))
    cond = s > 0

    rs = s.copy()

    rs.where(cond, inplace=True)
    tm.assert_series_equal(rs.dropna(), s[cond])
    tm.assert_series_equal(rs, s.where(cond))

    rs = s.copy()
    rs.where(cond, -s, inplace=True)
    tm.assert_series_equal(rs, s.where(cond, -s))


def test_where_dups():
    # GH 4550
    # where crashes with dups in index
    s1 = Series(list(range(3)))
    s2 = Series(list(range(3)))
    comb = pd.concat([s1, s2])
    result = comb.where(comb < 2)
    expected = Series([0, 1, np.nan, 0, 1, np.nan], index=[0, 1, 2, 0, 1, 2])
    tm.assert_series_equal(result, expected)

    # GH 4548
    # inplace updating not working with dups
    comb[comb < 1] = 5
    expected = Series([5, 1, 2, 5, 1, 2], index=[0, 1, 2, 0, 1, 2])
    tm.assert_series_equal(comb, expected)

    comb[comb < 2] += 10
    expected = Series([5, 11, 2, 5, 11, 2], index=[0, 1, 2, 0, 1, 2])
    tm.assert_series_equal(comb, expected)


def test_where_numeric_with_string():
    # GH 9280
    s = Series([1, 2, 3])
    w = s.where(s > 1, "X")

    assert not is_integer(w[0])
    assert is_integer(w[1])
    assert is_integer(w[2])
    assert isinstance(w[0], str)
    assert w.dtype == "object"

    w = s.where(s > 1, ["X", "Y", "Z"])
    assert not is_integer(w[0])
    assert is_integer(w[1])
    assert is_integer(w[2])
    assert isinstance(w[0], str)
    assert w.dtype == "object"

    w = s.where(s > 1, np.array(["X", "Y", "Z"]))
    assert not is_integer(w[0])
    assert is_integer(w[1])
    assert is_integer(w[2])
    assert isinstance(w[0], str)
    assert w.dtype == "object"


@pytest.mark.parametrize("dtype", ["timedelta64[ns]", "datetime64[ns]"])
def test_where_datetimelike_coerce(dtype):
    ser = Series([1, 2], dtype=dtype)
    expected = Series([10, 10])
    mask = np.array([False, False])

    msg = "Downcasting behavior in Series and DataFrame methods 'where'"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        rs = ser.where(mask, [10, 10])
    tm.assert_series_equal(rs, expected)

    with tm.assert_produces_warning(FutureWarning, match=msg):
        rs = ser.where(mask, 10)
    tm.assert_series_equal(rs, expected)

    with tm.assert_produces_warning(FutureWarning, match=msg):
        rs = ser.where(mask, 10.0)
    tm.assert_series_equal(rs, expected)

    with tm.assert_produces_warning(FutureWarning, match=msg):
        rs = ser.where(mask, [10.0, 10.0])
    tm.assert_series_equal(rs, expected)

    rs = ser.where(mask, [10.0, np.nan])
    expected = Series([10, np.nan], dtype="object")
    tm.assert_series_equal(rs, expected)


def test_where_datetimetz():
    # GH 15701
    timestamps = ["2016-12-31 12:00:04+00:00", "2016-12-31 12:00:04.010000+00:00"]
    ser = Series([Timestamp(t) for t in timestamps], dtype="datetime64[ns, UTC]")
    rs = ser.where(Series([False, True]))
    expected = Series([pd.NaT, ser[1]], dtype="datetime64[ns, UTC]")
    tm.assert_series_equal(rs, expected)


def test_where_sparse():
    # GH#17198 make sure we dont get an AttributeError for sp_index
    ser = Series(pd.arrays.SparseArray([1, 2]))
    result = ser.where(ser >= 2, 0)
    expected = Series(pd.arrays.SparseArray([0, 2]))
    tm.assert_series_equal(result, expected)


def test_where_empty_series_and_empty_cond_having_non_bool_dtypes():
    # https://github.com/pandas-dev/pandas/issues/34592
    ser = Series([], dtype=float)
    result = ser.where([])
    tm.assert_series_equal(result, ser)


def test_where_categorical(frame_or_series):
    # https://github.com/pandas-dev/pandas/issues/18888
    exp = frame_or_series(
        pd.Categorical(["A", "A", "B", "B", np.nan], categories=["A", "B", "C"]),
        dtype="category",
    )
    df = frame_or_series(["A", "A", "B", "B", "C"], dtype="category")
    res = df.where(df != "C")
    tm.assert_equal(exp, res)


def test_where_datetimelike_categorical(tz_naive_fixture):
    # GH#37682
    tz = tz_naive_fixture

    dr = date_range("2001-01-01", periods=3, tz=tz)._with_freq(None)
    lvals = pd.DatetimeIndex([dr[0], dr[1], pd.NaT])
    rvals = pd.Categorical([dr[0], pd.NaT, dr[2]])

    mask = np.array([True, True, False])

    # DatetimeIndex.where
    res = lvals.where(mask, rvals)
    tm.assert_index_equal(res, dr)

    # DatetimeArray.where
    res = lvals._data._where(mask, rvals)
    tm.assert_datetime_array_equal(res, dr._data)

    # Series.where
    res = Series(lvals).where(mask, rvals)
    tm.assert_series_equal(res, Series(dr))

    # DataFrame.where
    res = pd.DataFrame(lvals).where(mask[:, None], pd.DataFrame(rvals))

    tm.assert_frame_equal(res, pd.DataFrame(dr))
