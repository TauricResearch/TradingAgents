import numpy as np
import pytest

from pandas.compat import WARNING_CHECK_DISABLED
import pandas.util._test_decorators as td

from pandas import (
    Categorical,
    DataFrame,
    DatetimeIndex,
    NaT,
    PeriodIndex,
    Series,
    TimedeltaIndex,
    Timestamp,
    date_range,
    to_datetime,
)
import pandas._testing as tm
from pandas.tests.frame.common import _check_mixed_float


class TestFillNA:
    def test_fillna_dict_inplace_nonunique_columns(
        self, using_copy_on_write, warn_copy_on_write
    ):
        df = DataFrame(
            {"A": [np.nan] * 3, "B": [NaT, Timestamp(1), NaT], "C": [np.nan, "foo", 2]}
        )
        df.columns = ["A", "A", "A"]
        orig = df[:]

        # TODO(CoW-warn) better warning message
        with tm.assert_cow_warning(warn_copy_on_write):
            df.fillna({"A": 2}, inplace=True)
        # The first and third columns can be set inplace, while the second cannot.

        expected = DataFrame(
            {"A": [2.0] * 3, "B": [2, Timestamp(1), 2], "C": [2, "foo", 2]}
        )
        expected.columns = ["A", "A", "A"]
        tm.assert_frame_equal(df, expected)

        # TODO: what's the expected/desired behavior with CoW?
        if not using_copy_on_write:
            assert tm.shares_memory(df.iloc[:, 0], orig.iloc[:, 0])
        assert not tm.shares_memory(df.iloc[:, 1], orig.iloc[:, 1])
        if not using_copy_on_write:
            assert tm.shares_memory(df.iloc[:, 2], orig.iloc[:, 2])

    @td.skip_array_manager_not_yet_implemented
    def test_fillna_on_column_view(self, using_copy_on_write):
        # GH#46149 avoid unnecessary copies
        arr = np.full((40, 50), np.nan)
        df = DataFrame(arr, copy=False)

        if using_copy_on_write:
            with tm.raises_chained_assignment_error():
                df[0].fillna(-1, inplace=True)
            assert np.isnan(arr[:, 0]).all()
        else:
            with tm.assert_produces_warning(
                FutureWarning if not WARNING_CHECK_DISABLED else None,
                match="inplace method",
            ):
                df[0].fillna(-1, inplace=True)
            assert (arr[:, 0] == -1).all()

        # i.e. we didn't create a new 49-column block
        assert len(df._mgr.arrays) == 1
        assert np.shares_memory(df.values, arr)

    def test_fillna_datetime(self, datetime_frame):
        tf = datetime_frame
        tf.loc[tf.index[:5], "A"] = np.nan
        tf.loc[tf.index[-5:], "A"] = np.nan

        zero_filled = datetime_frame.fillna(0)
        assert (zero_filled.loc[zero_filled.index[:5], "A"] == 0).all()

        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            padded = datetime_frame.fillna(method="pad")
        assert np.isnan(padded.loc[padded.index[:5], "A"]).all()
        assert (
            padded.loc[padded.index[-5:], "A"] == padded.loc[padded.index[-5], "A"]
        ).all()

        msg = "Must specify a fill 'value' or 'method'"
        with pytest.raises(ValueError, match=msg):
            datetime_frame.fillna()
        msg = "Cannot specify both 'value' and 'method'"
        with pytest.raises(ValueError, match=msg):
            datetime_frame.fillna(5, method="ffill")

    def test_fillna_mixed_type(self, float_string_frame):
        mf = float_string_frame
        mf.loc[mf.index[5:20], "foo"] = np.nan
        mf.loc[mf.index[-10:], "A"] = np.nan
        # TODO: make stronger assertion here, GH 25640
        mf.fillna(value=0)
        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            mf.fillna(method="pad")

    def test_fillna_mixed_float(self, mixed_float_frame):
        # mixed numeric (but no float16)
        mf = mixed_float_frame.reindex(columns=["A", "B", "D"])
        mf.loc[mf.index[-10:], "A"] = np.nan
        result = mf.fillna(value=0)
        _check_mixed_float(result, dtype={"C": None})

        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = mf.fillna(method="pad")
        _check_mixed_float(result, dtype={"C": None})

    def test_fillna_empty(self, using_copy_on_write):
        if using_copy_on_write:
            pytest.skip("condition is unnecessary complex and is deprecated anyway")
        # empty frame (GH#2778)
        df = DataFrame(columns=["x"])
        for m in ["pad", "backfill"]:
            msg = "Series.fillna with 'method' is deprecated"
            with tm.assert_produces_warning(FutureWarning, match=msg):
                df.x.fillna(method=m, inplace=True)
                df.x.fillna(method=m)

    def test_fillna_different_dtype(self):
        # with different dtype (GH#3386)
        df = DataFrame(
            [["a", "a", np.nan, "a"], ["b", "b", np.nan, "b"], ["c", "c", np.nan, "c"]]
        )

        result = df.fillna({2: "foo"})
        expected = DataFrame(
            [["a", "a", "foo", "a"], ["b", "b", "foo", "b"], ["c", "c", "foo", "c"]]
        )
        # column is originally float (all-NaN) -> filling with string gives object dtype
        expected[2] = expected[2].astype("object")
        tm.assert_frame_equal(result, expected)

        return_value = df.fillna({2: "foo"}, inplace=True)
        tm.assert_frame_equal(df, expected)
        assert return_value is None

    def test_fillna_limit_and_value(self):
        # limit and value
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 3)))
        df.iloc[2:7, 0] = np.nan
        df.iloc[3:5, 2] = np.nan

        expected = df.copy()
        expected.iloc[2, 0] = 999
        expected.iloc[3, 2] = 999
        result = df.fillna(999, limit=1)
        tm.assert_frame_equal(result, expected)

    def test_fillna_datelike(self):
        # with datelike
        # GH#6344
        df = DataFrame(
            {
                "Date": [NaT, Timestamp("2014-1-1")],
                "Date2": [Timestamp("2013-1-1"), NaT],
            }
        )

        expected = df.copy()
        expected["Date"] = expected["Date"].fillna(df.loc[df.index[0], "Date2"])
        result = df.fillna(value={"Date": df["Date2"]})
        tm.assert_frame_equal(result, expected)

    def test_fillna_tzaware(self):
        # with timezone
        # GH#15855
        df = DataFrame({"A": [Timestamp("2012-11-11 00:00:00+01:00"), NaT]})
        exp = DataFrame(
            {
                "A": [
                    Timestamp("2012-11-11 00:00:00+01:00"),
                    Timestamp("2012-11-11 00:00:00+01:00"),
                ]
            }
        )
        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = df.fillna(method="pad")
        tm.assert_frame_equal(res, exp)

        df = DataFrame({"A": [NaT, Timestamp("2012-11-11 00:00:00+01:00")]})
        exp = DataFrame(
            {
                "A": [
                    Timestamp("2012-11-11 00:00:00+01:00"),
                    Timestamp("2012-11-11 00:00:00+01:00"),
                ]
            }
        )
        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = df.fillna(method="bfill")
        tm.assert_frame_equal(res, exp)

    def test_fillna_tzaware_different_column(self):
        # with timezone in another column
        # GH#15522
        df = DataFrame(
            {
                "A": date_range("20130101", periods=4, tz="US/Eastern"),
                "B": [1, 2, np.nan, np.nan],
            }
        )
        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.fillna(method="pad")
        expected = DataFrame(
            {
                "A": date_range("20130101", periods=4, tz="US/Eastern"),
                "B": [1.0, 2.0, 2.0, 2.0],
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_na_actions_categorical(self):
        cat = Categorical([1, 2, 3, np.nan], categories=[1, 2, 3])
        vals = ["a", "b", np.nan, "d"]
        df = DataFrame({"cats": cat, "vals": vals})
        cat2 = Categorical([1, 2, 3, 3], categories=[1, 2, 3])
        vals2 = ["a", "b", "b", "d"]
        df_exp_fill = DataFrame({"cats": cat2, "vals": vals2})
        cat3 = Categorical([1, 2, 3], categories=[1, 2, 3])
        vals3 = ["a", "b", np.nan]
        df_exp_drop_cats = DataFrame({"cats": cat3, "vals": vals3})
        cat4 = Categorical([1, 2], categories=[1, 2, 3])
        vals4 = ["a", "b"]
        df_exp_drop_all = DataFrame({"cats": cat4, "vals": vals4})

        # fillna
        res = df.fillna(value={"cats": 3, "vals": "b"})
        tm.assert_frame_equal(res, df_exp_fill)

        msg = "Cannot setitem on a Categorical with a new category"
        with pytest.raises(TypeError, match=msg):
            df.fillna(value={"cats": 4, "vals": "c"})

        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = df.fillna(method="pad")
        tm.assert_frame_equal(res, df_exp_fill)

        # dropna
        res = df.dropna(subset=["cats"])
        tm.assert_frame_equal(res, df_exp_drop_cats)

        res = df.dropna()
        tm.assert_frame_equal(res, df_exp_drop_all)

        # make sure that fillna takes missing values into account
        c = Categorical([np.nan, "b", np.nan], categories=["a", "b"])
        df = DataFrame({"cats": c, "vals": [1, 2, 3]})

        cat_exp = Categorical(["a", "b", "a"], categories=["a", "b"])
        df_exp = DataFrame({"cats": cat_exp, "vals": [1, 2, 3]})

        res = df.fillna("a")
        tm.assert_frame_equal(res, df_exp)

    def test_fillna_categorical_nan(self):
        # GH#14021
        # np.nan should always be a valid filler
        cat = Categorical([np.nan, 2, np.nan])
        val = Categorical([np.nan, np.nan, np.nan])
        df = DataFrame({"cats": cat, "vals": val})

        # GH#32950 df.median() is poorly behaved because there is no
        #  Categorical.median
        median = Series({"cats": 2.0, "vals": np.nan})

        res = df.fillna(median)
        v_exp = [np.nan, np.nan, np.nan]
        df_exp = DataFrame({"cats": [2, 2, 2], "vals": v_exp}, dtype="category")
        tm.assert_frame_equal(res, df_exp)

        result = df.cats.fillna(np.nan)
        tm.assert_series_equal(result, df.cats)

        result = df.vals.fillna(np.nan)
        tm.assert_series_equal(result, df.vals)

        idx = DatetimeIndex(
            ["2011-01-01 09:00", "2016-01-01 23:45", "2011-01-01 09:00", NaT, NaT]
        )
        df = DataFrame({"a": Categorical(idx)})
        tm.assert_frame_equal(df.fillna(value=NaT), df)

        idx = PeriodIndex(["2011-01", "2011-01", "2011-01", NaT, NaT], freq="M")
        df = DataFrame({"a": Categorical(idx)})
        tm.assert_frame_equal(df.fillna(value=NaT), df)

        idx = TimedeltaIndex(["1 days", "2 days", "1 days", NaT, NaT])
        df = DataFrame({"a": Categorical(idx)})
        tm.assert_frame_equal(df.fillna(value=NaT), df)

    def test_fillna_downcast(self):
        # GH#15277
        # infer int64 from float64
        df = DataFrame({"a": [1.0, np.nan]})
        msg = "The 'downcast' keyword in fillna is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.fillna(0, downcast="infer")
        expected = DataFrame({"a": [1, 0]})
        tm.assert_frame_equal(result, expected)

        # infer int64 from float64 when fillna value is a dict
        df = DataFrame({"a": [1.0, np.nan]})
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.fillna({"a": 0}, downcast="infer")
        expected = DataFrame({"a": [1, 0]})
        tm.assert_frame_equal(result, expected)

    def test_fillna_downcast_false(self, frame_or_series):
        # GH#45603 preserve object dtype with downcast=False
        obj = frame_or_series([1, 2, 3], dtype="object")
        msg = "The 'downcast' keyword in fillna"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = obj.fillna("", downcast=False)
        tm.assert_equal(result, obj)

    def test_fillna_downcast_noop(self, frame_or_series):
        # GH#45423
        # Two relevant paths:
        #  1) not _can_hold_na (e.g. integer)
        #  2) _can_hold_na + noop + not can_hold_element

        obj = frame_or_series([1, 2, 3], dtype=np.int64)

        msg = "The 'downcast' keyword in fillna"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            # GH#40988
            res = obj.fillna("foo", downcast=np.dtype(np.int32))
        expected = obj.astype(np.int32)
        tm.assert_equal(res, expected)

        obj2 = obj.astype(np.float64)
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res2 = obj2.fillna("foo", downcast="infer")
        expected2 = obj  # get back int64
        tm.assert_equal(res2, expected2)

        with tm.assert_produces_warning(FutureWarning, match=msg):
            # GH#40988
            res3 = obj2.fillna("foo", downcast=np.dtype(np.int32))
        tm.assert_equal(res3, expected)

    @pytest.mark.parametrize("columns", [["A", "A", "B"], ["A", "A"]])
    def test_fillna_dictlike_value_duplicate_colnames(self, columns):
        # GH#43476
        df = DataFrame(np.nan, index=[0, 1], columns=columns)
        with tm.assert_produces_warning(None):
            result = df.fillna({"A": 0})

        expected = df.copy()
        expected["A"] = 0.0
        tm.assert_frame_equal(result, expected)

    def test_fillna_dtype_conversion(self, using_infer_string):
        # make sure that fillna on an empty frame works
        df = DataFrame(index=["A", "B", "C"], columns=[1, 2, 3, 4, 5])
        result = df.dtypes
        expected = Series([np.dtype("object")] * 5, index=[1, 2, 3, 4, 5])
        tm.assert_series_equal(result, expected)

        msg = "Downcasting object dtype arrays"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.fillna(1)
        expected = DataFrame(1, index=["A", "B", "C"], columns=[1, 2, 3, 4, 5])
        tm.assert_frame_equal(result, expected)

        # empty block
        df = DataFrame(index=range(3), columns=["A", "B"], dtype="float64")
        result = df.fillna("nan")
        expected = DataFrame("nan", index=range(3), columns=["A", "B"], dtype=object)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("val", ["", 1, np.nan, 1.0])
    def test_fillna_dtype_conversion_equiv_replace(self, val):
        df = DataFrame({"A": [1, np.nan], "B": [1.0, 2.0]})
        expected = df.replace(np.nan, val)
        result = df.fillna(val)
        tm.assert_frame_equal(result, expected)

    def test_fillna_datetime_columns(self):
        # GH#7095
        df = DataFrame(
            {
                "A": [-1, -2, np.nan],
                "B": date_range("20130101", periods=3),
                "C": ["foo", "bar", None],
                "D": ["foo2", "bar2", None],
            },
            index=date_range("20130110", periods=3),
        )
        result = df.fillna("?")
        expected = DataFrame(
            {
                "A": [-1, -2, "?"],
                "B": date_range("20130101", periods=3),
                "C": ["foo", "bar", "?"],
                "D": ["foo2", "bar2", "?"],
            },
            index=date_range("20130110", periods=3),
        )
        tm.assert_frame_equal(result, expected)

        df = DataFrame(
            {
                "A": [-1, -2, np.nan],
                "B": [Timestamp("2013-01-01"), Timestamp("2013-01-02"), NaT],
                "C": ["foo", "bar", None],
                "D": ["foo2", "bar2", None],
            },
            index=date_range("20130110", periods=3),
        )
        result = df.fillna("?")
        expected = DataFrame(
            {
                "A": [-1, -2, "?"],
                "B": [Timestamp("2013-01-01"), Timestamp("2013-01-02"), "?"],
                "C": ["foo", "bar", "?"],
                "D": ["foo2", "bar2", "?"],
            },
            index=date_range("20130110", periods=3),
        )
        tm.assert_frame_equal(result, expected)

    def test_ffill(self, datetime_frame):
        datetime_frame.loc[datetime_frame.index[:5], "A"] = np.nan
        datetime_frame.loc[datetime_frame.index[-5:], "A"] = np.nan

        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            alt = datetime_frame.fillna(method="ffill")
        tm.assert_frame_equal(datetime_frame.ffill(), alt)

    def test_bfill(self, datetime_frame):
        datetime_frame.loc[datetime_frame.index[:5], "A"] = np.nan
        datetime_frame.loc[datetime_frame.index[-5:], "A"] = np.nan

        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            alt = datetime_frame.fillna(method="bfill")

        tm.assert_frame_equal(datetime_frame.bfill(), alt)

    def test_frame_pad_backfill_limit(self):
        index = np.arange(10)
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 4)), index=index)

        result = df[:2].reindex(index, method="pad", limit=5)

        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            expected = df[:2].reindex(index).fillna(method="pad")
        expected.iloc[-3:] = np.nan
        tm.assert_frame_equal(result, expected)

        result = df[-2:].reindex(index, method="backfill", limit=5)

        with tm.assert_produces_warning(FutureWarning, match=msg):
            expected = df[-2:].reindex(index).fillna(method="backfill")
        expected.iloc[:3] = np.nan
        tm.assert_frame_equal(result, expected)

    def test_frame_fillna_limit(self):
        index = np.arange(10)
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 4)), index=index)

        result = df[:2].reindex(index)
        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = result.fillna(method="pad", limit=5)

        with tm.assert_produces_warning(FutureWarning, match=msg):
            expected = df[:2].reindex(index).fillna(method="pad")
        expected.iloc[-3:] = np.nan
        tm.assert_frame_equal(result, expected)

        result = df[-2:].reindex(index)
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = result.fillna(method="backfill", limit=5)

        with tm.assert_produces_warning(FutureWarning, match=msg):
            expected = df[-2:].reindex(index).fillna(method="backfill")
        expected.iloc[:3] = np.nan
        tm.assert_frame_equal(result, expected)

    def test_fillna_skip_certain_blocks(self):
        # don't try to fill boolean, int blocks

        df = DataFrame(np.random.default_rng(2).standard_normal((10, 4)).astype(int))

        # it works!
        df.fillna(np.nan)

    @pytest.mark.parametrize("type", [int, float])
    def test_fillna_positive_limit(self, type):
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 4))).astype(type)

        msg = "Limit must be greater than 0"
        with pytest.raises(ValueError, match=msg):
            df.fillna(0, limit=-5)

    @pytest.mark.parametrize("type", [int, float])
    def test_fillna_integer_limit(self, type):
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 4))).astype(type)

        msg = "Limit must be an integer"
        with pytest.raises(ValueError, match=msg):
            df.fillna(0, limit=0.5)

    def test_fillna_inplace(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 4)))
        df.loc[:4, 1] = np.nan
        df.loc[-4:, 3] = np.nan

        expected = df.fillna(value=0)
        assert expected is not df

        df.fillna(value=0, inplace=True)
        tm.assert_frame_equal(df, expected)

        expected = df.fillna(value={0: 0}, inplace=True)
        assert expected is None

        df.loc[:4, 1] = np.nan
        df.loc[-4:, 3] = np.nan
        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            expected = df.fillna(method="ffill")
        assert expected is not df

        with tm.assert_produces_warning(FutureWarning, match=msg):
            df.fillna(method="ffill", inplace=True)
        tm.assert_frame_equal(df, expected)

    def test_fillna_dict_series(self):
        df = DataFrame(
            {
                "a": [np.nan, 1, 2, np.nan, np.nan],
                "b": [1, 2, 3, np.nan, np.nan],
                "c": [np.nan, 1, 2, 3, 4],
            }
        )

        result = df.fillna({"a": 0, "b": 5})

        expected = df.copy()
        expected["a"] = expected["a"].fillna(0)
        expected["b"] = expected["b"].fillna(5)
        tm.assert_frame_equal(result, expected)

        # it works
        result = df.fillna({"a": 0, "b": 5, "d": 7})

        # Series treated same as dict
        result = df.fillna(df.max())
        expected = df.fillna(df.max().to_dict())
        tm.assert_frame_equal(result, expected)

        # disable this for now
        with pytest.raises(NotImplementedError, match="column by column"):
            df.fillna(df.max(1), axis=1)

    def test_fillna_dataframe(self):
        # GH#8377
        df = DataFrame(
            {
                "a": [np.nan, 1, 2, np.nan, np.nan],
                "b": [1, 2, 3, np.nan, np.nan],
                "c": [np.nan, 1, 2, 3, 4],
            },
            index=list("VWXYZ"),
        )

        # df2 may have different index and columns
        df2 = DataFrame(
            {
                "a": [np.nan, 10, 20, 30, 40],
                "b": [50, 60, 70, 80, 90],
                "foo": ["bar"] * 5,
            },
            index=list("VWXuZ"),
        )

        result = df.fillna(df2)

        # only those columns and indices which are shared get filled
        expected = DataFrame(
            {
                "a": [np.nan, 1, 2, np.nan, 40],
                "b": [1, 2, 3, np.nan, 90],
                "c": [np.nan, 1, 2, 3, 4],
            },
            index=list("VWXYZ"),
        )

        tm.assert_frame_equal(result, expected)

    def test_fillna_columns(self):
        arr = np.random.default_rng(2).standard_normal((10, 10))
        arr[:, ::2] = np.nan
        df = DataFrame(arr)

        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.fillna(method="ffill", axis=1)
        with tm.assert_produces_warning(FutureWarning, match=msg):
            expected = df.T.fillna(method="pad").T
        tm.assert_frame_equal(result, expected)

        df.insert(6, "foo", 5)
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.fillna(method="ffill", axis=1)
        with tm.assert_produces_warning(FutureWarning, match=msg):
            expected = df.astype(float).fillna(method="ffill", axis=1)
        tm.assert_frame_equal(result, expected)

    def test_fillna_invalid_method(self, float_frame):
        with pytest.raises(ValueError, match="ffil"):
            float_frame.fillna(method="ffil")

    def test_fillna_invalid_value(self, float_frame):
        # list
        msg = '"value" parameter must be a scalar or dict, but you passed a "{}"'
        with pytest.raises(TypeError, match=msg.format("list")):
            float_frame.fillna([1, 2])
        # tuple
        with pytest.raises(TypeError, match=msg.format("tuple")):
            float_frame.fillna((1, 2))
        # frame with series
        msg = (
            '"value" parameter must be a scalar, dict or Series, but you '
            'passed a "DataFrame"'
        )
        with pytest.raises(TypeError, match=msg):
            float_frame.iloc[:, 0].fillna(float_frame)

    def test_fillna_col_reordering(self):
        cols = ["COL." + str(i) for i in range(5, 0, -1)]
        data = np.random.default_rng(2).random((20, 5))
        df = DataFrame(index=range(20), columns=cols, data=data)
        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            filled = df.fillna(method="ffill")
        assert df.columns.tolist() == filled.columns.tolist()

    def test_fill_empty(self, float_frame):
        df = float_frame.reindex(columns=[])
        result = df.fillna(value=0)
        tm.assert_frame_equal(result, df)

    def test_fillna_downcast_dict(self):
        # GH#40809
        df = DataFrame({"col1": [1, np.nan]})

        msg = "The 'downcast' keyword in fillna"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.fillna({"col1": 2}, downcast={"col1": "int64"})
        expected = DataFrame({"col1": [1, 2]})
        tm.assert_frame_equal(result, expected)

    def test_fillna_with_columns_and_limit(self):
        # GH40989
        df = DataFrame(
            [
                [np.nan, 2, np.nan, 0],
                [3, 4, np.nan, 1],
                [np.nan, np.nan, np.nan, 5],
                [np.nan, 3, np.nan, 4],
            ],
            columns=list("ABCD"),
        )
        result = df.fillna(axis=1, value=100, limit=1)
        result2 = df.fillna(axis=1, value=100, limit=2)

        expected = DataFrame(
            {
                "A": Series([100, 3, 100, 100], dtype="float64"),
                "B": [2, 4, np.nan, 3],
                "C": [np.nan, 100, np.nan, np.nan],
                "D": Series([0, 1, 5, 4], dtype="float64"),
            },
            index=[0, 1, 2, 3],
        )
        expected2 = DataFrame(
            {
                "A": Series([100, 3, 100, 100], dtype="float64"),
                "B": Series([2, 4, 100, 3], dtype="float64"),
                "C": [100, 100, np.nan, 100],
                "D": Series([0, 1, 5, 4], dtype="float64"),
            },
            index=[0, 1, 2, 3],
        )

        tm.assert_frame_equal(result, expected)
        tm.assert_frame_equal(result2, expected2)

    def test_fillna_datetime_inplace(self):
        # GH#48863
        df = DataFrame(
            {
                "date1": to_datetime(["2018-05-30", None]),
                "date2": to_datetime(["2018-09-30", None]),
            }
        )
        expected = df.copy()
        df.fillna(np.nan, inplace=True)
        tm.assert_frame_equal(df, expected)

    def test_fillna_inplace_with_columns_limit_and_value(self):
        # GH40989
        df = DataFrame(
            [
                [np.nan, 2, np.nan, 0],
                [3, 4, np.nan, 1],
                [np.nan, np.nan, np.nan, 5],
                [np.nan, 3, np.nan, 4],
            ],
            columns=list("ABCD"),
        )

        expected = df.fillna(axis=1, value=100, limit=1)
        assert expected is not df

        df.fillna(axis=1, value=100, limit=1, inplace=True)
        tm.assert_frame_equal(df, expected)

    @td.skip_array_manager_invalid_test
    @pytest.mark.parametrize("val", [-1, {"x": -1, "y": -1}])
    def test_inplace_dict_update_view(
        self, val, using_copy_on_write, warn_copy_on_write
    ):
        # GH#47188
        df = DataFrame({"x": [np.nan, 2], "y": [np.nan, 2]})
        df_orig = df.copy()
        result_view = df[:]
        with tm.assert_cow_warning(warn_copy_on_write):
            df.fillna(val, inplace=True)
        expected = DataFrame({"x": [-1, 2.0], "y": [-1.0, 2]})
        tm.assert_frame_equal(df, expected)
        if using_copy_on_write:
            tm.assert_frame_equal(result_view, df_orig)
        else:
            tm.assert_frame_equal(result_view, expected)

    def test_single_block_df_with_horizontal_axis(self):
        # GH 47713
        df = DataFrame(
            {
                "col1": [5, 0, np.nan, 10, np.nan],
                "col2": [7, np.nan, np.nan, 5, 3],
                "col3": [12, np.nan, 1, 2, 0],
                "col4": [np.nan, 1, 1, np.nan, 18],
            }
        )
        result = df.fillna(50, limit=1, axis=1)
        expected = DataFrame(
            [
                [5.0, 7.0, 12.0, 50.0],
                [0.0, 50.0, np.nan, 1.0],
                [50.0, np.nan, 1.0, 1.0],
                [10.0, 5.0, 2.0, 50.0],
                [50.0, 3.0, 0.0, 18.0],
            ],
            columns=["col1", "col2", "col3", "col4"],
        )
        tm.assert_frame_equal(result, expected)

    def test_fillna_with_multi_index_frame(self):
        # GH 47649
        pdf = DataFrame(
            {
                ("x", "a"): [np.nan, 2.0, 3.0],
                ("x", "b"): [1.0, 2.0, np.nan],
                ("y", "c"): [1.0, 2.0, np.nan],
            }
        )
        expected = DataFrame(
            {
                ("x", "a"): [-1.0, 2.0, 3.0],
                ("x", "b"): [1.0, 2.0, -1.0],
                ("y", "c"): [1.0, 2.0, np.nan],
            }
        )
        tm.assert_frame_equal(pdf.fillna({"x": -1}), expected)
        tm.assert_frame_equal(pdf.fillna({"x": -1, ("x", "b"): -2}), expected)

        expected = DataFrame(
            {
                ("x", "a"): [-1.0, 2.0, 3.0],
                ("x", "b"): [1.0, 2.0, -2.0],
                ("y", "c"): [1.0, 2.0, np.nan],
            }
        )
        tm.assert_frame_equal(pdf.fillna({("x", "b"): -2, "x": -1}), expected)


def test_fillna_nonconsolidated_frame():
    # https://github.com/pandas-dev/pandas/issues/36495
    df = DataFrame(
        [
            [1, 1, 1, 1.0],
            [2, 2, 2, 2.0],
            [3, 3, 3, 3.0],
        ],
        columns=["i1", "i2", "i3", "f1"],
    )
    df_nonconsol = df.pivot(index="i1", columns="i2")
    result = df_nonconsol.fillna(0)
    assert result.isna().sum().sum() == 0


def test_fillna_nones_inplace():
    # GH 48480
    df = DataFrame(
        [[None, None], [None, None]],
        columns=["A", "B"],
    )
    msg = "Downcasting object dtype arrays"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        df.fillna(value={"A": 1, "B": 2}, inplace=True)

    expected = DataFrame([[1, 2], [1, 2]], columns=["A", "B"])
    tm.assert_frame_equal(df, expected)


@pytest.mark.parametrize("func", ["pad", "backfill"])
def test_pad_backfill_deprecated(func):
    # GH#33396
    df = DataFrame({"a": [1, 2, 3]})
    with tm.assert_produces_warning(FutureWarning):
        getattr(df, func)()


@pytest.mark.parametrize(
    "data, expected_data, method, kwargs",
    (
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [np.nan, np.nan, 3.0, 3.0, 3.0, 3.0, 7.0, np.nan, np.nan],
            "ffill",
            {"limit_area": "inside"},
        ),
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [np.nan, np.nan, 3.0, 3.0, np.nan, np.nan, 7.0, np.nan, np.nan],
            "ffill",
            {"limit_area": "inside", "limit": 1},
        ),
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [np.nan, np.nan, 3.0, np.nan, np.nan, np.nan, 7.0, 7.0, 7.0],
            "ffill",
            {"limit_area": "outside"},
        ),
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [np.nan, np.nan, 3.0, np.nan, np.nan, np.nan, 7.0, 7.0, np.nan],
            "ffill",
            {"limit_area": "outside", "limit": 1},
        ),
        (
            [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan],
            [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan],
            "ffill",
            {"limit_area": "outside", "limit": 1},
        ),
        (
            range(5),
            range(5),
            "ffill",
            {"limit_area": "outside", "limit": 1},
        ),
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [np.nan, np.nan, 3.0, 7.0, 7.0, 7.0, 7.0, np.nan, np.nan],
            "bfill",
            {"limit_area": "inside"},
        ),
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [np.nan, np.nan, 3.0, np.nan, np.nan, 7.0, 7.0, np.nan, np.nan],
            "bfill",
            {"limit_area": "inside", "limit": 1},
        ),
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [3.0, 3.0, 3.0, np.nan, np.nan, np.nan, 7.0, np.nan, np.nan],
            "bfill",
            {"limit_area": "outside"},
        ),
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [np.nan, 3.0, 3.0, np.nan, np.nan, np.nan, 7.0, np.nan, np.nan],
            "bfill",
            {"limit_area": "outside", "limit": 1},
        ),
    ),
)
def test_ffill_bfill_limit_area(data, expected_data, method, kwargs):
    # GH#56492
    df = DataFrame(data)
    expected = DataFrame(expected_data)
    result = getattr(df, method)(**kwargs)
    tm.assert_frame_equal(result, expected)
