from datetime import (
    datetime,
    timedelta,
)

import numpy as np
import pytest

from pandas.errors import UnsortedIndexError

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Series,
    Timestamp,
)
import pandas._testing as tm
from pandas.tests.indexing.common import _mklbl


class TestMultiIndexSlicers:
    def test_per_axis_per_level_getitem(self):
        # GH6134
        # example test case
        ix = MultiIndex.from_product(
            [_mklbl("A", 5), _mklbl("B", 7), _mklbl("C", 4), _mklbl("D", 2)]
        )
        df = DataFrame(np.arange(len(ix.to_numpy())), index=ix)

        result = df.loc[(slice("A1", "A3"), slice(None), ["C1", "C3"]), :]
        expected = df.loc[
            [
                (
                    a,
                    b,
                    c,
                    d,
                )
                for a, b, c, d in df.index.values
                if a in ("A1", "A2", "A3") and c in ("C1", "C3")
            ]
        ]
        tm.assert_frame_equal(result, expected)

        expected = df.loc[
            [
                (
                    a,
                    b,
                    c,
                    d,
                )
                for a, b, c, d in df.index.values
                if a in ("A1", "A2", "A3") and c in ("C1", "C2", "C3")
            ]
        ]
        result = df.loc[(slice("A1", "A3"), slice(None), slice("C1", "C3")), :]
        tm.assert_frame_equal(result, expected)

        # test multi-index slicing with per axis and per index controls
        index = MultiIndex.from_tuples(
            [("A", 1), ("A", 2), ("A", 3), ("B", 1)], names=["one", "two"]
        )
        columns = MultiIndex.from_tuples(
            [("a", "foo"), ("a", "bar"), ("b", "foo"), ("b", "bah")],
            names=["lvl0", "lvl1"],
        )

        df = DataFrame(
            np.arange(16, dtype="int64").reshape(4, 4), index=index, columns=columns
        )
        df = df.sort_index(axis=0).sort_index(axis=1)

        # identity
        result = df.loc[(slice(None), slice(None)), :]
        tm.assert_frame_equal(result, df)
        result = df.loc[(slice(None), slice(None)), (slice(None), slice(None))]
        tm.assert_frame_equal(result, df)
        result = df.loc[:, (slice(None), slice(None))]
        tm.assert_frame_equal(result, df)

        # index
        result = df.loc[(slice(None), [1]), :]
        expected = df.iloc[[0, 3]]
        tm.assert_frame_equal(result, expected)

        result = df.loc[(slice(None), 1), :]
        expected = df.iloc[[0, 3]]
        tm.assert_frame_equal(result, expected)

        # columns
        result = df.loc[:, (slice(None), ["foo"])]
        expected = df.iloc[:, [1, 3]]
        tm.assert_frame_equal(result, expected)

        # both
        result = df.loc[(slice(None), 1), (slice(None), ["foo"])]
        expected = df.iloc[[0, 3], [1, 3]]
        tm.assert_frame_equal(result, expected)

        result = df.loc["A", "a"]
        expected = DataFrame(
            {"bar": [1, 5, 9], "foo": [0, 4, 8]},
            index=Index([1, 2, 3], name="two"),
            columns=Index(["bar", "foo"], name="lvl1"),
        )
        tm.assert_frame_equal(result, expected)

        result = df.loc[(slice(None), [1, 2]), :]
        expected = df.iloc[[0, 1, 3]]
        tm.assert_frame_equal(result, expected)

        # multi-level series
        s = Series(np.arange(len(ix.to_numpy())), index=ix)
        result = s.loc["A1":"A3", :, ["C1", "C3"]]
        expected = s.loc[
            [
                (
                    a,
                    b,
                    c,
                    d,
                )
                for a, b, c, d in s.index.values
                if a in ("A1", "A2", "A3") and c in ("C1", "C3")
            ]
        ]
        tm.assert_series_equal(result, expected)

        # boolean indexers
        result = df.loc[(slice(None), df.loc[:, ("a", "bar")] > 5), :]
        expected = df.iloc[[2, 3]]
        tm.assert_frame_equal(result, expected)

        msg = (
            "cannot index with a boolean indexer "
            "that is not the same length as the index"
        )
        with pytest.raises(ValueError, match=msg):
            df.loc[(slice(None), np.array([True, False])), :]

        with pytest.raises(KeyError, match=r"\[1\] not in index"):
            # slice(None) is on the index, [1] is on the columns, but 1 is
            #  not in the columns, so we raise
            #  This used to treat [1] as positional GH#16396
            df.loc[slice(None), [1]]

        # not lexsorted
        assert df.index._lexsort_depth == 2
        df = df.sort_index(level=1, axis=0)
        assert df.index._lexsort_depth == 0

        msg = (
            "MultiIndex slicing requires the index to be "
            r"lexsorted: slicing on levels \[1\], lexsort depth 0"
        )
        with pytest.raises(UnsortedIndexError, match=msg):
            df.loc[(slice(None), slice("bar")), :]

        # GH 16734: not sorted, but no real slicing
        result = df.loc[(slice(None), df.loc[:, ("a", "bar")] > 5), :]
        tm.assert_frame_equal(result, df.iloc[[1, 3], :])

    def test_multiindex_slicers_non_unique(self):
        # GH 7106
        # non-unique mi index support
        df = (
            DataFrame(
                {
                    "A": ["foo", "foo", "foo", "foo"],
                    "B": ["a", "a", "a", "a"],
                    "C": [1, 2, 1, 3],
                    "D": [1, 2, 3, 4],
                }
            )
            .set_index(["A", "B", "C"])
            .sort_index()
        )
        assert not df.index.is_unique
        expected = (
            DataFrame({"A": ["foo", "foo"], "B": ["a", "a"], "C": [1, 1], "D": [1, 3]})
            .set_index(["A", "B", "C"])
            .sort_index()
        )
        result = df.loc[(slice(None), slice(None), 1), :]
        tm.assert_frame_equal(result, expected)

        # this is equivalent of an xs expression
        result = df.xs(1, level=2, drop_level=False)
        tm.assert_frame_equal(result, expected)

        df = (
            DataFrame(
                {
                    "A": ["foo", "foo", "foo", "foo"],
                    "B": ["a", "a", "a", "a"],
                    "C": [1, 2, 1, 2],
                    "D": [1, 2, 3, 4],
                }
            )
            .set_index(["A", "B", "C"])
            .sort_index()
        )
        assert not df.index.is_unique
        expected = (
            DataFrame({"A": ["foo", "foo"], "B": ["a", "a"], "C": [1, 1], "D": [1, 3]})
            .set_index(["A", "B", "C"])
            .sort_index()
        )
        result = df.loc[(slice(None), slice(None), 1), :]
        assert not result.index.is_unique
        tm.assert_frame_equal(result, expected)

        # GH12896
        # numpy-implementation dependent bug
        ints = [
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            12,
            13,
            14,
            14,
            16,
            17,
            18,
            19,
            200000,
            200000,
        ]
        n = len(ints)
        idx = MultiIndex.from_arrays([["a"] * n, ints])
        result = Series([1] * n, index=idx)
        result = result.sort_index()
        result = result.loc[(slice(None), slice(100000))]
        expected = Series([1] * (n - 2), index=idx[:-2]).sort_index()
        tm.assert_series_equal(result, expected)

    def test_multiindex_slicers_datetimelike(self):
        # GH 7429
        # buggy/inconsistent behavior when slicing with datetime-like
        dates = [datetime(2012, 1, 1, 12, 12, 12) + timedelta(days=i) for i in range(6)]
        freq = [1, 2]
        index = MultiIndex.from_product([dates, freq], names=["date", "frequency"])

        df = DataFrame(
            np.arange(6 * 2 * 4, dtype="int64").reshape(-1, 4),
            index=index,
            columns=list("ABCD"),
        )

        # multi-axis slicing
        idx = pd.IndexSlice
        expected = df.iloc[[0, 2, 4], [0, 1]]
        result = df.loc[
            (
                slice(
                    Timestamp("2012-01-01 12:12:12"), Timestamp("2012-01-03 12:12:12")
                ),
                slice(1, 1),
            ),
            slice("A", "B"),
        ]
        tm.assert_frame_equal(result, expected)

        result = df.loc[
            (
                idx[
                    Timestamp("2012-01-01 12:12:12") : Timestamp("2012-01-03 12:12:12")
                ],
                idx[1:1],
            ),
            slice("A", "B"),
        ]
        tm.assert_frame_equal(result, expected)

        result = df.loc[
            (
                slice(
                    Timestamp("2012-01-01 12:12:12"), Timestamp("2012-01-03 12:12:12")
                ),
                1,
            ),
            slice("A", "B"),
        ]
        tm.assert_frame_equal(result, expected)

        # with strings
        result = df.loc[
            (slice("2012-01-01 12:12:12", "2012-01-03 12:12:12"), slice(1, 1)),
            slice("A", "B"),
        ]
        tm.assert_frame_equal(result, expected)

        result = df.loc[
            (idx["2012-01-01 12:12:12":"2012-01-03 12:12:12"], 1), idx["A", "B"]
        ]
        tm.assert_frame_equal(result, expected)

    def test_multiindex_slicers_edges(self):
        # GH 8132
        # various edge cases
        df = DataFrame(
            {
                "A": ["A0"] * 5 + ["A1"] * 5 + ["A2"] * 5,
                "B": ["B0", "B0", "B1", "B1", "B2"] * 3,
                "DATE": [
                    "2013-06-11",
                    "2013-07-02",
                    "2013-07-09",
                    "2013-07-30",
                    "2013-08-06",
                    "2013-06-11",
                    "2013-07-02",
                    "2013-07-09",
                    "2013-07-30",
                    "2013-08-06",
                    "2013-09-03",
                    "2013-10-01",
                    "2013-07-09",
                    "2013-08-06",
                    "2013-09-03",
                ],
                "VALUES": [22, 35, 14, 9, 4, 40, 18, 4, 2, 5, 1, 2, 3, 4, 2],
            }
        )

        df["DATE"] = pd.to_datetime(df["DATE"])
        df1 = df.set_index(["A", "B", "DATE"])
        df1 = df1.sort_index()

        # A1 - Get all values under "A0" and "A1"
        result = df1.loc[(slice("A1")), :]
        expected = df1.iloc[0:10]
        tm.assert_frame_equal(result, expected)

        # A2 - Get all values from the start to "A2"
        result = df1.loc[(slice("A2")), :]
        expected = df1
        tm.assert_frame_equal(result, expected)

        # A3 - Get all values under "B1" or "B2"
        result = df1.loc[(slice(None), slice("B1", "B2")), :]
        expected = df1.iloc[[2, 3, 4, 7, 8, 9, 12, 13, 14]]
        tm.assert_frame_equal(result, expected)

        # A4 - Get all values between 2013-07-02 and 2013-07-09
        result = df1.loc[(slice(None), slice(None), slice("20130702", "20130709")), :]
        expected = df1.iloc[[1, 2, 6, 7, 12]]
        tm.assert_frame_equal(result, expected)

        # B1 - Get all values in B0 that are also under A0, A1 and A2
        result = df1.loc[(slice("A2"), slice("B0")), :]
        expected = df1.iloc[[0, 1, 5, 6, 10, 11]]
        tm.assert_frame_equal(result, expected)

        # B2 - Get all values in B0, B1 and B2 (similar to what #2 is doing for
        # the As)
        result = df1.loc[(slice(None), slice("B2")), :]
        expected = df1
        tm.assert_frame_equal(result, expected)

        # B3 - Get all values from B1 to B2 and up to 2013-08-06
        result = df1.loc[(slice(None), slice("B1", "B2"), slice("2013-08-06")), :]
        expected = df1.iloc[[2, 3, 4, 7, 8, 9, 12, 13]]
        tm.assert_frame_equal(result, expected)

        # B4 - Same as A4 but the start of the date slice is not a key.
        #      shows indexing on a partial selection slice
        result = df1.loc[(slice(None), slice(None), slice("20130701", "20130709")), :]
        expected = df1.iloc[[1, 2, 6, 7, 12]]
        tm.assert_frame_equal(result, expected)

    def test_per_axis_per_level_doc_examples(self):
        # test index maker
        idx = pd.IndexSlice

        # from indexing.rst / advanced
        index = MultiIndex.from_product(
            [_mklbl("A", 4), _mklbl("B", 2), _mklbl("C", 4), _mklbl("D", 2)]
        )
        columns = MultiIndex.from_tuples(
            [("a", "foo"), ("a", "bar"), ("b", "foo"), ("b", "bah")],
            names=["lvl0", "lvl1"],
        )
        df = DataFrame(
            np.arange(len(index) * len(columns), dtype="int64").reshape(
                (len(index), len(columns))
            ),
            index=index,
            columns=columns,
        )
        result = df.loc[(slice("A1", "A3"), slice(None), ["C1", "C3"]), :]
        expected = df.loc[
            [
                (
                    a,
                    b,
                    c,
                    d,
                )
                for a, b, c, d in df.index.values
                if a in ("A1", "A2", "A3") and c in ("C1", "C3")
            ]
        ]
        tm.assert_frame_equal(result, expected)
        result = df.loc[idx["A1":"A3", :, ["C1", "C3"]], :]
        tm.assert_frame_equal(result, expected)

        result = df.loc[(slice(None), slice(None), ["C1", "C3"]), :]
        expected = df.loc[
            [
                (
                    a,
                    b,
                    c,
                    d,
                )
                for a, b, c, d in df.index.values
                if c in ("C1", "C3")
            ]
        ]
        tm.assert_frame_equal(result, expected)
        result = df.loc[idx[:, :, ["C1", "C3"]], :]
        tm.assert_frame_equal(result, expected)

        # not sorted
        msg = (
            "MultiIndex slicing requires the index to be lexsorted: "
            r"slicing on levels \[1\], lexsort depth 1"
        )
        with pytest.raises(UnsortedIndexError, match=msg):
            df.loc["A1", ("a", slice("foo"))]

        # GH 16734: not sorted, but no real slicing
        tm.assert_frame_equal(
            df.loc["A1", (slice(None), "foo")], df.loc["A1"].iloc[:, [0, 2]]
        )

        df = df.sort_index(axis=1)

        # slicing
        df.loc["A1", (slice(None), "foo")]
        df.loc[(slice(None), slice(None), ["C1", "C3"]), (slice(None), "foo")]

        # setitem
        df.loc(axis=0)[:, :, ["C1", "C3"]] = -10

    def test_loc_axis_arguments(self):
        index = MultiIndex.from_product(
            [_mklbl("A", 4), _mklbl("B", 2), _mklbl("C", 4), _mklbl("D", 2)]
        )
        columns = MultiIndex.from_tuples(
            [("a", "foo"), ("a", "bar"), ("b", "foo"), ("b", "bah")],
            names=["lvl0", "lvl1"],
        )
        df = (
            DataFrame(
                np.arange(len(index) * len(columns), dtype="int64").reshape(
                    (len(index), len(columns))
                ),
                index=index,
                columns=columns,
            )
            .sort_index()
            .sort_index(axis=1)
        )

        # axis 0
        result = df.loc(axis=0)["A1":"A3", :, ["C1", "C3"]]
        expected = df.loc[
            [
                (
                    a,
                    b,
                    c,
                    d,
                )
                for a, b, c, d in df.index.values
                if a in ("A1", "A2", "A3") and c in ("C1", "C3")
            ]
        ]
        tm.assert_frame_equal(result, expected)

        result = df.loc(axis="index")[:, :, ["C1", "C3"]]
        expected = df.loc[
            [
                (
                    a,
                    b,
                    c,
                    d,
                )
                for a, b, c, d in df.index.values
                if c in ("C1", "C3")
            ]
        ]
        tm.assert_frame_equal(result, expected)

        # axis 1
        result = df.loc(axis=1)[:, "foo"]
        expected = df.loc[:, (slice(None), "foo")]
        tm.assert_frame_equal(result, expected)

        result = df.loc(axis="columns")[:, "foo"]
        expected = df.loc[:, (slice(None), "foo")]
        tm.assert_frame_equal(result, expected)

        # invalid axis
        for i in [-1, 2, "foo"]:
            msg = f"No axis named {i} for object type DataFrame"
            with pytest.raises(ValueError, match=msg):
                df.loc(axis=i)[:, :, ["C1", "C3"]]

    def test_loc_axis_single_level_multi_col_indexing_multiindex_col_df(self):
        # GH29519
        df = DataFrame(
            np.arange(27).reshape(3, 9),
            columns=MultiIndex.from_product([["a1", "a2", "a3"], ["b1", "b2", "b3"]]),
        )
        result = df.loc(axis=1)["a1":"a2"]
        expected = df.iloc[:, :-3]

        tm.assert_frame_equal(result, expected)

    def test_loc_axis_single_level_single_col_indexing_multiindex_col_df(self):
        # GH29519
        df = DataFrame(
            np.arange(27).reshape(3, 9),
            columns=MultiIndex.from_product([["a1", "a2", "a3"], ["b1", "b2", "b3"]]),
        )
        result = df.loc(axis=1)["a1"]
        expected = df.iloc[:, :3]
        expected.columns = ["b1", "b2", "b3"]

        tm.assert_frame_equal(result, expected)

    def test_loc_ax_single_level_indexer_simple_df(self):
        # GH29519
        # test single level indexing on single index column data frame
        df = DataFrame(np.arange(9).reshape(3, 3), columns=["a", "b", "c"])
        result = df.loc(axis=1)["a"]
        expected = Series(np.array([0, 3, 6]), name="a")
        tm.assert_series_equal(result, expected)

    def test_per_axis_per_level_setitem(self):
        # test index maker
        idx = pd.IndexSlice

        # test multi-index slicing with per axis and per index controls
        index = MultiIndex.from_tuples(
            [("A", 1), ("A", 2), ("A", 3), ("B", 1)], names=["one", "two"]
        )
        columns = MultiIndex.from_tuples(
            [("a", "foo"), ("a", "bar"), ("b", "foo"), ("b", "bah")],
            names=["lvl0", "lvl1"],
        )

        df_orig = DataFrame(
            np.arange(16, dtype="int64").reshape(4, 4), index=index, columns=columns
        )
        df_orig = df_orig.sort_index(axis=0).sort_index(axis=1)

        # identity
        df = df_orig.copy()
        df.loc[(slice(None), slice(None)), :] = 100
        expected = df_orig.copy()
        expected.iloc[:, :] = 100
        tm.assert_frame_equal(df, expected)

        df = df_orig.copy()
        df.loc(axis=0)[:, :] = 100
        expected = df_orig.copy()
        expected.iloc[:, :] = 100
        tm.assert_frame_equal(df, expected)

        df = df_orig.copy()
        df.loc[(slice(None), slice(None)), (slice(None), slice(None))] = 100
        expected = df_orig.copy()
        expected.iloc[:, :] = 100
        tm.assert_frame_equal(df, expected)

        df = df_orig.copy()
        df.loc[:, (slice(None), slice(None))] = 100
        expected = df_orig.copy()
        expected.iloc[:, :] = 100
        tm.assert_frame_equal(df, expected)

        # index
        df = df_orig.copy()
        df.loc[(slice(None), [1]), :] = 100
        expected = df_orig.copy()
        expected.iloc[[0, 3]] = 100
        tm.assert_frame_equal(df, expected)

        df = df_orig.copy()
        df.loc[(slice(None), 1), :] = 100
        expected = df_orig.copy()
        expected.iloc[[0, 3]] = 100
        tm.assert_frame_equal(df, expected)

        df = df_orig.copy()
        df.loc(axis=0)[:, 1] = 100
        expected = df_orig.copy()
        expected.iloc[[0, 3]] = 100
        tm.assert_frame_equal(df, expected)

        # columns
        df = df_orig.copy()
        df.loc[:, (slice(None), ["foo"])] = 100
        expected = df_orig.copy()
        expected.iloc[:, [1, 3]] = 100
        tm.assert_frame_equal(df, expected)

        # both
        df = df_orig.copy()
        df.loc[(slice(None), 1), (slice(None), ["foo"])] = 100
        expected = df_orig.copy()
        expected.iloc[[0, 3], [1, 3]] = 100
        tm.assert_frame_equal(df, expected)

        df = df_orig.copy()
        df.loc[idx[:, 1], idx[:, ["foo"]]] = 100
        expected = df_orig.copy()
        expected.iloc[[0, 3], [1, 3]] = 100
        tm.assert_frame_equal(df, expected)

        df = df_orig.copy()
        df.loc["A", "a"] = 100
        expected = df_orig.copy()
        expected.iloc[0:3, 0:2] = 100
        tm.assert_frame_equal(df, expected)

        # setting with a list-like
        df = df_orig.copy()
        df.loc[(slice(None), 1), (slice(None), ["foo"])] = np.array(
            [[100, 100], [100, 100]], dtype="int64"
        )
        expected = df_orig.copy()
        expected.iloc[[0, 3], [1, 3]] = 100
        tm.assert_frame_equal(df, expected)

        # not enough values
        df = df_orig.copy()

        msg = "setting an array element with a sequence."
        with pytest.raises(ValueError, match=msg):
            df.loc[(slice(None), 1), (slice(None), ["foo"])] = np.array(
                [[100], [100, 100]], dtype="int64"
            )

        msg = "Must have equal len keys and value when setting with an iterable"
        with pytest.raises(ValueError, match=msg):
            df.loc[(slice(None), 1), (slice(None), ["foo"])] = np.array(
                [100, 100, 100, 100], dtype="int64"
            )

        # with an alignable rhs
        df = df_orig.copy()
        df.loc[(slice(None), 1), (slice(None), ["foo"])] = (
            df.loc[(slice(None), 1), (slice(None), ["foo"])] * 5
        )
        expected = df_orig.copy()
        expected.iloc[[0, 3], [1, 3]] = expected.iloc[[0, 3], [1, 3]] * 5
        tm.assert_frame_equal(df, expected)

        df = df_orig.copy()
        df.loc[(slice(None), 1), (slice(None), ["foo"])] *= df.loc[
            (slice(None), 1), (slice(None), ["foo"])
        ]
        expected = df_orig.copy()
        expected.iloc[[0, 3], [1, 3]] *= expected.iloc[[0, 3], [1, 3]]
        tm.assert_frame_equal(df, expected)

        rhs = df_orig.loc[(slice(None), 1), (slice(None), ["foo"])].copy()
        rhs.loc[:, ("c", "bah")] = 10
        df = df_orig.copy()
        df.loc[(slice(None), 1), (slice(None), ["foo"])] *= rhs
        expected = df_orig.copy()
        expected.iloc[[0, 3], [1, 3]] *= expected.iloc[[0, 3], [1, 3]]
        tm.assert_frame_equal(df, expected)

    def test_multiindex_label_slicing_with_negative_step(self):
        ser = Series(
            np.arange(20), MultiIndex.from_product([list("abcde"), np.arange(4)])
        )
        SLC = pd.IndexSlice

        tm.assert_indexing_slices_equivalent(ser, SLC[::-1], SLC[::-1])

        tm.assert_indexing_slices_equivalent(ser, SLC["d"::-1], SLC[15::-1])
        tm.assert_indexing_slices_equivalent(ser, SLC[("d",)::-1], SLC[15::-1])

        tm.assert_indexing_slices_equivalent(ser, SLC[:"d":-1], SLC[:11:-1])
        tm.assert_indexing_slices_equivalent(ser, SLC[:("d",):-1], SLC[:11:-1])

        tm.assert_indexing_slices_equivalent(ser, SLC["d":"b":-1], SLC[15:3:-1])
        tm.assert_indexing_slices_equivalent(ser, SLC[("d",):"b":-1], SLC[15:3:-1])
        tm.assert_indexing_slices_equivalent(ser, SLC["d":("b",):-1], SLC[15:3:-1])
        tm.assert_indexing_slices_equivalent(ser, SLC[("d",):("b",):-1], SLC[15:3:-1])
        tm.assert_indexing_slices_equivalent(ser, SLC["b":"d":-1], SLC[:0])

        tm.assert_indexing_slices_equivalent(ser, SLC[("c", 2)::-1], SLC[10::-1])
        tm.assert_indexing_slices_equivalent(ser, SLC[:("c", 2):-1], SLC[:9:-1])
        tm.assert_indexing_slices_equivalent(
            ser, SLC[("e", 0):("c", 2):-1], SLC[16:9:-1]
        )

    def test_multiindex_slice_first_level(self):
        # GH 12697
        freq = ["a", "b", "c", "d"]
        idx = MultiIndex.from_product([freq, range(500)])
        df = DataFrame(list(range(2000)), index=idx, columns=["Test"])
        df_slice = df.loc[pd.IndexSlice[:, 30:70], :]
        result = df_slice.loc["a"]
        expected = DataFrame(list(range(30, 71)), columns=["Test"], index=range(30, 71))
        tm.assert_frame_equal(result, expected)
        result = df_slice.loc["d"]
        expected = DataFrame(
            list(range(1530, 1571)), columns=["Test"], index=range(30, 71)
        )
        tm.assert_frame_equal(result, expected)

    def test_int_series_slicing(self, multiindex_year_month_day_dataframe_random_data):
        ymd = multiindex_year_month_day_dataframe_random_data
        s = ymd["A"]
        result = s[5:]
        expected = s.reindex(s.index[5:])
        tm.assert_series_equal(result, expected)

        s = ymd["A"].copy()
        exp = ymd["A"].copy()
        s[5:] = 0
        exp.iloc[5:] = 0
        tm.assert_numpy_array_equal(s.values, exp.values)

        result = ymd[5:]
        expected = ymd.reindex(s.index[5:])
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "dtype, loc, iloc",
        [
            # dtype = int, step = -1
            ("int", slice(None, None, -1), slice(None, None, -1)),
            ("int", slice(3, None, -1), slice(3, None, -1)),
            ("int", slice(None, 1, -1), slice(None, 0, -1)),
            ("int", slice(3, 1, -1), slice(3, 0, -1)),
            # dtype = int, step = -2
            ("int", slice(None, None, -2), slice(None, None, -2)),
            ("int", slice(3, None, -2), slice(3, None, -2)),
            ("int", slice(None, 1, -2), slice(None, 0, -2)),
            ("int", slice(3, 1, -2), slice(3, 0, -2)),
            # dtype = str, step = -1
            ("str", slice(None, None, -1), slice(None, None, -1)),
            ("str", slice("d", None, -1), slice(3, None, -1)),
            ("str", slice(None, "b", -1), slice(None, 0, -1)),
            ("str", slice("d", "b", -1), slice(3, 0, -1)),
            # dtype = str, step = -2
            ("str", slice(None, None, -2), slice(None, None, -2)),
            ("str", slice("d", None, -2), slice(3, None, -2)),
            ("str", slice(None, "b", -2), slice(None, 0, -2)),
            ("str", slice("d", "b", -2), slice(3, 0, -2)),
        ],
    )
    def test_loc_slice_negative_stepsize(self, dtype, loc, iloc):
        # GH#38071
        labels = {
            "str": list("abcde"),
            "int": range(5),
        }[dtype]

        mi = MultiIndex.from_arrays([labels] * 2)
        df = DataFrame(1.0, index=mi, columns=["A"])

        SLC = pd.IndexSlice

        expected = df.iloc[iloc, :]
        result_get_loc = df.loc[SLC[loc], :]
        result_get_locs_level_0 = df.loc[SLC[loc, :], :]
        result_get_locs_level_1 = df.loc[SLC[:, loc], :]

        tm.assert_frame_equal(result_get_loc, expected)
        tm.assert_frame_equal(result_get_locs_level_0, expected)
        tm.assert_frame_equal(result_get_locs_level_1, expected)
