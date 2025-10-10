"""
Tests for np.foo applied to DataFrame, not necessarily ufuncs.
"""
import numpy as np

from pandas import (
    Categorical,
    DataFrame,
)
import pandas._testing as tm


class TestAsArray:
    def test_asarray_homogeneous(self):
        df = DataFrame({"A": Categorical([1, 2]), "B": Categorical([1, 2])})
        result = np.asarray(df)
        # may change from object in the future
        expected = np.array([[1, 1], [2, 2]], dtype="object")
        tm.assert_numpy_array_equal(result, expected)

    def test_np_sqrt(self, float_frame):
        with np.errstate(all="ignore"):
            result = np.sqrt(float_frame)
        assert isinstance(result, type(float_frame))
        assert result.index.is_(float_frame.index)
        assert result.columns.is_(float_frame.columns)

        tm.assert_frame_equal(result, float_frame.apply(np.sqrt))

    def test_sum_deprecated_axis_behavior(self):
        # GH#52042 deprecated behavior of df.sum(axis=None), which gets
        #  called when we do np.sum(df)

        arr = np.random.default_rng(2).standard_normal((4, 3))
        df = DataFrame(arr)

        msg = "The behavior of DataFrame.sum with axis=None is deprecated"
        with tm.assert_produces_warning(
            FutureWarning, match=msg, check_stacklevel=False
        ):
            res = np.sum(df)

        with tm.assert_produces_warning(FutureWarning, match=msg):
            expected = df.sum(axis=None)
        tm.assert_series_equal(res, expected)

    def test_np_ravel(self):
        # GH26247
        arr = np.array(
            [
                [0.11197053, 0.44361564, -0.92589452],
                [0.05883648, -0.00948922, -0.26469934],
            ]
        )

        result = np.ravel([DataFrame(batch.reshape(1, 3)) for batch in arr])
        expected = np.array(
            [
                0.11197053,
                0.44361564,
                -0.92589452,
                0.05883648,
                -0.00948922,
                -0.26469934,
            ]
        )
        tm.assert_numpy_array_equal(result, expected)

        result = np.ravel(DataFrame(arr[0].reshape(1, 3), columns=["x1", "x2", "x3"]))
        expected = np.array([0.11197053, 0.44361564, -0.92589452])
        tm.assert_numpy_array_equal(result, expected)

        result = np.ravel(
            [
                DataFrame(batch.reshape(1, 3), columns=["x1", "x2", "x3"])
                for batch in arr
            ]
        )
        expected = np.array(
            [
                0.11197053,
                0.44361564,
                -0.92589452,
                0.05883648,
                -0.00948922,
                -0.26469934,
            ]
        )
        tm.assert_numpy_array_equal(result, expected)
