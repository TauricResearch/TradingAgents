"""
test setting *parts* of objects both positionally and label based

TODO: these should be split among the indexer tests
"""

import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    Period,
    Series,
    Timestamp,
    date_range,
    period_range,
)
import pandas._testing as tm


class TestEmptyFrameSetitemExpansion:
    def test_empty_frame_setitem_index_name_retained(self):
        # GH#31368 empty frame has non-None index.name -> retained
        df = DataFrame({}, index=pd.RangeIndex(0, name="df_index"))
        series = Series(1.23, index=pd.RangeIndex(4, name="series_index"))

        df["series"] = series
        expected = DataFrame(
            {"series": [1.23] * 4},
            index=pd.RangeIndex(4, name="df_index"),
            columns=Index(["series"]),
        )

        tm.assert_frame_equal(df, expected)

    def test_empty_frame_setitem_index_name_inherited(self):
        # GH#36527 empty frame has None index.name -> not retained
        df = DataFrame()
        series = Series(1.23, index=pd.RangeIndex(4, name="series_index"))
        df["series"] = series
        expected = DataFrame(
            {"series": [1.23] * 4},
            index=pd.RangeIndex(4, name="series_index"),
            columns=Index(["series"]),
        )
        tm.assert_frame_equal(df, expected)

    def test_loc_setitem_zerolen_series_columns_align(self):
        # columns will align
        df = DataFrame(columns=["A", "B"])
        df.loc[0] = Series(1, index=range(4))
        expected = DataFrame(columns=["A", "B"], index=[0], dtype=np.float64)
        tm.assert_frame_equal(df, expected)

        # columns will align
        df = DataFrame(columns=["A", "B"])
        df.loc[0] = Series(1, index=["B"])

        exp = DataFrame([[np.nan, 1]], columns=["A", "B"], index=[0], dtype="float64")
        tm.assert_frame_equal(df, exp)

    def test_loc_setitem_zerolen_list_length_must_match_columns(self):
        # list-like must conform
        df = DataFrame(columns=["A", "B"])

        msg = "cannot set a row with mismatched columns"
        with pytest.raises(ValueError, match=msg):
            df.loc[0] = [1, 2, 3]

        df = DataFrame(columns=["A", "B"])
        df.loc[3] = [6, 7]  # length matches len(df.columns) --> OK!

        exp = DataFrame([[6, 7]], index=[3], columns=["A", "B"], dtype=np.int64)
        tm.assert_frame_equal(df, exp)

    def test_partial_set_empty_frame(self):
        # partially set with an empty object
        # frame
        df = DataFrame()

        msg = "cannot set a frame with no defined columns"

        with pytest.raises(ValueError, match=msg):
            df.loc[1] = 1

        with pytest.raises(ValueError, match=msg):
            df.loc[1] = Series([1], index=["foo"])

        msg = "cannot set a frame with no defined index and a scalar"
        with pytest.raises(ValueError, match=msg):
            df.loc[:, 1] = 1

    def test_partial_set_empty_frame2(self):
        # these work as they don't really change
        # anything but the index
        # GH#5632
        expected = DataFrame(columns=Index(["foo"]), index=Index([], dtype="object"))

        df = DataFrame(index=Index([], dtype="object"))
        df["foo"] = Series([], dtype="object")

        tm.assert_frame_equal(df, expected)

        df = DataFrame(index=Index([]))
        df["foo"] = Series(df.index)

        tm.assert_frame_equal(df, expected)

        df = DataFrame(index=Index([]))
        df["foo"] = df.index

        tm.assert_frame_equal(df, expected)

    def test_partial_set_empty_frame3(self):
        expected = DataFrame(columns=Index(["foo"]), index=Index([], dtype="int64"))
        expected["foo"] = expected["foo"].astype("float64")

        df = DataFrame(index=Index([], dtype="int64"))
        df["foo"] = []

        tm.assert_frame_equal(df, expected)

        df = DataFrame(index=Index([], dtype="int64"))
        df["foo"] = Series(np.arange(len(df)), dtype="float64")

        tm.assert_frame_equal(df, expected)

    def test_partial_set_empty_frame4(self):
        df = DataFrame(index=Index([], dtype="int64"))
        df["foo"] = range(len(df))

        expected = DataFrame(columns=Index(["foo"]), index=Index([], dtype="int64"))
        # range is int-dtype-like, so we get int64 dtype
        expected["foo"] = expected["foo"].astype("int64")
        tm.assert_frame_equal(df, expected)

    def test_partial_set_empty_frame5(self):
        df = DataFrame()
        tm.assert_index_equal(df.columns, pd.RangeIndex(0))
        df2 = DataFrame()
        df2[1] = Series([1], index=["foo"])
        df.loc[:, 1] = Series([1], index=["foo"])
        tm.assert_frame_equal(df, DataFrame([[1]], index=["foo"], columns=[1]))
        tm.assert_frame_equal(df, df2)

    def test_partial_set_empty_frame_no_index(self):
        # no index to start
        expected = DataFrame({0: Series(1, index=range(4))}, columns=["A", "B", 0])

        df = DataFrame(columns=["A", "B"])
        df[0] = Series(1, index=range(4))
        tm.assert_frame_equal(df, expected)

        df = DataFrame(columns=["A", "B"])
        df.loc[:, 0] = Series(1, index=range(4))
        tm.assert_frame_equal(df, expected)

    def test_partial_set_empty_frame_row(self):
        # GH#5720, GH#5744
        # don't create rows when empty
        expected = DataFrame(columns=["A", "B", "New"], index=Index([], dtype="int64"))
        expected["A"] = expected["A"].astype("int64")
        expected["B"] = expected["B"].astype("float64")
        expected["New"] = expected["New"].astype("float64")

        df = DataFrame({"A": [1, 2, 3], "B": [1.2, 4.2, 5.2]})
        y = df[df.A > 5]
        y["New"] = np.nan
        tm.assert_frame_equal(y, expected)

        expected = DataFrame(columns=["a", "b", "c c", "d"])
        expected["d"] = expected["d"].astype("int64")
        df = DataFrame(columns=["a", "b", "c c"])
        df["d"] = 3
        tm.assert_frame_equal(df, expected)
        tm.assert_series_equal(df["c c"], Series(name="c c", dtype=object))

        # reindex columns is ok
        df = DataFrame({"A": [1, 2, 3], "B": [1.2, 4.2, 5.2]})
        y = df[df.A > 5]
        result = y.reindex(columns=["A", "B", "C"])
        expected = DataFrame(columns=["A", "B", "C"])
        expected["A"] = expected["A"].astype("int64")
        expected["B"] = expected["B"].astype("float64")
        expected["C"] = expected["C"].astype("float64")
        tm.assert_frame_equal(result, expected)

    def test_partial_set_empty_frame_set_series(self):
        # GH#5756
        # setting with empty Series
        df = DataFrame(Series(dtype=object))
        expected = DataFrame({0: Series(dtype=object)})
        tm.assert_frame_equal(df, expected)

        df = DataFrame(Series(name="foo", dtype=object))
        expected = DataFrame({"foo": Series(dtype=object)})
        tm.assert_frame_equal(df, expected)

    def test_partial_set_empty_frame_empty_copy_assignment(self):
        # GH#5932
        # copy on empty with assignment fails
        df = DataFrame(index=[0])
        df = df.copy()
        df["a"] = 0
        expected = DataFrame(0, index=[0], columns=Index(["a"]))
        tm.assert_frame_equal(df, expected)

    def test_partial_set_empty_frame_empty_consistencies(self, using_infer_string):
        # GH#6171
        # consistency on empty frames
        df = DataFrame(columns=["x", "y"])
        df["x"] = [1, 2]
        expected = DataFrame({"x": [1, 2], "y": [np.nan, np.nan]})
        tm.assert_frame_equal(df, expected, check_dtype=False)

        df = DataFrame(columns=["x", "y"])
        df["x"] = ["1", "2"]
        expected = DataFrame(
            {
                "x": Series(
                    ["1", "2"],
                    dtype=object if not using_infer_string else "str",
                ),
                "y": Series([np.nan, np.nan], dtype=object),
            }
        )
        tm.assert_frame_equal(df, expected)

        df = DataFrame(columns=["x", "y"])
        df.loc[0, "x"] = 1
        expected = DataFrame({"x": [1], "y": [np.nan]})
        tm.assert_frame_equal(df, expected, check_dtype=False)


class TestPartialSetting:
    def test_partial_setting(self):
        # GH2578, allow ix and friends to partially set

        # series
        s_orig = Series([1, 2, 3])

        s = s_orig.copy()
        s[5] = 5
        expected = Series([1, 2, 3, 5], index=[0, 1, 2, 5])
        tm.assert_series_equal(s, expected)

        s = s_orig.copy()
        s.loc[5] = 5
        expected = Series([1, 2, 3, 5], index=[0, 1, 2, 5])
        tm.assert_series_equal(s, expected)

        s = s_orig.copy()
        s[5] = 5.0
        expected = Series([1, 2, 3, 5.0], index=[0, 1, 2, 5])
        tm.assert_series_equal(s, expected)

        s = s_orig.copy()
        s.loc[5] = 5.0
        expected = Series([1, 2, 3, 5.0], index=[0, 1, 2, 5])
        tm.assert_series_equal(s, expected)

        # iloc/iat raise
        s = s_orig.copy()

        msg = "iloc cannot enlarge its target object"
        with pytest.raises(IndexError, match=msg):
            s.iloc[3] = 5.0

        msg = "index 3 is out of bounds for axis 0 with size 3"
        with pytest.raises(IndexError, match=msg):
            s.iat[3] = 5.0

    @pytest.mark.filterwarnings("ignore:Setting a value on a view:FutureWarning")
    def test_partial_setting_frame(self, using_array_manager):
        df_orig = DataFrame(
            np.arange(6).reshape(3, 2), columns=["A", "B"], dtype="int64"
        )

        # iloc/iat raise
        df = df_orig.copy()

        msg = "iloc cannot enlarge its target object"
        with pytest.raises(IndexError, match=msg):
            df.iloc[4, 2] = 5.0

        msg = "index 2 is out of bounds for axis 0 with size 2"
        if using_array_manager:
            msg = "list index out of range"
        with pytest.raises(IndexError, match=msg):
            df.iat[4, 2] = 5.0

        # row setting where it exists
        expected = DataFrame({"A": [0, 4, 4], "B": [1, 5, 5]})
        df = df_orig.copy()
        df.iloc[1] = df.iloc[2]
        tm.assert_frame_equal(df, expected)

        expected = DataFrame({"A": [0, 4, 4], "B": [1, 5, 5]})
        df = df_orig.copy()
        df.loc[1] = df.loc[2]
        tm.assert_frame_equal(df, expected)

        # like 2578, partial setting with dtype preservation
        expected = DataFrame({"A": [0, 2, 4, 4], "B": [1, 3, 5, 5]})
        df = df_orig.copy()
        df.loc[3] = df.loc[2]
        tm.assert_frame_equal(df, expected)

        # single dtype frame, overwrite
        expected = DataFrame({"A": [0, 2, 4], "B": [0, 2, 4]})
        df = df_orig.copy()
        df.loc[:, "B"] = df.loc[:, "A"]
        tm.assert_frame_equal(df, expected)

        # mixed dtype frame, overwrite
        expected = DataFrame({"A": [0, 2, 4], "B": Series([0.0, 2.0, 4.0])})
        df = df_orig.copy()
        df["B"] = df["B"].astype(np.float64)
        # as of 2.0, df.loc[:, "B"] = ... attempts (and here succeeds) at
        #  setting inplace
        df.loc[:, "B"] = df.loc[:, "A"]
        tm.assert_frame_equal(df, expected)

        # single dtype frame, partial setting
        expected = df_orig.copy()
        expected["C"] = df["A"]
        df = df_orig.copy()
        df.loc[:, "C"] = df.loc[:, "A"]
        tm.assert_frame_equal(df, expected)

        # mixed frame, partial setting
        expected = df_orig.copy()
        expected["C"] = df["A"]
        df = df_orig.copy()
        df.loc[:, "C"] = df.loc[:, "A"]
        tm.assert_frame_equal(df, expected)

    def test_partial_setting2(self):
        # GH 8473
        dates = date_range("1/1/2000", periods=8)
        df_orig = DataFrame(
            np.random.default_rng(2).standard_normal((8, 4)),
            index=dates,
            columns=["A", "B", "C", "D"],
        )

        expected = pd.concat(
            [df_orig, DataFrame({"A": 7}, index=dates[-1:] + dates.freq)], sort=True
        )
        df = df_orig.copy()
        df.loc[dates[-1] + dates.freq, "A"] = 7
        tm.assert_frame_equal(df, expected)
        df = df_orig.copy()
        df.at[dates[-1] + dates.freq, "A"] = 7
        tm.assert_frame_equal(df, expected)

        exp_other = DataFrame({0: 7}, index=dates[-1:] + dates.freq)
        expected = pd.concat([df_orig, exp_other], axis=1)

        df = df_orig.copy()
        df.loc[dates[-1] + dates.freq, 0] = 7
        tm.assert_frame_equal(df, expected)
        df = df_orig.copy()
        df.at[dates[-1] + dates.freq, 0] = 7
        tm.assert_frame_equal(df, expected)

    def test_partial_setting_mixed_dtype(self):
        # in a mixed dtype environment, try to preserve dtypes
        # by appending
        df = DataFrame([[True, 1], [False, 2]], columns=["female", "fitness"])

        s = df.loc[1].copy()
        s.name = 2
        expected = pd.concat([df, DataFrame(s).T.infer_objects()])

        df.loc[2] = df.loc[1]
        tm.assert_frame_equal(df, expected)

    def test_series_partial_set(self):
        # partial set with new index
        # Regression from GH4825
        ser = Series([0.1, 0.2], index=[1, 2])

        # loc equiv to .reindex
        expected = Series([np.nan, 0.2, np.nan], index=[3, 2, 3])
        with pytest.raises(KeyError, match=r"not in index"):
            ser.loc[[3, 2, 3]]

        result = ser.reindex([3, 2, 3])
        tm.assert_series_equal(result, expected, check_index_type=True)

        expected = Series([np.nan, 0.2, np.nan, np.nan], index=[3, 2, 3, "x"])
        with pytest.raises(KeyError, match="not in index"):
            ser.loc[[3, 2, 3, "x"]]

        result = ser.reindex([3, 2, 3, "x"])
        tm.assert_series_equal(result, expected, check_index_type=True)

        expected = Series([0.2, 0.2, 0.1], index=[2, 2, 1])
        result = ser.loc[[2, 2, 1]]
        tm.assert_series_equal(result, expected, check_index_type=True)

        expected = Series([0.2, 0.2, np.nan, 0.1], index=[2, 2, "x", 1])
        with pytest.raises(KeyError, match="not in index"):
            ser.loc[[2, 2, "x", 1]]

        result = ser.reindex([2, 2, "x", 1])
        tm.assert_series_equal(result, expected, check_index_type=True)

        # raises as nothing is in the index
        msg = (
            rf"\"None of \[Index\(\[3, 3, 3\], dtype='{np.dtype(int)}'\)\] "
            r"are in the \[index\]\""
        )
        with pytest.raises(KeyError, match=msg):
            ser.loc[[3, 3, 3]]

        expected = Series([0.2, 0.2, np.nan], index=[2, 2, 3])
        with pytest.raises(KeyError, match="not in index"):
            ser.loc[[2, 2, 3]]

        result = ser.reindex([2, 2, 3])
        tm.assert_series_equal(result, expected, check_index_type=True)

        s = Series([0.1, 0.2, 0.3], index=[1, 2, 3])
        expected = Series([0.3, np.nan, np.nan], index=[3, 4, 4])
        with pytest.raises(KeyError, match="not in index"):
            s.loc[[3, 4, 4]]

        result = s.reindex([3, 4, 4])
        tm.assert_series_equal(result, expected, check_index_type=True)

        s = Series([0.1, 0.2, 0.3, 0.4], index=[1, 2, 3, 4])
        expected = Series([np.nan, 0.3, 0.3], index=[5, 3, 3])
        with pytest.raises(KeyError, match="not in index"):
            s.loc[[5, 3, 3]]

        result = s.reindex([5, 3, 3])
        tm.assert_series_equal(result, expected, check_index_type=True)

        s = Series([0.1, 0.2, 0.3, 0.4], index=[1, 2, 3, 4])
        expected = Series([np.nan, 0.4, 0.4], index=[5, 4, 4])
        with pytest.raises(KeyError, match="not in index"):
            s.loc[[5, 4, 4]]

        result = s.reindex([5, 4, 4])
        tm.assert_series_equal(result, expected, check_index_type=True)

        s = Series([0.1, 0.2, 0.3, 0.4], index=[4, 5, 6, 7])
        expected = Series([0.4, np.nan, np.nan], index=[7, 2, 2])
        with pytest.raises(KeyError, match="not in index"):
            s.loc[[7, 2, 2]]

        result = s.reindex([7, 2, 2])
        tm.assert_series_equal(result, expected, check_index_type=True)

        s = Series([0.1, 0.2, 0.3, 0.4], index=[1, 2, 3, 4])
        expected = Series([0.4, np.nan, np.nan], index=[4, 5, 5])
        with pytest.raises(KeyError, match="not in index"):
            s.loc[[4, 5, 5]]

        result = s.reindex([4, 5, 5])
        tm.assert_series_equal(result, expected, check_index_type=True)

        # iloc
        expected = Series([0.2, 0.2, 0.1, 0.1], index=[2, 2, 1, 1])
        result = ser.iloc[[1, 1, 0, 0]]
        tm.assert_series_equal(result, expected, check_index_type=True)

    def test_series_partial_set_with_name(self):
        # GH 11497

        idx = Index([1, 2], dtype="int64", name="idx")
        ser = Series([0.1, 0.2], index=idx, name="s")

        # loc
        with pytest.raises(KeyError, match=r"\[3\] not in index"):
            ser.loc[[3, 2, 3]]

        with pytest.raises(KeyError, match=r"not in index"):
            ser.loc[[3, 2, 3, "x"]]

        exp_idx = Index([2, 2, 1], dtype="int64", name="idx")
        expected = Series([0.2, 0.2, 0.1], index=exp_idx, name="s")
        result = ser.loc[[2, 2, 1]]
        tm.assert_series_equal(result, expected, check_index_type=True)

        with pytest.raises(KeyError, match=r"\['x'\] not in index"):
            ser.loc[[2, 2, "x", 1]]

        # raises as nothing is in the index
        msg = (
            rf"\"None of \[Index\(\[3, 3, 3\], dtype='{np.dtype(int)}', "
            r"name='idx'\)\] are in the \[index\]\""
        )
        with pytest.raises(KeyError, match=msg):
            ser.loc[[3, 3, 3]]

        with pytest.raises(KeyError, match="not in index"):
            ser.loc[[2, 2, 3]]

        idx = Index([1, 2, 3], dtype="int64", name="idx")
        with pytest.raises(KeyError, match="not in index"):
            Series([0.1, 0.2, 0.3], index=idx, name="s").loc[[3, 4, 4]]

        idx = Index([1, 2, 3, 4], dtype="int64", name="idx")
        with pytest.raises(KeyError, match="not in index"):
            Series([0.1, 0.2, 0.3, 0.4], index=idx, name="s").loc[[5, 3, 3]]

        idx = Index([1, 2, 3, 4], dtype="int64", name="idx")
        with pytest.raises(KeyError, match="not in index"):
            Series([0.1, 0.2, 0.3, 0.4], index=idx, name="s").loc[[5, 4, 4]]

        idx = Index([4, 5, 6, 7], dtype="int64", name="idx")
        with pytest.raises(KeyError, match="not in index"):
            Series([0.1, 0.2, 0.3, 0.4], index=idx, name="s").loc[[7, 2, 2]]

        idx = Index([1, 2, 3, 4], dtype="int64", name="idx")
        with pytest.raises(KeyError, match="not in index"):
            Series([0.1, 0.2, 0.3, 0.4], index=idx, name="s").loc[[4, 5, 5]]

        # iloc
        exp_idx = Index([2, 2, 1, 1], dtype="int64", name="idx")
        expected = Series([0.2, 0.2, 0.1, 0.1], index=exp_idx, name="s")
        result = ser.iloc[[1, 1, 0, 0]]
        tm.assert_series_equal(result, expected, check_index_type=True)

    @pytest.mark.parametrize("key", [100, 100.0])
    def test_setitem_with_expansion_numeric_into_datetimeindex(self, key):
        # GH#4940 inserting non-strings
        orig = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        df = orig.copy()

        df.loc[key, :] = df.iloc[0]
        ex_index = Index(list(orig.index) + [key], dtype=object, name=orig.index.name)
        ex_data = np.concatenate([orig.values, df.iloc[[0]].values], axis=0)
        expected = DataFrame(ex_data, index=ex_index, columns=orig.columns)

        tm.assert_frame_equal(df, expected)

    def test_partial_set_invalid(self):
        # GH 4940
        # allow only setting of 'valid' values

        orig = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )

        # allow object conversion here
        df = orig.copy()
        df.loc["a", :] = df.iloc[0]
        ser = Series(df.iloc[0], name="a")
        exp = pd.concat([orig, DataFrame(ser).T.infer_objects()])
        tm.assert_frame_equal(df, exp)
        tm.assert_index_equal(df.index, Index(orig.index.tolist() + ["a"]))
        assert df.index.dtype == "object"

    @pytest.mark.parametrize(
        "idx,labels,expected_idx",
        [
            (
                period_range(start="2000", periods=20, freq="D"),
                ["2000-01-04", "2000-01-08", "2000-01-12"],
                [
                    Period("2000-01-04", freq="D"),
                    Period("2000-01-08", freq="D"),
                    Period("2000-01-12", freq="D"),
                ],
            ),
            (
                date_range(start="2000", periods=20, freq="D"),
                ["2000-01-04", "2000-01-08", "2000-01-12"],
                [
                    Timestamp("2000-01-04"),
                    Timestamp("2000-01-08"),
                    Timestamp("2000-01-12"),
                ],
            ),
            (
                pd.timedelta_range(start="1 day", periods=20),
                ["4D", "8D", "12D"],
                [pd.Timedelta("4 day"), pd.Timedelta("8 day"), pd.Timedelta("12 day")],
            ),
        ],
    )
    def test_loc_with_list_of_strings_representing_datetimes(
        self, idx, labels, expected_idx, frame_or_series
    ):
        # GH 11278
        obj = frame_or_series(range(20), index=idx)

        expected_value = [3, 7, 11]
        expected = frame_or_series(expected_value, expected_idx)

        tm.assert_equal(expected, obj.loc[labels])
        if frame_or_series is Series:
            tm.assert_series_equal(expected, obj[labels])

    @pytest.mark.parametrize(
        "idx,labels",
        [
            (
                period_range(start="2000", periods=20, freq="D"),
                ["2000-01-04", "2000-01-30"],
            ),
            (
                date_range(start="2000", periods=20, freq="D"),
                ["2000-01-04", "2000-01-30"],
            ),
            (pd.timedelta_range(start="1 day", periods=20), ["3 day", "30 day"]),
        ],
    )
    def test_loc_with_list_of_strings_representing_datetimes_missing_value(
        self, idx, labels
    ):
        # GH 11278
        ser = Series(range(20), index=idx)
        df = DataFrame(range(20), index=idx)
        msg = r"not in index"

        with pytest.raises(KeyError, match=msg):
            ser.loc[labels]
        with pytest.raises(KeyError, match=msg):
            ser[labels]
        with pytest.raises(KeyError, match=msg):
            df.loc[labels]

    @pytest.mark.parametrize(
        "idx,labels,msg",
        [
            (
                period_range(start="2000", periods=20, freq="D"),
                Index(["4D", "8D"], dtype=object),
                (
                    r"None of \[Index\(\['4D', '8D'\], dtype='object'\)\] "
                    r"are in the \[index\]"
                ),
            ),
            (
                date_range(start="2000", periods=20, freq="D"),
                Index(["4D", "8D"], dtype=object),
                (
                    r"None of \[Index\(\['4D', '8D'\], dtype='object'\)\] "
                    r"are in the \[index\]"
                ),
            ),
            (
                pd.timedelta_range(start="1 day", periods=20),
                Index(["2000-01-04", "2000-01-08"], dtype=object),
                (
                    r"None of \[Index\(\['2000-01-04', '2000-01-08'\], "
                    r"dtype='object'\)\] are in the \[index\]"
                ),
            ),
        ],
    )
    def test_loc_with_list_of_strings_representing_datetimes_not_matched_type(
        self, idx, labels, msg
    ):
        # GH 11278
        ser = Series(range(20), index=idx)
        df = DataFrame(range(20), index=idx)

        with pytest.raises(KeyError, match=msg):
            ser.loc[labels]
        with pytest.raises(KeyError, match=msg):
            ser[labels]
        with pytest.raises(KeyError, match=msg):
            df.loc[labels]


class TestStringSlicing:
    def test_slice_irregular_datetime_index_with_nan(self):
        # GH36953
        index = pd.to_datetime(["2012-01-01", "2012-01-02", "2012-01-03", None])
        df = DataFrame(range(len(index)), index=index)
        expected = DataFrame(range(len(index[:3])), index=index[:3])
        with pytest.raises(KeyError, match="non-existing keys is not allowed"):
            # Upper bound is not in index (which is unordered)
            # GH53983
            # GH37819
            df["2012-01-01":"2012-01-04"]
        # Need this precision for right bound since the right slice
        # bound is "rounded" up to the largest timepoint smaller than
        # the next "resolution"-step of the provided point.
        # e.g. 2012-01-03 is rounded up to 2012-01-04 - 1ns
        result = df["2012-01-01":"2012-01-03 00:00:00.000000000"]
        tm.assert_frame_equal(result, expected)
