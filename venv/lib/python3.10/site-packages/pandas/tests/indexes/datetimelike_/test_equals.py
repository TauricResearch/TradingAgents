"""
Tests shared for DatetimeIndex/TimedeltaIndex/PeriodIndex
"""
from datetime import (
    datetime,
    timedelta,
)

import numpy as np
import pytest

import pandas as pd
from pandas import (
    CategoricalIndex,
    DatetimeIndex,
    Index,
    PeriodIndex,
    TimedeltaIndex,
    date_range,
    period_range,
    timedelta_range,
)
import pandas._testing as tm


class EqualsTests:
    def test_not_equals_numeric(self, index):
        assert not index.equals(Index(index.asi8))
        assert not index.equals(Index(index.asi8.astype("u8")))
        assert not index.equals(Index(index.asi8).astype("f8"))

    def test_equals(self, index):
        assert index.equals(index)
        assert index.equals(index.astype(object))
        assert index.equals(CategoricalIndex(index))
        assert index.equals(CategoricalIndex(index.astype(object)))

    def test_not_equals_non_arraylike(self, index):
        assert not index.equals(list(index))

    def test_not_equals_strings(self, index):
        other = Index([str(x) for x in index], dtype=object)
        assert not index.equals(other)
        assert not index.equals(CategoricalIndex(other))

    def test_not_equals_misc_strs(self, index):
        other = Index(list("abc"))
        assert not index.equals(other)


class TestPeriodIndexEquals(EqualsTests):
    @pytest.fixture
    def index(self):
        return period_range("2013-01-01", periods=5, freq="D")

    # TODO: de-duplicate with other test_equals2 methods
    @pytest.mark.parametrize("freq", ["D", "M"])
    def test_equals2(self, freq):
        # GH#13107
        idx = PeriodIndex(["2011-01-01", "2011-01-02", "NaT"], freq=freq)
        assert idx.equals(idx)
        assert idx.equals(idx.copy())
        assert idx.equals(idx.astype(object))
        assert idx.astype(object).equals(idx)
        assert idx.astype(object).equals(idx.astype(object))
        assert not idx.equals(list(idx))
        assert not idx.equals(pd.Series(idx))

        idx2 = PeriodIndex(["2011-01-01", "2011-01-02", "NaT"], freq="h")
        assert not idx.equals(idx2)
        assert not idx.equals(idx2.copy())
        assert not idx.equals(idx2.astype(object))
        assert not idx.astype(object).equals(idx2)
        assert not idx.equals(list(idx2))
        assert not idx.equals(pd.Series(idx2))

        # same internal, different tz
        idx3 = PeriodIndex._simple_new(
            idx._values._simple_new(idx._values.asi8, dtype=pd.PeriodDtype("h"))
        )
        tm.assert_numpy_array_equal(idx.asi8, idx3.asi8)
        assert not idx.equals(idx3)
        assert not idx.equals(idx3.copy())
        assert not idx.equals(idx3.astype(object))
        assert not idx.astype(object).equals(idx3)
        assert not idx.equals(list(idx3))
        assert not idx.equals(pd.Series(idx3))


class TestDatetimeIndexEquals(EqualsTests):
    @pytest.fixture
    def index(self):
        return date_range("2013-01-01", periods=5)

    def test_equals2(self):
        # GH#13107
        idx = DatetimeIndex(["2011-01-01", "2011-01-02", "NaT"])
        assert idx.equals(idx)
        assert idx.equals(idx.copy())
        assert idx.equals(idx.astype(object))
        assert idx.astype(object).equals(idx)
        assert idx.astype(object).equals(idx.astype(object))
        assert not idx.equals(list(idx))
        assert not idx.equals(pd.Series(idx))

        idx2 = DatetimeIndex(["2011-01-01", "2011-01-02", "NaT"], tz="US/Pacific")
        assert not idx.equals(idx2)
        assert not idx.equals(idx2.copy())
        assert not idx.equals(idx2.astype(object))
        assert not idx.astype(object).equals(idx2)
        assert not idx.equals(list(idx2))
        assert not idx.equals(pd.Series(idx2))

        # same internal, different tz
        idx3 = DatetimeIndex(idx.asi8, tz="US/Pacific")
        tm.assert_numpy_array_equal(idx.asi8, idx3.asi8)
        assert not idx.equals(idx3)
        assert not idx.equals(idx3.copy())
        assert not idx.equals(idx3.astype(object))
        assert not idx.astype(object).equals(idx3)
        assert not idx.equals(list(idx3))
        assert not idx.equals(pd.Series(idx3))

        # check that we do not raise when comparing with OutOfBounds objects
        oob = Index([datetime(2500, 1, 1)] * 3, dtype=object)
        assert not idx.equals(oob)
        assert not idx2.equals(oob)
        assert not idx3.equals(oob)

        # check that we do not raise when comparing with OutOfBounds dt64
        oob2 = oob.map(np.datetime64)
        assert not idx.equals(oob2)
        assert not idx2.equals(oob2)
        assert not idx3.equals(oob2)

    @pytest.mark.parametrize("freq", ["B", "C"])
    def test_not_equals_bday(self, freq):
        rng = date_range("2009-01-01", "2010-01-01", freq=freq)
        assert not rng.equals(list(rng))


class TestTimedeltaIndexEquals(EqualsTests):
    @pytest.fixture
    def index(self):
        return timedelta_range("1 day", periods=10)

    def test_equals2(self):
        # GH#13107
        idx = TimedeltaIndex(["1 days", "2 days", "NaT"])
        assert idx.equals(idx)
        assert idx.equals(idx.copy())
        assert idx.equals(idx.astype(object))
        assert idx.astype(object).equals(idx)
        assert idx.astype(object).equals(idx.astype(object))
        assert not idx.equals(list(idx))
        assert not idx.equals(pd.Series(idx))

        idx2 = TimedeltaIndex(["2 days", "1 days", "NaT"])
        assert not idx.equals(idx2)
        assert not idx.equals(idx2.copy())
        assert not idx.equals(idx2.astype(object))
        assert not idx.astype(object).equals(idx2)
        assert not idx.astype(object).equals(idx2.astype(object))
        assert not idx.equals(list(idx2))
        assert not idx.equals(pd.Series(idx2))

        # Check that we dont raise OverflowError on comparisons outside the
        #  implementation range GH#28532
        oob = Index([timedelta(days=10**6)] * 3, dtype=object)
        assert not idx.equals(oob)
        assert not idx2.equals(oob)

        oob2 = Index([np.timedelta64(x) for x in oob], dtype=object)
        assert (oob == oob2).all()
        assert not idx.equals(oob2)
        assert not idx2.equals(oob2)

        oob3 = oob.map(np.timedelta64)
        assert (oob3 == oob).all()
        assert not idx.equals(oob3)
        assert not idx2.equals(oob3)
