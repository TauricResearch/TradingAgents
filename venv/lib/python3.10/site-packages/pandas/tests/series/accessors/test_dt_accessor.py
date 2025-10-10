import calendar
from datetime import (
    date,
    datetime,
    time,
)
import locale
import unicodedata

import numpy as np
import pytest
import pytz

from pandas._libs.tslibs.timezones import maybe_get_tz
from pandas.errors import SettingWithCopyError

from pandas.core.dtypes.common import (
    is_integer_dtype,
    is_list_like,
)

import pandas as pd
from pandas import (
    DataFrame,
    DatetimeIndex,
    Index,
    Period,
    PeriodIndex,
    Series,
    StringDtype,
    TimedeltaIndex,
    date_range,
    period_range,
    timedelta_range,
)
import pandas._testing as tm
from pandas.core.arrays import (
    DatetimeArray,
    PeriodArray,
    TimedeltaArray,
)

ok_for_period = PeriodArray._datetimelike_ops
ok_for_period_methods = ["strftime", "to_timestamp", "asfreq"]
ok_for_dt = DatetimeArray._datetimelike_ops
ok_for_dt_methods = [
    "to_period",
    "to_pydatetime",
    "tz_localize",
    "tz_convert",
    "normalize",
    "strftime",
    "round",
    "floor",
    "ceil",
    "day_name",
    "month_name",
    "isocalendar",
    "as_unit",
]
ok_for_td = TimedeltaArray._datetimelike_ops
ok_for_td_methods = [
    "components",
    "to_pytimedelta",
    "total_seconds",
    "round",
    "floor",
    "ceil",
    "as_unit",
]


def get_dir(ser):
    # check limited display api
    results = [r for r in ser.dt.__dir__() if not r.startswith("_")]
    return sorted(set(results))


class TestSeriesDatetimeValues:
    def _compare(self, ser, name):
        # GH 7207, 11128
        # test .dt namespace accessor

        def get_expected(ser, prop):
            result = getattr(Index(ser._values), prop)
            if isinstance(result, np.ndarray):
                if is_integer_dtype(result):
                    result = result.astype("int64")
            elif not is_list_like(result) or isinstance(result, DataFrame):
                return result
            return Series(result, index=ser.index, name=ser.name)

        left = getattr(ser.dt, name)
        right = get_expected(ser, name)
        if not (is_list_like(left) and is_list_like(right)):
            assert left == right
        elif isinstance(left, DataFrame):
            tm.assert_frame_equal(left, right)
        else:
            tm.assert_series_equal(left, right)

    @pytest.mark.parametrize("freq", ["D", "s", "ms"])
    def test_dt_namespace_accessor_datetime64(self, freq):
        # GH#7207, GH#11128
        # test .dt namespace accessor

        # datetimeindex
        dti = date_range("20130101", periods=5, freq=freq)
        ser = Series(dti, name="xxx")

        for prop in ok_for_dt:
            # we test freq below
            if prop != "freq":
                self._compare(ser, prop)

        for prop in ok_for_dt_methods:
            getattr(ser.dt, prop)

        msg = "The behavior of DatetimeProperties.to_pydatetime is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = ser.dt.to_pydatetime()
        assert isinstance(result, np.ndarray)
        assert result.dtype == object

        result = ser.dt.tz_localize("US/Eastern")
        exp_values = DatetimeIndex(ser.values).tz_localize("US/Eastern")
        expected = Series(exp_values, index=ser.index, name="xxx")
        tm.assert_series_equal(result, expected)

        tz_result = result.dt.tz
        assert str(tz_result) == "US/Eastern"
        freq_result = ser.dt.freq
        assert freq_result == DatetimeIndex(ser.values, freq="infer").freq

        # let's localize, then convert
        result = ser.dt.tz_localize("UTC").dt.tz_convert("US/Eastern")
        exp_values = (
            DatetimeIndex(ser.values).tz_localize("UTC").tz_convert("US/Eastern")
        )
        expected = Series(exp_values, index=ser.index, name="xxx")
        tm.assert_series_equal(result, expected)

    def test_dt_namespace_accessor_datetime64tz(self):
        # GH#7207, GH#11128
        # test .dt namespace accessor

        # datetimeindex with tz
        dti = date_range("20130101", periods=5, tz="US/Eastern")
        ser = Series(dti, name="xxx")
        for prop in ok_for_dt:
            # we test freq below
            if prop != "freq":
                self._compare(ser, prop)

        for prop in ok_for_dt_methods:
            getattr(ser.dt, prop)

        msg = "The behavior of DatetimeProperties.to_pydatetime is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = ser.dt.to_pydatetime()
        assert isinstance(result, np.ndarray)
        assert result.dtype == object

        result = ser.dt.tz_convert("CET")
        expected = Series(ser._values.tz_convert("CET"), index=ser.index, name="xxx")
        tm.assert_series_equal(result, expected)

        tz_result = result.dt.tz
        assert str(tz_result) == "CET"
        freq_result = ser.dt.freq
        assert freq_result == DatetimeIndex(ser.values, freq="infer").freq

    def test_dt_namespace_accessor_timedelta(self):
        # GH#7207, GH#11128
        # test .dt namespace accessor

        # timedelta index
        cases = [
            Series(
                timedelta_range("1 day", periods=5), index=list("abcde"), name="xxx"
            ),
            Series(timedelta_range("1 day 01:23:45", periods=5, freq="s"), name="xxx"),
            Series(
                timedelta_range("2 days 01:23:45.012345", periods=5, freq="ms"),
                name="xxx",
            ),
        ]
        for ser in cases:
            for prop in ok_for_td:
                # we test freq below
                if prop != "freq":
                    self._compare(ser, prop)

            for prop in ok_for_td_methods:
                getattr(ser.dt, prop)

            result = ser.dt.components
            assert isinstance(result, DataFrame)
            tm.assert_index_equal(result.index, ser.index)

            result = ser.dt.to_pytimedelta()
            assert isinstance(result, np.ndarray)
            assert result.dtype == object

            result = ser.dt.total_seconds()
            assert isinstance(result, Series)
            assert result.dtype == "float64"

            freq_result = ser.dt.freq
            assert freq_result == TimedeltaIndex(ser.values, freq="infer").freq

    def test_dt_namespace_accessor_period(self):
        # GH#7207, GH#11128
        # test .dt namespace accessor

        # periodindex
        pi = period_range("20130101", periods=5, freq="D")
        ser = Series(pi, name="xxx")

        for prop in ok_for_period:
            # we test freq below
            if prop != "freq":
                self._compare(ser, prop)

        for prop in ok_for_period_methods:
            getattr(ser.dt, prop)

        freq_result = ser.dt.freq
        assert freq_result == PeriodIndex(ser.values).freq

    def test_dt_namespace_accessor_index_and_values(self):
        # both
        index = date_range("20130101", periods=3, freq="D")
        dti = date_range("20140204", periods=3, freq="s")
        ser = Series(dti, index=index, name="xxx")
        exp = Series(
            np.array([2014, 2014, 2014], dtype="int32"), index=index, name="xxx"
        )
        tm.assert_series_equal(ser.dt.year, exp)

        exp = Series(np.array([2, 2, 2], dtype="int32"), index=index, name="xxx")
        tm.assert_series_equal(ser.dt.month, exp)

        exp = Series(np.array([0, 1, 2], dtype="int32"), index=index, name="xxx")
        tm.assert_series_equal(ser.dt.second, exp)

        exp = Series([ser.iloc[0]] * 3, index=index, name="xxx")
        tm.assert_series_equal(ser.dt.normalize(), exp)

    def test_dt_accessor_limited_display_api(self):
        # tznaive
        ser = Series(date_range("20130101", periods=5, freq="D"), name="xxx")
        results = get_dir(ser)
        tm.assert_almost_equal(results, sorted(set(ok_for_dt + ok_for_dt_methods)))

        # tzaware
        ser = Series(date_range("2015-01-01", "2016-01-01", freq="min"), name="xxx")
        ser = ser.dt.tz_localize("UTC").dt.tz_convert("America/Chicago")
        results = get_dir(ser)
        tm.assert_almost_equal(results, sorted(set(ok_for_dt + ok_for_dt_methods)))

        # Period
        idx = period_range("20130101", periods=5, freq="D", name="xxx").astype(object)
        with tm.assert_produces_warning(FutureWarning, match="Dtype inference"):
            ser = Series(idx)
        results = get_dir(ser)
        tm.assert_almost_equal(
            results, sorted(set(ok_for_period + ok_for_period_methods))
        )

    def test_dt_accessor_ambiguous_freq_conversions(self):
        # GH#11295
        # ambiguous time error on the conversions
        ser = Series(date_range("2015-01-01", "2016-01-01", freq="min"), name="xxx")
        ser = ser.dt.tz_localize("UTC").dt.tz_convert("America/Chicago")

        exp_values = date_range(
            "2015-01-01", "2016-01-01", freq="min", tz="UTC"
        ).tz_convert("America/Chicago")
        # freq not preserved by tz_localize above
        exp_values = exp_values._with_freq(None)
        expected = Series(exp_values, name="xxx")
        tm.assert_series_equal(ser, expected)

    def test_dt_accessor_not_writeable(self, using_copy_on_write, warn_copy_on_write):
        # no setting allowed
        ser = Series(date_range("20130101", periods=5, freq="D"), name="xxx")
        with pytest.raises(ValueError, match="modifications"):
            ser.dt.hour = 5

        # trying to set a copy
        msg = "modifications to a property of a datetimelike.+not supported"
        with pd.option_context("chained_assignment", "raise"):
            if using_copy_on_write:
                with tm.raises_chained_assignment_error():
                    ser.dt.hour[0] = 5
            elif warn_copy_on_write:
                with tm.assert_produces_warning(
                    FutureWarning, match="ChainedAssignmentError"
                ):
                    ser.dt.hour[0] = 5
            else:
                with pytest.raises(SettingWithCopyError, match=msg):
                    ser.dt.hour[0] = 5

    @pytest.mark.parametrize(
        "method, dates",
        [
            ["round", ["2012-01-02", "2012-01-02", "2012-01-01"]],
            ["floor", ["2012-01-01", "2012-01-01", "2012-01-01"]],
            ["ceil", ["2012-01-02", "2012-01-02", "2012-01-02"]],
        ],
    )
    def test_dt_round(self, method, dates):
        # round
        ser = Series(
            pd.to_datetime(
                ["2012-01-01 13:00:00", "2012-01-01 12:01:00", "2012-01-01 08:00:00"]
            ),
            name="xxx",
        )
        result = getattr(ser.dt, method)("D")
        expected = Series(pd.to_datetime(dates), name="xxx")
        tm.assert_series_equal(result, expected)

    def test_dt_round_tz(self):
        ser = Series(
            pd.to_datetime(
                ["2012-01-01 13:00:00", "2012-01-01 12:01:00", "2012-01-01 08:00:00"]
            ),
            name="xxx",
        )
        result = ser.dt.tz_localize("UTC").dt.tz_convert("US/Eastern").dt.round("D")

        exp_values = pd.to_datetime(
            ["2012-01-01", "2012-01-01", "2012-01-01"]
        ).tz_localize("US/Eastern")
        expected = Series(exp_values, name="xxx")
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("method", ["ceil", "round", "floor"])
    def test_dt_round_tz_ambiguous(self, method):
        # GH 18946 round near "fall back" DST
        df1 = DataFrame(
            [
                pd.to_datetime("2017-10-29 02:00:00+02:00", utc=True),
                pd.to_datetime("2017-10-29 02:00:00+01:00", utc=True),
                pd.to_datetime("2017-10-29 03:00:00+01:00", utc=True),
            ],
            columns=["date"],
        )
        df1["date"] = df1["date"].dt.tz_convert("Europe/Madrid")
        # infer
        result = getattr(df1.date.dt, method)("h", ambiguous="infer")
        expected = df1["date"]
        tm.assert_series_equal(result, expected)

        # bool-array
        result = getattr(df1.date.dt, method)("h", ambiguous=[True, False, False])
        tm.assert_series_equal(result, expected)

        # NaT
        result = getattr(df1.date.dt, method)("h", ambiguous="NaT")
        expected = df1["date"].copy()
        expected.iloc[0:2] = pd.NaT
        tm.assert_series_equal(result, expected)

        # raise
        with tm.external_error_raised(pytz.AmbiguousTimeError):
            getattr(df1.date.dt, method)("h", ambiguous="raise")

    @pytest.mark.parametrize(
        "method, ts_str, freq",
        [
            ["ceil", "2018-03-11 01:59:00-0600", "5min"],
            ["round", "2018-03-11 01:59:00-0600", "5min"],
            ["floor", "2018-03-11 03:01:00-0500", "2h"],
        ],
    )
    def test_dt_round_tz_nonexistent(self, method, ts_str, freq):
        # GH 23324 round near "spring forward" DST
        ser = Series([pd.Timestamp(ts_str, tz="America/Chicago")])
        result = getattr(ser.dt, method)(freq, nonexistent="shift_forward")
        expected = Series([pd.Timestamp("2018-03-11 03:00:00", tz="America/Chicago")])
        tm.assert_series_equal(result, expected)

        result = getattr(ser.dt, method)(freq, nonexistent="NaT")
        expected = Series([pd.NaT]).dt.tz_localize(result.dt.tz)
        tm.assert_series_equal(result, expected)

        with pytest.raises(pytz.NonExistentTimeError, match="2018-03-11 02:00:00"):
            getattr(ser.dt, method)(freq, nonexistent="raise")

    @pytest.mark.parametrize("freq", ["ns", "us", "1000us"])
    def test_dt_round_nonnano_higher_resolution_no_op(self, freq):
        # GH 52761
        ser = Series(
            ["2020-05-31 08:00:00", "2000-12-31 04:00:05", "1800-03-14 07:30:20"],
            dtype="datetime64[ms]",
        )
        expected = ser.copy()
        result = ser.dt.round(freq)
        tm.assert_series_equal(result, expected)

        assert not np.shares_memory(ser.array._ndarray, result.array._ndarray)

    def test_dt_namespace_accessor_categorical(self):
        # GH 19468
        dti = DatetimeIndex(["20171111", "20181212"]).repeat(2)
        ser = Series(pd.Categorical(dti), name="foo")
        result = ser.dt.year
        expected = Series([2017, 2017, 2018, 2018], dtype="int32", name="foo")
        tm.assert_series_equal(result, expected)

    def test_dt_tz_localize_categorical(self, tz_aware_fixture):
        # GH 27952
        tz = tz_aware_fixture
        datetimes = Series(
            ["2019-01-01", "2019-01-01", "2019-01-02"], dtype="datetime64[ns]"
        )
        categorical = datetimes.astype("category")
        result = categorical.dt.tz_localize(tz)
        expected = datetimes.dt.tz_localize(tz)
        tm.assert_series_equal(result, expected)

    def test_dt_tz_convert_categorical(self, tz_aware_fixture):
        # GH 27952
        tz = tz_aware_fixture
        datetimes = Series(
            ["2019-01-01", "2019-01-01", "2019-01-02"], dtype="datetime64[ns, MET]"
        )
        categorical = datetimes.astype("category")
        result = categorical.dt.tz_convert(tz)
        expected = datetimes.dt.tz_convert(tz)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("accessor", ["year", "month", "day"])
    def test_dt_other_accessors_categorical(self, accessor):
        # GH 27952
        datetimes = Series(
            ["2018-01-01", "2018-01-01", "2019-01-02"], dtype="datetime64[ns]"
        )
        categorical = datetimes.astype("category")
        result = getattr(categorical.dt, accessor)
        expected = getattr(datetimes.dt, accessor)
        tm.assert_series_equal(result, expected)

    def test_dt_accessor_no_new_attributes(self):
        # https://github.com/pandas-dev/pandas/issues/10673
        ser = Series(date_range("20130101", periods=5, freq="D"))
        with pytest.raises(AttributeError, match="You cannot add any new attribute"):
            ser.dt.xlabel = "a"

    # error: Unsupported operand types for + ("List[None]" and "List[str]")
    @pytest.mark.parametrize(
        "time_locale", [None] + tm.get_locales()  # type: ignore[operator]
    )
    def test_dt_accessor_datetime_name_accessors(self, time_locale):
        # Test Monday -> Sunday and January -> December, in that sequence
        if time_locale is None:
            # If the time_locale is None, day-name and month_name should
            # return the english attributes
            expected_days = [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
            expected_months = [
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ]
        else:
            with tm.set_locale(time_locale, locale.LC_TIME):
                expected_days = calendar.day_name[:]
                expected_months = calendar.month_name[1:]

        ser = Series(date_range(freq="D", start=datetime(1998, 1, 1), periods=365))
        english_days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        for day, name, eng_name in zip(range(4, 11), expected_days, english_days):
            name = name.capitalize()
            assert ser.dt.day_name(locale=time_locale)[day] == name
            assert ser.dt.day_name(locale=None)[day] == eng_name
        ser = pd.concat([ser, Series([pd.NaT])])
        assert np.isnan(ser.dt.day_name(locale=time_locale).iloc[-1])

        ser = Series(date_range(freq="ME", start="2012", end="2013"))
        result = ser.dt.month_name(locale=time_locale)
        expected = Series([month.capitalize() for month in expected_months])

        # work around https://github.com/pandas-dev/pandas/issues/22342
        result = result.str.normalize("NFD")
        expected = expected.str.normalize("NFD")

        tm.assert_series_equal(result, expected)

        for s_date, expected in zip(ser, expected_months):
            result = s_date.month_name(locale=time_locale)
            expected = expected.capitalize()

            result = unicodedata.normalize("NFD", result)
            expected = unicodedata.normalize("NFD", expected)

            assert result == expected

        ser = pd.concat([ser, Series([pd.NaT])])
        assert np.isnan(ser.dt.month_name(locale=time_locale).iloc[-1])

    def test_strftime(self):
        # GH 10086
        ser = Series(date_range("20130101", periods=5))
        result = ser.dt.strftime("%Y/%m/%d")
        expected = Series(
            ["2013/01/01", "2013/01/02", "2013/01/03", "2013/01/04", "2013/01/05"]
        )
        tm.assert_series_equal(result, expected)

        ser = Series(date_range("2015-02-03 11:22:33.4567", periods=5))
        result = ser.dt.strftime("%Y/%m/%d %H-%M-%S")
        expected = Series(
            [
                "2015/02/03 11-22-33",
                "2015/02/04 11-22-33",
                "2015/02/05 11-22-33",
                "2015/02/06 11-22-33",
                "2015/02/07 11-22-33",
            ]
        )
        tm.assert_series_equal(result, expected)

        ser = Series(period_range("20130101", periods=5))
        result = ser.dt.strftime("%Y/%m/%d")
        expected = Series(
            ["2013/01/01", "2013/01/02", "2013/01/03", "2013/01/04", "2013/01/05"]
        )
        tm.assert_series_equal(result, expected)

        ser = Series(period_range("2015-02-03 11:22:33.4567", periods=5, freq="s"))
        result = ser.dt.strftime("%Y/%m/%d %H-%M-%S")
        expected = Series(
            [
                "2015/02/03 11-22-33",
                "2015/02/03 11-22-34",
                "2015/02/03 11-22-35",
                "2015/02/03 11-22-36",
                "2015/02/03 11-22-37",
            ]
        )
        tm.assert_series_equal(result, expected)

    def test_strftime_dt64_days(self):
        ser = Series(date_range("20130101", periods=5))
        ser.iloc[0] = pd.NaT
        result = ser.dt.strftime("%Y/%m/%d")
        expected = Series(
            [np.nan, "2013/01/02", "2013/01/03", "2013/01/04", "2013/01/05"]
        )
        tm.assert_series_equal(result, expected)

        datetime_index = date_range("20150301", periods=5)
        result = datetime_index.strftime("%Y/%m/%d")

        expected = Index(
            ["2015/03/01", "2015/03/02", "2015/03/03", "2015/03/04", "2015/03/05"],
        )
        # dtype may be S10 or U10 depending on python version
        tm.assert_index_equal(result, expected)

    def test_strftime_period_days(self, using_infer_string):
        period_index = period_range("20150301", periods=5)
        result = period_index.strftime("%Y/%m/%d")
        expected = Index(
            ["2015/03/01", "2015/03/02", "2015/03/03", "2015/03/04", "2015/03/05"],
            dtype="=U10",
        )
        if using_infer_string:
            expected = expected.astype(StringDtype(na_value=np.nan))
        tm.assert_index_equal(result, expected)

    def test_strftime_dt64_microsecond_resolution(self):
        ser = Series([datetime(2013, 1, 1, 2, 32, 59), datetime(2013, 1, 2, 14, 32, 1)])
        result = ser.dt.strftime("%Y-%m-%d %H:%M:%S")
        expected = Series(["2013-01-01 02:32:59", "2013-01-02 14:32:01"])
        tm.assert_series_equal(result, expected)

    def test_strftime_period_hours(self):
        ser = Series(period_range("20130101", periods=4, freq="h"))
        result = ser.dt.strftime("%Y/%m/%d %H:%M:%S")
        expected = Series(
            [
                "2013/01/01 00:00:00",
                "2013/01/01 01:00:00",
                "2013/01/01 02:00:00",
                "2013/01/01 03:00:00",
            ]
        )
        tm.assert_series_equal(result, expected)

    def test_strftime_period_minutes(self):
        ser = Series(period_range("20130101", periods=4, freq="ms"))
        result = ser.dt.strftime("%Y/%m/%d %H:%M:%S.%l")
        expected = Series(
            [
                "2013/01/01 00:00:00.000",
                "2013/01/01 00:00:00.001",
                "2013/01/01 00:00:00.002",
                "2013/01/01 00:00:00.003",
            ]
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "data",
        [
            DatetimeIndex(["2019-01-01", pd.NaT]),
            PeriodIndex(["2019-01-01", pd.NaT], dtype="period[D]"),
        ],
    )
    def test_strftime_nat(self, data):
        # GH 29578
        ser = Series(data)
        result = ser.dt.strftime("%Y-%m-%d")
        expected = Series(["2019-01-01", np.nan])
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "data", [DatetimeIndex([pd.NaT]), PeriodIndex([pd.NaT], dtype="period[D]")]
    )
    def test_strftime_all_nat(self, data):
        # https://github.com/pandas-dev/pandas/issues/45858
        ser = Series(data)
        with tm.assert_produces_warning(None):
            result = ser.dt.strftime("%Y-%m-%d")
        expected = Series([np.nan], dtype="str")
        tm.assert_series_equal(result, expected)

    def test_valid_dt_with_missing_values(self):
        # GH 8689
        ser = Series(date_range("20130101", periods=5, freq="D"))
        ser.iloc[2] = pd.NaT

        for attr in ["microsecond", "nanosecond", "second", "minute", "hour", "day"]:
            expected = getattr(ser.dt, attr).copy()
            expected.iloc[2] = np.nan
            result = getattr(ser.dt, attr)
            tm.assert_series_equal(result, expected)

        result = ser.dt.date
        expected = Series(
            [
                date(2013, 1, 1),
                date(2013, 1, 2),
                pd.NaT,
                date(2013, 1, 4),
                date(2013, 1, 5),
            ],
            dtype="object",
        )
        tm.assert_series_equal(result, expected)

        result = ser.dt.time
        expected = Series([time(0), time(0), pd.NaT, time(0), time(0)], dtype="object")
        tm.assert_series_equal(result, expected)

    def test_dt_accessor_api(self):
        # GH 9322
        from pandas.core.indexes.accessors import (
            CombinedDatetimelikeProperties,
            DatetimeProperties,
        )

        assert Series.dt is CombinedDatetimelikeProperties

        ser = Series(date_range("2000-01-01", periods=3))
        assert isinstance(ser.dt, DatetimeProperties)

    @pytest.mark.parametrize(
        "ser",
        [
            Series(np.arange(5)),
            Series(list("abcde")),
            Series(np.random.default_rng(2).standard_normal(5)),
        ],
    )
    def test_dt_accessor_invalid(self, ser):
        # GH#9322 check that series with incorrect dtypes don't have attr
        with pytest.raises(AttributeError, match="only use .dt accessor"):
            ser.dt
        assert not hasattr(ser, "dt")

    def test_dt_accessor_updates_on_inplace(self):
        ser = Series(date_range("2018-01-01", periods=10))
        ser[2] = None
        return_value = ser.fillna(pd.Timestamp("2018-01-01"), inplace=True)
        assert return_value is None
        result = ser.dt.date
        assert result[0] == result[2]

    def test_date_tz(self):
        # GH11757
        rng = DatetimeIndex(
            ["2014-04-04 23:56", "2014-07-18 21:24", "2015-11-22 22:14"],
            tz="US/Eastern",
        )
        ser = Series(rng)
        expected = Series([date(2014, 4, 4), date(2014, 7, 18), date(2015, 11, 22)])
        tm.assert_series_equal(ser.dt.date, expected)
        tm.assert_series_equal(ser.apply(lambda x: x.date()), expected)

    def test_dt_timetz_accessor(self, tz_naive_fixture):
        # GH21358
        tz = maybe_get_tz(tz_naive_fixture)

        dtindex = DatetimeIndex(
            ["2014-04-04 23:56", "2014-07-18 21:24", "2015-11-22 22:14"], tz=tz
        )
        ser = Series(dtindex)
        expected = Series(
            [time(23, 56, tzinfo=tz), time(21, 24, tzinfo=tz), time(22, 14, tzinfo=tz)]
        )
        result = ser.dt.timetz
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "input_series, expected_output",
        [
            [["2020-01-01"], [[2020, 1, 3]]],
            [[pd.NaT], [[np.nan, np.nan, np.nan]]],
            [["2019-12-31", "2019-12-29"], [[2020, 1, 2], [2019, 52, 7]]],
            [["2010-01-01", pd.NaT], [[2009, 53, 5], [np.nan, np.nan, np.nan]]],
            # see GH#36032
            [["2016-01-08", "2016-01-04"], [[2016, 1, 5], [2016, 1, 1]]],
            [["2016-01-07", "2016-01-01"], [[2016, 1, 4], [2015, 53, 5]]],
        ],
    )
    def test_isocalendar(self, input_series, expected_output):
        result = pd.to_datetime(Series(input_series)).dt.isocalendar()
        expected_frame = DataFrame(
            expected_output, columns=["year", "week", "day"], dtype="UInt32"
        )
        tm.assert_frame_equal(result, expected_frame)

    def test_hour_index(self):
        dt_series = Series(
            date_range(start="2021-01-01", periods=5, freq="h"),
            index=[2, 6, 7, 8, 11],
            dtype="category",
        )
        result = dt_series.dt.hour
        expected = Series(
            [0, 1, 2, 3, 4],
            dtype="int32",
            index=[2, 6, 7, 8, 11],
        )
        tm.assert_series_equal(result, expected)


class TestSeriesPeriodValuesDtAccessor:
    @pytest.mark.parametrize(
        "input_vals",
        [
            [Period("2016-01", freq="M"), Period("2016-02", freq="M")],
            [Period("2016-01-01", freq="D"), Period("2016-01-02", freq="D")],
            [
                Period("2016-01-01 00:00:00", freq="h"),
                Period("2016-01-01 01:00:00", freq="h"),
            ],
            [
                Period("2016-01-01 00:00:00", freq="M"),
                Period("2016-01-01 00:01:00", freq="M"),
            ],
            [
                Period("2016-01-01 00:00:00", freq="s"),
                Period("2016-01-01 00:00:01", freq="s"),
            ],
        ],
    )
    def test_end_time_timevalues(self, input_vals):
        # GH#17157
        # Check that the time part of the Period is adjusted by end_time
        # when using the dt accessor on a Series
        input_vals = PeriodArray._from_sequence(np.asarray(input_vals))

        ser = Series(input_vals)
        result = ser.dt.end_time
        expected = ser.apply(lambda x: x.end_time)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("input_vals", [("2001"), ("NaT")])
    def test_to_period(self, input_vals):
        # GH#21205
        expected = Series([input_vals], dtype="Period[D]")
        result = Series([input_vals], dtype="datetime64[ns]").dt.to_period("D")
        tm.assert_series_equal(result, expected)


def test_normalize_pre_epoch_dates():
    # GH: 36294
    ser = pd.to_datetime(Series(["1969-01-01 09:00:00", "2016-01-01 09:00:00"]))
    result = ser.dt.normalize()
    expected = pd.to_datetime(Series(["1969-01-01", "2016-01-01"]))
    tm.assert_series_equal(result, expected)


def test_day_attribute_non_nano_beyond_int32():
    # GH 52386
    data = np.array(
        [
            136457654736252,
            134736784364431,
            245345345545332,
            223432411,
            2343241,
            3634548734,
            23234,
        ],
        dtype="timedelta64[s]",
    )
    ser = Series(data)
    result = ser.dt.days
    expected = Series([1579371003, 1559453522, 2839645203, 2586, 27, 42066, 0])
    tm.assert_series_equal(result, expected)
