import io

import numpy as np
import pytest

from pandas._config import using_string_dtype

from pandas import (
    DataFrame,
    date_range,
    read_csv,
    read_excel,
    read_feather,
    read_json,
    read_parquet,
    read_pickle,
    read_stata,
    read_table,
)
import pandas._testing as tm
from pandas.util import _test_decorators as td

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)


@pytest.fixture
def fsspectest():
    pytest.importorskip("fsspec")
    from fsspec import register_implementation
    from fsspec.implementations.memory import MemoryFileSystem
    from fsspec.registry import _registry as registry

    class TestMemoryFS(MemoryFileSystem):
        protocol = "testmem"
        test = [None]

        def __init__(self, **kwargs) -> None:
            self.test[0] = kwargs.pop("test", None)
            super().__init__(**kwargs)

    register_implementation("testmem", TestMemoryFS, clobber=True)
    yield TestMemoryFS()
    registry.pop("testmem", None)
    TestMemoryFS.test[0] = None
    TestMemoryFS.store.clear()


@pytest.fixture
def df1():
    return DataFrame(
        {
            "int": [1, 3],
            "float": [2.0, np.nan],
            "str": ["t", "s"],
            "dt": date_range("2018-06-18", periods=2),
        }
    )


@pytest.fixture
def cleared_fs():
    fsspec = pytest.importorskip("fsspec")

    memfs = fsspec.filesystem("memory")
    yield memfs
    memfs.store.clear()


def test_read_csv(cleared_fs, df1):
    text = str(df1.to_csv(index=False)).encode()
    with cleared_fs.open("test/test.csv", "wb") as w:
        w.write(text)
    df2 = read_csv("memory://test/test.csv", parse_dates=["dt"])

    tm.assert_frame_equal(df1, df2)


def test_reasonable_error(monkeypatch, cleared_fs):
    from fsspec.registry import known_implementations

    with pytest.raises(ValueError, match="nosuchprotocol"):
        read_csv("nosuchprotocol://test/test.csv")
    err_msg = "test error message"
    monkeypatch.setitem(
        known_implementations,
        "couldexist",
        {"class": "unimportable.CouldExist", "err": err_msg},
    )
    with pytest.raises(ImportError, match=err_msg):
        read_csv("couldexist://test/test.csv")


def test_to_csv(cleared_fs, df1):
    df1.to_csv("memory://test/test.csv", index=True)

    df2 = read_csv("memory://test/test.csv", parse_dates=["dt"], index_col=0)

    tm.assert_frame_equal(df1, df2)


def test_to_excel(cleared_fs, df1):
    pytest.importorskip("openpyxl")
    ext = "xlsx"
    path = f"memory://test/test.{ext}"
    df1.to_excel(path, index=True)

    df2 = read_excel(path, parse_dates=["dt"], index_col=0)

    tm.assert_frame_equal(df1, df2)


@pytest.mark.parametrize("binary_mode", [False, True])
def test_to_csv_fsspec_object(cleared_fs, binary_mode, df1):
    fsspec = pytest.importorskip("fsspec")

    path = "memory://test/test.csv"
    mode = "wb" if binary_mode else "w"
    with fsspec.open(path, mode=mode).open() as fsspec_object:
        df1.to_csv(fsspec_object, index=True)
        assert not fsspec_object.closed

    mode = mode.replace("w", "r")
    with fsspec.open(path, mode=mode) as fsspec_object:
        df2 = read_csv(
            fsspec_object,
            parse_dates=["dt"],
            index_col=0,
        )
        assert not fsspec_object.closed

    tm.assert_frame_equal(df1, df2)


def test_csv_options(fsspectest):
    df = DataFrame({"a": [0]})
    df.to_csv(
        "testmem://test/test.csv", storage_options={"test": "csv_write"}, index=False
    )
    assert fsspectest.test[0] == "csv_write"
    read_csv("testmem://test/test.csv", storage_options={"test": "csv_read"})
    assert fsspectest.test[0] == "csv_read"


def test_read_table_options(fsspectest):
    # GH #39167
    df = DataFrame({"a": [0]})
    df.to_csv(
        "testmem://test/test.csv", storage_options={"test": "csv_write"}, index=False
    )
    assert fsspectest.test[0] == "csv_write"
    read_table("testmem://test/test.csv", storage_options={"test": "csv_read"})
    assert fsspectest.test[0] == "csv_read"


def test_excel_options(fsspectest):
    pytest.importorskip("openpyxl")
    extension = "xlsx"

    df = DataFrame({"a": [0]})

    path = f"testmem://test/test.{extension}"

    df.to_excel(path, storage_options={"test": "write"}, index=False)
    assert fsspectest.test[0] == "write"
    read_excel(path, storage_options={"test": "read"})
    assert fsspectest.test[0] == "read"


def test_to_parquet_new_file(cleared_fs, df1):
    """Regression test for writing to a not-yet-existent GCS Parquet file."""
    pytest.importorskip("fastparquet")

    df1.to_parquet(
        "memory://test/test.csv", index=True, engine="fastparquet", compression=None
    )


def test_arrowparquet_options(fsspectest):
    """Regression test for writing to a not-yet-existent GCS Parquet file."""
    pytest.importorskip("pyarrow")
    df = DataFrame({"a": [0]})
    df.to_parquet(
        "testmem://test/test.csv",
        engine="pyarrow",
        compression=None,
        storage_options={"test": "parquet_write"},
    )
    assert fsspectest.test[0] == "parquet_write"
    read_parquet(
        "testmem://test/test.csv",
        engine="pyarrow",
        storage_options={"test": "parquet_read"},
    )
    assert fsspectest.test[0] == "parquet_read"


@td.skip_array_manager_not_yet_implemented  # TODO(ArrayManager) fastparquet
def test_fastparquet_options(fsspectest):
    """Regression test for writing to a not-yet-existent GCS Parquet file."""
    pytest.importorskip("fastparquet")

    df = DataFrame({"a": [0]})
    df.to_parquet(
        "testmem://test/test.csv",
        engine="fastparquet",
        compression=None,
        storage_options={"test": "parquet_write"},
    )
    assert fsspectest.test[0] == "parquet_write"
    read_parquet(
        "testmem://test/test.csv",
        engine="fastparquet",
        storage_options={"test": "parquet_read"},
    )
    assert fsspectest.test[0] == "parquet_read"


@pytest.mark.single_cpu
def test_from_s3_csv(s3_public_bucket_with_data, tips_file, s3so):
    pytest.importorskip("s3fs")
    tm.assert_equal(
        read_csv(
            f"s3://{s3_public_bucket_with_data.name}/tips.csv", storage_options=s3so
        ),
        read_csv(tips_file),
    )
    # the following are decompressed by pandas, not fsspec
    tm.assert_equal(
        read_csv(
            f"s3://{s3_public_bucket_with_data.name}/tips.csv.gz", storage_options=s3so
        ),
        read_csv(tips_file),
    )
    tm.assert_equal(
        read_csv(
            f"s3://{s3_public_bucket_with_data.name}/tips.csv.bz2", storage_options=s3so
        ),
        read_csv(tips_file),
    )


@pytest.mark.single_cpu
@pytest.mark.parametrize("protocol", ["s3", "s3a", "s3n"])
def test_s3_protocols(s3_public_bucket_with_data, tips_file, protocol, s3so):
    pytest.importorskip("s3fs")
    tm.assert_equal(
        read_csv(
            f"{protocol}://{s3_public_bucket_with_data.name}/tips.csv",
            storage_options=s3so,
        ),
        read_csv(tips_file),
    )


@pytest.mark.xfail(using_string_dtype(), reason="TODO(infer_string) fastparquet")
@pytest.mark.single_cpu
@td.skip_array_manager_not_yet_implemented  # TODO(ArrayManager) fastparquet
def test_s3_parquet(s3_public_bucket, s3so, df1):
    pytest.importorskip("fastparquet")
    pytest.importorskip("s3fs")

    fn = f"s3://{s3_public_bucket.name}/test.parquet"
    df1.to_parquet(
        fn, index=False, engine="fastparquet", compression=None, storage_options=s3so
    )
    df2 = read_parquet(fn, engine="fastparquet", storage_options=s3so)
    tm.assert_equal(df1, df2)


@td.skip_if_installed("fsspec")
def test_not_present_exception():
    msg = "Missing optional dependency 'fsspec'|fsspec library is required"
    with pytest.raises(ImportError, match=msg):
        read_csv("memory://test/test.csv")


def test_feather_options(fsspectest):
    pytest.importorskip("pyarrow")
    df = DataFrame({"a": [0]})
    df.to_feather("testmem://mockfile", storage_options={"test": "feather_write"})
    assert fsspectest.test[0] == "feather_write"
    out = read_feather("testmem://mockfile", storage_options={"test": "feather_read"})
    assert fsspectest.test[0] == "feather_read"
    tm.assert_frame_equal(df, out)


def test_pickle_options(fsspectest):
    df = DataFrame({"a": [0]})
    df.to_pickle("testmem://mockfile", storage_options={"test": "pickle_write"})
    assert fsspectest.test[0] == "pickle_write"
    out = read_pickle("testmem://mockfile", storage_options={"test": "pickle_read"})
    assert fsspectest.test[0] == "pickle_read"
    tm.assert_frame_equal(df, out)


def test_json_options(fsspectest, compression):
    df = DataFrame({"a": [0]})
    df.to_json(
        "testmem://mockfile",
        compression=compression,
        storage_options={"test": "json_write"},
    )
    assert fsspectest.test[0] == "json_write"
    out = read_json(
        "testmem://mockfile",
        compression=compression,
        storage_options={"test": "json_read"},
    )
    assert fsspectest.test[0] == "json_read"
    tm.assert_frame_equal(df, out)


def test_stata_options(fsspectest):
    df = DataFrame({"a": [0]})
    df.to_stata(
        "testmem://mockfile", storage_options={"test": "stata_write"}, write_index=False
    )
    assert fsspectest.test[0] == "stata_write"
    out = read_stata("testmem://mockfile", storage_options={"test": "stata_read"})
    assert fsspectest.test[0] == "stata_read"
    tm.assert_frame_equal(df, out.astype("int64"))


def test_markdown_options(fsspectest):
    pytest.importorskip("tabulate")
    df = DataFrame({"a": [0]})
    df.to_markdown("testmem://mockfile", storage_options={"test": "md_write"})
    assert fsspectest.test[0] == "md_write"
    assert fsspectest.cat("testmem://mockfile")


def test_non_fsspec_options():
    pytest.importorskip("pyarrow")
    with pytest.raises(ValueError, match="storage_options"):
        read_csv("localfile", storage_options={"a": True})
    with pytest.raises(ValueError, match="storage_options"):
        # separate test for parquet, which has a different code path
        read_parquet("localfile", storage_options={"a": True})
    by = io.BytesIO()

    with pytest.raises(ValueError, match="storage_options"):
        read_csv(by, storage_options={"a": True})

    df = DataFrame({"a": [0]})
    with pytest.raises(ValueError, match="storage_options"):
        df.to_parquet("nonfsspecpath", storage_options={"a": True})
