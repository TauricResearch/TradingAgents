from dateutil.tz import tzlocal
import numpy as np
import pytest

import pandas.util._test_decorators as td

from pandas import (
    DatetimeIndex,
    NaT,
    Timestamp,
    date_range,
)
import pandas._testing as tm


class TestNormalize:
    def test_normalize(self):
        rng = date_range("1/1/2000 9:30", periods=10, freq="D")

        result = rng.normalize()
        expected = date_range("1/1/2000", periods=10, freq="D")
        tm.assert_index_equal(result, expected)

        arr_ns = np.array([1380585623454345752, 1380585612343234312]).astype(
            "datetime64[ns]"
        )
        rng_ns = DatetimeIndex(arr_ns)
        rng_ns_normalized = rng_ns.normalize()

        arr_ns = np.array([1380585600000000000, 1380585600000000000]).astype(
            "datetime64[ns]"
        )
        expected = DatetimeIndex(arr_ns)
        tm.assert_index_equal(rng_ns_normalized, expected)

        assert result.is_normalized
        assert not rng.is_normalized

    def test_normalize_nat(self):
        dti = DatetimeIndex([NaT, Timestamp("2018-01-01 01:00:00")])
        result = dti.normalize()
        expected = DatetimeIndex([NaT, Timestamp("2018-01-01")])
        tm.assert_index_equal(result, expected)

    def test_normalize_tz(self):
        rng = date_range("1/1/2000 9:30", periods=10, freq="D", tz="US/Eastern")

        result = rng.normalize()  # does not preserve freq
        expected = date_range("1/1/2000", periods=10, freq="D", tz="US/Eastern")
        tm.assert_index_equal(result, expected._with_freq(None))

        assert result.is_normalized
        assert not rng.is_normalized

        rng = date_range("1/1/2000 9:30", periods=10, freq="D", tz="UTC")

        result = rng.normalize()
        expected = date_range("1/1/2000", periods=10, freq="D", tz="UTC")
        tm.assert_index_equal(result, expected)

        assert result.is_normalized
        assert not rng.is_normalized

        rng = date_range("1/1/2000 9:30", periods=10, freq="D", tz=tzlocal())
        result = rng.normalize()  # does not preserve freq
        expected = date_range("1/1/2000", periods=10, freq="D", tz=tzlocal())
        tm.assert_index_equal(result, expected._with_freq(None))

        assert result.is_normalized
        assert not rng.is_normalized

    @td.skip_if_windows
    @pytest.mark.parametrize(
        "timezone",
        [
            "US/Pacific",
            "US/Eastern",
            "UTC",
            "Asia/Kolkata",
            "Asia/Shanghai",
            "Australia/Canberra",
        ],
    )
    def test_normalize_tz_local(self, timezone):
        # GH#13459
        with tm.set_timezone(timezone):
            rng = date_range("1/1/2000 9:30", periods=10, freq="D", tz=tzlocal())

            result = rng.normalize()
            expected = date_range("1/1/2000", periods=10, freq="D", tz=tzlocal())
            expected = expected._with_freq(None)
            tm.assert_index_equal(result, expected)

            assert result.is_normalized
            assert not rng.is_normalized
