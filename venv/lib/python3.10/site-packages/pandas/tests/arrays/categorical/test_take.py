import numpy as np
import pytest

from pandas import Categorical
import pandas._testing as tm


@pytest.fixture(params=[True, False])
def allow_fill(request):
    """Boolean 'allow_fill' parameter for Categorical.take"""
    return request.param


class TestTake:
    # https://github.com/pandas-dev/pandas/issues/20664

    def test_take_default_allow_fill(self):
        cat = Categorical(["a", "b"])
        with tm.assert_produces_warning(None):
            result = cat.take([0, -1])

        assert result.equals(cat)

    def test_take_positive_no_warning(self):
        cat = Categorical(["a", "b"])
        with tm.assert_produces_warning(None):
            cat.take([0, 0])

    def test_take_bounds(self, allow_fill):
        # https://github.com/pandas-dev/pandas/issues/20664
        cat = Categorical(["a", "b", "a"])
        if allow_fill:
            msg = "indices are out-of-bounds"
        else:
            msg = "index 4 is out of bounds for( axis 0 with)? size 3"
        with pytest.raises(IndexError, match=msg):
            cat.take([4, 5], allow_fill=allow_fill)

    def test_take_empty(self, allow_fill):
        # https://github.com/pandas-dev/pandas/issues/20664
        cat = Categorical([], categories=["a", "b"])
        if allow_fill:
            msg = "indices are out-of-bounds"
        else:
            msg = "cannot do a non-empty take from an empty axes"
        with pytest.raises(IndexError, match=msg):
            cat.take([0], allow_fill=allow_fill)

    def test_positional_take(self, ordered):
        cat = Categorical(["a", "a", "b", "b"], categories=["b", "a"], ordered=ordered)
        result = cat.take([0, 1, 2], allow_fill=False)
        expected = Categorical(
            ["a", "a", "b"], categories=cat.categories, ordered=ordered
        )
        tm.assert_categorical_equal(result, expected)

    def test_positional_take_unobserved(self, ordered):
        cat = Categorical(["a", "b"], categories=["a", "b", "c"], ordered=ordered)
        result = cat.take([1, 0], allow_fill=False)
        expected = Categorical(["b", "a"], categories=cat.categories, ordered=ordered)
        tm.assert_categorical_equal(result, expected)

    def test_take_allow_fill(self):
        # https://github.com/pandas-dev/pandas/issues/23296
        cat = Categorical(["a", "a", "b"])
        result = cat.take([0, -1, -1], allow_fill=True)
        expected = Categorical(["a", np.nan, np.nan], categories=["a", "b"])
        tm.assert_categorical_equal(result, expected)

    def test_take_fill_with_negative_one(self):
        # -1 was a category
        cat = Categorical([-1, 0, 1])
        result = cat.take([0, -1, 1], allow_fill=True, fill_value=-1)
        expected = Categorical([-1, -1, 0], categories=[-1, 0, 1])
        tm.assert_categorical_equal(result, expected)

    def test_take_fill_value(self):
        # https://github.com/pandas-dev/pandas/issues/23296
        cat = Categorical(["a", "b", "c"])
        result = cat.take([0, 1, -1], fill_value="a", allow_fill=True)
        expected = Categorical(["a", "b", "a"], categories=["a", "b", "c"])
        tm.assert_categorical_equal(result, expected)

    def test_take_fill_value_new_raises(self):
        # https://github.com/pandas-dev/pandas/issues/23296
        cat = Categorical(["a", "b", "c"])
        xpr = r"Cannot setitem on a Categorical with a new category \(d\)"
        with pytest.raises(TypeError, match=xpr):
            cat.take([0, 1, -1], fill_value="d", allow_fill=True)
