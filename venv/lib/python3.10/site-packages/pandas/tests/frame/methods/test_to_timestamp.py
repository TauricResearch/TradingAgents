from datetime import timedelta

import numpy as np
import pytest

from pandas import (
    DataFrame,
    DatetimeIndex,
    PeriodIndex,
    Series,
    Timedelta,
    date_range,
    period_range,
    to_datetime,
)
import pandas._testing as tm


def _get_with_delta(delta, freq="YE-DEC"):
    return date_range(
        to_datetime("1/1/2001") + delta,
        to_datetime("12/31/2009") + delta,
        freq=freq,
    )


class TestToTimestamp:
    def test_to_timestamp(self, frame_or_series):
        K = 5
        index = period_range(freq="Y", start="1/1/2001", end="12/1/2009")
        obj = DataFrame(
            np.random.default_rng(2).standard_normal((len(index), K)),
            index=index,
            columns=["A", "B", "C", "D", "E"],
        )
        obj["mix"] = "a"
        obj = tm.get_obj(obj, frame_or_series)

        exp_index = date_range("1/1/2001", end="12/31/2009", freq="YE-DEC")
        exp_index = exp_index + Timedelta(1, "D") - Timedelta(1, "ns")
        result = obj.to_timestamp("D", "end")
        tm.assert_index_equal(result.index, exp_index)
        tm.assert_numpy_array_equal(result.values, obj.values)
        if frame_or_series is Series:
            assert result.name == "A"

        exp_index = date_range("1/1/2001", end="1/1/2009", freq="YS-JAN")
        result = obj.to_timestamp("D", "start")
        tm.assert_index_equal(result.index, exp_index)

        result = obj.to_timestamp(how="start")
        tm.assert_index_equal(result.index, exp_index)

        delta = timedelta(hours=23)
        result = obj.to_timestamp("H", "end")
        exp_index = _get_with_delta(delta)
        exp_index = exp_index + Timedelta(1, "h") - Timedelta(1, "ns")
        tm.assert_index_equal(result.index, exp_index)

        delta = timedelta(hours=23, minutes=59)
        result = obj.to_timestamp("T", "end")
        exp_index = _get_with_delta(delta)
        exp_index = exp_index + Timedelta(1, "m") - Timedelta(1, "ns")
        tm.assert_index_equal(result.index, exp_index)

        result = obj.to_timestamp("S", "end")
        delta = timedelta(hours=23, minutes=59, seconds=59)
        exp_index = _get_with_delta(delta)
        exp_index = exp_index + Timedelta(1, "s") - Timedelta(1, "ns")
        tm.assert_index_equal(result.index, exp_index)

    def test_to_timestamp_columns(self):
        K = 5
        index = period_range(freq="Y", start="1/1/2001", end="12/1/2009")
        df = DataFrame(
            np.random.default_rng(2).standard_normal((len(index), K)),
            index=index,
            columns=["A", "B", "C", "D", "E"],
        )
        df["mix"] = "a"

        # columns
        df = df.T

        exp_index = date_range("1/1/2001", end="12/31/2009", freq="YE-DEC")
        exp_index = exp_index + Timedelta(1, "D") - Timedelta(1, "ns")
        result = df.to_timestamp("D", "end", axis=1)
        tm.assert_index_equal(result.columns, exp_index)
        tm.assert_numpy_array_equal(result.values, df.values)

        exp_index = date_range("1/1/2001", end="1/1/2009", freq="YS-JAN")
        result = df.to_timestamp("D", "start", axis=1)
        tm.assert_index_equal(result.columns, exp_index)

        delta = timedelta(hours=23)
        result = df.to_timestamp("H", "end", axis=1)
        exp_index = _get_with_delta(delta)
        exp_index = exp_index + Timedelta(1, "h") - Timedelta(1, "ns")
        tm.assert_index_equal(result.columns, exp_index)

        delta = timedelta(hours=23, minutes=59)
        result = df.to_timestamp("min", "end", axis=1)
        exp_index = _get_with_delta(delta)
        exp_index = exp_index + Timedelta(1, "m") - Timedelta(1, "ns")
        tm.assert_index_equal(result.columns, exp_index)

        result = df.to_timestamp("S", "end", axis=1)
        delta = timedelta(hours=23, minutes=59, seconds=59)
        exp_index = _get_with_delta(delta)
        exp_index = exp_index + Timedelta(1, "s") - Timedelta(1, "ns")
        tm.assert_index_equal(result.columns, exp_index)

        result1 = df.to_timestamp("5min", axis=1)
        result2 = df.to_timestamp("min", axis=1)
        expected = date_range("2001-01-01", "2009-01-01", freq="YS")
        assert isinstance(result1.columns, DatetimeIndex)
        assert isinstance(result2.columns, DatetimeIndex)
        tm.assert_numpy_array_equal(result1.columns.asi8, expected.asi8)
        tm.assert_numpy_array_equal(result2.columns.asi8, expected.asi8)
        # PeriodIndex.to_timestamp always use 'infer'
        assert result1.columns.freqstr == "YS-JAN"
        assert result2.columns.freqstr == "YS-JAN"

    def test_to_timestamp_invalid_axis(self):
        index = period_range(freq="Y", start="1/1/2001", end="12/1/2009")
        obj = DataFrame(
            np.random.default_rng(2).standard_normal((len(index), 5)), index=index
        )

        # invalid axis
        with pytest.raises(ValueError, match="axis"):
            obj.to_timestamp(axis=2)

    def test_to_timestamp_hourly(self, frame_or_series):
        index = period_range(freq="h", start="1/1/2001", end="1/2/2001")
        obj = Series(1, index=index, name="foo")
        if frame_or_series is not Series:
            obj = obj.to_frame()

        exp_index = date_range("1/1/2001 00:59:59", end="1/2/2001 00:59:59", freq="h")
        result = obj.to_timestamp(how="end")
        exp_index = exp_index + Timedelta(1, "s") - Timedelta(1, "ns")
        tm.assert_index_equal(result.index, exp_index)
        if frame_or_series is Series:
            assert result.name == "foo"

    def test_to_timestamp_raises(self, index, frame_or_series):
        # GH#33327
        obj = frame_or_series(index=index, dtype=object)

        if not isinstance(index, PeriodIndex):
            msg = f"unsupported Type {type(index).__name__}"
            with pytest.raises(TypeError, match=msg):
                obj.to_timestamp()
