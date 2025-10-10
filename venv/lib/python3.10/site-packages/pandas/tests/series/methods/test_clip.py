from datetime import datetime

import numpy as np
import pytest

import pandas as pd
from pandas import (
    Series,
    Timestamp,
    isna,
    notna,
)
import pandas._testing as tm


class TestSeriesClip:
    def test_clip(self, datetime_series):
        val = datetime_series.median()

        assert datetime_series.clip(lower=val).min() == val
        assert datetime_series.clip(upper=val).max() == val

        result = datetime_series.clip(-0.5, 0.5)
        expected = np.clip(datetime_series, -0.5, 0.5)
        tm.assert_series_equal(result, expected)
        assert isinstance(expected, Series)

    def test_clip_types_and_nulls(self):
        sers = [
            Series([np.nan, 1.0, 2.0, 3.0]),
            Series([None, "a", "b", "c"]),
            Series(pd.to_datetime([np.nan, 1, 2, 3], unit="D")),
        ]

        for s in sers:
            thresh = s[2]
            lower = s.clip(lower=thresh)
            upper = s.clip(upper=thresh)
            assert lower[notna(lower)].min() == thresh
            assert upper[notna(upper)].max() == thresh
            assert list(isna(s)) == list(isna(lower))
            assert list(isna(s)) == list(isna(upper))

    def test_series_clipping_with_na_values(self, any_numeric_ea_dtype, nulls_fixture):
        # Ensure that clipping method can handle NA values with out failing
        # GH#40581

        if nulls_fixture is pd.NaT:
            # constructor will raise, see
            #  test_constructor_mismatched_null_nullable_dtype
            pytest.skip("See test_constructor_mismatched_null_nullable_dtype")

        ser = Series([nulls_fixture, 1.0, 3.0], dtype=any_numeric_ea_dtype)
        s_clipped_upper = ser.clip(upper=2.0)
        s_clipped_lower = ser.clip(lower=2.0)

        expected_upper = Series([nulls_fixture, 1.0, 2.0], dtype=any_numeric_ea_dtype)
        expected_lower = Series([nulls_fixture, 2.0, 3.0], dtype=any_numeric_ea_dtype)

        tm.assert_series_equal(s_clipped_upper, expected_upper)
        tm.assert_series_equal(s_clipped_lower, expected_lower)

    def test_clip_with_na_args(self):
        """Should process np.nan argument as None"""
        # GH#17276
        s = Series([1, 2, 3])

        tm.assert_series_equal(s.clip(np.nan), Series([1, 2, 3]))
        tm.assert_series_equal(s.clip(upper=np.nan, lower=np.nan), Series([1, 2, 3]))

        # GH#19992
        msg = "Downcasting behavior in Series and DataFrame methods 'where'"
        # TODO: avoid this warning here?  seems like we should never be upcasting
        #  in the first place?
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = s.clip(lower=[0, 4, np.nan])
        tm.assert_series_equal(res, Series([1, 4, 3]))
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = s.clip(upper=[1, np.nan, 1])
        tm.assert_series_equal(res, Series([1, 2, 1]))

        # GH#40420
        s = Series([1, 2, 3])
        result = s.clip(0, [np.nan, np.nan, np.nan])
        tm.assert_series_equal(s, result)

    def test_clip_against_series(self):
        # GH#6966

        s = Series([1.0, 1.0, 4.0])

        lower = Series([1.0, 2.0, 3.0])
        upper = Series([1.5, 2.5, 3.5])

        tm.assert_series_equal(s.clip(lower, upper), Series([1.0, 2.0, 3.5]))
        tm.assert_series_equal(s.clip(1.5, upper), Series([1.5, 1.5, 3.5]))

    @pytest.mark.parametrize("inplace", [True, False])
    @pytest.mark.parametrize("upper", [[1, 2, 3], np.asarray([1, 2, 3])])
    def test_clip_against_list_like(self, inplace, upper):
        # GH#15390
        original = Series([5, 6, 7])
        result = original.clip(upper=upper, inplace=inplace)
        expected = Series([1, 2, 3])

        if inplace:
            result = original
        tm.assert_series_equal(result, expected, check_exact=True)

    def test_clip_with_datetimes(self):
        # GH#11838
        # naive and tz-aware datetimes

        t = Timestamp("2015-12-01 09:30:30")
        s = Series([Timestamp("2015-12-01 09:30:00"), Timestamp("2015-12-01 09:31:00")])
        result = s.clip(upper=t)
        expected = Series(
            [Timestamp("2015-12-01 09:30:00"), Timestamp("2015-12-01 09:30:30")]
        )
        tm.assert_series_equal(result, expected)

        t = Timestamp("2015-12-01 09:30:30", tz="US/Eastern")
        s = Series(
            [
                Timestamp("2015-12-01 09:30:00", tz="US/Eastern"),
                Timestamp("2015-12-01 09:31:00", tz="US/Eastern"),
            ]
        )
        result = s.clip(upper=t)
        expected = Series(
            [
                Timestamp("2015-12-01 09:30:00", tz="US/Eastern"),
                Timestamp("2015-12-01 09:30:30", tz="US/Eastern"),
            ]
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("dtype", [object, "M8[us]"])
    def test_clip_with_timestamps_and_oob_datetimes(self, dtype):
        # GH-42794
        ser = Series([datetime(1, 1, 1), datetime(9999, 9, 9)], dtype=dtype)

        result = ser.clip(lower=Timestamp.min, upper=Timestamp.max)
        expected = Series([Timestamp.min, Timestamp.max], dtype=dtype)

        tm.assert_series_equal(result, expected)
