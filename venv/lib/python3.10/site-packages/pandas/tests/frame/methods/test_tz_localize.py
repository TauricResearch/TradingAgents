from datetime import timezone

import numpy as np
import pytest

from pandas import (
    DataFrame,
    Series,
    date_range,
)
import pandas._testing as tm


class TestTZLocalize:
    # See also:
    # test_tz_convert_and_localize in test_tz_convert

    def test_tz_localize(self, frame_or_series):
        rng = date_range("1/1/2011", periods=100, freq="h")

        obj = DataFrame({"a": 1}, index=rng)
        obj = tm.get_obj(obj, frame_or_series)

        result = obj.tz_localize("utc")
        expected = DataFrame({"a": 1}, rng.tz_localize("UTC"))
        expected = tm.get_obj(expected, frame_or_series)

        assert result.index.tz is timezone.utc
        tm.assert_equal(result, expected)

    def test_tz_localize_axis1(self):
        rng = date_range("1/1/2011", periods=100, freq="h")

        df = DataFrame({"a": 1}, index=rng)

        df = df.T
        result = df.tz_localize("utc", axis=1)
        assert result.columns.tz is timezone.utc

        expected = DataFrame({"a": 1}, rng.tz_localize("UTC"))

        tm.assert_frame_equal(result, expected.T)

    def test_tz_localize_naive(self, frame_or_series):
        # Can't localize if already tz-aware
        rng = date_range("1/1/2011", periods=100, freq="h", tz="utc")
        ts = Series(1, index=rng)
        ts = frame_or_series(ts)

        with pytest.raises(TypeError, match="Already tz-aware"):
            ts.tz_localize("US/Eastern")

    @pytest.mark.parametrize("copy", [True, False])
    def test_tz_localize_copy_inplace_mutate(self, copy, frame_or_series):
        # GH#6326
        obj = frame_or_series(
            np.arange(0, 5), index=date_range("20131027", periods=5, freq="1h", tz=None)
        )
        orig = obj.copy()
        result = obj.tz_localize("UTC", copy=copy)
        expected = frame_or_series(
            np.arange(0, 5),
            index=date_range("20131027", periods=5, freq="1h", tz="UTC"),
        )
        tm.assert_equal(result, expected)
        tm.assert_equal(obj, orig)
        assert result.index is not obj.index
        assert result is not obj
