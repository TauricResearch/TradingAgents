"""
A verbatim copy (vendored) of the spec tests.
Taken from https://github.com/data-apis/dataframe-api
"""
import ctypes
import math

import pytest

import pandas as pd


@pytest.fixture
def df_from_dict():
    def maker(dct, is_categorical=False):
        df = pd.DataFrame(dct)
        return df.astype("category") if is_categorical else df

    return maker


@pytest.mark.parametrize(
    "test_data",
    [
        {"a": ["foo", "bar"], "b": ["baz", "qux"]},
        {"a": [1.5, 2.5, 3.5], "b": [9.2, 10.5, 11.8]},
        {"A": [1, 2, 3, 4], "B": [1, 2, 3, 4]},
    ],
    ids=["str_data", "float_data", "int_data"],
)
def test_only_one_dtype(test_data, df_from_dict):
    columns = list(test_data.keys())
    df = df_from_dict(test_data)
    dfX = df.__dataframe__()

    column_size = len(test_data[columns[0]])
    for column in columns:
        null_count = dfX.get_column_by_name(column).null_count
        assert null_count == 0
        assert isinstance(null_count, int)
        assert dfX.get_column_by_name(column).size() == column_size
        assert dfX.get_column_by_name(column).offset == 0


def test_mixed_dtypes(df_from_dict):
    df = df_from_dict(
        {
            "a": [1, 2, 3],  # dtype kind INT = 0
            "b": [3, 4, 5],  # dtype kind INT = 0
            "c": [1.5, 2.5, 3.5],  # dtype kind FLOAT = 2
            "d": [9, 10, 11],  # dtype kind INT = 0
            "e": [True, False, True],  # dtype kind BOOLEAN = 20
            "f": ["a", "", "c"],  # dtype kind STRING = 21
        }
    )
    dfX = df.__dataframe__()
    # for meanings of dtype[0] see the spec; we cannot import the spec here as this
    # file is expected to be vendored *anywhere*;
    # values for dtype[0] are explained above
    columns = {"a": 0, "b": 0, "c": 2, "d": 0, "e": 20, "f": 21}

    for column, kind in columns.items():
        colX = dfX.get_column_by_name(column)
        assert colX.null_count == 0
        assert isinstance(colX.null_count, int)
        assert colX.size() == 3
        assert colX.offset == 0

        assert colX.dtype[0] == kind

    assert dfX.get_column_by_name("c").dtype[1] == 64


def test_na_float(df_from_dict):
    df = df_from_dict({"a": [1.0, math.nan, 2.0]})
    dfX = df.__dataframe__()
    colX = dfX.get_column_by_name("a")
    assert colX.null_count == 1
    assert isinstance(colX.null_count, int)


def test_noncategorical(df_from_dict):
    df = df_from_dict({"a": [1, 2, 3]})
    dfX = df.__dataframe__()
    colX = dfX.get_column_by_name("a")
    with pytest.raises(TypeError, match=".*categorical.*"):
        colX.describe_categorical


def test_categorical(df_from_dict):
    df = df_from_dict(
        {"weekday": ["Mon", "Tue", "Mon", "Wed", "Mon", "Thu", "Fri", "Sat", "Sun"]},
        is_categorical=True,
    )

    colX = df.__dataframe__().get_column_by_name("weekday")
    categorical = colX.describe_categorical
    assert isinstance(categorical["is_ordered"], bool)
    assert isinstance(categorical["is_dictionary"], bool)


def test_dataframe(df_from_dict):
    df = df_from_dict(
        {"x": [True, True, False], "y": [1, 2, 0], "z": [9.2, 10.5, 11.8]}
    )
    dfX = df.__dataframe__()

    assert dfX.num_columns() == 3
    assert dfX.num_rows() == 3
    assert dfX.num_chunks() == 1
    assert list(dfX.column_names()) == ["x", "y", "z"]
    assert list(dfX.select_columns((0, 2)).column_names()) == list(
        dfX.select_columns_by_name(("x", "z")).column_names()
    )


@pytest.mark.parametrize(["size", "n_chunks"], [(10, 3), (12, 3), (12, 5)])
def test_df_get_chunks(size, n_chunks, df_from_dict):
    df = df_from_dict({"x": list(range(size))})
    dfX = df.__dataframe__()
    chunks = list(dfX.get_chunks(n_chunks))
    assert len(chunks) == n_chunks
    assert sum(chunk.num_rows() for chunk in chunks) == size


@pytest.mark.parametrize(["size", "n_chunks"], [(10, 3), (12, 3), (12, 5)])
def test_column_get_chunks(size, n_chunks, df_from_dict):
    df = df_from_dict({"x": list(range(size))})
    dfX = df.__dataframe__()
    chunks = list(dfX.get_column(0).get_chunks(n_chunks))
    assert len(chunks) == n_chunks
    assert sum(chunk.size() for chunk in chunks) == size


def test_get_columns(df_from_dict):
    df = df_from_dict({"a": [0, 1], "b": [2.5, 3.5]})
    dfX = df.__dataframe__()
    for colX in dfX.get_columns():
        assert colX.size() == 2
        assert colX.num_chunks() == 1
    # for meanings of dtype[0] see the spec; we cannot import the spec here as this
    # file is expected to be vendored *anywhere*
    assert dfX.get_column(0).dtype[0] == 0  # INT
    assert dfX.get_column(1).dtype[0] == 2  # FLOAT


def test_buffer(df_from_dict):
    arr = [0, 1, -1]
    df = df_from_dict({"a": arr})
    dfX = df.__dataframe__()
    colX = dfX.get_column(0)
    bufX = colX.get_buffers()

    dataBuf, dataDtype = bufX["data"]

    assert dataBuf.bufsize > 0
    assert dataBuf.ptr != 0
    device, _ = dataBuf.__dlpack_device__()

    # for meanings of dtype[0] see the spec; we cannot import the spec here as this
    # file is expected to be vendored *anywhere*
    assert dataDtype[0] == 0  # INT

    if device == 1:  # CPU-only as we're going to directly read memory here
        bitwidth = dataDtype[1]
        ctype = {
            8: ctypes.c_int8,
            16: ctypes.c_int16,
            32: ctypes.c_int32,
            64: ctypes.c_int64,
        }[bitwidth]

        for idx, truth in enumerate(arr):
            val = ctype.from_address(dataBuf.ptr + idx * (bitwidth // 8)).value
            assert val == truth, f"Buffer at index {idx} mismatch"
