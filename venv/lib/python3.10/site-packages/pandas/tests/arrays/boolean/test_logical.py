import operator

import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.arrays import BooleanArray
from pandas.core.ops.mask_ops import (
    kleene_and,
    kleene_or,
    kleene_xor,
)
from pandas.tests.extension.base import BaseOpsUtil


class TestLogicalOps(BaseOpsUtil):
    def test_numpy_scalars_ok(self, all_logical_operators):
        a = pd.array([True, False, None], dtype="boolean")
        op = getattr(a, all_logical_operators)

        tm.assert_extension_array_equal(op(True), op(np.bool_(True)))
        tm.assert_extension_array_equal(op(False), op(np.bool_(False)))

    def get_op_from_name(self, op_name):
        short_opname = op_name.strip("_")
        short_opname = short_opname if "xor" in short_opname else short_opname + "_"
        try:
            op = getattr(operator, short_opname)
        except AttributeError:
            # Assume it is the reverse operator
            rop = getattr(operator, short_opname[1:])
            op = lambda x, y: rop(y, x)

        return op

    def test_empty_ok(self, all_logical_operators):
        a = pd.array([], dtype="boolean")
        op_name = all_logical_operators
        result = getattr(a, op_name)(True)
        tm.assert_extension_array_equal(a, result)

        result = getattr(a, op_name)(False)
        tm.assert_extension_array_equal(a, result)

        result = getattr(a, op_name)(pd.NA)
        tm.assert_extension_array_equal(a, result)

    @pytest.mark.parametrize(
        "other", ["a", pd.Timestamp(2017, 1, 1, 12), np.timedelta64(4)]
    )
    def test_eq_mismatched_type(self, other):
        # GH-44499
        arr = pd.array([True, False])
        result = arr == other
        expected = pd.array([False, False])
        tm.assert_extension_array_equal(result, expected)

        result = arr != other
        expected = pd.array([True, True])
        tm.assert_extension_array_equal(result, expected)

    def test_logical_length_mismatch_raises(self, all_logical_operators):
        op_name = all_logical_operators
        a = pd.array([True, False, None], dtype="boolean")
        msg = "Lengths must match"

        with pytest.raises(ValueError, match=msg):
            getattr(a, op_name)([True, False])

        with pytest.raises(ValueError, match=msg):
            getattr(a, op_name)(np.array([True, False]))

        with pytest.raises(ValueError, match=msg):
            getattr(a, op_name)(pd.array([True, False], dtype="boolean"))

    def test_logical_nan_raises(self, all_logical_operators):
        op_name = all_logical_operators
        a = pd.array([True, False, None], dtype="boolean")
        msg = "Got float instead"

        with pytest.raises(TypeError, match=msg):
            getattr(a, op_name)(np.nan)

    @pytest.mark.parametrize("other", ["a", 1])
    def test_non_bool_or_na_other_raises(self, other, all_logical_operators):
        a = pd.array([True, False], dtype="boolean")
        with pytest.raises(TypeError, match=str(type(other).__name__)):
            getattr(a, all_logical_operators)(other)

    def test_kleene_or(self):
        # A clear test of behavior.
        a = pd.array([True] * 3 + [False] * 3 + [None] * 3, dtype="boolean")
        b = pd.array([True, False, None] * 3, dtype="boolean")
        result = a | b
        expected = pd.array(
            [True, True, True, True, False, None, True, None, None], dtype="boolean"
        )
        tm.assert_extension_array_equal(result, expected)

        result = b | a
        tm.assert_extension_array_equal(result, expected)

        # ensure we haven't mutated anything inplace
        tm.assert_extension_array_equal(
            a, pd.array([True] * 3 + [False] * 3 + [None] * 3, dtype="boolean")
        )
        tm.assert_extension_array_equal(
            b, pd.array([True, False, None] * 3, dtype="boolean")
        )

    @pytest.mark.parametrize(
        "other, expected",
        [
            (pd.NA, [True, None, None]),
            (True, [True, True, True]),
            (np.bool_(True), [True, True, True]),
            (False, [True, False, None]),
            (np.bool_(False), [True, False, None]),
        ],
    )
    def test_kleene_or_scalar(self, other, expected):
        # TODO: test True & False
        a = pd.array([True, False, None], dtype="boolean")
        result = a | other
        expected = pd.array(expected, dtype="boolean")
        tm.assert_extension_array_equal(result, expected)

        result = other | a
        tm.assert_extension_array_equal(result, expected)

        # ensure we haven't mutated anything inplace
        tm.assert_extension_array_equal(
            a, pd.array([True, False, None], dtype="boolean")
        )

    def test_kleene_and(self):
        # A clear test of behavior.
        a = pd.array([True] * 3 + [False] * 3 + [None] * 3, dtype="boolean")
        b = pd.array([True, False, None] * 3, dtype="boolean")
        result = a & b
        expected = pd.array(
            [True, False, None, False, False, False, None, False, None], dtype="boolean"
        )
        tm.assert_extension_array_equal(result, expected)

        result = b & a
        tm.assert_extension_array_equal(result, expected)

        # ensure we haven't mutated anything inplace
        tm.assert_extension_array_equal(
            a, pd.array([True] * 3 + [False] * 3 + [None] * 3, dtype="boolean")
        )
        tm.assert_extension_array_equal(
            b, pd.array([True, False, None] * 3, dtype="boolean")
        )

    @pytest.mark.parametrize(
        "other, expected",
        [
            (pd.NA, [None, False, None]),
            (True, [True, False, None]),
            (False, [False, False, False]),
            (np.bool_(True), [True, False, None]),
            (np.bool_(False), [False, False, False]),
        ],
    )
    def test_kleene_and_scalar(self, other, expected):
        a = pd.array([True, False, None], dtype="boolean")
        result = a & other
        expected = pd.array(expected, dtype="boolean")
        tm.assert_extension_array_equal(result, expected)

        result = other & a
        tm.assert_extension_array_equal(result, expected)

        # ensure we haven't mutated anything inplace
        tm.assert_extension_array_equal(
            a, pd.array([True, False, None], dtype="boolean")
        )

    def test_kleene_xor(self):
        a = pd.array([True] * 3 + [False] * 3 + [None] * 3, dtype="boolean")
        b = pd.array([True, False, None] * 3, dtype="boolean")
        result = a ^ b
        expected = pd.array(
            [False, True, None, True, False, None, None, None, None], dtype="boolean"
        )
        tm.assert_extension_array_equal(result, expected)

        result = b ^ a
        tm.assert_extension_array_equal(result, expected)

        # ensure we haven't mutated anything inplace
        tm.assert_extension_array_equal(
            a, pd.array([True] * 3 + [False] * 3 + [None] * 3, dtype="boolean")
        )
        tm.assert_extension_array_equal(
            b, pd.array([True, False, None] * 3, dtype="boolean")
        )

    @pytest.mark.parametrize(
        "other, expected",
        [
            (pd.NA, [None, None, None]),
            (True, [False, True, None]),
            (np.bool_(True), [False, True, None]),
            (np.bool_(False), [True, False, None]),
        ],
    )
    def test_kleene_xor_scalar(self, other, expected):
        a = pd.array([True, False, None], dtype="boolean")
        result = a ^ other
        expected = pd.array(expected, dtype="boolean")
        tm.assert_extension_array_equal(result, expected)

        result = other ^ a
        tm.assert_extension_array_equal(result, expected)

        # ensure we haven't mutated anything inplace
        tm.assert_extension_array_equal(
            a, pd.array([True, False, None], dtype="boolean")
        )

    @pytest.mark.parametrize("other", [True, False, pd.NA, [True, False, None] * 3])
    def test_no_masked_assumptions(self, other, all_logical_operators):
        # The logical operations should not assume that masked values are False!
        a = pd.arrays.BooleanArray(
            np.array([True, True, True, False, False, False, True, False, True]),
            np.array([False] * 6 + [True, True, True]),
        )
        b = pd.array([True] * 3 + [False] * 3 + [None] * 3, dtype="boolean")
        if isinstance(other, list):
            other = pd.array(other, dtype="boolean")

        result = getattr(a, all_logical_operators)(other)
        expected = getattr(b, all_logical_operators)(other)
        tm.assert_extension_array_equal(result, expected)

        if isinstance(other, BooleanArray):
            other._data[other._mask] = True
            a._data[a._mask] = False

            result = getattr(a, all_logical_operators)(other)
            expected = getattr(b, all_logical_operators)(other)
            tm.assert_extension_array_equal(result, expected)


@pytest.mark.parametrize("operation", [kleene_or, kleene_xor, kleene_and])
def test_error_both_scalar(operation):
    msg = r"Either `left` or `right` need to be a np\.ndarray."
    with pytest.raises(TypeError, match=msg):
        # masks need to be non-None, otherwise it ends up in an infinite recursion
        operation(True, True, np.zeros(1), np.zeros(1))
