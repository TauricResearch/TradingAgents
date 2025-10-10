import numpy as np
import pytest

from pandas import (
    DataFrame,
    Series,
)
import pandas._testing as tm


class TestDataFramePctChange:
    @pytest.mark.parametrize(
        "periods, fill_method, limit, exp",
        [
            (1, "ffill", None, [np.nan, np.nan, np.nan, 1, 1, 1.5, 0, 0]),
            (1, "ffill", 1, [np.nan, np.nan, np.nan, 1, 1, 1.5, 0, np.nan]),
            (1, "bfill", None, [np.nan, 0, 0, 1, 1, 1.5, np.nan, np.nan]),
            (1, "bfill", 1, [np.nan, np.nan, 0, 1, 1, 1.5, np.nan, np.nan]),
            (-1, "ffill", None, [np.nan, np.nan, -0.5, -0.5, -0.6, 0, 0, np.nan]),
            (-1, "ffill", 1, [np.nan, np.nan, -0.5, -0.5, -0.6, 0, np.nan, np.nan]),
            (-1, "bfill", None, [0, 0, -0.5, -0.5, -0.6, np.nan, np.nan, np.nan]),
            (-1, "bfill", 1, [np.nan, 0, -0.5, -0.5, -0.6, np.nan, np.nan, np.nan]),
        ],
    )
    def test_pct_change_with_nas(
        self, periods, fill_method, limit, exp, frame_or_series
    ):
        vals = [np.nan, np.nan, 1, 2, 4, 10, np.nan, np.nan]
        obj = frame_or_series(vals)

        msg = (
            "The 'fill_method' keyword being not None and the 'limit' keyword in "
            f"{type(obj).__name__}.pct_change are deprecated"
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = obj.pct_change(periods=periods, fill_method=fill_method, limit=limit)
        tm.assert_equal(res, frame_or_series(exp))

    def test_pct_change_numeric(self):
        # GH#11150
        pnl = DataFrame(
            [np.arange(0, 40, 10), np.arange(0, 40, 10), np.arange(0, 40, 10)]
        ).astype(np.float64)
        pnl.iat[1, 0] = np.nan
        pnl.iat[1, 1] = np.nan
        pnl.iat[2, 3] = 60

        msg = (
            "The 'fill_method' keyword being not None and the 'limit' keyword in "
            "DataFrame.pct_change are deprecated"
        )

        for axis in range(2):
            expected = pnl.ffill(axis=axis) / pnl.ffill(axis=axis).shift(axis=axis) - 1

            with tm.assert_produces_warning(FutureWarning, match=msg):
                result = pnl.pct_change(axis=axis, fill_method="pad")
            tm.assert_frame_equal(result, expected)

    def test_pct_change(self, datetime_frame):
        msg = (
            "The 'fill_method' keyword being not None and the 'limit' keyword in "
            "DataFrame.pct_change are deprecated"
        )

        rs = datetime_frame.pct_change(fill_method=None)
        tm.assert_frame_equal(rs, datetime_frame / datetime_frame.shift(1) - 1)

        rs = datetime_frame.pct_change(2)
        filled = datetime_frame.ffill()
        tm.assert_frame_equal(rs, filled / filled.shift(2) - 1)

        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs = datetime_frame.pct_change(fill_method="bfill", limit=1)
        filled = datetime_frame.bfill(limit=1)
        tm.assert_frame_equal(rs, filled / filled.shift(1) - 1)

        rs = datetime_frame.pct_change(freq="5D")
        filled = datetime_frame.ffill()
        tm.assert_frame_equal(
            rs, (filled / filled.shift(freq="5D") - 1).reindex_like(filled)
        )

    def test_pct_change_shift_over_nas(self):
        s = Series([1.0, 1.5, np.nan, 2.5, 3.0])

        df = DataFrame({"a": s, "b": s})

        msg = "The default fill_method='pad' in DataFrame.pct_change is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            chg = df.pct_change()

        expected = Series([np.nan, 0.5, 0.0, 2.5 / 1.5 - 1, 0.2])
        edf = DataFrame({"a": expected, "b": expected})
        tm.assert_frame_equal(chg, edf)

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
        self, datetime_frame, freq, periods, fill_method, limit
    ):
        msg = (
            "The 'fill_method' keyword being not None and the 'limit' keyword in "
            "DataFrame.pct_change are deprecated"
        )

        # GH#7292
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs_freq = datetime_frame.pct_change(
                freq=freq, fill_method=fill_method, limit=limit
            )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs_periods = datetime_frame.pct_change(
                periods, fill_method=fill_method, limit=limit
            )
        tm.assert_frame_equal(rs_freq, rs_periods)

        empty_ts = DataFrame(index=datetime_frame.index, columns=datetime_frame.columns)
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs_freq = empty_ts.pct_change(
                freq=freq, fill_method=fill_method, limit=limit
            )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rs_periods = empty_ts.pct_change(
                periods, fill_method=fill_method, limit=limit
            )
        tm.assert_frame_equal(rs_freq, rs_periods)


@pytest.mark.parametrize("fill_method", ["pad", "ffill", None])
def test_pct_change_with_duplicated_indices(fill_method):
    # GH30463
    data = DataFrame(
        {0: [np.nan, 1, 2, 3, 9, 18], 1: [0, 1, np.nan, 3, 9, 18]}, index=["a", "b"] * 3
    )

    warn = None if fill_method is None else FutureWarning
    msg = (
        "The 'fill_method' keyword being not None and the 'limit' keyword in "
        "DataFrame.pct_change are deprecated"
    )
    with tm.assert_produces_warning(warn, match=msg):
        result = data.pct_change(fill_method=fill_method)

    if fill_method is None:
        second_column = [np.nan, np.inf, np.nan, np.nan, 2.0, 1.0]
    else:
        second_column = [np.nan, np.inf, 0.0, 2.0, 2.0, 1.0]
    expected = DataFrame(
        {0: [np.nan, np.nan, 1.0, 0.5, 2.0, 1.0], 1: second_column},
        index=["a", "b"] * 3,
    )
    tm.assert_frame_equal(result, expected)


def test_pct_change_none_beginning_no_warning():
    # GH#54481
    df = DataFrame(
        [
            [1, None],
            [2, 1],
            [3, 2],
            [4, 3],
            [5, 4],
        ]
    )
    result = df.pct_change()
    expected = DataFrame(
        {0: [np.nan, 1, 0.5, 1 / 3, 0.25], 1: [np.nan, np.nan, 1, 0.5, 1 / 3]}
    )
    tm.assert_frame_equal(result, expected)
