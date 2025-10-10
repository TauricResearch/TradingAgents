from contextlib import nullcontext
from datetime import (
    datetime,
    time,
)
import locale

import numpy as np
import pytest

import pandas as pd
from pandas import (
    PeriodIndex,
    Series,
)
import pandas._testing as tm


def get_local_am_pm():
    """Return the AM and PM strings returned by strftime in current locale."""
    am_local = time(1).strftime("%p")
    pm_local = time(13).strftime("%p")
    return am_local, pm_local


def test_get_values_for_csv():
    index = PeriodIndex(["2017-01-01", "2017-01-02", "2017-01-03"], freq="D")

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
    index = PeriodIndex(["2017-01-01", pd.NaT, "2017-01-03"], freq="D")
    expected = np.array(["2017-01-01", "NaT", "2017-01-03"], dtype=object)

    result = index._get_values_for_csv(na_rep="NaT")
    tm.assert_numpy_array_equal(result, expected)

    expected = np.array(["2017-01-01", "pandas", "2017-01-03"], dtype=object)

    result = index._get_values_for_csv(na_rep="pandas")
    tm.assert_numpy_array_equal(result, expected)


class TestPeriodIndexRendering:
    def test_format_empty(self):
        # GH#35712
        empty_idx = PeriodIndex([], freq="Y")
        msg = r"PeriodIndex\.format is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert empty_idx.format() == []
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert empty_idx.format(name=True) == [""]

    @pytest.mark.parametrize("method", ["__repr__", "__str__"])
    def test_representation(self, method):
        # GH#7601
        idx1 = PeriodIndex([], freq="D")
        idx2 = PeriodIndex(["2011-01-01"], freq="D")
        idx3 = PeriodIndex(["2011-01-01", "2011-01-02"], freq="D")
        idx4 = PeriodIndex(["2011-01-01", "2011-01-02", "2011-01-03"], freq="D")
        idx5 = PeriodIndex(["2011", "2012", "2013"], freq="Y")
        idx6 = PeriodIndex(["2011-01-01 09:00", "2012-02-01 10:00", "NaT"], freq="h")
        idx7 = pd.period_range("2013Q1", periods=1, freq="Q")
        idx8 = pd.period_range("2013Q1", periods=2, freq="Q")
        idx9 = pd.period_range("2013Q1", periods=3, freq="Q")
        idx10 = PeriodIndex(["2011-01-01", "2011-02-01"], freq="3D")

        exp1 = "PeriodIndex([], dtype='period[D]')"

        exp2 = "PeriodIndex(['2011-01-01'], dtype='period[D]')"

        exp3 = "PeriodIndex(['2011-01-01', '2011-01-02'], dtype='period[D]')"

        exp4 = (
            "PeriodIndex(['2011-01-01', '2011-01-02', '2011-01-03'], "
            "dtype='period[D]')"
        )

        exp5 = "PeriodIndex(['2011', '2012', '2013'], dtype='period[Y-DEC]')"

        exp6 = (
            "PeriodIndex(['2011-01-01 09:00', '2012-02-01 10:00', 'NaT'], "
            "dtype='period[h]')"
        )

        exp7 = "PeriodIndex(['2013Q1'], dtype='period[Q-DEC]')"

        exp8 = "PeriodIndex(['2013Q1', '2013Q2'], dtype='period[Q-DEC]')"

        exp9 = "PeriodIndex(['2013Q1', '2013Q2', '2013Q3'], dtype='period[Q-DEC]')"

        exp10 = "PeriodIndex(['2011-01-01', '2011-02-01'], dtype='period[3D]')"

        for idx, expected in zip(
            [idx1, idx2, idx3, idx4, idx5, idx6, idx7, idx8, idx9, idx10],
            [exp1, exp2, exp3, exp4, exp5, exp6, exp7, exp8, exp9, exp10],
        ):
            result = getattr(idx, method)()
            assert result == expected

    # TODO: These are Series.__repr__ tests
    def test_representation_to_series(self):
        # GH#10971
        idx1 = PeriodIndex([], freq="D")
        idx2 = PeriodIndex(["2011-01-01"], freq="D")
        idx3 = PeriodIndex(["2011-01-01", "2011-01-02"], freq="D")
        idx4 = PeriodIndex(["2011-01-01", "2011-01-02", "2011-01-03"], freq="D")
        idx5 = PeriodIndex(["2011", "2012", "2013"], freq="Y")
        idx6 = PeriodIndex(["2011-01-01 09:00", "2012-02-01 10:00", "NaT"], freq="h")

        idx7 = pd.period_range("2013Q1", periods=1, freq="Q")
        idx8 = pd.period_range("2013Q1", periods=2, freq="Q")
        idx9 = pd.period_range("2013Q1", periods=3, freq="Q")

        exp1 = """Series([], dtype: period[D])"""

        exp2 = """0    2011-01-01
dtype: period[D]"""

        exp3 = """0    2011-01-01
1    2011-01-02
dtype: period[D]"""

        exp4 = """0    2011-01-01
1    2011-01-02
2    2011-01-03
dtype: period[D]"""

        exp5 = """0    2011
1    2012
2    2013
dtype: period[Y-DEC]"""

        exp6 = """0    2011-01-01 09:00
1    2012-02-01 10:00
2                 NaT
dtype: period[h]"""

        exp7 = """0    2013Q1
dtype: period[Q-DEC]"""

        exp8 = """0    2013Q1
1    2013Q2
dtype: period[Q-DEC]"""

        exp9 = """0    2013Q1
1    2013Q2
2    2013Q3
dtype: period[Q-DEC]"""

        for idx, expected in zip(
            [idx1, idx2, idx3, idx4, idx5, idx6, idx7, idx8, idx9],
            [exp1, exp2, exp3, exp4, exp5, exp6, exp7, exp8, exp9],
        ):
            result = repr(Series(idx))
            assert result == expected

    def test_summary(self):
        # GH#9116
        idx1 = PeriodIndex([], freq="D")
        idx2 = PeriodIndex(["2011-01-01"], freq="D")
        idx3 = PeriodIndex(["2011-01-01", "2011-01-02"], freq="D")
        idx4 = PeriodIndex(["2011-01-01", "2011-01-02", "2011-01-03"], freq="D")
        idx5 = PeriodIndex(["2011", "2012", "2013"], freq="Y")
        idx6 = PeriodIndex(["2011-01-01 09:00", "2012-02-01 10:00", "NaT"], freq="h")

        idx7 = pd.period_range("2013Q1", periods=1, freq="Q")
        idx8 = pd.period_range("2013Q1", periods=2, freq="Q")
        idx9 = pd.period_range("2013Q1", periods=3, freq="Q")

        exp1 = """PeriodIndex: 0 entries
Freq: D"""

        exp2 = """PeriodIndex: 1 entries, 2011-01-01 to 2011-01-01
Freq: D"""

        exp3 = """PeriodIndex: 2 entries, 2011-01-01 to 2011-01-02
Freq: D"""

        exp4 = """PeriodIndex: 3 entries, 2011-01-01 to 2011-01-03
Freq: D"""

        exp5 = """PeriodIndex: 3 entries, 2011 to 2013
Freq: Y-DEC"""

        exp6 = """PeriodIndex: 3 entries, 2011-01-01 09:00 to NaT
Freq: h"""

        exp7 = """PeriodIndex: 1 entries, 2013Q1 to 2013Q1
Freq: Q-DEC"""

        exp8 = """PeriodIndex: 2 entries, 2013Q1 to 2013Q2
Freq: Q-DEC"""

        exp9 = """PeriodIndex: 3 entries, 2013Q1 to 2013Q3
Freq: Q-DEC"""

        for idx, expected in zip(
            [idx1, idx2, idx3, idx4, idx5, idx6, idx7, idx8, idx9],
            [exp1, exp2, exp3, exp4, exp5, exp6, exp7, exp8, exp9],
        ):
            result = idx._summary()
            assert result == expected


class TestPeriodIndexFormat:
    def test_period_format_and_strftime_default(self):
        per = PeriodIndex([datetime(2003, 1, 1, 12), None], freq="h")

        # Default formatting
        msg = "PeriodIndex.format is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            formatted = per.format()
        assert formatted[0] == "2003-01-01 12:00"  # default: minutes not shown
        assert formatted[1] == "NaT"
        # format is equivalent to strftime(None)...
        assert formatted[0] == per.strftime(None)[0]
        assert per.strftime(None)[1] is np.nan  # ...except for NaTs

        # Same test with nanoseconds freq
        per = pd.period_range("2003-01-01 12:01:01.123456789", periods=2, freq="ns")
        with tm.assert_produces_warning(FutureWarning, match=msg):
            formatted = per.format()
        assert (formatted == per.strftime(None)).all()
        assert formatted[0] == "2003-01-01 12:01:01.123456789"
        assert formatted[1] == "2003-01-01 12:01:01.123456790"

    def test_period_custom(self):
        # GH#46252 custom formatting directives %l (ms) and %u (us)
        msg = "PeriodIndex.format is deprecated"

        # 3 digits
        per = pd.period_range("2003-01-01 12:01:01.123", periods=2, freq="ms")
        with tm.assert_produces_warning(FutureWarning, match=msg):
            formatted = per.format(date_format="%y %I:%M:%S (ms=%l us=%u ns=%n)")
        assert formatted[0] == "03 12:01:01 (ms=123 us=123000 ns=123000000)"
        assert formatted[1] == "03 12:01:01 (ms=124 us=124000 ns=124000000)"

        # 6 digits
        per = pd.period_range("2003-01-01 12:01:01.123456", periods=2, freq="us")
        with tm.assert_produces_warning(FutureWarning, match=msg):
            formatted = per.format(date_format="%y %I:%M:%S (ms=%l us=%u ns=%n)")
        assert formatted[0] == "03 12:01:01 (ms=123 us=123456 ns=123456000)"
        assert formatted[1] == "03 12:01:01 (ms=123 us=123457 ns=123457000)"

        # 9 digits
        per = pd.period_range("2003-01-01 12:01:01.123456789", periods=2, freq="ns")
        with tm.assert_produces_warning(FutureWarning, match=msg):
            formatted = per.format(date_format="%y %I:%M:%S (ms=%l us=%u ns=%n)")
        assert formatted[0] == "03 12:01:01 (ms=123 us=123456 ns=123456789)"
        assert formatted[1] == "03 12:01:01 (ms=123 us=123456 ns=123456790)"

    def test_period_tz(self):
        # Formatting periods created from a datetime with timezone.
        msg = r"PeriodIndex\.format is deprecated"
        # This timestamp is in 2013 in Europe/Paris but is 2012 in UTC
        dt = pd.to_datetime(["2013-01-01 00:00:00+01:00"], utc=True)

        # Converting to a period looses the timezone information
        # Since tz is currently set as utc, we'll see 2012
        with tm.assert_produces_warning(UserWarning, match="will drop timezone"):
            per = dt.to_period(freq="h")
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert per.format()[0] == "2012-12-31 23:00"

        # If tz is currently set as paris before conversion, we'll see 2013
        dt = dt.tz_convert("Europe/Paris")
        with tm.assert_produces_warning(UserWarning, match="will drop timezone"):
            per = dt.to_period(freq="h")
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert per.format()[0] == "2013-01-01 00:00"

    @pytest.mark.parametrize(
        "locale_str",
        [
            pytest.param(None, id=str(locale.getlocale())),
            "it_IT.utf8",
            "it_IT",  # Note: encoding will be 'ISO8859-1'
            "zh_CN.utf8",
            "zh_CN",  # Note: encoding will be 'gb2312'
        ],
    )
    def test_period_non_ascii_fmt(self, locale_str):
        # GH#46468 non-ascii char in input format string leads to wrong output

        # Skip if locale cannot be set
        if locale_str is not None and not tm.can_set_locale(locale_str, locale.LC_ALL):
            pytest.skip(f"Skipping as locale '{locale_str}' cannot be set on host.")

        # Change locale temporarily for this test.
        with tm.set_locale(locale_str, locale.LC_ALL) if locale_str else nullcontext():
            # Scalar
            per = pd.Period("2018-03-11 13:00", freq="h")
            assert per.strftime("%y é") == "18 é"

            # Index
            per = pd.period_range("2003-01-01 01:00:00", periods=2, freq="12h")
            msg = "PeriodIndex.format is deprecated"
            with tm.assert_produces_warning(FutureWarning, match=msg):
                formatted = per.format(date_format="%y é")
            assert formatted[0] == "03 é"
            assert formatted[1] == "03 é"

    @pytest.mark.parametrize(
        "locale_str",
        [
            pytest.param(None, id=str(locale.getlocale())),
            "it_IT.utf8",
            "it_IT",  # Note: encoding will be 'ISO8859-1'
            "zh_CN.utf8",
            "zh_CN",  # Note: encoding will be 'gb2312'
        ],
    )
    def test_period_custom_locale_directive(self, locale_str):
        # GH#46319 locale-specific directive leads to non-utf8 c strftime char* result

        # Skip if locale cannot be set
        if locale_str is not None and not tm.can_set_locale(locale_str, locale.LC_ALL):
            pytest.skip(f"Skipping as locale '{locale_str}' cannot be set on host.")

        # Change locale temporarily for this test.
        with tm.set_locale(locale_str, locale.LC_ALL) if locale_str else nullcontext():
            # Get locale-specific reference
            am_local, pm_local = get_local_am_pm()

            # Scalar
            per = pd.Period("2018-03-11 13:00", freq="h")
            assert per.strftime("%p") == pm_local

            # Index
            per = pd.period_range("2003-01-01 01:00:00", periods=2, freq="12h")
            msg = "PeriodIndex.format is deprecated"
            with tm.assert_produces_warning(FutureWarning, match=msg):
                formatted = per.format(date_format="%y %I:%M:%S%p")
            assert formatted[0] == f"03 01:00:00{am_local}"
            assert formatted[1] == f"03 01:00:00{pm_local}"
