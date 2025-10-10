import numpy as np
import pytest

from pandas.errors import SettingWithCopyWarning

from pandas.core.dtypes.common import is_float_dtype

import pandas as pd
from pandas import (
    DataFrame,
    Series,
)
import pandas._testing as tm
from pandas.tests.copy_view.util import get_array


@pytest.fixture(params=["numpy", "nullable"])
def backend(request):
    if request.param == "numpy":

        def make_dataframe(*args, **kwargs):
            return DataFrame(*args, **kwargs)

        def make_series(*args, **kwargs):
            return Series(*args, **kwargs)

    elif request.param == "nullable":

        def make_dataframe(*args, **kwargs):
            df = DataFrame(*args, **kwargs)
            df_nullable = df.convert_dtypes()
            # convert_dtypes will try to cast float to int if there is no loss in
            # precision -> undo that change
            for col in df.columns:
                if is_float_dtype(df[col].dtype) and not is_float_dtype(
                    df_nullable[col].dtype
                ):
                    df_nullable[col] = df_nullable[col].astype("Float64")
            # copy final result to ensure we start with a fully self-owning DataFrame
            return df_nullable.copy()

        def make_series(*args, **kwargs):
            ser = Series(*args, **kwargs)
            return ser.convert_dtypes().copy()

    return request.param, make_dataframe, make_series


# -----------------------------------------------------------------------------
# Indexing operations taking subset + modifying the subset/parent


def test_subset_column_selection(backend, using_copy_on_write):
    # Case: taking a subset of the columns of a DataFrame
    # + afterwards modifying the subset
    _, DataFrame, _ = backend
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [0.1, 0.2, 0.3]})
    df_orig = df.copy()

    subset = df[["a", "c"]]

    if using_copy_on_write:
        # the subset shares memory ...
        assert np.shares_memory(get_array(subset, "a"), get_array(df, "a"))
        # ... but uses CoW when being modified
        subset.iloc[0, 0] = 0
    else:
        assert not np.shares_memory(get_array(subset, "a"), get_array(df, "a"))
        # INFO this no longer raise warning since pandas 1.4
        # with pd.option_context("chained_assignment", "warn"):
        #     with tm.assert_produces_warning(SettingWithCopyWarning):
        subset.iloc[0, 0] = 0

    assert not np.shares_memory(get_array(subset, "a"), get_array(df, "a"))

    expected = DataFrame({"a": [0, 2, 3], "c": [0.1, 0.2, 0.3]})
    tm.assert_frame_equal(subset, expected)
    tm.assert_frame_equal(df, df_orig)


def test_subset_column_selection_modify_parent(backend, using_copy_on_write):
    # Case: taking a subset of the columns of a DataFrame
    # + afterwards modifying the parent
    _, DataFrame, _ = backend
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [0.1, 0.2, 0.3]})

    subset = df[["a", "c"]]

    if using_copy_on_write:
        # the subset shares memory ...
        assert np.shares_memory(get_array(subset, "a"), get_array(df, "a"))
        # ... but parent uses CoW parent when it is modified
    df.iloc[0, 0] = 0

    assert not np.shares_memory(get_array(subset, "a"), get_array(df, "a"))
    if using_copy_on_write:
        # different column/block still shares memory
        assert np.shares_memory(get_array(subset, "c"), get_array(df, "c"))

    expected = DataFrame({"a": [1, 2, 3], "c": [0.1, 0.2, 0.3]})
    tm.assert_frame_equal(subset, expected)


def test_subset_row_slice(backend, using_copy_on_write, warn_copy_on_write):
    # Case: taking a subset of the rows of a DataFrame using a slice
    # + afterwards modifying the subset
    _, DataFrame, _ = backend
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [0.1, 0.2, 0.3]})
    df_orig = df.copy()

    subset = df[1:3]
    subset._mgr._verify_integrity()

    assert np.shares_memory(get_array(subset, "a"), get_array(df, "a"))

    if using_copy_on_write:
        subset.iloc[0, 0] = 0
        assert not np.shares_memory(get_array(subset, "a"), get_array(df, "a"))

    else:
        # INFO this no longer raise warning since pandas 1.4
        # with pd.option_context("chained_assignment", "warn"):
        #     with tm.assert_produces_warning(SettingWithCopyWarning):
        with tm.assert_cow_warning(warn_copy_on_write):
            subset.iloc[0, 0] = 0

    subset._mgr._verify_integrity()

    expected = DataFrame({"a": [0, 3], "b": [5, 6], "c": [0.2, 0.3]}, index=range(1, 3))
    tm.assert_frame_equal(subset, expected)
    if using_copy_on_write:
        # original parent dataframe is not modified (CoW)
        tm.assert_frame_equal(df, df_orig)
    else:
        # original parent dataframe is actually updated
        df_orig.iloc[1, 0] = 0
        tm.assert_frame_equal(df, df_orig)


@pytest.mark.parametrize(
    "dtype", ["int64", "float64"], ids=["single-block", "mixed-block"]
)
def test_subset_column_slice(
    backend, using_copy_on_write, warn_copy_on_write, using_array_manager, dtype
):
    # Case: taking a subset of the columns of a DataFrame using a slice
    # + afterwards modifying the subset
    dtype_backend, DataFrame, _ = backend
    single_block = (
        dtype == "int64" and dtype_backend == "numpy"
    ) and not using_array_manager
    df = DataFrame(
        {"a": [1, 2, 3], "b": [4, 5, 6], "c": np.array([7, 8, 9], dtype=dtype)}
    )
    df_orig = df.copy()

    subset = df.iloc[:, 1:]
    subset._mgr._verify_integrity()

    if using_copy_on_write:
        assert np.shares_memory(get_array(subset, "b"), get_array(df, "b"))

        subset.iloc[0, 0] = 0
        assert not np.shares_memory(get_array(subset, "b"), get_array(df, "b"))
    elif warn_copy_on_write:
        with tm.assert_cow_warning(single_block):
            subset.iloc[0, 0] = 0
    else:
        # we only get a warning in case of a single block
        warn = SettingWithCopyWarning if single_block else None
        with pd.option_context("chained_assignment", "warn"):
            with tm.assert_produces_warning(warn):
                subset.iloc[0, 0] = 0

    expected = DataFrame({"b": [0, 5, 6], "c": np.array([7, 8, 9], dtype=dtype)})
    tm.assert_frame_equal(subset, expected)
    # original parent dataframe is not modified (also not for BlockManager case,
    # except for single block)
    if not using_copy_on_write and (using_array_manager or single_block):
        df_orig.iloc[0, 1] = 0
        tm.assert_frame_equal(df, df_orig)
    else:
        tm.assert_frame_equal(df, df_orig)


@pytest.mark.parametrize(
    "dtype", ["int64", "float64"], ids=["single-block", "mixed-block"]
)
@pytest.mark.parametrize(
    "row_indexer",
    [slice(1, 2), np.array([False, True, True]), np.array([1, 2])],
    ids=["slice", "mask", "array"],
)
@pytest.mark.parametrize(
    "column_indexer",
    [slice("b", "c"), np.array([False, True, True]), ["b", "c"]],
    ids=["slice", "mask", "array"],
)
def test_subset_loc_rows_columns(
    backend,
    dtype,
    row_indexer,
    column_indexer,
    using_array_manager,
    using_copy_on_write,
    warn_copy_on_write,
):
    # Case: taking a subset of the rows+columns of a DataFrame using .loc
    # + afterwards modifying the subset
    # Generic test for several combinations of row/column indexers, not all
    # of those could actually return a view / need CoW (so this test is not
    # checking memory sharing, only ensuring subsequent mutation doesn't
    # affect the parent dataframe)
    dtype_backend, DataFrame, _ = backend
    df = DataFrame(
        {"a": [1, 2, 3], "b": [4, 5, 6], "c": np.array([7, 8, 9], dtype=dtype)}
    )
    df_orig = df.copy()

    subset = df.loc[row_indexer, column_indexer]

    # a few corner cases _do_ actually modify the parent (with both row and column
    # slice, and in case of ArrayManager or BlockManager with single block)
    mutate_parent = (
        isinstance(row_indexer, slice)
        and isinstance(column_indexer, slice)
        and (
            using_array_manager
            or (
                dtype == "int64"
                and dtype_backend == "numpy"
                and not using_copy_on_write
            )
        )
    )

    # modifying the subset never modifies the parent
    with tm.assert_cow_warning(warn_copy_on_write and mutate_parent):
        subset.iloc[0, 0] = 0

    expected = DataFrame(
        {"b": [0, 6], "c": np.array([8, 9], dtype=dtype)}, index=range(1, 3)
    )
    tm.assert_frame_equal(subset, expected)
    if mutate_parent:
        df_orig.iloc[1, 1] = 0
    tm.assert_frame_equal(df, df_orig)


@pytest.mark.parametrize(
    "dtype", ["int64", "float64"], ids=["single-block", "mixed-block"]
)
@pytest.mark.parametrize(
    "row_indexer",
    [slice(1, 3), np.array([False, True, True]), np.array([1, 2])],
    ids=["slice", "mask", "array"],
)
@pytest.mark.parametrize(
    "column_indexer",
    [slice(1, 3), np.array([False, True, True]), [1, 2]],
    ids=["slice", "mask", "array"],
)
def test_subset_iloc_rows_columns(
    backend,
    dtype,
    row_indexer,
    column_indexer,
    using_array_manager,
    using_copy_on_write,
    warn_copy_on_write,
):
    # Case: taking a subset of the rows+columns of a DataFrame using .iloc
    # + afterwards modifying the subset
    # Generic test for several combinations of row/column indexers, not all
    # of those could actually return a view / need CoW (so this test is not
    # checking memory sharing, only ensuring subsequent mutation doesn't
    # affect the parent dataframe)
    dtype_backend, DataFrame, _ = backend
    df = DataFrame(
        {"a": [1, 2, 3], "b": [4, 5, 6], "c": np.array([7, 8, 9], dtype=dtype)}
    )
    df_orig = df.copy()

    subset = df.iloc[row_indexer, column_indexer]

    # a few corner cases _do_ actually modify the parent (with both row and column
    # slice, and in case of ArrayManager or BlockManager with single block)
    mutate_parent = (
        isinstance(row_indexer, slice)
        and isinstance(column_indexer, slice)
        and (
            using_array_manager
            or (
                dtype == "int64"
                and dtype_backend == "numpy"
                and not using_copy_on_write
            )
        )
    )

    # modifying the subset never modifies the parent
    with tm.assert_cow_warning(warn_copy_on_write and mutate_parent):
        subset.iloc[0, 0] = 0

    expected = DataFrame(
        {"b": [0, 6], "c": np.array([8, 9], dtype=dtype)}, index=range(1, 3)
    )
    tm.assert_frame_equal(subset, expected)
    if mutate_parent:
        df_orig.iloc[1, 1] = 0
    tm.assert_frame_equal(df, df_orig)


@pytest.mark.parametrize(
    "indexer",
    [slice(0, 2), np.array([True, True, False]), np.array([0, 1])],
    ids=["slice", "mask", "array"],
)
def test_subset_set_with_row_indexer(
    backend, indexer_si, indexer, using_copy_on_write, warn_copy_on_write
):
    # Case: setting values with a row indexer on a viewing subset
    # subset[indexer] = value and subset.iloc[indexer] = value
    _, DataFrame, _ = backend
    df = DataFrame({"a": [1, 2, 3, 4], "b": [4, 5, 6, 7], "c": [0.1, 0.2, 0.3, 0.4]})
    df_orig = df.copy()
    subset = df[1:4]

    if (
        indexer_si is tm.setitem
        and isinstance(indexer, np.ndarray)
        and indexer.dtype == "int"
    ):
        pytest.skip("setitem with labels selects on columns")

    if using_copy_on_write:
        indexer_si(subset)[indexer] = 0
    elif warn_copy_on_write:
        with tm.assert_cow_warning():
            indexer_si(subset)[indexer] = 0
    else:
        # INFO iloc no longer raises warning since pandas 1.4
        warn = SettingWithCopyWarning if indexer_si is tm.setitem else None
        with pd.option_context("chained_assignment", "warn"):
            with tm.assert_produces_warning(warn):
                indexer_si(subset)[indexer] = 0

    expected = DataFrame(
        {"a": [0, 0, 4], "b": [0, 0, 7], "c": [0.0, 0.0, 0.4]}, index=range(1, 4)
    )
    tm.assert_frame_equal(subset, expected)
    if using_copy_on_write:
        # original parent dataframe is not modified (CoW)
        tm.assert_frame_equal(df, df_orig)
    else:
        # original parent dataframe is actually updated
        df_orig[1:3] = 0
        tm.assert_frame_equal(df, df_orig)


def test_subset_set_with_mask(backend, using_copy_on_write, warn_copy_on_write):
    # Case: setting values with a mask on a viewing subset: subset[mask] = value
    _, DataFrame, _ = backend
    df = DataFrame({"a": [1, 2, 3, 4], "b": [4, 5, 6, 7], "c": [0.1, 0.2, 0.3, 0.4]})
    df_orig = df.copy()
    subset = df[1:4]

    mask = subset > 3

    if using_copy_on_write:
        subset[mask] = 0
    elif warn_copy_on_write:
        with tm.assert_cow_warning():
            subset[mask] = 0
    else:
        with pd.option_context("chained_assignment", "warn"):
            with tm.assert_produces_warning(SettingWithCopyWarning):
                subset[mask] = 0

    expected = DataFrame(
        {"a": [2, 3, 0], "b": [0, 0, 0], "c": [0.20, 0.3, 0.4]}, index=range(1, 4)
    )
    tm.assert_frame_equal(subset, expected)
    if using_copy_on_write:
        # original parent dataframe is not modified (CoW)
        tm.assert_frame_equal(df, df_orig)
    else:
        # original parent dataframe is actually updated
        df_orig.loc[3, "a"] = 0
        df_orig.loc[1:3, "b"] = 0
        tm.assert_frame_equal(df, df_orig)


def test_subset_set_column(backend, using_copy_on_write, warn_copy_on_write):
    # Case: setting a single column on a viewing subset -> subset[col] = value
    dtype_backend, DataFrame, _ = backend
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [0.1, 0.2, 0.3]})
    df_orig = df.copy()
    subset = df[1:3]

    if dtype_backend == "numpy":
        arr = np.array([10, 11], dtype="int64")
    else:
        arr = pd.array([10, 11], dtype="Int64")

    if using_copy_on_write or warn_copy_on_write:
        subset["a"] = arr
    else:
        with pd.option_context("chained_assignment", "warn"):
            with tm.assert_produces_warning(SettingWithCopyWarning):
                subset["a"] = arr

    subset._mgr._verify_integrity()
    expected = DataFrame(
        {"a": [10, 11], "b": [5, 6], "c": [0.2, 0.3]}, index=range(1, 3)
    )
    tm.assert_frame_equal(subset, expected)
    tm.assert_frame_equal(df, df_orig)


@pytest.mark.parametrize(
    "dtype", ["int64", "float64"], ids=["single-block", "mixed-block"]
)
def test_subset_set_column_with_loc(
    backend, using_copy_on_write, warn_copy_on_write, using_array_manager, dtype
):
    # Case: setting a single column with loc on a viewing subset
    # -> subset.loc[:, col] = value
    _, DataFrame, _ = backend
    df = DataFrame(
        {"a": [1, 2, 3], "b": [4, 5, 6], "c": np.array([7, 8, 9], dtype=dtype)}
    )
    df_orig = df.copy()
    subset = df[1:3]

    if using_copy_on_write:
        subset.loc[:, "a"] = np.array([10, 11], dtype="int64")
    elif warn_copy_on_write:
        with tm.assert_cow_warning():
            subset.loc[:, "a"] = np.array([10, 11], dtype="int64")
    else:
        with pd.option_context("chained_assignment", "warn"):
            with tm.assert_produces_warning(
                None,
                raise_on_extra_warnings=not using_array_manager,
            ):
                subset.loc[:, "a"] = np.array([10, 11], dtype="int64")

    subset._mgr._verify_integrity()
    expected = DataFrame(
        {"a": [10, 11], "b": [5, 6], "c": np.array([8, 9], dtype=dtype)},
        index=range(1, 3),
    )
    tm.assert_frame_equal(subset, expected)
    if using_copy_on_write:
        # original parent dataframe is not modified (CoW)
        tm.assert_frame_equal(df, df_orig)
    else:
        # original parent dataframe is actually updated
        df_orig.loc[1:3, "a"] = np.array([10, 11], dtype="int64")
        tm.assert_frame_equal(df, df_orig)


def test_subset_set_column_with_loc2(
    backend, using_copy_on_write, warn_copy_on_write, using_array_manager
):
    # Case: setting a single column with loc on a viewing subset
    # -> subset.loc[:, col] = value
    # separate test for case of DataFrame of a single column -> takes a separate
    # code path
    _, DataFrame, _ = backend
    df = DataFrame({"a": [1, 2, 3]})
    df_orig = df.copy()
    subset = df[1:3]

    if using_copy_on_write:
        subset.loc[:, "a"] = 0
    elif warn_copy_on_write:
        with tm.assert_cow_warning():
            subset.loc[:, "a"] = 0
    else:
        with pd.option_context("chained_assignment", "warn"):
            with tm.assert_produces_warning(
                None,
                raise_on_extra_warnings=not using_array_manager,
            ):
                subset.loc[:, "a"] = 0

    subset._mgr._verify_integrity()
    expected = DataFrame({"a": [0, 0]}, index=range(1, 3))
    tm.assert_frame_equal(subset, expected)
    if using_copy_on_write:
        # original parent dataframe is not modified (CoW)
        tm.assert_frame_equal(df, df_orig)
    else:
        # original parent dataframe is actually updated
        df_orig.loc[1:3, "a"] = 0
        tm.assert_frame_equal(df, df_orig)


@pytest.mark.parametrize(
    "dtype", ["int64", "float64"], ids=["single-block", "mixed-block"]
)
def test_subset_set_columns(backend, using_copy_on_write, warn_copy_on_write, dtype):
    # Case: setting multiple columns on a viewing subset
    # -> subset[[col1, col2]] = value
    dtype_backend, DataFrame, _ = backend
    df = DataFrame(
        {"a": [1, 2, 3], "b": [4, 5, 6], "c": np.array([7, 8, 9], dtype=dtype)}
    )
    df_orig = df.copy()
    subset = df[1:3]

    if using_copy_on_write or warn_copy_on_write:
        subset[["a", "c"]] = 0
    else:
        with pd.option_context("chained_assignment", "warn"):
            with tm.assert_produces_warning(SettingWithCopyWarning):
                subset[["a", "c"]] = 0

    subset._mgr._verify_integrity()
    if using_copy_on_write:
        # first and third column should certainly have no references anymore
        assert all(subset._mgr._has_no_reference(i) for i in [0, 2])
    expected = DataFrame({"a": [0, 0], "b": [5, 6], "c": [0, 0]}, index=range(1, 3))
    if dtype_backend == "nullable":
        # there is not yet a global option, so overriding a column by setting a scalar
        # defaults to numpy dtype even if original column was nullable
        expected["a"] = expected["a"].astype("int64")
        expected["c"] = expected["c"].astype("int64")

    tm.assert_frame_equal(subset, expected)
    tm.assert_frame_equal(df, df_orig)


@pytest.mark.parametrize(
    "indexer",
    [slice("a", "b"), np.array([True, True, False]), ["a", "b"]],
    ids=["slice", "mask", "array"],
)
def test_subset_set_with_column_indexer(
    backend, indexer, using_copy_on_write, warn_copy_on_write
):
    # Case: setting multiple columns with a column indexer on a viewing subset
    # -> subset.loc[:, [col1, col2]] = value
    _, DataFrame, _ = backend
    df = DataFrame({"a": [1, 2, 3], "b": [0.1, 0.2, 0.3], "c": [4, 5, 6]})
    df_orig = df.copy()
    subset = df[1:3]

    if using_copy_on_write:
        subset.loc[:, indexer] = 0
    elif warn_copy_on_write:
        with tm.assert_cow_warning():
            subset.loc[:, indexer] = 0
    else:
        with pd.option_context("chained_assignment", "warn"):
            # As of 2.0, this setitem attempts (successfully) to set values
            #  inplace, so the assignment is not chained.
            subset.loc[:, indexer] = 0

    subset._mgr._verify_integrity()
    expected = DataFrame({"a": [0, 0], "b": [0.0, 0.0], "c": [5, 6]}, index=range(1, 3))
    tm.assert_frame_equal(subset, expected)
    if using_copy_on_write:
        tm.assert_frame_equal(df, df_orig)
    else:
        # pre-2.0, in the mixed case with BlockManager, only column "a"
        #  would be mutated in the parent frame. this changed with the
        #  enforcement of GH#45333
        df_orig.loc[1:2, ["a", "b"]] = 0
        tm.assert_frame_equal(df, df_orig)


@pytest.mark.parametrize(
    "method",
    [
        lambda df: df[["a", "b"]][0:2],
        lambda df: df[0:2][["a", "b"]],
        lambda df: df[["a", "b"]].iloc[0:2],
        lambda df: df[["a", "b"]].loc[0:1],
        lambda df: df[0:2].iloc[:, 0:2],
        lambda df: df[0:2].loc[:, "a":"b"],  # type: ignore[misc]
    ],
    ids=[
        "row-getitem-slice",
        "column-getitem",
        "row-iloc-slice",
        "row-loc-slice",
        "column-iloc-slice",
        "column-loc-slice",
    ],
)
@pytest.mark.parametrize(
    "dtype", ["int64", "float64"], ids=["single-block", "mixed-block"]
)
def test_subset_chained_getitem(
    request,
    backend,
    method,
    dtype,
    using_copy_on_write,
    using_array_manager,
    warn_copy_on_write,
):
    # Case: creating a subset using multiple, chained getitem calls using views
    # still needs to guarantee proper CoW behaviour
    _, DataFrame, _ = backend
    df = DataFrame(
        {"a": [1, 2, 3], "b": [4, 5, 6], "c": np.array([7, 8, 9], dtype=dtype)}
    )
    df_orig = df.copy()

    # when not using CoW, it depends on whether we have a single block or not
    # and whether we are slicing the columns -> in that case we have a view
    test_callspec = request.node.callspec.id
    if not using_array_manager:
        subset_is_view = test_callspec in (
            "numpy-single-block-column-iloc-slice",
            "numpy-single-block-column-loc-slice",
        )
    else:
        # with ArrayManager, it doesn't matter whether we have
        # single vs mixed block or numpy vs nullable dtypes
        subset_is_view = test_callspec.endswith(
            ("column-iloc-slice", "column-loc-slice")
        )

    # modify subset -> don't modify parent
    subset = method(df)

    with tm.assert_cow_warning(warn_copy_on_write and subset_is_view):
        subset.iloc[0, 0] = 0
    if using_copy_on_write or (not subset_is_view):
        tm.assert_frame_equal(df, df_orig)
    else:
        assert df.iloc[0, 0] == 0

    # modify parent -> don't modify subset
    subset = method(df)
    with tm.assert_cow_warning(warn_copy_on_write and subset_is_view):
        df.iloc[0, 0] = 0
    expected = DataFrame({"a": [1, 2], "b": [4, 5]})
    if using_copy_on_write or not subset_is_view:
        tm.assert_frame_equal(subset, expected)
    else:
        assert subset.iloc[0, 0] == 0


@pytest.mark.parametrize(
    "dtype", ["int64", "float64"], ids=["single-block", "mixed-block"]
)
def test_subset_chained_getitem_column(
    backend, dtype, using_copy_on_write, warn_copy_on_write
):
    # Case: creating a subset using multiple, chained getitem calls using views
    # still needs to guarantee proper CoW behaviour
    dtype_backend, DataFrame, Series = backend
    df = DataFrame(
        {"a": [1, 2, 3], "b": [4, 5, 6], "c": np.array([7, 8, 9], dtype=dtype)}
    )
    df_orig = df.copy()

    # modify subset -> don't modify parent
    subset = df[:]["a"][0:2]
    df._clear_item_cache()
    with tm.assert_cow_warning(warn_copy_on_write):
        subset.iloc[0] = 0
    if using_copy_on_write:
        tm.assert_frame_equal(df, df_orig)
    else:
        assert df.iloc[0, 0] == 0

    # modify parent -> don't modify subset
    subset = df[:]["a"][0:2]
    df._clear_item_cache()
    with tm.assert_cow_warning(warn_copy_on_write):
        df.iloc[0, 0] = 0
    expected = Series([1, 2], name="a")
    if using_copy_on_write:
        tm.assert_series_equal(subset, expected)
    else:
        assert subset.iloc[0] == 0


@pytest.mark.parametrize(
    "method",
    [
        lambda s: s["a":"c"]["a":"b"],  # type: ignore[misc]
        lambda s: s.iloc[0:3].iloc[0:2],
        lambda s: s.loc["a":"c"].loc["a":"b"],  # type: ignore[misc]
        lambda s: s.loc["a":"c"]  # type: ignore[misc]
        .iloc[0:3]
        .iloc[0:2]
        .loc["a":"b"]  # type: ignore[misc]
        .iloc[0:1],
    ],
    ids=["getitem", "iloc", "loc", "long-chain"],
)
def test_subset_chained_getitem_series(
    backend, method, using_copy_on_write, warn_copy_on_write
):
    # Case: creating a subset using multiple, chained getitem calls using views
    # still needs to guarantee proper CoW behaviour
    _, _, Series = backend
    s = Series([1, 2, 3], index=["a", "b", "c"])
    s_orig = s.copy()

    # modify subset -> don't modify parent
    subset = method(s)
    with tm.assert_cow_warning(warn_copy_on_write):
        subset.iloc[0] = 0
    if using_copy_on_write:
        tm.assert_series_equal(s, s_orig)
    else:
        assert s.iloc[0] == 0

    # modify parent -> don't modify subset
    subset = s.iloc[0:3].iloc[0:2]
    with tm.assert_cow_warning(warn_copy_on_write):
        s.iloc[0] = 0
    expected = Series([1, 2], index=["a", "b"])
    if using_copy_on_write:
        tm.assert_series_equal(subset, expected)
    else:
        assert subset.iloc[0] == 0


def test_subset_chained_single_block_row(
    using_copy_on_write, using_array_manager, warn_copy_on_write
):
    # not parametrizing this for dtype backend, since this explicitly tests single block
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]})
    df_orig = df.copy()

    # modify subset -> don't modify parent
    subset = df[:].iloc[0].iloc[0:2]
    with tm.assert_cow_warning(warn_copy_on_write):
        subset.iloc[0] = 0
    if using_copy_on_write or using_array_manager:
        tm.assert_frame_equal(df, df_orig)
    else:
        assert df.iloc[0, 0] == 0

    # modify parent -> don't modify subset
    subset = df[:].iloc[0].iloc[0:2]
    with tm.assert_cow_warning(warn_copy_on_write):
        df.iloc[0, 0] = 0
    expected = Series([1, 4], index=["a", "b"], name=0)
    if using_copy_on_write or using_array_manager:
        tm.assert_series_equal(subset, expected)
    else:
        assert subset.iloc[0] == 0


@pytest.mark.parametrize(
    "method",
    [
        lambda df: df[:],
        lambda df: df.loc[:, :],
        lambda df: df.loc[:],
        lambda df: df.iloc[:, :],
        lambda df: df.iloc[:],
    ],
    ids=["getitem", "loc", "loc-rows", "iloc", "iloc-rows"],
)
def test_null_slice(backend, method, using_copy_on_write, warn_copy_on_write):
    # Case: also all variants of indexing with a null slice (:) should return
    # new objects to ensure we correctly use CoW for the results
    dtype_backend, DataFrame, _ = backend
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]})
    df_orig = df.copy()

    df2 = method(df)

    # we always return new objects (shallow copy), regardless of CoW or not
    assert df2 is not df

    # and those trigger CoW when mutated
    with tm.assert_cow_warning(warn_copy_on_write):
        df2.iloc[0, 0] = 0
    if using_copy_on_write:
        tm.assert_frame_equal(df, df_orig)
    else:
        assert df.iloc[0, 0] == 0


@pytest.mark.parametrize(
    "method",
    [
        lambda s: s[:],
        lambda s: s.loc[:],
        lambda s: s.iloc[:],
    ],
    ids=["getitem", "loc", "iloc"],
)
def test_null_slice_series(backend, method, using_copy_on_write, warn_copy_on_write):
    _, _, Series = backend
    s = Series([1, 2, 3], index=["a", "b", "c"])
    s_orig = s.copy()

    s2 = method(s)

    # we always return new objects, regardless of CoW or not
    assert s2 is not s

    # and those trigger CoW when mutated
    with tm.assert_cow_warning(warn_copy_on_write):
        s2.iloc[0] = 0
    if using_copy_on_write:
        tm.assert_series_equal(s, s_orig)
    else:
        assert s.iloc[0] == 0


# TODO add more tests modifying the parent


# -----------------------------------------------------------------------------
# Series -- Indexing operations taking subset + modifying the subset/parent


def test_series_getitem_slice(backend, using_copy_on_write, warn_copy_on_write):
    # Case: taking a slice of a Series + afterwards modifying the subset
    _, _, Series = backend
    s = Series([1, 2, 3], index=["a", "b", "c"])
    s_orig = s.copy()

    subset = s[:]
    assert np.shares_memory(get_array(subset), get_array(s))

    with tm.assert_cow_warning(warn_copy_on_write):
        subset.iloc[0] = 0

    if using_copy_on_write:
        assert not np.shares_memory(get_array(subset), get_array(s))

    expected = Series([0, 2, 3], index=["a", "b", "c"])
    tm.assert_series_equal(subset, expected)

    if using_copy_on_write:
        # original parent series is not modified (CoW)
        tm.assert_series_equal(s, s_orig)
    else:
        # original parent series is actually updated
        assert s.iloc[0] == 0


def test_series_getitem_ellipsis(using_copy_on_write, warn_copy_on_write):
    # Case: taking a view of a Series using Ellipsis + afterwards modifying the subset
    s = Series([1, 2, 3])
    s_orig = s.copy()

    subset = s[...]
    assert np.shares_memory(get_array(subset), get_array(s))

    with tm.assert_cow_warning(warn_copy_on_write):
        subset.iloc[0] = 0

    if using_copy_on_write:
        assert not np.shares_memory(get_array(subset), get_array(s))

    expected = Series([0, 2, 3])
    tm.assert_series_equal(subset, expected)

    if using_copy_on_write:
        # original parent series is not modified (CoW)
        tm.assert_series_equal(s, s_orig)
    else:
        # original parent series is actually updated
        assert s.iloc[0] == 0


@pytest.mark.parametrize(
    "indexer",
    [slice(0, 2), np.array([True, True, False]), np.array([0, 1])],
    ids=["slice", "mask", "array"],
)
def test_series_subset_set_with_indexer(
    backend, indexer_si, indexer, using_copy_on_write, warn_copy_on_write
):
    # Case: setting values in a viewing Series with an indexer
    _, _, Series = backend
    s = Series([1, 2, 3], index=["a", "b", "c"])
    s_orig = s.copy()
    subset = s[:]

    warn = None
    msg = "Series.__setitem__ treating keys as positions is deprecated"
    if (
        indexer_si is tm.setitem
        and isinstance(indexer, np.ndarray)
        and indexer.dtype.kind == "i"
    ):
        warn = FutureWarning
    if warn_copy_on_write:
        with tm.assert_cow_warning(raise_on_extra_warnings=warn is not None):
            indexer_si(subset)[indexer] = 0
    else:
        with tm.assert_produces_warning(warn, match=msg):
            indexer_si(subset)[indexer] = 0
    expected = Series([0, 0, 3], index=["a", "b", "c"])
    tm.assert_series_equal(subset, expected)

    if using_copy_on_write:
        tm.assert_series_equal(s, s_orig)
    else:
        tm.assert_series_equal(s, expected)


# -----------------------------------------------------------------------------
# del operator


def test_del_frame(backend, using_copy_on_write, warn_copy_on_write):
    # Case: deleting a column with `del` on a viewing child dataframe should
    # not modify parent + update the references
    dtype_backend, DataFrame, _ = backend
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [0.1, 0.2, 0.3]})
    df_orig = df.copy()
    df2 = df[:]

    assert np.shares_memory(get_array(df, "a"), get_array(df2, "a"))

    del df2["b"]

    assert np.shares_memory(get_array(df, "a"), get_array(df2, "a"))
    tm.assert_frame_equal(df, df_orig)
    tm.assert_frame_equal(df2, df_orig[["a", "c"]])
    df2._mgr._verify_integrity()

    with tm.assert_cow_warning(warn_copy_on_write and dtype_backend == "numpy"):
        df.loc[0, "b"] = 200
    assert np.shares_memory(get_array(df, "a"), get_array(df2, "a"))
    df_orig = df.copy()

    with tm.assert_cow_warning(warn_copy_on_write):
        df2.loc[0, "a"] = 100
    if using_copy_on_write:
        # modifying child after deleting a column still doesn't update parent
        tm.assert_frame_equal(df, df_orig)
    else:
        assert df.loc[0, "a"] == 100


def test_del_series(backend):
    _, _, Series = backend
    s = Series([1, 2, 3], index=["a", "b", "c"])
    s_orig = s.copy()
    s2 = s[:]

    assert np.shares_memory(get_array(s), get_array(s2))

    del s2["a"]

    assert not np.shares_memory(get_array(s), get_array(s2))
    tm.assert_series_equal(s, s_orig)
    tm.assert_series_equal(s2, s_orig[["b", "c"]])

    # modifying s2 doesn't need copy on write (due to `del`, s2 is backed by new array)
    values = s2.values
    s2.loc["b"] = 100
    assert values[0] == 100


# -----------------------------------------------------------------------------
# Accessing column as Series


def test_column_as_series(
    backend, using_copy_on_write, warn_copy_on_write, using_array_manager
):
    # Case: selecting a single column now also uses Copy-on-Write
    dtype_backend, DataFrame, Series = backend
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [0.1, 0.2, 0.3]})
    df_orig = df.copy()

    s = df["a"]

    assert np.shares_memory(get_array(s, "a"), get_array(df, "a"))

    if using_copy_on_write or using_array_manager:
        s[0] = 0
    else:
        if warn_copy_on_write:
            with tm.assert_cow_warning():
                s[0] = 0
        else:
            warn = SettingWithCopyWarning if dtype_backend == "numpy" else None
            with pd.option_context("chained_assignment", "warn"):
                with tm.assert_produces_warning(warn):
                    s[0] = 0

    expected = Series([0, 2, 3], name="a")
    tm.assert_series_equal(s, expected)
    if using_copy_on_write:
        # assert not np.shares_memory(s.values, get_array(df, "a"))
        tm.assert_frame_equal(df, df_orig)
        # ensure cached series on getitem is not the changed series
        tm.assert_series_equal(df["a"], df_orig["a"])
    else:
        df_orig.iloc[0, 0] = 0
        tm.assert_frame_equal(df, df_orig)


def test_column_as_series_set_with_upcast(
    backend, using_copy_on_write, using_array_manager, warn_copy_on_write
):
    # Case: selecting a single column now also uses Copy-on-Write -> when
    # setting a value causes an upcast, we don't need to update the parent
    # DataFrame through the cache mechanism
    dtype_backend, DataFrame, Series = backend
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [0.1, 0.2, 0.3]})
    df_orig = df.copy()

    s = df["a"]
    if dtype_backend == "nullable":
        with tm.assert_cow_warning(warn_copy_on_write):
            with pytest.raises(TypeError, match="Invalid value"):
                s[0] = "foo"
        expected = Series([1, 2, 3], name="a")
    elif using_copy_on_write or warn_copy_on_write or using_array_manager:
        # TODO(CoW-warn) assert the FutureWarning for CoW is also raised
        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            s[0] = "foo"
        expected = Series(["foo", 2, 3], dtype=object, name="a")
    else:
        with pd.option_context("chained_assignment", "warn"):
            msg = "|".join(
                [
                    "A value is trying to be set on a copy of a slice from a DataFrame",
                    "Setting an item of incompatible dtype is deprecated",
                ]
            )
            with tm.assert_produces_warning(
                (SettingWithCopyWarning, FutureWarning), match=msg
            ):
                s[0] = "foo"
        expected = Series(["foo", 2, 3], dtype=object, name="a")

    tm.assert_series_equal(s, expected)
    if using_copy_on_write:
        tm.assert_frame_equal(df, df_orig)
        # ensure cached series on getitem is not the changed series
        tm.assert_series_equal(df["a"], df_orig["a"])
    else:
        df_orig["a"] = expected
        tm.assert_frame_equal(df, df_orig)


@pytest.mark.parametrize(
    "method",
    [
        lambda df: df["a"],
        lambda df: df.loc[:, "a"],
        lambda df: df.iloc[:, 0],
    ],
    ids=["getitem", "loc", "iloc"],
)
def test_column_as_series_no_item_cache(
    request,
    backend,
    method,
    using_copy_on_write,
    warn_copy_on_write,
    using_array_manager,
):
    # Case: selecting a single column (which now also uses Copy-on-Write to protect
    # the view) should always give a new object (i.e. not make use of a cache)
    dtype_backend, DataFrame, _ = backend
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [0.1, 0.2, 0.3]})
    df_orig = df.copy()

    s1 = method(df)
    s2 = method(df)

    is_iloc = "iloc" in request.node.name
    if using_copy_on_write or warn_copy_on_write or is_iloc:
        assert s1 is not s2
    else:
        assert s1 is s2

    if using_copy_on_write or using_array_manager:
        s1.iloc[0] = 0
    elif warn_copy_on_write:
        with tm.assert_cow_warning():
            s1.iloc[0] = 0
    else:
        warn = SettingWithCopyWarning if dtype_backend == "numpy" else None
        with pd.option_context("chained_assignment", "warn"):
            with tm.assert_produces_warning(warn):
                s1.iloc[0] = 0

    if using_copy_on_write:
        tm.assert_series_equal(s2, df_orig["a"])
        tm.assert_frame_equal(df, df_orig)
    else:
        assert s2.iloc[0] == 0


# TODO add tests for other indexing methods on the Series


def test_dataframe_add_column_from_series(backend, using_copy_on_write):
    # Case: adding a new column to a DataFrame from an existing column/series
    # -> delays copy under CoW
    _, DataFrame, Series = backend
    df = DataFrame({"a": [1, 2, 3], "b": [0.1, 0.2, 0.3]})

    s = Series([10, 11, 12])
    df["new"] = s
    if using_copy_on_write:
        assert np.shares_memory(get_array(df, "new"), get_array(s))
    else:
        assert not np.shares_memory(get_array(df, "new"), get_array(s))

    # editing series -> doesn't modify column in frame
    s[0] = 0
    expected = DataFrame({"a": [1, 2, 3], "b": [0.1, 0.2, 0.3], "new": [10, 11, 12]})
    tm.assert_frame_equal(df, expected)


@pytest.mark.parametrize("val", [100, "a"])
@pytest.mark.parametrize(
    "indexer_func, indexer",
    [
        (tm.loc, (0, "a")),
        (tm.iloc, (0, 0)),
        (tm.loc, ([0], "a")),
        (tm.iloc, ([0], 0)),
        (tm.loc, (slice(None), "a")),
        (tm.iloc, (slice(None), 0)),
    ],
)
@pytest.mark.parametrize(
    "col", [[0.1, 0.2, 0.3], [7, 8, 9]], ids=["mixed-block", "single-block"]
)
def test_set_value_copy_only_necessary_column(
    using_copy_on_write, warn_copy_on_write, indexer_func, indexer, val, col
):
    # When setting inplace, only copy column that is modified instead of the whole
    # block (by splitting the block)
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": col})
    df_orig = df.copy()
    view = df[:]

    if val == "a" and not warn_copy_on_write:
        with tm.assert_produces_warning(
            FutureWarning, match="Setting an item of incompatible dtype is deprecated"
        ):
            indexer_func(df)[indexer] = val
    if val == "a" and warn_copy_on_write:
        with tm.assert_produces_warning(
            FutureWarning, match="incompatible dtype|Setting a value on a view"
        ):
            indexer_func(df)[indexer] = val
    else:
        with tm.assert_cow_warning(warn_copy_on_write and val == 100):
            indexer_func(df)[indexer] = val

    if using_copy_on_write:
        assert np.shares_memory(get_array(df, "b"), get_array(view, "b"))
        assert not np.shares_memory(get_array(df, "a"), get_array(view, "a"))
        tm.assert_frame_equal(view, df_orig)
    else:
        assert np.shares_memory(get_array(df, "c"), get_array(view, "c"))
        if val == "a":
            assert not np.shares_memory(get_array(df, "a"), get_array(view, "a"))
        else:
            assert np.shares_memory(get_array(df, "a"), get_array(view, "a"))


def test_series_midx_slice(using_copy_on_write, warn_copy_on_write):
    ser = Series([1, 2, 3], index=pd.MultiIndex.from_arrays([[1, 1, 2], [3, 4, 5]]))
    ser_orig = ser.copy()
    result = ser[1]
    assert np.shares_memory(get_array(ser), get_array(result))
    with tm.assert_cow_warning(warn_copy_on_write):
        result.iloc[0] = 100
    if using_copy_on_write:
        tm.assert_series_equal(ser, ser_orig)
    else:
        expected = Series(
            [100, 2, 3], index=pd.MultiIndex.from_arrays([[1, 1, 2], [3, 4, 5]])
        )
        tm.assert_series_equal(ser, expected)


def test_getitem_midx_slice(
    using_copy_on_write, warn_copy_on_write, using_array_manager
):
    df = DataFrame({("a", "x"): [1, 2], ("a", "y"): 1, ("b", "x"): 2})
    df_orig = df.copy()
    new_df = df[("a",)]

    if using_copy_on_write:
        assert not new_df._mgr._has_no_reference(0)

    if not using_array_manager:
        assert np.shares_memory(get_array(df, ("a", "x")), get_array(new_df, "x"))
    if using_copy_on_write:
        new_df.iloc[0, 0] = 100
        tm.assert_frame_equal(df_orig, df)
    else:
        if warn_copy_on_write:
            with tm.assert_cow_warning():
                new_df.iloc[0, 0] = 100
        else:
            with pd.option_context("chained_assignment", "warn"):
                with tm.assert_produces_warning(SettingWithCopyWarning):
                    new_df.iloc[0, 0] = 100
        assert df.iloc[0, 0] == 100


def test_series_midx_tuples_slice(using_copy_on_write, warn_copy_on_write):
    ser = Series(
        [1, 2, 3],
        index=pd.MultiIndex.from_tuples([((1, 2), 3), ((1, 2), 4), ((2, 3), 4)]),
    )
    result = ser[(1, 2)]
    assert np.shares_memory(get_array(ser), get_array(result))
    with tm.assert_cow_warning(warn_copy_on_write):
        result.iloc[0] = 100
    if using_copy_on_write:
        expected = Series(
            [1, 2, 3],
            index=pd.MultiIndex.from_tuples([((1, 2), 3), ((1, 2), 4), ((2, 3), 4)]),
        )
        tm.assert_series_equal(ser, expected)


def test_midx_read_only_bool_indexer():
    # GH#56635
    def mklbl(prefix, n):
        return [f"{prefix}{i}" for i in range(n)]

    idx = pd.MultiIndex.from_product(
        [mklbl("A", 4), mklbl("B", 2), mklbl("C", 4), mklbl("D", 2)]
    )
    cols = pd.MultiIndex.from_tuples(
        [("a", "foo"), ("a", "bar"), ("b", "foo"), ("b", "bah")], names=["lvl0", "lvl1"]
    )
    df = DataFrame(1, index=idx, columns=cols).sort_index().sort_index(axis=1)

    mask = df[("a", "foo")] == 1
    expected_mask = mask.copy()
    result = df.loc[pd.IndexSlice[mask, :, ["C1", "C3"]], :]
    expected = df.loc[pd.IndexSlice[:, :, ["C1", "C3"]], :]
    tm.assert_frame_equal(result, expected)
    tm.assert_series_equal(mask, expected_mask)


def test_loc_enlarging_with_dataframe(using_copy_on_write):
    df = DataFrame({"a": [1, 2, 3]})
    rhs = DataFrame({"b": [1, 2, 3], "c": [4, 5, 6]})
    rhs_orig = rhs.copy()
    df.loc[:, ["b", "c"]] = rhs
    if using_copy_on_write:
        assert np.shares_memory(get_array(df, "b"), get_array(rhs, "b"))
        assert np.shares_memory(get_array(df, "c"), get_array(rhs, "c"))
        assert not df._mgr._has_no_reference(1)
    else:
        assert not np.shares_memory(get_array(df, "b"), get_array(rhs, "b"))

    df.iloc[0, 1] = 100
    tm.assert_frame_equal(rhs, rhs_orig)
