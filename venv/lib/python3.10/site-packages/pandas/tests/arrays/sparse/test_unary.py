import operator

import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays import SparseArray


@pytest.mark.filterwarnings("ignore:invalid value encountered in cast:RuntimeWarning")
@pytest.mark.parametrize("fill_value", [0, np.nan])
@pytest.mark.parametrize("op", [operator.pos, operator.neg])
def test_unary_op(op, fill_value):
    arr = np.array([0, 1, np.nan, 2])
    sparray = SparseArray(arr, fill_value=fill_value)
    result = op(sparray)
    expected = SparseArray(op(arr), fill_value=op(fill_value))
    tm.assert_sp_array_equal(result, expected)


@pytest.mark.parametrize("fill_value", [True, False])
def test_invert(fill_value):
    arr = np.array([True, False, False, True])
    sparray = SparseArray(arr, fill_value=fill_value)
    result = ~sparray
    expected = SparseArray(~arr, fill_value=not fill_value)
    tm.assert_sp_array_equal(result, expected)

    result = ~pd.Series(sparray)
    expected = pd.Series(expected)
    tm.assert_series_equal(result, expected)

    result = ~pd.DataFrame({"A": sparray})
    expected = pd.DataFrame({"A": expected})
    tm.assert_frame_equal(result, expected)


class TestUnaryMethods:
    @pytest.mark.filterwarnings(
        "ignore:invalid value encountered in cast:RuntimeWarning"
    )
    def test_neg_operator(self):
        arr = SparseArray([-1, -2, np.nan, 3], fill_value=np.nan, dtype=np.int8)
        res = -arr
        exp = SparseArray([1, 2, np.nan, -3], fill_value=np.nan, dtype=np.int8)
        tm.assert_sp_array_equal(exp, res)

        arr = SparseArray([-1, -2, 1, 3], fill_value=-1, dtype=np.int8)
        res = -arr
        exp = SparseArray([1, 2, -1, -3], fill_value=1, dtype=np.int8)
        tm.assert_sp_array_equal(exp, res)

    @pytest.mark.filterwarnings(
        "ignore:invalid value encountered in cast:RuntimeWarning"
    )
    def test_abs_operator(self):
        arr = SparseArray([-1, -2, np.nan, 3], fill_value=np.nan, dtype=np.int8)
        res = abs(arr)
        exp = SparseArray([1, 2, np.nan, 3], fill_value=np.nan, dtype=np.int8)
        tm.assert_sp_array_equal(exp, res)

        arr = SparseArray([-1, -2, 1, 3], fill_value=-1, dtype=np.int8)
        res = abs(arr)
        exp = SparseArray([1, 2, 1, 3], fill_value=1, dtype=np.int8)
        tm.assert_sp_array_equal(exp, res)

    def test_invert_operator(self):
        arr = SparseArray([False, True, False, True], fill_value=False, dtype=np.bool_)
        exp = SparseArray(
            np.invert([False, True, False, True]), fill_value=True, dtype=np.bool_
        )
        res = ~arr
        tm.assert_sp_array_equal(exp, res)

        arr = SparseArray([0, 1, 0, 2, 3, 0], fill_value=0, dtype=np.int32)
        res = ~arr
        exp = SparseArray([-1, -2, -1, -3, -4, -1], fill_value=-1, dtype=np.int32)
        tm.assert_sp_array_equal(exp, res)
