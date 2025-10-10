import numpy as np
import pytest

from pandas import (
    CategoricalDtype,
    DataFrame,
)
import pandas._testing as tm


def test_transpose(index_or_series_obj):
    obj = index_or_series_obj
    tm.assert_equal(obj.transpose(), obj)


def test_transpose_non_default_axes(index_or_series_obj):
    msg = "the 'axes' parameter is not supported"
    obj = index_or_series_obj
    with pytest.raises(ValueError, match=msg):
        obj.transpose(1)
    with pytest.raises(ValueError, match=msg):
        obj.transpose(axes=1)


def test_numpy_transpose(index_or_series_obj):
    msg = "the 'axes' parameter is not supported"
    obj = index_or_series_obj
    tm.assert_equal(np.transpose(obj), obj)

    with pytest.raises(ValueError, match=msg):
        np.transpose(obj, axes=1)


@pytest.mark.parametrize(
    "data, transposed_data, index, columns, dtype",
    [
        ([[1], [2]], [[1, 2]], ["a", "a"], ["b"], int),
        ([[1], [2]], [[1, 2]], ["a", "a"], ["b"], CategoricalDtype([1, 2])),
        ([[1, 2]], [[1], [2]], ["b"], ["a", "a"], int),
        ([[1, 2]], [[1], [2]], ["b"], ["a", "a"], CategoricalDtype([1, 2])),
        ([[1, 2], [3, 4]], [[1, 3], [2, 4]], ["a", "a"], ["b", "b"], int),
        (
            [[1, 2], [3, 4]],
            [[1, 3], [2, 4]],
            ["a", "a"],
            ["b", "b"],
            CategoricalDtype([1, 2, 3, 4]),
        ),
    ],
)
def test_duplicate_labels(data, transposed_data, index, columns, dtype):
    # GH 42380
    df = DataFrame(data, index=index, columns=columns, dtype=dtype)
    result = df.T
    expected = DataFrame(transposed_data, index=columns, columns=index, dtype=dtype)
    tm.assert_frame_equal(result, expected)
