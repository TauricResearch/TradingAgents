import re
import warnings

import numpy as np
import pytest

import pandas as pd
from pandas import SparseDtype


@pytest.mark.parametrize(
    "dtype, fill_value",
    [
        ("int", 0),
        ("float", np.nan),
        ("bool", False),
        ("object", np.nan),
        ("datetime64[ns]", np.datetime64("NaT", "ns")),
        ("timedelta64[ns]", np.timedelta64("NaT", "ns")),
    ],
)
def test_inferred_dtype(dtype, fill_value):
    sparse_dtype = SparseDtype(dtype)
    result = sparse_dtype.fill_value
    if pd.isna(fill_value):
        assert pd.isna(result) and type(result) == type(fill_value)
    else:
        assert result == fill_value


def test_from_sparse_dtype():
    dtype = SparseDtype("float", 0)
    result = SparseDtype(dtype)
    assert result.fill_value == 0


def test_from_sparse_dtype_fill_value():
    dtype = SparseDtype("int", 1)
    result = SparseDtype(dtype, fill_value=2)
    expected = SparseDtype("int", 2)
    assert result == expected


@pytest.mark.parametrize(
    "dtype, fill_value",
    [
        ("int", None),
        ("float", None),
        ("bool", None),
        ("object", None),
        ("datetime64[ns]", None),
        ("timedelta64[ns]", None),
        ("int", np.nan),
        ("float", 0),
    ],
)
def test_equal(dtype, fill_value):
    a = SparseDtype(dtype, fill_value)
    b = SparseDtype(dtype, fill_value)
    assert a == b
    assert b == a


def test_nans_equal():
    a = SparseDtype(float, float("nan"))
    b = SparseDtype(float, np.nan)
    assert a == b
    assert b == a


with warnings.catch_warnings():
    msg = "Allowing arbitrary scalar fill_value in SparseDtype is deprecated"
    warnings.filterwarnings("ignore", msg, category=FutureWarning)

    tups = [
        (SparseDtype("float64"), SparseDtype("float32")),
        (SparseDtype("float64"), SparseDtype("float64", 0)),
        (SparseDtype("float64"), SparseDtype("datetime64[ns]", np.nan)),
        (SparseDtype(int, pd.NaT), SparseDtype(float, pd.NaT)),
        (SparseDtype("float64"), np.dtype("float64")),
    ]


@pytest.mark.parametrize(
    "a, b",
    tups,
)
def test_not_equal(a, b):
    assert a != b


def test_construct_from_string_raises():
    with pytest.raises(
        TypeError, match="Cannot construct a 'SparseDtype' from 'not a dtype'"
    ):
        SparseDtype.construct_from_string("not a dtype")


@pytest.mark.parametrize(
    "dtype, expected",
    [
        (SparseDtype(int), True),
        (SparseDtype(float), True),
        (SparseDtype(bool), True),
        (SparseDtype(object), False),
        (SparseDtype(str), False),
    ],
)
def test_is_numeric(dtype, expected):
    assert dtype._is_numeric is expected


def test_str_uses_object():
    result = SparseDtype(str).subtype
    assert result == np.dtype("object")


@pytest.mark.parametrize(
    "string, expected",
    [
        ("Sparse[float64]", SparseDtype(np.dtype("float64"))),
        ("Sparse[float32]", SparseDtype(np.dtype("float32"))),
        ("Sparse[int]", SparseDtype(np.dtype("int"))),
        ("Sparse[str]", SparseDtype(np.dtype("str"))),
        ("Sparse[datetime64[ns]]", SparseDtype(np.dtype("datetime64[ns]"))),
        ("Sparse", SparseDtype(np.dtype("float"), np.nan)),
    ],
)
def test_construct_from_string(string, expected):
    result = SparseDtype.construct_from_string(string)
    assert result == expected


@pytest.mark.parametrize(
    "a, b, expected",
    [
        (SparseDtype(float, 0.0), SparseDtype(np.dtype("float"), 0.0), True),
        (SparseDtype(int, 0), SparseDtype(int, 0), True),
        (SparseDtype(float, float("nan")), SparseDtype(float, np.nan), True),
        (SparseDtype(float, 0), SparseDtype(float, np.nan), False),
        (SparseDtype(int, 0.0), SparseDtype(float, 0.0), False),
    ],
)
def test_hash_equal(a, b, expected):
    result = a == b
    assert result is expected

    result = hash(a) == hash(b)
    assert result is expected


@pytest.mark.parametrize(
    "string, expected",
    [
        ("Sparse[int]", "int"),
        ("Sparse[int, 0]", "int"),
        ("Sparse[int64]", "int64"),
        ("Sparse[int64, 0]", "int64"),
        ("Sparse[datetime64[ns], 0]", "datetime64[ns]"),
    ],
)
def test_parse_subtype(string, expected):
    subtype, _ = SparseDtype._parse_subtype(string)
    assert subtype == expected


@pytest.mark.parametrize(
    "string", ["Sparse[int, 1]", "Sparse[float, 0.0]", "Sparse[bool, True]"]
)
def test_construct_from_string_fill_value_raises(string):
    with pytest.raises(TypeError, match="fill_value in the string is not"):
        SparseDtype.construct_from_string(string)


@pytest.mark.parametrize(
    "original, dtype, expected",
    [
        (SparseDtype(int, 0), float, SparseDtype(float, 0.0)),
        (SparseDtype(int, 1), float, SparseDtype(float, 1.0)),
        (SparseDtype(int, 1), np.str_, SparseDtype(object, "1")),
        (SparseDtype(float, 1.5), int, SparseDtype(int, 1)),
    ],
)
def test_update_dtype(original, dtype, expected):
    result = original.update_dtype(dtype)
    assert result == expected


@pytest.mark.parametrize(
    "original, dtype, expected_error_msg",
    [
        (
            SparseDtype(float, np.nan),
            int,
            re.escape("Cannot convert non-finite values (NA or inf) to integer"),
        ),
        (
            SparseDtype(str, "abc"),
            int,
            r"invalid literal for int\(\) with base 10: ('abc'|np\.str_\('abc'\))",
        ),
    ],
)
def test_update_dtype_raises(original, dtype, expected_error_msg):
    with pytest.raises(ValueError, match=expected_error_msg):
        original.update_dtype(dtype)


def test_repr():
    # GH-34352
    result = str(SparseDtype("int64", fill_value=0))
    expected = "Sparse[int64, 0]"
    assert result == expected

    result = str(SparseDtype(object, fill_value="0"))
    expected = "Sparse[object, '0']"
    assert result == expected


def test_sparse_dtype_subtype_must_be_numpy_dtype():
    # GH#53160
    msg = "SparseDtype subtype must be a numpy dtype"
    with pytest.raises(TypeError, match=msg):
        SparseDtype("category", fill_value="c")
