import pandas as pd
import pandas._testing as tm


def test_array_setitem_nullable_boolean_mask():
    # GH 31446
    ser = pd.Series([1, 2], dtype="Int64")
    result = ser.where(ser > 1)
    expected = pd.Series([pd.NA, 2], dtype="Int64")
    tm.assert_series_equal(result, expected)


def test_array_setitem():
    # GH 31446
    arr = pd.Series([1, 2], dtype="Int64").array
    arr[arr > 1] = 1

    expected = pd.array([1, 1], dtype="Int64")
    tm.assert_extension_array_equal(arr, expected)
