import numpy as np
import pytest

import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    CategoricalIndex,
    DataFrame,
    Index,
    NaT,
    Series,
    date_range,
    offsets,
)
import pandas._testing as tm


class TestDataFrameShift:
    def test_shift_axis1_with_valid_fill_value_one_array(self):
        # Case with axis=1 that does not go through the "len(arrays)>1" path
        #  in DataFrame.shift
        data = np.random.default_rng(2).standard_normal((5, 3))
        df = DataFrame(data)
        res = df.shift(axis=1, periods=1, fill_value=12345)
        expected = df.T.shift(periods=1, fill_value=12345).T
        tm.assert_frame_equal(res, expected)

        # same but with an 1D ExtensionArray backing it
        df2 = df[[0]].astype("Float64")
        res2 = df2.shift(axis=1, periods=1, fill_value=12345)
        expected2 = DataFrame([12345] * 5, dtype="Float64")
        tm.assert_frame_equal(res2, expected2)

    def test_shift_deprecate_freq_and_fill_value(self, frame_or_series):
        # Can't pass both!
        obj = frame_or_series(
            np.random.default_rng(2).standard_normal(5),
            index=date_range("1/1/2000", periods=5, freq="h"),
        )

        msg = (
            "Passing a 'freq' together with a 'fill_value' silently ignores the "
            "fill_value"
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            obj.shift(1, fill_value=1, freq="h")

        if frame_or_series is DataFrame:
            obj.columns = date_range("1/1/2000", periods=1, freq="h")
            with tm.assert_produces_warning(FutureWarning, match=msg):
                obj.shift(1, axis=1, fill_value=1, freq="h")

    @pytest.mark.parametrize(
        "input_data, output_data",
        [(np.empty(shape=(0,)), []), (np.ones(shape=(2,)), [np.nan, 1.0])],
    )
    def test_shift_non_writable_array(self, input_data, output_data, frame_or_series):
        # GH21049 Verify whether non writable numpy array is shiftable
        input_data.setflags(write=False)

        result = frame_or_series(input_data).shift(1)
        if frame_or_series is not Series:
            # need to explicitly specify columns in the empty case
            expected = frame_or_series(
                output_data,
                index=range(len(output_data)),
                columns=range(1),
                dtype="float64",
            )
        else:
            expected = frame_or_series(output_data, dtype="float64")

        tm.assert_equal(result, expected)

    def test_shift_mismatched_freq(self, frame_or_series):
        ts = frame_or_series(
            np.random.default_rng(2).standard_normal(5),
            index=date_range("1/1/2000", periods=5, freq="h"),
        )

        result = ts.shift(1, freq="5min")
        exp_index = ts.index.shift(1, freq="5min")
        tm.assert_index_equal(result.index, exp_index)

        # GH#1063, multiple of same base
        result = ts.shift(1, freq="4h")
        exp_index = ts.index + offsets.Hour(4)
        tm.assert_index_equal(result.index, exp_index)

    @pytest.mark.parametrize(
        "obj",
        [
            Series([np.arange(5)]),
            date_range("1/1/2011", periods=24, freq="h"),
            Series(range(5), index=date_range("2017", periods=5)),
        ],
    )
    @pytest.mark.parametrize("shift_size", [0, 1, 2])
    def test_shift_always_copy(self, obj, shift_size, frame_or_series):
        # GH#22397
        if frame_or_series is not Series:
            obj = obj.to_frame()
        assert obj.shift(shift_size) is not obj

    def test_shift_object_non_scalar_fill(self):
        # shift requires scalar fill_value except for object dtype
        ser = Series(range(3))
        with pytest.raises(ValueError, match="fill_value must be a scalar"):
            ser.shift(1, fill_value=[])

        df = ser.to_frame()
        with pytest.raises(ValueError, match="fill_value must be a scalar"):
            df.shift(1, fill_value=np.arange(3))

        obj_ser = ser.astype(object)
        result = obj_ser.shift(1, fill_value={})
        assert result[0] == {}

        obj_df = obj_ser.to_frame()
        result = obj_df.shift(1, fill_value={})
        assert result.iloc[0, 0] == {}

    def test_shift_int(self, datetime_frame, frame_or_series):
        ts = tm.get_obj(datetime_frame, frame_or_series).astype(int)
        shifted = ts.shift(1)
        expected = ts.astype(float).shift(1)
        tm.assert_equal(shifted, expected)

    @pytest.mark.parametrize("dtype", ["int32", "int64"])
    def test_shift_32bit_take(self, frame_or_series, dtype):
        # 32-bit taking
        # GH#8129
        index = date_range("2000-01-01", periods=5)
        arr = np.arange(5, dtype=dtype)
        s1 = frame_or_series(arr, index=index)
        p = arr[1]
        result = s1.shift(periods=p)
        expected = frame_or_series([np.nan, 0, 1, 2, 3], index=index)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize("periods", [1, 2, 3, 4])
    def test_shift_preserve_freqstr(self, periods, frame_or_series):
        # GH#21275
        obj = frame_or_series(
            range(periods),
            index=date_range("2016-1-1 00:00:00", periods=periods, freq="h"),
        )

        result = obj.shift(1, "2h")

        expected = frame_or_series(
            range(periods),
            index=date_range("2016-1-1 02:00:00", periods=periods, freq="h"),
        )
        tm.assert_equal(result, expected)

    def test_shift_dst(self, frame_or_series):
        # GH#13926
        dates = date_range("2016-11-06", freq="h", periods=10, tz="US/Eastern")
        obj = frame_or_series(dates)

        res = obj.shift(0)
        tm.assert_equal(res, obj)
        assert tm.get_dtype(res) == "datetime64[ns, US/Eastern]"

        res = obj.shift(1)
        exp_vals = [NaT] + dates.astype(object).values.tolist()[:9]
        exp = frame_or_series(exp_vals)
        tm.assert_equal(res, exp)
        assert tm.get_dtype(res) == "datetime64[ns, US/Eastern]"

        res = obj.shift(-2)
        exp_vals = dates.astype(object).values.tolist()[2:] + [NaT, NaT]
        exp = frame_or_series(exp_vals)
        tm.assert_equal(res, exp)
        assert tm.get_dtype(res) == "datetime64[ns, US/Eastern]"

    @pytest.mark.parametrize("ex", [10, -10, 20, -20])
    def test_shift_dst_beyond(self, frame_or_series, ex):
        # GH#13926
        dates = date_range("2016-11-06", freq="h", periods=10, tz="US/Eastern")
        obj = frame_or_series(dates)
        res = obj.shift(ex)
        exp = frame_or_series([NaT] * 10, dtype="datetime64[ns, US/Eastern]")
        tm.assert_equal(res, exp)
        assert tm.get_dtype(res) == "datetime64[ns, US/Eastern]"

    def test_shift_by_zero(self, datetime_frame, frame_or_series):
        # shift by 0
        obj = tm.get_obj(datetime_frame, frame_or_series)
        unshifted = obj.shift(0)
        tm.assert_equal(unshifted, obj)

    def test_shift(self, datetime_frame):
        # naive shift
        ser = datetime_frame["A"]

        shifted = datetime_frame.shift(5)
        tm.assert_index_equal(shifted.index, datetime_frame.index)

        shifted_ser = ser.shift(5)
        tm.assert_series_equal(shifted["A"], shifted_ser)

        shifted = datetime_frame.shift(-5)
        tm.assert_index_equal(shifted.index, datetime_frame.index)

        shifted_ser = ser.shift(-5)
        tm.assert_series_equal(shifted["A"], shifted_ser)

        unshifted = datetime_frame.shift(5).shift(-5)
        tm.assert_numpy_array_equal(
            unshifted.dropna().values, datetime_frame.values[:-5]
        )

        unshifted_ser = ser.shift(5).shift(-5)
        tm.assert_numpy_array_equal(unshifted_ser.dropna().values, ser.values[:-5])

    def test_shift_by_offset(self, datetime_frame, frame_or_series):
        # shift by DateOffset
        obj = tm.get_obj(datetime_frame, frame_or_series)
        offset = offsets.BDay()

        shifted = obj.shift(5, freq=offset)
        assert len(shifted) == len(obj)
        unshifted = shifted.shift(-5, freq=offset)
        tm.assert_equal(unshifted, obj)

        shifted2 = obj.shift(5, freq="B")
        tm.assert_equal(shifted, shifted2)

        unshifted = obj.shift(0, freq=offset)
        tm.assert_equal(unshifted, obj)

        d = obj.index[0]
        shifted_d = d + offset * 5
        if frame_or_series is DataFrame:
            tm.assert_series_equal(obj.xs(d), shifted.xs(shifted_d), check_names=False)
        else:
            tm.assert_almost_equal(obj.at[d], shifted.at[shifted_d])

    def test_shift_with_periodindex(self, frame_or_series):
        # Shifting with PeriodIndex
        ps = DataFrame(
            np.arange(4, dtype=float), index=pd.period_range("2020-01-01", periods=4)
        )
        ps = tm.get_obj(ps, frame_or_series)

        shifted = ps.shift(1)
        unshifted = shifted.shift(-1)
        tm.assert_index_equal(shifted.index, ps.index)
        tm.assert_index_equal(unshifted.index, ps.index)
        if frame_or_series is DataFrame:
            tm.assert_numpy_array_equal(
                unshifted.iloc[:, 0].dropna().values, ps.iloc[:-1, 0].values
            )
        else:
            tm.assert_numpy_array_equal(unshifted.dropna().values, ps.values[:-1])

        shifted2 = ps.shift(1, "D")
        shifted3 = ps.shift(1, offsets.Day())
        tm.assert_equal(shifted2, shifted3)
        tm.assert_equal(ps, shifted2.shift(-1, "D"))

        msg = "does not match PeriodIndex freq"
        with pytest.raises(ValueError, match=msg):
            ps.shift(freq="W")

        # legacy support
        shifted4 = ps.shift(1, freq="D")
        tm.assert_equal(shifted2, shifted4)

        shifted5 = ps.shift(1, freq=offsets.Day())
        tm.assert_equal(shifted5, shifted4)

    def test_shift_other_axis(self):
        # shift other axis
        # GH#6371
        df = DataFrame(np.random.default_rng(2).random((10, 5)))
        expected = pd.concat(
            [DataFrame(np.nan, index=df.index, columns=[0]), df.iloc[:, 0:-1]],
            ignore_index=True,
            axis=1,
        )
        result = df.shift(1, axis=1)
        tm.assert_frame_equal(result, expected)

    def test_shift_named_axis(self):
        # shift named axis
        df = DataFrame(np.random.default_rng(2).random((10, 5)))
        expected = pd.concat(
            [DataFrame(np.nan, index=df.index, columns=[0]), df.iloc[:, 0:-1]],
            ignore_index=True,
            axis=1,
        )
        result = df.shift(1, axis="columns")
        tm.assert_frame_equal(result, expected)

    def test_shift_other_axis_with_freq(self, datetime_frame):
        obj = datetime_frame.T
        offset = offsets.BDay()

        # GH#47039
        shifted = obj.shift(5, freq=offset, axis=1)
        assert len(shifted) == len(obj)
        unshifted = shifted.shift(-5, freq=offset, axis=1)
        tm.assert_equal(unshifted, obj)

    def test_shift_bool(self):
        df = DataFrame({"high": [True, False], "low": [False, False]})
        rs = df.shift(1)
        xp = DataFrame(
            np.array([[np.nan, np.nan], [True, False]], dtype=object),
            columns=["high", "low"],
        )
        tm.assert_frame_equal(rs, xp)

    def test_shift_categorical1(self, frame_or_series):
        # GH#9416
        obj = frame_or_series(["a", "b", "c", "d"], dtype="category")

        rt = obj.shift(1).shift(-1)
        tm.assert_equal(obj.iloc[:-1], rt.dropna())

        def get_cat_values(ndframe):
            # For Series we could just do ._values; for DataFrame
            #  we may be able to do this if we ever have 2D Categoricals
            return ndframe._mgr.arrays[0]

        cat = get_cat_values(obj)

        sp1 = obj.shift(1)
        tm.assert_index_equal(obj.index, sp1.index)
        assert np.all(get_cat_values(sp1).codes[:1] == -1)
        assert np.all(cat.codes[:-1] == get_cat_values(sp1).codes[1:])

        sn2 = obj.shift(-2)
        tm.assert_index_equal(obj.index, sn2.index)
        assert np.all(get_cat_values(sn2).codes[-2:] == -1)
        assert np.all(cat.codes[2:] == get_cat_values(sn2).codes[:-2])

        tm.assert_index_equal(cat.categories, get_cat_values(sp1).categories)
        tm.assert_index_equal(cat.categories, get_cat_values(sn2).categories)

    def test_shift_categorical(self):
        # GH#9416
        s1 = Series(["a", "b", "c"], dtype="category")
        s2 = Series(["A", "B", "C"], dtype="category")
        df = DataFrame({"one": s1, "two": s2})
        rs = df.shift(1)
        xp = DataFrame({"one": s1.shift(1), "two": s2.shift(1)})
        tm.assert_frame_equal(rs, xp)

    def test_shift_categorical_fill_value(self, frame_or_series):
        ts = frame_or_series(["a", "b", "c", "d"], dtype="category")
        res = ts.shift(1, fill_value="a")
        expected = frame_or_series(
            pd.Categorical(
                ["a", "a", "b", "c"], categories=["a", "b", "c", "d"], ordered=False
            )
        )
        tm.assert_equal(res, expected)

        # check for incorrect fill_value
        msg = r"Cannot setitem on a Categorical with a new category \(f\)"
        with pytest.raises(TypeError, match=msg):
            ts.shift(1, fill_value="f")

    def test_shift_fill_value(self, frame_or_series):
        # GH#24128
        dti = date_range("1/1/2000", periods=5, freq="h")

        ts = frame_or_series([1.0, 2.0, 3.0, 4.0, 5.0], index=dti)
        exp = frame_or_series([0.0, 1.0, 2.0, 3.0, 4.0], index=dti)
        # check that fill value works
        result = ts.shift(1, fill_value=0.0)
        tm.assert_equal(result, exp)

        exp = frame_or_series([0.0, 0.0, 1.0, 2.0, 3.0], index=dti)
        result = ts.shift(2, fill_value=0.0)
        tm.assert_equal(result, exp)

        ts = frame_or_series([1, 2, 3])
        res = ts.shift(2, fill_value=0)
        assert tm.get_dtype(res) == tm.get_dtype(ts)

        # retain integer dtype
        obj = frame_or_series([1, 2, 3, 4, 5], index=dti)
        exp = frame_or_series([0, 1, 2, 3, 4], index=dti)
        result = obj.shift(1, fill_value=0)
        tm.assert_equal(result, exp)

        exp = frame_or_series([0, 0, 1, 2, 3], index=dti)
        result = obj.shift(2, fill_value=0)
        tm.assert_equal(result, exp)

    def test_shift_empty(self):
        # Regression test for GH#8019
        df = DataFrame({"foo": []})
        rs = df.shift(-1)

        tm.assert_frame_equal(df, rs)

    def test_shift_duplicate_columns(self):
        # GH#9092; verify that position-based shifting works
        # in the presence of duplicate columns
        column_lists = [list(range(5)), [1] * 5, [1, 1, 2, 2, 1]]
        data = np.random.default_rng(2).standard_normal((20, 5))

        shifted = []
        for columns in column_lists:
            df = DataFrame(data.copy(), columns=columns)
            for s in range(5):
                df.iloc[:, s] = df.iloc[:, s].shift(s + 1)
            df.columns = range(5)
            shifted.append(df)

        # sanity check the base case
        nulls = shifted[0].isna().sum()
        tm.assert_series_equal(nulls, Series(range(1, 6), dtype="int64"))

        # check all answers are the same
        tm.assert_frame_equal(shifted[0], shifted[1])
        tm.assert_frame_equal(shifted[0], shifted[2])

    def test_shift_axis1_multiple_blocks(self, using_array_manager):
        # GH#35488
        df1 = DataFrame(np.random.default_rng(2).integers(1000, size=(5, 3)))
        df2 = DataFrame(np.random.default_rng(2).integers(1000, size=(5, 2)))
        df3 = pd.concat([df1, df2], axis=1)
        if not using_array_manager:
            assert len(df3._mgr.blocks) == 2

        result = df3.shift(2, axis=1)

        expected = df3.take([-1, -1, 0, 1, 2], axis=1)
        # Explicit cast to float to avoid implicit cast when setting nan.
        # Column names aren't unique, so directly calling `expected.astype` won't work.
        expected = expected.pipe(
            lambda df: df.set_axis(range(df.shape[1]), axis=1)
            .astype({0: "float", 1: "float"})
            .set_axis(df.columns, axis=1)
        )
        expected.iloc[:, :2] = np.nan
        expected.columns = df3.columns

        tm.assert_frame_equal(result, expected)

        # Case with periods < 0
        # rebuild df3 because `take` call above consolidated
        df3 = pd.concat([df1, df2], axis=1)
        if not using_array_manager:
            assert len(df3._mgr.blocks) == 2
        result = df3.shift(-2, axis=1)

        expected = df3.take([2, 3, 4, -1, -1], axis=1)
        # Explicit cast to float to avoid implicit cast when setting nan.
        # Column names aren't unique, so directly calling `expected.astype` won't work.
        expected = expected.pipe(
            lambda df: df.set_axis(range(df.shape[1]), axis=1)
            .astype({3: "float", 4: "float"})
            .set_axis(df.columns, axis=1)
        )
        expected.iloc[:, -2:] = np.nan
        expected.columns = df3.columns

        tm.assert_frame_equal(result, expected)

    @td.skip_array_manager_not_yet_implemented  # TODO(ArrayManager) axis=1 support
    def test_shift_axis1_multiple_blocks_with_int_fill(self):
        # GH#42719
        rng = np.random.default_rng(2)
        df1 = DataFrame(rng.integers(1000, size=(5, 3), dtype=int))
        df2 = DataFrame(rng.integers(1000, size=(5, 2), dtype=int))
        df3 = pd.concat([df1.iloc[:4, 1:3], df2.iloc[:4, :]], axis=1)
        result = df3.shift(2, axis=1, fill_value=np.int_(0))
        assert len(df3._mgr.blocks) == 2

        expected = df3.take([-1, -1, 0, 1], axis=1)
        expected.iloc[:, :2] = np.int_(0)
        expected.columns = df3.columns

        tm.assert_frame_equal(result, expected)

        # Case with periods < 0
        df3 = pd.concat([df1.iloc[:4, 1:3], df2.iloc[:4, :]], axis=1)
        result = df3.shift(-2, axis=1, fill_value=np.int_(0))
        assert len(df3._mgr.blocks) == 2

        expected = df3.take([2, 3, -1, -1], axis=1)
        expected.iloc[:, -2:] = np.int_(0)
        expected.columns = df3.columns

        tm.assert_frame_equal(result, expected)

    def test_period_index_frame_shift_with_freq(self, frame_or_series):
        ps = DataFrame(range(4), index=pd.period_range("2020-01-01", periods=4))
        ps = tm.get_obj(ps, frame_or_series)

        shifted = ps.shift(1, freq="infer")
        unshifted = shifted.shift(-1, freq="infer")
        tm.assert_equal(unshifted, ps)

        shifted2 = ps.shift(freq="D")
        tm.assert_equal(shifted, shifted2)

        shifted3 = ps.shift(freq=offsets.Day())
        tm.assert_equal(shifted, shifted3)

    def test_datetime_frame_shift_with_freq(self, datetime_frame, frame_or_series):
        dtobj = tm.get_obj(datetime_frame, frame_or_series)
        shifted = dtobj.shift(1, freq="infer")
        unshifted = shifted.shift(-1, freq="infer")
        tm.assert_equal(dtobj, unshifted)

        shifted2 = dtobj.shift(freq=dtobj.index.freq)
        tm.assert_equal(shifted, shifted2)

        inferred_ts = DataFrame(
            datetime_frame.values,
            Index(np.asarray(datetime_frame.index)),
            columns=datetime_frame.columns,
        )
        inferred_ts = tm.get_obj(inferred_ts, frame_or_series)
        shifted = inferred_ts.shift(1, freq="infer")
        expected = dtobj.shift(1, freq="infer")
        expected.index = expected.index._with_freq(None)
        tm.assert_equal(shifted, expected)

        unshifted = shifted.shift(-1, freq="infer")
        tm.assert_equal(unshifted, inferred_ts)

    def test_period_index_frame_shift_with_freq_error(self, frame_or_series):
        ps = DataFrame(range(4), index=pd.period_range("2020-01-01", periods=4))
        ps = tm.get_obj(ps, frame_or_series)
        msg = "Given freq M does not match PeriodIndex freq D"
        with pytest.raises(ValueError, match=msg):
            ps.shift(freq="M")

    def test_datetime_frame_shift_with_freq_error(
        self, datetime_frame, frame_or_series
    ):
        dtobj = tm.get_obj(datetime_frame, frame_or_series)
        no_freq = dtobj.iloc[[0, 5, 7]]
        msg = "Freq was not set in the index hence cannot be inferred"
        with pytest.raises(ValueError, match=msg):
            no_freq.shift(freq="infer")

    def test_shift_dt64values_int_fill_deprecated(self):
        # GH#31971
        ser = Series([pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-02")])

        with pytest.raises(TypeError, match="value should be a"):
            ser.shift(1, fill_value=0)

        df = ser.to_frame()
        with pytest.raises(TypeError, match="value should be a"):
            df.shift(1, fill_value=0)

        # axis = 1
        df2 = DataFrame({"A": ser, "B": ser})
        df2._consolidate_inplace()

        result = df2.shift(1, axis=1, fill_value=0)
        expected = DataFrame({"A": [0, 0], "B": df2["A"]})
        tm.assert_frame_equal(result, expected)

        # same thing but not consolidated; pre-2.0 we got different behavior
        df3 = DataFrame({"A": ser})
        df3["B"] = ser
        assert len(df3._mgr.arrays) == 2
        result = df3.shift(1, axis=1, fill_value=0)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "as_cat",
        [
            pytest.param(
                True,
                marks=pytest.mark.xfail(
                    reason="_can_hold_element incorrectly always returns True"
                ),
            ),
            False,
        ],
    )
    @pytest.mark.parametrize(
        "vals",
        [
            date_range("2020-01-01", periods=2),
            date_range("2020-01-01", periods=2, tz="US/Pacific"),
            pd.period_range("2020-01-01", periods=2, freq="D"),
            pd.timedelta_range("2020 Days", periods=2, freq="D"),
            pd.interval_range(0, 3, periods=2),
            pytest.param(
                pd.array([1, 2], dtype="Int64"),
                marks=pytest.mark.xfail(
                    reason="_can_hold_element incorrectly always returns True"
                ),
            ),
            pytest.param(
                pd.array([1, 2], dtype="Float32"),
                marks=pytest.mark.xfail(
                    reason="_can_hold_element incorrectly always returns True"
                ),
            ),
        ],
        ids=lambda x: str(x.dtype),
    )
    def test_shift_dt64values_axis1_invalid_fill(self, vals, as_cat):
        # GH#44564
        ser = Series(vals)
        if as_cat:
            ser = ser.astype("category")

        df = DataFrame({"A": ser})
        result = df.shift(-1, axis=1, fill_value="foo")
        expected = DataFrame({"A": ["foo", "foo"]})
        tm.assert_frame_equal(result, expected)

        # same thing but multiple blocks
        df2 = DataFrame({"A": ser, "B": ser})
        df2._consolidate_inplace()

        result = df2.shift(-1, axis=1, fill_value="foo")
        expected = DataFrame({"A": df2["B"], "B": ["foo", "foo"]})
        tm.assert_frame_equal(result, expected)

        # same thing but not consolidated
        df3 = DataFrame({"A": ser})
        df3["B"] = ser
        assert len(df3._mgr.arrays) == 2
        result = df3.shift(-1, axis=1, fill_value="foo")
        tm.assert_frame_equal(result, expected)

    def test_shift_axis1_categorical_columns(self):
        # GH#38434
        ci = CategoricalIndex(["a", "b", "c"])
        df = DataFrame(
            {"a": [1, 3], "b": [2, 4], "c": [5, 6]}, index=ci[:-1], columns=ci
        )
        result = df.shift(axis=1)

        expected = DataFrame(
            {"a": [np.nan, np.nan], "b": [1, 3], "c": [2, 4]}, index=ci[:-1], columns=ci
        )
        tm.assert_frame_equal(result, expected)

        # periods != 1
        result = df.shift(2, axis=1)
        expected = DataFrame(
            {"a": [np.nan, np.nan], "b": [np.nan, np.nan], "c": [1, 3]},
            index=ci[:-1],
            columns=ci,
        )
        tm.assert_frame_equal(result, expected)

    def test_shift_axis1_many_periods(self):
        # GH#44978 periods > len(columns)
        df = DataFrame(np.random.default_rng(2).random((5, 3)))
        shifted = df.shift(6, axis=1, fill_value=None)

        expected = df * np.nan
        tm.assert_frame_equal(shifted, expected)

        shifted2 = df.shift(-6, axis=1, fill_value=None)
        tm.assert_frame_equal(shifted2, expected)

    def test_shift_with_offsets_freq(self):
        df = DataFrame({"x": [1, 2, 3]}, index=date_range("2000", periods=3))
        shifted = df.shift(freq="1MS")
        expected = DataFrame(
            {"x": [1, 2, 3]},
            index=date_range(start="02/01/2000", end="02/01/2000", periods=3),
        )
        tm.assert_frame_equal(shifted, expected)

    def test_shift_with_iterable_basic_functionality(self):
        # GH#44424
        data = {"a": [1, 2, 3], "b": [4, 5, 6]}
        shifts = [0, 1, 2]

        df = DataFrame(data)
        shifted = df.shift(shifts)

        expected = DataFrame(
            {
                "a_0": [1, 2, 3],
                "b_0": [4, 5, 6],
                "a_1": [np.nan, 1.0, 2.0],
                "b_1": [np.nan, 4.0, 5.0],
                "a_2": [np.nan, np.nan, 1.0],
                "b_2": [np.nan, np.nan, 4.0],
            }
        )
        tm.assert_frame_equal(expected, shifted)

    def test_shift_with_iterable_series(self):
        # GH#44424
        data = {"a": [1, 2, 3]}
        shifts = [0, 1, 2]

        df = DataFrame(data)
        s = df["a"]
        tm.assert_frame_equal(s.shift(shifts), df.shift(shifts))

    def test_shift_with_iterable_freq_and_fill_value(self):
        # GH#44424
        df = DataFrame(
            np.random.default_rng(2).standard_normal(5),
            index=date_range("1/1/2000", periods=5, freq="h"),
        )

        tm.assert_frame_equal(
            # rename because shift with an iterable leads to str column names
            df.shift([1], fill_value=1).rename(columns=lambda x: int(x[0])),
            df.shift(1, fill_value=1),
        )

        tm.assert_frame_equal(
            df.shift([1], freq="h").rename(columns=lambda x: int(x[0])),
            df.shift(1, freq="h"),
        )

        msg = (
            "Passing a 'freq' together with a 'fill_value' silently ignores the "
            "fill_value"
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            df.shift([1, 2], fill_value=1, freq="h")

    def test_shift_with_iterable_check_other_arguments(self):
        # GH#44424
        data = {"a": [1, 2], "b": [4, 5]}
        shifts = [0, 1]
        df = DataFrame(data)

        # test suffix
        shifted = df[["a"]].shift(shifts, suffix="_suffix")
        expected = DataFrame({"a_suffix_0": [1, 2], "a_suffix_1": [np.nan, 1.0]})
        tm.assert_frame_equal(shifted, expected)

        # check bad inputs when doing multiple shifts
        msg = "If `periods` contains multiple shifts, `axis` cannot be 1."
        with pytest.raises(ValueError, match=msg):
            df.shift(shifts, axis=1)

        msg = "Periods must be integer, but s is <class 'str'>."
        with pytest.raises(TypeError, match=msg):
            df.shift(["s"])

        msg = "If `periods` is an iterable, it cannot be empty."
        with pytest.raises(ValueError, match=msg):
            df.shift([])

        msg = "Cannot specify `suffix` if `periods` is an int."
        with pytest.raises(ValueError, match=msg):
            df.shift(1, suffix="fails")

    def test_shift_axis_one_empty(self):
        # GH#57301
        df = DataFrame()
        result = df.shift(1, axis=1)
        tm.assert_frame_equal(result, df)
