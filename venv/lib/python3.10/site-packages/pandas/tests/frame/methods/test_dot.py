import numpy as np
import pytest

from pandas import (
    DataFrame,
    Series,
)
import pandas._testing as tm


class DotSharedTests:
    @pytest.fixture
    def obj(self):
        raise NotImplementedError

    @pytest.fixture
    def other(self) -> DataFrame:
        """
        other is a DataFrame that is indexed so that obj.dot(other) is valid
        """
        raise NotImplementedError

    @pytest.fixture
    def expected(self, obj, other) -> DataFrame:
        """
        The expected result of obj.dot(other)
        """
        raise NotImplementedError

    @classmethod
    def reduced_dim_assert(cls, result, expected):
        """
        Assertion about results with 1 fewer dimension that self.obj
        """
        raise NotImplementedError

    def test_dot_equiv_values_dot(self, obj, other, expected):
        # `expected` is constructed from obj.values.dot(other.values)
        result = obj.dot(other)
        tm.assert_equal(result, expected)

    def test_dot_2d_ndarray(self, obj, other, expected):
        # Check ndarray argument; in this case we get matching values,
        #  but index/columns may not match
        result = obj.dot(other.values)
        assert np.all(result == expected.values)

    def test_dot_1d_ndarray(self, obj, expected):
        # can pass correct-length array
        row = obj.iloc[0] if obj.ndim == 2 else obj

        result = obj.dot(row.values)
        expected = obj.dot(row)
        self.reduced_dim_assert(result, expected)

    def test_dot_series(self, obj, other, expected):
        # Check series argument
        result = obj.dot(other["1"])
        self.reduced_dim_assert(result, expected["1"])

    def test_dot_series_alignment(self, obj, other, expected):
        result = obj.dot(other.iloc[::-1]["1"])
        self.reduced_dim_assert(result, expected["1"])

    def test_dot_aligns(self, obj, other, expected):
        # Check index alignment
        other2 = other.iloc[::-1]
        result = obj.dot(other2)
        tm.assert_equal(result, expected)

    def test_dot_shape_mismatch(self, obj):
        msg = "Dot product shape mismatch"
        # exception raised is of type Exception
        with pytest.raises(Exception, match=msg):
            obj.dot(obj.values[:3])

    def test_dot_misaligned(self, obj, other):
        msg = "matrices are not aligned"
        with pytest.raises(ValueError, match=msg):
            obj.dot(other.T)


class TestSeriesDot(DotSharedTests):
    @pytest.fixture
    def obj(self):
        return Series(
            np.random.default_rng(2).standard_normal(4), index=["p", "q", "r", "s"]
        )

    @pytest.fixture
    def other(self):
        return DataFrame(
            np.random.default_rng(2).standard_normal((3, 4)),
            index=["1", "2", "3"],
            columns=["p", "q", "r", "s"],
        ).T

    @pytest.fixture
    def expected(self, obj, other):
        return Series(np.dot(obj.values, other.values), index=other.columns)

    @classmethod
    def reduced_dim_assert(cls, result, expected):
        """
        Assertion about results with 1 fewer dimension that self.obj
        """
        tm.assert_almost_equal(result, expected)


class TestDataFrameDot(DotSharedTests):
    @pytest.fixture
    def obj(self):
        return DataFrame(
            np.random.default_rng(2).standard_normal((3, 4)),
            index=["a", "b", "c"],
            columns=["p", "q", "r", "s"],
        )

    @pytest.fixture
    def other(self):
        return DataFrame(
            np.random.default_rng(2).standard_normal((4, 2)),
            index=["p", "q", "r", "s"],
            columns=["1", "2"],
        )

    @pytest.fixture
    def expected(self, obj, other):
        return DataFrame(
            np.dot(obj.values, other.values), index=obj.index, columns=other.columns
        )

    @classmethod
    def reduced_dim_assert(cls, result, expected):
        """
        Assertion about results with 1 fewer dimension that self.obj
        """
        tm.assert_series_equal(result, expected, check_names=False)
        assert result.name is None


@pytest.mark.parametrize(
    "dtype,exp_dtype",
    [("Float32", "Float64"), ("Int16", "Int32"), ("float[pyarrow]", "double[pyarrow]")],
)
def test_arrow_dtype(dtype, exp_dtype):
    pytest.importorskip("pyarrow")

    cols = ["a", "b"]
    df_a = DataFrame([[1, 2], [3, 4], [5, 6]], columns=cols, dtype="int32")
    df_b = DataFrame([[1, 0], [0, 1]], index=cols, dtype=dtype)
    result = df_a.dot(df_b)
    expected = DataFrame([[1, 2], [3, 4], [5, 6]], dtype=exp_dtype)

    tm.assert_frame_equal(result, expected)
