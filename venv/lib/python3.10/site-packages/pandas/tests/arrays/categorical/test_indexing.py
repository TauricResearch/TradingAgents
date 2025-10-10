import math

import numpy as np
import pytest

from pandas import (
    NA,
    Categorical,
    CategoricalIndex,
    Index,
    Interval,
    IntervalIndex,
    NaT,
    PeriodIndex,
    Series,
    Timedelta,
    Timestamp,
)
import pandas._testing as tm
import pandas.core.common as com


class TestCategoricalIndexingWithFactor:
    def test_getitem(self):
        factor = Categorical(["a", "b", "b", "a", "a", "c", "c", "c"], ordered=True)
        assert factor[0] == "a"
        assert factor[-1] == "c"

        subf = factor[[0, 1, 2]]
        tm.assert_numpy_array_equal(subf._codes, np.array([0, 1, 1], dtype=np.int8))

        subf = factor[np.asarray(factor) == "c"]
        tm.assert_numpy_array_equal(subf._codes, np.array([2, 2, 2], dtype=np.int8))

    def test_setitem(self):
        factor = Categorical(["a", "b", "b", "a", "a", "c", "c", "c"], ordered=True)
        # int/positional
        c = factor.copy()
        c[0] = "b"
        assert c[0] == "b"
        c[-1] = "a"
        assert c[-1] == "a"

        # boolean
        c = factor.copy()
        indexer = np.zeros(len(c), dtype="bool")
        indexer[0] = True
        indexer[-1] = True
        c[indexer] = "c"
        expected = Categorical(["c", "b", "b", "a", "a", "c", "c", "c"], ordered=True)

        tm.assert_categorical_equal(c, expected)

    @pytest.mark.parametrize(
        "other",
        [Categorical(["b", "a"]), Categorical(["b", "a"], categories=["b", "a"])],
    )
    def test_setitem_same_but_unordered(self, other):
        # GH-24142
        target = Categorical(["a", "b"], categories=["a", "b"])
        mask = np.array([True, False])
        target[mask] = other[mask]
        expected = Categorical(["b", "b"], categories=["a", "b"])
        tm.assert_categorical_equal(target, expected)

    @pytest.mark.parametrize(
        "other",
        [
            Categorical(["b", "a"], categories=["b", "a", "c"]),
            Categorical(["b", "a"], categories=["a", "b", "c"]),
            Categorical(["a", "a"], categories=["a"]),
            Categorical(["b", "b"], categories=["b"]),
        ],
    )
    def test_setitem_different_unordered_raises(self, other):
        # GH-24142
        target = Categorical(["a", "b"], categories=["a", "b"])
        mask = np.array([True, False])
        msg = "Cannot set a Categorical with another, without identical categories"
        with pytest.raises(TypeError, match=msg):
            target[mask] = other[mask]

    @pytest.mark.parametrize(
        "other",
        [
            Categorical(["b", "a"]),
            Categorical(["b", "a"], categories=["b", "a"], ordered=True),
            Categorical(["b", "a"], categories=["a", "b", "c"], ordered=True),
        ],
    )
    def test_setitem_same_ordered_raises(self, other):
        # Gh-24142
        target = Categorical(["a", "b"], categories=["a", "b"], ordered=True)
        mask = np.array([True, False])
        msg = "Cannot set a Categorical with another, without identical categories"
        with pytest.raises(TypeError, match=msg):
            target[mask] = other[mask]

    def test_setitem_tuple(self):
        # GH#20439
        cat = Categorical([(0, 1), (0, 2), (0, 1)])

        # This should not raise
        cat[1] = cat[0]
        assert cat[1] == (0, 1)

    def test_setitem_listlike(self):
        # GH#9469
        # properly coerce the input indexers

        cat = Categorical(
            np.random.default_rng(2).integers(0, 5, size=150000).astype(np.int8)
        ).add_categories([-1000])
        indexer = np.array([100000]).astype(np.int64)
        cat[indexer] = -1000

        # we are asserting the code result here
        # which maps to the -1000 category
        result = cat.codes[np.array([100000]).astype(np.int64)]
        tm.assert_numpy_array_equal(result, np.array([5], dtype="int8"))


class TestCategoricalIndexing:
    def test_getitem_slice(self):
        cat = Categorical(["a", "b", "c", "d", "a", "b", "c"])
        sliced = cat[3]
        assert sliced == "d"

        sliced = cat[3:5]
        expected = Categorical(["d", "a"], categories=["a", "b", "c", "d"])
        tm.assert_categorical_equal(sliced, expected)

    def test_getitem_listlike(self):
        # GH 9469
        # properly coerce the input indexers

        c = Categorical(
            np.random.default_rng(2).integers(0, 5, size=150000).astype(np.int8)
        )
        result = c.codes[np.array([100000]).astype(np.int64)]
        expected = c[np.array([100000]).astype(np.int64)].codes
        tm.assert_numpy_array_equal(result, expected)

    def test_periodindex(self):
        idx1 = PeriodIndex(
            ["2014-01", "2014-01", "2014-02", "2014-02", "2014-03", "2014-03"],
            freq="M",
        )

        cat1 = Categorical(idx1)
        str(cat1)
        exp_arr = np.array([0, 0, 1, 1, 2, 2], dtype=np.int8)
        exp_idx = PeriodIndex(["2014-01", "2014-02", "2014-03"], freq="M")
        tm.assert_numpy_array_equal(cat1._codes, exp_arr)
        tm.assert_index_equal(cat1.categories, exp_idx)

        idx2 = PeriodIndex(
            ["2014-03", "2014-03", "2014-02", "2014-01", "2014-03", "2014-01"],
            freq="M",
        )
        cat2 = Categorical(idx2, ordered=True)
        str(cat2)
        exp_arr = np.array([2, 2, 1, 0, 2, 0], dtype=np.int8)
        exp_idx2 = PeriodIndex(["2014-01", "2014-02", "2014-03"], freq="M")
        tm.assert_numpy_array_equal(cat2._codes, exp_arr)
        tm.assert_index_equal(cat2.categories, exp_idx2)

        idx3 = PeriodIndex(
            [
                "2013-12",
                "2013-11",
                "2013-10",
                "2013-09",
                "2013-08",
                "2013-07",
                "2013-05",
            ],
            freq="M",
        )
        cat3 = Categorical(idx3, ordered=True)
        exp_arr = np.array([6, 5, 4, 3, 2, 1, 0], dtype=np.int8)
        exp_idx = PeriodIndex(
            [
                "2013-05",
                "2013-07",
                "2013-08",
                "2013-09",
                "2013-10",
                "2013-11",
                "2013-12",
            ],
            freq="M",
        )
        tm.assert_numpy_array_equal(cat3._codes, exp_arr)
        tm.assert_index_equal(cat3.categories, exp_idx)

    @pytest.mark.parametrize(
        "null_val",
        [None, np.nan, NaT, NA, math.nan, "NaT", "nat", "NAT", "nan", "NaN", "NAN"],
    )
    def test_periodindex_on_null_types(self, null_val):
        # GH 46673
        result = PeriodIndex(["2022-04-06", "2022-04-07", null_val], freq="D")
        expected = PeriodIndex(["2022-04-06", "2022-04-07", "NaT"], dtype="period[D]")
        assert result[2] is NaT
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("new_categories", [[1, 2, 3, 4], [1, 2]])
    def test_categories_assignments_wrong_length_raises(self, new_categories):
        cat = Categorical(["a", "b", "c", "a"])
        msg = (
            "new categories need to have the same number of items "
            "as the old categories!"
        )
        with pytest.raises(ValueError, match=msg):
            cat.rename_categories(new_categories)

    # Combinations of sorted/unique:
    @pytest.mark.parametrize(
        "idx_values", [[1, 2, 3, 4], [1, 3, 2, 4], [1, 3, 3, 4], [1, 2, 2, 4]]
    )
    # Combinations of missing/unique
    @pytest.mark.parametrize("key_values", [[1, 2], [1, 5], [1, 1], [5, 5]])
    @pytest.mark.parametrize("key_class", [Categorical, CategoricalIndex])
    @pytest.mark.parametrize("dtype", [None, "category", "key"])
    def test_get_indexer_non_unique(self, idx_values, key_values, key_class, dtype):
        # GH 21448
        key = key_class(key_values, categories=range(1, 5))

        if dtype == "key":
            dtype = key.dtype

        # Test for flat index and CategoricalIndex with same/different cats:
        idx = Index(idx_values, dtype=dtype)
        expected, exp_miss = idx.get_indexer_non_unique(key_values)
        result, res_miss = idx.get_indexer_non_unique(key)

        tm.assert_numpy_array_equal(expected, result)
        tm.assert_numpy_array_equal(exp_miss, res_miss)

        exp_unique = idx.unique().get_indexer(key_values)
        res_unique = idx.unique().get_indexer(key)
        tm.assert_numpy_array_equal(res_unique, exp_unique)

    def test_where_unobserved_nan(self):
        ser = Series(Categorical(["a", "b"]))
        result = ser.where([True, False])
        expected = Series(Categorical(["a", None], categories=["a", "b"]))
        tm.assert_series_equal(result, expected)

        # all NA
        ser = Series(Categorical(["a", "b"]))
        result = ser.where([False, False])
        expected = Series(Categorical([None, None], categories=["a", "b"]))
        tm.assert_series_equal(result, expected)

    def test_where_unobserved_categories(self):
        ser = Series(Categorical(["a", "b", "c"], categories=["d", "c", "b", "a"]))
        result = ser.where([True, True, False], other="b")
        expected = Series(Categorical(["a", "b", "b"], categories=ser.cat.categories))
        tm.assert_series_equal(result, expected)

    def test_where_other_categorical(self):
        ser = Series(Categorical(["a", "b", "c"], categories=["d", "c", "b", "a"]))
        other = Categorical(["b", "c", "a"], categories=["a", "c", "b", "d"])
        result = ser.where([True, False, True], other)
        expected = Series(Categorical(["a", "c", "c"], dtype=ser.dtype))
        tm.assert_series_equal(result, expected)

    def test_where_new_category_raises(self):
        ser = Series(Categorical(["a", "b", "c"]))
        msg = "Cannot setitem on a Categorical with a new category"
        with pytest.raises(TypeError, match=msg):
            ser.where([True, False, True], "d")

    def test_where_ordered_differs_rasies(self):
        ser = Series(
            Categorical(["a", "b", "c"], categories=["d", "c", "b", "a"], ordered=True)
        )
        other = Categorical(
            ["b", "c", "a"], categories=["a", "c", "b", "d"], ordered=True
        )
        with pytest.raises(TypeError, match="without identical categories"):
            ser.where([True, False, True], other)


class TestContains:
    def test_contains(self):
        # GH#21508
        cat = Categorical(list("aabbca"), categories=list("cab"))

        assert "b" in cat
        assert "z" not in cat
        assert np.nan not in cat
        with pytest.raises(TypeError, match="unhashable type: 'list'"):
            assert [1] in cat

        # assert codes NOT in index
        assert 0 not in cat
        assert 1 not in cat

        cat = Categorical(list("aabbca") + [np.nan], categories=list("cab"))
        assert np.nan in cat

    @pytest.mark.parametrize(
        "item, expected",
        [
            (Interval(0, 1), True),
            (1.5, True),
            (Interval(0.5, 1.5), False),
            ("a", False),
            (Timestamp(1), False),
            (Timedelta(1), False),
        ],
        ids=str,
    )
    def test_contains_interval(self, item, expected):
        # GH#23705
        cat = Categorical(IntervalIndex.from_breaks(range(3)))
        result = item in cat
        assert result is expected

    def test_contains_list(self):
        # GH#21729
        cat = Categorical([1, 2, 3])

        assert "a" not in cat

        with pytest.raises(TypeError, match="unhashable type"):
            ["a"] in cat

        with pytest.raises(TypeError, match="unhashable type"):
            ["a", "b"] in cat


@pytest.mark.parametrize("index", [True, False])
def test_mask_with_boolean(index):
    ser = Series(range(3))
    idx = Categorical([True, False, True])
    if index:
        idx = CategoricalIndex(idx)

    assert com.is_bool_indexer(idx)
    result = ser[idx]
    expected = ser[idx.astype("object")]
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("index", [True, False])
def test_mask_with_boolean_na_treated_as_false(index):
    # https://github.com/pandas-dev/pandas/issues/31503
    ser = Series(range(3))
    idx = Categorical([True, False, None])
    if index:
        idx = CategoricalIndex(idx)

    result = ser[idx]
    expected = ser[idx.fillna(False)]

    tm.assert_series_equal(result, expected)


@pytest.fixture
def non_coercible_categorical(monkeypatch):
    """
    Monkeypatch Categorical.__array__ to ensure no implicit conversion.

    Raises
    ------
    ValueError
        When Categorical.__array__ is called.
    """

    # TODO(Categorical): identify other places where this may be
    # useful and move to a conftest.py
    def array(self, dtype=None):
        raise ValueError("I cannot be converted.")

    with monkeypatch.context() as m:
        m.setattr(Categorical, "__array__", array)
        yield


def test_series_at():
    arr = Categorical(["a", "b", "c"])
    ser = Series(arr)
    result = ser.at[0]
    assert result == "a"
