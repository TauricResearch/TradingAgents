from datetime import datetime

import numpy as np
import pytest

from pandas._libs import iNaT

import pandas._testing as tm
import pandas.core.algorithms as algos


@pytest.fixture(
    params=[
        (np.int8, np.int16(127), np.int8),
        (np.int8, np.int16(128), np.int16),
        (np.int32, 1, np.int32),
        (np.int32, 2.0, np.float64),
        (np.int32, 3.0 + 4.0j, np.complex128),
        (np.int32, True, np.object_),
        (np.int32, "", np.object_),
        (np.float64, 1, np.float64),
        (np.float64, 2.0, np.float64),
        (np.float64, 3.0 + 4.0j, np.complex128),
        (np.float64, True, np.object_),
        (np.float64, "", np.object_),
        (np.complex128, 1, np.complex128),
        (np.complex128, 2.0, np.complex128),
        (np.complex128, 3.0 + 4.0j, np.complex128),
        (np.complex128, True, np.object_),
        (np.complex128, "", np.object_),
        (np.bool_, 1, np.object_),
        (np.bool_, 2.0, np.object_),
        (np.bool_, 3.0 + 4.0j, np.object_),
        (np.bool_, True, np.bool_),
        (np.bool_, "", np.object_),
    ]
)
def dtype_fill_out_dtype(request):
    return request.param


class TestTake:
    def test_1d_fill_nonna(self, dtype_fill_out_dtype):
        dtype, fill_value, out_dtype = dtype_fill_out_dtype
        data = np.random.default_rng(2).integers(0, 2, 4).astype(dtype)
        indexer = [2, 1, 0, -1]

        result = algos.take_nd(data, indexer, fill_value=fill_value)
        assert (result[[0, 1, 2]] == data[[2, 1, 0]]).all()
        assert result[3] == fill_value
        assert result.dtype == out_dtype

        indexer = [2, 1, 0, 1]

        result = algos.take_nd(data, indexer, fill_value=fill_value)
        assert (result[[0, 1, 2, 3]] == data[indexer]).all()
        assert result.dtype == dtype

    def test_2d_fill_nonna(self, dtype_fill_out_dtype):
        dtype, fill_value, out_dtype = dtype_fill_out_dtype
        data = np.random.default_rng(2).integers(0, 2, (5, 3)).astype(dtype)
        indexer = [2, 1, 0, -1]

        result = algos.take_nd(data, indexer, axis=0, fill_value=fill_value)
        assert (result[[0, 1, 2], :] == data[[2, 1, 0], :]).all()
        assert (result[3, :] == fill_value).all()
        assert result.dtype == out_dtype

        result = algos.take_nd(data, indexer, axis=1, fill_value=fill_value)
        assert (result[:, [0, 1, 2]] == data[:, [2, 1, 0]]).all()
        assert (result[:, 3] == fill_value).all()
        assert result.dtype == out_dtype

        indexer = [2, 1, 0, 1]
        result = algos.take_nd(data, indexer, axis=0, fill_value=fill_value)
        assert (result[[0, 1, 2, 3], :] == data[indexer, :]).all()
        assert result.dtype == dtype

        result = algos.take_nd(data, indexer, axis=1, fill_value=fill_value)
        assert (result[:, [0, 1, 2, 3]] == data[:, indexer]).all()
        assert result.dtype == dtype

    def test_3d_fill_nonna(self, dtype_fill_out_dtype):
        dtype, fill_value, out_dtype = dtype_fill_out_dtype

        data = np.random.default_rng(2).integers(0, 2, (5, 4, 3)).astype(dtype)
        indexer = [2, 1, 0, -1]

        result = algos.take_nd(data, indexer, axis=0, fill_value=fill_value)
        assert (result[[0, 1, 2], :, :] == data[[2, 1, 0], :, :]).all()
        assert (result[3, :, :] == fill_value).all()
        assert result.dtype == out_dtype

        result = algos.take_nd(data, indexer, axis=1, fill_value=fill_value)
        assert (result[:, [0, 1, 2], :] == data[:, [2, 1, 0], :]).all()
        assert (result[:, 3, :] == fill_value).all()
        assert result.dtype == out_dtype

        result = algos.take_nd(data, indexer, axis=2, fill_value=fill_value)
        assert (result[:, :, [0, 1, 2]] == data[:, :, [2, 1, 0]]).all()
        assert (result[:, :, 3] == fill_value).all()
        assert result.dtype == out_dtype

        indexer = [2, 1, 0, 1]
        result = algos.take_nd(data, indexer, axis=0, fill_value=fill_value)
        assert (result[[0, 1, 2, 3], :, :] == data[indexer, :, :]).all()
        assert result.dtype == dtype

        result = algos.take_nd(data, indexer, axis=1, fill_value=fill_value)
        assert (result[:, [0, 1, 2, 3], :] == data[:, indexer, :]).all()
        assert result.dtype == dtype

        result = algos.take_nd(data, indexer, axis=2, fill_value=fill_value)
        assert (result[:, :, [0, 1, 2, 3]] == data[:, :, indexer]).all()
        assert result.dtype == dtype

    def test_1d_other_dtypes(self):
        arr = np.random.default_rng(2).standard_normal(10).astype(np.float32)

        indexer = [1, 2, 3, -1]
        result = algos.take_nd(arr, indexer)
        expected = arr.take(indexer)
        expected[-1] = np.nan
        tm.assert_almost_equal(result, expected)

    def test_2d_other_dtypes(self):
        arr = np.random.default_rng(2).standard_normal((10, 5)).astype(np.float32)

        indexer = [1, 2, 3, -1]

        # axis=0
        result = algos.take_nd(arr, indexer, axis=0)
        expected = arr.take(indexer, axis=0)
        expected[-1] = np.nan
        tm.assert_almost_equal(result, expected)

        # axis=1
        result = algos.take_nd(arr, indexer, axis=1)
        expected = arr.take(indexer, axis=1)
        expected[:, -1] = np.nan
        tm.assert_almost_equal(result, expected)

    def test_1d_bool(self):
        arr = np.array([0, 1, 0], dtype=bool)

        result = algos.take_nd(arr, [0, 2, 2, 1])
        expected = arr.take([0, 2, 2, 1])
        tm.assert_numpy_array_equal(result, expected)

        result = algos.take_nd(arr, [0, 2, -1])
        assert result.dtype == np.object_

    def test_2d_bool(self):
        arr = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 1]], dtype=bool)

        result = algos.take_nd(arr, [0, 2, 2, 1])
        expected = arr.take([0, 2, 2, 1], axis=0)
        tm.assert_numpy_array_equal(result, expected)

        result = algos.take_nd(arr, [0, 2, 2, 1], axis=1)
        expected = arr.take([0, 2, 2, 1], axis=1)
        tm.assert_numpy_array_equal(result, expected)

        result = algos.take_nd(arr, [0, 2, -1])
        assert result.dtype == np.object_

    def test_2d_float32(self):
        arr = np.random.default_rng(2).standard_normal((4, 3)).astype(np.float32)
        indexer = [0, 2, -1, 1, -1]

        # axis=0
        result = algos.take_nd(arr, indexer, axis=0)

        expected = arr.take(indexer, axis=0)
        expected[[2, 4], :] = np.nan
        tm.assert_almost_equal(result, expected)

        # axis=1
        result = algos.take_nd(arr, indexer, axis=1)
        expected = arr.take(indexer, axis=1)
        expected[:, [2, 4]] = np.nan
        tm.assert_almost_equal(result, expected)

    def test_2d_datetime64(self):
        # 2005/01/01 - 2006/01/01
        arr = (
            np.random.default_rng(2).integers(11_045_376, 11_360_736, (5, 3))
            * 100_000_000_000
        )
        arr = arr.view(dtype="datetime64[ns]")
        indexer = [0, 2, -1, 1, -1]

        # axis=0
        result = algos.take_nd(arr, indexer, axis=0)
        expected = arr.take(indexer, axis=0)
        expected.view(np.int64)[[2, 4], :] = iNaT
        tm.assert_almost_equal(result, expected)

        result = algos.take_nd(arr, indexer, axis=0, fill_value=datetime(2007, 1, 1))
        expected = arr.take(indexer, axis=0)
        expected[[2, 4], :] = datetime(2007, 1, 1)
        tm.assert_almost_equal(result, expected)

        # axis=1
        result = algos.take_nd(arr, indexer, axis=1)
        expected = arr.take(indexer, axis=1)
        expected.view(np.int64)[:, [2, 4]] = iNaT
        tm.assert_almost_equal(result, expected)

        result = algos.take_nd(arr, indexer, axis=1, fill_value=datetime(2007, 1, 1))
        expected = arr.take(indexer, axis=1)
        expected[:, [2, 4]] = datetime(2007, 1, 1)
        tm.assert_almost_equal(result, expected)

    def test_take_axis_0(self):
        arr = np.arange(12).reshape(4, 3)
        result = algos.take(arr, [0, -1])
        expected = np.array([[0, 1, 2], [9, 10, 11]])
        tm.assert_numpy_array_equal(result, expected)

        # allow_fill=True
        result = algos.take(arr, [0, -1], allow_fill=True, fill_value=0)
        expected = np.array([[0, 1, 2], [0, 0, 0]])
        tm.assert_numpy_array_equal(result, expected)

    def test_take_axis_1(self):
        arr = np.arange(12).reshape(4, 3)
        result = algos.take(arr, [0, -1], axis=1)
        expected = np.array([[0, 2], [3, 5], [6, 8], [9, 11]])
        tm.assert_numpy_array_equal(result, expected)

        # allow_fill=True
        result = algos.take(arr, [0, -1], axis=1, allow_fill=True, fill_value=0)
        expected = np.array([[0, 0], [3, 0], [6, 0], [9, 0]])
        tm.assert_numpy_array_equal(result, expected)

        # GH#26976 make sure we validate along the correct axis
        with pytest.raises(IndexError, match="indices are out-of-bounds"):
            algos.take(arr, [0, 3], axis=1, allow_fill=True, fill_value=0)

    def test_take_non_hashable_fill_value(self):
        arr = np.array([1, 2, 3])
        indexer = np.array([1, -1])
        with pytest.raises(ValueError, match="fill_value must be a scalar"):
            algos.take(arr, indexer, allow_fill=True, fill_value=[1])

        # with object dtype it is allowed
        arr = np.array([1, 2, 3], dtype=object)
        result = algos.take(arr, indexer, allow_fill=True, fill_value=[1])
        expected = np.array([2, [1]], dtype=object)
        tm.assert_numpy_array_equal(result, expected)


class TestExtensionTake:
    # The take method found in pd.api.extensions

    def test_bounds_check_large(self):
        arr = np.array([1, 2])

        msg = "indices are out-of-bounds"
        with pytest.raises(IndexError, match=msg):
            algos.take(arr, [2, 3], allow_fill=True)

        msg = "index 2 is out of bounds for( axis 0 with)? size 2"
        with pytest.raises(IndexError, match=msg):
            algos.take(arr, [2, 3], allow_fill=False)

    def test_bounds_check_small(self):
        arr = np.array([1, 2, 3], dtype=np.int64)
        indexer = [0, -1, -2]

        msg = r"'indices' contains values less than allowed \(-2 < -1\)"
        with pytest.raises(ValueError, match=msg):
            algos.take(arr, indexer, allow_fill=True)

        result = algos.take(arr, indexer)
        expected = np.array([1, 3, 2], dtype=np.int64)
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize("allow_fill", [True, False])
    def test_take_empty(self, allow_fill):
        arr = np.array([], dtype=np.int64)
        # empty take is ok
        result = algos.take(arr, [], allow_fill=allow_fill)
        tm.assert_numpy_array_equal(arr, result)

        msg = "|".join(
            [
                "cannot do a non-empty take from an empty axes.",
                "indices are out-of-bounds",
            ]
        )
        with pytest.raises(IndexError, match=msg):
            algos.take(arr, [0], allow_fill=allow_fill)

    def test_take_na_empty(self):
        result = algos.take(np.array([]), [-1, -1], allow_fill=True, fill_value=0.0)
        expected = np.array([0.0, 0.0])
        tm.assert_numpy_array_equal(result, expected)

    def test_take_coerces_list(self):
        arr = [1, 2, 3]
        msg = "take accepting non-standard inputs is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = algos.take(arr, [0, 0])
        expected = np.array([1, 1])
        tm.assert_numpy_array_equal(result, expected)
