import numpy as np
import pytest

from pandas.compat import WARNING_CHECK_DISABLED

from pandas import (
    Categorical,
    DataFrame,
    option_context,
)
import pandas._testing as tm
from pandas.tests.copy_view.util import get_array


@pytest.mark.parametrize(
    "replace_kwargs",
    [
        {"to_replace": {"a": 1, "b": 4}, "value": -1},
        # Test CoW splits blocks to avoid copying unchanged columns
        {"to_replace": {"a": 1}, "value": -1},
        {"to_replace": {"b": 4}, "value": -1},
        {"to_replace": {"b": {4: 1}}},
        # TODO: Add these in a further optimization
        # We would need to see which columns got replaced in the mask
        # which could be expensive
        # {"to_replace": {"b": 1}},
        # 1
    ],
)
def test_replace(using_copy_on_write, replace_kwargs):
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [0.1, 0.2, 0.3]})
    df_orig = df.copy()

    df_replaced = df.replace(**replace_kwargs)

    if using_copy_on_write:
        if (df_replaced["b"] == df["b"]).all():
            assert np.shares_memory(get_array(df_replaced, "b"), get_array(df, "b"))
        assert tm.shares_memory(get_array(df_replaced, "c"), get_array(df, "c"))

    # mutating squeezed df triggers a copy-on-write for that column/block
    df_replaced.loc[0, "c"] = -1
    if using_copy_on_write:
        assert not np.shares_memory(get_array(df_replaced, "c"), get_array(df, "c"))

    if "a" in replace_kwargs["to_replace"]:
        arr = get_array(df_replaced, "a")
        df_replaced.loc[0, "a"] = 100
        assert np.shares_memory(get_array(df_replaced, "a"), arr)
    tm.assert_frame_equal(df, df_orig)


def test_replace_regex_inplace_refs(using_copy_on_write, warn_copy_on_write):
    df = DataFrame({"a": ["aaa", "bbb"]})
    df_orig = df.copy()
    view = df[:]
    arr = get_array(df, "a")
    with tm.assert_cow_warning(warn_copy_on_write):
        df.replace(to_replace=r"^a.*$", value="new", inplace=True, regex=True)
    if using_copy_on_write:
        assert not tm.shares_memory(arr, get_array(df, "a"))
        assert df._mgr._has_no_reference(0)
        tm.assert_frame_equal(view, df_orig)
    else:
        assert np.shares_memory(arr, get_array(df, "a"))


def test_replace_regex_inplace(using_copy_on_write):
    df = DataFrame({"a": ["aaa", "bbb"]})
    arr = get_array(df, "a")
    df.replace(to_replace=r"^a.*$", value="new", inplace=True, regex=True)
    if using_copy_on_write:
        assert df._mgr._has_no_reference(0)
    assert tm.shares_memory(arr, get_array(df, "a"))

    df_orig = df.copy()
    df2 = df.replace(to_replace=r"^b.*$", value="new", regex=True)
    tm.assert_frame_equal(df_orig, df)
    assert not tm.shares_memory(get_array(df2, "a"), get_array(df, "a"))


def test_replace_regex_inplace_no_op(using_copy_on_write):
    df = DataFrame({"a": [1, 2]})
    arr = get_array(df, "a")
    df.replace(to_replace=r"^a.$", value="new", inplace=True, regex=True)
    if using_copy_on_write:
        assert df._mgr._has_no_reference(0)
    assert np.shares_memory(arr, get_array(df, "a"))

    df_orig = df.copy()
    df2 = df.replace(to_replace=r"^x.$", value="new", regex=True)
    tm.assert_frame_equal(df_orig, df)
    if using_copy_on_write:
        assert np.shares_memory(get_array(df2, "a"), get_array(df, "a"))
    else:
        assert not np.shares_memory(get_array(df2, "a"), get_array(df, "a"))


def test_replace_mask_all_false_second_block(using_copy_on_write):
    df = DataFrame({"a": [1.5, 2, 3], "b": 100.5, "c": 1, "d": 2})
    df_orig = df.copy()

    df2 = df.replace(to_replace=1.5, value=55.5)

    if using_copy_on_write:
        # TODO: Block splitting would allow us to avoid copying b
        assert np.shares_memory(get_array(df, "c"), get_array(df2, "c"))
        assert not np.shares_memory(get_array(df, "a"), get_array(df2, "a"))

    else:
        assert not np.shares_memory(get_array(df, "c"), get_array(df2, "c"))
        assert not np.shares_memory(get_array(df, "a"), get_array(df2, "a"))

    df2.loc[0, "c"] = 1
    tm.assert_frame_equal(df, df_orig)  # Original is unchanged

    if using_copy_on_write:
        assert not np.shares_memory(get_array(df, "c"), get_array(df2, "c"))
        # TODO: This should split and not copy the whole block
        # assert np.shares_memory(get_array(df, "d"), get_array(df2, "d"))


def test_replace_coerce_single_column(using_copy_on_write, using_array_manager):
    df = DataFrame({"a": [1.5, 2, 3], "b": 100.5})
    df_orig = df.copy()

    df2 = df.replace(to_replace=1.5, value="a")

    if using_copy_on_write:
        assert np.shares_memory(get_array(df, "b"), get_array(df2, "b"))
        assert not np.shares_memory(get_array(df, "a"), get_array(df2, "a"))

    elif not using_array_manager:
        assert np.shares_memory(get_array(df, "b"), get_array(df2, "b"))
        assert not np.shares_memory(get_array(df, "a"), get_array(df2, "a"))

    if using_copy_on_write:
        df2.loc[0, "b"] = 0.5
        tm.assert_frame_equal(df, df_orig)  # Original is unchanged
        assert not np.shares_memory(get_array(df, "b"), get_array(df2, "b"))


def test_replace_to_replace_wrong_dtype(using_copy_on_write):
    df = DataFrame({"a": [1.5, 2, 3], "b": 100.5})
    df_orig = df.copy()

    df2 = df.replace(to_replace="xxx", value=1.5)

    if using_copy_on_write:
        assert np.shares_memory(get_array(df, "b"), get_array(df2, "b"))
        assert np.shares_memory(get_array(df, "a"), get_array(df2, "a"))

    else:
        assert not np.shares_memory(get_array(df, "b"), get_array(df2, "b"))
        assert not np.shares_memory(get_array(df, "a"), get_array(df2, "a"))

    df2.loc[0, "b"] = 0.5
    tm.assert_frame_equal(df, df_orig)  # Original is unchanged

    if using_copy_on_write:
        assert not np.shares_memory(get_array(df, "b"), get_array(df2, "b"))


def test_replace_list_categorical(using_copy_on_write):
    df = DataFrame({"a": ["a", "b", "c"]}, dtype="category")
    arr = get_array(df, "a")
    msg = (
        r"The behavior of Series\.replace \(and DataFrame.replace\) "
        "with CategoricalDtype"
    )
    with tm.assert_produces_warning(FutureWarning, match=msg):
        df.replace(["c"], value="a", inplace=True)
    assert np.shares_memory(arr.codes, get_array(df, "a").codes)
    if using_copy_on_write:
        assert df._mgr._has_no_reference(0)

    df_orig = df.copy()
    with tm.assert_produces_warning(FutureWarning, match=msg):
        df2 = df.replace(["b"], value="a")
    assert not np.shares_memory(arr.codes, get_array(df2, "a").codes)

    tm.assert_frame_equal(df, df_orig)


def test_replace_list_inplace_refs_categorical(using_copy_on_write):
    df = DataFrame({"a": ["a", "b", "c"]}, dtype="category")
    view = df[:]
    df_orig = df.copy()
    msg = (
        r"The behavior of Series\.replace \(and DataFrame.replace\) "
        "with CategoricalDtype"
    )
    with tm.assert_produces_warning(FutureWarning, match=msg):
        df.replace(["c"], value="a", inplace=True)
    if using_copy_on_write:
        assert not np.shares_memory(
            get_array(view, "a").codes, get_array(df, "a").codes
        )
        tm.assert_frame_equal(df_orig, view)
    else:
        # This could be inplace
        assert not np.shares_memory(
            get_array(view, "a").codes, get_array(df, "a").codes
        )


@pytest.mark.parametrize("to_replace", [1.5, [1.5], []])
def test_replace_inplace(using_copy_on_write, to_replace):
    df = DataFrame({"a": [1.5, 2, 3]})
    arr_a = get_array(df, "a")
    df.replace(to_replace=1.5, value=15.5, inplace=True)

    assert np.shares_memory(get_array(df, "a"), arr_a)
    if using_copy_on_write:
        assert df._mgr._has_no_reference(0)


@pytest.mark.parametrize("to_replace", [1.5, [1.5]])
def test_replace_inplace_reference(using_copy_on_write, to_replace, warn_copy_on_write):
    df = DataFrame({"a": [1.5, 2, 3]})
    arr_a = get_array(df, "a")
    view = df[:]
    with tm.assert_cow_warning(warn_copy_on_write):
        df.replace(to_replace=to_replace, value=15.5, inplace=True)

    if using_copy_on_write:
        assert not np.shares_memory(get_array(df, "a"), arr_a)
        assert df._mgr._has_no_reference(0)
        assert view._mgr._has_no_reference(0)
    else:
        assert np.shares_memory(get_array(df, "a"), arr_a)


@pytest.mark.parametrize("to_replace", ["a", 100.5])
def test_replace_inplace_reference_no_op(using_copy_on_write, to_replace):
    df = DataFrame({"a": [1.5, 2, 3]})
    arr_a = get_array(df, "a")
    view = df[:]
    df.replace(to_replace=to_replace, value=15.5, inplace=True)

    assert np.shares_memory(get_array(df, "a"), arr_a)
    if using_copy_on_write:
        assert not df._mgr._has_no_reference(0)
        assert not view._mgr._has_no_reference(0)


@pytest.mark.parametrize("to_replace", [1, [1]])
@pytest.mark.parametrize("val", [1, 1.5])
def test_replace_categorical_inplace_reference(using_copy_on_write, val, to_replace):
    df = DataFrame({"a": Categorical([1, 2, 3])})
    df_orig = df.copy()
    arr_a = get_array(df, "a")
    view = df[:]
    msg = (
        r"The behavior of Series\.replace \(and DataFrame.replace\) "
        "with CategoricalDtype"
    )
    warn = FutureWarning if val == 1.5 else None
    with tm.assert_produces_warning(warn, match=msg):
        df.replace(to_replace=to_replace, value=val, inplace=True)

    if using_copy_on_write:
        assert not np.shares_memory(get_array(df, "a").codes, arr_a.codes)
        assert df._mgr._has_no_reference(0)
        assert view._mgr._has_no_reference(0)
        tm.assert_frame_equal(view, df_orig)
    else:
        assert np.shares_memory(get_array(df, "a").codes, arr_a.codes)


@pytest.mark.parametrize("val", [1, 1.5])
def test_replace_categorical_inplace(using_copy_on_write, val):
    df = DataFrame({"a": Categorical([1, 2, 3])})
    arr_a = get_array(df, "a")
    msg = (
        r"The behavior of Series\.replace \(and DataFrame.replace\) "
        "with CategoricalDtype"
    )
    warn = FutureWarning if val == 1.5 else None
    with tm.assert_produces_warning(warn, match=msg):
        df.replace(to_replace=1, value=val, inplace=True)

    assert np.shares_memory(get_array(df, "a").codes, arr_a.codes)
    if using_copy_on_write:
        assert df._mgr._has_no_reference(0)

    expected = DataFrame({"a": Categorical([val, 2, 3])})
    tm.assert_frame_equal(df, expected)


@pytest.mark.parametrize("val", [1, 1.5])
def test_replace_categorical(using_copy_on_write, val):
    df = DataFrame({"a": Categorical([1, 2, 3])})
    df_orig = df.copy()
    msg = (
        r"The behavior of Series\.replace \(and DataFrame.replace\) "
        "with CategoricalDtype"
    )
    warn = FutureWarning if val == 1.5 else None
    with tm.assert_produces_warning(warn, match=msg):
        df2 = df.replace(to_replace=1, value=val)

    if using_copy_on_write:
        assert df._mgr._has_no_reference(0)
        assert df2._mgr._has_no_reference(0)
    assert not np.shares_memory(get_array(df, "a").codes, get_array(df2, "a").codes)
    tm.assert_frame_equal(df, df_orig)

    arr_a = get_array(df2, "a").codes
    df2.iloc[0, 0] = 2.0
    assert np.shares_memory(get_array(df2, "a").codes, arr_a)


@pytest.mark.parametrize("method", ["where", "mask"])
def test_masking_inplace(using_copy_on_write, method, warn_copy_on_write):
    df = DataFrame({"a": [1.5, 2, 3]})
    df_orig = df.copy()
    arr_a = get_array(df, "a")
    view = df[:]

    method = getattr(df, method)
    if warn_copy_on_write:
        with tm.assert_cow_warning():
            method(df["a"] > 1.6, -1, inplace=True)
    else:
        method(df["a"] > 1.6, -1, inplace=True)

    if using_copy_on_write:
        assert not np.shares_memory(get_array(df, "a"), arr_a)
        assert df._mgr._has_no_reference(0)
        assert view._mgr._has_no_reference(0)
        tm.assert_frame_equal(view, df_orig)
    else:
        assert np.shares_memory(get_array(df, "a"), arr_a)


def test_replace_empty_list(using_copy_on_write):
    df = DataFrame({"a": [1, 2]})

    df2 = df.replace([], [])
    if using_copy_on_write:
        assert np.shares_memory(get_array(df2, "a"), get_array(df, "a"))
        assert not df._mgr._has_no_reference(0)
    else:
        assert not np.shares_memory(get_array(df2, "a"), get_array(df, "a"))

    arr_a = get_array(df, "a")
    df.replace([], [])
    if using_copy_on_write:
        assert np.shares_memory(get_array(df, "a"), arr_a)
        assert not df._mgr._has_no_reference(0)
        assert not df2._mgr._has_no_reference(0)


@pytest.mark.parametrize("value", ["d", None])
def test_replace_object_list_inplace(using_copy_on_write, value):
    df = DataFrame({"a": ["a", "b", "c"]}, dtype=object)
    arr = get_array(df, "a")
    df.replace(["c"], value, inplace=True)
    if using_copy_on_write or value is None:
        assert tm.shares_memory(arr, get_array(df, "a"))
    else:
        # This could be inplace
        assert not np.shares_memory(arr, get_array(df, "a"))
    if using_copy_on_write:
        assert df._mgr._has_no_reference(0)


def test_replace_list_multiple_elements_inplace(using_copy_on_write):
    df = DataFrame({"a": [1, 2, 3]})
    arr = get_array(df, "a")
    df.replace([1, 2], 4, inplace=True)
    if using_copy_on_write:
        assert np.shares_memory(arr, get_array(df, "a"))
        assert df._mgr._has_no_reference(0)
    else:
        assert np.shares_memory(arr, get_array(df, "a"))


def test_replace_list_none(using_copy_on_write):
    df = DataFrame({"a": ["a", "b", "c"]})

    df_orig = df.copy()
    df2 = df.replace(["b"], value=None)
    tm.assert_frame_equal(df, df_orig)

    assert not np.shares_memory(get_array(df, "a"), get_array(df2, "a"))

    # replace multiple values that don't actually replace anything with None
    # https://github.com/pandas-dev/pandas/issues/59770
    df3 = df.replace(["d", "e", "f"], value=None)
    tm.assert_frame_equal(df3, df_orig)
    if using_copy_on_write:
        assert tm.shares_memory(get_array(df, "a"), get_array(df3, "a"))
    else:
        assert not tm.shares_memory(get_array(df, "a"), get_array(df3, "a"))


def test_replace_list_none_inplace_refs(using_copy_on_write, warn_copy_on_write):
    df = DataFrame({"a": ["a", "b", "c"]})
    arr = get_array(df, "a")
    df_orig = df.copy()
    view = df[:]
    with tm.assert_cow_warning(warn_copy_on_write):
        df.replace(["a"], value=None, inplace=True)
    if using_copy_on_write:
        assert df._mgr._has_no_reference(0)
        assert not np.shares_memory(arr, get_array(df, "a"))
        tm.assert_frame_equal(df_orig, view)
    else:
        assert np.shares_memory(arr, get_array(df, "a"))


def test_replace_columnwise_no_op_inplace(using_copy_on_write):
    df = DataFrame({"a": [1, 2, 3], "b": [1, 2, 3]})
    view = df[:]
    df_orig = df.copy()
    df.replace({"a": 10}, 100, inplace=True)
    if using_copy_on_write:
        assert np.shares_memory(get_array(view, "a"), get_array(df, "a"))
        df.iloc[0, 0] = 100
        tm.assert_frame_equal(view, df_orig)


def test_replace_columnwise_no_op(using_copy_on_write):
    df = DataFrame({"a": [1, 2, 3], "b": [1, 2, 3]})
    df_orig = df.copy()
    df2 = df.replace({"a": 10}, 100)
    if using_copy_on_write:
        assert np.shares_memory(get_array(df2, "a"), get_array(df, "a"))
    df2.iloc[0, 0] = 100
    tm.assert_frame_equal(df, df_orig)


def test_replace_chained_assignment(using_copy_on_write):
    df = DataFrame({"a": [1, np.nan, 2], "b": 1})
    df_orig = df.copy()
    if using_copy_on_write:
        with tm.raises_chained_assignment_error():
            df["a"].replace(1, 100, inplace=True)
        tm.assert_frame_equal(df, df_orig)

        with tm.raises_chained_assignment_error():
            df[["a"]].replace(1, 100, inplace=True)
        tm.assert_frame_equal(df, df_orig)
    else:
        with tm.assert_produces_warning(None):
            with option_context("mode.chained_assignment", None):
                df[["a"]].replace(1, 100, inplace=True)

        with tm.assert_produces_warning(None):
            with option_context("mode.chained_assignment", None):
                df[df.a > 5].replace(1, 100, inplace=True)

        with tm.assert_produces_warning(
            FutureWarning if not WARNING_CHECK_DISABLED else None,
            match="inplace method",
        ):
            df["a"].replace(1, 100, inplace=True)


def test_replace_listlike(using_copy_on_write):
    df = DataFrame({"a": [1, 2, 3], "b": [1, 2, 3]})
    df_orig = df.copy()

    result = df.replace([200, 201], [11, 11])
    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "a"), get_array(df, "a"))
    else:
        assert not np.shares_memory(get_array(result, "a"), get_array(df, "a"))

    result.iloc[0, 0] = 100
    tm.assert_frame_equal(df, df)

    result = df.replace([200, 2], [10, 10])
    assert not np.shares_memory(get_array(df, "a"), get_array(result, "a"))
    tm.assert_frame_equal(df, df_orig)


def test_replace_listlike_inplace(using_copy_on_write, warn_copy_on_write):
    df = DataFrame({"a": [1, 2, 3], "b": [1, 2, 3]})
    arr = get_array(df, "a")
    df.replace([200, 2], [10, 11], inplace=True)
    assert np.shares_memory(get_array(df, "a"), arr)

    view = df[:]
    df_orig = df.copy()
    with tm.assert_cow_warning(warn_copy_on_write):
        df.replace([200, 3], [10, 11], inplace=True)
    if using_copy_on_write:
        assert not np.shares_memory(get_array(df, "a"), arr)
        tm.assert_frame_equal(view, df_orig)
    else:
        assert np.shares_memory(get_array(df, "a"), arr)
        tm.assert_frame_equal(df, view)
