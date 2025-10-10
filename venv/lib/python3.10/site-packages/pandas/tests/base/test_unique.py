import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.tests.base.common import allow_na_ops


@pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
def test_unique(index_or_series_obj):
    obj = index_or_series_obj
    obj = np.repeat(obj, range(1, len(obj) + 1))
    result = obj.unique()

    # dict.fromkeys preserves the order
    unique_values = list(dict.fromkeys(obj.values))
    if isinstance(obj, pd.MultiIndex):
        expected = pd.MultiIndex.from_tuples(unique_values)
        expected.names = obj.names
        tm.assert_index_equal(result, expected, exact=True)
    elif isinstance(obj, pd.Index):
        expected = pd.Index(unique_values, dtype=obj.dtype)
        if isinstance(obj.dtype, pd.DatetimeTZDtype):
            expected = expected.normalize()
        tm.assert_index_equal(result, expected, exact=True)
    else:
        expected = np.array(unique_values)
        tm.assert_numpy_array_equal(result, expected)


@pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
@pytest.mark.parametrize("null_obj", [np.nan, None])
def test_unique_null(null_obj, index_or_series_obj):
    obj = index_or_series_obj

    if not allow_na_ops(obj):
        pytest.skip("type doesn't allow for NA operations")
    elif len(obj) < 1:
        pytest.skip("Test doesn't make sense on empty data")
    elif isinstance(obj, pd.MultiIndex):
        pytest.skip(f"MultiIndex can't hold '{null_obj}'")

    values = obj._values
    values[0:2] = null_obj

    klass = type(obj)
    repeated_values = np.repeat(values, range(1, len(values) + 1))
    obj = klass(repeated_values, dtype=obj.dtype)
    result = obj.unique()

    unique_values_raw = dict.fromkeys(obj.values)
    # because np.nan == np.nan is False, but None == None is True
    # np.nan would be duplicated, whereas None wouldn't
    unique_values_not_null = [val for val in unique_values_raw if not pd.isnull(val)]
    unique_values = [null_obj] + unique_values_not_null

    if isinstance(obj, pd.Index):
        expected = pd.Index(unique_values, dtype=obj.dtype)
        if isinstance(obj.dtype, pd.DatetimeTZDtype):
            result = result.normalize()
            expected = expected.normalize()
        tm.assert_index_equal(result, expected, exact=True)
    else:
        expected = np.array(unique_values, dtype=obj.dtype)
        tm.assert_numpy_array_equal(result, expected)


def test_nunique(index_or_series_obj):
    obj = index_or_series_obj
    obj = np.repeat(obj, range(1, len(obj) + 1))
    expected = len(obj.unique())
    assert obj.nunique(dropna=False) == expected


@pytest.mark.parametrize("null_obj", [np.nan, None])
def test_nunique_null(null_obj, index_or_series_obj):
    obj = index_or_series_obj

    if not allow_na_ops(obj):
        pytest.skip("type doesn't allow for NA operations")
    elif isinstance(obj, pd.MultiIndex):
        pytest.skip(f"MultiIndex can't hold '{null_obj}'")

    values = obj._values
    values[0:2] = null_obj

    klass = type(obj)
    repeated_values = np.repeat(values, range(1, len(values) + 1))
    obj = klass(repeated_values, dtype=obj.dtype)

    if isinstance(obj, pd.CategoricalIndex):
        assert obj.nunique() == len(obj.categories)
        assert obj.nunique(dropna=False) == len(obj.categories) + 1
    else:
        num_unique_values = len(obj.unique())
        assert obj.nunique() == max(0, num_unique_values - 1)
        assert obj.nunique(dropna=False) == max(0, num_unique_values)


@pytest.mark.single_cpu
def test_unique_bad_unicode(index_or_series):
    # regression test for #34550
    uval = "\ud83d"  # smiley emoji

    obj = index_or_series([uval] * 2, dtype=object)
    result = obj.unique()

    if isinstance(obj, pd.Index):
        expected = pd.Index(["\ud83d"], dtype=object)
        tm.assert_index_equal(result, expected, exact=True)
    else:
        expected = np.array(["\ud83d"], dtype=object)
        tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize("dropna", [True, False])
def test_nunique_dropna(dropna):
    # GH37566
    ser = pd.Series(["yes", "yes", pd.NA, np.nan, None, pd.NaT])
    res = ser.nunique(dropna)
    assert res == 1 if dropna else 5
