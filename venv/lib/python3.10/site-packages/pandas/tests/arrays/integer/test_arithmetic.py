import operator

import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.core import ops
from pandas.core.arrays import FloatingArray

# Basic test for the arithmetic array ops
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "opname, exp",
    [("add", [1, 3, None, None, 9]), ("mul", [0, 2, None, None, 20])],
    ids=["add", "mul"],
)
def test_add_mul(dtype, opname, exp):
    a = pd.array([0, 1, None, 3, 4], dtype=dtype)
    b = pd.array([1, 2, 3, None, 5], dtype=dtype)

    # array / array
    expected = pd.array(exp, dtype=dtype)

    op = getattr(operator, opname)
    result = op(a, b)
    tm.assert_extension_array_equal(result, expected)

    op = getattr(ops, "r" + opname)
    result = op(a, b)
    tm.assert_extension_array_equal(result, expected)


def test_sub(dtype):
    a = pd.array([1, 2, 3, None, 5], dtype=dtype)
    b = pd.array([0, 1, None, 3, 4], dtype=dtype)

    result = a - b
    expected = pd.array([1, 1, None, None, 1], dtype=dtype)
    tm.assert_extension_array_equal(result, expected)


def test_div(dtype):
    a = pd.array([1, 2, 3, None, 5], dtype=dtype)
    b = pd.array([0, 1, None, 3, 4], dtype=dtype)

    result = a / b
    expected = pd.array([np.inf, 2, None, None, 1.25], dtype="Float64")
    tm.assert_extension_array_equal(result, expected)


@pytest.mark.parametrize("zero, negative", [(0, False), (0.0, False), (-0.0, True)])
def test_divide_by_zero(zero, negative):
    # https://github.com/pandas-dev/pandas/issues/27398, GH#22793
    a = pd.array([0, 1, -1, None], dtype="Int64")
    result = a / zero
    expected = FloatingArray(
        np.array([np.nan, np.inf, -np.inf, 1], dtype="float64"),
        np.array([False, False, False, True]),
    )
    if negative:
        expected *= -1
    tm.assert_extension_array_equal(result, expected)


def test_floordiv(dtype):
    a = pd.array([1, 2, 3, None, 5], dtype=dtype)
    b = pd.array([0, 1, None, 3, 4], dtype=dtype)

    result = a // b
    # Series op sets 1//0 to np.inf, which IntegerArray does not do (yet)
    expected = pd.array([0, 2, None, None, 1], dtype=dtype)
    tm.assert_extension_array_equal(result, expected)


def test_floordiv_by_int_zero_no_mask(any_int_ea_dtype):
    # GH 48223: Aligns with non-masked floordiv
    # but differs from numpy
    # https://github.com/pandas-dev/pandas/issues/30188#issuecomment-564452740
    ser = pd.Series([0, 1], dtype=any_int_ea_dtype)
    result = 1 // ser
    expected = pd.Series([np.inf, 1.0], dtype="Float64")
    tm.assert_series_equal(result, expected)

    ser_non_nullable = ser.astype(ser.dtype.numpy_dtype)
    result = 1 // ser_non_nullable
    expected = expected.astype(np.float64)
    tm.assert_series_equal(result, expected)


def test_mod(dtype):
    a = pd.array([1, 2, 3, None, 5], dtype=dtype)
    b = pd.array([0, 1, None, 3, 4], dtype=dtype)

    result = a % b
    expected = pd.array([0, 0, None, None, 1], dtype=dtype)
    tm.assert_extension_array_equal(result, expected)


def test_pow_scalar():
    a = pd.array([-1, 0, 1, None, 2], dtype="Int64")
    result = a**0
    expected = pd.array([1, 1, 1, 1, 1], dtype="Int64")
    tm.assert_extension_array_equal(result, expected)

    result = a**1
    expected = pd.array([-1, 0, 1, None, 2], dtype="Int64")
    tm.assert_extension_array_equal(result, expected)

    result = a**pd.NA
    expected = pd.array([None, None, 1, None, None], dtype="Int64")
    tm.assert_extension_array_equal(result, expected)

    result = a**np.nan
    expected = FloatingArray(
        np.array([np.nan, np.nan, 1, np.nan, np.nan], dtype="float64"),
        np.array([False, False, False, True, False]),
    )
    tm.assert_extension_array_equal(result, expected)

    # reversed
    a = a[1:]  # Can't raise integers to negative powers.

    result = 0**a
    expected = pd.array([1, 0, None, 0], dtype="Int64")
    tm.assert_extension_array_equal(result, expected)

    result = 1**a
    expected = pd.array([1, 1, 1, 1], dtype="Int64")
    tm.assert_extension_array_equal(result, expected)

    result = pd.NA**a
    expected = pd.array([1, None, None, None], dtype="Int64")
    tm.assert_extension_array_equal(result, expected)

    result = np.nan**a
    expected = FloatingArray(
        np.array([1, np.nan, np.nan, np.nan], dtype="float64"),
        np.array([False, False, True, False]),
    )
    tm.assert_extension_array_equal(result, expected)


def test_pow_array():
    a = pd.array([0, 0, 0, 1, 1, 1, None, None, None])
    b = pd.array([0, 1, None, 0, 1, None, 0, 1, None])
    result = a**b
    expected = pd.array([1, 0, None, 1, 1, 1, 1, None, None])
    tm.assert_extension_array_equal(result, expected)


def test_rpow_one_to_na():
    # https://github.com/pandas-dev/pandas/issues/22022
    # https://github.com/pandas-dev/pandas/issues/29997
    arr = pd.array([np.nan, np.nan], dtype="Int64")
    result = np.array([1.0, 2.0]) ** arr
    expected = pd.array([1.0, np.nan], dtype="Float64")
    tm.assert_extension_array_equal(result, expected)


@pytest.mark.parametrize("other", [0, 0.5])
def test_numpy_zero_dim_ndarray(other):
    arr = pd.array([1, None, 2])
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
    with tm.external_error_raised(TypeError):
        ops("foo")
    with tm.external_error_raised(TypeError):
        ops(pd.Timestamp("20180101"))

    # invalid array-likes
    str_ser = pd.Series("foo", index=s.index)
    # with pytest.raises(TypeError, match=msg):
    if all_arithmetic_operators in [
        "__mul__",
        "__rmul__",
    ]:  # (data[~data.isna()] >= 0).all():
        res = ops(str_ser)
        expected = pd.Series(["foo" * x for x in data], index=s.index)
        expected = expected.fillna(np.nan)
        # TODO: doing this fillna to keep tests passing as we make
        #  assert_almost_equal stricter, but the expected with pd.NA seems
        #  more-correct than np.nan here.
        tm.assert_series_equal(res, expected)
    else:
        with tm.external_error_raised(TypeError):
            ops(str_ser)

    with tm.external_error_raised(TypeError):
        ops(pd.Series(pd.date_range("20180101", periods=len(s))))


# Various
# -----------------------------------------------------------------------------


# TODO test unsigned overflow


def test_arith_coerce_scalar(data, all_arithmetic_operators):
    op = tm.get_op_from_name(all_arithmetic_operators)
    s = pd.Series(data)
    other = 0.01

    result = op(s, other)
    expected = op(s.astype(float), other)
    expected = expected.astype("Float64")

    # rmod results in NaN that wasn't NA in original nullable Series -> unmask it
    if all_arithmetic_operators == "__rmod__":
        mask = (s == 0).fillna(False).to_numpy(bool)
        expected.array._mask[mask] = False

    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("other", [1.0, np.array(1.0)])
def test_arithmetic_conversion(all_arithmetic_operators, other):
    # if we have a float operand we should have a float result
    # if that is equal to an integer
    op = tm.get_op_from_name(all_arithmetic_operators)

    s = pd.Series([1, 2, 3], dtype="Int64")
    result = op(s, other)
    assert result.dtype == "Float64"


def test_cross_type_arithmetic():
    df = pd.DataFrame(
        {
            "A": pd.Series([1, 2, np.nan], dtype="Int64"),
            "B": pd.Series([1, np.nan, 3], dtype="UInt8"),
            "C": [1, 2, 3],
        }
    )

    result = df.A + df.C
    expected = pd.Series([2, 4, np.nan], dtype="Int64")
    tm.assert_series_equal(result, expected)

    result = (df.A + df.C) * 3 == 12
    expected = pd.Series([False, True, None], dtype="boolean")
    tm.assert_series_equal(result, expected)

    result = df.A + df.B
    expected = pd.Series([2, np.nan, np.nan], dtype="Int64")
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("op", ["mean"])
def test_reduce_to_float(op):
    # some reduce ops always return float, even if the result
    # is a rounded number
    df = pd.DataFrame(
        {
            "A": ["a", "b", "b"],
            "B": [1, None, 3],
            "C": pd.array([1, None, 3], dtype="Int64"),
        }
    )

    # op
    result = getattr(df.C, op)()
    assert isinstance(result, float)

    # groupby
    result = getattr(df.groupby("A"), op)()

    expected = pd.DataFrame(
        {"B": np.array([1.0, 3.0]), "C": pd.array([1, 3], dtype="Float64")},
        index=pd.Index(["a", "b"], name="A"),
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "source, neg_target, abs_target",
    [
        ([1, 2, 3], [-1, -2, -3], [1, 2, 3]),
        ([1, 2, None], [-1, -2, None], [1, 2, None]),
        ([-1, 0, 1], [1, 0, -1], [1, 0, 1]),
    ],
)
def test_unary_int_operators(any_signed_int_ea_dtype, source, neg_target, abs_target):
    dtype = any_signed_int_ea_dtype
    arr = pd.array(source, dtype=dtype)
    neg_result, pos_result, abs_result = -arr, +arr, abs(arr)
    neg_target = pd.array(neg_target, dtype=dtype)
    abs_target = pd.array(abs_target, dtype=dtype)

    tm.assert_extension_array_equal(neg_result, neg_target)
    tm.assert_extension_array_equal(pos_result, arr)
    assert not tm.shares_memory(pos_result, arr)
    tm.assert_extension_array_equal(abs_result, abs_target)


def test_values_multiplying_large_series_by_NA():
    # GH#33701

    result = pd.NA * pd.Series(np.zeros(10001))
    expected = pd.Series([pd.NA] * 10001)

    tm.assert_series_equal(result, expected)


def test_bitwise(dtype):
    left = pd.array([1, None, 3, 4], dtype=dtype)
    right = pd.array([None, 3, 5, 4], dtype=dtype)

    result = left | right
    expected = pd.array([None, None, 3 | 5, 4 | 4], dtype=dtype)
    tm.assert_extension_array_equal(result, expected)

    result = left & right
    expected = pd.array([None, None, 3 & 5, 4 & 4], dtype=dtype)
    tm.assert_extension_array_equal(result, expected)

    result = left ^ right
    expected = pd.array([None, None, 3 ^ 5, 4 ^ 4], dtype=dtype)
    tm.assert_extension_array_equal(result, expected)

    # TODO: desired behavior when operating with boolean?  defer?

    floats = right.astype("Float64")
    with pytest.raises(TypeError, match="unsupported operand type"):
        left | floats
    with pytest.raises(TypeError, match="unsupported operand type"):
        left & floats
    with pytest.raises(TypeError, match="unsupported operand type"):
        left ^ floats
