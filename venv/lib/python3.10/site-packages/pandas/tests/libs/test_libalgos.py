from datetime import datetime
from itertools import permutations

import numpy as np

from pandas._libs import algos as libalgos

import pandas._testing as tm


def test_ensure_platform_int():
    arr = np.arange(100, dtype=np.intp)

    result = libalgos.ensure_platform_int(arr)
    assert result is arr


def test_is_lexsorted():
    failure = [
        np.array(
            ([3] * 32) + ([2] * 32) + ([1] * 32) + ([0] * 32),
            dtype="int64",
        ),
        np.array(
            list(range(31))[::-1] * 4,
            dtype="int64",
        ),
    ]

    assert not libalgos.is_lexsorted(failure)


def test_groupsort_indexer():
    a = np.random.default_rng(2).integers(0, 1000, 100).astype(np.intp)
    b = np.random.default_rng(2).integers(0, 1000, 100).astype(np.intp)

    result = libalgos.groupsort_indexer(a, 1000)[0]

    # need to use a stable sort
    # np.argsort returns int, groupsort_indexer
    # always returns intp
    expected = np.argsort(a, kind="mergesort")
    expected = expected.astype(np.intp)

    tm.assert_numpy_array_equal(result, expected)

    # compare with lexsort
    # np.lexsort returns int, groupsort_indexer
    # always returns intp
    key = a * 1000 + b
    result = libalgos.groupsort_indexer(key, 1000000)[0]
    expected = np.lexsort((b, a))
    expected = expected.astype(np.intp)

    tm.assert_numpy_array_equal(result, expected)


class TestPadBackfill:
    def test_backfill(self):
        old = np.array([1, 5, 10], dtype=np.int64)
        new = np.array(list(range(12)), dtype=np.int64)

        filler = libalgos.backfill["int64_t"](old, new)

        expect_filler = np.array([0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 2, -1], dtype=np.intp)
        tm.assert_numpy_array_equal(filler, expect_filler)

        # corner case
        old = np.array([1, 4], dtype=np.int64)
        new = np.array(list(range(5, 10)), dtype=np.int64)
        filler = libalgos.backfill["int64_t"](old, new)

        expect_filler = np.array([-1, -1, -1, -1, -1], dtype=np.intp)
        tm.assert_numpy_array_equal(filler, expect_filler)

    def test_pad(self):
        old = np.array([1, 5, 10], dtype=np.int64)
        new = np.array(list(range(12)), dtype=np.int64)

        filler = libalgos.pad["int64_t"](old, new)

        expect_filler = np.array([-1, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 2], dtype=np.intp)
        tm.assert_numpy_array_equal(filler, expect_filler)

        # corner case
        old = np.array([5, 10], dtype=np.int64)
        new = np.arange(5, dtype=np.int64)
        filler = libalgos.pad["int64_t"](old, new)
        expect_filler = np.array([-1, -1, -1, -1, -1], dtype=np.intp)
        tm.assert_numpy_array_equal(filler, expect_filler)

    def test_pad_backfill_object_segfault(self):
        old = np.array([], dtype="O")
        new = np.array([datetime(2010, 12, 31)], dtype="O")

        result = libalgos.pad["object"](old, new)
        expected = np.array([-1], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

        result = libalgos.pad["object"](new, old)
        expected = np.array([], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

        result = libalgos.backfill["object"](old, new)
        expected = np.array([-1], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

        result = libalgos.backfill["object"](new, old)
        expected = np.array([], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)


class TestInfinity:
    def test_infinity_sort(self):
        # GH#13445
        # numpy's argsort can be unhappy if something is less than
        # itself.  Instead, let's give our infinities a self-consistent
        # ordering, but outside the float extended real line.

        Inf = libalgos.Infinity()
        NegInf = libalgos.NegInfinity()

        ref_nums = [NegInf, float("-inf"), -1e100, 0, 1e100, float("inf"), Inf]

        assert all(Inf >= x for x in ref_nums)
        assert all(Inf > x or x is Inf for x in ref_nums)
        assert Inf >= Inf and Inf == Inf
        assert not Inf < Inf and not Inf > Inf
        assert libalgos.Infinity() == libalgos.Infinity()
        assert not libalgos.Infinity() != libalgos.Infinity()

        assert all(NegInf <= x for x in ref_nums)
        assert all(NegInf < x or x is NegInf for x in ref_nums)
        assert NegInf <= NegInf and NegInf == NegInf
        assert not NegInf < NegInf and not NegInf > NegInf
        assert libalgos.NegInfinity() == libalgos.NegInfinity()
        assert not libalgos.NegInfinity() != libalgos.NegInfinity()

        for perm in permutations(ref_nums):
            assert sorted(perm) == ref_nums

        # smoke tests
        np.array([libalgos.Infinity()] * 32).argsort()
        np.array([libalgos.NegInfinity()] * 32).argsort()

    def test_infinity_against_nan(self):
        Inf = libalgos.Infinity()
        NegInf = libalgos.NegInfinity()

        assert not Inf > np.nan
        assert not Inf >= np.nan
        assert not Inf < np.nan
        assert not Inf <= np.nan
        assert not Inf == np.nan
        assert Inf != np.nan

        assert not NegInf > np.nan
        assert not NegInf >= np.nan
        assert not NegInf < np.nan
        assert not NegInf <= np.nan
        assert not NegInf == np.nan
        assert NegInf != np.nan
