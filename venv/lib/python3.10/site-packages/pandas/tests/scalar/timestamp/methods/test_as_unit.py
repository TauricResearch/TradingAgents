import pytest

from pandas._libs.tslibs.dtypes import NpyDatetimeUnit
from pandas.errors import OutOfBoundsDatetime

from pandas import Timestamp


class TestTimestampAsUnit:
    def test_as_unit(self):
        ts = Timestamp("1970-01-01").as_unit("ns")
        assert ts.unit == "ns"

        assert ts.as_unit("ns") is ts

        res = ts.as_unit("us")
        assert res._value == ts._value // 1000
        assert res._creso == NpyDatetimeUnit.NPY_FR_us.value

        rt = res.as_unit("ns")
        assert rt._value == ts._value
        assert rt._creso == ts._creso

        res = ts.as_unit("ms")
        assert res._value == ts._value // 1_000_000
        assert res._creso == NpyDatetimeUnit.NPY_FR_ms.value

        rt = res.as_unit("ns")
        assert rt._value == ts._value
        assert rt._creso == ts._creso

        res = ts.as_unit("s")
        assert res._value == ts._value // 1_000_000_000
        assert res._creso == NpyDatetimeUnit.NPY_FR_s.value

        rt = res.as_unit("ns")
        assert rt._value == ts._value
        assert rt._creso == ts._creso

    def test_as_unit_overflows(self):
        # microsecond that would be just out of bounds for nano
        us = 9223372800000000
        ts = Timestamp._from_value_and_reso(us, NpyDatetimeUnit.NPY_FR_us.value, None)

        msg = "Cannot cast 2262-04-12 00:00:00 to unit='ns' without overflow"
        with pytest.raises(OutOfBoundsDatetime, match=msg):
            ts.as_unit("ns")

        res = ts.as_unit("ms")
        assert res._value == us // 1000
        assert res._creso == NpyDatetimeUnit.NPY_FR_ms.value

    def test_as_unit_rounding(self):
        ts = Timestamp(1_500_000)  # i.e. 1500 microseconds
        res = ts.as_unit("ms")

        expected = Timestamp(1_000_000)  # i.e. 1 millisecond
        assert res == expected

        assert res._creso == NpyDatetimeUnit.NPY_FR_ms.value
        assert res._value == 1

        with pytest.raises(ValueError, match="Cannot losslessly convert units"):
            ts.as_unit("ms", round_ok=False)

    def test_as_unit_non_nano(self):
        # case where we are going neither to nor from nano
        ts = Timestamp("1970-01-02").as_unit("ms")
        assert ts.year == 1970
        assert ts.month == 1
        assert ts.day == 2
        assert ts.hour == ts.minute == ts.second == ts.microsecond == ts.nanosecond == 0

        res = ts.as_unit("s")
        assert res._value == 24 * 3600
        assert res.year == 1970
        assert res.month == 1
        assert res.day == 2
        assert (
            res.hour
            == res.minute
            == res.second
            == res.microsecond
            == res.nanosecond
            == 0
        )
