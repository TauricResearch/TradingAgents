""" test to_datetime """

import calendar
from collections import deque
from datetime import (
    date,
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
import locale

from dateutil.parser import parse
from dateutil.tz.tz import tzoffset
import numpy as np
import pytest
import pytz

from pandas._libs import tslib
from pandas._libs.tslibs import (
    iNaT,
    parsing,
)
from pandas.compat import PY314
from pandas.errors import (
    OutOfBoundsDatetime,
    OutOfBoundsTimedelta,
)
import pandas.util._test_decorators as td

from pandas.core.dtypes.common import is_datetime64_ns_dtype

import pandas as pd
from pandas import (
    DataFrame,
    DatetimeIndex,
    Index,
    NaT,
    Series,
    Timestamp,
    date_range,
    isna,
    to_datetime,
)
import pandas._testing as tm
from pandas.core.arrays import DatetimeArray
from pandas.core.tools import datetimes as tools
from pandas.core.tools.datetimes import start_caching_at

PARSING_ERR_MSG = (
    r"You might want to try:\n"
    r"    - passing `format` if your strings have a consistent format;\n"
    r"    - passing `format=\'ISO8601\'` if your strings are all ISO8601 "
    r"but not necessarily in exactly the same format;\n"
    r"    - passing `format=\'mixed\'`, and the format will be inferred "
    r"for each element individually. You might want to use `dayfirst` "
    r"alongside this."
)

if PY314:
    NOT_99 = ", not 99"
    DAY_IS_OUT_OF_RANGE = (
        r"day \d{1,2} must be in range 1\.\.\d{1,2} for month \d{1,2} in year \d{4}"
        ", at position 0"
    )
else:
    NOT_99 = ""
    DAY_IS_OUT_OF_RANGE = "day is out of range for month, at position 0"


pytestmark = pytest.mark.filterwarnings(
    "ignore:errors='ignore' is deprecated:FutureWarning"
)


@pytest.fixture(params=[True, False])
def cache(request):
    """
    cache keyword to pass to to_datetime.
    """
    return request.param


class TestTimeConversionFormats:
    @pytest.mark.parametrize("readonly", [True, False])
    def test_to_datetime_readonly(self, readonly):
        # GH#34857
        arr = np.array([], dtype=object)
        if readonly:
            arr.setflags(write=False)
        result = to_datetime(arr)
        expected = to_datetime([])
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "format, expected",
        [
            [
                "%d/%m/%Y",
                [Timestamp("20000101"), Timestamp("20000201"), Timestamp("20000301")],
            ],
            [
                "%m/%d/%Y",
                [Timestamp("20000101"), Timestamp("20000102"), Timestamp("20000103")],
            ],
        ],
    )
    def test_to_datetime_format(self, cache, index_or_series, format, expected):
        values = index_or_series(["1/1/2000", "1/2/2000", "1/3/2000"])
        result = to_datetime(values, format=format, cache=cache)
        expected = index_or_series(expected)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize(
        "arg, expected, format",
        [
            ["1/1/2000", "20000101", "%d/%m/%Y"],
            ["1/1/2000", "20000101", "%m/%d/%Y"],
            ["1/2/2000", "20000201", "%d/%m/%Y"],
            ["1/2/2000", "20000102", "%m/%d/%Y"],
            ["1/3/2000", "20000301", "%d/%m/%Y"],
            ["1/3/2000", "20000103", "%m/%d/%Y"],
        ],
    )
    def test_to_datetime_format_scalar(self, cache, arg, expected, format):
        result = to_datetime(arg, format=format, cache=cache)
        expected = Timestamp(expected)
        assert result == expected

    def test_to_datetime_format_YYYYMMDD(self, cache):
        ser = Series([19801222, 19801222] + [19810105] * 5)
        expected = Series([Timestamp(x) for x in ser.apply(str)])

        result = to_datetime(ser, format="%Y%m%d", cache=cache)
        tm.assert_series_equal(result, expected)

        result = to_datetime(ser.apply(str), format="%Y%m%d", cache=cache)
        tm.assert_series_equal(result, expected)

    def test_to_datetime_format_YYYYMMDD_with_nat(self, cache):
        # Explicit cast to float to explicit cast when setting np.nan
        ser = Series([19801222, 19801222] + [19810105] * 5, dtype="float")
        # with NaT
        expected = Series(
            [Timestamp("19801222"), Timestamp("19801222")] + [Timestamp("19810105")] * 5
        )
        expected[2] = np.nan
        ser[2] = np.nan

        result = to_datetime(ser, format="%Y%m%d", cache=cache)
        tm.assert_series_equal(result, expected)

        # string with NaT
        ser2 = ser.apply(str)
        ser2[2] = "nat"
        with pytest.raises(
            ValueError,
            match=(
                'unconverted data remains when parsing with format "%Y%m%d": ".0", '
                "at position 0"
            ),
        ):
            # https://github.com/pandas-dev/pandas/issues/50051
            to_datetime(ser2, format="%Y%m%d", cache=cache)

    def test_to_datetime_format_YYYYMM_with_nat(self, cache):
        # https://github.com/pandas-dev/pandas/issues/50237
        # Explicit cast to float to explicit cast when setting np.nan
        ser = Series([198012, 198012] + [198101] * 5, dtype="float")
        expected = Series(
            [Timestamp("19801201"), Timestamp("19801201")] + [Timestamp("19810101")] * 5
        )
        expected[2] = np.nan
        ser[2] = np.nan
        result = to_datetime(ser, format="%Y%m", cache=cache)
        tm.assert_series_equal(result, expected)

    def test_to_datetime_format_YYYYMMDD_ignore(self, cache):
        # coercion
        # GH 7930, GH 14487
        ser = Series([20121231, 20141231, 99991231])
        result = to_datetime(ser, format="%Y%m%d", errors="ignore", cache=cache)
        expected = Series(
            [20121231, 20141231, 99991231],
            dtype=object,
        )
        tm.assert_series_equal(result, expected)

    def test_to_datetime_format_YYYYMMDD_ignore_with_outofbounds(self, cache):
        # https://github.com/pandas-dev/pandas/issues/26493
        result = to_datetime(
            ["15010101", "20150101", np.nan],
            format="%Y%m%d",
            errors="ignore",
            cache=cache,
        )
        expected = Index(["15010101", "20150101", np.nan], dtype=object)
        tm.assert_index_equal(result, expected)

    def test_to_datetime_format_YYYYMMDD_coercion(self, cache):
        # coercion
        # GH 7930
        ser = Series([20121231, 20141231, 99991231])
        result = to_datetime(ser, format="%Y%m%d", errors="coerce", cache=cache)
        expected = Series(["20121231", "20141231", "NaT"], dtype="M8[ns]")
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "input_s",
        [
            # Null values with Strings
            ["19801222", "20010112", None],
            ["19801222", "20010112", np.nan],
            ["19801222", "20010112", NaT],
            ["19801222", "20010112", "NaT"],
            # Null values with Integers
            [19801222, 20010112, None],
            [19801222, 20010112, np.nan],
            [19801222, 20010112, NaT],
            [19801222, 20010112, "NaT"],
        ],
    )
    def test_to_datetime_format_YYYYMMDD_with_none(self, input_s):
        # GH 30011
        # format='%Y%m%d'
        # with None
        expected = Series([Timestamp("19801222"), Timestamp("20010112"), NaT])
        result = Series(to_datetime(input_s, format="%Y%m%d"))
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "input_s, expected",
        [
            # NaN before strings with invalid date values
            [
                Series(["19801222", np.nan, "20010012", "10019999"]),
                Series([Timestamp("19801222"), np.nan, np.nan, np.nan]),
            ],
            # NaN after strings with invalid date values
            [
                Series(["19801222", "20010012", "10019999", np.nan]),
                Series([Timestamp("19801222"), np.nan, np.nan, np.nan]),
            ],
            # NaN before integers with invalid date values
            [
                Series([20190813, np.nan, 20010012, 20019999]),
                Series([Timestamp("20190813"), np.nan, np.nan, np.nan]),
            ],
            # NaN after integers with invalid date values
            [
                Series([20190813, 20010012, np.nan, 20019999]),
                Series([Timestamp("20190813"), np.nan, np.nan, np.nan]),
            ],
        ],
    )
    def test_to_datetime_format_YYYYMMDD_overflow(self, input_s, expected):
        # GH 25512
        # format='%Y%m%d', errors='coerce'
        result = to_datetime(input_s, format="%Y%m%d", errors="coerce")
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "data, format, expected",
        [
            ([pd.NA], "%Y%m%d%H%M%S", DatetimeIndex(["NaT"])),
            ([pd.NA], None, DatetimeIndex(["NaT"])),
            (
                [pd.NA, "20210202202020"],
                "%Y%m%d%H%M%S",
                DatetimeIndex(["NaT", "2021-02-02 20:20:20"]),
            ),
            (["201010", pd.NA], "%y%m%d", DatetimeIndex(["2020-10-10", "NaT"])),
            (["201010", pd.NA], "%d%m%y", DatetimeIndex(["2010-10-20", "NaT"])),
            ([None, np.nan, pd.NA], None, DatetimeIndex(["NaT", "NaT", "NaT"])),
            ([None, np.nan, pd.NA], "%Y%m%d", DatetimeIndex(["NaT", "NaT", "NaT"])),
        ],
    )
    def test_to_datetime_with_NA(self, data, format, expected):
        # GH#42957
        result = to_datetime(data, format=format)
        tm.assert_index_equal(result, expected)

    def test_to_datetime_with_NA_with_warning(self):
        # GH#42957
        result = to_datetime(["201010", pd.NA])
        expected = DatetimeIndex(["2010-10-20", "NaT"])
        tm.assert_index_equal(result, expected)

    def test_to_datetime_format_integer(self, cache):
        # GH 10178
        ser = Series([2000, 2001, 2002])
        expected = Series([Timestamp(x) for x in ser.apply(str)])

        result = to_datetime(ser, format="%Y", cache=cache)
        tm.assert_series_equal(result, expected)

        ser = Series([200001, 200105, 200206])
        expected = Series([Timestamp(x[:4] + "-" + x[4:]) for x in ser.apply(str)])

        result = to_datetime(ser, format="%Y%m", cache=cache)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "int_date, expected",
        [
            # valid date, length == 8
            [20121030, datetime(2012, 10, 30)],
            # short valid date, length == 6
            [199934, datetime(1999, 3, 4)],
            # long integer date partially parsed to datetime(2012,1,1), length > 8
            [2012010101, 2012010101],
            # invalid date partially parsed to datetime(2012,9,9), length == 8
            [20129930, 20129930],
            # short integer date partially parsed to datetime(2012,9,9), length < 8
            [2012993, 2012993],
            # short invalid date, length == 4
            [2121, 2121],
        ],
    )
    def test_int_to_datetime_format_YYYYMMDD_typeerror(self, int_date, expected):
        # GH 26583
        result = to_datetime(int_date, format="%Y%m%d", errors="ignore")
        assert result == expected

    def test_to_datetime_format_microsecond(self, cache):
        month_abbr = calendar.month_abbr[4]
        val = f"01-{month_abbr}-2011 00:00:01.978"

        format = "%d-%b-%Y %H:%M:%S.%f"
        result = to_datetime(val, format=format, cache=cache)
        exp = datetime.strptime(val, format)
        assert result == exp

    @pytest.mark.parametrize(
        "value, format, dt",
        [
            ["01/10/2010 15:20", "%m/%d/%Y %H:%M", Timestamp("2010-01-10 15:20")],
            ["01/10/2010 05:43", "%m/%d/%Y %I:%M", Timestamp("2010-01-10 05:43")],
            [
                "01/10/2010 13:56:01",
                "%m/%d/%Y %H:%M:%S",
                Timestamp("2010-01-10 13:56:01"),
            ],
            # The 3 tests below are locale-dependent.
            # They pass, except when the machine locale is zh_CN or it_IT .
            pytest.param(
                "01/10/2010 08:14 PM",
                "%m/%d/%Y %I:%M %p",
                Timestamp("2010-01-10 20:14"),
                marks=pytest.mark.xfail(
                    locale.getlocale()[0] in ("zh_CN", "it_IT"),
                    reason="fail on a CI build with LC_ALL=zh_CN.utf8/it_IT.utf8",
                    strict=False,
                ),
            ),
            pytest.param(
                "01/10/2010 07:40 AM",
                "%m/%d/%Y %I:%M %p",
                Timestamp("2010-01-10 07:40"),
                marks=pytest.mark.xfail(
                    locale.getlocale()[0] in ("zh_CN", "it_IT"),
                    reason="fail on a CI build with LC_ALL=zh_CN.utf8/it_IT.utf8",
                    strict=False,
                ),
            ),
            pytest.param(
                "01/10/2010 09:12:56 AM",
                "%m/%d/%Y %I:%M:%S %p",
                Timestamp("2010-01-10 09:12:56"),
                marks=pytest.mark.xfail(
                    locale.getlocale()[0] in ("zh_CN", "it_IT"),
                    reason="fail on a CI build with LC_ALL=zh_CN.utf8/it_IT.utf8",
                    strict=False,
                ),
            ),
        ],
    )
    def test_to_datetime_format_time(self, cache, value, format, dt):
        assert to_datetime(value, format=format, cache=cache) == dt

    @td.skip_if_not_us_locale
    def test_to_datetime_with_non_exact(self, cache):
        # GH 10834
        # 8904
        # exact kw
        ser = Series(
            ["19MAY11", "foobar19MAY11", "19MAY11:00:00:00", "19MAY11 00:00:00Z"]
        )
        result = to_datetime(ser, format="%d%b%y", exact=False, cache=cache)
        expected = to_datetime(
            ser.str.extract(r"(\d+\w+\d+)", expand=False), format="%d%b%y", cache=cache
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "format, expected",
        [
            ("%Y-%m-%d", Timestamp(2000, 1, 3)),
            ("%Y-%d-%m", Timestamp(2000, 3, 1)),
            ("%Y-%m-%d %H", Timestamp(2000, 1, 3, 12)),
            ("%Y-%d-%m %H", Timestamp(2000, 3, 1, 12)),
            ("%Y-%m-%d %H:%M", Timestamp(2000, 1, 3, 12, 34)),
            ("%Y-%d-%m %H:%M", Timestamp(2000, 3, 1, 12, 34)),
            ("%Y-%m-%d %H:%M:%S", Timestamp(2000, 1, 3, 12, 34, 56)),
            ("%Y-%d-%m %H:%M:%S", Timestamp(2000, 3, 1, 12, 34, 56)),
            ("%Y-%m-%d %H:%M:%S.%f", Timestamp(2000, 1, 3, 12, 34, 56, 123456)),
            ("%Y-%d-%m %H:%M:%S.%f", Timestamp(2000, 3, 1, 12, 34, 56, 123456)),
            (
                "%Y-%m-%d %H:%M:%S.%f%z",
                Timestamp(2000, 1, 3, 12, 34, 56, 123456, tz="UTC+01:00"),
            ),
            (
                "%Y-%d-%m %H:%M:%S.%f%z",
                Timestamp(2000, 3, 1, 12, 34, 56, 123456, tz="UTC+01:00"),
            ),
        ],
    )
    def test_non_exact_doesnt_parse_whole_string(self, cache, format, expected):
        # https://github.com/pandas-dev/pandas/issues/50412
        # the formats alternate between ISO8601 and non-ISO8601 to check both paths
        result = to_datetime(
            "2000-01-03 12:34:56.123456+01:00", format=format, exact=False
        )
        assert result == expected

    @pytest.mark.parametrize(
        "arg",
        [
            "2012-01-01 09:00:00.000000001",
            "2012-01-01 09:00:00.000001",
            "2012-01-01 09:00:00.001",
            "2012-01-01 09:00:00.001000",
            "2012-01-01 09:00:00.001000000",
        ],
    )
    def test_parse_nanoseconds_with_formula(self, cache, arg):
        # GH8989
        # truncating the nanoseconds when a format was provided
        expected = to_datetime(arg, cache=cache)
        result = to_datetime(arg, format="%Y-%m-%d %H:%M:%S.%f", cache=cache)
        assert result == expected

    @pytest.mark.parametrize(
        "value,fmt,expected",
        [
            ["2009324", "%Y%W%w", Timestamp("2009-08-13")],
            ["2013020", "%Y%U%w", Timestamp("2013-01-13")],
        ],
    )
    def test_to_datetime_format_weeks(self, value, fmt, expected, cache):
        assert to_datetime(value, format=fmt, cache=cache) == expected

    @pytest.mark.parametrize(
        "fmt,dates,expected_dates",
        [
            [
                "%Y-%m-%d %H:%M:%S %Z",
                ["2010-01-01 12:00:00 UTC"] * 2,
                [Timestamp("2010-01-01 12:00:00", tz="UTC")] * 2,
            ],
            [
                "%Y-%m-%d %H:%M:%S%z",
                ["2010-01-01 12:00:00+0100"] * 2,
                [
                    Timestamp(
                        "2010-01-01 12:00:00", tzinfo=timezone(timedelta(minutes=60))
                    )
                ]
                * 2,
            ],
            [
                "%Y-%m-%d %H:%M:%S %z",
                ["2010-01-01 12:00:00 +0100"] * 2,
                [
                    Timestamp(
                        "2010-01-01 12:00:00", tzinfo=timezone(timedelta(minutes=60))
                    )
                ]
                * 2,
            ],
            [
                "%Y-%m-%d %H:%M:%S %z",
                ["2010-01-01 12:00:00 Z", "2010-01-01 12:00:00 Z"],
                [
                    Timestamp(
                        "2010-01-01 12:00:00", tzinfo=pytz.FixedOffset(0)
                    ),  # pytz coerces to UTC
                    Timestamp("2010-01-01 12:00:00", tzinfo=pytz.FixedOffset(0)),
                ],
            ],
        ],
    )
    def test_to_datetime_parse_tzname_or_tzoffset(self, fmt, dates, expected_dates):
        # GH 13486
        result = to_datetime(dates, format=fmt)
        expected = Index(expected_dates)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize(
        "fmt,dates,expected_dates",
        [
            [
                "%Y-%m-%d %H:%M:%S %Z",
                [
                    "2010-01-01 12:00:00 UTC",
                    "2010-01-01 12:00:00 GMT",
                    "2010-01-01 12:00:00 US/Pacific",
                ],
                [
                    Timestamp("2010-01-01 12:00:00", tz="UTC"),
                    Timestamp("2010-01-01 12:00:00", tz="GMT"),
                    Timestamp("2010-01-01 12:00:00", tz="US/Pacific"),
                ],
            ],
            [
                "%Y-%m-%d %H:%M:%S %z",
                ["2010-01-01 12:00:00 +0100", "2010-01-01 12:00:00 -0100"],
                [
                    Timestamp(
                        "2010-01-01 12:00:00", tzinfo=timezone(timedelta(minutes=60))
                    ),
                    Timestamp(
                        "2010-01-01 12:00:00", tzinfo=timezone(timedelta(minutes=-60))
                    ),
                ],
            ],
        ],
    )
    def test_to_datetime_parse_tzname_or_tzoffset_utc_false_deprecated(
        self, fmt, dates, expected_dates
    ):
        # GH 13486, 50887
        msg = "parsing datetimes with mixed time zones will raise an error"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = to_datetime(dates, format=fmt)
        expected = Index(expected_dates)
        tm.assert_equal(result, expected)

    def test_to_datetime_parse_tzname_or_tzoffset_different_tz_to_utc(self):
        # GH 32792
        dates = [
            "2010-01-01 12:00:00 +0100",
            "2010-01-01 12:00:00 -0100",
            "2010-01-01 12:00:00 +0300",
            "2010-01-01 12:00:00 +0400",
        ]
        expected_dates = [
            "2010-01-01 11:00:00+00:00",
            "2010-01-01 13:00:00+00:00",
            "2010-01-01 09:00:00+00:00",
            "2010-01-01 08:00:00+00:00",
        ]
        fmt = "%Y-%m-%d %H:%M:%S %z"

        result = to_datetime(dates, format=fmt, utc=True)
        expected = DatetimeIndex(expected_dates)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "offset", ["+0", "-1foo", "UTCbar", ":10", "+01:000:01", ""]
    )
    def test_to_datetime_parse_timezone_malformed(self, offset):
        fmt = "%Y-%m-%d %H:%M:%S %z"
        date = "2010-01-01 12:00:00 " + offset

        msg = "|".join(
            [
                r'^time data ".*" doesn\'t match format ".*", at position 0. '
                f"{PARSING_ERR_MSG}$",
                r'^unconverted data remains when parsing with format ".*": ".*", '
                f"at position 0. {PARSING_ERR_MSG}$",
            ]
        )
        with pytest.raises(ValueError, match=msg):
            to_datetime([date], format=fmt)

    def test_to_datetime_parse_timezone_keeps_name(self):
        # GH 21697
        fmt = "%Y-%m-%d %H:%M:%S %z"
        arg = Index(["2010-01-01 12:00:00 Z"], name="foo")
        result = to_datetime(arg, format=fmt)
        expected = DatetimeIndex(["2010-01-01 12:00:00"], tz="UTC", name="foo")
        tm.assert_index_equal(result, expected)


class TestToDatetime:
    @pytest.mark.filterwarnings("ignore:Could not infer format")
    def test_to_datetime_overflow(self):
        # we should get an OutOfBoundsDatetime, NOT OverflowError
        # TODO: Timestamp raises ValueError("could not convert string to Timestamp")
        #  can we make these more consistent?
        arg = "08335394550"
        msg = 'Parsing "08335394550" to datetime overflows, at position 0'
        with pytest.raises(OutOfBoundsDatetime, match=msg):
            to_datetime(arg)

        with pytest.raises(OutOfBoundsDatetime, match=msg):
            to_datetime([arg])

        res = to_datetime(arg, errors="coerce")
        assert res is NaT
        res = to_datetime([arg], errors="coerce")
        tm.assert_index_equal(res, Index([NaT]))

        res = to_datetime(arg, errors="ignore")
        assert isinstance(res, str) and res == arg
        res = to_datetime([arg], errors="ignore")
        tm.assert_index_equal(res, Index([arg], dtype=object))

    def test_to_datetime_mixed_datetime_and_string(self):
        # GH#47018 adapted old doctest with new behavior
        d1 = datetime(2020, 1, 1, 17, tzinfo=timezone(-timedelta(hours=1)))
        d2 = datetime(2020, 1, 1, 18, tzinfo=timezone(-timedelta(hours=1)))
        res = to_datetime(["2020-01-01 17:00 -0100", d2])
        expected = to_datetime([d1, d2]).tz_convert(timezone(timedelta(minutes=-60)))
        tm.assert_index_equal(res, expected)

    def test_to_datetime_mixed_string_and_numeric(self):
        # GH#55780 np.array(vals) would incorrectly cast the number to str
        vals = ["2016-01-01", 0]
        expected = DatetimeIndex([Timestamp(x) for x in vals])
        result = to_datetime(vals, format="mixed")
        result2 = to_datetime(vals[::-1], format="mixed")[::-1]
        result3 = DatetimeIndex(vals)
        result4 = DatetimeIndex(vals[::-1])[::-1]

        tm.assert_index_equal(result, expected)
        tm.assert_index_equal(result2, expected)
        tm.assert_index_equal(result3, expected)
        tm.assert_index_equal(result4, expected)

    @pytest.mark.parametrize(
        "format", ["%Y-%m-%d", "%Y-%d-%m"], ids=["ISO8601", "non-ISO8601"]
    )
    def test_to_datetime_mixed_date_and_string(self, format):
        # https://github.com/pandas-dev/pandas/issues/50108
        d1 = date(2020, 1, 2)
        res = to_datetime(["2020-01-01", d1], format=format)
        expected = DatetimeIndex(["2020-01-01", "2020-01-02"], dtype="M8[ns]")
        tm.assert_index_equal(res, expected)

    @pytest.mark.parametrize(
        "fmt",
        ["%Y-%d-%m %H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z"],
        ids=["non-ISO8601 format", "ISO8601 format"],
    )
    @pytest.mark.parametrize(
        "utc, args, expected",
        [
            pytest.param(
                True,
                ["2000-01-01 01:00:00-08:00", "2000-01-01 02:00:00-08:00"],
                DatetimeIndex(
                    ["2000-01-01 09:00:00+00:00", "2000-01-01 10:00:00+00:00"],
                    dtype="datetime64[ns, UTC]",
                ),
                id="all tz-aware, with utc",
            ),
            pytest.param(
                False,
                ["2000-01-01 01:00:00+00:00", "2000-01-01 02:00:00+00:00"],
                DatetimeIndex(
                    ["2000-01-01 01:00:00+00:00", "2000-01-01 02:00:00+00:00"],
                ),
                id="all tz-aware, without utc",
            ),
            pytest.param(
                True,
                ["2000-01-01 01:00:00-08:00", "2000-01-01 02:00:00+00:00"],
                DatetimeIndex(
                    ["2000-01-01 09:00:00+00:00", "2000-01-01 02:00:00+00:00"],
                    dtype="datetime64[ns, UTC]",
                ),
                id="all tz-aware, mixed offsets, with utc",
            ),
            pytest.param(
                True,
                ["2000-01-01 01:00:00", "2000-01-01 02:00:00+00:00"],
                DatetimeIndex(
                    ["2000-01-01 01:00:00+00:00", "2000-01-01 02:00:00+00:00"],
                    dtype="datetime64[ns, UTC]",
                ),
                id="tz-aware string, naive pydatetime, with utc",
            ),
        ],
    )
    @pytest.mark.parametrize(
        "constructor",
        [Timestamp, lambda x: Timestamp(x).to_pydatetime()],
    )
    def test_to_datetime_mixed_datetime_and_string_with_format(
        self, fmt, utc, args, expected, constructor
    ):
        # https://github.com/pandas-dev/pandas/issues/49298
        # https://github.com/pandas-dev/pandas/issues/50254
        # note: ISO8601 formats go down a fastpath, so we need to check both
        # a ISO8601 format and a non-ISO8601 one
        ts1 = constructor(args[0])
        ts2 = args[1]
        result = to_datetime([ts1, ts2], format=fmt, utc=utc)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "fmt",
        ["%Y-%d-%m %H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z"],
        ids=["non-ISO8601 format", "ISO8601 format"],
    )
    @pytest.mark.parametrize(
        "constructor",
        [Timestamp, lambda x: Timestamp(x).to_pydatetime()],
    )
    def test_to_datetime_mixed_datetime_and_string_with_format_mixed_offsets_utc_false(
        self, fmt, constructor
    ):
        # https://github.com/pandas-dev/pandas/issues/49298
        # https://github.com/pandas-dev/pandas/issues/50254
        # note: ISO8601 formats go down a fastpath, so we need to check both
        # a ISO8601 format and a non-ISO8601 one
        args = ["2000-01-01 01:00:00", "2000-01-01 02:00:00+00:00"]
        ts1 = constructor(args[0])
        ts2 = args[1]
        msg = "parsing datetimes with mixed time zones will raise an error"

        expected = Index(
            [
                Timestamp("2000-01-01 01:00:00"),
                Timestamp("2000-01-01 02:00:00+0000", tz="UTC"),
            ],
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = to_datetime([ts1, ts2], format=fmt, utc=False)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "fmt, expected",
        [
            pytest.param(
                "%Y-%m-%d %H:%M:%S%z",
                Index(
                    [
                        Timestamp("2000-01-01 09:00:00+0100", tz="UTC+01:00"),
                        Timestamp("2000-01-02 02:00:00+0200", tz="UTC+02:00"),
                        NaT,
                    ]
                ),
                id="ISO8601, non-UTC",
            ),
            pytest.param(
                "%Y-%d-%m %H:%M:%S%z",
                Index(
                    [
                        Timestamp("2000-01-01 09:00:00+0100", tz="UTC+01:00"),
                        Timestamp("2000-02-01 02:00:00+0200", tz="UTC+02:00"),
                        NaT,
                    ]
                ),
                id="non-ISO8601, non-UTC",
            ),
        ],
    )
    def test_to_datetime_mixed_offsets_with_none_tz(self, fmt, expected):
        # https://github.com/pandas-dev/pandas/issues/50071
        msg = "parsing datetimes with mixed time zones will raise an error"

        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = to_datetime(
                ["2000-01-01 09:00:00+01:00", "2000-01-02 02:00:00+02:00", None],
                format=fmt,
                utc=False,
            )
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "fmt, expected",
        [
            pytest.param(
                "%Y-%m-%d %H:%M:%S%z",
                DatetimeIndex(
                    ["2000-01-01 08:00:00+00:00", "2000-01-02 00:00:00+00:00", "NaT"],
                    dtype="datetime64[ns, UTC]",
                ),
                id="ISO8601, UTC",
            ),
            pytest.param(
                "%Y-%d-%m %H:%M:%S%z",
                DatetimeIndex(
                    ["2000-01-01 08:00:00+00:00", "2000-02-01 00:00:00+00:00", "NaT"],
                    dtype="datetime64[ns, UTC]",
                ),
                id="non-ISO8601, UTC",
            ),
        ],
    )
    def test_to_datetime_mixed_offsets_with_none(self, fmt, expected):
        # https://github.com/pandas-dev/pandas/issues/50071
        result = to_datetime(
            ["2000-01-01 09:00:00+01:00", "2000-01-02 02:00:00+02:00", None],
            format=fmt,
            utc=True,
        )
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "fmt",
        ["%Y-%d-%m %H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z"],
        ids=["non-ISO8601 format", "ISO8601 format"],
    )
    @pytest.mark.parametrize(
        "args",
        [
            pytest.param(
                ["2000-01-01 01:00:00-08:00", "2000-01-01 02:00:00-07:00"],
                id="all tz-aware, mixed timezones, without utc",
            ),
        ],
    )
    @pytest.mark.parametrize(
        "constructor",
        [Timestamp, lambda x: Timestamp(x).to_pydatetime()],
    )
    def test_to_datetime_mixed_datetime_and_string_with_format_raises(
        self, fmt, args, constructor
    ):
        # https://github.com/pandas-dev/pandas/issues/49298
        # note: ISO8601 formats go down a fastpath, so we need to check both
        # a ISO8601 format and a non-ISO8601 one
        ts1 = constructor(args[0])
        ts2 = constructor(args[1])
        with pytest.raises(
            ValueError, match="cannot be converted to datetime64 unless utc=True"
        ):
            to_datetime([ts1, ts2], format=fmt, utc=False)

    def test_to_datetime_np_str(self):
        # GH#32264
        # GH#48969
        value = np.str_("2019-02-04 10:18:46.297000+0000")

        ser = Series([value])

        exp = Timestamp("2019-02-04 10:18:46.297000", tz="UTC")

        assert to_datetime(value) == exp
        assert to_datetime(ser.iloc[0]) == exp

        res = to_datetime([value])
        expected = Index([exp])
        tm.assert_index_equal(res, expected)

        res = to_datetime(ser)
        expected = Series(expected)
        tm.assert_series_equal(res, expected)

    @pytest.mark.parametrize(
        "s, _format, dt",
        [
            ["2015-1-1", "%G-%V-%u", datetime(2014, 12, 29, 0, 0)],
            ["2015-1-4", "%G-%V-%u", datetime(2015, 1, 1, 0, 0)],
            ["2015-1-7", "%G-%V-%u", datetime(2015, 1, 4, 0, 0)],
        ],
    )
    def test_to_datetime_iso_week_year_format(self, s, _format, dt):
        # See GH#16607
        assert to_datetime(s, format=_format) == dt

    @pytest.mark.parametrize(
        "msg, s, _format",
        [
            [
                "ISO week directive '%V' is incompatible with the year directive "
                "'%Y'. Use the ISO year '%G' instead.",
                "1999 50",
                "%Y %V",
            ],
            [
                "ISO year directive '%G' must be used with the ISO week directive "
                "'%V' and a weekday directive '%A', '%a', '%w', or '%u'.",
                "1999 51",
                "%G %V",
            ],
            [
                "ISO year directive '%G' must be used with the ISO week directive "
                "'%V' and a weekday directive '%A', '%a', '%w', or '%u'.",
                "1999 Monday",
                "%G %A",
            ],
            [
                "ISO year directive '%G' must be used with the ISO week directive "
                "'%V' and a weekday directive '%A', '%a', '%w', or '%u'.",
                "1999 Mon",
                "%G %a",
            ],
            [
                "ISO year directive '%G' must be used with the ISO week directive "
                "'%V' and a weekday directive '%A', '%a', '%w', or '%u'.",
                "1999 6",
                "%G %w",
            ],
            [
                "ISO year directive '%G' must be used with the ISO week directive "
                "'%V' and a weekday directive '%A', '%a', '%w', or '%u'.",
                "1999 6",
                "%G %u",
            ],
            [
                "ISO year directive '%G' must be used with the ISO week directive "
                "'%V' and a weekday directive '%A', '%a', '%w', or '%u'.",
                "2051",
                "%G",
            ],
            [
                "Day of the year directive '%j' is not compatible with ISO year "
                "directive '%G'. Use '%Y' instead.",
                "1999 51 6 256",
                "%G %V %u %j",
            ],
            [
                "ISO week directive '%V' is incompatible with the year directive "
                "'%Y'. Use the ISO year '%G' instead.",
                "1999 51 Sunday",
                "%Y %V %A",
            ],
            [
                "ISO week directive '%V' is incompatible with the year directive "
                "'%Y'. Use the ISO year '%G' instead.",
                "1999 51 Sun",
                "%Y %V %a",
            ],
            [
                "ISO week directive '%V' is incompatible with the year directive "
                "'%Y'. Use the ISO year '%G' instead.",
                "1999 51 1",
                "%Y %V %w",
            ],
            [
                "ISO week directive '%V' is incompatible with the year directive "
                "'%Y'. Use the ISO year '%G' instead.",
                "1999 51 1",
                "%Y %V %u",
            ],
            [
                "ISO week directive '%V' must be used with the ISO year directive "
                "'%G' and a weekday directive '%A', '%a', '%w', or '%u'.",
                "20",
                "%V",
            ],
            [
                "ISO week directive '%V' must be used with the ISO year directive "
                "'%G' and a weekday directive '%A', '%a', '%w', or '%u'.",
                "1999 51 Sunday",
                "%V %A",
            ],
            [
                "ISO week directive '%V' must be used with the ISO year directive "
                "'%G' and a weekday directive '%A', '%a', '%w', or '%u'.",
                "1999 51 Sun",
                "%V %a",
            ],
            [
                "ISO week directive '%V' must be used with the ISO year directive "
                "'%G' and a weekday directive '%A', '%a', '%w', or '%u'.",
                "1999 51 1",
                "%V %w",
            ],
            [
                "ISO week directive '%V' must be used with the ISO year directive "
                "'%G' and a weekday directive '%A', '%a', '%w', or '%u'.",
                "1999 51 1",
                "%V %u",
            ],
            [
                "Day of the year directive '%j' is not compatible with ISO year "
                "directive '%G'. Use '%Y' instead.",
                "1999 50",
                "%G %j",
            ],
            [
                "ISO week directive '%V' must be used with the ISO year directive "
                "'%G' and a weekday directive '%A', '%a', '%w', or '%u'.",
                "20 Monday",
                "%V %A",
            ],
        ],
    )
    @pytest.mark.parametrize("errors", ["raise", "coerce", "ignore"])
    def test_error_iso_week_year(self, msg, s, _format, errors):
        # See GH#16607, GH#50308
        # This test checks for errors thrown when giving the wrong format
        # However, as discussed on PR#25541, overriding the locale
        # causes a different error to be thrown due to the format being
        # locale specific, but the test data is in english.
        # Therefore, the tests only run when locale is not overwritten,
        # as a sort of solution to this problem.
        if locale.getlocale() != ("zh_CN", "UTF-8") and locale.getlocale() != (
            "it_IT",
            "UTF-8",
        ):
            with pytest.raises(ValueError, match=msg):
                to_datetime(s, format=_format, errors=errors)

    @pytest.mark.parametrize("tz", [None, "US/Central"])
    def test_to_datetime_dtarr(self, tz):
        # DatetimeArray
        dti = date_range("1965-04-03", periods=19, freq="2W", tz=tz)
        arr = dti._data

        result = to_datetime(arr)
        assert result is arr

    # Doesn't work on Windows since tzpath not set correctly
    @td.skip_if_windows
    @pytest.mark.parametrize("arg_class", [Series, Index])
    @pytest.mark.parametrize("utc", [True, False])
    @pytest.mark.parametrize("tz", [None, "US/Central"])
    def test_to_datetime_arrow(self, tz, utc, arg_class):
        pa = pytest.importorskip("pyarrow")

        dti = date_range("1965-04-03", periods=19, freq="2W", tz=tz)
        dti = arg_class(dti)

        dti_arrow = dti.astype(pd.ArrowDtype(pa.timestamp(unit="ns", tz=tz)))

        result = to_datetime(dti_arrow, utc=utc)
        expected = to_datetime(dti, utc=utc).astype(
            pd.ArrowDtype(pa.timestamp(unit="ns", tz=tz if not utc else "UTC"))
        )
        if not utc and arg_class is not Series:
            # Doesn't hold for utc=True, since that will astype
            # to_datetime also returns a new object for series
            assert result is dti_arrow
        if arg_class is Series:
            tm.assert_series_equal(result, expected)
        else:
            tm.assert_index_equal(result, expected)

    def test_to_datetime_pydatetime(self):
        actual = to_datetime(datetime(2008, 1, 15))
        assert actual == datetime(2008, 1, 15)

    def test_to_datetime_YYYYMMDD(self):
        actual = to_datetime("20080115")
        assert actual == datetime(2008, 1, 15)

    def test_to_datetime_unparsable_ignore(self):
        # unparsable
        ser = "Month 1, 1999"
        assert to_datetime(ser, errors="ignore") == ser

    @td.skip_if_windows  # `tm.set_timezone` does not work in windows
    def test_to_datetime_now(self):
        # See GH#18666
        with tm.set_timezone("US/Eastern"):
            # GH#18705
            now = Timestamp("now").as_unit("ns")
            pdnow = to_datetime("now")
            pdnow2 = to_datetime(["now"])[0]

            # These should all be equal with infinite perf; this gives
            # a generous margin of 10 seconds
            assert abs(pdnow._value - now._value) < 1e10
            assert abs(pdnow2._value - now._value) < 1e10

            assert pdnow.tzinfo is None
            assert pdnow2.tzinfo is None

    @td.skip_if_windows  # `tm.set_timezone` does not work in windows
    @pytest.mark.parametrize("tz", ["Pacific/Auckland", "US/Samoa"])
    def test_to_datetime_today(self, tz):
        # See GH#18666
        # Test with one timezone far ahead of UTC and another far behind, so
        # one of these will _almost_ always be in a different day from UTC.
        # Unfortunately this test between 12 and 1 AM Samoa time
        # this both of these timezones _and_ UTC will all be in the same day,
        # so this test will not detect the regression introduced in #18666.
        with tm.set_timezone(tz):
            nptoday = np.datetime64("today").astype("datetime64[ns]").astype(np.int64)
            pdtoday = to_datetime("today")
            pdtoday2 = to_datetime(["today"])[0]

            tstoday = Timestamp("today").as_unit("ns")
            tstoday2 = Timestamp.today().as_unit("ns")

            # These should all be equal with infinite perf; this gives
            # a generous margin of 10 seconds
            assert abs(pdtoday.normalize()._value - nptoday) < 1e10
            assert abs(pdtoday2.normalize()._value - nptoday) < 1e10
            assert abs(pdtoday._value - tstoday._value) < 1e10
            assert abs(pdtoday._value - tstoday2._value) < 1e10

            assert pdtoday.tzinfo is None
            assert pdtoday2.tzinfo is None

    @pytest.mark.parametrize("arg", ["now", "today"])
    def test_to_datetime_today_now_unicode_bytes(self, arg):
        to_datetime([arg])

    @pytest.mark.parametrize(
        "format, expected_ds",
        [
            ("%Y-%m-%d %H:%M:%S%z", "2020-01-03"),
            ("%Y-%d-%m %H:%M:%S%z", "2020-03-01"),
            (None, "2020-01-03"),
        ],
    )
    @pytest.mark.parametrize(
        "string, attribute",
        [
            ("now", "utcnow"),
            ("today", "today"),
        ],
    )
    def test_to_datetime_now_with_format(self, format, expected_ds, string, attribute):
        # https://github.com/pandas-dev/pandas/issues/50359
        result = to_datetime(["2020-01-03 00:00:00Z", string], format=format, utc=True)
        expected = DatetimeIndex(
            [expected_ds, getattr(Timestamp, attribute)()], dtype="datetime64[ns, UTC]"
        )
        assert (expected - result).max().total_seconds() < 1

    @pytest.mark.parametrize(
        "dt", [np.datetime64("2000-01-01"), np.datetime64("2000-01-02")]
    )
    def test_to_datetime_dt64s(self, cache, dt):
        assert to_datetime(dt, cache=cache) == Timestamp(dt)

    @pytest.mark.parametrize(
        "arg, format",
        [
            ("2001-01-01", "%Y-%m-%d"),
            ("01-01-2001", "%d-%m-%Y"),
        ],
    )
    def test_to_datetime_dt64s_and_str(self, arg, format):
        # https://github.com/pandas-dev/pandas/issues/50036
        result = to_datetime([arg, np.datetime64("2020-01-01")], format=format)
        expected = DatetimeIndex(["2001-01-01", "2020-01-01"])
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "dt", [np.datetime64("1000-01-01"), np.datetime64("5000-01-02")]
    )
    @pytest.mark.parametrize("errors", ["raise", "ignore", "coerce"])
    def test_to_datetime_dt64s_out_of_ns_bounds(self, cache, dt, errors):
        # GH#50369 We cast to the nearest supported reso, i.e. "s"
        ts = to_datetime(dt, errors=errors, cache=cache)
        assert isinstance(ts, Timestamp)
        assert ts.unit == "s"
        assert ts.asm8 == dt

        ts = Timestamp(dt)
        assert ts.unit == "s"
        assert ts.asm8 == dt

    @pytest.mark.skip_ubsan
    def test_to_datetime_dt64d_out_of_bounds(self, cache):
        dt64 = np.datetime64(np.iinfo(np.int64).max, "D")

        msg = "Out of bounds second timestamp: 25252734927768524-07-27"
        with pytest.raises(OutOfBoundsDatetime, match=msg):
            Timestamp(dt64)
        with pytest.raises(OutOfBoundsDatetime, match=msg):
            to_datetime(dt64, errors="raise", cache=cache)

        assert to_datetime(dt64, errors="coerce", cache=cache) is NaT

    @pytest.mark.parametrize("unit", ["s", "D"])
    def test_to_datetime_array_of_dt64s(self, cache, unit):
        # https://github.com/pandas-dev/pandas/issues/31491
        # Need at least 50 to ensure cache is used.
        dts = [
            np.datetime64("2000-01-01", unit),
            np.datetime64("2000-01-02", unit),
        ] * 30
        # Assuming all datetimes are in bounds, to_datetime() returns
        # an array that is equal to Timestamp() parsing
        result = to_datetime(dts, cache=cache)
        if cache:
            # FIXME: behavior should not depend on cache
            expected = DatetimeIndex([Timestamp(x).asm8 for x in dts], dtype="M8[s]")
        else:
            expected = DatetimeIndex([Timestamp(x).asm8 for x in dts], dtype="M8[ns]")

        tm.assert_index_equal(result, expected)

        # A list of datetimes where the last one is out of bounds
        dts_with_oob = dts + [np.datetime64("9999-01-01")]

        # As of GH#51978 we do not raise in this case
        to_datetime(dts_with_oob, errors="raise")

        result = to_datetime(dts_with_oob, errors="coerce", cache=cache)
        if not cache:
            # FIXME: shouldn't depend on cache!
            expected = DatetimeIndex(
                [Timestamp(dts_with_oob[0]).asm8, Timestamp(dts_with_oob[1]).asm8] * 30
                + [NaT],
            )
        else:
            expected = DatetimeIndex(np.array(dts_with_oob, dtype="M8[s]"))
        tm.assert_index_equal(result, expected)

        # With errors='ignore', out of bounds datetime64s
        # are converted to their .item(), which depending on the version of
        # numpy is either a python datetime.datetime or datetime.date
        result = to_datetime(dts_with_oob, errors="ignore", cache=cache)
        if not cache:
            # FIXME: shouldn't depend on cache!
            expected = Index(dts_with_oob)
        tm.assert_index_equal(result, expected)

    def test_out_of_bounds_errors_ignore(self):
        # https://github.com/pandas-dev/pandas/issues/50587
        result = to_datetime(np.datetime64("9999-01-01"), errors="ignore")
        expected = np.datetime64("9999-01-01")
        assert result == expected

    def test_out_of_bounds_errors_ignore2(self):
        # GH#12424
        msg = "errors='ignore' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = to_datetime(Series(["2362-01-01", np.nan]), errors="ignore")
        exp = Series(["2362-01-01", np.nan])
        tm.assert_series_equal(res, exp)

    def test_to_datetime_tz(self, cache):
        # xref 8260
        # uniform returns a DatetimeIndex
        arr = [
            Timestamp("2013-01-01 13:00:00-0800", tz="US/Pacific"),
            Timestamp("2013-01-02 14:00:00-0800", tz="US/Pacific"),
        ]
        result = to_datetime(arr, cache=cache)
        expected = DatetimeIndex(
            ["2013-01-01 13:00:00", "2013-01-02 14:00:00"], tz="US/Pacific"
        )
        tm.assert_index_equal(result, expected)

    def test_to_datetime_tz_mixed(self, cache):
        # mixed tzs will raise if errors='raise'
        # https://github.com/pandas-dev/pandas/issues/50585
        arr = [
            Timestamp("2013-01-01 13:00:00", tz="US/Pacific"),
            Timestamp("2013-01-02 14:00:00", tz="US/Eastern"),
        ]
        msg = (
            "Tz-aware datetime.datetime cannot be "
            "converted to datetime64 unless utc=True"
        )
        with pytest.raises(ValueError, match=msg):
            to_datetime(arr, cache=cache)

        depr_msg = "errors='ignore' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            result = to_datetime(arr, cache=cache, errors="ignore")
        expected = Index(
            [
                Timestamp("2013-01-01 13:00:00-08:00"),
                Timestamp("2013-01-02 14:00:00-05:00"),
            ],
            dtype="object",
        )
        tm.assert_index_equal(result, expected)
        result = to_datetime(arr, cache=cache, errors="coerce")
        expected = DatetimeIndex(
            ["2013-01-01 13:00:00-08:00", "NaT"], dtype="datetime64[ns, US/Pacific]"
        )
        tm.assert_index_equal(result, expected)

    def test_to_datetime_different_offsets(self, cache):
        # inspired by asv timeseries.ToDatetimeNONISO8601 benchmark
        # see GH-26097 for more
        ts_string_1 = "March 1, 2018 12:00:00+0400"
        ts_string_2 = "March 1, 2018 12:00:00+0500"
        arr = [ts_string_1] * 5 + [ts_string_2] * 5
        expected = Index([parse(x) for x in arr])
        msg = "parsing datetimes with mixed time zones will raise an error"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = to_datetime(arr, cache=cache)
        tm.assert_index_equal(result, expected)

    def test_to_datetime_tz_pytz(self, cache):
        # see gh-8260
        us_eastern = pytz.timezone("US/Eastern")
        arr = np.array(
            [
                us_eastern.localize(
                    datetime(year=2000, month=1, day=1, hour=3, minute=0)
                ),
                us_eastern.localize(
                    datetime(year=2000, month=6, day=1, hour=3, minute=0)
                ),
            ],
            dtype=object,
        )
        result = to_datetime(arr, utc=True, cache=cache)
        expected = DatetimeIndex(
            ["2000-01-01 08:00:00+00:00", "2000-06-01 07:00:00+00:00"],
            dtype="datetime64[ns, UTC]",
            freq=None,
        )
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "init_constructor, end_constructor",
        [
            (Index, DatetimeIndex),
            (list, DatetimeIndex),
            (np.array, DatetimeIndex),
            (Series, Series),
        ],
    )
    def test_to_datetime_utc_true(self, cache, init_constructor, end_constructor):
        # See gh-11934 & gh-6415
        data = ["20100102 121314", "20100102 121315"]
        expected_data = [
            Timestamp("2010-01-02 12:13:14", tz="utc"),
            Timestamp("2010-01-02 12:13:15", tz="utc"),
        ]

        result = to_datetime(
            init_constructor(data), format="%Y%m%d %H%M%S", utc=True, cache=cache
        )
        expected = end_constructor(expected_data)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize(
        "scalar, expected",
        [
            ["20100102 121314", Timestamp("2010-01-02 12:13:14", tz="utc")],
            ["20100102 121315", Timestamp("2010-01-02 12:13:15", tz="utc")],
        ],
    )
    def test_to_datetime_utc_true_scalar(self, cache, scalar, expected):
        # Test scalar case as well
        result = to_datetime(scalar, format="%Y%m%d %H%M%S", utc=True, cache=cache)
        assert result == expected

    def test_to_datetime_utc_true_with_series_single_value(self, cache):
        # GH 15760 UTC=True with Series
        ts = 1.5e18
        result = to_datetime(Series([ts]), utc=True, cache=cache)
        expected = Series([Timestamp(ts, tz="utc")])
        tm.assert_series_equal(result, expected)

    def test_to_datetime_utc_true_with_series_tzaware_string(self, cache):
        ts = "2013-01-01 00:00:00-01:00"
        expected_ts = "2013-01-01 01:00:00"
        data = Series([ts] * 3)
        result = to_datetime(data, utc=True, cache=cache)
        expected = Series([Timestamp(expected_ts, tz="utc")] * 3)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "date, dtype",
        [
            ("2013-01-01 01:00:00", "datetime64[ns]"),
            ("2013-01-01 01:00:00", "datetime64[ns, UTC]"),
        ],
    )
    def test_to_datetime_utc_true_with_series_datetime_ns(self, cache, date, dtype):
        expected = Series(
            [Timestamp("2013-01-01 01:00:00", tz="UTC")], dtype="M8[ns, UTC]"
        )
        result = to_datetime(Series([date], dtype=dtype), utc=True, cache=cache)
        tm.assert_series_equal(result, expected)

    def test_to_datetime_tz_psycopg2(self, request, cache):
        # xref 8260
        psycopg2_tz = pytest.importorskip("psycopg2.tz")

        # misc cases
        tz1 = psycopg2_tz.FixedOffsetTimezone(offset=-300, name=None)
        tz2 = psycopg2_tz.FixedOffsetTimezone(offset=-240, name=None)
        arr = np.array(
            [
                datetime(2000, 1, 1, 3, 0, tzinfo=tz1),
                datetime(2000, 6, 1, 3, 0, tzinfo=tz2),
            ],
            dtype=object,
        )

        result = to_datetime(arr, errors="coerce", utc=True, cache=cache)
        expected = DatetimeIndex(
            ["2000-01-01 08:00:00+00:00", "2000-06-01 07:00:00+00:00"],
            dtype="datetime64[ns, UTC]",
            freq=None,
        )
        tm.assert_index_equal(result, expected)

        # dtype coercion
        i = DatetimeIndex(
            ["2000-01-01 08:00:00"],
            tz=psycopg2_tz.FixedOffsetTimezone(offset=-300, name=None),
        )
        assert is_datetime64_ns_dtype(i)

        # tz coercion
        result = to_datetime(i, errors="coerce", cache=cache)
        tm.assert_index_equal(result, i)

        result = to_datetime(i, errors="coerce", utc=True, cache=cache)
        expected = DatetimeIndex(["2000-01-01 13:00:00"], dtype="datetime64[ns, UTC]")
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("arg", [True, False])
    def test_datetime_bool(self, cache, arg):
        # GH13176
        msg = r"dtype bool cannot be converted to datetime64\[ns\]"
        with pytest.raises(TypeError, match=msg):
            to_datetime(arg)
        assert to_datetime(arg, errors="coerce", cache=cache) is NaT
        assert to_datetime(arg, errors="ignore", cache=cache) is arg

    def test_datetime_bool_arrays_mixed(self, cache):
        msg = f"{type(cache)} is not convertible to datetime"
        with pytest.raises(TypeError, match=msg):
            to_datetime([False, datetime.today()], cache=cache)
        with pytest.raises(
            ValueError,
            match=(
                r'^time data "True" doesn\'t match format "%Y%m%d", '
                f"at position 1. {PARSING_ERR_MSG}$"
            ),
        ):
            to_datetime(["20130101", True], cache=cache)
        tm.assert_index_equal(
            to_datetime([0, False, NaT, 0.0], errors="coerce", cache=cache),
            DatetimeIndex(
                [to_datetime(0, cache=cache), NaT, NaT, to_datetime(0, cache=cache)]
            ),
        )

    @pytest.mark.parametrize("arg", [bool, to_datetime])
    def test_datetime_invalid_datatype(self, arg):
        # GH13176
        msg = "is not convertible to datetime"
        with pytest.raises(TypeError, match=msg):
            to_datetime(arg)

    @pytest.mark.parametrize("errors", ["coerce", "raise", "ignore"])
    def test_invalid_format_raises(self, errors):
        # https://github.com/pandas-dev/pandas/issues/50255
        with pytest.raises(
            ValueError, match="':' is a bad directive in format 'H%:M%:S%"
        ):
            to_datetime(["00:00:00"], format="H%:M%:S%", errors=errors)

    @pytest.mark.parametrize("value", ["a", "00:01:99"])
    @pytest.mark.parametrize("format", [None, "%H:%M:%S"])
    def test_datetime_invalid_scalar(self, value, format):
        # GH24763
        res = to_datetime(value, errors="ignore", format=format)
        assert res == value

        res = to_datetime(value, errors="coerce", format=format)
        assert res is NaT

        msg = "|".join(
            [
                r'^time data "a" doesn\'t match format "%H:%M:%S", at position 0. '
                f"{PARSING_ERR_MSG}$",
                r'^Given date string "a" not likely a datetime, at position 0$',
                r'^unconverted data remains when parsing with format "%H:%M:%S": "9", '
                f"at position 0. {PARSING_ERR_MSG}$",
                rf"^second must be in 0..59{NOT_99}: 00:01:99, at position 0$",
            ]
        )
        with pytest.raises(ValueError, match=msg):
            to_datetime(value, errors="raise", format=format)

    @pytest.mark.parametrize("value", ["3000/12/11 00:00:00"])
    @pytest.mark.parametrize("format", [None, "%H:%M:%S"])
    def test_datetime_outofbounds_scalar(self, value, format):
        # GH24763
        res = to_datetime(value, errors="ignore", format=format)
        assert res == value

        res = to_datetime(value, errors="coerce", format=format)
        assert res is NaT

        if format is not None:
            msg = r'^time data ".*" doesn\'t match format ".*", at position 0.'
            with pytest.raises(ValueError, match=msg):
                to_datetime(value, errors="raise", format=format)
        else:
            msg = "^Out of bounds .*, at position 0$"
            with pytest.raises(OutOfBoundsDatetime, match=msg):
                to_datetime(value, errors="raise", format=format)

    @pytest.mark.parametrize(
        ("values"), [(["a"]), (["00:01:99"]), (["a", "b", "99:00:00"])]
    )
    @pytest.mark.parametrize("format", [(None), ("%H:%M:%S")])
    def test_datetime_invalid_index(self, values, format):
        # GH24763
        # Not great to have logic in tests, but this one's hard to
        # parametrise over
        if format is None and len(values) > 1:
            warn = UserWarning
        else:
            warn = None
        with tm.assert_produces_warning(
            warn, match="Could not infer format", raise_on_extra_warnings=False
        ):
            res = to_datetime(values, errors="ignore", format=format)
        tm.assert_index_equal(
            res, Index(values, dtype="object" if format is None else "str")
        )

        with tm.assert_produces_warning(
            warn, match="Could not infer format", raise_on_extra_warnings=False
        ):
            res = to_datetime(values, errors="coerce", format=format)
        tm.assert_index_equal(res, DatetimeIndex([NaT] * len(values)))

        msg = "|".join(
            [
                r'^Given date string "a" not likely a datetime, at position 0$',
                r'^time data "a" doesn\'t match format "%H:%M:%S", at position 0. '
                f"{PARSING_ERR_MSG}$",
                r'^unconverted data remains when parsing with format "%H:%M:%S": "9", '
                f"at position 0. {PARSING_ERR_MSG}$",
                rf"^second must be in 0..59{NOT_99}: 00:01:99, at position 0$",
            ]
        )
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(
                warn, match="Could not infer format", raise_on_extra_warnings=False
            ):
                to_datetime(values, errors="raise", format=format)

    @pytest.mark.parametrize("utc", [True, None])
    @pytest.mark.parametrize("format", ["%Y%m%d %H:%M:%S", None])
    @pytest.mark.parametrize("constructor", [list, tuple, np.array, Index, deque])
    def test_to_datetime_cache(self, utc, format, constructor):
        date = "20130101 00:00:00"
        test_dates = [date] * 10**5
        data = constructor(test_dates)

        result = to_datetime(data, utc=utc, format=format, cache=True)
        expected = to_datetime(data, utc=utc, format=format, cache=False)

        tm.assert_index_equal(result, expected)

    def test_to_datetime_from_deque(self):
        # GH 29403
        result = to_datetime(deque([Timestamp("2010-06-02 09:30:00")] * 51))
        expected = to_datetime([Timestamp("2010-06-02 09:30:00")] * 51)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("utc", [True, None])
    @pytest.mark.parametrize("format", ["%Y%m%d %H:%M:%S", None])
    def test_to_datetime_cache_series(self, utc, format):
        date = "20130101 00:00:00"
        test_dates = [date] * 10**5
        data = Series(test_dates)
        result = to_datetime(data, utc=utc, format=format, cache=True)
        expected = to_datetime(data, utc=utc, format=format, cache=False)
        tm.assert_series_equal(result, expected)

    def test_to_datetime_cache_scalar(self):
        date = "20130101 00:00:00"
        result = to_datetime(date, cache=True)
        expected = Timestamp("20130101 00:00:00")
        assert result == expected

    @pytest.mark.parametrize(
        "datetimelikes,expected_values",
        (
            (
                (None, np.nan) + (NaT,) * start_caching_at,
                (NaT,) * (start_caching_at + 2),
            ),
            (
                (None, Timestamp("2012-07-26")) + (NaT,) * start_caching_at,
                (NaT, Timestamp("2012-07-26")) + (NaT,) * start_caching_at,
            ),
            (
                (None,)
                + (NaT,) * start_caching_at
                + ("2012 July 26", Timestamp("2012-07-26")),
                (NaT,) * (start_caching_at + 1)
                + (Timestamp("2012-07-26"), Timestamp("2012-07-26")),
            ),
        ),
    )
    def test_convert_object_to_datetime_with_cache(
        self, datetimelikes, expected_values
    ):
        # GH#39882
        ser = Series(
            datetimelikes,
            dtype="object",
        )
        result_series = to_datetime(ser, errors="coerce")
        expected_series = Series(
            expected_values,
            dtype="datetime64[ns]",
        )
        tm.assert_series_equal(result_series, expected_series)

    @pytest.mark.parametrize("cache", [True, False])
    @pytest.mark.parametrize(
        "input",
        [
            Series([NaT] * 20 + [None] * 20, dtype="object"),
            Series([NaT] * 60 + [None] * 60, dtype="object"),
            Series([None] * 20),
            Series([None] * 60),
            Series([""] * 20),
            Series([""] * 60),
            Series([pd.NA] * 20),
            Series([pd.NA] * 60),
            Series([np.nan] * 20),
            Series([np.nan] * 60),
        ],
    )
    def test_to_datetime_converts_null_like_to_nat(self, cache, input):
        # GH35888
        expected = Series([NaT] * len(input), dtype="M8[ns]")
        result = to_datetime(input, cache=cache)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "date, format",
        [
            ("2017-20", "%Y-%W"),
            ("20 Sunday", "%W %A"),
            ("20 Sun", "%W %a"),
            ("2017-21", "%Y-%U"),
            ("20 Sunday", "%U %A"),
            ("20 Sun", "%U %a"),
        ],
    )
    def test_week_without_day_and_calendar_year(self, date, format):
        # GH16774

        msg = "Cannot use '%W' or '%U' without day and year"
        with pytest.raises(ValueError, match=msg):
            to_datetime(date, format=format)

    def test_to_datetime_coerce(self):
        # GH 26122
        ts_strings = [
            "March 1, 2018 12:00:00+0400",
            "March 1, 2018 12:00:00+0500",
            "20100240",
        ]
        msg = "parsing datetimes with mixed time zones will raise an error"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = to_datetime(ts_strings, errors="coerce")
        expected = Index(
            [
                datetime(2018, 3, 1, 12, 0, tzinfo=tzoffset(None, 14400)),
                datetime(2018, 3, 1, 12, 0, tzinfo=tzoffset(None, 18000)),
                NaT,
            ]
        )
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "string_arg, format",
        [("March 1, 2018", "%B %d, %Y"), ("2018-03-01", "%Y-%m-%d")],
    )
    @pytest.mark.parametrize(
        "outofbounds",
        [
            datetime(9999, 1, 1),
            date(9999, 1, 1),
            np.datetime64("9999-01-01"),
            "January 1, 9999",
            "9999-01-01",
        ],
    )
    def test_to_datetime_coerce_oob(self, string_arg, format, outofbounds):
        # https://github.com/pandas-dev/pandas/issues/50255
        ts_strings = [string_arg, outofbounds]
        result = to_datetime(ts_strings, errors="coerce", format=format)
        expected = DatetimeIndex([datetime(2018, 3, 1), NaT])
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "errors, expected",
        [
            ("coerce", Index([NaT, NaT])),
            ("ignore", Index(["200622-12-31", "111111-24-11"], dtype=object)),
        ],
    )
    def test_to_datetime_malformed_no_raise(self, errors, expected):
        # GH 28299
        # GH 48633
        ts_strings = ["200622-12-31", "111111-24-11"]
        with tm.assert_produces_warning(
            UserWarning, match="Could not infer format", raise_on_extra_warnings=False
        ):
            result = to_datetime(ts_strings, errors=errors)
        tm.assert_index_equal(result, expected)

    def test_to_datetime_malformed_raise(self):
        # GH 48633
        ts_strings = ["200622-12-31", "111111-24-11"]
        msg = (
            'Parsed string "200622-12-31" gives an invalid tzoffset, which must '
            r"be between -timedelta\(hours=24\) and timedelta\(hours=24\), "
            "at position 0"
        )
        with pytest.raises(
            ValueError,
            match=msg,
        ):
            with tm.assert_produces_warning(
                UserWarning, match="Could not infer format"
            ):
                to_datetime(
                    ts_strings,
                    errors="raise",
                )

    def test_iso_8601_strings_with_same_offset(self):
        # GH 17697, 11736
        ts_str = "2015-11-18 15:30:00+05:30"
        result = to_datetime(ts_str)
        expected = Timestamp(ts_str)
        assert result == expected

        expected = DatetimeIndex([Timestamp(ts_str)] * 2)
        result = to_datetime([ts_str] * 2)
        tm.assert_index_equal(result, expected)

        result = DatetimeIndex([ts_str] * 2)
        tm.assert_index_equal(result, expected)

    def test_iso_8601_strings_with_different_offsets(self):
        # GH 17697, 11736, 50887
        ts_strings = ["2015-11-18 15:30:00+05:30", "2015-11-18 16:30:00+06:30", NaT]
        msg = "parsing datetimes with mixed time zones will raise an error"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = to_datetime(ts_strings)
        expected = np.array(
            [
                datetime(2015, 11, 18, 15, 30, tzinfo=tzoffset(None, 19800)),
                datetime(2015, 11, 18, 16, 30, tzinfo=tzoffset(None, 23400)),
                NaT,
            ],
            dtype=object,
        )
        # GH 21864
        expected = Index(expected)
        tm.assert_index_equal(result, expected)

    def test_iso_8601_strings_with_different_offsets_utc(self):
        ts_strings = ["2015-11-18 15:30:00+05:30", "2015-11-18 16:30:00+06:30", NaT]
        result = to_datetime(ts_strings, utc=True)
        expected = DatetimeIndex(
            [Timestamp(2015, 11, 18, 10), Timestamp(2015, 11, 18, 10), NaT], tz="UTC"
        )
        tm.assert_index_equal(result, expected)

    def test_mixed_offsets_with_native_datetime_raises(self):
        # GH 25978

        vals = [
            "nan",
            Timestamp("1990-01-01"),
            "2015-03-14T16:15:14.123-08:00",
            "2019-03-04T21:56:32.620-07:00",
            None,
            "today",
            "now",
        ]
        ser = Series(vals)
        assert all(ser[i] is vals[i] for i in range(len(vals)))  # GH#40111

        now = Timestamp("now")
        today = Timestamp("today")
        msg = "parsing datetimes with mixed time zones will raise an error"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            mixed = to_datetime(ser)
        expected = Series(
            [
                "NaT",
                Timestamp("1990-01-01"),
                Timestamp("2015-03-14T16:15:14.123-08:00").to_pydatetime(),
                Timestamp("2019-03-04T21:56:32.620-07:00").to_pydatetime(),
                None,
            ],
            dtype=object,
        )
        tm.assert_series_equal(mixed[:-2], expected)
        # we'll check mixed[-1] and mixed[-2] match now and today to within
        # call-timing tolerances
        assert (now - mixed.iloc[-1]).total_seconds() <= 0.1
        assert (today - mixed.iloc[-2]).total_seconds() <= 0.1

        with pytest.raises(ValueError, match="Tz-aware datetime.datetime"):
            to_datetime(mixed)

    def test_non_iso_strings_with_tz_offset(self):
        result = to_datetime(["March 1, 2018 12:00:00+0400"] * 2)
        expected = DatetimeIndex(
            [datetime(2018, 3, 1, 12, tzinfo=timezone(timedelta(minutes=240)))] * 2
        )
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "ts, expected",
        [
            (Timestamp("2018-01-01"), Timestamp("2018-01-01", tz="UTC")),
            (
                Timestamp("2018-01-01", tz="US/Pacific"),
                Timestamp("2018-01-01 08:00", tz="UTC"),
            ),
        ],
    )
    def test_timestamp_utc_true(self, ts, expected):
        # GH 24415
        result = to_datetime(ts, utc=True)
        assert result == expected

    @pytest.mark.parametrize("dt_str", ["00010101", "13000101", "30000101", "99990101"])
    def test_to_datetime_with_format_out_of_bounds(self, dt_str):
        # GH 9107
        msg = "Out of bounds nanosecond timestamp"
        with pytest.raises(OutOfBoundsDatetime, match=msg):
            to_datetime(dt_str, format="%Y%m%d")

    def test_to_datetime_utc(self):
        arr = np.array([parse("2012-06-13T01:39:00Z")], dtype=object)

        result = to_datetime(arr, utc=True)
        assert result.tz is timezone.utc

    def test_to_datetime_fixed_offset(self):
        from pandas.tests.indexes.datetimes.test_timezones import FixedOffset

        fixed_off = FixedOffset(-420, "-07:00")

        dates = [
            datetime(2000, 1, 1, tzinfo=fixed_off),
            datetime(2000, 1, 2, tzinfo=fixed_off),
            datetime(2000, 1, 3, tzinfo=fixed_off),
        ]
        result = to_datetime(dates)
        assert result.tz == fixed_off

    @pytest.mark.parametrize(
        "date",
        [
            ["2020-10-26 00:00:00+06:00", "2020-10-26 00:00:00+01:00"],
            ["2020-10-26 00:00:00+06:00", Timestamp("2018-01-01", tz="US/Pacific")],
            [
                "2020-10-26 00:00:00+06:00",
                datetime(2020, 1, 1, 18, tzinfo=pytz.timezone("Australia/Melbourne")),
            ],
        ],
    )
    def test_to_datetime_mixed_offsets_with_utc_false_deprecated(self, date):
        # GH 50887
        msg = "parsing datetimes with mixed time zones will raise an error"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            to_datetime(date, utc=False)


class TestToDatetimeUnit:
    @pytest.mark.parametrize("unit", ["Y", "M"])
    @pytest.mark.parametrize("item", [150, float(150)])
    def test_to_datetime_month_or_year_unit_int(self, cache, unit, item, request):
        # GH#50870 Note we have separate tests that pd.Timestamp gets these right
        ts = Timestamp(item, unit=unit)
        expected = DatetimeIndex([ts], dtype="M8[ns]")

        result = to_datetime([item], unit=unit, cache=cache)
        tm.assert_index_equal(result, expected)

        result = to_datetime(np.array([item], dtype=object), unit=unit, cache=cache)
        tm.assert_index_equal(result, expected)

        result = to_datetime(np.array([item]), unit=unit, cache=cache)
        tm.assert_index_equal(result, expected)

        # with a nan!
        result = to_datetime(np.array([item, np.nan]), unit=unit, cache=cache)
        assert result.isna()[1]
        tm.assert_index_equal(result[:1], expected)

    @pytest.mark.parametrize("unit", ["Y", "M"])
    def test_to_datetime_month_or_year_unit_non_round_float(self, cache, unit):
        # GH#50301
        # Match Timestamp behavior in disallowing non-round floats with
        #  Y or M unit
        warn_msg = "strings will be parsed as datetime strings"
        msg = f"Conversion of non-round float with unit={unit} is ambiguous"
        with pytest.raises(ValueError, match=msg):
            to_datetime([1.5], unit=unit, errors="raise")
        with pytest.raises(ValueError, match=msg):
            to_datetime(np.array([1.5]), unit=unit, errors="raise")
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=warn_msg):
                to_datetime(["1.5"], unit=unit, errors="raise")

        # with errors="ignore" we also end up raising within the Timestamp
        #  constructor; this may not be ideal
        with pytest.raises(ValueError, match=msg):
            to_datetime([1.5], unit=unit, errors="ignore")

        res = to_datetime([1.5], unit=unit, errors="coerce")
        expected = Index([NaT], dtype="M8[ns]")
        tm.assert_index_equal(res, expected)

        with tm.assert_produces_warning(FutureWarning, match=warn_msg):
            res = to_datetime(["1.5"], unit=unit, errors="coerce")
        tm.assert_index_equal(res, expected)

        # round floats are OK
        res = to_datetime([1.0], unit=unit)
        expected = to_datetime([1], unit=unit)
        tm.assert_index_equal(res, expected)

    def test_unit(self, cache):
        # GH 11758
        # test proper behavior with errors
        msg = "cannot specify both format and unit"
        with pytest.raises(ValueError, match=msg):
            to_datetime([1], unit="D", format="%Y%m%d", cache=cache)

    def test_unit_str(self, cache):
        # GH 57051
        # Test that strs aren't dropping precision to 32-bit accidentally.
        with tm.assert_produces_warning(FutureWarning):
            res = to_datetime(["1704660000"], unit="s", origin="unix")
        expected = to_datetime([1704660000], unit="s", origin="unix")
        tm.assert_index_equal(res, expected)

    def test_unit_array_mixed_nans(self, cache):
        values = [11111111111111111, 1, 1.0, iNaT, NaT, np.nan, "NaT", ""]
        result = to_datetime(values, unit="D", errors="ignore", cache=cache)
        expected = Index(
            [
                11111111111111111,
                Timestamp("1970-01-02"),
                Timestamp("1970-01-02"),
                NaT,
                NaT,
                NaT,
                NaT,
                NaT,
            ],
            dtype=object,
        )
        tm.assert_index_equal(result, expected)

        result = to_datetime(values, unit="D", errors="coerce", cache=cache)
        expected = DatetimeIndex(
            ["NaT", "1970-01-02", "1970-01-02", "NaT", "NaT", "NaT", "NaT", "NaT"],
            dtype="M8[ns]",
        )
        tm.assert_index_equal(result, expected)

        msg = "cannot convert input 11111111111111111 with the unit 'D'"
        with pytest.raises(OutOfBoundsDatetime, match=msg):
            to_datetime(values, unit="D", errors="raise", cache=cache)

    def test_unit_array_mixed_nans_large_int(self, cache):
        values = [1420043460000000000000000, iNaT, NaT, np.nan, "NaT"]

        result = to_datetime(values, errors="ignore", unit="s", cache=cache)
        expected = Index([1420043460000000000000000, NaT, NaT, NaT, NaT], dtype=object)
        tm.assert_index_equal(result, expected)

        result = to_datetime(values, errors="coerce", unit="s", cache=cache)
        expected = DatetimeIndex(["NaT", "NaT", "NaT", "NaT", "NaT"], dtype="M8[ns]")
        tm.assert_index_equal(result, expected)

        msg = "cannot convert input 1420043460000000000000000 with the unit 's'"
        with pytest.raises(OutOfBoundsDatetime, match=msg):
            to_datetime(values, errors="raise", unit="s", cache=cache)

    def test_to_datetime_invalid_str_not_out_of_bounds_valuerror(self, cache):
        # if we have a string, then we raise a ValueError
        # and NOT an OutOfBoundsDatetime
        msg = "non convertible value foo with the unit 's'"
        with pytest.raises(ValueError, match=msg):
            to_datetime("foo", errors="raise", unit="s", cache=cache)

    @pytest.mark.parametrize("error", ["raise", "coerce", "ignore"])
    def test_unit_consistency(self, cache, error):
        # consistency of conversions
        expected = Timestamp("1970-05-09 14:25:11")
        result = to_datetime(11111111, unit="s", errors=error, cache=cache)
        assert result == expected
        assert isinstance(result, Timestamp)

    @pytest.mark.parametrize("errors", ["ignore", "raise", "coerce"])
    @pytest.mark.parametrize("dtype", ["float64", "int64"])
    def test_unit_with_numeric(self, cache, errors, dtype):
        # GH 13180
        # coercions from floats/ints are ok
        expected = DatetimeIndex(
            ["2015-06-19 05:33:20", "2015-05-27 22:33:20"], dtype="M8[ns]"
        )
        arr = np.array([1.434692e18, 1.432766e18]).astype(dtype)
        result = to_datetime(arr, errors=errors, cache=cache)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "exp, arr, warning",
        [
            [
                ["NaT", "2015-06-19 05:33:20", "2015-05-27 22:33:20"],
                ["foo", 1.434692e18, 1.432766e18],
                UserWarning,
            ],
            [
                ["2015-06-19 05:33:20", "2015-05-27 22:33:20", "NaT", "NaT"],
                [1.434692e18, 1.432766e18, "foo", "NaT"],
                None,
            ],
        ],
    )
    def test_unit_with_numeric_coerce(self, cache, exp, arr, warning):
        # but we want to make sure that we are coercing
        # if we have ints/strings
        expected = DatetimeIndex(exp, dtype="M8[ns]")
        with tm.assert_produces_warning(warning, match="Could not infer format"):
            result = to_datetime(arr, errors="coerce", cache=cache)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "arr",
        [
            [Timestamp("20130101"), 1.434692e18, 1.432766e18],
            [1.434692e18, 1.432766e18, Timestamp("20130101")],
        ],
    )
    def test_unit_mixed(self, cache, arr):
        # GH#50453 pre-2.0 with mixed numeric/datetimes and errors="coerce"
        #  the numeric entries would be coerced to NaT, was never clear exactly
        #  why.
        # mixed integers/datetimes
        expected = Index([Timestamp(x) for x in arr], dtype="M8[ns]")
        result = to_datetime(arr, errors="coerce", cache=cache)
        tm.assert_index_equal(result, expected)

        # GH#49037 pre-2.0 this raised, but it always worked with Series,
        #  was never clear why it was disallowed
        result = to_datetime(arr, errors="raise", cache=cache)
        tm.assert_index_equal(result, expected)

        result = DatetimeIndex(arr)
        tm.assert_index_equal(result, expected)

    def test_unit_rounding(self, cache):
        # GH 14156 & GH 20445: argument will incur floating point errors
        # but no premature rounding
        value = 1434743731.8770001
        result = to_datetime(value, unit="s", cache=cache)
        expected = Timestamp("2015-06-19 19:55:31.877000093")
        assert result == expected

        alt = Timestamp(value, unit="s")
        assert alt == result

    def test_unit_ignore_keeps_name(self, cache):
        # GH 21697
        expected = Index([15e9] * 2, name="name")
        result = to_datetime(expected, errors="ignore", unit="s", cache=cache)
        tm.assert_index_equal(result, expected)

    def test_to_datetime_errors_ignore_utc_true(self):
        # GH#23758
        result = to_datetime([1], unit="s", utc=True, errors="ignore")
        expected = DatetimeIndex(["1970-01-01 00:00:01"], dtype="M8[ns, UTC]")
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("dtype", [int, float])
    def test_to_datetime_unit(self, dtype):
        epoch = 1370745748
        ser = Series([epoch + t for t in range(20)]).astype(dtype)
        result = to_datetime(ser, unit="s")
        expected = Series(
            [
                Timestamp("2013-06-09 02:42:28") + timedelta(seconds=t)
                for t in range(20)
            ],
            dtype="M8[ns]",
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("null", [iNaT, np.nan])
    def test_to_datetime_unit_with_nulls(self, null):
        epoch = 1370745748
        ser = Series([epoch + t for t in range(20)] + [null])
        result = to_datetime(ser, unit="s")
        expected = Series(
            [Timestamp("2013-06-09 02:42:28") + timedelta(seconds=t) for t in range(20)]
            + [NaT],
            dtype="M8[ns]",
        )
        tm.assert_series_equal(result, expected)

    def test_to_datetime_unit_fractional_seconds(self):
        # GH13834
        epoch = 1370745748
        ser = Series([epoch + t for t in np.arange(0, 2, 0.25)] + [iNaT]).astype(float)
        result = to_datetime(ser, unit="s")
        expected = Series(
            [
                Timestamp("2013-06-09 02:42:28") + timedelta(seconds=t)
                for t in np.arange(0, 2, 0.25)
            ]
            + [NaT],
            dtype="M8[ns]",
        )
        # GH20455 argument will incur floating point errors but no premature rounding
        result = result.round("ms")
        tm.assert_series_equal(result, expected)

    def test_to_datetime_unit_na_values(self):
        result = to_datetime([1, 2, "NaT", NaT, np.nan], unit="D")
        expected = DatetimeIndex(
            [Timestamp("1970-01-02"), Timestamp("1970-01-03")] + ["NaT"] * 3,
            dtype="M8[ns]",
        )
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("bad_val", ["foo", 111111111])
    def test_to_datetime_unit_invalid(self, bad_val):
        msg = f"{bad_val} with the unit 'D'"
        with pytest.raises(ValueError, match=msg):
            to_datetime([1, 2, bad_val], unit="D")

    @pytest.mark.parametrize("bad_val", ["foo", 111111111])
    def test_to_timestamp_unit_coerce(self, bad_val):
        # coerce we can process
        expected = DatetimeIndex(
            [Timestamp("1970-01-02"), Timestamp("1970-01-03")] + ["NaT"] * 1,
            dtype="M8[ns]",
        )
        result = to_datetime([1, 2, bad_val], unit="D", errors="coerce")
        tm.assert_index_equal(result, expected)

    def test_float_to_datetime_raise_near_bounds(self):
        # GH50183
        msg = "cannot convert input with unit 'D'"
        oneday_in_ns = 1e9 * 60 * 60 * 24
        tsmax_in_days = 2**63 / oneday_in_ns  # 2**63 ns, in days
        # just in bounds
        should_succeed = Series(
            [0, tsmax_in_days - 0.005, -tsmax_in_days + 0.005], dtype=float
        )
        expected = (should_succeed * oneday_in_ns).astype(np.int64)
        for error_mode in ["raise", "coerce", "ignore"]:
            result1 = to_datetime(should_succeed, unit="D", errors=error_mode)
            # Cast to `np.float64` so that `rtol` and inexact checking kick in
            # (`check_exact` doesn't take place for integer dtypes)
            tm.assert_almost_equal(
                result1.astype(np.int64).astype(np.float64),
                expected.astype(np.float64),
                rtol=1e-10,
            )
        # just out of bounds
        should_fail1 = Series([0, tsmax_in_days + 0.005], dtype=float)
        should_fail2 = Series([0, -tsmax_in_days - 0.005], dtype=float)
        with pytest.raises(OutOfBoundsDatetime, match=msg):
            to_datetime(should_fail1, unit="D", errors="raise")
        with pytest.raises(OutOfBoundsDatetime, match=msg):
            to_datetime(should_fail2, unit="D", errors="raise")


class TestToDatetimeDataFrame:
    @pytest.fixture
    def df(self):
        return DataFrame(
            {
                "year": [2015, 2016],
                "month": [2, 3],
                "day": [4, 5],
                "hour": [6, 7],
                "minute": [58, 59],
                "second": [10, 11],
                "ms": [1, 1],
                "us": [2, 2],
                "ns": [3, 3],
            }
        )

    def test_dataframe(self, df, cache):
        result = to_datetime(
            {"year": df["year"], "month": df["month"], "day": df["day"]}, cache=cache
        )
        expected = Series(
            [Timestamp("20150204 00:00:00"), Timestamp("20160305 00:0:00")]
        )
        tm.assert_series_equal(result, expected)

        # dict-like
        result = to_datetime(df[["year", "month", "day"]].to_dict(), cache=cache)
        tm.assert_series_equal(result, expected)

    def test_dataframe_dict_with_constructable(self, df, cache):
        # dict but with constructable
        df2 = df[["year", "month", "day"]].to_dict()
        df2["month"] = 2
        result = to_datetime(df2, cache=cache)
        expected2 = Series(
            [Timestamp("20150204 00:00:00"), Timestamp("20160205 00:0:00")]
        )
        tm.assert_series_equal(result, expected2)

    @pytest.mark.parametrize(
        "unit",
        [
            {
                "year": "years",
                "month": "months",
                "day": "days",
                "hour": "hours",
                "minute": "minutes",
                "second": "seconds",
            },
            {
                "year": "year",
                "month": "month",
                "day": "day",
                "hour": "hour",
                "minute": "minute",
                "second": "second",
            },
        ],
    )
    def test_dataframe_field_aliases_column_subset(self, df, cache, unit):
        # unit mappings
        result = to_datetime(df[list(unit.keys())].rename(columns=unit), cache=cache)
        expected = Series(
            [Timestamp("20150204 06:58:10"), Timestamp("20160305 07:59:11")],
            dtype="M8[ns]",
        )
        tm.assert_series_equal(result, expected)

    def test_dataframe_field_aliases(self, df, cache):
        d = {
            "year": "year",
            "month": "month",
            "day": "day",
            "hour": "hour",
            "minute": "minute",
            "second": "second",
            "ms": "ms",
            "us": "us",
            "ns": "ns",
        }

        result = to_datetime(df.rename(columns=d), cache=cache)
        expected = Series(
            [
                Timestamp("20150204 06:58:10.001002003"),
                Timestamp("20160305 07:59:11.001002003"),
            ]
        )
        tm.assert_series_equal(result, expected)

    def test_dataframe_str_dtype(self, df, cache):
        # coerce back to int
        result = to_datetime(df.astype(str), cache=cache)
        expected = Series(
            [
                Timestamp("20150204 06:58:10.001002003"),
                Timestamp("20160305 07:59:11.001002003"),
            ]
        )
        tm.assert_series_equal(result, expected)

    def test_dataframe_coerce(self, cache):
        # passing coerce
        df2 = DataFrame({"year": [2015, 2016], "month": [2, 20], "day": [4, 5]})

        msg = (
            r'^cannot assemble the datetimes: time data ".+" doesn\'t '
            r'match format "%Y%m%d", at position 1\.'
        )
        with pytest.raises(ValueError, match=msg):
            to_datetime(df2, cache=cache)

        result = to_datetime(df2, errors="coerce", cache=cache)
        expected = Series([Timestamp("20150204 00:00:00"), NaT])
        tm.assert_series_equal(result, expected)

    def test_dataframe_extra_keys_raisesm(self, df, cache):
        # extra columns
        msg = r"extra keys have been passed to the datetime assemblage: \[foo\]"
        with pytest.raises(ValueError, match=msg):
            df2 = df.copy()
            df2["foo"] = 1
            to_datetime(df2, cache=cache)

    @pytest.mark.parametrize(
        "cols",
        [
            ["year"],
            ["year", "month"],
            ["year", "month", "second"],
            ["month", "day"],
            ["year", "day", "second"],
        ],
    )
    def test_dataframe_missing_keys_raises(self, df, cache, cols):
        # not enough
        msg = (
            r"to assemble mappings requires at least that \[year, month, "
            r"day\] be specified: \[.+\] is missing"
        )
        with pytest.raises(ValueError, match=msg):
            to_datetime(df[cols], cache=cache)

    def test_dataframe_duplicate_columns_raises(self, cache):
        # duplicates
        msg = "cannot assemble with duplicate keys"
        df2 = DataFrame({"year": [2015, 2016], "month": [2, 20], "day": [4, 5]})
        df2.columns = ["year", "year", "day"]
        with pytest.raises(ValueError, match=msg):
            to_datetime(df2, cache=cache)

        df2 = DataFrame(
            {"year": [2015, 2016], "month": [2, 20], "day": [4, 5], "hour": [4, 5]}
        )
        df2.columns = ["year", "month", "day", "day"]
        with pytest.raises(ValueError, match=msg):
            to_datetime(df2, cache=cache)

    def test_dataframe_int16(self, cache):
        # GH#13451
        df = DataFrame({"year": [2015, 2016], "month": [2, 3], "day": [4, 5]})

        # int16
        result = to_datetime(df.astype("int16"), cache=cache)
        expected = Series(
            [Timestamp("20150204 00:00:00"), Timestamp("20160305 00:00:00")]
        )
        tm.assert_series_equal(result, expected)

    def test_dataframe_mixed(self, cache):
        # mixed dtypes
        df = DataFrame({"year": [2015, 2016], "month": [2, 3], "day": [4, 5]})
        df["month"] = df["month"].astype("int8")
        df["day"] = df["day"].astype("int8")
        result = to_datetime(df, cache=cache)
        expected = Series(
            [Timestamp("20150204 00:00:00"), Timestamp("20160305 00:00:00")]
        )
        tm.assert_series_equal(result, expected)

    def test_dataframe_float(self, cache):
        # float
        df = DataFrame({"year": [2000, 2001], "month": [1.5, 1], "day": [1, 1]})
        msg = (
            r"^cannot assemble the datetimes: unconverted data remains when parsing "
            r'with format ".*": "1", at position 0.'
        )
        with pytest.raises(ValueError, match=msg):
            to_datetime(df, cache=cache)

    def test_dataframe_utc_true(self):
        # GH#23760
        df = DataFrame({"year": [2015, 2016], "month": [2, 3], "day": [4, 5]})
        result = to_datetime(df, utc=True)
        expected = Series(
            np.array(["2015-02-04", "2016-03-05"], dtype="datetime64[ns]")
        ).dt.tz_localize("UTC")
        tm.assert_series_equal(result, expected)


class TestToDatetimeMisc:
    def test_to_datetime_barely_out_of_bounds(self):
        # GH#19529
        # GH#19382 close enough to bounds that dropping nanos would result
        # in an in-bounds datetime
        arr = np.array(["2262-04-11 23:47:16.854775808"], dtype=object)

        msg = "^Out of bounds nanosecond timestamp: .*, at position 0"
        with pytest.raises(OutOfBoundsDatetime, match=msg):
            to_datetime(arr)

    @pytest.mark.parametrize(
        "arg, exp_str",
        [
            ["2012-01-01 00:00:00", "2012-01-01 00:00:00"],
            ["20121001", "2012-10-01"],  # bad iso 8601
        ],
    )
    def test_to_datetime_iso8601(self, cache, arg, exp_str):
        result = to_datetime([arg], cache=cache)
        exp = Timestamp(exp_str)
        assert result[0] == exp

    @pytest.mark.parametrize(
        "input, format",
        [
            ("2012", "%Y-%m"),
            ("2012-01", "%Y-%m-%d"),
            ("2012-01-01", "%Y-%m-%d %H"),
            ("2012-01-01 10", "%Y-%m-%d %H:%M"),
            ("2012-01-01 10:00", "%Y-%m-%d %H:%M:%S"),
            ("2012-01-01 10:00:00", "%Y-%m-%d %H:%M:%S.%f"),
            ("2012-01-01 10:00:00.123", "%Y-%m-%d %H:%M:%S.%f%z"),
            (0, "%Y-%m-%d"),
        ],
    )
    @pytest.mark.parametrize("exact", [True, False])
    def test_to_datetime_iso8601_fails(self, input, format, exact):
        # https://github.com/pandas-dev/pandas/issues/12649
        # `format` is longer than the string, so this fails regardless of `exact`
        with pytest.raises(
            ValueError,
            match=(
                rf"time data \"{input}\" doesn't match format "
                rf"\"{format}\", at position 0"
            ),
        ):
            to_datetime(input, format=format, exact=exact)

    @pytest.mark.parametrize(
        "input, format",
        [
            ("2012-01-01", "%Y-%m"),
            ("2012-01-01 10", "%Y-%m-%d"),
            ("2012-01-01 10:00", "%Y-%m-%d %H"),
            ("2012-01-01 10:00:00", "%Y-%m-%d %H:%M"),
            (0, "%Y-%m-%d"),
        ],
    )
    def test_to_datetime_iso8601_exact_fails(self, input, format):
        # https://github.com/pandas-dev/pandas/issues/12649
        # `format` is shorter than the date string, so only fails with `exact=True`
        msg = "|".join(
            [
                '^unconverted data remains when parsing with format ".*": ".*"'
                f", at position 0. {PARSING_ERR_MSG}$",
                f'^time data ".*" doesn\'t match format ".*", at position 0. '
                f"{PARSING_ERR_MSG}$",
            ]
        )
        with pytest.raises(
            ValueError,
            match=(msg),
        ):
            to_datetime(input, format=format)

    @pytest.mark.parametrize(
        "input, format",
        [
            ("2012-01-01", "%Y-%m"),
            ("2012-01-01 00", "%Y-%m-%d"),
            ("2012-01-01 00:00", "%Y-%m-%d %H"),
            ("2012-01-01 00:00:00", "%Y-%m-%d %H:%M"),
        ],
    )
    def test_to_datetime_iso8601_non_exact(self, input, format):
        # https://github.com/pandas-dev/pandas/issues/12649
        expected = Timestamp(2012, 1, 1)
        result = to_datetime(input, format=format, exact=False)
        assert result == expected

    @pytest.mark.parametrize(
        "input, format",
        [
            ("2020-01", "%Y/%m"),
            ("2020-01-01", "%Y/%m/%d"),
            ("2020-01-01 00", "%Y/%m/%dT%H"),
            ("2020-01-01T00", "%Y/%m/%d %H"),
            ("2020-01-01 00:00", "%Y/%m/%dT%H:%M"),
            ("2020-01-01T00:00", "%Y/%m/%d %H:%M"),
            ("2020-01-01 00:00:00", "%Y/%m/%dT%H:%M:%S"),
            ("2020-01-01T00:00:00", "%Y/%m/%d %H:%M:%S"),
        ],
    )
    def test_to_datetime_iso8601_separator(self, input, format):
        # https://github.com/pandas-dev/pandas/issues/12649
        with pytest.raises(
            ValueError,
            match=(
                rf"time data \"{input}\" doesn\'t match format "
                rf"\"{format}\", at position 0"
            ),
        ):
            to_datetime(input, format=format)

    @pytest.mark.parametrize(
        "input, format",
        [
            ("2020-01", "%Y-%m"),
            ("2020-01-01", "%Y-%m-%d"),
            ("2020-01-01 00", "%Y-%m-%d %H"),
            ("2020-01-01T00", "%Y-%m-%dT%H"),
            ("2020-01-01 00:00", "%Y-%m-%d %H:%M"),
            ("2020-01-01T00:00", "%Y-%m-%dT%H:%M"),
            ("2020-01-01 00:00:00", "%Y-%m-%d %H:%M:%S"),
            ("2020-01-01T00:00:00", "%Y-%m-%dT%H:%M:%S"),
            ("2020-01-01T00:00:00.000", "%Y-%m-%dT%H:%M:%S.%f"),
            ("2020-01-01T00:00:00.000000", "%Y-%m-%dT%H:%M:%S.%f"),
            ("2020-01-01T00:00:00.000000000", "%Y-%m-%dT%H:%M:%S.%f"),
        ],
    )
    def test_to_datetime_iso8601_valid(self, input, format):
        # https://github.com/pandas-dev/pandas/issues/12649
        expected = Timestamp(2020, 1, 1)
        result = to_datetime(input, format=format)
        assert result == expected

    @pytest.mark.parametrize(
        "input, format",
        [
            ("2020-1", "%Y-%m"),
            ("2020-1-1", "%Y-%m-%d"),
            ("2020-1-1 0", "%Y-%m-%d %H"),
            ("2020-1-1T0", "%Y-%m-%dT%H"),
            ("2020-1-1 0:0", "%Y-%m-%d %H:%M"),
            ("2020-1-1T0:0", "%Y-%m-%dT%H:%M"),
            ("2020-1-1 0:0:0", "%Y-%m-%d %H:%M:%S"),
            ("2020-1-1T0:0:0", "%Y-%m-%dT%H:%M:%S"),
            ("2020-1-1T0:0:0.000", "%Y-%m-%dT%H:%M:%S.%f"),
            ("2020-1-1T0:0:0.000000", "%Y-%m-%dT%H:%M:%S.%f"),
            ("2020-1-1T0:0:0.000000000", "%Y-%m-%dT%H:%M:%S.%f"),
        ],
    )
    def test_to_datetime_iso8601_non_padded(self, input, format):
        # https://github.com/pandas-dev/pandas/issues/21422
        expected = Timestamp(2020, 1, 1)
        result = to_datetime(input, format=format)
        assert result == expected

    @pytest.mark.parametrize(
        "input, format",
        [
            ("2020-01-01T00:00:00.000000000+00:00", "%Y-%m-%dT%H:%M:%S.%f%z"),
            ("2020-01-01T00:00:00+00:00", "%Y-%m-%dT%H:%M:%S%z"),
            ("2020-01-01T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z"),
        ],
    )
    def test_to_datetime_iso8601_with_timezone_valid(self, input, format):
        # https://github.com/pandas-dev/pandas/issues/12649
        expected = Timestamp(2020, 1, 1, tzinfo=pytz.UTC)
        result = to_datetime(input, format=format)
        assert result == expected

    def test_to_datetime_default(self, cache):
        rs = to_datetime("2001", cache=cache)
        xp = datetime(2001, 1, 1)
        assert rs == xp

    @pytest.mark.xfail(reason="fails to enforce dayfirst=True, which would raise")
    def test_to_datetime_respects_dayfirst(self, cache):
        # dayfirst is essentially broken

        # The msg here is not important since it isn't actually raised yet.
        msg = "Invalid date specified"
        with pytest.raises(ValueError, match=msg):
            # if dayfirst is respected, then this would parse as month=13, which
            #  would raise
            with tm.assert_produces_warning(UserWarning, match="Provide format"):
                to_datetime("01-13-2012", dayfirst=True, cache=cache)

    def test_to_datetime_on_datetime64_series(self, cache):
        # #2699
        ser = Series(date_range("1/1/2000", periods=10))

        result = to_datetime(ser, cache=cache)
        assert result[0] == ser[0]

    def test_to_datetime_with_space_in_series(self, cache):
        # GH 6428
        ser = Series(["10/18/2006", "10/18/2008", " "])
        msg = (
            r'^time data " " doesn\'t match format "%m/%d/%Y", '
            rf"at position 2. {PARSING_ERR_MSG}$"
        )
        with pytest.raises(ValueError, match=msg):
            to_datetime(ser, errors="raise", cache=cache)
        result_coerce = to_datetime(ser, errors="coerce", cache=cache)
        expected_coerce = Series([datetime(2006, 10, 18), datetime(2008, 10, 18), NaT])
        tm.assert_series_equal(result_coerce, expected_coerce)
        result_ignore = to_datetime(ser, errors="ignore", cache=cache)
        tm.assert_series_equal(result_ignore, ser)

    @td.skip_if_not_us_locale
    def test_to_datetime_with_apply(self, cache):
        # this is only locale tested with US/None locales
        # GH 5195
        # with a format and coerce a single item to_datetime fails
        td = Series(["May 04", "Jun 02", "Dec 11"], index=[1, 2, 3])
        expected = to_datetime(td, format="%b %y", cache=cache)
        result = td.apply(to_datetime, format="%b %y", cache=cache)
        tm.assert_series_equal(result, expected)

    def test_to_datetime_timezone_name(self):
        # https://github.com/pandas-dev/pandas/issues/49748
        result = to_datetime("2020-01-01 00:00:00UTC", format="%Y-%m-%d %H:%M:%S%Z")
        expected = Timestamp(2020, 1, 1).tz_localize("UTC")
        assert result == expected

    @td.skip_if_not_us_locale
    @pytest.mark.parametrize("errors", ["raise", "coerce", "ignore"])
    def test_to_datetime_with_apply_with_empty_str(self, cache, errors):
        # this is only locale tested with US/None locales
        # GH 5195, GH50251
        # with a format and coerce a single item to_datetime fails
        td = Series(["May 04", "Jun 02", ""], index=[1, 2, 3])
        expected = to_datetime(td, format="%b %y", errors=errors, cache=cache)

        result = td.apply(
            lambda x: to_datetime(x, format="%b %y", errors="coerce", cache=cache)
        )
        tm.assert_series_equal(result, expected)

    def test_to_datetime_empty_stt(self, cache):
        # empty string
        result = to_datetime("", cache=cache)
        assert result is NaT

    def test_to_datetime_empty_str_list(self, cache):
        result = to_datetime(["", ""], cache=cache)
        assert isna(result).all()

    def test_to_datetime_zero(self, cache):
        # ints
        result = Timestamp(0)
        expected = to_datetime(0, cache=cache)
        assert result == expected

    def test_to_datetime_strings(self, cache):
        # GH 3888 (strings)
        expected = to_datetime(["2012"], cache=cache)[0]
        result = to_datetime("2012", cache=cache)
        assert result == expected

    def test_to_datetime_strings_variation(self, cache):
        array = ["2012", "20120101", "20120101 12:01:01"]
        expected = [to_datetime(dt_str, cache=cache) for dt_str in array]
        result = [Timestamp(date_str) for date_str in array]
        tm.assert_almost_equal(result, expected)

    @pytest.mark.parametrize("result", [Timestamp("2012"), to_datetime("2012")])
    def test_to_datetime_strings_vs_constructor(self, result):
        expected = Timestamp(2012, 1, 1)
        assert result == expected

    def test_to_datetime_unprocessable_input(self, cache):
        # GH 4928
        # GH 21864
        result = to_datetime([1, "1"], errors="ignore", cache=cache)

        expected = Index(np.array([1, "1"], dtype="O"))
        tm.assert_equal(result, expected)
        msg = '^Given date string "1" not likely a datetime, at position 1$'
        with pytest.raises(ValueError, match=msg):
            to_datetime([1, "1"], errors="raise", cache=cache)

    def test_to_datetime_unhashable_input(self, cache):
        series = Series([["a"]] * 100)
        result = to_datetime(series, errors="ignore", cache=cache)
        tm.assert_series_equal(series, result)

    def test_to_datetime_other_datetime64_units(self):
        # 5/25/2012
        scalar = np.int64(1337904000000000).view("M8[us]")
        as_obj = scalar.astype("O")

        index = DatetimeIndex([scalar])
        assert index[0] == scalar.astype("O")

        value = Timestamp(scalar)
        assert value == as_obj

    def test_to_datetime_list_of_integers(self):
        rng = date_range("1/1/2000", periods=20)
        rng = DatetimeIndex(rng.values)

        ints = list(rng.asi8)

        result = DatetimeIndex(ints)

        tm.assert_index_equal(rng, result)

    def test_to_datetime_overflow(self):
        # gh-17637
        # we are overflowing Timedelta range here
        msg = "Cannot cast 139999 days 00:00:00 to unit='ns' without overflow"
        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            date_range(start="1/1/1700", freq="B", periods=100000)

    def test_string_invalid_operation(self, cache):
        invalid = np.array(["87156549591102612381000001219H5"], dtype=object)
        # GH #51084

        with pytest.raises(ValueError, match="Unknown datetime string format"):
            to_datetime(invalid, errors="raise", cache=cache)

    def test_string_na_nat_conversion(self, cache):
        # GH #999, #858

        strings = np.array(["1/1/2000", "1/2/2000", np.nan, "1/4/2000"], dtype=object)

        expected = np.empty(4, dtype="M8[ns]")
        for i, val in enumerate(strings):
            if isna(val):
                expected[i] = iNaT
            else:
                expected[i] = parse(val)

        result = tslib.array_to_datetime(strings)[0]
        tm.assert_almost_equal(result, expected)

        result2 = to_datetime(strings, cache=cache)
        assert isinstance(result2, DatetimeIndex)
        tm.assert_numpy_array_equal(result, result2.values)

    def test_string_na_nat_conversion_malformed(self, cache):
        malformed = np.array(["1/100/2000", np.nan], dtype=object)

        # GH 10636, default is now 'raise'
        msg = r"Unknown datetime string format"
        with pytest.raises(ValueError, match=msg):
            to_datetime(malformed, errors="raise", cache=cache)

        result = to_datetime(malformed, errors="ignore", cache=cache)
        # GH 21864
        expected = Index(malformed, dtype=object)
        tm.assert_index_equal(result, expected)

        with pytest.raises(ValueError, match=msg):
            to_datetime(malformed, errors="raise", cache=cache)

    def test_string_na_nat_conversion_with_name(self, cache):
        idx = ["a", "b", "c", "d", "e"]
        series = Series(
            ["1/1/2000", np.nan, "1/3/2000", np.nan, "1/5/2000"], index=idx, name="foo"
        )
        dseries = Series(
            [
                to_datetime("1/1/2000", cache=cache),
                np.nan,
                to_datetime("1/3/2000", cache=cache),
                np.nan,
                to_datetime("1/5/2000", cache=cache),
            ],
            index=idx,
            name="foo",
        )

        result = to_datetime(series, cache=cache)
        dresult = to_datetime(dseries, cache=cache)

        expected = Series(np.empty(5, dtype="M8[ns]"), index=idx)
        for i in range(5):
            x = series.iloc[i]
            if isna(x):
                expected.iloc[i] = NaT
            else:
                expected.iloc[i] = to_datetime(x, cache=cache)

        tm.assert_series_equal(result, expected, check_names=False)
        assert result.name == "foo"

        tm.assert_series_equal(dresult, expected, check_names=False)
        assert dresult.name == "foo"

    @pytest.mark.parametrize(
        "unit",
        ["h", "m", "s", "ms", "us", "ns"],
    )
    def test_dti_constructor_numpy_timeunits(self, cache, unit):
        # GH 9114
        dtype = np.dtype(f"M8[{unit}]")
        base = to_datetime(["2000-01-01T00:00", "2000-01-02T00:00", "NaT"], cache=cache)

        values = base.values.astype(dtype)

        if unit in ["h", "m"]:
            # we cast to closest supported unit
            unit = "s"
        exp_dtype = np.dtype(f"M8[{unit}]")
        expected = DatetimeIndex(base.astype(exp_dtype))
        assert expected.dtype == exp_dtype

        tm.assert_index_equal(DatetimeIndex(values), expected)
        tm.assert_index_equal(to_datetime(values, cache=cache), expected)

    def test_dayfirst(self, cache):
        # GH 5917
        arr = ["10/02/2014", "11/02/2014", "12/02/2014"]
        expected = DatetimeIndex(
            [datetime(2014, 2, 10), datetime(2014, 2, 11), datetime(2014, 2, 12)]
        )
        idx1 = DatetimeIndex(arr, dayfirst=True)
        idx2 = DatetimeIndex(np.array(arr), dayfirst=True)
        idx3 = to_datetime(arr, dayfirst=True, cache=cache)
        idx4 = to_datetime(np.array(arr), dayfirst=True, cache=cache)
        idx5 = DatetimeIndex(Index(arr), dayfirst=True)
        idx6 = DatetimeIndex(Series(arr), dayfirst=True)
        tm.assert_index_equal(expected, idx1)
        tm.assert_index_equal(expected, idx2)
        tm.assert_index_equal(expected, idx3)
        tm.assert_index_equal(expected, idx4)
        tm.assert_index_equal(expected, idx5)
        tm.assert_index_equal(expected, idx6)

    def test_dayfirst_warnings_valid_input(self):
        # GH 12585
        warning_msg = (
            "Parsing dates in .* format when dayfirst=.* was specified. "
            "Pass `dayfirst=.*` or specify a format to silence this warning."
        )

        # CASE 1: valid input
        arr = ["31/12/2014", "10/03/2011"]
        expected = DatetimeIndex(
            ["2014-12-31", "2011-03-10"], dtype="datetime64[ns]", freq=None
        )

        # A. dayfirst arg correct, no warning
        res1 = to_datetime(arr, dayfirst=True)
        tm.assert_index_equal(expected, res1)

        # B. dayfirst arg incorrect, warning
        with tm.assert_produces_warning(UserWarning, match=warning_msg):
            res2 = to_datetime(arr, dayfirst=False)
        tm.assert_index_equal(expected, res2)

    def test_dayfirst_warnings_invalid_input(self):
        # CASE 2: invalid input
        # cannot consistently process with single format
        # ValueError *always* raised

        # first in DD/MM/YYYY, second in MM/DD/YYYY
        arr = ["31/12/2014", "03/30/2011"]

        with pytest.raises(
            ValueError,
            match=(
                r'^time data "03/30/2011" doesn\'t match format '
                rf'"%d/%m/%Y", at position 1. {PARSING_ERR_MSG}$'
            ),
        ):
            to_datetime(arr, dayfirst=True)

    @pytest.mark.parametrize("klass", [DatetimeIndex, DatetimeArray._from_sequence])
    def test_to_datetime_dta_tz(self, klass):
        # GH#27733
        dti = date_range("2015-04-05", periods=3).rename("foo")
        expected = dti.tz_localize("UTC")

        obj = klass(dti)
        expected = klass(expected)

        result = to_datetime(obj, utc=True)
        tm.assert_equal(result, expected)


class TestGuessDatetimeFormat:
    @pytest.mark.parametrize(
        "test_list",
        [
            [
                "2011-12-30 00:00:00.000000",
                "2011-12-30 00:00:00.000000",
                "2011-12-30 00:00:00.000000",
            ],
            [np.nan, np.nan, "2011-12-30 00:00:00.000000"],
            ["", "2011-12-30 00:00:00.000000"],
            ["NaT", "2011-12-30 00:00:00.000000"],
            ["2011-12-30 00:00:00.000000", "random_string"],
            ["now", "2011-12-30 00:00:00.000000"],
            ["today", "2011-12-30 00:00:00.000000"],
        ],
    )
    def test_guess_datetime_format_for_array(self, test_list):
        expected_format = "%Y-%m-%d %H:%M:%S.%f"
        test_array = np.array(test_list, dtype=object)
        assert tools._guess_datetime_format_for_array(test_array) == expected_format

    @td.skip_if_not_us_locale
    def test_guess_datetime_format_for_array_all_nans(self):
        format_for_string_of_nans = tools._guess_datetime_format_for_array(
            np.array([np.nan, np.nan, np.nan], dtype="O")
        )
        assert format_for_string_of_nans is None


class TestToDatetimeInferFormat:
    @pytest.mark.parametrize(
        "test_format", ["%m-%d-%Y", "%m/%d/%Y %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f"]
    )
    def test_to_datetime_infer_datetime_format_consistent_format(
        self, cache, test_format
    ):
        ser = Series(date_range("20000101", periods=50, freq="h"))

        s_as_dt_strings = ser.apply(lambda x: x.strftime(test_format))

        with_format = to_datetime(s_as_dt_strings, format=test_format, cache=cache)
        without_format = to_datetime(s_as_dt_strings, cache=cache)

        # Whether the format is explicitly passed, or
        # it is inferred, the results should all be the same
        tm.assert_series_equal(with_format, without_format)

    def test_to_datetime_inconsistent_format(self, cache):
        data = ["01/01/2011 00:00:00", "01-02-2011 00:00:00", "2011-01-03T00:00:00"]
        ser = Series(np.array(data))
        msg = (
            r'^time data "01-02-2011 00:00:00" doesn\'t match format '
            rf'"%m/%d/%Y %H:%M:%S", at position 1. {PARSING_ERR_MSG}$'
        )
        with pytest.raises(ValueError, match=msg):
            to_datetime(ser, cache=cache)

    def test_to_datetime_consistent_format(self, cache):
        data = ["Jan/01/2011", "Feb/01/2011", "Mar/01/2011"]
        ser = Series(np.array(data))
        result = to_datetime(ser, cache=cache)
        expected = Series(
            ["2011-01-01", "2011-02-01", "2011-03-01"], dtype="datetime64[ns]"
        )
        tm.assert_series_equal(result, expected)

    def test_to_datetime_series_with_nans(self, cache):
        ser = Series(
            np.array(
                ["01/01/2011 00:00:00", np.nan, "01/03/2011 00:00:00", np.nan],
                dtype=object,
            )
        )
        result = to_datetime(ser, cache=cache)
        expected = Series(
            ["2011-01-01", NaT, "2011-01-03", NaT], dtype="datetime64[ns]"
        )
        tm.assert_series_equal(result, expected)

    def test_to_datetime_series_start_with_nans(self, cache):
        ser = Series(
            np.array(
                [
                    np.nan,
                    np.nan,
                    "01/01/2011 00:00:00",
                    "01/02/2011 00:00:00",
                    "01/03/2011 00:00:00",
                ],
                dtype=object,
            )
        )

        result = to_datetime(ser, cache=cache)
        expected = Series(
            [NaT, NaT, "2011-01-01", "2011-01-02", "2011-01-03"], dtype="datetime64[ns]"
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "tz_name, offset",
        [("UTC", 0), ("UTC-3", 180), ("UTC+3", -180)],
    )
    def test_infer_datetime_format_tz_name(self, tz_name, offset):
        # GH 33133
        ser = Series([f"2019-02-02 08:07:13 {tz_name}"])
        result = to_datetime(ser)
        tz = timezone(timedelta(minutes=offset))
        expected = Series([Timestamp("2019-02-02 08:07:13").tz_localize(tz)])
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "ts,zero_tz",
        [
            ("2019-02-02 08:07:13", "Z"),
            ("2019-02-02 08:07:13", ""),
            ("2019-02-02 08:07:13.012345", "Z"),
            ("2019-02-02 08:07:13.012345", ""),
        ],
    )
    def test_infer_datetime_format_zero_tz(self, ts, zero_tz):
        # GH 41047
        ser = Series([ts + zero_tz])
        result = to_datetime(ser)
        tz = pytz.utc if zero_tz == "Z" else None
        expected = Series([Timestamp(ts, tz=tz)])
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("format", [None, "%Y-%m-%d"])
    def test_to_datetime_iso8601_noleading_0s(self, cache, format):
        # GH 11871
        ser = Series(["2014-1-1", "2014-2-2", "2015-3-3"])
        expected = Series(
            [
                Timestamp("2014-01-01"),
                Timestamp("2014-02-02"),
                Timestamp("2015-03-03"),
            ]
        )
        result = to_datetime(ser, format=format, cache=cache)
        tm.assert_series_equal(result, expected)

    def test_parse_dates_infer_datetime_format_warning(self):
        # GH 49024
        with tm.assert_produces_warning(
            UserWarning,
            match="The argument 'infer_datetime_format' is deprecated",
        ):
            to_datetime(["10-10-2000"], infer_datetime_format=True)


class TestDaysInMonth:
    # tests for issue #10154

    @pytest.mark.parametrize(
        "arg, format",
        [
            ["2015-02-29", None],
            ["2015-02-29", "%Y-%m-%d"],
            ["2015-02-32", "%Y-%m-%d"],
            ["2015-04-31", "%Y-%m-%d"],
        ],
    )
    def test_day_not_in_month_coerce(self, cache, arg, format):
        assert isna(to_datetime(arg, errors="coerce", format=format, cache=cache))

    def test_day_not_in_month_raise(self, cache):
        if PY314:
            msg = "day 29 must be in range 1..28 for month 2 in year 2015: 2015-02-29"
        else:
            msg = "day is out of range for month: 2015-02-29"
        with pytest.raises(ValueError, match=msg):
            to_datetime("2015-02-29", errors="raise", cache=cache)

    @pytest.mark.parametrize(
        "arg, format, msg",
        [
            (
                "2015-02-29",
                "%Y-%m-%d",
                f"^{DAY_IS_OUT_OF_RANGE}. {PARSING_ERR_MSG}$",
            ),
            (
                "2015-29-02",
                "%Y-%d-%m",
                f"^{DAY_IS_OUT_OF_RANGE}. {PARSING_ERR_MSG}$",
            ),
            (
                "2015-02-32",
                "%Y-%m-%d",
                '^unconverted data remains when parsing with format "%Y-%m-%d": "2", '
                f"at position 0. {PARSING_ERR_MSG}$",
            ),
            (
                "2015-32-02",
                "%Y-%d-%m",
                '^time data "2015-32-02" doesn\'t match format "%Y-%d-%m", '
                f"at position 0. {PARSING_ERR_MSG}$",
            ),
            (
                "2015-04-31",
                "%Y-%m-%d",
                f"^{DAY_IS_OUT_OF_RANGE}. {PARSING_ERR_MSG}$",
            ),
            (
                "2015-31-04",
                "%Y-%d-%m",
                f"^{DAY_IS_OUT_OF_RANGE}. {PARSING_ERR_MSG}$",
            ),
        ],
    )
    def test_day_not_in_month_raise_value(self, cache, arg, format, msg):
        # https://github.com/pandas-dev/pandas/issues/50462
        with pytest.raises(ValueError, match=msg):
            to_datetime(arg, errors="raise", format=format, cache=cache)

    @pytest.mark.parametrize(
        "expected, format",
        [
            ["2015-02-29", None],
            ["2015-02-29", "%Y-%m-%d"],
            ["2015-02-29", "%Y-%m-%d"],
            ["2015-04-31", "%Y-%m-%d"],
        ],
    )
    def test_day_not_in_month_ignore(self, cache, expected, format):
        result = to_datetime(expected, errors="ignore", format=format, cache=cache)
        assert result == expected


class TestDatetimeParsingWrappers:
    @pytest.mark.parametrize(
        "date_str, expected",
        [
            ("2011-01-01", datetime(2011, 1, 1)),
            ("2Q2005", datetime(2005, 4, 1)),
            ("2Q05", datetime(2005, 4, 1)),
            ("2005Q1", datetime(2005, 1, 1)),
            ("05Q1", datetime(2005, 1, 1)),
            ("2011Q3", datetime(2011, 7, 1)),
            ("11Q3", datetime(2011, 7, 1)),
            ("3Q2011", datetime(2011, 7, 1)),
            ("3Q11", datetime(2011, 7, 1)),
            # quarterly without space
            ("2000Q4", datetime(2000, 10, 1)),
            ("00Q4", datetime(2000, 10, 1)),
            ("4Q2000", datetime(2000, 10, 1)),
            ("4Q00", datetime(2000, 10, 1)),
            ("2000q4", datetime(2000, 10, 1)),
            ("2000-Q4", datetime(2000, 10, 1)),
            ("00-Q4", datetime(2000, 10, 1)),
            ("4Q-2000", datetime(2000, 10, 1)),
            ("4Q-00", datetime(2000, 10, 1)),
            ("00q4", datetime(2000, 10, 1)),
            ("2005", datetime(2005, 1, 1)),
            ("2005-11", datetime(2005, 11, 1)),
            ("2005 11", datetime(2005, 11, 1)),
            ("11-2005", datetime(2005, 11, 1)),
            ("11 2005", datetime(2005, 11, 1)),
            ("200511", datetime(2020, 5, 11)),
            ("20051109", datetime(2005, 11, 9)),
            ("20051109 10:15", datetime(2005, 11, 9, 10, 15)),
            ("20051109 08H", datetime(2005, 11, 9, 8, 0)),
            ("2005-11-09 10:15", datetime(2005, 11, 9, 10, 15)),
            ("2005-11-09 08H", datetime(2005, 11, 9, 8, 0)),
            ("2005/11/09 10:15", datetime(2005, 11, 9, 10, 15)),
            ("2005/11/09 10:15:32", datetime(2005, 11, 9, 10, 15, 32)),
            ("2005/11/09 10:15:32 AM", datetime(2005, 11, 9, 10, 15, 32)),
            ("2005/11/09 10:15:32 PM", datetime(2005, 11, 9, 22, 15, 32)),
            ("2005/11/09 08H", datetime(2005, 11, 9, 8, 0)),
            ("Thu Sep 25 10:36:28 2003", datetime(2003, 9, 25, 10, 36, 28)),
            ("Thu Sep 25 2003", datetime(2003, 9, 25)),
            ("Sep 25 2003", datetime(2003, 9, 25)),
            ("January 1 2014", datetime(2014, 1, 1)),
            # GH#10537
            ("2014-06", datetime(2014, 6, 1)),
            ("06-2014", datetime(2014, 6, 1)),
            ("2014-6", datetime(2014, 6, 1)),
            ("6-2014", datetime(2014, 6, 1)),
            ("20010101 12", datetime(2001, 1, 1, 12)),
            ("20010101 1234", datetime(2001, 1, 1, 12, 34)),
            ("20010101 123456", datetime(2001, 1, 1, 12, 34, 56)),
        ],
    )
    def test_parsers(self, date_str, expected, cache):
        # dateutil >= 2.5.0 defaults to yearfirst=True
        # https://github.com/dateutil/dateutil/issues/217
        yearfirst = True

        result1, _ = parsing.parse_datetime_string_with_reso(
            date_str, yearfirst=yearfirst
        )
        result2 = to_datetime(date_str, yearfirst=yearfirst)
        result3 = to_datetime([date_str], yearfirst=yearfirst)
        # result5 is used below
        result4 = to_datetime(
            np.array([date_str], dtype=object), yearfirst=yearfirst, cache=cache
        )
        result6 = DatetimeIndex([date_str], yearfirst=yearfirst)
        # result7 is used below
        result8 = DatetimeIndex(Index([date_str]), yearfirst=yearfirst)
        result9 = DatetimeIndex(Series([date_str]), yearfirst=yearfirst)

        for res in [result1, result2]:
            assert res == expected
        for res in [result3, result4, result6, result8, result9]:
            exp = DatetimeIndex([Timestamp(expected)])
            tm.assert_index_equal(res, exp)

        # these really need to have yearfirst, but we don't support
        if not yearfirst:
            result5 = Timestamp(date_str)
            assert result5 == expected
            result7 = date_range(date_str, freq="S", periods=1, yearfirst=yearfirst)
            assert result7 == expected

    def test_na_values_with_cache(
        self, cache, unique_nulls_fixture, unique_nulls_fixture2
    ):
        # GH22305
        expected = Index([NaT, NaT], dtype="datetime64[ns]")
        result = to_datetime([unique_nulls_fixture, unique_nulls_fixture2], cache=cache)
        tm.assert_index_equal(result, expected)

    def test_parsers_nat(self):
        # Test that each of several string-accepting methods return pd.NaT
        result1, _ = parsing.parse_datetime_string_with_reso("NaT")
        result2 = to_datetime("NaT")
        result3 = Timestamp("NaT")
        result4 = DatetimeIndex(["NaT"])[0]
        assert result1 is NaT
        assert result2 is NaT
        assert result3 is NaT
        assert result4 is NaT

    @pytest.mark.parametrize(
        "date_str, dayfirst, yearfirst, expected",
        [
            ("10-11-12", False, False, datetime(2012, 10, 11)),
            ("10-11-12", True, False, datetime(2012, 11, 10)),
            ("10-11-12", False, True, datetime(2010, 11, 12)),
            ("10-11-12", True, True, datetime(2010, 12, 11)),
            ("20/12/21", False, False, datetime(2021, 12, 20)),
            ("20/12/21", True, False, datetime(2021, 12, 20)),
            ("20/12/21", False, True, datetime(2020, 12, 21)),
            ("20/12/21", True, True, datetime(2020, 12, 21)),
        ],
    )
    def test_parsers_dayfirst_yearfirst(
        self, cache, date_str, dayfirst, yearfirst, expected
    ):
        # OK
        # 2.5.1 10-11-12   [dayfirst=0, yearfirst=0] -> 2012-10-11 00:00:00
        # 2.5.2 10-11-12   [dayfirst=0, yearfirst=1] -> 2012-10-11 00:00:00
        # 2.5.3 10-11-12   [dayfirst=0, yearfirst=0] -> 2012-10-11 00:00:00

        # OK
        # 2.5.1 10-11-12   [dayfirst=0, yearfirst=1] -> 2010-11-12 00:00:00
        # 2.5.2 10-11-12   [dayfirst=0, yearfirst=1] -> 2010-11-12 00:00:00
        # 2.5.3 10-11-12   [dayfirst=0, yearfirst=1] -> 2010-11-12 00:00:00

        # bug fix in 2.5.2
        # 2.5.1 10-11-12   [dayfirst=1, yearfirst=1] -> 2010-11-12 00:00:00
        # 2.5.2 10-11-12   [dayfirst=1, yearfirst=1] -> 2010-12-11 00:00:00
        # 2.5.3 10-11-12   [dayfirst=1, yearfirst=1] -> 2010-12-11 00:00:00

        # OK
        # 2.5.1 10-11-12   [dayfirst=1, yearfirst=0] -> 2012-11-10 00:00:00
        # 2.5.2 10-11-12   [dayfirst=1, yearfirst=0] -> 2012-11-10 00:00:00
        # 2.5.3 10-11-12   [dayfirst=1, yearfirst=0] -> 2012-11-10 00:00:00

        # OK
        # 2.5.1 20/12/21   [dayfirst=0, yearfirst=0] -> 2021-12-20 00:00:00
        # 2.5.2 20/12/21   [dayfirst=0, yearfirst=0] -> 2021-12-20 00:00:00
        # 2.5.3 20/12/21   [dayfirst=0, yearfirst=0] -> 2021-12-20 00:00:00

        # OK
        # 2.5.1 20/12/21   [dayfirst=0, yearfirst=1] -> 2020-12-21 00:00:00
        # 2.5.2 20/12/21   [dayfirst=0, yearfirst=1] -> 2020-12-21 00:00:00
        # 2.5.3 20/12/21   [dayfirst=0, yearfirst=1] -> 2020-12-21 00:00:00

        # revert of bug in 2.5.2
        # 2.5.1 20/12/21   [dayfirst=1, yearfirst=1] -> 2020-12-21 00:00:00
        # 2.5.2 20/12/21   [dayfirst=1, yearfirst=1] -> month must be in 1..12
        # 2.5.3 20/12/21   [dayfirst=1, yearfirst=1] -> 2020-12-21 00:00:00

        # OK
        # 2.5.1 20/12/21   [dayfirst=1, yearfirst=0] -> 2021-12-20 00:00:00
        # 2.5.2 20/12/21   [dayfirst=1, yearfirst=0] -> 2021-12-20 00:00:00
        # 2.5.3 20/12/21   [dayfirst=1, yearfirst=0] -> 2021-12-20 00:00:00

        # str : dayfirst, yearfirst, expected

        # compare with dateutil result
        dateutil_result = parse(date_str, dayfirst=dayfirst, yearfirst=yearfirst)
        assert dateutil_result == expected

        result1, _ = parsing.parse_datetime_string_with_reso(
            date_str, dayfirst=dayfirst, yearfirst=yearfirst
        )

        # we don't support dayfirst/yearfirst here:
        if not dayfirst and not yearfirst:
            result2 = Timestamp(date_str)
            assert result2 == expected

        result3 = to_datetime(
            date_str, dayfirst=dayfirst, yearfirst=yearfirst, cache=cache
        )

        result4 = DatetimeIndex([date_str], dayfirst=dayfirst, yearfirst=yearfirst)[0]

        assert result1 == expected
        assert result3 == expected
        assert result4 == expected

    @pytest.mark.parametrize(
        "date_str, exp_def",
        [["10:15", datetime(1, 1, 1, 10, 15)], ["9:05", datetime(1, 1, 1, 9, 5)]],
    )
    def test_parsers_timestring(self, date_str, exp_def):
        # must be the same as dateutil result
        exp_now = parse(date_str)

        result1, _ = parsing.parse_datetime_string_with_reso(date_str)
        result2 = to_datetime(date_str)
        result3 = to_datetime([date_str])
        result4 = Timestamp(date_str)
        result5 = DatetimeIndex([date_str])[0]
        # parse time string return time string based on default date
        # others are not, and can't be changed because it is used in
        # time series plot
        assert result1 == exp_def
        assert result2 == exp_now
        assert result3 == exp_now
        assert result4 == exp_now
        assert result5 == exp_now

    @pytest.mark.parametrize(
        "dt_string, tz, dt_string_repr",
        [
            (
                "2013-01-01 05:45+0545",
                timezone(timedelta(minutes=345)),
                "Timestamp('2013-01-01 05:45:00+0545', tz='UTC+05:45')",
            ),
            (
                "2013-01-01 05:30+0530",
                timezone(timedelta(minutes=330)),
                "Timestamp('2013-01-01 05:30:00+0530', tz='UTC+05:30')",
            ),
        ],
    )
    def test_parsers_timezone_minute_offsets_roundtrip(
        self, cache, dt_string, tz, dt_string_repr
    ):
        # GH11708
        base = to_datetime("2013-01-01 00:00:00", cache=cache)
        base = base.tz_localize("UTC").tz_convert(tz)
        dt_time = to_datetime(dt_string, cache=cache)
        assert base == dt_time
        assert dt_string_repr == repr(dt_time)


@pytest.fixture(params=["D", "s", "ms", "us", "ns"])
def units(request):
    """Day and some time units.

    * D
    * s
    * ms
    * us
    * ns
    """
    return request.param


@pytest.fixture
def epoch_1960():
    """Timestamp at 1960-01-01."""
    return Timestamp("1960-01-01")


@pytest.fixture
def units_from_epochs():
    return list(range(5))


@pytest.fixture(params=["timestamp", "pydatetime", "datetime64", "str_1960"])
def epochs(epoch_1960, request):
    """Timestamp at 1960-01-01 in various forms.

    * Timestamp
    * datetime.datetime
    * numpy.datetime64
    * str
    """
    assert request.param in {"timestamp", "pydatetime", "datetime64", "str_1960"}
    if request.param == "timestamp":
        return epoch_1960
    elif request.param == "pydatetime":
        return epoch_1960.to_pydatetime()
    elif request.param == "datetime64":
        return epoch_1960.to_datetime64()
    else:
        return str(epoch_1960)


@pytest.fixture
def julian_dates():
    return date_range("2014-1-1", periods=10).to_julian_date().values


class TestOrigin:
    def test_origin_and_unit(self):
        # GH#42624
        ts = to_datetime(1, unit="s", origin=1)
        expected = Timestamp("1970-01-01 00:00:02")
        assert ts == expected

        ts = to_datetime(1, unit="s", origin=1_000_000_000)
        expected = Timestamp("2001-09-09 01:46:41")
        assert ts == expected

    def test_julian(self, julian_dates):
        # gh-11276, gh-11745
        # for origin as julian

        result = Series(to_datetime(julian_dates, unit="D", origin="julian"))
        expected = Series(
            to_datetime(julian_dates - Timestamp(0).to_julian_date(), unit="D")
        )
        tm.assert_series_equal(result, expected)

    def test_unix(self):
        result = Series(to_datetime([0, 1, 2], unit="D", origin="unix"))
        expected = Series(
            [Timestamp("1970-01-01"), Timestamp("1970-01-02"), Timestamp("1970-01-03")],
            dtype="M8[ns]",
        )
        tm.assert_series_equal(result, expected)

    def test_julian_round_trip(self):
        result = to_datetime(2456658, origin="julian", unit="D")
        assert result.to_julian_date() == 2456658

        # out-of-bounds
        msg = "1 is Out of Bounds for origin='julian'"
        with pytest.raises(ValueError, match=msg):
            to_datetime(1, origin="julian", unit="D")

    def test_invalid_unit(self, units, julian_dates):
        # checking for invalid combination of origin='julian' and unit != D
        if units != "D":
            msg = "unit must be 'D' for origin='julian'"
            with pytest.raises(ValueError, match=msg):
                to_datetime(julian_dates, unit=units, origin="julian")

    @pytest.mark.parametrize("unit", ["ns", "D"])
    def test_invalid_origin(self, unit):
        # need to have a numeric specified
        msg = "it must be numeric with a unit specified"
        with pytest.raises(ValueError, match=msg):
            to_datetime("2005-01-01", origin="1960-01-01", unit=unit)

    @pytest.mark.parametrize(
        "epochs",
        [
            Timestamp(1960, 1, 1),
            datetime(1960, 1, 1),
            "1960-01-01",
            np.datetime64("1960-01-01"),
        ],
    )
    def test_epoch(self, units, epochs):
        epoch_1960 = Timestamp(1960, 1, 1)
        units_from_epochs = np.arange(5, dtype=np.int64)
        expected = Series(
            [pd.Timedelta(x, unit=units) + epoch_1960 for x in units_from_epochs]
        )

        result = Series(to_datetime(units_from_epochs, unit=units, origin=epochs))
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "origin, exc",
        [
            ("random_string", ValueError),
            ("epoch", ValueError),
            ("13-24-1990", ValueError),
            (datetime(1, 1, 1), OutOfBoundsDatetime),
        ],
    )
    def test_invalid_origins(self, origin, exc, units, units_from_epochs):
        msg = "|".join(
            [
                f"origin {origin} is Out of Bounds",
                f"origin {origin} cannot be converted to a Timestamp",
                "Cannot cast .* to unit='ns' without overflow",
            ]
        )
        with pytest.raises(exc, match=msg):
            to_datetime(units_from_epochs, unit=units, origin=origin)

    def test_invalid_origins_tzinfo(self):
        # GH16842
        with pytest.raises(ValueError, match="must be tz-naive"):
            to_datetime(1, unit="D", origin=datetime(2000, 1, 1, tzinfo=pytz.utc))

    def test_incorrect_value_exception(self):
        # GH47495
        msg = (
            "Unknown datetime string format, unable to parse: yesterday, at position 1"
        )
        with pytest.raises(ValueError, match=msg):
            to_datetime(["today", "yesterday"])

    @pytest.mark.parametrize(
        "format, warning",
        [
            (None, UserWarning),
            ("%Y-%m-%d %H:%M:%S", None),
            ("%Y-%d-%m %H:%M:%S", None),
        ],
    )
    def test_to_datetime_out_of_bounds_with_format_arg(self, format, warning):
        # see gh-23830
        msg = r"^Out of bounds nanosecond timestamp: 2417-10-10 00:00:00, at position 0"
        with pytest.raises(OutOfBoundsDatetime, match=msg):
            to_datetime("2417-10-10 00:00:00", format=format)

    @pytest.mark.parametrize(
        "arg, origin, expected_str",
        [
            [200 * 365, "unix", "2169-11-13 00:00:00"],
            [200 * 365, "1870-01-01", "2069-11-13 00:00:00"],
            [300 * 365, "1870-01-01", "2169-10-20 00:00:00"],
        ],
    )
    def test_processing_order(self, arg, origin, expected_str):
        # make sure we handle out-of-bounds *before*
        # constructing the dates

        result = to_datetime(arg, unit="D", origin=origin)
        expected = Timestamp(expected_str)
        assert result == expected

        result = to_datetime(200 * 365, unit="D", origin="1870-01-01")
        expected = Timestamp("2069-11-13 00:00:00")
        assert result == expected

        result = to_datetime(300 * 365, unit="D", origin="1870-01-01")
        expected = Timestamp("2169-10-20 00:00:00")
        assert result == expected

    @pytest.mark.parametrize(
        "offset,utc,exp",
        [
            ["Z", True, "2019-01-01T00:00:00.000Z"],
            ["Z", None, "2019-01-01T00:00:00.000Z"],
            ["-01:00", True, "2019-01-01T01:00:00.000Z"],
            ["-01:00", None, "2019-01-01T00:00:00.000-01:00"],
        ],
    )
    def test_arg_tz_ns_unit(self, offset, utc, exp):
        # GH 25546
        arg = "2019-01-01T00:00:00.000" + offset
        result = to_datetime([arg], unit="ns", utc=utc)
        expected = to_datetime([exp]).as_unit("ns")
        tm.assert_index_equal(result, expected)


class TestShouldCache:
    @pytest.mark.parametrize(
        "listlike,do_caching",
        [
            ([1, 2, 3, 4, 5, 6, 7, 8, 9, 0], False),
            ([1, 1, 1, 1, 4, 5, 6, 7, 8, 9], True),
        ],
    )
    def test_should_cache(self, listlike, do_caching):
        assert (
            tools.should_cache(listlike, check_count=len(listlike), unique_share=0.7)
            == do_caching
        )

    @pytest.mark.parametrize(
        "unique_share,check_count, err_message",
        [
            (0.5, 11, r"check_count must be in next bounds: \[0; len\(arg\)\]"),
            (10, 2, r"unique_share must be in next bounds: \(0; 1\)"),
        ],
    )
    def test_should_cache_errors(self, unique_share, check_count, err_message):
        arg = [5] * 10

        with pytest.raises(AssertionError, match=err_message):
            tools.should_cache(arg, unique_share, check_count)

    @pytest.mark.parametrize(
        "listlike",
        [
            (deque([Timestamp("2010-06-02 09:30:00")] * 51)),
            ([Timestamp("2010-06-02 09:30:00")] * 51),
            (tuple([Timestamp("2010-06-02 09:30:00")] * 51)),
        ],
    )
    def test_no_slicing_errors_in_should_cache(self, listlike):
        # GH#29403
        assert tools.should_cache(listlike) is True


def test_nullable_integer_to_datetime():
    # Test for #30050
    ser = Series([1, 2, None, 2**61, None])
    ser = ser.astype("Int64")
    ser_copy = ser.copy()

    res = to_datetime(ser, unit="ns")

    expected = Series(
        [
            np.datetime64("1970-01-01 00:00:00.000000001"),
            np.datetime64("1970-01-01 00:00:00.000000002"),
            np.datetime64("NaT"),
            np.datetime64("2043-01-25 23:56:49.213693952"),
            np.datetime64("NaT"),
        ]
    )
    tm.assert_series_equal(res, expected)
    # Check that ser isn't mutated
    tm.assert_series_equal(ser, ser_copy)


@pytest.mark.parametrize("klass", [np.array, list])
def test_na_to_datetime(nulls_fixture, klass):
    if isinstance(nulls_fixture, Decimal):
        with pytest.raises(TypeError, match="not convertible to datetime"):
            to_datetime(klass([nulls_fixture]))

    else:
        result = to_datetime(klass([nulls_fixture]))

        assert result[0] is NaT


@pytest.mark.parametrize("errors", ["raise", "coerce", "ignore"])
@pytest.mark.parametrize(
    "args, format",
    [
        (["03/24/2016", "03/25/2016", ""], "%m/%d/%Y"),
        (["2016-03-24", "2016-03-25", ""], "%Y-%m-%d"),
    ],
    ids=["non-ISO8601", "ISO8601"],
)
def test_empty_string_datetime(errors, args, format):
    # GH13044, GH50251
    td = Series(args)

    # coerce empty string to pd.NaT
    result = to_datetime(td, format=format, errors=errors)
    expected = Series(["2016-03-24", "2016-03-25", NaT], dtype="datetime64[ns]")
    tm.assert_series_equal(expected, result)


def test_empty_string_datetime_coerce__unit():
    # GH13044
    # coerce empty string to pd.NaT
    result = to_datetime([1, ""], unit="s", errors="coerce")
    expected = DatetimeIndex(["1970-01-01 00:00:01", "NaT"], dtype="datetime64[ns]")
    tm.assert_index_equal(expected, result)

    # verify that no exception is raised even when errors='raise' is set
    result = to_datetime([1, ""], unit="s", errors="raise")
    tm.assert_index_equal(expected, result)


@pytest.mark.parametrize("cache", [True, False])
def test_to_datetime_monotonic_increasing_index(cache):
    # GH28238
    cstart = start_caching_at
    times = date_range(Timestamp("1980"), periods=cstart, freq="YS")
    times = times.to_frame(index=False, name="DT").sample(n=cstart, random_state=1)
    times.index = times.index.to_series().astype(float) / 1000
    result = to_datetime(times.iloc[:, 0], cache=cache)
    expected = times.iloc[:, 0]
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "series_length",
    [40, start_caching_at, (start_caching_at + 1), (start_caching_at + 5)],
)
def test_to_datetime_cache_coerce_50_lines_outofbounds(series_length):
    # GH#45319
    ser = Series(
        [datetime.fromisoformat("1446-04-12 00:00:00+00:00")]
        + ([datetime.fromisoformat("1991-10-20 00:00:00+00:00")] * series_length),
        dtype=object,
    )
    result1 = to_datetime(ser, errors="coerce", utc=True)

    expected1 = Series(
        [NaT] + ([Timestamp("1991-10-20 00:00:00+00:00")] * series_length)
    )

    tm.assert_series_equal(result1, expected1)

    result2 = to_datetime(ser, errors="ignore", utc=True)

    expected2 = Series(
        [datetime.fromisoformat("1446-04-12 00:00:00+00:00")]
        + ([datetime.fromisoformat("1991-10-20 00:00:00+00:00")] * series_length)
    )

    tm.assert_series_equal(result2, expected2)

    with pytest.raises(OutOfBoundsDatetime, match="Out of bounds nanosecond timestamp"):
        to_datetime(ser, errors="raise", utc=True)


def test_to_datetime_format_f_parse_nanos():
    # GH 48767
    timestamp = "15/02/2020 02:03:04.123456789"
    timestamp_format = "%d/%m/%Y %H:%M:%S.%f"
    result = to_datetime(timestamp, format=timestamp_format)
    expected = Timestamp(
        year=2020,
        month=2,
        day=15,
        hour=2,
        minute=3,
        second=4,
        microsecond=123456,
        nanosecond=789,
    )
    assert result == expected


def test_to_datetime_mixed_iso8601():
    # https://github.com/pandas-dev/pandas/issues/50411
    result = to_datetime(["2020-01-01", "2020-01-01 05:00:00"], format="ISO8601")
    expected = DatetimeIndex(["2020-01-01 00:00:00", "2020-01-01 05:00:00"])
    tm.assert_index_equal(result, expected)


def test_to_datetime_mixed_other():
    # https://github.com/pandas-dev/pandas/issues/50411
    result = to_datetime(["01/11/2000", "12 January 2000"], format="mixed")
    expected = DatetimeIndex(["2000-01-11", "2000-01-12"])
    tm.assert_index_equal(result, expected)


@pytest.mark.parametrize("exact", [True, False])
@pytest.mark.parametrize("format", ["ISO8601", "mixed"])
def test_to_datetime_mixed_or_iso_exact(exact, format):
    msg = "Cannot use 'exact' when 'format' is 'mixed' or 'ISO8601'"
    with pytest.raises(ValueError, match=msg):
        to_datetime(["2020-01-01"], exact=exact, format=format)


def test_to_datetime_mixed_not_necessarily_iso8601_raise():
    # https://github.com/pandas-dev/pandas/issues/50411
    with pytest.raises(
        ValueError, match="Time data 01-01-2000 is not ISO8601 format, at position 1"
    ):
        to_datetime(["2020-01-01", "01-01-2000"], format="ISO8601")


@pytest.mark.parametrize(
    ("errors", "expected"),
    [
        ("coerce", DatetimeIndex(["2020-01-01 00:00:00", NaT])),
        ("ignore", Index(["2020-01-01", "01-01-2000"], dtype="str")),
    ],
)
def test_to_datetime_mixed_not_necessarily_iso8601_coerce(errors, expected):
    # https://github.com/pandas-dev/pandas/issues/50411
    result = to_datetime(["2020-01-01", "01-01-2000"], format="ISO8601", errors=errors)
    tm.assert_index_equal(result, expected)


def test_ignoring_unknown_tz_deprecated():
    # GH#18702, GH#51476
    dtstr = "2014 Jan 9 05:15 FAKE"
    msg = 'un-recognized timezone "FAKE". Dropping unrecognized timezones is deprecated'
    with tm.assert_produces_warning(FutureWarning, match=msg):
        res = Timestamp(dtstr)
    assert res == Timestamp(dtstr[:-5])

    with tm.assert_produces_warning(FutureWarning):
        res = to_datetime(dtstr)
    assert res == to_datetime(dtstr[:-5])
    with tm.assert_produces_warning(FutureWarning):
        res = to_datetime([dtstr])
    tm.assert_index_equal(res, to_datetime([dtstr[:-5]]))


def test_from_numeric_arrow_dtype(any_numeric_ea_dtype):
    # GH 52425
    pytest.importorskip("pyarrow")
    ser = Series([1, 2], dtype=f"{any_numeric_ea_dtype.lower()}[pyarrow]")
    result = to_datetime(ser)
    expected = Series([1, 2], dtype="datetime64[ns]")
    tm.assert_series_equal(result, expected)


def test_to_datetime_with_empty_str_utc_false_format_mixed():
    # GH 50887
    vals = ["2020-01-01 00:00+00:00", ""]
    result = to_datetime(vals, format="mixed")
    expected = Index([Timestamp("2020-01-01 00:00+00:00"), "NaT"], dtype="M8[ns, UTC]")
    tm.assert_index_equal(result, expected)

    # Check that a couple of other similar paths work the same way
    alt = to_datetime(vals)
    tm.assert_index_equal(alt, expected)
    alt2 = DatetimeIndex(vals)
    tm.assert_index_equal(alt2, expected)


def test_to_datetime_with_empty_str_utc_false_offsets_and_format_mixed():
    # GH 50887
    msg = "parsing datetimes with mixed time zones will raise an error"

    with tm.assert_produces_warning(FutureWarning, match=msg):
        to_datetime(
            ["2020-01-01 00:00+00:00", "2020-01-01 00:00+02:00", ""], format="mixed"
        )


def test_to_datetime_mixed_tzs_mixed_types():
    # GH#55793, GH#55693 mismatched tzs but one is str and other is
    #  datetime object
    ts = Timestamp("2016-01-02 03:04:05", tz="US/Pacific")
    dtstr = "2023-10-30 15:06+01"
    arr = [ts, dtstr]

    msg = (
        "Mixed timezones detected. pass utc=True in to_datetime or tz='UTC' "
        "in DatetimeIndex to convert to a common timezone"
    )
    with pytest.raises(ValueError, match=msg):
        to_datetime(arr)
    with pytest.raises(ValueError, match=msg):
        to_datetime(arr, format="mixed")
    with pytest.raises(ValueError, match=msg):
        DatetimeIndex(arr)


def test_to_datetime_mixed_types_matching_tzs():
    # GH#55793
    dtstr = "2023-11-01 09:22:03-07:00"
    ts = Timestamp(dtstr)
    arr = [ts, dtstr]
    res1 = to_datetime(arr)
    res2 = to_datetime(arr[::-1])[::-1]
    res3 = to_datetime(arr, format="mixed")
    res4 = DatetimeIndex(arr)

    expected = DatetimeIndex([ts, ts])
    tm.assert_index_equal(res1, expected)
    tm.assert_index_equal(res2, expected)
    tm.assert_index_equal(res3, expected)
    tm.assert_index_equal(res4, expected)


dtstr = "2020-01-01 00:00+00:00"
ts = Timestamp(dtstr)


@pytest.mark.filterwarnings("ignore:Could not infer format:UserWarning")
@pytest.mark.parametrize(
    "aware_val",
    [dtstr, Timestamp(dtstr)],
    ids=lambda x: type(x).__name__,
)
@pytest.mark.parametrize(
    "naive_val",
    [dtstr[:-6], ts.tz_localize(None), ts.date(), ts.asm8, ts.value, float(ts.value)],
    ids=lambda x: type(x).__name__,
)
@pytest.mark.parametrize("naive_first", [True, False])
def test_to_datetime_mixed_awareness_mixed_types(aware_val, naive_val, naive_first):
    # GH#55793, GH#55693
    # Empty string parses to NaT
    vals = [aware_val, naive_val, ""]

    vec = vals
    if naive_first:
        # alas, the behavior is order-dependent, so we test both ways
        vec = [naive_val, aware_val, ""]

    # both_strs-> paths that were previously already deprecated with warning
    #  issued in _array_to_datetime_object
    both_strs = isinstance(aware_val, str) and isinstance(naive_val, str)
    has_numeric = isinstance(naive_val, (int, float))

    depr_msg = "In a future version of pandas, parsing datetimes with mixed time zones"

    first_non_null = next(x for x in vec if x != "")
    # if first_non_null is a not a string, _guess_datetime_format_for_array
    #  doesn't guess a format so we don't go through array_strptime
    if not isinstance(first_non_null, str):
        # that case goes through array_strptime which has different behavior
        msg = "Cannot mix tz-aware with tz-naive values"
        if naive_first and isinstance(aware_val, Timestamp):
            if isinstance(naive_val, Timestamp):
                msg = "Tz-aware datetime.datetime cannot be converted to datetime64"
            with pytest.raises(ValueError, match=msg):
                to_datetime(vec)
        else:
            with pytest.raises(ValueError, match=msg):
                to_datetime(vec)

        # No warning/error with utc=True
        to_datetime(vec, utc=True)

    elif has_numeric and vec.index(aware_val) < vec.index(naive_val):
        msg = "time data .* doesn't match format"
        with pytest.raises(ValueError, match=msg):
            to_datetime(vec)
        with pytest.raises(ValueError, match=msg):
            to_datetime(vec, utc=True)

    elif both_strs and vec.index(aware_val) < vec.index(naive_val):
        msg = r"time data \"2020-01-01 00:00\" doesn't match format"
        with pytest.raises(ValueError, match=msg):
            to_datetime(vec)
        with pytest.raises(ValueError, match=msg):
            to_datetime(vec, utc=True)

    elif both_strs and vec.index(naive_val) < vec.index(aware_val):
        msg = "unconverted data remains when parsing with format"
        with pytest.raises(ValueError, match=msg):
            to_datetime(vec)
        with pytest.raises(ValueError, match=msg):
            to_datetime(vec, utc=True)

    else:
        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            to_datetime(vec)

        # No warning/error with utc=True
        to_datetime(vec, utc=True)

    if both_strs:
        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            to_datetime(vec, format="mixed")
        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            msg = "DatetimeIndex has mixed timezones"
            with pytest.raises(TypeError, match=msg):
                DatetimeIndex(vec)
    else:
        msg = "Cannot mix tz-aware with tz-naive values"
        if naive_first and isinstance(aware_val, Timestamp):
            if isinstance(naive_val, Timestamp):
                msg = "Tz-aware datetime.datetime cannot be converted to datetime64"
            with pytest.raises(ValueError, match=msg):
                to_datetime(vec, format="mixed")
            with pytest.raises(ValueError, match=msg):
                DatetimeIndex(vec)
        else:
            with pytest.raises(ValueError, match=msg):
                to_datetime(vec, format="mixed")
            with pytest.raises(ValueError, match=msg):
                DatetimeIndex(vec)
