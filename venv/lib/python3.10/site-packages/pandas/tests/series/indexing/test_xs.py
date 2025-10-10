import numpy as np
import pytest

from pandas import (
    MultiIndex,
    Series,
    date_range,
)
import pandas._testing as tm


def test_xs_datetimelike_wrapping():
    # GH#31630 a case where we shouldn't wrap datetime64 in Timestamp
    arr = date_range("2016-01-01", periods=3)._data._ndarray

    ser = Series(arr, dtype=object)
    for i in range(len(ser)):
        ser.iloc[i] = arr[i]
    assert ser.dtype == object
    assert isinstance(ser[0], np.datetime64)

    result = ser.xs(0)
    assert isinstance(result, np.datetime64)


class TestXSWithMultiIndex:
    def test_xs_level_series(self, multiindex_dataframe_random_data):
        df = multiindex_dataframe_random_data
        ser = df["A"]
        expected = ser[:, "two"]
        result = df.xs("two", level=1)["A"]
        tm.assert_series_equal(result, expected)

    def test_series_getitem_multiindex_xs_by_label(self):
        # GH#5684
        idx = MultiIndex.from_tuples(
            [("a", "one"), ("a", "two"), ("b", "one"), ("b", "two")]
        )
        ser = Series([1, 2, 3, 4], index=idx)
        return_value = ser.index.set_names(["L1", "L2"], inplace=True)
        assert return_value is None
        expected = Series([1, 3], index=["a", "b"])
        return_value = expected.index.set_names(["L1"], inplace=True)
        assert return_value is None

        result = ser.xs("one", level="L2")
        tm.assert_series_equal(result, expected)

    def test_series_getitem_multiindex_xs(self):
        # GH#6258
        dt = list(date_range("20130903", periods=3))
        idx = MultiIndex.from_product([list("AB"), dt])
        ser = Series([1, 3, 4, 1, 3, 4], index=idx)
        expected = Series([1, 1], index=list("AB"))

        result = ser.xs("20130903", level=1)
        tm.assert_series_equal(result, expected)

    def test_series_xs_droplevel_false(self):
        # GH: 19056
        mi = MultiIndex.from_tuples(
            [("a", "x"), ("a", "y"), ("b", "x")], names=["level1", "level2"]
        )
        ser = Series([1, 1, 1], index=mi)
        result = ser.xs("a", axis=0, drop_level=False)
        expected = Series(
            [1, 1],
            index=MultiIndex.from_tuples(
                [("a", "x"), ("a", "y")], names=["level1", "level2"]
            ),
        )
        tm.assert_series_equal(result, expected)

    def test_xs_key_as_list(self):
        # GH#41760
        mi = MultiIndex.from_tuples([("a", "x")], names=["level1", "level2"])
        ser = Series([1], index=mi)
        with pytest.raises(TypeError, match="list keys are not supported"):
            ser.xs(["a", "x"], axis=0, drop_level=False)

        with pytest.raises(TypeError, match="list keys are not supported"):
            ser.xs(["a"], axis=0, drop_level=False)
