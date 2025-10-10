from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from functools import partial
from operator import attrgetter

import dateutil
import dateutil.tz
from dateutil.tz import gettz
import numpy as np
import pytest
import pytz

from pandas._libs.tslibs import (
    OutOfBoundsDatetime,
    astype_overflowsafe,
    timezones,
)

import pandas as pd
from pandas import (
    DatetimeIndex,
    Index,
    Timestamp,
    date_range,
    offsets,
    to_datetime,
)
import pandas._testing as tm
from pandas.core.arrays import period_array


class TestDatetimeIndex:
    def test_closed_deprecated(self):
        # GH#52628
        msg = "The 'closed' keyword"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            DatetimeIndex([], closed=True)

    def test_normalize_deprecated(self):
        # GH#52628
        msg = "The 'normalize' keyword"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            DatetimeIndex([], normalize=True)

    def test_from_dt64_unsupported_unit(self):
        # GH#49292
        val = np.datetime64(1, "D")
        result = DatetimeIndex([val], tz="US/Pacific")

        expected = DatetimeIndex([val.astype("M8[s]")], tz="US/Pacific")
        tm.assert_index_equal(result, expected)

    def test_explicit_tz_none(self):
        # GH#48659
        dti = date_range("2016-01-01", periods=10, tz="UTC")

        msg = "Passed data is timezone-aware, incompatible with 'tz=None'"
        with pytest.raises(ValueError, match=msg):
            DatetimeIndex(dti, tz=None)

        with pytest.raises(ValueError, match=msg):
            DatetimeIndex(np.array(dti), tz=None)

        msg = "Cannot pass both a timezone-aware dtype and tz=None"
        with pytest.raises(ValueError, match=msg):
            DatetimeIndex([], dtype="M8[ns, UTC]", tz=None)

    def test_freq_validation_with_nat(self):
        # GH#11587 make sure we get a useful error message when generate_range
        #  raises
        msg = (
            "Inferred frequency None from passed values does not conform "
            "to passed frequency D"
        )
        with pytest.raises(ValueError, match=msg):
            DatetimeIndex([pd.NaT, Timestamp("2011-01-01")], freq="D")
        with pytest.raises(ValueError, match=msg):
            DatetimeIndex([pd.NaT, Timestamp("2011-01-01")._value], freq="D")

    # TODO: better place for tests shared by DTI/TDI?
    @pytest.mark.parametrize(
        "index",
        [
            date_range("2016-01-01", periods=5, tz="US/Pacific"),
            pd.timedelta_range("1 Day", periods=5),
        ],
    )
    def test_shallow_copy_inherits_array_freq(self, index):
        # If we pass a DTA/TDA to shallow_copy and dont specify a freq,
        #  we should inherit the array's freq, not our own.
        array = index._data

        arr = array[[0, 3, 2, 4, 1]]
        assert arr.freq is None

        result = index._shallow_copy(arr)
        assert result.freq is None

    def test_categorical_preserves_tz(self):
        # GH#18664 retain tz when going DTI-->Categorical-->DTI
        dti = DatetimeIndex(
            [pd.NaT, "2015-01-01", "1999-04-06 15:14:13", "2015-01-01"], tz="US/Eastern"
        )

        for dtobj in [dti, dti._data]:
            # works for DatetimeIndex or DatetimeArray

            ci = pd.CategoricalIndex(dtobj)
            carr = pd.Categorical(dtobj)
            cser = pd.Series(ci)

            for obj in [ci, carr, cser]:
                result = DatetimeIndex(obj)
                tm.assert_index_equal(result, dti)

    def test_dti_with_period_data_raises(self):
        # GH#23675
        data = pd.PeriodIndex(["2016Q1", "2016Q2"], freq="Q")

        with pytest.raises(TypeError, match="PeriodDtype data is invalid"):
            DatetimeIndex(data)

        with pytest.raises(TypeError, match="PeriodDtype data is invalid"):
            to_datetime(data)

        with pytest.raises(TypeError, match="PeriodDtype data is invalid"):
            DatetimeIndex(period_array(data))

        with pytest.raises(TypeError, match="PeriodDtype data is invalid"):
            to_datetime(period_array(data))

    def test_dti_with_timedelta64_data_raises(self):
        # GH#23675 deprecated, enforrced in GH#29794
        data = np.array([0], dtype="m8[ns]")
        msg = r"timedelta64\[ns\] cannot be converted to datetime64"
        with pytest.raises(TypeError, match=msg):
            DatetimeIndex(data)

        with pytest.raises(TypeError, match=msg):
            to_datetime(data)

        with pytest.raises(TypeError, match=msg):
            DatetimeIndex(pd.TimedeltaIndex(data))

        with pytest.raises(TypeError, match=msg):
            to_datetime(pd.TimedeltaIndex(data))

    def test_constructor_from_sparse_array(self):
        # https://github.com/pandas-dev/pandas/issues/35843
        values = [
            Timestamp("2012-05-01T01:00:00.000000"),
            Timestamp("2016-05-01T01:00:00.000000"),
        ]
        arr = pd.arrays.SparseArray(values)
        result = Index(arr)
        assert type(result) is Index
        assert result.dtype == arr.dtype

    def test_construction_caching(self):
        df = pd.DataFrame(
            {
                "dt": date_range("20130101", periods=3),
                "dttz": date_range("20130101", periods=3, tz="US/Eastern"),
                "dt_with_null": [
                    Timestamp("20130101"),
                    pd.NaT,
                    Timestamp("20130103"),
                ],
                "dtns": date_range("20130101", periods=3, freq="ns"),
            }
        )
        assert df.dttz.dtype.tz.zone == "US/Eastern"

    @pytest.mark.parametrize(
        "kwargs",
        [{"tz": "dtype.tz"}, {"dtype": "dtype"}, {"dtype": "dtype", "tz": "dtype.tz"}],
    )
    def test_construction_with_alt(self, kwargs, tz_aware_fixture):
        tz = tz_aware_fixture
        i = date_range("20130101", periods=5, freq="h", tz=tz)
        kwargs = {key: attrgetter(val)(i) for key, val in kwargs.items()}
        result = DatetimeIndex(i, **kwargs)
        tm.assert_index_equal(i, result)

    @pytest.mark.parametrize(
        "kwargs",
        [{"tz": "dtype.tz"}, {"dtype": "dtype"}, {"dtype": "dtype", "tz": "dtype.tz"}],
    )
    def test_construction_with_alt_tz_localize(self, kwargs, tz_aware_fixture):
        tz = tz_aware_fixture
        i = date_range("20130101", periods=5, freq="h", tz=tz)
        i = i._with_freq(None)
        kwargs = {key: attrgetter(val)(i) for key, val in kwargs.items()}

        if "tz" in kwargs:
            result = DatetimeIndex(i.asi8, tz="UTC").tz_convert(kwargs["tz"])

            expected = DatetimeIndex(i, **kwargs)
            tm.assert_index_equal(result, expected)

        # localize into the provided tz
        i2 = DatetimeIndex(i.tz_localize(None).asi8, tz="UTC")
        expected = i.tz_localize(None).tz_localize("UTC")
        tm.assert_index_equal(i2, expected)

        # incompat tz/dtype
        msg = "cannot supply both a tz and a dtype with a tz"
        with pytest.raises(ValueError, match=msg):
            DatetimeIndex(i.tz_localize(None).asi8, dtype=i.dtype, tz="US/Pacific")

    def test_construction_index_with_mixed_timezones(self):
        # gh-11488: no tz results in DatetimeIndex
        result = Index([Timestamp("2011-01-01"), Timestamp("2011-01-02")], name="idx")
        exp = DatetimeIndex(
            [Timestamp("2011-01-01"), Timestamp("2011-01-02")], name="idx"
        )
        tm.assert_index_equal(result, exp, exact=True)
        assert isinstance(result, DatetimeIndex)
        assert result.tz is None

        # same tz results in DatetimeIndex
        result = Index(
            [
                Timestamp("2011-01-01 10:00", tz="Asia/Tokyo"),
                Timestamp("2011-01-02 10:00", tz="Asia/Tokyo"),
            ],
            name="idx",
        )
        exp = DatetimeIndex(
            [Timestamp("2011-01-01 10:00"), Timestamp("2011-01-02 10:00")],
            tz="Asia/Tokyo",
            name="idx",
        )
        tm.assert_index_equal(result, exp, exact=True)
        assert isinstance(result, DatetimeIndex)
        assert result.tz is not None
        assert result.tz == exp.tz

        # same tz results in DatetimeIndex (DST)
        result = Index(
            [
                Timestamp("2011-01-01 10:00", tz="US/Eastern"),
                Timestamp("2011-08-01 10:00", tz="US/Eastern"),
            ],
            name="idx",
        )
        exp = DatetimeIndex(
            [Timestamp("2011-01-01 10:00"), Timestamp("2011-08-01 10:00")],
            tz="US/Eastern",
            name="idx",
        )
        tm.assert_index_equal(result, exp, exact=True)
        assert isinstance(result, DatetimeIndex)
        assert result.tz is not None
        assert result.tz == exp.tz

        # Different tz results in Index(dtype=object)
        result = Index(
            [
                Timestamp("2011-01-01 10:00"),
                Timestamp("2011-01-02 10:00", tz="US/Eastern"),
            ],
            name="idx",
        )
        exp = Index(
            [
                Timestamp("2011-01-01 10:00"),
                Timestamp("2011-01-02 10:00", tz="US/Eastern"),
            ],
            dtype="object",
            name="idx",
        )
        tm.assert_index_equal(result, exp, exact=True)
        assert not isinstance(result, DatetimeIndex)

        result = Index(
            [
                Timestamp("2011-01-01 10:00", tz="Asia/Tokyo"),
                Timestamp("2011-01-02 10:00", tz="US/Eastern"),
            ],
            name="idx",
        )
        exp = Index(
            [
                Timestamp("2011-01-01 10:00", tz="Asia/Tokyo"),
                Timestamp("2011-01-02 10:00", tz="US/Eastern"),
            ],
            dtype="object",
            name="idx",
        )
        tm.assert_index_equal(result, exp, exact=True)
        assert not isinstance(result, DatetimeIndex)

        msg = "DatetimeIndex has mixed timezones"
        msg_depr = "parsing datetimes with mixed time zones will raise an error"
        with pytest.raises(TypeError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=msg_depr):
                DatetimeIndex(["2013-11-02 22:00-05:00", "2013-11-03 22:00-06:00"])

        # length = 1
        result = Index([Timestamp("2011-01-01")], name="idx")
        exp = DatetimeIndex([Timestamp("2011-01-01")], name="idx")
        tm.assert_index_equal(result, exp, exact=True)
        assert isinstance(result, DatetimeIndex)
        assert result.tz is None

        # length = 1 with tz
        result = Index([Timestamp("2011-01-01 10:00", tz="Asia/Tokyo")], name="idx")
        exp = DatetimeIndex(
            [Timestamp("2011-01-01 10:00")], tz="Asia/Tokyo", name="idx"
        )
        tm.assert_index_equal(result, exp, exact=True)
        assert isinstance(result, DatetimeIndex)
        assert result.tz is not None
        assert result.tz == exp.tz

    def test_construction_index_with_mixed_timezones_with_NaT(self):
        # see gh-11488
        result = Index(
            [pd.NaT, Timestamp("2011-01-01"), pd.NaT, Timestamp("2011-01-02")],
            name="idx",
        )
        exp = DatetimeIndex(
            [pd.NaT, Timestamp("2011-01-01"), pd.NaT, Timestamp("2011-01-02")],
            name="idx",
        )
        tm.assert_index_equal(result, exp, exact=True)
        assert isinstance(result, DatetimeIndex)
        assert result.tz is None

        # Same tz results in DatetimeIndex
        result = Index(
            [
                pd.NaT,
                Timestamp("2011-01-01 10:00", tz="Asia/Tokyo"),
                pd.NaT,
                Timestamp("2011-01-02 10:00", tz="Asia/Tokyo"),
            ],
            name="idx",
        )
        exp = DatetimeIndex(
            [
                pd.NaT,
                Timestamp("2011-01-01 10:00"),
                pd.NaT,
                Timestamp("2011-01-02 10:00"),
            ],
            tz="Asia/Tokyo",
            name="idx",
        )
        tm.assert_index_equal(result, exp, exact=True)
        assert isinstance(result, DatetimeIndex)
        assert result.tz is not None
        assert result.tz == exp.tz

        # same tz results in DatetimeIndex (DST)
        result = Index(
            [
                Timestamp("2011-01-01 10:00", tz="US/Eastern"),
                pd.NaT,
                Timestamp("2011-08-01 10:00", tz="US/Eastern"),
            ],
            name="idx",
        )
        exp = DatetimeIndex(
            [Timestamp("2011-01-01 10:00"), pd.NaT, Timestamp("2011-08-01 10:00")],
            tz="US/Eastern",
            name="idx",
        )
        tm.assert_index_equal(result, exp, exact=True)
        assert isinstance(result, DatetimeIndex)
        assert result.tz is not None
        assert result.tz == exp.tz

        # different tz results in Index(dtype=object)
        result = Index(
            [
                pd.NaT,
                Timestamp("2011-01-01 10:00"),
                pd.NaT,
                Timestamp("2011-01-02 10:00", tz="US/Eastern"),
            ],
            name="idx",
        )
        exp = Index(
            [
                pd.NaT,
                Timestamp("2011-01-01 10:00"),
                pd.NaT,
                Timestamp("2011-01-02 10:00", tz="US/Eastern"),
            ],
            dtype="object",
            name="idx",
        )
        tm.assert_index_equal(result, exp, exact=True)
        assert not isinstance(result, DatetimeIndex)

        result = Index(
            [
                pd.NaT,
                Timestamp("2011-01-01 10:00", tz="Asia/Tokyo"),
                pd.NaT,
                Timestamp("2011-01-02 10:00", tz="US/Eastern"),
            ],
            name="idx",
        )
        exp = Index(
            [
                pd.NaT,
                Timestamp("2011-01-01 10:00", tz="Asia/Tokyo"),
                pd.NaT,
                Timestamp("2011-01-02 10:00", tz="US/Eastern"),
            ],
            dtype="object",
            name="idx",
        )
        tm.assert_index_equal(result, exp, exact=True)
        assert not isinstance(result, DatetimeIndex)

        # all NaT
        result = Index([pd.NaT, pd.NaT], name="idx")
        exp = DatetimeIndex([pd.NaT, pd.NaT], name="idx")
        tm.assert_index_equal(result, exp, exact=True)
        assert isinstance(result, DatetimeIndex)
        assert result.tz is None

    def test_construction_dti_with_mixed_timezones(self):
        # GH 11488 (not changed, added explicit tests)

        # no tz results in DatetimeIndex
        result = DatetimeIndex(
            [Timestamp("2011-01-01"), Timestamp("2011-01-02")], name="idx"
        )
        exp = DatetimeIndex(
            [Timestamp("2011-01-01"), Timestamp("2011-01-02")], name="idx"
        )
        tm.assert_index_equal(result, exp, exact=True)
        assert isinstance(result, DatetimeIndex)

        # same tz results in DatetimeIndex
        result = DatetimeIndex(
            [
                Timestamp("2011-01-01 10:00", tz="Asia/Tokyo"),
                Timestamp("2011-01-02 10:00", tz="Asia/Tokyo"),
            ],
            name="idx",
        )
        exp = DatetimeIndex(
            [Timestamp("2011-01-01 10:00"), Timestamp("2011-01-02 10:00")],
            tz="Asia/Tokyo",
            name="idx",
        )
        tm.assert_index_equal(result, exp, exact=True)
        assert isinstance(result, DatetimeIndex)

        # same tz results in DatetimeIndex (DST)
        result = DatetimeIndex(
            [
                Timestamp("2011-01-01 10:00", tz="US/Eastern"),
                Timestamp("2011-08-01 10:00", tz="US/Eastern"),
            ],
            name="idx",
        )
        exp = DatetimeIndex(
            [Timestamp("2011-01-01 10:00"), Timestamp("2011-08-01 10:00")],
            tz="US/Eastern",
            name="idx",
        )
        tm.assert_index_equal(result, exp, exact=True)
        assert isinstance(result, DatetimeIndex)

        # tz mismatch affecting to tz-aware raises TypeError/ValueError

        msg = "cannot be converted to datetime64"
        with pytest.raises(ValueError, match=msg):
            DatetimeIndex(
                [
                    Timestamp("2011-01-01 10:00", tz="Asia/Tokyo"),
                    Timestamp("2011-01-02 10:00", tz="US/Eastern"),
                ],
                name="idx",
            )

        # pre-2.0 this raised bc of awareness mismatch. in 2.0 with a tz#
        #  specified we behave as if this was called pointwise, so
        #  the naive Timestamp is treated as a wall time.
        dti = DatetimeIndex(
            [
                Timestamp("2011-01-01 10:00"),
                Timestamp("2011-01-02 10:00", tz="US/Eastern"),
            ],
            tz="Asia/Tokyo",
            name="idx",
        )
        expected = DatetimeIndex(
            [
                Timestamp("2011-01-01 10:00", tz="Asia/Tokyo"),
                Timestamp("2011-01-02 10:00", tz="US/Eastern").tz_convert("Asia/Tokyo"),
            ],
            tz="Asia/Tokyo",
            name="idx",
        )
        tm.assert_index_equal(dti, expected)

        # pre-2.0 mixed-tz scalars raised even if a tz/dtype was specified.
        #  as of 2.0 we successfully return the requested tz/dtype
        dti = DatetimeIndex(
            [
                Timestamp("2011-01-01 10:00", tz="Asia/Tokyo"),
                Timestamp("2011-01-02 10:00", tz="US/Eastern"),
            ],
            tz="US/Eastern",
            name="idx",
        )
        expected = DatetimeIndex(
            [
                Timestamp("2011-01-01 10:00", tz="Asia/Tokyo").tz_convert("US/Eastern"),
                Timestamp("2011-01-02 10:00", tz="US/Eastern"),
            ],
            tz="US/Eastern",
            name="idx",
        )
        tm.assert_index_equal(dti, expected)

        # same thing but pass dtype instead of tz
        dti = DatetimeIndex(
            [
                Timestamp("2011-01-01 10:00", tz="Asia/Tokyo"),
                Timestamp("2011-01-02 10:00", tz="US/Eastern"),
            ],
            dtype="M8[ns, US/Eastern]",
            name="idx",
        )
        tm.assert_index_equal(dti, expected)

    def test_construction_base_constructor(self):
        arr = [Timestamp("2011-01-01"), pd.NaT, Timestamp("2011-01-03")]
        tm.assert_index_equal(Index(arr), DatetimeIndex(arr))
        tm.assert_index_equal(Index(np.array(arr)), DatetimeIndex(np.array(arr)))

        arr = [np.nan, pd.NaT, Timestamp("2011-01-03")]
        tm.assert_index_equal(Index(arr), DatetimeIndex(arr))
        tm.assert_index_equal(Index(np.array(arr)), DatetimeIndex(np.array(arr)))

    def test_construction_outofbounds(self):
        # GH 13663
        dates = [
            datetime(3000, 1, 1),
            datetime(4000, 1, 1),
            datetime(5000, 1, 1),
            datetime(6000, 1, 1),
        ]
        exp = Index(dates, dtype=object)
        # coerces to object
        tm.assert_index_equal(Index(dates), exp)

        msg = "^Out of bounds nanosecond timestamp: 3000-01-01 00:00:00, at position 0$"
        with pytest.raises(OutOfBoundsDatetime, match=msg):
            # can't create DatetimeIndex
            DatetimeIndex(dates)

    @pytest.mark.parametrize("data", [["1400-01-01"], [datetime(1400, 1, 1)]])
    def test_dti_date_out_of_range(self, data):
        # GH#1475
        msg = (
            "^Out of bounds nanosecond timestamp: "
            "1400-01-01( 00:00:00)?, at position 0$"
        )
        with pytest.raises(OutOfBoundsDatetime, match=msg):
            DatetimeIndex(data)

    def test_construction_with_ndarray(self):
        # GH 5152
        dates = [datetime(2013, 10, 7), datetime(2013, 10, 8), datetime(2013, 10, 9)]
        data = DatetimeIndex(dates, freq=offsets.BDay()).values
        result = DatetimeIndex(data, freq=offsets.BDay())
        expected = DatetimeIndex(["2013-10-07", "2013-10-08", "2013-10-09"], freq="B")
        tm.assert_index_equal(result, expected)

    def test_integer_values_and_tz_interpreted_as_utc(self):
        # GH-24559
        val = np.datetime64("2000-01-01 00:00:00", "ns")
        values = np.array([val.view("i8")])

        result = DatetimeIndex(values).tz_localize("US/Central")

        expected = DatetimeIndex(["2000-01-01T00:00:00"], dtype="M8[ns, US/Central]")
        tm.assert_index_equal(result, expected)

        # but UTC is *not* deprecated.
        with tm.assert_produces_warning(None):
            result = DatetimeIndex(values, tz="UTC")
        expected = DatetimeIndex(["2000-01-01T00:00:00"], dtype="M8[ns, UTC]")
        tm.assert_index_equal(result, expected)

    def test_constructor_coverage(self):
        msg = r"DatetimeIndex\(\.\.\.\) must be called with a collection"
        with pytest.raises(TypeError, match=msg):
            DatetimeIndex("1/1/2000")

        # generator expression
        gen = (datetime(2000, 1, 1) + timedelta(i) for i in range(10))
        result = DatetimeIndex(gen)
        expected = DatetimeIndex(
            [datetime(2000, 1, 1) + timedelta(i) for i in range(10)]
        )
        tm.assert_index_equal(result, expected)

        # NumPy string array
        strings = np.array(["2000-01-01", "2000-01-02", "2000-01-03"])
        result = DatetimeIndex(strings)
        expected = DatetimeIndex(strings.astype("O"))
        tm.assert_index_equal(result, expected)

        from_ints = DatetimeIndex(expected.asi8)
        tm.assert_index_equal(from_ints, expected)

        # string with NaT
        strings = np.array(["2000-01-01", "2000-01-02", "NaT"])
        result = DatetimeIndex(strings)
        expected = DatetimeIndex(strings.astype("O"))
        tm.assert_index_equal(result, expected)

        from_ints = DatetimeIndex(expected.asi8)
        tm.assert_index_equal(from_ints, expected)

        # non-conforming
        msg = (
            "Inferred frequency None from passed values does not conform "
            "to passed frequency D"
        )
        with pytest.raises(ValueError, match=msg):
            DatetimeIndex(["2000-01-01", "2000-01-02", "2000-01-04"], freq="D")

    @pytest.mark.parametrize("freq", ["YS", "W-SUN"])
    def test_constructor_datetime64_tzformat(self, freq):
        # see GH#6572: ISO 8601 format results in stdlib timezone object
        idx = date_range(
            "2013-01-01T00:00:00-05:00", "2016-01-01T23:59:59-05:00", freq=freq
        )
        expected = date_range(
            "2013-01-01T00:00:00",
            "2016-01-01T23:59:59",
            freq=freq,
            tz=timezone(timedelta(minutes=-300)),
        )
        tm.assert_index_equal(idx, expected)
        # Unable to use `US/Eastern` because of DST
        expected_i8 = date_range(
            "2013-01-01T00:00:00", "2016-01-01T23:59:59", freq=freq, tz="America/Lima"
        )
        tm.assert_numpy_array_equal(idx.asi8, expected_i8.asi8)

        idx = date_range(
            "2013-01-01T00:00:00+09:00", "2016-01-01T23:59:59+09:00", freq=freq
        )
        expected = date_range(
            "2013-01-01T00:00:00",
            "2016-01-01T23:59:59",
            freq=freq,
            tz=timezone(timedelta(minutes=540)),
        )
        tm.assert_index_equal(idx, expected)
        expected_i8 = date_range(
            "2013-01-01T00:00:00", "2016-01-01T23:59:59", freq=freq, tz="Asia/Tokyo"
        )
        tm.assert_numpy_array_equal(idx.asi8, expected_i8.asi8)

        # Non ISO 8601 format results in dateutil.tz.tzoffset
        idx = date_range("2013/1/1 0:00:00-5:00", "2016/1/1 23:59:59-5:00", freq=freq)
        expected = date_range(
            "2013-01-01T00:00:00",
            "2016-01-01T23:59:59",
            freq=freq,
            tz=timezone(timedelta(minutes=-300)),
        )
        tm.assert_index_equal(idx, expected)
        # Unable to use `US/Eastern` because of DST
        expected_i8 = date_range(
            "2013-01-01T00:00:00", "2016-01-01T23:59:59", freq=freq, tz="America/Lima"
        )
        tm.assert_numpy_array_equal(idx.asi8, expected_i8.asi8)

        idx = date_range("2013/1/1 0:00:00+9:00", "2016/1/1 23:59:59+09:00", freq=freq)
        expected = date_range(
            "2013-01-01T00:00:00",
            "2016-01-01T23:59:59",
            freq=freq,
            tz=timezone(timedelta(minutes=540)),
        )
        tm.assert_index_equal(idx, expected)
        expected_i8 = date_range(
            "2013-01-01T00:00:00", "2016-01-01T23:59:59", freq=freq, tz="Asia/Tokyo"
        )
        tm.assert_numpy_array_equal(idx.asi8, expected_i8.asi8)

    def test_constructor_dtype(self):
        # passing a dtype with a tz should localize
        idx = DatetimeIndex(
            ["2013-01-01", "2013-01-02"], dtype="datetime64[ns, US/Eastern]"
        )
        expected = (
            DatetimeIndex(["2013-01-01", "2013-01-02"])
            .as_unit("ns")
            .tz_localize("US/Eastern")
        )
        tm.assert_index_equal(idx, expected)

        idx = DatetimeIndex(["2013-01-01", "2013-01-02"], tz="US/Eastern").as_unit("ns")
        tm.assert_index_equal(idx, expected)

    def test_constructor_dtype_tz_mismatch_raises(self):
        # if we already have a tz and its not the same, then raise
        idx = DatetimeIndex(
            ["2013-01-01", "2013-01-02"], dtype="datetime64[ns, US/Eastern]"
        )

        msg = (
            "cannot supply both a tz and a timezone-naive dtype "
            r"\(i\.e\. datetime64\[ns\]\)"
        )
        with pytest.raises(ValueError, match=msg):
            DatetimeIndex(idx, dtype="datetime64[ns]")

        # this is effectively trying to convert tz's
        msg = "data is already tz-aware US/Eastern, unable to set specified tz: CET"
        with pytest.raises(TypeError, match=msg):
            DatetimeIndex(idx, dtype="datetime64[ns, CET]")
        msg = "cannot supply both a tz and a dtype with a tz"
        with pytest.raises(ValueError, match=msg):
            DatetimeIndex(idx, tz="CET", dtype="datetime64[ns, US/Eastern]")

        result = DatetimeIndex(idx, dtype="datetime64[ns, US/Eastern]")
        tm.assert_index_equal(idx, result)

    @pytest.mark.parametrize("dtype", [object, np.int32, np.int64])
    def test_constructor_invalid_dtype_raises(self, dtype):
        # GH 23986
        msg = "Unexpected value for 'dtype'"
        with pytest.raises(ValueError, match=msg):
            DatetimeIndex([1, 2], dtype=dtype)

    def test_000constructor_resolution(self):
        # 2252
        t1 = Timestamp((1352934390 * 1000000000) + 1000000 + 1000 + 1)
        idx = DatetimeIndex([t1])

        assert idx.nanosecond[0] == t1.nanosecond

    def test_disallow_setting_tz(self):
        # GH 3746
        dti = DatetimeIndex(["2010"], tz="UTC")
        msg = "Cannot directly set timezone"
        with pytest.raises(AttributeError, match=msg):
            dti.tz = pytz.timezone("US/Pacific")

    @pytest.mark.parametrize(
        "tz",
        [
            None,
            "America/Los_Angeles",
            pytz.timezone("America/Los_Angeles"),
            Timestamp("2000", tz="America/Los_Angeles").tz,
        ],
    )
    def test_constructor_start_end_with_tz(self, tz):
        # GH 18595
        start = Timestamp("2013-01-01 06:00:00", tz="America/Los_Angeles")
        end = Timestamp("2013-01-02 06:00:00", tz="America/Los_Angeles")
        result = date_range(freq="D", start=start, end=end, tz=tz)
        expected = DatetimeIndex(
            ["2013-01-01 06:00:00", "2013-01-02 06:00:00"],
            dtype="M8[ns, America/Los_Angeles]",
            freq="D",
        )
        tm.assert_index_equal(result, expected)
        # Especially assert that the timezone is consistent for pytz
        assert pytz.timezone("America/Los_Angeles") is result.tz

    @pytest.mark.parametrize("tz", ["US/Pacific", "US/Eastern", "Asia/Tokyo"])
    def test_constructor_with_non_normalized_pytz(self, tz):
        # GH 18595
        non_norm_tz = Timestamp("2010", tz=tz).tz
        result = DatetimeIndex(["2010"], tz=non_norm_tz)
        assert pytz.timezone(tz) is result.tz

    def test_constructor_timestamp_near_dst(self):
        # GH 20854
        ts = [
            Timestamp("2016-10-30 03:00:00+0300", tz="Europe/Helsinki"),
            Timestamp("2016-10-30 03:00:00+0200", tz="Europe/Helsinki"),
        ]
        result = DatetimeIndex(ts)
        expected = DatetimeIndex([ts[0].to_pydatetime(), ts[1].to_pydatetime()])
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("klass", [Index, DatetimeIndex])
    @pytest.mark.parametrize("box", [np.array, partial(np.array, dtype=object), list])
    @pytest.mark.parametrize(
        "tz, dtype",
        [("US/Pacific", "datetime64[ns, US/Pacific]"), (None, "datetime64[ns]")],
    )
    def test_constructor_with_int_tz(self, klass, box, tz, dtype):
        # GH 20997, 20964
        ts = Timestamp("2018-01-01", tz=tz).as_unit("ns")
        result = klass(box([ts._value]), dtype=dtype)
        expected = klass([ts])
        assert result == expected

    def test_construction_int_rountrip(self, tz_naive_fixture):
        # GH 12619, GH#24559
        tz = tz_naive_fixture

        result = 1293858000000000000
        expected = DatetimeIndex([result], tz=tz).asi8[0]
        assert result == expected

    def test_construction_from_replaced_timestamps_with_dst(self):
        # GH 18785
        index = date_range(
            Timestamp(2000, 12, 31),
            Timestamp(2005, 12, 31),
            freq="YE-DEC",
            tz="Australia/Melbourne",
        )
        result = DatetimeIndex([x.replace(month=6, day=1) for x in index])
        expected = DatetimeIndex(
            [
                "2000-06-01 00:00:00",
                "2001-06-01 00:00:00",
                "2002-06-01 00:00:00",
                "2003-06-01 00:00:00",
                "2004-06-01 00:00:00",
                "2005-06-01 00:00:00",
            ],
            tz="Australia/Melbourne",
        )
        tm.assert_index_equal(result, expected)

    def test_construction_with_tz_and_tz_aware_dti(self):
        # GH 23579
        dti = date_range("2016-01-01", periods=3, tz="US/Central")
        msg = "data is already tz-aware US/Central, unable to set specified tz"
        with pytest.raises(TypeError, match=msg):
            DatetimeIndex(dti, tz="Asia/Tokyo")

    def test_construction_with_nat_and_tzlocal(self):
        tz = dateutil.tz.tzlocal()
        result = DatetimeIndex(["2018", "NaT"], tz=tz)
        expected = DatetimeIndex([Timestamp("2018", tz=tz), pd.NaT])
        tm.assert_index_equal(result, expected)

    def test_constructor_with_ambiguous_keyword_arg(self):
        # GH 35297

        expected = DatetimeIndex(
            ["2020-11-01 01:00:00", "2020-11-02 01:00:00"],
            dtype="datetime64[ns, America/New_York]",
            freq="D",
            ambiguous=False,
        )

        # ambiguous keyword in start
        timezone = "America/New_York"
        start = Timestamp(year=2020, month=11, day=1, hour=1).tz_localize(
            timezone, ambiguous=False
        )
        result = date_range(start=start, periods=2, ambiguous=False)
        tm.assert_index_equal(result, expected)

        # ambiguous keyword in end
        timezone = "America/New_York"
        end = Timestamp(year=2020, month=11, day=2, hour=1).tz_localize(
            timezone, ambiguous=False
        )
        result = date_range(end=end, periods=2, ambiguous=False)
        tm.assert_index_equal(result, expected)

    def test_constructor_with_nonexistent_keyword_arg(self, warsaw):
        # GH 35297
        timezone = warsaw

        # nonexistent keyword in start
        start = Timestamp("2015-03-29 02:30:00").tz_localize(
            timezone, nonexistent="shift_forward"
        )
        result = date_range(start=start, periods=2, freq="h")
        expected = DatetimeIndex(
            [
                Timestamp("2015-03-29 03:00:00+02:00", tz=timezone),
                Timestamp("2015-03-29 04:00:00+02:00", tz=timezone),
            ]
        )

        tm.assert_index_equal(result, expected)

        # nonexistent keyword in end
        end = start
        result = date_range(end=end, periods=2, freq="h")
        expected = DatetimeIndex(
            [
                Timestamp("2015-03-29 01:00:00+01:00", tz=timezone),
                Timestamp("2015-03-29 03:00:00+02:00", tz=timezone),
            ]
        )

        tm.assert_index_equal(result, expected)

    def test_constructor_no_precision_raises(self):
        # GH-24753, GH-24739

        msg = "with no precision is not allowed"
        with pytest.raises(ValueError, match=msg):
            DatetimeIndex(["2000"], dtype="datetime64")

        msg = "The 'datetime64' dtype has no unit. Please pass in"
        with pytest.raises(ValueError, match=msg):
            Index(["2000"], dtype="datetime64")

    def test_constructor_wrong_precision_raises(self):
        dti = DatetimeIndex(["2000"], dtype="datetime64[us]")
        assert dti.dtype == "M8[us]"
        assert dti[0] == Timestamp(2000, 1, 1)

    def test_index_constructor_with_numpy_object_array_and_timestamp_tz_with_nan(self):
        # GH 27011
        result = Index(np.array([Timestamp("2019", tz="UTC"), np.nan], dtype=object))
        expected = DatetimeIndex([Timestamp("2019", tz="UTC"), pd.NaT])
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("tz", [pytz.timezone("US/Eastern"), gettz("US/Eastern")])
    def test_dti_from_tzaware_datetime(self, tz):
        d = [datetime(2012, 8, 19, tzinfo=tz)]

        index = DatetimeIndex(d)
        assert timezones.tz_compare(index.tz, tz)

    @pytest.mark.parametrize("tzstr", ["US/Eastern", "dateutil/US/Eastern"])
    def test_dti_tz_constructors(self, tzstr):
        """Test different DatetimeIndex constructions with timezone
        Follow-up of GH#4229
        """
        arr = ["11/10/2005 08:00:00", "11/10/2005 09:00:00"]

        idx1 = to_datetime(arr).tz_localize(tzstr)
        idx2 = date_range(start="2005-11-10 08:00:00", freq="h", periods=2, tz=tzstr)
        idx2 = idx2._with_freq(None)  # the others all have freq=None
        idx3 = DatetimeIndex(arr, tz=tzstr)
        idx4 = DatetimeIndex(np.array(arr), tz=tzstr)

        for other in [idx2, idx3, idx4]:
            tm.assert_index_equal(idx1, other)

    def test_dti_construction_idempotent(self, unit):
        rng = date_range(
            "03/12/2012 00:00", periods=10, freq="W-FRI", tz="US/Eastern", unit=unit
        )
        rng2 = DatetimeIndex(data=rng, tz="US/Eastern")
        tm.assert_index_equal(rng, rng2)

    @pytest.mark.parametrize("prefix", ["", "dateutil/"])
    def test_dti_constructor_static_tzinfo(self, prefix):
        # it works!
        index = DatetimeIndex([datetime(2012, 1, 1)], tz=prefix + "EST")
        index.hour
        index[0]

    @pytest.mark.parametrize("tzstr", ["US/Eastern", "dateutil/US/Eastern"])
    def test_dti_convert_datetime_list(self, tzstr):
        dr = date_range("2012-06-02", periods=10, tz=tzstr, name="foo")
        dr2 = DatetimeIndex(list(dr), name="foo", freq="D")
        tm.assert_index_equal(dr, dr2)

    @pytest.mark.parametrize(
        "tz",
        [
            pytz.timezone("US/Eastern"),
            gettz("US/Eastern"),
        ],
    )
    @pytest.mark.parametrize("use_str", [True, False])
    @pytest.mark.parametrize("box_cls", [Timestamp, DatetimeIndex])
    def test_dti_ambiguous_matches_timestamp(self, tz, use_str, box_cls, request):
        # GH#47471 check that we get the same raising behavior in the DTI
        # constructor and Timestamp constructor
        dtstr = "2013-11-03 01:59:59.999999"
        item = dtstr
        if not use_str:
            item = Timestamp(dtstr).to_pydatetime()
        if box_cls is not Timestamp:
            item = [item]

        if not use_str and isinstance(tz, dateutil.tz.tzfile):
            # FIXME: The Timestamp constructor here behaves differently than all
            #  the other cases bc with dateutil/zoneinfo tzinfos we implicitly
            #  get fold=0. Having this raise is not important, but having the
            #  behavior be consistent across cases is.
            mark = pytest.mark.xfail(reason="We implicitly get fold=0.")
            request.applymarker(mark)

        with pytest.raises(pytz.AmbiguousTimeError, match=dtstr):
            box_cls(item, tz=tz)

    @pytest.mark.parametrize("tz", [None, "UTC", "US/Pacific"])
    def test_dti_constructor_with_non_nano_dtype(self, tz):
        # GH#55756, GH#54620
        ts = Timestamp("2999-01-01")
        dtype = "M8[us]"
        if tz is not None:
            dtype = f"M8[us, {tz}]"
        vals = [ts, "2999-01-02 03:04:05.678910", 2500]
        result = DatetimeIndex(vals, dtype=dtype)
        # The 2500 is interpreted as microseconds, consistent with what
        #  we would get if we created DatetimeIndexes from vals[:2] and vals[2:]
        #  and concated the results.
        pointwise = [
            vals[0].tz_localize(tz),
            Timestamp(vals[1], tz=tz),
            to_datetime(vals[2], unit="us", utc=True).tz_convert(tz),
        ]
        exp_vals = [x.as_unit("us").asm8 for x in pointwise]
        exp_arr = np.array(exp_vals, dtype="M8[us]")
        expected = DatetimeIndex(exp_arr, dtype="M8[us]")
        if tz is not None:
            expected = expected.tz_localize("UTC").tz_convert(tz)
        tm.assert_index_equal(result, expected)

        result2 = DatetimeIndex(np.array(vals, dtype=object), dtype=dtype)
        tm.assert_index_equal(result2, expected)

    def test_dti_constructor_with_non_nano_now_today(self):
        # GH#55756
        now = Timestamp.now()
        today = Timestamp.today()
        result = DatetimeIndex(["now", "today"], dtype="M8[s]")
        assert result.dtype == "M8[s]"

        # result may not exactly match [now, today] so we'll test it up to a tolerance.
        #  (it *may* match exactly due to rounding)
        tolerance = pd.Timedelta(microseconds=1)

        diff0 = result[0] - now.as_unit("s")
        assert diff0 >= pd.Timedelta(0)
        assert diff0 < tolerance

        diff1 = result[1] - today.as_unit("s")
        assert diff1 >= pd.Timedelta(0)
        assert diff1 < tolerance

    def test_dti_constructor_object_float_matches_float_dtype(self):
        # GH#55780
        arr = np.array([0, np.nan], dtype=np.float64)
        arr2 = arr.astype(object)

        dti1 = DatetimeIndex(arr, tz="CET")
        dti2 = DatetimeIndex(arr2, tz="CET")
        tm.assert_index_equal(dti1, dti2)

    @pytest.mark.parametrize("dtype", ["M8[us]", "M8[us, US/Pacific]"])
    def test_dti_constructor_with_dtype_object_int_matches_int_dtype(self, dtype):
        # Going through the object path should match the non-object path

        vals1 = np.arange(5, dtype="i8") * 1000
        vals1[0] = pd.NaT.value

        vals2 = vals1.astype(np.float64)
        vals2[0] = np.nan

        vals3 = vals1.astype(object)
        # change lib.infer_dtype(vals3) from "integer" so we go through
        #  array_to_datetime in _sequence_to_dt64
        vals3[0] = pd.NaT

        vals4 = vals2.astype(object)

        res1 = DatetimeIndex(vals1, dtype=dtype)
        res2 = DatetimeIndex(vals2, dtype=dtype)
        res3 = DatetimeIndex(vals3, dtype=dtype)
        res4 = DatetimeIndex(vals4, dtype=dtype)

        expected = DatetimeIndex(vals1.view("M8[us]"))
        if res1.tz is not None:
            expected = expected.tz_localize("UTC").tz_convert(res1.tz)
        tm.assert_index_equal(res1, expected)
        tm.assert_index_equal(res2, expected)
        tm.assert_index_equal(res3, expected)
        tm.assert_index_equal(res4, expected)


class TestTimeSeries:
    def test_dti_constructor_preserve_dti_freq(self):
        rng = date_range("1/1/2000", "1/2/2000", freq="5min")

        rng2 = DatetimeIndex(rng)
        assert rng.freq == rng2.freq

    def test_explicit_none_freq(self):
        # Explicitly passing freq=None is respected
        rng = date_range("1/1/2000", "1/2/2000", freq="5min")

        result = DatetimeIndex(rng, freq=None)
        assert result.freq is None

        result = DatetimeIndex(rng._data, freq=None)
        assert result.freq is None

    def test_dti_constructor_small_int(self, any_int_numpy_dtype):
        # see gh-13721
        exp = DatetimeIndex(
            [
                "1970-01-01 00:00:00.00000000",
                "1970-01-01 00:00:00.00000001",
                "1970-01-01 00:00:00.00000002",
            ]
        )

        arr = np.array([0, 10, 20], dtype=any_int_numpy_dtype)
        tm.assert_index_equal(DatetimeIndex(arr), exp)

    def test_ctor_str_intraday(self):
        rng = DatetimeIndex(["1-1-2000 00:00:01"])
        assert rng[0].second == 1

    def test_index_cast_datetime64_other_units(self):
        arr = np.arange(0, 100, 10, dtype=np.int64).view("M8[D]")
        idx = Index(arr)

        assert (idx.values == astype_overflowsafe(arr, dtype=np.dtype("M8[ns]"))).all()

    def test_constructor_int64_nocopy(self):
        # GH#1624
        arr = np.arange(1000, dtype=np.int64)
        index = DatetimeIndex(arr)

        arr[50:100] = -1
        assert (index.asi8[50:100] == -1).all()

        arr = np.arange(1000, dtype=np.int64)
        index = DatetimeIndex(arr, copy=True)

        arr[50:100] = -1
        assert (index.asi8[50:100] != -1).all()

    @pytest.mark.parametrize(
        "freq",
        ["ME", "QE", "YE", "D", "B", "bh", "min", "s", "ms", "us", "h", "ns", "C"],
    )
    def test_from_freq_recreate_from_data(self, freq):
        org = date_range(start="2001/02/01 09:00", freq=freq, periods=1)
        idx = DatetimeIndex(org, freq=freq)
        tm.assert_index_equal(idx, org)

        org = date_range(
            start="2001/02/01 09:00", freq=freq, tz="US/Pacific", periods=1
        )
        idx = DatetimeIndex(org, freq=freq, tz="US/Pacific")
        tm.assert_index_equal(idx, org)

    def test_datetimeindex_constructor_misc(self):
        arr = ["1/1/2005", "1/2/2005", "Jn 3, 2005", "2005-01-04"]
        msg = r"(\(')?Unknown datetime string format(:', 'Jn 3, 2005'\))?"
        with pytest.raises(ValueError, match=msg):
            DatetimeIndex(arr)

        arr = ["1/1/2005", "1/2/2005", "1/3/2005", "2005-01-04"]
        idx1 = DatetimeIndex(arr)

        arr = [datetime(2005, 1, 1), "1/2/2005", "1/3/2005", "2005-01-04"]
        idx2 = DatetimeIndex(arr)

        arr = [Timestamp(datetime(2005, 1, 1)), "1/2/2005", "1/3/2005", "2005-01-04"]
        idx3 = DatetimeIndex(arr)

        arr = np.array(["1/1/2005", "1/2/2005", "1/3/2005", "2005-01-04"], dtype="O")
        idx4 = DatetimeIndex(arr)

        idx5 = DatetimeIndex(["12/05/2007", "25/01/2008"], dayfirst=True)
        idx6 = DatetimeIndex(
            ["2007/05/12", "2008/01/25"], dayfirst=False, yearfirst=True
        )
        tm.assert_index_equal(idx5, idx6)

        for other in [idx2, idx3, idx4]:
            assert (idx1.values == other.values).all()

    def test_dti_constructor_object_dtype_dayfirst_yearfirst_with_tz(self):
        # GH#55813
        val = "5/10/16"

        dfirst = Timestamp(2016, 10, 5, tz="US/Pacific")
        yfirst = Timestamp(2005, 10, 16, tz="US/Pacific")

        result1 = DatetimeIndex([val], tz="US/Pacific", dayfirst=True)
        expected1 = DatetimeIndex([dfirst])
        tm.assert_index_equal(result1, expected1)

        result2 = DatetimeIndex([val], tz="US/Pacific", yearfirst=True)
        expected2 = DatetimeIndex([yfirst])
        tm.assert_index_equal(result2, expected2)
