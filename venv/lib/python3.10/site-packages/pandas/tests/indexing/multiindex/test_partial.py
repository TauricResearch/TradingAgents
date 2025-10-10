import numpy as np
import pytest

import pandas.util._test_decorators as td

from pandas import (
    DataFrame,
    DatetimeIndex,
    MultiIndex,
    date_range,
)
import pandas._testing as tm


class TestMultiIndexPartial:
    def test_getitem_partial_int(self):
        # GH 12416
        # with single item
        l1 = [10, 20]
        l2 = ["a", "b"]
        df = DataFrame(index=range(2), columns=MultiIndex.from_product([l1, l2]))
        expected = DataFrame(index=range(2), columns=l2)
        result = df[20]
        tm.assert_frame_equal(result, expected)

        # with list
        expected = DataFrame(
            index=range(2), columns=MultiIndex.from_product([l1[1:], l2])
        )
        result = df[[20]]
        tm.assert_frame_equal(result, expected)

        # missing item:
        with pytest.raises(KeyError, match="1"):
            df[1]
        with pytest.raises(KeyError, match=r"'\[1\] not in index'"):
            df[[1]]

    def test_series_slice_partial(self):
        pass

    def test_xs_partial(
        self,
        multiindex_dataframe_random_data,
        multiindex_year_month_day_dataframe_random_data,
    ):
        frame = multiindex_dataframe_random_data
        ymd = multiindex_year_month_day_dataframe_random_data
        result = frame.xs("foo")
        result2 = frame.loc["foo"]
        expected = frame.T["foo"].T
        tm.assert_frame_equal(result, expected)
        tm.assert_frame_equal(result, result2)

        result = ymd.xs((2000, 4))
        expected = ymd.loc[2000, 4]
        tm.assert_frame_equal(result, expected)

        # ex from #1796
        index = MultiIndex(
            levels=[["foo", "bar"], ["one", "two"], [-1, 1]],
            codes=[
                [0, 0, 0, 0, 1, 1, 1, 1],
                [0, 0, 1, 1, 0, 0, 1, 1],
                [0, 1, 0, 1, 0, 1, 0, 1],
            ],
        )
        df = DataFrame(
            np.random.default_rng(2).standard_normal((8, 4)),
            index=index,
            columns=list("abcd"),
        )

        result = df.xs(("foo", "one"))
        expected = df.loc["foo", "one"]
        tm.assert_frame_equal(result, expected)

    def test_getitem_partial(self, multiindex_year_month_day_dataframe_random_data):
        ymd = multiindex_year_month_day_dataframe_random_data
        ymd = ymd.T
        result = ymd[2000, 2]

        expected = ymd.reindex(columns=ymd.columns[ymd.columns.codes[1] == 1])
        expected.columns = expected.columns.droplevel(0).droplevel(0)
        tm.assert_frame_equal(result, expected)

    def test_fancy_slice_partial(
        self,
        multiindex_dataframe_random_data,
        multiindex_year_month_day_dataframe_random_data,
    ):
        frame = multiindex_dataframe_random_data
        result = frame.loc["bar":"baz"]
        expected = frame[3:7]
        tm.assert_frame_equal(result, expected)

        ymd = multiindex_year_month_day_dataframe_random_data
        result = ymd.loc[(2000, 2):(2000, 4)]
        lev = ymd.index.codes[1]
        expected = ymd[(lev >= 1) & (lev <= 3)]
        tm.assert_frame_equal(result, expected)

    def test_getitem_partial_column_select(self):
        idx = MultiIndex(
            codes=[[0, 0, 0], [0, 1, 1], [1, 0, 1]],
            levels=[["a", "b"], ["x", "y"], ["p", "q"]],
        )
        df = DataFrame(np.random.default_rng(2).random((3, 2)), index=idx)

        result = df.loc[("a", "y"), :]
        expected = df.loc[("a", "y")]
        tm.assert_frame_equal(result, expected)

        result = df.loc[("a", "y"), [1, 0]]
        expected = df.loc[("a", "y")][[1, 0]]
        tm.assert_frame_equal(result, expected)

        with pytest.raises(KeyError, match=r"\('a', 'foo'\)"):
            df.loc[("a", "foo"), :]

    # TODO(ArrayManager) rewrite test to not use .values
    # exp.loc[2000, 4].values[:] select multiple columns -> .values is not a view
    @td.skip_array_manager_invalid_test
    def test_partial_set(
        self,
        multiindex_year_month_day_dataframe_random_data,
        using_copy_on_write,
        warn_copy_on_write,
    ):
        # GH #397
        ymd = multiindex_year_month_day_dataframe_random_data
        df = ymd.copy()
        exp = ymd.copy()
        df.loc[2000, 4] = 0
        exp.iloc[65:85] = 0
        tm.assert_frame_equal(df, exp)

        if using_copy_on_write:
            with tm.raises_chained_assignment_error():
                df["A"].loc[2000, 4] = 1
            df.loc[(2000, 4), "A"] = 1
        else:
            with tm.raises_chained_assignment_error():
                df["A"].loc[2000, 4] = 1
        exp.iloc[65:85, 0] = 1
        tm.assert_frame_equal(df, exp)

        df.loc[2000] = 5
        exp.iloc[:100] = 5
        tm.assert_frame_equal(df, exp)

        # this works...for now
        with tm.raises_chained_assignment_error():
            df["A"].iloc[14] = 5
        if using_copy_on_write:
            assert df["A"].iloc[14] == exp["A"].iloc[14]
        else:
            assert df["A"].iloc[14] == 5

    @pytest.mark.parametrize("dtype", [int, float])
    def test_getitem_intkey_leading_level(
        self, multiindex_year_month_day_dataframe_random_data, dtype
    ):
        # GH#33355 dont fall-back to positional when leading level is int
        ymd = multiindex_year_month_day_dataframe_random_data
        levels = ymd.index.levels
        ymd.index = ymd.index.set_levels([levels[0].astype(dtype)] + levels[1:])
        ser = ymd["A"]
        mi = ser.index
        assert isinstance(mi, MultiIndex)
        if dtype is int:
            assert mi.levels[0].dtype == np.dtype(int)
        else:
            assert mi.levels[0].dtype == np.float64

        assert 14 not in mi.levels[0]
        assert not mi.levels[0]._should_fallback_to_positional
        assert not mi._should_fallback_to_positional

        with pytest.raises(KeyError, match="14"):
            ser[14]

    # ---------------------------------------------------------------------

    def test_setitem_multiple_partial(self, multiindex_dataframe_random_data):
        frame = multiindex_dataframe_random_data
        expected = frame.copy()
        result = frame.copy()
        result.loc[["foo", "bar"]] = 0
        expected.loc["foo"] = 0
        expected.loc["bar"] = 0
        tm.assert_frame_equal(result, expected)

        expected = frame.copy()
        result = frame.copy()
        result.loc["foo":"bar"] = 0
        expected.loc["foo"] = 0
        expected.loc["bar"] = 0
        tm.assert_frame_equal(result, expected)

        expected = frame["A"].copy()
        result = frame["A"].copy()
        result.loc[["foo", "bar"]] = 0
        expected.loc["foo"] = 0
        expected.loc["bar"] = 0
        tm.assert_series_equal(result, expected)

        expected = frame["A"].copy()
        result = frame["A"].copy()
        result.loc["foo":"bar"] = 0
        expected.loc["foo"] = 0
        expected.loc["bar"] = 0
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "indexer, exp_idx, exp_values",
        [
            (
                slice("2019-2", None),
                DatetimeIndex(["2019-02-01"], dtype="M8[ns]"),
                [2, 3],
            ),
            (
                slice(None, "2019-2"),
                date_range("2019", periods=2, freq="MS"),
                [0, 1, 2, 3],
            ),
        ],
    )
    def test_partial_getitem_loc_datetime(self, indexer, exp_idx, exp_values):
        # GH: 25165
        date_idx = date_range("2019", periods=2, freq="MS")
        df = DataFrame(
            list(range(4)),
            index=MultiIndex.from_product([date_idx, [0, 1]], names=["x", "y"]),
        )
        expected = DataFrame(
            exp_values,
            index=MultiIndex.from_product([exp_idx, [0, 1]], names=["x", "y"]),
        )
        result = df[indexer]
        tm.assert_frame_equal(result, expected)
        result = df.loc[indexer]
        tm.assert_frame_equal(result, expected)

        result = df.loc(axis=0)[indexer]
        tm.assert_frame_equal(result, expected)

        result = df.loc[indexer, :]
        tm.assert_frame_equal(result, expected)

        df2 = df.swaplevel(0, 1).sort_index()
        expected = expected.swaplevel(0, 1).sort_index()

        result = df2.loc[:, indexer, :]
        tm.assert_frame_equal(result, expected)


def test_loc_getitem_partial_both_axis():
    # gh-12660
    iterables = [["a", "b"], [2, 1]]
    columns = MultiIndex.from_product(iterables, names=["col1", "col2"])
    rows = MultiIndex.from_product(iterables, names=["row1", "row2"])
    df = DataFrame(
        np.random.default_rng(2).standard_normal((4, 4)), index=rows, columns=columns
    )
    expected = df.iloc[:2, 2:].droplevel("row1").droplevel("col1", axis=1)
    result = df.loc["a", "b"]
    tm.assert_frame_equal(result, expected)
