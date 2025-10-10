from datetime import datetime

import dateutil
import numpy as np
import pytest
import pytz

import pandas as pd
from pandas import (
    DatetimeIndex,
    Index,
    NaT,
    PeriodIndex,
    Timestamp,
    date_range,
)
import pandas._testing as tm


class TestDatetimeIndex:
    @pytest.mark.parametrize("tzstr", ["US/Eastern", "dateutil/US/Eastern"])
    def test_dti_astype_asobject_around_dst_transition(self, tzstr):
        # GH#1345

        # dates around a dst transition
        rng = date_range("2/13/2010", "5/6/2010", tz=tzstr)

        objs = rng.astype(object)
        for i, x in enumerate(objs):
            exval = rng[i]
            assert x == exval
            assert x.tzinfo == exval.tzinfo

        objs = rng.astype(object)
        for i, x in enumerate(objs):
            exval = rng[i]
            assert x == exval
            assert x.tzinfo == exval.tzinfo

    def test_astype(self):
        # GH 13149, GH 13209
        idx = DatetimeIndex(
            ["2016-05-16", "NaT", NaT, np.nan], dtype="M8[ns]", name="idx"
        )

        result = idx.astype(object)
        expected = Index(
            [Timestamp("2016-05-16")] + [NaT] * 3, dtype=object, name="idx"
        )
        tm.assert_index_equal(result, expected)

        result = idx.astype(np.int64)
        expected = Index(
            [1463356800000000000] + [-9223372036854775808] * 3,
            dtype=np.int64,
            name="idx",
        )
        tm.assert_index_equal(result, expected)

    def test_astype2(self):
        rng = date_range("1/1/2000", periods=10, name="idx")
        result = rng.astype("i8")
        tm.assert_index_equal(result, Index(rng.asi8, name="idx"))
        tm.assert_numpy_array_equal(result.values, rng.asi8)

    def test_astype_uint(self):
        arr = date_range("2000", periods=2, name="idx")

        with pytest.raises(TypeError, match=r"Do obj.astype\('int64'\)"):
            arr.astype("uint64")
        with pytest.raises(TypeError, match=r"Do obj.astype\('int64'\)"):
            arr.astype("uint32")

    def test_astype_with_tz(self):
        # with tz
        rng = date_range("1/1/2000", periods=10, tz="US/Eastern")
        msg = "Cannot use .astype to convert from timezone-aware"
        with pytest.raises(TypeError, match=msg):
            # deprecated
            rng.astype("datetime64[ns]")
        with pytest.raises(TypeError, match=msg):
            # check DatetimeArray while we're here deprecated
            rng._data.astype("datetime64[ns]")

    def test_astype_tzaware_to_tzaware(self):
        # GH 18951: tz-aware to tz-aware
        idx = date_range("20170101", periods=4, tz="US/Pacific")
        result = idx.astype("datetime64[ns, US/Eastern]")
        expected = date_range("20170101 03:00:00", periods=4, tz="US/Eastern")
        tm.assert_index_equal(result, expected)
        assert result.freq == expected.freq

    def test_astype_tznaive_to_tzaware(self):
        # GH 18951: tz-naive to tz-aware
        idx = date_range("20170101", periods=4)
        idx = idx._with_freq(None)  # tz_localize does not preserve freq
        msg = "Cannot use .astype to convert from timezone-naive"
        with pytest.raises(TypeError, match=msg):
            # dt64->dt64tz deprecated
            idx.astype("datetime64[ns, US/Eastern]")
        with pytest.raises(TypeError, match=msg):
            # dt64->dt64tz deprecated
            idx._data.astype("datetime64[ns, US/Eastern]")

    def test_astype_str_nat(self, using_infer_string):
        # GH 13149, GH 13209
        # verify that we are returning NaT as a string (and not unicode)

        idx = DatetimeIndex(["2016-05-16", "NaT", NaT, np.nan])
        result = idx.astype(str)
        if using_infer_string:
            expected = Index(["2016-05-16", None, None, None], dtype="str")
        else:
            expected = Index(["2016-05-16", "NaT", "NaT", "NaT"], dtype=object)
        tm.assert_index_equal(result, expected)

    def test_astype_str(self):
        # test astype string - #10442
        dti = date_range("2012-01-01", periods=4, name="test_name")
        result = dti.astype(str)
        expected = Index(
            ["2012-01-01", "2012-01-02", "2012-01-03", "2012-01-04"],
            name="test_name",
            dtype="str",
        )
        tm.assert_index_equal(result, expected)

    def test_astype_str_tz_and_name(self):
        # test astype string with tz and name
        dti = date_range("2012-01-01", periods=3, name="test_name", tz="US/Eastern")
        result = dti.astype(str)
        expected = Index(
            [
                "2012-01-01 00:00:00-05:00",
                "2012-01-02 00:00:00-05:00",
                "2012-01-03 00:00:00-05:00",
            ],
            name="test_name",
            dtype="str",
        )
        tm.assert_index_equal(result, expected)

    def test_astype_str_freq_and_name(self):
        # test astype string with freqH and name
        dti = date_range("1/1/2011", periods=3, freq="h", name="test_name")
        result = dti.astype(str)
        expected = Index(
            ["2011-01-01 00:00:00", "2011-01-01 01:00:00", "2011-01-01 02:00:00"],
            name="test_name",
            dtype="str",
        )
        tm.assert_index_equal(result, expected)

    def test_astype_str_freq_and_tz(self):
        # test astype string with freqH and timezone
        dti = date_range(
            "3/6/2012 00:00", periods=2, freq="h", tz="Europe/London", name="test_name"
        )
        result = dti.astype(str)
        expected = Index(
            ["2012-03-06 00:00:00+00:00", "2012-03-06 01:00:00+00:00"],
            dtype="str",
            name="test_name",
        )
        tm.assert_index_equal(result, expected)

    def test_astype_datetime64(self):
        # GH 13149, GH 13209
        idx = DatetimeIndex(
            ["2016-05-16", "NaT", NaT, np.nan], dtype="M8[ns]", name="idx"
        )

        result = idx.astype("datetime64[ns]")
        tm.assert_index_equal(result, idx)
        assert result is not idx

        result = idx.astype("datetime64[ns]", copy=False)
        tm.assert_index_equal(result, idx)
        assert result is idx

        idx_tz = DatetimeIndex(["2016-05-16", "NaT", NaT, np.nan], tz="EST", name="idx")
        msg = "Cannot use .astype to convert from timezone-aware"
        with pytest.raises(TypeError, match=msg):
            # dt64tz->dt64 deprecated
            result = idx_tz.astype("datetime64[ns]")

    def test_astype_object(self):
        rng = date_range("1/1/2000", periods=20)

        casted = rng.astype("O")
        exp_values = list(rng)

        tm.assert_index_equal(casted, Index(exp_values, dtype=np.object_))
        assert casted.tolist() == exp_values

    @pytest.mark.parametrize("tz", [None, "Asia/Tokyo"])
    def test_astype_object_tz(self, tz):
        idx = date_range(start="2013-01-01", periods=4, freq="ME", name="idx", tz=tz)
        expected_list = [
            Timestamp("2013-01-31", tz=tz),
            Timestamp("2013-02-28", tz=tz),
            Timestamp("2013-03-31", tz=tz),
            Timestamp("2013-04-30", tz=tz),
        ]
        expected = Index(expected_list, dtype=object, name="idx")
        result = idx.astype(object)
        tm.assert_index_equal(result, expected)
        assert idx.tolist() == expected_list

    def test_astype_object_with_nat(self):
        idx = DatetimeIndex(
            [datetime(2013, 1, 1), datetime(2013, 1, 2), NaT, datetime(2013, 1, 4)],
            name="idx",
        )
        expected_list = [
            Timestamp("2013-01-01"),
            Timestamp("2013-01-02"),
            NaT,
            Timestamp("2013-01-04"),
        ]
        expected = Index(expected_list, dtype=object, name="idx")
        result = idx.astype(object)
        tm.assert_index_equal(result, expected)
        assert idx.tolist() == expected_list

    @pytest.mark.parametrize(
        "dtype",
        [float, "timedelta64", "timedelta64[ns]", "datetime64", "datetime64[D]"],
    )
    def test_astype_raises(self, dtype):
        # GH 13149, GH 13209
        idx = DatetimeIndex(["2016-05-16", "NaT", NaT, np.nan])
        msg = "Cannot cast DatetimeIndex to dtype"
        if dtype == "datetime64":
            msg = "Casting to unit-less dtype 'datetime64' is not supported"
        with pytest.raises(TypeError, match=msg):
            idx.astype(dtype)

    def test_index_convert_to_datetime_array(self):
        def _check_rng(rng):
            converted = rng.to_pydatetime()
            assert isinstance(converted, np.ndarray)
            for x, stamp in zip(converted, rng):
                assert isinstance(x, datetime)
                assert x == stamp.to_pydatetime()
                assert x.tzinfo == stamp.tzinfo

        rng = date_range("20090415", "20090519")
        rng_eastern = date_range("20090415", "20090519", tz="US/Eastern")
        rng_utc = date_range("20090415", "20090519", tz="utc")

        _check_rng(rng)
        _check_rng(rng_eastern)
        _check_rng(rng_utc)

    def test_index_convert_to_datetime_array_explicit_pytz(self):
        def _check_rng(rng):
            converted = rng.to_pydatetime()
            assert isinstance(converted, np.ndarray)
            for x, stamp in zip(converted, rng):
                assert isinstance(x, datetime)
                assert x == stamp.to_pydatetime()
                assert x.tzinfo == stamp.tzinfo

        rng = date_range("20090415", "20090519")
        rng_eastern = date_range("20090415", "20090519", tz=pytz.timezone("US/Eastern"))
        rng_utc = date_range("20090415", "20090519", tz=pytz.utc)

        _check_rng(rng)
        _check_rng(rng_eastern)
        _check_rng(rng_utc)

    def test_index_convert_to_datetime_array_dateutil(self):
        def _check_rng(rng):
            converted = rng.to_pydatetime()
            assert isinstance(converted, np.ndarray)
            for x, stamp in zip(converted, rng):
                assert isinstance(x, datetime)
                assert x == stamp.to_pydatetime()
                assert x.tzinfo == stamp.tzinfo

        rng = date_range("20090415", "20090519")
        rng_eastern = date_range("20090415", "20090519", tz="dateutil/US/Eastern")
        rng_utc = date_range("20090415", "20090519", tz=dateutil.tz.tzutc())

        _check_rng(rng)
        _check_rng(rng_eastern)
        _check_rng(rng_utc)

    @pytest.mark.parametrize(
        "tz, dtype",
        [["US/Pacific", "datetime64[ns, US/Pacific]"], [None, "datetime64[ns]"]],
    )
    def test_integer_index_astype_datetime(self, tz, dtype):
        # GH 20997, 20964, 24559
        val = [Timestamp("2018-01-01", tz=tz).as_unit("ns")._value]
        result = Index(val, name="idx").astype(dtype)
        expected = DatetimeIndex(["2018-01-01"], tz=tz, name="idx").as_unit("ns")
        tm.assert_index_equal(result, expected)

    def test_dti_astype_period(self):
        idx = DatetimeIndex([NaT, "2011-01-01", "2011-02-01"], name="idx")

        res = idx.astype("period[M]")
        exp = PeriodIndex(["NaT", "2011-01", "2011-02"], freq="M", name="idx")
        tm.assert_index_equal(res, exp)

        res = idx.astype("period[3M]")
        exp = PeriodIndex(["NaT", "2011-01", "2011-02"], freq="3M", name="idx")
        tm.assert_index_equal(res, exp)


class TestAstype:
    @pytest.mark.parametrize("tz", [None, "US/Central"])
    def test_astype_category(self, tz):
        obj = date_range("2000", periods=2, tz=tz, name="idx")
        result = obj.astype("category")
        dti = DatetimeIndex(["2000-01-01", "2000-01-02"], tz=tz).as_unit("ns")
        expected = pd.CategoricalIndex(
            dti,
            name="idx",
        )
        tm.assert_index_equal(result, expected)

        result = obj._data.astype("category")
        expected = expected.values
        tm.assert_categorical_equal(result, expected)

    @pytest.mark.parametrize("tz", [None, "US/Central"])
    def test_astype_array_fallback(self, tz):
        obj = date_range("2000", periods=2, tz=tz, name="idx")
        result = obj.astype(bool)
        expected = Index(np.array([True, True]), name="idx")
        tm.assert_index_equal(result, expected)

        result = obj._data.astype(bool)
        expected = np.array([True, True])
        tm.assert_numpy_array_equal(result, expected)
