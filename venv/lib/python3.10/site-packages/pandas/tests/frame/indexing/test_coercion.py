"""
Tests for values coercion in setitem-like operations on DataFrame.

For the most part, these should be multi-column DataFrames, otherwise
we would share the tests with Series.
"""
import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    MultiIndex,
    NaT,
    Series,
    Timestamp,
    date_range,
)
import pandas._testing as tm


class TestDataFrameSetitemCoercion:
    @pytest.mark.parametrize("consolidate", [True, False])
    def test_loc_setitem_multiindex_columns(self, consolidate):
        # GH#18415 Setting values in a single column preserves dtype,
        #  while setting them in multiple columns did unwanted cast.

        # Note that A here has 2 blocks, below we do the same thing
        #  with a consolidated frame.
        A = DataFrame(np.zeros((6, 5), dtype=np.float32))
        A = pd.concat([A, A], axis=1, keys=[1, 2])
        if consolidate:
            A = A._consolidate()

        A.loc[2:3, (1, slice(2, 3))] = np.ones((2, 2), dtype=np.float32)
        assert (A.dtypes == np.float32).all()

        A.loc[0:5, (1, slice(2, 3))] = np.ones((6, 2), dtype=np.float32)

        assert (A.dtypes == np.float32).all()

        A.loc[:, (1, slice(2, 3))] = np.ones((6, 2), dtype=np.float32)
        assert (A.dtypes == np.float32).all()

        # TODO: i think this isn't about MultiIndex and could be done with iloc?


def test_37477():
    # fixed by GH#45121
    orig = DataFrame({"A": [1, 2, 3], "B": [3, 4, 5]})
    expected = DataFrame({"A": [1, 2, 3], "B": [3, 1.2, 5]})

    df = orig.copy()
    with tm.assert_produces_warning(
        FutureWarning, match="Setting an item of incompatible dtype"
    ):
        df.at[1, "B"] = 1.2
    tm.assert_frame_equal(df, expected)

    df = orig.copy()
    with tm.assert_produces_warning(
        FutureWarning, match="Setting an item of incompatible dtype"
    ):
        df.loc[1, "B"] = 1.2
    tm.assert_frame_equal(df, expected)

    df = orig.copy()
    with tm.assert_produces_warning(
        FutureWarning, match="Setting an item of incompatible dtype"
    ):
        df.iat[1, 1] = 1.2
    tm.assert_frame_equal(df, expected)

    df = orig.copy()
    with tm.assert_produces_warning(
        FutureWarning, match="Setting an item of incompatible dtype"
    ):
        df.iloc[1, 1] = 1.2
    tm.assert_frame_equal(df, expected)


def test_6942(indexer_al):
    # check that the .at __setitem__ after setting "Live" actually sets the data
    start = Timestamp("2014-04-01")
    t1 = Timestamp("2014-04-23 12:42:38.883082")
    t2 = Timestamp("2014-04-24 01:33:30.040039")

    dti = date_range(start, periods=1)
    orig = DataFrame(index=dti, columns=["timenow", "Live"])

    df = orig.copy()
    indexer_al(df)[start, "timenow"] = t1

    df["Live"] = True

    df.at[start, "timenow"] = t2
    assert df.iloc[0, 0] == t2


def test_26395(indexer_al):
    # .at case fixed by GH#45121 (best guess)
    df = DataFrame(index=["A", "B", "C"])
    df["D"] = 0

    indexer_al(df)["C", "D"] = 2
    expected = DataFrame({"D": [0, 0, 2]}, index=["A", "B", "C"], dtype=np.int64)
    tm.assert_frame_equal(df, expected)

    with tm.assert_produces_warning(
        FutureWarning, match="Setting an item of incompatible dtype"
    ):
        indexer_al(df)["C", "D"] = 44.5
    expected = DataFrame(
        {"D": [0, 0, 44.5]},
        index=["A", "B", "C"],
        columns=["D"],
        dtype=np.float64,
    )
    tm.assert_frame_equal(df, expected)

    with tm.assert_produces_warning(
        FutureWarning, match="Setting an item of incompatible dtype"
    ):
        indexer_al(df)["C", "D"] = "hello"
    expected = DataFrame(
        {"D": [0, 0, "hello"]},
        index=["A", "B", "C"],
        columns=["D"],
        dtype=object,
    )
    tm.assert_frame_equal(df, expected)


@pytest.mark.xfail(reason="unwanted upcast")
def test_15231():
    df = DataFrame([[1, 2], [3, 4]], columns=["a", "b"])
    df.loc[2] = Series({"a": 5, "b": 6})
    assert (df.dtypes == np.int64).all()

    df.loc[3] = Series({"a": 7})

    # df["a"] doesn't have any NaNs, should not have been cast
    exp_dtypes = Series([np.int64, np.float64], dtype=object, index=["a", "b"])
    tm.assert_series_equal(df.dtypes, exp_dtypes)


def test_iloc_setitem_unnecesssary_float_upcasting():
    # GH#12255
    df = DataFrame(
        {
            0: np.array([1, 3], dtype=np.float32),
            1: np.array([2, 4], dtype=np.float32),
            2: ["a", "b"],
        }
    )
    orig = df.copy()

    values = df[0].values.reshape(2, 1)
    df.iloc[:, 0:1] = values

    tm.assert_frame_equal(df, orig)


@pytest.mark.xfail(reason="unwanted casting to dt64")
def test_12499():
    # TODO: OP in GH#12499 used np.datetim64("NaT") instead of pd.NaT,
    #  which has consequences for the expected df["two"] (though i think at
    #  the time it might not have because of a separate bug). See if it makes
    #  a difference which one we use here.
    ts = Timestamp("2016-03-01 03:13:22.98986", tz="UTC")

    data = [{"one": 0, "two": ts}]
    orig = DataFrame(data)
    df = orig.copy()
    df.loc[1] = [np.nan, NaT]

    expected = DataFrame(
        {"one": [0, np.nan], "two": Series([ts, NaT], dtype="datetime64[ns, UTC]")}
    )
    tm.assert_frame_equal(df, expected)

    data = [{"one": 0, "two": ts}]
    df = orig.copy()
    df.loc[1, :] = [np.nan, NaT]
    tm.assert_frame_equal(df, expected)


def test_20476():
    mi = MultiIndex.from_product([["A", "B"], ["a", "b", "c"]])
    df = DataFrame(-1, index=range(3), columns=mi)
    filler = DataFrame([[1, 2, 3.0]] * 3, index=range(3), columns=["a", "b", "c"])
    df["A"] = filler

    expected = DataFrame(
        {
            0: [1, 1, 1],
            1: [2, 2, 2],
            2: [3.0, 3.0, 3.0],
            3: [-1, -1, -1],
            4: [-1, -1, -1],
            5: [-1, -1, -1],
        }
    )
    expected.columns = mi
    exp_dtypes = Series(
        [np.dtype(np.int64)] * 2 + [np.dtype(np.float64)] + [np.dtype(np.int64)] * 3,
        index=mi,
    )
    tm.assert_series_equal(df.dtypes, exp_dtypes)
