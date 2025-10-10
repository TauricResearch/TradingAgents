from datetime import date

import numpy as np
import pytest

from pandas import (
    Categorical,
    CategoricalDtype,
    CategoricalIndex,
    Index,
    IntervalIndex,
)
import pandas._testing as tm


class TestAstype:
    def test_astype(self):
        ci = CategoricalIndex(list("aabbca"), categories=list("cab"), ordered=False)

        result = ci.astype(object)
        tm.assert_index_equal(result, Index(np.array(ci), dtype=object))

        # this IS equal, but not the same class
        assert result.equals(ci)
        assert isinstance(result, Index)
        assert not isinstance(result, CategoricalIndex)

        # interval
        ii = IntervalIndex.from_arrays(left=[-0.001, 2.0], right=[2, 4], closed="right")

        ci = CategoricalIndex(
            Categorical.from_codes([0, 1, -1], categories=ii, ordered=True)
        )

        result = ci.astype("interval")
        expected = ii.take([0, 1, -1], allow_fill=True, fill_value=np.nan)
        tm.assert_index_equal(result, expected)

        result = IntervalIndex(result.values)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("name", [None, "foo"])
    @pytest.mark.parametrize("dtype_ordered", [True, False])
    @pytest.mark.parametrize("index_ordered", [True, False])
    def test_astype_category(self, name, dtype_ordered, index_ordered):
        # GH#18630
        index = CategoricalIndex(
            list("aabbca"), categories=list("cab"), ordered=index_ordered
        )
        if name:
            index = index.rename(name)

        # standard categories
        dtype = CategoricalDtype(ordered=dtype_ordered)
        result = index.astype(dtype)
        expected = CategoricalIndex(
            index.tolist(),
            name=name,
            categories=index.categories,
            ordered=dtype_ordered,
        )
        tm.assert_index_equal(result, expected)

        # non-standard categories
        dtype = CategoricalDtype(index.unique().tolist()[:-1], dtype_ordered)
        result = index.astype(dtype)
        expected = CategoricalIndex(index.tolist(), name=name, dtype=dtype)
        tm.assert_index_equal(result, expected)

        if dtype_ordered is False:
            # dtype='category' can't specify ordered, so only test once
            result = index.astype("category")
            expected = index
            tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("box", [True, False])
    def test_categorical_date_roundtrip(self, box):
        # astype to categorical and back should preserve date objects
        v = date.today()

        obj = Index([v, v])
        assert obj.dtype == object
        if box:
            obj = obj.array

        cat = obj.astype("category")

        rtrip = cat.astype(object)
        assert rtrip.dtype == object
        assert type(rtrip[0]) is date
