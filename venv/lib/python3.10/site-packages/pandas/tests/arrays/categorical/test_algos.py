import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm


@pytest.mark.parametrize("ordered", [True, False])
@pytest.mark.parametrize("categories", [["b", "a", "c"], ["a", "b", "c", "d"]])
def test_factorize(categories, ordered):
    cat = pd.Categorical(
        ["b", "b", "a", "c", None], categories=categories, ordered=ordered
    )
    codes, uniques = pd.factorize(cat)
    expected_codes = np.array([0, 0, 1, 2, -1], dtype=np.intp)
    expected_uniques = pd.Categorical(
        ["b", "a", "c"], categories=categories, ordered=ordered
    )

    tm.assert_numpy_array_equal(codes, expected_codes)
    tm.assert_categorical_equal(uniques, expected_uniques)


def test_factorized_sort():
    cat = pd.Categorical(["b", "b", None, "a"])
    codes, uniques = pd.factorize(cat, sort=True)
    expected_codes = np.array([1, 1, -1, 0], dtype=np.intp)
    expected_uniques = pd.Categorical(["a", "b"])

    tm.assert_numpy_array_equal(codes, expected_codes)
    tm.assert_categorical_equal(uniques, expected_uniques)


def test_factorized_sort_ordered():
    cat = pd.Categorical(
        ["b", "b", None, "a"], categories=["c", "b", "a"], ordered=True
    )

    codes, uniques = pd.factorize(cat, sort=True)
    expected_codes = np.array([0, 0, -1, 1], dtype=np.intp)
    expected_uniques = pd.Categorical(
        ["b", "a"], categories=["c", "b", "a"], ordered=True
    )

    tm.assert_numpy_array_equal(codes, expected_codes)
    tm.assert_categorical_equal(uniques, expected_uniques)


def test_isin_cats():
    # GH2003
    cat = pd.Categorical(["a", "b", np.nan])

    result = cat.isin(["a", np.nan])
    expected = np.array([True, False, True], dtype=bool)
    tm.assert_numpy_array_equal(expected, result)

    result = cat.isin(["a", "c"])
    expected = np.array([True, False, False], dtype=bool)
    tm.assert_numpy_array_equal(expected, result)


@pytest.mark.parametrize("value", [[""], [None, ""], [pd.NaT, ""]])
def test_isin_cats_corner_cases(value):
    # GH36550
    cat = pd.Categorical([""])
    result = cat.isin(value)
    expected = np.array([True], dtype=bool)
    tm.assert_numpy_array_equal(expected, result)


@pytest.mark.parametrize("empty", [[], pd.Series(dtype=object), np.array([])])
def test_isin_empty(empty):
    s = pd.Categorical(["a", "b"])
    expected = np.array([False, False], dtype=bool)

    result = s.isin(empty)
    tm.assert_numpy_array_equal(expected, result)


def test_diff():
    ser = pd.Series([1, 2, 3], dtype="category")

    msg = "Convert to a suitable dtype"
    with pytest.raises(TypeError, match=msg):
        ser.diff()

    df = ser.to_frame(name="A")
    with pytest.raises(TypeError, match=msg):
        df.diff()
