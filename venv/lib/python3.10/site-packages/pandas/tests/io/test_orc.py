""" test orc compat """
import datetime
from decimal import Decimal
from io import BytesIO
import os
import pathlib

import numpy as np
import pytest

import pandas as pd
from pandas import read_orc
import pandas._testing as tm
from pandas.core.arrays import StringArray

pytest.importorskip("pyarrow.orc")

import pyarrow as pa

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)


@pytest.fixture
def dirpath(datapath):
    return datapath("io", "data", "orc")


@pytest.fixture(
    params=[
        np.array([1, 20], dtype="uint64"),
        pd.Series(["a", "b", "a"], dtype="category"),
        [pd.Interval(left=0, right=2), pd.Interval(left=0, right=5)],
        [pd.Period("2022-01-03", freq="D"), pd.Period("2022-01-04", freq="D")],
    ]
)
def orc_writer_dtypes_not_supported(request):
    # Examples of dataframes with dtypes for which conversion to ORC
    # hasn't been implemented yet, that is, Category, unsigned integers,
    # interval, period and sparse.
    return pd.DataFrame({"unimpl": request.param})


def test_orc_reader_empty(dirpath, using_infer_string):
    columns = [
        "boolean1",
        "byte1",
        "short1",
        "int1",
        "long1",
        "float1",
        "double1",
        "bytes1",
        "string1",
    ]
    dtypes = [
        "bool",
        "int8",
        "int16",
        "int32",
        "int64",
        "float32",
        "float64",
        "object",
        "str" if using_infer_string else "object",
    ]
    expected = pd.DataFrame(index=pd.RangeIndex(0))
    for colname, dtype in zip(columns, dtypes):
        expected[colname] = pd.Series(dtype=dtype)
    expected.columns = expected.columns.astype("str")

    inputfile = os.path.join(dirpath, "TestOrcFile.emptyFile.orc")
    got = read_orc(inputfile, columns=columns)

    tm.assert_equal(expected, got)


def test_orc_reader_basic(dirpath):
    data = {
        "boolean1": np.array([False, True], dtype="bool"),
        "byte1": np.array([1, 100], dtype="int8"),
        "short1": np.array([1024, 2048], dtype="int16"),
        "int1": np.array([65536, 65536], dtype="int32"),
        "long1": np.array([9223372036854775807, 9223372036854775807], dtype="int64"),
        "float1": np.array([1.0, 2.0], dtype="float32"),
        "double1": np.array([-15.0, -5.0], dtype="float64"),
        "bytes1": np.array([b"\x00\x01\x02\x03\x04", b""], dtype="object"),
        "string1": np.array(["hi", "bye"], dtype="object"),
    }
    expected = pd.DataFrame.from_dict(data)

    inputfile = os.path.join(dirpath, "TestOrcFile.test1.orc")
    got = read_orc(inputfile, columns=data.keys())

    tm.assert_equal(expected, got)


def test_orc_reader_decimal(dirpath):
    # Only testing the first 10 rows of data
    data = {
        "_col0": np.array(
            [
                Decimal("-1000.50000"),
                Decimal("-999.60000"),
                Decimal("-998.70000"),
                Decimal("-997.80000"),
                Decimal("-996.90000"),
                Decimal("-995.10000"),
                Decimal("-994.11000"),
                Decimal("-993.12000"),
                Decimal("-992.13000"),
                Decimal("-991.14000"),
            ],
            dtype="object",
        )
    }
    expected = pd.DataFrame.from_dict(data)

    inputfile = os.path.join(dirpath, "TestOrcFile.decimal.orc")
    got = read_orc(inputfile).iloc[:10]

    tm.assert_equal(expected, got)


def test_orc_reader_date_low(dirpath):
    data = {
        "time": np.array(
            [
                "1900-05-05 12:34:56.100000",
                "1900-05-05 12:34:56.100100",
                "1900-05-05 12:34:56.100200",
                "1900-05-05 12:34:56.100300",
                "1900-05-05 12:34:56.100400",
                "1900-05-05 12:34:56.100500",
                "1900-05-05 12:34:56.100600",
                "1900-05-05 12:34:56.100700",
                "1900-05-05 12:34:56.100800",
                "1900-05-05 12:34:56.100900",
            ],
            dtype="datetime64[ns]",
        ),
        "date": np.array(
            [
                datetime.date(1900, 12, 25),
                datetime.date(1900, 12, 25),
                datetime.date(1900, 12, 25),
                datetime.date(1900, 12, 25),
                datetime.date(1900, 12, 25),
                datetime.date(1900, 12, 25),
                datetime.date(1900, 12, 25),
                datetime.date(1900, 12, 25),
                datetime.date(1900, 12, 25),
                datetime.date(1900, 12, 25),
            ],
            dtype="object",
        ),
    }
    expected = pd.DataFrame.from_dict(data)

    inputfile = os.path.join(dirpath, "TestOrcFile.testDate1900.orc")
    got = read_orc(inputfile).iloc[:10]

    tm.assert_equal(expected, got)


def test_orc_reader_date_high(dirpath):
    data = {
        "time": np.array(
            [
                "2038-05-05 12:34:56.100000",
                "2038-05-05 12:34:56.100100",
                "2038-05-05 12:34:56.100200",
                "2038-05-05 12:34:56.100300",
                "2038-05-05 12:34:56.100400",
                "2038-05-05 12:34:56.100500",
                "2038-05-05 12:34:56.100600",
                "2038-05-05 12:34:56.100700",
                "2038-05-05 12:34:56.100800",
                "2038-05-05 12:34:56.100900",
            ],
            dtype="datetime64[ns]",
        ),
        "date": np.array(
            [
                datetime.date(2038, 12, 25),
                datetime.date(2038, 12, 25),
                datetime.date(2038, 12, 25),
                datetime.date(2038, 12, 25),
                datetime.date(2038, 12, 25),
                datetime.date(2038, 12, 25),
                datetime.date(2038, 12, 25),
                datetime.date(2038, 12, 25),
                datetime.date(2038, 12, 25),
                datetime.date(2038, 12, 25),
            ],
            dtype="object",
        ),
    }
    expected = pd.DataFrame.from_dict(data)

    inputfile = os.path.join(dirpath, "TestOrcFile.testDate2038.orc")
    got = read_orc(inputfile).iloc[:10]

    tm.assert_equal(expected, got)


def test_orc_reader_snappy_compressed(dirpath):
    data = {
        "int1": np.array(
            [
                -1160101563,
                1181413113,
                2065821249,
                -267157795,
                172111193,
                1752363137,
                1406072123,
                1911809390,
                -1308542224,
                -467100286,
            ],
            dtype="int32",
        ),
        "string1": np.array(
            [
                "f50dcb8",
                "382fdaaa",
                "90758c6",
                "9e8caf3f",
                "ee97332b",
                "d634da1",
                "2bea4396",
                "d67d89e8",
                "ad71007e",
                "e8c82066",
            ],
            dtype="object",
        ),
    }
    expected = pd.DataFrame.from_dict(data)

    inputfile = os.path.join(dirpath, "TestOrcFile.testSnappy.orc")
    got = read_orc(inputfile).iloc[:10]

    tm.assert_equal(expected, got)


def test_orc_roundtrip_file(dirpath):
    # GH44554
    # PyArrow gained ORC write support with the current argument order
    pytest.importorskip("pyarrow")

    data = {
        "boolean1": np.array([False, True], dtype="bool"),
        "byte1": np.array([1, 100], dtype="int8"),
        "short1": np.array([1024, 2048], dtype="int16"),
        "int1": np.array([65536, 65536], dtype="int32"),
        "long1": np.array([9223372036854775807, 9223372036854775807], dtype="int64"),
        "float1": np.array([1.0, 2.0], dtype="float32"),
        "double1": np.array([-15.0, -5.0], dtype="float64"),
        "bytes1": np.array([b"\x00\x01\x02\x03\x04", b""], dtype="object"),
        "string1": np.array(["hi", "bye"], dtype="object"),
    }
    expected = pd.DataFrame.from_dict(data)

    with tm.ensure_clean() as path:
        expected.to_orc(path)
        got = read_orc(path)

        tm.assert_equal(expected, got)


def test_orc_roundtrip_bytesio():
    # GH44554
    # PyArrow gained ORC write support with the current argument order
    pytest.importorskip("pyarrow")

    data = {
        "boolean1": np.array([False, True], dtype="bool"),
        "byte1": np.array([1, 100], dtype="int8"),
        "short1": np.array([1024, 2048], dtype="int16"),
        "int1": np.array([65536, 65536], dtype="int32"),
        "long1": np.array([9223372036854775807, 9223372036854775807], dtype="int64"),
        "float1": np.array([1.0, 2.0], dtype="float32"),
        "double1": np.array([-15.0, -5.0], dtype="float64"),
        "bytes1": np.array([b"\x00\x01\x02\x03\x04", b""], dtype="object"),
        "string1": np.array(["hi", "bye"], dtype="object"),
    }
    expected = pd.DataFrame.from_dict(data)

    bytes = expected.to_orc()
    got = read_orc(BytesIO(bytes))

    tm.assert_equal(expected, got)


def test_orc_writer_dtypes_not_supported(orc_writer_dtypes_not_supported):
    # GH44554
    # PyArrow gained ORC write support with the current argument order
    pytest.importorskip("pyarrow")

    msg = "The dtype of one or more columns is not supported yet."
    with pytest.raises(NotImplementedError, match=msg):
        orc_writer_dtypes_not_supported.to_orc()


def test_orc_dtype_backend_pyarrow(using_infer_string):
    pytest.importorskip("pyarrow")
    df = pd.DataFrame(
        {
            "string": list("abc"),
            "string_with_nan": ["a", np.nan, "c"],
            "string_with_none": ["a", None, "c"],
            "bytes": [b"foo", b"bar", None],
            "int": list(range(1, 4)),
            "float": np.arange(4.0, 7.0, dtype="float64"),
            "float_with_nan": [2.0, np.nan, 3.0],
            "bool": [True, False, True],
            "bool_with_na": [True, False, None],
            "datetime": pd.date_range("20130101", periods=3),
            "datetime_with_nat": [
                pd.Timestamp("20130101"),
                pd.NaT,
                pd.Timestamp("20130103"),
            ],
        }
    )

    bytes_data = df.copy().to_orc()
    result = read_orc(BytesIO(bytes_data), dtype_backend="pyarrow")

    expected = pd.DataFrame(
        {
            col: pd.arrays.ArrowExtensionArray(pa.array(df[col], from_pandas=True))
            for col in df.columns
        }
    )
    if using_infer_string:
        # ORC does not preserve distinction between string and large string
        # -> the default large string comes back as string
        string_dtype = pd.ArrowDtype(pa.string())
        expected["string"] = expected["string"].astype(string_dtype)
        expected["string_with_nan"] = expected["string_with_nan"].astype(string_dtype)
        expected["string_with_none"] = expected["string_with_none"].astype(string_dtype)

    tm.assert_frame_equal(result, expected)


def test_orc_dtype_backend_numpy_nullable():
    # GH#50503
    pytest.importorskip("pyarrow")
    df = pd.DataFrame(
        {
            "string": list("abc"),
            "string_with_nan": ["a", np.nan, "c"],
            "string_with_none": ["a", None, "c"],
            "int": list(range(1, 4)),
            "int_with_nan": pd.Series([1, pd.NA, 3], dtype="Int64"),
            "na_only": pd.Series([pd.NA, pd.NA, pd.NA], dtype="Int64"),
            "float": np.arange(4.0, 7.0, dtype="float64"),
            "float_with_nan": [2.0, np.nan, 3.0],
            "bool": [True, False, True],
            "bool_with_na": [True, False, None],
        }
    )

    bytes_data = df.copy().to_orc()
    result = read_orc(BytesIO(bytes_data), dtype_backend="numpy_nullable")

    expected = pd.DataFrame(
        {
            "string": StringArray(np.array(["a", "b", "c"], dtype=np.object_)),
            "string_with_nan": StringArray(
                np.array(["a", pd.NA, "c"], dtype=np.object_)
            ),
            "string_with_none": StringArray(
                np.array(["a", pd.NA, "c"], dtype=np.object_)
            ),
            "int": pd.Series([1, 2, 3], dtype="Int64"),
            "int_with_nan": pd.Series([1, pd.NA, 3], dtype="Int64"),
            "na_only": pd.Series([pd.NA, pd.NA, pd.NA], dtype="Int64"),
            "float": pd.Series([4.0, 5.0, 6.0], dtype="Float64"),
            "float_with_nan": pd.Series([2.0, pd.NA, 3.0], dtype="Float64"),
            "bool": pd.Series([True, False, True], dtype="boolean"),
            "bool_with_na": pd.Series([True, False, pd.NA], dtype="boolean"),
        }
    )

    tm.assert_frame_equal(result, expected)


def test_orc_uri_path():
    expected = pd.DataFrame({"int": list(range(1, 4))})
    with tm.ensure_clean("tmp.orc") as path:
        expected.to_orc(path)
        uri = pathlib.Path(path).as_uri()
        result = read_orc(uri)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "index",
    [
        pd.RangeIndex(start=2, stop=5, step=1),
        pd.RangeIndex(start=0, stop=3, step=1, name="non-default"),
        pd.Index([1, 2, 3]),
    ],
)
def test_to_orc_non_default_index(index):
    df = pd.DataFrame({"a": [1, 2, 3]}, index=index)
    msg = (
        "orc does not support serializing a non-default index|"
        "orc does not serialize index meta-data"
    )
    with pytest.raises(ValueError, match=msg):
        df.to_orc()


def test_invalid_dtype_backend():
    msg = (
        "dtype_backend numpy is invalid, only 'numpy_nullable' and "
        "'pyarrow' are allowed."
    )
    df = pd.DataFrame({"int": list(range(1, 4))})
    with tm.ensure_clean("tmp.orc") as path:
        df.to_orc(path)
        with pytest.raises(ValueError, match=msg):
            read_orc(path, dtype_backend="numpy")


def test_string_inference(tmp_path):
    # GH#54431
    path = tmp_path / "test_string_inference.p"
    df = pd.DataFrame(data={"a": ["x", "y"]})
    df.to_orc(path)
    with pd.option_context("future.infer_string", True):
        result = read_orc(path)
    expected = pd.DataFrame(
        data={"a": ["x", "y"]},
        dtype=pd.StringDtype(na_value=np.nan),
        columns=pd.Index(["a"], dtype=pd.StringDtype(na_value=np.nan)),
    )
    tm.assert_frame_equal(result, expected)
