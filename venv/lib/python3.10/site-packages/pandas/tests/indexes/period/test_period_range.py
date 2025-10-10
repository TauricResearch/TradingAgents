import numpy as np
import pytest

from pandas import (
    NaT,
    Period,
    PeriodIndex,
    date_range,
    period_range,
)
import pandas._testing as tm


class TestPeriodRangeKeywords:
    def test_required_arguments(self):
        msg = (
            "Of the three parameters: start, end, and periods, exactly two "
            "must be specified"
        )
        with pytest.raises(ValueError, match=msg):
            period_range("2011-1-1", "2012-1-1", "B")

    def test_required_arguments2(self):
        start = Period("02-Apr-2005", "D")
        msg = (
            "Of the three parameters: start, end, and periods, exactly two "
            "must be specified"
        )
        with pytest.raises(ValueError, match=msg):
            period_range(start=start)

    def test_required_arguments3(self):
        # not enough params
        msg = (
            "Of the three parameters: start, end, and periods, "
            "exactly two must be specified"
        )
        with pytest.raises(ValueError, match=msg):
            period_range(start="2017Q1")

        with pytest.raises(ValueError, match=msg):
            period_range(end="2017Q1")

        with pytest.raises(ValueError, match=msg):
            period_range(periods=5)

        with pytest.raises(ValueError, match=msg):
            period_range()

    def test_required_arguments_too_many(self):
        msg = (
            "Of the three parameters: start, end, and periods, "
            "exactly two must be specified"
        )
        with pytest.raises(ValueError, match=msg):
            period_range(start="2017Q1", end="2018Q1", periods=8, freq="Q")

    def test_start_end_non_nat(self):
        # start/end NaT
        msg = "start and end must not be NaT"
        with pytest.raises(ValueError, match=msg):
            period_range(start=NaT, end="2018Q1")
        with pytest.raises(ValueError, match=msg):
            period_range(start=NaT, end="2018Q1", freq="Q")

        with pytest.raises(ValueError, match=msg):
            period_range(start="2017Q1", end=NaT)
        with pytest.raises(ValueError, match=msg):
            period_range(start="2017Q1", end=NaT, freq="Q")

    def test_periods_requires_integer(self):
        # invalid periods param
        msg = "periods must be a number, got foo"
        with pytest.raises(TypeError, match=msg):
            period_range(start="2017Q1", periods="foo")


class TestPeriodRange:
    @pytest.mark.parametrize(
        "freq_offset, freq_period",
        [
            ("D", "D"),
            ("W", "W"),
            ("QE", "Q"),
            ("YE", "Y"),
        ],
    )
    def test_construction_from_string(self, freq_offset, freq_period):
        # non-empty
        expected = date_range(
            start="2017-01-01", periods=5, freq=freq_offset, name="foo"
        ).to_period()
        start, end = str(expected[0]), str(expected[-1])

        result = period_range(start=start, end=end, freq=freq_period, name="foo")
        tm.assert_index_equal(result, expected)

        result = period_range(start=start, periods=5, freq=freq_period, name="foo")
        tm.assert_index_equal(result, expected)

        result = period_range(end=end, periods=5, freq=freq_period, name="foo")
        tm.assert_index_equal(result, expected)

        # empty
        expected = PeriodIndex([], freq=freq_period, name="foo")

        result = period_range(start=start, periods=0, freq=freq_period, name="foo")
        tm.assert_index_equal(result, expected)

        result = period_range(end=end, periods=0, freq=freq_period, name="foo")
        tm.assert_index_equal(result, expected)

        result = period_range(start=end, end=start, freq=freq_period, name="foo")
        tm.assert_index_equal(result, expected)

    def test_construction_from_string_monthly(self):
        # non-empty
        expected = date_range(
            start="2017-01-01", periods=5, freq="ME", name="foo"
        ).to_period()
        start, end = str(expected[0]), str(expected[-1])

        result = period_range(start=start, end=end, freq="M", name="foo")
        tm.assert_index_equal(result, expected)

        result = period_range(start=start, periods=5, freq="M", name="foo")
        tm.assert_index_equal(result, expected)

        result = period_range(end=end, periods=5, freq="M", name="foo")
        tm.assert_index_equal(result, expected)

        # empty
        expected = PeriodIndex([], freq="M", name="foo")

        result = period_range(start=start, periods=0, freq="M", name="foo")
        tm.assert_index_equal(result, expected)

        result = period_range(end=end, periods=0, freq="M", name="foo")
        tm.assert_index_equal(result, expected)

        result = period_range(start=end, end=start, freq="M", name="foo")
        tm.assert_index_equal(result, expected)

    def test_construction_from_period(self):
        # upsampling
        start, end = Period("2017Q1", freq="Q"), Period("2018Q1", freq="Q")
        expected = date_range(
            start="2017-03-31", end="2018-03-31", freq="ME", name="foo"
        ).to_period()
        result = period_range(start=start, end=end, freq="M", name="foo")
        tm.assert_index_equal(result, expected)

        # downsampling
        start = Period("2017-1", freq="M")
        end = Period("2019-12", freq="M")
        expected = date_range(
            start="2017-01-31", end="2019-12-31", freq="QE", name="foo"
        ).to_period()
        result = period_range(start=start, end=end, freq="Q", name="foo")
        tm.assert_index_equal(result, expected)

        # test for issue # 21793
        start = Period("2017Q1", freq="Q")
        end = Period("2018Q1", freq="Q")
        idx = period_range(start=start, end=end, freq="Q", name="foo")
        result = idx == idx.values
        expected = np.array([True, True, True, True, True])
        tm.assert_numpy_array_equal(result, expected)

        # empty
        expected = PeriodIndex([], freq="W", name="foo")

        result = period_range(start=start, periods=0, freq="W", name="foo")
        tm.assert_index_equal(result, expected)

        result = period_range(end=end, periods=0, freq="W", name="foo")
        tm.assert_index_equal(result, expected)

        result = period_range(start=end, end=start, freq="W", name="foo")
        tm.assert_index_equal(result, expected)

    def test_mismatched_start_end_freq_raises(self):
        depr_msg = "Period with BDay freq is deprecated"
        msg = "'w' is deprecated and will be removed in a future version."
        with tm.assert_produces_warning(FutureWarning, match=msg):
            end_w = Period("2006-12-31", "1w")

        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            start_b = Period("02-Apr-2005", "B")
            end_b = Period("2005-05-01", "B")

        msg = "start and end must have same freq"
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=depr_msg):
                period_range(start=start_b, end=end_w)

        # without mismatch we are OK
        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            period_range(start=start_b, end=end_b)


class TestPeriodRangeDisallowedFreqs:
    def test_constructor_U(self):
        # U was used as undefined period
        with pytest.raises(ValueError, match="Invalid frequency: X"):
            period_range("2007-1-1", periods=500, freq="X")

    @pytest.mark.parametrize(
        "freq,freq_depr",
        [
            ("2Y", "2A"),
            ("2Y", "2a"),
            ("2Y-AUG", "2A-AUG"),
            ("2Y-AUG", "2A-aug"),
        ],
    )
    def test_a_deprecated_from_time_series(self, freq, freq_depr):
        # GH#52536
        msg = f"'{freq_depr[1:]}' is deprecated and will be removed in a "
        f"future version. Please use '{freq[1:]}' instead."

        with tm.assert_produces_warning(FutureWarning, match=msg):
            period_range(freq=freq_depr, start="1/1/2001", end="12/1/2009")

    @pytest.mark.parametrize("freq_depr", ["2H", "2MIN", "2S", "2US", "2NS"])
    def test_uppercase_freq_deprecated_from_time_series(self, freq_depr):
        # GH#52536, GH#54939
        msg = f"'{freq_depr[1:]}' is deprecated and will be removed in a "
        f"future version. Please use '{freq_depr.lower()[1:]}' instead."

        with tm.assert_produces_warning(FutureWarning, match=msg):
            period_range("2020-01-01 00:00:00 00:00", periods=2, freq=freq_depr)

    @pytest.mark.parametrize("freq_depr", ["2m", "2q-sep", "2y", "2w"])
    def test_lowercase_freq_deprecated_from_time_series(self, freq_depr):
        # GH#52536, GH#54939
        msg = f"'{freq_depr[1:]}' is deprecated and will be removed in a "
        f"future version. Please use '{freq_depr.upper()[1:]}' instead."

        with tm.assert_produces_warning(FutureWarning, match=msg):
            period_range(freq=freq_depr, start="1/1/2001", end="12/1/2009")
