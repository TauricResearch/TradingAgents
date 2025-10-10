"""
manage legacy pickle tests

How to add pickle tests:

1. Install pandas version intended to output the pickle.

2. Execute "generate_legacy_storage_files.py" to create the pickle.
$ python generate_legacy_storage_files.py <output_dir> pickle

3. Move the created pickle to "data/legacy_pickle/<version>" directory.
"""
from __future__ import annotations

from array import array
import bz2
import datetime
import functools
from functools import partial
import gzip
import io
import os
from pathlib import Path
import pickle
import shutil
import tarfile
from typing import Any
import uuid
import zipfile

import numpy as np
import pytest

from pandas.compat import (
    get_lzma_file,
    is_platform_little_endian,
)
from pandas.compat._optional import import_optional_dependency
from pandas.compat.compressors import flatten_buffer
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    Series,
    period_range,
)
import pandas._testing as tm
from pandas.tests.io.generate_legacy_storage_files import create_pickle_data

import pandas.io.common as icom
from pandas.tseries.offsets import (
    Day,
    MonthEnd,
)


# ---------------------
# comparison functions
# ---------------------
def compare_element(result, expected, typ):
    if isinstance(expected, Index):
        tm.assert_index_equal(expected, result)
        return

    if typ.startswith("sp_"):
        tm.assert_equal(result, expected)
    elif typ == "timestamp":
        if expected is pd.NaT:
            assert result is pd.NaT
        else:
            assert result == expected
    else:
        comparator = getattr(tm, f"assert_{typ}_equal", tm.assert_almost_equal)
        comparator(result, expected)


# ---------------------
# tests
# ---------------------


@pytest.mark.parametrize(
    "data",
    [
        b"123",
        b"123456",
        bytearray(b"123"),
        memoryview(b"123"),
        pickle.PickleBuffer(b"123"),
        array("I", [1, 2, 3]),
        memoryview(b"123456").cast("B", (3, 2)),
        memoryview(b"123456").cast("B", (3, 2))[::2],
        np.arange(12).reshape((3, 4), order="C"),
        np.arange(12).reshape((3, 4), order="F"),
        np.arange(12).reshape((3, 4), order="C")[:, ::2],
    ],
)
def test_flatten_buffer(data):
    result = flatten_buffer(data)
    expected = memoryview(data).tobytes("A")
    assert result == expected
    if isinstance(data, (bytes, bytearray)):
        assert result is data
    elif isinstance(result, memoryview):
        assert result.ndim == 1
        assert result.format == "B"
        assert result.contiguous
        assert result.shape == (result.nbytes,)


def test_pickles(datapath):
    if not is_platform_little_endian():
        pytest.skip("known failure on non-little endian")

    # For loop for compat with --strict-data-files
    for legacy_pickle in Path(__file__).parent.glob("data/legacy_pickle/*/*.p*kl*"):
        legacy_pickle = datapath(legacy_pickle)

        data = pd.read_pickle(legacy_pickle)

        for typ, dv in data.items():
            for dt, result in dv.items():
                expected = data[typ][dt]

                if typ == "series" and dt == "ts":
                    # GH 7748
                    tm.assert_series_equal(result, expected)
                    assert result.index.freq == expected.index.freq
                    assert not result.index.freq.normalize
                    tm.assert_series_equal(result > 0, expected > 0)

                    # GH 9291
                    freq = result.index.freq
                    assert freq + Day(1) == Day(2)

                    res = freq + pd.Timedelta(hours=1)
                    assert isinstance(res, pd.Timedelta)
                    assert res == pd.Timedelta(days=1, hours=1)

                    res = freq + pd.Timedelta(nanoseconds=1)
                    assert isinstance(res, pd.Timedelta)
                    assert res == pd.Timedelta(days=1, nanoseconds=1)
                elif typ == "index" and dt == "period":
                    tm.assert_index_equal(result, expected)
                    assert isinstance(result.freq, MonthEnd)
                    assert result.freq == MonthEnd()
                    assert result.freqstr == "M"
                    tm.assert_index_equal(result.shift(2), expected.shift(2))
                elif typ == "series" and dt in ("dt_tz", "cat"):
                    tm.assert_series_equal(result, expected)
                elif typ == "frame" and dt in (
                    "dt_mixed_tzs",
                    "cat_onecol",
                    "cat_and_float",
                ):
                    tm.assert_frame_equal(result, expected)
                else:
                    compare_element(result, expected, typ)


def python_pickler(obj, path):
    with open(path, "wb") as fh:
        pickle.dump(obj, fh, protocol=-1)


def python_unpickler(path):
    with open(path, "rb") as fh:
        fh.seek(0)
        return pickle.load(fh)


def flatten(data: dict) -> list[tuple[str, Any]]:
    """Flatten create_pickle_data"""
    return [
        (typ, example)
        for typ, examples in data.items()
        for example in examples.values()
    ]


@pytest.mark.parametrize(
    "pickle_writer",
    [
        pytest.param(python_pickler, id="python"),
        pytest.param(pd.to_pickle, id="pandas_proto_default"),
        pytest.param(
            functools.partial(pd.to_pickle, protocol=pickle.HIGHEST_PROTOCOL),
            id="pandas_proto_highest",
        ),
        pytest.param(functools.partial(pd.to_pickle, protocol=4), id="pandas_proto_4"),
        pytest.param(
            functools.partial(pd.to_pickle, protocol=5),
            id="pandas_proto_5",
        ),
    ],
)
@pytest.mark.parametrize("writer", [pd.to_pickle, python_pickler])
@pytest.mark.parametrize("typ, expected", flatten(create_pickle_data()))
def test_round_trip_current(typ, expected, pickle_writer, writer):
    with tm.ensure_clean() as path:
        # test writing with each pickler
        pickle_writer(expected, path)

        # test reading with each unpickler
        result = pd.read_pickle(path)
        compare_element(result, expected, typ)

        result = python_unpickler(path)
        compare_element(result, expected, typ)

        # and the same for file objects (GH 35679)
        with open(path, mode="wb") as handle:
            writer(expected, path)
            handle.seek(0)  # shouldn't close file handle
        with open(path, mode="rb") as handle:
            result = pd.read_pickle(handle)
            handle.seek(0)  # shouldn't close file handle
        compare_element(result, expected, typ)


def test_pickle_path_pathlib():
    df = DataFrame(
        1.1 * np.arange(120).reshape((30, 4)),
        columns=Index(list("ABCD"), dtype=object),
        index=Index([f"i-{i}" for i in range(30)], dtype=object),
    )
    result = tm.round_trip_pathlib(df.to_pickle, pd.read_pickle)
    tm.assert_frame_equal(df, result)


def test_pickle_path_localpath():
    df = DataFrame(
        1.1 * np.arange(120).reshape((30, 4)),
        columns=Index(list("ABCD"), dtype=object),
        index=Index([f"i-{i}" for i in range(30)], dtype=object),
    )
    result = tm.round_trip_localpath(df.to_pickle, pd.read_pickle)
    tm.assert_frame_equal(df, result)


# ---------------------
# test pickle compression
# ---------------------


@pytest.fixture
def get_random_path():
    return f"__{uuid.uuid4()}__.pickle"


class TestCompression:
    _extension_to_compression = icom.extension_to_compression

    def compress_file(self, src_path, dest_path, compression):
        if compression is None:
            shutil.copyfile(src_path, dest_path)
            return

        if compression == "gzip":
            f = gzip.open(dest_path, "w")
        elif compression == "bz2":
            f = bz2.BZ2File(dest_path, "w")
        elif compression == "zip":
            with zipfile.ZipFile(dest_path, "w", compression=zipfile.ZIP_DEFLATED) as f:
                f.write(src_path, os.path.basename(src_path))
        elif compression == "tar":
            with open(src_path, "rb") as fh:
                with tarfile.open(dest_path, mode="w") as tar:
                    tarinfo = tar.gettarinfo(src_path, os.path.basename(src_path))
                    tar.addfile(tarinfo, fh)
        elif compression == "xz":
            f = get_lzma_file()(dest_path, "w")
        elif compression == "zstd":
            f = import_optional_dependency("zstandard").open(dest_path, "wb")
        else:
            msg = f"Unrecognized compression type: {compression}"
            raise ValueError(msg)

        if compression not in ["zip", "tar"]:
            with open(src_path, "rb") as fh:
                with f:
                    f.write(fh.read())

    def test_write_explicit(self, compression, get_random_path):
        base = get_random_path
        path1 = base + ".compressed"
        path2 = base + ".raw"

        with tm.ensure_clean(path1) as p1, tm.ensure_clean(path2) as p2:
            df = DataFrame(
                1.1 * np.arange(120).reshape((30, 4)),
                columns=Index(list("ABCD"), dtype=object),
                index=Index([f"i-{i}" for i in range(30)], dtype=object),
            )

            # write to compressed file
            df.to_pickle(p1, compression=compression)

            # decompress
            with tm.decompress_file(p1, compression=compression) as f:
                with open(p2, "wb") as fh:
                    fh.write(f.read())

            # read decompressed file
            df2 = pd.read_pickle(p2, compression=None)

            tm.assert_frame_equal(df, df2)

    @pytest.mark.parametrize("compression", ["", "None", "bad", "7z"])
    def test_write_explicit_bad(self, compression, get_random_path):
        with pytest.raises(ValueError, match="Unrecognized compression type"):
            with tm.ensure_clean(get_random_path) as path:
                df = DataFrame(
                    1.1 * np.arange(120).reshape((30, 4)),
                    columns=Index(list("ABCD"), dtype=object),
                    index=Index([f"i-{i}" for i in range(30)], dtype=object),
                )
                df.to_pickle(path, compression=compression)

    def test_write_infer(self, compression_ext, get_random_path):
        base = get_random_path
        path1 = base + compression_ext
        path2 = base + ".raw"
        compression = self._extension_to_compression.get(compression_ext.lower())

        with tm.ensure_clean(path1) as p1, tm.ensure_clean(path2) as p2:
            df = DataFrame(
                1.1 * np.arange(120).reshape((30, 4)),
                columns=Index(list("ABCD"), dtype=object),
                index=Index([f"i-{i}" for i in range(30)], dtype=object),
            )

            # write to compressed file by inferred compression method
            df.to_pickle(p1)

            # decompress
            with tm.decompress_file(p1, compression=compression) as f:
                with open(p2, "wb") as fh:
                    fh.write(f.read())

            # read decompressed file
            df2 = pd.read_pickle(p2, compression=None)

            tm.assert_frame_equal(df, df2)

    def test_read_explicit(self, compression, get_random_path):
        base = get_random_path
        path1 = base + ".raw"
        path2 = base + ".compressed"

        with tm.ensure_clean(path1) as p1, tm.ensure_clean(path2) as p2:
            df = DataFrame(
                1.1 * np.arange(120).reshape((30, 4)),
                columns=Index(list("ABCD"), dtype=object),
                index=Index([f"i-{i}" for i in range(30)], dtype=object),
            )

            # write to uncompressed file
            df.to_pickle(p1, compression=None)

            # compress
            self.compress_file(p1, p2, compression=compression)

            # read compressed file
            df2 = pd.read_pickle(p2, compression=compression)
            tm.assert_frame_equal(df, df2)

    def test_read_infer(self, compression_ext, get_random_path):
        base = get_random_path
        path1 = base + ".raw"
        path2 = base + compression_ext
        compression = self._extension_to_compression.get(compression_ext.lower())

        with tm.ensure_clean(path1) as p1, tm.ensure_clean(path2) as p2:
            df = DataFrame(
                1.1 * np.arange(120).reshape((30, 4)),
                columns=Index(list("ABCD"), dtype=object),
                index=Index([f"i-{i}" for i in range(30)], dtype=object),
            )

            # write to uncompressed file
            df.to_pickle(p1, compression=None)

            # compress
            self.compress_file(p1, p2, compression=compression)

            # read compressed file by inferred compression method
            df2 = pd.read_pickle(p2)
            tm.assert_frame_equal(df, df2)


# ---------------------
# test pickle compression
# ---------------------


class TestProtocol:
    @pytest.mark.parametrize("protocol", [-1, 0, 1, 2])
    def test_read(self, protocol, get_random_path):
        with tm.ensure_clean(get_random_path) as path:
            df = DataFrame(
                1.1 * np.arange(120).reshape((30, 4)),
                columns=Index(list("ABCD"), dtype=object),
                index=Index([f"i-{i}" for i in range(30)], dtype=object),
            )
            df.to_pickle(path, protocol=protocol)
            df2 = pd.read_pickle(path)
            tm.assert_frame_equal(df, df2)


@pytest.mark.parametrize(
    ["pickle_file", "excols"],
    [
        ("test_py27.pkl", Index(["a", "b", "c"], dtype=object)),
        (
            "test_mi_py27.pkl",
            pd.MultiIndex(
                [
                    Index(["a", "b", "c"], dtype=object),
                    Index(["A", "B", "C"], dtype=object),
                ],
                [np.array([0, 1, 2]), np.array([0, 1, 2])],
            ),
        ),
    ],
)
def test_unicode_decode_error(datapath, pickle_file, excols):
    # pickle file written with py27, should be readable without raising
    #  UnicodeDecodeError, see GH#28645 and GH#31988
    path = datapath("io", "data", "pickle", pickle_file)
    df = pd.read_pickle(path)

    # just test the columns are correct since the values are random
    tm.assert_index_equal(df.columns, excols)


# ---------------------
# tests for buffer I/O
# ---------------------


def test_pickle_buffer_roundtrip():
    with tm.ensure_clean() as path:
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=Index([f"i-{i}" for i in range(30)], dtype=object),
        )
        with open(path, "wb") as fh:
            df.to_pickle(fh)
        with open(path, "rb") as fh:
            result = pd.read_pickle(fh)
        tm.assert_frame_equal(df, result)


# ---------------------
# tests for URL I/O
# ---------------------


@pytest.mark.parametrize(
    "mockurl", ["http://url.com", "ftp://test.com", "http://gzip.com"]
)
def test_pickle_generalurl_read(monkeypatch, mockurl):
    def python_pickler(obj, path):
        with open(path, "wb") as fh:
            pickle.dump(obj, fh, protocol=-1)

    class MockReadResponse:
        def __init__(self, path) -> None:
            self.file = open(path, "rb")
            if "gzip" in path:
                self.headers = {"Content-Encoding": "gzip"}
            else:
                self.headers = {"Content-Encoding": ""}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

        def read(self):
            return self.file.read()

        def close(self):
            return self.file.close()

    with tm.ensure_clean() as path:

        def mock_urlopen_read(*args, **kwargs):
            return MockReadResponse(path)

        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=Index([f"i-{i}" for i in range(30)], dtype=object),
        )
        python_pickler(df, path)
        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen_read)
        result = pd.read_pickle(mockurl)
        tm.assert_frame_equal(df, result)


def test_pickle_fsspec_roundtrip():
    pytest.importorskip("fsspec")
    with tm.ensure_clean():
        mockurl = "memory://mockfile"
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=Index([f"i-{i}" for i in range(30)], dtype=object),
        )
        df.to_pickle(mockurl)
        result = pd.read_pickle(mockurl)
        tm.assert_frame_equal(df, result)


class MyTz(datetime.tzinfo):
    def __init__(self) -> None:
        pass


def test_read_pickle_with_subclass():
    # GH 12163
    expected = Series(dtype=object), MyTz()
    result = tm.round_trip_pickle(expected)

    tm.assert_series_equal(result[0], expected[0])
    assert isinstance(result[1], MyTz)


def test_pickle_binary_object_compression(compression):
    """
    Read/write from binary file-objects w/wo compression.

    GH 26237, GH 29054, and GH 29570
    """
    df = DataFrame(
        1.1 * np.arange(120).reshape((30, 4)),
        columns=Index(list("ABCD"), dtype=object),
        index=Index([f"i-{i}" for i in range(30)], dtype=object),
    )

    # reference for compression
    with tm.ensure_clean() as path:
        df.to_pickle(path, compression=compression)
        reference = Path(path).read_bytes()

    # write
    buffer = io.BytesIO()
    df.to_pickle(buffer, compression=compression)
    buffer.seek(0)

    # gzip  and zip safe the filename: cannot compare the compressed content
    assert buffer.getvalue() == reference or compression in ("gzip", "zip", "tar")

    # read
    read_df = pd.read_pickle(buffer, compression=compression)
    buffer.seek(0)
    tm.assert_frame_equal(df, read_df)


def test_pickle_dataframe_with_multilevel_index(
    multiindex_year_month_day_dataframe_random_data,
    multiindex_dataframe_random_data,
):
    ymd = multiindex_year_month_day_dataframe_random_data
    frame = multiindex_dataframe_random_data

    def _test_roundtrip(frame):
        unpickled = tm.round_trip_pickle(frame)
        tm.assert_frame_equal(frame, unpickled)

    _test_roundtrip(frame)
    _test_roundtrip(frame.T)
    _test_roundtrip(ymd)
    _test_roundtrip(ymd.T)


def test_pickle_timeseries_periodindex():
    # GH#2891
    prng = period_range("1/1/2011", "1/1/2012", freq="M")
    ts = Series(np.random.default_rng(2).standard_normal(len(prng)), prng)
    new_ts = tm.round_trip_pickle(ts)
    assert new_ts.index.freqstr == "M"


@pytest.mark.parametrize(
    "name", [777, 777.0, "name", datetime.datetime(2001, 11, 11), (1, 2)]
)
def test_pickle_preserve_name(name):
    unpickled = tm.round_trip_pickle(Series(np.arange(10, dtype=np.float64), name=name))
    assert unpickled.name == name


def test_pickle_datetimes(datetime_series):
    unp_ts = tm.round_trip_pickle(datetime_series)
    tm.assert_series_equal(unp_ts, datetime_series)


def test_pickle_strings(string_series):
    unp_series = tm.round_trip_pickle(string_series)
    tm.assert_series_equal(unp_series, string_series)


@td.skip_array_manager_invalid_test
def test_pickle_preserves_block_ndim():
    # GH#37631
    ser = Series(list("abc")).astype("category").iloc[[0]]
    res = tm.round_trip_pickle(ser)

    assert res._mgr.blocks[0].ndim == 1
    assert res._mgr.blocks[0].shape == (1,)

    # GH#37631 OP issue was about indexing, underlying problem was pickle
    tm.assert_series_equal(res[[True]], ser)


@pytest.mark.parametrize("protocol", [pickle.DEFAULT_PROTOCOL, pickle.HIGHEST_PROTOCOL])
def test_pickle_big_dataframe_compression(protocol, compression):
    # GH#39002
    df = DataFrame(range(100000))
    result = tm.round_trip_pathlib(
        partial(df.to_pickle, protocol=protocol, compression=compression),
        partial(pd.read_pickle, compression=compression),
    )
    tm.assert_frame_equal(df, result)


def test_pickle_frame_v124_unpickle_130(datapath):
    # GH#42345 DataFrame created in 1.2.x, unpickle in 1.3.x
    path = datapath(
        Path(__file__).parent,
        "data",
        "legacy_pickle",
        "1.2.4",
        "empty_frame_v1_2_4-GH#42345.pkl",
    )
    with open(path, "rb") as fd:
        df = pickle.load(fd)

    expected = DataFrame(index=[], columns=[])
    tm.assert_frame_equal(df, expected)


def test_pickle_pos_args_deprecation():
    # GH-54229
    df = DataFrame({"a": [1, 2, 3]})
    msg = (
        r"Starting with pandas version 3.0 all arguments of to_pickle except for the "
        r"argument 'path' will be keyword-only."
    )
    with tm.assert_produces_warning(FutureWarning, match=msg):
        buffer = io.BytesIO()
        df.to_pickle(buffer, "infer")
