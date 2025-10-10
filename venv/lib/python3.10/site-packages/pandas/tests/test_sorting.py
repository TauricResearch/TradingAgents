from collections import defaultdict
from datetime import datetime
from itertools import product

import numpy as np
import pytest

from pandas import (
    NA,
    DataFrame,
    MultiIndex,
    Series,
    array,
    concat,
    merge,
)
import pandas._testing as tm
from pandas.core.algorithms import safe_sort
import pandas.core.common as com
from pandas.core.sorting import (
    _decons_group_index,
    get_group_index,
    is_int64_overflow_possible,
    lexsort_indexer,
    nargsort,
)


@pytest.fixture
def left_right():
    low, high, n = -1 << 10, 1 << 10, 1 << 20
    left = DataFrame(
        np.random.default_rng(2).integers(low, high, (n, 7)), columns=list("ABCDEFG")
    )
    left["left"] = left.sum(axis=1)

    # one-2-one match
    i = np.random.default_rng(2).permutation(len(left))
    right = left.iloc[i].copy()
    right.columns = right.columns[:-1].tolist() + ["right"]
    right.index = np.arange(len(right))
    right["right"] *= -1
    return left, right


class TestSorting:
    @pytest.mark.slow
    def test_int64_overflow(self):
        B = np.concatenate((np.arange(1000), np.arange(1000), np.arange(500)))
        A = np.arange(2500)
        df = DataFrame(
            {
                "A": A,
                "B": B,
                "C": A,
                "D": B,
                "E": A,
                "F": B,
                "G": A,
                "H": B,
                "values": np.random.default_rng(2).standard_normal(2500),
            }
        )

        lg = df.groupby(["A", "B", "C", "D", "E", "F", "G", "H"])
        rg = df.groupby(["H", "G", "F", "E", "D", "C", "B", "A"])

        left = lg.sum()["values"]
        right = rg.sum()["values"]

        exp_index, _ = left.index.sortlevel()
        tm.assert_index_equal(left.index, exp_index)

        exp_index, _ = right.index.sortlevel(0)
        tm.assert_index_equal(right.index, exp_index)

        tups = list(map(tuple, df[["A", "B", "C", "D", "E", "F", "G", "H"]].values))
        tups = com.asarray_tuplesafe(tups)

        expected = df.groupby(tups).sum()["values"]

        for k, v in expected.items():
            assert left[k] == right[k[::-1]]
            assert left[k] == v
        assert len(left) == len(right)

    def test_int64_overflow_groupby_large_range(self):
        # GH9096
        values = range(55109)
        data = DataFrame.from_dict({"a": values, "b": values, "c": values, "d": values})
        grouped = data.groupby(["a", "b", "c", "d"])
        assert len(grouped) == len(values)

    @pytest.mark.parametrize("agg", ["mean", "median"])
    def test_int64_overflow_groupby_large_df_shuffled(self, agg):
        rs = np.random.default_rng(2)
        arr = rs.integers(-1 << 12, 1 << 12, (1 << 15, 5))
        i = rs.choice(len(arr), len(arr) * 4)
        arr = np.vstack((arr, arr[i]))  # add some duplicate rows

        i = rs.permutation(len(arr))
        arr = arr[i]  # shuffle rows

        df = DataFrame(arr, columns=list("abcde"))
        df["jim"], df["joe"] = np.zeros((2, len(df)))
        gr = df.groupby(list("abcde"))

        # verify this is testing what it is supposed to test!
        assert is_int64_overflow_possible(gr._grouper.shape)

        mi = MultiIndex.from_arrays(
            [ar.ravel() for ar in np.array_split(np.unique(arr, axis=0), 5, axis=1)],
            names=list("abcde"),
        )

        res = DataFrame(
            np.zeros((len(mi), 2)), columns=["jim", "joe"], index=mi
        ).sort_index()

        tm.assert_frame_equal(getattr(gr, agg)(), res)

    @pytest.mark.parametrize(
        "order, na_position, exp",
        [
            [
                True,
                "last",
                list(range(5, 105)) + list(range(5)) + list(range(105, 110)),
            ],
            [
                True,
                "first",
                list(range(5)) + list(range(105, 110)) + list(range(5, 105)),
            ],
            [
                False,
                "last",
                list(range(104, 4, -1)) + list(range(5)) + list(range(105, 110)),
            ],
            [
                False,
                "first",
                list(range(5)) + list(range(105, 110)) + list(range(104, 4, -1)),
            ],
        ],
    )
    def test_lexsort_indexer(self, order, na_position, exp):
        keys = [[np.nan] * 5 + list(range(100)) + [np.nan] * 5]
        result = lexsort_indexer(keys, orders=order, na_position=na_position)
        tm.assert_numpy_array_equal(result, np.array(exp, dtype=np.intp))

    @pytest.mark.parametrize(
        "ascending, na_position, exp",
        [
            [
                True,
                "last",
                list(range(5, 105)) + list(range(5)) + list(range(105, 110)),
            ],
            [
                True,
                "first",
                list(range(5)) + list(range(105, 110)) + list(range(5, 105)),
            ],
            [
                False,
                "last",
                list(range(104, 4, -1)) + list(range(5)) + list(range(105, 110)),
            ],
            [
                False,
                "first",
                list(range(5)) + list(range(105, 110)) + list(range(104, 4, -1)),
            ],
        ],
    )
    def test_nargsort(self, ascending, na_position, exp):
        # list places NaNs last, np.array(..., dtype="O") may not place NaNs first
        items = np.array([np.nan] * 5 + list(range(100)) + [np.nan] * 5, dtype="O")

        # mergesort is the most difficult to get right because we want it to be
        # stable.

        # According to numpy/core/tests/test_multiarray, """The number of
        # sorted items must be greater than ~50 to check the actual algorithm
        # because quick and merge sort fall over to insertion sort for small
        # arrays."""

        result = nargsort(
            items, kind="mergesort", ascending=ascending, na_position=na_position
        )
        tm.assert_numpy_array_equal(result, np.array(exp), check_dtype=False)


class TestMerge:
    def test_int64_overflow_outer_merge(self):
        # #2690, combinatorial explosion
        df1 = DataFrame(
            np.random.default_rng(2).standard_normal((1000, 7)),
            columns=list("ABCDEF") + ["G1"],
        )
        df2 = DataFrame(
            np.random.default_rng(3).standard_normal((1000, 7)),
            columns=list("ABCDEF") + ["G2"],
        )
        result = merge(df1, df2, how="outer")
        assert len(result) == 2000

    @pytest.mark.slow
    def test_int64_overflow_check_sum_col(self, left_right):
        left, right = left_right

        out = merge(left, right, how="outer")
        assert len(out) == len(left)
        tm.assert_series_equal(out["left"], -out["right"], check_names=False)
        result = out.iloc[:, :-2].sum(axis=1)
        tm.assert_series_equal(out["left"], result, check_names=False)
        assert result.name is None

    @pytest.mark.slow
    @pytest.mark.parametrize("how", ["left", "right", "outer", "inner"])
    def test_int64_overflow_how_merge(self, left_right, how):
        left, right = left_right

        out = merge(left, right, how="outer")
        out.sort_values(out.columns.tolist(), inplace=True)
        out.index = np.arange(len(out))
        tm.assert_frame_equal(out, merge(left, right, how=how, sort=True))

    @pytest.mark.slow
    def test_int64_overflow_sort_false_order(self, left_right):
        left, right = left_right

        # check that left merge w/ sort=False maintains left frame order
        out = merge(left, right, how="left", sort=False)
        tm.assert_frame_equal(left, out[left.columns.tolist()])

        out = merge(right, left, how="left", sort=False)
        tm.assert_frame_equal(right, out[right.columns.tolist()])

    @pytest.mark.slow
    @pytest.mark.parametrize("how", ["left", "right", "outer", "inner"])
    @pytest.mark.parametrize("sort", [True, False])
    def test_int64_overflow_one_to_many_none_match(self, how, sort):
        # one-2-many/none match
        low, high, n = -1 << 10, 1 << 10, 1 << 11
        left = DataFrame(
            np.random.default_rng(2).integers(low, high, (n, 7)).astype("int64"),
            columns=list("ABCDEFG"),
        )

        # confirm that this is checking what it is supposed to check
        shape = left.apply(Series.nunique).values
        assert is_int64_overflow_possible(shape)

        # add duplicates to left frame
        left = concat([left, left], ignore_index=True)

        right = DataFrame(
            np.random.default_rng(3).integers(low, high, (n // 2, 7)).astype("int64"),
            columns=list("ABCDEFG"),
        )

        # add duplicates & overlap with left to the right frame
        i = np.random.default_rng(4).choice(len(left), n)
        right = concat([right, right, left.iloc[i]], ignore_index=True)

        left["left"] = np.random.default_rng(2).standard_normal(len(left))
        right["right"] = np.random.default_rng(2).standard_normal(len(right))

        # shuffle left & right frames
        i = np.random.default_rng(5).permutation(len(left))
        left = left.iloc[i].copy()
        left.index = np.arange(len(left))

        i = np.random.default_rng(6).permutation(len(right))
        right = right.iloc[i].copy()
        right.index = np.arange(len(right))

        # manually compute outer merge
        ldict, rdict = defaultdict(list), defaultdict(list)

        for idx, row in left.set_index(list("ABCDEFG")).iterrows():
            ldict[idx].append(row["left"])

        for idx, row in right.set_index(list("ABCDEFG")).iterrows():
            rdict[idx].append(row["right"])

        vals = []
        for k, lval in ldict.items():
            rval = rdict.get(k, [np.nan])
            for lv, rv in product(lval, rval):
                vals.append(
                    k
                    + (
                        lv,
                        rv,
                    )
                )

        for k, rval in rdict.items():
            if k not in ldict:
                vals.extend(
                    k
                    + (
                        np.nan,
                        rv,
                    )
                    for rv in rval
                )

        def align(df):
            df = df.sort_values(df.columns.tolist())
            df.index = np.arange(len(df))
            return df

        out = DataFrame(vals, columns=list("ABCDEFG") + ["left", "right"])
        out = align(out)

        jmask = {
            "left": out["left"].notna(),
            "right": out["right"].notna(),
            "inner": out["left"].notna() & out["right"].notna(),
            "outer": np.ones(len(out), dtype="bool"),
        }

        mask = jmask[how]
        frame = align(out[mask].copy())
        assert mask.all() ^ mask.any() or how == "outer"

        res = merge(left, right, how=how, sort=sort)
        if sort:
            kcols = list("ABCDEFG")
            tm.assert_frame_equal(
                res[kcols].copy(), res[kcols].sort_values(kcols, kind="mergesort")
            )

        # as in GH9092 dtypes break with outer/right join
        # 2021-12-18: dtype does not break anymore
        tm.assert_frame_equal(frame, align(res))


@pytest.mark.parametrize(
    "codes_list, shape",
    [
        [
            [
                np.tile([0, 1, 2, 3, 0, 1, 2, 3], 100).astype(np.int64),
                np.tile([0, 2, 4, 3, 0, 1, 2, 3], 100).astype(np.int64),
                np.tile([5, 1, 0, 2, 3, 0, 5, 4], 100).astype(np.int64),
            ],
            (4, 5, 6),
        ],
        [
            [
                np.tile(np.arange(10000, dtype=np.int64), 5),
                np.tile(np.arange(10000, dtype=np.int64), 5),
            ],
            (10000, 10000),
        ],
    ],
)
def test_decons(codes_list, shape):
    group_index = get_group_index(codes_list, shape, sort=True, xnull=True)
    codes_list2 = _decons_group_index(group_index, shape)

    for a, b in zip(codes_list, codes_list2):
        tm.assert_numpy_array_equal(a, b)


class TestSafeSort:
    @pytest.mark.parametrize(
        "arg, exp",
        [
            [[3, 1, 2, 0, 4], [0, 1, 2, 3, 4]],
            [
                np.array(list("baaacb"), dtype=object),
                np.array(list("aaabbc"), dtype=object),
            ],
            [[], []],
        ],
    )
    def test_basic_sort(self, arg, exp):
        result = safe_sort(np.array(arg))
        expected = np.array(exp)
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize("verify", [True, False])
    @pytest.mark.parametrize(
        "codes, exp_codes",
        [
            [[0, 1, 1, 2, 3, 0, -1, 4], [3, 1, 1, 2, 0, 3, -1, 4]],
            [[], []],
        ],
    )
    def test_codes(self, verify, codes, exp_codes):
        values = np.array([3, 1, 2, 0, 4])
        expected = np.array([0, 1, 2, 3, 4])

        result, result_codes = safe_sort(
            values, codes, use_na_sentinel=True, verify=verify
        )
        expected_codes = np.array(exp_codes, dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)
        tm.assert_numpy_array_equal(result_codes, expected_codes)

    def test_codes_out_of_bound(self):
        values = np.array([3, 1, 2, 0, 4])
        expected = np.array([0, 1, 2, 3, 4])

        # out of bound indices
        codes = [0, 101, 102, 2, 3, 0, 99, 4]
        result, result_codes = safe_sort(values, codes, use_na_sentinel=True)
        expected_codes = np.array([3, -1, -1, 2, 0, 3, -1, 4], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)
        tm.assert_numpy_array_equal(result_codes, expected_codes)

    def test_mixed_integer(self):
        values = np.array(["b", 1, 0, "a", 0, "b"], dtype=object)
        result = safe_sort(values)
        expected = np.array([0, 0, 1, "a", "b", "b"], dtype=object)
        tm.assert_numpy_array_equal(result, expected)

    def test_mixed_integer_with_codes(self):
        values = np.array(["b", 1, 0, "a"], dtype=object)
        codes = [0, 1, 2, 3, 0, -1, 1]
        result, result_codes = safe_sort(values, codes)
        expected = np.array([0, 1, "a", "b"], dtype=object)
        expected_codes = np.array([3, 1, 0, 2, 3, -1, 1], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)
        tm.assert_numpy_array_equal(result_codes, expected_codes)

    def test_unsortable(self):
        # GH 13714
        arr = np.array([1, 2, datetime.now(), 0, 3], dtype=object)
        msg = "'[<>]' not supported between instances of .*"
        with pytest.raises(TypeError, match=msg):
            safe_sort(arr)

    @pytest.mark.parametrize(
        "arg, codes, err, msg",
        [
            [1, None, TypeError, "Only np.ndarray, ExtensionArray, and Index"],
            [np.array([0, 1, 2]), 1, TypeError, "Only list-like objects or None"],
            [np.array([0, 1, 2, 1]), [0, 1], ValueError, "values should be unique"],
        ],
    )
    def test_exceptions(self, arg, codes, err, msg):
        with pytest.raises(err, match=msg):
            safe_sort(values=arg, codes=codes)

    @pytest.mark.parametrize(
        "arg, exp", [[[1, 3, 2], [1, 2, 3]], [[1, 3, np.nan, 2], [1, 2, 3, np.nan]]]
    )
    def test_extension_array(self, arg, exp):
        a = array(arg, dtype="Int64")
        result = safe_sort(a)
        expected = array(exp, dtype="Int64")
        tm.assert_extension_array_equal(result, expected)

    @pytest.mark.parametrize("verify", [True, False])
    def test_extension_array_codes(self, verify):
        a = array([1, 3, 2], dtype="Int64")
        result, codes = safe_sort(a, [0, 1, -1, 2], use_na_sentinel=True, verify=verify)
        expected_values = array([1, 2, 3], dtype="Int64")
        expected_codes = np.array([0, 2, -1, 1], dtype=np.intp)
        tm.assert_extension_array_equal(result, expected_values)
        tm.assert_numpy_array_equal(codes, expected_codes)


def test_mixed_str_null(nulls_fixture):
    values = np.array(["b", nulls_fixture, "a", "b"], dtype=object)
    result = safe_sort(values)
    expected = np.array(["a", "b", "b", nulls_fixture], dtype=object)
    tm.assert_numpy_array_equal(result, expected)


def test_safe_sort_multiindex():
    # GH#48412
    arr1 = Series([2, 1, NA, NA], dtype="Int64")
    arr2 = [2, 1, 3, 3]
    midx = MultiIndex.from_arrays([arr1, arr2])
    result = safe_sort(midx)
    expected = MultiIndex.from_arrays(
        [Series([1, 2, NA, NA], dtype="Int64"), [1, 2, 3, 3]]
    )
    tm.assert_index_equal(result, expected)
