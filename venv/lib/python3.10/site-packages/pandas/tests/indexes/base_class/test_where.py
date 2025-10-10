import numpy as np

from pandas import Index
import pandas._testing as tm


class TestWhere:
    def test_where_intlike_str_doesnt_cast_ints(self):
        idx = Index(range(3))
        mask = np.array([True, False, True])
        res = idx.where(mask, "2")
        expected = Index([0, "2", 2])
        tm.assert_index_equal(res, expected)
