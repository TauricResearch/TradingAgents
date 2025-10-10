"""
Also test support for datetime64[ns] in Series / DataFrame
"""
from datetime import (
    datetime,
    timedelta,
)
import re

from dateutil.tz import (
    gettz,
    tzutc,
)
import numpy as np
import pytest
import pytz

from pandas._libs import index as libindex

import pandas as pd
from pandas import (
    DataFrame,
    Series,
    Timestamp,
    date_range,
    period_range,
)
import pandas._testing as tm


def test_fancy_getitem():
    dti = date_range(
        freq="WOM-1FRI", start=datetime(2005, 1, 1), end=datetime(2010, 1, 1)
    )

    s = Series(np.arange(len(dti)), index=dti)

    msg = "Series.__getitem__ treating keys as positions is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        assert s[48] == 48
    assert s["1/2/2009"] == 48
    assert s["2009-1-2"] == 48
    assert s[datetime(2009, 1, 2)] == 48
    assert s[Timestamp(datetime(2009, 1, 2))] == 48
    with pytest.raises(KeyError, match=r"^'2009-1-3'$"):
        s["2009-1-3"]
    tm.assert_series_equal(
        s["3/6/2009":"2009-06-05"], s[datetime(2009, 3, 6) : datetime(2009, 6, 5)]
    )


def test_fancy_setitem():
    dti = date_range(
        freq="WOM-1FRI", start=datetime(2005, 1, 1), end=datetime(2010, 1, 1)
    )

    s = Series(np.arange(len(dti)), index=dti)

    msg = "Series.__setitem__ treating keys as positions is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        s[48] = -1
    assert s.iloc[48] == -1
    s["1/2/2009"] = -2
    assert s.iloc[48] == -2
    s["1/2/2009":"2009-06-05"] = -3
    assert (s[48:54] == -3).all()


@pytest.mark.parametrize("tz_source", ["pytz", "dateutil"])
def test_getitem_setitem_datetime_tz(tz_source):
    if tz_source == "pytz":
        tzget = pytz.timezone
    else:
        # handle special case for utc in dateutil
        tzget = lambda x: tzutc() if x == "UTC" else gettz(x)

    N = 50
    # testing with timezone, GH #2785
    rng = date_range("1/1/1990", periods=N, freq="h", tz=tzget("US/Eastern"))
    ts = Series(np.random.default_rng(2).standard_normal(N), index=rng)

    # also test Timestamp tz handling, GH #2789
    result = ts.copy()
    result["1990-01-01 09:00:00+00:00"] = 0
    result["1990-01-01 09:00:00+00:00"] = ts.iloc[4]
    tm.assert_series_equal(result, ts)

    result = ts.copy()
    result["1990-01-01 03:00:00-06:00"] = 0
    result["1990-01-01 03:00:00-06:00"] = ts.iloc[4]
    tm.assert_series_equal(result, ts)

    # repeat with datetimes
    result = ts.copy()
    result[datetime(1990, 1, 1, 9, tzinfo=tzget("UTC"))] = 0
    result[datetime(1990, 1, 1, 9, tzinfo=tzget("UTC"))] = ts.iloc[4]
    tm.assert_series_equal(result, ts)

    result = ts.copy()
    dt = Timestamp(1990, 1, 1, 3).tz_localize(tzget("US/Central"))
    dt = dt.to_pydatetime()
    result[dt] = 0
    result[dt] = ts.iloc[4]
    tm.assert_series_equal(result, ts)


def test_getitem_setitem_datetimeindex():
    N = 50
    # testing with timezone, GH #2785
    rng = date_range("1/1/1990", periods=N, freq="h", tz="US/Eastern")
    ts = Series(np.random.default_rng(2).standard_normal(N), index=rng)

    result = ts["1990-01-01 04:00:00"]
    expected = ts.iloc[4]
    assert result == expected

    result = ts.copy()
    result["1990-01-01 04:00:00"] = 0
    result["1990-01-01 04:00:00"] = ts.iloc[4]
    tm.assert_series_equal(result, ts)

    result = ts["1990-01-01 04:00:00":"1990-01-01 07:00:00"]
    expected = ts[4:8]
    tm.assert_series_equal(result, expected)

    result = ts.copy()
    result["1990-01-01 04:00:00":"1990-01-01 07:00:00"] = 0
    result["1990-01-01 04:00:00":"1990-01-01 07:00:00"] = ts[4:8]
    tm.assert_series_equal(result, ts)

    lb = "1990-01-01 04:00:00"
    rb = "1990-01-01 07:00:00"
    # GH#18435 strings get a pass from tzawareness compat
    result = ts[(ts.index >= lb) & (ts.index <= rb)]
    expected = ts[4:8]
    tm.assert_series_equal(result, expected)

    lb = "1990-01-01 04:00:00-0500"
    rb = "1990-01-01 07:00:00-0500"
    result = ts[(ts.index >= lb) & (ts.index <= rb)]
    expected = ts[4:8]
    tm.assert_series_equal(result, expected)

    # But we do not give datetimes a pass on tzawareness compat
    msg = "Cannot compare tz-naive and tz-aware datetime-like objects"
    naive = datetime(1990, 1, 1, 4)
    for key in [naive, Timestamp(naive), np.datetime64(naive, "ns")]:
        with pytest.raises(KeyError, match=re.escape(repr(key))):
            # GH#36148 as of 2.0 we require tzawareness-compat
            ts[key]

    result = ts.copy()
    # GH#36148 as of 2.0 we do not ignore tzawareness mismatch in indexing,
    #  so setting it as a new key casts to object rather than matching
    #  rng[4]
    result[naive] = ts.iloc[4]
    assert result.index.dtype == object
    tm.assert_index_equal(result.index[:-1], rng.astype(object))
    assert result.index[-1] == naive

    msg = "Cannot compare tz-naive and tz-aware datetime-like objects"
    with pytest.raises(TypeError, match=msg):
        # GH#36148 require tzawareness compat as of 2.0
        ts[naive : datetime(1990, 1, 1, 7)]

    result = ts.copy()
    with pytest.raises(TypeError, match=msg):
        # GH#36148 require tzawareness compat as of 2.0
        result[naive : datetime(1990, 1, 1, 7)] = 0
    with pytest.raises(TypeError, match=msg):
        # GH#36148 require tzawareness compat as of 2.0
        result[naive : datetime(1990, 1, 1, 7)] = 99
    # the __setitems__ here failed, so result should still match ts
    tm.assert_series_equal(result, ts)

    lb = naive
    rb = datetime(1990, 1, 1, 7)
    msg = r"Invalid comparison between dtype=datetime64\[ns, US/Eastern\] and datetime"
    with pytest.raises(TypeError, match=msg):
        # tznaive vs tzaware comparison is invalid
        # see GH#18376, GH#18162
        ts[(ts.index >= lb) & (ts.index <= rb)]

    lb = Timestamp(naive).tz_localize(rng.tzinfo)
    rb = Timestamp(datetime(1990, 1, 1, 7)).tz_localize(rng.tzinfo)
    result = ts[(ts.index >= lb) & (ts.index <= rb)]
    expected = ts[4:8]
    tm.assert_series_equal(result, expected)

    result = ts[ts.index[4]]
    expected = ts.iloc[4]
    assert result == expected

    result = ts[ts.index[4:8]]
    expected = ts[4:8]
    tm.assert_series_equal(result, expected)

    result = ts.copy()
    result[ts.index[4:8]] = 0
    result.iloc[4:8] = ts.iloc[4:8]
    tm.assert_series_equal(result, ts)

    # also test partial date slicing
    result = ts["1990-01-02"]
    expected = ts[24:48]
    tm.assert_series_equal(result, expected)

    result = ts.copy()
    result["1990-01-02"] = 0
    result["1990-01-02"] = ts[24:48]
    tm.assert_series_equal(result, ts)


def test_getitem_setitem_periodindex():
    N = 50
    rng = period_range("1/1/1990", periods=N, freq="h")
    ts = Series(np.random.default_rng(2).standard_normal(N), index=rng)

    result = ts["1990-01-01 04"]
    expected = ts.iloc[4]
    assert result == expected

    result = ts.copy()
    result["1990-01-01 04"] = 0
    result["1990-01-01 04"] = ts.iloc[4]
    tm.assert_series_equal(result, ts)

    result = ts["1990-01-01 04":"1990-01-01 07"]
    expected = ts[4:8]
    tm.assert_series_equal(result, expected)

    result = ts.copy()
    result["1990-01-01 04":"1990-01-01 07"] = 0
    result["1990-01-01 04":"1990-01-01 07"] = ts[4:8]
    tm.assert_series_equal(result, ts)

    lb = "1990-01-01 04"
    rb = "1990-01-01 07"
    result = ts[(ts.index >= lb) & (ts.index <= rb)]
    expected = ts[4:8]
    tm.assert_series_equal(result, expected)

    # GH 2782
    result = ts[ts.index[4]]
    expected = ts.iloc[4]
    assert result == expected

    result = ts[ts.index[4:8]]
    expected = ts[4:8]
    tm.assert_series_equal(result, expected)

    result = ts.copy()
    result[ts.index[4:8]] = 0
    result.iloc[4:8] = ts.iloc[4:8]
    tm.assert_series_equal(result, ts)


def test_datetime_indexing():
    index = date_range("1/1/2000", "1/7/2000")
    index = index.repeat(3)

    s = Series(len(index), index=index)
    stamp = Timestamp("1/8/2000")

    with pytest.raises(KeyError, match=re.escape(repr(stamp))):
        s[stamp]
    s[stamp] = 0
    assert s[stamp] == 0

    # not monotonic
    s = Series(len(index), index=index)
    s = s[::-1]

    with pytest.raises(KeyError, match=re.escape(repr(stamp))):
        s[stamp]
    s[stamp] = 0
    assert s[stamp] == 0


# test duplicates in time series


def test_indexing_with_duplicate_datetimeindex(
    rand_series_with_duplicate_datetimeindex,
):
    ts = rand_series_with_duplicate_datetimeindex

    uniques = ts.index.unique()
    for date in uniques:
        result = ts[date]

        mask = ts.index == date
        total = (ts.index == date).sum()
        expected = ts[mask]
        if total > 1:
            tm.assert_series_equal(result, expected)
        else:
            tm.assert_almost_equal(result, expected.iloc[0])

        cp = ts.copy()
        cp[date] = 0
        expected = Series(np.where(mask, 0, ts), index=ts.index)
        tm.assert_series_equal(cp, expected)

    key = datetime(2000, 1, 6)
    with pytest.raises(KeyError, match=re.escape(repr(key))):
        ts[key]

    # new index
    ts[datetime(2000, 1, 6)] = 0
    assert ts[datetime(2000, 1, 6)] == 0


def test_loc_getitem_over_size_cutoff(monkeypatch):
    # #1821

    monkeypatch.setattr(libindex, "_SIZE_CUTOFF", 1000)

    # create large list of non periodic datetime
    dates = []
    sec = timedelta(seconds=1)
    half_sec = timedelta(microseconds=500000)
    d = datetime(2011, 12, 5, 20, 30)
    n = 1100
    for i in range(n):
        dates.append(d)
        dates.append(d + sec)
        dates.append(d + sec + half_sec)
        dates.append(d + sec + sec + half_sec)
        d += 3 * sec

    # duplicate some values in the list
    duplicate_positions = np.random.default_rng(2).integers(0, len(dates) - 1, 20)
    for p in duplicate_positions:
        dates[p + 1] = dates[p]

    df = DataFrame(
        np.random.default_rng(2).standard_normal((len(dates), 4)),
        index=dates,
        columns=list("ABCD"),
    )

    pos = n * 3
    timestamp = df.index[pos]
    assert timestamp in df.index

    # it works!
    df.loc[timestamp]
    assert len(df.loc[[timestamp]]) > 0


def test_indexing_over_size_cutoff_period_index(monkeypatch):
    # GH 27136

    monkeypatch.setattr(libindex, "_SIZE_CUTOFF", 1000)

    n = 1100
    idx = period_range("1/1/2000", freq="min", periods=n)
    assert idx._engine.over_size_threshold

    s = Series(np.random.default_rng(2).standard_normal(len(idx)), index=idx)

    pos = n - 1
    timestamp = idx[pos]
    assert timestamp in s.index

    # it works!
    s[timestamp]
    assert len(s.loc[[timestamp]]) > 0


def test_indexing_unordered():
    # GH 2437
    rng = date_range(start="2011-01-01", end="2011-01-15")
    ts = Series(np.random.default_rng(2).random(len(rng)), index=rng)
    ts2 = pd.concat([ts[0:4], ts[-4:], ts[4:-4]])

    for t in ts.index:
        expected = ts[t]
        result = ts2[t]
        assert expected == result

    # GH 3448 (ranges)
    def compare(slobj):
        result = ts2[slobj].copy()
        result = result.sort_index()
        expected = ts[slobj]
        expected.index = expected.index._with_freq(None)
        tm.assert_series_equal(result, expected)

    for key in [
        slice("2011-01-01", "2011-01-15"),
        slice("2010-12-30", "2011-01-15"),
        slice("2011-01-01", "2011-01-16"),
        # partial ranges
        slice("2011-01-01", "2011-01-6"),
        slice("2011-01-06", "2011-01-8"),
        slice("2011-01-06", "2011-01-12"),
    ]:
        with pytest.raises(
            KeyError, match="Value based partial slicing on non-monotonic"
        ):
            compare(key)

    # single values
    result = ts2["2011"].sort_index()
    expected = ts["2011"]
    expected.index = expected.index._with_freq(None)
    tm.assert_series_equal(result, expected)


def test_indexing_unordered2():
    # diff freq
    rng = date_range(datetime(2005, 1, 1), periods=20, freq="ME")
    ts = Series(np.arange(len(rng)), index=rng)
    ts = ts.take(np.random.default_rng(2).permutation(20))

    result = ts["2005"]
    for t in result.index:
        assert t.year == 2005


def test_indexing():
    idx = date_range("2001-1-1", periods=20, freq="ME")
    ts = Series(np.random.default_rng(2).random(len(idx)), index=idx)

    # getting

    # GH 3070, make sure semantics work on Series/Frame
    result = ts["2001"]
    tm.assert_series_equal(result, ts.iloc[:12])

    df = DataFrame({"A": ts.copy()})

    # GH#36179 pre-2.0 df["2001"] operated as slicing on rows. in 2.0 it behaves
    #  like any other key, so raises
    with pytest.raises(KeyError, match="2001"):
        df["2001"]

    # setting
    ts = Series(np.random.default_rng(2).random(len(idx)), index=idx)
    expected = ts.copy()
    expected.iloc[:12] = 1
    ts["2001"] = 1
    tm.assert_series_equal(ts, expected)

    expected = df.copy()
    expected.iloc[:12, 0] = 1
    df.loc["2001", "A"] = 1
    tm.assert_frame_equal(df, expected)


def test_getitem_str_month_with_datetimeindex():
    # GH3546 (not including times on the last day)
    idx = date_range(start="2013-05-31 00:00", end="2013-05-31 23:00", freq="h")
    ts = Series(range(len(idx)), index=idx)
    expected = ts["2013-05"]
    tm.assert_series_equal(expected, ts)

    idx = date_range(start="2013-05-31 00:00", end="2013-05-31 23:59", freq="s")
    ts = Series(range(len(idx)), index=idx)
    expected = ts["2013-05"]
    tm.assert_series_equal(expected, ts)


def test_getitem_str_year_with_datetimeindex():
    idx = [
        Timestamp("2013-05-31 00:00"),
        Timestamp(datetime(2013, 5, 31, 23, 59, 59, 999999)),
    ]
    ts = Series(range(len(idx)), index=idx)
    expected = ts["2013"]
    tm.assert_series_equal(expected, ts)


def test_getitem_str_second_with_datetimeindex():
    # GH14826, indexing with a seconds resolution string / datetime object
    df = DataFrame(
        np.random.default_rng(2).random((5, 5)),
        columns=["open", "high", "low", "close", "volume"],
        index=date_range("2012-01-02 18:01:00", periods=5, tz="US/Central", freq="s"),
    )

    # this is a single date, so will raise
    with pytest.raises(KeyError, match=r"^'2012-01-02 18:01:02'$"):
        df["2012-01-02 18:01:02"]

    msg = r"Timestamp\('2012-01-02 18:01:02-0600', tz='US/Central'\)"
    with pytest.raises(KeyError, match=msg):
        df[df.index[2]]


def test_compare_datetime_with_all_none():
    # GH#54870
    ser = Series(["2020-01-01", "2020-01-02"], dtype="datetime64[ns]")
    ser2 = Series([None, None])
    result = ser > ser2
    expected = Series([False, False])
    tm.assert_series_equal(result, expected)
