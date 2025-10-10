import numpy as np
import pytest

from pandas import (
    NA,
    Categorical,
    CategoricalIndex,
    Index,
    MultiIndex,
    NaT,
    RangeIndex,
)
import pandas._testing as tm


def test_index_equal_levels_mismatch():
    msg = """Index are different

Index levels are different
\\[left\\]:  1, Index\\(\\[1, 2, 3\\], dtype='int64'\\)
\\[right\\]: 2, MultiIndex\\(\\[\\('A', 1\\),
            \\('A', 2\\),
            \\('B', 3\\),
            \\('B', 4\\)\\],
           \\)"""

    idx1 = Index([1, 2, 3])
    idx2 = MultiIndex.from_tuples([("A", 1), ("A", 2), ("B", 3), ("B", 4)])

    with pytest.raises(AssertionError, match=msg):
        tm.assert_index_equal(idx1, idx2, exact=False)


def test_index_equal_values_mismatch(check_exact):
    msg = """MultiIndex level \\[1\\] are different

MultiIndex level \\[1\\] values are different \\(25\\.0 %\\)
\\[left\\]:  Index\\(\\[2, 2, 3, 4\\], dtype='int64'\\)
\\[right\\]: Index\\(\\[1, 2, 3, 4\\], dtype='int64'\\)"""

    idx1 = MultiIndex.from_tuples([("A", 2), ("A", 2), ("B", 3), ("B", 4)])
    idx2 = MultiIndex.from_tuples([("A", 1), ("A", 2), ("B", 3), ("B", 4)])

    with pytest.raises(AssertionError, match=msg):
        tm.assert_index_equal(idx1, idx2, check_exact=check_exact)


def test_index_equal_length_mismatch(check_exact):
    msg = """Index are different

Index length are different
\\[left\\]:  3, Index\\(\\[1, 2, 3\\], dtype='int64'\\)
\\[right\\]: 4, Index\\(\\[1, 2, 3, 4\\], dtype='int64'\\)"""

    idx1 = Index([1, 2, 3])
    idx2 = Index([1, 2, 3, 4])

    with pytest.raises(AssertionError, match=msg):
        tm.assert_index_equal(idx1, idx2, check_exact=check_exact)


@pytest.mark.parametrize("exact", [False, "equiv"])
def test_index_equal_class(exact):
    idx1 = Index([0, 1, 2])
    idx2 = RangeIndex(3)

    tm.assert_index_equal(idx1, idx2, exact=exact)


def test_int_float_index_equal_class_mismatch(check_exact):
    msg = """Index are different

Attribute "inferred_type" are different
\\[left\\]:  integer
\\[right\\]: floating"""

    idx1 = Index([1, 2, 3])
    idx2 = Index([1, 2, 3], dtype=np.float64)

    with pytest.raises(AssertionError, match=msg):
        tm.assert_index_equal(idx1, idx2, exact=True, check_exact=check_exact)


def test_range_index_equal_class_mismatch(check_exact):
    msg = """Index are different

Index classes are different
\\[left\\]:  Index\\(\\[1, 2, 3\\], dtype='int64'\\)
\\[right\\]: """

    idx1 = Index([1, 2, 3])
    idx2 = RangeIndex(range(3))

    with pytest.raises(AssertionError, match=msg):
        tm.assert_index_equal(idx1, idx2, exact=True, check_exact=check_exact)


def test_index_equal_values_close(check_exact):
    idx1 = Index([1, 2, 3.0])
    idx2 = Index([1, 2, 3.0000000001])

    if check_exact:
        msg = """Index are different

Index values are different \\(33\\.33333 %\\)
\\[left\\]:  Index\\(\\[1.0, 2.0, 3.0], dtype='float64'\\)
\\[right\\]: Index\\(\\[1.0, 2.0, 3.0000000001\\], dtype='float64'\\)"""

        with pytest.raises(AssertionError, match=msg):
            tm.assert_index_equal(idx1, idx2, check_exact=check_exact)
    else:
        tm.assert_index_equal(idx1, idx2, check_exact=check_exact)


def test_index_equal_values_less_close(check_exact, rtol):
    idx1 = Index([1, 2, 3.0])
    idx2 = Index([1, 2, 3.0001])
    kwargs = {"check_exact": check_exact, "rtol": rtol}

    if check_exact or rtol < 0.5e-3:
        msg = """Index are different

Index values are different \\(33\\.33333 %\\)
\\[left\\]:  Index\\(\\[1.0, 2.0, 3.0], dtype='float64'\\)
\\[right\\]: Index\\(\\[1.0, 2.0, 3.0001\\], dtype='float64'\\)"""

        with pytest.raises(AssertionError, match=msg):
            tm.assert_index_equal(idx1, idx2, **kwargs)
    else:
        tm.assert_index_equal(idx1, idx2, **kwargs)


def test_index_equal_values_too_far(check_exact, rtol):
    idx1 = Index([1, 2, 3])
    idx2 = Index([1, 2, 4])
    kwargs = {"check_exact": check_exact, "rtol": rtol}

    msg = """Index are different

Index values are different \\(33\\.33333 %\\)
\\[left\\]:  Index\\(\\[1, 2, 3\\], dtype='int64'\\)
\\[right\\]: Index\\(\\[1, 2, 4\\], dtype='int64'\\)"""

    with pytest.raises(AssertionError, match=msg):
        tm.assert_index_equal(idx1, idx2, **kwargs)


@pytest.mark.parametrize("check_order", [True, False])
def test_index_equal_value_order_mismatch(check_exact, rtol, check_order):
    idx1 = Index([1, 2, 3])
    idx2 = Index([3, 2, 1])

    msg = """Index are different

Index values are different \\(66\\.66667 %\\)
\\[left\\]:  Index\\(\\[1, 2, 3\\], dtype='int64'\\)
\\[right\\]: Index\\(\\[3, 2, 1\\], dtype='int64'\\)"""

    if check_order:
        with pytest.raises(AssertionError, match=msg):
            tm.assert_index_equal(
                idx1, idx2, check_exact=check_exact, rtol=rtol, check_order=True
            )
    else:
        tm.assert_index_equal(
            idx1, idx2, check_exact=check_exact, rtol=rtol, check_order=False
        )


def test_index_equal_level_values_mismatch(check_exact, rtol):
    idx1 = MultiIndex.from_tuples([("A", 2), ("A", 2), ("B", 3), ("B", 4)])
    idx2 = MultiIndex.from_tuples([("A", 1), ("A", 2), ("B", 3), ("B", 4)])
    kwargs = {"check_exact": check_exact, "rtol": rtol}

    msg = """MultiIndex level \\[1\\] are different

MultiIndex level \\[1\\] values are different \\(25\\.0 %\\)
\\[left\\]:  Index\\(\\[2, 2, 3, 4\\], dtype='int64'\\)
\\[right\\]: Index\\(\\[1, 2, 3, 4\\], dtype='int64'\\)"""

    with pytest.raises(AssertionError, match=msg):
        tm.assert_index_equal(idx1, idx2, **kwargs)


@pytest.mark.parametrize(
    "name1,name2",
    [(None, "x"), ("x", "x"), (np.nan, np.nan), (NaT, NaT), (np.nan, NaT)],
)
def test_index_equal_names(name1, name2):
    idx1 = Index([1, 2, 3], name=name1)
    idx2 = Index([1, 2, 3], name=name2)

    if name1 == name2 or name1 is name2:
        tm.assert_index_equal(idx1, idx2)
    else:
        name1 = "'x'" if name1 == "x" else name1
        name2 = "'x'" if name2 == "x" else name2
        msg = f"""Index are different

Attribute "names" are different
\\[left\\]:  \\[{name1}\\]
\\[right\\]: \\[{name2}\\]"""

        with pytest.raises(AssertionError, match=msg):
            tm.assert_index_equal(idx1, idx2)


def test_index_equal_category_mismatch(check_categorical, using_infer_string):
    if using_infer_string:
        dtype = "str"
    else:
        dtype = "object"
    msg = f"""Index are different

Attribute "dtype" are different
\\[left\\]:  CategoricalDtype\\(categories=\\['a', 'b'\\], ordered=False, \
categories_dtype={dtype}\\)
\\[right\\]: CategoricalDtype\\(categories=\\['a', 'b', 'c'\\], \
ordered=False, categories_dtype={dtype}\\)"""

    idx1 = Index(Categorical(["a", "b"]))
    idx2 = Index(Categorical(["a", "b"], categories=["a", "b", "c"]))

    if check_categorical:
        with pytest.raises(AssertionError, match=msg):
            tm.assert_index_equal(idx1, idx2, check_categorical=check_categorical)
    else:
        tm.assert_index_equal(idx1, idx2, check_categorical=check_categorical)


@pytest.mark.parametrize("exact", [False, True])
def test_index_equal_range_categories(check_categorical, exact):
    # GH41263
    msg = """\
Index are different

Index classes are different
\\[left\\]:  RangeIndex\\(start=0, stop=10, step=1\\)
\\[right\\]: Index\\(\\[0, 1, 2, 3, 4, 5, 6, 7, 8, 9\\], dtype='int64'\\)"""

    rcat = CategoricalIndex(RangeIndex(10))
    icat = CategoricalIndex(list(range(10)))

    if check_categorical and exact:
        with pytest.raises(AssertionError, match=msg):
            tm.assert_index_equal(rcat, icat, check_categorical=True, exact=True)
    else:
        tm.assert_index_equal(
            rcat, icat, check_categorical=check_categorical, exact=exact
        )


def test_assert_index_equal_different_inferred_types():
    # GH#31884
    msg = """\
Index are different

Attribute "inferred_type" are different
\\[left\\]:  mixed
\\[right\\]: datetime"""

    idx1 = Index([NA, np.datetime64("nat")])
    idx2 = Index([NA, NaT])
    with pytest.raises(AssertionError, match=msg):
        tm.assert_index_equal(idx1, idx2)


def test_assert_index_equal_different_names_check_order_false():
    # GH#47328
    idx1 = Index([1, 3], name="a")
    idx2 = Index([3, 1], name="b")
    with pytest.raises(AssertionError, match='"names" are different'):
        tm.assert_index_equal(idx1, idx2, check_order=False, check_names=True)


def test_assert_index_equal_mixed_dtype():
    # GH#39168
    idx = Index(["foo", "bar", 42])
    tm.assert_index_equal(idx, idx, check_order=False)


def test_assert_index_equal_ea_dtype_order_false(any_numeric_ea_dtype):
    # GH#47207
    idx1 = Index([1, 3], dtype=any_numeric_ea_dtype)
    idx2 = Index([3, 1], dtype=any_numeric_ea_dtype)
    tm.assert_index_equal(idx1, idx2, check_order=False)


def test_assert_index_equal_object_ints_order_false():
    # GH#47207
    idx1 = Index([1, 3], dtype="object")
    idx2 = Index([3, 1], dtype="object")
    tm.assert_index_equal(idx1, idx2, check_order=False)


@pytest.mark.parametrize("check_categorical", [True, False])
@pytest.mark.parametrize("check_names", [True, False])
def test_assert_ea_index_equal_non_matching_na(check_names, check_categorical):
    # GH#48608
    idx1 = Index([1, 2], dtype="Int64")
    idx2 = Index([1, NA], dtype="Int64")
    with pytest.raises(AssertionError, match="50.0 %"):
        tm.assert_index_equal(
            idx1, idx2, check_names=check_names, check_categorical=check_categorical
        )


@pytest.mark.parametrize("check_categorical", [True, False])
def test_assert_multi_index_dtype_check_categorical(check_categorical):
    # GH#52126
    idx1 = MultiIndex.from_arrays([Categorical(np.array([1, 2], dtype=np.uint64))])
    idx2 = MultiIndex.from_arrays([Categorical(np.array([1, 2], dtype=np.int64))])
    if check_categorical:
        with pytest.raises(
            AssertionError, match=r"^MultiIndex level \[0\] are different"
        ):
            tm.assert_index_equal(idx1, idx2, check_categorical=check_categorical)
    else:
        tm.assert_index_equal(idx1, idx2, check_categorical=check_categorical)
