from datetime import datetime

import numpy as np
import pytest

from pandas import (
    DataFrame,
    Index,
    Series,
)
import pandas._testing as tm
from pandas.tests.groupby import get_groupby_method_args

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager|Passing a SingleBlockManager:DeprecationWarning"
)


@pytest.mark.parametrize(
    "obj",
    [
        tm.SubclassedDataFrame({"A": np.arange(0, 10)}),
        tm.SubclassedSeries(np.arange(0, 10), name="A"),
    ],
)
def test_groupby_preserves_subclass(obj, groupby_func):
    # GH28330 -- preserve subclass through groupby operations

    if isinstance(obj, Series) and groupby_func in {"corrwith"}:
        pytest.skip(f"Not applicable for Series and {groupby_func}")

    grouped = obj.groupby(np.arange(0, 10))

    # Groups should preserve subclass type
    assert isinstance(grouped.get_group(0), type(obj))

    args = get_groupby_method_args(groupby_func, obj)

    warn = FutureWarning if groupby_func == "fillna" else None
    msg = f"{type(grouped).__name__}.fillna is deprecated"
    with tm.assert_produces_warning(warn, match=msg, raise_on_extra_warnings=False):
        result1 = getattr(grouped, groupby_func)(*args)
    with tm.assert_produces_warning(warn, match=msg, raise_on_extra_warnings=False):
        result2 = grouped.agg(groupby_func, *args)

    # Reduction or transformation kernels should preserve type
    slices = {"ngroup", "cumcount", "size"}
    if isinstance(obj, DataFrame) and groupby_func in slices:
        assert isinstance(result1, tm.SubclassedSeries)
    else:
        assert isinstance(result1, type(obj))

    # Confirm .agg() groupby operations return same results
    if isinstance(result1, DataFrame):
        tm.assert_frame_equal(result1, result2)
    else:
        tm.assert_series_equal(result1, result2)


def test_groupby_preserves_metadata():
    # GH-37343
    custom_df = tm.SubclassedDataFrame({"a": [1, 2, 3], "b": [1, 1, 2], "c": [7, 8, 9]})
    assert "testattr" in custom_df._metadata
    custom_df.testattr = "hello"
    for _, group_df in custom_df.groupby("c"):
        assert group_df.testattr == "hello"

    # GH-45314
    def func(group):
        assert isinstance(group, tm.SubclassedDataFrame)
        assert hasattr(group, "testattr")
        assert group.testattr == "hello"
        return group.testattr

    msg = "DataFrameGroupBy.apply operated on the grouping columns"
    with tm.assert_produces_warning(
        FutureWarning,
        match=msg,
        raise_on_extra_warnings=False,
        check_stacklevel=False,
    ):
        result = custom_df.groupby("c").apply(func)
    expected = tm.SubclassedSeries(["hello"] * 3, index=Index([7, 8, 9], name="c"))
    tm.assert_series_equal(result, expected)

    result = custom_df.groupby("c").apply(func, include_groups=False)
    tm.assert_series_equal(result, expected)

    # https://github.com/pandas-dev/pandas/pull/56761
    result = custom_df.groupby("c")[["a", "b"]].apply(func)
    tm.assert_series_equal(result, expected)

    def func2(group):
        assert isinstance(group, tm.SubclassedSeries)
        assert hasattr(group, "testattr")
        return group.testattr

    custom_series = tm.SubclassedSeries([1, 2, 3])
    custom_series.testattr = "hello"
    result = custom_series.groupby(custom_df["c"]).apply(func2)
    tm.assert_series_equal(result, expected)
    result = custom_series.groupby(custom_df["c"]).agg(func2)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("obj", [DataFrame, tm.SubclassedDataFrame])
def test_groupby_resample_preserves_subclass(obj):
    # GH28330 -- preserve subclass through groupby.resample()

    df = obj(
        {
            "Buyer": Series("Carl Carl Carl Carl Joe Carl".split(), dtype=object),
            "Quantity": [18, 3, 5, 1, 9, 3],
            "Date": [
                datetime(2013, 9, 1, 13, 0),
                datetime(2013, 9, 1, 13, 5),
                datetime(2013, 10, 1, 20, 0),
                datetime(2013, 10, 3, 10, 0),
                datetime(2013, 12, 2, 12, 0),
                datetime(2013, 9, 2, 14, 0),
            ],
        }
    )
    df = df.set_index("Date")

    # Confirm groupby.resample() preserves dataframe type
    msg = "DataFrameGroupBy.resample operated on the grouping columns"
    with tm.assert_produces_warning(
        FutureWarning,
        match=msg,
        raise_on_extra_warnings=False,
        check_stacklevel=False,
    ):
        result = df.groupby("Buyer").resample("5D").sum()
    assert isinstance(result, obj)
