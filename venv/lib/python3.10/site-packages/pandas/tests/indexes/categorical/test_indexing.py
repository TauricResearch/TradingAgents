import numpy as np
import pytest

from pandas.errors import InvalidIndexError

import pandas as pd
from pandas import (
    CategoricalIndex,
    Index,
    IntervalIndex,
    Timestamp,
)
import pandas._testing as tm


class TestTake:
    def test_take_fill_value(self):
        # GH 12631

        # numeric category
        idx = CategoricalIndex([1, 2, 3], name="xxx")
        result = idx.take(np.array([1, 0, -1]))
        expected = CategoricalIndex([2, 1, 3], name="xxx")
        tm.assert_index_equal(result, expected)
        tm.assert_categorical_equal(result.values, expected.values)

        # fill_value
        result = idx.take(np.array([1, 0, -1]), fill_value=True)
        expected = CategoricalIndex([2, 1, np.nan], categories=[1, 2, 3], name="xxx")
        tm.assert_index_equal(result, expected)
        tm.assert_categorical_equal(result.values, expected.values)

        # allow_fill=False
        result = idx.take(np.array([1, 0, -1]), allow_fill=False, fill_value=True)
        expected = CategoricalIndex([2, 1, 3], name="xxx")
        tm.assert_index_equal(result, expected)
        tm.assert_categorical_equal(result.values, expected.values)

        # object category
        idx = CategoricalIndex(
            list("CBA"), categories=list("ABC"), ordered=True, name="xxx"
        )
        result = idx.take(np.array([1, 0, -1]))
        expected = CategoricalIndex(
            list("BCA"), categories=list("ABC"), ordered=True, name="xxx"
        )
        tm.assert_index_equal(result, expected)
        tm.assert_categorical_equal(result.values, expected.values)

        # fill_value
        result = idx.take(np.array([1, 0, -1]), fill_value=True)
        expected = CategoricalIndex(
            ["B", "C", np.nan], categories=list("ABC"), ordered=True, name="xxx"
        )
        tm.assert_index_equal(result, expected)
        tm.assert_categorical_equal(result.values, expected.values)

        # allow_fill=False
        result = idx.take(np.array([1, 0, -1]), allow_fill=False, fill_value=True)
        expected = CategoricalIndex(
            list("BCA"), categories=list("ABC"), ordered=True, name="xxx"
        )
        tm.assert_index_equal(result, expected)
        tm.assert_categorical_equal(result.values, expected.values)

        msg = (
            "When allow_fill=True and fill_value is not None, "
            "all indices must be >= -1"
        )
        with pytest.raises(ValueError, match=msg):
            idx.take(np.array([1, 0, -2]), fill_value=True)
        with pytest.raises(ValueError, match=msg):
            idx.take(np.array([1, 0, -5]), fill_value=True)

        msg = "index -5 is out of bounds for (axis 0 with )?size 3"
        with pytest.raises(IndexError, match=msg):
            idx.take(np.array([1, -5]))

    def test_take_fill_value_datetime(self):
        # datetime category
        idx = pd.DatetimeIndex(["2011-01-01", "2011-02-01", "2011-03-01"], name="xxx")
        idx = CategoricalIndex(idx)
        result = idx.take(np.array([1, 0, -1]))
        expected = pd.DatetimeIndex(
            ["2011-02-01", "2011-01-01", "2011-03-01"], name="xxx"
        )
        expected = CategoricalIndex(expected)
        tm.assert_index_equal(result, expected)

        # fill_value
        result = idx.take(np.array([1, 0, -1]), fill_value=True)
        expected = pd.DatetimeIndex(["2011-02-01", "2011-01-01", "NaT"], name="xxx")
        exp_cats = pd.DatetimeIndex(["2011-01-01", "2011-02-01", "2011-03-01"])
        expected = CategoricalIndex(expected, categories=exp_cats)
        tm.assert_index_equal(result, expected)

        # allow_fill=False
        result = idx.take(np.array([1, 0, -1]), allow_fill=False, fill_value=True)
        expected = pd.DatetimeIndex(
            ["2011-02-01", "2011-01-01", "2011-03-01"], name="xxx"
        )
        expected = CategoricalIndex(expected)
        tm.assert_index_equal(result, expected)

        msg = (
            "When allow_fill=True and fill_value is not None, "
            "all indices must be >= -1"
        )
        with pytest.raises(ValueError, match=msg):
            idx.take(np.array([1, 0, -2]), fill_value=True)
        with pytest.raises(ValueError, match=msg):
            idx.take(np.array([1, 0, -5]), fill_value=True)

        msg = "index -5 is out of bounds for (axis 0 with )?size 3"
        with pytest.raises(IndexError, match=msg):
            idx.take(np.array([1, -5]))

    def test_take_invalid_kwargs(self):
        idx = CategoricalIndex([1, 2, 3], name="foo")
        indices = [1, 0, -1]

        msg = r"take\(\) got an unexpected keyword argument 'foo'"
        with pytest.raises(TypeError, match=msg):
            idx.take(indices, foo=2)

        msg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=msg):
            idx.take(indices, out=indices)

        msg = "the 'mode' parameter is not supported"
        with pytest.raises(ValueError, match=msg):
            idx.take(indices, mode="clip")


class TestGetLoc:
    def test_get_loc(self):
        # GH 12531
        cidx1 = CategoricalIndex(list("abcde"), categories=list("edabc"))
        idx1 = Index(list("abcde"))
        assert cidx1.get_loc("a") == idx1.get_loc("a")
        assert cidx1.get_loc("e") == idx1.get_loc("e")

        for i in [cidx1, idx1]:
            with pytest.raises(KeyError, match="'NOT-EXIST'"):
                i.get_loc("NOT-EXIST")

        # non-unique
        cidx2 = CategoricalIndex(list("aacded"), categories=list("edabc"))
        idx2 = Index(list("aacded"))

        # results in bool array
        res = cidx2.get_loc("d")
        tm.assert_numpy_array_equal(res, idx2.get_loc("d"))
        tm.assert_numpy_array_equal(
            res, np.array([False, False, False, True, False, True])
        )
        # unique element results in scalar
        res = cidx2.get_loc("e")
        assert res == idx2.get_loc("e")
        assert res == 4

        for i in [cidx2, idx2]:
            with pytest.raises(KeyError, match="'NOT-EXIST'"):
                i.get_loc("NOT-EXIST")

        # non-unique, sliceable
        cidx3 = CategoricalIndex(list("aabbb"), categories=list("abc"))
        idx3 = Index(list("aabbb"))

        # results in slice
        res = cidx3.get_loc("a")
        assert res == idx3.get_loc("a")
        assert res == slice(0, 2, None)

        res = cidx3.get_loc("b")
        assert res == idx3.get_loc("b")
        assert res == slice(2, 5, None)

        for i in [cidx3, idx3]:
            with pytest.raises(KeyError, match="'c'"):
                i.get_loc("c")

    def test_get_loc_unique(self):
        cidx = CategoricalIndex(list("abc"))
        result = cidx.get_loc("b")
        assert result == 1

    def test_get_loc_monotonic_nonunique(self):
        cidx = CategoricalIndex(list("abbc"))
        result = cidx.get_loc("b")
        expected = slice(1, 3, None)
        assert result == expected

    def test_get_loc_nonmonotonic_nonunique(self):
        cidx = CategoricalIndex(list("abcb"))
        result = cidx.get_loc("b")
        expected = np.array([False, True, False, True], dtype=bool)
        tm.assert_numpy_array_equal(result, expected)

    def test_get_loc_nan(self):
        # GH#41933
        ci = CategoricalIndex(["A", "B", np.nan])
        res = ci.get_loc(np.nan)

        assert res == 2


class TestGetIndexer:
    def test_get_indexer_base(self):
        # Determined by cat ordering.
        idx = CategoricalIndex(list("cab"), categories=list("cab"))
        expected = np.arange(len(idx), dtype=np.intp)

        actual = idx.get_indexer(idx)
        tm.assert_numpy_array_equal(expected, actual)

        with pytest.raises(ValueError, match="Invalid fill method"):
            idx.get_indexer(idx, method="invalid")

    def test_get_indexer_requires_unique(self):
        ci = CategoricalIndex(list("aabbca"), categories=list("cab"), ordered=False)
        oidx = Index(np.array(ci))

        msg = "Reindexing only valid with uniquely valued Index objects"

        for n in [1, 2, 5, len(ci)]:
            finder = oidx[np.random.default_rng(2).integers(0, len(ci), size=n)]

            with pytest.raises(InvalidIndexError, match=msg):
                ci.get_indexer(finder)

        # see gh-17323
        #
        # Even when indexer is equal to the
        # members in the index, we should
        # respect duplicates instead of taking
        # the fast-track path.
        for finder in [list("aabbca"), list("aababca")]:
            with pytest.raises(InvalidIndexError, match=msg):
                ci.get_indexer(finder)

    def test_get_indexer_non_unique(self):
        idx1 = CategoricalIndex(list("aabcde"), categories=list("edabc"))
        idx2 = CategoricalIndex(list("abf"))

        for indexer in [idx2, list("abf"), Index(list("abf"))]:
            msg = "Reindexing only valid with uniquely valued Index objects"
            with pytest.raises(InvalidIndexError, match=msg):
                idx1.get_indexer(indexer)

            r1, _ = idx1.get_indexer_non_unique(indexer)
            expected = np.array([0, 1, 2, -1], dtype=np.intp)
            tm.assert_almost_equal(r1, expected)

    def test_get_indexer_method(self):
        idx1 = CategoricalIndex(list("aabcde"), categories=list("edabc"))
        idx2 = CategoricalIndex(list("abf"))

        msg = "method pad not yet implemented for CategoricalIndex"
        with pytest.raises(NotImplementedError, match=msg):
            idx2.get_indexer(idx1, method="pad")
        msg = "method backfill not yet implemented for CategoricalIndex"
        with pytest.raises(NotImplementedError, match=msg):
            idx2.get_indexer(idx1, method="backfill")

        msg = "method nearest not yet implemented for CategoricalIndex"
        with pytest.raises(NotImplementedError, match=msg):
            idx2.get_indexer(idx1, method="nearest")

    def test_get_indexer_array(self):
        arr = np.array(
            [Timestamp("1999-12-31 00:00:00"), Timestamp("2000-12-31 00:00:00")],
            dtype=object,
        )
        cats = [Timestamp("1999-12-31 00:00:00"), Timestamp("2000-12-31 00:00:00")]
        ci = CategoricalIndex(cats, categories=cats, ordered=False, dtype="category")
        result = ci.get_indexer(arr)
        expected = np.array([0, 1], dtype="intp")
        tm.assert_numpy_array_equal(result, expected)

    def test_get_indexer_same_categories_same_order(self):
        ci = CategoricalIndex(["a", "b"], categories=["a", "b"])

        result = ci.get_indexer(CategoricalIndex(["b", "b"], categories=["a", "b"]))
        expected = np.array([1, 1], dtype="intp")
        tm.assert_numpy_array_equal(result, expected)

    def test_get_indexer_same_categories_different_order(self):
        # https://github.com/pandas-dev/pandas/issues/19551
        ci = CategoricalIndex(["a", "b"], categories=["a", "b"])

        result = ci.get_indexer(CategoricalIndex(["b", "b"], categories=["b", "a"]))
        expected = np.array([1, 1], dtype="intp")
        tm.assert_numpy_array_equal(result, expected)

    def test_get_indexer_nans_in_index_and_target(self):
        # GH 45361
        ci = CategoricalIndex([1, 2, np.nan, 3])
        other1 = [2, 3, 4, np.nan]
        res1 = ci.get_indexer(other1)
        expected1 = np.array([1, 3, -1, 2], dtype=np.intp)
        tm.assert_numpy_array_equal(res1, expected1)
        other2 = [1, 4, 2, 3]
        res2 = ci.get_indexer(other2)
        expected2 = np.array([0, -1, 1, 3], dtype=np.intp)
        tm.assert_numpy_array_equal(res2, expected2)


class TestWhere:
    def test_where(self, listlike_box):
        klass = listlike_box

        i = CategoricalIndex(list("aabbca"), categories=list("cab"), ordered=False)
        cond = [True] * len(i)
        expected = i
        result = i.where(klass(cond))
        tm.assert_index_equal(result, expected)

        cond = [False] + [True] * (len(i) - 1)
        expected = CategoricalIndex([np.nan] + i[1:].tolist(), categories=i.categories)
        result = i.where(klass(cond))
        tm.assert_index_equal(result, expected)

    def test_where_non_categories(self):
        ci = CategoricalIndex(["a", "b", "c", "d"])
        mask = np.array([True, False, True, False])

        result = ci.where(mask, 2)
        expected = Index(["a", 2, "c", 2], dtype=object)
        tm.assert_index_equal(result, expected)

        msg = "Cannot setitem on a Categorical with a new category"
        with pytest.raises(TypeError, match=msg):
            # Test the Categorical method directly
            ci._data._where(mask, 2)


class TestContains:
    def test_contains(self):
        ci = CategoricalIndex(list("aabbca"), categories=list("cabdef"), ordered=False)

        assert "a" in ci
        assert "z" not in ci
        assert "e" not in ci
        assert np.nan not in ci

        # assert codes NOT in index
        assert 0 not in ci
        assert 1 not in ci

    def test_contains_nan(self):
        ci = CategoricalIndex(list("aabbca") + [np.nan], categories=list("cabdef"))
        assert np.nan in ci

    @pytest.mark.parametrize("unwrap", [True, False])
    def test_contains_na_dtype(self, unwrap):
        dti = pd.date_range("2016-01-01", periods=100).insert(0, pd.NaT)
        pi = dti.to_period("D")
        tdi = dti - dti[-1]
        ci = CategoricalIndex(dti)

        obj = ci
        if unwrap:
            obj = ci._data

        assert np.nan in obj
        assert None in obj
        assert pd.NaT in obj
        assert np.datetime64("NaT") in obj
        assert np.timedelta64("NaT") not in obj

        obj2 = CategoricalIndex(tdi)
        if unwrap:
            obj2 = obj2._data

        assert np.nan in obj2
        assert None in obj2
        assert pd.NaT in obj2
        assert np.datetime64("NaT") not in obj2
        assert np.timedelta64("NaT") in obj2

        obj3 = CategoricalIndex(pi)
        if unwrap:
            obj3 = obj3._data

        assert np.nan in obj3
        assert None in obj3
        assert pd.NaT in obj3
        assert np.datetime64("NaT") not in obj3
        assert np.timedelta64("NaT") not in obj3

    @pytest.mark.parametrize(
        "item, expected",
        [
            (pd.Interval(0, 1), True),
            (1.5, True),
            (pd.Interval(0.5, 1.5), False),
            ("a", False),
            (Timestamp(1), False),
            (pd.Timedelta(1), False),
        ],
        ids=str,
    )
    def test_contains_interval(self, item, expected):
        # GH 23705
        ci = CategoricalIndex(IntervalIndex.from_breaks(range(3)))
        result = item in ci
        assert result is expected

    def test_contains_list(self):
        # GH#21729
        idx = CategoricalIndex([1, 2, 3])

        assert "a" not in idx

        with pytest.raises(TypeError, match="unhashable type"):
            ["a"] in idx

        with pytest.raises(TypeError, match="unhashable type"):
            ["a", "b"] in idx
