import numpy as np
import pytest

from pandas.core.dtypes.concat import union_categoricals

import pandas as pd
from pandas import (
    Categorical,
    CategoricalIndex,
    Series,
)
import pandas._testing as tm


class TestUnionCategoricals:
    @pytest.mark.parametrize(
        "a, b, combined",
        [
            (list("abc"), list("abd"), list("abcabd")),
            ([0, 1, 2], [2, 3, 4], [0, 1, 2, 2, 3, 4]),
            ([0, 1.2, 2], [2, 3.4, 4], [0, 1.2, 2, 2, 3.4, 4]),
            (
                ["b", "b", np.nan, "a"],
                ["a", np.nan, "c"],
                ["b", "b", np.nan, "a", "a", np.nan, "c"],
            ),
            (
                pd.date_range("2014-01-01", "2014-01-05"),
                pd.date_range("2014-01-06", "2014-01-07"),
                pd.date_range("2014-01-01", "2014-01-07"),
            ),
            (
                pd.date_range("2014-01-01", "2014-01-05", tz="US/Central"),
                pd.date_range("2014-01-06", "2014-01-07", tz="US/Central"),
                pd.date_range("2014-01-01", "2014-01-07", tz="US/Central"),
            ),
            (
                pd.period_range("2014-01-01", "2014-01-05"),
                pd.period_range("2014-01-06", "2014-01-07"),
                pd.period_range("2014-01-01", "2014-01-07"),
            ),
        ],
    )
    @pytest.mark.parametrize("box", [Categorical, CategoricalIndex, Series])
    def test_union_categorical(self, a, b, combined, box):
        # GH 13361
        result = union_categoricals([box(Categorical(a)), box(Categorical(b))])
        expected = Categorical(combined)
        tm.assert_categorical_equal(result, expected)

    def test_union_categorical_ordered_appearance(self):
        # new categories ordered by appearance
        s = Categorical(["x", "y", "z"])
        s2 = Categorical(["a", "b", "c"])
        result = union_categoricals([s, s2])
        expected = Categorical(
            ["x", "y", "z", "a", "b", "c"], categories=["x", "y", "z", "a", "b", "c"]
        )
        tm.assert_categorical_equal(result, expected)

    def test_union_categorical_ordered_true(self):
        s = Categorical([0, 1.2, 2], ordered=True)
        s2 = Categorical([0, 1.2, 2], ordered=True)
        result = union_categoricals([s, s2])
        expected = Categorical([0, 1.2, 2, 0, 1.2, 2], ordered=True)
        tm.assert_categorical_equal(result, expected)

    def test_union_categorical_match_types(self):
        # must exactly match types
        s = Categorical([0, 1.2, 2])
        s2 = Categorical([2, 3, 4])
        msg = "dtype of categories must be the same"
        with pytest.raises(TypeError, match=msg):
            union_categoricals([s, s2])

    def test_union_categorical_empty(self):
        msg = "No Categoricals to union"
        with pytest.raises(ValueError, match=msg):
            union_categoricals([])

    def test_union_categoricals_nan(self):
        # GH 13759
        res = union_categoricals(
            [Categorical([1, 2, np.nan]), Categorical([3, 2, np.nan])]
        )
        exp = Categorical([1, 2, np.nan, 3, 2, np.nan])
        tm.assert_categorical_equal(res, exp)

        res = union_categoricals(
            [Categorical(["A", "B"]), Categorical(["B", "B", np.nan])]
        )
        exp = Categorical(["A", "B", "B", "B", np.nan])
        tm.assert_categorical_equal(res, exp)

        val1 = [pd.Timestamp("2011-01-01"), pd.Timestamp("2011-03-01"), pd.NaT]
        val2 = [pd.NaT, pd.Timestamp("2011-01-01"), pd.Timestamp("2011-02-01")]

        res = union_categoricals([Categorical(val1), Categorical(val2)])
        exp = Categorical(
            val1 + val2,
            categories=[
                pd.Timestamp("2011-01-01"),
                pd.Timestamp("2011-03-01"),
                pd.Timestamp("2011-02-01"),
            ],
        )
        tm.assert_categorical_equal(res, exp)

        # all NaN
        res = union_categoricals(
            [
                Categorical(np.array([np.nan, np.nan], dtype=object)),
                Categorical(["X"], categories=pd.Index(["X"], dtype=object)),
            ]
        )
        exp = Categorical([np.nan, np.nan, "X"])
        tm.assert_categorical_equal(res, exp)

        res = union_categoricals(
            [Categorical([np.nan, np.nan]), Categorical([np.nan, np.nan])]
        )
        exp = Categorical([np.nan, np.nan, np.nan, np.nan])
        tm.assert_categorical_equal(res, exp)

    @pytest.mark.parametrize("val", [[], ["1"]])
    def test_union_categoricals_empty(self, val, request, using_infer_string):
        # GH 13759
        if using_infer_string and val == ["1"]:
            request.applymarker(
                pytest.mark.xfail(
                    reason="TDOD(infer_string) object and strings dont match"
                )
            )
        res = union_categoricals([Categorical([]), Categorical(val)])
        exp = Categorical(val)
        tm.assert_categorical_equal(res, exp)

    def test_union_categorical_same_category(self):
        # check fastpath
        c1 = Categorical([1, 2, 3, 4], categories=[1, 2, 3, 4])
        c2 = Categorical([3, 2, 1, np.nan], categories=[1, 2, 3, 4])
        res = union_categoricals([c1, c2])
        exp = Categorical([1, 2, 3, 4, 3, 2, 1, np.nan], categories=[1, 2, 3, 4])
        tm.assert_categorical_equal(res, exp)

    def test_union_categorical_same_category_str(self):
        c1 = Categorical(["z", "z", "z"], categories=["x", "y", "z"])
        c2 = Categorical(["x", "x", "x"], categories=["x", "y", "z"])
        res = union_categoricals([c1, c2])
        exp = Categorical(["z", "z", "z", "x", "x", "x"], categories=["x", "y", "z"])
        tm.assert_categorical_equal(res, exp)

    def test_union_categorical_same_categories_different_order(self):
        # https://github.com/pandas-dev/pandas/issues/19096
        c1 = Categorical(["a", "b", "c"], categories=["a", "b", "c"])
        c2 = Categorical(["a", "b", "c"], categories=["b", "a", "c"])
        result = union_categoricals([c1, c2])
        expected = Categorical(
            ["a", "b", "c", "a", "b", "c"], categories=["a", "b", "c"]
        )
        tm.assert_categorical_equal(result, expected)

    def test_union_categoricals_ordered(self):
        c1 = Categorical([1, 2, 3], ordered=True)
        c2 = Categorical([1, 2, 3], ordered=False)

        msg = "Categorical.ordered must be the same"
        with pytest.raises(TypeError, match=msg):
            union_categoricals([c1, c2])

        res = union_categoricals([c1, c1])
        exp = Categorical([1, 2, 3, 1, 2, 3], ordered=True)
        tm.assert_categorical_equal(res, exp)

        c1 = Categorical([1, 2, 3, np.nan], ordered=True)
        c2 = Categorical([3, 2], categories=[1, 2, 3], ordered=True)

        res = union_categoricals([c1, c2])
        exp = Categorical([1, 2, 3, np.nan, 3, 2], ordered=True)
        tm.assert_categorical_equal(res, exp)

        c1 = Categorical([1, 2, 3], ordered=True)
        c2 = Categorical([1, 2, 3], categories=[3, 2, 1], ordered=True)

        msg = "to union ordered Categoricals, all categories must be the same"
        with pytest.raises(TypeError, match=msg):
            union_categoricals([c1, c2])

    def test_union_categoricals_ignore_order(self):
        # GH 15219
        c1 = Categorical([1, 2, 3], ordered=True)
        c2 = Categorical([1, 2, 3], ordered=False)

        res = union_categoricals([c1, c2], ignore_order=True)
        exp = Categorical([1, 2, 3, 1, 2, 3])
        tm.assert_categorical_equal(res, exp)

        msg = "Categorical.ordered must be the same"
        with pytest.raises(TypeError, match=msg):
            union_categoricals([c1, c2], ignore_order=False)

        res = union_categoricals([c1, c1], ignore_order=True)
        exp = Categorical([1, 2, 3, 1, 2, 3])
        tm.assert_categorical_equal(res, exp)

        res = union_categoricals([c1, c1], ignore_order=False)
        exp = Categorical([1, 2, 3, 1, 2, 3], categories=[1, 2, 3], ordered=True)
        tm.assert_categorical_equal(res, exp)

        c1 = Categorical([1, 2, 3, np.nan], ordered=True)
        c2 = Categorical([3, 2], categories=[1, 2, 3], ordered=True)

        res = union_categoricals([c1, c2], ignore_order=True)
        exp = Categorical([1, 2, 3, np.nan, 3, 2])
        tm.assert_categorical_equal(res, exp)

        c1 = Categorical([1, 2, 3], ordered=True)
        c2 = Categorical([1, 2, 3], categories=[3, 2, 1], ordered=True)

        res = union_categoricals([c1, c2], ignore_order=True)
        exp = Categorical([1, 2, 3, 1, 2, 3])
        tm.assert_categorical_equal(res, exp)

        res = union_categoricals([c2, c1], ignore_order=True, sort_categories=True)
        exp = Categorical([1, 2, 3, 1, 2, 3], categories=[1, 2, 3])
        tm.assert_categorical_equal(res, exp)

        c1 = Categorical([1, 2, 3], ordered=True)
        c2 = Categorical([4, 5, 6], ordered=True)
        result = union_categoricals([c1, c2], ignore_order=True)
        expected = Categorical([1, 2, 3, 4, 5, 6])
        tm.assert_categorical_equal(result, expected)

        msg = "to union ordered Categoricals, all categories must be the same"
        with pytest.raises(TypeError, match=msg):
            union_categoricals([c1, c2], ignore_order=False)

        with pytest.raises(TypeError, match=msg):
            union_categoricals([c1, c2])

    def test_union_categoricals_sort(self):
        # GH 13846
        c1 = Categorical(["x", "y", "z"])
        c2 = Categorical(["a", "b", "c"])
        result = union_categoricals([c1, c2], sort_categories=True)
        expected = Categorical(
            ["x", "y", "z", "a", "b", "c"], categories=["a", "b", "c", "x", "y", "z"]
        )
        tm.assert_categorical_equal(result, expected)

        # fastpath
        c1 = Categorical(["a", "b"], categories=["b", "a", "c"])
        c2 = Categorical(["b", "c"], categories=["b", "a", "c"])
        result = union_categoricals([c1, c2], sort_categories=True)
        expected = Categorical(["a", "b", "b", "c"], categories=["a", "b", "c"])
        tm.assert_categorical_equal(result, expected)

        c1 = Categorical(["a", "b"], categories=["c", "a", "b"])
        c2 = Categorical(["b", "c"], categories=["c", "a", "b"])
        result = union_categoricals([c1, c2], sort_categories=True)
        expected = Categorical(["a", "b", "b", "c"], categories=["a", "b", "c"])
        tm.assert_categorical_equal(result, expected)

        # fastpath - skip resort
        c1 = Categorical(["a", "b"], categories=["a", "b", "c"])
        c2 = Categorical(["b", "c"], categories=["a", "b", "c"])
        result = union_categoricals([c1, c2], sort_categories=True)
        expected = Categorical(["a", "b", "b", "c"], categories=["a", "b", "c"])
        tm.assert_categorical_equal(result, expected)

        c1 = Categorical(["x", np.nan])
        c2 = Categorical([np.nan, "b"])
        result = union_categoricals([c1, c2], sort_categories=True)
        expected = Categorical(["x", np.nan, np.nan, "b"], categories=["b", "x"])
        tm.assert_categorical_equal(result, expected)

        c1 = Categorical([np.nan])
        c2 = Categorical([np.nan])
        result = union_categoricals([c1, c2], sort_categories=True)
        expected = Categorical([np.nan, np.nan])
        tm.assert_categorical_equal(result, expected)

        c1 = Categorical([])
        c2 = Categorical([])
        result = union_categoricals([c1, c2], sort_categories=True)
        expected = Categorical([])
        tm.assert_categorical_equal(result, expected)

        c1 = Categorical(["b", "a"], categories=["b", "a", "c"], ordered=True)
        c2 = Categorical(["a", "c"], categories=["b", "a", "c"], ordered=True)
        msg = "Cannot use sort_categories=True with ordered Categoricals"
        with pytest.raises(TypeError, match=msg):
            union_categoricals([c1, c2], sort_categories=True)

    def test_union_categoricals_sort_false(self):
        # GH 13846
        c1 = Categorical(["x", "y", "z"])
        c2 = Categorical(["a", "b", "c"])
        result = union_categoricals([c1, c2], sort_categories=False)
        expected = Categorical(
            ["x", "y", "z", "a", "b", "c"], categories=["x", "y", "z", "a", "b", "c"]
        )
        tm.assert_categorical_equal(result, expected)

    def test_union_categoricals_sort_false_fastpath(self):
        # fastpath
        c1 = Categorical(["a", "b"], categories=["b", "a", "c"])
        c2 = Categorical(["b", "c"], categories=["b", "a", "c"])
        result = union_categoricals([c1, c2], sort_categories=False)
        expected = Categorical(["a", "b", "b", "c"], categories=["b", "a", "c"])
        tm.assert_categorical_equal(result, expected)

    def test_union_categoricals_sort_false_skipresort(self):
        # fastpath - skip resort
        c1 = Categorical(["a", "b"], categories=["a", "b", "c"])
        c2 = Categorical(["b", "c"], categories=["a", "b", "c"])
        result = union_categoricals([c1, c2], sort_categories=False)
        expected = Categorical(["a", "b", "b", "c"], categories=["a", "b", "c"])
        tm.assert_categorical_equal(result, expected)

    def test_union_categoricals_sort_false_one_nan(self):
        c1 = Categorical(["x", np.nan])
        c2 = Categorical([np.nan, "b"])
        result = union_categoricals([c1, c2], sort_categories=False)
        expected = Categorical(["x", np.nan, np.nan, "b"], categories=["x", "b"])
        tm.assert_categorical_equal(result, expected)

    def test_union_categoricals_sort_false_only_nan(self):
        c1 = Categorical([np.nan])
        c2 = Categorical([np.nan])
        result = union_categoricals([c1, c2], sort_categories=False)
        expected = Categorical([np.nan, np.nan])
        tm.assert_categorical_equal(result, expected)

    def test_union_categoricals_sort_false_empty(self):
        c1 = Categorical([])
        c2 = Categorical([])
        result = union_categoricals([c1, c2], sort_categories=False)
        expected = Categorical([])
        tm.assert_categorical_equal(result, expected)

    def test_union_categoricals_sort_false_ordered_true(self):
        c1 = Categorical(["b", "a"], categories=["b", "a", "c"], ordered=True)
        c2 = Categorical(["a", "c"], categories=["b", "a", "c"], ordered=True)
        result = union_categoricals([c1, c2], sort_categories=False)
        expected = Categorical(
            ["b", "a", "a", "c"], categories=["b", "a", "c"], ordered=True
        )
        tm.assert_categorical_equal(result, expected)

    def test_union_categorical_unwrap(self):
        # GH 14173
        c1 = Categorical(["a", "b"])
        c2 = Series(["b", "c"], dtype="category")
        result = union_categoricals([c1, c2])
        expected = Categorical(["a", "b", "b", "c"])
        tm.assert_categorical_equal(result, expected)

        c2 = CategoricalIndex(c2)
        result = union_categoricals([c1, c2])
        tm.assert_categorical_equal(result, expected)

        c1 = Series(c1)
        result = union_categoricals([c1, c2])
        tm.assert_categorical_equal(result, expected)

        msg = "all components to combine must be Categorical"
        with pytest.raises(TypeError, match=msg):
            union_categoricals([c1, ["a", "b", "c"]])
