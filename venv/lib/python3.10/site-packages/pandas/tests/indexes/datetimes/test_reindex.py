from datetime import timedelta

import numpy as np

from pandas import (
    DatetimeIndex,
    date_range,
)
import pandas._testing as tm


class TestDatetimeIndexReindex:
    def test_reindex_preserves_tz_if_target_is_empty_list_or_array(self):
        # GH#7774
        index = date_range("2013-01-01", periods=3, tz="US/Eastern")
        assert str(index.reindex([])[0].tz) == "US/Eastern"
        assert str(index.reindex(np.array([]))[0].tz) == "US/Eastern"

    def test_reindex_with_same_tz_nearest(self):
        # GH#32740
        rng_a = date_range("2010-01-01", "2010-01-02", periods=24, tz="utc")
        rng_b = date_range("2010-01-01", "2010-01-02", periods=23, tz="utc")
        result1, result2 = rng_a.reindex(
            rng_b, method="nearest", tolerance=timedelta(seconds=20)
        )
        expected_list1 = [
            "2010-01-01 00:00:00",
            "2010-01-01 01:05:27.272727272",
            "2010-01-01 02:10:54.545454545",
            "2010-01-01 03:16:21.818181818",
            "2010-01-01 04:21:49.090909090",
            "2010-01-01 05:27:16.363636363",
            "2010-01-01 06:32:43.636363636",
            "2010-01-01 07:38:10.909090909",
            "2010-01-01 08:43:38.181818181",
            "2010-01-01 09:49:05.454545454",
            "2010-01-01 10:54:32.727272727",
            "2010-01-01 12:00:00",
            "2010-01-01 13:05:27.272727272",
            "2010-01-01 14:10:54.545454545",
            "2010-01-01 15:16:21.818181818",
            "2010-01-01 16:21:49.090909090",
            "2010-01-01 17:27:16.363636363",
            "2010-01-01 18:32:43.636363636",
            "2010-01-01 19:38:10.909090909",
            "2010-01-01 20:43:38.181818181",
            "2010-01-01 21:49:05.454545454",
            "2010-01-01 22:54:32.727272727",
            "2010-01-02 00:00:00",
        ]
        expected1 = DatetimeIndex(
            expected_list1, dtype="datetime64[ns, UTC]", freq=None
        )
        expected2 = np.array([0] + [-1] * 21 + [23], dtype=np.dtype("intp"))
        tm.assert_index_equal(result1, expected1)
        tm.assert_numpy_array_equal(result2, expected2)
