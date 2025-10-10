import re

import numpy as np
import pytest

from pandas import (
    Categorical,
    CategoricalDtype,
    CategoricalIndex,
    DataFrame,
    DateOffset,
    DatetimeIndex,
    Index,
    MultiIndex,
    Series,
    Timestamp,
    concat,
    date_range,
    get_dummies,
    period_range,
)
import pandas._testing as tm
from pandas.core.arrays import SparseArray


class TestGetitem:
    def test_getitem_unused_level_raises(self):
        # GH#20410
        mi = MultiIndex(
            levels=[["a_lot", "onlyone", "notevenone"], [1970, ""]],
            codes=[[1, 0], [1, 0]],
        )
        df = DataFrame(-1, index=range(3), columns=mi)

        with pytest.raises(KeyError, match="notevenone"):
            df["notevenone"]

    def test_getitem_periodindex(self):
        rng = period_range("1/1/2000", periods=5)
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 5)), columns=rng)

        ts = df[rng[0]]
        tm.assert_series_equal(ts, df.iloc[:, 0])

        ts = df["1/1/2000"]
        tm.assert_series_equal(ts, df.iloc[:, 0])

    def test_getitem_list_of_labels_categoricalindex_cols(self):
        # GH#16115
        cats = Categorical([Timestamp("12-31-1999"), Timestamp("12-31-2000")])

        expected = DataFrame([[1, 0], [0, 1]], dtype="bool", index=[0, 1], columns=cats)
        dummies = get_dummies(cats)
        result = dummies[list(dummies.columns)]
        tm.assert_frame_equal(result, expected)

    def test_getitem_sparse_column_return_type_and_dtype(self):
        # https://github.com/pandas-dev/pandas/issues/23559
        data = SparseArray([0, 1])
        df = DataFrame({"A": data})
        expected = Series(data, name="A")
        result = df["A"]
        tm.assert_series_equal(result, expected)

        # Also check iloc and loc while we're here
        result = df.iloc[:, 0]
        tm.assert_series_equal(result, expected)

        result = df.loc[:, "A"]
        tm.assert_series_equal(result, expected)

    def test_getitem_string_columns(self):
        # GH#46185
        df = DataFrame([[1, 2]], columns=Index(["A", "B"], dtype="string"))
        result = df.A
        expected = df["A"]
        tm.assert_series_equal(result, expected)


class TestGetitemListLike:
    def test_getitem_list_missing_key(self):
        # GH#13822, incorrect error string with non-unique columns when missing
        # column is accessed
        df = DataFrame({"x": [1.0], "y": [2.0], "z": [3.0]})
        df.columns = ["x", "x", "z"]

        # Check that we get the correct value in the KeyError
        with pytest.raises(KeyError, match=r"\['y'\] not in index"):
            df[["x", "y", "z"]]

    def test_getitem_list_duplicates(self):
        # GH#1943
        df = DataFrame(
            np.random.default_rng(2).standard_normal((4, 4)), columns=list("AABC")
        )
        df.columns.name = "foo"

        result = df[["B", "C"]]
        assert result.columns.name == "foo"

        expected = df.iloc[:, 2:]
        tm.assert_frame_equal(result, expected)

    def test_getitem_dupe_cols(self):
        df = DataFrame([[1, 2, 3], [4, 5, 6]], columns=["a", "a", "b"])
        msg = "\"None of [Index(['baf'], dtype="
        with pytest.raises(KeyError, match=re.escape(msg)):
            df[["baf"]]

    @pytest.mark.parametrize(
        "idx_type",
        [
            list,
            iter,
            Index,
            set,
            lambda keys: dict(zip(keys, range(len(keys)))),
            lambda keys: dict(zip(keys, range(len(keys)))).keys(),
        ],
        ids=["list", "iter", "Index", "set", "dict", "dict_keys"],
    )
    @pytest.mark.parametrize("levels", [1, 2])
    def test_getitem_listlike(self, idx_type, levels, float_frame):
        # GH#21294

        if levels == 1:
            frame, missing = float_frame, "food"
        else:
            # MultiIndex columns
            frame = DataFrame(
                np.random.default_rng(2).standard_normal((8, 3)),
                columns=Index(
                    [("foo", "bar"), ("baz", "qux"), ("peek", "aboo")],
                    name=("sth", "sth2"),
                ),
            )
            missing = ("good", "food")

        keys = [frame.columns[1], frame.columns[0]]
        idx = idx_type(keys)
        idx_check = list(idx_type(keys))

        if isinstance(idx, (set, dict)):
            with pytest.raises(TypeError, match="as an indexer is not supported"):
                frame[idx]

            return
        else:
            result = frame[idx]

        expected = frame.loc[:, idx_check]
        expected.columns.names = frame.columns.names

        tm.assert_frame_equal(result, expected)

        idx = idx_type(keys + [missing])
        with pytest.raises(KeyError, match="not in index"):
            frame[idx]

    def test_getitem_iloc_generator(self):
        # GH#39614
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        indexer = (x for x in [1, 2])
        result = df.iloc[indexer]
        expected = DataFrame({"a": [2, 3], "b": [5, 6]}, index=[1, 2])
        tm.assert_frame_equal(result, expected)

    def test_getitem_iloc_two_dimensional_generator(self):
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        indexer = (x for x in [1, 2])
        result = df.iloc[indexer, 1]
        expected = Series([5, 6], name="b", index=[1, 2])
        tm.assert_series_equal(result, expected)

    def test_getitem_iloc_dateoffset_days(self):
        # GH 46671
        df = DataFrame(
            list(range(10)),
            index=date_range("01-01-2022", periods=10, freq=DateOffset(days=1)),
        )
        result = df.loc["2022-01-01":"2022-01-03"]
        expected = DataFrame(
            [0, 1, 2],
            index=DatetimeIndex(
                ["2022-01-01", "2022-01-02", "2022-01-03"],
                dtype="datetime64[ns]",
                freq=DateOffset(days=1),
            ),
        )
        tm.assert_frame_equal(result, expected)

        df = DataFrame(
            list(range(10)),
            index=date_range(
                "01-01-2022", periods=10, freq=DateOffset(days=1, hours=2)
            ),
        )
        result = df.loc["2022-01-01":"2022-01-03"]
        expected = DataFrame(
            [0, 1, 2],
            index=DatetimeIndex(
                ["2022-01-01 00:00:00", "2022-01-02 02:00:00", "2022-01-03 04:00:00"],
                dtype="datetime64[ns]",
                freq=DateOffset(days=1, hours=2),
            ),
        )
        tm.assert_frame_equal(result, expected)

        df = DataFrame(
            list(range(10)),
            index=date_range("01-01-2022", periods=10, freq=DateOffset(minutes=3)),
        )
        result = df.loc["2022-01-01":"2022-01-03"]
        tm.assert_frame_equal(result, df)


class TestGetitemCallable:
    def test_getitem_callable(self, float_frame):
        # GH#12533
        result = float_frame[lambda x: "A"]
        expected = float_frame.loc[:, "A"]
        tm.assert_series_equal(result, expected)

        result = float_frame[lambda x: ["A", "B"]]
        expected = float_frame.loc[:, ["A", "B"]]
        tm.assert_frame_equal(result, float_frame.loc[:, ["A", "B"]])

        df = float_frame[:3]
        result = df[lambda x: [True, False, True]]
        expected = float_frame.iloc[[0, 2], :]
        tm.assert_frame_equal(result, expected)

    def test_loc_multiindex_columns_one_level(self):
        # GH#29749
        df = DataFrame([[1, 2]], columns=[["a", "b"]])
        expected = DataFrame([1], columns=[["a"]])

        result = df["a"]
        tm.assert_frame_equal(result, expected)

        result = df.loc[:, "a"]
        tm.assert_frame_equal(result, expected)


class TestGetitemBooleanMask:
    def test_getitem_bool_mask_categorical_index(self):
        df3 = DataFrame(
            {
                "A": np.arange(6, dtype="int64"),
            },
            index=CategoricalIndex(
                [1, 1, 2, 1, 3, 2],
                dtype=CategoricalDtype([3, 2, 1], ordered=True),
                name="B",
            ),
        )
        df4 = DataFrame(
            {
                "A": np.arange(6, dtype="int64"),
            },
            index=CategoricalIndex(
                [1, 1, 2, 1, 3, 2],
                dtype=CategoricalDtype([3, 2, 1], ordered=False),
                name="B",
            ),
        )

        result = df3[df3.index == "a"]
        expected = df3.iloc[[]]
        tm.assert_frame_equal(result, expected)

        result = df4[df4.index == "a"]
        expected = df4.iloc[[]]
        tm.assert_frame_equal(result, expected)

        result = df3[df3.index == 1]
        expected = df3.iloc[[0, 1, 3]]
        tm.assert_frame_equal(result, expected)

        result = df4[df4.index == 1]
        expected = df4.iloc[[0, 1, 3]]
        tm.assert_frame_equal(result, expected)

        # since we have an ordered categorical

        # CategoricalIndex([1, 1, 2, 1, 3, 2],
        #         categories=[3, 2, 1],
        #         ordered=True,
        #         name='B')
        result = df3[df3.index < 2]
        expected = df3.iloc[[4]]
        tm.assert_frame_equal(result, expected)

        result = df3[df3.index > 1]
        expected = df3.iloc[[]]
        tm.assert_frame_equal(result, expected)

        # unordered
        # cannot be compared

        # CategoricalIndex([1, 1, 2, 1, 3, 2],
        #         categories=[3, 2, 1],
        #         ordered=False,
        #         name='B')
        msg = "Unordered Categoricals can only compare equality or not"
        with pytest.raises(TypeError, match=msg):
            df4[df4.index < 2]
        with pytest.raises(TypeError, match=msg):
            df4[df4.index > 1]

    @pytest.mark.parametrize(
        "data1,data2,expected_data",
        (
            (
                [[1, 2], [3, 4]],
                [[0.5, 6], [7, 8]],
                [[np.nan, 3.0], [np.nan, 4.0], [np.nan, 7.0], [6.0, 8.0]],
            ),
            (
                [[1, 2], [3, 4]],
                [[5, 6], [7, 8]],
                [[np.nan, 3.0], [np.nan, 4.0], [5, 7], [6, 8]],
            ),
        ),
    )
    def test_getitem_bool_mask_duplicate_columns_mixed_dtypes(
        self,
        data1,
        data2,
        expected_data,
    ):
        # GH#31954

        df1 = DataFrame(np.array(data1))
        df2 = DataFrame(np.array(data2))
        df = concat([df1, df2], axis=1)

        result = df[df > 2]

        exdict = {i: np.array(col) for i, col in enumerate(expected_data)}
        expected = DataFrame(exdict).rename(columns={2: 0, 3: 1})
        tm.assert_frame_equal(result, expected)

    @pytest.fixture
    def df_dup_cols(self):
        dups = ["A", "A", "C", "D"]
        df = DataFrame(np.arange(12).reshape(3, 4), columns=dups, dtype="float64")
        return df

    def test_getitem_boolean_frame_unaligned_with_duplicate_columns(self, df_dup_cols):
        # `df.A > 6` is a DataFrame with a different shape from df

        # boolean with the duplicate raises
        df = df_dup_cols
        msg = "cannot reindex on an axis with duplicate labels"
        with pytest.raises(ValueError, match=msg):
            df[df.A > 6]

    def test_getitem_boolean_series_with_duplicate_columns(self, df_dup_cols):
        # boolean indexing
        # GH#4879
        df = DataFrame(
            np.arange(12).reshape(3, 4), columns=["A", "B", "C", "D"], dtype="float64"
        )
        expected = df[df.C > 6]
        expected.columns = df_dup_cols.columns

        df = df_dup_cols
        result = df[df.C > 6]

        tm.assert_frame_equal(result, expected)

    def test_getitem_boolean_frame_with_duplicate_columns(self, df_dup_cols):
        # where
        df = DataFrame(
            np.arange(12).reshape(3, 4), columns=["A", "B", "C", "D"], dtype="float64"
        )
        # `df > 6` is a DataFrame with the same shape+alignment as df
        expected = df[df > 6]
        expected.columns = df_dup_cols.columns

        df = df_dup_cols
        result = df[df > 6]

        tm.assert_frame_equal(result, expected)

    def test_getitem_empty_frame_with_boolean(self):
        # Test for issue GH#11859

        df = DataFrame()
        df2 = df[df > 0]
        tm.assert_frame_equal(df, df2)

    def test_getitem_returns_view_when_column_is_unique_in_df(
        self, using_copy_on_write, warn_copy_on_write
    ):
        # GH#45316
        df = DataFrame([[1, 2, 3], [4, 5, 6]], columns=["a", "a", "b"])
        df_orig = df.copy()
        view = df["b"]
        with tm.assert_cow_warning(warn_copy_on_write):
            view.loc[:] = 100
        if using_copy_on_write:
            expected = df_orig
        else:
            expected = DataFrame([[1, 2, 100], [4, 5, 100]], columns=["a", "a", "b"])
        tm.assert_frame_equal(df, expected)

    def test_getitem_frozenset_unique_in_column(self):
        # GH#41062
        df = DataFrame([[1, 2, 3, 4]], columns=[frozenset(["KEY"]), "B", "C", "C"])
        result = df[frozenset(["KEY"])]
        expected = Series([1], name=frozenset(["KEY"]))
        tm.assert_series_equal(result, expected)


class TestGetitemSlice:
    def test_getitem_slice_float64(self, frame_or_series):
        values = np.arange(10.0, 50.0, 2)
        index = Index(values)

        start, end = values[[5, 15]]

        data = np.random.default_rng(2).standard_normal((20, 3))
        if frame_or_series is not DataFrame:
            data = data[:, 0]

        obj = frame_or_series(data, index=index)

        result = obj[start:end]
        expected = obj.iloc[5:16]
        tm.assert_equal(result, expected)

        result = obj.loc[start:end]
        tm.assert_equal(result, expected)

    def test_getitem_datetime_slice(self):
        # GH#43223
        df = DataFrame(
            {"a": 0},
            index=DatetimeIndex(
                [
                    "11.01.2011 22:00",
                    "11.01.2011 23:00",
                    "12.01.2011 00:00",
                    "2011-01-13 00:00",
                ]
            ),
        )
        with pytest.raises(
            KeyError, match="Value based partial slicing on non-monotonic"
        ):
            df["2011-01-01":"2011-11-01"]

    def test_getitem_slice_same_dim_only_one_axis(self):
        # GH#54622
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 8)))
        result = df.iloc[(slice(None, None, 2),)]
        assert result.shape == (5, 8)
        expected = df.iloc[slice(None, None, 2), slice(None)]
        tm.assert_frame_equal(result, expected)


class TestGetitemDeprecatedIndexers:
    @pytest.mark.parametrize("key", [{"a", "b"}, {"a": "a"}])
    def test_getitem_dict_and_set_deprecated(self, key):
        # GH#42825 enforced in 2.0
        df = DataFrame(
            [[1, 2], [3, 4]], columns=MultiIndex.from_tuples([("a", 1), ("b", 2)])
        )
        with pytest.raises(TypeError, match="as an indexer is not supported"):
            df[key]
