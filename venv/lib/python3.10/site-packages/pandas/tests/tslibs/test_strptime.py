from datetime import (
    datetime,
    timezone,
)

import numpy as np
import pytest

from pandas._libs.tslibs.dtypes import NpyDatetimeUnit
from pandas._libs.tslibs.strptime import array_strptime

from pandas import (
    NaT,
    Timestamp,
)
import pandas._testing as tm

creso_infer = NpyDatetimeUnit.NPY_FR_GENERIC.value


class TestArrayStrptimeResolutionInference:
    def test_array_strptime_resolution_all_nat(self):
        arr = np.array([NaT, np.nan], dtype=object)

        fmt = "%Y-%m-%d %H:%M:%S"
        res, _ = array_strptime(arr, fmt=fmt, utc=False, creso=creso_infer)
        assert res.dtype == "M8[s]"

        res, _ = array_strptime(arr, fmt=fmt, utc=True, creso=creso_infer)
        assert res.dtype == "M8[s]"

    @pytest.mark.parametrize("tz", [None, timezone.utc])
    def test_array_strptime_resolution_inference_homogeneous_strings(self, tz):
        dt = datetime(2016, 1, 2, 3, 4, 5, 678900, tzinfo=tz)

        fmt = "%Y-%m-%d %H:%M:%S"
        dtstr = dt.strftime(fmt)
        arr = np.array([dtstr] * 3, dtype=object)
        expected = np.array([dt.replace(tzinfo=None)] * 3, dtype="M8[s]")

        res, _ = array_strptime(arr, fmt=fmt, utc=False, creso=creso_infer)
        tm.assert_numpy_array_equal(res, expected)

        fmt = "%Y-%m-%d %H:%M:%S.%f"
        dtstr = dt.strftime(fmt)
        arr = np.array([dtstr] * 3, dtype=object)
        expected = np.array([dt.replace(tzinfo=None)] * 3, dtype="M8[us]")

        res, _ = array_strptime(arr, fmt=fmt, utc=False, creso=creso_infer)
        tm.assert_numpy_array_equal(res, expected)

        fmt = "ISO8601"
        res, _ = array_strptime(arr, fmt=fmt, utc=False, creso=creso_infer)
        tm.assert_numpy_array_equal(res, expected)

    @pytest.mark.parametrize("tz", [None, timezone.utc])
    def test_array_strptime_resolution_mixed(self, tz):
        dt = datetime(2016, 1, 2, 3, 4, 5, 678900, tzinfo=tz)

        ts = Timestamp(dt).as_unit("ns")

        arr = np.array([dt, ts], dtype=object)
        expected = np.array(
            [Timestamp(dt).as_unit("ns").asm8, ts.asm8],
            dtype="M8[ns]",
        )

        fmt = "%Y-%m-%d %H:%M:%S"
        res, _ = array_strptime(arr, fmt=fmt, utc=False, creso=creso_infer)
        tm.assert_numpy_array_equal(res, expected)

        fmt = "ISO8601"
        res, _ = array_strptime(arr, fmt=fmt, utc=False, creso=creso_infer)
        tm.assert_numpy_array_equal(res, expected)

    def test_array_strptime_resolution_todaynow(self):
        # specifically case where today/now is the *first* item
        vals = np.array(["today", np.datetime64("2017-01-01", "us")], dtype=object)

        now = Timestamp("now").asm8
        res, _ = array_strptime(vals, fmt="%Y-%m-%d", utc=False, creso=creso_infer)
        res2, _ = array_strptime(
            vals[::-1], fmt="%Y-%m-%d", utc=False, creso=creso_infer
        )

        # 1s is an arbitrary cutoff for call overhead; in local testing the
        #  actual difference is about 250us
        tolerance = np.timedelta64(1, "s")

        assert res.dtype == "M8[us]"
        assert abs(res[0] - now) < tolerance
        assert res[1] == vals[1]

        assert res2.dtype == "M8[us]"
        assert abs(res2[1] - now) < tolerance * 2
        assert res2[0] == vals[1]

    def test_array_strptime_str_outside_nano_range(self):
        vals = np.array(["2401-09-15"], dtype=object)
        expected = np.array(["2401-09-15"], dtype="M8[s]")
        fmt = "ISO8601"
        res, _ = array_strptime(vals, fmt=fmt, creso=creso_infer)
        tm.assert_numpy_array_equal(res, expected)

        # non-iso -> different path
        vals2 = np.array(["Sep 15, 2401"], dtype=object)
        expected2 = np.array(["2401-09-15"], dtype="M8[s]")
        fmt2 = "%b %d, %Y"
        res2, _ = array_strptime(vals2, fmt=fmt2, creso=creso_infer)
        tm.assert_numpy_array_equal(res2, expected2)
