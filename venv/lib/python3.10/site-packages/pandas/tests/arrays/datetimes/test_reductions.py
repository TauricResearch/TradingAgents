import numpy as np
import pytest

from pandas.core.dtypes.dtypes import DatetimeTZDtype

import pandas as pd
from pandas import NaT
import pandas._testing as tm
from pandas.core.arrays import DatetimeArray


class TestReductions:
    @pytest.fixture(params=["s", "ms", "us", "ns"])
    def unit(self, request):
        return request.param

    @pytest.fixture
    def arr1d(self, tz_naive_fixture):
        """Fixture returning DatetimeArray with parametrized timezones"""
        tz = tz_naive_fixture
        dtype = DatetimeTZDtype(tz=tz) if tz is not None else np.dtype("M8[ns]")
        arr = DatetimeArray._from_sequence(
            [
                "2000-01-03",
                "2000-01-03",
                "NaT",
                "2000-01-02",
                "2000-01-05",
                "2000-01-04",
            ],
            dtype=dtype,
        )
        return arr

    def test_min_max(self, arr1d, unit):
        arr = arr1d
        arr = arr.as_unit(unit)
        tz = arr.tz

        result = arr.min()
        expected = pd.Timestamp("2000-01-02", tz=tz).as_unit(unit)
        assert result == expected
        assert result.unit == expected.unit

        result = arr.max()
        expected = pd.Timestamp("2000-01-05", tz=tz).as_unit(unit)
        assert result == expected
        assert result.unit == expected.unit

        result = arr.min(skipna=False)
        assert result is NaT

        result = arr.max(skipna=False)
        assert result is NaT

    @pytest.mark.parametrize("tz", [None, "US/Central"])
    @pytest.mark.parametrize("skipna", [True, False])
    def test_min_max_empty(self, skipna, tz):
        dtype = DatetimeTZDtype(tz=tz) if tz is not None else np.dtype("M8[ns]")
        arr = DatetimeArray._from_sequence([], dtype=dtype)
        result = arr.min(skipna=skipna)
        assert result is NaT

        result = arr.max(skipna=skipna)
        assert result is NaT

    @pytest.mark.parametrize("tz", [None, "US/Central"])
    @pytest.mark.parametrize("skipna", [True, False])
    def test_median_empty(self, skipna, tz):
        dtype = DatetimeTZDtype(tz=tz) if tz is not None else np.dtype("M8[ns]")
        arr = DatetimeArray._from_sequence([], dtype=dtype)
        result = arr.median(skipna=skipna)
        assert result is NaT

        arr = arr.reshape(0, 3)
        result = arr.median(axis=0, skipna=skipna)
        expected = type(arr)._from_sequence([NaT, NaT, NaT], dtype=arr.dtype)
        tm.assert_equal(result, expected)

        result = arr.median(axis=1, skipna=skipna)
        expected = type(arr)._from_sequence([], dtype=arr.dtype)
        tm.assert_equal(result, expected)

    def test_median(self, arr1d):
        arr = arr1d

        result = arr.median()
        assert result == arr[0]
        result = arr.median(skipna=False)
        assert result is NaT

        result = arr.dropna().median(skipna=False)
        assert result == arr[0]

        result = arr.median(axis=0)
        assert result == arr[0]

    def test_median_axis(self, arr1d):
        arr = arr1d
        assert arr.median(axis=0) == arr.median()
        assert arr.median(axis=0, skipna=False) is NaT

        msg = r"abs\(axis\) must be less than ndim"
        with pytest.raises(ValueError, match=msg):
            arr.median(axis=1)

    @pytest.mark.filterwarnings("ignore:All-NaN slice encountered:RuntimeWarning")
    def test_median_2d(self, arr1d):
        arr = arr1d.reshape(1, -1)

        # axis = None
        assert arr.median() == arr1d.median()
        assert arr.median(skipna=False) is NaT

        # axis = 0
        result = arr.median(axis=0)
        expected = arr1d
        tm.assert_equal(result, expected)

        # Since column 3 is all-NaT, we get NaT there with or without skipna
        result = arr.median(axis=0, skipna=False)
        expected = arr1d
        tm.assert_equal(result, expected)

        # axis = 1
        result = arr.median(axis=1)
        expected = type(arr)._from_sequence([arr1d.median()], dtype=arr.dtype)
        tm.assert_equal(result, expected)

        result = arr.median(axis=1, skipna=False)
        expected = type(arr)._from_sequence([NaT], dtype=arr.dtype)
        tm.assert_equal(result, expected)

    def test_mean(self, arr1d):
        arr = arr1d

        # manually verified result
        expected = arr[0] + 0.4 * pd.Timedelta(days=1)

        result = arr.mean()
        assert result == expected
        result = arr.mean(skipna=False)
        assert result is NaT

        result = arr.dropna().mean(skipna=False)
        assert result == expected

        result = arr.mean(axis=0)
        assert result == expected

    def test_mean_2d(self):
        dti = pd.date_range("2016-01-01", periods=6, tz="US/Pacific")
        dta = dti._data.reshape(3, 2)

        result = dta.mean(axis=0)
        expected = dta[1]
        tm.assert_datetime_array_equal(result, expected)

        result = dta.mean(axis=1)
        expected = dta[:, 0] + pd.Timedelta(hours=12)
        tm.assert_datetime_array_equal(result, expected)

        result = dta.mean(axis=None)
        expected = dti.mean()
        assert result == expected

    @pytest.mark.parametrize("skipna", [True, False])
    def test_mean_empty(self, arr1d, skipna):
        arr = arr1d[:0]

        assert arr.mean(skipna=skipna) is NaT

        arr2d = arr.reshape(0, 3)
        result = arr2d.mean(axis=0, skipna=skipna)
        expected = DatetimeArray._from_sequence([NaT, NaT, NaT], dtype=arr.dtype)
        tm.assert_datetime_array_equal(result, expected)

        result = arr2d.mean(axis=1, skipna=skipna)
        expected = arr  # i.e. 1D, empty
        tm.assert_datetime_array_equal(result, expected)

        result = arr2d.mean(axis=None, skipna=skipna)
        assert result is NaT
