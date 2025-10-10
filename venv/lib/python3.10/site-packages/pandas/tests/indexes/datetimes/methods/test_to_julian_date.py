import numpy as np

from pandas import (
    Index,
    Timestamp,
    date_range,
)
import pandas._testing as tm


class TestDateTimeIndexToJulianDate:
    def test_1700(self):
        dr = date_range(start=Timestamp("1710-10-01"), periods=5, freq="D")
        r1 = Index([x.to_julian_date() for x in dr])
        r2 = dr.to_julian_date()
        assert isinstance(r2, Index) and r2.dtype == np.float64
        tm.assert_index_equal(r1, r2)

    def test_2000(self):
        dr = date_range(start=Timestamp("2000-02-27"), periods=5, freq="D")
        r1 = Index([x.to_julian_date() for x in dr])
        r2 = dr.to_julian_date()
        assert isinstance(r2, Index) and r2.dtype == np.float64
        tm.assert_index_equal(r1, r2)

    def test_hour(self):
        dr = date_range(start=Timestamp("2000-02-27"), periods=5, freq="h")
        r1 = Index([x.to_julian_date() for x in dr])
        r2 = dr.to_julian_date()
        assert isinstance(r2, Index) and r2.dtype == np.float64
        tm.assert_index_equal(r1, r2)

    def test_minute(self):
        dr = date_range(start=Timestamp("2000-02-27"), periods=5, freq="min")
        r1 = Index([x.to_julian_date() for x in dr])
        r2 = dr.to_julian_date()
        assert isinstance(r2, Index) and r2.dtype == np.float64
        tm.assert_index_equal(r1, r2)

    def test_second(self):
        dr = date_range(start=Timestamp("2000-02-27"), periods=5, freq="s")
        r1 = Index([x.to_julian_date() for x in dr])
        r2 = dr.to_julian_date()
        assert isinstance(r2, Index) and r2.dtype == np.float64
        tm.assert_index_equal(r1, r2)
