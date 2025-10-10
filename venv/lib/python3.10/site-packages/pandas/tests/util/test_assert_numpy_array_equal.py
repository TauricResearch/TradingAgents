import copy

import numpy as np
import pytest

import pandas as pd
from pandas import Timestamp
import pandas._testing as tm


def test_assert_numpy_array_equal_shape_mismatch():
    msg = """numpy array are different

numpy array shapes are different
\\[left\\]:  \\(2L*,\\)
\\[right\\]: \\(3L*,\\)"""

    with pytest.raises(AssertionError, match=msg):
        tm.assert_numpy_array_equal(np.array([1, 2]), np.array([3, 4, 5]))


def test_assert_numpy_array_equal_bad_type():
    expected = "Expected type"

    with pytest.raises(AssertionError, match=expected):
        tm.assert_numpy_array_equal(1, 2)


@pytest.mark.parametrize(
    "a,b,klass1,klass2",
    [(np.array([1]), 1, "ndarray", "int"), (1, np.array([1]), "int", "ndarray")],
)
def test_assert_numpy_array_equal_class_mismatch(a, b, klass1, klass2):
    msg = f"""numpy array are different

numpy array classes are different
\\[left\\]:  {klass1}
\\[right\\]: {klass2}"""

    with pytest.raises(AssertionError, match=msg):
        tm.assert_numpy_array_equal(a, b)


def test_assert_numpy_array_equal_value_mismatch1():
    msg = """numpy array are different

numpy array values are different \\(66\\.66667 %\\)
\\[left\\]:  \\[nan, 2\\.0, 3\\.0\\]
\\[right\\]: \\[1\\.0, nan, 3\\.0\\]"""

    with pytest.raises(AssertionError, match=msg):
        tm.assert_numpy_array_equal(np.array([np.nan, 2, 3]), np.array([1, np.nan, 3]))


def test_assert_numpy_array_equal_value_mismatch2():
    msg = """numpy array are different

numpy array values are different \\(50\\.0 %\\)
\\[left\\]:  \\[1, 2\\]
\\[right\\]: \\[1, 3\\]"""

    with pytest.raises(AssertionError, match=msg):
        tm.assert_numpy_array_equal(np.array([1, 2]), np.array([1, 3]))


def test_assert_numpy_array_equal_value_mismatch3():
    msg = """numpy array are different

numpy array values are different \\(16\\.66667 %\\)
\\[left\\]:  \\[\\[1, 2\\], \\[3, 4\\], \\[5, 6\\]\\]
\\[right\\]: \\[\\[1, 3\\], \\[3, 4\\], \\[5, 6\\]\\]"""

    with pytest.raises(AssertionError, match=msg):
        tm.assert_numpy_array_equal(
            np.array([[1, 2], [3, 4], [5, 6]]), np.array([[1, 3], [3, 4], [5, 6]])
        )


def test_assert_numpy_array_equal_value_mismatch4():
    msg = """numpy array are different

numpy array values are different \\(50\\.0 %\\)
\\[left\\]:  \\[1\\.1, 2\\.000001\\]
\\[right\\]: \\[1\\.1, 2.0\\]"""

    with pytest.raises(AssertionError, match=msg):
        tm.assert_numpy_array_equal(np.array([1.1, 2.000001]), np.array([1.1, 2.0]))


def test_assert_numpy_array_equal_value_mismatch5():
    msg = """numpy array are different

numpy array values are different \\(16\\.66667 %\\)
\\[left\\]:  \\[\\[1, 2\\], \\[3, 4\\], \\[5, 6\\]\\]
\\[right\\]: \\[\\[1, 3\\], \\[3, 4\\], \\[5, 6\\]\\]"""

    with pytest.raises(AssertionError, match=msg):
        tm.assert_numpy_array_equal(
            np.array([[1, 2], [3, 4], [5, 6]]), np.array([[1, 3], [3, 4], [5, 6]])
        )


def test_assert_numpy_array_equal_value_mismatch6():
    msg = """numpy array are different

numpy array values are different \\(25\\.0 %\\)
\\[left\\]:  \\[\\[1, 2\\], \\[3, 4\\]\\]
\\[right\\]: \\[\\[1, 3\\], \\[3, 4\\]\\]"""

    with pytest.raises(AssertionError, match=msg):
        tm.assert_numpy_array_equal(
            np.array([[1, 2], [3, 4]]), np.array([[1, 3], [3, 4]])
        )


def test_assert_numpy_array_equal_shape_mismatch_override():
    msg = """Index are different

Index shapes are different
\\[left\\]:  \\(2L*,\\)
\\[right\\]: \\(3L*,\\)"""

    with pytest.raises(AssertionError, match=msg):
        tm.assert_numpy_array_equal(np.array([1, 2]), np.array([3, 4, 5]), obj="Index")


def test_numpy_array_equal_unicode():
    # see gh-20503
    #
    # Test ensures that `tm.assert_numpy_array_equals` raises the right
    # exception when comparing np.arrays containing differing unicode objects.
    msg = """numpy array are different

numpy array values are different \\(33\\.33333 %\\)
\\[left\\]:  \\[á, à, ä\\]
\\[right\\]: \\[á, à, å\\]"""

    with pytest.raises(AssertionError, match=msg):
        tm.assert_numpy_array_equal(
            np.array(["á", "à", "ä"]), np.array(["á", "à", "å"])
        )


def test_numpy_array_equal_object():
    a = np.array([Timestamp("2011-01-01"), Timestamp("2011-01-01")])
    b = np.array([Timestamp("2011-01-01"), Timestamp("2011-01-02")])

    msg = """numpy array are different

numpy array values are different \\(50\\.0 %\\)
\\[left\\]:  \\[2011-01-01 00:00:00, 2011-01-01 00:00:00\\]
\\[right\\]: \\[2011-01-01 00:00:00, 2011-01-02 00:00:00\\]"""

    with pytest.raises(AssertionError, match=msg):
        tm.assert_numpy_array_equal(a, b)


@pytest.mark.parametrize("other_type", ["same", "copy"])
@pytest.mark.parametrize("check_same", ["same", "copy"])
def test_numpy_array_equal_copy_flag(other_type, check_same):
    a = np.array([1, 2, 3])
    msg = None

    if other_type == "same":
        other = a.view()
    else:
        other = a.copy()

    if check_same != other_type:
        msg = (
            r"array\(\[1, 2, 3\]\) is not array\(\[1, 2, 3\]\)"
            if check_same == "same"
            else r"array\(\[1, 2, 3\]\) is array\(\[1, 2, 3\]\)"
        )

    if msg is not None:
        with pytest.raises(AssertionError, match=msg):
            tm.assert_numpy_array_equal(a, other, check_same=check_same)
    else:
        tm.assert_numpy_array_equal(a, other, check_same=check_same)


def test_numpy_array_equal_contains_na():
    # https://github.com/pandas-dev/pandas/issues/31881
    a = np.array([True, False])
    b = np.array([True, pd.NA], dtype=object)

    msg = """numpy array are different

numpy array values are different \\(50.0 %\\)
\\[left\\]:  \\[True, False\\]
\\[right\\]: \\[True, <NA>\\]"""

    with pytest.raises(AssertionError, match=msg):
        tm.assert_numpy_array_equal(a, b)


def test_numpy_array_equal_identical_na(nulls_fixture):
    a = np.array([nulls_fixture], dtype=object)

    tm.assert_numpy_array_equal(a, a)

    # matching but not the identical object
    if hasattr(nulls_fixture, "copy"):
        other = nulls_fixture.copy()
    else:
        other = copy.copy(nulls_fixture)
    b = np.array([other], dtype=object)
    tm.assert_numpy_array_equal(a, b)


def test_numpy_array_equal_different_na():
    a = np.array([np.nan], dtype=object)
    b = np.array([pd.NA], dtype=object)

    msg = """numpy array are different

numpy array values are different \\(100.0 %\\)
\\[left\\]:  \\[nan\\]
\\[right\\]: \\[<NA>\\]"""

    with pytest.raises(AssertionError, match=msg):
        tm.assert_numpy_array_equal(a, b)
