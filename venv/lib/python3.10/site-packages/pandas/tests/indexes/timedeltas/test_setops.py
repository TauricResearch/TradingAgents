import numpy as np
import pytest

import pandas as pd
from pandas import (
    Index,
    TimedeltaIndex,
    timedelta_range,
)
import pandas._testing as tm

from pandas.tseries.offsets import Hour


class TestTimedeltaIndex:
    def test_union(self):
        i1 = timedelta_range("1day", periods=5)
        i2 = timedelta_range("3day", periods=5)
        result = i1.union(i2)
        expected = timedelta_range("1day", periods=7)
        tm.assert_index_equal(result, expected)

        i1 = Index(np.arange(0, 20, 2, dtype=np.int64))
        i2 = timedelta_range(start="1 day", periods=10, freq="D")
        i1.union(i2)  # Works
        i2.union(i1)  # Fails with "AttributeError: can't set attribute"

    def test_union_sort_false(self):
        tdi = timedelta_range("1day", periods=5)

        left = tdi[3:]
        right = tdi[:3]

        # Check that we are testing the desired code path
        assert left._can_fast_union(right)

        result = left.union(right)
        tm.assert_index_equal(result, tdi)

        result = left.union(right, sort=False)
        expected = TimedeltaIndex(["4 Days", "5 Days", "1 Days", "2 Day", "3 Days"])
        tm.assert_index_equal(result, expected)

    def test_union_coverage(self):
        idx = TimedeltaIndex(["3d", "1d", "2d"])
        ordered = TimedeltaIndex(idx.sort_values(), freq="infer")
        result = ordered.union(idx)
        tm.assert_index_equal(result, ordered)

        result = ordered[:0].union(ordered)
        tm.assert_index_equal(result, ordered)
        assert result.freq == ordered.freq

    def test_union_bug_1730(self):
        rng_a = timedelta_range("1 day", periods=4, freq="3h")
        rng_b = timedelta_range("1 day", periods=4, freq="4h")

        result = rng_a.union(rng_b)
        exp = TimedeltaIndex(sorted(set(rng_a) | set(rng_b)))
        tm.assert_index_equal(result, exp)

    def test_union_bug_1745(self):
        left = TimedeltaIndex(["1 day 15:19:49.695000"])
        right = TimedeltaIndex(
            ["2 day 13:04:21.322000", "1 day 15:27:24.873000", "1 day 15:31:05.350000"]
        )

        result = left.union(right)
        exp = TimedeltaIndex(sorted(set(left) | set(right)))
        tm.assert_index_equal(result, exp)

    def test_union_bug_4564(self):
        left = timedelta_range("1 day", "30d")
        right = left + pd.offsets.Minute(15)

        result = left.union(right)
        exp = TimedeltaIndex(sorted(set(left) | set(right)))
        tm.assert_index_equal(result, exp)

    def test_union_freq_infer(self):
        # When taking the union of two TimedeltaIndexes, we infer
        #  a freq even if the arguments don't have freq.  This matches
        #  DatetimeIndex behavior.
        tdi = timedelta_range("1 Day", periods=5)
        left = tdi[[0, 1, 3, 4]]
        right = tdi[[2, 3, 1]]

        assert left.freq is None
        assert right.freq is None

        result = left.union(right)
        tm.assert_index_equal(result, tdi)
        assert result.freq == "D"

    def test_intersection_bug_1708(self):
        index_1 = timedelta_range("1 day", periods=4, freq="h")
        index_2 = index_1 + pd.offsets.Hour(5)

        result = index_1.intersection(index_2)
        assert len(result) == 0

        index_1 = timedelta_range("1 day", periods=4, freq="h")
        index_2 = index_1 + pd.offsets.Hour(1)

        result = index_1.intersection(index_2)
        expected = timedelta_range("1 day 01:00:00", periods=3, freq="h")
        tm.assert_index_equal(result, expected)
        assert result.freq == expected.freq

    def test_intersection_equal(self, sort):
        # GH 24471 Test intersection outcome given the sort keyword
        # for equal indices intersection should return the original index
        first = timedelta_range("1 day", periods=4, freq="h")
        second = timedelta_range("1 day", periods=4, freq="h")
        intersect = first.intersection(second, sort=sort)
        if sort is None:
            tm.assert_index_equal(intersect, second.sort_values())
        tm.assert_index_equal(intersect, second)

        # Corner cases
        inter = first.intersection(first, sort=sort)
        assert inter is first

    @pytest.mark.parametrize("period_1, period_2", [(0, 4), (4, 0)])
    def test_intersection_zero_length(self, period_1, period_2, sort):
        # GH 24471 test for non overlap the intersection should be zero length
        index_1 = timedelta_range("1 day", periods=period_1, freq="h")
        index_2 = timedelta_range("1 day", periods=period_2, freq="h")
        expected = timedelta_range("1 day", periods=0, freq="h")
        result = index_1.intersection(index_2, sort=sort)
        tm.assert_index_equal(result, expected)

    def test_zero_length_input_index(self, sort):
        # GH 24966 test for 0-len intersections are copied
        index_1 = timedelta_range("1 day", periods=0, freq="h")
        index_2 = timedelta_range("1 day", periods=3, freq="h")
        result = index_1.intersection(index_2, sort=sort)
        assert index_1 is not result
        assert index_2 is not result
        tm.assert_copy(result, index_1)

    @pytest.mark.parametrize(
        "rng, expected",
        # if target has the same name, it is preserved
        [
            (
                timedelta_range("1 day", periods=5, freq="h", name="idx"),
                timedelta_range("1 day", periods=4, freq="h", name="idx"),
            ),
            # if target name is different, it will be reset
            (
                timedelta_range("1 day", periods=5, freq="h", name="other"),
                timedelta_range("1 day", periods=4, freq="h", name=None),
            ),
            # if no overlap exists return empty index
            (
                timedelta_range("1 day", periods=10, freq="h", name="idx")[5:],
                TimedeltaIndex([], freq="h", name="idx"),
            ),
        ],
    )
    def test_intersection(self, rng, expected, sort):
        # GH 4690 (with tz)
        base = timedelta_range("1 day", periods=4, freq="h", name="idx")
        result = base.intersection(rng, sort=sort)
        if sort is None:
            expected = expected.sort_values()
        tm.assert_index_equal(result, expected)
        assert result.name == expected.name
        assert result.freq == expected.freq

    @pytest.mark.parametrize(
        "rng, expected",
        # part intersection works
        [
            (
                TimedeltaIndex(["5 hour", "2 hour", "4 hour", "9 hour"], name="idx"),
                TimedeltaIndex(["2 hour", "4 hour"], name="idx"),
            ),
            # reordered part intersection
            (
                TimedeltaIndex(["2 hour", "5 hour", "5 hour", "1 hour"], name="other"),
                TimedeltaIndex(["1 hour", "2 hour"], name=None),
            ),
            # reversed index
            (
                TimedeltaIndex(["1 hour", "2 hour", "4 hour", "3 hour"], name="idx")[
                    ::-1
                ],
                TimedeltaIndex(["1 hour", "2 hour", "4 hour", "3 hour"], name="idx"),
            ),
        ],
    )
    def test_intersection_non_monotonic(self, rng, expected, sort):
        # 24471 non-monotonic
        base = TimedeltaIndex(["1 hour", "2 hour", "4 hour", "3 hour"], name="idx")
        result = base.intersection(rng, sort=sort)
        if sort is None:
            expected = expected.sort_values()
        tm.assert_index_equal(result, expected)
        assert result.name == expected.name

        # if reversed order, frequency is still the same
        if all(base == rng[::-1]) and sort is None:
            assert isinstance(result.freq, Hour)
        else:
            assert result.freq is None


class TestTimedeltaIndexDifference:
    def test_difference_freq(self, sort):
        # GH14323: Difference of TimedeltaIndex should not preserve frequency

        index = timedelta_range("0 days", "5 days", freq="D")

        other = timedelta_range("1 days", "4 days", freq="D")
        expected = TimedeltaIndex(["0 days", "5 days"], freq=None)
        idx_diff = index.difference(other, sort)
        tm.assert_index_equal(idx_diff, expected)
        tm.assert_attr_equal("freq", idx_diff, expected)

        # preserve frequency when the difference is a contiguous
        # subset of the original range
        other = timedelta_range("2 days", "5 days", freq="D")
        idx_diff = index.difference(other, sort)
        expected = TimedeltaIndex(["0 days", "1 days"], freq="D")
        tm.assert_index_equal(idx_diff, expected)
        tm.assert_attr_equal("freq", idx_diff, expected)

    def test_difference_sort(self, sort):
        index = TimedeltaIndex(
            ["5 days", "3 days", "2 days", "4 days", "1 days", "0 days"]
        )

        other = timedelta_range("1 days", "4 days", freq="D")
        idx_diff = index.difference(other, sort)

        expected = TimedeltaIndex(["5 days", "0 days"], freq=None)

        if sort is None:
            expected = expected.sort_values()

        tm.assert_index_equal(idx_diff, expected)
        tm.assert_attr_equal("freq", idx_diff, expected)

        other = timedelta_range("2 days", "5 days", freq="D")
        idx_diff = index.difference(other, sort)
        expected = TimedeltaIndex(["1 days", "0 days"], freq=None)

        if sort is None:
            expected = expected.sort_values()

        tm.assert_index_equal(idx_diff, expected)
        tm.assert_attr_equal("freq", idx_diff, expected)
