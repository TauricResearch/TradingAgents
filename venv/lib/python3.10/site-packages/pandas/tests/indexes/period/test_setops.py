import numpy as np
import pytest

import pandas as pd
from pandas import (
    PeriodIndex,
    date_range,
    period_range,
)
import pandas._testing as tm


def _permute(obj):
    return obj.take(np.random.default_rng(2).permutation(len(obj)))


class TestPeriodIndex:
    def test_union(self, sort):
        # union
        other1 = period_range("1/1/2000", freq="D", periods=5)
        rng1 = period_range("1/6/2000", freq="D", periods=5)
        expected1 = PeriodIndex(
            [
                "2000-01-06",
                "2000-01-07",
                "2000-01-08",
                "2000-01-09",
                "2000-01-10",
                "2000-01-01",
                "2000-01-02",
                "2000-01-03",
                "2000-01-04",
                "2000-01-05",
            ],
            freq="D",
        )

        rng2 = period_range("1/1/2000", freq="D", periods=5)
        other2 = period_range("1/4/2000", freq="D", periods=5)
        expected2 = period_range("1/1/2000", freq="D", periods=8)

        rng3 = period_range("1/1/2000", freq="D", periods=5)
        other3 = PeriodIndex([], freq="D")
        expected3 = period_range("1/1/2000", freq="D", periods=5)

        rng4 = period_range("2000-01-01 09:00", freq="h", periods=5)
        other4 = period_range("2000-01-02 09:00", freq="h", periods=5)
        expected4 = PeriodIndex(
            [
                "2000-01-01 09:00",
                "2000-01-01 10:00",
                "2000-01-01 11:00",
                "2000-01-01 12:00",
                "2000-01-01 13:00",
                "2000-01-02 09:00",
                "2000-01-02 10:00",
                "2000-01-02 11:00",
                "2000-01-02 12:00",
                "2000-01-02 13:00",
            ],
            freq="h",
        )

        rng5 = PeriodIndex(
            ["2000-01-01 09:01", "2000-01-01 09:03", "2000-01-01 09:05"], freq="min"
        )
        other5 = PeriodIndex(
            ["2000-01-01 09:01", "2000-01-01 09:05", "2000-01-01 09:08"], freq="min"
        )
        expected5 = PeriodIndex(
            [
                "2000-01-01 09:01",
                "2000-01-01 09:03",
                "2000-01-01 09:05",
                "2000-01-01 09:08",
            ],
            freq="min",
        )

        rng6 = period_range("2000-01-01", freq="M", periods=7)
        other6 = period_range("2000-04-01", freq="M", periods=7)
        expected6 = period_range("2000-01-01", freq="M", periods=10)

        rng7 = period_range("2003-01-01", freq="Y", periods=5)
        other7 = period_range("1998-01-01", freq="Y", periods=8)
        expected7 = PeriodIndex(
            [
                "2003",
                "2004",
                "2005",
                "2006",
                "2007",
                "1998",
                "1999",
                "2000",
                "2001",
                "2002",
            ],
            freq="Y",
        )

        rng8 = PeriodIndex(
            ["1/3/2000", "1/2/2000", "1/1/2000", "1/5/2000", "1/4/2000"], freq="D"
        )
        other8 = period_range("1/6/2000", freq="D", periods=5)
        expected8 = PeriodIndex(
            [
                "1/3/2000",
                "1/2/2000",
                "1/1/2000",
                "1/5/2000",
                "1/4/2000",
                "1/6/2000",
                "1/7/2000",
                "1/8/2000",
                "1/9/2000",
                "1/10/2000",
            ],
            freq="D",
        )

        for rng, other, expected in [
            (rng1, other1, expected1),
            (rng2, other2, expected2),
            (rng3, other3, expected3),
            (rng4, other4, expected4),
            (rng5, other5, expected5),
            (rng6, other6, expected6),
            (rng7, other7, expected7),
            (rng8, other8, expected8),
        ]:
            result_union = rng.union(other, sort=sort)
            if sort is None:
                expected = expected.sort_values()
            tm.assert_index_equal(result_union, expected)

    def test_union_misc(self, sort):
        index = period_range("1/1/2000", "1/20/2000", freq="D")

        result = index[:-5].union(index[10:], sort=sort)
        tm.assert_index_equal(result, index)

        # not in order
        result = _permute(index[:-5]).union(_permute(index[10:]), sort=sort)
        if sort is False:
            tm.assert_index_equal(result.sort_values(), index)
        else:
            tm.assert_index_equal(result, index)

        # cast if different frequencies
        index = period_range("1/1/2000", "1/20/2000", freq="D")
        index2 = period_range("1/1/2000", "1/20/2000", freq="W-WED")
        result = index.union(index2, sort=sort)
        expected = index.astype(object).union(index2.astype(object), sort=sort)
        tm.assert_index_equal(result, expected)

    def test_intersection(self, sort):
        index = period_range("1/1/2000", "1/20/2000", freq="D")

        result = index[:-5].intersection(index[10:], sort=sort)
        tm.assert_index_equal(result, index[10:-5])

        # not in order
        left = _permute(index[:-5])
        right = _permute(index[10:])
        result = left.intersection(right, sort=sort)
        if sort is False:
            tm.assert_index_equal(result.sort_values(), index[10:-5])
        else:
            tm.assert_index_equal(result, index[10:-5])

        # cast if different frequencies
        index = period_range("1/1/2000", "1/20/2000", freq="D")
        index2 = period_range("1/1/2000", "1/20/2000", freq="W-WED")

        result = index.intersection(index2, sort=sort)
        expected = pd.Index([], dtype=object)
        tm.assert_index_equal(result, expected)

        index3 = period_range("1/1/2000", "1/20/2000", freq="2D")
        result = index.intersection(index3, sort=sort)
        tm.assert_index_equal(result, expected)

    def test_intersection_cases(self, sort):
        base = period_range("6/1/2000", "6/30/2000", freq="D", name="idx")

        # if target has the same name, it is preserved
        rng2 = period_range("5/15/2000", "6/20/2000", freq="D", name="idx")
        expected2 = period_range("6/1/2000", "6/20/2000", freq="D", name="idx")

        # if target name is different, it will be reset
        rng3 = period_range("5/15/2000", "6/20/2000", freq="D", name="other")
        expected3 = period_range("6/1/2000", "6/20/2000", freq="D", name=None)

        rng4 = period_range("7/1/2000", "7/31/2000", freq="D", name="idx")
        expected4 = PeriodIndex([], name="idx", freq="D")

        for rng, expected in [
            (rng2, expected2),
            (rng3, expected3),
            (rng4, expected4),
        ]:
            result = base.intersection(rng, sort=sort)
            tm.assert_index_equal(result, expected)
            assert result.name == expected.name
            assert result.freq == expected.freq

        # non-monotonic
        base = PeriodIndex(
            ["2011-01-05", "2011-01-04", "2011-01-02", "2011-01-03"],
            freq="D",
            name="idx",
        )

        rng2 = PeriodIndex(
            ["2011-01-04", "2011-01-02", "2011-02-02", "2011-02-03"],
            freq="D",
            name="idx",
        )
        expected2 = PeriodIndex(["2011-01-04", "2011-01-02"], freq="D", name="idx")

        rng3 = PeriodIndex(
            ["2011-01-04", "2011-01-02", "2011-02-02", "2011-02-03"],
            freq="D",
            name="other",
        )
        expected3 = PeriodIndex(["2011-01-04", "2011-01-02"], freq="D", name=None)

        rng4 = period_range("7/1/2000", "7/31/2000", freq="D", name="idx")
        expected4 = PeriodIndex([], freq="D", name="idx")

        for rng, expected in [
            (rng2, expected2),
            (rng3, expected3),
            (rng4, expected4),
        ]:
            result = base.intersection(rng, sort=sort)
            if sort is None:
                expected = expected.sort_values()
            tm.assert_index_equal(result, expected)
            assert result.name == expected.name
            assert result.freq == "D"

        # empty same freq
        rng = date_range("6/1/2000", "6/15/2000", freq="min")
        result = rng[0:0].intersection(rng)
        assert len(result) == 0

        result = rng.intersection(rng[0:0])
        assert len(result) == 0

    def test_difference(self, sort):
        # diff
        period_rng = ["1/3/2000", "1/2/2000", "1/1/2000", "1/5/2000", "1/4/2000"]
        rng1 = PeriodIndex(period_rng, freq="D")
        other1 = period_range("1/6/2000", freq="D", periods=5)
        expected1 = rng1

        rng2 = PeriodIndex(period_rng, freq="D")
        other2 = period_range("1/4/2000", freq="D", periods=5)
        expected2 = PeriodIndex(["1/3/2000", "1/2/2000", "1/1/2000"], freq="D")

        rng3 = PeriodIndex(period_rng, freq="D")
        other3 = PeriodIndex([], freq="D")
        expected3 = rng3

        period_rng = [
            "2000-01-01 10:00",
            "2000-01-01 09:00",
            "2000-01-01 12:00",
            "2000-01-01 11:00",
            "2000-01-01 13:00",
        ]
        rng4 = PeriodIndex(period_rng, freq="h")
        other4 = period_range("2000-01-02 09:00", freq="h", periods=5)
        expected4 = rng4

        rng5 = PeriodIndex(
            ["2000-01-01 09:03", "2000-01-01 09:01", "2000-01-01 09:05"], freq="min"
        )
        other5 = PeriodIndex(["2000-01-01 09:01", "2000-01-01 09:05"], freq="min")
        expected5 = PeriodIndex(["2000-01-01 09:03"], freq="min")

        period_rng = [
            "2000-02-01",
            "2000-01-01",
            "2000-06-01",
            "2000-07-01",
            "2000-05-01",
            "2000-03-01",
            "2000-04-01",
        ]
        rng6 = PeriodIndex(period_rng, freq="M")
        other6 = period_range("2000-04-01", freq="M", periods=7)
        expected6 = PeriodIndex(["2000-02-01", "2000-01-01", "2000-03-01"], freq="M")

        period_rng = ["2003", "2007", "2006", "2005", "2004"]
        rng7 = PeriodIndex(period_rng, freq="Y")
        other7 = period_range("1998-01-01", freq="Y", periods=8)
        expected7 = PeriodIndex(["2007", "2006"], freq="Y")

        for rng, other, expected in [
            (rng1, other1, expected1),
            (rng2, other2, expected2),
            (rng3, other3, expected3),
            (rng4, other4, expected4),
            (rng5, other5, expected5),
            (rng6, other6, expected6),
            (rng7, other7, expected7),
        ]:
            result_difference = rng.difference(other, sort=sort)
            if sort is None and len(other):
                # We dont sort (yet?) when empty GH#24959
                expected = expected.sort_values()
            tm.assert_index_equal(result_difference, expected)

    def test_difference_freq(self, sort):
        # GH14323: difference of Period MUST preserve frequency
        # but the ability to union results must be preserved

        index = period_range("20160920", "20160925", freq="D")

        other = period_range("20160921", "20160924", freq="D")
        expected = PeriodIndex(["20160920", "20160925"], freq="D")
        idx_diff = index.difference(other, sort)
        tm.assert_index_equal(idx_diff, expected)
        tm.assert_attr_equal("freq", idx_diff, expected)

        other = period_range("20160922", "20160925", freq="D")
        idx_diff = index.difference(other, sort)
        expected = PeriodIndex(["20160920", "20160921"], freq="D")
        tm.assert_index_equal(idx_diff, expected)
        tm.assert_attr_equal("freq", idx_diff, expected)

    def test_intersection_equal_duplicates(self):
        # GH#38302
        idx = period_range("2011-01-01", periods=2)
        idx_dup = idx.append(idx)
        result = idx_dup.intersection(idx_dup)
        tm.assert_index_equal(result, idx)

    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_union_duplicates(self):
        # GH#36289
        idx = period_range("2011-01-01", periods=2)
        idx_dup = idx.append(idx)

        idx2 = period_range("2011-01-02", periods=2)
        idx2_dup = idx2.append(idx2)
        result = idx_dup.union(idx2_dup)

        expected = PeriodIndex(
            [
                "2011-01-01",
                "2011-01-01",
                "2011-01-02",
                "2011-01-02",
                "2011-01-03",
                "2011-01-03",
            ],
            freq="D",
        )
        tm.assert_index_equal(result, expected)
