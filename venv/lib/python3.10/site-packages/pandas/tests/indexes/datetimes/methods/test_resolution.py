from dateutil.tz import tzlocal
import pytest

from pandas.compat import IS64

from pandas import date_range


@pytest.mark.parametrize(
    "freq,expected",
    [
        ("YE", "day"),
        ("QE", "day"),
        ("ME", "day"),
        ("D", "day"),
        ("h", "hour"),
        ("min", "minute"),
        ("s", "second"),
        ("ms", "millisecond"),
        ("us", "microsecond"),
    ],
)
def test_dti_resolution(request, tz_naive_fixture, freq, expected):
    tz = tz_naive_fixture
    if freq == "YE" and not IS64 and isinstance(tz, tzlocal):
        request.applymarker(
            pytest.mark.xfail(reason="OverflowError inside tzlocal past 2038")
        )

    idx = date_range(start="2013-04-01", periods=30, freq=freq, tz=tz)
    assert idx.resolution == expected
