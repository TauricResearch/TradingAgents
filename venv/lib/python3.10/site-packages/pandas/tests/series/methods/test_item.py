"""
Series.item method, mainly testing that we get python scalars as opposed to
numpy scalars.
"""
import pytest

from pandas import (
    Series,
    Timedelta,
    Timestamp,
    date_range,
)


class TestItem:
    def test_item(self):
        # We are testing that we get python scalars as opposed to numpy scalars
        ser = Series([1])
        result = ser.item()
        assert result == 1
        assert result == ser.iloc[0]
        assert isinstance(result, int)  # i.e. not np.int64

        ser = Series([0.5], index=[3])
        result = ser.item()
        assert isinstance(result, float)
        assert result == 0.5

        ser = Series([1, 2])
        msg = "can only convert an array of size 1"
        with pytest.raises(ValueError, match=msg):
            ser.item()

        dti = date_range("2016-01-01", periods=2)
        with pytest.raises(ValueError, match=msg):
            dti.item()
        with pytest.raises(ValueError, match=msg):
            Series(dti).item()

        val = dti[:1].item()
        assert isinstance(val, Timestamp)
        val = Series(dti)[:1].item()
        assert isinstance(val, Timestamp)

        tdi = dti - dti
        with pytest.raises(ValueError, match=msg):
            tdi.item()
        with pytest.raises(ValueError, match=msg):
            Series(tdi).item()

        val = tdi[:1].item()
        assert isinstance(val, Timedelta)
        val = Series(tdi)[:1].item()
        assert isinstance(val, Timedelta)

        # Case where ser[0] would not work
        ser = Series(dti, index=[5, 6])
        val = ser.iloc[:1].item()
        assert val == dti[0]
