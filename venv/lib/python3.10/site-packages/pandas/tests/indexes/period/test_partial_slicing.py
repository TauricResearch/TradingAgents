import numpy as np
import pytest

from pandas import (
    DataFrame,
    PeriodIndex,
    Series,
    date_range,
    period_range,
)
import pandas._testing as tm


class TestPeriodIndex:
    def test_getitem_periodindex_duplicates_string_slice(
        self, using_copy_on_write, warn_copy_on_write
    ):
        # monotonic
        idx = PeriodIndex([2000, 2007, 2007, 2009, 2009], freq="Y-JUN")
        ts = Series(np.random.default_rng(2).standard_normal(len(idx)), index=idx)
        original = ts.copy()

        result = ts["2007"]
        expected = ts[1:3]
        tm.assert_series_equal(result, expected)
        with tm.assert_cow_warning(warn_copy_on_write):
            result[:] = 1
        if using_copy_on_write:
            tm.assert_series_equal(ts, original)
        else:
            assert (ts[1:3] == 1).all()

        # not monotonic
        idx = PeriodIndex([2000, 2007, 2007, 2009, 2007], freq="Y-JUN")
        ts = Series(np.random.default_rng(2).standard_normal(len(idx)), index=idx)

        result = ts["2007"]
        expected = ts[idx == "2007"]
        tm.assert_series_equal(result, expected)

    def test_getitem_periodindex_quarter_string(self):
        pi = PeriodIndex(["2Q05", "3Q05", "4Q05", "1Q06", "2Q06"], freq="Q")
        ser = Series(np.random.default_rng(2).random(len(pi)), index=pi).cumsum()
        # Todo: fix these accessors!
        assert ser["05Q4"] == ser.iloc[2]

    def test_pindex_slice_index(self):
        pi = period_range(start="1/1/10", end="12/31/12", freq="M")
        s = Series(np.random.default_rng(2).random(len(pi)), index=pi)
        res = s["2010"]
        exp = s[0:12]
        tm.assert_series_equal(res, exp)
        res = s["2011"]
        exp = s[12:24]
        tm.assert_series_equal(res, exp)

    @pytest.mark.parametrize("make_range", [date_range, period_range])
    def test_range_slice_day(self, make_range):
        # GH#6716
        idx = make_range(start="2013/01/01", freq="D", periods=400)

        msg = "slice indices must be integers or None or have an __index__ method"
        # slices against index should raise IndexError
        values = [
            "2014",
            "2013/02",
            "2013/01/02",
            "2013/02/01 9H",
            "2013/02/01 09:00",
        ]
        for v in values:
            with pytest.raises(TypeError, match=msg):
                idx[v:]

        s = Series(np.random.default_rng(2).random(len(idx)), index=idx)

        tm.assert_series_equal(s["2013/01/02":], s[1:])
        tm.assert_series_equal(s["2013/01/02":"2013/01/05"], s[1:5])
        tm.assert_series_equal(s["2013/02":], s[31:])
        tm.assert_series_equal(s["2014":], s[365:])

        invalid = ["2013/02/01 9H", "2013/02/01 09:00"]
        for v in invalid:
            with pytest.raises(TypeError, match=msg):
                idx[v:]

    @pytest.mark.parametrize("make_range", [date_range, period_range])
    def test_range_slice_seconds(self, make_range):
        # GH#6716
        idx = make_range(start="2013/01/01 09:00:00", freq="s", periods=4000)
        msg = "slice indices must be integers or None or have an __index__ method"

        # slices against index should raise IndexError
        values = [
            "2014",
            "2013/02",
            "2013/01/02",
            "2013/02/01 9H",
            "2013/02/01 09:00",
        ]
        for v in values:
            with pytest.raises(TypeError, match=msg):
                idx[v:]

        s = Series(np.random.default_rng(2).random(len(idx)), index=idx)

        tm.assert_series_equal(s["2013/01/01 09:05":"2013/01/01 09:10"], s[300:660])
        tm.assert_series_equal(s["2013/01/01 10:00":"2013/01/01 10:05"], s[3600:3960])
        tm.assert_series_equal(s["2013/01/01 10H":], s[3600:])
        tm.assert_series_equal(s[:"2013/01/01 09:30"], s[:1860])
        for d in ["2013/01/01", "2013/01", "2013"]:
            tm.assert_series_equal(s[d:], s)

    @pytest.mark.parametrize("make_range", [date_range, period_range])
    def test_range_slice_outofbounds(self, make_range):
        # GH#5407
        idx = make_range(start="2013/10/01", freq="D", periods=10)

        df = DataFrame({"units": [100 + i for i in range(10)]}, index=idx)
        empty = DataFrame(index=idx[:0], columns=["units"])
        empty["units"] = empty["units"].astype("int64")

        tm.assert_frame_equal(df["2013/09/01":"2013/09/30"], empty)
        tm.assert_frame_equal(df["2013/09/30":"2013/10/02"], df.iloc[:2])
        tm.assert_frame_equal(df["2013/10/01":"2013/10/02"], df.iloc[:2])
        tm.assert_frame_equal(df["2013/10/02":"2013/09/30"], empty)
        tm.assert_frame_equal(df["2013/10/15":"2013/10/17"], empty)
        tm.assert_frame_equal(df["2013-06":"2013-09"], empty)
        tm.assert_frame_equal(df["2013-11":"2013-12"], empty)

    @pytest.mark.parametrize("make_range", [date_range, period_range])
    def test_maybe_cast_slice_bound(self, make_range, frame_or_series):
        idx = make_range(start="2013/10/01", freq="D", periods=10)

        obj = DataFrame({"units": [100 + i for i in range(10)]}, index=idx)
        obj = tm.get_obj(obj, frame_or_series)

        msg = (
            f"cannot do slice indexing on {type(idx).__name__} with "
            r"these indexers \[foo\] of type str"
        )

        # Check the lower-level calls are raising where expected.
        with pytest.raises(TypeError, match=msg):
            idx._maybe_cast_slice_bound("foo", "left")
        with pytest.raises(TypeError, match=msg):
            idx.get_slice_bound("foo", "left")

        with pytest.raises(TypeError, match=msg):
            obj["2013/09/30":"foo"]
        with pytest.raises(TypeError, match=msg):
            obj["foo":"2013/09/30"]
        with pytest.raises(TypeError, match=msg):
            obj.loc["2013/09/30":"foo"]
        with pytest.raises(TypeError, match=msg):
            obj.loc["foo":"2013/09/30"]

    def test_partial_slice_doesnt_require_monotonicity(self):
        # See also: DatetimeIndex test ofm the same name
        dti = date_range("2014-01-01", periods=30, freq="30D")
        pi = dti.to_period("D")

        ser_montonic = Series(np.arange(30), index=pi)

        shuffler = list(range(0, 30, 2)) + list(range(1, 31, 2))
        ser = ser_montonic.iloc[shuffler]
        nidx = ser.index

        # Manually identified locations of year==2014
        indexer_2014 = np.array(
            [0, 1, 2, 3, 4, 5, 6, 15, 16, 17, 18, 19, 20], dtype=np.intp
        )
        assert (nidx[indexer_2014].year == 2014).all()
        assert not (nidx[~indexer_2014].year == 2014).any()

        result = nidx.get_loc("2014")
        tm.assert_numpy_array_equal(result, indexer_2014)

        expected = ser.iloc[indexer_2014]
        result = ser.loc["2014"]
        tm.assert_series_equal(result, expected)

        result = ser["2014"]
        tm.assert_series_equal(result, expected)

        # Manually identified locations where ser.index is within Mat 2015
        indexer_may2015 = np.array([23], dtype=np.intp)
        assert nidx[23].year == 2015 and nidx[23].month == 5

        result = nidx.get_loc("May 2015")
        tm.assert_numpy_array_equal(result, indexer_may2015)

        expected = ser.iloc[indexer_may2015]
        result = ser.loc["May 2015"]
        tm.assert_series_equal(result, expected)

        result = ser["May 2015"]
        tm.assert_series_equal(result, expected)
