from datetime import timezone

import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    Series,
    date_range,
)
import pandas._testing as tm


class TestDataFrameAlign:
    def test_align_asfreq_method_raises(self):
        df = DataFrame({"A": [1, np.nan, 2]})
        msg = "Invalid fill method"
        msg2 = "The 'method', 'limit', and 'fill_axis' keywords"
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=msg2):
                df.align(df.iloc[::-1], method="asfreq")

    def test_frame_align_aware(self):
        idx1 = date_range("2001", periods=5, freq="h", tz="US/Eastern")
        idx2 = date_range("2001", periods=5, freq="2h", tz="US/Eastern")
        df1 = DataFrame(np.random.default_rng(2).standard_normal((len(idx1), 3)), idx1)
        df2 = DataFrame(np.random.default_rng(2).standard_normal((len(idx2), 3)), idx2)
        new1, new2 = df1.align(df2)
        assert df1.index.tz == new1.index.tz
        assert df2.index.tz == new2.index.tz

        # different timezones convert to UTC

        # frame with frame
        df1_central = df1.tz_convert("US/Central")
        new1, new2 = df1.align(df1_central)
        assert new1.index.tz is timezone.utc
        assert new2.index.tz is timezone.utc

        # frame with Series
        new1, new2 = df1.align(df1_central[0], axis=0)
        assert new1.index.tz is timezone.utc
        assert new2.index.tz is timezone.utc

        df1[0].align(df1_central, axis=0)
        assert new1.index.tz is timezone.utc
        assert new2.index.tz is timezone.utc

    def test_align_float(self, float_frame, using_copy_on_write):
        af, bf = float_frame.align(float_frame)
        assert af._mgr is not float_frame._mgr

        af, bf = float_frame.align(float_frame, copy=False)
        if not using_copy_on_write:
            assert af._mgr is float_frame._mgr
        else:
            assert af._mgr is not float_frame._mgr

        # axis = 0
        other = float_frame.iloc[:-5, :3]
        af, bf = float_frame.align(other, axis=0, fill_value=-1)

        tm.assert_index_equal(bf.columns, other.columns)

        # test fill value
        join_idx = float_frame.index.join(other.index)
        diff_a = float_frame.index.difference(join_idx)
        diff_a_vals = af.reindex(diff_a).values
        assert (diff_a_vals == -1).all()

        af, bf = float_frame.align(other, join="right", axis=0)
        tm.assert_index_equal(bf.columns, other.columns)
        tm.assert_index_equal(bf.index, other.index)
        tm.assert_index_equal(af.index, other.index)

        # axis = 1
        other = float_frame.iloc[:-5, :3].copy()
        af, bf = float_frame.align(other, axis=1)
        tm.assert_index_equal(bf.columns, float_frame.columns)
        tm.assert_index_equal(bf.index, other.index)

        # test fill value
        join_idx = float_frame.index.join(other.index)
        diff_a = float_frame.index.difference(join_idx)
        diff_a_vals = af.reindex(diff_a).values

        assert (diff_a_vals == -1).all()

        af, bf = float_frame.align(other, join="inner", axis=1)
        tm.assert_index_equal(bf.columns, other.columns)

        msg = (
            "The 'method', 'limit', and 'fill_axis' keywords in DataFrame.align "
            "are deprecated"
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            af, bf = float_frame.align(other, join="inner", axis=1, method="pad")
        tm.assert_index_equal(bf.columns, other.columns)

        msg = (
            "The 'method', 'limit', and 'fill_axis' keywords in DataFrame.align "
            "are deprecated"
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            af, bf = float_frame.align(
                other.iloc[:, 0], join="inner", axis=1, method=None, fill_value=None
            )
        tm.assert_index_equal(bf.index, Index([]).astype(bf.index.dtype))

        msg = (
            "The 'method', 'limit', and 'fill_axis' keywords in DataFrame.align "
            "are deprecated"
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            af, bf = float_frame.align(
                other.iloc[:, 0], join="inner", axis=1, method=None, fill_value=0
            )
        tm.assert_index_equal(bf.index, Index([]).astype(bf.index.dtype))

        # Try to align DataFrame to Series along bad axis
        msg = "No axis named 2 for object type DataFrame"
        with pytest.raises(ValueError, match=msg):
            float_frame.align(af.iloc[0, :3], join="inner", axis=2)

    def test_align_frame_with_series(self, float_frame):
        # align dataframe to series with broadcast or not
        idx = float_frame.index
        s = Series(range(len(idx)), index=idx)

        left, right = float_frame.align(s, axis=0)
        tm.assert_index_equal(left.index, float_frame.index)
        tm.assert_index_equal(right.index, float_frame.index)
        assert isinstance(right, Series)

        msg = "The 'broadcast_axis' keyword in DataFrame.align is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            left, right = float_frame.align(s, broadcast_axis=1)
        tm.assert_index_equal(left.index, float_frame.index)
        expected = {c: s for c in float_frame.columns}
        expected = DataFrame(
            expected, index=float_frame.index, columns=float_frame.columns
        )
        tm.assert_frame_equal(right, expected)

    def test_align_series_condition(self):
        # see gh-9558
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        result = df[df["a"] == 2]
        expected = DataFrame([[2, 5]], index=[1], columns=["a", "b"])
        tm.assert_frame_equal(result, expected)

        result = df.where(df["a"] == 2, 0)
        expected = DataFrame({"a": [0, 2, 0], "b": [0, 5, 0]})
        tm.assert_frame_equal(result, expected)

    def test_align_int(self, int_frame):
        # test other non-float types
        other = DataFrame(index=range(5), columns=["A", "B", "C"])

        msg = (
            "The 'method', 'limit', and 'fill_axis' keywords in DataFrame.align "
            "are deprecated"
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            af, bf = int_frame.align(other, join="inner", axis=1, method="pad")
        tm.assert_index_equal(bf.columns, other.columns)

    def test_align_mixed_type(self, float_string_frame):
        msg = (
            "The 'method', 'limit', and 'fill_axis' keywords in DataFrame.align "
            "are deprecated"
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            af, bf = float_string_frame.align(
                float_string_frame, join="inner", axis=1, method="pad"
            )
        tm.assert_index_equal(bf.columns, float_string_frame.columns)

    def test_align_mixed_float(self, mixed_float_frame):
        # mixed floats/ints
        other = DataFrame(index=range(5), columns=["A", "B", "C"])

        msg = (
            "The 'method', 'limit', and 'fill_axis' keywords in DataFrame.align "
            "are deprecated"
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            af, bf = mixed_float_frame.align(
                other.iloc[:, 0], join="inner", axis=1, method=None, fill_value=0
            )
        tm.assert_index_equal(bf.index, Index([]))

    def test_align_mixed_int(self, mixed_int_frame):
        other = DataFrame(index=range(5), columns=["A", "B", "C"])

        msg = (
            "The 'method', 'limit', and 'fill_axis' keywords in DataFrame.align "
            "are deprecated"
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            af, bf = mixed_int_frame.align(
                other.iloc[:, 0], join="inner", axis=1, method=None, fill_value=0
            )
        tm.assert_index_equal(bf.index, Index([]))

    @pytest.mark.parametrize(
        "l_ordered,r_ordered,expected",
        [
            [True, True, pd.CategoricalIndex],
            [True, False, Index],
            [False, True, Index],
            [False, False, pd.CategoricalIndex],
        ],
    )
    def test_align_categorical(self, l_ordered, r_ordered, expected):
        # GH-28397
        df_1 = DataFrame(
            {
                "A": np.arange(6, dtype="int64"),
                "B": Series(list("aabbca")).astype(
                    pd.CategoricalDtype(list("cab"), ordered=l_ordered)
                ),
            }
        ).set_index("B")
        df_2 = DataFrame(
            {
                "A": np.arange(5, dtype="int64"),
                "B": Series(list("babca")).astype(
                    pd.CategoricalDtype(list("cab"), ordered=r_ordered)
                ),
            }
        ).set_index("B")

        aligned_1, aligned_2 = df_1.align(df_2)
        assert isinstance(aligned_1.index, expected)
        assert isinstance(aligned_2.index, expected)
        tm.assert_index_equal(aligned_1.index, aligned_2.index)

    def test_align_multiindex(self):
        # GH#10665
        # same test cases as test_align_multiindex in test_series.py

        midx = pd.MultiIndex.from_product(
            [range(2), range(3), range(2)], names=("a", "b", "c")
        )
        idx = Index(range(2), name="b")
        df1 = DataFrame(np.arange(12, dtype="int64"), index=midx)
        df2 = DataFrame(np.arange(2, dtype="int64"), index=idx)

        # these must be the same results (but flipped)
        res1l, res1r = df1.align(df2, join="left")
        res2l, res2r = df2.align(df1, join="right")

        expl = df1
        tm.assert_frame_equal(expl, res1l)
        tm.assert_frame_equal(expl, res2r)
        expr = DataFrame([0, 0, 1, 1, np.nan, np.nan] * 2, index=midx)
        tm.assert_frame_equal(expr, res1r)
        tm.assert_frame_equal(expr, res2l)

        res1l, res1r = df1.align(df2, join="right")
        res2l, res2r = df2.align(df1, join="left")

        exp_idx = pd.MultiIndex.from_product(
            [range(2), range(2), range(2)], names=("a", "b", "c")
        )
        expl = DataFrame([0, 1, 2, 3, 6, 7, 8, 9], index=exp_idx)
        tm.assert_frame_equal(expl, res1l)
        tm.assert_frame_equal(expl, res2r)
        expr = DataFrame([0, 0, 1, 1] * 2, index=exp_idx)
        tm.assert_frame_equal(expr, res1r)
        tm.assert_frame_equal(expr, res2l)

    def test_align_series_combinations(self):
        df = DataFrame({"a": [1, 3, 5], "b": [1, 3, 5]}, index=list("ACE"))
        s = Series([1, 2, 4], index=list("ABD"), name="x")

        # frame + series
        res1, res2 = df.align(s, axis=0)
        exp1 = DataFrame(
            {"a": [1, np.nan, 3, np.nan, 5], "b": [1, np.nan, 3, np.nan, 5]},
            index=list("ABCDE"),
        )
        exp2 = Series([1, 2, np.nan, 4, np.nan], index=list("ABCDE"), name="x")

        tm.assert_frame_equal(res1, exp1)
        tm.assert_series_equal(res2, exp2)

        # series + frame
        res1, res2 = s.align(df)
        tm.assert_series_equal(res1, exp2)
        tm.assert_frame_equal(res2, exp1)

    def test_multiindex_align_to_series_with_common_index_level(self):
        #  GH-46001
        foo_index = Index([1, 2, 3], name="foo")
        bar_index = Index([1, 2], name="bar")

        series = Series([1, 2], index=bar_index, name="foo_series")
        df = DataFrame(
            {"col": np.arange(6)},
            index=pd.MultiIndex.from_product([foo_index, bar_index]),
        )

        expected_r = Series([1, 2] * 3, index=df.index, name="foo_series")
        result_l, result_r = df.align(series, axis=0)

        tm.assert_frame_equal(result_l, df)
        tm.assert_series_equal(result_r, expected_r)

    def test_multiindex_align_to_series_with_common_index_level_missing_in_left(self):
        #  GH-46001
        foo_index = Index([1, 2, 3], name="foo")
        bar_index = Index([1, 2], name="bar")

        series = Series(
            [1, 2, 3, 4], index=Index([1, 2, 3, 4], name="bar"), name="foo_series"
        )
        df = DataFrame(
            {"col": np.arange(6)},
            index=pd.MultiIndex.from_product([foo_index, bar_index]),
        )

        expected_r = Series([1, 2] * 3, index=df.index, name="foo_series")
        result_l, result_r = df.align(series, axis=0)

        tm.assert_frame_equal(result_l, df)
        tm.assert_series_equal(result_r, expected_r)

    def test_multiindex_align_to_series_with_common_index_level_missing_in_right(self):
        #  GH-46001
        foo_index = Index([1, 2, 3], name="foo")
        bar_index = Index([1, 2, 3, 4], name="bar")

        series = Series([1, 2], index=Index([1, 2], name="bar"), name="foo_series")
        df = DataFrame(
            {"col": np.arange(12)},
            index=pd.MultiIndex.from_product([foo_index, bar_index]),
        )

        expected_r = Series(
            [1, 2, np.nan, np.nan] * 3, index=df.index, name="foo_series"
        )
        result_l, result_r = df.align(series, axis=0)

        tm.assert_frame_equal(result_l, df)
        tm.assert_series_equal(result_r, expected_r)

    def test_multiindex_align_to_series_with_common_index_level_missing_in_both(self):
        #  GH-46001
        foo_index = Index([1, 2, 3], name="foo")
        bar_index = Index([1, 3, 4], name="bar")

        series = Series(
            [1, 2, 3], index=Index([1, 2, 4], name="bar"), name="foo_series"
        )
        df = DataFrame(
            {"col": np.arange(9)},
            index=pd.MultiIndex.from_product([foo_index, bar_index]),
        )

        expected_r = Series([1, np.nan, 3] * 3, index=df.index, name="foo_series")
        result_l, result_r = df.align(series, axis=0)

        tm.assert_frame_equal(result_l, df)
        tm.assert_series_equal(result_r, expected_r)

    def test_multiindex_align_to_series_with_common_index_level_non_unique_cols(self):
        #  GH-46001
        foo_index = Index([1, 2, 3], name="foo")
        bar_index = Index([1, 2], name="bar")

        series = Series([1, 2], index=bar_index, name="foo_series")
        df = DataFrame(
            np.arange(18).reshape(6, 3),
            index=pd.MultiIndex.from_product([foo_index, bar_index]),
        )
        df.columns = ["cfoo", "cbar", "cfoo"]

        expected = Series([1, 2] * 3, index=df.index, name="foo_series")
        result_left, result_right = df.align(series, axis=0)

        tm.assert_series_equal(result_right, expected)
        tm.assert_index_equal(result_left.columns, df.columns)

    def test_missing_axis_specification_exception(self):
        df = DataFrame(np.arange(50).reshape((10, 5)))
        series = Series(np.arange(5))

        with pytest.raises(ValueError, match=r"axis=0 or 1"):
            df.align(series)

    @pytest.mark.parametrize("method", ["pad", "bfill"])
    @pytest.mark.parametrize("axis", [0, 1, None])
    @pytest.mark.parametrize("fill_axis", [0, 1])
    @pytest.mark.parametrize("how", ["inner", "outer", "left", "right"])
    @pytest.mark.parametrize(
        "left_slice",
        [
            [slice(4), slice(10)],
            [slice(0), slice(0)],
        ],
    )
    @pytest.mark.parametrize(
        "right_slice",
        [
            [slice(2, None), slice(6, None)],
            [slice(0), slice(0)],
        ],
    )
    @pytest.mark.parametrize("limit", [1, None])
    def test_align_fill_method(
        self, how, method, axis, fill_axis, float_frame, left_slice, right_slice, limit
    ):
        frame = float_frame
        left = frame.iloc[left_slice[0], left_slice[1]]
        right = frame.iloc[right_slice[0], right_slice[1]]

        msg = (
            "The 'method', 'limit', and 'fill_axis' keywords in DataFrame.align "
            "are deprecated"
        )

        with tm.assert_produces_warning(FutureWarning, match=msg):
            aa, ab = left.align(
                right,
                axis=axis,
                join=how,
                method=method,
                limit=limit,
                fill_axis=fill_axis,
            )

        join_index, join_columns = None, None

        ea, eb = left, right
        if axis is None or axis == 0:
            join_index = left.index.join(right.index, how=how)
            ea = ea.reindex(index=join_index)
            eb = eb.reindex(index=join_index)

        if axis is None or axis == 1:
            join_columns = left.columns.join(right.columns, how=how)
            ea = ea.reindex(columns=join_columns)
            eb = eb.reindex(columns=join_columns)

        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            ea = ea.fillna(axis=fill_axis, method=method, limit=limit)
            eb = eb.fillna(axis=fill_axis, method=method, limit=limit)

        tm.assert_frame_equal(aa, ea)
        tm.assert_frame_equal(ab, eb)

    def test_align_series_check_copy(self):
        # GH#
        df = DataFrame({0: [1, 2]})
        ser = Series([1], name=0)
        expected = ser.copy()
        result, other = df.align(ser, axis=1)
        ser.iloc[0] = 100
        tm.assert_series_equal(other, expected)

    def test_align_identical_different_object(self):
        # GH#51032
        df = DataFrame({"a": [1, 2]})
        ser = Series([3, 4])
        result, result2 = df.align(ser, axis=0)
        tm.assert_frame_equal(result, df)
        tm.assert_series_equal(result2, ser)
        assert df is not result
        assert ser is not result2

    def test_align_identical_different_object_columns(self):
        # GH#51032
        df = DataFrame({"a": [1, 2]})
        ser = Series([1], index=["a"])
        result, result2 = df.align(ser, axis=1)
        tm.assert_frame_equal(result, df)
        tm.assert_series_equal(result2, ser)
        assert df is not result
        assert ser is not result2
