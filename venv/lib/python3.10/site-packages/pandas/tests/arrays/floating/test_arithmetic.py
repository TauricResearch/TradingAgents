import operator

import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays import FloatingArray

# Basic test for the arithmetic array ops
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "opname, exp",
    [
        ("add", [1.1, 2.2, None, None, 5.5]),
        ("mul", [0.1, 0.4, None, None, 2.5]),
        ("sub", [0.9, 1.8, None, None, 4.5]),
        ("truediv", [10.0, 10.0, None, None, 10.0]),
        ("floordiv", [9.0, 9.0, None, None, 10.0]),
        ("mod", [0.1, 0.2, None, None, 0.0]),
    ],
    ids=["add", "mul", "sub", "div", "floordiv", "mod"],
)
def test_array_op(dtype, opname, exp):
    a = pd.array([1.0, 2.0, None, 4.0, 5.0], dtype=dtype)
    b = pd.array([0.1, 0.2, 0.3, None, 0.5], dtype=dtype)

    op = getattr(operator, opname)

    result = op(a, b)
    expected = pd.array(exp, dtype=dtype)
    tm.assert_extension_array_equal(result, expected)


@pytest.mark.parametrize("zero, negative", [(0, False), (0.0, False), (-0.0, True)])
def test_divide_by_zero(dtype, zero, negative):
    # TODO pending NA/NaN discussion
    # https://github.com/pandas-dev/pandas/issues/32265/
    a = pd.array([0, 1, -1, None], dtype=dtype)
    result = a / zero
    expected = FloatingArray(
        np.array([np.nan, np.inf, -np.inf, np.nan], dtype=dtype.numpy_dtype),
        np.array([False, False, False, True]),
    )
    if negative:
        expected *= -1
    tm.assert_extension_array_equal(result, expected)


def test_pow_scalar(dtype):
    a = pd.array([-1, 0, 1, None, 2], dtype=dtype)
    result = a**0
    expected = pd.array([1, 1, 1, 1, 1], dtype=dtype)
    tm.assert_extension_array_equal(result, expected)

    result = a**1
    expected = pd.array([-1, 0, 1, None, 2], dtype=dtype)
    tm.assert_extension_array_equal(result, expected)

    result = a**pd.NA
    expected = pd.array([None, None, 1, None, None], dtype=dtype)
    tm.assert_extension_array_equal(result, expected)

    result = a**np.nan
    # TODO np.nan should be converted to pd.NA / missing before operation?
    expected = FloatingArray(
        np.array([np.nan, np.nan, 1, np.nan, np.nan], dtype=dtype.numpy_dtype),
        mask=a._mask,
    )
    tm.assert_extension_array_equal(result, expected)

    # reversed
    a = a[1:]  # Can't raise integers to negative powers.

    result = 0**a
    expected = pd.array([1, 0, None, 0], dtype=dtype)
    tm.assert_extension_array_equal(result, expected)

    result = 1**a
    expected = pd.array([1, 1, 1, 1], dtype=dtype)
    tm.assert_extension_array_equal(result, expected)

    result = pd.NA**a
    expected = pd.array([1, None, None, None], dtype=dtype)
    tm.assert_extension_array_equal(result, expected)

    result = np.nan**a
    expected = FloatingArray(
        np.array([1, np.nan, np.nan, np.nan], dtype=dtype.numpy_dtype), mask=a._mask
    )
    tm.assert_extension_array_equal(result, expected)


def test_pow_array(dtype):
    a = pd.array([0, 0, 0, 1, 1, 1, None, None, None], dtype=dtype)
    b = pd.array([0, 1, None, 0, 1, None, 0, 1, None], dtype=dtype)
    result = a**b
    expected = pd.array([1, 0, None, 1, 1, 1, 1, None, None], dtype=dtype)
    tm.assert_extension_array_equal(result, expected)


def test_rpow_one_to_na():
    # https://github.com/pandas-dev/pandas/issues/22022
    # https://github.com/pandas-dev/pandas/issues/29997
    arr = pd.array([np.nan, np.nan], dtype="Float64")
    result = np.array([1.0, 2.0]) ** arr
    expected = pd.array([1.0, np.nan], dtype="Float64")
    tm.assert_extension_array_equal(result, expected)


@pytest.mark.parametrize("other", [0, 0.5])
def test_arith_zero_dim_ndarray(other):
    arr = pd.array([1, None, 2], dtype="Float64")
    result = arr + np.array(other)
    expected = arr + other
    tm.assert_equal(result, expected)


# Test generic characteristics / errors
# -----------------------------------------------------------------------------


def test_error_invalid_values(data, all_arithmetic_operators):
    op = all_arithmetic_operators
    s = pd.Series(data)
    ops = getattr(s, op)

    # invalid scalars
    msg = "|".join(
        [
            r"can only perform ops with numeric values",
            r"FloatingArray cannot perform the operation mod",
            "unsupported operand type",
            "not all arguments converted during string formatting",
            "can't multiply sequence by non-int of type 'float'",
            "ufunc 'subtract' cannot use operands with types dtype",
            r"can only concatenate str \(not \"float\"\) to str",
            "ufunc '.*' not supported for the input types, and the inputs could not",
            "ufunc '.*' did not contain a loop with signature matching types",
            "Concatenation operation is not implemented for NumPy arrays",
            "has no kernel",
            "not implemented",
            "not supported for dtype",
            "Can only string multiply by an integer",
        ]
    )
    with pytest.raises(TypeError, match=msg):
        ops("foo")
    with pytest.raises(TypeError, match=msg):
        ops(pd.Timestamp("20180101"))

    # invalid array-likes
    with pytest.raises(TypeError, match=msg):
        ops(pd.Series("foo", index=s.index))

    msg = "|".join(
        [
            "can only perform ops with numeric values",
            "cannot perform .* with this index type: DatetimeArray",
            "Addition/subtraction of integers and integer-arrays "
            "with DatetimeArray is no longer supported. *",
            "unsupported operand type",
            "not all arguments converted during string formatting",
            "can't multiply sequence by non-int of type 'float'",
            "ufunc 'subtract' cannot use operands with types dtype",
            (
                "ufunc 'add' cannot use operands with types "
                rf"dtype\('{tm.ENDIAN}M8\[ns\]'\)"
            ),
            r"ufunc 'add' cannot use operands with types dtype\('float\d{2}'\)",
            "cannot subtract DatetimeArray from ndarray",
            "has no kernel",
            "not implemented",
            "not supported for dtype",
        ]
    )
    with pytest.raises(TypeError, match=msg):
        ops(pd.Series(pd.date_range("20180101", periods=len(s))))


# Various
# -----------------------------------------------------------------------------


def test_cross_type_arithmetic():
    df = pd.DataFrame(
        {
            "A": pd.array([1, 2, np.nan], dtype="Float64"),
            "B": pd.array([1, np.nan, 3], dtype="Float32"),
            "C": np.array([1, 2, 3], dtype="float64"),
        }
    )

    result = df.A + df.C
    expected = pd.Series([2, 4, np.nan], dtype="Float64")
    tm.assert_series_equal(result, expected)

    result = (df.A + df.C) * 3 == 12
    expected = pd.Series([False, True, None], dtype="boolean")
    tm.assert_series_equal(result, expected)

    result = df.A + df.B
    expected = pd.Series([2, np.nan, np.nan], dtype="Float64")
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "source, neg_target, abs_target",
    [
        ([1.1, 2.2, 3.3], [-1.1, -2.2, -3.3], [1.1, 2.2, 3.3]),
        ([1.1, 2.2, None], [-1.1, -2.2, None], [1.1, 2.2, None]),
        ([-1.1, 0.0, 1.1], [1.1, 0.0, -1.1], [1.1, 0.0, 1.1]),
    ],
)
def test_unary_float_operators(float_ea_dtype, source, neg_target, abs_target):
    # GH38794
    dtype = float_ea_dtype
    arr = pd.array(source, dtype=dtype)
    neg_result, pos_result, abs_result = -arr, +arr, abs(arr)
    neg_target = pd.array(neg_target, dtype=dtype)
    abs_target = pd.array(abs_target, dtype=dtype)

    tm.assert_extension_array_equal(neg_result, neg_target)
    tm.assert_extension_array_equal(pos_result, arr)
    assert not tm.shares_memory(pos_result, arr)
    tm.assert_extension_array_equal(abs_result, abs_target)


def test_bitwise(dtype):
    left = pd.array([1, None, 3, 4], dtype=dtype)
    right = pd.array([None, 3, 5, 4], dtype=dtype)

    with pytest.raises(TypeError, match="unsupported operand type"):
        left | right
    with pytest.raises(TypeError, match="unsupported operand type"):
        left & right
    with pytest.raises(TypeError, match="unsupported operand type"):
        left ^ right
