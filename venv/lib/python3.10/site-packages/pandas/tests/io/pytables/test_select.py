import numpy as np
import pytest

from pandas._libs.tslibs import Timestamp

import pandas as pd
from pandas import (
    DataFrame,
    HDFStore,
    Index,
    MultiIndex,
    Series,
    _testing as tm,
    bdate_range,
    concat,
    date_range,
    isna,
    read_hdf,
)
from pandas.tests.io.pytables.common import (
    _maybe_remove,
    ensure_clean_store,
)

from pandas.io.pytables import Term

pytestmark = [pytest.mark.single_cpu]


def test_select_columns_in_where(setup_path):
    # GH 6169
    # recreate multi-indexes when columns is passed
    # in the `where` argument
    index = MultiIndex(
        levels=[["foo", "bar", "baz", "qux"], ["one", "two", "three"]],
        codes=[[0, 0, 0, 1, 1, 2, 2, 3, 3, 3], [0, 1, 2, 0, 1, 1, 2, 0, 1, 2]],
        names=["foo_name", "bar_name"],
    )

    # With a DataFrame
    df = DataFrame(
        np.random.default_rng(2).standard_normal((10, 3)),
        index=index,
        columns=["A", "B", "C"],
    )

    with ensure_clean_store(setup_path) as store:
        store.put("df", df, format="table")
        expected = df[["A"]]

        tm.assert_frame_equal(store.select("df", columns=["A"]), expected)

        tm.assert_frame_equal(store.select("df", where="columns=['A']"), expected)

    # With a Series
    s = Series(np.random.default_rng(2).standard_normal(10), index=index, name="A")
    with ensure_clean_store(setup_path) as store:
        store.put("s", s, format="table")
        tm.assert_series_equal(store.select("s", where="columns=['A']"), s)


def test_select_with_dups(setup_path):
    # single dtypes
    df = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)), columns=["A", "A", "B", "B"]
    )
    df.index = date_range("20130101 9:30", periods=10, freq="min")

    with ensure_clean_store(setup_path) as store:
        store.append("df", df)

        result = store.select("df")
        expected = df
        tm.assert_frame_equal(result, expected, by_blocks=True)

        result = store.select("df", columns=df.columns)
        expected = df
        tm.assert_frame_equal(result, expected, by_blocks=True)

        result = store.select("df", columns=["A"])
        expected = df.loc[:, ["A"]]
        tm.assert_frame_equal(result, expected)

    # dups across dtypes
    df = concat(
        [
            DataFrame(
                np.random.default_rng(2).standard_normal((10, 4)),
                columns=["A", "A", "B", "B"],
            ),
            DataFrame(
                np.random.default_rng(2).integers(0, 10, size=20).reshape(10, 2),
                columns=["A", "C"],
            ),
        ],
        axis=1,
    )
    df.index = date_range("20130101 9:30", periods=10, freq="min")

    with ensure_clean_store(setup_path) as store:
        store.append("df", df)

        result = store.select("df")
        expected = df
        tm.assert_frame_equal(result, expected, by_blocks=True)

        result = store.select("df", columns=df.columns)
        expected = df
        tm.assert_frame_equal(result, expected, by_blocks=True)

        expected = df.loc[:, ["A"]]
        result = store.select("df", columns=["A"])
        tm.assert_frame_equal(result, expected, by_blocks=True)

        expected = df.loc[:, ["B", "A"]]
        result = store.select("df", columns=["B", "A"])
        tm.assert_frame_equal(result, expected, by_blocks=True)

    # duplicates on both index and columns
    with ensure_clean_store(setup_path) as store:
        store.append("df", df)
        store.append("df", df)

        expected = df.loc[:, ["B", "A"]]
        expected = concat([expected, expected])
        result = store.select("df", columns=["B", "A"])
        tm.assert_frame_equal(result, expected, by_blocks=True)


def test_select(setup_path):
    with ensure_clean_store(setup_path) as store:
        # select with columns=
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        _maybe_remove(store, "df")
        store.append("df", df)
        result = store.select("df", columns=["A", "B"])
        expected = df.reindex(columns=["A", "B"])
        tm.assert_frame_equal(expected, result)

        # equivalently
        result = store.select("df", [("columns=['A', 'B']")])
        expected = df.reindex(columns=["A", "B"])
        tm.assert_frame_equal(expected, result)

        # with a data column
        _maybe_remove(store, "df")
        store.append("df", df, data_columns=["A"])
        result = store.select("df", ["A > 0"], columns=["A", "B"])
        expected = df[df.A > 0].reindex(columns=["A", "B"])
        tm.assert_frame_equal(expected, result)

        # all a data columns
        _maybe_remove(store, "df")
        store.append("df", df, data_columns=True)
        result = store.select("df", ["A > 0"], columns=["A", "B"])
        expected = df[df.A > 0].reindex(columns=["A", "B"])
        tm.assert_frame_equal(expected, result)

        # with a data column, but different columns
        _maybe_remove(store, "df")
        store.append("df", df, data_columns=["A"])
        result = store.select("df", ["A > 0"], columns=["C", "D"])
        expected = df[df.A > 0].reindex(columns=["C", "D"])
        tm.assert_frame_equal(expected, result)


def test_select_dtypes(setup_path):
    with ensure_clean_store(setup_path) as store:
        # with a Timestamp data column (GH #2637)
        df = DataFrame(
            {
                "ts": bdate_range("2012-01-01", periods=300),
                "A": np.random.default_rng(2).standard_normal(300),
            }
        )
        _maybe_remove(store, "df")
        store.append("df", df, data_columns=["ts", "A"])

        result = store.select("df", "ts>=Timestamp('2012-02-01')")
        expected = df[df.ts >= Timestamp("2012-02-01")]
        tm.assert_frame_equal(expected, result)

        # bool columns (GH #2849)
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 2)), columns=["A", "B"]
        )
        df["object"] = "foo"
        df.loc[4:5, "object"] = "bar"
        df["boolv"] = df["A"] > 0
        _maybe_remove(store, "df")
        store.append("df", df, data_columns=True)

        expected = df[df.boolv == True].reindex(columns=["A", "boolv"])  # noqa: E712
        for v in [True, "true", 1]:
            result = store.select("df", f"boolv == {v}", columns=["A", "boolv"])
            tm.assert_frame_equal(expected, result)

        expected = df[df.boolv == False].reindex(columns=["A", "boolv"])  # noqa: E712
        for v in [False, "false", 0]:
            result = store.select("df", f"boolv == {v}", columns=["A", "boolv"])
            tm.assert_frame_equal(expected, result)

        # integer index
        df = DataFrame(
            {
                "A": np.random.default_rng(2).random(20),
                "B": np.random.default_rng(2).random(20),
            }
        )
        _maybe_remove(store, "df_int")
        store.append("df_int", df)
        result = store.select("df_int", "index<10 and columns=['A']")
        expected = df.reindex(index=list(df.index)[0:10], columns=["A"])
        tm.assert_frame_equal(expected, result)

        # float index
        df = DataFrame(
            {
                "A": np.random.default_rng(2).random(20),
                "B": np.random.default_rng(2).random(20),
                "index": np.arange(20, dtype="f8"),
            }
        )
        _maybe_remove(store, "df_float")
        store.append("df_float", df)
        result = store.select("df_float", "index<10.0 and columns=['A']")
        expected = df.reindex(index=list(df.index)[0:10], columns=["A"])
        tm.assert_frame_equal(expected, result)

    with ensure_clean_store(setup_path) as store:
        # floats w/o NaN
        df = DataFrame({"cols": range(11), "values": range(11)}, dtype="float64")
        df["cols"] = (df["cols"] + 10).apply(str)

        store.append("df1", df, data_columns=True)
        result = store.select("df1", where="values>2.0")
        expected = df[df["values"] > 2.0]
        tm.assert_frame_equal(expected, result)

        # floats with NaN
        df.iloc[0] = np.nan
        expected = df[df["values"] > 2.0]

        store.append("df2", df, data_columns=True, index=False)
        result = store.select("df2", where="values>2.0")
        tm.assert_frame_equal(expected, result)

        # https://github.com/PyTables/PyTables/issues/282
        # bug in selection when 0th row has a np.nan and an index
        # store.append('df3',df,data_columns=True)
        # result = store.select(
        #    'df3', where='values>2.0')
        # tm.assert_frame_equal(expected, result)

        # not in first position float with NaN ok too
        df = DataFrame({"cols": range(11), "values": range(11)}, dtype="float64")
        df["cols"] = (df["cols"] + 10).apply(str)

        df.iloc[1] = np.nan
        expected = df[df["values"] > 2.0]

        store.append("df4", df, data_columns=True)
        result = store.select("df4", where="values>2.0")
        tm.assert_frame_equal(expected, result)

    # test selection with comparison against numpy scalar
    # GH 11283
    with ensure_clean_store(setup_path) as store:
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=Index(list("ABCD")),
            index=Index([f"i-{i}" for i in range(30)]),
        )

        expected = df[df["A"] > 0]

        store.append("df", df, data_columns=True)
        np_zero = np.float64(0)  # noqa: F841
        result = store.select("df", where=["A>np_zero"])
        tm.assert_frame_equal(expected, result)


def test_select_with_many_inputs(setup_path):
    with ensure_clean_store(setup_path) as store:
        df = DataFrame(
            {
                "ts": bdate_range("2012-01-01", periods=300),
                "A": np.random.default_rng(2).standard_normal(300),
                "B": range(300),
                "users": ["a"] * 50
                + ["b"] * 50
                + ["c"] * 100
                + [f"a{i:03d}" for i in range(100)],
            }
        )
        _maybe_remove(store, "df")
        store.append("df", df, data_columns=["ts", "A", "B", "users"])

        # regular select
        result = store.select("df", "ts>=Timestamp('2012-02-01')")
        expected = df[df.ts >= Timestamp("2012-02-01")]
        tm.assert_frame_equal(expected, result)

        # small selector
        result = store.select("df", "ts>=Timestamp('2012-02-01') & users=['a','b','c']")
        expected = df[
            (df.ts >= Timestamp("2012-02-01")) & df.users.isin(["a", "b", "c"])
        ]
        tm.assert_frame_equal(expected, result)

        # big selector along the columns
        selector = ["a", "b", "c"] + [f"a{i:03d}" for i in range(60)]
        result = store.select("df", "ts>=Timestamp('2012-02-01') and users=selector")
        expected = df[(df.ts >= Timestamp("2012-02-01")) & df.users.isin(selector)]
        tm.assert_frame_equal(expected, result)

        selector = range(100, 200)
        result = store.select("df", "B=selector")
        expected = df[df.B.isin(selector)]
        tm.assert_frame_equal(expected, result)
        assert len(result) == 100

        # big selector along the index
        selector = Index(df.ts[0:100].values)
        result = store.select("df", "ts=selector")
        expected = df[df.ts.isin(selector.values)]
        tm.assert_frame_equal(expected, result)
        assert len(result) == 100


def test_select_iterator(tmp_path, setup_path):
    # single table
    with ensure_clean_store(setup_path) as store:
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        _maybe_remove(store, "df")
        store.append("df", df)

        expected = store.select("df")

        results = list(store.select("df", iterator=True))
        result = concat(results)
        tm.assert_frame_equal(expected, result)

        results = list(store.select("df", chunksize=2))
        assert len(results) == 5
        result = concat(results)
        tm.assert_frame_equal(expected, result)

        results = list(store.select("df", chunksize=2))
        result = concat(results)
        tm.assert_frame_equal(result, expected)

    path = tmp_path / setup_path

    df = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )
    df.to_hdf(path, key="df_non_table")

    msg = "can only use an iterator or chunksize on a table"
    with pytest.raises(TypeError, match=msg):
        read_hdf(path, "df_non_table", chunksize=2)

    with pytest.raises(TypeError, match=msg):
        read_hdf(path, "df_non_table", iterator=True)

    path = tmp_path / setup_path

    df = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )
    df.to_hdf(path, key="df", format="table")

    results = list(read_hdf(path, "df", chunksize=2))
    result = concat(results)

    assert len(results) == 5
    tm.assert_frame_equal(result, df)
    tm.assert_frame_equal(result, read_hdf(path, "df"))

    # multiple

    with ensure_clean_store(setup_path) as store:
        df1 = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        store.append("df1", df1, data_columns=True)
        df2 = df1.copy().rename(columns="{}_2".format)
        df2["foo"] = "bar"
        store.append("df2", df2)

        df = concat([df1, df2], axis=1)

        # full selection
        expected = store.select_as_multiple(["df1", "df2"], selector="df1")
        results = list(
            store.select_as_multiple(["df1", "df2"], selector="df1", chunksize=2)
        )
        result = concat(results)
        tm.assert_frame_equal(expected, result)


def test_select_iterator_complete_8014(setup_path):
    # GH 8014
    # using iterator and where clause
    chunksize = 1e4

    # no iterator
    with ensure_clean_store(setup_path) as store:
        expected = DataFrame(
            np.random.default_rng(2).standard_normal((100064, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=100064, freq="s"),
        )
        _maybe_remove(store, "df")
        store.append("df", expected)

        beg_dt = expected.index[0]
        end_dt = expected.index[-1]

        # select w/o iteration and no where clause works
        result = store.select("df")
        tm.assert_frame_equal(expected, result)

        # select w/o iterator and where clause, single term, begin
        # of range, works
        where = f"index >= '{beg_dt}'"
        result = store.select("df", where=where)
        tm.assert_frame_equal(expected, result)

        # select w/o iterator and where clause, single term, end
        # of range, works
        where = f"index <= '{end_dt}'"
        result = store.select("df", where=where)
        tm.assert_frame_equal(expected, result)

        # select w/o iterator and where clause, inclusive range,
        # works
        where = f"index >= '{beg_dt}' & index <= '{end_dt}'"
        result = store.select("df", where=where)
        tm.assert_frame_equal(expected, result)

    # with iterator, full range
    with ensure_clean_store(setup_path) as store:
        expected = DataFrame(
            np.random.default_rng(2).standard_normal((100064, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=100064, freq="s"),
        )
        _maybe_remove(store, "df")
        store.append("df", expected)

        beg_dt = expected.index[0]
        end_dt = expected.index[-1]

        # select w/iterator and no where clause works
        results = list(store.select("df", chunksize=chunksize))
        result = concat(results)
        tm.assert_frame_equal(expected, result)

        # select w/iterator and where clause, single term, begin of range
        where = f"index >= '{beg_dt}'"
        results = list(store.select("df", where=where, chunksize=chunksize))
        result = concat(results)
        tm.assert_frame_equal(expected, result)

        # select w/iterator and where clause, single term, end of range
        where = f"index <= '{end_dt}'"
        results = list(store.select("df", where=where, chunksize=chunksize))
        result = concat(results)
        tm.assert_frame_equal(expected, result)

        # select w/iterator and where clause, inclusive range
        where = f"index >= '{beg_dt}' & index <= '{end_dt}'"
        results = list(store.select("df", where=where, chunksize=chunksize))
        result = concat(results)
        tm.assert_frame_equal(expected, result)


def test_select_iterator_non_complete_8014(setup_path):
    # GH 8014
    # using iterator and where clause
    chunksize = 1e4

    # with iterator, non complete range
    with ensure_clean_store(setup_path) as store:
        expected = DataFrame(
            np.random.default_rng(2).standard_normal((100064, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=100064, freq="s"),
        )
        _maybe_remove(store, "df")
        store.append("df", expected)

        beg_dt = expected.index[1]
        end_dt = expected.index[-2]

        # select w/iterator and where clause, single term, begin of range
        where = f"index >= '{beg_dt}'"
        results = list(store.select("df", where=where, chunksize=chunksize))
        result = concat(results)
        rexpected = expected[expected.index >= beg_dt]
        tm.assert_frame_equal(rexpected, result)

        # select w/iterator and where clause, single term, end of range
        where = f"index <= '{end_dt}'"
        results = list(store.select("df", where=where, chunksize=chunksize))
        result = concat(results)
        rexpected = expected[expected.index <= end_dt]
        tm.assert_frame_equal(rexpected, result)

        # select w/iterator and where clause, inclusive range
        where = f"index >= '{beg_dt}' & index <= '{end_dt}'"
        results = list(store.select("df", where=where, chunksize=chunksize))
        result = concat(results)
        rexpected = expected[(expected.index >= beg_dt) & (expected.index <= end_dt)]
        tm.assert_frame_equal(rexpected, result)

    # with iterator, empty where
    with ensure_clean_store(setup_path) as store:
        expected = DataFrame(
            np.random.default_rng(2).standard_normal((100064, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=100064, freq="s"),
        )
        _maybe_remove(store, "df")
        store.append("df", expected)

        end_dt = expected.index[-1]

        # select w/iterator and where clause, single term, begin of range
        where = f"index > '{end_dt}'"
        results = list(store.select("df", where=where, chunksize=chunksize))
        assert 0 == len(results)


def test_select_iterator_many_empty_frames(setup_path):
    # GH 8014
    # using iterator and where clause can return many empty
    # frames.
    chunksize = 10_000

    # with iterator, range limited to the first chunk
    with ensure_clean_store(setup_path) as store:
        expected = DataFrame(
            np.random.default_rng(2).standard_normal((100064, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=100064, freq="s"),
        )
        _maybe_remove(store, "df")
        store.append("df", expected)

        beg_dt = expected.index[0]
        end_dt = expected.index[chunksize - 1]

        # select w/iterator and where clause, single term, begin of range
        where = f"index >= '{beg_dt}'"
        results = list(store.select("df", where=where, chunksize=chunksize))
        result = concat(results)
        rexpected = expected[expected.index >= beg_dt]
        tm.assert_frame_equal(rexpected, result)

        # select w/iterator and where clause, single term, end of range
        where = f"index <= '{end_dt}'"
        results = list(store.select("df", where=where, chunksize=chunksize))

        assert len(results) == 1
        result = concat(results)
        rexpected = expected[expected.index <= end_dt]
        tm.assert_frame_equal(rexpected, result)

        # select w/iterator and where clause, inclusive range
        where = f"index >= '{beg_dt}' & index <= '{end_dt}'"
        results = list(store.select("df", where=where, chunksize=chunksize))

        # should be 1, is 10
        assert len(results) == 1
        result = concat(results)
        rexpected = expected[(expected.index >= beg_dt) & (expected.index <= end_dt)]
        tm.assert_frame_equal(rexpected, result)

        # select w/iterator and where clause which selects
        # *nothing*.
        #
        # To be consistent with Python idiom I suggest this should
        # return [] e.g. `for e in []: print True` never prints
        # True.

        where = f"index <= '{beg_dt}' & index >= '{end_dt}'"
        results = list(store.select("df", where=where, chunksize=chunksize))

        # should be []
        assert len(results) == 0


def test_frame_select(setup_path):
    df = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )

    with ensure_clean_store(setup_path) as store:
        store.put("frame", df, format="table")
        date = df.index[len(df) // 2]

        crit1 = Term("index>=date")
        assert crit1.env.scope["date"] == date

        crit2 = "columns=['A', 'D']"
        crit3 = "columns=A"

        result = store.select("frame", [crit1, crit2])
        expected = df.loc[date:, ["A", "D"]]
        tm.assert_frame_equal(result, expected)

        result = store.select("frame", [crit3])
        expected = df.loc[:, ["A"]]
        tm.assert_frame_equal(result, expected)

        # invalid terms
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        store.append("df_time", df)
        msg = "day is out of range for month: 0"
        with pytest.raises(ValueError, match=msg):
            store.select("df_time", "index>0")

        # can't select if not written as table
        # store['frame'] = df
        # with pytest.raises(ValueError):
        #     store.select('frame', [crit1, crit2])


def test_frame_select_complex(setup_path):
    # select via complex criteria

    df = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )
    df["string"] = "foo"
    df.loc[df.index[0:4], "string"] = "bar"

    with ensure_clean_store(setup_path) as store:
        store.put("df", df, format="table", data_columns=["string"])

        # empty
        result = store.select("df", 'index>df.index[3] & string="bar"')
        expected = df.loc[(df.index > df.index[3]) & (df.string == "bar")]
        tm.assert_frame_equal(result, expected)

        result = store.select("df", 'index>df.index[3] & string="foo"')
        expected = df.loc[(df.index > df.index[3]) & (df.string == "foo")]
        tm.assert_frame_equal(result, expected)

        # or
        result = store.select("df", 'index>df.index[3] | string="bar"')
        expected = df.loc[(df.index > df.index[3]) | (df.string == "bar")]
        tm.assert_frame_equal(result, expected)

        result = store.select(
            "df", '(index>df.index[3] & index<=df.index[6]) | string="bar"'
        )
        expected = df.loc[
            ((df.index > df.index[3]) & (df.index <= df.index[6]))
            | (df.string == "bar")
        ]
        tm.assert_frame_equal(result, expected)

        # invert
        result = store.select("df", 'string!="bar"')
        expected = df.loc[df.string != "bar"]
        tm.assert_frame_equal(result, expected)

        # invert not implemented in numexpr :(
        msg = "cannot use an invert condition when passing to numexpr"
        with pytest.raises(NotImplementedError, match=msg):
            store.select("df", '~(string="bar")')

        # invert ok for filters
        result = store.select("df", "~(columns=['A','B'])")
        expected = df.loc[:, df.columns.difference(["A", "B"])]
        tm.assert_frame_equal(result, expected)

        # in
        result = store.select("df", "index>df.index[3] & columns in ['A','B']")
        expected = df.loc[df.index > df.index[3]].reindex(columns=["A", "B"])
        tm.assert_frame_equal(result, expected)


def test_frame_select_complex2(tmp_path):
    pp = tmp_path / "params.hdf"
    hh = tmp_path / "hist.hdf"

    # use non-trivial selection criteria
    params = DataFrame({"A": [1, 1, 2, 2, 3]})
    params.to_hdf(pp, key="df", mode="w", format="table", data_columns=["A"])

    selection = read_hdf(pp, "df", where="A=[2,3]")
    hist = DataFrame(
        np.random.default_rng(2).standard_normal((25, 1)),
        columns=["data"],
        index=MultiIndex.from_tuples(
            [(i, j) for i in range(5) for j in range(5)], names=["l1", "l2"]
        ),
    )

    hist.to_hdf(hh, key="df", mode="w", format="table")

    expected = read_hdf(hh, "df", where="l1=[2, 3, 4]")

    # scope with list like
    l0 = selection.index.tolist()  # noqa: F841
    with HDFStore(hh) as store:
        result = store.select("df", where="l1=l0")
        tm.assert_frame_equal(result, expected)

    result = read_hdf(hh, "df", where="l1=l0")
    tm.assert_frame_equal(result, expected)

    # index
    index = selection.index  # noqa: F841
    result = read_hdf(hh, "df", where="l1=index")
    tm.assert_frame_equal(result, expected)

    result = read_hdf(hh, "df", where="l1=selection.index")
    tm.assert_frame_equal(result, expected)

    result = read_hdf(hh, "df", where="l1=selection.index.tolist()")
    tm.assert_frame_equal(result, expected)

    result = read_hdf(hh, "df", where="l1=list(selection.index)")
    tm.assert_frame_equal(result, expected)

    # scope with index
    with HDFStore(hh) as store:
        result = store.select("df", where="l1=index")
        tm.assert_frame_equal(result, expected)

        result = store.select("df", where="l1=selection.index")
        tm.assert_frame_equal(result, expected)

        result = store.select("df", where="l1=selection.index.tolist()")
        tm.assert_frame_equal(result, expected)

        result = store.select("df", where="l1=list(selection.index)")
        tm.assert_frame_equal(result, expected)


def test_invalid_filtering(setup_path):
    # can't use more than one filter (atm)

    df = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )

    with ensure_clean_store(setup_path) as store:
        store.put("df", df, format="table")

        msg = "unable to collapse Joint Filters"
        # not implemented
        with pytest.raises(NotImplementedError, match=msg):
            store.select("df", "columns=['A'] | columns=['B']")

        # in theory we could deal with this
        with pytest.raises(NotImplementedError, match=msg):
            store.select("df", "columns=['A','B'] & columns=['C']")


def test_string_select(setup_path):
    # GH 2973
    with ensure_clean_store(setup_path) as store:
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )

        # test string ==/!=
        df["x"] = "none"
        df.loc[df.index[2:7], "x"] = ""

        store.append("df", df, data_columns=["x"])

        result = store.select("df", "x=none")
        expected = df[df.x == "none"]
        tm.assert_frame_equal(result, expected)

        result = store.select("df", "x!=none")
        expected = df[df.x != "none"]
        tm.assert_frame_equal(result, expected)

        df2 = df.copy()
        df2.loc[df2.x == "", "x"] = np.nan

        store.append("df2", df2, data_columns=["x"])
        result = store.select("df2", "x!=none")
        expected = df2[isna(df2.x)]
        tm.assert_frame_equal(result, expected)

        # int ==/!=
        df["int"] = 1
        df.loc[df.index[2:7], "int"] = 2

        store.append("df3", df, data_columns=["int"])

        result = store.select("df3", "int=2")
        expected = df[df.int == 2]
        tm.assert_frame_equal(result, expected)

        result = store.select("df3", "int!=2")
        expected = df[df.int != 2]
        tm.assert_frame_equal(result, expected)


def test_select_as_multiple(setup_path):
    df1 = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )
    df2 = df1.copy().rename(columns="{}_2".format)
    df2["foo"] = "bar"

    with ensure_clean_store(setup_path) as store:
        msg = "keys must be a list/tuple"
        # no tables stored
        with pytest.raises(TypeError, match=msg):
            store.select_as_multiple(None, where=["A>0", "B>0"], selector="df1")

        store.append("df1", df1, data_columns=["A", "B"])
        store.append("df2", df2)

        # exceptions
        with pytest.raises(TypeError, match=msg):
            store.select_as_multiple(None, where=["A>0", "B>0"], selector="df1")

        with pytest.raises(TypeError, match=msg):
            store.select_as_multiple([None], where=["A>0", "B>0"], selector="df1")

        msg = "'No object named df3 in the file'"
        with pytest.raises(KeyError, match=msg):
            store.select_as_multiple(
                ["df1", "df3"], where=["A>0", "B>0"], selector="df1"
            )

        with pytest.raises(KeyError, match=msg):
            store.select_as_multiple(["df3"], where=["A>0", "B>0"], selector="df1")

        with pytest.raises(KeyError, match="'No object named df4 in the file'"):
            store.select_as_multiple(
                ["df1", "df2"], where=["A>0", "B>0"], selector="df4"
            )

        # default select
        result = store.select("df1", ["A>0", "B>0"])
        expected = store.select_as_multiple(
            ["df1"], where=["A>0", "B>0"], selector="df1"
        )
        tm.assert_frame_equal(result, expected)
        expected = store.select_as_multiple("df1", where=["A>0", "B>0"], selector="df1")
        tm.assert_frame_equal(result, expected)

        # multiple
        result = store.select_as_multiple(
            ["df1", "df2"], where=["A>0", "B>0"], selector="df1"
        )
        expected = concat([df1, df2], axis=1)
        expected = expected[(expected.A > 0) & (expected.B > 0)]
        tm.assert_frame_equal(result, expected, check_freq=False)
        # FIXME: 2021-01-20 this is failing with freq None vs 4B on some builds

        # multiple (diff selector)
        result = store.select_as_multiple(
            ["df1", "df2"], where="index>df2.index[4]", selector="df2"
        )
        expected = concat([df1, df2], axis=1)
        expected = expected[5:]
        tm.assert_frame_equal(result, expected)

        # test exception for diff rows
        df3 = df1.copy().head(2)
        store.append("df3", df3)
        msg = "all tables must have exactly the same nrows!"
        with pytest.raises(ValueError, match=msg):
            store.select_as_multiple(
                ["df1", "df3"], where=["A>0", "B>0"], selector="df1"
            )


def test_nan_selection_bug_4858(setup_path):
    with ensure_clean_store(setup_path) as store:
        df = DataFrame({"cols": range(6), "values": range(6)}, dtype="float64")
        df["cols"] = (df["cols"] + 10).apply(str)
        df.iloc[0] = np.nan

        expected = DataFrame(
            {"cols": ["13.0", "14.0", "15.0"], "values": [3.0, 4.0, 5.0]},
            index=[3, 4, 5],
        )

        # write w/o the index on that particular column
        store.append("df", df, data_columns=True, index=["cols"])
        result = store.select("df", where="values>2.0")
        tm.assert_frame_equal(result, expected)


def test_query_with_nested_special_character(setup_path):
    df = DataFrame(
        {
            "a": ["a", "a", "c", "b", "test & test", "c", "b", "e"],
            "b": [1, 2, 3, 4, 5, 6, 7, 8],
        }
    )
    expected = df[df.a == "test & test"]
    with ensure_clean_store(setup_path) as store:
        store.append("test", df, format="table", data_columns=True)
        result = store.select("test", 'a = "test & test"')
    tm.assert_frame_equal(expected, result)


def test_query_long_float_literal(setup_path):
    # GH 14241
    df = DataFrame({"A": [1000000000.0009, 1000000000.0011, 1000000000.0015]})

    with ensure_clean_store(setup_path) as store:
        store.append("test", df, format="table", data_columns=True)

        cutoff = 1000000000.0006
        result = store.select("test", f"A < {cutoff:.4f}")
        assert result.empty

        cutoff = 1000000000.0010
        result = store.select("test", f"A > {cutoff:.4f}")
        expected = df.loc[[1, 2], :]
        tm.assert_frame_equal(expected, result)

        exact = 1000000000.0011
        result = store.select("test", f"A == {exact:.4f}")
        expected = df.loc[[1], :]
        tm.assert_frame_equal(expected, result)


def test_query_compare_column_type(setup_path):
    # GH 15492
    df = DataFrame(
        {
            "date": ["2014-01-01", "2014-01-02"],
            "real_date": date_range("2014-01-01", periods=2),
            "float": [1.1, 1.2],
            "int": [1, 2],
        },
        columns=["date", "real_date", "float", "int"],
    )

    with ensure_clean_store(setup_path) as store:
        store.append("test", df, format="table", data_columns=True)

        ts = Timestamp("2014-01-01")  # noqa: F841
        result = store.select("test", where="real_date > ts")
        expected = df.loc[[1], :]
        tm.assert_frame_equal(expected, result)

        for op in ["<", ">", "=="]:
            # non strings to string column always fail
            for v in [2.1, True, Timestamp("2014-01-01"), pd.Timedelta(1, "s")]:
                query = f"date {op} v"
                msg = f"Cannot compare {v} of type {type(v)} to string column"
                with pytest.raises(TypeError, match=msg):
                    store.select("test", where=query)

            # strings to other columns must be convertible to type
            v = "a"
            for col in ["int", "float", "real_date"]:
                query = f"{col} {op} v"
                if col == "real_date":
                    msg = 'Given date string "a" not likely a datetime'
                else:
                    msg = "could not convert string to"
                with pytest.raises(ValueError, match=msg):
                    store.select("test", where=query)

            for v, col in zip(
                ["1", "1.1", "2014-01-01"], ["int", "float", "real_date"]
            ):
                query = f"{col} {op} v"
                result = store.select("test", where=query)

                if op == "==":
                    expected = df.loc[[0], :]
                elif op == ">":
                    expected = df.loc[[1], :]
                else:
                    expected = df.loc[[], :]
                tm.assert_frame_equal(expected, result)


@pytest.mark.parametrize("where", ["", (), (None,), [], [None]])
def test_select_empty_where(tmp_path, where):
    # GH26610

    df = DataFrame([1, 2, 3])
    path = tmp_path / "empty_where.h5"
    with HDFStore(path) as store:
        store.put("df", df, "t")
        result = read_hdf(store, "df", where=where)
        tm.assert_frame_equal(result, df)


def test_select_large_integer(tmp_path):
    path = tmp_path / "large_int.h5"

    df = DataFrame(
        zip(
            ["a", "b", "c", "d"],
            [-9223372036854775801, -9223372036854775802, -9223372036854775803, 123],
        ),
        columns=["x", "y"],
    )
    with HDFStore(path) as s:
        s.append("data", df, data_columns=True, index=False)
        result = s.select("data", where="y==-9223372036854775801").get("y").get(0)
    expected = df["y"][0]

    assert expected == result
