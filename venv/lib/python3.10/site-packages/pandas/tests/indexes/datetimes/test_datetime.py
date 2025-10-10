import datetime as dt
from datetime import date
import re

import numpy as np
import pytest

from pandas.compat.numpy import np_long

import pandas as pd
from pandas import (
    DataFrame,
    DatetimeIndex,
    Index,
    Timestamp,
    date_range,
    offsets,
)
import pandas._testing as tm


class TestDatetimeIndex:
    def test_is_(self):
        dti = date_range(start="1/1/2005", end="12/1/2005", freq="ME")
        assert dti.is_(dti)
        assert dti.is_(dti.view())
        assert not dti.is_(dti.copy())

    def test_time_overflow_for_32bit_machines(self):
        # GH8943.  On some machines NumPy defaults to np.int32 (for example,
        # 32-bit Linux machines).  In the function _generate_regular_range
        # found in tseries/index.py, `periods` gets multiplied by `strides`
        # (which has value 1e9) and since the max value for np.int32 is ~2e9,
        # and since those machines won't promote np.int32 to np.int64, we get
        # overflow.
        periods = np_long(1000)

        idx1 = date_range(start="2000", periods=periods, freq="s")
        assert len(idx1) == periods

        idx2 = date_range(end="2000", periods=periods, freq="s")
        assert len(idx2) == periods

    def test_nat(self):
        assert DatetimeIndex([np.nan])[0] is pd.NaT

    def test_week_of_month_frequency(self):
        # GH 5348: "ValueError: Could not evaluate WOM-1SUN" shouldn't raise
        d1 = date(2002, 9, 1)
        d2 = date(2013, 10, 27)
        d3 = date(2012, 9, 30)
        idx1 = DatetimeIndex([d1, d2])
        idx2 = DatetimeIndex([d3])
        result_append = idx1.append(idx2)
        expected = DatetimeIndex([d1, d2, d3])
        tm.assert_index_equal(result_append, expected)
        result_union = idx1.union(idx2)
        expected = DatetimeIndex([d1, d3, d2])
        tm.assert_index_equal(result_union, expected)

    def test_append_nondatetimeindex(self):
        rng = date_range("1/1/2000", periods=10)
        idx = Index(["a", "b", "c", "d"])

        result = rng.append(idx)
        assert isinstance(result[0], Timestamp)

    def test_misc_coverage(self):
        rng = date_range("1/1/2000", periods=5)
        result = rng.groupby(rng.day)
        assert isinstance(next(iter(result.values()))[0], Timestamp)

    # TODO: belongs in frame groupby tests?
    def test_groupby_function_tuple_1677(self):
        df = DataFrame(
            np.random.default_rng(2).random(100),
            index=date_range("1/1/2000", periods=100),
        )
        monthly_group = df.groupby(lambda x: (x.year, x.month))

        result = monthly_group.mean()
        assert isinstance(result.index[0], tuple)

    def assert_index_parameters(self, index):
        assert index.freq == "40960ns"
        assert index.inferred_freq == "40960ns"

    def test_ns_index(self):
        nsamples = 400
        ns = int(1e9 / 24414)
        dtstart = np.datetime64("2012-09-20T00:00:00")

        dt = dtstart + np.arange(nsamples) * np.timedelta64(ns, "ns")
        freq = ns * offsets.Nano()
        index = DatetimeIndex(dt, freq=freq, name="time")
        self.assert_index_parameters(index)

        new_index = date_range(start=index[0], end=index[-1], freq=index.freq)
        self.assert_index_parameters(new_index)

    def test_asarray_tz_naive(self):
        # This shouldn't produce a warning.
        idx = date_range("2000", periods=2)
        # M8[ns] by default
        result = np.asarray(idx)

        expected = np.array(["2000-01-01", "2000-01-02"], dtype="M8[ns]")
        tm.assert_numpy_array_equal(result, expected)

        # optionally, object
        result = np.asarray(idx, dtype=object)

        expected = np.array([Timestamp("2000-01-01"), Timestamp("2000-01-02")])
        tm.assert_numpy_array_equal(result, expected)

    def test_asarray_tz_aware(self):
        tz = "US/Central"
        idx = date_range("2000", periods=2, tz=tz)
        expected = np.array(["2000-01-01T06", "2000-01-02T06"], dtype="M8[ns]")
        result = np.asarray(idx, dtype="datetime64[ns]")

        tm.assert_numpy_array_equal(result, expected)

        # Old behavior with no warning
        result = np.asarray(idx, dtype="M8[ns]")

        tm.assert_numpy_array_equal(result, expected)

        # Future behavior with no warning
        expected = np.array(
            [Timestamp("2000-01-01", tz=tz), Timestamp("2000-01-02", tz=tz)]
        )
        result = np.asarray(idx, dtype=object)

        tm.assert_numpy_array_equal(result, expected)

    def test_CBH_deprecated(self):
        msg = "'CBH' is deprecated and will be removed in a future version."

        with tm.assert_produces_warning(FutureWarning, match=msg):
            expected = date_range(
                dt.datetime(2022, 12, 11), dt.datetime(2022, 12, 13), freq="CBH"
            )
        result = DatetimeIndex(
            [
                "2022-12-12 09:00:00",
                "2022-12-12 10:00:00",
                "2022-12-12 11:00:00",
                "2022-12-12 12:00:00",
                "2022-12-12 13:00:00",
                "2022-12-12 14:00:00",
                "2022-12-12 15:00:00",
                "2022-12-12 16:00:00",
            ],
            dtype="datetime64[ns]",
            freq="cbh",
        )

        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "freq_depr, expected_values, expected_freq",
        [
            (
                "AS-AUG",
                ["2021-08-01", "2022-08-01", "2023-08-01"],
                "YS-AUG",
            ),
            (
                "1BAS-MAY",
                ["2021-05-03", "2022-05-02", "2023-05-01"],
                "1BYS-MAY",
            ),
        ],
    )
    def test_AS_BAS_deprecated(self, freq_depr, expected_values, expected_freq):
        # GH#55479
        freq_msg = re.split("[0-9]*", freq_depr, maxsplit=1)[1]
        msg = f"'{freq_msg}' is deprecated and will be removed in a future version."

        with tm.assert_produces_warning(FutureWarning, match=msg):
            expected = date_range(
                dt.datetime(2020, 12, 1), dt.datetime(2023, 12, 1), freq=freq_depr
            )
        result = DatetimeIndex(
            expected_values,
            dtype="datetime64[ns]",
            freq=expected_freq,
        )

        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "freq, expected_values, freq_depr",
        [
            ("2BYE-MAR", ["2016-03-31"], "2BA-MAR"),
            ("2BYE-JUN", ["2016-06-30"], "2BY-JUN"),
            ("2BME", ["2016-02-29", "2016-04-29", "2016-06-30"], "2BM"),
            ("2BQE", ["2016-03-31"], "2BQ"),
            ("1BQE-MAR", ["2016-03-31", "2016-06-30"], "1BQ-MAR"),
        ],
    )
    def test_BM_BQ_BY_deprecated(self, freq, expected_values, freq_depr):
        # GH#52064
        msg = f"'{freq_depr[1:]}' is deprecated and will be removed "
        f"in a future version, please use '{freq[1:]}' instead."

        with tm.assert_produces_warning(FutureWarning, match=msg):
            expected = date_range(start="2016-02-21", end="2016-08-21", freq=freq_depr)
        result = DatetimeIndex(
            data=expected_values,
            dtype="datetime64[ns]",
            freq=freq,
        )

        tm.assert_index_equal(result, expected)
