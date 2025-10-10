from datetime import datetime
import itertools
import re

import numpy as np
import pytest

from pandas._libs import lib
from pandas.errors import PerformanceWarning

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Period,
    Series,
    Timedelta,
    date_range,
)
import pandas._testing as tm
from pandas.core.reshape import reshape as reshape_lib


@pytest.fixture(params=[True, False])
def future_stack(request):
    return request.param


class TestDataFrameReshape:
    def test_stack_unstack(self, float_frame, future_stack):
        df = float_frame.copy()
        df[:] = np.arange(np.prod(df.shape)).reshape(df.shape)

        stacked = df.stack(future_stack=future_stack)
        stacked_df = DataFrame({"foo": stacked, "bar": stacked})

        unstacked = stacked.unstack()
        unstacked_df = stacked_df.unstack()

        tm.assert_frame_equal(unstacked, df)
        tm.assert_frame_equal(unstacked_df["bar"], df)

        unstacked_cols = stacked.unstack(0)
        unstacked_cols_df = stacked_df.unstack(0)
        tm.assert_frame_equal(unstacked_cols.T, df)
        tm.assert_frame_equal(unstacked_cols_df["bar"].T, df)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_mixed_level(self, future_stack):
        # GH 18310
        levels = [range(3), [3, "a", "b"], [1, 2]]

        # flat columns:
        df = DataFrame(1, index=levels[0], columns=levels[1])
        result = df.stack(future_stack=future_stack)
        expected = Series(1, index=MultiIndex.from_product(levels[:2]))
        tm.assert_series_equal(result, expected)

        # MultiIndex columns:
        df = DataFrame(1, index=levels[0], columns=MultiIndex.from_product(levels[1:]))
        result = df.stack(1, future_stack=future_stack)
        expected = DataFrame(
            1, index=MultiIndex.from_product([levels[0], levels[2]]), columns=levels[1]
        )
        tm.assert_frame_equal(result, expected)

        # as above, but used labels in level are actually of homogeneous type
        result = df[["a", "b"]].stack(1, future_stack=future_stack)
        expected = expected[["a", "b"]]
        tm.assert_frame_equal(result, expected)

    def test_unstack_not_consolidated(self, using_array_manager):
        # Gh#34708
        df = DataFrame({"x": [1, 2, np.nan], "y": [3.0, 4, np.nan]})
        df2 = df[["x"]]
        df2["y"] = df["y"]
        if not using_array_manager:
            assert len(df2._mgr.blocks) == 2

        res = df2.unstack()
        expected = df.unstack()
        tm.assert_series_equal(res, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_unstack_fill(self, future_stack):
        # GH #9746: fill_value keyword argument for Series
        # and DataFrame unstack

        # From a series
        data = Series([1, 2, 4, 5], dtype=np.int16)
        data.index = MultiIndex.from_tuples(
            [("x", "a"), ("x", "b"), ("y", "b"), ("z", "a")]
        )

        result = data.unstack(fill_value=-1)
        expected = DataFrame(
            {"a": [1, -1, 5], "b": [2, 4, -1]}, index=["x", "y", "z"], dtype=np.int16
        )
        tm.assert_frame_equal(result, expected)

        # From a series with incorrect data type for fill_value
        result = data.unstack(fill_value=0.5)
        expected = DataFrame(
            {"a": [1, 0.5, 5], "b": [2, 4, 0.5]}, index=["x", "y", "z"], dtype=float
        )
        tm.assert_frame_equal(result, expected)

        # GH #13971: fill_value when unstacking multiple levels:
        df = DataFrame(
            {"x": ["a", "a", "b"], "y": ["j", "k", "j"], "z": [0, 1, 2], "w": [0, 1, 2]}
        ).set_index(["x", "y", "z"])
        unstacked = df.unstack(["x", "y"], fill_value=0)
        key = ("w", "b", "j")
        expected = unstacked[key]
        result = Series([0, 0, 2], index=unstacked.index, name=key)
        tm.assert_series_equal(result, expected)

        stacked = unstacked.stack(["x", "y"], future_stack=future_stack)
        stacked.index = stacked.index.reorder_levels(df.index.names)
        # Workaround for GH #17886 (unnecessarily casts to float):
        stacked = stacked.astype(np.int64)
        result = stacked.loc[df.index]
        tm.assert_frame_equal(result, df)

        # From a series
        s = df["w"]
        result = s.unstack(["x", "y"], fill_value=0)
        expected = unstacked["w"]
        tm.assert_frame_equal(result, expected)

    def test_unstack_fill_frame(self):
        # From a dataframe
        rows = [[1, 2], [3, 4], [5, 6], [7, 8]]
        df = DataFrame(rows, columns=list("AB"), dtype=np.int32)
        df.index = MultiIndex.from_tuples(
            [("x", "a"), ("x", "b"), ("y", "b"), ("z", "a")]
        )

        result = df.unstack(fill_value=-1)

        rows = [[1, 3, 2, 4], [-1, 5, -1, 6], [7, -1, 8, -1]]
        expected = DataFrame(rows, index=list("xyz"), dtype=np.int32)
        expected.columns = MultiIndex.from_tuples(
            [("A", "a"), ("A", "b"), ("B", "a"), ("B", "b")]
        )
        tm.assert_frame_equal(result, expected)

        # From a mixed type dataframe
        df["A"] = df["A"].astype(np.int16)
        df["B"] = df["B"].astype(np.float64)

        result = df.unstack(fill_value=-1)
        expected["A"] = expected["A"].astype(np.int16)
        expected["B"] = expected["B"].astype(np.float64)
        tm.assert_frame_equal(result, expected)

        # From a dataframe with incorrect data type for fill_value
        result = df.unstack(fill_value=0.5)

        rows = [[1, 3, 2, 4], [0.5, 5, 0.5, 6], [7, 0.5, 8, 0.5]]
        expected = DataFrame(rows, index=list("xyz"), dtype=float)
        expected.columns = MultiIndex.from_tuples(
            [("A", "a"), ("A", "b"), ("B", "a"), ("B", "b")]
        )
        tm.assert_frame_equal(result, expected)

    def test_unstack_fill_frame_datetime(self):
        # Test unstacking with date times
        dv = date_range("2012-01-01", periods=4).values
        data = Series(dv)
        data.index = MultiIndex.from_tuples(
            [("x", "a"), ("x", "b"), ("y", "b"), ("z", "a")]
        )

        result = data.unstack()
        expected = DataFrame(
            {"a": [dv[0], pd.NaT, dv[3]], "b": [dv[1], dv[2], pd.NaT]},
            index=["x", "y", "z"],
        )
        tm.assert_frame_equal(result, expected)

        result = data.unstack(fill_value=dv[0])
        expected = DataFrame(
            {"a": [dv[0], dv[0], dv[3]], "b": [dv[1], dv[2], dv[0]]},
            index=["x", "y", "z"],
        )
        tm.assert_frame_equal(result, expected)

    def test_unstack_fill_frame_timedelta(self):
        # Test unstacking with time deltas
        td = [Timedelta(days=i) for i in range(4)]
        data = Series(td)
        data.index = MultiIndex.from_tuples(
            [("x", "a"), ("x", "b"), ("y", "b"), ("z", "a")]
        )

        result = data.unstack()
        expected = DataFrame(
            {"a": [td[0], pd.NaT, td[3]], "b": [td[1], td[2], pd.NaT]},
            index=["x", "y", "z"],
        )
        tm.assert_frame_equal(result, expected)

        result = data.unstack(fill_value=td[1])
        expected = DataFrame(
            {"a": [td[0], td[1], td[3]], "b": [td[1], td[2], td[1]]},
            index=["x", "y", "z"],
        )
        tm.assert_frame_equal(result, expected)

    def test_unstack_fill_frame_period(self):
        # Test unstacking with period
        periods = [
            Period("2012-01"),
            Period("2012-02"),
            Period("2012-03"),
            Period("2012-04"),
        ]
        data = Series(periods)
        data.index = MultiIndex.from_tuples(
            [("x", "a"), ("x", "b"), ("y", "b"), ("z", "a")]
        )

        result = data.unstack()
        expected = DataFrame(
            {"a": [periods[0], None, periods[3]], "b": [periods[1], periods[2], None]},
            index=["x", "y", "z"],
        )
        tm.assert_frame_equal(result, expected)

        result = data.unstack(fill_value=periods[1])
        expected = DataFrame(
            {
                "a": [periods[0], periods[1], periods[3]],
                "b": [periods[1], periods[2], periods[1]],
            },
            index=["x", "y", "z"],
        )
        tm.assert_frame_equal(result, expected)

    def test_unstack_fill_frame_categorical(self):
        # Test unstacking with categorical
        data = Series(["a", "b", "c", "a"], dtype="category")
        data.index = MultiIndex.from_tuples(
            [("x", "a"), ("x", "b"), ("y", "b"), ("z", "a")]
        )

        # By default missing values will be NaN
        result = data.unstack()
        expected = DataFrame(
            {
                "a": pd.Categorical(list("axa"), categories=list("abc")),
                "b": pd.Categorical(list("bcx"), categories=list("abc")),
            },
            index=list("xyz"),
        )
        tm.assert_frame_equal(result, expected)

        # Fill with non-category results in a ValueError
        msg = r"Cannot setitem on a Categorical with a new category \(d\)"
        with pytest.raises(TypeError, match=msg):
            data.unstack(fill_value="d")

        # Fill with category value replaces missing values as expected
        result = data.unstack(fill_value="c")
        expected = DataFrame(
            {
                "a": pd.Categorical(list("aca"), categories=list("abc")),
                "b": pd.Categorical(list("bcc"), categories=list("abc")),
            },
            index=list("xyz"),
        )
        tm.assert_frame_equal(result, expected)

    def test_unstack_tuplename_in_multiindex(self):
        # GH 19966
        idx = MultiIndex.from_product(
            [["a", "b", "c"], [1, 2, 3]], names=[("A", "a"), ("B", "b")]
        )
        df = DataFrame({"d": [1] * 9, "e": [2] * 9}, index=idx)
        result = df.unstack(("A", "a"))

        expected = DataFrame(
            [[1, 1, 1, 2, 2, 2], [1, 1, 1, 2, 2, 2], [1, 1, 1, 2, 2, 2]],
            columns=MultiIndex.from_tuples(
                [
                    ("d", "a"),
                    ("d", "b"),
                    ("d", "c"),
                    ("e", "a"),
                    ("e", "b"),
                    ("e", "c"),
                ],
                names=[None, ("A", "a")],
            ),
            index=Index([1, 2, 3], name=("B", "b")),
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "unstack_idx, expected_values, expected_index, expected_columns",
        [
            (
                ("A", "a"),
                [[1, 1, 2, 2], [1, 1, 2, 2], [1, 1, 2, 2], [1, 1, 2, 2]],
                MultiIndex.from_tuples(
                    [(1, 3), (1, 4), (2, 3), (2, 4)], names=["B", "C"]
                ),
                MultiIndex.from_tuples(
                    [("d", "a"), ("d", "b"), ("e", "a"), ("e", "b")],
                    names=[None, ("A", "a")],
                ),
            ),
            (
                (("A", "a"), "B"),
                [[1, 1, 1, 1, 2, 2, 2, 2], [1, 1, 1, 1, 2, 2, 2, 2]],
                Index([3, 4], name="C"),
                MultiIndex.from_tuples(
                    [
                        ("d", "a", 1),
                        ("d", "a", 2),
                        ("d", "b", 1),
                        ("d", "b", 2),
                        ("e", "a", 1),
                        ("e", "a", 2),
                        ("e", "b", 1),
                        ("e", "b", 2),
                    ],
                    names=[None, ("A", "a"), "B"],
                ),
            ),
        ],
    )
    def test_unstack_mixed_type_name_in_multiindex(
        self, unstack_idx, expected_values, expected_index, expected_columns
    ):
        # GH 19966
        idx = MultiIndex.from_product(
            [["a", "b"], [1, 2], [3, 4]], names=[("A", "a"), "B", "C"]
        )
        df = DataFrame({"d": [1] * 8, "e": [2] * 8}, index=idx)
        result = df.unstack(unstack_idx)

        expected = DataFrame(
            expected_values, columns=expected_columns, index=expected_index
        )
        tm.assert_frame_equal(result, expected)

    def test_unstack_preserve_dtypes(self):
        # Checks fix for #11847
        df = DataFrame(
            {
                "state": ["IL", "MI", "NC"],
                "index": ["a", "b", "c"],
                "some_categories": Series(["a", "b", "c"]).astype("category"),
                "A": np.random.default_rng(2).random(3),
                "B": 1,
                "C": "foo",
                "D": pd.Timestamp("20010102"),
                "E": Series([1.0, 50.0, 100.0]).astype("float32"),
                "F": Series([3.0, 4.0, 5.0]).astype("float64"),
                "G": False,
                "H": Series([1, 200, 923442]).astype("int8"),
            }
        )

        def unstack_and_compare(df, column_name):
            unstacked1 = df.unstack([column_name])
            unstacked2 = df.unstack(column_name)
            tm.assert_frame_equal(unstacked1, unstacked2)

        df1 = df.set_index(["state", "index"])
        unstack_and_compare(df1, "index")

        df1 = df.set_index(["state", "some_categories"])
        unstack_and_compare(df1, "some_categories")

        df1 = df.set_index(["F", "C"])
        unstack_and_compare(df1, "F")

        df1 = df.set_index(["G", "B", "state"])
        unstack_and_compare(df1, "B")

        df1 = df.set_index(["E", "A"])
        unstack_and_compare(df1, "E")

        df1 = df.set_index(["state", "index"])
        s = df1["A"]
        unstack_and_compare(s, "index")

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_ints(self, future_stack):
        columns = MultiIndex.from_tuples(list(itertools.product(range(3), repeat=3)))
        df = DataFrame(
            np.random.default_rng(2).standard_normal((30, 27)), columns=columns
        )

        tm.assert_frame_equal(
            df.stack(level=[1, 2], future_stack=future_stack),
            df.stack(level=1, future_stack=future_stack).stack(
                level=1, future_stack=future_stack
            ),
        )
        tm.assert_frame_equal(
            df.stack(level=[-2, -1], future_stack=future_stack),
            df.stack(level=1, future_stack=future_stack).stack(
                level=1, future_stack=future_stack
            ),
        )

        df_named = df.copy()
        return_value = df_named.columns.set_names(range(3), inplace=True)
        assert return_value is None

        tm.assert_frame_equal(
            df_named.stack(level=[1, 2], future_stack=future_stack),
            df_named.stack(level=1, future_stack=future_stack).stack(
                level=1, future_stack=future_stack
            ),
        )

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_mixed_levels(self, future_stack):
        columns = MultiIndex.from_tuples(
            [
                ("A", "cat", "long"),
                ("B", "cat", "long"),
                ("A", "dog", "short"),
                ("B", "dog", "short"),
            ],
            names=["exp", "animal", "hair_length"],
        )
        df = DataFrame(
            np.random.default_rng(2).standard_normal((4, 4)), columns=columns
        )

        animal_hair_stacked = df.stack(
            level=["animal", "hair_length"], future_stack=future_stack
        )
        exp_hair_stacked = df.stack(
            level=["exp", "hair_length"], future_stack=future_stack
        )

        # GH #8584: Need to check that stacking works when a number
        # is passed that is both a level name and in the range of
        # the level numbers
        df2 = df.copy()
        df2.columns.names = ["exp", "animal", 1]
        tm.assert_frame_equal(
            df2.stack(level=["animal", 1], future_stack=future_stack),
            animal_hair_stacked,
            check_names=False,
        )
        tm.assert_frame_equal(
            df2.stack(level=["exp", 1], future_stack=future_stack),
            exp_hair_stacked,
            check_names=False,
        )

        # When mixed types are passed and the ints are not level
        # names, raise
        msg = (
            "level should contain all level names or all level numbers, not "
            "a mixture of the two"
        )
        with pytest.raises(ValueError, match=msg):
            df2.stack(level=["animal", 0], future_stack=future_stack)

        # GH #8584: Having 0 in the level names could raise a
        # strange error about lexsort depth
        df3 = df.copy()
        df3.columns.names = ["exp", "animal", 0]
        tm.assert_frame_equal(
            df3.stack(level=["animal", 0], future_stack=future_stack),
            animal_hair_stacked,
            check_names=False,
        )

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_int_level_names(self, future_stack):
        columns = MultiIndex.from_tuples(
            [
                ("A", "cat", "long"),
                ("B", "cat", "long"),
                ("A", "dog", "short"),
                ("B", "dog", "short"),
            ],
            names=["exp", "animal", "hair_length"],
        )
        df = DataFrame(
            np.random.default_rng(2).standard_normal((4, 4)), columns=columns
        )

        exp_animal_stacked = df.stack(
            level=["exp", "animal"], future_stack=future_stack
        )
        animal_hair_stacked = df.stack(
            level=["animal", "hair_length"], future_stack=future_stack
        )
        exp_hair_stacked = df.stack(
            level=["exp", "hair_length"], future_stack=future_stack
        )

        df2 = df.copy()
        df2.columns.names = [0, 1, 2]
        tm.assert_frame_equal(
            df2.stack(level=[1, 2], future_stack=future_stack),
            animal_hair_stacked,
            check_names=False,
        )
        tm.assert_frame_equal(
            df2.stack(level=[0, 1], future_stack=future_stack),
            exp_animal_stacked,
            check_names=False,
        )
        tm.assert_frame_equal(
            df2.stack(level=[0, 2], future_stack=future_stack),
            exp_hair_stacked,
            check_names=False,
        )

        # Out-of-order int column names
        df3 = df.copy()
        df3.columns.names = [2, 0, 1]
        tm.assert_frame_equal(
            df3.stack(level=[0, 1], future_stack=future_stack),
            animal_hair_stacked,
            check_names=False,
        )
        tm.assert_frame_equal(
            df3.stack(level=[2, 0], future_stack=future_stack),
            exp_animal_stacked,
            check_names=False,
        )
        tm.assert_frame_equal(
            df3.stack(level=[2, 1], future_stack=future_stack),
            exp_hair_stacked,
            check_names=False,
        )

    def test_unstack_bool(self):
        df = DataFrame(
            [False, False],
            index=MultiIndex.from_arrays([["a", "b"], ["c", "l"]]),
            columns=["col"],
        )
        rs = df.unstack()
        xp = DataFrame(
            np.array([[False, np.nan], [np.nan, False]], dtype=object),
            index=["a", "b"],
            columns=MultiIndex.from_arrays([["col", "col"], ["c", "l"]]),
        )
        tm.assert_frame_equal(rs, xp)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_unstack_level_binding(self, future_stack):
        # GH9856
        mi = MultiIndex(
            levels=[["foo", "bar"], ["one", "two"], ["a", "b"]],
            codes=[[0, 0, 1, 1], [0, 1, 0, 1], [1, 0, 1, 0]],
            names=["first", "second", "third"],
        )
        s = Series(0, index=mi)
        result = s.unstack([1, 2]).stack(0, future_stack=future_stack)

        expected_mi = MultiIndex(
            levels=[["foo", "bar"], ["one", "two"]],
            codes=[[0, 0, 1, 1], [0, 1, 0, 1]],
            names=["first", "second"],
        )

        expected = DataFrame(
            np.array(
                [[0, np.nan], [np.nan, 0], [0, np.nan], [np.nan, 0]], dtype=np.float64
            ),
            index=expected_mi,
            columns=Index(["b", "a"], name="third"),
        )

        tm.assert_frame_equal(result, expected)

    def test_unstack_to_series(self, float_frame):
        # check reversibility
        data = float_frame.unstack()

        assert isinstance(data, Series)
        undo = data.unstack().T
        tm.assert_frame_equal(undo, float_frame)

        # check NA handling
        data = DataFrame({"x": [1, 2, np.nan], "y": [3.0, 4, np.nan]})
        data.index = Index(["a", "b", "c"])
        result = data.unstack()

        midx = MultiIndex(
            levels=[["x", "y"], ["a", "b", "c"]],
            codes=[[0, 0, 0, 1, 1, 1], [0, 1, 2, 0, 1, 2]],
        )
        expected = Series([1, 2, np.nan, 3, 4, np.nan], index=midx)

        tm.assert_series_equal(result, expected)

        # check composability of unstack
        old_data = data.copy()
        for _ in range(4):
            data = data.unstack()
        tm.assert_frame_equal(old_data, data)

    def test_unstack_dtypes(self, using_infer_string):
        # GH 2929
        rows = [[1, 1, 3, 4], [1, 2, 3, 4], [2, 1, 3, 4], [2, 2, 3, 4]]

        df = DataFrame(rows, columns=list("ABCD"))
        result = df.dtypes
        expected = Series([np.dtype("int64")] * 4, index=list("ABCD"))
        tm.assert_series_equal(result, expected)

        # single dtype
        df2 = df.set_index(["A", "B"])
        df3 = df2.unstack("B")
        result = df3.dtypes
        expected = Series(
            [np.dtype("int64")] * 4,
            index=MultiIndex.from_arrays(
                [["C", "C", "D", "D"], [1, 2, 1, 2]], names=(None, "B")
            ),
        )
        tm.assert_series_equal(result, expected)

        # mixed
        df2 = df.set_index(["A", "B"])
        df2["C"] = 3.0
        df3 = df2.unstack("B")
        result = df3.dtypes
        expected = Series(
            [np.dtype("float64")] * 2 + [np.dtype("int64")] * 2,
            index=MultiIndex.from_arrays(
                [["C", "C", "D", "D"], [1, 2, 1, 2]], names=(None, "B")
            ),
        )
        tm.assert_series_equal(result, expected)
        df2["D"] = "foo"
        df3 = df2.unstack("B")
        result = df3.dtypes
        dtype = (
            pd.StringDtype(na_value=np.nan)
            if using_infer_string
            else np.dtype("object")
        )
        expected = Series(
            [np.dtype("float64")] * 2 + [dtype] * 2,
            index=MultiIndex.from_arrays(
                [["C", "C", "D", "D"], [1, 2, 1, 2]], names=(None, "B")
            ),
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "c, d",
        (
            (np.zeros(5), np.zeros(5)),
            (np.arange(5, dtype="f8"), np.arange(5, 10, dtype="f8")),
        ),
    )
    def test_unstack_dtypes_mixed_date(self, c, d):
        # GH7405
        df = DataFrame(
            {
                "A": ["a"] * 5,
                "C": c,
                "D": d,
                "B": date_range("2012-01-01", periods=5),
            }
        )

        right = df.iloc[:3].copy(deep=True)

        df = df.set_index(["A", "B"])
        df["D"] = df["D"].astype("int64")

        left = df.iloc[:3].unstack(0)
        right = right.set_index(["A", "B"]).unstack(0)
        right[("D", "a")] = right[("D", "a")].astype("int64")

        assert left.shape == (3, 2)
        tm.assert_frame_equal(left, right)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_unstack_non_unique_index_names(self, future_stack):
        idx = MultiIndex.from_tuples([("a", "b"), ("c", "d")], names=["c1", "c1"])
        df = DataFrame([1, 2], index=idx)
        msg = "The name c1 occurs multiple times, use a level number"
        with pytest.raises(ValueError, match=msg):
            df.unstack("c1")

        with pytest.raises(ValueError, match=msg):
            df.T.stack("c1", future_stack=future_stack)

    def test_unstack_unused_levels(self):
        # GH 17845: unused codes in index make unstack() cast int to float
        idx = MultiIndex.from_product([["a"], ["A", "B", "C", "D"]])[:-1]
        df = DataFrame([[1, 0]] * 3, index=idx)

        result = df.unstack()
        exp_col = MultiIndex.from_product([[0, 1], ["A", "B", "C"]])
        expected = DataFrame([[1, 1, 1, 0, 0, 0]], index=["a"], columns=exp_col)
        tm.assert_frame_equal(result, expected)
        assert (result.columns.levels[1] == idx.levels[1]).all()

        # Unused items on both levels
        levels = [[0, 1, 7], [0, 1, 2, 3]]
        codes = [[0, 0, 1, 1], [0, 2, 0, 2]]
        idx = MultiIndex(levels, codes)
        block = np.arange(4).reshape(2, 2)
        df = DataFrame(np.concatenate([block, block + 4]), index=idx)
        result = df.unstack()
        expected = DataFrame(
            np.concatenate([block * 2, block * 2 + 1], axis=1), columns=idx
        )
        tm.assert_frame_equal(result, expected)
        assert (result.columns.levels[1] == idx.levels[1]).all()

    @pytest.mark.parametrize(
        "level, idces, col_level, idx_level",
        (
            (0, [13, 16, 6, 9, 2, 5, 8, 11], [np.nan, "a", 2], [np.nan, 5, 1]),
            (1, [8, 11, 1, 4, 12, 15, 13, 16], [np.nan, 5, 1], [np.nan, "a", 2]),
        ),
    )
    def test_unstack_unused_levels_mixed_with_nan(
        self, level, idces, col_level, idx_level
    ):
        # With mixed dtype and NaN
        levels = [["a", 2, "c"], [1, 3, 5, 7]]
        codes = [[0, -1, 1, 1], [0, 2, -1, 2]]
        idx = MultiIndex(levels, codes)
        data = np.arange(8)
        df = DataFrame(data.reshape(4, 2), index=idx)

        result = df.unstack(level=level)
        exp_data = np.zeros(18) * np.nan
        exp_data[idces] = data
        cols = MultiIndex.from_product([[0, 1], col_level])
        expected = DataFrame(exp_data.reshape(3, 6), index=idx_level, columns=cols)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("cols", [["A", "C"], slice(None)])
    def test_unstack_unused_level(self, cols):
        # GH 18562 : unused codes on the unstacked level
        df = DataFrame([[2010, "a", "I"], [2011, "b", "II"]], columns=["A", "B", "C"])

        ind = df.set_index(["A", "B", "C"], drop=False)
        selection = ind.loc[(slice(None), slice(None), "I"), cols]
        result = selection.unstack()

        expected = ind.iloc[[0]][cols]
        expected.columns = MultiIndex.from_product(
            [expected.columns, ["I"]], names=[None, "C"]
        )
        expected.index = expected.index.droplevel("C")
        tm.assert_frame_equal(result, expected)

    def test_unstack_long_index(self):
        # PH 32624: Error when using a lot of indices to unstack.
        # The error occurred only, if a lot of indices are used.
        df = DataFrame(
            [[1]],
            columns=MultiIndex.from_tuples([[0]], names=["c1"]),
            index=MultiIndex.from_tuples(
                [[0, 0, 1, 0, 0, 0, 1]],
                names=["i1", "i2", "i3", "i4", "i5", "i6", "i7"],
            ),
        )
        result = df.unstack(["i2", "i3", "i4", "i5", "i6", "i7"])
        expected = DataFrame(
            [[1]],
            columns=MultiIndex.from_tuples(
                [[0, 0, 1, 0, 0, 0, 1]],
                names=["c1", "i2", "i3", "i4", "i5", "i6", "i7"],
            ),
            index=Index([0], name="i1"),
        )
        tm.assert_frame_equal(result, expected)

    def test_unstack_multi_level_cols(self):
        # PH 24729: Unstack a df with multi level columns
        df = DataFrame(
            [[0.0, 0.0], [0.0, 0.0]],
            columns=MultiIndex.from_tuples(
                [["B", "C"], ["B", "D"]], names=["c1", "c2"]
            ),
            index=MultiIndex.from_tuples(
                [[10, 20, 30], [10, 20, 40]], names=["i1", "i2", "i3"]
            ),
        )
        assert df.unstack(["i2", "i1"]).columns.names[-2:] == ["i2", "i1"]

    def test_unstack_multi_level_rows_and_cols(self):
        # PH 28306: Unstack df with multi level cols and rows
        df = DataFrame(
            [[1, 2], [3, 4], [-1, -2], [-3, -4]],
            columns=MultiIndex.from_tuples([["a", "b", "c"], ["d", "e", "f"]]),
            index=MultiIndex.from_tuples(
                [
                    ["m1", "P3", 222],
                    ["m1", "A5", 111],
                    ["m2", "P3", 222],
                    ["m2", "A5", 111],
                ],
                names=["i1", "i2", "i3"],
            ),
        )
        result = df.unstack(["i3", "i2"])
        expected = df.unstack(["i3"]).unstack(["i2"])
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("idx", [("jim", "joe"), ("joe", "jim")])
    @pytest.mark.parametrize("lev", list(range(2)))
    def test_unstack_nan_index1(self, idx, lev):
        # GH7466
        def cast(val):
            val_str = "" if val != val else val
            return f"{val_str:1}"

        df = DataFrame(
            {
                "jim": ["a", "b", np.nan, "d"],
                "joe": ["w", "x", "y", "z"],
                "jolie": ["a.w", "b.x", " .y", "d.z"],
            }
        )

        left = df.set_index(["jim", "joe"]).unstack()["jolie"]
        right = df.set_index(["joe", "jim"]).unstack()["jolie"].T
        tm.assert_frame_equal(left, right)

        mi = df.set_index(list(idx))
        udf = mi.unstack(level=lev)
        assert udf.notna().values.sum() == len(df)
        mk_list = lambda a: list(a) if isinstance(a, tuple) else [a]
        rows, cols = udf["jolie"].notna().values.nonzero()
        for i, j in zip(rows, cols):
            left = sorted(udf["jolie"].iloc[i, j].split("."))
            right = mk_list(udf["jolie"].index[i]) + mk_list(udf["jolie"].columns[j])
            right = sorted(map(cast, right))
            assert left == right

    @pytest.mark.parametrize("idx", itertools.permutations(["1st", "2nd", "3rd"]))
    @pytest.mark.parametrize("lev", list(range(3)))
    @pytest.mark.parametrize("col", ["4th", "5th"])
    def test_unstack_nan_index_repeats(self, idx, lev, col):
        def cast(val):
            val_str = "" if val != val else val
            return f"{val_str:1}"

        df = DataFrame(
            {
                "1st": ["d"] * 3
                + [np.nan] * 5
                + ["a"] * 2
                + ["c"] * 3
                + ["e"] * 2
                + ["b"] * 5,
                "2nd": ["y"] * 2
                + ["w"] * 3
                + [np.nan] * 3
                + ["z"] * 4
                + [np.nan] * 3
                + ["x"] * 3
                + [np.nan] * 2,
                "3rd": [
                    67,
                    39,
                    53,
                    72,
                    57,
                    80,
                    31,
                    18,
                    11,
                    30,
                    59,
                    50,
                    62,
                    59,
                    76,
                    52,
                    14,
                    53,
                    60,
                    51,
                ],
            }
        )

        df["4th"], df["5th"] = (
            df.apply(lambda r: ".".join(map(cast, r)), axis=1),
            df.apply(lambda r: ".".join(map(cast, r.iloc[::-1])), axis=1),
        )

        mi = df.set_index(list(idx))
        udf = mi.unstack(level=lev)
        assert udf.notna().values.sum() == 2 * len(df)
        mk_list = lambda a: list(a) if isinstance(a, tuple) else [a]
        rows, cols = udf[col].notna().values.nonzero()
        for i, j in zip(rows, cols):
            left = sorted(udf[col].iloc[i, j].split("."))
            right = mk_list(udf[col].index[i]) + mk_list(udf[col].columns[j])
            right = sorted(map(cast, right))
            assert left == right

    def test_unstack_nan_index2(self):
        # GH7403
        df = DataFrame({"A": list("aaaabbbb"), "B": range(8), "C": range(8)})
        # Explicit cast to avoid implicit cast when setting to np.nan
        df = df.astype({"B": "float"})
        df.iloc[3, 1] = np.nan
        left = df.set_index(["A", "B"]).unstack(0)

        vals = [
            [3, 0, 1, 2, np.nan, np.nan, np.nan, np.nan],
            [np.nan, np.nan, np.nan, np.nan, 4, 5, 6, 7],
        ]
        vals = list(map(list, zip(*vals)))
        idx = Index([np.nan, 0, 1, 2, 4, 5, 6, 7], name="B")
        cols = MultiIndex(
            levels=[["C"], ["a", "b"]], codes=[[0, 0], [0, 1]], names=[None, "A"]
        )

        right = DataFrame(vals, columns=cols, index=idx)
        tm.assert_frame_equal(left, right)

        df = DataFrame({"A": list("aaaabbbb"), "B": list(range(4)) * 2, "C": range(8)})
        # Explicit cast to avoid implicit cast when setting to np.nan
        df = df.astype({"B": "float"})
        df.iloc[2, 1] = np.nan
        left = df.set_index(["A", "B"]).unstack(0)

        vals = [[2, np.nan], [0, 4], [1, 5], [np.nan, 6], [3, 7]]
        cols = MultiIndex(
            levels=[["C"], ["a", "b"]], codes=[[0, 0], [0, 1]], names=[None, "A"]
        )
        idx = Index([np.nan, 0, 1, 2, 3], name="B")
        right = DataFrame(vals, columns=cols, index=idx)
        tm.assert_frame_equal(left, right)

        df = DataFrame({"A": list("aaaabbbb"), "B": list(range(4)) * 2, "C": range(8)})
        # Explicit cast to avoid implicit cast when setting to np.nan
        df = df.astype({"B": "float"})
        df.iloc[3, 1] = np.nan
        left = df.set_index(["A", "B"]).unstack(0)

        vals = [[3, np.nan], [0, 4], [1, 5], [2, 6], [np.nan, 7]]
        cols = MultiIndex(
            levels=[["C"], ["a", "b"]], codes=[[0, 0], [0, 1]], names=[None, "A"]
        )
        idx = Index([np.nan, 0, 1, 2, 3], name="B")
        right = DataFrame(vals, columns=cols, index=idx)
        tm.assert_frame_equal(left, right)

    def test_unstack_nan_index3(self, using_array_manager):
        # GH7401
        df = DataFrame(
            {
                "A": list("aaaaabbbbb"),
                "B": (date_range("2012-01-01", periods=5).tolist() * 2),
                "C": np.arange(10),
            }
        )

        df.iloc[3, 1] = np.nan
        left = df.set_index(["A", "B"]).unstack()

        vals = np.array([[3, 0, 1, 2, np.nan, 4], [np.nan, 5, 6, 7, 8, 9]])
        idx = Index(["a", "b"], name="A")
        cols = MultiIndex(
            levels=[["C"], date_range("2012-01-01", periods=5)],
            codes=[[0, 0, 0, 0, 0, 0], [-1, 0, 1, 2, 3, 4]],
            names=[None, "B"],
        )

        right = DataFrame(vals, columns=cols, index=idx)
        if using_array_manager:
            # INFO(ArrayManager) with ArrayManager preserve dtype where possible
            cols = right.columns[[1, 2, 3, 5]]
            right[cols] = right[cols].astype(df["C"].dtype)
        tm.assert_frame_equal(left, right)

    def test_unstack_nan_index4(self):
        # GH4862
        vals = [
            ["Hg", np.nan, np.nan, 680585148],
            ["U", 0.0, np.nan, 680585148],
            ["Pb", 7.07e-06, np.nan, 680585148],
            ["Sn", 2.3614e-05, 0.0133, 680607017],
            ["Ag", 0.0, 0.0133, 680607017],
            ["Hg", -0.00015, 0.0133, 680607017],
        ]
        df = DataFrame(
            vals,
            columns=["agent", "change", "dosage", "s_id"],
            index=[17263, 17264, 17265, 17266, 17267, 17268],
        )

        left = df.copy().set_index(["s_id", "dosage", "agent"]).unstack()

        vals = [
            [np.nan, np.nan, 7.07e-06, np.nan, 0.0],
            [0.0, -0.00015, np.nan, 2.3614e-05, np.nan],
        ]

        idx = MultiIndex(
            levels=[[680585148, 680607017], [0.0133]],
            codes=[[0, 1], [-1, 0]],
            names=["s_id", "dosage"],
        )

        cols = MultiIndex(
            levels=[["change"], ["Ag", "Hg", "Pb", "Sn", "U"]],
            codes=[[0, 0, 0, 0, 0], [0, 1, 2, 3, 4]],
            names=[None, "agent"],
        )

        right = DataFrame(vals, columns=cols, index=idx)
        tm.assert_frame_equal(left, right)

        left = df.loc[17264:].copy().set_index(["s_id", "dosage", "agent"])
        tm.assert_frame_equal(left.unstack(), right)

    def test_unstack_nan_index5(self):
        # GH9497 - multiple unstack with nulls
        df = DataFrame(
            {
                "1st": [1, 2, 1, 2, 1, 2],
                "2nd": date_range("2014-02-01", periods=6, freq="D"),
                "jim": 100 + np.arange(6),
                "joe": (np.random.default_rng(2).standard_normal(6) * 10).round(2),
            }
        )

        df["3rd"] = df["2nd"] - pd.Timestamp("2014-02-02")
        df.loc[1, "2nd"] = df.loc[3, "2nd"] = np.nan
        df.loc[1, "3rd"] = df.loc[4, "3rd"] = np.nan

        left = df.set_index(["1st", "2nd", "3rd"]).unstack(["2nd", "3rd"])
        assert left.notna().values.sum() == 2 * len(df)

        for col in ["jim", "joe"]:
            for _, r in df.iterrows():
                key = r["1st"], (col, r["2nd"], r["3rd"])
                assert r[col] == left.loc[key]

    def test_stack_datetime_column_multiIndex(self, future_stack):
        # GH 8039
        t = datetime(2014, 1, 1)
        df = DataFrame([1, 2, 3, 4], columns=MultiIndex.from_tuples([(t, "A", "B")]))
        warn = None if future_stack else FutureWarning
        msg = "The previous implementation of stack is deprecated"
        with tm.assert_produces_warning(warn, match=msg):
            result = df.stack(future_stack=future_stack)

        eidx = MultiIndex.from_product([(0, 1, 2, 3), ("B",)])
        ecols = MultiIndex.from_tuples([(t, "A")])
        expected = DataFrame([1, 2, 3, 4], index=eidx, columns=ecols)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    @pytest.mark.parametrize(
        "multiindex_columns",
        [
            [0, 1, 2, 3, 4],
            [0, 1, 2, 3],
            [0, 1, 2, 4],
            [0, 1, 2],
            [1, 2, 3],
            [2, 3, 4],
            [0, 1],
            [0, 2],
            [0, 3],
            [0],
            [2],
            [4],
            [4, 3, 2, 1, 0],
            [3, 2, 1, 0],
            [4, 2, 1, 0],
            [2, 1, 0],
            [3, 2, 1],
            [4, 3, 2],
            [1, 0],
            [2, 0],
            [3, 0],
        ],
    )
    @pytest.mark.parametrize("level", (-1, 0, 1, [0, 1], [1, 0]))
    def test_stack_partial_multiIndex(self, multiindex_columns, level, future_stack):
        # GH 8844
        dropna = False if not future_stack else lib.no_default
        full_multiindex = MultiIndex.from_tuples(
            [("B", "x"), ("B", "z"), ("A", "y"), ("C", "x"), ("C", "u")],
            names=["Upper", "Lower"],
        )
        multiindex = full_multiindex[multiindex_columns]
        df = DataFrame(
            np.arange(3 * len(multiindex)).reshape(3, len(multiindex)),
            columns=multiindex,
        )
        result = df.stack(level=level, dropna=dropna, future_stack=future_stack)

        if isinstance(level, int) and not future_stack:
            # Stacking a single level should not make any all-NaN rows,
            # so df.stack(level=level, dropna=False) should be the same
            # as df.stack(level=level, dropna=True).
            expected = df.stack(level=level, dropna=True, future_stack=future_stack)
            if isinstance(expected, Series):
                tm.assert_series_equal(result, expected)
            else:
                tm.assert_frame_equal(result, expected)

        df.columns = MultiIndex.from_tuples(
            df.columns.to_numpy(), names=df.columns.names
        )
        expected = df.stack(level=level, dropna=dropna, future_stack=future_stack)
        if isinstance(expected, Series):
            tm.assert_series_equal(result, expected)
        else:
            tm.assert_frame_equal(result, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_full_multiIndex(self, future_stack):
        # GH 8844
        full_multiindex = MultiIndex.from_tuples(
            [("B", "x"), ("B", "z"), ("A", "y"), ("C", "x"), ("C", "u")],
            names=["Upper", "Lower"],
        )
        df = DataFrame(np.arange(6).reshape(2, 3), columns=full_multiindex[[0, 1, 3]])
        dropna = False if not future_stack else lib.no_default
        result = df.stack(dropna=dropna, future_stack=future_stack)
        expected = DataFrame(
            [[0, 2], [1, np.nan], [3, 5], [4, np.nan]],
            index=MultiIndex(
                levels=[[0, 1], ["u", "x", "y", "z"]],
                codes=[[0, 0, 1, 1], [1, 3, 1, 3]],
                names=[None, "Lower"],
            ),
            columns=Index(["B", "C"], name="Upper"),
        )
        expected["B"] = expected["B"].astype(df.dtypes.iloc[0])
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("ordered", [False, True])
    def test_stack_preserve_categorical_dtype(self, ordered, future_stack):
        # GH13854
        cidx = pd.CategoricalIndex(list("yxz"), categories=list("xyz"), ordered=ordered)
        df = DataFrame([[10, 11, 12]], columns=cidx)
        result = df.stack(future_stack=future_stack)

        # `MultiIndex.from_product` preserves categorical dtype -
        # it's tested elsewhere.
        midx = MultiIndex.from_product([df.index, cidx])
        expected = Series([10, 11, 12], index=midx)

        tm.assert_series_equal(result, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    @pytest.mark.parametrize("ordered", [False, True])
    @pytest.mark.parametrize(
        "labels,data",
        [
            (list("xyz"), [10, 11, 12, 13, 14, 15]),
            (list("zyx"), [14, 15, 12, 13, 10, 11]),
        ],
    )
    def test_stack_multi_preserve_categorical_dtype(
        self, ordered, labels, data, future_stack
    ):
        # GH-36991
        cidx = pd.CategoricalIndex(labels, categories=sorted(labels), ordered=ordered)
        cidx2 = pd.CategoricalIndex(["u", "v"], ordered=ordered)
        midx = MultiIndex.from_product([cidx, cidx2])
        df = DataFrame([sorted(data)], columns=midx)
        result = df.stack([0, 1], future_stack=future_stack)

        labels = labels if future_stack else sorted(labels)
        s_cidx = pd.CategoricalIndex(labels, ordered=ordered)
        expected_data = sorted(data) if future_stack else data
        expected = Series(
            expected_data, index=MultiIndex.from_product([[0], s_cidx, cidx2])
        )

        tm.assert_series_equal(result, expected)

    def test_stack_preserve_categorical_dtype_values(self, future_stack):
        # GH-23077
        cat = pd.Categorical(["a", "a", "b", "c"])
        df = DataFrame({"A": cat, "B": cat})
        result = df.stack(future_stack=future_stack)
        index = MultiIndex.from_product([[0, 1, 2, 3], ["A", "B"]])
        expected = Series(
            pd.Categorical(["a", "a", "a", "a", "b", "b", "c", "c"]), index=index
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    @pytest.mark.filterwarnings("ignore:Downcasting object dtype arrays:FutureWarning")
    @pytest.mark.parametrize(
        "index, columns",
        [
            ([0, 0, 1, 1], MultiIndex.from_product([[1, 2], ["a", "b"]])),
            ([0, 0, 2, 3], MultiIndex.from_product([[1, 2], ["a", "b"]])),
            ([0, 1, 2, 3], MultiIndex.from_product([[1, 2], ["a", "b"]])),
        ],
    )
    def test_stack_multi_columns_non_unique_index(self, index, columns, future_stack):
        # GH-28301

        df = DataFrame(index=index, columns=columns).fillna(1)
        stacked = df.stack(future_stack=future_stack)
        new_index = MultiIndex.from_tuples(stacked.index.to_numpy())
        expected = DataFrame(
            stacked.to_numpy(), index=new_index, columns=stacked.columns
        )
        tm.assert_frame_equal(stacked, expected)
        stacked_codes = np.asarray(stacked.index.codes)
        expected_codes = np.asarray(new_index.codes)
        tm.assert_numpy_array_equal(stacked_codes, expected_codes)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    @pytest.mark.parametrize(
        "vals1, vals2, dtype1, dtype2, expected_dtype",
        [
            ([1, 2], [3.0, 4.0], "Int64", "Float64", "Float64"),
            ([1, 2], ["foo", "bar"], "Int64", "string", "object"),
        ],
    )
    def test_stack_multi_columns_mixed_extension_types(
        self, vals1, vals2, dtype1, dtype2, expected_dtype, future_stack
    ):
        # GH45740
        df = DataFrame(
            {
                ("A", 1): Series(vals1, dtype=dtype1),
                ("A", 2): Series(vals2, dtype=dtype2),
            }
        )
        result = df.stack(future_stack=future_stack)
        expected = (
            df.astype(object).stack(future_stack=future_stack).astype(expected_dtype)
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("level", [0, 1])
    def test_unstack_mixed_extension_types(self, level):
        index = MultiIndex.from_tuples([("A", 0), ("A", 1), ("B", 1)], names=["a", "b"])
        df = DataFrame(
            {
                "A": pd.array([0, 1, None], dtype="Int64"),
                "B": pd.Categorical(["a", "a", "b"]),
            },
            index=index,
        )

        result = df.unstack(level=level)
        expected = df.astype(object).unstack(level=level)
        if level == 0:
            expected[("A", "B")] = expected[("A", "B")].fillna(pd.NA)
        else:
            expected[("A", 0)] = expected[("A", 0)].fillna(pd.NA)

        expected_dtypes = Series(
            [df.A.dtype] * 2 + [df.B.dtype] * 2, index=result.columns
        )
        tm.assert_series_equal(result.dtypes, expected_dtypes)
        tm.assert_frame_equal(result.astype(object), expected)

    @pytest.mark.parametrize("level", [0, "baz"])
    def test_unstack_swaplevel_sortlevel(self, level):
        # GH 20994
        mi = MultiIndex.from_product([[0], ["d", "c"]], names=["bar", "baz"])
        df = DataFrame([[0, 2], [1, 3]], index=mi, columns=["B", "A"])
        df.columns.name = "foo"

        expected = DataFrame(
            [[3, 1, 2, 0]],
            columns=MultiIndex.from_tuples(
                [("c", "A"), ("c", "B"), ("d", "A"), ("d", "B")], names=["baz", "foo"]
            ),
        )
        expected.index.name = "bar"

        result = df.unstack().swaplevel(axis=1).sort_index(axis=1, level=level)
        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("dtype", ["float64", "Float64"])
def test_unstack_sort_false(frame_or_series, dtype):
    # GH 15105
    index = MultiIndex.from_tuples(
        [("two", "z", "b"), ("two", "y", "a"), ("one", "z", "b"), ("one", "y", "a")]
    )
    obj = frame_or_series(np.arange(1.0, 5.0), index=index, dtype=dtype)
    result = obj.unstack(level=-1, sort=False)

    if frame_or_series is DataFrame:
        expected_columns = MultiIndex.from_tuples([(0, "b"), (0, "a")])
    else:
        expected_columns = ["b", "a"]
    expected = DataFrame(
        [[1.0, np.nan], [np.nan, 2.0], [3.0, np.nan], [np.nan, 4.0]],
        columns=expected_columns,
        index=MultiIndex.from_tuples(
            [("two", "z"), ("two", "y"), ("one", "z"), ("one", "y")]
        ),
        dtype=dtype,
    )
    tm.assert_frame_equal(result, expected)

    result = obj.unstack(level=[1, 2], sort=False)

    if frame_or_series is DataFrame:
        expected_columns = MultiIndex.from_tuples([(0, "z", "b"), (0, "y", "a")])
    else:
        expected_columns = MultiIndex.from_tuples([("z", "b"), ("y", "a")])
    expected = DataFrame(
        [[1.0, 2.0], [3.0, 4.0]],
        index=["two", "one"],
        columns=expected_columns,
        dtype=dtype,
    )
    tm.assert_frame_equal(result, expected)


def test_unstack_fill_frame_object():
    # GH12815 Test unstacking with object.
    data = Series(["a", "b", "c", "a"], dtype="object")
    data.index = MultiIndex.from_tuples(
        [("x", "a"), ("x", "b"), ("y", "b"), ("z", "a")]
    )

    # By default missing values will be NaN
    result = data.unstack()
    expected = DataFrame(
        {"a": ["a", np.nan, "a"], "b": ["b", "c", np.nan]},
        index=list("xyz"),
        dtype=object,
    )
    tm.assert_frame_equal(result, expected)

    # Fill with any value replaces missing values as expected
    result = data.unstack(fill_value="d")
    expected = DataFrame(
        {"a": ["a", "d", "a"], "b": ["b", "c", "d"]}, index=list("xyz"), dtype=object
    )
    tm.assert_frame_equal(result, expected)


def test_unstack_timezone_aware_values():
    # GH 18338
    df = DataFrame(
        {
            "timestamp": [pd.Timestamp("2017-08-27 01:00:00.709949+0000", tz="UTC")],
            "a": ["a"],
            "b": ["b"],
            "c": ["c"],
        },
        columns=["timestamp", "a", "b", "c"],
    )
    result = df.set_index(["a", "b"]).unstack()
    expected = DataFrame(
        [[pd.Timestamp("2017-08-27 01:00:00.709949+0000", tz="UTC"), "c"]],
        index=Index(["a"], name="a"),
        columns=MultiIndex(
            levels=[["timestamp", "c"], ["b"]],
            codes=[[0, 1], [0, 0]],
            names=[None, "b"],
        ),
    )
    tm.assert_frame_equal(result, expected)


def test_stack_timezone_aware_values(future_stack):
    # GH 19420
    ts = date_range(freq="D", start="20180101", end="20180103", tz="America/New_York")
    df = DataFrame({"A": ts}, index=["a", "b", "c"])
    result = df.stack(future_stack=future_stack)
    expected = Series(
        ts,
        index=MultiIndex(levels=[["a", "b", "c"], ["A"]], codes=[[0, 1, 2], [0, 0, 0]]),
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.filterwarnings("ignore:The previous implementation of stack is deprecated")
@pytest.mark.parametrize("dropna", [True, False, lib.no_default])
def test_stack_empty_frame(dropna, future_stack):
    # GH 36113
    levels = [np.array([], dtype=np.int64), np.array([], dtype=np.int64)]
    expected = Series(dtype=np.float64, index=MultiIndex(levels=levels, codes=[[], []]))
    if future_stack and dropna is not lib.no_default:
        with pytest.raises(ValueError, match="dropna must be unspecified"):
            DataFrame(dtype=np.float64).stack(dropna=dropna, future_stack=future_stack)
    else:
        result = DataFrame(dtype=np.float64).stack(
            dropna=dropna, future_stack=future_stack
        )
        tm.assert_series_equal(result, expected)


@pytest.mark.filterwarnings("ignore:The previous implementation of stack is deprecated")
@pytest.mark.parametrize("dropna", [True, False, lib.no_default])
@pytest.mark.parametrize("fill_value", [None, 0])
def test_stack_unstack_empty_frame(dropna, fill_value, future_stack):
    # GH 36113
    if future_stack and dropna is not lib.no_default:
        with pytest.raises(ValueError, match="dropna must be unspecified"):
            DataFrame(dtype=np.int64).stack(
                dropna=dropna, future_stack=future_stack
            ).unstack(fill_value=fill_value)
    else:
        result = (
            DataFrame(dtype=np.int64)
            .stack(dropna=dropna, future_stack=future_stack)
            .unstack(fill_value=fill_value)
        )
        expected = DataFrame(dtype=np.int64)
        tm.assert_frame_equal(result, expected)


def test_unstack_single_index_series():
    # GH 36113
    msg = r"index must be a MultiIndex to unstack.*"
    with pytest.raises(ValueError, match=msg):
        Series(dtype=np.int64).unstack()


def test_unstacking_multi_index_df():
    # see gh-30740
    df = DataFrame(
        {
            "name": ["Alice", "Bob"],
            "score": [9.5, 8],
            "employed": [False, True],
            "kids": [0, 0],
            "gender": ["female", "male"],
        }
    )
    df = df.set_index(["name", "employed", "kids", "gender"])
    df = df.unstack(["gender"], fill_value=0)
    expected = df.unstack("employed", fill_value=0).unstack("kids", fill_value=0)
    result = df.unstack(["employed", "kids"], fill_value=0)
    expected = DataFrame(
        [[9.5, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 8.0]],
        index=Index(["Alice", "Bob"], name="name"),
        columns=MultiIndex.from_tuples(
            [
                ("score", "female", False, 0),
                ("score", "female", True, 0),
                ("score", "male", False, 0),
                ("score", "male", True, 0),
            ],
            names=[None, "gender", "employed", "kids"],
        ),
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.filterwarnings("ignore:The previous implementation of stack is deprecated")
def test_stack_positional_level_duplicate_column_names(future_stack):
    # https://github.com/pandas-dev/pandas/issues/36353
    columns = MultiIndex.from_product([("x", "y"), ("y", "z")], names=["a", "a"])
    df = DataFrame([[1, 1, 1, 1]], columns=columns)
    result = df.stack(0, future_stack=future_stack)

    new_columns = Index(["y", "z"], name="a")
    new_index = MultiIndex.from_tuples([(0, "x"), (0, "y")], names=[None, "a"])
    expected = DataFrame([[1, 1], [1, 1]], index=new_index, columns=new_columns)

    tm.assert_frame_equal(result, expected)


def test_unstack_non_slice_like_blocks(using_array_manager):
    # Case where the mgr_locs of a DataFrame's underlying blocks are not slice-like

    mi = MultiIndex.from_product([range(5), ["A", "B", "C"]])
    df = DataFrame(
        {
            0: np.random.default_rng(2).standard_normal(15),
            1: np.random.default_rng(2).standard_normal(15).astype(np.int64),
            2: np.random.default_rng(2).standard_normal(15),
            3: np.random.default_rng(2).standard_normal(15),
        },
        index=mi,
    )
    if not using_array_manager:
        assert any(not x.mgr_locs.is_slice_like for x in df._mgr.blocks)

    res = df.unstack()

    expected = pd.concat([df[n].unstack() for n in range(4)], keys=range(4), axis=1)
    tm.assert_frame_equal(res, expected)


@pytest.mark.filterwarnings("ignore:The previous implementation of stack is deprecated")
def test_stack_sort_false(future_stack):
    # GH 15105
    data = [[1, 2, 3.0, 4.0], [2, 3, 4.0, 5.0], [3, 4, np.nan, np.nan]]
    df = DataFrame(
        data,
        columns=MultiIndex(
            levels=[["B", "A"], ["x", "y"]], codes=[[0, 0, 1, 1], [0, 1, 0, 1]]
        ),
    )
    kwargs = {} if future_stack else {"sort": False}
    result = df.stack(level=0, future_stack=future_stack, **kwargs)
    if future_stack:
        expected = DataFrame(
            {
                "x": [1.0, 3.0, 2.0, 4.0, 3.0, np.nan],
                "y": [2.0, 4.0, 3.0, 5.0, 4.0, np.nan],
            },
            index=MultiIndex.from_arrays(
                [[0, 0, 1, 1, 2, 2], ["B", "A", "B", "A", "B", "A"]]
            ),
        )
    else:
        expected = DataFrame(
            {"x": [1.0, 3.0, 2.0, 4.0, 3.0], "y": [2.0, 4.0, 3.0, 5.0, 4.0]},
            index=MultiIndex.from_arrays([[0, 0, 1, 1, 2], ["B", "A", "B", "A", "B"]]),
        )
    tm.assert_frame_equal(result, expected)

    # Codes sorted in this call
    df = DataFrame(
        data,
        columns=MultiIndex.from_arrays([["B", "B", "A", "A"], ["x", "y", "x", "y"]]),
    )
    kwargs = {} if future_stack else {"sort": False}
    result = df.stack(level=0, future_stack=future_stack, **kwargs)
    tm.assert_frame_equal(result, expected)


@pytest.mark.filterwarnings("ignore:The previous implementation of stack is deprecated")
def test_stack_sort_false_multi_level(future_stack):
    # GH 15105
    idx = MultiIndex.from_tuples([("weight", "kg"), ("height", "m")])
    df = DataFrame([[1.0, 2.0], [3.0, 4.0]], index=["cat", "dog"], columns=idx)
    kwargs = {} if future_stack else {"sort": False}
    result = df.stack([0, 1], future_stack=future_stack, **kwargs)
    expected_index = MultiIndex.from_tuples(
        [
            ("cat", "weight", "kg"),
            ("cat", "height", "m"),
            ("dog", "weight", "kg"),
            ("dog", "height", "m"),
        ]
    )
    expected = Series([1.0, 2.0, 3.0, 4.0], index=expected_index)
    tm.assert_series_equal(result, expected)


class TestStackUnstackMultiLevel:
    def test_unstack(self, multiindex_year_month_day_dataframe_random_data):
        # just check that it works for now
        ymd = multiindex_year_month_day_dataframe_random_data

        unstacked = ymd.unstack()
        unstacked.unstack()

        # test that ints work
        ymd.astype(int).unstack()

        # test that int32 work
        ymd.astype(np.int32).unstack()

    @pytest.mark.parametrize(
        "result_rows,result_columns,index_product,expected_row",
        [
            (
                [[1, 1, None, None, 30.0, None], [2, 2, None, None, 30.0, None]],
                ["ix1", "ix2", "col1", "col2", "col3", "col4"],
                2,
                [None, None, 30.0, None],
            ),
            (
                [[1, 1, None, None, 30.0], [2, 2, None, None, 30.0]],
                ["ix1", "ix2", "col1", "col2", "col3"],
                2,
                [None, None, 30.0],
            ),
            (
                [[1, 1, None, None, 30.0], [2, None, None, None, 30.0]],
                ["ix1", "ix2", "col1", "col2", "col3"],
                None,
                [None, None, 30.0],
            ),
        ],
    )
    def test_unstack_partial(
        self, result_rows, result_columns, index_product, expected_row
    ):
        # check for regressions on this issue:
        # https://github.com/pandas-dev/pandas/issues/19351
        # make sure DataFrame.unstack() works when its run on a subset of the DataFrame
        # and the Index levels contain values that are not present in the subset
        result = DataFrame(result_rows, columns=result_columns).set_index(
            ["ix1", "ix2"]
        )
        result = result.iloc[1:2].unstack("ix2")
        expected = DataFrame(
            [expected_row],
            columns=MultiIndex.from_product(
                [result_columns[2:], [index_product]], names=[None, "ix2"]
            ),
            index=Index([2], name="ix1"),
        )
        tm.assert_frame_equal(result, expected)

    def test_unstack_multiple_no_empty_columns(self):
        index = MultiIndex.from_tuples(
            [(0, "foo", 0), (0, "bar", 0), (1, "baz", 1), (1, "qux", 1)]
        )

        s = Series(np.random.default_rng(2).standard_normal(4), index=index)

        unstacked = s.unstack([1, 2])
        expected = unstacked.dropna(axis=1, how="all")
        tm.assert_frame_equal(unstacked, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack(self, multiindex_year_month_day_dataframe_random_data, future_stack):
        ymd = multiindex_year_month_day_dataframe_random_data

        # regular roundtrip
        unstacked = ymd.unstack()
        restacked = unstacked.stack(future_stack=future_stack)
        if future_stack:
            # NA values in unstacked persist to restacked in version 3
            restacked = restacked.dropna(how="all")
        tm.assert_frame_equal(restacked, ymd)

        unlexsorted = ymd.sort_index(level=2)

        unstacked = unlexsorted.unstack(2)
        restacked = unstacked.stack(future_stack=future_stack)
        if future_stack:
            # NA values in unstacked persist to restacked in version 3
            restacked = restacked.dropna(how="all")
        tm.assert_frame_equal(restacked.sort_index(level=0), ymd)

        unlexsorted = unlexsorted[::-1]
        unstacked = unlexsorted.unstack(1)
        restacked = unstacked.stack(future_stack=future_stack).swaplevel(1, 2)
        if future_stack:
            # NA values in unstacked persist to restacked in version 3
            restacked = restacked.dropna(how="all")
        tm.assert_frame_equal(restacked.sort_index(level=0), ymd)

        unlexsorted = unlexsorted.swaplevel(0, 1)
        unstacked = unlexsorted.unstack(0).swaplevel(0, 1, axis=1)
        restacked = unstacked.stack(0, future_stack=future_stack).swaplevel(1, 2)
        if future_stack:
            # NA values in unstacked persist to restacked in version 3
            restacked = restacked.dropna(how="all")
        tm.assert_frame_equal(restacked.sort_index(level=0), ymd)

        # columns unsorted
        unstacked = ymd.unstack()
        restacked = unstacked.stack(future_stack=future_stack)
        if future_stack:
            # NA values in unstacked persist to restacked in version 3
            restacked = restacked.dropna(how="all")
        tm.assert_frame_equal(restacked, ymd)

        # more than 2 levels in the columns
        unstacked = ymd.unstack(1).unstack(1)

        result = unstacked.stack(1, future_stack=future_stack)
        expected = ymd.unstack()
        tm.assert_frame_equal(result, expected)

        result = unstacked.stack(2, future_stack=future_stack)
        expected = ymd.unstack(1)
        tm.assert_frame_equal(result, expected)

        result = unstacked.stack(0, future_stack=future_stack)
        expected = ymd.stack(future_stack=future_stack).unstack(1).unstack(1)
        tm.assert_frame_equal(result, expected)

        # not all levels present in each echelon
        unstacked = ymd.unstack(2).loc[:, ::3]
        stacked = unstacked.stack(future_stack=future_stack).stack(
            future_stack=future_stack
        )
        ymd_stacked = ymd.stack(future_stack=future_stack)
        if future_stack:
            # NA values in unstacked persist to restacked in version 3
            stacked = stacked.dropna(how="all")
            ymd_stacked = ymd_stacked.dropna(how="all")
        tm.assert_series_equal(stacked, ymd_stacked.reindex(stacked.index))

        # stack with negative number
        result = ymd.unstack(0).stack(-2, future_stack=future_stack)
        expected = ymd.unstack(0).stack(0, future_stack=future_stack)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize(
        "idx, columns, exp_idx",
        [
            [
                list("abab"),
                ["1st", "2nd", "1st"],
                MultiIndex(
                    levels=[["a", "b"], ["1st", "2nd"]],
                    codes=[np.tile(np.arange(2).repeat(3), 2), np.tile([0, 1, 0], 4)],
                ),
            ],
            [
                MultiIndex.from_tuples((("a", 2), ("b", 1), ("a", 1), ("b", 2))),
                ["1st", "2nd", "1st"],
                MultiIndex(
                    levels=[["a", "b"], [1, 2], ["1st", "2nd"]],
                    codes=[
                        np.tile(np.arange(2).repeat(3), 2),
                        np.repeat([1, 0, 1], [3, 6, 3]),
                        np.tile([0, 1, 0], 4),
                    ],
                ),
            ],
        ],
    )
    def test_stack_duplicate_index(self, idx, columns, exp_idx, future_stack):
        # GH10417
        df = DataFrame(
            np.arange(12).reshape(4, 3),
            index=idx,
            columns=columns,
        )
        if future_stack:
            msg = "Columns with duplicate values are not supported in stack"
            with pytest.raises(ValueError, match=msg):
                df.stack(future_stack=future_stack)
        else:
            result = df.stack(future_stack=future_stack)
            expected = Series(np.arange(12), index=exp_idx)
            tm.assert_series_equal(result, expected)
            assert result.index.is_unique is False
            li, ri = result.index, expected.index
            tm.assert_index_equal(li, ri)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_unstack_odd_failure(self, future_stack):
        mi = MultiIndex.from_arrays(
            [
                ["Fri"] * 4 + ["Sat"] * 2 + ["Sun"] * 2 + ["Thu"] * 3,
                ["Dinner"] * 2 + ["Lunch"] * 2 + ["Dinner"] * 5 + ["Lunch"] * 2,
                ["No", "Yes"] * 4 + ["No", "No", "Yes"],
            ],
            names=["day", "time", "smoker"],
        )
        df = DataFrame(
            {
                "sum": np.arange(11, dtype="float64"),
                "len": np.arange(11, dtype="float64"),
            },
            index=mi,
        )
        # it works, #2100
        result = df.unstack(2)

        recons = result.stack(future_stack=future_stack)
        if future_stack:
            # NA values in unstacked persist to restacked in version 3
            recons = recons.dropna(how="all")
        tm.assert_frame_equal(recons, df)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_mixed_dtype(self, multiindex_dataframe_random_data, future_stack):
        frame = multiindex_dataframe_random_data

        df = frame.T
        df["foo", "four"] = "foo"
        df = df.sort_index(level=1, axis=1)

        stacked = df.stack(future_stack=future_stack)
        result = df["foo"].stack(future_stack=future_stack).sort_index()
        tm.assert_series_equal(stacked["foo"], result, check_names=False)
        assert result.name is None
        assert stacked["bar"].dtype == np.float64

    def test_unstack_bug(self, future_stack):
        df = DataFrame(
            {
                "state": ["naive", "naive", "naive", "active", "active", "active"],
                "exp": ["a", "b", "b", "b", "a", "a"],
                "barcode": [1, 2, 3, 4, 1, 3],
                "v": ["hi", "hi", "bye", "bye", "bye", "peace"],
                "extra": np.arange(6.0),
            }
        )

        msg = "DataFrameGroupBy.apply operated on the grouping columns"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.groupby(["state", "exp", "barcode", "v"]).apply(len)

        unstacked = result.unstack()
        restacked = unstacked.stack(future_stack=future_stack)
        tm.assert_series_equal(restacked, result.reindex(restacked.index).astype(float))

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_unstack_preserve_names(
        self, multiindex_dataframe_random_data, future_stack
    ):
        frame = multiindex_dataframe_random_data

        unstacked = frame.unstack()
        assert unstacked.index.name == "first"
        assert unstacked.columns.names == ["exp", "second"]

        restacked = unstacked.stack(future_stack=future_stack)
        assert restacked.index.names == frame.index.names

    @pytest.mark.parametrize("method", ["stack", "unstack"])
    def test_stack_unstack_wrong_level_name(
        self, method, multiindex_dataframe_random_data, future_stack
    ):
        # GH 18303 - wrong level name should raise
        frame = multiindex_dataframe_random_data

        # A DataFrame with flat axes:
        df = frame.loc["foo"]

        kwargs = {"future_stack": future_stack} if method == "stack" else {}
        with pytest.raises(KeyError, match="does not match index name"):
            getattr(df, method)("mistake", **kwargs)

        if method == "unstack":
            # Same on a Series:
            s = df.iloc[:, 0]
            with pytest.raises(KeyError, match="does not match index name"):
                getattr(s, method)("mistake", **kwargs)

    def test_unstack_level_name(self, multiindex_dataframe_random_data):
        frame = multiindex_dataframe_random_data

        result = frame.unstack("second")
        expected = frame.unstack(level=1)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_level_name(self, multiindex_dataframe_random_data, future_stack):
        frame = multiindex_dataframe_random_data

        unstacked = frame.unstack("second")
        result = unstacked.stack("exp", future_stack=future_stack)
        expected = frame.unstack().stack(0, future_stack=future_stack)
        tm.assert_frame_equal(result, expected)

        result = frame.stack("exp", future_stack=future_stack)
        expected = frame.stack(future_stack=future_stack)
        tm.assert_series_equal(result, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_unstack_multiple(
        self, multiindex_year_month_day_dataframe_random_data, future_stack
    ):
        ymd = multiindex_year_month_day_dataframe_random_data

        unstacked = ymd.unstack(["year", "month"])
        expected = ymd.unstack("year").unstack("month")
        tm.assert_frame_equal(unstacked, expected)
        assert unstacked.columns.names == expected.columns.names

        # series
        s = ymd["A"]
        s_unstacked = s.unstack(["year", "month"])
        tm.assert_frame_equal(s_unstacked, expected["A"])

        restacked = unstacked.stack(["year", "month"], future_stack=future_stack)
        if future_stack:
            # NA values in unstacked persist to restacked in version 3
            restacked = restacked.dropna(how="all")
        restacked = restacked.swaplevel(0, 1).swaplevel(1, 2)
        restacked = restacked.sort_index(level=0)

        tm.assert_frame_equal(restacked, ymd)
        assert restacked.index.names == ymd.index.names

        # GH #451
        unstacked = ymd.unstack([1, 2])
        expected = ymd.unstack(1).unstack(1).dropna(axis=1, how="all")
        tm.assert_frame_equal(unstacked, expected)

        unstacked = ymd.unstack([2, 1])
        expected = ymd.unstack(2).unstack(1).dropna(axis=1, how="all")
        tm.assert_frame_equal(unstacked, expected.loc[:, unstacked.columns])

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_names_and_numbers(
        self, multiindex_year_month_day_dataframe_random_data, future_stack
    ):
        ymd = multiindex_year_month_day_dataframe_random_data

        unstacked = ymd.unstack(["year", "month"])

        # Can't use mixture of names and numbers to stack
        with pytest.raises(ValueError, match="level should contain"):
            unstacked.stack([0, "month"], future_stack=future_stack)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_multiple_out_of_bounds(
        self, multiindex_year_month_day_dataframe_random_data, future_stack
    ):
        # nlevels == 3
        ymd = multiindex_year_month_day_dataframe_random_data

        unstacked = ymd.unstack(["year", "month"])

        with pytest.raises(IndexError, match="Too many levels"):
            unstacked.stack([2, 3], future_stack=future_stack)
        with pytest.raises(IndexError, match="not a valid level number"):
            unstacked.stack([-4, -3], future_stack=future_stack)

    def test_unstack_period_series(self):
        # GH4342
        idx1 = pd.PeriodIndex(
            ["2013-01", "2013-01", "2013-02", "2013-02", "2013-03", "2013-03"],
            freq="M",
            name="period",
        )
        idx2 = Index(["A", "B"] * 3, name="str")
        value = [1, 2, 3, 4, 5, 6]

        idx = MultiIndex.from_arrays([idx1, idx2])
        s = Series(value, index=idx)

        result1 = s.unstack()
        result2 = s.unstack(level=1)
        result3 = s.unstack(level=0)

        e_idx = pd.PeriodIndex(
            ["2013-01", "2013-02", "2013-03"], freq="M", name="period"
        )
        expected = DataFrame(
            {"A": [1, 3, 5], "B": [2, 4, 6]}, index=e_idx, columns=["A", "B"]
        )
        expected.columns.name = "str"

        tm.assert_frame_equal(result1, expected)
        tm.assert_frame_equal(result2, expected)
        tm.assert_frame_equal(result3, expected.T)

        idx1 = pd.PeriodIndex(
            ["2013-01", "2013-01", "2013-02", "2013-02", "2013-03", "2013-03"],
            freq="M",
            name="period1",
        )

        idx2 = pd.PeriodIndex(
            ["2013-12", "2013-11", "2013-10", "2013-09", "2013-08", "2013-07"],
            freq="M",
            name="period2",
        )
        idx = MultiIndex.from_arrays([idx1, idx2])
        s = Series(value, index=idx)

        result1 = s.unstack()
        result2 = s.unstack(level=1)
        result3 = s.unstack(level=0)

        e_idx = pd.PeriodIndex(
            ["2013-01", "2013-02", "2013-03"], freq="M", name="period1"
        )
        e_cols = pd.PeriodIndex(
            ["2013-07", "2013-08", "2013-09", "2013-10", "2013-11", "2013-12"],
            freq="M",
            name="period2",
        )
        expected = DataFrame(
            [
                [np.nan, np.nan, np.nan, np.nan, 2, 1],
                [np.nan, np.nan, 4, 3, np.nan, np.nan],
                [6, 5, np.nan, np.nan, np.nan, np.nan],
            ],
            index=e_idx,
            columns=e_cols,
        )

        tm.assert_frame_equal(result1, expected)
        tm.assert_frame_equal(result2, expected)
        tm.assert_frame_equal(result3, expected.T)

    def test_unstack_period_frame(self):
        # GH4342
        idx1 = pd.PeriodIndex(
            ["2014-01", "2014-02", "2014-02", "2014-02", "2014-01", "2014-01"],
            freq="M",
            name="period1",
        )
        idx2 = pd.PeriodIndex(
            ["2013-12", "2013-12", "2014-02", "2013-10", "2013-10", "2014-02"],
            freq="M",
            name="period2",
        )
        value = {"A": [1, 2, 3, 4, 5, 6], "B": [6, 5, 4, 3, 2, 1]}
        idx = MultiIndex.from_arrays([idx1, idx2])
        df = DataFrame(value, index=idx)

        result1 = df.unstack()
        result2 = df.unstack(level=1)
        result3 = df.unstack(level=0)

        e_1 = pd.PeriodIndex(["2014-01", "2014-02"], freq="M", name="period1")
        e_2 = pd.PeriodIndex(
            ["2013-10", "2013-12", "2014-02", "2013-10", "2013-12", "2014-02"],
            freq="M",
            name="period2",
        )
        e_cols = MultiIndex.from_arrays(["A A A B B B".split(), e_2])
        expected = DataFrame(
            [[5, 1, 6, 2, 6, 1], [4, 2, 3, 3, 5, 4]], index=e_1, columns=e_cols
        )

        tm.assert_frame_equal(result1, expected)
        tm.assert_frame_equal(result2, expected)

        e_1 = pd.PeriodIndex(
            ["2014-01", "2014-02", "2014-01", "2014-02"], freq="M", name="period1"
        )
        e_2 = pd.PeriodIndex(
            ["2013-10", "2013-12", "2014-02"], freq="M", name="period2"
        )
        e_cols = MultiIndex.from_arrays(["A A B B".split(), e_1])
        expected = DataFrame(
            [[5, 4, 2, 3], [1, 2, 6, 5], [6, 3, 1, 4]], index=e_2, columns=e_cols
        )

        tm.assert_frame_equal(result3, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_multiple_bug(self, future_stack, using_infer_string):
        # bug when some uniques are not present in the data GH#3170
        id_col = ([1] * 3) + ([2] * 3)
        name = (["a"] * 3) + (["b"] * 3)
        date = pd.to_datetime(["2013-01-03", "2013-01-04", "2013-01-05"] * 2)
        var1 = np.random.default_rng(2).integers(0, 100, 6)
        df = DataFrame({"ID": id_col, "NAME": name, "DATE": date, "VAR1": var1})

        multi = df.set_index(["DATE", "ID"])
        multi.columns.name = "Params"
        unst = multi.unstack("ID")
        msg = re.escape("agg function failed [how->mean,dtype->")
        if using_infer_string:
            msg = "dtype 'str' does not support operation 'mean'"
        with pytest.raises(TypeError, match=msg):
            unst.resample("W-THU").mean()
        down = unst.resample("W-THU").mean(numeric_only=True)
        rs = down.stack("ID", future_stack=future_stack)
        xp = (
            unst.loc[:, ["VAR1"]]
            .resample("W-THU")
            .mean()
            .stack("ID", future_stack=future_stack)
        )
        xp.columns.name = "Params"
        tm.assert_frame_equal(rs, xp)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_dropna(self, future_stack):
        # GH#3997
        df = DataFrame({"A": ["a1", "a2"], "B": ["b1", "b2"], "C": [1, 1]})
        df = df.set_index(["A", "B"])

        dropna = False if not future_stack else lib.no_default
        stacked = df.unstack().stack(dropna=dropna, future_stack=future_stack)
        assert len(stacked) > len(stacked.dropna())

        if future_stack:
            with pytest.raises(ValueError, match="dropna must be unspecified"):
                df.unstack().stack(dropna=True, future_stack=future_stack)
        else:
            stacked = df.unstack().stack(dropna=True, future_stack=future_stack)
            tm.assert_frame_equal(stacked, stacked.dropna())

    def test_unstack_multiple_hierarchical(self, future_stack):
        df = DataFrame(
            index=[
                [0, 0, 0, 0, 1, 1, 1, 1],
                [0, 0, 1, 1, 0, 0, 1, 1],
                [0, 1, 0, 1, 0, 1, 0, 1],
            ],
            columns=[[0, 0, 1, 1], [0, 1, 0, 1]],
        )

        df.index.names = ["a", "b", "c"]
        df.columns.names = ["d", "e"]

        # it works!
        df.unstack(["b", "c"])

    def test_unstack_sparse_keyspace(self):
        # memory problems with naive impl GH#2278
        # Generate Long File & Test Pivot
        NUM_ROWS = 1000

        df = DataFrame(
            {
                "A": np.random.default_rng(2).integers(100, size=NUM_ROWS),
                "B": np.random.default_rng(3).integers(300, size=NUM_ROWS),
                "C": np.random.default_rng(4).integers(-7, 7, size=NUM_ROWS),
                "D": np.random.default_rng(5).integers(-19, 19, size=NUM_ROWS),
                "E": np.random.default_rng(6).integers(3000, size=NUM_ROWS),
                "F": np.random.default_rng(7).standard_normal(NUM_ROWS),
            }
        )

        idf = df.set_index(["A", "B", "C", "D", "E"])

        # it works! is sufficient
        idf.unstack("E")

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_unstack_unobserved_keys(self, future_stack):
        # related to GH#2278 refactoring
        levels = [[0, 1], [0, 1, 2, 3]]
        codes = [[0, 0, 1, 1], [0, 2, 0, 2]]

        index = MultiIndex(levels, codes)

        df = DataFrame(np.random.default_rng(2).standard_normal((4, 2)), index=index)

        result = df.unstack()
        assert len(result.columns) == 4

        recons = result.stack(future_stack=future_stack)
        tm.assert_frame_equal(recons, df)

    @pytest.mark.slow
    def test_unstack_number_of_levels_larger_than_int32(self, monkeypatch):
        # GH#20601
        # GH 26314: Change ValueError to PerformanceWarning

        class MockUnstacker(reshape_lib._Unstacker):
            def __init__(self, *args, **kwargs) -> None:
                # __init__ will raise the warning
                super().__init__(*args, **kwargs)
                raise Exception("Don't compute final result.")

        with monkeypatch.context() as m:
            m.setattr(reshape_lib, "_Unstacker", MockUnstacker)
            df = DataFrame(
                np.zeros((2**16, 2)),
                index=[np.arange(2**16), np.arange(2**16)],
            )
            msg = "The following operation may generate"
            with tm.assert_produces_warning(PerformanceWarning, match=msg):
                with pytest.raises(Exception, match="Don't compute final result."):
                    df.unstack()

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    @pytest.mark.parametrize(
        "levels",
        itertools.chain.from_iterable(
            itertools.product(itertools.permutations([0, 1, 2], width), repeat=2)
            for width in [2, 3]
        ),
    )
    @pytest.mark.parametrize("stack_lev", range(2))
    @pytest.mark.parametrize("sort", [True, False])
    def test_stack_order_with_unsorted_levels(
        self, levels, stack_lev, sort, future_stack
    ):
        # GH#16323
        # deep check for 1-row case
        columns = MultiIndex(levels=levels, codes=[[0, 0, 1, 1], [0, 1, 0, 1]])
        df = DataFrame(columns=columns, data=[range(4)])
        kwargs = {} if future_stack else {"sort": sort}
        df_stacked = df.stack(stack_lev, future_stack=future_stack, **kwargs)
        for row in df.index:
            for col in df.columns:
                expected = df.loc[row, col]
                result_row = row, col[stack_lev]
                result_col = col[1 - stack_lev]
                result = df_stacked.loc[result_row, result_col]
                assert result == expected

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_order_with_unsorted_levels_multi_row(self, future_stack):
        # GH#16323

        # check multi-row case
        mi = MultiIndex(
            levels=[["A", "C", "B"], ["B", "A", "C"]],
            codes=[np.repeat(range(3), 3), np.tile(range(3), 3)],
        )
        df = DataFrame(
            columns=mi, index=range(5), data=np.arange(5 * len(mi)).reshape(5, -1)
        )
        assert all(
            df.loc[row, col]
            == df.stack(0, future_stack=future_stack).loc[(row, col[0]), col[1]]
            for row in df.index
            for col in df.columns
        )

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_order_with_unsorted_levels_multi_row_2(self, future_stack):
        # GH#53636
        levels = ((0, 1), (1, 0))
        stack_lev = 1
        columns = MultiIndex(levels=levels, codes=[[0, 0, 1, 1], [0, 1, 0, 1]])
        df = DataFrame(columns=columns, data=[range(4)], index=[1, 0, 2, 3])
        kwargs = {} if future_stack else {"sort": True}
        result = df.stack(stack_lev, future_stack=future_stack, **kwargs)
        expected_index = MultiIndex(
            levels=[[0, 1, 2, 3], [0, 1]],
            codes=[[1, 1, 0, 0, 2, 2, 3, 3], [1, 0, 1, 0, 1, 0, 1, 0]],
        )
        expected = DataFrame(
            {
                0: [0, 1, 0, 1, 0, 1, 0, 1],
                1: [2, 3, 2, 3, 2, 3, 2, 3],
            },
            index=expected_index,
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_unstack_unordered_multiindex(self, future_stack):
        # GH# 18265
        values = np.arange(5)
        data = np.vstack(
            [
                [f"b{x}" for x in values],  # b0, b1, ..
                [f"a{x}" for x in values],  # a0, a1, ..
            ]
        )
        df = DataFrame(data.T, columns=["b", "a"])
        df.columns.name = "first"
        second_level_dict = {"x": df}
        multi_level_df = pd.concat(second_level_dict, axis=1)
        multi_level_df.columns.names = ["second", "first"]
        df = multi_level_df.reindex(sorted(multi_level_df.columns), axis=1)
        result = df.stack(["first", "second"], future_stack=future_stack).unstack(
            ["first", "second"]
        )
        expected = DataFrame(
            [["a0", "b0"], ["a1", "b1"], ["a2", "b2"], ["a3", "b3"], ["a4", "b4"]],
            index=[0, 1, 2, 3, 4],
            columns=MultiIndex.from_tuples(
                [("a", "x"), ("b", "x")], names=["first", "second"]
            ),
        )
        tm.assert_frame_equal(result, expected)

    def test_unstack_preserve_types(
        self, multiindex_year_month_day_dataframe_random_data, using_infer_string
    ):
        # GH#403
        ymd = multiindex_year_month_day_dataframe_random_data
        ymd["E"] = "foo"
        ymd["F"] = 2

        unstacked = ymd.unstack("month")
        assert unstacked["A", 1].dtype == np.float64
        assert (
            unstacked["E", 1].dtype == np.object_
            if not using_infer_string
            else "string"
        )
        assert unstacked["F", 1].dtype == np.float64

    def test_unstack_group_index_overflow(self, future_stack):
        codes = np.tile(np.arange(500), 2)
        level = np.arange(500)

        index = MultiIndex(
            levels=[level] * 8 + [[0, 1]],
            codes=[codes] * 8 + [np.arange(2).repeat(500)],
        )

        s = Series(np.arange(1000), index=index)
        result = s.unstack()
        assert result.shape == (500, 2)

        # test roundtrip
        stacked = result.stack(future_stack=future_stack)
        tm.assert_series_equal(s, stacked.reindex(s.index))

        # put it at beginning
        index = MultiIndex(
            levels=[[0, 1]] + [level] * 8,
            codes=[np.arange(2).repeat(500)] + [codes] * 8,
        )

        s = Series(np.arange(1000), index=index)
        result = s.unstack(0)
        assert result.shape == (500, 2)

        # put it in middle
        index = MultiIndex(
            levels=[level] * 4 + [[0, 1]] + [level] * 4,
            codes=([codes] * 4 + [np.arange(2).repeat(500)] + [codes] * 4),
        )

        s = Series(np.arange(1000), index=index)
        result = s.unstack(4)
        assert result.shape == (500, 2)

    def test_unstack_with_missing_int_cast_to_float(self, using_array_manager):
        # https://github.com/pandas-dev/pandas/issues/37115
        df = DataFrame(
            {
                "a": ["A", "A", "B"],
                "b": ["ca", "cb", "cb"],
                "v": [10] * 3,
            }
        ).set_index(["a", "b"])

        # add another int column to get 2 blocks
        df["is_"] = 1
        if not using_array_manager:
            assert len(df._mgr.blocks) == 2

        result = df.unstack("b")
        result[("is_", "ca")] = result[("is_", "ca")].fillna(0)

        expected = DataFrame(
            [[10.0, 10.0, 1.0, 1.0], [np.nan, 10.0, 0.0, 1.0]],
            index=Index(["A", "B"], name="a"),
            columns=MultiIndex.from_tuples(
                [("v", "ca"), ("v", "cb"), ("is_", "ca"), ("is_", "cb")],
                names=[None, "b"],
            ),
        )
        if using_array_manager:
            # INFO(ArrayManager) with ArrayManager preserve dtype where possible
            expected[("v", "cb")] = expected[("v", "cb")].astype("int64")
            expected[("is_", "cb")] = expected[("is_", "cb")].astype("int64")
        tm.assert_frame_equal(result, expected)

    def test_unstack_with_level_has_nan(self):
        # GH 37510
        df1 = DataFrame(
            {
                "L1": [1, 2, 3, 4],
                "L2": [3, 4, 1, 2],
                "L3": [1, 1, 1, 1],
                "x": [1, 2, 3, 4],
            }
        )
        df1 = df1.set_index(["L1", "L2", "L3"])
        new_levels = ["n1", "n2", "n3", None]
        df1.index = df1.index.set_levels(levels=new_levels, level="L1")
        df1.index = df1.index.set_levels(levels=new_levels, level="L2")

        result = df1.unstack("L3")[("x", 1)].sort_index().index
        expected = MultiIndex(
            levels=[["n1", "n2", "n3", None], ["n1", "n2", "n3", None]],
            codes=[[0, 1, 2, 3], [2, 3, 0, 1]],
            names=["L1", "L2"],
        )

        tm.assert_index_equal(result, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_nan_in_multiindex_columns(self, future_stack):
        # GH#39481
        df = DataFrame(
            np.zeros([1, 5]),
            columns=MultiIndex.from_tuples(
                [
                    (0, None, None),
                    (0, 2, 0),
                    (0, 2, 1),
                    (0, 3, 0),
                    (0, 3, 1),
                ],
            ),
        )
        result = df.stack(2, future_stack=future_stack)
        if future_stack:
            index = MultiIndex(levels=[[0], [0.0, 1.0]], codes=[[0, 0, 0], [-1, 0, 1]])
            columns = MultiIndex(levels=[[0], [2, 3]], codes=[[0, 0, 0], [-1, 0, 1]])
        else:
            index = Index([(0, None), (0, 0), (0, 1)])
            columns = Index([(0, None), (0, 2), (0, 3)])
        expected = DataFrame(
            [[0.0, np.nan, np.nan], [np.nan, 0.0, 0.0], [np.nan, 0.0, 0.0]],
            index=index,
            columns=columns,
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_multi_level_stack_categorical(self, future_stack):
        # GH 15239
        midx = MultiIndex.from_arrays(
            [
                ["A"] * 2 + ["B"] * 2,
                pd.Categorical(list("abab")),
                pd.Categorical(list("ccdd")),
            ]
        )
        df = DataFrame(np.arange(8).reshape(2, 4), columns=midx)
        result = df.stack([1, 2], future_stack=future_stack)
        if future_stack:
            expected = DataFrame(
                [
                    [0, np.nan],
                    [1, np.nan],
                    [np.nan, 2],
                    [np.nan, 3],
                    [4, np.nan],
                    [5, np.nan],
                    [np.nan, 6],
                    [np.nan, 7],
                ],
                columns=["A", "B"],
                index=MultiIndex.from_arrays(
                    [
                        [0] * 4 + [1] * 4,
                        pd.Categorical(list("abababab")),
                        pd.Categorical(list("ccddccdd")),
                    ]
                ),
            )
        else:
            expected = DataFrame(
                [
                    [0, np.nan],
                    [np.nan, 2],
                    [1, np.nan],
                    [np.nan, 3],
                    [4, np.nan],
                    [np.nan, 6],
                    [5, np.nan],
                    [np.nan, 7],
                ],
                columns=["A", "B"],
                index=MultiIndex.from_arrays(
                    [
                        [0] * 4 + [1] * 4,
                        pd.Categorical(list("aabbaabb")),
                        pd.Categorical(list("cdcdcdcd")),
                    ]
                ),
            )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_nan_level(self, future_stack):
        # GH 9406
        df_nan = DataFrame(
            np.arange(4).reshape(2, 2),
            columns=MultiIndex.from_tuples(
                [("A", np.nan), ("B", "b")], names=["Upper", "Lower"]
            ),
            index=Index([0, 1], name="Num"),
            dtype=np.float64,
        )
        result = df_nan.stack(future_stack=future_stack)
        if future_stack:
            index = MultiIndex(
                levels=[[0, 1], [np.nan, "b"]],
                codes=[[0, 0, 1, 1], [0, 1, 0, 1]],
                names=["Num", "Lower"],
            )
        else:
            index = MultiIndex.from_tuples(
                [(0, np.nan), (0, "b"), (1, np.nan), (1, "b")], names=["Num", "Lower"]
            )
        expected = DataFrame(
            [[0.0, np.nan], [np.nan, 1], [2.0, np.nan], [np.nan, 3.0]],
            columns=Index(["A", "B"], name="Upper"),
            index=index,
        )
        tm.assert_frame_equal(result, expected)

    def test_unstack_categorical_columns(self):
        # GH 14018
        idx = MultiIndex.from_product([["A"], [0, 1]])
        df = DataFrame({"cat": pd.Categorical(["a", "b"])}, index=idx)
        result = df.unstack()
        expected = DataFrame(
            {
                0: pd.Categorical(["a"], categories=["a", "b"]),
                1: pd.Categorical(["b"], categories=["a", "b"]),
            },
            index=["A"],
        )
        expected.columns = MultiIndex.from_tuples([("cat", 0), ("cat", 1)])
        tm.assert_frame_equal(result, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_unsorted(self, future_stack):
        # GH 16925
        PAE = ["ITA", "FRA"]
        VAR = ["A1", "A2"]
        TYP = ["CRT", "DBT", "NET"]
        MI = MultiIndex.from_product([PAE, VAR, TYP], names=["PAE", "VAR", "TYP"])

        V = list(range(len(MI)))
        DF = DataFrame(data=V, index=MI, columns=["VALUE"])

        DF = DF.unstack(["VAR", "TYP"])
        DF.columns = DF.columns.droplevel(0)
        DF.loc[:, ("A0", "NET")] = 9999

        result = DF.stack(["VAR", "TYP"], future_stack=future_stack).sort_index()
        expected = (
            DF.sort_index(axis=1)
            .stack(["VAR", "TYP"], future_stack=future_stack)
            .sort_index()
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    def test_stack_nullable_dtype(self, future_stack):
        # GH#43561
        columns = MultiIndex.from_product(
            [["54511", "54515"], ["r", "t_mean"]], names=["station", "element"]
        )
        index = Index([1, 2, 3], name="time")

        arr = np.array([[50, 226, 10, 215], [10, 215, 9, 220], [305, 232, 111, 220]])
        df = DataFrame(arr, columns=columns, index=index, dtype=pd.Int64Dtype())

        result = df.stack("station", future_stack=future_stack)

        expected = (
            df.astype(np.int64)
            .stack("station", future_stack=future_stack)
            .astype(pd.Int64Dtype())
        )
        tm.assert_frame_equal(result, expected)

        # non-homogeneous case
        df[df.columns[0]] = df[df.columns[0]].astype(pd.Float64Dtype())
        result = df.stack("station", future_stack=future_stack)

        expected = DataFrame(
            {
                "r": pd.array(
                    [50.0, 10.0, 10.0, 9.0, 305.0, 111.0], dtype=pd.Float64Dtype()
                ),
                "t_mean": pd.array(
                    [226, 215, 215, 220, 232, 220], dtype=pd.Int64Dtype()
                ),
            },
            index=MultiIndex.from_product([index, columns.levels[0]]),
        )
        expected.columns.name = "element"
        tm.assert_frame_equal(result, expected)

    def test_unstack_mixed_level_names(self):
        # GH#48763
        arrays = [["a", "a"], [1, 2], ["red", "blue"]]
        idx = MultiIndex.from_arrays(arrays, names=("x", 0, "y"))
        df = DataFrame({"m": [1, 2]}, index=idx)
        result = df.unstack("x")
        expected = DataFrame(
            [[1], [2]],
            columns=MultiIndex.from_tuples([("m", "a")], names=[None, "x"]),
            index=MultiIndex.from_tuples([(1, "red"), (2, "blue")], names=[0, "y"]),
        )
        tm.assert_frame_equal(result, expected)


def test_stack_tuple_columns(future_stack):
    # GH#54948 - test stack when the input has a non-MultiIndex with tuples
    df = DataFrame(
        [[1, 2, 3], [4, 5, 6], [7, 8, 9]], columns=[("a", 1), ("a", 2), ("b", 1)]
    )
    result = df.stack(future_stack=future_stack)
    expected = Series(
        [1, 2, 3, 4, 5, 6, 7, 8, 9],
        index=MultiIndex(
            levels=[[0, 1, 2], [("a", 1), ("a", 2), ("b", 1)]],
            codes=[[0, 0, 0, 1, 1, 1, 2, 2, 2], [0, 1, 2, 0, 1, 2, 0, 1, 2]],
        ),
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "dtype, na_value",
    [
        ("float64", np.nan),
        ("Float64", np.nan),
        ("Float64", pd.NA),
        ("Int64", pd.NA),
    ],
)
@pytest.mark.parametrize("test_multiindex", [True, False])
def test_stack_preserves_na(dtype, na_value, test_multiindex):
    # GH#56573
    if test_multiindex:
        index = MultiIndex.from_arrays(2 * [Index([na_value], dtype=dtype)])
    else:
        index = Index([na_value], dtype=dtype)
    df = DataFrame({"a": [1]}, index=index)
    result = df.stack(future_stack=True)

    if test_multiindex:
        expected_index = MultiIndex.from_arrays(
            [
                Index([na_value], dtype=dtype),
                Index([na_value], dtype=dtype),
                Index(["a"]),
            ]
        )
    else:
        expected_index = MultiIndex.from_arrays(
            [
                Index([na_value], dtype=dtype),
                Index(["a"]),
            ]
        )
    expected = Series(1, index=expected_index)
    tm.assert_series_equal(result, expected)
