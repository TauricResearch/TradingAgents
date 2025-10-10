from datetime import datetime

from pandas import Series


class TestSetName:
    def test_set_name(self):
        ser = Series([1, 2, 3])
        ser2 = ser._set_name("foo")
        assert ser2.name == "foo"
        assert ser.name is None
        assert ser is not ser2

    def test_set_name_attribute(self):
        ser = Series([1, 2, 3])
        ser2 = Series([1, 2, 3], name="bar")
        for name in [7, 7.0, "name", datetime(2001, 1, 1), (1,), "\u05D0"]:
            ser.name = name
            assert ser.name == name
            ser2.name = name
            assert ser2.name == name
