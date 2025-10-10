from datetime import (
    datetime,
    timedelta,
)

from hypothesis import (
    assume,
    given,
    strategies as st,
)
import numpy as np
import pytest

from pandas import (
    Index,
    RangeIndex,
)
import pandas._testing as tm


class TestRangeIndexSetOps:
    @pytest.mark.parametrize("dtype", [None, "int64", "uint64"])
    def test_intersection_mismatched_dtype(self, dtype):
        # check that we cast to float, not object
        index = RangeIndex(start=0, stop=20, step=2, name="foo")
        index = Index(index, dtype=dtype)

        flt = index.astype(np.float64)

        # bc index.equals(flt), we go through fastpath and get RangeIndex back
        result = index.intersection(flt)
        tm.assert_index_equal(result, index, exact=True)

        result = flt.intersection(index)
        tm.assert_index_equal(result, flt, exact=True)

        # neither empty, not-equals
        result = index.intersection(flt[1:])
        tm.assert_index_equal(result, flt[1:], exact=True)

        result = flt[1:].intersection(index)
        tm.assert_index_equal(result, flt[1:], exact=True)

        # empty other
        result = index.intersection(flt[:0])
        tm.assert_index_equal(result, flt[:0], exact=True)

        result = flt[:0].intersection(index)
        tm.assert_index_equal(result, flt[:0], exact=True)

    def test_intersection_empty(self, sort, names):
        # name retention on empty intersections
        index = RangeIndex(start=0, stop=20, step=2, name=names[0])

        # empty other
        result = index.intersection(index[:0].rename(names[1]), sort=sort)
        tm.assert_index_equal(result, index[:0].rename(names[2]), exact=True)

        # empty self
        result = index[:0].intersection(index.rename(names[1]), sort=sort)
        tm.assert_index_equal(result, index[:0].rename(names[2]), exact=True)

    def test_intersection(self, sort):
        # intersect with Index with dtype int64
        index = RangeIndex(start=0, stop=20, step=2)
        other = Index(np.arange(1, 6))
        result = index.intersection(other, sort=sort)
        expected = Index(np.sort(np.intersect1d(index.values, other.values)))
        tm.assert_index_equal(result, expected)

        result = other.intersection(index, sort=sort)
        expected = Index(
            np.sort(np.asarray(np.intersect1d(index.values, other.values)))
        )
        tm.assert_index_equal(result, expected)

        # intersect with increasing RangeIndex
        other = RangeIndex(1, 6)
        result = index.intersection(other, sort=sort)
        expected = Index(np.sort(np.intersect1d(index.values, other.values)))
        tm.assert_index_equal(result, expected, exact="equiv")

        # intersect with decreasing RangeIndex
        other = RangeIndex(5, 0, -1)
        result = index.intersection(other, sort=sort)
        expected = Index(np.sort(np.intersect1d(index.values, other.values)))
        tm.assert_index_equal(result, expected, exact="equiv")

        # reversed (GH 17296)
        result = other.intersection(index, sort=sort)
        tm.assert_index_equal(result, expected, exact="equiv")

        # GH 17296: intersect two decreasing RangeIndexes
        first = RangeIndex(10, -2, -2)
        other = RangeIndex(5, -4, -1)
        expected = first.astype(int).intersection(other.astype(int), sort=sort)
        result = first.intersection(other, sort=sort).astype(int)
        tm.assert_index_equal(result, expected)

        # reversed
        result = other.intersection(first, sort=sort).astype(int)
        tm.assert_index_equal(result, expected)

        index = RangeIndex(5, name="foo")

        # intersect of non-overlapping indices
        other = RangeIndex(5, 10, 1, name="foo")
        result = index.intersection(other, sort=sort)
        expected = RangeIndex(0, 0, 1, name="foo")
        tm.assert_index_equal(result, expected)

        other = RangeIndex(-1, -5, -1)
        result = index.intersection(other, sort=sort)
        expected = RangeIndex(0, 0, 1)
        tm.assert_index_equal(result, expected)

        # intersection of empty indices
        other = RangeIndex(0, 0, 1)
        result = index.intersection(other, sort=sort)
        expected = RangeIndex(0, 0, 1)
        tm.assert_index_equal(result, expected)

        result = other.intersection(index, sort=sort)
        tm.assert_index_equal(result, expected)

    def test_intersection_non_overlapping_gcd(self, sort, names):
        # intersection of non-overlapping values based on start value and gcd
        index = RangeIndex(1, 10, 2, name=names[0])
        other = RangeIndex(0, 10, 4, name=names[1])
        result = index.intersection(other, sort=sort)
        expected = RangeIndex(0, 0, 1, name=names[2])
        tm.assert_index_equal(result, expected)

    def test_union_noncomparable(self, sort):
        # corner case, Index with non-int64 dtype
        index = RangeIndex(start=0, stop=20, step=2)
        other = Index([datetime.now() + timedelta(i) for i in range(4)], dtype=object)
        result = index.union(other, sort=sort)
        expected = Index(np.concatenate((index, other)))
        tm.assert_index_equal(result, expected)

        result = other.union(index, sort=sort)
        expected = Index(np.concatenate((other, index)))
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "idx1, idx2, expected_sorted, expected_notsorted",
        [
            (
                RangeIndex(0, 10, 1),
                RangeIndex(0, 10, 1),
                RangeIndex(0, 10, 1),
                RangeIndex(0, 10, 1),
            ),
            (
                RangeIndex(0, 10, 1),
                RangeIndex(5, 20, 1),
                RangeIndex(0, 20, 1),
                RangeIndex(0, 20, 1),
            ),
            (
                RangeIndex(0, 10, 1),
                RangeIndex(10, 20, 1),
                RangeIndex(0, 20, 1),
                RangeIndex(0, 20, 1),
            ),
            (
                RangeIndex(0, -10, -1),
                RangeIndex(0, -10, -1),
                RangeIndex(0, -10, -1),
                RangeIndex(0, -10, -1),
            ),
            (
                RangeIndex(0, -10, -1),
                RangeIndex(-10, -20, -1),
                RangeIndex(-19, 1, 1),
                RangeIndex(0, -20, -1),
            ),
            (
                RangeIndex(0, 10, 2),
                RangeIndex(1, 10, 2),
                RangeIndex(0, 10, 1),
                Index(list(range(0, 10, 2)) + list(range(1, 10, 2))),
            ),
            (
                RangeIndex(0, 11, 2),
                RangeIndex(1, 12, 2),
                RangeIndex(0, 12, 1),
                Index(list(range(0, 11, 2)) + list(range(1, 12, 2))),
            ),
            (
                RangeIndex(0, 21, 4),
                RangeIndex(-2, 24, 4),
                RangeIndex(-2, 24, 2),
                Index(list(range(0, 21, 4)) + list(range(-2, 24, 4))),
            ),
            (
                RangeIndex(0, -20, -2),
                RangeIndex(-1, -21, -2),
                RangeIndex(-19, 1, 1),
                Index(list(range(0, -20, -2)) + list(range(-1, -21, -2))),
            ),
            (
                RangeIndex(0, 100, 5),
                RangeIndex(0, 100, 20),
                RangeIndex(0, 100, 5),
                RangeIndex(0, 100, 5),
            ),
            (
                RangeIndex(0, -100, -5),
                RangeIndex(5, -100, -20),
                RangeIndex(-95, 10, 5),
                Index(list(range(0, -100, -5)) + [5]),
            ),
            (
                RangeIndex(0, -11, -1),
                RangeIndex(1, -12, -4),
                RangeIndex(-11, 2, 1),
                Index(list(range(0, -11, -1)) + [1, -11]),
            ),
            (RangeIndex(0), RangeIndex(0), RangeIndex(0), RangeIndex(0)),
            (
                RangeIndex(0, -10, -2),
                RangeIndex(0),
                RangeIndex(0, -10, -2),
                RangeIndex(0, -10, -2),
            ),
            (
                RangeIndex(0, 100, 2),
                RangeIndex(100, 150, 200),
                RangeIndex(0, 102, 2),
                RangeIndex(0, 102, 2),
            ),
            (
                RangeIndex(0, -100, -2),
                RangeIndex(-100, 50, 102),
                RangeIndex(-100, 4, 2),
                Index(list(range(0, -100, -2)) + [-100, 2]),
            ),
            (
                RangeIndex(0, -100, -1),
                RangeIndex(0, -50, -3),
                RangeIndex(-99, 1, 1),
                RangeIndex(0, -100, -1),
            ),
            (
                RangeIndex(0, 1, 1),
                RangeIndex(5, 6, 10),
                RangeIndex(0, 6, 5),
                RangeIndex(0, 10, 5),
            ),
            (
                RangeIndex(0, 10, 5),
                RangeIndex(-5, -6, -20),
                RangeIndex(-5, 10, 5),
                Index([0, 5, -5]),
            ),
            (
                RangeIndex(0, 3, 1),
                RangeIndex(4, 5, 1),
                Index([0, 1, 2, 4]),
                Index([0, 1, 2, 4]),
            ),
            (
                RangeIndex(0, 10, 1),
                Index([], dtype=np.int64),
                RangeIndex(0, 10, 1),
                RangeIndex(0, 10, 1),
            ),
            (
                RangeIndex(0),
                Index([1, 5, 6]),
                Index([1, 5, 6]),
                Index([1, 5, 6]),
            ),
            # GH 43885
            (
                RangeIndex(0, 10),
                RangeIndex(0, 5),
                RangeIndex(0, 10),
                RangeIndex(0, 10),
            ),
        ],
        ids=lambda x: repr(x) if isinstance(x, RangeIndex) else x,
    )
    def test_union_sorted(self, idx1, idx2, expected_sorted, expected_notsorted):
        res1 = idx1.union(idx2, sort=None)
        tm.assert_index_equal(res1, expected_sorted, exact=True)

        res1 = idx1.union(idx2, sort=False)
        tm.assert_index_equal(res1, expected_notsorted, exact=True)

        res2 = idx2.union(idx1, sort=None)
        res3 = Index(idx1._values, name=idx1.name).union(idx2, sort=None)
        tm.assert_index_equal(res2, expected_sorted, exact=True)
        tm.assert_index_equal(res3, expected_sorted, exact="equiv")

    def test_union_same_step_misaligned(self):
        # GH#44019
        left = RangeIndex(range(0, 20, 4))
        right = RangeIndex(range(1, 21, 4))

        result = left.union(right)
        expected = Index([0, 1, 4, 5, 8, 9, 12, 13, 16, 17])
        tm.assert_index_equal(result, expected, exact=True)

    def test_difference(self):
        # GH#12034 Cases where we operate against another RangeIndex and may
        #  get back another RangeIndex
        obj = RangeIndex.from_range(range(1, 10), name="foo")

        result = obj.difference(obj)
        expected = RangeIndex.from_range(range(0), name="foo")
        tm.assert_index_equal(result, expected, exact=True)

        result = obj.difference(expected.rename("bar"))
        tm.assert_index_equal(result, obj.rename(None), exact=True)

        result = obj.difference(obj[:3])
        tm.assert_index_equal(result, obj[3:], exact=True)

        result = obj.difference(obj[-3:])
        tm.assert_index_equal(result, obj[:-3], exact=True)

        # Flipping the step of 'other' doesn't affect the result, but
        #  flipping the stepof 'self' does when sort=None
        result = obj[::-1].difference(obj[-3:])
        tm.assert_index_equal(result, obj[:-3], exact=True)

        result = obj[::-1].difference(obj[-3:], sort=False)
        tm.assert_index_equal(result, obj[:-3][::-1], exact=True)

        result = obj[::-1].difference(obj[-3:][::-1])
        tm.assert_index_equal(result, obj[:-3], exact=True)

        result = obj[::-1].difference(obj[-3:][::-1], sort=False)
        tm.assert_index_equal(result, obj[:-3][::-1], exact=True)

        result = obj.difference(obj[2:6])
        expected = Index([1, 2, 7, 8, 9], name="foo")
        tm.assert_index_equal(result, expected, exact=True)

    def test_difference_sort(self):
        # GH#44085 ensure we respect the sort keyword

        idx = Index(range(4))[::-1]
        other = Index(range(3, 4))

        result = idx.difference(other)
        expected = Index(range(3))
        tm.assert_index_equal(result, expected, exact=True)

        result = idx.difference(other, sort=False)
        expected = expected[::-1]
        tm.assert_index_equal(result, expected, exact=True)

        # case where the intersection is empty
        other = range(10, 12)
        result = idx.difference(other, sort=None)
        expected = idx[::-1]
        tm.assert_index_equal(result, expected, exact=True)

    def test_difference_mismatched_step(self):
        obj = RangeIndex.from_range(range(1, 10), name="foo")

        result = obj.difference(obj[::2])
        expected = obj[1::2]
        tm.assert_index_equal(result, expected, exact=True)

        result = obj[::-1].difference(obj[::2], sort=False)
        tm.assert_index_equal(result, expected[::-1], exact=True)

        result = obj.difference(obj[1::2])
        expected = obj[::2]
        tm.assert_index_equal(result, expected, exact=True)

        result = obj[::-1].difference(obj[1::2], sort=False)
        tm.assert_index_equal(result, expected[::-1], exact=True)

    def test_difference_interior_overlap_endpoints_preserved(self):
        left = RangeIndex(range(4))
        right = RangeIndex(range(1, 3))

        result = left.difference(right)
        expected = RangeIndex(0, 4, 3)
        assert expected.tolist() == [0, 3]
        tm.assert_index_equal(result, expected, exact=True)

    def test_difference_endpoints_overlap_interior_preserved(self):
        left = RangeIndex(-8, 20, 7)
        right = RangeIndex(13, -9, -3)

        result = left.difference(right)
        expected = RangeIndex(-1, 13, 7)
        assert expected.tolist() == [-1, 6]
        tm.assert_index_equal(result, expected, exact=True)

    def test_difference_interior_non_preserving(self):
        # case with intersection of length 1 but RangeIndex is not preserved
        idx = Index(range(10))

        other = idx[3:4]
        result = idx.difference(other)
        expected = Index([0, 1, 2, 4, 5, 6, 7, 8, 9])
        tm.assert_index_equal(result, expected, exact=True)

        # case with other.step / self.step > 2
        other = idx[::3]
        result = idx.difference(other)
        expected = Index([1, 2, 4, 5, 7, 8])
        tm.assert_index_equal(result, expected, exact=True)

        # cases with only reaching one end of left
        obj = Index(range(20))
        other = obj[:10:2]
        result = obj.difference(other)
        expected = Index([1, 3, 5, 7, 9] + list(range(10, 20)))
        tm.assert_index_equal(result, expected, exact=True)

        other = obj[1:11:2]
        result = obj.difference(other)
        expected = Index([0, 2, 4, 6, 8, 10] + list(range(11, 20)))
        tm.assert_index_equal(result, expected, exact=True)

    def test_symmetric_difference(self):
        # GH#12034 Cases where we operate against another RangeIndex and may
        #  get back another RangeIndex
        left = RangeIndex.from_range(range(1, 10), name="foo")

        result = left.symmetric_difference(left)
        expected = RangeIndex.from_range(range(0), name="foo")
        tm.assert_index_equal(result, expected)

        result = left.symmetric_difference(expected.rename("bar"))
        tm.assert_index_equal(result, left.rename(None))

        result = left[:-2].symmetric_difference(left[2:])
        expected = Index([1, 2, 8, 9], name="foo")
        tm.assert_index_equal(result, expected, exact=True)

        right = RangeIndex.from_range(range(10, 15))

        result = left.symmetric_difference(right)
        expected = RangeIndex.from_range(range(1, 15))
        tm.assert_index_equal(result, expected)

        result = left.symmetric_difference(right[1:])
        expected = Index([1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14])
        tm.assert_index_equal(result, expected, exact=True)


def assert_range_or_not_is_rangelike(index):
    """
    Check that we either have a RangeIndex or that this index *cannot*
    be represented as a RangeIndex.
    """
    if not isinstance(index, RangeIndex) and len(index) > 0:
        diff = index[:-1] - index[1:]
        assert not (diff == diff[0]).all()


@given(
    st.integers(-20, 20),
    st.integers(-20, 20),
    st.integers(-20, 20),
    st.integers(-20, 20),
    st.integers(-20, 20),
    st.integers(-20, 20),
)
def test_range_difference(start1, stop1, step1, start2, stop2, step2):
    # test that
    #  a) we match Index[int64].difference and
    #  b) we return RangeIndex whenever it is possible to do so.
    assume(step1 != 0)
    assume(step2 != 0)

    left = RangeIndex(start1, stop1, step1)
    right = RangeIndex(start2, stop2, step2)

    result = left.difference(right, sort=None)
    assert_range_or_not_is_rangelike(result)

    left_int64 = Index(left.to_numpy())
    right_int64 = Index(right.to_numpy())

    alt = left_int64.difference(right_int64, sort=None)
    tm.assert_index_equal(result, alt, exact="equiv")

    result = left.difference(right, sort=False)
    assert_range_or_not_is_rangelike(result)

    alt = left_int64.difference(right_int64, sort=False)
    tm.assert_index_equal(result, alt, exact="equiv")
