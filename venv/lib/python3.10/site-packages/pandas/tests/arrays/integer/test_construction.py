import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.api.types import is_integer
from pandas.core.arrays import IntegerArray
from pandas.core.arrays.integer import (
    Int8Dtype,
    Int32Dtype,
    Int64Dtype,
)


@pytest.fixture(params=[pd.array, IntegerArray._from_sequence])
def constructor(request):
    """Fixture returning parametrized IntegerArray from given sequence.

    Used to test dtype conversions.
    """
    return request.param


def test_uses_pandas_na():
    a = pd.array([1, None], dtype=Int64Dtype())
    assert a[1] is pd.NA


def test_from_dtype_from_float(data):
    # construct from our dtype & string dtype
    dtype = data.dtype

    # from float
    expected = pd.Series(data)
    result = pd.Series(data.to_numpy(na_value=np.nan, dtype="float"), dtype=str(dtype))
    tm.assert_series_equal(result, expected)

    # from int / list
    expected = pd.Series(data)
    result = pd.Series(np.array(data).tolist(), dtype=str(dtype))
    tm.assert_series_equal(result, expected)

    # from int / array
    expected = pd.Series(data).dropna().reset_index(drop=True)
    dropped = np.array(data.dropna()).astype(np.dtype(dtype.type))
    result = pd.Series(dropped, dtype=str(dtype))
    tm.assert_series_equal(result, expected)


def test_conversions(data_missing):
    # astype to object series
    df = pd.DataFrame({"A": data_missing})
    result = df["A"].astype("object")
    expected = pd.Series(np.array([pd.NA, 1], dtype=object), name="A")
    tm.assert_series_equal(result, expected)

    # convert to object ndarray
    # we assert that we are exactly equal
    # including type conversions of scalars
    result = df["A"].astype("object").values
    expected = np.array([pd.NA, 1], dtype=object)
    tm.assert_numpy_array_equal(result, expected)

    for r, e in zip(result, expected):
        if pd.isnull(r):
            assert pd.isnull(e)
        elif is_integer(r):
            assert r == e
            assert is_integer(e)
        else:
            assert r == e
            assert type(r) == type(e)


def test_integer_array_constructor():
    values = np.array([1, 2, 3, 4], dtype="int64")
    mask = np.array([False, False, False, True], dtype="bool")

    result = IntegerArray(values, mask)
    expected = pd.array([1, 2, 3, np.nan], dtype="Int64")
    tm.assert_extension_array_equal(result, expected)

    msg = r".* should be .* numpy array. Use the 'pd.array' function instead"
    with pytest.raises(TypeError, match=msg):
        IntegerArray(values.tolist(), mask)

    with pytest.raises(TypeError, match=msg):
        IntegerArray(values, mask.tolist())

    with pytest.raises(TypeError, match=msg):
        IntegerArray(values.astype(float), mask)
    msg = r"__init__\(\) missing 1 required positional argument: 'mask'"
    with pytest.raises(TypeError, match=msg):
        IntegerArray(values)


def test_integer_array_constructor_copy():
    values = np.array([1, 2, 3, 4], dtype="int64")
    mask = np.array([False, False, False, True], dtype="bool")

    result = IntegerArray(values, mask)
    assert result._data is values
    assert result._mask is mask

    result = IntegerArray(values, mask, copy=True)
    assert result._data is not values
    assert result._mask is not mask


@pytest.mark.parametrize(
    "a, b",
    [
        ([1, None], [1, np.nan]),
        ([None], [np.nan]),
        ([None, np.nan], [np.nan, np.nan]),
        ([np.nan, np.nan], [np.nan, np.nan]),
    ],
)
def test_to_integer_array_none_is_nan(a, b):
    result = pd.array(a, dtype="Int64")
    expected = pd.array(b, dtype="Int64")
    tm.assert_extension_array_equal(result, expected)


@pytest.mark.parametrize(
    "values",
    [
        ["foo", "bar"],
        "foo",
        1,
        1.0,
        pd.date_range("20130101", periods=2),
        np.array(["foo"]),
        [[1, 2], [3, 4]],
        [np.nan, {"a": 1}],
    ],
)
def test_to_integer_array_error(values):
    # error in converting existing arrays to IntegerArrays
    msg = "|".join(
        [
            r"cannot be converted to IntegerDtype",
            r"invalid literal for int\(\) with base 10:",
            r"values must be a 1D list-like",
            r"Cannot pass scalar",
            r"int\(\) argument must be a string",
        ]
    )
    with pytest.raises((ValueError, TypeError), match=msg):
        pd.array(values, dtype="Int64")

    with pytest.raises((ValueError, TypeError), match=msg):
        IntegerArray._from_sequence(values)


def test_to_integer_array_inferred_dtype(constructor):
    # if values has dtype -> respect it
    result = constructor(np.array([1, 2], dtype="int8"))
    assert result.dtype == Int8Dtype()
    result = constructor(np.array([1, 2], dtype="int32"))
    assert result.dtype == Int32Dtype()

    # if values have no dtype -> always int64
    result = constructor([1, 2])
    assert result.dtype == Int64Dtype()


def test_to_integer_array_dtype_keyword(constructor):
    result = constructor([1, 2], dtype="Int8")
    assert result.dtype == Int8Dtype()

    # if values has dtype -> override it
    result = constructor(np.array([1, 2], dtype="int8"), dtype="Int32")
    assert result.dtype == Int32Dtype()


def test_to_integer_array_float():
    result = IntegerArray._from_sequence([1.0, 2.0], dtype="Int64")
    expected = pd.array([1, 2], dtype="Int64")
    tm.assert_extension_array_equal(result, expected)

    with pytest.raises(TypeError, match="cannot safely cast non-equivalent"):
        IntegerArray._from_sequence([1.5, 2.0], dtype="Int64")

    # for float dtypes, the itemsize is not preserved
    result = IntegerArray._from_sequence(
        np.array([1.0, 2.0], dtype="float32"), dtype="Int64"
    )
    assert result.dtype == Int64Dtype()


def test_to_integer_array_str():
    result = IntegerArray._from_sequence(["1", "2", None], dtype="Int64")
    expected = pd.array([1, 2, np.nan], dtype="Int64")
    tm.assert_extension_array_equal(result, expected)

    with pytest.raises(
        ValueError, match=r"invalid literal for int\(\) with base 10: .*"
    ):
        IntegerArray._from_sequence(["1", "2", ""], dtype="Int64")

    with pytest.raises(
        ValueError, match=r"invalid literal for int\(\) with base 10: .*"
    ):
        IntegerArray._from_sequence(["1.5", "2.0"], dtype="Int64")


@pytest.mark.parametrize(
    "bool_values, int_values, target_dtype, expected_dtype",
    [
        ([False, True], [0, 1], Int64Dtype(), Int64Dtype()),
        ([False, True], [0, 1], "Int64", Int64Dtype()),
        ([False, True, np.nan], [0, 1, np.nan], Int64Dtype(), Int64Dtype()),
    ],
)
def test_to_integer_array_bool(
    constructor, bool_values, int_values, target_dtype, expected_dtype
):
    result = constructor(bool_values, dtype=target_dtype)
    assert result.dtype == expected_dtype
    expected = pd.array(int_values, dtype=target_dtype)
    tm.assert_extension_array_equal(result, expected)


@pytest.mark.parametrize(
    "values, to_dtype, result_dtype",
    [
        (np.array([1], dtype="int64"), None, Int64Dtype),
        (np.array([1, np.nan]), None, Int64Dtype),
        (np.array([1, np.nan]), "int8", Int8Dtype),
    ],
)
def test_to_integer_array(values, to_dtype, result_dtype):
    # convert existing arrays to IntegerArrays
    result = IntegerArray._from_sequence(values, dtype=to_dtype)
    assert result.dtype == result_dtype()
    expected = pd.array(values, dtype=result_dtype())
    tm.assert_extension_array_equal(result, expected)


def test_integer_array_from_boolean():
    # GH31104
    expected = pd.array(np.array([True, False]), dtype="Int64")
    result = pd.array(np.array([True, False], dtype=object), dtype="Int64")
    tm.assert_extension_array_equal(result, expected)
