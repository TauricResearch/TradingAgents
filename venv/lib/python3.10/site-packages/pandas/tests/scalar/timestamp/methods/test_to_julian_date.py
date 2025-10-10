from pandas import Timestamp


class TestTimestampToJulianDate:
    def test_compare_1700(self):
        ts = Timestamp("1700-06-23")
        res = ts.to_julian_date()
        assert res == 2_342_145.5

    def test_compare_2000(self):
        ts = Timestamp("2000-04-12")
        res = ts.to_julian_date()
        assert res == 2_451_646.5

    def test_compare_2100(self):
        ts = Timestamp("2100-08-12")
        res = ts.to_julian_date()
        assert res == 2_488_292.5

    def test_compare_hour01(self):
        ts = Timestamp("2000-08-12T01:00:00")
        res = ts.to_julian_date()
        assert res == 2_451_768.5416666666666666

    def test_compare_hour13(self):
        ts = Timestamp("2000-08-12T13:00:00")
        res = ts.to_julian_date()
        assert res == 2_451_769.0416666666666666
