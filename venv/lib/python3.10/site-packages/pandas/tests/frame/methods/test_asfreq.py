from datetime import datetime

import numpy as np
import pytest

from pandas._libs.tslibs.offsets import MonthEnd

from pandas import (
    DataFrame,
    DatetimeIndex,
    Series,
    date_range,
    period_range,
    to_datetime,
)
import pandas._testing as tm

from pandas.tseries import offsets


class TestAsFreq:
    @pytest.fixture(params=["s", "ms", "us", "ns"])
    def unit(self, request):
        return request.param

    def test_asfreq2(self, frame_or_series):
        ts = frame_or_series(
            [0.0, 1.0, 2.0],
            index=DatetimeIndex(
                [
                    datetime(2009, 10, 30),
                    datetime(2009, 11, 30),
                    datetime(2009, 12, 31),
                ],
                dtype="M8[ns]",
                freq="BME",
            ),
        )

        daily_ts = ts.asfreq("B")
        monthly_ts = daily_ts.asfreq("BME")
        tm.assert_equal(monthly_ts, ts)

        daily_ts = ts.asfreq("B", method="pad")
        monthly_ts = daily_ts.asfreq("BME")
        tm.assert_equal(monthly_ts, ts)

        daily_ts = ts.asfreq(offsets.BDay())
        monthly_ts = daily_ts.asfreq(offsets.BMonthEnd())
        tm.assert_equal(monthly_ts, ts)

        result = ts[:0].asfreq("ME")
        assert len(result) == 0
        assert result is not ts

        if frame_or_series is Series:
            daily_ts = ts.asfreq("D", fill_value=-1)
            result = daily_ts.value_counts().sort_index()
            expected = Series(
                [60, 1, 1, 1], index=[-1.0, 2.0, 1.0, 0.0], name="count"
            ).sort_index()
            tm.assert_series_equal(result, expected)

    def test_asfreq_datetimeindex_empty(self, frame_or_series):
        # GH#14320
        index = DatetimeIndex(["2016-09-29 11:00"])
        expected = frame_or_series(index=index, dtype=object).asfreq("h")
        result = frame_or_series([3], index=index.copy()).asfreq("h")
        tm.assert_index_equal(expected.index, result.index)

    @pytest.mark.parametrize("tz", ["US/Eastern", "dateutil/US/Eastern"])
    def test_tz_aware_asfreq_smoke(self, tz, frame_or_series):
        dr = date_range("2011-12-01", "2012-07-20", freq="D", tz=tz)

        obj = frame_or_series(
            np.random.default_rng(2).standard_normal(len(dr)), index=dr
        )

        # it works!
        obj.asfreq("min")

    def test_asfreq_normalize(self, frame_or_series):
        rng = date_range("1/1/2000 09:30", periods=20)
        norm = date_range("1/1/2000", periods=20)

        vals = np.random.default_rng(2).standard_normal((20, 3))

        obj = DataFrame(vals, index=rng)
        expected = DataFrame(vals, index=norm)
        if frame_or_series is Series:
            obj = obj[0]
            expected = expected[0]

        result = obj.asfreq("D", normalize=True)
        tm.assert_equal(result, expected)

    def test_asfreq_keep_index_name(self, frame_or_series):
        # GH#9854
        index_name = "bar"
        index = date_range("20130101", periods=20, name=index_name)
        obj = DataFrame(list(range(20)), columns=["foo"], index=index)
        obj = tm.get_obj(obj, frame_or_series)

        assert index_name == obj.index.name
        assert index_name == obj.asfreq("10D").index.name

    def test_asfreq_ts(self, frame_or_series):
        index = period_range(freq="Y", start="1/1/2001", end="12/31/2010")
        obj = DataFrame(
            np.random.default_rng(2).standard_normal((len(index), 3)), index=index
        )
        obj = tm.get_obj(obj, frame_or_series)

        result = obj.asfreq("D", how="end")
        exp_index = index.asfreq("D", how="end")
        assert len(result) == len(obj)
        tm.assert_index_equal(result.index, exp_index)

        result = obj.asfreq("D", how="start")
        exp_index = index.asfreq("D", how="start")
        assert len(result) == len(obj)
        tm.assert_index_equal(result.index, exp_index)

    def test_asfreq_resample_set_correct_freq(self, frame_or_series):
        # GH#5613
        # we test if .asfreq() and .resample() set the correct value for .freq
        dti = to_datetime(["2012-01-01", "2012-01-02", "2012-01-03"])
        obj = DataFrame({"col": [1, 2, 3]}, index=dti)
        obj = tm.get_obj(obj, frame_or_series)

        # testing the settings before calling .asfreq() and .resample()
        assert obj.index.freq is None
        assert obj.index.inferred_freq == "D"

        # does .asfreq() set .freq correctly?
        assert obj.asfreq("D").index.freq == "D"

        # does .resample() set .freq correctly?
        assert obj.resample("D").asfreq().index.freq == "D"

    def test_asfreq_empty(self, datetime_frame):
        # test does not blow up on length-0 DataFrame
        zero_length = datetime_frame.reindex([])
        result = zero_length.asfreq("BME")
        assert result is not zero_length

    def test_asfreq(self, datetime_frame):
        offset_monthly = datetime_frame.asfreq(offsets.BMonthEnd())
        rule_monthly = datetime_frame.asfreq("BME")

        tm.assert_frame_equal(offset_monthly, rule_monthly)

        rule_monthly.asfreq("B", method="pad")
        # TODO: actually check that this worked.

        # don't forget!
        rule_monthly.asfreq("B", method="pad")

    def test_asfreq_datetimeindex(self):
        df = DataFrame(
            {"A": [1, 2, 3]},
            index=[datetime(2011, 11, 1), datetime(2011, 11, 2), datetime(2011, 11, 3)],
        )
        df = df.asfreq("B")
        assert isinstance(df.index, DatetimeIndex)

        ts = df["A"].asfreq("B")
        assert isinstance(ts.index, DatetimeIndex)

    def test_asfreq_fillvalue(self):
        # test for fill value during upsampling, related to issue 3715

        # setup
        rng = date_range("1/1/2016", periods=10, freq="2s")
        # Explicit cast to 'float' to avoid implicit cast when setting None
        ts = Series(np.arange(len(rng)), index=rng, dtype="float")
        df = DataFrame({"one": ts})

        # insert pre-existing missing value
        df.loc["2016-01-01 00:00:08", "one"] = None

        actual_df = df.asfreq(freq="1s", fill_value=9.0)
        expected_df = df.asfreq(freq="1s").fillna(9.0)
        expected_df.loc["2016-01-01 00:00:08", "one"] = None
        tm.assert_frame_equal(expected_df, actual_df)

        expected_series = ts.asfreq(freq="1s").fillna(9.0)
        actual_series = ts.asfreq(freq="1s", fill_value=9.0)
        tm.assert_series_equal(expected_series, actual_series)

    def test_asfreq_with_date_object_index(self, frame_or_series):
        rng = date_range("1/1/2000", periods=20)
        ts = frame_or_series(np.random.default_rng(2).standard_normal(20), index=rng)

        ts2 = ts.copy()
        ts2.index = [x.date() for x in ts2.index]

        result = ts2.asfreq("4h", method="ffill")
        expected = ts.asfreq("4h", method="ffill")
        tm.assert_equal(result, expected)

    def test_asfreq_with_unsorted_index(self, frame_or_series):
        # GH#39805
        # Test that rows are not dropped when the datetime index is out of order
        index = to_datetime(["2021-01-04", "2021-01-02", "2021-01-03", "2021-01-01"])
        result = frame_or_series(range(4), index=index)

        expected = result.reindex(sorted(index))
        expected.index = expected.index._with_freq("infer")

        result = result.asfreq("D")
        tm.assert_equal(result, expected)

    def test_asfreq_after_normalize(self, unit):
        # https://github.com/pandas-dev/pandas/issues/50727
        result = DatetimeIndex(
            date_range("2000", periods=2).as_unit(unit).normalize(), freq="D"
        )
        expected = DatetimeIndex(["2000-01-01", "2000-01-02"], freq="D").as_unit(unit)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "freq, freq_half",
        [
            ("2ME", "ME"),
            (MonthEnd(2), MonthEnd(1)),
        ],
    )
    def test_asfreq_2ME(self, freq, freq_half):
        index = date_range("1/1/2000", periods=6, freq=freq_half)
        df = DataFrame({"s": Series([0.0, 1.0, 2.0, 3.0, 4.0, 5.0], index=index)})
        expected = df.asfreq(freq=freq)

        index = date_range("1/1/2000", periods=3, freq=freq)
        result = DataFrame({"s": Series([0.0, 2.0, 4.0], index=index)})
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "freq, freq_depr",
        [
            ("2ME", "2M"),
            ("2QE", "2Q"),
            ("2QE-SEP", "2Q-SEP"),
            ("1BQE", "1BQ"),
            ("2BQE-SEP", "2BQ-SEP"),
            ("1YE", "1Y"),
            ("2YE-MAR", "2Y-MAR"),
            ("1YE", "1A"),
            ("2YE-MAR", "2A-MAR"),
            ("2BYE-MAR", "2BA-MAR"),
        ],
    )
    def test_asfreq_frequency_M_Q_Y_A_deprecated(self, freq, freq_depr):
        # GH#9586, #55978
        depr_msg = f"'{freq_depr[1:]}' is deprecated and will be removed "
        f"in a future version, please use '{freq[1:]}' instead."

        index = date_range("1/1/2000", periods=4, freq=f"{freq[1:]}")
        df = DataFrame({"s": Series([0.0, 1.0, 2.0, 3.0], index=index)})
        expected = df.asfreq(freq=freq)
        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            result = df.asfreq(freq=freq_depr)
        tm.assert_frame_equal(result, expected)
