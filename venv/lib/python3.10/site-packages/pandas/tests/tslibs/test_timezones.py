from datetime import (
    datetime,
    timedelta,
    timezone,
)

import dateutil.tz
import pytest
import pytz

from pandas._libs.tslibs import (
    conversion,
    timezones,
)
from pandas.compat import is_platform_windows

from pandas import Timestamp


def test_is_utc(utc_fixture):
    tz = timezones.maybe_get_tz(utc_fixture)
    assert timezones.is_utc(tz)


@pytest.mark.parametrize("tz_name", list(pytz.common_timezones))
def test_cache_keys_are_distinct_for_pytz_vs_dateutil(tz_name):
    tz_p = timezones.maybe_get_tz(tz_name)
    tz_d = timezones.maybe_get_tz("dateutil/" + tz_name)

    if tz_d is None:
        pytest.skip(tz_name + ": dateutil does not know about this one")

    if not (tz_name == "UTC" and is_platform_windows()):
        # they both end up as tzwin("UTC") on windows
        assert timezones._p_tz_cache_key(tz_p) != timezones._p_tz_cache_key(tz_d)


def test_tzlocal_repr():
    # see gh-13583
    ts = Timestamp("2011-01-01", tz=dateutil.tz.tzlocal())
    assert ts.tz == dateutil.tz.tzlocal()
    assert "tz='tzlocal()')" in repr(ts)


def test_tzlocal_maybe_get_tz():
    # see gh-13583
    tz = timezones.maybe_get_tz("tzlocal()")
    assert tz == dateutil.tz.tzlocal()


def test_tzlocal_offset():
    # see gh-13583
    #
    # Get offset using normal datetime for test.
    ts = Timestamp("2011-01-01", tz=dateutil.tz.tzlocal())

    offset = dateutil.tz.tzlocal().utcoffset(datetime(2011, 1, 1))
    offset = offset.total_seconds()

    assert ts._value + offset == Timestamp("2011-01-01")._value


def test_tzlocal_is_not_utc():
    # even if the machine running the test is localized to UTC
    tz = dateutil.tz.tzlocal()
    assert not timezones.is_utc(tz)

    assert not timezones.tz_compare(tz, dateutil.tz.tzutc())


def test_tz_compare_utc(utc_fixture, utc_fixture2):
    tz = timezones.maybe_get_tz(utc_fixture)
    tz2 = timezones.maybe_get_tz(utc_fixture2)
    assert timezones.tz_compare(tz, tz2)


@pytest.fixture(
    params=[
        (pytz.timezone("US/Eastern"), lambda tz, x: tz.localize(x)),
        (dateutil.tz.gettz("US/Eastern"), lambda tz, x: x.replace(tzinfo=tz)),
    ]
)
def infer_setup(request):
    eastern, localize = request.param

    start_naive = datetime(2001, 1, 1)
    end_naive = datetime(2009, 1, 1)

    start = localize(eastern, start_naive)
    end = localize(eastern, end_naive)

    return eastern, localize, start, end, start_naive, end_naive


def test_infer_tz_compat(infer_setup):
    eastern, _, start, end, start_naive, end_naive = infer_setup

    assert (
        timezones.infer_tzinfo(start, end)
        is conversion.localize_pydatetime(start_naive, eastern).tzinfo
    )
    assert (
        timezones.infer_tzinfo(start, None)
        is conversion.localize_pydatetime(start_naive, eastern).tzinfo
    )
    assert (
        timezones.infer_tzinfo(None, end)
        is conversion.localize_pydatetime(end_naive, eastern).tzinfo
    )


def test_infer_tz_utc_localize(infer_setup):
    _, _, start, end, start_naive, end_naive = infer_setup
    utc = pytz.utc

    start = utc.localize(start_naive)
    end = utc.localize(end_naive)

    assert timezones.infer_tzinfo(start, end) is utc


@pytest.mark.parametrize("ordered", [True, False])
def test_infer_tz_mismatch(infer_setup, ordered):
    eastern, _, _, _, start_naive, end_naive = infer_setup
    msg = "Inputs must both have the same timezone"

    utc = pytz.utc
    start = utc.localize(start_naive)
    end = conversion.localize_pydatetime(end_naive, eastern)

    args = (start, end) if ordered else (end, start)

    with pytest.raises(AssertionError, match=msg):
        timezones.infer_tzinfo(*args)


def test_maybe_get_tz_invalid_types():
    with pytest.raises(TypeError, match="<class 'float'>"):
        timezones.maybe_get_tz(44.0)

    with pytest.raises(TypeError, match="<class 'module'>"):
        timezones.maybe_get_tz(pytz)

    msg = "<class 'pandas._libs.tslibs.timestamps.Timestamp'>"
    with pytest.raises(TypeError, match=msg):
        timezones.maybe_get_tz(Timestamp("2021-01-01", tz="UTC"))


def test_maybe_get_tz_offset_only():
    # see gh-36004

    # timezone.utc
    tz = timezones.maybe_get_tz(timezone.utc)
    assert tz == timezone(timedelta(hours=0, minutes=0))

    # without UTC+- prefix
    tz = timezones.maybe_get_tz("+01:15")
    assert tz == timezone(timedelta(hours=1, minutes=15))

    tz = timezones.maybe_get_tz("-01:15")
    assert tz == timezone(-timedelta(hours=1, minutes=15))

    # with UTC+- prefix
    tz = timezones.maybe_get_tz("UTC+02:45")
    assert tz == timezone(timedelta(hours=2, minutes=45))

    tz = timezones.maybe_get_tz("UTC-02:45")
    assert tz == timezone(-timedelta(hours=2, minutes=45))
