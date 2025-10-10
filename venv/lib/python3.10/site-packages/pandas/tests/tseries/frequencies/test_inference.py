from datetime import (
    datetime,
    timedelta,
)

import numpy as np
import pytest

from pandas._libs.tslibs.ccalendar import (
    DAYS,
    MONTHS,
)
from pandas._libs.tslibs.offsets import _get_offset
from pandas._libs.tslibs.period import INVALID_FREQ_ERR_MSG
from pandas.compat import is_platform_windows

from pandas import (
    DatetimeIndex,
    Index,
    RangeIndex,
    Series,
    Timestamp,
    date_range,
    period_range,
)
import pandas._testing as tm
from pandas.core.arrays import (
    DatetimeArray,
    TimedeltaArray,
)
from pandas.core.tools.datetimes import to_datetime

from pandas.tseries import (
    frequencies,
    offsets,
)


@pytest.fixture(
    params=[
        (timedelta(1), "D"),
        (timedelta(hours=1), "h"),
        (timedelta(minutes=1), "min"),
        (timedelta(seconds=1), "s"),
        (np.timedelta64(1, "ns"), "ns"),
        (timedelta(microseconds=1), "us"),
        (timedelta(microseconds=1000), "ms"),
    ]
)
def base_delta_code_pair(request):
    return request.param


freqs = (
    [f"QE-{month}" for month in MONTHS]
    + [f"{annual}-{month}" for annual in ["YE", "BYE"] for month in MONTHS]
    + ["ME", "BME", "BMS"]
    + [f"WOM-{count}{day}" for count in range(1, 5) for day in DAYS]
    + [f"W-{day}" for day in DAYS]
)


@pytest.mark.parametrize("freq", freqs)
@pytest.mark.parametrize("periods", [5, 7])
def test_infer_freq_range(periods, freq):
    freq = freq.upper()

    gen = date_range("1/1/2000", periods=periods, freq=freq)
    index = DatetimeIndex(gen.values)

    if not freq.startswith("QE-"):
        assert frequencies.infer_freq(index) == gen.freqstr
    else:
        inf_freq = frequencies.infer_freq(index)
        is_dec_range = inf_freq == "QE-DEC" and gen.freqstr in (
            "QE",
            "QE-DEC",
            "QE-SEP",
            "QE-JUN",
            "QE-MAR",
        )
        is_nov_range = inf_freq == "QE-NOV" and gen.freqstr in (
            "QE-NOV",
            "QE-AUG",
            "QE-MAY",
            "QE-FEB",
        )
        is_oct_range = inf_freq == "QE-OCT" and gen.freqstr in (
            "QE-OCT",
            "QE-JUL",
            "QE-APR",
            "QE-JAN",
        )
        assert is_dec_range or is_nov_range or is_oct_range


def test_raise_if_period_index():
    index = period_range(start="1/1/1990", periods=20, freq="M")
    msg = "Check the `freq` attribute instead of using infer_freq"

    with pytest.raises(TypeError, match=msg):
        frequencies.infer_freq(index)


def test_raise_if_too_few():
    index = DatetimeIndex(["12/31/1998", "1/3/1999"])
    msg = "Need at least 3 dates to infer frequency"

    with pytest.raises(ValueError, match=msg):
        frequencies.infer_freq(index)


def test_business_daily():
    index = DatetimeIndex(["01/01/1999", "1/4/1999", "1/5/1999"])
    assert frequencies.infer_freq(index) == "B"


def test_business_daily_look_alike():
    # see gh-16624
    #
    # Do not infer "B when "weekend" (2-day gap) in wrong place.
    index = DatetimeIndex(["12/31/1998", "1/3/1999", "1/4/1999"])
    assert frequencies.infer_freq(index) is None


def test_day_corner():
    index = DatetimeIndex(["1/1/2000", "1/2/2000", "1/3/2000"])
    assert frequencies.infer_freq(index) == "D"


def test_non_datetime_index():
    dates = to_datetime(["1/1/2000", "1/2/2000", "1/3/2000"])
    assert frequencies.infer_freq(dates) == "D"


def test_fifth_week_of_month_infer():
    # see gh-9425
    #
    # Only attempt to infer up to WOM-4.
    index = DatetimeIndex(["2014-03-31", "2014-06-30", "2015-03-30"])
    assert frequencies.infer_freq(index) is None


def test_week_of_month_fake():
    # All of these dates are on same day
    # of week and are 4 or 5 weeks apart.
    index = DatetimeIndex(["2013-08-27", "2013-10-01", "2013-10-29", "2013-11-26"])
    assert frequencies.infer_freq(index) != "WOM-4TUE"


def test_fifth_week_of_month():
    # see gh-9425
    #
    # Only supports freq up to WOM-4.
    msg = (
        "Of the four parameters: start, end, periods, "
        "and freq, exactly three must be specified"
    )

    with pytest.raises(ValueError, match=msg):
        date_range("2014-01-01", freq="WOM-5MON")


def test_monthly_ambiguous():
    rng = DatetimeIndex(["1/31/2000", "2/29/2000", "3/31/2000"])
    assert rng.inferred_freq == "ME"


def test_annual_ambiguous():
    rng = DatetimeIndex(["1/31/2000", "1/31/2001", "1/31/2002"])
    assert rng.inferred_freq == "YE-JAN"


@pytest.mark.parametrize("count", range(1, 5))
def test_infer_freq_delta(base_delta_code_pair, count):
    b = Timestamp(datetime.now())
    base_delta, code = base_delta_code_pair

    inc = base_delta * count
    index = DatetimeIndex([b + inc * j for j in range(3)])

    exp_freq = f"{count:d}{code}" if count > 1 else code
    assert frequencies.infer_freq(index) == exp_freq


@pytest.mark.parametrize(
    "constructor",
    [
        lambda now, delta: DatetimeIndex(
            [now + delta * 7] + [now + delta * j for j in range(3)]
        ),
        lambda now, delta: DatetimeIndex(
            [now + delta * j for j in range(3)] + [now + delta * 7]
        ),
    ],
)
def test_infer_freq_custom(base_delta_code_pair, constructor):
    b = Timestamp(datetime.now())
    base_delta, _ = base_delta_code_pair

    index = constructor(b, base_delta)
    assert frequencies.infer_freq(index) is None


@pytest.mark.parametrize(
    "freq,expected", [("Q", "QE-DEC"), ("Q-NOV", "QE-NOV"), ("Q-OCT", "QE-OCT")]
)
def test_infer_freq_index(freq, expected):
    rng = period_range("1959Q2", "2009Q3", freq=freq)
    with tm.assert_produces_warning(FutureWarning, match="Dtype inference"):
        rng = Index(rng.to_timestamp("D", how="e").astype(object))

    assert rng.inferred_freq == expected


@pytest.mark.parametrize(
    "expected,dates",
    list(
        {
            "YS-JAN": ["2009-01-01", "2010-01-01", "2011-01-01", "2012-01-01"],
            "QE-OCT": ["2009-01-31", "2009-04-30", "2009-07-31", "2009-10-31"],
            "ME": ["2010-11-30", "2010-12-31", "2011-01-31", "2011-02-28"],
            "W-SAT": ["2010-12-25", "2011-01-01", "2011-01-08", "2011-01-15"],
            "D": ["2011-01-01", "2011-01-02", "2011-01-03", "2011-01-04"],
            "h": [
                "2011-12-31 22:00",
                "2011-12-31 23:00",
                "2012-01-01 00:00",
                "2012-01-01 01:00",
            ],
        }.items()
    ),
)
@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_infer_freq_tz(tz_naive_fixture, expected, dates, unit):
    # see gh-7310, GH#55609
    tz = tz_naive_fixture
    idx = DatetimeIndex(dates, tz=tz).as_unit(unit)
    assert idx.inferred_freq == expected


def test_infer_freq_tz_series(tz_naive_fixture):
    # infer_freq should work with both tz-naive and tz-aware series. See gh-52456
    tz = tz_naive_fixture
    idx = date_range("2021-01-01", "2021-01-04", tz=tz)
    series = idx.to_series().reset_index(drop=True)
    inferred_freq = frequencies.infer_freq(series)
    assert inferred_freq == "D"


@pytest.mark.parametrize(
    "date_pair",
    [
        ["2013-11-02", "2013-11-5"],  # Fall DST
        ["2014-03-08", "2014-03-11"],  # Spring DST
        ["2014-01-01", "2014-01-03"],  # Regular Time
    ],
)
@pytest.mark.parametrize(
    "freq",
    ["h", "3h", "10min", "3601s", "3600001ms", "3600000001us", "3600000000001ns"],
)
def test_infer_freq_tz_transition(tz_naive_fixture, date_pair, freq):
    # see gh-8772
    tz = tz_naive_fixture
    idx = date_range(date_pair[0], date_pair[1], freq=freq, tz=tz)
    assert idx.inferred_freq == freq


def test_infer_freq_tz_transition_custom():
    index = date_range("2013-11-03", periods=5, freq="3h").tz_localize(
        "America/Chicago"
    )
    assert index.inferred_freq is None


@pytest.mark.parametrize(
    "data,expected",
    [
        # Hourly freq in a day must result in "h"
        (
            [
                "2014-07-01 09:00",
                "2014-07-01 10:00",
                "2014-07-01 11:00",
                "2014-07-01 12:00",
                "2014-07-01 13:00",
                "2014-07-01 14:00",
            ],
            "h",
        ),
        (
            [
                "2014-07-01 09:00",
                "2014-07-01 10:00",
                "2014-07-01 11:00",
                "2014-07-01 12:00",
                "2014-07-01 13:00",
                "2014-07-01 14:00",
                "2014-07-01 15:00",
                "2014-07-01 16:00",
                "2014-07-02 09:00",
                "2014-07-02 10:00",
                "2014-07-02 11:00",
            ],
            "bh",
        ),
        (
            [
                "2014-07-04 09:00",
                "2014-07-04 10:00",
                "2014-07-04 11:00",
                "2014-07-04 12:00",
                "2014-07-04 13:00",
                "2014-07-04 14:00",
                "2014-07-04 15:00",
                "2014-07-04 16:00",
                "2014-07-07 09:00",
                "2014-07-07 10:00",
                "2014-07-07 11:00",
            ],
            "bh",
        ),
        (
            [
                "2014-07-04 09:00",
                "2014-07-04 10:00",
                "2014-07-04 11:00",
                "2014-07-04 12:00",
                "2014-07-04 13:00",
                "2014-07-04 14:00",
                "2014-07-04 15:00",
                "2014-07-04 16:00",
                "2014-07-07 09:00",
                "2014-07-07 10:00",
                "2014-07-07 11:00",
                "2014-07-07 12:00",
                "2014-07-07 13:00",
                "2014-07-07 14:00",
                "2014-07-07 15:00",
                "2014-07-07 16:00",
                "2014-07-08 09:00",
                "2014-07-08 10:00",
                "2014-07-08 11:00",
                "2014-07-08 12:00",
                "2014-07-08 13:00",
                "2014-07-08 14:00",
                "2014-07-08 15:00",
                "2014-07-08 16:00",
            ],
            "bh",
        ),
    ],
)
def test_infer_freq_business_hour(data, expected):
    # see gh-7905
    idx = DatetimeIndex(data)
    assert idx.inferred_freq == expected


def test_not_monotonic():
    rng = DatetimeIndex(["1/31/2000", "1/31/2001", "1/31/2002"])
    rng = rng[::-1]

    assert rng.inferred_freq == "-1YE-JAN"


def test_non_datetime_index2():
    rng = DatetimeIndex(["1/31/2000", "1/31/2001", "1/31/2002"])
    vals = rng.to_pydatetime()

    result = frequencies.infer_freq(vals)
    assert result == rng.inferred_freq


@pytest.mark.parametrize(
    "idx",
    [
        Index(np.arange(5), dtype=np.int64),
        Index(np.arange(5), dtype=np.float64),
        period_range("2020-01-01", periods=5),
        RangeIndex(5),
    ],
)
def test_invalid_index_types(idx):
    # see gh-48439
    msg = "|".join(
        [
            "cannot infer freq from a non-convertible",
            "Check the `freq` attribute instead of using infer_freq",
        ]
    )

    with pytest.raises(TypeError, match=msg):
        frequencies.infer_freq(idx)


@pytest.mark.skipif(is_platform_windows(), reason="see gh-10822: Windows issue")
def test_invalid_index_types_unicode():
    # see gh-10822
    #
    # Odd error message on conversions to datetime for unicode.
    msg = "Unknown datetime string format"

    with pytest.raises(ValueError, match=msg):
        frequencies.infer_freq(Index(["ZqgszYBfuL"]))


def test_string_datetime_like_compat():
    # see gh-6463
    data = ["2004-01", "2004-02", "2004-03", "2004-04"]

    expected = frequencies.infer_freq(data)
    result = frequencies.infer_freq(Index(data))

    assert result == expected


def test_series():
    # see gh-6407
    s = Series(date_range("20130101", "20130110"))
    inferred = frequencies.infer_freq(s)
    assert inferred == "D"


@pytest.mark.parametrize("end", [10, 10.0])
def test_series_invalid_type(end):
    # see gh-6407
    msg = "cannot infer freq from a non-convertible dtype on a Series"
    s = Series(np.arange(end))

    with pytest.raises(TypeError, match=msg):
        frequencies.infer_freq(s)


def test_series_inconvertible_string(using_infer_string):
    # see gh-6407
    if using_infer_string:
        msg = "cannot infer freq from"

        with pytest.raises(TypeError, match=msg):
            frequencies.infer_freq(Series(["foo", "bar"]))
    else:
        msg = "Unknown datetime string format"

        with pytest.raises(ValueError, match=msg):
            frequencies.infer_freq(Series(["foo", "bar"]))


@pytest.mark.parametrize("freq", [None, "ms"])
def test_series_period_index(freq):
    # see gh-6407
    #
    # Cannot infer on PeriodIndex
    msg = "cannot infer freq from a non-convertible dtype on a Series"
    s = Series(period_range("2013", periods=10, freq=freq))

    with pytest.raises(TypeError, match=msg):
        frequencies.infer_freq(s)


@pytest.mark.parametrize("freq", ["ME", "ms", "s"])
def test_series_datetime_index(freq):
    s = Series(date_range("20130101", periods=10, freq=freq))
    inferred = frequencies.infer_freq(s)
    assert inferred == freq


@pytest.mark.parametrize(
    "offset_func",
    [
        _get_offset,
        lambda freq: date_range("2011-01-01", periods=5, freq=freq),
    ],
)
@pytest.mark.parametrize(
    "freq",
    [
        "WEEKDAY",
        "EOM",
        "W@MON",
        "W@TUE",
        "W@WED",
        "W@THU",
        "W@FRI",
        "W@SAT",
        "W@SUN",
        "QE@JAN",
        "QE@FEB",
        "QE@MAR",
        "YE@JAN",
        "YE@FEB",
        "YE@MAR",
        "YE@APR",
        "YE@MAY",
        "YE@JUN",
        "YE@JUL",
        "YE@AUG",
        "YE@SEP",
        "YE@OCT",
        "YE@NOV",
        "YE@DEC",
        "YE@JAN",
        "WOM@1MON",
        "WOM@2MON",
        "WOM@3MON",
        "WOM@4MON",
        "WOM@1TUE",
        "WOM@2TUE",
        "WOM@3TUE",
        "WOM@4TUE",
        "WOM@1WED",
        "WOM@2WED",
        "WOM@3WED",
        "WOM@4WED",
        "WOM@1THU",
        "WOM@2THU",
        "WOM@3THU",
        "WOM@4THU",
        "WOM@1FRI",
        "WOM@2FRI",
        "WOM@3FRI",
        "WOM@4FRI",
    ],
)
def test_legacy_offset_warnings(offset_func, freq):
    with pytest.raises(ValueError, match=INVALID_FREQ_ERR_MSG):
        offset_func(freq)


def test_ms_vs_capital_ms():
    left = _get_offset("ms")
    right = _get_offset("MS")

    assert left == offsets.Milli()
    assert right == offsets.MonthBegin()


def test_infer_freq_non_nano():
    arr = np.arange(10).astype(np.int64).view("M8[s]")
    dta = DatetimeArray._simple_new(arr, dtype=arr.dtype)
    res = frequencies.infer_freq(dta)
    assert res == "s"

    arr2 = arr.view("m8[ms]")
    tda = TimedeltaArray._simple_new(arr2, dtype=arr2.dtype)
    res2 = frequencies.infer_freq(tda)
    assert res2 == "ms"


def test_infer_freq_non_nano_tzaware(tz_aware_fixture):
    tz = tz_aware_fixture

    dti = date_range("2016-01-01", periods=365, freq="B", tz=tz)
    dta = dti._data.as_unit("s")

    res = frequencies.infer_freq(dta)
    assert res == "B"
