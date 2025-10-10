import re

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
    concat,
    date_range,
)
from pandas.tests.io.pytables.common import (
    _maybe_remove,
    ensure_clean_store,
)
from pandas.util import _test_decorators as td

pytestmark = [pytest.mark.single_cpu]


def test_format_type(tmp_path, setup_path):
    df = DataFrame({"A": [1, 2]})
    with HDFStore(tmp_path / setup_path) as store:
        store.put("a", df, format="fixed")
        store.put("b", df, format="table")

        assert store.get_storer("a").format_type == "fixed"
        assert store.get_storer("b").format_type == "table"


def test_format_kwarg_in_constructor(tmp_path, setup_path):
    # GH 13291

    msg = "format is not a defined argument for HDFStore"

    with pytest.raises(ValueError, match=msg):
        HDFStore(tmp_path / setup_path, format="table")


def test_api_default_format(tmp_path, setup_path):
    # default_format option
    with ensure_clean_store(setup_path) as store:
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=Index(list("ABCD")),
            index=Index([f"i-{i}" for i in range(30)]),
        )

        with pd.option_context("io.hdf.default_format", "fixed"):
            _maybe_remove(store, "df")
            store.put("df", df)
            assert not store.get_storer("df").is_table

            msg = "Can only append to Tables"
            with pytest.raises(ValueError, match=msg):
                store.append("df2", df)

        with pd.option_context("io.hdf.default_format", "table"):
            _maybe_remove(store, "df")
            store.put("df", df)
            assert store.get_storer("df").is_table

            _maybe_remove(store, "df2")
            store.append("df2", df)
            assert store.get_storer("df").is_table

    path = tmp_path / setup_path
    df = DataFrame(
        1.1 * np.arange(120).reshape((30, 4)),
        columns=Index(list("ABCD")),
        index=Index([f"i-{i}" for i in range(30)]),
    )

    with pd.option_context("io.hdf.default_format", "fixed"):
        df.to_hdf(path, key="df")
        with HDFStore(path) as store:
            assert not store.get_storer("df").is_table
        with pytest.raises(ValueError, match=msg):
            df.to_hdf(path, key="df2", append=True)

    with pd.option_context("io.hdf.default_format", "table"):
        df.to_hdf(path, key="df3")
        with HDFStore(path) as store:
            assert store.get_storer("df3").is_table
        df.to_hdf(path, key="df4", append=True)
        with HDFStore(path) as store:
            assert store.get_storer("df4").is_table


def test_put(setup_path):
    with ensure_clean_store(setup_path) as store:
        ts = Series(
            np.arange(10, dtype=np.float64), index=date_range("2020-01-01", periods=10)
        )
        df = DataFrame(
            np.random.default_rng(2).standard_normal((20, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=20, freq="B"),
        )
        store["a"] = ts
        store["b"] = df[:10]
        store["foo/bar/bah"] = df[:10]
        store["foo"] = df[:10]
        store["/foo"] = df[:10]
        store.put("c", df[:10], format="table")

        # not OK, not a table
        msg = "Can only append to Tables"
        with pytest.raises(ValueError, match=msg):
            store.put("b", df[10:], append=True)

        # node does not currently exist, test _is_table_type returns False
        # in this case
        _maybe_remove(store, "f")
        with pytest.raises(ValueError, match=msg):
            store.put("f", df[10:], append=True)

        # can't put to a table (use append instead)
        with pytest.raises(ValueError, match=msg):
            store.put("c", df[10:], append=True)

        # overwrite table
        store.put("c", df[:10], format="table", append=False)
        tm.assert_frame_equal(df[:10], store["c"])


def test_put_string_index(setup_path):
    with ensure_clean_store(setup_path) as store:
        index = Index([f"I am a very long string index: {i}" for i in range(20)])
        s = Series(np.arange(20), index=index)
        df = DataFrame({"A": s, "B": s})

        store["a"] = s
        tm.assert_series_equal(store["a"], s)

        store["b"] = df
        tm.assert_frame_equal(store["b"], df)

        # mixed length
        index = Index(
            ["abcdefghijklmnopqrstuvwxyz1234567890"]
            + [f"I am a very long string index: {i}" for i in range(20)]
        )
        s = Series(np.arange(21), index=index)
        df = DataFrame({"A": s, "B": s})
        store["a"] = s
        tm.assert_series_equal(store["a"], s)

        store["b"] = df
        tm.assert_frame_equal(store["b"], df)


def test_put_compression(setup_path):
    with ensure_clean_store(setup_path) as store:
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )

        store.put("c", df, format="table", complib="zlib")
        tm.assert_frame_equal(store["c"], df)

        # can't compress if format='fixed'
        msg = "Compression not supported on Fixed format stores"
        with pytest.raises(ValueError, match=msg):
            store.put("b", df, format="fixed", complib="zlib")


@td.skip_if_windows
def test_put_compression_blosc(setup_path):
    df = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )

    with ensure_clean_store(setup_path) as store:
        # can't compress if format='fixed'
        msg = "Compression not supported on Fixed format stores"
        with pytest.raises(ValueError, match=msg):
            store.put("b", df, format="fixed", complib="blosc")

        store.put("c", df, format="table", complib="blosc")
        tm.assert_frame_equal(store["c"], df)


def test_put_datetime_ser(setup_path):
    # https://github.com/pandas-dev/pandas/pull/60663
    ser = Series(3 * [Timestamp("20010102").as_unit("ns")])
    with ensure_clean_store(setup_path) as store:
        store.put("ser", ser)
        expected = ser.copy()
        result = store.get("ser")
        tm.assert_series_equal(result, expected)


def test_put_mixed_type(setup_path, using_infer_string):
    df = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )
    df["obj1"] = "foo"
    df["obj2"] = "bar"
    df["bool1"] = df["A"] > 0
    df["bool2"] = df["B"] > 0
    df["bool3"] = True
    df["int1"] = 1
    df["int2"] = 2
    df["timestamp1"] = Timestamp("20010102").as_unit("ns")
    df["timestamp2"] = Timestamp("20010103").as_unit("ns")
    df["datetime1"] = Timestamp("20010102").as_unit("ns")
    df["datetime2"] = Timestamp("20010103").as_unit("ns")
    df.loc[df.index[3:6], ["obj1"]] = np.nan
    df = df._consolidate()

    with ensure_clean_store(setup_path) as store:
        _maybe_remove(store, "df")

        warning = None if using_infer_string else pd.errors.PerformanceWarning
        with tm.assert_produces_warning(warning):
            store.put("df", df)

        expected = store.get("df")
        tm.assert_frame_equal(expected, df)


def test_put_str_frame(setup_path, string_dtype_arguments):
    # https://github.com/pandas-dev/pandas/pull/60663
    dtype = pd.StringDtype(*string_dtype_arguments)
    df = DataFrame({"a": pd.array(["x", pd.NA, "y"], dtype=dtype)})
    with ensure_clean_store(setup_path) as store:
        _maybe_remove(store, "df")

        store.put("df", df)
        expected_dtype = "str" if dtype.na_value is np.nan else "string"
        expected = df.astype(expected_dtype)
        result = store.get("df")
        tm.assert_frame_equal(result, expected)


def test_put_str_series(setup_path, string_dtype_arguments):
    # https://github.com/pandas-dev/pandas/pull/60663
    dtype = pd.StringDtype(*string_dtype_arguments)
    ser = Series(["x", pd.NA, "y"], dtype=dtype)
    with ensure_clean_store(setup_path) as store:
        _maybe_remove(store, "df")

        store.put("ser", ser)
        expected_dtype = "str" if dtype.na_value is np.nan else "string"
        expected = ser.astype(expected_dtype)
        result = store.get("ser")
        tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("format", ["table", "fixed"])
@pytest.mark.parametrize(
    "index",
    [
        Index([str(i) for i in range(10)]),
        Index(np.arange(10, dtype=float)),
        Index(np.arange(10)),
        date_range("2020-01-01", periods=10),
        pd.period_range("2020-01-01", periods=10),
    ],
)
def test_store_index_types(setup_path, format, index):
    # GH5386
    # test storing various index types

    with ensure_clean_store(setup_path) as store:
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 2)),
            columns=list("AB"),
            index=index,
        )
        _maybe_remove(store, "df")
        store.put("df", df, format=format)
        tm.assert_frame_equal(df, store["df"])


def test_column_multiindex(setup_path, using_infer_string):
    # GH 4710
    # recreate multi-indexes properly

    index = MultiIndex.from_tuples(
        [("A", "a"), ("A", "b"), ("B", "a"), ("B", "b")], names=["first", "second"]
    )
    df = DataFrame(np.arange(12).reshape(3, 4), columns=index)
    expected = df.set_axis(df.index.to_numpy())

    with ensure_clean_store(setup_path) as store:
        if using_infer_string:
            # TODO(infer_string) make this work for string dtype
            msg = "Saving a MultiIndex with an extension dtype is not supported."
            with pytest.raises(NotImplementedError, match=msg):
                store.put("df", df)
            return
        store.put("df", df)
        tm.assert_frame_equal(
            store["df"], expected, check_index_type=True, check_column_type=True
        )

        store.put("df1", df, format="table")
        tm.assert_frame_equal(
            store["df1"], expected, check_index_type=True, check_column_type=True
        )

        msg = re.escape("cannot use a multi-index on axis [1] with data_columns ['A']")
        with pytest.raises(ValueError, match=msg):
            store.put("df2", df, format="table", data_columns=["A"])
        msg = re.escape("cannot use a multi-index on axis [1] with data_columns True")
        with pytest.raises(ValueError, match=msg):
            store.put("df3", df, format="table", data_columns=True)

    # appending multi-column on existing table (see GH 6167)
    with ensure_clean_store(setup_path) as store:
        store.append("df2", df)
        store.append("df2", df)

        tm.assert_frame_equal(store["df2"], concat((df, df)))

    # non_index_axes name
    df = DataFrame(np.arange(12).reshape(3, 4), columns=Index(list("ABCD"), name="foo"))
    expected = df.set_axis(df.index.to_numpy())

    with ensure_clean_store(setup_path) as store:
        store.put("df1", df, format="table")
        tm.assert_frame_equal(
            store["df1"], expected, check_index_type=True, check_column_type=True
        )


def test_store_multiindex(setup_path):
    # validate multi-index names
    # GH 5527
    with ensure_clean_store(setup_path) as store:

        def make_index(names=None):
            dti = date_range("2013-12-01", "2013-12-02")
            mi = MultiIndex.from_product([dti, range(2), range(3)], names=names)
            return mi

        # no names
        _maybe_remove(store, "df")
        df = DataFrame(np.zeros((12, 2)), columns=["a", "b"], index=make_index())
        store.append("df", df)
        tm.assert_frame_equal(store.select("df"), df)

        # partial names
        _maybe_remove(store, "df")
        df = DataFrame(
            np.zeros((12, 2)),
            columns=["a", "b"],
            index=make_index(["date", None, None]),
        )
        store.append("df", df)
        tm.assert_frame_equal(store.select("df"), df)

        # series
        _maybe_remove(store, "ser")
        ser = Series(np.zeros(12), index=make_index(["date", None, None]))
        store.append("ser", ser)
        xp = Series(np.zeros(12), index=make_index(["date", "level_1", "level_2"]))
        tm.assert_series_equal(store.select("ser"), xp)

        # dup with column
        _maybe_remove(store, "df")
        df = DataFrame(
            np.zeros((12, 2)),
            columns=["a", "b"],
            index=make_index(["date", "a", "t"]),
        )
        msg = "duplicate names/columns in the multi-index when storing as a table"
        with pytest.raises(ValueError, match=msg):
            store.append("df", df)

        # dup within level
        _maybe_remove(store, "df")
        df = DataFrame(
            np.zeros((12, 2)),
            columns=["a", "b"],
            index=make_index(["date", "date", "date"]),
        )
        with pytest.raises(ValueError, match=msg):
            store.append("df", df)

        # fully names
        _maybe_remove(store, "df")
        df = DataFrame(
            np.zeros((12, 2)),
            columns=["a", "b"],
            index=make_index(["date", "s", "t"]),
        )
        store.append("df", df)
        tm.assert_frame_equal(store.select("df"), df)


@pytest.mark.parametrize("format", ["fixed", "table"])
def test_store_periodindex(tmp_path, setup_path, format):
    # GH 7796
    # test of PeriodIndex in HDFStore
    df = DataFrame(
        np.random.default_rng(2).standard_normal((5, 1)),
        index=pd.period_range("20220101", freq="M", periods=5),
    )

    path = tmp_path / setup_path
    df.to_hdf(path, key="df", mode="w", format=format)
    expected = pd.read_hdf(path, "df")
    tm.assert_frame_equal(df, expected)
