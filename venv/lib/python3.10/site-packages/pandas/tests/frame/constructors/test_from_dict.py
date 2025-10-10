from collections import OrderedDict

import numpy as np
import pytest

from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    RangeIndex,
    Series,
)
import pandas._testing as tm


class TestFromDict:
    # Note: these tests are specific to the from_dict method, not for
    #  passing dictionaries to DataFrame.__init__

    def test_constructor_list_of_odicts(self):
        data = [
            OrderedDict([["a", 1.5], ["b", 3], ["c", 4], ["d", 6]]),
            OrderedDict([["a", 1.5], ["b", 3], ["d", 6]]),
            OrderedDict([["a", 1.5], ["d", 6]]),
            OrderedDict(),
            OrderedDict([["a", 1.5], ["b", 3], ["c", 4]]),
            OrderedDict([["b", 3], ["c", 4], ["d", 6]]),
        ]

        result = DataFrame(data)
        expected = DataFrame.from_dict(
            dict(zip(range(len(data)), data)), orient="index"
        )
        tm.assert_frame_equal(result, expected.reindex(result.index))

    def test_constructor_single_row(self):
        data = [OrderedDict([["a", 1.5], ["b", 3], ["c", 4], ["d", 6]])]

        result = DataFrame(data)
        expected = DataFrame.from_dict(dict(zip([0], data)), orient="index").reindex(
            result.index
        )
        tm.assert_frame_equal(result, expected)

    def test_constructor_list_of_series(self):
        data = [
            OrderedDict([["a", 1.5], ["b", 3.0], ["c", 4.0]]),
            OrderedDict([["a", 1.5], ["b", 3.0], ["c", 6.0]]),
        ]
        sdict = OrderedDict(zip(["x", "y"], data))
        idx = Index(["a", "b", "c"])

        # all named
        data2 = [
            Series([1.5, 3, 4], idx, dtype="O", name="x"),
            Series([1.5, 3, 6], idx, name="y"),
        ]
        result = DataFrame(data2)
        expected = DataFrame.from_dict(sdict, orient="index")
        tm.assert_frame_equal(result, expected)

        # some unnamed
        data2 = [
            Series([1.5, 3, 4], idx, dtype="O", name="x"),
            Series([1.5, 3, 6], idx),
        ]
        result = DataFrame(data2)

        sdict = OrderedDict(zip(["x", "Unnamed 0"], data))
        expected = DataFrame.from_dict(sdict, orient="index")
        tm.assert_frame_equal(result, expected)

        # none named
        data = [
            OrderedDict([["a", 1.5], ["b", 3], ["c", 4], ["d", 6]]),
            OrderedDict([["a", 1.5], ["b", 3], ["d", 6]]),
            OrderedDict([["a", 1.5], ["d", 6]]),
            OrderedDict(),
            OrderedDict([["a", 1.5], ["b", 3], ["c", 4]]),
            OrderedDict([["b", 3], ["c", 4], ["d", 6]]),
        ]
        data = [Series(d) for d in data]

        result = DataFrame(data)
        sdict = OrderedDict(zip(range(len(data)), data))
        expected = DataFrame.from_dict(sdict, orient="index")
        tm.assert_frame_equal(result, expected.reindex(result.index))

        result2 = DataFrame(data, index=np.arange(6, dtype=np.int64))
        tm.assert_frame_equal(result, result2)

        result = DataFrame([Series(dtype=object)])
        expected = DataFrame(index=[0])
        tm.assert_frame_equal(result, expected)

        data = [
            OrderedDict([["a", 1.5], ["b", 3.0], ["c", 4.0]]),
            OrderedDict([["a", 1.5], ["b", 3.0], ["c", 6.0]]),
        ]
        sdict = OrderedDict(zip(range(len(data)), data))

        idx = Index(["a", "b", "c"])
        data2 = [Series([1.5, 3, 4], idx, dtype="O"), Series([1.5, 3, 6], idx)]
        result = DataFrame(data2)
        expected = DataFrame.from_dict(sdict, orient="index")
        tm.assert_frame_equal(result, expected)

    def test_constructor_orient(self, float_string_frame):
        data_dict = float_string_frame.T._series
        recons = DataFrame.from_dict(data_dict, orient="index")
        expected = float_string_frame.reindex(index=recons.index)
        tm.assert_frame_equal(recons, expected)

        # dict of sequence
        a = {"hi": [32, 3, 3], "there": [3, 5, 3]}
        rs = DataFrame.from_dict(a, orient="index")
        xp = DataFrame.from_dict(a).T.reindex(list(a.keys()))
        tm.assert_frame_equal(rs, xp)

    def test_constructor_from_ordered_dict(self):
        # GH#8425
        a = OrderedDict(
            [
                ("one", OrderedDict([("col_a", "foo1"), ("col_b", "bar1")])),
                ("two", OrderedDict([("col_a", "foo2"), ("col_b", "bar2")])),
                ("three", OrderedDict([("col_a", "foo3"), ("col_b", "bar3")])),
            ]
        )
        expected = DataFrame.from_dict(a, orient="columns").T
        result = DataFrame.from_dict(a, orient="index")
        tm.assert_frame_equal(result, expected)

    def test_from_dict_columns_parameter(self):
        # GH#18529
        # Test new columns parameter for from_dict that was added to make
        # from_items(..., orient='index', columns=[...]) easier to replicate
        result = DataFrame.from_dict(
            OrderedDict([("A", [1, 2]), ("B", [4, 5])]),
            orient="index",
            columns=["one", "two"],
        )
        expected = DataFrame([[1, 2], [4, 5]], index=["A", "B"], columns=["one", "two"])
        tm.assert_frame_equal(result, expected)

        msg = "cannot use columns parameter with orient='columns'"
        with pytest.raises(ValueError, match=msg):
            DataFrame.from_dict(
                {"A": [1, 2], "B": [4, 5]},
                orient="columns",
                columns=["one", "two"],
            )
        with pytest.raises(ValueError, match=msg):
            DataFrame.from_dict({"A": [1, 2], "B": [4, 5]}, columns=["one", "two"])

    @pytest.mark.parametrize(
        "data_dict, orient, expected",
        [
            ({}, "index", RangeIndex(0)),
            (
                [{("a",): 1}, {("a",): 2}],
                "columns",
                Index([("a",)], tupleize_cols=False),
            ),
            (
                [OrderedDict([(("a",), 1), (("b",), 2)])],
                "columns",
                Index([("a",), ("b",)], tupleize_cols=False),
            ),
            ([{("a", "b"): 1}], "columns", Index([("a", "b")], tupleize_cols=False)),
        ],
    )
    def test_constructor_from_dict_tuples(self, data_dict, orient, expected):
        # GH#16769
        df = DataFrame.from_dict(data_dict, orient)
        result = df.columns
        tm.assert_index_equal(result, expected)

    def test_frame_dict_constructor_empty_series(self):
        s1 = Series(
            [1, 2, 3, 4], index=MultiIndex.from_tuples([(1, 2), (1, 3), (2, 2), (2, 4)])
        )
        s2 = Series(
            [1, 2, 3, 4], index=MultiIndex.from_tuples([(1, 2), (1, 3), (3, 2), (3, 4)])
        )
        s3 = Series(dtype=object)

        # it works!
        DataFrame({"foo": s1, "bar": s2, "baz": s3})
        DataFrame.from_dict({"foo": s1, "baz": s3, "bar": s2})

    def test_from_dict_scalars_requires_index(self):
        msg = "If using all scalar values, you must pass an index"
        with pytest.raises(ValueError, match=msg):
            DataFrame.from_dict(OrderedDict([("b", 8), ("a", 5), ("a", 6)]))

    def test_from_dict_orient_invalid(self):
        msg = (
            "Expected 'index', 'columns' or 'tight' for orient parameter. "
            "Got 'abc' instead"
        )
        with pytest.raises(ValueError, match=msg):
            DataFrame.from_dict({"foo": 1, "baz": 3, "bar": 2}, orient="abc")

    def test_from_dict_order_with_single_column(self):
        data = {
            "alpha": {
                "value2": 123,
                "value1": 532,
                "animal": 222,
                "plant": False,
                "name": "test",
            }
        }
        result = DataFrame.from_dict(
            data,
            orient="columns",
        )
        expected = DataFrame(
            [[123], [532], [222], [False], ["test"]],
            index=["value2", "value1", "animal", "plant", "name"],
            columns=["alpha"],
        )
        tm.assert_frame_equal(result, expected)
