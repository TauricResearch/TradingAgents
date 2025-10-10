"""
Tests for the pandas custom headers in http(s) requests
"""
from functools import partial
import gzip
from io import BytesIO

import pytest

from pandas._config import using_string_dtype

import pandas.util._test_decorators as td

import pandas as pd
import pandas._testing as tm

pytestmark = [
    pytest.mark.single_cpu,
    pytest.mark.network,
    pytest.mark.filterwarnings(
        "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
    ),
]


def gzip_bytes(response_bytes):
    with BytesIO() as bio:
        with gzip.GzipFile(fileobj=bio, mode="w") as zipper:
            zipper.write(response_bytes)
        return bio.getvalue()


def csv_responder(df):
    return df.to_csv(index=False).encode("utf-8")


def gz_csv_responder(df):
    return gzip_bytes(csv_responder(df))


def json_responder(df):
    return df.to_json().encode("utf-8")


def gz_json_responder(df):
    return gzip_bytes(json_responder(df))


def html_responder(df):
    return df.to_html(index=False).encode("utf-8")


def parquetpyarrow_reponder(df):
    return df.to_parquet(index=False, engine="pyarrow")


def parquetfastparquet_responder(df):
    # the fastparquet engine doesn't like to write to a buffer
    # it can do it via the open_with function being set appropriately
    # however it automatically calls the close method and wipes the buffer
    # so just overwrite that attribute on this instance to not do that

    # protected by an importorskip in the respective test
    import fsspec

    df.to_parquet(
        "memory://fastparquet_user_agent.parquet",
        index=False,
        engine="fastparquet",
        compression=None,
    )
    with fsspec.open("memory://fastparquet_user_agent.parquet", "rb") as f:
        return f.read()


def pickle_respnder(df):
    with BytesIO() as bio:
        df.to_pickle(bio)
        return bio.getvalue()


def stata_responder(df):
    with BytesIO() as bio:
        df.to_stata(bio, write_index=False)
        return bio.getvalue()


@pytest.mark.parametrize(
    "responder, read_method",
    [
        (csv_responder, pd.read_csv),
        (json_responder, pd.read_json),
        (
            html_responder,
            lambda *args, **kwargs: pd.read_html(*args, **kwargs)[0],
        ),
        pytest.param(
            parquetpyarrow_reponder,
            partial(pd.read_parquet, engine="pyarrow"),
            marks=td.skip_if_no("pyarrow"),
        ),
        pytest.param(
            parquetfastparquet_responder,
            partial(pd.read_parquet, engine="fastparquet"),
            # TODO(ArrayManager) fastparquet
            marks=[
                td.skip_if_no("fastparquet"),
                td.skip_if_no("fsspec"),
                td.skip_array_manager_not_yet_implemented,
                pytest.mark.xfail(using_string_dtype(), reason="TODO(infer_string"),
            ],
        ),
        (pickle_respnder, pd.read_pickle),
        (stata_responder, pd.read_stata),
        (gz_csv_responder, pd.read_csv),
        (gz_json_responder, pd.read_json),
    ],
)
@pytest.mark.parametrize(
    "storage_options",
    [
        None,
        {"User-Agent": "foo"},
        {"User-Agent": "foo", "Auth": "bar"},
    ],
)
def test_request_headers(responder, read_method, httpserver, storage_options):
    expected = pd.DataFrame({"a": ["b"]})
    default_headers = ["Accept-Encoding", "Host", "Connection", "User-Agent"]
    if "gz" in responder.__name__:
        extra = {"Content-Encoding": "gzip"}
        if storage_options is None:
            storage_options = extra
        else:
            storage_options |= extra
    else:
        extra = None
    expected_headers = set(default_headers).union(
        storage_options.keys() if storage_options else []
    )
    httpserver.serve_content(content=responder(expected), headers=extra)
    result = read_method(httpserver.url, storage_options=storage_options)
    tm.assert_frame_equal(result, expected)

    request_headers = dict(httpserver.requests[0].headers)
    for header in expected_headers:
        exp = request_headers.pop(header)
        if storage_options and header in storage_options:
            assert exp == storage_options[header]
    # No extra headers added
    assert not request_headers


@pytest.mark.parametrize(
    "engine",
    [
        "pyarrow",
        "fastparquet",
    ],
)
def test_to_parquet_to_disk_with_storage_options(engine):
    headers = {
        "User-Agent": "custom",
        "Auth": "other_custom",
    }

    pytest.importorskip(engine)

    true_df = pd.DataFrame({"column_name": ["column_value"]})
    msg = (
        "storage_options passed with file object or non-fsspec file path|"
        "storage_options passed with buffer, or non-supported URL"
    )
    with pytest.raises(ValueError, match=msg):
        true_df.to_parquet("/tmp/junk.parquet", storage_options=headers, engine=engine)
