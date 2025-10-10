import pytest

from pandas._libs.tslibs.dtypes import NpyDatetimeUnit
from pandas.errors import OutOfBoundsTimedelta

from pandas import Timedelta


class TestAsUnit:
    def test_as_unit(self):
        td = Timedelta(days=1)

        assert td.as_unit("ns") is td

        res = td.as_unit("us")
        assert res._value == td._value // 1000
        assert res._creso == NpyDatetimeUnit.NPY_FR_us.value

        rt = res.as_unit("ns")
        assert rt._value == td._value
        assert rt._creso == td._creso

        res = td.as_unit("ms")
        assert res._value == td._value // 1_000_000
        assert res._creso == NpyDatetimeUnit.NPY_FR_ms.value

        rt = res.as_unit("ns")
        assert rt._value == td._value
        assert rt._creso == td._creso

        res = td.as_unit("s")
        assert res._value == td._value // 1_000_000_000
        assert res._creso == NpyDatetimeUnit.NPY_FR_s.value

        rt = res.as_unit("ns")
        assert rt._value == td._value
        assert rt._creso == td._creso

    def test_as_unit_overflows(self):
        # microsecond that would be just out of bounds for nano
        us = 9223372800000000
        td = Timedelta._from_value_and_reso(us, NpyDatetimeUnit.NPY_FR_us.value)

        msg = "Cannot cast 106752 days 00:00:00 to unit='ns' without overflow"
        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            td.as_unit("ns")

        res = td.as_unit("ms")
        assert res._value == us // 1000
        assert res._creso == NpyDatetimeUnit.NPY_FR_ms.value

    def test_as_unit_rounding(self):
        td = Timedelta(microseconds=1500)
        res = td.as_unit("ms")

        expected = Timedelta(milliseconds=1)
        assert res == expected

        assert res._creso == NpyDatetimeUnit.NPY_FR_ms.value
        assert res._value == 1

        with pytest.raises(ValueError, match="Cannot losslessly convert units"):
            td.as_unit("ms", round_ok=False)

    def test_as_unit_non_nano(self):
        # case where we are going neither to nor from nano
        td = Timedelta(days=1).as_unit("ms")
        assert td.days == 1
        assert td._value == 86_400_000
        assert td.components.days == 1
        assert td._d == 1
        assert td.total_seconds() == 86400

        res = td.as_unit("us")
        assert res._value == 86_400_000_000
        assert res.components.days == 1
        assert res.components.hours == 0
        assert res._d == 1
        assert res._h == 0
        assert res.total_seconds() == 86400
