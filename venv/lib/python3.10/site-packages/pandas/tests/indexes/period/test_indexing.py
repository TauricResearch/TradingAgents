from datetime import datetime
import re

import numpy as np
import pytest

from pandas._libs.tslibs import period as libperiod
from pandas.errors import InvalidIndexError

import pandas as pd
from pandas import (
    DatetimeIndex,
    NaT,
    Period,
    PeriodIndex,
    Series,
    Timedelta,
    date_range,
    notna,
    period_range,
)
import pandas._testing as tm

dti4 = date_range("2016-01-01", periods=4)
dti = dti4[:-1]
rng = pd.Index(range(3))


@pytest.fixture(
    params=[
        dti,
        dti.tz_localize("UTC"),
        dti.to_period("W"),
        dti - dti[0],
        rng,
        pd.Index([1, 2, 3]),
        pd.Index([2.0, 3.0, 4.0]),
        pd.Index([4, 5, 6], dtype="u8"),
        pd.IntervalIndex.from_breaks(dti4),
    ]
)
def non_comparable_idx(request):
    # All have length 3
    return request.param


class TestGetItem:
    def test_getitem_slice_keeps_name(self):
        idx = period_range("20010101", periods=10, freq="D", name="bob")
        assert idx.name == idx[1:].name

    def test_getitem(self):
        idx1 = period_range("2011-01-01", "2011-01-31", freq="D", name="idx")

        for idx in [idx1]:
            result = idx[0]
            assert result == Period("2011-01-01", freq="D")

            result = idx[-1]
            assert result == Period("2011-01-31", freq="D")

            result = idx[0:5]
            expected = period_range("2011-01-01", "2011-01-05", freq="D", name="idx")
            tm.assert_index_equal(result, expected)
            assert result.freq == expected.freq
            assert result.freq == "D"

            result = idx[0:10:2]
            expected = PeriodIndex(
                ["2011-01-01", "2011-01-03", "2011-01-05", "2011-01-07", "2011-01-09"],
                freq="D",
                name="idx",
            )
            tm.assert_index_equal(result, expected)
            assert result.freq == expected.freq
            assert result.freq == "D"

            result = idx[-20:-5:3]
            expected = PeriodIndex(
                ["2011-01-12", "2011-01-15", "2011-01-18", "2011-01-21", "2011-01-24"],
                freq="D",
                name="idx",
            )
            tm.assert_index_equal(result, expected)
            assert result.freq == expected.freq
            assert result.freq == "D"

            result = idx[4::-1]
            expected = PeriodIndex(
                ["2011-01-05", "2011-01-04", "2011-01-03", "2011-01-02", "2011-01-01"],
                freq="D",
                name="idx",
            )
            tm.assert_index_equal(result, expected)
            assert result.freq == expected.freq
            assert result.freq == "D"

    def test_getitem_index(self):
        idx = period_range("2007-01", periods=10, freq="M", name="x")

        result = idx[[1, 3, 5]]
        exp = PeriodIndex(["2007-02", "2007-04", "2007-06"], freq="M", name="x")
        tm.assert_index_equal(result, exp)

        result = idx[[True, True, False, False, False, True, True, False, False, False]]
        exp = PeriodIndex(
            ["2007-01", "2007-02", "2007-06", "2007-07"], freq="M", name="x"
        )
        tm.assert_index_equal(result, exp)

    def test_getitem_partial(self):
        rng = period_range("2007-01", periods=50, freq="M")
        ts = Series(np.random.default_rng(2).standard_normal(len(rng)), rng)

        with pytest.raises(KeyError, match=r"^'2006'$"):
            ts["2006"]

        result = ts["2008"]
        assert (result.index.year == 2008).all()

        result = ts["2008":"2009"]
        assert len(result) == 24

        result = ts["2008-1":"2009-12"]
        assert len(result) == 24

        result = ts["2008Q1":"2009Q4"]
        assert len(result) == 24

        result = ts[:"2009"]
        assert len(result) == 36

        result = ts["2009":]
        assert len(result) == 50 - 24

        exp = result
        result = ts[24:]
        tm.assert_series_equal(exp, result)

        ts = pd.concat([ts[10:], ts[10:]])
        msg = "left slice bound for non-unique label: '2008'"
        with pytest.raises(KeyError, match=msg):
            ts[slice("2008", "2009")]

    def test_getitem_datetime(self):
        rng = period_range(start="2012-01-01", periods=10, freq="W-MON")
        ts = Series(range(len(rng)), index=rng)

        dt1 = datetime(2011, 10, 2)
        dt4 = datetime(2012, 4, 20)

        rs = ts[dt1:dt4]
        tm.assert_series_equal(rs, ts)

    def test_getitem_nat(self):
        idx = PeriodIndex(["2011-01", "NaT", "2011-02"], freq="M")
        assert idx[0] == Period("2011-01", freq="M")
        assert idx[1] is NaT

        s = Series([0, 1, 2], index=idx)
        assert s[NaT] == 1

        s = Series(idx, index=idx)
        assert s[Period("2011-01", freq="M")] == Period("2011-01", freq="M")
        assert s[NaT] is NaT

    def test_getitem_list_periods(self):
        # GH 7710
        rng = period_range(start="2012-01-01", periods=10, freq="D")
        ts = Series(range(len(rng)), index=rng)
        exp = ts.iloc[[1]]
        tm.assert_series_equal(ts[[Period("2012-01-02", freq="D")]], exp)

    @pytest.mark.arm_slow
    def test_getitem_seconds(self):
        # GH#6716
        didx = date_range(start="2013/01/01 09:00:00", freq="s", periods=4000)
        pidx = period_range(start="2013/01/01 09:00:00", freq="s", periods=4000)

        for idx in [didx, pidx]:
            # getitem against index should raise ValueError
            values = [
                "2014",
                "2013/02",
                "2013/01/02",
                "2013/02/01 9h",
                "2013/02/01 09:00",
            ]
            for val in values:
                # GH7116
                # these show deprecations as we are trying
                # to slice with non-integer indexers
                with pytest.raises(IndexError, match="only integers, slices"):
                    idx[val]

            ser = Series(np.random.default_rng(2).random(len(idx)), index=idx)
            tm.assert_series_equal(ser["2013/01/01 10:00"], ser[3600:3660])
            tm.assert_series_equal(ser["2013/01/01 9h"], ser[:3600])
            for d in ["2013/01/01", "2013/01", "2013"]:
                tm.assert_series_equal(ser[d], ser)

    @pytest.mark.parametrize(
        "idx_range",
        [
            date_range,
            period_range,
        ],
    )
    def test_getitem_day(self, idx_range):
        # GH#6716
        # Confirm DatetimeIndex and PeriodIndex works identically
        # getitem against index should raise ValueError
        idx = idx_range(start="2013/01/01", freq="D", periods=400)
        values = [
            "2014",
            "2013/02",
            "2013/01/02",
            "2013/02/01 9h",
            "2013/02/01 09:00",
        ]
        for val in values:
            # GH7116
            # these show deprecations as we are trying
            # to slice with non-integer indexers
            with pytest.raises(IndexError, match="only integers, slices"):
                idx[val]

        ser = Series(np.random.default_rng(2).random(len(idx)), index=idx)
        tm.assert_series_equal(ser["2013/01"], ser[0:31])
        tm.assert_series_equal(ser["2013/02"], ser[31:59])
        tm.assert_series_equal(ser["2014"], ser[365:])

        invalid = ["2013/02/01 9h", "2013/02/01 09:00"]
        for val in invalid:
            with pytest.raises(KeyError, match=val):
                ser[val]


class TestGetLoc:
    def test_get_loc_msg(self):
        idx = period_range("2000-1-1", freq="Y", periods=10)
        bad_period = Period("2012", "Y")
        with pytest.raises(KeyError, match=r"^Period\('2012', 'Y-DEC'\)$"):
            idx.get_loc(bad_period)

        try:
            idx.get_loc(bad_period)
        except KeyError as inst:
            assert inst.args[0] == bad_period

    def test_get_loc_nat(self):
        didx = DatetimeIndex(["2011-01-01", "NaT", "2011-01-03"])
        pidx = PeriodIndex(["2011-01-01", "NaT", "2011-01-03"], freq="M")

        # check DatetimeIndex compat
        for idx in [didx, pidx]:
            assert idx.get_loc(NaT) == 1
            assert idx.get_loc(None) == 1
            assert idx.get_loc(float("nan")) == 1
            assert idx.get_loc(np.nan) == 1

    def test_get_loc(self):
        # GH 17717
        p0 = Period("2017-09-01")
        p1 = Period("2017-09-02")
        p2 = Period("2017-09-03")

        # get the location of p1/p2 from
        # monotonic increasing PeriodIndex with non-duplicate
        idx0 = PeriodIndex([p0, p1, p2])
        expected_idx1_p1 = 1
        expected_idx1_p2 = 2

        assert idx0.get_loc(p1) == expected_idx1_p1
        assert idx0.get_loc(str(p1)) == expected_idx1_p1
        assert idx0.get_loc(p2) == expected_idx1_p2
        assert idx0.get_loc(str(p2)) == expected_idx1_p2

        msg = "Cannot interpret 'foo' as period"
        with pytest.raises(KeyError, match=msg):
            idx0.get_loc("foo")
        with pytest.raises(KeyError, match=r"^1\.1$"):
            idx0.get_loc(1.1)

        with pytest.raises(InvalidIndexError, match=re.escape(str(idx0))):
            idx0.get_loc(idx0)

        # get the location of p1/p2 from
        # monotonic increasing PeriodIndex with duplicate
        idx1 = PeriodIndex([p1, p1, p2])
        expected_idx1_p1 = slice(0, 2)
        expected_idx1_p2 = 2

        assert idx1.get_loc(p1) == expected_idx1_p1
        assert idx1.get_loc(str(p1)) == expected_idx1_p1
        assert idx1.get_loc(p2) == expected_idx1_p2
        assert idx1.get_loc(str(p2)) == expected_idx1_p2

        msg = "Cannot interpret 'foo' as period"
        with pytest.raises(KeyError, match=msg):
            idx1.get_loc("foo")

        with pytest.raises(KeyError, match=r"^1\.1$"):
            idx1.get_loc(1.1)

        with pytest.raises(InvalidIndexError, match=re.escape(str(idx1))):
            idx1.get_loc(idx1)

        # get the location of p1/p2 from
        # non-monotonic increasing/decreasing PeriodIndex with duplicate
        idx2 = PeriodIndex([p2, p1, p2])
        expected_idx2_p1 = 1
        expected_idx2_p2 = np.array([True, False, True])

        assert idx2.get_loc(p1) == expected_idx2_p1
        assert idx2.get_loc(str(p1)) == expected_idx2_p1
        tm.assert_numpy_array_equal(idx2.get_loc(p2), expected_idx2_p2)
        tm.assert_numpy_array_equal(idx2.get_loc(str(p2)), expected_idx2_p2)

    def test_get_loc_integer(self):
        dti = date_range("2016-01-01", periods=3)
        pi = dti.to_period("D")
        with pytest.raises(KeyError, match="16801"):
            pi.get_loc(16801)

        pi2 = dti.to_period("Y")  # duplicates, ordinals are all 46
        with pytest.raises(KeyError, match="46"):
            pi2.get_loc(46)

    def test_get_loc_invalid_string_raises_keyerror(self):
        # GH#34240
        pi = period_range("2000", periods=3, name="A")
        with pytest.raises(KeyError, match="A"):
            pi.get_loc("A")

        ser = Series([1, 2, 3], index=pi)
        with pytest.raises(KeyError, match="A"):
            ser.loc["A"]

        with pytest.raises(KeyError, match="A"):
            ser["A"]

        assert "A" not in ser
        assert "A" not in pi

    def test_get_loc_mismatched_freq(self):
        # see also test_get_indexer_mismatched_dtype testing we get analogous
        # behavior for get_loc
        dti = date_range("2016-01-01", periods=3)
        pi = dti.to_period("D")
        pi2 = dti.to_period("W")
        pi3 = pi.view(pi2.dtype)  # i.e. matching i8 representations

        with pytest.raises(KeyError, match="W-SUN"):
            pi.get_loc(pi2[0])

        with pytest.raises(KeyError, match="W-SUN"):
            # even though we have matching i8 values
            pi.get_loc(pi3[0])


class TestGetIndexer:
    def test_get_indexer(self):
        # GH 17717
        p1 = Period("2017-09-01")
        p2 = Period("2017-09-04")
        p3 = Period("2017-09-07")

        tp0 = Period("2017-08-31")
        tp1 = Period("2017-09-02")
        tp2 = Period("2017-09-05")
        tp3 = Period("2017-09-09")

        idx = PeriodIndex([p1, p2, p3])

        tm.assert_numpy_array_equal(
            idx.get_indexer(idx), np.array([0, 1, 2], dtype=np.intp)
        )

        target = PeriodIndex([tp0, tp1, tp2, tp3])
        tm.assert_numpy_array_equal(
            idx.get_indexer(target, "pad"), np.array([-1, 0, 1, 2], dtype=np.intp)
        )
        tm.assert_numpy_array_equal(
            idx.get_indexer(target, "backfill"), np.array([0, 1, 2, -1], dtype=np.intp)
        )
        tm.assert_numpy_array_equal(
            idx.get_indexer(target, "nearest"), np.array([0, 0, 1, 2], dtype=np.intp)
        )

        res = idx.get_indexer(target, "nearest", tolerance=Timedelta("1 day"))
        tm.assert_numpy_array_equal(res, np.array([0, 0, 1, -1], dtype=np.intp))

    def test_get_indexer_mismatched_dtype(self):
        # Check that we return all -1s and do not raise or cast incorrectly

        dti = date_range("2016-01-01", periods=3)
        pi = dti.to_period("D")
        pi2 = dti.to_period("W")

        expected = np.array([-1, -1, -1], dtype=np.intp)

        result = pi.get_indexer(dti)
        tm.assert_numpy_array_equal(result, expected)

        # This should work in both directions
        result = dti.get_indexer(pi)
        tm.assert_numpy_array_equal(result, expected)

        result = pi.get_indexer(pi2)
        tm.assert_numpy_array_equal(result, expected)

        # We expect the same from get_indexer_non_unique
        result = pi.get_indexer_non_unique(dti)[0]
        tm.assert_numpy_array_equal(result, expected)

        result = dti.get_indexer_non_unique(pi)[0]
        tm.assert_numpy_array_equal(result, expected)

        result = pi.get_indexer_non_unique(pi2)[0]
        tm.assert_numpy_array_equal(result, expected)

    def test_get_indexer_mismatched_dtype_different_length(self, non_comparable_idx):
        # without method we aren't checking inequalities, so get all-missing
        #  but do not raise
        dti = date_range("2016-01-01", periods=3)
        pi = dti.to_period("D")

        other = non_comparable_idx

        res = pi[:-1].get_indexer(other)
        expected = -np.ones(other.shape, dtype=np.intp)
        tm.assert_numpy_array_equal(res, expected)

    @pytest.mark.parametrize("method", ["pad", "backfill", "nearest"])
    def test_get_indexer_mismatched_dtype_with_method(self, non_comparable_idx, method):
        dti = date_range("2016-01-01", periods=3)
        pi = dti.to_period("D")

        other = non_comparable_idx

        msg = re.escape(f"Cannot compare dtypes {pi.dtype} and {other.dtype}")
        with pytest.raises(TypeError, match=msg):
            pi.get_indexer(other, method=method)

        for dtype in ["object", "category"]:
            other2 = other.astype(dtype)
            if dtype == "object" and isinstance(other, PeriodIndex):
                continue
            # Two different error message patterns depending on dtypes
            msg = "|".join(
                [
                    re.escape(msg)
                    for msg in (
                        f"Cannot compare dtypes {pi.dtype} and {other.dtype}",
                        " not supported between instances of ",
                    )
                ]
            )
            with pytest.raises(TypeError, match=msg):
                pi.get_indexer(other2, method=method)

    def test_get_indexer_non_unique(self):
        # GH 17717
        p1 = Period("2017-09-02")
        p2 = Period("2017-09-03")
        p3 = Period("2017-09-04")
        p4 = Period("2017-09-05")

        idx1 = PeriodIndex([p1, p2, p1])
        idx2 = PeriodIndex([p2, p1, p3, p4])

        result = idx1.get_indexer_non_unique(idx2)
        expected_indexer = np.array([1, 0, 2, -1, -1], dtype=np.intp)
        expected_missing = np.array([2, 3], dtype=np.intp)

        tm.assert_numpy_array_equal(result[0], expected_indexer)
        tm.assert_numpy_array_equal(result[1], expected_missing)

    # TODO: This method came from test_period; de-dup with version above
    def test_get_indexer2(self):
        idx = period_range("2000-01-01", periods=3).asfreq("h", how="start")
        tm.assert_numpy_array_equal(
            idx.get_indexer(idx), np.array([0, 1, 2], dtype=np.intp)
        )

        target = PeriodIndex(
            ["1999-12-31T23", "2000-01-01T12", "2000-01-02T01"], freq="h"
        )
        tm.assert_numpy_array_equal(
            idx.get_indexer(target, "pad"), np.array([-1, 0, 1], dtype=np.intp)
        )
        tm.assert_numpy_array_equal(
            idx.get_indexer(target, "backfill"), np.array([0, 1, 2], dtype=np.intp)
        )
        tm.assert_numpy_array_equal(
            idx.get_indexer(target, "nearest"), np.array([0, 1, 1], dtype=np.intp)
        )
        tm.assert_numpy_array_equal(
            idx.get_indexer(target, "nearest", tolerance="1 hour"),
            np.array([0, -1, 1], dtype=np.intp),
        )

        msg = "Input has different freq=None from PeriodArray\\(freq=h\\)"
        with pytest.raises(ValueError, match=msg):
            idx.get_indexer(target, "nearest", tolerance="1 minute")

        tm.assert_numpy_array_equal(
            idx.get_indexer(target, "nearest", tolerance="1 day"),
            np.array([0, 1, 1], dtype=np.intp),
        )
        tol_raw = [
            Timedelta("1 hour"),
            Timedelta("1 hour"),
            np.timedelta64(1, "D"),
        ]
        tm.assert_numpy_array_equal(
            idx.get_indexer(
                target, "nearest", tolerance=[np.timedelta64(x) for x in tol_raw]
            ),
            np.array([0, -1, 1], dtype=np.intp),
        )
        tol_bad = [
            Timedelta("2 hour").to_timedelta64(),
            Timedelta("1 hour").to_timedelta64(),
            np.timedelta64(1, "M"),
        ]
        with pytest.raises(
            libperiod.IncompatibleFrequency, match="Input has different freq=None from"
        ):
            idx.get_indexer(target, "nearest", tolerance=tol_bad)


class TestWhere:
    def test_where(self, listlike_box):
        i = period_range("20130101", periods=5, freq="D")
        cond = [True] * len(i)
        expected = i
        result = i.where(listlike_box(cond))
        tm.assert_index_equal(result, expected)

        cond = [False] + [True] * (len(i) - 1)
        expected = PeriodIndex([NaT] + i[1:].tolist(), freq="D")
        result = i.where(listlike_box(cond))
        tm.assert_index_equal(result, expected)

    def test_where_other(self):
        i = period_range("20130101", periods=5, freq="D")
        for arr in [np.nan, NaT]:
            result = i.where(notna(i), other=arr)
            expected = i
            tm.assert_index_equal(result, expected)

        i2 = i.copy()
        i2 = PeriodIndex([NaT, NaT] + i[2:].tolist(), freq="D")
        result = i.where(notna(i2), i2)
        tm.assert_index_equal(result, i2)

        i2 = i.copy()
        i2 = PeriodIndex([NaT, NaT] + i[2:].tolist(), freq="D")
        result = i.where(notna(i2), i2.values)
        tm.assert_index_equal(result, i2)

    def test_where_invalid_dtypes(self):
        pi = period_range("20130101", periods=5, freq="D")

        tail = pi[2:].tolist()
        i2 = PeriodIndex([NaT, NaT] + tail, freq="D")
        mask = notna(i2)

        result = pi.where(mask, i2.asi8)
        expected = pd.Index([NaT._value, NaT._value] + tail, dtype=object)
        assert isinstance(expected[0], int)
        tm.assert_index_equal(result, expected)

        tdi = i2.asi8.view("timedelta64[ns]")
        expected = pd.Index([tdi[0], tdi[1]] + tail, dtype=object)
        assert isinstance(expected[0], np.timedelta64)
        result = pi.where(mask, tdi)
        tm.assert_index_equal(result, expected)

        dti = i2.to_timestamp("s")
        expected = pd.Index([dti[0], dti[1]] + tail, dtype=object)
        assert expected[0] is NaT
        result = pi.where(mask, dti)
        tm.assert_index_equal(result, expected)

        td = Timedelta(days=4)
        expected = pd.Index([td, td] + tail, dtype=object)
        assert expected[0] == td
        result = pi.where(mask, td)
        tm.assert_index_equal(result, expected)

    def test_where_mismatched_nat(self):
        pi = period_range("20130101", periods=5, freq="D")
        cond = np.array([True, False, True, True, False])

        tdnat = np.timedelta64("NaT", "ns")
        expected = pd.Index([pi[0], tdnat, pi[2], pi[3], tdnat], dtype=object)
        assert expected[1] is tdnat
        result = pi.where(cond, tdnat)
        tm.assert_index_equal(result, expected)


class TestTake:
    def test_take(self):
        # GH#10295
        idx1 = period_range("2011-01-01", "2011-01-31", freq="D", name="idx")

        for idx in [idx1]:
            result = idx.take([0])
            assert result == Period("2011-01-01", freq="D")

            result = idx.take([5])
            assert result == Period("2011-01-06", freq="D")

            result = idx.take([0, 1, 2])
            expected = period_range("2011-01-01", "2011-01-03", freq="D", name="idx")
            tm.assert_index_equal(result, expected)
            assert result.freq == "D"
            assert result.freq == expected.freq

            result = idx.take([0, 2, 4])
            expected = PeriodIndex(
                ["2011-01-01", "2011-01-03", "2011-01-05"], freq="D", name="idx"
            )
            tm.assert_index_equal(result, expected)
            assert result.freq == expected.freq
            assert result.freq == "D"

            result = idx.take([7, 4, 1])
            expected = PeriodIndex(
                ["2011-01-08", "2011-01-05", "2011-01-02"], freq="D", name="idx"
            )
            tm.assert_index_equal(result, expected)
            assert result.freq == expected.freq
            assert result.freq == "D"

            result = idx.take([3, 2, 5])
            expected = PeriodIndex(
                ["2011-01-04", "2011-01-03", "2011-01-06"], freq="D", name="idx"
            )
            tm.assert_index_equal(result, expected)
            assert result.freq == expected.freq
            assert result.freq == "D"

            result = idx.take([-3, 2, 5])
            expected = PeriodIndex(
                ["2011-01-29", "2011-01-03", "2011-01-06"], freq="D", name="idx"
            )
            tm.assert_index_equal(result, expected)
            assert result.freq == expected.freq
            assert result.freq == "D"

    def test_take_misc(self):
        index = period_range(start="1/1/10", end="12/31/12", freq="D", name="idx")
        expected = PeriodIndex(
            [
                datetime(2010, 1, 6),
                datetime(2010, 1, 7),
                datetime(2010, 1, 9),
                datetime(2010, 1, 13),
            ],
            freq="D",
            name="idx",
        )

        taken1 = index.take([5, 6, 8, 12])
        taken2 = index[[5, 6, 8, 12]]

        for taken in [taken1, taken2]:
            tm.assert_index_equal(taken, expected)
            assert isinstance(taken, PeriodIndex)
            assert taken.freq == index.freq
            assert taken.name == expected.name

    def test_take_fill_value(self):
        # GH#12631
        idx = PeriodIndex(
            ["2011-01-01", "2011-02-01", "2011-03-01"], name="xxx", freq="D"
        )
        result = idx.take(np.array([1, 0, -1]))
        expected = PeriodIndex(
            ["2011-02-01", "2011-01-01", "2011-03-01"], name="xxx", freq="D"
        )
        tm.assert_index_equal(result, expected)

        # fill_value
        result = idx.take(np.array([1, 0, -1]), fill_value=True)
        expected = PeriodIndex(
            ["2011-02-01", "2011-01-01", "NaT"], name="xxx", freq="D"
        )
        tm.assert_index_equal(result, expected)

        # allow_fill=False
        result = idx.take(np.array([1, 0, -1]), allow_fill=False, fill_value=True)
        expected = PeriodIndex(
            ["2011-02-01", "2011-01-01", "2011-03-01"], name="xxx", freq="D"
        )
        tm.assert_index_equal(result, expected)

        msg = (
            "When allow_fill=True and fill_value is not None, "
            "all indices must be >= -1"
        )
        with pytest.raises(ValueError, match=msg):
            idx.take(np.array([1, 0, -2]), fill_value=True)
        with pytest.raises(ValueError, match=msg):
            idx.take(np.array([1, 0, -5]), fill_value=True)

        msg = "index -5 is out of bounds for( axis 0 with)? size 3"
        with pytest.raises(IndexError, match=msg):
            idx.take(np.array([1, -5]))


class TestGetValue:
    @pytest.mark.parametrize("freq", ["h", "D"])
    def test_get_value_datetime_hourly(self, freq):
        # get_loc and get_value should treat datetime objects symmetrically
        # TODO: this test used to test get_value, which is removed in 2.0.
        #  should this test be moved somewhere, or is what's left redundant?
        dti = date_range("2016-01-01", periods=3, freq="MS")
        pi = dti.to_period(freq)
        ser = Series(range(7, 10), index=pi)

        ts = dti[0]

        assert pi.get_loc(ts) == 0
        assert ser[ts] == 7
        assert ser.loc[ts] == 7

        ts2 = ts + Timedelta(hours=3)
        if freq == "h":
            with pytest.raises(KeyError, match="2016-01-01 03:00"):
                pi.get_loc(ts2)
            with pytest.raises(KeyError, match="2016-01-01 03:00"):
                ser[ts2]
            with pytest.raises(KeyError, match="2016-01-01 03:00"):
                ser.loc[ts2]
        else:
            assert pi.get_loc(ts2) == 0
            assert ser[ts2] == 7
            assert ser.loc[ts2] == 7


class TestContains:
    def test_contains(self):
        # GH 17717
        p0 = Period("2017-09-01")
        p1 = Period("2017-09-02")
        p2 = Period("2017-09-03")
        p3 = Period("2017-09-04")

        ps0 = [p0, p1, p2]
        idx0 = PeriodIndex(ps0)

        for p in ps0:
            assert p in idx0
            assert str(p) in idx0

        # GH#31172
        # Higher-resolution period-like are _not_ considered as contained
        key = "2017-09-01 00:00:01"
        assert key not in idx0
        with pytest.raises(KeyError, match=key):
            idx0.get_loc(key)

        assert "2017-09" in idx0

        assert p3 not in idx0

    def test_contains_freq_mismatch(self):
        rng = period_range("2007-01", freq="M", periods=10)

        assert Period("2007-01", freq="M") in rng
        assert Period("2007-01", freq="D") not in rng
        assert Period("2007-01", freq="2M") not in rng

    def test_contains_nat(self):
        # see gh-13582
        idx = period_range("2007-01", freq="M", periods=10)
        assert NaT not in idx
        assert None not in idx
        assert float("nan") not in idx
        assert np.nan not in idx

        idx = PeriodIndex(["2011-01", "NaT", "2011-02"], freq="M")
        assert NaT in idx
        assert None in idx
        assert float("nan") in idx
        assert np.nan in idx


class TestAsOfLocs:
    def test_asof_locs_mismatched_type(self):
        dti = date_range("2016-01-01", periods=3)
        pi = dti.to_period("D")
        pi2 = dti.to_period("h")

        mask = np.array([0, 1, 0], dtype=bool)

        msg = "must be DatetimeIndex or PeriodIndex"
        with pytest.raises(TypeError, match=msg):
            pi.asof_locs(pd.Index(pi.asi8, dtype=np.int64), mask)

        with pytest.raises(TypeError, match=msg):
            pi.asof_locs(pd.Index(pi.asi8, dtype=np.float64), mask)

        with pytest.raises(TypeError, match=msg):
            # TimedeltaIndex
            pi.asof_locs(dti - dti, mask)

        msg = "Input has different freq=h"
        with pytest.raises(libperiod.IncompatibleFrequency, match=msg):
            pi.asof_locs(pi2, mask)
