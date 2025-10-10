from datetime import (
    datetime,
    timezone,
)

import dateutil.parser
import dateutil.tz
from dateutil.tz import tzlocal
import numpy as np

from pandas import (
    DatetimeIndex,
    date_range,
    to_datetime,
)
import pandas._testing as tm
from pandas.tests.indexes.datetimes.test_timezones import FixedOffset

fixed_off = FixedOffset(-420, "-07:00")


class TestToPyDatetime:
    def test_dti_to_pydatetime(self):
        dt = dateutil.parser.parse("2012-06-13T01:39:00Z")
        dt = dt.replace(tzinfo=tzlocal())

        arr = np.array([dt], dtype=object)

        result = to_datetime(arr, utc=True)
        assert result.tz is timezone.utc

        rng = date_range("2012-11-03 03:00", "2012-11-05 03:00", tz=tzlocal())
        arr = rng.to_pydatetime()
        result = to_datetime(arr, utc=True)
        assert result.tz is timezone.utc

    def test_dti_to_pydatetime_fizedtz(self):
        dates = np.array(
            [
                datetime(2000, 1, 1, tzinfo=fixed_off),
                datetime(2000, 1, 2, tzinfo=fixed_off),
                datetime(2000, 1, 3, tzinfo=fixed_off),
            ]
        )
        dti = DatetimeIndex(dates)

        result = dti.to_pydatetime()
        tm.assert_numpy_array_equal(dates, result)

        result = dti._mpl_repr()
        tm.assert_numpy_array_equal(dates, result)
