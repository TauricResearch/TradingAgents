import re

import numpy as np
import pytest

from pandas import (
    DataFrame,
    MultiIndex,
)


class TestDataFrameDelItem:
    def test_delitem(self, float_frame):
        del float_frame["A"]
        assert "A" not in float_frame

    def test_delitem_multiindex(self):
        midx = MultiIndex.from_product([["A", "B"], [1, 2]])
        df = DataFrame(np.random.default_rng(2).standard_normal((4, 4)), columns=midx)
        assert len(df.columns) == 4
        assert ("A",) in df.columns
        assert "A" in df.columns

        result = df["A"]
        assert isinstance(result, DataFrame)
        del df["A"]

        assert len(df.columns) == 2

        # A still in the levels, BUT get a KeyError if trying
        # to delete
        assert ("A",) not in df.columns
        with pytest.raises(KeyError, match=re.escape("('A',)")):
            del df[("A",)]

        # behavior of dropped/deleted MultiIndex levels changed from
        # GH 2770 to GH 19027: MultiIndex no longer '.__contains__'
        # levels which are dropped/deleted
        assert "A" not in df.columns
        with pytest.raises(KeyError, match=re.escape("('A',)")):
            del df["A"]

    def test_delitem_corner(self, float_frame):
        f = float_frame.copy()
        del f["D"]
        assert len(f.columns) == 3
        with pytest.raises(KeyError, match=r"^'D'$"):
            del f["D"]
        del f["B"]
        assert len(f.columns) == 2

    def test_delitem_col_still_multiindex(self):
        arrays = [["a", "b", "c", "top"], ["", "", "", "OD"], ["", "", "", "wx"]]

        tuples = sorted(zip(*arrays))
        index = MultiIndex.from_tuples(tuples)

        df = DataFrame(np.random.default_rng(2).standard_normal((3, 4)), columns=index)
        del df[("a", "", "")]
        assert isinstance(df.columns, MultiIndex)
