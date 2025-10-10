import numpy as np
import pytest

from pandas._libs.tslibs import IncompatibleFrequency

from pandas import (
    NaT,
    Period,
    PeriodIndex,
)
import pandas._testing as tm


class TestSearchsorted:
    @pytest.mark.parametrize("freq", ["D", "2D"])
    def test_searchsorted(self, freq):
        pidx = PeriodIndex(
            ["2014-01-01", "2014-01-02", "2014-01-03", "2014-01-04", "2014-01-05"],
            freq=freq,
        )

        p1 = Period("2014-01-01", freq=freq)
        assert pidx.searchsorted(p1) == 0

        p2 = Period("2014-01-04", freq=freq)
        assert pidx.searchsorted(p2) == 3

        assert pidx.searchsorted(NaT) == 5

        msg = "Input has different freq=h from PeriodArray"
        with pytest.raises(IncompatibleFrequency, match=msg):
            pidx.searchsorted(Period("2014-01-01", freq="h"))

        msg = "Input has different freq=5D from PeriodArray"
        with pytest.raises(IncompatibleFrequency, match=msg):
            pidx.searchsorted(Period("2014-01-01", freq="5D"))

    def test_searchsorted_different_argument_classes(self, listlike_box):
        pidx = PeriodIndex(
            ["2014-01-01", "2014-01-02", "2014-01-03", "2014-01-04", "2014-01-05"],
            freq="D",
        )
        result = pidx.searchsorted(listlike_box(pidx))
        expected = np.arange(len(pidx), dtype=result.dtype)
        tm.assert_numpy_array_equal(result, expected)

        result = pidx._data.searchsorted(listlike_box(pidx))
        tm.assert_numpy_array_equal(result, expected)

    def test_searchsorted_invalid(self):
        pidx = PeriodIndex(
            ["2014-01-01", "2014-01-02", "2014-01-03", "2014-01-04", "2014-01-05"],
            freq="D",
        )

        other = np.array([0, 1], dtype=np.int64)

        msg = "|".join(
            [
                "searchsorted requires compatible dtype or scalar",
                "value should be a 'Period', 'NaT', or array of those. Got",
            ]
        )
        with pytest.raises(TypeError, match=msg):
            pidx.searchsorted(other)

        with pytest.raises(TypeError, match=msg):
            pidx.searchsorted(other.astype("timedelta64[ns]"))

        with pytest.raises(TypeError, match=msg):
            pidx.searchsorted(np.timedelta64(4))

        with pytest.raises(TypeError, match=msg):
            pidx.searchsorted(np.timedelta64("NaT", "ms"))

        with pytest.raises(TypeError, match=msg):
            pidx.searchsorted(np.datetime64(4, "ns"))

        with pytest.raises(TypeError, match=msg):
            pidx.searchsorted(np.datetime64("NaT", "ns"))
