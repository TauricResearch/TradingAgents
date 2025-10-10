from datetime import datetime

import dateutil.tz
import numpy as np
import pytest
import pytz

import pandas as pd
from pandas import (
    DatetimeIndex,
    NaT,
    Series,
)
import pandas._testing as tm


@pytest.fixture(params=["s", "ms", "us", "ns"])
def unit(request):
    return request.param


def test_get_values_for_csv():
    index = pd.date_range(freq="1D", periods=3, start="2017-01-01")

    # First, with no arguments.
    expected = np.array(["2017-01-01", "2017-01-02", "2017-01-03"], dtype=object)

    result = index._get_values_for_csv()
    tm.assert_numpy_array_equal(result, expected)

    # No NaN values, so na_rep has no effect
    result = index._get_values_for_csv(na_rep="pandas")
    tm.assert_numpy_array_equal(result, expected)

    # Make sure date formatting works
    expected = np.array(["01-2017-01", "01-2017-02", "01-2017-03"], dtype=object)

    result = index._get_values_for_csv(date_format="%m-%Y-%d")
    tm.assert_numpy_array_equal(result, expected)

    # NULL object handling should work
    index = DatetimeIndex(["2017-01-01", NaT, "2017-01-03"])
    expected = np.array(["2017-01-01", "NaT", "2017-01-03"], dtype=object)

    result = index._get_values_for_csv(na_rep="NaT")
    tm.assert_numpy_array_equal(result, expected)

    expected = np.array(["2017-01-01", "pandas", "2017-01-03"], dtype=object)

    result = index._get_values_for_csv(na_rep="pandas")
    tm.assert_numpy_array_equal(result, expected)

    result = index._get_values_for_csv(na_rep="NaT", date_format="%Y-%m-%d %H:%M:%S.%f")
    expected = np.array(
        ["2017-01-01 00:00:00.000000", "NaT", "2017-01-03 00:00:00.000000"],
        dtype=object,
    )
    tm.assert_numpy_array_equal(result, expected)

    # invalid format
    result = index._get_values_for_csv(na_rep="NaT", date_format="foo")
    expected = np.array(["foo", "NaT", "foo"], dtype=object)
    tm.assert_numpy_array_equal(result, expected)


class TestDatetimeIndexRendering:
    @pytest.mark.parametrize("tzstr", ["US/Eastern", "dateutil/US/Eastern"])
    def test_dti_with_timezone_repr(self, tzstr):
        rng = pd.date_range("4/13/2010", "5/6/2010")

        rng_eastern = rng.tz_localize(tzstr)

        rng_repr = repr(rng_eastern)
        assert "2010-04-13 00:00:00" in rng_repr

    def test_dti_repr_dates(self):
        text = str(pd.to_datetime([datetime(2013, 1, 1), datetime(2014, 1, 1)]))
        assert "['2013-01-01'," in text
        assert ", '2014-01-01']" in text

    def test_dti_repr_mixed(self):
        text = str(
            pd.to_datetime(
                [datetime(2013, 1, 1), datetime(2014, 1, 1, 12), datetime(2014, 1, 1)]
            )
        )
        assert "'2013-01-01 00:00:00'," in text
        assert "'2014-01-01 00:00:00']" in text

    def test_dti_repr_short(self):
        dr = pd.date_range(start="1/1/2012", periods=1)
        repr(dr)

        dr = pd.date_range(start="1/1/2012", periods=2)
        repr(dr)

        dr = pd.date_range(start="1/1/2012", periods=3)
        repr(dr)

    @pytest.mark.parametrize(
        "dates, freq, expected_repr",
        [
            (
                ["2012-01-01 00:00:00"],
                "60min",
                (
                    "DatetimeIndex(['2012-01-01 00:00:00'], "
                    "dtype='datetime64[ns]', freq='60min')"
                ),
            ),
            (
                ["2012-01-01 00:00:00", "2012-01-01 01:00:00"],
                "60min",
                "DatetimeIndex(['2012-01-01 00:00:00', '2012-01-01 01:00:00'], "
                "dtype='datetime64[ns]', freq='60min')",
            ),
            (
                ["2012-01-01"],
                "24h",
                "DatetimeIndex(['2012-01-01'], dtype='datetime64[ns]', freq='24h')",
            ),
        ],
    )
    def test_dti_repr_time_midnight(self, dates, freq, expected_repr, unit):
        # GH53634
        dti = DatetimeIndex(dates, freq).as_unit(unit)
        actual_repr = repr(dti)
        assert actual_repr == expected_repr.replace("[ns]", f"[{unit}]")

    def test_dti_representation(self, unit):
        idxs = []
        idxs.append(DatetimeIndex([], freq="D"))
        idxs.append(DatetimeIndex(["2011-01-01"], freq="D"))
        idxs.append(DatetimeIndex(["2011-01-01", "2011-01-02"], freq="D"))
        idxs.append(DatetimeIndex(["2011-01-01", "2011-01-02", "2011-01-03"], freq="D"))
        idxs.append(
            DatetimeIndex(
                ["2011-01-01 09:00", "2011-01-01 10:00", "2011-01-01 11:00"],
                freq="h",
                tz="Asia/Tokyo",
            )
        )
        idxs.append(
            DatetimeIndex(
                ["2011-01-01 09:00", "2011-01-01 10:00", NaT], tz="US/Eastern"
            )
        )
        idxs.append(
            DatetimeIndex(["2011-01-01 09:00", "2011-01-01 10:00", NaT], tz="UTC")
        )

        exp = []
        exp.append("DatetimeIndex([], dtype='datetime64[ns]', freq='D')")
        exp.append("DatetimeIndex(['2011-01-01'], dtype='datetime64[ns]', freq='D')")
        exp.append(
            "DatetimeIndex(['2011-01-01', '2011-01-02'], "
            "dtype='datetime64[ns]', freq='D')"
        )
        exp.append(
            "DatetimeIndex(['2011-01-01', '2011-01-02', '2011-01-03'], "
            "dtype='datetime64[ns]', freq='D')"
        )
        exp.append(
            "DatetimeIndex(['2011-01-01 09:00:00+09:00', "
            "'2011-01-01 10:00:00+09:00', '2011-01-01 11:00:00+09:00']"
            ", dtype='datetime64[ns, Asia/Tokyo]', freq='h')"
        )
        exp.append(
            "DatetimeIndex(['2011-01-01 09:00:00-05:00', "
            "'2011-01-01 10:00:00-05:00', 'NaT'], "
            "dtype='datetime64[ns, US/Eastern]', freq=None)"
        )
        exp.append(
            "DatetimeIndex(['2011-01-01 09:00:00+00:00', "
            "'2011-01-01 10:00:00+00:00', 'NaT'], "
            "dtype='datetime64[ns, UTC]', freq=None)"
            ""
        )

        with pd.option_context("display.width", 300):
            for index, expected in zip(idxs, exp):
                index = index.as_unit(unit)
                expected = expected.replace("[ns", f"[{unit}")
                result = repr(index)
                assert result == expected
                result = str(index)
                assert result == expected

    # TODO: this is a Series.__repr__ test
    def test_dti_representation_to_series(self, unit):
        idx1 = DatetimeIndex([], freq="D")
        idx2 = DatetimeIndex(["2011-01-01"], freq="D")
        idx3 = DatetimeIndex(["2011-01-01", "2011-01-02"], freq="D")
        idx4 = DatetimeIndex(["2011-01-01", "2011-01-02", "2011-01-03"], freq="D")
        idx5 = DatetimeIndex(
            ["2011-01-01 09:00", "2011-01-01 10:00", "2011-01-01 11:00"],
            freq="h",
            tz="Asia/Tokyo",
        )
        idx6 = DatetimeIndex(
            ["2011-01-01 09:00", "2011-01-01 10:00", NaT], tz="US/Eastern"
        )
        idx7 = DatetimeIndex(["2011-01-01 09:00", "2011-01-02 10:15"])

        exp1 = """Series([], dtype: datetime64[ns])"""

        exp2 = "0   2011-01-01\ndtype: datetime64[ns]"

        exp3 = "0   2011-01-01\n1   2011-01-02\ndtype: datetime64[ns]"

        exp4 = (
            "0   2011-01-01\n"
            "1   2011-01-02\n"
            "2   2011-01-03\n"
            "dtype: datetime64[ns]"
        )

        exp5 = (
            "0   2011-01-01 09:00:00+09:00\n"
            "1   2011-01-01 10:00:00+09:00\n"
            "2   2011-01-01 11:00:00+09:00\n"
            "dtype: datetime64[ns, Asia/Tokyo]"
        )

        exp6 = (
            "0   2011-01-01 09:00:00-05:00\n"
            "1   2011-01-01 10:00:00-05:00\n"
            "2                         NaT\n"
            "dtype: datetime64[ns, US/Eastern]"
        )

        exp7 = (
            "0   2011-01-01 09:00:00\n"
            "1   2011-01-02 10:15:00\n"
            "dtype: datetime64[ns]"
        )

        with pd.option_context("display.width", 300):
            for idx, expected in zip(
                [idx1, idx2, idx3, idx4, idx5, idx6, idx7],
                [exp1, exp2, exp3, exp4, exp5, exp6, exp7],
            ):
                ser = Series(idx.as_unit(unit))
                result = repr(ser)
                assert result == expected.replace("[ns", f"[{unit}")

    def test_dti_summary(self):
        # GH#9116
        idx1 = DatetimeIndex([], freq="D")
        idx2 = DatetimeIndex(["2011-01-01"], freq="D")
        idx3 = DatetimeIndex(["2011-01-01", "2011-01-02"], freq="D")
        idx4 = DatetimeIndex(["2011-01-01", "2011-01-02", "2011-01-03"], freq="D")
        idx5 = DatetimeIndex(
            ["2011-01-01 09:00", "2011-01-01 10:00", "2011-01-01 11:00"],
            freq="h",
            tz="Asia/Tokyo",
        )
        idx6 = DatetimeIndex(
            ["2011-01-01 09:00", "2011-01-01 10:00", NaT], tz="US/Eastern"
        )

        exp1 = "DatetimeIndex: 0 entries\nFreq: D"

        exp2 = "DatetimeIndex: 1 entries, 2011-01-01 to 2011-01-01\nFreq: D"

        exp3 = "DatetimeIndex: 2 entries, 2011-01-01 to 2011-01-02\nFreq: D"

        exp4 = "DatetimeIndex: 3 entries, 2011-01-01 to 2011-01-03\nFreq: D"

        exp5 = (
            "DatetimeIndex: 3 entries, 2011-01-01 09:00:00+09:00 "
            "to 2011-01-01 11:00:00+09:00\n"
            "Freq: h"
        )

        exp6 = """DatetimeIndex: 3 entries, 2011-01-01 09:00:00-05:00 to NaT"""

        for idx, expected in zip(
            [idx1, idx2, idx3, idx4, idx5, idx6], [exp1, exp2, exp3, exp4, exp5, exp6]
        ):
            result = idx._summary()
            assert result == expected

    @pytest.mark.parametrize("tz", [None, pytz.utc, dateutil.tz.tzutc()])
    @pytest.mark.parametrize("freq", ["B", "C"])
    def test_dti_business_repr_etc_smoke(self, tz, freq):
        # only really care that it works
        dti = pd.bdate_range(
            datetime(2009, 1, 1), datetime(2010, 1, 1), tz=tz, freq=freq
        )
        repr(dti)
        dti._summary()
        dti[2:2]._summary()


class TestFormat:
    def test_format(self):
        # GH#35439
        idx = pd.date_range("20130101", periods=5)
        expected = [f"{x:%Y-%m-%d}" for x in idx]
        msg = r"DatetimeIndex\.format is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert idx.format() == expected

    def test_format_with_name_time_info(self):
        # bug I fixed 12/20/2011
        dates = pd.date_range("2011-01-01 04:00:00", periods=10, name="something")

        msg = "DatetimeIndex.format is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            formatted = dates.format(name=True)
        assert formatted[0] == "something"

    def test_format_datetime_with_time(self):
        dti = DatetimeIndex([datetime(2012, 2, 7), datetime(2012, 2, 7, 23)])

        msg = "DatetimeIndex.format is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = dti.format()
        expected = ["2012-02-07 00:00:00", "2012-02-07 23:00:00"]
        assert len(result) == 2
        assert result == expected

    def test_format_datetime(self):
        msg = "DatetimeIndex.format is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            formatted = pd.to_datetime([datetime(2003, 1, 1, 12), NaT]).format()
        assert formatted[0] == "2003-01-01 12:00:00"
        assert formatted[1] == "NaT"

    def test_format_date(self):
        msg = "DatetimeIndex.format is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            formatted = pd.to_datetime([datetime(2003, 1, 1), NaT]).format()
        assert formatted[0] == "2003-01-01"
        assert formatted[1] == "NaT"

    def test_format_date_tz(self):
        dti = pd.to_datetime([datetime(2013, 1, 1)], utc=True)
        msg = "DatetimeIndex.format is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            formatted = dti.format()
        assert formatted[0] == "2013-01-01 00:00:00+00:00"

        dti = pd.to_datetime([datetime(2013, 1, 1), NaT], utc=True)
        with tm.assert_produces_warning(FutureWarning, match=msg):
            formatted = dti.format()
        assert formatted[0] == "2013-01-01 00:00:00+00:00"

    def test_format_date_explicit_date_format(self):
        dti = pd.to_datetime([datetime(2003, 2, 1), NaT])
        msg = "DatetimeIndex.format is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            formatted = dti.format(date_format="%m-%d-%Y", na_rep="UT")
        assert formatted[0] == "02-01-2003"
        assert formatted[1] == "UT"
