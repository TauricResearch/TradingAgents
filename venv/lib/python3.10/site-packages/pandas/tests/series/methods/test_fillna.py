from datetime import (
    datetime,
    timedelta,
    timezone,
)

import numpy as np
import pytest
import pytz

from pandas import (
    Categorical,
    DataFrame,
    DatetimeIndex,
    NaT,
    Period,
    Series,
    Timedelta,
    Timestamp,
    date_range,
    isna,
    timedelta_range,
)
import pandas._testing as tm
from pandas.core.arrays import period_array


@pytest.mark.filterwarnings(
    "ignore:(Series|DataFrame).fillna with 'method' is deprecated:FutureWarning"
)
class TestSeriesFillNA:
    def test_fillna_nat(self):
        series = Series([0, 1, 2, NaT._value], dtype="M8[ns]")

        filled = series.fillna(method="pad")
        filled2 = series.fillna(value=series.values[2])

        expected = series.copy()
        expected.iloc[3] = expected.iloc[2]

        tm.assert_series_equal(filled, expected)
        tm.assert_series_equal(filled2, expected)

        df = DataFrame({"A": series})
        filled = df.fillna(method="pad")
        filled2 = df.fillna(value=series.values[2])
        expected = DataFrame({"A": expected})
        tm.assert_frame_equal(filled, expected)
        tm.assert_frame_equal(filled2, expected)

        series = Series([NaT._value, 0, 1, 2], dtype="M8[ns]")

        filled = series.fillna(method="bfill")
        filled2 = series.fillna(value=series[1])

        expected = series.copy()
        expected[0] = expected[1]

        tm.assert_series_equal(filled, expected)
        tm.assert_series_equal(filled2, expected)

        df = DataFrame({"A": series})
        filled = df.fillna(method="bfill")
        filled2 = df.fillna(value=series[1])
        expected = DataFrame({"A": expected})
        tm.assert_frame_equal(filled, expected)
        tm.assert_frame_equal(filled2, expected)

    def test_fillna_value_or_method(self, datetime_series):
        msg = "Cannot specify both 'value' and 'method'"
        with pytest.raises(ValueError, match=msg):
            datetime_series.fillna(value=0, method="ffill")

    def test_fillna(self):
        ts = Series(
            [0.0, 1.0, 2.0, 3.0, 4.0], index=date_range("2020-01-01", periods=5)
        )

        tm.assert_series_equal(ts, ts.fillna(method="ffill"))

        ts.iloc[2] = np.nan

        exp = Series([0.0, 1.0, 1.0, 3.0, 4.0], index=ts.index)
        tm.assert_series_equal(ts.fillna(method="ffill"), exp)

        exp = Series([0.0, 1.0, 3.0, 3.0, 4.0], index=ts.index)
        tm.assert_series_equal(ts.fillna(method="backfill"), exp)

        exp = Series([0.0, 1.0, 5.0, 3.0, 4.0], index=ts.index)
        tm.assert_series_equal(ts.fillna(value=5), exp)

        msg = "Must specify a fill 'value' or 'method'"
        with pytest.raises(ValueError, match=msg):
            ts.fillna()

    def test_fillna_nonscalar(self):
        # GH#5703
        s1 = Series([np.nan])
        s2 = Series([1])
        result = s1.fillna(s2)
        expected = Series([1.0])
        tm.assert_series_equal(result, expected)
        result = s1.fillna({})
        tm.assert_series_equal(result, s1)
        result = s1.fillna(Series((), dtype=object))
        tm.assert_series_equal(result, s1)
        result = s2.fillna(s1)
        tm.assert_series_equal(result, s2)
        result = s1.fillna({0: 1})
        tm.assert_series_equal(result, expected)
        result = s1.fillna({1: 1})
        tm.assert_series_equal(result, Series([np.nan]))
        result = s1.fillna({0: 1, 1: 1})
        tm.assert_series_equal(result, expected)
        result = s1.fillna(Series({0: 1, 1: 1}))
        tm.assert_series_equal(result, expected)
        result = s1.fillna(Series({0: 1, 1: 1}, index=[4, 5]))
        tm.assert_series_equal(result, s1)

    def test_fillna_aligns(self):
        s1 = Series([0, 1, 2], list("abc"))
        s2 = Series([0, np.nan, 2], list("bac"))
        result = s2.fillna(s1)
        expected = Series([0, 0, 2.0], list("bac"))
        tm.assert_series_equal(result, expected)

    def test_fillna_limit(self):
        ser = Series(np.nan, index=[0, 1, 2])
        result = ser.fillna(999, limit=1)
        expected = Series([999, np.nan, np.nan], index=[0, 1, 2])
        tm.assert_series_equal(result, expected)

        result = ser.fillna(999, limit=2)
        expected = Series([999, 999, np.nan], index=[0, 1, 2])
        tm.assert_series_equal(result, expected)

    def test_fillna_dont_cast_strings(self):
        # GH#9043
        # make sure a string representation of int/float values can be filled
        # correctly without raising errors or being converted
        vals = ["0", "1.5", "-0.3"]
        for val in vals:
            ser = Series([0, 1, np.nan, np.nan, 4], dtype="float64")
            result = ser.fillna(val)
            expected = Series([0, 1, val, val, 4], dtype="object")
            tm.assert_series_equal(result, expected)

    def test_fillna_consistency(self):
        # GH#16402
        # fillna with a tz aware to a tz-naive, should result in object

        ser = Series([Timestamp("20130101"), NaT])

        result = ser.fillna(Timestamp("20130101", tz="US/Eastern"))
        expected = Series(
            [Timestamp("20130101"), Timestamp("2013-01-01", tz="US/Eastern")],
            dtype="object",
        )
        tm.assert_series_equal(result, expected)

        result = ser.where([True, False], Timestamp("20130101", tz="US/Eastern"))
        tm.assert_series_equal(result, expected)

        result = ser.where([True, False], Timestamp("20130101", tz="US/Eastern"))
        tm.assert_series_equal(result, expected)

        # with a non-datetime
        result = ser.fillna("foo")
        expected = Series([Timestamp("20130101"), "foo"])
        tm.assert_series_equal(result, expected)

        # assignment
        ser2 = ser.copy()
        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            ser2[1] = "foo"
        tm.assert_series_equal(ser2, expected)

    def test_fillna_downcast(self):
        # GH#15277
        # infer int64 from float64
        ser = Series([1.0, np.nan])
        msg = "The 'downcast' keyword in fillna is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = ser.fillna(0, downcast="infer")
        expected = Series([1, 0])
        tm.assert_series_equal(result, expected)

        # infer int64 from float64 when fillna value is a dict
        ser = Series([1.0, np.nan])
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = ser.fillna({1: 0}, downcast="infer")
        expected = Series([1, 0])
        tm.assert_series_equal(result, expected)

    def test_fillna_downcast_infer_objects_to_numeric(self):
        # GH#44241 if we have object-dtype, 'downcast="infer"' should
        #  _actually_ infer

        arr = np.arange(5).astype(object)
        arr[3] = np.nan

        ser = Series(arr)

        msg = "The 'downcast' keyword in fillna is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = ser.fillna(3, downcast="infer")
        expected = Series(np.arange(5), dtype=np.int64)
        tm.assert_series_equal(res, expected)

        msg = "The 'downcast' keyword in ffill is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = ser.ffill(downcast="infer")
        expected = Series([0, 1, 2, 2, 4], dtype=np.int64)
        tm.assert_series_equal(res, expected)

        msg = "The 'downcast' keyword in bfill is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = ser.bfill(downcast="infer")
        expected = Series([0, 1, 2, 4, 4], dtype=np.int64)
        tm.assert_series_equal(res, expected)

        # with a non-round float present, we will downcast to float64
        ser[2] = 2.5

        expected = Series([0, 1, 2.5, 3, 4], dtype=np.float64)
        msg = "The 'downcast' keyword in fillna is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = ser.fillna(3, downcast="infer")
        tm.assert_series_equal(res, expected)

        msg = "The 'downcast' keyword in ffill is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = ser.ffill(downcast="infer")
        expected = Series([0, 1, 2.5, 2.5, 4], dtype=np.float64)
        tm.assert_series_equal(res, expected)

        msg = "The 'downcast' keyword in bfill is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = ser.bfill(downcast="infer")
        expected = Series([0, 1, 2.5, 4, 4], dtype=np.float64)
        tm.assert_series_equal(res, expected)

    def test_timedelta_fillna(self, frame_or_series, unit):
        # GH#3371
        ser = Series(
            [
                Timestamp("20130101"),
                Timestamp("20130101"),
                Timestamp("20130102"),
                Timestamp("20130103 9:01:01"),
            ],
            dtype=f"M8[{unit}]",
        )
        td = ser.diff()
        obj = frame_or_series(td).copy()

        # reg fillna
        result = obj.fillna(Timedelta(seconds=0))
        expected = Series(
            [
                timedelta(0),
                timedelta(0),
                timedelta(1),
                timedelta(days=1, seconds=9 * 3600 + 60 + 1),
            ],
            dtype=f"m8[{unit}]",
        )
        expected = frame_or_series(expected)
        tm.assert_equal(result, expected)

        # GH#45746 pre-1.? ints were interpreted as seconds.  then that was
        #  deprecated and changed to raise. In 2.0 it casts to common dtype,
        #  consistent with every other dtype's behavior
        res = obj.fillna(1)
        expected = obj.astype(object).fillna(1)
        tm.assert_equal(res, expected)

        result = obj.fillna(Timedelta(seconds=1))
        expected = Series(
            [
                timedelta(seconds=1),
                timedelta(0),
                timedelta(1),
                timedelta(days=1, seconds=9 * 3600 + 60 + 1),
            ],
            dtype=f"m8[{unit}]",
        )
        expected = frame_or_series(expected)
        tm.assert_equal(result, expected)

        result = obj.fillna(timedelta(days=1, seconds=1))
        expected = Series(
            [
                timedelta(days=1, seconds=1),
                timedelta(0),
                timedelta(1),
                timedelta(days=1, seconds=9 * 3600 + 60 + 1),
            ],
            dtype=f"m8[{unit}]",
        )
        expected = frame_or_series(expected)
        tm.assert_equal(result, expected)

        result = obj.fillna(np.timedelta64(10**9))
        expected = Series(
            [
                timedelta(seconds=1),
                timedelta(0),
                timedelta(1),
                timedelta(days=1, seconds=9 * 3600 + 60 + 1),
            ],
            dtype=f"m8[{unit}]",
        )
        expected = frame_or_series(expected)
        tm.assert_equal(result, expected)

        result = obj.fillna(NaT)
        expected = Series(
            [
                NaT,
                timedelta(0),
                timedelta(1),
                timedelta(days=1, seconds=9 * 3600 + 60 + 1),
            ],
            dtype=f"m8[{unit}]",
        )
        expected = frame_or_series(expected)
        tm.assert_equal(result, expected)

        # ffill
        td[2] = np.nan
        obj = frame_or_series(td).copy()
        result = obj.ffill()
        expected = td.fillna(Timedelta(seconds=0))
        expected[0] = np.nan
        expected = frame_or_series(expected)

        tm.assert_equal(result, expected)

        # bfill
        td[2] = np.nan
        obj = frame_or_series(td)
        result = obj.bfill()
        expected = td.fillna(Timedelta(seconds=0))
        expected[2] = timedelta(days=1, seconds=9 * 3600 + 60 + 1)
        expected = frame_or_series(expected)
        tm.assert_equal(result, expected)

    def test_datetime64_fillna(self):
        ser = Series(
            [
                Timestamp("20130101"),
                Timestamp("20130101"),
                Timestamp("20130102"),
                Timestamp("20130103 9:01:01"),
            ]
        )
        ser[2] = np.nan

        # ffill
        result = ser.ffill()
        expected = Series(
            [
                Timestamp("20130101"),
                Timestamp("20130101"),
                Timestamp("20130101"),
                Timestamp("20130103 9:01:01"),
            ]
        )
        tm.assert_series_equal(result, expected)

        # bfill
        result = ser.bfill()
        expected = Series(
            [
                Timestamp("20130101"),
                Timestamp("20130101"),
                Timestamp("20130103 9:01:01"),
                Timestamp("20130103 9:01:01"),
            ]
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "scalar",
        [
            False,
            pytest.param(
                True,
                marks=pytest.mark.xfail(
                    reason="GH#56410 scalar case not yet addressed"
                ),
            ),
        ],
    )
    @pytest.mark.parametrize("tz", [None, "UTC"])
    def test_datetime64_fillna_mismatched_reso_no_rounding(self, tz, scalar):
        # GH#56410
        dti = date_range("2016-01-01", periods=3, unit="s", tz=tz)
        item = Timestamp("2016-02-03 04:05:06.789", tz=tz)
        vec = date_range(item, periods=3, unit="ms")

        exp_dtype = "M8[ms]" if tz is None else "M8[ms, UTC]"
        expected = Series([item, dti[1], dti[2]], dtype=exp_dtype)

        ser = Series(dti)
        ser[0] = NaT
        ser2 = ser.copy()

        res = ser.fillna(item)
        res2 = ser2.fillna(Series(vec))

        if scalar:
            tm.assert_series_equal(res, expected)
        else:
            tm.assert_series_equal(res2, expected)

    @pytest.mark.parametrize(
        "scalar",
        [
            False,
            pytest.param(
                True,
                marks=pytest.mark.xfail(
                    reason="GH#56410 scalar case not yet addressed"
                ),
            ),
        ],
    )
    def test_timedelta64_fillna_mismatched_reso_no_rounding(self, scalar):
        # GH#56410
        tdi = date_range("2016-01-01", periods=3, unit="s") - Timestamp("1970-01-01")
        item = Timestamp("2016-02-03 04:05:06.789") - Timestamp("1970-01-01")
        vec = timedelta_range(item, periods=3, unit="ms")

        expected = Series([item, tdi[1], tdi[2]], dtype="m8[ms]")

        ser = Series(tdi)
        ser[0] = NaT
        ser2 = ser.copy()

        res = ser.fillna(item)
        res2 = ser2.fillna(Series(vec))

        if scalar:
            tm.assert_series_equal(res, expected)
        else:
            tm.assert_series_equal(res2, expected)

    def test_datetime64_fillna_backfill(self):
        # GH#6587
        # make sure that we are treating as integer when filling
        ser = Series([NaT, NaT, "2013-08-05 15:30:00.000001"], dtype="M8[ns]")

        expected = Series(
            [
                "2013-08-05 15:30:00.000001",
                "2013-08-05 15:30:00.000001",
                "2013-08-05 15:30:00.000001",
            ],
            dtype="M8[ns]",
        )
        result = ser.fillna(method="backfill")
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("tz", ["US/Eastern", "Asia/Tokyo"])
    def test_datetime64_tz_fillna(self, tz, unit):
        # DatetimeLikeBlock
        ser = Series(
            [
                Timestamp("2011-01-01 10:00"),
                NaT,
                Timestamp("2011-01-03 10:00"),
                NaT,
            ],
            dtype=f"M8[{unit}]",
        )
        null_loc = Series([False, True, False, True])

        result = ser.fillna(Timestamp("2011-01-02 10:00"))
        expected = Series(
            [
                Timestamp("2011-01-01 10:00"),
                Timestamp("2011-01-02 10:00"),
                Timestamp("2011-01-03 10:00"),
                Timestamp("2011-01-02 10:00"),
            ],
            dtype=f"M8[{unit}]",
        )
        tm.assert_series_equal(expected, result)
        # check s is not changed
        tm.assert_series_equal(isna(ser), null_loc)

        result = ser.fillna(Timestamp("2011-01-02 10:00", tz=tz))
        expected = Series(
            [
                Timestamp("2011-01-01 10:00"),
                Timestamp("2011-01-02 10:00", tz=tz),
                Timestamp("2011-01-03 10:00"),
                Timestamp("2011-01-02 10:00", tz=tz),
            ]
        )
        tm.assert_series_equal(expected, result)
        tm.assert_series_equal(isna(ser), null_loc)

        result = ser.fillna("AAA")
        expected = Series(
            [
                Timestamp("2011-01-01 10:00"),
                "AAA",
                Timestamp("2011-01-03 10:00"),
                "AAA",
            ],
            dtype=object,
        )
        tm.assert_series_equal(expected, result)
        tm.assert_series_equal(isna(ser), null_loc)

        result = ser.fillna(
            {
                1: Timestamp("2011-01-02 10:00", tz=tz),
                3: Timestamp("2011-01-04 10:00"),
            }
        )
        expected = Series(
            [
                Timestamp("2011-01-01 10:00"),
                Timestamp("2011-01-02 10:00", tz=tz),
                Timestamp("2011-01-03 10:00"),
                Timestamp("2011-01-04 10:00"),
            ]
        )
        tm.assert_series_equal(expected, result)
        tm.assert_series_equal(isna(ser), null_loc)

        result = ser.fillna(
            {1: Timestamp("2011-01-02 10:00"), 3: Timestamp("2011-01-04 10:00")}
        )
        expected = Series(
            [
                Timestamp("2011-01-01 10:00"),
                Timestamp("2011-01-02 10:00"),
                Timestamp("2011-01-03 10:00"),
                Timestamp("2011-01-04 10:00"),
            ],
            dtype=f"M8[{unit}]",
        )
        tm.assert_series_equal(expected, result)
        tm.assert_series_equal(isna(ser), null_loc)

        # DatetimeTZBlock
        idx = DatetimeIndex(
            ["2011-01-01 10:00", NaT, "2011-01-03 10:00", NaT], tz=tz
        ).as_unit(unit)
        ser = Series(idx)
        assert ser.dtype == f"datetime64[{unit}, {tz}]"
        tm.assert_series_equal(isna(ser), null_loc)

        result = ser.fillna(Timestamp("2011-01-02 10:00"))
        expected = Series(
            [
                Timestamp("2011-01-01 10:00", tz=tz),
                Timestamp("2011-01-02 10:00"),
                Timestamp("2011-01-03 10:00", tz=tz),
                Timestamp("2011-01-02 10:00"),
            ]
        )
        tm.assert_series_equal(expected, result)
        tm.assert_series_equal(isna(ser), null_loc)

        result = ser.fillna(Timestamp("2011-01-02 10:00", tz=tz))
        idx = DatetimeIndex(
            [
                "2011-01-01 10:00",
                "2011-01-02 10:00",
                "2011-01-03 10:00",
                "2011-01-02 10:00",
            ],
            tz=tz,
        ).as_unit(unit)
        expected = Series(idx)
        tm.assert_series_equal(expected, result)
        tm.assert_series_equal(isna(ser), null_loc)

        result = ser.fillna(Timestamp("2011-01-02 10:00", tz=tz).to_pydatetime())
        idx = DatetimeIndex(
            [
                "2011-01-01 10:00",
                "2011-01-02 10:00",
                "2011-01-03 10:00",
                "2011-01-02 10:00",
            ],
            tz=tz,
        ).as_unit(unit)
        expected = Series(idx)
        tm.assert_series_equal(expected, result)
        tm.assert_series_equal(isna(ser), null_loc)

        result = ser.fillna("AAA")
        expected = Series(
            [
                Timestamp("2011-01-01 10:00", tz=tz),
                "AAA",
                Timestamp("2011-01-03 10:00", tz=tz),
                "AAA",
            ],
            dtype=object,
        )
        tm.assert_series_equal(expected, result)
        tm.assert_series_equal(isna(ser), null_loc)

        result = ser.fillna(
            {
                1: Timestamp("2011-01-02 10:00", tz=tz),
                3: Timestamp("2011-01-04 10:00"),
            }
        )
        expected = Series(
            [
                Timestamp("2011-01-01 10:00", tz=tz),
                Timestamp("2011-01-02 10:00", tz=tz),
                Timestamp("2011-01-03 10:00", tz=tz),
                Timestamp("2011-01-04 10:00"),
            ]
        )
        tm.assert_series_equal(expected, result)
        tm.assert_series_equal(isna(ser), null_loc)

        result = ser.fillna(
            {
                1: Timestamp("2011-01-02 10:00", tz=tz),
                3: Timestamp("2011-01-04 10:00", tz=tz),
            }
        )
        expected = Series(
            [
                Timestamp("2011-01-01 10:00", tz=tz),
                Timestamp("2011-01-02 10:00", tz=tz),
                Timestamp("2011-01-03 10:00", tz=tz),
                Timestamp("2011-01-04 10:00", tz=tz),
            ]
        ).dt.as_unit(unit)
        tm.assert_series_equal(expected, result)
        tm.assert_series_equal(isna(ser), null_loc)

        # filling with a naive/other zone, coerce to object
        result = ser.fillna(Timestamp("20130101"))
        expected = Series(
            [
                Timestamp("2011-01-01 10:00", tz=tz),
                Timestamp("2013-01-01"),
                Timestamp("2011-01-03 10:00", tz=tz),
                Timestamp("2013-01-01"),
            ]
        )
        tm.assert_series_equal(expected, result)
        tm.assert_series_equal(isna(ser), null_loc)

        # pre-2.0 fillna with mixed tzs would cast to object, in 2.0
        #  it retains dtype.
        result = ser.fillna(Timestamp("20130101", tz="US/Pacific"))
        expected = Series(
            [
                Timestamp("2011-01-01 10:00", tz=tz),
                Timestamp("2013-01-01", tz="US/Pacific").tz_convert(tz),
                Timestamp("2011-01-03 10:00", tz=tz),
                Timestamp("2013-01-01", tz="US/Pacific").tz_convert(tz),
            ]
        ).dt.as_unit(unit)
        tm.assert_series_equal(expected, result)
        tm.assert_series_equal(isna(ser), null_loc)

    def test_fillna_dt64tz_with_method(self):
        # with timezone
        # GH#15855
        ser = Series([Timestamp("2012-11-11 00:00:00+01:00"), NaT])
        exp = Series(
            [
                Timestamp("2012-11-11 00:00:00+01:00"),
                Timestamp("2012-11-11 00:00:00+01:00"),
            ]
        )
        tm.assert_series_equal(ser.fillna(method="pad"), exp)

        ser = Series([NaT, Timestamp("2012-11-11 00:00:00+01:00")])
        exp = Series(
            [
                Timestamp("2012-11-11 00:00:00+01:00"),
                Timestamp("2012-11-11 00:00:00+01:00"),
            ]
        )
        tm.assert_series_equal(ser.fillna(method="bfill"), exp)

    def test_fillna_pytimedelta(self):
        # GH#8209
        ser = Series([np.nan, Timedelta("1 days")], index=["A", "B"])

        result = ser.fillna(timedelta(1))
        expected = Series(Timedelta("1 days"), index=["A", "B"])
        tm.assert_series_equal(result, expected)

    def test_fillna_period(self):
        # GH#13737
        ser = Series([Period("2011-01", freq="M"), Period("NaT", freq="M")])

        res = ser.fillna(Period("2012-01", freq="M"))
        exp = Series([Period("2011-01", freq="M"), Period("2012-01", freq="M")])
        tm.assert_series_equal(res, exp)
        assert res.dtype == "Period[M]"

    def test_fillna_dt64_timestamp(self, frame_or_series):
        ser = Series(
            [
                Timestamp("20130101"),
                Timestamp("20130101"),
                Timestamp("20130102"),
                Timestamp("20130103 9:01:01"),
            ]
        )
        ser[2] = np.nan
        obj = frame_or_series(ser)

        # reg fillna
        result = obj.fillna(Timestamp("20130104"))
        expected = Series(
            [
                Timestamp("20130101"),
                Timestamp("20130101"),
                Timestamp("20130104"),
                Timestamp("20130103 9:01:01"),
            ]
        )
        expected = frame_or_series(expected)
        tm.assert_equal(result, expected)

        result = obj.fillna(NaT)
        expected = obj
        tm.assert_equal(result, expected)

    def test_fillna_dt64_non_nao(self):
        # GH#27419
        ser = Series([Timestamp("2010-01-01"), NaT, Timestamp("2000-01-01")])
        val = np.datetime64("1975-04-05", "ms")

        result = ser.fillna(val)
        expected = Series(
            [Timestamp("2010-01-01"), Timestamp("1975-04-05"), Timestamp("2000-01-01")]
        )
        tm.assert_series_equal(result, expected)

    def test_fillna_numeric_inplace(self):
        x = Series([np.nan, 1.0, np.nan, 3.0, np.nan], ["z", "a", "b", "c", "d"])
        y = x.copy()

        return_value = y.fillna(value=0, inplace=True)
        assert return_value is None

        expected = x.fillna(value=0)
        tm.assert_series_equal(y, expected)

    # ---------------------------------------------------------------
    # CategoricalDtype

    @pytest.mark.parametrize(
        "fill_value, expected_output",
        [
            ("a", ["a", "a", "b", "a", "a"]),
            ({1: "a", 3: "b", 4: "b"}, ["a", "a", "b", "b", "b"]),
            ({1: "a"}, ["a", "a", "b", np.nan, np.nan]),
            ({1: "a", 3: "b"}, ["a", "a", "b", "b", np.nan]),
            (Series("a"), ["a", np.nan, "b", np.nan, np.nan]),
            (Series("a", index=[1]), ["a", "a", "b", np.nan, np.nan]),
            (Series({1: "a", 3: "b"}), ["a", "a", "b", "b", np.nan]),
            (Series(["a", "b"], index=[3, 4]), ["a", np.nan, "b", "a", "b"]),
        ],
    )
    def test_fillna_categorical(self, fill_value, expected_output):
        # GH#17033
        # Test fillna for a Categorical series
        data = ["a", np.nan, "b", np.nan, np.nan]
        ser = Series(Categorical(data, categories=["a", "b"]))
        exp = Series(Categorical(expected_output, categories=["a", "b"]))
        result = ser.fillna(fill_value)
        tm.assert_series_equal(result, exp)

    @pytest.mark.parametrize(
        "fill_value, expected_output",
        [
            (Series(["a", "b", "c", "d", "e"]), ["a", "b", "b", "d", "e"]),
            (Series(["b", "d", "a", "d", "a"]), ["a", "d", "b", "d", "a"]),
            (
                Series(
                    Categorical(
                        ["b", "d", "a", "d", "a"], categories=["b", "c", "d", "e", "a"]
                    )
                ),
                ["a", "d", "b", "d", "a"],
            ),
        ],
    )
    def test_fillna_categorical_with_new_categories(self, fill_value, expected_output):
        # GH#26215
        data = ["a", np.nan, "b", np.nan, np.nan]
        ser = Series(Categorical(data, categories=["a", "b", "c", "d", "e"]))
        exp = Series(Categorical(expected_output, categories=["a", "b", "c", "d", "e"]))
        result = ser.fillna(fill_value)
        tm.assert_series_equal(result, exp)

    def test_fillna_categorical_raises(self):
        data = ["a", np.nan, "b", np.nan, np.nan]
        ser = Series(Categorical(data, categories=["a", "b"]))
        cat = ser._values

        msg = "Cannot setitem on a Categorical with a new category"
        with pytest.raises(TypeError, match=msg):
            ser.fillna("d")

        msg2 = "Length of 'value' does not match."
        with pytest.raises(ValueError, match=msg2):
            cat.fillna(Series("d"))

        with pytest.raises(TypeError, match=msg):
            ser.fillna({1: "d", 3: "a"})

        msg = '"value" parameter must be a scalar or dict, but you passed a "list"'
        with pytest.raises(TypeError, match=msg):
            ser.fillna(["a", "b"])

        msg = '"value" parameter must be a scalar or dict, but you passed a "tuple"'
        with pytest.raises(TypeError, match=msg):
            ser.fillna(("a", "b"))

        msg = (
            '"value" parameter must be a scalar, dict '
            'or Series, but you passed a "DataFrame"'
        )
        with pytest.raises(TypeError, match=msg):
            ser.fillna(DataFrame({1: ["a"], 3: ["b"]}))

    @pytest.mark.parametrize("dtype", [float, "float32", "float64"])
    @pytest.mark.parametrize("fill_type", tm.ALL_REAL_NUMPY_DTYPES)
    @pytest.mark.parametrize("scalar", [True, False])
    def test_fillna_float_casting(self, dtype, fill_type, scalar):
        # GH-43424
        ser = Series([np.nan, 1.2], dtype=dtype)
        fill_values = Series([2, 2], dtype=fill_type)
        if scalar:
            fill_values = fill_values.dtype.type(2)

        result = ser.fillna(fill_values)
        expected = Series([2.0, 1.2], dtype=dtype)
        tm.assert_series_equal(result, expected)

        ser = Series([np.nan, 1.2], dtype=dtype)
        mask = ser.isna().to_numpy()
        ser[mask] = fill_values
        tm.assert_series_equal(ser, expected)

        ser = Series([np.nan, 1.2], dtype=dtype)
        ser.mask(mask, fill_values, inplace=True)
        tm.assert_series_equal(ser, expected)

        ser = Series([np.nan, 1.2], dtype=dtype)
        res = ser.where(~mask, fill_values)
        tm.assert_series_equal(res, expected)

    def test_fillna_f32_upcast_with_dict(self):
        # GH-43424
        ser = Series([np.nan, 1.2], dtype=np.float32)
        result = ser.fillna({0: 1})
        expected = Series([1.0, 1.2], dtype=np.float32)
        tm.assert_series_equal(result, expected)

    # ---------------------------------------------------------------
    # Invalid Usages

    def test_fillna_invalid_method(self, datetime_series):
        try:
            datetime_series.fillna(method="ffil")
        except ValueError as inst:
            assert "ffil" in str(inst)

    def test_fillna_listlike_invalid(self):
        ser = Series(np.random.default_rng(2).integers(-100, 100, 50))
        msg = '"value" parameter must be a scalar or dict, but you passed a "list"'
        with pytest.raises(TypeError, match=msg):
            ser.fillna([1, 2])

        msg = '"value" parameter must be a scalar or dict, but you passed a "tuple"'
        with pytest.raises(TypeError, match=msg):
            ser.fillna((1, 2))

    def test_fillna_method_and_limit_invalid(self):
        # related GH#9217, make sure limit is an int and greater than 0
        ser = Series([1, 2, 3, None])
        msg = "|".join(
            [
                r"Cannot specify both 'value' and 'method'\.",
                "Limit must be greater than 0",
                "Limit must be an integer",
            ]
        )
        for limit in [-1, 0, 1.0, 2.0]:
            for method in ["backfill", "bfill", "pad", "ffill", None]:
                with pytest.raises(ValueError, match=msg):
                    ser.fillna(1, limit=limit, method=method)

    def test_fillna_datetime64_with_timezone_tzinfo(self):
        # https://github.com/pandas-dev/pandas/issues/38851
        # different tzinfos representing UTC treated as equal
        ser = Series(date_range("2020", periods=3, tz="UTC"))
        expected = ser.copy()
        ser[1] = NaT
        result = ser.fillna(datetime(2020, 1, 2, tzinfo=timezone.utc))
        tm.assert_series_equal(result, expected)

        # pre-2.0 we cast to object with mixed tzs, in 2.0 we retain dtype
        ts = Timestamp("2000-01-01", tz="US/Pacific")
        ser2 = Series(ser._values.tz_convert("dateutil/US/Pacific"))
        assert ser2.dtype.kind == "M"
        result = ser2.fillna(ts)
        expected = Series(
            [ser2[0], ts.tz_convert(ser2.dtype.tz), ser2[2]],
            dtype=ser2.dtype,
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "input, input_fillna, expected_data, expected_categories",
        [
            (["A", "B", None, "A"], "B", ["A", "B", "B", "A"], ["A", "B"]),
            (["A", "B", np.nan, "A"], "B", ["A", "B", "B", "A"], ["A", "B"]),
        ],
    )
    def test_fillna_categorical_accept_same_type(
        self, input, input_fillna, expected_data, expected_categories
    ):
        # GH32414
        cat = Categorical(input)
        ser = Series(cat).fillna(input_fillna)
        filled = cat.fillna(ser)
        result = cat.fillna(filled)
        expected = Categorical(expected_data, categories=expected_categories)
        tm.assert_categorical_equal(result, expected)


@pytest.mark.filterwarnings(
    "ignore:Series.fillna with 'method' is deprecated:FutureWarning"
)
class TestFillnaPad:
    def test_fillna_bug(self):
        ser = Series([np.nan, 1.0, np.nan, 3.0, np.nan], ["z", "a", "b", "c", "d"])
        filled = ser.fillna(method="ffill")
        expected = Series([np.nan, 1.0, 1.0, 3.0, 3.0], ser.index)
        tm.assert_series_equal(filled, expected)

        filled = ser.fillna(method="bfill")
        expected = Series([1.0, 1.0, 3.0, 3.0, np.nan], ser.index)
        tm.assert_series_equal(filled, expected)

    def test_ffill(self):
        ts = Series(
            [0.0, 1.0, 2.0, 3.0, 4.0], index=date_range("2020-01-01", periods=5)
        )
        ts.iloc[2] = np.nan
        tm.assert_series_equal(ts.ffill(), ts.fillna(method="ffill"))

    def test_ffill_mixed_dtypes_without_missing_data(self):
        # GH#14956
        series = Series([datetime(2015, 1, 1, tzinfo=pytz.utc), 1])
        result = series.ffill()
        tm.assert_series_equal(series, result)

    def test_bfill(self):
        ts = Series(
            [0.0, 1.0, 2.0, 3.0, 4.0], index=date_range("2020-01-01", periods=5)
        )
        ts.iloc[2] = np.nan
        tm.assert_series_equal(ts.bfill(), ts.fillna(method="bfill"))

    def test_pad_nan(self):
        x = Series(
            [np.nan, 1.0, np.nan, 3.0, np.nan], ["z", "a", "b", "c", "d"], dtype=float
        )

        return_value = x.fillna(method="pad", inplace=True)
        assert return_value is None

        expected = Series(
            [np.nan, 1.0, 1.0, 3.0, 3.0], ["z", "a", "b", "c", "d"], dtype=float
        )
        tm.assert_series_equal(x[1:], expected[1:])
        assert np.isnan(x.iloc[0]), np.isnan(expected.iloc[0])

    def test_series_fillna_limit(self):
        index = np.arange(10)
        s = Series(np.random.default_rng(2).standard_normal(10), index=index)

        result = s[:2].reindex(index)
        result = result.fillna(method="pad", limit=5)

        expected = s[:2].reindex(index).fillna(method="pad")
        expected[-3:] = np.nan
        tm.assert_series_equal(result, expected)

        result = s[-2:].reindex(index)
        result = result.fillna(method="bfill", limit=5)

        expected = s[-2:].reindex(index).fillna(method="backfill")
        expected[:3] = np.nan
        tm.assert_series_equal(result, expected)

    def test_series_pad_backfill_limit(self):
        index = np.arange(10)
        s = Series(np.random.default_rng(2).standard_normal(10), index=index)

        result = s[:2].reindex(index, method="pad", limit=5)

        expected = s[:2].reindex(index).fillna(method="pad")
        expected[-3:] = np.nan
        tm.assert_series_equal(result, expected)

        result = s[-2:].reindex(index, method="backfill", limit=5)

        expected = s[-2:].reindex(index).fillna(method="backfill")
        expected[:3] = np.nan
        tm.assert_series_equal(result, expected)

    def test_fillna_int(self):
        ser = Series(np.random.default_rng(2).integers(-100, 100, 50))
        return_value = ser.fillna(method="ffill", inplace=True)
        assert return_value is None
        tm.assert_series_equal(ser.fillna(method="ffill", inplace=False), ser)

    def test_datetime64tz_fillna_round_issue(self):
        # GH#14872

        data = Series(
            [NaT, NaT, datetime(2016, 12, 12, 22, 24, 6, 100001, tzinfo=pytz.utc)]
        )

        filled = data.bfill()

        expected = Series(
            [
                datetime(2016, 12, 12, 22, 24, 6, 100001, tzinfo=pytz.utc),
                datetime(2016, 12, 12, 22, 24, 6, 100001, tzinfo=pytz.utc),
                datetime(2016, 12, 12, 22, 24, 6, 100001, tzinfo=pytz.utc),
            ]
        )

        tm.assert_series_equal(filled, expected)

    def test_fillna_parr(self):
        # GH-24537
        dti = date_range(
            Timestamp.max - Timedelta(nanoseconds=10), periods=5, freq="ns"
        )
        ser = Series(dti.to_period("ns"))
        ser[2] = NaT
        arr = period_array(
            [
                Timestamp("2262-04-11 23:47:16.854775797"),
                Timestamp("2262-04-11 23:47:16.854775798"),
                Timestamp("2262-04-11 23:47:16.854775798"),
                Timestamp("2262-04-11 23:47:16.854775800"),
                Timestamp("2262-04-11 23:47:16.854775801"),
            ],
            freq="ns",
        )
        expected = Series(arr)

        filled = ser.ffill()

        tm.assert_series_equal(filled, expected)

    @pytest.mark.parametrize("func", ["pad", "backfill"])
    def test_pad_backfill_deprecated(self, func):
        # GH#33396
        ser = Series([1, 2, 3])
        with tm.assert_produces_warning(FutureWarning):
            getattr(ser, func)()


@pytest.mark.parametrize(
    "data, expected_data, method, kwargs",
    (
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [np.nan, np.nan, 3.0, 3.0, 3.0, 3.0, 7.0, np.nan, np.nan],
            "ffill",
            {"limit_area": "inside"},
        ),
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [np.nan, np.nan, 3.0, 3.0, np.nan, np.nan, 7.0, np.nan, np.nan],
            "ffill",
            {"limit_area": "inside", "limit": 1},
        ),
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [np.nan, np.nan, 3.0, np.nan, np.nan, np.nan, 7.0, 7.0, 7.0],
            "ffill",
            {"limit_area": "outside"},
        ),
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [np.nan, np.nan, 3.0, np.nan, np.nan, np.nan, 7.0, 7.0, np.nan],
            "ffill",
            {"limit_area": "outside", "limit": 1},
        ),
        (
            [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan],
            [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan],
            "ffill",
            {"limit_area": "outside", "limit": 1},
        ),
        (
            range(5),
            range(5),
            "ffill",
            {"limit_area": "outside", "limit": 1},
        ),
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [np.nan, np.nan, 3.0, 7.0, 7.0, 7.0, 7.0, np.nan, np.nan],
            "bfill",
            {"limit_area": "inside"},
        ),
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [np.nan, np.nan, 3.0, np.nan, np.nan, 7.0, 7.0, np.nan, np.nan],
            "bfill",
            {"limit_area": "inside", "limit": 1},
        ),
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [3.0, 3.0, 3.0, np.nan, np.nan, np.nan, 7.0, np.nan, np.nan],
            "bfill",
            {"limit_area": "outside"},
        ),
        (
            [np.nan, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan, np.nan],
            [np.nan, 3.0, 3.0, np.nan, np.nan, np.nan, 7.0, np.nan, np.nan],
            "bfill",
            {"limit_area": "outside", "limit": 1},
        ),
    ),
)
def test_ffill_bfill_limit_area(data, expected_data, method, kwargs):
    # GH#56492
    s = Series(data)
    expected = Series(expected_data)
    result = getattr(s, method)(**kwargs)
    tm.assert_series_equal(result, expected)
