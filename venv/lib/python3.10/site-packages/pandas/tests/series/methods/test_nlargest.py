"""
Note: for naming purposes, most tests are title with as e.g. "test_nlargest_foo"
but are implicitly also testing nsmallest_foo.
"""
from itertools import product

import numpy as np
import pytest

import pandas as pd
from pandas import Series
import pandas._testing as tm

main_dtypes = [
    "datetime",
    "datetimetz",
    "timedelta",
    "int8",
    "int16",
    "int32",
    "int64",
    "float32",
    "float64",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
]


@pytest.fixture
def s_main_dtypes():
    """
    A DataFrame with many dtypes

    * datetime
    * datetimetz
    * timedelta
    * [u]int{8,16,32,64}
    * float{32,64}

    The columns are the name of the dtype.
    """
    df = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2003", "2002", "2001", "2002", "2005"]),
            "datetimetz": pd.to_datetime(
                ["2003", "2002", "2001", "2002", "2005"]
            ).tz_localize("US/Eastern"),
            "timedelta": pd.to_timedelta(["3d", "2d", "1d", "2d", "5d"]),
        }
    )

    for dtype in [
        "int8",
        "int16",
        "int32",
        "int64",
        "float32",
        "float64",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
    ]:
        df[dtype] = Series([3, 2, 1, 2, 5], dtype=dtype)

    return df


@pytest.fixture(params=main_dtypes)
def s_main_dtypes_split(request, s_main_dtypes):
    """Each series in s_main_dtypes."""
    return s_main_dtypes[request.param]


def assert_check_nselect_boundary(vals, dtype, method):
    # helper function for 'test_boundary_{dtype}' tests
    ser = Series(vals, dtype=dtype)
    result = getattr(ser, method)(3)
    expected_idxr = [0, 1, 2] if method == "nsmallest" else [3, 2, 1]
    expected = ser.loc[expected_idxr]
    tm.assert_series_equal(result, expected)


class TestSeriesNLargestNSmallest:
    @pytest.mark.parametrize(
        "r",
        [
            Series([3.0, 2, 1, 2, "5"], dtype="object"),
            Series([3.0, 2, 1, 2, 5], dtype="object"),
            # not supported on some archs
            # Series([3., 2, 1, 2, 5], dtype='complex256'),
            Series([3.0, 2, 1, 2, 5], dtype="complex128"),
            Series(list("abcde")),
            Series(list("abcde"), dtype="category"),
        ],
    )
    def test_nlargest_error(self, r):
        dt = r.dtype
        msg = f"Cannot use method 'n(largest|smallest)' with dtype {dt}"
        args = 2, len(r), 0, -1
        methods = r.nlargest, r.nsmallest
        for method, arg in product(methods, args):
            with pytest.raises(TypeError, match=msg):
                method(arg)

    def test_nsmallest_nlargest(self, s_main_dtypes_split):
        # float, int, datetime64 (use i8), timedelts64 (same),
        # object that are numbers, object that are strings
        ser = s_main_dtypes_split

        tm.assert_series_equal(ser.nsmallest(2), ser.iloc[[2, 1]])
        tm.assert_series_equal(ser.nsmallest(2, keep="last"), ser.iloc[[2, 3]])

        empty = ser.iloc[0:0]
        tm.assert_series_equal(ser.nsmallest(0), empty)
        tm.assert_series_equal(ser.nsmallest(-1), empty)
        tm.assert_series_equal(ser.nlargest(0), empty)
        tm.assert_series_equal(ser.nlargest(-1), empty)

        tm.assert_series_equal(ser.nsmallest(len(ser)), ser.sort_values())
        tm.assert_series_equal(ser.nsmallest(len(ser) + 1), ser.sort_values())
        tm.assert_series_equal(ser.nlargest(len(ser)), ser.iloc[[4, 0, 1, 3, 2]])
        tm.assert_series_equal(ser.nlargest(len(ser) + 1), ser.iloc[[4, 0, 1, 3, 2]])

    def test_nlargest_misc(self):
        ser = Series([3.0, np.nan, 1, 2, 5])
        result = ser.nlargest()
        expected = ser.iloc[[4, 0, 3, 2, 1]]
        tm.assert_series_equal(result, expected)
        result = ser.nsmallest()
        expected = ser.iloc[[2, 3, 0, 4, 1]]
        tm.assert_series_equal(result, expected)

        msg = 'keep must be either "first", "last"'
        with pytest.raises(ValueError, match=msg):
            ser.nsmallest(keep="invalid")
        with pytest.raises(ValueError, match=msg):
            ser.nlargest(keep="invalid")

        # GH#15297
        ser = Series([1] * 5, index=[1, 2, 3, 4, 5])
        expected_first = Series([1] * 3, index=[1, 2, 3])
        expected_last = Series([1] * 3, index=[5, 4, 3])

        result = ser.nsmallest(3)
        tm.assert_series_equal(result, expected_first)

        result = ser.nsmallest(3, keep="last")
        tm.assert_series_equal(result, expected_last)

        result = ser.nlargest(3)
        tm.assert_series_equal(result, expected_first)

        result = ser.nlargest(3, keep="last")
        tm.assert_series_equal(result, expected_last)

    @pytest.mark.parametrize("n", range(1, 5))
    def test_nlargest_n(self, n):
        # GH 13412
        ser = Series([1, 4, 3, 2], index=[0, 0, 1, 1])
        result = ser.nlargest(n)
        expected = ser.sort_values(ascending=False).head(n)
        tm.assert_series_equal(result, expected)

        result = ser.nsmallest(n)
        expected = ser.sort_values().head(n)
        tm.assert_series_equal(result, expected)

    def test_nlargest_boundary_integer(self, nselect_method, any_int_numpy_dtype):
        # GH#21426
        dtype_info = np.iinfo(any_int_numpy_dtype)
        min_val, max_val = dtype_info.min, dtype_info.max
        vals = [min_val, min_val + 1, max_val - 1, max_val]
        assert_check_nselect_boundary(vals, any_int_numpy_dtype, nselect_method)

    def test_nlargest_boundary_float(self, nselect_method, float_numpy_dtype):
        # GH#21426
        dtype_info = np.finfo(float_numpy_dtype)
        min_val, max_val = dtype_info.min, dtype_info.max
        min_2nd, max_2nd = np.nextafter([min_val, max_val], 0, dtype=float_numpy_dtype)
        vals = [min_val, min_2nd, max_2nd, max_val]
        assert_check_nselect_boundary(vals, float_numpy_dtype, nselect_method)

    @pytest.mark.parametrize("dtype", ["datetime64[ns]", "timedelta64[ns]"])
    def test_nlargest_boundary_datetimelike(self, nselect_method, dtype):
        # GH#21426
        # use int64 bounds and +1 to min_val since true minimum is NaT
        # (include min_val/NaT at end to maintain same expected_idxr)
        dtype_info = np.iinfo("int64")
        min_val, max_val = dtype_info.min, dtype_info.max
        vals = [min_val + 1, min_val + 2, max_val - 1, max_val, min_val]
        assert_check_nselect_boundary(vals, dtype, nselect_method)

    def test_nlargest_duplicate_keep_all_ties(self):
        # see GH#16818
        ser = Series([10, 9, 8, 7, 7, 7, 7, 6])
        result = ser.nlargest(4, keep="all")
        expected = Series([10, 9, 8, 7, 7, 7, 7])
        tm.assert_series_equal(result, expected)

        result = ser.nsmallest(2, keep="all")
        expected = Series([6, 7, 7, 7, 7], index=[7, 3, 4, 5, 6])
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "data,expected", [([True, False], [True]), ([True, False, True, True], [True])]
    )
    def test_nlargest_boolean(self, data, expected):
        # GH#26154 : ensure True > False
        ser = Series(data)
        result = ser.nlargest(1)
        expected = Series(expected)
        tm.assert_series_equal(result, expected)

    def test_nlargest_nullable(self, any_numeric_ea_dtype):
        # GH#42816
        dtype = any_numeric_ea_dtype
        if dtype.startswith("UInt"):
            # Can't cast from negative float to uint on some platforms
            arr = np.random.default_rng(2).integers(1, 10, 10)
        else:
            arr = np.random.default_rng(2).standard_normal(10)
        arr = arr.astype(dtype.lower(), copy=False)

        ser = Series(arr.copy(), dtype=dtype)
        ser[1] = pd.NA
        result = ser.nlargest(5)

        expected = (
            Series(np.delete(arr, 1), index=ser.index.delete(1))
            .nlargest(5)
            .astype(dtype)
        )
        tm.assert_series_equal(result, expected)

    def test_nsmallest_nan_when_keep_is_all(self):
        # GH#46589
        s = Series([1, 2, 3, 3, 3, None])
        result = s.nsmallest(3, keep="all")
        expected = Series([1.0, 2.0, 3.0, 3.0, 3.0])
        tm.assert_series_equal(result, expected)

        s = Series([1, 2, None, None, None])
        result = s.nsmallest(3, keep="all")
        expected = Series([1, 2, None, None, None])
        tm.assert_series_equal(result, expected)
