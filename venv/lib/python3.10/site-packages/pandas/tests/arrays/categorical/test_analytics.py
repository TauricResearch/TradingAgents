import re
import sys

import numpy as np
import pytest

from pandas.compat import PYPY

from pandas import (
    Categorical,
    CategoricalDtype,
    DataFrame,
    Index,
    NaT,
    Series,
    date_range,
)
import pandas._testing as tm
from pandas.api.types import is_scalar


class TestCategoricalAnalytics:
    @pytest.mark.parametrize("aggregation", ["min", "max"])
    def test_min_max_not_ordered_raises(self, aggregation):
        # unordered cats have no min/max
        cat = Categorical(["a", "b", "c", "d"], ordered=False)
        msg = f"Categorical is not ordered for operation {aggregation}"
        agg_func = getattr(cat, aggregation)

        with pytest.raises(TypeError, match=msg):
            agg_func()

        ufunc = np.minimum if aggregation == "min" else np.maximum
        with pytest.raises(TypeError, match=msg):
            ufunc.reduce(cat)

    def test_min_max_ordered(self, index_or_series_or_array):
        cat = Categorical(["a", "b", "c", "d"], ordered=True)
        obj = index_or_series_or_array(cat)
        _min = obj.min()
        _max = obj.max()
        assert _min == "a"
        assert _max == "d"

        assert np.minimum.reduce(obj) == "a"
        assert np.maximum.reduce(obj) == "d"
        # TODO: raises if we pass axis=0  (on Index and Categorical, not Series)

        cat = Categorical(
            ["a", "b", "c", "d"], categories=["d", "c", "b", "a"], ordered=True
        )
        obj = index_or_series_or_array(cat)
        _min = obj.min()
        _max = obj.max()
        assert _min == "d"
        assert _max == "a"
        assert np.minimum.reduce(obj) == "d"
        assert np.maximum.reduce(obj) == "a"

    def test_min_max_reduce(self):
        # GH52788
        cat = Categorical(["a", "b", "c", "d"], ordered=True)
        df = DataFrame(cat)

        result_max = df.agg("max")
        expected_max = Series(Categorical(["d"], dtype=cat.dtype))
        tm.assert_series_equal(result_max, expected_max)

        result_min = df.agg("min")
        expected_min = Series(Categorical(["a"], dtype=cat.dtype))
        tm.assert_series_equal(result_min, expected_min)

    @pytest.mark.parametrize(
        "categories,expected",
        [
            (list("ABC"), np.nan),
            ([1, 2, 3], np.nan),
            pytest.param(
                Series(date_range("2020-01-01", periods=3), dtype="category"),
                NaT,
                marks=pytest.mark.xfail(
                    reason="https://github.com/pandas-dev/pandas/issues/29962"
                ),
            ),
        ],
    )
    @pytest.mark.parametrize("aggregation", ["min", "max"])
    def test_min_max_ordered_empty(self, categories, expected, aggregation):
        # GH 30227
        cat = Categorical([], categories=categories, ordered=True)

        agg_func = getattr(cat, aggregation)
        result = agg_func()
        assert result is expected

    @pytest.mark.parametrize(
        "values, categories",
        [(["a", "b", "c", np.nan], list("cba")), ([1, 2, 3, np.nan], [3, 2, 1])],
    )
    @pytest.mark.parametrize("skipna", [True, False])
    @pytest.mark.parametrize("function", ["min", "max"])
    def test_min_max_with_nan(self, values, categories, function, skipna):
        # GH 25303
        cat = Categorical(values, categories=categories, ordered=True)
        result = getattr(cat, function)(skipna=skipna)

        if skipna is False:
            assert result is np.nan
        else:
            expected = categories[0] if function == "min" else categories[2]
            assert result == expected

    @pytest.mark.parametrize("function", ["min", "max"])
    @pytest.mark.parametrize("skipna", [True, False])
    def test_min_max_only_nan(self, function, skipna):
        # https://github.com/pandas-dev/pandas/issues/33450
        cat = Categorical([np.nan], categories=[1, 2], ordered=True)
        result = getattr(cat, function)(skipna=skipna)
        assert result is np.nan

    @pytest.mark.parametrize("method", ["min", "max"])
    def test_numeric_only_min_max_raises(self, method):
        # GH 25303
        cat = Categorical(
            [np.nan, 1, 2, np.nan], categories=[5, 4, 3, 2, 1], ordered=True
        )
        with pytest.raises(TypeError, match=".* got an unexpected keyword"):
            getattr(cat, method)(numeric_only=True)

    @pytest.mark.parametrize("method", ["min", "max"])
    def test_numpy_min_max_raises(self, method):
        cat = Categorical(["a", "b", "c", "b"], ordered=False)
        msg = (
            f"Categorical is not ordered for operation {method}\n"
            "you can use .as_ordered() to change the Categorical to an ordered one"
        )
        method = getattr(np, method)
        with pytest.raises(TypeError, match=re.escape(msg)):
            method(cat)

    @pytest.mark.parametrize("kwarg", ["axis", "out", "keepdims"])
    @pytest.mark.parametrize("method", ["min", "max"])
    def test_numpy_min_max_unsupported_kwargs_raises(self, method, kwarg):
        cat = Categorical(["a", "b", "c", "b"], ordered=True)
        msg = (
            f"the '{kwarg}' parameter is not supported in the pandas implementation "
            f"of {method}"
        )
        if kwarg == "axis":
            msg = r"`axis` must be fewer than the number of dimensions \(1\)"
        kwargs = {kwarg: 42}
        method = getattr(np, method)
        with pytest.raises(ValueError, match=msg):
            method(cat, **kwargs)

    @pytest.mark.parametrize("method, expected", [("min", "a"), ("max", "c")])
    def test_numpy_min_max_axis_equals_none(self, method, expected):
        cat = Categorical(["a", "b", "c", "b"], ordered=True)
        method = getattr(np, method)
        result = method(cat, axis=None)
        assert result == expected

    @pytest.mark.parametrize(
        "values,categories,exp_mode",
        [
            ([1, 1, 2, 4, 5, 5, 5], [5, 4, 3, 2, 1], [5]),
            ([1, 1, 1, 4, 5, 5, 5], [5, 4, 3, 2, 1], [5, 1]),
            ([1, 2, 3, 4, 5], [5, 4, 3, 2, 1], [5, 4, 3, 2, 1]),
            ([np.nan, np.nan, np.nan, 4, 5], [5, 4, 3, 2, 1], [5, 4]),
            ([np.nan, np.nan, np.nan, 4, 5, 4], [5, 4, 3, 2, 1], [4]),
            ([np.nan, np.nan, 4, 5, 4], [5, 4, 3, 2, 1], [4]),
        ],
    )
    def test_mode(self, values, categories, exp_mode):
        cat = Categorical(values, categories=categories, ordered=True)
        res = Series(cat).mode()._values
        exp = Categorical(exp_mode, categories=categories, ordered=True)
        tm.assert_categorical_equal(res, exp)

    def test_searchsorted(self, ordered):
        # https://github.com/pandas-dev/pandas/issues/8420
        # https://github.com/pandas-dev/pandas/issues/14522

        cat = Categorical(
            ["cheese", "milk", "apple", "bread", "bread"],
            categories=["cheese", "milk", "apple", "bread"],
            ordered=ordered,
        )
        ser = Series(cat)

        # Searching for single item argument, side='left' (default)
        res_cat = cat.searchsorted("apple")
        assert res_cat == 2
        assert is_scalar(res_cat)

        res_ser = ser.searchsorted("apple")
        assert res_ser == 2
        assert is_scalar(res_ser)

        # Searching for single item array, side='left' (default)
        res_cat = cat.searchsorted(["bread"])
        res_ser = ser.searchsorted(["bread"])
        exp = np.array([3], dtype=np.intp)
        tm.assert_numpy_array_equal(res_cat, exp)
        tm.assert_numpy_array_equal(res_ser, exp)

        # Searching for several items array, side='right'
        res_cat = cat.searchsorted(["apple", "bread"], side="right")
        res_ser = ser.searchsorted(["apple", "bread"], side="right")
        exp = np.array([3, 5], dtype=np.intp)
        tm.assert_numpy_array_equal(res_cat, exp)
        tm.assert_numpy_array_equal(res_ser, exp)

        # Searching for a single value that is not from the Categorical
        with pytest.raises(TypeError, match="cucumber"):
            cat.searchsorted("cucumber")
        with pytest.raises(TypeError, match="cucumber"):
            ser.searchsorted("cucumber")

        # Searching for multiple values one of each is not from the Categorical
        msg = (
            "Cannot setitem on a Categorical with a new category, "
            "set the categories first"
        )
        with pytest.raises(TypeError, match=msg):
            cat.searchsorted(["bread", "cucumber"])
        with pytest.raises(TypeError, match=msg):
            ser.searchsorted(["bread", "cucumber"])

    def test_unique(self, ordered):
        # GH38140
        dtype = CategoricalDtype(["a", "b", "c"], ordered=ordered)

        # categories are reordered based on value when ordered=False
        cat = Categorical(["a", "b", "c"], dtype=dtype)
        res = cat.unique()
        tm.assert_categorical_equal(res, cat)

        cat = Categorical(["a", "b", "a", "a"], dtype=dtype)
        res = cat.unique()
        tm.assert_categorical_equal(res, Categorical(["a", "b"], dtype=dtype))

        cat = Categorical(["c", "a", "b", "a", "a"], dtype=dtype)
        res = cat.unique()
        exp_cat = Categorical(["c", "a", "b"], dtype=dtype)
        tm.assert_categorical_equal(res, exp_cat)

        # nan must be removed
        cat = Categorical(["b", np.nan, "b", np.nan, "a"], dtype=dtype)
        res = cat.unique()
        exp_cat = Categorical(["b", np.nan, "a"], dtype=dtype)
        tm.assert_categorical_equal(res, exp_cat)

    def test_unique_index_series(self, ordered):
        # GH38140
        dtype = CategoricalDtype([3, 2, 1], ordered=ordered)

        c = Categorical([3, 1, 2, 2, 1], dtype=dtype)
        # Categorical.unique sorts categories by appearance order
        # if ordered=False
        exp = Categorical([3, 1, 2], dtype=dtype)
        tm.assert_categorical_equal(c.unique(), exp)

        tm.assert_index_equal(Index(c).unique(), Index(exp))
        tm.assert_categorical_equal(Series(c).unique(), exp)

        c = Categorical([1, 1, 2, 2], dtype=dtype)
        exp = Categorical([1, 2], dtype=dtype)
        tm.assert_categorical_equal(c.unique(), exp)
        tm.assert_index_equal(Index(c).unique(), Index(exp))
        tm.assert_categorical_equal(Series(c).unique(), exp)

    def test_shift(self):
        # GH 9416
        cat = Categorical(["a", "b", "c", "d", "a"])

        # shift forward
        sp1 = cat.shift(1)
        xp1 = Categorical([np.nan, "a", "b", "c", "d"])
        tm.assert_categorical_equal(sp1, xp1)
        tm.assert_categorical_equal(cat[:-1], sp1[1:])

        # shift back
        sn2 = cat.shift(-2)
        xp2 = Categorical(
            ["c", "d", "a", np.nan, np.nan], categories=["a", "b", "c", "d"]
        )
        tm.assert_categorical_equal(sn2, xp2)
        tm.assert_categorical_equal(cat[2:], sn2[:-2])

        # shift by zero
        tm.assert_categorical_equal(cat, cat.shift(0))

    def test_nbytes(self):
        cat = Categorical([1, 2, 3])
        exp = 3 + 3 * 8  # 3 int8s for values + 3 int64s for categories
        assert cat.nbytes == exp

    def test_memory_usage(self, using_infer_string):
        cat = Categorical([1, 2, 3])

        # .categories is an index, so we include the hashtable
        assert 0 < cat.nbytes <= cat.memory_usage()
        assert 0 < cat.nbytes <= cat.memory_usage(deep=True)

        cat = Categorical(["foo", "foo", "bar"])
        if using_infer_string:
            if cat.categories.dtype.storage == "python":
                assert cat.memory_usage(deep=True) > cat.nbytes
            else:
                assert cat.memory_usage(deep=True) >= cat.nbytes
        else:
            assert cat.memory_usage(deep=True) > cat.nbytes

        if not PYPY:
            # sys.getsizeof will call the .memory_usage with
            # deep=True, and add on some GC overhead
            diff = cat.memory_usage(deep=True) - sys.getsizeof(cat)
            assert abs(diff) < 100

    def test_map(self):
        c = Categorical(list("ABABC"), categories=list("CBA"), ordered=True)
        result = c.map(lambda x: x.lower(), na_action=None)
        exp = Categorical(list("ababc"), categories=list("cba"), ordered=True)
        tm.assert_categorical_equal(result, exp)

        c = Categorical(list("ABABC"), categories=list("ABC"), ordered=False)
        result = c.map(lambda x: x.lower(), na_action=None)
        exp = Categorical(list("ababc"), categories=list("abc"), ordered=False)
        tm.assert_categorical_equal(result, exp)

        result = c.map(lambda x: 1, na_action=None)
        # GH 12766: Return an index not an array
        tm.assert_index_equal(result, Index(np.array([1] * 5, dtype=np.int64)))

    @pytest.mark.parametrize("value", [1, "True", [1, 2, 3], 5.0])
    def test_validate_inplace_raises(self, value):
        cat = Categorical(["A", "B", "B", "C", "A"])
        msg = (
            'For argument "inplace" expected type bool, '
            f"received type {type(value).__name__}"
        )

        with pytest.raises(ValueError, match=msg):
            cat.sort_values(inplace=value)

    def test_quantile_empty(self):
        # make sure we have correct itemsize on resulting codes
        cat = Categorical(["A", "B"])
        idx = Index([0.0, 0.5])
        result = cat[:0]._quantile(idx, interpolation="linear")
        assert result._codes.dtype == np.int8

        expected = cat.take([-1, -1], allow_fill=True)
        tm.assert_extension_array_equal(result, expected)
