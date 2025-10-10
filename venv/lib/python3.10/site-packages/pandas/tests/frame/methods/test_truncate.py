import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    DatetimeIndex,
    Index,
    Series,
    date_range,
)
import pandas._testing as tm


class TestDataFrameTruncate:
    def test_truncate(self, datetime_frame, frame_or_series):
        ts = datetime_frame[::3]
        ts = tm.get_obj(ts, frame_or_series)

        start, end = datetime_frame.index[3], datetime_frame.index[6]

        start_missing = datetime_frame.index[2]
        end_missing = datetime_frame.index[7]

        # neither specified
        truncated = ts.truncate()
        tm.assert_equal(truncated, ts)

        # both specified
        expected = ts[1:3]

        truncated = ts.truncate(start, end)
        tm.assert_equal(truncated, expected)

        truncated = ts.truncate(start_missing, end_missing)
        tm.assert_equal(truncated, expected)

        # start specified
        expected = ts[1:]

        truncated = ts.truncate(before=start)
        tm.assert_equal(truncated, expected)

        truncated = ts.truncate(before=start_missing)
        tm.assert_equal(truncated, expected)

        # end specified
        expected = ts[:3]

        truncated = ts.truncate(after=end)
        tm.assert_equal(truncated, expected)

        truncated = ts.truncate(after=end_missing)
        tm.assert_equal(truncated, expected)

        # corner case, empty series/frame returned
        truncated = ts.truncate(after=ts.index[0] - ts.index.freq)
        assert len(truncated) == 0

        truncated = ts.truncate(before=ts.index[-1] + ts.index.freq)
        assert len(truncated) == 0

        msg = "Truncate: 2000-01-06 00:00:00 must be after 2000-05-16 00:00:00"
        with pytest.raises(ValueError, match=msg):
            ts.truncate(
                before=ts.index[-1] - ts.index.freq, after=ts.index[0] + ts.index.freq
            )

    def test_truncate_nonsortedindex(self, frame_or_series):
        # GH#17935

        obj = DataFrame({"A": ["a", "b", "c", "d", "e"]}, index=[5, 3, 2, 9, 0])
        obj = tm.get_obj(obj, frame_or_series)

        msg = "truncate requires a sorted index"
        with pytest.raises(ValueError, match=msg):
            obj.truncate(before=3, after=9)

    def test_sort_values_nonsortedindex(self):
        rng = date_range("2011-01-01", "2012-01-01", freq="W")
        ts = DataFrame(
            {
                "A": np.random.default_rng(2).standard_normal(len(rng)),
                "B": np.random.default_rng(2).standard_normal(len(rng)),
            },
            index=rng,
        )

        decreasing = ts.sort_values("A", ascending=False)

        msg = "truncate requires a sorted index"
        with pytest.raises(ValueError, match=msg):
            decreasing.truncate(before="2011-11", after="2011-12")

    def test_truncate_nonsortedindex_axis1(self):
        # GH#17935

        df = DataFrame(
            {
                3: np.random.default_rng(2).standard_normal(5),
                20: np.random.default_rng(2).standard_normal(5),
                2: np.random.default_rng(2).standard_normal(5),
                0: np.random.default_rng(2).standard_normal(5),
            },
            columns=[3, 20, 2, 0],
        )
        msg = "truncate requires a sorted index"
        with pytest.raises(ValueError, match=msg):
            df.truncate(before=2, after=20, axis=1)

    @pytest.mark.parametrize(
        "before, after, indices",
        [(1, 2, [2, 1]), (None, 2, [2, 1, 0]), (1, None, [3, 2, 1])],
    )
    @pytest.mark.parametrize("dtyp", [*tm.ALL_REAL_NUMPY_DTYPES, "datetime64[ns]"])
    def test_truncate_decreasing_index(
        self, before, after, indices, dtyp, frame_or_series
    ):
        # https://github.com/pandas-dev/pandas/issues/33756
        idx = Index([3, 2, 1, 0], dtype=dtyp)
        if isinstance(idx, DatetimeIndex):
            before = pd.Timestamp(before) if before is not None else None
            after = pd.Timestamp(after) if after is not None else None
            indices = [pd.Timestamp(i) for i in indices]
        values = frame_or_series(range(len(idx)), index=idx)
        result = values.truncate(before=before, after=after)
        expected = values.loc[indices]
        tm.assert_equal(result, expected)

    def test_truncate_multiindex(self, frame_or_series):
        # GH 34564
        mi = pd.MultiIndex.from_product([[1, 2, 3, 4], ["A", "B"]], names=["L1", "L2"])
        s1 = DataFrame(range(mi.shape[0]), index=mi, columns=["col"])
        s1 = tm.get_obj(s1, frame_or_series)

        result = s1.truncate(before=2, after=3)

        df = DataFrame.from_dict(
            {"L1": [2, 2, 3, 3], "L2": ["A", "B", "A", "B"], "col": [2, 3, 4, 5]}
        )
        expected = df.set_index(["L1", "L2"])
        expected = tm.get_obj(expected, frame_or_series)

        tm.assert_equal(result, expected)

    def test_truncate_index_only_one_unique_value(self, frame_or_series):
        # GH 42365
        obj = Series(0, index=date_range("2021-06-30", "2021-06-30")).repeat(5)
        if frame_or_series is DataFrame:
            obj = obj.to_frame(name="a")

        truncated = obj.truncate("2021-06-28", "2021-07-01")

        tm.assert_equal(truncated, obj)
