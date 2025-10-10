import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager|Passing a SingleBlockManager:DeprecationWarning"
)


class TestSeriesSubclassing:
    @pytest.mark.parametrize(
        "idx_method, indexer, exp_data, exp_idx",
        [
            ["loc", ["a", "b"], [1, 2], "ab"],
            ["iloc", [2, 3], [3, 4], "cd"],
        ],
    )
    def test_indexing_sliced(self, idx_method, indexer, exp_data, exp_idx):
        s = tm.SubclassedSeries([1, 2, 3, 4], index=list("abcd"))
        res = getattr(s, idx_method)[indexer]
        exp = tm.SubclassedSeries(exp_data, index=list(exp_idx))
        tm.assert_series_equal(res, exp)

    def test_to_frame(self):
        s = tm.SubclassedSeries([1, 2, 3, 4], index=list("abcd"), name="xxx")
        res = s.to_frame()
        exp = tm.SubclassedDataFrame({"xxx": [1, 2, 3, 4]}, index=list("abcd"))
        tm.assert_frame_equal(res, exp)

    def test_subclass_unstack(self):
        # GH 15564
        s = tm.SubclassedSeries([1, 2, 3, 4], index=[list("aabb"), list("xyxy")])

        res = s.unstack()
        exp = tm.SubclassedDataFrame({"x": [1, 3], "y": [2, 4]}, index=["a", "b"])

        tm.assert_frame_equal(res, exp)

    def test_subclass_empty_repr(self):
        sub_series = tm.SubclassedSeries()
        assert "SubclassedSeries" in repr(sub_series)

    def test_asof(self):
        N = 3
        rng = pd.date_range("1/1/1990", periods=N, freq="53s")
        s = tm.SubclassedSeries({"A": [np.nan, np.nan, np.nan]}, index=rng)

        result = s.asof(rng[-2:])
        assert isinstance(result, tm.SubclassedSeries)

    def test_explode(self):
        s = tm.SubclassedSeries([[1, 2, 3], "foo", [], [3, 4]])
        result = s.explode()
        assert isinstance(result, tm.SubclassedSeries)

    def test_equals(self):
        # https://github.com/pandas-dev/pandas/pull/34402
        # allow subclass in both directions
        s1 = pd.Series([1, 2, 3])
        s2 = tm.SubclassedSeries([1, 2, 3])
        assert s1.equals(s2)
        assert s2.equals(s1)


class SubclassedSeries(pd.Series):
    @property
    def _constructor(self):
        def _new(*args, **kwargs):
            # some constructor logic that accesses the Series' name
            if self.name == "test":
                return pd.Series(*args, **kwargs)
            return SubclassedSeries(*args, **kwargs)

        return _new


def test_constructor_from_dict():
    # https://github.com/pandas-dev/pandas/issues/52445
    result = SubclassedSeries({"a": 1, "b": 2, "c": 3})
    assert isinstance(result, SubclassedSeries)
