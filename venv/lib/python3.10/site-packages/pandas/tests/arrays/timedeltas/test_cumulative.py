import pytest

import pandas._testing as tm
from pandas.core.arrays import TimedeltaArray


class TestAccumulator:
    def test_accumulators_disallowed(self):
        # GH#50297
        arr = TimedeltaArray._from_sequence(["1D", "2D"], dtype="m8[ns]")
        with pytest.raises(TypeError, match="cumprod not supported"):
            arr._accumulate("cumprod")

    def test_cumsum(self, unit):
        # GH#50297
        dtype = f"m8[{unit}]"
        arr = TimedeltaArray._from_sequence(["1D", "2D"], dtype=dtype)
        result = arr._accumulate("cumsum")
        expected = TimedeltaArray._from_sequence(["1D", "3D"], dtype=dtype)
        tm.assert_timedelta_array_equal(result, expected)
