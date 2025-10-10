from datetime import (
    date,
    datetime,
    time,
    timedelta,
)

import numpy as np
import pytest

from pandas._libs import index as libindex
from pandas.compat.numpy import np_long

import pandas as pd
from pandas import (
    DatetimeIndex,
    Index,
    Timestamp,
    bdate_range,
    date_range,
    notna,
)
import pandas._testing as tm

from pandas.tseries.frequencies import to_offset

START, END = datetime(2009, 1, 1), datetime(2010, 1, 1)


class TestGetItem:
    def test_getitem_slice_keeps_name(self):
        # GH4226
        st = Timestamp("2013-07-01 00:00:00", tz="America/Los_Angeles")
        et = Timestamp("2013-07-02 00:00:00", tz="America/Los_Angeles")
        dr = date_range(st, et, freq="h", name="timebucket")
        assert dr[1:].name == dr.name

    @pytest.mark.parametrize("tz", [None, "Asia/Tokyo"])
    def test_getitem(self, tz):
        idx = date_range("2011-01-01", "2011-01-31", freq="D", tz=tz, name="idx")

        result = idx[0]
        assert result == Timestamp("2011-01-01", tz=idx.tz)

        result = idx[0:5]
        expected = date_range(
            "2011-01-01", "2011-01-05", freq="D", tz=idx.tz, name="idx"
        )
        tm.assert_index_equal(result, expected)
        assert result.freq == expected.freq

        result = idx[0:10:2]
        expected = date_range(
            "2011-01-01", "2011-01-09", freq="2D", tz=idx.tz, name="idx"
        )
        tm.assert_index_equal(result, expected)
        assert result.freq == expected.freq

        result = idx[-20:-5:3]
        expected = date_range(
            "2011-01-12", "2011-01-24", freq="3D", tz=idx.tz, name="idx"
        )
        tm.assert_index_equal(result, expected)
        assert result.freq == expected.freq

        result = idx[4::-1]
        expected = DatetimeIndex(
            ["2011-01-05", "2011-01-04", "2011-01-03", "2011-01-02", "2011-01-01"],
            dtype=idx.dtype,
            freq="-1D",
            name="idx",
        )
        tm.assert_index_equal(result, expected)
        assert result.freq == expected.freq

    @pytest.mark.parametrize("freq", ["B", "C"])
    def test_dti_business_getitem(self, freq):
        rng = bdate_range(START, END, freq=freq)
        smaller = rng[:5]
        exp = DatetimeIndex(rng.view(np.ndarray)[:5], freq=freq)
        tm.assert_index_equal(smaller, exp)
        assert smaller.freq == exp.freq
        assert smaller.freq == rng.freq

        sliced = rng[::5]
        assert sliced.freq == to_offset(freq) * 5

        fancy_indexed = rng[[4, 3, 2, 1, 0]]
        assert len(fancy_indexed) == 5
        assert isinstance(fancy_indexed, DatetimeIndex)
        assert fancy_indexed.freq is None

        # 32-bit vs. 64-bit platforms
        assert rng[4] == rng[np_long(4)]

    @pytest.mark.parametrize("freq", ["B", "C"])
    def test_dti_business_getitem_matplotlib_hackaround(self, freq):
        rng = bdate_range(START, END, freq=freq)
        with pytest.raises(ValueError, match="Multi-dimensional indexing"):
            # GH#30588 multi-dimensional indexing deprecated
            rng[:, None]

    def test_getitem_int_list(self):
        dti = date_range(start="1/1/2005", end="12/1/2005", freq="ME")
        dti2 = dti[[1, 3, 5]]

        v1 = dti2[0]
        v2 = dti2[1]
        v3 = dti2[2]

        assert v1 == Timestamp("2/28/2005")
        assert v2 == Timestamp("4/30/2005")
        assert v3 == Timestamp("6/30/2005")

        # getitem with non-slice drops freq
        assert dti2.freq is None


class TestWhere:
    def test_where_doesnt_retain_freq(self):
        dti = date_range("20130101", periods=3, freq="D", name="idx")
        cond = [True, True, False]
        expected = DatetimeIndex([dti[0], dti[1], dti[0]], freq=None, name="idx")

        result = dti.where(cond, dti[::-1])
        tm.assert_index_equal(result, expected)

    def test_where_other(self):
        # other is ndarray or Index
        i = date_range("20130101", periods=3, tz="US/Eastern")

        for arr in [np.nan, pd.NaT]:
            result = i.where(notna(i), other=arr)
            expected = i
            tm.assert_index_equal(result, expected)

        i2 = i.copy()
        i2 = Index([pd.NaT, pd.NaT] + i[2:].tolist())
        result = i.where(notna(i2), i2)
        tm.assert_index_equal(result, i2)

        i2 = i.copy()
        i2 = Index([pd.NaT, pd.NaT] + i[2:].tolist())
        result = i.where(notna(i2), i2._values)
        tm.assert_index_equal(result, i2)

    def test_where_invalid_dtypes(self):
        dti = date_range("20130101", periods=3, tz="US/Eastern")

        tail = dti[2:].tolist()
        i2 = Index([pd.NaT, pd.NaT] + tail)

        mask = notna(i2)

        # passing tz-naive ndarray to tzaware DTI
        result = dti.where(mask, i2.values)
        expected = Index([pd.NaT.asm8, pd.NaT.asm8] + tail, dtype=object)
        tm.assert_index_equal(result, expected)

        # passing tz-aware DTI to tznaive DTI
        naive = dti.tz_localize(None)
        result = naive.where(mask, i2)
        expected = Index([i2[0], i2[1]] + naive[2:].tolist(), dtype=object)
        tm.assert_index_equal(result, expected)

        pi = i2.tz_localize(None).to_period("D")
        result = dti.where(mask, pi)
        expected = Index([pi[0], pi[1]] + tail, dtype=object)
        tm.assert_index_equal(result, expected)

        tda = i2.asi8.view("timedelta64[ns]")
        result = dti.where(mask, tda)
        expected = Index([tda[0], tda[1]] + tail, dtype=object)
        assert isinstance(expected[0], np.timedelta64)
        tm.assert_index_equal(result, expected)

        result = dti.where(mask, i2.asi8)
        expected = Index([pd.NaT._value, pd.NaT._value] + tail, dtype=object)
        assert isinstance(expected[0], int)
        tm.assert_index_equal(result, expected)

        # non-matching scalar
        td = pd.Timedelta(days=4)
        result = dti.where(mask, td)
        expected = Index([td, td] + tail, dtype=object)
        assert expected[0] is td
        tm.assert_index_equal(result, expected)

    def test_where_mismatched_nat(self, tz_aware_fixture):
        tz = tz_aware_fixture
        dti = date_range("2013-01-01", periods=3, tz=tz)
        cond = np.array([True, False, True])

        tdnat = np.timedelta64("NaT", "ns")
        expected = Index([dti[0], tdnat, dti[2]], dtype=object)
        assert expected[1] is tdnat

        result = dti.where(cond, tdnat)
        tm.assert_index_equal(result, expected)

    def test_where_tz(self):
        i = date_range("20130101", periods=3, tz="US/Eastern")
        result = i.where(notna(i))
        expected = i
        tm.assert_index_equal(result, expected)

        i2 = i.copy()
        i2 = Index([pd.NaT, pd.NaT] + i[2:].tolist())
        result = i.where(notna(i2))
        expected = i2
        tm.assert_index_equal(result, expected)


class TestTake:
    @pytest.mark.parametrize("tzstr", ["US/Eastern", "dateutil/US/Eastern"])
    def test_dti_take_dont_lose_meta(self, tzstr):
        rng = date_range("1/1/2000", periods=20, tz=tzstr)

        result = rng.take(range(5))
        assert result.tz == rng.tz
        assert result.freq == rng.freq

    def test_take_nan_first_datetime(self):
        index = DatetimeIndex([pd.NaT, Timestamp("20130101"), Timestamp("20130102")])
        result = index.take([-1, 0, 1])
        expected = DatetimeIndex([index[-1], index[0], index[1]])
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("tz", [None, "Asia/Tokyo"])
    def test_take(self, tz):
        # GH#10295
        idx = date_range("2011-01-01", "2011-01-31", freq="D", name="idx", tz=tz)

        result = idx.take([0])
        assert result == Timestamp("2011-01-01", tz=idx.tz)

        result = idx.take([0, 1, 2])
        expected = date_range(
            "2011-01-01", "2011-01-03", freq="D", tz=idx.tz, name="idx"
        )
        tm.assert_index_equal(result, expected)
        assert result.freq == expected.freq

        result = idx.take([0, 2, 4])
        expected = date_range(
            "2011-01-01", "2011-01-05", freq="2D", tz=idx.tz, name="idx"
        )
        tm.assert_index_equal(result, expected)
        assert result.freq == expected.freq

        result = idx.take([7, 4, 1])
        expected = date_range(
            "2011-01-08", "2011-01-02", freq="-3D", tz=idx.tz, name="idx"
        )
        tm.assert_index_equal(result, expected)
        assert result.freq == expected.freq

        result = idx.take([3, 2, 5])
        expected = DatetimeIndex(
            ["2011-01-04", "2011-01-03", "2011-01-06"],
            dtype=idx.dtype,
            freq=None,
            name="idx",
        )
        tm.assert_index_equal(result, expected)
        assert result.freq is None

        result = idx.take([-3, 2, 5])
        expected = DatetimeIndex(
            ["2011-01-29", "2011-01-03", "2011-01-06"],
            dtype=idx.dtype,
            freq=None,
            name="idx",
        )
        tm.assert_index_equal(result, expected)
        assert result.freq is None

    def test_take_invalid_kwargs(self):
        idx = date_range("2011-01-01", "2011-01-31", freq="D", name="idx")
        indices = [1, 6, 5, 9, 10, 13, 15, 3]

        msg = r"take\(\) got an unexpected keyword argument 'foo'"
        with pytest.raises(TypeError, match=msg):
            idx.take(indices, foo=2)

        msg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=msg):
            idx.take(indices, out=indices)

        msg = "the 'mode' parameter is not supported"
        with pytest.raises(ValueError, match=msg):
            idx.take(indices, mode="clip")

    # TODO: This method came from test_datetime; de-dup with version above
    @pytest.mark.parametrize("tz", [None, "US/Eastern", "Asia/Tokyo"])
    def test_take2(self, tz):
        dates = [
            datetime(2010, 1, 1, 14),
            datetime(2010, 1, 1, 15),
            datetime(2010, 1, 1, 17),
            datetime(2010, 1, 1, 21),
        ]

        idx = date_range(
            start="2010-01-01 09:00",
            end="2010-02-01 09:00",
            freq="h",
            tz=tz,
            name="idx",
        )
        expected = DatetimeIndex(dates, freq=None, name="idx", dtype=idx.dtype)

        taken1 = idx.take([5, 6, 8, 12])
        taken2 = idx[[5, 6, 8, 12]]

        for taken in [taken1, taken2]:
            tm.assert_index_equal(taken, expected)
            assert isinstance(taken, DatetimeIndex)
            assert taken.freq is None
            assert taken.tz == expected.tz
            assert taken.name == expected.name

    def test_take_fill_value(self):
        # GH#12631
        idx = DatetimeIndex(["2011-01-01", "2011-02-01", "2011-03-01"], name="xxx")
        result = idx.take(np.array([1, 0, -1]))
        expected = DatetimeIndex(["2011-02-01", "2011-01-01", "2011-03-01"], name="xxx")
        tm.assert_index_equal(result, expected)

        # fill_value
        result = idx.take(np.array([1, 0, -1]), fill_value=True)
        expected = DatetimeIndex(["2011-02-01", "2011-01-01", "NaT"], name="xxx")
        tm.assert_index_equal(result, expected)

        # allow_fill=False
        result = idx.take(np.array([1, 0, -1]), allow_fill=False, fill_value=True)
        expected = DatetimeIndex(["2011-02-01", "2011-01-01", "2011-03-01"], name="xxx")
        tm.assert_index_equal(result, expected)

        msg = (
            "When allow_fill=True and fill_value is not None, "
            "all indices must be >= -1"
        )
        with pytest.raises(ValueError, match=msg):
            idx.take(np.array([1, 0, -2]), fill_value=True)
        with pytest.raises(ValueError, match=msg):
            idx.take(np.array([1, 0, -5]), fill_value=True)

        msg = "out of bounds"
        with pytest.raises(IndexError, match=msg):
            idx.take(np.array([1, -5]))

    def test_take_fill_value_with_timezone(self):
        idx = DatetimeIndex(
            ["2011-01-01", "2011-02-01", "2011-03-01"], name="xxx", tz="US/Eastern"
        )
        result = idx.take(np.array([1, 0, -1]))
        expected = DatetimeIndex(
            ["2011-02-01", "2011-01-01", "2011-03-01"], name="xxx", tz="US/Eastern"
        )
        tm.assert_index_equal(result, expected)

        # fill_value
        result = idx.take(np.array([1, 0, -1]), fill_value=True)
        expected = DatetimeIndex(
            ["2011-02-01", "2011-01-01", "NaT"], name="xxx", tz="US/Eastern"
        )
        tm.assert_index_equal(result, expected)

        # allow_fill=False
        result = idx.take(np.array([1, 0, -1]), allow_fill=False, fill_value=True)
        expected = DatetimeIndex(
            ["2011-02-01", "2011-01-01", "2011-03-01"], name="xxx", tz="US/Eastern"
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

        msg = "out of bounds"
        with pytest.raises(IndexError, match=msg):
            idx.take(np.array([1, -5]))


class TestGetLoc:
    def test_get_loc_key_unit_mismatch(self):
        idx = date_range("2000-01-01", periods=3)
        key = idx[1].as_unit("ms")
        loc = idx.get_loc(key)
        assert loc == 1
        assert key in idx

    def test_get_loc_key_unit_mismatch_not_castable(self):
        dta = date_range("2000-01-01", periods=3)._data.astype("M8[s]")
        dti = DatetimeIndex(dta)
        key = dta[0].as_unit("ns") + pd.Timedelta(1)

        with pytest.raises(
            KeyError, match=r"Timestamp\('2000-01-01 00:00:00.000000001'\)"
        ):
            dti.get_loc(key)

        assert key not in dti

    def test_get_loc_time_obj(self):
        # time indexing
        idx = date_range("2000-01-01", periods=24, freq="h")

        result = idx.get_loc(time(12))
        expected = np.array([12])
        tm.assert_numpy_array_equal(result, expected, check_dtype=False)

        result = idx.get_loc(time(12, 30))
        expected = np.array([])
        tm.assert_numpy_array_equal(result, expected, check_dtype=False)

    @pytest.mark.parametrize("offset", [-10, 10])
    def test_get_loc_time_obj2(self, monkeypatch, offset):
        # GH#8667
        size_cutoff = 50
        n = size_cutoff + offset
        key = time(15, 11, 30)
        start = key.hour * 3600 + key.minute * 60 + key.second
        step = 24 * 3600

        with monkeypatch.context():
            monkeypatch.setattr(libindex, "_SIZE_CUTOFF", size_cutoff)
            idx = date_range("2014-11-26", periods=n, freq="s")
            ts = pd.Series(np.random.default_rng(2).standard_normal(n), index=idx)
            locs = np.arange(start, n, step, dtype=np.intp)

            result = ts.index.get_loc(key)
            tm.assert_numpy_array_equal(result, locs)
            tm.assert_series_equal(ts[key], ts.iloc[locs])

            left, right = ts.copy(), ts.copy()
            left[key] *= -10
            right.iloc[locs] *= -10
            tm.assert_series_equal(left, right)

    def test_get_loc_time_nat(self):
        # GH#35114
        # Case where key's total microseconds happens to match iNaT % 1e6 // 1000
        tic = time(minute=12, second=43, microsecond=145224)
        dti = DatetimeIndex([pd.NaT])

        loc = dti.get_loc(tic)
        expected = np.array([], dtype=np.intp)
        tm.assert_numpy_array_equal(loc, expected)

    def test_get_loc_nat(self):
        # GH#20464
        index = DatetimeIndex(["1/3/2000", "NaT"])
        assert index.get_loc(pd.NaT) == 1

        assert index.get_loc(None) == 1

        assert index.get_loc(np.nan) == 1

        assert index.get_loc(pd.NA) == 1

        assert index.get_loc(np.datetime64("NaT")) == 1

        with pytest.raises(KeyError, match="NaT"):
            index.get_loc(np.timedelta64("NaT"))

    @pytest.mark.parametrize("key", [pd.Timedelta(0), pd.Timedelta(1), timedelta(0)])
    def test_get_loc_timedelta_invalid_key(self, key):
        # GH#20464
        dti = date_range("1970-01-01", periods=10)
        msg = "Cannot index DatetimeIndex with [Tt]imedelta"
        with pytest.raises(TypeError, match=msg):
            dti.get_loc(key)

    def test_get_loc_reasonable_key_error(self):
        # GH#1062
        index = DatetimeIndex(["1/3/2000"])
        with pytest.raises(KeyError, match="2000"):
            index.get_loc("1/1/2000")

    def test_get_loc_year_str(self):
        rng = date_range("1/1/2000", "1/1/2010")

        result = rng.get_loc("2009")
        expected = slice(3288, 3653)
        assert result == expected


class TestContains:
    def test_dti_contains_with_duplicates(self):
        d = datetime(2011, 12, 5, 20, 30)
        ix = DatetimeIndex([d, d])
        assert d in ix

    @pytest.mark.parametrize(
        "vals",
        [
            [0, 1, 0],
            [0, 0, -1],
            [0, -1, -1],
            ["2015", "2015", "2016"],
            ["2015", "2015", "2014"],
        ],
    )
    def test_contains_nonunique(self, vals):
        # GH#9512
        idx = DatetimeIndex(vals)
        assert idx[0] in idx


class TestGetIndexer:
    def test_get_indexer_date_objs(self):
        rng = date_range("1/1/2000", periods=20)

        result = rng.get_indexer(rng.map(lambda x: x.date()))
        expected = rng.get_indexer(rng)
        tm.assert_numpy_array_equal(result, expected)

    def test_get_indexer(self):
        idx = date_range("2000-01-01", periods=3)
        exp = np.array([0, 1, 2], dtype=np.intp)
        tm.assert_numpy_array_equal(idx.get_indexer(idx), exp)

        target = idx[0] + pd.to_timedelta(["-1 hour", "12 hours", "1 day 1 hour"])
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
            idx.get_indexer(target, "nearest", tolerance=pd.Timedelta("1 hour")),
            np.array([0, -1, 1], dtype=np.intp),
        )
        tol_raw = [
            pd.Timedelta("1 hour"),
            pd.Timedelta("1 hour"),
            pd.Timedelta("1 hour").to_timedelta64(),
        ]
        tm.assert_numpy_array_equal(
            idx.get_indexer(
                target, "nearest", tolerance=[np.timedelta64(x) for x in tol_raw]
            ),
            np.array([0, -1, 1], dtype=np.intp),
        )
        tol_bad = [
            pd.Timedelta("2 hour").to_timedelta64(),
            pd.Timedelta("1 hour").to_timedelta64(),
            "foo",
        ]
        msg = "Could not convert 'foo' to NumPy timedelta"
        with pytest.raises(ValueError, match=msg):
            idx.get_indexer(target, "nearest", tolerance=tol_bad)
        with pytest.raises(ValueError, match="abbreviation w/o a number"):
            idx.get_indexer(idx[[0]], method="nearest", tolerance="foo")

    @pytest.mark.parametrize(
        "target",
        [
            [date(2020, 1, 1), Timestamp("2020-01-02")],
            [Timestamp("2020-01-01"), date(2020, 1, 2)],
        ],
    )
    def test_get_indexer_mixed_dtypes(self, target):
        # https://github.com/pandas-dev/pandas/issues/33741
        values = DatetimeIndex([Timestamp("2020-01-01"), Timestamp("2020-01-02")])
        result = values.get_indexer(target)
        expected = np.array([0, 1], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize(
        "target, positions",
        [
            ([date(9999, 1, 1), Timestamp("2020-01-01")], [-1, 0]),
            ([Timestamp("2020-01-01"), date(9999, 1, 1)], [0, -1]),
            ([date(9999, 1, 1), date(9999, 1, 1)], [-1, -1]),
        ],
    )
    def test_get_indexer_out_of_bounds_date(self, target, positions):
        values = DatetimeIndex([Timestamp("2020-01-01"), Timestamp("2020-01-02")])

        result = values.get_indexer(target)
        expected = np.array(positions, dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

    def test_get_indexer_pad_requires_monotonicity(self):
        rng = date_range("1/1/2000", "3/1/2000", freq="B")

        # neither monotonic increasing or decreasing
        rng2 = rng[[1, 0, 2]]

        msg = "index must be monotonic increasing or decreasing"
        with pytest.raises(ValueError, match=msg):
            rng2.get_indexer(rng, method="pad")


class TestMaybeCastSliceBound:
    def test_maybe_cast_slice_bounds_empty(self):
        # GH#14354
        empty_idx = date_range(freq="1h", periods=0, end="2015")

        right = empty_idx._maybe_cast_slice_bound("2015-01-02", "right")
        exp = Timestamp("2015-01-02 23:59:59.999999999")
        assert right == exp

        left = empty_idx._maybe_cast_slice_bound("2015-01-02", "left")
        exp = Timestamp("2015-01-02 00:00:00")
        assert left == exp

    def test_maybe_cast_slice_duplicate_monotonic(self):
        # https://github.com/pandas-dev/pandas/issues/16515
        idx = DatetimeIndex(["2017", "2017"])
        result = idx._maybe_cast_slice_bound("2017-01-01", "left")
        expected = Timestamp("2017-01-01")
        assert result == expected


class TestGetSliceBounds:
    @pytest.mark.parametrize("box", [date, datetime, Timestamp])
    @pytest.mark.parametrize("side, expected", [("left", 4), ("right", 5)])
    def test_get_slice_bounds_datetime_within(
        self, box, side, expected, tz_aware_fixture
    ):
        # GH 35690
        tz = tz_aware_fixture
        index = bdate_range("2000-01-03", "2000-02-11").tz_localize(tz)
        key = box(year=2000, month=1, day=7)

        if tz is not None:
            with pytest.raises(TypeError, match="Cannot compare tz-naive"):
                # GH#36148 we require tzawareness-compat as of 2.0
                index.get_slice_bound(key, side=side)
        else:
            result = index.get_slice_bound(key, side=side)
            assert result == expected

    @pytest.mark.parametrize("box", [datetime, Timestamp])
    @pytest.mark.parametrize("side", ["left", "right"])
    @pytest.mark.parametrize("year, expected", [(1999, 0), (2020, 30)])
    def test_get_slice_bounds_datetime_outside(
        self, box, side, year, expected, tz_aware_fixture
    ):
        # GH 35690
        tz = tz_aware_fixture
        index = bdate_range("2000-01-03", "2000-02-11").tz_localize(tz)
        key = box(year=year, month=1, day=7)

        if tz is not None:
            with pytest.raises(TypeError, match="Cannot compare tz-naive"):
                # GH#36148 we require tzawareness-compat as of 2.0
                index.get_slice_bound(key, side=side)
        else:
            result = index.get_slice_bound(key, side=side)
            assert result == expected

    @pytest.mark.parametrize("box", [datetime, Timestamp])
    def test_slice_datetime_locs(self, box, tz_aware_fixture):
        # GH 34077
        tz = tz_aware_fixture
        index = DatetimeIndex(["2010-01-01", "2010-01-03"]).tz_localize(tz)
        key = box(2010, 1, 1)

        if tz is not None:
            with pytest.raises(TypeError, match="Cannot compare tz-naive"):
                # GH#36148 we require tzawareness-compat as of 2.0
                index.slice_locs(key, box(2010, 1, 2))
        else:
            result = index.slice_locs(key, box(2010, 1, 2))
            expected = (0, 1)
            assert result == expected


class TestIndexerBetweenTime:
    def test_indexer_between_time(self):
        # GH#11818
        rng = date_range("1/1/2000", "1/5/2000", freq="5min")
        msg = r"Cannot convert arg \[datetime\.datetime\(2010, 1, 2, 1, 0\)\] to a time"
        with pytest.raises(ValueError, match=msg):
            rng.indexer_between_time(datetime(2010, 1, 2, 1), datetime(2010, 1, 2, 5))

    @pytest.mark.parametrize("unit", ["us", "ms", "s"])
    def test_indexer_between_time_non_nano(self, unit):
        # For simple cases like this, the non-nano indexer_between_time
        #  should match the nano result

        rng = date_range("1/1/2000", "1/5/2000", freq="5min")
        arr_nano = rng._data._ndarray

        arr = arr_nano.astype(f"M8[{unit}]")

        dta = type(rng._data)._simple_new(arr, dtype=arr.dtype)
        dti = DatetimeIndex(dta)
        assert dti.dtype == arr.dtype

        tic = time(1, 25)
        toc = time(2, 29)

        result = dti.indexer_between_time(tic, toc)
        expected = rng.indexer_between_time(tic, toc)
        tm.assert_numpy_array_equal(result, expected)

        # case with non-zero micros in arguments
        tic = time(1, 25, 0, 45678)
        toc = time(2, 29, 0, 1234)

        result = dti.indexer_between_time(tic, toc)
        expected = rng.indexer_between_time(tic, toc)
        tm.assert_numpy_array_equal(result, expected)
