import datetime
from datetime import timedelta
import re

import numpy as np
import pytest

from pandas._libs.tslibs import Timestamp
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    Series,
    _testing as tm,
    concat,
    date_range,
    read_hdf,
)
from pandas.tests.io.pytables.common import (
    _maybe_remove,
    ensure_clean_store,
)

pytestmark = [pytest.mark.single_cpu]

tables = pytest.importorskip("tables")


@pytest.mark.filterwarnings("ignore::tables.NaturalNameWarning")
def test_append(setup_path):
    with ensure_clean_store(setup_path) as store:
        # this is allowed by almost always don't want to do it
        # tables.NaturalNameWarning):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((20, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=20, freq="B"),
        )
        _maybe_remove(store, "df1")
        store.append("df1", df[:10])
        store.append("df1", df[10:])
        tm.assert_frame_equal(store["df1"], df)

        _maybe_remove(store, "df2")
        store.put("df2", df[:10], format="table")
        store.append("df2", df[10:])
        tm.assert_frame_equal(store["df2"], df)

        _maybe_remove(store, "df3")
        store.append("/df3", df[:10])
        store.append("/df3", df[10:])
        tm.assert_frame_equal(store["df3"], df)

        # this is allowed by almost always don't want to do it
        # tables.NaturalNameWarning
        _maybe_remove(store, "/df3 foo")
        store.append("/df3 foo", df[:10])
        store.append("/df3 foo", df[10:])
        tm.assert_frame_equal(store["df3 foo"], df)

        # dtype issues - mizxed type in a single object column
        df = DataFrame(data=[[1, 2], [0, 1], [1, 2], [0, 0]])
        df["mixed_column"] = "testing"
        df.loc[2, "mixed_column"] = np.nan
        _maybe_remove(store, "df")
        store.append("df", df)
        tm.assert_frame_equal(store["df"], df)

        # uints - test storage of uints
        uint_data = DataFrame(
            {
                "u08": Series(
                    np.random.default_rng(2).integers(0, high=255, size=5),
                    dtype=np.uint8,
                ),
                "u16": Series(
                    np.random.default_rng(2).integers(0, high=65535, size=5),
                    dtype=np.uint16,
                ),
                "u32": Series(
                    np.random.default_rng(2).integers(0, high=2**30, size=5),
                    dtype=np.uint32,
                ),
                "u64": Series(
                    [2**58, 2**59, 2**60, 2**61, 2**62],
                    dtype=np.uint64,
                ),
            },
            index=np.arange(5),
        )
        _maybe_remove(store, "uints")
        store.append("uints", uint_data)
        tm.assert_frame_equal(store["uints"], uint_data, check_index_type=True)

        # uints - test storage of uints in indexable columns
        _maybe_remove(store, "uints")
        # 64-bit indices not yet supported
        store.append("uints", uint_data, data_columns=["u08", "u16", "u32"])
        tm.assert_frame_equal(store["uints"], uint_data, check_index_type=True)


def test_append_series(setup_path):
    with ensure_clean_store(setup_path) as store:
        # basic
        ss = Series(range(20), dtype=np.float64, index=[f"i_{i}" for i in range(20)])
        ts = Series(
            np.arange(10, dtype=np.float64), index=date_range("2020-01-01", periods=10)
        )
        ns = Series(np.arange(100))

        store.append("ss", ss)
        result = store["ss"]
        tm.assert_series_equal(result, ss)
        assert result.name is None

        store.append("ts", ts)
        result = store["ts"]
        tm.assert_series_equal(result, ts)
        assert result.name is None

        ns.name = "foo"
        store.append("ns", ns)
        result = store["ns"]
        tm.assert_series_equal(result, ns)
        assert result.name == ns.name

        # select on the values
        expected = ns[ns > 60]
        result = store.select("ns", "foo>60")
        tm.assert_series_equal(result, expected)

        # select on the index and values
        expected = ns[(ns > 70) & (ns.index < 90)]
        result = store.select("ns", "foo>70 and index<90")
        tm.assert_series_equal(result, expected, check_index_type=True)

        # multi-index
        mi = DataFrame(np.random.default_rng(2).standard_normal((5, 1)), columns=["A"])
        mi["B"] = np.arange(len(mi))
        mi["C"] = "foo"
        mi.loc[3:5, "C"] = "bar"
        mi.set_index(["C", "B"], inplace=True)
        s = mi.stack(future_stack=True)
        s.index = s.index.droplevel(2)
        store.append("mi", s)
        tm.assert_series_equal(store["mi"], s, check_index_type=True)


def test_append_some_nans(setup_path):
    with ensure_clean_store(setup_path) as store:
        df = DataFrame(
            {
                "A": Series(np.random.default_rng(2).standard_normal(20)).astype(
                    "int32"
                ),
                "A1": np.random.default_rng(2).standard_normal(20),
                "A2": np.random.default_rng(2).standard_normal(20),
                "B": "foo",
                "C": "bar",
                "D": Timestamp("2001-01-01").as_unit("ns"),
                "E": Timestamp("2001-01-02").as_unit("ns"),
            },
            index=np.arange(20),
        )
        # some nans
        _maybe_remove(store, "df1")
        df.loc[0:15, ["A1", "B", "D", "E"]] = np.nan
        store.append("df1", df[:10])
        store.append("df1", df[10:])
        tm.assert_frame_equal(store["df1"], df, check_index_type=True)

        # first column
        df1 = df.copy()
        df1["A1"] = np.nan
        _maybe_remove(store, "df1")
        store.append("df1", df1[:10])
        store.append("df1", df1[10:])
        tm.assert_frame_equal(store["df1"], df1, check_index_type=True)

        # 2nd column
        df2 = df.copy()
        df2["A2"] = np.nan
        _maybe_remove(store, "df2")
        store.append("df2", df2[:10])
        store.append("df2", df2[10:])
        tm.assert_frame_equal(store["df2"], df2, check_index_type=True)

        # datetimes
        df3 = df.copy()
        df3["E"] = np.nan
        _maybe_remove(store, "df3")
        store.append("df3", df3[:10])
        store.append("df3", df3[10:])
        tm.assert_frame_equal(store["df3"], df3, check_index_type=True)


def test_append_all_nans(setup_path, using_infer_string):
    with ensure_clean_store(setup_path) as store:
        df = DataFrame(
            {
                "A1": np.random.default_rng(2).standard_normal(20),
                "A2": np.random.default_rng(2).standard_normal(20),
            },
            index=np.arange(20),
        )
        df.loc[0:15, :] = np.nan

        # nan some entire rows (dropna=True)
        _maybe_remove(store, "df")
        store.append("df", df[:10], dropna=True)
        store.append("df", df[10:], dropna=True)
        tm.assert_frame_equal(store["df"], df[-4:], check_index_type=True)

        # nan some entire rows (dropna=False)
        _maybe_remove(store, "df2")
        store.append("df2", df[:10], dropna=False)
        store.append("df2", df[10:], dropna=False)
        tm.assert_frame_equal(store["df2"], df, check_index_type=True)

        # tests the option io.hdf.dropna_table
        with pd.option_context("io.hdf.dropna_table", False):
            _maybe_remove(store, "df3")
            store.append("df3", df[:10])
            store.append("df3", df[10:])
            tm.assert_frame_equal(store["df3"], df)

        with pd.option_context("io.hdf.dropna_table", True):
            _maybe_remove(store, "df4")
            store.append("df4", df[:10])
            store.append("df4", df[10:])
            tm.assert_frame_equal(store["df4"], df[-4:])

            # nan some entire rows (string are still written!)
            df = DataFrame(
                {
                    "A1": np.random.default_rng(2).standard_normal(20),
                    "A2": np.random.default_rng(2).standard_normal(20),
                    "B": "foo",
                    "C": "bar",
                },
                index=np.arange(20),
            )

            df.loc[0:15, :] = np.nan

            _maybe_remove(store, "df")
            store.append("df", df[:10], dropna=True)
            store.append("df", df[10:], dropna=True)
            result = store["df"]
            expected = df
            if using_infer_string:
                # TODO: Test is incorrect when not using_infer_string.
                #       Should take the last 4 rows uncondiationally.
                expected = expected[-4:]
            tm.assert_frame_equal(result, expected, check_index_type=True)

            _maybe_remove(store, "df2")
            store.append("df2", df[:10], dropna=False)
            store.append("df2", df[10:], dropna=False)
            tm.assert_frame_equal(store["df2"], df, check_index_type=True)

            # nan some entire rows (but since we have dates they are still
            # written!)
            df = DataFrame(
                {
                    "A1": np.random.default_rng(2).standard_normal(20),
                    "A2": np.random.default_rng(2).standard_normal(20),
                    "B": "foo",
                    "C": "bar",
                    "D": Timestamp("2001-01-01").as_unit("ns"),
                    "E": Timestamp("2001-01-02").as_unit("ns"),
                },
                index=np.arange(20),
            )

            df.loc[0:15, :] = np.nan

            _maybe_remove(store, "df")
            store.append("df", df[:10], dropna=True)
            store.append("df", df[10:], dropna=True)
            tm.assert_frame_equal(store["df"], df, check_index_type=True)

            _maybe_remove(store, "df2")
            store.append("df2", df[:10], dropna=False)
            store.append("df2", df[10:], dropna=False)
            tm.assert_frame_equal(store["df2"], df, check_index_type=True)


def test_append_frame_column_oriented(setup_path):
    with ensure_clean_store(setup_path) as store:
        # column oriented
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        df.index = df.index._with_freq(None)  # freq doesn't round-trip

        _maybe_remove(store, "df1")
        store.append("df1", df.iloc[:, :2], axes=["columns"])
        store.append("df1", df.iloc[:, 2:])
        tm.assert_frame_equal(store["df1"], df)

        result = store.select("df1", "columns=A")
        expected = df.reindex(columns=["A"])
        tm.assert_frame_equal(expected, result)

        # selection on the non-indexable
        result = store.select("df1", ("columns=A", "index=df.index[0:4]"))
        expected = df.reindex(columns=["A"], index=df.index[0:4])
        tm.assert_frame_equal(expected, result)

        # this isn't supported
        msg = re.escape(
            "passing a filterable condition to a non-table indexer "
            "[Filter: Not Initialized]"
        )
        with pytest.raises(TypeError, match=msg):
            store.select("df1", "columns=A and index>df.index[4]")


def test_append_with_different_block_ordering(setup_path):
    # GH 4096; using same frames, but different block orderings
    with ensure_clean_store(setup_path) as store:
        for i in range(10):
            df = DataFrame(
                np.random.default_rng(2).standard_normal((10, 2)), columns=list("AB")
            )
            df["index"] = range(10)
            df["index"] += i * 10
            df["int64"] = Series([1] * len(df), dtype="int64")
            df["int16"] = Series([1] * len(df), dtype="int16")

            if i % 2 == 0:
                del df["int64"]
                df["int64"] = Series([1] * len(df), dtype="int64")
            if i % 3 == 0:
                a = df.pop("A")
                df["A"] = a

            df.set_index("index", inplace=True)

            store.append("df", df)

    # test a different ordering but with more fields (like invalid
    # combinations)
    with ensure_clean_store(setup_path) as store:
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 2)),
            columns=list("AB"),
            dtype="float64",
        )
        df["int64"] = Series([1] * len(df), dtype="int64")
        df["int16"] = Series([1] * len(df), dtype="int16")
        store.append("df", df)

        # store additional fields in different blocks
        df["int16_2"] = Series([1] * len(df), dtype="int16")
        msg = re.escape(
            "cannot match existing table structure for [int16] on appending data"
        )
        with pytest.raises(ValueError, match=msg):
            store.append("df", df)

        # store multiple additional fields in different blocks
        df["float_3"] = Series([1.0] * len(df), dtype="float64")
        msg = re.escape(
            "cannot match existing table structure for [A,B] on appending data"
        )
        with pytest.raises(ValueError, match=msg):
            store.append("df", df)


def test_append_with_strings(setup_path):
    with ensure_clean_store(setup_path) as store:

        def check_col(key, name, size):
            assert (
                getattr(store.get_storer(key).table.description, name).itemsize == size
            )

        # avoid truncation on elements
        df = DataFrame([[123, "asdqwerty"], [345, "dggnhebbsdfbdfb"]])
        store.append("df_big", df)
        tm.assert_frame_equal(store.select("df_big"), df)
        check_col("df_big", "values_block_1", 15)

        # appending smaller string ok
        df2 = DataFrame([[124, "asdqy"], [346, "dggnhefbdfb"]])
        store.append("df_big", df2)
        expected = concat([df, df2])
        tm.assert_frame_equal(store.select("df_big"), expected)
        check_col("df_big", "values_block_1", 15)

        # avoid truncation on elements
        df = DataFrame([[123, "asdqwerty"], [345, "dggnhebbsdfbdfb"]])
        store.append("df_big2", df, min_itemsize={"values": 50})
        tm.assert_frame_equal(store.select("df_big2"), df)
        check_col("df_big2", "values_block_1", 50)

        # bigger string on next append
        store.append("df_new", df)
        df_new = DataFrame([[124, "abcdefqhij"], [346, "abcdefghijklmnopqrtsuvwxyz"]])
        msg = (
            r"Trying to store a string with len \[26\] in "
            r"\[values_block_1\] column but\n"
            r"this column has a limit of \[15\]!\n"
            "Consider using min_itemsize to preset the sizes on these "
            "columns"
        )
        with pytest.raises(ValueError, match=msg):
            store.append("df_new", df_new)

        # min_itemsize on Series index (GH 11412)
        df = DataFrame(
            {
                "A": [0.0, 1.0, 2.0, 3.0, 4.0],
                "B": [0.0, 1.0, 0.0, 1.0, 0.0],
                "C": Index(["foo1", "foo2", "foo3", "foo4", "foo5"]),
                "D": date_range("20130101", periods=5),
            }
        ).set_index("C")
        store.append("ss", df["B"], min_itemsize={"index": 4})
        tm.assert_series_equal(store.select("ss"), df["B"])

        # same as above, with data_columns=True
        store.append("ss2", df["B"], data_columns=True, min_itemsize={"index": 4})
        tm.assert_series_equal(store.select("ss2"), df["B"])

        # min_itemsize in index without appending (GH 10381)
        store.put("ss3", df, format="table", min_itemsize={"index": 6})
        # just make sure there is a longer string:
        df2 = df.copy().reset_index().assign(C="longer").set_index("C")
        store.append("ss3", df2)
        tm.assert_frame_equal(store.select("ss3"), concat([df, df2]))

        # same as above, with a Series
        store.put("ss4", df["B"], format="table", min_itemsize={"index": 6})
        store.append("ss4", df2["B"])
        tm.assert_series_equal(store.select("ss4"), concat([df["B"], df2["B"]]))

        # with nans
        _maybe_remove(store, "df")
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        df["string"] = "foo"
        df.loc[df.index[1:4], "string"] = np.nan
        df["string2"] = "bar"
        df.loc[df.index[4:8], "string2"] = np.nan
        df["string3"] = "bah"
        df.loc[df.index[1:], "string3"] = np.nan
        store.append("df", df)
        result = store.select("df")
        tm.assert_frame_equal(result, df)

    with ensure_clean_store(setup_path) as store:
        df = DataFrame({"A": "foo", "B": "bar"}, index=range(10))

        # a min_itemsize that creates a data_column
        _maybe_remove(store, "df")
        store.append("df", df, min_itemsize={"A": 200})
        check_col("df", "A", 200)
        assert store.get_storer("df").data_columns == ["A"]

        # a min_itemsize that creates a data_column2
        _maybe_remove(store, "df")
        store.append("df", df, data_columns=["B"], min_itemsize={"A": 200})
        check_col("df", "A", 200)
        assert store.get_storer("df").data_columns == ["B", "A"]

        # a min_itemsize that creates a data_column2
        _maybe_remove(store, "df")
        store.append("df", df, data_columns=["B"], min_itemsize={"values": 200})
        check_col("df", "B", 200)
        check_col("df", "values_block_0", 200)
        assert store.get_storer("df").data_columns == ["B"]

        # infer the .typ on subsequent appends
        _maybe_remove(store, "df")
        store.append("df", df[:5], min_itemsize=200)
        store.append("df", df[5:], min_itemsize=200)
        tm.assert_frame_equal(store["df"], df)

        # invalid min_itemsize keys
        df = DataFrame(["foo", "foo", "foo", "barh", "barh", "barh"], columns=["A"])
        _maybe_remove(store, "df")
        msg = re.escape(
            "min_itemsize has the key [foo] which is not an axis or data_column"
        )
        with pytest.raises(ValueError, match=msg):
            store.append("df", df, min_itemsize={"foo": 20, "foobar": 20})


def test_append_with_empty_string(setup_path):
    with ensure_clean_store(setup_path) as store:
        # with all empty strings (GH 12242)
        df = DataFrame({"x": ["a", "b", "c", "d", "e", "f", ""]})
        store.append("df", df[:-1], min_itemsize={"x": 1})
        store.append("df", df[-1:], min_itemsize={"x": 1})
        tm.assert_frame_equal(store.select("df"), df)


def test_append_with_data_columns(setup_path):
    with ensure_clean_store(setup_path) as store:
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        df.iloc[0, df.columns.get_loc("B")] = 1.0
        _maybe_remove(store, "df")
        store.append("df", df[:2], data_columns=["B"])
        store.append("df", df[2:])
        tm.assert_frame_equal(store["df"], df)

        # check that we have indices created
        assert store._handle.root.df.table.cols.index.is_indexed is True
        assert store._handle.root.df.table.cols.B.is_indexed is True

        # data column searching
        result = store.select("df", "B>0")
        expected = df[df.B > 0]
        tm.assert_frame_equal(result, expected)

        # data column searching (with an indexable and a data_columns)
        result = store.select("df", "B>0 and index>df.index[3]")
        df_new = df.reindex(index=df.index[4:])
        expected = df_new[df_new.B > 0]
        tm.assert_frame_equal(result, expected)

        # data column selection with a string data_column
        df_new = df.copy()
        df_new["string"] = "foo"
        df_new.loc[df_new.index[1:4], "string"] = np.nan
        df_new.loc[df_new.index[5:6], "string"] = "bar"
        _maybe_remove(store, "df")
        store.append("df", df_new, data_columns=["string"])
        result = store.select("df", "string='foo'")
        expected = df_new[df_new.string == "foo"]
        tm.assert_frame_equal(result, expected)

        # using min_itemsize and a data column
        def check_col(key, name, size):
            assert (
                getattr(store.get_storer(key).table.description, name).itemsize == size
            )

    with ensure_clean_store(setup_path) as store:
        _maybe_remove(store, "df")
        store.append("df", df_new, data_columns=["string"], min_itemsize={"string": 30})
        check_col("df", "string", 30)
        _maybe_remove(store, "df")
        store.append("df", df_new, data_columns=["string"], min_itemsize=30)
        check_col("df", "string", 30)
        _maybe_remove(store, "df")
        store.append("df", df_new, data_columns=["string"], min_itemsize={"values": 30})
        check_col("df", "string", 30)

    with ensure_clean_store(setup_path) as store:
        df_new["string2"] = "foobarbah"
        df_new["string_block1"] = "foobarbah1"
        df_new["string_block2"] = "foobarbah2"
        _maybe_remove(store, "df")
        store.append(
            "df",
            df_new,
            data_columns=["string", "string2"],
            min_itemsize={"string": 30, "string2": 40, "values": 50},
        )
        check_col("df", "string", 30)
        check_col("df", "string2", 40)
        check_col("df", "values_block_1", 50)

    with ensure_clean_store(setup_path) as store:
        # multiple data columns
        df_new = df.copy()
        df_new.iloc[0, df_new.columns.get_loc("A")] = 1.0
        df_new.iloc[0, df_new.columns.get_loc("B")] = -1.0
        df_new["string"] = "foo"

        sl = df_new.columns.get_loc("string")
        df_new.iloc[1:4, sl] = np.nan
        df_new.iloc[5:6, sl] = "bar"

        df_new["string2"] = "foo"
        sl = df_new.columns.get_loc("string2")
        df_new.iloc[2:5, sl] = np.nan
        df_new.iloc[7:8, sl] = "bar"
        _maybe_remove(store, "df")
        store.append("df", df_new, data_columns=["A", "B", "string", "string2"])
        result = store.select("df", "string='foo' and string2='foo' and A>0 and B<0")
        expected = df_new[
            (df_new.string == "foo")
            & (df_new.string2 == "foo")
            & (df_new.A > 0)
            & (df_new.B < 0)
        ]
        tm.assert_frame_equal(result, expected, check_freq=False)
        # FIXME: 2020-05-07 freq check randomly fails in the CI

        # yield an empty frame
        result = store.select("df", "string='foo' and string2='cool'")
        expected = df_new[(df_new.string == "foo") & (df_new.string2 == "cool")]
        tm.assert_frame_equal(result, expected)

    with ensure_clean_store(setup_path) as store:
        # doc example
        df_dc = df.copy()
        df_dc["string"] = "foo"
        df_dc.loc[df_dc.index[4:6], "string"] = np.nan
        df_dc.loc[df_dc.index[7:9], "string"] = "bar"
        df_dc["string2"] = "cool"
        df_dc["datetime"] = Timestamp("20010102").as_unit("ns")
        df_dc.loc[df_dc.index[3:5], ["A", "B", "datetime"]] = np.nan

        _maybe_remove(store, "df_dc")
        store.append(
            "df_dc", df_dc, data_columns=["B", "C", "string", "string2", "datetime"]
        )
        result = store.select("df_dc", "B>0")

        expected = df_dc[df_dc.B > 0]
        tm.assert_frame_equal(result, expected)

        result = store.select("df_dc", ["B > 0", "C > 0", "string == foo"])
        expected = df_dc[(df_dc.B > 0) & (df_dc.C > 0) & (df_dc.string == "foo")]
        tm.assert_frame_equal(result, expected, check_freq=False)
        # FIXME: 2020-12-07 intermittent build failures here with freq of
        #  None instead of BDay(4)

    with ensure_clean_store(setup_path) as store:
        # doc example part 2

        index = date_range("1/1/2000", periods=8)
        df_dc = DataFrame(
            np.random.default_rng(2).standard_normal((8, 3)),
            index=index,
            columns=["A", "B", "C"],
        )
        df_dc["string"] = "foo"
        df_dc.loc[df_dc.index[4:6], "string"] = np.nan
        df_dc.loc[df_dc.index[7:9], "string"] = "bar"
        df_dc[["B", "C"]] = df_dc[["B", "C"]].abs()
        df_dc["string2"] = "cool"

        # on-disk operations
        store.append("df_dc", df_dc, data_columns=["B", "C", "string", "string2"])

        result = store.select("df_dc", "B>0")
        expected = df_dc[df_dc.B > 0]
        tm.assert_frame_equal(result, expected)

        result = store.select("df_dc", ["B > 0", "C > 0", 'string == "foo"'])
        expected = df_dc[(df_dc.B > 0) & (df_dc.C > 0) & (df_dc.string == "foo")]
        tm.assert_frame_equal(result, expected)


def test_append_hierarchical(tmp_path, setup_path, multiindex_dataframe_random_data):
    df = multiindex_dataframe_random_data
    df.columns.name = None

    with ensure_clean_store(setup_path) as store:
        store.append("mi", df)
        result = store.select("mi")
        tm.assert_frame_equal(result, df)

        # GH 3748
        result = store.select("mi", columns=["A", "B"])
        expected = df.reindex(columns=["A", "B"])
        tm.assert_frame_equal(result, expected)

    path = tmp_path / "test.hdf"
    df.to_hdf(path, key="df", format="table")
    result = read_hdf(path, "df", columns=["A", "B"])
    expected = df.reindex(columns=["A", "B"])
    tm.assert_frame_equal(result, expected)


def test_append_misc(setup_path):
    with ensure_clean_store(setup_path) as store:
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=Index(list("ABCD")),
            index=Index([f"i-{i}" for i in range(30)]),
        )
        store.append("df", df, chunksize=1)
        result = store.select("df")
        tm.assert_frame_equal(result, df)

        store.append("df1", df, expectedrows=10)
        result = store.select("df1")
        tm.assert_frame_equal(result, df)


@pytest.mark.parametrize("chunksize", [10, 200, 1000])
def test_append_misc_chunksize(setup_path, chunksize):
    # more chunksize in append tests
    df = DataFrame(
        1.1 * np.arange(120).reshape((30, 4)),
        columns=Index(list("ABCD")),
        index=Index([f"i-{i}" for i in range(30)]),
    )
    df["string"] = "foo"
    df["float322"] = 1.0
    df["float322"] = df["float322"].astype("float32")
    df["bool"] = df["float322"] > 0
    df["time1"] = Timestamp("20130101").as_unit("ns")
    df["time2"] = Timestamp("20130102").as_unit("ns")
    with ensure_clean_store(setup_path, mode="w") as store:
        store.append("obj", df, chunksize=chunksize)
        result = store.select("obj")
        tm.assert_frame_equal(result, df)


def test_append_misc_empty_frame(setup_path):
    # empty frame, GH4273
    with ensure_clean_store(setup_path) as store:
        # 0 len
        df_empty = DataFrame(columns=list("ABC"))
        store.append("df", df_empty)
        with pytest.raises(KeyError, match="'No object named df in the file'"):
            store.select("df")

        # repeated append of 0/non-zero frames
        df = DataFrame(np.random.default_rng(2).random((10, 3)), columns=list("ABC"))
        store.append("df", df)
        tm.assert_frame_equal(store.select("df"), df)
        store.append("df", df_empty)
        tm.assert_frame_equal(store.select("df"), df)

        # store
        df = DataFrame(columns=list("ABC"))
        store.put("df2", df)
        tm.assert_frame_equal(store.select("df2"), df)


# TODO(ArrayManager) currently we rely on falling back to BlockManager, but
# the conversion from AM->BM converts the invalid object dtype column into
# a datetime64 column no longer raising an error
@td.skip_array_manager_not_yet_implemented
def test_append_raise(setup_path, using_infer_string):
    with ensure_clean_store(setup_path) as store:
        # test append with invalid input to get good error messages

        # list in column
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=Index(list("ABCD")),
            index=Index([f"i-{i}" for i in range(30)]),
        )
        df["invalid"] = [["a"]] * len(df)
        assert df.dtypes["invalid"] == np.object_
        msg = re.escape(
            """Cannot serialize the column [invalid]
because its data contents are not [string] but [mixed] object dtype"""
        )
        with pytest.raises(TypeError, match=msg):
            store.append("df", df)

        # multiple invalid columns
        df["invalid2"] = [["a"]] * len(df)
        df["invalid3"] = [["a"]] * len(df)
        with pytest.raises(TypeError, match=msg):
            store.append("df", df)

        # datetime with embedded nans as object
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=Index(list("ABCD")),
            index=Index([f"i-{i}" for i in range(30)]),
        )
        s = Series(datetime.datetime(2001, 1, 2), index=df.index)
        s = s.astype(object)
        s[0:5] = np.nan
        df["invalid"] = s
        assert df.dtypes["invalid"] == np.object_
        msg = "too many timezones in this block, create separate data columns"
        with pytest.raises(TypeError, match=msg):
            store.append("df", df)

        # directly ndarray
        msg = "value must be None, Series, or DataFrame"
        with pytest.raises(TypeError, match=msg):
            store.append("df", np.arange(10))

        # series directly
        msg = re.escape(
            "cannot properly create the storer for: "
            "[group->df,value-><class 'pandas.core.series.Series'>]"
        )
        with pytest.raises(TypeError, match=msg):
            store.append("df", Series(np.arange(10)))

        # appending an incompatible table
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=Index(list("ABCD")),
            index=Index([f"i-{i}" for i in range(30)]),
        )
        store.append("df", df)

        df["foo"] = "foo"
        msg = re.escape(
            "invalid combination of [non_index_axes] on appending data "
            "[(1, ['A', 'B', 'C', 'D', 'foo'])] vs current table "
            "[(1, ['A', 'B', 'C', 'D'])]"
        )
        with pytest.raises(ValueError, match=msg):
            store.append("df", df)

        # incompatible type (GH 41897)
        _maybe_remove(store, "df")
        df["foo"] = Timestamp("20130101")
        store.append("df", df)
        df["foo"] = "bar"
        msg = re.escape(
            "Cannot serialize the column [foo] "
            "because its data contents are not [string] "
            "but [datetime64[s]] object dtype"
        )
        with pytest.raises(ValueError, match=msg):
            store.append("df", df)


def test_append_with_timedelta(setup_path):
    # GH 3577
    # append timedelta

    ts = Timestamp("20130101").as_unit("ns")
    df = DataFrame(
        {
            "A": ts,
            "B": [ts + timedelta(days=i, seconds=10) for i in range(10)],
        }
    )
    df["C"] = df["A"] - df["B"]
    df.loc[3:5, "C"] = np.nan

    with ensure_clean_store(setup_path) as store:
        # table
        _maybe_remove(store, "df")
        store.append("df", df, data_columns=True)
        result = store.select("df")
        tm.assert_frame_equal(result, df)

        result = store.select("df", where="C<100000")
        tm.assert_frame_equal(result, df)

        result = store.select("df", where="C<pd.Timedelta('-3D')")
        tm.assert_frame_equal(result, df.iloc[3:])

        result = store.select("df", "C<'-3D'")
        tm.assert_frame_equal(result, df.iloc[3:])

        # a bit hacky here as we don't really deal with the NaT properly

        result = store.select("df", "C<'-500000s'")
        result = result.dropna(subset=["C"])
        tm.assert_frame_equal(result, df.iloc[6:])

        result = store.select("df", "C<'-3.5D'")
        result = result.iloc[1:]
        tm.assert_frame_equal(result, df.iloc[4:])

        # fixed
        _maybe_remove(store, "df2")
        store.put("df2", df)
        result = store.select("df2")
        tm.assert_frame_equal(result, df)


def test_append_to_multiple(setup_path):
    df1 = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )
    df2 = df1.copy().rename(columns="{}_2".format)
    df2["foo"] = "bar"
    df = concat([df1, df2], axis=1)

    with ensure_clean_store(setup_path) as store:
        # exceptions
        msg = "append_to_multiple requires a selector that is in passed dict"
        with pytest.raises(ValueError, match=msg):
            store.append_to_multiple(
                {"df1": ["A", "B"], "df2": None}, df, selector="df3"
            )

        with pytest.raises(ValueError, match=msg):
            store.append_to_multiple({"df1": None, "df2": None}, df, selector="df3")

        msg = (
            "append_to_multiple must have a dictionary specified as the way to "
            "split the value"
        )
        with pytest.raises(ValueError, match=msg):
            store.append_to_multiple("df1", df, "df1")

        # regular operation
        store.append_to_multiple({"df1": ["A", "B"], "df2": None}, df, selector="df1")
        result = store.select_as_multiple(
            ["df1", "df2"], where=["A>0", "B>0"], selector="df1"
        )
        expected = df[(df.A > 0) & (df.B > 0)]
        tm.assert_frame_equal(result, expected)


def test_append_to_multiple_dropna(setup_path):
    df1 = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )
    df2 = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    ).rename(columns="{}_2".format)
    df1.iloc[1, df1.columns.get_indexer(["A", "B"])] = np.nan
    df = concat([df1, df2], axis=1)

    with ensure_clean_store(setup_path) as store:
        # dropna=True should guarantee rows are synchronized
        store.append_to_multiple(
            {"df1": ["A", "B"], "df2": None}, df, selector="df1", dropna=True
        )
        result = store.select_as_multiple(["df1", "df2"])
        expected = df.dropna()
        tm.assert_frame_equal(result, expected, check_index_type=True)
        tm.assert_index_equal(store.select("df1").index, store.select("df2").index)


def test_append_to_multiple_dropna_false(setup_path):
    df1 = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )
    df2 = df1.copy().rename(columns="{}_2".format)
    df1.iloc[1, df1.columns.get_indexer(["A", "B"])] = np.nan
    df = concat([df1, df2], axis=1)

    with ensure_clean_store(setup_path) as store, pd.option_context(
        "io.hdf.dropna_table", True
    ):
        # dropna=False shouldn't synchronize row indexes
        store.append_to_multiple(
            {"df1a": ["A", "B"], "df2a": None}, df, selector="df1a", dropna=False
        )

        msg = "all tables must have exactly the same nrows!"
        with pytest.raises(ValueError, match=msg):
            store.select_as_multiple(["df1a", "df2a"])

        assert not store.select("df1a").index.equals(store.select("df2a").index)


def test_append_to_multiple_min_itemsize(setup_path):
    # GH 11238
    df = DataFrame(
        {
            "IX": np.arange(1, 21),
            "Num": np.arange(1, 21),
            "BigNum": np.arange(1, 21) * 88,
            "Str": ["a" for _ in range(20)],
            "LongStr": ["abcde" for _ in range(20)],
        }
    )
    expected = df.iloc[[0]]

    with ensure_clean_store(setup_path) as store:
        store.append_to_multiple(
            {
                "index": ["IX"],
                "nums": ["Num", "BigNum"],
                "strs": ["Str", "LongStr"],
            },
            df.iloc[[0]],
            "index",
            min_itemsize={"Str": 10, "LongStr": 100, "Num": 2},
        )
        result = store.select_as_multiple(["index", "nums", "strs"])
        tm.assert_frame_equal(result, expected, check_index_type=True)


def test_append_string_nan_rep(setup_path):
    # GH 16300
    df = DataFrame({"A": "a", "B": "foo"}, index=np.arange(10))
    df_nan = df.copy()
    df_nan.loc[0:4, :] = np.nan
    msg = "NaN representation is too large for existing column size"

    with ensure_clean_store(setup_path) as store:
        # string column too small
        store.append("sa", df["A"])
        with pytest.raises(ValueError, match=msg):
            store.append("sa", df_nan["A"])

        # nan_rep too big
        store.append("sb", df["B"], nan_rep="bars")
        with pytest.raises(ValueError, match=msg):
            store.append("sb", df_nan["B"])

        # smaller modified nan_rep
        store.append("sc", df["A"], nan_rep="n")
        store.append("sc", df_nan["A"])
        result = store["sc"]
        expected = concat([df["A"], df_nan["A"]])
        tm.assert_series_equal(result, expected)
