import re

import pytest

from pandas import (
    ArrowDtype,
    Series,
)
import pandas._testing as tm

pa = pytest.importorskip("pyarrow")

from pandas.compat import pa_version_under11p0


@pytest.mark.parametrize(
    "list_dtype",
    (
        pa.list_(pa.int64()),
        pa.list_(pa.int64(), list_size=3),
        pa.large_list(pa.int64()),
    ),
)
def test_list_getitem(list_dtype):
    ser = Series(
        [[1, 2, 3], [4, None, 5], None],
        dtype=ArrowDtype(list_dtype),
    )
    actual = ser.list[1]
    expected = Series([2, None, None], dtype="int64[pyarrow]")
    tm.assert_series_equal(actual, expected)


def test_list_getitem_slice():
    ser = Series(
        [[1, 2, 3], [4, None, 5], None],
        dtype=ArrowDtype(pa.list_(pa.int64())),
    )
    if pa_version_under11p0:
        with pytest.raises(
            NotImplementedError, match="List slice not supported by pyarrow "
        ):
            ser.list[1:None:None]
    else:
        actual = ser.list[1:None:None]
        expected = Series(
            [[2, 3], [None, 5], None], dtype=ArrowDtype(pa.list_(pa.int64()))
        )
        tm.assert_series_equal(actual, expected)


def test_list_len():
    ser = Series(
        [[1, 2, 3], [4, None], None],
        dtype=ArrowDtype(pa.list_(pa.int64())),
    )
    actual = ser.list.len()
    expected = Series([3, 2, None], dtype=ArrowDtype(pa.int32()))
    tm.assert_series_equal(actual, expected)


def test_list_flatten():
    ser = Series(
        [[1, 2, 3], [4, None], None],
        dtype=ArrowDtype(pa.list_(pa.int64())),
    )
    actual = ser.list.flatten()
    expected = Series([1, 2, 3, 4, None], dtype=ArrowDtype(pa.int64()))
    tm.assert_series_equal(actual, expected)


def test_list_getitem_slice_invalid():
    ser = Series(
        [[1, 2, 3], [4, None, 5], None],
        dtype=ArrowDtype(pa.list_(pa.int64())),
    )
    if pa_version_under11p0:
        with pytest.raises(
            NotImplementedError, match="List slice not supported by pyarrow "
        ):
            ser.list[1:None:0]
    else:
        with pytest.raises(pa.lib.ArrowInvalid, match=re.escape("`step` must be >= 1")):
            ser.list[1:None:0]


def test_list_accessor_non_list_dtype():
    ser = Series(
        [1, 2, 4],
        dtype=ArrowDtype(pa.int64()),
    )
    with pytest.raises(
        AttributeError,
        match=re.escape(
            "Can only use the '.list' accessor with 'list[pyarrow]' dtype, "
            "not int64[pyarrow]."
        ),
    ):
        ser.list[1:None:0]


@pytest.mark.parametrize(
    "list_dtype",
    (
        pa.list_(pa.int64()),
        pa.list_(pa.int64(), list_size=3),
        pa.large_list(pa.int64()),
    ),
)
def test_list_getitem_invalid_index(list_dtype):
    ser = Series(
        [[1, 2, 3], [4, None, 5], None],
        dtype=ArrowDtype(list_dtype),
    )
    with pytest.raises(pa.lib.ArrowInvalid, match="Index -1 is out of bounds"):
        ser.list[-1]
    with pytest.raises(pa.lib.ArrowInvalid, match="Index 5 is out of bounds"):
        ser.list[5]
    with pytest.raises(ValueError, match="key must be an int or slice, got str"):
        ser.list["abc"]


def test_list_accessor_not_iterable():
    ser = Series(
        [[1, 2, 3], [4, None], None],
        dtype=ArrowDtype(pa.list_(pa.int64())),
    )
    with pytest.raises(TypeError, match="'ListAccessor' object is not iterable"):
        iter(ser.list)
