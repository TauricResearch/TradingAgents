import re

import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    Series,
    Timestamp,
    date_range,
)
import pandas._testing as tm


class TestDatetimeIndex:
    def test_get_loc_naive_dti_aware_str_deprecated(self):
        # GH#46903
        ts = Timestamp("20130101")._value
        dti = pd.DatetimeIndex([ts + 50 + i for i in range(100)])
        ser = Series(range(100), index=dti)

        key = "2013-01-01 00:00:00.000000050+0000"
        msg = re.escape(repr(key))
        with pytest.raises(KeyError, match=msg):
            ser[key]

        with pytest.raises(KeyError, match=msg):
            dti.get_loc(key)

    def test_indexing_with_datetime_tz(self):
        # GH#8260
        # support datetime64 with tz

        idx = Index(date_range("20130101", periods=3, tz="US/Eastern"), name="foo")
        dr = date_range("20130110", periods=3)
        df = DataFrame({"A": idx, "B": dr})
        df["C"] = idx
        df.iloc[1, 1] = pd.NaT
        df.iloc[1, 2] = pd.NaT

        expected = Series(
            [Timestamp("2013-01-02 00:00:00-0500", tz="US/Eastern"), pd.NaT, pd.NaT],
            index=list("ABC"),
            dtype="object",
            name=1,
        )

        # indexing
        result = df.iloc[1]
        tm.assert_series_equal(result, expected)
        result = df.loc[1]
        tm.assert_series_equal(result, expected)

    def test_indexing_fast_xs(self):
        # indexing - fast_xs
        df = DataFrame({"a": date_range("2014-01-01", periods=10, tz="UTC")})
        result = df.iloc[5]
        expected = Series(
            [Timestamp("2014-01-06 00:00:00+0000", tz="UTC")],
            index=["a"],
            name=5,
            dtype="M8[ns, UTC]",
        )
        tm.assert_series_equal(result, expected)

        result = df.loc[5]
        tm.assert_series_equal(result, expected)

        # indexing - boolean
        result = df[df.a > df.a[3]]
        expected = df.iloc[4:]
        tm.assert_frame_equal(result, expected)

    def test_consistency_with_tz_aware_scalar(self):
        # xef gh-12938
        # various ways of indexing the same tz-aware scalar
        df = Series([Timestamp("2016-03-30 14:35:25", tz="Europe/Brussels")]).to_frame()

        df = pd.concat([df, df]).reset_index(drop=True)
        expected = Timestamp("2016-03-30 14:35:25+0200", tz="Europe/Brussels")

        result = df[0][0]
        assert result == expected

        result = df.iloc[0, 0]
        assert result == expected

        result = df.loc[0, 0]
        assert result == expected

        result = df.iat[0, 0]
        assert result == expected

        result = df.at[0, 0]
        assert result == expected

        result = df[0].loc[0]
        assert result == expected

        result = df[0].at[0]
        assert result == expected

    def test_indexing_with_datetimeindex_tz(self, indexer_sl):
        # GH 12050
        # indexing on a series with a datetimeindex with tz
        index = date_range("2015-01-01", periods=2, tz="utc")

        ser = Series(range(2), index=index, dtype="int64")

        # list-like indexing

        for sel in (index, list(index)):
            # getitem
            result = indexer_sl(ser)[sel]
            expected = ser.copy()
            if sel is not index:
                expected.index = expected.index._with_freq(None)
            tm.assert_series_equal(result, expected)

            # setitem
            result = ser.copy()
            indexer_sl(result)[sel] = 1
            expected = Series(1, index=index)
            tm.assert_series_equal(result, expected)

        # single element indexing

        # getitem
        assert indexer_sl(ser)[index[1]] == 1

        # setitem
        result = ser.copy()
        indexer_sl(result)[index[1]] = 5
        expected = Series([0, 5], index=index)
        tm.assert_series_equal(result, expected)

    def test_nanosecond_getitem_setitem_with_tz(self):
        # GH 11679
        data = ["2016-06-28 08:30:00.123456789"]
        index = pd.DatetimeIndex(data, dtype="datetime64[ns, America/Chicago]")
        df = DataFrame({"a": [10]}, index=index)
        result = df.loc[df.index[0]]
        expected = Series(10, index=["a"], name=df.index[0])
        tm.assert_series_equal(result, expected)

        result = df.copy()
        result.loc[df.index[0], "a"] = -1
        expected = DataFrame(-1, index=index, columns=["a"])
        tm.assert_frame_equal(result, expected)

    def test_getitem_str_slice_millisecond_resolution(self, frame_or_series):
        # GH#33589

        keys = [
            "2017-10-25T16:25:04.151",
            "2017-10-25T16:25:04.252",
            "2017-10-25T16:50:05.237",
            "2017-10-25T16:50:05.238",
        ]
        obj = frame_or_series(
            [1, 2, 3, 4],
            index=[Timestamp(x) for x in keys],
        )
        result = obj[keys[1] : keys[2]]
        expected = frame_or_series(
            [2, 3],
            index=[
                Timestamp(keys[1]),
                Timestamp(keys[2]),
            ],
        )
        tm.assert_equal(result, expected)

    def test_getitem_pyarrow_index(self, frame_or_series):
        # GH 53644
        pytest.importorskip("pyarrow")
        obj = frame_or_series(
            range(5),
            index=date_range("2020", freq="D", periods=5).astype(
                "timestamp[us][pyarrow]"
            ),
        )
        result = obj.loc[obj.index[:-3]]
        expected = frame_or_series(
            range(2),
            index=date_range("2020", freq="D", periods=2).astype(
                "timestamp[us][pyarrow]"
            ),
        )
        tm.assert_equal(result, expected)
