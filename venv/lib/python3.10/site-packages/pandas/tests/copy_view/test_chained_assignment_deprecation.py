import numpy as np
import pytest

from pandas.compat import (
    PY311,
    WARNING_CHECK_DISABLED,
)
from pandas.errors import (
    ChainedAssignmentError,
    SettingWithCopyWarning,
)

from pandas import (
    DataFrame,
    option_context,
)
import pandas._testing as tm


def test_methods_iloc_warn(using_copy_on_write):
    if not using_copy_on_write:
        df = DataFrame({"a": [1, 2, 3], "b": 1})
        with tm.assert_cow_warning(match="A value"):
            df.iloc[:, 0].replace(1, 5, inplace=True)

        with tm.assert_cow_warning(match="A value"):
            df.iloc[:, 0].fillna(1, inplace=True)

        with tm.assert_cow_warning(match="A value"):
            df.iloc[:, 0].interpolate(inplace=True)

        with tm.assert_cow_warning(match="A value"):
            df.iloc[:, 0].ffill(inplace=True)

        with tm.assert_cow_warning(match="A value"):
            df.iloc[:, 0].bfill(inplace=True)


@pytest.mark.parametrize(
    "func, args",
    [
        ("replace", (4, 5)),
        ("fillna", (1,)),
        ("interpolate", ()),
        ("bfill", ()),
        ("ffill", ()),
    ],
)
def test_methods_iloc_getitem_item_cache(
    func, args, using_copy_on_write, warn_copy_on_write
):
    # ensure we don't incorrectly raise chained assignment warning because
    # of the item cache / iloc not setting the item cache
    df_orig = DataFrame({"a": [1, 2, 3], "b": 1})

    df = df_orig.copy()
    ser = df.iloc[:, 0]
    getattr(ser, func)(*args, inplace=True)

    # parent that holds item_cache is dead, so don't increase ref count
    df = df_orig.copy()
    ser = df.copy()["a"]
    getattr(ser, func)(*args, inplace=True)

    df = df_orig.copy()
    df["a"]  # populate the item_cache
    ser = df.iloc[:, 0]  # iloc creates a new object
    getattr(ser, func)(*args, inplace=True)

    df = df_orig.copy()
    df["a"]  # populate the item_cache
    ser = df["a"]
    getattr(ser, func)(*args, inplace=True)

    df = df_orig.copy()
    df["a"]  # populate the item_cache
    # TODO(CoW-warn) because of the usage of *args, this doesn't warn on Py3.11+
    if using_copy_on_write:
        with tm.raises_chained_assignment_error(not PY311):
            getattr(df["a"], func)(*args, inplace=True)
    else:
        with tm.assert_cow_warning(not PY311, match="A value"):
            getattr(df["a"], func)(*args, inplace=True)

    df = df_orig.copy()
    ser = df["a"]  # populate the item_cache and keep ref
    if using_copy_on_write:
        with tm.raises_chained_assignment_error(not PY311):
            getattr(df["a"], func)(*args, inplace=True)
    else:
        # ideally also warns on the default mode, but the ser' _cacher
        # messes up the refcount + even in warning mode this doesn't trigger
        # the warning of Py3.1+ (see above)
        with tm.assert_cow_warning(warn_copy_on_write and not PY311, match="A value"):
            getattr(df["a"], func)(*args, inplace=True)


def test_methods_iloc_getitem_item_cache_fillna(
    using_copy_on_write, warn_copy_on_write
):
    # ensure we don't incorrectly raise chained assignment warning because
    # of the item cache / iloc not setting the item cache
    df_orig = DataFrame({"a": [1, 2, 3], "b": 1})

    df = df_orig.copy()
    ser = df.iloc[:, 0]
    ser.fillna(1, inplace=True)

    # parent that holds item_cache is dead, so don't increase ref count
    df = df_orig.copy()
    ser = df.copy()["a"]
    ser.fillna(1, inplace=True)

    df = df_orig.copy()
    df["a"]  # populate the item_cache
    ser = df.iloc[:, 0]  # iloc creates a new object
    ser.fillna(1, inplace=True)

    df = df_orig.copy()
    df["a"]  # populate the item_cache
    ser = df["a"]
    ser.fillna(1, inplace=True)

    df = df_orig.copy()
    df["a"]  # populate the item_cache
    if using_copy_on_write:
        with tm.raises_chained_assignment_error():
            df["a"].fillna(1, inplace=True)
    else:
        with tm.assert_cow_warning(match="A value"):
            df["a"].fillna(1, inplace=True)

    df = df_orig.copy()
    ser = df["a"]  # populate the item_cache and keep ref
    if using_copy_on_write:
        with tm.raises_chained_assignment_error():
            df["a"].fillna(1, inplace=True)
    else:
        # TODO(CoW-warn) ideally also warns on the default mode, but the ser' _cacher
        # messes up the refcount
        with tm.assert_cow_warning(warn_copy_on_write, match="A value"):
            df["a"].fillna(1, inplace=True)


# TODO(CoW-warn) expand the cases
@pytest.mark.parametrize(
    "indexer", [0, [0, 1], slice(0, 2), np.array([True, False, True])]
)
def test_series_setitem(indexer, using_copy_on_write, warn_copy_on_write):
    # ensure we only get a single warning for those typical cases of chained
    # assignment
    df = DataFrame({"a": [1, 2, 3], "b": 1})

    # using custom check instead of tm.assert_produces_warning because that doesn't
    # fail if multiple warnings are raised
    if WARNING_CHECK_DISABLED:
        return

    with pytest.warns() as record:
        df["a"][indexer] = 0
    assert len(record) == 1
    if using_copy_on_write:
        assert record[0].category == ChainedAssignmentError
    else:
        assert record[0].category == FutureWarning
        assert "ChainedAssignmentError" in record[0].message.args[0]


@pytest.mark.filterwarnings("ignore::pandas.errors.SettingWithCopyWarning")
@pytest.mark.parametrize(
    "indexer", ["a", ["a", "b"], slice(0, 2), np.array([True, False, True])]
)
def test_frame_setitem(indexer, using_copy_on_write):
    df = DataFrame({"a": [1, 2, 3, 4, 5], "b": 1})

    extra_warnings = () if using_copy_on_write else (SettingWithCopyWarning,)

    with option_context("chained_assignment", "warn"):
        with tm.raises_chained_assignment_error(extra_warnings=extra_warnings):
            df[0:3][indexer] = 10


@pytest.mark.parametrize(
    "indexer", [0, [0, 1], slice(0, 2), np.array([True, False, True])]
)
def test_series_iloc_setitem(indexer):
    df = DataFrame({"a": [1, 2, 3], "b": 1})

    with option_context("chained_assignment", "warn"):
        with tm.raises_chained_assignment_error():
            df["a"].iloc[indexer] = 0


@pytest.mark.parametrize(
    "indexer", [0, [0, 1], slice(0, 2), np.array([True, False, True])]
)
def test_frame_iloc_setitem(indexer, using_copy_on_write):
    df = DataFrame({"a": [1, 2, 3, 4, 5], "b": 1})

    extra_warnings = () if using_copy_on_write else (SettingWithCopyWarning,)

    with option_context("chained_assignment", "warn"):
        with tm.raises_chained_assignment_error(extra_warnings=extra_warnings):
            df[0:3].iloc[indexer] = 10


@pytest.mark.parametrize(
    "indexer", [0, [0, 1], slice(0, 2), np.array([True, False, True])]
)
def test_series_loc_setitem(indexer):
    df = DataFrame({"a": [1, 2, 3], "b": 1})

    with option_context("chained_assignment", "warn"):
        with tm.raises_chained_assignment_error():
            df["a"].loc[indexer] = 0


@pytest.mark.parametrize(
    "indexer", [0, [0, 1], (0, "a"), slice(0, 2), np.array([True, False, True])]
)
def test_frame_loc_setitem(indexer, using_copy_on_write):
    df = DataFrame({"a": [1, 2, 3, 4, 5], "b": 1})

    extra_warnings = () if using_copy_on_write else (SettingWithCopyWarning,)

    with option_context("chained_assignment", "warn"):
        with tm.raises_chained_assignment_error(extra_warnings=extra_warnings):
            df[0:3].loc[indexer] = 10


def test_series_at_setitem():
    df = DataFrame({"a": [1, 2, 3], "b": 1})

    with option_context("chained_assignment", "warn"):
        with tm.raises_chained_assignment_error():
            df["a"].at[0] = 0


def test_frame_at_setitem():
    df = DataFrame({"a": [1, 2, 3, 4, 5], "b": 1})

    with option_context("chained_assignment", "warn"):
        with tm.raises_chained_assignment_error():
            df[0:3].at[0, "a"] = 10


def test_series_iat_setitem():
    df = DataFrame({"a": [1, 2, 3], "b": 1})

    with option_context("chained_assignment", "warn"):
        with tm.raises_chained_assignment_error():
            df["a"].iat[0] = 0


def test_frame_iat_setitem():
    df = DataFrame({"a": [1, 2, 3, 4, 5], "b": 1})

    with option_context("chained_assignment", "warn"):
        with tm.raises_chained_assignment_error():
            df[0:3].iat[0, 0] = 10
