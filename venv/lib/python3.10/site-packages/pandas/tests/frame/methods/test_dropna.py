import datetime

import dateutil
import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Series,
)
import pandas._testing as tm


class TestDataFrameMissingData:
    def test_dropEmptyRows(self, float_frame):
        N = len(float_frame.index)
        mat = np.random.default_rng(2).standard_normal(N)
        mat[:5] = np.nan

        frame = DataFrame({"foo": mat}, index=float_frame.index)
        original = Series(mat, index=float_frame.index, name="foo")
        expected = original.dropna()
        inplace_frame1, inplace_frame2 = frame.copy(), frame.copy()

        smaller_frame = frame.dropna(how="all")
        # check that original was preserved
        tm.assert_series_equal(frame["foo"], original)
        return_value = inplace_frame1.dropna(how="all", inplace=True)
        tm.assert_series_equal(smaller_frame["foo"], expected)
        tm.assert_series_equal(inplace_frame1["foo"], expected)
        assert return_value is None

        smaller_frame = frame.dropna(how="all", subset=["foo"])
        return_value = inplace_frame2.dropna(how="all", subset=["foo"], inplace=True)
        tm.assert_series_equal(smaller_frame["foo"], expected)
        tm.assert_series_equal(inplace_frame2["foo"], expected)
        assert return_value is None

    def test_dropIncompleteRows(self, float_frame):
        N = len(float_frame.index)
        mat = np.random.default_rng(2).standard_normal(N)
        mat[:5] = np.nan

        frame = DataFrame({"foo": mat}, index=float_frame.index)
        frame["bar"] = 5
        original = Series(mat, index=float_frame.index, name="foo")
        inp_frame1, inp_frame2 = frame.copy(), frame.copy()

        smaller_frame = frame.dropna()
        tm.assert_series_equal(frame["foo"], original)
        return_value = inp_frame1.dropna(inplace=True)

        exp = Series(mat[5:], index=float_frame.index[5:], name="foo")
        tm.assert_series_equal(smaller_frame["foo"], exp)
        tm.assert_series_equal(inp_frame1["foo"], exp)
        assert return_value is None

        samesize_frame = frame.dropna(subset=["bar"])
        tm.assert_series_equal(frame["foo"], original)
        assert (frame["bar"] == 5).all()
        return_value = inp_frame2.dropna(subset=["bar"], inplace=True)
        tm.assert_index_equal(samesize_frame.index, float_frame.index)
        tm.assert_index_equal(inp_frame2.index, float_frame.index)
        assert return_value is None

    def test_dropna(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((6, 4)))
        df.iloc[:2, 2] = np.nan

        dropped = df.dropna(axis=1)
        expected = df.loc[:, [0, 1, 3]]
        inp = df.copy()
        return_value = inp.dropna(axis=1, inplace=True)
        tm.assert_frame_equal(dropped, expected)
        tm.assert_frame_equal(inp, expected)
        assert return_value is None

        dropped = df.dropna(axis=0)
        expected = df.loc[list(range(2, 6))]
        inp = df.copy()
        return_value = inp.dropna(axis=0, inplace=True)
        tm.assert_frame_equal(dropped, expected)
        tm.assert_frame_equal(inp, expected)
        assert return_value is None

        # threshold
        dropped = df.dropna(axis=1, thresh=5)
        expected = df.loc[:, [0, 1, 3]]
        inp = df.copy()
        return_value = inp.dropna(axis=1, thresh=5, inplace=True)
        tm.assert_frame_equal(dropped, expected)
        tm.assert_frame_equal(inp, expected)
        assert return_value is None

        dropped = df.dropna(axis=0, thresh=4)
        expected = df.loc[range(2, 6)]
        inp = df.copy()
        return_value = inp.dropna(axis=0, thresh=4, inplace=True)
        tm.assert_frame_equal(dropped, expected)
        tm.assert_frame_equal(inp, expected)
        assert return_value is None

        dropped = df.dropna(axis=1, thresh=4)
        tm.assert_frame_equal(dropped, df)

        dropped = df.dropna(axis=1, thresh=3)
        tm.assert_frame_equal(dropped, df)

        # subset
        dropped = df.dropna(axis=0, subset=[0, 1, 3])
        inp = df.copy()
        return_value = inp.dropna(axis=0, subset=[0, 1, 3], inplace=True)
        tm.assert_frame_equal(dropped, df)
        tm.assert_frame_equal(inp, df)
        assert return_value is None

        # all
        dropped = df.dropna(axis=1, how="all")
        tm.assert_frame_equal(dropped, df)

        df[2] = np.nan
        dropped = df.dropna(axis=1, how="all")
        expected = df.loc[:, [0, 1, 3]]
        tm.assert_frame_equal(dropped, expected)

        # bad input
        msg = "No axis named 3 for object type DataFrame"
        with pytest.raises(ValueError, match=msg):
            df.dropna(axis=3)

    def test_drop_and_dropna_caching(self):
        # tst that cacher updates
        original = Series([1, 2, np.nan], name="A")
        expected = Series([1, 2], dtype=original.dtype, name="A")
        df = DataFrame({"A": original.values.copy()})
        df2 = df.copy()
        df["A"].dropna()
        tm.assert_series_equal(df["A"], original)

        ser = df["A"]
        return_value = ser.dropna(inplace=True)
        tm.assert_series_equal(ser, expected)
        tm.assert_series_equal(df["A"], original)
        assert return_value is None

        df2["A"].drop([1])
        tm.assert_series_equal(df2["A"], original)

        ser = df2["A"]
        return_value = ser.drop([1], inplace=True)
        tm.assert_series_equal(ser, original.drop([1]))
        tm.assert_series_equal(df2["A"], original)
        assert return_value is None

    def test_dropna_corner(self, float_frame):
        # bad input
        msg = "invalid how option: foo"
        with pytest.raises(ValueError, match=msg):
            float_frame.dropna(how="foo")
        # non-existent column - 8303
        with pytest.raises(KeyError, match=r"^\['X'\]$"):
            float_frame.dropna(subset=["A", "X"])

    def test_dropna_multiple_axes(self):
        df = DataFrame(
            [
                [1, np.nan, 2, 3],
                [4, np.nan, 5, 6],
                [np.nan, np.nan, np.nan, np.nan],
                [7, np.nan, 8, 9],
            ]
        )

        # GH20987
        with pytest.raises(TypeError, match="supplying multiple axes"):
            df.dropna(how="all", axis=[0, 1])
        with pytest.raises(TypeError, match="supplying multiple axes"):
            df.dropna(how="all", axis=(0, 1))

        inp = df.copy()
        with pytest.raises(TypeError, match="supplying multiple axes"):
            inp.dropna(how="all", axis=(0, 1), inplace=True)

    def test_dropna_tz_aware_datetime(self):
        # GH13407
        df = DataFrame()
        dt1 = datetime.datetime(2015, 1, 1, tzinfo=dateutil.tz.tzutc())
        dt2 = datetime.datetime(2015, 2, 2, tzinfo=dateutil.tz.tzutc())
        df["Time"] = [dt1]
        result = df.dropna(axis=0)
        expected = DataFrame({"Time": [dt1]})
        tm.assert_frame_equal(result, expected)

        # Ex2
        df = DataFrame({"Time": [dt1, None, np.nan, dt2]})
        result = df.dropna(axis=0)
        expected = DataFrame([dt1, dt2], columns=["Time"], index=[0, 3])
        tm.assert_frame_equal(result, expected)

    def test_dropna_categorical_interval_index(self):
        # GH 25087
        ii = pd.IntervalIndex.from_breaks([0, 2.78, 3.14, 6.28])
        ci = pd.CategoricalIndex(ii)
        df = DataFrame({"A": list("abc")}, index=ci)

        expected = df
        result = df.dropna()
        tm.assert_frame_equal(result, expected)

    def test_dropna_with_duplicate_columns(self):
        df = DataFrame(
            {
                "A": np.random.default_rng(2).standard_normal(5),
                "B": np.random.default_rng(2).standard_normal(5),
                "C": np.random.default_rng(2).standard_normal(5),
                "D": ["a", "b", "c", "d", "e"],
            }
        )
        df.iloc[2, [0, 1, 2]] = np.nan
        df.iloc[0, 0] = np.nan
        df.iloc[1, 1] = np.nan
        df.iloc[:, 3] = np.nan
        expected = df.dropna(subset=["A", "B", "C"], how="all")
        expected.columns = ["A", "A", "B", "C"]

        df.columns = ["A", "A", "B", "C"]

        result = df.dropna(subset=["A", "C"], how="all")
        tm.assert_frame_equal(result, expected)

    def test_set_single_column_subset(self):
        # GH 41021
        df = DataFrame({"A": [1, 2, 3], "B": list("abc"), "C": [4, np.nan, 5]})
        expected = DataFrame(
            {"A": [1, 3], "B": list("ac"), "C": [4.0, 5.0]}, index=[0, 2]
        )
        result = df.dropna(subset="C")
        tm.assert_frame_equal(result, expected)

    def test_single_column_not_present_in_axis(self):
        # GH 41021
        df = DataFrame({"A": [1, 2, 3]})

        # Column not present
        with pytest.raises(KeyError, match="['D']"):
            df.dropna(subset="D", axis=0)

    def test_subset_is_nparray(self):
        # GH 41021
        df = DataFrame({"A": [1, 2, np.nan], "B": list("abc"), "C": [4, np.nan, 5]})
        expected = DataFrame({"A": [1.0], "B": ["a"], "C": [4.0]})
        result = df.dropna(subset=np.array(["A", "C"]))
        tm.assert_frame_equal(result, expected)

    def test_no_nans_in_frame(self, axis):
        # GH#41965
        df = DataFrame([[1, 2], [3, 4]], columns=pd.RangeIndex(0, 2))
        expected = df.copy()
        result = df.dropna(axis=axis)
        tm.assert_frame_equal(result, expected, check_index_type=True)

    def test_how_thresh_param_incompatible(self):
        # GH46575
        df = DataFrame([1, 2, pd.NA])
        msg = "You cannot set both the how and thresh arguments at the same time"
        with pytest.raises(TypeError, match=msg):
            df.dropna(how="all", thresh=2)

        with pytest.raises(TypeError, match=msg):
            df.dropna(how="any", thresh=2)

        with pytest.raises(TypeError, match=msg):
            df.dropna(how=None, thresh=None)

    @pytest.mark.parametrize("val", [1, 1.5])
    def test_dropna_ignore_index(self, val):
        # GH#31725
        df = DataFrame({"a": [1, 2, val]}, index=[3, 2, 1])
        result = df.dropna(ignore_index=True)
        expected = DataFrame({"a": [1, 2, val]})
        tm.assert_frame_equal(result, expected)

        df.dropna(ignore_index=True, inplace=True)
        tm.assert_frame_equal(df, expected)
