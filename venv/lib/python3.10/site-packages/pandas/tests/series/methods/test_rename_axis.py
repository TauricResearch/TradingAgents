import pytest

from pandas import (
    Index,
    MultiIndex,
    Series,
)
import pandas._testing as tm


class TestSeriesRenameAxis:
    def test_rename_axis_mapper(self):
        # GH 19978
        mi = MultiIndex.from_product([["a", "b", "c"], [1, 2]], names=["ll", "nn"])
        ser = Series(list(range(len(mi))), index=mi)

        result = ser.rename_axis(index={"ll": "foo"})
        assert result.index.names == ["foo", "nn"]

        result = ser.rename_axis(index=str.upper, axis=0)
        assert result.index.names == ["LL", "NN"]

        result = ser.rename_axis(index=["foo", "goo"])
        assert result.index.names == ["foo", "goo"]

        with pytest.raises(TypeError, match="unexpected"):
            ser.rename_axis(columns="wrong")

    def test_rename_axis_inplace(self, datetime_series):
        # GH 15704
        expected = datetime_series.rename_axis("foo")
        result = datetime_series
        no_return = result.rename_axis("foo", inplace=True)

        assert no_return is None
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("kwargs", [{"mapper": None}, {"index": None}, {}])
    def test_rename_axis_none(self, kwargs):
        # GH 25034
        index = Index(list("abc"), name="foo")
        ser = Series([1, 2, 3], index=index)

        result = ser.rename_axis(**kwargs)
        expected_index = index.rename(None) if kwargs else index
        expected = Series([1, 2, 3], index=expected_index)
        tm.assert_series_equal(result, expected)
