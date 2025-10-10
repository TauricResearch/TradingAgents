"""
Tests of the groupby API, including internal consistency and with other pandas objects.

Tests in this file should only check the existence, names, and arguments of groupby
methods. It should not test the results of any groupby operation.
"""

import inspect

import pytest

from pandas import (
    DataFrame,
    Series,
)
from pandas.core.groupby.base import (
    groupby_other_methods,
    reduction_kernels,
    transformation_kernels,
)
from pandas.core.groupby.generic import (
    DataFrameGroupBy,
    SeriesGroupBy,
)


def test_tab_completion(multiindex_dataframe_random_data):
    grp = multiindex_dataframe_random_data.groupby(level="second")
    results = {v for v in dir(grp) if not v.startswith("_")}
    expected = {
        "A",
        "B",
        "C",
        "agg",
        "aggregate",
        "apply",
        "boxplot",
        "filter",
        "first",
        "get_group",
        "groups",
        "hist",
        "indices",
        "last",
        "max",
        "mean",
        "median",
        "min",
        "ngroups",
        "nth",
        "ohlc",
        "plot",
        "prod",
        "size",
        "std",
        "sum",
        "transform",
        "var",
        "sem",
        "count",
        "nunique",
        "head",
        "describe",
        "cummax",
        "quantile",
        "rank",
        "cumprod",
        "tail",
        "resample",
        "cummin",
        "fillna",
        "cumsum",
        "cumcount",
        "ngroup",
        "all",
        "shift",
        "skew",
        "take",
        "pct_change",
        "any",
        "corr",
        "corrwith",
        "cov",
        "dtypes",
        "ndim",
        "diff",
        "idxmax",
        "idxmin",
        "ffill",
        "bfill",
        "rolling",
        "expanding",
        "pipe",
        "sample",
        "ewm",
        "value_counts",
    }
    assert results == expected


def test_all_methods_categorized(multiindex_dataframe_random_data):
    grp = multiindex_dataframe_random_data.groupby(
        multiindex_dataframe_random_data.iloc[:, 0]
    )
    names = {_ for _ in dir(grp) if not _.startswith("_")} - set(
        multiindex_dataframe_random_data.columns
    )
    new_names = set(names)
    new_names -= reduction_kernels
    new_names -= transformation_kernels
    new_names -= groupby_other_methods

    assert not reduction_kernels & transformation_kernels
    assert not reduction_kernels & groupby_other_methods
    assert not transformation_kernels & groupby_other_methods

    # new public method?
    if new_names:
        msg = f"""
There are uncategorized methods defined on the Grouper class:
{new_names}.

Was a new method recently added?

Every public method On Grouper must appear in exactly one the
following three lists defined in pandas.core.groupby.base:
- `reduction_kernels`
- `transformation_kernels`
- `groupby_other_methods`
see the comments in pandas/core/groupby/base.py for guidance on
how to fix this test.
        """
        raise AssertionError(msg)

    # removed a public method?
    all_categorized = reduction_kernels | transformation_kernels | groupby_other_methods
    if names != all_categorized:
        msg = f"""
Some methods which are supposed to be on the Grouper class
are missing:
{all_categorized - names}.

They're still defined in one of the lists that live in pandas/core/groupby/base.py.
If you removed a method, you should update them
"""
        raise AssertionError(msg)


def test_frame_consistency(groupby_func):
    # GH#48028
    if groupby_func in ("first", "last"):
        msg = "first and last are entirely different between frame and groupby"
        pytest.skip(reason=msg)

    if groupby_func in ("cumcount", "ngroup"):
        assert not hasattr(DataFrame, groupby_func)
        return

    frame_method = getattr(DataFrame, groupby_func)
    gb_method = getattr(DataFrameGroupBy, groupby_func)
    result = set(inspect.signature(gb_method).parameters)
    if groupby_func == "size":
        # "size" is a method on GroupBy but property on DataFrame:
        expected = {"self"}
    else:
        expected = set(inspect.signature(frame_method).parameters)

    # Exclude certain arguments from result and expected depending on the operation
    # Some of these may be purposeful inconsistencies between the APIs
    exclude_expected, exclude_result = set(), set()
    if groupby_func in ("any", "all"):
        exclude_expected = {"kwargs", "bool_only", "axis"}
    elif groupby_func in ("count",):
        exclude_expected = {"numeric_only", "axis"}
    elif groupby_func in ("nunique",):
        exclude_expected = {"axis"}
    elif groupby_func in ("max", "min"):
        exclude_expected = {"axis", "kwargs", "skipna"}
        exclude_result = {"min_count", "engine", "engine_kwargs"}
    elif groupby_func in ("mean", "std", "sum", "var"):
        exclude_expected = {"axis", "kwargs", "skipna"}
        exclude_result = {"engine", "engine_kwargs"}
    elif groupby_func in ("median", "prod", "sem"):
        exclude_expected = {"axis", "kwargs", "skipna"}
    elif groupby_func in ("backfill", "bfill", "ffill", "pad"):
        exclude_expected = {"downcast", "inplace", "axis", "limit_area"}
    elif groupby_func in ("cummax", "cummin"):
        exclude_expected = {"skipna", "args"}
        exclude_result = {"numeric_only"}
    elif groupby_func in ("cumprod", "cumsum"):
        exclude_expected = {"skipna"}
    elif groupby_func in ("pct_change",):
        exclude_expected = {"kwargs"}
        exclude_result = {"axis"}
    elif groupby_func in ("rank",):
        exclude_expected = {"numeric_only"}
    elif groupby_func in ("quantile",):
        exclude_expected = {"method", "axis"}

    # Ensure excluded arguments are actually in the signatures
    assert result & exclude_result == exclude_result
    assert expected & exclude_expected == exclude_expected

    result -= exclude_result
    expected -= exclude_expected
    assert result == expected


def test_series_consistency(request, groupby_func):
    # GH#48028
    if groupby_func in ("first", "last"):
        pytest.skip("first and last are entirely different between Series and groupby")

    if groupby_func in ("cumcount", "corrwith", "ngroup"):
        assert not hasattr(Series, groupby_func)
        return

    series_method = getattr(Series, groupby_func)
    gb_method = getattr(SeriesGroupBy, groupby_func)
    result = set(inspect.signature(gb_method).parameters)
    if groupby_func == "size":
        # "size" is a method on GroupBy but property on Series
        expected = {"self"}
    else:
        expected = set(inspect.signature(series_method).parameters)

    # Exclude certain arguments from result and expected depending on the operation
    # Some of these may be purposeful inconsistencies between the APIs
    exclude_expected, exclude_result = set(), set()
    if groupby_func in ("any", "all"):
        exclude_expected = {"kwargs", "bool_only", "axis"}
    elif groupby_func in ("diff",):
        exclude_result = {"axis"}
    elif groupby_func in ("max", "min"):
        exclude_expected = {"axis", "kwargs", "skipna"}
        exclude_result = {"min_count", "engine", "engine_kwargs"}
    elif groupby_func in ("mean", "std", "sum", "var"):
        exclude_expected = {"axis", "kwargs", "skipna"}
        exclude_result = {"engine", "engine_kwargs"}
    elif groupby_func in ("median", "prod", "sem"):
        exclude_expected = {"axis", "kwargs", "skipna"}
    elif groupby_func in ("backfill", "bfill", "ffill", "pad"):
        exclude_expected = {"downcast", "inplace", "axis", "limit_area"}
    elif groupby_func in ("cummax", "cummin"):
        exclude_expected = {"skipna", "args"}
        exclude_result = {"numeric_only"}
    elif groupby_func in ("cumprod", "cumsum"):
        exclude_expected = {"skipna"}
    elif groupby_func in ("pct_change",):
        exclude_expected = {"kwargs"}
        exclude_result = {"axis"}
    elif groupby_func in ("rank",):
        exclude_expected = {"numeric_only"}
    elif groupby_func in ("idxmin", "idxmax"):
        exclude_expected = {"args", "kwargs"}
    elif groupby_func in ("quantile",):
        exclude_result = {"numeric_only"}

    # Ensure excluded arguments are actually in the signatures
    assert result & exclude_result == exclude_result
    assert expected & exclude_expected == exclude_expected

    result -= exclude_result
    expected -= exclude_expected
    assert result == expected
