from io import BytesIO
import os
import pathlib
import tarfile
import zipfile

import numpy as np
import pytest

from pandas.compat.pyarrow import pa_version_under17p0

from pandas import (
    DataFrame,
    Index,
    date_range,
    read_csv,
    read_excel,
    read_json,
    read_parquet,
)
import pandas._testing as tm
from pandas.util import _test_decorators as td

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)


@pytest.fixture
def gcs_buffer():
    """Emulate GCS using a binary buffer."""
    pytest.importorskip("gcsfs")
    fsspec = pytest.importorskip("fsspec")

    gcs_buffer = BytesIO()
    gcs_buffer.close = lambda: True

    class MockGCSFileSystem(fsspec.AbstractFileSystem):
        @staticmethod
        def open(*args, **kwargs):
            gcs_buffer.seek(0)
            return gcs_buffer

        def ls(self, path, **kwargs):
            # needed for pyarrow
            return [{"name": path, "type": "file"}]

    # Overwrites the default implementation from gcsfs to our mock class
    fsspec.register_implementation("gs", MockGCSFileSystem, clobber=True)

    return gcs_buffer


# Patches pyarrow; other processes should not pick up change
@pytest.mark.single_cpu
@pytest.mark.parametrize("format", ["csv", "json", "parquet", "excel", "markdown"])
def test_to_read_gcs(gcs_buffer, format, monkeypatch, capsys, request):
    """
    Test that many to/read functions support GCS.

    GH 33987
    """

    df1 = DataFrame(
        {
            "int": [1, 3],
            "float": [2.0, np.nan],
            "str": ["t", "s"],
            "dt": date_range("2018-06-18", periods=2),
        }
    )

    path = f"gs://test/test.{format}"

    if format == "csv":
        df1.to_csv(path, index=True)
        df2 = read_csv(path, parse_dates=["dt"], index_col=0)
    elif format == "excel":
        path = "gs://test/test.xlsx"
        df1.to_excel(path)
        df2 = read_excel(path, parse_dates=["dt"], index_col=0)
    elif format == "json":
        df1.to_json(path)
        df2 = read_json(path, convert_dates=["dt"])
    elif format == "parquet":
        pytest.importorskip("pyarrow")
        pa_fs = pytest.importorskip("pyarrow.fs")

        class MockFileSystem(pa_fs.FileSystem):
            @staticmethod
            def from_uri(path):
                print("Using pyarrow filesystem")
                to_local = pathlib.Path(path.replace("gs://", "")).absolute().as_uri()
                return pa_fs.LocalFileSystem(to_local)

        request.applymarker(
            pytest.mark.xfail(
                not pa_version_under17p0,
                raises=TypeError,
                reason="pyarrow 17 broke the mocked filesystem",
            )
        )
        with monkeypatch.context() as m:
            m.setattr(pa_fs, "FileSystem", MockFileSystem)
            df1.to_parquet(path)
            df2 = read_parquet(path)
        captured = capsys.readouterr()
        assert captured.out == "Using pyarrow filesystem\nUsing pyarrow filesystem\n"
    elif format == "markdown":
        pytest.importorskip("tabulate")
        df1.to_markdown(path)
        df2 = df1

    tm.assert_frame_equal(df1, df2)


def assert_equal_zip_safe(result: bytes, expected: bytes, compression: str):
    """
    For zip compression, only compare the CRC-32 checksum of the file contents
    to avoid checking the time-dependent last-modified timestamp which
    in some CI builds is off-by-one

    See https://en.wikipedia.org/wiki/ZIP_(file_format)#File_headers
    """
    if compression == "zip":
        # Only compare the CRC checksum of the file contents
        with zipfile.ZipFile(BytesIO(result)) as exp, zipfile.ZipFile(
            BytesIO(expected)
        ) as res:
            for res_info, exp_info in zip(res.infolist(), exp.infolist()):
                assert res_info.CRC == exp_info.CRC
    elif compression == "tar":
        with tarfile.open(fileobj=BytesIO(result)) as tar_exp, tarfile.open(
            fileobj=BytesIO(expected)
        ) as tar_res:
            for tar_res_info, tar_exp_info in zip(
                tar_res.getmembers(), tar_exp.getmembers()
            ):
                actual_file = tar_res.extractfile(tar_res_info)
                expected_file = tar_exp.extractfile(tar_exp_info)
                assert (actual_file is None) == (expected_file is None)
                if actual_file is not None and expected_file is not None:
                    assert actual_file.read() == expected_file.read()
    else:
        assert result == expected


@pytest.mark.parametrize("encoding", ["utf-8", "cp1251"])
def test_to_csv_compression_encoding_gcs(
    gcs_buffer, compression_only, encoding, compression_to_extension
):
    """
    Compression and encoding should with GCS.

    GH 35677 (to_csv, compression), GH 26124 (to_csv, encoding), and
    GH 32392 (read_csv, encoding)
    """
    df = DataFrame(
        1.1 * np.arange(120).reshape((30, 4)),
        columns=Index(list("ABCD")),
        index=Index([f"i-{i}" for i in range(30)]),
    )

    # reference of compressed and encoded file
    compression = {"method": compression_only}
    if compression_only == "gzip":
        compression["mtime"] = 1  # be reproducible
    buffer = BytesIO()
    df.to_csv(buffer, compression=compression, encoding=encoding, mode="wb")

    # write compressed file with explicit compression
    path_gcs = "gs://test/test.csv"
    df.to_csv(path_gcs, compression=compression, encoding=encoding)
    res = gcs_buffer.getvalue()
    expected = buffer.getvalue()
    assert_equal_zip_safe(res, expected, compression_only)

    read_df = read_csv(
        path_gcs, index_col=0, compression=compression_only, encoding=encoding
    )
    tm.assert_frame_equal(df, read_df)

    # write compressed file with implicit compression
    file_ext = compression_to_extension[compression_only]
    compression["method"] = "infer"
    path_gcs += f".{file_ext}"
    df.to_csv(path_gcs, compression=compression, encoding=encoding)

    res = gcs_buffer.getvalue()
    expected = buffer.getvalue()
    assert_equal_zip_safe(res, expected, compression_only)

    read_df = read_csv(path_gcs, index_col=0, compression="infer", encoding=encoding)
    tm.assert_frame_equal(df, read_df)


def test_to_parquet_gcs_new_file(monkeypatch, tmpdir):
    """Regression test for writing to a not-yet-existent GCS Parquet file."""
    pytest.importorskip("fastparquet")
    pytest.importorskip("gcsfs")

    from fsspec import AbstractFileSystem

    df1 = DataFrame(
        {
            "int": [1, 3],
            "float": [2.0, np.nan],
            "str": ["t", "s"],
            "dt": date_range("2018-06-18", periods=2),
        }
    )

    class MockGCSFileSystem(AbstractFileSystem):
        def open(self, path, mode="r", *args):
            if "w" not in mode:
                raise FileNotFoundError
            return open(os.path.join(tmpdir, "test.parquet"), mode, encoding="utf-8")

    monkeypatch.setattr("gcsfs.GCSFileSystem", MockGCSFileSystem)
    df1.to_parquet(
        "gs://test/test.csv", index=True, engine="fastparquet", compression=None
    )


@td.skip_if_installed("gcsfs")
def test_gcs_not_present_exception():
    with tm.external_error_raised(ImportError):
        read_csv("gs://test/test.csv")
