import ctypes

import pytest

import pandas.util._test_decorators as td

import pandas as pd

pa = pytest.importorskip("pyarrow")


@td.skip_if_no("pyarrow", min_version="14.0")
def test_dataframe_arrow_interface(using_infer_string):
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["a", "b", "c"]})

    capsule = df.__arrow_c_stream__()
    assert (
        ctypes.pythonapi.PyCapsule_IsValid(
            ctypes.py_object(capsule), b"arrow_array_stream"
        )
        == 1
    )

    table = pa.table(df)
    string_type = pa.large_string() if using_infer_string else pa.string()
    expected = pa.table({"a": [1, 2, 3], "b": pa.array(["a", "b", "c"], string_type)})
    assert table.equals(expected)

    schema = pa.schema([("a", pa.int8()), ("b", pa.string())])
    table = pa.table(df, schema=schema)
    expected = expected.cast(schema)
    assert table.equals(expected)


@td.skip_if_no("pyarrow", min_version="15.0")
def test_dataframe_to_arrow(using_infer_string):
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["a", "b", "c"]})

    table = pa.RecordBatchReader.from_stream(df).read_all()
    string_type = pa.large_string() if using_infer_string else pa.string()
    expected = pa.table({"a": [1, 2, 3], "b": pa.array(["a", "b", "c"], string_type)})
    assert table.equals(expected)

    schema = pa.schema([("a", pa.int8()), ("b", pa.string())])
    table = pa.RecordBatchReader.from_stream(df, schema=schema).read_all()
    expected = expected.cast(schema)
    assert table.equals(expected)
