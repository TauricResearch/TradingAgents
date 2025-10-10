from datetime import (
    datetime,
    timedelta,
)
from importlib import reload
import string
import sys

import numpy as np
import pytest

from pandas._libs.tslibs import iNaT
import pandas.util._test_decorators as td

from pandas import (
    NA,
    Categorical,
    CategoricalDtype,
    DatetimeTZDtype,
    Index,
    Interval,
    NaT,
    Series,
    Timedelta,
    Timestamp,
    cut,
    date_range,
    to_datetime,
)
import pandas._testing as tm


def rand_str(nchars: int) -> str:
    """
    Generate one random byte string.
    """
    RANDS_CHARS = np.array(
        list(string.ascii_letters + string.digits), dtype=(np.str_, 1)
    )
    return "".join(np.random.default_rng(2).choice(RANDS_CHARS, nchars))


class TestAstypeAPI:
    def test_astype_unitless_dt64_raises(self):
        # GH#47844
        ser = Series(["1970-01-01", "1970-01-01", "1970-01-01"], dtype="datetime64[ns]")
        df = ser.to_frame()

        msg = "Casting to unit-less dtype 'datetime64' is not supported"
        with pytest.raises(TypeError, match=msg):
            ser.astype(np.datetime64)
        with pytest.raises(TypeError, match=msg):
            df.astype(np.datetime64)
        with pytest.raises(TypeError, match=msg):
            ser.astype("datetime64")
        with pytest.raises(TypeError, match=msg):
            df.astype("datetime64")

    def test_arg_for_errors_in_astype(self):
        # see GH#14878
        ser = Series([1, 2, 3])

        msg = (
            r"Expected value of kwarg 'errors' to be one of \['raise', "
            r"'ignore'\]\. Supplied value is 'False'"
        )
        with pytest.raises(ValueError, match=msg):
            ser.astype(np.float64, errors=False)

        ser.astype(np.int8, errors="raise")

    @pytest.mark.parametrize("dtype_class", [dict, Series])
    def test_astype_dict_like(self, dtype_class):
        # see GH#7271
        ser = Series(range(0, 10, 2), name="abc")

        dt1 = dtype_class({"abc": str})
        result = ser.astype(dt1)
        expected = Series(["0", "2", "4", "6", "8"], name="abc", dtype="str")
        tm.assert_series_equal(result, expected)

        dt2 = dtype_class({"abc": "float64"})
        result = ser.astype(dt2)
        expected = Series([0.0, 2.0, 4.0, 6.0, 8.0], dtype="float64", name="abc")
        tm.assert_series_equal(result, expected)

        dt3 = dtype_class({"abc": str, "def": str})
        msg = (
            "Only the Series name can be used for the key in Series dtype "
            r"mappings\."
        )
        with pytest.raises(KeyError, match=msg):
            ser.astype(dt3)

        dt4 = dtype_class({0: str})
        with pytest.raises(KeyError, match=msg):
            ser.astype(dt4)

        # GH#16717
        # if dtypes provided is empty, it should error
        if dtype_class is Series:
            dt5 = dtype_class({}, dtype=object)
        else:
            dt5 = dtype_class({})

        with pytest.raises(KeyError, match=msg):
            ser.astype(dt5)


class TestAstype:
    @pytest.mark.parametrize("tz", [None, "UTC", "US/Pacific"])
    def test_astype_object_to_dt64_non_nano(self, tz):
        # GH#55756, GH#54620
        ts = Timestamp("2999-01-01")
        dtype = "M8[us]"
        if tz is not None:
            dtype = f"M8[us, {tz}]"
        vals = [ts, "2999-01-02 03:04:05.678910", 2500]
        ser = Series(vals, dtype=object)
        result = ser.astype(dtype)

        # The 2500 is interpreted as microseconds, consistent with what
        #  we would get if we created DatetimeIndexes from vals[:2] and vals[2:]
        #  and concated the results.
        pointwise = [
            vals[0].tz_localize(tz),
            Timestamp(vals[1], tz=tz),
            to_datetime(vals[2], unit="us", utc=True).tz_convert(tz),
        ]
        exp_vals = [x.as_unit("us").asm8 for x in pointwise]
        exp_arr = np.array(exp_vals, dtype="M8[us]")
        expected = Series(exp_arr, dtype="M8[us]")
        if tz is not None:
            expected = expected.dt.tz_localize("UTC").dt.tz_convert(tz)
        tm.assert_series_equal(result, expected)

    def test_astype_mixed_object_to_dt64tz(self):
        # pre-2.0 this raised ValueError bc of tz mismatch
        # xref GH#32581
        ts = Timestamp("2016-01-04 05:06:07", tz="US/Pacific")
        ts2 = ts.tz_convert("Asia/Tokyo")

        ser = Series([ts, ts2], dtype=object)
        res = ser.astype("datetime64[ns, Europe/Brussels]")
        expected = Series(
            [ts.tz_convert("Europe/Brussels"), ts2.tz_convert("Europe/Brussels")],
            dtype="datetime64[ns, Europe/Brussels]",
        )
        tm.assert_series_equal(res, expected)

    @pytest.mark.parametrize("dtype", np.typecodes["All"])
    def test_astype_empty_constructor_equality(self, dtype):
        # see GH#15524

        if dtype not in (
            "S",
            "V",  # poor support (if any) currently
            "M",
            "m",  # Generic timestamps raise a ValueError. Already tested.
        ):
            init_empty = Series([], dtype=dtype)
            as_type_empty = Series([]).astype(dtype)
            tm.assert_series_equal(init_empty, as_type_empty)

    @pytest.mark.parametrize("dtype", [str, np.str_])
    @pytest.mark.parametrize(
        "series",
        [
            Series([string.digits * 10, rand_str(63), rand_str(64), rand_str(1000)]),
            Series([string.digits * 10, rand_str(63), rand_str(64), np.nan, 1.0]),
        ],
    )
    def test_astype_str_map(self, dtype, series, using_infer_string):
        # see GH#4405
        using_string_dtype = using_infer_string and dtype is str
        result = series.astype(dtype)
        if using_string_dtype:
            expected = series.map(lambda val: str(val) if val is not np.nan else np.nan)
        else:
            expected = series.map(str)
            if using_infer_string:
                expected = expected.astype(object)
        tm.assert_series_equal(result, expected)

    def test_astype_float_to_period(self):
        result = Series([np.nan]).astype("period[D]")
        expected = Series([NaT], dtype="period[D]")
        tm.assert_series_equal(result, expected)

    def test_astype_no_pandas_dtype(self):
        # https://github.com/pandas-dev/pandas/pull/24866
        ser = Series([1, 2], dtype="int64")
        # Don't have NumpyEADtype in the public API, so we use `.array.dtype`,
        # which is a NumpyEADtype.
        result = ser.astype(ser.array.dtype)
        tm.assert_series_equal(result, ser)

    @pytest.mark.parametrize("dtype", [np.datetime64, np.timedelta64])
    def test_astype_generic_timestamp_no_frequency(self, dtype, request):
        # see GH#15524, GH#15987
        data = [1]
        ser = Series(data)

        if np.dtype(dtype).name not in ["timedelta64", "datetime64"]:
            mark = pytest.mark.xfail(reason="GH#33890 Is assigned ns unit")
            request.applymarker(mark)

        msg = (
            rf"The '{dtype.__name__}' dtype has no unit\. "
            rf"Please pass in '{dtype.__name__}\[ns\]' instead."
        )
        with pytest.raises(ValueError, match=msg):
            ser.astype(dtype)

    def test_astype_dt64_to_str(self):
        # GH#10442 : testing astype(str) is correct for Series/DatetimeIndex
        dti = date_range("2012-01-01", periods=3)
        result = Series(dti).astype(str)
        expected = Series(["2012-01-01", "2012-01-02", "2012-01-03"], dtype="str")
        tm.assert_series_equal(result, expected)

    def test_astype_dt64tz_to_str(self):
        # GH#10442 : testing astype(str) is correct for Series/DatetimeIndex
        dti_tz = date_range("2012-01-01", periods=3, tz="US/Eastern")
        result = Series(dti_tz).astype(str)
        expected = Series(
            [
                "2012-01-01 00:00:00-05:00",
                "2012-01-02 00:00:00-05:00",
                "2012-01-03 00:00:00-05:00",
            ],
            dtype="str",
        )
        tm.assert_series_equal(result, expected)

    def test_astype_datetime(self, unit):
        ser = Series(iNaT, dtype=f"M8[{unit}]", index=range(5))

        ser = ser.astype("O")
        assert ser.dtype == np.object_

        ser = Series([datetime(2001, 1, 2, 0, 0)])

        ser = ser.astype("O")
        assert ser.dtype == np.object_

        ser = Series(
            [datetime(2001, 1, 2, 0, 0) for i in range(3)], dtype=f"M8[{unit}]"
        )

        ser[1] = np.nan
        assert ser.dtype == f"M8[{unit}]"

        ser = ser.astype("O")
        assert ser.dtype == np.object_

    def test_astype_datetime64tz(self):
        ser = Series(date_range("20130101", periods=3, tz="US/Eastern"))

        # astype
        result = ser.astype(object)
        expected = Series(ser.astype(object), dtype=object)
        tm.assert_series_equal(result, expected)

        result = Series(ser.values).dt.tz_localize("UTC").dt.tz_convert(ser.dt.tz)
        tm.assert_series_equal(result, ser)

        # astype - object, preserves on construction
        result = Series(ser.astype(object))
        expected = ser.astype(object)
        tm.assert_series_equal(result, expected)

        # astype - datetime64[ns, tz]
        msg = "Cannot use .astype to convert from timezone-naive"
        with pytest.raises(TypeError, match=msg):
            # dt64->dt64tz astype deprecated
            Series(ser.values).astype("datetime64[ns, US/Eastern]")

        with pytest.raises(TypeError, match=msg):
            # dt64->dt64tz astype deprecated
            Series(ser.values).astype(ser.dtype)

        result = ser.astype("datetime64[ns, CET]")
        expected = Series(date_range("20130101 06:00:00", periods=3, tz="CET"))
        tm.assert_series_equal(result, expected)

    def test_astype_str_cast_dt64(self):
        # see GH#9757
        ts = Series([Timestamp("2010-01-04 00:00:00")])
        res = ts.astype(str)

        expected = Series(["2010-01-04"], dtype="str")
        tm.assert_series_equal(res, expected)

        ts = Series([Timestamp("2010-01-04 00:00:00", tz="US/Eastern")])
        res = ts.astype(str)

        expected = Series(["2010-01-04 00:00:00-05:00"], dtype="str")
        tm.assert_series_equal(res, expected)

    def test_astype_str_cast_td64(self):
        # see GH#9757

        td = Series([Timedelta(1, unit="d")])
        ser = td.astype(str)

        expected = Series(["1 days"], dtype="str")
        tm.assert_series_equal(ser, expected)

    def test_dt64_series_astype_object(self):
        dt64ser = Series(date_range("20130101", periods=3))
        result = dt64ser.astype(object)
        assert isinstance(result.iloc[0], datetime)
        assert result.dtype == np.object_

    def test_td64_series_astype_object(self):
        tdser = Series(["59 Days", "59 Days", "NaT"], dtype="timedelta64[ns]")
        result = tdser.astype(object)
        assert isinstance(result.iloc[0], timedelta)
        assert result.dtype == np.object_

    @pytest.mark.parametrize(
        "data, dtype",
        [
            (["x", "y", "z"], "string[python]"),
            pytest.param(
                ["x", "y", "z"],
                "string[pyarrow]",
                marks=td.skip_if_no("pyarrow"),
            ),
            (["x", "y", "z"], "category"),
            (3 * [Timestamp("2020-01-01", tz="UTC")], None),
            (3 * [Interval(0, 1)], None),
        ],
    )
    @pytest.mark.parametrize("errors", ["raise", "ignore"])
    def test_astype_ignores_errors_for_extension_dtypes(self, data, dtype, errors):
        # https://github.com/pandas-dev/pandas/issues/35471
        ser = Series(data, dtype=dtype)
        if errors == "ignore":
            expected = ser
            result = ser.astype(float, errors="ignore")
            tm.assert_series_equal(result, expected)
        else:
            msg = "(Cannot cast)|(could not convert)"
            with pytest.raises((ValueError, TypeError), match=msg):
                ser.astype(float, errors=errors)

    @pytest.mark.parametrize("dtype", [np.float16, np.float32, np.float64])
    def test_astype_from_float_to_str(self, dtype):
        # https://github.com/pandas-dev/pandas/issues/36451
        ser = Series([0.1], dtype=dtype)
        result = ser.astype(str)
        expected = Series(["0.1"], dtype="str")
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "value, string_value",
        [
            (None, "None"),
            (np.nan, "nan"),
            (NA, "<NA>"),
        ],
    )
    def test_astype_to_str_preserves_na(self, value, string_value, using_infer_string):
        # https://github.com/pandas-dev/pandas/issues/36904
        ser = Series(["a", "b", value], dtype=object)
        result = ser.astype(str)
        expected = Series(
            ["a", "b", None if using_infer_string else string_value], dtype="str"
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("dtype", ["float32", "float64", "int64", "int32"])
    def test_astype(self, dtype):
        ser = Series(np.random.default_rng(2).standard_normal(5), name="foo")
        as_typed = ser.astype(dtype)

        assert as_typed.dtype == dtype
        assert as_typed.name == ser.name

    @pytest.mark.parametrize("value", [np.nan, np.inf])
    @pytest.mark.parametrize("dtype", [np.int32, np.int64])
    def test_astype_cast_nan_inf_int(self, dtype, value):
        # gh-14265: check NaN and inf raise error when converting to int
        msg = "Cannot convert non-finite values \\(NA or inf\\) to integer"
        ser = Series([value])

        with pytest.raises(ValueError, match=msg):
            ser.astype(dtype)

    @pytest.mark.parametrize("dtype", [int, np.int8, np.int64])
    def test_astype_cast_object_int_fail(self, dtype):
        arr = Series(["car", "house", "tree", "1"])
        msg = r"invalid literal for int\(\) with base 10: 'car'"
        with pytest.raises(ValueError, match=msg):
            arr.astype(dtype)

    def test_astype_float_to_uint_negatives_raise(
        self, float_numpy_dtype, any_unsigned_int_numpy_dtype
    ):
        # GH#45151 We don't cast negative numbers to nonsense values
        # TODO: same for EA float/uint dtypes, signed integers?
        arr = np.arange(5).astype(float_numpy_dtype) - 3  # includes negatives
        ser = Series(arr)

        msg = "Cannot losslessly cast from .* to .*"
        with pytest.raises(ValueError, match=msg):
            ser.astype(any_unsigned_int_numpy_dtype)

        with pytest.raises(ValueError, match=msg):
            ser.to_frame().astype(any_unsigned_int_numpy_dtype)

        with pytest.raises(ValueError, match=msg):
            # We currently catch and re-raise in Index.astype
            Index(ser).astype(any_unsigned_int_numpy_dtype)

        with pytest.raises(ValueError, match=msg):
            ser.array.astype(any_unsigned_int_numpy_dtype)

    def test_astype_cast_object_int(self):
        arr = Series(["1", "2", "3", "4"], dtype=object)
        result = arr.astype(int)

        tm.assert_series_equal(result, Series(np.arange(1, 5)))

    def test_astype_unicode(self, using_infer_string):
        # see GH#7758: A bit of magic is required to set
        # default encoding to utf-8
        digits = string.digits
        test_series = [
            Series([digits * 10, rand_str(63), rand_str(64), rand_str(1000)]),
            Series(["データーサイエンス、お前はもう死んでいる"]),
        ]

        former_encoding = None

        if sys.getdefaultencoding() == "utf-8":
            # GH#45326 as of 2.0 Series.astype matches Index.astype by handling
            #  bytes with obj.decode() instead of str(obj)
            item = "野菜食べないとやばい"
            ser = Series([item.encode()])
            result = ser.astype(np.str_)
            expected = Series([item], dtype=object)
            tm.assert_series_equal(result, expected)

        for ser in test_series:
            res = ser.astype(np.str_)
            expec = ser.map(str)
            if using_infer_string:
                expec = expec.astype(object)
            tm.assert_series_equal(res, expec)

        # Restore the former encoding
        if former_encoding is not None and former_encoding != "utf-8":
            reload(sys)
            sys.setdefaultencoding(former_encoding)

    def test_astype_bytes(self):
        # GH#39474
        result = Series(["foo", "bar", "baz"]).astype(bytes)
        assert result.dtypes == np.dtype("S3")

    def test_astype_nan_to_bool(self):
        # GH#43018
        ser = Series(np.nan, dtype="object")
        result = ser.astype("bool")
        expected = Series(True, dtype="bool")
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "dtype",
        tm.ALL_INT_EA_DTYPES + tm.FLOAT_EA_DTYPES,
    )
    def test_astype_ea_to_datetimetzdtype(self, dtype):
        # GH37553
        ser = Series([4, 0, 9], dtype=dtype)
        result = ser.astype(DatetimeTZDtype(tz="US/Pacific"))

        expected = Series(
            {
                0: Timestamp("1969-12-31 16:00:00.000000004-08:00", tz="US/Pacific"),
                1: Timestamp("1969-12-31 16:00:00.000000000-08:00", tz="US/Pacific"),
                2: Timestamp("1969-12-31 16:00:00.000000009-08:00", tz="US/Pacific"),
            }
        )

        tm.assert_series_equal(result, expected)

    def test_astype_retain_attrs(self, any_numpy_dtype):
        # GH#44414
        ser = Series([0, 1, 2, 3])
        ser.attrs["Location"] = "Michigan"

        result = ser.astype(any_numpy_dtype).attrs
        expected = ser.attrs

        tm.assert_dict_equal(expected, result)


class TestAstypeString:
    @pytest.mark.parametrize(
        "data, dtype",
        [
            ([True, NA], "boolean"),
            (["A", NA], "category"),
            (["2020-10-10", "2020-10-10"], "datetime64[ns]"),
            (["2020-10-10", "2020-10-10", NaT], "datetime64[ns]"),
            (
                ["2012-01-01 00:00:00-05:00", NaT],
                "datetime64[ns, US/Eastern]",
            ),
            ([1, None], "UInt16"),
            (["1/1/2021", "2/1/2021"], "period[M]"),
            (["1/1/2021", "2/1/2021", NaT], "period[M]"),
            (["1 Day", "59 Days", NaT], "timedelta64[ns]"),
            # currently no way to parse IntervalArray from a list of strings
        ],
    )
    def test_astype_string_to_extension_dtype_roundtrip(
        self, data, dtype, request, nullable_string_dtype
    ):
        if dtype == "boolean":
            mark = pytest.mark.xfail(
                reason="TODO StringArray.astype() with missing values #GH40566"
            )
            request.applymarker(mark)
        # GH-40351
        ser = Series(data, dtype=dtype)

        # Note: just passing .astype(dtype) fails for dtype="category"
        #  with bc ser.dtype.categories will be object dtype whereas
        #  result.dtype.categories will have string dtype
        result = ser.astype(nullable_string_dtype).astype(ser.dtype)
        tm.assert_series_equal(result, ser)


class TestAstypeCategorical:
    def test_astype_categorical_to_other(self):
        cat = Categorical([f"{i} - {i + 499}" for i in range(0, 10000, 500)])
        ser = Series(np.random.default_rng(2).integers(0, 10000, 100)).sort_values()
        ser = cut(ser, range(0, 10500, 500), right=False, labels=cat)

        expected = ser
        tm.assert_series_equal(ser.astype("category"), expected)
        tm.assert_series_equal(ser.astype(CategoricalDtype()), expected)
        msg = r"Cannot cast object|str dtype to float64"
        with pytest.raises(ValueError, match=msg):
            ser.astype("float64")

        cat = Series(Categorical(["a", "b", "b", "a", "a", "c", "c", "c"]))
        exp = Series(["a", "b", "b", "a", "a", "c", "c", "c"], dtype="str")
        tm.assert_series_equal(cat.astype("str"), exp)
        s2 = Series(Categorical(["1", "2", "3", "4"]))
        exp2 = Series([1, 2, 3, 4]).astype("int")
        tm.assert_series_equal(s2.astype("int"), exp2)

        # object don't sort correctly, so just compare that we have the same
        # values
        def cmp(a, b):
            tm.assert_almost_equal(np.sort(np.unique(a)), np.sort(np.unique(b)))

        expected = Series(np.array(ser.values), name="value_group")
        cmp(ser.astype("object"), expected)
        cmp(ser.astype(np.object_), expected)

        # array conversion
        tm.assert_almost_equal(np.array(ser), np.array(ser.values))

        tm.assert_series_equal(ser.astype("category"), ser)
        tm.assert_series_equal(ser.astype(CategoricalDtype()), ser)

        roundtrip_expected = ser.cat.set_categories(
            ser.cat.categories.sort_values()
        ).cat.remove_unused_categories()
        result = ser.astype("object").astype("category")
        tm.assert_series_equal(result, roundtrip_expected)
        result = ser.astype("object").astype(CategoricalDtype())
        tm.assert_series_equal(result, roundtrip_expected)

    def test_astype_categorical_invalid_conversions(self):
        # invalid conversion (these are NOT a dtype)
        cat = Categorical([f"{i} - {i + 499}" for i in range(0, 10000, 500)])
        ser = Series(np.random.default_rng(2).integers(0, 10000, 100)).sort_values()
        ser = cut(ser, range(0, 10500, 500), right=False, labels=cat)

        msg = (
            "dtype '<class 'pandas.core.arrays.categorical.Categorical'>' "
            "not understood"
        )
        with pytest.raises(TypeError, match=msg):
            ser.astype(Categorical)
        with pytest.raises(TypeError, match=msg):
            ser.astype("object").astype(Categorical)

    def test_astype_categoricaldtype(self):
        ser = Series(["a", "b", "a"])
        result = ser.astype(CategoricalDtype(["a", "b"], ordered=True))
        expected = Series(Categorical(["a", "b", "a"], ordered=True))
        tm.assert_series_equal(result, expected)

        result = ser.astype(CategoricalDtype(["a", "b"], ordered=False))
        expected = Series(Categorical(["a", "b", "a"], ordered=False))
        tm.assert_series_equal(result, expected)

        result = ser.astype(CategoricalDtype(["a", "b", "c"], ordered=False))
        expected = Series(
            Categorical(["a", "b", "a"], categories=["a", "b", "c"], ordered=False)
        )
        tm.assert_series_equal(result, expected)
        tm.assert_index_equal(result.cat.categories, Index(["a", "b", "c"]))

    @pytest.mark.parametrize("name", [None, "foo"])
    @pytest.mark.parametrize("dtype_ordered", [True, False])
    @pytest.mark.parametrize("series_ordered", [True, False])
    def test_astype_categorical_to_categorical(
        self, name, dtype_ordered, series_ordered
    ):
        # GH#10696, GH#18593
        s_data = list("abcaacbab")
        s_dtype = CategoricalDtype(list("bac"), ordered=series_ordered)
        ser = Series(s_data, dtype=s_dtype, name=name)

        # unspecified categories
        dtype = CategoricalDtype(ordered=dtype_ordered)
        result = ser.astype(dtype)
        exp_dtype = CategoricalDtype(s_dtype.categories, dtype_ordered)
        expected = Series(s_data, name=name, dtype=exp_dtype)
        tm.assert_series_equal(result, expected)

        # different categories
        dtype = CategoricalDtype(list("adc"), dtype_ordered)
        result = ser.astype(dtype)
        expected = Series(s_data, name=name, dtype=dtype)
        tm.assert_series_equal(result, expected)

        if dtype_ordered is False:
            # not specifying ordered, so only test once
            expected = ser
            result = ser.astype("category")
            tm.assert_series_equal(result, expected)

    def test_astype_bool_missing_to_categorical(self):
        # GH-19182
        ser = Series([True, False, np.nan])
        assert ser.dtypes == np.object_

        result = ser.astype(CategoricalDtype(categories=[True, False]))
        expected = Series(Categorical([True, False, np.nan], categories=[True, False]))
        tm.assert_series_equal(result, expected)

    def test_astype_categories_raises(self):
        # deprecated GH#17636, removed in GH#27141
        ser = Series(["a", "b", "a"])
        with pytest.raises(TypeError, match="got an unexpected"):
            ser.astype("category", categories=["a", "b"], ordered=True)

    @pytest.mark.parametrize("items", [["a", "b", "c", "a"], [1, 2, 3, 1]])
    def test_astype_from_categorical(self, items):
        ser = Series(items)
        exp = Series(Categorical(items))
        res = ser.astype("category")
        tm.assert_series_equal(res, exp)

    def test_astype_from_categorical_with_keywords(self):
        # with keywords
        lst = ["a", "b", "c", "a"]
        ser = Series(lst)
        exp = Series(Categorical(lst, ordered=True))
        res = ser.astype(CategoricalDtype(None, ordered=True))
        tm.assert_series_equal(res, exp)

        exp = Series(Categorical(lst, categories=list("abcdef"), ordered=True))
        res = ser.astype(CategoricalDtype(list("abcdef"), ordered=True))
        tm.assert_series_equal(res, exp)

    def test_astype_timedelta64_with_np_nan(self):
        # GH45798
        result = Series([Timedelta(1), np.nan], dtype="timedelta64[ns]")
        expected = Series([Timedelta(1), NaT], dtype="timedelta64[ns]")
        tm.assert_series_equal(result, expected)

    @td.skip_if_no("pyarrow")
    def test_astype_int_na_string(self):
        # GH#57418
        ser = Series([12, NA], dtype="Int64[pyarrow]")
        result = ser.astype("string[pyarrow]")
        expected = Series(["12", NA], dtype="string[pyarrow]")
        tm.assert_series_equal(result, expected)
