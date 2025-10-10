import re

import numpy as np
import pytest

from pandas import (
    Index,
    Interval,
    IntervalIndex,
    Series,
)
import pandas._testing as tm


class TestIntervalIndex:
    @pytest.fixture
    def series_with_interval_index(self):
        return Series(np.arange(5), IntervalIndex.from_breaks(np.arange(6)))

    def test_loc_with_interval(self, series_with_interval_index, indexer_sl):
        # loc with single label / list of labels:
        #   - Intervals: only exact matches
        #   - scalars: those that contain it

        ser = series_with_interval_index.copy()

        expected = 0
        result = indexer_sl(ser)[Interval(0, 1)]
        assert result == expected

        expected = ser.iloc[3:5]
        result = indexer_sl(ser)[[Interval(3, 4), Interval(4, 5)]]
        tm.assert_series_equal(expected, result)

        # missing or not exact
        with pytest.raises(KeyError, match=re.escape("Interval(3, 5, closed='left')")):
            indexer_sl(ser)[Interval(3, 5, closed="left")]

        with pytest.raises(KeyError, match=re.escape("Interval(3, 5, closed='right')")):
            indexer_sl(ser)[Interval(3, 5)]

        with pytest.raises(
            KeyError, match=re.escape("Interval(-2, 0, closed='right')")
        ):
            indexer_sl(ser)[Interval(-2, 0)]

        with pytest.raises(KeyError, match=re.escape("Interval(5, 6, closed='right')")):
            indexer_sl(ser)[Interval(5, 6)]

    def test_loc_with_scalar(self, series_with_interval_index, indexer_sl):
        # loc with single label / list of labels:
        #   - Intervals: only exact matches
        #   - scalars: those that contain it

        ser = series_with_interval_index.copy()

        assert indexer_sl(ser)[1] == 0
        assert indexer_sl(ser)[1.5] == 1
        assert indexer_sl(ser)[2] == 1

        expected = ser.iloc[1:4]
        tm.assert_series_equal(expected, indexer_sl(ser)[[1.5, 2.5, 3.5]])
        tm.assert_series_equal(expected, indexer_sl(ser)[[2, 3, 4]])
        tm.assert_series_equal(expected, indexer_sl(ser)[[1.5, 3, 4]])

        expected = ser.iloc[[1, 1, 2, 1]]
        tm.assert_series_equal(expected, indexer_sl(ser)[[1.5, 2, 2.5, 1.5]])

        expected = ser.iloc[2:5]
        tm.assert_series_equal(expected, indexer_sl(ser)[ser >= 2])

    def test_loc_with_slices(self, series_with_interval_index, indexer_sl):
        # loc with slices:
        #   - Interval objects: only works with exact matches
        #   - scalars: only works for non-overlapping, monotonic intervals,
        #     and start/stop select location based on the interval that
        #     contains them:
        #    (slice_loc(start, stop) == (idx.get_loc(start), idx.get_loc(stop))

        ser = series_with_interval_index.copy()

        # slice of interval

        expected = ser.iloc[:3]
        result = indexer_sl(ser)[Interval(0, 1) : Interval(2, 3)]
        tm.assert_series_equal(expected, result)

        expected = ser.iloc[3:]
        result = indexer_sl(ser)[Interval(3, 4) :]
        tm.assert_series_equal(expected, result)

        msg = "Interval objects are not currently supported"
        with pytest.raises(NotImplementedError, match=msg):
            indexer_sl(ser)[Interval(3, 6) :]

        with pytest.raises(NotImplementedError, match=msg):
            indexer_sl(ser)[Interval(3, 4, closed="left") :]

    def test_slice_step_ne1(self, series_with_interval_index):
        # GH#31658 slice of scalar with step != 1
        ser = series_with_interval_index.copy()
        expected = ser.iloc[0:4:2]

        result = ser[0:4:2]
        tm.assert_series_equal(result, expected)

        result2 = ser[0:4][::2]
        tm.assert_series_equal(result2, expected)

    def test_slice_float_start_stop(self, series_with_interval_index):
        # GH#31658 slicing with integers is positional, with floats is not
        #  supported
        ser = series_with_interval_index.copy()

        msg = "label-based slicing with step!=1 is not supported for IntervalIndex"
        with pytest.raises(ValueError, match=msg):
            ser[1.5:9.5:2]

    def test_slice_interval_step(self, series_with_interval_index):
        # GH#31658 allows for integer step!=1, not Interval step
        ser = series_with_interval_index.copy()
        msg = "label-based slicing with step!=1 is not supported for IntervalIndex"
        with pytest.raises(ValueError, match=msg):
            ser[0 : 4 : Interval(0, 1)]

    def test_loc_with_overlap(self, indexer_sl):
        idx = IntervalIndex.from_tuples([(1, 5), (3, 7)])
        ser = Series(range(len(idx)), index=idx)

        # scalar
        expected = ser
        result = indexer_sl(ser)[4]
        tm.assert_series_equal(expected, result)

        result = indexer_sl(ser)[[4]]
        tm.assert_series_equal(expected, result)

        # interval
        expected = 0
        result = indexer_sl(ser)[Interval(1, 5)]
        assert expected == result

        expected = ser
        result = indexer_sl(ser)[[Interval(1, 5), Interval(3, 7)]]
        tm.assert_series_equal(expected, result)

        with pytest.raises(KeyError, match=re.escape("Interval(3, 5, closed='right')")):
            indexer_sl(ser)[Interval(3, 5)]

        msg = (
            r"None of \[IntervalIndex\(\[\(3, 5\]\], "
            r"dtype='interval\[int64, right\]'\)\] are in the \[index\]"
        )
        with pytest.raises(KeyError, match=msg):
            indexer_sl(ser)[[Interval(3, 5)]]

        # slices with interval (only exact matches)
        expected = ser
        result = indexer_sl(ser)[Interval(1, 5) : Interval(3, 7)]
        tm.assert_series_equal(expected, result)

        msg = (
            "'can only get slices from an IntervalIndex if bounds are "
            "non-overlapping and all monotonic increasing or decreasing'"
        )
        with pytest.raises(KeyError, match=msg):
            indexer_sl(ser)[Interval(1, 6) : Interval(3, 8)]

        if indexer_sl is tm.loc:
            # slices with scalar raise for overlapping intervals
            # TODO KeyError is the appropriate error?
            with pytest.raises(KeyError, match=msg):
                ser.loc[1:4]

    def test_non_unique(self, indexer_sl):
        idx = IntervalIndex.from_tuples([(1, 3), (3, 7)])
        ser = Series(range(len(idx)), index=idx)

        result = indexer_sl(ser)[Interval(1, 3)]
        assert result == 0

        result = indexer_sl(ser)[[Interval(1, 3)]]
        expected = ser.iloc[0:1]
        tm.assert_series_equal(expected, result)

    def test_non_unique_moar(self, indexer_sl):
        idx = IntervalIndex.from_tuples([(1, 3), (1, 3), (3, 7)])
        ser = Series(range(len(idx)), index=idx)

        expected = ser.iloc[[0, 1]]
        result = indexer_sl(ser)[Interval(1, 3)]
        tm.assert_series_equal(expected, result)

        expected = ser
        result = indexer_sl(ser)[Interval(1, 3) :]
        tm.assert_series_equal(expected, result)

        expected = ser.iloc[[0, 1]]
        result = indexer_sl(ser)[[Interval(1, 3)]]
        tm.assert_series_equal(expected, result)

    def test_loc_getitem_missing_key_error_message(
        self, frame_or_series, series_with_interval_index
    ):
        # GH#27365
        ser = series_with_interval_index.copy()
        obj = frame_or_series(ser)
        with pytest.raises(KeyError, match=r"\[6\]"):
            obj.loc[[4, 5, 6]]


@pytest.mark.parametrize(
    "intervals",
    [
        ([Interval(-np.inf, 0.0), Interval(0.0, 1.0)]),
        ([Interval(-np.inf, -2.0), Interval(-2.0, -1.0)]),
        ([Interval(-1.0, 0.0), Interval(0.0, np.inf)]),
        ([Interval(1.0, 2.0), Interval(2.0, np.inf)]),
    ],
)
def test_repeating_interval_index_with_infs(intervals):
    # GH 46658

    interval_index = Index(intervals * 51)

    expected = np.arange(1, 102, 2, dtype=np.intp)
    result = interval_index.get_indexer_for([intervals[1]])

    tm.assert_equal(result, expected)
