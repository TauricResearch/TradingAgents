import pytest

import pandas as pd
from pandas import Categorical
import pandas._testing as tm


@pytest.mark.parametrize(
    "to_replace,value,expected,flip_categories",
    [
        # one-to-one
        (1, 2, [2, 2, 3], False),
        (1, 4, [4, 2, 3], False),
        (4, 1, [1, 2, 3], False),
        (5, 6, [1, 2, 3], False),
        # many-to-one
        ([1], 2, [2, 2, 3], False),
        ([1, 2], 3, [3, 3, 3], False),
        ([1, 2], 4, [4, 4, 3], False),
        ((1, 2, 4), 5, [5, 5, 3], False),
        ((5, 6), 2, [1, 2, 3], False),
        ([1], [2], [2, 2, 3], False),
        ([1, 4], [5, 2], [5, 2, 3], False),
        # GH49404: overlap between to_replace and value
        ([1, 2, 3], [2, 3, 4], [2, 3, 4], False),
        # GH50872, GH46884: replace with null
        (1, None, [None, 2, 3], False),
        (1, pd.NA, [None, 2, 3], False),
        # check_categorical sorts categories, which crashes on mixed dtypes
        (3, "4", [1, 2, "4"], False),
        ([1, 2, "3"], "5", ["5", "5", 3], True),
    ],
)
@pytest.mark.filterwarnings(
    "ignore:.*with CategoricalDtype is deprecated:FutureWarning"
)
def test_replace_categorical_series(to_replace, value, expected, flip_categories):
    # GH 31720

    ser = pd.Series([1, 2, 3], dtype="category")
    result = ser.replace(to_replace, value)
    expected = pd.Series(expected, dtype="category")
    ser.replace(to_replace, value, inplace=True)

    if flip_categories:
        expected = expected.cat.set_categories(expected.cat.categories[::-1])

    tm.assert_series_equal(expected, result, check_category_order=False)
    tm.assert_series_equal(expected, ser, check_category_order=False)


@pytest.mark.parametrize(
    "to_replace, value, result, expected_error_msg",
    [
        ("b", "c", ["a", "c"], "Categorical.categories are different"),
        ("c", "d", ["a", "b"], None),
        # https://github.com/pandas-dev/pandas/issues/33288
        ("a", "a", ["a", "b"], None),
        ("b", None, ["a", None], "Categorical.categories length are different"),
    ],
)
def test_replace_categorical(to_replace, value, result, expected_error_msg):
    # GH#26988
    cat = Categorical(["a", "b"])
    expected = Categorical(result)
    msg = (
        r"The behavior of Series\.replace \(and DataFrame.replace\) "
        "with CategoricalDtype"
    )
    warn = FutureWarning if expected_error_msg is not None else None
    with tm.assert_produces_warning(warn, match=msg):
        result = pd.Series(cat, copy=False).replace(to_replace, value)._values

    tm.assert_categorical_equal(result, expected)
    if to_replace == "b":  # the "c" test is supposed to be unchanged
        with pytest.raises(AssertionError, match=expected_error_msg):
            # ensure non-inplace call does not affect original
            tm.assert_categorical_equal(cat, expected)

    ser = pd.Series(cat, copy=False)
    with tm.assert_produces_warning(warn, match=msg):
        ser.replace(to_replace, value, inplace=True)
    tm.assert_categorical_equal(cat, expected)


def test_replace_categorical_ea_dtype():
    # GH49404
    cat = Categorical(pd.array(["a", "b"], dtype="string"))
    msg = (
        r"The behavior of Series\.replace \(and DataFrame.replace\) "
        "with CategoricalDtype"
    )
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = pd.Series(cat).replace(["a", "b"], ["c", pd.NA])._values
    expected = Categorical(pd.array(["c", pd.NA], dtype="string"))
    tm.assert_categorical_equal(result, expected)


def test_replace_maintain_ordering():
    # GH51016
    dtype = pd.CategoricalDtype([0, 1, 2], ordered=True)
    ser = pd.Series([0, 1, 2], dtype=dtype)
    msg = (
        r"The behavior of Series\.replace \(and DataFrame.replace\) "
        "with CategoricalDtype"
    )
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = ser.replace(0, 2)
    expected_dtype = pd.CategoricalDtype([1, 2], ordered=True)
    expected = pd.Series([2, 1, 2], dtype=expected_dtype)
    tm.assert_series_equal(expected, result, check_category_order=True)
