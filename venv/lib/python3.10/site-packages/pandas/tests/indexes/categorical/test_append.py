import pytest

from pandas import (
    CategoricalIndex,
    Index,
)
import pandas._testing as tm


class TestAppend:
    @pytest.fixture
    def ci(self):
        categories = list("cab")
        return CategoricalIndex(list("aabbca"), categories=categories, ordered=False)

    def test_append(self, ci):
        # append cats with the same categories
        result = ci[:3].append(ci[3:])
        tm.assert_index_equal(result, ci, exact=True)

        foos = [ci[:1], ci[1:3], ci[3:]]
        result = foos[0].append(foos[1:])
        tm.assert_index_equal(result, ci, exact=True)

    def test_append_empty(self, ci):
        # empty
        result = ci.append([])
        tm.assert_index_equal(result, ci, exact=True)

    def test_append_mismatched_categories(self, ci):
        # appending with different categories or reordered is not ok
        msg = "all inputs must be Index"
        with pytest.raises(TypeError, match=msg):
            ci.append(ci.values.set_categories(list("abcd")))
        with pytest.raises(TypeError, match=msg):
            ci.append(ci.values.reorder_categories(list("abc")))

    def test_append_category_objects(self, ci):
        # with objects
        result = ci.append(Index(["c", "a"]))
        expected = CategoricalIndex(list("aabbcaca"), categories=ci.categories)
        tm.assert_index_equal(result, expected, exact=True)

    def test_append_non_categories(self, ci):
        # invalid objects -> cast to object via concat_compat
        result = ci.append(Index(["a", "d"]))
        expected = Index(["a", "a", "b", "b", "c", "a", "a", "d"])
        tm.assert_index_equal(result, expected, exact=True)

    def test_append_object(self, ci):
        # GH#14298 - if base object is not categorical -> coerce to object
        result = Index(["c", "a"]).append(ci)
        expected = Index(list("caaabbca"))
        tm.assert_index_equal(result, expected, exact=True)

    def test_append_to_another(self):
        # hits Index._concat
        fst = Index(["a", "b"])
        snd = CategoricalIndex(["d", "e"])
        result = fst.append(snd)
        expected = Index(["a", "b", "d", "e"])
        tm.assert_index_equal(result, expected)
