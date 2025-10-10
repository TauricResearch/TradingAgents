import re

import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays import IntervalArray


class TestSeriesReplace:
    def test_replace_explicit_none(self):
        # GH#36984 if the user explicitly passes value=None, give it to them
        ser = pd.Series([0, 0, ""], dtype=object)
        result = ser.replace("", None)
        expected = pd.Series([0, 0, None], dtype=object)
        tm.assert_series_equal(result, expected)

        # Cast column 2 to object to avoid implicit cast when setting entry to ""
        df = pd.DataFrame(np.zeros((3, 3))).astype({2: object})
        df.iloc[2, 2] = ""
        result = df.replace("", None)
        expected = pd.DataFrame(
            {
                0: np.zeros(3),
                1: np.zeros(3),
                2: np.array([0.0, 0.0, None], dtype=object),
            }
        )
        assert expected.iloc[2, 2] is None
        tm.assert_frame_equal(result, expected)

        # GH#19998 same thing with object dtype
        ser = pd.Series([10, 20, 30, "a", "a", "b", "a"])
        result = ser.replace("a", None)
        expected = pd.Series([10, 20, 30, None, None, "b", None])
        assert expected.iloc[-1] is None
        tm.assert_series_equal(result, expected)

    def test_replace_noop_doesnt_downcast(self):
        # GH#44498
        ser = pd.Series([None, None, pd.Timestamp("2021-12-16 17:31")], dtype=object)
        res = ser.replace({np.nan: None})  # should be a no-op
        tm.assert_series_equal(res, ser)
        assert res.dtype == object

        # same thing but different calling convention
        res = ser.replace(np.nan, None)
        tm.assert_series_equal(res, ser)
        assert res.dtype == object

    def test_replace(self):
        N = 50
        ser = pd.Series(np.random.default_rng(2).standard_normal(N))
        ser[0:4] = np.nan
        ser[6:10] = 0

        # replace list with a single value
        return_value = ser.replace([np.nan], -1, inplace=True)
        assert return_value is None

        exp = ser.fillna(-1)
        tm.assert_series_equal(ser, exp)

        rs = ser.replace(0.0, np.nan)
        ser[ser == 0.0] = np.nan
        tm.assert_series_equal(rs, ser)

        ser = pd.Series(
            np.fabs(np.random.default_rng(2).standard_normal(N)),
            pd.date_range("2020-01-01", periods=N),
            dtype=object,
        )
        ser[:5] = np.nan
        ser[6:10] = "foo"
        ser[20:30] = "bar"

        # replace list with a single value
        msg = "Downcasting behavior in `replace`"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs = ser.replace([np.nan, "foo", "bar"], -1)

        assert (rs[:5] == -1).all()
        assert (rs[6:10] == -1).all()
        assert (rs[20:30] == -1).all()
        assert (pd.isna(ser[:5])).all()

        # replace with different values
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs = ser.replace({np.nan: -1, "foo": -2, "bar": -3})

        assert (rs[:5] == -1).all()
        assert (rs[6:10] == -2).all()
        assert (rs[20:30] == -3).all()
        assert (pd.isna(ser[:5])).all()

        # replace with different values with 2 lists
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs2 = ser.replace([np.nan, "foo", "bar"], [-1, -2, -3])
        tm.assert_series_equal(rs, rs2)

        # replace inplace
        with tm.assert_produces_warning(FutureWarning, match=msg):
            return_value = ser.replace([np.nan, "foo", "bar"], -1, inplace=True)
        assert return_value is None

        assert (ser[:5] == -1).all()
        assert (ser[6:10] == -1).all()
        assert (ser[20:30] == -1).all()

    def test_replace_nan_with_inf(self):
        ser = pd.Series([np.nan, 0, np.inf])
        tm.assert_series_equal(ser.replace(np.nan, 0), ser.fillna(0))

        ser = pd.Series([np.nan, 0, "foo", "bar", np.inf, None, pd.NaT])
        tm.assert_series_equal(ser.replace(np.nan, 0), ser.fillna(0))
        filled = ser.copy()
        filled[4] = 0
        tm.assert_series_equal(ser.replace(np.inf, 0), filled)

    def test_replace_listlike_value_listlike_target(self, datetime_series):
        ser = pd.Series(datetime_series.index)
        tm.assert_series_equal(ser.replace(np.nan, 0), ser.fillna(0))

        # malformed
        msg = r"Replacement lists must match in length\. Expecting 3 got 2"
        with pytest.raises(ValueError, match=msg):
            ser.replace([1, 2, 3], [np.nan, 0])

        # ser is dt64 so can't hold 1 or 2, so this replace is a no-op
        result = ser.replace([1, 2], [np.nan, 0])
        tm.assert_series_equal(result, ser)

        ser = pd.Series([0, 1, 2, 3, 4])
        result = ser.replace([0, 1, 2, 3, 4], [4, 3, 2, 1, 0])
        tm.assert_series_equal(result, pd.Series([4, 3, 2, 1, 0]))

    def test_replace_gh5319(self):
        # API change from 0.12?
        # GH 5319
        ser = pd.Series([0, np.nan, 2, 3, 4])
        expected = ser.ffill()
        msg = (
            "Series.replace without 'value' and with non-dict-like "
            "'to_replace' is deprecated"
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = ser.replace([np.nan])
        tm.assert_series_equal(result, expected)

        ser = pd.Series([0, np.nan, 2, 3, 4])
        expected = ser.ffill()
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = ser.replace(np.nan)
        tm.assert_series_equal(result, expected)

    def test_replace_datetime64(self):
        # GH 5797
        ser = pd.Series(pd.date_range("20130101", periods=5))
        expected = ser.copy()
        expected.loc[2] = pd.Timestamp("20120101")
        result = ser.replace({pd.Timestamp("20130103"): pd.Timestamp("20120101")})
        tm.assert_series_equal(result, expected)
        result = ser.replace(pd.Timestamp("20130103"), pd.Timestamp("20120101"))
        tm.assert_series_equal(result, expected)

    def test_replace_nat_with_tz(self):
        # GH 11792: Test with replacing NaT in a list with tz data
        ts = pd.Timestamp("2015/01/01", tz="UTC")
        s = pd.Series([pd.NaT, pd.Timestamp("2015/01/01", tz="UTC")])
        result = s.replace([np.nan, pd.NaT], pd.Timestamp.min)
        expected = pd.Series([pd.Timestamp.min, ts], dtype=object)
        tm.assert_series_equal(expected, result)

    def test_replace_timedelta_td64(self):
        tdi = pd.timedelta_range(0, periods=5)
        ser = pd.Series(tdi)

        # Using a single dict argument means we go through replace_list
        result = ser.replace({ser[1]: ser[3]})

        expected = pd.Series([ser[0], ser[3], ser[2], ser[3], ser[4]])
        tm.assert_series_equal(result, expected)

    def test_replace_with_single_list(self):
        ser = pd.Series([0, 1, 2, 3, 4])
        msg2 = (
            "Series.replace without 'value' and with non-dict-like "
            "'to_replace' is deprecated"
        )
        with tm.assert_produces_warning(FutureWarning, match=msg2):
            result = ser.replace([1, 2, 3])
        tm.assert_series_equal(result, pd.Series([0, 0, 0, 0, 4]))

        s = ser.copy()
        with tm.assert_produces_warning(FutureWarning, match=msg2):
            return_value = s.replace([1, 2, 3], inplace=True)
        assert return_value is None
        tm.assert_series_equal(s, pd.Series([0, 0, 0, 0, 4]))

        # make sure things don't get corrupted when fillna call fails
        s = ser.copy()
        msg = (
            r"Invalid fill method\. Expecting pad \(ffill\) or backfill "
            r"\(bfill\)\. Got crash_cymbal"
        )
        msg3 = "The 'method' keyword in Series.replace is deprecated"
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=msg3):
                return_value = s.replace([1, 2, 3], inplace=True, method="crash_cymbal")
            assert return_value is None
        tm.assert_series_equal(s, ser)

    def test_replace_mixed_types(self):
        ser = pd.Series(np.arange(5), dtype="int64")

        def check_replace(to_rep, val, expected):
            sc = ser.copy()
            result = ser.replace(to_rep, val)
            return_value = sc.replace(to_rep, val, inplace=True)
            assert return_value is None
            tm.assert_series_equal(expected, result)
            tm.assert_series_equal(expected, sc)

        # 3.0 can still be held in our int64 series, so we do not upcast GH#44940
        tr, v = [3], [3.0]
        check_replace(tr, v, ser)
        # Note this matches what we get with the scalars 3 and 3.0
        check_replace(tr[0], v[0], ser)

        # MUST upcast to float
        e = pd.Series([0, 1, 2, 3.5, 4])
        tr, v = [3], [3.5]
        check_replace(tr, v, e)

        # casts to object
        e = pd.Series([0, 1, 2, 3.5, "a"])
        tr, v = [3, 4], [3.5, "a"]
        check_replace(tr, v, e)

        # again casts to object
        e = pd.Series([0, 1, 2, 3.5, pd.Timestamp("20130101")])
        tr, v = [3, 4], [3.5, pd.Timestamp("20130101")]
        check_replace(tr, v, e)

        # casts to object
        e = pd.Series([0, 1, 2, 3.5, True], dtype="object")
        tr, v = [3, 4], [3.5, True]
        check_replace(tr, v, e)

        # test an object with dates + floats + integers + strings
        dr = pd.Series(pd.date_range("1/1/2001", "1/10/2001", freq="D"))
        result = dr.astype(object).replace([dr[0], dr[1], dr[2]], [1.0, 2, "a"])
        expected = pd.Series([1.0, 2, "a"] + dr[3:].tolist(), dtype=object)
        tm.assert_series_equal(result, expected)

    def test_replace_bool_with_string_no_op(self):
        s = pd.Series([True, False, True])
        result = s.replace("fun", "in-the-sun")
        tm.assert_series_equal(s, result)

    def test_replace_bool_with_string(self):
        # nonexistent elements
        s = pd.Series([True, False, True])
        result = s.replace(True, "2u")
        expected = pd.Series(["2u", False, "2u"])
        tm.assert_series_equal(expected, result)

    def test_replace_bool_with_bool(self):
        s = pd.Series([True, False, True])
        result = s.replace(True, False)
        expected = pd.Series([False] * len(s))
        tm.assert_series_equal(expected, result)

    def test_replace_with_dict_with_bool_keys(self):
        s = pd.Series([True, False, True])
        result = s.replace({"asdf": "asdb", True: "yes"})
        expected = pd.Series(["yes", False, "yes"])
        tm.assert_series_equal(result, expected)

    def test_replace_Int_with_na(self, any_int_ea_dtype):
        # GH 38267
        result = pd.Series([0, None], dtype=any_int_ea_dtype).replace(0, pd.NA)
        expected = pd.Series([pd.NA, pd.NA], dtype=any_int_ea_dtype)
        tm.assert_series_equal(result, expected)
        result = pd.Series([0, 1], dtype=any_int_ea_dtype).replace(0, pd.NA)
        result.replace(1, pd.NA, inplace=True)
        tm.assert_series_equal(result, expected)

    def test_replace2(self):
        N = 50
        ser = pd.Series(
            np.fabs(np.random.default_rng(2).standard_normal(N)),
            pd.date_range("2020-01-01", periods=N),
            dtype=object,
        )
        ser[:5] = np.nan
        ser[6:10] = "foo"
        ser[20:30] = "bar"

        # replace list with a single value
        msg = "Downcasting behavior in `replace`"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs = ser.replace([np.nan, "foo", "bar"], -1)

        assert (rs[:5] == -1).all()
        assert (rs[6:10] == -1).all()
        assert (rs[20:30] == -1).all()
        assert (pd.isna(ser[:5])).all()

        # replace with different values
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs = ser.replace({np.nan: -1, "foo": -2, "bar": -3})

        assert (rs[:5] == -1).all()
        assert (rs[6:10] == -2).all()
        assert (rs[20:30] == -3).all()
        assert (pd.isna(ser[:5])).all()

        # replace with different values with 2 lists
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs2 = ser.replace([np.nan, "foo", "bar"], [-1, -2, -3])
        tm.assert_series_equal(rs, rs2)

        # replace inplace
        with tm.assert_produces_warning(FutureWarning, match=msg):
            return_value = ser.replace([np.nan, "foo", "bar"], -1, inplace=True)
        assert return_value is None
        assert (ser[:5] == -1).all()
        assert (ser[6:10] == -1).all()
        assert (ser[20:30] == -1).all()

    @pytest.mark.parametrize("inplace", [True, False])
    def test_replace_cascade(self, inplace):
        # Test that replaced values are not replaced again
        # GH #50778
        ser = pd.Series([1, 2, 3])
        expected = pd.Series([2, 3, 4])

        res = ser.replace([1, 2, 3], [2, 3, 4], inplace=inplace)
        if inplace:
            tm.assert_series_equal(ser, expected)
        else:
            tm.assert_series_equal(res, expected)

    def test_replace_with_dictlike_and_string_dtype(self, nullable_string_dtype):
        # GH 32621, GH#44940
        ser = pd.Series(["one", "two", np.nan], dtype=nullable_string_dtype)
        expected = pd.Series(["1", "2", np.nan], dtype=nullable_string_dtype)
        result = ser.replace({"one": "1", "two": "2"})
        tm.assert_series_equal(expected, result)

    def test_replace_with_empty_dictlike(self):
        # GH 15289
        s = pd.Series(list("abcd"))
        tm.assert_series_equal(s, s.replace({}))

        empty_series = pd.Series([])
        tm.assert_series_equal(s, s.replace(empty_series))

    def test_replace_string_with_number(self):
        # GH 15743
        s = pd.Series([1, 2, 3])
        result = s.replace("2", np.nan)
        expected = pd.Series([1, 2, 3])
        tm.assert_series_equal(expected, result)

    def test_replace_replacer_equals_replacement(self):
        # GH 20656
        # make sure all replacers are matching against original values
        s = pd.Series(["a", "b"])
        expected = pd.Series(["b", "a"])
        result = s.replace({"a": "b", "b": "a"})
        tm.assert_series_equal(expected, result)

    def test_replace_unicode_with_number(self):
        # GH 15743
        s = pd.Series([1, 2, 3])
        result = s.replace("2", np.nan)
        expected = pd.Series([1, 2, 3])
        tm.assert_series_equal(expected, result)

    def test_replace_mixed_types_with_string(self):
        # Testing mixed
        s = pd.Series([1, 2, 3, "4", 4, 5])
        msg = "Downcasting behavior in `replace`"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = s.replace([2, "4"], np.nan)
        expected = pd.Series([1, np.nan, 3, np.nan, 4, 5])
        tm.assert_series_equal(expected, result)

    @pytest.mark.parametrize(
        "categorical, numeric",
        [
            (pd.Categorical(["A"], categories=["A", "B"]), [1]),
            (pd.Categorical(["A", "B"], categories=["A", "B"]), [1, 2]),
        ],
    )
    def test_replace_categorical(self, categorical, numeric, using_infer_string):
        # GH 24971, GH#23305
        ser = pd.Series(categorical)
        msg = "Downcasting behavior in `replace`"
        msg = "with CategoricalDtype is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = ser.replace({"A": 1, "B": 2})
        expected = pd.Series(numeric).astype("category")
        if 2 not in expected.cat.categories:
            # i.e. categories should be [1, 2] even if there are no "B"s present
            # GH#44940
            expected = expected.cat.add_categories(2)
        tm.assert_series_equal(expected, result)

    @pytest.mark.parametrize(
        "data, data_exp", [(["a", "b", "c"], ["b", "b", "c"]), (["a"], ["b"])]
    )
    def test_replace_categorical_inplace(self, data, data_exp):
        # GH 53358
        result = pd.Series(data, dtype="category")
        msg = "with CategoricalDtype is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result.replace(to_replace="a", value="b", inplace=True)
        expected = pd.Series(data_exp, dtype="category")
        tm.assert_series_equal(result, expected)

    def test_replace_categorical_single(self):
        # GH 26988
        dti = pd.date_range("2016-01-01", periods=3, tz="US/Pacific")
        s = pd.Series(dti)
        c = s.astype("category")

        expected = c.copy()
        expected = expected.cat.add_categories("foo")
        expected[2] = "foo"
        expected = expected.cat.remove_unused_categories()
        assert c[2] != "foo"

        msg = "with CategoricalDtype is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = c.replace(c[2], "foo")
        tm.assert_series_equal(expected, result)
        assert c[2] != "foo"  # ensure non-inplace call does not alter original

        msg = "with CategoricalDtype is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            return_value = c.replace(c[2], "foo", inplace=True)
        assert return_value is None
        tm.assert_series_equal(expected, c)

        first_value = c[0]
        msg = "with CategoricalDtype is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            return_value = c.replace(c[1], c[0], inplace=True)
        assert return_value is None
        assert c[0] == c[1] == first_value  # test replacing with existing value

    def test_replace_with_no_overflowerror(self):
        # GH 25616
        # casts to object without Exception from OverflowError
        s = pd.Series([0, 1, 2, 3, 4])
        result = s.replace([3], ["100000000000000000000"])
        expected = pd.Series([0, 1, 2, "100000000000000000000", 4])
        tm.assert_series_equal(result, expected)

        s = pd.Series([0, "100000000000000000000", "100000000000000000001"])
        result = s.replace(["100000000000000000000"], [1])
        expected = pd.Series([0, 1, "100000000000000000001"])
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "ser, to_replace, exp",
        [
            ([1, 2, 3], {1: 2, 2: 3, 3: 4}, [2, 3, 4]),
            (["1", "2", "3"], {"1": "2", "2": "3", "3": "4"}, ["2", "3", "4"]),
        ],
    )
    def test_replace_commutative(self, ser, to_replace, exp):
        # GH 16051
        # DataFrame.replace() overwrites when values are non-numeric

        series = pd.Series(ser)

        expected = pd.Series(exp)
        result = series.replace(to_replace)

        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "ser, exp", [([1, 2, 3], [1, True, 3]), (["x", 2, 3], ["x", True, 3])]
    )
    def test_replace_no_cast(self, ser, exp):
        # GH 9113
        # BUG: replace int64 dtype with bool coerces to int64

        series = pd.Series(ser)
        result = series.replace(2, True)
        expected = pd.Series(exp)

        tm.assert_series_equal(result, expected)

    def test_replace_invalid_to_replace(self):
        # GH 18634
        # API: replace() should raise an exception if invalid argument is given
        series = pd.Series(["a", "b", "c "])
        msg = (
            r"Expecting 'to_replace' to be either a scalar, array-like, "
            r"dict or None, got invalid type.*"
        )
        msg2 = (
            "Series.replace without 'value' and with non-dict-like "
            "'to_replace' is deprecated"
        )
        with pytest.raises(TypeError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=msg2):
                series.replace(lambda x: x.strip())

    @pytest.mark.parametrize("frame", [False, True])
    def test_replace_nonbool_regex(self, frame):
        obj = pd.Series(["a", "b", "c "])
        if frame:
            obj = obj.to_frame()

        msg = "'to_replace' must be 'None' if 'regex' is not a bool"
        with pytest.raises(ValueError, match=msg):
            obj.replace(to_replace=["a"], regex="foo")

    @pytest.mark.parametrize("frame", [False, True])
    def test_replace_empty_copy(self, frame):
        obj = pd.Series([], dtype=np.float64)
        if frame:
            obj = obj.to_frame()

        res = obj.replace(4, 5, inplace=True)
        assert res is None

        res = obj.replace(4, 5, inplace=False)
        tm.assert_equal(res, obj)
        assert res is not obj

    def test_replace_only_one_dictlike_arg(self, fixed_now_ts):
        # GH#33340

        ser = pd.Series([1, 2, "A", fixed_now_ts, True])
        to_replace = {0: 1, 2: "A"}
        value = "foo"
        msg = "Series.replace cannot use dict-like to_replace and non-None value"
        with pytest.raises(ValueError, match=msg):
            ser.replace(to_replace, value)

        to_replace = 1
        value = {0: "foo", 2: "bar"}
        msg = "Series.replace cannot use dict-value and non-None to_replace"
        with pytest.raises(ValueError, match=msg):
            ser.replace(to_replace, value)

    def test_replace_extension_other(self, frame_or_series):
        # https://github.com/pandas-dev/pandas/issues/34530
        obj = frame_or_series(pd.array([1, 2, 3], dtype="Int64"))
        result = obj.replace("", "")  # no exception
        # should not have changed dtype
        tm.assert_equal(obj, result)

    def _check_replace_with_method(self, ser: pd.Series):
        df = ser.to_frame()

        msg1 = "The 'method' keyword in Series.replace is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg1):
            res = ser.replace(ser[1], method="pad")
        expected = pd.Series([ser[0], ser[0]] + list(ser[2:]), dtype=ser.dtype)
        tm.assert_series_equal(res, expected)

        msg2 = "The 'method' keyword in DataFrame.replace is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg2):
            res_df = df.replace(ser[1], method="pad")
        tm.assert_frame_equal(res_df, expected.to_frame())

        ser2 = ser.copy()
        with tm.assert_produces_warning(FutureWarning, match=msg1):
            res2 = ser2.replace(ser[1], method="pad", inplace=True)
        assert res2 is None
        tm.assert_series_equal(ser2, expected)

        with tm.assert_produces_warning(FutureWarning, match=msg2):
            res_df2 = df.replace(ser[1], method="pad", inplace=True)
        assert res_df2 is None
        tm.assert_frame_equal(df, expected.to_frame())

    def test_replace_ea_dtype_with_method(self, any_numeric_ea_dtype):
        arr = pd.array([1, 2, pd.NA, 4], dtype=any_numeric_ea_dtype)
        ser = pd.Series(arr)

        self._check_replace_with_method(ser)

    @pytest.mark.parametrize("as_categorical", [True, False])
    def test_replace_interval_with_method(self, as_categorical):
        # in particular interval that can't hold NA

        idx = pd.IntervalIndex.from_breaks(range(4))
        ser = pd.Series(idx)
        if as_categorical:
            ser = ser.astype("category")

        self._check_replace_with_method(ser)

    @pytest.mark.parametrize("as_period", [True, False])
    @pytest.mark.parametrize("as_categorical", [True, False])
    def test_replace_datetimelike_with_method(self, as_period, as_categorical):
        idx = pd.date_range("2016-01-01", periods=5, tz="US/Pacific")
        if as_period:
            idx = idx.tz_localize(None).to_period("D")

        ser = pd.Series(idx)
        ser.iloc[-2] = pd.NaT
        if as_categorical:
            ser = ser.astype("category")

        self._check_replace_with_method(ser)

    def test_replace_with_compiled_regex(self):
        # https://github.com/pandas-dev/pandas/issues/35680
        s = pd.Series(["a", "b", "c"])
        regex = re.compile("^a$")
        result = s.replace({regex: "z"}, regex=True)
        expected = pd.Series(["z", "b", "c"])
        tm.assert_series_equal(result, expected)

    def test_pandas_replace_na(self):
        # GH#43344
        # GH#56599
        ser = pd.Series(["AA", "BB", "CC", "DD", "EE", "", pd.NA, "AA"], dtype="string")
        regex_mapping = {
            "AA": "CC",
            "BB": "CC",
            "EE": "CC",
            "CC": "CC-REPL",
        }
        result = ser.replace(regex_mapping, regex=True)
        exp = pd.Series(
            ["CC", "CC", "CC-REPL", "DD", "CC", "", pd.NA, "CC"], dtype="string"
        )
        tm.assert_series_equal(result, exp)

    @pytest.mark.parametrize(
        "dtype, input_data, to_replace, expected_data",
        [
            ("bool", [True, False], {True: False}, [False, False]),
            ("int64", [1, 2], {1: 10, 2: 20}, [10, 20]),
            ("Int64", [1, 2], {1: 10, 2: 20}, [10, 20]),
            ("float64", [1.1, 2.2], {1.1: 10.1, 2.2: 20.5}, [10.1, 20.5]),
            ("Float64", [1.1, 2.2], {1.1: 10.1, 2.2: 20.5}, [10.1, 20.5]),
            ("string", ["one", "two"], {"one": "1", "two": "2"}, ["1", "2"]),
            (
                pd.IntervalDtype("int64"),
                IntervalArray([pd.Interval(1, 2), pd.Interval(2, 3)]),
                {pd.Interval(1, 2): pd.Interval(10, 20)},
                IntervalArray([pd.Interval(10, 20), pd.Interval(2, 3)]),
            ),
            (
                pd.IntervalDtype("float64"),
                IntervalArray([pd.Interval(1.0, 2.7), pd.Interval(2.8, 3.1)]),
                {pd.Interval(1.0, 2.7): pd.Interval(10.6, 20.8)},
                IntervalArray([pd.Interval(10.6, 20.8), pd.Interval(2.8, 3.1)]),
            ),
            (
                pd.PeriodDtype("M"),
                [pd.Period("2020-05", freq="M")],
                {pd.Period("2020-05", freq="M"): pd.Period("2020-06", freq="M")},
                [pd.Period("2020-06", freq="M")],
            ),
        ],
    )
    def test_replace_dtype(self, dtype, input_data, to_replace, expected_data):
        # GH#33484
        ser = pd.Series(input_data, dtype=dtype)
        result = ser.replace(to_replace)
        expected = pd.Series(expected_data, dtype=dtype)
        tm.assert_series_equal(result, expected)

    def test_replace_string_dtype(self):
        # GH#40732, GH#44940
        ser = pd.Series(["one", "two", np.nan], dtype="string")
        res = ser.replace({"one": "1", "two": "2"})
        expected = pd.Series(["1", "2", np.nan], dtype="string")
        tm.assert_series_equal(res, expected)

        # GH#31644
        ser2 = pd.Series(["A", np.nan], dtype="string")
        res2 = ser2.replace("A", "B")
        expected2 = pd.Series(["B", np.nan], dtype="string")
        tm.assert_series_equal(res2, expected2)

        ser3 = pd.Series(["A", "B"], dtype="string")
        res3 = ser3.replace("A", pd.NA)
        expected3 = pd.Series([pd.NA, "B"], dtype="string")
        tm.assert_series_equal(res3, expected3)

    def test_replace_string_dtype_list_to_replace(self):
        # GH#41215, GH#44940
        ser = pd.Series(["abc", "def"], dtype="string")
        res = ser.replace(["abc", "any other string"], "xyz")
        expected = pd.Series(["xyz", "def"], dtype="string")
        tm.assert_series_equal(res, expected)

    def test_replace_string_dtype_regex(self):
        # GH#31644
        ser = pd.Series(["A", "B"], dtype="string")
        res = ser.replace(r".", "C", regex=True)
        expected = pd.Series(["C", "C"], dtype="string")
        tm.assert_series_equal(res, expected)

    def test_replace_nullable_numeric(self):
        # GH#40732, GH#44940

        floats = pd.Series([1.0, 2.0, 3.999, 4.4], dtype=pd.Float64Dtype())
        assert floats.replace({1.0: 9}).dtype == floats.dtype
        assert floats.replace(1.0, 9).dtype == floats.dtype
        assert floats.replace({1.0: 9.0}).dtype == floats.dtype
        assert floats.replace(1.0, 9.0).dtype == floats.dtype

        res = floats.replace(to_replace=[1.0, 2.0], value=[9.0, 10.0])
        assert res.dtype == floats.dtype

        ints = pd.Series([1, 2, 3, 4], dtype=pd.Int64Dtype())
        assert ints.replace({1: 9}).dtype == ints.dtype
        assert ints.replace(1, 9).dtype == ints.dtype
        assert ints.replace({1: 9.0}).dtype == ints.dtype
        assert ints.replace(1, 9.0).dtype == ints.dtype

        # nullable (for now) raises instead of casting
        with pytest.raises(TypeError, match="Invalid value"):
            ints.replace({1: 9.5})
        with pytest.raises(TypeError, match="Invalid value"):
            ints.replace(1, 9.5)

    @pytest.mark.parametrize("regex", [False, True])
    def test_replace_regex_dtype_series(self, regex):
        # GH-48644
        series = pd.Series(["0"], dtype=object)
        expected = pd.Series([1])
        msg = "Downcasting behavior in `replace`"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = series.replace(to_replace="0", value=1, regex=regex)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("regex", [False, True])
    def test_replace_regex_dtype_series_string(self, regex):
        series = pd.Series(["0"], dtype="str")
        expected = pd.Series([1], dtype="int64")
        msg = "Downcasting behavior in `replace`"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = series.replace(to_replace="0", value=1, regex=regex)
        tm.assert_series_equal(result, expected)

    def test_replace_different_int_types(self, any_int_numpy_dtype):
        # GH#45311
        labs = pd.Series([1, 1, 1, 0, 0, 2, 2, 2], dtype=any_int_numpy_dtype)

        maps = pd.Series([0, 2, 1], dtype=any_int_numpy_dtype)
        map_dict = dict(zip(maps.values, maps.index))

        result = labs.replace(map_dict)
        expected = labs.replace({0: 0, 2: 1, 1: 2})
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("val", [2, np.nan, 2.0])
    def test_replace_value_none_dtype_numeric(self, val):
        # GH#48231
        ser = pd.Series([1, val])
        result = ser.replace(val, None)
        expected = pd.Series([1, None], dtype=object)
        tm.assert_series_equal(result, expected)

    def test_replace_change_dtype_series(self):
        # GH#25797
        df = pd.DataFrame({"Test": ["0.5", True, "0.6"]}, dtype=object)
        df["Test"] = df["Test"].replace([True], [np.nan])
        expected = pd.DataFrame({"Test": ["0.5", np.nan, "0.6"]}, dtype=object)
        tm.assert_frame_equal(df, expected)

        df = pd.DataFrame({"Test": ["0.5", None, "0.6"]}, dtype=object)
        df["Test"] = df["Test"].replace([None], [np.nan])
        tm.assert_frame_equal(df, expected)

        df = pd.DataFrame({"Test": ["0.5", None, "0.6"]}, dtype=object)
        df["Test"] = df["Test"].fillna(np.nan)
        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize("dtype", ["object", "Int64"])
    def test_replace_na_in_obj_column(self, dtype):
        # GH#47480
        ser = pd.Series([0, 1, pd.NA], dtype=dtype)
        expected = pd.Series([0, 2, pd.NA], dtype=dtype)
        result = ser.replace(to_replace=1, value=2)
        tm.assert_series_equal(result, expected)

        ser.replace(to_replace=1, value=2, inplace=True)
        tm.assert_series_equal(ser, expected)

    @pytest.mark.parametrize("val", [0, 0.5])
    def test_replace_numeric_column_with_na(self, val):
        # GH#50758
        ser = pd.Series([val, 1])
        expected = pd.Series([val, pd.NA])
        result = ser.replace(to_replace=1, value=pd.NA)
        tm.assert_series_equal(result, expected)

        ser.replace(to_replace=1, value=pd.NA, inplace=True)
        tm.assert_series_equal(ser, expected)

    def test_replace_ea_float_with_bool(self):
        # GH#55398
        ser = pd.Series([0.0], dtype="Float64")
        expected = ser.copy()
        result = ser.replace(False, 1.0)
        tm.assert_series_equal(result, expected)

        ser = pd.Series([False], dtype="boolean")
        expected = ser.copy()
        result = ser.replace(0.0, True)
        tm.assert_series_equal(result, expected)
