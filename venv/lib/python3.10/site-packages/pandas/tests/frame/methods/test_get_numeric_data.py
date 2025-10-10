import numpy as np

import pandas as pd
from pandas import (
    Categorical,
    DataFrame,
    Index,
    Series,
    Timestamp,
)
import pandas._testing as tm
from pandas.core.arrays import IntervalArray


class TestGetNumericData:
    def test_get_numeric_data_preserve_dtype(self):
        # get the numeric data
        obj = DataFrame({"A": [1, "2", 3.0]}, columns=Index(["A"], dtype="object"))
        result = obj._get_numeric_data()
        expected = DataFrame(dtype=object, index=pd.RangeIndex(3), columns=[])
        tm.assert_frame_equal(result, expected)

    def test_get_numeric_data(self, using_infer_string):
        datetime64name = np.dtype("M8[s]").name
        objectname = np.dtype(np.object_).name

        df = DataFrame(
            {"a": 1.0, "b": 2, "c": "foo", "f": Timestamp("20010102")},
            index=np.arange(10),
        )
        result = df.dtypes
        expected = Series(
            [
                np.dtype("float64"),
                np.dtype("int64"),
                np.dtype(objectname)
                if not using_infer_string
                else pd.StringDtype(na_value=np.nan),
                np.dtype(datetime64name),
            ],
            index=["a", "b", "c", "f"],
        )
        tm.assert_series_equal(result, expected)

        df = DataFrame(
            {
                "a": 1.0,
                "b": 2,
                "c": "foo",
                "d": np.array([1.0] * 10, dtype="float32"),
                "e": np.array([1] * 10, dtype="int32"),
                "f": np.array([1] * 10, dtype="int16"),
                "g": Timestamp("20010102"),
            },
            index=np.arange(10),
        )

        result = df._get_numeric_data()
        expected = df.loc[:, ["a", "b", "d", "e", "f"]]
        tm.assert_frame_equal(result, expected)

        only_obj = df.loc[:, ["c", "g"]]
        result = only_obj._get_numeric_data()
        expected = df.loc[:, []]
        tm.assert_frame_equal(result, expected)

        df = DataFrame.from_dict({"a": [1, 2], "b": ["foo", "bar"], "c": [np.pi, np.e]})
        result = df._get_numeric_data()
        expected = DataFrame.from_dict({"a": [1, 2], "c": [np.pi, np.e]})
        tm.assert_frame_equal(result, expected)

        df = result.copy()
        result = df._get_numeric_data()
        expected = df
        tm.assert_frame_equal(result, expected)

    def test_get_numeric_data_mixed_dtype(self):
        # numeric and object columns

        df = DataFrame(
            {
                "a": [1, 2, 3],
                "b": [True, False, True],
                "c": ["foo", "bar", "baz"],
                "d": [None, None, None],
                "e": [3.14, 0.577, 2.773],
            }
        )
        result = df._get_numeric_data()
        tm.assert_index_equal(result.columns, Index(["a", "b", "e"]))

    def test_get_numeric_data_extension_dtype(self):
        # GH#22290
        df = DataFrame(
            {
                "A": pd.array([-10, np.nan, 0, 10, 20, 30], dtype="Int64"),
                "B": Categorical(list("abcabc")),
                "C": pd.array([0, 1, 2, 3, np.nan, 5], dtype="UInt8"),
                "D": IntervalArray.from_breaks(range(7)),
            }
        )
        result = df._get_numeric_data()
        expected = df.loc[:, ["A", "C"]]
        tm.assert_frame_equal(result, expected)
