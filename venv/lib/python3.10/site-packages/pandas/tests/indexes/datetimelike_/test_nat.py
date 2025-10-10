import numpy as np
import pytest

from pandas import (
    DatetimeIndex,
    NaT,
    PeriodIndex,
    TimedeltaIndex,
)
import pandas._testing as tm


class NATests:
    def test_nat(self, index_without_na):
        empty_index = index_without_na[:0]

        index_with_na = index_without_na.copy(deep=True)
        index_with_na._data[1] = NaT

        assert empty_index._na_value is NaT
        assert index_with_na._na_value is NaT
        assert index_without_na._na_value is NaT

        idx = index_without_na
        assert idx._can_hold_na

        tm.assert_numpy_array_equal(idx._isnan, np.array([False, False]))
        assert idx.hasnans is False

        idx = index_with_na
        assert idx._can_hold_na

        tm.assert_numpy_array_equal(idx._isnan, np.array([False, True]))
        assert idx.hasnans is True


class TestDatetimeIndexNA(NATests):
    @pytest.fixture
    def index_without_na(self, tz_naive_fixture):
        tz = tz_naive_fixture
        return DatetimeIndex(["2011-01-01", "2011-01-02"], tz=tz)


class TestTimedeltaIndexNA(NATests):
    @pytest.fixture
    def index_without_na(self):
        return TimedeltaIndex(["1 days", "2 days"])


class TestPeriodIndexNA(NATests):
    @pytest.fixture
    def index_without_na(self):
        return PeriodIndex(["2011-01-01", "2011-01-02"], freq="D")
