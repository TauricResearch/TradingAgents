"""
Tests for Timestamp parsing, aimed at pandas/_libs/tslibs/parsing.pyx
"""
from datetime import datetime
import re

from dateutil.parser import parse as du_parse
from dateutil.tz import tzlocal
from hypothesis import given
import numpy as np
import pytest

from pandas._libs.tslibs import (
    parsing,
    strptime,
)
from pandas._libs.tslibs.parsing import parse_datetime_string_with_reso
from pandas.compat import (
    ISMUSL,
    is_platform_arm,
    is_platform_windows,
)
import pandas.util._test_decorators as td

import pandas._testing as tm
from pandas._testing._hypothesis import DATETIME_NO_TZ


@pytest.mark.skipif(
    is_platform_windows() or ISMUSL or is_platform_arm(),
    reason="TZ setting incorrect on Windows and MUSL Linux",
)
def test_parsing_tzlocal_deprecated():
    # GH#50791
    msg = (
        "Parsing 'EST' as tzlocal.*"
        "Pass the 'tz' keyword or call tz_localize after construction instead"
    )
    dtstr = "Jan 15 2004 03:00 EST"

    with tm.set_timezone("US/Eastern"):
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res, _ = parse_datetime_string_with_reso(dtstr)

        assert isinstance(res.tzinfo, tzlocal)

        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = parsing.py_parse_datetime_string(dtstr)
        assert isinstance(res.tzinfo, tzlocal)


def test_parse_datetime_string_with_reso():
    (parsed, reso) = parse_datetime_string_with_reso("4Q1984")
    (parsed_lower, reso_lower) = parse_datetime_string_with_reso("4q1984")

    assert reso == reso_lower
    assert parsed == parsed_lower


def test_parse_datetime_string_with_reso_nanosecond_reso():
    # GH#46811
    parsed, reso = parse_datetime_string_with_reso("2022-04-20 09:19:19.123456789")
    assert reso == "nanosecond"


def test_parse_datetime_string_with_reso_invalid_type():
    # Raise on invalid input, don't just return it
    msg = "Argument 'date_string' has incorrect type (expected str, got tuple)"
    with pytest.raises(TypeError, match=re.escape(msg)):
        parse_datetime_string_with_reso((4, 5))


@pytest.mark.parametrize(
    "dashed,normal", [("1988-Q2", "1988Q2"), ("2Q-1988", "2Q1988")]
)
def test_parse_time_quarter_with_dash(dashed, normal):
    # see gh-9688
    (parsed_dash, reso_dash) = parse_datetime_string_with_reso(dashed)
    (parsed, reso) = parse_datetime_string_with_reso(normal)

    assert parsed_dash == parsed
    assert reso_dash == reso


@pytest.mark.parametrize("dashed", ["-2Q1992", "2-Q1992", "4-4Q1992"])
def test_parse_time_quarter_with_dash_error(dashed):
    msg = f"Unknown datetime string format, unable to parse: {dashed}"

    with pytest.raises(parsing.DateParseError, match=msg):
        parse_datetime_string_with_reso(dashed)


@pytest.mark.parametrize(
    "date_string,expected",
    [
        ("123.1234", False),
        ("-50000", False),
        ("999", False),
        ("m", False),
        ("T", False),
        ("Mon Sep 16, 2013", True),
        ("2012-01-01", True),
        ("01/01/2012", True),
        ("01012012", True),
        ("0101", True),
        ("1-1", True),
    ],
)
def test_does_not_convert_mixed_integer(date_string, expected):
    assert parsing._does_string_look_like_datetime(date_string) is expected


@pytest.mark.parametrize(
    "date_str,kwargs,msg",
    [
        (
            "2013Q5",
            {},
            (
                "Incorrect quarterly string is given, "
                "quarter must be between 1 and 4: 2013Q5"
            ),
        ),
        # see gh-5418
        (
            "2013Q1",
            {"freq": "INVLD-L-DEC-SAT"},
            (
                "Unable to retrieve month information "
                "from given freq: INVLD-L-DEC-SAT"
            ),
        ),
    ],
)
def test_parsers_quarterly_with_freq_error(date_str, kwargs, msg):
    with pytest.raises(parsing.DateParseError, match=msg):
        parsing.parse_datetime_string_with_reso(date_str, **kwargs)


@pytest.mark.parametrize(
    "date_str,freq,expected",
    [
        ("2013Q2", None, datetime(2013, 4, 1)),
        ("2013Q2", "Y-APR", datetime(2012, 8, 1)),
        ("2013-Q2", "Y-DEC", datetime(2013, 4, 1)),
    ],
)
def test_parsers_quarterly_with_freq(date_str, freq, expected):
    result, _ = parsing.parse_datetime_string_with_reso(date_str, freq=freq)
    assert result == expected


@pytest.mark.parametrize(
    "date_str", ["2Q 2005", "2Q-200Y", "2Q-200", "22Q2005", "2Q200.", "6Q-20"]
)
def test_parsers_quarter_invalid(date_str):
    if date_str == "6Q-20":
        msg = (
            "Incorrect quarterly string is given, quarter "
            f"must be between 1 and 4: {date_str}"
        )
    else:
        msg = f"Unknown datetime string format, unable to parse: {date_str}"

    with pytest.raises(ValueError, match=msg):
        parsing.parse_datetime_string_with_reso(date_str)


@pytest.mark.parametrize(
    "date_str,expected",
    [("201101", datetime(2011, 1, 1, 0, 0)), ("200005", datetime(2000, 5, 1, 0, 0))],
)
def test_parsers_month_freq(date_str, expected):
    result, _ = parsing.parse_datetime_string_with_reso(date_str, freq="ME")
    assert result == expected


@td.skip_if_not_us_locale
@pytest.mark.parametrize(
    "string,fmt",
    [
        ("20111230", "%Y%m%d"),
        ("201112300000", "%Y%m%d%H%M"),
        ("20111230000000", "%Y%m%d%H%M%S"),
        ("20111230T00", "%Y%m%dT%H"),
        ("20111230T0000", "%Y%m%dT%H%M"),
        ("20111230T000000", "%Y%m%dT%H%M%S"),
        ("2011-12-30", "%Y-%m-%d"),
        ("2011", "%Y"),
        ("2011-01", "%Y-%m"),
        ("30-12-2011", "%d-%m-%Y"),
        ("2011-12-30 00:00:00", "%Y-%m-%d %H:%M:%S"),
        ("2011-12-30T00:00:00", "%Y-%m-%dT%H:%M:%S"),
        ("2011-12-30T00:00:00UTC", "%Y-%m-%dT%H:%M:%S%Z"),
        ("2011-12-30T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z"),
        ("2011-12-30T00:00:00+9", "%Y-%m-%dT%H:%M:%S%z"),
        ("2011-12-30T00:00:00+09", "%Y-%m-%dT%H:%M:%S%z"),
        ("2011-12-30T00:00:00+090", None),
        ("2011-12-30T00:00:00+0900", "%Y-%m-%dT%H:%M:%S%z"),
        ("2011-12-30T00:00:00-0900", "%Y-%m-%dT%H:%M:%S%z"),
        ("2011-12-30T00:00:00+09:00", "%Y-%m-%dT%H:%M:%S%z"),
        ("2011-12-30T00:00:00+09:000", None),
        ("2011-12-30T00:00:00+9:0", "%Y-%m-%dT%H:%M:%S%z"),
        ("2011-12-30T00:00:00+09:", None),
        ("2011-12-30T00:00:00.000000UTC", "%Y-%m-%dT%H:%M:%S.%f%Z"),
        ("2011-12-30T00:00:00.000000Z", "%Y-%m-%dT%H:%M:%S.%f%z"),
        ("2011-12-30T00:00:00.000000+9", "%Y-%m-%dT%H:%M:%S.%f%z"),
        ("2011-12-30T00:00:00.000000+09", "%Y-%m-%dT%H:%M:%S.%f%z"),
        ("2011-12-30T00:00:00.000000+090", None),
        ("2011-12-30T00:00:00.000000+0900", "%Y-%m-%dT%H:%M:%S.%f%z"),
        ("2011-12-30T00:00:00.000000-0900", "%Y-%m-%dT%H:%M:%S.%f%z"),
        ("2011-12-30T00:00:00.000000+09:00", "%Y-%m-%dT%H:%M:%S.%f%z"),
        ("2011-12-30T00:00:00.000000+09:000", None),
        ("2011-12-30T00:00:00.000000+9:0", "%Y-%m-%dT%H:%M:%S.%f%z"),
        ("2011-12-30T00:00:00.000000+09:", None),
        ("2011-12-30 00:00:00.000000", "%Y-%m-%d %H:%M:%S.%f"),
        ("Tue 24 Aug 2021 01:30:48", "%a %d %b %Y %H:%M:%S"),
        ("Tuesday 24 Aug 2021 01:30:48", "%A %d %b %Y %H:%M:%S"),
        ("Tue 24 Aug 2021 01:30:48 AM", "%a %d %b %Y %I:%M:%S %p"),
        ("Tuesday 24 Aug 2021 01:30:48 AM", "%A %d %b %Y %I:%M:%S %p"),
        ("27.03.2003 14:55:00.000", "%d.%m.%Y %H:%M:%S.%f"),  # GH50317
    ],
)
def test_guess_datetime_format_with_parseable_formats(string, fmt):
    with tm.maybe_produces_warning(
        UserWarning, fmt is not None and re.search(r"%d.*%m", fmt)
    ):
        result = parsing.guess_datetime_format(string)
    assert result == fmt


@pytest.mark.parametrize("dayfirst,expected", [(True, "%d/%m/%Y"), (False, "%m/%d/%Y")])
def test_guess_datetime_format_with_dayfirst(dayfirst, expected):
    ambiguous_string = "01/01/2011"
    result = parsing.guess_datetime_format(ambiguous_string, dayfirst=dayfirst)
    assert result == expected


@td.skip_if_not_us_locale
@pytest.mark.parametrize(
    "string,fmt",
    [
        ("30/Dec/2011", "%d/%b/%Y"),
        ("30/December/2011", "%d/%B/%Y"),
        ("30/Dec/2011 00:00:00", "%d/%b/%Y %H:%M:%S"),
    ],
)
def test_guess_datetime_format_with_locale_specific_formats(string, fmt):
    result = parsing.guess_datetime_format(string)
    assert result == fmt


@pytest.mark.parametrize(
    "invalid_dt",
    [
        "01/2013",
        "12:00:00",
        "1/1/1/1",
        "this_is_not_a_datetime",
        "51a",
        "13/2019",
        "202001",  # YYYYMM isn't ISO8601
        "2020/01",  # YYYY/MM isn't ISO8601 either
        "87156549591102612381000001219H5",
    ],
)
def test_guess_datetime_format_invalid_inputs(invalid_dt):
    # A datetime string must include a year, month and a day for it to be
    # guessable, in addition to being a string that looks like a datetime.
    assert parsing.guess_datetime_format(invalid_dt) is None


@pytest.mark.parametrize("invalid_type_dt", [9, datetime(2011, 1, 1)])
def test_guess_datetime_format_wrong_type_inputs(invalid_type_dt):
    # A datetime string must include a year, month and a day for it to be
    # guessable, in addition to being a string that looks like a datetime.
    with pytest.raises(
        TypeError,
        match=r"^Argument 'dt_str' has incorrect type \(expected str, got .*\)$",
    ):
        parsing.guess_datetime_format(invalid_type_dt)


@pytest.mark.parametrize(
    "string,fmt,dayfirst,warning",
    [
        ("2011-1-1", "%Y-%m-%d", False, None),
        ("2011-1-1", "%Y-%d-%m", True, None),
        ("1/1/2011", "%m/%d/%Y", False, None),
        ("1/1/2011", "%d/%m/%Y", True, None),
        ("30-1-2011", "%d-%m-%Y", False, UserWarning),
        ("30-1-2011", "%d-%m-%Y", True, None),
        ("2011-1-1 0:0:0", "%Y-%m-%d %H:%M:%S", False, None),
        ("2011-1-1 0:0:0", "%Y-%d-%m %H:%M:%S", True, None),
        ("2011-1-3T00:00:0", "%Y-%m-%dT%H:%M:%S", False, None),
        ("2011-1-3T00:00:0", "%Y-%d-%mT%H:%M:%S", True, None),
        ("2011-1-1 00:00:00", "%Y-%m-%d %H:%M:%S", False, None),
        ("2011-1-1 00:00:00", "%Y-%d-%m %H:%M:%S", True, None),
    ],
)
def test_guess_datetime_format_no_padding(string, fmt, dayfirst, warning):
    # see gh-11142
    msg = (
        rf"Parsing dates in {fmt} format when dayfirst=False \(the default\) "
        "was specified. "
        "Pass `dayfirst=True` or specify a format to silence this warning."
    )
    with tm.assert_produces_warning(warning, match=msg):
        result = parsing.guess_datetime_format(string, dayfirst=dayfirst)
    assert result == fmt


def test_try_parse_dates():
    arr = np.array(["5/1/2000", "6/1/2000", "7/1/2000"], dtype=object)
    result = parsing.try_parse_dates(arr, parser=lambda x: du_parse(x, dayfirst=True))

    expected = np.array([du_parse(d, dayfirst=True) for d in arr])
    tm.assert_numpy_array_equal(result, expected)


def test_parse_datetime_string_with_reso_check_instance_type_raise_exception():
    # issue 20684
    msg = "Argument 'date_string' has incorrect type (expected str, got tuple)"
    with pytest.raises(TypeError, match=re.escape(msg)):
        parse_datetime_string_with_reso((1, 2, 3))

    result = parse_datetime_string_with_reso("2019")
    expected = (datetime(2019, 1, 1), "year")
    assert result == expected


@pytest.mark.parametrize(
    "fmt,expected",
    [
        ("%Y %m %d %H:%M:%S", True),
        ("%Y/%m/%d %H:%M:%S", True),
        (r"%Y\%m\%d %H:%M:%S", True),
        ("%Y-%m-%d %H:%M:%S", True),
        ("%Y.%m.%d %H:%M:%S", True),
        ("%Y%m%d %H:%M:%S", True),
        ("%Y-%m-%dT%H:%M:%S", True),
        ("%Y-%m-%dT%H:%M:%S%z", True),
        ("%Y-%m-%dT%H:%M:%S%Z", False),
        ("%Y-%m-%dT%H:%M:%S.%f", True),
        ("%Y-%m-%dT%H:%M:%S.%f%z", True),
        ("%Y-%m-%dT%H:%M:%S.%f%Z", False),
        ("%Y%m%d", True),
        ("%Y%m", False),
        ("%Y", True),
        ("%Y-%m-%d", True),
        ("%Y-%m", True),
    ],
)
def test_is_iso_format(fmt, expected):
    # see gh-41047
    result = strptime._test_format_is_iso(fmt)
    assert result == expected


@pytest.mark.parametrize(
    "input",
    [
        "2018-01-01T00:00:00.123456789",
        "2018-01-01T00:00:00.123456",
        "2018-01-01T00:00:00.123",
    ],
)
def test_guess_datetime_format_f(input):
    # https://github.com/pandas-dev/pandas/issues/49043
    result = parsing.guess_datetime_format(input)
    expected = "%Y-%m-%dT%H:%M:%S.%f"
    assert result == expected


def _helper_hypothesis_delimited_date(call, date_string, **kwargs):
    msg, result = None, None
    try:
        result = call(date_string, **kwargs)
    except ValueError as err:
        msg = str(err)
    return msg, result


@given(DATETIME_NO_TZ)
@pytest.mark.parametrize("delimiter", list(" -./"))
@pytest.mark.parametrize("dayfirst", [True, False])
@pytest.mark.parametrize(
    "date_format",
    ["%d %m %Y", "%m %d %Y", "%m %Y", "%Y %m %d", "%y %m %d", "%Y%m%d", "%y%m%d"],
)
def test_hypothesis_delimited_date(
    request, date_format, dayfirst, delimiter, test_datetime
):
    if date_format == "%m %Y" and delimiter == ".":
        request.applymarker(
            pytest.mark.xfail(
                reason="parse_datetime_string cannot reliably tell whether "
                "e.g. %m.%Y is a float or a date",
                strict=False,
            )
        )
    date_string = test_datetime.strftime(date_format.replace(" ", delimiter))

    except_out_dateutil, result = _helper_hypothesis_delimited_date(
        parsing.py_parse_datetime_string, date_string, dayfirst=dayfirst
    )
    except_in_dateutil, expected = _helper_hypothesis_delimited_date(
        du_parse,
        date_string,
        default=datetime(1, 1, 1),
        dayfirst=dayfirst,
        yearfirst=False,
    )

    assert except_out_dateutil == except_in_dateutil
    assert result == expected
