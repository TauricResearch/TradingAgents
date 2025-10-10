from datetime import (
    date,
    datetime,
    timedelta,
)
import re

import numpy as np
import pytest

from pandas._libs.tslibs import iNaT
from pandas._libs.tslibs.ccalendar import (
    DAYS,
    MONTHS,
)
from pandas._libs.tslibs.np_datetime import OutOfBoundsDatetime
from pandas._libs.tslibs.parsing import DateParseError
from pandas._libs.tslibs.period import INVALID_FREQ_ERR_MSG
from pandas.compat import PY314

from pandas import (
    NaT,
    Period,
    Timedelta,
    Timestamp,
    offsets,
)
import pandas._testing as tm

bday_msg = "Period with BDay freq is deprecated"


class TestPeriodDisallowedFreqs:
    @pytest.mark.parametrize(
        "freq, freq_msg",
        [
            (offsets.BYearBegin(), "BYearBegin"),
            (offsets.YearBegin(2), "YearBegin"),
            (offsets.QuarterBegin(startingMonth=12), "QuarterBegin"),
            (offsets.BusinessMonthEnd(2), "BusinessMonthEnd"),
        ],
    )
    def test_offsets_not_supported(self, freq, freq_msg):
        # GH#55785
        msg = re.escape(f"{freq} is not supported as period frequency")
        with pytest.raises(ValueError, match=msg):
            Period(year=2014, freq=freq)

    def test_custom_business_day_freq_raises(self):
        # GH#52534
        msg = "C is not supported as period frequency"
        with pytest.raises(ValueError, match=msg):
            Period("2023-04-10", freq="C")
        msg = f"{offsets.CustomBusinessDay().base} is not supported as period frequency"
        with pytest.raises(ValueError, match=msg):
            Period("2023-04-10", freq=offsets.CustomBusinessDay())

    def test_invalid_frequency_error_message(self):
        msg = "WOM-1MON is not supported as period frequency"
        with pytest.raises(ValueError, match=msg):
            Period("2012-01-02", freq="WOM-1MON")

    def test_invalid_frequency_period_error_message(self):
        msg = "for Period, please use 'M' instead of 'ME'"
        with pytest.raises(ValueError, match=msg):
            Period("2012-01-02", freq="ME")


class TestPeriodConstruction:
    def test_from_td64nat_raises(self):
        # GH#44507
        td = NaT.to_numpy("m8[ns]")

        msg = "Value must be Period, string, integer, or datetime"
        with pytest.raises(ValueError, match=msg):
            Period(td)

        with pytest.raises(ValueError, match=msg):
            Period(td, freq="D")

    def test_construction(self):
        i1 = Period("1/1/2005", freq="M")
        i2 = Period("Jan 2005")

        assert i1 == i2

        # GH#54105 - Period can be confusingly instantiated with lowercase freq
        # TODO: raise in the future an error when passing lowercase freq
        i1 = Period("2005", freq="Y")
        i2 = Period("2005")

        assert i1 == i2

        i4 = Period("2005", freq="M")
        assert i1 != i4

        i1 = Period.now(freq="Q")
        i2 = Period(datetime.now(), freq="Q")

        assert i1 == i2

        # Pass in freq as a keyword argument sometimes as a test for
        # https://github.com/pandas-dev/pandas/issues/53369
        i1 = Period.now(freq="D")
        i2 = Period(datetime.now(), freq="D")
        i3 = Period.now(offsets.Day())

        assert i1 == i2
        assert i1 == i3

        i1 = Period("1982", freq="min")
        msg = "'MIN' is deprecated and will be removed in a future version."
        with tm.assert_produces_warning(FutureWarning, match=msg):
            i2 = Period("1982", freq="MIN")
        assert i1 == i2

        i1 = Period(year=2005, month=3, day=1, freq="D")
        i2 = Period("3/1/2005", freq="D")
        assert i1 == i2

        i3 = Period(year=2005, month=3, day=1, freq="d")
        assert i1 == i3

        i1 = Period("2007-01-01 09:00:00.001")
        expected = Period(datetime(2007, 1, 1, 9, 0, 0, 1000), freq="ms")
        assert i1 == expected

        expected = Period("2007-01-01 09:00:00.001", freq="ms")
        assert i1 == expected

        i1 = Period("2007-01-01 09:00:00.00101")
        expected = Period(datetime(2007, 1, 1, 9, 0, 0, 1010), freq="us")
        assert i1 == expected

        expected = Period("2007-01-01 09:00:00.00101", freq="us")
        assert i1 == expected

        msg = "Must supply freq for ordinal value"
        with pytest.raises(ValueError, match=msg):
            Period(ordinal=200701)

        msg = "Invalid frequency: X"
        with pytest.raises(ValueError, match=msg):
            Period("2007-1-1", freq="X")

    def test_tuple_freq_disallowed(self):
        # GH#34703 tuple freq disallowed
        with pytest.raises(TypeError, match="pass as a string instead"):
            Period("1982", freq=("Min", 1))

        with pytest.raises(TypeError, match="pass as a string instead"):
            Period("2006-12-31", ("w", 1))

    def test_construction_from_timestamp_nanos(self):
        # GH#46811 don't drop nanos from Timestamp
        ts = Timestamp("2022-04-20 09:23:24.123456789")
        per = Period(ts, freq="ns")

        # should losslessly round-trip, not lose the 789
        rt = per.to_timestamp()
        assert rt == ts

        # same thing but from a datetime64 object
        dt64 = ts.asm8
        per2 = Period(dt64, freq="ns")
        rt2 = per2.to_timestamp()
        assert rt2.asm8 == dt64

    def test_construction_bday(self):
        # Biz day construction, roll forward if non-weekday
        with tm.assert_produces_warning(FutureWarning, match=bday_msg):
            i1 = Period("3/10/12", freq="B")
            i2 = Period("3/10/12", freq="D")
            assert i1 == i2.asfreq("B")
            i2 = Period("3/11/12", freq="D")
            assert i1 == i2.asfreq("B")
            i2 = Period("3/12/12", freq="D")
            assert i1 == i2.asfreq("B")

            i3 = Period("3/10/12", freq="b")
            assert i1 == i3

            i1 = Period(year=2012, month=3, day=10, freq="B")
            i2 = Period("3/12/12", freq="B")
            assert i1 == i2

    def test_construction_quarter(self):
        i1 = Period(year=2005, quarter=1, freq="Q")
        i2 = Period("1/1/2005", freq="Q")
        assert i1 == i2

        i1 = Period(year=2005, quarter=3, freq="Q")
        i2 = Period("9/1/2005", freq="Q")
        assert i1 == i2

        i1 = Period("2005Q1")
        i2 = Period(year=2005, quarter=1, freq="Q")
        i3 = Period("2005q1")
        assert i1 == i2
        assert i1 == i3

        i1 = Period("05Q1")
        assert i1 == i2
        lower = Period("05q1")
        assert i1 == lower

        i1 = Period("1Q2005")
        assert i1 == i2
        lower = Period("1q2005")
        assert i1 == lower

        i1 = Period("1Q05")
        assert i1 == i2
        lower = Period("1q05")
        assert i1 == lower

        i1 = Period("4Q1984")
        assert i1.year == 1984
        lower = Period("4q1984")
        assert i1 == lower

    def test_construction_month(self):
        expected = Period("2007-01", freq="M")
        i1 = Period("200701", freq="M")
        assert i1 == expected

        i1 = Period("200701", freq="M")
        assert i1 == expected

        i1 = Period(200701, freq="M")
        assert i1 == expected

        i1 = Period(ordinal=200701, freq="M")
        assert i1.year == 18695

        i1 = Period(datetime(2007, 1, 1), freq="M")
        i2 = Period("200701", freq="M")
        assert i1 == i2

        i1 = Period(date(2007, 1, 1), freq="M")
        i2 = Period(datetime(2007, 1, 1), freq="M")
        i3 = Period(np.datetime64("2007-01-01"), freq="M")
        i4 = Period("2007-01-01 00:00:00", freq="M")
        i5 = Period("2007-01-01 00:00:00.000", freq="M")
        assert i1 == i2
        assert i1 == i3
        assert i1 == i4
        assert i1 == i5

    def test_period_constructor_offsets(self):
        assert Period("1/1/2005", freq=offsets.MonthEnd()) == Period(
            "1/1/2005", freq="M"
        )
        assert Period("2005", freq=offsets.YearEnd()) == Period("2005", freq="Y")
        assert Period("2005", freq=offsets.MonthEnd()) == Period("2005", freq="M")
        with tm.assert_produces_warning(FutureWarning, match=bday_msg):
            assert Period("3/10/12", freq=offsets.BusinessDay()) == Period(
                "3/10/12", freq="B"
            )
        assert Period("3/10/12", freq=offsets.Day()) == Period("3/10/12", freq="D")

        assert Period(
            year=2005, quarter=1, freq=offsets.QuarterEnd(startingMonth=12)
        ) == Period(year=2005, quarter=1, freq="Q")
        assert Period(
            year=2005, quarter=2, freq=offsets.QuarterEnd(startingMonth=12)
        ) == Period(year=2005, quarter=2, freq="Q")

        assert Period(year=2005, month=3, day=1, freq=offsets.Day()) == Period(
            year=2005, month=3, day=1, freq="D"
        )
        with tm.assert_produces_warning(FutureWarning, match=bday_msg):
            assert Period(year=2012, month=3, day=10, freq=offsets.BDay()) == Period(
                year=2012, month=3, day=10, freq="B"
            )

        expected = Period("2005-03-01", freq="3D")
        assert Period(year=2005, month=3, day=1, freq=offsets.Day(3)) == expected
        assert Period(year=2005, month=3, day=1, freq="3D") == expected

        with tm.assert_produces_warning(FutureWarning, match=bday_msg):
            assert Period(year=2012, month=3, day=10, freq=offsets.BDay(3)) == Period(
                year=2012, month=3, day=10, freq="3B"
            )

        assert Period(200701, freq=offsets.MonthEnd()) == Period(200701, freq="M")

        i1 = Period(ordinal=200701, freq=offsets.MonthEnd())
        i2 = Period(ordinal=200701, freq="M")
        assert i1 == i2
        assert i1.year == 18695
        assert i2.year == 18695

        i1 = Period(datetime(2007, 1, 1), freq="M")
        i2 = Period("200701", freq="M")
        assert i1 == i2

        i1 = Period(date(2007, 1, 1), freq="M")
        i2 = Period(datetime(2007, 1, 1), freq="M")
        i3 = Period(np.datetime64("2007-01-01"), freq="M")
        i4 = Period("2007-01-01 00:00:00", freq="M")
        i5 = Period("2007-01-01 00:00:00.000", freq="M")
        assert i1 == i2
        assert i1 == i3
        assert i1 == i4
        assert i1 == i5

        i1 = Period("2007-01-01 09:00:00.001")
        expected = Period(datetime(2007, 1, 1, 9, 0, 0, 1000), freq="ms")
        assert i1 == expected

        expected = Period("2007-01-01 09:00:00.001", freq="ms")
        assert i1 == expected

        i1 = Period("2007-01-01 09:00:00.00101")
        expected = Period(datetime(2007, 1, 1, 9, 0, 0, 1010), freq="us")
        assert i1 == expected

        expected = Period("2007-01-01 09:00:00.00101", freq="us")
        assert i1 == expected

    def test_invalid_arguments(self):
        msg = "Must supply freq for datetime value"
        with pytest.raises(ValueError, match=msg):
            Period(datetime.now())
        with pytest.raises(ValueError, match=msg):
            Period(datetime.now().date())

        msg = "Value must be Period, string, integer, or datetime"
        with pytest.raises(ValueError, match=msg):
            Period(1.6, freq="D")
        msg = "Ordinal must be an integer"
        with pytest.raises(ValueError, match=msg):
            Period(ordinal=1.6, freq="D")
        msg = "Only value or ordinal but not both should be given but not both"
        with pytest.raises(ValueError, match=msg):
            Period(ordinal=2, value=1, freq="D")

        msg = "If value is None, freq cannot be None"
        with pytest.raises(ValueError, match=msg):
            Period(month=1)

        msg = '^Given date string "-2000" not likely a datetime$'
        with pytest.raises(ValueError, match=msg):
            Period("-2000", "Y")
        if PY314:
            msg = "day 0 must be in range 1..31 for month 1 in year 1: 0"
        else:
            msg = "day is out of range for month"
        with pytest.raises(DateParseError, match=msg):
            Period("0", "Y")
        msg = "Unknown datetime string format, unable to parse"
        with pytest.raises(DateParseError, match=msg):
            Period("1/1/-2000", "Y")

    def test_constructor_corner(self):
        expected = Period("2007-01", freq="2M")
        assert Period(year=2007, month=1, freq="2M") == expected

        assert Period(None) is NaT

        p = Period("2007-01-01", freq="D")

        result = Period(p, freq="Y")
        exp = Period("2007", freq="Y")
        assert result == exp

    def test_constructor_infer_freq(self):
        p = Period("2007-01-01")
        assert p.freq == "D"

        p = Period("2007-01-01 07")
        assert p.freq == "h"

        p = Period("2007-01-01 07:10")
        assert p.freq == "min"

        p = Period("2007-01-01 07:10:15")
        assert p.freq == "s"

        p = Period("2007-01-01 07:10:15.123")
        assert p.freq == "ms"

        # We see that there are 6 digits after the decimal, so get microsecond
        #  even though they are all zeros.
        p = Period("2007-01-01 07:10:15.123000")
        assert p.freq == "us"

        p = Period("2007-01-01 07:10:15.123400")
        assert p.freq == "us"

    def test_multiples(self):
        result1 = Period("1989", freq="2Y")
        result2 = Period("1989", freq="Y")
        assert result1.ordinal == result2.ordinal
        assert result1.freqstr == "2Y-DEC"
        assert result2.freqstr == "Y-DEC"
        assert result1.freq == offsets.YearEnd(2)
        assert result2.freq == offsets.YearEnd()

        assert (result1 + 1).ordinal == result1.ordinal + 2
        assert (1 + result1).ordinal == result1.ordinal + 2
        assert (result1 - 1).ordinal == result2.ordinal - 2
        assert (-1 + result1).ordinal == result2.ordinal - 2

    @pytest.mark.parametrize("month", MONTHS)
    def test_period_cons_quarterly(self, month):
        # bugs in scikits.timeseries
        freq = f"Q-{month}"
        exp = Period("1989Q3", freq=freq)
        assert "1989Q3" in str(exp)
        stamp = exp.to_timestamp("D", how="end")
        p = Period(stamp, freq=freq)
        assert p == exp

        stamp = exp.to_timestamp("3D", how="end")
        p = Period(stamp, freq=freq)
        assert p == exp

    @pytest.mark.parametrize("month", MONTHS)
    def test_period_cons_annual(self, month):
        # bugs in scikits.timeseries
        freq = f"Y-{month}"
        exp = Period("1989", freq=freq)
        stamp = exp.to_timestamp("D", how="end") + timedelta(days=30)
        p = Period(stamp, freq=freq)

        assert p == exp + 1
        assert isinstance(p, Period)

    @pytest.mark.parametrize("day", DAYS)
    @pytest.mark.parametrize("num", range(10, 17))
    def test_period_cons_weekly(self, num, day):
        daystr = f"2011-02-{num}"
        freq = f"W-{day}"

        result = Period(daystr, freq=freq)
        expected = Period(daystr, freq="D").asfreq(freq)
        assert result == expected
        assert isinstance(result, Period)

    def test_parse_week_str_roundstrip(self):
        # GH#50803
        per = Period("2017-01-23/2017-01-29")
        assert per.freq.freqstr == "W-SUN"

        per = Period("2017-01-24/2017-01-30")
        assert per.freq.freqstr == "W-MON"

        msg = "Could not parse as weekly-freq Period"
        with pytest.raises(ValueError, match=msg):
            # not 6 days apart
            Period("2016-01-23/2017-01-29")

    def test_period_from_ordinal(self):
        p = Period("2011-01", freq="M")
        res = Period._from_ordinal(p.ordinal, freq=p.freq)
        assert p == res
        assert isinstance(res, Period)

    @pytest.mark.parametrize("freq", ["Y", "M", "D", "h"])
    def test_construct_from_nat_string_and_freq(self, freq):
        per = Period("NaT", freq=freq)
        assert per is NaT

        per = Period("NaT", freq="2" + freq)
        assert per is NaT

        per = Period("NaT", freq="3" + freq)
        assert per is NaT

    def test_period_cons_nat(self):
        p = Period("nat", freq="W-SUN")
        assert p is NaT

        p = Period(iNaT, freq="D")
        assert p is NaT

        p = Period(iNaT, freq="3D")
        assert p is NaT

        p = Period(iNaT, freq="1D1h")
        assert p is NaT

        p = Period("NaT")
        assert p is NaT

        p = Period(iNaT)
        assert p is NaT

    def test_period_cons_mult(self):
        p1 = Period("2011-01", freq="3M")
        p2 = Period("2011-01", freq="M")
        assert p1.ordinal == p2.ordinal

        assert p1.freq == offsets.MonthEnd(3)
        assert p1.freqstr == "3M"

        assert p2.freq == offsets.MonthEnd()
        assert p2.freqstr == "M"

        result = p1 + 1
        assert result.ordinal == (p2 + 3).ordinal

        assert result.freq == p1.freq
        assert result.freqstr == "3M"

        result = p1 - 1
        assert result.ordinal == (p2 - 3).ordinal
        assert result.freq == p1.freq
        assert result.freqstr == "3M"

        msg = "Frequency must be positive, because it represents span: -3M"
        with pytest.raises(ValueError, match=msg):
            Period("2011-01", freq="-3M")

        msg = "Frequency must be positive, because it represents span: 0M"
        with pytest.raises(ValueError, match=msg):
            Period("2011-01", freq="0M")

    def test_period_cons_combined(self):
        p = [
            (
                Period("2011-01", freq="1D1h"),
                Period("2011-01", freq="1h1D"),
                Period("2011-01", freq="h"),
            ),
            (
                Period(ordinal=1, freq="1D1h"),
                Period(ordinal=1, freq="1h1D"),
                Period(ordinal=1, freq="h"),
            ),
        ]

        for p1, p2, p3 in p:
            assert p1.ordinal == p3.ordinal
            assert p2.ordinal == p3.ordinal

            assert p1.freq == offsets.Hour(25)
            assert p1.freqstr == "25h"

            assert p2.freq == offsets.Hour(25)
            assert p2.freqstr == "25h"

            assert p3.freq == offsets.Hour()
            assert p3.freqstr == "h"

            result = p1 + 1
            assert result.ordinal == (p3 + 25).ordinal
            assert result.freq == p1.freq
            assert result.freqstr == "25h"

            result = p2 + 1
            assert result.ordinal == (p3 + 25).ordinal
            assert result.freq == p2.freq
            assert result.freqstr == "25h"

            result = p1 - 1
            assert result.ordinal == (p3 - 25).ordinal
            assert result.freq == p1.freq
            assert result.freqstr == "25h"

            result = p2 - 1
            assert result.ordinal == (p3 - 25).ordinal
            assert result.freq == p2.freq
            assert result.freqstr == "25h"

        msg = "Frequency must be positive, because it represents span: -25h"
        with pytest.raises(ValueError, match=msg):
            Period("2011-01", freq="-1D1h")
        with pytest.raises(ValueError, match=msg):
            Period("2011-01", freq="-1h1D")
        with pytest.raises(ValueError, match=msg):
            Period(ordinal=1, freq="-1D1h")
        with pytest.raises(ValueError, match=msg):
            Period(ordinal=1, freq="-1h1D")

        msg = "Frequency must be positive, because it represents span: 0D"
        with pytest.raises(ValueError, match=msg):
            Period("2011-01", freq="0D0h")
        with pytest.raises(ValueError, match=msg):
            Period(ordinal=1, freq="0D0h")

        # You can only combine together day and intraday offsets
        msg = "Invalid frequency: 1W1D"
        with pytest.raises(ValueError, match=msg):
            Period("2011-01", freq="1W1D")
        msg = "Invalid frequency: 1D1W"
        with pytest.raises(ValueError, match=msg):
            Period("2011-01", freq="1D1W")

    @pytest.mark.parametrize("day", ["1970/01/01 ", "2020-12-31 ", "1981/09/13 "])
    @pytest.mark.parametrize("hour", ["00:00:00", "00:00:01", "23:59:59", "12:00:59"])
    @pytest.mark.parametrize(
        "sec_float, expected",
        [
            (".000000001", 1),
            (".000000999", 999),
            (".123456789", 789),
            (".999999999", 999),
            (".999999000", 0),
            # Test femtoseconds, attoseconds, picoseconds are dropped like Timestamp
            (".999999001123", 1),
            (".999999001123456", 1),
            (".999999001123456789", 1),
        ],
    )
    def test_period_constructor_nanosecond(self, day, hour, sec_float, expected):
        # GH 34621

        assert Period(day + hour + sec_float).start_time.nanosecond == expected

    @pytest.mark.parametrize("hour", range(24))
    def test_period_large_ordinal(self, hour):
        # Issue #36430
        # Integer overflow for Period over the maximum timestamp
        p = Period(ordinal=2562048 + hour, freq="1h")
        assert p.hour == hour


class TestPeriodMethods:
    def test_round_trip(self):
        p = Period("2000Q1")
        new_p = tm.round_trip_pickle(p)
        assert new_p == p

    def test_hash(self):
        assert hash(Period("2011-01", freq="M")) == hash(Period("2011-01", freq="M"))

        assert hash(Period("2011-01-01", freq="D")) != hash(Period("2011-01", freq="M"))

        assert hash(Period("2011-01", freq="3M")) != hash(Period("2011-01", freq="2M"))

        assert hash(Period("2011-01", freq="M")) != hash(Period("2011-02", freq="M"))

    # --------------------------------------------------------------
    # to_timestamp

    def test_to_timestamp_mult(self):
        p = Period("2011-01", freq="M")
        assert p.to_timestamp(how="S") == Timestamp("2011-01-01")
        expected = Timestamp("2011-02-01") - Timedelta(1, "ns")
        assert p.to_timestamp(how="E") == expected

        p = Period("2011-01", freq="3M")
        assert p.to_timestamp(how="S") == Timestamp("2011-01-01")
        expected = Timestamp("2011-04-01") - Timedelta(1, "ns")
        assert p.to_timestamp(how="E") == expected

    @pytest.mark.filterwarnings(
        "ignore:Period with BDay freq is deprecated:FutureWarning"
    )
    def test_to_timestamp(self):
        p = Period("1982", freq="Y")
        start_ts = p.to_timestamp(how="S")
        aliases = ["s", "StarT", "BEGIn"]
        for a in aliases:
            assert start_ts == p.to_timestamp("D", how=a)
            # freq with mult should not affect to the result
            assert start_ts == p.to_timestamp("3D", how=a)

        end_ts = p.to_timestamp(how="E")
        aliases = ["e", "end", "FINIsH"]
        for a in aliases:
            assert end_ts == p.to_timestamp("D", how=a)
            assert end_ts == p.to_timestamp("3D", how=a)

        from_lst = ["Y", "Q", "M", "W", "B", "D", "h", "Min", "s"]

        def _ex(p):
            if p.freq == "B":
                return p.start_time + Timedelta(days=1, nanoseconds=-1)
            return Timestamp((p + p.freq).start_time._value - 1)

        for fcode in from_lst:
            p = Period("1982", freq=fcode)
            result = p.to_timestamp().to_period(fcode)
            assert result == p

            assert p.start_time == p.to_timestamp(how="S")

            assert p.end_time == _ex(p)

        # Frequency other than daily

        p = Period("1985", freq="Y")

        result = p.to_timestamp("h", how="end")
        expected = Timestamp(1986, 1, 1) - Timedelta(1, "ns")
        assert result == expected
        result = p.to_timestamp("3h", how="end")
        assert result == expected

        result = p.to_timestamp("min", how="end")
        expected = Timestamp(1986, 1, 1) - Timedelta(1, "ns")
        assert result == expected
        result = p.to_timestamp("2min", how="end")
        assert result == expected

        result = p.to_timestamp(how="end")
        expected = Timestamp(1986, 1, 1) - Timedelta(1, "ns")
        assert result == expected

        expected = datetime(1985, 1, 1)
        result = p.to_timestamp("h", how="start")
        assert result == expected
        result = p.to_timestamp("min", how="start")
        assert result == expected
        result = p.to_timestamp("s", how="start")
        assert result == expected
        result = p.to_timestamp("3h", how="start")
        assert result == expected
        result = p.to_timestamp("5s", how="start")
        assert result == expected

    def test_to_timestamp_business_end(self):
        with tm.assert_produces_warning(FutureWarning, match=bday_msg):
            per = Period("1990-01-05", "B")  # Friday
            result = per.to_timestamp("B", how="E")

        expected = Timestamp("1990-01-06") - Timedelta(nanoseconds=1)
        assert result == expected

    @pytest.mark.parametrize(
        "ts, expected",
        [
            ("1970-01-01 00:00:00", 0),
            ("1970-01-01 00:00:00.000001", 1),
            ("1970-01-01 00:00:00.00001", 10),
            ("1970-01-01 00:00:00.499", 499000),
            ("1999-12-31 23:59:59.999", 999000),
            ("1999-12-31 23:59:59.999999", 999999),
            ("2050-12-31 23:59:59.5", 500000),
            ("2050-12-31 23:59:59.500001", 500001),
            ("2050-12-31 23:59:59.123456", 123456),
        ],
    )
    @pytest.mark.parametrize("freq", [None, "us", "ns"])
    def test_to_timestamp_microsecond(self, ts, expected, freq):
        # GH 24444
        result = Period(ts).to_timestamp(freq=freq).microsecond
        assert result == expected

    # --------------------------------------------------------------
    # Rendering: __repr__, strftime, etc

    @pytest.mark.parametrize(
        "str_ts,freq,str_res,str_freq",
        (
            ("Jan-2000", None, "2000-01", "M"),
            ("2000-12-15", None, "2000-12-15", "D"),
            (
                "2000-12-15 13:45:26.123456789",
                "ns",
                "2000-12-15 13:45:26.123456789",
                "ns",
            ),
            ("2000-12-15 13:45:26.123456789", "us", "2000-12-15 13:45:26.123456", "us"),
            ("2000-12-15 13:45:26.123456", None, "2000-12-15 13:45:26.123456", "us"),
            ("2000-12-15 13:45:26.123456789", "ms", "2000-12-15 13:45:26.123", "ms"),
            ("2000-12-15 13:45:26.123", None, "2000-12-15 13:45:26.123", "ms"),
            ("2000-12-15 13:45:26", "s", "2000-12-15 13:45:26", "s"),
            ("2000-12-15 13:45:26", "min", "2000-12-15 13:45", "min"),
            ("2000-12-15 13:45:26", "h", "2000-12-15 13:00", "h"),
            ("2000-12-15", "Y", "2000", "Y-DEC"),
            ("2000-12-15", "Q", "2000Q4", "Q-DEC"),
            ("2000-12-15", "M", "2000-12", "M"),
            ("2000-12-15", "W", "2000-12-11/2000-12-17", "W-SUN"),
            ("2000-12-15", "D", "2000-12-15", "D"),
            ("2000-12-15", "B", "2000-12-15", "B"),
        ),
    )
    @pytest.mark.filterwarnings(
        "ignore:Period with BDay freq is deprecated:FutureWarning"
    )
    def test_repr(self, str_ts, freq, str_res, str_freq):
        p = Period(str_ts, freq=freq)
        assert str(p) == str_res
        assert repr(p) == f"Period('{str_res}', '{str_freq}')"

    def test_repr_nat(self):
        p = Period("nat", freq="M")
        assert repr(NaT) in repr(p)

    def test_strftime(self):
        # GH#3363
        p = Period("2000-1-1 12:34:12", freq="s")
        res = p.strftime("%Y-%m-%d %H:%M:%S")
        assert res == "2000-01-01 12:34:12"
        assert isinstance(res, str)


class TestPeriodProperties:
    """Test properties such as year, month, weekday, etc...."""

    @pytest.mark.parametrize("freq", ["Y", "M", "D", "h"])
    def test_is_leap_year(self, freq):
        # GH 13727
        p = Period("2000-01-01 00:00:00", freq=freq)
        assert p.is_leap_year
        assert isinstance(p.is_leap_year, bool)

        p = Period("1999-01-01 00:00:00", freq=freq)
        assert not p.is_leap_year

        p = Period("2004-01-01 00:00:00", freq=freq)
        assert p.is_leap_year

        p = Period("2100-01-01 00:00:00", freq=freq)
        assert not p.is_leap_year

    def test_quarterly_negative_ordinals(self):
        p = Period(ordinal=-1, freq="Q-DEC")
        assert p.year == 1969
        assert p.quarter == 4
        assert isinstance(p, Period)

        p = Period(ordinal=-2, freq="Q-DEC")
        assert p.year == 1969
        assert p.quarter == 3
        assert isinstance(p, Period)

        p = Period(ordinal=-2, freq="M")
        assert p.year == 1969
        assert p.month == 11
        assert isinstance(p, Period)

    def test_freq_str(self):
        i1 = Period("1982", freq="Min")
        assert i1.freq == offsets.Minute()
        assert i1.freqstr == "min"

    @pytest.mark.filterwarnings(
        "ignore:Period with BDay freq is deprecated:FutureWarning"
    )
    def test_period_deprecated_freq(self):
        cases = {
            "M": ["MTH", "MONTH", "MONTHLY", "Mth", "month", "monthly"],
            "B": ["BUS", "BUSINESS", "BUSINESSLY", "WEEKDAY", "bus"],
            "D": ["DAY", "DLY", "DAILY", "Day", "Dly", "Daily"],
            "h": ["HR", "HOUR", "HRLY", "HOURLY", "hr", "Hour", "HRly"],
            "min": ["minute", "MINUTE", "MINUTELY", "minutely"],
            "s": ["sec", "SEC", "SECOND", "SECONDLY", "second"],
            "ms": ["MILLISECOND", "MILLISECONDLY", "millisecond"],
            "us": ["MICROSECOND", "MICROSECONDLY", "microsecond"],
            "ns": ["NANOSECOND", "NANOSECONDLY", "nanosecond"],
        }

        msg = INVALID_FREQ_ERR_MSG
        for exp, freqs in cases.items():
            for freq in freqs:
                with pytest.raises(ValueError, match=msg):
                    Period("2016-03-01 09:00", freq=freq)
                with pytest.raises(ValueError, match=msg):
                    Period(ordinal=1, freq=freq)

            # check supported freq-aliases still works
            p1 = Period("2016-03-01 09:00", freq=exp)
            p2 = Period(ordinal=1, freq=exp)
            assert isinstance(p1, Period)
            assert isinstance(p2, Period)

    @staticmethod
    def _period_constructor(bound, offset):
        return Period(
            year=bound.year,
            month=bound.month,
            day=bound.day,
            hour=bound.hour,
            minute=bound.minute,
            second=bound.second + offset,
            freq="us",
        )

    @pytest.mark.parametrize("bound, offset", [(Timestamp.min, -1), (Timestamp.max, 1)])
    @pytest.mark.parametrize("period_property", ["start_time", "end_time"])
    def test_outer_bounds_start_and_end_time(self, bound, offset, period_property):
        # GH #13346
        period = TestPeriodProperties._period_constructor(bound, offset)
        with pytest.raises(OutOfBoundsDatetime, match="Out of bounds nanosecond"):
            getattr(period, period_property)

    @pytest.mark.parametrize("bound, offset", [(Timestamp.min, -1), (Timestamp.max, 1)])
    @pytest.mark.parametrize("period_property", ["start_time", "end_time"])
    def test_inner_bounds_start_and_end_time(self, bound, offset, period_property):
        # GH #13346
        period = TestPeriodProperties._period_constructor(bound, -offset)
        expected = period.to_timestamp().round(freq="s")
        assert getattr(period, period_property).round(freq="s") == expected
        expected = (bound - offset * Timedelta(1, unit="s")).floor("s")
        assert getattr(period, period_property).floor("s") == expected

    def test_start_time(self):
        freq_lst = ["Y", "Q", "M", "D", "h", "min", "s"]
        xp = datetime(2012, 1, 1)
        for f in freq_lst:
            p = Period("2012", freq=f)
            assert p.start_time == xp
        with tm.assert_produces_warning(FutureWarning, match=bday_msg):
            assert Period("2012", freq="B").start_time == datetime(2012, 1, 2)
        assert Period("2012", freq="W").start_time == datetime(2011, 12, 26)

    def test_end_time(self):
        p = Period("2012", freq="Y")

        def _ex(*args):
            return Timestamp(Timestamp(datetime(*args)).as_unit("ns")._value - 1)

        xp = _ex(2013, 1, 1)
        assert xp == p.end_time

        p = Period("2012", freq="Q")
        xp = _ex(2012, 4, 1)
        assert xp == p.end_time

        p = Period("2012", freq="M")
        xp = _ex(2012, 2, 1)
        assert xp == p.end_time

        p = Period("2012", freq="D")
        xp = _ex(2012, 1, 2)
        assert xp == p.end_time

        p = Period("2012", freq="h")
        xp = _ex(2012, 1, 1, 1)
        assert xp == p.end_time

        with tm.assert_produces_warning(FutureWarning, match=bday_msg):
            p = Period("2012", freq="B")
            xp = _ex(2012, 1, 3)
            assert xp == p.end_time

        p = Period("2012", freq="W")
        xp = _ex(2012, 1, 2)
        assert xp == p.end_time

        # Test for GH 11738
        p = Period("2012", freq="15D")
        xp = _ex(2012, 1, 16)
        assert xp == p.end_time

        p = Period("2012", freq="1D1h")
        xp = _ex(2012, 1, 2, 1)
        assert xp == p.end_time

        p = Period("2012", freq="1h1D")
        xp = _ex(2012, 1, 2, 1)
        assert xp == p.end_time

    def test_end_time_business_friday(self):
        # GH#34449
        with tm.assert_produces_warning(FutureWarning, match=bday_msg):
            per = Period("1990-01-05", "B")
            result = per.end_time

        expected = Timestamp("1990-01-06") - Timedelta(nanoseconds=1)
        assert result == expected

    def test_anchor_week_end_time(self):
        def _ex(*args):
            return Timestamp(Timestamp(datetime(*args)).as_unit("ns")._value - 1)

        p = Period("2013-1-1", "W-SAT")
        xp = _ex(2013, 1, 6)
        assert p.end_time == xp

    def test_properties_annually(self):
        # Test properties on Periods with annually frequency.
        a_date = Period(freq="Y", year=2007)
        assert a_date.year == 2007

    def test_properties_quarterly(self):
        # Test properties on Periods with daily frequency.
        qedec_date = Period(freq="Q-DEC", year=2007, quarter=1)
        qejan_date = Period(freq="Q-JAN", year=2007, quarter=1)
        qejun_date = Period(freq="Q-JUN", year=2007, quarter=1)
        #
        for x in range(3):
            for qd in (qedec_date, qejan_date, qejun_date):
                assert (qd + x).qyear == 2007
                assert (qd + x).quarter == x + 1

    def test_properties_monthly(self):
        # Test properties on Periods with daily frequency.
        m_date = Period(freq="M", year=2007, month=1)
        for x in range(11):
            m_ival_x = m_date + x
            assert m_ival_x.year == 2007
            if 1 <= x + 1 <= 3:
                assert m_ival_x.quarter == 1
            elif 4 <= x + 1 <= 6:
                assert m_ival_x.quarter == 2
            elif 7 <= x + 1 <= 9:
                assert m_ival_x.quarter == 3
            elif 10 <= x + 1 <= 12:
                assert m_ival_x.quarter == 4
            assert m_ival_x.month == x + 1

    def test_properties_weekly(self):
        # Test properties on Periods with daily frequency.
        w_date = Period(freq="W", year=2007, month=1, day=7)
        #
        assert w_date.year == 2007
        assert w_date.quarter == 1
        assert w_date.month == 1
        assert w_date.week == 1
        assert (w_date - 1).week == 52
        assert w_date.days_in_month == 31
        assert Period(freq="W", year=2012, month=2, day=1).days_in_month == 29

    def test_properties_weekly_legacy(self):
        # Test properties on Periods with daily frequency.
        w_date = Period(freq="W", year=2007, month=1, day=7)
        assert w_date.year == 2007
        assert w_date.quarter == 1
        assert w_date.month == 1
        assert w_date.week == 1
        assert (w_date - 1).week == 52
        assert w_date.days_in_month == 31

        exp = Period(freq="W", year=2012, month=2, day=1)
        assert exp.days_in_month == 29

        msg = INVALID_FREQ_ERR_MSG
        with pytest.raises(ValueError, match=msg):
            Period(freq="WK", year=2007, month=1, day=7)

    def test_properties_daily(self):
        # Test properties on Periods with daily frequency.
        with tm.assert_produces_warning(FutureWarning, match=bday_msg):
            b_date = Period(freq="B", year=2007, month=1, day=1)
        #
        assert b_date.year == 2007
        assert b_date.quarter == 1
        assert b_date.month == 1
        assert b_date.day == 1
        assert b_date.weekday == 0
        assert b_date.dayofyear == 1
        assert b_date.days_in_month == 31
        with tm.assert_produces_warning(FutureWarning, match=bday_msg):
            assert Period(freq="B", year=2012, month=2, day=1).days_in_month == 29

        d_date = Period(freq="D", year=2007, month=1, day=1)

        assert d_date.year == 2007
        assert d_date.quarter == 1
        assert d_date.month == 1
        assert d_date.day == 1
        assert d_date.weekday == 0
        assert d_date.dayofyear == 1
        assert d_date.days_in_month == 31
        assert Period(freq="D", year=2012, month=2, day=1).days_in_month == 29

    def test_properties_hourly(self):
        # Test properties on Periods with hourly frequency.
        h_date1 = Period(freq="h", year=2007, month=1, day=1, hour=0)
        h_date2 = Period(freq="2h", year=2007, month=1, day=1, hour=0)

        for h_date in [h_date1, h_date2]:
            assert h_date.year == 2007
            assert h_date.quarter == 1
            assert h_date.month == 1
            assert h_date.day == 1
            assert h_date.weekday == 0
            assert h_date.dayofyear == 1
            assert h_date.hour == 0
            assert h_date.days_in_month == 31
            assert (
                Period(freq="h", year=2012, month=2, day=1, hour=0).days_in_month == 29
            )

    def test_properties_minutely(self):
        # Test properties on Periods with minutely frequency.
        t_date = Period(freq="Min", year=2007, month=1, day=1, hour=0, minute=0)
        #
        assert t_date.quarter == 1
        assert t_date.month == 1
        assert t_date.day == 1
        assert t_date.weekday == 0
        assert t_date.dayofyear == 1
        assert t_date.hour == 0
        assert t_date.minute == 0
        assert t_date.days_in_month == 31
        assert (
            Period(freq="D", year=2012, month=2, day=1, hour=0, minute=0).days_in_month
            == 29
        )

    def test_properties_secondly(self):
        # Test properties on Periods with secondly frequency.
        s_date = Period(
            freq="Min", year=2007, month=1, day=1, hour=0, minute=0, second=0
        )
        #
        assert s_date.year == 2007
        assert s_date.quarter == 1
        assert s_date.month == 1
        assert s_date.day == 1
        assert s_date.weekday == 0
        assert s_date.dayofyear == 1
        assert s_date.hour == 0
        assert s_date.minute == 0
        assert s_date.second == 0
        assert s_date.days_in_month == 31
        assert (
            Period(
                freq="Min", year=2012, month=2, day=1, hour=0, minute=0, second=0
            ).days_in_month
            == 29
        )


class TestPeriodComparisons:
    def test_sort_periods(self):
        jan = Period("2000-01", "M")
        feb = Period("2000-02", "M")
        mar = Period("2000-03", "M")
        periods = [mar, jan, feb]
        correctPeriods = [jan, feb, mar]
        assert sorted(periods) == correctPeriods


def test_period_immutable():
    # see gh-17116
    msg = "not writable"

    per = Period("2014Q1")
    with pytest.raises(AttributeError, match=msg):
        per.ordinal = 14

    freq = per.freq
    with pytest.raises(AttributeError, match=msg):
        per.freq = 2 * freq


def test_small_year_parsing():
    per1 = Period("0001-01-07", "D")
    assert per1.year == 1
    assert per1.day == 7


def test_negone_ordinals():
    freqs = ["Y", "M", "Q", "D", "h", "min", "s"]

    period = Period(ordinal=-1, freq="D")
    for freq in freqs:
        repr(period.asfreq(freq))

    for freq in freqs:
        period = Period(ordinal=-1, freq=freq)
        repr(period)
        assert period.year == 1969

    with tm.assert_produces_warning(FutureWarning, match=bday_msg):
        period = Period(ordinal=-1, freq="B")
    repr(period)
    period = Period(ordinal=-1, freq="W")
    repr(period)
