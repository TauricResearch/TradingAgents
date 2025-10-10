from datetime import (
    date,
    datetime,
    timedelta,
    timezone,
)

from dateutil.tz.tz import tzoffset
import numpy as np
import pytest

from pandas._libs import (
    NaT,
    iNaT,
    tslib,
)
from pandas._libs.tslibs.dtypes import NpyDatetimeUnit
from pandas._libs.tslibs.np_datetime import OutOfBoundsDatetime

from pandas import Timestamp
import pandas._testing as tm

creso_infer = NpyDatetimeUnit.NPY_FR_GENERIC.value


class TestArrayToDatetimeResolutionInference:
    # TODO: tests that include tzs, ints

    def test_infer_all_nat(self):
        arr = np.array([NaT, np.nan], dtype=object)
        result, tz = tslib.array_to_datetime(arr, creso=creso_infer)
        assert tz is None
        assert result.dtype == "M8[s]"

    def test_infer_homogeoneous_datetimes(self):
        dt = datetime(2023, 10, 27, 18, 3, 5, 678000)
        arr = np.array([dt, dt, dt], dtype=object)
        result, tz = tslib.array_to_datetime(arr, creso=creso_infer)
        assert tz is None
        expected = np.array([dt, dt, dt], dtype="M8[us]")
        tm.assert_numpy_array_equal(result, expected)

    def test_infer_homogeoneous_date_objects(self):
        dt = datetime(2023, 10, 27, 18, 3, 5, 678000)
        dt2 = dt.date()
        arr = np.array([None, dt2, dt2, dt2], dtype=object)
        result, tz = tslib.array_to_datetime(arr, creso=creso_infer)
        assert tz is None
        expected = np.array([np.datetime64("NaT"), dt2, dt2, dt2], dtype="M8[s]")
        tm.assert_numpy_array_equal(result, expected)

    def test_infer_homogeoneous_dt64(self):
        dt = datetime(2023, 10, 27, 18, 3, 5, 678000)
        dt64 = np.datetime64(dt, "ms")
        arr = np.array([None, dt64, dt64, dt64], dtype=object)
        result, tz = tslib.array_to_datetime(arr, creso=creso_infer)
        assert tz is None
        expected = np.array([np.datetime64("NaT"), dt64, dt64, dt64], dtype="M8[ms]")
        tm.assert_numpy_array_equal(result, expected)

    def test_infer_homogeoneous_timestamps(self):
        dt = datetime(2023, 10, 27, 18, 3, 5, 678000)
        ts = Timestamp(dt).as_unit("ns")
        arr = np.array([None, ts, ts, ts], dtype=object)
        result, tz = tslib.array_to_datetime(arr, creso=creso_infer)
        assert tz is None
        expected = np.array([np.datetime64("NaT")] + [ts.asm8] * 3, dtype="M8[ns]")
        tm.assert_numpy_array_equal(result, expected)

    def test_infer_homogeoneous_datetimes_strings(self):
        item = "2023-10-27 18:03:05.678000"
        arr = np.array([None, item, item, item], dtype=object)
        result, tz = tslib.array_to_datetime(arr, creso=creso_infer)
        assert tz is None
        expected = np.array([np.datetime64("NaT"), item, item, item], dtype="M8[us]")
        tm.assert_numpy_array_equal(result, expected)

    def test_infer_heterogeneous(self):
        dtstr = "2023-10-27 18:03:05.678000"

        arr = np.array([dtstr, dtstr[:-3], dtstr[:-7], None], dtype=object)
        result, tz = tslib.array_to_datetime(arr, creso=creso_infer)
        assert tz is None
        expected = np.array(arr, dtype="M8[us]")
        tm.assert_numpy_array_equal(result, expected)

        result, tz = tslib.array_to_datetime(arr[::-1], creso=creso_infer)
        assert tz is None
        tm.assert_numpy_array_equal(result, expected[::-1])

    @pytest.mark.parametrize(
        "item", [float("nan"), NaT.value, float(NaT.value), "NaT", ""]
    )
    def test_infer_with_nat_int_float_str(self, item):
        # floats/ints get inferred to nanos *unless* they are NaN/iNaT,
        # similar NaT string gets treated like NaT scalar (ignored for resolution)
        dt = datetime(2023, 11, 15, 15, 5, 6)

        arr = np.array([dt, item], dtype=object)
        result, tz = tslib.array_to_datetime(arr, creso=creso_infer)
        assert tz is None
        expected = np.array([dt, np.datetime64("NaT")], dtype="M8[us]")
        tm.assert_numpy_array_equal(result, expected)

        result2, tz2 = tslib.array_to_datetime(arr[::-1], creso=creso_infer)
        assert tz2 is None
        tm.assert_numpy_array_equal(result2, expected[::-1])


class TestArrayToDatetimeWithTZResolutionInference:
    def test_array_to_datetime_with_tz_resolution(self):
        tz = tzoffset("custom", 3600)
        vals = np.array(["2016-01-01 02:03:04.567", NaT], dtype=object)
        res = tslib.array_to_datetime_with_tz(vals, tz, False, False, creso_infer)
        assert res.dtype == "M8[ms]"

        vals2 = np.array([datetime(2016, 1, 1, 2, 3, 4), NaT], dtype=object)
        res2 = tslib.array_to_datetime_with_tz(vals2, tz, False, False, creso_infer)
        assert res2.dtype == "M8[us]"

        vals3 = np.array([NaT, np.datetime64(12345, "s")], dtype=object)
        res3 = tslib.array_to_datetime_with_tz(vals3, tz, False, False, creso_infer)
        assert res3.dtype == "M8[s]"

    def test_array_to_datetime_with_tz_resolution_all_nat(self):
        tz = tzoffset("custom", 3600)
        vals = np.array(["NaT"], dtype=object)
        res = tslib.array_to_datetime_with_tz(vals, tz, False, False, creso_infer)
        assert res.dtype == "M8[s]"

        vals2 = np.array([NaT, NaT], dtype=object)
        res2 = tslib.array_to_datetime_with_tz(vals2, tz, False, False, creso_infer)
        assert res2.dtype == "M8[s]"


@pytest.mark.parametrize(
    "data,expected",
    [
        (
            ["01-01-2013", "01-02-2013"],
            [
                "2013-01-01T00:00:00.000000000",
                "2013-01-02T00:00:00.000000000",
            ],
        ),
        (
            ["Mon Sep 16 2013", "Tue Sep 17 2013"],
            [
                "2013-09-16T00:00:00.000000000",
                "2013-09-17T00:00:00.000000000",
            ],
        ),
    ],
)
def test_parsing_valid_dates(data, expected):
    arr = np.array(data, dtype=object)
    result, _ = tslib.array_to_datetime(arr)

    expected = np.array(expected, dtype="M8[ns]")
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize(
    "dt_string, expected_tz",
    [
        ["01-01-2013 08:00:00+08:00", 480],
        ["2013-01-01T08:00:00.000000000+0800", 480],
        ["2012-12-31T16:00:00.000000000-0800", -480],
        ["12-31-2012 23:00:00-01:00", -60],
    ],
)
def test_parsing_timezone_offsets(dt_string, expected_tz):
    # All of these datetime strings with offsets are equivalent
    # to the same datetime after the timezone offset is added.
    arr = np.array(["01-01-2013 00:00:00"], dtype=object)
    expected, _ = tslib.array_to_datetime(arr)

    arr = np.array([dt_string], dtype=object)
    result, result_tz = tslib.array_to_datetime(arr)

    tm.assert_numpy_array_equal(result, expected)
    assert result_tz == timezone(timedelta(minutes=expected_tz))


def test_parsing_non_iso_timezone_offset():
    dt_string = "01-01-2013T00:00:00.000000000+0000"
    arr = np.array([dt_string], dtype=object)

    with tm.assert_produces_warning(None):
        # GH#50949 should not get tzlocal-deprecation warning here
        result, result_tz = tslib.array_to_datetime(arr)
    expected = np.array([np.datetime64("2013-01-01 00:00:00.000000000")])

    tm.assert_numpy_array_equal(result, expected)
    assert result_tz is timezone.utc


def test_parsing_different_timezone_offsets():
    # see gh-17697
    data = ["2015-11-18 15:30:00+05:30", "2015-11-18 15:30:00+06:30"]
    data = np.array(data, dtype=object)

    msg = "parsing datetimes with mixed time zones will raise an error"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result, result_tz = tslib.array_to_datetime(data)
    expected = np.array(
        [
            datetime(2015, 11, 18, 15, 30, tzinfo=tzoffset(None, 19800)),
            datetime(2015, 11, 18, 15, 30, tzinfo=tzoffset(None, 23400)),
        ],
        dtype=object,
    )

    tm.assert_numpy_array_equal(result, expected)
    assert result_tz is None


@pytest.mark.parametrize(
    "data", [["-352.737091", "183.575577"], ["1", "2", "3", "4", "5"]]
)
def test_number_looking_strings_not_into_datetime(data):
    # see gh-4601
    #
    # These strings don't look like datetimes, so
    # they shouldn't be attempted to be converted.
    arr = np.array(data, dtype=object)
    result, _ = tslib.array_to_datetime(arr, errors="ignore")

    tm.assert_numpy_array_equal(result, arr)


@pytest.mark.parametrize(
    "invalid_date",
    [
        date(1000, 1, 1),
        datetime(1000, 1, 1),
        "1000-01-01",
        "Jan 1, 1000",
        np.datetime64("1000-01-01"),
    ],
)
@pytest.mark.parametrize("errors", ["coerce", "raise"])
def test_coerce_outside_ns_bounds(invalid_date, errors):
    arr = np.array([invalid_date], dtype="object")
    kwargs = {"values": arr, "errors": errors}

    if errors == "raise":
        msg = "^Out of bounds nanosecond timestamp: .*, at position 0$"

        with pytest.raises(OutOfBoundsDatetime, match=msg):
            tslib.array_to_datetime(**kwargs)
    else:  # coerce.
        result, _ = tslib.array_to_datetime(**kwargs)
        expected = np.array([iNaT], dtype="M8[ns]")

        tm.assert_numpy_array_equal(result, expected)


def test_coerce_outside_ns_bounds_one_valid():
    arr = np.array(["1/1/1000", "1/1/2000"], dtype=object)
    result, _ = tslib.array_to_datetime(arr, errors="coerce")

    expected = [iNaT, "2000-01-01T00:00:00.000000000"]
    expected = np.array(expected, dtype="M8[ns]")

    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize("errors", ["ignore", "coerce"])
def test_coerce_of_invalid_datetimes(errors):
    arr = np.array(["01-01-2013", "not_a_date", "1"], dtype=object)
    kwargs = {"values": arr, "errors": errors}

    if errors == "ignore":
        # Without coercing, the presence of any invalid
        # dates prevents any values from being converted.
        result, _ = tslib.array_to_datetime(**kwargs)
        tm.assert_numpy_array_equal(result, arr)
    else:  # coerce.
        # With coercing, the invalid dates becomes iNaT
        result, _ = tslib.array_to_datetime(arr, errors="coerce")
        expected = ["2013-01-01T00:00:00.000000000", iNaT, iNaT]

        tm.assert_numpy_array_equal(result, np.array(expected, dtype="M8[ns]"))


def test_to_datetime_barely_out_of_bounds():
    # see gh-19382, gh-19529
    #
    # Close enough to bounds that dropping nanos
    # would result in an in-bounds datetime.
    arr = np.array(["2262-04-11 23:47:16.854775808"], dtype=object)
    msg = "^Out of bounds nanosecond timestamp: 2262-04-11 23:47:16, at position 0$"

    with pytest.raises(tslib.OutOfBoundsDatetime, match=msg):
        tslib.array_to_datetime(arr)


@pytest.mark.parametrize(
    "timestamp",
    [
        # Close enough to bounds that scaling micros to nanos overflows
        # but adding nanos would result in an in-bounds datetime.
        "1677-09-21T00:12:43.145224193",
        "1677-09-21T00:12:43.145224999",
        # this always worked
        "1677-09-21T00:12:43.145225000",
    ],
)
def test_to_datetime_barely_inside_bounds(timestamp):
    # see gh-57150
    result, _ = tslib.array_to_datetime(np.array([timestamp], dtype=object))
    tm.assert_numpy_array_equal(result, np.array([timestamp], dtype="M8[ns]"))


class SubDatetime(datetime):
    pass


@pytest.mark.parametrize(
    "data,expected",
    [
        ([SubDatetime(2000, 1, 1)], ["2000-01-01T00:00:00.000000000"]),
        ([datetime(2000, 1, 1)], ["2000-01-01T00:00:00.000000000"]),
        ([Timestamp(2000, 1, 1)], ["2000-01-01T00:00:00.000000000"]),
    ],
)
def test_datetime_subclass(data, expected):
    # GH 25851
    # ensure that subclassed datetime works with
    # array_to_datetime

    arr = np.array(data, dtype=object)
    result, _ = tslib.array_to_datetime(arr)

    expected = np.array(expected, dtype="M8[ns]")
    tm.assert_numpy_array_equal(result, expected)
