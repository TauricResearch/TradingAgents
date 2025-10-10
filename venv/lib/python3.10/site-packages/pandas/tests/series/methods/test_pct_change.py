import numpy as np
import pytest

from pandas import (
    Series,
    date_range,
)
import pandas._testing as tm


class TestSeriesPctChange:
    def test_pct_change(self, datetime_series):
        msg = (
            "The 'fill_method' keyword being not None and the 'limit' keyword in "
            "Series.pct_change are deprecated"
        )

        rs = datetime_series.pct_change(fill_method=None)
        tm.assert_series_equal(rs, datetime_series / datetime_series.shift(1) - 1)

        rs = datetime_series.pct_change(2)
        filled = datetime_series.ffill()
        tm.assert_series_equal(rs, filled / filled.shift(2) - 1)

        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs = datetime_series.pct_change(fill_method="bfill", limit=1)
        filled = datetime_series.bfill(limit=1)
        tm.assert_series_equal(rs, filled / filled.shift(1) - 1)

        rs = datetime_series.pct_change(freq="5D")
        filled = datetime_series.ffill()
        tm.assert_series_equal(
            rs, (filled / filled.shift(freq="5D") - 1).reindex_like(filled)
        )

    def test_pct_change_with_duplicate_axis(self):
        # GH#28664
        common_idx = date_range("2019-11-14", periods=5, freq="D")
        result = Series(range(5), common_idx).pct_change(freq="B")

        # the reason that the expected should be like this is documented at PR 28681
        expected = Series([np.nan, np.inf, np.nan, np.nan, 3.0], common_idx)

        tm.assert_series_equal(result, expected)

    def test_pct_change_shift_over_nas(self):
        s = Series([1.0, 1.5, np.nan, 2.5, 3.0])

        msg = "The default fill_method='pad' in Series.pct_change is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            chg = s.pct_change()

        expected = Series([np.nan, 0.5, 0.0, 2.5 / 1.5 - 1, 0.2])
        tm.assert_series_equal(chg, expected)

    @pytest.mark.parametrize(
        "freq, periods, fill_method, limit",
        [
            ("5B", 5, None, None),
            ("3B", 3, None, None),
            ("3B", 3, "bfill", None),
            ("7B", 7, "pad", 1),
            ("7B", 7, "bfill", 3),
            ("14B", 14, None, None),
        ],
    )
    def test_pct_change_periods_freq(
        self, freq, periods, fill_method, limit, datetime_series
    ):
        msg = (
            "The 'fill_method' keyword being not None and the 'limit' keyword in "
            "Series.pct_change are deprecated"
        )

        # GH#7292
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs_freq = datetime_series.pct_change(
                freq=freq, fill_method=fill_method, limit=limit
            )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs_periods = datetime_series.pct_change(
                periods, fill_method=fill_method, limit=limit
            )
        tm.assert_series_equal(rs_freq, rs_periods)

        empty_ts = Series(index=datetime_series.index, dtype=object)
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs_freq = empty_ts.pct_change(
                freq=freq, fill_method=fill_method, limit=limit
            )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs_periods = empty_ts.pct_change(
                periods, fill_method=fill_method, limit=limit
            )
        tm.assert_series_equal(rs_freq, rs_periods)


@pytest.mark.parametrize("fill_method", ["pad", "ffill", None])
def test_pct_change_with_duplicated_indices(fill_method):
    # GH30463
    s = Series([np.nan, 1, 2, 3, 9, 18], index=["a", "b"] * 3)

    warn = None if fill_method is None else FutureWarning
    msg = (
        "The 'fill_method' keyword being not None and the 'limit' keyword in "
        "Series.pct_change are deprecated"
    )
    with tm.assert_produces_warning(warn, match=msg):
        result = s.pct_change(fill_method=fill_method)

    expected = Series([np.nan, np.nan, 1.0, 0.5, 2.0, 1.0], index=["a", "b"] * 3)
    tm.assert_series_equal(result, expected)


def test_pct_change_no_warning_na_beginning():
    # GH#54981
    ser = Series([None, None, 1, 2, 3])
    result = ser.pct_change()
    expected = Series([np.nan, np.nan, np.nan, 1, 0.5])
    tm.assert_series_equal(result, expected)


def test_pct_change_empty():
    # GH 57056
    ser = Series([], dtype="float64")
    expected = ser.copy()
    result = ser.pct_change(periods=0)
    tm.assert_series_equal(expected, result)
