import pytest

from pandas import Categorical
import pandas._testing as tm


@pytest.mark.parametrize(
    "c",
    [Categorical([1, 2, 3, 4]), Categorical([1, 2, 3, 4], categories=[1, 2, 3, 4, 5])],
)
def test_categorical_equal(c):
    tm.assert_categorical_equal(c, c)


@pytest.mark.parametrize("check_category_order", [True, False])
def test_categorical_equal_order_mismatch(check_category_order):
    c1 = Categorical([1, 2, 3, 4], categories=[1, 2, 3, 4])
    c2 = Categorical([1, 2, 3, 4], categories=[4, 3, 2, 1])
    kwargs = {"check_category_order": check_category_order}

    if check_category_order:
        msg = """Categorical\\.categories are different

Categorical\\.categories values are different \\(100\\.0 %\\)
\\[left\\]:  Index\\(\\[1, 2, 3, 4\\], dtype='int64'\\)
\\[right\\]: Index\\(\\[4, 3, 2, 1\\], dtype='int64'\\)"""
        with pytest.raises(AssertionError, match=msg):
            tm.assert_categorical_equal(c1, c2, **kwargs)
    else:
        tm.assert_categorical_equal(c1, c2, **kwargs)


def test_categorical_equal_categories_mismatch():
    msg = """Categorical\\.categories are different

Categorical\\.categories values are different \\(25\\.0 %\\)
\\[left\\]:  Index\\(\\[1, 2, 3, 4\\], dtype='int64'\\)
\\[right\\]: Index\\(\\[1, 2, 3, 5\\], dtype='int64'\\)"""

    c1 = Categorical([1, 2, 3, 4])
    c2 = Categorical([1, 2, 3, 5])

    with pytest.raises(AssertionError, match=msg):
        tm.assert_categorical_equal(c1, c2)


def test_categorical_equal_codes_mismatch():
    categories = [1, 2, 3, 4]
    msg = """Categorical\\.codes are different

Categorical\\.codes values are different \\(50\\.0 %\\)
\\[left\\]:  \\[0, 1, 3, 2\\]
\\[right\\]: \\[0, 1, 2, 3\\]"""

    c1 = Categorical([1, 2, 4, 3], categories=categories)
    c2 = Categorical([1, 2, 3, 4], categories=categories)

    with pytest.raises(AssertionError, match=msg):
        tm.assert_categorical_equal(c1, c2)


def test_categorical_equal_ordered_mismatch():
    data = [1, 2, 3, 4]
    msg = """Categorical are different

Attribute "ordered" are different
\\[left\\]:  False
\\[right\\]: True"""

    c1 = Categorical(data, ordered=False)
    c2 = Categorical(data, ordered=True)

    with pytest.raises(AssertionError, match=msg):
        tm.assert_categorical_equal(c1, c2)


@pytest.mark.parametrize("obj", ["index", "foo", "pandas"])
def test_categorical_equal_object_override(obj):
    data = [1, 2, 3, 4]
    msg = f"""{obj} are different

Attribute "ordered" are different
\\[left\\]:  False
\\[right\\]: True"""

    c1 = Categorical(data, ordered=False)
    c2 = Categorical(data, ordered=True)

    with pytest.raises(AssertionError, match=msg):
        tm.assert_categorical_equal(c1, c2, obj=obj)
