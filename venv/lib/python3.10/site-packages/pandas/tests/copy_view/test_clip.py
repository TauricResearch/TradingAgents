import numpy as np

from pandas.compat import WARNING_CHECK_DISABLED

from pandas import (
    DataFrame,
    option_context,
)
import pandas._testing as tm
from pandas.tests.copy_view.util import get_array


def test_clip_inplace_reference(using_copy_on_write, warn_copy_on_write):
    df = DataFrame({"a": [1.5, 2, 3]})
    df_copy = df.copy()
    arr_a = get_array(df, "a")
    view = df[:]
    if warn_copy_on_write:
        with tm.assert_cow_warning():
            df.clip(lower=2, inplace=True)
    else:
        df.clip(lower=2, inplace=True)

    if using_copy_on_write:
        assert not np.shares_memory(get_array(df, "a"), arr_a)
        assert df._mgr._has_no_reference(0)
        assert view._mgr._has_no_reference(0)
        tm.assert_frame_equal(df_copy, view)
    else:
        assert np.shares_memory(get_array(df, "a"), arr_a)


def test_clip_inplace_reference_no_op(using_copy_on_write):
    df = DataFrame({"a": [1.5, 2, 3]})
    df_copy = df.copy()
    arr_a = get_array(df, "a")
    view = df[:]
    df.clip(lower=0, inplace=True)

    assert np.shares_memory(get_array(df, "a"), arr_a)

    if using_copy_on_write:
        assert not df._mgr._has_no_reference(0)
        assert not view._mgr._has_no_reference(0)
        tm.assert_frame_equal(df_copy, view)


def test_clip_inplace(using_copy_on_write):
    df = DataFrame({"a": [1.5, 2, 3]})
    arr_a = get_array(df, "a")
    df.clip(lower=2, inplace=True)

    assert np.shares_memory(get_array(df, "a"), arr_a)

    if using_copy_on_write:
        assert df._mgr._has_no_reference(0)


def test_clip(using_copy_on_write):
    df = DataFrame({"a": [1.5, 2, 3]})
    df_orig = df.copy()
    df2 = df.clip(lower=2)

    assert not np.shares_memory(get_array(df2, "a"), get_array(df, "a"))

    if using_copy_on_write:
        assert df._mgr._has_no_reference(0)
    tm.assert_frame_equal(df_orig, df)


def test_clip_no_op(using_copy_on_write):
    df = DataFrame({"a": [1.5, 2, 3]})
    df2 = df.clip(lower=0)

    if using_copy_on_write:
        assert not df._mgr._has_no_reference(0)
        assert np.shares_memory(get_array(df2, "a"), get_array(df, "a"))
    else:
        assert not np.shares_memory(get_array(df2, "a"), get_array(df, "a"))


def test_clip_chained_inplace(using_copy_on_write):
    df = DataFrame({"a": [1, 4, 2], "b": 1})
    df_orig = df.copy()
    if using_copy_on_write:
        with tm.raises_chained_assignment_error():
            df["a"].clip(1, 2, inplace=True)
        tm.assert_frame_equal(df, df_orig)

        with tm.raises_chained_assignment_error():
            df[["a"]].clip(1, 2, inplace=True)
        tm.assert_frame_equal(df, df_orig)
    else:
        with tm.assert_produces_warning(
            FutureWarning if not WARNING_CHECK_DISABLED else None,
            match="inplace method",
        ):
            df["a"].clip(1, 2, inplace=True)

        with tm.assert_produces_warning(None):
            with option_context("mode.chained_assignment", None):
                df[["a"]].clip(1, 2, inplace=True)

        with tm.assert_produces_warning(None):
            with option_context("mode.chained_assignment", None):
                df[df["a"] > 1].clip(1, 2, inplace=True)
