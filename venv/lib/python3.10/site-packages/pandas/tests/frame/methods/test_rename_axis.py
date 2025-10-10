import numpy as np
import pytest

from pandas import (
    DataFrame,
    Index,
    MultiIndex,
)
import pandas._testing as tm


class TestDataFrameRenameAxis:
    def test_rename_axis_inplace(self, float_frame):
        # GH#15704
        expected = float_frame.rename_axis("foo")
        result = float_frame.copy()
        return_value = no_return = result.rename_axis("foo", inplace=True)
        assert return_value is None

        assert no_return is None
        tm.assert_frame_equal(result, expected)

        expected = float_frame.rename_axis("bar", axis=1)
        result = float_frame.copy()
        return_value = no_return = result.rename_axis("bar", axis=1, inplace=True)
        assert return_value is None

        assert no_return is None
        tm.assert_frame_equal(result, expected)

    def test_rename_axis_raises(self):
        # GH#17833
        df = DataFrame({"A": [1, 2], "B": [1, 2]})
        with pytest.raises(ValueError, match="Use `.rename`"):
            df.rename_axis(id, axis=0)

        with pytest.raises(ValueError, match="Use `.rename`"):
            df.rename_axis({0: 10, 1: 20}, axis=0)

        with pytest.raises(ValueError, match="Use `.rename`"):
            df.rename_axis(id, axis=1)

        with pytest.raises(ValueError, match="Use `.rename`"):
            df["A"].rename_axis(id)

    def test_rename_axis_mapper(self):
        # GH#19978
        mi = MultiIndex.from_product([["a", "b", "c"], [1, 2]], names=["ll", "nn"])
        df = DataFrame(
            {"x": list(range(len(mi))), "y": [i * 10 for i in range(len(mi))]}, index=mi
        )

        # Test for rename of the Index object of columns
        result = df.rename_axis("cols", axis=1)
        tm.assert_index_equal(result.columns, Index(["x", "y"], name="cols"))

        # Test for rename of the Index object of columns using dict
        result = result.rename_axis(columns={"cols": "new"}, axis=1)
        tm.assert_index_equal(result.columns, Index(["x", "y"], name="new"))

        # Test for renaming index using dict
        result = df.rename_axis(index={"ll": "foo"})
        assert result.index.names == ["foo", "nn"]

        # Test for renaming index using a function
        result = df.rename_axis(index=str.upper, axis=0)
        assert result.index.names == ["LL", "NN"]

        # Test for renaming index providing complete list
        result = df.rename_axis(index=["foo", "goo"])
        assert result.index.names == ["foo", "goo"]

        # Test for changing index and columns at same time
        sdf = df.reset_index().set_index("nn").drop(columns=["ll", "y"])
        result = sdf.rename_axis(index="foo", columns="meh")
        assert result.index.name == "foo"
        assert result.columns.name == "meh"

        # Test different error cases
        with pytest.raises(TypeError, match="Must pass"):
            df.rename_axis(index="wrong")

        with pytest.raises(ValueError, match="Length of names"):
            df.rename_axis(index=["wrong"])

        with pytest.raises(TypeError, match="bogus"):
            df.rename_axis(bogus=None)

    @pytest.mark.parametrize(
        "kwargs, rename_index, rename_columns",
        [
            ({"mapper": None, "axis": 0}, True, False),
            ({"mapper": None, "axis": 1}, False, True),
            ({"index": None}, True, False),
            ({"columns": None}, False, True),
            ({"index": None, "columns": None}, True, True),
            ({}, False, False),
        ],
    )
    def test_rename_axis_none(self, kwargs, rename_index, rename_columns):
        # GH 25034
        index = Index(list("abc"), name="foo")
        columns = Index(["col1", "col2"], name="bar")
        data = np.arange(6).reshape(3, 2)
        df = DataFrame(data, index, columns)

        result = df.rename_axis(**kwargs)
        expected_index = index.rename(None) if rename_index else index
        expected_columns = columns.rename(None) if rename_columns else columns
        expected = DataFrame(data, expected_index, expected_columns)
        tm.assert_frame_equal(result, expected)
