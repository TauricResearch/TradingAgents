import collections

import numpy as np
import pytest

from pandas import Series
import pandas._testing as tm


class TestSeriesToDict:
    @pytest.mark.parametrize(
        "mapping", (dict, collections.defaultdict(list), collections.OrderedDict)
    )
    def test_to_dict(self, mapping, datetime_series):
        # GH#16122
        result = Series(datetime_series.to_dict(into=mapping), name="ts")
        expected = datetime_series.copy()
        expected.index = expected.index._with_freq(None)
        tm.assert_series_equal(result, expected)

        from_method = Series(datetime_series.to_dict(into=collections.Counter))
        from_constructor = Series(collections.Counter(datetime_series.items()))
        tm.assert_series_equal(from_method, from_constructor)

    @pytest.mark.parametrize(
        "input",
        (
            {"a": np.int64(64), "b": 10},
            {"a": np.int64(64), "b": 10, "c": "ABC"},
            {"a": np.uint64(64), "b": 10, "c": "ABC"},
        ),
    )
    def test_to_dict_return_types(self, input):
        # GH25969

        d = Series(input).to_dict()
        assert isinstance(d["a"], int)
        assert isinstance(d["b"], int)
