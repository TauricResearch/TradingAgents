import numpy as np
import pytest

from pandas import (
    DataFrame,
    Index,
    Series,
)
import pandas._testing as tm
from pandas.tests.copy_view.util import get_array


def index_view(index_data=[1, 2]):
    df = DataFrame({"a": index_data, "b": 1.5})
    view = df[:]
    df = df.set_index("a", drop=True)
    idx = df.index
    # df = None
    return idx, view


def test_set_index_update_column(using_copy_on_write, warn_copy_on_write):
    df = DataFrame({"a": [1, 2], "b": 1})
    df = df.set_index("a", drop=False)
    expected = df.index.copy(deep=True)
    with tm.assert_cow_warning(warn_copy_on_write):
        df.iloc[0, 0] = 100
    if using_copy_on_write:
        tm.assert_index_equal(df.index, expected)
    else:
        tm.assert_index_equal(df.index, Index([100, 2], name="a"))


def test_set_index_drop_update_column(using_copy_on_write):
    df = DataFrame({"a": [1, 2], "b": 1.5})
    view = df[:]
    df = df.set_index("a", drop=True)
    expected = df.index.copy(deep=True)
    view.iloc[0, 0] = 100
    tm.assert_index_equal(df.index, expected)


def test_set_index_series(using_copy_on_write, warn_copy_on_write):
    df = DataFrame({"a": [1, 2], "b": 1.5})
    ser = Series([10, 11])
    df = df.set_index(ser)
    expected = df.index.copy(deep=True)
    with tm.assert_cow_warning(warn_copy_on_write):
        ser.iloc[0] = 100
    if using_copy_on_write:
        tm.assert_index_equal(df.index, expected)
    else:
        tm.assert_index_equal(df.index, Index([100, 11]))


def test_assign_index_as_series(using_copy_on_write, warn_copy_on_write):
    df = DataFrame({"a": [1, 2], "b": 1.5})
    ser = Series([10, 11])
    df.index = ser
    expected = df.index.copy(deep=True)
    with tm.assert_cow_warning(warn_copy_on_write):
        ser.iloc[0] = 100
    if using_copy_on_write:
        tm.assert_index_equal(df.index, expected)
    else:
        tm.assert_index_equal(df.index, Index([100, 11]))


def test_assign_index_as_index(using_copy_on_write, warn_copy_on_write):
    df = DataFrame({"a": [1, 2], "b": 1.5})
    ser = Series([10, 11])
    rhs_index = Index(ser)
    df.index = rhs_index
    rhs_index = None  # overwrite to clear reference
    expected = df.index.copy(deep=True)
    with tm.assert_cow_warning(warn_copy_on_write):
        ser.iloc[0] = 100
    if using_copy_on_write:
        tm.assert_index_equal(df.index, expected)
    else:
        tm.assert_index_equal(df.index, Index([100, 11]))


def test_index_from_series(using_copy_on_write, warn_copy_on_write):
    ser = Series([1, 2])
    idx = Index(ser)
    expected = idx.copy(deep=True)
    with tm.assert_cow_warning(warn_copy_on_write):
        ser.iloc[0] = 100
    if using_copy_on_write:
        tm.assert_index_equal(idx, expected)
    else:
        tm.assert_index_equal(idx, Index([100, 2]))


def test_index_from_series_copy(using_copy_on_write):
    ser = Series([1, 2])
    idx = Index(ser, copy=True)  # noqa: F841
    arr = get_array(ser)
    ser.iloc[0] = 100
    assert np.shares_memory(get_array(ser), arr)


def test_index_from_index(using_copy_on_write, warn_copy_on_write):
    ser = Series([1, 2])
    idx = Index(ser)
    idx = Index(idx)
    expected = idx.copy(deep=True)
    with tm.assert_cow_warning(warn_copy_on_write):
        ser.iloc[0] = 100
    if using_copy_on_write:
        tm.assert_index_equal(idx, expected)
    else:
        tm.assert_index_equal(idx, Index([100, 2]))


@pytest.mark.parametrize(
    "func",
    [
        lambda x: x._shallow_copy(x._values),
        lambda x: x.view(),
        lambda x: x.take([0, 1]),
        lambda x: x.repeat([1, 1]),
        lambda x: x[slice(0, 2)],
        lambda x: x[[0, 1]],
        lambda x: x._getitem_slice(slice(0, 2)),
        lambda x: x.delete([]),
        lambda x: x.rename("b"),
        lambda x: x.astype("Int64", copy=False),
    ],
    ids=[
        "_shallow_copy",
        "view",
        "take",
        "repeat",
        "getitem_slice",
        "getitem_list",
        "_getitem_slice",
        "delete",
        "rename",
        "astype",
    ],
)
def test_index_ops(using_copy_on_write, func, request):
    idx, view_ = index_view()
    expected = idx.copy(deep=True)
    if "astype" in request.node.callspec.id:
        expected = expected.astype("Int64")
    idx = func(idx)
    view_.iloc[0, 0] = 100
    if using_copy_on_write:
        tm.assert_index_equal(idx, expected, check_names=False)


def test_infer_objects(using_copy_on_write):
    idx, view_ = index_view(["a", "b"])
    expected = idx.copy(deep=True)
    idx = idx.infer_objects(copy=False)
    view_.iloc[0, 0] = "aaaa"
    if using_copy_on_write:
        tm.assert_index_equal(idx, expected, check_names=False)


def test_index_to_frame(using_copy_on_write):
    idx = Index([1, 2, 3], name="a")
    expected = idx.copy(deep=True)
    df = idx.to_frame()
    if using_copy_on_write:
        assert np.shares_memory(get_array(df, "a"), idx._values)
        assert not df._mgr._has_no_reference(0)
    else:
        assert not np.shares_memory(get_array(df, "a"), idx._values)

    df.iloc[0, 0] = 100
    tm.assert_index_equal(idx, expected)


def test_index_values(using_copy_on_write):
    idx = Index([1, 2, 3])
    result = idx.values
    if using_copy_on_write:
        assert result.flags.writeable is False
    else:
        assert result.flags.writeable is True
