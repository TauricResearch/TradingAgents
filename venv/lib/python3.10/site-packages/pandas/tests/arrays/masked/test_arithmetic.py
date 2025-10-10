from __future__ import annotations

from typing import Any

import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm

# integer dtypes
arrays = [pd.array([1, 2, 3, None], dtype=dtype) for dtype in tm.ALL_INT_EA_DTYPES]
scalars: list[Any] = [2] * len(arrays)
# floating dtypes
arrays += [pd.array([0.1, 0.2, 0.3, None], dtype=dtype) for dtype in tm.FLOAT_EA_DTYPES]
scalars += [0.2, 0.2]
# boolean
arrays += [pd.array([True, False, True, None], dtype="boolean")]
scalars += [False]


@pytest.fixture(params=zip(arrays, scalars), ids=[a.dtype.name for a in arrays])
def data(request):
    """Fixture returning parametrized (array, scalar) tuple.

    Used to test equivalence of scalars, numpy arrays with array ops, and the
    equivalence of DataFrame and Series ops.
    """
    return request.param


def check_skip(data, op_name):
    if isinstance(data.dtype, pd.BooleanDtype) and "sub" in op_name:
        pytest.skip("subtract not implemented for boolean")


def is_bool_not_implemented(data, op_name):
    # match non-masked behavior
    return data.dtype.kind == "b" and op_name.strip("_").lstrip("r") in [
        "pow",
        "truediv",
        "floordiv",
    ]


# Test equivalence of scalars, numpy arrays with array ops
# -----------------------------------------------------------------------------


def test_array_scalar_like_equivalence(data, all_arithmetic_operators):
    data, scalar = data
    op = tm.get_op_from_name(all_arithmetic_operators)
    check_skip(data, all_arithmetic_operators)

    scalar_array = pd.array([scalar] * len(data), dtype=data.dtype)

    # TODO also add len-1 array (np.array([scalar], dtype=data.dtype.numpy_dtype))
    for scalar in [scalar, data.dtype.type(scalar)]:
        if is_bool_not_implemented(data, all_arithmetic_operators):
            msg = "operator '.*' not implemented for bool dtypes"
            with pytest.raises(NotImplementedError, match=msg):
                op(data, scalar)
            with pytest.raises(NotImplementedError, match=msg):
                op(data, scalar_array)
        else:
            result = op(data, scalar)
            expected = op(data, scalar_array)
            tm.assert_extension_array_equal(result, expected)


def test_array_NA(data, all_arithmetic_operators):
    data, _ = data
    op = tm.get_op_from_name(all_arithmetic_operators)
    check_skip(data, all_arithmetic_operators)

    scalar = pd.NA
    scalar_array = pd.array([pd.NA] * len(data), dtype=data.dtype)

    mask = data._mask.copy()

    if is_bool_not_implemented(data, all_arithmetic_operators):
        msg = "operator '.*' not implemented for bool dtypes"
        with pytest.raises(NotImplementedError, match=msg):
            op(data, scalar)
        # GH#45421 check op doesn't alter data._mask inplace
        tm.assert_numpy_array_equal(mask, data._mask)
        return

    result = op(data, scalar)
    # GH#45421 check op doesn't alter data._mask inplace
    tm.assert_numpy_array_equal(mask, data._mask)

    expected = op(data, scalar_array)
    tm.assert_numpy_array_equal(mask, data._mask)

    tm.assert_extension_array_equal(result, expected)


def test_numpy_array_equivalence(data, all_arithmetic_operators):
    data, scalar = data
    op = tm.get_op_from_name(all_arithmetic_operators)
    check_skip(data, all_arithmetic_operators)

    numpy_array = np.array([scalar] * len(data), dtype=data.dtype.numpy_dtype)
    pd_array = pd.array(numpy_array, dtype=data.dtype)

    if is_bool_not_implemented(data, all_arithmetic_operators):
        msg = "operator '.*' not implemented for bool dtypes"
        with pytest.raises(NotImplementedError, match=msg):
            op(data, numpy_array)
        with pytest.raises(NotImplementedError, match=msg):
            op(data, pd_array)
        return

    result = op(data, numpy_array)
    expected = op(data, pd_array)
    tm.assert_extension_array_equal(result, expected)


# Test equivalence with Series and DataFrame ops
# -----------------------------------------------------------------------------


def test_frame(data, all_arithmetic_operators):
    data, scalar = data
    op = tm.get_op_from_name(all_arithmetic_operators)
    check_skip(data, all_arithmetic_operators)

    # DataFrame with scalar
    df = pd.DataFrame({"A": data})

    if is_bool_not_implemented(data, all_arithmetic_operators):
        msg = "operator '.*' not implemented for bool dtypes"
        with pytest.raises(NotImplementedError, match=msg):
            op(df, scalar)
        with pytest.raises(NotImplementedError, match=msg):
            op(data, scalar)
        return

    result = op(df, scalar)
    expected = pd.DataFrame({"A": op(data, scalar)})
    tm.assert_frame_equal(result, expected)


def test_series(data, all_arithmetic_operators):
    data, scalar = data
    op = tm.get_op_from_name(all_arithmetic_operators)
    check_skip(data, all_arithmetic_operators)

    ser = pd.Series(data)

    others = [
        scalar,
        np.array([scalar] * len(data), dtype=data.dtype.numpy_dtype),
        pd.array([scalar] * len(data), dtype=data.dtype),
        pd.Series([scalar] * len(data), dtype=data.dtype),
    ]

    for other in others:
        if is_bool_not_implemented(data, all_arithmetic_operators):
            msg = "operator '.*' not implemented for bool dtypes"
            with pytest.raises(NotImplementedError, match=msg):
                op(ser, other)

        else:
            result = op(ser, other)
            expected = pd.Series(op(data, other))
            tm.assert_series_equal(result, expected)


# Test generic characteristics / errors
# -----------------------------------------------------------------------------


def test_error_invalid_object(data, all_arithmetic_operators):
    data, _ = data

    op = all_arithmetic_operators
    opa = getattr(data, op)

    # 2d -> return NotImplemented
    result = opa(pd.DataFrame({"A": data}))
    assert result is NotImplemented

    msg = r"can only perform ops with 1-d structures"
    with pytest.raises(NotImplementedError, match=msg):
        opa(np.arange(len(data)).reshape(-1, len(data)))


def test_error_len_mismatch(data, all_arithmetic_operators):
    # operating with a list-like with non-matching length raises
    data, scalar = data
    op = tm.get_op_from_name(all_arithmetic_operators)

    other = [scalar] * (len(data) - 1)

    err = ValueError
    msg = "|".join(
        [
            r"operands could not be broadcast together with shapes \(3,\) \(4,\)",
            r"operands could not be broadcast together with shapes \(4,\) \(3,\)",
        ]
    )
    if data.dtype.kind == "b" and all_arithmetic_operators.strip("_") in [
        "sub",
        "rsub",
    ]:
        err = TypeError
        msg = (
            r"numpy boolean subtract, the `\-` operator, is not supported, use "
            r"the bitwise_xor, the `\^` operator, or the logical_xor function instead"
        )
    elif is_bool_not_implemented(data, all_arithmetic_operators):
        msg = "operator '.*' not implemented for bool dtypes"
        err = NotImplementedError

    for other in [other, np.array(other)]:
        with pytest.raises(err, match=msg):
            op(data, other)

        s = pd.Series(data)
        with pytest.raises(err, match=msg):
            op(s, other)


@pytest.mark.parametrize("op", ["__neg__", "__abs__", "__invert__"])
def test_unary_op_does_not_propagate_mask(data, op):
    # https://github.com/pandas-dev/pandas/issues/39943
    data, _ = data
    ser = pd.Series(data)

    if op == "__invert__" and data.dtype.kind == "f":
        # we follow numpy in raising
        msg = "ufunc 'invert' not supported for the input types"
        with pytest.raises(TypeError, match=msg):
            getattr(ser, op)()
        with pytest.raises(TypeError, match=msg):
            getattr(data, op)()
        with pytest.raises(TypeError, match=msg):
            # Check that this is still the numpy behavior
            getattr(data._data, op)()

        return

    result = getattr(ser, op)()
    expected = result.copy(deep=True)
    ser[0] = None
    tm.assert_series_equal(result, expected)
