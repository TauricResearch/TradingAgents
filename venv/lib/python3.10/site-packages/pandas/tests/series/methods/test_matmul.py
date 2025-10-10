import operator

import numpy as np
import pytest

from pandas import (
    DataFrame,
    Series,
)
import pandas._testing as tm


class TestMatmul:
    def test_matmul(self):
        # matmul test is for GH#10259
        a = Series(
            np.random.default_rng(2).standard_normal(4), index=["p", "q", "r", "s"]
        )
        b = DataFrame(
            np.random.default_rng(2).standard_normal((3, 4)),
            index=["1", "2", "3"],
            columns=["p", "q", "r", "s"],
        ).T

        # Series @ DataFrame -> Series
        result = operator.matmul(a, b)
        expected = Series(np.dot(a.values, b.values), index=["1", "2", "3"])
        tm.assert_series_equal(result, expected)

        # DataFrame @ Series -> Series
        result = operator.matmul(b.T, a)
        expected = Series(np.dot(b.T.values, a.T.values), index=["1", "2", "3"])
        tm.assert_series_equal(result, expected)

        # Series @ Series -> scalar
        result = operator.matmul(a, a)
        expected = np.dot(a.values, a.values)
        tm.assert_almost_equal(result, expected)

        # GH#21530
        # vector (1D np.array) @ Series (__rmatmul__)
        result = operator.matmul(a.values, a)
        expected = np.dot(a.values, a.values)
        tm.assert_almost_equal(result, expected)

        # GH#21530
        # vector (1D list) @ Series (__rmatmul__)
        result = operator.matmul(a.values.tolist(), a)
        expected = np.dot(a.values, a.values)
        tm.assert_almost_equal(result, expected)

        # GH#21530
        # matrix (2D np.array) @ Series (__rmatmul__)
        result = operator.matmul(b.T.values, a)
        expected = np.dot(b.T.values, a.values)
        tm.assert_almost_equal(result, expected)

        # GH#21530
        # matrix (2D nested lists) @ Series (__rmatmul__)
        result = operator.matmul(b.T.values.tolist(), a)
        expected = np.dot(b.T.values, a.values)
        tm.assert_almost_equal(result, expected)

        # mixed dtype DataFrame @ Series
        a["p"] = int(a.p)
        result = operator.matmul(b.T, a)
        expected = Series(np.dot(b.T.values, a.T.values), index=["1", "2", "3"])
        tm.assert_series_equal(result, expected)

        # different dtypes DataFrame @ Series
        a = a.astype(int)
        result = operator.matmul(b.T, a)
        expected = Series(np.dot(b.T.values, a.T.values), index=["1", "2", "3"])
        tm.assert_series_equal(result, expected)

        msg = r"Dot product shape mismatch, \(4,\) vs \(3,\)"
        # exception raised is of type Exception
        with pytest.raises(Exception, match=msg):
            a.dot(a.values[:3])
        msg = "matrices are not aligned"
        with pytest.raises(ValueError, match=msg):
            a.dot(b.T)
