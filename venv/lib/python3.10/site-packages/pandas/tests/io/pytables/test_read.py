from contextlib import closing
from pathlib import Path
import re

import numpy as np
import pytest

from pandas._libs.tslibs import Timestamp
from pandas.compat import is_platform_windows

import pandas as pd
from pandas import (
    DataFrame,
    HDFStore,
    Index,
    Series,
    _testing as tm,
    date_range,
    read_hdf,
)
from pandas.tests.io.pytables.common import (
    _maybe_remove,
    ensure_clean_store,
)
from pandas.util import _test_decorators as td

from pandas.io.pytables import TableIterator

pytestmark = [pytest.mark.single_cpu]


def test_read_missing_key_close_store(tmp_path, setup_path):
    # GH 25766
    path = tmp_path / setup_path
    df = DataFrame({"a": range(2), "b": range(2)})
    df.to_hdf(path, key="k1")

    with pytest.raises(KeyError, match="'No object named k2 in the file'"):
        read_hdf(path, "k2")

    # smoke test to test that file is properly closed after
    # read with KeyError before another write
    df.to_hdf(path, key="k2")


def test_read_index_error_close_store(tmp_path, setup_path):
    # GH 25766
    path = tmp_path / setup_path
    df = DataFrame({"A": [], "B": []}, index=[])
    df.to_hdf(path, key="k1")

    with pytest.raises(IndexError, match=r"list index out of range"):
        read_hdf(path, "k1", stop=0)

    # smoke test to test that file is properly closed after
    # read with IndexError before another write
    df.to_hdf(path, key="k1")


def test_read_missing_key_opened_store(tmp_path, setup_path):
    # GH 28699
    path = tmp_path / setup_path
    df = DataFrame({"a": range(2), "b": range(2)})
    df.to_hdf(path, key="k1")

    with HDFStore(path, "r") as store:
        with pytest.raises(KeyError, match="'No object named k2 in the file'"):
            read_hdf(store, "k2")

        # Test that the file is still open after a KeyError and that we can
        # still read from it.
        read_hdf(store, "k1")


def test_read_column(setup_path):
    df = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )

    with ensure_clean_store(setup_path) as store:
        _maybe_remove(store, "df")

        # GH 17912
        # HDFStore.select_column should raise a KeyError
        # exception if the key is not a valid store
        with pytest.raises(KeyError, match="No object named df in the file"):
            store.select_column("df", "index")

        store.append("df", df)
        # error
        with pytest.raises(
            KeyError, match=re.escape("'column [foo] not found in the table'")
        ):
            store.select_column("df", "foo")

        msg = re.escape("select_column() got an unexpected keyword argument 'where'")
        with pytest.raises(TypeError, match=msg):
            store.select_column("df", "index", where=["index>5"])

        # valid
        result = store.select_column("df", "index")
        tm.assert_almost_equal(result.values, Series(df.index).values)
        assert isinstance(result, Series)

        # not a data indexable column
        msg = re.escape(
            "column [values_block_0] can not be extracted individually; "
            "it is not data indexable"
        )
        with pytest.raises(ValueError, match=msg):
            store.select_column("df", "values_block_0")

        # a data column
        df2 = df.copy()
        df2["string"] = "foo"
        store.append("df2", df2, data_columns=["string"])
        result = store.select_column("df2", "string")
        tm.assert_almost_equal(result.values, df2["string"].values)

        # a data column with NaNs, result excludes the NaNs
        df3 = df.copy()
        df3["string"] = "foo"
        df3.loc[df3.index[4:6], "string"] = np.nan
        store.append("df3", df3, data_columns=["string"])
        result = store.select_column("df3", "string")
        tm.assert_almost_equal(result.values, df3["string"].values)

        # start/stop
        result = store.select_column("df3", "string", start=2)
        tm.assert_almost_equal(result.values, df3["string"].values[2:])

        result = store.select_column("df3", "string", start=-2)
        tm.assert_almost_equal(result.values, df3["string"].values[-2:])

        result = store.select_column("df3", "string", stop=2)
        tm.assert_almost_equal(result.values, df3["string"].values[:2])

        result = store.select_column("df3", "string", stop=-2)
        tm.assert_almost_equal(result.values, df3["string"].values[:-2])

        result = store.select_column("df3", "string", start=2, stop=-2)
        tm.assert_almost_equal(result.values, df3["string"].values[2:-2])

        result = store.select_column("df3", "string", start=-2, stop=2)
        tm.assert_almost_equal(result.values, df3["string"].values[-2:2])

        # GH 10392 - make sure column name is preserved
        df4 = DataFrame({"A": np.random.default_rng(2).standard_normal(10), "B": "foo"})
        store.append("df4", df4, data_columns=True)
        expected = df4["B"]
        result = store.select_column("df4", "B")
        tm.assert_series_equal(result, expected)


def test_pytables_native_read(datapath):
    with ensure_clean_store(
        datapath("io", "data", "legacy_hdf/pytables_native.h5"), mode="r"
    ) as store:
        d2 = store["detector/readout"]
    assert isinstance(d2, DataFrame)


@pytest.mark.skipif(is_platform_windows(), reason="native2 read fails oddly on windows")
def test_pytables_native2_read(datapath):
    with ensure_clean_store(
        datapath("io", "data", "legacy_hdf", "pytables_native2.h5"), mode="r"
    ) as store:
        str(store)
        d1 = store["detector"]
    assert isinstance(d1, DataFrame)


def test_legacy_table_fixed_format_read_py2(datapath):
    # GH 24510
    # legacy table with fixed format written in Python 2
    with ensure_clean_store(
        datapath("io", "data", "legacy_hdf", "legacy_table_fixed_py2.h5"), mode="r"
    ) as store:
        result = store.select("df")
    expected = DataFrame(
        [[1, 2, 3, "D"]],
        columns=["A", "B", "C", "D"],
        index=Index(["ABC"], name="INDEX_NAME"),
    )
    tm.assert_frame_equal(expected, result)


def test_legacy_table_fixed_format_read_datetime_py2(datapath):
    # GH 31750
    # legacy table with fixed format and datetime64 column written in Python 2
    expected = DataFrame(
        [[Timestamp("2020-02-06T18:00")]],
        columns=["A"],
        index=Index(["date"]),
        dtype="M8[ns]",
    )
    with ensure_clean_store(
        datapath("io", "data", "legacy_hdf", "legacy_table_fixed_datetime_py2.h5"),
        mode="r",
    ) as store:
        result = store.select("df")
    tm.assert_frame_equal(expected, result)


def test_legacy_table_read_py2(datapath):
    # issue: 24925
    # legacy table written in Python 2
    with ensure_clean_store(
        datapath("io", "data", "legacy_hdf", "legacy_table_py2.h5"), mode="r"
    ) as store:
        result = store.select("table")

    expected = DataFrame({"a": ["a", "b"], "b": [2, 3]})
    tm.assert_frame_equal(expected, result)


def test_read_hdf_open_store(tmp_path, setup_path, using_infer_string):
    # GH10330
    # No check for non-string path_or-buf, and no test of open store
    df = DataFrame(
        np.random.default_rng(2).random((4, 5)),
        index=list("abcd"),
        columns=list("ABCDE"),
    )
    df.index.name = "letters"
    df = df.set_index(keys="E", append=True)

    path = tmp_path / setup_path
    if using_infer_string:
        # TODO(infer_string) make this work for string dtype
        msg = "Saving a MultiIndex with an extension dtype is not supported."
        with pytest.raises(NotImplementedError, match=msg):
            df.to_hdf(path, key="df", mode="w")
        return
    df.to_hdf(path, key="df", mode="w")
    direct = read_hdf(path, "df")
    with HDFStore(path, mode="r") as store:
        indirect = read_hdf(store, "df")
        tm.assert_frame_equal(direct, indirect)
        assert store.is_open


def test_read_hdf_index_not_view(tmp_path, setup_path):
    # GH 37441
    # Ensure that the index of the DataFrame is not a view
    # into the original recarray that pytables reads in
    df = DataFrame(
        np.random.default_rng(2).random((4, 5)),
        index=[0, 1, 2, 3],
        columns=list("ABCDE"),
    )

    path = tmp_path / setup_path
    df.to_hdf(path, key="df", mode="w", format="table")

    df2 = read_hdf(path, "df")
    assert df2.index._data.base is None
    tm.assert_frame_equal(df, df2)


def test_read_hdf_iterator(tmp_path, setup_path):
    df = DataFrame(
        np.random.default_rng(2).random((4, 5)),
        index=list("abcd"),
        columns=list("ABCDE"),
    )
    df.index.name = "letters"
    df = df.set_index(keys="E", append=True)

    path = tmp_path / setup_path
    df.to_hdf(path, key="df", mode="w", format="t")
    direct = read_hdf(path, "df")
    iterator = read_hdf(path, "df", iterator=True)
    with closing(iterator.store):
        assert isinstance(iterator, TableIterator)
        indirect = next(iterator.__iter__())
    tm.assert_frame_equal(direct, indirect)


def test_read_nokey(tmp_path, setup_path):
    # GH10443
    df = DataFrame(
        np.random.default_rng(2).random((4, 5)),
        index=list("abcd"),
        columns=list("ABCDE"),
    )

    # Categorical dtype not supported for "fixed" format. So no need
    # to test with that dtype in the dataframe here.
    path = tmp_path / setup_path
    df.to_hdf(path, key="df", mode="a")
    reread = read_hdf(path)
    tm.assert_frame_equal(df, reread)
    df.to_hdf(path, key="df2", mode="a")

    msg = "key must be provided when HDF5 file contains multiple datasets."
    with pytest.raises(ValueError, match=msg):
        read_hdf(path)


def test_read_nokey_table(tmp_path, setup_path):
    # GH13231
    df = DataFrame({"i": range(5), "c": Series(list("abacd"), dtype="category")})

    path = tmp_path / setup_path
    df.to_hdf(path, key="df", mode="a", format="table")
    reread = read_hdf(path)
    tm.assert_frame_equal(df, reread)
    df.to_hdf(path, key="df2", mode="a", format="table")

    msg = "key must be provided when HDF5 file contains multiple datasets."
    with pytest.raises(ValueError, match=msg):
        read_hdf(path)


def test_read_nokey_empty(tmp_path, setup_path):
    path = tmp_path / setup_path
    store = HDFStore(path)
    store.close()
    msg = re.escape(
        "Dataset(s) incompatible with Pandas data types, not table, or no "
        "datasets found in HDF5 file."
    )
    with pytest.raises(ValueError, match=msg):
        read_hdf(path)


def test_read_from_pathlib_path(tmp_path, setup_path):
    # GH11773
    expected = DataFrame(
        np.random.default_rng(2).random((4, 5)),
        index=list("abcd"),
        columns=list("ABCDE"),
    )
    filename = tmp_path / setup_path
    path_obj = Path(filename)

    expected.to_hdf(path_obj, key="df", mode="a")
    actual = read_hdf(path_obj, key="df")

    tm.assert_frame_equal(expected, actual)


@td.skip_if_no("py.path")
def test_read_from_py_localpath(tmp_path, setup_path):
    # GH11773
    from py.path import local as LocalPath

    expected = DataFrame(
        np.random.default_rng(2).random((4, 5)),
        index=list("abcd"),
        columns=list("ABCDE"),
    )
    filename = tmp_path / setup_path
    path_obj = LocalPath(filename)

    expected.to_hdf(path_obj, key="df", mode="a")
    actual = read_hdf(path_obj, key="df")

    tm.assert_frame_equal(expected, actual)


@pytest.mark.parametrize("format", ["fixed", "table"])
def test_read_hdf_series_mode_r(tmp_path, format, setup_path):
    # GH 16583
    # Tests that reading a Series saved to an HDF file
    # still works if a mode='r' argument is supplied
    series = Series(range(10), dtype=np.float64)
    path = tmp_path / setup_path
    series.to_hdf(path, key="data", format=format)
    result = read_hdf(path, key="data", mode="r")
    tm.assert_series_equal(result, series)


@pytest.mark.filterwarnings(r"ignore:Period with BDay freq is deprecated:FutureWarning")
@pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
def test_read_py2_hdf_file_in_py3(datapath):
    # GH 16781

    # tests reading a PeriodIndex DataFrame written in Python2 in Python3

    # the file was generated in Python 2.7 like so:
    #
    # df = DataFrame([1.,2,3], index=pd.PeriodIndex(
    #              ['2015-01-01', '2015-01-02', '2015-01-05'], freq='B'))
    # df.to_hdf('periodindex_0.20.1_x86_64_darwin_2.7.13.h5', 'p')

    expected = DataFrame(
        [1.0, 2, 3],
        index=pd.PeriodIndex(["2015-01-01", "2015-01-02", "2015-01-05"], freq="B"),
    )

    with ensure_clean_store(
        datapath(
            "io", "data", "legacy_hdf", "periodindex_0.20.1_x86_64_darwin_2.7.13.h5"
        ),
        mode="r",
    ) as store:
        result = store["p"]
    tm.assert_frame_equal(result, expected)


def test_read_infer_string(tmp_path, setup_path):
    # GH#54431
    df = DataFrame({"a": ["a", "b", None]})
    path = tmp_path / setup_path
    df.to_hdf(path, key="data", format="table")
    with pd.option_context("future.infer_string", True):
        result = read_hdf(path, key="data", mode="r")
    expected = DataFrame(
        {"a": ["a", "b", None]},
        dtype=pd.StringDtype(na_value=np.nan),
        columns=Index(["a"], dtype=pd.StringDtype(na_value=np.nan)),
    )
    tm.assert_frame_equal(result, expected)
