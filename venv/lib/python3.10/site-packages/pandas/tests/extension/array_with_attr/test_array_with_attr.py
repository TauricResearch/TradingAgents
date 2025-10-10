import numpy as np

import pandas as pd
import pandas._testing as tm
from pandas.tests.extension.array_with_attr import FloatAttrArray


def test_concat_with_all_na():
    # https://github.com/pandas-dev/pandas/pull/47762
    # ensure that attribute of the column array is preserved (when it gets
    # preserved in reindexing the array) during merge/concat
    arr = FloatAttrArray(np.array([np.nan, np.nan], dtype="float64"), attr="test")

    df1 = pd.DataFrame({"col": arr, "key": [0, 1]})
    df2 = pd.DataFrame({"key": [0, 1], "col2": [1, 2]})
    result = pd.merge(df1, df2, on="key")
    expected = pd.DataFrame({"col": arr, "key": [0, 1], "col2": [1, 2]})
    tm.assert_frame_equal(result, expected)
    assert result["col"].array.attr == "test"

    df1 = pd.DataFrame({"col": arr, "key": [0, 1]})
    df2 = pd.DataFrame({"key": [0, 2], "col2": [1, 2]})
    result = pd.merge(df1, df2, on="key")
    expected = pd.DataFrame({"col": arr.take([0]), "key": [0], "col2": [1]})
    tm.assert_frame_equal(result, expected)
    assert result["col"].array.attr == "test"

    result = pd.concat([df1.set_index("key"), df2.set_index("key")], axis=1)
    expected = pd.DataFrame(
        {"col": arr.take([0, 1, -1]), "col2": [1, np.nan, 2], "key": [0, 1, 2]}
    ).set_index("key")
    tm.assert_frame_equal(result, expected)
    assert result["col"].array.attr == "test"
