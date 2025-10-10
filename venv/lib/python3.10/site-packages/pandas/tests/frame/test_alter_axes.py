from datetime import datetime

import pytz

from pandas import DataFrame
import pandas._testing as tm


class TestDataFrameAlterAxes:
    # Tests for setting index/columns attributes directly (i.e. __setattr__)

    def test_set_axis_setattr_index(self):
        # GH 6785
        # set the index manually

        df = DataFrame([{"ts": datetime(2014, 4, 1, tzinfo=pytz.utc), "foo": 1}])
        expected = df.set_index("ts")
        df.index = df["ts"]
        df.pop("ts")
        tm.assert_frame_equal(df, expected)

    # Renaming

    def test_assign_columns(self, float_frame):
        float_frame["hi"] = "there"

        df = float_frame.copy()
        df.columns = ["foo", "bar", "baz", "quux", "foo2"]
        tm.assert_series_equal(float_frame["C"], df["baz"], check_names=False)
        tm.assert_series_equal(float_frame["hi"], df["foo2"], check_names=False)
