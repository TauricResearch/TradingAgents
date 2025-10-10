from datetime import (
    datetime,
    timezone,
)

import numpy as np
import pytest

from pandas.errors import InvalidIndexError

from pandas import (
    CategoricalDtype,
    CategoricalIndex,
    DataFrame,
    DatetimeIndex,
    MultiIndex,
    Series,
    Timestamp,
)
import pandas._testing as tm


def test_at_timezone():
    # https://github.com/pandas-dev/pandas/issues/33544
    result = DataFrame({"foo": [datetime(2000, 1, 1)]})
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        result.at[0, "foo"] = datetime(2000, 1, 2, tzinfo=timezone.utc)
    expected = DataFrame(
        {"foo": [datetime(2000, 1, 2, tzinfo=timezone.utc)]}, dtype=object
    )
    tm.assert_frame_equal(result, expected)


def test_selection_methods_of_assigned_col():
    # GH 29282
    df = DataFrame(data={"a": [1, 2, 3], "b": [4, 5, 6]})
    df2 = DataFrame(data={"c": [7, 8, 9]}, index=[2, 1, 0])
    df["c"] = df2["c"]
    df.at[1, "c"] = 11
    result = df
    expected = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [9, 11, 7]})
    tm.assert_frame_equal(result, expected)
    result = df.at[1, "c"]
    assert result == 11

    result = df["c"]
    expected = Series([9, 11, 7], name="c")
    tm.assert_series_equal(result, expected)

    result = df[["c"]]
    expected = DataFrame({"c": [9, 11, 7]})
    tm.assert_frame_equal(result, expected)


class TestAtSetItem:
    def test_at_setitem_item_cache_cleared(self):
        # GH#22372 Note the multi-step construction is necessary to trigger
        #  the original bug. pandas/issues/22372#issuecomment-413345309
        df = DataFrame(index=[0])
        df["x"] = 1
        df["cost"] = 2

        # accessing df["cost"] adds "cost" to the _item_cache
        df["cost"]

        # This loc[[0]] lookup used to call _consolidate_inplace at the
        #  BlockManager level, which failed to clear the _item_cache
        df.loc[[0]]

        df.at[0, "x"] = 4
        df.at[0, "cost"] = 789

        expected = DataFrame({"x": [4], "cost": 789}, index=[0])
        tm.assert_frame_equal(df, expected)

        # And in particular, check that the _item_cache has updated correctly.
        tm.assert_series_equal(df["cost"], expected["cost"])

    def test_at_setitem_mixed_index_assignment(self):
        # GH#19860
        ser = Series([1, 2, 3, 4, 5], index=["a", "b", "c", 1, 2])
        ser.at["a"] = 11
        assert ser.iat[0] == 11
        ser.at[1] = 22
        assert ser.iat[3] == 22

    def test_at_setitem_categorical_missing(self):
        df = DataFrame(
            index=range(3), columns=range(3), dtype=CategoricalDtype(["foo", "bar"])
        )
        df.at[1, 1] = "foo"

        expected = DataFrame(
            [
                [np.nan, np.nan, np.nan],
                [np.nan, "foo", np.nan],
                [np.nan, np.nan, np.nan],
            ],
            dtype=CategoricalDtype(["foo", "bar"]),
        )

        tm.assert_frame_equal(df, expected)

    def test_at_setitem_multiindex(self):
        df = DataFrame(
            np.zeros((3, 2), dtype="int64"),
            columns=MultiIndex.from_tuples([("a", 0), ("a", 1)]),
        )
        df.at[0, "a"] = 10
        expected = DataFrame(
            [[10, 10], [0, 0], [0, 0]],
            columns=MultiIndex.from_tuples([("a", 0), ("a", 1)]),
        )
        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize("row", (Timestamp("2019-01-01"), "2019-01-01"))
    def test_at_datetime_index(self, row):
        # Set float64 dtype to avoid upcast when setting .5
        df = DataFrame(
            data=[[1] * 2], index=DatetimeIndex(data=["2019-01-01", "2019-01-02"])
        ).astype({0: "float64"})
        expected = DataFrame(
            data=[[0.5, 1], [1.0, 1]],
            index=DatetimeIndex(data=["2019-01-01", "2019-01-02"]),
        )

        df.at[row, 0] = 0.5
        tm.assert_frame_equal(df, expected)


class TestAtSetItemWithExpansion:
    def test_at_setitem_expansion_series_dt64tz_value(self, tz_naive_fixture):
        # GH#25506
        ts = Timestamp("2017-08-05 00:00:00+0100", tz=tz_naive_fixture)
        result = Series(ts)
        result.at[1] = ts
        expected = Series([ts, ts])
        tm.assert_series_equal(result, expected)


class TestAtWithDuplicates:
    def test_at_with_duplicate_axes_requires_scalar_lookup(self):
        # GH#33041 check that falling back to loc doesn't allow non-scalar
        #  args to slip in

        arr = np.random.default_rng(2).standard_normal(6).reshape(3, 2)
        df = DataFrame(arr, columns=["A", "A"])

        msg = "Invalid call for scalar access"
        with pytest.raises(ValueError, match=msg):
            df.at[[1, 2]]
        with pytest.raises(ValueError, match=msg):
            df.at[1, ["A"]]
        with pytest.raises(ValueError, match=msg):
            df.at[:, "A"]

        with pytest.raises(ValueError, match=msg):
            df.at[[1, 2]] = 1
        with pytest.raises(ValueError, match=msg):
            df.at[1, ["A"]] = 1
        with pytest.raises(ValueError, match=msg):
            df.at[:, "A"] = 1


class TestAtErrors:
    # TODO: De-duplicate/parametrize
    #  test_at_series_raises_key_error2, test_at_frame_raises_key_error2

    def test_at_series_raises_key_error(self, indexer_al):
        # GH#31724 .at should match .loc

        ser = Series([1, 2, 3], index=[3, 2, 1])
        result = indexer_al(ser)[1]
        assert result == 3

        with pytest.raises(KeyError, match="a"):
            indexer_al(ser)["a"]

    def test_at_frame_raises_key_error(self, indexer_al):
        # GH#31724 .at should match .loc

        df = DataFrame({0: [1, 2, 3]}, index=[3, 2, 1])

        result = indexer_al(df)[1, 0]
        assert result == 3

        with pytest.raises(KeyError, match="a"):
            indexer_al(df)["a", 0]

        with pytest.raises(KeyError, match="a"):
            indexer_al(df)[1, "a"]

    def test_at_series_raises_key_error2(self, indexer_al):
        # at should not fallback
        # GH#7814
        # GH#31724 .at should match .loc
        ser = Series([1, 2, 3], index=list("abc"))
        result = indexer_al(ser)["a"]
        assert result == 1

        with pytest.raises(KeyError, match="^0$"):
            indexer_al(ser)[0]

    def test_at_frame_raises_key_error2(self, indexer_al):
        # GH#31724 .at should match .loc
        df = DataFrame({"A": [1, 2, 3]}, index=list("abc"))
        result = indexer_al(df)["a", "A"]
        assert result == 1

        with pytest.raises(KeyError, match="^0$"):
            indexer_al(df)["a", 0]

    def test_at_frame_multiple_columns(self):
        # GH#48296 - at shouldn't modify multiple columns
        df = DataFrame({"a": [1, 2], "b": [3, 4]})
        new_row = [6, 7]
        with pytest.raises(
            InvalidIndexError,
            match=f"You can only assign a scalar value not a \\{type(new_row)}",
        ):
            df.at[5] = new_row

    def test_at_getitem_mixed_index_no_fallback(self):
        # GH#19860
        ser = Series([1, 2, 3, 4, 5], index=["a", "b", "c", 1, 2])
        with pytest.raises(KeyError, match="^0$"):
            ser.at[0]
        with pytest.raises(KeyError, match="^4$"):
            ser.at[4]

    def test_at_categorical_integers(self):
        # CategoricalIndex with integer categories that don't happen to match
        #  the Categorical's codes
        ci = CategoricalIndex([3, 4])

        arr = np.arange(4).reshape(2, 2)
        frame = DataFrame(arr, index=ci)

        for df in [frame, frame.T]:
            for key in [0, 1]:
                with pytest.raises(KeyError, match=str(key)):
                    df.at[key, key]

    def test_at_applied_for_rows(self):
        # GH#48729 .at should raise InvalidIndexError when assigning rows
        df = DataFrame(index=["a"], columns=["col1", "col2"])
        new_row = [123, 15]
        with pytest.raises(
            InvalidIndexError,
            match=f"You can only assign a scalar value not a \\{type(new_row)}",
        ):
            df.at["a"] = new_row
