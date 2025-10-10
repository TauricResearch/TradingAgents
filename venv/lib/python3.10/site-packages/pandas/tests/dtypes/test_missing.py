from contextlib import nullcontext
from datetime import datetime
from decimal import Decimal

import numpy as np
import pytest

from pandas._config import config as cf

from pandas._libs import missing as libmissing
from pandas._libs.tslibs import iNaT
from pandas.compat.numpy import np_version_gte1p25

from pandas.core.dtypes.common import (
    is_float,
    is_scalar,
    pandas_dtype,
)
from pandas.core.dtypes.dtypes import (
    CategoricalDtype,
    DatetimeTZDtype,
    IntervalDtype,
    PeriodDtype,
)
from pandas.core.dtypes.missing import (
    array_equivalent,
    is_valid_na_for_dtype,
    isna,
    isnull,
    na_value_for_dtype,
    notna,
    notnull,
)

import pandas as pd
from pandas import (
    DatetimeIndex,
    Index,
    NaT,
    Series,
    TimedeltaIndex,
    date_range,
    period_range,
)
import pandas._testing as tm

fix_now = pd.Timestamp("2021-01-01")
fix_utcnow = pd.Timestamp("2021-01-01", tz="UTC")


@pytest.mark.parametrize("notna_f", [notna, notnull])
def test_notna_notnull(notna_f):
    assert notna_f(1.0)
    assert not notna_f(None)
    assert not notna_f(np.nan)

    msg = "use_inf_as_na option is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        with cf.option_context("mode.use_inf_as_na", False):
            assert notna_f(np.inf)
            assert notna_f(-np.inf)

            arr = np.array([1.5, np.inf, 3.5, -np.inf])
            result = notna_f(arr)
            assert result.all()

    with tm.assert_produces_warning(FutureWarning, match=msg):
        with cf.option_context("mode.use_inf_as_na", True):
            assert not notna_f(np.inf)
            assert not notna_f(-np.inf)

            arr = np.array([1.5, np.inf, 3.5, -np.inf])
            result = notna_f(arr)
            assert result.sum() == 2


@pytest.mark.parametrize("null_func", [notna, notnull, isna, isnull])
@pytest.mark.parametrize(
    "ser",
    [
        Series(
            [str(i) for i in range(5)],
            index=Index([str(i) for i in range(5)], dtype=object),
            dtype=object,
        ),
        Series(range(5), date_range("2020-01-01", periods=5)),
        Series(range(5), period_range("2020-01-01", periods=5)),
    ],
)
def test_null_check_is_series(null_func, ser):
    msg = "use_inf_as_na option is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        with cf.option_context("mode.use_inf_as_na", False):
            assert isinstance(null_func(ser), Series)


class TestIsNA:
    def test_0d_array(self):
        assert isna(np.array(np.nan))
        assert not isna(np.array(0.0))
        assert not isna(np.array(0))
        # test object dtype
        assert isna(np.array(np.nan, dtype=object))
        assert not isna(np.array(0.0, dtype=object))
        assert not isna(np.array(0, dtype=object))

    @pytest.mark.parametrize("shape", [(4, 0), (4,)])
    def test_empty_object(self, shape):
        arr = np.empty(shape=shape, dtype=object)
        result = isna(arr)
        expected = np.ones(shape=shape, dtype=bool)
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize("isna_f", [isna, isnull])
    def test_isna_isnull(self, isna_f):
        assert not isna_f(1.0)
        assert isna_f(None)
        assert isna_f(np.nan)
        assert float("nan")
        assert not isna_f(np.inf)
        assert not isna_f(-np.inf)

        # type
        assert not isna_f(type(Series(dtype=object)))
        assert not isna_f(type(Series(dtype=np.float64)))
        assert not isna_f(type(pd.DataFrame()))

    @pytest.mark.parametrize("isna_f", [isna, isnull])
    @pytest.mark.parametrize(
        "data",
        [
            np.arange(4, dtype=float),
            [0.0, 1.0, 0.0, 1.0],
            Series(list("abcd")),
            date_range("2020-01-01", periods=4),
        ],
    )
    @pytest.mark.parametrize(
        "index",
        [
            date_range("2020-01-01", periods=4),
            range(4),
            period_range("2020-01-01", periods=4),
        ],
    )
    def test_isna_isnull_frame(self, isna_f, data, index):
        # frame
        df = pd.DataFrame(data, index=index)
        result = isna_f(df)
        expected = df.apply(isna_f)
        tm.assert_frame_equal(result, expected)

    def test_isna_lists(self):
        result = isna([[False]])
        exp = np.array([[False]])
        tm.assert_numpy_array_equal(result, exp)

        result = isna([[1], [2]])
        exp = np.array([[False], [False]])
        tm.assert_numpy_array_equal(result, exp)

        # list of strings / unicode
        result = isna(["foo", "bar"])
        exp = np.array([False, False])
        tm.assert_numpy_array_equal(result, exp)

        result = isna(["foo", "bar"])
        exp = np.array([False, False])
        tm.assert_numpy_array_equal(result, exp)

        # GH20675
        result = isna([np.nan, "world"])
        exp = np.array([True, False])
        tm.assert_numpy_array_equal(result, exp)

    def test_isna_nat(self):
        result = isna([NaT])
        exp = np.array([True])
        tm.assert_numpy_array_equal(result, exp)

        result = isna(np.array([NaT], dtype=object))
        exp = np.array([True])
        tm.assert_numpy_array_equal(result, exp)

    def test_isna_numpy_nat(self):
        arr = np.array(
            [
                NaT,
                np.datetime64("NaT"),
                np.timedelta64("NaT"),
                np.datetime64("NaT", "s"),
            ]
        )
        result = isna(arr)
        expected = np.array([True] * 4)
        tm.assert_numpy_array_equal(result, expected)

    def test_isna_datetime(self):
        assert not isna(datetime.now())
        assert notna(datetime.now())

        idx = date_range("1/1/1990", periods=20)
        exp = np.ones(len(idx), dtype=bool)
        tm.assert_numpy_array_equal(notna(idx), exp)

        idx = np.asarray(idx)
        idx[0] = iNaT
        idx = DatetimeIndex(idx)
        mask = isna(idx)
        assert mask[0]
        exp = np.array([True] + [False] * (len(idx) - 1), dtype=bool)
        tm.assert_numpy_array_equal(mask, exp)

        # GH 9129
        pidx = idx.to_period(freq="M")
        mask = isna(pidx)
        assert mask[0]
        exp = np.array([True] + [False] * (len(idx) - 1), dtype=bool)
        tm.assert_numpy_array_equal(mask, exp)

        mask = isna(pidx[1:])
        exp = np.zeros(len(mask), dtype=bool)
        tm.assert_numpy_array_equal(mask, exp)

    def test_isna_old_datetimelike(self):
        # isna_old should work for dt64tz, td64, and period, not just tznaive
        dti = date_range("2016-01-01", periods=3)
        dta = dti._data
        dta[-1] = NaT
        expected = np.array([False, False, True], dtype=bool)

        objs = [dta, dta.tz_localize("US/Eastern"), dta - dta, dta.to_period("D")]

        for obj in objs:
            msg = "use_inf_as_na option is deprecated"
            with tm.assert_produces_warning(FutureWarning, match=msg):
                with cf.option_context("mode.use_inf_as_na", True):
                    result = isna(obj)

            tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize(
        "value, expected",
        [
            (np.complex128(np.nan), True),
            (np.float64(1), False),
            (np.array([1, 1 + 0j, np.nan, 3]), np.array([False, False, True, False])),
            (
                np.array([1, 1 + 0j, np.nan, 3], dtype=object),
                np.array([False, False, True, False]),
            ),
            (
                np.array([1, 1 + 0j, np.nan, 3]).astype(object),
                np.array([False, False, True, False]),
            ),
        ],
    )
    def test_complex(self, value, expected):
        result = isna(value)
        if is_scalar(result):
            assert result is expected
        else:
            tm.assert_numpy_array_equal(result, expected)

    def test_datetime_other_units(self):
        idx = DatetimeIndex(["2011-01-01", "NaT", "2011-01-02"])
        exp = np.array([False, True, False])
        tm.assert_numpy_array_equal(isna(idx), exp)
        tm.assert_numpy_array_equal(notna(idx), ~exp)
        tm.assert_numpy_array_equal(isna(idx.values), exp)
        tm.assert_numpy_array_equal(notna(idx.values), ~exp)

    @pytest.mark.parametrize(
        "dtype",
        [
            "datetime64[D]",
            "datetime64[h]",
            "datetime64[m]",
            "datetime64[s]",
            "datetime64[ms]",
            "datetime64[us]",
            "datetime64[ns]",
        ],
    )
    def test_datetime_other_units_astype(self, dtype):
        idx = DatetimeIndex(["2011-01-01", "NaT", "2011-01-02"])
        values = idx.values.astype(dtype)

        exp = np.array([False, True, False])
        tm.assert_numpy_array_equal(isna(values), exp)
        tm.assert_numpy_array_equal(notna(values), ~exp)

        exp = Series([False, True, False])
        s = Series(values)
        tm.assert_series_equal(isna(s), exp)
        tm.assert_series_equal(notna(s), ~exp)
        s = Series(values, dtype=object)
        tm.assert_series_equal(isna(s), exp)
        tm.assert_series_equal(notna(s), ~exp)

    def test_timedelta_other_units(self):
        idx = TimedeltaIndex(["1 days", "NaT", "2 days"])
        exp = np.array([False, True, False])
        tm.assert_numpy_array_equal(isna(idx), exp)
        tm.assert_numpy_array_equal(notna(idx), ~exp)
        tm.assert_numpy_array_equal(isna(idx.values), exp)
        tm.assert_numpy_array_equal(notna(idx.values), ~exp)

    @pytest.mark.parametrize(
        "dtype",
        [
            "timedelta64[D]",
            "timedelta64[h]",
            "timedelta64[m]",
            "timedelta64[s]",
            "timedelta64[ms]",
            "timedelta64[us]",
            "timedelta64[ns]",
        ],
    )
    def test_timedelta_other_units_dtype(self, dtype):
        idx = TimedeltaIndex(["1 days", "NaT", "2 days"])
        values = idx.values.astype(dtype)

        exp = np.array([False, True, False])
        tm.assert_numpy_array_equal(isna(values), exp)
        tm.assert_numpy_array_equal(notna(values), ~exp)

        exp = Series([False, True, False])
        s = Series(values)
        tm.assert_series_equal(isna(s), exp)
        tm.assert_series_equal(notna(s), ~exp)
        s = Series(values, dtype=object)
        tm.assert_series_equal(isna(s), exp)
        tm.assert_series_equal(notna(s), ~exp)

    def test_period(self):
        idx = pd.PeriodIndex(["2011-01", "NaT", "2012-01"], freq="M")
        exp = np.array([False, True, False])
        tm.assert_numpy_array_equal(isna(idx), exp)
        tm.assert_numpy_array_equal(notna(idx), ~exp)

        exp = Series([False, True, False])
        s = Series(idx)
        tm.assert_series_equal(isna(s), exp)
        tm.assert_series_equal(notna(s), ~exp)
        s = Series(idx, dtype=object)
        tm.assert_series_equal(isna(s), exp)
        tm.assert_series_equal(notna(s), ~exp)

    def test_decimal(self):
        # scalars GH#23530
        a = Decimal(1.0)
        assert isna(a) is False
        assert notna(a) is True

        b = Decimal("NaN")
        assert isna(b) is True
        assert notna(b) is False

        # array
        arr = np.array([a, b])
        expected = np.array([False, True])
        result = isna(arr)
        tm.assert_numpy_array_equal(result, expected)

        result = notna(arr)
        tm.assert_numpy_array_equal(result, ~expected)

        # series
        ser = Series(arr)
        expected = Series(expected)
        result = isna(ser)
        tm.assert_series_equal(result, expected)

        result = notna(ser)
        tm.assert_series_equal(result, ~expected)

        # index
        idx = Index(arr)
        expected = np.array([False, True])
        result = isna(idx)
        tm.assert_numpy_array_equal(result, expected)

        result = notna(idx)
        tm.assert_numpy_array_equal(result, ~expected)


@pytest.mark.parametrize("dtype_equal", [True, False])
def test_array_equivalent(dtype_equal):
    assert array_equivalent(
        np.array([np.nan, np.nan]), np.array([np.nan, np.nan]), dtype_equal=dtype_equal
    )
    assert array_equivalent(
        np.array([np.nan, 1, np.nan]),
        np.array([np.nan, 1, np.nan]),
        dtype_equal=dtype_equal,
    )
    assert array_equivalent(
        np.array([np.nan, None], dtype="object"),
        np.array([np.nan, None], dtype="object"),
        dtype_equal=dtype_equal,
    )
    # Check the handling of nested arrays in array_equivalent_object
    assert array_equivalent(
        np.array([np.array([np.nan, None], dtype="object"), None], dtype="object"),
        np.array([np.array([np.nan, None], dtype="object"), None], dtype="object"),
        dtype_equal=dtype_equal,
    )
    assert array_equivalent(
        np.array([np.nan, 1 + 1j], dtype="complex"),
        np.array([np.nan, 1 + 1j], dtype="complex"),
        dtype_equal=dtype_equal,
    )
    assert not array_equivalent(
        np.array([np.nan, 1 + 1j], dtype="complex"),
        np.array([np.nan, 1 + 2j], dtype="complex"),
        dtype_equal=dtype_equal,
    )
    assert not array_equivalent(
        np.array([np.nan, 1, np.nan]),
        np.array([np.nan, 2, np.nan]),
        dtype_equal=dtype_equal,
    )
    assert not array_equivalent(
        np.array(["a", "b", "c", "d"]), np.array(["e", "e"]), dtype_equal=dtype_equal
    )
    assert array_equivalent(
        Index([0, np.nan]), Index([0, np.nan]), dtype_equal=dtype_equal
    )
    assert not array_equivalent(
        Index([0, np.nan]), Index([1, np.nan]), dtype_equal=dtype_equal
    )


@pytest.mark.parametrize("dtype_equal", [True, False])
def test_array_equivalent_tdi(dtype_equal):
    assert array_equivalent(
        TimedeltaIndex([0, np.nan]),
        TimedeltaIndex([0, np.nan]),
        dtype_equal=dtype_equal,
    )
    assert not array_equivalent(
        TimedeltaIndex([0, np.nan]),
        TimedeltaIndex([1, np.nan]),
        dtype_equal=dtype_equal,
    )


@pytest.mark.parametrize("dtype_equal", [True, False])
def test_array_equivalent_dti(dtype_equal):
    assert array_equivalent(
        DatetimeIndex([0, np.nan]), DatetimeIndex([0, np.nan]), dtype_equal=dtype_equal
    )
    assert not array_equivalent(
        DatetimeIndex([0, np.nan]), DatetimeIndex([1, np.nan]), dtype_equal=dtype_equal
    )

    dti1 = DatetimeIndex([0, np.nan], tz="US/Eastern")
    dti2 = DatetimeIndex([0, np.nan], tz="CET")
    dti3 = DatetimeIndex([1, np.nan], tz="US/Eastern")

    assert array_equivalent(
        dti1,
        dti1,
        dtype_equal=dtype_equal,
    )
    assert not array_equivalent(
        dti1,
        dti3,
        dtype_equal=dtype_equal,
    )
    # The rest are not dtype_equal
    assert not array_equivalent(DatetimeIndex([0, np.nan]), dti1)
    assert array_equivalent(
        dti2,
        dti1,
    )

    assert not array_equivalent(DatetimeIndex([0, np.nan]), TimedeltaIndex([0, np.nan]))


@pytest.mark.parametrize(
    "val", [1, 1.1, 1 + 1j, True, "abc", [1, 2], (1, 2), {1, 2}, {"a": 1}, None]
)
def test_array_equivalent_series(val):
    arr = np.array([1, 2])
    msg = "elementwise comparison failed"
    cm = (
        # stacklevel is chosen to make sense when called from .equals
        tm.assert_produces_warning(FutureWarning, match=msg, check_stacklevel=False)
        if isinstance(val, str) and not np_version_gte1p25
        else nullcontext()
    )
    with cm:
        assert not array_equivalent(Series([arr, arr]), Series([arr, val]))


def test_array_equivalent_array_mismatched_shape():
    # to trigger the motivating bug, the first N elements of the arrays need
    #  to match
    first = np.array([1, 2, 3])
    second = np.array([1, 2])

    left = Series([first, "a"], dtype=object)
    right = Series([second, "a"], dtype=object)
    assert not array_equivalent(left, right)


def test_array_equivalent_array_mismatched_dtype():
    # same shape, different dtype can still be equivalent
    first = np.array([1, 2], dtype=np.float64)
    second = np.array([1, 2])

    left = Series([first, "a"], dtype=object)
    right = Series([second, "a"], dtype=object)
    assert array_equivalent(left, right)


def test_array_equivalent_different_dtype_but_equal():
    # Unclear if this is exposed anywhere in the public-facing API
    assert array_equivalent(np.array([1, 2]), np.array([1.0, 2.0]))


@pytest.mark.parametrize(
    "lvalue, rvalue",
    [
        # There are 3 variants for each of lvalue and rvalue. We include all
        #  three for the tz-naive `now` and exclude the datetim64 variant
        #  for utcnow because it drops tzinfo.
        (fix_now, fix_utcnow),
        (fix_now.to_datetime64(), fix_utcnow),
        (fix_now.to_pydatetime(), fix_utcnow),
        (fix_now, fix_utcnow),
        (fix_now.to_datetime64(), fix_utcnow.to_pydatetime()),
        (fix_now.to_pydatetime(), fix_utcnow.to_pydatetime()),
    ],
)
def test_array_equivalent_tzawareness(lvalue, rvalue):
    # we shouldn't raise if comparing tzaware and tznaive datetimes
    left = np.array([lvalue], dtype=object)
    right = np.array([rvalue], dtype=object)

    assert not array_equivalent(left, right, strict_nan=True)
    assert not array_equivalent(left, right, strict_nan=False)


def test_array_equivalent_compat():
    # see gh-13388
    m = np.array([(1, 2), (3, 4)], dtype=[("a", int), ("b", float)])
    n = np.array([(1, 2), (3, 4)], dtype=[("a", int), ("b", float)])
    assert array_equivalent(m, n, strict_nan=True)
    assert array_equivalent(m, n, strict_nan=False)

    m = np.array([(1, 2), (3, 4)], dtype=[("a", int), ("b", float)])
    n = np.array([(1, 2), (4, 3)], dtype=[("a", int), ("b", float)])
    assert not array_equivalent(m, n, strict_nan=True)
    assert not array_equivalent(m, n, strict_nan=False)

    m = np.array([(1, 2), (3, 4)], dtype=[("a", int), ("b", float)])
    n = np.array([(1, 2), (3, 4)], dtype=[("b", int), ("a", float)])
    assert not array_equivalent(m, n, strict_nan=True)
    assert not array_equivalent(m, n, strict_nan=False)


@pytest.mark.parametrize("dtype", ["O", "S", "U"])
def test_array_equivalent_str(dtype):
    assert array_equivalent(
        np.array(["A", "B"], dtype=dtype), np.array(["A", "B"], dtype=dtype)
    )
    assert not array_equivalent(
        np.array(["A", "B"], dtype=dtype), np.array(["A", "X"], dtype=dtype)
    )


@pytest.mark.parametrize("strict_nan", [True, False])
def test_array_equivalent_nested(strict_nan):
    # reached in groupby aggregations, make sure we use np.any when checking
    #  if the comparison is truthy
    left = np.array([np.array([50, 70, 90]), np.array([20, 30])], dtype=object)
    right = np.array([np.array([50, 70, 90]), np.array([20, 30])], dtype=object)

    assert array_equivalent(left, right, strict_nan=strict_nan)
    assert not array_equivalent(left, right[::-1], strict_nan=strict_nan)

    left = np.empty(2, dtype=object)
    left[:] = [np.array([50, 70, 90]), np.array([20, 30, 40])]
    right = np.empty(2, dtype=object)
    right[:] = [np.array([50, 70, 90]), np.array([20, 30, 40])]
    assert array_equivalent(left, right, strict_nan=strict_nan)
    assert not array_equivalent(left, right[::-1], strict_nan=strict_nan)

    left = np.array([np.array([50, 50, 50]), np.array([40, 40])], dtype=object)
    right = np.array([50, 40])
    assert not array_equivalent(left, right, strict_nan=strict_nan)


@pytest.mark.filterwarnings("ignore:elementwise comparison failed:DeprecationWarning")
@pytest.mark.parametrize("strict_nan", [True, False])
def test_array_equivalent_nested2(strict_nan):
    # more than one level of nesting
    left = np.array(
        [
            np.array([np.array([50, 70]), np.array([90])], dtype=object),
            np.array([np.array([20, 30])], dtype=object),
        ],
        dtype=object,
    )
    right = np.array(
        [
            np.array([np.array([50, 70]), np.array([90])], dtype=object),
            np.array([np.array([20, 30])], dtype=object),
        ],
        dtype=object,
    )
    assert array_equivalent(left, right, strict_nan=strict_nan)
    assert not array_equivalent(left, right[::-1], strict_nan=strict_nan)

    left = np.array([np.array([np.array([50, 50, 50])], dtype=object)], dtype=object)
    right = np.array([50])
    assert not array_equivalent(left, right, strict_nan=strict_nan)


@pytest.mark.parametrize("strict_nan", [True, False])
def test_array_equivalent_nested_list(strict_nan):
    left = np.array([[50, 70, 90], [20, 30]], dtype=object)
    right = np.array([[50, 70, 90], [20, 30]], dtype=object)

    assert array_equivalent(left, right, strict_nan=strict_nan)
    assert not array_equivalent(left, right[::-1], strict_nan=strict_nan)

    left = np.array([[50, 50, 50], [40, 40]], dtype=object)
    right = np.array([50, 40])
    assert not array_equivalent(left, right, strict_nan=strict_nan)


@pytest.mark.filterwarnings("ignore:elementwise comparison failed:DeprecationWarning")
@pytest.mark.xfail(reason="failing")
@pytest.mark.parametrize("strict_nan", [True, False])
def test_array_equivalent_nested_mixed_list(strict_nan):
    # mixed arrays / lists in left and right
    # https://github.com/pandas-dev/pandas/issues/50360
    left = np.array([np.array([1, 2, 3]), np.array([4, 5])], dtype=object)
    right = np.array([[1, 2, 3], [4, 5]], dtype=object)

    assert array_equivalent(left, right, strict_nan=strict_nan)
    assert not array_equivalent(left, right[::-1], strict_nan=strict_nan)

    # multiple levels of nesting
    left = np.array(
        [
            np.array([np.array([1, 2, 3]), np.array([4, 5])], dtype=object),
            np.array([np.array([6]), np.array([7, 8]), np.array([9])], dtype=object),
        ],
        dtype=object,
    )
    right = np.array([[[1, 2, 3], [4, 5]], [[6], [7, 8], [9]]], dtype=object)
    assert array_equivalent(left, right, strict_nan=strict_nan)
    assert not array_equivalent(left, right[::-1], strict_nan=strict_nan)

    # same-length lists
    subarr = np.empty(2, dtype=object)
    subarr[:] = [
        np.array([None, "b"], dtype=object),
        np.array(["c", "d"], dtype=object),
    ]
    left = np.array([subarr, None], dtype=object)
    right = np.array([[[None, "b"], ["c", "d"]], None], dtype=object)
    assert array_equivalent(left, right, strict_nan=strict_nan)
    assert not array_equivalent(left, right[::-1], strict_nan=strict_nan)


@pytest.mark.xfail(reason="failing")
@pytest.mark.parametrize("strict_nan", [True, False])
def test_array_equivalent_nested_dicts(strict_nan):
    left = np.array([{"f1": 1, "f2": np.array(["a", "b"], dtype=object)}], dtype=object)
    right = np.array(
        [{"f1": 1, "f2": np.array(["a", "b"], dtype=object)}], dtype=object
    )
    assert array_equivalent(left, right, strict_nan=strict_nan)
    assert not array_equivalent(left, right[::-1], strict_nan=strict_nan)

    right2 = np.array([{"f1": 1, "f2": ["a", "b"]}], dtype=object)
    assert array_equivalent(left, right2, strict_nan=strict_nan)
    assert not array_equivalent(left, right2[::-1], strict_nan=strict_nan)


def test_array_equivalent_index_with_tuples():
    # GH#48446
    idx1 = Index(np.array([(pd.NA, 4), (1, 1)], dtype="object"))
    idx2 = Index(np.array([(1, 1), (pd.NA, 4)], dtype="object"))
    assert not array_equivalent(idx1, idx2)
    assert not idx1.equals(idx2)
    assert not array_equivalent(idx2, idx1)
    assert not idx2.equals(idx1)

    idx1 = Index(np.array([(4, pd.NA), (1, 1)], dtype="object"))
    idx2 = Index(np.array([(1, 1), (4, pd.NA)], dtype="object"))
    assert not array_equivalent(idx1, idx2)
    assert not idx1.equals(idx2)
    assert not array_equivalent(idx2, idx1)
    assert not idx2.equals(idx1)


@pytest.mark.parametrize(
    "dtype, na_value",
    [
        # Datetime-like
        (np.dtype("M8[ns]"), np.datetime64("NaT", "ns")),
        (np.dtype("m8[ns]"), np.timedelta64("NaT", "ns")),
        (DatetimeTZDtype.construct_from_string("datetime64[ns, US/Eastern]"), NaT),
        (PeriodDtype("M"), NaT),
        # Integer
        ("u1", 0),
        ("u2", 0),
        ("u4", 0),
        ("u8", 0),
        ("i1", 0),
        ("i2", 0),
        ("i4", 0),
        ("i8", 0),
        # Bool
        ("bool", False),
        # Float
        ("f2", np.nan),
        ("f4", np.nan),
        ("f8", np.nan),
        # Object
        ("O", np.nan),
        # Interval
        (IntervalDtype(), np.nan),
    ],
)
def test_na_value_for_dtype(dtype, na_value):
    result = na_value_for_dtype(pandas_dtype(dtype))
    # identify check doesn't work for datetime64/timedelta64("NaT") bc they
    #  are not singletons
    assert result is na_value or (
        isna(result) and isna(na_value) and type(result) is type(na_value)
    )


class TestNAObj:
    def _check_behavior(self, arr, expected):
        result = libmissing.isnaobj(arr)
        tm.assert_numpy_array_equal(result, expected)
        result = libmissing.isnaobj(arr, inf_as_na=True)
        tm.assert_numpy_array_equal(result, expected)

        arr = np.atleast_2d(arr)
        expected = np.atleast_2d(expected)

        result = libmissing.isnaobj(arr)
        tm.assert_numpy_array_equal(result, expected)
        result = libmissing.isnaobj(arr, inf_as_na=True)
        tm.assert_numpy_array_equal(result, expected)

        # Test fortran order
        arr = arr.copy(order="F")
        result = libmissing.isnaobj(arr)
        tm.assert_numpy_array_equal(result, expected)
        result = libmissing.isnaobj(arr, inf_as_na=True)
        tm.assert_numpy_array_equal(result, expected)

    def test_basic(self):
        arr = np.array([1, None, "foo", -5.1, NaT, np.nan])
        expected = np.array([False, True, False, False, True, True])

        self._check_behavior(arr, expected)

    def test_non_obj_dtype(self):
        arr = np.array([1, 3, np.nan, 5], dtype=float)
        expected = np.array([False, False, True, False])

        self._check_behavior(arr, expected)

    def test_empty_arr(self):
        arr = np.array([])
        expected = np.array([], dtype=bool)

        self._check_behavior(arr, expected)

    def test_empty_str_inp(self):
        arr = np.array([""])  # empty but not na
        expected = np.array([False])

        self._check_behavior(arr, expected)

    def test_empty_like(self):
        # see gh-13717: no segfaults!
        arr = np.empty_like([None])
        expected = np.array([True])

        self._check_behavior(arr, expected)


m8_units = ["as", "ps", "ns", "us", "ms", "s", "m", "h", "D", "W", "M", "Y"]

na_vals = (
    [
        None,
        NaT,
        float("NaN"),
        complex("NaN"),
        np.nan,
        np.float64("NaN"),
        np.float32("NaN"),
        np.complex64(np.nan),
        np.complex128(np.nan),
        np.datetime64("NaT"),
        np.timedelta64("NaT"),
    ]
    + [np.datetime64("NaT", unit) for unit in m8_units]
    + [np.timedelta64("NaT", unit) for unit in m8_units]
)

inf_vals = [
    float("inf"),
    float("-inf"),
    complex("inf"),
    complex("-inf"),
    np.inf,
    -np.inf,
]

int_na_vals = [
    # Values that match iNaT, which we treat as null in specific cases
    np.int64(NaT._value),
    int(NaT._value),
]

sometimes_na_vals = [Decimal("NaN")]

never_na_vals = [
    # float/complex values that when viewed as int64 match iNaT
    -0.0,
    np.float64("-0.0"),
    -0j,
    np.complex64(-0j),
]


class TestLibMissing:
    @pytest.mark.parametrize("func", [libmissing.checknull, isna])
    @pytest.mark.parametrize(
        "value", na_vals + sometimes_na_vals  # type: ignore[operator]
    )
    def test_checknull_na_vals(self, func, value):
        assert func(value)

    @pytest.mark.parametrize("func", [libmissing.checknull, isna])
    @pytest.mark.parametrize("value", inf_vals)
    def test_checknull_inf_vals(self, func, value):
        assert not func(value)

    @pytest.mark.parametrize("func", [libmissing.checknull, isna])
    @pytest.mark.parametrize("value", int_na_vals)
    def test_checknull_intna_vals(self, func, value):
        assert not func(value)

    @pytest.mark.parametrize("func", [libmissing.checknull, isna])
    @pytest.mark.parametrize("value", never_na_vals)
    def test_checknull_never_na_vals(self, func, value):
        assert not func(value)

    @pytest.mark.parametrize(
        "value", na_vals + sometimes_na_vals  # type: ignore[operator]
    )
    def test_checknull_old_na_vals(self, value):
        assert libmissing.checknull(value, inf_as_na=True)

    @pytest.mark.parametrize("value", inf_vals)
    def test_checknull_old_inf_vals(self, value):
        assert libmissing.checknull(value, inf_as_na=True)

    @pytest.mark.parametrize("value", int_na_vals)
    def test_checknull_old_intna_vals(self, value):
        assert not libmissing.checknull(value, inf_as_na=True)

    @pytest.mark.parametrize("value", int_na_vals)
    def test_checknull_old_never_na_vals(self, value):
        assert not libmissing.checknull(value, inf_as_na=True)

    def test_is_matching_na(self, nulls_fixture, nulls_fixture2):
        left = nulls_fixture
        right = nulls_fixture2

        assert libmissing.is_matching_na(left, left)

        if left is right:
            assert libmissing.is_matching_na(left, right)
        elif is_float(left) and is_float(right):
            # np.nan vs float("NaN") we consider as matching
            assert libmissing.is_matching_na(left, right)
        elif type(left) is type(right):
            # e.g. both Decimal("NaN")
            assert libmissing.is_matching_na(left, right)
        else:
            assert not libmissing.is_matching_na(left, right)

    def test_is_matching_na_nan_matches_none(self):
        assert not libmissing.is_matching_na(None, np.nan)
        assert not libmissing.is_matching_na(np.nan, None)

        assert libmissing.is_matching_na(None, np.nan, nan_matches_none=True)
        assert libmissing.is_matching_na(np.nan, None, nan_matches_none=True)


class TestIsValidNAForDtype:
    def test_is_valid_na_for_dtype_interval(self):
        dtype = IntervalDtype("int64", "left")
        assert not is_valid_na_for_dtype(NaT, dtype)

        dtype = IntervalDtype("datetime64[ns]", "both")
        assert not is_valid_na_for_dtype(NaT, dtype)

    def test_is_valid_na_for_dtype_categorical(self):
        dtype = CategoricalDtype(categories=[0, 1, 2])
        assert is_valid_na_for_dtype(np.nan, dtype)

        assert not is_valid_na_for_dtype(NaT, dtype)
        assert not is_valid_na_for_dtype(np.datetime64("NaT", "ns"), dtype)
        assert not is_valid_na_for_dtype(np.timedelta64("NaT", "ns"), dtype)
