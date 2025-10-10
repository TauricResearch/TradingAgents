import pytest

from pandas import (
    DatetimeIndex,
    date_range,
)

from pandas.tseries.offsets import (
    BDay,
    DateOffset,
    Day,
    Hour,
)


class TestFreq:
    def test_freq_setter_errors(self):
        # GH#20678
        idx = DatetimeIndex(["20180101", "20180103", "20180105"])

        # setting with an incompatible freq
        msg = (
            "Inferred frequency 2D from passed values does not conform to "
            "passed frequency 5D"
        )
        with pytest.raises(ValueError, match=msg):
            idx._data.freq = "5D"

        # setting with non-freq string
        with pytest.raises(ValueError, match="Invalid frequency"):
            idx._data.freq = "foo"

    @pytest.mark.parametrize("values", [["20180101", "20180103", "20180105"], []])
    @pytest.mark.parametrize("freq", ["2D", Day(2), "2B", BDay(2), "48h", Hour(48)])
    @pytest.mark.parametrize("tz", [None, "US/Eastern"])
    def test_freq_setter(self, values, freq, tz):
        # GH#20678
        idx = DatetimeIndex(values, tz=tz)

        # can set to an offset, converting from string if necessary
        idx._data.freq = freq
        assert idx.freq == freq
        assert isinstance(idx.freq, DateOffset)

        # can reset to None
        idx._data.freq = None
        assert idx.freq is None

    def test_freq_view_safe(self):
        # Setting the freq for one DatetimeIndex shouldn't alter the freq
        #  for another that views the same data

        dti = date_range("2016-01-01", periods=5)
        dta = dti._data

        dti2 = DatetimeIndex(dta)._with_freq(None)
        assert dti2.freq is None

        # Original was not altered
        assert dti.freq == "D"
        assert dta.freq == "D"
